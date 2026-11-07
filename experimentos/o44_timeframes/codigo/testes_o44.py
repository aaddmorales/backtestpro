"""ORDEM 044 — testes do motor em M30 e H1 (dados sintéticos): mesma regra da R0 da O43 no próprio TF; M1 só executa. Uso: python testes_o44.py SAIDA.json"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formacao_o44 as FO, estrategia_o39 as ST
RES = []; T0 = pd.Timestamp("2026-01-05 00:00")
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)


def caminho(o, h, l, c, n):
    pts = np.interp(np.arange(n), [0, 1, 2, n - 1], [o, h, l, c]); out, prev = [], o
    for k in range(n):
        cc = round(float(pts[k]), 2); oo = round(float(prev), 2); out.append((oo, max(oo, cc), min(oo, cc), cc)); prev = cc
    out[1] = (out[1][0], round(h, 2), out[1][2], out[1][3]); out[2] = (out[2][0], out[2][1], round(l, 2), out[2][3]); return out


def m1f(prev, closes, lows=None, highs=None):
    out = []
    for k, cc in enumerate(closes):
        oo = prev; h, l = max(oo, cc), min(oo, cc)
        if lows and k in lows: l = lows[k]
        if highs and k in highs: h = highs[k]
        out.append((round(oo, 2), round(h, 2), round(l, 2), round(cc, 2))); prev = cc
    return out


def construir(barras, tf):
    rows = []
    for i, b in enumerate(barras):
        m = caminho(*b, tf) if isinstance(b, tuple) else b
        assert len(m) == tf
        for k, x in enumerate(m): rows.append((T0 + pd.Timedelta(minutes=tf * i + k), *x))
    m1 = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]); m1["spread"] = 2
    g = m1.t.dt.floor(f"{tf}min"); d = m1.assign(g=g).groupby("g").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), spread=("spread", "last")).reset_index().rename(columns={"g": "t"})
    return d[["t", "o", "h", "l", "c", "spread"]], m1


def base(tf, b51=None, b52=None, n=58, b53=None):
    B = []
    for i in range(n):
        if i == 40: B.append((100.0, 100.5, 99.0, 99.8))
        elif i == 48: B.append((99.8, 100.2, 98.9, 99.6))
        elif i == 50: B.append((99.5, 99.8, 98.5, 98.7))
        elif i == 51 and b51 is not None: B.append(b51)
        elif i == 52 and b52 is not None: B.append(b52)
        elif i == 53 and b53 is not None: B.append(b53)
        elif i > 50: B.append((99.0, 99.3, 98.8, 99.1))
        else: B.append((100.0, 100.5, 99.5, 100.0) if i % 2 else (100.0, 100.45, 99.55, 100.05))
    return construir(B, tf)


def motor(tf, d, m1): M = FO.Motor("XAUUSD", d, m1, tf_min=tf); M.rodar(i0=20); return M


def queda(tf, k_sup, lows=None, highs=None, depois=98.40, antes=None):
    c = (antes or list(np.linspace(98.68, 98.53, k_sup))) + [98.45] + [depois] * (tf - k_sup - 1); return m1f(98.70, c, lows, highs)


for tf in (30, 60):
    nome = "M30" if tf == 30 else "H1"; t51 = T0 + pd.Timedelta(minutes=tf * 51)
    d, m1 = base(tf, m1f(98.70, [98.6] * 20 + [98.52] + [98.55] * (tf - 21), lows={20: 98.50})); M = motor(tf, d, m1); s = M.sinais[0]
    reg(f"{nome}: igualar o extremo da barra de rompimento é toque, não abre", s["resultado_gatilho"] == "toque sem superação" and not M.ops["R0"] and M.pos["R0"] is None, f"resultado={s['resultado_gatilho']}")
    d, m1 = base(tf, queda(tf, 20, lows={20: 98.49})); M = motor(tf, d, m1); s = M.sinais[0]; p = M.pos["R0"] or (M.ops["R0"][0] if M.ops["R0"] else None)
    reg(f"{nome}: 1 tick além abre no minuto 20 da barra {nome} seguinte", s["resultado_gatilho"] == "superou" and pd.Timestamp(s["t_superacao"]) == t51 + pd.Timedelta(minutes=20) and p and abs(p["entrada"] - 98.49) < 1e-9,
        f"τ={s['t_superacao']} entrada={p and p['entrada']}")
    atr = float(M.ATR[50]); reg(f"{nome}: stop = 2 × ATR14 do próprio TF na barra de rompimento", p and abs(abs(p["entrada"] - p["stop"]) - 2 * atr) < 1e-9, f"ATR {nome}={atr:.4f}; risco={abs(p['entrada'] - p['stop']):.4f}")
    d, m1 = base(tf, m1f(98.70, [98.72] * tf), b52=m1f(98.72, [98.3] + [97.5] * (tf - 1))); M = motor(tf, d, m1); s = M.sinais[0]
    reg(f"{nome}: sem superação na barra seguinte expira; a queda na barra depois não abre", s["resultado_gatilho"] == "não alcançou" and not M.ops["R0"] and M.pos["R0"] is None, "0 entradas")
    # M1 fora da decisão: mesma OHLC do TF, ordem das M1 antes de τ invertida (subindo × caindo) → mesma decisão e preço
    up = m1f(98.70, list(np.linspace(98.72, 98.80, 20)) + [98.45] + [98.40] * (tf - 21), lows={20: 98.49}); dn = m1f(98.70, list(np.linspace(98.68, 98.53, 20)) + [98.45] + [98.40] * (tf - 21), lows={20: 98.49})
    A = motor(tf, *base(tf, up)); B = motor(tf, *base(tf, dn)); pa = A.pos["R0"] or A.ops["R0"][0]; pb = B.pos["R0"] or B.ops["R0"][0]
    reg(f"{nome}: M1 antes da superação (subindo × caindo) não muda a decisão nem o preço (sem filtro M1/M5)", (pa["t_ent"], pa["entrada"]) == (pb["t_ent"], pb["entrada"]), f"τ={pd.Timestamp(pa['t_ent'])} preço={pa['entrada']}")
    # retorno: volta acima do extremo no minuto 30 após τ → fora dos 15 min; dentro da barra só se a barra ainda não terminou
    k = 5; closes = [98.6] * k + [98.45] + [98.40] * 20 + [98.60] + [98.40] * (tf - k - 22); d, m1 = base(tf, m1f(98.70, closes, lows={k: 98.30})); M = motor(tf, d, m1); s = M.sinais[0]
    esp_barra = 22.0 if tf - k - 1 >= 21 else None
    reg(f"{nome}: retorno 22 min após τ conta 'até o fim da barra' mas não '15 min'", s["retorno_15min_min"] is None and s["retorno_fim_barra_min"] == esp_barra, f"15min={s['retorno_15min_min']} fim_barra={s['retorno_fim_barra_min']}")
    # saída: fechamento do TF de volta ao canal → executa na 1ª M1 da barra seguinte
    d, m1 = base(tf, queda(tf, 20, lows={20: 98.49}), b52=(98.4, 100.2, 98.3, 100.0)); M = motor(tf, d, m1); o = M.ops["R0"][0] if M.ops["R0"] else None
    reg(f"{nome}: saída pelo canal EMA20 do próprio TF na abertura da barra seguinte", o is not None and o["motivo_saida"].startswith("saída por sinal") and pd.Timestamp(int(o["t_sai"])) == T0 + pd.Timedelta(minutes=tf * 53),
        f"saída {o and pd.Timestamp(int(o['t_sai']))} a {o and round(o['saida'], 2)}")
    # ambíguo: stop na M1 da entrada
    d, m1 = base(tf, queda(tf, 20, lows={20: 98.49}, highs={20: 103.0})); M = motor(tf, d, m1); o = M.ops["R0"][0] if M.ops["R0"] else None
    reg(f"{nome}: stop na mesma M1 da entrada é marcado ambíguo", o is not None and o["ambiguo"] and o["stop_na_m1_entrada"], f"saída no stop {o and round(o['stop'], 2)}")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "versao": FO.VERSAO, "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
