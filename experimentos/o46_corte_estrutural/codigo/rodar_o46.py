"""ORDEM 046 — G0 (O44) × G1 (corte estrutural com confirmação M15): reprodução da O44, comparação PAREADA (mesmas entradas, simulação isolada)
e carteiras contínuas separadas. Uso: python rodar_o46.py SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formacao_o44 as FO, estrategia_o39 as ST, rodar_o44 as R44, corte_o46 as CT
O44 = "/home/claude/r005/lm044/saida/replay"; O45 = "/home/claude/r005/lm045/saida"; ESCOPO = [("XAUUSD", "M15"), ("XAUUSD", "M30"), ("BTCUSD", "M15")]; CORTE = "2026-05-01"; MIN = CT.MIN


def boot_dias(dif_por_dia, n=2000):
    d = np.asarray(dif_por_dia, float); rng = np.random.default_rng(46); bs = [d[rng.integers(0, len(d), len(d))].sum() for _ in range(n)]; lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"diferenca_R": round(float(d.sum()), 2), "IC95": [round(float(lo), 2), round(float(hi), 2)], "conclusao": "inconclusiva (IC95 inclui zero)" if lo <= 0 <= hi else ("G1 maior" if lo > 0 else "G1 menor")}


def carteira(P, col_sai):
    """filtro cronológico de uma posição por ativo (regra do motor: entra se a última saída ≤ M1 do gatilho)."""
    ult = -1; sel = []
    for r in P.sort_values("j_ent").itertuples():
        if r.j_ent >= ult: sel.append(r.Index); ult = getattr(r, col_sai)
    return P.loc[sel]


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); R = {"versao": CT.VERSAO, "reproducao_O44": {}, "escopos": {}}; m1s, m15s = {}, {}
    for at, tf in ESCOPO:
        t0 = time.time()
        if at not in m1s: m1s[at] = ST.ler(at, "M1"); m15s[at] = ST.ler(at, "M15")
        m1, m15 = m1s[at], m15s[at]; d = m15 if tf == "M15" else ST.ler(at, tf); mn = R44.TFS[tf]; ini, fim = R44.janela(at, m1); K = ST.CUSTO[at]
        M = FO.Motor(at, d, m1, tf_min=mn); i0 = int(np.searchsorted(d.t.values, np.datetime64(ini))); i1 = int(np.searchsorted((d.t + pd.Timedelta(minutes=mn)).values, np.datetime64(fim), side="right"))
        M.rodar(i0=i0, i1=i1); o = pd.DataFrame(M.ops["R0"]); o44 = pd.read_csv(f"{O44}/O44_{at}_{tf}_operacoes.csv", sep=";")
        sup = [s for s in M.sinais if s["resultado_gatilho"] == "superou"]; iso = [M.isolada(s) for s in sup]
        ok = len(o) == len(o44) and (o.id.values == o44.id.values).all() and np.allclose(o.R.values, o44.R.values, atol=1e-9)
        R["reproducao_O44"][f"{at}_{tf}"] = {"operacoes": int(len(o)), "R": round(float(o.R.sum()), 4), "R_O44": round(float(o44.R.sum()), 4), "identico": bool(ok), "superacoes": len(sup)}
        print(at, tf, R["reproducao_O44"][f"{at}_{tf}"], flush=True)
        if not ok: raise SystemExit("BLOQUEIO: O44 não reproduzida")
        mk = CT.Mercado(m1, m15); rows = []
        for s, op in zip(sup, iso):
            if op is None: continue
            base = {"id": s["id"], "lado": s["lado"], "N": s["referencia"], "j_ent": int(op["j_ent"]), "j_sai_G0": int(op["j_sai"]), "t_ent": str(pd.Timestamp(int(op["t_ent"]))),
                    "t_sai_G0": str(pd.Timestamp(int(op["t_sai"]))), "entrada": op["entrada"], "stop": op["stop"], "R_G0": op["R"], "usd_G0": op["usd_1lote"], "motivo_G0": op["motivo_saida"], "ambiguo_entrada": op["ambiguo"]}
            for dz in (0.0, 1.0, 2.0):
                e = CT.corte(mk, op, s["referencia"], K, desl=dz); suf = {0.0: "_d0", 1.0: "", 2.0: "_d2"}[dz]
                base[f"R_G1{suf}"] = e["R_G1"]; base[f"usd_G1{suf}"] = e["usd_G1"]
                if dz == 1.0:
                    base.update({"n_alertas": e["n_alertas"], "recuperados": e["recuperados"], "expirados": e["expirados"], "encerrados_por_G0": e["encerrados_por_G0"], "confirmado": e["confirmado"],
                                 "cortou": e["cortou"], "empate": e["empate"], "ordem_incerta": e["ordem_incerta"], "j_sai_G1": int(e["j_sai_G1"]), "t_sai_G1": str(pd.Timestamp(int(mk.t1[e["j_sai_G1"]]))),
                                 "px_corte": e.get("px_corte"), "aviso_vs_saida_G0": e.get("aviso_vs_saida_G0"), "t_alerta1": None if e["j_alerta1"] is None else str(pd.Timestamp(int(mk.t1[e["j_alerta1"]]) + MIN)),
                                 "t_decisao15": None if e["t_decisao15"] is None else str(pd.Timestamp(e["t_decisao15"])), "alertas": json.dumps([{k: (str(pd.Timestamp(v)) if k.startswith("t_") and v else v) for k, v in a.items()} for a in e["alertas"]], ensure_ascii=False)})
            base["mfe_G0"] = CT.mfe(mk, op, op["j_sai"]); base["mfe_G1"] = CT.mfe(mk, op, base["j_sai_G1"]); rows.append(base)
        P = pd.DataFrame(rows); P["dif"] = P.R_G1 - P.R_G0; P["posterior"] = pd.to_datetime(P.t_ent) >= CORTE; P["dia"] = pd.to_datetime(P.t_ent).dt.floor("D")
        P.to_csv(f"{out}/O46_{at}_{tf}_pareado.csv", index=False, sep=";")
        dias = pd.date_range(ini.floor("D"), fim.floor("D"), freq="D")
        def pareado(Q, dd=dias, col="R_G1"):
            c = Q[Q.cortou]; dif = Q[col] - Q.R_G0
            red = c[(c[col] > c.R_G0) & (c.R_G0 < 0)]; cort = c[c[col] < c.R_G0]; mel = c[(c[col] > c.R_G0) & (c.R_G0 >= 0)]
            daily = dif.groupby(Q.dia).sum().reindex(dd, fill_value=0).values
            return {"operacoes": int(len(Q)), "cortes": int(len(c)), "R_G0": round(float(Q.R_G0.sum()), 2), "R_G1": round(float(Q[col].sum()), 2),
                    "perdas_reduzidas": {"n": int(len(red)), "R_preservado": round(float((red[col] - red.R_G0).sum()), 2)},
                    "ganhos_cortados": {"n": int(len(cort)), "R_retirado": round(float((cort[col] - cort.R_G0).sum()), 2), "dos_quais_G0_vencedora": int((cort.R_G0 > 0).sum())},
                    "corte_melhor_com_G0_vencedora": int(len(mel)), "saldo": boot_dias(daily)}
        A = P[P.n_alertas > 0]; C = P[P.cortou]
        E = {"contadores": {"superacoes": int(len(P)), "operacoes_com_alerta": int(len(A)), "alertas": int(P.n_alertas.sum()), "recuperacoes": int(P.recuperados.sum()), "expirados": int(P.expirados.sum()),
                            "encerrados_pela_saida_G0_antes_da_decisao": int(P.encerrados_por_G0.sum()), "confirmacoes": int(P.confirmado.sum()), "cortes_antecipados": int(P.cortou.sum()),
                            "empates": int(P.empate.sum()), "confirmado_mas_G0_antes_da_execucao": int((P.confirmado & ~P.cortou & ~P.empate).sum()), "ordem_incerta": int(P.ordem_incerta.sum()),
                            "aviso_1o_alerta_vs_saida_G0": A.aviso_vs_saida_G0.value_counts().to_dict()},
             "pareado": pareado(P), "pareado_sem_ordem_incerta": pareado(P[~P.ordem_incerta]), "pareado_sem_ambiguos_de_entrada": pareado(P[~P.ambiguo_entrada.astype(bool)]),
             "deslizamento": {f"{k}x_spread": pareado(P, col=c)["saldo"] for k, c in ((0, "R_G1_d0"), (1, "R_G1"), (2, "R_G1_d2"))},
             "desenvolvimento": pareado(P[~P.posterior], dias[dias < CORTE]), "posterior_RETROSPECTIVO": pareado(P[P.posterior], dias[dias >= CORTE])}
        if len(C):
            g = (pd.to_datetime(C.t_sai_G0) - pd.to_datetime(C.t_sai_G1)).dt.total_seconds() / 60
            E["tempo"] = {"minutos_ganhos_mediana": float(g.median()), "minutos_ganhos_media": round(float(g.mean()), 1), "min_ate_alerta_mediana": float(((pd.to_datetime(C.t_alerta1) - pd.to_datetime(C.t_ent)).dt.total_seconds() / 60).median())}
            E["devolucao_do_pico_R"] = {"G0_media_nos_cortados": round(float((C.mfe_G0 - C.R_G0).mean()), 3), "G1_media_nos_cortados": round(float((C.mfe_G1 - C.R_G1).mean()), 3),
                                        "G0_media_todas": round(float((P.mfe_G0 - P.R_G0).mean()), 3), "G1_media_todas": round(float((P.mfe_G1 - P.R_G1).mean()), 3)}
            E["cortados_resultado_G0"] = {"perdedoras": int((C.R_G0 < 0).sum()), "vencedoras": int((C.R_G0 > 0).sum()), "R_G0": round(float(C.R_G0.sum()), 2), "R_G1": round(float(C.R_G1.sum()), 2),
                                          "motivo_G0": C.motivo_G0.value_counts().to_dict()}
        # carteiras contínuas separadas
        c0 = carteira(P, "j_sai_G0"); c1 = carteira(P, "j_sai_G1")
        same = len(c0) == len(o) and set("R0-" + c0.id) == set(o.id) and abs(float(c0.R_G0.sum()) - float(o.R.sum())) < 1e-9
        def ops(Q, g):
            x = pd.DataFrame({"id": Q.id.values, "lado": Q.lado.values, "j_ent": Q.j_ent.values, "j_sai": Q[f"j_sai_{g}"].values, "entrada": Q.entrada.values, "R": Q[f"R_{g}"].values, "usd_1lote": Q[f"usd_{g}"].values,
                              "t_ent": pd.to_datetime(Q.t_ent).values.astype("datetime64[ns]").astype(np.int64), "custo_com_usd": 2 * K["com_lado"], "motivo_saida": np.where(Q.cortou.values & (g == "G1"), "corte estrutural", Q.motivo_G0.values)})
            return x
        O0, O1 = ops(c0, "G0"), ops(c1, "G1"); h = lambda Q: ((pd.to_datetime(Q[f"t_sai_{'G1' if Q is c1 else 'G0'}"]) - pd.to_datetime(Q.t_ent)).dt.total_seconds() / 3600).sum()
        horas_tot = (fim - ini) / pd.Timedelta(hours=1)
        def met(X, Q, col):
            m = ST.metricas(X, ST.curva(X, m1, K)); m["tempo_em_posicao_pct"] = round(float(((pd.to_datetime(Q[col]) - pd.to_datetime(Q.t_ent)).dt.total_seconds() / 3600).sum() / horas_tot * 100), 2)
            cum = np.cumsum(X.sort_values("j_sai").R.values); m["DD_R_fechadas"] = round(float((cum - np.maximum.accumulate(np.r_[0, cum])[1:]).min()), 2); return m
        d0 = O0.R.groupby(pd.to_datetime(O0.t_ent).dt.floor("D")).sum().reindex(dias, fill_value=0); d1 = O1.R.groupby(pd.to_datetime(O1.t_ent).dt.floor("D")).sum().reindex(dias, fill_value=0)
        post0, post1 = pd.to_datetime(O0.t_ent) >= CORTE, pd.to_datetime(O1.t_ent) >= CORTE
        E["carteira"] = {"G0_reproduz_O44": bool(same), "G0": met(O0, c0, "t_sai_G0"), "G1": met(O1, c1, "t_sai_G1"), "diferenca_G1_G0": boot_dias((d1 - d0).values),
                         "entradas_liberadas_pelo_G1": int((~c1.id.isin(c0.id)).sum()), "entradas_G0_perdidas_no_G1": int((~c0.id.isin(c1.id)).sum()),
                         "posterior_RETROSPECTIVO": {"G0": {"n": int(post0.sum()), "R": round(float(O0.R[post0].sum()), 2)}, "G1": {"n": int(post1.sum()), "R": round(float(O1.R[post1].sum()), 2)}}}
        # correção do tempo da O45 (grupo C) — anterior / simultâneo / posterior
        C45 = pd.read_csv(f"{O45}/O45_{at}_{tf}_classificacao.csv", sep=";"); C45 = C45[C45.completo & (C45.grupo == "C")]
        ta, ts = pd.to_datetime(C45.aviso_N), pd.to_datetime(C45.saida)
        E["correcao_O45_grupo_C"] = {"anterior": int((ta < ts).sum()), "simultaneo": int((ta == ts).sum()), "posterior": int((ta > ts).sum()), "O45_contou_antes": int((C45.aviso_grupo_antes_da_saida == True).sum())}
        R["escopos"][f"{at}_{tf}"] = E; print(json.dumps(E, ensure_ascii=False, default=str)[:3000], round(time.time() - t0), "s", flush=True)
    json.dump(R, open(f"{out}/O46_resultado.json", "w"), ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__": main()
