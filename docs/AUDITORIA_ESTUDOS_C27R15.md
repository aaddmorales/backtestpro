# Auditoria dos estudos e do ranking do Admin (C27R15, 02/out/2026)

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
  - Selo: "forte" = ≥ 30 trades, PF > 1 e PF > 1 nas duas metades do walk-forward; "ok" = PF > 1 e ≥ 20 trades.
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
| fora da amostra | walk-forward em duas metades (`wf_a_pf`, `wf_b_pf`) | **não há**; 3 janelas consecutivas medidas em separado |
| resultado por regime | **não registrado** | **não registrado** |
| extras | `pior`, `mae_p95` (pontos) | `captura_pct`, `forca` |

Volume lido em 02/out:
- **Produção:** v2 = 915 linhas; v1 = 12 444 linhas.
- **Homologação:** v1 = 3 621 linhas (sem XAU); v2 = 0 antes desta ordem.

## 4. Cópia feita na homologação

- Copiei as 55 linhas de `estudo_biblioteca_v2` de **XAUUSD** da produção para a homologação, **literalmente**: mesmos ids (2592–2646), métricas, carimbo, origem e `medido_em`. O arquivo é `sql/0006_copia_estudo_v2_xauusd.sql`.
- Conferência por md5 nos dois bancos: métricas `0c6fa03734f43eab8bd5d235640c1ae1`, carimbo `9cafcdf7ecf5da5296ae8ff08132ab25`. Os dois batem.
- Os outros 15 ativos não foram copiados. Para tê-los, reimporte os pacotes do Professor pela rota oficial `/admin/estudo/v2/importar`.

## 5. Vínculo bot ↔ estudo

- O envio grava no bot (`config_operacional`): `estrategia_id`, `estrategia_nome`, `ativo_envio`, `timeframe_envio`, `codigo_sha1`, `sl_envio_pts`, `tp_envio_pts`.
- **v1:** o id é o mesmo da Vitrine, então o vínculo é direto.
- **v2:** os ids são outros (`cardN_…`) e **nenhum banco guarda o vínculo**. Criei a tabela declarada `_REF_CORRESP_V2`, com dois níveis:
  - "idêntico" (mesmo nome nos dois bancos): EMA 9/21, Tripla Média, RSI, Bollinger, Donchian 20;
  - "declarada" (nome próximo, **a confirmar pelo dono**): Estratégia 2 ↔ Reversão no Extremo, Cruzamento do Canal ↔ card4, MACD, S&R do Dia Anterior, Engolfo, Topo/Fundo Duplo.
- Sem equivalente na Vitrine: `card2_rompimento_caixa`, `card3_segunda_entrada`.
- Sem card no v2: Canal EMA 20 H/L, Tendência Diária, Trend Day, Fibonacci, Gap, Média+ATR, Microcanal, Fechamento Ímã.
- **MASTER** (`teste_integracao_mt5`): executor de integração, "sem resultado medido". Não tem estudo.

## 6. O estudo participa da decisão?

- **Autorização de abertura (R-CICLO-01):** não. Usa só o atestado do motor e as checagens da API.
- **Checklist, item "Estratégia ajustada":** só confere se o bot tem `estrategia_nome` registrado. Não olha desempenho.
- **Radar:** usa o banco v1 para **sugerir** estratégia ou TF melhor. Não autoriza ordem.
- **Regra derivada de medição que já atua:** o "mandato medido" da v7.46 grava `veto_fase=true` (Cruzamento do Canal e Estratégia 2 em XAU) e `protecao=false` (Donchian em BTC) no envio. Vem da medição do Professor de fases; os números dessa medição **não estão** nos bancos de estudo.

Nesta ordem o estudo entrou só como **referência informativa**. Nenhuma regra de abertura foi alterada.
