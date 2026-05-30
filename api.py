# ============================================================
# BacktestPro API — v2.3
# Versao: 2.3 | Data: 2026-05-30
# Autor: aaddmorales | Deploy: Railway
# Novidade: /backtest/custom — editor de codigo do trader
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from datetime import datetime, timedelta
import traceback
import os
import ast
import sys
import io

# ── Versão ──────────────────────────────────────────────────
VERSION = "2.3"
BUILD_DATE = "2026-05-30"
# ────────────────────────────────────────────────────────────

app = FastAPI(title="BacktestPro API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Ativos ───────────────────────────────────────────────────
ATIVOS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X",
    "XAU/USD": "GC=F",
    "BTC/USD": "BTC-USD",
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

# ── Imports bloqueados no sandbox ────────────────────────────
IMPORTS_BLOQUEADOS = {
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests", "httpx",
    "open", "exec", "eval", "compile", "__import__",
    "importlib", "ctypes", "multiprocessing", "threading",
    "signal", "pty", "tty", "termios", "fcntl",
}

# ── Request Models ───────────────────────────────────────────
class BacktestRequest(BaseModel):
    ativo: str = "EUR/USD"
    periodo: str = "2 anos"
    capital: float = 10000
    comissao: float = 0.0002
    ema_period: int = 20
    timeframe: str = "1d"

class CustomBacktestRequest(BaseModel):
    codigo: str
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    capital: float = 10000
    comissao: float = 0.0002
    timeframe: str = "1d"

# ── Helpers ──────────────────────────────────────────────────
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
    return df.resample("4h").agg({
        "Open": "first", "High": "max",
        "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna()


def baixar_dados(ativo: str, periodo: str, timeframe: str) -> pd.DataFrame:
    ticker = ATIVOS.get(ativo, "EURUSD=X")
    tf = timeframe if timeframe in TIMEFRAMES else "1d"
    inicio, fim = get_datas(periodo, tf)
    yf_interval = TIMEFRAMES[tf]
    data = yf.download(ticker, start=inicio, end=fim, interval=yf_interval, progress=False)
    if data.empty:
        raise ValueError(f"Sem dados para {ativo}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
    data.index = pd.to_datetime(data.index)
    if tf == "4h":
        data = resample_4h(data)
    if len(data) < 50:
        raise ValueError(f"Dados insuficientes ({len(data)} candles)")
    return data


def formatar_resultado(r, ativo, periodo, tf, ema_period=None):
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
    resultado = {
        "versao":        VERSION,
        "ativo":         ativo,
        "periodo":       periodo,
        "timeframe":     tf,
        "candles":       int(r["_equity_curve"].shape[0]),
        "retorno":       safe(r["Return [%]"]),
        "retorno_anual": safe(r["Return (Ann.) [%]"]),
        "win_rate":      safe(r["Win Rate [%]"]),
        "sharpe":        safe(r["Sharpe Ratio"]),
        "max_drawdown":  safe(r["Max. Drawdown [%]"]),
        "total_trades":  int(r["# Trades"]),
        "profit_factor": safe(r["Profit Factor"]),
        "capital_final": safe(r["Equity Final [$]"]),
        "equity_curve":  equity[::step],
        "datas_equity":  datas[::step],
        "trades":        trades[-20:],
    }
    if ema_period:
        resultado["ema_period"] = ema_period
    return resultado


def verificar_codigo_seguro(codigo: str) -> tuple[bool, str]:
    """Verifica se o código é seguro antes de executar."""
    try:
        tree = ast.parse(codigo)
    except SyntaxError as e:
        return False, f"Erro de sintaxe: {e}"

    for node in ast.walk(tree):
        # Bloquear imports perigosos
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modulos = []
            if isinstance(node, ast.Import):
                modulos = [alias.name.split('.')[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modulos = [node.module.split('.')[0]]
            for mod in modulos:
                if mod in IMPORTS_BLOQUEADOS:
                    return False, f"Import bloqueado por segurança: '{mod}'"

        # Bloquear chamadas perigosas
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in {"exec", "eval", "compile", "__import__", "open"}:
                    return False, f"Função bloqueada por segurança: '{node.func.id}'"

    # Verificar se tem classe Strategy
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    tem_strategy = any(
        any(isinstance(b, ast.Name) and b.id == "Strategy" for b in c.bases)
        for c in classes
    )
    if not tem_strategy:
        return False, "O código deve conter uma classe que herda de Strategy"

    return True, "ok"


# ── Estratégia EMA Channel (padrão) ─────────────────────────
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


# ── Endpoints ────────────────────────────────────────────────
@app.get("/")
def root():
    if os.path.exists("index.html"):
        return FileResponse("index.html", media_type="text/html")
    return {"app": "BacktestPro API", "versao": VERSION, "docs": "/docs"}


@app.get("/version")
def get_version():
    return {
        "versao":     VERSION,
        "build":      BUILD_DATE,
        "estrategia": "EMA Channel High/Low + Custom Strategy",
        "ativos":     len(ATIVOS),
        "timeframes": list(TIMEFRAMES.keys()),
        "mercados":   list(CATEGORIAS.keys()),
    }


@app.get("/ativos")
def listar_ativos():
    return {"ativos": list(ATIVOS.keys()), "categorias": CATEGORIAS}


@app.get("/timeframes")
def listar_timeframes():
    return {"timeframes": list(TIMEFRAMES.keys()), "limites_dias": LIMITE_DIAS}


@app.post("/backtest")
def rodar_backtest(req: BacktestRequest):
    try:
        tf = req.timeframe if req.timeframe in TIMEFRAMES else "1d"
        data = baixar_dados(req.ativo, req.periodo, tf)
        EMAChannel.ema_period = req.ema_period
        bt = Backtest(data, EMAChannel, cash=req.capital, commission=req.comissao)
        r = bt.run()
        resultado = formatar_resultado(r, req.ativo, req.periodo, tf, req.ema_period)
        print(f"[v{VERSION}] Backtest: {req.ativo} | {req.periodo} | TF:{tf} | EMA:{req.ema_period}")
        return resultado
    except Exception as e:
        return {"erro": str(e), "detalhe": traceback.format_exc()}


@app.post("/backtest/custom")
def rodar_backtest_custom(req: CustomBacktestRequest):
    """
    Executa estratégia personalizada do trader.
    O trader cola o código da classe Strategy e nós executamos.
    """
    try:
        # 1. Verificar segurança do código
        seguro, msg = verificar_codigo_seguro(req.codigo)
        if not seguro:
            return {"erro": msg}

        # 2. Baixar dados
        tf = req.timeframe if req.timeframe in TIMEFRAMES else "1d"
        data = baixar_dados(req.ativo, req.periodo, tf)

        # 3. Executar código do trader em namespace controlado
        namespace = {
            "Strategy": Strategy,
            "pd": pd,
            "np": np,
        }

        exec(req.codigo, namespace)

        # 4. Encontrar a classe Strategy definida pelo trader
        estrategia_classe = None
        for nome, obj in namespace.items():
            if (isinstance(obj, type) and
                issubclass(obj, Strategy) and
                obj is not Strategy):
                estrategia_classe = obj
                break

        if estrategia_classe is None:
            return {"erro": "Nenhuma classe Strategy encontrada no código"}

        # 5. Rodar backtest
        bt = Backtest(data, estrategia_classe, cash=req.capital, commission=req.comissao)
        r = bt.run()
        resultado = formatar_resultado(r, req.ativo, req.periodo, tf)
        resultado["estrategia"] = estrategia_classe.__name__
        resultado["custom"] = True

        print(f"[v{VERSION}] Custom Backtest: {estrategia_classe.__name__} | {req.ativo} | {req.periodo} | TF:{tf}")
        return resultado

    except Exception as e:
        return {"erro": str(e), "detalhe": traceback.format_exc()}


@app.get("/templates")
def listar_templates():
    """Templates prontos para o trader copiar e colar."""
    return {
        "templates": [
            {
                "nome": "EMA Channel — XAU/USD",
                "descricao": "Canal de EMA 20 no High e Low. Compra no breakout.",
                "ativo_sugerido": "XAU/USD",
                "codigo": """class EMAChannelStrategy(Strategy):
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
                self.position.close()"""
            },
            {
                "nome": "Cruzamento de Médias — EUR/USD",
                "descricao": "Média rápida (9) cruza média lenta (21). Clássico.",
                "ativo_sugerido": "EUR/USD",
                "codigo": """class CrossoverStrategy(Strategy):
    fast = 9
    slow = 21

    def init(self):
        self.ema_fast = self.I(
            lambda x: pd.Series(x).ewm(span=self.fast, adjust=False).mean().values,
            self.data.Close
        )
        self.ema_slow = self.I(
            lambda x: pd.Series(x).ewm(span=self.slow, adjust=False).mean().values,
            self.data.Close
        )

    def next(self):
        if not self.position:
            if self.ema_fast[-1] > self.ema_slow[-1]:
                self.buy()
        else:
            if self.ema_fast[-1] < self.ema_slow[-1]:
                self.position.close()"""
            },
            {
                "nome": "RSI Reversal — BTC/USD",
                "descricao": "Compra quando RSI < 30 (sobrevendido). Vende quando RSI > 70.",
                "ativo_sugerido": "BTC/USD",
                "codigo": """class RSIStrategy(Strategy):
    rsi_period = 14
    rsi_low  = 30
    rsi_high = 70

    def init(self):
        def rsi(close, period=14):
            s = pd.Series(close)
            delta = s.diff()
            gain = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
            rs = gain / loss
            return (100 - (100 / (1 + rs))).values

        self.rsi = self.I(rsi, self.data.Close, self.rsi_period)

    def next(self):
        if not self.position:
            if self.rsi[-1] < self.rsi_low:
                self.buy()
        else:
            if self.rsi[-1] > self.rsi_high:
                self.position.close()"""
            },
            {
                "nome": "Mini Índice B3 — IBOVESPA",
                "descricao": "EMA Channel adaptado para o mercado brasileiro.",
                "ativo_sugerido": "IBOVESPA",
                "codigo": """class B3EMAStrategy(Strategy):
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
                self.position.close()"""
            },
        ]
    }

# ============================================================
# BacktestPro API — v2.3 | FIM DO FICHEIRO
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
