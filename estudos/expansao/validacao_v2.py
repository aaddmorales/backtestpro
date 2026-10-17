# -*- coding: utf-8 -*-
"""Validação v2 (ordem 17/10 18:21 Kyiv): bruto × agrupado, cobertura, IC 95% CONJUNTO da diferença detector − base
(blocos semanais), ambíguas/sem resolução à parte, recortes com aviso de amostra insuficiente, critério da escolha de Lp,
rompimento com a confirmação FIEL ao motor (caixa rearmada abandona o rompimento). O 3º período é comparação temporal
(já observado nos estudos anteriores), não reserva inédita."""
import json, sys, collections, random
import numpy as np, pandas as pd
import alternativas as M
CV1 = M.CV1
PER = ("desenvolvimento", "validação", "reserva")
NOME_PER = {"desenvolvimento": "desenvolvimento", "validação": "validação", "reserva": "comparação temporal (já observada)"}
NMIN = 30


def semana(A, i):
    return str(pd.Timestamp(A.a.ts[i]).to_period("W"))


def ic_conjunto(A, ex, pop, n=400, seed=11):
    """IC 95% da diferença (precisão ENR da exaustão − taxa de base ENR), reamostrando SEMANAS: as duas medidas são
    recalculadas na mesma reamostra."""
    sem_ex, sem_pop = collections.defaultdict(list), collections.defaultdict(list)
    for x in ex: sem_ex[semana(A, x["i"])].append(x)
    for x in pop: sem_pop[semana(A, x["i"])].append(x)
    chaves = sorted(set(sem_pop) | set(sem_ex)); rnd = random.Random(seed); d = []
    for _ in range(n):
        ks = [rnd.choice(chaves) for _ in chaves]
        e = [x for k in ks for x in sem_ex.get(k, [])]; p = [x for k in ks for x in sem_pop.get(k, [])]
        if e and p:
            d.append(100 * sum(x["verdade"] == "FIM" for x in e) / len(e) - 100 * sum(x["verdade"] == "FIM" for x in p) / len(p))
    return [round(float(np.percentile(d, 2.5)), 1), round(float(np.percentile(d, 97.5)), 1)] if len(d) > 50 else None


def medir_p1(A, lst):
    out = {}
    for agrupado in (False, True):
        ex = [x for x in lst if x["rot"] == "exaustão"]; pop = list(lst)
        if agrupado:
            ex = M.desagrupar(ex); pop = M.desagrupar(pop)
        b = M.pct(sum(x["verdade"] == "FIM" for x in pop), len(pop)); pr = M.pct(sum(x["verdade"] == "FIM" for x in ex), len(ex))
        r = dict(n_populacao=len(pop), n_exaustao=len(ex), cobertura_pct=M.pct(len(ex), len(pop)), base_nao_renovado=b,
                 precisao_nao_renovado=pr, diferenca_pp=(round(pr - b, 1) if pr is not None and b is not None else None),
                 amostra_suficiente=len(ex) >= NMIN)
        if agrupado and len(ex) >= 10:
            r["IC95_diferenca_conjunto"] = ic_conjunto(A, ex, pop)
        out["agrupado" if agrupado else "bruto"] = r
    return out


def medir_oper(A, lst):
    out = {}
    for rot in ("exaustão", "pausa"):
        for agrupado in (False, True):
            evs = [x for x in lst if x["rot"] == rot]
            if agrupado: evs = M.desagrupar(evs)
            rs = [A.barreiras(x["i"], x["d"]) for x in evs]; c = collections.Counter(r["res"] for r in rs)
            dec = c["favor"] + c["contra"]
            out[f"{rot}_{'agrupado' if agrupado else 'bruto'}"] = dict(
                n=len(evs), favor=c["favor"], contra=c["contra"], ambigua=c["ambígua"], sem_resolucao=c["sem resolução"],
                desempatadas_m5_m1=sum(1 for r in rs if r["desempate"] in ("M5", "M1")), pct_favor_entre_resolvidos=M.pct(c["favor"], dec))
    return out


def recortes(A, lst):
    out = {}
    for nome, chave in (("direção", lambda x: "perna de alta" if x["d"] > 0 else "perna de baixa"),
                        ("regime H1", lambda x: A.regime_h1(x["i"], x["d"]))):
        g = collections.defaultdict(list)
        for x in lst: g[chave(x)].append(x)
        out[nome] = {}
        for k, v in sorted(g.items()):
            ex = M.desagrupar([x for x in v if x["rot"] == "exaustão"]); pop = M.desagrupar(v)
            pr = M.pct(sum(x["verdade"] == "FIM" for x in ex), len(ex)); b = M.pct(sum(x["verdade"] == "FIM" for x in pop), len(pop))
            out[nome][k] = dict(n_exaustao=len(ex), precisao=pr, base=b, diferenca_pp=(round(pr - b, 1) if pr is not None else None),
                                amostra=("suficiente" if len(ex) >= NMIN else "INSUFICIENTE (< 30)"))
    return out


def rodar(sim):
    A = M.Ativo(sim)
    t0 = lambda i: (abs(A.D[i]) >= CV1.P("D_AFASTAMENTO")) or (A.Lcor[i][1] >= CV1.P("L_PERNA_TARDIA"))
    pop = A.p1()
    ex0 = {x["i"]: A.exaustao(x["i"], t0) for x in pop}
    det = {"A0": lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d,
           "A2a": lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d and (ex0[i]["degrau"] >= 3 or ex0[i]["origem"] in ("E2", "E3")),
           "A2b": lambda i, d: ex0[i]["degrau"] >= 3 and ex0[i]["lado"] == -d}
    for lp in M.LP_GRADE:
        exl = {x["i"]: A.exaustao(x["i"], (lambda j, lp=lp: (abs(A.D[j]) >= CV1.P("D_AFASTAMENTO")) or (A.Lpiv[j] >= lp))) for x in pop}
        det[f"A1 Lp={lp}"] = (lambda i, d, exl=exl: exl[i]["degrau"] >= 2 and exl[i]["lado"] == -d)
    rot = {k: M.rotular(A, pop, k, f) for k, f in det.items()}
    res = dict(ativo=sim, periodos={p: NOME_PER[p] for p in PER},
               janela_do_extremo={p: dict(collections.Counter(x["janela"] for x in pop if A.periodo(x["i"]) == p)) for p in PER})
    res["percepcao"] = {k: {p: medir_p1(A, [x for x in v if A.periodo(x["i"]) == p]) for p in PER} for k, v in rot.items()}
    # escolha de Lp: tabela do desenvolvimento (agrupado), regra usada e regra correta
    tab = {k: res["percepcao"][k]["desenvolvimento"]["agrupado"] for k in rot if k.startswith("A1") or k == "A0"}
    res["escolha_Lp"] = dict(tabela_desenvolvimento={k: dict(n=v["n_exaustao"], diferenca_pp=v["diferenca_pp"]) for k, v in tab.items()},
                             regra_aplicada="maior diferença (precisão − base) no desenvolvimento, agrupado, com n ≥ 30; empate desfeito pela ORDEM ALFABÉTICA do nome (defeito do script)",
                             observacao="L por pivô ≥ 20 ocorre em ~1% das barras: com Lp=20 o detector A1 é praticamente o A0; escolher Lp=20 equivale a não mudar")
    res["operacional"] = {k: {p: medir_oper(A, [x for x in rot[k] if A.periodo(x["i"]) == p]) for p in PER} for k in ("A0", "A1 Lp=20", "A1 Lp=12", "A2a")}
    res["recortes"] = {k: {p: recortes(A, [x for x in rot[k] if A.periodo(x["i"]) == p]) for p in PER} for k in ("A0", "A1 Lp=12")}
    # rompimento fiel ao motor
    pend = A.pendentes(); a = A.a; p2 = {}
    for p in PER:
        for agrupado in (False, True):
            sub = [x for x in pend if A.periodo(x["i"]) == p]
            if agrupado: sub = M.desagrupar(sub)
            dec = [x for x in sub if x["verdade"] in ("SUSTENTADO", "FALSO")]
            linha = dict(n_pendentes=len(sub), sem_resolucao_verdade=len(sub) - len(dec), rearmou_antes_de_confirmar=sum(1 for x in sub if x["rearmou"] and x["A0"] is None),
                         base_sustentado=M.pct(sum(x["verdade"] == "SUSTENTADO" for x in dec), len(dec)))
            for r in ("A0", "A3"):
                cf = [x for x in sub if x[r] is not None]; cfd = [x for x in cf if x["verdade"] in ("SUSTENTADO", "FALSO")]
                ops = [A.barreiras(x[r], x["lado"]) for x in cf]; c = collections.Counter(o["res"] for o in ops)
                linha[r] = dict(confirmados=len(cf), cobertura_pct=M.pct(len(cf), len(sub)),
                                sustentado_entre_confirmados=M.pct(sum(x["verdade"] == "SUSTENTADO" for x in cfd), len(cfd)),
                                falsos_confirmados=sum(x["verdade"] == "FALSO" for x in cfd),
                                sustentados_nao_confirmados=sum(1 for x in sub if x[r] is None and x["verdade"] == "SUSTENTADO"),
                                entrada_favor=c["favor"], entrada_contra=c["contra"], entrada_ambigua=c["ambígua"], entrada_sem_resolucao=c["sem resolução"],
                                entrada_pct_favor=M.pct(c["favor"], c["favor"] + c["contra"]),
                                custo_espera_atr_mediana=(round(float(np.median([(a.c[x[r]] - a.c[x["i"]]) * x["lado"] / x["atr"] for x in cf])), 2) if cf else None))
            p2[f"{p}_{'agrupado' if agrupado else 'bruto'}"] = linha
    res["rompimento"] = p2
    return res


if __name__ == "__main__":
    out = {s: rodar(s) for s in sys.argv[1:]}
    json.dump(out, open(f"validacao_v2_{'_'.join(sys.argv[1:])}.json", "w"), ensure_ascii=False, indent=1, default=str)
    print("ok")
