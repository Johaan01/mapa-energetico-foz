"""Exporta footprints de edificacoes hibrido: geometria REAL do OpenStreetMap (via
osmnx - contorno fiel da casa, sem a fragmentacao que o Open Buildings v3 as vezes
gera) + altura via Open Buildings 2.5D Temporal (Earth Engine, unica fonte com
cobertura de altura utilizavel nessa cidade). area_in_meters e calculada direto da
geometria do OSM (reprojetada pra UTM). Saida no mesmo formato que o
export_bairro_buildings.py, pronta pro simulate_data.py.

Requer autenticacao previa do Earth Engine (ja feita nesta maquina).

Uso (Vila Yolanda, poligono oficial do IBGE ja baixado):
    python export_bairro_buildings_osm.py --aoi-geojson ..\ibge\vila_yolanda_boundary.geojson --output ..\..\simulation\input_buildings.geojson
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ee
import geopandas as gpd
import osmnx as ox

GEE_PROJECT_ID = "testegee-479916"
UTM_CRS = "EPSG:31982"  # SIRGAS 2000 / UTM 22S, cobre Foz do Iguacu

OPEN_BUILDINGS_HEIGHT = "GOOGLE/Research/open-buildings-temporal/v1"
HEIGHT_YEAR = 2023

MIN_AREA_M2 = 40.0
# 6m parecia razoavel de saida ("1-2 pavimentos"), mas a distribuicao real medida em
# Vila Yolanda (debug_osm_heights.py) tem mediana 5,34m - um limite de 6m cortava perto
# da metade das casas legitimas de 1-2 pavimentos por variacao normal de altura de
# telhado + ruido do proprio raster (erro medio conhecido de ~1,5m). 8m exclui os
# predios claramente multi-pavimento (percentil 88,7) sem penalizar casas comuns.
MAX_HEIGHT_M = 8.0
HEIGHT_BATCH_SIZE = 500


def initialize() -> None:
    ee.Initialize(project=GEE_PROJECT_ID)


def fetch_osm_buildings(aoi_polygon, min_area_m2: float) -> gpd.GeoDataFrame:
    gdf = ox.features_from_polygon(aoi_polygon, tags={"building": True})
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()

    gdf["area_in_meters"] = gdf.geometry.to_crs(UTM_CRS).area
    gdf = gdf[gdf["area_in_meters"] >= min_area_m2].copy()

    gdf = gdf.reset_index(drop=True)
    gdf["building_id"] = gdf.index.astype(str)
    return gdf[["building_id", "area_in_meters", "geometry"]]


def height_image(year: int) -> ee.Image:
    return (
        ee.ImageCollection(OPEN_BUILDINGS_HEIGHT)
        .select("building_height")
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .mosaic()
    )


def join_height(gdf: gpd.GeoDataFrame, batch_size: int) -> gpd.GeoDataFrame:
    centroids = gdf.geometry.centroid  # OSM ja vem em EPSG:4326 (lon/lat)
    img = height_image(HEIGHT_YEAR)

    heights: list[float | None] = [None] * len(gdf)
    for start in range(0, len(gdf), batch_size):
        end = min(start + batch_size, len(gdf))
        features = [
            ee.Feature(ee.Geometry.Point([centroids.iloc[i].x, centroids.iloc[i].y]), {"idx": i})
            for i in range(start, end)
        ]
        fc = ee.FeatureCollection(features)
        result = img.reduceRegions(
            collection=fc,
            reducer=ee.Reducer.first().setOutputs(["building_height"]),
            scale=4,
        ).getInfo()
        for feat in result["features"]:
            idx = feat["properties"]["idx"]
            heights[idx] = feat["properties"].get("building_height")
        print(f"  altura: {end}/{len(gdf)} processados")

    gdf = gdf.copy()
    gdf["height_m"] = heights
    return gdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi-geojson", type=Path, required=True)
    parser.add_argument("--min-area-m2", type=float, default=MIN_AREA_M2)
    parser.add_argument("--max-height-m", type=float, default=MAX_HEIGHT_M)
    parser.add_argument("--output", type=Path, default=Path("input_buildings.geojson"))
    args = parser.parse_args()

    initialize()

    aoi_gdf = gpd.read_file(args.aoi_geojson)
    aoi_polygon = aoi_gdf.geometry.iloc[0]

    print("Baixando geometria real do OSM...")
    gdf = fetch_osm_buildings(aoi_polygon, args.min_area_m2)
    print(f"  apos area >= {args.min_area_m2} m2: {len(gdf)}")

    print("Juntando altura via Earth Engine (Open Buildings 2.5D Temporal)...")
    gdf = join_height(gdf, HEIGHT_BATCH_SIZE)

    n_sem_altura = gdf["height_m"].isna().sum()
    if n_sem_altura:
        print(f"  aviso: {n_sem_altura} sem dado de altura (assumidos como baixos, mantidos)")
    gdf["height_m"] = gdf["height_m"].fillna(0.0)

    final = gdf[gdf["height_m"] <= args.max_height_m].copy()
    print(f"  apos altura <= {args.max_height_m} m: {len(final)}")

    geojson = json.loads(final.to_json())
    args.output.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")

    print(f"\nEdificacoes exportadas: {len(geojson['features'])}")
    print(f"Gerado: {args.output}")


if __name__ == "__main__":
    main()
