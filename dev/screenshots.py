"""Screenshots de validacao do dashboard (substitui os varios shots_*.py da v1).

    cd web && python -m http.server 8765
    python dev/screenshots.py [cidade|acesso|perfil|residencia|tudo]

As imagens caem em dev/saida/ — que nao vai para o repositorio, sao regeneraveis.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8765/"
SAIDA = Path(__file__).resolve().parent / "saida"


def _zoom_ate_imovel(pg, passos: int = 4):
    box = pg.locator("#map").bounding_box()
    cx, cy = box["x"] + box["width"] * 0.42, box["y"] + box["height"] * 0.5
    pg.mouse.move(cx, cy)
    for _ in range(passos):
        pg.mouse.wheel(0, -500)
        pg.wait_for_timeout(400)
    pg.wait_for_timeout(2000)
    return cx, cy


def cidade(pg):
    pg.screenshot(path=SAIDA / "cidade.png")
    pg.evaluate("() => { const s=document.getElementById('hour-slider'); s.value=12; "
                "s.dispatchEvent(new Event('input')); }")
    pg.wait_for_timeout(1400)
    pg.screenshot(path=SAIDA / "cidade_meiodia.png")
    pg.evaluate("() => { const s=document.getElementById('hour-slider'); s.value=19; "
                "s.dispatchEvent(new Event('input')); }")
    pg.wait_for_timeout(1000)


def acesso(pg):
    pg.select_option("#bairro-select", "yolanda")
    pg.wait_for_timeout(4000)
    _zoom_ate_imovel(pg)
    for nivel in ("publico", "consumidor", "distribuidora"):
        pg.select_option("#perfil-select", nivel)
        pg.wait_for_timeout(1200)
        pg.screenshot(path=SAIDA / f"acesso_{nivel}.png")


def perfil(pg):
    pg.select_option("#perfil-select", "distribuidora")
    pg.select_option("#bairro-select", "yolanda")
    pg.wait_for_timeout(4000)
    _zoom_ate_imovel(pg)
    pg.screenshot(path=SAIDA / "modo_carga.png")
    pg.click('#modo-cor button[data-modo="perfil"]')
    pg.wait_for_timeout(1300)
    pg.screenshot(path=SAIDA / "modo_perfil.png")
    pg.click('#modo-cor button[data-modo="carga"]')
    pg.wait_for_timeout(600)


def residencia(pg):
    """Painel da unidade consumidora, aberto ao clicar num imovel."""
    pg.select_option("#perfil-select", "distribuidora")
    pg.select_option("#bairro-select", "yolanda")
    pg.wait_for_timeout(4000)
    cx, cy = _zoom_ate_imovel(pg)

    for dx, dy in [(0, 0), (40, 30), (-60, -40), (90, -20), (-30, 70)]:
        pg.mouse.click(cx + dx, cy + dy)
        pg.wait_for_timeout(900)
        if pg.locator("#uc-painel").count() and not pg.locator("#uc-painel").is_hidden():
            break
    pg.wait_for_timeout(800)
    pg.screenshot(path=SAIDA / "residencia.png", full_page=False)


ROTINAS = {"cidade": cidade, "acesso": acesso, "perfil": perfil, "residencia": residencia}


def main() -> None:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    rotinas = ROTINAS if alvo == "tudo" else {alvo: ROTINAS[alvo]}
    SAIDA.mkdir(exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        erros: list[str] = []
        pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: erros.append(f"PAGEERROR: {e}"))

        pg.goto(URL, wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(5000)

        for nome, fn in rotinas.items():
            fn(pg)
            print(f"  {nome}: ok")

        print("ERROS:", erros if erros else "nenhum")
        b.close()


if __name__ == "__main__":
    main()
