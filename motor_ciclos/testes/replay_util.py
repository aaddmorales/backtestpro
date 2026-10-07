"""Reprodução cronológica para TESTE: a cada instante T só existem no espelho as barras que o MT5
(falso, determinístico) já tinha FECHADO em T. Nada do futuro entra na pasta daquele instante."""
import os, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.dirname(AQUI); FAKE = os.path.join(AQUI, "fake_mt5")
for p in (FAKE, MOTOR):
    if p not in sys.path:
        sys.path.insert(0, p)
N_BARRAS = {"M1": 3000, "M5": 2000, "M15": 1500, "M30": 1000, "H1": 800, "H4": 400, "Daily": 300}


def espelho_em(pasta, t_utc, ativo="XAUUSD"):
    """Grava o espelho como o MT5 falso o entregaria no instante t_utc (segundos UTC)."""
    import pandas as pd
    os.environ["BT_FAKE_AGORA"] = str(float(t_utc))
    import MetaTrader5 as mt5
    cods = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "Daily": mt5.TIMEFRAME_D1}
    os.makedirs(pasta, exist_ok=True)
    for f in os.listdir(pasta):
        os.remove(os.path.join(pasta, f))
    for tf, cod in cods.items():
        r = mt5.copy_rates_from_pos(ativo, cod, 1, N_BARRAS[tf])            # pos 1 = só FECHADAS em t_utc
        d = pd.DataFrame(r); d["dt"] = pd.to_datetime(d["time"], unit="s")
        out = pd.DataFrame({"<DATE>": d["dt"].dt.strftime("%Y.%m.%d"), "<TIME>": d["dt"].dt.strftime("%H:%M:%S"),
                            "<OPEN>": d["open"], "<HIGH>": d["high"], "<LOW>": d["low"], "<CLOSE>": d["close"],
                            "<TICKVOL>": d["tick_volume"].astype(int), "<VOL>": 0, "<SPREAD>": d["spread"].astype(int)})
        out.to_csv(os.path.join(pasta, f"{ativo}_{tf}_x.csv"), sep="\t", index=False, float_format="%.2f")
    return mt5
