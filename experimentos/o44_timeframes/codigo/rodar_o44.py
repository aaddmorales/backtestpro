"""ORDEM 044 — (1) reprodução da R0 da O43 no M15 com os dados originais; (2) M15 × M30 × H1 no MESMO intervalo por ativo: ruído (por superação)
e desempenho (carteira contínua de cada TF), com incerteza da diferença (bootstrap por dia). Uso: python rodar_o44.py ATIVO SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formacao_o44 as FO, estrategia_o39 as ST
TFS = {"M15": 15, "M30": 30, "H1": 60}; CORTE = "2026-05-01"; O43 = "/home/claude/r005/lm043/saida/replay"; MIN = FO.MIN


def janela(at, m1):
    h1 = ST.ler(at, "H1"); t300 = h1.t.iloc[300]; ini = (t300 + pd.offsets.MonthBegin(1)).normalize(); fim = m1.t.iloc[-1] + pd.Timedelta(minutes=1); return ini, fim


def sinais_df(M):
    rows = []
    for s in M.sinais:
        r = {k: v for k, v in s.items() if k not in ("leitura", "tentativas")}; r["tentativas"] = "; ".join(f"{t['barra']} tipo {t['tipo']}" for t in s["tentativas"]); rows.append(r)
    S = pd.DataFrame(rows)
    iso = [M.isolada(s) if s["resultado_gatilho"] == "superou" else None for s in M.sinais]
    for k in ("R", "usd_1lote", "motivo_saida", "mfe", "ambiguo", "stop_na_m1_entrada", "entrada", "saida", "t_sai"): S[f"iso_{k}"] = [None if o is None else o[k] for o in iso]
    return S


def ops_df(M, at, fim_ns):
    o = pd.DataFrame(M.ops["R0"])
    if not len(o): return o
    K = ST.CUSTO[at]; sp = M.sp
    o["spread_usd"] = [(sp[a] if l > 0 else sp[b]) * K["contrato"] for a, b, l in zip(o.j_ent, o.j_sai, o.lado)]
    o["horas"] = (o.t_sai - o.t_ent) / (60 * MIN); return o


def met(o, m1, K, meses, horas_tot):
    if not len(o): return {"n": 0}
    eq = ST.curva(o, m1, K); m = ST.metricas(o, eq)
    m.update({"R_por_operacao": m["expectativa_R"], "R_por_mes": round(float(o.R.sum() / meses), 3), "spread_usd_estimado": round(float(o.spread_usd.sum()), 2),
              "tempo_em_posicao_pct": round(float(o.horas.sum() / horas_tot * 100), 2), "duracao_mediana_h": round(float(o.horas.median()), 2), "duracao_media_h": round(float(o.horas.mean()), 2),
              "vendas": {"n": int((o.lado < 0).sum()), "R": round(float(o.R[o.lado < 0].sum()), 2)}, "compras": {"n": int((o.lado > 0).sum()), "R": round(float(o.R[o.lado > 0].sum()), 2)}})
    return m


def ruido(S, meses):
    sup = S[S.resultado_gatilho == "superou"]; n = len(sup)
    r15, rb = sup.retorno_15min_min.notna(), sup.retorno_fim_barra_min.notna(); perd = sup.iso_R < 0
    pc = lambda x: round(float(x) * 100, 1)
    return {"formacoes": int(len(S)), "formacoes_por_mes": round(len(S) / meses, 1), "superacoes": n, "superacoes_por_mes": round(n / meses, 1),
            "toque_sem_superacao": int((S.resultado_gatilho == "toque sem superação").sum()), "nao_alcancou": int((S.resultado_gatilho == "não alcançou").sum()),
            "retorno_15min": {"n": int(r15.sum()), "pct": pc(r15.mean())}, "retorno_ate_fim_da_barra_do_TF": {"n": int(rb.sum()), "pct": pc(rb.mean())},
            "operacao_isolada_perdedora": {"n": int(perd.sum()), "pct": pc(perd.mean())},
            "cruzamento_retorno15_x_perdedora": {"voltou_e_perdeu": int((r15 & perd).sum()), "voltou_e_nao_perdeu": int((r15 & ~perd).sum()), "nao_voltou_e_perdeu": int((~r15 & perd).sum()), "nao_voltou_e_nao_perdeu": int((~r15 & ~perd).sum())},
            "minutos_ate_retorno_mediana_15min": None if not r15.any() else float(sup.retorno_15min_min.median()),
            "ambiguos": int(sup.iso_ambiguo.astype(bool).sum()), "lacuna": int(sup.lacuna_na_abertura.sum()), "stop_na_m1_entrada": int(sup.iso_stop_na_m1_entrada.astype(bool).sum())}


def dif_boot(a, b, dias, n=2000):
    """IC95 da diferença de R total (a − b) reamostrando dias (as séries diárias somam R por dia de ENTRADA; dias sem operação = 0)."""
    da = a.groupby(pd.to_datetime(a.t_ent).dt.floor("D")).R.sum().reindex(dias, fill_value=0).values if len(a) else np.zeros(len(dias))
    db = b.groupby(pd.to_datetime(b.t_ent).dt.floor("D")).R.sum().reindex(dias, fill_value=0).values if len(b) else np.zeros(len(dias))
    d = da - db; rng = np.random.default_rng(44); bs = [d[rng.integers(0, len(d), len(d))].sum() for _ in range(n)]
    lo, hi = np.percentile(bs, 2.5), np.percentile(bs, 97.5)
    return {"diferenca_R": round(float(d.sum()), 2), "IC95": [round(float(lo), 2), round(float(hi), 2)], "conclusao": "inconclusiva (IC95 inclui zero)" if lo <= 0 <= hi else ("primeiro maior" if lo > 0 else "segundo maior")}


def dif_prop(x, y, n=2000):
    """IC95 da diferença de proporções (bootstrap independente)."""
    rng = np.random.default_rng(44); x, y = np.asarray(x, float), np.asarray(y, float)
    bs = [x[rng.integers(0, len(x), len(x))].mean() - y[rng.integers(0, len(y), len(y))].mean() for _ in range(n)]
    lo, hi = np.percentile(bs, 2.5) * 100, np.percentile(bs, 97.5) * 100
    return {"diferenca_pp": round(float((x.mean() - y.mean()) * 100), 1), "IC95_pp": [round(float(lo), 1), round(float(hi), 1)], "conclusao": "inconclusiva (IC95 inclui zero)" if lo <= 0 <= hi else ("primeiro maior" if lo > 0 else "segundo maior")}


def main():
    at, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); t0 = time.time(); m1 = ST.ler(at, "M1"); K = ST.CUSTO[at]; R = {"ativo": at, "versao": FO.VERSAO}
    # ── 1. reprodução da O43 R0 (dados originais, mesmo i0) ──
    m15 = ST.ler(at, "M15"); M = FO.Motor(at, m15, m1, tf_min=15); M.rodar(i0=25); o = pd.DataFrame(M.ops["R0"]); ref = pd.read_csv(f"{O43}/O43_{at}_R0_operacoes.csv", sep=";")
    S43 = pd.read_csv(f"{O43}/O43_{at}_sinais.csv", sep=";"); S44 = pd.DataFrame(M.sinais)
    iguais = len(o) == len(ref) and (o.id.values == ref.id.values).all() and np.allclose(o.R.values, ref.R.values, atol=1e-9) and (o.t_ent.values == ref.t_ent.values).all() and (o.t_sai.values == ref.t_sai.values).all()
    R["reproducao_O43_R0"] = {"operacoes_O43": int(len(ref)), "operacoes_O44_M15": int(len(o)), "R_O43": round(float(ref.R.sum()), 4), "R_O44": round(float(o.R.sum()), 4), "identicas": bool(iguais),
                              "sinais_O43": int(len(S43)), "sinais_O44": int(len(S44)), "mesmos_sinais": bool(len(S43) == len(S44) and (S43.id.values == S44.id.values).all()
                                                                                                          and (S43.resultado_gatilho.values == S44.resultado_gatilho.values).all())}
    print("reprodução:", R["reproducao_O43_R0"], flush=True)
    # ── 2. comparação no mesmo intervalo ──
    ini, fim = janela(at, m1); meses = (fim - ini) / pd.Timedelta(days=30.4375); horas_tot = (fim - ini) / pd.Timedelta(hours=1)
    R["intervalo"] = {"inicio": str(ini), "fim": str(fim), "meses": round(meses, 2), "aquecimento": "300 barras H1 + até o dia 1 do mês seguinte; indicadores com todo o histórico anterior"}
    dias = pd.date_range(ini.floor("D"), fim.floor("D"), freq="D"); OPS, SIG = {}, {}
    for tf, mn in TFS.items():
        d = m15 if tf == "M15" else ST.ler(at, tf); M = FO.Motor(at, d, m1, tf_min=mn)
        i0 = int(np.searchsorted(d.t.values, np.datetime64(ini))); i1 = int(np.searchsorted((d.t + pd.Timedelta(minutes=mn)).values, np.datetime64(fim), side="right"))
        M.rodar(i0=i0, i1=i1); S = sinais_df(M); S["tf"] = tf; o = ops_df(M, at, fim.value); OPS[tf], SIG[tf] = o, S
        post = pd.to_datetime(o.t_ent) >= CORTE; cut = int(np.searchsorted(m1.t.values, np.datetime64(CORTE)))
        trim = {str(q): {"n": int(len(g)), "R": round(float(g.R.sum()), 2)} for q, g in o.groupby(pd.to_datetime(o.t_ent).dt.to_period("Q"))}
        R[tf] = {"barras_avaliadas": int(i1 - i0), "caixa_horas": 12 * mn / 60, "ruido": ruido(S, meses), "desempenho": met(o, m1, K, meses, horas_tot),
                 "desenvolvimento": ST.metricas(o[~post]) if (~post).any() else {"n": 0}, "posterior_RETROSPECTIVO": ST.metricas(o[post]) if post.any() else {"n": 0},
                 "por_trimestre": trim, "aberta_no_fim_excluida": M.pos["R0"] is not None, "bloqueados_por_posicao_aberta": int(sum(1 for x in M.reg if x["decisao"] == "bloqueado_posicao_aberta"))}
        S.drop(columns=["j_sup"], errors="ignore").to_csv(f"{out}/O44_{at}_{tf}_sinais.csv", index=False, sep=";")
        if len(o): o.drop(columns=["j_ent", "j_sai"]).to_csv(f"{out}/O44_{at}_{tf}_operacoes.csv", index=False, sep=";")
        print(tf, json.dumps({"ruido": R[tf]["ruido"], "R": R[tf]["desempenho"].get("R_total"), "n": R[tf]["desempenho"].get("n")}, ensure_ascii=False), flush=True)
    # ── diferenças ──
    R["diferencas"] = {}
    for a, b in (("M30", "M15"), ("H1", "M15"), ("H1", "M30")):
        sa = SIG[a][SIG[a].resultado_gatilho == "superou"]; sb = SIG[b][SIG[b].resultado_gatilho == "superou"]
        pos = lambda o, x: o[(pd.to_datetime(o.t_ent) >= CORTE) == x]
        R["diferencas"][f"{a}-{b}"] = {"R_total": dif_boot(OPS[a], OPS[b], dias), "R_desenvolvimento": dif_boot(pos(OPS[a], False), pos(OPS[b], False), dias[dias < CORTE]),
                                        "R_posterior_RETROSPECTIVO": dif_boot(pos(OPS[a], True), pos(OPS[b], True), dias[dias >= CORTE]),
                                        "retorno_15min": dif_prop(sa.retorno_15min_min.notna(), sb.retorno_15min_min.notna()),
                                        "retorno_fim_barra": dif_prop(sa.retorno_fim_barra_min.notna(), sb.retorno_fim_barra_min.notna()),
                                        "perdedora_isolada": dif_prop(sa.iso_R < 0, sb.iso_R < 0)}
    R["segundos"] = round(time.time() - t0, 1); json.dump(R, open(f"{out}/O44_{at}_resultado.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(R["diferencas"], ensure_ascii=False, indent=1))


if __name__ == "__main__": main()
