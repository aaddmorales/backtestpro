# -*- coding: utf-8 -*-
"""C27R47 — reprodução cronológica do BTC (bot 13, BTCUSD, conta DEMO 52648209) de 13/10/2026, 00:40–02:15 UTC (03:40–05:15 hora do
servidor/Kyiv): formação do FUNDO (barras M15 00:30 e 00:45 UTC = 15 e 16 do dia do servidor) e ROMPIMENTO da máxima da barra 16 pela
17 (01:00 UTC). Caso de reprodução pedido na ordem do dono de 13/10 06:25 Kyiv (item 2).

Só usa o que estava GRAVADO em cada instante (auditoria_leituras: estrutura por timeframe e eventos M1/M5/M15 de cada snapshot;
selecao_avaliacoes: candidatos com portões e valores de cada barra). Nenhum candle posterior entra na decisão de cada instante.
Compara ANTES = sel-4 (portão 5 — selo — veta) com DEPOIS = sel-5 (selo informativo; compatibilidade com o movimento ordena).
`python -m testes.reproducao_btc_1310` imprime o JSON; test_31 valida os pontos-chave."""
import json

PT = 0.01
# ---- leituras (auditoria_leituras, bot 13): instante UTC, barra M15 em formação, preço, M1 (dir, estrutura, eventos), M5 (dir, estrutura,
#      último fundo, último topo, eventos), M15 (dir, estrutura, regime, eventos)  — só as mudanças de estado
LEITURAS = [
    ("00:40:09", "00:30", 81362.52, (0, "mista", ["compressao_armada"]), (-1, "descendente", 81178.47, 81848.60, ["rompimento_pendente(por_barra)"]), (-1, "ascendente", "tendencia", ["rompimento_confirmado(por_barra)", "quebra_estrutura_baixa"])),
    ("00:45:46", "00:45", 81187.38, (-1, "mista", ["compressao_armada"]), (-1, "descendente", 81138.49, 81848.60, ["compressao_armada"]), (-1, "ascendente", "tendencia", ["rompimento_confirmado(por_barra)", "exaustao_candidata(E3_gradual_alta)"])),
    ("01:00:51", "01:00", 81318.07, (1, "ascendente", ["compressao_armada"]), (-1, "descendente", 81138.49, 81533.26, ["compressao_armada"]), (-1, "ascendente", "tendencia", ["rompimento_confirmado(por_barra)", "quebra_estrutura_baixa"])),
    ("01:15:43", "01:15", 81768.17, (1, "ascendente", ["compressao_armada", "quebra_estrutura_alta"]), (1, "descendente", 80917.83, 81533.26, ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"]), (-1, "ascendente", "tendencia", ["rompimento_confirmado(por_barra)", "quebra_estrutura_baixa"])),
    ("01:30:40", "01:30", 81997.02, (1, "mista", ["compressao_armada"]), (1, "mista", 80917.83, 82119.59, ["rompimento_confirmado(por_barra)"]), (0, "mista", "lateral", ["rompimento_confirmado(por_barra)"])),
    ("01:45:26", "01:45", 82274.97, (1, "mista", ["compressao_armada", "quebra_estrutura_alta"]), (1, "mista", 80917.83, 82119.59, ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"]), (1, "mista", "lateral", ["rompimento_confirmado(por_barra)"])),
    ("02:00:44", "02:00", 82336.82, (1, "mista", ["compressao_armada"]), (1, "mista", 80917.83, 82119.59, ["compressao_armada", "quebra_estrutura_alta"]), (1, "mista", "lateral", ["rompimento_confirmado(por_barra)"])),
]

# ---- candidatos de COMPRA gravados por barra (selecao_avaliacoes, bot 13): barra, tf, card, confirmado_utc, vence_utc, entrada, stop,
#      portões 1..9 da sel-4 ("T"/"F"; "-" = não avaliado), detalhe do portão 8, preço do snapshot
CANDIDATOS_COMPRA = [
    ("01:30", "M30", "card7_rsi",        "01:30", "02:00", 81971.19, 80822.095331, "TTTTFTTTT", "preço a 2583 pts; limite 11491", 81997.02),
    ("01:30", "M30", "card8_bollinger",  "01:30", "02:00", 81971.19, 80822.095331, "TTTTFTTTT", "preço a 2583 pts; limite 11491", 81997.02),
    ("01:45", "M15", "card4_canal_ema20","01:45", "02:15", 82275.41, 80820.952022, "TTTTFTTTT", "preço a 44 pts; limite 14545", 82274.97),
    ("01:45", "M15", "card9_macd",       "01:45", "02:15", 82275.41, 80820.952022, "TTTTFTTTT", "preço a 44 pts; limite 14545", 82274.97),
    ("01:45", "M30", "card7_rsi",        "01:30", "02:00", 81971.19, 80822.095331, "TTTTFTTFT", "preço a 30378 pts; limite 11491", 82274.97),
    ("01:45", "M30", "card8_bollinger",  "01:30", "02:00", 81971.19, 80822.095331, "TTTTFTTFT", "preço a 30378 pts; limite 11491", 82274.97),
    ("02:00", "H1",  "card7_rsi",        "02:00", "02:30", 82343.84, 80823.481378, "TTTTTTTTT", "preço a 702 pts; limite 15204", 82336.82),   # op 14 REAL (sel-4 aprovou: selo PF 1,054)
    ("02:00", "H1",  "card8_bollinger",  "02:00", "02:30", 82343.84, 80823.481378, "TTTTFTTTT", "preço a 702 pts; limite 15204", 82336.82),
    ("02:00", "M15", "card4_canal_ema20","01:45", "02:15", 82275.41, 80820.952022, "TTTTFTTTT", "preço a 6141 pts; limite 14545", 82336.82),
    ("02:00", "M15", "card9_macd",       "01:45", "02:15", 82275.41, 80820.952022, "TTTTFTTTT", "preço a 6141 pts; limite 14545", 82336.82),
    ("02:00", "M30", "card7_rsi",        "01:30", "02:00", 81971.19, 80822.095331, "TTFTFTTFT", "vencido; preço a 36563 pts", 82336.82),
    ("02:00", "M30", "card8_bollinger",  "01:30", "02:00", 81971.19, 80822.095331, "TTFTFTTFT", "vencido; preço a 36563 pts", 82336.82),
]
# barras 00:30–01:15: NENHUM candidato de compra gravado (só vendas vencidas / vetadas pelo portão 4 ou 5) — ausência registrada

OP14 = {"abertura_id": 14, "uid": "card7_rsi|H1|2026-10-13 04:00:00|1", "decisao_utc": "02:00:45", "execucao_utc": "02:01:01", "preco_entrada": 82380.65, "lote": 0.06,
        "stop_inicial": 80823.48, "ticket": 2003877706}


def por_tf_de(leitura):
    _ts, _b, _p, m1, m5, m15 = leitura
    return {"M1": {"dir": m1[0], "estrutura": m1[1], "eventos": m1[2]},
            "M5": {"dir": m5[0], "estrutura": m5[1], "ultimo_fundo": m5[2], "ultimo_topo": m5[3], "eventos": m5[4]},
            "M15": {"dir": m15[0], "estrutura": m15[1], "regime": m15[2], "eventos": m15[3], "localizacao": ""}}


def reproduzir(api):
    """Instante a instante: o que o leitor via (M1/M5/M15), o movimento em formação pela sel-5, os candidatos gravados e a elegibilidade
    ANTES (sel-4: selo veta) × DEPOIS (sel-5: selo informa; demais portões iguais). Devolve o JSON da comparação."""
    linhas = []
    for L in LEITURAS:
        ts, barra, preco, m1, m5, m15 = L
        mov = api._sel_movimento_em_formacao(por_tf_de(L))
        linhas.append({"instante_utc": ts, "barra_m15_em_formacao_utc": barra, "preco": preco,
                       "M1": {"dir": m1[0], "eventos": m1[2]}, "M5": {"dir": m5[0], "ultimo_fundo": m5[2], "ultimo_topo": m5[3], "eventos": m5[4]},
                       "M15": {"dir": m15[0], "estrutura": m15[1], "regime": m15[2], "eventos": m15[3]},
                       "movimento_sel5": mov["rotulo"], "compatibilidade_por_familia": mov["compatibilidade_por_familia"]})
    cands = []
    primeiro_antes = primeiro_depois = None
    for (barra, tf, card, conf, vence, ent, stop, oks, det8, preco) in CANDIDATOS_COMPRA:
        oks_l = list(oks)
        antes = all(o == "T" for o in oks_l)
        depois = all(o == "T" for i, o in enumerate(oks_l) if i != 4)        # portão 5 (índice 4) informa
        leit = next(x for x in LEITURAS if x[1] == barra)
        mov = api._sel_movimento_em_formacao(por_tf_de(leit))
        comp = api._sel_compatibilidade({"estrategia": {"card": card}, "lado_num": 1}, mov)
        c = {"barra_utc": barra, "timeframe": tf, "card": card, "familia": comp["familia"], "compatibilidade": comp["rotulo"], "grau": comp["grau"],
             "confirmado_utc": conf, "vence_utc": vence, "entrada_ref": ent, "stop": stop, "risco_pts": round((ent - stop) / PT), "preco_no_snapshot": preco,
             "portoes_sel4": oks, "portao_8": det8, "elegivel_antes_sel4": antes, "elegivel_depois_sel5": depois,
             "motivo_antes": ("elegível" if antes else "portão " + str(oks_l.index("F") + 1) + (" (selo)" if oks_l.index("F") == 4 else "")),
             "motivo_depois": ("elegível" if depois else "portão " + str(next(i for i, o in enumerate(oks_l) if o == "F" and i != 4) + 1))}
        cands.append(c)
        if antes and primeiro_antes is None:
            primeiro_antes = c
        if depois and primeiro_depois is None:
            primeiro_depois = c
    eleg_1330 = [c for c in cands if c["barra_utc"] == "01:30" and c["elegivel_depois_sel5"]]
    esc_1330 = sorted(eleg_1330, key=lambda c: (-c["grau"], c["card"]))[0] if eleg_1330 else None
    return {"caso": "BTC 13/10/2026 — fundo nas barras 15–16 (00:30/00:45 UTC) e rompimento da máxima da 16 pela 17 (01:00 UTC)",
            "leituras_por_instante": linhas,
            "reconhecimento_do_padrao": {
                "M1_M5_identificaram": "01:15:43 UTC (barra 01:15 em formação): M1 e M5 com quebra_estrutura_alta e rompimento confirmado por barra; M5 último fundo 80917,83 (o fundo das barras 15–16); M15 ainda rotulado 'ascendente/canal −1' (rótulo defasado)",
                "primeira_estrategia_confirmada": "01:30 UTC: card7_rsi e card8_bollinger em M30 (família reversão), confirmadas no fechamento do M30 01:00–01:30 — a barra 17 é a 1ª metade desse M30",
                "depois": "01:45 UTC: card4_canal_ema20 e card9_macd em M15 (continuação) confirmadas; 02:00 UTC: card7_rsi e card8_bollinger em H1",
                "nenhuma_estrategia_M15_confirmou_na_barra_17": "a barra 01:00 fechou às 01:15 sem candidato M15 de compra confirmado (os cards M15 só confirmaram às 01:45); por isso a sel-5 não anteciparia para 01:15 — não há sinal a forçar"},
            "candidatos_compra": cands,
            "primeiro_elegivel_antes_sel4": ({k: primeiro_antes[k] for k in ("barra_utc", "timeframe", "card", "preco_no_snapshot", "confirmado_utc")} if primeiro_antes else None),
            "primeiro_elegivel_depois_sel5": ({k: primeiro_depois[k] for k in ("barra_utc", "timeframe", "card", "preco_no_snapshot", "confirmado_utc")} if primeiro_depois else None),
            "escolha_sel5_em_01_30": (esc_1330 and {k: esc_1330[k] for k in ("card", "timeframe", "familia", "compatibilidade", "preco_no_snapshot")}),
            "op14_real": OP14,
            "diferenca": {"antecipacao_min": 30, "preco_sel5_01_30": 81997.02, "preco_real_02_01": OP14["preco_entrada"],
                          "pontos_a_favor": round((OP14["preco_entrada"] - 81997.02) / PT), "usd_no_lote_da_op14": round((OP14["preco_entrada"] - 81997.02) * OP14["lote"], 2),
                          "nota": "entrada hipotética ao preço do snapshot de 01:30:40 (ask ≈ +500 pts de spread): aproximação declarada; stop 80822,10 = o mesmo pivô do M15 (risco ≈ 11,5 mil pts)"},
            "limitacoes": ["sem candles M1/M5 intrabarra gravados: o instante da detecção é o do snapshot (≈ 20 s)", "a reavaliação dentro da barra (sel-5) não muda este caso: as confirmações chegaram no 1º snapshot de cada barra",
                           "não força sinal: as barras 00:30–01:15 não tiveram candidato de compra confirmado em nenhum card"]}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("BT_CV_SEGREDO", "x")
    import api
    print(json.dumps(reproduzir(api), ensure_ascii=False, indent=1))
