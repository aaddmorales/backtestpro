"""ORDEM 041 — replay comparativo Referência (V1-200 da O40) × Teste A × Teste B. Uso: python rodar_o41.py ATIVO SAIDA_DIR [A|B|todos]"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrategia_o39 as ST, janela_o40 as JN, reacoes_o41 as RQ
at, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); CORTE = "2026-05-01"
m15, m1 = ST.ler(at, "M15"), ST.ler(at, "M1"); R = {"ativo": at, "versao": RQ.VERSAO}; OPS, REG = {}, {}
for v in ("Ref", "A", "B"):
    t0 = time.time(); rp = RQ.ReplayRef(at, m15, m1, "V1-200") if v == "Ref" else RQ.ReplayQ(at, m15, m1, v); rp.rodar()
    o = pd.DataFrame(rp.ops); g = pd.DataFrame(rp.reg); OPS[v], REG[v] = o, g; eq = ST.curva(o, m1, ST.CUSTO[at])
    oos = pd.to_datetime(o.t_ent) >= CORTE; cut = int(np.searchsorted(m1.t.values, np.datetime64(CORTE)))
    R[v] = {"geral": ST.metricas(o, eq), "desenvolvimento": ST.metricas(o[~oos], eq[:cut]), "bloco_posterior_RETROSPECTIVO": ST.metricas(o[oos], eq[cut:] - eq[cut]),
            "compras": ST.metricas(o[o.lado > 0]), "vendas": ST.metricas(o[o.lado < 0]), "decisoes": g.decisao.value_counts().to_dict(), "segundos": round(time.time() - t0, 1)}
    ini = g[g.decisao.isin(["aguardando", "gatilho_armado"]) & (g.get("condicao").astype(str).str.startswith("fech") & g.motivo.astype(str).str.startswith("sinal de média") | (g.condicao.astype(str) == "sinal de média"))]
    R[v]["sinais"] = {"sinais_de_media": int(len(ini)), "bloqueio_inicial": int((ini.decisao == "aguardando").sum()), "liberados_direto": int((ini.decisao == "gatilho_armado").sum()),
                      "espera_segundo_nivel": int(g.motivo.astype(str).str.contains("novo obstáculo|segundo nível").sum()),
                      "gatilhos_por_rompimento": int(g.motivo.astype(str).str.contains("rompimento").where(g.decisao == "gatilho_armado", False).sum()),
                      "esperas_encerradas_inelegivel": int((g.decisao == "espera_encerrada_inelegivel").sum()), "esperas_encerradas_borda": int((g.decisao == "espera_encerrada_borda").sum()),
                      "esperas_canceladas": int((g.decisao == "espera_cancelada").sum())}
    if v == "Ref" and "diag_rompimento_por_borda" in g:
        dg = g[g.diag_rompimento_por_borda == True]; ok_ent = o[o.referencia.isin(set(dg.barra))] if len(o) else o
        R["Ref"]["diagnostico_rompimento_por_borda"] = {"gatilhos_armados": int(len(dg)), "de_um_total_de": int(g.diag_rompimento_por_borda.notna().sum()), "entradas": int(len(ok_ent)), "R_dessas": round(float(ok_ent.R.sum()), 2) if len(ok_ent) else 0}
    o.to_csv(f"{out}/O41_{at}_{v}_operacoes.csv", index=False, sep=";"); g.to_csv(f"{out}/O41_{at}_{v}_decisoes.csv.gz", index=False, sep=";")
    print(at, v, R[v]["geral"].get("n"), R[v]["geral"].get("R_total"), R[v]["sinais"], round(time.time() - t0), "s", flush=True)
# Referência = O40?
a = pd.read_csv(f"/home/claude/r005/lm040/saida/replay/O40_{at}_V1-200_operacoes.csv", sep=";"); b = OPS["Ref"]
R["Ref_identica_O40"] = bool(len(a) == len(b) and (a.sinal.values == b.sinal.values).all() and np.allclose(a.R.values, b.R.values))
def obst(x):
    if isinstance(x, dict): return x
    try: return eval(x) if isinstance(x, str) and x.startswith("{") else None
    except Exception: return None
# A × Referência
gR, gA, gB = REG["Ref"], REG["A"], REG["B"]
refb = gR[(gR.decisao == "aguardando") & (gR.condicao.astype(str) == "sinal de média")].copy(); refb["d0"] = [((obst(x) or {}).get("dist_atr", 1) == 0) for x in refb.obstaculo]
Al = gA[(gA.decisao == "gatilho_armado") & gA.motivo.astype(str).str.startswith("sinal de média")]; lib = set(Al.sinal)
ev = refb[refb.barra.isin(lib)]
oR, oA, oB = OPS["Ref"], OPS["A"], OPS["B"]; volt = oA[~oA.sinal.isin(set(oR.sinal))]; sair = oR[~oR.sinal.isin(set(oA.sinal))]
R["A_x_Ref"] = {"bloqueios_iniciais_Ref": int(len(refb)), "bloqueios_iniciais_que_A_liberou": int(len(ev)), "dos_quais_a_0_ATR": int(ev.d0.sum()), "bloqueios_Ref_a_0_ATR": int(refb.d0.sum()),
                "operacoes_que_voltaram": {"n": int(len(volt)), "R_liquido": round(float(volt.R.sum()), 2), "acerto": round(float((volt.R > 0).mean()), 4) if len(volt) else None, "usd_1lote": round(float(volt.usd_1lote.sum()), 2),
                                           "bloco_posterior": int((pd.to_datetime(volt.t_ent) >= CORTE).sum()), "R_bloco_posterior": round(float(volt[pd.to_datetime(volt.t_ent) >= CORTE].R.sum()), 2)},
                "operacoes_da_Ref_que_A_nao_fez": {"n": int(len(sair)), "R": round(float(sair.R.sum()), 2)},
                "sinais_correspondentes": int(oA.sinal.isin(set(oR.sinal)).sum())}
# B × A
segA = gA[gA.motivo.astype(str).str.contains("segundo nível")]; libB = gB[(gB.get("liberado_com_nivel_proximo") == True)]
com = oA.merge(oB[["sinal", "t_ent", "R"]], on="sinal", suffixes=("_A", "_B")); d = (com.t_ent_A - com.t_ent_B) / 6e10
opsLib = oB[oB.referencia.isin(set(libB.barra))]
R["B_x_A"] = {"esperas_segundo_nivel_A": int(len(segA)), "liberacoes_B_com_nivel_proximo": int(len(libB)), "esperas_segundo_nivel_B": int(gB.motivo.astype(str).str.contains("segundo nível").sum()),
              "mesmo_sinal_nas_duas": int(len(com)), "B_entrou_antes": int((d > 0).sum()), "reducao_atraso_min_mediana": round(float(d[d > 0].median()), 1) if (d > 0).any() else 0.0,
              "entradas_B_liberadas_com_nivel_proximo": {"n": int(len(opsLib)), "R_liquido": round(float(opsLib.R.sum()), 2), "acerto": round(float((opsLib.R > 0).mean()), 4) if len(opsLib) else None,
                                                         "saidas": opsLib.motivo_saida.value_counts().to_dict() if len(opsLib) else {}},
              "operacoes_B_sem_par_em_A": {"n": int((~oB.sinal.isin(set(oA.sinal))).sum()), "R": round(float(oB[~oB.sinal.isin(set(oA.sinal))].R.sum()), 2)},
              "operacoes_A_sem_par_em_B": {"n": int((~oA.sinal.isin(set(oB.sinal))).sum()), "R": round(float(oA[~oA.sinal.isin(set(oB.sinal))].R.sum()), 2)}}
# exemplos
def ex(df, asc, k=3):
    rows = []
    for r in df.sort_values("R", ascending=asc).head(k).itertuples():
        s = gA[(gA.sinal == r.sinal)]; ob = obst(s.obstaculo.iloc[0]) if len(s) else None
        rows.append({"sinal": r.sinal, "lado": "compra" if r.lado > 0 else "venda", "entrada": str(pd.Timestamp(r.t_ent)), "R": round(r.R, 3), "saida": r.motivo_saida,
                     "nivel_mais_proximo_nao_qualificado": None if not ob else {k2: (ob["mais_proximo"] or {}).get(k2) for k2 in ("nivel", "dist_atr", "reacoes_na_janela")},
                     "por_que_a_Ref_bloqueou": "nível elegível a ≤ 2×ATR (sem exigir reações)"})
    return rows
R["exemplos"] = {"bloqueio_indevido_evitado_(voltou_e_ganhou)": ex(volt[volt.R > 0], False), "entrada_perdedora_liberada": ex(volt[volt.R <= 0], True)}
# por sinal (A e B): uma linha por sinal com a sequência de decisões e a operação
for v, g in (("A", gA), ("B", gB)):
    rows = []
    for s, x in g[g.sinal.notna()].groupby("sinal", sort=False):
        ob0 = obst(x.obstaculo.iloc[0]); o = OPS[v][OPS[v].sinal == s]; bl = (ob0 or {}).get("bloqueador") or {}; sg = (ob0 or {}).get("seguinte") or {}
        rows.append({"versao": v, "sinal": s, "sequencia": " → ".join(x.decisao.tolist()), "motivo_final": x.motivo.iloc[-1], "nivel_bloqueador": bl.get("nivel"), "reacoes_bloqueador": bl.get("reacoes_na_janela"),
                     "reacoes_detalhe": bl.get("reacoes"), "mais_proximo": ((ob0 or {}).get("mais_proximo") or {}).get("nivel"), "dist_mais_proximo_atr": ((ob0 or {}).get("mais_proximo") or {}).get("dist_atr"),
                     "seguinte": sg.get("nivel"), "dist_seguinte_preco": sg.get("distancia"), "dist_seguinte_atr": sg.get("dist_atr"), "dist_seguinte_R": sg.get("dist_R"),
                     "operacao": o.id.iloc[0] if len(o) else None, "R": round(float(o.R.iloc[0]), 4) if len(o) else None, "par_na_Ref": bool(s in set(oR.sinal))})
    pd.DataFrame(rows).to_csv(f"{out}/O41_{at}_{v}_por_sinal.csv.gz", index=False, sep=";")
json.dump(R, open(f"{out}/O41_{at}_resultado.json", "w"), ensure_ascii=False, indent=1, default=str); print("FIM", at)
