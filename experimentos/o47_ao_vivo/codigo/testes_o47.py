"""ORDEM 047 — testes do motor por tick e do leitor ao vivo no terminal SIMULADO (ticks sintéticos a partir das M1; NÃO são ticks reais).
(1) unidade: toque × 1 tick, cotação além do gatilho, stop no ask, saída na 1ª cotação após o fechamento, expiração, bloqueio, início congelado;
(2) integração: o leitor (6 instâncias em 2 processos) reproduz as decisões do replay O44 no mesmo período; (3) reinício sem duplicar; (4) nenhuma ordem.
Uso: python testes_o47.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
PKG = "/home/claude/r005/lm047/mt5"; sys.path.insert(0, PKG); sys.path.insert(0, "/home/claude/r005/lm044/codigo")
import ao_vivo_o47 as AV
_argv = sys.argv; sys.argv = sys.argv[:1]; import testes_o44 as T44; sys.argv = _argv   # (o módulo da O44 roda os próprios testes ao importar; sem gravar arquivo)
os.chdir(PKG)
import mt5_falso_ticks as F, bt_ao_vivo_o47 as BT, formacao_o44 as FO, estrategia_o39 as ST
RES = []; DADOS = "/home/claude/r005/lm014/dados/csv_limpo"
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)
T44.RES.clear()


def inst_ate(barras=50, tf=15):
    d, m1 = T44.base(tf); I = AV.Instancia("XAUUSD", "M15" if tf == 15 else "M30"); I.ativo_desde_ms = 0
    for b in range(20, barras + 1): I.fecha_barra(d.iloc[:b + 1].reset_index(drop=True))
    t51 = int(d.t.iloc[51].value // 10**6); return I, d, t51


ms = 60_000
I, d, t0 = inst_ate(); I.tick(t0 + 5 * ms, 98.50, 98.70); I.fecha_barra(d.iloc[:52].reset_index(drop=True))
reg("tocar o extremo (bid = 98,50) não abre; expira no fechamento da barra seguinte", I.pos is None and I.cont["toques"] == 1 and I.pend is None, f"toques={I.cont['toques']}")
I, d, t0 = inst_ate(); I.tick(t0 + 5 * ms, 98.49, 98.69)
reg("1 tick além (bid 98,49): venda entra no bid observado", I.pos is not None and I.pos["entrada"] == 98.49 and not I.sinais[-1]["lacuna_alem_do_gatilho"], f"entrada {I.pos and I.pos['entrada']}")
I, d, t0 = inst_ate(); I.tick(t0 + 2 * ms, 98.62, 98.82); I.tick(t0 + 3 * ms, 98.30, 98.50)
reg("1ª cotação já além do gatilho (98,30): entra em 98,30, não no teórico 98,49, e marca", I.pos["entrada"] == 98.30 and I.sinais[-1]["lacuna_alem_do_gatilho"], f"entrada {I.pos['entrada']} (gatilho 98,49)")
st = I.pos["stop"]; I.tick(t0 + 4 * ms, st - 0.25, st - 0.05); ainda = I.pos is not None; I.tick(t0 + 5 * ms, st - 0.10, st + 0.10)
reg("stop da venda pelo ASK observado (ask ≥ stop), saída ao preço desse ask", ainda and I.pos is None and I.ops[-1]["motivo_saida"] == "stop de proteção" and abs(I.ops[-1]["saida"] - (st + 0.10)) < 1e-9,
    f"stop {st:.2f}; ask {st - 0.05:.2f} não sai; ask {st + 0.10:.2f} sai")
d2, _ = T44.base(15, b52=(98.4, 100.2, 98.3, 100.0)); I = AV.Instancia("XAUUSD", "M15"); I.ativo_desde_ms = 0
for b in range(20, 51): I.fecha_barra(d2.iloc[:b + 1].reset_index(drop=True))
t51 = int(d2.t.iloc[51].value // 10**6); I.tick(t51 + 5 * ms, 98.49, 98.69); I.fecha_barra(d2.iloc[:52].reset_index(drop=True)); I.fecha_barra(d2.iloc[:53].reset_index(drop=True))
fim52 = int(d2.t.iloc[53].value // 10**6); I.tick(fim52 - 1000, 100.0, 100.2); antes = I.pos is not None; I.tick(fim52 + 700, 100.05, 100.27)
reg("saída pelo canal na 1ª cotação após o fechamento (venda paga o ask)", antes and I.ops and I.ops[-1]["motivo_saida"].startswith("saída por sinal") and I.ops[-1]["saida"] == 100.27, f"saída {I.ops and I.ops[-1]['saida']} às +0,7 s do fechamento")
I, d, t0 = inst_ate(); I.ativo_desde_ms = int(d.t.iloc[51].value // 10**6); I.usados.clear(); I.pend = None
I2 = AV.Instancia("XAUUSD", "M15"); I2.ativo_desde_ms = int(d.t.iloc[51].value // 10**6)
for b in range(20, 51): I2.fecha_barra(d.iloc[:b + 1].reset_index(drop=True))
reg("início congelado: formação anterior ao início não arma gatilho", I2.pend is None and I2.cont["formacoes"] == 0, "0 gatilhos antes do início")
# ── integração no terminal simulado: leitor × replay O44 ──
INI = pd.Timestamp("2026-03-02"); DIAS = 12; tmp = tempfile.mkdtemp(prefix="o47_"); CFG = dict(BT.EX.CFG_PADRAO, plataforma_url="")
def correr(at, pasta, de, minutos, L=None):
    if L is None: F.configurar(DADOS, de, common=os.path.join(tmp, "c")); L = BT.Leitor(F, CFG, at, pasta, "simulado", str(INI))
    for _ in range(minutos): L.ciclo(); F.avancar(1)
    return L
t_ini = time.time(); res_int = {}
for at in ("XAUUSD", "BTCUSD"):
    L = correr(at, os.path.join(tmp, f"cont_{at}"), INI - pd.Timedelta(hours=2), DIAS * 1440 + 120); ev = [json.loads(l) for l in open(L.D.f)]
    vivo_ent = {(e["payload"]["instancia"].split("-")[1], e["payload"]["id"].split("-", 2)[2]): e["payload"] for e in ev if e["tipo"] == "decisao" and e["payload"]["tipo"] == "entrada_virtual"}
    vivo_res = {(e["payload"]["tf"], e["payload"]["id"].split("-", 2)[2]): e["payload"] for e in ev if e["tipo"] == "resultado"}
    vivo_arm = {(e["payload"]["instancia"].split("-")[1], e["payload"]["sinal"].split("-", 2)[2]) for e in ev if e["tipo"] == "decisao" and e["payload"]["tipo"] == "gatilho_armado"}
    m1 = ST.ler(at, "M1"); fim = INI + pd.Timedelta(days=DIAS); res_int[at] = {}
    for tf, mn in (("M15", 15), ("M30", 30), ("H1", 60)):
        dd = ST.ler(at, tf); M = FO.Motor(at, dd, m1, tf_min=mn); i0 = int(np.searchsorted(dd.t.values, np.datetime64(INI))); i1 = int(np.searchsorted((dd.t + pd.Timedelta(minutes=mn)).values, np.datetime64(fim), side="right"))
        M.rodar(i0=i0, i1=i1)
        arm = {(tf, s["id"].split("-", 1)[1]) for s in M.sinais}; arm_v = {k for k in vivo_arm if k[0] == tf}
        ops = {(tf, o["id"].split("-", 2)[2]): o for o in M.ops["R0"] + ([M.pos["R0"]] if M.pos["R0"] is not None else [])}; ent_v = {k: v for k, v in vivo_ent.items() if k[0] == tf}
        min_ok = sum(1 for k, o in ops.items() if k in ent_v and pd.Timestamp(ent_v[k]["t"]).floor("min") == pd.Timestamp(int(o["t_ent"])))
        sai_ok = sum(1 for k, o in ops.items() if k in vivo_res and "t_sai" in o and pd.Timestamp(vivo_res[k]["t_sai_ms"], unit="ms").floor("min") == pd.Timestamp(int(o["t_sai"])) and vivo_res[k]["motivo_saida"] == o["motivo_saida"])
        sai_dif = [{"id": k[1], "entrada_vivo": round(ent_v[k]["preco"], 2), "entrada_teorica_replay": round(o["entrada"], 2), "saida_vivo": vivo_res[k]["motivo_saida"], "saida_replay": o["motivo_saida"]}
                   for k, o in ops.items() if k in vivo_res and "t_sai" in o and not (pd.Timestamp(vivo_res[k]["t_sai_ms"], unit="ms").floor("min") == pd.Timestamp(int(o["t_sai"])) and vivo_res[k]["motivo_saida"] == o["motivo_saida"])]
        dpx = [ent_v[k]["preco"] - o["entrada"] for k, o in ops.items() if k in ent_v]
        res_int[at][tf] = {"gatilhos_replay": len(arm), "gatilhos_vivo": len([k for k in arm_v]), "mesmos_gatilhos": arm == arm_v, "operacoes_replay": len(ops), "entradas_vivo": len(ent_v), "mesmas_entradas": set(ops) == set(ent_v),
                           "minuto_de_entrada_igual": min_ok, "saida_mesmo_minuto_e_motivo": sai_ok, "saidas_diferentes": sai_dif, "fechadas_vivo": sum(1 for k in vivo_res if k[0] == tf),
                           "dif_preco_entrada_mediana": round(float(np.median(dpx)), 4) if dpx else None, "dif_preco_entrada_max_abs": round(float(np.max(np.abs(dpx))), 4) if dpx else None}
    if at == "XAUUSD": LA, evA = L, ev
print(json.dumps(res_int, ensure_ascii=False, indent=1), round(time.time() - t_ini), "s")
ok_i = all(v["mesmos_gatilhos"] and v["mesmas_entradas"] and v["minuto_de_entrada_igual"] == v["operacoes_replay"] for a in res_int.values() for v in a.values())
reg("leitor ao vivo (terminal simulado) = replay O44: mesmos gatilhos, mesmas entradas, mesmo minuto de entrada (6 instâncias, 12 dias)", ok_i,
    "; ".join(f"{a} {tf}: {v['gatilhos_vivo']} gatilhos, {v['entradas_vivo']} entradas" for a, x in res_int.items() for tf, v in x.items()))
tot = sum(v["operacoes_replay"] for a in res_int.values() for v in a.values()); sai = sum(v["saida_mesmo_minuto_e_motivo"] for a in res_int.values() for v in a.values())
difs = [x for a in res_int.values() for v in a.values() for x in v["saidas_diferentes"]]; fech = sum(v["fechadas_vivo"] for a in res_int.values() for v in a.values())
reg("saídas no mesmo minuto e motivo do replay; diferenças só onde a cotação observada no gatilho ficou além do preço teórico (stop recalculado da entrada real)",
    sai + len(difs) == fech and all(abs(x["entrada_vivo"] - x["entrada_teorica_replay"]) > 0 for x in difs), f"{sai} de {fech} fechadas iguais; diferentes: {difs}")
# reinício no meio
P = os.path.join(tmp, "rein"); n1 = 5 * 1440 + 437; B1 = correr("XAUUSD", P, INI - pd.Timedelta(hours=2), n1); F.configurar(DADOS, INI - pd.Timedelta(hours=2) + pd.Timedelta(minutes=n1), common=os.path.join(tmp, "c"))
B2 = correr("XAUUSD", P, None, DIAS * 1440 + 120 - n1, BT.Leitor(F, CFG, "XAUUSD", P, "simulado", str(INI)))
evB = [json.loads(l) for l in open(B2.D.f)]; kA = sorted(e["chave"] for e in evA if e["tipo"] in ("decisao", "resultado", "diagnostico")); kB = [e["chave"] for e in evB if e["tipo"] in ("decisao", "resultado", "diagnostico")]
reg("reinício no meio (ticks buscados no histórico do terminal): mesmos eventos, sem duplicar", sorted(kB) == kA and len(set(kB)) == len(kB), f"{len(kB)} eventos (contínuo {len(kA)})")
# desconexão
P = os.path.join(tmp, "desc"); F.configurar(DADOS, INI + pd.Timedelta(hours=10), common=os.path.join(tmp, "c")); Ld = BT.Leitor(F, CFG, "XAUUSD", P, "simulado", str(INI))
for _ in range(30): Ld.ciclo(); F.avancar(1)
F.desconectar(True)
for _ in range(10): Ld.ciclo(); F.avancar(1)
F.desconectar(False)
for _ in range(10): Ld.ciclo(); F.avancar(1)
evD = [json.loads(l) for l in open(Ld.D.f)]; tipos = [e["payload"].get("evento") for e in evD if e["tipo"] == "dados"]
reg("desconexão e reconexão registradas", "desconexão" in tipos and "reconexão" in tipos, str([t for t in tipos if t in ("desconexão", "reconexão")]))
nret = sum(1 for e in evA if e["tipo"] == "diagnostico"); reg("retorno A/B/C (15 min, M1 do terminal) registrado para cada entrada", nret == sum(v["entradas_vivo"] for v in res_int["XAUUSD"].values()), f"{nret} diagnósticos no XAU")
reg("nenhuma ordem enviada", not getattr(F, "CHAMADAS_PROIBIDAS", []), "order_send/order_check nunca chamados")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "versao": AV.VERSAO, "aprovados": ok, "total": len(RES), "testes": RES, "integracao": res_int,
                                 "nota": "terminal SIMULADO com ticks sintéticos derivados das M1 — NÃO é teste ao vivo"}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
