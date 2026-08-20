"""Perfil solar REAL de Foz do Iguaçu, da NASA POWER.

Ate aqui a geracao fotovoltaica usava uma gaussiana centrada no meio-dia — um modelo
razoavel, mas inventado. A NASA POWER publica irradiancia horaria derivada de satelite
(ALLSKY_SFC_SW_DWN), que ja embute a nebulosidade real do local: dia nublado aparece
como irradiancia baixa. E gratuita, global e cobre de 1981 ate hoje.

Com isso a curva de geracao passa a ter formato medido:
  - assimetria real entre manha e tarde (nuvem convectiva de fim de tarde no verao);
  - largura do dia solar conforme a latitude e a estacao;
  - nivel medio coerente com o ceu de Foz do Iguacu, nao com uma curva teorica.

A AMPLITUDE continua ancorada na injecao real medida (ANEEL SAMP) — a irradiancia
define o FORMATO e a variacao sazonal.

    python irradiancia.py                 # media anual
    python irradiancia.py --mes 8         # so agosto
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "web" / "data" / "irradiancia.json"

# Centro aproximado de Foz do Iguacu.
LAT, LON = -25.5163, -54.5854

API = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMETRO = "ALLSKY_SFC_SW_DWN"  # irradiancia global horizontal, W/m2, ceu real
ANO_INICIO, ANO_FIM = 2023, 2024


def baixar(lat: float = LAT, lon: float = LON) -> dict:
    resp = requests.get(API, params={
        "parameters": PARAMETRO,
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": f"{ANO_INICIO}0101",
        "end": f"{ANO_FIM}1231",
        "format": "JSON",
    }, timeout=300)
    resp.raise_for_status()
    return resp.json()


def perfil_horario(bruto: dict, mes: int | None = None) -> tuple[list[float], dict]:
    """Media da irradiancia por hora do dia. Normalizada para media 1,0."""
    serie = bruto["properties"]["parameter"][PARAMETRO]

    soma = np.zeros(24)
    conta = np.zeros(24)
    for carimbo, valor in serie.items():
        # carimbo no formato AAAAMMDDHH
        if valor is None or valor < -100:  # sentinela de faltante da NASA POWER
            continue
        if mes is not None and int(carimbo[4:6]) != mes:
            continue
        hora = int(carimbo[8:10])
        soma[hora] += valor
        conta[hora] += 1

    media = np.divide(soma, np.maximum(conta, 1))
    total = media.sum()

    estatisticas = {
        "irradiancia_media_w_m2": round(float(media.mean()), 2),
        # Horas de Sol Pleno: energia diaria / 1000 W/m2.
        "hsp_kwh_m2_dia": round(float(total / 1000), 2),
        "hora_pico": int(np.argmax(media)),
        "horas_com_sol": int((media > 10).sum()),
        "amostras": int(conta.sum()),
    }
    formato = [round(float(v / media.mean()), 5) for v in media] if total > 0 else [0.0] * 24
    return formato, estatisticas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mes", type=int, default=None, help="1-12; sem isso, media anual")
    args = ap.parse_args()

    print(f"Baixando irradiância horária da NASA POWER ({ANO_INICIO}-{ANO_FIM})...", flush=True)
    bruto = baixar()

    formato_ano, est_ano = perfil_horario(bruto)
    print(f"\nFoz do Iguaçu — média {ANO_INICIO}-{ANO_FIM}")
    for k, v in est_ano.items():
        print(f"  {k:24s}: {v}")

    por_mes = {}
    for m in range(1, 13):
        _, est = perfil_horario(bruto, mes=m)
        por_mes[m] = est["hsp_kwh_m2_dia"]
    print("\nHSP por mês (kWh/m²/dia):")
    print("  " + "  ".join(f"{m:02d}:{v:.1f}" for m, v in por_mes.items()))

    dados = {
        "fonte": "NASA POWER — ALLSKY_SFC_SW_DWN (irradiância global horizontal, céu real)",
        "local": {"lat": LAT, "lon": LON, "cidade": "Foz do Iguaçu"},
        "periodo": f"{ANO_INICIO}-{ANO_FIM}",
        "observacao": "céu real: a nebulosidade já está embutida na medição por satélite",
        "estatisticas": est_ano,
        "hsp_por_mes": por_mes,
        "formato_horario": formato_ano,
    }
    if args.mes:
        formato_mes, est_mes = perfil_horario(bruto, mes=args.mes)
        dados["mes_selecionado"] = {"mes": args.mes, "estatisticas": est_mes,
                                    "formato_horario": formato_mes}

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
