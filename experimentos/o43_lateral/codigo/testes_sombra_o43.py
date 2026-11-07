"""ORDEM 043 — leitor SOMBRA (terminal SIMULADO): decisões = replay contínuo com a mesma memória inicial; reinício sem duplicar; nenhuma ordem.
Uso: python testes_sombra_o43.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
PKG = "/home/claude/r005/lm043/mt5"; sys.path.insert(0, PKG); os.chdir(PKG)
import mt5_falso as F, bt_lateral_sombra_o43 as SB, estrutura_o39 as ES, estrategia_o39 as ST, formacao_o43 as FO
DADOS = "/home/claude/r005/lm014/dados/csv_limpo"; RES = []; T = tempfile.mkdtemp(prefix="o43_sombra_")
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
CFG = dict(SB.EX.CFG_PADRAO, plataforma_url=""); t0 = pd.Timestamp("2025-10-03 06:00:30"); HORAS = 30


def correr(pasta, minutos, inicio, S=None):
    if S is None: F.configurar(DADOS, inicio, common=os.path.join(T, "c")); S = SB.Sombra(F, CFG, "XAUUSD", pasta, "simulado")
    for _ in range(minutos): S.ciclo(); F.avancar(1)
    return S


A = correr(os.path.join(T, "cont"), HORAS * 60, t0); evA = [json.loads(l) for l in open(A.D.f)]
m15a = ST.ler("XAUUSD", "M15"); m1a = ST.ler("XAUUSD", "M1"); fim0 = int(np.searchsorted(m15a.t.values, np.datetime64(t0.floor("15min"))))
m15 = m15a.iloc[fim0 - SB.N_JAN: fim0 + HORAS * 4 - 1].reset_index(drop=True); m1 = m1a[(m1a.t >= m15.t.iloc[0]) & (m1a.t < m15.t.iloc[-1] + pd.Timedelta(minutes=15))].reset_index(drop=True)
M = FO.Motor("XAUUSD", m15, m1); M.mem = ES.Memoria("XAUUSD", "M15", 0.01)
for i in range(SB.N_JAN - SB.N_INI, SB.N_JAN): M.mem.nova_barra(str(m15.t.iloc[i]), str(m15.t.iloc[i] + pd.Timedelta(minutes=15)), *(float(m15[k].iloc[i]) for k in "ohlc"))
M.rodar(i0=SB.N_JAN)
ref = sorted((r["decisao"], r["barra"], r.get("regra") or "", r.get("sinal") or r.get("id") or "") for r in M.reg)
som = sorted((e["payload"]["decisao"], e["payload"]["barra"], e["payload"].get("regra") or "", e["payload"].get("sinal") or e["payload"].get("id") or "") for e in evA if e["tipo"] == "decisao")
cont = pd.Series([x[0] for x in ref]).value_counts().to_dict()
reg("sombra = replay contínuo com a mesma memória inicial (R0, R1, R2)", ref == som and len(ref) > 0, f"{len(som)} decisões (replay {len(ref)}): {cont}")
resA = sorted((e["payload"]["regra"], e["chave"], round(e["payload"]["R"], 9)) for e in evA if e["tipo"] == "resultado"); resM = sorted((r, f"XAUUSD|o43|resultado_virtual|{o['id']}", round(o["R"], 9)) for r in FO.REGRAS for o in M.ops[r])
reg("resultados virtuais da sombra = replay", resA == resM, f"{len(resA)} resultados virtuais")
B1 = correr(os.path.join(T, "rein"), 13 * 60 + 7, t0); F.configurar(DADOS, t0 + pd.Timedelta(minutes=13 * 60 + 7), common=os.path.join(T, "c"))
B2 = correr(os.path.join(T, "rein"), HORAS * 60 - (13 * 60 + 7), None, SB.Sombra(F, CFG, "XAUUSD", os.path.join(T, "rein"), "simulado"))
evB = [json.loads(l) for l in open(B2.D.f)]; kA = sorted(e["chave"] for e in evA if e["tipo"] in ("decisao", "resultado")); kB = [e["chave"] for e in evB if e["tipo"] in ("decisao", "resultado")]
reg("reinício no meio de uma barra: mesmos eventos, sem duplicar", sorted(kB) == kA and len(set(kB)) == len(kB), f"eventos {len(kB)} (contínuo {len(kA)})")
reg("nenhuma ordem (sombra)", not getattr(F, "CHAMADAS_PROIBIDAS", []), "order_send/order_check nunca chamados")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES, "nota": "terminal SIMULADO; dados XAUUSD 03–04/10/2025"}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
