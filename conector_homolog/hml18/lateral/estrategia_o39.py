"""ESTR-EMA-M15-0.1 (ORDEM 039) — replay cronológico V0 × V1 (spec O39 §5): sinal de média (canal EMA20 máx/mín), gatilho de superação ≥ 1 tick só na
barra seguinte (intrabar em M1, bid), V1 com memória estrutural (estrutura-0.1) e prioridade do obstáculo próximo. Mesma gestão nas duas (stop 2×ATR14
Wilder; saída no fechamento M15 de volta ao canal). Uso: python estrategia_o39.py ATIVO SAIDA_DIR"""
import os, sys, glob, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrutura_o39 as ES, romp_m15 as RM
DADOS = "/home/claude/r005/lm014/dados/csv_limpo"; MIN = 60 * 10**9; M15 = 15 * MIN; TICK = 0.01; PT = 0.01
CUSTO = {"XAUUSD": {"contrato": 100.0, "com_lado": 3.50}, "BTCUSD": {"contrato": 1.0, "com_lado": 0.0}}
VERSAO = "ESTR-EMA-M15-0.1"; MSG_ESPERA = "Sinal local identificado; entrada aguardando rompimento e confirmação do suporte."


def ler(at, tf):
    f = glob.glob(f"{DADOS}/{at}_{tf}_*.csv")[0]; d = pd.read_csv(f, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
    d["t"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S"); return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c", "spread"]].reset_index(drop=True)


class Replay:
    def __init__(self, at, m15, m1, versao, mem=None):
        self.at, self.v = at, versao; self.m15, self.m1 = m15, m1; self.K = CUSTO[at]
        self.t15 = m15.t.values.astype("datetime64[ns]").astype(np.int64); self.f15 = self.t15 + M15
        self.t1 = m1.t.values.astype("datetime64[ns]").astype(np.int64); self.o1, self.h1, self.l1 = (m1[k].values.astype(float) for k in "ohl"); self.sp = m1.spread.values * PT
        self.EH = pd.Series(m15.h).ewm(span=20, adjust=False).mean().values; self.EL = pd.Series(m15.l).ewm(span=20, adjust=False).mean().values
        self.ATR = RM.atr_wilder(m15.h, m15.l, m15.c); self.mem = mem or ES.Memoria(at, "M15", TICK)
        self.ops, self.reg = [], []; self.pos = None; self.gat = None; self.espera = None

    def R(self, i, decisao, **kw): self.reg.append({"versao": self.v, "ativo": self.at, "tf": "M15", "barra": str(self.m15.t.iloc[i]), "decisao": decisao, **kw})

    def m1_da_barra(self, i): return int(np.searchsorted(self.t1, self.t15[i])), int(np.searchsorted(self.t1, self.f15[i]))

    def checar_stop(self, a, b):
        p = self.pos
        for j in range(a, b):
            if (p["lado"] > 0 and self.l1[j] <= p["stop"]) or (p["lado"] < 0 and self.h1[j] + self.sp[j] >= p["stop"]):
                px = min(p["stop"], self.o1[j]) if p["lado"] > 0 else max(p["stop"], self.o1[j] + self.sp[j])
                if j == p["j_ent"]: px = p["stop"]                                   # minuto da entrada: ordem desconhecida → stop (conservador)
                self.fechar(j, px, "stop de proteção"); return True
        return False

    def fechar(self, j, px, motivo):
        p = self.pos; r0 = abs(p["entrada"] - p["stop"]); bruto = (px - p["entrada"]) * p["lado"]; c = self.K
        self.ops.append({**p, "j_sai": j, "t_sai": int(self.t1[j]), "saida": px, "motivo_saida": motivo, "R": bruto / r0 - 2 * c["com_lado"] / c["contrato"] / r0,
                         "usd_1lote": bruto * c["contrato"] - 2 * c["com_lado"], "custo_com_usd": 2 * c["com_lado"]}); self.pos = None

    def rodar(self, i0=25, i1=None):
        m15 = self.m15; O, H, L, C = (m15[k].values.astype(float) for k in "ohlc"); i1 = i1 or len(m15)
        for i in range(i0, i1):
            a, b = self.m1_da_barra(i); saiu = False
            if self.pos is not None and self.checar_stop(a, b): saiu = True
            # gatilho armado para ESTA barra (só ela)
            g, self.gat = self.gat, None
            if g is not None and self.pos is None:
                T = g["nivel_gatilho"]; s = g["lado"]
                hit = np.nonzero((self.l1[a:b] <= T + 1e-9) if s < 0 else (self.h1[a:b] >= T - 1e-9))[0]
                if len(hit):
                    j = a + int(hit[0]); bid = min(T, self.o1[j]) if s < 0 else max(T, self.o1[j]); px = bid if s < 0 else bid + self.sp[j]
                    atr = g["atr"]; self.pos = {"versao": self.v, "id": f"{self.v}-{self.at}-{g['sinal']}", "lado": s, "sinal": g["sinal"], "referencia": g["referencia"], "tipo_referencia": g["tipo"],
                                                "t_sinal_fecha": g["t_sinal_fecha"], "j_ent": j, "t_ent": int(self.t1[j]), "entrada": px, "bid_gatilho": T, "spread_ent": self.sp[j], "stop": px - s * 2 * atr, "atr": atr,
                                                "obstaculo": g.get("obstaculo")}
                    self.R(i, "entrada", motivo=f"superação de {'mínima' if s < 0 else 'máxima'} da barra de referência ({g['tipo']}) por ≥ 1 tick", condicao=f"bid {'≤' if s < 0 else '≥'} {T:.2f}", resultado=True,
                           id=self.pos["id"], t_m1=str(pd.Timestamp(int(self.t1[j]))), preco=px)
                    self.checar_stop(j, b)
                else:
                    self.R(i, "gatilho_expirado", motivo="a barra seguinte terminou sem superar o extremo (igualar não confirma)", condicao=f"bid nunca {'≤' if s < 0 else '≥'} {T:.2f}", resultado=False, referencia=g["referencia"])
            # fechamento da barra i: memória, saída por sinal, novos sinais
            evs = self.mem.nova_barra(str(m15.t.iloc[i]), str(pd.Timestamp(int(self.f15[i]))), O[i], H[i], L[i], C[i])
            if self.pos is not None:
                s = self.pos["lado"]; dentro = (C[i] >= self.EL[i]) if s < 0 else (C[i] <= self.EH[i])
                if dentro and self.t15[i] >= self.pos["t_sinal_fecha"]:
                    j = b if b < len(self.t1) else None
                    if j is None: break
                    px = self.o1[j] + self.sp[j] if s < 0 else self.o1[j]; self.fechar(j, px, "saída por sinal (fechamento de volta ao canal)"); saiu = True
            if self.pos is not None or saiu or not np.isfinite(self.ATR[i]): self.espera = None if self.pos is not None else self.espera; continue
            self.decidir(i, H, L, C, evs)

    def decidir(self, i, H, L, C, evs):
        r = decidir_puro(self.v, self.mem, self.espera, C[i], C[i - 1], self.EL[i], self.EL[i - 1], self.EH[i], self.EH[i - 1], H[i], L[i], self.ATR[i], str(self.m15.t.iloc[i]), int(self.f15[i]), evs)
        self.espera = r["espera"]
        if r["gat"] is not None: self.gat = r["gat"]
        for x in r["regs"]: self.R(i, **x)


def decidir_puro(v, mem, espera, c, c_ant, el, el_ant, eh, eh_ant, h, l, atr, t_barra, fecha, evs):
    """decisão no fechamento de UMA barra M15 concluída (spec O39 §5). Função pura: a MESMA no replay e no leitor sombra.
    Devolve {"gat": gatilho para a barra seguinte ou None, "espera": estado de espera V1, "regs": registros}."""
    regs = []; risco = 2 * atr
    sinal = -1 if (c < el and c_ant >= el_ant) else (1 if (c > eh and c_ant <= eh_ant) else 0)
    if v == "V1" and espera is not None:
        e = espera; s = e["lado"]
        if (s < 0 and c >= el) or (s > 0 and c <= eh):
            regs.append({"decisao": "espera_cancelada", "motivo": "fechamento de volta para dentro do canal: o sinal de média deixou de valer", "referencia": e["nivel"]}); return {"gat": None, "espera": None, "regs": regs}
        br = [x for x in evs if x["evento"] == "rompimento_pendente" and x["nivel"] == e["nivel"]]
        if br:
            E = (l - TICK) if s < 0 else (h + TICK); ob = mem.obstaculo(s, E, atr, risco)
            if ob and ob["proximo"]:
                regs.append({"decisao": "aguardando", "motivo": MSG_ESPERA + " (novo obstáculo à frente após o rompimento)", "obstaculo": ob}); return {"gat": None, "espera": {"lado": s, "nivel": ob["nivel"], "sinal": e["sinal"]}, "regs": regs}
            gat = {"lado": s, "nivel_gatilho": E, "atr": atr, "sinal": e["sinal"], "referencia": t_barra, "tipo": "barra de rompimento estrutural", "t_sinal_fecha": fecha, "obstaculo": e.get("ob")}
            regs.append({"decisao": "gatilho_armado", "motivo": "barra de rompimento estrutural concluída: gatilho só na barra seguinte", "condicao": f"fech {c:.2f} além da zona {e['nivel']}", "resultado": True, "nivel_gatilho": E})
            return {"gat": gat, "espera": None, "regs": regs}
        return {"gat": None, "espera": espera, "regs": regs}
    if not sinal: return {"gat": None, "espera": espera, "regs": regs}
    E = (l - TICK) if sinal < 0 else (h + TICK); ob = mem.obstaculo(sinal, E, atr, risco) if v == "V1" else None
    if v == "V1" and ob and ob["proximo"]:
        regs.append({"decisao": "aguardando", "motivo": MSG_ESPERA if sinal < 0 else MSG_ESPERA.replace("suporte", "resistência"), "condicao": "sinal de média", "obstaculo": ob})
        return {"gat": None, "espera": {"lado": sinal, "nivel": ob["nivel"], "sinal": t_barra, "ob": ob}, "regs": regs}
    gat = {"lado": sinal, "nivel_gatilho": E, "atr": atr, "sinal": t_barra, "referencia": t_barra, "tipo": "barra do sinal de média", "t_sinal_fecha": fecha, "obstaculo": ob}
    regs.append({"decisao": "gatilho_armado", "motivo": "sinal de média" + (" sem obstáculo próximo" if v == "V1" else ""), "condicao": f"fech {c:.2f} {'<' if sinal < 0 else '>'} EMA20 {'mín' if sinal < 0 else 'máx'}",
                 "resultado": True, "nivel_gatilho": E, "obstaculo": ob})
    return {"gat": gat, "espera": espera, "regs": regs}


def metricas(o, eq=None):
    if not len(o): return {"n": 0}
    g, p = o.usd_1lote[o.usd_1lote > 0], o.usd_1lote[o.usd_1lote <= 0]
    m = {"n": int(len(o)), "liquido_usd_1lote": round(float(o.usd_1lote.sum()), 2), "R_total": round(float(o.R.sum()), 2), "expectativa_R": round(float(o.R.mean()), 4), "acerto": round(float((o.R > 0).mean()), 4),
         "fator_lucro_usd": round(float(g.sum() / -p.sum()), 3) if p.sum() < 0 else None, "comissao_usd": round(float(o.custo_com_usd.sum()), 2), "saidas": o.motivo_saida.value_counts().to_dict()}
    rng = np.random.default_rng(1); d = pd.Series(o.R.values).groupby(pd.to_datetime(o.t_ent).dt.floor("D").values).sum().values
    if len(d) > 5: bs = [d[rng.integers(0, len(d), len(d))].sum() / len(o) for _ in range(2000)]; m["IC95_expectativa_R"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
    if eq is not None: m["drawdown_mtm_usd_1lote"] = round(float((eq - np.maximum.accumulate(eq)).min()), 2)
    return m


def curva(ops, m1, K):
    c1 = m1.c.values.astype(float); sp = m1.spread.values * PT; eq = np.zeros(len(c1))
    for r in ops.itertuples():
        a, b = r.j_ent, r.j_sai; px = c1[a:b] if r.lado > 0 else c1[a:b] + sp[a:b]; eq[a:b] += (px - r.entrada) * r.lado * K["contrato"] - K["com_lado"]; eq[b:] += r.usd_1lote
    return eq


def main():
    at, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); m15, m1 = ler(at, "M15"), ler(at, "M1"); R = {"ativo": at, "versao": VERSAO, "memoria": ES.VERSAO}; OPS = {}
    for v in ("V0", "V1"):
        t0 = time.time(); rp = Replay(at, m15, m1, v); rp.rodar(); o = pd.DataFrame(rp.ops); OPS[v] = o; eq = curva(o, m1, CUSTO[at]) if len(o) else None
        oos = pd.to_datetime(o.t_ent) >= "2026-05-01"; cut = int(np.searchsorted(m1.t.values, np.datetime64("2026-05-01")))
        R[v] = {"geral": metricas(o, eq), "desenvolvimento": metricas(o[~oos], eq[:cut] if eq is not None else None), "fora_da_amostra": metricas(o[oos], (eq[cut:] - eq[cut]) if eq is not None else None),
                "compras": metricas(o[o.lado > 0]), "vendas": metricas(o[o.lado < 0]), "decisoes": pd.Series([x["decisao"] for x in rp.reg]).value_counts().to_dict(), "segundos": round(time.time() - t0, 1)}
        o.to_csv(f"{out}/O39_{at}_{v}_operacoes.csv", index=False, sep=";"); pd.DataFrame(rp.reg).to_csv(f"{out}/O39_{at}_{v}_decisoes.csv.gz", index=False, sep=";")
        if v == "V1": rp.mem.salvar(f"{out}/O39_{at}_memoria_M15.json"); R["niveis"] = {"total": len(rp.mem.niveis), "por_estado": pd.Series([n["estado"] for n in rp.mem.niveis]).value_counts().to_dict(),
                                                                                            "agrupados_duplos": sum(len(n["membros"]) > 1 for n in rp.mem.niveis), "troca_funcao": sum(bool(n["evidencias_troca"]) for n in rp.mem.niveis)}
    a, b = OPS["V0"], OPS["V1"]; sv = set(b.sinal); ev = a[~a.sinal.isin(sv)]; com = a.merge(b[["sinal", "t_ent", "R"]], on="sinal", suffixes=("_v0", "_v1"))
    R["comparacao"] = {"entradas_V0_evitadas_por_V1": int(len(ev)), "vencedoras_descartadas": int((ev.R > 0).sum()), "R_das_evitadas": round(float(ev.R.sum()), 2),
                       "entradas_V1_sem_par_em_V0": int((~b.sinal.isin(set(a.sinal))).sum()), "mesmo_sinal_nas_duas": int(len(com)),
                       "atraso_adicional_min_mediana_quando_V1_entrou_depois": round(float(((com.t_ent_v1 - com.t_ent_v0) / 6e10)[com.t_ent_v1 > com.t_ent_v0].median()), 1) if (com.t_ent_v1 > com.t_ent_v0).any() else 0,
                       "sinais_em_que_V1_entrou_depois": int((com.t_ent_v1 > com.t_ent_v0).sum())}
    json.dump(R, open(f"{out}/O39_{at}_resultado.json", "w"), ensure_ascii=False, indent=1, default=str); print(json.dumps(R, ensure_ascii=False, indent=1, default=str)[:3500])


if __name__ == "__main__": main()


def salvar_estado(rp, f_mem, f_est, i_prox):
    """persistência para o leitor sombra/reinício: memória + gatilho + espera + posição + próxima barra."""
    rp.mem.salvar(f_mem); json.dump({"gat": rp.gat, "espera": rp.espera, "pos": rp.pos, "i_prox": i_prox, "ops": rp.ops, "reg": rp.reg}, open(f_est, "w"), default=str)


def carregar_estado(rp, f_mem, f_est):
    rp.mem = ES.Memoria.carregar(f_mem); d = json.load(open(f_est)); rp.gat, rp.espera, rp.pos, rp.ops, rp.reg = d["gat"], d["espera"], d["pos"], d["ops"], d["reg"]
    return d["i_prox"]
