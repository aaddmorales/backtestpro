"""janela-0.1 (ORDEM 040) — elegibilidade operacional por JANELA MÓVEL de 200 barras sobre a memória ACUMULADA (estrutura-0.1) e decisão V1-200.
A memória não muda: só a consulta operacional filtra membros (pivôs) cujo extremo está nas últimas W barras fechadas e já confirmados.
Especificação: O40_especificacao_congelada.txt."""
import numpy as np
import estrutura_o39 as ES, estrategia_o39 as ST
VERSAO = "janela-0.1 (ORDEM 040)"; W = 200


def membros_elegiveis(n, n_atual, w=W):
    return [m for m in n["membros"] if m["barra_confirmacao"] <= n_atual and m["barra"] >= n_atual - w + 1]


def zona_elegivel(n, n_atual, w=W, funcao=None):
    """bordas só com os membros elegíveis; None se o nível não tem membro elegível ou não é relevante (O39: estado ≠ ROMPIMENTO CONFIRMADO)."""
    if n["estado"] == "ROMPIMENTO CONFIRMADO" or (funcao and n["funcao"] != funcao): return None
    ms = membros_elegiveis(n, n_atual, w)
    if not ms: return None
    if n["funcao"] == "suporte": return [min(m["extremo"] for m in ms), max(m["extremo"] + ES.K_ZONA * m["atr"] for m in ms)]
    return [min(m["extremo"] - ES.K_ZONA * m["atr"] for m in ms), max(m["extremo"] for m in ms)]


def obstaculos(mem, lado, E, atr, risco, w=W):
    """nível ELEGÍVEL à frente (venda: suporte abaixo de E; compra: resistência acima) + o SEGUINTE; distâncias em preço, ATR e risco."""
    fun = "suporte" if lado < 0 else "resistencia"; cand = []
    for n in mem.niveis:
        z = zona_elegivel(n, mem.n_barras, w, fun)
        if z is None: continue
        b, t = z
        if lado < 0 and b < E: d = max(0.0, E - t)
        elif lado > 0 and t > E: d = max(0.0, b - E)
        else: continue
        cand.append((d, n, z))
    if not cand: return None
    cand.sort(key=lambda x: x[0]); d, n, z = cand[0]; lim = max(1.0 * atr, risco)
    seg = None if len(cand) < 2 else {"nivel": cand[1][1]["id"], "zona_elegivel": cand[1][2], "distancia": cand[1][0], "dist_atr": cand[1][0] / atr}
    return {"nivel": n["id"], "funcao": n["funcao"], "zona_elegivel": z, "zona_acumulada": list(n["zona"]), "estado": n["estado"], "distancia": d, "dist_atr": d / atr, "dist_risco": d / risco,
            "limiar": lim, "proximo": d <= lim, "membros_elegiveis": len(membros_elegiveis(n, mem.n_barras, w)), "membros_total": len(n["membros"]), "seguinte": seg, "janela_barras": w}


def contar(mem, w=W):
    """(níveis relevantes na memória acumulada, níveis elegíveis na janela) no fechamento atual."""
    lim = mem.n_barras - w + 1; rel = [n for n in mem.niveis if n["estado"] != "ROMPIMENTO CONFIRMADO"]
    return len(rel), sum(1 for n in rel if n["membros"][-1]["barra"] >= lim)      # membros entram em ordem cronológica: o último tem o extremo mais recente


def decidir_janela(mem, espera, c, c_ant, el, el_ant, eh, eh_ant, h, l, atr, t_barra, fecha, evs=None, w=W):
    """V1-200: mesma lógica da V1 (O39), com obstáculo e espera avaliados SÓ na janela; a espera termina se o nível perde a elegibilidade (sem retroatividade)."""
    regs = []; risco = 2 * atr; TICK = ST.TICK
    sinal = -1 if (c < el and c_ant >= el_ant) else (1 if (c > eh and c_ant <= eh_ant) else 0)
    if espera is not None:
        s = espera["lado"]
        if (s < 0 and c >= el) or (s > 0 and c <= eh):
            regs.append({"decisao": "espera_cancelada", "motivo": "fechamento de volta para dentro do canal: o sinal de média deixou de valer", "referencia": espera["nivel"]}); return {"gat": None, "espera": None, "regs": regs}
        n = next((x for x in mem.niveis if x["id"] == espera["nivel"]), None); z = None if n is None else zona_elegivel(n, mem.n_barras, w, "suporte" if s < 0 else "resistencia")
        if z is None:
            regs.append({"decisao": "espera_encerrada_inelegivel", "motivo": "o nível que sustentava a espera deixou de ser elegível (saiu da janela de 200 barras ou mudou de estado/função): espera encerrada; o sinal original NÃO é liberado (o gatilho dele já expirou)",
                         "referencia": espera["nivel"], "sinal": espera["sinal"]})
            return {"gat": None, "espera": None, "regs": regs}
        if (s < 0 and c < z[0]) or (s > 0 and c > z[1]):
            E = (l - TICK) if s < 0 else (h + TICK); ob = obstaculos(mem, s, E, atr, risco, w)
            if ob and ob["proximo"]:
                regs.append({"decisao": "aguardando", "motivo": ST.MSG_ESPERA + " (novo obstáculo à frente após o rompimento)", "segundo_nivel": True, "obstaculo": ob})
                return {"gat": None, "espera": {"lado": s, "nivel": ob["nivel"], "sinal": espera["sinal"]}, "regs": regs}
            gat = {"lado": s, "nivel_gatilho": E, "atr": atr, "sinal": espera["sinal"], "referencia": t_barra, "tipo": "barra de rompimento estrutural (zona elegível)", "t_sinal_fecha": fecha, "obstaculo": ob}
            regs.append({"decisao": "gatilho_armado", "motivo": "barra de rompimento da zona ELEGÍVEL concluída: gatilho só na barra seguinte", "condicao": f"fech {c:.2f} além de {z}", "resultado": True, "nivel_gatilho": E, "obstaculo": ob})
            return {"gat": gat, "espera": None, "regs": regs}
        return {"gat": None, "espera": espera, "regs": regs}
    if not sinal: return {"gat": None, "espera": None, "regs": regs}
    E = (l - TICK) if sinal < 0 else (h + TICK); ob = obstaculos(mem, sinal, E, atr, risco, w)
    if ob and ob["proximo"]:
        regs.append({"decisao": "aguardando", "motivo": ST.MSG_ESPERA if sinal < 0 else ST.MSG_ESPERA.replace("suporte", "resistência"), "condicao": "sinal de média", "obstaculo": ob})
        return {"gat": None, "espera": {"lado": sinal, "nivel": ob["nivel"], "sinal": t_barra}, "regs": regs}
    gat = {"lado": sinal, "nivel_gatilho": E, "atr": atr, "sinal": t_barra, "referencia": t_barra, "tipo": "barra do sinal de média", "t_sinal_fecha": fecha, "obstaculo": ob}
    regs.append({"decisao": "gatilho_armado", "motivo": "sinal de média sem obstáculo ELEGÍVEL próximo", "condicao": f"fech {c:.2f} {'<' if sinal < 0 else '>'} EMA20 {'mín' if sinal < 0 else 'máx'}", "resultado": True,
                 "nivel_gatilho": E, "obstaculo": ob})
    return {"gat": gat, "espera": None, "regs": regs}


class ReplayJanela(ST.Replay):
    """V1-200: o mesmo motor de replay da O39 (gatilho, stop, saída, custos); só a decisão troca para decidir_janela. Conta níveis por barra."""
    def __init__(self, *a, w=W, **k):
        super().__init__(*a, **k); self.w = w; self.contagem = []; mem = self.mem; orig = mem.nova_barra
        def nb(*x):
            ev = orig(*x); r, e = contar(mem, self.w); self.contagem.append((mem.n_barras, r, e)); return ev
        mem.nova_barra = nb

    def decidir(self, i, H, L, C, evs):
        r = decidir_janela(self.mem, self.espera, C[i], C[i - 1], self.EL[i], self.EL[i - 1], self.EH[i], self.EH[i - 1], H[i], L[i], self.ATR[i], str(self.m15.t.iloc[i]), int(self.f15[i]), evs, self.w)
        self.espera = r["espera"]
        if r["gat"] is not None: self.gat = r["gat"]
        for x in r["regs"]: self.R(i, **x)
