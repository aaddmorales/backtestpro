# -*- coding: utf-8 -*-
"""Estudo das alternativas de percepção — protocolo em PROTOCOLO_ALTERNATIVAS.md (escrito antes da medição).
Motor em operação NÃO é alterado: bt_ciclo_v1 é só importado; as variantes são reimplementadas aqui."""
import sys, os, json, collections, random
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude/repo/motor_ciclos")
import bt_ciclo_v1 as CV1

AQUI = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(AQUI, "dados")
H = 16
SPLITS = {"BTCUSD": ("2025-08-09", "2026-02-08", "2026-05-08", "2026-08-08 14:45"),
          "XAUUSD": ("2025-09-04", "2026-03-04", "2026-06-04", "2026-09-04 19:45")}
ARQ = {"BTCUSD": dict(m15="BTCUSD_M15_202508080000_202608081845.csv", h1="BTCUSD_H1_202508080000_202608081800.csv"),
       "XAUUSD": dict(m15="XAUUSD_M15_202409100100_202609042345.csv", h1="XAUUSD_H1_202409100100_202609042300.csv",
                      m5="XAUUSD_M5_202409100100_202609042355.csv", m1="XAUUSD_M1_202409100100_202609042356.csv")}
LP_GRADE = (8, 10, 12, 15, 20)


def ler(nome):
    return pd.read_csv(os.path.join(D, nome), sep="\t")


def menor(nome):
    if not nome:
        return None
    df = ler(nome)
    ts = pd.to_datetime(df["<DATE>"] + " " + df["<TIME>"], format="%Y.%m.%d %H:%M:%S").values
    return dict(ts=ts, h=df["<HIGH>"].astype(float).values, l=df["<LOW>"].astype(float).values)


class Ativo:
    def __init__(self, sim):
        self.sim = sim
        f = ARQ[sim]
        self.a = CV1.Andar("M15", ler(f["m15"]))
        self.h1 = CV1.Andar("H1", ler(f["h1"]))
        self.m5, self.m1 = menor(f.get("m5")), menor(f.get("m1"))
        a = self.a
        self.ts = pd.to_datetime(a.ts)
        s = SPLITS[sim]
        self.i_ini = int(np.searchsorted(a.ts, np.datetime64(s[0])))
        self.i_fim = int(np.searchsorted(a.ts, np.datetime64(s[3]), side="right")) - 1 - H
        self.cortes = [np.datetime64(s[1]), np.datetime64(s[2])]
        lo = self.i_ini - 260
        self.piv, self.comp, self.dcanal, self.Lcor, self.Lpiv, self.D = {}, {}, {}, {}, {}, {}
        for i in range(lo, self.i_fim + H + 1):
            p = CV1.pivos(a, i)
            self.piv[i] = p
            self.comp[i] = CV1.compressao(a, i)[0]
            dc = 1 if a.c[i] > a.emaH[i] else (-1 if a.c[i] < a.emaL[i] else 0)
            self.dcanal[i] = dc
            self.Lcor[i] = CV1.perna_L(a, i)
            k = p["k_fundo"] if dc == 1 else (p["k_topo"] if dc == -1 else None)
            self.Lpiv[i] = (i - k) if k is not None else 0
            self.D[i] = CV1.afastamento_D(a, i)

    def periodo(self, i):
        t = self.a.ts[i]
        return "desenvolvimento" if t < self.cortes[0] else ("validação" if t < self.cortes[1] else "reserva")

    def regime_h1(self, i, d):
        t_dec = self.a.ts[i] + np.timedelta64(15, "m")
        j = int(np.searchsorted(self.h1.ts, t_dec - np.timedelta64(60, "m"), side="right")) - 1
        if j < 20:
            return "sem H1"
        b = self.h1
        dh = 1 if b.c[j] > b.emaH[j] else (-1 if b.c[j] < b.emaL[j] else 0)
        return "H1 lateral" if dh == 0 else ("H1 a favor" if dh == d else "H1 contra")

    # ---------------- exaustão (cópia fiel de CV1.exaustao com o "tardio" trocável) ----------------
    def exaustao(self, i, tardio_fn):
        a = self.a; piv = self.piv[i]
        if np.isnan(a.atr[i]) or a.atr[i] <= 0:
            return dict(degrau=0, gatilho=None, lado=0)
        d, L = self.Lcor[i]
        tardio = tardio_fn(i)
        rng = a.h[i] - a.l[i]; corpo = abs(a.c[i] - a.o[i])
        gat = None; lado = 0; origem = None
        if tardio and d != 0:
            maior20 = rng >= max(a.h[max(0, i - 20):i] - a.l[max(0, i - 20):i]) if i > 20 else False
            if (rng >= CV1.P("X_CLIMAX") * a.atr[i] or maior20) and corpo / max(rng, 1e-12) > 0.6:
                gat, lado = ("E1_climax_baixa" if -d < 0 else "E1_climax_alta"), -d
            pavio = (a.h[i] - max(a.o[i], a.c[i])) if d == 1 else (min(a.o[i], a.c[i]) - a.l[i])
            if rng > 0 and pavio / rng >= CV1.P("R_REJEICAO"):
                gat, lado = "E2_rejeicao", -d
            if gat is None and i >= CV1.P("K_E3"):
                corpos = [abs(a.c[k] - a.o[k]) for k in range(i - CV1.P("K_E3") + 1, i + 1)]
                if all(corpos[j] < corpos[j - 1] for j in range(1, len(corpos))):
                    gat, lado = ("E3_gradual_baixa" if -d < 0 else "E3_gradual_alta"), -d
        if gat is None:
            for j in range(i - 1, max(24, i - 6), -1):
                dj = 1 if a.c[j] > a.o[j] else (-1 if a.c[j] < a.o[j] else 0)
                if dj == 0 or np.isnan(a.atr[j]) or a.atr[j] <= 0:
                    continue
                if not tardio_fn(j):
                    continue
                rj = a.h[j] - a.l[j]; cj = abs(a.c[j] - a.o[j])
                m20 = rj >= max(a.h[max(0, j - 20):j] - a.l[max(0, j - 20):j]) if j > 20 else False
                pv = (a.h[j] - max(a.o[j], a.c[j])) if dj == 1 else (min(a.o[j], a.c[j]) - a.l[j])
                e1 = (rj >= CV1.P("X_CLIMAX") * a.atr[j] or m20) and cj / max(rj, 1e-12) > 0.6
                e2 = rj > 0 and pv / rj >= CV1.P("R_REJEICAO")
                if e1 or e2:
                    gat, lado = ("E1/E2_baixa(persistente)" if -dj < 0 else "E1/E2_alta(persistente)"), -dj
                    origem = "E2" if e2 else "E1"          # mesma precedência do motor no gatilho da própria barra (E2 sobrescreve E1)
                    break
        degrau = 1 if gat else 0
        if gat and lado == -1 and piv["k_topo"] is not None and piv["k_topo"] >= i - 6:
            degrau = 2
            if piv["ultimo_fundo"] and a.c[i] < piv["ultimo_fundo"]:
                degrau = 3
        if gat and lado == 1 and piv["k_fundo"] is not None and piv["k_fundo"] >= i - 6:
            degrau = 2
            if piv["ultimo_topo"] and a.c[i] > piv["ultimo_topo"]:
                degrau = 3
        if gat and origem is None:
            origem = gat[:2]
        return dict(degrau=degrau, gatilho=gat, lado=lado, origem=origem)

    # ---------------- resolução por barreiras ±1 ATR, com M5/M1 para a barra que toca as duas ----------------
    def _desempate(self, t0, t1, up, dn, s):
        for nome, tf in (("M5", self.m5), ("M1", self.m1)):
            if tf is None:
                continue
            j0, j1 = int(np.searchsorted(tf["ts"], t0)), int(np.searchsorted(tf["ts"], t1))
            amb = False
            for j in range(j0, j1):
                hu, hd = tf["h"][j] >= up, tf["l"][j] <= dn
                if hu and hd:
                    amb = True
                    if nome == "M5" and self.m1 is not None:          # desce para o M1 nesse M5
                        break
                    return "ambígua", nome
                if hu or hd:
                    return ("favor" if (hu if s > 0 else hd) else "contra"), nome
            if amb and nome == "M5":
                continue
        return "ambígua", "sem dado menor"

    def barreiras(self, i, s, R=1.0):
        a = self.a; c0, atr = a.c[i], a.atr[i]
        up, dn = c0 + R * atr, c0 - R * atr
        mae = 0.0
        for k in range(i + 1, min(a.n, i + 1 + H)):
            adv = (c0 - a.l[k]) if s > 0 else (a.h[k] - c0)
            hu, hd = a.h[k] >= up, a.l[k] <= dn
            if hu and hd:
                t0 = a.ts[k]; r, fonte = self._desempate(t0, t0 + np.timedelta64(15, "m"), up, dn, s)
                return dict(res=r, barras=k - i, desempate=fonte, mae=round(max(mae, adv) / atr, 2))
            if hu or hd:
                fav = hu if s > 0 else hd
                if not fav:
                    mae = max(mae, adv)
                else:
                    mae = max(mae, max(0.0, adv))
                return dict(res="favor" if fav else "contra", barras=k - i, desempate=None, mae=round(mae / atr, 2))
            mae = max(mae, adv)
        return dict(res="sem resolução", barras=H, desempate=None, mae=round(mae / atr, 2))

    # ---------------- caixa com regra de confirmação trocável (cópia de CV1.caixa_estado) ----------------
    def pendentes(self):
        """todas as barras que abrem um rompimento pendente (caixa do motor), com o que vem depois por cada regra."""
        a = self.a; out = []; vistos = set()
        for i in range(self.i_ini, self.i_fim + 1):
            k_arm = None
            for k in range(i, max(25, i - 90), -1):
                if self.comp.get(k):
                    k_arm = k; break
            if k_arm is None or k_arm == i:
                continue
            j0 = k_arm - CV1.P("N_CAIXA") + 1
            topo, fundo = float(max(a.h[j0:k_arm + 1])), float(min(a.l[j0:k_arm + 1]))
            # a barra i é a PRIMEIRA a fechar fora desde o armamento (ou desde o último retorno)?
            if not (a.c[i] > topo or a.c[i] < fundo):
                continue
            prev_fora = False
            for k in range(i - 1, k_arm, -1):
                if a.c[k] > topo or a.c[k] < fundo:
                    prev_fora = True; break
                break
            if prev_fora or (k_arm, i) in vistos:
                continue
            vistos.add((k_arm, i))
            ld = 1 if a.c[i] > topo else -1
            ev = dict(i=i, lado=ld, topo=topo, fundo=fundo, atr=float(a.atr[i]))
            ev["rearmou"] = None
            for regra in ("A0", "A3"):
                conf = None
                for k in range(i + 1, min(a.n, i + 1 + H)):
                    if self.comp.get(k):                  # fidelidade (v2): o motor rearma a caixa nesta barra e abandona o rompimento
                        ev["rearmou"] = ev["rearmou"] or k
                        break
                    dentro = fundo <= a.c[k] <= topo
                    if regra == "A0":
                        ok = (a.h[k] > a.h[i]) if ld == 1 else (a.l[k] < a.l[i])
                    else:
                        ok = (a.c[k] > a.h[i]) if ld == 1 else (a.c[k] < a.l[i])
                    if ok and not dentro:
                        conf = k; break
                    if dentro:
                        break
                ev[regra] = conf
            # verdade (igual para todos): 1 ATR além da fronteira antes de fechar de volta dentro
            alvo = topo + ev["atr"] if ld == 1 else fundo - ev["atr"]
            ver = "sem resolução"
            for k in range(i + 1, min(a.n, i + 1 + H)):
                if (a.h[k] >= alvo) if ld == 1 else (a.l[k] <= alvo):
                    ver = "SUSTENTADO"; break
                if fundo <= a.c[k] <= topo:
                    ver = "FALSO"; break
            ev["verdade"] = ver
            out.append(ev)
        return out

    # ---------------- população P1: barra contrária à perna ----------------
    def p1(self):
        a = self.a; out = []
        for i in range(self.i_ini, self.i_fim + 1):
            d = self.dcanal[i - 1]
            cor = 1 if a.c[i] > a.o[i] else (-1 if a.c[i] < a.o[i] else 0)
            if d == 0 or cor != -d:
                continue
            p = self.piv[i]
            k0 = p["k_fundo"] if d == 1 else p["k_topo"]
            bruto = (i - k0) if k0 is not None else None
            n = min(60, max(5, bruto if bruto is not None else 5))
            janela = "sem pivô contrário confirmado (5 barras)" if bruto is None else ("pivô a menos de 5 barras (usa 5)" if bruto < 5 else ("perna > 60 barras (usa 60)" if bruto > 60 else "desde o pivô (5–60)"))
            E = a.h[i - n:i + 1].max() if d == 1 else a.l[i - n:i + 1].min()
            fut = a.h[i + 1:i + 1 + H].max() if d == 1 else a.l[i + 1:i + 1 + H].min()
            cont = (fut > E) if d == 1 else (fut < E)
            out.append(dict(i=i, d=d, E=float(E), janela=janela, verdade="CONTINUA" if cont else "FIM"))
        return out


def rotular(A, pop, nome, fn):
    """fn(i, d) -> True se o detector diz exaustão (corta) contra a perna d."""
    return [dict(x, det=nome, rot=("exaustão" if fn(x["i"], x["d"]) else "pausa")) for x in pop]


def desagrupar(evs):
    out, ult = [], -10**9
    for x in sorted(evs, key=lambda e: e["i"]):
        if x["i"] - ult >= H:
            out.append(x); ult = x["i"]
    return out


def boot(evs, fn, A, n=300, seed=7):
    """IC 95% por blocos semanais."""
    if not evs:
        return None
    sem = collections.defaultdict(list)
    for x in evs:
        sem[str(pd.Timestamp(A.a.ts[x["i"]]).to_period("W"))].append(x)
    chaves = list(sem); rnd = random.Random(seed); vals = []
    for _ in range(n):
        amostra = [e for k in (rnd.choice(chaves) for _ in chaves) for e in sem[k]]
        v = fn(amostra)
        if v is not None:
            vals.append(v)
    if len(vals) < 20:
        return None
    return [round(float(np.percentile(vals, 2.5)), 1), round(float(np.percentile(vals, 97.5)), 1)]


def pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def met_p1(lst):
    """precisão da exaustão, taxa de base, ganho, cobertura (sobre a população)."""
    n = len(lst); ex = [x for x in lst if x["rot"] == "exaustão"]
    if not n or not ex:
        return dict(n=n, n_exaustao=len(ex))
    base = pct(sum(1 for x in lst if x["verdade"] == "FIM"), n)
    prec = pct(sum(1 for x in ex if x["verdade"] == "FIM"), len(ex))
    pz = [x for x in lst if x["rot"] == "pausa"]
    return dict(n=n, n_exaustao=len(ex), cobertura=pct(len(ex), n), base_FIM=base, precisao_FIM=prec,
                ganho_pp=round(prec - base, 1), pausa_CONTINUA=pct(sum(1 for x in pz if x["verdade"] == "CONTINUA"), len(pz)))


def ganho(lst):
    m = met_p1(lst)
    return m.get("ganho_pp")


def met_oper(lst, A):
    """efeito operacional numa posição no sentido da perna: barreiras ±1 ATR em H barras."""
    out = {}
    for rot in ("exaustão", "pausa"):
        evs = desagrupar([x for x in lst if x["rot"] == rot])
        rs = [A.barreiras(x["i"], x["d"]) for x in evs]
        c = collections.Counter(r["res"] for r in rs)
        dec = [r for r in rs if r["res"] in ("favor", "contra")]
        out[rot] = dict(n=len(evs), favor=c["favor"], contra=c["contra"], ambigua=c["ambígua"], sem_resolucao=c["sem resolução"],
                        desempatadas_por_menor=sum(1 for r in rs if r["desempate"] in ("M5", "M1")),
                        pct_favor=pct(c["favor"], len(dec)), mae_mediana_atr=(round(float(np.median([r["mae"] for r in rs])), 2) if rs else None))
        if rot == "exaustão":
            out[rot]["leitura"] = "corte: favor = saída prematura; contra = proteção útil"
        else:
            out[rot]["leitura"] = "mantém: favor = continuidade preservada; contra = exposição (−1 ATR antes)"
    return out


def rodar(sim):
    A = Ativo(sim); a = A.a
    t0 = lambda i: (abs(A.D[i]) >= CV1.P("D_AFASTAMENTO")) or (A.Lcor[i][1] >= CV1.P("L_PERNA_TARDIA"))
    # conferência: a cópia da exaustão reproduz o motor
    amostra = list(range(A.i_ini, A.i_fim, 97))
    iguais = sum(1 for i in amostra if (lambda x, y: (x["degrau"], x["gatilho"], x["lado"]) == (y["degrau"], y["gatilho"], y["lado"]))(
        A.exaustao(i, t0), CV1.exaustao(a, i, A.piv[i])))
    pop = A.p1()
    ex0 = {}
    for x in pop:
        ex0[x["i"]] = A.exaustao(x["i"], t0)
    det = {"A0 motor atual": lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d,
           "A2a rejeição/gradual (E2/E3, inclusive persistente) ou 3º sinal": lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d and (
               ex0[i]["degrau"] >= 3 or ex0[i]["origem"] in ("E2", "E3")),
           "A2b só 3º sinal": lambda i, d: ex0[i]["degrau"] >= 3 and ex0[i]["lado"] == -d}
    for lp in LP_GRADE:
        exl = {x["i"]: A.exaustao(x["i"], (lambda j, lp=lp: (abs(A.D[j]) >= CV1.P("D_AFASTAMENTO")) or (A.Lpiv[j] >= lp))) for x in pop}
        det[f"A1 perna por pivô Lp={lp}"] = (lambda i, d, exl=exl: exl[i]["degrau"] >= 2 and exl[i]["lado"] == -d)
    rot = {k: rotular(A, pop, k, f) for k, f in det.items()}
    res = {"ativo": sim, "conferencia_copia_exaustao": f"{iguais}/{len(amostra)} barras idênticas ao motor",
           "populacao_P1": len(pop), "perna": {}}
    # contador de perna
    Lc = [A.Lcor[i][1] for i in range(A.i_ini, A.i_fim)]; Lp_ = [A.Lpiv[i] for i in range(A.i_ini, A.i_fim) if A.dcanal[i] != 0]
    res["perna"] = dict(L_cor_max=int(max(Lc)), L_cor_p50_p90_p99=[float(np.percentile(Lc, q)) for q in (50, 90, 99)],
                        L_cor_ge_20=sum(1 for v in Lc if v >= 20),
                        L_pivo_p50_p90_p99=[float(np.percentile(Lp_, q)) for q in (50, 90, 99)],
                        L_pivo_ge_20_pct=pct(sum(1 for v in Lp_ if v >= 20), len(Lp_)))
    # percepção por período (desagrupado) + IC
    per = {}
    for k, lst in rot.items():
        per[k] = {}
        for nomep in ("desenvolvimento", "validação", "reserva"):
            sub = [x for x in lst if A.periodo(x["i"]) == nomep]
            ex = desagrupar([x for x in sub if x["rot"] == "exaustão"]); pz = desagrupar([x for x in sub if x["rot"] == "pausa"])
            base_pop = desagrupar(sub)
            m = met_p1(ex + pz); m["base_FIM"] = pct(sum(1 for x in base_pop if x["verdade"] == "FIM"), len(base_pop))
            if m.get("precisao_FIM") is not None:
                m["ganho_pp"] = round(m["precisao_FIM"] - m["base_FIM"], 1)
                m["IC95_precisao"] = boot(ex, lambda s: pct(sum(1 for x in s if x["verdade"] == "FIM"), len(s)), A)
            m["bruto_n_exaustao"] = sum(1 for x in sub if x["rot"] == "exaustão")
            per[k][nomep] = m
    res["percepcao"] = per
    # escolha no desenvolvimento (n ≥ 30)
    def melhor(prefixo):
        cand = [(per[k]["desenvolvimento"].get("ganho_pp"), k) for k in per if k.startswith(prefixo)
                and (per[k]["desenvolvimento"].get("n_exaustao") or 0) >= 30 and per[k]["desenvolvimento"].get("ganho_pp") is not None]
        return max(cand)[1] if cand else None
    esc = {"A1": melhor("A1"), "A2": melhor("A2")}
    res["escolhidos_no_desenvolvimento"] = esc
    # efeito operacional por período para A0 e escolhidos
    res["operacional"] = {}
    for k in ["A0 motor atual"] + [v for v in esc.values() if v]:
        res["operacional"][k] = {p: met_oper([x for x in rot[k] if A.periodo(x["i"]) == p], A) for p in ("desenvolvimento", "validação", "reserva")}
    # recortes (validação + reserva juntos, desagrupado): direção e regime
    rec = {}
    for k in ["A0 motor atual"] + [v for v in esc.values() if v]:
        fora = [x for x in rot[k] if A.periodo(x["i"]) != "desenvolvimento"]
        rec[k] = {}
        for nome, chave in (("direção", lambda x: "perna de alta (posição comprada)" if x["d"] > 0 else "perna de baixa (posição vendida)"),
                            ("regime", lambda x: A.regime_h1(x["i"], x["d"]))):
            g = collections.defaultdict(list)
            for x in fora:
                g[chave(x)].append(x)
            rec[k][nome] = {gk: (lambda ex, pop_: dict(n_exaustao=len(ex), precisao_FIM=pct(sum(1 for e in ex if e["verdade"] == "FIM"), len(ex)),
                                                      base_FIM=pct(sum(1 for e in pop_ if e["verdade"] == "FIM"), len(pop_))))(
                desagrupar([x for x in gv if x["rot"] == "exaustão"]), desagrupar(gv)) for gk, gv in sorted(g.items())}
    res["recortes_fora_do_desenvolvimento"] = rec
    # rompimentos (P2)
    pend = A.pendentes()
    p2 = {}
    for nomep in ("desenvolvimento", "validação", "reserva", "total"):
        sub = desagrupar([x for x in pend if nomep == "total" or A.periodo(x["i"]) == nomep])
        base = pct(sum(1 for x in sub if x["verdade"] == "SUSTENTADO"), sum(1 for x in sub if x["verdade"] in ("SUSTENTADO", "FALSO")))
        linha = dict(n_pendentes=len(sub), base_SUSTENTADO=base,
                     sem_resolucao=sum(1 for x in sub if x["verdade"] == "sem resolução"))
        for r in ("A0", "A3"):
            cf = [x for x in sub if x[r] is not None]
            dec = [x for x in cf if x["verdade"] in ("SUSTENTADO", "FALSO")]
            ops = [A.barreiras(x[r], x["lado"]) for x in cf]
            cc = collections.Counter(o["res"] for o in ops)
            espera = [(a.c[x[r]] - a.c[x["i"]]) * x["lado"] / x["atr"] for x in cf]
            linha[r] = dict(confirmados=len(cf), pct_dos_pendentes=pct(len(cf), len(sub)),
                            SUSTENTADO_pct=pct(sum(1 for x in dec if x["verdade"] == "SUSTENTADO"), len(dec)),
                            FALSO_confirmado=sum(1 for x in dec if x["verdade"] == "FALSO"),
                            SUSTENTADO_perdido=sum(1 for x in sub if x[r] is None and x["verdade"] == "SUSTENTADO"),
                            entrada_no_confirmado=dict(favor=cc["favor"], contra=cc["contra"], ambigua=cc["ambígua"], sem_resolucao=cc["sem resolução"],
                                                       pct_favor=pct(cc["favor"], cc["favor"] + cc["contra"])),
                            custo_espera_atr_mediana=(round(float(np.median(espera)), 2) if espera else None),
                            IC95_SUSTENTADO=boot(dec, lambda s: pct(sum(1 for x in s if x["verdade"] == "SUSTENTADO"), len(s)), A))
        p2[nomep] = linha
    res["rompimento"] = p2
    return A, res, rot, pend
