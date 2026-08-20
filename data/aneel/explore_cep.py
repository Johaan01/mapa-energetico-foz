"""Segunda exploracao: distribuicao de prefixos de CEP (5 digitos visiveis, os ultimos 3 sao
mascarados pela ANEEL por privacidade) para instalacoes residenciais UFV em Foz do Iguacu e
Cascavel. Objetivo: ver se ha concentracao geografica clara o suficiente para escolher um
bairro-alvo de forma orientada a dado, em vez de por inspecao visual apenas.
"""
import csv
from collections import Counter
from pathlib import Path

CSV_PATH = Path(__file__).parent / "empreendimento-geracao-distribuida.csv"
TARGET_UF = "PR"
TARGET_MUNICIPIOS = {"Foz do Iguaçu", "Cascavel"}

cep_counter = {m: Counter() for m in TARGET_MUNICIPIOS}
potencia_sum = {m: 0.0 for m in TARGET_MUNICIPIOS}
potencia_n = {m: 0 for m in TARGET_MUNICIPIOS}

with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        if row.get("SigTipoGeracao") != "UFV":
            continue
        if row.get("SigUF") != TARGET_UF:
            continue
        municipio = row.get("NomMunicipio")
        if municipio not in TARGET_MUNICIPIOS:
            continue
        if row.get("DscClasseConsumo") != "Residencial":
            continue

        cep = row.get("CodCEP", "").strip()
        cep_prefix = cep[:5] if len(cep) >= 5 else cep
        cep_counter[municipio][cep_prefix] += 1

        pot_raw = row.get("MdaPotenciaInstaladaKW", "").replace(",", ".")
        try:
            potencia_sum[municipio] += float(pot_raw)
            potencia_n[municipio] += 1
        except ValueError:
            pass

for municipio in TARGET_MUNICIPIOS:
    print(f"\n=== {municipio} ===")
    print(f"Potencia media instalada: {potencia_sum[municipio] / max(potencia_n[municipio], 1):.2f} kW (n={potencia_n[municipio]})")
    print("Top 15 prefixos de CEP (residencial, UFV):")
    for cep_prefix, count in cep_counter[municipio].most_common(15):
        print(f"  {cep_prefix}xx-xxx : {count}")
    print(f"Total de prefixos distintos: {len(cep_counter[municipio])}")
