"""lateral-tf-ao-vivo-0.1 (ORDEM 047) — motor POR TICK da R0 da O44 para uma instância (ativo × TF). Posições VIRTUAIS; nunca envia ordens.
Eventos em ordem de tempo: fechamento de barra do TF (fecha_barra) antes dos ticks ≥ fim da barra; ticks (tick) com bid/ask observados.
Especificação: O47_especificacao_congelada.txt."""
import numpy as np, pandas as pd
import formacao_o44 as FO, romp_m15 as RM
VERSAO = "lateral-tf-ao-vivo-0.1 (ORDEM 047)"; TICK = 0.01; K_STOP = 2.0
CUSTO = {"XAUUSD": {"contrato": 100.0, "com_lado": 3.50}, "BTCUSD": {"contrato": 1.0, "com_lado": 0.0}}
TF_MIN = {"M15": 15, "M30": 30, "H1": 60}


def tk(x): return int(round(float(x) / TICK))


class Instancia:
    def __init__(self, at, tf):
        self.at, self.tf = at, tf; self.dur_ms = TF_MIN[tf] * 60_000; self.K = CUSTO[at]
        self.usados = set(); self.pend = None; self.pos = None; self.ops = []; self.eventos = []; self.sinais = []; self.ult_barra_ms = None
        self.cont = {"barras": 0, "formacoes": 0, "gatilhos_armados": 0, "toques": 0, "nao_alcancou": 0, "superacoes": 0, "entradas": 0, "bloqueados_posicao_aberta": 0,
                     "saidas_canal": 0, "saidas_stop": 0, "ticks": 0, "lacunas_no_gatilho": 0}
        self.ativo_desde_ms = None                                                     # início congelado: nenhum sinal antes

    def ev(self, tipo, t_ms, **kw): e = {"instancia": f"{self.at}-{self.tf}", "tipo": tipo, "t": str(pd.Timestamp(int(t_ms), unit="ms")), **kw}; self.eventos.append(e); return e

    # ── fechamento de barra (rates = DataFrame t,o,h,l,c das barras FECHADAS, a última é a que acabou de fechar) ──
    def fecha_barra(self, rates):
        b = len(rates) - 1; t_ab = int(pd.Timestamp(rates.t.iloc[b]).value // 10**6); fim = t_ab + self.dur_ms
        if self.ult_barra_ms is not None and t_ab <= self.ult_barra_ms: return
        self.ult_barra_ms = t_ab; self.cont["barras"] += 1
        H, L, C = (rates[k].values.astype(float) for k in "hlc"); ATR = RM.atr_wilder(rates.h, rates.l, rates.c)
        EH = pd.Series(H).ewm(span=20, adjust=False).mean().values; EL = pd.Series(L).ewm(span=20, adjust=False).mean().values
        if self.pend is not None and self.pend["fim_ms"] <= fim:                       # a barra do gatilho terminou sem superação
            g = self.pend; res = "toque sem superação" if g["tocou"] else "não alcançou"; self.cont["toques" if g["tocou"] else "nao_alcancou"] += 1
            self.sinais.append({**g, "resultado_gatilho": res}); self.ev("gatilho_expirado", fim, sinal=g["id"], resultado=res); self.pend = None
        if self.pos is not None and not self.pos["saida_pendente"]:
            s = self.pos["lado"]
            if (C[b] >= EL[b]) if s < 0 else (C[b] <= EH[b]): self.pos["saida_pendente"] = True; self.pos["saida_apos_ms"] = fim; self.ev("saida_canal_decidida", fim, id=self.pos["id"], c=C[b], canal=EL[b] if s < 0 else EH[b])
        if self.ativo_desde_ms is None or t_ab < self.ativo_desde_ms or not np.isfinite(ATR[b]): return
        hT, lT, cT = (np.rint(x / TICK).astype(np.int64) for x in (H, L, C))
        for s in (-1, 1):
            d = FO.detectar_venda(lT, hT, cT, ATR, b) if s < 0 else FO.detectar_venda(-hT, -lT, -cT, ATR, b)
            if d is None: continue
            chave = f"{s}|{rates.t.iloc[d['p']]}"
            if chave in self.usados: continue
            self.usados.add(chave); F = (d["F"] if s < 0 else -d["F"]) * TICK; ext = L[b] if s < 0 else H[b]; T = (tk(ext) + s) * TICK
            g = {"id": f"{self.at}-{self.tf}-{'V' if s < 0 else 'C'}-{pd.Timestamp(rates.t.iloc[b]):%Y%m%d%H%M}", "lado": s, "nivel": round(F, 2), "extremo": round(ext, 2), "T": round(T, 2), "T_t": tk(ext) + s,
                 "ext_t": tk(ext), "atr": float(ATR[b]), "ini_ms": fim, "fim_ms": fim + self.dur_ms, "tocou": False, "barra_rompimento": str(rates.t.iloc[b]), "fech_rompimento": float(C[b]),
                 "tentativas": [{"barra": str(rates.t.iloc[x["barra_idx"]]), "tipo": x["tipo"]} for x in d["tentativas"]], "caixa_inicio": str(rates.t.iloc[b - FO.CAIXA])}
            self.pend = g; self.cont["formacoes"] += 1; self.cont["gatilhos_armados"] += 1
            self.ev("gatilho_armado", fim, sinal=g["id"], lado=s, nivel=g["nivel"], extremo=g["extremo"], gatilho=g["T"], atr=round(g["atr"], 4)); break

    # ── tick ──
    def tick(self, t_ms, bid, ask, lacuna=False):
        self.cont["ticks"] += 1; p = self.pos
        if p is not None:
            s = p["lado"]
            if p["saida_pendente"] and t_ms >= p["saida_apos_ms"]: self._fechar(t_ms, ask if s < 0 else bid, "saída por sinal (fechamento de volta ao canal)", bid, ask, lacuna)
            elif (s < 0 and ask >= p["stop"]) or (s > 0 and bid <= p["stop"]): self._fechar(t_ms, ask if s < 0 else bid, "stop de proteção", bid, ask, lacuna)
            else:
                r0 = abs(p["entrada"] - p["stop"]); p["mfe"] = max(p["mfe"], ((ask if s < 0 else bid) - p["entrada"]) * s / r0)
                if lacuna: p["com_lacuna"] = True
        g = self.pend
        if g is None or t_ms < g["ini_ms"]: return
        if t_ms >= g["fim_ms"]: return                                                    # expiração tratada no fechamento da barra
        if lacuna: g["com_lacuna"] = True
        s = g["lado"]; b_t = tk(bid)
        if (b_t <= g["ext_t"]) if s < 0 else (b_t >= g["ext_t"]): g["tocou"] = True
        if not ((b_t <= g["T_t"]) if s < 0 else (b_t >= g["T_t"])): return
        self.pend = None; self.cont["superacoes"] += 1; px = bid if s < 0 else ask
        sig = {**g, "resultado_gatilho": "superou", "t_superacao": str(pd.Timestamp(int(t_ms), unit="ms")), "tau_ms": int(t_ms), "bid": bid, "ask": ask, "spread": round(ask - bid, 5),
               "lacuna_alem_do_gatilho": bool((b_t < g["T_t"]) if s < 0 else (b_t > g["T_t"])), "bid_menos_gatilho": round(bid - g["T"], 5)}
        if self.pos is not None:
            self.cont["bloqueados_posicao_aberta"] += 1; sig["decisao"] = "bloqueado: posição virtual aberta"; self.sinais.append(sig); self.ev("bloqueado_posicao_aberta", t_ms, sinal=g["id"]); return
        stop = px - s * K_STOP * g["atr"]; self.cont["entradas"] += 1
        if sig["lacuna_alem_do_gatilho"]: self.cont["lacunas_no_gatilho"] += 1
        self.pos = {"id": f"{self.at}-{self.tf}-{g['id'].split('-', 2)[2]}", "sinal": g["id"], "lado": s, "t_ent_ms": int(t_ms), "entrada": px, "stop": stop, "nivel": g["nivel"], "extremo": g["extremo"], "T": g["T"],
                    "bid_ent": bid, "ask_ent": ask, "spread_ent": ask - bid, "saida_pendente": False, "saida_apos_ms": None, "mfe": 0.0, "com_lacuna": bool(g.get("com_lacuna"))}
        sig["decisao"] = "entrou"; self.sinais.append(sig)
        self.ev("entrada_virtual", t_ms, id=self.pos["id"], lado=s, nivel=g["nivel"], gatilho=g["T"], bid=bid, ask=ask, preco=px, spread=round(ask - bid, 5), stop=round(stop, 2),
                cotacao_alem_do_gatilho=sig["lacuna_alem_do_gatilho"], modo="SOMBRA AO VIVO — nenhuma ordem")

    def _fechar(self, t_ms, px, motivo, bid, ask, lacuna):
        p = self.pos; s = p["lado"]; r0 = abs(p["entrada"] - p["stop"]); c = self.K; bruto = (px - p["entrada"]) * s
        spread_usd = (p["spread_ent"] if s > 0 else (ask - bid)) * c["contrato"]
        op = {**p, "t_sai_ms": int(t_ms), "saida": px, "bid_sai": bid, "ask_sai": ask, "motivo_saida": motivo, "R": bruto / r0 - 2 * c["com_lado"] / c["contrato"] / r0,
              "usd_1lote": bruto * c["contrato"] - 2 * c["com_lado"], "comissao_usd": 2 * c["com_lado"], "spread_pago_usd": spread_usd, "com_lacuna": bool(p["com_lacuna"] or lacuna),
              "horas": (t_ms - p["t_ent_ms"]) / 3_600_000}
        self.ops.append(op); self.pos = None; self.cont["saidas_stop" if motivo.startswith("stop") else "saidas_canal"] += 1
        self.ev("saida_virtual", t_ms, id=p["id"], motivo=motivo, bid=bid, ask=ask, preco=px, R=round(op["R"], 4), modo="SOMBRA AO VIVO — nenhuma ordem")

    def estado(self):
        return {"usados": sorted(self.usados), "pend": self.pend, "pos": self.pos, "ult_barra_ms": self.ult_barra_ms, "ativo_desde_ms": self.ativo_desde_ms, "cont": self.cont}

    def restaurar(self, d):
        self.usados = set(d["usados"]); self.pend, self.pos, self.ult_barra_ms, self.ativo_desde_ms = d["pend"], d["pos"], d["ult_barra_ms"], d["ativo_desde_ms"]; self.cont.update(d["cont"])
