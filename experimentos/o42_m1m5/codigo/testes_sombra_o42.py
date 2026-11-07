"""ORDEM 042 — leitor SOMBRA (terminal SIMULADO): decisões = replay contínuo com a mesma memória inicial; reinício sem duplicar; nenhuma ordem."""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
PKG = "/home/claude/r005/lm042/mt5"; sys.path.insert(0, PKG); os.chdir(PKG)
import mt5_falso as F, bt_estrutura_sombra_o42 as SB, estrutura_o39 as ES, estrategia_o39 as ST, leitura_o42 as LQ
DADOS = "/home/claude/r005/lm014/dados/csv_limpo"; RES = []; T = tempfile.mkdtemp(prefix="o42_sombra_")
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
CFG = dict(SB.EX.CFG_PADRAO, plataforma_url=""); t0 = pd.Timestamp("2026-06-02 08:00:30"); HORAS = 24
def correr(pasta, minutos, inicio, S=None):
    if S is None: F.configurar(DADOS, inicio, common=os.path.join(T, "c")); S = SB.Sombra(F, CFG, "XAUUSD", pasta, "simulado")
    for _ in range(minutos): S.ciclo(); F.avancar(1)
    return S
A = correr(os.path.join(T, "cont"), HORAS * 60, t0); evA = [json.loads(l) for l in open(A.D.f)]
# referência: replay contínuo com a mesma memória inicial (200 M15 antes de t0) e as mesmas barras
m15a = ST.ler("XAUUSD", "M15"); m1a = ST.ler("XAUUSD", "M1"); fim0 = int(np.searchsorted(m15a.t.values, np.datetime64(t0.floor("15min"))))
m15 = m15a.iloc[fim0 - SB.N_JAN: fim0 + HORAS * 4 - 1].reset_index(drop=True); m1 = m1a[(m1a.t >= m15.t.iloc[0]) & (m1a.t < m15.t.iloc[-1] + pd.Timedelta(minutes=15))].reset_index(drop=True)
ok_all = True; det = []
for v, (e, s) in SB.VARS.items():
    rp = LQ.ReplayM1("XAUUSD", m15, m1, v, entrada=e, saida=s); rp.mem = ES.Memoria("XAUUSD", "M15", 0.01)
    for i in range(SB.N_JAN - SB.N_INI, SB.N_JAN): rp.mem.nova_barra(str(m15.t.iloc[i]), str(m15.t.iloc[i] + pd.Timedelta(minutes=15)), *(float(m15[k].iloc[i]) for k in "ohlc"))
    rp.rodar(i0=SB.N_JAN); ref = sorted((r["decisao"], r["barra"]) for r in rp.reg)
    som = sorted((e_["payload"]["decisao"], e_["payload"]["barra"]) for e_ in evA if e_["tipo"] == "decisao" and e_["payload"].get("versao_regra") == v)
    ok_all &= ref == som; det.append(f"{v}: {len(som)} decisões (replay {len(ref)})")
reg("sombra = replay contínuo com a mesma memória inicial (4 variantes)", ok_all, "; ".join(det))
B1 = correr(os.path.join(T, "rein"), 11 * 60 + 7, t0); F.configurar(DADOS, t0 + pd.Timedelta(minutes=11 * 60 + 7), common=os.path.join(T, "c"))
B2 = correr(os.path.join(T, "rein"), HORAS * 60 - (11 * 60 + 7), None, SB.Sombra(F, CFG, "XAUUSD", os.path.join(T, "rein"), "simulado"))
evB = [json.loads(l) for l in open(B2.D.f)]; kA = sorted(e["chave"] for e in evA if e["tipo"] in ("decisao", "resultado")); kB = [e["chave"] for e in evB if e["tipo"] in ("decisao", "resultado")]
reg("reinício no meio de uma barra: mesmos eventos, sem duplicar", sorted(kB) == kA and len(set(kB)) == len(kB), f"eventos {len(kB)} (contínuo {len(kA)})")
reg("nenhuma ordem (sombra)", not getattr(F, "CHAMADAS_PROIBIDAS", []), "order_send/order_check nunca chamados")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES, "nota": "terminal SIMULADO"}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
