"""Exporta footprints de edificacoes do Google Open Buildings v3 para um bairro-alvo,
filtrados por confianca, area minima e altura, prontos para alimentar o
simulate_data.py (propriedade `area_in_meters` por feature).

Requer autenticacao previa do Earth Engine (uma vez, ja feita nesta maquina):
    python -c "import ee; ee.Authenticate(auth_mode='localhost')"

Uso (Vila Yolanda, ja calibrado como padrao):
    python export_bairro_buildings.py --output ..\..\simulation\input_buildings.geojson

Uso generico (outro bairro/cidade, buffer em torno de um ponto central):
    python export_bairro_buildings.py --lat -25.55 --lon -54.57 --radius-m 700 --output outro.geojson

Parametrizado (lat/lon/raio, filtros) para ficar repetivel por bairro/cidade mais
tarde. Hoje o padrao aponta pro centro aproximado da Vila Yolanda (Foz do Iguacu),
obtido via Nominatim/OSM - nao existe poligono oficial de bairro publico pra essa
area, so um ponto central. Ajuste --lat/--lon/--radius-m (ou troque build_aoi por um
poligono proprio) se tiver um recorte mais preciso.
"""
import argparse
import json
from pathlib import Path

import ee

GEE_PROJECT_ID = "testegee-479916"

# Centro aproximado da Vila Yolanda (Foz do Iguacu/PR), via Nominatim.
DEFAULT_LAT = -25.5520036
DEFAULT_LON = -54.5701875
DEFAULT_RADIUS_M = 700

OPEN_BUILDINGS_POLYGONS = "GOOGLE/Research/open-buildings/v3/polygons"
OPEN_BUILDINGS_HEIGHT = "GOOGLE/Research/open-buildings-temporal/v1"
HEIGHT_YEAR = 2023  # ano mais recente coberto pelo dataset temporal

MIN_CONFIDENCE = 0.70  # limiar recomendado pela documentacao do Open Buildings v3
MIN_AREA_M2 = 40.0     # exclui garagens/anexos/fragmentos de telhado
MAX_HEIGHT_M = 6.0     # exclui predios/sobrados altos (~1-2 pavimentos)


def initialize() -> None:
    ee.Initialize(project=GEE_PROJECT_ID)


def build_aoi(lat: float, lon: float, radius_m: float) -> ee.Geometry:
    return ee.Geometry.Point([lon, lat]).buffer(radius_m).bounds()


def build_aoi_from_geojson(path: Path) -> ee.Geometry:
    """AOI a partir de um poligono real (ex.: malha oficial de bairros do IBGE),
    em vez do box aproximado lat/lon/raio. Aceita Feature ou FeatureCollection;
    usa a primeira geometria encontrada."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geometry = data["features"][0]["geometry"]
    elif data.get("type") == "Feature":
        geometry = data["geometry"]
    else:
        geometry = data
    return ee.Geometry(geometry)


def height_image(year: int) -> ee.Image:
    return (
        ee.ImageCollection(OPEN_BUILDINGS_HEIGHT)
        .select("building_height")
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .mosaic()
    )


def fetch_buildings(aoi: ee.Geometry, min_confidence: float, min_area_m2: float, max_height_m: float) -> dict:
    raw = ee.FeatureCollection(OPEN_BUILDINGS_POLYGONS).filterBounds(aoi)
    print(f"  1) bruto (dentro do AOI):              {raw.size().getInfo()}")

    by_conf_area = raw.filter(
        ee.Filter.And(
            ee.Filter.gte("confidence", min_confidence),
            ee.Filter.gte("area_in_meters", min_area_m2),
        )
    )
    print(f"  2) apos confianca >= {min_confidence} e area >= {min_area_m2} m2: {by_conf_area.size().getInfo()}")

    # reduceRegions com o poligono inteiro retorna null para a maioria das edificacoes:
    # muitos footprints (< ~100 m2) sao menores ou comparaveis ao pixel de 4m da banda
    # de altura, entao nenhum centro de pixel cai dentro do poligono. Fix: amostrar no
    # centroide de cada edificacao em vez do poligono inteiro, depois juntar o valor de
    # volta ao poligono original via ee.Join (evitar filter() dentro de map(), que é
    # anti-padrao no Earth Engine e pode travar ou ficar extremamente lento).
    centroids = by_conf_area.map(lambda f: f.setGeometry(f.geometry().centroid(1)))

    with_height = height_image(HEIGHT_YEAR).reduceRegions(
        collection=centroids,
        reducer=ee.Reducer.first().setOutputs(["building_height"]),
        scale=4,
    )

    join_filter = ee.Filter.equals(leftField="system:index", rightField="system:index")
    joined = ee.Join.saveFirst("height_match").apply(by_conf_area, with_height, join_filter)

    with_height_prop = joined.map(
        lambda f: f.set("building_height", ee.Feature(f.get("height_match")).get("building_height"))
    )

    final = with_height_prop.filter(ee.Filter.lte("building_height", max_height_m))
    print(f"  3) apos altura media <= {max_height_m} m:          {final.size().getInfo()}")

    return final.getInfo()


def to_simple_geojson(fc: dict) -> dict:
    features = []
    for feat in fc.get("features", []):
        props = feat.get("properties", {})
        features.append({
            "type": "Feature",
            "properties": {
                "id": feat.get("id"),
                "area_in_meters": props.get("area_in_meters"),
                "confidence": props.get("confidence"),
                "height_m": props.get("building_height"),
            },
            "geometry": feat.get("geometry"),
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--radius-m", type=float, default=DEFAULT_RADIUS_M)
    parser.add_argument("--aoi-geojson", type=Path, default=None,
                         help="Poligono real do bairro (ex.: malha oficial de bairros do IBGE). "
                              "Se informado, substitui --lat/--lon/--radius-m.")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    parser.add_argument("--min-area-m2", type=float, default=MIN_AREA_M2)
    parser.add_argument("--max-height-m", type=float, default=MAX_HEIGHT_M)
    parser.add_argument("--output", type=Path, default=Path("input_buildings.geojson"))
    args = parser.parse_args()

    initialize()
    if args.aoi_geojson:
        aoi = build_aoi_from_geojson(args.aoi_geojson)
    else:
        aoi = build_aoi(args.lat, args.lon, args.radius_m)

    print("Filtrando edificacoes...")
    raw = fetch_buildings(aoi, args.min_confidence, args.min_area_m2, args.max_height_m)
    geojson = to_simple_geojson(raw)

    args.output.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
    print(f"\nEdificacoes exportadas: {len(geojson['features'])}")
    print(f"Gerado: {args.output}")


if __name__ == "__main__":
    main()
