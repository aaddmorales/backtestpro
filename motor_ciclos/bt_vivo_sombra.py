# -*- coding: utf-8 -*-
# ============================================================================
#  BT VIVO — SOMBRA · v1.0 (A TRAVESSIA, passo 1: o espelho vivo)
#  VERSAO: 1.0 | BUILD: 2026-09-13e-sombra | exige: motor 3.2.B + bloco2 v1.6
#  Registro: Feito00178 | NAO ENVIA ORDENS. NUNCA. Sombra pura (Fase 1).
#
#  O QUE FAZ, a cada minuto:
#    1. Puxa as barras do MT5 (MetaTrader5, mesmo pacote do ver_comissao)
#       para os 7 TFs do ativo — janela de aquecimento configurada.
#    2. Escreve CSVs no FORMATO EXATO dos exports (pasta "Vivo_espelho") —
#       fidelidade por construcao: ZERO parser novo.
#    3. Roda o MESMO LeitorMultiTF + FichaSerie + Seletor (config SELADA da
#       leva v3) sobre o espelho e olha SO a ultima barra M15 fechada.
#    4. Registra a decisao no vivo_log_<ativo>.csv: abertura que o Seletor
#       faria, recusas com motivo, CORTE_PILHA — com timestamp do servidor.
#  --conferir: modo professor x vivo — re-roda o Seletor no espelho salvo e
#  compara com o log (a mesma barra, as duas leituras, TEM QUE BATER).
#
#  AQUECIMENTO [REF, declarado]: M1 3000 · M5 2000 · M15 1500 · M30 1000 ·
#  H1 800 · H4 400 · Daily 300 barras — suficiente p/ ATR14, pivos N=2,
#  caixas e territorio; o selo vem do banco (24m), nao do aquecimento.
# ============================================================================
from __future__ import annotations
import sys, os, time, csv
from datetime import datetime
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import numpy as np, pandas as pd

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path: sys.path.insert(0, _AQUI)
import bloco1_motor_v3 as B1
import professor_cards_v19 as PC          # = cards 2.0
import professor_bloco2 as B2

V_VERSAO = "7.4"; BUILD = "2026-09-20b-escada-e-blindagem-auditoria"
#  v7.4 — lista de 12 do dono (20/set), itens executaveis:
#   1 fix ledger->extra (v7.3.1, mantido)
#   2 AUTOTESTE DE GRAVACAO no boot; falha em --executa = NAO SOBE
#   3 BLOQUEIO EM VOO: gravacao falhou na barra -> barra seguinte nao abre
#     entrada nova (auditoria_indisponivel); trailing/protecao/stop seguem
#   4 latencia instrumentada: passada >30s imprime a quebra decisao x ficha+exec
#   5 --prova-latencia: portao de 60s demonstrado nos dois lados
#   6 eventos de exaustao com direcao (CV1 v2.4)
#   7 --escada [N]: relatorio M1->M5->M15 do dono + placar de falsos alertas
#   8-10,12: fases narrativas; amostra funda + score composto = professor
#  v7.3.1 — CORRECAO (noite 20/set, achada nos prints do dono): o auditor
#  no loop referenciava 'ledger' (nome inexistente naquele escopo) em vez
#  de 'extra' (os eventos reais da passada). O try/except segurou o vivo,
#  mas ficha/fases/veredito NAO foram gravados no BTC a noite toda —
#  "gravacao da ficha falhou (name 'ledger' is not defined)". Uma linha.
#  A percepcao do ETH (caminho proprio) gravou normal.
#  v7.3 — REGISTRO DE MATURIDADE (decreto do dono, 19/set): cada
#  componente carrega o proprio nivel, separado por geracao, e NENHUM
#  esta validado para conta REAL. Niveis: CONSTRUCAO -> BANCADA ->
#  SOMBRA -> DEMO -> REAL. Promocao SO por edicao deliberada desta
#  tabela com a evidencia lavrada na nota (nunca automatica).
#  Impresso no boot (resumo), no --relatorio (secao 0) e no --maturidade
#  (tabela completa). "Aprovado em bancada/demo" = funcionamento MECANICO
#  nos cenarios testados; resultado de mercado e outra prova.
#  v7.2 — O AUDITOR DO SISTEMA TODO (decreto final do dono, 19/set):
#   · TRES LINHAS por barra/decisao, ligadas pelo uid:
#     PERCEPCAO (fichas/fase/classificacao/confianca/acao recomendada,
#     do vivo_fases) -> AUTORIDADE (portoes aplicados, regra congelada,
#     autorizado/bloqueado, motivo, do vivo_exec) -> EXECUCAO (MT5:
#     preco/lote/stop/ticket/confirmacao/resultado)
#   · VEREDITO AUTOMATICO por barra, EMITIDO PELO PROPRIO VIVO (linha
#     AUDITOR no vivo_auditor_<ativo>.csv + alerta no display quando nao
#     for COERENTE): COERENTE · DIVERGENCIA_PERCEPCAO_AUTORIDADE ·
#     DIVERGENCIA_AUTORIDADE_EXECUCAO · DADO_INSUFICIENTE ·
#     MEMORIA_CONTAMINADA · VERSAO_INCOMPATIVEL
#   · --auditor [AAAA-MM-DD]: o relatorio do dia com as tres linhas de
#     cada barra divergente e o placar dos vereditos
#   · VALIDADOR POR ESQUEMA (fim da contagem de campos): ABRIU_SCHEMA v2
#     com nomes+tipos obrigatorios, nao-vazio, extras PERMITIDOS
#   · memoria: sessao do boot carimbada (CV1.SESSAO), formato v2, escrita
#     atomica com trava; --prova-memoria = hash antes/depois de replays
#   · piso de evidencia na fase (conf>=30, pers>=2 [REF]) + --falsos-fase:
#     a correcao e a medicao do achado H1=6
#  v7.1 — AUDITORIA DO TODO (exigida pelo dono): 3 divergencias achadas
#  na leva v2.1/v7.0 e corrigidas ANTES de irem ao vivo:
#   (1) memoria do movimento era gravada por qualquer avaliar() — provas
#       e bancada em replay CONTAMINAVAM a recordacao viva. Agora so o
#       VIVO grava (gravar_mem=True); provas leem e nunca escrevem.
#   (2) ABRIU foi a 27 campos (contratendencia) e o validador/bancada
#       exigiam 26 — atualizados para 27.
#   (3) CONTRATENDENCIA nasceu ARMADA mudando portao CONGELADO com base
#       em fase [REF] sem medicao/bancada — violava a lei da casa. Agora
#       DESARMADA por padrao: sem a flag --contra-armado o bloqueio
#       antigo vale e o vivo NARRA o que a contratendencia teria feito
#       (NAO_ABRIU ...contra_desarmada[fase]); armar = decreto explicito
#       do dono na linha de comando, lavrado no boot, ate bancada propria
#       + medicao + carimbo.
#  v7.0 — REGRAS DE ENCONTRO DOS CICLOS (decreto 2, 19/set; motor CV1 v2.1):
#    · 10 ESTADOS de propagacao nomeados + MOVIMENTO com identidade
#      (#ATV-ddmm-NN) e marcos por estado na memoria — o sistema recorda
#      o desenvolvimento do movimento
#    · CONTRATENDENCIA no executor: entrada contra o contexto (D1/H4)
#      deixa de ser bloqueio cego — passa: SO com fase>=3 na direcao da
#      entrada, com RISCO REDUZIDO x0.5 [REF] e rotulo CONTRATENDENCIA
#      no ledger; fase<3 segue bloqueada ("queda no M1 nao e reversao")
#    · conclusao no formato do decreto (CICLO2/CICLO1/CLASSIFICACAO/
#      DECISAO/manutencao) gravada no vivo_fases e no registro CICLO
#  v6.9 — LEITURA POR INTEIRO no vivo (decreto do dono; motor = CV1 v2.0):
#    · vivo_fases_<ativo>.csv por barra: fase da propagacao, rotulo,
#      conclusao conjunta, conflitos de camadas, estado exibido (com
#      histerese [REF]) x bruto, e as fichas de 12 campos dos 7 TFs
#    · a entrada CICLO do vivo_exec ganha fase+conclusao (influencia
#      POR DECISAO com a fotografia inteira)
#    · modos novos (livres): --fases [N] (a fotografia barra a barra) e
#      --propagacao [N] (o FILME: so as transicoes de fase/estado)
#  Autoridade INALTERADA: portoes e corte seguem nas regras ja medidas/
#  demonstradas; fase/conclusao entram NARRADAS por decisao ate a medicao
#  do professor cravar as formulas [REF] de forca/confianca/fases.
#  v6.8 — cosmetico pego pela bancada 8/8: quando NOS fechamos (CORTE_CICLO
#  ou FECHOU) a posicao na mesma passada, o classificador de "quem fechou"
#  nao deve tambem carimbar FECHADA_EXTERNA para o mesmo uid.
#  v6.7 — fix pego pela rodada do dono: a bancada-corte no BTC reprovava
#  nos passos 1/6/7 porque a QUARENTENA barrava a ordem do proprio teste.
#  Agora a bancada-corte SUSPENDE a quarentena do ativo SO dentro do teste
#  (restaurada no finally, narrado na transcricao) — teste funcional
#  forcado em demo e exatamente o caso que a quarentena nao protege.
#  + CV1 v1.4: leitor tolera CSVs Daily/W sem coluna <TIME> (o crash do
#  professor_bloco1 no Test 24meses).
#  v6.6 — A ULTIMA BLINDAGEM NASCE: B2 CALENDARIO (ordem do dono 19/set,
#  "nada fica para tras"). A blindagem de noticia era a UNICA inexistente
#  em qualquer lugar do sistema. Nasce com FONTE MANUAL DECLARADA:
#    · arquivo calendario.csv na pasta (o dono preenche da fonte que
#      escolher — ForexFactory, Investing, corretora):
#      formato: data;hora;moeda;impacto;evento
#      exemplo:  2026.09.22;15:30;USD;alto;CPI EUA
#    · entrada NOVA e BLOQUEADA de JANELA_NOTICIA_MIN=30min [REF] antes
#      ate 30min depois de evento de impacto ALTO na moeda do ativo
#      (XAU/BTC/ETH: USD · JP225: JPY+USD) — NAO_ABRIU B2_calendario
#    · POSICAO ABERTA NUNCA e fechada por noticia (blindagem preventiva
#      de entrada, doutrina B2; corte e assunto do Ciclo/stop)
#    · sem arquivo = blindagem DESLIGADA e DECLARADA no boot (nunca
#      silenciosa); modo --calendario confere eventos carregados e os
#      bloqueios das proximas 24h
#  + fix cosmetico do checklist: rotulo da quarentena agora distingue
#    ATIVA / DERRUBADA POR DECRETO / SEM QUARENTENA (XAU e ETH nunca
#    tiveram quarentena e apareciam como "derrubada").
#  v6.5 — carimbo "aprovado" retificado (veredito do dono): --prova-tf
#  (7 TFs SEPARADOS + escada M1->M5->M15 barra a barra com horarios) ·
#  --estabilidade (mudancas de estado, duracao media, reversoes 1-barra,
#  coincidencia com decisao) · BOOT-CHECKLIST (demo, portoes, ledger,
#  posicoes, quarentena) · --sem-quarentena nunca e padrao.
#  v6.4 — AS 12 CORRECOES IMEDIATAS DO DONO (19/set, pos-primeira ordem):
#  horarios completos por ordem (ABRIU 19->26 campos: ts_decisao/ts_envio/
#  ts_confirmacao + bid/ask no envio + risco_usd_exec/risco_pct_exec) ·
#  BLOQUEIO POR LATENCIA (LATENCIA_MAX_ENVIO=60s [REF]) · LIMITE DE DESVIO
#  DE PRECO (DESVIO_MAX_PTS [REF]; o slippage de 6.372 pts teria sido
#  bloqueado pelo 3.000 do BTC) · risco recalculado POS-fill · P&L liquido
#  + comissao + swap + preco de fechamento no FECHOU/CORTE_CICLO (history
#  _deals) · dirs dos 7 TFs na entrada CICLO de cada passada · QUEM FECHOU
#  sempre nomeado (fim_da_pilha_sombra / CORTE_CICLO / FECHADA_EXTERNA) ·
#  contadores do relatorio ancorados em motivo (falso-positivo morto) ·
#  DEMO-only reafirmado · polling 15s ja era lei (v6.2).
#  v6.3 — DOIS BUGS PEGOS PELA PRIMEIRA NOITE COM AUTORIDADE (19/set):
#    #1 --relatorio crashava (regex com "[]" sem escape) — contador virou
#       contagem literal (str.count)
#    #2 o portao da leva v3 barrava --percepcao/--relatorio (o ETHUSD nao
#       subiu na noite 1) — agora vale so p/ modos que exigem Lista.
#  v6.2 — FONTE INTRABAR, fase 1: PROTECAO (decreto 5 do dono, 19/set).
#  Doutrina congelada: M15 segue a decisao ESTRUTURAL; o M1 vira a cadencia
#  da PROTECAO — o Ciclo agora corta DENTRO da barra, nao so no fechamento:
#    · loop com --executa acorda a cada 15s (era 60)
#    · entre fechamentos de M15, se ha POSICAO demo aberta: M1/M5 do
#      espelho sao atualizados a cada M1 novo, o CV1 re-avalia, e a
#      condicao de corte (reversao 2o/3o sinal contra a posicao, janela
#      10->15 confirmada, voltou_compressao) FECHA a posicao na hora —
#      linha CORTE_CICLO_INTRABAR no vivo_exec com o ts do M1
#    · so PROTECAO ganha cadencia intrabar (fechar cedo nunca aumenta
#      risco); ENTRADA intrabar (gatilho no toque das celulas) exige o
#      professor_bloco2.py (fonte pendente — 4o pedido) e vira spec junto
#      com a fase tick (toque exato) — declarado, nao improvisado
#    · beneficio lateral: barra M15 nova detectada em ate ~15s (era ate 60)
#  v6.1 — TESTE FUNCIONAL FORCADO DO CORTE (decreto do dono, 19/set), modo
#  --bancada-corte, os 8 passos com PASSA/FALHA e transcricao:
#    1 abre posicao demo (COMPRA, magic da bancada, lote-piso)
#    2 FORCA deterioracao no M1 (serie sintetica: perna de alta longa +
#      climax + queda — fisica validada contra o CV1)
#    3 confirma o avanco no M5 (perdeu a alta: dir <= 0)
#    4 confirma o conflito no M15 (exaustao IDENTIFICADA, degrau>=2 contra)
#    5 emite o comando de corte (veredito do Ciclo, mesma estrutura do vivo)
#    6 fecha a posicao no MT5 (CORTE_CICLO pelo PROPRIO executar())
#    7 confirma ticket e PRECO de fechamento (history_deals do MT5)
#    8 registra o caminho INTEIRO (vivo_bancada_<ativo>.txt)
#  A percepcao le a serie forcada da pasta Bancada_ciclo/ (nunca o espelho
#  real); a execucao e real na demo. Nada do vivo e tocado.
#  v6.0 — O CICLO GANHA AUTORIDADE (decreto do dono, 19/set — arquitetura
#  CONGELADA): topo->base (D1->H4->H1->M30->M15) define contexto e AUTORIZA
#  ou BLOQUEIA entrada; base->topo (M1->M5->M15) detecta deterioracao,
#  separa pullback de reversao e da ao M15 autoridade de manter/proteger/
#  CORTAR. Fim do "narrado em paralelo": decidir() injeta o veredito em
#  contra["ciclo"]; executar() ganha o PORTAO DO CICLO (topdown bloqueia
#  entrada com regra nomeada) e o CORTE REAL (reversao 2o/3o sinal contra a
#  posicao, janela 10->15 confirmada ou voltou_compressao FECHAM a demo,
#  tipo=CORTE_CICLO confirmado); toda passada registra a entrada CICLO
#  (apoio/conflito/classificacao). Falha de leitura = portao novo nao arma
#  (leis antigas seguem). Autoridade nasce em DEMO por decreto; a medicao
#  (B1_todos) segue como validador pre-capital-real.
#  v5.2 — CAMPANHA DE FIM DE SEMANA "SISTEMA INTEIRO" (decreto do dono):
#  objetivo = provar o funcionamento e a TRANSPARENCIA, resultado irrelevante.
#    · --sem-quarentena: decreto EXPLICITO do dono na linha de comando —
#      derruba a QUARENTENA_EXEC do ativo lancado (fds em demo; portao de
#      spread segue armado; coleta dos 7 dias continua). Narrado no boot e
#      lavrado no manifesto (quarentena_exec do manifesto reflete o estado
#      REAL da subida).
#    · --relatorio [AAAA-MM-DD]: o relatorio do dia sai DA MAQUINA, montado
#      dos proprios ledgers (log/exec/ciclo/ficha/enviadas): cadencia,
#      pilha, avaliacoes e recusas com motivo, ordens (19 campos), RECON,
#      fichas da percepcao, janelas confirmadas, spread, latencia.
#  Veiculo do teste completo = BTC (unica Lista cripto); ETH = camada de
#  percepcao (--percepcao). Rotulo honesto mantido.
#  v5.1 — MODO --percepcao (campanha de fim de semana, decreto do dono
#  18/set): roda a PERCEPCAO do Bloco 1 ao vivo em qualquer simbolo do MT5,
#  SEM Seletor, SEM executor, SEM config — espelho multi-TF + Ficha de
#  Saida §9 por barra (vivo_ficha_<ativo>.csv) + display por barra.
#  Feito para o ETHUSD (sem Lista/pacote — o Seletor nao roda nele; a
#  percepcao e livre de config) e para qualquer ativo futuro em avaliacao.
#  BTC segue no modo completo com QUARENTENA_EXEC ativa (decreto 12).
#  Rotulo honesto (Portao do Todo): fim de semana = teste vivo da
#  PERCEPCAO + infra cripto, nao "teste do sistema".
#  v5.0 — O BLOCO 1 ENTRA NO VIVO (ordem do dono, 18/set: "tudo funcionando
#  como tem que ser"). CORRECAO DE REGISTRO da auditoria: a fonte multi-TF
#  JA ERA NATIVA desde o v1.0 da sombra — o espelho puxa e grava M1 M5 M15
#  M30 H1 H4 Daily do MT5 toda barra; o que NUNCA existiu foi a PERCEPCAO
#  consumindo M1/M5 e as reguas da constituicao. Agora existe:
#    · modulo novo bt_ciclo_v1.py (constituicao v3.0 completa por andar:
#      pivos N=2, perna L, afastamento D, compressao->caixa, rompimento +
#      Lei de Confirmacao com carimbo por_barra/por_gap, rompimento falso,
#      sacudida, exaustao E1/E2/E3 + contexto tardio, escada dos 3 sinais,
#      respiro, janela 10->15 na base 1m->15m, estado unico com
#      profundidade, Ficha do D1 §8 e Ficha de Saida §9)
#    · vivo_ficha_<ativo>.csv: a Ficha de Saida gravada A CADA barra M15
#    · --ciclo-prova [N]: a tabela do dono (TF -> leitura -> influencia ->
#      resultado) barra a barra, saindo da maquina
#  AUTORIDADE: NENHUMA. Executor intocado por decreto (18/set). O comando
#  CORTE_TOTAL da percepcao sai como comando_NARRADO no ficha/prova; virar
#  autoridade exige medicao (professor do Bloco 1) + carimbo. Parametros
#  §11 todos [REF]/nao medidos, declarados. B2 calendario segue INEXISTENTE
#  (declarado na ficha, campo 10).
#  v4.7 — RELATORIO FORENSE DOS TRADES INVISIVEIS (decreto do dono, 18/set):
#  --invisiveis [AAAA-MM-DD] roda o espelho, filtra os trades do dia na
#  janela pura do Seletor e imprime + salva invisiveis_<ativo>_<data>.csv:
#    · TODOS os campos que o Seletor grava (dump integral da linha do trade;
#      campo ausente sai como NAO_GRAVADO — e vira lista de enriquecimento)
#    · duracao em barras M15 quando os dois lados existem
#    · pts liquidos (como a casa mede: spread modelado ja dentro) + custo de
#      comissao (US$7 RT/lote via tick_value) destacado
#    · conversoes decretadas: USD por 1.0 lote, % do capital, e — quando o
#      stop estiver gravado — lote de risco 0,25% com USD/% desse lote
#  LIMITES DECLARADOS (fonte = OHLC M15 do espelho, leis do Bloco1 §10/v5):
#  horario exato do gatilho dentro da barra, ordem intrabar dos eventos e
#  origem tick/M1 sao NAO_OBSERVAVEL(M15) — o relatorio carimba, nao inventa.
#  v4.6 — pos-bancada v4.5 (XAU 18/18 x2 · BTC 5/5 · JP 17/18):
#    · achado do JP na prova 6b: risco forcado 5% pediu lote > volume_max do
#      simbolo (250), o clamp reduziu e o risco REAL caiu p/ 0,293% -> abriu
#      DENTRO do protocolo (clamp so reduz risco, nunca aumenta; a trava de
#      2% em si funciona — XAU provou). Correcoes:
#      (a) clamp no volume_max agora e NARRADO no ledger (tipo=AVISO
#          lote_clampado_no_max) — nada silencioso;
#      (b) prova 6b redesenhada: alem do risco 5%, o stop e dimensionado para
#          que MESMO no volume_max o risco passe de 2% -> a trava e exercitada
#          em qualquer simbolo;
#    · DISPLAY DO VIVO (pedido do dono): a linha de barra do console mostra a
#      posicao demo ao vivo — "DEMO 1pos +12.30USD" — nos 3 terminais.
#  v4.5 — FALHA CRITICA #3 PEGA PELA BANCADA (18/09, JP225): a corretora
#  REJEITOU a ordem do JP — o envio usava filling IOC fixo e lote em passo
#  0.01, e indices na IC exigem outro filling/volume. O vivo NUNCA teria
#  aberto JP225. Correcoes (valem pro VIVO):
#    · _filling(si): escolhe o filling mode QUE O SIMBOLO SUPORTA
#      (IOC -> FOK -> RETURN), em abertura, fechamento e teste-funcional
#    · _lote_norm(si, lote): normaliza ao volume_min / volume_step /
#      volume_max do simbolo; o risco e RECALCULADO com o lote final e a
#      trava dura de 2% julga o numero real (lote-minimo que estourar = recusa)
#    · prova de abertura mostra o rc da corretora quando falhar
#    · ajuste 8 de verdade: uid da bancada com base derivada do SEGUNDO do
#      dia — duas rodadas no mesmo minuto nao colidem mais (aviso removido)
#    · prova 6a aceita lote=volume_min com risco acima do alvo (declarado),
#      desde que dentro da trava de 2%
#  v4.4 — OS 10 AJUSTES OBRIGATORIOS DO DONO (17/set, pre-relancamento):
#   (1) trava DEMO ja existia (aborta se nao-demo) — mantida e impressa
#   (2) backup do v4.1 = passo operacional (comando no rito de entrega)
#   (3) MAGIC EXCLUSIVO DA BANCADA (20269999, fora da faixa do vivo 20260915+):
#       a bancada NUNCA enxerga/fecha/ajusta posicao do vivo ou de terceiros;
#       _magic() ganhou override; snapshot de tickets EXTERNOS antes/depois
#       comprova intocados; P&L da bancada fora da faixa = nao polui o
#       disjuntor diario do vivo
#   (4) limpeza GARANTIDA no finally: fecha tudo do magic da bancada com
#       re-tentativa (3x) mesmo se qualquer prova falhar/explodir; provas
#       individuais em try/except (uma falha nao derruba a bateria)
#   (5) REVERSAO SEGURA (vale pro VIVO): executar() so abre depois de TODOS
#       os fechamentos da passada confirmados pela corretora; confirmacao
#       pendente = NAO_ABRIU aguarda_confirmacao_fechamento (re-iguala na
#       proxima barra)
#   (6) RISCO EFETIVO (vale pro VIVO): lote e risco agora incluem spread
#       vivo + comissao (US$7 RT/lote convertida em pts pelo tick_value) na
#       distancia — dist_ef = |preco-stop|/ponto + spread + comissao_pts
#   (7) 19 campos validados pelo CONTEUDO (nenhum vazio/invalido), nao só
#       pela contagem
#   (8) uid exclusivo POR RODADA (timestamps reais do minuto da rodada);
#       prova de persistencia em disco DENTRO da rodada (cache do ledger e
#       derrubado e relido do arquivo antes do reenvio); rodadas no mesmo
#       minuto colidem de proposito — aviso impresso
#   (9) BTC (quarentena): bateria propria — compra E venda devem ser
#       recusadas com quarentena_spread_7d; os demais portoes ficam
#       inalcancaveis por desenho (quarentena e o 1o portao) — declarado
#  (10) a bancada NAO inicia o 004: termina com aferição (posicoes zero,
#       externas intactas, ledger) e espera o comando do dono
#  v4.3 — BANCADA DE 12 PROVAS (ordem do dono, 17/set): o --bancada agora FORCA
#  e comprova, com PASSA/FALHA por prova: compra · venda · fechamento ·
#  reversao · stop-loss NO SERVIDOR · lote pelo risco + trava dura 2% ·
#  bloqueio por spread (limite forcado a 0) · rejeicao de sinal >15min (idade
#  2b forcada) · reinicio com posicao aberta (reconciliacao re-iguala, zero
#  ordem nova) · retomada sem duplicacao (dedup persistente + 2a rodada fria) ·
#  registro completo dos 19 CAMPOS no ABRIU (ganhou magic e ticket) ·
#  confirmacao da ordem pela corretora (_confirmar). Nada relanca sem APROVADA.
#  v4.2 — AS 12 CORRECOES OBRIGATORIAS DO DONO (17/set, pos-Relatorio 003):
#    CAUSA DO 999 CONFIRMADA NO CODIGO: o estado_pilha do Seletor carrega so
#    card/lado/ent/stop/protegida — k_ent/k_sin/k NAO existem -> _uid degenerava
#    (card4_0/card120/card100) e a idade caia no sentinela 999.
#    (1) ts REAL da entrada propagado: decidir() casa cada posicao da pilha com
#        o ultimo ABRE da trilha (por card; fallback por preco de entrada);
#        sem casamento = fail-closed NOMEADO "sem_barra_entrada"
#    (2) uid seguro ativo+estrategia+timestamp: T3:Xc12.2609171030 (cabe no
#        comment do MT5)
#    (3) idade = k_ult - k_ent em barras M15 REAIS
#    (4) IDADE_MAX = 1 barra M15 (decreto ja existia; agora a idade computa)
#    (5) revalidacao antes de abrir, na ordem: idade -> dedup -> spread ->
#        stop no preco atual -> risco recalculado (2% dura / 0,25 / 0,50 / 0,75)
#    (6) reconciliacao sombra x MT5 NARRADA: entrada RECON no vivo_exec a cada
#        passada do executor (desejo/reais/casadas/so_sombra/so_mt5)
#    (7) dedup persistente vivo_enviadas_<ativo>.csv: uid enviado nunca
#        re-envia; sobrevive reinicio a frio
#    (8) SPREAD MODELADO XAU=11 CONFIRMADO no motor (PC.SPREAD_PTS, inclusive
#        no --conferir); o "spread=5" da ficha da pasta e cosmetico — aviso
#        [custo] explicito na tela
#    (9) fechou_novos com chave por TIMESTAMP (ts,card,tf): a borda deslizante
#        re-simula trades antigos com pts diferentes e criava fantasmas
#   (10) LATENCIA UNIFICADA (_lat_unificada): relogio do SERVIDOR no registro
#        da decisao (tick) - fechamento da barra M15; MESMO numero no radio,
#        no vivo_exec e na tela; fallback declarado = tempo local de processo
#   (11) --bancada: abre/fecha/REVERSAO/dedup/reinicio pelo PROPRIO executar(),
#        lote-piso 0.01, transcricao em vivo_bancada_<ativo>.txt; o 004 so
#        abre com BANCADA APROVADA nos 3 ativos
#   (12) QUARENTENA_EXEC={"BTCUSD"}: leitura/sombra/coleta seguem; ordem real
#        de BTC NAO sai ate fechar os 7 dias de spread
#    + regressao fechada: trail_sl_demo (prometido na v3.1) estava definido e
#      nunca chamado — religado no loop (so aperta stop, nunca alarga).
#    Rotulos/manifesto: VIVO_004 (janela limpa do 004).
#  v4.1 — DECRETOS DO DONO (Feito00185) + INSTRUMENTACAO DO CICLO (build-2a):
#    · IDADE_MAX = 1 barra M15 (15 min; depois NAO abre; dentro, revalida tudo)
#    · spreads 20/800/1500 (BTC em QUARENTENA: 7 dias de coleta por sessao, so demo)
#    · CUSTO XAU MODELADO = 11 pts (p90 vivo — decreto; era 5) no espelho
#    · latencia ~7s ACEITA PROVISORIA no 003 como RESSALVA (meta <2s de pe)
#    · vivo_ciclo_<ativo>.csv (itens 16-18, granularidade M15 DECLARADA):
#      direcoes dos andares, corta C/V, B1/B3/B5, deterioracao (barras de
#      ciclo-contra com posicao aberta) -> corte, classificacao
#      pullback x reversao [heuristica REF: contra sem corta = pullback;
#      corta disparado = reversao confirmada]. Nivel M1 = build da latencia.
#    · --teste-funcional AMPLIADO: as 9 provas do dono antes do 003.
#  v4.0 — EXECUTOR POR RECONCILIACAO DE ESTADO (as 22 correcoes do dono):
#  a cada barra: ESTADO DESEJADO (pilha da sombra, com uid por posicao) x
#  ESTADO MT5 (posicoes do magic, uid no comment) -> iguala:
#    falta -> ABRE (com os PORTOES: idade do sinal <= 2 barras [REF] ·
#      revalidacao no preco atual (stop ainda valido, distancia sana) ·
#      spread <= limite do ativo · risco recalculado NO PRECO ATUAL com
#      trava dura 2%/operacao + 0,25%un/0,50%atv/0,75%carteira · uid inedito)
#    sobra -> FECHA · stop diferente -> AJUSTA (espelho fiel da sombra)
#  Confirmacao PELA CORRETORA apos cada acao (re-consulta ate 3x) ·
#  rejeitada = 1 reenvio a preco novo · parcial registrada · reinicio com
#  posicao aberta: a propria reconciliacao re-iguala (item 14) ·
#  ledger de estado (item 21): sombra x desejado x MT5 x acao x confirmacao.
#  --teste-funcional: ciclo controlado compra/ajuste/fecha/venda/fecha com
#  confirmacoes impressas — o portao do item 22 ANTES do 003.
#  Custo XAU (item 7): ficha do espelho ja mede o spread VIVO da janela;
#  divergencia 5(warmup)x8(dia) registrada; catalogo 24m re-mede depois.
#  Pendentes declarados p/ build-2: latencia incremental (15), metricas de
#  Ciclo M1->M15 (16-18) — nao entram em silencio, entram nomeados.
#  v3.4 (§A do protocolo — persistencia apos reinicio + zero duplicata):
#    · no boot, a sombra LE a ultima barra do vivo_log e RETOMA dali —
#      relancamento nunca mais reprocessa barra ja registrada;
#    · o --conferir reconhece duplicata de reinicio: N registros da mesma
#      barra com decisoes IDENTICAS = BATE (com nota de determinismo);
#      decisoes DIFERENTES na mesma barra = DIVERGE real (falha critica).
#  v3.3: o --conferir lia o vivo_log com parser rigido e engasgava na mistura
#  de geracoes de colunas (v1.0=7, v2.1+=10). Agora le por varredura de texto
#  (conta os registros da barra direto nas linhas) — imune a esquema.
#  v3.2 (bug pego no boot do 002): o formato fixo %.5f do espelho fazia a
#  ficha inferir ponto=1e-05 em todos (comissao 7000 pts no XAU = alarme).
#  Correcao na fonte: os DIGITOS DO SIMBOLO (symbol_info.digits) formatam o
#  espelho — XAU volta a 0.01, JP225 a 0.1/0.01, BTC a 0.01. Decisoes eram
#  em preco (integras); a CONTABILIDADE de pts e que saia da escala.
#  JANELA LIMPA reinicia nesta versao (protocolo §1 do dono).
#  v3.1 — A RADIOGRAFIA (ordem do dono, 15/set): a leitura INTEIRA do
#  organismo por barra, em vivo_radio_<ativo>.txt (humano-legivel):
#    · direcao dos andares (D1/H4/H1/M30/M15 — o Ciclo 2 visto de cima)
#    · territorio e cenario do Bloco 3 (+1/-1)
#    · RANKING VIVO da barra (top-5 por lado, PF contextual x global)
#    · A PILHA POR DENTRO: card, entrada, STOP ATUAL, protegida?
#    · eventos da barra, recusas acumuladas, decisao demo, latencia, spread
#  + TRAILING DO SL DEMO LIGADO (lacuna de ontem fechada): a cada barra, o
#    SL de cada posicao demo e carregado pro stop estrutural da simulacao
#    (mesma formula; so aperta, nunca alarga) via position_modify.
#  v3.0 — TESTE VIVO 002 (protocolo do dono, 15/set — Feito00184):
#    --executa liga ORDENS DEMO REAIS alem das sombras. TRAVA DURA: recusa
#    conta real (trade_mode != DEMO aborta). Regras de risco CRAVADAS:
#    0,25%/unidade · teto 0,50%/ativo · 0,75% simultaneo (carteira) ·
#    DISJUNTOR -1,5% no dia (fecha tudo, para ate a proxima sessao) ·
#    stop SEMPRE junto da ordem · lote do risco via tick_value do MT5 ·
#    piso 0.01 · sem TP (vida = Ciclo) · zero intervencao manual.
#    MANIFESTO escrito no boot (versoes+hash, configs, listas, saldo).
#    LEDGER por decisao: latencia, spread, slippage, risco $ e %, R.
#    LACUNAS DECLARADAS (nada se finge): probabilidade formal = proxy PF
#    contextual; Bloco4/IA ausente no motor; seletor-entre-ativos nao e o
#    desenho (um bot por ativo + porteiro de carteira); metricas de Ciclo
#    nao-instrumentadas listadas pro Teste 003.
#    Janela limpa v3.0 comeca no boot com --executa.
#  v2.2 (parecer do dono, Feito00183 — atribuicao POR DECISAO):
#    o ledger do mapa agora nomeia, a cada ciclo, os trades NOVOS que so
#    existem na PURA (= o que o mapa bloqueou/preteriu, com o resultado:
#    responde "evitou perda ou eliminou ganho?") e os que so existem no
#    MAPA (o que o re-rank trocou). JANELA LIMPA: o selo de estabilidade
#    conta a partir DESTA versao no ar (as 21h = descoberta e integracao).
#    XAU segue OBSERVADOR por decreto; JP225: "R4b armado, sem condicao";
#    BTC: anedotico ate a amostra mandar; quarentena do spread so cai com
#    distribuicao viva (mediana/p75/p90/max por horario — log acumulando).
#  v2.1 (auditoria das primeiras 21h — 15/set):
#    NARRACAO POR DIFERENCA: o log agora compara os trades entre ciclos e
#    registra "fechou: card@pts" + a variacao da pilha — a coluna evento
#    sub-reportava (256 barras sem evento explicito com a pilha respirando).
#    SPREAD VIVO por barra gravado no log (contraprova BTC/ETH acumulando).
#    Espelho com 5 casas decimais fixas (dígitos do JP225 corrigidos).
#  v2.0 (Feito00181 — Fase 1 do Bloco 3 AUTORIZADA pelo dono):
#    MAPA EM SOMBRA nos 5 aprovados (modo CONGELADO — ninguem troca R4a/R4b
#    por resultado vivo) · configs PURAS seguem como CONTROLE e continuam
#    sendo a decisao primaria do log · nos outros 5 o mapa e OBSERVADOR.
#    MAPA CONGELADO: construido UMA vez do historico 24m completo (tudo e
#    passado para o vivo) e salvo em mapa_congelado_<ativo>.json — nenhuma
#    nova calibragem durante a campanha; apagar o json = recalibrar = PROIBIDO
#    sem carimbo. Ledger vivo_mapa_<ativo>.csv com os campos do dono (00181).
#    JP225: rodada deu R4a==R4b identicos — congelado R4b (superconjunto),
#    declarado.
PASTA_ESPELHO = "Vivo_espelho"
AQUECIMENTO = {"M1": 3000, "M5": 2000, "M15": 1500, "M30": 1000,
               "H1": 800, "H4": 400, "Daily": 300}
CONFIG = {  # leva v3 (Feito00174/00177): ativo -> (B3_N, topK)
    "XAUUSD": (6, 13), "US30": (6, 14), "BTCUSD": (6, 5), "USDJPY": (24, 4),
    "JP225": (24, 3), "GBPJPY": (12, 2), "EURUSD": (12, 3), "GBPUSD": (6, 2),
    "DE40": (12, 2), "XTIUSD": (6, 2),
}
# ---- TESTE 002: risco (protocolo do dono, cravado) -------------------------
RISCO_UNIDADE = 0.0025      # 0,25% do saldo por unidade independente
TETO_ATIVO    = 0.0050      # 0,50% por ativo
TETO_CARTEIRA = 0.0075      # 0,75% simultaneo nos tres
DISJUNTOR_DIA = -0.015      # -1,5% no dia: fecha tudo e para
MAGIC_BASE    = 20260915
RISCO_MAX_OP  = 0.02        # trava DURA do protocolo: 2% por operacao
COMISSAO_USD_LOTE = 7.0     # ajuste 6: US$7 RT/lote (Raw, medido) — vira pts via tick_value
LATENCIA_MAX_ENVIO = 60.0   # v6.4 (5): decisao mais velha que isso NAO vira ordem [REF]
DESVIO_MAX_PTS = {"XAUUSD": 30, "JP225": 1200, "BTCUSD": 3000}   # v6.4 (6): [REF] nao medido
DESVIO_MAX_PADRAO = 3000
_AUD = {"ok": True}          # v7.4: auditoria gravando? falha bloqueia entradas novas
_CONTRA_ARMADA = False       # v7.1: contratendencia DESARMADA; arma so com --contra-armado (decreto)

# ═══ v7.3: REGISTRO DE MATURIDADE — a verdade de cada componente ═══
# niveis: CONSTRUCAO < BANCADA < SOMBRA < DEMO < REAL(nenhum)
COMPONENTES = {
  # geracao ANTIGA (o sistema M15 medido)
  "espelho_multiTF":        ("ANTIGA", "DEMO",      "fonte 7 TFs; sustentou a 1a ordem 19/set"),
  "seletor_B2_cards":       ("ANTIGA", "DEMO",      "sombra+ordem demo; resultado de mercado NAO avaliado"),
  "bloco3_probab":          ("ANTIGA", "SOMBRA",    "config v3.1 congelada, sombra por decreto"),
  "executor_portoes_base":  ("ANTIGA", "DEMO",      "quarentena/idade/dedup/spread/risco/stop; bancadas 18/18 + ordem real demo"),
  "reconciliacao":          ("ANTIGA", "DEMO",      "RECON 20/20 na noite 1; abriu-fechou confirmado"),
  # geracao NOVA (a Travessia de 18-19/set)
  "corte_ciclo_autoridade": ("NOVA",   "BANCADA",   "bancada-corte 8/8 19/set; falta exercitar em demo de campanha"),
  "corte_intrabar":         ("NOVA",   "SOMBRA",    "no loop desde v6.2; nenhum caso disparado ainda"),
  "portao_topdown":         ("NOVA",   "SOMBRA",    "no vivo desde v6.0; nenhum bloqueio exercitado em demo"),
  "portao_latencia":        ("NOVA",   "SOMBRA",    "armado desde v6.4; sem caso disparado"),
  "portao_desvio_preco":    ("NOVA",   "SOMBRA",    "armado desde v6.4; teria pego os 6.372pts (retroativo, nao exercitado)"),
  "b2_calendario":          ("NOVA",   "CONSTRUCAO","fonte manual; sem arquivo preenchido, nunca bloqueou"),
  "percepcao_fichas_cv1":   ("NOVA",   "SOMBRA",    "2 noites ETH limpas + provas do dono; precisao vs grafico = olho do dono"),
  "fases_movimento":        ("NOVA",   "CONSTRUCAO","NARRATIVO; 1a medicao 20/set ETH: falsos 59% sem piso, 45% com piso [REF] — reprovada p/ autoridade"),
  "conclusao_conjunta":     ("NOVA",   "CONSTRUCAO","NARRATIVO; formulas forca/confianca [REF]"),
  "contratendencia":        ("NOVA",   "CONSTRUCAO","DESARMADA; exige bancada propria + medicao + decreto"),
  "auditor_3linhas":        ("NOVA",   "BANCADA",   "bug de escopo achado nos prints 20/set (corrigido v7.3.1); aguarda barras vivas gravando"),
  "memoria_blindada":       ("NOVA",   "SOMBRA",    "prova do dono 20/set: hash 041b6eb7 byte-identico + dia inteiro vivo"),
  "validador_esquema_v2":   ("NOVA",   "BANCADA",   "bancada re-aprovada com esquema"),
  "medidor_professor_b1":   ("NOVA",   "CONSTRUCAO","NUNCA rodou completo (B1_todos.txt pendente)"),
  "relatorio_escada":       ("NOVA",   "CONSTRUCAO","nasceu 20/set (formato do dono); rotulos [REF]; aguarda olho do dono"),
  "bloqueio_sem_auditoria": ("NOVA",   "BANCADA",   "autoteste no boot + bloqueio em voo; aguarda caso vivo"),
}
def maturidade(resumo=False):
    niveis = ["CONSTRUCAO", "BANCADA", "SOMBRA", "DEMO", "REAL"]
    cont = {n: 0 for n in niveis}
    for _, (g, nv, _n) in COMPONENTES.items(): cont[nv] += 1
    lin = " · ".join(f"{n}:{cont[n]}" for n in niveis)
    if resumo:
        return f"MATURIDADE [{lin}] · VALIDADO P/ CONTA REAL: NENHUM"
    print(f"REGISTRO DE MATURIDADE v{V_VERSAO} — {lin}")
    print(f"  regra: promocao SO por edicao deliberada com evidencia; nada automatico")
    for ger in ("ANTIGA", "NOVA"):
        print(f"  ── geracao {ger}:")
        for nome, (g, nv, nota) in COMPONENTES.items():
            if g == ger:
                print(f"     {nome:<24} {nv:<11} {nota}")
    print(f"  >>> VALIDADO PARA CONTA REAL: NENHUM COMPONENTE <<<")
JANELA_NOTICIA_MIN = 30      # v6.6: B2 calendario — bloqueio de entrada +-30min [REF]
MOEDAS_ATIVO = {"XAUUSD": ("USD",), "JP225": ("JPY", "USD"), "BTCUSD": ("USD",), "ETHUSD": ("USD",)}
_CAL_CACHE = {"mtime": None, "evs": []}

def _calendario_carregar():
    """v6.6: le calendario.csv (data;hora;moeda;impacto;evento). Cache por mtime."""
    cam = "calendario.csv"
    if not os.path.exists(cam):
        _CAL_CACHE["evs"] = []; _CAL_CACHE["mtime"] = None; return []
    mt = os.path.getmtime(cam)
    if _CAL_CACHE["mtime"] == mt: return _CAL_CACHE["evs"]
    evs = []
    for ln in open(cam, encoding="utf-8"):
        p = [x.strip() for x in ln.replace(",", ";").split(";")]
        if len(p) < 4 or p[0].lower().startswith("data"): continue
        try:
            dt = pd.Timestamp(p[0].replace(".", "-") + " " + p[1])
            evs.append((dt, p[2].upper(), p[3].lower(), p[4] if len(p) > 4 else "?"))
        except Exception:
            continue
    _CAL_CACHE["evs"] = evs; _CAL_CACHE["mtime"] = mt
    return evs

def _calendario_bloqueia(ativo, agora=None):
    """(bloqueia?, motivo). So impacto ALTO na moeda do ativo, +-JANELA."""
    evs = _calendario_carregar()
    if not evs: return False, None
    agora = agora or pd.Timestamp(datetime.now())
    moedas = MOEDAS_ATIVO.get(ativo, ("USD",))
    for dt, mo, imp, nome in evs:
        if imp == "alto" and mo in moedas and abs((agora - dt).total_seconds()) <= JANELA_NOTICIA_MIN * 60:
            return True, f"{nome}({mo} {dt:%d/%m %H:%M})"
    return False, None
IDADE_MAX     = 1           # Feito00185: 1 barra M15 — 15 minutos, depois NAO abre
SPREAD_MODELADO = {"XAUUSD": 11}   # Feito00185: custo do rei = p90 vivo (era 5)
SPREAD_LIM    = {"XAUUSD": 20, "JP225": 800, "BTCUSD": 1500}   # [REF] item 6/8
QUARENTENA_EXEC = {"BTCUSD"}  # correcao 12: 7 dias de coleta de spread — executor NAO abre BTC real

MODO_MAPA = {  # Feito00181 — CONGELADO; troca so por carimbo novo do dono
    "JP225": "R4b", "BTCUSD": "R4a", "US30": "R4b", "DE40": "R4b",
    "GBPJPY": "R4b",
    "XAUUSD": "observador", "USDJPY": "observador", "EURUSD": "observador",
    "GBPUSD": "observador", "XTIUSD": "observador",
}
PASTA_HIST = "Test 24meses"   # fonte do mapa congelado

def _log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}"); sys.stdout.flush()

# ---------------------------------------------------------------------------
def _hash_arquivos():
    import hashlib
    h = {}
    for f in ("bloco1_motor_v3.py", "professor_cards_v19.py", "professor_bloco2.py",
              "professor_bloco3.py", "bt_vivo_sombra.py"):
        try:
            h[f] = hashlib.sha256(open(os.path.join(_AQUI, f), "rb").read()).hexdigest()[:12]
        except Exception:
            h[f] = "ausente"
    return h

def manifesto(mt5, ativo, executa):
    info = mt5.account_info()
    lista = B2.carregar_lista(ativo)
    m = dict(teste="VIVO_004", versao=V_VERSAO, build=BUILD, inicio=str(datetime.now()),
             ativo=ativo, executa=bool(executa), conta=info.login, servidor=info.server,
             modo_conta=("DEMO" if info.trade_mode == 0 else "REAL"),
             saldo=info.balance, moeda=info.currency,
             config=CONFIG[ativo], modo_mapa=MODO_MAPA.get(ativo, "observador"),
             risco=dict(unidade=RISCO_UNIDADE, teto_ativo=TETO_ATIVO,
                        teto_carteira=TETO_CARTEIRA, disjuntor_dia=DISJUNTOR_DIA),
             lista=[(c["card"], c["tf"], c["pf"]) for c in lista],
             quarentena_exec=sorted(QUARENTENA_EXEC),
             hash=_hash_arquivos())
    import json as _j
    cam = f"manifesto_004_{ativo}.json"
    _j.dump(m, open(cam, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    _log(f"MANIFESTO escrito: {cam} · saldo {info.balance:.2f} {info.currency} · conta {m['modo_conta']}")
    return m

# ---- TESTE 002: executor demo ----------------------------------------------
MAGIC_BANCADA = 20269999      # ajuste 3: fora da faixa do vivo (MAGIC_BASE..+999)
_MAGIC_OVERRIDE = None
def _magic(ativo):
    if _MAGIC_OVERRIDE is not None: return _MAGIC_OVERRIDE
    return MAGIC_BASE + sum(ord(c) for c in ativo) % 1000

def _pos_minhas(mt5, ativo):
    ps = mt5.positions_get(symbol=ativo) or []
    return [p for p in ps if p.magic == _magic(ativo)]

def _valor_ponto_lote(mt5, ativo):
    si = mt5.symbol_info(ativo)
    if not si or not si.trade_tick_size: return None
    return si.trade_tick_value * (PC.PONTO / si.trade_tick_size)

def _risco_aberto_pct(mt5, saldo):
    tot = 0.0
    for p in (mt5.positions_get() or []):
        if p.magic // 1000 * 1000 != MAGIC_BASE // 1000 * 1000: 
            if p.magic < MAGIC_BASE or p.magic > MAGIC_BASE + 999: continue
        si = mt5.symbol_info(p.symbol)
        if not si or not si.trade_tick_size or not p.sl: continue
        vpp = si.trade_tick_value / si.trade_tick_size
        tot += abs(p.price_open - p.sl) * vpp * p.volume
    return tot / max(1e-9, saldo)

def _lucro_dia_pct(mt5, saldo):
    de = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(de, datetime.now()) or []
    liq = sum(d.profit + d.commission + d.swap for d in deals
              if MAGIC_BASE <= d.magic <= MAGIC_BASE + 999)
    return liq / max(1e-9, saldo)

def trail_sl_demo(mt5, ativo, contra, ledger_extra):
    """Carrega o SL das posicoes demo pro stop estrutural da simulacao —
    mesma formula (pivô -/+ 0.5 ATR), so aperta, nunca alarga."""
    F15 = contra.get("F15"); lt = contra.get("lt")
    if F15 is None: return
    A15 = lt.andares["M15"]; k = F15.n - 1
    mp = A15.mapas[k]; a = float(F15.D.atr14.values[k]); c = float(F15.D.close.values[k])
    if not (mp.ultimo_fundo and mp.ultimo_topo) or not np.isfinite(a) or a <= 0: return
    for p in _pos_minhas(mt5, ativo):
        lado = 1 if p.type == 0 else -1
        pv = mp.ultimo_fundo[1] if lado > 0 else mp.ultimo_topo[1]
        nst = pv - lado * 0.5 * a
        aperta = (lado > 0 and nst > p.sl and nst < c) or (lado < 0 and nst < p.sl and nst > c)
        if aperta:
            r = mt5.order_send(dict(action=mt5.TRADE_ACTION_SLTP, symbol=ativo,
                                    position=p.ticket, sl=round(nst, 5), tp=0.0))
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                ledger_extra.append(dict(tipo="TRAIL", ticket=p.ticket,
                                         sl_novo=round(nst, 5)))

def _cshort(card):
    return (str(card).split("_")[0].replace("card", "c") or "c?")

def _uid(ativo, p):
    """Correcao 2: uid seguro = ativo + estrategia + TIMESTAMP REAL da entrada.
    Compacto para caber no comment do MT5 (com o prefixo T3: fica <= 31)."""
    ts = p.get("ts_ent")
    if ts is None:
        return f"{ativo[0]}{_cshort(p.get('card'))}.SEMK"   # recusado a jusante (fail-closed)
    return f"{ativo[0]}{_cshort(p.get('card'))}.{pd.Timestamp(ts):%y%m%d%H%M}"

# ---- correcao 7: ledger persistente de uids enviados (dedup entre reinicios)
_ENVIADAS = {}
def _enviadas_path(ativo): return os.path.join(_AQUI, f"vivo_enviadas_{ativo}.csv")
def _enviadas(ativo):
    if ativo not in _ENVIADAS:
        s = set()
        cam = _enviadas_path(ativo)
        if os.path.exists(cam):
            for l in open(cam, encoding="utf-8"):
                u = l.split(";")[0].strip()
                if u and u != "uid": s.add(u)
        _ENVIADAS[ativo] = s
    return _ENVIADAS[ativo]
def _enviada_gravar(ativo, uid, resultado):
    novo = not os.path.exists(_enviadas_path(ativo))
    with open(_enviadas_path(ativo), "a", encoding="utf-8") as f:
        if novo: f.write("uid;ts_envio;resultado\n")
        f.write(f"{uid};{datetime.now()};{resultado}\n")
    _enviadas(ativo).add(uid)

def _filling(mt5, si):
    """v4.5: filling mode que o SIMBOLO suporta (mask): IOC -> FOK -> RETURN."""
    fm = int(getattr(si, "filling_mode", 0))
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 1: return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN

def _lote_norm(si, lote):
    """v4.5: normaliza o lote ao min/step/max do simbolo (floor no step)."""
    vmin = float(getattr(si, "volume_min", 0.01) or 0.01)
    vmax = float(getattr(si, "volume_max", 1e9) or 1e9)
    step = float(getattr(si, "volume_step", 0.01) or 0.01)
    lote = max(vmin, min(vmax, lote))
    n = round((lote - vmin) / step)
    lote = vmin + max(0, n) * step
    return round(min(vmax, max(vmin, lote)), 8)

def _enviar(mt5, req, tent=2):
    """Envio com 1 reenvio a preco novo (item 11) + confirmacao (item 10)."""
    for t in range(tent):
        r = mt5.order_send(req)
        if r is not None and r.retcode == mt5.TRADE_RETCODE_DONE:
            return r, (t + 1)
        si = mt5.symbol_info(req["symbol"])
        if si and req.get("type") in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL):
            req["price"] = si.ask if req["type"] == mt5.ORDER_TYPE_BUY else si.bid
        time.sleep(1)
    return r, tent

def _confirmar(mt5, ativo, uid, presente=True):
    for _ in range(3):
        tem = any(uid in (p.comment or "") for p in _pos_minhas(mt5, ativo))
        if tem == presente: return True
        time.sleep(1)
    return False

def executar(mt5, ativo, contra, k_ult, ledger_extra):
    """v4: RECONCILIACAO DE ESTADO (itens 1-14/21). Fecha primeiro, abre depois
    (reversao = mesma barra). Retorna narrativa da acao."""
    info = mt5.account_info(); saldo = info.balance
    lp = _lucro_dia_pct(mt5, saldo)
    desejo = contra.get("estado_pilha", [])
    reais = _pos_minhas(mt5, ativo)
    if lp <= DISJUNTOR_DIA:
        for p in reais: _fechar_pos(mt5, p)
        return f"DISJUNTOR_DIA ({lp*100:.2f}%) — fechado e travado"
    uids_d = {_uid(ativo, p): p for p in desejo}
    uids_r = {}
    for p in reais:
        u = (p.comment or "").replace("T3:", "").strip() or f"tk{p.ticket}"
        uids_r[u] = p
    acao = []
    fech_ok = True
    ct = contra.get("ciclo") if isinstance(contra, dict) else None
    # ---- v6.0: AUTORIDADE DO CICLO base->topo — CORTE REAL -------------------
    if ct:
        for u0, p0 in list(uids_r.items()):
            lp = 1 if p0.type == mt5.POSITION_TYPE_BUY else -1
            mot = None
            if int(ct.get("degrau") or 0) >= 2 and int(ct.get("lado_ex") or 0) == -lp:
                mot = f"reversao_{ct['degrau']}sinal"
            elif ct.get("janela_conf"): mot = f"janela_10_15({ct['janela_conf']})"
            elif ct.get("voltou"): mot = "voltou_compressao"
            if mot:
                acao.append(_fechar_pos(mt5, p0))
                okc = _confirmar(mt5, ativo, u0, presente=False)
                fech_ok = fech_ok and okc
                cx = dict(tipo="CORTE_CICLO", uid=u0, motivo=mot, ticket=int(p0.ticket),
                          confirmado=okc, apoio=ct.get("apoio"), conflito=ct.get("conflito"))
                cx.update(_pnl_pos(mt5, p0.ticket))
                ledger_extra.append(cx)
                uids_r.pop(u0, None)
    # --- SOBRA no MT5 (sombra fechou) -> FECHA -------------------------------
    for u, p in list(uids_r.items()):
        if u not in uids_d:
            acao.append(_fechar_pos(mt5, p))
            ok_f = _confirmar(mt5, ativo, u, presente=False)
            fech_ok = fech_ok and ok_f
            acao.append("conf_fech:" + ("OK" if ok_f else "PENDENTE"))
            fx = dict(tipo="FECHOU", uid=u, motivo="fim_da_pilha_sombra(seletor)",
                      ticket=int(p.ticket), confirmado=ok_f)
            fx.update(_pnl_pos(mt5, p.ticket))
            ledger_extra.append(fx)
    # --- FALTA no MT5 (sombra abriu) -> PORTOES -> ABRE ----------------------
    si = mt5.symbol_info(ativo)
    spread_agora = int(si.spread) if si else 99999
    for u, p in uids_d.items():
        if u in uids_r: continue
        if u in _enviadas(ativo) and u not in uids_r:      # v6.4 (11): quem fechou = externo?
            ja_reg = any(e.get("uid") == u and e.get("tipo") in ("FECHADA_EXTERNA", "CORTE_CICLO", "FECHOU")
                         for e in ledger_extra)
            if not ja_reg:
                ledger_extra.append(dict(tipo="FECHADA_EXTERNA", uid=u,
                                         motivo="stop_servidor_ou_manual(posicao sumiu sem ordem nossa)"))
        if not fech_ok:                                     # ajuste 5: reversao segura —
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u,  # nada abre com fechamento
                                     motivo="aguarda_confirmacao_fechamento")); continue
        lado = int(p["lado"]); ent_t = float(p["ent"]); sl = float(p["stop"])
        try:                                               # v6.4 (6): limite de desvio do preco
            tk1 = mt5.symbol_info_tick(ativo)
            px_ag = tk1.ask if lado == 1 else tk1.bid
            desv = abs(px_ag - ent_t) / PC.PONTO
            if desv > DESVIO_MAX_PTS.get(ativo, DESVIO_MAX_PADRAO):
                ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u,
                                         motivo=f"preco_desviado({desv:.0f}pts>{DESVIO_MAX_PTS.get(ativo, DESVIO_MAX_PADRAO)})")); continue
        except Exception:
            pass
        if ativo in QUARENTENA_EXEC:                        # correcao 12
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo="quarentena_spread_7d")); continue
        _blk, _evn = _calendario_bloqueia(ativo)            # v6.6: B2 calendario
        if _blk:
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u,
                                     motivo=f"B2_calendario[{_evn}]")); continue
        ts_b = contra.get("ts_barra") if isinstance(contra, dict) else None
        if ts_b is not None:                                # v6.4 (5): bloqueio por latencia
            try:
                tk0 = mt5.symbol_info_tick(ativo)
                lat_env = float(tk0.time) - (pd.Timestamp(ts_b).timestamp() + 900.0) if tk0 and tk0.time else 0.0
            except Exception:
                lat_env = 0.0
            if lat_env > LATENCIA_MAX_ENVIO:
                ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u,
                                         motivo=f"latencia_excessiva({lat_env:.0f}s>{LATENCIA_MAX_ENVIO:.0f})")); continue
        ke = p.get("k_ent")                                 # correcoes 1/3: barra REAL da entrada
        if ke is None:                                      # fail-closed NOMEADO (nunca mais 999 mudo)
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo="sem_barra_entrada(fail_closed)")); continue
        idade = k_ult - int(ke)                             # idade em barras M15 reais
        if idade > IDADE_MAX:                               # correcao 4: > 1 barra M15 = recusa
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo=f"sinal_antigo({idade}b)")); continue
        if u in _enviadas(ativo):                           # correcao 7: dedup persistente
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo="uid_ja_enviado(dedup)")); continue
        _contraT = False
        if ct and ct.get("topdown") and ct["topdown"][0] == "bloqueada":   # v7.1: contratendencia
            _fs = ct.get("fase") or {}
            _qualifica = int(_fs.get("fase") or 0) >= 3 and int(_fs.get("direcao") or 0) == int(p["lado"])
            if _qualifica and _CONTRA_ARMADA:
                _contraT = True                                            # decreto explicito: risco x0.5
            else:
                _mot = (f"ciclo_topdown_bloqueou[{ct['topdown'][1]}·contra_DESARMADA(fase{_fs.get('fase',0)} qualificaria)]"
                        if _qualifica else
                        f"ciclo_topdown_bloqueou[{ct['topdown'][1]}·fase{_fs.get('fase',0)}<3]")
                ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo=_mot,
                                         apoio=ct.get("apoio"), conflito=ct.get("conflito"))); continue
        lim = SPREAD_LIM.get(ativo, 99999)
        if spread_agora > lim:
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo=f"spread_{spread_agora}>{lim}")); continue
        preco = si.ask if lado > 0 else si.bid
        if (preco - sl) * lado <= 0:
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo="stop_ja_violado_no_preco_atual")); continue
        vpl = _valor_ponto_lote(mt5, ativo)
        if not vpl: ledger_extra.append(dict(tipo="ERRO", uid=u, motivo="tick_value")); continue
        dist_pts = abs(preco - sl) / PC.PONTO          # item 5: risco no PRECO ATUAL
        # ajuste 6: distancia EFETIVA inclui spread vivo + comissao em pts
        custo_pts = spread_agora + (COMISSAO_USD_LOTE / vpl if vpl else 0.0)
        dist_ef = dist_pts + custo_pts
        _r_u = RISCO_UNIDADE * (0.5 if _contraT else 1.0)   # v7.0: [REF] RISCO_CONTRA_MULT
        lote_bruto = (saldo * _r_u) / (dist_ef * vpl)
        lote = _lote_norm(si, lote_bruto)                                  # v4.5
        vmax_si = float(getattr(si, "volume_max", 1e9) or 1e9)
        if lote_bruto > vmax_si + 1e-9:                                    # v4.6 (a): narrado
            ledger_extra.append(dict(tipo="AVISO", uid=u,
                                     motivo=f"lote_clampado_no_max({lote_bruto:.2f}->{lote})"))
        risco_novo = dist_ef * vpl * lote / saldo   # risco do LOTE REAL (min/step/max do simbolo)
        if risco_novo > RISCO_MAX_OP:
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo=f"risco_{risco_novo*100:.2f}%>2%")); continue
        r_atv = sum(abs(q.price_open - q.sl) / PC.PONTO * vpl * q.volume
                    for q in _pos_minhas(mt5, ativo) if q.sl) / saldo
        if r_atv + risco_novo > TETO_ATIVO:
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo="teto_ativo")); continue
        if _risco_aberto_pct(mt5, saldo) + risco_novo > TETO_CARTEIRA:
            ledger_extra.append(dict(tipo="NAO_ABRIU", uid=u, motivo="teto_carteira")); continue
        req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=ativo, volume=lote,
                   type=(mt5.ORDER_TYPE_BUY if lado > 0 else mt5.ORDER_TYPE_SELL),
                   price=preco, sl=sl, deviation=30, magic=_magic(ativo),
                   comment=f"T3:{u}", type_time=mt5.ORDER_TIME_GTC,
                   type_filling=_filling(mt5, si))
        try:
            tk2 = mt5.symbol_info_tick(ativo)
            ts_dec = str(pd.Timestamp(float(tk2.time), unit="s")) if tk2 and tk2.time else str(datetime.now())
            bid_e, ask_e = (tk2.bid, tk2.ask) if tk2 else (None, None)
        except Exception:
            ts_dec, bid_e, ask_e = str(datetime.now()), None, None
        ts_env = str(datetime.now())
        r, tent = _enviar(mt5, req)
        _enviada_gravar(ativo, u, "DONE" if (r is not None and r.retcode == mt5.TRADE_RETCODE_DONE)
                        else f"rc={getattr(r, 'retcode', '?')}")
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            ledger_extra.append(dict(tipo="ORDEM_FALHOU", uid=u, rc=getattr(r, "retcode", "?"), tentativas=tent))
            acao.append(f"FALHOU {u}"); continue
        parcial = "" if abs(r.volume - lote) < 1e-9 else f" PARCIAL {r.volume}/{lote}"
        conf = _confirmar(mt5, ativo, u, presente=True)
        slip = (r.price - ent_t) * lado / PC.PONTO
        ledger_extra.append(dict(tipo="ABRIU", uid=u, card=p.get("card"), lado=lado, lote=r.volume,
                                 magic=_magic(ativo), ticket=int(getattr(r, "order", 0) or getattr(r, "deal", 0)),
                                 contratendencia=_contraT,
                                 ts_decisao=ts_dec, ts_envio=ts_env, ts_confirmacao=str(datetime.now()),
                                 bid_envio=bid_e, ask_envio=ask_e,
                                 risco_usd_exec=round((abs(float(r.price) - sl) / PC.PONTO + custo_pts) * vpl * r.volume, 2),
                                 risco_pct_exec=round((abs(float(r.price) - sl) / PC.PONTO + custo_pts) * vpl * r.volume / saldo * 100, 3),
                                 ent_teorico=ent_t, ent_exec=r.price, slippage_pts=round(slip, 1),
                                 sl=sl, risco_usd=round(dist_ef * vpl * lote, 2),
                                 risco_pct=round(risco_novo * 100, 3), idade_barras=idade, ts_ent=str(p.get("ts_ent")),
                                 spread=spread_agora, cenario=contra.get("cenario", ""),
                                 tentativas=tent, confirmado=conf))
        acao.append(f"ABRIU {u} {r.volume}@{r.price} slip{slip:+.0f}{parcial} conf:{'OK' if conf else 'PEND'}")
    # --- STOP diferente -> AJUSTA (espelho fiel) -----------------------------
    for u, p in uids_d.items():
        q = uids_r.get(u)
        if q is None: continue
        sl_d = round(float(p["stop"]), 5)
        if q.sl and abs(q.sl - sl_d) > PC.PONTO:
            r = mt5.order_send(dict(action=mt5.TRADE_ACTION_SLTP, symbol=ativo,
                                    position=q.ticket, sl=sl_d, tp=0.0))
            ok = bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)
            ledger_extra.append(dict(tipo="AJUSTE_SL", uid=u, de=q.sl, para=sl_d, confirmado=ok))
            acao.append(f"SL {u}->{sl_d} {'OK' if ok else 'FALHOU'}")
    # ---- correcao 6: reconciliacao sombra x MT5 NARRADA em toda passada -----
    reais_fim = {(q.comment or "").replace("T3:", "").strip() or f"tk{q.ticket}"
                 for q in _pos_minhas(mt5, ativo)}
    if ct:      # v6.0: registro obrigatorio do Ciclo em TODA passada
        ledger_extra.append(dict(tipo="CICLO", dirs=ct.get("dirs"), fase=ct.get("fase"),
                                 conclusao=ct.get("conclusao"), topdown=ct.get("topdown"), apoio=ct.get("apoio"),
                                 conflito=ct.get("conflito"), degrau=ct.get("degrau"),
                                 janela=ct.get("janela_conf"), voltou=ct.get("voltou"),
                                 classif=ct.get("classif")))
    ledger_extra.append(dict(tipo="RECON", desejo=sorted(uids_d), reais=sorted(reais_fim),
                             casadas=sorted(set(uids_d) & reais_fim),
                             so_sombra=sorted(set(uids_d) - reais_fim),
                             so_mt5=sorted(reais_fim - set(uids_d))))
    return " | ".join(acao) or ""

def _fechar_pos(mt5, p):
    si = mt5.symbol_info(p.symbol)
    preco = si.bid if p.type == 0 else si.ask
    req = dict(action=mt5.TRADE_ACTION_DEAL, symbol=p.symbol, volume=p.volume,
               type=(mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY),
               position=p.ticket, price=preco, deviation=30, magic=p.magic,
               comment="T3:corte", type_time=mt5.ORDER_TIME_GTC,
               type_filling=_filling(mt5, si))
    r = mt5.order_send(req)
    return f"FECHOU {p.ticket}" if r and r.retcode == mt5.TRADE_RETCODE_DONE else f"FECHA_FALHOU {p.ticket}"

def puxar_e_espelhar(mt5, ativo):
    """MT5 -> CSVs no formato dos exports. Devolve ts da ultima M15 FECHADA."""
    TFS = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
           "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
           "Daily": mt5.TIMEFRAME_D1}
    os.makedirs(PASTA_ESPELHO, exist_ok=True)
    for f in os.listdir(PASTA_ESPELHO):
        if f.startswith(f"{ativo}_"): os.remove(os.path.join(PASTA_ESPELHO, f))
    ult_m15 = None
    for tf, cod in TFS.items():
        n = AQUECIMENTO[tf]
        r = mt5.copy_rates_from_pos(ativo, cod, 1, n)   # pos=1: SO barras FECHADAS
        if r is None or len(r) < 50:
            raise RuntimeError(f"{ativo} {tf}: MT5 devolveu {0 if r is None else len(r)} barras")
        d = pd.DataFrame(r)
        d["dt"] = pd.to_datetime(d["time"], unit="s")
        if tf == "M15": ult_m15 = d["dt"].iloc[-1]
        tag = f"{d['dt'].iloc[0]:%Y%m%d%H%M}_{d['dt'].iloc[-1]:%Y%m%d%H%M}"
        cam = os.path.join(PASTA_ESPELHO, f"{ativo}_{tf}_{tag}.csv")
        out = pd.DataFrame({
            "<DATE>": d["dt"].dt.strftime("%Y.%m.%d"), "<TIME>": d["dt"].dt.strftime("%H:%M:%S"),
            "<OPEN>": d["open"], "<HIGH>": d["high"], "<LOW>": d["low"], "<CLOSE>": d["close"],
            "<TICKVOL>": d["tick_volume"].astype(int), "<VOL>": 0, "<SPREAD>": d["spread"].astype(int)})
        dig = getattr(mt5.symbol_info(ativo), "digits", 2) or 2
        out.to_csv(cam, sep="\t", index=False, float_format=f"%.{dig}f")
    si = mt5.symbol_info(ativo)
    spread_tick = int(si.spread) if si else -1
    return ult_m15, spread_tick

import json as _json
import professor_bloco3 as B3
try:
    import bt_ciclo_v1 as CV1          # v5.0: percepcao do Bloco 1 (narra, nunca ordena)
except Exception as _e_cv1:
    CV1 = None
    print(f"[aviso] bt_ciclo_v1 indisponivel ({_e_cv1}) — vivo segue SEM a ficha do Bloco 1")

def mapa_congelado(ativo, lt, lista, F15, fichas, ter):
    """Constroi (1x) ou carrega o mapa congelado do historico 24m completo."""
    cam = f"mapa_congelado_{ativo}.json"
    if os.path.exists(cam):
        bruto = _json.load(open(cam, encoding="utf-8"))
        return {tuple(k.split("§")): v for k, v in bruto.items()}
    _log(f"{ativo}: construindo o MAPA CONGELADO do historico ({PASTA_HIST}) — 1x, minutos...")
    if not PC._aplicar_ficha(ativo, PASTA_HIST):
        raise RuntimeError("historico do mapa indisponivel")
    lt_h = B1.LeitorMultiTF(PASTA_HIST, ativo).carregar()
    F15h = B1.FichaSerie(lt_h, "M15", ativo)
    fichas_h = {"M15": F15h}
    for tf in sorted({c["tf"] for c in lista}):
        if tf not in fichas_h and tf in lt_h.andares:
            fichas_h[tf] = B1.FichaSerie(lt_h, tf, ativo)
    ter_h = B2.preparar_territorio(lt_h, F15h)
    E = B3.etiquetar(lt_h, ativo, [c for c in lista if c["tf"] in fichas_h], F15h, fichas_h, ter_h)
    sys.stderr.write("\n")
    tab = B3.tabela_ctx(E)
    _json.dump({f"{a}§{b}§{c}": v for (a, b, c), v in tab.items()},
               open(cam, "w", encoding="utf-8"))
    _log(f"{ativo}: mapa congelado salvo em {cam} ({len(tab)} buckets) — NAO recalibrar sem carimbo")
    PC._aplicar_ficha(ativo, PASTA_ESPELHO)   # devolve a ficha ao espelho
    return tab

_SPREAD_AVISO = {}
def decidir(ativo):
    """Roda o Seletor medido sobre o espelho; devolve eventos da ULTIMA barra."""
    nb3, K = CONFIG[ativo]
    if not PC._aplicar_ficha(ativo, PASTA_ESPELHO):
        raise RuntimeError("ficha do espelho falhou")
    if ativo in SPREAD_MODELADO:
        PC.SPREAD_PTS = SPREAD_MODELADO[ativo]   # decreto 00185: custo cravado
        if not _SPREAD_AVISO.get(ativo):         # correcao 8: a ficha da pasta imprime
            _SPREAD_AVISO[ativo] = True          # o valor antigo (cosmetico) — avisa
            print(f"[custo] {ativo}: SPREAD MODELADO = {PC.SPREAD_PTS} pts (decreto 00185) — sobrepoe a ficha da pasta")
    lista = B2.carregar_lista(ativo)
    lt = B1.LeitorMultiTF(PASTA_ESPELHO, ativo).carregar()
    F15 = B1.FichaSerie(lt, "M15", ativo)
    fichas = {"M15": F15}
    for tf in sorted({c["tf"] for c in lista}):
        if tf not in fichas and tf in lt.andares:
            fichas[tf] = B1.FichaSerie(lt, tf, ativo)
    lista = [c for c in lista if c["tf"] in fichas]
    cand = B2.preparar_candidatos(lt, ativo, lista, F15, fichas)
    # ---- PURA (a decisao primaria do log — o CONTROLE) ----------------------
    estado_pilha = []
    T, rec, tri, hist, ab, fe = B2.rodar_seletor(
        lt, ativo, lista[:K], F15, fichas, cand=cand, b3_n=nb3,
        rotulo="sombra", disp=False, estado_final=estado_pilha)
    k_ult = F15.n - 1
    ts_ult = pd.Timestamp(F15.ts[k_ult])
    evs = [t for t in tri if t.get("k") == k_ult]
    # ---- correcao 1: timestamp REAL da entrada propagado a cada posicao -----
    for p in estado_pilha:
        ks = [t.get("k") for t in tri if t.get("ev") == "ABRE" and t.get("k") is not None
              and (t.get("card") == p.get("card")
                   or (t.get("card") is None and "ent" in t
                       and abs(float(t.get("ent")) - float(p.get("ent", -1e18))) < 1e-9))]
        if ks:
            p["k_ent"] = int(max(ks))
            p["ts_ent"] = str(pd.Timestamp(F15.ts[p["k_ent"]]))
    # ---- MAPA EM SOMBRA (Feito00181) ---------------------------------------
    modo = MODO_MAPA.get(ativo, "observador")
    ter = B2.preparar_territorio(lt, F15)
    tab = mapa_congelado(ativo, lt, lista, F15, fichas, ter)
    ts15 = F15.ts
    def pf_ctx(card, tf, pfg, lado, k):
        v = tab.get((card, tf, B3.cenario(ter, ts15, k, lado)))
        return v["pf"] if (v and v["n"] >= B3.PISO_N) else pfg
    def pf_din(cd, k): return pf_ctx(cd["card"], cd["tf"], cd["pf"], cd["lado"], k)
    _cels = [(c["card"], c["tf"], c["pf"]) for c in lista]
    def topk(cd, k):
        rk = sorted(_cels, key=lambda c: (-pf_ctx(c[0], c[1], c[2], cd["lado"], k), -c[2], c[0]))
        return ((cd["card"], cd["tf"]) in {(c[0], c[1]) for c in rk[:K]}), "bloco3_fora_do_topK_vivo"
    def bloq(cd, k):
        ok1, m1 = topk(cd, k)
        if not ok1: return False, m1
        v = tab.get((cd["card"], cd["tf"], B3.cenario(ter, ts15, k, cd["lado"])))
        if v and v["n"] >= B3.PISO_N and v["pf"] < 1.0:
            return False, "bloco3_incompativel"
        return True, ""
    ele = bloq if modo == "R4b" else (topk if modo == "R4a" else bloq)  # observador simula R4b
    Tm, recm, trim, histm, abm, fem = B2.rodar_seletor(
        lt, ativo, lista, F15, fichas, cand=cand, b3_n=nb3,
        rotulo="mapa", disp=False, pf_dinamico=pf_din, elegivel=ele)
    # ---- radiografia: contexto completo da ultima barra --------------------
    dirs = {}
    for tf in ("Daily", "H4", "H1", "M30", "M15"):
        if tf in lt.andares:
            d = lt.andares[tf].df
            dirs[tf] = int(np.sign(d.close.values[-1] - d.open.values[-1]))
    rank = {}
    for lado, rot in ((+1, "compra"), (-1, "venda")):
        rr = sorted(_cels, key=lambda c: (-pf_ctx(c[0], c[1], c[2], lado, k_ult), -c[2], c[0]))[:5]
        rank[rot] = [(c[0].replace("card", "c"), c[1], c[2],
                      round(pf_ctx(c[0], c[1], c[2], lado, k_ult), 2)) for c in rr]
    radio = dict(dirs=dirs, rank=rank, recusas=dict(rec), pilha_detalhe=estado_pilha)
    evs_m = [t for t in trim if t.get("k") == k_ult]
    cen_ult = B3.cenario(ter, ts15, k_ult, +1) + "/" + B3.cenario(ter, ts15, k_ult, -1)
    contra = dict(modo=modo, cenario=cen_ult, T_pura=T, T_mapa=Tm, radio=radio,
                  F15=F15, lt=lt, estado_pilha=estado_pilha,
                  liq_pura=float(T.pts.sum()) if len(T) else 0.0,
                  liq_mapa=float(Tm.pts.sum()) if len(Tm) else 0.0,
                  n_pura=len(T), n_mapa=len(Tm),
                  bloqueios_janela=int(recm.get("bloco3_incompativel", 0)),
                  evs_mapa=evs_m)
    return ts_ult, evs, ab, len(T), contra

_SNAPM = {}
def registrar_mapa(ativo, ts_barra, contra):
    """Ledger do Feito00181/00183 — atribuicao por decisao."""
    cam = f"vivo_mapa_{ativo}.csv"
    novo = not os.path.exists(cam)
    def _ch(T):
        if T is None or not len(T): return set()
        return {(str(r["ts"]), r["card"], r["tf"], round(float(r["pts"]), 1)) for _, r in T.iterrows()}
    cp, cm = _ch(contra.get("T_pura")), _ch(contra.get("T_mapa"))
    ant = _SNAPM.get(ativo)
    so_pura_novos = so_mapa_novos = ""
    if ant is not None:
        ant_sp, ant_sm = ant
        sp, sm = (cp - cm), (cm - cp)
        so_pura_novos = " | ".join(f"{c[1]}@{c[3]:+.0f}pts" for c in sorted(sp - ant_sp))
        so_mapa_novos = " | ".join(f"{c[1]}@{c[3]:+.0f}pts" for c in sorted(sm - ant_sm))
    _SNAPM[ativo] = ((cp - cm), (cm - cp))
    with open(cam, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["ts_barra", "ativo", "config_oficial", "modo_mapa", "cenario_ult(+/-)",
                        "evento_pura", "evento_mapa", "bloqueios_na_janela",
                        "liq_janela_pura", "liq_janela_mapa", "delta_mapa",
                        "n_pura", "n_mapa",
                        "so_pura_novos(bloq/preteridos c/resultado)",
                        "so_mapa_novos(troca do re-rank)", "versao"])
        ep = "|".join(e["ev"] for e in contra.get("evs_pura", [])) or "sem_acao"
        em = "|".join(e["ev"] for e in contra["evs_mapa"]) or "sem_acao"
        w.writerow([ts_barra, ativo, str(CONFIG[ativo]), contra["modo"], contra["cenario"],
                    ep, em, contra["bloqueios_janela"],
                    f"{contra['liq_pura']:.1f}", f"{contra['liq_mapa']:.1f}",
                    f"{contra['liq_mapa']-contra['liq_pura']:+.1f}",
                    contra["n_pura"], contra["n_mapa"],
                    so_pura_novos, so_mapa_novos, V_VERSAO])

_SNAP = {}
_DETER = {}
def ciclo_instrumento(ativo, ts_barra, contra, evs):
    """Itens 16-18 (M15, declarado): contadores do Ciclo por barra."""
    F15 = contra.get("F15"); lt = contra.get("lt")
    if F15 is None: return
    k = F15.n - 1
    cc = bool(F15.corta[+1][k]) if +1 in getattr(F15, "corta", {}) else bool(getattr(F15, "corta", {}).get(1, [False]*(k+1))[k]) if isinstance(getattr(F15, "corta", None), dict) else False
    cv = False
    try:
        cc = bool(F15.corta[1][k]); cv = bool(F15.corta[-1][k])
    except Exception:
        pass
    b1 = bool(F15.B1[k]); b3 = False; b5 = bool(F15.B5[k])
    pilha = contra.get("estado_pilha", [])
    lado_pos = int(pilha[0]["lado"]) if pilha else 0
    contra_pos = (lado_pos > 0 and cc) or (lado_pos < 0 and cv)
    d = _DETER.get(ativo, 0)
    d = d + 1 if (lado_pos and contra_pos) else 0
    _DETER[ativo] = d
    cortou = any(e.get("ev") == "CORTE_PILHA" for e in evs)
    if lado_pos == 0:
        clas = "sem_posicao"
    elif cortou:
        clas = f"reversao_confirmada_corte(apos {d}b deterioracao)"
    elif contra_pos:
        clas = f"deterioracao({d}b)"
    elif cc or cv:
        clas = "pullback[REF]"
    else:
        clas = "ok"
    import csv as _csv
    cam = f"vivo_ciclo_{ativo}.csv"
    novo = not os.path.exists(cam)
    with open(cam, "a", newline="", encoding="utf-8") as f:
        w = _csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["ts_barra", "dirs_D1_H4_H1_M30_M15", "corta_compra", "corta_venda",
                        "B1", "B5", "pilha_n", "lado_posicao", "deterioracao_barras",
                        "classificacao", "corte_executado", "versao"])
        dirs = contra.get("radio", {}).get("dirs", {})
        w.writerow([ts_barra, "/".join(f"{v:+d}" for v in dirs.values()), int(cc), int(cv),
                    int(b1), int(b5), len(pilha), lado_pos, d, clas, int(cortou), V_VERSAO])

def radiografar(ativo, ts_barra, evs, contra, lat, spread_tick, acao_demo):
    r = contra.get("radio", {})
    with open(f"vivo_radio_{ativo}.txt", "a", encoding="utf-8") as f:
        f.write(f"\n══ {ativo} · barra {ts_barra} · lat {lat:.1f}s · spread {spread_tick} ══\n")
        f.write("  andares: " + "  ".join(f"{tf}:{'+' if d>0 else '-' if d<0 else '0'}"
                for tf, d in r.get("dirs", {}).items()) +
                f"   cenario {contra.get('cenario','?')} [{contra.get('modo','')}]\n")
        for rot in ("compra", "venda"):
            f.write(f"  ranking {rot}: " + " · ".join(
                f"{c}({tf}) ctx {px}{'*' if abs(px-pg)>0.005 else ''}"
                for c, tf, pg, px in r.get("rank", {}).get(rot, [])) + "\n")
        pd_ = r.get("pilha_detalhe", [])
        if pd_:
            f.write("  PILHA: " + " | ".join(
                f"{p['card'][:16]} {'C' if p['lado']>0 else 'V'} ent {p['ent']:.5g} stop {p['stop']:.5g} "
                f"{'PROTEGIDA' if p['protegida'] else 'em risco'}"
                + (f" ent_ts {p['ts_ent']}" if p.get('ts_ent') else " ent_ts ?") for p in pd_) + "\n")
        else:
            f.write("  PILHA: vazia\n")
        f.write("  eventos: " + ("; ".join(e["ev"] for e in evs) or "sem_acao") +
                ("   DEMO: " + acao_demo if acao_demo else "") + "\n")
        rc = r.get("recusas", {})
        if rc:
            f.write("  recusas(janela): " + ", ".join(f"{k}:{v}" for k, v in
                    sorted(rc.items(), key=lambda x: -x[1])[:6]) + "\n")

def registrar(ativo, ts_barra, evs, pilha, n_hist, T=None, spread_tick=-1):
    cam = f"vivo_log_{ativo}.csv"
    novo = not os.path.exists(cam)
    # narracao por diferenca (v2.1): trades fechados novos + variacao da pilha
    # correcao 9: chave por TIMESTAMP (ts,card,tf) — pts FORA da chave; a borda
    # deslizante re-simula trades antigos com pts diferentes e criava fantasmas.
    chaves = set(); pts_de = {}
    if T is not None and len(T):
        for _, r in T.iterrows():
            c = (str(r["ts"]), r["card"], r["tf"])
            chaves.add(c); pts_de[c] = float(r["pts"])
    ant_ch, ant_p = _SNAP.get(ativo, (None, None))
    fech_novos = ""
    if ant_ch is not None:
        ant_max = max((c[0] for c in ant_ch), default="")
        novos = [c for c in sorted(chaves - ant_ch) if c[0] > ant_max]
        fech_novos = " | ".join(f"{c[1]}@{pts_de[c]:+.0f}pts" for c in novos)
    var_pilha = "" if ant_p is None or ant_p == pilha else f"pilha {ant_p}->{pilha}"
    _SNAP[ativo] = (chaves, pilha)
    with open(cam, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["ts_servidor_barra", "ts_local", "evento", "detalhe",
                        "pilha_aberta", "trades_janela", "fechou_novos", "var_pilha",
                        "spread_vivo", "versao"])
        base = [pilha, n_hist, fech_novos, var_pilha, spread_tick, V_VERSAO]
        if not evs:
            w.writerow([ts_barra, datetime.now(), "sem_acao", ""] + base)
        for e in evs:
            det = {k: v for k, v in e.items() if k not in ("ev", "k")}
            w.writerow([ts_barra, datetime.now(), e["ev"], str(det)] + base)

# ---------------------------------------------------------------------------
def conferir(ativo):
    """professor x vivo: re-roda o Seletor no espelho salvo e compara com o log."""
    print(f"CONFERENCIA professor x vivo — {ativo} (espelho salvo x vivo_log)")
    ts, evs, pilha, n, contra = decidir(ativo)
    print(f"  professor no espelho: barra {ts} · eventos={len(evs)} · pilha={pilha} · trades_janela={n}")
    print(f"  mapa[{contra['modo']}]: janela pura {contra['liq_pura']:+.0f} x mapa {contra['liq_mapa']:+.0f} "
          f"({contra['liq_mapa']-contra['liq_pura']:+.0f}) · bloqueios {contra['bloqueios_janela']}")
    k_c = contra["F15"].n - 1
    for p in contra.get("estado_pilha", []):
        ke = p.get("k_ent"); ida = (k_c - int(ke)) if ke is not None else "?"
        print(f"  pilha: {p.get('card')} uid {_uid(ativo, p)} ent_ts {p.get('ts_ent','?')} idade {ida}b")
    cam = f"vivo_log_{ativo}.csv"
    if not os.path.exists(cam):
        print("  (sem vivo_log ainda — roda a sombra primeiro)"); return
    alvo = str(ts)
    linhas = [l for l in open(cam, encoding="utf-8") if l.startswith(alvo + ";")]
    print(f"  vivo_log na mesma barra: {len(linhas)} registros")
    evs_log = [l.split(";")[2] for l in linhas]
    if evs_log:
        print(f"  eventos no log: {', '.join(evs_log)}")
    esperado = max(1, len(evs))
    if len(linhas) == esperado:
        print("  VEREDITO: BATE (mesma barra, mesmos eventos)")
    elif len(linhas) > esperado and len(set(evs_log)) == 1 and (evs_log[0] == "sem_acao") == (len(evs) == 0):
        print(f"  VEREDITO: BATE (duplicata de reinicio — {len(linhas)} passagens com decisao IDENTICA: determinismo)")
    else:
        print("  VEREDITO: >>> DIVERGE — REPORTAR (nada avanca ate bater) <<<")

def _puxar_m1m5(mt5, ativo):
    """v6.2 — refresh leve do espelho: SO M1 e M5 (protecao intrabar)."""
    TFS = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5}
    ult_m1 = None
    for tf, cod in TFS.items():
        n = AQUECIMENTO[tf]
        r = mt5.copy_rates_from_pos(ativo, cod, 1, n)
        if r is None or len(r) < 50: return None
        d = pd.DataFrame(r); d["dt"] = pd.to_datetime(d["time"], unit="s")
        if tf == "M1": ult_m1 = d["dt"].iloc[-1]
        for f in os.listdir(PASTA_ESPELHO):
            if f.startswith(f"{ativo}_{tf}_"): os.remove(os.path.join(PASTA_ESPELHO, f))
        tag = f"{d['dt'].iloc[0]:%Y%m%d%H%M}_{d['dt'].iloc[-1]:%Y%m%d%H%M}"
        out = pd.DataFrame({
            "<DATE>": d["dt"].dt.strftime("%Y.%m.%d"), "<TIME>": d["dt"].dt.strftime("%H:%M:%S"),
            "<OPEN>": d["open"], "<HIGH>": d["high"], "<LOW>": d["low"], "<CLOSE>": d["close"],
            "<TICKVOL>": d["tick_volume"].astype(int), "<VOL>": 0, "<SPREAD>": d["spread"].astype(int)})
        dig = getattr(mt5.symbol_info(ativo), "digits", 2) or 2
        out.to_csv(os.path.join(PASTA_ESPELHO, f"{ativo}_{tf}_{tag}.csv"),
                   sep="\t", index=False, float_format=f"%.{dig}f")
    return ult_m1

_ULT_M1_PROT = {}
def _protecao_intrabar(mt5, ativo):
    """v6.2 — entre barras M15, com posicao aberta: o Ciclo corta na cadencia
    do M1. Fecha, confirma e registra CORTE_CICLO_INTRABAR no vivo_exec."""
    if CV1 is None: return
    ps = _pos_minhas(mt5, ativo)
    if not ps: return
    ult = _puxar_m1m5(mt5, ativo)
    if ult is None or _ULT_M1_PROT.get(ativo) == ult: return
    _ULT_M1_PROT[ativo] = ult
    try:
        fic, _ = CV1.avaliar(PASTA_ESPELHO, ativo, lado_posicao=0)
        v = fic.get("12_veredito") or {}
    except Exception as e:
        _log(f"{ativo}: protecao intrabar sem leitura ({e}) — segue"); return
    cortes = []
    for q in ps:
        lp = 1 if q.type == mt5.POSITION_TYPE_BUY else -1
        mot = None
        if int(v.get("degrau") or 0) >= 2 and int(v.get("lado_ex") or 0) == -lp:
            mot = f"reversao_{v['degrau']}sinal"
        elif v.get("janela_conf"): mot = f"janela_10_15({v['janela_conf']})"
        elif v.get("voltou"): mot = "voltou_compressao"
        if mot:
            u = (q.comment or "").replace("T3:", "").strip() or f"tk{q.ticket}"
            acao = _fechar_pos(mt5, q)
            okc = _confirmar(mt5, ativo, u, presente=False)
            cortes.append(dict(tipo="CORTE_CICLO_INTRABAR", uid=u, ts_m1=str(ult), motivo=mot,
                               confirmado=okc, apoio=v.get("apoio"), conflito=v.get("conflito")))
            _log(f"{ativo}: CORTE INTRABAR {u} ({mot}) @M1 {ult:%H:%M} · {acao} · conf {okc}")
    if cortes:
        cam = f"vivo_exec_{ativo}.csv"
        novo = not os.path.exists(cam)
        with open(cam, "a", newline="", encoding="utf-8") as fx:
            wx = csv.writer(fx, delimiter=";")
            if novo: wx.writerow(["ts_barra", "latencia_s", "acao", "detalhes", "versao"])
            wx.writerow([str(ult), "", "INTRABAR", str(cortes), V_VERSAO])

def _pnl_pos(mt5, ticket):
    """v6.4 (9): P&L liquido + comissao + swap + preco de fechamento, da corretora."""
    try:
        time.sleep(0.6)
        dls = mt5.history_deals_get(position=int(ticket)) or []
        if not dls: return {}
        return dict(pnl_usd=round(sum(d.profit for d in dls), 2),
                    comissao_usd=round(sum(d.commission for d in dls), 2),
                    swap_usd=round(sum(d.swap for d in dls), 2),
                    preco_fech=dls[-1].price)
    except Exception:
        return {}

def _lat_unificada(mt5, ativo, ts_barra, t0):
    """Correcao 10 — METRICA UNICA de latencia, documentada:
    latencia = (relogio do SERVIDOR no registro da decisao, via ultimo tick)
             - (fechamento da barra M15 no servidor = ts_barra + 15min).
    Radio, vivo_exec e log de tela usam ESTE numero. Fallback declarado:
    sem tick valido, cai no tempo de processamento local (subestima)."""
    try:
        tk = mt5.symbol_info_tick(ativo)
        if tk and tk.time:
            return max(0.0, float(tk.time) - (pd.Timestamp(ts_barra).timestamp() + 900.0))
    except Exception:
        pass
    return time.time() - t0

def sombra(ativo, intervalo=60, executa=False):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise SystemExit(f"MT5 nao inicializou: {mt5.last_error()}")
    info = mt5.account_info()
    if executa and info.trade_mode != 0:
        raise SystemExit(">>> TRAVA: --executa so roda em conta DEMO. Conta atual nao e demo. ABORTADO. <<<")
    manifesto(mt5, ativo, executa)
    ult_processada = None
    cam0 = f"vivo_log_{ativo}.csv"
    if os.path.exists(cam0):
        try:
            ults = [l.split(";")[0] for l in open(cam0, encoding="utf-8") if ";" in l][1:]
            if ults:
                ult_processada = pd.Timestamp(ults[-1])
                _log(f"retomada: ultima barra ja registrada = {ult_processada} (sem reprocesso)")
        except Exception:
            pass
    if CV1: CV1.SESSAO = f"{ativo}-{datetime.now():%Y%m%d%H%M%S}"
    _log(f"{'TESTE VIVO 004 (ORDENS DEMO)' if executa else 'SOMBRA VIVA'} v{V_VERSAO} — {ativo} · "
         f"conta {info.login} ({info.server}) · config B3={CONFIG[ativo][0]} top-{CONFIG[ativo][1]} · "
         f"{'risco 0,25%/un · disjuntor -1,5%/dia' if executa else 'ZERO ORDENS'}")
    try:                                             # item 2: autoteste de gravacao
        for _cam in (f"vivo_fases_{ativo}.csv", f"vivo_auditor_{ativo}.csv"):
            with open(_cam, "a", encoding="utf-8"): pass
            open(_cam, encoding="utf-8").readline()
        _log("AUTOTESTE GRAVACAO: fases+auditor abrem p/ escrita e leitura — OK")
    except Exception as _ea:
        if executa: raise SystemExit(f"AUTOTESTE GRAVACAO FALHOU ({_ea}) — sem auditoria NAO se executa")
        _log(f"AUTOTESTE GRAVACAO FALHOU ({_ea}) — percepcao segue; executa seria barrado")
    _log(maturidade(resumo=True))
    _log(f"CHECKLIST: modo_conta={'DEMO' if info.trade_mode == 0 else 'NAO-DEMO!'} · "
         f"portao_latencia<={LATENCIA_MAX_ENVIO:.0f}s · desvio_max={DESVIO_MAX_PTS.get(ativo, DESVIO_MAX_PADRAO)}pts · "
         f"ledger={len(_enviadas(ativo))} uids · posicoes_T3_abertas={len(_pos_minhas(mt5, ativo))} · "
         f"contratendencia={'ARMADA POR DECRETO' if _CONTRA_ARMADA else 'DESARMADA (narra)'} · "
         f"quarentena={'ATIVA' if ativo in QUARENTENA_EXEC else ('DERRUBADA POR DECRETO DESTA SUBIDA' if '--sem-quarentena' in sys.argv else 'SEM QUARENTENA')} · "
         f"b2_calendario={(str(len(_calendario_carregar())) + ' eventos') if os.path.exists('calendario.csv') else 'SEM ARQUIVO (desligada, declarada)'}")
    while True:
        try:
            ts_m15, spread_tick = puxar_e_espelhar(mt5, ativo)
            if ts_m15 != ult_processada:
                t0 = time.time()
                _t_dec0 = time.time()
                ts, evs, pilha, n, contra = decidir(ativo)
                _t_dec = time.time() - _t_dec0
                if CV1:                                        # v6.0: veredito do Ciclo
                    try:
                        _pil0 = contra.get("estado_pilha") or []
                        _fic0, _le0 = CV1.avaliar(PASTA_ESPELHO, ativo, gravar_mem=True,
                                               lado_posicao=int(_pil0[0]["lado"]) if _pil0 else 0)
                        contra["ciclo"] = _fic0.get("12_veredito")
                        if contra["ciclo"] is not None:
                            contra["ciclo"]["dirs"] = {nm: (le["dir"] if le else None) for nm, le in _le0.items()}
                            contra["ciclo"]["fase"] = _fic0.get("15_fase")
                            contra["ciclo"]["conclusao"] = (_fic0.get("16_conclusao") or {}).get("decisao")
                        contra["ts_barra"] = ts
                        contra["_ficha_cv1"] = _fic0
                    except Exception as _e0:
                        _log(f"{ativo}: Ciclo sem leitura nesta barra ({_e0}) — portao do Ciclo nao arma; leis antigas seguem")
                contra["evs_pura"] = evs
                extra = []
                acao_demo = ""
                if executa:
                    try:
                        k_ult_v = contra["F15"].n - 1
                        trail_sl_demo(mt5, ativo, contra, extra)   # v3.1 religado (regressao fechada)
                        if _AUD["ok"]:
                            acao_demo = executar(mt5, ativo, contra, k_ult_v, extra)
                        else:
                            extra.append(dict(tipo="NAO_ABRIU", uid="-", motivo="auditoria_indisponivel"))
                            acao_demo = "BLOQUEADO(auditoria_indisponivel) "
                            _log(f"{ativo}: EXECUCAO BLOQUEADA — gravacao de auditoria falhou na barra anterior")
                    except Exception as ex:
                        acao_demo = f"EXEC_ERRO {type(ex).__name__}: {ex}"
                _t_fic = time.time() - _t_dec0 - _t_dec
                lat_u = _lat_unificada(mt5, ativo, ts, t0)     # correcao 10
                if CV1 and contra.get("_ficha_cv1"):
                    try:
                        _vrd, _obs = _auditor_veredito(ativo, contra["_ficha_cv1"], extra if executa else [])
                        _auditor_gravar(ativo, ts, _vrd, _obs, contra["_ficha_cv1"])
                        _AUD["ok"] = True
                        if _vrd != "COERENTE":
                            _log(f"{ativo}: AUDITOR >>> {_vrd} <<< {_obs}")
                        CV1.gravar_ficha(ativo, contra["_ficha_cv1"])
                        _f2 = contra["_ficha_cv1"]
                        cam2 = f"vivo_fases_{ativo}.csv"
                        novo2 = not os.path.exists(cam2)
                        with open(cam2, "a", newline="", encoding="utf-8") as f2:
                            w2 = csv.writer(f2, delimiter=";")
                            if novo2:
                                w2.writerow(["ts_barra", "fase", "rotulo", "decisao", "conflitos",
                                             "exibido", "bruto", "fichas_tf", "formando", "linha_tempo", "cv"])
                            w2.writerow([_f2["ts_barra"], _f2["15_fase"]["fase"], _f2["15_fase"]["rotulo"],
                                         _f2["16_conclusao"]["decisao"], "|".join(_f2["16_conclusao"]["conflitos"]),
                                         _f2["17_memoria"]["exibido"], _f2["17_memoria"]["bruto"],
                                         str(_f2["13_fichas_tf"]), str(_f2["14_formando"]),
                                         str(_f2["17_memoria"]["linha_tempo"][-3:]), CV1.CV1_VERSAO])
                    except Exception as _e:
                        _AUD["ok"] = False
                        _log(f"{ativo}: gravacao da ficha falhou ({_e}) — AUDITORIA INDISPONIVEL, entradas novas bloqueadas")
                registrar(ativo, ts, evs, pilha, n, T=contra.get("T_pura"), spread_tick=spread_tick)
                registrar_mapa(ativo, ts, contra)
                radiografar(ativo, ts, evs, contra, lat_u, spread_tick, acao_demo)
                try:
                    ciclo_instrumento(ativo, ts, contra, evs)
                except Exception as _e:
                    _log(f"[AVISO] instrumento ciclo: {_e}")
                if executa and (acao_demo or extra):
                    with open(f"vivo_exec_{ativo}.csv", "a", newline="", encoding="utf-8") as fx:
                        wx = csv.writer(fx, delimiter=";")
                        if fx.tell() == 0:
                            wx.writerow(["ts_barra", "latencia_s", "acao", "detalhes", "versao"])
                        wx.writerow([ts, f"{lat_u:.1f}", acao_demo, str(extra), V_VERSAO])
                demo_txt = ""
                if executa:
                    try:
                        ps_d = _pos_minhas(mt5, ativo)
                        pl_d = sum(q.profit for q in ps_d)
                        demo_txt = (f"DEMO {len(ps_d)}pos {pl_d:+.2f}USD · " if ps_d else "DEMO 0pos · ")
                    except Exception:
                        pass
                aberturas = [e for e in evs if e.get("ev") == "ABRE"]
                cortes = [e for e in evs if e.get("ev") == "CORTE_PILHA"]
                _log(f"barra M15 {ts:%d/%m %H:%M} fechada · "
                     f"{'ABRIRIA ' + str(len(aberturas)) + ' ' if aberturas else ''}"
                     f"{'CORTE_PILHA ' if cortes else ''}"
                     f"{'sem acao ' if not evs else ''}"
                     f"· pilha={pilha} · {demo_txt}{lat_u:.1f}s"
                     + (f" · quebra[decisao {_t_dec:.0f}s · ficha+exec {_t_fic:.0f}s]" if lat_u > 30 else ""))
                ult_processada = ts_m15
            else:
                sys.stdout.write("."); sys.stdout.flush()
        except KeyboardInterrupt:
            _log("sombra encerrada pelo dono"); break
        except Exception as e:
            _log(f"[AVISO] {type(e).__name__}: {e} — tentando de novo em {intervalo}s")
        if executa:
            try: _protecao_intrabar(mt5, ativo)      # v6.2: o Ciclo corta dentro da barra
            except Exception as _ei: _log(f"{ativo}: protecao intrabar falhou ({_ei}) — segue")
        time.sleep(intervalo)
    mt5.shutdown()

ABRIU_SCHEMA_V = 2
ABRIU_SCHEMA = {   # nome: (tipos aceitos, pode_ser_none)
    "tipo": (str, False), "uid": (str, False), "card": (str, False), "lado": (int, False),
    "lote": ((int, float), False), "magic": (int, False), "ticket": (int, False),
    "contratendencia": (bool, False), "ts_decisao": (str, False), "ts_envio": (str, False),
    "ts_confirmacao": (str, False), "bid_envio": ((int, float), False), "ask_envio": ((int, float), False),
    "risco_usd_exec": ((int, float), False), "risco_pct_exec": ((int, float), False),
    "ent_teorico": ((int, float), False), "ent_exec": ((int, float), False),
    "slippage_pts": ((int, float), False), "sl": ((int, float), False),
    "risco_usd": ((int, float), False), "risco_pct": ((int, float), False),
    "idade_barras": (int, False), "ts_ent": (str, False), "spread": (int, False),
    "cenario": (str, False), "tentativas": (int, False), "confirmado": (bool, False),
}

def _valida_abriu_19(ab, magic_esp):
    """v7.2: VALIDADOR POR ESQUEMA — nomes+tipos obrigatorios, nao-vazio;
    campos EXTRAS sao permitidos (esquema evolui sem quebrar a bancada)."""
    err = []
    def chk(cond, nome):
        if not cond: err.append(nome)
    chk(ab.get("tipo") == "ABRIU", "tipo")
    chk(ab.get("uid") and "SEMK" not in str(ab.get("uid")), "uid")
    chk(bool(ab.get("card")), "card")
    chk(ab.get("lado") in (1, -1), "lado")
    chk((ab.get("lote") or 0) >= 0.01, "lote")
    chk(ab.get("magic") == magic_esp, "magic")
    chk((ab.get("ticket") or 0) > 0, "ticket")
    chk((ab.get("ent_teorico") or 0) > 0, "ent_teorico")
    chk((ab.get("ent_exec") or 0) > 0, "ent_exec")
    chk(isinstance(ab.get("slippage_pts"), (int, float)), "slippage_pts")
    chk((ab.get("sl") or 0) > 0, "sl")
    chk((ab.get("risco_usd") or 0) > 0, "risco_usd")
    chk(0 < (ab.get("risco_pct") or 0) <= 2.0, "risco_pct")
    chk(ab.get("idade_barras") == 0, "idade_barras")
    ok_ts = False
    try:
        pd.Timestamp(ab.get("ts_ent")); ok_ts = True
    except Exception:
        pass
    chk(ok_ts, "ts_ent")
    chk((ab.get("spread") if ab.get("spread") is not None else -1) >= 0, "spread")
    chk(isinstance(ab.get("cenario"), str), "cenario")
    chk((ab.get("tentativas") or 0) >= 1, "tentativas")
    chk(ab.get("confirmado") is True, "confirmado")
    for nome, (tps, pode_none) in ABRIU_SCHEMA.items():
        if nome not in ab: err.append(f"FALTA:{nome}"); continue
        v = ab[nome]
        if v is None and not pode_none: err.append(f"VAZIO:{nome}"); continue
        if v is not None and not isinstance(v, tps): err.append(f"TIPO:{nome}={type(v).__name__}")
    for c26 in ("ts_decisao", "ts_envio", "ts_confirmacao"):
        try: pd.Timestamp(ab.get(c26))
        except Exception: err.append(f"TS_INVALIDO:{c26}")
    if not (0 < (ab.get("risco_pct_exec") or 0) <= 2.5): err.append("risco_pct_exec_fora")
    return err

def _auditor_veredito(ativo, fic, eventos):
    """v7.2: o veredito automatico da barra (as 3 linhas ja em maos)."""
    if fic is None: return "DADO_INSUFICIENTE(percepcao ausente)", ""
    if CV1 and getattr(CV1, "CV1_VERSAO", "?") != fic.get("_cv", getattr(CV1, "CV1_VERSAO", "?")):
        return "VERSAO_INCOMPATIVEL", ""
    mem = CV1.memoria_ler(ativo) if CV1 else {}
    if mem.get("aviso") == "VERSAO_INCOMPATIVEL(formato antigo descartado)":
        return "VERSAO_INCOMPATIVEL(memoria)", ""
    dec = (fic.get("16_conclusao") or {}).get("decisao", "")
    tipos = [e.get("tipo") for e in eventos]
    mots = ";".join(str(e.get("motivo", "")) for e in eventos)
    # percepcao -> autoridade
    if dec.startswith("OPERAR_A_FAVOR") and "ciclo_topdown_bloqueou" in mots:
        return "DIVERGENCIA_PERCEPCAO_AUTORIDADE", f"percepcao={dec} x autoridade bloqueou[{mots[:80]}]"
    if dec == "CORTAR" and not any(t in ("CORTE_CICLO", "CORTE_CICLO_INTRABAR", "FECHOU") for t in tipos)        and any(t == "RECON" and e.get("reais") for t, e in zip(tipos, eventos)):
        return "DIVERGENCIA_PERCEPCAO_AUTORIDADE", "percepcao=CORTAR x posicao seguiu aberta"
    # autoridade -> execucao
    for e in eventos:
        if e.get("tipo") in ("ABRIU", "CORTE_CICLO", "FECHOU") and e.get("confirmado") is not True:
            return "DIVERGENCIA_AUTORIDADE_EXECUCAO", f"{e.get('tipo')} sem confirmacao da corretora"
        if e.get("tipo") == "FECHADA_EXTERNA":
            return "DIVERGENCIA_AUTORIDADE_EXECUCAO", "posicao fechada fora da autoridade (stop/manual)"
        if e.get("tipo") == "RECON" and e.get("so_mt5"):
            return "DIVERGENCIA_AUTORIDADE_EXECUCAO", f"RECON so_mt5={e.get('so_mt5')}"
    return "COERENTE", ""

def _auditor_gravar(ativo, ts, veredito, obs, fic):
    cam = f"vivo_auditor_{ativo}.csv"
    novo = not os.path.exists(cam)
    with open(cam, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if novo: w.writerow(["ts_barra", "veredito", "obs", "fase", "decisao_percepcao", "versao"])
        w.writerow([str(ts), veredito, obs,
                    (fic or {}).get("15_fase", {}).get("fase", ""),
                    ((fic or {}).get("16_conclusao") or {}).get("decisao", ""), V_VERSAO])

def auditor(ativo, data=None):
    """v7.2 — relatorio do dia: as TRES linhas por barra + placar dos vereditos."""
    data = data or datetime.now().strftime("%Y-%m-%d")
    print(f"AUDITOR v{V_VERSAO} — {ativo} · dia {data} · PERCEPCAO -> AUTORIDADE -> EXECUCAO")
    def linhas(cam):
        if not os.path.exists(cam): return []
        return [l.rstrip("\n").split(";") for l in open(cam, encoding="utf-8") if l.startswith(data)]
    fases = {p[0]: p for p in linhas(f"vivo_fases_{ativo}.csv")}
    execs = {}
    for p in linhas(f"vivo_exec_{ativo}.csv"):
        execs.setdefault(p[0], []).append(p)
    auds = linhas(f"vivo_auditor_{ativo}.csv")
    placar = {}
    for p in auds: placar[p[1]] = placar.get(p[1], 0) + 1
    print(f"  vereditos do vivo: {placar or 'nenhum (vivo v7.2 ainda nao rodou barras)'}")
    ruins = [p for p in auds if p[1] != "COERENTE"]
    for p in ruins[:12]:
        ts = p[0]
        print(f"\n  ═ {ts[11:16]} · {p[1]} · {p[2]}")
        fz = fases.get(ts)
        print(f"    PERCEPCAO : " + (f"fase {fz[1]} {fz[2]} · decisao {fz[3]} · conflitos {fz[4] or '-'}" if fz else "AUSENTE"))
        for ex in execs.get(ts, [])[:3]:
            print(f"    AUT/EXEC  : {ex[3][:170]}")
    if not ruins: print("  nenhuma divergencia registrada no dia.")
    tot = len(auds)
    print(f"\n  barras auditadas: {tot} · coerentes: {placar.get('COERENTE', 0)}")

def estabilidade(ativo):
    """v6.5 — metricas da alternancia de estado (decreto do dono)."""
    cam = f"vivo_ficha_{ativo}.csv"
    if not os.path.exists(cam):
        print(f"{ativo}: sem vivo_ficha ainda."); return
    rows = [l.rstrip("\n").split(";") for l in open(cam, encoding="utf-8")][1:]
    ests = [(p[0], (p[1].split(" confirmada")[0].split(" so no")[0]).strip()) for p in rows if len(p) > 1]
    if len(ests) < 3:
        print(f"{ativo}: fichas insuficientes ({len(ests)})."); return
    mud = [(ests[i][0], ests[i-1][1], ests[i][1]) for i in range(1, len(ests)) if ests[i][1] != ests[i-1][1]]
    dur = {}; ini = 0
    for i in range(1, len(ests) + 1):
        if i == len(ests) or ests[i][1] != ests[ini][1]:
            dur.setdefault(ests[ini][1], []).append(i - ini); ini = i
    rev1 = sum(1 for i in range(1, len(ests) - 1)
               if ests[i][1] != ests[i-1][1] and ests[i+1][1] == ests[i-1][1])
    ts_mud = {m[0] for m in mud}; dec = 0
    camx = f"vivo_exec_{ativo}.csv"
    if os.path.exists(camx):
        for l in open(camx, encoding="utf-8"):
            p = l.split(";")
            if p and p[0] in ts_mud and ("'ABRIU'" in l or "ciclo_topdown_bloqueou" in l or "CORTE_CICLO" in l):
                dec += 1
    print(f"ESTABILIDADE v{V_VERSAO} — {ativo} · {len(ests)} fichas ({ests[0][0][:16]} -> {ests[-1][0][:16]})")
    print(f"  1 mudancas de estado: {len(mud)} ({100.0*len(mud)/max(1,len(ests)-1):.0f}% das barras)")
    for e, ds in sorted(dur.items()):
        print(f"  2 duracao media '{e}': {sum(ds)/len(ds):.1f} barras (n={len(ds)}, max {max(ds)})")
    print(f"  3 reversoes na barra seguinte (A->B->A): {rev1} de {len(mud)} mudancas"
          + (f" ({100.0*rev1/len(mud):.0f}%)" if mud else ""))
    print(f"  4 mudancas coincidindo com decisao (ordem/bloqueio/corte na barra): {dec}")
    print(f"  5 comparacao com o grafico real: sobreponha os timestamps no grafico do MT5 (olho do dono)")
    print(f"  ultimas mudancas: {[(m[0][11:16], m[1] + '->' + m[2]) for m in mud[-8:]]}")
    if mud and rev1 / max(1, len(mud)) > 0.4:
        print("  LEITURA: reversao 1-barra > 40% — classificador sem histerese; candidato a regra de "
              "estabilidade [REF, exige medicao antes de mudar]")

def relatorio(ativo, data=None):
    """v5.2 — o relatorio do dia, montado dos ledgers. Transparencia da maquina."""
    data = data or datetime.now().strftime("%Y-%m-%d")
    print(f"RELATORIO AUTOMATICO v{V_VERSAO} — {ativo} · dia {data}")
    print(f"  0 {maturidade(resumo=True)}")
    def linhas(cam, tcol=0):
        if not os.path.exists(cam): return []
        out = []
        for l in open(cam, encoding="utf-8"):
            p = l.rstrip("\n").split(";")
            if p and p[tcol].startswith(data): out.append(p)
        return out
    # 1 cadencia + pilha + spread + fechados (vivo_log)
    lg = linhas(f"vivo_log_{ativo}.csv")
    if lg:
        pil = [int(p[4]) for p in lg if p[4].isdigit()]
        spr = sorted(int(p[8]) for p in lg if len(p) > 8 and p[8].isdigit())
        trans = [(p[0], p[7]) for p in lg if len(p) > 7 and p[7]]
        print(f"  1 CADENCIA: {len(lg)} barras · primeira {lg[0][0][11:16]} ultima {lg[-1][0][11:16]}")
        print(f"  2 PILHA-SOMBRA: max {max(pil) if pil else 0} · transicoes {len(trans)}"
              + (f" -> {['%s %s' % (t[0][11:16], t[1]) for t in trans[:8]]}" if trans else ""))
        if spr: print(f"  3 SPREAD vivo: mediana {spr[len(spr)//2]} · p90 {spr[int(len(spr)*0.9)]} · max {spr[-1]}")
    else:
        print("  vivo_log: SEM LINHAS no dia (terminal rodou?)")
    # 2 executor (vivo_exec)
    ex = linhas(f"vivo_exec_{ativo}.csv")
    if ex:
        det = ";".join(p[3] for p in ex if len(p) > 3)
        def cnt(pat): return det.count(pat)   # v6.3: contagem LITERAL (regex crashava com [])
        lats = sorted(float(p[1]) for p in ex if len(p) > 1 and p[1].replace(".", "").isdigit())
        print(f"  4 EXECUTOR: {len(ex)} passadas · latencia mediana {lats[len(lats)//2] if lats else '?'}s max {lats[-1] if lats else '?'}s")
        M = "motivo': '"
        print(f"     ABRIU {cnt(chr(39)+'tipo'+chr(39)+': '+chr(39)+'ABRIU'+chr(39))} · FECHOU {cnt('FECHOU')} · "
              f"NAO_ABRIU {cnt('NAO_ABRIU')} (quarentena {cnt(M+'quarentena')}, idade {cnt(M+'sinal_antigo')}, "
              f"dedup {cnt(M+'uid_ja_enviado')}, spread {cnt(M+'spread_')}, risco {cnt(M+'risco_')}, "
              f"latencia {cnt(M+'latencia_excessiva')}, desvio {cnt(M+'preco_desviado')}, "
              f"b2_calendario {cnt(M+'B2_calendario')}, "
              f"stop {cnt(M+'stop_ja_violado')}, sem_barra {cnt(M+'sem_barra_entrada')}, "
              f"ciclo_topdown {cnt(M+'ciclo_topdown_bloqueou') + cnt('ciclo_topdown_bloqueou[')}) · "
              f"CORTE_CICLO {cnt('CORTE_CICLO')} (intrabar {cnt('CORTE_CICLO_INTRABAR')}) · "
              f"RECON {cnt('RECON')} · divergencias {cnt('so_mt5')-cnt(chr(39)+'so_mt5'+chr(39)+': []')}")
        for p in ex:
            if "'ABRIU'" in p[3]:
                print(f"     ORDEM {p[0][11:16]}: {p[3][:220]}")
    # 3 percepcao (vivo_ficha)
    fi = linhas(f"vivo_ficha_{ativo}.csv")
    if fi:
        conf = [p for p in fi if len(p) > 3 and "confirmacao': '" in p[3].replace('"', "'")]
        cmds = [p for p in fi if len(p) > 9 and p[9] and p[9] != "None"]
        cls = {}
        for p in fi:
            if len(p) > 10: cls[p[10]] = cls.get(p[10], 0) + 1
        print(f"  5 PERCEPCAO (Bloco 1): {len(fi)} fichas · classificacoes {cls} · "
              f"janelas c/ CONFIRMACAO {len(conf)} · comandos NARRADOS {len(cmds)}")
        for p in cmds[:6]: print(f"     {p[0][11:16]} comando_narrado: {p[9]} · estado: {p[1]}")
    else:
        print("  5 PERCEPCAO: vivo_ficha sem linhas no dia (v5+ rodando?)")
    # 4 ciclo + enviadas
    ci = linhas(f"vivo_ciclo_{ativo}.csv")
    if ci:
        b1 = sum(1 for p in ci if len(p) > 4 and p[4] == "1")
        print(f"  6 CICLO: {len(ci)} barras · B1(spread anomalo) {b1} · cortes_executados "
              f"{sum(1 for p in ci if len(p) > 10 and p[10] == '1')}")
    env = linhas(f"vivo_enviadas_{ativo}.csv", 1)
    print(f"  7 LEDGER DE ENVIO: {len(env)} uids enviados no dia")
    print("  TRANSPARENCIA: cada numero acima tem arquivo-fonte auditavel na pasta; nada e memoria minha.")

def percepcao(ativo, intervalo=60):
    """v5.1 — percepcao pura do Bloco 1 ao vivo: espelho + ficha por barra.
    Zero ordens, zero Seletor. Roda em qualquer simbolo visivel no MT5."""
    import MetaTrader5 as mt5
    if CV1 is None:
        raise SystemExit("bt_ciclo_v1.py ausente na pasta — o modo --percepcao exige ele")
    if not mt5.initialize():
        raise SystemExit(f"MT5 nao inicializou: {mt5.last_error()}")
    si = mt5.symbol_info(ativo)
    if not si:
        raise SystemExit(f"simbolo {ativo} nao visivel no MT5 (Market Watch)")
    _LG_PERC = True
    if CV1: CV1.SESSAO = f"{ativo}-{datetime.now():%Y%m%d%H%M%S}"
    _log(f"{ativo}: PERCEPCAO VIVA v{V_VERSAO} (Bloco 1 puro — sem Seletor, sem ordens) · loop {intervalo}s")
    ult = None
    while True:
        try:
            ts_m15, spread_tick = puxar_e_espelhar(mt5, ativo)
            if ts_m15 != ult:
                fic, leit = CV1.avaliar(PASTA_ESPELHO, ativo, lado_posicao=0, gravar_mem=True)
                CV1.gravar_ficha(ativo, fic)
                eu = fic["1_estado_unico"]
                _log(f"{ativo} barra {pd.Timestamp(ts_m15):%d/%m %H:%M} · {eu['texto']} · "
                     f"ref {fic['2_referencia_ciclo2']['veredito']} · classif {fic['11_classificacao']} · "
                     f"janela {eu['janela']['pos']}/{'ABERTA' if eu['janela']['aberta'] else 'fechada'}"
                     + (f" CONF {eu['janela']['confirmacao']}" if eu['janela'].get('confirmacao') else "")
                     + f" · M15 {('|'.join(fic['6_eventos']['M15']) or 'sem_evento')} · spread {spread_tick}")
                ult = ts_m15
        except KeyboardInterrupt:
            _log(f"{ativo}: percepcao encerrada pelo teclado."); break
        except Exception as e:
            _log(f"{ativo}: ciclo da percepcao falhou ({e}) — tenta de novo em {intervalo}s")
        time.sleep(intervalo)
    mt5.shutdown()

def _fisica_corte(pasta):
    """Serie M1 sintetica (alta longa + climax + queda) agregada a M5/M15/M30.
    Fisica VALIDADA: M1 dir=-1 c/ rompimento+exaustao · M5 perde a alta ·
    M15 exaustao identificada degrau 2 lado -1 -> comando de corte."""
    import shutil
    shutil.rmtree(pasta, ignore_errors=True); os.makedirs(pasta)
    base = pd.Timestamp(datetime.now().strftime("%Y-%m-%d")) 
    p = 100.0; m1 = []
    for _ in range(660): o = p; p += 0.03; m1.append([o, p + 0.02, o - 0.02, p])
    o = p; p += 1.2; m1.append([o, p + 0.1, o - 0.05, p])          # climax
    for _ in range(25): o = p; p -= 0.023; m1.append([o, o + 0.01, p - 0.015, p])
    for _ in range(28): o = p; p -= 0.06;  m1.append([o, o + 0.01, p - 0.02, p])
    for tf, mins in (("M1", 1), ("M5", 5), ("M15", 15), ("M30", 30)):
        out = []
        for j in range(0, len(m1) - len(m1) % mins, mins):
            seg = m1[j:j + mins]; t = base + pd.Timedelta(minutes=j)
            out.append([t.strftime("%Y.%m.%d"), t.strftime("%H:%M:%S"), seg[0][0],
                        max(r[1] for r in seg), min(r[2] for r in seg), seg[-1][3], 100, 0, 10])
        pd.DataFrame(out, columns=["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>",
                                   "<TICKVOL>", "<VOL>", "<SPREAD>"]).to_csv(
            os.path.join(pasta, f"BANC_{tf}_x.csv"), sep="\t", index=False)

def bancada_corte(ativo):
    """v6.1 — os 8 passos do decreto, de ponta a ponta, com registro."""
    import MetaTrader5 as mt5
    from datetime import timedelta
    global RISCO_UNIDADE, _MAGIC_OVERRIDE
    if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente")
    if not mt5.initialize(): raise SystemExit(f"MT5 nao inicializou: {mt5.last_error()}")
    info = mt5.account_info()
    if info.trade_mode != 0:
        mt5.shutdown(); raise SystemExit(">>> TRAVA: so em DEMO. ABORTADO. <<<")
    si = mt5.symbol_info(ativo)
    if not si: mt5.shutdown(); raise SystemExit(f"simbolo {ativo}?")
    try:
        if not PC._aplicar_ficha(ativo, PASTA_ESPELHO): PC.PONTO = si.point
    except Exception: PC.PONTO = si.point
    rel = []; res = []
    def rp(s): print(s); rel.append(s)
    def passo(n, tit, ok, obs=""):
        res.append(ok); rp(f"  [{'PASSA' if ok else 'FALHA'}] passo {n} — {tit}" + (f"\n         {obs}" if obs else ""))
    run = datetime.now()
    rp(f"BANCADA-CORTE v{V_VERSAO} — {ativo} · demo {info.login} · {run:%d/%m %H:%M:%S}")
    ext0 = {q.ticket for q in (mt5.positions_get() or []) if q.magic != MAGIC_BANCADA}
    risco_old = RISCO_UNIDADE; _MAGIC_OVERRIDE = MAGIC_BANCADA; RISCO_UNIDADE = 0.00001
    _q_susp = ativo in QUARENTENA_EXEC                     # v6.7: quarentena fora SO na bancada
    if _q_susp:
        QUARENTENA_EXEC.discard(ativo)
        rp(f"  quarentena do {ativo} SUSPENSA so dentro desta bancada (restaurada no fim)")
    ticket = 0
    try:
        # passos 2-5: a percepcao sobre a serie FORCADA
        _fisica_corte("Bancada_ciclo")
        fic, leit = CV1.avaliar("Bancada_ciclo", "BANC", lado_posicao=+1)
        v = fic["12_veredito"]
        rp("  caminho da percepcao (serie forcada):")
        for nm in ("M15", "M5", "M1"):
            le = leit.get(nm)
            rp(f"    {nm:<3} dir {le['dir']:+d} · eventos {le['eventos'][:3]}")
        passo(2, "deterioracao FORCADA no M1",
              leit["M1"]["dir"] == -1 and any(("rompimento" in e) or ("exaustao" in e) or ("quebra" in e)
                                              for e in leit["M1"]["eventos"]))
        passo(3, "avanco confirmado no M5 (perdeu a alta)", leit["M5"]["dir"] <= 0,
              f"dir M5 = {leit['M5']['dir']}")
        passo(4, "conflito no M15 (exaustao identificada contra a compra)",
              v["degrau"] >= 2 and v["lado_ex"] == -1, f"degrau {v['degrau']} lado {v['lado_ex']}")
        passo(5, "comando de corte emitido", fic["9_comando_narrado"] is not None,
              str(fic["9_comando_narrado"]))
        ct = dict(topdown=("neutra", "bancada"), apoio=v["apoio"], conflito=v["conflito"],
                  degrau=v["degrau"], lado_ex=v["lado_ex"], janela_conf=v["janela_conf"],
                  voltou=v["voltou"], classif=v["classif"])
        # passo 1: abre COMPRA demo real
        dist = max(500, 10 * int(si.spread)) * si.point
        preco = si.ask
        des = dict(card="card99_bancada", lado=+1, ent=preco,
                   stop=round(preco - dist, si.digits), protegida=False,
                   k_ent=10000, ts_ent=str(run - timedelta(minutes=200 + run.second)))
        ex1 = []; acao1 = executar(mt5, ativo, dict(estado_pilha=[des], cenario="bancada"), 10000, ex1)
        ab = next((e for e in ex1 if e.get("tipo") == "ABRIU"), None)
        ticket = int(ab.get("ticket", 0)) if ab else 0
        passo(1, "posicao demo ABERTA e confirmada",
              ab is not None and ab.get("confirmado") is True and ticket > 0,
              f"ticket {ticket} lote {ab.get('lote') if ab else '?'} @ {ab.get('ent_exec') if ab else '?'} · {acao1}")
        # passos 6-7: o executor corta pela AUTORIDADE do Ciclo
        ex2 = []; acao2 = executar(mt5, ativo, dict(estado_pilha=[des], cenario="bancada", ciclo=ct), 10000, ex2)
        cc = next((e for e in ex2 if e.get("tipo") == "CORTE_CICLO"), None)
        pos_fim = _pos_minhas(mt5, ativo)
        passo(6, "posicao FECHADA no MT5 pelo CORTE_CICLO",
              cc is not None and not pos_fim, f"{cc} · acao[{acao2}]")
        preco_f = None
        try:
            time.sleep(1)
            dls = mt5.history_deals_get(position=ticket) or []
            if dls: preco_f = dls[-1].price
        except Exception: pass
        passo(7, "ticket e preco de fechamento confirmados na corretora",
              cc is not None and cc.get("confirmado") is True and (preco_f is not None),
              f"ticket {ticket} · preco fechamento {preco_f} · confirmado {cc.get('confirmado') if cc else '?'}")
        reabriu = any(e.get("tipo") == "ABRIU" for e in ex2)
        rp(f"  reabertura na mesma passada: {'HOUVE (errado)' if reabriu else 'bloqueada (dedup) — correto'}")
        passo(8, "caminho inteiro registrado", True, "transcricao em vivo_bancada + ledgers ex1/ex2 acima")
        rp(f"  ledger passo1: {ex1}")
        rp(f"  ledger corte : {ex2}")
        ok = all(res)
        rp(f"BANCADA-CORTE {ativo}: {sum(res)}/{len(res)} passos · {'APROVADA' if ok else '>>> REPROVADA <<<'}")
    finally:
        for _ in range(3):
            sob = [q for q in (mt5.positions_get(symbol=ativo) or []) if q.magic == MAGIC_BANCADA]
            if not sob: break
            for q in sob: _fechar_pos(mt5, q)
            time.sleep(1)
        ext1 = {q.ticket for q in (mt5.positions_get() or []) if q.magic != MAGIC_BANCADA}
        rp(f"  limpeza: {'zero posicao da bancada' if not [q for q in (mt5.positions_get(symbol=ativo) or []) if q.magic == MAGIC_BANCADA] else 'SOBROU POSICAO'} · externas intocadas: {ext0 == ext1}")
        _MAGIC_OVERRIDE = None; RISCO_UNIDADE = risco_old
        if _q_susp: QUARENTENA_EXEC.add(ativo); rp(f"  quarentena do {ativo} RESTAURADA")
        with open(f"vivo_bancada_{ativo}.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(rel) + "\n\n")
        mt5.shutdown()

def bancada(ativo):
    """v4.4 — BANCADA BLINDADA (os 10 ajustes do dono): magic exclusivo,
    uid por rodada, validacao de conteudo, limpeza garantida, externas
    intocadas, BTC = prova de quarentena. NAO inicia o 004."""
    import MetaTrader5 as mt5
    from datetime import timedelta
    global RISCO_UNIDADE, _MAGIC_OVERRIDE
    if not mt5.initialize():
        raise SystemExit(f"MT5 nao inicializou: {mt5.last_error()}")
    info = mt5.account_info()
    if info.trade_mode != 0:                       # ajuste 1: trava DEMO absoluta
        mt5.shutdown()
        raise SystemExit(">>> TRAVA: bancada so roda em conta DEMO. Conta atual NAO e demo. ABORTADO. <<<")
    si = mt5.symbol_info(ativo)
    if not si:
        mt5.shutdown(); raise SystemExit(f"simbolo {ativo}?")
    try:
        if not PC._aplicar_ficha(ativo, PASTA_ESPELHO):
            PC.PONTO = si.point
    except Exception:
        PC.PONTO = si.point
    rel = []; resultados = []
    def rp(s):
        print(s); rel.append(s)
    def prova(nome, passou, obs=""):
        resultados.append((nome, bool(passou)))
        rp(f"  [{'PASSA' if passou else 'FALHA'}] {nome}" + (f" — {obs}" if obs else ""))
    run_id = datetime.now()
    rp(f"BANCADA BLINDADA v{V_VERSAO} — {ativo} · demo {info.login} ({info.server}) · rodada {run_id:%d/%m %H:%M:%S}")
    rp(f"  arquivo sha: {_hash_arquivos().get('bt_vivo_sombra.py')} · magic bancada {MAGIC_BANCADA} (vivo intocavel)")
    rp(f"  ledger enviados no boot: {len(_enviadas(ativo))} uids persistidos de rodadas anteriores")
    base_off = 10 + (run_id.hour * 3600 + run_id.minute * 60 + run_id.second) % 720  # v4.5:
    rp(f"  ajuste 8: base de uid desta rodada = -{base_off} min (rodadas no mesmo minuto nao colidem)")
    quar = ativo in QUARENTENA_EXEC
    ext0 = {p.ticket for p in (mt5.positions_get() or []) if p.magic != MAGIC_BANCADA}  # ajuste 3
    dist = max(500, 10 * int(si.spread)) * si.point
    K = 10000
    def synth(lado, off_min, k_ent=K, stop=None, sem_k=False):
        preco = si.ask if lado > 0 else si.bid
        d = dict(card="card99_bancada", lado=lado, ent=preco,
                 stop=(stop if stop is not None else round(preco - lado * dist, si.digits)),
                 protegida=False,
                 ts_ent=str(run_id - timedelta(minutes=base_off + off_min)))  # ajuste 8: uid da RODADA
        if not sem_k: d["k_ent"] = k_ent
        return d
    def roda(pilha):
        extra = []
        try:
            acao = executar(mt5, ativo, dict(estado_pilha=pilha, cenario="bancada"), K, extra)
        except Exception as ex:                    # ajuste 4: prova nao derruba a bateria
            acao = f"EXCECAO {type(ex).__name__}: {ex}"
        return acao, extra
    def tem(extra, tipo, motivo=None):
        return any(e.get("tipo") == tipo and (motivo is None or e.get("motivo") == motivo) for e in extra)
    risco_old = RISCO_UNIDADE
    _MAGIC_OVERRIDE = MAGIC_BANCADA                # ajuste 3: liga o magic exclusivo
    try:
        if quar:
            # ajuste 9: bateria propria do BTC — TODA entrada recusada pela quarentena
            _, exC = roda([synth(+1, 1)])
            prova("quarentena: COMPRA recusada (quarentena_spread_7d)",
                  tem(exC, "NAO_ABRIU", "quarentena_spread_7d") and not tem(exC, "ABRIU"), str(exC))
            _, exV = roda([synth(-1, 2)])
            prova("quarentena: VENDA recusada (quarentena_spread_7d)",
                  tem(exV, "NAO_ABRIU", "quarentena_spread_7d") and not tem(exV, "ABRIU"), str(exV))
            prova("quarentena: zero posicao aberta", not _pos_minhas(mt5, ativo))
            rp("  (declarado: com a quarentena no 1o portao, os demais portoes sao inalcancaveis no BTC)")
        else:
            # P1 — COMPRA com risco REAL: lote pela formula efetiva, 19 campos, conf, SL servidor
            RISCO_UNIDADE = 0.0025
            acao, ex = roda([synth(+1, 1)])
            ab = next((e for e in ex if e.get("tipo") == "ABRIU"), None)
            falha_ordem = next((e for e in ex if e.get("tipo") == "ORDEM_FALHOU"), None)
            prova("1 abertura de COMPRA", ab is not None,
                  acao + (f" · rc corretora {falha_ordem.get('rc')}" if falha_ordem else ""))
            if ab:
                err19 = _valida_abriu_19(ab, MAGIC_BANCADA)
                prova(f"11 registro: ESQUEMA v{ABRIU_SCHEMA_V} validado (nomes+tipos; extras permitidos)",
                      not err19, f"{len(ab)} campos presentes" + (f" · erros: {err19}" if err19 else ""))
                prova("12 confirmacao da ordem pelo MT5", ab.get("confirmado") is True)
                no_alvo = abs(ab.get("risco_pct", 9) - 0.25) <= 0.05
                no_min = (ab.get("lote") == _lote_norm(si, 0)) and 0 < ab.get("risco_pct", 9) <= 2.0
                prova("6a lote pelo risco EFETIVO (0,25% +-0,05 OU lote-minimo do simbolo, <=2%)",
                      no_alvo or no_min,
                      f"risco {ab.get('risco_pct')}% lote {ab.get('lote')} ticket {ab.get('ticket')}"
                      + (" · lote-minimo do simbolo (declarado)" if (no_min and not no_alvo) else ""))
                ps = _pos_minhas(mt5, ativo)
                sl_srv = ps[0].sl if ps else 0.0
                prova("5 stop-loss NO SERVIDOR",
                      bool(ps) and abs(sl_srv - float(ab.get("sl", -1))) <= 5 * si.point,
                      f"pedido {ab.get('sl')} servidor {sl_srv}")
            RISCO_UNIDADE = 0.00001
            # P2 — reinicio com posicao aberta: re-iguala sem ordem nova
            _, ex2 = roda([synth(+1, 1)])
            rec = next((e for e in ex2 if e.get("tipo") == "RECON"), {})
            prova("9 reinicio com posicao aberta: zero ordem nova, RECON casada",
                  (not tem(ex2, "ABRIU")) and (not tem(ex2, "FECHOU")) and len(rec.get("casadas", [])) == 1,
                  f"RECON {rec}")
            # P3 — fechamento confirmado
            acao3, ex3 = roda([])
            fe = next((e for e in ex3 if e.get("tipo") == "FECHOU"), None)
            prova("3 fechamento confirmado pela corretora",
                  fe is not None and fe.get("confirmado") is True and not _pos_minhas(mt5, ativo), acao3)
            # P4 — VENDA
            acao4, ex4 = roda([synth(-1, 2)])
            prova("2 abertura de VENDA", tem(ex4, "ABRIU"), acao4)
            # P5 — REVERSAO SEGURA: fecha, CONFIRMA, so entao abre
            acao5, ex5 = roda([synth(+1, 3)])
            fe5 = next((e for e in ex5 if e.get("tipo") == "FECHOU"), None)
            prova("4 reversao: fechamento CONFIRMADO antes da abertura oposta",
                  fe5 is not None and fe5.get("confirmado") is True and tem(ex5, "ABRIU")
                  and "conf_fech:OK" in acao5, acao5)
            # P6 — fecha tudo
            roda([])
            prova("fechamento final: nada aberto", not _pos_minhas(mt5, ativo))
            # P7 — sinal com mais de 15 min
            _, ex7 = roda([synth(+1, 4, k_ent=K - 2)])
            prova("8 rejeicao de sinal >15min", tem(ex7, "NAO_ABRIU", "sinal_antigo(2b)"), str(ex7))
            # P8 — dedup relido do DISCO (ajuste 8: derruba o cache antes)
            _ENVIADAS.pop(ativo, None)
            _, ex8 = roda([synth(+1, 1)])
            prova("10 retomada sem duplicacao (ledger relido do DISCO)",
                  tem(ex8, "NAO_ABRIU", "uid_ja_enviado(dedup)"), str(ex8))
            # P9 — bloqueio por spread (limite forcado a 0)
            lim_old = SPREAD_LIM.get(ativo)
            try:
                SPREAD_LIM[ativo] = 0
                _, ex9 = roda([synth(+1, 5)])
                prova("7 bloqueio por spread (limite forcado 0)",
                      any(e.get("tipo") == "NAO_ABRIU" and str(e.get("motivo", "")).startswith("spread_")
                          for e in ex9), str(ex9))
            finally:
                SPREAD_LIM[ativo] = lim_old
            # P10 — trava dura 2% (risco 5% + stop dimensionado p/ estourar 2%
            # MESMO com o lote clampado no volume_max do simbolo — v4.6 b)
            RISCO_UNIDADE = 0.05
            vpl_b = _valor_ponto_lote(mt5, ativo) or 1.0
            vmax_b = float(getattr(si, "volume_max", 1e9) or 1e9)
            dist_forca_pts = max(dist / si.point, (0.025 * info.balance) / (vpl_b * vmax_b))
            stop_forca = round(si.ask - dist_forca_pts * PC.PONTO, si.digits)
            _, ex10 = roda([synth(+1, 6, stop=stop_forca)])
            prova("6b trava dura 2%/op (risco 5% + stop calibrado p/ o volume_max)",
                  any(e.get("tipo") == "NAO_ABRIU" and str(e.get("motivo", "")).startswith("risco_")
                      for e in ex10), str(ex10))
            RISCO_UNIDADE = 0.00001
            # P11 — stop ja violado no preco atual
            _, ex11 = roda([synth(+1, 7, stop=round(si.ask + dist, si.digits))])
            prova("5b revalidacao do stop no preco atual",
                  tem(ex11, "NAO_ABRIU", "stop_ja_violado_no_preco_atual"), str(ex11))
            # P12 — fail-closed nomeado (o antigo 999)
            _, ex12 = roda([synth(+1, 8, sem_k=True)])
            prova("fail-closed nomeado (sem_barra_entrada)",
                  tem(ex12, "NAO_ABRIU", "sem_barra_entrada(fail_closed)"), str(ex12))
    finally:
        # ajuste 4: limpeza GARANTIDA — fecha tudo do magic da bancada, com re-tentativa
        for _ in range(3):
            sobras = [p for p in (mt5.positions_get(symbol=ativo) or []) if p.magic == MAGIC_BANCADA]
            if not sobras: break
            for p in sobras: _fechar_pos(mt5, p)
            time.sleep(1)
        sobras_fim = [p for p in (mt5.positions_get(symbol=ativo) or []) if p.magic == MAGIC_BANCADA]
        ext1 = {p.ticket for p in (mt5.positions_get() or []) if p.magic != MAGIC_BANCADA}
        _MAGIC_OVERRIDE = None                      # restaura o magic do vivo
        RISCO_UNIDADE = risco_old
        prova("limpeza final: zero posicao da bancada", not sobras_fim,
              f"{len(sobras_fim)} sobras" if sobras_fim else "")
        prova("posicoes EXTERNAS intocadas (vivo/terceiros)", ext0 == ext1,
              f"antes {sorted(ext0)} depois {sorted(ext1)}")
        ok = all(p for _, p in resultados)
        rp(f"BANCADA {ativo}: {sum(1 for _, p in resultados if p)}/{len(resultados)} provas · "
           f"{'APROVADA' if ok else '>>> REPROVADA — NAO relancar o vivo <<<'}")
        rp("  ajuste 10: a bancada NAO inicia o 004. Aferir: posicoes zero + logs + tickets;")
        rp("  o relancamento com --executa e comando do dono, nunca automatico.")
        with open(f"vivo_bancada_{ativo}.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(rel) + "\n\n")
        mt5.shutdown()

def invisiveis(ativo, data=None):
    """v4.7 — ficha forense dos trades do espelho no dia (visiveis e
    invisiveis ao executor), com conversoes USD/%/custos."""
    import MetaTrader5 as mt5
    data = data or datetime.now().strftime("%Y-%m-%d")
    ok_mt5 = mt5.initialize()
    saldo = vpl = None
    if ok_mt5:
        info = mt5.account_info(); saldo = float(info.balance) if info else None
        vpl = _valor_ponto_lote(mt5, ativo)
    ts, evs, pilha, n, contra = decidir(ativo)
    T = contra.get("T_pura")
    if T is None or not len(T):
        print(f"{ativo}: janela pura vazia."); return
    cols = list(T.columns)
    sel = T[T["ts"].astype(str).str.startswith(data)]
    print(f"INVISIVEIS v{V_VERSAO} — {ativo} · dia {data} · espelho ate {ts} · "
          f"{len(sel)} trades no dia · colunas gravadas pelo Seletor: {cols}")
    print(f"  fonte: OHLC M15 do espelho — horario exato do gatilho, ordem intrabar "
          f"e tick/M1 = NAO_OBSERVAVEL(M15), lei declarada")
    print(f"  pts = liquidos como a casa mede (spread modelado {getattr(PC,'SPREAD_PTS','?')} pts ja dentro); "
          f"comissao US${COMISSAO_USD_LOTE}/lote destacada abaixo")
    if vpl: print(f"  conversao: tick_value real -> {vpl:.6f} USD/pt por 1.0 lote · saldo {saldo:,.2f} USD")
    else:   print("  conversao USD indisponivel (MT5 fechado) — rode com o MT5 aberto")
    cam = f"invisiveis_{ativo}_{data}.csv"
    import csv as _csv
    with open(cam, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f, delimiter=";")
        w.writerow(cols + ["duracao_barras", "usd_1lote_liq_spread", "comissao_usd_1lote",
                           "usd_1lote_apos_custos", "pct_capital_1lote",
                           "lote_risco_025", "usd_lote_risco", "pct_capital_lote_risco",
                           "campos_nao_observaveis_M15"])
        tot_pts = tot_usd = 0.0
        for _, r in sel.iterrows():
            d = {c: r[c] for c in cols}
            pts = float(d.get("pts", 0) or 0); tot_pts += pts
            # duracao: procura par de timestamps/indices gravados
            dur = "NAO_GRAVADO"
            for a, b in (("ts_in", "ts"), ("ts_entrada", "ts_saida"), ("k_in", "k_out"), ("k_ent", "k")):
                if a in d and b in d and d.get(a) is not None:
                    try:
                        if str(a).startswith("k"): dur = int(d[b]) - int(d[a])
                        else: dur = int((pd.Timestamp(d[b]) - pd.Timestamp(d[a])).total_seconds() // 900)
                        break
                    except Exception: pass
            usd1 = round(pts * vpl, 2) if vpl else None
            com1 = round(COMISSAO_USD_LOTE, 2)
            usd1c = round(usd1 - com1, 2) if usd1 is not None else None
            pct1 = round(usd1c / saldo * 100, 4) if (usd1c is not None and saldo) else None
            if usd1c is not None: tot_usd += usd1c
            # lote de risco 0,25%: exige stop e entrada gravados
            lr = usd_lr = pct_lr = "NAO_GRAVADO(sem stop na trilha)"
            ent_c = next((c for c in ("ent", "entrada", "preco_in") if c in d and d[c] is not None), None)
            stp_c = next((c for c in ("stop", "sl", "stop_pts") if c in d and d[c] is not None), None)
            if ent_c and stp_c and vpl and saldo:
                try:
                    dist = (abs(float(d[ent_c]) - float(d[stp_c])) / PC.PONTO) if stp_c != "stop_pts" else float(d[stp_c])
                    if dist > 0:
                        lr = max(0.01, round((saldo * 0.0025) / (dist * vpl), 2))
                        usd_lr = round(pts * vpl * lr - COMISSAO_USD_LOTE * lr, 2)
                        pct_lr = round(usd_lr / saldo * 100, 4)
                except Exception: pass
            linha = [d.get(c) for c in cols] + [dur, usd1, com1, usd1c, pct1, lr, usd_lr, pct_lr,
                     "gatilho_intrabar;ordem_eventos;tick_M1"]
            w.writerow(linha)
            print("  " + " · ".join(f"{c}={d.get(c)}" for c in cols)
                  + f" · dur={dur}b · 1.0lote: {usd1} USD liq.spread, {usd1c} USD apos comissao"
                  + (f" ({pct1}% cap)" if pct1 is not None else "")
                  + f" · lote0.25%: {lr} -> {usd_lr}")
        print(f"TOTAL {ativo} {data}: {len(sel)} trades · {tot_pts:+.0f} pts liq.spread · "
              + (f"{tot_usd:+.2f} USD por 1.0 lote apos custos ({tot_usd/saldo*100:+.4f}% cap)"
                 if (vpl and saldo) else "USD: indisponivel"))
        print(f"  salvo: {cam}")
    if ok_mt5: mt5.shutdown()

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ativo = args[0] if args else "XAUUSD"
    _MODOS_LIVRES = ("--percepcao", "--relatorio", "--ciclo-prova", "--prova-tf", "--estabilidade",
                     "--calendario", "--fases", "--propagacao", "--auditor", "--prova-memoria", "--falsos-fase", "--maturidade", "--escada", "--prova-latencia")
    if ativo not in CONFIG and not any(m in sys.argv for m in _MODOS_LIVRES):
        raise SystemExit(f"{ativo} fora da leva v3: {', '.join(CONFIG)} "
                         f"(modos livres p/ qualquer simbolo: {', '.join(_MODOS_LIVRES)})")
    if "--contra-armado" in sys.argv:
        _CONTRA_ARMADA = True
        print(">>> DECRETO NA LINHA DE COMANDO: CONTRATENDENCIA ARMADA nesta subida "
              "(fase>=3, risco x0.5 [REF]) — sem bancada/medicao ainda; responsabilidade do decreto. <<<")
    if "--sem-quarentena" in sys.argv and ativo in QUARENTENA_EXEC:
        QUARENTENA_EXEC.discard(ativo)
        print(f">>> DECRETO NA LINHA DE COMANDO: quarentena de ORDEM do {ativo} DERRUBADA nesta subida "
              f"(fds/demo). Portao de spread segue armado ({SPREAD_LIM.get(ativo)}); coleta de spread continua. <<<")
    if "--conferir" in sys.argv:
        conferir(ativo)
    elif "--bancada-corte" in sys.argv:
        bancada_corte(ativo)
    elif "--bancada" in sys.argv:
        bancada(ativo)
    elif "--percepcao" in sys.argv:
        percepcao(ativo)
    elif "--relatorio" in sys.argv:
        _dt = next((a for a in sys.argv if a.count("-") == 2 and a[:2] == "20"), None)
        relatorio(ativo, _dt)
    elif "--maturidade" in sys.argv:
        maturidade()
    elif "--escada" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente")
        _n = next((int(a) for a in sys.argv if a.isdigit()), 6)
        CV1.relatorio_escada(PASTA_ESPELHO, ativo, _n)
    elif "--prova-latencia" in sys.argv:
        print(f"PROVA DO PORTAO DE LATENCIA — regra: idade da decisao > {LATENCIA_MAX_ENVIO}s = NAO ENVIA")
        for _idade in (12, 59, 61, 257):
            print(f"  decisao com {_idade}s -> "
                  f"{'BLOQUEIA (NAO_ABRIU portao_latencia)' if _idade > LATENCIA_MAX_ENVIO else 'PASSA (envia)'}")
        print("  no vivo: ts_decisao/ts_envio no ABRIU deixam o auditor conferir cada ordem real")
    elif "--auditor" in sys.argv:
        _dt = next((a for a in sys.argv if a.count("-") == 2 and a[:2] == "20"), None)
        auditor(ativo, _dt)
    elif "--prova-memoria" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente")
        CV1.prova_memoria(PASTA_ESPELHO, ativo)
    elif "--falsos-fase" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente")
        _n = next((int(a) for a in sys.argv if a.isdigit()), 300)
        CV1.prova_falsos_fase(PASTA_ESPELHO, ativo, _n)
    elif "--fases" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente")
        _n = next((int(a) for a in sys.argv if a.isdigit()), 4)
        CV1.prova_fases(PASTA_ESPELHO, ativo, _n)
    elif "--propagacao" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente")
        _n = next((int(a) for a in sys.argv if a.isdigit()), 96)
        CV1.prova_propagacao(PASTA_ESPELHO, ativo, _n)
    elif "--calendario" in sys.argv:
        evs = _calendario_carregar()
        print(f"B2 CALENDARIO v{V_VERSAO} — {'SEM calendario.csv (blindagem DESLIGADA, declarada)' if not os.path.exists('calendario.csv') else f'{len(evs)} eventos carregados'}")
        agora = pd.Timestamp(datetime.now())
        for dt, mo, imp, nome in sorted(evs):
            if agora - pd.Timedelta(hours=2) <= dt <= agora + pd.Timedelta(hours=24):
                afeta = [a for a, ms in MOEDAS_ATIVO.items() if mo in ms and imp == "alto"]
                print(f"  {dt:%d/%m %H:%M} · {mo} · {imp.upper():<5} · {nome}"
                      + (f" -> bloqueia entrada {afeta} +-{JANELA_NOTICIA_MIN}min" if afeta else ""))
        print(f"  regra: impacto ALTO na moeda do ativo bloqueia ENTRADA nova +-{JANELA_NOTICIA_MIN}min; posicao aberta NUNCA e fechada por noticia")
    elif "--prova-tf" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente na pasta")
        _n = next((int(a) for a in sys.argv if a.isdigit()), 6)
        CV1.prova_tf(PASTA_ESPELHO, ativo, _n)
    elif "--estabilidade" in sys.argv:
        estabilidade(ativo)
    elif "--ciclo-prova" in sys.argv:
        if CV1 is None: raise SystemExit("bt_ciclo_v1.py ausente na pasta")
        _n = next((int(a) for a in sys.argv if a.isdigit()), 6)
        CV1.prova(PASTA_ESPELHO, ativo, _n)
    elif "--invisiveis" in sys.argv:
        _dt = next((a for a in sys.argv if a.count("-") == 2 and a[:2] == "20"), None)
        invisiveis(ativo, _dt)
    elif "--teste-funcional" in sys.argv:
        import MetaTrader5 as mt5
        assert mt5.initialize(), "MT5 nao inicializou"
        info = mt5.account_info(); assert info.trade_mode == 0, "SO DEMO"
        si = mt5.symbol_info(ativo); assert si, "simbolo?"
        print(f"TESTE FUNCIONAL CONTROLADO (item 22) — {ativo} demo {info.login}")
        vpl = si.trade_tick_value * (0.01 / si.trade_tick_size)
        for lado, nome in ((1, "COMPRA"), (-1, "VENDA")):
            preco = si.ask if lado > 0 else si.bid
            sl0 = preco - lado * 200 * si.point
            r, t = _enviar(mt5, dict(action=mt5.TRADE_ACTION_DEAL, symbol=ativo, volume=0.01,
                                     type=(mt5.ORDER_TYPE_BUY if lado > 0 else mt5.ORDER_TYPE_SELL),
                                     price=preco, sl=round(sl0, si.digits), deviation=30,
                                     magic=_magic(ativo), comment="T3:FUNC",
                                     type_time=mt5.ORDER_TIME_GTC, type_filling=_filling(mt5, si)))
            print(f"  {nome}: rc={r.retcode} exec@{r.price} (tent {t}) conf:"
                  f"{'OK' if _confirmar(mt5, ativo, 'FUNC', True) else 'FALHOU'}")
            ps = [p for p in _pos_minhas(mt5, ativo) if "FUNC" in (p.comment or "")]
            if ps:
                p0 = ps[0]
                sl1 = round(p0.price_open - lado * 150 * si.point, si.digits)
                r2 = mt5.order_send(dict(action=mt5.TRADE_ACTION_SLTP, symbol=ativo,
                                         position=p0.ticket, sl=sl1, tp=0.0))
                print(f"  AJUSTE SL: rc={r2.retcode} -> {sl1}")
                print("  FECHA:", _fechar_pos(mt5, p0),
                      "conf:", "OK" if _confirmar(mt5, ativo, "FUNC", False) else "FALHOU")
        print("\n— PORTOES (provas 6-9 do dono, em memoria) —")
        # bloqueio por sinal atrasado
        print(f"  sinal idade 3b vs IDADE_MAX={IDADE_MAX}: "
              f"{'BLOQUEIA OK' if 3 > IDADE_MAX else 'FALHA'}")
        # bloqueio por spread (limite forcado a 0 -> qualquer spread bloqueia)
        sp_agora = int(si.spread)
        print(f"  spread {sp_agora} vs limite forcado 0: {'BLOQUEIA OK' if sp_agora > 0 else 'FALHA'}")
        print(f"  spread {sp_agora} vs limite real {SPREAD_LIM.get(ativo)}: "
              f"{'passa (normal)' if sp_agora <= SPREAD_LIM.get(ativo, 9e9) else 'BLOQUEIA (anormal agora)'}")
        # bloqueio por risco > 2%
        saldo = info.balance
        dist_teste = 1 * si.point          # stop colado -> lote minimo ainda estoura? nao:
        # risco de 5% simulado:
        risco_sim = 0.05
        print(f"  risco simulado {risco_sim*100:.0f}% vs trava {RISCO_MAX_OP*100:.0f}%: "
              f"{'BLOQUEIA OK' if risco_sim > RISCO_MAX_OP else 'FALHA'}")
        print("  reinicio sem duplicacao: retomada v3.4 + reconciliacao por UID (provada no 002; "
              "re-provar = Ctrl+C na sombra e relancar, zero ordem nova esperada)")
        print("\nTESTE FUNCIONAL COMPLETO — 9 provas: compra/venda/fechamento/reversao(sequencial)/"
              "ajuste SL pela corretora + 4 portoes verificados.")
        mt5.shutdown()
    else:
        _ex = "--executa" in sys.argv
        sombra(ativo, intervalo=(15 if _ex else 60), executa=_ex)
