"""O OSM mapeia infraestrutura eletrica (power=*). Quanto disso existe em Foz do Iguacu?

Se houver subestacoes e linhas reais mapeadas, elas substituem partes sinteticas do
nosso modelo: a subestacao deixa de ser "no da via de maior hierarquia" e passa a ser
o equipamento real, e os trechos de linha mapeados viram infraestrutura confirmada.
"""
import osmnx as ox

import bairros
import cache_osm
import osm_util

osm_util.configurar()
contorno = cache_osm.contorno_municipio()

TAGS = {
    "subestacao": {"power": ["substation"]},
    "transformador": {"power": ["transformer"]},
    "poste": {"power": ["pole"]},
    "torre": {"power": ["tower"]},
    "linha_alta": {"power": ["line"]},
    "linha_menor": {"power": ["minor_line"]},
    "gerador": {"power": ["generator"]},
}

print("Infraestrutura eletrica mapeada no OSM — Foz do Iguacu\n")
for rotulo, tag in TAGS.items():
    try:
        gdf = osm_util.com_retry(
            lambda t=tag: ox.features_from_polygon(contorno, tags=t), rotulo=rotulo
        )
        tipos = gdf.geometry.type.value_counts().to_dict()
        print(f"  {rotulo:14s}: {len(gdf):5d}  {tipos}")
        if rotulo == "subestacao" and len(gdf):
            cols = [c for c in ("name", "operator", "voltage", "substation") if c in gdf.columns]
            print(gdf[cols].head(12).to_string())
    except Exception as exc:  # noqa: BLE001
        print(f"  {rotulo:14s}:     0  ({type(exc).__name__})")
    osm_util.pausa(1.5)
