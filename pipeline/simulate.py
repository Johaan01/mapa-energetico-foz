"""Curvas de carga de 24h por imovel, montadas so a partir de dado real.

O consumo de uma UC especifica e fechado (LGPD), entao a curva individual e sintetica —
mas cada ingrediente dela vem de medicao publicada:

  formato da curva : ANEEL CTR — campanhas de medicao das distribuidoras, 15 em 15 min
  nivel (kWh/dia)  : ANEEL SAMP — energia faturada / numero de consumidores (Copel)
  injecao solar    : ANEEL SAMP — energia injetada por prosumidor
  variacao entre   : area util real do imovel (footprint OSM x pavimentos)
  imoveis
  % de prosumidores: ANEEL Geracao Distribuida x IBGE Censo 2022

O que sobra de arbitrado e a forma da geracao fotovoltaica (gaussiana no meio-dia,
modelo padrao de PV) e o sorteio de QUAIS imoveis sao prosumidores.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

HORAS = np.arange(24)

# Fatia do recorte tratada como uso comercial. Heuristica de simulacao (o OSM da
# regiao nao tem tag de uso confiavel na maioria dos imoveis), nao dado medido.
TAXA_COMERCIAL = 0.10

# Taxa real de adesao residencial a geracao solar (UFV):
#   ANEEL, empreendimento-geracao-distribuida.csv (snapshot 08/2026): 1.364 UCs
#   residenciais com UFV na zona de CEP 85853.
#   Essa zona cobre 6 bairros oficiais do IBGE (Yolanda, Sao Roque, Bourbon, Remanso,
#   Mata Verde, Cataratas) - verificado por amostragem de 100 sufixos no ViaCEP.
#   IBGE Censo 2022: 16.541 hab nesses 6 bairros / 2,82 hab por domicilio = 5.866 dom.
#   1.364 / 5.866 = 0,233.
# Numerador e denominador descrevem a MESMA geografia, que e o ponto: dividir os 1.364
# da zona inteira pelos imoveis de um bairro so dava 81%, valor impossivel.
TAXA_PROSUMIDOR = 0.233

# --- Ancoragem em consumo REAL (ANEEL SAMP 2025, COPEL-DIS) -------------------
# A amplitude nao e mais um numero magico. O SAMP publica energia faturada e numero
# de consumidores no mesmo recorte, entao temos a media real por UC:
#
#   Residencial : 174,1 kWh/mes  ->  5,73 kWh/dia
#   Comercial   : 582,2 kWh/mes  -> 19,15 kWh/dia
#   Injecao GD  : 353,9 kWh/mes  -> 11,64 kWh/dia  (313.341 UCs residenciais com GD)
#
# Antes deste ancoramento o modelo gerava ~1.351 kWh/mes por residencia — 7,8x acima
# do real. A area do imovel continua modulando a variacao entre casas; o que mudou e
# que a MEDIA do conjunto agora bate com o mercado declarado a ANEEL.
#
# Ressalva: o SAMP e por area de concessao (Copel inteira), nao por municipio.
CONSUMO_MEDIO_KWH_DIA = {"residencial": 5.73, "prosumidor": 5.73, "comercial": 19.15}

# Injecao liquida diaria de um prosumidor. Nao separamos autoconsumo: a geracao bruta
# e maior que isto, mas o que a plataforma modela — e o que importa para a rede — e o
# liquido trocado com ela.
INJECAO_MEDIA_KWH_DIA = 11.64


def _gaussiana(horas, centro, largura, altura):
    return altura * np.exp(-0.5 * ((horas - centro) / largura) ** 2)


def _patamar(horas, inicio, fim, inclinacao=2.2):
    sobe = 1.0 / (1.0 + np.exp(-inclinacao * (horas - inicio)))
    desce = 1.0 / (1.0 + np.exp(-inclinacao * (horas - fim)))
    return sobe - desce


def _forma_residencial(horas):
    return 0.25 + _gaussiana(horas, 8.0, 1.3, 0.5) + _gaussiana(horas, 19.5, 2.0, 1.3)


def _forma_comercial(horas):
    return 0.10 + 0.95 * _patamar(horas, 8.0, 18.0)


_ARQUIVO_IRRADIANCIA = Path(__file__).resolve().parent.parent / "web" / "data" / "irradiancia.json"


@lru_cache(maxsize=1)
def _irradiancia_medida() -> np.ndarray | None:
    """Perfil horario de irradiancia real (NASA POWER). None se indisponivel."""
    if not _ARQUIVO_IRRADIANCIA.exists():
        return None
    dados = json.loads(_ARQUIVO_IRRADIANCIA.read_text(encoding="utf-8"))
    formato = dados.get("formato_horario")
    return np.asarray(formato, dtype=float) if formato else None


def _forma_geracao_solar(horas):
    """Curva de geracao fotovoltaica ao longo do dia.

    Usa a irradiancia horaria REAL de Foz do Iguacu (NASA POWER, ceu real — a
    nebulosidade ja esta embutida na medicao por satelite). O ceu de verdade nao e
    uma gaussiana simetrica: o pico medido fica as 11h, nao ao meio-dia, e a tarde
    cai mais rapido que a manha sobe (nuvem convectiva).

    Cai na gaussiana so se o arquivo de irradiancia nao existir.
    """
    medida = _irradiancia_medida()
    if medida is not None:
        return medida
    return _gaussiana(horas, 12.0, 2.3, 1.0)


# Formas sinteticas: usadas apenas se as curvas medidas nao estiverem disponiveis.
FORMAS = {
    "residencial": _forma_residencial,
    "prosumidor": _forma_residencial,
    "comercial": _forma_comercial,
}

# --- Curvas medidas (ANEEL CTR) ----------------------------------------------
# Formato real, de campanha de medicao da Copel, em vez de soma de gaussianas. Sao
# varios perfis por classe (8 residenciais, 20 comerciais) com silhuetas diferentes
# entre si — inclusive residencias que picam ao meio-dia, nao a noite. Sortear entre
# eles da heterogeneidade MEDIDA, nao inventada.
_ARQUIVO_CURVAS = Path(__file__).resolve().parent.parent / "web" / "data" / "curvas_tipo.json"


@lru_cache(maxsize=1)
def curvas_medidas() -> dict[str, np.ndarray]:
    """{classe: matriz (n_perfis, 24) com media 1,0}. Vazio se o arquivo nao existir."""
    if not _ARQUIVO_CURVAS.exists():
        return {}
    dados = json.loads(_ARQUIVO_CURVAS.read_text(encoding="utf-8"))
    saida: dict[str, np.ndarray] = {}
    for classe, bloco in dados.get("perfis", {}).items():
        curvas = list(bloco.get("curvas", {}).values())
        if curvas:
            saida[classe] = np.asarray(curvas, dtype=float)
    return saida


def _matriz_de_formas(perfil: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """Uma curva de formato por imovel: medida quando houver, sintetica se nao."""
    medidas = curvas_medidas()
    classe = "comercial" if perfil == "comercial" else "residencial"

    if classe in medidas:
        banco = medidas[classe]
        return banco[rng.integers(0, len(banco), size=n)]

    return np.tile(FORMAS[perfil](HORAS), (n, 1))


def atribuir_perfis(areas_uteis: np.ndarray, elegivel: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Sorteia o perfil de cada imovel.

    Prosumidores sao sorteados SEM reposicao e ponderados por area (telhado maior =
    mais chance de ter UFV, proxy de renda e area disponivel), com o total travado em
    round(TAXA_PROSUMIDOR * n_residenciais). Assim a taxa calibrada com dado real vale
    exatamente no recorte, nao apenas "na media de varias execucoes".
    """
    perfis = np.full(len(areas_uteis), "nao_residencial", dtype=object)
    idx = np.where(elegivel)[0]
    if len(idx) == 0:
        return perfis

    comercial = rng.random(len(idx)) < TAXA_COMERCIAL
    perfis[idx[comercial]] = "comercial"

    residenciais = idx[~comercial]
    perfis[residenciais] = "residencial"
    if len(residenciais) == 0:
        return perfis

    n_prosumidor = int(round(len(residenciais) * TAXA_PROSUMIDOR))
    if n_prosumidor > 0:
        pesos = np.sqrt(np.clip(areas_uteis[residenciais], 1.0, None))
        escolhidos = rng.choice(
            len(residenciais), size=min(n_prosumidor, len(residenciais)),
            replace=False, p=pesos / pesos.sum(),
        )
        perfis[residenciais[escolhidos]] = "prosumidor"

    return perfis


def _calibrar(curvas: np.ndarray, alvo_kwh_dia: float) -> np.ndarray:
    """Escala o conjunto para que o consumo diario MEDIO bata com o alvo real.

    A variacao relativa entre imoveis (dada pela area) e preservada; o que se ajusta
    e o nivel do conjunto.
    """
    media = curvas.sum(axis=1).mean()
    if media <= 0:
        return curvas
    return curvas * (alvo_kwh_dia / media)


def _escalar_para_injecao(consumo: np.ndarray, geracao: np.ndarray, alvo_injecao: float) -> np.ndarray:
    """Escala a geracao para que a ENERGIA EXPORTADA media bata com o dado da ANEEL.

    "Energia Injetada" no SAMP e so o excedente que chega a rede: nas horas de sol, o
    autoconsumo abate parte da geracao antes de sobrar qualquer coisa para exportar.
    Entao nao basta calibrar a geracao bruta — o alvo e a soma das horas em que o
    liquido fica negativo. Como essa relacao nao e linear (o clip em zero), resolvemos
    o fator por bisseccao.
    """
    def exportado(fator: float) -> float:
        liquido = consumo - geracao * fator
        return float(-np.minimum(liquido, 0.0).sum(axis=1).mean())

    baixo, alto = 0.0, 1.0
    while exportado(alto) < alvo_injecao and alto < 1e6:
        alto *= 2.0

    for _ in range(60):
        meio = (baixo + alto) / 2.0
        if exportado(meio) < alvo_injecao:
            baixo = meio
        else:
            alto = meio

    return geracao * ((baixo + alto) / 2.0)


def gerar_curvas(
    areas_uteis: np.ndarray, perfis: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devolve (liquido, consumo, geracao), cada um matriz (n_imoveis, 24) em kWh.

    O liquido e o que a rede enxerga: positivo puxa, negativo injeta. Consumo e
    geracao vao separados porque o painel da unidade consumidora precisa distinguir
    "gerei e usei na hora" de "gerei e mandei para a rede" — no liquido os dois se
    confundem.
    """
    n_total = len(areas_uteis)
    curvas = np.zeros((n_total, 24))
    consumo_total = np.zeros((n_total, 24))
    geracao_total = np.zeros((n_total, 24))

    for perfil, forma in FORMAS.items():
        mask = perfis == perfil
        if not mask.any():
            continue
        n = int(mask.sum())

        # Area modula a diferenca entre imoveis; o nivel absoluto vem da calibracao;
        # o formato vem das curvas medidas (uma sorteada por imovel).
        base = areas_uteis[mask][:, None]
        escala_imovel = rng.normal(1.0, 0.10, size=(n, 1))
        ruido_hora = rng.normal(1.0, 0.06, size=(n, 24))
        formas = _matriz_de_formas(perfil, n, rng)

        consumo = np.clip(base * formas * escala_imovel * ruido_hora, 0.0, None)
        consumo = _calibrar(consumo, CONSUMO_MEDIO_KWH_DIA[perfil])

        consumo_total[mask] = consumo

        if perfil == "prosumidor":
            ruido_g = rng.normal(1.0, 0.08, size=(n, 24))
            geracao = np.clip(base * _forma_geracao_solar(HORAS)[None, :] * escala_imovel * ruido_g, 0.0, None)
            geracao = _escalar_para_injecao(consumo, geracao, INJECAO_MEDIA_KWH_DIA)
            geracao_total[mask] = geracao
            curvas[mask] = consumo - geracao
        else:
            curvas[mask] = consumo

    return np.round(curvas, 4), np.round(consumo_total, 4), np.round(geracao_total, 4)


def simular(predios, seed: int = 42):
    """Devolve (perfis, liquido, consumo, geracao) para um GeoDataFrame de predios."""
    rng = np.random.default_rng(seed)
    areas = predios["area_util_m2"].to_numpy(dtype=float)
    elegivel = predios["e_domicilio"].to_numpy(dtype=bool)

    perfis = atribuir_perfis(areas, elegivel, rng)
    liquido, consumo, geracao = gerar_curvas(areas, perfis, rng)
    return perfis, liquido, consumo, geracao
