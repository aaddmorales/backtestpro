"""ORDEM 041 — refinamento da comparação A × Referência por CAUSA (decisão inicial do sinal no Teste A) e exemplos. Lê os arquivos do replay."""
import ast, json, sys, numpy as np, pandas as pd
D = "/home/claude/r005/lm041/saida/replay"; CORTE = "2026-05-01"; OUT = {}
def ob(x):
    try: return eval(x, {"__builtins__": {}, "np": np, "nan": float("nan"), "True": True, "False": False, "None": None}) if isinstance(x, str) and x.startswith("{") else None   # registros gerados por este próprio replay
    except Exception: return None
for at in ("XAUUSD", "BTCUSD"):
    oR, oA = (pd.read_csv(f"{D}/O41_{at}_{v}_operacoes.csv", sep=";") for v in ("Ref", "A"))
    gA = pd.read_csv(f"{D}/O41_{at}_A_decisoes.csv.gz", sep=";", low_memory=False); gR = pd.read_csv(f"{D}/O41_{at}_Ref_decisoes.csv.gz", sep=";", low_memory=False)
    prim = gA[gA.sinal.notna()].groupby("sinal", sort=False).first()
    refblk = gR[(gR.decisao == "aguardando") & (gR.condicao.astype(str) == "sinal de média")].set_index("barra")
    volt = oA[~oA.sinal.isin(set(oR.sinal))].copy()
    def classe(s):
        p = prim.loc[s] if s in prim.index else None
        if p is None: return "sem registro"
        if p.decisao == "gatilho_armado" and str(p.get("bloqueio_evitado_isolado")) == "True": return "bloqueio da Referência evitado (nível próximo sem 2 reações)"
        if p.decisao == "gatilho_armado": return "liberado direto (Referência também não tinha nível próximo)"
        return "esperou em nível qualificado e entrou depois por outro caminho"
    volt["causa"] = volt.sinal.map(classe); volt["oos"] = pd.to_datetime(volt.t_ent) >= CORTE
    volt["dist_ref_atr"] = [(ob(refblk.loc[s].obstaculo) or {}).get("dist_atr") if s in refblk.index and not isinstance(refblk.loc[s], pd.DataFrame) else None for s in volt.sinal]
    res = {}
    for c, g in volt.groupby("causa"):
        res[c] = {"n": int(len(g)), "R_liquido": round(float(g.R.sum()), 2), "acerto": round(float((g.R > 0).mean()), 4), "expectativa_R": round(float(g.R.mean()), 4), "usd_1lote": round(float(g.usd_1lote.sum()), 2),
                  "bloco_posterior_RETROSPECTIVO": {"n": int(g.oos.sum()), "R": round(float(g[g.oos].R.sum()), 2)}, "a_0_ATR_na_Referencia": int((g.dist_ref_atr == 0).sum())}
    ev = volt[volt.causa.str.startswith("bloqueio da Referência")]
    def exs(df, asc):
        out = []
        for r in df.sort_values("R", ascending=asc).head(3).itertuples():
            p = ob(prim.loc[r.sinal].obstaculo) or {}; mp = p.get("mais_proximo") or {}; sg = p.get("seguinte") or {}
            out.append({"sinal": r.sinal, "lado": "compra" if r.lado > 0 else "venda", "entrada": str(pd.Timestamp(r.t_ent)), "R": round(r.R, 3), "saida": r.motivo_saida,
                        "nivel_que_a_Referencia_usaria": mp.get("nivel"), "distancia_atr": None if mp.get("dist_atr") is None else round(mp["dist_atr"], 2), "reacoes_na_janela": mp.get("reacoes_na_janela"),
                        "nivel_seguinte": sg.get("nivel"), "dist_seguinte": None if not sg else {"preco": round(sg["distancia"], 2), "ATR": round(sg["dist_atr"], 2), "R": round(sg["dist_R"], 2), "reacoes": sg.get("reacoes_na_janela")}})
        return out
    OUT[at] = {"operacoes_que_voltaram_por_causa": res, "exemplos_bloqueio_indevido_evitado_que_ganhou": exs(ev[ev.R > 0], False), "exemplos_entrada_perdedora_liberada": exs(ev[ev.R <= 0], True)}
    volt.to_csv(f"{D}/O41_{at}_A_operacoes_que_voltaram.csv", index=False, sep=";")
json.dump(OUT, open(f"{D}/O41_analise_causas.json", "w"), ensure_ascii=False, indent=1, default=str); print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
