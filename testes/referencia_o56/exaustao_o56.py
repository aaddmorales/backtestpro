"""exaustao-1 (ORDEM 056-A) — saída por exaustão (afastamento das médias → perda de força → reação → superação da máxima da barra de reação).
Referência Python. Especificação congelada: O56_exaustao_especificacao_congelada.txt. Estende a InstanciaC (caixa + ROMPZ + COMPZ, gestão R1)."""
import os, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(AQUI, "..", "referencia_o55"), os.path.join(AQUI, "..", "referencia_o53"), os.path.join(AQUI, "..", "referencia_o51")]
import compz_o55 as CZ  # noqa: E402
import rompz_o53c as RZ  # noqa: E402
import ao_vivo_o53 as R1  # noqa: E402
import romp_m15 as RM  # noqa: E402

VERSAO = "exaustao-1 (ORDEM 056-A)"
K_AF, JANELA_AF, CLV_FRACO, CLV_REACAO = 1.5, 3, 0.5, 0.6
TICK = RZ.TICK; tk = RZ.tk


def clv(s, h, l, c):
    a = h - l
    if a <= 0: return 0.0
    return (c - l) / a if s < 0 else (h - c) / a


def avaliar(s, O, H, L, C, EH, EL, ATR, b):
    """estado de exaustão na barra b (fechada) para uma posição de lado s. Só usa barras <= b."""
    if b < 3 or not np.isfinite(ATR[b]) or ATR[b] <= 0: return None
    dist = [((EL[i] - C[i]) if s < 0 else (C[i] - EH[i])) / ATR[i] for i in range(b - JANELA_AF + 1, b + 1)]
    av = lambda i: (L[i - 1] - L[i]) if s < 0 else (H[i] - H[i - 1])
    contexto = max(dist) >= K_AF - 1e-12
    desac = av(b) < av(b - 1)
    k1, k0 = clv(s, H[b - 1], L[b - 1], C[b - 1]), clv(s, H[b], L[b], C[b])
    longe = k1 >= CLV_FRACO and k0 >= CLV_FRACO
    alerta = contexto and desac and longe
    if s < 0: reac = C[b] > O[b] and C[b] > C[b - 1] and L[b] > L[b - 1] and k0 >= CLV_REACAO
    else: reac = C[b] < O[b] and C[b] < C[b - 1] and H[b] < H[b - 1] and k0 >= CLV_REACAO
    return {"dist_atr": round(float(dist[-1]), 3), "dist_max": round(float(max(dist)), 3), "contexto": bool(contexto), "av": round(float(av(b)), 2),
            "av_ant": round(float(av(b - 1)), 2), "desaceleracao": bool(desac), "clv_ant": round(k1, 3), "clv": round(k0, 3), "longe_do_extremo": bool(longe),
            "alerta": bool(alerta), "reacao": bool(alerta and reac)}


class InstanciaE(CZ.InstanciaC):
    def __init__(self, at, tf, exaustao=True, **kw):
        super().__init__(at, tf, **kw)
        self.exaustao = exaustao; self.exa = {"pos": None, "sombra": None}; self.m1_atual = None; self.trilha_exa = []

    def fecha_barra(self, rates, rates_h1=None):
        b = len(rates) - 1; t_ab = int(pd.Timestamp(rates.t.iloc[b]).value // 10**6); fim = t_ab + self.dur_ms
        if self.ult_barra_ms is not None and t_ab <= self.ult_barra_ms: return
        # gatilho de exaustão da barra que terminou: expira
        for nome in ("pos", "sombra"):
            g = self.exa[nome]
            if g is not None and g["fim_ms"] <= fim:
                self.ev("exaustao_expirada", fim, id=g["id"], gatilho=g["gat"]); self.trilha_exa.append({**g, "resultado": "expirou"}); self.exa[nome] = None
        super().fecha_barra(rates, rates_h1)
        if not self.exaustao: return
        O, H, L, C = (rates[k].values.astype(float) for k in "ohlc"); ATR = RM.atr_wilder(rates.h, rates.l, rates.c)
        EH = pd.Series(H).ewm(span=20, adjust=False).mean().values; EL = pd.Series(L).ewm(span=20, adjust=False).mean().values
        for nome in ("pos", "sombra"):
            p = getattr(self, nome)
            if p is None or p["saida_pendente"] or t_ab <= p["barra_ent_ms"] or self.exa[nome] is not None: continue
            s = p["lado"]; e = avaliar(s, O, H, L, C, EH, EL, ATR, b)
            if e is None: continue
            reg = {"id": p["id"], "barra_ms": t_ab, "c": float(C[b]), "ema": float(EL[b] if s < 0 else EH[b]), "atr": float(ATR[b]), **e}
            if e["contexto"] and not e["alerta"]: self.ev("exaustao_contexto", fim, **reg)
            if e["alerta"] and not e["reacao"]: self.ev("exaustao_alerta", fim, **reg)
            if e["reacao"]:
                ext = H[b] if s < 0 else L[b]; can = L[b] if s < 0 else H[b]
                g = {**reg, "gat_t": tk(ext) - s, "gat": round((tk(ext) - s) * TICK, 2), "can_t": tk(can) + s, "cancel": round((tk(can) + s) * TICK, 2),
                     "ini_ms": fim, "fim_ms": fim + self.dur_ms, "lado": s, "tocou": False}
                self.exa[nome] = g
                self.ev("exaustao_reacao", fim, **{k: v for k, v in g.items() if k not in ("gat_t", "can_t")})

    def tick(self, t_ms, bid, ask):
        for nome in ("pos", "sombra"):
            g = self.exa[nome]; p = getattr(self, nome)
            if g is None: continue
            if p is None or p["id"] != g["id"] or p["saida_pendente"]: self.exa[nome] = None; continue
            if t_ms < g["ini_ms"] or t_ms >= g["fim_ms"]: continue
            s = g["lado"]; bt = tk(bid)
            sup = (bt >= g["gat_t"]) if s < 0 else (bt <= g["gat_t"])
            can = (bt <= g["can_t"]) if s < 0 else (bt >= g["can_t"])
            m = self.m1_atual
            if m is not None and (sup or can):
                h_t, l_t = tk(m[0]), tk(m[1])
                amb = ((h_t >= g["gat_t"] and l_t <= g["can_t"]) if s < 0 else (l_t <= g["gat_t"] and h_t >= g["can_t"]))
                if amb:
                    self.ev("exaustao_indeterminada", t_ms, id=g["id"], gatilho=g["gat"], cancel=g["cancel"], m1_max=m[0], m1_min=m[1])
                    self.trilha_exa.append({**g, "resultado": "indeterminado (mesma M1 cruzou o gatilho e renovou a mínima)"}); self.exa[nome] = None; continue
            if can:
                self.ev("exaustao_cancelada", t_ms, id=g["id"], gatilho=g["gat"], bid=bid); self.trilha_exa.append({**g, "resultado": "cancelado", "t_ms": t_ms}); self.exa[nome] = None; continue
            if sup:
                self.exa[nome] = None; self.trilha_exa.append({**g, "resultado": "saiu", "t_ms": t_ms, "bid": bid})
                self.ev("exaustao_saida", t_ms, id=g["id"], gatilho=g["gat"], bid=bid, ask=ask)
                self._fechar(nome, t_ms, ask if s < 0 else bid, "exaustao", bid, ask)
        super().tick(t_ms, bid, ask)


def ticks_m1(m1, ini):
    for b in m1.itertuples():
        up = b.close >= b.open; p1, p2 = (b.low, b.high) if up else (b.high, b.low)
        for px, dt in zip((b.open, p1, p2, b.close), (0, 15, 30, 59)):
            t = int(b.ep) + dt
            if ini is None or t >= ini: yield t, px, (b.high, b.low)


def rodar(m15, h1, m1, ini, sp, tf="M15", at="XAUUSD", m1_real=True, **kw):
    """replay como compz_o55.rodar; com m1_real=True o caso 'mesma M1 cruza e renova' vira indeterminado."""
    I = InstanciaE(at, tf, **kw); I.ativo_desde_ms = 0; dur = R1.TF_MIN[tf] * 60; ult = None
    def df(x): return pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)
    ep_tf = m15.ep.values; ep_h1 = h1.ep.values if h1 is not None else None
    for t, px, hl in ticks_m1(m1, ini):
        t0 = (t // dur) * dur
        if t0 != ult:
            n = int(np.searchsorted(ep_tf + dur, t, side="right"))
            if n >= 29:
                rh = df(h1.iloc[:int(np.searchsorted(ep_h1 + 3600, t, side="right"))]) if h1 is not None else None
                I.fecha_barra(df(m15.iloc[max(0, n - 1200):n]), rh); ult = t0
        I.m1_atual = hl if m1_real else None
        bid = round(px, 2); I.tick(t * 1000, bid, round(bid + sp, 2))
    return I


def gerir(m15, m1, lado, E, stop, t_ent, sp, exaustao=True, sinal="POS", m1_real=True, at="BTCUSD"):
    """replay só da GESTÃO de uma posição dada (lado, entrada E, stop, instante t_ent em s UTC) — mesma gestão do EA r1.4:
    corte estrutural (máx./mín. da barra de entrada), canal EMA20, stop 2 ATR e, com exaustao=True, a saída por exaustão.
    m15/m1: DataFrames ep,open,high,low,close (UTC). Devolve a InstanciaE (ops, eventos, trilha_exa)."""
    I = InstanciaE(at, "M15", exaustao=exaustao, caixa=False, rompz=False, compz=False, filtro=False, reversao_sombra=False)
    I.ativo_desde_ms = 0; ult = None; aberto = False; ep = m15.ep.values
    def df(x): return pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)
    for t, px, hl in ticks_m1(m1, None):
        t0 = (t // 900) * 900
        if t0 != ult:
            n = int(np.searchsorted(ep + 900, t, side="right")); I.fecha_barra(df(m15.iloc[max(0, n - 1200):n]), None); ult = t0
        if not aberto and t >= t_ent:
            I.pos = {"id": sinal, "sinal": sinal, "lado": lado, "t_ent_ms": int(t_ent) * 1000, "entrada": float(E), "stop": float(stop), "atr": abs(E - stop) / 2,
                     "barra_ent_ms": (int(t_ent) // 900) * 900 * 1000, "ref_inval": None, "ref_def": "", "saida_pendente": False, "saida_apos_ms": None,
                     "motivo_dec": None, "spread_ent": sp, "espaco": {}}; aberto = True
        I.m1_atual = hl if m1_real else None
        bid = round(px, 2); I.tick(t * 1000, bid, round(bid + sp, 2))
        if aberto and I.pos is None: break
    return I
