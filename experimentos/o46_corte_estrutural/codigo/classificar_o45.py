"""ORDEM 045 — reprodução da O44 e classificação A/B/C (retorno ao extremo × perda do nível estrutural) em janela fixa de 15 min com fechamentos M1.
Diagnóstico: não altera a entrada nem a gestão. Uso: python classificar_o45.py SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formacao_o44 as FO, estrategia_o39 as ST, rodar_o44 as R44
O44 = "/home/claude/r005/lm044/saida/replay"; ESCOPO = [("XAUUSD", "M15"), ("XAUUSD", "M30"), ("BTCUSD", "M15")]; MIN = FO.MIN; JAN = 15


def classificar(lado, E, N, tau_ns, t1, c1):
    """janela [τ, τ+15 min): M1 com início nesse intervalo. Devolve grupo, completo, horários (fechamento) do 1º > E e do 1º > N."""
    a = int(np.searchsorted(t1, tau_ns)); b = int(np.searchsorted(t1, tau_ns + JAN * MIN)); cs = c1[a:b]; ts = t1[a:b]
    alem = (lambda x, y: x > y + 1e-9) if lado < 0 else (lambda x, y: x < y - 1e-9)
    kE = next((k for k in range(len(cs)) if alem(cs[k], E)), None); kN = next((k for k in range(len(cs)) if alem(cs[k], N)), None)
    g = "C" if kN is not None else ("B" if kE is not None else "A")
    fecha = lambda k: None if k is None else int(ts[k]) + MIN
    return {"grupo": g, "n_m1_janela": int(b - a), "completo": bool(b - a == JAN), "aviso_E_ns": fecha(kE), "aviso_N_ns": fecha(kN),
            "min_ate_E": None if kE is None else (fecha(kE) - tau_ns) / MIN, "min_ate_N": None if kN is None else (fecha(kN) - tau_ns) / MIN}


def boot_dif(x, y, f, n=2000):
    rng = np.random.default_rng(45); x, y = np.asarray(x, float), np.asarray(y, float)
    bs = [f(x[rng.integers(0, len(x), len(x))]) - f(y[rng.integers(0, len(y), len(y))]) for _ in range(n)]; lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"diferenca": round(float(f(x) - f(y)), 4), "IC95": [round(float(lo), 4), round(float(hi), 4)], "conclusao": "inconclusiva (IC95 inclui zero)" if lo <= 0 <= hi else ("C maior" if lo > 0 else "C menor")}


def resumo(d):
    if not len(d): return {"n": 0}
    return {"n": int(len(d)), "perdedoras_pct": round(float((d.iso_R < 0).mean() * 100), 1), "R_medio": round(float(d.iso_R.mean()), 4), "R_liquido": round(float(d.iso_R.sum()), 2),
            "stop_pct": round(float((d.iso_motivo_saida == "stop de proteção").mean() * 100), 1)}


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); R = {"reproducao_O44": {}, "por_escopo": {}}; TODOS = []
    m1s = {}
    for at, tf in ESCOPO:
        if at not in m1s: m1s[at] = ST.ler(at, "M1")
        m1 = m1s[at]; d = ST.ler(at, tf); mn = R44.TFS[tf]; ini, fim = R44.janela(at, m1)
        M = FO.Motor(at, d, m1, tf_min=mn); i0 = int(np.searchsorted(d.t.values, np.datetime64(ini))); i1 = int(np.searchsorted((d.t + pd.Timedelta(minutes=mn)).values, np.datetime64(fim), side="right"))
        M.rodar(i0=i0, i1=i1); S = R44.sinais_df(M); o = pd.DataFrame(M.ops["R0"])
        S44 = pd.read_csv(f"{O44}/O44_{at}_{tf}_sinais.csv", sep=";"); o44 = pd.read_csv(f"{O44}/O44_{at}_{tf}_operacoes.csv", sep=";")
        sup, sup44 = S[S.resultado_gatilho == "superou"], S44[S44.resultado_gatilho == "superou"]
        ok = (len(S) == len(S44) and (S.id.values == S44.id.values).all() and (S.resultado_gatilho.values == S44.resultado_gatilho.values).all()
              and (sup.t_superacao.astype(str).values == sup44.t_superacao.astype(str).values).all() and np.allclose(sup.iso_R.astype(float).values, sup44.iso_R.values, atol=1e-9)
              and len(o) == len(o44) and (o.id.values == o44.id.values).all() and np.allclose(o.R.values, o44.R.values, atol=1e-9))
        R["reproducao_O44"][f"{at}_{tf}"] = {"sinais": int(len(S)), "superacoes": int(len(sup)), "operacoes_carteira": int(len(o)), "R_carteira": round(float(o.R.sum()), 4), "R_O44": round(float(o44.R.sum()), 4), "identico": bool(ok)}
        print(at, tf, R["reproducao_O44"][f"{at}_{tf}"], flush=True)
        if not ok: raise SystemExit("BLOQUEIO: reprodução da O44 diferente — classificação não executada")
        # ── classificação ──
        t1 = M.t1; c1 = M.c1; rows = []
        for s in M.sinais:
            if s["resultado_gatilho"] != "superou": continue
            tau = int(pd.Timestamp(s["t_superacao"]).value); cl = classificar(s["lado"], s["extremo_rompimento"], s["referencia"], tau, t1, c1)
            rows.append({"id": s["id"], "ativo": at, "tf": tf, "lado": s["lado"], "tau": s["t_superacao"], "E_extremo": s["extremo_rompimento"], "N_nivel": s["referencia"], **cl})
        C = pd.DataFrame(rows).merge(sup[["id", "iso_R", "iso_motivo_saida", "iso_t_sai", "iso_entrada", "iso_saida", "iso_ambiguo", "barra_rompimento", "R0_carteira"]], on="id")
        C["t_sai_ns"] = C.iso_t_sai.astype(np.int64)
        for k in ("E", "N"):
            C[f"aviso_{k}_antes_da_saida"] = [None if pd.isna(a) else bool(int(a) <= ts) for a, ts in zip(C[f"aviso_{k}_ns"], C.t_sai_ns)]
        C["aviso_grupo_antes_da_saida"] = [r.aviso_N_antes_da_saida if r.grupo == "C" else (r.aviso_E_antes_da_saida if r.grupo == "B" else None) for r in C.itertuples()]
        C["posterior_RETROSPECTIVO"] = pd.to_datetime(C.tau) >= "2026-05-01"
        C["aviso_E"] = [None if pd.isna(x) else str(pd.Timestamp(int(x))) for x in C.aviso_E_ns]; C["aviso_N"] = [None if pd.isna(x) else str(pd.Timestamp(int(x))) for x in C.aviso_N_ns]
        C["saida"] = [str(pd.Timestamp(int(x))) for x in C.t_sai_ns]
        TODOS.append(C); C.drop(columns=["aviso_E_ns", "aviso_N_ns", "t_sai_ns"]).to_csv(f"{out}/O45_{at}_{tf}_classificacao.csv", index=False, sep=";")
    T = pd.concat(TODOS, ignore_index=True)
    def bloco(d):
        comp = d[d.completo]; r = {"incompletos": {"n": int((~d.completo).sum()), "por_grupo": d[~d.completo].grupo.value_counts().to_dict(), **{g: resumo(d[(~d.completo) & (d.grupo == g)]) for g in "ABC"}}}
        r["grupos"] = {g: resumo(comp[comp.grupo == g]) for g in "ABC"}; r["total_completos"] = resumo(comp)
        b, c = comp[comp.grupo == "B"], comp[comp.grupo == "C"]
        if len(b) > 1 and len(c) > 1:
            r["C_x_B"] = {"perdedoras_pp": {k: (v * 100 if k != "conclusao" and not isinstance(v, list) else ([x * 100 for x in v] if isinstance(v, list) else v)) for k, v in boot_dif(c.iso_R < 0, b.iso_R < 0, np.mean).items()},
                          "R_medio": boot_dif(c.iso_R, b.iso_R, np.mean)}
            r["C_x_B"]["perdedoras_pp"] = {k: (round(v, 1) if isinstance(v, float) else ([round(x, 1) for x in v] if isinstance(v, list) else v)) for k, v in r["C_x_B"]["perdedoras_pp"].items()}
        r["aviso"] = {}
        for g in "BC":
            x = comp[comp.grupo == g]; an, dep = x[x.aviso_grupo_antes_da_saida == True], x[x.aviso_grupo_antes_da_saida == False]
            r["aviso"][g] = {"antes_da_saida": resumo(an), "depois_da_saida": resumo(dep), "minutos_ate_aviso_mediana": None if not len(x) else float((x.min_ate_N if g == "C" else x.min_ate_E).median())}
        # B que perde → quantos cruzam o nível depois da janela? (só descreve; fora do escopo) — não calculado
        r["por_lado"] = {("venda" if l < 0 else "compra"): {g: resumo(comp[(comp.lado == l) & (comp.grupo == g)]) for g in "ABC"} for l in (-1, 1)}
        r["por_bloco"] = {("posterior_RETROSPECTIVO" if p else "desenvolvimento"): {g: resumo(comp[(comp.posterior_RETROSPECTIVO == p) & (comp.grupo == g)]) for g in "ABC"} for p in (False, True)}
        r["carteira_O44"] = {g: resumo(comp[(comp.grupo == g) & (comp.R0_carteira == "entrou")]) for g in "ABC"}
        r["sem_ambiguos"] = {g: resumo(comp[(comp.grupo == g) & ~comp.iso_ambiguo.astype(bool)]) for g in "ABC"}
        return r
    for (at, tf), C in zip(ESCOPO, TODOS): R["por_escopo"][f"{at}_{tf}"] = bloco(C)
    R["conjunto"] = bloco(T)
    json.dump(R, open(f"{out}/O45_resultado.json", "w"), ensure_ascii=False, indent=1, default=str); print(json.dumps({k: R[k] for k in ("por_escopo", "conjunto")}, ensure_ascii=False, default=str)[:9000])


if __name__ == "__main__": main()
