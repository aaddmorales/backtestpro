# -*- coding: utf-8 -*-
"""Fidelidade estudo × motor (bt_ciclo_v1), barra a barra, nos 12 meses de cada ativo.
Compara: exaustão (degrau, gatilho, lado) em TODAS as barras; escada (transições de degrau); contador de perna;
caixa/rompimento/confirmação (eventos do motor × eventos reconstruídos no estudo)."""
import json, sys, collections
import numpy as np
import alternativas as M
CV1 = M.CV1


def rodar(sim):
    A = M.Ativo(sim); a = A.a
    t0 = lambda i: (abs(A.D[i]) >= CV1.P("D_AFASTAMENTO")) or (A.Lcor[i][1] >= CV1.P("L_PERNA_TARDIA"))
    rng = range(A.i_ini, A.i_fim + 1)
    out = {"ativo": sim, "barras": len(rng)}
    # 1) exaustão completa + escada
    div_ex = []; seq_m, seq_e = [], []
    for i in rng:
        m = CV1.exaustao(a, i, A.piv[i]); e = A.exaustao(i, t0)
        seq_m.append(m["degrau"]); seq_e.append(e["degrau"])
        if (m["degrau"], m["gatilho"], m["lado"]) != (e["degrau"], e["gatilho"], e["lado"]):
            div_ex.append(dict(i=i, ts=str(A.ts[i]), motor=[m["degrau"], m["gatilho"], m["lado"]], estudo=[e["degrau"], e["gatilho"], e["lado"]]))
    trans = lambda s: collections.Counter(f"{s[k-1]}→{s[k]}" for k in range(1, len(s)) if s[k] != s[k - 1])
    out["exaustao"] = dict(divergencias=len(div_ex), exemplos=div_ex[:10], transicoes_motor=dict(trans(seq_m)), transicoes_estudo=dict(trans(seq_e)))
    # 2) contador de perna: o estudo chama a função do motor (CV1.perna_L) — confere igualdade e registra
    div_L = sum(1 for i in rng if A.Lcor[i] != CV1.perna_L(a, i))
    out["perna"] = dict(divergencias=div_L, observacao="o estudo usa a própria função do motor (CV1.perna_L); L por pivô (A1) não tem contraparte no motor")
    # 3) caixa / rompimento / confirmação: eventos do motor por transição de estado
    ev_m = collections.defaultdict(dict)
    prev = None
    for i in rng:
        cx = CV1.caixa_estado(a, i)
        if cx and cx["estado"] == "rompida_pendente" and cx["k_romp"] == i:
            ev_m[i]["pendente"] = (round(cx["topo"], 5), round(cx["fundo"], 5), cx["lado"])
        if cx and prev and cx["k_arm"] == prev["k_arm"] and prev["estado"] == "rompida_pendente" and cx["estado"] == "rompida_confirmada":
            ev_m[prev["k_romp"]]["confirma"] = i
        if cx and prev and cx["k_arm"] == prev["k_arm"] and prev["estado"] in ("rompida_pendente", "rompida_confirmada") and cx["estado"] == "voltou_compressao":
            ev_m[prev["k_romp"]]["voltou"] = i
        prev = cx
    pend = A.pendentes()
    ev_e = {x["i"]: x for x in pend}
    so_motor = [i for i in ev_m if "pendente" in ev_m[i] and i not in ev_e]
    so_estudo = [i for i in ev_e if i not in ev_m or "pendente" not in ev_m[i]]
    ambos = [i for i in ev_e if i in ev_m and "pendente" in ev_m[i]]
    caixa_dif = [i for i in ambos if (round(ev_e[i]["topo"], 5), round(ev_e[i]["fundo"], 5), ev_e[i]["lado"]) != ev_m[i]["pendente"]]
    conf_dif = [i for i in ambos if ev_m[i].get("confirma") != ev_e[i]["A0"] and not (ev_m[i].get("confirma") is None and ev_e[i]["A0"] is None)]
    # confirmação no motor pode ocorrer depois de H barras (o estudo só olha H): separa
    conf_dif_alem_H = [i for i in conf_dif if ev_m[i].get("confirma") is not None and ev_m[i]["confirma"] - i > M.H and ev_e[i]["A0"] is None]
    out["caixa_rompimento"] = dict(
        pendentes_motor=sum(1 for i in ev_m if "pendente" in ev_m[i]), pendentes_estudo=len(ev_e), coincidentes=len(ambos),
        so_no_motor=len(so_motor), so_no_estudo=len(so_estudo), fronteiras_diferentes=len(caixa_dif),
        confirmacao_diferente=len(conf_dif), das_quais_motor_confirma_depois_de_H=len(conf_dif_alem_H),
        exemplos_so_motor=[str(A.ts[i]) for i in so_motor[:8]], exemplos_so_estudo=[str(A.ts[i]) for i in so_estudo[:8]],
        exemplos_conf=[dict(ts=str(A.ts[i]), motor=ev_m[i].get("confirma"), estudo=ev_e[i]["A0"], pend=i) for i in conf_dif[:8]])
    return out, A, ev_m, ev_e


if __name__ == "__main__":
    res = {}
    for s in sys.argv[1:]:
        r, *_ = rodar(s); res[s] = r
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str)[:4000])
    json.dump(res, open(f"fidelidade_{'_'.join(sys.argv[1:])}.json", "w"), ensure_ascii=False, indent=1, default=str)
