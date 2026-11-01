"""Define a 'regiao' do zoom macro como a UNIAO dos bairros oficiais do IBGE que
compartilham a zona de CEP 85853 (achado via amostragem no ViaCEP), em vez de um
unico bairro administrativo. Isso alinha a geografia do denominador (populacao real
via IBGE) com a geografia do numerador (registros reais da ANEEL, que sao por CEP,
nao por bairro).
"""
import geopandas as gpd
import openpyxl
from pathlib import Path

AQUI = Path(__file__).parent

BAIRROS_NA_ZONA_CEP_85853 = ["Yolanda", "São Roque", "Bourbon", "Remanso", "Mata Verde", "Cataratas"]
HAB_POR_DOMICILIO_FOZ = 2.82
REGISTROS_ANEEL_ZONA_85853 = 1364

# --- Populacao real por bairro (Censo 2022) ---
wb = openpyxl.load_workbook(
    AQUI / "Populacao_residente_por_bairros_sexo_idade.xlsx",
    read_only=True, data_only=True,
)
ws = wb[wb.sheetnames[0]]
rows = ws.iter_rows(values_only=True)
for _ in range(10):
    next(rows)

pop_por_bairro = {}
for row in rows:
    municipio, nome_bairro, total = row[2], row[4], row[6]
    if municipio == "Foz do Iguaçu" and nome_bairro in BAIRROS_NA_ZONA_CEP_85853:
        pop_por_bairro[nome_bairro] = total

# --- Poligono/area real por bairro (malha IBGE) ---
gdf = gpd.read_file(AQUI / "PR_bairros" / "PR_bairros_CD2022.shp")
foz = gdf[(gdf["NM_MUN"] == "Foz do Iguaçu") & (gdf["NM_BAIRRO"].isin(BAIRROS_NA_ZONA_CEP_85853))]

print(f"{'Bairro':15s} {'Populacao':>10s} {'Area km2':>10s}")
pop_total = 0
for _, row in foz.iterrows():
    nome = row["NM_BAIRRO"]
    pop = pop_por_bairro.get(nome, 0)
    area_km2 = gpd.GeoSeries([row.geometry], crs=gdf.crs).to_crs(31982).area.iloc[0] / 1e6
    pop_total += pop
    print(f"{nome:15s} {pop:10d} {area_km2:10.3f}")

regiao = foz.dissolve()
area_total_km2 = regiao.to_crs(31982).geometry.area.iloc[0] / 1e6
domicilios_estimados = pop_total / HAB_POR_DOMICILIO_FOZ

print(f"\nPopulacao total da regiao (6 bairros): {pop_total}")
print(f"Area total da regiao: {area_total_km2:.3f} km2")
print(f"Domicilios estimados (pop / {HAB_POR_DOMICILIO_FOZ}): {domicilios_estimados:.0f}")
print(f"Registros ANEEL reais na zona 85853: {REGISTROS_ANEEL_ZONA_85853}")
print(f"Taxa de adesao da REGIAO (numerador e denominador da mesma geografia): {REGISTROS_ANEEL_ZONA_85853 / domicilios_estimados * 100:.1f}%")

regiao.to_file(AQUI / "regiao_cep_85853.geojson", driver="GeoJSON")
print("\nSalvo: regiao_cep_85853.geojson")
