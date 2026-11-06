"""ORDEM 039 §11 — exemplos positivos e negativos para a LM estudar o CONTEXTO da estrutura (não decorar barras).
Variáveis = só o que existia no fechamento do evento; rótulos = resultado POSTERIOR (colunas rotulo_*), nunca usados como entrada.
Uso: python exemplos_o39.py SAIDA_DIR"""
import os, sys, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrutura_o39 as ES, estrategia_o39 as ST, romp_m15 as RM
out = sys.argv[1]; H = 16; RES = {}
for at in ("XAUUSD", "BTCUSD"):
    m = ST.ler(at, "M15"); O, Hh, L, C = (m[k].values.astype(float) for k in "ohlc"); A = RM.atr_wilder(Hh, L, C)
    EL = pd.Series(L).ewm(span=20, adjust=False).mean().values; EH = pd.Series(Hh).ewm(span=20, adjust=False).mean().values
    mem = ES.Memoria(at, "M15"); X = []; byid = {}
    for i in range(len(m)):
        evs = mem.nova_barra(str(m.t.iloc[i]), str(m.t.iloc[i] + pd.Timedelta(minutes=15)), O[i], Hh[i], L[i], C[i])
        if i == 0 or not np.isfinite(A[i]): continue
        byid = {n["id"]: n for n in mem.niveis}
        for e in evs:
            n = byid.get(e.get("nivel")); tipo = None
            if e["evento"] == "rompimento_nao_confirmado":
                sup = n["funcao"] == "suporte"; ref = e["ref_l"] if sup else e["ref_h"]          # extremo da barra de rompimento ANTERIOR (gravado no evento)
                tipo = "toque/igualdade sem superação" if (L[i] == ref if sup else Hh[i] == ref) else "rompimento sem confirmação na barra seguinte"
            elif e["evento"] == "rompimento_confirmado": tipo = "superação válida (rótulo posterior decide continuação × perda)"
            elif e["evento"] == "teste" and e.get("rejeicao") and n["idade_barras"] > 200: tipo = "suporte/resistência antigo ainda relevante (rejeição, idade > 200 barras)"
            elif e["evento"] == "confirmado":
                outros = [k for k in mem.niveis if k["id"] != n["id"] and k["funcao"] == n["funcao"] and k["estado"] != "ROMPIMENTO CONFIRMADO" and abs(k["extremo"] - n["extremo"]) <= 3 * A[i]]
                if outros: tipo = "novo fundo/topo coexistindo com o anterior"
            elif e["evento"] == "recuperado": tipo = "falso rompimento com recuperação da zona"
            if tipo is None or n is None: continue
            s = -1 if n["funcao"] == "suporte" else 1; b, tz = n["zona"]
            X.append({"ativo": at, "tf": "M15", "t_evento": str(m.t.iloc[i] + pd.Timedelta(minutes=15)), "i": i, "nivel": n["id"], "categoria": tipo, "funcao": n["funcao"],
                      "dist_fech_zona_atr": (C[i] - (b if s < 0 else tz)) / A[i], "largura_zona_atr": (tz - b) / A[i], "idade_barras": n["idade_barras"], "testes": n["testes"], "rejeicoes": n["rejeicoes"],
                      "tentativas": n["tentativas_rompimento"], "nao_confirmados": n["rompimentos_nao_confirmados"], "membros": len(n["membros"]), "fech_menos_EMAL_atr": (C[i] - EL[i]) / A[i],
                      "fech_menos_EMAH_atr": (C[i] - EH[i]) / A[i], "ret4_atr": (C[i] - C[max(0, i - 4)]) / A[i], "corpo_atr": (C[i] - O[i]) / A[i], "atr_rel": A[i] / C[i], "zs": s, "zb": b, "zt": tz})
    D = pd.DataFrame(X)
    # rótulos POSTERIORES (16 barras)
    cont, rec = [], []
    for r in D.itertuples():
        j0, j1 = r.i + 1, min(len(m), r.i + 1 + H); a = A[r.i]
        if r.zs < 0: ext = L[j0:j1].min() if j1 > j0 else np.nan; volta = (C[j0:j1] >= r.zt).any(); c_ = (C[r.i] - ext) / a if j1 > j0 else np.nan
        else: ext = Hh[j0:j1].max() if j1 > j0 else np.nan; volta = (C[j0:j1] <= r.zb).any(); c_ = (ext - C[r.i]) / a if j1 > j0 else np.nan
        cont.append(c_); rec.append(bool(volta))
    D["rotulo_avanco_max_atr_16b"] = cont; D["rotulo_voltou_para_zona_16b"] = rec
    D["rotulo_continuacao"] = (D.rotulo_avanco_max_atr_16b >= 1) & ~D.rotulo_voltou_para_zona_16b
    D["rotulo_resultado"] = np.where(D.categoria.str.startswith("superação"), np.where(D.rotulo_continuacao, "superação seguida de continuação", np.where(D.rotulo_voltou_para_zona_16b, "superação seguida de perda (voltou à zona)", "superação sem desfecho em 16 barras")), "")
    D = D.drop(columns=["zs", "zb", "zt", "i"]); D.to_csv(f"{out}/O39_exemplos_LM_{at}.csv.gz", index=False, sep=";")
    RES[at] = {"total": len(D), "por_categoria": D.categoria.value_counts().to_dict(), "superacoes": D[D.categoria.str.startswith("superação")].rotulo_resultado.value_counts().to_dict()}
json.dump(RES, open(f"{out}/O39_exemplos_LM_resumo.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(RES, ensure_ascii=False, indent=1))
