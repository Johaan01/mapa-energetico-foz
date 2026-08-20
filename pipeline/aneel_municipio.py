"""Estatisticas REAIS de geracao distribuida da ANEEL para o municipio.

Nivel municipal de proposito: o CEP nos registros vem com os 3 ultimos digitos
mascarados, entao qualquer recorte menor que o municipio carrega ambiguidade (a zona
85853, por exemplo, cobre 6 bairros oficiais). O municipio e o menor recorte em que
numerador e denominador batem sem ressalva.

    python aneel_municipio.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSV_PATH = RAIZ / "data" / "aneel" / "empreendimento-geracao-distribuida.csv"
SAIDA = RAIZ / "web" / "data" / "municipio.json"

MUNICIPIO = "Foz do Iguaçu"
UF = "PR"
POPULACAO_CENSO2022 = 285_415
HAB_POR_DOMICILIO = 2.82


def main() -> None:
    por_classe = Counter()
    potencia_por_classe = Counter()
    por_ano = Counter()
    potencia_residencial = 0.0
    n_residencial = 0

    with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row.get("SigUF") != UF or row.get("NomMunicipio") != MUNICIPIO:
                continue
            if row.get("SigTipoGeracao") != "UFV":
                continue

            classe = row.get("DscClasseConsumo", "?")
            por_classe[classe] += 1

            try:
                pot = float(row.get("MdaPotenciaInstaladaKW", "0").replace(",", "."))
            except ValueError:
                pot = 0.0
            potencia_por_classe[classe] += pot

            if classe == "Residencial":
                n_residencial += 1
                potencia_residencial += pot
                ano = (row.get("DthAtualizaCadastralEmpreend") or "")[:4]
                if ano.isdigit():
                    por_ano[ano] += 1

    domicilios = round(POPULACAO_CENSO2022 / HAB_POR_DOMICILIO)
    dados = {
        "municipio": MUNICIPIO,
        "uf": UF,
        "fonte": "ANEEL — dadosabertos.aneel.gov.br, empreendimento-geracao-distribuida",
        "populacao_censo2022": POPULACAO_CENSO2022,
        "domicilios_estimados": domicilios,
        "ufv_total": int(sum(por_classe.values())),
        "ufv_residencial": n_residencial,
        "potencia_residencial_mw": round(potencia_residencial / 1000, 2),
        "potencia_media_residencial_kw": round(potencia_residencial / max(n_residencial, 1), 2),
        "taxa_adesao_residencial": round(n_residencial / domicilios, 4),
        "ufv_por_classe": dict(por_classe.most_common()),
        "ufv_residencial_por_ano": dict(sorted(por_ano.items())),
    }

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dados, ensure_ascii=False, indent=2)[:900])
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
