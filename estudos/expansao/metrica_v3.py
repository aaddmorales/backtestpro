# -*- coding: utf-8 -*-
"""Métrica primária corrigida (protocolo v3): P(não renovado | exaustão) − P(não renovado | pausa), cada rótulo agrupado dentro de si
(mesma população bruta, mesma regra de 16 barras), IC 95% por reamostragem de semanas aplicada às duas medidas juntas."""
import json, sys, collections, random
import numpy as np
import alternativas as M
import validacao_v2 as V
CV1 = M.CV1


def ic(A, ex, pz, n=1000, seed=13, nivel=95.0):
    se, sp = collections.defaultdict(list), collections.defaultdict(list)
    for x in ex: se[V.semana(A, x["i"])].append(x)
    for x in pz: sp[V.semana(A, x["i"])].append(x)
    ks = sorted(set(se) | set(sp)); r = random.Random(seed); d = []
    for _ in range(n):
        s = [r.choice(ks) for _ in ks]
        e = [x for k in s for x in se.get(k, [])]; p = [x for k in s for x in sp.get(k, [])]
        if e and p:
            d.append(100 * sum(x["verdade"] == "FIM" for x in e) / len(e) - 100 * sum(x["verdade"] == "FIM" for x in p) / len(p))
    q = (100 - nivel) / 2
    return [round(float(np.percentile(d, q)), 1), round(float(np.percentile(d, 100 - q)), 1)]


N_MIN = 30   # exaustões agrupadas por ativo na janela confirmatória (mesmo mínimo já usado no v2 para declarar n insuficiente)


def classificar(n, dif, lo, hi):
    """critérios FECHADOS do protocolo v3, seção 6.1 (IC 98,75% = Bonferroni sobre a família de 4 testes)."""
    if n < N_MIN:
        return "insuficiente (n < 30)"
    if lo > 0 and dif >= 5:
        return "efeito confirmado e relevante"
    if lo > 0:
        return "efeito positivo abaixo do limiar relevante (não aceito)"
    if hi < 0:
        return "contrário"
    return "inconclusivo"


out = {}
for sim in sys.argv[1:]:
    A = M.Ativo(sim)
    t0 = lambda i: (abs(A.D[i]) >= CV1.P("D_AFASTAMENTO")) or (A.Lcor[i][1] >= CV1.P("L_PERNA_TARDIA"))
    pop = A.p1(); ex0 = {x["i"]: A.exaustao(x["i"], t0) for x in pop}
    rot = M.rotular(A, pop, "A0", lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d)
    out[sim] = {}
    for p in V.PER:
        sub = [x for x in rot if A.periodo(x["i"]) == p]
        ex = M.desagrupar([x for x in sub if x["rot"] == "exaustão"]); pz = M.desagrupar([x for x in sub if x["rot"] == "pausa"])
        pe = 100 * sum(x["verdade"] == "FIM" for x in ex) / len(ex); pp = 100 * sum(x["verdade"] == "FIM" for x in pz) / len(pz)
        out[sim][p] = dict(n_exaustao=len(ex), n_pausa=len(pz), exaustao_nao_renovado=round(pe, 1), pausa_nao_renovado=round(pp, 1),
                           diferenca_pp=round(pe - pp, 1), IC95=ic(A, ex, pz), IC98_75=ic(A, ex, pz, nivel=98.75))
        o = out[sim][p]; o["classificacao_descritiva"] = classificar(o["n_exaustao"], o["diferenca_pp"], *o["IC98_75"])
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open("metrica_v3_historico.json", "w"), ensure_ascii=False, indent=1)
