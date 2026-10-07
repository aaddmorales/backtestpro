# Autoridade r01v5 e confirmação em tempo real (C27R23, 07/out/2026)

Estado: **construído, testado na bancada, desligado na plataforma**. A r01v4 continua sendo a única regra que abre operação. Nenhuma execução foi habilitada.

## 1. Cadeia completa

```
MT5 (PC) ──barras FECHADAS──▶ leitor 1.5
   │   espelho da barra  +  cópia com a barra aberta (sem informação)
   │   cards 2.0 (congelados) → sinais em barras fechadas
   │   confirmação em TEMPO REAL (conf-rt-1)  ·  resolvedor do estudo (só referência)
   ▼
candidatos.json ──▶ conector hml11
   │   cv_atestado        (r01v4: veredito do motor, como antes)
   │   cv_atestado_cand   (r01v5: candidatos confirmados e válidos, ASSINADOS — HMAC, bot, símbolo, magic, barra)
   ▼
API ── seleção sel-3 (portões, escolha)                         → selecao_avaliacoes
    ── r01v4: decisão da barra (em vigor)                       → ciclo_leituras
    ── r01v5: 12 condições sobre o candidato assinado (SOMBRA)  → selecao_avaliacoes.autoridade_r01v5 + trilha
          └─ só com a chave ligada + bot em automático: ciclo_decisoes → RPC r05_claim_e_comando → mt5_comandos
   ▼
conector (confere stop e lado do candidato) ──▶ EA ──▶ MT5
```

## 2. Contratos, antes e depois

| | antes (C27R22) | depois (C27R23) |
|---|---|---|
| Seleção | `sel-2`: entrada do resolvedor retrospectivo; frescor por idade em barras M15 | `sel-3`: confirmação em tempo real `conf-rt-1`; validade de 30 min a contar da confirmação; "entrada perdida" |
| Autoridade em vigor | `r01v4` | `r01v4` (inalterada) |
| Autoridade nova | não existia | `r01v5`: construída e **desligada** (`autoridade_contratos.r01v5 = false`) |
| Sinais assinados | não | sim (`cv_atestado_cand`) |
| D1/H4 | contexto na seleção, veto na autoridade | contexto na seleção e na r01v5; veto só na r01v4 |

### r01v5: o que é condição e o que é contexto

Condições obrigatórias (todas têm de dar certo):

1. atestado r01v5 verificado (HMAC, bot, símbolo, magic, barra M15 fechada, 900 s)
2. candidato presente no atestado
3. confirmação pelo contrato do card (`conf-rt-1`)
4. dentro da validade da entrada
5. Ciclo sem corte contra o lado e sem blindagem agora
6. Ciclo na escala do card
7. preço atual × referência e stop
8. custo (spread × risco)
9. célula com selo no estudo (filtro herdado)
10. bot sem posição aberta
11. candidato e barra ainda sem decisão
12. candidato é o escolhido pela seleção desta barra

Contexto (gravado na decisão, não entra na conta): D1, H4, a relação de cada um com o lado do candidato, a janela M1/M5/M15 e o veredito do motor congelado.

A r01v5 não transforma "bloqueada" em "autorizada": ela não lê o veredito para decidir. Com o motor dizendo "autorizada", um candidato sem assinatura, com corte do Ciclo ou vencido não passa.

### Travas da execução

| trava | onde | estado na homologação |
|---|---|---|
| chave do contrato | `autoridade_contratos.r01v5.emissao_habilitada` (lida pela API e pela RPC) | desligada |
| modo do bot | só `automatico` executa | observar |
| avaliação | as 12 condições | por barra |

Com a chave desligada, `_r05_emitir_decisao` recusa e a RPC `r05_claim_e_comando` recusa mesmo uma decisão plantada no banco.

## 3. Fluxo temporal dos sinais

| informação | quando existe | antes | agora |
|---|---|---|---|
| sinal do card | no fechamento da barra do sinal | idem; cards baseados em eventos do Ciclo só 1 barra depois | no fechamento, inclusive os baseados em eventos |
| eventos do Ciclo da última barra | no fechamento dela | só quando a barra seguinte fechava (o detector congelado não avalia a última barra da série) | no fechamento, pela cópia com a barra aberta |
| corte do Ciclo e blindagem da barra que abre | na abertura dela | lidos da barra anterior | lidos para a barra que abre agora |
| entrada (modo fechamento) | abertura da M15 seguinte ao sinal | 30 min depois (M15, M30) ou 60 min depois (H1) | no instante da abertura |
| entrada (modo gatilho) | fechamento da barra de continuidade | quando o resolvedor devolvia | no fechamento da barra de continuidade |
| preço | — | preço histórico da entrada do estudo | preço de referência = fechamento da última M15 antes da confirmação; o preço do EA é conferido à parte |
| stop | — | pivô/ATR lidos na barra da entrada (ainda aberta) | pivô/ATR da última M15 fechada antes da confirmação |

### Confirmação, validade e vencimento por escala

| escala | modo | confirmação | início da validade | vencimento |
|---|---|---|---|---|
| M15, M30, H1 | fechamento | barra do sinal fecha, Ciclo sem corte e sem blindagem; com blindagem tenta na M15 seguinte; corte cancela | instante da confirmação | 30 min depois |
| M15, M30, H1 | gatilho | uma barra do timeframe do card fecha além do nível com corpo a favor | fechamento dessa barra | 30 min depois |

A validade de 30 min é a mesma de antes (1 barra M15 do executor congelado), contada do instante da entrada. Não foi ampliada.

Depois do vencimento: **vencida** se houve avaliação dentro do prazo; **entrada perdida** se a confirmação só foi vista depois. Nos dois casos o sinal não volta.

## 4. Comparabilidade com o estudo

O selo do estudo foi medido com o resolvedor retrospectivo. O contrato ao vivo difere:

| item | medido | ao vivo |
|---|---|---|
| stop | pivô e ATR lidos na própria barra da entrada | última M15 fechada antes da confirmação |
| gatilho em M30/H1 | entrada posicionada na M15 que abre a barra de continuidade, ao preço do fechamento dela (até 15/45 min no futuro) | confirma no fechamento, ao preço do fechamento |
| corte e blindagem | vetores do motor por barra | mesmas regras para a barra que abre agora; B5 fica ligada a sexta inteira (ativos não cripto) |
| cards | 1.9 | 2.0 |
| custos | não registrados | spread do EA |

Por isso o selo aparece como **filtro herdado** e a avaliação grava `selo_valida_o_contrato_ao_vivo = false`. Medir o contrato ao vivo exige rodar o Professor com a confirmação em tempo real; não foi feito.

## 5. Conferência motor × MT5 × EA

Ordem: símbolo → timeframe → horário da mesma barra → OHLC → EMA. Barras diferentes (virada) aparecem como "aguardando sincronização", sem comparar valores. EMA: período 20, fator 2/21, sobre máximas e mínimas, iniciada na primeira barra do espelho (300 barras em D1, 400 em H4); conferida contra até 1000 barras do MT5 com tolerância relativa de 1e-5.

## 6. Provas

Bancada (sintético): reprodução cronológica com MT5 falso determinístico — H1 confirmado no fechamento do sinal e ainda válido; o resolvedor do estudo só devolve a mesma entrada 60 min depois; confirmações não mudam com barras novas; a casa "agora" é igual à que o motor congelado grava depois. Autoridade: sombra, adulteração, outro bot, vencimento, repetição, consumo único, comando com stop assinado, chave desligada.

Plataforma: pendente (ver a entrega).

## 7. Limites

- A posição aberta por um comando r01v5 teria só o stop: a saída "100% Ciclo" do contrato do card não é executada por nenhum componente. É mais um motivo para a execução ficar desligada.
- B5 em tempo real bloqueia a sexta inteira em ativos não cripto.
- A cópia com a barra aberta foi provada igual ao motor congelado na bancada, em dados sintéticos; em dados reais a prova vem da observação.
