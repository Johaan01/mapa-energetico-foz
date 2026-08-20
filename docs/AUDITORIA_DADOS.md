# Auditoria de dados — o que é medido e o que é construído

Documento de defesa para o pitch. Regra que orienta tudo: **nenhum número aparece na
plataforma sem que se saiba de onde veio.** Abaixo, cada dado, sua origem e a resposta
honesta para a pergunta que um jurado técnico faria.

---

## 1. Dados REAIS (medidos ou publicados por órgão oficial)

| # | Dado | Fonte | Granularidade | Ressalva |
|---|---|---|---|---|
| 1 | Limite dos bairros | IBGE — malha de bairros, Censo 2022 | polígono oficial | — |
| 2 | População por bairro | IBGE — Censo 2022 | por bairro | — |
| 3 | Footprints das edificações | OpenStreetMap | por imóvel | cobertura não é 100% |
| 4 | Malha viária | OpenStreetMap | por segmento | — |
| 5 | Altura das edificações | Google Open Buildings 2.5D (Earth Engine) | 4 m de resolução | erro médio ±1,5 m |
| 6 | Subestações | OpenStreetMap `power=substation` | posição real | 7 em Foz; 5 de distribuição |
| 7 | Instalações solares (nº e potência) | ANEEL — Geração Distribuída | por município e zona de CEP | CEP com 3 dígitos mascarados |
| 8 | Consumo médio por classe | ANEEL SAMP 2025 | por distribuidora | área de concessão, não municipal |
| 9 | Energia injetada por prosumidor | ANEEL SAMP 2025 | por distribuidora | idem |
| 10 | **Formato** das curvas de 24 h | ANEEL CTR — campanhas de medição | 15 min, por consumidor tipo | medição de campo das distribuidoras |
| 11 | Perfis de consumidor tipo | ANEEL CTR | 8 residenciais, 20 comerciais (Copel) | — |
| 12 | Tarifas e componente Fio B | ANEEL — Componentes Tarifárias 2026 | B1 residencial, REH 3.592/2026 | — |
| 13 | Irradiância solar horária | NASA POWER (`ALLSKY_SFC_SW_DWN`) | horária, céu real | nebulosidade já embutida |
| 14 | Sazonalidade do consumo | ANEEL SAMP | mensal | — |
| 15 | Sazonalidade da geração | NASA POWER | mensal | — |

---

## 2. Dados CONSTRUÍDOS (estimados, sorteados ou modelados)

| # | Dado | Como é construído | Ancoragem real | Risco se errado |
|---|---|---|---|---|
| 1 | **Quais** imóveis são prosumidores | sorteio sem reposição, ponderado por área | o **total** respeita a taxa real (23,3%) | nenhum no agregado; alto no imóvel isolado |
| 2 | Qual perfil CTR cada imóvel recebe | sorteio uniforme entre os perfis medidos | o conjunto de perfis é real | distribui heterogeneidade de forma plausível |
| 3 | Curva individual de cada imóvel | formato real × nível real × ruído (±10% imóvel, ±6% hora) | formato CTR + nível SAMP | não é a medição daquela casa |
| 4 | **Posição dos transformadores** | agrupamento de ~30 imóveis por trecho de rua | quantidade plausível | **fictícia** — os reais estão em postes específicos |
| 5 | Traçado da rede | árvore radial (Dijkstra) sobre as ruas | topologia radial é como a rede real funciona | plausível, não é o cabeamento da Copel |
| 6 | Unidades consumidoras | contagem de footprints ≥ 40 m² | — | 1 prédio = 1 UC → subconta em área vertical |
| 7 | Fatia comercial (10%) | heurística | OSM não tem tag de uso confiável | afeta mix, não o total |
| 8 | Área útil | footprint × pavimentos estimados | altura real (±1,5 m) | pavimentos é arredondamento |
| 9 | Autoconsumo solar | derivado: geração − injeção | ambos ancorados no SAMP | medidor **não consegue** medir isso |
| 10 | Tributos (ICMS 19%, PIS/COFINS 9,25%) | alíquota aproximada | LC 194/2022 | cálculo real é "por dentro" e varia por faixa |
| 11 | Fração deslocável da ponta (35%) | premissa | — | afeta a economia estimada |
| 12 | **Redução de 6% por hábito** | **premissa de demonstração** | — | **não temos cliente real ainda** |

---

## 3. Validações já feitas

| Verificação | Resultado |
|---|---|
| UCs modeladas × domicílios IBGE (Vila Yolanda) | 1.689 × 1.674 → **0,9% de diferença** |
| UCs modeladas × domicílios IBGE (cidade) | 78.126 × 100.598 → razão 0,78 (causa conhecida: prédios) |
| Footprints × imagem de satélite | sobreposição conferida visualmente |
| Consumo residencial simulado × ANEEL | 174 kWh/mês × 174,1 real |
| Consumo comercial simulado × ANEEL | 582 kWh/mês × 582,2 real |
| Injeção por prosumidor × ANEEL | 11,64 kWh/dia × 11,64 real |
| Imóveis por transformador | mín. 15 / mediana 26 / máx. 45 |
| HSP de Foz (NASA POWER) × Atlas do Paraná | 4,73 × faixa estadual 4,2–4,5 |

---

## 4. Perguntas prováveis no pitch — e a resposta

**"Esses dados de consumo são reais?"**
O *volume* é: 174 kWh/mês por residência vem do mercado que a Copel declara à ANEEL. O
*formato* da curva também: vem de campanhas de medição de 15 em 15 minutos publicadas
no CTR. O que é sintético é a atribuição de uma curva específica a uma casa específica —
e isso é obrigatório, porque o dado individual é protegido por LGPD.

**"Vocês sabem quais casas têm painel solar?"**
Não, e não afirmamos que sabemos. Sabemos **quantas** têm, por dado da ANEEL, e
distribuímos essa quantidade ponderando por área de telhado. Tentamos detecção por
visão computacional e descartamos com o motivo documentado — a resolução disponível não
sustenta a afirmação.

**"Esses transformadores estão onde os da Copel estão?"**
Não. A posição é estimada por agrupamento de ~30 imóveis ao longo da rua, que é a faixa
real de atendimento de um trafo de poste. A Copel não publica o cadastro. As
**subestações**, essas sim, estão na posição real — vêm do OpenStreetMap.

**"Como vocês medem o autoconsumo se o medidor não vê isso?"**
Reconhecemos que não vê: a energia gerada e consumida no mesmo instante nunca atravessa
o medidor. No modelo, o autoconsumo é derivado (geração menos injeção), com os dois
extremos ancorados em medição da ANEEL. Para medir de fato seria preciso telemetria do
inversor ou um segundo clamp no circuito fotovoltaico — está no roadmap de hardware.

**"A economia de 6% é comprovada?"**
Não. É premissa de demonstração e está marcada como tal no código e na interface. O que
é comprovado é o *método* de apuração: separamos o efeito do reajuste tarifário do
efeito de mudança de hábito, e a taxa incide só sobre o segundo.

**"Por que a razão UCs/domicílios cai para 0,78 na cidade?"**
Porque contamos uma unidade consumidora por footprint, e no Centro um prédio com
dezenas de apartamentos entra como uma só. Em bairro horizontal, que é o caso de Vila
Yolanda, a razão é 1,01. O modelo é preciso onde foi projetado para atuar e subconta em
área verticalizada — e isso está declarado, não escondido.

**"De onde vem a tarifa?"**
Componentes Tarifárias da ANEEL, REH 3.592/2026, COPEL-DIS, B1 residencial subclasse
"Residencial". Atenção à subclasse: B1 tem Baixa Renda e Tarifa Social com valores
menores, e usar a errada subestima a conta em cerca de 30%.
