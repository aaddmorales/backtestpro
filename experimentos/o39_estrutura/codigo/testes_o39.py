"""ORDEM 039 §12 — testes obrigatórios da memória estrutural (estrutura-0.1) e do gatilho de superação (ESTR-EMA-M15-0.1). Uso: python testes_o39.py SAIDA.json"""
import os, sys, json, time, tempfile, copy
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrutura_o39 as ES, estrategia_o39 as ST


def sint(precos15, inicio="2026-01-05 00:00", spread=0):
    """mesmo construtor sintético da experiência ROMP: cada M15 = 15 M1 (1ª M1 abre no 'o', 2ª atinge a máxima, 3ª a mínima, a última fecha no 'c')."""
    t = pd.date_range(inicio, periods=len(precos15), freq="15min"); m15 = pd.DataFrame(precos15, columns=["o", "h", "l", "c"]); m15["t"] = t; m15["spread"] = spread; rows = []
    for (o, h, l, c), tt in zip(precos15, t):
        for k in range(15):
            ts = tt + pd.Timedelta(minutes=k)
            if k == 1: rows.append((ts, o, h, min(o, h), o))
            elif k == 2: rows.append((ts, o, o, l, o))
            elif k == 14: rows.append((ts, o, max(o, c), min(o, c), c))
            else: rows.append((ts, o, o, o, o))
    m1 = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]); m1["spread"] = spread
    return m15[["t", "o", "h", "l", "c", "spread"]], m1
RES = []
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
def rodar(P, v):
    m15, m1 = sint(P); rp = ST.Replay("XAUUSD", m15, m1, v); rp.rodar(i0=2); rp.todas = rp.ops + ([rp.pos] if rp.pos else []); return rp, m15


base = [(100.5, 101, 100, 100.5)] * 40
# cenário de venda de média SEM obstáculo (nenhum fundo estrito abaixo): barra 40 sinal, barra 41 testa a mínima
def cen(l41, l42=None):
    P = list(base) + [(100.5, 100.6, 99.6, 99.8)] + [(99.8, 99.9, l41, 99.85)] + [(99.85, 99.9, l42 if l42 else 99.7, 99.8)] + [(99.8, 99.9, 99.75, 99.8)] * 3
    return P
rp, m = rodar(cen(99.6), "V0")
reg("igualdade com a mínima da barra de referência NÃO abre", not rp.ops and any(r["decisao"] == "gatilho_expirado" for r in rp.reg), "mínima da 41 = 99,60 = mínima da 40 → gatilho expirado, sem entrada")
rp, m = rodar(cen(99.59), "V0")
reg("um tick além (99,59) satisfaz a condição", len(rp.todas) == 1 and abs(rp.todas[0]["bid_gatilho"] - 99.59) < 1e-9, f"entrada no bid {rp.todas[0]['entrada'] if rp.todas else None}")
reg("entrada intrabar, sem esperar o fechamento da barra", rp.todas and m.t.iloc[41] < pd.Timestamp(rp.todas[0]["t_ent"]) < m.t.iloc[41] + pd.Timedelta(minutes=15),
    f"entrada às {pd.Timestamp(rp.todas[0]['t_ent']) if rp.todas else None} (barra 41 de {m.t.iloc[41]} a +15 min)")
rp, m = rodar(cen(99.65, 99.0), "V0")
reg("o gatilho vale SÓ para a barra imediatamente seguinte", not rp.todas, "a 41 não superou; a 42 caiu abaixo, mas o gatilho já tinha expirado → nenhuma entrada")
# obstáculo: fundo estrito em 99,0 na barra 25 → suporte confirmado; sinal de venda em 40 com entrada proposta 99,59
P = list(base); P[25] = (100.5, 101, 99.0, 100.5); P += [(100.5, 100.6, 99.6, 99.8), (99.8, 99.9, 99.5, 99.7), (99.7, 99.75, 98.7, 98.8), (98.8, 98.85, 98.70, 98.75), (98.75, 98.8, 98.6, 98.65), (98.65, 98.7, 98.0, 98.1), (98.1, 98.2, 97.9, 98.0)]
rp0, m = rodar(P, "V0"); rp1, _ = rodar(P, "V1")
esp = [r for r in rp1.reg if r["decisao"] == "aguardando"]
reg("V1: sinal de média suspenso diante do suporte próximo (V0 entra)", rp0.todas and esp and esp[0]["motivo"].startswith(ST.MSG_ESPERA) and esp[0]["obstaculo"]["proximo"],
    f"V0 entradas {len(rp0.todas)}; V1: '{esp[0]['motivo'] if esp else None}' · d = {esp[0]['obstaculo']['distancia']:.2f} ({esp[0]['obstaculo']['dist_atr']:.2f} ATR) ≤ limiar {esp[0]['obstaculo']['limiar']:.2f}" if esp else "")
arm = [r for r in rp1.reg if r["decisao"] == "gatilho_armado"]; exp_ = [r for r in rp1.reg if r["decisao"] == "gatilho_expirado"]
reg("V1: barra que fecha abaixo do suporte vira referência; a seguinte só confirma superando a mínima (igualar não)", arm and arm[0]["barra"] == str(m.t.iloc[42]) and exp_ and not any(o["referencia"] == str(m.t.iloc[42]) for o in rp1.todas),
    f"armado na {arm[0]['barra'] if arm else None} (gatilho {arm[0].get('nivel_gatilho') if arm else None}); barra 43 mínima 98,70 = igual à da 42 → {exp_[0]['decisao'] if exp_ else 'sem expiração'}")
M = rp1.mem; n0 = [n for n in M.niveis if n["tipo"] == "fundo" and abs(n["extremo"] - 99.0) < 1e-9]
reg("tentativa frustrada não apaga o suporte (contador registrado)", n0 and n0[0]["rompimentos_nao_confirmados"] >= 1, f"nível {n0[0]['id'] if n0 else None}: estado {n0[0]['estado'] if n0 else None}, rompimentos não confirmados {n0[0]['rompimentos_nao_confirmados'] if n0 else None}")
reg("horário do extremo e da confirmação separados (confirmação = fechamento da barra i+2)", n0 and pd.Timestamp(n0[0]["t_confirmacao"]) == m.t.iloc[27] + pd.Timedelta(minutes=15),
    f"extremo {n0[0]['t_extremo'] if n0 else None} · confirmação {n0[0]['t_confirmacao'] if n0 else None}")
# memória longa: nível antigo continua após sair da janela de 200; novos extremos não sobrescrevem; agrupamento explícito
mem = ES.Memoria("T", "M15"); t0 = pd.Timestamp("2026-01-05")
def barra(k, o, h, l, c): return mem.nova_barra(str(t0 + pd.Timedelta(minutes=15 * k)), str(t0 + pd.Timedelta(minutes=15 * (k + 1))), o, h, l, c)
for k in range(400):
    l = 99.0 if k == 30 else (95.0 if k == 330 else (99.05 if k == 60 else (95.5 if k == 360 else 100.0)))
    barra(k, 100.5, 101, l, 100.5)
ids = [(n["extremo"], len(n["membros"]), n["estado"]) for n in mem.niveis]
reg("nível antigo permanece após sair da janela de 200 barras", any(abs(e - 99.0) < 1e-9 for e, _, _ in ids), f"níveis: {ids}")
reg("fundo próximo (99,05 a 0,05 do 99,00) é AGRUPADO explicitamente; fundo distante (95,5 × 95,0) coexiste", any(abs(e - 99.0) < 1e-9 and k == 2 for e, k, _ in ids) and sum(abs(e - 95.0) < 1e-9 or abs(e - 95.5) < 1e-9 for e, _, _ in ids) == 2,
    "99,00 com 2 membros (duplo); 95,00 e 95,50 como níveis distintos (distância > 0,25×ATR)")
# reinício: salvar no meio e continuar = execução contínua
P2 = list(P) + [(98.0, 99.5, 97.9, 99.4), (99.4, 99.6, 99.3, 99.5)] * 10
m15, m1 = sint(P2); full = ST.Replay("XAUUSD", m15, m1, "V1"); full.rodar(i0=2)
d = tempfile.mkdtemp(); a = ST.Replay("XAUUSD", m15, m1, "V1"); a.rodar(i0=2, i1=42); ST.salvar_estado(a, f"{d}/m.json", f"{d}/e.json", 42)
b = ST.Replay("XAUUSD", m15, m1, "V1"); ip = ST.carregar_estado(b, f"{d}/m.json", f"{d}/e.json"); b.rodar(i0=ip)
reg("reinício restaura níveis e gatilhos com horários corretos (= execução contínua)", json.dumps(b.mem.niveis, sort_keys=True, default=str) == json.dumps(full.mem.niveis, sort_keys=True, default=str)
    and [r["decisao"] + r["barra"] for r in b.reg] == [r["decisao"] + r["barra"] for r in full.reg] and len(b.ops) == len(full.ops), f"{len(full.mem.niveis)} níveis e {len(full.reg)} decisões idênticos após reiniciar na barra 42 (gatilho armado na 42 restaurado)")
# sem dados futuros: memória truncada = memória contínua até cada barra; obstáculos só com níveis já confirmados
X = ST.ler("XAUUSD", "M15").iloc[:3000]; memA = ES.Memoria("XAUUSD", "M15"); snaps = {}
for i, r in enumerate(X.itertuples()):
    memA.nova_barra(str(r.t), str(r.t + pd.Timedelta(minutes=15)), r.o, r.h, r.l, r.c)
    if i in (1000, 2000, 2999): snaps[i] = json.dumps(memA.niveis, sort_keys=True)
ok = True
for i, s in snaps.items():
    memB = ES.Memoria("XAUUSD", "M15")
    for r in X.iloc[:i + 1].itertuples(): memB.nova_barra(str(r.t), str(r.t + pd.Timedelta(minutes=15)), r.o, r.h, r.l, r.c)
    ok &= json.dumps(memB.niveis, sort_keys=True) == s
fut = sum(pd.Timestamp(n["t_confirmacao"]) < pd.Timestamp(n["t_extremo"]) + pd.Timedelta(minutes=45) for n in memA.niveis)
reg("sem dados futuros: memória truncada = memória contínua; confirmação nunca antes de extremo + 3 barras", ok and fut == 0, f"3 cortes conferidos; níveis com confirmação precoce: {fut}")
dv = pd.read_csv("/home/claude/r005/lm039/saida/replay/O39_XAUUSD_V1_decisoes.csv.gz", sep=";"); o1 = pd.read_csv("/home/claude/r005/lm039/saida/replay/O39_XAUUSD_V1_operacoes.csv", sep=";")
reg("uma entrada por gatilho (sem duplicidade) no replay completo", o1.id.is_unique and (dv.decisao == "entrada").sum() == len(o1), f"{len(o1)} entradas, ids únicos")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
