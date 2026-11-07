"""ORDEM 042 — Referência (V1-200) × Entrada (E) × Saída (S, também nas MESMAS entradas) × Combinada (E+S). Uso: python rodar_o42.py ATIVO SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrategia_o39 as ST, leitura_o42 as LQ
at, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); CORTE = "2026-05-01"; m15, m1 = ST.ler(at, "M15"), ST.ler(at, "M1")
R = {"ativo": at, "leitura": LQ.VERSAO}; OPS, REG, RP = {}, {}, {}
for v, e, s in (("Ref", False, False), ("E", True, False), ("S", False, True), ("ES", True, True)):
    t0 = time.time(); rp = LQ.ReplayM1(at, m15, m1, v, entrada=e, saida=s); rp.rodar(); RP[v] = rp
    o = pd.DataFrame(rp.ops); g = pd.DataFrame(rp.reg); OPS[v], REG[v] = o, g; eq = ST.curva(o, m1, ST.CUSTO[at]); oos = pd.to_datetime(o.t_ent) >= CORTE; cut = int(np.searchsorted(m1.t.values, np.datetime64(CORTE)))
    R[v] = {"geral": ST.metricas(o, eq), "desenvolvimento": ST.metricas(o[~oos], eq[:cut]), "bloco_posterior_RETROSPECTIVO": ST.metricas(o[oos], eq[cut:] - eq[cut]),
            "compras": ST.metricas(o[o.lado > 0]), "vendas": ST.metricas(o[o.lado < 0]), "decisoes": g.decisao.value_counts().to_dict(), "segundos": round(time.time() - t0, 1)}
    o.drop(columns=[c for c in ("leitura_entrada", "obstaculo") if c in o], errors="ignore").to_csv(f"{out}/O42_{at}_{v}_operacoes.csv", index=False, sep=";"); g.to_csv(f"{out}/O42_{at}_{v}_decisoes.csv.gz", index=False, sep=";")
    print(at, v, R[v]["geral"].get("n"), R[v]["geral"].get("R_total"), round(time.time() - t0), "s", flush=True)
a = pd.read_csv(f"/home/claude/r005/lm040/saida/replay/O40_{at}_V1-200_operacoes.csv", sep=";"); b = OPS["Ref"]
R["Ref_identica_O40"] = bool(len(a) == len(b) and (a.sinal.values == b.sinal.values).all() and np.allclose(a.R.values, b.R.values))
# ENTRADA × Referência
oR, oE = OPS["Ref"], OPS["E"]; fora = oR[~oR.sinal.isin(set(oE.sinal))]; novas = oE[~oE.sinal.isin(set(oR.sinal))]; par = oR.merge(oE[["sinal", "t_ent", "R"]], on="sinal", suffixes=("_ref", "_E"))
gE = REG["E"]; ssc = gE[gE.decisao == "superacao_sem_continuidade"]; conf_tarde = gE[(gE.decisao == "entrada") & (gE.confirmacao_m1m5.astype(str).str.startswith("confirmada depois"))]
def combo(L):
    try: m1 = L["m1_atual"]; return f"M1 avanço={m1.get('avanco')}·rejeição={m1.get('rejeicao')}·pressão={m1.get('pressao_contraria')} | M5 contrária={L['m5_contraria']}"
    except Exception: return "?"
R["entrada_x_ref"] = {"superacoes_sem_continuidade_no_instante": int(len(ssc)), "entradas_confirmadas_depois": int(len(conf_tarde)),
                      "gatilhos_expirados_sem_continuidade": int(gE.motivo.astype(str).str.contains("sem continuidade M1/M5").sum()),
                      "operacoes_da_Ref_que_E_nao_fez": {"n": int(len(fora)), "falsos_rompimentos_evitados_(perdedoras)": int((fora.R <= 0).sum()), "R_perdedoras_evitadas": round(float(fora[fora.R <= 0].R.sum()), 2),
                                                         "entradas_boas_perdidas_(vencedoras)": int((fora.R > 0).sum()), "R_vencedoras_perdidas": round(float(fora[fora.R > 0].R.sum()), 2), "R_total": round(float(fora.R.sum()), 2)},
                      "operacoes_novas_de_E_sem_par": {"n": int(len(novas)), "R": round(float(novas.R.sum()), 2)},
                      "mesmo_sinal": {"n": int(len(par)), "mesma_entrada": int((par.t_ent_ref == par.t_ent_E).sum()), "E_entrou_depois": int((par.t_ent_E > par.t_ent_ref).sum()),
                                      "atraso_min_mediana": round(float(((par.t_ent_E - par.t_ent_ref) / 6e10)[par.t_ent_E > par.t_ent_ref].median()), 1) if (par.t_ent_E > par.t_ent_ref).any() else 0.0,
                                      "R_ref": round(float(par.R_ref.sum()), 2), "R_E": round(float(par.R_E.sum()), 2)},
                      "leituras_quando_nao_confirmou": ssc.leitura.map(combo).value_counts().head(8).to_dict()}
# SAÍDA nas MESMAS entradas da Referência
rp = RP["Ref"]; linhas = []
for op in OPS["Ref"].to_dict("records"):
    rb = LQ.seguir_saida(rp, op, False); rs = LQ.seguir_saida(rp, op, True)
    if rb is None or rs is None: continue
    linhas.append({"sinal": op["sinal"], "lado": op["lado"], "t_ent": op["t_ent"], "R_ref": rb["R"], "R_S": rs["R"], "motivo_ref": rb["motivo_saida"], "motivo_S": rs["motivo_saida"], "t_sai_ref": rb["t_sai"], "t_sai_S": rs["t_sai"],
                   "mfe_R": rb["mfe"], "devolucao_ref_R": rb["mfe"] - rb["R"], "devolucao_S_R": rs["mfe"] - rs["R"], "alertas": rs["n_alertas"]})
X = pd.DataFrame(linhas); X.to_csv(f"{out}/O42_{at}_saida_mesmas_entradas.csv", index=False, sep=";")
cut = X[X.motivo_S.str.startswith("corte")]; ok_base = bool(np.allclose(X.R_ref.values, OPS["Ref"].R.values[:len(X)]))
R["saida_mesmas_entradas"] = {"entradas": int(len(X)), "reaplicacao_da_saida_ref_confere": ok_base, "posicoes_com_alerta_m1m5": int((X.alertas > 0).sum()), "alertas_total": int(X.alertas.sum()),
                              "cortes_por_reversao_M15": int(len(cut)), "reversoes_reconhecidas_(corte_melhor)": int((cut.R_S > cut.R_ref + 1e-9).sum()), "cortes_prematuros_(corte_pior)": int((cut.R_S < cut.R_ref - 1e-9).sum()),
                              "R_ganho_nas_reconhecidas": round(float((cut.R_S - cut.R_ref)[cut.R_S > cut.R_ref].sum()), 2), "R_perdido_nos_prematuros": round(float((cut.R_S - cut.R_ref)[cut.R_S < cut.R_ref].sum()), 2),
                              "alertas_sem_corte_(pullback_respeitou_M15)": int(((X.alertas > 0) & ~X.motivo_S.str.startswith("corte")).sum()),
                              "R_total_ref": round(float(X.R_ref.sum()), 2), "R_total_S": round(float(X.R_S.sum()), 2), "devolucao_media_ref_R": round(float(X.devolucao_ref_R.mean()), 3), "devolucao_media_S_R": round(float(X.devolucao_S_R.mean()), 3),
                              "bloco_posterior_RETROSPECTIVO": {"n": int((pd.to_datetime(X.t_ent) >= CORTE).sum()), "R_ref": round(float(X[pd.to_datetime(X.t_ent) >= CORTE].R_ref.sum()), 2), "R_S": round(float(X[pd.to_datetime(X.t_ent) >= CORTE].R_S.sum()), 2)}}
# discordâncias M1 × M5 nas decisões de entrada (E)
ent = gE[gE.decisao.isin(["entrada", "superacao_sem_continuidade"])]; dis = 0; tot = 0
for L in ent.leitura:
    if not isinstance(L, dict) or not L.get("m1_atual"): continue
    tot += 1; dis += int(bool(L["m1_atual"]["avanco"]) == bool(L["m5_contraria"]))
R["discordancia_M1_M5_nas_entradas"] = {"leituras": tot, "M1_avanca_e_M5_contraria_ou_M1_nao_avanca_e_M5_favoravel": dis}
json.dump(R, open(f"{out}/O42_{at}_resultado.json", "w"), ensure_ascii=False, indent=1, default=str); print("FIM", at)
