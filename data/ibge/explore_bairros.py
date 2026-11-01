"""Explora o shapefile oficial de bairros do IBGE (Censo 2022) para o Parana,
procurando Foz do Iguacu / Vila Yolanda, e verifica quais atributos (populacao,
domicilios) vem junto.
"""
import geopandas as gpd
from pathlib import Path

AQUI = Path(__file__).parent

gdf = gpd.read_file(AQUI / "PR_bairros" / "PR_bairros_CD2022.shp")

print("Colunas:", list(gdf.columns))
print("Total de bairros no PR:", len(gdf))
print("CRS:", gdf.crs)
print()
print(gdf.head(3).drop(columns="geometry"))

# Tenta achar colunas de municipio e nome do bairro
possible_name_cols = [c for c in gdf.columns if "NM" in c.upper() or "NOME" in c.upper()]
print("\nColunas candidatas a nome:", possible_name_cols)

for col in possible_name_cols:
    matches = gdf[gdf[col].astype(str).str.contains("Iguaçu", case=False, na=False)]
    if len(matches):
        print(f"\nLinhas onde {col} contem 'Iguaçu': {len(matches)}")
