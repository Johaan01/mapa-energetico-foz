"""Tarifas homologadas REAIS da Copel para baixa tensao residencial (B1).

Fonte: ANEEL, "Componentes Tarifarias" — quebra da TUSD e da TE por componente,
resultante do processo de reajuste (REH 3.592/2026, vigencia a partir de 24/06/2026).

Por que a quebra por componente importa: a Lei 14.300 nao cobra do prosumidor a TUSD
inteira sobre a energia injetada, e sim a parcela **Fio B** (que remunera a rede), num
percentual que sobe 15 p.p. ao ano — 60% em 2026.

CUIDADO com a subclasse: B1 tem varias (Baixa Renda, Tarifa Social, Desconto Social...)
com tarifas diferentes. A residencial "cheia" e `DscSubClasseConsumidor == 'Residencial'`
(TUSD 457,17); filtrar so por classe pega Baixa Renda (TUSD 308,43) e subestima a conta.

    python tarifas_copel.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PARQUET = RAIZ / "data" / "aneel" / "componentes-tarifarias-2026.parquet"
SAIDA = RAIZ / "web" / "data" / "tarifas.json"

AGENTE = "COPEL-DIS"
SUBGRUPO = "B1"
SUBCLASSE = "Residencial"          # a "cheia" — ver aviso no docstring
BASE = "Tarifa de Aplicação"

# Lei 14.300/2022, art. 27: percentual do Fio B cobrado sobre a energia INJETADA.
# 2023: 15% · 2024: 30% · 2025: 45% · 2026: 60% · 2027: 75% · 2028: 90%.
# O autoconsumo simultaneo (gerou e usou na hora) nao paga nada disso.
FIO_B_PERCENTUAL = {2023: 0.15, 2024: 0.30, 2025: 0.45, 2026: 0.60, 2027: 0.75, 2028: 0.90}
ANO_VIGENTE = 2026

# Referencia para a comparacao ano a ano do modelo de receita.
DATA_ANO_PASSADO = (date.today() - timedelta(days=365)).isoformat()

# Tributos sobre a tarifa. Aproximacao declarada: o calculo real e "por dentro",
# varia com faixa de consumo e com a bandeira do mes.
# ICMS: apos a LC 194/2022 a energia eletrica virou bem essencial e a aliquota caiu
# para a faixa de 17-20% (antes chegava a 29% no PR). Usamos 19%.
ICMS_PR = 0.19
PIS_COFINS = 0.0925


def _valor(d: pd.DataFrame, componente: str, posto: str, detalhe: str) -> float:
    linha = d[(d["DscComponenteTarifario"] == componente)
              & (d["DscPostoTarifario"] == posto)
              & (d["DscDetalheConsumidor"] == detalhe)]
    return round(float(linha["VlrComponenteTarifario"].iloc[0]), 4) if len(linha) else 0.0


def _vigencia_anterior() -> dict:
    """Tarifa da mesma distribuidora um ano antes, do CSV historico ja baixado.

    O modelo de receita do produto compara a conta com a do MESMO MES DO ANO ANTERIOR.
    Parte da diferenca vem de mudanca de habito e parte vem do reajuste tarifario —
    e so da para separar as duas se soubermos a tarifa antiga. Este e o dado real dela.
    """
    csv_local = RAIZ / "data" / "aneel" / "tarifas-homologadas.csv"
    if not csv_local.exists():
        return {}

    import csv as _csv
    melhor: dict | None = None
    with csv_local.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for linha in _csv.DictReader(f, delimiter=";"):
            if (linha.get("SigAgente") != AGENTE
                    or linha.get("DscSubGrupo") != SUBGRUPO
                    or linha.get("DscSubClasse") != SUBCLASSE
                    or linha.get("DscModalidadeTarifaria") != "Convencional"
                    or linha.get("DscBaseTarifaria") != BASE
                    or linha.get("DscDetalhe") != "Não se aplica"):
                continue
            inicio = str(linha.get("DatInicioVigencia", ""))
            fim = str(linha.get("DatFimVigencia", ""))
            # A vigencia que estava ATIVA um ano atras — nao simplesmente a anterior.
            # A Copel teve reajuste em jan/2026 alem do de junho, entao "a anterior"
            # seria de janeiro, e nao a que valia no mesmo mes do ano passado.
            if not (inicio <= DATA_ANO_PASSADO <= fim):
                continue
            if melhor is None or inicio > melhor["inicio"]:
                melhor = {
                    "inicio": inicio,
                    "fim": str(linha.get("DatFimVigencia", "")),
                    "te": float(str(linha.get("VlrTE", "0")).replace(",", ".")),
                    "tusd": float(str(linha.get("VlrTUSD", "0")).replace(",", ".")),
                }
    return melhor or {}


def main() -> None:
    df = pd.read_parquet(PARQUET)
    base = df[(df["SigNomeAgente"] == AGENTE)
              & (df["DscSubGrupoTarifario"] == SUBGRUPO)
              & (df["DscSubClasseConsumidor"] == SUBCLASSE)
              & (df["DscBaseTarifaria"] == BASE)]

    if base.empty:
        raise RuntimeError("nenhuma tarifa encontrada — confira os filtros")

    conv = base[base["DscModalidadeTarifaria"] == "Convencional"]
    branca = base[base["DscModalidadeTarifaria"] == "Branca"]

    modalidades = {
        "convencional": {
            "unico": {
                "te": _valor(conv, "TE", "Não se aplica", "Não se aplica"),
                "tusd": _valor(conv, "TUSD", "Não se aplica", "Não se aplica"),
                "fio_b": _valor(conv, "TUSD_FioB", "Não se aplica", "Não se aplica"),
                "te_scee": _valor(conv, "TE", "Não se aplica", "SCEE"),
            }
        },
        "branca": {
            posto.lower().replace(" ", "_"): {
                "te": _valor(branca, "TE", posto, "Não se aplica"),
                "tusd": _valor(branca, "TUSD", posto, "Não se aplica"),
                "fio_b": _valor(branca, "TUSD_FioB", posto, "Não se aplica"),
                "te_scee": _valor(branca, "TE", posto, "SCEE"),
            }
            for posto in ("Fora ponta", "Intermediário", "Ponta")
        },
    }

    dados = {
        "vigencia_anterior": _vigencia_anterior(),
        "fonte": "ANEEL — Componentes Tarifárias 2026",
        "resolucao": str(base["DscResolucaoHomologatoria"].iloc[0]),
        "distribuidora": AGENTE,
        "subgrupo": SUBGRUPO,
        "subclasse": SUBCLASSE,
        "vigencia_inicio": str(base["DatInicioVigencia"].iloc[0]),
        "vigencia_fim": str(base["DatFimVigencia"].iloc[0]),
        "unidade": "R$/MWh",
        "ano_fio_b": ANO_VIGENTE,
        "fio_b_percentual": FIO_B_PERCENTUAL[ANO_VIGENTE],
        "fio_b_base_legal": "Lei 14.300/2022, art. 27 — incide só sobre energia injetada",
        "tributos": {"icms_pr": ICMS_PR, "pis_cofins": PIS_COFINS,
                     "observacao": "aproximação; o cálculo real é 'por dentro' e varia por faixa"},
        # Horarios da tarifa branca da Copel (dia util). Ponta = 3h, intermediario = 1h
        # antes e 1h depois.
        "horarios_branca": {"ponta": [18, 19, 20], "intermediario": [17, 21]},
        "modalidades": modalidades,
    }

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    c = modalidades["convencional"]["unico"]
    total = c["te"] + c["tusd"]
    print(f"Convencional  TE {c['te']:.2f} + TUSD {c['tusd']:.2f} = {total:.2f} R$/MWh")
    print(f"  sem tributos : R$ {total/1000:.4f}/kWh")
    print(f"  com tributos : R$ {total/1000/(1-ICMS_PR-PIS_COFINS):.4f}/kWh")
    print(f"  Fio B        : {c['fio_b']:.2f} R$/MWh  ->  cobrado {FIO_B_PERCENTUAL[ANO_VIGENTE]*100:.0f}% "
          f"= R$ {c['fio_b']*FIO_B_PERCENTUAL[ANO_VIGENTE]/1000:.4f}/kWh injetado")
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
