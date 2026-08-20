"""Agrega estatisticas REAIS (sem nenhuma simulacao) da base aberta da ANEEL para o
bairro-alvo, usando o prefixo de CEP como proxy de zona geografica (os 3 ultimos
digitos do CEP sao mascarados pela propria ANEEL por privacidade, entao a resolucao
maxima que temos e "zona", nao endereco).

Essas estatisticas alimentam os KPIs reais do zoom macro do dashboard (contagem de
instalacoes, potencia instalada total, evolucao por ano de atualizacao cadastral).
Nao confundir com o simulate_data.py, que gera as curvas horarias SINTETICAS por
imovel a partir da taxa de adesao calibrada por este mesmo dataset.
"""
import csv
import json
from collections import Counter
from pathlib import Path

CSV_PATH = Path(__file__).parent / "empreendimento-geracao-distribuida.csv"
OUTPUT_PATH = Path(__file__).parent / "vila_yolanda_stats.json"

CEP_PREFIX = "85853"
MUNICIPIO = "Foz do Iguaçu"
UF = "PR"
CLASSE = "Residencial"
FONTE = "UFV"

count = 0
potencia_total_kw = 0.0
por_ano = Counter()

with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        if row.get("SigTipoGeracao") != FONTE:
            continue
        if row.get("SigUF") != UF or row.get("NomMunicipio") != MUNICIPIO:
            continue
        if row.get("DscClasseConsumo") != CLASSE:
            continue

        cep = row.get("CodCEP", "").strip()
        if not cep.startswith(CEP_PREFIX):
            continue

        count += 1

        pot_raw = row.get("MdaPotenciaInstaladaKW", "").replace(",", ".")
        try:
            potencia_total_kw += float(pot_raw)
        except ValueError:
            pass

        # Nao existe campo de "data de conexao" isolado no export atual; usamos a
        # atualizacao cadastral como proxy aproximada de quando o registro passou a existir.
        atualizacao = row.get("DthAtualizaCadastralEmpreend", "")
        ano = atualizacao[:4] if len(atualizacao) >= 4 else "desconhecido"
        por_ano[ano] += 1

stats = {
    "bairro": "Vila Yolanda",
    "municipio": MUNICIPIO,
    "uf": UF,
    "cep_prefix": CEP_PREFIX,
    "observacao_cep": "Prefixo de 5 digitos; os 3 digitos finais do CEP sao mascarados pela ANEEL, entao a zona pode extrapolar levemente o perimetro exato do bairro.",
    "fonte": "ANEEL - dadosabertos.aneel.gov.br - empreendimento-geracao-distribuida.csv",
    "registros_residenciais_ufv": count,
    "potencia_instalada_total_kw": round(potencia_total_kw, 2),
    "potencia_media_kw": round(potencia_total_kw / count, 2) if count else 0,
    "registros_por_ano_atualizacao_cadastral": dict(sorted(por_ano.items())),
}

OUTPUT_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(stats, ensure_ascii=False, indent=2))
