# C27R25 — Contrato de corte do Ciclo (`corte-ciclo-2`)

Versões: API 7.94 · app v10.61 · leitor 1.7-hml (cand-5) · conector HOMOLOG v1.35-hml13.
Preparado em 08/10/2026 durante o ensaio `ENS-20261007-b4e1c812`. **Não implantado nem instalado antes do fim do ensaio** (08/10 17:00 UTC): o ensaio roda inteiro na versão C27R24.

## 1. Contrato original localizado (motor congelado, não alterado)

| Onde | O que diz | Função |
|---|---|---|
| `bloco1_motor_v3.py` l.1117–1130 (Feito00093, palavra do dono 28/ago) | "o corte a partir do M15 seguido de confirmação"; "M1 / M5 / M10 IDENTIFICAM e MONITORAM. Nunca cortam"; "Sem confirmação: CARREGA a posição" | regra do corte: identificação embaixo + confirmação no andar que decide |
| idem, l.1129 | `ANDARES_QUE_DECIDEM = ["M15","M30","H1","H4","Daily","W1","MN1"]` | lista de quem confirma — **o código escreveu "do M15 para cima"** |
| `FichaSerie._cortes` (l.1502) → `corta[lado][k]`, `motivo[lado][k]` | identificação em M1/M5/M10 na barra M15 `k` + evento de reversão/exaustão de qualquer andar da lista acima na mesma barra | série de corte usada pelo estudo e pela integração |
| `decisao_de_corte()` (l.1132) | mesma regra, por instante ("fonte única") | consulta pontual |
| `corte_pelo_ciclo()` (l.1196, Feito00091) | versão anterior; M1→M5 sozinhos cortam (contraria o Feito00093) | não usada |
| `professor_bloco2.py` l.299 (Feito00153.3) | `F15.corta[lado][k] and not F15.B1[k]`; "corte no M15, pilha inteira"; vida da posição 100% Ciclo no relógio do M15 | gestão (saída) no estudo |
| idem, l.152/159/326 | corte contra o lado na barra da entrada impede a entrada | entrada no estudo |
| `CICLO_BLOCO1_CHECKLIST_OFICIAL_v3.md` §2.1, §2.2, R1 | janela 10→15; "sem confirmação até a 15ª barra: o 15m fechado decide"; "gatilho NUNCA no M1"; proteção corta sem consultar contexto | checklist oficial |

## 2. Divergência registrada

A ordem do dono: **H1 e M30 não são fontes de corte**; participam da confirmação de oportunidades.
O que estava em vigor (leitor ≤ 1.6, API ≤ 7.93): o corte vinha da ficha completa, em que M30, H1, H4, D1, W1 e MN1 também decidiam. Esses tempos podiam (a) impedir a entrada — portão 4 da seleção e condição 5 da autoridade — e (b) fechar posição — passo "corte do Ciclo" da gestão.

A divergência **não nasceu na integração**: está na lista `ANDARES_QUE_DECIDEM` do próprio motor congelado, que a integração reproduzia fielmente. O motor continua intacto; a adequação é feita no contrato.

Medição de bancada (reprodução sintética, 1.501 barras M15 — não é evidência da plataforma):

| Lado | Cortes na integração anterior | Cortes no contrato | Deixam de existir (só por tempos maiores) | Andares que decidiam |
|---|---|---|---|---|
| contra compra | 62 | 37 | 25 | M15 37 · M30 17 · H1 12 · H4 7 · D1 1 |
| contra venda | 82 | 40 | 42 | M15 40 · M30 24 · H1 17 · H4 8 · D1 3 |

Trade nº 1 do ensaio (BTC, fechado por B3) não passou por corte do Ciclo: não é afetado.

## 3. Contrato `corte-ciclo-2`

- Regra: a ficha **congelada** (`FichaSerie._cortes`) calculada sobre um leitor que só tem os andares M1, M5, M10 e M15. Identificam M1/M5/M10; **só o M15 decide**. Nenhuma linha do motor é alterada.
- Não cortam, não vetam, não fecham: M30, H1, H4, D1, W1, MN1.
- Uso único na entrada e na gestão: confirmação em tempo real (`conf-rt-1`), portão 4, condição 5 da r01v5 e passo "corte do Ciclo" da gestão (`gestao-1`, ordem inalterada: B5 → B3 → corte → trailing).
- Assinado: o conector hml13 inclui o bloco `corte` (contrato, andares, corte e origem por lado na barra que abre e na última fechada) no atestado r01v5.
- A API só aceita corte com este contrato assinado. Sem contrato, com contrato diferente ou com origem que cite andar que decide ≠ M15: na entrada, condição 5 = dado indisponível (não autoriza); na gestão, o corte é ignorado e registrado como aviso (stop, B5, B3 e trailing seguem valendo).
- Nenhum requisito novo: B1, B3 e B5 seguem como eram (B3 lê o M5).

## 4. BabyMachine — três coisas separadas

1. **Contexto**: D1, H4, H1, M30 (direção do canal). Informa; não aprova, não veta, não muda ranking, lote, stop ou saída; não corta.
2. **Confirmação de abertura**: sinal do card no timeframe do card (M15, M30 ou H1), em barra fechada; cada confirmação mostra a origem (card, timeframe, leituras usadas).
3. **Corte**: contrato, regra original, andares, quem não corta, corte por lado (barra que abre / última fechada) com a origem (`M5:evento -> M15:evento`) e, quando difere, o que a integração anterior faria e por qual andar.

Cada fechamento por corte grava na gestão e na trilha: contrato, regra original responsável e origem.

## 5. Testes

- `motor_ciclos/testes/test_replay_tempo_real.py` 6, 7, 8: corte do contrato = ficha completa filtrada por "M15 decidiu"; todo corte só por M30/H1/H4/D1 some; nenhum corte novo; trocar as barras de M30/H1/H4/D1 não muda nenhuma barra do corte do contrato (e muda o da integração anterior); candidato, gestão e relato usam o contrato.
- `testes/test_r01v5.py` 6: M30/H1/H4/D1 todos contra não vetam; sem contrato / contrato anterior / origem H1, M30, H4 ou D1 → não autoriza; corte legítimo veta com origem; separação na BabyMachine.
- `testes/test_sessao.py` 6: corte de contrato anterior ou com origem H1/M30 não fecha posição; corte do contrato fecha e grava regra e origem.
- `conector_homolog/test_conector_homolog.py` h19: bloco `corte` na mesma assinatura.

## 6. Atenção — comparabilidade com o estudo

As células com selo foram medidas com o corte da ficha completa (M30/H1/H4/D1 decidindo). Com o contrato, ao vivo haverá **menos cortes**: menos entradas barradas e posições carregadas por mais tempo. O resultado do estudo deixa de ser referência direta para a saída até o estudo ser refeito com o mesmo contrato (o que exige rodar o Bloco 2 com a ficha restrita — não feito aqui).

## 7. Pendente (não resolvido neste contrato)

- Condição 6 / portão 6 ("Ciclo na escala do card") ainda veta card de continuação pelo canal do próprio timeframe — inclusive H1 e M30. É veto de abertura por direção de H1/M30, não corte; fica para a linha única (C27R25, etapas e autoridade única), junto com id único de decisão e estados uniformes.
- Evidência da plataforma: só depois de instalar (leitor 1.7 + conector hml13) e implantar a API 7.94, após o ensaio.
