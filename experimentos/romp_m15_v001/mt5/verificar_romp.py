"""SÓ LEITURA: confere conta DEMO, símbolo, especificações (ponto, tick size/value, contrato, volumes, stops level, modo de preenchimento, swaps,
comissão não disponível pela API → ver deals reais), histórico M15 (≥ 3000 barras para o ATR de Wilder convergir) e posições com o magic.
Uso: python verificar_romp.py"""
import os, json, sys
import MetaTrader5 as mt5
AQUI = os.path.dirname(os.path.abspath(__file__)); cfg = json.load(open(os.path.join(AQUI, "config_romp.json"), encoding="utf-8"))
if not mt5.initialize(path=cfg.get("terminal_caminho") or None): sys.exit(f"MT5 não inicializou: {mt5.last_error()}")
acc = mt5.account_info(); si = mt5.symbol_info(cfg["simbolo"]); r = mt5.copy_rates_from_pos(cfg["simbolo"], mt5.TIMEFRAME_M15, 1, 3000)
out = {"conta": None if acc is None else {"login": acc.login, "servidor": acc.server, "demo": acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO, "moeda": acc.currency, "margem": acc.margin_mode},
       "simbolo": None if si is None else {k: getattr(si, k) for k in ("name", "point", "digits", "trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min", "volume_step", "volume_max",
                                                                          "trade_stops_level", "filling_mode", "swap_long", "swap_short", "swap_rollover3days", "currency_profit")},
       "barras_M15": 0 if r is None else len(r), "posicoes_com_magic": [p._asdict() for p in (mt5.positions_get(symbol=cfg["simbolo"]) or ()) if p.magic == cfg["magic"]],
       "dimensionamento": cfg.get("dimensionamento")}
ok = bool(out["conta"] and out["conta"]["demo"] and out["simbolo"] and out["barras_M15"] >= 3000)
out["resultado"] = "VERIFICADO (somente leitura)" if ok else "FALHA — ver campos acima"
json.dump(out, open(os.path.join(AQUI, "verificacao_romp.json"), "w"), indent=1, default=str, ensure_ascii=False); print(json.dumps(out, indent=1, default=str, ensure_ascii=False)); mt5.shutdown()
