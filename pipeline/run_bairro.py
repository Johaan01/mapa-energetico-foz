"""Roda o pipeline completo para um bairro e exporta os GeoJSON do dashboard.

    python run_bairro.py Yolanda
    python run_bairro.py --todos
    python run_bairro.py --todos --sem-altura      (pula o Earth Engine: mais rapido)
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import geopandas as gpd

import bairros
import buildings as mod_buildings
import grid
import simulate

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "web" / "data" / "bairros"
GEE_PROJECT_ID = "testegee-479916"

# Versao do formato de saida. `--retomar` so pula um bairro se ele ja estiver NESTA
# versao — senao um lote interrompido no meio de uma recalibracao deixaria bairros
# com dado velho para sempre, sem ninguem perceber.
#
# 3: curvas com formato medido (ANEEL CTR) + consumo/geracao gravados separados.
# 2: consumo calibrado no SAMP + subestacoes reais do OSM.
VERSAO_SAIDA = 3


def _iniciar_ee() -> bool:
    try:
        import ee
        ee.Initialize(project=GEE_PROJECT_ID)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  aviso: Earth Engine indisponivel ({type(exc).__name__}); seguindo sem altura")
        return False


def _salvar(gdf: gpd.GeoDataFrame, caminho: Path) -> None:
    if caminho.exists():
        caminho.unlink()
    gdf.to_file(caminho, driver="GeoJSON")


def processar(nome_bairro: str, com_altura: bool, seed: int = 42) -> dict:
    linha = bairros.buscar(nome_bairro)
    poligono = linha.geometry
    slug = bairros.slug(linha["NM_BAIRRO"])
    destino = SAIDA / slug
    destino.mkdir(parents=True, exist_ok=True)

    print(f"  [1/5] footprints do OSM...", flush=True)
    predios = mod_buildings.carregar(poligono, com_altura=com_altura)
    n_total = len(predios)
    n_domicilios = int(predios["e_domicilio"].sum())
    print(f"        {n_total} construcoes ({n_domicilios} tratadas como unidade consumidora)")
    if n_domicilios < grid.TRAFO_MINIMO:
        raise RuntimeError(f"apenas {n_domicilios} unidades consumidoras - recorte pequeno demais")

    print(f"  [2/5] curvas de carga...", flush=True)
    perfis, curvas, consumo, geracao = simulate.simular(predios, seed=seed)
    predios["perfil"] = perfis

    print(f"  [3/5] rede sobre a malha viaria...", flush=True)
    rede = grid.montar(poligono, predios, curvas)
    predios["trafo_id"] = rede["trafo"]
    predios["carga_kwh"] = [[round(float(x), 3) for x in c] for c in curvas]
    predios["carga_pico_kwh"] = curvas.max(axis=1).round(2)
    # Consumo e geracao separados: o painel da UC precisa distinguir o que foi gerado
    # e usado na hora do que foi injetado na rede.
    predios["consumo_kwh"] = [[round(float(x), 3) for x in c] for c in consumo]
    predios["geracao_kwh"] = [[round(float(x), 3) for x in g] for g in geracao]

    print(f"  [4/5] exportando camadas...", flush=True)
    contorno = gpd.GeoDataFrame(
        [{"bairro": linha["NM_BAIRRO"], "municipio": linha["NM_MUN"]}],
        geometry=[poligono], crs="EPSG:4326",
    )
    _salvar(contorno, destino / "boundary.geojson")
    _salvar(predios, destino / "buildings.geojson")
    _salvar(grid.alimentadores_geojson(rede), destino / "feeders.geojson")
    _salvar(grid.ramais_geojson(rede, predios), destino / "ramais.geojson")

    trafos = grid.transformadores_geojson(rede, predios)
    _salvar(trafos, destino / "transformers.geojson")

    sub = grid.subestacao_geojson(rede)
    _salvar(sub, destino / "substation.geojson")
    sub_props = sub.iloc[0]
    subestacao_meta = f"{sub_props['nome']} — {sub_props['fonte_dado']}"

    print(f"  [5/5] metadados...", flush=True)
    area_km2 = gpd.GeoSeries([poligono], crs=4326).to_crs(grid.UTM_CRS).area.iloc[0] / 1e6
    populacao = linha["populacao"]
    domicilios_ibge = linha["domicilios_estimados"]

    meta = {
        "versao_saida": VERSAO_SAIDA,
        "bairro": linha["NM_BAIRRO"],
        "slug": slug,
        "municipio": linha["NM_MUN"],
        "cd_bairro": int(linha["CD_BAIRRO"]),
        "area_km2": round(float(area_km2), 4),
        "populacao_censo2022": int(populacao) if populacao == populacao else None,
        "domicilios_estimados_ibge": int(domicilios_ibge) if domicilios_ibge == domicilios_ibge else None,
        "construcoes_osm": n_total,
        "unidades_consumidoras": n_domicilios,
        "transformadores": int(len(trafos)),
        "imoveis_por_trafo": {
            "min": int(trafos["n_imoveis"].min()),
            "mediana": int(trafos["n_imoveis"].median()),
            "max": int(trafos["n_imoveis"].max()),
        },
        "perfis": {
            "residencial": int((perfis == "residencial").sum()),
            "prosumidor": int((perfis == "prosumidor").sum()),
            "comercial": int((perfis == "comercial").sum()),
            "nao_residencial": int((perfis == "nao_residencial").sum()),
        },
        "taxa_prosumidor_calibrada": simulate.TAXA_PROSUMIDOR,
        "com_altura_gee": com_altura,
        # Procedencia explicita: o que e medido e o que e estimado. Sem isso, um numero
        # como "unidades consumidoras" fica ambiguo — e ele E uma estimativa.
        "procedencia": {
            "real_medido": {
                "limite_do_bairro": "IBGE — malha de bairros do Censo 2022",
                "populacao": "IBGE — Censo 2022",
                "footprints": "OpenStreetMap (contribuidores)",
                "malha_viaria": "OpenStreetMap (contribuidores)",
                "altura_das_edificacoes": "Google Open Buildings 2.5D Temporal (±1,5 m)" if com_altura else None,
                "subestacao": subestacao_meta,
                "consumo_medio_por_classe": "ANEEL SAMP 2025 (COPEL-DIS) — área de concessão, não municipal",
                "taxa_de_adesao_solar": "ANEEL Geração Distribuída + IBGE Censo 2022",
            },
            "estimado": {
                "unidades_consumidoras": (
                    "contagem de footprints do OSM com área ≥ 40 m². NÃO é o cadastro da "
                    "Copel: um prédio de apartamentos conta como 1, e imóveis não mapeados "
                    "no OSM ficam de fora."
                ),
                "curvas_de_24h": (
                    "sintéticas. A MÉDIA do conjunto é calibrada no consumo real da ANEEL; "
                    "o formato da curva e a variação entre imóveis são modelados."
                ),
                "quem_tem_painel_solar": (
                    "sorteio ponderado por área, respeitando a taxa real de adesão. "
                    "Não é detecção — não sabemos quais telhados realmente têm UFV."
                ),
                "posicao_dos_transformadores": (
                    "FICTÍCIA. Agrupamos ~30 imóveis por trecho de rua; os transformadores "
                    "reais estão em postes específicos, dado que a Copel não publica."
                ),
                "tracado_da_rede": (
                    "plausível, não real. Árvore radial sobre as ruas; o cabeamento da "
                    "Copel não é público."
                ),
            },
        },
    }
    (destino / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _resumo(meta: dict) -> dict:
    campos = ("bairro", "slug", "populacao_censo2022", "unidades_consumidoras", "transformadores")
    return {k: meta.get(k) for k in campos}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bairro", nargs="?", default="Yolanda")
    parser.add_argument("--todos", action="store_true")
    parser.add_argument("--sem-altura", action="store_true")
    parser.add_argument("--retomar", action="store_true",
                        help="pula bairros que ja tem meta.json (util apos falha de rede)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    com_altura = not args.sem_altura
    if com_altura:
        com_altura = _iniciar_ee()

    if args.todos:
        alvos = sorted(bairros.listar()["NM_BAIRRO"])
    else:
        alvos = [args.bairro]

    SAIDA.mkdir(parents=True, exist_ok=True)
    indice, falhas = [], []

    for i, nome in enumerate(alvos, 1):
        pronto = SAIDA / bairros.slug(nome) / "meta.json"
        if args.retomar and pronto.exists():
            anterior = json.loads(pronto.read_text(encoding="utf-8"))
            if anterior.get("versao_saida") == VERSAO_SAIDA:
                indice.append(_resumo(anterior))
                print(f"[{i}/{len(alvos)}] {nome} — já na versão {VERSAO_SAIDA}, pulando", flush=True)
                continue
            print(f"[{i}/{len(alvos)}] {nome} — versão antiga, reprocessando", flush=True)

        print(f"\n[{i}/{len(alvos)}] {nome}", flush=True)
        try:
            meta = processar(nome, com_altura, seed=args.seed)
            indice.append(_resumo(meta))
            print(f"        OK - {meta['unidades_consumidoras']} UCs, {meta['transformadores']} trafos")
        except Exception as exc:  # noqa: BLE001
            falhas.append({"bairro": nome, "erro": f"{type(exc).__name__}: {exc}"})
            print(f"        FALHOU: {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc(limit=2, file=sys.stderr)

    if args.todos:
        (SAIDA / "index.json").write_text(
            json.dumps({"bairros": sorted(indice, key=lambda b: b["bairro"]), "falhas": falhas},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n=== {len(indice)} bairros OK, {len(falhas)} falhas ===")
        for f in falhas:
            print(f"  - {f['bairro']}: {f['erro']}")


if __name__ == "__main__":
    main()
