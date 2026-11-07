"""Terminal MT5 SIMULADO com TICKS SINTÉTICOS (ORDEM 047). NÃO é o MetaTrader5 e NÃO são ticks reais: cada M1 do CSV vira 4 cotações
(abertura, extremos na ordem convencional — alta: mínima antes da máxima; baixa: máxima antes da mínima — e fechamento), ask = bid + spread.
Serve só para testar o leitor. Qualquer tentativa de ordem é registrada em CHAMADAS_PROIBIDAS."""
import collections, numpy as np, pandas as pd
from mt5_falso import *                                                       # noqa: F401,F403 (candles, conta, símbolos, ordens proibidas)
import mt5_falso as _F
COPY_TICKS_ALL, COPY_TICKS_INFO, COPY_TICKS_TRADE = -1, 1, 2
TermC = collections.namedtuple("TermC", "commondata_path name connected"); TickC = collections.namedtuple("TickC", "time bid ask time_msc")
_T = {"cache": {}, "desconectado": False}
def desconectar(v): _T["desconectado"] = bool(v)
def terminal_info(): t = _F.terminal_info(); return TermC(t.commondata_path, t.name, not _T["desconectado"])
def _ticks(sym):
    if sym not in _T["cache"]:
        d = _F._tab(sym, 1); t0 = d.t.values.astype("datetime64[ms]").astype(np.int64); o, h, l, c, sp = (d[k].values.astype(float) for k in ("open", "high", "low", "close", "spread"))
        up = c >= o; p1 = np.where(up, l, h); p2 = np.where(up, h, l)
        T = np.stack([t0, t0 + 15000, t0 + 30000, t0 + 59000], 1).ravel(); B = np.stack([o, p1, p2, c], 1).ravel(); S = np.repeat(sp * 0.01, 4)
        _T["cache"][sym] = (T, np.round(B, 2), np.round(B + S, 2))
    return _T["cache"][sym]
def copy_ticks_range(sym, de, ate, flags=COPY_TICKS_INFO):
    if _T["desconectado"]: return None
    T, B, A = _ticks(sym); ms = lambda x: int(pd.Timestamp(x).tz_localize(None).value // 10**6) if pd.Timestamp(x).tzinfo else int(pd.Timestamp(x).value // 10**6)
    lim = min(ms(ate), int(_F._S["agora"].value // 10**6)); a, b = np.searchsorted(T, ms(de)), np.searchsorted(T, lim, side="right"); b = max(a, b)
    out = np.zeros(b - a, dtype=[("time", "i8"), ("bid", "f8"), ("ask", "f8"), ("last", "f8"), ("volume", "i8"), ("time_msc", "i8"), ("flags", "i4"), ("volume_real", "f8")])
    out["time_msc"] = T[a:b]; out["time"] = T[a:b] // 1000; out["bid"] = B[a:b]; out["ask"] = A[a:b]; out["flags"] = 6; return out
def symbol_info_tick(sym):
    T, B, A = _ticks(sym); k = int(np.searchsorted(T, int(_F._S["agora"].value // 10**6), side="right")) - 1; return TickC(int(T[k] // 1000), B[k], A[k], int(T[k]))

_R = {}
def copy_rates_from_pos(s, tf, start, count):
    """versão rápida (mesma semântica do mt5_falso: posição 0 = barra em formação; start=1 → só fechadas)."""
    if (s, tf) not in _R:
        d = _F._tab(s, tf); _R[(s, tf)] = (d.t.values.astype("datetime64[s]").astype(np.int64), d)
    ts, d = _R[(s, tf)]; now = int(_F._S["agora"].value // 10**9); dur = _F.DUR[tf] * 60
    n = int(np.searchsorted(ts, now, side="right"))
    if n == 0: return None
    form = ts[n - 1] + dur > now; fim = n - (1 if form else 0) - (start - 1) if start >= 1 else n
    if start == 0 and form: fim = n
    ini = max(0, fim - count); sel = d.iloc[ini:fim]
    out = np.zeros(len(sel), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])
    out["time"] = ts[ini:fim]; out["open"], out["high"], out["low"], out["close"] = sel.open.values, sel.high.values, sel.low.values, sel.close.values; out["tick_volume"] = sel.tickvol.values; out["spread"] = sel.spread.values
    return out
