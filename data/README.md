# data/

As bases oficiais brutas (~1,8 GB) são baixadas para `aneel/` e `ibge/` e não vão para
o repositório (veja o `.gitignore` na raiz). O que fica versionado aqui:

| Pasta | Conteúdo |
|---|---|
| `recorte/` | Só as linhas de Foz do Iguaçu / COPEL-DIS de cada base da ANEEL, geradas por `pipeline/enxugar_dados.py`. É o que mantém o projeto reproduzível sem rebaixar as bases inteiras. |
| `aneel/`, `ibge/`, `gee/` | Scripts da fase de exploração, quando o projeto ainda olhava só para a Vila Yolanda, e o que eles produziram (`*.geojson`, `vila_yolanda_stats.json`). Não fazem parte do pipeline atual; alguns citam o `simulate_data.py` e a pasta `simulation/` da primeira versão, que não existem mais. |
