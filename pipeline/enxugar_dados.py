"""Extrai de cada base bruta só o recorte que o projeto usa.

Os downloads originais somam ~1,8 GB (o CSV de geração distribuída da ANEEL sozinho tem
1,46 GB, com o Brasil inteiro). Nada disso pode ir para o repositório, e sem eles o
projeto deixa de ser reproduzível: quem clonar precisa rebaixar tudo.

Este script resolve os dois lados. Guarda em `data/recorte/` apenas as linhas de Foz do
Iguaçu / COPEL-DIS — alguns MB, versionáveis — e os módulos do pipeline passam a poder
ler daí. As bases brutas viram opcionais, necessárias só para refazer o recorte.

    python enxugar_dados.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BRUTO = RAIZ / "data" / "aneel"
DESTINO = RAIZ / "data" / "recorte"

MUNICIPIO = "Foz do Iguaçu"
DISTRIBUIDORA = "COPEL-DIS"


def _mb(p: Path) -> float:
    return p.stat().st_size / 1e6


def recortar_geracao_distribuida() -> None:
    """1,46 GB (Brasil) -> só as UCs de Foz do Iguaçu."""
    origem = BRUTO / "empreendimento-geracao-distribuida.csv"
    destino = DESTINO / "gd-foz-do-iguacu.csv"
    if not origem.exists():
        print("  gd: base bruta ausente, pulando")
        return

    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    mantidas = 0
    with origem.open("r", encoding="utf-8", newline="") as fe, \
         destino.open("w", encoding="utf-8", newline="") as fs:
        leitor = csv.DictReader(fe, delimiter=";")
        escritor = csv.DictWriter(fs, fieldnames=leitor.fieldnames, delimiter=";")
        escritor.writeheader()
        for linha in leitor:
            if linha.get("NomMunicipio") == MUNICIPIO and linha.get("SigUF") == "PR":
                escritor.writerow(linha)
                mantidas += 1
    print(f"  gd: {mantidas:,} linhas  ({_mb(origem):.0f} MB -> {_mb(destino):.1f} MB)")


def recortar_parquet(nome: str, coluna: str, valor: str, saida: str) -> None:
    import pandas as pd

    origem = BRUTO / nome
    destino = DESTINO / saida
    if not origem.exists():
        print(f"  {saida}: base bruta ausente, pulando")
        return

    df = pd.read_parquet(origem)
    if coluna not in df.columns:
        print(f"  {saida}: coluna {coluna} não existe, pulando")
        return
    recorte = df[df[coluna] == valor]
    recorte.to_parquet(destino, index=False)
    print(f"  {saida}: {len(recorte):,} linhas  ({_mb(origem):.0f} MB -> {_mb(destino):.1f} MB)")


def recortar_tarifas() -> None:
    """84 MB (todas as distribuidoras, todos os anos) -> só COPEL-DIS baixa tensão."""
    origem = BRUTO / "tarifas-homologadas.csv"
    destino = DESTINO / "tarifas-copel.csv"
    if not origem.exists():
        print("  tarifas: base bruta ausente, pulando")
        return

    mantidas = 0
    with origem.open("r", encoding="utf-8", errors="replace", newline="") as fe, \
         destino.open("w", encoding="utf-8", newline="") as fs:
        leitor = csv.DictReader(fe, delimiter=";")
        escritor = csv.DictWriter(fs, fieldnames=leitor.fieldnames, delimiter=";")
        escritor.writeheader()
        for linha in leitor:
            if linha.get("SigAgente") == DISTRIBUIDORA and str(linha.get("DscSubGrupo", "")).startswith("B"):
                escritor.writerow(linha)
                mantidas += 1
    print(f"  tarifas: {mantidas:,} linhas  ({_mb(origem):.0f} MB -> {_mb(destino):.1f} MB)")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"Recortando para {MUNICIPIO} / {DISTRIBUIDORA}:")

    recortar_geracao_distribuida()
    recortar_tarifas()
    recortar_parquet("samp-2025.parquet", "SigAgenteDistribuidora", DISTRIBUIDORA,
                     "samp-copel-2025.parquet")
    recortar_parquet("ctr-curvas-carga-consumidor-tipo.parquet", "SigCcs", "COPEL",
                     "ctr-copel.parquet")
    recortar_parquet("componentes-tarifarias-2026.parquet", "SigNomeAgente", DISTRIBUIDORA,
                     "componentes-copel-2026.parquet")

    total = sum(p.stat().st_size for p in DESTINO.glob("*"))
    print(f"\ntotal do recorte: {total/1e6:.1f} MB  (em {DESTINO.relative_to(RAIZ)})")


if __name__ == "__main__":
    main()
