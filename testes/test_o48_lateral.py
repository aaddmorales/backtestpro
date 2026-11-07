"""ORDEM 048 — caminho completo em ambiente SIMULADO: cartão (vitrine) → Criar bot → Enviar ao MT5 → leitor confirma com cotações do terminal
→ "Conectado" → semana de coleta com o mesmo início/fim por ativo → relatório. Plataforma = rotas /lateral reais sobre Supabase FALSO;
terminal = MT5 SIMULADO com ticks sintéticos (4 cotações por M1). NÃO é teste ao vivo. Uso: python test_o48_lateral.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); PKG = os.path.join(RAIZ, "leitor_lateral_o48")
sys.path.insert(0, RAIZ); sys.path.insert(0, PKG); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import lateral_o48 as LT, fake_sb_o48 as FS
os.chdir(PKG)
import mt5_falso_ticks as F, bt_lateral_leitor_o48 as LE, formacao_o44 as FO, estrategia_o39 as ST
RES = []; DADOS = "/home/claude/r005/lm014/dados/csv_limpo"
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)

os.environ["BT_CARD_TESTE_USER"] = "u-teste"; SB = FS.FakeSB()
def sessao(auth):
    if not auth.startswith("Bearer "): raise HTTPException(status_code=401, detail="sem sessão")
    return auth[7:]
relogio = lambda: F._F._S["agora"].tz_localize("UTC").to_pydatetime()
app = FastAPI(); app.include_router(LT.criar_router(lambda: SB, sessao, relogio)); C = TestClient(app)
H = {"Authorization": "Bearer u-teste"}; H2 = {"Authorization": "Bearer outro"}
F.configurar(DADOS, pd.Timestamp("2026-03-01 23:00"), common=tempfile.mkdtemp())

# 1 · cartão
v = LT.card_para_vitrine({"estrategias": [{"id": "x"}]}, "u-teste"); v2 = LT.card_para_vitrine({"estrategias": [{"id": "x"}]}, "outro")
c = v["estrategias"][0]
reg("cartão aparece só para o usuário de teste, com selo 'Experimental · teste em sombra' e sem medição herdada",
    c["id"] == "lateral_r0" and c["selo"] == "Experimental · teste em sombra" and c["winrate_medio"] is None and c["celulas_aprovadas"] == [] and c["medida"] is False and len(v2["estrategias"]) == 1,
    f"{c['nome']} · ativos {c['mercados']} · TF {c['timeframes']} · regra {c['regra_versao']}")
reg("outro usuário não vê as rotas do cartão (404 sem oráculo)", C.post("/lateral/bots/listar", json={}, headers=H2).status_code == 404, "404")
# 2 · criar
d = C.post("/lateral/bots/criar", json={"ativos": ["XAUUSD", "BTCUSD"], "tfs": ["M15", "M30", "H1"]}, headers=H).json()
d2 = C.post("/lateral/bots/criar", json={"ativos": ["XAUUSD"], "tfs": ["M15"]}, headers=H).json()
reg("Criar bot: 6 bots (XAU/BTC × M15/M30/H1), sem duplicar", len(d["criados"]) == 6 and len(d2["criados"]) == 0 and len(d2["ja_existiam"]) == 1, ", ".join(b["nome"] for b in d["criados"]))
ids = {(b["ativo"], b["tf"]): b["id"] for b in d["criados"]}
# 3 · chave e envio
ch = C.post("/lateral/chave/gerar", json={}, headers=H).json()["chave"]
reg("chave do leitor inválida é recusada", C.post("/lateral/leitor/bots", json={"chave": "lat_invalida_xxx"}).status_code == 401, "401")
lst0 = C.post("/lateral/leitor/bots", json={"chave": ch}).json()["bots"]
C.post("/lateral/bots/enviar", json={"bot_ids": list(ids.values())}, headers=H)
lst = C.post("/lateral/bots/listar", json={}, headers=H).json()["bots"]
reg("Enviar ao MT5: bots ficam 'enviado' (aguardando o terminal) — 'Conectado' ainda não aparece", len(lst0) == 0 and all(b["estado"] == "enviado" for b in lst), ", ".join(sorted({b["estado"] for b in lst})))
# 4 · leitor no terminal simulado
P = LE.Plataforma("http://plataforma", ch, post=lambda rota, corpo: C.post(rota, json=corpo).json())
L = LE.Leitor(F, P, tempfile.mkdtemp(), {"XAUUSD": "XAUUSD", "BTCUSD": "BTCUSD"}, demo_obrigatoria=False)
seg = lambda: F._F._S["agora"].timestamp()
def rodar(minutos):
    for _ in range(minutos): L.ciclo(seg()); F.avancar(1)
t0 = time.time(); rodar(130)
lst = {b["id"]: b for b in C.post("/lateral/bots/listar", json={}, headers=H).json()["bots"]}
conf_ok = all(b["estado"] in ("conectado", "coletando") and b["confirmacao"].get("simbolo_efetivo") == b["ativo"] and b["confirmacao"].get("timeframe") == b["tf"]
              and b["confirmacao"].get("modo") == "sombra" and b["confirmacao"].get("regra_versao") == LT.VERSAO_REGRA and b["confirmacao"]["cotacao"].get("bid") for b in lst.values())
reg("terminal confirmou os 6 bots: ID, símbolo efetivo, timeframe, versão da regra e modo sombra, com cotação lida → Conectado", conf_ok,
    "; ".join(f"{b['id']} {b['confirmacao'].get('simbolo_efetivo')} {b['confirmacao'].get('timeframe')} bid {b['confirmacao'].get('cotacao', {}).get('bid')}" for b in lst.values()))
jan = {at: {(b["coleta_inicio"], b["coleta_fim"]) for b in lst.values() if b["ativo"] == at} for at in ("XAUUSD", "BTCUSD")}
reg("semana com o MESMO início e fim para os 3 TF de cada ativo, depois de 1 h de verificação técnica", all(len(v) == 1 and list(v)[0][0] for v in jan.values()),
    "; ".join(f"{at}: {list(v)[0][0]} → {list(v)[0][1]}" for at, v in jan.items()))
ini_xau = pd.Timestamp(list(jan["XAUUSD"])[0][0]).tz_convert(None)
rodar(3 * 1440)
C.post("/lateral/bots/parar", json={"bot_ids": [ids[("BTCUSD", "H1")]]}, headers=H)
n_btch1 = len(SB.t.get("lateral_eventos", [])); rodar(31)
ev_depois = [e for e in SB.t["lateral_eventos"][n_btch1:]]
so_status = all(e["tipo"] in ("status",) for e in ev_depois if e["bot_id"] == ids[("BTCUSD", "H1")]); outros = any(e["bot_id"] != ids[("BTCUSD", "H1")] for e in ev_depois)
reg("Parar afeta só o bot escolhido do teste; os demais seguem lendo", so_status and outros, f"eventos depois do parar: {len(ev_depois)} ({sum(1 for e in ev_depois if e['bot_id'] == ids[('BTCUSD', 'H1')])} do BTC H1, só 'status')")
rodar(1440); dur = round(time.time() - t0)
EV = pd.DataFrame(SB.t["lateral_eventos"]); EV["t"] = pd.to_datetime(EV.t_evento, format="mixed", utc=True).dt.tz_convert(None)
arm = EV[EV.tipo == "gatilho_armado"]
reg("nenhum gatilho armado antes do início da semana", (arm.t >= ini_xau - pd.Timedelta(hours=1)).all() and len(arm) > 0, f"{len(arm)} gatilhos; 1º em {arm.t.min()} (início XAU {ini_xau})")
# 5 · leitor × replay O44 no mesmo período (XAU M15 e BTC M15)
res = {}
for at, tf, mn in (("XAUUSD", "M15", 15), ("XAUUSD", "M30", 30), ("BTCUSD", "M15", 15)):
    b = [x for x in lst.values() if x["ativo"] == at and x["tf"] == tf][0]; ini = pd.Timestamp(b["coleta_inicio"]).tz_convert(None); fim = F._F._S["agora"]
    m1 = ST.ler(at, "M1"); dd = ST.ler(at, tf); M = FO.Motor(at, dd, m1, tf_min=mn)
    i0 = int(np.searchsorted(dd.t.values, np.datetime64(ini))); i1 = int(np.searchsorted((dd.t + pd.Timedelta(minutes=mn)).values, np.datetime64(fim), side="right")); M.rodar(i0=i0, i1=i1)
    e = EV[EV.bot_id == b["id"]]; ent = e[e.tipo == "entrada_virtual"]
    rep = {o["id"].split("-", 2)[2]: pd.Timestamp(int(o["t_ent"])) for o in M.ops["R0"] + ([M.pos["R0"]] if M.pos["R0"] else [])}
    viv = {p["id"].split("-", 2)[2]: pd.Timestamp(t).floor("min") for p, t in zip(ent.payload, ent.t)}
    armv = {p["sinal"].split("-", 2)[2] for p in e[e.tipo == "gatilho_armado"].payload}; armr = {s["id"].split("-", 1)[1] for s in M.sinais}
    res[f"{at} {tf}"] = {"gatilhos": [len(armv), len(armr)], "entradas": [len(viv), len(rep)], "iguais": armv == armr and viv == rep,
                          "so_no_leitor": sorted(armv - armr), "so_no_replay": sorted(armr - armv), "fim_replay": str(fim)}
reg("leitor do cartão = replay O44 no mesmo período (mesmos gatilhos, entradas e minuto de entrada)", all(x["iguais"] for x in res.values()), json.dumps(res, ensure_ascii=False))
# 6 · relatório
R = C.post("/lateral/relatorio", json={}, headers=H).json()["bots"]
tem = {k: {t for t in (e["tipo"] for e in v["eventos"])} for k, v in R.items()}
need = {"contadores", "status"}
reg("relatório por bot: contadores e status em todos; gatilhos, entradas/saídas, retorno A/B/C e gráficos (barras nos eventos) onde houve sinal", all(need <= t for t in tem.values()) and any("retorno" in t for t in tem.values()) and any("saida_virtual" in t for t in tem.values())
    and any((e["payload"] or {}).get("barras") for v in R.values() for e in v["eventos"] if e["tipo"] == "entrada_virtual"),
    "; ".join(f"{R[k]['bot']['nome']}: {len(R[k]['eventos'])} eventos" for k in R))
reg("nenhuma ordem enviada", not F.CHAMADAS_PROIBIDAS and "order_send" not in open(os.path.join(PKG, "bt_lateral_leitor_o48.py")).read() and "order_send" not in open(os.path.join(RAIZ, "lateral_o48.py")).read(), "order_send/order_check nunca chamados")
cont = {R[k]["bot"]["nome"]: [e["payload"] for e in R[k]["eventos"] if e["tipo"] == "contadores"][-1] for k in R}
print(json.dumps(cont, ensure_ascii=False)[:1500], dur, "s")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES, "contadores_simulados": cont,
                                 "nota": "plataforma com Supabase FALSO e terminal SIMULADO (ticks sintéticos): NÃO é teste ao vivo"}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
