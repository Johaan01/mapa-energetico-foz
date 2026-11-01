# Mapa energético de Foz do Iguaçu

Plataforma de análise da rede de distribuição de Foz do Iguaçu (PR). Mapeia o
comportamento energético de cada bairro sobre uma **rede elétrica plausível, traçada
sobre as ruas reais**, mostrando como cada grupo de imóveis pesa sobre a rede ao longo
das 24 h do dia, com agregação suficiente para respeitar a LGPD.

**Ver o protótipo:** <https://johaan01.github.io/mapa-energetico-foz/>

> **Protótipo de hackathon.** Desenvolvido no 1º Hackathon de Transição Energética do
> Itaipu Parquetec (Tema 3 — Consumidores e prosumidores). Foi construído com dados
> públicos e estatísticos (IBGE, ANEEL, OpenStreetMap, NASA POWER), sem acesso a
> medição individual: as curvas de consumo de cada imóvel, a posição dos
> transformadores e o traçado da rede são simulados, calibrados por médias oficiais.
> Não é um produto, não usa dados internos da distribuidora e não serve para decisões
> sobre a rede real. As [limitações declaradas](#limitações-declaradas) detalham até
> onde ele vai.

---

## Princípio que orienta tudo

**O dado individual de consumo é fechado; a geografia e a estatística agregada não são.**

Então: toda geometria é real (footprints, ruas, limites de bairro, população), e só a
curva de consumo por imóvel é sintética — com amplitude e proporções calibradas por
dados abertos oficiais. Nenhum número foi inventado para "ficar bonito"; onde não há
dado, isso está dito explicitamente.

---

## Fontes de dados

| Camada | Fonte | Natureza |
|---|---|---|
| Limite dos bairros | IBGE, malha de bairros do Censo 2022 (`PR_bairros_CD2022`) | Real |
| População por bairro | IBGE, Censo 2022 (`Populacao_residente_por_bairros`) | Real |
| Footprints das edificações | OpenStreetMap (via `osmnx`) | Real |
| Altura das edificações | Google Open Buildings 2.5D Temporal (Earth Engine) | Real (±1,5 m) |
| Malha viária | OpenStreetMap (via `osmnx`) | Real |
| Instalações solares (UFV) | ANEEL, dados abertos de Geração Distribuída | Real, agregado por CEP |
| Consumo médio por classe | ANEEL SAMP 2025 (COPEL-DIS) | Real, por área de concessão |
| Formato das curvas de 24 h | ANEEL CTR (campanhas de medição, 15 min) | Real, por consumidor tipo |
| Tarifas e Fio B | ANEEL Componentes Tarifárias 2026 | Real, homologado |
| Energia injetada por prosumidor | ANEEL SAMP 2025 (COPEL-DIS) | Real, por área de concessão |
| Subestações | OpenStreetMap (`power=substation`) | Real |
| Curva de consumo por imóvel | Simulação | **Sintético**, calibrado |
| Posição dos transformadores | Agrupamento por trecho de rua | **Sintético** |
| Traçado da rede | Derivado da malha viária | **Sintético**, plausível |

### Por que OpenStreetMap e não Google Open Buildings

Comparação feita na mesma área (Vila Yolanda, polígono oficial do IBGE):

| | OSM | Open Buildings v3 |
|---|---|---|
| Contagem | 1.788 | 2.017 (após filtros) |
| Fragmentação (mesma casa em 2+ polígonos) | 0 pares detectados | problema visível |
| Área mediana | 144,8 m² (plausível) | — |
| Aderência ao telhado real | fiel | aproximada |

O OSM venceu em fidelidade de contorno. A altura, que o OSM praticamente não tem
(8 de 1.788 edificações com `building:levels`), vem do raster do Google — é o híbrido
que usamos.

### Calibração da taxa de prosumidores (23,3 %)

O CEP nos registros da ANEEL vem com os **3 últimos dígitos mascarados** por
privacidade, então o numerador só é válido na granularidade da *zona de CEP*, nunca do
bairro administrativo. Amostrando 100 sufixos da zona `85853` no ViaCEP, descobrimos
que ela cobre **6 bairros oficiais** (Yolanda 59 % das respostas, São Roque, Bourbon,
Remanso, Mata Verde, Cataratas).

```
numerador   = 1.364 UCs residenciais com UFV na zona 85853        (ANEEL)
denominador = 16.541 hab nos 6 bairros ÷ 2,82 hab/domicílio       (IBGE Censo 2022)
            = 5.866 domicílios
taxa        = 1.364 / 5.866 = 23,3 %
```

Numerador e denominador descrevem a **mesma geografia** — esse é o ponto. Dividir os
1.364 da zona inteira pelos imóveis de um bairro só dava 81 %, valor impossível.

---

### Calibração do consumo (ANEEL SAMP)

A amplitude das curvas não é arbitrada. O SAMP publica energia faturada e número de
consumidores no mesmo recorte, o que dá a média real por unidade consumidora da
COPEL-DIS:

```
Residencial : 174,1 kWh/mês  ->  5,73 kWh/dia
Comercial   : 582,2 kWh/mês  -> 19,15 kWh/dia
Injeção GD  : 353,9 kWh/mês  -> 11,64 kWh/dia   (313.341 UCs residenciais com GD)
```

Antes desse ancoramento o modelo gerava **1.351 kWh/mês por residência — 7,8× acima do
real**. A área do imóvel continua modulando a diferença entre casas; o que mudou é que
a média do conjunto agora bate com o mercado declarado à ANEEL.

Detalhe que importa: `Energia Injetada` é apenas o **excedente exportado**, não a
geração bruta — o autoconsumo diurno abate parte da geração antes de sobrar excedente.
Por isso a geração é escalada por bissecção até que a soma das horas de saldo negativo
resulte em 11,64 kWh/dia, em vez de simplesmente calibrar a geração total.

Use `python pipeline/verificar_calibracao.py` para conferir que as curvas geradas ainda
batem com esses alvos.

> Ressalva: o SAMP é por **área de concessão** (Copel inteira), não por município.

## Topologia da rede

Uma rede de distribuição real é **radial, mas corre sobre as ruas**:

```
subestação ──(alimentador sobre a rua)──> transformador ──(ramal)──> imóvel
```

1. Grafo viário do OSM, projetado em UTM 22S.
2. Subestação = a **real** mais próxima, do OSM (`power=substation`). Foz do Iguaçu tem
   7 mapeadas, entre elas a *Subestação Vila Yolanda* (Copel, 138 kV). Como a
   subestação costuma ficar fora do bairro que alimenta, o alimentador entra pelo nó
   viário mais próximo dela. Sem subestação mapeada por perto, cai num nó estimado —
   e o `substation.geojson` diz qual dos dois casos ocorreu.
3. Árvore radial = caminhos mínimos (Dijkstra) — sem malha, sem anel, como um alimentador.
4. Cada imóvel projetado na aresta viária mais próxima; o ramal é o segmento curto
   perpendicular até a fachada.
5. Transformadores: imóveis do mesmo trecho de rua, ordenados ao longo da via e
   agrupados em lotes de ~30 (faixa real de um trafo de poste, e que coincide com o
   piso de agregação que a LGPD nos exige).
6. Carga de cada trecho = soma das curvas dos imóveis cujo caminho até a subestação
   passa por ele. Avenida troncal fica carregada, rua sem saída fica leve.

**Isto não é o cabeamento da Copel** — esse dado não é público. É uma topologia
plausível derivada da geografia real, e está rotulada como tal na interface.

As posições dos transformadores também são **fictícias**: os reais estão em postes
específicos, e a Copel não publica esse cadastro. O agrupamento por trecho de rua é
estatisticamente razoável, mas não aponta equipamento existente.

## Níveis de acesso (LGPD)

O dado individual é o eixo da LGPD aqui, então o nível de acesso governa o que aparece
no mapa — e a trava vale também no clique, não só na visibilidade da camada:

| Perfil | Vê imóvel a imóvel? | O que enxerga |
|---|---|---|
| Público (livre) | não | agregado por transformador (piso de 15 imóveis) |
| Consumidor / prosumidor | só a própria UC | sua UC em detalhe; o resto agregado |
| Distribuidora (Copel) | sim | imóvel a imóvel — é a detentora do dado |
| Comercializadora | não | clusters estatísticos por perfil |

O seletor fica no topo do dashboard, e trocar de perfil muda o mapa ao vivo — o
contraste entre "Público" e "Distribuidora" demonstra a proteção em vez de prometê-la.

## As duas telas

**Tela 1 — o mapa.** Cidade inteira → bairro → imóvel, com o slider de 24 h e os
níveis de acesso acima.

**Tela 2 — a unidade consumidora.** Abre ao clicar num imóvel (respeitando o nível de
acesso). Traduz a curva daquela UC em dinheiro, usando **tarifas homologadas reais**:

| Item | Valor real usado |
|---|---|
| TE + TUSD (B1 residencial) | 310,85 + 457,17 = 768,02 R$/MWh |
| Com tributos | ≈ R$ 1,07/kWh |
| TUSD Fio B | 214,54 R$/MWh, cobrado a **60 %** em 2026 |
| Tarifa vigente há 1 ano | 642,42 R$/MWh (alta real de **19,6 %**) |

Fonte: ANEEL, Componentes Tarifárias 2026 (REH 3.592/2026, COPEL-DIS), e Lei
14.300/2022 para o escalonamento do Fio B.

⚠️ **Cuidado com a subclasse B1**: ela tem várias (Baixa Renda, Tarifa Social, Desconto
Social). A residencial "cheia" é `DscSubClasseConsumidor == 'Residencial'` (TUSD 457,17);
filtrar só por classe pega Baixa Renda (TUSD 308,43) e subestima a conta em ~30 %.

### O modelo de receita fica auditável

O contrato é participativo — a plataforma fica com um percentual da economia. Isso só
funciona se a variação da conta for **decomposta**, porque três coisas mudam a conta ao
longo do ano e duas delas não têm nada a ver com o serviço:

```
Δtarifa  = consumo_do_ano_passado × (tarifa_hoje − tarifa_de_então)     ← reajuste
Δconsumo = (consumo_hoje − consumo_do_ano_passado) × tarifa_hoje        ← hábito
```

A taxa incide **apenas sobre Δconsumo negativo**. Cada peça vem de medição:

| Componente | Fonte real |
|---|---|
| Sazonalidade do consumo | ANEEL SAMP — kWh por UC, mês a mês (fev/mar 1,16 × mai/jun 0,92) |
| Sazonalidade da geração | NASA POWER — HSP mensal (jan 1,44 × jul 0,61, fator 2,4×) |
| Tarifa de cada mês | ANEEL — vigências homologadas |

Por que isso importa na prática: em julho de 2026 a tarifa da Copel subiu **19,6 %**
(642,42 → 768,02 R$/MWh). Num contrato ingênuo de "economia contra o ano passado", um
cliente que não mudou nada apareceria com economia *negativa* — e a plataforma não
receberia apesar de ter entregue valor. No sentido inverso, num mês de tarifa em queda
receberia sem ter feito nada. A decomposição resolve os dois casos.

O painel mostra os 12 meses lado a lado (ano passado × este ano), no mesmo formato do
gráfico de histórico que já vem na fatura da Copel — o cliente não precisa aprender a
ler nada novo.

### Estimado vs medido no painel

Cada KPI carrega um selo (`est.`, `IBGE`, `sim.`) e um tooltip com a procedência, porque
um número como "imóveis modelados" é ambíguo sem isso — ele é a **contagem de footprints
do OSM com área ≥ 40 m²**, não o cadastro da Copel e não `população ÷ 2,82`. Cada
`meta.json` traz um bloco `procedencia` separando o que é real medido do que é estimado.

---

## Resultado — Foz do Iguaçu completa

Os 37 bairros do município foram processados (0 falhas):

| | |
|---|---|
| Bairros | 37 |
| Construções (OSM) | 85.021 |
| Unidades consumidoras modeladas | 78.126 |
| Transformadores | 2.950 |
| Prosumidores modelados | 16.440 (21,0 %) |
| População (Censo 2022) | 283.687 |

Carga da cidade ao longo do dia, com o consumo já calibrado:

| Hora | Carga líquida |
|---|---|
| 12 h | **−19,2 MWh** (a geração distribuída inverte o fluxo) |
| 19 h | **+45,6 MWh** (pico) |
| Dia | 321,7 MWh |

## Validação

| Verificação | Resultado |
|---|---|
| UCs modeladas × domicílios IBGE (Vila Yolanda) | 1.689 × 1.674 → **0,9 % de diferença** |
| UCs modeladas × domicílios IBGE (cidade inteira) | 78.126 × 100.598 → **razão 0,78** |
| Footprints × imagem de satélite | sobreposição conferida (`pipeline/validar_footprints.py`) |
| Imóveis por transformador (Vila Yolanda) | mín. 15 / mediana 26 / máx. 45 |
| Grafo viário conectado (Vila Yolanda) | 1 componente, 189 nós, 48,6 km |

A razão cai de 1,01 em Vila Yolanda para 0,78 na cidade inteira, e a causa é conhecida:
contamos **uma unidade consumidora por footprint**, então no Centro um prédio com
dezenas de apartamentos entra como uma UC só; some-se a isso a cobertura menor do OSM
na periferia. O modelo é preciso em bairro horizontal — que foi exatamente o critério
de escolha de Vila Yolanda — e subconta em área verticalizada. A altura já é usada para
escalar o consumo (área útil = footprint × pavimentos), mas não para multiplicar a
contagem de UCs.

---

## Estrutura

```
pipeline/
  bairros.py              limites e população oficiais (IBGE)
  cache_osm.py            baixa o município inteiro do OSM uma vez (ver abaixo)
  osm_util.py             retry/backoff e espelhos da Overpass
  buildings.py            footprints do OSM + altura do Earth Engine
  simulate.py             curvas de 24 h calibradas
  grid.py                 rede radial sobre a malha viária
  aneel_municipio.py      KPIs reais de geração distribuída (ANEEL)
  consumo_real.py         consumo médio real por classe (ANEEL SAMP)
  curvas_reais.py         formato das curvas medidas (ANEEL CTR)
  irradiancia.py          perfil solar real de Foz do Iguaçu (NASA POWER)
  sazonalidade.py         consumo, geração e tarifa mês a mês
  perfis_consumidor.py    caracteriza os perfis medidos (Tema 3)
  tarifas_copel.py        tarifas homologadas e Fio B (ANEEL)
  verificar_calibracao.py confere as curvas contra os alvos reais
  subestacoes.py          subestações reais do OSM
  run_bairro.py           orquestrador  →  python run_bairro.py --todos
  resumo_cidade.py        camada macro: todos os trafos e bairros num arquivo leve
  validar_footprints.py   prova visual footprint × satélite
web/
  index.html style.css app.js     dashboard (MapLibre GL, estático)
  data/municipio.json             KPIs reais da ANEEL
  data/resumo_*.geojson           visão macro da cidade (~1,6 MB)
  data/bairros/<slug>/            camadas por bairro (~2 MB cada)
data/
  recorte/                        recorte das bases da ANEEL usado pelo pipeline
  ibge/  aneel/  gee/             fontes brutas e scripts da fase de exploração
                                  (ver data/README.md)
```

### Armadilha do osmnx que custou horas (documentada para não repetir)

O `osmnx` resolve o host da Overpass e **fixa aquele IP** em `socket.getaddrinfo`, para
que a checagem de status e a consulta caiam na mesma máquina do balanceador. O efeito
colateral: se o IP sorteado estiver inacessível a partir da sua rede, **tudo** vira
`ConnectTimeout` — inclusive consultas que funcionam perfeitamente por outro caminho.
Aqui ele grudou em `65.109.112.52` (morto desta rede) enquanto `162.55.144.139`, do
mesmo hostname, respondia em 4 s. Sintoma enganoso: `requests.get` no `/status`
funcionava, e só o osmnx falhava.

Além disso, `ox.settings.overpass_rate_limit = True` faz o osmnx **dormir em silêncio**
esperando slot — sem log, sem conexão aberta, indistinguível de travamento.

Ambos estão neutralizados em `osm_util.configurar()`. Depois disso, a mesma consulta
que travava indefinidamente passou a levar 8 s.

### Cache do OSM — por que existe

Consultar a Overpass por bairro dá **74 consultas** (edificações + malha viária) num
serviço público com limite de requisições. Na prática o lote trava esperando slot — foi
exatamente o que aconteceu aqui, com `ConnectTimeout` a partir do quarto bairro.

Solução: **duas consultas no total**. `cache_osm.py` baixa todas as edificações e toda a
malha viária do município de uma vez para `data/osm_cache/`, e cada bairro vira um
recorte local com índice espacial — sem rede, rápido e reprodutível. Sem o cache, os
módulos voltam sozinhos a consultar a Overpass por bairro (com retry e espelhos).

### Rodar

```bash
cd pipeline
python cache_osm.py                 # uma vez: baixa o município inteiro
python run_bairro.py Yolanda        # um bairro
python run_bairro.py --todos        # todos os 37 bairros de Foz
python run_bairro.py --todos --retomar      # continua de onde parou
python run_bairro.py --todos --sem-altura   # pula o Earth Engine (mais rápido)
python resumo_cidade.py             # ao final: camada macro da cidade
```

`--retomar` é consciente de versão: só pula bairros já gravados na `VERSAO_SAIDA`
atual. Ao mudar a calibração, basta subir a versão para que um lote interrompido não
deixe bairros com dado velho sem ninguém perceber.

### Rodar o dashboard

Na raiz do projeto:

```powershell
.\rodar.ps1
```

Abre o navegador e imprime também o endereço para acessar **pelo celular** na mesma
rede wifi (ex.: `http://192.168.0.15:8765`) — serve para ensaiar no aparelho de verdade.

Equivalente manual:

```bash
cd web && python -m http.server 8765
```

Não abra o `index.html` com duplo clique: o navegador bloqueia `fetch` em `file://`
e o mapa fica vazio. Precisa ser servido por HTTP.

### Dados: bruto vs recorte

As bases oficiais somam **~1,8 GB** (o CSV de geração distribuída da ANEEL sozinho tem
1,46 GB, com o Brasil inteiro). Isso não vai para o repositório.

`pipeline/enxugar_dados.py` extrai só o recorte de Foz do Iguaçu / COPEL-DIS:

| Base | Bruto | Recorte |
|---|---|---|
| Geração distribuída | 1.531 MB | 5,8 MB |
| Tarifas homologadas | 88 MB | 0,4 MB |
| SAMP (mercado) | 13 MB | 0,4 MB |
| CTR (curvas medidas) | 33 MB | 0,6 MB |
| Componentes tarifárias | 4 MB | 0,2 MB |
| **Total** | **~1,8 GB** | **7,4 MB** |

O recorte é versionado, então quem clona o projeto consegue rodar o pipeline sem
rebaixar nada. O recorte de geração distribuída sai sem as colunas `NumCPFCNPJ` e
`NomTitularEmpreendimento`: a ANEEL já as publica mascaradas, e o projeto não usa
nenhuma das duas.

### Publicar

O site é estático, então qualquer hospedagem serve. `web/` tem ~86 MB (comprimido no
transporte fica bem menos, GeoJSON gzipa muito bem).

- **Netlify Drop** (`app.netlify.com/drop`) — arrasta a pasta `web/` no navegador e sai
  a URL. Não precisa instalar nada nem ter conta.
- **GitHub Pages** — o workflow em `.github/workflows/deploy.yml` publica `web/` a cada
  push na `main`, em <https://johaan01.github.io/mapa-energetico-foz/>. O Pages precisa estar com
  *GitHub Actions* como origem nas configurações do repositório (já está).

O dashboard é **estático** — nenhum backend. Publicável em GitHub Pages / Netlify, o
que também resolve o acesso pelo celular durante a apresentação.

---

## Perfis de consumo — o núcleo do Tema 3

Os perfis não são inventados. A ANEEL publica no CTR as curvas de consumidores tipo
levantadas em campanhas de medição das próprias distribuidoras. Para a Copel são
**8 perfis residenciais e 20 comerciais**, cada um com silhueta própria — e caracterizá-los
é exatamente o que o Tema 3 pede.

`pipeline/perfis_consumidor.py` mede cada curva e a classifica por indicadores de
engenharia (fator de carga, hora do pico, % na ponta, % na janela solar):

| Arquétipo residencial | Qtd. | Oportunidade |
|---|---|---|
| Pico noturno | 4 | maior potencial de deslocamento — e o que mais pesa no trafo |
| Diurno | 2 | aproveita a geração solar sem bateria |
| Constante | 1 | ganho vem de eficiência, não de deslocamento |
| Matinal | 1 | já está fora da ponta; foco no chuveiro |

**Isso muda a métrica de cobrança.** O fator de carga varia de 0,231 a 0,796 entre os
perfis residenciais medidos — um fator de 3,4×. O perfil CT-036 (fator 0,231, 32,2 % na
ponta) tem o dobro de carga deslocável do CT-038 (fator 0,796, 15,0 %). Cobrar um
percentual uniforme ignoraria que o potencial de economia é estruturalmente diferente
entre eles.

## Auditoria de dados

O que é medido e o que é construído está detalhado em
[`docs/AUDITORIA_DADOS.md`](docs/AUDITORIA_DADOS.md), com as validações feitas e as
respostas para as perguntas prováveis da apresentação no hackathon.

## Limitações declaradas

Registradas de propósito: um protótipo feito com dados estatísticos só é útil se
deixar claro onde ele para de valer.

- **Curvas de consumo são sintéticas.** A *média* do conjunto é calibrada no consumo
  real da ANEEL (SAMP/Copel), mas o formato da curva ao longo do dia e a variação entre
  imóveis são modelados, não medidos. Não temos acesso a medidor: a Copel expõe consumo
  agregado, não curva horária por UC.
- **O consumo real é por área de concessão**, não por município — aplicamos a média da
  Copel inteira a Foz do Iguaçu.
- **A topologia da rede não é a da Copel.** É derivada das ruas; a real não é pública.
- **A taxa de 23,3 % é da zona de CEP, não do bairro.** Aplicada uniformemente aos
  bairros por falta de granularidade oficial melhor.
- **Quais casas têm painel solar é sorteio**, ponderado por área — não detecção. A
  tentativa de detectar por visão computacional foi feita e descartada com motivo
  documentado em [`docs/VISION_DETECTION_NOTES.md`](docs/VISION_DETECTION_NOTES.md).
- **Cobertura do OSM não é 100 %.** Algumas construções reais não estão mapeadas.
- **Altura tem ~1,5 m de erro médio** (raster de 4 m), então o número de pavimentos é
  estimativa. Por isso altura nunca exclui um imóvel — só escala o consumo.

## Próximos passos (não implementados)

- Crosswalk CEP ↔ bairro para taxa de adesão por bairro (exige base dos Correios, paga).
- Detecção de UFV por visão computacional com dataset rotulado real.
- Ingestão de medição real via ESP32 + CI de metrologia (PZEM-004T / ADE7953), medindo
  potência ativa e fator de potência — não apenas corrente.

## Licença

O código está sob a licença [MIT](LICENSE). Os dados de terceiros seguem as licenças
das próprias fontes (veja [Fontes de dados](#fontes-de-dados)); em particular, os
contornos das edificações, as ruas e as subestações vêm do OpenStreetMap
(© colaboradores do OpenStreetMap, licença ODbL).
