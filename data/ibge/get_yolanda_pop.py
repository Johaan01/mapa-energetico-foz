import openpyxl
from pathlib import Path

AQUI = Path(__file__).parent

wb = openpyxl.load_workbook(
    AQUI / "Populacao_residente_por_bairros_sexo_idade.xlsx",
    read_only=True,
    data_only=True,
)
ws = wb[wb.sheetnames[0]]

TARGET_CD_BAIRRO = 4108304026  # Yolanda, Foz do Iguacu (do shapefile de bairros)
TARGET_MUN = "Foz do Iguaçu"

rows = ws.iter_rows(values_only=True)
for _ in range(10):
    next(rows)

foz_rows = []
for row in rows:
    municipio = row[2]
    cod_bairro = row[5]
    if municipio == TARGET_MUN:
        foz_rows.append(row)
    if cod_bairro == TARGET_CD_BAIRRO:
        print("MATCH EXATO:")
        print(row[:8])

print(f"\nTotal de linhas de Foz do Iguacu encontradas: {len(foz_rows)}")
for r in foz_rows[:10]:
    print(r[:8])
