"""ORDEM 043 — replay contínuo (carteira, uma posição por ativo e por regra) + comparação POR SINAL (cada sinal simulado isoladamente) R0 × R1 × R2.
Uso: python rodar_o43.py ATIVO SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formacao_o43 as FO, estrategia_o39 as ST
CORTE = "2026-05-01"


def plano(sig):
    L = sig.get("leitura") or {}; mk = L.get("m1_marcas") or {}
    out = {k: v for k, v in sig.items() if k not in ("leitura", "tentativas")}
    out["tentativas"] = "; ".join(f"{t['barra']} tipo {t['tipo']}" for t in sig["tentativas"])
    out.update({"tau": L.get("tau"), "m1_estado": L.get("m1_estado"), "m1_avanco": mk.get("avanco"), "m1_rejeicao": mk.get("rejeicao"), "m1_pressao": mk.get("pressao_contraria"),
                "m1_marcas_15": " ".join(L.get("m1_marcas_15") or []), "m1_defasagem_min": L.get("m1_defasagem_min"), "m5_estado": L.get("m5_estado"), "m5_o42_contraria": L.get("m5_o42_contraria"),
                "m5_3": " | ".join(f"{x['fim'][11:16]} o{x['o']:.2f} c{x['c']:.2f}" for x in (L.get("m5_3") or [])), "m5_defasagem_min": L.get("m5_defasagem_min")})
    return out


def met(o, m1, K, eq_fn=True):
    if not len(o): return {"n": 0}
    eq = ST.curva(o, m1, K) if eq_fn else None; return ST.metricas(o, eq)


def main():
    at, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); t0 = time.time()
    m15, m1 = ST.ler(at, "M15"), ST.ler(at, "M1"); M = FO.Motor(at, m15, m1); M.rodar(i0=25); K = ST.CUSTO[at]
    S = pd.DataFrame([plano(s) for s in M.sinais]); R = {"ativo": at, "versao": FO.VERSAO, "segundos": None}
    # ── disponibilidade dos dados ──
    sup = S[S.resultado_gatilho == "superou"].copy()
    R["dados"] = {"sinais": int(len(S)), "por_resultado_gatilho": S.resultado_gatilho.value_counts().to_dict(), "vendas": int((S.lado < 0).sum()), "compras": int((S.lado > 0).sum()),
                  "barra_seguinte_com_15_M1": int((S.n_m1_barra == 15).sum()) if "n_m1_barra" in S else None,
                  "leitura_ausente_no_instante": int(sup.m1_estado.isna().sum()), "m1_defasada_no_instante(>0 min)": int((sup.m1_defasagem_min > 0).sum()),
                  "m5_sem_dados": int((sup.m5_estado == "SEM DADOS").sum()), "m5_defasagem_min_distribuicao": sup.m5_defasagem_min.value_counts().sort_index().to_dict(),
                  "superacao_com_lacuna_na_abertura": int(sup.lacuna_na_abertura.sum()), "primeiro_M1": str(m1.t.iloc[0]), "ultimo_M1": str(m1.t.iloc[-1])}
    # n_m1 da barra seguinte vem dos registros de expiração; para superadas, conta direto
    nm = []
    for s in M.sinais:
        i = int(np.searchsorted(M.t15, pd.Timestamp(s["barra_gatilho"]).value)); a, b = M.m1_da_barra(i); nm.append(b - a)
    S["n_m1_barra_seguinte"] = nm; R["dados"]["barra_seguinte_com_15_M1"] = int((S.n_m1_barra_seguinte == 15).sum()); R["dados"]["barra_seguinte_sem_M1"] = int((S.n_m1_barra_seguinte == 0).sum())
    # ── por sinal (isolado) ──
    iso = []
    for s in M.sinais:
        if s["resultado_gatilho"] != "superou": iso.append(None); continue
        iso.append(M.isolada(s))
    S["iso_R"] = [None if o is None else o["R"] for o in iso]; S["iso_usd_1lote"] = [None if o is None else o["usd_1lote"] for o in iso]; S["iso_motivo_saida"] = [None if o is None else o["motivo_saida"] for o in iso]
    S["iso_mfe_R"] = [None if o is None else o["mfe"] for o in iso]; S["iso_ambiguo"] = [None if o is None else o["ambiguo"] for o in iso]; S["iso_stop_na_m1_entrada"] = [None if o is None else o["stop_na_m1_entrada"] for o in iso]
    S["iso_t_sai"] = [None if o is None else str(pd.Timestamp(int(o["t_sai"]))) for o in iso]; S["iso_entrada"] = [None if o is None else o["entrada"] for o in iso]
    S["iso_saida_primeira_barra"] = [None if o is None else bool(o["t_sai"] <= pd.Timestamp(s["barra_gatilho"]).value + 2 * FO.M15) for o, s in zip(iso, M.sinais)]
    v = S[S.iso_R.notna()].copy(); v["posterior"] = pd.to_datetime(v.tau) >= CORTE
    def por_sinal(d, r):
        des = d[d[f"{r}_decisao"] == "descarta"]; ent = d[d[f"{r}_decisao"] == "entra"]
        return {"sinais_superados": int(len(d)), "entra": int(len(ent)), "descarta": int(len(des)),
                "perdas_evitadas": {"n": int((des.iso_R < 0).sum()), "R": round(float(des.iso_R[des.iso_R < 0].sum()), 2)},
                "ganhos_de_fora": {"n": int((des.iso_R > 0).sum()), "R": round(float(des.iso_R[des.iso_R > 0].sum()), 2)},
                "diferenca_liquida_R_vs_R0": round(float(-des.iso_R.sum()), 2), "R_R0": round(float(d.iso_R.sum()), 2), "R_regra": round(float(ent.iso_R.sum()), 2),
                "expectativa_entradas": round(float(ent.iso_R.mean()), 4) if len(ent) else None, "expectativa_descartadas": round(float(des.iso_R.mean()), 4) if len(des) else None,
                "acerto_entradas": round(float((ent.iso_R > 0).mean()), 4) if len(ent) else None, "acerto_descartadas": round(float((des.iso_R > 0).mean()), 4) if len(des) else None}
    R["por_sinal"] = {}
    for r in ("R1", "R2"):
        R["por_sinal"][r] = {"todos": por_sinal(v, r), "sem_ambiguos": por_sinal(v[~v.iso_ambiguo.astype(bool)], r), "vendas": por_sinal(v[v.lado < 0], r), "compras": por_sinal(v[v.lado > 0], r),
                             "desenvolvimento": por_sinal(v[~v.posterior], r), "posterior_RETROSPECTIVO": por_sinal(v[v.posterior], r)}
        # IC95 da diferença por bootstrap de dias
        rng = np.random.default_rng(1); dd = (-(v[f"{r}_decisao"] == "descarta") * v.iso_R).groupby(pd.to_datetime(v.tau).dt.floor("D")).sum().values
        bs = [dd[rng.integers(0, len(dd), len(dd))].sum() for _ in range(2000)]; R["por_sinal"][r]["todos"]["IC95_diferenca_R"] = [round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)]
    R["leituras_no_instante"] = {"M1xM5": v.groupby(["m1_estado", "m5_estado"]).size().rename("n").reset_index().assign(R_medio=lambda d: [round(float(v[(v.m1_estado == a) & (v.m5_estado == b)].iso_R.mean()), 3) for a, b in zip(d.m1_estado, d.m5_estado)]).to_dict("records")}
    # conhecido na entrada × desfecho (descritivo, sem limiar)
    v["devolveu_15min"] = v.desfecho_devolucao_min.notna()
    R["desfecho"] = {r: {dec: {"n": int(len(g)), "devolveu_em_15min": round(float(g.devolveu_15min.mean()), 3), "R_medio": round(float(g.iso_R.mean()), 3), "MFE_mediano_R": round(float(g.iso_mfe_R.median()), 3),
                               "amp_rompimento_atr_mediana": round(float(g.amp_rompimento_atr.median()), 3), "dist_prox_nivel_atr_mediana": None if g.prox_nivel_dist_atr.dropna().empty else round(float(g.prox_nivel_dist_atr.median()), 3),
                               "sem_nivel_a_frente": int(g.prox_nivel_dist_atr.isna().sum())}
                         for dec, g in v.groupby(f"{r}_decisao")} for r in ("R1", "R2")}
    R["isoladas"] = {"ambiguos": int(v.iso_ambiguo.sum()), "lacuna": int(v.lacuna_na_abertura.sum()), "stop_na_m1_entrada": int(v.iso_stop_na_m1_entrada.sum()),
                     "saida_ja_no_fechamento_da_barra_seguinte": int(v.iso_saida_primeira_barra.sum()), "motivos": v.iso_motivo_saida.value_counts().to_dict()}
    # ── carteira contínua ──
    R["carteira"] = {}; cut = int(np.searchsorted(m1.t.values, np.datetime64(CORTE)))
    for r in FO.REGRAS:
        o = pd.DataFrame(M.ops[r])
        if not len(o): R["carteira"][r] = {"n": 0}; continue
        eq = ST.curva(o, m1, K); post = pd.to_datetime(o.t_ent) >= CORTE
        R["carteira"][r] = {"geral": ST.metricas(o, eq), "desenvolvimento": ST.metricas(o[~post], eq[:cut]), "posterior_RETROSPECTIVO": ST.metricas(o[post], eq[cut:] - eq[cut]),
                            "vendas": ST.metricas(o[o.lado < 0]), "compras": ST.metricas(o[o.lado > 0]), "ambiguas": int(o.ambiguo.sum()),
                            "bloqueados_por_posicao_aberta": int(sum(1 for x in M.reg if x["decisao"] == "bloqueado_posicao_aberta" and x["regra"] == r)), "aberta_no_fim": M.pos[r] is not None}
        o.drop(columns=["j_ent", "j_sai"]).to_csv(f"{out}/O43_{at}_{r}_operacoes.csv", index=False, sep=";")
    S.to_csv(f"{out}/O43_{at}_sinais.csv", index=False, sep=";"); pd.DataFrame(M.reg).to_csv(f"{out}/O43_{at}_decisoes.csv.gz", index=False, sep=";")
    R["segundos"] = round(time.time() - t0, 1); json.dump(R, open(f"{out}/O43_{at}_resultado.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: R[k] for k in ("dados", "por_sinal", "isoladas")}, ensure_ascii=False, indent=1, default=str)[:6000])
    for r in FO.REGRAS: g = R["carteira"][r]["geral"]; print(r, g["n"], g["R_total"], g.get("IC95_expectativa_R"), g.get("drawdown_mtm_usd_1lote"))


if __name__ == "__main__": main()
