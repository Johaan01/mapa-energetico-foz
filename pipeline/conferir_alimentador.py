"""Conferência independente de um trecho do alimentador.

A carga de um trecho deveria ser, por construção, a soma das curvas de todos os
transformadores que dependem dele para chegar à subestação. Este script recalcula isso
do zero — refazendo a árvore de caminhos mínimos a partir do grafo viário e somando os
transformadores a jusante — e compara com o que o pipeline gravou no GeoJSON.

É uma conferência de verdade e não uma repetição da mesma conta: o pipeline acumula
percorrendo o caminho de cada transformador (empurra), enquanto aqui se identifica
quem está a jusante de cada trecho e soma (puxa). Se as duas chegarem ao mesmo número,
a topologia e a acumulação estão coerentes.

    python conferir_alimentador.py [bairro]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry import Point

import bairros
import grid

RAIZ = Path(__file__).resolve().parent.parent
TOLERANCIA = 0.01  # kWh


def main() -> None:
    nome = sys.argv[1] if len(sys.argv) > 1 else "Yolanda"
    linha = bairros.buscar(nome)
    slug = bairros.slug(linha["NM_BAIRRO"])
    pasta = RAIZ / "web" / "data" / "bairros" / slug

    feeders = gpd.read_file(pasta / "feeders.geojson")
    trafos = gpd.read_file(pasta / "transformers.geojson")
    sub = gpd.read_file(pasta / "substation.geojson")

    print(f"Bairro: {linha['NM_BAIRRO']}  ({len(feeders)} trechos, {len(trafos)} trafos)\n")

    # Reconstrói a rede viária e a árvore radial exatamente como o pipeline faz.
    G = grid._maior_componente(grid.carregar_ruas(linha.geometry))
    Gu = ox.convert.to_undirected(G)

    real = grid.escolher_subestacao_real(G, linha.geometry)
    fonte = real[0] if real else grid.escolher_subestacao(
        G, gpd.GeoSeries([linha.geometry], crs=4326).to_crs(grid.UTM_CRS).centroid.iloc[0])
    caminhos = nx.single_source_dijkstra_path(Gu, fonte, weight="length")

    # Nó de entrada de cada transformador: o nó do grafo mais próximo dele.
    nos = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in G.nodes])
    lista_nos = list(G.nodes)
    trafos_utm = trafos.geometry.to_crs(grid.UTM_CRS)

    entrada_por_trafo = {}
    for i, pt in enumerate(trafos_utm):
        d = np.hypot(nos[:, 0] - pt.x, nos[:, 1] - pt.y)
        entrada_por_trafo[int(trafos.iloc[i]["trafo_id"])] = lista_nos[int(d.argmin())]

    # Escolhe um trecho de porte médio-alto numa via nomeada — o caso que interessa
    # conferir é o tronco, não a ponta.
    candidatos = feeders[(feeders["carga_pico_kwh"] > feeders["carga_pico_kwh"].median())
                         & (feeders["nome_via"].astype(str).str.len() > 3)]
    escolhido = candidatos.sort_values("carga_pico_kwh").iloc[len(candidatos) // 2]

    nome_via = escolhido["nome_via"]
    print(f"Trecho conferido : {nome_via}")
    print(f"  classe         : {escolhido['classe_via']}")
    print(f"  extensão       : {escolhido['comprimento_m']} m")
    print(f"  pico gravado   : {escolhido['carga_pico_kwh']} kWh")

    # Quais nós do grafo são os extremos deste trecho?
    linha_geom = escolhido.geometry
    p0 = gpd.GeoSeries([Point(linha_geom.coords[0])], crs=4326).to_crs(grid.UTM_CRS).iloc[0]
    p1 = gpd.GeoSeries([Point(linha_geom.coords[-1])], crs=4326).to_crs(grid.UTM_CRS).iloc[0]
    extremos = []
    for p in (p0, p1):
        d = np.hypot(nos[:, 0] - p.x, nos[:, 1] - p.y)
        extremos.append(lista_nos[int(d.argmin())])
    u, v = extremos
    aresta = (min(u, v), max(u, v))

    # Um transformador está a jusante se o caminho dele até a subestação usa este trecho.
    jusante = []
    for tid, no in entrada_por_trafo.items():
        caminho = caminhos.get(no)
        if not caminho:
            continue
        pares = {(min(a, b), max(a, b)) for a, b in zip(caminho[:-1], caminho[1:])}
        # o próprio trecho de conexão do trafo também conta
        if aresta in pares or (no in (u, v) and aresta in pares) or aresta in pares:
            jusante.append(tid)
        elif no in (u, v):
            jusante.append(tid)

    curvas = {int(r["trafo_id"]): np.asarray(r["carga_kwh"], dtype=float)
              for _, r in trafos.iterrows()}
    soma = np.zeros(24)
    for tid in jusante:
        soma += curvas[tid]

    gravado = np.asarray(escolhido["carga_kwh"], dtype=float)
    dif = np.abs(soma - gravado).max()

    print(f"\n  transformadores a jusante : {len(jusante)}")
    print(f"  imóveis atendidos por eles: "
          f"{int(trafos[trafos['trafo_id'].isin(jusante)]['n_imoveis'].sum())}")
    print(f"  pico recalculado          : {soma.max():.2f} kWh")
    print(f"  maior diferença hora a hora: {dif:.4f} kWh")

    ok_soma = dif <= TOLERANCIA
    print(f"\n  [{'OK' if ok_soma else 'DIVERGE'}] carga do trecho = soma dos trafos a jusante")

    # Coerências independentes da acumulação.
    total_trafos = sum(curvas.values())
    total_sub = np.asarray(sub.iloc[0]["carga_kwh"], dtype=float)
    dif_sub = np.abs(total_trafos - total_sub).max()
    print(f"  [{'OK' if dif_sub <= TOLERANCIA else 'DIVERGE'}] "
          f"soma de TODOS os trafos = carga da subestação (dif {dif_sub:.4f} kWh)")

    maior = feeders.loc[feeders["carga_pico_kwh"].idxmax()]
    print(f"  [{'OK' if maior['carga_pico_kwh'] <= total_sub.max() + TOLERANCIA else 'DIVERGE'}] "
          f"nenhum trecho excede a subestação "
          f"({maior['carga_pico_kwh']:.1f} <= {total_sub.max():.1f} kWh)")

    n_ucs = int(trafos["n_imoveis"].sum())
    meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
    print(f"  [{'OK' if n_ucs == meta['unidades_consumidoras'] else 'DIVERGE'}] "
          f"imóveis nos trafos = UCs do bairro ({n_ucs} vs {meta['unidades_consumidoras']})")


if __name__ == "__main__":
    main()
