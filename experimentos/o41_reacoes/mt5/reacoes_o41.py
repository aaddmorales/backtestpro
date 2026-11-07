"""reacoes-0.1 (ORDEM 041) — reações por nível (episódio toque → afastamento ≥ 0,5×ATR além da zona), qualificação para bloquear (≥ 2 reações
conhecidas na janela de 200 barras + elegível na V1-200), rompimento com TRAVESSIA da borda, e decisões dos Testes A e B. A memória (estrutura-0.1),
a janela (janela-0.1) e a Referência (V1-200) não mudam. Especificação: O41_especificacao_congelada.txt."""
import json, numpy as np, pandas as pd
import estrutura_o39 as ES, estrategia_o39 as ST, janela_o40 as JN
VERSAO = "reacoes-0.1 (ORDEM 041)"; D_ATR = 0.5; MIN_REACOES = 2; W = JN.W


class Reacoes:
    """acompanhamento causal barra a barra; estado serializável."""
    def __init__(self): self.s = {}                # id → {"ep": None|{...}, "lista": [...], "falhas": [...]}

    def _st(self, nid): return self.s.setdefault(nid, {"ep": None, "lista": [], "falhas": []})

    def _avaliar(self, n, st, k, t, h, l, c, atr, conhecida_n=None, t_conhecida=None):
        """avança o episódio do nível n com a barra (k = contagem da barra; t = fechamento). Devolve evento ou None."""
        b, tz = n["zona"]; sup = n["funcao"] == "suporte"; D = D_ATR * atr
        if st["ep"] is None:
            if (sup and l <= tz) or ((not sup) and h >= b): st["ep"] = {"inicio_n": k, "t_inicio": t, "funcao": n["funcao"]}
            else: return None
        ep = st["ep"]
        if (sup and c < b) or ((not sup) and c > tz):
            st["falhas"].append({**ep, "fim_n": k, "t_fim": t}); st["ep"] = None; return "falha"
        if (sup and c >= tz + D) or ((not sup) and c <= b - D):
            r = {**ep, "conhecida_n": conhecida_n or k, "t_conhecida": t_conhecida or t, "barra_afastamento_n": k, "afastamento_atr": round(((c - tz) if sup else (b - c)) / atr, 3), "funcao": n["funcao"]}
            st["lista"].append(r); st["ep"] = None; return "reacao"
        return None

    def atualizar(self, mem, evs, h, l, c, cp, atr, t):
        """chamar DEPOIS de mem.nova_barra para a mesma barra concluída."""
        if atr is None or not mem.niveis: return
        k = mem.n_barras; novos = {e["nivel"] for e in evs if e["evento"] == "confirmado"}
        B, T = mem._arr(); lo, hi = (min(l, cp), max(h, cp)) if cp is not None else (l, h)
        cand = set(np.nonzero((B <= hi) & (T >= lo))[0].tolist()); ids = {n["id"]: j for j, n in enumerate(mem.niveis)}
        cand |= {ids[i] for i, st in self.s.items() if st["ep"] is not None and i in ids}
        for j in sorted(cand):
            n = mem.niveis[j]
            if n["id"] in novos: continue
            self._avaliar(n, self._st(n["id"]), k, t, h, l, c, atr)
        for nid in novos:                                  # formação: episódio começa em i; avalia i+1 e i+2 (buffer); conhecida só em i+2
            n = mem.niveis[ids[nid]]; st = self._st(nid); st["ep"] = {"inicio_n": n["barra_extremo"], "t_inicio": n["t_extremo"], "funcao": n["funcao"]}
            for bb in mem.buf:                             # [i, t_ab, t_fecha, o, h, l, c, atr]
                if bb[0] <= n["barra_extremo"] or st["ep"] is None: continue
                self._avaliar(n, st, bb[0], bb[2], bb[4], bb[5], bb[6], bb[7] or atr, conhecida_n=k, t_conhecida=t)

    def na_janela(self, n, k, w=W):
        return [r for r in self.s.get(n["id"], {}).get("lista", []) if r["conhecida_n"] >= k - w + 1 and r["conhecida_n"] <= k and r["funcao"] == n["funcao"]]

    def para_json(self): return self.s
    @classmethod
    def de_json(cls, d): r = cls(); r.s = d; return r


def qualificado(mem, reac, n, fun, w=W):
    z = JN.zona_elegivel(n, mem.n_barras, w, fun)
    if z is None: return None, []
    rs = reac.na_janela(n, mem.n_barras, w)
    return (z if len(rs) >= MIN_REACOES else None), rs


def obstaculos_q(mem, reac, lado, E, atr, risco, w=W):
    """à frente: o nível QUALIFICADO mais próximo (bloqueia) e, para referência, o nível elegível mais próximo (qualificado ou não) e o seguinte."""
    fun = "suporte" if lado < 0 else "resistencia"; q, todos = [], []
    for n in mem.niveis:
        z = JN.zona_elegivel(n, mem.n_barras, w, fun)
        if z is None: continue
        b, t = z
        if lado < 0 and b < E: d = max(0.0, E - t)
        elif lado > 0 and t > E: d = max(0.0, b - E)
        else: continue
        rs = reac.na_janela(n, mem.n_barras, w); item = (d, n, z, rs); todos.append(item)
        if len(rs) >= MIN_REACOES: q.append(item)
    q.sort(key=lambda x: x[0]); todos.sort(key=lambda x: x[0]); lim = max(atr, risco)
    def fmt(it):
        if it is None: return None
        d, n, z, rs = it
        return {"nivel": n["id"], "zona_elegivel": z, "distancia": d, "dist_atr": d / atr, "dist_R": d / risco, "reacoes_na_janela": len(rs),
                "reacoes": [{"t_inicio": r["t_inicio"], "t_conhecida": r["t_conhecida"], "afastamento_atr": r["afastamento_atr"]} for r in rs[-4:]], "qualificado": len(rs) >= MIN_REACOES}
    out = {"bloqueador": fmt(q[0]) if q else None, "mais_proximo": fmt(todos[0]) if todos else None, "seguinte": fmt(todos[1]) if len(todos) > 1 else None,
           "seguinte_qualificado": fmt(q[1]) if len(q) > 1 else None, "limiar": lim}
    out["proximo"] = bool(q) and q[0][0] <= lim
    out["evitado_isolado"] = (not out["proximo"]) and bool(todos) and todos[0][0] <= lim       # o V1-200 bloquearia (nível próximo), mas ele não é qualificado
    return out


def decidir_q(modo, mem, reac, espera, c, c_ant, el, el_ant, eh, eh_ant, h, l, atr, t_barra, fecha, evs=None, w=W):
    regs = []; risco = 2 * atr; TICK = ST.TICK
    sinal = -1 if (c < el and c_ant >= el_ant) else (1 if (c > eh and c_ant <= eh_ant) else 0)
    if espera is not None:
        s = espera["lado"]; fun = "suporte" if s < 0 else "resistencia"
        if (s < 0 and c >= el) or (s > 0 and c <= eh):
            regs.append({"decisao": "espera_cancelada", "motivo": "fechamento de volta para dentro do canal: o sinal de média deixou de valer", "referencia": espera["nivel"], "sinal": espera["sinal"]}); return {"gat": None, "espera": None, "regs": regs}
        n = next((x for x in mem.niveis if x["id"] == espera["nivel"]), None); z, rs = qualificado(mem, reac, n, fun, w) if n else (None, [])
        if z is None:
            regs.append({"decisao": "espera_encerrada_inelegivel", "motivo": "o nível da espera deixou de ser qualificado (pivô ou reações fora da janela, ou mudou de estado/função): espera encerrada; o sinal original NÃO é liberado",
                         "referencia": espera["nivel"], "sinal": espera["sinal"]}); return {"gat": None, "espera": None, "regs": regs}
        alem = (c < z[0]) if s < 0 else (c > z[1]); dentro_antes = (c_ant >= z[0]) if s < 0 else (c_ant <= z[1])
        if alem and not dentro_antes:
            regs.append({"decisao": "espera_encerrada_borda", "motivo": "a borda da zona mudou (pivô saiu da janela) e o preço já estava além dela: NÃO é rompimento, nenhum gatilho; o nível deixou de estar à frente",
                         "referencia": espera["nivel"], "zona_elegivel": z, "c": c, "c_ant": c_ant, "sinal": espera["sinal"]}); return {"gat": None, "espera": None, "regs": regs}
        if alem:
            E = (l - TICK) if s < 0 else (h + TICK); ob = obstaculos_q(mem, reac, s, E, atr, risco, w)
            if modo == "A" and ob["proximo"]:
                regs.append({"decisao": "aguardando", "motivo": ST.MSG_ESPERA + " (segundo nível qualificado à frente após o rompimento)", "segundo_nivel": True, "obstaculo": ob, "sinal": espera["sinal"]})
                return {"gat": None, "espera": {"lado": s, "nivel": ob["bloqueador"]["nivel"], "sinal": espera["sinal"]}, "regs": regs}
            gat = {"lado": s, "nivel_gatilho": E, "atr": atr, "sinal": espera["sinal"], "referencia": t_barra, "tipo": "barra de rompimento estrutural (travessia da zona qualificada)", "t_sinal_fecha": fecha, "obstaculo": ob}
            regs.append({"decisao": "gatilho_armado", "motivo": "rompimento do nível qualificado com travessia: gatilho só na barra seguinte" + (" (Teste B: próximo nível só registrado, sem nova espera)" if modo == "B" else ""),
                         "condicao": f"fech {c:.2f} além de {z} (anterior {c_ant:.2f} dentro)", "resultado": True, "nivel_gatilho": E, "obstaculo": ob, "sinal": espera["sinal"],
                         "liberado_com_nivel_proximo": bool(modo == "B" and ob["proximo"])})
            return {"gat": gat, "espera": None, "regs": regs}
        return {"gat": None, "espera": espera, "regs": regs}
    if not sinal: return {"gat": None, "espera": None, "regs": regs}
    E = (l - TICK) if sinal < 0 else (h + TICK); ob = obstaculos_q(mem, reac, sinal, E, atr, risco, w)
    if ob["proximo"]:
        regs.append({"decisao": "aguardando", "motivo": ST.MSG_ESPERA if sinal < 0 else ST.MSG_ESPERA.replace("suporte", "resistência"), "condicao": "sinal de média", "obstaculo": ob, "sinal": t_barra})
        return {"gat": None, "espera": {"lado": sinal, "nivel": ob["bloqueador"]["nivel"], "sinal": t_barra}, "regs": regs}
    gat = {"lado": sinal, "nivel_gatilho": E, "atr": atr, "sinal": t_barra, "referencia": t_barra, "tipo": "barra do sinal de média", "t_sinal_fecha": fecha, "obstaculo": ob}
    regs.append({"decisao": "gatilho_armado", "motivo": "sinal de média sem nível QUALIFICADO próximo" + (" (bloqueio evitado: o nível próximo não tem 2 reações)" if ob["evitado_isolado"] else ""),
                 "condicao": f"fech {c:.2f} {'<' if sinal < 0 else '>'} EMA20 {'mín' if sinal < 0 else 'máx'}", "resultado": True, "nivel_gatilho": E, "obstaculo": ob, "sinal": t_barra,
                 "bloqueio_evitado_isolado": ob["evitado_isolado"]})
    return {"gat": gat, "espera": None, "regs": regs}


class ReplayRef(JN.ReplayJanela):
    """Referência = V1-200 inalterada + DIAGNÓSTICO: o gatilho por 'rompimento' veio de borda que mudou (fechamento anterior já além)?"""
    def decidir(self, i, H, L, C, evs):
        e = self.espera; z = None
        if e is not None:
            n = next((x for x in self.mem.niveis if x["id"] == e["nivel"]), None); z = JN.zona_elegivel(n, self.mem.n_barras, self.w, "suporte" if e["lado"] < 0 else "resistencia") if n else None
        k0 = len(self.reg); super().decidir(i, H, L, C, evs)
        for r in self.reg[k0:]:
            if r["decisao"] == "gatilho_armado" and str(r.get("motivo", "")).startswith("barra de rompimento") and z is not None:
                r["diag_rompimento_por_borda"] = bool((C[i - 1] < z[0]) if e["lado"] < 0 else (C[i - 1] > z[1]))


class ReplayQ(JN.ReplayJanela):
    """Testes A e B: mesma máquina de replay; memória + reações; decisão decidir_q."""
    def __init__(self, at, m15, m1, modo, **k):
        super().__init__(at, m15, m1, "V1-200-" + modo, **k); self.modo = modo; self.reac = Reacoes(); mem = self.mem; nb = mem.nova_barra; self._cp = None
        def nb2(t_ab, t_fecha, o, h, l, c):
            cp = mem.c_ant; ev = nb(t_ab, t_fecha, o, h, l, c); self.reac.atualizar(mem, ev, h, l, c, cp, mem.atr, t_fecha); return ev
        mem.nova_barra = nb2

    def decidir(self, i, H, L, C, evs):
        r = decidir_q(self.modo, self.mem, self.reac, self.espera, C[i], C[i - 1], self.EL[i], self.EL[i - 1], self.EH[i], self.EH[i - 1], H[i], L[i], self.ATR[i], str(self.m15.t.iloc[i]), int(self.f15[i]), evs, self.w)
        self.espera = r["espera"]
        if r["gat"] is not None: self.gat = r["gat"]
        for x in r["regs"]: self.R(i, **x)
