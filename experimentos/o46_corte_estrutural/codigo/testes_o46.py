"""ORDEM 046 — testes da sequência do corte (alerta, recuperação, novo cruzamento, confirmação, execução, precedência, empate, ordem incerta). Uso: python testes_o46.py SAIDA.json"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corte_o46 as CT
RES = []; T0 = pd.Timestamp("2026-01-05 10:00"); K = {"contrato": 100.0, "com_lado": 3.5}; N = 100.00
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d)


def mercado(closes, highs=None, opens=None, n=90):
    c = np.full(n, 99.70); c[:len(closes)] = closes if len(closes) else c[:0]
    for k, v in (closes.items() if isinstance(closes, dict) else []): c[k] = v
    o = np.r_[c[0], c[:-1]] if opens is None else opens; h = np.maximum(o, c) + 0.01; l = np.minimum(o, c) - 0.01
    for k, v in (highs or {}).items(): h[k] = v
    m1 = pd.DataFrame({"t": [T0 + pd.Timedelta(minutes=k) for k in range(n)], "o": o, "h": h, "l": l, "c": c, "spread": 20})
    m15 = m1.assign(g=m1.t.dt.floor("15min")).groupby("g").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).reset_index().rename(columns={"g": "t"})
    return CT.Mercado(m1, m15), m1


def cl(d, faixa=None):
    """fechamentos M1: 99,70 (lado da venda) por padrão; faixa=(a,b,v) preenche [a,b] com v antes dos pontos avulsos."""
    c = np.full(90, 99.70)
    if faixa: c[faixa[0]:faixa[1] + 1] = faixa[2]
    for k, v in d.items(): c[k] = v
    return c


op = {"lado": -1, "j_ent": 2, "j_sai": 60, "entrada": 99.80, "stop": 101.80, "R": 0.5, "usd_1lote": 93.0}
mk, _ = mercado(cl({}), n=90)
mk.c1 = cl({14: 100.20}, (5, 14, 100.10)); mk.C15[0] = 100.20                      # alerta 10:05, sem recuperação, M15 10:00–10:15 fecha 100,20 > N
e = CT.corte(mk, op, N, K, desl=1.0)
reg("alerta sem recuperação + M15 além de N: corta na abertura da 1ª M1 após o fechamento M15", e["cortou"] and e["j_corte"] == 15 and abs(e["px_corte"] - (mk.o1[15] + 0.4)) < 1e-9,
    f"alerta 10:05 → decisão 10:15 → execução 10:15 a {e.get('px_corte'):.2f} (abertura {mk.o1[15]:.2f} + spread 0,20 + deslizamento 0,20)")
reg("não executa ao preço do fechamento que decidiu", abs(e["px_corte"] - mk.C15[0]) > 1e-9, f"fechamento M15 {mk.C15[0]:.2f} ≠ execução {e['px_corte']:.2f}")
mk.c1 = cl({8: 99.90, 14: 100.20}, (5, 7, 100.05)); mk.C15[0] = 100.20
e = CT.corte(mk, op, N, K)
reg("recupera o nível antes do fechamento M15: cancela; a M1 de 10:14 fecha além de novo = novo alerta, confirmado no mesmo M15", e["recuperados"] == 1 and e["n_alertas"] == 2 and e["cortou"], f"alertas={e['n_alertas']} recuperados={e['recuperados']} cortou={e['cortou']}")
mk.c1 = cl({5: 100.05, 8: 99.90}); mk.C15[0] = 99.70
e = CT.corte(mk, op, N, K); reg("recuperado (M1 de 10:08 fecha < N) e sem novo cruzamento: G1 = G0", not e["cortou"] and e["R_G1"] == op["R"], f"R_G1={e['R_G1']}")
mk.c1 = cl({5: 100.00, 14: 100.00}); mk.C15[0] = 100.00
e = CT.corte(mk, op, N, K); reg("igualar o nível não alerta", e["n_alertas"] == 0, "0 alertas")
mk.c1 = cl({20: 100.50, 29: 100.50}); mk.C15[1] = 100.50
e = CT.corte(mk, op, N, K); reg("cruzamento depois da janela de 15 min não alerta", e["n_alertas"] == 0 and not e["cortou"], "M1 10:20 fora de [10:02, 10:17)")
mk.c1 = cl({14: 100.00}, (5, 13, 100.05)); mk.C15[0] = 100.00
e = CT.corte(mk, op, N, K); reg("M15 fecha igual a N: expira (não confirma)", e["expirados"] == 1 and not e["cortou"], f"expirados={e['expirados']}")
mk.c1 = cl({}, (12, 29, 100.10)); mk.C15[0] = 100.10; mk.C15[1] = 100.10
e = CT.corte(mk, dict(op, j_sai=14), N, K); reg("saída G0 antes do fechamento M15: G0 prevalece", not e["cortou"] and e["encerrados_por_G0"] == 1, "encerrado pela saída G0")
mk.c1 = cl({14: 100.20}, (5, 13, 100.05)); mk.C15[0] = 100.20
e = CT.corte(mk, dict(op, j_sai=15), N, K); reg("saída G0 na mesma M1 da execução: empate, prevalece G0", e["empate"] and not e["cortou"] and e["R_G1"] == op["R"], "empate")
e = CT.corte(mk, dict(op, j_sai=5), N, K); reg("G0 sai na própria M1 do alerta: sem alerta (posição já fechada)", e["n_alertas"] == 0, "0 alertas")
e = CT.corte(mk, dict(op, j_sai=6), N, K); reg("alerta às 10:06 com saída G0 às 10:06: aviso SIMULTÂNEO (não é antecipação)", e["aviso_vs_saida_G0"] == "simultaneo", e["aviso_vs_saida_G0"])
mk.h1[15] = 101.70; e = CT.corte(mk, op, N, K); mk.h1[15] = mk.c1[15] + 0.01
reg("stop alcançado na M1 da execução do corte: ordem incerta marcada", e["cortou"] and e["ordem_incerta"], "h + spread ≥ stop na M1 de 10:15")
e0 = CT.corte(mk, op, N, K, desl=0); e2 = CT.corte(mk, op, N, K, desl=2)
reg("deslizamento 0/1/2 × spread piora o preço de saída da venda", e0["px_corte"] < CT.corte(mk, op, N, K, desl=1)["px_corte"] < e2["px_corte"], f"{e0['px_corte']:.2f} < … < {e2['px_corte']:.2f}")
opc = {"lado": 1, "j_ent": 2, "j_sai": 60, "entrada": 100.20, "stop": 98.20, "R": 0.5, "usd_1lote": 93.0}; mk.c1 = cl({k: 100.30 for k in range(90)}); mk.c1[5] = 99.95; mk.c1[14] = 99.90; mk.C15[0] = 99.90
mk.o1 = np.r_[mk.c1[0], mk.c1[:-1]]; e = CT.corte(mk, opc, N, K, desl=1)
reg("compra (espelho): fecha abaixo da resistência rompida + M15 abaixo → corta no bid − deslizamento", e["cortou"] and abs(e["px_corte"] - (mk.o1[15] - 0.2)) < 1e-9, f"execução {e['px_corte']:.2f}")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "versao": CT.VERSAO, "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
