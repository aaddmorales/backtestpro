from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
from backtesting import Backtest, Strategy
import traceback

app = FastAPI(title="BacktestPro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mapa de ativos
ATIVOS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "XAU/USD": "GC=F",
    "BTC/USD": "BTC-USD",
    "AUD/USD": "AUDUSD=X",
}

PERIODOS = {
    "1 ano":  ("2024-01-01", "2025-01-01"),
    "2 anos": ("2023-01-01", "2025-01-01"),
    "3 anos": ("2022-01-01", "2025-01-01"),
}

class BacktestRequest(BaseModel):
    ativo: str = "EUR/USD"
    periodo: str = "2 anos"
    capital: float = 10000
    comissao: float = 0.0002
    ema_period: int = 85

class EMAChannel(Strategy):
    ema_period = 85

    def init(self):
        self.ema_high = self.I(
            lambda h: pd.Series(h).ewm(span=self.ema_period).mean().values,
            self.data.High
        )
        self.ema_low = self.I(
            lambda l: pd.Series(l).ewm(span=self.ema_period).mean().values,
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

@app.get("/")
def root():
    return {"status": "BacktestPro API rodando!", "versao": "1.0"}

@app.get("/ativos")
def listar_ativos():
    return {"ativos": list(ATIVOS.keys())}

@app.post("/backtest")
def rodar_backtest(req: BacktestRequest):
    try:
        ticker = ATIVOS.get(req.ativo, "EURUSD=X")
        inicio, fim = PERIODOS.get(req.periodo, ("2023-01-01", "2025-01-01"))

        print(f"Rodando backtest: {req.ativo} | {req.periodo} | Capital: {req.capital}")

        data = yf.download(ticker, start=inicio, end=fim, interval="1d", progress=False)
        data.columns = data.columns.droplevel(1)
        data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
        data.index = pd.to_datetime(data.index)

        if len(data) < 50:
            return {"erro": "Dados insuficientes para o período selecionado"}

        EMAChannel.ema_period = req.ema_period
        bt = Backtest(data, EMAChannel, cash=req.capital, commission=req.comissao)
        r = bt.run()

        # Equity curve
        equity = r["_equity_curve"]["Equity"].tolist()
        datas  = r["_equity_curve"].index.strftime("%Y-%m-%d").tolist()

        # Trades
        trades = []
        if len(r["_trades"]) > 0:
            for _, t in r["_trades"].iterrows():
                trades.append({
                    "entrada": str(t.get("EntryTime", ""))[:10],
                    "saida":   str(t.get("ExitTime",  ""))[:10],
                    "retorno": round(float(t.get("ReturnPct", 0)) * 100, 2),
                    "lucro":   round(float(t.get("PnL", 0)), 2),
                })

        return {
            "ativo":          req.ativo,
            "periodo":        req.periodo,
            "retorno":        round(float(r["Return [%]"]), 2),
            "retorno_anual":  round(float(r["Return (Ann.) [%]"]), 2),
            "win_rate":       round(float(r["Win Rate [%]"]), 2),
            "sharpe":         round(float(r["Sharpe Ratio"]), 2),
            "max_drawdown":   round(float(r["Max. Drawdown [%]"]), 2),
            "total_trades":   int(r["# Trades"]),
            "profit_factor":  round(float(r["Profit Factor"]), 2),
            "capital_final":  round(float(r["Equity Final [$]"]), 2),
            "equity_curve":   equity[::5],
            "datas_equity":   datas[::5],
            "trades":         trades[-20:],
        }

    except Exception as e:
        return {"erro": str(e), "detalhe": traceback.format_exc()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)