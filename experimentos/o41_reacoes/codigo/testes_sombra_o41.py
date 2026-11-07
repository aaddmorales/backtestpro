"""ORDEM 039 — leitor SOMBRA no terminal SIMULADO: equivalência com o replay (mesmas 200 barras iniciais), reinício sem duplicar e com gatilhos restaurados,
nenhuma ordem. Uso: python testes_sombra_o39.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
PKG = "/home/claude/r005/lm041/mt5"; sys.path.insert(0, PKG); os.chdir(PKG)
import mt5_falso as F, bt_estrutura_sombra_o41 as SB, janela_o40 as JN, reacoes_o41 as RQ, estrutura_o39 as ES, estrategia_o39 as ST, romp_m15 as RM
DADOS = "/home/claude/r005/lm014/dados/csv_limpo"; RES = []; T = tempfile.mkdtemp(prefix="o41_sombra_")
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
CFG = dict(SB.EX.CFG_PADRAO, plataforma_url="")
t0 = pd.Timestamp("2026-06-02 08:00:30"); NB = 48                             # 48 barras M15 (12 h), ciclo a cada minuto
def correr(pasta, minutos, inicio):
    F.configurar(DADOS, inicio, common=os.path.join(T, "c")); S = SB.Sombra(F, CFG, "XAUUSD", pasta, "simulado")
    for _ in range(minutos): S.ciclo(); F.avancar(1)
    return S
A = correr(os.path.join(T, "cont"), NB * 15, t0)
evA = [json.loads(l) for l in open(A.D.f)]
reg("inicialização com 200 M15 concluídas e incremento a cada barra", evA[0]["payload"]["evento"].startswith("memória reconstruída com as 200") and A.mem.n_barras == 200 + NB - 1,
    f"{evA[0]['payload']['evento']}; barras na memória {A.mem.n_barras} (= 200 + 47 concluídas em 12 h de relógio); níveis {len(A.mem.niveis)}")
# equivalência com o replay alimentado pelas MESMAS barras
m15 = ST.ler("XAUUSD", "M15"); fim0 = int(np.searchsorted(m15.t.values, np.datetime64(t0.floor("15min")))); ini = fim0 - 200
mem = ES.Memoria("XAUUSD", "M15", 0.01); dec = []
X = m15.iloc[:fim0 + NB].reset_index(drop=True); EH = pd.Series(X.h).ewm(span=20, adjust=False).mean().values; EL = pd.Series(X.l).ewm(span=20, adjust=False).mean().values; AT = RM.atr_wilder(X.h, X.l, X.c)
esp = {"Ref": None, "A": None, "B": None}; rc = RQ.Reacoes()
for i in range(ini, fim0 + NB - 1):
    r = X.iloc[i]; f_ = int(r.t.value) + 15 * 60 * 10**9; cp = mem.c_ant; evs = mem.nova_barra(str(r.t), str(pd.Timestamp(f_)), r.o, r.h, r.l, r.c); rc.atualizar(mem, evs, r.h, r.l, r.c, cp, mem.atr, str(pd.Timestamp(f_)))
    if i < fim0: continue
    for v in ("Ref", "A", "B"):
        args = (X.c[i], X.c[i - 1], EL[i], EL[i - 1], EH[i], EH[i - 1], X.h[i], X.l[i], AT[i], str(r.t), f_, evs)
        rr = JN.decidir_janela(mem, esp[v], *args) if v == "Ref" else RQ.decidir_q(v, mem, rc, esp[v], *args); esp[v] = rr["espera"]
        dec += [(v, x["decisao"], f_) for x in rr["regs"]]
dS = [(e["payload"]["versao_regra"], e["payload"]["decisao"], int(pd.Timestamp(e["t"]).value)) for e in evA if e["tipo"] == "decisao" and e["payload"]["decisao"] not in ("superacao_observada", "gatilho_expirado")]
reg("sombra = replay com as mesmas barras (memória, reações e decisões Ref, A e B)", json.dumps(mem.niveis, sort_keys=True) == json.dumps(A.mem.niveis, sort_keys=True) and json.dumps(rc.s, sort_keys=True) == json.dumps(A.reac.s, sort_keys=True) and sorted(dS) == sorted(dec),
    f"níveis {len(mem.niveis)} iguais; decisões {len(dec)} iguais")
obs = [e for e in evA if e["tipo"] == "decisao" and e["payload"]["decisao"] in ("superacao_observada", "gatilho_expirado")]
arm = [e for e in evA if e["tipo"] == "decisao" and e["payload"]["decisao"] == "gatilho_armado"]
reg("todo gatilho armado termina em superação observada OU expiração na barra seguinte (uma vez)", len(obs) == len(arm), f"armados {len(arm)}; desfechos {len(obs)} ({sum(e['payload']['decisao'] == 'superacao_observada' for e in obs)} superações)")
# reinício no meio: mesma pasta, mesmo relógio
B1 = correr(os.path.join(T, "rein"), 20 * 15 + 7, t0)                       # para no meio de uma barra
F.configurar(DADOS, t0 + pd.Timedelta(minutes=20 * 15 + 7), common=os.path.join(T, "c")); B2 = SB.Sombra(F, CFG, "XAUUSD", os.path.join(T, "rein"), "simulado")
for _ in range(NB * 15 - (20 * 15 + 7)): B2.ciclo(); F.avancar(1)
evB = [json.loads(l) for l in open(B2.D.f)]; kA = [e["chave"] for e in evA if e["tipo"] == "decisao"]; kB = [e["chave"] for e in evB if e["tipo"] == "decisao"]
reg("reinício restaura memória e gatilhos (resultado = execução contínua) e não duplica eventos", json.dumps(B2.mem.niveis, sort_keys=True) == json.dumps(A.mem.niveis, sort_keys=True) and json.dumps(B2.reac.s, sort_keys=True) == json.dumps(A.reac.s, sort_keys=True) and sorted(kA) == sorted(kB) and len(set(kB)) == len(kB),
    f"decisões {len(kB)} (contínua {len(kA)}); chaves únicas; restaurado: {any(e['payload'].get('evento') == 'memória e gatilhos restaurados' for e in evB)}")
reg("nenhuma ordem (sombra)", not getattr(F, "CHAMADAS_PROIBIDAS", []), "order_send/order_check nunca chamados")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES, "nota": "terminal SIMULADO"}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
