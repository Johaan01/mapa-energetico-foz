import openpyxl

wb = openpyxl.load_workbook(
    r"C:\Users\joao~\hackathon-transicao-energetica\data\ibge\Populacao_residente_por_bairros_sexo_idade.xlsx",
    read_only=True,
    data_only=True,
)
ws = wb[wb.sheetnames[0]]

rows = ws.iter_rows(values_only=True)
for i, row in enumerate(rows):
    print(i, row[:10])
    if i >= 12:
        break
