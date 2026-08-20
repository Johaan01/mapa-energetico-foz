"""Caracterizacao dos PERFIS DE CONSUMO medidos — o núcleo do Tema 3.

O desafio pede "compreender os diferentes perfis de consumo para identificar
desperdicios, oportunidades de eficiencia e possibilidades de flexibilizacao". A
tentacao e inventar tres personas (residencial, comercial, prosumidor) e seguir. Nao e
preciso: a ANEEL publica no CTR as curvas de consumidores tipo levantadas em campanhas
de medicao das proprias distribuidoras — 8 perfis residenciais e 20 comerciais so para
a Copel, cada um com silhueta propria.

Este modulo mede cada curva e a classifica por indicadores padrao de engenharia:

  fator de carga    media / pico. Baixo = consumo concentrado em poucas horas, que e
                    justamente o que pesa na rede e o que da para deslocar.
  hora de pico      quando o imovel puxa mais.
  % na ponta        fracao do consumo dentro do horario de ponta (18h-21h) — o que
                    custa mais caro na tarifa branca.
  razao noite/dia   separa quem vive de noite de quem consome de dia (e portanto
                    aproveita melhor a geracao solar).
  flexivel_kwh      quanto do consumo esta na ponta e poderia ser deslocado.

O resultado alimenta duas coisas: a definicao de arquetipos para o pitch e a metrica
de cobranca (quanto cada tipo consegue economizar de fato).

    python perfis_consumidor.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
CURVAS = RAIZ / "web" / "data" / "curvas_tipo.json"
SAIDA = RAIZ / "web" / "data" / "perfis_consumidor.json"

HORAS_PONTA = (18, 19, 20)
HORAS_SOL = tuple(range(9, 16))     # janela util de geracao fotovoltaica
HORAS_NOITE = tuple(range(19, 24)) + tuple(range(0, 6))


def indicadores(curva: np.ndarray) -> dict:
    """Curva normalizada (media 1,0) -> indicadores de forma."""
    total = curva.sum()
    return {
        "hora_pico": int(np.argmax(curva)),
        "fator_carga": round(float(curva.mean() / curva.max()), 3),
        "pct_ponta": round(float(curva[list(HORAS_PONTA)].sum() / total * 100), 1),
        "pct_sol": round(float(curva[list(HORAS_SOL)].sum() / total * 100), 1),
        "pct_noite": round(float(curva[list(HORAS_NOITE)].sum() / total * 100), 1),
        "razao_pico_vale": round(float(curva.max() / max(curva.min(), 1e-6)), 2),
    }


def classificar(ind: dict, classe: str) -> tuple[str, str]:
    """Arquetipo legivel + a oportunidade que ele abre.

    A ordem das regras importa: classificamos primeiro pela HORA DO PICO, depois
    refinamos. Uma versao anterior testava '% na ponta' antes da hora e rotulava como
    "pico noturno" curvas que picavam as 6h e as 11h — o percentual na ponta pode
    passar do limiar mesmo num perfil cujo maximo esta em outro lugar do dia.
    """
    pico = ind["hora_pico"]
    carga = ind["fator_carga"]

    # Curva achatada: o pico perde significado, o que define e a carga de base.
    if carga >= (0.80 if classe == "comercial" else 0.72):
        rotulo = "Comércio contínuo" if classe == "comercial" else "Residencial constante"
        return (rotulo,
                "Curva achatada, carga de base alta (refrigeração, climatização). "
                "Consome de forma estável durante o sol, então é bom candidato a "
                "geração própria; o ganho vem de eficiência, não de deslocamento.")

    if classe == "comercial":
        if 5 <= pico <= 9:
            return ("Comércio matinal",
                    "Pico no início da manhã (padaria, açougue). Parte do consumo "
                    "acontece antes do sol — geração própria cobre só o resto do dia.")
        if 10 <= pico <= 17:
            return ("Comércio diurno",
                    "Pico no horário comercial coincide com o sol: autoconsumo alto, "
                    "pouca injeção e portanto pouco Fio B.")
        return ("Comércio noturno",
                "Opera fora do sol (bar, restaurante). Geração própria renderia pouco "
                "sem bateria, e a carga cai bem no horário de ponta.")

    # residencial
    if 5 <= pico <= 9:
        return ("Residencial matinal",
                "Pico antes do trabalho (chuveiro, café). Fora do horário de ponta, "
                "então já é eficiente em tarifa — ganho vem de eficiência do chuveiro.")
    if 10 <= pico <= 16:
        return ("Residencial diurno",
                "Consome durante o dia (home office, alguém em casa). Aproveita bem a "
                "geração solar sem precisar de bateria.")
    if 17 <= pico <= 22:
        return ("Residencial de pico noturno",
                "Concentra consumo em 18h–21h, o horário mais caro. É o maior "
                "potencial de economia por deslocamento — e o que mais pesa no trafo.")
    return ("Residencial de madrugada",
            "Pico fora de qualquer janela usual: vale investigar carga esquecida ligada.")


def main() -> None:
    dados = json.loads(CURVAS.read_text(encoding="utf-8"))
    saida = {"fonte": dados["fonte"], "distribuidora": dados["distribuidora"],
             "ano_processo": dados["ano_processo"], "classes": {}}

    for classe, bloco in dados["perfis"].items():
        perfis = []
        for ct, curva in bloco["curvas"].items():
            arr = np.asarray(curva, dtype=float)
            ind = indicadores(arr)
            nome, oportunidade = classificar(ind, classe)
            perfis.append({"consumidor_tipo": ct, "arquetipo": nome,
                           "oportunidade": oportunidade, **ind, "curva": curva})

        saida["classes"][classe] = {"subgrupo": bloco["subgrupo"], "perfis": perfis}

        print(f"\n=== {classe.upper()} ({bloco['subgrupo']}) — {len(perfis)} perfis medidos")
        print(f"{'tipo':9s} {'arquétipo':30s} {'pico':>5s} {'f.carga':>8s} {'%ponta':>7s} {'%sol':>6s}")
        for p in sorted(perfis, key=lambda x: -x["pct_ponta"]):
            print(f"{p['consumidor_tipo']:9s} {p['arquetipo'][:30]:30s} "
                  f"{p['hora_pico']:3d}h {p['fator_carga']:8.3f} "
                  f"{p['pct_ponta']:6.1f}% {p['pct_sol']:5.1f}%")

        contagem: dict[str, int] = {}
        for p in perfis:
            contagem[p["arquetipo"]] = contagem.get(p["arquetipo"], 0) + 1
        print("  distribuição:", ", ".join(f"{k}: {v}" for k, v in sorted(contagem.items())))

    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
