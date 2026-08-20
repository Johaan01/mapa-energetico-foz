"""Consumo medio REAL por unidade consumidora, da base SAMP da ANEEL.

Ate agora a amplitude das curvas vinha de um chute meu (0,012 kWh/h por m2). Este
modulo troca esse numero magico por um ancoramento real: o mercado declarado pela
COPEL-DIS a ANEEL, por classe de consumo, com energia faturada (kWh) e numero de
consumidores no mesmo recorte.

Limitacao honesta: o SAMP e por DISTRIBUIDORA, nao por municipio. O numero e o da area
de concessao da Copel inteira, aplicado a Foz do Iguacu. E o recorte mais fino que a
base publica permite.

    python consumo_real.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PARQUET = RAIZ / "data" / "aneel" / "samp-2025.parquet"
SAIDA = RAIZ / "web" / "data" / "consumo_real.json"

DISTRIBUIDORA = "COPEL-DIS"
CLASSES = ["Residencial", "Comercial", "Industrial", "Rural"]


# A energia faturada aparece como "Energia TE (kWh)" (identica a TUSD). NAO usar
# "Energia Consumida (kWh)": esse campo cobre so o subconjunto de compensacao de
# geracao distribuida e da 28 kWh/mes por residencia — implausivel. Com TE o numero
# fecha em 174 kWh/mes, coerente com a media residencial brasileira.
METRICA_ENERGIA = "Energia TE (kWh)"


def media_por_uc(df: pd.DataFrame, classe: str) -> dict | None:
    base = df[df["DscClasseConsumoMercado"] == classe]
    if base.empty:
        return None

    energia = base[base["DscDetalheMercado"] == METRICA_ENERGIA]
    consumidores = base[base["DscDetalheMercado"] == "Número de consumidores"]
    if energia.empty or consumidores.empty:
        return None

    # Soma por mes e depois tira a media dos meses: o numero de consumidores e um
    # estoque (nao se soma ao longo do ano), a energia e um fluxo.
    kwh_mes = energia.groupby("DatCompetencia")["VlrMercado"].sum()
    ucs_mes = consumidores.groupby("DatCompetencia")["VlrMercado"].sum()

    comum = kwh_mes.index.intersection(ucs_mes.index)
    if len(comum) == 0:
        return None

    media_mensal_por_uc = (kwh_mes[comum] / ucs_mes[comum]).mean()
    return {
        "classe": classe,
        "meses": len(comum),
        "ucs_medias": round(float(ucs_mes[comum].mean())),
        "kwh_mes_total_medio": round(float(kwh_mes[comum].mean())),
        "kwh_mes_por_uc": round(float(media_mensal_por_uc), 1),
        "kwh_dia_por_uc": round(float(media_mensal_por_uc) / 30.4, 2),
    }


def main() -> None:
    df = pd.read_parquet(PARQUET)
    df = df[df["SigAgenteDistribuidora"] == DISTRIBUIDORA]

    resultados = [r for c in CLASSES if (r := media_por_uc(df, c))]

    # Geracao distribuida real: quanto os prosumidores injetaram de fato na rede.
    res = df[df["DscClasseConsumoMercado"] == "Residencial"]
    injetada = res[res["DscDetalheMercado"] == "Energia Injetada (kWh)"]
    inj_mes = float(injetada.groupby("DatCompetencia")["VlrMercado"].sum().mean()) if not injetada.empty else 0.0

    dados = {
        "fonte": "ANEEL SAMP 2025 — mercado declarado pelas distribuidoras (Res. Normativa 1.003/2022)",
        "distribuidora": DISTRIBUIDORA,
        "metrica_energia": METRICA_ENERGIA,
        "ressalva": "Valores da area de concessao da Copel inteira; o SAMP nao tem recorte municipal.",
        "por_classe": resultados,
        "energia_injetada_residencial_kwh_mes": round(inj_mes),
    }

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'classe':12s} {'UCs':>10s} {'kWh/mes/UC':>12s} {'kWh/dia/UC':>12s}")
    for r in resultados:
        print(f"{r['classe']:12s} {r['ucs_medias']:10,d} {r['kwh_mes_por_uc']:12.1f} {r['kwh_dia_por_uc']:12.2f}")
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
