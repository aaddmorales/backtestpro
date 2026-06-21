# ============================================================
#  BotBacktest API — v3.5 (Radar IA + cache)
#  Data: 2026-06-07 | Deploy: Railway
#  Novidades v3.1:
#  - FIX CRITICO: rodar_codigo_custom agora executa de verdade com o motor
#    backtesting.py (antes engolia erro e devolvia sempre 0 trades).
#    Editor Python, IA e galeria de estrategias passam a funcionar de fato.
#  - Parser do /gerar-bot-ia entende portugues (canal high/low, cruzamento
#    com periodos, tolerante a typos; "2 medias de 20" = periodo 20).
#  Historico anterior:
#  Novidades v3.0:
#  - Catalogo 40 ativos em 7 categorias com gating por plano (/ativos/catalogo)
#  - Galeria de 10 estrategias prontas, 2 assinaturas da casa (/estrategias/prontas)
#  - Conector MT5 read-only: /conector/registrar, /conector/snapshot,
#    /conector/evento, /conector/bots (token, nunca credenciais de corretora)
#  - Agente Bloco F (F1-F4): consistencia vivo x backtest, cooldown anti-spam
#    (/agente/sugestoes, /agente/sugestoes/lida)
#  Historico anterior:
#  Novidades v2.1:
#  - v3.3: /radar/analisar (OffMind + coletivo -> sugestao aplicavel no chat do Radar)
#  - /babymachine/contador: endpoint leve que retorna total de backtests
#    do usuario (count exact) p/ contador no topo da coluna esquerda.
#  Historico anterior:
#  Novidades v2.0:
#  - BabyMachine: comportamento agora inclui serie evolucao (Sharpe e
#    retorno de cada backtest do usuario em ordem cronologica) p/ 2 graficos.
#  Historico anterior:
#  Novidades v1.9:
#  - BabyMachine analise: /babymachine/analisar le os dados coletados e
#    gera (B) aprendizado coletivo anonimo (tendencias do banco inteiro) +
#    (C) deteccao de comportamento de risco da jornada do usuario
#    (overfitting manual, win-alto/retorno-negativo, etc). Analise por
#    regras puras. user_id se logado, senao sessao_id. Sempre honesto.
#  Historico anterior:
#  Novidades v1.8:
#  - Renomeacao interna da feature de padroes para OffMind.
#    Rotas /offmind/analisar e /offmind/padroes. Tecnicas-chave protegidas no backend.
#  Historico anterior:
#  Novidades v1.7:
#  - OffMind (Association Rules): engine generica de deteccao de padroes.
#    /offmind/analisar detecta padrao no historico e mede acerto/falha
#    em varios horizontes (3/5/10/20 velas), com alvo/stop por ATR.
#    /offmind/padroes lista os padroes disponiveis. Detectores plugaveis
#    (Categoria 1: engolfo, martelo, estrela, 3 velas). Sempre honesto:
#    mostra acerto E falha, nunca promete retorno futuro.
#  Historico anterior:
#  Novidades v1.6:
#  - Deteccao de overfitting (out-of-sample): endpoint /validar-overfitting
#    fatia o historico em treino (split%) e teste (resto, dados nunca vistos),
#    roda a MESMA estrategia nas duas partes, compara metricas e da um
#    veredito honesto (robusta / atencao / overfitting). Split cronologico
#    (nunca embaralha serie temporal). Nunca promete retorno futuro.
#  Historico anterior:
#  Novidades v1.5:
#  - Otimizacao de parametros: endpoint /otimizar varre combinacoes de
#    stop_loss, take_profit e ema_period; baixa dados UMA vez e varia em
#    memoria; retorna ranking + alerta de overfitting. Teto de 50 combos.
#    Cada combo tambem grava na BabyMachine (backtests_historico).
#  Historico anterior:
#  Novidades v1.4:
#  - BabyMachine: registra historico de cada backtest na tabela
#    backtests_historico (Supabase). Fundacao p/ IA aprender a
#    jornada do trader. Gravacao NON-BLOCKING (falha nao quebra o teste).
#  Historico anterior:
#  Novidades v1.3:
#  - Separacao landing/app:
#      "/"     serve index.html  (landing page)
#      "/app"  serve app.html    (antigo index.html do backtest)
#  - success_url/cancel_url do Stripe apontam para /app
#  Historico:
#  - v2.5: fix plano "trader"->"trader_pro" (batia com check constraint perfis_plano_check)
#  - v2.4: trava anti-duplicação no /criar-checkout (já tem assinatura ativa -> portal)
#  - v2.3: endpoint /criar-portal (Stripe Customer Portal: usuario cancela/gerencia sozinho)
#  - v2.2: webhook customer.subscription.deleted -> rebaixa cancelados p/ free
#  - v1.2: fix StripeObject.to_dict() no webhook + SUPABASE_URL
#  - v1.1: payload completo estilo TradingView (/backtest/visual e /custom)
# ============================================================

from fastapi import FastAPI, HTTPException, Request
import stripe
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import traceback
import random
import os
import hashlib
import uuid as _uuid

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

app = FastAPI(title="BotBacktest API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── MAPA DE ATIVOS ──────────────────────────────────────────
ATIVOS_MAP = {
    "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X", "USD/CAD": "CAD=X", "USD/CHF": "CHF=X",
    "XAU/USD": "GC=F",    "XAG/USD": "SI=F",
    "BTC/USD": "BTC-USD",  "ETH/USD": "ETH-USD",
    "IBOVESPA": "^BVSP",   "USD/BRL": "BRL=X",
    "S&P500": "^GSPC",     "NASDAQ": "^IXIC",
}

PERIODOS_MAP = {
    "6 meses": "6mo", "1 ano": "1y", "2 anos": "2y",
    "3 anos": "3y",   "5 anos": "5y",
}

INTERVALOS_MAP = {
    "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "1h",  "1d": "1d",
}

# ── MODELS ──────────────────────────────────────────────────
class BacktestParams(BaseModel):
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    timeframe: str = "1d"
    indicador: str = "EMA Channel High/Low"
    ema_period: int = 20
    stop_loss: float = 50
    take_profit: float = 100
    capital: float = 10000
    max_ops: int = 5
    comissao: float = 0.0002
    user_id: Optional[str] = None      # BabyMachine: dono do teste (se logado)
    sessao_id: Optional[str] = None    # BabyMachine: agrupa a jornada de ajustes

class BacktestCustom(BacktestParams):
    codigo: str = ""

class IARequest(BaseModel):
    descricao: str

# ── HELPERS ─────────────────────────────────────────────────
# ── Cache de dados (v3.2): evita rate-limit do Yahoo e acelera repetições ──
import time as _time
_DADOS_CACHE = {}           # chave -> (timestamp, DataFrame)
_DADOS_CACHE_TTL = 600      # 10 minutos
_DADOS_CACHE_MAX = 20       # teto de entradas (RAM limitada no Railway)

def baixar_dados(ativo: str, periodo: str, timeframe: str) -> pd.DataFrame:
    ticker = ATIVOS_MAP.get(ativo, "GC=F")
    periodo_yf = PERIODOS_MAP.get(periodo, "2y")
    intervalo_yf = INTERVALOS_MAP.get(timeframe, "1d")

    if intervalo_yf in ["5m","15m","30m"]:
        periodo_yf = "60d"

    chave = f"{ticker}|{periodo_yf}|{intervalo_yf}"
    agora = _time.time()

    # 1) cache fresco? serve da memória (sem bater no Yahoo)
    hit = _DADOS_CACHE.get(chave)
    if hit and (agora - hit[0]) < _DADOS_CACHE_TTL:
        return hit[1].copy()

    # 2) baixa com 1 retry (rate-limit transitório do Yahoo)
    df = None
    erro = None
    for tentativa in range(2):
        try:
            tk = yf.Ticker(ticker)
            df = tk.history(period=periodo_yf, interval=intervalo_yf)
            if df is not None and not df.empty:
                break
        except Exception as e:
            erro = e
        if tentativa == 0:
            _time.sleep(2)

    # 3) falhou agora, mas tem cache velho? melhor servir dado de até 2h
    if (df is None or df.empty) and hit and (agora - hit[0]) < 7200:
        return hit[1].copy()

    if df is None or df.empty:
        if erro:
            raise HTTPException(400, f"Erro ao baixar dados: {str(erro)}")
        raise HTTPException(400,
            f"Fonte de dados temporariamente indisponível para {ativo} "
            f"(limite de requisições). Aguarde ~1 minuto e tente de novo.")

    # Flatten MultiIndex se existir
    if hasattr(df.columns, 'levels'):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    # Manter APENAS colunas OHLCV — ignorar Dividends, Stock Splits, etc.
    colunas_manter = ['Open','High','Low','Close','Volume']
    df = df[[c for c in colunas_manter if c in df.columns]]

    df = df.dropna(subset=['Open','High','Low','Close'])

    if len(df) < 5:
        raise HTTPException(400, f"Dados insuficientes para {ativo}.")

    # guarda no cache (com teto de entradas; intraday pesado fica de fora p/ poupar RAM)
    if len(df) <= 6000:
        if len(_DADOS_CACHE) >= _DADOS_CACHE_MAX:
            mais_velha = min(_DADOS_CACHE, key=lambda k: _DADOS_CACHE[k][0])
            _DADOS_CACHE.pop(mais_velha, None)
        _DADOS_CACHE[chave] = (agora, df.copy())

    return df

def calcular_ema_channel(df: pd.DataFrame, period: int):
    df = df.copy()
    df['ema_high'] = df['High'].ewm(span=period, adjust=False).mean()
    df['ema_low']  = df['Low'].ewm(span=period, adjust=False).mean()
    return df

def calcular_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calcular_macd(series: pd.Series):
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calcular_bollinger(series: pd.Series, period: int = 20):
    sma   = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return upper, lower

def rodar_estrategia(df: pd.DataFrame, params: BacktestParams) -> dict:
    """Motor de backtest principal — retorna trades e equity curve"""
    df = df.copy()
    capital_inicial = params.capital
    capital = capital_inicial
    comissao = params.comissao
    ind = params.indicador
    period = params.ema_period

    # Calcular indicadores
    if "EMA Channel" in ind or ind == "EMA":
        df = calcular_ema_channel(df, period)
    elif ind == "RSI":
        df['rsi'] = calcular_rsi(df['Close'], period)
    elif ind == "MACD":
        df['macd'], df['signal'] = calcular_macd(df['Close'])
    elif ind == "Bollinger Bands":
        df['bb_upper'], df['bb_lower'] = calcular_bollinger(df['Close'], period)
    elif ind == "SMA":
        df['sma'] = df['Close'].rolling(period).mean()

    df = df.dropna()

    trades = []
    equity_curve = [capital]
    posicao = None  # {'tipo': 'long', 'entrada': preco, 'data': dt, 'idx': i}

    for i in range(1, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i-1]
        preco = float(row['Close'])
        data  = str(df.index[i])[:16]

        # Sinais de entrada/saída por indicador
        sinal_compra = False
        sinal_venda  = False

        if "EMA Channel" in ind or ind == "EMA":
            ema_h = float(row['ema_high'])
            ema_l = float(row['ema_low'])
            sinal_compra = preco > ema_h and float(prev['Close']) <= float(prev['ema_high'])
            sinal_venda  = preco < ema_l and float(prev['Close']) >= float(prev['ema_low'])
        elif ind == "RSI":
            sinal_compra = float(row['rsi']) < 30 and float(prev['rsi']) >= 30
            sinal_venda  = float(row['rsi']) > 70
        elif ind == "MACD":
            sinal_compra = float(row['macd']) > float(row['signal']) and float(prev['macd']) <= float(prev['signal'])
            sinal_venda  = float(row['macd']) < float(row['signal']) and float(prev['macd']) >= float(prev['signal'])
        elif ind == "Bollinger Bands":
            sinal_compra = preco < float(row['bb_lower'])
            sinal_venda  = preco > float(row['bb_upper'])
        elif ind == "SMA":
            sinal_compra = preco > float(row['sma']) and float(prev['Close']) <= float(prev['sma'])
            sinal_venda  = preco < float(row['sma']) and float(prev['Close']) >= float(prev['sma'])

        if posicao is None:
            if sinal_compra:
                posicao = {'tipo': 'long', 'entrada': preco, 'data': data, 'idx': i}
        else:
            # Verifica SL/TP ou sinal de saída
            entrada = posicao['entrada']
            variacao = (preco - entrada) / entrada
            saiu = False

            if sinal_venda:
                saiu = True
            elif variacao <= -(params.stop_loss / 10000):
                saiu = True
                variacao = -(params.stop_loss / 10000)
            elif variacao >= (params.take_profit / 10000):
                saiu = True
                variacao = params.take_profit / 10000

            if saiu:
                retorno_pct = variacao * 100
                custo = comissao * 2
                retorno_liquido = retorno_pct - (custo * 100)
                pl = capital * retorno_liquido / 100
                capital += pl

                trades.append({
                    "entrada": posicao['data'],
                    "saida": data,
                    "preco_entrada": round(entrada, 5),
                    "preco_saida": round(preco, 5),
                    "retorno_pct": round(retorno_liquido, 4),
                    "pl": round(pl, 2),
                    "resultado": "Ganho" if pl > 0 else "Perda",
                    "idx_entrada": posicao['idx'],
                    "idx_saida": i,
                })
                posicao = None

        equity_curve.append(round(capital, 2))

    return {"trades": trades, "equity_curve": equity_curve, "df": df, "capital_final": capital}

def calcular_metricas_completas(resultado: dict, params: BacktestParams, df: pd.DataFrame) -> dict:
    """Calcula TODAS as métricas estilo TradingView"""
    trades       = resultado['trades']
    equity_curve = resultado['equity_curve']
    capital_ini  = params.capital
    capital_fin  = resultado['capital_final']

    if not trades:
        return metricas_vazias(capital_ini)

    # ── Métricas básicas ──
    total     = len(trades)
    ganhos    = [t for t in trades if t['pl'] > 0]
    perdas    = [t for t in trades if t['pl'] <= 0]
    win_rate  = len(ganhos) / total * 100 if total > 0 else 0
    retorno   = (capital_fin - capital_ini) / capital_ini * 100

    gross_profit = sum(t['pl'] for t in ganhos)
    gross_loss   = abs(sum(t['pl'] for t in perdas))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 9.99

    # ── Sharpe Ratio ──
    retornos_arr = np.array([t['retorno_pct'] for t in trades])
    sharpe = round(
        np.mean(retornos_arr) / np.std(retornos_arr) * np.sqrt(252)
        if np.std(retornos_arr) > 0 else 0, 2
    )

    # ── Max Drawdown ──
    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd   = (eq - peak) / peak * 100
    max_dd = round(float(np.min(dd)), 2)

    # ── Buy & Hold ──
    preco_ini = float(df['Close'].iloc[0])
    preco_fin = float(df['Close'].iloc[-1])
    buy_hold  = round((preco_fin - preco_ini) / preco_ini * 100, 2)

    # ── CAGR ──
    anos = len(df) / 252
    cagr = round(((capital_fin / capital_ini) ** (1 / max(anos, 0.1)) - 1) * 100, 2) if anos > 0 else 0

    # ── ROI Distribution ──
    retornos_list = [t['retorno_pct'] for t in trades]
    hist_counts, hist_bins = np.histogram(retornos_list, bins=20)
    roi_distribution = [
        {"bin": round(float(hist_bins[i]), 3), "count": int(hist_counts[i]),
         "positivo": hist_bins[i] >= 0}
        for i in range(len(hist_counts))
    ]

    # ── Run-ups e Drawdowns por trade ──
    run_ups   = []
    drawdowns_list = []
    for t in trades:
        if t['pl'] > 0:
            run_ups.append(t['retorno_pct'])
        else:
            drawdowns_list.append(t['retorno_pct'])

    avg_runup   = round(np.mean(run_ups), 4) if run_ups else 0
    avg_drawdown_trade = round(np.mean(drawdowns_list), 4) if drawdowns_list else 0

    # ── Duração média dos trades (bars) ──
    duracoes = [abs(t['idx_saida'] - t['idx_entrada']) for t in trades]
    avg_bars = round(np.mean(duracoes)) if duracoes else 0

    # ── Maior ganho e maior perda ──
    maior_ganho = round(max((t['pl'] for t in ganhos), default=0), 2)
    maior_perda = round(min((t['pl'] for t in perdas), default=0), 2)

    # ── Account size required (margem estimada) ──
    account_required = round(capital_ini * (1 + abs(max_dd) / 100), 2)

    # ── Candles OHLCV para o gráfico ──
    # v3.2: usa o MESMO df dos trades (indices alinhados) e tempo UNIX (epoch)
    # p/ intraday funcionar — antes era so a data (str[:10]) e todos os candles
    # do mesmo dia viravam "duplicados" no front, sumindo do grafico.
    df_plot = resultado.get('df') if isinstance(resultado.get('df'), pd.DataFrame) else df
    tempos = []
    for ix in df_plot.index:
        try:
            tempos.append(int(ix.timestamp()))
        except Exception:
            tempos.append(int(pd.Timestamp(str(ix)).timestamp()))
    candles = []
    for i, (idx, row) in enumerate(df_plot.iterrows()):
        candles.append({
            "t": tempos[i],
            "o": round(float(row['Open']), 4),
            "h": round(float(row['High']), 4),
            "l": round(float(row['Low']), 4),
            "c": round(float(row['Close']), 4),
            "v": int(row.get('Volume', 0) or 0),
        })

    # ── Markers de trades nos candles (tempo UNIX pelo indice do trade) ──
    def _tempo_do_idx(i, fallback):
        if isinstance(i, int) and 0 <= i < len(tempos):
            return tempos[i]
        try:
            return int(pd.Timestamp(fallback).timestamp())
        except Exception:
            return None
    markers = []
    for t in trades:
        markers.append({
            "idx": t['idx_entrada'],
            "t": _tempo_do_idx(t['idx_entrada'], t['entrada']),
            "data": t['entrada'],
            "tipo": "BUY",
            "preco": t['preco_entrada'],
            "cor": "#00d084",
        })
        markers.append({
            "idx": t['idx_saida'],
            "t": _tempo_do_idx(t['idx_saida'], t['saida']),
            "data": t['saida'],
            "tipo": "SELL",
            "preco": t['preco_saida'],
            "cor": "#ff4d6a" if t['pl'] <= 0 else "#00d084",
        })

    # ── Sugestão da IA ──
    sugestao = gerar_sugestao_ia(win_rate, sharpe, max_dd, profit_factor, retorno)

    return {
        # Header
        "ativo": params.ativo,
        "periodo": params.periodo,
        "timeframe": params.timeframe,
        "candles": len(df),
        "data_backtest": datetime.now().strftime("%d/%m/%Y"),

        # Retorno
        "retorno": round(retorno, 2),
        "capital_inicial": capital_ini,
        "capital_final": round(capital_fin, 2),
        "lucro_perda": round(capital_fin - capital_ini, 2),
        "retorno_anual": round(cagr, 2),

        # Key stats (topo)
        "win_rate": round(win_rate, 2),
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "total_trades": total,

        # Gross
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),

        # Trades analysis
        "avg_pnl": round((capital_fin - capital_ini) / total, 2) if total > 0 else 0,
        "avg_pnl_pct": round(retorno / total, 4) if total > 0 else 0,
        "avg_bars_in_trades": avg_bars,
        "maior_ganho": maior_ganho,
        "maior_perda": maior_perda,
        "winners": len(ganhos),
        "losers": len(perdas),
        "breakevens": len([t for t in trades if t['pl'] == 0]),

        # Distribuições
        "roi_distribution": roi_distribution,

        # Run-ups e drawdowns
        "avg_runup": avg_runup,
        "avg_drawdown_trade": avg_drawdown_trade,
        "max_runup": round(max(run_ups, default=0), 4),
        "max_drawdown_trade": round(min(drawdowns_list, default=0), 4),

        # Capital efficiency
        "cagr": cagr,
        "account_size_required": account_required,
        "return_on_capital": round(retorno, 2),
        "buy_hold": buy_hold,
        "alpha": round(retorno - buy_hold, 2),

        # Gráficos
        "equity_curve": equity_curve,
        "candles_data": candles[-500:],  # últimos 500 candles
        "markers": markers,

        # Trades completos
        "trades": trades,

        # IA
        "sugestao": sugestao,
    }

def metricas_vazias(capital):
    return {
        "retorno": 0, "win_rate": 0, "sharpe": 0,
        "max_drawdown": 0, "profit_factor": 0,
        "total_trades": 0, "equity_curve": [capital],
        "trades": [], "candles_data": [], "markers": [],
        "sugestao": "Nenhum trade gerado. Verifique os parâmetros da estratégia.",
        "capital_inicial": capital, "capital_final": capital, "lucro_perda": 0,
    }

def gerar_sugestao_ia(wr, sharpe, dd, pf, retorno):
    sugestoes = []
    if retorno < 0:
        sugestoes.append("Resultado negativo. Ajuste o ratio SL/TP — tente TP pelo menos 2x o SL.")
    if wr < 45:
        sugestoes.append(f"Win Rate de {wr:.1f}% está baixo. Considere adicionar um filtro de tendência.")
    if sharpe < 0.5:
        sugestoes.append(f"Sharpe de {sharpe:.2f} indica alta volatilidade. Reduza o tamanho das posições.")
    if abs(dd) > 20:
        sugestoes.append(f"Drawdown de {dd:.1f}% está alto. Reduza o Stop Loss ou use position sizing dinâmico.")
    if pf > 1.5 and retorno > 5:
        sugestoes.append(f"Ótimo resultado! Profit Factor {pf:.2f} e retorno {retorno:.2f}%. Considere otimizar o período do indicador.")
    if not sugestoes:
        sugestoes.append("Resultado sólido. Teste em outros ativos e timeframes para confirmar a robustez.")
    return " | ".join(sugestoes)

# ── ENDPOINTS ───────────────────────────────────────────────

# ── Porteiro: se um NAVEGADOR visitar um endpoint de dados (GET pedindo
#    text/html), redireciona pro app em vez de mostrar JSON cru.
#    fetch() do front pede Accept: */* e continua recebendo JSON normalmente.
_ROTAS_HTML = {"/", "/app", "/docs", "/redoc", "/openapi.json", "/versao", "/offmind/dias-tendencia"}

@app.middleware("http")
async def _redirecionar_navegador(request: Request, call_next):
    try:
        if request.method == "GET" and request.url.path not in _ROTAS_HTML:
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return RedirectResponse(url="/app")
    except Exception:
        pass
    return await call_next(request)


API_VERSAO = "4.0 — Radar IA multilíngue (PT/EN/ES) + Estudo como fonte"

@app.get("/versao")
def versao():
    tem_chave = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    diag = {"api": API_VERSAO,
            "radar_ia_chave": "configurada" if tem_chave else "AUSENTE — adicione ANTHROPIC_API_KEY no Railway",
            "radar_ia_modelo": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
            "cache_analises_memoria": len(_RADAR_IA_CACHE)}
    if tem_chave:
        # teste real da IA: chamada mínima pra validar chave+modelo
        try:
            import httpx
            r = httpx.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"].strip(),
                         "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": diag["radar_ia_modelo"], "max_tokens": 8,
                      "messages": [{"role": "user", "content": "ok"}]},
                timeout=8.0)
            diag["radar_ia_teste"] = "✅ funcionando" if r.status_code == 200 else f"❌ erro {r.status_code}: {r.text[:160]}"
        except Exception as e:
            diag["radar_ia_teste"] = f"❌ exceção: {e}"
    return diag


@app.get("/debug")
def debug_backtest():
    """Roda backtest de diagnóstico e retorna erro completo"""
    from fastapi.responses import PlainTextResponse
    try:
        params = BacktestParams(
            ativo="XAU/USD", periodo="6 meses", timeframe="1d",
            indicador="EMA Channel High/Low", ema_period=20,
            stop_loss=50, take_profit=100, capital=10000,
            max_ops=5, comissao=0.0002
        )
        df = baixar_dados(params.ativo, params.periodo, params.timeframe)
        log = f"✅ Dados baixados: {len(df)} linhas\nColunas: {list(df.columns)}\n\n"
        resultado = rodar_estrategia(df, params)
        log += f"✅ Estratégia rodada: {len(resultado['trades'])} trades\n\n"
        metricas = calcular_metricas_completas(resultado, params, df)
        log += f"✅ Métricas calculadas\nRetorno: {metricas['retorno']}%\n"
        return PlainTextResponse(log)
    except Exception as e:
        return PlainTextResponse(f"❌ ERRO: {str(e)}\n\n{traceback.format_exc()}")

@app.get("/teste")
def teste_conexao():
    """Testa se yfinance consegue baixar dados"""
    try:
        import yfinance as yf
        tk = yf.Ticker("GC=F")
        df = tk.history(period="5d", interval="1d")
        if df.empty:
            return {"status": "erro", "msg": "yfinance retornou dados vazios"}
        return {
            "status": "ok",
            "yfinance_version": yf.__version__,
            "linhas": len(df),
            "colunas": list(df.columns),
            "ultimo_preco": float(df['Close'].iloc[-1]) if 'Close' in df.columns else None
        }
    except Exception as e:
        return {"status": "erro", "msg": str(e), "traceback": traceback.format_exc()}

@app.get("/")
def root():
    # Serve a LANDING PAGE (index.html). O app de backtest foi movido para /app
    if os.path.exists("index.html"):
        return FileResponse("index.html", media_type="text/html")
    return {
        "status": "online",
        "version": "3.0.0",
        "name": "BotBacktest API",
        "endpoints": ["/app", "/backtest/visual", "/backtest/custom", "/gerar-bot-ia",
                      "/exportar/ntsl", "/historico", "/ranking", "/stats"]
    }

@app.get("/app")
def serve_app():
    # Serve o app de backtest (antigo index.html, renomeado para app.html)
    if os.path.exists("app.html"):
        return FileResponse("app.html", media_type="text/html")
    raise HTTPException(404, "app.html nao encontrado")

@app.get("/ativos")
def get_ativos():
    return {"ativos": list(ATIVOS_MAP.keys())}

@app.get("/timeframes")
def get_timeframes():
    return {"timeframes": list(INTERVALOS_MAP.keys())}

@app.get("/indicadores")
def get_indicadores():
    return {"indicadores": ["EMA Channel High/Low","EMA","SMA","RSI","MACD","Bollinger Bands"]}

def converter_para_python(obj):
    """Converte tipos numpy para tipos Python nativos serializáveis"""
    if isinstance(obj, dict):
        return {k: converter_para_python(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [converter_para_python(i) for i in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return [converter_para_python(i) for i in obj.tolist()]
    elif hasattr(obj, 'item'):
        return obj.item()
    return obj

# ── OTIMIZACAO DE PARAMETROS (v1.5) ─────────────────────────
class OtimizarParams(BaseModel):
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    timeframe: str = "1d"
    indicador: str = "EMA Channel High/Low"
    capital: float = 10000
    max_ops: int = 5
    comissao: float = 0.0002
    # intervalos: [inicio, fim, passo]
    stop_loss_range: list = [30, 60, 10]
    take_profit_range: list = [60, 120, 20]
    ema_period_range: list = [20, 20, 1]   # padrao: fixo em 20
    ordenar_por: str = "win_rate"          # win_rate | sharpe | retorno | profit_factor
    user_id: Optional[str] = None
    sessao_id: Optional[str] = None

def _gerar_valores(rng):
    """De [inicio, fim, passo] gera a lista de valores. Seguro contra passo<=0."""
    try:
        ini, fim, passo = float(rng[0]), float(rng[1]), float(rng[2])
    except Exception:
        return []
    if passo <= 0:
        return [ini]
    vals = []
    v = ini
    # +1e-9 para incluir o fim mesmo com float
    while v <= fim + 1e-9:
        vals.append(round(v, 6))
        v += passo
    return vals or [ini]

@app.post("/otimizar")
def otimizar(req: OtimizarParams):
    import sys, copy
    try:
        stops = _gerar_valores(req.stop_loss_range)
        takes = _gerar_valores(req.take_profit_range)
        emas  = [int(x) for x in _gerar_valores(req.ema_period_range)]

        total = len(stops) * len(takes) * len(emas)
        TETO = 50
        if total == 0:
            raise HTTPException(400, "Intervalos invalidos: nenhuma combinacao gerada.")
        if total > TETO:
            raise HTTPException(400, f"{total} combinacoes excedem o teto de {TETO}. Reduza os intervalos ou aumente o passo.")

        # Baixa os dados UMA vez (eficiencia) e reusa em todas as combinacoes
        df_base = baixar_dados(req.ativo, req.periodo, req.timeframe)

        resultados = []
        for sl in stops:
            for tp in takes:
                for ep in emas:
                    p = BacktestParams(
                        ativo=req.ativo, periodo=req.periodo, timeframe=req.timeframe,
                        indicador=req.indicador, ema_period=ep,
                        stop_loss=sl, take_profit=tp,
                        capital=req.capital, max_ops=req.max_ops, comissao=req.comissao,
                        user_id=req.user_id, sessao_id=req.sessao_id,
                    )
                    try:
                        resultado = rodar_estrategia(df_base.copy(), p)
                        m = calcular_metricas_completas(resultado, p, df_base)
                        # alimenta a BabyMachine (non-blocking)
                        salvar_historico_backtest(p, m, user_id=req.user_id, sessao_id=req.sessao_id, codigo="")
                        resultados.append({
                            "stop_loss": sl, "take_profit": tp, "ema_period": ep,
                            "win_rate": m.get("win_rate"), "sharpe": m.get("sharpe"),
                            "retorno": m.get("retorno"), "max_drawdown": m.get("max_drawdown"),
                            "profit_factor": m.get("profit_factor"), "total_trades": m.get("total_trades"),
                        })
                    except Exception as e:
                        print(f"[otimizar] combo sl={sl} tp={tp} ep={ep} falhou: {e}", file=sys.stderr)

        if not resultados:
            raise HTTPException(400, "Nenhuma combinacao produziu resultado valido.")

        # Ordena pelo criterio escolhido (maior melhor; drawdown nao e usado p/ ordenar)
        chave = req.ordenar_por if req.ordenar_por in ("win_rate","sharpe","retorno","profit_factor") else "win_rate"
        resultados.sort(key=lambda r: (r.get(chave) if r.get(chave) is not None else -9e9), reverse=True)

        # Alerta de overfitting: sempre presente, em linguagem honesta
        alerta = ("Estes resultados sao METRICAS DE BACKTEST sobre dados historicos. "
                  "Melhor desempenho no passado NAO garante desempenho futuro. "
                  "A combinacao no topo pode estar superajustada (overfitting) ao historico. "
                  "Antes de confiar, valide a escolhida fora da amostra (out-of-sample) e em outros periodos.")

        return converter_para_python({
            "combinacoes_testadas": len(resultados),
            "ordenado_por": chave,
            "ranking": resultados,
            "melhor": resultados[0],
            "alerta_overfitting": alerta,
        })
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERRO OTIMIZAR: {str(e)}\n{tb}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{tb}")


# ── BABYMACHINE: registro de historico ──────────────────────
def _sb_admin():
    """Cliente Supabase com service_role (ignora RLS) para gravacao."""
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)

def salvar_historico_backtest(params, metricas, user_id=None, sessao_id=None, codigo=""):
    """Grava 1 linha em backtests_historico. NON-BLOCKING: erro nunca quebra o backtest."""
    try:
        sb = _sb_admin()
        if sb is None or not user_id:
            return
        codigo_hash = None
        if codigo and codigo.strip():
            codigo_hash = hashlib.sha256(codigo.strip().encode("utf-8")).hexdigest()[:16]
        parametros = {
            "ema_period": getattr(params, "ema_period", None),
            "stop_loss": getattr(params, "stop_loss", None),
            "take_profit": getattr(params, "take_profit", None),
            "capital": getattr(params, "capital", None),
            "max_ops": getattr(params, "max_ops", None),
            "comissao": getattr(params, "comissao", None),
        }
        linha = {
            "user_id": user_id,
            "ativo": getattr(params, "ativo", None),
            "timeframe": getattr(params, "timeframe", None),
            "periodo": getattr(params, "periodo", None),
            "estrategia_nome": getattr(params, "indicador", None),
            "codigo_hash": codigo_hash,
            "parametros": parametros,
            "retorno": metricas.get("retorno"),
            "win_rate": metricas.get("win_rate"),
            "sharpe": metricas.get("sharpe"),
            "max_drawdown": metricas.get("max_drawdown"),
            "profit_factor": metricas.get("profit_factor"),
            "total_trades": metricas.get("total_trades"),
            "sessao_id": sessao_id or str(_uuid.uuid4()),
            "permite_treino": True,
        }
        sb.table("backtests_historico").insert(linha).execute()
    except Exception as e:
        import sys
        print(f"[BabyMachine] historico nao gravado: {e}", file=sys.stderr)


# ════════════════════════════════════════════════════════════
#  BABYMACHINE — Análise dos dados coletados (regras puras)
#  B: aprendizado coletivo anônimo (banco inteiro)
#  C: detecção de comportamento de risco (jornada do usuário)
#  Sempre honesto: observações estatísticas, nunca promessa de retorno.
# ════════════════════════════════════════════════════════════

class BabyMachineParams(BaseModel):
    user_id: Optional[str] = None
    sessao_id: Optional[str] = None
    ativo: Optional[str] = None       # opcional: focar a análise coletiva num ativo


def _bm_media(vals):
    vals = [v for v in vals if v is not None]
    return (sum(vals)/len(vals)) if vals else None


class BabyMachineContadorParams(BaseModel):
    user_id: Optional[str] = None
    sessao_id: Optional[str] = None


@app.post("/babymachine/contador")
def babymachine_contador(params: BabyMachineContadorParams):
    """Endpoint leve: retorna só o total de backtests do usuário (p/ contador no topo)."""
    try:
        sb = _sb_admin()
        if sb is None:
            return {"total": 0}
        # busca os ids do usuário e conta (sem count=exact, p/ compatibilidade de versão)
        if params.user_id:
            resp = sb.table("backtests_historico").select("id").eq("user_id", params.user_id).limit(10000).execute()
        elif params.sessao_id:
            resp = sb.table("backtests_historico").select("id").eq("sessao_id", params.sessao_id).limit(10000).execute()
        else:
            return {"total": 0}
        total = len(resp.data or [])
        return {"total": total}
    except Exception:
        return {"total": 0}


@app.post("/babymachine/analisar")
def babymachine_analisar(params: BabyMachineParams):
    """Analisa os dados coletados: tendências do banco (B) + comportamento do usuário (C)."""
    import sys
    try:
        sb = _sb_admin()
        if sb is None:
            return {"disponivel": False, "motivo": "Coleta de dados não configurada."}

        # ── B: APRENDIZADO COLETIVO (anônimo) ─────────────────────
        # lê a tabela inteira (sem expor user_id de ninguém)
        try:
            resp = sb.table("backtests_historico").select(
                "ativo,timeframe,stop_loss,take_profit,retorno,win_rate,sharpe,profit_factor,max_drawdown,total_trades,sessao_id,user_id"
            ).limit(5000).execute()
            linhas = resp.data or []
        except Exception:
            # fallback: campos podem estar dentro de 'parametros'
            resp = sb.table("backtests_historico").select("*").limit(5000).execute()
            linhas = resp.data or []

        total_banco = len(linhas)
        coletivo = {"total_backtests": total_banco, "insights": []}

        if total_banco >= 10:
            # tendência 1: take > stop vs take <= stop (qual tem Sharpe médio maior)
            def _sl(r): return r.get("stop_loss") or (r.get("parametros") or {}).get("stop_loss")
            def _tp(r): return r.get("take_profit") or (r.get("parametros") or {}).get("take_profit")
            grupo_tp_maior = [r for r in linhas if _tp(r) and _sl(r) and _tp(r) > _sl(r)]
            grupo_tp_menor = [r for r in linhas if _tp(r) and _sl(r) and _tp(r) <= _sl(r)]
            sh_maior = _bm_media([r.get("sharpe") for r in grupo_tp_maior])
            sh_menor = _bm_media([r.get("sharpe") for r in grupo_tp_menor])
            if sh_maior is not None and sh_menor is not None and len(grupo_tp_maior) >= 5 and len(grupo_tp_menor) >= 5:
                if sh_maior > sh_menor:
                    coletivo["insights"].append(
                        f"Na plataforma, configurações com take maior que o stop tiveram Sharpe médio mais alto "
                        f"({sh_maior:.2f} vs {sh_menor:.2f}) em {len(grupo_tp_maior)+len(grupo_tp_menor)} backtests. "
                        f"Isso sugere 'deixar o lucro correr' — mas é observação do passado, valide na sua estratégia."
                    )
                else:
                    coletivo["insights"].append(
                        f"Curiosamente, na plataforma o take maior que o stop NÃO teve vantagem de Sharpe "
                        f"({sh_maior:.2f} vs {sh_menor:.2f}). Cada mercado é diferente — teste no seu ativo."
                    )

            # tendência 2: ativo mais testado
            from collections import Counter
            ativos = Counter([r.get("ativo") for r in linhas if r.get("ativo")])
            if ativos:
                mais, qtd = ativos.most_common(1)[0]
                coletivo["insights"].append(f"O ativo mais testado na plataforma é {mais} ({qtd} backtests).")

            # tendência 3: sharpe médio geral (referência honesta)
            sh_geral = _bm_media([r.get("sharpe") for r in linhas])
            wr_geral = _bm_media([r.get("win_rate") for r in linhas])
            if sh_geral is not None:
                coletivo["insights"].append(
                    f"Sharpe médio de todos os backtests da plataforma: {sh_geral:.2f}"
                    + (f" · Win rate médio: {wr_geral:.1f}%" if wr_geral is not None else "")
                    + ". A maioria das estratégias fica perto da média — vantagem real é rara."
                )
        else:
            coletivo["insights"].append("Ainda há poucos dados na plataforma para tendências coletivas confiáveis. Volte em breve.")

        # ── C: COMPORTAMENTO DO USUÁRIO ──────────────────────────
        comportamento = {"disponivel": False, "alertas": [], "resumo": "", "evolucao": []}
        minha_jornada = []
        if params.user_id:
            minha_jornada = [r for r in linhas if r.get("user_id") == params.user_id]
            escopo = "histórico completo"
        elif params.sessao_id:
            minha_jornada = [r for r in linhas if r.get("sessao_id") == params.sessao_id]
            escopo = "sessão atual"
        else:
            escopo = None

        # ordena cronologicamente (created_at se existir, senão mantém ordem do banco)
        try:
            minha_jornada = sorted(minha_jornada, key=lambda r: (r.get("created_at") or ""))
        except Exception:
            pass

        if minha_jornada and len(minha_jornada) >= 2:
            comportamento["disponivel"] = True
            n = len(minha_jornada)
            comportamento["resumo"] = f"Analisei {n} backtests seus ({escopo})."

            # série de evolução p/ os 2 gráficos (Sharpe e Retorno ao longo dos testes)
            comportamento["evolucao"] = [
                {
                    "i": idx + 1,
                    "ativo": r.get("ativo"),
                    "timeframe": r.get("timeframe"),
                    "sharpe": r.get("sharpe"),
                    "retorno": r.get("retorno"),
                }
                for idx, r in enumerate(minha_jornada)
            ]

            # alerta 1: muitos testes mudando só o stop/take (sinal de overfitting manual)
            def _sl(r): return r.get("stop_loss") or (r.get("parametros") or {}).get("stop_loss")
            def _tp(r): return r.get("take_profit") or (r.get("parametros") or {}).get("take_profit")
            ativos_testados = set(r.get("ativo") for r in minha_jornada)
            if n >= 6 and len(ativos_testados) == 1:
                comportamento["alertas"].append({
                    "nivel": "alto",
                    "texto": f"Você rodou {n} backtests no mesmo ativo ({list(ativos_testados)[0]}) ajustando parâmetros. "
                             f"Cuidado: buscar o 'número perfeito' no histórico é a definição de overfitting. "
                             f"Valide a melhor configuração na aba Robustez (out-of-sample)."
                })

            # alerta 2: nunca testou em mais de um timeframe
            tfs = set(r.get("timeframe") for r in minha_jornada if r.get("timeframe"))
            if n >= 4 and len(tfs) == 1:
                comportamento["alertas"].append({
                    "nivel": "medio",
                    "texto": f"Todos os seus testes foram no timeframe {list(tfs)[0]}. "
                             f"Uma estratégia robusta costuma funcionar em mais de um timeframe — experimente variar."
                })

            # alerta 3: melhor sharpe da jornada
            melhor = max(minha_jornada, key=lambda r: (r.get("sharpe") or -999))
            if melhor.get("sharpe") is not None:
                comportamento["alertas"].append({
                    "nivel": "info",
                    "texto": f"Seu melhor backtest até agora: {melhor.get('ativo')} "
                             f"(stop {_sl(melhor)}/take {_tp(melhor)}), Sharpe {melhor.get('sharpe'):.2f}, "
                             f"retorno {melhor.get('retorno')}%. Que tal validar a robustez dele?"
                })

            # alerta 4: win rate alto com retorno negativo (a armadilha clássica)
            armadilha = [r for r in minha_jornada
                         if (r.get("win_rate") or 0) >= 55 and (r.get("retorno") or 0) < 0]
            if armadilha:
                comportamento["alertas"].append({
                    "nivel": "alto",
                    "texto": f"Você teve {len(armadilha)} teste(s) com win rate alto (≥55%) MAS retorno negativo. "
                             f"Lembre: ganhar muitas vezes não é o mesmo que lucrar. O tamanho dos ganhos/perdas importa mais."
                })
        elif escopo:
            comportamento["resumo"] = "Rode mais alguns backtests para a BabyMachine analisar sua jornada."

        return converter_para_python({
            "disponivel": True,
            "coletivo": coletivo,
            "comportamento": comportamento,
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERRO BABYMACHINE: {str(e)}\n{tb}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{str(e)}")



class ValidarOverfittingParams(BaseModel):
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    timeframe: str = "1d"
    indicador: str = "EMA Channel High/Low"
    capital: float = 10000
    max_ops: int = 5
    comissao: float = 0.0002
    ema_period: int = 20
    stop_loss: float = 50
    take_profit: float = 100
    split: float = 0.70   # fração de treino (resto = teste)
    codigo: str = ""      # se vier, valida o CÓDIGO do cliente (não o indicador)
    user_id: Optional[str] = None
    sessao_id: Optional[str] = None


def _metricas_simples(df_slice, base_params):
    """Roda a estratégia num pedaço do df e devolve só as métricas-chave.
    Se base_params tiver código custom, roda o CÓDIGO do cliente (mesmo motor
    do /backtest/custom); senão, roda pelo indicador."""
    codigo = (getattr(base_params, "codigo", "") or "").strip()
    if codigo and not codigo.startswith("#"):
        resultado = rodar_codigo_custom(df_slice, base_params)
    else:
        resultado = rodar_estrategia(df_slice, base_params)
    m = calcular_metricas_completas(resultado, base_params, df_slice)
    return {
        "retorno": float(m.get("retorno") or 0),
        "win_rate": float(m.get("win_rate") or 0),
        "sharpe": float(m.get("sharpe") or 0),
        "profit_factor": float(m.get("profit_factor") or 0),
        "max_drawdown": float(m.get("max_drawdown") or 0),
        "total_trades": int(m.get("total_trades") or 0),
    }


@app.post("/validar-overfitting")
def validar_overfitting(params: ValidarOverfittingParams):
    """
    Out-of-sample (treino/teste). Roda a MESMA estratégia em duas partes do
    histórico: treino (primeiros split%) e teste (resto, dados 'nunca vistos').
    Compara e dá um veredito honesto sobre robustez x overfitting.
    """
    import sys
    try:
        # 1) baixa os dados uma vez
        df = baixar_dados(params.ativo, params.periodo, params.timeframe)
        if df is None or len(df) < 60:
            raise HTTPException(status_code=400, detail="Dados insuficientes para dividir em treino/teste (mínimo ~60 candles).")

        # 2) fatia cronológica: treino primeiro, teste depois (NUNCA embaralhar série temporal)
        split = params.split if 0.5 <= params.split <= 0.9 else 0.70
        corte = int(len(df) * split)
        df_treino = df.iloc[:corte].copy()
        df_teste = df.iloc[corte:].copy()
        if len(df_treino) < 30 or len(df_teste) < 20:
            raise HTTPException(status_code=400, detail="Período curto demais para um teste out-of-sample confiável. Use um período maior.")

        # 3) parâmetros idênticos nas duas fatias
        _cod = (params.codigo or "").strip()
        _campos = dict(
            ativo=params.ativo, periodo=params.periodo, timeframe=params.timeframe,
            indicador=params.indicador, capital=params.capital, max_ops=params.max_ops,
            comissao=params.comissao, ema_period=params.ema_period,
            stop_loss=params.stop_loss, take_profit=params.take_profit,
        )
        if _cod and not _cod.startswith("#"):
            bp = BacktestCustom(**_campos, codigo=params.codigo)
        else:
            bp = BacktestParams(**_campos)

        treino = _metricas_simples(df_treino, bp)
        teste = _metricas_simples(df_teste, bp)

        # 4) veredito honesto
        veredito = _avaliar_overfitting(treino, teste)

        return converter_para_python({
            "ativo": params.ativo,
            "split": split,
            "candles_treino": len(df_treino),
            "candles_teste": len(df_teste),
            "treino": treino,
            "teste": teste,
            "veredito": veredito,
        })
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERRO VALIDAR-OVERFITTING: {str(e)}\n{tb}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{str(e)}")


def _avaliar_overfitting(treino: dict, teste: dict) -> dict:
    """
    Decide se a estratégia parece robusta ou superajustada, comparando o
    desempenho de treino com o de teste (out-of-sample). Sempre honesto:
    nunca promete retorno futuro, só sinaliza fragilidade.
    """
    ret_tr = treino["retorno"]
    ret_te = teste["retorno"]
    sh_tr = treino["sharpe"]
    sh_te = teste["sharpe"]
    pf_te = teste["profit_factor"]
    trades_te = teste["total_trades"]

    motivos = []
    # sinais de overfitting
    if ret_tr > 0 and ret_te <= 0:
        motivos.append("Lucro no treino virou prejuízo (ou zero) no teste.")
    if sh_tr > 0 and sh_te < 0:
        motivos.append("Sharpe positivo no treino ficou negativo no teste.")
    # queda relativa grande de retorno (quando o treino foi positivo)
    if ret_tr > 0:
        queda = (ret_tr - ret_te) / abs(ret_tr) if ret_tr != 0 else 0
        if queda >= 0.6 and ret_te < ret_tr:
            motivos.append("Desempenho caiu mais de 60% do treino para o teste.")
    # poucos trades no teste = amostra pequena, pouco confiável
    if trades_te < 10:
        motivos.append(f"Apenas {trades_te} operações no teste — amostra pequena, resultado pouco confiável.")

    # sinais de robustez
    robusto = (ret_te > 0 and sh_te > 0 and pf_te >= 1.0)

    if len(motivos) >= 2 or (ret_tr > 0 and ret_te <= 0):
        nivel = "alto"
        titulo = "Sinais de overfitting"
        resumo = "A estratégia foi bem no passado conhecido, mas tropeçou nos dados que nunca viu. Cuidado: pode estar ajustada demais ao histórico."
    elif motivos:
        nivel = "medio"
        titulo = "Atenção"
        resumo = "Há sinais de fragilidade entre treino e teste. Vale investigar antes de confiar."
    elif robusto:
        nivel = "baixo"
        titulo = "Mais robusta"
        resumo = "A estratégia manteve desempenho positivo nos dados que nunca viu. É um bom sinal — mas backtest nunca garante o futuro."
    else:
        nivel = "medio"
        titulo = "Resultado misto"
        resumo = "O comportamento entre treino e teste não é claramente bom nem ruim. Teste em mais períodos e ativos."

    return {"nivel": nivel, "titulo": titulo, "resumo": resumo, "motivos": motivos}


# ════════════════════════════════════════════════════════════
#  OFFMIND — Engine de detecção de padrões (Association Rules)
#  Filosofia: detectar padrões no histórico e medir HONESTAMENTE
#  (acerto E falha). Nunca promete retorno futuro.
# ════════════════════════════════════════════════════════════

def calcular_atr(df, period=14):
    """Average True Range — mede a volatilidade recente. Usado p/ alvo e stop."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()

# ── DETECTORES DE PADRÃO ──────────────────────────────────────
# Cada detector recebe o df e retorna lista de (índice, direção_esperada).
# direção: "alta" (espera subir) ou "baixa" (espera cair).
# Plugar um padrão novo = escrever uma função aqui e registrar em PADROES_OFFMIND.

def _corpo(o, c):       # tamanho do corpo da vela
    return abs(c - o)

def det_engolfo_alta(df):
    """Candle verde cujo corpo engole o corpo do candle vermelho anterior."""
    o, c = df['Open'].values, df['Close'].values
    out = []
    for i in range(1, len(df)):
        prev_baixa = c[i-1] < o[i-1]           # vela anterior vermelha
        atual_alta = c[i] > o[i]               # vela atual verde
        engole = (o[i] <= c[i-1]) and (c[i] >= o[i-1])
        if prev_baixa and atual_alta and engole and _corpo(o[i],c[i]) > _corpo(o[i-1],c[i-1]):
            out.append((i, "alta"))
    return out

def det_engolfo_baixa(df):
    """Candle vermelho que engole o corpo do verde anterior."""
    o, c = df['Open'].values, df['Close'].values
    out = []
    for i in range(1, len(df)):
        prev_alta = c[i-1] > o[i-1]
        atual_baixa = c[i] < o[i]
        engole = (o[i] >= c[i-1]) and (c[i] <= o[i-1])
        if prev_alta and atual_baixa and engole and _corpo(o[i],c[i]) > _corpo(o[i-1],c[i-1]):
            out.append((i, "baixa"))
    return out

def det_martelo(df):
    """Pin bar de baixo: pavio inferior longo, corpo pequeno no topo → reversão p/ cima."""
    o, c, h, l = df['Open'].values, df['Close'].values, df['High'].values, df['Low'].values
    out = []
    for i in range(len(df)):
        rng = h[i] - l[i]
        if rng <= 0: continue
        corpo = _corpo(o[i], c[i])
        pavio_inf = min(o[i], c[i]) - l[i]
        pavio_sup = h[i] - max(o[i], c[i])
        if corpo <= rng*0.35 and pavio_inf >= rng*0.5 and pavio_sup <= rng*0.2:
            out.append((i, "alta"))
    return out

def det_estrela_cadente(df):
    """Pin bar de cima: pavio superior longo → reversão p/ baixo."""
    o, c, h, l = df['Open'].values, df['Close'].values, df['High'].values, df['Low'].values
    out = []
    for i in range(len(df)):
        rng = h[i] - l[i]
        if rng <= 0: continue
        corpo = _corpo(o[i], c[i])
        pavio_inf = min(o[i], c[i]) - l[i]
        pavio_sup = h[i] - max(o[i], c[i])
        if corpo <= rng*0.35 and pavio_sup >= rng*0.5 and pavio_inf <= rng*0.2:
            out.append((i, "baixa"))
    return out

def det_tres_verdes(df):
    """3 velas verdes seguidas → mede se continua ou exausta."""
    o, c = df['Open'].values, df['Close'].values
    out = []
    for i in range(2, len(df)):
        if c[i]>o[i] and c[i-1]>o[i-1] and c[i-2]>o[i-2]:
            out.append((i, "alta"))
    return out

def det_tres_vermelhas(df):
    """3 velas vermelhas seguidas."""
    o, c = df['Open'].values, df['Close'].values
    out = []
    for i in range(2, len(df)):
        if c[i]<o[i] and c[i-1]<o[i-1] and c[i-2]<o[i-2]:
            out.append((i, "baixa"))
    return out

PADROES_OFFMIND = {
    "engolfo_alta":    {"fn": det_engolfo_alta,    "nome": "Engolfo de alta",        "categoria": "candle"},
    "engolfo_baixa":   {"fn": det_engolfo_baixa,   "nome": "Engolfo de baixa",       "categoria": "candle"},
    "martelo":         {"fn": det_martelo,         "nome": "Martelo (pin bar alta)", "categoria": "candle"},
    "estrela_cadente": {"fn": det_estrela_cadente, "nome": "Estrela cadente (pin bar baixa)", "categoria": "candle"},
    "tres_verdes":     {"fn": det_tres_verdes,     "nome": "3 velas verdes",         "categoria": "candle"},
    "tres_vermelhas":  {"fn": det_tres_vermelhas,  "nome": "3 velas vermelhas",      "categoria": "candle"},
}

# ── ENGINE GENÉRICA DE MEDIÇÃO ────────────────────────────────
def _medir_ocorrencia(df, atr, i, direcao, velas_frente, atr_mult_alvo, atr_mult_stop):
    """
    A partir da ocorrência no índice i, simula entrada no fechamento da vela i
    com alvo/stop baseados em ATR, olhando até `velas_frente` velas à frente.
    Retorna: 'acerto' (bateu alvo antes do stop), 'falha' (bateu stop antes),
    'neutro' (não bateu nenhum no horizonte) e o movimento % no fim do horizonte.
    """
    entrada = float(df['Close'].iloc[i])
    a = float(atr.iloc[i]) if atr.iloc[i] == atr.iloc[i] else 0.0  # NaN-safe
    if a <= 0 or entrada <= 0:
        return None
    if direcao == "alta":
        alvo = entrada + atr_mult_alvo * a
        stop = entrada - atr_mult_stop * a
    else:
        alvo = entrada - atr_mult_alvo * a
        stop = entrada + atr_mult_stop * a

    fim = min(i + velas_frente, len(df) - 1)
    resultado = "neutro"
    for j in range(i+1, fim+1):
        hi = float(df['High'].iloc[j]); lo = float(df['Low'].iloc[j])
        if direcao == "alta":
            bateu_alvo = hi >= alvo
            bateu_stop = lo <= stop
        else:
            bateu_alvo = lo <= alvo
            bateu_stop = hi >= stop
        # se ambos no mesmo candle, assume pior caso (stop primeiro) p/ ser conservador
        if bateu_stop:
            resultado = "falha"; break
        if bateu_alvo:
            resultado = "acerto"; break
    preco_fim = float(df['Close'].iloc[fim])
    mov_pct = (preco_fim - entrada)/entrada*100
    if direcao == "baixa":
        mov_pct = -mov_pct   # p/ baixa, mov favorável é queda
    return {"resultado": resultado, "mov_pct": mov_pct}

def analisar_padrao(df, detector, horizontes, atr_mult_alvo=2.0, atr_mult_stop=1.0):
    """Engine genérica: roda o detector e mede o resultado em vários horizontes."""
    atr = calcular_atr(df)
    ocorrencias = detector(df)
    total = len(ocorrencias)
    por_horizonte = []
    for h in horizontes:
        acertos = falhas = neutros = 0
        movs = []
        for (i, direcao) in ocorrencias:
            if i >= len(df)-1:
                continue
            r = _medir_ocorrencia(df, atr, i, direcao, h, atr_mult_alvo, atr_mult_stop)
            if r is None:
                continue
            movs.append(r["mov_pct"])
            if r["resultado"] == "acerto": acertos += 1
            elif r["resultado"] == "falha": falhas += 1
            else: neutros += 1
        validos = acertos + falhas + neutros
        decididos = acertos + falhas
        taxa_acerto = (acertos/decididos*100) if decididos > 0 else 0.0
        taxa_falha = (falhas/decididos*100) if decididos > 0 else 0.0
        mov_medio = (sum(movs)/len(movs)) if movs else 0.0
        por_horizonte.append({
            "horizonte": h,
            "ocorrencias_medidas": validos,
            "acertos": acertos,
            "falhas": falhas,
            "neutros": neutros,
            "taxa_acerto": round(taxa_acerto, 2),
            "taxa_falha": round(taxa_falha, 2),
            "mov_medio_pct": round(mov_medio, 3),
        })
    return {"total_ocorrencias": total, "por_horizonte": por_horizonte}


class OffMindParams(BaseModel):
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    timeframe: str = "1d"
    padrao: str = "engolfo_alta"        # chave em PADROES_OFFMIND, ou "todos"
    horizontes: list = [3, 5, 10, 20]
    atr_mult_alvo: float = 2.0
    atr_mult_stop: float = 1.0
    user_id: Optional[str] = None
    sessao_id: Optional[str] = None


# ── MATRIZ ESTRATEGIA x TIMEFRAME (v3.8: recurso de plano, dentro do app) ──
# No lancamento do Elite: deixar apenas {"elite"} aqui (1 linha)
PLANOS_MATRIZ = {"elite", "trader_pro"}
_MATRIZ_CACHE = {}          # ativo -> (timestamp, resultado) — Radar consulta isso
_MATRIZ_CACHE_TTL = 86400   # 24h

class MatrizParams(BaseModel):
    ativo: str = "XAU/USD"
    tfs: str = "1d,4h,1h,30m,15m"
    periodo: str = "2 anos"
    idioma: str = "pt"
    user_id: str = ""

def _plano_vigente(plano, ate):
    """Cortesia com prazo: se o plano não é free e a data de validade já passou,
       trata como free. Assinatura paga do Stripe não tem data -> nunca expira aqui."""
    try:
        if plano and plano != "free" and ate:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(str(ate).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < datetime.now(timezone.utc):
                return "free"
    except Exception:
        pass
    return plano or "free"


def _plano_usuario(user_id: str) -> str:
    try:
        sb = _sb_admin()
        if sb is None:
            return "free"
        try:
            r = sb.table("perfis").select("plano,plano_valido_ate").eq("id", user_id).single().execute()
            d = r.data or {}
            return _plano_vigente(d.get("plano"), d.get("plano_valido_ate"))
        except Exception:
            r = sb.table("perfis").select("plano").eq("id", user_id).single().execute()
            return (r.data or {}).get("plano") or "free"
    except Exception:
        return "free"

def _matriz_calcular(ativo: str, lista_tfs: list, periodo: str = "2 anos", lang: str = "pt") -> dict:
    import time as _t
    inicio = _t.time()
    dfs = {}
    for tf in lista_tfs:
        try:
            dfs[tf] = baixar_dados(ativo, periodo, tf)
        except Exception:
            dfs[tf] = None
    linhas = []
    ranking = []
    for est in ESTRATEGIAS_PRONTAS:
        cels = {}
        for tf in lista_tfs:
            df = dfs.get(tf)
            if df is None or len(df) < 60:
                cels[tf] = None
                continue
            try:
                params = BacktestCustom(
                    ativo=ativo, periodo=periodo, timeframe=tf,
                    indicador=est["nome"], ema_period=20,
                    stop_loss=50, take_profit=100, capital=10000,
                    max_ops=5, comissao=0.0002, codigo=est["codigo"])
                r = rodar_codigo_custom(df, params)
                met = calcular_metricas_completas(r, params, df)
                cel = {"retorno": float(met.get("retorno") or 0),
                       "pf": float(met.get("profit_factor") or 0),
                       "wr": float(met.get("win_rate") or 0),
                       "sharpe": float(met.get("sharpe") or 0),
                       "trades": int(met.get("total_trades") or 0)}
                cel["forca"] = ("forte" if (cel["pf"] >= 1.15 and cel["trades"] >= 30 and cel["sharpe"] > 0.5)
                                else ("ok" if (cel["pf"] > 1 and cel["trades"] >= 20) else "fraca"))
                cels[tf] = cel
                if cel["trades"] >= 20 and cel["pf"] > 1:
                    ranking.append({"estrategia": _estrat_loc(est, lang, "nome"), "id": est["id"], "emoji": est.get("emoji", ""),
                                    "tf": tf, **cel})
            except Exception:
                cels[tf] = None
        linhas.append({"nome": _estrat_loc(est, lang, "nome"), "id": est["id"], "emoji": est.get("emoji", ""),
                       "casa": bool(est.get("casa")), "cels": cels})
    ranking.sort(key=lambda x: x["sharpe"], reverse=True)
    resultado = {"ativo": ativo, "tfs": lista_tfs, "linhas": linhas,
                 "tops": ranking[:10], "duracao_s": round(_t.time() - inicio)}
    _MATRIZ_CACHE[f"{ativo}|{periodo}"] = (_t.time(), resultado)
    if len(_MATRIZ_CACHE) > 20:
        _MATRIZ_CACHE.pop(next(iter(_MATRIZ_CACHE)))
    return resultado

@app.post("/offmind/matriz-dados")
def offmind_matriz_dados(p: MatrizParams):
    """Estudo Estrategia x Timeframe — recurso do plano topo, chamado pela aba Estudo."""
    plano = _plano_usuario(p.user_id) if p.user_id else "free"
    if plano not in PLANOS_MATRIZ:
        return JSONResponse(status_code=403, content={
            "erro": "Recurso exclusivo do plano profissional.",
            "upgrade": True, "plano_atual": plano})
    lista_tfs = [t.strip() for t in p.tfs.split(",") if t.strip() in INTERVALOS_MAP]
    if not lista_tfs:
        lista_tfs = ["1d", "1h"]
    return _matriz_calcular(p.ativo, lista_tfs, p.periodo, p.idioma)


@app.get("/offmind/dias-tendencia", response_class=HTMLResponse)
def offmind_dias_tendencia(ativo: str = "XAU/USD", periodo: str = "2 anos",
                           corpo_min: float = 0.65, range_atr: float = 1.0):
    """Raio-X de dias de tendencia: quantos dias o ativo passou o dia inteiro
    numa direcao so (corpo dominante + range relevante). Pagina HTML simples."""
    try:
        df = baixar_dados(ativo, periodo, "1d")
        if df is None or len(df) < 30:
            return HTMLResponse("<h3>Dados insuficientes</h3>")
        h, l, c, o = df["High"], df["Low"], df["Close"], df["Open"]
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        rng = (h - l)
        corpo = (c - o).abs()
        frac = corpo / rng.replace(0, np.nan)
        cond = (frac >= corpo_min) & (rng >= range_atr * atr)
        alta = cond & (c > o)
        baixa = cond & (c < o)
        n = len(df.dropna(subset=["Close"]))
        na, nb = int(alta.sum()), int(baixa.sum())
        nt = na + nb
        rng_medio = float(rng[cond].mean()) if nt else 0.0
        rng_medio_pct = float((rng[cond] / c[cond]).mean() * 100) if nt else 0.0
        rng_normal = float(rng[~cond].mean()) if (n - nt) else 0.0
        # top 5 maiores dias direcionais
        tops = rng[cond].sort_values(ascending=False).head(5)
        linhas_top = "".join(
            f"<tr><td>{str(ix)[:10]}</td><td>{'⬆️ alta' if bool(alta.loc[ix]) else '⬇️ baixa'}</td>"
            f"<td>${rng.loc[ix]:,.2f}</td><td>{frac.loc[ix]*100:.0f}%</td></tr>"
            for ix in tops.index)
        # sequência mais longa de dias direcionais seguidos (qualquer direção)
        seq = melhor_seq = 0
        for v in cond.fillna(False).values:
            seq = seq + 1 if v else 0
            melhor_seq = max(melhor_seq, seq)
        freq = nt / n * 100 if n else 0
        html = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Dias de Tendência — {ativo}</title>
<style>body{{background:#0a0f14;color:#e8ecf1;font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.7}}
h1{{color:#00d084;font-size:22px}} .big{{font-size:38px;font-weight:800;color:#00d084}}
table{{border-collapse:collapse;width:100%;margin:14px 0}} td,th{{border:1px solid #243240;padding:8px 12px;font-size:14px;text-align:left}}
th{{background:#121a23;color:#9fb0c0}} .muted{{color:#9fb0c0;font-size:13px}}
.card{{background:#121a23;border:1px solid #243240;border-radius:12px;padding:18px 22px;margin:14px 0}}</style></head><body>
<h1>📊 Raio-X de Dias de Tendência — {ativo} (D1, {periodo})</h1>
<div class='card'><div class='muted'>Dias em que o mercado passou <b>o dia inteiro numa direção só</b><br>
(critério: corpo ≥ {corpo_min*100:.0f}% do range e range ≥ {range_atr:g}× ATR14)</div>
<div class='big'>{nt} de {n} dias &nbsp;({freq:.1f}%)</div>
<div>⬆️ Subindo o dia todo: <b>{na} dias</b> &nbsp;·&nbsp; ⬇️ Caindo o dia todo: <b>{nb} dias</b></div>
<div>≈ <b>{nt/24:.1f} dias por mês</b> · maior sequência seguida: <b>{melhor_seq} dias</b></div></div>
<div class='card'><b>Tamanho do movimento nesses dias:</b><br>
Range médio do dia direcional: <b>${rng_medio:,.2f}</b> ({rng_medio_pct:.2f}% do preço)<br>
<span class='muted'>vs ${rng_normal:,.2f} nos dias normais — o dia de tendência rende {rng_medio/rng_normal:.1f}× mais movimento</span></div>
<div class='card'><b>🏆 Top 5 maiores dias direcionais:</b>
<table><tr><th>Data</th><th>Direção</th><th>Range do dia</th><th>Corpo/Range</th></tr>{linhas_top}</table></div>
<p class='muted'>Medição histórica do OffMind · critério conservador e transparente · histórico medido, não promessa.
Experimente outros ativos: <code>?ativo=BTC/USD</code>, <code>?ativo=EUR/USD</code> · ajuste o rigor: <code>&corpo_min=0.7</code></p>
</body></html>"""
        return HTMLResponse(html)
    except Exception as e:
        import traceback as tb
        return HTMLResponse(f"<pre>Erro: {e}\n{tb.format_exc()[:500]}</pre>")


@app.get("/offmind/padroes")
def offmind_listar_padroes():
    """Lista os padrões disponíveis na engine."""
    return {"padroes": [
        {"chave": k, "nome": v["nome"], "categoria": v["categoria"]}
        for k, v in PADROES_OFFMIND.items()
    ]}


@app.post("/offmind/analisar")
def offmind_analisar(params: OffMindParams):
    """Detecta padrão(ões) no histórico e mede acerto/falha em vários horizontes."""
    import sys
    try:
        df = baixar_dados(params.ativo, params.periodo, params.timeframe)
        if df is None or len(df) < 40:
            raise HTTPException(status_code=400, detail="Dados insuficientes para análise de padrões.")

        horizontes = [int(h) for h in (params.horizontes or [3,5,10,20]) if int(h) > 0][:6] or [3,5,10,20]
        alvo = params.atr_mult_alvo if params.atr_mult_alvo > 0 else 2.0
        stop = params.atr_mult_stop if params.atr_mult_stop > 0 else 1.0

        if params.padrao == "todos":
            chaves = list(PADROES_OFFMIND.keys())
        elif params.padrao in PADROES_OFFMIND:
            chaves = [params.padrao]
        else:
            raise HTTPException(status_code=400, detail=f"Padrão desconhecido: {params.padrao}")

        resultados = []
        for k in chaves:
            meta = PADROES_OFFMIND[k]
            r = analisar_padrao(df, meta["fn"], horizontes, alvo, stop)
            resultados.append({
                "chave": k, "nome": meta["nome"], "categoria": meta["categoria"],
                "total_ocorrencias": r["total_ocorrencias"],
                "por_horizonte": r["por_horizonte"],
            })

        return converter_para_python({
            "ativo": params.ativo,
            "periodo": params.periodo,
            "timeframe": params.timeframe,
            "candles_analisados": len(df),
            "atr_mult_alvo": alvo,
            "atr_mult_stop": stop,
            "resultados": resultados,
        })
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERRO OFFMIND: {str(e)}\n{tb}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{str(e)}")


class RadarAnalisarParams(BaseModel):
    ativo: str = "XAU/USD"
    periodo: str = "2 anos"
    timeframe: str = "1d"
    user_id: Optional[str] = None
    sessao_id: Optional[str] = None
    indicador_atual: Optional[str] = None
    ema_period_atual: Optional[int] = None
    estrategia_id_atual: Optional[str] = None     # id da estratégia pronta em execução (modo código)
    estrategia_nome_atual: Optional[str] = None
    esperado: Optional[dict] = None               # números indicados quando o usuário clicou "Testar X"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None
    retorno: Optional[float] = None
    max_drawdown: Optional[float] = None
    capital: Optional[float] = None
    max_ops: Optional[int] = None
    idioma: Optional[str] = "pt"


# Mapa: classe de padrão dominante -> indicador + gatilho de entrada sugeridos
_RADAR_SUGESTOES = {
    "reversao_alta": {
        "indicador": "Bollinger Bands", "ema_period": 20,
        "gatilho": "comprar quando o preço toca a banda inferior e fecha um candle de reversão (martelo/engolfo de alta)",
    },
    "reversao_baixa": {
        "indicador": "Bollinger Bands", "ema_period": 20,
        "gatilho": "operar reversões: preço esticado na banda superior + candle de rejeição costuma devolver",
    },
    "continuacao": {
        "indicador": "EMA Channel High/Low", "ema_period": 20,
        "gatilho": "entrar no rompimento do canal a favor da sequência (preço fecha fora do canal na direção do movimento)",
    },
}
_RADAR_CLASSES = {
    "engolfo_alta": "reversao_alta", "martelo": "reversao_alta",
    "engolfo_baixa": "reversao_baixa", "estrela_cadente": "reversao_baixa",
    "tres_verdes": "continuacao", "tres_vermelhas": "continuacao",
}


# ── Cache de análises do Radar IA ──
# Mesmo teste (config + métricas idênticas) = mesma análise, sem pagar de novo.
# Camada 1: memória do processo. Camada 2: Supabase (persiste entre deploys).
_RADAR_IA_CACHE = {}
_RADAR_IA_CACHE_TTL = 7 * 24 * 3600   # 7 dias
_RADAR_IA_CACHE_MAX = 500

def _radar_cache_chave(base: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]

def _radar_cache_get(chave: str):
    import time as _t, sys
    hit = _RADAR_IA_CACHE.get(chave)
    if hit and (_t.time() - hit[0]) < _RADAR_IA_CACHE_TTL:
        return hit[1]
    try:
        sb = _sb_admin()
        if sb is not None:
            r = sb.table("radar_analises_cache").select("mensagens,criado_em").eq("chave", chave).limit(1).execute()
            if r.data:
                from datetime import timezone
                criado = r.data[0].get("criado_em", "")
                msgs = r.data[0].get("mensagens")
                if isinstance(msgs, list) and msgs:
                    _RADAR_IA_CACHE[chave] = (_t.time(), msgs)
                    return msgs
    except Exception as e:
        print(f"RADAR cache get: {e}", file=sys.stderr)
    return None

def _radar_cache_set(chave: str, msgs: list):
    import time as _t, sys
    if len(_RADAR_IA_CACHE) >= _RADAR_IA_CACHE_MAX:
        _RADAR_IA_CACHE.pop(next(iter(_RADAR_IA_CACHE)), None)
    _RADAR_IA_CACHE[chave] = (_t.time(), msgs)
    try:
        sb = _sb_admin()
        if sb is not None:
            sb.table("radar_analises_cache").upsert(
                {"chave": chave, "mensagens": msgs}, on_conflict="chave").execute()
    except Exception as e:
        print(f"RADAR cache set: {e}", file=sys.stderr)


_IDIOMA_NOME = {"pt": "português brasileiro", "en": "English (US)", "es": "español"}

# ── REDE DE SEGURANÇA DO RADAR ──────────────────────────────────────────
# A Opção B deixa a Haiku redigir livre. Esta rede varre o texto ANTES de sair
# atrás de linguagem de PROMESSA (lucro futuro / garantia / certeza). Se acender,
# a resposta da IA é descartada e o Radar usa os templates de regra (seguros por
# construção). Conservador de propósito: NÃO barra estatística histórica
# (PF, win rate medidos são permitidos) — só promessa de retorno futuro e certeza.
import re as _re_radar
_RADAR_PROMESSA_PADROES = [
    # PT — promessa de lucro/retorno futuro e garantias
    r"\b(vai|ir[áa]|vais)\s+(te\s+)?(dar|gerar|render|trazer)\s+(lucro|dinheiro|ganho)",
    r"\bvoc[êe]\s+(vai|ir[áa])\s+(lucrar|ganhar|faturar|enriquecer)",
    r"\b(lucro|retorno|ganho|resultado)\s+(garantido|garantida|certo|certa|assegurado)",
    r"\bgarant(e|ia|ido|ida|imos|o)\b[^.]{0,40}\b(lucro|retorno|ganho|resultado|sucesso)",
    r"\b(com\s+certeza|certamente|sem\s+d[úu]vida\s+nenhuma)\s+(vai|ir[áa]|voc[êe])",
    r"\b100\s*%\s+de\s+(acerto|acertos|sucesso|ganho|lucro)",
    r"\bn[ãa]o\s+tem\s+como\s+(perder|dar\s+errado|errar)",
    r"\b(dinheiro|lucro)\s+(f[áa]cil|garantido|certo)",
    # EN
    r"\bguaranteed\s+(profit|return|gains?|money|win|success)",
    r"\byou\s*('| wi)ll\s+(profit|make\s+money|win|earn|get\s+rich)",
    r"\b100\s*%\s+(win|accuracy|success|profit)",
    r"\bcan\s*('| ?no)t\s+lose",
    r"\bsure\s+(thing|profit|win|bet)",
    # ES
    r"\bganancia\s+(garantizada|segura|asegurada)",
    r"\bvas\s+a\s+(ganar|lucrar|enriquecer)",
    r"\b100\s*%\s+de\s+(acierto|aciertos|[ée]xito)",
    r"\b(beneficio|retorno)\s+garantizado",
]
_RADAR_PROMESSA_RE = [_re_radar.compile(p, _re_radar.IGNORECASE) for p in _RADAR_PROMESSA_PADROES]

def _radar_tem_promessa(msgs):
    """True se QUALQUER mensagem contém linguagem de promessa/garantia de retorno."""
    texto = " ".join(m for m in msgs if isinstance(m, str))
    return any(rx.search(texto) for rx in _RADAR_PROMESSA_RE)


def _radar_ia(ctx: dict) -> Optional[list]:
    """Radar IA: entrega os numeros calculados pelas regras a um LLM que escreve
    a analise em linguagem natural, unica a cada teste. Regras rigidas no prompt:
    so usar os numeros fornecidos, nunca prever mercado, nunca prometer retorno.
    Qualquer falha -> None (caller usa os templates). Requer ANTHROPIC_API_KEY."""
    import sys
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return None
    try:
        import httpx
        sistema = (
            "Você é o Radar, copiloto de validação do BotBacktest (backtesting de estratégias de trading). "
            "Sua função: explicar o resultado do backtest do usuário usando EXCLUSIVAMENTE os números do contexto JSON. "
            "REGRAS INVIOLÁVEIS: (1) nunca preveja o mercado nem prometa lucro futuro — você fala de histórico medido, não de garantias. "
            "Quando o histórico medido deste ativo mostrar uma configuração com resultado MELHOR que a do usuário, seja DIRETO e útil: "
            "diga claramente que EXISTE uma forma de melhorar neste ativo, qual é (estratégia/parâmetros), os números medidos dela, "
            "e sugira aplicar e testar agora. O objetivo é AJUDAR o usuário a melhorar o resultado. "
            "Proibido apenas PROMETER retorno futuro (nada de 'vai lucrar', 'garante', 'com certeza', '100%'); "
            "ser direto sobre o que o histórico mostra e sugerir testar é permitido e desejável; "
            "se 'estrategia_mais_forte_medida_neste_ativo' vier preenchida, NUNCA diga que o usuário já está na "
            "melhor — destaque essa estratégia pelo nome, com Sharpe/retorno/PF/trades medidos, como o caminho mais "
            "forte deste ativo, e sugira gerar e testar (✨ Gerar estratégia / 📋 Estratégias prontas); "
            "se 'resultado_abaixo_do_medido' vier preenchido, o usuário JÁ está rodando essa estratégia mas o "
            "resultado ficou abaixo do que foi medido — explique de forma honesta que com parâmetros padrão (e/ou "
            "período/janela diferente) o número sai menor, e sugira AJUSTES CONCRETOS para perseguir o resultado mais "
            "forte: testar o período medido, mexer no stop/take e no período do indicador, rodar de novo e comparar; "
            "(2) use apenas os números fornecidos, jamais invente valores; "
            "(2b) SEJA HONESTO sobre resultados fracos ou de baixa relevância: NÃO transforme pouca atividade, amostra pequena "
            "ou resultado morno em elogio. Ex.: não chame 'poucos trades em muito tempo' (tipo ~1 por mês) de 'paciência operacional' "
            "como se fosse virtude — uma amostra pequena REDUZ a confiança estatística e dificulta concluir qualquer coisa; diga isso "
            "com clareza em vez de enfeitar. Resultado mediano é mediano; só elogie o que os números realmente sustentam; "
            f"(3) ESCREVA INTEIRAMENTE NO IDIOMA: {_IDIOMA_NOME.get(ctx.get('idioma','pt'),'português brasileiro')}. Tom de mentor experiente: claro, criativo, por vezes bem-humorado, sempre honesto; "
            "(4) cada análise deve soar DIFERENTE: varie aberturas, metáforas e estrutura; "
            "(5) traduza jargão (ex.: o que PF significa em dinheiro); "
            "(6) termine a última mensagem com um próximo passo prático (ex.: otimizar, validar out-of-sample, ajustar Máx. Ops); "
            "(7) se um dado vier null/ausente, simplesmente não fale dele; "
            "(8) NUNCA mencione outros traders, uma comunidade, base/banco coletivo ou dados de outros usuários — "
            "apresente TODA comparação como análise estatística/histórica DESTE ativo medida pela plataforma "
            "(ex.: 'no histórico medido deste ativo', nunca 'outros traders fazem X'). "
            "FORMATO DA RESPOSTA: somente um array JSON de 2 a 4 strings (cada uma vira uma bolha de chat, máx ~450 caracteres), "
            "podendo usar <b>negrito</b>. Nada fora do array JSON."
        )
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": chave,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
                "max_tokens": 800,
                "temperature": 1.0,
                "system": sistema,
                "messages": [{"role": "user", "content":
                    "Contexto do teste (JSON):\n" + json.dumps(ctx, ensure_ascii=False)}],
            },
            timeout=9.0,
        )
        if r.status_code != 200:
            print(f"RADAR IA status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        texto = "".join(b.get("text", "") for b in r.json().get("content", []))
        texto = texto.strip()
        if texto.startswith("```"):
            texto = texto.strip("`")
            if texto.startswith("json"):
                texto = texto[4:]
        msgs = json.loads(texto)
        if isinstance(msgs, list) and 1 <= len(msgs) <= 5 and all(isinstance(m, str) and m.strip() for m in msgs):
            # REDE DE SEGURANÇA: se a IA escorregou pra promessa, descarta e usa templates.
            if _radar_tem_promessa(msgs):
                print("RADAR IA: resposta BARRADA pela rede de segurança (linguagem de promessa) — "
                      "usando templates seguros. idioma=" + str(ctx.get("idioma", "pt")), file=sys.stderr)
                return None
            return ["✨ " + m if i == 0 else m for i, m in enumerate(msgs)]
        return None
    except Exception as e:
        print(f"RADAR IA erro: {e}", file=sys.stderr)
        return None


@app.post("/radar/analisar")
def radar_analisar(p: RadarAnalisarParams):
    """Análise do Radar: OffMind (padrões do ativo) + histórico coletivo (BabyMachine)
    => leitura honesta + sugestão de indicador/gatilho APLICÁVEL.
    Sempre validação histórica, nunca previsão."""
    import sys
    mensagens = []
    aplicar = None
    ia_usada = False
    try:
        # ── GATING (v3.9): plano de quem chama + regra de IA do Free ──
        # Free: IA no 1º e 3º teste, 2º só regras (contraste + economia). Pro/Trader Pro: IA sempre.
        # Recomendação de melhoria (mapa) = exclusiva Pro+ (cenoura pro upgrade).
        if p.user_id:
            plano_radar, _free_usados, _ = _perfil_plano_e_creditos(p.user_id)
        else:
            plano_radar, _free_usados = "free", 0
        nivel_radar = _PLANO_NIVEL.get(plano_radar, 0)
        pode_recomendar = nivel_radar >= 1
        usar_ia = True if nivel_radar >= 1 else (_free_usados in (1, 3))
        # ── 1) OffMind: varre os 6 padrões no ativo/timeframe (dados vêm do cache) ──
        fortes = []
        # relação risco/retorno que o usuário pediu (take/stop), limitada a 0.5..4
        ratio = 2.0
        if p.stop_loss and p.take_profit and float(p.stop_loss) > 0:
            ratio = max(0.5, min(4.0, float(p.take_profit) / float(p.stop_loss)))
        try:
            df = baixar_dados(p.ativo, p.periodo, p.timeframe)
            if df is not None and len(df) >= 60:
                for k, meta in PADROES_OFFMIND.items():
                    r = analisar_padrao(df, meta["fn"], [5, 10], ratio, 1.0)
                    if r["total_ocorrencias"] < 8:
                        continue
                    melhor = None
                    for h in r["por_horizonte"]:
                        if (h["acertos"] + h["falhas"]) < 6:
                            continue
                        if melhor is None or h["taxa_acerto"] > melhor["taxa_acerto"]:
                            melhor = h
                    if melhor:
                        fortes.append({
                            "chave": k, "nome": meta["nome"],
                            "ocorrencias": r["total_ocorrencias"],
                            "horizonte": melhor["horizonte"],
                            "taxa": melhor["taxa_acerto"],
                        })
                fortes.sort(key=lambda x: x["taxa"], reverse=True)
                if fortes:
                    top = fortes[:2]
                    partes = []
                    for f in top:
                        partes.append(
                            f"<b>{f['nome']}</b> apareceu {f['ocorrencias']}x; "
                            f"em até {f['horizonte']} candles, <b>{f['taxa']:.0f}%</b> bateram o alvo antes do stop"
                        )
                    destaques = "; ".join(partes)
                    nc = len(df); atv = p.ativo; tfu = p.timeframe.upper()
                    mensagens.append(random.choice([
                        f"🧠 <b>O que o passado deste ativo mostra:</b> varri {nc} candles de {atv} {tfu} "
                        f"usando a <b>sua</b> relação risco/retorno (1:{ratio:.1f}). Destaques: {destaques}. "
                        f"<b>Tradução:</b> frequências reais, medição conservadora — empate conta como stop.",
                        f"🔬 <b>Mergulhei no histórico:</b> {nc} candles de {atv} {tfu} passaram pelo pente fino, "
                        f"com a sua régua de risco (1:{ratio:.1f}). O que saltou aos olhos: {destaques}. "
                        f"Números crus, sem maquiagem — quando empata no candle, eu conto como derrota.",
                        f"📜 <b>A história que {atv} conta no {tfu}:</b> em {nc} candles, medindo com a sua "
                        f"relação 1:{ratio:.1f}, os protagonistas foram: {destaques}. São estatísticas do que "
                        f"JÁ aconteceu — uso o critério mais duro possível pra não te iludir.",
                        f"🎲 <b>Frequências do passado</b> ({nc} candles, {atv} {tfu}, sua relação 1:{ratio:.1f}): "
                        f"{destaques}. Lembrete de sempre: padrão que funcionou ontem é pista, não profecia — "
                        f"e eu meço pelo critério conservador.",
                    ]))
        except Exception as e:
            print(f"RADAR offmind: {e}", file=sys.stderr)

        # ── 2) Histórico coletivo: melhor config já validada nesse ativo ──
        melhor_cfg = None
        try:
            sb = _sb_admin()
            if sb is not None:
                # SÓ COMPARA O COMPARÁVEL: mesmo ativo + MESMO timeframe + 30+ trades.
                # (Lição aprendida: sugerir config de 1D pra quem opera 1H piora resultado.)
                resp = sb.table("backtests_historico").select(
                    "estrategia_nome,parametros,profit_factor,win_rate,total_trades,timeframe"
                ).eq("ativo", p.ativo).eq("timeframe", p.timeframe).gte("total_trades", 30).order(
                    "profit_factor", desc=True).limit(20).execute()

                def _pf_robusto(pf, n):
                    # encolhe o PF de amostras pequenas em direção a 1.0 (neutro):
                    # PF 5.0 em 16 trades vale menos que PF 1.4 em 500 trades
                    return 1.0 + (float(pf) - 1.0) * (float(n) / (float(n) + 50.0))

                candidatos = []
                for row in (resp.data or []):
                    pf = row.get("profit_factor"); n = row.get("total_trades") or 0
                    if pf is None or float(pf) <= 1.0:
                        continue
                    pr = row.get("parametros") or {}
                    candidatos.append((_pf_robusto(pf, n), row, pr))
                if candidatos:
                    candidatos.sort(key=lambda c: c[0], reverse=True)
                    score, row, pr = candidatos[0]
                    melhor_cfg = {
                        "indicador": row.get("estrategia_nome"),
                        "ema_period": pr.get("ema_period"),
                        "stop_loss": pr.get("stop_loss"),
                        "take_profit": pr.get("take_profit"),
                        "pf": round(float(row.get("profit_factor")), 2),
                        "pf_robusto": round(score, 2),
                        "wr": round(float(row.get("win_rate") or 0), 1),
                        "trades": row.get("total_trades"),
                        "timeframe": row.get("timeframe"),
                    }
        except Exception as e:
            print(f"RADAR coletivo: {e}", file=sys.stderr)

        # ── 3) Sugestão CONTEXTUAL: olha o que o usuário ACABOU de rodar ──
        classe = _RADAR_CLASSES.get(fortes[0]["chave"]) if fortes else None
        base = _RADAR_SUGESTOES.get(classe) if classe else None

        def _num(x):
            try: return round(float(x), 2)
            except Exception: return None

        # a config que o usuário acabou de testar
        cfg_usuario = (str(p.indicador_atual or ""), _num(p.ema_period_atual),
                       _num(p.stop_loss), _num(p.take_profit))
        cfg_melhor = None
        if melhor_cfg:
            cfg_melhor = (str(melhor_cfg.get("indicador") or ""), _num(melhor_cfg.get("ema_period")),
                          _num(melhor_cfg.get("stop_loss")), _num(melhor_cfg.get("take_profit")))
        ja_esta_na_melhor = cfg_melhor is not None and cfg_melhor == cfg_usuario

        # comparação do resultado DESTE teste com o melhor do coletivo
        pf_u = _num(p.profit_factor); wr_u = _num(p.win_rate); nt_u = p.total_trades or 0

        # ── 2b) BIBLIOTECA DE ESTUDO (tabela persistente): varredura sistemática de
        # estratégias × timeframes. Fonte autoritativa de "estratégia mais forte neste
        # ativo" — SEMPRE disponível, não depende do cache em memória. Corrige o caso em
        # que o Radar dizia "você já está na melhor" ignorando estratégias superiores.
        biblioteca = None
        biblioteca_melhor = None
        ajustar_parametros = None
        try:
            if pode_recomendar:
                _sbb = _sb_admin()
                if _sbb is not None:
                    _rb = (_sbb.table("estudo_biblioteca")
                           .select("estrategia_id,estrategia_nome,timeframe,periodo,retorno,profit_factor,win_rate,sharpe,trades")
                           .eq("ativo", p.ativo).gte("trades", 20)
                           .order("sharpe", desc=True).limit(80).execute())
                    _lin = [r for r in (_rb.data or []) if r.get("sharpe") is not None]
                    if _lin:
                        def _nb(r):
                            return {"estrategia": r.get("estrategia_nome"), "id": r.get("estrategia_id"),
                                    "tf": r.get("timeframe"), "periodo": r.get("periodo"),
                                    "retorno": _num(r.get("retorno")), "pf": _num(r.get("profit_factor")),
                                    "wr": _num(r.get("win_rate")), "sharpe": _num(r.get("sharpe")),
                                    "trades": r.get("trades")}
                        _lin.sort(key=lambda r: (r.get("sharpe") or -999), reverse=True)
                        _tops = [_nb(r) for r in _lin]
                        _tfu = str(p.timeframe or "").strip().lower()
                        _rodando_id = str(p.estrategia_id_atual or "").strip()   # estratégia REALMENTE em execução
                        _mesmo = [t for t in _tops if str(t["tf"]).strip().lower() == _tfu]
                        _mesmo_per = [t for t in _mesmo if str(t.get("periodo") or "") == str(p.periodo or "")]
                        _top_tf = (_mesmo_per[0] if _mesmo_per else (_mesmo[0] if _mesmo else None))
                        biblioteca = {"top1": _tops[0], "top_mesmo_tf": _top_tf, "lista": _tops[:6]}
                        # (Ponto 1) estratégia DIFERENTE (por id) e mais forte no MESMO timeframe = sugestão honesta.
                        # Indicador do dropdown nunca tem id de biblioteca -> sempre "diferente" (sugere a estratégia).
                        _cand = _top_tf
                        if (_cand and _cand.get("pf") and _cand.get("trades") and _cand["trades"] >= 20
                                and ((str(_cand.get("id") or "").strip() != _rodando_id) if _rodando_id else True)
                                and float(_cand["pf"]) > max(1.15, (pf_u or 1.0) * 1.10)):
                            biblioteca_melhor = _cand
                            ja_esta_na_melhor = False   # há estratégia superior medida — não diga que está na melhor
                        # (Ponto 2) usuário JÁ está rodando uma estratégia da biblioteca, mas o resultado
                        # ficou abaixo do indicado/medido -> sugerir ajuste de parâmetros (a IA analisa).
                        if _rodando_id:
                            _mesma = [t for t in _tops if str(t.get("id") or "").strip() == _rodando_id]
                            _mesma_tf = [t for t in _mesma if str(t.get("tf")).strip().lower() == _tfu]
                            _mesma_tf_per = [t for t in _mesma_tf if str(t.get("periodo") or "") == str(p.periodo or "")]
                            _med = (_mesma_tf_per[0] if _mesma_tf_per else
                                    (_mesma_tf[0] if _mesma_tf else (_mesma[0] if _mesma else None)))
                            _ret_u = _num(p.retorno)
                            _alvo_ret = _alvo_pf = None
                            if p.esperado and isinstance(p.esperado, dict):
                                _alvo_ret = _num(p.esperado.get("retorno")); _alvo_pf = _num(p.esperado.get("pf"))
                            if _alvo_ret is None and _med:
                                _alvo_ret = _med.get("retorno"); _alvo_pf = _med.get("pf")
                            _abaixo = False
                            if _alvo_ret is not None and _ret_u is not None and _alvo_ret > 0:
                                _abaixo = _ret_u < _alvo_ret * 0.7
                            elif _alvo_pf is not None and pf_u is not None:
                                _abaixo = pf_u < max(1.0, _alvo_pf * 0.85)
                            if _abaixo and _med:
                                ajustar_parametros = {
                                    "estrategia": _med.get("estrategia"), "tf": _med.get("tf"),
                                    "periodo": _med.get("periodo"),
                                    "medido_retorno": _med.get("retorno"), "medido_pf": _med.get("pf"),
                                    "medido_sharpe": _med.get("sharpe"), "medido_trades": _med.get("trades"),
                                    "seu_retorno": _ret_u, "seu_pf": pf_u,
                                }
        except Exception as e:
            print(f"RADAR biblioteca: {e}", file=sys.stderr)

        if ja_esta_na_melhor:
            # não repete a sugestão da mesma config: evolui a conversa
            txt = random.choice([
                f"🏆 <b>Boa notícia:</b> a config que você opera é a mais forte já medida "
                f"no histórico deste ativo (PF {melhor_cfg['pf']}, WR {melhor_cfg['wr']}% "
                f"em {melhor_cfg['trades']} trades). ",
                f"👑 <b>Config no ponto:</b> de tudo que o histórico deste ativo e timeframe registra, "
                f"a sua é a mais consistente (PF {melhor_cfg['pf']}, WR {melhor_cfg['wr']}% em "
                f"{melhor_cfg['trades']} trades). ",
                f"🥇 <b>Nada no histórico supera o que você usa</b> neste recorte — "
                f"PF {melhor_cfg['pf']}, WR {melhor_cfg['wr']}% em "
                f"{melhor_cfg['trades']} trades. ",
            ])
            if pf_u is not None and melhor_cfg.get("pf"):
                if pf_u >= float(melhor_cfg["pf"]) * 0.85:
                    txt += (f"Seu teste agora confirmou: PF <b>{pf_u}</b> em {nt_u} trades. "
                            f"Próximo passo profissional: <b>validação out-of-sample</b> e depois o ⚙ Otimizar "
                            f"pra varrer stop/take EM VOLTA dessa base — pequenos ajustes, não revolução.")
                else:
                    txt += (f"Mas seu teste agora deu PF <b>{pf_u}</b> — abaixo do registrado. "
                            f"Diferença comum: janela de período diferente pegou outra fase do mercado. "
                            f"Rode um período maior pra confirmar, ou use o ⚙ Otimizar pra recalibrar stop/take.")
            else:
                txt += "Use o ⚙ Otimizar pra refinar stop/take em volta dela e valide out-of-sample antes do MT5."
            mensagens.append(txt)
        elif base:
            _tipo = 'reversão' if 'reversao' in classe else 'continuação'
            _expl = ('o preço tende a voltar depois de esticar' if 'reversao' in classe
                     else 'movimentos iniciados tendem a continuar')
            texto = random.choice([
                f"📐 <b>Leitura do ativo:</b> o comportamento dominante de {p.ativo} nesse timeframe "
                f"favorece <b>{_tipo}</b> — ou seja, {_expl}. Gatilho que conversa com isso: "
                f"<b>{base['indicador']}</b> — {base['gatilho']}.",
                f"🧭 <b>Personalidade do ativo:</b> {p.ativo} nesse timeframe tem alma de <b>{_tipo}</b> "
                f"({_expl}). Se fosse pra escolher uma arma alinhada com esse temperamento: "
                f"<b>{base['indicador']}</b> — {base['gatilho']}.",
                f"📊 <b>O padrão por trás dos padrões:</b> somando as frequências, {p.ativo} aqui se comporta "
                f"como ativo de <b>{_tipo}</b> — {_expl}. Estratégia que costuma casar com esse perfil: "
                f"<b>{base['indicador']}</b> ({base['gatilho']}).",
            ])
            # A caixa de sugestão SÓ aparece se for MELHORA comprovada no histórico:
            # config coletiva com PF claramente acima do resultado atual do usuário.
            if melhor_cfg and melhor_cfg.get("stop_loss"):
                pf_rob_col = float(melhor_cfg.get("pf_robusto") or 0)
                pf_rob_user = (1.0 + (pf_u - 1.0) * (nt_u / (nt_u + 50.0))) if (pf_u is not None and nt_u) else None
                melhora = pf_rob_col > max(1.12, (pf_rob_user or 1.0) * 1.15)
                texto += (f" No histórico medido <b>neste mesmo timeframe</b> "
                          f"({melhor_cfg['timeframe']}), a config mais forte foi <b>{melhor_cfg['indicador']}</b> "
                          f"(período {melhor_cfg['ema_period']}, stop {melhor_cfg['stop_loss']} / "
                          f"take {melhor_cfg['take_profit']}): PF <b>{melhor_cfg['pf']}</b> "
                          f"em <b>{melhor_cfg['trades']} trades</b>.")
                if pf_u is not None:
                    texto += f" Seu teste atual: PF <b>{pf_u}</b>" + (f", WR {wr_u}%" if wr_u is not None else "") + f" em {nt_u} trades."
                if melhora:
                    aplicar = {
                        "indicador": melhor_cfg.get("indicador") or base["indicador"],
                        "ema_period": melhor_cfg.get("ema_period") or base["ema_period"],
                        "stop_loss": melhor_cfg["stop_loss"],
                        "take_profit": melhor_cfg["take_profit"],
                        "pf": melhor_cfg["pf"],
                        "pf_atual": pf_u,
                        "trades": melhor_cfg["trades"],
                    }
            else:
                texto += random.choice([
                    f" 📚 No histórico medido ainda <b>não há</b> configuração com amostra robusta "
                    f"(30+ trades) <b>neste timeframe</b> que supere seu teste — "
                    f"só comparo o comparável.",
                    f" 🗺️ Você está em <b>território pouco mapeado</b>: o histórico ainda não tem config "
                    f"robusta neste timeframe que bata a sua.",
                    f" 🔍 Procurei no histórico deste ativo e... <b>nada supera seu teste neste timeframe</b> com "
                    f"amostra decente (30+ trades). Config de outro timeframe não entra — comparação justa ou nenhuma.",
                ])
            mensagens.append(texto)

        # Estratégia SUPERIOR medida na biblioteca (cross-estratégia): aviso DIRETO e honesto.
        # Não há apply de 1 clique (estratégia diferente), então aponta como gerar/testar.
        if biblioteca_melhor:
            bm = biblioteca_melhor
            mensagens.append(
                f"🎯 <b>Existe um caminho mais forte pra {p.ativo} no {p.timeframe.upper()}:</b> "
                f"no histórico medido deste ativo, <b>{bm['estrategia']}</b> entregou "
                f"Sharpe <b>{bm['sharpe']}</b>, retorno <b>{bm['retorno']}%</b> e PF <b>{bm['pf']}</b> "
                f"em <b>{bm['trades']} trades</b> — acima do seu PF {pf_u} atual. "
                f"Não é promessa de futuro, é o que o passado mediu. Vale gerar essa estratégia "
                f"(✨ Gerar estratégia ou 📋 Estratégias prontas) e testar pra comparar de verdade."
            )

        # ── 4) Combinações de parâmetros: medidas nas bibliotecas, não opinião ──
        lab_info = None
        try:
            # (a) Varredura de relações risco/retorno no padrão dominante
            if fortes:
                f0 = fortes[0]
                meta0 = PADROES_OFFMIND[f0["chave"]]
                taxas = []
                for rr in (1.5, 2.0, 3.0):
                    r2 = analisar_padrao(df, meta0["fn"], [f0["horizonte"]], rr, 1.0)
                    hh = next((h for h in r2["por_horizonte"] if h["horizonte"] == f0["horizonte"]), None)
                    if hh and (hh["acertos"] + hh["falhas"]) >= 6:
                        taxas.append((rr, hh["taxa_acerto"]))
                if len(taxas) >= 2:
                    melhor_rr, melhor_tx = max(taxas, key=lambda t: t[1])
                    lab_info = {"padrao": f0["nome"],
                                "taxas_por_relacao": {f"1:{rr:g}": round(tx, 1) for rr, tx in taxas},
                                "relacao_mais_forte": f"1:{melhor_rr:g}"}
                    partes_rr = " · ".join(f"1:{rr:g} → <b>{tx:.0f}%</b>" for rr, tx in taxas)
                    msg = random.choice([
                        f"🔧 <b>Laboratório de combinações:</b> peguei o padrão dominante "
                        f"(<b>{f0['nome']}</b>) e testei 3 relações risco/retorno no histórico — {partes_rr}. ",
                        f"⚗️ <b>Experimento do dia:</b> coloquei o padrão <b>{f0['nome']}</b> no banco de provas "
                        f"com três relações risco/retorno — {partes_rr}. ",
                        f"🎛️ <b>Girando os botões:</b> mesmo padrão (<b>{f0['nome']}</b>), três calibragens "
                        f"de alvo no histórico — {partes_rr}. ",
                    ])
                    if p.stop_loss and float(p.stop_loss) > 0:
                        ratio_user = float(p.take_profit or 0) / float(p.stop_loss) if p.take_profit else None
                        take_sug = round(float(p.stop_loss) * melhor_rr)
                        if ratio_user and abs(ratio_user - melhor_rr) < 0.25:
                            msg += f"Sua relação atual (1:{ratio_user:.1f}) já está alinhada com a mais forte do histórico. ✅"
                        else:
                            msg += (f"A relação <b>1:{melhor_rr:g}</b> foi historicamente a mais forte "
                                    f"<b>para esse padrão de candles</b> — se quiser testar a hipótese, "
                                    f"mantendo seu stop {float(p.stop_loss):g} o take seria <b>~{take_sug}</b>. "
                                    f"Valide com um backtest antes de adotar: medição de padrão é termômetro "
                                    f"do ativo, não garantia pra sua estratégia.")
                    mensagens.append(msg)

            # (b) Capital vs drawdown: fôlego pra atravessar o pior momento
            if p.max_drawdown and p.capital and pf_u is not None:
                dd = abs(float(p.max_drawdown))
                if dd > 12 and pf_u >= 1.15:
                    valor_dd = round(float(p.capital) * dd / 100)
                    ops_txt = f" (Máx. Ops {p.max_ops})" if p.max_ops else ""
                    mensagens.append(random.choice([
                        f"💰 <b>Fôlego de capital:</b> estratégia positiva (PF {pf_u}), mas o drawdown de "
                        f"<b>{dd:.1f}%</b> significa aguentar <b>~${valor_dd:,}</b> de queda com capital de "
                        f"${float(p.capital):,.0f}{ops_txt}. Reduza o Máx. Ops ou aumente o colchão — "
                        f"o resultado só chega pra quem sobrevive ao pior trecho.",
                        f"🛟 <b>Teste de estômago:</b> no pior momento dessa curva você estaria "
                        f"<b>~${valor_dd:,} no vermelho</b> ({dd:.1f}% de ${float(p.capital):,.0f}{ops_txt}) — "
                        f"e a estratégia é lucrativa (PF {pf_u})! A pergunta honesta: você seguraria sem "
                        f"abandonar o plano? Se a resposta for não, menos Máx. Ops ou mais colchão.",
                        f"⛰️ <b>O vale antes do topo:</b> PF {pf_u} no final, mas o caminho passa por um "
                        f"drawdown de {dd:.1f}% — <b>~${valor_dd:,}</b> do seu capital{ops_txt}. Quem "
                        f"dimensiona o capital pro vale colhe o topo; quem não dimensiona, sai no fundo.",
                    ]))
        except Exception as e:
            print(f"RADAR combos: {e}", file=sys.stderr)

        if not mensagens:
            mensagens.append("🧠 OffMind não encontrou padrões com amostra suficiente nesse ativo/timeframe ainda. Rode em 1D ou aumente o período pra eu ter mais candles pra medir.")

        # ── 5) RADAR IA: reescreve a análise em linguagem natural (fallback: templates) ──
        try:
            ctx = {
                "teste": {
                    "ativo": p.ativo, "timeframe": p.timeframe, "periodo": p.periodo,
                    "profit_factor": pf_u, "win_rate": wr_u, "total_trades": nt_u,
                    "retorno_pct": _num(p.retorno), "max_drawdown_pct": _num(p.max_drawdown),
                    "capital": _num(p.capital), "max_ops": p.max_ops,
                    "indicador": p.indicador_atual, "periodo_indicador": p.ema_period_atual,
                    "stop_loss": _num(p.stop_loss), "take_profit": _num(p.take_profit),
                    "relacao_risco_retorno": f"1:{ratio:.1f}",
                },
                "offmind_padroes_no_ativo": [
                    {"padrao": f["nome"], "ocorrencias": f["ocorrencias"],
                     "horizonte_candles": f["horizonte"], "taxa_acerto_pct": round(f["taxa"], 1)}
                    for f in fortes[:3]
                ],
                "laboratorio_relacoes": lab_info,
                "config_historica_mais_forte_neste_ativo": melhor_cfg,
                "usuario_ja_esta_na_melhor_config": ja_esta_na_melhor,
                "ha_sugestao_aplicavel": aplicar is not None,
                "melhores_estrategias_medidas_neste_ativo": (biblioteca or {}).get("lista"),
                "estrategia_mais_forte_medida_neste_ativo": biblioteca_melhor,
                "resultado_abaixo_do_medido": ajustar_parametros,
            }
            # ── ESTUDO (matriz estrategia x timeframe) como 4a fonte do Radar ──
            import time as _t2
            estudo_ctx = None
            _mc = None
            _mc_cands = [v for k, v in _MATRIZ_CACHE.items() if k == p.ativo or k.startswith(p.ativo + "|")]
            if _mc_cands:
                _mc = max(_mc_cands, key=lambda x: x[0])
            if pode_recomendar and _mc and (_t2.time() - _mc[0]) < _MATRIZ_CACHE_TTL:
                dados_m = _mc[1]
                tops_m = dados_m.get("tops") or []
                # celula do usuario (mesma estrategia + mesmo timeframe)
                cel_u = None
                melhor_tf_da_minha = None
                for lin in dados_m.get("linhas", []):
                    if lin["nome"] == (p.indicador_atual or ""):
                        cel_u = lin["cels"].get(p.timeframe)
                        vivas = [(tf, c) for tf, c in lin["cels"].items() if c]
                        if vivas:
                            melhor_tf_da_minha = max(vivas, key=lambda x: x[1]["sharpe"])
                        break
                if tops_m:
                    top1 = tops_m[0]
                    a_frente = sum(1 for t in tops_m if pf_u and t["pf"] > pf_u)
                    estudo_ctx = {"top1": top1, "celula_do_usuario": cel_u,
                                  "melhor_tf_da_estrategia_do_usuario":
                                      ({"tf": melhor_tf_da_minha[0], **melhor_tf_da_minha[1]}
                                       if melhor_tf_da_minha else None),
                                  "configs_do_estudo_a_frente_do_usuario_em_pf": a_frente}
                    import random as _rd
                    if biblioteca is None and ((top1["estrategia"] != (p.indicador_atual or "")) or (top1["tf"] != p.timeframe)):
                        mensagens.append(_rd.choice([
                            f"🧪 <b>Cruzando com o Estudo deste ativo:</b> a combinação mais consistente "
                            f"foi <b>{top1['estrategia']} no {top1['tf'].upper()}</b> (PF {top1['pf']:.2f}, "
                            f"Sharpe {top1['sharpe']:.2f}, {top1['trades']} trades). Não é ordem de troca — "
                            f"é mapa: bom saber em que terreno sua config compete.",
                            f"🧪 <b>O Estudo deste ativo te dá régua:</b> o topo da matriz é "
                            f"<b>{top1['estrategia']} · {top1['tf'].upper()}</b> com Sharpe {top1['sharpe']:.2f} "
                            f"(PF {top1['pf']:.2f} em {top1['trades']} trades). Sua config tem "
                            f"{a_frente} combinações à frente em PF — use a aba 🧪 pra ver o ranking completo.",
                        ]))
                    if (melhor_tf_da_minha and melhor_tf_da_minha[0] != p.timeframe
                            and cel_u and melhor_tf_da_minha[1]["pf"] > max(1.05, (cel_u.get("pf") or 0) * 1.1)
                            and melhor_tf_da_minha[1]["trades"] >= 20):
                        mensagens.append(
                            f"🧭 <b>Detalhe do Estudo:</b> a sua <b>{p.indicador_atual}</b> rendeu mais no "
                            f"<b>{melhor_tf_da_minha[0].upper()}</b> (PF {melhor_tf_da_minha[1]['pf']:.2f} em "
                            f"{melhor_tf_da_minha[1]['trades']} trades) do que no {p.timeframe.upper()} que você está testando. "
                            f"Pode ser o terreno, não a estratégia — vale um backtest lá pra comparar.")
            elif p.user_id and _plano_usuario(p.user_id) in PLANOS_MATRIZ:
                import random as _rd
                if _rd.random() < 0.35:
                    mensagens.append(
                        "🧪 <b>Dica:</b> rode o <b>Estudo</b> deste ativo (aba 🧪) — a partir daí eu passo a "
                        "comparar cada teste seu com a galeria inteira de estratégias e te digo onde sua config "
                        "está no mapa.")
            ctx["estudo_matriz"] = estudo_ctx
            ctx["idioma"] = (p.idioma or "pt")
            if not pode_recomendar:
                # Free: IA descreve o resultado, mas NÃO entrega o mapa de melhoria (isso é Pro)
                for _k in ("config_historica_mais_forte_neste_ativo",
                           "usuario_ja_esta_na_melhor_config",
                           "ha_sugestao_aplicavel", "estudo_matriz", "laboratorio_relacoes",
                           "melhores_estrategias_medidas_neste_ativo",
                           "estrategia_mais_forte_medida_neste_ativo",
                           "resultado_abaixo_do_medido"):
                    ctx.pop(_k, None)
                aplicar = None
            # chave do cache: config + métricas + resumo do coletivo
            # (mesmo teste com mesmo resultado = mesma análise, custo zero)
            chave_cache = _radar_cache_chave({
                "t": ctx["teste"],
                "lang": ctx.get("idioma", "pt"),
                "col_pf": (melhor_cfg or {}).get("pf"),
                "col_n": (melhor_cfg or {}).get("trades"),
                "top": ja_esta_na_melhor,
                "sug": aplicar is not None,
            })
            if usar_ia:
                msgs_cache = _radar_cache_get(chave_cache)
                if msgs_cache:
                    mensagens = msgs_cache
                    ia_usada = True
                else:
                    msgs_ia = _radar_ia(ctx)
                    if msgs_ia:
                        mensagens = msgs_ia
                        ia_usada = True
                        _radar_cache_set(chave_cache, msgs_ia)
        except Exception as e:
            print(f"RADAR IA contexto: {e}", file=sys.stderr)

        testar_estrategia = None
        if biblioteca_melhor and biblioteca_melhor.get("id"):
            testar_estrategia = {
                "id": biblioteca_melhor.get("id"), "nome": biblioteca_melhor.get("estrategia"),
                "tf": biblioteca_melhor.get("tf"), "sharpe": biblioteca_melhor.get("sharpe"),
                "pf": biblioteca_melhor.get("pf"), "retorno": biblioteca_melhor.get("retorno"),
                "trades": biblioteca_melhor.get("trades"),
            }
        return converter_para_python({"mensagens": mensagens, "aplicar": aplicar, "ia_usada": ia_usada,
                                      "testar_estrategia": testar_estrategia,
                                      "ajustar_parametros": ajustar_parametros})
    except Exception as e:
        print(f"ERRO RADAR ANALISAR: {e}", file=sys.stderr)
        return {"mensagens": [], "aplicar": None, "ia_usada": False}


class ParamSugeridosReq(BaseModel):
    ativo: str
    timeframe: str = "1d"
    user_id: Optional[str] = None


@app.post("/radar/parametros-sugeridos")
def radar_parametros_sugeridos(req: ParamSugeridosReq):
    """Sugere stop/take para preencher antes de rodar: usa a config mais forte
    MEDIDA neste ativo+timeframe (histórico coletivo) quando existe; senão devolve
    um ponto de partida equilibrado. Nunca promete retorno — é ponto de partida medido."""
    stop, take, motivo, fonte = 50, 100, None, "padrao"
    try:
        sb = _sb_admin()
        if sb is not None:
            resp = (sb.table("backtests_historico")
                    .select("parametros,profit_factor,total_trades,timeframe")
                    .eq("ativo", req.ativo).eq("timeframe", req.timeframe)
                    .gte("total_trades", 20).order("profit_factor", desc=True).limit(20).execute())
            best = None; best_score = 0.0
            for row in (resp.data or []):
                pf = row.get("profit_factor"); n = row.get("total_trades") or 0
                pr = row.get("parametros") or {}
                sl = pr.get("stop_loss"); tp = pr.get("take_profit")
                if pf and float(pf) > 1.0 and sl and tp:
                    score = 1.0 + (float(pf) - 1.0) * (n / (n + 50.0))
                    if score > best_score:
                        best_score = score
                        best = (round(float(sl)), round(float(tp)), round(float(pf), 2), n)
            if best:
                stop, take, _pf, _n = best
                motivo = f"config mais forte medida neste ativo no {req.timeframe.upper()}: PF {_pf} em {_n} trades"
                fonte = "historico"
    except Exception as e:
        print(f"PARAM SUGERIDOS: {e}", file=sys.stderr)
    if fonte == "padrao":
        motivo = "ponto de partida equilibrado (relação 1:2) — ajuste e compare"
    return {"stop": stop, "take": take, "motivo": motivo, "fonte": fonte}


@app.post("/backtest/visual")
def backtest_visual(params: BacktestParams):
    import sys
    try:
        _credito = _consumir_credito_backtest(params.user_id, params.ativo)
        df = baixar_dados(params.ativo, params.periodo, params.timeframe)
        resultado = rodar_estrategia(df, params)
        metricas = calcular_metricas_completas(resultado, params, df)
        salvar_historico_backtest(params, metricas, user_id=params.user_id, sessao_id=params.sessao_id, codigo="")
        _out = converter_para_python(metricas); _out["_credito"] = _credito
        return _out
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERRO BACKTEST: {str(e)}\n{tb}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{tb}")

@app.post("/backtest/custom")
def backtest_custom(params: BacktestCustom):
    import sys
    try:
        _credito = _consumir_credito_backtest(params.user_id, params.ativo)
        df = baixar_dados(params.ativo, params.periodo, params.timeframe)
        if params.codigo and len(params.codigo.strip()) > 20:
            try:
                resultado = rodar_codigo_custom(df, params)
            except Exception:
                resultado = rodar_estrategia(df, params)
        else:
            resultado = rodar_estrategia(df, params)
        metricas = calcular_metricas_completas(resultado, params, df)
        salvar_historico_backtest(params, metricas, user_id=params.user_id, sessao_id=params.sessao_id, codigo=getattr(params, "codigo", ""))
        _out = converter_para_python(metricas); _out["_credito"] = _credito
        return _out
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERRO CUSTOM: {str(e)}\n{tb}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{tb}")

def rodar_codigo_custom(df: pd.DataFrame, params: BacktestCustom) -> dict:
    """
    v3.1 - Executa de VERDADE a estrategia Python do usuario com o motor
    backtesting.py. Aceita classes Strategy (com ou sem imports no codigo).
    Se falhar, levanta excecao - o chamador cai no motor padrao.
    """
    from backtesting import Backtest, Strategy as _Strategy
    from backtesting.lib import crossover as _crossover

    # Namespace com tudo que os codigos gerados/colados costumam usar
    ns = {
        "pd": pd, "np": np,
        "Strategy": _Strategy, "crossover": _crossover,
        # Valores da barra lateral disponíveis pro código colado (em pontos/USD)
        "SL_PTS": float(params.stop_loss), "TP_PTS": float(params.take_profit),
        "MAX_OPS": int(params.max_ops), "CAPITAL": float(params.capital),
        "__builtins__": __builtins__,
    }
    exec(params.codigo, ns)  # erro no codigo -> excecao sobe -> fallback

    # Encontra a classe Strategy definida pelo usuario
    cls = None
    for v in ns.values():
        if isinstance(v, type) and issubclass(v, _Strategy) and v is not _Strategy:
            cls = v
    if cls is None:
        raise ValueError("Nenhuma classe Strategy encontrada no codigo")

    dfx = df.copy().dropna()

    # Ativos caros (ex: BTC) > capital: roda com cash ampliado e re-escala
    capital_user = float(params.capital)
    preco_max = float(dfx["Close"].max())
    cash_engine = max(capital_user, preco_max * 3)
    fator = capital_user / cash_engine

    bt = Backtest(dfx, cls, cash=cash_engine,
                  commission=float(params.comissao), exclusive_orders=True)
    stats = bt.run()

    # Converte trades pro formato do front
    trades = []
    tdf = stats.get("_trades")
    if tdf is not None and len(tdf):
        for _, t in tdf.iterrows():
            pl = float(t["PnL"]) * fator
            trades.append({
                "entrada": str(t["EntryTime"])[:16],
                "saida": str(t["ExitTime"])[:16],
                "preco_entrada": round(float(t["EntryPrice"]), 5),
                "preco_saida": round(float(t["ExitPrice"]), 5),
                "retorno_pct": round(float(t["ReturnPct"]) * 100, 4),
                "pl": round(pl, 2),
                "resultado": "Ganho" if pl > 0 else "Perda",
                "idx_entrada": int(t["EntryBar"]),
                "idx_saida": int(t["ExitBar"]),
            })

    # Equity curve re-escalada pro capital do usuario
    eq = stats["_equity_curve"]["Equity"]
    equity_curve = [round(float(v) * fator, 2) for v in eq.tolist()]
    if not equity_curve:
        equity_curve = [capital_user]
    capital_final = equity_curve[-1]

    return {"trades": trades, "equity_curve": equity_curve,
            "df": dfx, "capital_final": capital_final}

@app.post("/gerar-bot-ia")
def gerar_bot_ia(req: IARequest):
    import re as _re
    desc = req.descricao.lower()
    # normaliza erros comuns de digitacao
    for a, b in [("crusamento", "cruzamento"), ("cruzameto", "cruzamento"),
                 ("hight", "high"), ("higt", "high"), ("loww", "low"),
                 ("médias", "medias"), ("média", "media")]:
        desc = desc.replace(a, b)
    numeros = [int(n) for n in _re.findall(r"\b(\d{1,3})\b", desc)]
    # quantidades tipo "2 medias" nao sao periodo — periodo valido: 5 a 200
    periodos = [n for n in numeros if 5 <= n <= 200]

    # ── PRIORIDADE 1: canal high/low (assinatura da casa) ──
    # "2 medias de 20 uma high e outra low", "canal ema 20", etc.
    if ("high" in desc and "low" in desc) or "canal" in desc:
        periodo = periodos[0] if periodos else 20
        codigo = f"""class CanalEMAHighLow(Strategy):
    # Gerado por IA baseado em: {req.descricao}
    # Canal: EMA{{0}} das maximas (high) e EMA{{0}} das minimas (low).
    # Preco rompe ACIMA do canal = compra. Rompe ABAIXO = sai/vende.
    # Dentro do canal = lateral, nao opera.
    ema_period = {periodo}

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
        return {"codigo": codigo, "entendi": f"Canal EMA {periodo} High/Low — rompimento do canal"}

    # ── PRIORIDADE 2: cruzamento de DUAS medias com periodos ──
    if "cruzamento" in desc and ("media" in desc or "ema" in desc or "sma" in desc):
        if len(periodos) >= 2:
            rapida, lenta = sorted(periodos[:2])
        elif len(periodos) == 1:
            rapida, lenta = periodos[0], periodos[0] * 2
        else:
            rapida, lenta = 9, 21
        if rapida == lenta:
            lenta = rapida * 2
        codigo = f"""class CruzamentoEMA(Strategy):
    # Gerado por IA baseado em: {req.descricao}
    # EMA{{rapida}} cruza ACIMA da EMA{{lenta}} = compra. Cruza abaixo = sai.
    rapida = {rapida}
    lenta = {lenta}

    def init(self):
        close = pd.Series(self.data.Close)
        self.e1 = self.I(lambda: close.ewm(span=self.rapida, adjust=False).mean().values)
        self.e2 = self.I(lambda: close.ewm(span=self.lenta, adjust=False).mean().values)

    def next(self):
        if not self.position:
            if self.e1[-1] > self.e2[-1] and self.e1[-2] <= self.e2[-2]:
                self.buy()
        else:
            if self.e1[-1] < self.e2[-1]:
                self.position.close()"""
        return {"codigo": codigo, "entendi": f"Cruzamento EMA {rapida}/{lenta}"}

    # Templates inteligentes baseados na descrição
    if "rsi" in desc:
        periodo = 14
        for w in desc.split():
            if w.isdigit():
                periodo = int(w)
                break
        codigo = f"""class RSIStrategy(Strategy):
    rsi_period = {periodo}

    def init(self):
        close = pd.Series(self.data.Close)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        self.rsi = self.I(lambda: (100 - 100 / (1 + rs)).values)

    def next(self):
        if not self.position:
            if self.rsi[-1] < 30:
                self.buy()
        else:
            if self.rsi[-1] > 70:
                self.position.close()"""

    elif "macd" in desc:
        codigo = """class MACDStrategy(Strategy):
    def init(self):
        close = pd.Series(self.data.Close)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        self.macd = self.I(lambda: macd.values)
        self.signal = self.I(lambda: signal.values)

    def next(self):
        if not self.position:
            if self.macd[-1] > self.signal[-1] and self.macd[-2] <= self.signal[-2]:
                self.buy()
        else:
            if self.macd[-1] < self.signal[-1]:
                self.position.close()"""

    elif "bollinger" in desc or "bb" in desc:
        codigo = """class BollingerStrategy(Strategy):
    period = 20

    def init(self):
        close = pd.Series(self.data.Close)
        sma = close.rolling(self.period).mean()
        std = close.rolling(self.period).std()
        self.upper = self.I(lambda: (sma + 2*std).values)
        self.lower = self.I(lambda: (sma - 2*std).values)

    def next(self):
        if not self.position:
            if self.data.Close[-1] < self.lower[-1]:
                self.buy()
        else:
            if self.data.Close[-1] > self.upper[-1]:
                self.position.close()"""

    elif "sma" in desc or "media" in desc or "golden" in desc:
        codigo = """class GoldenCrossStrategy(Strategy):
    fast = 50
    slow = 200

    def init(self):
        close = pd.Series(self.data.Close)
        self.sma_fast = self.I(lambda: close.rolling(self.fast).mean().values)
        self.sma_slow = self.I(lambda: close.rolling(self.slow).mean().values)

    def next(self):
        if not self.position:
            if self.sma_fast[-1] > self.sma_slow[-1] and self.sma_fast[-2] <= self.sma_slow[-2]:
                self.buy()
        else:
            if self.sma_fast[-1] < self.sma_slow[-1]:
                self.position.close()"""

    else:
        # EMA Channel padrão
        codigo = f"""class EMAChannelStrategy(Strategy):
    # Gerado por IA baseado em: {req.descricao}
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

    return {
        "codigo": codigo,
        "descricao": req.descricao,
        "indicador_detectado": "RSI" if "rsi" in desc else "MACD" if "macd" in desc else "EMA Channel"
    }

@app.get("/exportar/ntsl")
def exportar_ntsl():
    codigo = """// ============================================
// BacktestPro — Exportação NTSL para Profit
// Gerado automaticamente
// ============================================

// Parâmetros
input int    EMA_Period   = 20;
input double StopLoss     = 50;
input double TakeProfit   = 100;
input double Lotes        = 0.1;

// Variáveis globais
double ema_high[], ema_low[];

void OnInit() {
    SetIndexBuffer(0, ema_high);
    SetIndexBuffer(1, ema_low);
}

void OnTick() {
    int bars = Bars;
    if (bars < EMA_Period + 1) return;

    // Calcula EMA High e EMA Low
    double soma_h = 0, soma_l = 0;
    for (int i = 0; i < EMA_Period; i++) {
        soma_h += High[i];
        soma_l += Low[i];
    }
    double ema_h = soma_h / EMA_Period;
    double ema_l = soma_l / EMA_Period;

    double preco = Close[0];

    // Sem posição aberta — verifica entrada
    if (OrdersTotal() == 0) {
        if (preco > ema_h) {
            OrderSend(Symbol(), OP_BUY, Lotes, Ask, 3,
                      Ask - StopLoss * Point,
                      Ask + TakeProfit * Point,
                      "BotBacktest EMA Channel", 0, 0, clrGreen);
        }
    } else {
        // Verifica saída
        for (int j = 0; j < OrdersTotal(); j++) {
            if (OrderSelect(j, SELECT_BY_POS)) {
                if (OrderType() == OP_BUY && preco < ema_l) {
                    OrderClose(OrderTicket(), OrderLots(), Bid, 3, clrRed);
                }
            }
        }
    }
}"""
    return {"codigo": codigo, "formato": "NTSL/MQL4", "plataforma": "Profit/MetaTrader"}

@app.get("/historico")
def get_historico():
    return {"historico": [], "total": 0, "mensagem": "Histórico disponível com autenticação ativa"}

@app.get("/ranking")
def get_ranking():
    return {
        "ranking": [
            {"posicao": 1, "nome": "EMA Channel XAU Master", "retorno": 68.4, "win_rate": 67.2, "ativo": "XAU/USD", "estrelas": 5},
            {"posicao": 2, "nome": "Bollinger Squeeze Pro",  "retorno": 47.2, "win_rate": 61.5, "ativo": "BTC/USD", "estrelas": 4},
            {"posicao": 3, "nome": "MACD BTC Scalper",       "retorno": 38.9, "win_rate": 58.3, "ativo": "BTC/USD", "estrelas": 4},
            {"posicao": 4, "nome": "RSI Reversal Gold",      "retorno": 34.1, "win_rate": 61.2, "ativo": "XAU/USD", "estrelas": 4},
            {"posicao": 5, "nome": "Golden Cross S&P",       "retorno": 29.7, "win_rate": 57.8, "ativo": "IBOVESPA","estrelas": 4},
        ]
    }

@app.get("/stats")
def get_stats():
    return {
        "total_backtests": 1247,
        "usuarios_ativos": 89,
        "ativo_mais_testado": "XAU/USD",
        "melhor_retorno": 68.4,
        "versao_api": "1.1.0"
    }

# ── STRIPE ──────────────────────────────────────────────


PRICE_IDS = {
    "pro": {
        "BRL": "price_1TdF3TAWeqEnicm4OJJEgFvR",
        "USD": "price_1TdF5HAWeqEnicm4e5wRK96S",
        "EUR": "price_1TdF5XAWeqEnicm4dfadId2G",
    },
    "trader": {
        "BRL": "price_1TdF9FAWeqEnicm4dqDhez61",
        "USD": "price_1TdFAhAWeqEnicm4i0DNuJ2b",
        "EUR": "price_1TdFBSAWeqEnicm4ZoxIQgBn",
    }
}

class CheckoutRequest(BaseModel):
    plano: str
    moeda: str = "BRL"
    user_id: str
    email: str

@app.post("/criar-checkout")
def criar_checkout(req: CheckoutRequest):
    try:
        price_id = PRICE_IDS.get(req.plano, {}).get(req.moeda)
        if not price_id:
            raise HTTPException(status_code=400, detail="Plano ou moeda inválido")

        # Trava anti-duplicação: se o usuário já tem assinatura ativa, NÃO cria outra.
        # Devolve o link do Customer Portal para ele gerenciar a existente.
        # Fail-open: se a checagem falhar, segue o fluxo normal (não bloqueia assinatura legítima).
        try:
            sb = _sb_admin()
            if sb is not None:
                resp = sb.table("perfis").select("stripe_subscription_id").eq("id", req.user_id).single().execute()
                sub_id = (resp.data or {}).get("stripe_subscription_id")
                if sub_id:
                    sub_obj = stripe.Subscription.retrieve(sub_id)
                    sub = sub_obj.to_dict() if hasattr(sub_obj, "to_dict") else dict(sub_obj)
                    if sub.get("status") in ("active", "trialing", "past_due"):
                        customer_id = sub.get("customer")
                        portal_url = None
                        if customer_id:
                            portal = stripe.billing_portal.Session.create(
                                customer=customer_id,
                                return_url="https://backtestpro-production-eb9a.up.railway.app/app",
                            )
                            portal_url = portal.url
                        return {"already_subscribed": True, "portal_url": portal_url}
        except Exception as e:
            print(f"Anti-duplicação: checagem ignorada ({e})")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            customer_email=req.email,
            client_reference_id=req.user_id,
            success_url="https://backtestpro-production-eb9a.up.railway.app/app?checkout=success",
            cancel_url="https://backtestpro-production-eb9a.up.railway.app/app?checkout=cancel",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PortalRequest(BaseModel):
    user_id: str

@app.post("/criar-portal")
def criar_portal(req: PortalRequest):
    """Abre o Stripe Customer Portal para o usuario gerenciar/cancelar a assinatura.
    Resolve tudo no servidor: user_id -> stripe_subscription_id (perfis) -> customer -> portal."""
    try:
        sb = _sb_admin()
        if sb is None:
            raise HTTPException(status_code=500, detail="Supabase indisponivel")

        resp = sb.table("perfis").select("stripe_subscription_id").eq("id", req.user_id).single().execute()
        sub_id = (resp.data or {}).get("stripe_subscription_id")
        if not sub_id:
            raise HTTPException(status_code=400, detail="Nenhuma assinatura ativa encontrada para gerenciar.")

        sub_obj = stripe.Subscription.retrieve(sub_id)
        sub = sub_obj.to_dict() if hasattr(sub_obj, "to_dict") else dict(sub_obj)
        customer_id = sub.get("customer")
        if not customer_id:
            raise HTTPException(status_code=400, detail="Cliente Stripe nao encontrado.")

        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url="https://backtestpro-production-eb9a.up.railway.app/app",
        )
        return {"url": portal.url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stripe/publishable-key")
def get_publishable_key():
    return {"key": os.getenv("STRIPE_PUBLISHABLE_KEY", "")}

@app.post("/webhook/stripe")
async def webhook_stripe(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        # Converte StripeObject para dict puro
        session_obj = event["data"]["object"]
        session = session_obj.to_dict() if hasattr(session_obj, "to_dict") else dict(session_obj)

        user_id = session.get("client_reference_id")
        subscription_id = session.get("subscription")
        plano = "pro"

        print(f"Webhook recebido: user_id={user_id}, subscription_id={subscription_id}")

        try:
            if subscription_id:
                sub_obj = stripe.Subscription.retrieve(subscription_id)
                sub = sub_obj.to_dict() if hasattr(sub_obj, "to_dict") else dict(sub_obj)
                items = sub.get("items", {}).get("data", [])
                for item in items:
                    pid = item.get("price", {}).get("id", "")
                    if pid in PRICE_IDS.get("trader", {}).values():
                        plano = "trader_pro"
                        break
        except Exception as e:
            print(f"Stripe subscription retrieve error: {e}")

        print(f"Atualizando Supabase: user_id={user_id} plano={plano}")

        if user_id:
            try:
                from supabase import create_client
                sb = create_client(
                    os.getenv("SUPABASE_URL", ""),
                    os.getenv("SUPABASE_SERVICE_KEY", "")
                )
                limite = 999999 if plano == "trader_pro" else 200
                result = sb.table("perfis").update({
                    "plano": plano,
                    "backtests_limite": limite,
                    "stripe_subscription_id": subscription_id
                }).eq("id", user_id).execute()
                print(f"Supabase update OK: {result}")
            except Exception as e:
                print(f"Supabase update error: {e}")
                raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")

    # Assinatura cancelada (ou expirada) -> rebaixa o usuario para o plano free.
    # FREE_LIMIT: ajuste para o limite de backtests do seu plano gratuito,
    # caso o trigger de signup do Supabase use um valor diferente.
    elif event["type"] == "customer.subscription.deleted":
        FREE_LIMIT = 10
        sub_obj = event["data"]["object"]
        sub = sub_obj.to_dict() if hasattr(sub_obj, "to_dict") else dict(sub_obj)
        subscription_id = sub.get("id")

        print(f"Webhook cancelamento recebido: subscription_id={subscription_id}")

        if subscription_id:
            try:
                sb = _sb_admin()
                if sb is not None:
                    result = sb.table("perfis").update({
                        "plano": "free",
                        "backtests_limite": FREE_LIMIT,
                        "stripe_subscription_id": None
                    }).eq("stripe_subscription_id", subscription_id).execute()
                    print(f"Downgrade para free OK: {result}")
                else:
                    print("Downgrade ignorado: _sb_admin() retornou None (SUPABASE_URL/KEY ausentes)")
            except Exception as e:
                print(f"Supabase downgrade error: {e}")
                raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")

    return {"ok": True}


# ════════════════════════════════════════════════════════════
#  v3.0 — CATÁLOGO 40 ATIVOS (gating por plano)
#  7 categorias. Free: 11 | Pro: 30 | Elite (trader_pro): 40
# ════════════════════════════════════════════════════════════
import secrets as _secrets
from datetime import datetime as _dt, timezone as _tz, timedelta as _td

_PLANO_NIVEL = {"free": 0, "pro": 1, "trader_pro": 2, "elite": 2}

# plano: nivel mínimo p/ usar o ativo (0=free, 1=pro, 2=elite)
CATALOGO_ATIVOS = {
    "Índices Globais": [
        {"nome": "S&P500",    "ticker": "^GSPC",  "nivel": 0},
        {"nome": "NASDAQ",    "ticker": "^IXIC",  "nivel": 0},
        {"nome": "IBOVESPA",  "ticker": "^BVSP",  "nivel": 0},
        {"nome": "US30",      "ticker": "^DJI",   "nivel": 1},
        {"nome": "DAX40",     "ticker": "^GDAXI", "nivel": 1},
        {"nome": "FTSE100",   "ticker": "^FTSE",  "nivel": 2},
        {"nome": "NIKKEI225", "ticker": "^N225",  "nivel": 2},
    ],
    "Forex": [
        {"nome": "EUR/USD", "ticker": "EURUSD=X", "nivel": 0},
        {"nome": "USD/BRL", "ticker": "BRL=X",    "nivel": 0},
        {"nome": "GBP/USD", "ticker": "GBPUSD=X", "nivel": 1},
        {"nome": "USD/JPY", "ticker": "JPY=X",    "nivel": 1},
        {"nome": "AUD/USD", "ticker": "AUDUSD=X", "nivel": 1},
        {"nome": "USD/CAD", "ticker": "CAD=X",    "nivel": 1},
    ],
    "Commodities": [
        {"nome": "XAU/USD (Ouro)",    "ticker": "GC=F", "nivel": 1},  # TRAVADO no Free: carro-chefe = isca
        {"nome": "XAG/USD (Prata)",   "ticker": "SI=F", "nivel": 1},
        {"nome": "Petróleo WTI",      "ticker": "CL=F", "nivel": 1},
        {"nome": "Gás Natural",       "ticker": "NG=F", "nivel": 2},
    ],
    "Cripto": [
        {"nome": "BTC/USD", "ticker": "BTC-USD", "nivel": 0},
        {"nome": "ETH/USD", "ticker": "ETH-USD", "nivel": 0},
        {"nome": "SOL/USD", "ticker": "SOL-USD", "nivel": 2},
        {"nome": "BNB/USD", "ticker": "BNB-USD", "nivel": 2},
    ],
    "Magnificent 7": [
        {"nome": "Apple",     "ticker": "AAPL",  "nivel": 0},
        {"nome": "NVIDIA",    "ticker": "NVDA",  "nivel": 0},
        {"nome": "Microsoft", "ticker": "MSFT",  "nivel": 1},
        {"nome": "Google",    "ticker": "GOOGL", "nivel": 1},
        {"nome": "Amazon",    "ticker": "AMZN",  "nivel": 1},
        {"nome": "Meta",      "ticker": "META",  "nivel": 1},
        {"nome": "Tesla",     "ticker": "TSLA",  "nivel": 1},
    ],
    "Ações Pro": [
        {"nome": "JPMorgan",  "ticker": "JPM",  "nivel": 1},
        {"nome": "Visa",      "ticker": "V",    "nivel": 1},
        {"nome": "Coca-Cola", "ticker": "KO",   "nivel": 1},
        {"nome": "Disney",    "ticker": "DIS",  "nivel": 2},
        {"nome": "Netflix",   "ticker": "NFLX", "nivel": 2},
        {"nome": "AMD",       "ticker": "AMD",  "nivel": 2},
    ],
    "B3 — Brasil": [
        {"nome": "Petrobras PN", "ticker": "PETR4.SA", "nivel": 0},
        {"nome": "Vale ON",      "ticker": "VALE3.SA", "nivel": 0},
        {"nome": "Itaú PN",      "ticker": "ITUB4.SA", "nivel": 1},
        {"nome": "Bradesco PN",  "ticker": "BBDC4.SA", "nivel": 1},
        {"nome": "WEG ON",       "ticker": "WEGE3.SA", "nivel": 2},
        {"nome": "Magazine Luiza","ticker": "MGLU3.SA","nivel": 2},
    ],
}

# Integra todos no mapa de tickers usado pelo motor de backtest
for _cat, _itens in CATALOGO_ATIVOS.items():
    for _a in _itens:
        ATIVOS_MAP.setdefault(_a["nome"], _a["ticker"])

class ResgateReq(BaseModel):
    user_id: str
    codigo: str


@app.post("/resgatar-codigo")
def resgatar_codigo(req: ResgateReq):
    """Resgata um código de acesso cortesia. Eleva o plano e grava a validade."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(500, {"code": "indisponivel", "msg": "Serviço indisponível. Tente mais tarde."})
    code = (req.codigo or "").strip().upper()
    if not code or not req.user_id:
        raise HTTPException(400, {"code": "invalido", "msg": "Código inválido."})
    # busca o código
    row = None
    try:
        r = sb.table("codigos_acesso").select("*").eq("codigo", code).single().execute()
        row = r.data
    except Exception:
        row = None
    if not row:
        raise HTTPException(404, {"code": "nao_encontrado", "msg": "Código não encontrado."})
    if row.get("ativo") is False:
        raise HTTPException(403, {"code": "inativo", "msg": "Este código foi desativado."})
    if row.get("usado"):
        raise HTTPException(409, {"code": "ja_usado", "msg": "Este código já foi utilizado."})
    plano = row.get("plano") or "trader_pro"
    dias = int(row.get("dias") or 30)
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone.utc)
    ate = (agora + timedelta(days=dias)).isoformat()
    # eleva o plano do usuário com validade
    try:
        sb.table("perfis").update({"plano": plano, "plano_valido_ate": ate}).eq("id", req.user_id).execute()
    except Exception as e:
        raise HTTPException(500, {"code": "erro_perfil", "msg": f"Não consegui aplicar o acesso: {e}"})
    # marca o código como usado (1 uso só)
    try:
        sb.table("codigos_acesso").update({
            "usado": True, "usado_por": req.user_id, "usado_em": agora.isoformat()
        }).eq("codigo", code).execute()
    except Exception:
        pass
    return {"ok": True, "plano": plano, "dias": dias, "valido_ate": ate}


@app.get("/ativos/catalogo")
def ativos_catalogo(plano: str = "free"):
    """Catálogo completo com flag 'bloqueado' conforme o plano do usuário."""
    nivel_user = _PLANO_NIVEL.get(plano, 0)
    out = {}
    total, liberados = 0, 0
    for cat, itens in CATALOGO_ATIVOS.items():
        out[cat] = []
        for a in itens:
            total += 1
            bloq = a["nivel"] > nivel_user
            if not bloq:
                liberados += 1
            out[cat].append({**a, "bloqueado": bloq})
    return {"catalogo": out, "total": total, "liberados": liberados, "plano": plano}


# ════════════════════════════════════════════════════════════
#  GATING DE 3 NÍVEIS (v3.9) — Free=isca / Pro / Trader Pro
#  Free: 3 backtests no TOTAL + catálogo limitado (XAU travado).
#  Pro/Trader Pro: ilimitado. Contador mora em perfis.free_tests_usados.
#  SQL necessário (rodar no Supabase ANTES do deploy):
#    alter table perfis add column if not exists free_tests_usados int not null default 0;
# ════════════════════════════════════════════════════════════
LIMITE_FREE_TESTS = 3

# nível por ticker, montado uma vez a partir do catálogo
_NIVEL_POR_TICKER = {}
for _c, _its in CATALOGO_ATIVOS.items():
    for _a in _its:
        _NIVEL_POR_TICKER[_a["ticker"]] = _a.get("nivel", 0)

def _nivel_do_ativo(ativo: str) -> int:
    tk = ATIVOS_MAP.get(ativo, ativo)           # nome -> ticker
    return _NIVEL_POR_TICKER.get(tk, 0)         # desconhecido = liberado (fail-open)

def _perfil_plano_e_creditos(user_id: str):
    """Retorna (plano, free_tests_usados, sb). Tolera coluna ausente/perfil novo."""
    try:
        sb = _sb_admin()
        if sb is None:
            return ("free", 0, None)
        try:
            r = sb.table("perfis").select("plano,free_tests_usados,plano_valido_ate").eq("id", user_id).single().execute()
            d = r.data or {}
            plano_ef = _plano_vigente(d.get("plano"), d.get("plano_valido_ate"))
            return (plano_ef, int(d.get("free_tests_usados") or 0), sb)
        except Exception:
            r = sb.table("perfis").select("plano,free_tests_usados").eq("id", user_id).single().execute()
            d = r.data or {}
            return (d.get("plano") or "free", int(d.get("free_tests_usados") or 0), sb)
    except Exception:
        # coluna free_tests_usados pode não existir ainda -> lê só o plano
        try:
            sb = _sb_admin()
            r = sb.table("perfis").select("plano").eq("id", user_id).single().execute()
            return ((r.data or {}).get("plano") or "free", 0, sb)
        except Exception:
            return ("free", 0, None)

def _email_confirmado(user_id):
    """True se o email do usuário está confirmado. Anti multi-conta no Free.
       FALHA ABERTA de propósito: se a checagem der erro, NÃO trava o usuário
       legítimo (preferimos deixar passar a bloquear quem tem direito)."""
    try:
        sb = _sb_admin()
        if sb is None:
            return True
        resp = sb.auth.admin.get_user_by_id(user_id)
        user = getattr(resp, "user", None)
        if user is None and isinstance(resp, dict):
            user = resp.get("user")
        ts = getattr(user, "email_confirmed_at", None) if user is not None else None
        if ts is None and isinstance(user, dict):
            ts = user.get("email_confirmed_at")
        return bool(ts)
    except Exception as _e:
        import sys as _sys
        print(f"[GATING] checagem email_confirmado falhou (deixando passar): {_e}", file=_sys.stderr)
        return True


def _consumir_credito_backtest(user_id, ativo: str):
    """Porteiro chamado no topo dos endpoints de backtest.
       Levanta HTTPException com detail ESTRUTURADO pro front reagir."""
    if not user_id:
        raise HTTPException(status_code=401, detail={
            "code": "login_necessario",
            "msg": "Crie uma conta grátis pra rodar seu backtest."})
    plano, usados, sb = _perfil_plano_e_creditos(user_id)
    nivel_user = _PLANO_NIVEL.get(plano, 0)
    # ativo bloqueado pro plano (ex.: Free tentando XAU)
    if _nivel_do_ativo(ativo) > nivel_user:
        raise HTTPException(status_code=403, detail={
            "code": "ativo_bloqueado", "plano": plano, "ativo": ativo,
            "msg": "Esse ativo faz parte de um plano superior."})
    # pago = ilimitado
    if nivel_user >= 1:
        return {"plano": plano, "ilimitado": True}
    # free precisa de email confirmado (anti multi-conta com emails descartáveis)
    if not _email_confirmado(user_id):
        raise HTTPException(status_code=403, detail={
            "code": "email_nao_confirmado",
            "msg": "Confirme seu email para liberar seus 3 backtests gratuitos."})
    # free = consome 1 dos 3
    if usados >= LIMITE_FREE_TESTS:
        raise HTTPException(status_code=402, detail={
            "code": "free_esgotado", "usados": usados, "limite": LIMITE_FREE_TESTS,
            "msg": "Você usou seus 3 backtests gratuitos."})
    novos = usados + 1
    if sb is not None:
        try:
            sb.table("perfis").update({"free_tests_usados": novos}).eq("id", user_id).execute()
        except Exception as _e:
            import sys as _sys
            print(f"[GATING] não consegui gravar free_tests_usados (coluna existe?): {_e}", file=_sys.stderr)
    return {"plano": plano, "ilimitado": False, "usados": novos,
            "restantes": max(0, LIMITE_FREE_TESTS - novos)}

@app.get("/free/status")
def free_status(user_id: str = ""):
    """Front consulta pra mostrar 'X de 3' e saber se congelou — sem rodar teste."""
    if not user_id:
        return {"logado": False, "plano": "free", "usados": 0,
                "limite": LIMITE_FREE_TESTS, "restantes": LIMITE_FREE_TESTS, "congelado": False}
    plano, usados, _ = _perfil_plano_e_creditos(user_id)
    if _PLANO_NIVEL.get(plano, 0) >= 1:
        return {"logado": True, "plano": plano, "ilimitado": True, "congelado": False}
    return {"logado": True, "plano": plano, "ilimitado": False,
            "usados": usados, "limite": LIMITE_FREE_TESTS,
            "restantes": max(0, LIMITE_FREE_TESTS - usados),
            "congelado": usados >= LIMITE_FREE_TESTS}


# ════════════════════════════════════════════════════════════
#  v3.0 — ESTRATÉGIAS PRONTAS (galeria com 10)
#  2 assinaturas da casa + 8 clássicas. Código backtesting.py.
#  Sempre honesto: nenhuma promessa de retorno futuro.
# ════════════════════════════════════════════════════════════
ESTRATEGIAS_PRONTAS = [
    {
        "id": "canal_ema20_hl", "casa": False, "emoji": "🛤️",
        "nome": "Canal EMA 20 High/Low",
        "desc": "Assinatura BotBacktest: canal entre EMA20 das máximas e EMA20 das mínimas. Rompe pra cima = compra; rompe pra baixo = venda; dentro do canal = lateral, não opera.",
        "tags": ["TENDÊNCIA", "EMA"], "nivel": "intermediário",
        "mercados": ["XAU/USD (Ouro)", "NAS100", "BTC/USD"],
        "codigo": '''from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

class CanalEMA20HL(Strategy):
    n = 20
    def init(self):
        self.ema_high = self.I(EMA, self.data.High, self.n)
        self.ema_low  = self.I(EMA, self.data.Low,  self.n)
    def next(self):
        preco = self.data.Close[-1]
        if preco > self.ema_high[-1] and not self.position.is_long:
            self.position.close()
            self.buy()
        elif preco < self.ema_low[-1] and not self.position.is_short:
            self.position.close()
            self.sell()
        # dentro do canal = lateralizacao, nao abre nada
'''
    },
    {
        "id": "tendencia_diaria_piramide", "casa": False, "emoji": "🔺",
        "nome": "Tendência Diária com Pirâmide",
        "desc": "Assinatura BotBacktest: lê a direção do D1 pela manhã, entra SEMPRE a favor (nunca contra), pirâmide na mesma direção, trailing protege o lucro. Valide por ativo antes de automatizar.",
        "tags": ["TENDÊNCIA", "PIRÂMIDE"], "nivel": "avançado",
        "mercados": ["XAU/USD (Ouro)", "US30", "S&P500"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

class TendenciaDiariaPiramide(Strategy):
    n = 20
    max_piramide = 3
    trail_pct = 0.015   # trailing 1.5%
    def init(self):
        self.ema_high = self.I(EMA, self.data.High, self.n)
        self.ema_low  = self.I(EMA, self.data.Low,  self.n)
        self.topo = None
    def next(self):
        preco = self.data.Close[-1]
        alta  = preco > self.ema_high[-1]
        baixa = preco < self.ema_low[-1]
        # trailing stop manual
        if self.position.is_long:
            self.topo = max(self.topo or preco, preco)
            if preco < self.topo * (1 - self.trail_pct):
                self.position.close(); self.topo = None; return
        # entra/piramida apenas A FAVOR da tendencia
        if alta and len(self.trades) < self.max_piramide:
            self.buy()
        elif baixa and self.position.is_long:
            self.position.close(); self.topo = None
'''
    },
    {
        "id": "topo_fundo_duplo", "casa": False, "emoji": "⛰️",
        "nome": "Topo Duplo / Fundo Duplo",
        "desc": "Assinatura BotBacktest: dois topos na mesma altura + rompimento da linha do pescoço (o fundo entre eles) = venda. Mesma família do Ombro-Cabeça-Ombro: quando a cabeça não se forma, vira Topo Duplo — a entrada é a mesma. Espelhado no Fundo Duplo / OCO invertido = compra (mais difícil de ver a olho; o detector acha pra você). Alvo pela altura do padrão, stop atrás dos topos/fundos.",
        "tags": ["PRICE ACTION", "REVERSÃO"], "nivel": "avançado",
        "mercados": ["XAU/USD (Ouro)", "BTC/USD", "NASDAQ"],
        "codigo": '''from backtesting import Strategy

class TopoFundoDuplo(Strategy):
    k = 5              # candles de cada lado p/ confirmar um pivo (topo/fundo)
    tolerancia = 0.004 # 0.4% de diferenca maxima entre os dois topos/fundos
    validade = 40      # padrao expira depois de N candles sem rompimento

    def init(self):
        self.pivos_alta = []    # swing highs confirmados: (indice, preco)
        self.pivos_baixa = []   # swing lows confirmados
        self.stop = None
        self.alvo = None
        self.usado_alta = -1
        self.usado_baixa = -1

    def next(self):
        h, l, c = self.data.High, self.data.Low, self.data.Close
        i = len(c) - 1
        if i < 2 * self.k + 1:
            return

        # confirma pivo k candles atras (precisa de k candles dos dois lados)
        j = i - self.k
        jan_h = [h[j + m] for m in range(-self.k, self.k + 1)]
        jan_l = [l[j + m] for m in range(-self.k, self.k + 1)]
        if h[j] == max(jan_h):
            self.pivos_alta.append((j, h[j]))
        if l[j] == min(jan_l):
            self.pivos_baixa.append((j, l[j]))

        # gestao de posicao aberta (alvo pela altura / stop atras do padrao)
        if self.position:
            if self.position.is_short:
                if c[-1] <= self.alvo or c[-1] >= self.stop:
                    self.position.close()
            else:
                if c[-1] >= self.alvo or c[-1] <= self.stop:
                    self.position.close()
            return

        # TOPO DUPLO -> rompeu a linha do pescoco pra baixo = venda
        if len(self.pivos_alta) >= 2:
            (i1, p1), (i2, p2) = self.pivos_alta[-2], self.pivos_alta[-1]
            recente = (i - i2) <= self.validade
            mesmo_nivel = abs(p2 - p1) / p1 <= self.tolerancia
            if recente and mesmo_nivel and i2 != self.usado_alta:
                pescoco = min(l[m] for m in range(i1, i2 + 1))
                if c[-1] < pescoco:
                    altura = (p1 + p2) / 2 - pescoco
                    self.stop = max(p1, p2)
                    self.alvo = pescoco - altura
                    self.usado_alta = i2
                    self.sell()
                    return

        # FUNDO DUPLO -> rompeu o topo central pra cima = compra
        if len(self.pivos_baixa) >= 2:
            (i1, p1), (i2, p2) = self.pivos_baixa[-2], self.pivos_baixa[-1]
            recente = (i - i2) <= self.validade
            mesmo_nivel = abs(p2 - p1) / p1 <= self.tolerancia
            if recente and mesmo_nivel and i2 != self.usado_baixa:
                pescoco = max(h[m] for m in range(i1, i2 + 1))
                if c[-1] > pescoco:
                    altura = pescoco - (p1 + p2) / 2
                    self.stop = min(p1, p2)
                    self.alvo = pescoco + altura
                    self.usado_baixa = i2
                    self.buy()
'''
    },
    {
        "id": "cruzamento_ema_9_21", "casa": False, "emoji": "📊",
        "nome": "Cruzamento EMA 9/21",
        "desc": "Clássica de tendência: EMA9 cruza acima da EMA21 = compra; cruza abaixo = sai/inverte.",
        "tags": ["TENDÊNCIA", "EMA"], "nivel": "iniciante",
        "mercados": ["EUR/USD", "S&P500"],
        "codigo": '''from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

class CruzamentoEMA(Strategy):
    rapida = 9
    lenta = 21
    def init(self):
        self.e1 = self.I(EMA, self.data.Close, self.rapida)
        self.e2 = self.I(EMA, self.data.Close, self.lenta)
    def next(self):
        if crossover(self.e1, self.e2):
            self.position.close(); self.buy()
        elif crossover(self.e2, self.e1):
            self.position.close(); self.sell()
'''
    },
    {
        "id": "rsi_reversao", "casa": False, "emoji": "📈",
        "nome": "RSI Sobrevenda/Sobrecompra",
        "desc": "Reversão: compra com RSI < 30 (sobrevenda), vende com RSI > 70 (sobrecompra).",
        "tags": ["REVERSÃO", "RSI"], "nivel": "iniciante",
        "mercados": ["Ações", "Cripto"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def RSI(serie, n=14):
    s = pd.Series(serie)
    delta = s.diff()
    ganho = delta.clip(lower=0).rolling(n).mean()
    perda = (-delta.clip(upper=0)).rolling(n).mean()
    rs = ganho / perda
    return 100 - (100 / (1 + rs))

class RSIReversao(Strategy):
    n = 14
    def init(self):
        self.rsi = self.I(RSI, self.data.Close, self.n)
    def next(self):
        if self.rsi[-1] < 30 and not self.position.is_long:
            self.position.close(); self.buy()
        elif self.rsi[-1] > 70 and self.position.is_long:
            self.position.close()
'''
    },
    {
        "id": "bollinger_reversao", "casa": False, "emoji": "🎯",
        "nome": "Bandas de Bollinger — Reversão",
        "desc": "Compra ao tocar a banda inferior, realiza na média central. Funciona melhor em mercado lateral.",
        "tags": ["REVERSÃO", "BOLLINGER"], "nivel": "intermediário",
        "mercados": ["Forex", "Índices"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def BB(serie, n=20, k=2.0):
    s = pd.Series(serie)
    media = s.rolling(n).mean()
    desv = s.rolling(n).std()
    return media, media + k*desv, media - k*desv

class BollingerReversao(Strategy):
    n = 20
    def init(self):
        self.media, self.sup, self.inf = self.I(BB, self.data.Close, self.n)
    def next(self):
        preco = self.data.Close[-1]
        if preco <= self.inf[-1] and not self.position.is_long:
            self.buy()
        elif self.position.is_long and preco >= self.media[-1]:
            self.position.close()
'''
    },
    {
        "id": "rompimento_donchian", "casa": False, "emoji": "💥",
        "nome": "Rompimento Donchian 20",
        "desc": "Estilo Turtle Traders: compra no rompimento da máxima de 20 períodos, sai na mínima de 10.",
        "tags": ["ROMPIMENTO", "DONCHIAN"], "nivel": "intermediário",
        "mercados": ["Commodities", "Cripto"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def MAX_N(serie, n):
    return pd.Series(serie).rolling(n).max()

def MIN_N(serie, n):
    return pd.Series(serie).rolling(n).min()

class Donchian(Strategy):
    n_entrada = 20
    n_saida = 10
    def init(self):
        self.topo = self.I(MAX_N, self.data.High, self.n_entrada)
        self.fundo = self.I(MIN_N, self.data.Low, self.n_saida)
    def next(self):
        preco = self.data.Close[-1]
        if preco >= self.topo[-2] and not self.position.is_long:
            self.buy()
        elif self.position.is_long and preco <= self.fundo[-2]:
            self.position.close()
'''
    },
    {
        "id": "macd_tendencia", "casa": False, "emoji": "🌊",
        "nome": "MACD Tendência",
        "desc": "Compra quando a linha MACD cruza acima da linha de sinal; sai no cruzamento contrário.",
        "tags": ["TENDÊNCIA", "MACD"], "nivel": "iniciante",
        "mercados": ["Ações", "Índices"],
        "codigo": '''from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd

def MACD_LINHA(serie, rapida=12, lenta=26):
    s = pd.Series(serie)
    return s.ewm(span=rapida, adjust=False).mean() - s.ewm(span=lenta, adjust=False).mean()

def MACD_SINAL(serie, rapida=12, lenta=26, sinal=9):
    macd = MACD_LINHA(serie, rapida, lenta)
    return macd.ewm(span=sinal, adjust=False).mean()

class MACDTendencia(Strategy):
    def init(self):
        self.macd  = self.I(MACD_LINHA, self.data.Close)
        self.sinal = self.I(MACD_SINAL, self.data.Close)
    def next(self):
        if crossover(self.macd, self.sinal):
            self.position.close(); self.buy()
        elif crossover(self.sinal, self.macd):
            self.position.close()
'''
    },
    {
        "id": "engolfo_tendencia", "casa": False, "emoji": "🕯️",
        "nome": "Engolfo a Favor da Tendência",
        "desc": "Price action: candle de engolfo de alta acima da EMA50 = compra. Filtro de tendência evita operar contra.",
        "tags": ["PRICE ACTION", "CANDLE"], "nivel": "intermediário",
        "mercados": ["XAU/USD (Ouro)", "Forex"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

class EngolfoTendencia(Strategy):
    n_ema = 50
    def init(self):
        self.ema = self.I(EMA, self.data.Close, self.n_ema)
    def next(self):
        if len(self.data.Close) < 2:
            return
        o1, c1 = self.data.Open[-2], self.data.Close[-2]
        o2, c2 = self.data.Open[-1], self.data.Close[-1]
        engolfo_alta = (c1 < o1) and (c2 > o2) and (c2 > o1) and (o2 < c1)
        acima_ema = self.data.Close[-1] > self.ema[-1]
        if engolfo_alta and acima_ema and not self.position.is_long:
            self.buy()
        elif self.position.is_long and self.data.Close[-1] < self.ema[-1]:
            self.position.close()
'''
    },
    {
        "id": "abertura_gap", "casa": False, "emoji": "🌅",
        "nome": "Gap de Abertura",
        "desc": "Gap de alta acima de 0,5% na abertura com fechamento anterior forte = segue o movimento no dia.",
        "tags": ["GAP", "INTRADAY"], "nivel": "avançado",
        "mercados": ["Ações", "Índices"],
        "codigo": '''from backtesting import Strategy

class GapAbertura(Strategy):
    gap_min = 0.005   # 0,5%
    def init(self):
        pass
    def next(self):
        if len(self.data.Close) < 2:
            return
        gap = (self.data.Open[-1] - self.data.Close[-2]) / self.data.Close[-2]
        if gap >= self.gap_min and not self.position.is_long:
            self.buy()
        elif self.position.is_long and gap <= -self.gap_min:
            self.position.close()
'''
    },
    {
        "id": "media_atr_trailing", "casa": False, "emoji": "🛡️",
        "nome": "Média + Trailing ATR",
        "desc": "Entra na tendência (preço acima da SMA50) e protege com trailing stop de 2x ATR — deixa o lucro correr.",
        "tags": ["TENDÊNCIA", "ATR", "TRAILING"], "nivel": "intermediário",
        "mercados": ["Commodities", "Cripto", "Índices"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def SMA(serie, n):
    return pd.Series(serie).rolling(n).mean()

def ATR(high, low, close, n=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

class MediaATRTrailing(Strategy):
    n_sma = 50
    mult_atr = 2.0
    def init(self):
        self.sma = self.I(SMA, self.data.Close, self.n_sma)
        self.atr = self.I(ATR, self.data.High, self.data.Low, self.data.Close)
        self.stop = None
    def next(self):
        preco = self.data.Close[-1]
        if self.position.is_long:
            novo_stop = preco - self.mult_atr * self.atr[-1]
            self.stop = max(self.stop or novo_stop, novo_stop)
            if preco <= self.stop:
                self.position.close(); self.stop = None; return
        if preco > self.sma[-1] and not self.position.is_long:
            self.buy()
            self.stop = preco - self.mult_atr * self.atr[-1]
'''
    },
    {
        "id": "sr_dia_anterior", "casa": False, "emoji": "📐",
        "nome": "Suporte & Resistência do Dia Anterior",
        "desc": "Price action clássico: a máxima e a mínima de ontem viram as referências de hoje. Fechou acima da máxima de ontem = compra (rompimento); abaixo da mínima = venda. Sai quando o preço cruza a referência oposta.",
        "tags": ["PRICE ACTION", "ROMPIMENTO", "S/R"], "nivel": "intermediário",
        "mercados": ["XAU/USD (Ouro)", "NASDAQ", "Índices"],
        "codigo": '''from backtesting import Strategy

class SuporteResistenciaOntem(Strategy):
    # Maxima/minima do dia anterior como suporte e resistencia de hoje.
    # No diario, vale a maxima/minima do candle anterior (mesma logica).

    def init(self):
        self.dia = None
        self.h_ontem = None
        self.l_ontem = None
        self.h_hoje = None
        self.l_hoje = None

    def next(self):
        d = self.data.index[-1].date()
        h, l, c = self.data.High[-1], self.data.Low[-1], self.data.Close[-1]

        if self.dia is None:
            self.dia, self.h_hoje, self.l_hoje = d, h, l
            return
        if d != self.dia:
            # virou o dia: ontem fica congelado como referencia
            self.h_ontem, self.l_ontem = self.h_hoje, self.l_hoje
            self.dia, self.h_hoje, self.l_hoje = d, h, l
        else:
            self.h_hoje = max(self.h_hoje, h)
            self.l_hoje = min(self.l_hoje, l)

        if self.h_ontem is None:
            return

        if not self.position:
            if c > self.h_ontem:
                self.buy()      # rompeu a resistencia de ontem
            elif c < self.l_ontem:
                self.sell()     # rompeu o suporte de ontem
        else:
            if self.position.is_long and c < self.l_ontem:
                self.position.close()
            elif self.position.is_short and c > self.h_ontem:
                self.position.close()
'''
    },
    {
        "id": "microcanal", "casa": False, "emoji": "🪜",
        "nome": "Microcanal de Impulso",
        "desc": "Price action: sequência de mínimas ascendentes coladas na EMA curta = impulso comprador (microcanal). Entra na continuação; sai quando um candle perde a mínima do anterior (canal quebrado).",
        "tags": ["PRICE ACTION", "TENDÊNCIA", "IMPULSO"], "nivel": "avançado",
        "mercados": ["XAU/USD (Ouro)", "BTC/USD", "NAS100"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

class Microcanal(Strategy):
    n_seq = 3    # quantas minimas ascendentes seguidas formam o microcanal
    n_ema = 9    # EMA curta de referencia do impulso

    def init(self):
        self.ema = self.I(EMA, self.data.Close, self.n_ema)

    def next(self):
        l, c = self.data.Low, self.data.Close
        i = len(c) - 1
        if i < self.n_seq + 1:
            return

        # quebrou a minima do candle anterior = microcanal acabou
        if self.position:
            if c[-1] < l[-2]:
                self.position.close()
            return

        minimas_ascendentes = all(l[-k] > l[-k - 1] for k in range(1, self.n_seq + 1))
        acima_ema = c[-1] > self.ema[-1]
        if minimas_ascendentes and acima_ema:
            self.buy()
'''
    },
    {
        "id": "fechamento_ima", "casa": False, "emoji": "🧲",
        "nome": "Fechamento Anterior como Ímã",
        "desc": "Abriu longe do fechamento de ontem? O preço tende a voltar pra ele (efeito ímã / fechamento de gap). Opera a volta: alvo no fechamento anterior, stop na continuação do gap. Versão multi-mercado do clássico ajuste dos futuros.",
        "tags": ["GAP", "REVERSÃO", "ÍMÃ"], "nivel": "intermediário",
        "mercados": ["Índices", "Ações", "XAU/USD (Ouro)"],
        "codigo": '''from backtesting import Strategy

class FechamentoIma(Strategy):
    gap_min = 0.003   # 0,3% de distancia minima na abertura p/ operar a volta

    def init(self):
        self.dia = None
        self.fech_ontem = None
        self.fech_hoje = None
        self.alvo = None
        self.stop = None

    def next(self):
        d = self.data.index[-1].date()
        o, c = self.data.Open[-1], self.data.Close[-1]

        if self.dia is None:
            self.dia, self.fech_hoje = d, c
            return
        novo_dia = d != self.dia
        if novo_dia:
            self.fech_ontem = self.fech_hoje
            self.dia = d
        self.fech_hoje = c

        if self.fech_ontem is None:
            return

        # gestao: alvo no fechamento de ontem, stop na continuacao
        if self.position:
            if self.position.is_long and (c >= self.alvo or c <= self.stop):
                self.position.close()
            elif self.position.is_short and (c <= self.alvo or c >= self.stop):
                self.position.close()
            return

        # so avalia na abertura de um dia novo
        if novo_dia:
            gap = (o - self.fech_ontem) / self.fech_ontem
            if gap >= self.gap_min:
                # abriu acima: aposta na volta ao fechamento (vende)
                self.alvo = self.fech_ontem
                self.stop = o * (1 + abs(gap))
                self.sell()
            elif gap <= -self.gap_min:
                # abriu abaixo: aposta na volta ao fechamento (compra)
                self.alvo = self.fech_ontem
                self.stop = o * (1 - abs(gap))
                self.buy()
'''
    },
]

# ── Tradução das estratégias prontas (nome+desc) PT/EN/ES — lógica fica no id ──
ESTRATEGIAS_I18N = {
  "canal_ema20_hl": {
    "en": {"nome": "EMA 20 High/Low Channel", "desc": "Channel between the EMA20 of the highs and the EMA20 of the lows. Breaks above = buy; breaks below = sell; inside the channel = ranging, no trade."},
    "es": {"nome": "Canal EMA 20 High/Low", "desc": "Canal entre la EMA20 de los máximos y la EMA20 de los mínimos. Rompe hacia arriba = compra; rompe hacia abajo = venta; dentro del canal = lateral, no opera."}},
  "tendencia_diaria_piramide": {
    "en": {"nome": "Daily Trend with Pyramiding", "desc": "Reads the D1 direction in the morning, ALWAYS enters with the trend (never against), pyramids in the same direction, trailing protects profit. Validate per asset before automating."},
    "es": {"nome": "Tendencia Diaria con Pirámide", "desc": "Lee la dirección del D1 por la mañana, entra SIEMPRE a favor (nunca en contra), pirámide en la misma dirección, trailing protege la ganancia. Valida por activo antes de automatizar."}},
  "topo_fundo_duplo": {
    "en": {"nome": "Double Top / Double Bottom", "desc": "Two tops at the same height + a break of the neckline (the low between them) = sell. Same family as Head & Shoulders: when the head does not form, it becomes a Double Top — the entry is the same. Mirrored in the Double Bottom / inverted H&S = buy (harder to spot by eye; the detector finds it for you). Target by the pattern height, stop behind the tops/bottoms."},
    "es": {"nome": "Doble Techo / Doble Suelo", "desc": "Dos techos a la misma altura + ruptura de la línea del cuello (el suelo entre ellos) = venta. Misma familia que el Hombro-Cabeza-Hombro: cuando la cabeza no se forma, se vuelve Doble Techo — la entrada es la misma. Reflejado en el Doble Suelo / HCH invertido = compra (más difícil de ver a simple vista; el detector lo encuentra por ti). Objetivo por la altura del patrón, stop detrás de los techos/suelos."}},
  "cruzamento_ema_9_21": {
    "en": {"nome": "EMA 9/21 Crossover", "desc": "Trend classic: EMA9 crosses above EMA21 = buy; crosses below = exit/reverse."},
    "es": {"nome": "Cruce EMA 9/21", "desc": "Clásica de tendencia: EMA9 cruza por encima de la EMA21 = compra; cruza por debajo = sale/invierte."}},
  "rsi_reversao": {
    "en": {"nome": "RSI Oversold/Overbought", "desc": "Reversal: buy with RSI < 30 (oversold), sell with RSI > 70 (overbought)."},
    "es": {"nome": "RSI Sobreventa/Sobrecompra", "desc": "Reversión: compra con RSI < 30 (sobreventa), vende con RSI > 70 (sobrecompra)."}},
  "bollinger_reversao": {
    "en": {"nome": "Bollinger Bands — Reversal", "desc": "Buy when touching the lower band, take profit at the middle average. Works best in ranging markets."},
    "es": {"nome": "Bandas de Bollinger — Reversión", "desc": "Compra al tocar la banda inferior, realiza en la media central. Funciona mejor en mercado lateral."}},
  "rompimento_donchian": {
    "en": {"nome": "Donchian 20 Breakout", "desc": "Turtle Traders style: buy on the breakout of the 20-period high, exit at the 10-period low."},
    "es": {"nome": "Ruptura Donchian 20", "desc": "Estilo Turtle Traders: compra en la ruptura del máximo de 20 períodos, sale en el mínimo de 10."}},
  "macd_tendencia": {
    "en": {"nome": "MACD Trend", "desc": "Buy when the MACD line crosses above the signal line; exit on the opposite cross."},
    "es": {"nome": "MACD Tendencia", "desc": "Compra cuando la línea MACD cruza por encima de la línea de señal; sale en el cruce contrario."}},
  "engolfo_tendencia": {
    "en": {"nome": "Trend-Following Engulfing", "desc": "Price action: a bullish engulfing candle above the EMA50 = buy. The trend filter avoids trading against it."},
    "es": {"nome": "Envolvente a Favor de la Tendencia", "desc": "Price action: vela envolvente alcista por encima de la EMA50 = compra. El filtro de tendencia evita operar en contra."}},
  "abertura_gap": {
    "en": {"nome": "Opening Gap", "desc": "An opening gap up above 0.5% with a strong prior close = follow the move for the day."},
    "es": {"nome": "Gap de Apertura", "desc": "Gap alcista por encima del 0,5% en la apertura con cierre anterior fuerte = sigue el movimiento del día."}},
  "media_atr_trailing": {
    "en": {"nome": "Moving Average + ATR Trailing", "desc": "Enters the trend (price above the SMA50) and protects with a 2x ATR trailing stop — lets profit run."},
    "es": {"nome": "Media + Trailing ATR", "desc": "Entra en la tendencia (precio por encima de la SMA50) y protege con un trailing stop de 2x ATR — deja correr la ganancia."}},
  "sr_dia_anterior": {
    "en": {"nome": "Previous Day Support & Resistance", "desc": "Classic price action: yesterday's high and low become today's references. Closing above yesterday's high = buy (breakout); below the low = sell. Exits when price crosses the opposite reference."},
    "es": {"nome": "Soporte y Resistencia del Día Anterior", "desc": "Price action clásico: el máximo y el mínimo de ayer se vuelven las referencias de hoy. Cierre por encima del máximo de ayer = compra (ruptura); por debajo del mínimo = venta. Sale cuando el precio cruza la referencia opuesta."}},
  "microcanal": {
    "en": {"nome": "Impulse Micro-Channel", "desc": "Price action: a sequence of rising lows hugging the short EMA = buying impulse (micro-channel). Enters the continuation; exits when a candle loses the previous candle's low (channel broken)."},
    "es": {"nome": "Microcanal de Impulso", "desc": "Price action: secuencia de mínimos ascendentes pegados a la EMA corta = impulso comprador (microcanal). Entra en la continuación; sale cuando una vela pierde el mínimo de la anterior (canal roto)."}},
  "fechamento_ima": {
    "en": {"nome": "Previous Close as a Magnet", "desc": "Opened far from yesterday's close? Price tends to return to it (magnet effect / gap fill). Trades the return: target at the previous close, stop on the gap continuation. A multi-market version of the classic futures settlement."},
    "es": {"nome": "Cierre Anterior como Imán", "desc": "¿Abrió lejos del cierre de ayer? El precio tiende a volver a él (efecto imán / cierre de gap). Opera el regreso: objetivo en el cierre anterior, stop en la continuación del gap. Versión multimercado del clásico ajuste de futuros."}},
}

def _estrat_loc(est, lang, campo):
    """Nome/descrição de exibição no idioma; PT é o original. Lógica nunca usa isso (usa o id)."""
    if lang and lang != "pt":
        tr = ESTRATEGIAS_I18N.get(est.get("id"), {}).get(lang, {})
        if tr.get(campo):
            return tr[campo]
    return est.get(campo, "")


@app.get("/estrategias/prontas")
def estrategias_prontas(lang: str = "pt"):
    """Galeria das estratégias prontas (metadados + código), nome/desc no idioma pedido."""
    out = []
    for est in ESTRATEGIAS_PRONTAS:
        e = dict(est)
        e["nome"] = _estrat_loc(est, lang, "nome")
        e["desc"] = _estrat_loc(est, lang, "desc")
        out.append(e)
    return {"estrategias": out, "total": len(out)}


# ════════════════════════════════════════════════════════════
#  v3.0 — CONECTOR MT5 (read-only) + AGENTE BLOCO F
#  Princípio: o EA executa LOCAL na conta do usuário.
#  A nuvem só OBSERVA (snapshots read-only). Nunca comanda.
#  Nunca pede credenciais de corretora — apenas bot_token.
#  Agente: comenta CONSISTÊNCIA do trader vs plano validado.
#  Nunca comenta direção de mercado. Nunca promete retorno.
# ════════════════════════════════════════════════════════════

OFFLINE_APOS_SEGUNDOS = 180  # 3 min sem ping = offline

# Cooldown anti-spam por regra (minutos)
_AGENTE_COOLDOWN_MIN = {"F1": 60, "F2": 30, "F3": 15, "F4": 1440}

# Mapeia símbolo MT5 -> nome do ativo no catálogo (p/ cruzar com backtests)
_MT5_PARA_CATALOGO = {
    "XAUUSD": "XAU/USD", "GOLD": "XAU/USD",
    "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD",
    "US500": "S&P500", "SPX500": "S&P500",
    "NAS100": "NASDAQ", "USTEC": "NASDAQ",
    "US30": "US30", "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY", "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD",
    "USDBRL": "USD/BRL", "XAGUSD": "XAG/USD",
}

class ConectorRegistrar(BaseModel):
    user_id: str
    nome: str = "Meu Bot"
    simbolo: str = ""
    magic_number: Optional[int] = None

class ConectorSnapshot(BaseModel):
    bot_token: str
    conta_login: Optional[str] = None
    corretora: Optional[str] = None
    simbolo: Optional[str] = None
    magic_number: Optional[int] = None
    equity: Optional[float] = None
    balance: Optional[float] = None
    margem_livre: Optional[float] = None
    posicoes_abertas: int = 0
    lucro_flutuante: Optional[float] = None
    drawdown_atual: Optional[float] = None   # em % (ex: 4.2)
    direcao_d1: Optional[str] = None         # compra | venda | lateral
    padrao_ativo: Optional[str] = None
    detalhe: Optional[dict] = None

class ConectorEvento(BaseModel):
    bot_token: str
    tipo: str                                 # trade_aberto | trade_fechado | reversao | piramide | erro
    detalhe: Optional[dict] = None

class SugestaoLida(BaseModel):
    user_id: str
    sugestao_id: int


def _bot_por_token(sb, bot_token: str):
    try:
        r = sb.table("conector_bots").select("*").eq("bot_token", bot_token).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def _agente_em_cooldown(sb, user_id: str, regra: str) -> bool:
    """True se a regra já disparou dentro da janela de cooldown."""
    try:
        minutos = _AGENTE_COOLDOWN_MIN.get(regra, 60)
        corte = (_dt.now(_tz.utc) - _td(minutes=minutos)).isoformat()
        r = (sb.table("agente_sugestoes").select("id")
             .eq("user_id", user_id).eq("regra", regra)
             .gte("criado_em", corte).limit(1).execute())
        return bool(r.data)
    except Exception:
        return True  # na dúvida, não spamma


def _agente_emite(sb, user_id, regra, categoria, mensagem, severidade="info", contexto=None):
    try:
        sb.table("agente_sugestoes").insert({
            "user_id": user_id, "regra": regra, "categoria": categoria,
            "mensagem": mensagem, "severidade": severidade,
            "contexto_json": contexto or {},
        }).execute()
        sb.table("agente_eventos").insert({
            "user_id": user_id, "tipo": "sugestao_emitida", "regra": regra,
            "detalhe_json": {"mensagem": mensagem},
        }).execute()
    except Exception as e:
        print(f"[Agente] falha ao emitir {regra}: {e}")


def _agente_bloco_f(sb, user_id: str, bot: dict, snap: ConectorSnapshot):
    """
    BLOCO F — consistência vivo × backtest (regras puras, custo zero).
    F1: drawdown vivo chegou a 80%+ do max_drawdown testado p/ o ativo  -> alerta (cd 60min)
    F2: pirâmide além do plano (posições abertas > 3)                   -> atenção (cd 30min)
    F3: drawdown vivo SUPEROU o pior drawdown testado                   -> alerta (cd 15min)
    F4: operando símbolo SEM nenhum backtest validado                   -> atenção (cd 24h)
    O agente fala de DISCIPLINA contra o próprio plano. Nunca de mercado.
    """
    if not user_id:
        return 0
    emitidas = 0
    simbolo_mt5 = (snap.simbolo or bot.get("simbolo") or "").upper()
    ativo_catalogo = _MT5_PARA_CATALOGO.get(simbolo_mt5, simbolo_mt5)

    # Busca o pior (maior) drawdown testado pelo usuário nesse ativo
    max_dd_testado = None
    tem_backtest = False
    try:
        r = (sb.table("backtests_historico").select("max_drawdown")
             .eq("user_id", user_id).eq("ativo", ativo_catalogo)
             .order("criado_em", desc=True).limit(50).execute())
        dds = [abs(float(x["max_drawdown"])) for x in (r.data or []) if x.get("max_drawdown") is not None]
        tem_backtest = bool(r.data)
        if dds:
            max_dd_testado = max(dds)
    except Exception as e:
        print(f"[Agente F] consulta historico falhou: {e}")

    dd_vivo = abs(snap.drawdown_atual) if snap.drawdown_atual is not None else None

    # F3 — superou o testado (mais grave, avalia primeiro)
    if dd_vivo is not None and max_dd_testado and dd_vivo > max_dd_testado:
        if not _agente_em_cooldown(sb, user_id, "F3"):
            _agente_emite(sb, user_id, "F3", "posicao",
                f"O drawdown ao vivo em {ativo_catalogo} ({dd_vivo:.1f}%) já SUPEROU o pior cenário "
                f"do seu backtest ({max_dd_testado:.1f}%). O mercado está fora do que você validou. "
                f"Vale revisar a posição contra o seu plano.",
                "alerta", {"dd_vivo": dd_vivo, "dd_testado": max_dd_testado, "simbolo": simbolo_mt5})
            emitidas += 1
    # F1 — aproximando do testado (só se F3 não disparou)
    elif dd_vivo is not None and max_dd_testado and dd_vivo >= 0.8 * max_dd_testado:
        if not _agente_em_cooldown(sb, user_id, "F1"):
            _agente_emite(sb, user_id, "F1", "posicao",
                f"Drawdown ao vivo em {ativo_catalogo} ({dd_vivo:.1f}%) chegou a 80% do pior drawdown "
                f"do seu backtest ({max_dd_testado:.1f}%). Ainda dentro do plano, mas no limite dele.",
                "atencao", {"dd_vivo": dd_vivo, "dd_testado": max_dd_testado, "simbolo": simbolo_mt5})
            emitidas += 1

    # F2 — pirâmide além do plano
    if snap.posicoes_abertas and snap.posicoes_abertas > 3:
        if not _agente_em_cooldown(sb, user_id, "F2"):
            _agente_emite(sb, user_id, "F2", "intraday",
                f"{snap.posicoes_abertas} posições abertas em {ativo_catalogo} — acima das 3 da sua "
                f"pirâmide planejada. Exposição além do que foi testado.",
                "atencao", {"posicoes": snap.posicoes_abertas, "simbolo": simbolo_mt5})
            emitidas += 1

    # F4 — símbolo sem backtest validado
    if not tem_backtest:
        if not _agente_em_cooldown(sb, user_id, "F4"):
            _agente_emite(sb, user_id, "F4", "backtest",
                f"Você está operando {ativo_catalogo} ao vivo, mas não encontrei nenhum backtest seu "
                f"nesse ativo. Estratégia que funciona num ativo pode falhar em outro — vale validar "
                f"antes de seguir automatizado.",
                "atencao", {"simbolo": simbolo_mt5})
            emitidas += 1

    return emitidas


# ── ENDPOINTS DO CONECTOR ───────────────────────────────────

@app.post("/conector/registrar")
def conector_registrar(req: ConectorRegistrar):
    """Gera bot_token p/ o conector. Nunca pede credenciais de corretora."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    token = _secrets.token_hex(16)
    try:
        sb.table("conector_bots").insert({
            "user_id": req.user_id, "bot_token": token,
            "nome": req.nome, "simbolo": req.simbolo,
            "magic_number": req.magic_number,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao registrar bot: {e}")
    return {"ok": True, "bot_token": token,
            "instrucao": "Cole este token no conector (config). Ele identifica o bot — nunca compartilhe."}


@app.post("/conector/snapshot")
def conector_snapshot(snap: ConectorSnapshot):
    """Recebe snapshot read-only do conector. Atualiza ping, grava e roda o agente."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    bot = _bot_por_token(sb, snap.bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    user_id = bot.get("user_id")
    agora = _dt.now(_tz.utc).isoformat()
    try:
        sb.table("conector_bots").update({
            "ultimo_ping": agora,
            "ultimo_equity": snap.equity,
            "ultimo_dd": snap.drawdown_atual,
            "ultima_direcao": snap.direcao_d1,
            "ultimo_padrao": snap.padrao_ativo,
            "posicoes_abertas": snap.posicoes_abertas,
        }).eq("id", bot["id"]).execute()
        sb.table("conector_snapshots").insert({
            "user_id": user_id, "bot_token": snap.bot_token,
            "conta_login": snap.conta_login, "corretora": snap.corretora,
            "simbolo": snap.simbolo, "magic_number": snap.magic_number,
            "equity": snap.equity, "balance": snap.balance,
            "margem_livre": snap.margem_livre,
            "posicoes_abertas": snap.posicoes_abertas,
            "lucro_flutuante": snap.lucro_flutuante,
            "drawdown_atual": snap.drawdown_atual,
            "direcao_d1": snap.direcao_d1, "padrao_ativo": snap.padrao_ativo,
            "detalhe_json": snap.detalhe or {},
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gravar snapshot: {e}")
    novas = _agente_bloco_f(sb, user_id, bot, snap)
    return {"ok": True, "sugestoes_novas": novas}


@app.post("/conector/evento")
def conector_evento(ev: ConectorEvento):
    """Evento do bot (trade aberto/fechado, reversão, pirâmide...)."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    bot = _bot_por_token(sb, ev.bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    try:
        sb.table("agente_eventos").insert({
            "user_id": bot.get("user_id"), "tipo": f"bot_{ev.tipo}",
            "regra": None, "detalhe_json": ev.detalhe or {},
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gravar evento: {e}")
    return {"ok": True}


@app.get("/conector/bots")
def conector_bots(user_id: str):
    """Painel: lista bots do usuário com status online/offline (3 min sem ping)."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    try:
        r = (sb.table("conector_bots").select("*")
             .eq("user_id", user_id).order("criado_em", desc=True).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar bots: {e}")
    agora = _dt.now(_tz.utc)
    bots = []
    for b in (r.data or []):
        online = False
        if b.get("ultimo_ping"):
            try:
                ping = _dt.fromisoformat(str(b["ultimo_ping"]).replace("Z", "+00:00"))
                online = (agora - ping).total_seconds() < OFFLINE_APOS_SEGUNDOS
            except Exception:
                pass
        b.pop("bot_token", None)  # token nunca volta pro front
        bots.append({**b, "online": online})
    return {"bots": bots}


@app.get("/agente/sugestoes")
def agente_sugestoes(user_id: str, apenas_nao_lidas: bool = False, limite: int = 30):
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    try:
        q = (sb.table("agente_sugestoes").select("*")
             .eq("user_id", user_id).order("criado_em", desc=True).limit(limite))
        if apenas_nao_lidas:
            q = q.eq("lida", False)
        r = q.execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar sugestões: {e}")
    nao_lidas = sum(1 for s in (r.data or []) if not s.get("lida"))
    return {"sugestoes": r.data or [], "nao_lidas": nao_lidas}


@app.post("/agente/sugestoes/lida")
def agente_sugestao_lida(req: SugestaoLida):
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    try:
        (sb.table("agente_sugestoes").update({"lida": True})
         .eq("id", req.sugestao_id).eq("user_id", req.user_id).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro: {e}")
    return {"ok": True}


# ╔════════════════════════════════════════════════════════════════════╗
# ║  BIBLIOTECA DE ESTUDO — PASSO 2 de 7                                ║
# ║  Popular a tabela estudo_biblioteca (motor invisível)              ║
# ║                                                                    ║
# ║  COMO INSTALAR:                                                     ║
# ║  1. Cole TODO este bloco no FINAL do seu api.py                    ║
# ║  2. Garanta a variável de ambiente BIBLIOTECA_ADMIN_TOKEN no       ║
# ║     Railway (uma senha secreta sua — ex: um texto aleatório longo) ║
# ║  3. Deploy. O cron semanal começa sozinho.                         ║
# ║                                                                    ║
# ║  Reusa: _matriz_calcular(), _sb_admin(), CATALOGO_ATIVOS           ║
# ║  (tudo que já existe no seu api.py — nada reescrito)               ║
# ╚════════════════════════════════════════════════════════════════════╝

import threading as _bib_threading
import time as _bib_time
from datetime import datetime as _bib_dt, timezone as _bib_tz

# ── Combinações VÁLIDAS (período × timeframe) — sem desperdício ──
# Respeita o que o yfinance realmente fornece. Timeframe curto = período curto.
_BIB_COMBOS = {
    "5m":  ["6 meses"],
    "15m": ["6 meses", "1 ano"],
    "30m": ["6 meses", "1 ano"],
    "1h":  ["1 ano", "2 anos"],
    "4h":  ["1 ano", "2 anos"],
    "1d":  ["2 anos", "3 anos", "5 anos"],
}

# Estado global do processamento (pra você acompanhar o progresso ao vivo)
_BIB_ESTADO = {
    "rodando": False,
    "inicio": None,
    "ativo_atual": None,
    "ativos_feitos": 0,
    "ativos_total": 0,
    "linhas_gravadas": 0,
    "erros": [],
    "ultima_conclusao": None,
}


def _bib_lista_todos_ativos():
    """Todos os 40 ativos do catálogo (nomes que o motor de backtest entende)."""
    nomes = []
    for _cat, itens in CATALOGO_ATIVOS.items():
        for a in itens:
            nomes.append(a["nome"])
    return nomes


def _bib_gravar_ativo(sb, ativo, periodo, resultado):
    """Converte o retorno de _matriz_calcular em linhas e faz upsert na tabela."""
    linhas = []
    medido = _bib_dt.now(_bib_tz.utc).isoformat()
    for linha in resultado.get("linhas", []):
        est_id = linha.get("id")
        est_nome = linha.get("nome")
        for tf, cel in (linha.get("cels") or {}).items():
            if not cel:
                continue
            linhas.append({
                "ativo": ativo,
                "periodo": periodo,
                "timeframe": tf,
                "estrategia_id": est_id,
                "estrategia_nome": est_nome,
                "retorno": cel.get("retorno"),
                "profit_factor": cel.get("pf"),
                "win_rate": cel.get("wr"),
                "sharpe": cel.get("sharpe"),
                "trades": cel.get("trades"),
                "forca": cel.get("forca"),
                "medido_em": medido,
            })
    if not linhas:
        return 0
    # upsert na constraint única (ativo,periodo,timeframe,estrategia_id)
    sb.table("estudo_biblioteca").upsert(
        linhas, on_conflict="ativo,periodo,timeframe,estrategia_id"
    ).execute()
    return len(linhas)


def _bib_ativos_pendentes(sb, dias_validade=7):
    """Retorna só os ativos que PRECISAM ser (re)processados:
    - faltando (nenhuma linha na biblioteca)
    - incompletos (não têm todos os períodos exigidos)
    - velhos (medido_em mais recente é mais antigo que dias_validade)
    Ativos completos e frescos são pulados. Ordena por prioridade:
    faltando/incompletos primeiro, velhos depois."""
    from datetime import timedelta as _td
    todos = _bib_lista_todos_ativos()
    periodos_necessarios = set(p for ps in _BIB_COMBOS.values() for p in ps)
    limite = _bib_dt.now(_bib_tz.utc) - _td(days=dias_validade)

    resp = (sb.table("estudo_biblioteca")
            .select("ativo,periodo,medido_em").execute())
    rows = resp.data or []
    estado = {}  # ativo -> {periodos:set, mais_novo:datetime|None}
    for r in rows:
        a = r["ativo"]
        st = estado.setdefault(a, {"periodos": set(), "mais_novo": None})
        st["periodos"].add(r["periodo"])
        m = r.get("medido_em")
        if m:
            try:
                dt = _bib_dt.fromisoformat(str(m).replace("Z", "+00:00"))
                if st["mais_novo"] is None or dt > st["mais_novo"]:
                    st["mais_novo"] = dt
            except Exception:
                pass

    urgentes, velhos = [], []
    for ativo in todos:
        st = estado.get(ativo)
        if st is None or not periodos_necessarios.issubset(st["periodos"]):
            urgentes.append(ativo)            # faltando ou incompleto
        elif st["mais_novo"] is None or st["mais_novo"] < limite:
            velhos.append(ativo)              # completo mas velho
    return urgentes + velhos


def _bib_processar_tudo(dias_validade=None, max_por_rodada=None):
    """Processa a biblioteca. Bloqueante — sempre chamada dentro de uma thread.
    - dias_validade=None: rodada COMPLETA (todos os 40, refaz tudo).
    - dias_validade=N: rodada INTELIGENTE — só ativos faltando/incompletos/velhos
      (mais de N dias). Pula o que está fresco. Usada pelo cron automático.
    - max_por_rodada=N: processa no máximo N ativos por chamada (lotes pequenos,
      pra nenhuma rodada ficar pesada o bastante pra cair no meio)."""
    import sys
    if _BIB_ESTADO["rodando"]:
        return
    sb = _sb_admin()
    if sb is None:
        print("BIBLIOTECA: Supabase indisponível", file=sys.stderr)
        return

    if dias_validade is None:
        ativos = _bib_lista_todos_ativos()
    else:
        ativos = _bib_ativos_pendentes(sb, dias_validade)
        if not ativos:
            print("BIBLIOTECA: nada pendente — tudo fresco e completo.", file=sys.stderr)
            return
    if max_por_rodada:
        ativos = ativos[:max_por_rodada]
    _BIB_ESTADO.update({
        "rodando": True, "inicio": _bib_time.time(), "ativo_atual": None,
        "ativos_feitos": 0, "ativos_total": len(ativos),
        "linhas_gravadas": 0, "erros": [],
    })
    print(f"BIBLIOTECA: iniciando — {len(ativos)} ativos", file=sys.stderr)

    # Quais períodos cada ativo precisa (união de todos os períodos dos combos)
    periodos_necessarios = sorted({p for ps in _BIB_COMBOS.values() for p in ps})

    for ativo in ativos:
        _BIB_ESTADO["ativo_atual"] = ativo
        t0 = _bib_time.time()
        linhas_ativo = 0
        try:
            # para cada período, calcula a matriz só com os TFs válidos daquele período
            for periodo in periodos_necessarios:
                tfs_do_periodo = [tf for tf, ps in _BIB_COMBOS.items() if periodo in ps]
                if not tfs_do_periodo:
                    continue
                try:
                    res = _matriz_calcular(ativo, tfs_do_periodo, periodo, "pt")
                    linhas_ativo += _bib_gravar_ativo(sb, ativo, periodo, res)
                except Exception as e:
                    _BIB_ESTADO["erros"].append(f"{ativo}/{periodo}: {e}")
                    print(f"BIBLIOTECA erro {ativo}/{periodo}: {e}", file=sys.stderr)
                _bib_time.sleep(1.0)  # respiro entre períodos (rate-limit yfinance)
        except Exception as e:
            _BIB_ESTADO["erros"].append(f"{ativo}: {e}")

        _BIB_ESTADO["ativos_feitos"] += 1
        _BIB_ESTADO["linhas_gravadas"] += linhas_ativo
        dur = round(_bib_time.time() - t0)
        print(f"BIBLIOTECA: {ativo} ✓ ({linhas_ativo} linhas, {dur}s) "
              f"[{_BIB_ESTADO['ativos_feitos']}/{len(ativos)}]", file=sys.stderr)
        _bib_time.sleep(2.0)  # respiro entre ativos (alivia o servidor)

    _BIB_ESTADO["rodando"] = False
    _BIB_ESTADO["ultima_conclusao"] = _bib_dt.now(_bib_tz.utc).isoformat()
    total_dur = round(_bib_time.time() - _BIB_ESTADO["inicio"])
    print(f"BIBLIOTECA: CONCLUÍDO — {_BIB_ESTADO['linhas_gravadas']} linhas, "
          f"{len(_BIB_ESTADO['erros'])} erros, {total_dur}s", file=sys.stderr)


def _bib_disparar(dias_validade=None, max_por_rodada=None):
    """Dispara o processamento numa thread (não trava a API).
    Sem argumentos = rodada completa (todos os 40)."""
    if _BIB_ESTADO["rodando"]:
        return False
    th = _bib_threading.Thread(
        target=_bib_processar_tudo,
        kwargs={"dias_validade": dias_validade, "max_por_rodada": max_por_rodada},
        daemon=True)
    th.start()
    return True


# ── ENDPOINT ADMIN: disparar manualmente + ver progresso ──
class BibDispararReq(BaseModel):
    token: str
    # opcional: se informado, roda SÓ o que está pendente (faltando/incompleto/
    # mais velho que N dias) em vez de refazer os 40. Ex: dias_validade=7.
    dias_validade: Optional[int] = None
    max_por_rodada: Optional[int] = None

@app.post("/admin/biblioteca/rodar")
def admin_biblioteca_rodar(req: BibDispararReq):
    """Dispara uma rodada. Sem dias_validade = completa (40 ativos).
    Com dias_validade=N = só pendentes (faltando/incompletos/velhos).
    Protegido por token secreto."""
    token_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not token_certo or req.token != token_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    if _BIB_ESTADO["rodando"]:
        return {"ok": False, "msg": "Já está rodando", "estado": _bib_estado_publico()}
    _bib_disparar(dias_validade=req.dias_validade, max_por_rodada=req.max_por_rodada)
    modo = "só pendentes" if req.dias_validade is not None else "completa (40)"
    return {"ok": True, "msg": f"Rodada iniciada em background ({modo})",
            "estado": _bib_estado_publico()}


@app.get("/admin/biblioteca/status")
def admin_biblioteca_status(token: str = ""):
    """Ver progresso ao vivo. Protegido por token."""
    token_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not token_certo or token != token_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    return _bib_estado_publico()


def _bib_estado_publico():
    e = dict(_BIB_ESTADO)
    if e.get("inicio") and e.get("rodando"):
        e["decorrido_s"] = round(_bib_time.time() - e["inicio"])
    e["erros"] = e.get("erros", [])[:20]  # limita o tamanho da resposta
    return e


# ── ENDPOINT DE TESTE: roda só 1 ativo (validação rápida antes da rodada completa) ──
class BibTesteReq(BaseModel):
    token: str
    ativo: str = "S&P500"   # padrão: S&P500 (rápido e confiável)

@app.post("/admin/biblioteca/testar")
def admin_biblioteca_testar(req: BibTesteReq):
    """TESTE: processa UM único ativo, de forma síncrona (espera terminar),
    e retorna quantas linhas gravou. Use isto ANTES da rodada completa.
    Protegido por token secreto."""
    import sys
    token_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not token_certo or req.token != token_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    if _BIB_ESTADO["rodando"]:
        return {"ok": False, "msg": "Uma rodada completa está em andamento — aguarde."}

    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")

    # valida que o ativo existe no catálogo
    todos = _bib_lista_todos_ativos()
    if req.ativo not in todos:
        return {"ok": False, "msg": f"Ativo '{req.ativo}' não está no catálogo.",
                "ativos_validos": todos}

    t0 = _bib_time.time()
    periodos_necessarios = sorted({p for ps in _BIB_COMBOS.values() for p in ps})
    total_linhas = 0
    detalhes = []
    erros = []
    for periodo in periodos_necessarios:
        tfs_do_periodo = [tf for tf, ps in _BIB_COMBOS.items() if periodo in ps]
        try:
            res = _matriz_calcular(req.ativo, tfs_do_periodo, periodo, "pt")
            n = _bib_gravar_ativo(sb, req.ativo, periodo, res)
            total_linhas += n
            detalhes.append({"periodo": periodo, "tfs": tfs_do_periodo, "linhas": n})
        except Exception as e:
            erros.append(f"{periodo}: {e}")
            print(f"BIBLIOTECA teste erro {req.ativo}/{periodo}: {e}", file=sys.stderr)
        _bib_time.sleep(1.0)

    dur = round(_bib_time.time() - t0)
    return {
        "ok": True,
        "ativo": req.ativo,
        "linhas_gravadas": total_linhas,
        "duracao_s": dur,
        "detalhes": detalhes,
        "erros": erros,
        "msg": f"{req.ativo}: {total_linhas} linhas gravadas em {dur}s. "
               f"Confira na tabela estudo_biblioteca.",
    }


# ── CRON AUTOMÁTICO: mantém a biblioteca fresca sozinho, sem rodada pesada ──
def _bib_cron_loop():
    """Thread que mantém a biblioteca fresca de forma resiliente.
    Em vez de uma rodada pesada semanal (que pode cair no meio), ele:
      - acorda a cada 24h
      - processa SÓ o que está pendente (faltando, incompleto ou >7 dias)
      - no máximo 8 ativos por vez (lote leve, nunca cai por peso)
    Se cair no meio, o que ficou pendente é retomado na próxima checagem —
    a biblioteca se auto-cura sem intervenção."""
    import sys
    _bib_time.sleep(600)  # 10 min após boot (deixa a API estabilizar)
    UM_DIA = 24 * 60 * 60
    DIAS_VALIDADE = 7        # ativo é "fresco" se medido nos últimos 7 dias
    MAX_POR_RODADA = 8       # processa no máximo 8 pendentes por checagem
    while True:
        try:
            if not _BIB_ESTADO["rodando"]:
                print("BIBLIOTECA: checagem automática (mantém fresco)", file=sys.stderr)
                _bib_processar_tudo(dias_validade=DIAS_VALIDADE,
                                    max_por_rodada=MAX_POR_RODADA)
        except Exception as e:
            print(f"BIBLIOTECA cron erro: {e}", file=sys.stderr)
        _bib_time.sleep(UM_DIA)


def _bib_iniciar_cron():
    th = _bib_threading.Thread(target=_bib_cron_loop, daemon=True)
    th.start()

# inicia o cron quando a API sobe
_bib_iniciar_cron()


# ╔════════════════════════════════════════════════════════════════════╗
# ║  BIBLIOTECA DE ESTUDO — PASSO 3a (backend do painel admin)         ║
# ║  Endpoint que LÊ da biblioteca e devolve no formato que o          ║
# ║  renderEstudo() do frontend já entende.                            ║
# ║                                                                    ║
# ║  COLE este bloco no FINAL do api.py (depois do bloco do Passo 2).  ║
# ╚════════════════════════════════════════════════════════════════════╝

# user_id do dono (admin). Só este usuário acessa o painel.
_BIB_ADMIN_USER_ID = "cd99b5b0-d97e-484a-900e-30a267a01f12"

# Ordem fixa dos timeframes para montar as colunas da matriz
_BIB_TF_ORDEM = ["5m", "15m", "30m", "1h", "4h", "1d"]


class BibLerReq(BaseModel):
    user_id: str
    ativo: str
    periodo: str = "2 anos"


@app.post("/admin/biblioteca/ler")
def admin_biblioteca_ler(req: BibLerReq):
    """Lê da biblioteca (instantâneo) e monta a matriz no formato do renderEstudo.
    Só responde para o user_id admin. Senão, 403."""
    if req.user_id != _BIB_ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="Acesso restrito")

    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")

    # busca todas as linhas desse ativo+período
    resp = (sb.table("estudo_biblioteca")
            .select("*")
            .eq("ativo", req.ativo)
            .eq("periodo", req.periodo)
            .execute())
    rows = resp.data or []

    if not rows:
        return {"ativo": req.ativo, "periodo": req.periodo, "tfs": [],
                "linhas": [], "tops": [], "duracao_s": 0, "vazio": True}

    # quais timeframes existem para esse ativo+período (na ordem fixa)
    tfs_presentes = [tf for tf in _BIB_TF_ORDEM
                     if any(r["timeframe"] == tf for r in rows)]

    # indexa: estrategia_id -> { tf -> celula }
    por_est = {}
    medido_em = None
    for r in rows:
        eid = r["estrategia_id"]
        if eid not in por_est:
            por_est[eid] = {"id": eid, "nome": r["estrategia_nome"], "cels": {}}
        por_est[eid]["cels"][r["timeframe"]] = {
            "retorno": r.get("retorno") or 0.0,
            "pf": r.get("profit_factor") or 0.0,
            "wr": r.get("win_rate") or 0.0,
            "sharpe": r.get("sharpe") or 0.0,
            "trades": r.get("trades") or 0,
            "forca": r.get("forca") or "fraca",
        }
        if not medido_em:
            medido_em = r.get("medido_em")

    # mantém a ordem das estratégias igual à do app (ESTRATEGIAS_PRONTAS)
    ordem_ids = [e["id"] for e in ESTRATEGIAS_PRONTAS]
    linhas = []
    for eid in ordem_ids:
        if eid in por_est:
            e = por_est[eid]
            # acha emoji/casa na lista original
            orig = next((x for x in ESTRATEGIAS_PRONTAS if x["id"] == eid), {})
            linhas.append({
                "id": eid, "nome": e["nome"],
                "emoji": orig.get("emoji", ""),
                "casa": bool(orig.get("casa")),
                "cels": e["cels"],
            })

    # ranking (tops por sharpe, mínimo 20 trades e PF > 1)
    ranking = []
    for l in linhas:
        orig = next((x for x in ESTRATEGIAS_PRONTAS if x["id"] == l["id"]), {})
        for tf, c in l["cels"].items():
            if c["trades"] >= 20 and c["pf"] > 1:
                ranking.append({"estrategia": l["nome"], "id": l["id"],
                                "emoji": orig.get("emoji", ""), "tf": tf, **c})
    ranking.sort(key=lambda x: x["sharpe"], reverse=True)

    return {
        "ativo": req.ativo,
        "periodo": req.periodo,
        "tfs": tfs_presentes,
        "linhas": linhas,
        "tops": ranking[:10],
        "duracao_s": 0,
        "medido_em": medido_em,
        "vazio": False,
    }


@app.get("/admin/biblioteca/ativos")
def admin_biblioteca_ativos(user_id: str = ""):
    """Lista os ativos+períodos disponíveis na biblioteca (pra montar os seletores
    do painel admin). Só responde para o admin."""
    if user_id != _BIB_ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="Acesso restrito")
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    resp = (sb.table("estudo_biblioteca")
            .select("ativo,periodo,medido_em").execute())
    rows = resp.data or []
    ativos = {}
    for r in rows:
        a = r["ativo"]
        if a not in ativos:
            ativos[a] = {"periodos": set(), "medido_em": r.get("medido_em")}
        ativos[a]["periodos"].add(r["periodo"])
    # serializa
    out = []
    for a, info in sorted(ativos.items()):
        out.append({"ativo": a, "periodos": sorted(info["periodos"]),
                    "medido_em": info["medido_em"]})
    return {"ativos": out, "total": len(out)}
