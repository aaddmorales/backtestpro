"""ROMP-M15-0.1 — testes do EXECUTOR bt_romp_m15_v001 no terminal MT5 SIMULADO (mt5_falso_exec; conta, preenchimento e comissão SIMULADOS).
Lote 0,01 só de TESTE no simulador (não é autorização para a DEMO). Uso: python testes_executor_romp.py SAIDA.json"""
import os, sys, json, time, shutil, tempfile
import numpy as np, pandas as pd
PKG = "/home/claude/r005/rompimento/mt5"; sys.path.insert(0, PKG); os.chdir(PKG)
import mt5_falso_exec as F, bt_romp_m15_v001 as RX
DADOS = "/home/claude/r005/lm014/dados/csv_limpo"; RES = []; TMP = tempfile.mkdtemp(prefix="romp_exec_")
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
def evs(S): return [json.loads(l) for l in open(S.D.f)]
CFG = lambda dim: dict(RX.CFG_PADRAO, plataforma_url="", dimensionamento=dim)
ops = pd.read_csv("/home/claude/r005/rompimento/saida/bancada/ROMP_operacoes.csv", sep=";")
ops = ops[(~ops.aberta_no_fim_dos_dados) & (pd.to_datetime(ops.barra_sinal) >= "2026-05-01")]
ALVOS = [ops[ops.motivo_saida == "stop de proteção"].iloc[0], ops[ops.motivo_saida != "stop de proteção"].iloc[0]]

# 1) sem dimensionamento autorizado: sinal vira impedimento, nenhuma ordem
o = ALVOS[0]; fim = pd.Timestamp(o.barra_sinal) + pd.Timedelta(minutes=15)
F.configurar(DADOS, fim + pd.Timedelta(seconds=20), common=os.path.join(TMP, "c")); S = RX.Romp(F, CFG({"modo": None, "valor": None}), os.path.join(TMP, "bloq"), "simulado"); S.ciclo()
E = evs(S); imp = [e for e in E if e["tipo"] == "impedimento"]
reg("sem lote/risco autorizado: sinal registrado como impedimento, nenhuma ordem", not F.X["envios"] and imp and "NÃO autorizado" in imp[0]["payload"]["motivo"] and any(e["tipo"] == "decisao" and e["payload"]["acao"] in ("comprar", "vender") for e in E),
    f"envios {len(F.X['envios'])}; impedimento: {imp[0]['payload']['motivo'][:70] if imp else None}")

for n, o in enumerate(ALVOS):
    fim = pd.Timestamp(o.barra_sinal) + pd.Timedelta(minutes=15); F.configurar(DADOS, fim + pd.Timedelta(seconds=20), common=os.path.join(TMP, "c")); pasta = os.path.join(TMP, f"op{n}")
    S = RX.Romp(F, CFG({"modo": "lote_fixo", "valor": 0.01}), pasta, "simulado"); S.ciclo(); est = S.est["posicao"]
    reg(f"[{o.id}] entrada na 1ª cotação após o fechamento = bancada", est is not None and est["lado"] == o.lado and abs(est["entrada"] - o.entrada) < 1e-6, f"executor {est and est['entrada']} × bancada {o.entrada}; lado {o.lado}")
    p = F.positions_get(symbol="XAUUSD")[0]
    reg(f"[{o.id}] stop no servidor = entrada efetiva − 2×ATR14 (conferido)", abs(p.sl - round(o.stop, 2)) <= 0.011 and any(e["tipo"] == "validacao" and e["payload"]["ok"] for e in evs(S)), f"sl servidor {p.sl} × bancada {o.stop:.2f}")
    for _ in range(5): S.ciclo()
    reg(f"[{o.id}] uma avaliação por barra concluída (ciclos repetidos não reavaliam)", sum(e["tipo"] == "informacao" for e in evs(S)) == 1 and len(F.X["envios"]) <= 2, f"informacao {sum(e['tipo'] == 'informacao' for e in evs(S))}; envios {len(F.X['envios'])}")
    # reinício: mesmo estado → nada reenviado; estado apagado → recuperado do servidor pelo magic, com stop
    n_env = len(F.X["envios"]); S2 = RX.Romp(F, CFG({"modo": "lote_fixo", "valor": 0.01}), pasta, "simulado"); S2.est["ultima_barra"] = None; S2.ciclo()
    reg(f"[{o.id}] reinício na mesma barra não duplica a ordem", len(F.X["envios"]) == n_env and len(F.positions_get(symbol="XAUUSD")) == 1, f"envios antes {n_env}, depois {len(F.X['envios'])}; posições {len(F.positions_get(symbol='XAUUSD'))}")
    os.remove(os.path.join(pasta, "estado_romp.json")); S3 = RX.Romp(F, CFG({"modo": "lote_fixo", "valor": 0.01}), pasta, "simulado"); S3.reconciliar(int(fim.value))
    reg(f"[{o.id}] recuperação da posição e do stop pelo magic após perder o estado", S3.est["posicao"] and S3.est["posicao"]["ticket"] == p.ticket and abs(S3.est["posicao"]["stop"] - p.sl) < 1e-9, f"ticket {S3.est['posicao'] and S3.est['posicao']['ticket']}; stop {S3.est['posicao'] and S3.est['posicao']['stop']}")
    S3.est["posicao"]["barra_sinal_fim"] = int(fim.value); S3.est["posicao"]["stop_inicial"] = p.sl; S3.est["ultima_barra"] = int((fim - pd.Timedelta(minutes=15)).value); S3.salvar()
    # desconexão: nada avaliado
    F.X["desconectado"] = True; ne = len(F.X["envios"]); S3.ciclo(); F.X["desconectado"] = False
    reg(f"[{o.id}] terminal desconectado: impedimento registrado, nenhuma ordem", len(F.X["envios"]) == ne and any(e["tipo"] == "impedimento" and "sem conexão" in e["payload"]["motivo"] for e in evs(S3)), "ok")
    # acompanhar minuto a minuto até a saída
    k = 0
    while S3.est["posicao"] is not None and k < 60 * 24 * 7: F.avancar(1); S3.ciclo(); k += 1
    rs = [e for e in evs(S3) if e["tipo"] == "resultado"]
    tsai = pd.Timestamp(o.t_sai); px = rs[0]["payload"]["preco_saida"] if rs else None
    reg(f"[{o.id}] saída igual à bancada (motivo e preço)", rs and ((o.motivo_saida == "stop de proteção") == ("stop" in rs[0]["payload"]["motivo_saida"])) and abs(px - o.saida) < 0.011,
        f"executor: {rs[0]['payload']['motivo_saida'] if rs else None} a {px} × bancada: {o.motivo_saida} a {o.saida:.2f} ({tsai})")
    nentr = sum(e["tipo"] == "ordem" and e["payload"].get("pedido", {}).get("action") == F.TRADE_ACTION_DEAL and not e["payload"]["pedido"].get("position") for e in evs(S3))
    reg(f"[{o.id}] correspondência sinal × ordem (1 sinal → 1 ordem de entrada)", nentr == 1, f"ordens de entrada {nentr}")
    reg(f"[{o.id}] outros bots/posições não tocados", all(r.get("magic") == 380380001 for r in F.X["envios"]), "todas as ordens com o magic da experiência")

# stop não confirmado → encerra
o = ALVOS[1]; fim = pd.Timestamp(o.barra_sinal) + pd.Timedelta(minutes=15); F.configurar(DADOS, fim + pd.Timedelta(seconds=20), common=os.path.join(TMP, "c"))
orig = F.order_send
def falha_sltp(req):
    """corretora SIMULADA que abre a posição SEM o stop pedido e recusa o SLTP."""
    if req["action"] == F.TRADE_ACTION_SLTP: F.X["envios"].append(dict(req)); return F.Res(10016, 0, 0, 0, 0, 0, 0, "stops inválidos (simulado)", 0)
    r = orig(req)
    if not req.get("position"):
        for t, p in list(F.X["pos"].items()): F.X["pos"][t] = p._replace(sl=0.0)
    return r
F.order_send = falha_sltp; RX_S = RX.Romp(F, CFG({"modo": "lote_fixo", "valor": 0.01}), os.path.join(TMP, "semstop"), "simulado"); RX_S.ciclo(); F.order_send = orig
reg("stop não aceito pelo servidor → posição encerrada na hora (não fica desprotegida)", not F.positions_get(symbol="XAUUSD") and any(e["tipo"] == "resultado" and "stop não confirmado" in e["payload"]["motivo_saida"] for e in evs(RX_S)), "posição fechada com motivo 'falha operacional: stop não confirmado no servidor'")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES, "nota": "terminal SIMULADO; lote 0,01 só de teste"}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
