import openpyxl
from pathlib import Path

AQUI = Path(__file__).parent

wb = openpyxl.load_workbook(
    AQUI / "Populacao_residente_por_bairros_sexo_idade.xlsx",
    read_only=True,
    data_only=True,
)
print("Abas:", wb.sheetnames)
ws = wb[wb.sheetnames[0]]

rows = ws.iter_rows(values_only=True)
header_rows = []
for i, row in enumerate(rows):
    header_rows.append(row)
    if i >= 8:
        break

for i, row in enumerate(header_rows):
    print(i, row[:8])
