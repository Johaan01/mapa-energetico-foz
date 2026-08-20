"""Camada macro da cidade: um arquivo leve com TODOS os transformadores de Foz.

O detalhe por bairro vive em web/data/bairros/<slug>/ e so e baixado quando o usuario
entra naquele bairro — o arquivo pesado (buildings.geojson, ~1 MB) nao faz sentido no
zoom de cidade. Este resumo resolve o outro extremo: ver Foz inteira de uma vez sem
baixar dezenas de MB. Sao ~2 mil pontos, na casa de centenas de KB.

    python resumo_cidade.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BAIRROS_DIR = RAIZ / "web" / "data" / "bairros"
SAIDA_TRAFOS = RAIZ / "web" / "data" / "resumo_transformadores.geojson"
SAIDA_BAIRROS = RAIZ / "web" / "data" / "resumo_bairros.geojson"
SAIDA_SUBESTACOES = RAIZ / "web" / "data" / "subestacoes.geojson"


def exportar_subestacoes() -> int:
    """Todas as subestacoes REAIS do municipio, num arquivo so.

    Cada bairro ja guarda a subestacao que o alimenta, mas o mapa da cidade precisa
    ver todas de uma vez — e diferenciadas: uma conversora de 750 kV da Furnas nao
    cumpre o mesmo papel que uma subestacao de distribuicao da Copel.
    """
    import subestacoes

    gdf = subestacoes.todas().copy()

    def classificar(linha) -> str:
        tipo = str(linha.get("substation", "")).lower()
        if tipo in ("converter", "transmission"):
            return tipo
        return "distribution"

    gdf["classe"] = gdf.apply(classificar, axis=1)
    gdf["nome"] = gdf["name"].where(
        ~gdf["name"].isin(["", "nan", "None"]), "Subestação sem nome (OSM)"
    )
    # Quantos bairros cada subestacao alimenta, segundo o que o pipeline ja decidiu.
    # A chave e (nome, operador): "Subestação Foz do Iguaçu" existe duas vezes em Foz —
    # uma conversora da Furnas e uma de distribuicao da Copel. Casar so por nome faria
    # a conversora de 750 kV parecer que alimenta bairros, o que ela nao faz.
    contagem: dict[tuple[str, str], int] = {}
    for pasta in BAIRROS_DIR.iterdir():
        alvo = pasta / "substation.geojson"
        if pasta.is_dir() and alvo.exists():
            props = json.loads(alvo.read_text(encoding="utf-8"))["features"][0]["properties"]
            chave = (props.get("nome"), str(props.get("operador", "")))
            contagem[chave] = contagem.get(chave, 0) + 1

    gdf["alimenta_bairros"] = [
        contagem.get((n, str(o)), 0) for n, o in zip(gdf["nome"], gdf["operator"])
    ]

    saida = gdf[["nome", "operator", "voltage", "classe", "alimenta_bairros", "geometry"]]
    saida = saida.rename(columns={"operator": "operador", "voltage": "tensao_v"})
    if SAIDA_SUBESTACOES.exists():
        SAIDA_SUBESTACOES.unlink()
    saida.to_file(SAIDA_SUBESTACOES, driver="GeoJSON")
    return len(saida)


def main() -> None:
    trafos: list[gpd.GeoDataFrame] = []
    contornos: list[gpd.GeoDataFrame] = []
    resumo: list[dict] = []

    for pasta in sorted(p for p in BAIRROS_DIR.iterdir() if p.is_dir()):
        meta_path = pasta / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        t = gpd.read_file(pasta / "transformers.geojson")
        t["bairro"] = meta["bairro"]
        t["slug"] = meta["slug"]
        trafos.append(t[["bairro", "slug", "trafo_id", "n_imoveis", "n_prosumidor",
                         "carga_kwh", "carga_pico_kwh", "geometry"]])

        c = gpd.read_file(pasta / "boundary.geojson")
        # Curva do bairro inteiro = soma das curvas dos seus transformadores.
        curva = [round(float(v), 2) for v in
                 pd.DataFrame(list(t["carga_kwh"])).sum(axis=0)]
        c["bairro"] = meta["bairro"]
        c["slug"] = meta["slug"]
        c["unidades_consumidoras"] = meta["unidades_consumidoras"]
        c["populacao"] = meta.get("populacao_censo2022")
        c["transformadores"] = meta["transformadores"]
        c["prosumidores"] = meta["perfis"]["prosumidor"]
        c["carga_kwh"] = [curva]
        c["carga_pico_kwh"] = round(max(curva), 2)
        contornos.append(c[["bairro", "slug", "unidades_consumidoras", "populacao",
                            "transformadores", "prosumidores", "carga_kwh",
                            "carga_pico_kwh", "geometry"]])

        resumo.append({k: meta.get(k) for k in
                       ("bairro", "slug", "populacao_censo2022",
                        "unidades_consumidoras", "transformadores")})

    if not trafos:
        raise RuntimeError("nenhum bairro processado ainda")

    gdf_t = gpd.GeoDataFrame(pd.concat(trafos, ignore_index=True), crs=trafos[0].crs)
    gdf_c = gpd.GeoDataFrame(pd.concat(contornos, ignore_index=True), crs=contornos[0].crs)

    for caminho, gdf in ((SAIDA_TRAFOS, gdf_t), (SAIDA_BAIRROS, gdf_c)):
        if caminho.exists():
            caminho.unlink()
        gdf.to_file(caminho, driver="GeoJSON")

    (BAIRROS_DIR / "index.json").write_text(
        json.dumps({"bairros": sorted(resumo, key=lambda b: b["bairro"])},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    n_sub = exportar_subestacoes()

    kb = lambda p: round(p.stat().st_size / 1024)
    print(f"{len(gdf_c)} bairros | {len(gdf_t)} transformadores | {n_sub} subestações reais")
    print(f"  {SAIDA_SUBESTACOES.name}: {kb(SAIDA_SUBESTACOES)} KB")
    print(f"  {SAIDA_TRAFOS.name}: {kb(SAIDA_TRAFOS)} KB")
    print(f"  {SAIDA_BAIRROS.name}: {kb(SAIDA_BAIRROS)} KB")
    print(f"  index.json atualizado")


if __name__ == "__main__":
    main()
