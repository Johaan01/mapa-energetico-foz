"""Cache local do OpenStreetMap para o municipio inteiro.

Motivacao: consultar a Overpass uma vez por bairro significa 74 consultas (37 bairros
x edificacoes + malha viaria) num servico publico com rate limit — na pratica o lote
trava esperando slot. Baixar o municipio INTEIRO uma unica vez e recortar localmente
com geopandas reduz isso a 2 consultas e deixa o resto offline e reprodutivel.

    python cache_osm.py            # baixa e grava o cache
    python cache_osm.py --forcar   # refaz mesmo se ja existir
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd

import bairros
import osm_util

CACHE = Path(__file__).resolve().parent.parent / "data" / "osm_cache"
PREDIOS_GPKG = CACHE / "predios_municipio.gpkg"
GRAFO_GRAPHML = CACHE / "vias_municipio.graphml"

WGS84 = "EPSG:4326"

_predios: gpd.GeoDataFrame | None = None
_grafo: nx.MultiDiGraph | None = None


def contorno_municipio(municipio: str = bairros.MUNICIPIO_PADRAO):
    """Uniao dos bairros oficiais do IBGE — evita depender do geocoder do OSM."""
    gdf = bairros.listar(municipio)
    return gdf.geometry.union_all()


def _blocos(contorno, n: int) -> list[tuple[float, float, float, float]]:
    """Grade n x n de bboxes cobrindo o contorno.

    Uma consulta unica de ~360 km2 fica minutos na fila da Overpass; varias consultas
    menores por bbox sao processadas muito mais rapido e falham de forma isolada
    (um bloco ruim nao derruba o resto).
    """
    minx, miny, maxx, maxy = contorno.bounds
    dx, dy = (maxx - minx) / n, (maxy - miny) / n
    return [
        (minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy)
        for i in range(n)
        for j in range(n)
    ]


def construir(forcar: bool = False, n_blocos: int = 4) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    osm_util.configurar()
    contorno = contorno_municipio()
    blocos = _blocos(contorno, n_blocos)

    if forcar or not PREDIOS_GPKG.exists():
        print(f"Edificacoes do municipio em {len(blocos)} blocos...", flush=True)
        partes: list[gpd.GeoDataFrame] = []
        for i, bbox in enumerate(blocos, 1):
            try:
                gdf = osm_util.com_retry(
                    lambda b=bbox: ox.features_from_bbox(bbox=b, tags={"building": True}),
                    rotulo=f"predios bloco {i}",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  bloco {i}/{len(blocos)}: sem dados ({type(exc).__name__})", flush=True)
                continue

            gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if gdf.empty:
                print(f"  bloco {i}/{len(blocos)}: vazio", flush=True)
                continue

            tipo = gdf["building"] if "building" in gdf.columns else "yes"
            partes.append(
                gpd.GeoDataFrame(
                    {"tipo_osm": [str(t) for t in tipo], "geometry": gdf.geometry.values},
                    crs=gdf.crs,
                ).to_crs(WGS84)
            )
            print(f"  bloco {i}/{len(blocos)}: {len(gdf)} edificacoes", flush=True)
            osm_util.pausa()

        if not partes:
            raise RuntimeError("nenhum bloco de edificacoes foi baixado")

        todos = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=WGS84)
        todos = todos[~todos.geometry.duplicated()].reset_index(drop=True)
        todos.to_file(PREDIOS_GPKG, driver="GPKG", layer="predios")
        print(f"  total {len(todos)} edificacoes -> {PREDIOS_GPKG.name}")
    else:
        print(f"Edificacoes ja em cache ({PREDIOS_GPKG.name})")

    if forcar or not GRAFO_GRAPHML.exists():
        print(f"Malha viaria do municipio em {len(blocos)} blocos...", flush=True)
        grafos: list[nx.MultiDiGraph] = []
        for i, bbox in enumerate(blocos, 1):
            try:
                g = osm_util.com_retry(
                    lambda b=bbox: ox.graph_from_bbox(bbox=b, network_type="all",
                                                      simplify=False, retain_all=True),
                    rotulo=f"vias bloco {i}",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  bloco {i}/{len(blocos)}: sem vias ({type(exc).__name__})", flush=True)
                continue
            grafos.append(g)
            print(f"  bloco {i}/{len(blocos)}: {g.number_of_nodes()} nos", flush=True)
            osm_util.pausa()

        if not grafos:
            raise RuntimeError("nenhum bloco de vias foi baixado")

        # Ids de no/aresta sao os proprios ids do OSM, entao os blocos remendam sem conflito.
        G = nx.compose_all(grafos)
        G.graph["crs"] = grafos[0].graph.get("crs", WGS84)
        G = ox.simplification.simplify_graph(G)
        ox.io.save_graphml(G, GRAFO_GRAPHML)
        print(f"  total {G.number_of_nodes()} nos / {G.number_of_edges()} arestas -> {GRAFO_GRAPHML.name}")
    else:
        print(f"Malha viaria ja em cache ({GRAFO_GRAPHML.name})")


def predios_disponivel() -> bool:
    return PREDIOS_GPKG.exists()


def vias_disponivel() -> bool:
    return GRAFO_GRAPHML.exists()


def disponivel() -> bool:
    """Compatibilidade: ha cache utilizavel de edificacoes."""
    return predios_disponivel()


def predios() -> gpd.GeoDataFrame:
    global _predios
    if _predios is None:
        _predios = gpd.read_file(PREDIOS_GPKG, layer="predios").to_crs(WGS84)
        _predios.sindex  # constroi o indice espacial uma vez
    return _predios


def grafo() -> nx.MultiDiGraph:
    global _grafo
    if _grafo is None:
        _grafo = ox.io.load_graphml(GRAFO_GRAPHML)
    return _grafo


def recortar_predios(poligono) -> gpd.GeoDataFrame:
    todos = predios()
    candidatos = todos.iloc[list(todos.sindex.query(poligono, predicate="intersects"))]
    dentro = candidatos[candidatos.geometry.intersects(poligono)]
    return dentro.reset_index(drop=True)


def recortar_vias(poligono) -> nx.MultiDiGraph:
    return ox.truncate.truncate_graph_polygon(grafo(), poligono, truncate_by_edge=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--forcar", action="store_true")
    ap.add_argument("--blocos", type=int, default=4, help="grade N x N de consultas")
    args = ap.parse_args()
    construir(forcar=args.forcar, n_blocos=args.blocos)
