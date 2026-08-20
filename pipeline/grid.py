"""Rede de distribuicao realista, construida sobre a malha viaria real do bairro.

Por que assim: a versao anterior ligava cada imovel direto a um "hub" e todos os hubs
a um ponto central, produzindo um feixe radial que atravessava quarteirao, telhado e
terreno - visualmente um ourico, e eletricamente sem sentido. Uma rede de distribuicao
real e RADIAL mas corre SOBRE AS RUAS: sai da subestacao, percorre avenidas e ruas,
alimenta transformadores espalhados ao longo das vias, e cada transformador atende as
casas do seu trecho por um ramal curto ate a fachada.

Este modulo reproduz essa topologia:

  subestacao ──(alimentador sobre a geometria da rua)──> transformador ──(ramal)──> imovel

  1. Grafo viario do OSM (osmnx), projetado em UTM.
  2. Subestacao = no sobre a via de maior hierarquia mais proxima do centro do bairro.
  3. Arvore radial = caminhos minimos (Dijkstra por comprimento) da subestacao.
     Isso e literalmente a topologia de um alimentador: sem malha, sem anel.
  4. Cada imovel e projetado na aresta viaria mais proxima -> ponto de conexao na rua.
     O ramal e o segmento curto imovel->rua (perpendicular a via, como na realidade).
  5. Transformadores: os imoveis de um mesmo trecho de rua sao ordenados ao longo da
     via e agrupados em lotes de ~30 (faixa real de atendimento de um trafo de poste,
     e que coincide com o minimo de agregacao que a LGPD nos exige).
  6. Carga por trecho de rua = soma das curvas de 24h de todos os imoveis cujo caminho
     ate a subestacao passa por aquele trecho. Avenida troncal fica carregada, rua sem
     saida fica leve - exatamente o que um analista de rede espera ver.
"""
from __future__ import annotations

from collections import defaultdict

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry import LineString, Point

import cache_osm
import osm_util

UTM_CRS = "EPSG:31982"
WGS84 = "EPSG:4326"

TRAFO_ALVO = 30   # imoveis por transformador (alvo)
TRAFO_MINIMO = 15  # piso de agregacao (LGPD): nenhum grupo publicado abaixo disso

# Hierarquia viaria: o alimentador entra pela via mais importante disponivel.
HIERARQUIA = ["primary", "secondary", "tertiary", "residential", "unclassified", "service"]


def _classe(valor) -> str:
    if isinstance(valor, list):
        valor = valor[0] if valor else "residential"
    return str(valor)


def carregar_ruas(poligono) -> nx.MultiDiGraph:
    """Malha viaria do bairro.

    Consulta por bairro e barata (a malha de um bairro tem ~200 nos e volta em
    segundos), entao so vale usar o cache municipal se ele ja existir — baixar a
    malha da cidade inteira custa muito mais do que as 37 consultas somadas.
    """
    if cache_osm.vias_disponivel():
        G = cache_osm.recortar_vias(poligono)
    else:
        osm_util.configurar()
        G = osm_util.com_retry(
            lambda: ox.graph_from_polygon(poligono, network_type="all", simplify=True),
            rotulo="malha viaria",
        )
    return ox.projection.project_graph(G, to_crs=UTM_CRS)


def _maior_componente(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    Gu = ox.convert.to_undirected(G)
    if nx.is_connected(Gu):
        return G
    maior = max(nx.connected_components(Gu), key=len)
    return G.subgraph(maior).copy()


def escolher_subestacao_real(G: nx.MultiDiGraph, poligono) -> tuple[int, dict] | None:
    """Ancora a arvore na subestacao REAL mais proxima (OSM `power=substation`).

    A subestacao costuma ficar fora do bairro que alimenta, entao o ponto de entrada
    na rede local e o no viario mais proximo dela — o alimentador chega por ali.
    """
    try:
        import subestacoes
        info = subestacoes.mais_proxima(poligono.centroid)
    except Exception:  # noqa: BLE001 - sem OSM disponivel, cai no fallback sintetico
        return None
    if info is None:
        return None

    ponto_utm = gpd.GeoSeries([info["geometry"]], crs=WGS84).to_crs(UTM_CRS).iloc[0]
    no = min(
        G.nodes,
        key=lambda n: (G.nodes[n]["x"] - ponto_utm.x) ** 2 + (G.nodes[n]["y"] - ponto_utm.y) ** 2,
    )
    return no, info


def escolher_subestacao(G: nx.MultiDiGraph, centro_utm: Point) -> int:
    """Fallback sintetico: no sobre a via de maior hierarquia, mais proximo do centro."""
    por_classe: dict[str, set[int]] = defaultdict(set)
    for u, v, data in G.edges(data=True):
        classe = _classe(data.get("highway", "residential"))
        por_classe[classe].add(u)
        por_classe[classe].add(v)

    candidatos: set[int] = set()
    for classe in HIERARQUIA:
        if por_classe.get(classe):
            candidatos = por_classe[classe]
            break
    if not candidatos:
        candidatos = set(G.nodes)

    return min(
        candidatos,
        key=lambda n: (G.nodes[n]["x"] - centro_utm.x) ** 2 + (G.nodes[n]["y"] - centro_utm.y) ** 2,
    )


def _geometria_aresta(G, u, v, k) -> LineString:
    data = G.edges[u, v, k]
    if "geometry" in data:
        return data["geometry"]
    return LineString(
        [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
    )


def conectar_imoveis(G: nx.MultiDiGraph, predios_utm: gpd.GeoSeries) -> dict:
    """Projeta cada imovel na via mais proxima. Retorna arestas, pontos e distancias."""
    centroides = predios_utm.centroid
    xs = centroides.x.to_numpy()
    ys = centroides.y.to_numpy()

    arestas = ox.distance.nearest_edges(G, xs, ys)

    pontos_rua = []
    posicao_na_via = []
    ramais = []
    for i, (u, v, k) in enumerate(arestas):
        linha = _geometria_aresta(G, u, v, k)
        origem = Point(xs[i], ys[i])
        s = linha.project(origem)
        destino = linha.interpolate(s)
        pontos_rua.append(destino)
        posicao_na_via.append(s)
        ramais.append(LineString([origem, destino]))

    return {
        "arestas": arestas,
        "pontos_rua": pontos_rua,
        "posicao_na_via": np.asarray(posicao_na_via),
        "ramais": ramais,
        "centroides": list(centroides),
    }


def agrupar_transformadores(conexoes: dict, elegivel: np.ndarray) -> np.ndarray:
    """Agrupa imoveis por trecho de rua e fatia em lotes de ~TRAFO_ALVO.

    Retorna vetor de trafo_id (-1 para imoveis nao elegiveis, ex.: garagens).
    """
    trafo = np.full(len(elegivel), -1, dtype=int)

    por_aresta: dict[tuple, list[int]] = defaultdict(list)
    for i, aresta in enumerate(conexoes["arestas"]):
        if elegivel[i]:
            por_aresta[tuple(aresta)].append(i)

    proximo = 0
    grupos: dict[int, list[int]] = {}
    for _aresta, indices in por_aresta.items():
        indices.sort(key=lambda i: conexoes["posicao_na_via"][i])
        n = len(indices)
        n_lotes = max(1, round(n / TRAFO_ALVO))
        for lote in np.array_split(np.asarray(indices), n_lotes):
            if len(lote) == 0:
                continue
            grupos[proximo] = list(lote)
            for i in lote:
                trafo[i] = proximo
            proximo += 1

    _fundir_pequenos(grupos, trafo, conexoes)

    # renumera 0..n-1
    remap = {antigo: novo for novo, antigo in enumerate(sorted(set(trafo[trafo >= 0])))}
    for i, t in enumerate(trafo):
        if t >= 0:
            trafo[i] = remap[t]
    return trafo


def _centro_grupo(indices: list[int], conexoes: dict) -> np.ndarray:
    pts = [conexoes["pontos_rua"][i] for i in indices]
    return np.array([np.mean([p.x for p in pts]), np.mean([p.y for p in pts])])


def _fundir_pequenos(grupos: dict[int, list[int]], trafo: np.ndarray, conexoes: dict) -> None:
    """Funde grupos abaixo do piso de privacidade no vizinho mais proximo."""
    while True:
        pequenos = [g for g, idx in grupos.items() if len(idx) < TRAFO_MINIMO]
        if not pequenos or len(grupos) <= 1:
            break

        alvo = min(pequenos, key=lambda g: len(grupos[g]))
        centro_alvo = _centro_grupo(grupos[alvo], conexoes)

        vizinho = min(
            (g for g in grupos if g != alvo),
            key=lambda g: np.sum((_centro_grupo(grupos[g], conexoes) - centro_alvo) ** 2),
        )
        grupos[vizinho].extend(grupos[alvo])
        for i in grupos[alvo]:
            trafo[i] = vizinho
        del grupos[alvo]


def acumular_carga(
    G: nx.MultiDiGraph,
    fonte: int,
    conexoes: dict,
    curvas: np.ndarray,
    elegivel: np.ndarray,
    trafo: np.ndarray,
) -> dict[tuple[int, int], np.ndarray]:
    """Carga de cada trecho do alimentador de MEDIA TENSAO.

    Ponto importante de modelagem: a rede real tem dois niveis, e eles nao se misturam.
    O alimentador de media tensao sai da subestacao e percorre as vias ate os
    transformadores; a baixa tensao vai de cada transformador ate as ~30 casas dele
    (que aqui sao os ramais, desenhados a parte).

    Uma versao anterior somava a curva de CADA IMOVEL ao longo de todo o caminho ate a
    subestacao, misturando os dois niveis. O efeito era visivel e errado: na Avenida das
    Cataratas, trechos vizinhos de ~97 m apareciam com pico de 0,62 e 67 kWh (fator
    108x), e 62% dos trechos chegavam a ficar negativos — porque um punhado de
    prosumidores bastava para inverter um trecho que so servia a eles.

    Agora quem percorre a arvore e o TRANSFORMADOR, com a curva ja agregada dos seus
    imoveis. Os trechos passam a carregar somas de transformadores a jusante, que e o
    que um tronco de avenida de fato carrega — e a agregacao suaviza a inversao, como
    na rede real.
    """
    caminhos = nx.single_source_dijkstra_path(ox.convert.to_undirected(G), fonte, weight="length")

    # Curva agregada e no de entrada de cada transformador.
    agregada: dict[int, np.ndarray] = defaultdict(lambda: np.zeros(24))
    no_entrada: dict[int, tuple[int, int]] = {}
    for i, (u, v, _k) in enumerate(conexoes["arestas"]):
        if not elegivel[i] or trafo[i] < 0:
            continue
        tid = int(trafo[i])
        agregada[tid] += curvas[i]
        no_entrada.setdefault(tid, (u, v))

    carga: dict[tuple[int, int], np.ndarray] = defaultdict(lambda: np.zeros(24))
    for tid, curva in agregada.items():
        u, v = no_entrada[tid]
        entrada = u if u in caminhos else v
        if entrada not in caminhos:
            continue
        for a, b in zip(caminhos[entrada][:-1], caminhos[entrada][1:]):
            carga[(min(a, b), max(a, b))] += curva
        # o proprio trecho onde o transformador esta tambem carrega
        carga[(min(u, v), max(u, v))] += curva
    return carga


def montar(poligono, predios: gpd.GeoDataFrame, curvas: np.ndarray) -> dict:
    """Constroi a rede completa. `curvas` = matriz (n_imoveis, 24) em kWh."""
    G = _maior_componente(carregar_ruas(poligono))

    real = escolher_subestacao_real(G, poligono)
    if real is not None:
        fonte, info_subestacao = real
    else:
        centro_utm = gpd.GeoSeries([poligono], crs=WGS84).to_crs(UTM_CRS).centroid.iloc[0]
        fonte = escolher_subestacao(G, centro_utm)
        info_subestacao = None

    predios_utm = predios.geometry.to_crs(UTM_CRS)
    conexoes = conectar_imoveis(G, predios_utm)

    elegivel = predios["e_domicilio"].to_numpy(dtype=bool)
    trafo = agrupar_transformadores(conexoes, elegivel)
    carga = acumular_carga(G, fonte, conexoes, curvas, elegivel, trafo)

    return {
        "grafo": G,
        "fonte": fonte,
        "subestacao": info_subestacao,
        "conexoes": conexoes,
        "trafo": trafo,
        "carga_trechos": carga,
        "curvas": curvas,
        "elegivel": elegivel,
    }


# ---------------------------------------------------------------- exportacao

def alimentadores_geojson(rede: dict) -> gpd.GeoDataFrame:
    G, carga = rede["grafo"], rede["carga_trechos"]
    linhas, registros = [], []
    vistos = set()

    for u, v, k, data in G.edges(keys=True, data=True):
        chave = (min(u, v), max(u, v), k)
        if chave in vistos:
            continue
        vistos.add(chave)

        curva = carga.get((min(u, v), max(u, v)))
        if curva is None:
            continue  # trecho sem nenhum imovel a jusante

        linhas.append(_geometria_aresta(G, u, v, k))
        registros.append(
            {
                "classe_via": _classe(data.get("highway", "residential")),
                "nome_via": str(data.get("name", "")) if data.get("name") else "",
                "comprimento_m": round(float(data.get("length", 0.0)), 1),
                "carga_kwh": [round(float(x), 3) for x in curva],
                "carga_pico_kwh": round(float(curva.max()), 2),
            }
        )

    gdf = gpd.GeoDataFrame(registros, geometry=linhas, crs=UTM_CRS)
    return gdf.to_crs(WGS84)


def ramais_geojson(rede: dict, predios: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    conexoes, elegivel = rede["conexoes"], rede["elegivel"]
    linhas, registros = [], []
    for i in range(len(predios)):
        if not elegivel[i]:
            continue
        linhas.append(conexoes["ramais"][i])
        registros.append(
            {
                "building_id": predios["building_id"].iloc[i],
                "trafo_id": int(rede["trafo"][i]),
                "carga_kwh": [round(float(x), 3) for x in rede["curvas"][i]],
            }
        )
    gdf = gpd.GeoDataFrame(registros, geometry=linhas, crs=UTM_CRS)
    return gdf.to_crs(WGS84)


def transformadores_geojson(rede: dict, predios: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    conexoes, trafo, curvas = rede["conexoes"], rede["trafo"], rede["curvas"]
    perfis = predios["perfil"].to_numpy()

    pontos, registros = [], []
    for tid in sorted(set(trafo[trafo >= 0])):
        idx = np.where(trafo == tid)[0]
        centro = _centro_grupo(list(idx), conexoes)
        agregada = curvas[idx].sum(axis=0)

        contagem: dict[str, int] = {}
        for p in perfis[idx]:
            contagem[p] = contagem.get(p, 0) + 1

        pontos.append(Point(centro[0], centro[1]))
        registros.append(
            {
                "trafo_id": int(tid),
                "n_imoveis": int(len(idx)),
                "n_residencial": contagem.get("residencial", 0),
                "n_prosumidor": contagem.get("prosumidor", 0),
                "n_comercial": contagem.get("comercial", 0),
                "carga_kwh": [round(float(x), 3) for x in agregada],
                "carga_pico_kwh": round(float(agregada.max()), 2),
            }
        )

    gdf = gpd.GeoDataFrame(registros, geometry=pontos, crs=UTM_CRS)
    return gdf.to_crs(WGS84)


def subestacao_geojson(rede: dict) -> gpd.GeoDataFrame:
    G, fonte, info = rede["grafo"], rede["fonte"], rede.get("subestacao")
    total = np.zeros(24)
    for curva, ok in zip(rede["curvas"], rede["elegivel"]):
        if ok:
            total += curva

    props = {
        "carga_kwh": [round(float(x), 3) for x in total],
        "carga_pico_kwh": round(float(total.max()), 2),
    }

    if info is not None:
        # Posicao REAL do equipamento (OSM), nao o no viario onde o alimentador entra.
        props |= {
            "nome": info["nome"],
            "operador": info["operador"],
            "tensao_v": info["tensao"],
            "fonte_dado": "OpenStreetMap (power=substation)",
            "distancia_ao_bairro_m": info["distancia_m"],
        }
        gdf = gpd.GeoDataFrame([props], geometry=[info["geometry"]], crs=WGS84)
        return gdf

    props |= {
        "nome": "Ponto de entrada estimado",
        "operador": "",
        "tensao_v": "",
        "fonte_dado": "estimado (nó viário de maior hierarquia) — nenhuma subestação mapeada por perto",
        "distancia_ao_bairro_m": 0,
    }
    ponto = Point(G.nodes[fonte]["x"], G.nodes[fonte]["y"])
    return gpd.GeoDataFrame([props], geometry=[ponto], crs=UTM_CRS).to_crs(WGS84)
