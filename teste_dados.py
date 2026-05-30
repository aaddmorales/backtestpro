import yfinance as yf
import pandas as pd
from backtesting import Backtest, Strategy

# Lista de ativos para testar
ATIVOS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "XAU/USD (Ouro)": "GC=F",
    "BTC/USD": "BTC-USD",
    "IBOV":    "^BVSP",
}

class EMAChannel(Strategy):
    ema_period = 85  # melhor período que encontramos

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

# Testa todos os ativos
resultados = []

for nome, ticker in ATIVOS.items():
    try:
        print(f"Testando {nome}...")
        data = yf.download(ticker, start="2022-01-01", end="2025-01-01", interval="1d", progress=False)
        data.columns = data.columns.droplevel(1)
        data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
        data.index = pd.to_datetime(data.index)

        if len(data) < 100:
            print(f"  ⚠ Dados insuficientes para {nome}")
            continue

        bt = Backtest(data, EMAChannel, cash=10000, commission=0.0002)
        r = bt.run()

        resultados.append({
            "Ativo":        nome,
            "Retorno %":    round(r["Return [%]"], 2),
            "Win Rate %":   round(r["Win Rate [%]"], 2),
            "Sharpe":       round(r["Sharpe Ratio"], 2),
            "Max DD %":     round(r["Max. Drawdown [%]"], 2),
            "Trades":       r["# Trades"],
            "Profit Factor":round(r["Profit Factor"], 2),
        })
        print(f"  ✓ Retorno: {r['Return [%]']:.2f}% | Win Rate: {r['Win Rate [%]']:.2f}% | Trades: {r['# Trades']}")

    except Exception as e:
        print(f"  ✗ Erro em {nome}: {e}")

# Tabela final com ranking
print("\n========== RANKING GERAL ==========")
df = pd.DataFrame(resultados).sort_values("Retorno %", ascending=False)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 120)
print(df.to_string(index=False))
print("\n>>> Melhor ativo:", df.iloc[0]["Ativo"])
print(">>> Pior ativo: ", df.iloc[-1]["Ativo"])