---
name: bottested-trader-m15
description: Leitura e auditoria da entrada M15 ensinada pelo dono do BotTested (exaustão → lateralização → zona já conhecida → fechamento além da zona → superação da mínima/máxima na vela seguinte → gestão). Use ao auditar sinais dos bots da BabyMachine (Bot 01 BTCUSD, Bot 02 XAUUSD), ao explicar por que o bot entrou ou não entrou, ao montar replays sem ordens e ao separar sinal de autorização de ordem.
---

# bottested-trader-m15 — v1.1 (ORDEM 054-A + ORDEM 055, 12/11/2026)

Skill própria do projeto. Ela descreve e audita a regra; **não executa nada no MT5**. Instalar esta skill no agente
não significa que o bot já faz a leitura no terminal: o que roda no MT5 é só o que está no EA (`api.py`, `_BT_LATERAL_R0_MQL5`,
`BTLAT_VERSAO "lateral-r1.3 (O55)"`) e foi instalado pelo Conector HOMOLOG.

## 1. Sequência ensinada (ordem obrigatória)

1. **Exaustão** do movimento anterior (sacudida/exaustão na leitura LM).
2. **Lateralização** — o preço para de andar e passa a respeitar zonas.
3. **Suporte ou resistência já conhecido** — a zona tem que estar CONFIRMADA na memória O39 **antes** da barra de rompimento
   (horário de confirmação ≤ abertura da barra que rompe). Zona confirmada na própria barra não vale.
4. **Fechamento além da zona** — a barra M15 fecha abaixo da base do suporte (venda) / acima do topo da resistência (compra).
   Isso ARMA o gatilho na mínima (venda) / máxima (compra) dessa barra.
5. **Superação na vela seguinte** — só dentro da barra seguinte, o primeiro tick que fica ≥ 1 tick além do extremo é o SINAL.
   Igualar a mínima/máxima não dispara. Sem superação até o fim da barra seguinte → o sinal EXPIRA
   (`toque sem superacao` se tocou, `nao alcancou` se nem chegou). Não espera fechamento, terceira barra nem reteste.
6. **Acompanhamento da posição** — gestão da R1: stop 2 ATR, corte estrutural pela máxima/mínima da barra de entrada,
   saída pelo canal EMA20 (High/Low).

## 2. Quatro decisões SEPARADAS (nunca misturar no registro)

| Decisão | Pergunta | Onde mora hoje |
|---|---|---|
| D1 Leitura do contexto | Há zona já conhecida e confirmada antes do rompimento? Houve exaustão/lateralização? | Zonas: memória O39 (EA + LM). Exaustão/lateralização: **só na leitura LM** (`auditoria_leituras.eventos`), o EA não a usa na entrada |
| D2 Disparo do sinal | Fechou além da zona? A vela seguinte superou o extremo em ≥ 1 tick? | EA r1.2 (`BTLatRompZArmar` / `BTLatRompZTick`) |
| D3 Autorização da ordem | Há espaço ≥ 1,0 R até a próxima zona (M15 + H1, líquido de spread)? Já existe posição? | EA r1.2 (`avaliar_espaco` / `BTLatEnviar`, porta única) |
| D4 Gestão | Stop, corte estrutural, saída no canal EMA20 | EA (gestão R1) |

### Registro obrigatório quando a ordem não sai

Sinal que disparou e não virou ordem é **"sinal reconhecido; ordem bloqueada — <motivo>"**, nunca "sem sinal".
Mapeamento das strings do motor:

| String do EA / referência | Registro da skill |
|---|---|
| `sinal disparado; bloqueado por falta de espaco` | sinal reconhecido; ordem bloqueada — falta de espaço (< 1,0 R até a próxima zona) |
| `sinal disparado; bloqueado: entrada dentro da zona` | sinal reconhecido; ordem bloqueada — entrada dentro da zona |
| `sinal disparado; bloqueado: distancia nao calculavel (historico insuficiente)` | sinal reconhecido; ordem bloqueada — distância não calculável (histórico < 200 barras) |
| `sinal disparado; bloqueado: posicao aberta` | sinal reconhecido; **CONTINUIDADE** — posição já aberta, entrada não duplicada |
| `sinal disparado; ordem autorizada` + `envio=nao enviada: envio desligado (validacao em sombra)` | sinal reconhecido; ordem autorizada; não enviada (sombra) |

Cálculo do espaço (D3): `d = E − topo da zona à frente` (venda; espelhado na compra), `espaço líquido = d − spread`,
`R = 2 ATR`, `espaço_R = espaço líquido / R`, mínimo **1,0 R**. Sem zona à frente e memória < 200 barras → não calculável → bloqueia.


## 2b. As três entradas do EA (não confundir)

| Entrada | Referência do gatilho | Onde |
|---|---|---|
| CAIXA (R0/R1) | mín./máx. da barra de rompimento da caixa de 12 barras ≤ 3 ATR, válida só na barra seguinte | EA desde a O47/O53 |
| ROMPZ (O53-D) | mín./máx. da vela que FECHOU FORA de uma zona O39 já confirmada, válida só na barra seguinte | EA r1.2+ |
| **COMPZ (O55)** | mín./máx. da **ÚLTIMA vela fechada que ainda respeitou e testou** o suporte/resistência da compressão que veio **depois da mudança de estrutura** | EA r1.3 (sombra) |

COMPZ (especificação congelada em `testes/referencia_o55/O55_especificacao_congelada.txt`):
1. Mudança de estrutura (venda): último topo O39 confirmado MAIS BAIXO que o anterior (≤ 12 barras) + fechamento abaixo da EMA20 Low.
2. Compressão a partir da barra seguinte: caixa ≤ 2,0 ATR; cancela se superar o topo da mudança, fechar acima da EMA20 High, passar de 16 barras ou fechar abaixo do suporte sem disparo.
3. Vela que respeita e testa: fecha ≥ suporte e a mínima fica até 0,25 ATR acima dele → vira a referência (atualiza a cada nova).
4. Sinal: 1º tick ≥ 1 tick abaixo da referência, em qualquer barra posterior, com a caixa ≥ 3 barras. Autorização separada (mesmo filtro de 1,0 R).

Caso de aceitação: XAU 11/11 — mudança no fechamento da op42 (11:30 srv), referências op43 → op47 → **op51 (4047,20)**, sinal na op52 (13:45) a 4047,00; o filtro vigente bloqueia ("entrada dentro da zona": a zona M15 4045,85–4052,90 é o próprio suporte da compressão). Sem filtro (sombra): saída pelo canal 12/11 02:45 a 3985,50.

## 3. O que NÃO pode ser alterado por esta skill

- O filtro de espaço de 1,0 R continua no fluxo autorizado. A variante sem filtro existe **só em sombra** (`InpRompZFiltro=false` apenas em teste).
- **Caixa ≠ ROMPZ ≠ COMPZ.** São três entradas separadas, cada uma com sua referência.
- **Regra da caixa ≠ regra da zona.** A R0/R1 de caixa (12 barras ≤ 3 ATR, `formacao_o44.detectar_venda`) é uma entrada; o ROMPZ (zona O39 já confirmada) é outra.
  Uma falhar não invalida a outra (ex.: BTC 10/11 barra 70: caixa falha por 1402,52 > 3 ATR 1013,22; ROMPZ arma e dispara na 71).
- Nada de abrir, fechar ou mexer em posição para gerar evidência. Nada em produção. Mudança de regra só por ORDEM do dono.

## 4. Como usar

**Auditar um sinal real (sombra):** ler `agente_eventos` (tipo `bot_lateral`, `detalhe_json.ev` = `rompz_armado` / `rompz_disparo` /
`rompz_expirado` / `ordem`) no Supabase **homolog**, montar D1–D4 com o mapeamento acima e conferir o horário da confirmação da zona.
Horário do servidor = UTC+2; barra do dia = minutos desde 00:00 do servidor / 15 + 1.

**Replay sem ordens** (dados exportados do MT5, horários UTC):

```
python .claude/skills/bottested-trader-m15/scripts/replay_trilha.py M15.csv M1.csv H1.csv --ini <epoch_utc> --spread <spread> [--ativo XAUUSD] [--sem-filtro-sombra]
```

O script não reimplementa a regra: chama `testes/referencia_o53/rompz_o53c.rodar` (referência validada evento a evento contra o EA
em `testes/test_o53c_rompz.py`) e imprime D1–D4 por sinal. Não fala com corretora, terminal nem banco.

**Gráfico de todo relatório:** nível/zona, gatilho, entrada, saída, R, "deixou passar e por quê", e o canal EMA20 High/Low em
amarelo `#ffd60a` com legenda (usar `validacao_o53.trilha_rompz` / `_ema`).

## 5. Casos de aceitação (não usar para medir desempenho)

| Caso | Esperado | Situação |
|---|---|---|
| BTCUSD M15 10/11 barras 70→71 | zonas 74041,89–74115,18 (conf. barra 48) e 74009,30–74070,81 (conf. barra 54) conhecidas antes; fechamento 73995,05 arma gatilho 73956,78 na 70; disparo na 71 (17:30:30 srv); D3: sinal reconhecido; ordem bloqueada — falta de espaço (0,177 R até suporte H1 73642,49) | **Demonstrado em replay** (`replay_trilha.py` + `test_o53c_rompz` 2) |
| Controles: toque sem superação, gatilho expirado, compra espelhada, zona não confirmada | conforme strings acima | **Demonstrado em replay** (`test_o53c_rompz` 3) |
| Rompimento que falha (sinal autorizado que vai ao stop/corte) | D4 registra a saída e o R | Pendente de caso escolhido pelo dono |
| XAUUSD M15 barras 5→6 e 11→12 (+ barra 72 só para auditar saída) | exaustão, suporte rompido, dois gatilhos; o 2º como continuidade se a 1ª posição estiver aberta | **Pendente**: falta a data do print e a exportação MT5 (as velas do banco perto da virada do dia estão corrompidas) |

Os dias desses gráficos são de aceitação; desempenho se mede em outros dias (walk-forward; ver `ml4t-walk-forward-cv`,
`backtest-expert`, `ml4t-cost-model`).

## 6. Referências de código

- EA: `api.py` → `_BT_LATERAL_R0_MQL5` (lateral-r1.2 O53-D).
- Memória de zonas O39: `testes/referencia_o51/estrutura_o39.py`. Caixa: `testes/referencia_o51/formacao_o44.py`.
- ROMPZ: `testes/referencia_o53/rompz_o53c.py`. Gestão/espaço: `testes/referencia_o53/ao_vivo_o53.py`.
- Trilha/diagnóstico: `validacao_o53.py` (`trilha_rompz`), `diagnostico_lm_o50.py`.
