"""Curvas de carga REAIS medidas, da base CTR da ANEEL.

O CTR guarda as curvas de demanda dos "consumidores tipo" levantadas em campanhas de
medicao das proprias distribuidoras — as mesmas que a ANEEL usa para calcular estrutura
tarifaria. Ou seja: medicao de campo, em intervalos de 15 minutos, por subgrupo
tarifario e por tipo de dia.

Isso substitui o formato ate entao inventado das curvas (somas de gaussianas). O que
importa: nao e so mais preciso, e mais RICO — a Copel tem 8 perfis distintos de
consumidor B1, com formatos diferentes entre si. Antes toda residencia tinha a mesma
silhueta e variava so na amplitude; agora ha heterogeneidade medida.

Saida: web/data/curvas_tipo.json, com cada perfil normalizado para media 1,0 — a
amplitude continua vindo da calibracao de consumo (SAMP), este modulo define o FORMATO.

    python curvas_reais.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PARQUET = RAIZ / "data" / "aneel" / "ctr-curvas-carga-consumidor-tipo.parquet"
SAIDA = RAIZ / "web" / "data" / "curvas_tipo.json"

DISTRIBUIDORA = "COPEL"
# B1 = residencial, B3 = comercial/demais classes (a classe comercial de baixa tensao).
SUBGRUPOS = {"residencial": "B1", "comercial": "B3"}
TIPO_DIA = "Dia Útil"


def _hora_do_intervalo(serie: pd.Series) -> pd.Series:
    """'HH:MM:SS' (ou time) -> hora inteira 0..23."""
    if np.issubdtype(serie.dtype, np.datetime64):
        return serie.dt.hour
    return serie.astype(str).str.slice(0, 2).astype(int)


def extrair(df: pd.DataFrame, subgrupo: str, ano: int) -> dict[str, list[float]]:
    d = df[
        (df["SigCcs"] == DISTRIBUIDORA)
        & (df["NomSubGrupoTarifario"] == subgrupo)
        & (df["AnoPrcCal"] == ano)
        & (df["DscTipoDia"] == TIPO_DIA)
    ].copy()
    if d.empty:
        return {}

    d["hora"] = _hora_do_intervalo(d["HorInicial"])

    perfis: dict[str, list[float]] = {}
    for ct, grupo in d.groupby("DscDemandante"):
        # 4 medidas de 15 min por hora -> media horaria
        por_hora = grupo.groupby("hora")["VlrDmd"].mean().reindex(range(24))
        if por_hora.isna().any() or por_hora.sum() <= 0:
            continue
        # Normaliza para media 1,0: guardamos o FORMATO, nao o nivel.
        perfis[str(ct)] = [round(float(v), 5) for v in (por_hora / por_hora.mean())]

    return perfis


def main() -> None:
    df = pd.read_parquet(PARQUET)
    ano = int(df[df["SigCcs"] == DISTRIBUIDORA]["AnoPrcCal"].max())

    dados = {
        "fonte": "ANEEL CTR — curvas de carga de consumidores tipo (campanhas de medição das distribuidoras)",
        "distribuidora": DISTRIBUIDORA,
        "ano_processo": ano,
        "tipo_dia": TIPO_DIA,
        "resolucao_original": "15 minutos (agregado para hora nesta saída)",
        "normalizacao": "cada curva tem média 1,0 — define o formato; a amplitude vem da calibração SAMP",
        "perfis": {},
    }

    for rotulo, subgrupo in SUBGRUPOS.items():
        perfis = extrair(df, subgrupo, ano)
        dados["perfis"][rotulo] = {"subgrupo": subgrupo, "curvas": perfis}
        print(f"{rotulo:12s} ({subgrupo}): {len(perfis)} perfis medidos")
        for ct, curva in list(perfis.items())[:3]:
            pico = int(np.argmax(curva))
            print(f"    {ct}: pico as {pico:02d}h  (min {min(curva):.2f} / max {max(curva):.2f})")

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {SAIDA} ({SAIDA.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
