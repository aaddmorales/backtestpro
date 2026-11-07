"""ORDEM 045 — testes da classificação A/B/C (venda e compra, igualdade, mesmo minuto, incompleto, momento do aviso). Uso: python testes_o45.py SAIDA.json"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classificar_o45 as CL
RES = []; MIN = CL.MIN; T0 = pd.Timestamp("2026-01-05 10:00").value
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d)
t1 = np.array([T0 + k * MIN for k in range(30)]); E, N = 98.50, 99.00
def c(m): x = np.full(30, 98.40); [x.__setitem__(k, v) for k, v in m.items()]; return x
r = CL.classificar(-1, E, N, T0, t1, c({})); reg("venda: nenhum fechamento acima do extremo → A", r["grupo"] == "A" and r["completo"], r["grupo"])
r = CL.classificar(-1, E, N, T0, t1, c({3: 98.50})); reg("igualar o extremo não conta → A", r["grupo"] == "A", r["grupo"])
r = CL.classificar(-1, E, N, T0, t1, c({5: 99.00})); reg("igualar o nível (acima do extremo) não é C → B", r["grupo"] == "B", r["grupo"])
r = CL.classificar(-1, E, N, T0, t1, c({4: 98.51, 9: 98.99})); reg("fecha acima do extremo, não do nível → B (aviso no fechamento da M1 4)", r["grupo"] == "B" and r["min_ate_E"] == 5.0, f"{r['grupo']} {r['min_ate_E']} min")
r = CL.classificar(-1, E, N, T0, t1, c({6: 99.01})); reg("atravessa extremo e nível no mesmo minuto → C", r["grupo"] == "C" and r["min_ate_N"] == 7.0 and r["min_ate_E"] == 7.0, f"{r['grupo']} {r['min_ate_N']} min")
r = CL.classificar(-1, E, N, T0, t1, c({15: 99.50})); reg("fechamento acima do nível no minuto 16 está fora da janela → A", r["grupo"] == "A", r["grupo"])
r = CL.classificar(-1, E, N, T0, np.delete(t1, [7, 8]), np.delete(c({}), [7, 8])); reg("lacuna na janela → incompleto", not r["completo"] and r["n_m1_janela"] == 13, f"{r['n_m1_janela']} M1")
r = CL.classificar(1, 101.50, 101.00, T0, t1, np.full(30, 101.60) - np.r_[np.zeros(3), 0.61, np.zeros(26)]); reg("compra (espelho): fecha abaixo da resistência rompida → C", r["grupo"] == "C", f"{r['grupo']}")
r = CL.classificar(1, 101.50, 101.00, T0, t1, np.full(30, 101.60) - np.r_[np.zeros(3), 0.11, np.zeros(26)]); reg("compra: fecha abaixo só do extremo → B", r["grupo"] == "B", r["grupo"])
r = CL.classificar(-1, E, N, T0, t1, c({6: 99.01})); a = r["aviso_N_ns"]
reg("aviso antes da saída só se o fechamento da M1 ≤ início da M1 de saída", (a <= T0 + 7 * MIN) and not (a <= T0 + 6 * MIN), "saída na M1 7 → antes; saída na M1 6 (mesmo minuto) → depois")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
