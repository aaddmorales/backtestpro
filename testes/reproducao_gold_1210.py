# -*- coding: utf-8 -*-
"""C27R44 — reprodução cronológica do Gold (bot 12, XAUUSD, conta DEMO 52648209) de 12/10/2026, 04:00–11:00 UTC (07:00–14:00 Kyiv).

Só usa o que estava GRAVADO em cada instante (selecao_avaliacoes: candidatos com portões e valores; auditoria_leituras: estrutura por
timeframe e gestão assinada do mesmo snapshot). Nenhum candle posterior entra na decisão de cada barra. Compara:
  ANTES  = sel-3 (portão 4 veta qualquer corte; portão 8 = 30 pts fixos) + gestao-1 (B3 ou corte → fecha)
  DEPOIS = sel-4 (portão 4 só veta corte ESTRUTURAL, indeterminado = fail_closed; portão 8 = max(30, 10% do risco)) + gestao-2 (continuidade)
Os preços de saída hipotéticos são o preço do snapshot da avaliação (não há candle intrabarra aqui): são aproximações declaradas.
`python -m testes.reproducao_gold_1210` imprime o JSON da comparação; test_26 valida os pontos-chave."""
import json

PT = 0.01
# ---- candidatos de VENDA confirmados que o sel-3 recusou SÓ no portão 8 (ou no 4 com evento fino), por barra M15 UTC
# (b, tf, card, entrada, risco_pts, oks sel-3 [portões 1..9], desvio_pts, m15_evento_do_corte ou None, preco_ea)
CANDIDATOS_VENDA = [
    ("04:00", "M30", "c9_macd",            4203.14, 1304, "TTTTTTTFT",  39, None, 4203.53),
    ("04:15", "M30", "c9_macd",            4203.14, 1304, "TTTTTTTFT", 358, None, 4199.56),
    ("05:00", "M15", "c2_rompimento_caixa",4197.97, 1214, "TTTTTTTFT", 265, None, 4195.32),
    ("05:00", "M30", "c4_canal_ema20",     4194.78, 1531, "TTTTTTTFT",  54, None, 4195.32),
    ("05:15", "M30", "c4_canal_ema20",     4194.78, 1531, "TTTTTTTFT", 826, None, 4186.52),
    ("05:30", "M15", "c2_rompimento_caixa",4184.63, 2549, "TTTTTTTFT",  44, None, 4184.19),
    ("05:30", "M30", "c1_reversao_extremo",4184.63, 2549, "TTTTTTTFT",  44, None, 4184.19),
    ("05:45", "M15", "c2_rompimento_caixa",4184.63, 2549, "TTTFTTTFT", 220, "",   4186.83),   # origem truncada: "-> M15:" sem evento
    ("05:45", "M30", "c1_reversao_extremo",4184.63, 2549, "TTTFTTTFT", 220, "",   4186.83),
    ("06:15", "M15", "c12_engolfo",        4185.73, 2450, "TTTTTTTFT", 135, None, 4184.38),
    ("06:30", "M15", "c12_engolfo",        4185.73, 2450, "TTTTTTTFT", 130, None, 4184.43),
    ("06:30", "M30", "c12_engolfo",        4183.34, 2685, "TTTTTTTFT", 109, None, 4184.43),
    ("06:45", "M30", "c12_engolfo",        4183.34, 2685, "TTTTTTTFT", 153, None, 4184.87),
    ("07:00", "M15", "c12_engolfo",        4185.73, 2450, "TTFFTTTFT",  55, "alerta_empilhado_3", 4186.28),   # vencido (3) e corte estrutural: segue recusado
    ("07:00", "M30", "c1_reversao_extremo",4184.63, 2549, "TTFFTTTFT", 165, "alerta_empilhado_3", 4186.28),
    ("08:00", "H1",  "c4_canal_ema20",     4180.65, 1376, "TTTTTTTFT",  37, None, 4180.28),
    ("08:15", "H1",  "c4_canal_ema20",     4180.65, 1376, "TTTTTTTFT", 351, None, 4177.14),
    ("08:30", "M15", "c10_donchian20",     4176.76, 1299, "TTTTTTTFT",  57, None, 4176.19),
    ("08:45", "M15", "c10_donchian20",     4176.76, 1299, "TTTTTTTTT",  19, None, 4176.57),   # op 10 REAL (sel-3 aprovou)
    ("09:15", "M15", "c10_donchian20",     4173.96, 1573, "TTTFTTTFT", 438, "fundo_barra_rompido", 4178.34),
]

# ---- gestão assinada da VENDA por barra fechada (gb = início da barra M15 fechada; avaliada ~15 min depois)
# (gb, preco_no_snapshot, d15, estrutura15, regime15, ultimo_topo15, d30, fechamento, B3, corte, m15_evento, b3_atr, stop_estrutural)
GESTAO_VENDA = [
    ("04:00", 4200.63, -1, "mista", "lateral",    4214.23,  0, 4198.87, 0, 0, None, None, 4216.18),
    ("04:15", 4198.15,  0, "mista", "lateral",    4208.27,  0, 4200.62, 0, 0, None, None, 4210.16),
    ("04:30", 4194.91, -1, "mista", "lateral",    4208.27,  0, 4197.97, 0, 0, None, None, 4210.11),
    ("04:45", 4187.26, -1, "mista", "compressao", 4208.27, -1, 4194.78, 0, 0, None, None, 4210.09),
    ("05:00", 4184.64, -1, "mista", "lateral",    4208.27, -1, 4187.64, 0, 0, None, None, 4210.14),
    ("05:15", 4187.03, -1, "mista", "lateral",    4208.27, -1, 4184.63, 0, 0, None, None, 4210.12),
    ("05:30", 4191.39, -1, "mista", "lateral",    4208.27, -1, 4187.45, 0, 0, None, None, 4210.17),
    ("05:45", 4186.31, -1, "mista", "lateral",    4208.27, -1, 4191.07, 0, 1, "alerta_empilhado_", None, 4210.16),   # truncado → prefixo → estrutural
    ("06:00", 4183.51, -1, "descendente", "tendencia", 4208.27, -1, 4185.73, 0, 1, "fundo_barra_rompido", None, 4210.23),
    ("06:15", 4184.98, -1, "descendente", "tendencia", 4208.27, -1, 4183.34, 0, 0, None, None, 4210.19),
    ("06:30", 4185.41, -1, "descendente", "compressao", 4192.73, -1, 4184.67, 1, 0, None, -0.33, 4194.58),
    ("06:45", 4185.86, -1, "mista", "compressao", 4192.73, -1, 4185.94, 1, 0, None, -1.14, 4194.52),
    ("07:00", 4184.90, -1, "mista", "compressao", 4192.73, -1, 4185.72, 1, 1, "fundo_barra_rompido", -1.01, 4194.45),
    ("07:15", 4183.44, -1, "mista", "compressao", 4192.73, -1, 4185.33, 0, 0, None, None, 4194.40),
    ("07:30", 4180.76, -1, "mista", "compressao", 4192.73, -1, 4182.05, 0, 0, None, None, 4194.42),
    ("07:45", 4177.06, -1, "mista", "lateral",    4192.73, -1, 4180.65, 1, 0, None, -0.21, 4194.41),
    ("08:00", 4176.74, -1, "mista", "lateral",    4188.15, -1, 4177.16, 0, 0, None, None, 4189.81),
    ("08:15", 4177.83, -1, "mista", "lateral",    4188.15, -1, 4176.76, 0, 0, None, None, 4189.75),
    ("08:30", 4173.96, -1, "mista", "lateral",    4188.15, -1, 4176.46, 0, 0, None, None, 4189.72),
    ("08:45", 4178.27, -1, "mista", "compressao", 4188.15, -1, 4173.96, 0, 0, None, None, 4189.69),   # op 10: barra da entrada
    ("09:00", 4175.85, -1, "mista", "compressao", 4188.15, -1, 4178.49, 0, 0, None, None, 4189.68),
    ("09:15", 4170.90, -1, "descendente", "compressao", 4188.15, -1, 4177.18, 1, 1, "fundo_barra_", -0.45, 4189.66),   # op 10: gestao-1 FECHOU aqui (09:30 UTC)
    ("09:30", 4172.32, -1, "descendente", "compressao", 4188.15, -1, 4170.68, 0, 0, None, None, 4189.70),
    ("09:45", 4175.02, -1, "descendente", "compressao", 4178.53, -1, 4173.25, 0, 0, None, None, 4180.07),
    ("10:00", 4179.36, -1, "descendente", "compressao", 4178.53, -1, 4174.95, 1, 0, None, -0.74, 4180.02),
    ("10:15", 4178.94,  0, "descendente", "lateral",    4178.53, -1, 4179.25, 1, 1, "fundo_barra_rompido", -1.69, 4180.03),
    ("10:30", 4177.45,  0, "descendente", "lateral",    4178.53, -1, 4178.88, 1, 1, "rompeu_ultimo_topo", -2.46, 4179.97),
    ("10:45", 4171.47, -1, "descendente", "compressao", 4178.53, -1, 4177.25, 0, 0, None, None, 4179.93),
]

# ---- op 8 (COMPRA real, 02:15:55 UTC @4213.47, stop inicial 4197.81): gestão assinada do lado compra
GESTAO_OP8_COMPRA = [
    ("02:15", 4208.24, 1, "ascendente", "compressao", 4217.23, 4200.07, 1, 4211.36, 0, 0, None, None, 4197.90),
    ("02:30", 4209.17, 1, "mista",      "compressao", 4214.23, 4200.07, 1, 4208.89, 0, 0, None, None, 4197.89),
    ("02:45", 4205.55, 0, "mista",      "compressao", 4214.23, 4200.07, 1, 4204.59, 0, 0, None, None, 4197.92),
    ("03:00", 4204.14, 0, "mista",      "compressao", 4214.23, 4200.07, 1, 4203.79, 1, 0, None, -0.84, 4197.99),   # gestao-1 FECHOU (B3)
]


def _origem(ev):
    if ev is None:
        return []
    return ["M1:fundo_barra_rompido M5:fundo_barra_rompido -> M15:" + ev]


def selecao(api):
    """Portões 4 e 8 por candidato: ANTES (sel-3) × DEPOIS (sel-4). Os demais portões são lidos do registro (oks)."""
    linhas = []
    for b, tf, card, ent, risco, oks, desv, ev, px in CANDIDATOS_VENDA:
        outros_ok = all(oks[i] == "T" for i in (0, 1, 2, 4, 5, 6, 8))            # 1,2,3,5,6,7,9 como gravados
        antes = outros_ok and oks[3] == "T" and desv <= api._SEL_DESVIO_MAX["XAUUSD"]
        cls = api._cont_eventos_corte(_origem(ev)) if ev is not None else None
        g4 = (ev is None) or (cls is not None and cls["fino"])                    # sel-4: estrutural/indeterminado veta; fino informa
        lim = max(api._SEL_DESVIO_MAX["XAUUSD"], risco * api._SEL_DESVIO_FRAC_RISCO)
        g8 = desv <= lim
        depois = outros_ok and g4 and g8
        linhas.append({"barra_utc": b, "tf": tf, "card": card, "entrada": ent, "preco": px, "risco_pts": risco, "desvio_pts": desv,
                       "portao4_sel3": oks[3] == "T", "portao4_sel4": g4, "corte_classe": (cls or {}).get("classe"),
                       "portao8_limite_sel3": api._SEL_DESVIO_MAX["XAUUSD"], "portao8_limite_sel4": round(lim, 1), "portao8_sel4": g8,
                       "outros_portoes_ok": outros_ok, "elegivel_antes": antes, "elegivel_depois": depois})
    return linhas


def _por_tf(d15, e15, r15, topo, d30, fundo=None):
    return {"M15": {"dir": d15, "estrutura": e15, "regime": r15, "ultimo_topo": topo, "ultimo_fundo": fundo}, "M30": {"dir": d30}, "H1": {"dir": -1}}


def gestao_venda(api, entrada_gb, preco_entrada, stop_inicial, lote=0.07):
    """Replay de uma venda aberta na barra `entrada_gb` (preço `preco_entrada`) pela gestao-2, barra a barra, até fechar."""
    idx = [i for i, r in enumerate(GESTAO_VENDA) if r[0] == entrada_gb][0]
    stop, passos, gest = stop_inicial, [], []
    for n, r in enumerate(GESTAO_VENDA[idx:]):
        gb, px, d15, e15, r15, topo, d30, fech, b3, cv, ev, atr, sev = r
        L = {"B3": b3, "corte_do_ciclo": cv, "corte_origem": _origem(ev), "stop_estrutural": sev, "stop_do_lado_certo": 1}
        acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": fech}, ({"contrato": "corte-ciclo-2"} if cv else None),
                                                           _por_tf(d15, e15, r15, topo, d30), n, gest)
        antes = "close" if (b3 and n >= 2) or cv else ("mover_sl" if sev < stop - PT else "manter")
        protegido = motivo if acao == "proteger" else None
        if acao == "proteger":
            acao = None
        if acao is None and sev < stop - PT:
            acao, stop = "mover_sl", round(sev, 2)
        reg = {"barra": gb, "barras_de_posicao": n, "acao": acao or ("manter(protegido)" if protegido else "manter"), "protegido_por": protegido,
               "motivo": motivo if acao == "close" else None, "leitura": {"B3": b3}}
        gest.append(reg)
        passos.append({"barra_utc": gb, "barras": n, "preco": px, "B3": b3, "B3_atr": atr, "corte": cv, "corte_classe": cls["classe"] if cv else None,
                       "continuidade": cont["situacao"], "motivos": cont["motivos"], "gestao1": antes, "gestao2": reg["acao"], "explicacao": exp, "stop": stop})
        if acao == "close":
            return {"entrada": entrada_gb, "preco_entrada": preco_entrada, "saida_barra_utc": gb, "preco_saida_aprox": px,
                    "resultado_aprox_usd": round((preco_entrada - px) * lote * 100, 2), "stop_final": stop, "passos": passos,
                    "nota": "preço de saída = preço do snapshot da avaliação (aproximação); o stop na corretora pode ter sido atingido antes (sem intrabarra aqui)"}
    return {"entrada": entrada_gb, "preco_entrada": preco_entrada, "aberta_ao_fim": True, "stop_final": stop, "passos": passos}


def gestao_op8(api):
    passos = []
    for n, r in enumerate(GESTAO_OP8_COMPRA):
        gb, px, d15, e15, r15, topo, fundo, d30, fech, b3, cv, ev, atr, sev = r
        L = {"B3": b3, "corte_do_ciclo": cv, "corte_origem": _origem(ev), "stop_estrutural": sev}
        acao, motivo, cont, cls, exp = api._gestao2_decidir(1, L, {"B5": 0, "fechamento": fech}, None, _por_tf(d15, e15, r15, topo, 1, fundo), n + 1, [])
        passos.append({"barra_utc": gb, "barras": n + 1, "preco": px, "B3": b3, "B3_atr": atr, "continuidade": cont["situacao"], "motivos": cont["motivos"],
                       "gestao1": "close" if (b3 and n + 1 >= 2) else "manter/trailing", "gestao2": acao or "manter/trailing", "explicacao": exp})
    return passos


def reproduzir(api):
    sel = selecao(api)
    primeira_antes = next((x for x in sel if x["elegivel_antes"]), None)
    primeira_depois = next((x for x in sel if x["elegivel_depois"]), None)
    return {
        "janela_utc": "2026-10-12 04:00–11:00 (Kyiv 07:00–14:00)", "regras": {"antes": "sel-3 + gestao-1", "depois": "sel-4 + gestao-2"},
        "selecao": sel,
        "primeira_venda_elegivel": {"antes": primeira_antes and f"{primeira_antes['barra_utc']} {primeira_antes['tf']} {primeira_antes['card']} @{primeira_antes['entrada']}",
                                    "depois": primeira_depois and f"{primeira_depois['barra_utc']} {primeira_depois['tf']} {primeira_depois['card']} @{primeira_depois['entrada']}"},
        "op10_real_gestao2": gestao_venda(api, "08:45", 4176.17, 4192.87),
        "venda_hipotetica_0400_gestao2": gestao_venda(api, "04:00", 4203.53, 4216.18),
        "venda_hipotetica_0615_gestao2": gestao_venda(api, "06:15", 4184.38, 4210.23),
        "op8_real_gestao2": gestao_op8(api),
    }


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import api
    print(json.dumps(reproduzir(api), ensure_ascii=False, indent=1))
