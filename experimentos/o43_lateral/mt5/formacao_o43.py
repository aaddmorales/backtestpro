"""lateral-m1m5-0.1 (ORDEM 043) — rompimento da LATERALIZAÇÃO no M15 com confirmação IMEDIATA em M1/M5 (só no instante da 1ª superação).
Especificação congelada: O43_especificacao_congelada.txt (sha 2aeb198d…). Experimental; replay e sombra; nenhuma ordem.
Motor incremental por barra M15 (o MESMO código no replay contínuo, na simulação isolada por sinal e no leitor sombra):
  barra(i): (1) posições virtuais abertas: saída pendente / stop nas M1 da barra i; (2) sinal pendente da barra i−1: gatilho na barra i (e só nela),
            leitura M1/M5 no instante τ, decisão R0/R1/R2; (3) fechamento M15: saída pelo canal EMA20; (4) memória estrutural; (5) detecção da formação em i.
Preços comparados em TICKS inteiros (0,01) para que igualar ≠ superar sem erro de ponto flutuante."""
import numpy as np, pandas as pd
import estrutura_o39 as ES, estrategia_o39 as ST, janela_o40 as JN, leitura_o42 as LQ
VERSAO = "lateral-m1m5-0.1 (ORDEM 043)"; MIN = 60 * 10**9; M15 = 15 * MIN; TICK = 0.01
CAIXA = 12; K_AMP = 3.0; K_STOP = 2.0                                  # [P] congelados
REGRAS = ("R0", "R1", "R2")
NOME_REGRA = {"R0": "sem M1/M5", "R1": "estrita O43 (M1 confirma e M5 confirma)", "R2": "variante O42 (M1 confirma e M5 não contrária)"}


def tk(x): return np.rint(np.asarray(x, dtype=float) / TICK).astype(np.int64)


# ─────────────────────────── formação (só M15 concluídas) ───────────────────────────
def detectar_venda(l, h, c, ATR, b):
    """sobre séries (l,h,c) em ticks no sentido VENDA (compra usa o espelho −h,−l,−c). Devolve dict ou None. Usa só barras ≤ b."""
    if b < CAIXA + 2 or not np.isfinite(ATR[b - 1]): return None
    amp = int(h[b - CAIXA:b].max() - l[b - CAIXA:b].min())
    if amp * TICK > K_AMP * ATR[b - 1] + 1e-12: return None
    p = None
    for q in range(b - 3, b - CAIXA - 1, -1):                                           # pivô mais recente, confirmado até b−1, dentro de [b−12, b−3]
        if q - 2 >= 0 and l[q] < min(l[q - 2], l[q - 1], l[q + 1], l[q + 2]): p = q; break
    if p is None: return None
    F = int(l[p])
    if not c[b] < F: return None
    tent, acima = [], 0
    for q in range(p + 1, b):
        if c[q] >= F:
            acima += 1
            if l[q] < F: tent.append({"barra_idx": q, "tipo": 1, "descricao": "pavio abaixo do fundo e fechamento de volta (≥ fundo)"})
        else:
            if q + 1 <= b - 1 and not (l[q + 1] <= l[q] - 1) and c[q + 1] >= F:
                tent.append({"barra_idx": q, "tipo": 2, "descricao": "fechamento abaixo não confirmado (barra seguinte não superou a mínima e fechou ≥ fundo)"})
            else: return None
    if not tent: return None
    return {"p": p, "F": F, "tentativas": tent, "barras_acima": acima, "amp_caixa_atr": amp * TICK / ATR[b - 1]}


class Motor:
    def __init__(self, at, m15, m1, mem=None):
        self.at, self.m15, self.m1 = at, m15, m1; self.K = ST.CUSTO[at]
        self.t15 = m15.t.values.astype("datetime64[ns]").astype(np.int64); self.f15 = self.t15 + M15
        self.O, self.H, self.L_, self.C = (m15[k].values.astype(float) for k in "ohlc"); self.hT, self.lT, self.cT = tk(self.H), tk(self.L_), tk(self.C)
        self.t1 = m1.t.values.astype("datetime64[ns]").astype(np.int64); self.o1, self.h1, self.l1, self.c1 = (m1[k].values.astype(float) for k in "ohlc")
        self.h1T, self.l1T, self.o1T = tk(self.h1), tk(self.l1), tk(self.o1); self.sp = m1.spread.values * ST.PT
        self.EH = pd.Series(self.H).ewm(span=20, adjust=False).mean().values; self.EL = pd.Series(self.L_).ewm(span=20, adjust=False).mean().values
        self.ATR = ST.RM.atr_wilder(m15.h, m15.l, m15.c); self.LM = LQ.M1M5(m1); self.mem = mem or ES.Memoria(at, "M15", TICK)
        self.usados = set(); self.pend = None; self.pos = {r: None for r in REGRAS}; self.ult_sai = {r: -1 for r in REGRAS}
        self.ops = {r: [] for r in REGRAS}; self.sinais = []; self.reg = []

    def R(self, i, decisao, **kw): self.reg.append({"versao": VERSAO, "ativo": self.at, "barra": str(self.m15.t.iloc[i]), "decisao": decisao, **kw})
    def m1_da_barra(self, i): return int(np.searchsorted(self.t1, self.t15[i])), int(np.searchsorted(self.t1, self.f15[i]))
    def ts(self, x): return str(pd.Timestamp(int(x)))

    # ── detecção ──
    def detectar(self, i):
        out = []
        for s in (-1, 1):
            d = detectar_venda(self.lT, self.hT, self.cT, self.ATR, i) if s < 0 else detectar_venda(-self.hT, -self.lT, -self.cT, self.ATR, i)
            if d is None: continue
            chave = f"{s}|{self.t15[d['p']]}"
            if chave in self.usados: continue
            self.usados.add(chave); F = d["F"] if s < 0 else -d["F"]
            ext = self.L_[i] if s < 0 else self.H[i]; atr = float(self.ATR[i])
            ob = JN.obstaculos(self.mem, s, ext, atr, K_STOP * atr)
            out.append({"id": f"{self.at}-{'V' if s < 0 else 'C'}-{self.m15.t.iloc[i]:%Y%m%d%H%M}", "lado": s, "t_rompimento": int(self.t15[i]), "barra_rompimento": str(self.m15.t.iloc[i]),
                        "referencia": F * TICK, "t_pivo": str(self.m15.t.iloc[d["p"]]), "caixa_inicio": str(self.m15.t.iloc[i - CAIXA]), "amp_caixa_atr": round(d["amp_caixa_atr"], 3),
                        "barras_acima": d["barras_acima"], "tentativas": [{"barra": str(self.m15.t.iloc[x["barra_idx"]]), "tipo": x["tipo"], "descricao": x["descricao"]} for x in d["tentativas"]],
                        "n_tent_tipo1": sum(x["tipo"] == 1 for x in d["tentativas"]), "n_tent_tipo2": sum(x["tipo"] == 2 for x in d["tentativas"]),
                        "extremo_rompimento": ext, "fech_rompimento": self.C[i], "amp_rompimento_atr": round((self.H[i] - self.L_[i]) / atr, 3), "atr": atr,
                        "prox_nivel_dist_atr": None if ob is None else round(ob["dist_atr"], 3), "prox_nivel_id": None if ob is None else ob["nivel"],
                        "prox_nivel_zona": None if ob is None else [round(z, 2) for z in ob["zona_elegivel"]]})
        if len(out) == 2: out = []                                                       # (não ocorre: fechar abaixo do fundo e acima do topo da mesma caixa)
        return out[0] if out else None

    # ── leitura no instante τ ──
    def leitura(self, j, s):
        tau = int(self.t1[j]); k = j - 1; LM = self.LM
        if k < 6: return None
        mk = LM.marcas(k, s); Lr = LM.leitura(k, s, tau)
        av, rj, pc = mk["avanco"], mk["rejeicao"], mk["pressao_contraria"]
        m1 = "CONFIRMA" if (av and not rj and not pc) else ("CONTRARIA" if (pc or (rj and not av)) else "NEUTRO")
        n5 = LM.m5_fechadas(tau)
        if n5 >= 2:
            q = n5 - 1; o5, c5, cp = LM.o5[q], LM.c5[q], LM.c5[q - 1]; fav = lambda x: s * x
            m5 = "CONFIRMA" if (fav(c5 - o5) > 0 and fav(c5 - cp) > 0) else ("CONTRARIA" if (fav(c5 - o5) < 0 and fav(c5 - cp) < 0) else "NEUTRO")
            m5_o42_contraria = bool(fav(c5 - o5) < 0); m5_fim = int(LM.t5_fim[q])
        else: m5, m5_o42_contraria, m5_fim = "SEM DADOS", True, None
        return {"tau": self.ts(tau), "m1_ultima_fechada": self.ts(self.t1[k]), "m1_defasagem_min": round((tau - int(self.t1[k]) - MIN) / MIN, 1), "m1_estado": m1, "m1_marcas": mk,
                "m1_marcas_15": Lr["m1_marcas_15"], "m5_estado": m5, "m5_o42_contraria": m5_o42_contraria, "m5_3": Lr["m5_3"],
                "m5_ultima_fim": None if m5_fim is None else self.ts(m5_fim), "m5_defasagem_min": None if m5_fim is None else round((tau - m5_fim) / MIN, 1)}

    @staticmethod
    def decide(regra, Lr):
        if regra == "R0": return True
        if Lr is None: return False
        if regra == "R1": return Lr["m1_estado"] == "CONFIRMA" and Lr["m5_estado"] == "CONFIRMA"
        return Lr["m1_estado"] == "CONFIRMA" and not Lr["m5_o42_contraria"]

    # ── posição virtual (mesma gestão para todas as regras) ──
    def nova_pos(self, g, j, regra):
        s = g["lado"]; T = g["T"]; o = self.o1[j]
        bid = min(T, o) if s < 0 else max(T, o); px = bid if s < 0 else bid + self.sp[j]
        return {"regra": regra, "id": f"{regra}-{g['id']}", "sinal": g["id"], "lado": s, "j_ent": j, "t_ent": int(self.t1[j]), "entrada": px, "stop": px - s * K_STOP * g["atr"], "atr": g["atr"],
                "extremo_rompimento": g["extremo_rompimento"], "lacuna_na_abertura": bool(self.o1T[j] < g["T_t"] if s < 0 else self.o1T[j] > g["T_t"]), "saida_pendente": False, "mfe": 0.0, "stop_na_m1_entrada": False}

    def fechar(self, p, j, px, motivo):
        r0 = abs(p["entrada"] - p["stop"]); bruto = (px - p["entrada"]) * p["lado"]; c = self.K
        return {**p, "j_sai": j, "t_sai": int(self.t1[j]), "saida": px, "motivo_saida": motivo, "R": bruto / r0 - 2 * c["com_lado"] / c["contrato"] / r0,
                "usd_1lote": bruto * c["contrato"] - 2 * c["com_lado"], "custo_com_usd": 2 * c["com_lado"], "ambiguo": bool(p["lacuna_na_abertura"] or p["stop_na_m1_entrada"])}

    def intrabarra(self, p, a, b):
        """saída pendente na 1ª M1 de [a,b) ou stop nas M1 a partir da entrada. Devolve operação fechada ou None."""
        s = p["lado"]
        if p["saida_pendente"] and a < b: return self.fechar(p, a, self.o1[a] + self.sp[a] if s < 0 else self.o1[a], "saída por sinal (fechamento de volta ao canal)")
        if p["saida_pendente"]: return None
        r0 = abs(p["entrada"] - p["stop"])
        for jj in range(max(a, p["j_ent"]), b):
            if (s > 0 and self.l1[jj] <= p["stop"]) or (s < 0 and self.h1[jj] + self.sp[jj] >= p["stop"]):
                px = min(p["stop"], self.o1[jj]) if s > 0 else max(p["stop"], self.o1[jj] + self.sp[jj])
                if jj == p["j_ent"]: px = p["stop"]; p["stop_na_m1_entrada"] = True
                return self.fechar(p, jj, px, "stop de proteção")
            p["mfe"] = max(p["mfe"], (self.c1[jj] - p["entrada"]) * s / r0)
        return None

    def fechamento(self, p, i):
        if (self.C[i] >= self.EL[i]) if p["lado"] < 0 else (self.C[i] <= self.EH[i]): p["saida_pendente"] = True

    # ── gatilho na barra seguinte ──
    def gatilho(self, g, i, a, b):
        s = g["lado"]; Lb_t = g["ext_t"]; T_t = g["T_t"]; info = {"lado": s, "n_m1_barra": b - a}
        if a >= b: return "sem M1 na barra seguinte", None, info
        if s < 0: hit = np.nonzero(self.l1T[a:b] <= T_t)[0]; toque = bool((self.l1T[a:b] <= Lb_t).any())
        else: hit = np.nonzero(self.h1T[a:b] >= T_t)[0]; toque = bool((self.h1T[a:b] >= Lb_t).any())
        if not len(hit): return ("toque sem superação" if toque else "não alcançou"), None, info
        return "superou", a + int(hit[0]), info

    def desfecho_rapido(self, g, j):
        """DESFECHO (não usado para decidir): minutos até uma M1 fechar de volta além do extremo, nos 15 min após τ."""
        s = g["lado"]; tau = self.t1[j]; Lb = g["extremo_rompimento"]
        for k in range(j, min(j + 15, len(self.t1))):
            if self.t1[k] >= tau + M15: break
            if (self.c1[k] > Lb + 1e-9) if s < 0 else (self.c1[k] < Lb - 1e-9): return round((int(self.t1[k]) + MIN - int(tau)) / MIN, 1)
        return None

    # ── uma barra ──
    def barra(self, i):
        a, b = self.m1_da_barra(i)
        for r in REGRAS:                                                                 # (1) posições abertas
            p = self.pos[r]
            if p is None: continue
            op = self.intrabarra(p, a, b)
            if op is not None: self.ops[r].append(op); self.pos[r] = None; self.ult_sai[r] = op["j_sai"]; self.R(i, "saida_virtual", regra=r, id=op["id"], motivo=op["motivo_saida"], R=round(op["R"], 4))
        g, self.pend = self.pend, None                                                   # (2) gatilho só nesta barra
        if g is not None:
            res, j, info = self.gatilho(g, i, a, b); sig = {**{k: v for k, v in g.items() if k not in ("T_t", "ext_t")}, "barra_gatilho": str(self.m15.t.iloc[i]), "resultado_gatilho": res}
            if j is not None:
                Lr = self.leitura(j, g["lado"]); sig.update({"t_superacao": self.ts(self.t1[j]), "j_sup": j, "leitura": Lr, "lacuna_na_abertura": bool(self.o1T[j] < g["T_t"] if g["lado"] < 0 else self.o1T[j] > g["T_t"]),
                                                             "desfecho_devolucao_min": self.desfecho_rapido(g, j)})
                for r in REGRAS:
                    ok = self.decide(r, Lr); sig[f"{r}_decisao"] = "entra" if ok else "descarta"
                    if not ok:
                        self.R(i, "descartado", regra=r, sinal=g["id"], motivo=f"{NOME_REGRA[r]}: não confirmou no instante da superação (sem reativação depois)", leitura=Lr); continue
                    if self.pos[r] is not None or self.ult_sai[r] > j:
                        sig[f"{r}_carteira"] = "posição aberta"; self.R(i, "bloqueado_posicao_aberta", regra=r, sinal=g["id"]); continue
                    p = self.nova_pos(g, j, r); self.R(i, "entrada_virtual", regra=r, sinal=g["id"], id=p["id"], t_m1=self.ts(self.t1[j]), preco=round(p["entrada"], 2), leitura=Lr)
                    sig[f"{r}_carteira"] = "entrou"; op = self.intrabarra(p, j, b)
                    if op is not None: self.ops[r].append(op); self.ult_sai[r] = op["j_sai"]; self.R(i, "saida_virtual", regra=r, id=op["id"], motivo=op["motivo_saida"], R=round(op["R"], 4))
                    else: self.pos[r] = p
            else:
                for r in REGRAS: sig[f"{r}_decisao"] = "sem entrada"
                self.R(i, "gatilho_expirado", sinal=g["id"], motivo=f"{res}: a barra seguinte terminou; nada depois disso abre", **info)
            self.sinais.append(sig)
        for r in REGRAS:                                                                 # (3) fechamento M15
            if self.pos[r] is not None: self.fechamento(self.pos[r], i)
        self.mem.nova_barra(str(self.m15.t.iloc[i]), self.ts(self.f15[i]), self.O[i], self.H[i], self.L_[i], self.C[i])   # (4)
        if np.isfinite(self.ATR[i]):                                                     # (5) formação → gatilho armado para i+1
            g = self.detectar(i)
            if g is not None:
                s = g["lado"]; ext_t = int(tk(g["extremo_rompimento"])); g.update({"ext_t": ext_t, "T_t": ext_t + s, "T": (ext_t + s) * TICK}); self.pend = g
                self.R(i, "gatilho_armado", sinal=g["id"], motivo="lateralização + tentativa sem confirmação + fechamento além do nível; vale só na barra seguinte",
                       nivel=g["referencia"], gatilho=round(g["T"], 2), prox_nivel_dist_atr=g["prox_nivel_dist_atr"])

    def rodar(self, i0=25, i1=None):
        for i in range(i0, i1 or len(self.m15)): self.barra(i)

    # ── simulação ISOLADA de um sinal superado (mesma gestão; ignora a carteira) ──
    def isolada(self, sig):
        g = {"id": sig["id"], "lado": sig["lado"], "T": sig["T"], "T_t": int(tk(sig["T"])), "atr": sig["atr"], "extremo_rompimento": sig["extremo_rompimento"]}
        j = sig["j_sup"]; p = self.nova_pos(g, j, "ISO"); i = int(np.searchsorted(self.f15, self.t1[j], side="right"))
        a, b = self.m1_da_barra(i); op = self.intrabarra(p, j, b)
        while op is None:
            self.fechamento(p, i); i += 1
            if i >= len(self.m15): return None
            a, b = self.m1_da_barra(i); op = self.intrabarra(p, a, b)
        return op


# ─────────────────────────── persistência (reinício / sombra): índices viram horários ───────────────────────────
def _js(x):
    if hasattr(x, "item"): return x.item()
    raise TypeError(type(x))


def salvar_estado(M, f_mem, f_est):
    import json
    M.mem.salvar(f_mem)
    pos = {r: (None if p is None else {k: v for k, v in p.items() if k != "j_ent"}) for r, p in M.pos.items()}
    pend = None if M.pend is None else dict(M.pend)
    ult = {r: (None if j < 0 else int(M.t1[j])) for r, j in M.ult_sai.items()}
    json.dump({"versao": VERSAO, "usados": sorted(M.usados), "pend": pend, "pos": pos, "ult_sai_t": ult}, open(f_est, "w"), default=_js)


def carregar_estado(M, f_mem, f_est):
    import json
    M.mem = ES.Memoria.carregar(f_mem); d = json.load(open(f_est)); M.usados = set(d["usados"]); M.pend = d["pend"]
    for r in REGRAS:
        p = d["pos"][r]
        if p is not None: p["j_ent"] = int(np.searchsorted(M.t1, p["t_ent"]))
        M.pos[r] = p; t = d["ult_sai_t"][r]; M.ult_sai[r] = -1 if t is None else int(np.searchsorted(M.t1, t))
