# ============================================================
# BacktestPro API — v2.6
# Versao: 2.6 | Data: 2026-05-30
# Autor: aaddmorales | Deploy: Railway
# Novidade: PostgreSQL — guardar estratégias e backtests
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
import psycopg2
from psycopg2.extras import RealDictCursor

# ── Versão ──────────────────────────────────────────────────
VERSION = "2.6"
BUILD_DATE = "2026-05-30"
# ────────────────────────────────────────────────────────────

app = FastAPI(title="BacktestPro API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Base de Dados ────────────────────────────────────────────
def get_db():
    url = os.environ["DATABASE_URL"].strip()
    # Railway ja configura SSL na URL automaticamente
    return psycopg2.connect(url)

def init_db():
    """Cria as tabelas se não existirem."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS estrategias (
                id          SERIAL PRIMARY KEY,
                nome        VARCHAR(100),
                descricao   TEXT,
                codigo      TEXT NOT NULL,
                ativo       VARCHAR(20),
                publica     BOOLEAN DEFAULT false,
                preco       DECIMAL(10,2) DEFAULT 0,
                criado_em   TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS backtests (
                id              SERIAL PRIMARY KEY,
                estrategia_id   INTEGER REFERENCES estrategias(id),
                nome_estrategia VARCHAR(100),
                ativo           VARCHAR(20),
                periodo         VARCHAR(20),
                timeframe       VARCHAR(10),
                ema_period      INTEGER,
                capital         DECIMAL(12,2),
                retorno         DECIMAL(10,2),
                retorno_anual   DECIMAL(10,2),
                win_rate        DECIMAL(10,2),
                sharpe          DECIMAL(10,4),
                max_drawdown    DECIMAL(10,2),
                total_trades    INTEGER,
                profit_factor   DECIMAL(10,4),
                capital_final   DECIMAL(12,2),
                candles         INTEGER,
                custom          BOOLEAN DEFAULT false,
                criado_em       TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print(f"[v{VERSION}] Base de dados inicializada!")
    except Exception as e:
        print(f"[v{VERSION}] Erro DB: {e}")

# Inicializar DB ao arrancar
init_db()

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
    "1d": "1d", "4h": "1h", "1h": "1h",
    "30m": "30m", "15m": "15m", "5m": "5m",
}

LIMITE_DIAS = {
    "1d": 1095, "4h": 59, "1h": 729,
    "30m": 59, "15m": 59, "5m": 59,
}

IMPORTS_BLOQUEADOS = {
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests", "httpx",
    "importlib", "ctypes", "multiprocessing", "threading",
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
    nome: str = "Minha Estratégia"
    descricao: str = ""
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    capital: float = 10000
    comissao: float = 0.0002
    timeframe: str = "1d"
    guardar: bool = True

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


def resample_4h(df):
    return df.resample("4h").agg({
        "Open": "first", "High": "max",
        "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna()


def baixar_dados(ativo, periodo, timeframe):
    ticker = ATIVOS.get(ativo, "EURUSD=X")
    tf = timeframe if timeframe in TIMEFRAMES else "1d"
    inicio, fim = get_datas(periodo, tf)
    data = yf.download(ticker, start=inicio, end=fim, interval=TIMEFRAMES[tf], progress=False)
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
    return data, tf


def safe(val):
    try:
        v = float(val)
        return round(v, 2) if v == v else 0.0
    except:
        return 0.0


def formatar_resultado(r, ativo, periodo, tf, ema_period=None, nome=None, custom=False):
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
    res = {
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
        "custom":        custom,
    }
    if ema_period: res["ema_period"] = ema_period
    if nome: res["estrategia"] = nome
    return res


def guardar_backtest_db(resultado, nome_estrategia, estrategia_id=None, ema_period=None, custom=False):
    """Guarda o resultado do backtest na base de dados."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO backtests (
                estrategia_id, nome_estrategia, ativo, periodo, timeframe,
                ema_period, capital, retorno, retorno_anual, win_rate,
                sharpe, max_drawdown, total_trades, profit_factor,
                capital_final, candles, custom
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            estrategia_id, nome_estrategia,
            resultado["ativo"], resultado["periodo"], resultado["timeframe"],
            ema_period, 10000,
            resultado["retorno"], resultado["retorno_anual"], resultado["win_rate"],
            resultado["sharpe"], resultado["max_drawdown"], resultado["total_trades"],
            resultado["profit_factor"], resultado["capital_final"],
            resultado["candles"], custom
        ))
        backtest_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return backtest_id
    except Exception as e:
        print(f"Erro ao guardar backtest: {e}")
        return None


def verificar_codigo_seguro(codigo):
    try:
        tree = ast.parse(codigo)
    except SyntaxError as e:
        return False, f"Erro de sintaxe: {e}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modulos = []
            if isinstance(node, ast.Import):
                modulos = [a.name.split('.')[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modulos = [node.module.split('.')[0]]
            for mod in modulos:
                if mod in IMPORTS_BLOQUEADOS:
                    return False, f"Import bloqueado: '{mod}'"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in {"exec", "eval", "compile", "__import__", "open"}:
                    return False, f"Função bloqueada: '{node.func.id}'"
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    tem_strategy = any(
        any(isinstance(b, ast.Name) and b.id == "Strategy" for b in c.bases)
        for c in classes
    )
    if not tem_strategy:
        return False, "O código deve conter uma classe que herda de Strategy"
    return True, "ok"


# ── Estratégia EMA Channel ───────────────────────────────────
class EMAChannel(Strategy):
    ema_period = 20
    def init(self):
        self.ema_high = self.I(lambda h: pd.Series(h).ewm(span=self.ema_period, adjust=False).mean().values, self.data.High)
        self.ema_low  = self.I(lambda l: pd.Series(l).ewm(span=self.ema_period, adjust=False).mean().values, self.data.Low)
    def next(self):
        preco = self.data.Close[-1]
        if not self.position:
            if preco > self.ema_high[-1]: self.buy()
        else:
            if preco < self.ema_low[-1]:  self.position.close()


# ── Endpoints ────────────────────────────────────────────────
@app.get("/")
def root():
    if os.path.exists("index.html"):
        return FileResponse("index.html", media_type="text/html")
    return {"app": "BacktestPro API", "versao": VERSION, "docs": "/docs"}


@app.get("/version")
def get_version():
    return {
        "versao": VERSION, "build": BUILD_DATE,
        "estrategia": "EMA Channel High/Low + Custom",
        "ativos": len(ATIVOS), "timeframes": list(TIMEFRAMES.keys()),
        "mercados": list(CATEGORIAS.keys()), "db": "PostgreSQL",
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
        data, tf = baixar_dados(req.ativo, req.periodo, req.timeframe)
        EMAChannel.ema_period = req.ema_period
        bt = Backtest(data, EMAChannel, cash=req.capital, commission=req.comissao)
        r  = bt.run()
        resultado = formatar_resultado(r, req.ativo, req.periodo, tf, req.ema_period, "EMA Channel")
        # Guardar na DB
        bid = guardar_backtest_db(resultado, "EMA Channel", ema_period=req.ema_period)
        if bid: resultado["backtest_id"] = bid
        print(f"[v{VERSION}] Backtest EMA: {req.ativo} | {tf} | ID:{bid}")
        return resultado
    except Exception as e:
        return {"erro": str(e), "detalhe": traceback.format_exc()}


@app.post("/backtest/custom")
def rodar_backtest_custom(req: CustomBacktestRequest):
    try:
        seguro, msg = verificar_codigo_seguro(req.codigo)
        if not seguro:
            return {"erro": msg}

        data, tf = baixar_dados(req.ativo, req.periodo, req.timeframe)

        namespace = {"Strategy": Strategy, "pd": pd, "np": np}
        exec(req.codigo, namespace)

        estrategia_classe = None
        for nome, obj in namespace.items():
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                estrategia_classe = obj
                break

        if estrategia_classe is None:
            return {"erro": "Nenhuma classe Strategy encontrada"}

        bt = Backtest(data, estrategia_classe, cash=req.capital, commission=req.comissao)
        r  = bt.run()
        resultado = formatar_resultado(r, req.ativo, req.periodo, tf, nome=estrategia_classe.__name__, custom=True)

        # Guardar estratégia e backtest na DB
        estrategia_id = None
        if req.guardar:
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO estrategias (nome, descricao, codigo, ativo)
                    VALUES (%s, %s, %s, %s) RETURNING id
                """, (req.nome, req.descricao, req.codigo, req.ativo))
                estrategia_id = cur.fetchone()[0]
                conn.commit()
                cur.close()
                conn.close()
                resultado["estrategia_id"] = estrategia_id
            except Exception as e:
                print(f"Erro ao guardar estratégia: {e}")

            bid = guardar_backtest_db(resultado, req.nome, estrategia_id=estrategia_id, custom=True)
            if bid: resultado["backtest_id"] = bid

        resultado["estrategia"] = estrategia_classe.__name__
        print(f"[v{VERSION}] Custom: {estrategia_classe.__name__} | {req.ativo} | guardado:{req.guardar}")
        return resultado

    except Exception as e:
        return {"erro": str(e), "detalhe": traceback.format_exc()}


@app.get("/historico")
def listar_historico(limite: int = 50):
    """Retorna os últimos backtests guardados na DB."""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, nome_estrategia, ativo, periodo, timeframe,
                   ema_period, retorno, retorno_anual, win_rate, sharpe,
                   max_drawdown, total_trades, profit_factor, capital_final,
                   candles, custom, criado_em
            FROM backtests
            ORDER BY criado_em DESC
            LIMIT %s
        """, (limite,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"historico": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"erro": str(e)}


@app.get("/ranking")
def listar_ranking():
    """Top estratégias por Sharpe Ratio — base do Marketplace."""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                b.nome_estrategia,
                b.ativo,
                b.timeframe,
                AVG(b.retorno)       as retorno_medio,
                AVG(b.win_rate)      as win_rate_medio,
                AVG(b.sharpe)        as sharpe_medio,
                AVG(b.max_drawdown)  as drawdown_medio,
                AVG(b.profit_factor) as pf_medio,
                COUNT(*)             as total_backtests
            FROM backtests b
            WHERE b.sharpe > 0
              AND b.win_rate > 40
              AND b.profit_factor > 1.0
              AND b.total_trades >= 5
            GROUP BY b.nome_estrategia, b.ativo, b.timeframe
            ORDER BY sharpe_medio DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"ranking": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"erro": str(e)}


@app.get("/stats")
def estatisticas():
    """Estatísticas gerais da plataforma."""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                COUNT(*) as total_backtests,
                COUNT(DISTINCT nome_estrategia) as total_estrategias,
                COUNT(DISTINCT ativo) as total_ativos,
                AVG(retorno) as retorno_medio,
                AVG(win_rate) as win_rate_medio,
                MAX(retorno) as melhor_retorno
            FROM backtests
        """)
        stats = dict(cur.fetchone())
        cur.close()
        conn.close()
        return {"stats": stats, "versao": VERSION}
    except Exception as e:
        return {"erro": str(e)}


@app.get("/templates")
def listar_templates():
    return {
        "templates": [
            {
                "nome": "EMA Channel — XAU/USD",
                "descricao": "Canal EMA 20 High/Low. Padrão TrailingBot.",
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
                "descricao": "EMA 9 cruza EMA 21. Estratégia clássica.",
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
                "descricao": "Compra RSI < 30, vende RSI > 70.",
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
                "nome": "Mini Índice — IBOVESPA 🇧🇷",
                "descricao": "EMA Channel para o mercado brasileiro.",
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
# BacktestPro API — v2.6 | FIM DO FICHEIRO
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
