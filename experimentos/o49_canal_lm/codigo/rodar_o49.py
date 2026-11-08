"""ORDEM 049 — replay da leitura do canal EMA20 High/Low + estrutura nos pilotos (XAUUSD M30, BTCUSD M15), por barra fechada, no intervalo da O44.
Registro por instante (sinais R0 da O44): dados recebidos → campos do canal → nível estrutural → leitura produzida, e, ao lado, os campos de canal
que o modelo LM-0.2 (treinado, M15) recebe hoje no mesmo instante. Uso: python rodar_o49.py SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leitura_canal_o49 as LC, estrategia_o39 as ST, romp_m15 as RM
O44 = "/home/claude/r005/lm044/saida/replay"; PILOTOS = [("XAUUSD", "M30", 30), ("BTCUSD", "M15", 15)]
INI = {"XAUUSD": "2024-10-01", "BTCUSD": "2025-09-01"}


def campos_lm02_m15(m15):
    """fórmulas da identificação-1.0 (linhas 152–156): o que o modelo LM-0.2 recebe sobre o canal, no M15."""
    h, l, c = (m15[k].values.astype(float) for k in "hlc"); pc = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc))); tr[0] = h[0] - l[0]; A = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    eH, eL = (np.array(x, dtype=float) for x in LC.emas(h, l)); eH[:20] = np.nan; eL[:20] = np.nan
    pos = np.where(c > eH, 1.0, np.where(c < eL, -1.0, 0.0)); mid = (eH + eL) / 2
    incl = (mid - np.r_[np.full(5, np.nan), mid[:-5]]) / A; af = np.where(c > eH, (c - eH) / A, np.where(c < eL, (c - eL) / A, 0.0))
    posp = np.r_[np.nan, pos[:-1]]
    return pd.DataFrame({"t_fecha": m15.t + pd.Timedelta(minutes=15), "m15_canal_pos": pos, "m15_canal_incl_atr": incl, "m15_canal_afast_atr": af,
                         "m15_canal_cruz_compra": ((pos == 1) & (posp != 1)).astype(float), "m15_canal_cruz_venda": ((pos == -1) & (posp != -1)).astype(float)})


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); R = {"versao": LC.VERSAO, "pilotos": {}}
    for at, tf, mn in PILOTOS:
        t0 = time.time(); d = ST.ler(at, tf); m15 = ST.ler(at, "M15"); m1 = ST.ler(at, "M1"); fim = m1.t.iloc[-1] + pd.Timedelta(minutes=1)
        T = d.t.values; o, h, l, c = (d[k].values.astype(float) for k in "ohlc"); A = RM.atr_wilder(d.h, d.l, d.c); eH, eL = LC.emas(h, l)
        S = pd.read_csv(f"{O44}/O44_{at}_{tf}_sinais.csv", sep=";"); alvo = set(pd.to_datetime(S.barra_rompimento))
        L02 = campos_lm02_m15(m15); L = LC.LeitorCanal(at, tf); linhas, inst = [], {}
        ini = pd.Timestamp(INI[at])
        for i in range(len(d)):
            L.alimentar_uma(T[i], mn, o[i], h[i], l[i], c[i])
            ti = pd.Timestamp(T[i])
            if ti < ini - pd.Timedelta(days=3) or ti + pd.Timedelta(minutes=mn) > fim: continue
            r = L.ler(T, o, h, l, c, A, eH, eL, i)
            if ti >= ini:
                if r["disponivel"]:
                    k = r["canal"]; e = r["estrutura"]
                    linhas.append({"barra": r["barra"], "posicao": k["posicao"], "dir_high": k["direcao_high"], "dir_low": k["direcao_low"], "incl_high": k["inclinacao_high_atr_por_barra"],
                                   "incl_low": k["inclinacao_low_atr_por_barra"], "largura_atr": k["largura_atr"], "evolucao": k["evolucao"], "compressao_pct": k["compressao_pct"],
                                   "dist_high_atr": k["dist_ema_high"]["atr"], "dist_low_atr": k["dist_ema_low"]["atr"], **{f"ev_{a}": b for a, b in r["eventos"].items()},
                                   "res_dist_atr": None if not e["resistencia_acima"] else e["resistencia_acima"]["dist_atr"], "res_vs_canal": None if not e["resistencia_acima"] else e["resistencia_acima"]["posicao_vs_canal"],
                                   "sup_dist_atr": None if not e["suporte_abaixo"] else e["suporte_abaixo"]["dist_atr"], "sup_vs_canal": None if not e["suporte_abaixo"] else e["suporte_abaixo"]["posicao_vs_canal"],
                                   "rompimentos_5b": len(e["rompimentos_ultimas_5_barras"]), "concordancia": r["concordancia"]["estado"], "av_alta_pct": r["evidencia_pct"]["avanco_alta"],
                                   "av_baixa_pct": r["evidencia_pct"]["avanco_baixa"], "disponivel": True})
                else: linhas.append({"barra": r["barra"], "disponivel": False})
                if ti in alvo:
                    fecha = ti + pd.Timedelta(minutes=mn); j = int(np.searchsorted(L02.t_fecha.values, np.datetime64(fecha), side="right")) - 1
                    lm = {k: (None if not np.isfinite(v) else round(float(v), 4)) for k, v in L02.iloc[j].drop("t_fecha").items()} if j >= 0 else None
                    inst[str(ti)] = {"instante_fechamento": str(fecha), "leitura_canal": r,
                                     "lm02_recebe_hoje": {"origem": "modelo treinado LM-0.2 (XGBoost congelado, decisão no M15) — recebe estes campos do canal, só do M15; NÃO recebe os campos novos",
                                                          "barra_m15_usada": None if j < 0 else str(L02.t_fecha.iloc[j] - pd.Timedelta(minutes=15)), "campos": lm}}
        P = pd.DataFrame(linhas); P.to_csv(f"{out}/O49_{at}_{tf}_leitura_por_barra.csv.gz", index=False, sep=";")
        json.dump(inst, open(f"{out}/O49_{at}_{tf}_registro_por_instante.json", "w"), ensure_ascii=False, indent=1, default=str)
        disp = P[P.disponivel == True]
        # sinais R0 da O44 × leitura do canal na barra de rompimento (descritivo; nada decide)
        S["barra_rompimento"] = pd.to_datetime(S.barra_rompimento); Q = S.merge(disp.assign(barra=pd.to_datetime(disp.barra)), left_on="barra_rompimento", right_on="barra", how="left")
        sup = Q[Q.resultado_gatilho == "superou"]
        por_conc = {k: {"n": int(len(g)), "R_medio_isolado": round(float(g.iso_R.mean()), 3), "perdedoras_pct": round(float((g.iso_R < 0).mean() * 100), 1)} for k, g in sup.groupby("concordancia")}
        R["pilotos"][f"{at} {tf}"] = {"barras": int(len(P)), "disponiveis": int(len(disp)), "indisponiveis": int((P.disponivel == False).sum()), "inicio": INI[at],
                                       "posicao": disp.posicao.value_counts().to_dict(), "evolucao": disp.evolucao.value_counts().to_dict(), "concordancia_todas_barras": disp.concordancia.value_counts().to_dict(),
                                       "eventos": {c_: int(disp[c_].sum()) for c_ in disp.columns if c_.startswith("ev_")}, "largura_atr_mediana": round(float(disp.largura_atr.median()), 3),
                                       "sinais_R0": int(len(S)), "superacoes": int(len(sup)), "superacoes_por_concordancia": por_conc,
                                       "sinais_por_posicao_no_canal": Q.posicao.value_counts().to_dict(), "instantes_registrados": len(inst), "segundos": round(time.time() - t0, 1)}
        Q.to_csv(f"{out}/O49_{at}_{tf}_sinais_com_canal.csv", index=False, sep=";")
        print(at, tf, json.dumps(R["pilotos"][f"{at} {tf}"], ensure_ascii=False, default=str), flush=True)
    json.dump(R, open(f"{out}/O49_resultado.json", "w"), ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__": main()
