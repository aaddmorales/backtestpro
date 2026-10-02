# Seleção de oportunidades em M15, M30 e H1 (C27R19, 03/out/2026)

Estado: **fase 1 pronta em modo observar**. A seleção lê, avalia, escolhe e explica; não emite decisão, comando nem ordem. A ligação da escolha com a execução (fase 2) está descrita no item 6 e ainda não foi feita.

## 1. Inventário: o que existia, o que faltava, o que foi feito

| componente | onde | como funciona hoje | lacuna | ação |
|---|---|---|---|---|
| Motor dos Ciclos | `motor_ciclos/bt_ciclo_v1.py` (congelado, 2.4) | lê 7 TFs do espelho; réguas por TF (pivôs, compressão, caixa, exaustão) são genéricas; a composição (topdown, escada, janela 10→15, fases, estado único) tem **M15 fixo no código** | não existe contrato para operar em M30 ou H1 | reutilizado sem alteração; a leitura por TF vai para a seleção |
| Escada, janela, fases | `bt_ciclo_v1.py` l.362–388, 562–616 | M1→M5→M15, janela de M1 dentro da M15, fases 1–3 | só existem na escala M15 | exibidas no grupo M15; não foram replicadas em M30/H1 |
| Cards do Professor | `motor_ciclos/professor_cards_v19.py` (cards 2.0) | 13 cards geram sinal em barra fechada de qualquer TF ≥ M15 | rodavam só no laboratório e no `bt_vivo_sombra` | **reutilizados**: o leitor 1.3 roda os 13 cards em M15, M30 e H1 |
| Resolução de entrada | `professor_bloco2.resolver_entradas` | entrada no relógio do M15, stop = pivô do M15 ∓ 0,3×ATR14, blindagens e corte do Ciclo | idem | **reutilizada** sem alteração |
| Seletor (pilha) | `professor_bloco2.rodar_seletor` | escolhe células card × TF com selo, por PF, com pilha protegida de até 5 | depende do pacote de estudo em arquivo, que não está no repositório | regra de ordenação (maior PF) e régua do selo reutilizadas na API; a pilha não roda |
| Bloco 3 (mapa por cenário) | `professor_bloco3.py` | PF por alinhamento × sessão | depende de `mapa_congelado`, ausente | não usado |
| Detector da plataforma | `api.py` `_detectar_oportunidade` | deveria gerar a oportunidade a cada snapshot | **nunca dispara**: é chamado com `fatos` vazio, então nenhum cenário de direção é reconhecido | não usado como produtor; ver item 6 |
| Radar | `api.py` `/radar/*` | análise pós-backtest e chat | não seleciona estratégia × ativo × TF para operar | não usado |
| Estudos | `estudo_biblioteca_v2` | métricas por card × TF × ativo | sem resultado por regime; medido com cards 1.9 | referência do candidato; BTCUSD copiado para a homologação |
| R-CICLO-01 | `api.py` `_r01_*`, `ciclo_decisoes`, RPC | decisão só na barra M15, validade 900 s | sem campo de TF nem de estratégia | intocado; aparece como "configuração atual" ao lado do contrato proposto |
| Canal de comando | conector hml9 + EA | transporta comando até o EA | testado só na bancada | intocado |
| Gestão de posição | `api.py` `_protetor_posicao` | guardião, breakeven, perseguição | não sabe qual card abriu a posição | pendente para a fase 2 |
| BabyMachine | `app.html` `clmRender` | mostrava só a cadeia do atestado | não mostrava candidatos | novo quadro "Seleção de oportunidades" |
| Persistência | `ciclo_leituras`, `ciclo_trilha` | uma linha por barra M15 | sem lugar para a avaliação | nova tabela `selecao_avaliacoes` e etapa `selecao` na trilha |

## 2. Percurso implementado (observar)

```
espelho do MT5 (PC) → leitor 1.3: cards 2.0 + resolver_entradas em M15, M30 e H1
  → candidatos.json na pasta da barra → conector hml10 (3 primeiros snapshots da barra)
  → API: portões → ordenação → escolha → selecao_avaliacoes (1 por barra) + trilha
  → BabyMachine + JSON exportado → acompanhamento de 8 barras
```

Os candidatos são telemetria **não assinada**. Só o atestado do motor é assinado. Por isso a seleção não pode autorizar nada nesta fase.

## 3. Contratos por timeframe

O que existe no código do Professor vale igual para os três TFs:

| item | regra existente | origem |
|---|---|---|
| Barra de referência | última barra **fechada** do TF do card | `professor_cards` |
| Entrada | "fechamento": abertura da barra seguinte; "gatilho": só com continuidade além do nível | `resolver_entradas` |
| Stop | último pivô do **M15** ∓ 0,3 × ATR14 do M15, mesmo para card de M30 ou H1 | `resolver_entradas` |
| Saída | 100% pelo Ciclo no relógio do M15, sem alvo fixo | `simular_card` |
| Frescor para entrada nova | até 1 barra M15 depois da entrada resolvida | `IDADE_MAX` do `bt_vivo_sombra` |
| Validade na fila | 4 barras do TF do card (M15: 1 h; M30: 2 h; H1: 4 h) | `VALIDADE_FILA_TF` |
| Elegibilidade pelo estudo | célula com selo: trades ≥ 30, PF > 1 e PF > 1 nas duas metades | `carregar_lista` |
| Ordenação | maior PF do estudo | `DESEMPATE = "pf"` |
| Custo | spread até o limite do ativo | `SPREAD_LIM` |
| Preço | desvio máximo entre preço e entrada; stop não violado | `DESVIO_MAX_PTS` |

Lacunas, com a proposta que está rodando em observação (`sel-1`):

| lacuna | proposta | estado |
|---|---|---|
| Ciclo na escala do card (M30, H1) | card de continuação: o canal EMA20 **do TF do card** não pode estar contra o lado; card de reversão: o canal é contexto | proposto, em observação |
| Autoridade de D1/H4 | contexto (a favor, contra, lateral) em vez de veto; contratendência reduz o risco à metade quando houver execução | proposto, em observação |
| Custo frente ao stop | spread ≤ 25% do risco | proposto, em observação |
| Repetição | um sinal já escolhido não é escolhido de novo | proposto, em observação |
| Escada/janela/fases em M30 e H1 | **não replicado**. O motor só tem essas regras para M15 | em aberto: precisa de definição sua |
| Risco/retorno | o contrato do estudo não tem alvo; a barreira contrária mais próxima é informada em R | informativo |

## 4. Portões (obrigatórios) e pontuação (ordenação)

1. integridade dos dados (motor ok, atestado verificado, candidatos da mesma barra e do mesmo ativo);
2. sinal confirmado pelo contrato do card;
3. frescor do sinal;
4. corte do Ciclo contra o lado no M15;
5. célula com selo no estudo;
6. Ciclo na escala do card (proposto);
7. custo;
8. preço atual frente à entrada e ao stop;
9. sinal não repetido (proposto).

Estados: `elegivel`, `aguardando`, `vetada`, `sem_dados`. A ordenação só compara elegíveis: maior PF do estudo, depois a menor das duas metades, depois a amostra. Portão fechado não entra na ordem, então pontuação alta não compensa. Sem elegível, a conclusão é "nenhuma oportunidade elegível".

## 5. Controle de escolhas e posições (definido para o ensaio)

| ponto | regra |
|---|---|
| Reavaliação | uma vez por barra M15 fechada; a avaliação gravada não muda dentro da barra |
| Estabilidade | uma linha por (bot, barra); reinício não refaz nem duplica |
| Expiração | frescor de 1 barra M15; fila de 4 barras do TF |
| Duplicação entre TFs | cada célula card × TF é um candidato; só um é escolhido por barra |
| Limite | 1 posição por bot neste ensaio |
| Posição aberta | a estratégia dona da posição não é trocada; a seleção só vale para entrada nova |

## 6. Fase 2 — ligação com a execução (não feita)

| item | o que precisa mudar |
|---|---|
| Produtor do sinal | o detector da plataforma não produz nada (ver item 1). O produtor legítimo passa a ser o candidato escolhido |
| Atestado | assinar o candidato escolhido: card, TF, barra do TF, lado, entrada e stop (nova versão do contrato) |
| Decisão | `ciclo_decisoes` com TF, card e barra do TF; validade pela escala; unicidade por (bot, TF, barra, lado) |
| RPC e comando | carregar TF e card; consumo único preservado |
| Gestão | gravar na operação o card e o contrato de saída; o protetor respeitar esse contrato |
| Autoridade | trocar o veto de D1/H4 por contexto só depois da observação e com a sua aprovação |

## 7. Evidências

- **Bancada:** `conector_homolog/test_conector_homolog.py::test_h19` (leitor real com MT5 simulado, conector real, API) e `testes/test_selecao.py` (6 testes **sintéticos**: oportunidade válida, contexto superior contrário, nenhuma oportunidade, dado vencido ou desencontrado, troca de candidato, reinício e duplicação, acompanhamento).
- **Plataforma:** pendente. Depende de publicar, implantar e reinstalar o leitor.

## 8. Pendências por timeframe

| TF | coleta e avaliação (3 barras reais) | execução |
|---|---|---|
| M15 | pendente | pendente (fase 2) |
| M30 | pendente | pendente (fase 2) |
| H1 | pendente | pendente (fase 2) |
