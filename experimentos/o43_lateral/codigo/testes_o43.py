"""ORDEM 043 — testes da formação, do gatilho e da leitura M1/M5 no instante (dados sintéticos) e do reinício (dados reais). Uso: python testes_o43.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formacao_o43 as FO, estrategia_o39 as ST
RES = []; T0 = pd.Timestamp("2026-01-05 00:00")
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)


def caminho(o, h, l, c):
    """15 M1 de uma barra: abre em o, máxima no minuto 1, mínima no minuto 2, fecha em c no minuto 14 (interpolação)."""
    pts = np.interp(np.arange(15), [0, 1, 2, 14], [o, h, l, c]) if h - max(o, c) >= l and False else np.interp(np.arange(15), [0, 1, 2, 14], [o, h, l, c])
    out, prev = [], o
    for k in range(15):
        cc = round(float(pts[k]), 2); oo = round(float(prev), 2); out.append((oo, max(oo, cc), min(oo, cc), cc)); prev = cc
    out[1] = (out[1][0], round(h, 2), out[1][2], out[1][3]); out[2] = (out[2][0], out[2][1], round(l, 2), out[2][3]); return out


def m1_de_fechamentos(prev, closes, lows=None, highs=None):
    out = []
    for k, cc in enumerate(closes):
        oo = prev; h = max(oo, cc); l = min(oo, cc)
        if lows and k in lows: l = lows[k]
        if highs and k in highs: h = highs[k]
        out.append((round(oo, 2), round(h, 2), round(l, 2), round(cc, 2))); prev = cc
    return out


def construir(barras):
    """barras: lista de (o,h,l,c) ou lista de 15 tuplas M1. Devolve (m15, m1) com M15 agregadas das M1; spread 2 pontos."""
    rows = []
    for i, b in enumerate(barras):
        m = caminho(*b) if isinstance(b, tuple) else b
        for k, x in enumerate(m): rows.append((T0 + pd.Timedelta(minutes=15 * i + k), *x))
    m1 = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]); m1["spread"] = 2
    g = m1.t.dt.floor("15min"); m15 = m1.assign(g=g).groupby("g").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), spread=("spread", "last")).reset_index().rename(columns={"g": "t"})
    return m15[["t", "o", "h", "l", "c", "spread"]], m1


def base(b51=None, quebra=(99.5, 99.8, 98.5, 98.7), tentativa=True, b52=None, n=56):
    """lateral 100 ± 0,5; pivô de fundo em 40 (99,00); tentativa tipo 1 em 48 (pavio 98,90, fecha 99,60); rompimento em 50 (fecha 98,70, mínima 98,50)."""
    B = []
    for i in range(n):
        if i == 40: B.append((100.0, 100.5, 99.0, 99.8))
        elif i == 48 and tentativa: B.append((99.8, 100.2, 98.9, 99.6))
        elif i == 50: B.append(quebra)
        elif i == 51 and b51 is not None: B.append(b51)
        elif i == 52 and b52 is not None: B.append(b52)
        elif i > 50: B.append((99.0, 99.3, 98.8, 99.1))
        else: B.append((100.0, 100.5, 99.5, 100.0) if i % 2 else (100.0, 100.45, 99.55, 100.05))
    return construir(B)


def motor(m15, m1, at="XAUUSD"): M = FO.Motor(at, m15, m1); M.rodar(i0=20); return M
def sinal(M): return M.sinais[0] if M.sinais else None


# fechamentos M1 da barra 51 (abre em 98,70 = fechamento da 50)
QUEDA = [98.68, 98.64, 98.60, 98.56, 98.53] + [98.45] + [98.40] * 9                      # superação (98,45 ≤ 98,49) no minuto 5
def b51_queda(lows=None, highs=None, closes=QUEDA): return m1_de_fechamentos(98.70, closes, lows, highs)

# 1 · igualar não abre
m15, m1 = base(b51_queda(closes=[98.68, 98.64, 98.60, 98.56, 98.53, 98.52] + [98.55] * 9, lows={5: 98.50}))
M = motor(m15, m1); s = sinal(M)
reg("igualar o extremo (mínima M1 = 98,50) é toque: não abre", s is not None and s["resultado_gatilho"] == "toque sem superação" and all(len(M.ops[r]) == 0 and M.pos[r] is None for r in FO.REGRAS),
    f"resultado={s and s['resultado_gatilho']}; operações={[len(M.ops[r]) for r in FO.REGRAS]}")
# 2 · 1 tick abre (R0) no minuto da superação, ao preço do gatilho
m15, m1 = base(b51_queda(closes=[98.68, 98.64, 98.60, 98.56, 98.53, 98.52] + [98.55] * 9, lows={5: 98.49}))
M = motor(m15, m1); s = sinal(M); e = [r for r in M.reg if r["decisao"] == "entrada_virtual" and r["regra"] == "R0"]
reg("superar por 1 tick (98,49) abre em τ ao preço do gatilho", s["resultado_gatilho"] == "superou" and s["t_superacao"] == "2026-01-05 12:50:00" and len(e) == 1 and e[0]["preco"] == 98.49,
    f"τ={s.get('t_superacao')}; entrada={e and e[0]['preco']}")
# 3 · só a barra b+1; nada depois da expiração
m15, m1 = base(m1_de_fechamentos(98.70, [98.72] * 15), b52=m1_de_fechamentos(98.72, [98.6, 98.3, 98.0] + [97.5] * 12))
M = motor(m15, m1); s = sinal(M)
reg("barra seguinte sem superação: expira; a queda na barra 52 não abre", s["resultado_gatilho"] == "não alcançou" and sum(len(M.ops[r]) for r in FO.REGRAS) == 0 and all(p is None for p in M.pos.values())
    and any(r["decisao"] == "gatilho_expirado" for r in M.reg), f"resultado={s['resultado_gatilho']}; posições=0; entradas=0")
# 4 · sem reativação: superação com M1 contrária; confirmação forte depois não abre
m15, m1 = base(b51_queda(closes=[98.75, 98.80, 98.85, 98.86, 98.45, 98.30, 98.10, 97.90, 97.70, 97.50, 97.40, 97.30, 97.20, 97.10, 97.00], lows={4: 98.40}))
M = motor(m15, m1); s = sinal(M); L = s["leitura"]
reg("superação com M1 contrária: R1/R2 descartam; confirmação posterior não reativa", L["m1_estado"] == "CONTRARIA" and s["R1_decisao"] == "descarta" and s["R2_decisao"] == "descarta"
    and not M.ops["R1"] and M.pos["R1"] is None and not M.ops["R2"] and M.pos["R2"] is None and (M.pos["R0"] is not None or M.ops["R0"]),
    f"M1={L['m1_estado']} M5={L['m5_estado']}; R1 entradas=0, R2 entradas=0; R0 entrou")
# 5 · M1 e M5 confirmam → R1 e R2 entram
m15, m1 = base(b51_queda())
M = motor(m15, m1); s = sinal(M); L = s["leitura"]
reg("M1 avançando e M5 fechada a favor: R0, R1 e R2 entram no mesmo instante e preço", L["m1_estado"] == "CONFIRMA" and L["m5_estado"] == "CONFIRMA" and all(s[f"{r}_decisao"] == "entra" for r in FO.REGRAS)
    and len({(o["t_ent"], o["entrada"]) for r in FO.REGRAS for o in M.ops[r] + ([M.pos[r]] if M.pos[r] else [])}) == 1, f"M1={L['m1_estado']} M5={L['m5_estado']} τ={s['t_superacao']}")
# 6 · M5 neutra não confirma (R1 descarta; R2 aceita porque não é contrária)
m15, m1 = base(b51_queda(closes=[98.80, 98.78, 98.75, 98.72, 98.70, 98.45] + [98.40] * 9))
M = motor(m15, m1); s = sinal(M); L = s["leitura"]
reg("M5 neutra (corpo nulo) não é confirmação: R1 descarta, R2 entra", L["m1_estado"] == "CONFIRMA" and L["m5_estado"] == "NEUTRO" and s["R1_decisao"] == "descarta" and s["R2_decisao"] == "entra",
    f"M1={L['m1_estado']} M5={L['m5_estado']} (o5=c5); R1={s['R1_decisao']} R2={s['R2_decisao']}")
# 7 · leitura só com fechadas: perturbar a M1 da superação e o futuro não muda a leitura nem as decisões
m15a, m1a = base(b51_queda()); A = sinal(motor(m15a, m1a))
alt = QUEDA[:5] + [98.20] + [99.50, 100.4, 100.6] + [101.0] * 6
m15b, m1b = base(b51_queda(closes=alt, highs={5: 98.70}), b52=m1_de_fechamentos(101.0, [102.0] * 15)); B = sinal(motor(m15b, m1b))
reg("leitura no instante usa só M1/M5 fechadas (M1 em formação e futuro alterados)", A["leitura"] == B["leitura"] and all(A[f"{r}_decisao"] == B[f"{r}_decisao"] for r in FO.REGRAS) and A["t_superacao"] == B["t_superacao"],
    f"leitura idêntica; decisões {[A[f'{r}_decisao'] for r in FO.REGRAS]}")
# 8 · formação
m15, m1 = base(b51_queda(), tentativa=False); reg("sem tentativa prévia não há formação", not motor(m15, m1).sinais, "0 sinais")
m15, m1 = base(b51_queda(), quebra=(99.5, 99.8, 98.5, 99.0)); M = motor(m15, m1)
reg("fechar igual ao fundo (99,00) não é rompimento", not any(x["barra_rompimento"] == "2026-01-05 12:30:00" for x in M.sinais), f"barra 50 sem sinal; sinais posteriores (a barra 50 vira tentativa tipo 1): {len(M.sinais)}")
B = []
for i in range(56):
    if i == 40: B.append((100.0, 100.5, 99.0, 99.8))
    elif i == 46: B.append((99.8, 100.0, 98.95, 98.97))                                   # tipo 2: fecha abaixo
    elif i == 47: B.append((98.97, 99.7, 98.95, 99.5))                                   # não supera a mínima (98,95) e volta ≥ fundo
    elif i == 50: B.append((99.5, 99.8, 98.5, 98.7))
    elif i == 51: B.append(b51_queda())
    elif i > 50: B.append((99.0, 99.3, 98.8, 99.1))
    else: B.append((100.0, 100.5, 99.5, 100.0) if i % 2 else (100.0, 100.45, 99.55, 100.05))
M = motor(*construir(B)); s = sinal(M)
reg("tentativa tipo 2 (fechamento abaixo não confirmado) forma o sinal", s is not None and s["n_tent_tipo2"] == 1 and s["referencia"] == 99.0, f"tentativas={s and [(t['barra'][-8:], t['tipo']) for t in s['tentativas']]}")
B[47] = (98.97, 99.7, 98.94, 99.5); M = motor(*construir(B))
reg("fechamento abaixo CONFIRMADO pela barra seguinte (−1 tick) invalida a lateralização", not M.sinais, "0 sinais")
# compra = espelho
esp = lambda b: (200 - b[0], 200 - b[2], 200 - b[1], 200 - b[3]) if isinstance(b, tuple) else [(round(200 - o, 2), round(200 - l, 2), round(200 - h, 2), round(200 - c, 2)) for o, h, l, c in b]
B2 = []
for i in range(56):
    if i == 40: B2.append(esp((100.0, 100.5, 99.0, 99.8)))
    elif i == 48: B2.append(esp((99.8, 100.2, 98.9, 99.6)))
    elif i == 50: B2.append(esp((99.5, 99.8, 98.5, 98.7)))
    elif i == 51: B2.append(esp(b51_queda()))
    elif i > 50: B2.append(esp((99.0, 99.3, 98.8, 99.1)))
    else: B2.append(esp((100.0, 100.5, 99.5, 100.0) if i % 2 else (100.0, 100.45, 99.55, 100.05)))
M = motor(*construir(B2)); s = sinal(M)
reg("compra (espelho): resistência 101,00, rompe acima, gatilho 101,51", s is not None and s["lado"] == 1 and s["referencia"] == 101.0 and round(s["T"], 2) == 101.51 and s["leitura"]["m1_estado"] == "CONFIRMA"
    and s["leitura"]["m5_estado"] == "CONFIRMA" and s["R1_decisao"] == "entra", f"lado={s and s['lado']} ref={s and s['referencia']} T={s and round(s['T'], 2)}")
m15, m1 = base(b51_queda(closes=[98.72] * 15), b52=None, quebra=(99.5, 99.8, 98.5, 98.7))
B3 = [m for m in [None]]                                                                 # mesmo fundo não gera 2º sinal
M = motor(m15, m1); n1 = len(M.sinais)
reg("um sinal por fundo de referência", n1 == 1, f"{n1} sinal em 56 barras (fechamentos seguintes abaixo do fundo não rearmam)")
# 9 · ambíguos
m15, m1 = base(b51_queda(closes=QUEDA[:5] + [98.45] + [98.40] * 9, lows={5: 98.30}) [:5] + [(98.40, 98.50, 98.30, 98.45)] + b51_queda()[6:])
M = motor(m15, m1); s = sinal(M); o = (M.ops["R0"] + [M.pos["R0"]])[0]
reg("M1 da superação abre além do gatilho (lacuna): entra na abertura e marca ambíguo", s["lacuna_na_abertura"] and abs(o["entrada"] - 98.40) < 1e-9, f"entrada={o['entrada']}; lacuna={s['lacuna_na_abertura']}")
m15, m1 = base(b51_queda(highs={5: 100.9}))
M = motor(m15, m1); o = M.ops["R0"][0] if M.ops["R0"] else None
reg("stop alcançado na mesma M1 da entrada: sai no stop e marca ambíguo", o is not None and o["motivo_saida"] == "stop de proteção" and o["ambiguo"] and o["stop_na_m1_entrada"], f"saída={o and round(o['saida'], 2)} stop={o and round(o['stop'], 2)}")
# 10 · isolada = carteira quando não há sobreposição
m15, m1 = base(b51_queda(), b52=(98.4, 100.2, 98.3, 100.0)); M = motor(m15, m1); s = sinal(M); iso = M.isolada(s); op = M.ops["R0"][0] if M.ops["R0"] else None
reg("simulação isolada do sinal = operação da carteira (mesma gestão)", op is not None and iso is not None and (iso["t_sai"], round(iso["R"], 9)) == (op["t_sai"], round(op["R"], 9)), f"R={op and round(op['R'], 3)}; saída {op and op['motivo_saida']}")
# 11 · reinício em dados reais (mesma janela): estado salvo no meio = contínuo
at = "XAUUSD"; m15a = ST.ler(at, "M15"); m1a = ST.ler(at, "M1"); m15 = m15a.iloc[20000:23000].reset_index(drop=True); m1 = m1a[(m1a.t >= m15.t.iloc[0]) & (m1a.t < m15.t.iloc[-1] + pd.Timedelta(minutes=15))].reset_index(drop=True)
A = FO.Motor(at, m15, m1); A.rodar(i0=25); d = tempfile.mkdtemp(); B = FO.Motor(at, m15, m1); B.rodar(i0=25, i1=1600); FO.salvar_estado(B, f"{d}/m.json", f"{d}/e.json")
C = FO.Motor(at, m15, m1); FO.carregar_estado(C, f"{d}/m.json", f"{d}/e.json"); C.rodar(i0=1600)
chave = lambda r: (r["decisao"], r["barra"], r.get("regra"), r.get("sinal"))
okr = [chave(r) for r in A.reg] == [chave(r) for r in B.reg + C.reg] and all([(o["id"], round(o["R"], 9)) for o in A.ops[r]] == [(o["id"], round(o["R"], 9)) for o in B.ops[r] + C.ops[r]] for r in FO.REGRAS)
reg("reinício com estado salvo reproduz o replay contínuo", okr, f"{len(A.reg)} decisões; operações {[len(A.ops[r]) for r in FO.REGRAS]}")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "versao": FO.VERSAO, "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
