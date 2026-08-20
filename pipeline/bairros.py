"""Recorte oficial de bairros (malha IBGE / Censo 2022) + populacao real por bairro.

Fonte da geometria:
  geoftp.ibge.gov.br .../censo_2022/bairros/shp/UF/PR_bairros_CD2022.zip
Fonte da populacao:
  .../censo_2022/tabelas_complementares/Populacao_residente_por_bairros_sexo_idade.xlsx

Ambos ja baixados em data/ibge/. Este modulo so le e filtra.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import openpyxl

DATA_IBGE = Path(__file__).resolve().parent.parent / "data" / "ibge"
SHP = DATA_IBGE / "PR_bairros" / "PR_bairros_CD2022.shp"
XLSX = DATA_IBGE / "Populacao_residente_por_bairros_sexo_idade.xlsx"

MUNICIPIO_PADRAO = "Foz do Iguaçu"
# Media de moradores por domicilio em Foz do Iguacu (Censo 2022): 285.415 hab / ~101.200 dom.
HAB_POR_DOMICILIO = 2.82


@lru_cache(maxsize=1)
def _malha() -> gpd.GeoDataFrame:
    return gpd.read_file(SHP)


@lru_cache(maxsize=1)
def _populacao() -> dict[int, int]:
    """{CD_BAIRRO (int): populacao residente}."""
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    for _ in range(10):
        next(rows)

    pop: dict[int, int] = {}
    for row in rows:
        cod_bairro, total = row[5], row[6]
        if isinstance(cod_bairro, int) and isinstance(total, int):
            pop[cod_bairro] = total
    return pop


def listar(municipio: str = MUNICIPIO_PADRAO) -> gpd.GeoDataFrame:
    """Todos os bairros do municipio, com populacao e domicilios estimados."""
    gdf = _malha()
    gdf = gdf[gdf["NM_MUN"] == municipio].copy()

    pop = _populacao()
    gdf["CD_BAIRRO"] = gdf["CD_BAIRRO"].astype("int64")
    gdf["populacao"] = gdf["CD_BAIRRO"].map(pop)
    gdf["domicilios_estimados"] = (gdf["populacao"] / HAB_POR_DOMICILIO).round()
    return gdf.reset_index(drop=True)


def _normalizar(texto: str) -> str:
    """Minusculo e sem acento: 'Carimã' e 'carima' devem casar na linha de comando."""
    import unicodedata
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return sem_acento.casefold().strip()


def buscar(nome: str, municipio: str = MUNICIPIO_PADRAO):
    """Uma linha da malha pelo nome do bairro, ignorando caixa e acento."""
    gdf = listar(municipio)
    alvo = _normalizar(nome)
    chaves = gdf["NM_BAIRRO"].map(_normalizar)

    hit = gdf[chaves == alvo]
    if hit.empty:
        hit = gdf[chaves.str.contains(alvo, na=False, regex=False)]
    if hit.empty:
        disponiveis = ", ".join(sorted(gdf["NM_BAIRRO"]))
        raise ValueError(f"Bairro '{nome}' nao encontrado em {municipio}. Disponiveis: {disponiveis}")
    return hit.iloc[0]


def slug(nome: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return "-".join(s.lower().split())


if __name__ == "__main__":
    gdf = listar()
    gdf = gdf.to_crs(31982)
    gdf["area_km2"] = (gdf.geometry.area / 1e6).round(3)
    cols = ["NM_BAIRRO", "populacao", "domicilios_estimados", "area_km2"]
    print(gdf[cols].sort_values("populacao", ascending=False).to_string(index=False))
