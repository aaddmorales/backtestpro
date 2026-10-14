# -*- coding: utf-8 -*-
"""C27R49 — reprodução cronológica dos PONTOS MARCADOS pelo dono no gráfico do Gold (XAUUSD M15, 12–14/10/2026; hora do gráfico =
servidor = Kyiv = UTC+3). Pontos 1–7 e 9–12 (o 8 não está no gráfico e não é inventado). Só com o que estava GRAVADO em cada instante:
auditoria_candles (M15, carimbo do EA), auditoria_leituras (estrutura por tempo do leitor no 1º snapshot da barra), selecao_avaliacoes
(candidatos, portões, escolha), ciclo_decisoes/mt5_comandos/sessao_aberturas (decisão, comando, execução, gestão).
`python -m testes.reproducao_gold_pontos_1214` imprime o JSON; test_38 valida as classificações."""
import json

K = "Kyiv (UTC+3)"
# (ponto, rótulo do dono, candle M15 UTC, Kyiv, OHLC, pivô/nível, reconhecimento pelo motor, eventos, leituras M1/M5/M15 (1º snapshot),
#  estratégias/sinais, decisão/gestão real, classificação, fundamento)
PONTOS = [
    {"ponto": 1, "rotulo": "Topo", "candle_utc": "2026-10-12 02:00", "kyiv": "12/10 05:00", "ohlc": (4211.87, 4214.23, 4207.61, 4213.52),
     "pivo": {"tipo": "topo", "provisorio": "máxima 4217.23 da M15 01:00 UTC (04:00 Kyiv) — 1ª alta; 2ª alta 4214.23 às 02:00 UTC", "confirmado": "último topo 4214.23 no mapa de pivôs do M15 (leitura 04:00:34 UTC = 07:00 Kyiv, 2 barras depois); às 05:00 UTC o mapa já traz o topo menor 4208.27 (03:45)"},
     "eventos": ["M30 momentum enfraquecendo em compressão (04:00 UTC)", "M15 compressao_armada, canal 0 (04:00 UTC)"],
     "leituras": {"04:00:34 UTC": "M1 −1 fundo_da_faixa · M5 −1 compressao_armada · M15 0 mista/compressão meio_da_faixa topo 4214.23 fundo 4201.59 · M30 0 compressão enfraquecendo"},
     "estrategias": "nenhum card de reversão confirmou VENDA entre 02:15 e 03:45 UTC (fila sem candidato de venda; só vendas a partir de 04:00 UTC)",
     "decisao_real": "nenhuma (sem candidato)", "gestao_real": None,
     "classificacao": "detectou o pivô (2 barras depois), nenhuma estratégia de reversão confirmou no topo — não detectou como entrada",
     "fundamento": "o topo é reconhecido pelo mapa N=2 do motor com atraso estrutural de 2 barras (por desenho); nenhum dos 13 cards emitiu venda de reversão no topo; a 1ª venda confirmada é o MACD M30 às 04:00 UTC (ponto 2)"},
    {"ponto": 2, "rotulo": "Rompimento da mínima — Entrada", "candle_utc": "2026-10-12 04:00", "kyiv": "12/10 07:00", "ohlc": (4203.19, 4204.35, 4198.05, 4198.87),
     "pivo": {"tipo": "quebra da mínima relevante", "nivel": "fechamento 4198.87 < último fundo do M15 4201.59 (e < mínima 4200.07 da barra 01:30 UTC)", "reconhecimento": "M15 quebra_estrutura_baixa e M5 quebra_estrutura_baixa na leitura 05:00:21 UTC (08:00 Kyiv) — 1 barra depois do fechamento (exige fechamento)"},
     "eventos": ["M1 rompimento_confirmado(por_barra) 04:00", "M5 quebra_estrutura_baixa 05:00", "M15 quebra_estrutura_baixa 05:00"],
     "leituras": {"04:00:34 UTC": "M1 −1 · M5 −1 · M15 0 mista/compressão · M30 0 enfraquecendo", "05:00:21 UTC": "M1 −1 · M5 −1 quebra_baixa · M15 −1 mista/compressão quebra_baixa topo 4208.27 · M30 −1 tendência acelerando"},
     "estrategias": "04:00 UTC: MACD M30 venda CONFIRMADA (ref 4203.14, risco 1304 pts) — portões 1–7 e 9 abertos; portão 8 (sel-3) fechado: 39 pts > 30 fixos; 04:15: 358 pts (recusa correta)",
     "decisao_real": "nenhuma: sel-3 recusou no portão 8 (régua fixa de 30 pts)", "gestao_real": None,
     "classificacao": "detectou e recusou", "fundamento": "selecao_avaliacoes bot 12 barra 04:00 UTC (reproducao_gold_1210.CANDIDATOS_VENDA); a régua proporcional (sel-4: max(30, 10% do risco) = 130 pts) teria aceitado; na 8.14 ao vivo a r01v5 ainda usava 30 fixos (8.15 nunca implantada)"},
    {"ponto": 3, "rotulo": "Rompimento da média — Entrada", "candle_utc": "2026-10-12 04:45", "kyiv": "12/10 07:45", "ohlc": (4197.95, 4198.84, 4193.73, 4194.78),
     "pivo": {"tipo": "fechamento abaixo do canal EMA20 (mínimas)", "nivel": "fechamento 4194.78; canal EMA20 H/L do M30 virou baixa", "reconhecimento": "card4 canal EMA20 M30 venda confirmado 05:00 UTC (fechamento do M30 04:30–05:00)"},
     "eventos": ["M15 quebra_estrutura_baixa (05:00)", "M30 canal −1 tendência acelerando (05:00)"],
     "leituras": {"05:00:21 UTC": "M1 −1 · M5 −1 quebra_baixa · M15 −1 mista/compressão · M30 −1 tendência acelerando"},
     "estrategias": "05:00 UTC: canal EMA20 M30 venda CONFIRMADA (ref 4194.78, risco 1531 pts) — portão 8 fechado: 54 pts > 30; rompimento de caixa M15 venda (265 pts: recusa correta)",
     "decisao_real": "nenhuma (portão 8, régua fixa)", "gestao_real": None,
     "classificacao": "detectou e recusou", "fundamento": "mesma causa do ponto 2; limite proporcional = 153 pts aceitaria 54"},
    {"ponto": 4, "rotulo": "Pull back — Entrada", "candle_utc": "2026-10-12 06:00", "kyiv": "12/10 09:00", "ohlc": (4191.08, 4192.73, 4183.27, 4185.73),
     "pivo": {"tipo": "pullback ao canal e retomada", "nivel": "05:45 UTC fechou 4191.07 (toque no canal EMA20), 06:00 UTC fechou 4185.73 (retomada da queda)", "reconhecimento": "engolfo M15 venda confirmado 06:15 UTC (barra 06:00 fechada)"},
     "eventos": ["M15 descendente/tendência fundo_da_faixa, rompimento_confirmado (06:15)", "M5 voltou_compressao (06:15)"],
     "leituras": {"06:15:42 UTC": "M1 −1 · M5 −1 voltou_compressao · M15 −1 descendente/tendência fundo_da_faixa topo 4208.27 fundo 4179.41 · M30 −1 tendência"},
     "estrategias": "06:15 UTC: engolfo M15 venda CONFIRMADA (ref 4185.73, risco 2450 pts) — portão 8 fechado: 135 pts > 30 (proporcional 245: aceitaria); 06:30 engolfo M15/M30 (130/109 pts) idem",
     "decisao_real": "nenhuma até 08:45 UTC; op 10 real: Donchian M15 venda @4176.17 às 08:45 UTC (11:45 Kyiv), fechada 09:30 UTC por B3 + corte fino (gestao-1): −1,69", "gestao_real": "op 10: 2 avaliações; fechada no 1º B3 com 2º sinal fino (gestao-1 tratava fino como estrutural)",
     "classificacao": "detectou e recusou (06:15) · reagiu tarde (08:45) · saiu cedo (09:30)", "fundamento": "a venda da pernada 4199→4169 (pontos 2→5) nunca foi carregada: recusas pela régua fixa e depois saída precoce da op 10 (C27R44 corrigiu a gestão; gestao-3 no replay mantém até 10:15, ainda pior que o real)"},
    {"ponto": 5, "rotulo": "Saída: fechamento acima das 2 médias", "candle_utc": "2026-10-12 17:00", "kyiv": "12/10 20:00", "ohlc": (4164.81, 4169.09, 4164.27, 4168.83),
     "pivo": {"tipo": "retomada contra a venda", "nivel": "fechamento 4168.83 acima das EMA20 H/L (~4166/4167)", "reconhecimento": "M1 quebra_estrutura_alta e M5 sacudida_fundo (17:00:41 UTC); M15 ainda canal −1 compressão (rótulo) — a saída de uma venda viria da gestão (B3/corte/trailing), não de regra de 'fechamento acima das médias', que não existe no contrato"},
     "eventos": ["M1 quebra_estrutura_alta (17:00)", "M5 sacudida_fundo (17:00)", "M15 compressao_armada canal −1 (17:00)"],
     "leituras": {"17:00:41 UTC": "M1 +1 quebra_alta · M5 0 sacudida_fundo · M15 −1 mista/compressão topo 4170.92 fundo 4158.82 · M30 −1 compressão"},
     "estrategias": "17:00–17:45 UTC: MACD M15 COMPRA confirmada — vetada pelo portão 5 (selo); 18:00–19:30: canal EMA20 / reversão / EMA 9-21 / topo-fundo duplo M15 compra — selo (5) ou vencido (3); 19:45 UTC: canal EMA20 M30 VENDA elegível → op 11 @4167.38, fechada 20:15 UTC por corte fino com continuidade perdida: −28,61",
     "decisao_real": "op 11 (venda) às 19:45 UTC, contra a retomada que o M1 já mostrava desde 17:00", "gestao_real": "op 11: fechada na 1ª avaliação (corte fino + continuidade PERDIDA)",
     "classificacao": "não havia posição para sair (op 10 fechada 09:30); compras detectadas e recusadas (selo); venda das 19:45 = interpretou incorretamente",
     "fundamento": "o selo vetou 4 compras entre 17:00 e 19:30 (sel-5 deixa de vetar); a venda 19:45 entrou com M15 estrutura 'ascendente' canal 0 e M1 +1 — o portão 10 novo (alertas por tempo) não a veta (sem extremo/suporte contra), ela cai pela compatibilidade 'compressão' (continuação 1) e pela gestão: fica declarada como limitação"},
    {"ponto": 6, "rotulo": "Fundo — Reversão", "candle_utc": "2026-10-13 01:45", "kyiv": "13/10 04:45", "ohlc": (4156.91, 4167.51, 4150.65, 4164.93),
     "pivo": {"tipo": "fundo", "provisorio": "M5 sacudida_fundo 4160.83 (00:45:37 UTC = 03:45 Kyiv); M1 exaustao_identificada(E1/E2_alta) 01:00:28 UTC — 1º alerta de reversão", "confirmado": "último fundo 4150.65 no mapa do M15 na leitura 02:00:34 UTC (05:00 Kyiv) com sacudida_fundo + M1 quebra_estrutura_alta (1 barra após o fechamento 01:45)"},
     "eventos": ["00:45 M1 quebra_estrutura_baixa, M5 sacudida_fundo", "01:00 M1 exaustao alta (persistente)", "01:15 M1/M5 +1, M15 sacudida_fundo + alerta_empilhado_3 → op 13 fechada", "01:30 M1 exaustão alta, M15 fundo_barra_rompido", "02:00 M15 sacudida_fundo, M1 quebra_estrutura_alta"],
     "leituras": {"01:15:35 UTC": "M1 +1 asc · M5 +1 quebra_alta · M15 0 asc(rótulo)/compressão sacudida_fundo", "02:00:34 UTC": "M1 +1 quebra_alta exaustão_candidata alta · M5 +1 rompimento_pendente · M15 0 descendente/compressão sacudida_fundo topo 4169.89 fundo 4153.13→4150.65"},
     "estrategias": "op 13 (venda canal EMA20 M30 @4164.33, 00:30 UTC): ganho flutuante +6,6 pts no fechamento 00:45 (bp 1, 2 candles) → 01:15 fechada no repique por alerta_empilhado_3 (gestao-2 estrutural): −24,37; nenhuma compra confirmada entre 02:00 e 02:15 UTC",
     "decisao_real": "op 13 fechada 01:15:40 UTC @4167.74", "gestao_real": "sem proteção: o 3º candle só fecharia 01:15 (regra por tempo não cobre); trailing não apertou (stop estrutural 4177)",
     "classificacao": "executou conforme o contrato (saída no 1º alerta estrutural: degrau 2 + M1/M5 contra), mas sem proteção do ganho antes",
     "fundamento": "a proteção por tempo não resolve saídas antes do 3º candle; proteção ESTRUTURAL (stop no último topo M5/M1 após sacudida_fundo) é o que faltou — proposta registrada, não implementada sem autorização (novo parâmetro)"},
    {"ponto": 7, "rotulo": "Dois sinais: rompimento da máxima e das médias", "candle_utc": "2026-10-13 02:15", "kyiv": "13/10 05:15", "ohlc": (4167.79, 4174.02, 4166.34, 4170.29),
     "pivo": {"tipo": "quebra da máxima relevante + fechamento acima das médias", "nivel": "02:00 UTC fechou 4167.79 (≈ máxima 4167.51 da 01:45); 02:15 fechou 4170.29 acima das EMA20 H/L; 02:30 fechou 4172.07", "reconhecimento": "M5 rompimento_confirmado (02:15:29 UTC); M15 quebra_estrutura_alta + rompimento_pendente (02:30:47); rompeu_ultimo_topo M15 (02:46:51)"},
     "eventos": ["02:15 M5 rompimento_confirmado", "02:30 M15 quebra_estrutura_alta", "02:46 M15 rompeu_ultimo_topo"],
     "leituras": {"02:15:29 UTC": "M1 +1 · M5 +1 rompimento_confirmado · M15 0 descendente/compressão topo 4169.89", "02:30:47 UTC": "M1 +1 exaustão baixa(persistente) · M5 +1 quebra_alta · M15 +1 descendente(rótulo)/quebra_alta"},
     "estrategias": "02:30 UTC: MACD M30 compra CONFIRMADA → elegível → op 15 @4169.03 (02:31:32 UTC); sob a sel-5 card7/card8 M30 também elegíveis às 02:30; nenhum card M15 confirmou compra às 02:00/02:15",
     "decisao_real": "op 15 aberta 02:31 UTC (1 barra M30 após os dois sinais)", "gestao_real": "op 15: continuidade 'PERDIDA' pelo rótulo (defasado) nas 4 avaliações; proteção manual 03:36 (comando 82); fechada 04:00 UTC por alerta_empilhado_3 (+80,20)",
     "classificacao": "executou conforme o contrato (reação na 1ª confirmação de card disponível)", "fundamento": "os sinais do motor (M5 02:15, M15 02:30) precederam o card em 1–2 barras; não existe card 'rompimento da máxima do fundo' — o MACD M30 foi a 1ª confirmação; gestao-3 teria PROTEGIDO em vez de fechar às 04:00 (degrau 2 sem direção contrária: M1/M5/M15 todos +1 às 04:00:50)"},
    {"ponto": 9, "rotulo": "Topo mostrando exaustão — ponto de reversão", "candle_utc": "2026-10-13 05:15", "kyiv": "13/10 08:15", "ohlc": (4197.95, 4200.53, 4194.01, 4194.18),
     "pivo": {"tipo": "topo", "provisorio": "exaustao_identificada no M15 na origem do corte da op 48 (05:15:27 UTC)", "confirmado": "último topo 4200.53 no mapa do M15 só na leitura 06:30:38 UTC (09:30 Kyiv) — 1h15 depois (N=2 + barras fechadas)"},
     "eventos": ["04:00 M1 exaustao_candidata(E1_climax_baixa) topo_da_faixa", "05:15 M15 exaustao_identificada (origem do corte)", "05:30 M1 −1 quebra_estrutura_baixa"],
     "leituras": {"05:15:24 UTC": "M1 +1 · M5 +1 quebra_alta · M15 +1 descendente(rótulo)/tendência topo_da_faixa · M30 +1 lateral", "05:30:42 UTC": "M1 −1 fundo_da_faixa quebra_baixa · M5 +1 rompimento_pendente · M15 +1 topo_da_faixa"},
     "estrategias": "op 48 (Donchian M15 compra @4191.45, 04:31 UTC — recompra 2,3 acima da saída da op 15 às 04:00) fechada 05:15:27 UTC por exaustao_identificada: +12,72",
     "decisao_real": "op 48 fechada na exaustão (gestao-2: estrutural)", "gestao_real": "gestao-3 trataria a exaustão isolada como ALERTA (proteger) e sairia depois — pior neste caso (declarado)",
     "classificacao": "executou conforme o contrato (saída na exaustão); a recompra da op 48 = corte anterior (04:00) interpretado como estrutural pela gestao-2 sem direção contrária",
     "fundamento": "sessao_aberturas 15 (corte 03:45 alerta_empilhado_3 com M1/M5/M15 +1) e 48; o portão 10 não veta a op 48 (M15 topo_da_faixa = 1 alerta; M1 meio às 04:30)"},
    {"ponto": 10, "rotulo": "Rompimento da mínima do topo — confirmação de reversão — Entrada (venda)", "candle_utc": "2026-10-13 05:30", "kyiv": "13/10 08:30", "ohlc": (4194.11, 4196.75, 4189.93, 4191.19),
     "pivo": {"tipo": "quebra da mínima do candle do topo", "nivel": "fechamento 4191.19 < mínima 4194.01 do candle 05:15", "reconhecimento": "M1 quebra_estrutura_baixa (05:30:42 UTC); M5 quebra_estrutura_baixa e M15 canal 0 mista/lateral só às 06:30:38 UTC; topo 4200.53 no mapa 06:30"},
     "eventos": ["05:30 M1 quebra_baixa", "06:30 M5 quebra_baixa, M1 no_suporte, M15 lateral"],
     "leituras": {"05:30:42 UTC": "M1 −1 fundo_da_faixa quebra_baixa · M5 +1 · M15 +1 topo_da_faixa", "06:30:38 UTC": "M1 −1 no_suporte · M5 −1 quebra_baixa · M15 0 mista/lateral topo 4200.53"},
     "estrategias": "05:30–06:15 UTC: NENHUM card confirmou VENDA (fila: Donchian M15/M30 compra vencidos; segunda entrada/canal EMA20/MACD H1 compra vencidos)",
     "decisao_real": "nenhuma", "gestao_real": None,
     "classificacao": "não detectou (nenhuma estratégia de reversão/rompimento confirmou venda na quebra da mínima do topo)",
     "fundamento": "o padrão 'rompimento da mínima do candle do topo' é um evento do motor (M1 quebra_estrutura_baixa 05:30; topo_barra_rompida só no corte), não um sinal de card; o 1º card de venda só às 06:30 (MACD M15, ponto 11)"},
    {"ponto": 11, "rotulo": "Rompimento das médias — Entrada (venda)", "candle_utc": "2026-10-13 06:15", "kyiv": "13/10 09:15", "ohlc": (4191.31, 4191.32, 4184.18, 4187.34),
     "pivo": {"tipo": "fechamento abaixo das EMA20 H/L", "nivel": "06:15 UTC fechou 4187.34; 07:30 UTC 4184.67; 09:15 UTC 4183.15 (2ª seta)", "reconhecimento": "MACD M15 venda confirmado 06:30 UTC; MACD M30 venda confirmado 09:30 UTC"},
     "eventos": ["06:30 M15 lateral, M5 quebra_baixa, M1 no_suporte", "09:15 M15 compressão fundo_da_faixa, M30 compressão acelerando"],
     "leituras": {"06:30:38 UTC": "M1 −1 no_suporte · M5 −1 quebra_baixa · M15 0 mista/lateral · M30 +1 lateral", "09:15:36 UTC": "M1 −1 sacudida_fundo · M5 −1 compressão · M15 0 descendente/compressão fundo_da_faixa topo 4193.76 fundo 4183.56 · M30 0 compressão acelerando"},
     "estrategias": "06:30 e 06:45 UTC: MACD M15 venda CONFIRMADA — vetada pelo portão 5 (selo); 07:00–07:30: vencida (portão 3); 09:30 UTC: MACD M30 venda ELEGÍVEL, r01v5 'seria emitida' → recusada: maximo_de_aberturas_do_dia (6ª abertura foi a op 49 às 08:31)",
     "decisao_real": "nenhuma: selo (06:30) e teto diário (09:30)", "gestao_real": None,
     "classificacao": "detectou e recusou (selo, 06:30) · detectou, elegível e impedido pelo limite diário (09:30)",
     "fundamento": "selecao_avaliacoes bot 12 06:30/06:45 (portão 5) e 09:30 (sessao.motivo maximo_de_aberturas_do_dia); sel-5 (selo informativo) e sql/0020 (limite informativo) resolvem os dois impedimentos; a 1ª seta (06:15–06:30) também passa pelo portão 10 (venda com M1 no_suporte = 1 alerta: não veta)"},
    {"ponto": 12, "rotulo": "Exaustão do movimento — Reversão (fundo)", "candle_utc": "2026-10-13 17:45", "kyiv": "13/10 20:45", "ohlc": (4155.78, 4155.78, 4146.71, 4148.49),
     "pivo": {"tipo": "fundo", "provisorio": "M15 sacudida_fundo + M1 quebra_estrutura_alta (17:16:03 UTC = 20:16 Kyiv, fundo 4154.96); M15 no_suporte 17:45", "confirmado": "último fundo 4150.11 no mapa do M15 (17:45:51 UTC); mínima real 4146.71 (17:45) e 4144.38 (14/10 01:45 UTC) — o fundo definitivo só se confirma na madrugada"},
     "eventos": ["17:16 M15 sacudida_fundo + voltou_compressao, M1 quebra_alta topo_da_faixa", "17:45 M15 no_suporte compressão", "18:01 M15 quebra_estrutura_baixa (rompimento pendente), M5 quebra_baixa"],
     "leituras": {"17:16:03 UTC": "M1 +1 topo_da_faixa quebra_alta · M5 0 voltou_compressao · M15 −1 descendente/compressão fundo_da_faixa sacudida_fundo · M30 −1 lateral acelerando", "18:01:11 UTC": "M1 −1 fundo_da_faixa · M5 −1 quebra_baixa · M15 −1 tendência fundo_da_faixa quebra_baixa · M30 −1 compressão"},
     "estrategias": "17:00 UTC: Donchian M30 venda elegível → r01v5 168 pts > 30 fixos; 17:15 UTC: RSI M15 COMPRA confirmada (reversão no fundo) — vetada pelo portão 5 (selo); 17:30: vetada pelo portão 4 (corte); 17:45: vencida; 18:00 UTC: 5 vendas elegíveis NO FUNDO (Donchian M15/M30, S&R dia anterior M15, tripla média H1) → escolhida S&R M15 → r01v5 93 pts > 30 fixos",
     "decisao_real": "nenhuma (selo na compra; régua fixa nas vendas)", "gestao_real": None,
     "classificacao": "detectou e recusou (selo) a compra de reversão; as vendas no fundo foram detectadas e recusadas pela régua fixa (coincidência, não regra)",
     "fundamento": "sel-5: RSI M15 compra 17:15 fica elegível (reversão compatível com 'tendência com exaustão/alerta'); as vendas de 18:00 passariam na régua proporcional da 8.15 — o portão 10 (M15 fundo_da_faixa + M1 fundo_da_faixa = 2 tempos) passa a vetá-las (não vender no fundo); não é ajuste ao gráfico: é a mesma régua dos pontos 1–4 (não comprar no topo/resistência) aplicada ao lado da venda"},
]

# leituras usadas pela conferência sel-5 (portão 10) dos casos de entrada perto de resistência/suporte (ops 12, 51, 52, 53 e o fundo do ponto 12)
LEITURAS_ENTRADA = {
    "op12 22:30:27 12/10 compra": {"M1": {"dir": 1, "localizacao": "na_resistencia"}, "M5": {"dir": 1, "localizacao": "meio_da_faixa", "gatilho_exaustao": "E1/E2_baixa(persistente)"},
                                   "M15": {"dir": 1, "estrutura": "ascendente", "regime": "tendencia", "localizacao": "topo_da_faixa", "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"]},
                                   "M30": {"dir": 1, "regime": "compressao", "momentum": "enfraquecendo", "localizacao": "na_resistencia"}},
    "op51 00:15:25 14/10 compra": {"M1": {"dir": 1, "localizacao": "topo_da_faixa"}, "M5": {"dir": 1, "localizacao": "topo_da_faixa"},
                                   "M15": {"dir": 1, "estrutura": "ascendente", "regime": "tendencia", "localizacao": "na_resistencia", "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"]},
                                   "M30": {"dir": -1, "regime": "compressao", "momentum": "estavel", "localizacao": "fundo_da_faixa"}},
    "op52 01:00:24 14/10 venda": {"M1": {"dir": -1, "localizacao": "no_suporte"}, "M5": {"dir": -1, "localizacao": "no_suporte", "eventos": ["sacudida_fundo", "compressao_armada"]},
                                  "M15": {"dir": -1, "estrutura": "mista", "regime": "lateral", "localizacao": "fundo_da_faixa", "eventos": ["sacudida_fundo", "rompimento_confirmado(por_barra)"]},
                                  "M30": {"dir": -1, "regime": "compressao", "momentum": "acelerando", "localizacao": "fundo_da_faixa"}},
    "op53 03:01:08 14/10 compra": {"M1": {"dir": 1, "localizacao": "topo_da_faixa"}, "M5": {"dir": 1, "localizacao": "topo_da_faixa"},
                                   "M15": {"dir": 1, "estrutura": "mista", "regime": "lateral", "localizacao": "topo_da_faixa", "eventos": ["rompimento_pendente(por_barra)", "quebra_estrutura_alta"]},
                                   "M30": {"dir": 1, "regime": "tendencia", "momentum": "estavel", "localizacao": "na_resistencia"}},
    "ponto12 18:01:11 13/10 venda": {"M1": {"dir": -1, "localizacao": "fundo_da_faixa"}, "M5": {"dir": -1, "localizacao": "meio_da_faixa", "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_baixa"]},
                                     "M15": {"dir": -1, "estrutura": "descendente", "regime": "tendencia", "localizacao": "fundo_da_faixa", "eventos": ["rompimento_pendente(por_barra)", "quebra_estrutura_baixa"]},
                                     "M30": {"dir": -1, "regime": "compressao", "momentum": "estavel", "localizacao": "meio_da_faixa"}},
    "op48 04:30:45 13/10 compra": {"M1": {"dir": 1, "localizacao": "meio_da_faixa"}, "M5": {"dir": 1, "localizacao": "meio_da_faixa"},
                                   "M15": {"dir": 1, "estrutura": "descendente", "regime": "tendencia", "localizacao": "topo_da_faixa", "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"]},
                                   "M30": {"dir": 1, "regime": "lateral", "momentum": "estavel", "localizacao": "meio_da_faixa"}},
    "op50 22:15:21 13/10 venda BTC": {"M1": {"dir": 0, "localizacao": "meio_da_faixa"}, "M5": {"dir": 0, "localizacao": "meio_da_faixa"},
                                      "M15": {"dir": 1, "estrutura": "ascendente", "regime": "compressao", "localizacao": "topo_da_faixa", "eventos": ["sacudida_topo", "compressao_armada"]},
                                      "M30": {"dir": 1, "regime": "compressao", "momentum": "estavel", "localizacao": "meio_da_faixa"}},
}
CARDS_ENTRADA = {"op12 22:30:27 12/10 compra": ("card4_canal_ema20", 1), "op51 00:15:25 14/10 compra": ("card12_engolfo", 1), "op52 01:00:24 14/10 venda": ("card4_canal_ema20", -1),
                 "op53 03:01:08 14/10 compra": ("card4_canal_ema20", 1), "ponto12 18:01:11 13/10 venda": ("card10_donchian20", -1), "op48 04:30:45 13/10 compra": ("card10_donchian20", 1),
                 "op50 22:15:21 13/10 venda BTC": ("card8_bollinger", -1)}


def conferir_portao10(api):
    out = {}
    for k, ptf in LEITURAS_ENTRADA.items():
        card, lado = CARDS_ENTRADA[k]
        mov = api._sel_movimento_em_formacao(ptf)
        comp = api._sel_compatibilidade({"estrategia": {"card": card}, "lado_num": lado}, mov)
        al = comp.get("alertas_de_estrutura") or []
        out[k] = {"card": card, "familia": comp["familia"], "fase": mov.get("fase"), "movimento": mov.get("rotulo"), "alertas": [a["tf"] + ":" + a["valor"] for a in al],
                  "grau": comp["grau"], "portao_10": ("VETA" if (len(al) >= 2 and comp["familia"] != "reversão") else "não veta")}
    return out


def reproduzir(api):
    return {"grafico": "XAUUSD M15 12–14/10/2026 marcado pelo dono (hora do gráfico = servidor = Kyiv = UTC+3); ponto 8 ausente no gráfico — não reproduzido",
            "fontes": ["auditoria_candles M15 (carimbo do EA)", "auditoria_leituras (1º snapshot da barra: estrutura por tempo do leitor 1.7-hml)", "selecao_avaliacoes (candidatos, portões, escolha, r01v5)",
                       "sessao_aberturas 10/11/13/15/48 (gestão por barra, comandos, resultado)", "testes/reproducao_gold_1210.py (12/10 04:00–11:00)"],
            "classes": ["não detectou", "detectou e recusou", "interpretou incorretamente", "reagiu tarde", "executou conforme o contrato"],
            "pontos": PONTOS,
            "conferencia_portao_10": conferir_portao10(api),
            "resumo": {"nao_detectou": [1, 10], "detectou_e_recusou": [2, 3, 4, 5, 11, 12], "interpretou_incorretamente": [5], "reagiu_tarde": [4], "executou_conforme_contrato": [6, 7, 9],
                       "causas": {"regua_fixa_30_pts": [2, 3, 4, 12], "selo": [5, 11, 12], "limite_diario": [11], "sem_card_para_o_padrao": [1, 10], "gestao2_fino_ou_alerta_como_estrutural": [4, 7, 9], "sem_protecao_antes_do_3o_candle": [6]}},
            "limitacoes": ["o eixo do gráfico é lido pelo padrão de preço/candle, não por pixel", "leituras intrabar entre snapshots (≈ 20 s) não existem", "candles 12/10 18:00–20:45 UTC da auditoria têm OHLC repetidos (reconstrução dos snapshots) — não usados nos pontos"]}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("BT_CV_SEGREDO", "x")
    import api
    print(json.dumps(reproduzir(api), ensure_ascii=False, indent=1))
