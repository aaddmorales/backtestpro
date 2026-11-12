"""compz-1 (ORDEM 055) — "última vela que respeitou o suporte/resistência" depois de uma MUDANÇA DE ESTRUTURA.
Referência Python (sem ordens). Especificação congelada: O55_especificacao_congelada.txt. Estende a InstanciaD (rompz_o53c: caixa + ROMPZ) com uma
terceira entrada independente, COMPZ. Reaproveita: pivôs da memória O39 (fractal 2+2), EMA20 High/Low, ATR14 Wilder, filtro de espaço vigente
(avaliar_espaco, 1,0 R) e a gestão da R1. A ROMPZ continua intacta (gatilho na mínima da vela que fechou fora da zona); a COMPZ usa a mínima da
ÚLTIMA vela que ainda respeitou o suporte da compressão."""
import os, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(AQUI, "..", "referencia_o53"), os.path.join(AQUI, "..", "referencia_o51")]
import rompz_o53c as RZ  # noqa: E402
import ao_vivo_o53 as R1  # noqa: E402
import romp_m15 as RM  # noqa: E402

VERSAO = "compz-1 (ORDEM 055)"
LH_JANELA, K_CAIXA, K_BANDA, N_MIN, N_MAX = 12, 2.0, 0.25, 3, 16
TICK = RZ.TICK; tk = RZ.tk


class InstanciaC(RZ.InstanciaD):
    def __init__(self, at, tf, compz=True, filtro_compz=True, **kw):
        super().__init__(at, tf, **kw)
        self.compz, self.filtro_compz = compz, filtro_compz
        self.piv = {"topo": [], "fundo": []}          # (t_extremo s, extremo, t_confirmacao s) em ordem de confirmação
        self.cz = {-1: None, 1: None}; self.sinais_cz = []; self.usados_lh = set()
        M = self.mem.m[tf]; anterior = M.nova_barra
        def nb(t_ab, t_fecha, o, h, l, c):
            ev = anterior(t_ab, t_fecha, o, h, l, c)
            for e in ev:
                if e["evento"] not in ("confirmado", "agrupado"): continue
                n = next(x for x in M.niveis if x["id"] == e["nivel"])
                tipo = "fundo" if n["funcao"] == "suporte" else "topo"          # tipo do PIVÔ novo (o nível pode ter trocado de função)
                t_ex = n["t_extremo"] if e["evento"] == "confirmado" else n["membros"][-1]["t_extremo"]
                self.piv[tipo].append((int(t_ex), float(e["extremo"]), int(t_fecha)))
            return ev
        M.nova_barra = nb

    def fecha_barra(self, rates, rates_h1=None):
        b = len(rates) - 1; t_ab = int(pd.Timestamp(rates.t.iloc[b]).value // 10**6); fim = t_ab + self.dur_ms
        aquecendo = self.mem.ult[self.tf] is None
        super().fecha_barra(rates, rates_h1)
        if self.ult_barra_ms != t_ab or aquecendo or not self.compz: return
        H, L, C = (rates[k].values.astype(float) for k in "hlc")
        EH = pd.Series(H).ewm(span=20, adjust=False).mean().values; EL = pd.Series(L).ewm(span=20, adjust=False).mean().values
        atr = float(RM.atr_wilder(rates.h, rates.l, rates.c)[b]); dur = self.dur_ms // 1000; tb = t_ab // 1000
        h, l, c = H[b], L[b], C[b]
        for s in (-1, 1):
            z = self.cz[s]
            # (a) compressão em andamento: atualizar caixa, referência ou cancelar
            if z is not None and z["fase"] == "compressao" and tb > z["barra_mudanca"]:
                lo0, hi0 = z["lo"], z["hi"]
                z["n"] += 1; z["lo"] = l if lo0 is None else min(lo0, l); z["hi"] = h if hi0 is None else max(hi0, h)
                sup = z["lo"] if s < 0 else z["hi"]; sup0 = lo0 if s < 0 else hi0
                motivo = None
                if z["hi"] - z["lo"] > K_CAIXA * z["atr"] + 1e-9: motivo = f"caixa {z['hi'] - z['lo']:.2f} > {K_CAIXA}·ATR {K_CAIXA * z['atr']:.2f}"
                elif (s < 0 and h > z["ext_lh"]) or (s > 0 and l < z["ext_lh"]): motivo = "superou o topo/fundo da mudança"
                elif (s < 0 and c > EH[b]) or (s > 0 and c < EL[b]): motivo = "fechou do outro lado do canal EMA20"
                elif z["n"] > N_MAX: motivo = f"mais de {N_MAX} barras"
                elif sup0 is not None and ((s < 0 and c < sup0) or (s > 0 and c > sup0)): motivo = "fechou além do suporte/resistência sem disparo"
                if motivo:
                    self.ev("compz_cancelado", fim, sinal=z["id"], motivo=motivo); z["resultado"] = "cancelado: " + motivo; self.sinais_cz.append(z); self.cz[s] = None
                else:
                    respeita = (sup0 is None) or (c >= sup0 if s < 0 else c <= sup0)
                    testa = (l <= sup + K_BANDA * z["atr"] + 1e-9) if s < 0 else (h >= sup - K_BANDA * z["atr"] - 1e-9)
                    if respeita and testa:
                        ext = l if s < 0 else h
                        z.update(ref=round(ext, 2), ref_t=tb, ref_tk=tk(ext), gat=round((tk(ext) + s) * TICK, 2), suporte=round(sup, 2))
                        self.ev("compz_referencia", fim, sinal=z["id"], lado=s, barra_ref=tb, ref=z["ref"], gatilho=z["gat"], suporte=z["suporte"],
                                caixa=[round(z["lo"], 2), round(z["hi"], 2)], n=z["n"])
                    z["armado"] = z["n"] >= N_MIN and z.get("ref") is not None
                continue
            # (b) nova mudança de estrutura
            if z is not None: continue
            tipo = "topo" if s < 0 else "fundo"; P = self.piv[tipo]
            if len(P) < 2: continue
            (t1, x1, _), (t0, x0, _) = P[-1], P[-2]
            lh = (x1 < x0) if s < 0 else (x1 > x0)
            perto = (tb - t1) // dur <= LH_JANELA
            canal = (c < EL[b]) if s < 0 else (c > EH[b])
            if lh and perto and canal and (tipo, t1) not in self.usados_lh:
                self.usados_lh.add((tipo, t1))
                z = {"id": ("CV-" if s < 0 else "CC-") + str(tb), "lado": s, "fase": "compressao", "barra_mudanca": tb, "t_lh": t1, "ext_lh": x1, "ext_ant": x0,
                     "atr": atr, "lo": None, "hi": None, "n": 0, "armado": False, "fechamento": c, "ema": float(EL[b] if s < 0 else EH[b])}
                self.cz[s] = z
                self.ev("compz_mudanca", fim, sinal=z["id"], lado=s, lh=x1, t_lh=t1, anterior=x0, fechamento=c, ema=z["ema"], atr=atr)

    def tick(self, t_ms, bid, ask):
        super().tick(t_ms, bid, ask)
        for s in (-1, 1):
            z = self.cz[s]
            if not z or not z.get("armado") or t_ms // 1000 < z["ref_t"] + self.dur_ms // 1000: continue
            bt = tk(bid)
            if not ((bt <= z["ref_tk"] + s) if s < 0 else (bt >= z["ref_tk"] + s)): continue
            self.cz[s] = None
            pos = self.pos is not None; esp = R1.avaliar_espaco(self.mem, s, bid, ask, z["atr"])
            n_tf = self.mem.m[self.tf].n_barras; n_h1 = self.mem.m["H1"].n_barras if "H1" in self.mem.m else n_tf
            sem_hist = esp["motivo"] == "sem zona à frente" and (n_tf < RZ.MIN_HIST or (self.tf != "H1" and n_h1 < RZ.MIN_HIST))
            passa = esp["passa"] and not sem_hist
            if pos: dec = "sinal disparado; bloqueado: posicao aberta"
            elif sem_hist: dec = "sinal disparado; bloqueado: distancia nao calculavel (historico insuficiente)"
            elif not passa: dec = "sinal disparado; bloqueado: entrada dentro da zona" if esp["motivo"].startswith("entrada dentro") else "sinal disparado; bloqueado por falta de espaco"
            else: dec = "sinal disparado; ordem autorizada"
            z.update(resultado="disparo", t=t_ms // 1000, bid=bid, ask=ask, espaco=esp, decisao=dec, sem_filtro_sombra="bloqueado: posicao aberta" if pos else "entraria (sombra)")
            self.sinais_cz.append(z)
            self.ev("compz_disparo", t_ms, sinal=z["id"], lado=s, bid=bid, ask=ask, gatilho=z["gat"], ref=z["ref"], barra_ref=z["ref_t"], decisao=dec,
                    motivo=esp["motivo"], espaco_R=esp.get("espaco_R"), zona=esp.get("zona"))
            if not pos and (passa or not self.filtro_compz) and self.enviar:
                self._abrir("pos", z["id"], s, t_ms, bid, ask, z["atr"], esp)


def rodar(m15, h1, m1, ini, sp, tf="M15", at="XAUUSD", **kw):
    """igual a rompz_o53c.rodar, com a InstanciaC."""
    I = InstanciaC(at, tf, **kw); I.ativo_desde_ms = 0; dur = R1.TF_MIN[tf] * 60; ult = None
    def df(x): return pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)
    ep_tf = m15.ep.values; ep_h1 = h1.ep.values if h1 is not None else None
    for t, px in RZ.ticks_m1(m1, ini):
        t0 = (t // dur) * dur
        if t0 != ult:
            n = int(np.searchsorted(ep_tf + dur, t, side="right"))
            if n >= 29:
                rh = df(h1.iloc[:int(np.searchsorted(ep_h1 + 3600, t, side="right"))]) if h1 is not None else None
                I.fecha_barra(df(m15.iloc[max(0, n - 1200):n]), rh); ult = t0
        bid = round(px, 2); I.tick(t * 1000, bid, round(bid + sp, 2))
    return I
