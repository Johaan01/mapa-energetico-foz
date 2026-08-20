"""Reduz o peso dos GeoJSON servidos, sem perda visível.

Motivo: a apresentação é no celular dos avaliadores, no wifi do evento. Um bairro
grande chega a 9 MB de GeoJSON, e a maior parte disso é precisão inútil — o driver
grava coordenadas com 15 casas decimais, o que representa fração de micrômetro. Seis
casas já dão ~11 cm, muito além do necessário para desenhar um telhado.

Também arredonda as séries de 24 h (3 casas = 1 Wh) e remove a chave "crs" redundante.

Idempotente: rodar de novo em cima do resultado não degrada mais nada.

    python otimizar_web.py            # aplica
    python otimizar_web.py --simular  # só mostra quanto economizaria
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB_DATA = RAIZ / "web" / "data"

CASAS_COORDENADA = 6   # ~11 cm no equador
CASAS_SERIE = 3        # 1 Wh


def _arredondar_coords(no, casas: int):
    if isinstance(no, (int, float)):
        return round(no, casas)
    if isinstance(no, list):
        return [_arredondar_coords(x, casas) for x in no]
    return no


def _arredondar_props(props: dict) -> dict:
    for chave, valor in props.items():
        if isinstance(valor, list) and valor and isinstance(valor[0], (int, float)):
            props[chave] = [round(v, CASAS_SERIE) for v in valor]
        elif isinstance(valor, float):
            props[chave] = round(valor, CASAS_SERIE)
    return props


def _remover_redundancia(props: dict) -> dict:
    """Descarta séries que o frontend consegue derivar.

    Quem não é prosumidor não gera nada: `geracao_kwh` é 24 zeros e `consumo_kwh` é
    idêntico a `carga_kwh`. São 48 números repetidos por imóvel, em ~79% deles. O
    painel da UC já tem o fallback (`consumo = max(carga, 0)`, `geracao = max(-carga, 0)`),
    que para esses casos não é aproximação — é exatamente o mesmo valor.
    """
    if props.get("perfil") != "prosumidor":
        props.pop("consumo_kwh", None)
        props.pop("geracao_kwh", None)
    return props


def otimizar(caminho: Path, simular: bool) -> tuple[int, int]:
    antes = caminho.stat().st_size
    dados = json.loads(caminho.read_text(encoding="utf-8"))

    if dados.get("type") == "FeatureCollection":
        dados.pop("crs", None)  # WGS84 é o padrão do formato; declarar é redundante
        for f in dados.get("features", []):
            if f.get("geometry"):
                f["geometry"]["coordinates"] = _arredondar_coords(
                    f["geometry"]["coordinates"], CASAS_COORDENADA)
            if f.get("properties"):
                f["properties"] = _remover_redundancia(_arredondar_props(f["properties"]))

    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    depois = len(texto.encode("utf-8"))

    if not simular:
        caminho.write_text(texto, encoding="utf-8")
    return antes, depois


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()

    arquivos = sorted(WEB_DATA.rglob("*.geojson"))
    total_antes = total_depois = 0

    for caminho in arquivos:
        antes, depois = otimizar(caminho, args.simular)
        total_antes += antes
        total_depois += depois

    corte = (1 - total_depois / total_antes) * 100 if total_antes else 0
    rotulo = "economizaria" if args.simular else "otimizado"
    print(f"{len(arquivos)} arquivos GeoJSON")
    print(f"  antes  : {total_antes/1e6:7.1f} MB")
    print(f"  depois : {total_depois/1e6:7.1f} MB")
    print(f"  {rotulo}: {corte:.1f}%")


if __name__ == "__main__":
    main()
