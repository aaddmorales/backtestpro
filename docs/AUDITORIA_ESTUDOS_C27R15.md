# Auditoria dos estudos e do ranking do Admin (C27R15, 02/out/2026 — rev. b)

Nada foi recalculado. Tudo abaixo foi lido do código (`api.py`, `app.html`) e dos bancos: produção só em leitura, homologação em leitura e na cópia descrita no item 4.

## 1. Onde estão os estudos e o ranking

| o que aparece | tabela | rota | função | quem grava |
|---|---|---|---|---|
| Aba **Estudo** do Admin (matriz + Top 10) | `estudo_biblioteca_v2` | `POST /admin/estudo/v2/ler`, `GET /admin/estudo/v2/ativos` | `admin_estudo_v2_ler`, `_estudo_v2_forca` | `POST /admin/estudo/v2/importar` (pacotes do Professor, token `BIBLIOTECA_ADMIN_TOKEN`) |
| Biblioteca antiga (matriz + tops); alimenta o Radar e a média dos cards da Vitrine | `estudo_biblioteca` | `POST /admin/biblioteca/ler`, `GET /admin/biblioteca/ativos` | `admin_biblioteca_ler`, `_bib_gravar_ativo` | fábrica interna (`_matriz_calcular`, regras `BT_FABRICA_V1`) |
| `GET /ranking` | nenhuma | `get_ranking` | lista **fixa no código** (5 nomes com números de demonstração) | ninguém; **não é estudo** |
| Histórico de backtests do usuário | `backtests_historico` | — | — | backtests rodados na plataforma; não entra no ranking do Admin |

## 2. Critério de ranking (como o Admin ordena)

- **v2 (aba Estudo):** entram células com `trades ≥ 30` e `PF > 1`; ordem por **Sharpe** decrescente; mostra as 10 primeiras, por ativo e período.
  - Selo: "forte" = ≥ 30 trades, PF > 1 e PF > 1 nas duas metades do período (ver item 3b); "ok" = PF > 1 e ≥ 20 trades.
- **v1:** entram células com `trades ≥ 20` e `PF > 1`; ordem por Sharpe decrescente; top 10.

## 3. O que cada banco registra

| campo | `estudo_biblioteca_v2` (Professor) | `estudo_biblioteca` (fábrica) |
|---|---|---|
| estratégia / versão | `estrategia_id` = `cardN_…` (13 cards); versão em `origem`: Professor "cards 1.9", motor "3.2.B", Bloco 1 "v4.0" | `estrategia_id` = id da Vitrine (19); `regras_versao` = `BT_FABRICA_V1`; `codigo_hash` (sha256) |
| ativo / TF | símbolo MT5 (16 ativos); M15, M30, H1, H4, Daily | nome da Vitrine (40 ativos); 5m, 15m, 30m, 1h, 4h, 1d |
| período / fonte | "12 meses Ago/25–Ago/26" ou "Set/25–Set/26"; barras MT5 reais, IC Markets | "janela k/3 (6 meses / 2 anos / 5 anos)"; yfinance |
| parâmetros | `carimbo`: stop "estrutural puro", saída "100% Ciclo, sem TP", `buffer_atr` 0,3 | `parametros`: stop_loss, take_profit, alvo_rr, stop_min_atr, ema_period, max_ops, capital |
| operações | `trades` | `trades` |
| acerto, PF, Sharpe, retorno | sim; retorno em **pontos** | sim; retorno em **%** |
| drawdown | `dd` (pontos) | **não registrado** |
| spread | `origem.spread` (fixo por ativo; XAUUSD: 5 pts) | **não registrado** |
| comissão | **não registrado** | `parametros.comissao` = 0,0002 |
| slippage | **não registrado** | **não registrado** |
| data do estudo | `medido_em` (06/09/2026) | `medido_em` (26/07 a 01/10/2026) |
| fora da amostra | **não registrado** (ver 3b); há estabilidade em duas metades (`wf_a_pf`, `wf_b_pf`) | **não registrado**; 3 janelas consecutivas medidas em separado |
| resultado por regime | **não registrado** | **não registrado** |
| extras | `pior`, `mae_p95` (pontos) | `captura_pct`, `forca` |

Volume lido em 02/out:
- **Produção:** v2 = 915 linhas; v1 = 12 444 linhas.
- **Homologação:** v1 = 3 621 linhas (sem XAU); v2 = 0 antes desta ordem.

## 3b. "Walk-forward" do Professor não é avaliação fora da amostra

Li o procedimento no código do Professor (`professor_cards_v19.py`, l. 395–401, cards 2.0; o estudo foi medido com cards 1.9, cujo código não tenho):

```
wf_a = pf(T[T.ts < meio]);  wf_b = pf(T[T.ts >= meio])
```

- É o **PF da primeira e da segunda metade** das operações do mesmo período, com **os mesmos parâmetros**.
- Não há treino numa parte e teste na outra, nem otimização, nem janela rolante. Logo não é fora da amostra; é uma medida de **estabilidade**.
- Não consegui comprovar que a 1.9 fazia diferente da 2.0. Por isso **ajustei o rótulo** em vez de afirmar o procedimento:
  - API: `fora_da_amostra = {existe: false, tipo: "não registrado"}` e, à parte, `estabilidade_em_metades` com os dois PFs e o nome que o banco usa;
  - Admin (aba Estudo): "walk-forward" virou "PF nas duas metades do período"; os números não mudaram.

## 3c. Onde o `/ranking` demonstrativo é consumido

| lugar | o que encontrei |
|---|---|
| `api.py` l. 7424, `GET /ranking` | lista fixa de 5 nomes com números inventados para layout |
| `api.py` l. 987, rota `/` | só cita `/ranking` na lista de endpoints |
| `app.html` | **nenhuma chamada** a `/ranking` |
| `app.html` l. 2272, aba `#tab-rank` ("Rank Best Bots") | HTML **estático** com os mesmos números fictícios; está na lista do `switchTab`, mas **não existe botão** que a abra |
| conector, EA, motor, instaladores | nenhuma referência |

Conclusão: ninguém consome a rota; nenhum número dela chega à BabyMachine, ao Radar ou a uma decisão. Marquei os dois pontos sem removê-los: a rota devolve `"demonstracao": true` com aviso, e a aba traz "DEMONSTRAÇÃO DE LAYOUT — nomes e números fictícios". Remover a rota e a aba é decisão sua.

## 4. Cópia feita na homologação

- Copiei as 55 linhas de `estudo_biblioteca_v2` de **XAUUSD** da produção para a homologação, **literalmente**: mesmos ids (2592–2646), métricas, carimbo, origem e `medido_em`. O arquivo é `sql/0006_copia_estudo_v2_xauusd.sql`.
- Conferência por md5 nos dois bancos: métricas `0c6fa03734f43eab8bd5d235640c1ae1`, carimbo `9cafcdf7ecf5da5296ae8ff08132ab25`. Os dois batem.
- Os outros 15 ativos não foram copiados. Para tê-los, reimporte os pacotes do Professor pela rota oficial `/admin/estudo/v2/importar`.

## 5. Vínculo bot ↔ estudo

- O envio grava no bot (`config_operacional`): `estrategia_id`, `estrategia_nome`, `ativo_envio`, `timeframe_envio`, `codigo_sha1`, `sl_envio_pts`, `tp_envio_pts`.
- **v1 (fábrica):** o id é o mesmo da Vitrine, mas isso **não basta**. A correspondência só é "comprovada" quando três coisas batem: o `codigo_hash` do estudo é o sha256 do código atual do card; o `codigo_sha1` gravado no envio do bot é o sha1 desse mesmo código; stop e alvo do envio são os do estudo. Fora disso aparece "NÃO COMPROVADA", com o que não bateu.
- **v2 (Professor):** os ids são outros (`cardN_…`) e **nenhum banco guarda o vínculo**. A ligação é só pelo nome, então **todas** ficam como **correspondência não comprovada**. Na BabyMachine o quadro diz "os números abaixo não são o desempenho deste bot".
- Comparei o código da Vitrine com o dos cards (cards 2.0). A **saída é sempre diferente**: o estudo usa stop estrutural e saída "100% Ciclo, sem TP"; o bot usa stop e alvo do envio.

| Vitrine | card do Professor | entrada |
|---|---|---|
| Cruzamento EMA 9/21 | card5_ema_9_21 | equivalente |
| Cruzamento do Canal | card4_canal_ema20 | parcial: a Vitrine entra enquanto o fechamento está fora do canal; o card só no cruzamento |
| MACD | card9_macd | parcial: a Vitrine só compra; o card opera os dois lados |
| S&R do Dia Anterior | card11_sr_dia_anterior | parcial: o card exige cruzamento e continuidade |
| Tripla Média 9/21/50 | card6_tripla_media | diferente |
| RSI Reversão | card7_rsi | diferente (média simples × Wilder; só compra × dois lados) |
| Bollinger Reversão | card8_bollinger | diferente (toque × fechou fora e voltou) |
| Rompimento Donchian 20 | card10_donchian20 | diferente (máxima/mínima da barra × fechamento com continuidade) |
| Engolfo | card12_engolfo | diferente |
| Topo/Fundo Duplo | card13_topo_fundo_duplo | diferente (pivôs e tolerância) |
| Estratégia 2 | card1_reversao_extremo | diferente |

- Sem equivalente na Vitrine: `card2_rompimento_caixa`, `card3_segunda_entrada`.
- Sem card no v2: Canal EMA 20 H/L, Tendência Diária, Trend Day, Fibonacci, Gap, Média+ATR, Microcanal, Fechamento Ímã.
- **MASTER** (`teste_integracao_mt5`): executor de integração, "sem resultado medido". Não tem estudo.

## 6. O estudo participa da decisão?

- **Autorização de abertura (R-CICLO-01):** não. Usa só o atestado do motor e as checagens da API.
- **Checklist, item "Estratégia ajustada":** só confere se o bot tem `estrategia_nome` registrado. Não olha desempenho.
- **Radar:** usa o banco v1 para **sugerir** estratégia ou TF melhor. Não autoriza ordem.
- **Regra derivada de medição que já atua:** o "mandato medido" da v7.46 grava `veto_fase=true` (Cruzamento do Canal e Estratégia 2 em XAU) e `protecao=false` (Donchian em BTC) no envio. Vem da medição do Professor de fases; os números dessa medição **não estão** nos bancos de estudo.

Nesta ordem o estudo entrou só como **referência informativa**. Nenhuma regra de abertura foi alterada.

## 7. Pontuação, veto e autorização

São três coisas diferentes, e o quadro agora mostra cada uma:

- **Pontuação** — prontidão % do checklist e estrelas de confluência. É medida; pontuação alta não autoriza.
- **Veto** — um portão fechado. O quadro lista os 8 portões na ordem em que o detector e o emissor os aplicam e aponta o primeiro fechado.
- **Autorização** — só existe com os 8 portões avaliados e abertos. O quadro **não autoriza nada**; ele lê.

| # | portão | o quadro avalia? |
|---|---|---|
| 1 | modo operacional ("observar" não dispara nada) | sim |
| 2 | intervalo entre oportunidades | sim (memória do servidor) |
| 3 | disjuntores: pausa, posição aberta, limite diário, drawdown | parcial: drawdown do dia só dentro do detector |
| 4 | direção e níveis da operação | não; só dentro do detector |
| 5 | confluências ≥ limiar de estrelas do modo | não; só dentro do detector |
| 6 | checklist de entrada (`pode_entrar`) | sim |
| 7 | autoridade dos Ciclos (R-CICLO-01) | sim |
| 8 | consumo único da decisão (RPC) | não; só quando há decisão emitida |

A leitura dos portões não cria nem altera estado no servidor (lê `_BOT_CONFIG`, `_OPORTUNIDADES_HIST` e `_CIRCUIT_STATE` sem chamar as funções que os inicializam).

## 8. Decisão registrada da barra × integração agora

- A decisão da barra M15 fica gravada em `ciclo_leituras` e vale 900 s. Snapshots que chegam depois da validade **não reescrevem** a decisão; são contados em `falhas.pos_validade` e geram um aviso na trilha por estado distinto.
- O painel mostra, lado a lado, a **decisão registrada** e a **integração agora** (motor e atestado deste snapshot, com o elo em falha). Uma falha atual aparece mesmo quando a barra anterior terminou válida.
