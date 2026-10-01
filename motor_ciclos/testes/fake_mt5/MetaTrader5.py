"""FAKE do pacote MetaTrader5 para TESTE (bancada). NÃO é a corretora.
Barras sintéticas determinísticas no HORÁRIO DO SERVIDOR (UTC + BT_FAKE_OFF),
só barras fechadas a partir de pos. order_send existe para provar que o leitor
o bloqueia."""
import os, time, math, hashlib
import numpy as np

TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30 = 1, 5, 15, 30
TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 16385, 16388, 16408
_SEG = {1: 60, 5: 300, 15: 900, 30: 1800, 16385: 3600, 16388: 14400, 16408: 86400}
OFF = int(os.environ.get("BT_FAKE_OFF", "10800"))
LOGIN = int(os.environ.get("BT_FAKE_LOGIN", "52648209"))
DEMO = os.environ.get("BT_FAKE_REAL", "") == ""
ORDENS = []


class _O:
    def __init__(self, **k): self.__dict__.update(k)


def _agora():
    return float(os.environ.get("BT_FAKE_AGORA") or time.time())


def initialize(path=None, **k):
    return True


def shutdown():
    return True


def last_error():
    return (0, "ok")


def account_info():
    return _O(login=LOGIN, server="ICMarketsSC-Demo", trade_mode=0 if DEMO else 2, balance=10000.0)


def terminal_info():
    return _O(path=os.environ.get("BT_FAKE_TERM", "/fake/term"),
              data_path=os.environ.get("BT_FAKE_DATA", "/fake/data/ABC"), trade_allowed=False)


def symbol_select(s, v=True):
    return True


def symbol_info(s):
    return _O(digits=2, spread=12, point=0.01)


def symbol_info_tick(s):
    return _O(time=int(_agora()) + OFF, bid=2000.0, ask=2000.1)


def barra(tf_seg, t):
    """OHLC determinístico da barra que abre em t (horário do servidor)."""
    base = 2000 + 40 * math.sin(t / 86400.0 * 2 * math.pi / 3) + 15 * math.sin(t / 5400.0)
    r = int(hashlib.sha256(f"{tf_seg}|{t}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    o = round(base, 2)
    c = round(base + (r - 0.5) * 2.0 * (tf_seg / 900) ** 0.5, 2)
    h = round(max(o, c) + r * 0.8 * (tf_seg / 900) ** 0.5, 2)
    l = round(min(o, c) - (1 - r) * 0.8 * (tf_seg / 900) ** 0.5, 2)
    return o, h, l, c


def copy_rates_from_pos(sym, tf, pos, n):
    s = _SEG[tf]
    srv = int(_agora()) + OFF
    aberta = (srv // s) * s
    dt = np.dtype([("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"),
                   ("close", "<f8"), ("tick_volume", "<u8"), ("spread", "<i4"), ("real_volume", "<u8")])
    out = np.zeros(n, dtype=dt)
    for i in range(n):
        t = aberta - (pos + n - 1 - i) * s
        o, h, l, c = barra(s, t)
        out[i] = (t, o, h, l, c, 100, 12, 0)
    return out


def order_send(req):
    ORDENS.append(req)
    raise AssertionError("FAKE: order_send chamado — o leitor NÃO pode enviar ordem")


def order_check(req):
    raise AssertionError("FAKE: order_check chamado")
