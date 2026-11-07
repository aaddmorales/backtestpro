"""leitura-m1m5-0.1 (ORDEM 042) — leitura M1/M5 barra a barra (só barras FECHADAS), confirmação de ENTRADA e ALERTA de reversão (REGRAS programadas)
e o replay com as variantes E (entrada), S (saída) e E+S sobre a V1-200 da O40 (mesmos níveis, stop, custos). Especificação: O42_especificacao_congelada.txt."""
import numpy as np, pandas as pd
import estrategia_o39 as ST, janela_o40 as JN
VERSAO = "leitura-m1m5-0.1 (ORDEM 042)"; MIN = 60 * 10**9


class M1M5:
    """arrays M1 (bid) + M5 agregadas das M1 (só completas). Índices: k = M1 fechada; disponível no instante t1[k] + 1 min."""
    def __init__(self, m1):
        self.t1 = m1.t.values.astype("datetime64[ns]").astype(np.int64); self.o, self.h, self.l, self.c = (m1[k].values.astype(float) for k in "ohlc")
        g = m1.t.dt.floor("5min"); d = m1.assign(g=g).groupby("g").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), n=("o", "size"), tu=("t", "last"))
        d = d[(d.tu - d.index) == pd.Timedelta(minutes=4)]                                     # M5 completa = tem a M1 do minuto 4
        self.t5_fim = (d.index.values.astype("datetime64[ns]").astype(np.int64) + 5 * MIN); self.o5, self.c5 = d.o.values, d.c.values; self.h5, self.l5 = d.h.values, d.l.values

    def m5_fechadas(self, instante):
        return int(np.searchsorted(self.t5_fim, instante, side="right"))                       # quantas M5 já fecharam até o instante

    def marcas(self, k, s):
        """marcas da M1 fechada k para o lado s (−1 venda, +1 compra)."""
        if k < 6: return {}
        o, h, l, c = self.o, self.h, self.l, self.c; fav = lambda x: s * x                      # deslocamento favorável > 0 (venda: queda)
        av = fav(c[k] - c[k - 3]) > 0
        pf = av and fav(c[k - 3] - c[k - 6]) > 0 and abs(c[k] - c[k - 3]) < 0.5 * abs(c[k - 3] - c[k - 6])
        rj = False
        for q in (k - 2, k - 1, k):
            r = h[q] - l[q]
            if r <= 0: continue
            if s < 0 and (min(o[q], c[q]) - l[q]) / r >= 0.6 and c[q] >= (h[q] + l[q]) / 2: rj = True
            if s > 0 and (h[q] - max(o[q], c[q])) / r >= 0.6 and c[q] <= (h[q] + l[q]) / 2: rj = True
        contra = lambda q: (c[q] > o[q]) if s < 0 else (c[q] < o[q])
        pc = contra(k) and contra(k - 1)
        rt = (not contra(k)) and contra(k - 1) and ((c[k] < l[k - 1]) if s < 0 else (c[k] > h[k - 1]))
        return {"avanco": bool(av), "perda_forca": bool(pf), "rejeicao": bool(rj), "retomada": bool(rt), "pressao_contraria": bool(pc)}

    def leitura(self, k, s, instante):
        """o que M1 (15 fechadas) e M5 (3 fechadas) mostravam no instante; k = última M1 fechada."""
        n5 = self.m5_fechadas(instante); m5 = [{"fim": str(pd.Timestamp(int(self.t5_fim[q]))), "o": self.o5[q], "c": self.c5[q], "contraria": bool((self.c5[q] > self.o5[q]) if s < 0 else (self.c5[q] < self.o5[q]))}
                                              for q in range(max(0, n5 - 3), n5)]
        seq = []
        for q in range(max(6, k - 14), k + 1):
            mk = self.marcas(q, s); seq.append("".join(x for x, f in (("A", "avanco"), ("F", "perda_forca"), ("R", "rejeicao"), ("T", "retomada"), ("P", "pressao_contraria")) if mk.get(f)) or "·")
        return {"m1_ultima_fechada": str(pd.Timestamp(int(self.t1[k]))), "m1_marcas_15": seq, "m1_atual": self.marcas(k, s), "m5_3": m5, "m5_contraria": bool(m5 and m5[-1]["contraria"]), "n5": n5}

    def confirma_entrada(self, k, s, instante):
        L = self.leitura(k, s, instante); m = L["m1_atual"]
        ok = bool(m) and m["avanco"] and not m["rejeicao"] and not m["pressao_contraria"] and not L["m5_contraria"]
        return ok, L

    def alerta(self, k, s, atr15, instante):
        if k < 3: return False, None
        n5 = self.m5_fechadas(instante)
        m1c = (-s) * (self.c[k] - self.c[k - 3]) >= 0.5 * atr15                          # deslocamento CONTRA o lado nas 3 últimas M1 fechadas
        m5c = n5 >= 2 and (((self.c5[n5 - 1] > self.o5[n5 - 1]) and self.c5[n5 - 1] > self.c5[n5 - 2]) if s < 0 else ((self.c5[n5 - 1] < self.o5[n5 - 1]) and self.c5[n5 - 1] < self.c5[n5 - 2]))
        return bool(m1c and m5c), {"m1_contra_3barras_atr": round(float(-s * (self.c[k] - self.c[k - 3]) / atr15), 3), "m5_contraria_avancando": bool(m5c)}


class ReplayM1(JN.ReplayJanela):
    """V1-200 da O40 com as variantes: entrada (E), saída (S) ou ambas (E+S). Sem flags = idêntico à Referência."""
    def __init__(self, at, m15, m1, rotulo, entrada=False, saida=False, **k):
        super().__init__(at, m15, m1, "V1-200", **k); self.rot, self.E, self.S = rotulo, entrada, saida; self.L = M1M5(m1); self.alertas = []
        self.v = rotulo

    def _abrir(self, i, j, px, g, conf, leitura, motivo):
        s = g["lado"]; atr = g["atr"]
        self.pos = {"versao": self.v, "id": f"{self.v}-{self.at}-{g['sinal']}", "lado": s, "sinal": g["sinal"], "referencia": g["referencia"], "tipo_referencia": g["tipo"], "t_sinal_fecha": g["t_sinal_fecha"],
                    "j_ent": j, "t_ent": int(self.t1[j]), "entrada": px, "bid_gatilho": g["nivel_gatilho"], "spread_ent": self.sp[j], "stop": px - s * 2 * atr, "atr": atr,
                    "ref_h": float(self.m15.h.iloc[i - 1]), "ref_l": float(self.m15.l.iloc[i - 1]), "alerta_bar": False, "n_alertas": 0, "mfe": 0.0, "leitura_entrada": leitura, "obstaculo": g.get("obstaculo")}
        self.R(i, "entrada", motivo=motivo, resultado=True, id=self.pos["id"], t_m1=str(pd.Timestamp(int(self.t1[j]))), preco=px, confirmacao_m1m5=conf, leitura=leitura)

    def _gatilho(self, i, a, b, g):
        T = g["nivel_gatilho"]; s = g["lado"]; hit = np.nonzero((self.l1[a:b] <= T + 1e-9) if s < 0 else (self.h1[a:b] >= T - 1e-9))[0]
        if not len(hit):
            self.R(i, "gatilho_expirado", motivo="a barra seguinte terminou sem superar o extremo (igualar não confirma)", resultado=False, referencia=g["referencia"]); return None
        j = a + int(hit[0]); bid = min(T, self.o1[j]) if s < 0 else max(T, self.o1[j]); px = bid if s < 0 else bid + self.sp[j]
        if not self.E:
            self._abrir(i, j, px, g, None, None, "superação por ≥ 1 tick (referência)"); return j
        ok, L = self.L.confirma_entrada(j - 1, s, int(self.t1[j]))
        if ok:
            self._abrir(i, j, px, g, "confirmada no instante da superação", L, "superação por ≥ 1 tick com continuidade M1/M5"); return j
        self.R(i, "superacao_sem_continuidade", motivo="superou, mas M1/M5 não confirmam a continuidade no instante (aguarda dentro da barra válida)", leitura=L, resultado=False, referencia=g["referencia"])
        fim15 = self.f15[i]
        for k in range(j, b):
            if self.t1[k] + MIN > fim15 or k + 1 >= len(self.t1): break
            alem = (self.L.c[k] <= T + 1e-9) if s < 0 else (self.L.c[k] >= T - 1e-9)
            if not alem: continue
            ok, L = self.L.confirma_entrada(k, s, int(self.t1[k]) + MIN)
            if ok:
                jj = k + 1; px2 = self.o1[jj] if s < 0 else self.o1[jj] + self.sp[jj]
                self._abrir(i, jj, px2, g, "confirmada depois da superação (1º preço disponível)", L, "continuidade M1/M5 confirmada depois da superação"); return jj
        self.R(i, "gatilho_expirado", motivo="a barra válida terminou sem continuidade M1/M5 confirmada (sem confirmação tardia)", resultado=False, referencia=g["referencia"]); return None

    def _vigiar(self, a, b, i):
        """stop + (S) alertas M1/M5 dentro da barra i. Devolve True se a posição foi encerrada pelo stop."""
        p = self.pos
        for jj in range(max(a, p["j_ent"]), b):
            if (p["lado"] > 0 and self.l1[jj] <= p["stop"]) or (p["lado"] < 0 and self.h1[jj] + self.sp[jj] >= p["stop"]):
                px = min(p["stop"], self.o1[jj]) if p["lado"] > 0 else max(p["stop"], self.o1[jj] + self.sp[jj])
                if jj == p["j_ent"]: px = p["stop"]
                self.fechar(jj, px, "stop de proteção"); return True
            fav = (self.L.c[jj] - p["entrada"]) * p["lado"]; p["mfe"] = max(p["mfe"], fav / abs(p["entrada"] - p["stop"]))
            if self.S and jj > p["j_ent"] and i >= 1:
                al, info = self.L.alerta(jj, p["lado"], self.ATR[i - 1], int(self.t1[jj]) + MIN)
                if al and not p["alerta_bar"]:
                    p["alerta_bar"] = True; p["n_alertas"] += 1
                    self.R(i, "alerta_reversao_m1m5", motivo="pressão contrária em M1 e M5; aguardando confirmação no M15 (M1/M5 sozinhos não cortam)", leitura=self.L.leitura(jj, p["lado"], int(self.t1[jj]) + MIN), info=info, id=p["id"])
        return False

    def rodar(self, i0=25, i1=None):
        m15 = self.m15; O, H, L, C = (m15[k].values.astype(float) for k in "ohlc"); i1 = i1 or len(m15)
        for i in range(i0, i1):
            a, b = self.m1_da_barra(i); saiu = False
            if self.pos is not None and self._vigiar(a, b, i): saiu = True
            g, self.gat = self.gat, None
            if g is not None and self.pos is None:
                j = self._gatilho(i, a, b, g)
                if j is not None and self._vigiar(j, b, i): saiu = True
            evs = self.mem.nova_barra(str(m15.t.iloc[i]), str(pd.Timestamp(int(self.f15[i]))), O[i], H[i], L[i], C[i])
            if self.pos is not None:
                p = self.pos; s = p["lado"]; j = b if b < len(self.t1) else None
                if j is None: break
                corte = self.S and p["alerta_bar"] and ((C[i] > p["ref_h"]) if s < 0 else (C[i] < p["ref_l"]))
                if self.S and p["alerta_bar"] and not corte:
                    self.R(i, "pullback_respeita_m15", motivo="alerta M1/M5 nesta barra, mas o fechamento M15 não passou do extremo oposto da barra de referência: mantém", id=p["id"], c15=C[i], ref=p["ref_h"] if s < 0 else p["ref_l"])
                p["alerta_bar"] = False
                dentro = (C[i] >= self.EL[i]) if s < 0 else (C[i] <= self.EH[i])
                if corte:
                    px = self.o1[j] + self.sp[j] if s < 0 else self.o1[j]; self.R(i, "corte_reversao_m15", motivo="alerta M1/M5 + fechamento M15 além do extremo oposto da barra de referência", id=p["id"], c15=C[i])
                    self.fechar(j, px, "corte por reversão confirmada no M15"); saiu = True
                elif dentro and self.t15[i] >= p["t_sinal_fecha"]:
                    px = self.o1[j] + self.sp[j] if s < 0 else self.o1[j]; self.fechar(j, px, "saída por sinal (fechamento de volta ao canal)"); saiu = True
            if self.pos is not None or saiu or not np.isfinite(self.ATR[i]): self.espera = None if self.pos is not None else self.espera; continue
            self.decidir(i, H, L, C, evs)


def seguir_saida(rp, op, saida):
    """NAS MESMAS ENTRADAS: reaplica a gestão a partir da entrada da operação `op` (dict da Referência) com ou sem a saída S. Devolve o resultado."""
    rp.S = saida; m15 = rp.m15; C = m15.c.values.astype(float); i_ref = int(np.searchsorted(m15.t.values, np.datetime64(pd.Timestamp(op["referencia"]))))
    rp.pos = {k: op[k] for k in ("versao", "id", "lado", "sinal", "referencia", "tipo_referencia", "t_sinal_fecha", "j_ent", "t_ent", "entrada", "bid_gatilho", "spread_ent", "stop", "atr")}
    rp.pos.update({"ref_h": float(m15.h.iloc[i_ref]), "ref_l": float(m15.l.iloc[i_ref]), "alerta_bar": False, "n_alertas": 0, "mfe": 0.0}); n0 = len(rp.ops)
    i = int(np.searchsorted(rp.f15, rp.t1[op["j_ent"]], side="right"))
    while rp.pos is not None and i < len(m15):
        a, b = rp.m1_da_barra(i)
        if rp._vigiar(a, b, i): break
        p = rp.pos; s = p["lado"]; j = b if b < len(rp.t1) else None
        if j is None: break
        corte = saida and p["alerta_bar"] and ((C[i] > p["ref_h"]) if s < 0 else (C[i] < p["ref_l"])); p["alerta_bar"] = False
        dentro = (C[i] >= rp.EL[i]) if s < 0 else (C[i] <= rp.EH[i])
        if corte: rp.fechar(j, rp.o1[j] + rp.sp[j] if s < 0 else rp.o1[j], "corte por reversão confirmada no M15")
        elif dentro and rp.t15[i] >= p["t_sinal_fecha"]: rp.fechar(j, rp.o1[j] + rp.sp[j] if s < 0 else rp.o1[j], "saída por sinal (fechamento de volta ao canal)")
        i += 1
    if len(rp.ops) == n0: return None
    r = rp.ops.pop(); return r
