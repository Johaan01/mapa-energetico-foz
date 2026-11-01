import openpyxl
from pathlib import Path

AQUI = Path(__file__).parent

wb = openpyxl.load_workbook(
    AQUI / "Populacao_residente_por_bairros_sexo_idade.xlsx",
    read_only=True,
    data_only=True,
)
ws = wb[wb.sheetnames[0]]

rows = ws.iter_rows(values_only=True)
for i, row in enumerate(rows):
    print(i, row[:10])
    if i >= 12:
        break
