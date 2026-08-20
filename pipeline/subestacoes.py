"""Subestacoes REAIS, do OpenStreetMap (`power=substation`).

Ate aqui a subestacao de cada bairro era sintetica: o no da via de maior hierarquia
mais proximo do centro. Isso serve para desenhar uma arvore radial plausivel, mas a
posicao era arbitraria — e subestacao nao e arbitraria, ela existe num lugar especifico.

O OSM mapeia as de Foz do Iguacu, incluindo as de distribuicao da Copel (entre elas a
"Subestação Vila Yolanda"). Este modulo baixa uma vez, guarda em disco, e entrega a
subestacao real mais proxima de cada bairro.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import osmnx as ox

import cache_osm
import osm_util

CACHE = Path(__file__).resolve().parent.parent / "data" / "osm_cache"
ARQUIVO = CACHE / "subestacoes.geojson"
WGS84 = "EPSG:4326"
UTM_CRS = "EPSG:31982"

# Subestacoes de transmissao/conversao (Itaipu, Furnas) alimentam o sistema, nao o
# bairro. Para a rede de distribuicao interessam as de distribuicao.
PREFERIR = ("distribution",)

_cache: gpd.GeoDataFrame | None = None


def construir(forcar: bool = False) -> gpd.GeoDataFrame:
    if ARQUIVO.exists() and not forcar:
        return gpd.read_file(ARQUIVO)

    CACHE.mkdir(parents=True, exist_ok=True)
    osm_util.configurar()
    contorno = cache_osm.contorno_municipio()

    gdf = osm_util.com_retry(
        lambda: ox.features_from_polygon(contorno, tags={"power": ["substation"]}),
        rotulo="subestacoes",
    )

    colunas = {}
    for c in ("name", "operator", "voltage", "substation"):
        colunas[c] = gdf[c].astype(str) if c in gdf.columns else ""

    simples = gpd.GeoDataFrame(colunas, geometry=gdf.geometry.values, crs=gdf.crs).to_crs(WGS84)
    # Poligono ou ponto: o que interessa e a posicao.
    simples["geometry"] = simples.geometry.to_crs(UTM_CRS).centroid.to_crs(WGS84)
    simples = simples.reset_index(drop=True)

    if ARQUIVO.exists():
        ARQUIVO.unlink()
    simples.to_file(ARQUIVO, driver="GeoJSON")
    return simples


def todas() -> gpd.GeoDataFrame:
    global _cache
    if _cache is None:
        _cache = construir()
    return _cache


def mais_proxima(ponto_wgs84):
    """Subestacao real mais proxima. Prefere as de distribuicao; None se nao houver."""
    gdf = todas()
    if gdf.empty:
        return None

    dist = gdf[gdf["substation"].isin(PREFERIR)]
    candidatas = dist if not dist.empty else gdf

    alvo = gpd.GeoSeries([ponto_wgs84], crs=WGS84).to_crs(UTM_CRS).iloc[0]
    pontos = candidatas.geometry.to_crs(UTM_CRS)
    idx = pontos.distance(alvo).idxmin()

    linha = candidatas.loc[idx]
    return {
        "nome": linha["name"] if linha["name"] not in ("", "nan", "None") else "Subestação sem nome (OSM)",
        "operador": linha["operator"],
        "tensao": linha["voltage"],
        "geometry": linha.geometry,
        "distancia_m": round(float(pontos.loc[idx].distance(alvo)), 1),
    }


if __name__ == "__main__":
    gdf = construir(forcar=True)
    print(f"{len(gdf)} subestacoes mapeadas no OSM:\n")
    print(gdf.drop(columns="geometry").to_string())
