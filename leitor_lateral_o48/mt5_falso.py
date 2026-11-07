"""Terminal MT5 SIMULADO para os testes do leitor (ORDEM 032). Serve candles dos CSVs exportados do MT5 até um relógio simulado.
NÃO é o MetaTrader5. Conta e especificações aqui são SIMULADAS (marcadas). Qualquer tentativa de ordem é registrada em CHAMADAS_PROIBIDAS."""
import os, glob, collections
import numpy as np, pandas as pd
TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 1, 5, 15, 30, 16385, 16388, 16408
DUR = {1: 1, 5: 5, 15: 15, 30: 30, 16385: 60, 16388: 240, 16408: 1440}; ARQ = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 16385: "H1", 16388: "H4", 16408: "Daily"}
ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_CONTEST, ACCOUNT_TRADE_MODE_REAL = 0, 1, 2
CHAMADAS_PROIBIDAS = []; _S = {"pasta": None, "agora": None, "modo": 0, "dados": {}, "common": None, "simbolos_ausentes": set()}
Conta = collections.namedtuple("Conta", "login server company trade_mode currency equity balance")
Simb = collections.namedtuple("Simb", "name point digits trade_tick_size trade_tick_value volume_min volume_step volume_max spread")
Tick = collections.namedtuple("Tick", "time bid ask")
Term = collections.namedtuple("Term", "commondata_path name")
def configurar(pasta, agora, modo=0, common=None):
    _S.update(pasta=pasta, agora=pd.Timestamp(agora), modo=modo, common=common or os.path.join(os.path.dirname(os.path.abspath(__file__)), "_common_simulado"))
def avancar(minutos): _S["agora"] = _S["agora"] + pd.Timedelta(minutes=minutos)
def _tab(sym, tf):
    k = (sym, tf)
    if k not in _S["dados"]:
        f = sorted(glob.glob(os.path.join(_S["pasta"], f"{sym}_{ARQ[tf]}_*.csv")))[0]; d = pd.read_csv(f, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
        d["t"] = pd.to_datetime(d["date"] + " " + (d["time"] if "time" in d else "00:00:00"), format="%Y.%m.%d %H:%M:%S"); _S["dados"][k] = d
    return _S["dados"][k]
def initialize(*a, **k): return True
def shutdown(): return True
def last_error(): return (0, "simulado")
def account_info(): return Conta(99000001, "ICMarketsSC-Demo (SIMULADO)", "terminal simulado de teste", _S["modo"], "USD", 10000.0, 10000.0)
def symbol_info(s):
    if s in _S["simbolos_ausentes"]: return None
    tv = {"BTCUSD": 0.01, "XAUUSD": 1.0}.get(s, 1.0)                       # SIMULADO: valor do tick por lote (não é dado real da corretora)
    return Simb(s, 0.01, 2, 0.01, tv, 0.01, 0.01, 100.0, 0)
def symbol_info_tick(s):
    d = _tab(s, 1); x = d[d.t <= _S["agora"]].iloc[-1]; return Tick(int(_S["agora"].timestamp()), x.open, x.open + x.spread * 0.01)
def terminal_info(): os.makedirs(_S["common"], exist_ok=True); return Term(_S["common"], "simulado")
def copy_rates_from_pos(s, tf, start, count):
    d = _tab(s, tf); now = _S["agora"]; dur = pd.Timedelta(minutes=DUR[tf])
    vis = d[d.t <= now]                                                     # barras já iniciadas
    if not len(vis): return None
    form = vis.t.iloc[-1] + dur > now                                       # a última ainda está em formação?
    rows = vis.copy()
    if form:                                                                 # barra em formação: só a abertura é conhecida no início
        i = rows.index[-1]; rows.loc[i, ["high", "low", "close"]] = rows.loc[i, "open"]
    rows = rows.iloc[::-1]                                                  # posição 0 = mais recente
    if not form: rows = pd.concat([rows.iloc[:0], rows])                    # sem barra em formação: posição 0 já é fechada
    sel = rows.iloc[start:start + count].iloc[::-1]
    out = np.zeros(len(sel), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])
    out["time"] = (sel.t.values.astype("datetime64[s]").astype("int64")); out["open"], out["high"], out["low"], out["close"] = sel.open, sel.high, sel.low, sel.close
    out["tick_volume"] = sel.tickvol; out["spread"] = sel.spread; return out
def copy_rates_range(s, tf, de, ate):
    """O36: barras com abertura em [de, ate] já FECHADAS no relógio simulado (como o terminal devolve o histórico)."""
    d = _tab(s, tf); dur = pd.Timedelta(minutes=DUR[tf]); de = pd.Timestamp(de).tz_localize(None) if pd.Timestamp(de).tzinfo else pd.Timestamp(de)
    ate = pd.Timestamp(ate).tz_localize(None) if pd.Timestamp(ate).tzinfo else pd.Timestamp(ate)
    sel = d[(d.t >= de) & (d.t <= ate) & (d.t + dur <= _S["agora"])]
    out = np.zeros(len(sel), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])
    out["time"] = (sel.t.values.astype("datetime64[s]").astype("int64")); out["open"], out["high"], out["low"], out["close"] = sel.open, sel.high, sel.low, sel.close
    out["tick_volume"] = sel.tickvol; out["spread"] = sel.spread; return out
def order_send(*a, **k): CHAMADAS_PROIBIDAS.append(("order_send", a, k)); raise RuntimeError("PROIBIDO: order_send chamado")
def order_check(*a, **k): CHAMADAS_PROIBIDAS.append(("order_check", a, k)); raise RuntimeError("PROIBIDO: order_check chamado")
