"""ROMP-M15-0.1 — regras da estratégia fixa de rompimento M15 (XAUUSD). Funções puras: as MESMAS na bancada e no executor MT5.
Especificação: ROMP_especificacao_congelada.txt."""
import numpy as np, pandas as pd
VERSAO = "ROMP-M15-0.1"
N_ENT, N_SAI, N_ATR, K_STOP = 20, 10, 14, 2.0


def atr_wilder(h, l, c, n=N_ATR):
    h, l, c = (np.asarray(x, float) for x in (h, l, c)); pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1); a = np.full(len(tr), np.nan)
    if len(tr) >= n:
        a[n - 1] = tr[:n].mean()
        for i in range(n, len(tr)): a[i] = (a[i - 1] * (n - 1) + tr[i]) / n
    return a


def canais(m15):
    """por barra t: limites das N barras ANTERIORES (t excluída). NaN sem histórico suficiente."""
    h = pd.Series(m15.h.values.astype(float)); l = pd.Series(m15.l.values.astype(float))
    return pd.DataFrame({"LS20": h.rolling(N_ENT).max().shift(1).values, "LI20": l.rolling(N_ENT).min().shift(1).values,
                         "LS10": h.rolling(N_SAI).max().shift(1).values, "LI10": l.rolling(N_SAI).min().shift(1).values,
                         "ATR14": atr_wilder(m15.h, m15.l, m15.c)})


def sinal_entrada(c, LS20, LI20):
    """+1 compra, −1 venda, 0 nada (igualdade não rompe; sem limite → 0)."""
    if not (np.isfinite(LS20) and np.isfinite(LI20)): return 0
    return 1 if c > LS20 else (-1 if c < LI20 else 0)


def sinal_saida(lado, c, LS10, LI10):
    if lado > 0: return bool(np.isfinite(LI10) and c < LI10)
    return bool(np.isfinite(LS10) and c > LS10)


def stop_inicial(lado, entrada, atr): return entrada - lado * K_STOP * atr
