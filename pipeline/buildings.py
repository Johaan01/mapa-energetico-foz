"""Footprints reais de edificacoes por bairro.

Fonte da geometria: OpenStreetMap (osmnx). Escolhido no lugar do Google Open Buildings
v3 porque, na comparacao feita para Vila Yolanda, o OSM tem contorno fiel ao imovel e
zero fragmentacao (o Open Buildings as vezes quebra uma casa em 2+ poligonos).

Altura: banda `building_height` do Open Buildings 2.5D Temporal (Earth Engine), baixada
UMA vez por bairro como raster e amostrada localmente (1 request por bairro em vez de
um request a cada 500 imoveis).

IMPORTANTE - altura e ATRIBUTO, nunca filtro. Uma versao anterior deste pipeline
descartava imoveis com altura > 8m, o que apagava do mapa ~290 das 1.788 construcoes
reais de Vila Yolanda: o raster tem 4m de resolucao e ~1,5m de erro medio, entao o
corte eliminava casas comuns junto com predios. Agora a altura vira numero de
pavimentos e MULTIPLICA a area util (predio de 3 andares = ~3x domicilios), que e o
comportamento fisicamente correto.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import requests

import cache_osm
import osm_util

UTM_CRS = "EPSG:31982"  # SIRGAS 2000 / UTM 22S
WGS84 = "EPSG:4326"

OPEN_BUILDINGS_HEIGHT = "GOOGLE/Research/open-buildings-temporal/v1"
HEIGHT_YEAR = 2023
ALTURA_PAVIMENTO_M = 3.0

# Estruturas menores que isso sao quase sempre garagem, edicula, telheiro ou galpao
# pequeno: continuam DESENHADAS no mapa (a realidade e essa), mas nao recebem curva
# de carga propria - senao inflariamos a contagem de unidades consumidoras.
AREA_MIN_DOMICILIO_M2 = 40.0


def carregar_osm(poligono, area_min_desenho_m2: float = 12.0) -> gpd.GeoDataFrame:
    """Todas as edificacoes do OSM dentro do poligono do bairro.

    Usa o cache do municipio quando existir (recorte local, sem rede); so consulta a
    Overpass direto como fallback.
    """
    if cache_osm.predios_disponivel():
        gdf = cache_osm.recortar_predios(poligono)
    else:
        osm_util.configurar()
        gdf = osm_util.com_retry(
            lambda: ox.features_from_polygon(poligono, tags={"building": True}),
            rotulo="footprints",
        )
        gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
        gdf = gdf.to_crs(WGS84)

    gdf["area_m2"] = gdf.geometry.to_crs(UTM_CRS).area
    gdf = gdf[gdf["area_m2"] >= area_min_desenho_m2].copy()

    tipo_osm = gdf["building"] if "building" in gdf.columns else "yes"
    gdf = gpd.GeoDataFrame(
        {
            "area_m2": gdf["area_m2"].round(1).values,
            "tipo_osm": np.asarray(tipo_osm, dtype=object),
            "geometry": gdf.geometry.values,
        },
        crs=WGS84,
    )
    gdf = gdf.reset_index(drop=True)
    gdf.insert(0, "building_id", gdf.index.astype(str))
    return gdf


def _raster_altura(regiao_geojson: dict) -> tuple[np.ndarray, object] | None:
    """Baixa o raster de altura da regiao do Earth Engine. None se indisponivel."""
    try:
        import ee
        from rasterio.io import MemoryFile
    except ImportError:
        return None

    img = (
        ee.ImageCollection(OPEN_BUILDINGS_HEIGHT)
        .select("building_height")
        .filter(ee.Filter.calendarRange(HEIGHT_YEAR, HEIGHT_YEAR, "year"))
        .mosaic()
    )
    regiao = ee.Geometry(regiao_geojson)
    url = img.getDownloadURL(
        {"region": regiao, "scale": 4, "crs": WGS84, "format": "GEO_TIFF"}
    )
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()

    payload = resp.content
    if payload[:2] == b"PK":  # as vezes vem zipado
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            nome = next(n for n in zf.namelist() if n.endswith((".tif", ".tiff")))
            payload = zf.read(nome)

    with MemoryFile(payload) as mem, mem.open() as src:
        return src.read(1), src.transform


def anexar_altura(gdf: gpd.GeoDataFrame, poligono) -> gpd.GeoDataFrame:
    """Adiciona altura_m, pavimentos e area_util_m2.

    A regiao do raster e o envelope das EDIFICACOES, nao do bairro: em recortes como
    Parque Nacional o poligono e enorme e quase vazio, e pedir o raster inteiro
    estouraria o limite de download do Earth Engine sem nenhum ganho.
    """
    altura = np.full(len(gdf), np.nan)

    from shapely.geometry import box
    minx, miny, maxx, maxy = gdf.total_bounds
    margem = 0.0005  # ~50 m
    envelope = box(minx - margem, miny - margem, maxx + margem, maxy + margem)

    raster = _raster_altura(envelope.__geo_interface__)
    if raster is not None:
        banda, transform = raster
        centroides = gdf.geometry.to_crs(UTM_CRS).centroid.to_crs(WGS84)
        inv = ~transform
        h, w = banda.shape
        for i, pt in enumerate(centroides):
            col, lin = inv * (pt.x, pt.y)
            col, lin = int(col), int(lin)
            if 0 <= lin < h and 0 <= col < w:
                valor = banda[lin, col]
                if np.isfinite(valor) and valor > 0:
                    altura[i] = float(valor)

    gdf = gdf.copy()
    gdf["altura_m"] = np.round(altura, 2)

    pavimentos = np.ones(len(gdf), dtype=int)
    conhecida = np.isfinite(altura)
    pavimentos[conhecida] = np.clip(
        np.round(altura[conhecida] / ALTURA_PAVIMENTO_M), 1, 40
    ).astype(int)
    gdf["pavimentos"] = pavimentos

    gdf["e_domicilio"] = gdf["area_m2"] >= AREA_MIN_DOMICILIO_M2
    gdf["area_util_m2"] = (gdf["area_m2"] * gdf["pavimentos"]).round(1)
    return gdf


def carregar(poligono, com_altura: bool = True) -> gpd.GeoDataFrame:
    gdf = carregar_osm(poligono)
    if com_altura:
        try:
            gdf = anexar_altura(gdf, poligono)
            return gdf
        except Exception as exc:  # noqa: BLE001 - altura e opcional, nao pode derrubar o pipeline
            print(f"    aviso: altura indisponivel ({type(exc).__name__}: {exc}); assumindo 1 pavimento")

    gdf = gdf.copy()
    gdf["altura_m"] = np.nan
    gdf["pavimentos"] = 1
    gdf["e_domicilio"] = gdf["area_m2"] >= AREA_MIN_DOMICILIO_M2
    gdf["area_util_m2"] = gdf["area_m2"]
    return gdf
