"""Exploracao pontual do CSV nacional da ANEEL para validar granularidade real dos dados
antes de decidir a estrategia de calibracao do simulador. Nao faz parte do pipeline final.
"""
import csv
from collections import Counter
from pathlib import Path

CSV_PATH = Path(__file__).parent / "empreendimento-geracao-distribuida.csv"
TARGET_MUNICIPIOS = {"Foz do Iguaçu", "Cascavel"}
TARGET_UF = "PR"

classe_counter = Counter()
municipio_counter = Counter()
sub_coord_nonempty = 0
sub_coord_total = 0
total_rows = 0
pr_target_rows = []

with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        total_rows += 1

        sub_coord_total += 1
        if row.get("NumCoordESub", "").strip() or row.get("NumCoordNSub", "").strip():
            sub_coord_nonempty += 1

        if row.get("SigTipoGeracao") != "UFV":
            continue

        uf = row.get("SigUF")
        municipio = row.get("NomMunicipio")

        if uf == TARGET_UF and municipio in TARGET_MUNICIPIOS:
            classe_counter[(municipio, row.get("DscClasseConsumo"))] += 1
            municipio_counter[municipio] += 1
            if len(pr_target_rows) < 5:
                pr_target_rows.append(row)

        if total_rows % 500_000 == 0:
            print(f"...{total_rows:,} linhas processadas")

print(f"\nTotal de linhas no arquivo: {total_rows:,}")
print(f"Linhas com NumCoordESub/NumCoordNSub preenchidos: {sub_coord_nonempty:,} de {sub_coord_total:,}")

print("\nContagem UFV por (municipio, classe de consumo) - PR:")
for (municipio, classe), count in sorted(classe_counter.items()):
    print(f"  {municipio:20s} | {classe:15s} | {count}")

print("\nTotal UFV por municipio:")
for municipio, count in municipio_counter.items():
    print(f"  {municipio}: {count}")

print("\nAmostra de linhas (Foz do Iguacu / Cascavel, UFV):")
for row in pr_target_rows:
    print({k: row[k] for k in ["NomMunicipio", "DscClasseConsumo", "SigTipoConsumidor", "MdaPotenciaInstaladaKW", "CodCEP", "NumCoordESub", "NumCoordNSub"]})
