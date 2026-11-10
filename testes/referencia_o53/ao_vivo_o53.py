"""lateral-r1 (ORDEM 053) — motor POR TICK de referência: R0 da O47 + filtro de espaço até a primeira zona (estrutura-0.1 da O39, TF do
gráfico + H1) + corte estrutural pela máxima/mínima da barra de entrada + reversão avaliada em SOMBRA. Posições VIRTUAIS; nunca envia ordens.
Especificação: O53_especificacao_congelada.txt (congelada antes do replay). Mesma ordem de eventos da O47."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "referencia_o51"))
import formacao_o44 as FO, romp_m15 as RM, estrutura_o39 as EO
from ao_vivo_o47 import CUSTO, TF_MIN, TICK, K_STOP, tk

VERSAO = "lateral-r1 (ORDEM 053)"
K_ESPACO_R = 1.0          # espaço líquido mínimo até a primeira zona, em R (congelado pelo dono)
N_JANELA = 1200           # aquecimento das memórias: últimas 1200 barras fechadas


class Memorias:
    """memória estrutural O39 do TF do gráfico e do H1 (no gráfico H1, uma só)."""
    def __init__(self, at, tf):
        self.tfs = [tf] if tf == "H1" else [tf, "H1"]
        self.m = {t: EO.Memoria(at, t) for t in self.tfs}; self.ult = {t: None for t in self.tfs}

    def alimentar(self, tf, rates):
        """rates: DataFrame t,o,h,l,c de barras FECHADAS do tf (ordem crescente)."""
        if rates is None or not len(rates): return
        ep = pd.to_datetime(rates.t).values.astype("datetime64[s]").astype("int64")
        if self.ult[tf] is None: ini = max(0, len(rates) - N_JANELA)
        else: ini = int(np.searchsorted(ep, self.ult[tf], side="right"))
        dur = TF_MIN[tf] * 60; M = self.m[tf]
        for i in range(ini, len(rates)):
            M.nova_barra(int(ep[i]), int(ep[i]) + dur, float(rates.o.iloc[i]), float(rates.h.iloc[i]), float(rates.l.iloc[i]), float(rates.c.iloc[i]))
            self.ult[tf] = int(ep[i])

    def obstaculo(self, lado, E):
        """primeira zona à frente nas memórias (mesma conta da Memoria.obstaculo, sem limiar)."""
        melhor = None
        for tf in self.tfs:
            for n in self.m[tf].niveis:
                if n["estado"] == "ROMPIMENTO CONFIRMADO": continue
                b, tz = n["zona"]
                if lado < 0 and n["funcao"] == "suporte" and b < E: d = max(0.0, E - tz)
                elif lado > 0 and n["funcao"] == "resistencia" and tz > E: d = max(0.0, b - E)
                else: continue
                if melhor is None or d < melhor[0] - 1e-9: melhor = (d, tf, n)
        if melhor is None: return None
        d, tf, n = melhor
        return {"tf": tf, "nivel": n["id"], "funcao": n["funcao"], "base": n["zona"][0], "topo": n["zona"][1], "estado": n["estado"], "testes": n["testes"],
                "rejeicoes": n["rejeicoes"], "membros": len(n["membros"]), "d": d, "dentro": d == 0.0}


def avaliar_espaco(mem, lado, bid, ask, atr):
    E = bid if lado < 0 else ask; sp = ask - bid; R = K_STOP * atr; z = mem.obstaculo(lado, E)
    out = {"E": E, "spread": sp, "R": R, "atr": atr, "zona": z}
    if z is None: return {**out, "passa": True, "motivo": "sem zona à frente"}
    liq = z["d"] - sp; out.update(d=z["d"], espaco_liq=liq, espaco_atr=liq / atr, espaco_R=liq / R)
    if z["dentro"]: return {**out, "passa": False, "motivo": "entrada dentro da zona"}
    if liq < K_ESPACO_R * R - 1e-9: return {**out, "passa": False, "motivo": "espaço insuficiente"}
    return {**out, "passa": True, "motivo": "espaço suficiente"}


class Instancia:
    def __init__(self, at, tf, filtro=True, corte=True, reversao_sombra=True):
        self.at, self.tf = at, tf; self.dur_ms = TF_MIN[tf] * 60_000; self.K = CUSTO[at]
        self.filtro, self.corte, self.rev = filtro, corte, reversao_sombra
        self.caixa = True                                                         # O53-D: a entrada de caixa (R0/R1) pode ser desligada
        self.usados = set(); self.pend = None; self.pos = None; self.sombra = None; self.ops = []; self.ops_sombra = []; self.eventos = []; self.sinais = []
        self.ult_barra_ms = None; self.ativo_desde_ms = None; self.mem = Memorias(at, tf)
        self.cont = {"barras": 0, "gatilhos_armados": 0, "superacoes": 0, "entradas": 0, "bloq_posicao": 0, "bloq_dentro_zona": 0, "bloq_espaco": 0,
                     "saidas_canal": 0, "saidas_corte": 0, "saidas_stop": 0, "rev_avaliadas": 0, "rev_abertas": 0}

    def ev(self, tipo, t_ms, **kw):
        e = {"instancia": f"{self.at}-{self.tf}", "tipo": tipo, "t": str(pd.Timestamp(int(t_ms), unit="ms")), "t_ms": int(t_ms), **kw}; self.eventos.append(e); return e

    # ── fechamento de barra do TF do gráfico ──
    def fecha_barra(self, rates, rates_h1=None):
        b = len(rates) - 1; t_ab = int(pd.Timestamp(rates.t.iloc[b]).value // 10**6); fim = t_ab + self.dur_ms
        if self.ult_barra_ms is not None and t_ab <= self.ult_barra_ms: return
        self.ult_barra_ms = t_ab; self.cont["barras"] += 1
        H, L, C = (rates[k].values.astype(float) for k in "hlc"); ATR = RM.atr_wilder(rates.h, rates.l, rates.c)
        EH = pd.Series(H).ewm(span=20, adjust=False).mean().values; EL = pd.Series(L).ewm(span=20, adjust=False).mean().values
        # (1) gatilho expirado
        if self.pend is not None and self.pend["fim_ms"] <= fim:
            g = self.pend; self.sinais.append({**g, "resultado_gatilho": "toque sem superação" if g["tocou"] else "não alcançou"}); self.ev("gatilho_expirado", fim, sinal=g["id"]); self.pend = None
        # (2) memórias
        if self.filtro or self.rev:
            self.mem.alimentar(self.tf, rates)
            if self.tf != "H1": self.mem.alimentar("H1", rates_h1)
        # (3) saídas decididas no fechamento (real e sombra)
        for nome in ("pos", "sombra"):
            p = getattr(self, nome)
            if p is None or p["saida_pendente"]: continue
            s = p["lado"]
            if p["ref_inval"] is None and t_ab == p["barra_ent_ms"]:
                p["ref_inval"] = float(H[b]) if s < 0 else float(L[b]); self.ev("ref_invalidacao_congelada", fim, id=p["id"], ref=p["ref_inval"], sombra=nome == "sombra")
                canal = (C[b] >= EL[b]) if s < 0 else (C[b] <= EH[b]); corte = False
            else:
                canal = (C[b] >= EL[b]) if s < 0 else (C[b] <= EH[b])
                corte = self.corte and p["ref_inval"] is not None and ((C[b] > p["ref_inval"]) if s < 0 else (C[b] < p["ref_inval"]))
            if corte or canal:
                p["saida_pendente"] = True; p["saida_apos_ms"] = fim; p["motivo_dec"] = "corte estrutural" if corte else "canal"
                self.ev("saida_decidida", fim, id=p["id"], motivo=p["motivo_dec"], c=float(C[b]), canal=float(EL[b] if s < 0 else EH[b]), ref=p["ref_inval"], canal_tambem=bool(corte and canal), sombra=nome == "sombra")
        # (4) formação → gatilho para a barra seguinte (R0 inalterada)
        if not self.caixa: return
        if self.ativo_desde_ms is None or t_ab < self.ativo_desde_ms or not np.isfinite(ATR[b]): return
        hT, lT, cT = (np.rint(x / TICK).astype(np.int64) for x in (H, L, C))
        for s in (-1, 1):
            d = FO.detectar_venda(lT, hT, cT, ATR, b) if s < 0 else FO.detectar_venda(-hT, -lT, -cT, ATR, b)
            if d is None: continue
            chave = f"{s}|{rates.t.iloc[d['p']]}"
            if chave in self.usados: continue
            self.usados.add(chave); F = (d["F"] if s < 0 else -d["F"]) * TICK; ext = L[b] if s < 0 else H[b]; T = (tk(ext) + s) * TICK
            g = {"id": f"{self.at}-{self.tf}-{'V' if s < 0 else 'C'}-{pd.Timestamp(rates.t.iloc[b]):%Y%m%d%H%M}", "lado": s, "nivel": round(F, 2), "extremo": round(ext, 2), "T": round(T, 2),
                 "T_t": tk(ext) + s, "ext_t": tk(ext), "atr": float(ATR[b]), "ini_ms": fim, "fim_ms": fim + self.dur_ms, "tocou": False, "barra_rompimento": str(rates.t.iloc[b])}
            self.pend = g; self.cont["gatilhos_armados"] += 1
            self.ev("gatilho_armado", fim, sinal=g["id"], lado=s, nivel=g["nivel"], extremo=g["extremo"], gatilho=g["T"], atr=round(g["atr"], 4)); break

    # ── tick ──
    def tick(self, t_ms, bid, ask):
        for nome in ("pos", "sombra"):
            p = getattr(self, nome)
            if p is None: continue
            s = p["lado"]
            if p["saida_pendente"] and t_ms >= p["saida_apos_ms"]: self._fechar(nome, t_ms, ask if s < 0 else bid, p["motivo_dec"], bid, ask)
            elif (s < 0 and ask >= p["stop"]) or (s > 0 and bid <= p["stop"]): self._fechar(nome, t_ms, ask if s < 0 else bid, "stop de proteção", bid, ask)
        g = self.pend
        if g is None or t_ms < g["ini_ms"] or t_ms >= g["fim_ms"]: return
        s = g["lado"]; b_t = tk(bid)
        if (b_t <= g["ext_t"]) if s < 0 else (b_t >= g["ext_t"]): g["tocou"] = True
        if not ((b_t <= g["T_t"]) if s < 0 else (b_t >= g["T_t"])): return
        self.pend = None; self.cont["superacoes"] += 1
        sig = {**g, "resultado_gatilho": "superou", "tau_ms": int(t_ms), "bid": bid, "ask": ask}
        if self.pos is not None:
            self.cont["bloq_posicao"] += 1; sig["decisao"] = "bloqueado: posição aberta"; self.sinais.append(sig); self.ev("bloqueado_posicao_aberta", t_ms, sinal=g["id"]); return
        esp = avaliar_espaco(self.mem, s, bid, ask, g["atr"]) if self.filtro else {"passa": True, "motivo": "filtro desligado"}
        sig["espaco"] = esp
        if not esp["passa"]:
            self.cont["bloq_dentro_zona" if esp["motivo"].startswith("entrada dentro") else "bloq_espaco"] += 1; sig["decisao"] = "bloqueado: " + esp["motivo"]; self.sinais.append(sig)
            self.ev("bloqueado_espaco", t_ms, sinal=g["id"], lado=s, motivo=esp["motivo"], E=esp["E"], spread=esp["spread"], R=esp["R"], d=esp.get("d"), espaco_R=esp.get("espaco_R"),
                    espaco_atr=esp.get("espaco_atr"), zona=esp["zona"]); return
        self._abrir("pos", g["id"], s, t_ms, bid, ask, g["atr"], esp)
        sig["decisao"] = "entrou"; self.sinais.append(sig)

    def _abrir(self, nome, sinal, s, t_ms, bid, ask, atr, esp):
        px = bid if s < 0 else ask; stop = px - s * K_STOP * atr; barra = (int(t_ms) // self.dur_ms) * self.dur_ms
        p = {"id": f"{sinal}{'-REV' if nome == 'sombra' else ''}", "sinal": sinal, "lado": s, "t_ent_ms": int(t_ms), "entrada": px, "stop": stop, "atr": atr, "barra_ent_ms": barra,
             "ref_inval": None, "ref_def": "máxima da barra de entrada" if s < 0 else "mínima da barra de entrada", "saida_pendente": False, "saida_apos_ms": None, "motivo_dec": None,
             "spread_ent": ask - bid, "espaco": esp}
        setattr(self, nome, p)
        if nome == "pos": self.cont["entradas"] += 1
        self.ev("entrada_virtual" if nome == "pos" else "reversao_sombra_aberta", t_ms, id=p["id"], lado=s, preco=px, stop=round(stop, 2), bid=bid, ask=ask, ref_def=p["ref_def"],
                espaco=esp.get("motivo"), espaco_R=esp.get("espaco_R"))

    def _fechar(self, nome, t_ms, px, motivo, bid, ask):
        p = getattr(self, nome); s = p["lado"]; r0 = abs(p["entrada"] - p["stop"]); c = self.K; bruto = (px - p["entrada"]) * s
        op = {**p, "t_sai_ms": int(t_ms), "saida": px, "motivo_saida": motivo, "R": bruto / r0 - 2 * c["com_lado"] / c["contrato"] / r0, "pts": bruto}
        setattr(self, nome, None)
        if nome == "pos":
            self.ops.append(op); self.cont["saidas_corte" if motivo == "corte estrutural" else "saidas_stop" if motivo.startswith("stop") else "saidas_canal"] += 1
        else: self.ops_sombra.append(op)
        self.ev("saida_virtual" if nome == "pos" else "reversao_sombra_fechada", t_ms, id=p["id"], motivo=motivo, preco=px, R=round(op["R"], 4))
        # reversão em SOMBRA: decisão independente, só após corte estrutural da posição real
        if nome == "pos" and motivo == "corte estrutural" and self.rev and self.sombra is None:
            self.cont["rev_avaliadas"] += 1; esp = avaliar_espaco(self.mem, -s, bid, ask, p["atr"])
            self.ev("reversao_sombra_avaliada", t_ms, id=p["id"], lado=-s, passa=esp["passa"], motivo=esp["motivo"], espaco_R=esp.get("espaco_R"))
            if esp["passa"]: self.cont["rev_abertas"] += 1; self._abrir("sombra", p["sinal"], -s, t_ms, bid, ask, p["atr"], esp)


def rodar(at, tf, bars, m1, h1=None, ini=None, sp=0.0, **kw):
    """replay tick a tick (4 ticks por M1: abertura, extremo 1, extremo 2, fechamento — mesma convenção do teste O51). bars/m1/h1: DataFrames ep,open,high,low,close."""
    I = Instancia(at, tf, **kw); I.ativo_desde_ms = 0; dur = TF_MIN[tf] * 60; ult = None
    def df(x): return pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)
    ep_tf = bars.ep.values; ep_h1 = h1.ep.values if h1 is not None else None
    for b in m1.itertuples():
        up = b.close >= b.open; p1, p2 = (b.low, b.high) if up else (b.high, b.low)
        for px, dt in zip((b.open, p1, p2, b.close), (0, 15, 30, 59)):
            t = int(b.ep) + dt
            if ini is not None and t < ini: continue
            t0 = (t // dur) * dur
            if t0 != ult:
                n = int(np.searchsorted(ep_tf + dur, t, side="right"))
                if n >= 29:
                    rh = None
                    if h1 is not None: rh = df(h1.iloc[:int(np.searchsorted(ep_h1 + 3600, t, side="right"))])
                    I.fecha_barra(df(bars.iloc[:n]), rh); ult = t0
            I.tick(t * 1000, round(px, 2), round(px + sp, 2))
    return I
