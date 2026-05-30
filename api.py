from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
from backtesting import Backtest, Strategy
from datetime import datetime, timedelta
import traceback
import os

app = FastAPI(title="BacktestPro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mapa de ativos
ATIVOS = {
    # Forex
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X",
    # Commodities
    "XAU/USD": "GC=F",
    # Crypto
    "BTC/USD": "BTC-USD",
    # Brasil B3
    "IBOVESPA": "^BVSP",
    "USD/BRL":  "USDBRL=X",
}

CATEGORIAS = {
    "Forex":     ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "NZD/USD"],
    "Commodities": ["XAU/USD"],
    "Crypto":    ["BTC/USD"],
    "B3 Brasil": ["IBOVESPA", "USD/BRL"],
}

TIMEFRAMES = {
    "1d":  "1d",
    "4h":  "1h",
    "1h":  "1h",
    "30m": "30m",
    "15m": "15m",
    "5m":  "5m",
}

LIMITE_DIAS = {
    "1d":  1095,
    "4h":  59,
    "1h":  729,
    "30m": 59,
    "15m": 59,
    "5m":  59,
}

class BacktestRequest(BaseModel):
    ativo: str = "EUR/USD"
    periodo: str = "2 anos"
    capital: float = 10000
    comissao: float = 0.0002
    ema_period: int = 20
    timeframe: str = "1d"


def get_datas(periodo: str, timeframe: str = "1d"):
    hoje = datetime.today()
    mapa = {
        "6 meses": hoje - timedelta(days=183),
        "1 ano":   hoje - timedelta(days=365),
        "2 anos":  hoje - timedelta(days=730),
        "3 anos":  hoje - timedelta(days=1095),
    }
    inicio = mapa.get(periodo, hoje - timedelta(days=730))
    limite = LIMITE_DIAS.get(timeframe, 1095)
    inicio_minimo = hoje - timedelta(days=limite)
    if inicio < inicio_minimo:
        inicio = inicio_minimo
    return inicio.strftime("%Y-%m-%d"), hoje.strftime("%Y-%m-%d")


def resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    df = df.resample("4h").agg({
        "Open":   "first",
        "High":   "max",
        "Low":    "min",
        "Close":  "last",
        "Volume": "sum",
    }).dropna()
    return df


class EMAChannel(Strategy):
    ema_period = 20

    def init(self):
        self.ema_high = self.I(
            lambda h: pd.Series(h).ewm(span=self.ema_period, adjust=False).mean().values,
            self.data.High
        )
        self.ema_low = self.I(
            lambda l: pd.Series(l).ewm(span=self.ema_period, adjust=False).mean().values,
            self.data.Low
        )

    def next(self):
        preco = self.data.Close[-1]
        if not self.position:
            if preco > self.ema_high[-1]:
                self.buy()
        else:
            if preco < self.ema_low[-1]:
                self.position.close()


# Serve o frontend (index.html)
@app.get("/")
def root():
    if os.path.exists("index.html"):
        return FileResponse("index.html", media_type="text/html")
    return {
        "status": "BacktestPro API rodando!",
        "versao": "2.1",
        "frontend": "index.html não encontrado",
        "docs": "/docs",
    }


@app.get("/ativos")
def listar_ativos():
    return {"ativos": list(ATIVOS.keys()), "categorias": CATEGORIAS}


@app.get("/timeframes")
def listar_timeframes():
    return {
        "timeframes": list(TIMEFRAMES.keys()),
        "limites_dias": LIMITE_DIAS,
    }


@app.post("/backtest")
def rodar_backtest(req: BacktestRequest):
    try:
        ticker = ATIVOS.get(req.ativo, "EURUSD=X")
        tf = req.timeframe if req.timeframe in TIMEFRAMES else "1d"
        inicio, fim = get_datas(req.periodo, tf)
        yf_interval = TIMEFRAMES[tf]

        print(f"Backtest: {req.ativo} | {req.periodo} | TF: {tf} | EMA: {req.ema_period} | Capital: {req.capital}")

        data = yf.download(ticker, start=inicio, end=fim, interval=yf_interval, progress=False)

        if data.empty:
            return {"erro": f"Sem dados para {req.ativo} no período selecionado"}

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
        data.index = pd.to_datetime(data.index)

        if tf == "4h":
            data = resample_4h(data)

        if len(data) < 50:
            return {"erro": f"Dados insuficientes ({len(data)} candles). Tente um período maior ou timeframe diário."}

        EMAChannel.ema_period = req.ema_period
        bt = Backtest(data, EMAChannel, cash=req.capital, commission=req.comissao)
        r = bt.run()

        equity = r["_equity_curve"]["Equity"].tolist()
        datas  = r["_equity_curve"].index.strftime("%Y-%m-%d %H:%M").tolist()
        step   = max(1, len(equity) // 200)

        trades = []
        if len(r["_trades"]) > 0:
            for _, t in r["_trades"].iterrows():
                trades.append({
                    "entrada": str(t.get("EntryTime", ""))[:16],
                    "saida":   str(t.get("ExitTime",  ""))[:16],
                    "retorno": round(float(t.get("ReturnPct", 0)) * 100, 2),
                    "lucro":   round(float(t.get("PnL", 0)), 2),
                })

        def safe(val):
            try:
                v = float(val)
                return round(v, 2) if v == v else 0.0
            except:
                return 0.0

        return {
            "ativo":          req.ativo,
            "periodo":        req.periodo,
            "timeframe":      tf,
            "ema_period":     req.ema_period,
            "candles":        len(data),
            "retorno":        safe(r["Return [%]"]),
            "retorno_anual":  safe(r["Return (Ann.) [%]"]),
            "win_rate":       safe(r["Win Rate [%]"]),
            "sharpe":         safe(r["Sharpe Ratio"]),
            "max_drawdown":   safe(r["Max. Drawdown [%]"]),
            "total_trades":   int(r["# Trades"]),
            "profit_factor":  safe(r["Profit Factor"]),
            "capital_final":  safe(r["Equity Final [$]"]),
            "equity_curve":   equity[::step],
            "datas_equity":   datas[::step],
            "trades":         trades[-20:],
        }

    except Exception as e:
        return {"erro": str(e), "detalhe": traceback.format_exc()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
