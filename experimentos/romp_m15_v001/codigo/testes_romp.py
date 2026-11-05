"""ROMP-M15-0.1 — testes funcionais das regras (A: implementada corretamente) com dados sintéticos de resultado conhecido e com o histórico real.
Uso: python testes_romp.py SAIDA.json"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import romp_m15 as RM, bancada_romp as B
RES = []
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)


def sint(precos15, inicio="2026-01-05 00:00", spread=0):
    """M15 a partir de (o,h,l,c) e M1 coerentes: cada M15 = 15 M1 (1ª M1 abre no 'o', a última fecha no 'c', h/l atingidos na 2ª/3ª M1)."""
    t = pd.date_range(inicio, periods=len(precos15), freq="15min"); m15 = pd.DataFrame(precos15, columns=["o", "h", "l", "c"]); m15["t"] = t; m15["spread"] = spread
    rows = []
    for (o, h, l, c), tt in zip(precos15, t):
        for k in range(15):
            ts = tt + pd.Timedelta(minutes=k)
            if k == 0: rows.append((ts, o, max(o, c if k == 14 else o), min(o, o), o))
            elif k == 1: rows.append((ts, o, h, o if o < h else h, o))
            elif k == 2: rows.append((ts, o, o, l, o))
            elif k == 14: rows.append((ts, o, max(o, c), min(o, c), c))
            else: rows.append((ts, o, o, o, o))
    m1 = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]); m1["spread"] = spread
    return m15[["t", "o", "h", "l", "c", "spread"]], m1


# 1) canal exclui a barra atual; igualdade não rompe
base = [(100, 101, 99, 100)] * 25
m15 = pd.DataFrame(base + [(100, 105, 99.5, 101)], columns=["o", "h", "l", "c"]); K = RM.canais(m15)
reg("canal de entrada exclui a barra t", K.LS20.iloc[-1] == 101 and K.LI20.iloc[-1] == 99, f"LS20 {K.LS20.iloc[-1]} (máxima da própria barra 105 não entra), LI20 {K.LI20.iloc[-1]}")
reg("igualdade com o limite não rompe", RM.sinal_entrada(101.0, 101.0, 99.0) == 0 and RM.sinal_entrada(99.0, 101.0, 99.0) == 0 and RM.sinal_entrada(101.01, 101, 99) == 1 and RM.sinal_entrada(98.99, 101, 99) == -1, "c = LS20 e c = LI20 → 0; estritos → ±1")
reg("sem 20 barras anteriores não há avaliação", np.isnan(RM.canais(m15.iloc[:20]).LS20.iloc[-1]) and RM.sinal_entrada(500, np.nan, np.nan) == 0, "LS20 da 20ª barra = NaN")
reg("saída exclui a barra t e é estrita", RM.sinal_saida(1, 98.99, 101, 99) and not RM.sinal_saida(1, 99, 101, 99) and RM.sinal_saida(-1, 101.01, 101, 99) and not RM.sinal_saida(-1, 101, 101, 99), "compra fecha só com c < mín10; venda só com c > máx10")
a = RM.atr_wilder(np.r_[np.full(14, 2.0), 4.0], np.zeros(15), np.ones(15))
reg("ATR de Wilder (semente média simples, depois (13·ATR+TR)/14)", abs(a[13] - 2.0) < 1e-12 and abs(a[14] - (2.0 * 13 + 4.0) / 14) < 1e-12, f"ATR14 = {a[13]}, depois {a[14]:.6f}")

# 2) cenário completo sintético: rompimento de alta → entrada na M1 seguinte → saída pelo canal de 10 → sem inversão na mesma barra
P = [(100, 101, 99, 100)] * 22 + [(100, 102, 100, 101.5)] + [(101.5, 103, 101.4, 102.5)] * 3 + [(102.5, 102.6, 95, 96)]
m15, m1 = sint(P); ops, dec = B.simular(m15, m1)
o = ops.iloc[0]
reg("entrada na primeira cotação após o fechamento do sinal", o.lado == 1 and o.barra_sinal == str(m15.t.iloc[22]) and pd.Timestamp(o.t_ent) == m15.t.iloc[23] and o.entrada == 101.5,
    f"sinal na barra {o.barra_sinal} (c 101,5 > LS20 101); entrada {pd.Timestamp(o.t_ent)} a {o.entrada}")
reg("stop inicial = entrada − 2×ATR14", abs(o.stop - (o.entrada - 2 * o.atr)) < 1e-9, f"ATR {o.atr:.4f} → stop {o.stop:.4f}")
reg("na barra de queda o STOP executa antes do fechamento (intrabarra)", o.motivo_saida == "stop de proteção" and len(ops) == 1, f"saída: {o.motivo_saida} a {o.saida:.4f}")
# saída por sinal sem stop: queda moderada abaixo do mín10 mas acima do stop
P2 = [(100, 101, 99, 100)] * 22 + [(100, 102, 100, 101.5)] + [(101.5, 101.8, 101.2, 101.6)] * 10 + [(101.6, 101.6, 99.8, 99.9)] + [(99.9, 100.2, 99.7, 100.0)] * 3
m15, m1 = sint(P2); ops2, dec2 = B.simular(m15, m1); o2 = ops2.iloc[0]
reg("saída por sinal executa na 1ª cotação após o fechamento, sem nova entrada na mesma decisão", o2.motivo_saida.startswith("saída por sinal") and pd.Timestamp(o2.t_sai) == m15.t.iloc[34] and len(ops2) == 1,
    f"fechamento 99,9 < mín10 {RM.canais(m15).LI10.iloc[33]:.2f} na barra {m15.t.iloc[33]}; saída {pd.Timestamp(o2.t_sai)} a {o2.saida}; operações {len(ops2)}")
# lacuna: stop executa na abertura pior
P3 = [(100, 101, 99, 100)] * 22 + [(100, 102, 100, 101.5)] + [(101.5, 101.6, 101.4, 101.5)] + [(90, 90.5, 89, 90)]
m15, m1 = sint(P3); ops3, _ = B.simular(m15, m1); o3 = ops3.iloc[0]
reg("lacuna além do stop executa na abertura (não no stop)", o3.motivo_saida == "stop de proteção" and o3.saida == 90, f"stop {o3.stop:.3f}; abertura com lacuna 90 → saída 90")
# sinal com posição aberta é ignorado e registrado
P4 = [(100, 101, 99, 100)] * 22 + [(100, 102, 100, 101.5)] + [(101.5, 103, 101.4, 102.9)] + [(102.9, 104, 102.8, 103.9)] * 2
m15, m1 = sint(P4); ops4, dec4 = B.simular(m15, m1)
reg("uma posição por vez; sinal com posição aberta só é registrado", len(ops4) == 1 and (dec4.motivo == "sinal ignorado: posição desta experiência aberta").sum() >= 1, f"operações {len(ops4)}; sinais ignorados {(dec4.motivo == 'sinal ignorado: posição desta experiência aberta').sum()}")

# 3) histórico real: sem futuro, uma avaliação por barra, sem sobreposição
m15r = B.ler("M15"); m1r = B.ler("M1"); Kf = RM.canais(m15r); rng = np.random.default_rng(7); dif = 0
for i in rng.choice(np.arange(100, len(m15r)), 200):
    Kt = RM.canais(m15r.iloc[:i + 1]); dif = max(dif, float(np.nanmax(np.abs(Kt.iloc[-1].values - Kf.iloc[i].values))))
reg("truncamento: limites e ATR em t não usam barras posteriores", dif < 1e-9, f"dif máx {dif} em 200 barras")
opsr, decr = B.simular(m15r, m1r); f = opsr[~opsr.aberta_no_fim_dos_dados]
sob = int((f.t_ent.values[1:] < f.t_sai.values[:-1]).sum())
reg("sem sobreposição de posições", sob == 0, f"{len(f)} operações; sobreposições {sob}")
dup = decr[decr.decisao == "entrada"].groupby("barra_abertura").size().max()
reg("no máximo uma avaliação de entrada registrada por barra", dup == 1, f"máximo por barra {dup}")
ok_ent = all(pd.Timestamp(r.t_ent) >= pd.Timestamp(r.barra_sinal) + pd.Timedelta(minutes=15) for r in f.itertuples())
reg("toda entrada ocorre depois do fechamento da barra de sinal", ok_ent, "t_ent ≥ abertura do sinal + 15 min em todas")
chk = []
for r in f.sample(min(300, len(f)), random_state=3).itertuples():
    i = int(np.searchsorted(m15r.t.values, np.datetime64(r.barra_sinal))); c = m15r.c.iloc[i]; k = Kf.iloc[i]
    chk.append((c > k.LS20) if r.lado > 0 else (c < k.LI20))
reg("correspondência sinal × operação (recalculado de forma independente)", all(chk), f"{len(chk)} operações conferidas")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
