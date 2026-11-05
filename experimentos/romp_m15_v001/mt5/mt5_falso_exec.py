"""Terminal MT5 SIMULADO COM NEGOCIAÇÃO para os testes do executor (ORDEM 033). NÃO é o MetaTrader5 nem a corretora.
Candles dos CSVs até um relógio simulado; conta, especificações, margem, comissão e preenchimento SIMULADOS. Stops atingidos pelas M1.
Comportamentos injetáveis: falha da corretora, execução parcial, desconexão, queda logo depois do envio. Posição de "outro bot" para isolamento."""
import collections, itertools
import numpy as np, pandas as pd
from mt5_falso import *                         # candles, conta e relógio do terminal simulado de leitura
import mt5_falso as _B
TRADE_ACTION_DEAL, TRADE_ACTION_SLTP = 1, 6
ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1; POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1
ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2; ORDER_TIME_GTC = 0
TRADE_RETCODE_PLACED, TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL, TRADE_RETCODE_INVALID_STOPS, TRADE_RETCODE_NO_MONEY = 10008, 10009, 10010, 10016, 10019
DEAL_ENTRY_IN, DEAL_ENTRY_OUT, DEAL_ENTRY_INOUT, DEAL_ENTRY_OUT_BY = 0, 1, 2, 3; DEAL_REASON_EXPERT, DEAL_REASON_SL = 3, 4
Conta = collections.namedtuple("Conta", "login server company trade_mode currency equity balance margin_free leverage margin_mode")
ACCOUNT_MARGIN_MODE_RETAIL_NETTING, ACCOUNT_MARGIN_MODE_EXCHANGE, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 0, 1, 2   # O36: modo de margem SIMULADO (padrão hedging)
Simb = collections.namedtuple("Simb", "name point digits trade_tick_size trade_tick_value volume_min volume_step volume_max spread trade_stops_level trade_freeze_level filling_mode trade_mode visible")
Pos = collections.namedtuple("Pos", "ticket time type magic identifier volume price_open sl tp price_current profit symbol comment")
Deal = collections.namedtuple("Deal", "ticket order time type entry magic position_id reason volume price commission swap fee profit symbol comment")
Res = collections.namedtuple("Res", "retcode deal order volume price bid ask comment request_id")
Term = collections.namedtuple("Term", "commondata_path name connected trade_allowed path data_path")
CONTRATO = {"BTCUSD": 1.0, "XAUUSD": 100.0}; COMISSAO_LADO = {"BTCUSD": 0.0, "XAUUSD": -3.5}     # SIMULADOS
X = {"pos": {}, "deals": [], "seq": itertools.count(5000), "proc_ate": None, "falha": None, "parcial": None, "desconectado": False, "cair_apos_envio": False, "envios": [], "equity": 10000.0, "margin_mode": 2}
def configurar(pasta, agora, modo=0, common=None):
    _B.configurar(pasta, agora, modo, common); X.update(pos={}, deals=[], proc_ate=pd.Timestamp(agora), falha=None, parcial=None, desconectado=False, cair_apos_envio=False, envios=[], margin_mode=2)
def account_info():
    return Conta(99000001, "ICMarketsSC-Demo (SIMULADO)", "terminal simulado de teste", _B._S["modo"], "USD", X["equity"], X["equity"], X["equity"] - sum(order_calc_margin(0, p.symbol, p.volume, p.price_open) for p in X["pos"].values()), 100, X["margin_mode"])
def symbol_info(s):
    if s in _B._S["simbolos_ausentes"]: return None
    tv = {"BTCUSD": 0.01, "XAUUSD": 1.0}.get(s, 1.0); return Simb(s, 0.01, 2, 0.01, tv, 0.01, 0.01, 100.0, 0, 0, 0, 1, 4, True)
def terminal_info():
    t = _B.terminal_info(); return Term(t.commondata_path, "simulado", not X["desconectado"], True, "C:/simulado/terminal64.exe", "C:/simulado/dados")
def _m1(s): return _B._tab(s, 1)
def _bid(s, t=None):
    d = _m1(s); t = t or _B._S["agora"]; x = d[d.t <= t].iloc[-1]; return float(x.open), float(x.open + x.spread * 0.01)
def symbol_info_tick(s):
    b, a = _bid(s); return _B.Tick(int(_B._S["agora"].timestamp()), b, a)
def order_calc_margin(tipo, s, vol, preco): return float(vol * preco * CONTRATO[s] / 100)
def _deal(s, tipo, entry, magic, pid, reason, vol, px, comment):
    d = Deal(next(X["seq"]), next(X["seq"]), int(_B._S["agora"].timestamp()), tipo, entry, magic, pid, reason, vol, px, COMISSAO_LADO[s] * vol, 0.0, 0.0, 0.0, s, comment); X["deals"].append(d); return d
def _fechar(p, px, reason, quando=None):
    lado = 1 if p.type == POSITION_TYPE_BUY else -1; lucro = (px - p.price_open) * lado * p.volume * CONTRATO[p.symbol]
    d = Deal(next(X["seq"]), next(X["seq"]), int((quando or _B._S["agora"]).timestamp()), 1 - p.type, DEAL_ENTRY_OUT, p.magic, p.ticket, reason, p.volume, px, COMISSAO_LADO[p.symbol] * p.volume, 0.0, 0.0, lucro, p.symbol, "sl" if reason == DEAL_REASON_SL else "fecha")
    X["deals"].append(d); X["equity"] += lucro + d.commission; X["pos"].pop(p.ticket, None)
def _processar():
    """stops atingidos nas M1 já fechadas desde a última verificação (bid na compra; ask na venda; lacuna executa na abertura)."""
    agora = _B._S["agora"]; ini = X["proc_ate"] or agora
    for p in list(X["pos"].values()):
        if not p.sl: continue
        d = _m1(p.symbol); seg = d[(d.t + pd.Timedelta(minutes=1) > ini) & (d.t + pd.Timedelta(minutes=1) > pd.Timestamp(p.time, unit="s")) & (d.t + pd.Timedelta(minutes=1) <= agora)]   # ROMP: M1 FECHADAS em (ini, agora] (antes pulava a M1 quando o relógio não estava no minuto cheio)
        for r in seg.itertuples():
            if p.type == POSITION_TYPE_BUY and r.low <= p.sl: _fechar(p, min(r.open, p.sl), DEAL_REASON_SL, r.t); break
            if p.type == POSITION_TYPE_SELL and r.high + r.spread * 0.01 >= p.sl: _fechar(p, max(r.open + r.spread * 0.01, p.sl), DEAL_REASON_SL, r.t); break
    X["proc_ate"] = agora
def avancar(minutos): _B.avancar(minutos); _processar()
def positions_get(symbol=None):
    _processar(); return tuple(p for p in X["pos"].values() if symbol is None or p.symbol == symbol)
def history_deals_get(*a, position=None, **k):
    _processar(); return tuple(d for d in X["deals"] if position is None or d.position_id == position)
def abrir_outro_bot(s, tipo, vol, sl, magic=123456):
    b, a = _bid(s); px = a if tipo == ORDER_TYPE_BUY else b; t = next(X["seq"])
    X["pos"][t] = Pos(t, int(_B._S["agora"].timestamp()), tipo, magic, t, vol, px, sl, 0.0, px, 0.0, s, "outro bot"); return t
def order_send(req):
    X["envios"].append(dict(req)); _processar()
    if X["desconectado"]: return None
    if X["falha"]: rc = X["falha"]; X["falha"] = None; return Res(rc, 0, 0, 0.0, 0.0, 0.0, 0.0, "falha simulada da corretora", 0)
    s = req["symbol"]; b, a = _bid(s)
    if req["action"] == TRADE_ACTION_SLTP:
        p = X["pos"].get(req["position"])
        if p is None: return Res(10013, 0, 0, 0, 0, b, a, "posição inexistente", 0)
        X["pos"][p.ticket] = p._replace(sl=req["sl"]); return Res(TRADE_RETCODE_DONE, 0, next(X["seq"]), p.volume, 0.0, b, a, "SL modificado", 0)
    if "position" in req and req.get("position"):
        p = X["pos"].get(req["position"])
        if p is None: return Res(10013, 0, 0, 0, 0, b, a, "posição inexistente", 0)
        px = b if p.type == POSITION_TYPE_BUY else a; _fechar(p, px, DEAL_REASON_EXPERT); return Res(TRADE_RETCODE_DONE, X["deals"][-1].ticket, next(X["seq"]), p.volume, px, b, a, "fechado", 0)
    px = a if req["type"] == ORDER_TYPE_BUY else b
    if (req["type"] == ORDER_TYPE_BUY and req["sl"] >= px) or (req["type"] == ORDER_TYPE_SELL and req["sl"] <= px): return Res(TRADE_RETCODE_INVALID_STOPS, 0, 0, 0, 0, b, a, "stops inválidos", 0)
    vol = req["volume"]; rc = TRADE_RETCODE_DONE
    if X["parcial"]: vol = round(max(0.01, np.floor(vol * X["parcial"] * 100) / 100), 2); rc = TRADE_RETCODE_DONE_PARTIAL; X["parcial"] = None
    t = next(X["seq"]); X["pos"][t] = Pos(t, int(_B._S["agora"].timestamp()), POSITION_TYPE_BUY if req["type"] == ORDER_TYPE_BUY else POSITION_TYPE_SELL, req["magic"], t, vol, px, req["sl"], 0.0, px, 0.0, s, req["comment"])
    d = _deal(s, req["type"], DEAL_ENTRY_IN, req["magic"], t, DEAL_REASON_EXPERT, vol, px, req["comment"])
    if X["cair_apos_envio"]: X["cair_apos_envio"] = False; raise RuntimeError("QUEDA SIMULADA logo após o envio (antes de registrar a resposta)")
    return Res(rc, d.ticket, d.order, vol, px, b, a, "executado (simulado)", 0)
