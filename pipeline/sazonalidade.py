"""Sazonalidade mensal REAL: consumo, geracao e tarifa, mes a mes.

O modelo de receita do produto e participativo — ficamos com um percentual da economia
comprovada contra o MESMO MES DO ANO ANTERIOR. Isso so e auditavel se soubermos separar
tres efeitos que mudam a conta ao longo do ano, e nenhum deles pode ser chutado:

  consumo  varia com a estacao (ar-condicionado no verao)      -> ANEEL SAMP, mensal
  geracao  varia com o sol (jan tem 2,3x o sol de jul em Foz)  -> NASA POWER, mensal
  tarifa   varia com reajuste e bandeira                       -> ANEEL, por vigencia

Sem isso, um contrato de "percentual sobre a economia" cobraria taxa sobre variacao
sazonal e reajuste tarifario — coisas que o servico nao causou.

    python sazonalidade.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
SAMP = RAIZ / "data" / "aneel" / "samp-2025.parquet"
IRRADIANCIA = RAIZ / "web" / "data" / "irradiancia.json"
TARIFAS_CSV = RAIZ / "data" / "aneel" / "tarifas-homologadas.csv"
SAIDA = RAIZ / "web" / "data" / "sazonalidade.json"

DISTRIBUIDORA = "COPEL-DIS"
METRICA = "Energia TE (kWh)"


def consumo_mensal() -> dict[int, float]:
    """Indice de consumo residencial por mes (1,0 = media do ano). Fonte: SAMP."""
    df = pd.read_parquet(SAMP)
    d = df[(df["SigAgenteDistribuidora"] == DISTRIBUIDORA)
           & (df["DscClasseConsumoMercado"] == "Residencial")]

    energia = d[d["DscDetalheMercado"] == METRICA]
    consumidores = d[d["DscDetalheMercado"] == "Número de consumidores"]

    kwh = energia.groupby("DatCompetencia")["VlrMercado"].sum()
    ucs = consumidores.groupby("DatCompetencia")["VlrMercado"].sum()
    comum = kwh.index.intersection(ucs.index)

    por_uc = (kwh[comum] / ucs[comum])
    por_mes = {pd.Timestamp(i).month: float(v) for i, v in por_uc.items()}
    media = sum(por_mes.values()) / len(por_mes)
    return {m: round(v / media, 4) for m, v in sorted(por_mes.items())}


def geracao_mensal() -> dict[int, float]:
    """Indice de geracao solar por mes (1,0 = media). Fonte: NASA POWER."""
    dados = json.loads(IRRADIANCIA.read_text(encoding="utf-8"))
    hsp = {int(m): float(v) for m, v in dados["hsp_por_mes"].items()}
    media = sum(hsp.values()) / len(hsp)
    return {m: round(v / media, 4) for m, v in sorted(hsp.items())}


def tarifa_por_mes(anos: tuple[int, ...]) -> dict[str, float]:
    """Tarifa cheia (TE+TUSD, R$/MWh) vigente em cada mes. Fonte: ANEEL."""
    vigencias: list[dict] = []
    with TARIFAS_CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            if (linha.get("SigAgente") != DISTRIBUIDORA
                    or linha.get("DscSubGrupo") != "B1"
                    or linha.get("DscSubClasse") != "Residencial"
                    or linha.get("DscModalidadeTarifaria") != "Convencional"
                    or linha.get("DscBaseTarifaria") != "Tarifa de Aplicação"
                    or linha.get("DscDetalhe") != "Não se aplica"):
                continue
            vigencias.append({
                "inicio": str(linha.get("DatInicioVigencia", "")),
                "fim": str(linha.get("DatFimVigencia", "")),
                "valor": (float(str(linha.get("VlrTE", "0")).replace(",", "."))
                          + float(str(linha.get("VlrTUSD", "0")).replace(",", "."))),
            })

    saida: dict[str, float] = {}
    for ano in anos:
        for mes in range(1, 13):
            dia15 = f"{ano}-{mes:02d}-15"  # meio do mes como referencia
            ativa = [v for v in vigencias if v["inicio"] <= dia15 <= v["fim"]]
            if ativa:
                saida[f"{ano}-{mes:02d}"] = round(max(v["valor"] for v in ativa), 2)
    return saida


def main() -> None:
    consumo = consumo_mensal()
    geracao = geracao_mensal()
    tarifas = tarifa_por_mes((2025, 2026))

    dados = {
        "consumo_indice": {
            "fonte": "ANEEL SAMP 2025 (COPEL-DIS, residencial) — kWh por UC, mês a mês",
            "base": "1,0 = média do ano",
            "por_mes": consumo,
        },
        "geracao_indice": {
            "fonte": "NASA POWER — HSP mensal em Foz do Iguaçu",
            "base": "1,0 = média do ano",
            "por_mes": geracao,
        },
        "tarifa_rs_mwh": {
            "fonte": "ANEEL — tarifas homologadas B1 residencial convencional (TE+TUSD)",
            "por_mes": tarifas,
        },
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    print("mês   consumo   geração   tarifa 2025   tarifa 2026")
    for m in range(1, 13):
        t25 = tarifas.get(f"2025-{m:02d}")
        t26 = tarifas.get(f"2026-{m:02d}")
        print(f" {m:02d}   {consumo.get(m, 0):7.3f}   {geracao.get(m, 0):7.3f}   "
              f"{t25 if t25 else '—':>11}   {t26 if t26 else '—':>11}")
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
