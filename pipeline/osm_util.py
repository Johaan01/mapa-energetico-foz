"""Resiliencia nas consultas ao OpenStreetMap.

A API Overpass e um servico publico gratuito e cai com alguma frequencia (timeout,
429, 504). Num lote de 37 bairros isso e praticamente garantido, entao vale tentar de
novo com espera crescente e alternar de espelho antes de desistir do bairro.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

import osmnx as ox

T = TypeVar("T")

# kumi primeiro: nos testes deste projeto foi o unico que respondeu de forma estavel
# quando o espelho principal comecou a recusar conexao apos varias consultas seguidas.
ESPELHOS = [
    "https://overpass.kumi.systems/api",
    "https://overpass-api.de/api",
    "https://overpass.osm.jp/api",
]

TENTATIVAS = 5
ESPERA_BASE_S = 6


def _desligar_pinning_dns() -> None:
    """Impede o osmnx de fixar um unico IP do servidor Overpass.

    O osmnx resolve o host e reescreve socket.getaddrinfo para sempre usar aquele IP
    (assim o check de status e a consulta caem na mesma maquina do balanceador). O
    efeito colateral: se o IP escolhido estiver inacessivel a partir desta rede, tudo
    passa a dar ConnectTimeout — foi o que aconteceu aqui, com o osmnx grudando em
    65.109.112.52 enquanto 162.55.144.139, do mesmo hostname, respondia em 4s.
    Neutralizando o pinning, o resolvedor do sistema faz failover entre os IPs.
    """
    try:
        import osmnx._http as _http
        _http._config_dns = lambda url: None
    except Exception:  # noqa: BLE001 - versao futura pode nao ter esse interno
        pass


def configurar() -> None:
    ox.settings.requests_timeout = 180
    # O laco de espera por slot do osmnx dorme em silencio por minutos (sem log, sem
    # conexao aberta), o que e indistinguivel de travamento. Preferimos autolimitar o
    # ritmo com uma pausa curta entre consultas — ver `pausa()`.
    ox.settings.overpass_rate_limit = False
    ox.settings.use_cache = True  # relanca um bairro sem repetir download
    _desligar_pinning_dns()


def pausa(segundos: float = 2.0) -> None:
    """Cortesia entre consultas seguidas ao servico publico."""
    time.sleep(segundos)


def _resposta_vazia(exc: Exception) -> bool:
    """Distingue 'a area nao tem nada' de 'a rede falhou'.

    Blocos sobre rio ou parque nacional voltam sem elementos, e o osmnx levanta
    InsufficientResponseError. Insistir nisso e desperdicio: nao ha o que baixar.
    """
    return type(exc).__name__ == "InsufficientResponseError"


def com_retry(fn: Callable[[], T], rotulo: str = "OSM") -> T:
    ultimo: Exception | None = None
    for tentativa in range(TENTATIVAS):
        espelho = ESPELHOS[tentativa % len(ESPELHOS)]
        ox.settings.overpass_url = espelho
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - qualquer falha de rede merece nova tentativa
            ultimo = exc
            if _resposta_vazia(exc) or tentativa == TENTATIVAS - 1:
                break
            espera = ESPERA_BASE_S * (2 ** tentativa)
            print(
                f"        {rotulo}: {type(exc).__name__} em {espelho}; "
                f"nova tentativa em {espera}s ({tentativa + 1}/{TENTATIVAS})",
                flush=True,
            )
            time.sleep(espera)
    raise RuntimeError(f"{rotulo} falhou apos {TENTATIVAS} tentativas: {ultimo}") from ultimo
