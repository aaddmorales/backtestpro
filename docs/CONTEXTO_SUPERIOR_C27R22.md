# D1/H4 como contexto na seleção M15/M30/H1 (C27R22, 07/out/2026)

Estado: **seleção em observação**. A autoridade que abre operação não mudou.

## 1. Caminho de `item1_referencia_contra` — antes e depois

| elo | onde | o que faz | antes (C27R21) | depois (C27R22) |
|---|---|---|---|---|
| Motor | `motor_ciclos/bt_ciclo_v1.py` l.290–293 e l.386–415 (congelado) | direção de cada tempo = canal EMA20 na última barra **fechada**; `topdown` = `bloqueada` se D1 ou H4 está contra o M15, `autorizada` se os dois estão a favor, `neutra` no resto | igual | **igual (intocado)** |
| Executor congelado | `motor_ciclos/bt_vivo_sombra.py` l.809–818 | `topdown` bloqueada impede a abertura; a "contratendência" existe e está DESARMADA (pede bancada, medição e decreto) | não é usado pela plataforma | igual |
| Atestado | ponte do conector → `cv1.veredito` e `cv1.motivo`, assinados | leva o `topdown` do motor | igual | igual |
| Autoridade (API) | `api.py` `_clm_decisao` e `_r01_emitir_decisao` — contrato **R-CICLO-01 r01v4** | `bloqueada` vira veto `R-CICLO-01.cv1_bloqueada`; só `autorizada` (D1 e H4 a favor) + M1/M5 no lado autoriza | **veta por D1/H4** | **continua vetando por D1/H4** (não alterado) |
| Seleção (API) | `api.py` `_sel_avaliar` | portões 1–9; D1/H4 não são portão | `sel-1`: já não vetava, mas rotulava "D1 contra" / "contratendência" e dizia que reduziria risco | `sel-2`: frase explícita, quadro dos tempos superiores, motivos separados, contratos nomeados |
| BabyMachine | `app.html` `clmSelBox` | mostra a avaliação | selo vermelho "D1 contra"; "configuração atual (referência)" | frase "contexto, sem veto automático"; quadro "Dois contratos — só um autoriza" |

Onde D1/H4 **ainda bloqueiam**: só na autoridade r01v4 (execução). Onde **já são contexto**: em todos os portões da seleção.

## 2. Contratos

| | Seleção | Autoridade |
|---|---|---|
| Identificador | `sel-2` | `R-CICLO-01 r01v4` |
| Estado | em observação, não operacional | em vigor |
| D1/H4 | contexto: informam, não fecham portão | veto quando contra o M15; exigidos a favor para autorizar |
| O que bloqueia | integridade, sinal confirmado, frescor, corte do Ciclo no M15, selo do estudo, Ciclo na escala do card, custo, preço × entrada/stop, sinal repetido | atestado inválido, veredito do motor, M1/M5 fora do lado |
| Exigência superior por card | nenhum dos 13 cards exige alinhamento com D1/H4 | — |

A avaliação gravada traz `contratos.selecao`, `contratos.autoridade`, `contratos.selecao_e_operacional = false` e, por barra, se a autoridade vetou por D1/H4.

Levar "D1/H4 como contexto" para a autoridade exige um contrato novo (r01v5), que muda o que o backend aceita do atestado. Não foi feito: é mudança de regra de abertura e precisa de decisão separada.

## 3. Como o motor lê o D1 e o H4

- Barra: a última **fechada** (o espelho vem de `copy_rates_from_pos` a partir da posição 1). O motor nunca lê barra em formação.
- Canal: EMA de 20 períodos das máximas e das mínimas (k = 2/21), com 300 barras de D1 e 400 de H4.
- Condição: `fechamento > EMA20 das máximas` = alta; `fechamento < EMA20 das mínimas` = baixa; entre as duas = lateral.
- Consequência: o D1 só muda uma vez por dia. Depois de um fechamento acima do canal, o D1 fica "alta" o dia seguinte inteiro, mesmo com o preço já de volta para dentro do canal.

O leitor 1.4 passa a registrar, por tempo: barra, OHLC, as duas EMAs, a condição, e uma conferência com até 1000 barras puxadas do MT5 na hora. A API compara ainda com a vela fechada que o EA envia e informa, à parte, a barra em formação.

## 4. Frescor dos candidatos

Regra (inalterada): entrada nova só até 1 barra M15 depois da entrada resolvida. Vem do executor congelado (`IDADE_MAX = 1`) e vale igual para M15, M30 e H1 porque o contrato do estudo resolve toda entrada no relógio do M15.

O que a auditoria mostrou: o leitor trabalha só com barras fechadas, e o resolvedor do estudo só devolve a entrada depois que a barra M15 seguinte fechou e, no modo "fechamento", depois que a barra do timeframe posterior ao sinal fechou.

| escala | entrada estudada | 1ª confirmação possível | vencimento | resultado |
|---|---|---|---|---|
| M15 | abertura da barra seguinte ao sinal | 30 min depois | 30 min depois | vista uma única vez, no limite |
| M30 | idem | 30 min depois | 30 min depois | vista uma única vez, no limite |
| H1 | idem | 60 min depois | 30 min depois | **nunca vista dentro do prazo** |

A validade não foi ampliada. Cada candidato passa a mostrar esses horários e, quando o prazo é inalcançável, um aviso.

## 5. Motivos separados

Cada candidato lista seus motivos com o efeito e o contrato:

- **bloqueia** (seleção): portão fechado ou sem dado — sinal vencido, sem selo, corte do Ciclo, custo, etc.
- **informa** (seleção): D1, H4, H1 ou M30 em sentido oposto.
- **bloqueia a execução** (autoridade r01v4): a regra em vigor não autorizaria o lado; quando a causa é D1/H4, isso é dito.
- **bloqueia a execução** (modo do bot): modo observar.

## 6. Pendências

- Decisão do dono sobre a autoridade (r01v5).
- Decisão do dono sobre o frescor em H1 (o método atual não permite ver um candidato H1 no prazo).
- Conferência das EMAs contra o indicador do gráfico do MT5: o leitor confere contra barras do MT5, não contra o buffer do indicador.
