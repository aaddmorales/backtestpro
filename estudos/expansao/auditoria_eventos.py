# -*- coding: utf-8 -*-
"""Auditoria dos contadores do estudo v2 (ordem 17/10 18:57 Kyiv, item 3).
Exporta cada evento com identificador, a regra de agrupamento aplicada e os denominadores de cada tabela, e recalcula os recortes
de duas formas: (a) reagrupando dentro de cada subgrupo (o que o v2 publicou) e (b) derivados de UMA população agrupada única."""
import csv, json, sys, collections
import alternativas as M
import validacao_v2 as V
CV1 = M.CV1


def eid(sim, x, tipo):
    return f"{sim}|{tipo}|{str(M.pd.Timestamp(x['ts']))[:16]}"


def rodar(sim, w):
    A = M.Ativo(sim)
    t0 = lambda i: (abs(A.D[i]) >= CV1.P("D_AFASTAMENTO")) or (A.Lcor[i][1] >= CV1.P("L_PERNA_TARDIA"))
    pop = A.p1()
    ex0 = {x["i"]: A.exaustao(x["i"], t0) for x in pop}
    rot = M.rotular(A, pop, "A0", lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d)
    for x in rot:
        x["ts"] = A.a.ts[x["i"]]
    out = {"ativo": sim, "regra_de_agrupamento": "ordena por barra; mantém um evento e descarta os seguintes do MESMO conjunto a menos de 16 barras M15 do último mantido (M.desagrupar)"}
    den = {}
    for p in V.PER:
        sub = [x for x in rot if A.periodo(x["i"]) == p]
        ex_b = [x for x in sub if x["rot"] == "exaustão"]
        ex_g = M.desagrupar(ex_b); pop_g = M.desagrupar(sub)
        ids_g = {x["i"] for x in ex_g}; ids_pop = {x["i"] for x in pop_g}
        den[p] = dict(populacao_bruta=len(sub), exaustoes_brutas=len(ex_b), populacao_agrupada=len(pop_g), exaustoes_agrupadas=len(ex_g),
                      exaustoes_agrupadas_que_tambem_estao_na_populacao_agrupada=len(ids_g & ids_pop),
                      nota="exaustões e população são agrupadas SEPARADAMENTE: a exaustão agrupada não é subconjunto da população agrupada")
        for x in sub:
            w.writerow([sim, p, "P1", str(M.pd.Timestamp(x["ts"]))[:16], x["i"], "alta" if x["d"] > 0 else "baixa", x["rot"],
                        "não renovado" if x["verdade"] == "FIM" else "renovado", int(x["i"] in ids_pop), int(x["i"] in ids_g), x["janela"]])
        # recortes (a) reagrupados por subgrupo  × (b) derivados da população agrupada única (pop_g e ex_g)
        rec = {}
        for nome, chave in (("direção", lambda x: "alta" if x["d"] > 0 else "baixa"), ("regime H1", lambda x: A.regime_h1(x["i"], x["d"]))):
            ga, gb = collections.defaultdict(list), collections.defaultdict(list)
            for x in sub: ga[chave(x)].append(x)
            for x in ex_g: gb[chave(x)].append(x)
            gpop = collections.defaultdict(list)
            for x in pop_g: gpop[chave(x)].append(x)
            rec[nome] = {}
            for k in sorted(set(ga) | set(gb)):
                ea = M.desagrupar([x for x in ga[k] if x["rot"] == "exaustão"])
                rec[nome][k] = dict(
                    reagrupado_no_subgrupo=dict(n_exaustao=len(ea), precisao=M.pct(sum(x["verdade"] == "FIM" for x in ea), len(ea))),
                    derivado_da_populacao_unica=dict(n_exaustao=len(gb[k]), precisao=M.pct(sum(x["verdade"] == "FIM" for x in gb[k]), len(gb[k])),
                                                     base=M.pct(sum(x["verdade"] == "FIM" for x in gpop[k]), len(gpop[k])), n_populacao=len(gpop[k])))
            rec[nome]["_soma"] = dict(reagrupado=sum(v["reagrupado_no_subgrupo"]["n_exaustao"] for kk, v in rec[nome].items() if not kk.startswith("_")),
                                      derivado=sum(v["derivado_da_populacao_unica"]["n_exaustao"] for kk, v in rec[nome].items() if not kk.startswith("_")),
                                      total_agrupado=len(ex_g))
        den[p]["recortes"] = rec
    out["denominadores"] = den
    return out


if __name__ == "__main__":
    with open("eventos_p1_v2.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ativo", "periodo", "populacao", "barra_m15_abertura_corretora", "indice_m15", "perna", "leitura_A0", "verdade_16b",
                    "na_populacao_agrupada", "na_exaustao_agrupada", "janela_do_extremo"])
        res = {s: rodar(s, w) for s in sys.argv[1:]}
    json.dump(res, open("auditoria_eventos_v2.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({s: {p: {k: v for k, v in d.items() if k != "recortes"} for p, d in r["denominadores"].items()} for s, r in res.items()}, ensure_ascii=False, indent=1))
    for s, r in res.items():
        for p, d in r["denominadores"].items():
            print(s, p, {n: v["_soma"] for n, v in d["recortes"].items()})
