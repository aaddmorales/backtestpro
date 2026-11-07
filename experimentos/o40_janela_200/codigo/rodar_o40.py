"""ORDEM 040 — replay comparativo V0 × V1 × V1-200 (mesmos dados, custos, gatilho, stop e gestão). Uso: python rodar_o40.py ATIVO SAIDA_DIR"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrategia_o39 as ST, janela_o40 as JN
at, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); m15, m1 = ST.ler(at, "M15"), ST.ler(at, "M1"); R = {"ativo": at, "janela": JN.VERSAO}; OPS, REG = {}, {}
CORTE = "2026-05-01"
for v in ("V0", "V1", "V1-200"):
    t0 = time.time(); rp = JN.ReplayJanela(at, m15, m1, v) if v == "V1-200" else ST.Replay(at, m15, m1, v); rp.rodar()
    o = pd.DataFrame(rp.ops); g = pd.DataFrame(rp.reg); OPS[v], REG[v] = o, g; eq = ST.curva(o, m1, ST.CUSTO[at]) if len(o) else None
    oos = pd.to_datetime(o.t_ent) >= CORTE; cut = int(np.searchsorted(m1.t.values, np.datetime64(CORTE)))
    dec = g.decisao.value_counts().to_dict()
    R[v] = {"geral": ST.metricas(o, eq), "desenvolvimento": ST.metricas(o[~oos], eq[:cut] if eq is not None else None), "fora_da_amostra": ST.metricas(o[oos], (eq[cut:] - eq[cut]) if eq is not None else None),
            "compras": ST.metricas(o[o.lado > 0]), "vendas": ST.metricas(o[o.lado < 0]), "decisoes": dec, "segundos": round(time.time() - t0, 1)}
    sinais = g[(g.decisao.isin(["aguardando", "gatilho_armado"])) & (g.get("condicao", pd.Series(dtype=str)).astype(str).str.startswith("fech") | (g.decisao == "aguardando"))]
    ini = g[g.decisao.isin(["aguardando", "gatilho_armado"]) & ~g.motivo.astype(str).str.contains("rompimento|novo obstáculo")]
    R[v]["sinais_de_media"] = {"bloqueados_espera": int((ini.decisao == "aguardando").sum()), "liberados_gatilho_direto": int((ini.decisao == "gatilho_armado").sum()),
                               "esperas_por_segundo_nivel": int(g.motivo.astype(str).str.contains("novo obstáculo").sum()),
                               "esperas_encerradas_por_inelegibilidade": int(dec.get("espera_encerrada_inelegivel", 0)), "esperas_canceladas_volta_ao_canal": int(dec.get("espera_cancelada", 0)),
                               "gatilhos_por_rompimento_estrutural": int(g.motivo.astype(str).str.startswith("barra de rompimento").sum())}
    if v == "V1-200":
        c = np.array(rp.contagem); c = c[c[:, 0] > 200]
        R["niveis_por_barra"] = {"memoria_acumulada_relevantes": {"media": round(float(c[:, 1].mean()), 1), "mediana": float(np.median(c[:, 1])), "p90": float(np.percentile(c[:, 1], 90))},
                                 "elegiveis_janela_200": {"media": round(float(c[:, 2].mean()), 1), "mediana": float(np.median(c[:, 2])), "p90": float(np.percentile(c[:, 2], 90)), "maximo": int(c[:, 2].max())}}
        ob = [x.get("obstaculo") for x in rp.reg if x["decisao"] in ("aguardando", "gatilho_armado") and isinstance(x.get("obstaculo"), dict)]
        R["V1-200"]["obstaculo_registrado"] = {"com_nivel_a_frente": len(ob), "dist_atr_mediana": round(float(np.median([b["dist_atr"] for b in ob])), 2) if ob else None,
                                               "com_seguinte": sum(b["seguinte"] is not None for b in ob), "dist_seguinte_atr_mediana": round(float(np.median([b["seguinte"]["dist_atr"] for b in ob if b["seguinte"]])), 2) if ob else None}
    o.to_csv(f"{out}/O40_{at}_{v}_operacoes.csv", index=False, sep=";"); g.to_csv(f"{out}/O40_{at}_{v}_decisoes.csv.gz", index=False, sep=";")
    print(at, v, R[v]["geral"].get("n"), R[v]["geral"].get("R_total"), round(time.time() - t0), "s", flush=True)
# preservação: V0 e V1 idênticas às da O39?
for v in ("V0", "V1"):
    a = pd.read_csv(f"/home/claude/r005/lm039/saida/replay/O39_{at}_{v}_operacoes.csv", sep=";"); b = pd.read_csv(f"{out}/O40_{at}_{v}_operacoes.csv", sep=";")
    cols = ["sinal", "t_ent", "entrada", "stop", "t_sai", "saida", "R"]; R[f"{v}_identica_O39"] = bool(len(a) == len(b) and np.allclose(a[cols[1:]].values.astype(float), b[cols[1:]].values.astype(float)) and (a.sinal == b.sinal).all())
def comp(base, nova):
    a, b = OPS[base], OPS[nova]; sa, sb = set(a.sinal), set(b.sinal); ev = a[~a.sinal.isin(sb)]; volt = b[b.sinal.isin(sa - set())]
    com = a.merge(b[["sinal", "t_ent", "R"]], on="sinal", suffixes=("_a", "_b"))
    return {"entradas": [len(a), len(b)], "da_base_que_a_nova_nao_fez": int(len(ev)), "vencedoras_descartadas": int((ev.R > 0).sum()), "R_dessas": round(float(ev.R.sum()), 2),
            "da_nova_sem_par_na_base": int((~b.sinal.isin(sa)).sum()), "mesmo_sinal_nas_duas": int(len(com)),
            "atraso_min_mediana_quando_entrou_depois": round(float(((com.t_ent_b - com.t_ent_a) / 6e10)[com.t_ent_b > com.t_ent_a].median()), 1) if (com.t_ent_b > com.t_ent_a).any() else 0.0,
            "entrou_depois": int((com.t_ent_b > com.t_ent_a).sum())}
R["comparacao"] = {"V0_x_V1": comp("V0", "V1"), "V0_x_V1-200": comp("V0", "V1-200"), "V1_x_V1-200": comp("V1", "V1-200")}
v1, v2 = OPS["V1"], OPS["V1-200"]; voltaram = v2[~v2.sinal.isin(set(v1.sinal))]
R["entradas_que_voltaram_V1-200_sem_par_na_V1"] = {"n": int(len(voltaram)), "R_total": round(float(voltaram.R.sum()), 2), "acerto": round(float((voltaram.R > 0).mean()), 4) if len(voltaram) else None,
                                                   "fora_da_amostra": int((pd.to_datetime(voltaram.t_ent) >= CORTE).sum())}
voltaram.to_csv(f"{out}/O40_{at}_entradas_que_voltaram.csv", index=False, sep=";")
json.dump(R, open(f"{out}/O40_{at}_resultado.json", "w"), ensure_ascii=False, indent=1, default=str); print("FIM", at)
