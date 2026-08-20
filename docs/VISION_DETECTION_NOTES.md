# Detecção visual de painéis solares — conclusão

## O que foi tentado

1. **Gemma 3 4B, prompt descritivo** (descreve como um painel se parece antes de perguntar): **31/31 = SIM**. Viés sistemático confirmado (probabilidade de ocorrer por acaso, se a taxa real fosse ~20%, é de ~0,0000000163%). Conferi visualmente algumas imagens marcadas "SIM" — nenhuma tinha painel visível.

2. **Gemma 3 4B, prompt neutro + few-shot com 2 exemplos negativos** (não achamos um exemplo positivo real dentro do orçamento de tempo): **10 SIM / 21 NAO** em 29 casos reais (excluindo os 2 usados como exemplo). Taxa agregada ficou plausível (~34%, perto da faixa real de ~20-23%), mas ao conferir visualmente 2 dos "SIM", nenhum mostrava painel — a melhora no agregado não veio acompanhada de confiança na precisão por imóvel.

3. **Gemma 3 12B, mesmo prompt neutro + few-shot**: **0/31 = NAO** (universal, oposto exato do item 1). Rodando em GPU (RTX 2060, 100% GPU confirmado via `ollama ps`) sem erro de hardware.

## Diagnóstico

O problema não é tamanho de modelo — é a ausência de um exemplo POSITIVO real e confirmado para ancorar o few-shot. Com only exemplos negativos, o modelo (de qualquer tamanho) tende a ancorar na direção do que foi mostrado como referência, e cada configuração produziu um viés sistemático diferente, não uma classificação real caso a caso. Ademais, a resolução dos recortes (tiles do ESRI World Imagery, zoom 19, ~0,3m/pixel efetivo) é baixa o suficiente para que mesmo inspeção humana seja incerta em vários casos — reconhecido pelo próprio usuário ao revisar os crops em `solar_crops/`.

## Decisão

**Não usar como fonte de dado do dashboard.** A atribuição de perfil `prosumidor` continua vindo exclusivamente do sorteio calibrado pela taxa real da ANEEL/IBGE (23,3%, ponderado por área do telhado) em `simulate_data.py` — esse mecanismo não muda.

Isso fica documentado como tentativa real e honesta pro pitch: testamos 3 configurações diferentes, diagnosticamos a causa raiz (falta de dataset rotulado com exemplos positivos confirmados — nenhum disponível publicamente e não haveria tempo hábil pra rotular manualmente um dataset de treino), e paramos aqui em vez de forçar uma feature que não é confiável. Roadmap futuro: com acesso a um dataset rotulado real (ex.: parceria com uma distribuidora que já tenha essa informação), a mesma pipeline de recorte (`detect_solar_panels.py`) poderia alimentar um classificador de verdade.

## Arquivos relevantes

- `simulation/detect_solar_panels.py` — pipeline completo (recorte via ESRI World Imagery + classificação via Ollama), com suporte a `--few-shot` e `--model`.
- `simulation/solar_crops/` — recortes reais baixados (cluster 0, 31 imóveis).
- `simulation/solar_detection_results*.json` — resultados de cada configuração testada.
