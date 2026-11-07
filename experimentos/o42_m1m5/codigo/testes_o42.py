"""ORDEM 042 — disponibilidade dos dados e regras M1/M5 (leitura-m1m5-0.1). Uso: python testes_o42.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrategia_o39 as ST, leitura_o42 as LQ
RES = []
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
T0 = pd.Timestamp("2026-01-05 00:00")


def construir(barras15, m1_custom=None):
    """M15 a partir das M1 (M1 padrão: abre o, 2ª M1 máxima, 3ª mínima, última fecha c). m1_custom[i] = lista de 15 (o,h,l,c) substitui as M1 da barra i."""
    rows = []
    for i, (o, h, l, c) in enumerate(barras15):
        tt = T0 + pd.Timedelta(minutes=15 * i)
        if m1_custom and i in m1_custom:
            for k, (a, b, d, e) in enumerate(m1_custom[i]): rows.append((tt + pd.Timedelta(minutes=k), a, b, d, e))
            continue
        for k in range(15):
            ts = tt + pd.Timedelta(minutes=k)
            if k == 1: rows.append((ts, o, h, o, o))
            elif k == 2: rows.append((ts, o, o, l, o))
            elif k == 14: rows.append((ts, o, max(o, c), min(o, c), c))
            else: rows.append((ts, o, o, o, o))
    m1 = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]); m1["spread"] = 0
    g = m1.groupby(m1.t.dt.floor("15min")).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).reset_index().rename(columns={"t": "t"}); g["spread"] = 0
    return g[["t", "o", "h", "l", "c", "spread"]], m1


base = [(100.5, 101, 100, 100.5)] * 40 + [(100.5, 100.6, 99.6, 99.8)]                   # barra 40 = sinal de venda de média (sem nível): gatilho 99,59 na barra 41
desc = [(99.8, 99.8, 99.7, 99.7), (99.7, 99.7, 99.6, 99.6), (99.6, 99.6, 99.5, 99.5)] + [(99.5 - 0.1 * k, 99.5 - 0.1 * k, 99.4 - 0.1 * k, 99.4 - 0.1 * k) for k in range(12)]
reb = [(99.8, 99.85, 99.62, 99.82), (99.82, 99.82, 99.55, 99.7), (99.7, 99.9, 99.65, 99.85), (99.85, 99.95, 99.8, 99.9)] + [(99.9, 99.95, 99.85, 99.9)] * 11   # M1 de rejeição ANTES da superação
fim = [(99.9, 99.95, 99.85, 99.9)] * 6
# 1) M5 só completas; leitura só com M1 fechadas
m15, m1 = construir(base + [(99.8, 99.8, 98.3, 98.3)] + fim, {41: desc}); L = LQ.M1M5(m1)
t = int((T0 + pd.Timedelta(minutes=15 * 41 + 7)).value)
reg("M5 fechadas no instante: só as completas (às 10:22 a última fechada termina às 10:20)", pd.Timestamp(int(L.t5_fim[L.m5_fechadas(t) - 1])) == T0 + pd.Timedelta(minutes=15 * 41 + 5), f"última M5 fechada termina em {pd.Timestamp(int(L.t5_fim[L.m5_fechadas(t) - 1]))}")
k = int(np.searchsorted(L.t1, t)) - 1; a1 = L.leitura(k, -1, t)
m1p = m1.copy(); m1p.loc[m1p.t >= pd.Timestamp(t) - pd.Timedelta(minutes=1) + pd.Timedelta(minutes=1), ["o", "h", "l", "c"]] = 50.0; Lp = LQ.M1M5(m1p)
reg("a leitura no instante não muda se a M1 em formação e o futuro mudarem (só M1 fechadas)", json.dumps(a1, sort_keys=True) == json.dumps(Lp.leitura(k, -1, t), sort_keys=True), f"marcas {a1['m1_marcas_15'][-5:]} · M5 {[x['fim'] for x in a1['m5_3']]}")
# 2) entrada confirmada no instante da superação (queda contínua) × referência
r0 = LQ.ReplayM1("XAUUSD", m15, m1, "Ref"); r0.rodar(i0=2); rE = LQ.ReplayM1("XAUUSD", m15, m1, "E", entrada=True); rE.rodar(i0=2)
p0 = (r0.ops + [r0.pos])[0] if (r0.ops or r0.pos) else None; pE = (rE.ops + [rE.pos])[0] if (rE.ops or rE.pos) else None
eE = [r for r in rE.reg if r["decisao"] == "entrada"]
reg("superação com continuidade M1/M5: entra no instante, no mesmo preço da referência", p0 and pE and pE["t_ent"] == p0["t_ent"] and abs(pE["entrada"] - p0["entrada"]) < 1e-9 and eE[0]["confirmacao_m1m5"].startswith("confirmada no instante"),
    f"referência {pd.Timestamp(p0['t_ent']) if p0 else None} a {p0 and p0['entrada']}; E {pd.Timestamp(pE['t_ent']) if pE else None} ({eE[0]['confirmacao_m1m5'] if eE else None})")
# 3) superação com rejeição e retomada para dentro: E não entra; gatilho expira sem confirmação tardia
m15b, m1b = construir(base + [(99.8, 99.95, 99.55, 99.9)] + fim, {41: reb})
r0b = LQ.ReplayM1("XAUUSD", m15b, m1b, "Ref"); r0b.rodar(i0=2); rEb = LQ.ReplayM1("XAUUSD", m15b, m1b, "E", entrada=True); rEb.rodar(i0=2)
dec = [r["decisao"] for r in rEb.reg]
reg("superação sem continuidade (rejeição/pressão contrária): E registra, não entra e expira no fim da barra válida; a referência entra",
    (r0b.ops or r0b.pos) and not (rEb.ops or rEb.pos) and "superacao_sem_continuidade" in dec and dec[-1] == "gatilho_expirado",
    f"referência entrou: {bool(r0b.ops or r0b.pos)}; E: {dec}")
# 4) confirmação DEPOIS da superação: entra na abertura da M1 seguinte à confirmação, dentro da barra válida
late = [(99.8, 99.8, 99.55, 99.75), (99.75, 99.78, 99.74, 99.76), (99.76, 99.77, 99.6, 99.62), (99.62, 99.62, 99.5, 99.5), (99.5, 99.5, 99.4, 99.41), (99.41, 99.41, 99.3, 99.3)] + [(99.3, 99.3, 99.2, 99.2)] * 9
b40 = [(100.5 - 0.06 * k, 100.5 - 0.06 * k, 100.44 - 0.06 * k, 100.44 - 0.06 * k) for k in range(10)] + [(99.9, 99.9, 99.85, 99.85), (99.85, 99.85, 99.7, 99.7), (99.7, 99.7, 99.6, 99.62), (99.62, 99.72, 99.62, 99.7), (99.7, 99.8, 99.7, 99.8)]   # termina com pressão contrária (2 M1 de alta)
m15c, m1c = construir(base + [(99.8, 99.8, 99.2, 99.2)] + fim, {40: b40, 41: late}); rEc = LQ.ReplayM1("XAUUSD", m15c, m1c, "E", entrada=True); rEc.rodar(i0=2)
pc = (rEc.ops + [rEc.pos])[0] if (rEc.ops or rEc.pos) else None; ec = [r for r in rEc.reg if r["decisao"] == "entrada"]
reg("confirmação depois da superação: entrada no 1º preço disponível (abertura da M1 seguinte), ainda dentro da barra válida",
    pc and ec and ec[0]["confirmacao_m1m5"].startswith("confirmada depois") and m15c.t.iloc[41] < pd.Timestamp(pc["t_ent"]) < m15c.t.iloc[41] + pd.Timedelta(minutes=15) and pc["entrada"] == float(m1c.o[m1c.t == pd.Timestamp(pc["t_ent"])].iloc[0]),
    f"superação em {m15c.t.iloc[41] + pd.Timedelta(minutes=0)} (mín 99,55 ≤ 99,59); entrada {pd.Timestamp(pc['t_ent']) if pc else None} a {pc and pc['entrada']}")
# 5) saída: alerta sem confirmação M15 mantém; alerta + M15 além da máxima da barra de referência corta; stop independente
pull = [(98.3, 98.4, 98.3, 98.4), (98.4, 98.5, 98.4, 98.5), (98.5, 98.6, 98.5, 98.6), (98.6, 98.7, 98.6, 98.7), (98.7, 98.8, 98.7, 98.8), (98.8, 99.2, 98.8, 99.2), (99.2, 99.6, 99.2, 99.6), (99.6, 99.9, 99.6, 99.9)] + [(99.5, 99.5, 99.4, 99.4)] * 7   # recuo forte e lento (M5 vira) que para abaixo da barra de referência
m15d, m1d = construir(base + [(99.8, 99.8, 98.3, 98.3)] + [(98.3, 99.9, 98.3, 99.4)] + fim, {41: desc, 42: pull})
rSd = LQ.ReplayM1("XAUUSD", m15d, m1d, "S", saida=True); rSd.rodar(i0=2); dd = [r["decisao"] for r in rSd.reg]
reg("alerta M1/M5 sem confirmação do M15 (fechamento abaixo da máxima da barra de referência 100,6): NÃO corta; registra pullback que respeita o M15",
    "alerta_reversao_m1m5" in dd and "pullback_respeita_m15" in dd and "corte_reversao_m15" not in dd, f"decisões: {[d for d in dd if d not in ('gatilho_armado',)]}")
rev = [(98.3, 99.0, 98.3, 99.0), (99.0, 99.6, 99.0, 99.6), (99.6, 100.2, 99.6, 100.2), (100.2, 100.7, 100.2, 100.7)] + [(100.7, 100.8, 100.6, 100.75)] * 11
m15e, m1e = construir(base + [(99.8, 99.8, 98.3, 98.3)] + [(98.3, 100.8, 98.3, 100.75)] + fim, {41: desc, 42: rev})
rSe = LQ.ReplayM1("XAUUSD", m15e, m1e, "S", saida=True); rSe.rodar(i0=2); pe = (rSe.ops or [None])[0]
reg("alerta M1/M5 + fechamento M15 acima da máxima da barra de referência: corte por reversão confirmada no M15, na 1ª cotação seguinte (ou o stop antes, se tocado)",
    pe and pe["motivo_saida"] in ("corte por reversão confirmada no M15", "stop de proteção"), f"saída: {pe and pe['motivo_saida']} em {pd.Timestamp(pe['t_sai']) if pe else None}; stop {pe and round(pe['stop'], 2)}")
r0e = LQ.ReplayM1("XAUUSD", m15e, m1e, "Ref"); r0e.rodar(i0=2); po = (r0e.ops or [None])[0]
reg("M1/M5 sozinhos nunca cortam: sem a variante S a mesma posição segue a regra de referência (stop/canal)", po and po["motivo_saida"] != "corte por reversão confirmada no M15", f"referência: {po and po['motivo_saida']}")
# 6) reinício reproduz (dados reais, E+S)
m15r = ST.ler("XAUUSD", "M15").iloc[:2500].reset_index(drop=True); m1a = ST.ler("XAUUSD", "M1"); m1r = m1a[m1a.t < m15r.t.iloc[-1] + pd.Timedelta(minutes=15)].reset_index(drop=True)
full = LQ.ReplayM1("XAUUSD", m15r, m1r, "ES", entrada=True, saida=True); full.rodar(); d = tempfile.mkdtemp()
a = LQ.ReplayM1("XAUUSD", m15r, m1r, "ES", entrada=True, saida=True); a.rodar(i1=1500); ST.salvar_estado(a, f"{d}/m.json", f"{d}/e.json", 1500)
b = LQ.ReplayM1("XAUUSD", m15r, m1r, "ES", entrada=True, saida=True); ip = ST.carregar_estado(b, f"{d}/m.json", f"{d}/e.json"); b.rodar(i0=ip)
reg("reinício (memória, espera, gatilho e posição com alertas) reproduz as mesmas decisões", [(r["decisao"], r["barra"]) for r in b.reg] == [(r["decisao"], r["barra"]) for r in full.reg] and len(b.ops) == len(full.ops),
    f"{len(full.reg)} decisões e {len(full.ops)} operações idênticas")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
