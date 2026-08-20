import geopandas as gpd

gdf = gpd.read_file(r"C:\Users\joao~\hackathon-transicao-energetica\data\ibge\PR_bairros\PR_bairros_CD2022.shp")

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
    yolanda.to_file(r"C:\Users\joao~\hackathon-transicao-energetica\data\ibge\vila_yolanda_boundary.geojson", driver="GeoJSON")
    print("Salvo: vila_yolanda_boundary.geojson")
