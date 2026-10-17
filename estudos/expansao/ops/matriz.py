# -*- coding: utf-8 -*-
"""Matriz de pendências e ramos (ordem 17/10 18:57, itens 4 e 5). Fonte: sessao_aberturas.gestao (homolog), ops 69–71
(únicas posições geridas pela gestao-4/5, desde 16/10 03:03Z da 8.24 e 17/10 03:03Z da 8.27). Barra = horário de ABERTURA do M15."""
import json
E4 = "implantado; não exercitado (nenhuma avaliação caiu neste ramo)"
ramos = [  # ordem de avaliação em _gestao2_decidir (gestao-4/5)
 ("R1 B5 (fim de semana) → fecha", "gestao-2+", [], E4),
 ("R2 C6 voltou pra compressão no M15, rompimento do lado da posição → fecha", "gestao-5", [], "implantado em 17/10 03:03Z; caixa assinada lida em 3 avaliações (op 71: estado 'ativa'); retorno à caixa não ocorreu → não exercitado"),
 ("R3 corta=1 + evento ESTRUTURAL do M15 (exaustão / alerta_empilhado_3 / 3º sinal) → fecha", "gestao-4", [], E4),
 ("R4 corta=1 com evento do M15 INDETERMINADO → fecha (fail_closed)", "gestao-4", [], E4),
 ("R5 corta=1 fino + DIREÇÃO CONTRÁRIA (M1 e M5, ou canal M15) → fecha", "gestao-4", ["op 70 · barra 13:00 (fecha 13:15) · close 81.925,02"], "exercitado com efeito (fechou a posição)"),
 ("R6 B3 com continuidade PERDIDA → fecha", "gestao-4", [], E4 + " na gestao-4/5 (exercitado 4× na gestao-3, ops 56/58/61/68)"),
 ("R7 B3 além da espera máxima → fecha", "gestao-4", [], E4 + " na gestao-4/5 (exercitado 3× na gestao-3, ops 60/62/64)"),
 ("R8 corta=1 fino + continuidade PERDIDA → fecha", "gestao-4", [], E4),
 ("R9a corta=1 fino + continuidade INTACTA → proteção efetiva (stop no extremo da barra de decisão), cabe → mover_sl", "gestao-4", ["op 69 · barra 04:00 (fecha 04:15) · stop 82.176,41 → 82.022,94 (cmd 153) · tocado 04:22"], "exercitado com efeito (stop novo tocado; saída −0,43 R)"),
 ("R9b idem, NÃO cabe (preço além do extremo) → fecha", "gestao-4", [], E4),
 ("R9c idem, sem máxima/mínima ou preço → fecha", "gestao-4", [], E4),
 ("R10 B3 com continuidade intacta → alerta + trailing", "gestao-4", [], E4 + " na gestao-4/5 (7× 'manter(protegido)' na gestao-3)"),
 ("R11 alerta de enfraquecimento ISOLADO (sem corta=1 do M15) → manter; trailing só aperta", "gestao-4", ["op 69 · 03:45 (trailing)", "op 70 · 12:00, 12:45 (manter)", "op 71 · 12:15 (proteção por tempo na mesma avaliação)"], "observado na leitura (registrado; por desenho não age sozinho)"),
 ("R12 sem alerta → manter / trailing estrutural", "gestao-2+", ["op 70 · 12:15, 12:30 (manter)", "op 71 · 11:45, 12:00 (trailing 81.654,99 → 81.603,67 → 81.603,41)"], "exercitado; trailing de op 71 não foi o stop que encerrou"),
 ("T1 proteção por tempo, cabe → mover_sl ao nível protegido", "gestao-3", ["op 71 · 12:15 (fecha 12:30) · 81.603,41 → 81.470,04 (cmd 159) · tocado 12:34"], "exercitado com efeito (saída +0,03 R; contra o stop anterior −0,39 R; contra a base sem gestão −1,25 R)"),
 ("T2 proteção por tempo, NÃO cabe → impedimento registrado; 4º candle explícito", "gestao-3", ["op 70 · 12:30 e 12:45 (folga −37.101 e −58.816 pts)"], "exercitado sem efeito (impedimento correto: preço abaixo da entrada)"),
 ("T3 stop vigente já protetor, origem EXTERNA → não conta como aplicada", "gestao-3", [], E4),
 ("J1 janela M10 (10/15 min) → alerta registrado", "gestao-4", ["op 70 · janela da barra 12:00"], "observado na leitura (registro; sem ação)"),
]
pend = [
 ("C5", "sel-7: portão 11 aguarda a Lei de Confirmação com rompimento PENDENTE da caixa M15", "implantado (17/10 03:03Z)", "observado na leitura: aguardou em 6 barras de 17/10", "sem efeito isolado: em todas as 6 barras outros portões já estavam fechados — não mudou nenhuma entrada", "não exercitado com efeito"),
 ("C6", "gestao-5: voltou pra compressão fecha (R2)", "implantado", "caixa assinada lida em 3 avaliações (op 71)", "retorno não ocorreu", "não exercitado"),
 ("C7", "sel-7: reversão estrutural no mesmo sentido da quebra M15 deixa de ser zerada", "implantado", "grau 2 do card 1 lido 6×", "nenhum candidato elegível resultou", "não exercitado com efeito"),
 ("D1", "gestao-4: 2º sinal fino — proteção efetiva × corte por direção contrária/continuidade", "implantado (16/10 03:03Z)", "ramos R9a e R5 exercitados; R11/R12 observados", "R9a op 69 e R5 op 70 com efeito", "PARCIAL: R3, R4, R8, R9b, R9c, R6/R7/R10 (na gestao-4/5) não exercitados — a regra inteira NÃO está validada"),
 ("D2", "proposta separada (não implantada)", "não implantado", "-", "-", "proposta; fora desta etapa"),
 ("D3", "alerta isolado continua alerta (R11)", "implantado", "registrado em op 69/70/71", "por desenho não age; em op 70 os alertas precederam o corte de 13:00", "observado na leitura (só alerta)"),
]
json.dump({"fonte": __doc__, "ramos_gestao4_5": [dict(ramo=a, desde=b, casos=c, situacao=d) for a, b, c, d in ramos],
           "pendencias": [dict(item=a, regra=b, implantado=c, observado_na_leitura=d, efeito=e, situacao=f) for a, b, c, d, e, f in pend]},
          open("matriz_pendencias.json", "w"), ensure_ascii=False, indent=1)
print("ok", len(ramos), len(pend))
