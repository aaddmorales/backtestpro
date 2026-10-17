# -*- coding: utf-8 -*-
"""Protocolo v3 — A0 × A3 PAREADOS por oportunidade de rompimento (mesmo rompimento pendente do motor, com rearme).
Unidade: cada rompimento pendente (1º fechamento fora da caixa armada). Para cada regra (A0 = máx/mín além da barra do rompimento;
A3 = fechamento além dela): confirma ou não dentro de 16 barras (rearme/volta para dentro encerra). Resultado da regra na oportunidade,
em ATR da BARRA DO ROMPIMENTO (mesma unidade para as duas): sem entrada = 0; com entrada no fechamento da barra que confirmou:
+1 se andou 1 ATR a favor antes de 1 ATR contra, −1 no contrário, 0 se a mesma barra tocou os dois e M5/M1 não desempatou,
e marcação a mercado no fechamento da 16ª barra se nada tocou. d = resultado(A3) − resultado(A0), pareado.
Também, pareados: precisão das confirmações (SUSTENTADO entre confirmados decididos) e cobertura (confirmados entre SUSTENTADOS).
IC por reamostragem de semanas (as duas regras na mesma reamostra). Nada aqui escolhe parâmetro."""
import json, sys, collections, random
import numpy as np
import alternativas as M
import validacao_v2 as V
H = M.H


def resultado(A, i_conf, lado, atr):
    a = A.a; c0 = a.c[i_conf]; up, dn = c0 + atr, c0 - atr
    for k in range(i_conf + 1, min(a.n, i_conf + 1 + H)):
        hu, hd = a.h[k] >= up, a.l[k] <= dn
        if hu and hd:
            r, _ = A._desempate(a.ts[k], a.ts[k] + np.timedelta64(15, "m"), up, dn, lado)
            return 1.0 if r == "favor" else (-1.0 if r == "contra" else 0.0)
        if hu or hd:
            return 1.0 if (hu if lado > 0 else hd) else -1.0
    k = min(a.n - 1, i_conf + H)
    return float(np.clip((a.c[k] - c0) * lado / atr, -1, 1))


def medidas(lst):
    d = [x["d"] for x in lst]
    dec = [x for x in lst if x["verdade"] in ("SUSTENTADO", "FALSO")]
    sus = [x for x in lst if x["verdade"] == "SUSTENTADO"]
    def prec(r):
        c = [x for x in dec if x[r] is not None]
        return 100 * sum(x["verdade"] == "SUSTENTADO" for x in c) / len(c) if c else float("nan")
    def cob(r):
        return 100 * sum(x[r] is not None for x in sus) / len(sus) if sus else float("nan")
    return dict(d_medio_atr=float(np.mean(d)) if d else float("nan"), d_prec_pp=prec("A3") - prec("A0"), d_cob_pp=cob("A3") - cob("A0"),
                prec_A0=prec("A0"), prec_A3=prec("A3"), cob_A0=cob("A0"), cob_A3=cob("A3"), r_A0=float(np.mean([x["rA0"] for x in lst])) if lst else float("nan"),
                r_A3=float(np.mean([x["rA3"] for x in lst])) if lst else float("nan"))


def ic(A, lst, n=1000, seed=17, niveis=(95.0, 98.75)):
    por = collections.defaultdict(list)
    for x in lst: por[V.semana(A, x["i"])].append(x)
    ks = sorted(por); r = random.Random(seed); bs = collections.defaultdict(list)
    for _ in range(n):
        amostra = [x for k in (r.choice(ks) for _ in ks) for x in por[k]]
        for kk, v in medidas(amostra).items():
            if v == v: bs[kk].append(v)
    out = {}
    for kk in ("d_medio_atr", "d_prec_pp", "d_cob_pp"):
        out[kk] = {f"IC{nv}": [round(float(np.percentile(bs[kk], (100 - nv) / 2)), 3 if kk == "d_medio_atr" else 1),
                                round(float(np.percentile(bs[kk], 100 - (100 - nv) / 2)), 3 if kk == "d_medio_atr" else 1)] for nv in niveis}
    return out


def oportunidades(A):
    out = []
    for x in A.pendentes():
        e = dict(i=x["i"], lado=x["lado"], verdade=x["verdade"], A0=x["A0"], A3=x["A3"], atr=x["atr"])
        for r in ("A0", "A3"):
            e["r" + r] = resultado(A, x[r], x["lado"], x["atr"]) if x[r] is not None else 0.0
        e["d"] = e["rA3"] - e["rA0"]
        out.append(e)
    return out


def classificar(m, I, nv="IC98.75"):
    """critérios FECHADOS do protocolo v3 (seção 6.3) — A3 só é 'aceito' se as três condições valerem."""
    p_lo = I["d_prec_pp"][nv][0]; c_lo = I["d_cob_pp"][nv][0]; d_lo, d_hi = I["d_medio_atr"][nv]
    prec = ("ganho confirmado e relevante" if (p_lo > 0 and m["d_prec_pp"] >= 5) else
            "ganho positivo abaixo do limiar relevante (não aceito)" if p_lo > 0 else "inconclusivo" if I["d_prec_pp"][nv][1] >= 0 else "contrário")
    cob = "não inferior (limite inferior > −5 pp)" if c_lo > -5 else "não demonstrado (limite inferior ≤ −5 pp)"
    res = "melhor" if d_lo > 0 else "pior" if d_hi < 0 else "sem diferença demonstrada"   # sem margem: nenhum limite novo em ATR
    aceito = prec.startswith("ganho confirmado") and cob.startswith("não inferior") and res != "pior"
    return dict(precisao=prec, cobertura=cob, resultado_pareado=res, A3_aceito=aceito)


if __name__ == "__main__":
    out = {}
    for sim in sys.argv[1:]:
        A = M.Ativo(sim); ops = oportunidades(A); out[sim] = {}
        for p in V.PER:
            sub = [x for x in ops if A.periodo(x["i"]) == p]
            m = medidas(sub); I = ic(A, sub)
            out[sim][p] = dict(n_oportunidades=len(sub), n_sustentado=sum(x["verdade"] == "SUSTENTADO" for x in sub),
                               n_conf_A0=sum(x["A0"] is not None for x in sub), n_conf_A3=sum(x["A3"] is not None for x in sub),
                               medidas={k: round(v, 3) for k, v in m.items()}, ic=I, classificacao_descritiva=classificar(m, I))
            print(sim, p, json.dumps(out[sim][p], ensure_ascii=False))
    json.dump(out, open("a3_pareado_historico.json", "w"), ensure_ascii=False, indent=1)
