# ============================================================
#  BotTested API — v3.5 (Radar IA + cache)
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

app = FastAPI(title="BotTested API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ARQUIVOS ESTÁTICOS (imagens dos robôs da vitrine, etc.) ──
# Coloque os PNGs em /assets no repositório. Ficam acessíveis em /assets/<arquivo>.
try:
    from fastapi.staticfiles import StaticFiles
    os.makedirs("assets", exist_ok=True)
    # Serve o robô da vitrine mesmo que o PNG esteja na RAIZ do repo (não só em /assets).
    # Registrado ANTES do mount para ter prioridade nesse caminho específico.
    @app.get("/assets/robo_default.png", include_in_schema=False)
    def _serve_robo_default():
        for _p in ("assets/robo_default.png", "robo_default.png"):
            if os.path.exists(_p):
                return FileResponse(_p, media_type="image/png")
        raise HTTPException(404, "robo_default.png nao encontrado")
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")
except Exception as _e:
    print(f"[assets] não foi possível montar /assets: {_e}")

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
    estrategia_id: Optional[str] = None      # id da estratégia ativa (p/ conversor testado)
    estrategia_nome: Optional[str] = None    # nome amigável (p/ cabeçalho do código exportado)

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
# Prefixos de rotas de API que SEMPRE devolvem JSON, mesmo abertas no navegador
# (não redireciona pro app-lock). Inclui a análise top-down e a tubulação do bot.
_PREFIXOS_API = ("/analise/", "/bot/", "/exportar/", "/babymachine/", "/offmind/", "/radar/")

@app.middleware("http")
async def _redirecionar_navegador(request: Request, call_next):
    try:
        path = request.url.path
        if request.method == "GET" and path not in _ROTAS_HTML:
            # rotas de API nunca redirecionam — sempre JSON
            if not any(path.startswith(p) for p in _PREFIXOS_API):
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    return RedirectResponse(url="/app")
    except Exception:
        pass
    return await call_next(request)


API_VERSAO = "4.0 — Radar IA multilíngue (PT/EN/ES) + Estudo como fonte"
# Marcador de build: muda a cada deploy para confirmarmos no /versao o que está live.
BUILD_TAG = "2026-06-25e-radar-stoptake-verificado"

@app.get("/versao")
def versao():
    tem_chave = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    diag = {"api": API_VERSAO,
            "build": BUILD_TAG,
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
        "name": "BotTested API",
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
            "Você é o Radar, copiloto de validação do BotTested (backtesting de estratégias de trading). "
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
        opcoes_testar = []
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
                            # lista de estratégias testáveis (distintas, mesmo TF, mais fortes) — o usuário escolhe qual testar
                            _vistos = set()
                            for _t in _mesmo:
                                _tid = str(_t.get("id") or "").strip()
                                if not _tid or _tid in _vistos:
                                    continue
                                if _rodando_id and _tid == _rodando_id:
                                    continue
                                if not (_t.get("pf") and _t.get("trades") and _t["trades"] >= 20 and float(_t["pf"]) > 1.0):
                                    continue
                                _vistos.add(_tid)
                                opcoes_testar.append({"id": _tid, "nome": _t.get("estrategia"), "tf": _t.get("tf"),
                                                      "sharpe": _t.get("sharpe"), "pf": _t.get("pf"),
                                                      "retorno": _t.get("retorno"), "trades": _t.get("trades")})
                                if len(opcoes_testar) >= 3:
                                    break
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
                                      "testar_opcoes": opcoes_testar,
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
            # SEGURANÇA: rejeita código inseguro com erro claro (400) em vez de
            # silenciosamente cair na estratégia padrão.
            ok, motivo = verificar_codigo_seguro(params.codigo)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Código bloqueado: {motivo}")
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

# ════════════════════════════════════════════════════════════
# SEGURANÇA: sandbox do código custom do utilizador
# O editor de código e a geração por IA executam Python do cliente.
# Sem estas duas camadas, exec() = execução remota arbitrária no servidor
# (leitura de SUPABASE_SERVICE_KEY, STRIPE_SECRET_KEY, sockets, etc.).
#   Camada 1: verificar_codigo_seguro() — validação AST (denylist).
#   Camada 2: SAFE_BUILTINS — conjunto mínimo de builtins no exec.
# ════════════════════════════════════════════════════════════
import builtins as _builtins

# Builtins permitidos dentro do código do utilizador. Inclui __build_class__
# (necessário para a instrução `class`) mas NÃO open/eval/exec/compile/
# __import__/input/globals/locals/vars/getattr/setattr/delattr/exit.
_NOMES_BUILTINS_SEGUROS = [
    "abs", "all", "any", "bool", "bytes", "dict", "divmod", "enumerate",
    "filter", "float", "format", "frozenset", "hasattr", "hash", "int",
    "isinstance", "issubclass", "len", "list", "map", "max", "min", "next",
    "object", "pow", "print", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "zip",
    "True", "False", "None",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "ZeroDivisionError", "ArithmeticError", "RuntimeError",
    "StopIteration", "NotImplementedError",
    "super", "property", "staticmethod", "classmethod",
    "__build_class__",
]
SAFE_BUILTINS = {
    n: getattr(_builtins, n)
    for n in _NOMES_BUILTINS_SEGUROS
    if hasattr(_builtins, n)
}
SAFE_BUILTINS["__name__"] = "strategy_sandbox"

# Módulos cujo import é proibido no código do utilizador.
_IMPORTS_BLOQUEADOS = {
    "os", "sys", "subprocess", "shutil", "pathlib", "socket", "http",
    "urllib", "requests", "httpx", "importlib", "ctypes", "multiprocessing",
    "threading", "asyncio", "pickle", "marshal", "builtins", "code", "pty",
    "signal", "resource", "gc", "inspect", "platform", "tempfile", "glob",
    "fileinput", "webbrowser", "smtplib", "ftplib", "telnetlib", "io",
}

# Funções cuja chamada é proibida (fuga de sandbox ou I/O).
_CHAMADAS_BLOQUEADAS = {
    "eval", "exec", "compile", "__import__", "open", "input", "globals",
    "locals", "vars", "getattr", "setattr", "delattr", "exit", "quit",
    "memoryview", "breakpoint", "help",
}


# O código do utilizador quase sempre tem `import pandas as pd` /
# `from backtesting import Strategy`. Sem __import__, o exec falha com
# "ImportError: __import__ not found". Em vez de devolver o __import__ real
# (que reabriria QUALQUER módulo), injetamos um __import__ SEGURO que respeita
# a mesma denylist do validador AST — restaura imports legítimos e mantém os
# perigosos bloqueados (defesa em profundidade: runtime + AST).
def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    base = (name or "").split(".")[0]
    if base in _IMPORTS_BLOQUEADOS:
        raise ImportError(f"Import bloqueado: '{name}'")
    return _builtins.__import__(name, globals, locals, fromlist, level)

SAFE_BUILTINS["__import__"] = _safe_import


def verificar_codigo_seguro(codigo: str):
    """Valida (AST) o código custom ANTES do exec. Defesa em profundidade
    junto com SAFE_BUILTINS. Retorna (True, 'ok') ou (False, motivo).
    Bloqueia: imports perigosos, chamadas perigosas, acesso a atributos/nomes
    dunder (ex: __globals__, __subclasses__, __builtins__) e código que não
    defina uma classe herdando de Strategy."""
    import ast
    if not codigo or not codigo.strip():
        return False, "Código vazio"
    try:
        tree = ast.parse(codigo)
    except SyntaxError as e:
        return False, f"Erro de sintaxe: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in _IMPORTS_BLOQUEADOS:
                    return False, f"Import bloqueado: '{a.name}'"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _IMPORTS_BLOQUEADOS:
                return False, f"Import bloqueado: '{node.module}'"
        elif isinstance(node, ast.Attribute):
            # ().__class__.__subclasses__() e afins
            if node.attr.startswith("__") and node.attr.endswith("__"):
                return False, f"Acesso a atributo interno bloqueado: '{node.attr}'"
        elif isinstance(node, ast.Name):
            if (node.id.startswith("__") and node.id.endswith("__")
                    and node.id != "__name__"):
                return False, f"Nome interno bloqueado: '{node.id}'"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _CHAMADAS_BLOQUEADAS:
                return False, f"Função bloqueada: '{node.func.id}'"

    tem_strategy = any(
        isinstance(n, ast.ClassDef) and any(
            (isinstance(b, ast.Name) and b.id == "Strategy")
            or (isinstance(b, ast.Attribute) and b.attr == "Strategy")
            for b in n.bases
        )
        for n in ast.walk(tree)
    )
    if not tem_strategy:
        return False, "O código deve definir uma classe que herda de Strategy"
    return True, "ok"


def rodar_codigo_custom(df: pd.DataFrame, params: BacktestCustom) -> dict:
    """
    v3.1 - Executa de VERDADE a estrategia Python do usuario com o motor
    backtesting.py. Aceita classes Strategy (com ou sem imports no codigo).
    Se falhar, levanta excecao - o chamador cai no motor padrao.
    v3.6 - Sandbox: valida o codigo (AST) e restringe builtins antes do exec.
    """
    from backtesting import Backtest, Strategy as _Strategy
    from backtesting.lib import crossover as _crossover

    # SEGURANÇA (camada 1): valida o código antes de executar qualquer coisa.
    ok, motivo = verificar_codigo_seguro(params.codigo)
    if not ok:
        raise ValueError(f"Código bloqueado: {motivo}")

    # Namespace com tudo que os codigos gerados/colados costumam usar.
    # SEGURANÇA (camada 2): __builtins__ restrito a SAFE_BUILTINS (sem open/
    # eval/exec/__import__/getattr/etc.).
    ns = {
        "pd": pd, "np": np,
        "Strategy": _Strategy, "crossover": _crossover,
        # Valores da barra lateral disponíveis pro código colado (em pontos/USD)
        "SL_PTS": float(params.stop_loss), "TP_PTS": float(params.take_profit),
        "MAX_OPS": int(params.max_ops), "CAPITAL": float(params.capital),
        "__builtins__": SAFE_BUILTINS,
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

# ════════════════════════════════════════════════════════════════════
# CONVERSOR PINE SCRIPT (TradingView) — BotTested
# Caminho A: conversores testados por estratégia conhecida (id da vitrine)
# Caminho B: fallback IA p/ código customizado (feito no endpoint)
# Os conversores recebem os PARÂMETROS REAIS do usuário (ema_period, stop,
# take, etc.) e geram Pine v5 pronto pra colar no TradingView.
# ════════════════════════════════════════════════════════════════════

def _pine_header(nome: str, ativo: str = "") -> str:
    """Cabeçalho comum do Pine: versão, strategy(), comentário de origem."""
    alvo = f" · {ativo}" if ativo else ""
    return (
        "//@version=5\n"
        f'// ── {nome}{alvo} ──\n'
        "// Gerado pelo BotTested (bottested.com) — histórico medido, não promessa.\n"
        "// Revise os parâmetros antes de usar em conta real.\n"
        f'strategy("{nome}", overlay=true, '
        "default_qty_type=strategy.percent_of_equity, default_qty_value=100, "
        "commission_type=strategy.commission.percent, commission_value=0.02)\n\n"
    )


def _pine_stop_take(stop_pts: float, take_pts: float) -> str:
    """Bloco de stop/take em pontos (pontos do ativo, igual ao backtest)."""
    return (
        f"// Gestão de risco (em pontos do ativo)\n"
        f"stopPts  = input.float({stop_pts}, 'Stop Loss (pts)')\n"
        f"takePts  = input.float({take_pts}, 'Take Profit (pts)')\n"
    )


# ── Canal EMA 20 High/Low ──────────────────────────────────────────
def _pine_canal_ema20_hl(p) -> str:
    n = int(getattr(p, "ema_period", 20) or 20)
    s = _pine_header("Canal EMA 20 High/Low", getattr(p, "ativo", ""))
    s += _pine_stop_take(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += f"""
len = input.int({n}, 'Período EMA')
emaHigh = ta.ema(high, len)
emaLow  = ta.ema(low,  len)

plot(emaHigh, 'EMA High', color=color.new(color.orange, 0))
plot(emaLow,  'EMA Low',  color=color.new(color.orange, 40))

// Rompe pra cima do canal = compra; pra baixo = venda; dentro = lateral (não opera)
longCond  = close > emaHigh
shortCond = close < emaLow

if longCond and strategy.position_size <= 0
    strategy.entry('Long', strategy.long)
if shortCond and strategy.position_size >= 0
    strategy.entry('Short', strategy.short)

// Stop/Take em pontos
strategy.exit('xL', 'Long',  loss=stopPts, profit=takePts)
strategy.exit('xS', 'Short', loss=stopPts, profit=takePts)
"""
    return s


# ── Cruzamento EMA 9/21 ────────────────────────────────────────────
def _pine_cruzamento_ema_9_21(p) -> str:
    s = _pine_header("Cruzamento EMA 9/21", getattr(p, "ativo", ""))
    s += _pine_stop_take(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """
fast = input.int(9,  'EMA Rápida')
slow = input.int(21, 'EMA Lenta')
emaFast = ta.ema(close, fast)
emaSlow = ta.ema(close, slow)

plot(emaFast, 'EMA 9',  color=color.new(color.aqua, 0))
plot(emaSlow, 'EMA 21', color=color.new(color.purple, 0))

longCond  = ta.crossover(emaFast, emaSlow)
shortCond = ta.crossunder(emaFast, emaSlow)

if longCond
    strategy.entry('Long', strategy.long)
if shortCond
    strategy.entry('Short', strategy.short)

strategy.exit('xL', 'Long',  loss=stopPts, profit=takePts)
strategy.exit('xS', 'Short', loss=stopPts, profit=takePts)
"""
    return s


# Mapa id da estratégia → função conversora (Caminho A: testado)
_CONVERSORES_PINE = {
    "canal_ema20_hl": _pine_canal_ema20_hl,
    "cruzamento_ema_9_21": _pine_cruzamento_ema_9_21,
    # demais estratégias adicionadas após validar estas duas
}


def _pine_via_ia(codigo_py: str, nome: str, p) -> Optional[str]:
    """Caminho B: código customizado → IA converte p/ Pine v5. Sempre com aviso.
    Falha → None (caller mostra mensagem de indisponível)."""
    import sys
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave or not codigo_py.strip():
        return None
    try:
        import httpx
        sistema = (
            "Você converte estratégias de trading de Python (biblioteca backtesting.py) "
            "para Pine Script v5 do TradingView. REGRAS: (1) gere SOMENTE código Pine v5 válido, "
            "começando com //@version=5 e strategy(...); (2) use overlay=true; (3) traduza a lógica "
            "de entrada/saída fielmente — não invente regras que não existem no Python; (4) inclua "
            "stop/take se houver; (5) se algo do Python não tiver equivalente direto em Pine, "
            "deixe um comentário // TODO explicando, em vez de inventar; (6) NÃO escreva nenhuma "
            "explicação fora do código — apenas o Pine. O usuário foi avisado de que deve revisar."
        )
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
                "max_tokens": 1500, "temperature": 0.2, "system": sistema,
                "messages": [{"role": "user", "content":
                    f"Converta esta estratégia '{nome}' para Pine Script v5:\n\n{codigo_py}"}],
            },
            timeout=20.0,
        )
        if r.status_code != 200:
            print(f"PINE IA status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        if texto.startswith("```"):
            texto = texto.strip("`")
            if texto.lower().startswith("pine"):
                texto = texto[4:]
        return texto.strip() or None
    except Exception as e:
        print(f"PINE IA erro: {e}", file=sys.stderr)
        return None


def gerar_pine(estrategia_id: str, codigo_py: str, nome: str, p) -> dict:
    """Decide o caminho: estratégia conhecida → conversor testado (A);
    senão → IA (B) com aviso. Retorna {codigo, fonte, aviso}."""
    conv = _CONVERSORES_PINE.get((estrategia_id or "").strip())
    if conv:
        return {"codigo": conv(p), "fonte": "testado", "aviso": ""}
    # código customizado / estratégia ainda sem conversor testado
    pine = _pine_via_ia(codigo_py, nome or "Estratégia", p)
    if pine:
        aviso = ("Conversão automática por IA — revise o código com atenção antes de usar "
                 "em conta real. Confira regras de entrada/saída, stop e take.")
        return {"codigo": pine, "fonte": "ia", "aviso": aviso}
    return {"codigo": "", "fonte": "indisponivel",
            "aviso": "Conversão automática indisponível para este código no momento."}

# ── Endpoint: exportar estratégia para Pine Script (TradingView) ──
@app.post("/exportar/pine")
def exportar_pine(req: BacktestCustom):
    """Gera Pine Script v5 da estratégia ativa. Estratégia conhecida usa conversor
    testado; código customizado cai na IA (com aviso). Usa os parâmetros reais."""
    est_id = (getattr(req, "estrategia_id", "") or "").strip()
    nome = getattr(req, "estrategia_nome", "") or "Estratégia"
    res = gerar_pine(est_id, getattr(req, "codigo", "") or "", nome, req)
    res["formato"] = "Pine Script v5"
    res["plataforma"] = "TradingView"
    return res


# ════════════════════════════════════════════════════════════════════
# CONVERSOR MQL5 (MetaTrader 5) — BotTested
# Gera Expert Advisor (.mq5) da estratégia validada. Mesma lógica A+B do Pine.
# ATENÇÃO: código de EXECUÇÃO REAL — avisos de risco no cabeçalho + base funcional.
# Usa a API moderna do MT5 (CTrade), stop/take em pontos, MagicNumber por EA.
# ════════════════════════════════════════════════════════════════════

# Avisos de risco (cabeçalho de TODO .mq5 gerado)
_MQL5_AVISO_HEADER = """//+------------------------------------------------------------------+
//|  BotTested — Expert Advisor gerado (bottested.com)               |
//|  ATENCAO: opera com dinheiro REAL. Teste em conta DEMO primeiro. |
//|  Historico medido, nao promessa de retorno. Use por sua conta    |
//|  e risco. Esta e uma BASE FUNCIONAL — revise antes de operar.    |
//+------------------------------------------------------------------+"""


def _mql5_preamble(nome: str, ativo: str, magic: int = 20250) -> str:
    """Cabeçalho + includes + inputs comuns + handle de trade."""
    alvo = f"  // testado em: {ativo}" if ativo else ""
    return f"""{_MQL5_AVISO_HEADER}
#property copyright "BotTested"
#property link      "https://bottested.com"
#property version   "1.00"
#property description "{nome} — gerado pelo BotTested. BASE FUNCIONAL: teste em conta demo."

#include <Trade/Trade.mqh>
CTrade trade;
{alvo}
"""


def _mql5_risk_inputs(stop_pts: float, take_pts: float) -> str:
    return f"""
//--- Parametros de risco (revise antes de usar)
input double  InpLote       = 0.10;        // Lote (volume por ordem)
input double  InpStopLoss   = {stop_pts};      // Stop Loss (pontos)
input double  InpTakeProfit = {take_pts};      // Take Profit (pontos)
input ulong   InpMagic      = 20250;       // Numero magico (identifica este EA)
input ulong   InpSlippage   = 30;          // Desvio maximo (pontos)
"""


# ── Canal EMA 20 High/Low ──────────────────────────────────────────
def _mql5_canal_ema20_hl(p) -> str:
    n = int(getattr(p, "ema_period", 20) or 20)
    ativo = getattr(p, "ativo", "")
    s = _mql5_preamble("Canal EMA 20 High/Low", ativo)
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += f"""input int     InpEMAPeriod  = {n};          // Periodo da EMA (canal)

//--- Handles dos indicadores
int hEmaHigh, hEmaLow;

int OnInit()
{{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   // EMA das maximas e EMA das minimas formam o canal
   hEmaHigh = iMA(_Symbol, _Period, InpEMAPeriod, 0, MODE_EMA, PRICE_HIGH);
   hEmaLow  = iMA(_Symbol, _Period, InpEMAPeriod, 0, MODE_EMA, PRICE_LOW);
   if(hEmaHigh == INVALID_HANDLE || hEmaLow == INVALID_HANDLE)
      return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}}

void OnDeinit(const int reason)
{{
   IndicatorRelease(hEmaHigh);
   IndicatorRelease(hEmaLow);
}}

//--- so processa uma vez por barra nova
datetime g_lastBar = 0;
bool NovaBarra()
{{
   datetime t = iTime(_Symbol, _Period, 0);
   if(t != g_lastBar) {{ g_lastBar = t; return(true); }}
   return(false);
}}

void OnTick()
{{
   if(!NovaBarra()) return;

   double emaH[], emaL[];
   if(CopyBuffer(hEmaHigh, 0, 1, 1, emaH) < 1) return;
   if(CopyBuffer(hEmaLow,  0, 1, 1, emaL) < 1) return;

   double preco = iClose(_Symbol, _Period, 1);
   double ponto = _Point;
   bool temPos = PositionSelect(_Symbol);
   long tipoPos = temPos ? PositionGetInteger(POSITION_TYPE) : -1;

   double sl, tp, ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   // Rompe pra cima do canal = compra
   if(preco > emaH[0] && tipoPos != POSITION_TYPE_BUY)
   {{
      if(temPos) trade.PositionClose(_Symbol);
      sl = ask - InpStopLoss   * ponto;
      tp = ask + InpTakeProfit * ponto;
      trade.Buy(InpLote, _Symbol, ask, sl, tp, "BotTested Canal EMA");
   }}
   // Rompe pra baixo do canal = venda
   else if(preco < emaL[0] && tipoPos != POSITION_TYPE_SELL)
   {{
      if(temPos) trade.PositionClose(_Symbol);
      sl = bid + InpStopLoss   * ponto;
      tp = bid - InpTakeProfit * ponto;
      trade.Sell(InpLote, _Symbol, bid, sl, tp, "BotTested Canal EMA");
   }}
   // dentro do canal = lateralizacao, nao abre nada
}}
"""
    return s


# ── Cruzamento EMA 9/21 ────────────────────────────────────────────
def _mql5_cruzamento_ema_9_21(p) -> str:
    ativo = getattr(p, "ativo", "")
    s = _mql5_preamble("Cruzamento EMA 9/21", ativo)
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpFast       = 9;           // EMA rapida
input int     InpSlow       = 21;          // EMA lenta

int hFast, hSlow;

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   hFast = iMA(_Symbol, _Period, InpFast, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, _Period, InpSlow, 0, MODE_EMA, PRICE_CLOSE);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE)
      return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hFast);
   IndicatorRelease(hSlow);
}

datetime g_lastBar = 0;
bool NovaBarra()
{
   datetime t = iTime(_Symbol, _Period, 0);
   if(t != g_lastBar) { g_lastBar = t; return(true); }
   return(false);
}

void OnTick()
{
   if(!NovaBarra()) return;

   double f[], s[];
   // pega 2 valores (barra 1 e 2) p/ detectar cruzamento
   if(CopyBuffer(hFast, 0, 1, 2, f) < 2) return;
   if(CopyBuffer(hSlow, 0, 1, 2, s) < 2) return;

   // f[1]=mais recente (barra 1), f[0]=anterior (barra 2)
   bool cruzaCima  = (f[0] <= s[0]) && (f[1] > s[1]);
   bool cruzaBaixo = (f[0] >= s[0]) && (f[1] < s[1]);

   double ponto = _Point;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl, tp;

   if(cruzaCima)
   {
      if(PositionSelect(_Symbol)) trade.PositionClose(_Symbol);
      sl = ask - InpStopLoss   * ponto;
      tp = ask + InpTakeProfit * ponto;
      trade.Buy(InpLote, _Symbol, ask, sl, tp, "BotTested Cruz 9/21");
   }
   else if(cruzaBaixo)
   {
      if(PositionSelect(_Symbol)) trade.PositionClose(_Symbol);
      sl = bid + InpStopLoss   * ponto;
      tp = bid - InpTakeProfit * ponto;
      trade.Sell(InpLote, _Symbol, bid, sl, tp, "BotTested Cruz 9/21");
   }
}
"""
    return s


# ════════════════════════════════════════════════════════════════════
# CONVERSORES MQL5 — 12 estratégias restantes
# Tradução fiel da lógica Python (backtesting.py) para Expert Advisor MQL5.
# Cada uma usa _mql5_preamble + _mql5_risk_inputs (já definidos no módulo base).
# ════════════════════════════════════════════════════════════════════

# ── Tendência Diária Escalonada (pirâmide a favor da tendência) ─────
def _mql5_tendencia_diaria_piramide(p) -> str:
    n = int(getattr(p, "ema_period", 20) or 20)
    s = _mql5_preamble("Tendencia Diaria Escalonada", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += f"""input int     InpEMAPeriod  = {n};          // Periodo EMA (canal)
input int     InpMaxPiramide= 3;           // Maximo de entradas empilhadas
input double  InpTrailPct   = 1.5;         // Trailing stop (%)

int hEmaHigh, hEmaLow;
double g_topo = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   hEmaHigh = iMA(_Symbol,_Period,InpEMAPeriod,0,MODE_EMA,PRICE_HIGH);
   hEmaLow  = iMA(_Symbol,_Period,InpEMAPeriod,0,MODE_EMA,PRICE_LOW);
   if(hEmaHigh==INVALID_HANDLE||hEmaLow==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}}
void OnDeinit(const int r){{ IndicatorRelease(hEmaHigh); IndicatorRelease(hEmaLow); }}

datetime g_lastBar=0;
bool NovaBarra(){{ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){{g_lastBar=t;return true;}} return false; }}

int PosicoesAbertas()
{{
   int n=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol && PositionGetInteger(POSITION_MAGIC)==(long)InpMagic) n++;
   return n;
}}

void OnTick()
{{
   if(!NovaBarra()) return;
   double eh[],el[];
   if(CopyBuffer(hEmaHigh,0,1,1,eh)<1) return;
   if(CopyBuffer(hEmaLow,0,1,1,el)<1) return;
   double preco=iClose(_Symbol,_Period,1);
   bool alta=preco>eh[0], baixa=preco<el[0];
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);

   // trailing stop manual sobre o topo
   if(PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)
   {{
      g_topo = MathMax(g_topo>0?g_topo:preco, preco);
      if(preco < g_topo*(1.0-InpTrailPct/100.0)) {{ trade.PositionClose(_Symbol); g_topo=0; return; }}
   }}
   // entra/piramida apenas A FAVOR da tendencia
   if(alta && PosicoesAbertas() < InpMaxPiramide)
   {{
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Escalonada");
   }}
   else if(baixa && PositionSelect(_Symbol))
   {{ trade.PositionClose(_Symbol); g_topo=0; }}
}}
"""
    return s


# ── RSI Sobrevenda/Sobrecompra ─────────────────────────────────────
def _mql5_rsi_reversao(p) -> str:
    s = _mql5_preamble("RSI Sobrevenda Sobrecompra", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpRSIPeriod  = 14;          // Periodo do RSI
input double  InpSobrevenda = 30;          // Nivel de sobrevenda (compra)
input double  InpSobrecompra= 70;          // Nivel de sobrecompra (sai)

int hRSI;
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage);
   hRSI = iRSI(_Symbol,_Period,InpRSIPeriod,PRICE_CLOSE);
   if(hRSI==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r){ IndicatorRelease(hRSI); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double r[];
   if(CopyBuffer(hRSI,0,1,1,r)<1) return;
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool temPos = PositionSelect(_Symbol);
   bool ehLong = temPos && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   if(r[0] < InpSobrevenda && !ehLong)
   {
      if(temPos) trade.PositionClose(_Symbol);
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested RSI");
   }
   else if(r[0] > InpSobrecompra && ehLong)
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── Bandas de Bollinger — Reversão ─────────────────────────────────
def _mql5_bollinger_reversao(p) -> str:
    s = _mql5_preamble("Bandas de Bollinger Reversao", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpBBPeriod   = 20;          // Periodo das bandas
input double  InpBBDesvio   = 2.0;         // Desvios-padrao

int hBB;
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage);
   hBB = iBands(_Symbol,_Period,InpBBPeriod,0,InpBBDesvio,PRICE_CLOSE);
   if(hBB==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r){ IndicatorRelease(hBB); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double mid[],up[],lo[];
   // buffer 0=media, 1=superior, 2=inferior
   if(CopyBuffer(hBB,0,1,1,mid)<1) return;
   if(CopyBuffer(hBB,1,1,1,up)<1) return;
   if(CopyBuffer(hBB,2,1,1,lo)<1) return;
   double preco=iClose(_Symbol,_Period,1);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   // toca banda inferior = compra; volta na media = realiza
   if(preco <= lo[0] && !ehLong)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Bollinger");
   }
   else if(ehLong && preco >= mid[0])
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── Rompimento Donchian ────────────────────────────────────────────
def _mql5_rompimento_donchian(p) -> str:
    s = _mql5_preamble("Rompimento Donchian", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpEntrada    = 20;          // Janela do canal de entrada (topo)
input int     InpSaida      = 10;          // Janela do canal de saida (fundo)

int OnInit(){ trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage); return(INIT_SUCCEEDED); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

double MaxHigh(int n,int desl){ double m=0; for(int i=0;i<n;i++){ double h=iHigh(_Symbol,_Period,desl+i); if(h>m)m=h; } return m; }
double MinLow(int n,int desl){ double m=DBL_MAX; for(int i=0;i<n;i++){ double l=iLow(_Symbol,_Period,desl+i); if(l<m)m=l; } return m; }

void OnTick()
{
   if(!NovaBarra()) return;
   // topo/fundo do candle anterior (desloca 2, como no Python topo[-2]/fundo[-2])
   double topo = MaxHigh(InpEntrada, 2);
   double fundo = MinLow(InpSaida, 2);
   double preco = iClose(_Symbol,_Period,1);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   if(preco >= topo && !ehLong)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Donchian");
   }
   else if(ehLong && preco <= fundo)
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── MACD Tendência ─────────────────────────────────────────────────
def _mql5_macd_tendencia(p) -> str:
    s = _mql5_preamble("MACD Tendencia", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpRapida     = 12;          // EMA rapida
input int     InpLenta      = 26;          // EMA lenta
input int     InpSinal      = 9;           // Linha de sinal

int hMACD;
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage);
   hMACD = iMACD(_Symbol,_Period,InpRapida,InpLenta,InpSinal,PRICE_CLOSE);
   if(hMACD==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r){ IndicatorRelease(hMACD); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double m[],s[];
   // buffer 0=MAIN (macd), 1=SIGNAL; pega 2 valores p/ detectar cruzamento
   if(CopyBuffer(hMACD,0,1,2,m)<2) return;
   if(CopyBuffer(hMACD,1,1,2,s)<2) return;
   bool cruzaCima  = (m[1]<=s[1]) && (m[0]>s[0]);
   bool cruzaBaixo = (m[1]>=s[1]) && (m[0]<s[0]);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   if(cruzaCima)
   {
      if(PositionSelect(_Symbol)) trade.PositionClose(_Symbol);
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested MACD");
   }
   else if(cruzaBaixo && ehLong)
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── Engolfo + Tendência (EMA 50) ───────────────────────────────────
def _mql5_engolfo_tendencia(p) -> str:
    s = _mql5_preamble("Engolfo de Tendencia", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpEMA        = 50;          // EMA de tendencia

int hEMA;
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage);
   hEMA = iMA(_Symbol,_Period,InpEMA,0,MODE_EMA,PRICE_CLOSE);
   if(hEMA==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r){ IndicatorRelease(hEMA); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double e[];
   if(CopyBuffer(hEMA,0,1,1,e)<1) return;
   // candle anterior (1) e o de tras (2)
   double o1=iOpen(_Symbol,_Period,2), c1=iClose(_Symbol,_Period,2);
   double o2=iOpen(_Symbol,_Period,1), c2=iClose(_Symbol,_Period,1);
   bool engolfoAlta = (c1<o1) && (c2>o2) && (c2>o1) && (o2<c1);
   double preco=iClose(_Symbol,_Period,1);
   bool acimaEma = preco>e[0];
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   if(engolfoAlta && acimaEma && !ehLong)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Engolfo");
   }
   else if(ehLong && preco < e[0])
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── Abertura em Gap ────────────────────────────────────────────────
def _mql5_abertura_gap(p) -> str:
    s = _mql5_preamble("Abertura em Gap", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input double  InpGapMin     = 0.5;         // Gap minimo p/ operar (%)

int OnInit(){ trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage); return(INIT_SUCCEEDED); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double ab=iOpen(_Symbol,_Period,1), fechAnt=iClose(_Symbol,_Period,2);
   if(fechAnt==0) return;
   double gap=(ab-fechAnt)/fechAnt*100.0;
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   if(gap >= InpGapMin && !ehLong)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Gap");
   }
   else if(ehLong && gap <= -InpGapMin)
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── Média + ATR Trailing (SMA 50 + trailing por ATR) ───────────────
def _mql5_media_atr_trailing(p) -> str:
    s = _mql5_preamble("Media com ATR Trailing", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpSMA        = 50;          // Media simples de tendencia
input int     InpATR        = 14;          // Periodo do ATR
input double  InpMultATR    = 2.0;         // Multiplicador do ATR (trailing)

int hSMA, hATR;
double g_stop=0;
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage);
   hSMA = iMA(_Symbol,_Period,InpSMA,0,MODE_SMA,PRICE_CLOSE);
   hATR = iATR(_Symbol,_Period,InpATR);
   if(hSMA==INVALID_HANDLE||hATR==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r){ IndicatorRelease(hSMA); IndicatorRelease(hATR); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double sma[],atr[];
   if(CopyBuffer(hSMA,0,1,1,sma)<1) return;
   if(CopyBuffer(hATR,0,1,1,atr)<1) return;
   double preco=iClose(_Symbol,_Period,1);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   // trailing por ATR enquanto comprado
   if(ehLong)
   {
      double novoStop = preco - InpMultATR*atr[0];
      g_stop = MathMax(g_stop>0?g_stop:novoStop, novoStop);
      if(preco <= g_stop) { trade.PositionClose(_Symbol); g_stop=0; return; }
   }
   // entra a favor da tendencia (preco acima da media)
   if(preco > sma[0] && !ehLong)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested ATR Trail");
      g_stop = preco - InpMultATR*atr[0];
   }
}
"""
    return s

# ════════════════════════════════════════════════════════════════════
# CONVERSORES MQL5 — lote 3: estratégias com lógica de pivô/intradiária
# Estas têm tradução menos direta. Onde a lógica Python depende de detalhes
# que mudam em execução real (virada de dia, pivôs confirmados), o código traz
# // TODO honesto. Por isso o aviso "base funcional — revise" é ainda mais
# importante aqui. São pontos de partida sólidos, não EAs blindados.
# ════════════════════════════════════════════════════════════════════

# ── Microcanal (mínimas ascendentes + EMA curta) ───────────────────
def _mql5_microcanal(p) -> str:
    s = _mql5_preamble("Microcanal", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpSeq        = 3;           // Minimas ascendentes seguidas
input int     InpEMA        = 9;           // EMA curta de referencia

int hEMA;
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage);
   hEMA = iMA(_Symbol,_Period,InpEMA,0,MODE_EMA,PRICE_CLOSE);
   if(hEMA==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r){ IndicatorRelease(hEMA); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double e[];
   if(CopyBuffer(hEMA,0,1,1,e)<1) return;
   double preco=iClose(_Symbol,_Period,1);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);

   // quebrou a minima do candle anterior = microcanal acabou -> sai
   if(PositionSelect(_Symbol))
   {
      if(iClose(_Symbol,_Period,1) < iLow(_Symbol,_Period,2))
         trade.PositionClose(_Symbol);
      return;
   }
   // confere N minimas ascendentes seguidas
   bool ascendentes=true;
   for(int k=1; k<=InpSeq; k++)
      if(iLow(_Symbol,_Period,k) <= iLow(_Symbol,_Period,k+1)) { ascendentes=false; break; }

   bool acimaEma = preco > e[0];
   if(ascendentes && acimaEma)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Microcanal");
   }
}
"""
    return s


# ── Suporte/Resistência do dia anterior ────────────────────────────
def _mql5_sr_dia_anterior(p) -> str:
    s = _mql5_preamble("Suporte Resistencia do dia anterior", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """// Usa a maxima/minima do dia ANTERIOR (D1) como referencia. Rompeu a maxima
// de ontem = compra. Funciona em qualquer timeframe lendo o periodo D1.
int OnInit(){ trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage); return(INIT_SUCCEEDED); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   // maxima/minima do candle diario anterior
   double hOntem = iHigh(_Symbol, PERIOD_D1, 1);
   double lOntem = iLow(_Symbol,  PERIOD_D1, 1);
   if(hOntem==0) return;
   double preco = iClose(_Symbol,_Period,1);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   bool ehLong = PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;

   // rompeu a resistencia de ontem = compra
   if(preco > hOntem && !ehLong)
   {
      double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested SR Ontem");
   }
   // perdeu o suporte de ontem = sai
   else if(ehLong && preco < lOntem)
      trade.PositionClose(_Symbol);
}
"""
    return s


# ── Ímã de Fechamento (volta ao fechamento do dia anterior) ────────
def _mql5_fechamento_ima(p) -> str:
    s = _mql5_preamble("Ima de Fechamento", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input double  InpGapMin     = 0.3;         // Distancia minima na abertura (%)
// Ideia: quando abre com gap, o preco tende a voltar (ima) ao fechamento de
// ontem. Alvo = fechamento de ontem. Usa candles diarios como referencia.
int OnInit(){ trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage); return(INIT_SUCCEEDED); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

void OnTick()
{
   if(!NovaBarra()) return;
   double fechOntem = iClose(_Symbol, PERIOD_D1, 1);
   double abHoje    = iOpen(_Symbol,  PERIOD_D1, 0);
   if(fechOntem==0) return;
   double gap = (abHoje - fechOntem)/fechOntem*100.0;
   double preco = iClose(_Symbol,_Period,1);
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   bool temPos = PositionSelect(_Symbol);

   // gestao: realiza quando volta ao fechamento de ontem (o "ima")
   if(temPos)
   {
      long tipo = PositionGetInteger(POSITION_TYPE);
      if(tipo==POSITION_TYPE_BUY  && preco >= fechOntem) trade.PositionClose(_Symbol);
      if(tipo==POSITION_TYPE_SELL && preco <= fechOntem) trade.PositionClose(_Symbol);
      return;
   }
   // abriu com gap pra BAIXO o suficiente = compra apostando na volta pra cima
   if(gap <= -InpGapMin)
   {
      double sl=ask-InpStopLoss*ponto;
      trade.Buy(InpLote,_Symbol,ask,sl,fechOntem,"BotTested Ima");
   }
   // abriu com gap pra CIMA o suficiente = vende apostando na volta pra baixo
   else if(gap >= InpGapMin)
   {
      double sl=bid+InpStopLoss*ponto;
      trade.Sell(InpLote,_Symbol,bid,sl,fechOntem,"BotTested Ima");
   }
}
"""
    return s


# ── Topo Duplo / Fundo Duplo (pivôs) ───────────────────────────────
def _mql5_topo_fundo_duplo(p) -> str:
    s = _mql5_preamble("Topo Duplo Fundo Duplo", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += """input int     InpK          = 5;           // Candles de cada lado p/ confirmar pivo
input double  InpTolerancia = 0.4;         // Diferenca maxima entre os 2 topos (%)
// Detecta fundo duplo: dois fundos parecidos seguidos = sinal de compra.
// TODO: versao simplificada — confirma pivo olhando K candles de cada lado.
// Para producao, considere validar o rompimento do pescoco (neckline).
int OnInit(){ trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpSlippage); return(INIT_SUCCEEDED); }
datetime g_lastBar=0;
bool NovaBarra(){ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){g_lastBar=t;return true;} return false; }

bool EhPivoFundo(int desl)
{
   double centro = iLow(_Symbol,_Period,desl);
   for(int m=1; m<=InpK; m++)
   {
      if(iLow(_Symbol,_Period,desl-m) < centro) return false;
      if(iLow(_Symbol,_Period,desl+m) < centro) return false;
   }
   return true;
}

double g_fundo1=0;
int    g_idxFundo1=-1;

void OnTick()
{
   if(!NovaBarra()) return;
   if(Bars(_Symbol,_Period) < 2*InpK+2) return;
   double ponto=_Point, ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);

   // confirma pivo de fundo K candles atras
   int desl = InpK + 1;
   if(EhPivoFundo(desl))
   {
      double f = iLow(_Symbol,_Period,desl);
      if(g_fundo1>0)
      {
         double dif = MathAbs(f - g_fundo1)/g_fundo1*100.0;
         // dois fundos parecidos = fundo duplo -> compra
         if(dif <= InpTolerancia && !PositionSelect(_Symbol))
         {
            double sl=ask-InpStopLoss*ponto, tp=ask+InpTakeProfit*ponto;
            trade.Buy(InpLote,_Symbol,ask,sl,tp,"BotTested Fundo Duplo");
            g_fundo1=0; return;
         }
      }
      g_fundo1 = f;
   }
}
"""
    return s


_CONVERSORES_MQL5 = {
    "canal_ema20_hl": _mql5_canal_ema20_hl,
    "cruzamento_ema_9_21": _mql5_cruzamento_ema_9_21,
    "tendencia_diaria_piramide": _mql5_tendencia_diaria_piramide,
    "rsi_reversao": _mql5_rsi_reversao,
    "bollinger_reversao": _mql5_bollinger_reversao,
    "rompimento_donchian": _mql5_rompimento_donchian,
    "macd_tendencia": _mql5_macd_tendencia,
    "engolfo_tendencia": _mql5_engolfo_tendencia,
    "abertura_gap": _mql5_abertura_gap,
    "media_atr_trailing": _mql5_media_atr_trailing,
    "microcanal": _mql5_microcanal,
    "sr_dia_anterior": _mql5_sr_dia_anterior,
    "fechamento_ima": _mql5_fechamento_ima,
    "topo_fundo_duplo": _mql5_topo_fundo_duplo,
}


def _mql5_via_ia(codigo_py: str, nome: str, p) -> Optional[str]:
    """Caminho B: código customizado → IA converte p/ MQL5 (CTrade). Sempre com aviso."""
    import sys
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave or not codigo_py.strip():
        return None
    try:
        import httpx
        sistema = (
            "Você converte estratégias de trading de Python (biblioteca backtesting.py) para "
            "Expert Advisor MQL5 do MetaTrader 5. REGRAS: (1) gere SOMENTE código MQL5 válido; "
            "(2) use #include <Trade/Trade.mqh> e a classe CTrade; (3) inputs para lote, stop, take, "
            "magic; (4) processe uma vez por barra nova; (5) traduza a lógica de entrada/saída "
            "fielmente — não invente regras; (6) stop/take em pontos (_Point); (7) onde não houver "
            "equivalente direto, deixe // TODO explicando; (8) inclua no topo um comentário de aviso: "
            "que opera com dinheiro real, testar em demo, base funcional. NÃO escreva nada fora do código."
        )
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
                "max_tokens": 2200, "temperature": 0.2, "system": sistema,
                "messages": [{"role": "user", "content":
                    f"Converta esta estratégia '{nome}' para Expert Advisor MQL5:\n\n{codigo_py}"}],
            },
            timeout=25.0,
        )
        if r.status_code != 200:
            print(f"MQL5 IA status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        if texto.startswith("```"):
            texto = texto.strip("`")
            for pref in ("mql5", "cpp", "c++"):
                if texto.lower().startswith(pref):
                    texto = texto[len(pref):]
                    break
        # garante o cabeçalho de aviso mesmo se a IA não puser
        if "BotTested" not in texto[:300]:
            texto = _MQL5_AVISO_HEADER + "\n" + texto
        return texto.strip() or None
    except Exception as e:
        print(f"MQL5 IA erro: {e}", file=sys.stderr)
        return None


def gerar_mql5(estrategia_id: str, codigo_py: str, nome: str, p) -> dict:
    """A: estratégia conhecida → conversor testado; B: customizado → IA (com aviso).
    Retorna {codigo, fonte, aviso, filename}."""
    safe = "".join(c if c.isalnum() else "_" for c in (nome or "BotTested"))[:40] or "BotTested"
    filename = f"BotTested_{safe}.mq5"
    conv = _CONVERSORES_MQL5.get((estrategia_id or "").strip())
    if conv:
        return {"codigo": conv(p), "fonte": "testado", "aviso": "", "filename": filename}
    mq = _mql5_via_ia(codigo_py, nome or "Estrategia", p)
    if mq:
        aviso = ("Conversao automatica por IA — revise o codigo com atencao. Teste em conta DEMO "
                 "antes de qualquer uso real. Confira entradas/saidas, stop, take e lote.")
        return {"codigo": mq, "fonte": "ia", "aviso": aviso, "filename": filename}
    return {"codigo": "", "fonte": "indisponivel",
            "aviso": "Conversao automatica indisponivel para este codigo no momento.",
            "filename": filename}


# ── Endpoint: exportar estratégia para MQL5 (MetaTrader 5) ──
@app.post("/exportar/mql5")
def exportar_mql5(req: BacktestCustom):
    """Gera Expert Advisor MQL5 da estratégia ativa. Estratégia conhecida usa
    conversor testado; código customizado cai na IA (com aviso). EXECUÇÃO REAL —
    sempre com avisos de risco. Usa os parâmetros reais do usuário."""
    est_id = (getattr(req, "estrategia_id", "") or "").strip()
    nome = getattr(req, "estrategia_nome", "") or "Estrategia"
    res = gerar_mql5(est_id, getattr(req, "codigo", "") or "", nome, req)
    res["formato"] = "MQL5"
    res["plataforma"] = "MetaTrader 5"
    return res


# ════════════════════════════════════════════════════════════════════
# CAMADA 1 — Leitura de DIREÇÃO (D1 + 1H), multi-sinal
# 4 sinais que se confirmam: estrutura (topos/fundos), inclinação das médias,
# força do movimento (corpo vs ATR), alinhamento D1+1H.
# Retorna veredito {direcao: alta/baixa/lateral, confianca: 0-100, sinais: {...}}
# É a 1ª camada da análise top-down. Reusa baixar_dados (yfinance).
# ════════════════════════════════════════════════════════════════════


def _ema(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()


def _atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ── Sinal 1: estrutura de topos e fundos (o mais importante) ───────
def _sinal_estrutura(df, lookback=4, n_pivos=3, tol=0.003):
    """Topos e fundos ascendentes = alta; descendentes = baixa. Confirma pivôs
    olhando 'lookback' candles de cada lado. 'tol' = zona morta (% do preço) pra
    não chamar de tendência uma diferença mínima entre pivôs (isso é lateral)."""
    h, l = df["High"].values, df["Low"].values
    n = len(df)
    topos, fundos = [], []
    for i in range(lookback, n - lookback):
        jan_h = h[i - lookback:i + lookback + 1]
        jan_l = l[i - lookback:i + lookback + 1]
        if h[i] == jan_h.max():
            topos.append(h[i])
        if l[i] == jan_l.min():
            fundos.append(l[i])
    if len(topos) < 2 or len(fundos) < 2:
        return "lateral", 0.0
    tt = topos[-n_pivos:] if len(topos) >= n_pivos else topos[-2:]
    ff = fundos[-n_pivos:] if len(fundos) >= n_pivos else fundos[-2:]
    preco_ref = float(df["Close"].iloc[-1]) or 1.0
    dz = tol * preco_ref  # zona morta absoluta

    def _tendencia(seq):
        # sobe se cada passo cresce mais que a zona morta; desce se cai mais
        sobe = all(seq[k + 1] - seq[k] > dz for k in range(len(seq) - 1))
        desce = all(seq[k] - seq[k + 1] > dz for k in range(len(seq) - 1))
        return "alta" if sobe else "baixa" if desce else "lateral"

    dir_t = _tendencia(tt)
    dir_f = _tendencia(ff)
    if dir_t == "alta" and dir_f == "alta":
        return "alta", 1.0
    if dir_t == "baixa" and dir_f == "baixa":
        return "baixa", 1.0
    # um confirma, outro lateral = sinal parcial
    if "alta" in (dir_t, dir_f) and "baixa" not in (dir_t, dir_f):
        return "alta", 0.5
    if "baixa" in (dir_t, dir_f) and "alta" not in (dir_t, dir_f):
        return "baixa", 0.5
    return "lateral", 0.0


# ── Sinal 2: inclinação das médias + lado do preço ─────────────────
def _sinal_medias(df, n_curta=20, n_longa=50):
    """Média longa inclinada + preço do lado certo. Inclinação medida pela
    variação da média longa nas últimas barras."""
    c = df["Close"]
    if len(c) < n_longa + 6:
        return "lateral", 0.0
    ema_l = _ema(c, n_longa)
    ema_c = _ema(c, n_curta)
    preco = float(c.iloc[-1])
    incl = float(ema_l.iloc[-1] - ema_l.iloc[-6])  # inclinação ~6 barras
    base = float(_atr(df).iloc[-1]) or 1.0
    incl_rel = incl / base  # inclinação relativa ao ATR
    acima = preco > float(ema_l.iloc[-1])
    curta_acima = float(ema_c.iloc[-1]) > float(ema_l.iloc[-1])
    if incl_rel > 0.15 and acima and curta_acima:
        return "alta", min(1.0, 0.5 + abs(incl_rel))
    if incl_rel < -0.15 and not acima and not curta_acima:
        return "baixa", min(1.0, 0.5 + abs(incl_rel))
    # inclinação fraca / preço do lado contrário = lateral ou parcial
    if incl_rel > 0.05 and acima:
        return "alta", 0.4
    if incl_rel < -0.05 and not acima:
        return "baixa", 0.4
    return "lateral", 0.0


# ── Sinal 3: força do movimento (corpo dominante vs ATR) ───────────
def _sinal_forca(df, n=10, corpo_min=0.55):
    """Quão direcionais são as últimas n barras: corpo dominante e fechamentos
    na mesma direção indicam tendência real (não ruído lateral)."""
    if len(df) < n + 1:
        return "lateral", 0.0
    rec = df.iloc[-n:]
    corpo = (rec["Close"] - rec["Open"])
    rng = (rec["High"] - rec["Low"]).replace(0, np.nan)
    frac = (corpo.abs() / rng).fillna(0)
    fortes = frac >= corpo_min
    altas = ((corpo > 0) & fortes).sum()
    baixas = ((corpo < 0) & fortes).sum()
    total_fortes = int(fortes.sum())
    if total_fortes < max(2, n // 3):
        return "lateral", 0.0  # poucas barras fortes = lateral/ruído
    if altas > baixas:
        return "alta", min(1.0, altas / n + 0.2)
    if baixas > altas:
        return "baixa", min(1.0, baixas / n + 0.2)
    return "lateral", 0.0


# ── Combina os 3 sinais acima num veredito de UM timeframe ─────────
def _veredito_tf(df):
    s_est, p_est = _sinal_estrutura(df)
    s_med, p_med = _sinal_medias(df)
    s_for, p_for = _sinal_forca(df)
    pesos = {"estrutura": 1.3, "medias": 1.0, "forca": 0.9}
    score = {"alta": 0.0, "baixa": 0.0, "lateral": 0.0}
    score[s_est] += pesos["estrutura"] * p_est
    score[s_med] += pesos["medias"] * p_med
    score[s_for] += pesos["forca"] * p_for
    direcao = max(("alta", "baixa", "lateral"), key=lambda k: score[k])
    if score[direcao] <= 0:
        direcao = "lateral"

    # TRAVA ANTI-LATERAL + DETECÇÃO DE VIRADA (calibrada com gráficos reais):
    # - 2+ sinais a favor = tendência firme.
    # - sinais brigando (1 a favor, 1 contra) = lateral.
    # - força recente aponta uma direção e estrutura/médias ainda NÃO confirmaram
    #   (laterais), sem nenhum sinal contrário = POSSÍVEL VIRADA: segue o
    #   movimento recente (força manda), mas marca virada=True. É o caso de uma
    #   queda/alta recente forte antes da estrutura longa virar.
    virada = False
    if direcao != "lateral":
        a_favor = sum(1 for s in (s_est, s_med, s_for) if s == direcao)
        contrario = "baixa" if direcao == "alta" else "alta"
        tem_contra = any(s == contrario for s in (s_est, s_med, s_for))
        if a_favor < 2 and tem_contra:
            direcao = "lateral"
    # se o veredito deu lateral MAS a força recente é direcional e nada a contradiz,
    # é uma virada começando — assume a direção da força
    if direcao == "lateral" and s_for in ("alta", "baixa"):
        oposto = "baixa" if s_for == "alta" else "alta"
        if s_est != oposto and s_med != oposto:
            direcao = s_for
            virada = True
    return direcao, score, {"estrutura": s_est, "medias": s_med, "forca": s_for}, virada


# ── Sinal 4 (orquestrador): alinhamento D1 + 1H = veredito final ───
def ler_direcao(ativo: str, periodo: str = "6 meses", baixar=None) -> dict:
    """Leitura de direção robusta combinando D1 e 1H. 'baixar' é a função
    baixar_dados injetada (pra reusar a do api.py). Retorna veredito completo."""
    if baixar is None:
        raise ValueError("baixar_dados não injetada")
    out = {"ativo": ativo, "direcao": "lateral", "confianca": 0,
           "d1": None, "h1": None, "sinais": {}, "alinhado": False,
           "virada": False, "estado": "lateral"}
    try:
        df_d1 = baixar(ativo, periodo, "1d")
        if df_d1 is None or len(df_d1) < 60:
            return out
        dir_d1, sc_d1, sin_d1, virada_d1 = _veredito_tf(df_d1)
        out["d1"] = dir_d1
        out["sinais"]["d1"] = sin_d1

        # 1H: usa um período menor (yfinance limita histórico intradiário)
        dir_h1, sin_h1 = None, {}
        try:
            df_h1 = baixar(ativo, "1 mês", "1h")
            if df_h1 is not None and len(df_h1) >= 60:
                dir_h1, sc_h1, sin_h1, _virada_h1 = _veredito_tf(df_h1)
        except Exception:
            dir_h1 = None
        out["h1"] = dir_h1
        out["sinais"]["h1"] = sin_h1

        # confiança: D1 manda a direção (estrutural). O 1H só ajusta levemente
        # (é mais instável por causa do histórico intradiário curto).
        nz = [k for k, v in sin_d1.items() if v == dir_d1 and dir_d1 != "lateral"]
        n_favor = len(nz)
        base_map = {0: 0, 1: 45, 2: 68, 3: 85}
        base_conf = base_map.get(n_favor, 0)

        # POSSÍVEL VIRADA: a força recente puxou a direção, estrutura ainda não
        # confirmou. Direção segue o movimento recente, mas confiança é moderada
        # (é uma transição, não tendência madura) e o estado avisa.
        if virada_d1 and dir_d1 != "lateral":
            base_conf = max(base_conf, 40)   # virada começa com confiança média
            out["virada"] = True

        if dir_h1 is not None and dir_h1 == dir_d1 and dir_d1 != "lateral":
            out["alinhado"] = True
            base_conf = min(100, base_conf + 12)
        elif dir_h1 is not None and dir_h1 != "lateral" and dir_h1 != dir_d1:
            base_conf = max(0, base_conf - 8)

        out["direcao"] = dir_d1
        out["confianca"] = base_conf
        # estado legível: tendência firme / possível virada / lateral
        if dir_d1 == "lateral":
            out["estado"] = "lateral"
        elif out["virada"]:
            out["estado"] = "possivel_virada_" + dir_d1
        else:
            out["estado"] = "tendencia_" + dir_d1
        return out
    except Exception as e:
        out["erro"] = str(e)
        return out


# ── Endpoint: leitura de DIREÇÃO (Camada 1 da análise top-down) ──
@app.get("/analise/direcao")
def analise_direcao(ativo: str = "XAU/USD", periodo: str = "6 meses"):
    """Camada 1: leitura de direção robusta (D1+1H, 4 sinais). O EA pergunta
    aqui a cada barra. Read-only, não comanda — informa direção + confiança."""
    return ler_direcao(ativo, periodo, baixar=baixar_dados)


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
                      "BotTested EMA Channel", 0, 0, clrGreen);
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
        "desc": "Assinatura BotTested: canal entre EMA20 das máximas e EMA20 das mínimas. Rompe pra cima = compra; rompe pra baixo = venda; dentro do canal = lateral, não opera.",
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
        "nome": "Tendência Diária Escalonada",
        "desc": "Assinatura BotTested: lê a direção do D1 pela manhã, entra SEMPRE a favor (nunca contra), escalona na mesma direção, trailing protege o lucro. Valide por ativo antes de automatizar.",
        "tags": ["TENDÊNCIA", "ESCALONADO"], "nivel": "avançado",
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
        "desc": "Assinatura BotTested: dois topos na mesma altura + rompimento da linha do pescoço (o fundo entre eles) = venda. Mesma família do Ombro-Cabeça-Ombro: quando a cabeça não se forma, vira Topo Duplo — a entrada é a mesma. Espelhado no Fundo Duplo / OCO invertido = compra (mais difícil de ver a olho; o detector acha pra você). Alvo pela altura do padrão, stop atrás dos topos/fundos.",
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
    "en": {"nome": "Daily Trend Scaling", "desc": "Reads the D1 direction in the morning, ALWAYS enters with the trend (never against), scales in the same direction, trailing protects profit. Validate per asset before automating."},
    "es": {"nome": "Tendencia Diaria Escalonada", "desc": "Lee la dirección del D1 por la mañana, entra SIEMPRE a favor (nunca en contra), escalona en la misma dirección, trailing protege la ganancia. Valida por activo antes de automatizar."}},
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

# Tradução de TAGS e NÍVEL (PT é o original). Tags universais (EMA/RSI/MACD…) ficam iguais.
_TAG_I18N = {
    "TENDÊNCIA":   {"en": "TREND",    "es": "TENDENCIA"},
    "ESCALONADO":  {"en": "SCALING",  "es": "ESCALONADA"},
    "REVERSÃO":    {"en": "REVERSAL", "es": "REVERSIÓN"},
    "ROMPIMENTO":  {"en": "BREAKOUT", "es": "RUPTURA"},
    "IMPULSO":     {"en": "MOMENTUM", "es": "IMPULSO"},
    "ÍMÃ":         {"en": "MAGNET",   "es": "IMÁN"},
}
_NIVEL_I18N = {
    "iniciante":     {"en": "beginner",     "es": "principiante"},
    "intermediário": {"en": "intermediate", "es": "intermedio"},
    "avançado":      {"en": "advanced",     "es": "avanzado"},
}
def _tag_loc(tag, lang):
    if lang and lang != "pt":
        return _TAG_I18N.get(tag, {}).get(lang, tag)
    return tag
def _nivel_loc(nivel, lang):
    if lang and lang != "pt":
        return _NIVEL_I18N.get(nivel, {}).get(lang, nivel)
    return nivel

# Categoria language-independent (derivada da tag PT original) p/ escolher o robô no front
def _categoria_de(tags):
    s = set(t.upper() for t in (tags or []))
    if "TENDÊNCIA" in s: return "tendencia"
    if "REVERSÃO" in s: return "reversao"
    if "ROMPIMENTO" in s: return "rompimento"
    if "PRICE ACTION" in s: return "priceaction"
    if "IMPULSO" in s: return "impulso"
    if "ÍMÃ" in s: return "ima"
    return "outro"


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


# ══════════════════════════════════════════════════════════════════════════
# ║  CALENDÁRIO ECONÔMICO — coletor do feed semanal (ForexFactory/Fair Eco) ║
# ║                                                                          ║
# ║  Objetivo: alimentar (1) a feature "Calendário Econômico" no produto e   ║
# ║  (2) o fallback CSV do filtro de notícias dos bots no Strategy Tester.   ║
# ║                                                                          ║
# ║  Fonte: feed semanal público nfs.faireconomy.media (json).               ║
# ║  REGRA DE OURO: baixar no MÁXIMO 1x/semana (cron). O feed limita a       ║
# ║  2 downloads / 5min por IP em QUALQUER formato — por isso só o cron      ║
# ║  bate nele. Nunca chamar /calendario/atualizar a cada request.           ║
# ║                                                                          ║
# ║  TABELA (rodar no Supabase SQL editor):                                  ║
# ║    create table if not exists public.calendario_economico (             ║
# ║      id bigint generated always as identity primary key,                 ║
# ║      titulo text not null,                                               ║
# ║      moeda text not null,                                                ║
# ║      impacto text not null,            -- alto|medio|baixo|feriado        ║
# ║      data_evento timestamptz not null, -- sempre em UTC                   ║
# ║      forecast text, previous text, actual text,                          ║
# ║      fonte text default 'forexfactory',                                  ║
# ║      atualizado_em timestamptz default now(),                            ║
# ║      unique (moeda, data_evento, titulo)                                  ║
# ║    );                                                                     ║
# ║    create index if not exists idx_calecon_data                           ║
# ║      on public.calendario_economico (data_evento);                       ║
# ║    alter table public.calendario_economico enable row level security;    ║
# ║    create policy "leitura publica calendario"                            ║
# ║      on public.calendario_economico for select using (true);             ║
# ══════════════════════════════════════════════════════════════════════════

_CAL_FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]

# normaliza o nível de impacto do feed -> nosso padrão interno
def _cal_normaliza_impacto(v: str) -> str:
    s = (v or "").strip().lower()
    if s.startswith("high"):
        return "alto"
    if s.startswith("medium") or s.startswith("med"):
        return "medio"
    if s.startswith("low"):
        return "baixo"
    if "holiday" in s or "bank" in s:
        return "feriado"
    return "baixo"

_CAL_RANK = {"alto": 3, "medio": 2, "baixo": 1, "feriado": 0}


def _cal_baixar_feed():
    """Baixa o(s) feed(s) semanal(is) e devolve lista de eventos normalizados.
    Não levanta exceção: em erro/rate-limit devolve o que conseguiu (pode ser []).
    """
    import httpx
    from datetime import datetime, timezone
    eventos = []
    vistos = set()  # dedupe (moeda|data|titulo)
    for i, url in enumerate(_CAL_FEEDS):
        try:
            if i > 0:
                import time as _t
                _t.sleep(2)  # respeita o limite (2 req / 5min no mesmo IP)
            r = httpx.get(url, timeout=20.0,
                          headers={"User-Agent": "BotTested/1.0 (calendario)"})
            if r.status_code != 200:
                print(f"[calendario] {url} -> HTTP {r.status_code}")
                continue
            ctype = r.headers.get("content-type", "")
            # quando bate no rate-limit, vem HTML "Request Denied" em vez de JSON
            if "json" not in ctype and not r.text.strip().startswith("["):
                print(f"[calendario] {url} -> resposta não-JSON (rate-limit?). Pulando.")
                continue
            dados = r.json()
        except Exception as e:
            print(f"[calendario] falha ao baixar {url}: {e}")
            continue

        for ev in (dados or []):
            try:
                titulo = (ev.get("title") or "").strip()
                moeda = (ev.get("country") or "").strip().upper()
                if not titulo or not moeda:
                    continue
                # data vem em ISO 8601 com offset (ex.: 2026-06-23T08:30:00-04:00)
                bruta = ev.get("date") or ev.get("datetime") or ""
                if not bruta:
                    continue
                dt = datetime.fromisoformat(bruta.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_utc = dt.astimezone(timezone.utc)
                data_iso = dt_utc.isoformat()

                chave = f"{moeda}|{data_iso}|{titulo}"
                if chave in vistos:
                    continue
                vistos.add(chave)

                def _txt(x):
                    x = ev.get(x)
                    if x is None:
                        return None
                    x = str(x).strip()
                    return x or None

                eventos.append({
                    "titulo": titulo,
                    "moeda": moeda,
                    "impacto": _cal_normaliza_impacto(ev.get("impact")),
                    "data_evento": data_iso,
                    "forecast": _txt("forecast"),
                    "previous": _txt("previous"),
                    "actual": _txt("actual"),
                    "fonte": "forexfactory",
                })
            except Exception as e:
                print(f"[calendario] evento ignorado: {e}")
                continue
    return eventos


def _cal_gravar(eventos):
    """Upsert não-destrutivo na calendario_economico. Devolve nº de linhas enviadas."""
    if not eventos:
        return 0
    sb = _sb_admin()
    if sb is None:
        raise RuntimeError("Supabase indisponível (SUPABASE_URL/SERVICE_KEY ausentes)")
    enviados = 0
    # envia em lotes para não estourar payload
    for j in range(0, len(eventos), 200):
        lote = eventos[j:j + 200]
        sb.table("calendario_economico").upsert(
            lote, on_conflict="moeda,data_evento,titulo"
        ).execute()
        enviados += len(lote)
    return enviados


# ── CRON (1x/semana): baixa o feed e atualiza a tabela. Protegido por token. ──
class CalAtualizarReq(BaseModel):
    token: str

@app.post("/calendario/atualizar")
def calendario_atualizar(req: CalAtualizarReq):
    token_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not token_certo or req.token != token_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    eventos = _cal_baixar_feed()
    if not eventos:
        return {"ok": False, "msg": "Feed vazio ou indisponível (rate-limit?). "
                                    "Nada foi alterado.", "gravados": 0}
    try:
        n = _cal_gravar(eventos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gravar: {e}")
    return {"ok": True, "msg": f"{n} evento(s) atualizado(s).", "gravados": n}


# ── FEATURE: próximos eventos (para o app e para o Radar). Público. ──
@app.get("/calendario/proximos")
def calendario_proximos(dias: int = 7, impacto_min: str = "medio",
                        moedas: str = "", incluir_feriado: bool = False,
                        limite: int = 200):
    """Eventos a partir de agora (UTC), ordenados por data.
      - dias: janela à frente (1..30)
      - impacto_min: 'alto' | 'medio' | 'baixo'
      - moedas: filtro opcional, ex.: 'USD,EUR' (vazio = todas)
      - incluir_feriado: inclui feriados bancários
    """
    from datetime import datetime, timezone, timedelta
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    dias = max(1, min(int(dias or 7), 30))
    agora = datetime.now(timezone.utc)
    ate = agora + timedelta(days=dias)
    corte = _CAL_RANK.get((impacto_min or "medio").lower(), 2)

    q = (sb.table("calendario_economico")
         .select("titulo,moeda,impacto,data_evento,forecast,previous,actual")
         .gte("data_evento", agora.isoformat())
         .lte("data_evento", ate.isoformat())
         .order("data_evento", desc=False)
         .limit(1000))
    rows = q.execute().data or []

    filtro_moedas = set(m.strip().upper() for m in (moedas or "").split(",") if m.strip())
    out = []
    for r in rows:
        imp = r.get("impacto", "baixo")
        if imp == "feriado":
            if not incluir_feriado:
                continue
        elif _CAL_RANK.get(imp, 1) < corte:
            continue
        if filtro_moedas and r.get("moeda", "") not in filtro_moedas:
            continue
        try:
            dt = datetime.fromisoformat(r["data_evento"].replace("Z", "+00:00"))
            horas = round((dt - agora).total_seconds() / 3600, 1)
        except Exception:
            horas = None
        r["em_horas"] = horas
        out.append(r)
        if len(out) >= max(1, min(int(limite or 200), 500)):
            break
    return {"agora_utc": agora.isoformat(), "dias": dias,
            "impacto_min": impacto_min, "total": len(out), "eventos": out}


# ── FALLBACK CSV: para o Strategy Tester do robô (calendário não roda no tester). ──
@app.get("/calendario/csv")
def calendario_csv(dias: int = 14, impacto_min: str = "medio"):
    """CSV simples para o NewsFilter no modo backtest.
    Colunas: data_utc,moeda,impacto,titulo  (data em ISO 8601 UTC)."""
    from datetime import datetime, timezone, timedelta
    from fastapi.responses import PlainTextResponse
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    dias = max(1, min(int(dias or 14), 90))
    agora = datetime.now(timezone.utc)
    de = agora - timedelta(days=2)
    ate = agora + timedelta(days=dias)
    corte = _CAL_RANK.get((impacto_min or "medio").lower(), 2)
    rows = (sb.table("calendario_economico")
            .select("titulo,moeda,impacto,data_evento")
            .gte("data_evento", de.isoformat())
            .lte("data_evento", ate.isoformat())
            .order("data_evento", desc=False).limit(2000).execute().data or [])
    linhas = ["data_utc,moeda,impacto,titulo"]
    for r in rows:
        imp = r.get("impacto", "baixo")
        if imp == "feriado" or _CAL_RANK.get(imp, 1) < corte:
            continue
        titulo = (r.get("titulo", "") or "").replace(",", " ").replace("\n", " ")
        linhas.append(f'{r.get("data_evento","")},{r.get("moeda","")},{imp},{titulo}')
    return PlainTextResponse("\n".join(linhas), media_type="text/csv")


# ── PÁGINA COMPLETA (estilo ForexFactory): todos os eventos, todos os impactos ──
@app.get("/calendario/semana")
def calendario_semana(de_dias: int = 7, ate_dias: int = 10):
    """Todos os eventos numa janela (todas as moedas, todos os impactos).
    Inclui dias passados da semana (que já têm 'actual') como o ForexFactory.
      - de_dias: dias para trás (default 7 = semana corrente)
      - ate_dias: dias para frente (default 10)
    """
    from datetime import datetime, timezone, timedelta
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    agora = datetime.now(timezone.utc)
    de = agora - timedelta(days=max(0, min(int(de_dias or 7), 60)))
    ate = agora + timedelta(days=max(1, min(int(ate_dias or 10), 60)))
    rows = (sb.table("calendario_economico")
            .select("titulo,moeda,impacto,data_evento,forecast,previous,actual")
            .gte("data_evento", de.isoformat())
            .lte("data_evento", ate.isoformat())
            .order("data_evento", desc=False).limit(3000).execute().data or [])
    return {"agora_utc": agora.isoformat(), "total": len(rows), "eventos": rows}


# ── VITRINE: estratégias prontas + desempenho MÉDIO histórico (público) ──
# Regra de marca: nunca revelar a existência da biblioteca interna. Aqui
# devolvemos apenas uma MÉDIA de desempenho histórico por estratégia,
# apresentada como "média histórica" — sem expor linhas nem a fonte.
_VITRINE_CACHE = {"t": 0.0, "dados": None}

@app.get("/estrategias/vitrine")
def estrategias_vitrine(lang: str = "pt"):
    import time as _t
    # cache de 1h (cálculo de média é estável; evita varrer a tabela a cada visita)
    if _VITRINE_CACHE["dados"] is not None and (_t.time() - _VITRINE_CACHE["t"] < 3600):
        return _VITRINE_CACHE["dados"]

    # agrega média por estrategia_id (server-side; nunca devolve linha individual)
    medias = {}
    sb = _sb_admin()
    if sb is not None:
        try:
            rows = (sb.table("estudo_biblioteca")
                    .select("estrategia_id,ativo,sharpe,profit_factor,retorno,win_rate,trades,forca")
                    .limit(8000).execute().data or [])
            acc = {}
            por_ativo = {}   # estrategia_id -> {ativo -> {sh:[], n:int}}  (p/ ranking de ativos)
            for r in rows:
                eid = r.get("estrategia_id")
                if not eid:
                    continue
                a = acc.setdefault(eid, {"sh": [], "pf": [], "ret": [], "wr": [], "n": 0, "forte": 0})
                a["sh"].append(float(r.get("sharpe") or 0))
                a["pf"].append(float(r.get("profit_factor") or 0))
                a["ret"].append(float(r.get("retorno") or 0))
                a["wr"].append(float(r.get("win_rate") or 0))
                a["n"] += 1
                if r.get("forca") == "forte":
                    a["forte"] += 1
                # acumula sharpe por ativo (p/ descobrir os ativos onde a estratégia mais funciona)
                ativo_nome = r.get("ativo")
                if ativo_nome:
                    pa = por_ativo.setdefault(eid, {}).setdefault(ativo_nome, {"sh": [], "n": 0})
                    pa["sh"].append(float(r.get("sharpe") or 0))
                    pa["n"] += 1
            def _med(xs):
                xs = [x for x in xs if x is not None]
                return round(sum(xs) / len(xs), 2) if xs else None
            # top 3 ativos por estratégia (maior sharpe médio; mínimo de dados p/ não ser ruído)
            # ── FILTRO DE ROBUSTEZ ──────────────────────────────────────────
            # Um ativo só entra no "top" se tiver evidência decente — senão é
            # ruído estatístico (banco ainda parcialmente populado). Critérios:
            #   • mínimo de backtests medidos para aquele ativo (não 1 só)
            #   • sharpe médio acima de um piso (mesmo critério de "robusta")
            # Se a estratégia não tem ativos robustos suficientes, top fica vazio
            # e o card cai no fallback do "mercados" curado manualmente.
            _MIN_BACKTESTS_ATIVO = 2     # nº mínimo de medições por ativo
            _PISO_SHARPE_ATIVO   = 0.5    # sharpe médio mínimo p/ ser sugerível
            top_ativos_por_est = {}
            for eid, ativos in por_ativo.items():
                ranking = []
                for ativo_nome, d in ativos.items():
                    sh_med = _med(d["sh"])
                    if sh_med is None:
                        continue
                    # só entra se tiver dados suficientes E qualidade mínima
                    if d["n"] < _MIN_BACKTESTS_ATIVO:
                        continue
                    if sh_med < _PISO_SHARPE_ATIVO:
                        continue
                    ranking.append((ativo_nome, sh_med, d["n"]))
                ranking.sort(key=lambda x: x[1], reverse=True)
                top_ativos_por_est[eid] = [nome for (nome, _sh, _n) in ranking[:3]]
            for eid, a in acc.items():
                medias[eid] = {
                    "sharpe_medio": _med(a["sh"]),
                    "pf_medio": _med(a["pf"]),
                    "retorno_medio": _med(a["ret"]),
                    "winrate_medio": _med(a["wr"]),
                    "combos": a["n"],
                    "forte_pct": round(100 * a["forte"] / a["n"]) if a["n"] else 0,
                    "top_ativos": top_ativos_por_est.get(eid, []),
                }
        except Exception as e:
            print(f"[vitrine] erro ao agregar: {e}")

    itens = []
    for est in ESTRATEGIAS_PRONTAS:
        eid = est["id"]
        m = medias.get(eid, {})
        itens.append({
            "id": eid,
            "nome": _estrat_loc(est, lang, "nome"),
            "desc": _estrat_loc(est, lang, "desc"),
            "emoji": est.get("emoji", "📈"),
            "tags": [_tag_loc(t, lang) for t in est.get("tags", [])],
            "categoria": _categoria_de(est.get("tags", [])),
            "nivel": _nivel_loc(est.get("nivel", ""), lang),
            "mercados": est.get("mercados", []),
            "top_ativos": (m.get("top_ativos") or est.get("mercados", [])),
            "casa": bool(est.get("casa")),
            "codigo": est.get("codigo", ""),
            "sharpe_medio": m.get("sharpe_medio"),
            "pf_medio": m.get("pf_medio"),
            "retorno_medio": m.get("retorno_medio"),
            "winrate_medio": m.get("winrate_medio"),
            "combos": m.get("combos", 0),
            "forte_pct": m.get("forte_pct", 0),
        })
    out = {"total": len(itens), "estrategias": itens}
    _VITRINE_CACHE["t"] = _t.time()
    _VITRINE_CACHE["dados"] = out
    return out


# ── RADAR CHAT: conversa com IA (focada em trading/plataforma; Pro/Trader Pro) ──
class RadarChatReq(BaseModel):
    user_id: str = ""
    mensagem: str = ""
    historico: list = []          # [{role:'user'|'assistant', content:str}, ...]
    idioma: str = "pt"
    codigo: str = ""              # código atual no editor (contexto opcional)
    resultado: dict = {}          # último resultado de backtest na tela (contexto opcional)
    config: dict = {}             # parâmetros atuais (stop, take, capital, máx ops, spread, ativo, tf, período)
    estrategia_id: str = ""       # id da estratégia escolhida na vitrine (p/ comparar com a média do card)

_CHAT_BLOQUEIO = {
    "pt": "💬 O chat com a IA é exclusivo dos planos <b>Pro</b> e <b>Trader Pro</b>. "
          "Faça upgrade em 💳 Planos para conversar comigo sobre suas estratégias, métricas e a plataforma.",
    "en": "💬 AI chat is exclusive to the <b>Pro</b> and <b>Trader Pro</b> plans. "
          "Upgrade in 💳 Plans to chat with me about your strategies, metrics and the platform.",
    "es": "💬 El chat con la IA es exclusivo de los planes <b>Pro</b> y <b>Trader Pro</b>. "
          "Mejora tu plan en 💳 Planes para conversar conmigo sobre tus estrategias, métricas y la plataforma.",
}

# limite diário do Free (configurável por env)
def _free_chat_limite():
    try:
        return int(os.environ.get("RADAR_FREE_CHAT_DIA", "8"))
    except Exception:
        return 8

def _periodo_chave():
    # chave diária (reset todo dia, horário UTC)
    import datetime as _dt
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")

def _radar_chat_usados(user_id: str) -> int:
    """Quantas mensagens o Free já usou nesta semana ISO."""
    try:
        sb = _sb_admin()
        if sb is None or not user_id:
            return 0
        sem = _periodo_chave()
        r = (sb.table("radar_chat_uso").select("usados")
             .eq("user_id", user_id).eq("semana", sem).limit(1).execute())
        if r.data:
            return int(r.data[0].get("usados") or 0)
        return 0
    except Exception as e:
        print(f"[radar_chat_usados] {e}")
        return 0

def _radar_chat_inc(user_id: str):
    """Incrementa o contador semanal do Free (upsert)."""
    try:
        sb = _sb_admin()
        if sb is None or not user_id:
            return
        sem = _periodo_chave()
        atual = _radar_chat_usados(user_id)
        sb.table("radar_chat_uso").upsert(
            {"user_id": user_id, "semana": sem, "usados": atual + 1,
             "updated_at": "now()"},
            on_conflict="user_id,semana").execute()
    except Exception as e:
        print(f"[radar_chat_inc] {e}")

def _msg_limite(idioma, limite):
    m = {
        "pt": (f"💬 Você usou suas <b>{limite} conversas grátis de hoje</b> comigo. "
               "No <b>Pro</b> a conversa é <b>ilimitada</b> (+ backtests ilimitados, out-of-sample e exportar NTSL); "
               "no <b>Trader Pro</b> você ainda ganha <b>todos os mercados</b>, a matriz de Estudo e suporte prioritário. "
               "Volte amanhã ou veja as opções em 💳 Planos."),
        "en": (f"💬 You've used your <b>{limite} free chats for today</b> with me. "
               "On <b>Pro</b>, chat is <b>unlimited</b> (+ unlimited backtests, out-of-sample and NTSL export); "
               "on <b>Trader Pro</b> you also get <b>all markets</b>, the Study matrix and priority support. "
               "Come back tomorrow or see the options in 💳 Plans."),
        "es": (f"💬 Usaste tus <b>{limite} conversaciones gratis de hoy</b> conmigo. "
               "En <b>Pro</b> el chat es <b>ilimitado</b> (+ backtests ilimitados, out-of-sample y exportar NTSL); "
               "en <b>Trader Pro</b> además obtienes <b>todos los mercados</b>, la matriz de Estudio y soporte prioritario. "
               "Vuelve mañana o mira las opciones en 💳 Planes."),
    }
    return m.get(idioma, m["pt"])

def _radar_chat_system(idioma: str, plano: str = "free", usados: int = 0, limite: int = 8) -> str:
    nome_idioma = _IDIOMA_NOME.get(idioma, "português brasileiro")
    base = (
        "Você é o Radar, o assistente do BotTested (plataforma de backtesting e validação de estratégias de trading). "
        "Você conversa com o usuário para AJUDÁ-LO a entender e melhorar o uso da plataforma.\n"
        "ESCOPO (responda SOMENTE sobre isto): trading, backtesting, estratégias, gestão de risco, disciplina operacional, "
        "interpretação de métricas (Sharpe, Profit Factor, drawdown, win rate, expectância), automação de bots MT5, "
        "e como usar os recursos do BotTested (Vitrine, Editor, Otimização, Robustez/out-of-sample, Estudo, Calendário, Monitor, Planos). "
        "Se a pergunta for FORA desse escopo (política, conhecimento geral, programação não relacionada a trading, conselhos pessoais, "
        "qualquer outro assunto), recuse com gentileza em uma frase e traga de volta para trading/plataforma. Não responda off-topic.\n"
        "REGRAS INVIOLÁVEIS:\n"
        "(1) NUNCA preveja o mercado nem prometa lucro/retorno futuro. Proibido 'vai lucrar', 'garante', 'com certeza', '100%', "
        "'recomendo comprar/vender'. Você fala de HISTÓRICO MEDIDO, nunca de garantias. Sempre 'histórico medido, não promessa'.\n"
        "(2) Você NÃO dá recomendação financeira personalizada nem sinal de entrada/saída. Você ensina o usuário a avaliar por conta própria.\n"
        "(3) NUNCA mencione nem insinue a existência de qualquer biblioteca/base interna pré-calculada de backtests, nem dados de "
        "outros usuários ou comunidade. Apresente qualquer comparação como 'histórico medido deste ativo' pela plataforma. "
        "Se o usuário pedir para LISTAR/EXPORTAR 'todas as estratégias e números' ou 'tudo o que você tem', RECUSE com gentileza e "
        "redirecione para o ativo/estratégia dele — você só comenta o recorte relevante, jamais despeja a base.\n"
        "(4) SEJA HONESTO: não transforme resultado fraco, amostra pequena ou resultado morno em elogio. Amostra pequena reduz a "
        "confiança estatística — diga isso com clareza. Só elogie o que os números sustentam.\n"
        "(5) Sobre automação: a plataforma executa LOCAL (decisão do usuário); a nuvem só observa, nunca opera por conta própria. "
        "Você não acessa contas reais nem envia ordens.\n"
        "(6) Se o usuário colar código de estratégia, você pode explicar e sugerir melhorias CONCEITUAIS, mas NUNCA invente números de backtest — "
        "oriente o usuário a rodar o teste para ver os números reais.\n"
        "(6b) Você RECEBE a configuração atual (ativo, timeframe, período, stop, take, capital, máx ops, spread, indicador) — use "
        "apenas como CONTEXTO. NÃO proponha mudar stop/take por achismo nem 'só para testar'. O padrão da plataforma (stop 60 / "
        "take 120) é a referência: só fale em mudar stop/take se o usuário PEDIR ou se houver motivo concreto — e, nesse caso, a "
        "plataforma VERIFICA a sugestão rodando backtest real e só mostra o botão se ela superar mesmo o 60/120 (ver regra 10). "
        "Nunca prometa resultado.\n"
        "(6c) Se o usuário escolheu um bot da VITRINE e o resultado ficou ABAIXO da média do card, seja honesto: a média do card é "
        "geral e varia por ativo/período/timeframe; explique os motivos prováveis. Para melhorar, oriente ajustes nos PARÂMETROS DA "
        "PRÓPRIA ESTRATÉGIA (ex.: período da média) ou no ativo/período — NÃO em stop/take (as estratégias prontas nem usam stop/take "
        "fixo). Sempre como teste, nunca promessa de atingir o mesmo número.\n"
        f"(7) ESCREVA INTEIRAMENTE EM: {nome_idioma}. Tom de mentor experiente: claro, direto, honesto, didático; traduza o jargão.\n"
        "(8) SEJA BEM CURTO: no MÁXIMO 2 parágrafos curtos (a janela do chat é estreita). Vá direto ao ponto, corte enrolação e "
        "repetição. Evite abrir muitos tópicos numa resposta só — foque no que importa. Se listar, no máximo 3 itens bem curtos.\n"
        "(8b) FORMATO: HTML simples — <b>negrito</b> e <br>. Use <b> com PARCIMÔNIA: no máximo 2 ou 3 destaques na resposta inteira, "
        "só no que é realmente essencial. NÃO destaque números soltos nem frases inteiras. NUNCA use markdown (**, ##, -, ``` ).\n"
        "(10) SUGESTÃO ESTRUTURADA DE STOP/TAKE (use com PARCIMÔNIA, NÃO em toda resposta): só faz sentido para estratégias que "
        "REAGEM a stop/take (por indicador, ou código custom que usa SL_PTS/TP_PTS). Se — e SOMENTE se — você tiver motivo concreto "
        "para crer que um stop/take específico supera o padrão 60/120 NESTE caso, ACRESCENTE na ÚLTIMA linha, sozinha, a tag "
        "[[SUGESTAO stop=NN take=NN]] (NN em PONTOS, inteiros; inclua SEMPRE os dois valores). A plataforma RODA backtest real e só "
        "mostra o botão 'Aplicar e testar' se a sugestão realmente bater o 60/120 (retorno maior e Profit Factor não pior) — então "
        "não invente: se não bater, o usuário não verá botão nenhum. NÃO comente a tag na prosa (ela some da tela); no MÁXIMO uma por "
        "resposta. Se a estratégia NÃO usa stop/take, ou você não tem motivo concreto, NÃO inclua a tag — oriente em texto outros "
        "ajustes (parâmetros da estratégia, período, ativo)."
    )
    if plano in ("pro", "trader_pro"):
        base += ("\n(9) O usuário é assinante (Pro/Trader Pro). NUNCA mencione upgrade, planos pagos ou venda — ele já paga. "
                 "Apenas ajude com excelência.")
    else:
        # Fatos REAIS dos planos (não invente nada além disto; nunca cite preço — está a definir):
        fatos_planos = (
            "FATOS DOS PLANOS (use só isto, nunca invente recursos nem preços):\n"
            "- PRO (mais popular): backtests ilimitados, conversa ILIMITADA comigo, validação out-of-sample, exportar NTSL, relatório completo.\n"
            "- TRADER PRO: tudo do Pro, MAIS o catálogo COMPLETO de mercados (todos os ativos), a matriz de ESTUDO "
            "(estratégia × timeframe) e suporte prioritário.\n"
            "- Roteie com inteligência: se o usuário quer conversar à vontade, validar robustez ou exportar para NTSL → PRO já resolve. "
            "Se ele quer TODOS os mercados/ativos ou a matriz de Estudo ou suporte prioritário → TRADER PRO. "
            "Na dúvida, mencione os dois e deixe a escolha com ele. NUNCA cite valores (o preço está a definir); aponte 💳 Planos."
        )
        restantes = max(0, limite - usados)
        fase_final = (usados >= (limite - 4))  # ex.: limite 8 -> a partir da 5ª mensagem
        if fase_final:
            base += (
                "\n(9) O usuário está no plano GRATUITO e CHEGANDO AO LIMITE diário de conversas comigo "
                f"(restam cerca de {restantes} hoje). PRIMEIRO ajude a pergunta dele com qualidade. "
                "DEPOIS, ao final, convide-o de forma CLARA, simpática e direta a fazer upgrade — escolhendo entre "
                "<b>Pro</b> ou <b>Trader Pro</b> conforme a necessidade dele (veja os fatos abaixo), destacando que lá a "
                "conversa comigo é ILIMITADA, e apontando 💳 Planos. Seja caloroso e honesto (nada de prometer lucro nem "
                "citar preço); um convite por resposta, sem repetir a mesma frase, fechando como um próximo passo recomendado.\n"
                + fatos_planos)
        else:
            base += (
                "\n(9) O usuário está no plano GRATUITO. Você PODE mencionar UMA única vez, de forma natural e leve, o upgrade "
                "para <b>Pro</b> ou <b>Trader Pro</b> — MAS SOMENTE quando o próprio assunto abrir a deixa (ex.: ele pede "
                "conversa ilimitada, validação out-of-sample aprofundada, exportar NTSL, todos os mercados, ou a matriz de Estudo). "
                "Roteie para o plano certo conforme a necessidade. Nunca seja insistente, nunca repita em toda resposta, nunca "
                "comece vendendo. Se não houver deixa natural, NÃO mencione planos — só ajude.\n" + fatos_planos)
    return base


# ── Verificação de sugestão de stop/take (Radar) ─────────────────────────────
# O Radar só pode propor mudar stop/take quando isso for COMPROVADAMENTE melhor
# que o padrão 60/120 — com base em backtest real, não em achismo.
STOPTAKE_PADRAO = (60, 120)

def _stoptake_tem_efeito(codigo: str) -> bool:
    """stop/take só alteram o backtest se: (a) é estratégia por INDICADOR (engine
    aplica stop/take), ou (b) é código custom que referencia SL_PTS/TP_PTS.
    As estratégias da Vitrine NÃO usam SL_PTS/TP_PTS -> stop/take é inerte nelas."""
    cod = (codigo or "").strip()
    eh_custom = bool(cod) and len(cod) > 10 and not cod.startswith("#")
    if not eh_custom:
        return True  # indicador: engine usa stop/take
    return ("SL_PTS" in cod) or ("TP_PTS" in cod)

def _metricas_stoptake(codigo: str, cfg: dict, sl: float, tp: float):
    """Roda 1 backtest com (sl, tp) na config atual e devolve (retorno, profit_factor).
    Devolve None em qualquer falha (o chamador trata como 'sem prova')."""
    try:
        ativo = (cfg or {}).get("ativo"); periodo = (cfg or {}).get("periodo")
        tf = (cfg or {}).get("timeframe")
        if not ativo or not periodo or not tf:
            return None
        df = baixar_dados(ativo, periodo, tf)
        def _f(v, d):
            try: return float(v)
            except Exception: return d
        params = BacktestCustom(
            ativo=ativo, periodo=periodo, timeframe=tf,
            indicador=(cfg or {}).get("indicador") or "EMA Channel High/Low",
            stop_loss=float(sl), take_profit=float(tp),
            capital=_f((cfg or {}).get("capital"), 10000),
            max_ops=int(_f((cfg or {}).get("max_ops"), 5)),
            comissao=_f((cfg or {}).get("spread"), 0.0002),
            codigo=codigo or "",
        )
        cod = (codigo or "").strip()
        if cod and len(cod) > 10 and not cod.startswith("#"):
            resultado = rodar_codigo_custom(df, params)
        else:
            resultado = rodar_estrategia(df, params)
        m = calcular_metricas_completas(resultado, params, df)
        return (float(m.get("retorno") or 0.0), float(m.get("profit_factor") or 0.0),
                int(m.get("total_trades") or 0))
    except Exception as e:
        print(f"[radar verif stoptake] {e}")
        return None

def _sugestao_stoptake_comprovada(codigo: str, cfg: dict, sl_sug, tp_sug) -> bool:
    """True só se (sl_sug, tp_sug) bater o padrão 60/120 na métrica COMPOSTA:
    retorno MAIOR e Profit Factor NÃO menor. Backtest real dos dois lados."""
    try:
        if sl_sug is None or tp_sug is None:
            return False
        # sem efeito (ex.: Vitrine não usa stop/take) -> nunca comprova
        if not _stoptake_tem_efeito(codigo):
            return False
        # mesmo valor do padrão -> não é mudança
        if abs(float(sl_sug) - STOPTAKE_PADRAO[0]) < 1e-9 and abs(float(tp_sug) - STOPTAKE_PADRAO[1]) < 1e-9:
            return False
        base = _metricas_stoptake(codigo, cfg, STOPTAKE_PADRAO[0], STOPTAKE_PADRAO[1])
        nova = _metricas_stoptake(codigo, cfg, sl_sug, tp_sug)
        if not base or not nova:
            return False
        ret_b, pf_b, _ = base
        ret_n, pf_n, nt_n = nova
        if nt_n < 1:
            return False  # proposta sem operações não prova nada
        # composto: retorno maior E PF não pior (margem mínima p/ evitar empate por ruído)
        return (ret_n > ret_b + 0.01) and (pf_n >= pf_b - 1e-9)
    except Exception as e:
        print(f"[radar verif comprova] {e}")
        return False


def _chat_ctx_biblioteca(ativo, estrategia_id, timeframe=""):
    """Contexto SEGURO para o chat: médias públicas da Vitrine + fatia medida do ativo atual.
    Nunca é a base inteira; apresentado como 'histórico medido', sem revelar a biblioteca."""
    partes = []
    # 1) Médias da Vitrine (já públicas nos cards) — inclusive o bot escolhido
    try:
        vit = estrategias_vitrine().get("estrategias", [])
        if estrategia_id:
            esc = next((e for e in vit if e.get("id") == estrategia_id), None)
            if esc and esc.get("winrate_medio") is not None:
                partes.append(
                    f"Bot que o usuário escolheu na Vitrine: '{esc.get('nome')}' — média histórica MOSTRADA no card: "
                    f"win rate {esc.get('winrate_medio')}%, PF {esc.get('pf_medio')}, Sharpe {esc.get('sharpe_medio')}, "
                    f"retorno {esc.get('retorno_medio')}%. (É média geral; varia por ativo/período.)")
        com = [e for e in vit if e.get("sharpe_medio") is not None]
        com.sort(key=lambda e: (e.get("sharpe_medio") or -999), reverse=True)
        if com:
            top = "; ".join(f"{e.get('nome')} (WR {e.get('winrate_medio')}%, PF {e.get('pf_medio')}, Sharpe {e.get('sharpe_medio')})"
                            for e in com[:3])
            partes.append("Bots fortes na Vitrine (médias históricas gerais): " + top + ".")
    except Exception as e:
        print(f"[chat ctx vitrine] {e}")
    # 2) Fatia MEDIDA do ativo atual (só os melhores; nunca a base toda)
    try:
        sb = _sb_admin()
        if sb is not None and ativo:
            rb = (sb.table("estudo_biblioteca")
                  .select("estrategia_nome,timeframe,periodo,retorno,profit_factor,win_rate,sharpe,trades")
                  .eq("ativo", ativo).gte("trades", 20).order("sharpe", desc=True).limit(6).execute())
            lin = [r for r in (rb.data or []) if r.get("sharpe") is not None]
            if lin:
                itens = "; ".join(
                    f"{r.get('estrategia_nome')} ({r.get('timeframe')},{r.get('periodo')}): "
                    f"retorno {r.get('retorno')}%, PF {r.get('profit_factor')}, WR {r.get('win_rate')}%, "
                    f"Sharpe {r.get('sharpe')}, {r.get('trades')} trades" for r in lin[:5])
                partes.append(f"Histórico MEDIDO neste ativo ({ativo}) — melhores resultados aferidos pela plataforma: {itens}.")
    except Exception as e:
        print(f"[chat ctx ativo] {e}")
    return "\n".join(partes)


def _chat_memoria(user_id, plano):
    """Memória entre sessões. Pro = curta (5 trocas). Trader Pro = completa (12 trocas + evolução)."""
    if not user_id or plano not in ("pro", "trader_pro"):
        return ""
    n = 12 if plano == "trader_pro" else 5
    try:
        sb = _sb_admin()
        if sb is None:
            return ""
        rb = (sb.table("radar_chat_log")
              .select("pergunta,resposta,ativo,resultado,created_at")
              .eq("user_id", user_id).order("created_at", desc=True).limit(n).execute())
        linhas = list(reversed(rb.data or []))   # mais antigas primeiro
        if not linhas:
            return ""
        partes = []
        cap = 160 if plano == "pro" else 220
        for r in linhas:
            p = (r.get("pergunta") or "").strip().replace("\n", " ")[:cap]
            a = (r.get("resposta") or "").strip().replace("\n", " ")[:cap]
            if p:
                partes.append(f"- Usuário: {p}\n  Radar: {a}")
        bloco = "Conversas anteriores deste usuário (memória):\n" + "\n".join(partes)
        # Trader Pro: acrescenta uma mini-evolução dos resultados já vistos
        if plano == "trader_pro":
            evol = []
            for r in linhas:
                res = r.get("resultado") or {}
                if isinstance(res, dict) and (res.get("sharpe") is not None or res.get("retorno") is not None):
                    evol.append(f"{res.get('ativo') or r.get('ativo') or '?'}: Sharpe {res.get('sharpe')}, retorno {res.get('retorno')}%")
            if evol:
                bloco += "\nEvolução de resultados que o usuário já testou (use para comentar progresso): " + "; ".join(evol[-4:]) + "."
        # limite de tamanho
        lim = 1500 if plano == "trader_pro" else 600
        return bloco[:lim]
    except Exception as e:
        print(f"[chat memoria] {e}")
        return ""


def _chat_log_salvar(user_id, plano, idioma, pergunta, resposta, ativo, estrategia_id, resultado, config):
    """Guarda a conversa para análise e memória. Nunca quebra o fluxo se falhar."""
    try:
        sb = _sb_admin()
        if sb is None:
            return
        sb.table("radar_chat_log").insert({
            "user_id": user_id or None,
            "plano": plano,
            "idioma": idioma,
            "pergunta": (pergunta or "")[:4000],
            "resposta": (resposta or "")[:4000],
            "ativo": (ativo or "")[:40] or None,
            "estrategia_id": (estrategia_id or "")[:80] or None,
            "resultado": resultado or None,
            "config": config or None,
        }).execute()
    except Exception as e:
        print(f"[chat log] {e}")


@app.post("/radar/chat")
def radar_chat(req: RadarChatReq):
    idioma = req.idioma if req.idioma in ("pt", "en", "es") else "pt"
    plano = _plano_usuario(req.user_id) if req.user_id else "free"

    # Free entra, mas com cota semanal. Sem user_id (não logado) -> pede login/upgrade.
    eh_free = plano not in ("pro", "trader_pro")
    usados_hoje = 0
    limite = _free_chat_limite()
    if eh_free:
        if not req.user_id:
            return {"ok": False, "bloqueado": True, "resposta": _CHAT_BLOQUEIO.get(idioma, _CHAT_BLOQUEIO["pt"])}
        usados_hoje = _radar_chat_usados(req.user_id)
        if usados_hoje >= limite:
            return {"ok": False, "bloqueado": True, "limite": True,
                    "resposta": _msg_limite(idioma, limite)}

    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return {"ok": False, "resposta": "IA indisponível no momento."}

    msg = (req.mensagem or "").strip()
    if not msg:
        return {"ok": False, "resposta": ""}

    try:
        import httpx, sys
        mensagens = []
        for m in (req.historico or [])[-10:]:
            papel = "assistant" if m.get("role") == "assistant" else "user"
            cont = str(m.get("content", ""))[:2000]
            if cont:
                mensagens.append({"role": papel, "content": cont})
        conteudo = msg[:2000]
        if req.resultado:
            r0 = req.resultado
            def _g(*ks):
                for k in ks:
                    if k in r0 and r0[k] not in (None, ""):
                        return r0[k]
                return None
            partes = []
            for rotulo, chaves in [
                ("ativo", ["ativo", "symbol"]), ("timeframe", ["timeframe", "tf"]),
                ("periodo", ["periodo", "period"]), ("trades", ["trades", "n_trades", "total_trades"]),
                ("win_rate", ["win_rate", "winrate"]), ("profit_factor", ["profit_factor", "pf"]),
                ("sharpe", ["sharpe"]), ("retorno_total", ["retorno", "retorno_total", "return_total"]),
                ("retorno_anual", ["cagr", "retorno_anual"]), ("max_drawdown", ["max_drawdown", "drawdown", "dd"]),
            ]:
                v = _g(*chaves)
                if v is not None:
                    partes.append(f"{rotulo}={v}")
            if partes:
                conteudo += ("\n\n[Resultado do ÚLTIMO backtest que o usuário VÊ na tela agora — "
                             "use estes números reais, não peça que ele os repita]:\n" + "; ".join(partes))
        if req.config:
            cfg = req.config
            sl = str(cfg.get("stop_loss") or "").strip() or "60"
            tp = str(cfg.get("take_profit") or "").strip() or "120"
            linha = (f"ativo={cfg.get('ativo','?')}; timeframe={cfg.get('timeframe','?')}; "
                     f"periodo={cfg.get('periodo','?')}; stop_loss={sl} pts; take_profit={tp} pts; "
                     f"capital={cfg.get('capital','?')}; max_ops={cfg.get('max_ops','?')}; "
                     f"spread_custo={cfg.get('spread','?')}; indicador={cfg.get('indicador','?')}")
            conteudo += ("\n\n[Configuração ATUAL do usuário — use como contexto. Padrão da plataforma: stop 60 / take 120. "
                         "NÃO proponha mudar stop/take por achismo; só com motivo concreto, e a plataforma verifica por backtest]:\n" + linha)
            # Diz à IA se stop/take têm efeito nesta estratégia (req 2/3).
            if not _stoptake_tem_efeito(req.codigo):
                conteudo += ("\n[IMPORTANTE: a estratégia ATUAL NÃO reage a stop/take fixos (ela gere as próprias saídas). "
                             "Mudar stop/take NÃO altera o backtest dela. NÃO sugira mudar stop/take nem emita a tag SUGESTAO; "
                             "se for melhorar, oriente em texto ajustes nos parâmetros da própria estratégia, no período ou no ativo.]")
        if req.codigo:
            conteudo += "\n\n[Código atual da estratégia do usuário, para contexto]:\n" + req.codigo[:3000]
        # contexto seguro: médias da vitrine + fatia medida do ativo atual
        try:
            _ativo = (req.config or {}).get("ativo") or (req.resultado or {}).get("ativo") or ""
            _tf = (req.config or {}).get("timeframe") or ""
            _ctx = _chat_ctx_biblioteca(_ativo, req.estrategia_id, _tf)
            if _ctx:
                conteudo += ("\n\n[DADOS MEDIDOS pela plataforma, para você CONTEXTUALIZAR a resposta. "
                             "Apresente como 'histórico medido'; NUNCA revele que vêm de uma base/biblioteca interna; "
                             "NUNCA liste tudo nem 'despeje' a base — use só o que é relevante à pergunta]:\n" + _ctx)
        except Exception as _e:
            print(f"[chat ctx] {_e}")
        # memória entre sessões (Pro curta / Trader Pro completa)
        try:
            _mem = _chat_memoria(req.user_id, plano)
            if _mem:
                conteudo += ("\n\n[MEMÓRIA do usuário — use para dar continuidade e comentar a evolução dele; "
                             "não repita literalmente, apenas leve em conta]:\n" + _mem)
        except Exception as _e:
            print(f"[chat mem] {_e}")
        mensagens.append({"role": "user", "content": conteudo})

        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
                "max_tokens": 320,
                "temperature": 0.7,
                "system": _radar_chat_system(idioma, plano, usados_hoje, limite),
                "messages": mensagens,
            },
            timeout=20.0,
        )
        if r.status_code != 200:
            print(f"RADAR CHAT status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return {"ok": False, "resposta": "Não consegui responder agora. Tente de novo em instantes."}
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()

        # ── Req 3a: extrai a tag estruturada [[SUGESTAO stop=NN take=NN]] ──
        # O usuário NUNCA vê a tag: ela é removida do texto e os valores voltam
        # estruturados (sugestao_stop / sugestao_take) para o front montar o
        # botão "Aplicar e testar". Robusto: aceita inteiro ou decimal.
        import re as _re
        sugestao_stop = None
        sugestao_take = None
        _m = _re.search(
            r"\[\[\s*SUGESTAO\s+stop\s*=\s*(\d+(?:\.\d+)?)\s+take\s*=\s*(\d+(?:\.\d+)?)\s*\]\]",
            texto, _re.IGNORECASE)
        if _m:
            try:
                _s = float(_m.group(1)); _t = float(_m.group(2))
                # valores plausíveis em pontos; descarta lixo
                if 0 < _s <= 100000 and 0 < _t <= 100000:
                    sugestao_stop = int(_s) if _s == int(_s) else _s
                    sugestao_take = int(_t) if _t == int(_t) else _t
            except Exception:
                sugestao_stop = sugestao_take = None
        # remove QUALQUER tag [[SUGESTAO ...]] do texto visível (mesmo malformada)
        texto = _re.sub(r"\[\[\s*SUGESTAO[^\]]*\]\]", "", texto, flags=_re.IGNORECASE).strip()

        # ── GATE (req 2/3): só mantém a sugestão se for COMPROVADAMENTE melhor que
        # o padrão 60/120 — backtest real dos dois lados, métrica composta
        # (retorno maior E Profit Factor não pior). Senão, descarta: sem botão,
        # o texto da IA segue normal.
        if sugestao_stop is not None and sugestao_take is not None:
            if not _sugestao_stoptake_comprovada(req.codigo, req.config or {}, sugestao_stop, sugestao_take):
                sugestao_stop = sugestao_take = None

        # só conta o uso do Free quando a resposta deu certo
        restantes = None
        if eh_free:
            _radar_chat_inc(req.user_id)
            restantes = max(0, _free_chat_limite() - _radar_chat_usados(req.user_id))

        # guarda a conversa (análise + memória) — todos os planos logados
        _chat_log_salvar(req.user_id, plano, idioma, msg, texto,
                         (req.config or {}).get("ativo") or (req.resultado or {}).get("ativo") or "",
                         req.estrategia_id, req.resultado, req.config)

        out = {"ok": True, "resposta": texto or "…"}
        if restantes is not None:
            out["restantes"] = restantes
        # Req 3a: valores sugeridos para o botão "Aplicar e testar" (se houver)
        if sugestao_stop is not None and sugestao_take is not None:
            out["sugestao_stop"] = sugestao_stop
            out["sugestao_take"] = sugestao_take
        return out
    except Exception as e:
        print(f"RADAR CHAT erro: {e}")
        return {"ok": False, "resposta": "Não consegui responder agora. Tente de novo em instantes."}
