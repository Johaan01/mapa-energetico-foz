"""Prova visual: desenha os footprints exportados por cima da imagem de satelite real.

Sem isso, "os predios batem com a realidade" e so afirmacao. Aqui o satelite (ESRI
World Imagery, tiles brutos) e os poligonos do OSM sao renderizados no MESMO recorte
geografico, lado a lado e sobrepostos.
"""
from __future__ import annotations

import argparse
import io
import math
from pathlib import Path

import geopandas as gpd
import requests
from PIL import Image, ImageDraw

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE_PX = 256


def _deg2num(lat, lon, z):
    n = 2 ** z
    lat_rad = math.radians(lat)
    xf = (lon + 180.0) / 360.0 * n
    yf = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return xf, yf


def mosaico(lat0, lon0, lat1, lon1, z=18):
    """lat0/lon0 = canto superior esquerdo. Retorna (imagem, funcao lonlat->pixel)."""
    x0f, y0f = _deg2num(lat0, lon0, z)
    x1f, y1f = _deg2num(lat1, lon1, z)
    x0, y0, x1, y1 = int(x0f), int(y0f), int(x1f), int(y1f)

    img = Image.new("RGB", ((x1 - x0 + 1) * TILE_PX, (y1 - y0 + 1) * TILE_PX), "#333")
    sess = requests.Session()
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            r = sess.get(TILE_URL.format(z=z, y=ty, x=tx), timeout=30)
            if r.ok and r.headers.get("Content-Type", "").startswith("image"):
                tile = Image.open(io.BytesIO(r.content)).convert("RGB")
                img.paste(tile, ((tx - x0) * TILE_PX, (ty - y0) * TILE_PX))

    def para_pixel(lon, lat):
        xf, yf = _deg2num(lat, lon, z)
        return ((xf - x0) * TILE_PX, (yf - y0) * TILE_PX)

    caixa = (
        int((x0f - x0) * TILE_PX), int((y0f - y0) * TILE_PX),
        int((x1f - x0) * TILE_PX), int((y1f - y0) * TILE_PX),
    )
    return img, para_pixel, caixa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="yolanda")
    ap.add_argument("--lat", type=float, default=-25.5510)
    ap.add_argument("--lon", type=float, default=-54.5735)
    ap.add_argument("--span", type=float, default=0.0035, help="lado do recorte em graus")
    ap.add_argument("--zoom", type=int, default=18)
    ap.add_argument("--out", default="validacao_footprints.png")
    args = ap.parse_args()

    raiz = Path(__file__).resolve().parent.parent
    predios = gpd.read_file(raiz / "web" / "data" / "bairros" / args.slug / "buildings.geojson")

    lat0, lon0 = args.lat + args.span / 2, args.lon - args.span / 2
    lat1, lon1 = args.lat - args.span / 2, args.lon + args.span / 2

    base, para_pixel, caixa = mosaico(lat0, lon0, lat1, lon1, args.zoom)
    recorte = base.crop(caixa)
    ox_, oy_ = caixa[0], caixa[1]

    sobreposto = recorte.copy()
    draw = ImageDraw.Draw(sobreposto, "RGBA")

    dentro = predios.cx[lon0:lon1, lat1:lat0]
    n = 0
    for geom, dom in zip(dentro.geometry, dentro["e_domicilio"]):
        partes = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for parte in partes:
            pts = [
                (px - ox_, py - oy_)
                for px, py in (para_pixel(x, y) for x, y in parte.exterior.coords)
            ]
            cor = (60, 220, 120, 70) if dom else (200, 200, 60, 70)
            borda = (40, 255, 120, 230) if dom else (230, 230, 60, 230)
            draw.polygon(pts, fill=cor, outline=borda)
            n += 1

    largura, altura = recorte.size
    combinado = Image.new("RGB", (largura * 2 + 8, altura), "white")
    combinado.paste(recorte, (0, 0))
    combinado.paste(sobreposto, (largura + 8, 0))
    combinado.save(args.out)
    print(f"{n} poligonos desenhados sobre o recorte -> {args.out}  ({largura}x{altura} px)")


if __name__ == "__main__":
    main()
