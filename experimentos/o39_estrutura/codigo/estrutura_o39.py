"""estrutura-0.1 (ORDEM 039) — MEMÓRIA ESTRUTURAL de fundos/topos por timeframe: detector fractal estrito (2+2), candidato → confirmado (fechamento de i+2),
zonas explícitas (zona-0.1: 0,25×ATR14), agrupamento explícito (fundo/topo duplo), estados com histórico, contadores, troca de função só com evidência,
persistência em JSON. Incremental: nova_barra() a cada barra CONCLUÍDA. Mesmo código no replay e no leitor sombra. Especificação: O39_especificacao_congelada.txt."""
import json
import numpy as np
VERSAO = "estrutura-0.1 (ORDEM 039)"; CRITERIO_ZONA = "zona-0.1: fundo [x, x+0,25·ATR14]; topo [x−0,25·ATR14, x]; agrupa se extremo em [base−0,25·ATR14, topo] de nível ativo"
K_ZONA = 0.25; N_ATR = 14


class Memoria:
    def __init__(self, ativo, tf, tick=0.01):
        self.ativo, self.tf, self.tick = ativo, tf, tick; self.niveis = []; self.buf = []; self.cand = []; self.n_barras = 0; self.atr = None; self.tr14 = []; self.c_ant = None
        self.versao = VERSAO; self._cache = None

    # ───────── persistência ─────────
    def salvar(self, f):
        d = {k: getattr(self, k) for k in ("ativo", "tf", "tick", "niveis", "buf", "cand", "n_barras", "atr", "tr14", "c_ant", "versao")}
        tmp = f + ".tmp"; json.dump(d, open(tmp, "w")); import os; os.replace(tmp, f)

    @classmethod
    def carregar(cls, f):
        d = json.load(open(f)); m = cls(d["ativo"], d["tf"], d["tick"])
        for k, v in d.items(): setattr(m, k, v)
        m._cache = None; return m

    # ───────── ATR14 de Wilder incremental ─────────
    def _atr(self, h, l, c):
        tr = h - l if self.c_ant is None else max(h - l, abs(h - self.c_ant), abs(l - self.c_ant)); self.c_ant = c
        if self.atr is None:
            self.tr14.append(tr)
            if len(self.tr14) == N_ATR: self.atr = sum(self.tr14) / N_ATR
        else: self.atr = (self.atr * (N_ATR - 1) + tr) / N_ATR
        return self.atr

    def _arr(self):
        if self._cache is None:
            N = self.niveis
            self._cache = (np.array([n["zona"][0] for n in N], float), np.array([n["zona"][1] for n in N], float))
        return self._cache

    def _hist(self, n, t, estado, motivo):
        if n["estado"] != estado or motivo: n["historico"].append([t, estado, motivo])
        n["estado"] = estado

    # ───────── barra concluída ─────────
    def nova_barra(self, t_ab, t_fecha, o, h, l, c):
        """processa UMA barra concluída; devolve a lista de eventos (dicts) desta barra."""
        ev = []; cp = self.c_ant; atr = self._atr(h, l, c); self.n_barras += 1; i = self.n_barras
        lo_, hi_ = (min(l, cp), max(h, cp)) if cp is not None else (l, h)          # inclui lacuna desde o fechamento anterior
        self.buf.append([i, t_ab, t_fecha, o, h, l, c, atr]); self.buf = self.buf[-5:]
        # 1) estados dos níveis já conhecidos (antes de confirmar novos: um nível confirmado agora não reage à própria barra de confirmação)
        if self.niveis:
            B, T = self._arr(); tol = 0.0
            idx = set(np.nonzero((B <= hi_) & (T >= lo_))[0].tolist()) | {k for k, n in enumerate(self.niveis) if n["estado"] in ("ROMPIMENTO PENDENTE",) or n.get("aguarda_superacao")}
            idx |= {k for k, n in enumerate(self.niveis) if n["estado"] == "ROMPIMENTO CONFIRMADO" and ((n["funcao"] == "suporte" and h >= n["zona"][0]) or (n["funcao"] == "resistencia" and l <= n["zona"][1]))}
            for k in sorted(idx): ev += self._atualizar(self.niveis[k], t_fecha, o, h, l, c)
            for n in self.niveis: n["idade_barras"] = i - n["barra_extremo"]
        # 2) candidatos pendentes: descartar ou confirmar
        novos = []
        for cd in self.cand:
            j = cd["barra"]
            if cd["tipo"] == "fundo" and l <= cd["extremo"] or cd["tipo"] == "topo" and h >= cd["extremo"]:
                ev.append({"evento": "candidato_descartado", "tipo": cd["tipo"], "extremo": cd["extremo"], "t_extremo": cd["t_extremo"], "t": t_fecha, "motivo": "barra seguinte igualou/ultrapassou (estrito)"}); continue
            if i - j == 2: ev += self._confirmar(cd, t_fecha)
            else: novos.append(cd)
        self.cand = novos
        # 3) novo candidato na barra atual (estrito contra as 2 anteriores)
        if len(self.buf) >= 3 and atr is not None:
            p1, p2 = self.buf[-2], self.buf[-3]
            if l < p1[5] and l < p2[5]: self.cand.append({"tipo": "fundo", "barra": i, "extremo": l, "t_extremo": t_ab, "atr": atr}); ev.append({"evento": "candidato", "tipo": "fundo", "extremo": l, "t": t_fecha})
            if h > p1[4] and h > p2[4]: self.cand.append({"tipo": "topo", "barra": i, "extremo": h, "t_extremo": t_ab, "atr": atr}); ev.append({"evento": "candidato", "tipo": "topo", "extremo": h, "t": t_fecha})
        return ev

    def _confirmar(self, cd, t):
        x, a, sup = cd["extremo"], cd["atr"], cd["tipo"] == "fundo"; fun = "suporte" if sup else "resistencia"
        # agrupamento explícito com nível ATIVO da mesma função
        melhor = None
        for n in self.niveis:
            if n["funcao"] != fun or n["estado"] == "ROMPIMENTO CONFIRMADO": continue
            b, tz = n["zona"]
            dentro = (b - K_ZONA * a <= x <= tz) if sup else (b <= x <= tz + K_ZONA * a)
            if dentro and (melhor is None or abs(x - n["extremo"]) < abs(x - melhor["extremo"])): melhor = n
        if melhor is not None:
            z = [x, x + K_ZONA * a] if sup else [x - K_ZONA * a, x]
            melhor["membros"].append({"extremo": x, "t_extremo": cd["t_extremo"], "t_confirmacao": t}); melhor["zona"] = [min(melhor["zona"][0], z[0]), max(melhor["zona"][1], z[1])]
            melhor["historico"].append([t, melhor["estado"], f"agrupado: novo {cd['tipo']} {x} (zona-0.1)"]); self._cache = None
            return [{"evento": "agrupado", "nivel": melhor["id"], "extremo": x, "t": t}]
        nid = f"{self.ativo}-{self.tf}-{cd['tipo']}-{cd['t_extremo']}"
        n = {"id": nid, "ativo": self.ativo, "tf": self.tf, "tipo": cd["tipo"], "funcao": fun, "extremo": x, "t_extremo": cd["t_extremo"], "t_confirmacao": t, "barra_extremo": cd["barra"],
             "zona": [x, x + K_ZONA * a] if sup else [x - K_ZONA * a, x], "criterio": CRITERIO_ZONA, "versao": VERSAO, "atr_formacao": a, "membros": [{"extremo": x, "t_extremo": cd["t_extremo"], "t_confirmacao": t}],
             "estado": "CONFIRMADO", "historico": [[cd["t_extremo"], "CANDIDATO", "fractal estrito 2+2"], [t, "CONFIRMADO", "2 barras seguintes concluídas"]],
             "testes": 0, "rejeicoes": 0, "tentativas_rompimento": 0, "rompimentos_nao_confirmados": 0, "idade_barras": 0, "barra_rompimento": None, "aguarda_superacao": False, "evidencias_troca": []}
        self.niveis.append(n); self._cache = None
        return [{"evento": "confirmado", "nivel": nid, "funcao": fun, "extremo": x, "zona": n["zona"], "t": t}]

    def _atualizar(self, n, t, o, h, l, c):
        ev = []; b, tz = n["zona"]; sup = n["funcao"] == "suporte"
        # superação da barra de rompimento (barra IMEDIATAMENTE seguinte)
        if n.get("aguarda_superacao"):
            br = n["barra_rompimento"]; n["aguarda_superacao"] = False
            ok = (l <= br["l"] - self.tick + 1e-9) if sup else (h >= br["h"] + self.tick - 1e-9)
            if ok:
                self._hist(n, t, "ROMPIMENTO CONFIRMADO", "barra seguinte superou o extremo da barra de rompimento em ≥ 1 tick"); return ev + [{"evento": "rompimento_confirmado", "nivel": n["id"], "t": t}]
            n["rompimentos_nao_confirmados"] += 1; self._hist(n, t, "EM TESTE", "rompimento NÃO confirmado: a barra seguinte não superou o extremo"); ev.append({"evento": "rompimento_nao_confirmado", "nivel": n["id"], "t": t, "ref_h": br["h"], "ref_l": br["l"]})
        e = n["estado"]
        if e == "ROMPIMENTO CONFIRMADO":
            if (sup and c >= tz) or ((not sup) and c <= b):
                self._hist(n, t, "RECUPERADO", "fechamento de volta além da zona"); return ev + [{"evento": "recuperado", "nivel": n["id"], "t": t}]
            if (sup and h >= b and c < b) or ((not sup) and l <= tz and c > tz):
                n["evidencias_troca"].append({"t": t, "o": o, "h": h, "l": l, "c": c}); nova = "resistencia" if sup else "suporte"
                n["funcao"] = nova; self._hist(n, t, "CONFIRMADO", f"TROCA DE FUNÇÃO → {nova}: rejeição registrada pelo outro lado"); self._cache = None
                return ev + [{"evento": "troca_de_funcao", "nivel": n["id"], "nova_funcao": nova, "t": t}]
            return ev
        rompe = (c < b) if sup else (c > tz)
        if rompe:
            n["tentativas_rompimento"] += 1; n["barra_rompimento"] = {"t": t, "h": h, "l": l}; n["aguarda_superacao"] = True
            self._hist(n, t, "ROMPIMENTO PENDENTE", "fechamento além da zona (barra de rompimento; máx/mín congeladas)"); return ev + [{"evento": "rompimento_pendente", "nivel": n["id"], "h": h, "l": l, "t": t}]
        toca = (l <= tz) if sup else (h >= b)
        if toca:
            n["testes"] += 1
            if (sup and l < b) or ((not sup) and h > tz): n["rejeicoes"] += 1; mot = "tentativa/rejeição: sombra além da zona, fechamento dentro"
            else: mot = "teste da zona"
            self._hist(n, t, "EM TESTE", mot); ev.append({"evento": "teste", "nivel": n["id"], "rejeicao": mot.startswith("tentativa"), "t": t})
        return ev

    # ───────── consulta ─────────
    def obstaculo(self, lado, E, atr, risco):
        """lado −1 (venda): suporte relevante mais próximo abaixo de E; +1: resistência acima. Devolve dict ou None."""
        melhor = None
        for n in self.niveis:
            if n["estado"] == "ROMPIMENTO CONFIRMADO": continue
            b, tz = n["zona"]
            if lado < 0 and n["funcao"] == "suporte" and b < E: d = max(0.0, E - tz)
            elif lado > 0 and n["funcao"] == "resistencia" and tz > E: d = max(0.0, b - E)
            else: continue
            if melhor is None or d < melhor[0]: melhor = (d, n)
        if melhor is None: return None
        d, n = melhor; lim = max(1.0 * atr, risco)
        return {"nivel": n["id"], "funcao": n["funcao"], "zona": list(n["zona"]), "estado": n["estado"], "distancia": d, "dist_atr": d / atr if atr else None, "dist_risco": d / risco if risco else None,
                "limiar": lim, "proximo": d <= lim, "idade_barras": n["idade_barras"], "testes": n["testes"], "membros": len(n["membros"])}
