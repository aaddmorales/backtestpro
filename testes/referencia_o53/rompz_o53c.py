"""rompz-1 (ORDEM 053-D) — ROMPIMENTO DE ZONA da memória O39 como ENTRADA PRÓPRIA (sem a caixa de 3 ATR). Referência Python do EA lateral-r1.2 (O53-D).

Regra do dono (O53-C/D): usam-se só zonas de suporte/resistência JÁ CONFIRMADAS antes da barra de rompimento (na memória O39 os níveis conhecidos
são atualizados antes de confirmar novos). A barra M15 que FECHA abaixo da borda inferior de um suporte (venda) / acima da borda superior de uma
resistência (compra) arma o gatilho na sua mínima (máxima). SÓ na barra seguinte, o primeiro tick cujo BID fica ≥ 1 tick além dispara o SINAL.
Igualar não dispara; sem superação na barra seguinte, o sinal expira. Não espera fechamento, terceira barra nem reteste.
O SINAL é separado da AUTORIZAÇÃO da ordem: no disparo registra-se a 1ª zona à frente (M15 + H1) e a distância líquida de spread em R;
o fluxo autorizado usa o filtro de 1,0 R ("sinal disparado; bloqueado por falta de espaço"); a variante sem filtro existe só em sombra.
Se não houver zona à frente e a memória tiver menos de 200 barras, a distância é declarada NÃO CALCULÁVEL (bloqueia no fluxo autorizado).
Gestão da posição = a da R1 (stop 2 ATR, corte estrutural pela máxima/mínima da barra de entrada, saída no canal EMA20). A entrada de caixa
(R0/R1) continua como entrada separada (caixa=True)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "referencia_o51"))
import romp_m15 as RM  # noqa: E402
import ao_vivo_o53 as R1  # noqa: E402

VERSAO = "rompz-1 (ORDEM 053-D)"; TICK = 0.01; MIN_HIST = 200
tk = lambda x: int(np.rint(x / TICK))


class InstanciaD(R1.Instancia):
    def __init__(self, at, tf, caixa=True, rompz=True, filtro_rompz=True, enviar=True, **kw):
        super().__init__(at, tf, **kw)
        self.caixa, self.rompz, self.filtro_rompz, self.enviar = caixa, rompz, filtro_rompz, enviar
        self.rz = {-1: None, 1: None}; self.sinais_rz = []; self._ultev = (None, [])
        M = self.mem.m[tf]; orig = M.nova_barra
        def nb(t_ab, t_fecha, o, h, l, c):
            ev = orig(t_ab, t_fecha, o, h, l, c); self._ultev = (int(t_ab), ev); return ev
        M.nova_barra = nb

    def fecha_barra(self, rates, rates_h1=None):
        b = len(rates) - 1; t_ab = int(pd.Timestamp(rates.t.iloc[b]).value // 10**6); fim = t_ab + self.dur_ms
        if self.ult_barra_ms is not None and t_ab <= self.ult_barra_ms: return
        for s in (-1, 1):
            p = self.rz[s]
            if p and p["fim_ms"] <= fim:
                p["resultado"] = "toque sem superacao" if p["tocou"] else "nao alcancou"; self.sinais_rz.append(p)
                self.ev("rompz_expirado", fim, sinal=p["id"], resultado=p["resultado"]); self.rz[s] = None
        aquecendo = self.mem.ult[self.tf] is None; self._ultev = (None, [])
        super().fecha_barra(rates, rates_h1)
        if self.ult_barra_ms != t_ab: return
        atr = float(RM.atr_wilder(rates.h, rates.l, rates.c)[b])
        t_ev, evs = self._ultev
        if aquecendo or not self.rompz or not (atr > 0) or t_ev != t_ab // 1000: return
        M = self.mem.m[self.tf]; niv = {x["id"]: x for x in M.niveis}
        for s in (-1, 1):
            zs = [niv[e["nivel"]] for e in evs if e["evento"] == "rompimento_pendente" and (niv[e["nivel"]]["funcao"] == "suporte") == (s < 0)]
            if not zs: continue
            ext = float(rates.l.iloc[b] if s < 0 else rates.h.iloc[b])
            p = {"id": ("ZV-" if s < 0 else "ZC-") + str(t_ab // 1000), "lado": s, "ext_t": tk(ext), "T_t": tk(ext) + s, "extremo": round(ext, 2),
                 "gatilho": round((tk(ext) + s) * TICK, 2), "atr": atr, "ini_ms": fim, "fim_ms": fim + self.dur_ms, "tocou": False, "barra_rompimento": t_ab // 1000,
                 "fechamento": float(rates.c.iloc[b]),
                 "zonas": [{"base": round(z["zona"][0], 2), "topo": round(z["zona"][1], 2), "confirmada_em": int(z["t_confirmacao"]), "t_extremo": int(z["t_extremo"]),
                            "testes": z["testes"]} for z in zs]}
            self.rz[s] = p
            self.ev("rompz_armado", fim, sinal=p["id"], lado=s, gatilho=p["gatilho"], extremo=p["extremo"], zonas=p["zonas"], atr=atr)

    def tick(self, t_ms, bid, ask):
        super().tick(t_ms, bid, ask)
        for s in (-1, 1):
            p = self.rz[s]
            if not p or not (p["ini_ms"] <= t_ms < p["fim_ms"]): continue
            bt = tk(bid)
            if (bt <= p["ext_t"]) if s < 0 else (bt >= p["ext_t"]): p["tocou"] = True
            if not ((bt <= p["T_t"]) if s < 0 else (bt >= p["T_t"])): continue
            self.rz[s] = None
            pos = self.pos is not None; esp = R1.avaliar_espaco(self.mem, s, bid, ask, p["atr"])
            n_tf = self.mem.m[self.tf].n_barras; n_h1 = self.mem.m["H1"].n_barras if "H1" in self.mem.m else n_tf
            sem_hist = esp["motivo"] == "sem zona à frente" and (n_tf < MIN_HIST or (self.tf != "H1" and n_h1 < MIN_HIST))
            passa = esp["passa"] and not sem_hist
            if pos: dec = "sinal disparado; bloqueado: posicao aberta"
            elif sem_hist: dec = "sinal disparado; bloqueado: distancia nao calculavel (historico insuficiente)"
            elif not passa: dec = "sinal disparado; bloqueado: entrada dentro da zona" if esp["motivo"].startswith("entrada dentro") else "sinal disparado; bloqueado por falta de espaco"
            else: dec = "sinal disparado; ordem autorizada"
            p.update(resultado="disparo", t=t_ms // 1000, bid=bid, ask=ask, espaco=esp, sem_historico=sem_hist, historico_barras={"TF": n_tf, "H1": n_h1},
                     decisao=dec, sem_filtro_sombra="bloqueado: posicao aberta" if pos else "entraria (sombra)")
            self.sinais_rz.append(p)
            self.ev("rompz_disparo", t_ms, sinal=p["id"], lado=s, bid=bid, ask=ask, gatilho=p["gatilho"], espaco_passa=passa, decisao=dec, motivo=esp["motivo"],
                    espaco_R=esp.get("espaco_R"), zona=esp.get("zona"), sem_historico=sem_hist)
            autorizado = not pos and (passa or not self.filtro_rompz)
            if autorizado and self.enviar:
                self._abrir("pos", p["id"], s, t_ms, bid, ask, p["atr"], esp)


def ticks_m1(m1, ini):
    for b in m1.itertuples():
        up = b.close >= b.open; p1, p2 = (b.low, b.high) if up else (b.high, b.low)
        for px, dt in zip((b.open, p1, p2, b.close), (0, 15, 30, 59)):
            t = int(b.ep) + dt
            if ini is None or t >= ini: yield t, px


def rodar(m15, h1, m1, ini, sp, tf="M15", at="BTCUSD", **kw):
    """replay tick a tick (mesma convenção do simulador do EA: 4 ticks por M1, bid = preço, ask = bid + spread). Devolve a InstanciaD."""
    I = InstanciaD(at, tf, **kw); I.ativo_desde_ms = 0; dur = R1.TF_MIN[tf] * 60; ult = None
    def df(x): return pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)
    ep_tf = m15.ep.values; ep_h1 = h1.ep.values if h1 is not None else None
    for t, px in ticks_m1(m1, ini):
        t0 = (t // dur) * dur
        if t0 != ult:
            n = int(np.searchsorted(ep_tf + dur, t, side="right"))
            if n >= 29:
                rh = df(h1.iloc[:int(np.searchsorted(ep_h1 + 3600, t, side="right"))]) if h1 is not None else None
                I.fecha_barra(df(m15.iloc[max(0, n - 1200):n]), rh); ult = t0
        bid = round(px, 2); I.tick(t * 1000, bid, round(bid + sp, 2))
    return I


def resumo(ops):
    R = [o["R"] for o in ops]
    return {"operacoes": len(R), "R_total": round(sum(R), 3), "R_medio": round(sum(R) / len(R), 3) if R else None, "vencedoras": sum(1 for r in R if r > 0),
            "perdedoras": sum(1 for r in R if r <= 0), "pior_R": round(min(R), 3) if R else None, "melhor_R": round(max(R), 3) if R else None}
