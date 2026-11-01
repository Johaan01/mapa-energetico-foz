import geopandas as gpd
from pathlib import Path

AQUI = Path(__file__).parent

gdf = gpd.read_file(AQUI / "PR_bairros" / "PR_bairros_CD2022.shp")

foz = gdf[gdf["NM_MUN"] == "Foz do Iguaçu"]
print("Bairros em Foz do Iguacu:", len(foz))
print(sorted(foz["NM_BAIRRO"].tolist()))

yolanda = foz[foz["NM_BAIRRO"].str.contains("Yolanda", case=False, na=False)]
print("\nMatches 'Yolanda':", len(yolanda))
if len(yolanda):
    row = yolanda.iloc[0]
    print(row.drop("geometry"))
    # area em km2 (reprojeta pra CRS metrico local, UTM 22S = EPSG:31982 cobre Foz do Iguacu)
    area_km2 = yolanda.to_crs(31982).geometry.area.iloc[0] / 1e6
    print(f"\nArea do poligono: {area_km2:.4f} km2")
    yolanda.to_file(AQUI / "vila_yolanda_boundary.geojson", driver="GeoJSON")
    print("Salvo: vila_yolanda_boundary.geojson")
