"""ROMP-M15-0.1 — bancada histórica cronológica (XAUUSD): sinais com M15 concluídas, execução e stop em M1 (bid/ask), custos, registros por decisão.
Uso: python bancada_romp.py SAIDA_DIR [--desliz-spread]"""
import os, sys, glob, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import romp_m15 as RM
DADOS = "/home/claude/r005/lm014/dados/csv_limpo"; PT = 0.01; CONTRATO = 100.0; COM_LADO = 3.50; MIN = 60 * 10**9; M15 = 15 * MIN
CORTE_OOS = pd.Timestamp("2026-05-01")


def ler(tf):
    f = glob.glob(f"{DADOS}/XAUUSD_{tf}_*.csv")[0]; d = pd.read_csv(f, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
    d["t"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S"); return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c", "spread"]]


def simular(m15, m1, desliz_spread=0.0):
    K = RM.canais(m15); t15 = m15.t.values.astype("datetime64[ns]").astype(np.int64); fim15 = t15 + M15
    t1 = m1.t.values.astype("datetime64[ns]").astype(np.int64); o1, h1, l1, c1 = (m1[k].values.astype(float) for k in "ohlc"); sp1 = m1.spread.values.astype(float) * PT
    O, H, L, C = (m15[k].values.astype(float) for k in "ohlc"); DEC = []; OPS = []; pos = None
    def prox_m1(ts): j = int(np.searchsorted(t1, ts, side="left")); return j if j < len(t1) else None
    for i in range(len(m15)):
        k = K.iloc[i]; base = {"barra_abertura": str(m15.t.iloc[i]), "barra_fecha": str(pd.Timestamp(int(fim15[i]))), "o": O[i], "h": H[i], "l": L[i], "c": C[i],
                               "LS20": k.LS20, "LI20": k.LI20, "LS10": k.LS10, "LI10": k.LI10, "ATR14": k.ATR14}
        # 1) stop dentro da barra i (M1 com abertura em [desde, fim da barra i))
        if pos is not None:
            j1 = int(np.searchsorted(t1, fim15[i], side="left")); a = pos["desde"]
            if j1 > a:
                s = pos["lado"]
                hit = (l1[a:j1] <= pos["stop"]) if s > 0 else (h1[a:j1] + sp1[a:j1] >= pos["stop"])
                if hit.any():
                    j = a + int(np.argmax(hit)); px = min(pos["stop"], o1[j]) if s > 0 else max(pos["stop"], o1[j] + sp1[j])
                    if s > 0: px -= desliz_spread * sp1[j]
                    else: px += desliz_spread * sp1[j]
                    fechar(pos, j, px, "stop de proteção", t1, sp1, OPS); DEC.append({**base, "decisao": "saida", "condicao": "stop tocado dentro da barra", "resultado": True, "motivo": "stop de proteção (intrabarra M1)", "op": pos["id"]}); pos = None
                else: pos["desde"] = j1
        # 2) saída por sinal no fechamento de i
        if pos is not None and t15[i] >= pos["barra_sinal_fim"]:
            s = pos["lado"]; cond = RM.sinal_saida(s, C[i], k.LS10, k.LI10)
            txt = f"fechamento {C[i]:.2f} < mín10 {k.LI10:.2f}" if s > 0 else f"fechamento {C[i]:.2f} > máx10 {k.LS10:.2f}"
            if cond:
                j = prox_m1(fim15[i])
                if j is None: DEC.append({**base, "decisao": "saida", "condicao": txt, "resultado": True, "motivo": "sem cotação posterior nos dados", "op": pos["id"]}); break
                px = o1[j] - desliz_spread * sp1[j] if s > 0 else o1[j] + sp1[j] + desliz_spread * sp1[j]
                fechar(pos, j, px, "saída por sinal (canal 10)", t1, sp1, OPS, ref=C[i], atraso=(t1[j] - fim15[i]) / 1e9)
                DEC.append({**base, "decisao": "saida", "condicao": txt, "resultado": True, "motivo": "saída por sinal: canal de 10 barras rompido contra", "op": pos["id"]}); pos = None
                continue                                                                 # sem entrada na mesma decisão
            DEC.append({**base, "decisao": "manutencao", "condicao": txt, "resultado": False, "motivo": "mantida: canal de 10 não rompido", "op": pos["id"]})
        # 3) entrada
        sig = RM.sinal_entrada(C[i], k.LS20, k.LI20)
        if pos is not None:
            if sig: DEC.append({**base, "decisao": "entrada", "condicao": "c > LS20" if sig > 0 else "c < LI20", "resultado": True, "motivo": "sinal ignorado: posição desta experiência aberta", "op": pos["id"]})
            continue
        if not np.isfinite(k.LS20): continue
        if not sig: continue                                                                # avaliação falsa não é gravada por barra (volume); contagem no resumo
        j = prox_m1(fim15[i])
        if j is None: break
        px = o1[j] + sp1[j] + desliz_spread * sp1[j] if sig > 0 else o1[j] - desliz_spread * sp1[j]
        st = RM.stop_inicial(sig, px, k.ATR14); oid = f"ROMP-XAU-{m15.t.iloc[i]:%Y%m%d%H%M}"
        pos = {"id": oid, "lado": sig, "barra_sinal": str(m15.t.iloc[i]), "barra_sinal_fim": int(fim15[i]), "j_ent": j, "t_ent": int(t1[j]), "entrada": px, "pedido": C[i],
               "spread_ent": sp1[j], "atraso_ent_s": (t1[j] - fim15[i]) / 1e9, "stop": st, "atr": k.ATR14, "LS20": k.LS20, "LI20": k.LI20, "desde": j,
               "ohlc_sinal": [O[i], H[i], L[i], C[i]]}
        DEC.append({**base, "decisao": "entrada", "condicao": f"c {C[i]:.2f} > LS20 {k.LS20:.2f}" if sig > 0 else f"c {C[i]:.2f} < LI20 {k.LI20:.2f}", "resultado": True,
                    "motivo": "COMPRA: rompimento do canal de 20" if sig > 0 else "VENDA: rompimento do canal de 20", "op": oid, "entrada": px, "stop": st, "risco_px": abs(px - st)})
    if pos is not None: OPS.append({**{k: v for k, v in pos.items() if k != "desde"}, "aberta_no_fim_dos_dados": True})
    return pd.DataFrame(OPS), pd.DataFrame(DEC)


def fechar(pos, j, px, motivo, t1, sp1, OPS, ref=None, atraso=0.0):
    s = pos["lado"]; R0 = abs(pos["entrada"] - pos["stop"]); bruto = (px - pos["entrada"]) * s
    d0 = pd.Timestamp(pos["t_ent"]).normalize(); d1 = pd.Timestamp(int(t1[j])).normalize()
    OPS.append({**{k: v for k, v in pos.items() if k != "desde"}, "j_sai": j, "t_sai": int(t1[j]), "saida": px, "pedido_saida": ref, "atraso_sai_s": atraso, "spread_sai": sp1[j], "motivo_saida": motivo,
                "bruto_px": bruto, "R": bruto / R0 - 2 * COM_LADO / CONTRATO / R0, "usd_1lote": bruto * CONTRATO - 2 * COM_LADO, "comissao_usd": 2 * COM_LADO,
                "spread_custo_usd": (pos["spread_ent"] + sp1[j]) / 2 * CONTRATO, "viradas_dia": int((d1 - d0).days), "aberta_no_fim_dos_dados": False})


def curva_mtm(ops, m1):
    """patrimônio de 1 lote marcado a mercado a cada M1 (bid para compra, ask para venda), incluindo posição aberta."""
    c1 = m1.c.values.astype(float); sp = m1.spread.values * PT; eq = np.zeros(len(c1)); real = np.zeros(len(c1))
    for r in ops[~ops.aberta_no_fim_dos_dados].itertuples():
        a, b = r.j_ent, r.j_sai; px = c1[a:b] if r.lado > 0 else c1[a:b] + sp[a:b]
        eq[a:b] += (px - r.entrada) * r.lado * CONTRATO - COM_LADO; real[b:] += r.usd_1lote
    return eq + real


def metricas(o, eq_parte=None):
    if not len(o): return {"n": 0}
    g, p = o.usd_1lote[o.usd_1lote > 0], o.usd_1lote[o.usd_1lote <= 0]
    m = {"n": int(len(o)), "lucro_liquido_usd_1lote": round(float(o.usd_1lote.sum()), 2), "R_total": round(float(o.R.sum()), 2), "expectativa_usd": round(float(o.usd_1lote.mean()), 2),
         "expectativa_R": round(float(o.R.mean()), 4), "acerto": round(float((o.usd_1lote > 0).mean()), 4), "fator_lucro": round(float(g.sum() / -p.sum()), 3) if p.sum() < 0 else None,
         "ganho_medio_usd": round(float(g.mean()), 2) if len(g) else None, "perda_media_usd": round(float(p.mean()), 2) if len(p) else None,
         "comissao_usd": round(float(o.comissao_usd.sum()), 2), "spread_estimado_usd": round(float(o.spread_custo_usd.sum()), 2),
         "saidas": o.motivo_saida.value_counts().to_dict(), "viradas_de_dia_total (swap não modelado)": int(o.viradas_dia.sum()),
         "atraso_entrada_s_mediana": float(o.atraso_ent_s.median()), "duracao_h_mediana": round(float(((o.t_sai - o.t_ent) / 3.6e12).median()), 2)}
    rng = np.random.default_rng(1); d = pd.Series(o.R.values).groupby(pd.to_datetime(o.t_ent).dt.floor("D").values).sum().values
    if len(d) > 5:
        bs = [d[rng.integers(0, len(d), len(d))].sum() / len(o) for _ in range(2000)]; m["IC95_expectativa_R_bootstrap_dia"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
    if eq_parte is not None and len(eq_parte):
        pk = np.maximum.accumulate(eq_parte); m["drawdown_mtm_usd_1lote"] = round(float((eq_parte - pk).min()), 2)
    return m


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); dz = 1.0 if "--desliz-spread" in sys.argv else 0.0; t0 = time.time()
    m15 = ler("M15"); m1 = ler("M1"); ops, dec = simular(m15, m1, dz); eq = curva_mtm(ops, m1); fe = ops[~ops.aberta_no_fim_dos_dados].copy()
    fe["mes"] = pd.to_datetime(fe.t_ent).dt.to_period("M").astype(str); fe["periodo"] = np.where(pd.to_datetime(fe.t_ent) >= CORTE_OOS, "fora_da_amostra", "desenvolvimento")
    t1 = m1.t.values; oos = t1 >= np.datetime64(CORTE_OOS)
    def eq_rel(mask): e = eq[mask]; return e - (e[0] if len(e) else 0)
    R = {"versao": RM.VERSAO, "desliz_adicional_spread": dz, "dados": {"M15": [str(m15.t.iloc[0]), str(m15.t.iloc[-1]), len(m15)], "M1": [str(m1.t.iloc[0]), str(m1.t.iloc[-1]), len(m1)]},
         "geral": metricas(fe, eq), "desenvolvimento": metricas(fe[fe.periodo == "desenvolvimento"], eq_rel(~oos)), "fora_da_amostra": metricas(fe[fe.periodo == "fora_da_amostra"], eq_rel(oos)),
         "compras": metricas(fe[fe.lado > 0]), "vendas": metricas(fe[fe.lado < 0]),
         "por_periodo_e_lado": {f"{p}|{'compra' if s > 0 else 'venda'}": metricas(fe[(fe.periodo == p) & (fe.lado == s)]) for p in ("desenvolvimento", "fora_da_amostra") for s in (1, -1)},
         "por_mes": {mm: {"n": int(len(g)), "usd": round(float(g.usd_1lote.sum()), 2), "R": round(float(g.R.sum()), 2)} for mm, g in fe.groupby("mes")},
         "aberta_no_fim": ops[ops.aberta_no_fim_dos_dados].id.tolist(), "decisoes": dec.decisao.value_counts().to_dict(),
         "sinais_ignorados_posicao_aberta": int((dec.motivo == "sinal ignorado: posição desta experiência aberta").sum()), "segundos": round(time.time() - t0, 1)}
    suf = "_desliz1spread" if dz else ""
    json.dump(R, open(f"{out}/ROMP_resultado{suf}.json", "w"), ensure_ascii=False, indent=1, default=str)
    if not dz:
        ops.to_csv(f"{out}/ROMP_operacoes.csv", index=False, sep=";"); dec.to_csv(f"{out}/ROMP_decisoes.csv.gz", index=False, sep=";")
        pd.DataFrame({"t": m1.t.values[::15], "patrimonio_usd_1lote": eq[::15]}).to_csv(f"{out}/ROMP_curva_mtm.csv.gz", index=False, sep=";")
    print(json.dumps({k: R[k] for k in ("geral", "desenvolvimento", "fora_da_amostra")}, ensure_ascii=False, indent=1, default=str)[:4000])


if __name__ == "__main__": main()
