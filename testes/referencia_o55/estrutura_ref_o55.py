"""estrutura-ref-1 (ORDEM 055) — REIMPLEMENTAÇÕES DE REFERÊNCIA (a partir da documentação pública do MQL5 CodeBase; o .mq5 não foi baixado)
para comparar com os pivôs que a BabyMachine já tem (memória O39, fractal estrito 2+2). Só leitura de barras FECHADAS; nada envia ordens.

A) fractal_n (estilo "Market Structure SMC", CodeBase 74575: InpSwingN barras de cada lado, rompimentos confirmados no FECHAMENTO):
   topo em k se high[k] > high das N anteriores e das N seguintes; confirmado no fechamento de k+N.
B) pullback (estilo "Market Structure from Pullback Swings", CodeBase 78245): um topo vira swing quando o preço negocia de volta
   abaixo da MÍNIMA da vela que fez o topo (pavio, padrão do indicador); swings alternam topo/fundo; só barras fechadas.
Rótulos HH/HL/LH/LL e BOS/CHoCH no fechamento além do último swing confirmado (convenção dos dois indicadores)."""
import numpy as np


def fractal_n(H, L, n=2):
    out = []
    for k in range(n, len(H) - n):
        if all(H[k] > H[k - j] for j in range(1, n + 1)) and all(H[k] > H[k + j] for j in range(1, n + 1)): out.append(("topo", k, float(H[k]), k + n))
        if all(L[k] < L[k - j] for j in range(1, n + 1)) and all(L[k] < L[k + j] for j in range(1, n + 1)): out.append(("fundo", k, float(L[k]), k + n))
    return sorted(out, key=lambda x: (x[3], x[1]))


def pullback(H, L, inicio="topo"):
    """swings alternados; topo confirmado quando uma barra posterior tem mínima < mínima da barra do topo (fundo: máxima > máxima)."""
    out = []; proc = inicio; k_ext = 0
    for i in range(1, len(H)):
        if proc == "topo":
            if H[i] >= H[k_ext]: k_ext = i; continue
            if L[i] < L[k_ext]: out.append(("topo", k_ext, float(H[k_ext]), i)); proc = "fundo"; k_ext = i
        else:
            if L[i] <= L[k_ext]: k_ext = i; continue
            if H[i] > H[k_ext]: out.append(("fundo", k_ext, float(L[k_ext]), i)); proc = "topo"; k_ext = i
    return out


def rotular(piv):
    """HH/LH para topos, HL/LL para fundos (comparando com o swing anterior do mesmo tipo)."""
    ult = {}; out = []
    for tp, k, x, c in piv:
        r = None
        if tp in ult: r = ("HH" if x > ult[tp] else "LH") if tp == "topo" else ("HL" if x > ult[tp] else "LL")
        ult[tp] = x; out.append((tp, k, x, c, r))
    return out


def bos_choch(piv, C):
    """tendência pelo último rompimento; CHoCH = fechamento além do último swing CONTRA a tendência; BOS = a favor."""
    ev = []; tend = 0; ult_t = ult_f = None; j = 0; piv = sorted(piv, key=lambda x: x[3])
    for i in range(len(C)):
        while j < len(piv) and piv[j][3] <= i:
            tp, k, x, c = piv[j][:4]
            if tp == "topo": ult_t = (k, x)
            else: ult_f = (k, x)
            j += 1
        if ult_t and C[i] > ult_t[1]:
            ev.append(("CHoCH alta" if tend < 0 else "BOS alta", i, ult_t[1])); tend = 1; ult_t = None
        elif ult_f and C[i] < ult_f[1]:
            ev.append(("CHoCH baixa" if tend > 0 else "BOS baixa", i, ult_f[1])); tend = -1; ult_f = None
    return ev
