# ============================================================
#  BotTested API — v6.86  (a versão REAL está em API_VERSAO/BUILD_TAG, ~linha 640, e no /versao)
#  Build: 2026-07-19k-learning-placar | Deploy: Railway
#  >>> AO ENTREGAR NOVO api.py: atualizar ESTA linha + API_VERSAO + BUILD_TAG juntos <<<
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
    bot_nome: Optional[str] = None           # nome do BOT (vira o arquivo/EA no MT5)
    bot_token: Optional[str] = None          # token do bot (deriva o magic único por bot)

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


@app.get("/candles")
def candles_preview(ativo: str = "", periodo: str = "2 anos", timeframe: str = "1d"):
    """PRÉVIA (v6.40): velas puras pro gráfico da Overview reagir à barra lateral
    SEM rodar backtest (mudou o ativo/TF/período -> o gráfico já mostra; o teste
    vira ação separada). Reusa baixar_dados (cache em memória + retry do yfinance),
    então trocar de ativo repetidamente não bombardeia o Yahoo. Read-only: não
    grava nada, não gasta cota de teste do plano."""
    if not (ativo or "").strip():
        return {"ok": False, "erro": "sem_ativo", "candles": []}
    try:
        df = baixar_dados(ativo, periodo, timeframe)
    except Exception as e:
        return {"ok": False, "erro": str(e)[:200], "candles": []}
    if df is None or getattr(df, "empty", True):
        return {"ok": False, "erro": "sem_dados", "candles": []}
    out = []
    for ix, row in df.iterrows():
        try:
            t = int(ix.timestamp())
        except Exception:
            try:
                t = int(pd.Timestamp(str(ix)).timestamp())
            except Exception:
                continue
        try:
            out.append({"t": t,
                        "o": round(float(row["Open"]), 4), "h": round(float(row["High"]), 4),
                        "l": round(float(row["Low"]), 4), "c": round(float(row["Close"]), 4)})
        except Exception:
            continue
    return {"ok": True, "candles": out, "ativo": ativo, "timeframe": timeframe, "n": len(out)}

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
_PREFIXOS_API = ("/analise/", "/bot/", "/exportar/", "/babymachine/", "/offmind/", "/radar/", "/conector/", "/admin/", "/usuario/", "/presenca/")

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


API_VERSAO = "6.86 - PLACAR DO APRENDIZADO (Sessao 6C — tela desenhada pelo dono, par da app v9.85): a aba Learning Machine ganha o placar de ACERTOS x ERROS por BOT e por ATIVO + a analise dos erros. ARQUITETURA (deterministica, custo zero de IA): (1) POST /babymachine/estatisticas (user_id, dias, bot_id opcional) le as fechadas do periodo (ate 500) e agrega: geral, por_bot e por_ativo — fechadas, acertos (pts>0; pts==0 conta como acerto de 0 pts = protegeu capital), erros (pts<0), sem_medicao (fechada sem pontos calculaveis — vira aviso na tela; Fix 2 do EA resolve), taxa de acerto sobre as MEDIDAS, pts_ganhos, pts_perdidos, saldo_pts, medias por acerto/erro; (2) _lm_pts prioriza pontos VERDADEIROS (preco_saida - entrada com direcao; o pnl_pts gravado pode ser monetario) e cai pro gravado se faltar dado; (3) _lm_post_mortem — POR QUE ERROU, cruzando contexto_entrada x decisao x resultado em linguagem simples: 'Stop atingido', 'Entrada contra a tendencia do momento', 'Padrao com historico fraco neste ativo (score/100)', 'Poucas confluencias', 'Sinal fraco do detector (N estrelas)', 'O mercado virou logo depois da entrada', 'Analise cruzada DIVERGENTE no momento da entrada'; fallback honesto 'movimento contrario sem aviso previo nos dados registrados'; (4) resposta traz ate 30 erros detalhados: bot/ativo/direcao/cenario/entrada/saida/pnl em pts (negativo) e %/tempo ativo + a ANALISE DE ENTRADA (regime, confirmacao score+veredito, sinal da IA, estrelas/confluencia, explicacao) + motivos. Zero SQL novo (le babymachine_operacoes da v6.76). | 6.85 - FIX DA RAIZ DO ERROR 112 (par da app v9.84): o BT-G01 com resumo_log na tela (BOTTESTED_16) provou que a GERACAO FRESCA tambem saia quebrada — a linha mostrada terminava com aspas abertas ('+ extra + \"'). CAUSA-RAIZ: _BT_VISAO_MQL5 (template injetado com BTvGravarOk/BTLerComando, v6.73) era string Python NAO-RAW — no parse do Python o \\n do FileWriteString colapsava em quebra de linha REAL (error 112: closing quote no MQL5) e os \\\" do BTvJsonNum viravam aspas nuas. Ou seja: TODA geracao pos-v6.73 dessa injecao nascia envenenada; o BOTTESTED_14 compilar foi cache de outra era (conclusao anterior errada, corrigida). FIX: prefixo r no template (r\"\"\") — uso e concatenacao pura (sem format), entao nada mais muda; \\n e \\\" chegam literais no MQL5 como devem. Varredura nos demais templates (_MQL5_AVISO_HEADER, _BT_WRAPPERS_MQL5, _BT_TRADE_CLAMP_MQL5, _BT_PAINEL_MQL5): zero escapes, imunes. Verificado por ast: valor de runtime do template contem \\n de 2 chars e passa na _mq5_sanidade. POS-DEPLOY: reenviar a EMA 9/21 com nome novo — a auto-cura da v6.83 apaga a entrada envenenada de CADA estrategia no proximo envio dela e regenera com o template corrigido (frota inteira se cura sozinha, sem SQL). | 6.84 - SENTINELA v2 (fix do BT-G01 do BOTTESTED_16, par da app v9.83): a sentinela v1 nao conhecia COMENTARIO DE BLOCO /* ... */ — aspas dentro de bloco (cabecalhos que a IA gera) contavam como string aberta e bloqueavam codigo VALIDO, inclusive a geracao fresca pos auto-cura (por isso o BT-G01 na tela). AGORA: (1) _mq5_sanidade v2 rastreia /* */ ATRAVES de linhas (estado em_bloco persistente; aspas e apostrofes dentro de comentario nao contam; */ retoma o scan no meio da linha); mantem tudo da v1: string nao atravessa linha, respeita a barra invertida de escape, // e char literal; (2) TRANSPARENCIA: o retorno BT-G01 do /mt5/enviar agora inclui resumo_log = 'linha N: trecho' da linha que barrou — o modal do front ja renderiza resumo_log, entao o diagnostico aparece NA TELA sem cacar log do Railway; front v9.83 repassa d.resumo_log no handler inicial. Se o BT-G01 voltar a aparecer, a linha mostrada diz na hora se e falso positivo restante ou geracao realmente quebrada. | 6.83 - CODIGOS DE REPROVACAO (BT-xx) + SENTINELA COM AUTO-CURA DO CACHE (par da app v9.82, pedido do dono apos o caso BOTTESTED_15): reprovacao deixa de ser mensagem generica e passa a sair com CODIGO identificavel na hora. CONTEXTO: BOTTESTED_15 (EMA 9/21) reprovou 4x identico — compile.log mostrou error 112 (closing quote) dentro do BTvGravarOk: a entrada da estrategia no mq5_cache estava ENVENENADA (\n colapsado em quebra real, era do bug de escape), e o cache servia a mesma geracao podre em todo reenvio; o template atual esta sao (BOTTESTED_14 gerado fresco compila). AGORA: (1) _mq5_sanidade(texto) — SENTINELA deterministica: varre linha a linha procurando string MQL5 aberta sem fechar (respeita \" escapado, // comentario e char literal '\"'); string nao atravessa linha em MQL5, entao aspas abertas no fim da linha = codigo corrompido; (2) AUTO-CURA no /mt5/enviar: se o .mq5 (novo ou do cache) reprova na sentinela, apaga a entrada do cache via _mq5_cache_apagar(gen_hash) e REGENERA uma vez — usuario final NUNCA precisa de SQL manual; se ainda sair ruim (bug de template), bloqueia ANTES de ir pro MT5 com BT-G01; pre_validado recalculado APOS a cura; (3) _classificar_reprovacao(log) — traduz o log que o conector ja manda no /mt5/veredito em codigo: BT-C01 string/aspas quebrada (error 112, classe do cache envenenado), BT-C02 identificadores MQL4 (Ask/Bid), BT-C03 chaves desbalanceadas/fim inesperado, BT-C04 already defined, BT-C05 cannot convert, BT-C99 compilacao generica, BT-X01 reprovado sem log; primeiro erro decide (o resto e cascata); resumo_log = ate 3 linhas de erro; (4) /mt5/status devolve codigo+resumo_log quando reprovado — o front mostra 'Codigo BT-xx — explicacao direta' + resumo monoespacado; (5) erros do proprio /mt5/enviar tambem codificados: BT-T01 sem token, BT-T02 sem codigo, BT-G02 falha ao gerar, BT-S01 supabase fora, BT-G01 malformado. Zero SQL, EA intocado, Conector intocado (o log ja vinha no veredito). | 6.82 - SCANNER MULTI-TF + ESTADO DO CACADOR (par da app v9.81, pedido do dono): o BOT passa a fazer um PENTE-FINO nos timeframes A PARTIR DO 1M e a narrar o proprio estado de caca. ARQUITETURA (deterministica, custo zero de IA): (1) _scanner_multitf varre 1m/5m/15m/30m/60m/4h (candles do snapshot + zonas + padroes do OffMind por TF) e classifica o comportamento de cada um: tendencia_alta/baixa, inclinando, lateral, reversao_formando (padrao de vela de reversao CONTRA o movimento recente, ou padrao formal do OffMind no TF); TF sem candles e pulado (bots antigos sem c1m comecam a cascata no 5m). (2) _cascata_reversao — o pente-fino de REVERSOES: reversao detectada no menor TF -> 'confirmando' no seguinte (mesmo sinal ou comportamento a favor) -> 'aguardando' no proximo; estados detectada/confirmando/confirmada ate o 15m. (3) _alinhamento_tfs — o pente-fino de TENDENCIAS: 'N de M TFs a favor da baixa (1m, 5m, 15m)'. (4) _estado_gatilho — o BOT narra a propria caca: PROCURANDO GATILHO DE ENTRADA (lista o que esta cacando com precos: fechamento fora da caixa, neckline, reacao em nivel testado) -> GATILHO DE ENTRADA LOCALIZADO (oportunidade recente do detector <15min com entrada/stop/alvo1/estrelas/confluencia, ou rompimento de range/pivo) + CALCULO DE PROBABILIDADE EM PONTOS: alvo provavel (+pts), risco ate a invalidacao (pts), R:R, historico medido (confirmacao contextual). (5) Tudo entra nos fatos do BOT (_bot_narracao_hibrida) com prompt novo (abre com o estado do cacador; cascata e manchete; assinatura do cache ganha estado_gatilho+cascata = re-narra na virada; max_tokens 300->340, ~430 chars) E no campo scanner novo do /monitor/leitura + _anl_ler_leitura -> ctx.momento.scanner da IA do cockpit, com secao SCANNER MULTI-TF no prompt (antecipar padroes em construcao; cascata x alinhamento em conflito E a analise). Numeros medidos, nunca promessa. Zero SQL, zero mq5_cache, EA intocado. | 6.81 - VISAO DO OPERADOR (Sessao C do diferencial de informacao, par da app v9.79): o usuario ganha VOZ dentro da analise cruzada do cockpit. ARQUITETURA: (1) POST /monitor/visao — texto (max 500 chars) e/ou print base64 (max ~5MB); se veio print, UMA chamada de visao Haiku extrai resumo factual do que o operador marcou (~$0.001) e a imagem e DESCARTADA — as analises seguintes usam so o resumo; (2) visao ativa por 2h (TTL) ou ate limpar/substituir (DELETE /monitor/visao), guardada em _VISAO_OP em memoria por worker (mesma classe aceita do _ANL_HIST — interpretacao viva, nao dado regulatorio); (3) injetada em TODA analise cruzada via ctx.visao_operador em _analisar_por_gatilho; prompt da IA ganha secao VISAO DO OPERADOR com regra inegociavel: a IA CRUZA com honestidade — concorda citando numeros quando os dados sustentam, DISCORDA com numeros quando contradizem, nunca obedece cegamente, nunca vira promessa; quando ha visao, o VEREDITO tambem diz ALINHADO/DIVERGENTE com a leitura do operador; (4) enviar visao dispara analise IMEDIATA (mesma prioridade de evento ABRIU/FECHOU — nao espera 90s nem cooldown); (5) /monitor/leitura ganha campo visao_operador por bot (texto, tem_print, resta_min) pro chip do cockpit; (6) DELIMITACAO FIRME: o campo aceita orientacao de LEITURA (vies, niveis a vigiar, contexto, padrao que o usuario enxergou) — NAO executa trade por texto livre; ordem de execucao continua exclusiva dos botoes Copiloto/Automatico com os circuit breakers. Zero SQL, zero mq5_cache, EA intocado. | 6.80 - ESTRUTURA DE SWING (PIVO 1-2-3) + CATALOGO DE PADROES AO VIVO (Sessao B, par da app v9.74): reversao classica entra no radar e no banco. CONTEXTO: BOTTESTED_14 mostrou topo -> fundo -> segundo topo MAIS BAIXO -> perda do fundo (pivo 1-2-3 de baixa, o padrao mais mapeado do trading) 100%% desenhado no grafico — e nem BOT nem IA identificaram, porque o OffMind ao vivo so conhecia 6 padroes de VELA + niveis horizontais; estrutura de SWING nao tinha detector, logo nunca consultava o banco. AGORA: (1) det_pivo_123_baixa/alta REGISTRADOS em PADROES_OFFMIND (categoria estrutura) — com isso a MESMA chave liga tudo automaticamente: _offmind_ao_vivo detecta ao vivo nos TFs de mecanica, /offmind/analisar e _confirm_stats_padrao MEDEM historicamente, e a confirmacao contextual passa a citar 'Pivo 1-2-3 de baixa: medido Nx neste ativo/TF, X%% confirmou'. Deteccao df: swing highs/lows janela 2, 2o extremo mais fraco com margem 0.25xATR, dispara na vela que FECHA alem da neckline, invalida se faz novo extremo alem do 1o. (2) _detectar_estrutura_swing ao vivo nos fatos do BOT: estados FORMANDO (2o topo mais baixo ja feito, neckline segurando) e ROMPEU (fechamento alem da neckline; confirmado com 2 fechamentos), p1/p2, neckline, altura, PROJECAO measured move (neckline -/+ altura), invalidacao no 2o extremo, avanco %% da projecao (>140%% some — virou historia); prompt do BOT ensina a narrar 'segundo topo MAIS BAIXO = compradores perdendo forca' no formando e manchete no rompimento; assinatura do cache re-narra na virada de estado; range tem precedencia quando os dois existem. (3) Detector de oportunidade Caso 0b reversao_estrutura_baixa/alta: entrada no rompimento da neckline, stop de volta pra dentro, ALVO = projecao da estrutura, +15 confluencia. (4) extras do /monitor/leitura ganham swing (estrutura completa) e padroes_catalogo (catalogo INTEIRO do banco) — o front mostra TODOS os padroes disponiveis em tempo real: acesos quando formando (com TF e direcao), 'monitorando' quando nao, estatistica medida anexada quando o banco tem. (5) max_tokens do BOT 250->300 (narracao de range+swing cita mais precos). Zero SQL, zero mq5_cache, EA intocado. | 6.79 - RANGE/LATERALIZACAO + RAIO-X DO COCKPIT (Sessao A do diferencial de informacao, par da app v9.73): o sistema passa a NOMEAR o estado do mercado em vez de so listar pecas. CONTEXTO: BOTTESTED_14 em BTCUSD 15m passou horas numa acumulacao classica (suporte forte x resistencia forte, preco batendo e voltando) e nem BOT nem IA nomearam o estado; quando rompeu pra baixo, nada disparou — existia detector de VELA e de NIVEL, nao existia detector de ESTADO. AGORA: (1) _detectar_range_lateral: detector deterministico de LATERALIZACAO no TF de operacao — dois extremos com 2+ toques cada e >=75% das velas presas entre eles; sai com topo/fundo/altura em pts e em ATRs, velas presas, toques por extremo, posicao %, e PROJECOES de rompimento por measured move (teto+altura / fundo-altura); estados dentro|rompeu_cima|rompeu_baixo (fechamento alem da tolerancia; 'confirmado' com 2 fechamentos fora); range consumido (>140% da projecao) some sozinho. (2) fatos do BOT ganham range_lateral + atr_pts; a assinatura do cache de narracao inclui o estado do range (rompimento re-narra NA HORA); prompt do BOT ensina a ABRIR a leitura nomeando a acumulacao (dentro do range = sem trade; gatilho = fechamento fora; citar fundo/teto/projecoes) e a anunciar ROMPIMENTO como fato principal com invalidacao = voltar pro range. A IA do cockpit (mesmos fatos) herda o range de graca. (3) Detector de oportunidade ganha o Caso 0 rompimento_range_alta/baixa: entrada no preco, stop de volta pro nivel rompido, ALVO1 = projecao da altura (measured move), alvo2 = +50%% da altura; +15 de confluencia 'Rompimento de lateralizacao'. Funciona nos DOIS lados — acumulacao rompe pra onde quiser. (4) RAIO-X DO COCKPIT: /monitor/leitura devolve campo extras por bot via _extras_cockpit — CANAL EMA20 H/L (largura em pts/%%/ATRs, posicao do preco no canal 0-100, distancia pra romper cada lado), ATR do TF em pontos, RANGE completo com projecoes, e ESCADA DE NIVEIS (3 resistencias acima + 3 suportes abaixo com TF, toques e distancia em pts = corredor livre). Tudo deterministico, custo ZERO de IA — a IA so narra por cima de numeros ja calculados. Regra da casa mantida: geometria e historico medidos, nunca promessa. | 6.78 - TREND DAY ADAPTATIVO (v2 TF-aware da Escalonada) + inclui v6.77 (BM dedup): a estrategia Tendencia Diaria Escalonada foi desenhada pra 1d — o BOTTESTED_13 rodando em 5m gerou piramidacao descontrolada. NOVA ESTRATEGIA na Vitrine (tendencia_dia_adaptativa - Trend Day Adaptativo) com regras TF-aware: (1) Trailing adaptativo por TF: M1=0.05%, M5=0.15%, M15=0.35%, M30=0.60%, H1=0.90%, H4=1.20%, D1=1.50%; (2) Cooldown adaptativo por TF: M1=12 barras, M5=6, M15=4, M30=3, H1=2, H4=2, D1=1 — evita piramidacao spam; (3) Espacamento minimo entre entradas: 0.7 x ATR — so piramida se preco realmente avancou; (4) PosicaoFecharTodas() fecha TODAS as posicoes em loop; (5) Trailing coletivo: quando ativa, fecha o pacote INTEIRO; (6) Saida defensiva por 2 velas vermelhas consecutivas; (7) Saida por rompimento canal EMA_L fecha TUDO. Registrada em _mql5_generators + vitrine_catalogo + i18n pt/en/es. v1 continua na Vitrine pra bots existentes. Inclui tambem v6.77: BabyMachine dedup de aberturas por janela de 30s. | 6.76 - BABYMACHINE OPERACOES REAIS (Sessao 6A - coleta pura): a BabyMachine que ate hoje so coletava BACKTESTS ganha novo dominio - OPERACOES REAIS ao vivo do MT5. ARQUITETURA: (1) tabela babymachine_operacoes (SQL v6.76) - irma de backtests_historico, guarda contexto_entrada (JSONB: regime + offmind + momentum_tfs + confirmacao + veredito_ia), decisao (JSONB: direcao + entrada + stop + alvo + cenario + confluencias + explicacao) e resultado (JSONB: preco_saida + pnl + tempo_ativo); (2) 3 fontes alimentam - detector_auto, detector_copiloto, estrategia_compilada; (3) fluxo detector - INSERT pendente + comando_id -> /mt5/comando/confirmar marca aberta + ticket -> /conector/evento tipo=fechado marca fechada (FIFO por bot); (4) fluxo estrategia compilada - /conector/evento tipo=aberto sem pendente cria linha aberta + contexto do ultimo snapshot -> fechado marca fechada; (5) endpoint POST /babymachine/operacoes - filtros e agregados. Base pra aba Learning Machine (Sessao 6B); (6) TTL 90 dias via _bm_operacoes_limpar_antigas() throttle 6h; (7) NON-BLOCKING - falha na coleta nunca quebra detector/comando/evento. Inclui tambem v6.75 (config persistente): coluna config_operacional em conector_bots pra sobreviver Railway restart. ZERO UI - UI vem na Sessao 6B. | 6.74 - DETECTOR AUTOMATICO DE OPORTUNIDADE (Sessao 3 do loop fechado): a inteligencia que construimos passa a produzir sinais executaveis. ARQUITETURA: (1) roda 24/7 no /conector/snapshot (a cada 15s enquanto EA emite) — cockpit fechado nao trava a operacao; (2) detector deterministico: le fatos ja calculados (offmind + regime + momentum + confirmacao) e determina direcao potencial (long/short) por padrao — pullback em tendencia, reversao em nivel testado; (3) niveis reais: entrada, stop, alvos calculados dos niveis S/R clustered do offmind (nao inventa); (4) confluencia 0-100: soma regime alinhado (+20), 4h a favor (+15), padrao formal (+15), toques do nivel (+10/+15), confirmacao historica (+8/+15), momentum recente (+10), veredito alinhado (+10). Traduz em ESTRELAS 1-5; (5) 3 modos por bot (memoria): observar (nada), copiloto (dispara oportunidade pra UI), automatico (cria comando via /mt5/comando); (6) 3 sensibilidades: conservador (>=4 estrelas), moderado (>=3), agressivo (>=2); (7) circuit breakers: pausado, ja tem posicao, cooldown 60s, max operacoes/dia (default 10), drawdown maximo/dia (default 5%); (8) narrador IA (Haiku, ~$0.0005) SO quando oportunidade passa do limiar — barato; ENDPOINTS: GET/POST /monitor/bot/{id}/config, GET /monitor/bot/{id}/oportunidades, POST /monitor/oportunidade/{id}/executar (copiloto). Estado em memoria — Sessao 6 migra pra tabela quando construir dashboard. Fail-safe: se Railway reinicia, todos os bots voltam pra observar. UI de fato vem na Sessao 4. | 6.73 - CANAL DE COMANDO CLOUD->EA (Sessao 1 do loop fechado): a plataforma deixa de ser read-only. ARQUITETURA: (1) tabela mt5_comandos guarda fila de ordens que a cloud manda pro EA (buy/sell/close/close_all/mover_sl/mover_tp/cancelar); (2) POST /mt5/comando cria comando (validacao de bot online, limite 20/dia por bot, retorno com id); (3) GET /mt5/comando/pendente?bot_token=X conector PY faz poll, marca linha como entregue e retorna o mais antigo pendente; (4) POST /mt5/comando/confirmar EA confirma execucao com ticket/preco real ou falha; (5) GET /mt5/comandos?bot_id=X&limite=20 lista pro cockpit mostrar historico. CIRCUIT BREAKERS iniciais: bot deve estar online (ultimo_ping < 45s), max 20 comandos/dia por bot, comandos velhos (>60s pendentes) viram expirado automatico via _mt5_expirar_comandos(). Conector PY ainda nao mexido — contrato documentado, integracao na proxima sessao. EA (MQL5) ganha BTLerComando() injetada que le arquivo bt_cmd_<magic>.txt do conector e executa. ACAO POS-DEPLOY: (1) rodar v6.73_mt5_comandos.sql no Supabase ANTES; (2) invalidar mq5_cache; (3) reenviar bot. | 6.72 - VOLUME NOS CANDLES (preparacao pro grafico com barras de volume no estilo MT5): (1) BTvCandles MQL5 agora inclui tick_volume no fim de cada candle: formato passou de O,H,L,C para O,H,L,C,V. Snapshot cresce ~0.4KB mas continua bem abaixo do limite do Print MQL5 (4KB). (2) _bt_parse_candles e _parse_candles_para_lista ficaram RETROCOMPATIVEIS: aceitam 4 ou 5 valores por candle. Bots velhos (v6.71 e anteriores) continuam funcionando sem volume; bots novos ganham volume automatico. (3) DataFrame do backend ganha coluna Volume quando disponivel; frontend consome via campo v de cada candle. ACAO POS-DEPLOY: invalidar mq5_cache e reenviar 1 bot pra ver volume no grafico do cockpit. Bots antigos continuam com gráfico sem volume ate serem reenviados. | 6.71 - BOT LE OFFMIND (fix arquitetural): a v6.70 do BOT analitico ignorava o offmind ja processado pelo EA (padroes formais engolfo/martelo/estrela cadente/3verdes/3vermelhas + niveis S/R clustered com N toques e marca de testando) e reinventava deteccao mais fraca com swing highs/lows crus de janela 2. AGORA: (1) _analisar_bot_tecnica aceita offmind como parametro; (2) integra padroes_formais e niveis_sendo_testados e niveis_proximos aos fatos passados pra IA; (3) prompt do BOT ensina que niveis com 2+ toques testados AGORA = DUPLO TOPO/FUNDO se formando, e a NARRAR estrutura de mercado antes de swing highs/lows; (4) swing highs/lows antigos permanecem como complemento (nao substitui estrutura formal). Resultado esperado: o BOT vira a citar \"duplo topo se formando em X com 2 toques no 15m\" e \"suporte em Y defendido 3 vezes segurando\". | 6.70 - BOT ANALITICO (Caminho C hibrido): o BOT deixa de ser uma frase-template morta e vira ANALISTA TECNICO real. ARQUITETURA: (1) _analisar_bot_tecnica(candles) DETERMINISTICO — detecta swing highs e swing lows (topos e fundos por janela de 2), padrao da ultima vela (marubozu, doji, martelo, estrela cadente, engolfo de alta/baixa), momentum das ultimas 3 velas, distancia pra romper EMAs, posicao no range das velas visiveis, gatilho concreto de proxima entrada. Nada de opiniao — so o que esta observavel no grafico. (2) _narrar_bot_analitico(fatos) — passa esses fatos pra Haiku formatar em VOZ DE SNIPER (temperatura 0.4, direto, tecnico, sempre com precos concretos). Prompt PROIBE contextualizar com historico ou outros TFs (isso e papel da IA MENTOR no outro quadro). (3) CACHE de 30s por bot_token com assinatura de fatos: se nada relevante mudou, reusa o texto — economiza tokens quando o grafico esta parado. (4) FALLBACK: sem candles ou IA indisponivel cai no _narracao_bot antigo (template morto). Nunca vazio. (5) _bot_narracao_hibrida orquestra tudo, e chamado no lugar de _narracao_bot em /monitor/leitura e _anl_ler_leitura. CUSTO: +1 chamada Haiku por bot ativo por ate 30s = ~$0.001/bot/30s = ~$3/dia por bot rodando 24h. Cache reduz drasticamente quando grafico esta parado. | 6.69 - OFFLINE RAPIDO (fix dos 5 minutos): (1) OFFLINE_APOS_SEGUNDOS caiu de 180s (3 min) para 45s. O EA emite snapshot a cada 15s, entao 45s = 3 ciclos perdidos = com toda certeza offline. Sem essa mudanca, remover EA do MT5 demorava ate 3 min pra card virar offline. (2) BTVisaoDeinit (injetado no OnDeinit do EA) agora EMITE Print(BOTTESTED_FIM|magic=X|motivo=Y) quando o EA e removido do grafico. Serve como sinal explicito de fim de vida — pode ser processado pelo conector PY (se souber) ou fica no log de auditoria. Independente disso, o timeout de 45s ja garante que o bot vira offline rapido. (3) /conector/evento agora aceita tipo=fim: se o conector PY souber processar BOTTESTED_FIM e mandar como evento, o backend zera ultimo_ping IMEDIATAMENTE (bot vira offline em segundos, nem espera os 45s). Cenario tipico: EA removido -> BTVisaoDeinit emite Print BOTTESTED_FIM -> conector PY detecta (se souber) e chama /conector/evento tipo=fim -> backend zera ultimo_ping -> bot offline imediato. Fallback: timeout 45s. | 6.68 - CANDLES REAIS + MOMENTUM SEMANTICO POR TF (par da app v9.56): (1) EA instrumentado agora emite candles OHLC de 5m/15m/60m/4h no snapshot via BTvCandles(tf,18) + CopyRates. Formato compacto O,H,L,C separado por ponto-e-virgula, ate 18 velas por TF. Snapshot cresce ~1.8KB mas Print MQL5 suporta ate 4KB por linha. (2) Backend calcula RESUMO SEMANTICO por TF via _momentum_semantico(candles_str): traduz OHLC crus em texto descritivo — quantas velas de alta/baixa, corpos crescentes/estaveis/encolhendo, posicao do preco no range recente, variacao da ultima vela. Passa isso pra IA como momentum_tfs (nao candles crus — economiza tokens). (3) Prompt IA refinado modo MENTOR HUMANO: reforca linguagem descritiva fluida (o 15m ganhou forca nas ultimas velas mas o 4h ainda esta lateral) em vez de listagem tecnica. (4) Grafico do cockpit volta a mostrar CANDLES REAIS renderizados (canal visual v9.55b continua fallback). ACAO POS-DEPLOY: invalidar mq5_cache e reenviar 1 bot pra testar. | 6.67 - COCKPIT DE ANALISE CRUZADA no Monitor (par da app v9.55): expandir um bot abre o COCKPIT — layout de 3 blocos: (A) LEITURA DO BOT (mecanica, do EA), (B) ANALISE DA IA (contextual + banco absorvido), (C) VEREDITO CONJUNTO (sintese cruzada). Nao e chat de duas vozes conversando; e DOIS PARECERES INDEPENDENTES sobre o mesmo momento e a SINTESE do cruzamento. UMA chamada de IA por rodada devolve JSON com 3 campos: analise_ia, veredito, sinal. Sinal e alinhado|divergente|adicao|neutro — o front pinta a cor. ARQUITETURA: (1) _ANL_HIST em memoria por bot (ate 30 analises); (2) GET /monitor/analise devolve analises novas desde timestamp; (3) POST /monitor/analise/tick decide se analisa: assinatura mudou OU >90s de silencio OU evento ABRIU/FECHOU (imediato, prioridade); respeita cooldown de 30s pra gatilhos de status (evento ignora cooldown). (4) IA ABSORVE o campo confirmacao (banco de padroes medidos v6.48) como conhecimento proprio — narra padroes historicos deste ativo sem citar tabela ou banco. Custo: cockpit fechado = zero. Aberto = ~US 0.001 por analise. | 6.66 - AUDITORIA (par da app v9.52): (1) /conector/evento passa a gravar bot_token e bot_nome DENTRO do detalhe_json do evento em agente_eventos — a partir daqui todo ABRIU/FECHOU no Monitor sai como \"BOTTESTED_10 · ABRIU BUY @ 64020\" em vez de só \"ABRIU @ 64020\" (fim do \"qual bot fez essa operação?\"). (2) /monitor/eventos enriquece cada linha com bot_nome: pega do detalhe_json (eventos novos) ou faz FALLBACK casando por símbolo com os bots do usuário (eventos velhos gravados antes desta versão continuam legíveis). Zero mudança de schema — bot_nome vive dentro do JSONB detalhe_json que já existia. | 6.65 - FONTE ÚNICA DA VERDADE (fim da classe do fantasma de 15/jul): (1) _MQ5_GER_CACHE (camada de memória do cache mq5) MORREU — _mq5_cache_buscar/guardar/aprovar agora falam SÓ com a tabela mq5_cache no Supabase; DELETE FROM mq5_cache mata o cache DE VERDADE, em todos os workers, sem restart (era a memória consultada ANTES do Supabase que manteve a geração envenenada da v6.61 viva o dia inteiro). (2) _MT5_JOBS (dict em memória) MORREU — jobs de validação vivem na tabela NOVA mt5_jobs (criar/pendente/presenca/veredito/status todos via Supabase): elimina o risco multi-worker (job invisível entre workers = F4 do MAPA_PIPELINE) e o job sobrevive a deploy/restart. Limpeza de jobs >1h roda no banco com throttle de 5min. _MT5_POLLS/_VISTO_DB/_MT5_RAISE continuam em memória de propósito (telemetria rápida/throttle; a verdade deles já estava no Supabase). REQUER: rodar o SQL da tabela mt5_jobs ANTES do deploy. | 6.60 - FIX ENUM DO SELO (o último erro de compilação — achado pelo compile.log real do BOTTESTED_05): BTPainelInit usava MQLInfoString(MQL5_PROGRAM_NAME), identificador que não existe no ENUM_MQL_INFO_STRING → error 262 cannot convert enum. Corrigido pra MQL_PROGRAM_NAME. Provavelmente a causa original do 'a injeção quebrava a compilação' da era v6.35. AÇÃO PÓS-DEPLOY: limpar mq5_cache (o envio do BOTTESTED_05 recacheou o selo com o enum errado) e reenviar 1 bot. | 6.59 - FAXINA BRACE-AWARE (fix dos 4x reprovados na compilação): o regex de remoção de função ([^}]*) não atravessa chave aninhada — snapshot da IA com if/FileOpen dentro era cortado no primeiro } e o EA saía com chaves órfãs = não compila; o 1º envio cacheava o .mq5 mutilado e os envios seguintes serviam o mesmo (por isso 4x idêntico). Agora a remoção conta chaves (mesma técnica do bloco OnTimer), protege forward declaration e há sentinela de chaves desbalanceadas no log. AÇÃO PÓS-DEPLOY: invalidar o cache da estratégia (entrada mutilada congelada) e reenviar. | 6.58 - CAUSA-RAIZ FINAL do snapshot mudo: _gerar_mq5_de_codigo (fluxo /mt5/enviar) NUNCA chamava _instrumentar_log_mql5 — comentário da era v6.35 dizia que a injeção quebrava compilação, mas a injeção atual é defensiva e foi validada na v6.56. Por isso v6.55/v6.56 não mudaram nada nesse fluxo (prompt sem snapshot + visão nunca injetada = EA mudo; BOTTESTED_03 provou, EventKillTimer órfão no OnDeinit = faxina nunca rodou). Agora: gera → instrumenta (faxina+SELO+VISÃO) → cacheia neutro instrumentado; HIT sem BTVisaoTick instrumenta e regrava (defesa contra cache legado). | 6.57 - FIX /admin/mq5/invalidar: o handler referenciava _MQ5_CACHE, variável que nunca existiu (o dict real é _MQ5_GER_CACHE, ~linha 8853) — NameError -> 500 em toda invalidação. Corrigido pra _MQ5_GER_CACHE (memória) + delete no Supabase por gen_hash (já certo). | 6.56 - FAXINA DEFENSIVA: v6.55 removeu a INSTRUÇÃO do prompt mas a IA reinventava a função sozinha (ainda saía snapshot mínimo). Agora _instrumentar_log_mql5 REMOVE via regex qualquer função BTEnviarSnapshot/Snapshot/etc inventada pela IA + chamadas + Print direto + EventSetTimer (a instrumentação nossa usa OnTick, não precisa timer). Só BTVisaoTick pode emitir BOTTESTED_SNAPSHOT. Precisa reinvalidar cache e reenviar. | 6.55 - FIX DA RAIZ (loop fechado): o prompt ordenava a IA a definir e chamar uma BTEnviarSnapshot() MÍNIMA (só equity+balance+posicoes+simbolo), que competia com — e vencia — a BTVisaoTick() rica que a instrumentação injeta. Prompt agora PROÍBE a IA de definir/chamar snapshot: a instrumentação faz sozinha em OnInit/OnTick/OnDeinit. EAs regenerados a partir daqui emitem o snapshot RICO. Ação: invalidar caches e reenviar. | 6.54 - INVALIDAR CACHE DO ESPELHO (loop de fechamento — sessão de acabamento): DELETE /admin/mq5/invalidar?estrategia_id=<id>&token=<> remove o .mq5 cacheado (memória + Supabase) de UMA estratégia; próximo envio dela regenera do zero com o PROMPT ATUAL (snapshot rico c/ zonas, regime, offmind, lucro, tfop, canal EMA). Uso: EAs atuais no MT5 emitem esqueleto porque cache é pré-v6.36. Invalidar UMA estratégia + reenviar 1 bot = teste do loop ponta-a-ponta. | 6.53 - FIX SIMBOLO E FLUTUANTE NO MONITOR: (1) o simbolo do card vem do SNAPSHOT (que o EA le do _Symbol do grafico) — nao mais do conector_bots.simbolo (que era o do momento do envio, ex: US30 aparecendo num bot rodando em XAUUSD/BTCUSD); (2) flutuante NULL nao vira mais 0.0 no front (o +0,00 com posicoes>0 era isso); le detalhe.lucro como fallback se o parser antigo nao preencheu a coluna. | 6.52 - PRESENCA EM LOTE (fix de escala do conector). | 6.51 - MONITOR grafico do bot. | 6.50 - DUAS ESTRATEGIAS NOVAS. | 6.49 - MONITOR 2.0. | 6.48 - CONFIRMACAO CONTEXTUAL. | 6.47 - OLHOS DO MONITOR. | 6.46 - VISAO TOTAL. | 6.45 - FIX VITRINE paginacao. | 6.44 - CURADORIA sr_dia_anterior. | 6.43 - VITRINE sem negativo. | 6.42 - ESPELHO POR CODIGO. | 6.41 - VITRINE SEM ACOES. | 6.40 - PREVIA DE VELAS. | 6.39 - CACHE PERSISTENTE. | 6.38 - VALIDACAO RAPIDA. | 6.37 - FIM DE VIDA NO ONDEINIT. | 6.36 - SNAPSHOT EM ARQUIVO. | 6.35 - REVERTE instrumentacao custom. | (historico completo no git)"

BUILD_TAG = "2026-07-19k-learning-placar"

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


def _sb_ler_paginado(montar_query, passo=1000, teto_paginas=20):
    """v6.46 — lê TUDO de uma consulta Supabase paginando com .range(). O
    PostgREST capa em ~1000 linhas por request MESMO com .limit() maior (raiz
    do bug da vitrine, v6.45) — qualquer leitura que possa passar de 1000
    linhas PRECISA vir por aqui. `montar_query(ini, fim)` devolve a query
    pronta; teto de segurança: passo*teto_paginas linhas."""
    tudo = []
    for _p in range(teto_paginas):
        try:
            lote = (montar_query(_p * passo, _p * passo + passo - 1).execute().data or [])
        except Exception:
            break
        tudo.extend(lote)
        if len(lote) < passo:
            break
    return tudo

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
            dados = _sb_ler_paginado(lambda a, b: sb.table("backtests_historico").select("id").eq("user_id", params.user_id).range(a, b))
        elif params.sessao_id:
            dados = _sb_ler_paginado(lambda a, b: sb.table("backtests_historico").select("id").eq("sessao_id", params.sessao_id).range(a, b))
        else:
            return {"total": 0}
        total = len(dados)
        return {"total": total}
    except Exception:
        return {"total": 0}


class BabyMachineOperacoesParams(BaseModel):
    bot_id: Optional[int] = None
    user_id: Optional[str] = None
    dias: Optional[int] = 7
    limite: Optional[int] = 100


@app.post("/babymachine/operacoes")
def babymachine_operacoes(params: BabyMachineOperacoesParams):
    """v6.76 — retorna operacoes reais registradas pela BabyMachine.
    Filtros: bot_id, user_id, ultimos N dias. Ordenacao por ts_criada desc.
    Base pra aba Learning Machine (Sessao 6B)."""
    try:
        sb = _sb_admin()
        if sb is None:
            return {"operacoes": [], "total": 0}
        dias = max(1, min(365, int(params.dias or 7)))
        limite = max(1, min(500, int(params.limite or 100)))
        desde = (_dt.now(_tz.utc) - timedelta(days=dias)).isoformat()
        q = (sb.table("babymachine_operacoes")
             .select("id,bot_id,bot_nome,ativo,timeframe,fonte,status,"
                     "oportunidade_id,comando_id,ticket_mt5,"
                     "contexto_entrada,decisao,resultado,"
                     "ts_criada,ts_entrada,ts_saida")
             .gte("ts_criada", desde)
             .order("ts_criada", desc=True)
             .limit(limite))
        if params.bot_id:
            q = q.eq("bot_id", int(params.bot_id))
        if params.user_id:
            q = q.eq("user_id", params.user_id)
        dados = q.execute().data or []
        total = len(dados)
        return {
            "operacoes": dados,
            "total": total,
            "por_status": {
                "pendente": sum(1 for d in dados if d.get("status") == "pendente"),
                "aberta":   sum(1 for d in dados if d.get("status") == "aberta"),
                "fechada":  sum(1 for d in dados if d.get("status") == "fechada"),
                "orfa":     sum(1 for d in dados if d.get("status") == "orfa"),
            },
        }
    except Exception as e:
        import sys, traceback
        print(f"ERRO BM_OPERACOES: {e}\n{traceback.format_exc()}", file=sys.stderr)
        return {"operacoes": [], "total": 0, "erro": str(e)}


# ════════════════════════════════════════════════════════════════════════════
#  v6.86 — PLACAR DO APRENDIZADO (Sessão 6C — tela desenhada pelo dono)
#
#  Acertos × erros por BOT e por ATIVO, pontos feitos, e nos erros o PORQUÊ
#  + quanto foi de negativo. Tudo determinístico sobre a coleta da BabyMachine.
# ════════════════════════════════════════════════════════════════════════════

def _lm_pts(op):
    """Pontos VERDADEIROS da operação: prioriza preço de saída − entrada com a
    direção (o pnl_pts gravado pode ser monetário, vindo do lucro do EA); cai
    pro gravado quando falta dado. None = fechada sem medição."""
    res = op.get("resultado") or {}
    dec = op.get("decisao") or {}
    try:
        saida = res.get("preco_saida")
        entrada = dec.get("preco_real_entrada") or dec.get("entrada")
        d = str(dec.get("direcao") or "").lower()
        if saida is not None and entrada is not None and d in ("long", "short"):
            delta = float(saida) - float(entrada)
            return round(delta if d == "long" else -delta, 2)
    except Exception:
        pass
    try:
        v = res.get("pnl_pts")
        return round(float(v), 2) if v is not None else None
    except Exception:
        return None


def _lm_post_mortem(op):
    """POR QUE ERROU — classificação determinística cruzando contexto de
    entrada × decisão × resultado. Linguagem simples, custo zero de IA."""
    padrao = "Movimento contrário sem aviso prévio nos dados registrados"
    try:
        dec = op.get("decisao") or {}
        ctx = op.get("contexto_entrada") or {}
        res = op.get("resultado") or {}
        motivos = []
        direcao = str(dec.get("direcao") or "").lower()
        regime = str(ctx.get("regime") or "").upper()
        # 1) saiu no stop (saída a <=20% do caminho entrada->stop)
        try:
            stop = float(dec.get("stop"))
            saida = float(res.get("preco_saida"))
            entrada = float(dec.get("preco_real_entrada") or dec.get("entrada"))
            dist = abs(entrada - stop)
            if dist > 0 and abs(saida - stop) <= dist * 0.2:
                motivos.append("Stop atingido — o mercado andou contra até o limite de proteção")
        except Exception:
            pass
        # 2) contra a tendência maior do momento
        if ("ALTA" in regime and direcao == "short") or ("BAIXA" in regime and direcao == "long"):
            motivos.append("Entrada contra a tendência do momento (" + regime.title() + ")")
        # 3) histórico medido fraco
        try:
            sc = float(ctx.get("confirmacao_score"))
            if sc < 45:
                motivos.append(f"Padrão com histórico fraco neste ativo ({int(sc)}/100 medido)")
        except Exception:
            pass
        # 4) poucas confluências / estrelas baixas na hora
        try:
            confl = dec.get("confluencia")
            if confl is None:
                confl = dec.get("score_confluencia")
            if confl is not None and float(confl) < 45:
                motivos.append(f"Poucas confluências a favor na entrada ({int(float(confl))}/100)")
        except Exception:
            pass
        try:
            est = dec.get("estrelas")
            if est is not None and int(est) <= 2:
                motivos.append(f"Sinal fraco do detector ({int(est)} estrela(s))")
        except Exception:
            pass
        # 5) reversão imediata
        try:
            t = int(res.get("tempo_ativo_seg"))
            if 0 <= t < 180:
                motivos.append("O mercado virou logo depois da entrada (menos de 3 minutos)")
        except Exception:
            pass
        # 6) análise cruzada divergente na hora da entrada
        via = ctx.get("veredito_ia") or {}
        if str(via.get("sinal") or "").lower() == "divergente":
            motivos.append("Análise cruzada (BOT × IA) estava DIVERGENTE no momento da entrada")
        return (motivos or [padrao])[:4]
    except Exception:
        return [padrao]


class LMEstatisticasParams(BaseModel):
    user_id: str = ""
    dias: int = 30
    bot_id: Optional[int] = None


@app.post("/babymachine/estatisticas")
def babymachine_estatisticas(params: LMEstatisticasParams):
    """v6.86 — placar: acertos × erros por bot e por ativo + análise dos erros."""
    try:
        sb = _sb_admin()
        if sb is None:
            return {"ok": False, "geral": None}
        dias = max(1, min(365, int(params.dias or 30)))
        desde = (_dt.now(_tz.utc) - timedelta(days=dias)).isoformat()
        q = (sb.table("babymachine_operacoes")
             .select("id,bot_id,bot_nome,ativo,timeframe,fonte,status,"
                     "contexto_entrada,decisao,resultado,ts_entrada,ts_saida")
             .eq("status", "fechada")
             .gte("ts_criada", desde)
             .order("ts_saida", desc=True)
             .limit(500))
        if params.user_id:
            q = q.eq("user_id", params.user_id)
        if params.bot_id:
            q = q.eq("bot_id", int(params.bot_id))
        ops = q.execute().data or []

        def _novo():
            return {"fechadas": 0, "acertos": 0, "erros": 0, "sem_medicao": 0,
                    "pts_ganhos": 0.0, "pts_perdidos": 0.0}

        geral = _novo()
        por_bot, por_ativo, erros = {}, {}, []
        for op in ops:
            pts = _lm_pts(op)
            grupos = [geral,
                      por_bot.setdefault(op.get("bot_nome") or f"bot {op.get('bot_id')}", _novo()),
                      por_ativo.setdefault(op.get("ativo") or "?", _novo())]
            for g in grupos:
                g["fechadas"] += 1
                if pts is None:
                    g["sem_medicao"] += 1
                elif pts >= 0:
                    g["acertos"] += 1
                    g["pts_ganhos"] += pts
                else:
                    g["erros"] += 1
                    g["pts_perdidos"] += -pts
            if pts is not None and pts < 0 and len(erros) < 30:
                dec = op.get("decisao") or {}
                ctx = op.get("contexto_entrada") or {}
                res = op.get("resultado") or {}
                via = ctx.get("veredito_ia") or {}
                erros.append({
                    "bot_nome":       op.get("bot_nome"),
                    "ativo":          op.get("ativo"),
                    "timeframe":      op.get("timeframe"),
                    "direcao":        dec.get("direcao"),
                    "cenario":        dec.get("cenario"),
                    "entrada":        dec.get("preco_real_entrada") or dec.get("entrada"),
                    "preco_saida":    res.get("preco_saida"),
                    "pnl_pts":        pts,
                    "pnl_pct":        res.get("pnl_pct"),
                    "tempo_ativo_seg": res.get("tempo_ativo_seg"),
                    "ts_saida":       op.get("ts_saida"),
                    "motivos":        _lm_post_mortem(op),
                    "analise": {
                        "regime":               ctx.get("regime"),
                        "confirmacao_score":    ctx.get("confirmacao_score"),
                        "confirmacao_veredito": ctx.get("confirmacao_veredito"),
                        "sinal_ia":             via.get("sinal"),
                        "veredito_ia":          via.get("veredito"),
                        "estrelas":             dec.get("estrelas"),
                        "confluencia":          dec.get("confluencia") or dec.get("score_confluencia"),
                        "explicacao":           dec.get("explicacao"),
                    },
                })

        def _fin(g):
            medidas = g["acertos"] + g["erros"]
            g["taxa_acerto"] = round(g["acertos"] / medidas * 100, 1) if medidas else None
            g["saldo_pts"] = round(g["pts_ganhos"] - g["pts_perdidos"], 2)
            g["media_acerto_pts"] = round(g["pts_ganhos"] / g["acertos"], 2) if g["acertos"] else None
            g["media_erro_pts"] = round(g["pts_perdidos"] / g["erros"], 2) if g["erros"] else None
            g["pts_ganhos"] = round(g["pts_ganhos"], 2)
            g["pts_perdidos"] = round(g["pts_perdidos"], 2)
            return g

        _fin(geral)
        lista_bot = sorted(
            [dict(nome=k, **_fin(v)) for k, v in por_bot.items()],
            key=lambda x: -x["fechadas"])
        lista_ativo = sorted(
            [dict(nome=k, **_fin(v)) for k, v in por_ativo.items()],
            key=lambda x: -x["fechadas"])
        return {"ok": True, "dias": dias, "geral": geral,
                "por_bot": lista_bot, "por_ativo": lista_ativo, "erros": erros}
    except Exception as e:
        import sys, traceback
        print(f"ERRO BM_ESTATISTICAS: {e}\n{traceback.format_exc()}", file=sys.stderr)
        return {"ok": False, "geral": None, "erro": str(e)}


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
            linhas = _sb_ler_paginado(lambda a, b: sb.table("backtests_historico").select(
                "ativo,timeframe,stop_loss,take_profit,retorno,win_rate,sharpe,profit_factor,max_drawdown,total_trades,sessao_id,user_id"
            ).range(a, b))
        except Exception:
            # fallback: campos podem estar dentro de 'parametros'
            linhas = _sb_ler_paginado(lambda a, b: sb.table("backtests_historico").select("*").range(a, b))

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

def _swings_df(df, janela=2):
    """v6.80 — índices de swing highs/lows num DataFrame OHLC (janela simétrica)."""
    h = df["High"].values; l = df["Low"].values
    tops, bots = [], []
    for i in range(janela, len(df) - janela):
        if all(h[i] >= h[j] for j in range(i - janela, i + janela + 1) if j != i):
            tops.append(i)
        if all(l[i] <= l[j] for j in range(i - janela, i + janela + 1) if j != i):
            bots.append(i)
    return tops, bots

def det_pivo_123_baixa(df):
    """v6.80 — PIVÔ 1-2-3 DE BAIXA (topo duplo descendente): topo -> fundo
    (neckline) -> topo MAIS BAIXO (margem 0.25×ATR) -> vela FECHA abaixo da
    neckline. Marca a vela do rompimento. Invalida se faz novo topo acima do 1º.
    A estrutura de reversão mais mapeada do trading — agora medível no banco."""
    tops, bots = _swings_df(df, 2)
    if len(tops) < 2 or not bots:
        return []
    h = df["High"].values; l = df["Low"].values; c = df["Close"].values
    atr = calcular_atr(df)
    out = []
    for k in range(1, len(tops)):
        t1, t2 = tops[k - 1], tops[k]
        if t2 - t1 < 2:
            continue
        a = float(atr.iloc[t2]) if atr.iloc[t2] == atr.iloc[t2] else 0.0
        marg = max(a * 0.25, float(h[t1]) * 0.0005)
        if h[t2] >= h[t1] - marg:
            continue
        entre = [b for b in bots if t1 < b < t2]
        if not entre:
            continue
        neck = min(float(l[b]) for b in entre)
        for i in range(t2 + 1, min(t2 + 13, len(df))):
            if float(c[i]) < neck:
                out.append((i, "baixa")); break
            if float(h[i]) > float(h[t1]):
                break
    return out

def det_pivo_123_alta(df):
    """v6.80 — PIVÔ 1-2-3 DE ALTA (fundo duplo ascendente): espelho do de baixa."""
    tops, bots = _swings_df(df, 2)
    if len(bots) < 2 or not tops:
        return []
    h = df["High"].values; l = df["Low"].values; c = df["Close"].values
    atr = calcular_atr(df)
    out = []
    for k in range(1, len(bots)):
        f1, f2 = bots[k - 1], bots[k]
        if f2 - f1 < 2:
            continue
        a = float(atr.iloc[f2]) if atr.iloc[f2] == atr.iloc[f2] else 0.0
        marg = max(a * 0.25, float(l[f1]) * 0.0005)
        if l[f2] <= l[f1] + marg:
            continue
        entre = [t for t in tops if f1 < t < f2]
        if not entre:
            continue
        neck = max(float(h[t]) for t in entre)
        for i in range(f2 + 1, min(f2 + 13, len(df))):
            if float(c[i]) > neck:
                out.append((i, "alta")); break
            if float(l[i]) < float(l[f1]):
                break
    return out

PADROES_OFFMIND = {
    "engolfo_alta":    {"fn": det_engolfo_alta,    "nome": "Engolfo de alta",        "categoria": "candle"},
    "engolfo_baixa":   {"fn": det_engolfo_baixa,   "nome": "Engolfo de baixa",       "categoria": "candle"},
    "martelo":         {"fn": det_martelo,         "nome": "Martelo (pin bar alta)", "categoria": "candle"},
    "estrela_cadente": {"fn": det_estrela_cadente, "nome": "Estrela cadente (pin bar baixa)", "categoria": "candle"},
    "tres_verdes":     {"fn": det_tres_verdes,     "nome": "3 velas verdes",         "categoria": "candle"},
    "tres_vermelhas":  {"fn": det_tres_vermelhas,  "nome": "3 velas vermelhas",      "categoria": "candle"},
    # v6.80 — ESTRUTURA DE SWING: registrar aqui liga o padrão ao banco inteiro
    # (medição histórica + detecção ao vivo + confirmação contextual), tudo
    # pela mesma chave. Lição do BOTTESTED_14: padrão sem detector nunca
    # consulta o banco.
    "pivo_123_baixa":  {"fn": det_pivo_123_baixa,  "nome": "Pivô 1-2-3 de baixa (topo duplo descendente)", "categoria": "estrutura"},
    "pivo_123_alta":   {"fn": det_pivo_123_alta,   "nome": "Pivô 1-2-3 de alta (fundo duplo ascendente)",  "categoria": "estrutura"},
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
    """Cabeçalho + includes + inputs comuns + handle de trade + funções de log
    que o BotTested Conector lê (read-only) pra reportar pra nuvem."""
    alvo = f"  // testado em: {ativo}" if ativo else ""
    return f"""{_MQL5_AVISO_HEADER}
#property copyright "BotTested"
#property link      "https://bottested.com"
#property version   "1.00"
#property description "{nome} — gerado pelo BotTested. BASE FUNCIONAL: teste em conta demo."

#include <Trade/Trade.mqh>
CTrade trade;
{alvo}

//--- Log pro BotTested Conector (read-only, só Print no log do MT5) ---
// O conector lê estas linhas e reporta pra nuvem. Não envia nada sozinho.
void BTEvento(string tipo, string extra="")
{{
   PrintFormat("BOTTESTED_EVENTO|%s|tipo=%s|simbolo=%s|%s",
               tipo, tipo, _Symbol, extra);
}}
void BTSnapshot()
{{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double bal= AccountInfoDouble(ACCOUNT_BALANCE);
   double ml = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   int    np = PositionSelect(_Symbol) ? 1 : 0;
   double lf = np ? PositionGetDouble(POSITION_PROFIT) : 0.0;
   PrintFormat("BOTTESTED_SNAPSHOT|equity=%.2f|balance=%.2f|margem_livre=%.2f|posicoes=%d|lucro=%.2f|simbolo=%s",
               eq, bal, ml, np, lf, _Symbol);
}}
//__BT_INJECT_WRAPPERS__
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


# ── Trend Day Adaptativo (v2 TF-aware da Escalonada) ────────────────────
def _mql5_tendencia_dia_adaptativa(p) -> str:
    """v6.78 — evolucao da Tendencia Diaria Escalonada: TF-aware, controle
    de piramidacao por ATR + cooldown, trailing coletivo (fecha o pacote
    inteiro), saida defensiva por 2 velas vermelhas. Roda em 5m/15m/30m/1h/4h/1d
    ajustando parametros automaticamente."""
    n = int(getattr(p, "ema_period", 20) or 20)
    s = _mql5_preamble("Trend Day Adaptativo", getattr(p, "ativo", ""))
    s += _mql5_risk_inputs(getattr(p, "stop_loss", 50), getattr(p, "take_profit", 100))
    s += f"""input int     InpEMAPeriod       = {n};      // Periodo EMA (canal)
input int     InpMaxPiramide     = 3;       // Maximo de entradas empilhadas
input int     InpATRPeriodo      = 14;      // Periodo do ATR (espacamento)
input double  InpEspacamentoATR  = 0.7;     // Espacamento minimo entre entradas (x ATR)
input int     InpCooldownBarras  = 0;       // 0 = automatico por TF (recomendado)
input double  InpTrailPctManual  = 0.0;     // 0 = automatico por TF (recomendado)
input bool    InpSaidaVelasVerm  = true;    // Sair se 2 velas vermelhas em posicao

int hEmaHigh, hEmaLow, hATR;
double g_topo = 0;
datetime g_ultimaEntradaBarra = 0;
double g_precoUltimaEntrada = 0;

// Trailing adaptativo por TF (% do preco)
double _btTrailPctPorTF()
{{
   ENUM_TIMEFRAMES tf = _Period;
   if(tf == PERIOD_M1)  return 0.05;
   if(tf == PERIOD_M5)  return 0.15;
   if(tf == PERIOD_M15) return 0.35;
   if(tf == PERIOD_M30) return 0.60;
   if(tf == PERIOD_H1)  return 0.90;
   if(tf == PERIOD_H4)  return 1.20;
   if(tf == PERIOD_D1)  return 1.50;
   return 1.00;
}}

// Cooldown adaptativo por TF (barras minimas entre entradas)
int _btCooldownBarrasPorTF()
{{
   ENUM_TIMEFRAMES tf = _Period;
   if(tf == PERIOD_M1)  return 12;
   if(tf == PERIOD_M5)  return 6;
   if(tf == PERIOD_M15) return 4;
   if(tf == PERIOD_M30) return 3;
   if(tf == PERIOD_H1)  return 2;
   if(tf == PERIOD_H4)  return 2;
   if(tf == PERIOD_D1)  return 1;
   return 3;
}}

int OnInit()
{{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   hEmaHigh = iMA(_Symbol,_Period,InpEMAPeriod,0,MODE_EMA,PRICE_HIGH);
   hEmaLow  = iMA(_Symbol,_Period,InpEMAPeriod,0,MODE_EMA,PRICE_LOW);
   hATR     = iATR(_Symbol,_Period,InpATRPeriodo);
   if(hEmaHigh==INVALID_HANDLE||hEmaLow==INVALID_HANDLE||hATR==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}}
void OnDeinit(const int r)
{{
   IndicatorRelease(hEmaHigh); IndicatorRelease(hEmaLow); IndicatorRelease(hATR);
}}

datetime g_lastBar=0;
bool NovaBarra() {{ datetime t=iTime(_Symbol,_Period,0); if(t!=g_lastBar){{g_lastBar=t;return true;}} return false; }}

int PosicoesAbertas()
{{
   int n=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol && PositionGetInteger(POSITION_MAGIC)==(long)InpMagic) n++;
   return n;
}}

void PosicaoFecharTodas()
{{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {{
      if(PositionGetSymbol(i)!=_Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=(long)InpMagic) continue;
      trade.PositionClose(PositionGetInteger(POSITION_TICKET));
   }}
}}

double UltATR()
{{
   double a[];
   if(CopyBuffer(hATR,0,1,1,a)<1) return 0;
   return a[0];
}}

bool DuasBarrasVermelhas()
{{
   double c1=iClose(_Symbol,_Period,1), o1=iOpen(_Symbol,_Period,1);
   double c2=iClose(_Symbol,_Period,2), o2=iOpen(_Symbol,_Period,2);
   return (c1<o1 && c2<o2);
}}

void OnTick()
{{
   if(!NovaBarra()) return;
   double eh[],el[];
   if(CopyBuffer(hEmaHigh,0,1,1,eh)<1) return;
   if(CopyBuffer(hEmaLow,0,1,1,el)<1) return;
   double preco=iClose(_Symbol,_Period,1);
   bool alta=preco>eh[0], baixa=preco<el[0];
   double atr=UltATR();
   double espacamento = atr * InpEspacamentoATR;

   // TRAILING COLETIVO — fecha o pacote inteiro se ativar
   if(PosicoesAbertas()>0)
   {{
      g_topo = MathMax(g_topo>0?g_topo:preco, preco);
      double trailPct = (InpTrailPctManual>0) ? InpTrailPctManual : _btTrailPctPorTF();
      if(preco < g_topo*(1.0 - trailPct/100.0))
      {{
         PosicaoFecharTodas();
         g_topo=0; g_ultimaEntradaBarra=0; g_precoUltimaEntrada=0;
         return;
      }}
   }}

   // SAIDA DEFENSIVA — 2 velas vermelhas antecipam quebra
   if(InpSaidaVelasVerm && PosicoesAbertas()>0 && DuasBarrasVermelhas())
   {{
      PosicaoFecharTodas();
      g_topo=0; g_ultimaEntradaBarra=0; g_precoUltimaEntrada=0;
      return;
   }}

   // ENTRA/PIRAMIDA A FAVOR
   if(alta && PosicoesAbertas() < InpMaxPiramide)
   {{
      // Cooldown por barras
      if(g_ultimaEntradaBarra > 0)
      {{
         int cd = (InpCooldownBarras>0) ? InpCooldownBarras : _btCooldownBarrasPorTF();
         datetime agora = iTime(_Symbol,_Period,0);
         int barrasDesde = (int)((agora - g_ultimaEntradaBarra) / PeriodSeconds(_Period));
         if(barrasDesde < cd) return;
      }}
      // Espacamento minimo em preco (tendencia avancou?)
      if(g_precoUltimaEntrada > 0 && atr > 0)
      {{
         if((preco - g_precoUltimaEntrada) < espacamento) return;
      }}
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), ponto = _Point;
      double sl = ask - InpStopLoss*ponto, tp = ask + InpTakeProfit*ponto;
      if(trade.Buy(InpLote,_Symbol,ask,sl,tp,"Trend Day v2"))
      {{
         g_ultimaEntradaBarra = iTime(_Symbol,_Period,0);
         g_precoUltimaEntrada = ask;
      }}
   }}
   // SAIDA POR ROMPIMENTO DO CANAL — fecha TUDO
   else if(baixa && PosicoesAbertas()>0)
   {{
      PosicaoFecharTodas();
      g_topo=0; g_ultimaEntradaBarra=0; g_precoUltimaEntrada=0;
   }}
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
    "tendencia_dia_adaptativa": _mql5_tendencia_dia_adaptativa,
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


# Wrappers MQL5 injetados nos EAs nativos: logam o evento, ajustam SL/TP pro
# nível mínimo de stops/freeze do ativo (evita "invalid stops" no BTC e cia.)
# e só então enviam a ordem. Injetado no marcador //__BT_INJECT_WRAPPERS__,
# DEPOIS do replace trade.Buy/Sell -> BTBuy/BTSell (por isso o trade.Buy/Sell
# aqui dentro não é tocado pelo replace).
_BT_WRAPPERS_MQL5 = """//--- BotTested: ajuste de stops + wrappers de entrada (injetado) ------
// Respeita o nivel minimo de stops/freeze do ativo e o lado da ordem,
// evitando "invalid stops" (distancia em pontos pequena demais p/ o ativo,
// ex.: BTCUSD). Normaliza os precos pelas casas decimais do simbolo.
void BTAjustaStops(bool ehCompra, double preco, double &sl, double &tp)
{
   double pt  = _Point;
   long   lvl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long   frz = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double bidp = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double askp = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double spread = (askp > bidp) ? (askp - bidp) : (10 * pt);
   // distancia minima = MAIOR entre o stops/freeze level e 3x o spread. Ativos como
   // BTCUSD/indices reportam stops_level=0 mas REJEITAM stop dentro do spread -> o
   // piso pelo spread resolve o "invalid stops". Vale pra qualquer ativo.
   double dNivel  = (double)((lvl > frz ? lvl : frz) + 10) * pt;
   double dSpread = spread * 3.0;
   double distMin = (dNivel > dSpread) ? dNivel : dSpread;
   if(ehCompra)
   {
      if(sl > 0.0 && preco - sl < distMin) sl = preco - distMin;
      if(tp > 0.0 && tp - preco < distMin) tp = preco + distMin;
   }
   else
   {
      if(sl > 0.0 && sl - preco < distMin) sl = preco + distMin;
      if(tp > 0.0 && preco - tp < distMin) tp = preco - distMin;
   }
   if(sl > 0.0) sl = NormalizeDouble(sl, _Digits);
   if(tp > 0.0) tp = NormalizeDouble(tp, _Digits);
}
bool BTBuy(double lote, string sym, double preco, double sl, double tp, string com="")
{
   BTEvento("aberto", "lado=BUY");
   BTAjustaStops(true, preco, sl, tp);
   return trade.Buy(lote, sym, preco, sl, tp, com);
}
bool BTSell(double lote, string sym, double preco, double sl, double tp, string com="")
{
   BTEvento("aberto", "lado=SELL");
   BTAjustaStops(false, preco, sl, tp);
   return trade.Sell(lote, sym, preco, sl, tp, com);
}
//----------------------------------------------------------------------"""


# CLAMP DE STOPS PARA EA DA IA: os EAs gerados pela IA declaram "CTrade trade;".
# Substituimos por uma SUBCLASSE que ajusta SL/TP pro nivel minimo de stops do
# ativo (ex.: BTCUSD, onde 60*_Point vira $0,60 e a corretora rejeita) ANTES de
# enviar. Como e chamada direta em objeto concreto (BTTrade trade;), trade.Buy/
# trade.Sell passam pela versao com clamp — vale pra QUALQUER codigo da IA, sem
# depender do formato do .mq5. Nao depende de BTEvento (loga o open por Print).
# Se algum EA nao usar exatamente "CTrade trade;", nada e injetado (degrada seguro).
_BT_TRADE_CLAMP_MQL5 = """//--- BotTested: CTrade com clamp de stops (evita "invalid stops") ------
void BTAjustaStops(bool ehCompra, double preco, double &sl, double &tp)
{
   double pt  = _Point;
   long   lvl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long   frz = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double bidp = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double askp = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double spread = (askp > bidp) ? (askp - bidp) : (10 * pt);
   // distancia minima = MAIOR entre o stops/freeze level e 3x o spread. Ativos como
   // BTCUSD/indices reportam stops_level=0 mas REJEITAM stop dentro do spread -> o
   // piso pelo spread resolve o "invalid stops". Vale pra qualquer ativo.
   double dNivel  = (double)((lvl > frz ? lvl : frz) + 10) * pt;
   double dSpread = spread * 3.0;
   double distMin = (dNivel > dSpread) ? dNivel : dSpread;
   if(ehCompra)
   {
      if(sl > 0.0 && preco - sl < distMin) sl = preco - distMin;
      if(tp > 0.0 && tp - preco < distMin) tp = preco + distMin;
   }
   else
   {
      if(sl > 0.0 && sl - preco < distMin) sl = preco + distMin;
      if(tp > 0.0 && preco - tp < distMin) tp = preco - distMin;
   }
   if(sl > 0.0) sl = NormalizeDouble(sl, _Digits);
   if(tp > 0.0) tp = NormalizeDouble(tp, _Digits);
}
class BTTrade : public CTrade
{
public:
   bool Buy(double volume, const string symbol=NULL, double price=0.0, double sl=0.0, double tp=0.0, const string comment="")
   {
      double p = (price > 0.0) ? price : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      BTAjustaStops(true, p, sl, tp);
      Print("BOTTESTED_EVENTO|aberto|tipo=aberto|simbolo=", _Symbol, "|lado=BUY");
      return CTrade::Buy(volume, symbol, price, sl, tp, comment);
   }
   bool Sell(double volume, const string symbol=NULL, double price=0.0, double sl=0.0, double tp=0.0, const string comment="")
   {
      double p = (price > 0.0) ? price : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      BTAjustaStops(false, p, sl, tp);
      Print("BOTTESTED_EVENTO|aberto|tipo=aberto|simbolo=", _Symbol, "|lado=SELL");
      return CTrade::Sell(volume, symbol, price, sl, tp, comment);
   }
   // A IA às vezes abre via PositionOpen (não via Buy/Sell) — cobre esse caminho.
   bool PositionOpen(const string symbol, ENUM_ORDER_TYPE order_type, double volume, double price, double sl, double tp, const string comment="")
   {
      bool ehCompra = (order_type==ORDER_TYPE_BUY || order_type==ORDER_TYPE_BUY_LIMIT || order_type==ORDER_TYPE_BUY_STOP);
      double p = (price > 0.0) ? price : (ehCompra ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID));
      BTAjustaStops(ehCompra, p, sl, tp);
      Print("BOTTESTED_EVENTO|aberto|tipo=aberto|simbolo=", _Symbol, "|lado=", (ehCompra ? "BUY" : "SELL"));
      return CTrade::PositionOpen(symbol, order_type, volume, price, sl, tp, comment);
   }
   // À PROVA DE BALA: TODA ordem do CTrade chamada direto no objeto passa por aqui
   // (Buy/Sell/PositionOpen chamam OrderSend internamente na base; e a IA que monta
   // o request na mão e chama trade.OrderSend(...) tambem cai aqui). Clampa o SL/TP
   // do request antes de enviar — pega qualquer caminho que a IA use.
   bool OrderSend(const MqlTradeRequest &request, MqlTradeResult &result)
   {
      MqlTradeRequest req = request;
      bool ehCompra = (req.type==ORDER_TYPE_BUY || req.type==ORDER_TYPE_BUY_LIMIT || req.type==ORDER_TYPE_BUY_STOP);
      double p = req.price;
      if(p <= 0.0) p = ehCompra ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID);
      BTAjustaStops(ehCompra, p, req.sl, req.tp);
      return CTrade::OrderSend(req, result);
   }
};
#define CTrade BTTrade
//----------------------------------------------------------------------"""


# Selo BotTested: painel de identidade on-chart, injetado ANTES do OnInit em
# TODO bot gerado (conversor testado E IA). Sem include — só objetos de gráfico,
# então compila em qualquer EA. Reposicionado abaixo do rótulo do símbolo (some
# a colisão do Comment()). Robô Fab vermelho = marca; status muda de cor com o
# estado (verde=lucro/compra, vermelho=prejuízo/venda, âmbar=aguardando).
# A estratégia pode setar g_btEstado/g_btEstadoCor pra um status rico; senão o
# selo infere sozinho pela posição/lucro.
_BT_PAINEL_MQL5 = """//----------------------------------------------------------------------
//  SELO BOTTESTED — painel de identidade on-chart (injetado, sem include)
//  Robo vermelho (Fab) + marca + dados vivos + status colorido por estado.
//----------------------------------------------------------------------
#define BT_PFX     "BTselo_"
#define BT_CORNER  CORNER_LEFT_UPPER
#define BT_X       8
#define BT_Y       22
#define BT_W       214
#define BTC_CARD   C'13,21,32'
#define BTC_BORDA  C'30,42,58'
#define BTC_TXT    C'232,236,241'
#define BTC_MUTE   C'138,150,166'
#define BTC_VERDE  C'0,208,132'
#define BTC_VERM   C'229,72,77'
#define BTC_AMBAR  C'255,184,48'
#define BTC_OLHO   C'142,230,255'
string g_btEstado    = "";
int    g_btEstadoCor = 0;   // 0=auto 1=verde 2=vermelho 3=ambar
void BTrect(string id,int x,int y,int w,int h,color bg,color brd)
{
   string n=BT_PFX+id;
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,BT_CORNER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,BT_X+x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,BT_Y+y);
   ObjectSetInteger(0,n,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,n,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,n,OBJPROP_BGCOLOR,bg);
   ObjectSetInteger(0,n,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,n,OBJPROP_COLOR,brd);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
}
void BTtxt(string id,int x,int y,string txt,color clr,int sz,int anchor,string font)
{
   string n=BT_PFX+id;
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,BT_CORNER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,BT_X+x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,BT_Y+y);
   ObjectSetInteger(0,n,OBJPROP_ANCHOR,anchor);
   ObjectSetString (0,n,OBJPROP_FONT,font);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,sz);
   ObjectSetInteger(0,n,OBJPROP_COLOR,clr);
   ObjectSetString (0,n,OBJPROP_TEXT,txt);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
}
int BTposSimb()
{
   int c=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol) c++;
   return c;
}
double BTlucroSimb()
{
   double L=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol) L+=PositionGetDouble(POSITION_PROFIT);
   return L;
}
int BTladoSimb()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol)
         return (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)?1:-1;
   return 0;
}
void BTPainelInit()
{
   BTrect("card",0,0,BT_W,152,BTC_CARD,BTC_BORDA);
   BTrect("accent",0,0,4,152,BTC_AMBAR,BTC_AMBAR);
   BTrect("r_dot", 16,0,5,4, BTC_VERDE,BTC_VERDE);
   BTrect("r_ant", 18,3,2,5, BTC_MUTE, BTC_MUTE);
   BTrect("r_head",12,8,16,13,BTC_VERM, BTC_VERM);
   BTrect("r_eye1",16,12,3,3, BTC_OLHO, BTC_OLHO);
   BTrect("r_eye2",22,12,3,3, BTC_OLHO, BTC_OLHO);
   BTtxt("brand",  36,6, "BotTested", BTC_VERDE,10,ANCHOR_LEFT_UPPER,"Segoe UI Semibold");
   string nome = MQLInfoString(MQL_PROGRAM_NAME);
   if(StringLen(nome)>24) nome=StringSubstr(nome,0,24);
   BTtxt("botname",36,22,nome, BTC_MUTE,7,ANCHOR_LEFT_UPPER,"Segoe UI");
   BTrect("div1",8,37,BT_W-16,1,BTC_BORDA,BTC_BORDA);
   BTtxt("c_preco",12,45,"Preco",    BTC_MUTE,8,ANCHOR_LEFT_UPPER,"Segoe UI");
   BTtxt("c_pos",  12,61,"Posicoes", BTC_MUTE,8,ANCHOR_LEFT_UPPER,"Segoe UI");
   BTtxt("c_saldo",12,77,"Saldo",    BTC_MUTE,8,ANCHOR_LEFT_UPPER,"Segoe UI");
   BTtxt("c_lucro",12,93,"Lucro",    BTC_MUTE,8,ANCHOR_LEFT_UPPER,"Segoe UI");
   BTrect("div2",8,113,BT_W-16,1,BTC_BORDA,BTC_BORDA);
   BTPainelTick();
}
void BTPainelTick()
{
   double preco = SymbolInfoDouble(_Symbol,SYMBOL_BID);
   int    dig   = (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   int    pos   = BTposSimb();
   double saldo = AccountInfoDouble(ACCOUNT_BALANCE);
   double lucro = BTlucroSimb();
   int    lado  = BTladoSimb();
   string moeda = AccountInfoString(ACCOUNT_CURRENCY);
   BTtxt("v_preco",BT_W-10,45,DoubleToString(preco,dig),BTC_TXT,8,ANCHOR_RIGHT_UPPER,"Segoe UI");
   BTtxt("v_pos",  BT_W-10,61,IntegerToString(pos),      BTC_TXT,8,ANCHOR_RIGHT_UPPER,"Segoe UI");
   BTtxt("v_saldo",BT_W-10,77,DoubleToString(saldo,2)+" "+moeda,BTC_TXT,8,ANCHOR_RIGHT_UPPER,"Segoe UI");
   color  clu = (lucro>0?BTC_VERDE:(lucro<0?BTC_VERM:BTC_TXT));
   string slu = (lucro>=0?"+":"")+DoubleToString(lucro,2)+" "+moeda;
   BTtxt("v_lucro",BT_W-10,93,slu,clu,8,ANCHOR_RIGHT_UPPER,"Segoe UI");
   string est; color cor;
   if(g_btEstado!="")
   {
      est=g_btEstado;
      cor = (g_btEstadoCor==1?BTC_VERDE:
             g_btEstadoCor==2?BTC_VERM:
             g_btEstadoCor==3?BTC_AMBAR:
             (lucro>0?BTC_VERDE:(lucro<0?BTC_VERM:BTC_AMBAR)));
   }
   else if(pos==0){ est="AGUARDANDO ENTRADA"; cor=BTC_AMBAR; }
   else
   {
      string ld=(lado>0?"COMPRADO":"VENDIDO");
      est=ld+"  "+(lucro>=0?"+":"")+DoubleToString(lucro,0);
      cor=(lucro>=0?BTC_VERDE:BTC_VERM);
   }
   BTtxt("status",12,121,est,cor,10,ANCHOR_LEFT_UPPER,"Segoe UI Semibold");
   ObjectSetInteger(0,BT_PFX+"accent",OBJPROP_BGCOLOR,cor);
   ObjectSetInteger(0,BT_PFX+"accent",OBJPROP_COLOR,cor);
   ChartRedraw(0);
}
void BTPainelDeinit()
{
   ObjectsDeleteAll(0,BT_PFX);
   ChartRedraw(0);
}
//----------------------------------------------------------------------
"""


# VISÃO multi-timeframe: o "olho" do bot. Computa a posição do preço vivo no
# canal EMA20 High/Low em CADA timeframe (atuação 5m/15m/60m/4h/D + virada
# 1m/5m/15m) e emite a linha BOTTESTED_SNAPSHOT enriquecida por TEMPO (~15s),
# não por barra — o que conserta o D1 ficar offline. Reporta o CRU (acima/
# dentro/abaixo); a síntese de regime (tendencia/lateral/virada) fica na nuvem
# (ler_direcao). Só objetos/handles próprios (prefixo hV), sem tocar na
# estratégia — compila em qualquer EA. Preenche dd/conta/corretora (colunas que
# já existiam vazias) e ativa as regras F1/F3 do agente de brinde.
_BT_VISAO_MQL5 = r"""//----------------------------------------------------------------------
//  VISAO BOTTESTED — snapshot multi-timeframe enriquecido (injetado)
//  Emite BOTTESTED_SNAPSHOT por TEMPO com zonas cruas por TF + detalhe.
//----------------------------------------------------------------------
#define BT_VISAO_SEG 15          // intervalo de emissao (segundos)
#define BT_VEMA_PER  20          // periodo do canal EMA High/Low
int hVH1,hVL1, hVH5,hVL5, hVH15,hVL15, hVH60,hVL60, hVH240,hVL240, hVHD,hVLD;
int hVHc,hVLc, hVATR;
datetime g_btVisaoUlt = 0;
double   g_btPicoEq   = 0;
string BTvD(double v){ return DoubleToString(v,_Digits); }
string BTvCandles(ENUM_TIMEFRAMES tf, int qtd)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int cop = CopyRates(_Symbol, tf, 0, qtd, rates);
   if(cop < 1) return "";
   string out = "";
   for(int i = cop - 1; i >= 0; i--)
   {
      if(i < cop - 1) out += ";";
      // v6.72 — inclui tick_volume no fim de cada candle: O,H,L,C,V
      out += BTvD(rates[i].open) + "," + BTvD(rates[i].high) + "," + BTvD(rates[i].low) + "," + BTvD(rates[i].close) + "," + IntegerToString((long)rates[i].tick_volume);
   }
   return out;
}
string BTvTF(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "1m";
      case PERIOD_M5:  return "5m";
      case PERIOD_M15: return "15m";
      case PERIOD_M30: return "30m";
      case PERIOD_H1:  return "60m";
      case PERIOD_H4:  return "4h";
      case PERIOD_D1:  return "D";
      default:         return EnumToString(tf);
   }
}
string BTvZona(int hH,int hL)
{
   double eh[],el[];
   if(CopyBuffer(hH,0,0,1,eh)<1) return "?";
   if(CopyBuffer(hL,0,0,1,el)<1) return "?";
   double p = SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(p > eh[0]) return "acima";
   if(p < el[0]) return "abaixo";
   return "dentro";
}
double BTvValor(int h)
{
   double b[];
   if(CopyBuffer(h,0,0,1,b)<1) return 0.0;
   return b[0];
}
int BTvPosSimb()
{
   int c=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol) c++;
   return c;
}
double BTvLucroSimb()
{
   double L=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetSymbol(i)==_Symbol) L+=PositionGetDouble(POSITION_PROFIT);
   return L;
}
double BTvDD()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_btPicoEq) g_btPicoEq = eq;
   if(g_btPicoEq <= 0) return 0.0;
   return (g_btPicoEq - eq)/g_btPicoEq*100.0;
}
void BTVisaoInit()
{
   g_btPicoEq = AccountInfoDouble(ACCOUNT_EQUITY);
   hVH1  =iMA(_Symbol,PERIOD_M1, BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH); hVL1  =iMA(_Symbol,PERIOD_M1, BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVH5  =iMA(_Symbol,PERIOD_M5, BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH); hVL5  =iMA(_Symbol,PERIOD_M5, BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVH15 =iMA(_Symbol,PERIOD_M15,BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH); hVL15 =iMA(_Symbol,PERIOD_M15,BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVH60 =iMA(_Symbol,PERIOD_H1, BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH); hVL60 =iMA(_Symbol,PERIOD_H1, BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVH240=iMA(_Symbol,PERIOD_H4, BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH); hVL240=iMA(_Symbol,PERIOD_H4, BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVHD  =iMA(_Symbol,PERIOD_D1, BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH); hVLD  =iMA(_Symbol,PERIOD_D1, BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVHc =iMA(_Symbol,_Period,BT_VEMA_PER,0,MODE_EMA,PRICE_HIGH);
   hVLc =iMA(_Symbol,_Period,BT_VEMA_PER,0,MODE_EMA,PRICE_LOW);
   hVATR=iATR(_Symbol,_Period,14);
}
void BTVisaoDeinit(const int reason=-1)
{
   // v6.69 — SINAL DE FIM DE VIDA: emite BOTTESTED_FIM no log quando o EA
   // é removido do gráfico. Serve pro conector PY detectar imediatamente
   // (se souber ler; senão, o timeout de 45s no backend cobre).
   string motivo = "desconhecido";
   if(reason==REASON_REMOVE)     motivo = "removido";
   else if(reason==REASON_CHARTCLOSE) motivo = "grafico_fechado";
   else if(reason==REASON_PROGRAM)    motivo = "encerrado";
   else if(reason==REASON_ACCOUNT)    motivo = "conta_trocada";
   else if(reason==REASON_TEMPLATE)   motivo = "template";
   else if(reason==REASON_PARAMETERS) motivo = "parametros";
   else if(reason==REASON_RECOMPILE)  motivo = "recompilado";
   Print("BOTTESTED_FIM|magic=", IntegerToString((long)InpMagic), "|motivo=", motivo);
   int hs[15]={hVH1,hVL1,hVH5,hVL5,hVH15,hVL15,hVH60,hVL60,hVH240,hVL240,hVHD,hVLD,hVHc,hVLc,hVATR};
   for(int i=0;i<15;i++) if(hs[i]!=INVALID_HANDLE) IndicatorRelease(hs[i]);
}
// v6.73 — CANAL DE COMANDO cloud->EA (Sessao 1 do loop fechado).
// Le arquivo bt_cmd_<magic>.txt escrito pelo conector PY, executa a ordem,
// grava bt_ok_<magic>.txt com resultado. Idempotencia via g_btLastCmdId.
// Formato do arquivo bt_cmd:   id|tipo|params_json
//   Ex.: 1234|buy|{"lote":0.01,"sl":64200,"tp":64800}
//        5678|close_all|{}
long g_btLastCmdId = 0;   // idempotencia entre OnTicks
string BTvJsonNum(const string js, const string chave)
{
   // extrator MINIMO de "chave":numero do JSON simples do conector.
   // NAO e parser completo — o conector garante formato limpo.
   int p = StringFind(js, "\""+chave+"\"");
   if(p < 0) return "";
   int c = StringFind(js, ":", p);
   if(c < 0) return "";
   int i = c + 1;
   while(i < StringLen(js) && (StringGetCharacter(js,i)==' ' || StringGetCharacter(js,i)=='"')) i++;
   int j = i;
   while(j < StringLen(js))
   {
      ushort ch = StringGetCharacter(js,j);
      if(ch==',' || ch=='}' || ch=='"' || ch==' ') break;
      j++;
   }
   return StringSubstr(js, i, j-i);
}
void BTvGravarOk(long cmd_id, bool sucesso, const string extra)
{
   string arq = "bt_ok_" + IntegerToString((long)InpMagic) + ".txt";
   int h = FileOpen(arq, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, IntegerToString(cmd_id) + "|" + (sucesso?"ok":"erro") + "|" + extra + "\n");
   FileClose(h);
}
void BTLerComando()
{
   string arq = "bt_cmd_" + IntegerToString((long)InpMagic) + ".txt";
   if(!FileIsExist(arq)) return;
   int h = FileOpen(arq, FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE) return;
   string linha = FileReadString(h);
   FileClose(h);
   FileDelete(arq);  // consome o comando — evita reprocessar
   if(StringLen(linha) < 3) return;
   // parse: id|tipo|params
   string parts[];
   int n = StringSplit(linha, '|', parts);
   if(n < 2) return;
   long cmd_id = (long)StringToInteger(parts[0]);
   if(cmd_id <= 0 || cmd_id == g_btLastCmdId) return;   // idempotencia
   g_btLastCmdId = cmd_id;
   string tipo = parts[1];
   string params = (n >= 3 ? parts[2] : "");
   Print("BOTTESTED_CMD|id=", IntegerToString(cmd_id), "|tipo=", tipo);
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.symbol = _Symbol;
   req.magic  = InpMagic;
   req.deviation = 20;
   bool ok = false; string extra = "";
   if(tipo == "buy" || tipo == "sell")
   {
      double lote = StringToDouble(BTvJsonNum(params, "lote"));
      if(lote <= 0) lote = 0.01;
      double sl_v = StringToDouble(BTvJsonNum(params, "sl"));
      double tp_v = StringToDouble(BTvJsonNum(params, "tp"));
      req.action = TRADE_ACTION_DEAL;
      req.type   = (tipo=="buy" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
      req.volume = lote;
      req.price  = (tipo=="buy" ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID));
      req.type_filling = ORDER_FILLING_IOC;
      if(sl_v > 0) req.sl = sl_v;
      if(tp_v > 0) req.tp = tp_v;
      ok = OrderSend(req, res);
      extra = "ticket=" + IntegerToString((long)res.order) + ";preco=" + DoubleToString(res.price, _Digits) + ";retcode=" + IntegerToString(res.retcode);
   }
   else if(tipo == "close_all")
   {
      int fechados = 0;
      for(int i = PositionsTotal()-1; i >= 0; i--)
      {
         if(PositionGetSymbol(i) != _Symbol) continue;
         MqlTradeRequest r2; MqlTradeResult rs2;
         ZeroMemory(r2); ZeroMemory(rs2);
         r2.action = TRADE_ACTION_DEAL;
         r2.symbol = _Symbol;
         r2.magic  = InpMagic;
         r2.deviation = 20;
         r2.position = PositionGetInteger(POSITION_TICKET);
         r2.volume = PositionGetDouble(POSITION_VOLUME);
         long ptype = PositionGetInteger(POSITION_TYPE);
         r2.type = (ptype==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
         r2.price = (ptype==POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol,SYMBOL_BID) : SymbolInfoDouble(_Symbol,SYMBOL_ASK));
         r2.type_filling = ORDER_FILLING_IOC;
         if(OrderSend(r2, rs2)) fechados++;
      }
      ok = (fechados > 0);
      extra = "fechados=" + IntegerToString(fechados);
   }
   else if(tipo == "close")
   {
      long ticket = (long)StringToInteger(BTvJsonNum(params, "ticket"));
      if(ticket > 0 && PositionSelectByTicket(ticket))
      {
         req.action = TRADE_ACTION_DEAL;
         req.position = ticket;
         req.volume = PositionGetDouble(POSITION_VOLUME);
         long ptype = PositionGetInteger(POSITION_TYPE);
         req.type = (ptype==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
         req.price = (ptype==POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol,SYMBOL_BID) : SymbolInfoDouble(_Symbol,SYMBOL_ASK));
         req.type_filling = ORDER_FILLING_IOC;
         ok = OrderSend(req, res);
         extra = "ticket=" + IntegerToString(ticket) + ";retcode=" + IntegerToString(res.retcode);
      }
      else extra = "posicao nao encontrada";
   }
   else if(tipo == "mover_sl" || tipo == "mover_tp")
   {
      long ticket = (long)StringToInteger(BTvJsonNum(params, "ticket"));
      double novo = StringToDouble(BTvJsonNum(params, (tipo=="mover_sl"?"sl":"tp")));
      if(ticket > 0 && novo > 0 && PositionSelectByTicket(ticket))
      {
         req.action = TRADE_ACTION_SLTP;
         req.position = ticket;
         req.sl = (tipo=="mover_sl" ? novo : PositionGetDouble(POSITION_SL));
         req.tp = (tipo=="mover_tp" ? novo : PositionGetDouble(POSITION_TP));
         ok = OrderSend(req, res);
         extra = "retcode=" + IntegerToString(res.retcode);
      }
      else extra = "posicao nao encontrada ou valor invalido";
   }
   else
   {
      extra = "tipo desconhecido: " + tipo;
   }
   BTvGravarOk(cmd_id, ok, extra);
   Print("BOTTESTED_CMD_OK|id=", IntegerToString(cmd_id), "|sucesso=", (ok?"1":"0"), "|", extra);
}
void BTVisaoTick()
{
   if(TimeCurrent() - g_btVisaoUlt < BT_VISAO_SEG) return;
   g_btVisaoUlt = TimeCurrent();
   string z1  = BTvZona(hVH1,hVL1);
   string z5  = BTvZona(hVH5,hVL5);
   string z15 = BTvZona(hVH15,hVL15);
   string z60 = BTvZona(hVH60,hVL60);
   string z240= BTvZona(hVH240,hVL240);
   string zD  = BTvZona(hVHD,hVLD);
   double preco = SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double emaHc = BTvValor(hVHc);
   double emaLc = BTvValor(hVLc);
   double atr   = BTvValor(hVATR);
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double ml  = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   string conta = IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
   string corretora = AccountInfoString(ACCOUNT_COMPANY);
   StringReplace(corretora,"|","/");
   double dd  = BTvDD();
   int    pos = BTvPosSimb();
   double lucro = BTvLucroSimb();
   string lado="flat"; double entrada=0,tp=0,sl=0,lote=0; long idade=0;
   if(PositionSelect(_Symbol))
   {
      long t = PositionGetInteger(POSITION_TYPE);
      lado    = (t==POSITION_TYPE_BUY)?"buy":"sell";
      entrada = PositionGetDouble(POSITION_PRICE_OPEN);
      tp      = PositionGetDouble(POSITION_TP);
      sl      = PositionGetDouble(POSITION_SL);
      lote    = PositionGetDouble(POSITION_VOLUME);
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      idade   = (long)((TimeCurrent()-ot)/60);
   }
   // v6.68 — candles OHLC dos 4 TFs (5m/15m/60m/4h), 18 velas cada
   string c5m  = BTvCandles(PERIOD_M5,  18);
   string c15m = BTvCandles(PERIOD_M15, 18);
   string c60m = BTvCandles(PERIOD_H1,  18);
   string c4h  = BTvCandles(PERIOD_H4,  18);
   string linha = StringFormat(
      "BOTTESTED_SNAPSHOT|equity=%.2f|balance=%.2f|margem_livre=%.2f|posicoes=%d|lucro=%.2f|simbolo=%s"
      "|dd=%.2f|conta=%s|corretora=%s|tfop=%s|preco=%s|emaH=%s|emaL=%s|atr=%s"
      "|z1=%s|z5=%s|z15=%s|z60=%s|z240=%s|zD=%s"
      "|lado=%s|entrada=%s|tp=%s|sl=%s|lote=%.2f|idade=%d"
      "|c5m=%s|c15m=%s|c60m=%s|c4h=%s",
      eq,bal,ml,pos,lucro,_Symbol,
      dd,conta,corretora,BTvTF(_Period),BTvD(preco),BTvD(emaHc),BTvD(emaLc),BTvD(atr),
      z1,z5,z15,z60,z240,zD,
      lado,BTvD(entrada),BTvD(tp),BTvD(sl),lote,(int)idade,
      c5m,c15m,c60m,c4h);
   Print(linha);
}
//----------------------------------------------------------------------
"""


def _instrumentar_log_mql5(codigo: str) -> str:
    """Insere no EA gerado, sem reescrever cada conversor: (a) evento em cada
    ordem, (b) o SELO de identidade on-chart e (c) a VISÃO multi-timeframe, que
    emite o snapshot enriquecido por TEMPO (~15s, não por barra). Nos EAs nativos
    (com preâmbulo) ajusta SL/TP pro stops level via wrappers BTBuy/BTSell; nos
    EAs da IA, via subclasse BTTrade (clamp de stops). A visão SUBSTITUI o antigo
    BTSnapshot por-barra — mais rico e sem o bug do D1 offline."""
    import re as _re

    # ── v6.55b — FAXINA DEFENSIVA (o prompt não é o suficiente) ────────────
    # A IA às vezes inventa uma função própria de snapshot mesmo o prompt não
    # pedindo. Se isso acontecer, ela ganha do BTVisaoTick (roda antes) e o
    # snapshot rico não aparece. Aqui removemos qualquer função "BTEnviarSnapshot",
    # "EnviarSnapshot", "BotTestedSnapshot" (variantes que a IA já inventou) do
    # EA gerado, junto com todas as chamadas e o EventSetTimer(N); (que ativa
    # o timer com essa função). Também mata qualquer Print direto de linha
    # "BOTTESTED_SNAPSHOT|" — só BTVisaoTick (injetada abaixo) pode emitir.
    # v6.59 — REMOÇÃO COM CONTAGEM DE CHAVES. O regex antigo ([^}]*) não
    # atravessa chave aninhada: função de snapshot com if/FileOpen dentro era
    # cortada no PRIMEIRO } e o EA ficava com chaves órfãs → NÃO COMPILAVA.
    # Foi a causa dos "4x não aprovado": o 1º envio cacheava o .mq5 mutilado
    # e os seguintes serviam o mesmo arquivo. Mesma técnica brace-aware que o
    # bloco do OnTimer (abaixo) já usava — agora pra toda função removida.
    def _bt_remover_funcao(cod, assinatura, exigir=""):
        pos = 0
        while True:
            m = _re.search(assinatura, cod[pos:])
            if not m:
                return cod
            ini = pos + m.start()
            fim_assin = pos + m.end()
            i = cod.find("{", fim_assin)
            # só remove DEFINIÇÃO: entre a assinatura e a { só pode haver
            # espaço/quebra (protege forward declaration "void X();")
            if i < 0 or cod[fim_assin:i].strip():
                pos = fim_assin
                continue
            depth, j = 0, i
            while j < len(cod):
                if cod[j] == '{':
                    depth += 1
                elif cod[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth != 0:
                return cod          # fonte já quebrado: não piora
            corpo = cod[i:j+1]
            if exigir and exigir not in corpo:
                pos = j + 1         # não é a função-alvo: segue adiante
                continue
            cod = cod[:ini] + cod[j+1:]
            pos = ini               # pode existir outra igual adiante
    codigo = _bt_remover_funcao(codigo, r"void\s+(?:BT)?EnviarSnapshot\s*\([^)]*\)")
    codigo = _bt_remover_funcao(codigo, r"void\s+BotTestedSnapshot\s*\([^)]*\)")
    codigo = _bt_remover_funcao(codigo, r"void\s+Snapshot\s*\([^)]*\)", exigir="BOTTESTED_SNAPSHOT")
    # remove CHAMADAS a essas funções (vira linha vazia — não quebra sintaxe)
    codigo = _re.sub(r"[ \t]*(?:BT)?EnviarSnapshot\s*\(\s*\)\s*;", "", codigo)
    codigo = _re.sub(r"[ \t]*BotTestedSnapshot\s*\(\s*\)\s*;", "", codigo)
    # mata Print direto de BOTTESTED_SNAPSHOT (linha inteira, se a IA fez inline)
    codigo = _re.sub(r"[ \t]*Print(?:Format)?\s*\([^;]*BOTTESTED_SNAPSHOT[^;]*\)\s*;", "", codigo)
    # remove EventSetTimer da IA — a instrumentação usa OnTick, não precisa timer
    codigo = _re.sub(r"[ \t]*EventSetTimer\s*\(\s*\d+\s*\)\s*;", "", codigo)
    codigo = _re.sub(r"[ \t]*EventKillTimer\s*\(\s*\)\s*;", "", codigo)
    # remove função OnTimer inteira que a IA tenha criado só pra emitir snapshot
    # (se ela contiver BOTTESTED, é do velho snapshot; se não, deixa)
    _m = _re.search(r"void\s+OnTimer\s*\([^)]*\)\s*\{", codigo)
    if _m:
        # acha o } que fecha e vê se tinha BOTTESTED
        i = _m.end() - 1
        depth = 0
        j = i
        while j < len(codigo):
            if codigo[j] == '{': depth += 1
            elif codigo[j] == '}':
                depth -= 1
                if depth == 0:
                    corpo = codigo[i:j+1]
                    if "BOTTESTED" in corpo:
                        codigo = codigo[:_m.start()] + codigo[j+1:]
                    break
            j += 1
    if "//__BT_INJECT_WRAPPERS__" in codigo:
        # EA NATIVO: BTEvento existe (preâmbulo). Close loga evento; entradas viram
        # wrappers (logam + ajustam stops); injeta as definições no marcador.
        codigo = codigo.replace("trade.PositionClose(_Symbol);",
                                "BTEvento(\"fechado\",\"\"); trade.PositionClose(_Symbol);")
        codigo = codigo.replace("trade.Buy(",  "BTBuy(")
        codigo = codigo.replace("trade.Sell(", "BTSell(")
        codigo = codigo.replace("//__BT_INJECT_WRAPPERS__", _BT_WRAPPERS_MQL5, 1)
    else:
        # EA da IA: injeta o bloco de clamp (subclasse BTTrade + BTAjustaStops) LOGO
        # APÓS o include do Trade.mqh, terminando com "#define CTrade BTTrade". A partir
        # daí, QUALQUER "CTrade <nome>;" que a IA declare (com qualquer nome de variável)
        # vira a subclasse com clamp pelo preprocessador — não depende mais de casar o
        # nome. Conserta o "invalid stops" em qualquer código da IA. Se não achar o
        # include (raríssimo), nada é injetado (degrada seguro, sem quebrar compilação).
        _minc = _re.search(r"#include\s*<Trade[\\/]Trade\.mqh>", codigo)
        if _minc:
            codigo = codigo.replace(_minc.group(0),
                                    _minc.group(0) + "\n" + _BT_TRADE_CLAMP_MQL5, 1)

    # ── SELO (identidade on-chart) + VISÃO (snapshot multi-timeframe) ─────
    # Injeta as funções dos dois ANTES do OnInit e chama Init/Tick/Deinit de
    # cada um por regex. Só ativa se achar o OnInit — se não achar, deixa o EA
    # intacto (nunca entra função sem chamada nem chamada sem função → não
    # compila quebrado). A visão emite por tempo, então NÃO depende de NovaBarra.
    import re as _re
    if _re.search(r"int\s+OnInit\s*\(", codigo):
        # 1) funções do selo + da visão logo antes do OnInit
        #    (lambda evita o re interpretar \\ e \g no texto injetado)
        codigo = _re.sub(r"int\s+OnInit\s*\(",
                         lambda m: _BT_PAINEL_MQL5 + "\n" + _BT_VISAO_MQL5 + "\n" + m.group(0),
                         codigo, count=1)
        # 2/3/4) Injeta o "grito de ligou" (BTVisaoTick emite JÁ no OnInit, no exato
        #    momento do OK) + o tick vivo + o deinit — achando o CORPO da função de
        #    forma ROBUSTA: acha a assinatura, depois a PRÓXIMA chave { (ignorando
        #    comentário, quebra de linha, formatação) e insere logo após ela. Não
        #    depende mais do regex casar a assinatura inteira — era isso que fazia o
        #    snapshot no OnInit FALHAR em alguns bots (comentário/quebra entre ) e {),
        #    caindo pra o snapshot por barra (60s). Agora acende sempre em ~1 tick.
        def _apos_chave(cod, assinatura, texto):
            m = _re.search(assinatura, cod)
            if not m:
                return cod
            i = cod.find("{", m.end())
            if i < 0:
                return cod
            return cod[:i+1] + texto + cod[i+1:]
        codigo = _apos_chave(codigo, r"int\s+OnInit\s*\(",
                             "\n   BTPainelInit();\n   BTVisaoInit();\n   BTVisaoTick();")
        codigo = _apos_chave(codigo, r"void\s+OnTick\s*\(",
                             "\n   BTPainelTick();\n   BTVisaoTick();\n   BTLerComando();")
        codigo = _apos_chave(codigo, r"void\s+OnDeinit\s*\(",
                             "\n   BTPainelDeinit();\n   BTVisaoDeinit(reason);")
    # v6.59: sentinela — se algo deixar chave órfã, grita no log do Railway
    if codigo.count("{") != codigo.count("}"):
        try:
            print("[instrumentar] AVISO: chaves desbalanceadas pós-instrumentação "
                  f"({{={codigo.count('{')} }}={codigo.count('}')}) — .mq5 NÃO vai compilar")
        except Exception:
            pass
    return codigo


def _magic_para_bot(estrategia_id: str, ativo: str, nome: str) -> int:
    """MAGIC único e determinístico por (estratégia, ativo, nome). Mantém o
    mesmo bot com o mesmo magic se regenerado, e separa estratégias/ativos
    diferentes pra não brigarem no mesmo gráfico do MT5. Range seguro, longe
    do 20250 padrão e dos magics fixos do TrailingBot (20280-20283)."""
    base = (f"{(estrategia_id or '').strip().lower()}|"
            f"{(ativo or '').strip().upper()}|"
            f"{(nome or '').strip().lower()}")
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    # faixa 100000 .. ~1.9 bi (cabe em ulong do MT5, fora das faixas reservadas)
    return 100000 + (int(h[:12], 16) % 1_900_000_000)


def _magic_do_token(bot_token: str, base_fallback: str = "") -> int:
    """MAGIC único por BOT — derivado do TOKEN (que é único por bot na nuvem).
    Assim cada bot tem o seu magic e as ordens de bots diferentes nunca se
    confundem no MT5, mesmo com nomes ou estratégias iguais. Sem token, cai num
    hash do fallback (estratégia/ativo/nome) só pra não repetir o 20250 padrão.
    Mesma faixa segura do _magic_para_bot (100000..~1.9bi)."""
    chave = (bot_token or "").strip() or (base_fallback or "").strip()
    if not chave:
        return 20250
    h = hashlib.sha1(("bot|" + chave).encode("utf-8")).hexdigest()
    return 100000 + (int(h[:12], 16) % 1_900_000_000)


def _nome_arquivo_bot(bot_nome: str, fallback: str = "MeuBot") -> str:
    """Nome do arquivo/EA = nome do bot que o usuário digitou, sanitizado.
    SEM prefixo e SEM sufixo — é a identidade do bot na plataforma e no MT5.
    Acentos viram ASCII (á→a, ç→c) pro MetaEditor não estranhar; colapsa
    separadores repetidos, limita tamanho e cai no fallback se vazio."""
    import unicodedata as _ud
    base = _ud.normalize("NFKD", (bot_nome or "").strip())
    base = base.encode("ascii", "ignore").decode("ascii")   # tira acentos
    safe = "".join(c if (c.isalnum() and ord(c) < 128) else "_" for c in base)
    safe = "_".join(p for p in safe.split("_") if p)         # tira __ repetidos
    safe = safe[:40].strip("_")
    return safe or fallback


def _forcar_magic_mql5(codigo: str, magic: int) -> str:
    """Garante que o .mq5 use exatamente ESTE magic, seja qual for o formato:
    troca o valor de InpMagic (conversores testados e IA que segue a instrução)
    ou, em último caso, o literal dentro de SetExpertMagicNumber(...). ALÉM disso,
    injeta magic=<valor> como LITERAL em TODA linha BOTTESTED_SNAPSHOT — é a
    identidade que o conector usa pra rotear o snapshot pro token do bot certo.
    Sem magic no snapshot, o dado é ambíguo (não dá pra saber de qual bot é) e o
    conector não consegue atribuir — dava o falso 'Operar' na trilha."""
    import re as _re
    if not codigo:
        return codigo
    novo, n = _re.subn(r"(InpMagic\s*=\s*)\d+", r"\g<1>" + str(magic), codigo, count=1)
    if not n:
        novo, n = _re.subn(r"SetExpertMagicNumber\s*\(\s*\d+\s*\)",
                           f"SetExpertMagicNumber({magic})", codigo, count=1)
    codigo = novo if n else codigo
    # magic no snapshot (literal, idempotente): funciona pra PrintFormat e concat,
    # do conversor testado ou da IA — todos imprimem o prefixo "BOTTESTED_SNAPSHOT|".
    if magic and "BOTTESTED_SNAPSHOT|" in codigo and "BOTTESTED_SNAPSHOT|magic=" not in codigo:
        codigo = codigo.replace("BOTTESTED_SNAPSHOT|", f"BOTTESTED_SNAPSHOT|magic={magic}|")
    return codigo


def gerar_mql5(estrategia_id: str, codigo_py: str, nome: str, p,
               bot_nome: str = "", bot_token: str = "") -> dict:
    """A: estratégia conhecida → conversor testado; B: customizado → IA (com aviso).
    IDENTIDADE POR BOT: o arquivo/EA leva o NOME DO BOT (bot_nome) e o magic vem
    do TOKEN — então dois bots nunca colidem no MT5, nem no arquivo nem nas ordens.
    Sem bot_nome/bot_token (chamada antiga), cai no nome da estratégia como antes.
    Retorna {codigo, fonte, aviso, filename, magic}."""
    ativo = getattr(p, "ativo", "") or ""
    # nome do arquivo = nome do bot (sanitizado, sem prefixo/sufixo). Fallback: estratégia.
    filename = _nome_arquivo_bot(bot_nome, fallback=_nome_arquivo_bot(nome, fallback="MeuBot")) + ".mq5"
    # magic = token (único por bot); sem token, hash de (estratégia|ativo|nome)
    base_fb = f"{(estrategia_id or '').lower()}|{ativo.upper()}|{(bot_nome or nome or '').lower()}"
    magic = _magic_do_token(bot_token, base_fb)
    conv = _CONVERSORES_MQL5.get((estrategia_id or "").strip())
    if conv:
        codigo = _instrumentar_log_mql5(conv(p))
        codigo = _forcar_magic_mql5(codigo, magic)
        return {"codigo": codigo, "fonte": "testado", "aviso": "", "filename": filename, "magic": magic}
    mq = _mql5_via_ia(codigo_py, bot_nome or nome or "Estrategia", p)
    if mq:
        aviso = ("Conversao automatica por IA — revise o codigo com atencao. Teste em conta DEMO "
                 "antes de qualquer uso real. Confira entradas/saidas, stop, take e lote.")
        codigo = _instrumentar_log_mql5(mq)
        codigo = _forcar_magic_mql5(codigo, magic)
        return {"codigo": codigo, "fonte": "ia", "aviso": aviso, "filename": filename, "magic": magic}
    return {"codigo": "", "fonte": "indisponivel",
            "aviso": "Conversao automatica indisponivel para este codigo no momento.",
            "filename": filename, "magic": magic}


# ── Endpoint: exportar estratégia para MQL5 (MetaTrader 5) ──
@app.post("/exportar/mql5")
def exportar_mql5(req: BacktestCustom):
    """Gera Expert Advisor MQL5 da estratégia ativa. Estratégia conhecida usa
    conversor testado; código customizado cai na IA (com aviso). EXECUÇÃO REAL —
    sempre com avisos de risco. Usa os parâmetros reais do usuário."""
    est_id = (getattr(req, "estrategia_id", "") or "").strip()
    nome = getattr(req, "estrategia_nome", "") or "Estrategia"
    res = gerar_mql5(est_id, getattr(req, "codigo", "") or "", nome, req,
                     bot_nome=getattr(req, "bot_nome", "") or "",
                     bot_token=getattr(req, "bot_token", "") or "")
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
        "id": "tendencia_dia_adaptativa", "casa": False, "emoji": "🚀",
        "nome": "Trend Day Adaptativo",
        "desc": "Evolução TF-aware da Escalonada: piramida a favor da tendência em qualquer TF (5m/15m/30m/1h/4h/1d) ajustando trailing, cooldown e espaçamento por ATR automaticamente. Trailing FECHA O PACOTE INTEIRO em vez de uma posição por vez. Sai também se aparecem 2 velas vermelhas em série. Cada piramidação exige que o preço tenha avançado 0.7 ATR desde a última — nada de spam de entradas na mesma vela.",
        "tags": ["TENDÊNCIA", "ESCALONADO", "TF-AWARE"], "nivel": "avançado",
        "mercados": ["BTC/USD", "XAU/USD (Ouro)", "US30", "NASDAQ"],
        "codigo": '''from backtesting import Strategy
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

def ATR(highs, lows, closes, n):
    tr = pd.DataFrame({"h": highs, "l": lows, "c": closes})
    tr["hl"] = tr["h"] - tr["l"]
    tr["hc"] = (tr["h"] - tr["c"].shift(1)).abs()
    tr["lc"] = (tr["l"] - tr["c"].shift(1)).abs()
    tr["tr"] = tr[["hl", "hc", "lc"]].max(axis=1)
    return tr["tr"].rolling(n).mean()

class TrendDayAdaptativo(Strategy):
    n = 20
    max_piramide = 3
    atr_periodo = 14
    espacamento_atr = 0.7    # 0.7 x ATR entre entradas
    cooldown_barras = 3      # min de barras entre entradas
    trail_pct = 0.015        # 1.5% (ajuste manual pra backtest — MQL5 usa TF-aware)
    saida_2_vermelhas = True

    def init(self):
        self.ema_high = self.I(EMA, self.data.High, self.n)
        self.ema_low  = self.I(EMA, self.data.Low,  self.n)
        self.atr = self.I(ATR, self.data.High, self.data.Low, self.data.Close, self.atr_periodo)
        self.topo = None
        self.ultima_entrada_bar = -999
        self.preco_ultima_entrada = 0.0

    def next(self):
        preco = self.data.Close[-1]
        alta  = preco > self.ema_high[-1]
        baixa = preco < self.ema_low[-1]
        atr_v = self.atr[-1] if self.atr[-1] and self.atr[-1] > 0 else 0
        barra_atual = len(self.data.Close) - 1

        # TRAILING COLETIVO
        if self.position and self.position.is_long:
            self.topo = max(self.topo or preco, preco)
            if preco < self.topo * (1 - self.trail_pct):
                self.position.close(); self.topo = None
                self.ultima_entrada_bar = -999; self.preco_ultima_entrada = 0.0
                return
            # SAIDA DEFENSIVA por 2 velas vermelhas
            if self.saida_2_vermelhas and len(self.data.Close) > 2:
                c1, o1 = self.data.Close[-1], self.data.Open[-1]
                c2, o2 = self.data.Close[-2], self.data.Open[-2]
                if c1 < o1 and c2 < o2:
                    self.position.close(); self.topo = None
                    self.ultima_entrada_bar = -999; self.preco_ultima_entrada = 0.0
                    return

        # ENTRA/PIRAMIDA a favor
        if alta and len(self.trades) < self.max_piramide:
            if (barra_atual - self.ultima_entrada_bar) < self.cooldown_barras:
                return
            if self.preco_ultima_entrada > 0 and atr_v > 0:
                if (preco - self.preco_ultima_entrada) < atr_v * self.espacamento_atr:
                    return
            self.buy()
            self.ultima_entrada_bar = barra_atual
            self.preco_ultima_entrada = preco
        elif baixa and self.position and self.position.is_long:
            self.position.close(); self.topo = None
            self.ultima_entrada_bar = -999; self.preco_ultima_entrada = 0.0
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
        "id": "fibonacci_retracao", "casa": False, "emoji": "🌀",
        "nome": "Fibonacci — Retração (Golden Zone)",
        "desc": "O clássico dos pullbacks: na tendência (filtro EMA50), espera o preço devolver 38,2%–61,8% do último impulso (a golden zone) e retomar — entra a favor, alvo no topo/fundo do impulso, invalida se passar do 78,6%. Espelhado nos dois lados.",
        "tags": ["PRICE ACTION", "FIBONACCI", "PULLBACK"], "nivel": "intermediário",
        "mercados": ["XAU/USD (Ouro)", "EUR/USD", "BTC/USD"],
        "codigo": '''from backtesting import Strategy

class FibonacciRetracao(Strategy):
    janela = 55        # candles p/ achar o impulso (swing low -> swing high)
    filtro_ema = 50    # tendencia: preco acima da EMA50 = so compra; abaixo = so venda

    def init(self):
        import pandas as pd
        close = pd.Series(self.data.Close)
        self.ema50 = self.I(lambda s: pd.Series(s).ewm(span=self.filtro_ema, adjust=False).mean(), self.data.Close)
        self.alvo = None
        self.invalida = None

    def next(self):
        h, l, c, o = self.data.High, self.data.Low, self.data.Close, self.data.Open
        i = len(c) - 1
        if i < self.janela + 2:
            return
        preco = c[-1]

        # gestao da posicao aberta: alvo no topo/fundo do impulso; invalida no 78.6%
        if self.position:
            if self.position.is_long:
                if preco >= self.alvo or preco <= self.invalida:
                    self.position.close()
            else:
                if preco <= self.alvo or preco >= self.invalida:
                    self.position.close()
            return

        # impulso recente: swing high e swing low da janela (sem olhar o candle atual)
        sh = max(h[-self.janela-1:-1])
        sl = min(l[-self.janela-1:-1])
        rng = sh - sl
        if rng <= 0:
            return

        if preco > self.ema50[-1]:
            # tendencia de ALTA: pullback na golden zone (38.2%-61.8% do impulso)
            z_raso = sh - 0.382 * rng
            z_fundo = sh - 0.618 * rng
            invalida = sh - 0.786 * rng     # abaixo do 78.6% o pullback virou reversao
            # preco DENTRO da zona + candle de retomada (fechou subindo)
            if z_fundo <= preco <= z_raso and c[-1] > o[-1] and l[-1] > invalida:
                self.alvo = sh              # alvo classico: topo do impulso
                self.invalida = invalida
                self.buy()
        elif preco < self.ema50[-1]:
            # tendencia de BAIXA: espelhado (rally ate a golden zone do impulso de queda)
            z_raso = sl + 0.382 * rng
            z_fundo = sl + 0.618 * rng
            invalida = sl + 0.786 * rng
            if z_raso <= preco <= z_fundo and c[-1] < o[-1] and h[-1] < invalida:
                self.alvo = sl
                self.invalida = invalida
                self.sell()
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
        "id": "tripla_media_9_21_50", "casa": False, "emoji": "📶",
        "nome": "Tripla Média 9/21/50",
        "desc": "A evolução do 9/21: o cruzamento continua dando o tempo de entrada, mas a EMA50 vira o juiz da tendência — cruzamento CONTRA a 50 é ignorado (o que mata a maior fraqueza do 9/21 puro: sinais falsos na lateralização). Compra só acima da 50, vende só abaixo.",
        "tags": ["TENDÊNCIA", "EMA"], "nivel": "iniciante",
        "mercados": ["EUR/USD", "S&P500", "XAU/USD (Ouro)"],
        "codigo": '''from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd

def EMA(serie, n):
    return pd.Series(serie).ewm(span=n, adjust=False).mean()

class TriplaMedia95021(Strategy):
    rapida = 9
    lenta = 21
    filtro = 50   # a EMA50 e o juiz da tendencia: cruzamento contra ela e ignorado

    def init(self):
        self.e9 = self.I(EMA, self.data.Close, self.rapida)
        self.e21 = self.I(EMA, self.data.Close, self.lenta)
        self.e50 = self.I(EMA, self.data.Close, self.filtro)

    def next(self):
        preco = self.data.Close[-1]
        # 9 cruza acima da 21 COM preco acima da 50 = compra (a favor da mare)
        if crossover(self.e9, self.e21):
            if preco > self.e50[-1]:
                self.position.close()
                self.buy()
            elif self.position.is_short is False and self.position:
                self.position.close()   # cruzou contra a posicao vendida: sai
        # 9 cruza abaixo da 21 COM preco abaixo da 50 = venda
        elif crossover(self.e21, self.e9):
            if preco < self.e50[-1]:
                self.position.close()
                self.sell()
            elif self.position.is_long and self.position:
                self.position.close()   # cruzou contra a posicao comprada: sai
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
        # v6.44 (curadoria do dono): NASDAQ removido — medição real deu -15.8%
        # com PF 0.76 nesta estratégia (XAU/USD: +64.8%, PF 1.52). O card só
        # sugere onde ela funciona.
        "mercados": ["XAU/USD (Ouro)", "Índices"],
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
  "tendencia_dia_adaptativa": {
    "en": {"nome": "Adaptive Trend Day", "desc": "TF-aware evolution of Daily Scaling: pyramids with the trend in ANY TF (5m/15m/30m/1h/4h/1d), automatically adjusting trailing, cooldown and ATR-based spacing. Trailing closes the ENTIRE package, not one position at a time. Also exits on 2 consecutive red candles. Each new pyramid entry requires price to have advanced 0.7 ATR from the previous — no entry spam within the same bar."},
    "es": {"nome": "Trend Day Adaptativo", "desc": "Evolución TF-aware de la Escalonada Diaria: piramida a favor de la tendencia en CUALQUIER TF (5m/15m/30m/1h/4h/1d), ajustando automáticamente trailing, cooldown y espaciado por ATR. El trailing cierra el paquete ENTERO, no una posición por vez. Sale también con 2 velas rojas seguidas. Cada nueva piramidación exige que el precio haya avanzado 0.7 ATR desde la última — sin spam de entradas en la misma vela."}},
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

OFFLINE_APOS_SEGUNDOS = 45   # v6.69: 45s = 3 ciclos de snapshot (15s cada) = com certeza morto

# ════════════════════════════════════════════════════════════════════════════
# ██  PRESENÇA — sensor de atividade (fonte de verdade do estado de um bot)  ██
# ════════════════════════════════════════════════════════════════════════════
# Bloco único e reusável: responde "o bot está PARADO / CONECTADO / OPERANDO?"
# a partir de 3 sinais, independente da PLATAFORMA (MT5 hoje, Tryd amanhã):
#   • heartbeat  -> coluna conector_visto_em   (o coletor/conector está vivo)
#   • snapshot   -> coluna ultimo_ping          (o EA está no gráfico emitindo)
#   • parar      -> coluna conector_parado_em   (aviso EXPLÍCITO de desconexão)
# Estados:
#   PARADO     = conector desligado (Parar apertado) ou sem sinal há tempo
#   CONECTADO  = coletor vivo e pareado, mas o EA não está emitindo no gráfico
#   OPERANDO   = EA no gráfico emitindo snapshot ao vivo
# A plataforma (Tryd/MT5) só EMPURRA os 3 sinais; este bloco DECIDE o estado.
# Corte imediato no Parar = o coletor manda o sinal 'parar'; os timeouts abaixo
# são só rede de segurança pra queda sem aviso (crash/luz).
_PRESENCA_JANELA_HB   = 40   # s sem heartbeat -> coletor caiu (deixa de CONECTADO)
_PRESENCA_JANELA_SNAP = 90   # s sem snapshot novo -> não está OPERANDO
_PRESENCA_THROTTLE_HB = 12   # s mínimos entre gravações do heartbeat no banco

def _presenca_log(msg: str):
    """Log dedicado do sensor de presença (prefixo grepável nos logs do Railway).
    É por aqui que se enxerga a linha do tempo de qualquer bot: conectou, operou,
    parou — com origem do sinal. Vale igual pra MT5 e Tryd."""
    try:
        import sys as _sys
        print(f"[PRESENCA] {msg}", file=_sys.stderr, flush=True)
    except Exception:
        pass

def _presenca_ts(v) -> float:
    if not v:
        return 0.0
    try:
        return _dt.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0

def _presenca_estado(bot: dict, agora_ts: float = None) -> str:
    """PARADO / CONECTADO / OPERANDO a partir dos 3 sinais do bot (fonte única)."""
    if agora_ts is None:
        agora_ts = _dt.now(_tz.utc).timestamp()
    # heartbeat: coluna conector_visto_em OU heartbeat em memória (_MT5_POLLS) — o
    # fallback em memória faz o CONECTADO funcionar mesmo sem a coluna (1 worker);
    # a coluna cobre o multi-worker. Usa o mais recente dos dois.
    hb_db  = _presenca_ts(bot.get("conector_visto_em"))
    try:
        hb_mem = float(_MT5_POLLS.get(bot.get("bot_token"), 0) or 0)
    except Exception:
        hb_mem = 0.0
    hb    = max(hb_db, hb_mem)
    snap  = _presenca_ts(bot.get("ultimo_ping"))
    parar = _presenca_ts(bot.get("conector_parado_em"))
    # o Parar (se for o sinal mais recente) vence tudo -> corte imediato
    if parar and parar >= max(hb, snap):
        return "PARADO"
    if snap and (agora_ts - snap) < _PRESENCA_JANELA_SNAP:
        return "OPERANDO"
    if hb and (agora_ts - hb) < _PRESENCA_JANELA_HB:
        return "CONECTADO"
    return "PARADO"

def _presenca_etapa(bot: dict, marco, agora_dt) -> int:
    """Traduz o estado de presença nas etapas 5/6 da trilha (0 = não acende).
    OPERANDO só vira etapa 6 se o snapshot for POSTERIOR ao envio da sessão."""
    est = _presenca_estado(bot, agora_dt.timestamp())
    if est == "PARADO":
        return 0
    if est == "CONECTADO":
        return 5
    # OPERANDO
    try:
        ping = _dt.fromisoformat(str(bot.get("ultimo_ping")).replace("Z", "+00:00"))
        if (marco is None) or (ping > marco):
            return 6
    except Exception:
        pass
    return 5  # emitindo, mas ping anterior ao envio desta sessão -> só conectado
# ════════════════════════════════════════════════════════════════════════════


# Cooldown anti-spam por regra (minutos)
_AGENTE_COOLDOWN_MIN = {"F1": 60, "F2": 30, "F3": 15, "F4": 1440, "LEITURA": 20}

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

class ConectorExcluir(BaseModel):
    user_id: Optional[str] = None    # caminho plataforma (front já manda user_id)
    bot_id: int
    bot_token: Optional[str] = None  # caminho conector (deleta via token do bot)

class SugestaoLida(BaseModel):
    user_id: str
    sugestao_id: int


# ════════════════════════════════════════════════════════════════════════════
#  v6.67 — COCKPIT DE ANÁLISE CRUZADA (BOT + IA)
#
#  Não é chat: são dois pareceres independentes sobre o MESMO momento
#  (A leitura do BOT vem do EA no MT5; a análise da IA vem daqui com o
#  snapshot como base) + uma SÍNTESE do cruzamento (VEREDITO).
#
#  Uma única chamada de IA por rodada devolve JSON com {analise_ia, veredito,
#  sinal}. O front renderiza cada campo no seu bloco.
#
#  Estado em memória (por worker). Sem tabela — se Railway reinicia, começa
#  do zero: análise cruzada é INTERPRETAÇÃO viva, não dado regulatório.
# ════════════════════════════════════════════════════════════════════════════
import time as _time_anl
from collections import deque as _deque_anl

_ANL_HIST = {}          # bot_id (int) -> deque[dict]
_ANL_LAST = {}          # bot_id -> {assinatura, ts_ultima_analise}
_ANL_HIST_MAX = 30      # 30 análises = ~30-90 min de cockpit aberto
_ANL_COOLDOWN_SEG = 30  # entre análises de status (eventos ignoram)
_ANL_SILENCIO_SEG = 90  # após X sem mudança, gera uma observação factual


def _anl_hist(bot_id):
    if bot_id not in _ANL_HIST:
        _ANL_HIST[bot_id] = _deque_anl(maxlen=_ANL_HIST_MAX)
    return _ANL_HIST[bot_id]


def _anl_push(bot_id, entrada):
    """Empilha análise cruzada no histórico com timestamp ISO."""
    if not entrada:
        return
    entrada = dict(entrada)
    entrada["ts"] = _dt.now(_tz.utc).isoformat()
    _anl_hist(bot_id).append(entrada)


def _anl_assinatura(bot_leitura):
    """Assinatura curta do que o bot vê AGORA. Muda entre ticks =
    algo novo aconteceu (regime, padrões, posições)."""
    if not bot_leitura:
        return ""
    reg = ((bot_leitura.get("regime") or {}).get("estado") or "").lower()
    pads = [(p.get("nome") or p.get("padrao") or "") + ":" + str(p.get("tf") or "")
            for p in (bot_leitura.get("padroes") or [])]
    pos = bot_leitura.get("posicoes") or 0
    return f"{reg}|{pos}|{','.join(sorted(pads))}"


def _anl_idioma_do_user(sb, user_id):
    try:
        p = sb.table("perfis").select("idioma").eq("id", user_id).limit(1).execute()
        return (p.data[0].get("idioma") if p.data else None) or "pt"
    except Exception:
        return "pt"


def _analisar_ia(ctx, gatilho="status"):
    """Chama Anthropic Haiku e devolve {analise_ia, veredito, sinal}. Uma
    chamada, três outputs. Any falha -> None (caller não empurra ao histórico)."""
    import sys
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return None
    idioma = ctx.get("idioma", "pt")
    idioma_nome = _IDIOMA_NOME.get(idioma, "português brasileiro")
    try:
        import httpx
        sistema = (
            "Você é a inteligência analítica de uma plataforma de trading que assiste um bot "
            "rodando ao vivo no MetaTrader 5 do usuário. Sua função: fazer análise TÉCNICA "
            "CONTEXTUAL do momento atual do mercado deste bot, cruzando o que o EA está vendo "
            "(narração mecânica) com o QUE VOCÊ SABE sobre esse ativo neste timeframe.\n\n"
            "PRINCÍPIO CENTRAL — VOCÊ ABSORVE, NÃO CONSULTA. Quando o contexto trouxer estatística "
            "de padrão medido neste ativo (campo 'confirmacao': ex. veredito 'Engolfo no 5m: medido "
            "42x, 68% confirmou'), você INCORPORA isso como CONHECIMENTO PRÓPRIO. Fale como analista "
            "experiente que SABE, nunca como sistema que consultou tabela. NUNCA diga 'no banco de "
            "dados', 'na tabela', 'na nossa base', 'consultei'. DIGA: 'no histórico deste ativo, esse "
            "padrão tende a converter em torno de 70%', 'já vi esse cenário antes: quando o 4h está "
            "lateral e o 5m rompe, a taxa cai bastante', 'esse tipo de rompimento após consolidação "
            "assim historicamente favorece o lado da tendência maior'.\n\n"
            "REGRAS INVIOLÁVEIS:\n"
            "(1) NUNCA prometa lucro, NUNCA preveja o mercado. Use 'pode', 'tende', 'historicamente "
            "favorece', 'aumenta/reduz a probabilidade'. Proibido: 'vai', 'garante', 'certamente', "
            "'100%';\n"
            "(2) escreva NO IDIOMA: " + idioma_nome + "; tom de mentor experiente, direto, sem "
            "enfeite; sem markdown; sem crases;\n"
            "(3) VAREIE aberturas e estrutura — nunca comece 2 análises seguidas do mesmo jeito;\n"
            "(4) NUNCA mencione outros usuários, comunidade, base coletiva, dados de outras pessoas. "
            "'no histórico deste ativo' é ok, 'outros traders' não é;\n"
            "(5) se um dado vier null/ausente, simplesmente não fale dele.\n\n"
            "COMO CRUZAR AS DUAS LEITURAS:\n"
            "Você recebe narracao_mecanica (o que o EA reportou — texto curto factual do MT5) "
            "e os dados crus do momento (preço, EMAs, regime por TF, padrões, estrutura, confirmação). "
            "Sua ANÁLISE deve dialogar com o que o BOT vê, acrescentando contexto que ele SOZINHO não "
            "teria (histórico, outros TFs, níveis, força estatística).\n\n"
            "MOMENTUM POR TIMEFRAME — SEU TRUNFO DE MENTOR HUMANO:\n"
            "O campo momentum_tfs traz descrições curtas do momentum recente de cada TF principal "
            "(5m, 15m, 60m, 4h). Ex.: 5m=3 velas de alta consecutivas, corpos crescentes / 4h=alternancia "
            "(2 de alta / 2 de baixa), corpos encolhendo. USE isso pra SOAR COMO MENTOR EXPERIENTE, "
            "descrevendo NATURALMENTE — o 15m ganhou força nas últimas velas mas o 4h ainda está lateral, "
            "os TFs curtos aceleraram enquanto o 4h continua indeciso, divergência entre TFs: 5m puxando "
            "pra cima, 60m estagnou. NUNCA liste como relatório técnico (5m: alta / 15m: neutro / ...) "
            "— isso é frio. VARIE quais TFs você menciona, use os que fazem sentido pro momento — não é "
            "obrigatório citar todos.\n\n"
            "SCANNER MULTI-TF DO BOT — MAIS OLHOS PRA VOCÊ:\n"
            "O campo scanner traz o pente-fino mecânico do BOT por timeframe a partir do 1m: "
            "comportamento de cada TF (tendência/lateral/reversão se formando), cascata_reversao "
            "(reversão detectada no 1m -> confirmando no 5m -> aguardando o 15m) e alinhamento "
            "(quantos TFs puxam pro mesmo lado). USE isso pra ANTECIPAR padrões EM CONSTRUÇÃO — "
            "especialmente reversões (a cascata) e tendências (o alinhamento) — cruzando com o "
            "histórico medido deste ativo. Se a cascata contradiz o alinhamento, esse conflito É a "
            "análise. Cite os TFs na ordem do menor pro maior.\n\n"
            "VISÃO DO OPERADOR — QUANDO PRESENTE NO CONTEXTO:\n"
            "O campo visao_operador traz a leitura que o PRÓPRIO usuário enviou (texto e/ou "
            "resumo do print que ele marcou; enviada_ha_min diz há quanto tempo). REGRA "
            "INEGOCIÁVEL: você CRUZA essa leitura com os dados — nunca obedece cegamente, "
            "nunca ignora. Se os dados sustentam a visão dele, REFORCE citando os números que "
            "confirmam (você apontou o topo em 4020 — de fato, 3 toques no 15m seguram ali). "
            "Se contradizem, DISCORDE com respeito e com números (preços, toques, TFs). Se não "
            "dá pra confirmar nem negar, diga o que precisaria acontecer pra validar. Converse "
            "como dois analistas: você apontou X — os dados mostram Y. A visão do operador "
            "NUNCA vira ordem de execução, recomendação de entrada imediata nem promessa. "
            "Quando houver visao_operador, o VEREDITO também deve dizer se está ALINHADO ou "
            "DIVERGENTE com a leitura do operador.\n\n"
            "E o VEREDITO conclui se as duas visões:\n"
            "  - 'alinhado' -> BOT e contexto histórico apontam pra mesma direção;\n"
            "  - 'divergente' -> BOT vê uma coisa, contexto sugere outra;\n"
            "  - 'adicao' -> BOT está neutro/esperando, IA acrescenta info relevante que ele não "
            "citou (nível próximo, virada em outro TF);\n"
            "  - 'neutro' -> sem sinal forte pra nenhum lado, momento morno.\n\n"
            "FORMATO DA RESPOSTA — SOMENTE um objeto JSON com EXATAMENTE 3 chaves:\n"
            "{\"analise_ia\": \"...\", \"veredito\": \"...\", \"sinal\": \"...\"}\n"
            "- analise_ia: 2 a 4 frases, máx ~360 caracteres, sem markdown;\n"
            "- veredito: 1 linha citável, máx ~130 caracteres, começa com palavra-chave em MAIÚSCULAS "
            "(ex.: ALINHADOS, DIVERGÊNCIA, ATENÇÃO, OBSERVAÇÃO), depois travessão e o resumo;\n"
            "- sinal: exatamente uma de: alinhado, divergente, adicao, neutro.\n"
            "Nada fora do JSON. Nada de crases. Nada de markdown."
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
                "max_tokens": 600,
                "temperature": 0.95,
                "system": sistema,
                "messages": [{"role": "user", "content":
                    "Gatilho: " + gatilho + "\n"
                    "Contexto ao vivo do bot (JSON):\n" + json.dumps(ctx, ensure_ascii=False)}],
            },
            timeout=10.0,
        )
        if r.status_code != 200:
            print(f"ANALISE IA status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        texto = "".join(b.get("text", "") for b in r.json().get("content", []))
        texto = texto.strip()
        if texto.startswith("```"):
            texto = texto.strip("`")
            if texto.startswith("json"):
                texto = texto[4:]
        obj = json.loads(texto)
        if not isinstance(obj, dict):
            return None
        an = str(obj.get("analise_ia") or "").strip()
        vr = str(obj.get("veredito") or "").strip()
        sn = str(obj.get("sinal") or "").strip().lower()
        if not an or not vr or sn not in ("alinhado", "divergente", "adicao", "neutro"):
            print(f"ANALISE IA formato invalido: sn={sn!r} an_len={len(an)} vr_len={len(vr)}", file=sys.stderr)
            return None
        return {"analise_ia": an[:600], "veredito": vr[:200], "sinal": sn}
    except Exception as e:
        print(f"ANALISE IA erro: {e}", file=sys.stderr)
        return None


def _analisar_por_gatilho(sb, bot_id, user_id, gatilho,
                          leitura_atual=None, ctx_extra=None):
    """Gera análise cruzada, grava no histórico, atualiza assinatura/cooldown.
    Silencioso em erro — cockpit nunca deve quebrar fluxo real."""
    try:
        ctx = {
            "idioma": _anl_idioma_do_user(sb, user_id),
            "gatilho": gatilho,
        }
        if leitura_atual:
            ctx["momento"] = {
                "simbolo": leitura_atual.get("simbolo"),
                "tf_op": leitura_atual.get("tf_op"),
                "preco": leitura_atual.get("preco"),
                "ema_h": leitura_atual.get("ema_h"),
                "ema_l": leitura_atual.get("ema_l"),
                "posicoes": leitura_atual.get("posicoes"),
                "flutuante": leitura_atual.get("flutuante"),
                "regime": leitura_atual.get("regime"),
                "padroes": leitura_atual.get("padroes"),
                "estrutura": leitura_atual.get("estrutura"),
                "zonas": leitura_atual.get("zonas"),
                "confirmacao": leitura_atual.get("confirmacao"),
                # v6.68 — resumo semantico por TF (mentor humano descritivo)
                "momentum_tfs": leitura_atual.get("momentum_tfs"),
                # A leitura mecanica do bot e o "BOT falou X" que a IA vai cruzar
                "narracao_mecanica": leitura_atual.get("narracao_bot"),
                # v6.82 — pente-fino multi-TF do BOT (scanner + cascata + alinhamento)
                "scanner": leitura_atual.get("scanner"),
            }
        if ctx_extra:
            ctx["evento"] = ctx_extra
        # v6.81 — VISÃO DO OPERADOR: se o usuário enviou a leitura dele (texto
        # e/ou print resumido), entra em TODA análise até expirar (TTL 2h).
        _vis = _visao_op_ativa(bot_id)
        if _vis:
            ctx["visao_operador"] = {
                "texto": _vis.get("texto"),
                "print_resumo": _vis.get("resumo_img"),
                "enviada_ha_min": int((_time_anl.time() - _vis.get("ts", 0)) / 60),
            }
        # últimas análises (contexto de continuidade — variar aberturas)
        hist = list(_anl_hist(bot_id))[-3:]
        if hist:
            ctx["analises_recentes"] = [{"veredito": h.get("veredito"),
                                         "sinal": h.get("sinal")} for h in hist]
        result = _analisar_ia(ctx, gatilho=gatilho)
        if not result:
            return
        entrada = {
            "gatilho": gatilho,
            "leitura_bot": (leitura_atual or {}).get("narracao_bot"),
            "analise_ia": result["analise_ia"],
            "veredito": result["veredito"],
            "sinal": result["sinal"],
        }
        _anl_push(bot_id, entrada)
        _ANL_LAST[bot_id] = {
            "assinatura": _anl_assinatura(leitura_atual) if leitura_atual else "",
            "ts": _time_anl.time(),
        }
    except Exception as _e:
        try: print(f"[analise] gatilho={gatilho} erro: {_e}")
        except Exception: pass


# ════════════════════════════════════════════════════════════════════════════
#  v6.81 — VISÃO DO OPERADOR (Sessão C do diferencial de informação)
#
#  O usuário passa a ter voz DENTRO da análise cruzada: texto curto e/ou um
#  print do gráfico dele. A visão fica ativa por 2h (ou até limpar/substituir)
#  e é injetada em toda análise como bloco visao_operador. A IA cruza com
#  honestidade (concorda/discorda com números) — nunca obedece cegamente e
#  NUNCA vira execução: ordem continua só pelos botões do Copiloto/Automático.
#
#  Print: UMA chamada de visão (Haiku) extrai um resumo estruturado; a imagem
#  é lida uma vez e DESCARTADA — as análises seguintes usam só o resumo.
#  Estado em memória por worker (mesma classe do _ANL_HIST): interpretação
#  viva, não dado regulatório. Zero SQL.
# ════════════════════════════════════════════════════════════════════════════

_VISAO_OP = {}                 # bot_id (int) -> {texto, resumo_img, ts, expira}
_VISAO_OP_TTL_SEG = 2 * 3600   # 2 horas de validade


def _visao_op_ativa(bot_id):
    v = _VISAO_OP.get(bot_id)
    if not v:
        return None
    if _time_anl.time() > v.get("expira", 0):
        _VISAO_OP.pop(bot_id, None)
        return None
    return v


def _visao_op_publica(bot_id):
    """Shape seguro pro front (chip 👁 no cockpit)."""
    v = _visao_op_ativa(bot_id)
    if not v:
        return None
    resta = max(0, int((v.get("expira", 0) - _time_anl.time()) / 60))
    return {"texto": v.get("texto") or None,
            "tem_print": bool(v.get("resumo_img")),
            "resta_min": resta}


def _visao_op_extrair_print(img_b64, img_tipo, idioma="pt"):
    """UMA chamada de visão: lê o print que o operador marcou e devolve um
    resumo curto e factual (níveis, linhas, padrões apontados). A imagem não
    é guardada. Falha -> None (a visão segue só com o texto)."""
    import sys
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave or not img_b64:
        return None
    idioma_nome = _IDIOMA_NOME.get(idioma, "português brasileiro")
    try:
        import httpx
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
                "max_tokens": 300,
                "temperature": 0.2,
                "system": (
                    "Você lê PRINTS de gráficos de trading que o usuário marcou e devolve um "
                    "resumo FACTUAL do que ele está apontando: ativo e timeframe se visíveis, "
                    "linhas e níveis desenhados (com preços quando legíveis), padrões marcados, "
                    "anotações escritas. Máximo ~400 caracteres, texto corrido, no idioma: "
                    + idioma_nome + ". Sem opinião, sem previsão, sem promessa — só o que está "
                    "marcado na imagem."
                ),
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                     "media_type": img_tipo or "image/png", "data": img_b64}},
                    {"type": "text", "text": "Resuma o que o operador marcou neste gráfico."},
                ]}],
            },
            timeout=25.0,
        )
        if r.status_code != 200:
            print(f"VISAO print status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        txt = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        return txt[:500] or None
    except Exception as e:
        print(f"VISAO print erro: {e}", file=sys.stderr)
        return None


# ════════════════════════════════════════════════════════════════════════════
#  v6.76 — BABYMACHINE: OPERAÇÕES REAIS (Sessão 6A — coleta)
#
#  Estende a BabyMachine (que hoje coleta backtests em backtests_historico)
#  pra registrar operações REAIS ao vivo do MT5 na tabela nova
#  babymachine_operacoes. Alimentada por 3 fontes:
#    (1) detector automático — cria linha 'pendente' quando decide entrar
#    (2) EA da estratégia compilada — cria linha 'aberta' via /conector/evento
#    (3) fechamento (qualquer fonte) — /conector/evento tipo=fechado
#
#  Non-blocking em TUDO: falha na coleta nunca quebra detector, comando ou
#  evento. Logs sempre.
# ════════════════════════════════════════════════════════════════════════════

_BM_LIMPAR_THROTTLE = {"ultimo": 0.0}


def _bm_limpar_throttled(sb):
    """Chama _bm_operacoes_limpar_antigas() no máximo 1x por 6h."""
    import time
    agora = time.time()
    if agora - _BM_LIMPAR_THROTTLE["ultimo"] < 21600:  # 6h
        return
    _BM_LIMPAR_THROTTLE["ultimo"] = agora
    try:
        sb.rpc("_bm_operacoes_limpar_antigas").execute()
    except Exception as _e:
        try: print(f"[bm limpar] {_e}")
        except Exception: pass


def _bm_extrair_contexto(bot, leitura, veredito):
    """Captura o contexto do momento da entrada. Sempre parcial — pega o que
    tiver disponível. Serve como 'foto' do cenário pra a BabyMachine aprender."""
    ctx = {}
    if leitura and isinstance(leitura, dict):
        reg = leitura.get("regime") or {}
        ctx["regime"] = str(reg.get("estado") or reg.get("regime") or "").upper()
        ctx["preco"] = leitura.get("preco")
        ctx["tfop"] = leitura.get("tf_op")
        # padrões formais + estrutura do offmind
        ctx["padroes_formais"] = leitura.get("padroes") or []
        # confirmação histórica (banco existente)
        conf = leitura.get("confirmacao") or {}
        if isinstance(conf, dict):
            ctx["confirmacao_score"] = conf.get("score")
            ctx["confirmacao_veredito"] = conf.get("veredito")
        # momentum semântico por TF
        ctx["momentum_tfs"] = leitura.get("momentum_tfs") or {}
    if veredito and isinstance(veredito, dict):
        ctx["veredito_ia"] = {
            "sinal": veredito.get("sinal"),
            "veredito": veredito.get("veredito"),
        }
    return ctx


def _bm_registrar_do_detector(sb, bot, oportunidade, leitura, veredito, comando_id, fonte):
    """Chamada quando o detector cria um comando via /mt5/comando.
    fonte: 'detector_auto' | 'detector_copiloto'.
    Cria linha status='pendente'. Vira 'aberta' quando o EA confirma
    execução (via _bm_marcar_aberta_por_comando)."""
    if not sb or not bot or not oportunidade: return
    try:
        contexto = _bm_extrair_contexto(bot, leitura, veredito)
        decisao = {
            "direcao":       oportunidade.get("direcao"),
            "cenario":       oportunidade.get("cenario"),
            "entrada":       oportunidade.get("entrada"),
            "stop":          oportunidade.get("stop"),
            "alvo1":         oportunidade.get("alvo1"),
            "alvo2":         oportunidade.get("alvo2"),
            "score":         oportunidade.get("score"),
            "estrelas":      oportunidade.get("estrelas"),
            "confluencias":  oportunidade.get("confluencias"),
            "explicacao":    oportunidade.get("explicacao"),
        }
        linha = {
            "user_id":          bot.get("user_id"),
            "bot_id":           bot.get("id"),
            "bot_nome":         bot.get("nome") or "",
            "ativo":            bot.get("simbolo") or "",
            "timeframe":        bot.get("timeframe") or "",
            "fonte":            fonte,
            "status":           "pendente",
            "oportunidade_id":  oportunidade.get("id"),
            "comando_id":       comando_id,
            "contexto_entrada": contexto,
            "decisao":          decisao,
        }
        sb.table("babymachine_operacoes").insert(linha).execute()
        _bm_limpar_throttled(sb)
    except Exception as _e:
        try: print(f"[bm registrar detector] {_e}")
        except Exception: pass


def _bm_marcar_aberta_por_comando(sb, comando_id, resultado_conf):
    """Chamada em /mt5/comando/confirmar. Se havia linha pendente pro
    comando, atualiza pra status='aberta' com ticket_mt5 e ts_entrada."""
    if not sb or not comando_id: return
    try:
        ticket = None
        preco_real = None
        if isinstance(resultado_conf, dict):
            ticket = resultado_conf.get("ticket") or resultado_conf.get("order")
            preco_real = resultado_conf.get("preco_real") or resultado_conf.get("price")
        upd = {
            "status":     "aberta",
            "ts_entrada": _dt.now(_tz.utc).isoformat(),
        }
        if ticket:      upd["ticket_mt5"] = int(ticket)
        # anexa preço real na decisão sem sobrescrever
        try:
            atual = (sb.table("babymachine_operacoes").select("decisao")
                     .eq("comando_id", comando_id).limit(1).execute().data or [])
            if atual:
                dec = dict(atual[0].get("decisao") or {})
                if preco_real:
                    dec["preco_real_entrada"] = preco_real
                upd["decisao"] = dec
        except Exception:
            pass
        sb.table("babymachine_operacoes").update(upd).eq("comando_id", comando_id).execute()
    except Exception as _e:
        try: print(f"[bm marcar aberta] {_e}")
        except Exception: pass


def _bm_registrar_estrategia_compilada(sb, bot, det, evento_id):
    """Chamada em /conector/evento tipo=aberto quando NÃO há operação
    pendente pra casar (EA da estratégia compilada abriu por conta).
    Cria linha status='aberta' com fonte='estrategia_compilada'."""
    if not sb or not bot: return
    try:
        # tenta puxar leitura recente pra ter contexto
        leitura = None
        try:
            leitura = _anl_ler_leitura(sb, bot.get("user_id"), bot.get("id"))
        except Exception:
            pass
        contexto = _bm_extrair_contexto(bot, leitura, None)
        # decisão inferida do detalhe do evento (o EA só manda "lado=BUY/SELL")
        lado = str((det or {}).get("lado") or "").upper()
        direcao = "long" if lado == "BUY" else ("short" if lado == "SELL" else "desconhecida")
        decisao = {
            "direcao":  direcao,
            "cenario":  "estrategia_compilada",
            "detalhe_ea": det or {},
        }
        linha = {
            "user_id":          bot.get("user_id"),
            "bot_id":           bot.get("id"),
            "bot_nome":         bot.get("nome") or "",
            "ativo":            bot.get("simbolo") or "",
            "timeframe":        bot.get("timeframe") or "",
            "fonte":            "estrategia_compilada",
            "status":           "aberta",
            "evento_id_abriu":  evento_id,
            "contexto_entrada": contexto,
            "decisao":          decisao,
            "ts_entrada":       _dt.now(_tz.utc).isoformat(),
        }
        sb.table("babymachine_operacoes").insert(linha).execute()
        _bm_limpar_throttled(sb)
    except Exception as _e:
        try: print(f"[bm registrar EA] {_e}")
        except Exception: pass


def _bm_processar_abertura(sb, bot, det, evento_id):
    """Roteador de /conector/evento tipo=aberto:
      - Se há linha pendente do detector pra este bot, marca como aberta
      - Senão, cria linha nova com fonte='estrategia_compilada'
    FIFO por bot pra casamento (o mais antigo pendente ganha)."""
    if not sb or not bot: return
    try:
        pendentes = (sb.table("babymachine_operacoes")
                     .select("id, comando_id")
                     .eq("bot_id", bot.get("id"))
                     .eq("status", "pendente")
                     .order("ts_criada")
                     .limit(1)
                     .execute().data or [])
        if pendentes:
            # casou — atualiza pra aberta
            upd = {
                "status":          "aberta",
                "ts_entrada":      _dt.now(_tz.utc).isoformat(),
                "evento_id_abriu": evento_id,
            }
            sb.table("babymachine_operacoes").update(upd).eq("id", pendentes[0]["id"]).execute()
        else:
            # estratégia compilada abriu sozinha
            _bm_registrar_estrategia_compilada(sb, bot, det, evento_id)
    except Exception as _e:
        try: print(f"[bm abertura] {_e}")
        except Exception: pass


def _bm_processar_fechamento(sb, bot, det, evento_id):
    """/conector/evento tipo=fechado. Fecha a operação ABERTA mais antiga
    desse bot (FIFO). Calcula pnl se der (detalhe geralmente traz preço)."""
    if not sb or not bot: return
    try:
        abertas = (sb.table("babymachine_operacoes")
                   .select("id, decisao, ts_entrada")
                   .eq("bot_id", bot.get("id"))
                   .eq("status", "aberta")
                   .order("ts_entrada")
                   .limit(1)
                   .execute().data or [])
        if not abertas:
            # órfã — fechou sem entrada registrada (perdemos o hook)
            try:
                sb.table("babymachine_operacoes").insert({
                    "user_id":         bot.get("user_id"),
                    "bot_id":          bot.get("id"),
                    "bot_nome":        bot.get("nome") or "",
                    "ativo":           bot.get("simbolo") or "",
                    "fonte":           "estrategia_compilada",
                    "status":          "orfa",
                    "evento_id_fechou": evento_id,
                    "resultado":       {"detalhe_ea": det or {}, "motivo": "fechou sem abertura registrada"},
                    "ts_saida":        _dt.now(_tz.utc).isoformat(),
                }).execute()
            except Exception:
                pass
            return
        op = abertas[0]
        ts_saida = _dt.now(_tz.utc)
        # calcula tempo ativo se possível
        tempo_seg = None
        try:
            ts_ent = _dt.fromisoformat(str(op.get("ts_entrada") or "").replace("Z", "+00:00"))
            tempo_seg = int((ts_saida - ts_ent).total_seconds())
        except Exception:
            pass
        # tenta extrair preço/pnl do detalhe (o EA pode ou não mandar)
        preco_saida = None
        pnl_pts = None
        pnl_pct = None
        try:
            det_low = {str(k).lower(): v for k, v in (det or {}).items()}
            for chave in ("preco_saida", "preco", "price", "close_price"):
                if chave in det_low and det_low[chave] is not None:
                    preco_saida = float(det_low[chave])
                    break
            for chave in ("pnl", "profit", "lucro"):
                if chave in det_low and det_low[chave] is not None:
                    pnl_pts = float(det_low[chave])
                    break
            # se tem entrada + saída, calcula pnl_pts se ainda não veio
            if preco_saida is not None:
                dec = op.get("decisao") or {}
                entrada = dec.get("preco_real_entrada") or dec.get("entrada")
                if entrada is not None:
                    dir_op = str(dec.get("direcao") or "").lower()
                    delta = (preco_saida - float(entrada)) if dir_op == "long" else (float(entrada) - preco_saida)
                    if pnl_pts is None:
                        pnl_pts = round(delta, 4)
                    if float(entrada) != 0:
                        pnl_pct = round(delta / float(entrada) * 100, 4)
        except Exception:
            pass
        resultado = {
            "preco_saida":     preco_saida,
            "pnl_pts":         pnl_pts,
            "pnl_pct":         pnl_pct,
            "tempo_ativo_seg": tempo_seg,
            "detalhe_ea":      det or {},
        }
        upd = {
            "status":           "fechada",
            "ts_saida":         ts_saida.isoformat(),
            "evento_id_fechou": evento_id,
            "resultado":        resultado,
        }
        sb.table("babymachine_operacoes").update(upd).eq("id", op["id"]).execute()
    except Exception as _e:
        try: print(f"[bm fechamento] {_e}")
        except Exception: pass


# ════════════════════════════════════════════════════════════════════════════
#  v6.74 — DETECTOR AUTOMATICO DE OPORTUNIDADE (Sessao 3 do loop fechado)
#
#  Roda 24/7 no /conector/snapshot (a cada 15s enquanto o EA emite). Analisa
#  o cenario do bot combinando os fatos que ja produzimos:
#    - offmind (padroes formais + niveis S/R com toques)
#    - regime sintetizado das zonas
#    - momentum semantico por TF
#    - confirmacao estatistica (banco historico)
#    - veredito da analise cruzada (BOT + IA)
#
#  Determina direcao, calcula entrada/stop/alvos com niveis reais do offmind,
#  soma confluencias (0-100), traduz em ESTRELAS (1-5). Cada modo do usuario
#  tem um LIMIAR de estrelas pra disparar:
#    - observar: NUNCA dispara (so registra passivo)
#    - copiloto: dispara oportunidade pra UI mostrar; usuario clica pra executar
#    - automatico: dispara + cria comando via /mt5/comando direto
#
#  Estado em memoria por bot (config, historico, circuit state). Tabela vem
#  na Sessao 6 quando construirmos dashboard historico — por enquanto se
#  Railway reinicia, tudo volta pra "observar" (fail-safe).
# ════════════════════════════════════════════════════════════════════════════

_BOT_CONFIG = {}          # bot_id (int) -> config dict
_OPORTUNIDADES_HIST = {}  # bot_id -> deque de oportunidades (mais recente por ultimo)
_CIRCUIT_STATE = {}       # bot_id -> {equity_inicio_dia, ops_hoje, data_ref}
_OPORT_MAX_HIST = 30
_OPORT_COOLDOWN_SEG = 60  # nao dispara nova oportunidade do mesmo bot em <60s

_DETECTOR_DEFAULT_CONFIG = {
    "modo_operacional":   "observar",    # observar | copiloto | automatico
    "modo_sensibilidade": "conservador", # conservador | moderado | agressivo
    "drawdown_max_dia":   5.0,           # % maximo de perda no dia
    "max_operacoes_dia":  10,            # circuit breaker
    "estrelas_min_auto":  4,             # so executa auto se >= X estrelas
    "pausado":            False,         # kill switch manual
    "lote_padrao":        0.01,          # lote default das ordens auto
}

_ESTRELAS_LIMIAR_POR_MODO = {
    "conservador": 4,
    "moderado":    3,
    "agressivo":   2,
}


def _bot_config_get(bot_id):
    """Retorna config do bot ou defaults conservadores. Nunca retorna None."""
    if bot_id not in _BOT_CONFIG:
        _BOT_CONFIG[bot_id] = dict(_DETECTOR_DEFAULT_CONFIG)
    return _BOT_CONFIG[bot_id]


def _bot_config_set(bot_id, novo):
    """Atualiza campos validos da config do bot. Ignora chaves nao permitidas."""
    cfg = _bot_config_get(bot_id)
    for k in _DETECTOR_DEFAULT_CONFIG.keys():
        if k in novo:
            cfg[k] = novo[k]
    return cfg


def _oportunidade_hist(bot_id):
    if bot_id not in _OPORTUNIDADES_HIST:
        from collections import deque
        _OPORTUNIDADES_HIST[bot_id] = deque(maxlen=_OPORT_MAX_HIST)
    return _OPORTUNIDADES_HIST[bot_id]


def _oport_push(bot_id, oportunidade):
    o = dict(oportunidade)
    o["ts"] = _dt.now(_tz.utc).isoformat()
    o["id"] = f"{bot_id}-{int(_time_anl.time() * 1000)}"
    _oportunidade_hist(bot_id).append(o)
    return o


# ──────────────────────────────────────────────────────────────────────────
#  DETECTORES DETERMINISTICOS (sem IA, custo zero)
# ──────────────────────────────────────────────────────────────────────────

def _detectar_direcao_potencial(fatos, leitura):
    """Analisa o cenario e determina se ha direcao potencial (long/short).
    Prioriza: (1) pullback em tendencia; (2) padrao de reversao em nivel;
    (3) rompimento. Retorna None se nao ha setup claro."""
    if not fatos: return None
    regime_str = str(fatos.get("regime") or "").upper()
    testando = fatos.get("niveis_sendo_testados") or []
    padroes = fatos.get("padroes_formais") or []
    # Caso 0 (v6.79): ROMPIMENTO DE RANGE/LATERALIZACAO — o gatilho mais
    # classico. Acumulacao rompe pra qualquer lado; entrada no rompimento,
    # stop de volta pro nivel rompido, alvo = projecao da altura (measured move).
    rng = fatos.get("range_lateral") or {}
    if rng.get("estado") == "rompeu_cima" and rng.get("topo"):
        return {"direcao": "long", "cenario": "rompimento_range_alta",
                "gatilho_ref": {"tipo": "resistencia", "nivel": rng.get("topo"),
                                "toques": rng.get("toques_topo")},
                "range": rng}
    if rng.get("estado") == "rompeu_baixo" and rng.get("fundo"):
        return {"direcao": "short", "cenario": "rompimento_range_baixa",
                "gatilho_ref": {"tipo": "suporte", "nivel": rng.get("fundo"),
                                "toques": rng.get("toques_fundo")},
                "range": rng}
    # Caso 0b (v6.80): REVERSAO POR ESTRUTURA (pivo 1-2-3) — 2o extremo mais
    # fraco + neckline rompida. Entrada no rompimento, stop de volta pra
    # dentro, alvo = projecao da altura da estrutura.
    sw = fatos.get("estrutura_swing") or {}
    if sw.get("estado") == "rompeu" and sw.get("neckline"):
        if sw.get("direcao") == "baixa":
            return {"direcao": "short", "cenario": "reversao_estrutura_baixa",
                    "gatilho_ref": {"tipo": "suporte", "nivel": sw.get("neckline")},
                    "swing": sw}
        if sw.get("direcao") == "alta":
            return {"direcao": "long", "cenario": "reversao_estrutura_alta",
                    "gatilho_ref": {"tipo": "resistencia", "nivel": sw.get("neckline")},
                    "swing": sw}
    # Caso 1: pullback em tendencia
    if "ALTA" in regime_str and testando:
        for nv in testando:
            if nv.get("tipo") == "suporte" and (nv.get("toques") or 0) >= 2:
                return {
                    "direcao": "long",
                    "cenario": "pullback_em_tendencia_alta",
                    "gatilho_ref": nv,
                }
    if "BAIXA" in regime_str and testando:
        for nv in testando:
            if nv.get("tipo") == "resistencia" and (nv.get("toques") or 0) >= 2:
                return {
                    "direcao": "short",
                    "cenario": "pullback_em_tendencia_baixa",
                    "gatilho_ref": nv,
                }
    # Caso 2: padrao de reversao em nivel
    if padroes and testando:
        for pad in padroes:
            direc = str(pad.get("direcao") or "").lower()
            if "alta" in direc:
                for nv in testando:
                    if nv.get("tipo") == "suporte":
                        return {
                            "direcao": "long",
                            "cenario": "padrao_reversao_em_suporte",
                            "gatilho_ref": nv,
                            "padrao_confirmando": pad,
                        }
            if "baixa" in direc:
                for nv in testando:
                    if nv.get("tipo") == "resistencia":
                        return {
                            "direcao": "short",
                            "cenario": "padrao_reversao_em_resistencia",
                            "gatilho_ref": nv,
                            "padrao_confirmando": pad,
                        }
    return None


def _calcular_niveis_operacao(direcao_info, fatos):
    """A partir da direcao potencial, calcula entrada/stop/alvos usando
    niveis REAIS do offmind. R:R minimo 1:1 (senao retorna None)."""
    preco = fatos.get("preco")
    if preco is None: return None
    try:
        preco = float(preco)
    except Exception:
        return None
    direcao = direcao_info["direcao"]
    gatilho_ref = direcao_info.get("gatilho_ref") or {}
    proximos = fatos.get("niveis_proximos") or []
    if direcao == "long":
        entrada = preco
        # stop: abaixo do suporte de referencia com pequena margem (0.1%)
        nivel_ref = gatilho_ref.get("nivel")
        if nivel_ref:
            stop = float(nivel_ref) * 0.999
        else:
            ema_l = fatos.get("distancia_ema_l")
            stop = preco - (preco * 0.005)
        # alvos
        resistencias = [n for n in proximos
                        if n.get("tipo") == "resistencia" and n.get("nivel", 0) > preco]
        resistencias.sort(key=lambda n: n.get("nivel"))
        risco = entrada - stop
        if risco <= 0: return None
        if resistencias:
            alvo1 = float(resistencias[0]["nivel"])
        else:
            alvo1 = entrada + risco * 1.5
        alvo2 = entrada + risco * 2.0
    else:  # short
        entrada = preco
        nivel_ref = gatilho_ref.get("nivel")
        if nivel_ref:
            stop = float(nivel_ref) * 1.001
        else:
            stop = preco + (preco * 0.005)
        suportes = [n for n in proximos
                    if n.get("tipo") == "suporte" and n.get("nivel", 0) < preco]
        suportes.sort(key=lambda n: -n.get("nivel"))
        risco = stop - entrada
        if risco <= 0: return None
        if suportes:
            alvo1 = float(suportes[0]["nivel"])
        else:
            alvo1 = entrada - risco * 1.5
        alvo2 = entrada - risco * 2.0
    # v6.79 — ROMPIMENTO DE RANGE: alvo1 = projecao da altura (measured move);
    # alvo2 estende +50%% da altura. Sobrepoe os alvos genericos acima.
    _rng_mm = direcao_info.get("range") or {}
    if str(direcao_info.get("cenario") or "").startswith("rompimento_range") and _rng_mm:
        _alt = float(_rng_mm.get("altura_pts") or 0)
        if direcao == "long" and _rng_mm.get("proj_alta"):
            alvo1 = float(_rng_mm["proj_alta"]); alvo2 = alvo1 + _alt * 0.5
        elif direcao == "short" and _rng_mm.get("proj_baixa"):
            alvo1 = float(_rng_mm["proj_baixa"]); alvo2 = alvo1 - _alt * 0.5
    # v6.80 — REVERSAO POR ESTRUTURA: alvo1 = projecao da altura do pivo.
    _sw_mm = direcao_info.get("swing") or {}
    if str(direcao_info.get("cenario") or "").startswith("reversao_estrutura") and _sw_mm.get("proj") is not None:
        _alt_sw = float(_sw_mm.get("altura_pts") or 0)
        if direcao == "long":
            alvo1 = float(_sw_mm["proj"]); alvo2 = alvo1 + _alt_sw * 0.5
        else:
            alvo1 = float(_sw_mm["proj"]); alvo2 = alvo1 - _alt_sw * 0.5
    rr = abs(alvo1 - entrada) / risco if risco > 0 else 0
    if rr < 1.0:
        return None  # R:R menor que 1:1 nao vale
    return {
        "entrada":       round(entrada, 4),
        "stop":          round(stop, 4),
        "alvo1":         round(alvo1, 4),
        "alvo2":         round(alvo2, 4),
        "risco_pts":     round(abs(entrada - stop), 4),
        "potencial_pts": round(abs(alvo1 - entrada), 4),
        "rr":            round(rr, 2),
    }


def _calcular_confluencias(direcao_info, fatos, leitura, veredito=None):
    """Soma pontos de confluencia (0-100) e lista os fatores. Determina a
    QUALIDADE do setup — quanto mais alinhado, mais estrelas."""
    if not direcao_info or not fatos: return {"score": 0, "confluencias": []}
    score = 0
    lista = []
    dir_pt = "alta" if direcao_info["direcao"] == "long" else "baixa"
    # +20 regime do TF de operacao alinhado
    regime_str = str(fatos.get("regime") or "").upper()
    if (dir_pt == "alta" and "ALTA" in regime_str) or (dir_pt == "baixa" and "BAIXA" in regime_str):
        score += 20
        lista.append({"peso": 20, "titulo": "Regime alinhado", "detalhe": f"TF de operacao em {regime_str}"})
    # +15 (v6.79) rompimento de lateralizacao: range medido com toques nos dois extremos
    if str(direcao_info.get("cenario") or "").startswith("rompimento_range"):
        _rng_cf = direcao_info.get("range") or {}
        score += 15
        lista.append({"peso": 15, "titulo": "Rompimento de lateralizacao",
                      "detalhe": (f"Range de {_rng_cf.get('altura_pts')} pts rompido "
                                  f"(fundo {_rng_cf.get('toques_fundo')}x · teto {_rng_cf.get('toques_topo')}x toques"
                                  + (", confirmado" if _rng_cf.get("confirmado") else "") + ")")})
    # +15 (v6.80) reversao por estrutura (pivo 1-2-3): 2o extremo mais fraco + neckline rompida
    if str(direcao_info.get("cenario") or "").startswith("reversao_estrutura"):
        _sw_cf = direcao_info.get("swing") or {}
        score += 15
        lista.append({"peso": 15, "titulo": "Reversao por estrutura (pivo 1-2-3)",
                      "detalhe": (f"Extremos {_sw_cf.get('p1')} -> {_sw_cf.get('p2')}, "
                                  f"neckline {_sw_cf.get('neckline')} rompida"
                                  + (", confirmado" if _sw_cf.get("confirmado") else ""))})
    # +15 TF maior (4h) alinhado via momentum semantico
    momentum_tfs = (leitura or {}).get("momentum_tfs") or {}
    m4h = momentum_tfs.get("4h") or {}
    rec4h = str(m4h.get("recentes") or "").lower()
    if dir_pt == "alta" and "alta" in rec4h and "baixa" not in rec4h:
        score += 15
        lista.append({"peso": 15, "titulo": "4h a favor", "detalhe": m4h.get("recentes")})
    elif dir_pt == "baixa" and "baixa" in rec4h and "alta" not in rec4h:
        score += 15
        lista.append({"peso": 15, "titulo": "4h a favor", "detalhe": m4h.get("recentes")})
    # +15 padrao formal na direcao
    for pad in (fatos.get("padroes_formais") or []):
        direc = str(pad.get("direcao") or "").lower()
        if dir_pt in direc:
            score += 15
            lista.append({"peso": 15, "titulo": f"Padrao {pad.get('nome')}",
                          "detalhe": f"formando no {pad.get('tf')}"})
            break
    # +15 (3+ toques) ou +10 (2 toques) do nivel testado
    testando = fatos.get("niveis_sendo_testados") or []
    if testando:
        toques_max = max((nv.get("toques") or 0) for nv in testando)
        if toques_max >= 3:
            score += 15
            lista.append({"peso": 15, "titulo": f"Nivel forte ({toques_max} toques)",
                          "detalhe": f"{testando[0].get('tipo')} em {testando[0].get('nivel')}"})
        elif toques_max >= 2:
            score += 10
            lista.append({"peso": 10, "titulo": f"Duplo {testando[0].get('tipo')}",
                          "detalhe": f"em {testando[0].get('nivel')}"})
    # +15 banco historico (confirmacao) forte
    conf = (leitura or {}).get("confirmacao") or {}
    if isinstance(conf, dict):
        sc = conf.get("score") or 0
        if sc >= 65:
            score += 15
            lista.append({"peso": 15, "titulo": f"Historico forte ({sc}%)",
                          "detalhe": conf.get("veredito") or "confirmado"})
        elif sc >= 50:
            score += 8
            lista.append({"peso": 8, "titulo": f"Historico neutro ({sc}%)",
                          "detalhe": conf.get("veredito") or "misto"})
    # +10 momentum das ultimas 3 velas do TF de operacao
    tf_op = str((leitura or {}).get("tf_op") or "").lower()
    mtf_op = momentum_tfs.get(tf_op) if tf_op else None
    if mtf_op:
        rec = str(mtf_op.get("recentes") or "").lower()
        if dir_pt in rec and "consecut" in rec:
            score += 10
            lista.append({"peso": 10, "titulo": "Momentum recente",
                          "detalhe": mtf_op.get("recentes")})
    # +10 veredito da analise cruzada alinhado
    if veredito and str(veredito.get("sinal") or "").lower() == "alinhado":
        score += 10
        lista.append({"peso": 10, "titulo": "Analise cruzada ALINHADA",
                      "detalhe": veredito.get("veredito") or ""})
    return {"score": min(100, score), "confluencias": lista}


def _score_para_estrelas(score):
    if score >= 85: return 5
    if score >= 70: return 4
    if score >= 55: return 3
    if score >= 40: return 2
    return 1


# ──────────────────────────────────────────────────────────────────────────
#  CIRCUIT BREAKERS (protegem o dinheiro do usuario)
# ──────────────────────────────────────────────────────────────────────────

def _circuit_state_do_dia(bot_id, equity_atual):
    """Mantem estado do dia por bot: equity de inicio, contagem de operacoes.
    Reseta automaticamente quando a data muda."""
    from datetime import date
    hoje = date.today().isoformat()
    st = _CIRCUIT_STATE.get(bot_id)
    if not st or st.get("data_ref") != hoje:
        st = {
            "data_ref": hoje,
            "equity_inicio_dia": equity_atual if equity_atual else 0,
            "ops_hoje": 0,
            "ultima_op_ts": 0,
        }
        _CIRCUIT_STATE[bot_id] = st
    # se ainda nao tinha equity e agora tem, seta
    if not st["equity_inicio_dia"] and equity_atual:
        st["equity_inicio_dia"] = equity_atual
    return st


def _check_pode_operar(bot, config, snap):
    """Retorna (pode_bool, motivo). Se pode=False, motivo explica o que barrou."""
    if config.get("pausado"):
        return False, "bot pausado manualmente"
    if bot.get("posicoes_abertas") and int(bot.get("posicoes_abertas") or 0) > 0:
        return False, "ja tem posicao aberta"
    bot_id = bot.get("id")
    equity = float(snap.get("equity") or 0) if snap else 0
    st = _circuit_state_do_dia(bot_id, equity)
    # cooldown entre operacoes do mesmo bot
    import time
    if time.time() - float(st.get("ultima_op_ts") or 0) < _OPORT_COOLDOWN_SEG:
        return False, "cooldown entre operacoes"
    # max operacoes no dia
    max_dia = int(config.get("max_operacoes_dia") or 10)
    if st["ops_hoje"] >= max_dia:
        return False, f"limite diario de {max_dia} operacoes atingido"
    # drawdown maximo diario
    dd_max = float(config.get("drawdown_max_dia") or 5.0)
    if st["equity_inicio_dia"] and equity:
        dd_atual = (st["equity_inicio_dia"] - equity) / st["equity_inicio_dia"] * 100
        if dd_atual >= dd_max:
            return False, f"drawdown ({dd_atual:.1f}%) atingiu limite ({dd_max}%)"
    return True, "ok"


# ──────────────────────────────────────────────────────────────────────────
#  NARRADOR IA (custo baixo — so quando ha oportunidade real)
# ──────────────────────────────────────────────────────────────────────────

def _narrar_oportunidade_ia(direcao_info, niveis, confluencias_info, leitura):
    """Chama Haiku pra formatar a oportunidade em texto de trader profissional.
    Custo ~$0.0005 por chamada. So chamado quando ja passou pelo filtro de
    estrelas — evita gastar tokens em setup fraco."""
    import sys
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        # fallback determinístico se nao ha IA
        return (f"{direcao_info['direcao'].upper()} em {niveis['entrada']} — "
                f"stop {niveis['stop']}, alvo {niveis['alvo1']} (R:R {niveis['rr']}). "
                f"{len(confluencias_info['confluencias'])} confluencias somam {confluencias_info['score']} pontos.")
    idioma = (leitura or {}).get("idioma") or "pt"
    idioma_nome = _IDIOMA_NOME.get(idioma, "portugues brasileiro")
    try:
        import httpx
        confs = "; ".join(f"{c['titulo']} ({c['peso']}pts): {c.get('detalhe','')}"
                          for c in (confluencias_info.get("confluencias") or [])[:5])
        sistema = (
            "Voce e um analista de trading escrevendo o plano de entrada de uma OPORTUNIDADE detectada. "
            "Escreva EM " + idioma_nome + ", 2 a 3 frases curtas (max ~280 caracteres), sem markdown. "
            "Tom: pratico, direto, tecnico. Comece afirmando A DIRECAO e O CENARIO. Depois cite a "
            "confluencia MAIS FORTE. Encerre com o gatilho concreto (entrada, stop, alvo). "
            "PROIBIDO: promessas de lucro, previsoes, palavras como 'vai', 'garante', 'certamente'. "
            "PERMITIDO: 'pode', 'tende', 'favorece', 'aumenta a probabilidade'."
        )
        contexto = {
            "direcao": direcao_info["direcao"],
            "cenario": direcao_info.get("cenario"),
            "entrada": niveis["entrada"],
            "stop": niveis["stop"],
            "alvo1": niveis["alvo1"],
            "rr": niveis["rr"],
            "risco_pts": niveis["risco_pts"],
            "score_confluencia": confluencias_info["score"],
            "confluencias": confs,
        }
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": os.environ.get("RADAR_IA_MODELO", "claude-haiku-4-5-20251001"),
                "max_tokens": 200,
                "temperature": 0.6,
                "system": sistema,
                "messages": [{"role": "user", "content":
                    "Oportunidade detectada:\n" + json.dumps(contexto, ensure_ascii=False)}],
            },
            timeout=8.0,
        )
        if r.status_code != 200:
            print(f"NARRAR OPORT status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        return texto[:400] if texto else None
    except Exception as e:
        print(f"NARRAR OPORT erro: {e}", file=sys.stderr)
        return None


# ──────────────────────────────────────────────────────────────────────────
#  ORQUESTRADOR — junta tudo, retorna oportunidade OU None
# ──────────────────────────────────────────────────────────────────────────

def _cooldown_oport_ativo(bot_id):
    """Ha uma oportunidade recente pro mesmo bot? Evita spam de setups."""
    import time
    hist = _oportunidade_hist(bot_id)
    if not hist: return False
    ultima = hist[-1]
    try:
        ts = _dt.fromisoformat(str(ultima.get("ts") or "").replace("Z", "+00:00"))
        return (_dt.now(_tz.utc) - ts).total_seconds() < _OPORT_COOLDOWN_SEG
    except Exception:
        return False


def _detectar_oportunidade(sb, bot, fatos, leitura, veredito=None, snap_dict=None):
    """Orquestra: config -> circuit -> direcao -> niveis -> confluencias ->
    estrelas -> limiar do modo -> IA narra -> registra. Silencioso e barato:
    detectores rodam sempre, IA so quando merece."""
    if not bot or not fatos: return None
    bot_id = bot.get("id")
    if not bot_id: return None
    config = _bot_config_get(bot_id)
    if config["modo_operacional"] == "observar":
        return None  # observar nao dispara nada
    # cooldown pra nao spamar oportunidades identicas
    if _cooldown_oport_ativo(bot_id):
        return None
    # circuit breakers
    pode, motivo = _check_pode_operar(bot, config, snap_dict or {})
    if not pode:
        return None
    # direcao
    direcao_info = _detectar_direcao_potencial(fatos, leitura)
    if not direcao_info: return None
    # niveis
    niveis = _calcular_niveis_operacao(direcao_info, fatos)
    if not niveis: return None
    # confluencias
    confl = _calcular_confluencias(direcao_info, fatos, leitura, veredito)
    estrelas = _score_para_estrelas(confl["score"])
    # limiar do modo
    limiar = _ESTRELAS_LIMIAR_POR_MODO.get(config["modo_sensibilidade"], 4)
    if estrelas < limiar:
        return None
    # passou! narra e registra
    explicacao = _narrar_oportunidade_ia(direcao_info, niveis, confl, leitura)
    oport = {
        "bot_id":         bot_id,
        "user_id":        bot.get("user_id"),
        "direcao":        direcao_info["direcao"],
        "cenario":        direcao_info.get("cenario"),
        "entrada":        niveis["entrada"],
        "stop":           niveis["stop"],
        "alvo1":          niveis["alvo1"],
        "alvo2":          niveis["alvo2"],
        "risco_pts":      niveis["risco_pts"],
        "potencial_pts":  niveis["potencial_pts"],
        "rr":             niveis["rr"],
        "score":          confl["score"],
        "estrelas":       estrelas,
        "confluencias":   confl["confluencias"],
        "explicacao":     explicacao,
        "modo_gerado":    config["modo_operacional"],
        "status":         "detectada",
    }
    oport = _oport_push(bot_id, oport)
    # MODO AUTOMATICO: cria comando via /mt5/comando internamente
    if (config["modo_operacional"] == "automatico"
            and estrelas >= int(config.get("estrelas_min_auto") or 4)):
        try:
            _executar_oportunidade_auto(sb, bot, oport, config)
        except Exception as _e:
            try: print(f"[oport auto] {_e}")
            except Exception: pass
    return oport


def _executar_oportunidade_auto(sb, bot, oport, config):
    """Cria um comando MT5 partindo direto da oportunidade detectada em modo
    automatico. Chamado internamente — nao expoe via UI."""
    if not sb: return
    lote = float(config.get("lote_padrao") or 0.01)
    tipo = "buy" if oport["direcao"] == "long" else "sell"
    params = {"lote": lote, "sl": oport["stop"], "tp": oport["alvo1"]}
    linha = {
        "bot_token": bot.get("bot_token"),
        "user_id":   bot.get("user_id"),
        "bot_id":    bot.get("id"),
        "tipo":      tipo,
        "params":    params,
        "status":    "pendente",
        "origem":    "auto_detector",
    }
    try:
        r = sb.table("mt5_comandos").insert(linha).execute()
        cmd = (r.data or [{}])[0]
        oport["comando_id"] = cmd.get("id")
        oport["status"] = "auto_executada"
        # atualiza circuit state (contagem de op)
        import time
        st = _CIRCUIT_STATE.get(bot.get("id")) or {}
        st["ops_hoje"] = int(st.get("ops_hoje") or 0) + 1
        st["ultima_op_ts"] = time.time()
        _CIRCUIT_STATE[bot.get("id")] = st
        # v6.76 — BabyMachine registra a decisao com contexto (non-blocking)
        try:
            _leit_bm = _anl_ler_leitura(sb, bot.get("user_id"), bot.get("id"))
            _bm_registrar_do_detector(sb, bot, oport, _leit_bm, None,
                                      cmd.get("id"), "detector_auto")
        except Exception as _e2:
            try: print(f"[bm auto] {_e2}")
            except Exception: pass
    except Exception as _e:
        try: print(f"[auto comando] {_e}")
        except Exception: pass


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
    """Gera bot_token p/ o conector. Nunca pede credenciais de corretora.

    IDENTIDADE ESTÁVEL (multi-bot): se já existe um bot ATIVO com o MESMO nome pra
    este usuário, REUSA o token dele em vez de criar outro. Assim o magic (derivado
    do token) NÃO muda entre reenvios — o EA que já está no gráfico continua batendo
    com o token da sessão, e a trilha/monitor reconhecem o bot mesmo que ele seja de
    um envio anterior. Sem isso, cada 'Enviar' criava um bot/token/magic novo e o
    snapshot do gráfico ia parar num token que a trilha não vigiava."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    nome = (req.nome or "Meu Bot").strip() or "Meu Bot"
    # reusa o bot ATIVO mais recente com o mesmo nome (mesmo usuário)
    try:
        ex = (sb.table("conector_bots").select("*")
              .eq("user_id", req.user_id).eq("nome", nome)
              .order("criado_em", desc=True).limit(10).execute())
        vivo = next((b for b in (ex.data or []) if not b.get("excluido")), None)
    except Exception:
        vivo = None
    if vivo and (vivo.get("bot_token") or "").strip():
        try:
            sb.table("conector_bots").update({
                "simbolo": req.simbolo, "magic_number": req.magic_number,
            }).eq("id", vivo["id"]).execute()
        except Exception:
            pass
        return {"ok": True, "bot_token": vivo["bot_token"], "reusado": True,
                "instrucao": "Bot já existente — mesmo token de antes (identidade estável)."}
    token = _secrets.token_hex(16)
    try:
        sb.table("conector_bots").insert({
            "user_id": req.user_id, "bot_token": token,
            "nome": nome, "simbolo": req.simbolo,
            "magic_number": req.magic_number,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao registrar bot: {e}")
    return {"ok": True, "bot_token": token, "reusado": False,
            "instrucao": "Cole este token no conector (config). Ele identifica o bot — nunca compartilhe."}


# ── VISÃO → REGIME: sintetiza o regime a partir do mapa de zonas cruas ──────
# "As duas juntas": o EA manda o CRU (posição do preço no canal EMA H/L por TF),
# a nuvem sintetiza aqui o regime — de graça, sem yfinance, usando o dado VIVO da
# corretora (o que o bot realmente vê). Top-down (regra do Adriano): a TENDÊNCIA
# é ancorada pelos tempos MAIORES (60m/4h/D — lentos, definem o regime), e a
# VIRADA é liderada pelos MENORES (1m/5m/15m — os menores confirmam antes dos
# maiores). Sem sobreposição, pra o sinal de virada não poluir a tendência.
_BT_ZONAS_ANCORA = ("z60", "z240", "zD")   # tendência estabelecida (top-down)
_BT_ZONAS_FAST   = ("z1", "z5", "z15")     # lideram a virada

# ═══ CAPÍTULO 1 DA INTELIGÊNCIA DINÂMICA (v6.48): CONFIRMAÇÃO CONTEXTUAL ═══
# O bot vê o cenário se formando (padrão + regime + zonas + nível); esta camada
# pergunta ao NOSSO banco o que esse cenário significou historicamente e devolve
# um veredito citável + score transparente. Regra da casa: ocorrências MEDIDAS,
# nunca promessa; amostra pequena é dita como amostra pequena.
_CONFIRM_CACHE = {}                 # (ativo_catalogo, tf, padrao) -> {"stats", "ts"}
_CONFIRM_TTL_S = 24 * 3600          # estatística de padrão muda devagar: 1x/dia basta
_CONFIRM_TF_PERIODO = {"5m": "6 meses", "15m": "6 meses", "30m": "6 meses",
                       "1h": "1 ano", "4h": "2 anos", "1d": "2 anos"}


def _confirm_stats_padrao(ativo_catalogo: str, tf: str, padrao: str):
    """Estatística histórica do padrão neste ativo/TF — computada 1x/dia por
    combo (cache) reusando a MESMA engine do OffMind (analisar_padrao, alvo/stop
    por ATR). Devolve {ocorrencias, acerto_5v, acerto_10v} ou None (ex.: 1m não
    tem loader — sem estatística é sem estatística, não se inventa)."""
    if tf not in _CONFIRM_TF_PERIODO or padrao not in PADROES_OFFMIND:
        return None
    chave = (ativo_catalogo, tf, padrao)
    ag = _time_mt5.time()
    hit = _CONFIRM_CACHE.get(chave)
    if hit and (ag - hit["ts"]) < _CONFIRM_TTL_S:
        return hit["stats"]
    try:
        df = baixar_dados(ativo_catalogo, _CONFIRM_TF_PERIODO[tf], tf)
        if df is None or len(df) < 60:
            return None
        r = analisar_padrao(df, PADROES_OFFMIND[padrao]["fn"], [5, 10])
        hz = {h["horizonte"]: h for h in r.get("por_horizonte", [])}
        stats = {"ocorrencias": int(r.get("total_ocorrencias") or 0),
                 "acerto_5v": (hz.get(5) or {}).get("taxa_acerto"),
                 "acerto_10v": (hz.get(10) or {}).get("taxa_acerto"),
                 "medidas_5v": (hz.get(5) or {}).get("ocorrencias_medidas") or 0}
        _CONFIRM_CACHE[chave] = {"stats": stats, "ts": ag}
        return stats
    except Exception as _e:
        print(f"[confirmacao] stats {chave}: {_e}")
        return None


def _confirmacao_contextual(det: dict, simbolo: str):
    """Junta os dois lados: o cenário que o bot está vendo AGORA + o que o banco
    mediu sobre ele. Score 0-100 transparente e explicado no próprio veredito:
    base 50 · alinhamento padrão×regime ±20 · acerto histórico ±18 · estratégia
    mapeada com PF>1 no ativo ±8 · amostra <20 trava o teto em 65."""
    om = det.get("offmind") or {}
    padroes = om.get("padroes") or []
    regime = det.get("regime") or {}
    if not padroes:
        return None                          # sem padrão formando, nada a confirmar
    p = padroes[0]                           # o padrão mais rápido em formação
    ativo_cat = _MT5_PARA_CATALOGO.get((simbolo or "").upper().replace("/", ""))
    estado = str(regime.get("estado") or "").lower()
    dir_p = str(p.get("direcao") or "").lower()
    a_favor = None
    if estado in ("compra", "alta") or estado in ("venda", "baixa"):
        favoravel = ("alta" in dir_p or "compra" in dir_p) if estado in ("compra", "alta") \
                    else ("baixa" in dir_p or "venda" in dir_p)
        a_favor = bool(favoravel)
    stats = _confirm_stats_padrao(ativo_cat, p.get("tf"), p.get("padrao")) if ativo_cat else None
    testando = [e for e in (om.get("estrutura") or []) if e.get("testando")]
    score = 50.0
    partes = []
    if a_favor is True:
        score += 20; partes.append("padrão a favor do regime (+20)")
    elif a_favor is False:
        score -= 20; partes.append("padrão CONTRA o regime (-20)")
    if stats and stats.get("acerto_5v") is not None:
        aj = max(-18.0, min(18.0, (float(stats["acerto_5v"]) - 50.0) * 0.6))
        score += aj
        partes.append(f"acerto histórico 5v {stats['acerto_5v']:.0f}% ({aj:+.0f})")
    if testando:
        partes.append(f"testando nível de {testando[0].get('tf')}")
    amostra_pequena = bool(stats and (stats.get("medidas_5v") or 0) < 20)
    if amostra_pequena:
        score = min(score, 65.0)
        partes.append("amostra pequena (teto 65)")
    score = int(round(max(0.0, min(100.0, score))))
    if stats:
        veredito = (f"{p.get('nome') or p.get('padrao')} no {p.get('tf')}: medido "
                    f"{stats.get('medidas_5v', 0)}x neste ativo/TF, "
                    f"{(stats.get('acerto_5v') or 0):.0f}% confirmou em 5 velas"
                    + (" — amostra pequena" if amostra_pequena else ""))
    else:
        veredito = (f"{p.get('nome') or p.get('padrao')} no {p.get('tf')}: sem estatística "
                    f"histórica disponível pra este ativo/TF — leitura só estrutural")
    return {"score": score, "veredito": veredito, "fatores": partes,
            "contexto": {"padrao": p.get("padrao"), "tf": p.get("tf"),
                         "direcao": p.get("direcao"), "regime": regime.get("estado"),
                         "testando_nivel": bool(testando)}}


def _regime_das_zonas(det: dict) -> Optional[dict]:
    """Recebe o detalhe do snapshot (zonas como strings acima/dentro/abaixo/?).
    Devolve {regime, estado, virada, confianca, ...} ou None se não há âncora
    suficiente. Puro (sem I/O) — roda a cada snapshot sem custo.
    Conservador: só chama tendência com maioria clara da âncora, e só sinaliza
    virada quando há tendência estabelecida E os rápidos viraram contra ela."""
    if not isinstance(det, dict):
        return None
    def _z(k):
        v = det.get(k)
        return v.strip().lower() if isinstance(v, str) else None
    anc = {k: _z(k) for k in _BT_ZONAS_ANCORA}
    validos = [v for v in anc.values() if v in ("acima", "dentro", "abaixo")]
    if len(validos) < 2:
        return None  # âncora não pronta (TF sem histórico) → sem regime
    acima  = sum(1 for v in anc.values() if v == "acima")
    abaixo = sum(1 for v in anc.values() if v == "abaixo")
    n = len(validos)
    # tendência pela âncora (maioria clara; senão lateral)
    regime = "lateral"
    if acima > abaixo and acima >= 2:
        regime = "tendencia_alta"
    elif abaixo > acima and abaixo >= 2:
        regime = "tendencia_baixa"
    # virada: os rápidos (1m/5m/15m) viraram CONTRA a tendência da âncora
    af = sum(1 for k in _BT_ZONAS_FAST if _z(k) == "acima")
    bf = sum(1 for k in _BT_ZONAS_FAST if _z(k) == "abaixo")
    virada = None
    if regime == "tendencia_alta" and bf >= 2 and af == 0:
        virada = "possivel_virada_baixa"
    elif regime == "tendencia_baixa" and af >= 2 and bf == 0:
        virada = "possivel_virada_alta"
    estado = virada or regime
    conf = int(round(100 * max(acima, abaixo) / n)) if regime != "lateral" else 0
    return {"regime": regime, "estado": estado, "virada": bool(virada),
            "confianca": conf, "acima": acima, "abaixo": abaixo, "ancoras_validas": n}


# ── OFFMIND AO VIVO: lê os candles reais que o bot mandou e enxerga o que o bot
# não vê — padrões se FORMANDO na borda (mecânica 1m/5m/15m) e níveis de
# suporte/resistência sendo testados (estrutura 30m/60m/4h). Roda sobre o dado
# da CORRETORA (sintonia: IA e bot no mesmo candle), puro (sem yfinance), só
# quando a leva de candles chega (~1x/min). Reusa os detectores do OffMind.
_BT_TF_MECANICA  = (("c1m", "1m"), ("c5m", "5m"), ("c15m", "15m"))     # gatilho entrada/saida
_BT_TF_ESTRUTURA = (("c30m", "30m"), ("c60m", "60m"), ("c4h", "4h"))   # fundo/topo

def _bt_parse_candles(s):
    """v6.72 — aceita 'o,h,l,c' (bots velhos) OU 'o,h,l,c,v' (bots v6.72+).
    Retorna DataFrame com Open/High/Low/Close (+ Volume se disponível)."""
    if not isinstance(s, str) or not s.strip():
        return None
    linhas4, linhas5 = [], []
    for parte in s.split(";"):
        vs = parte.split(",")
        try:
            if len(vs) == 5:
                linhas5.append([float(x) for x in vs])
            elif len(vs) == 4:
                linhas4.append([float(x) for x in vs])
        except Exception:
            continue
    if linhas5 and len(linhas5) >= 2:
        return pd.DataFrame(linhas5, columns=["Open", "High", "Low", "Close", "Volume"])
    if linhas4 and len(linhas4) >= 2:
        return pd.DataFrame(linhas4, columns=["Open", "High", "Low", "Close"])
    return None

def _bt_niveis_sr(df, tol_frac=0.0015, min_toques=2, max_niveis=3):
    """Níveis horizontais (suporte pelos mínimos, resistência pelos máximos)
    tocados >= min_toques na janela; marca se o preço atual está TESTANDO um.
    Clusterização 1D simples por tolerância relativa ao preço."""
    if df is None or len(df) < 4:
        return []
    preco = float(df["Close"].iloc[-1])
    tol = max(preco * tol_frac, 1e-9)
    def _cluster(vals):
        vals = sorted(float(v) for v in vals)
        cl = []
        for v in vals:
            if cl and abs(v - cl[-1]["soma"] / cl[-1]["n"]) <= tol:
                cl[-1]["soma"] += v; cl[-1]["n"] += 1
            else:
                cl.append({"soma": v, "n": 1})
        return [{"nivel": round(c["soma"] / c["n"], 5), "toques": c["n"]}
                for c in cl if c["n"] >= min_toques]
    out = []
    for s in _cluster(df["Low"].tolist()):
        out.append({"tipo": "suporte", "nivel": s["nivel"], "toques": s["toques"],
                    "testando": abs(preco - s["nivel"]) <= tol})
    for r in _cluster(df["High"].tolist()):
        out.append({"tipo": "resistencia", "nivel": r["nivel"], "toques": r["toques"],
                    "testando": abs(preco - r["nivel"]) <= tol})
    # prioriza os que estão sendo testados agora, depois por nº de toques
    out.sort(key=lambda x: (not x["testando"], -x["toques"]))
    return out[:max_niveis]

def _offmind_ao_vivo(det: dict) -> Optional[dict]:
    """Roda os detectores do OffMind sobre as janelas de candle do bot.
    Devolve {padroes, estrutura} ou None se não há candles. 'padroes' = padrão
    se formando na ÚLTIMA vela dos TFs de mecânica; 'estrutura' = níveis S/R
    testados nos TFs de estrutura. Honesto: reporta o que ESTÁ se formando —
    a estatística histórica é anexada depois (não prevê o futuro aqui)."""
    if not isinstance(det, dict):
        return None
    padroes = []
    for chave, tf in _BT_TF_MECANICA:
        df = _bt_parse_candles(det.get(chave))
        if df is None or len(df) < 4:
            continue
        ult = len(df) - 1
        for pk, meta in PADROES_OFFMIND.items():
            try:
                ocorr = meta["fn"](df)
            except Exception:
                continue
            # padrão fechando na ÚLTIMA vela = formando agora
            if any(idx == ult for (idx, _dir) in ocorr):
                direc = next(d for (i, d) in ocorr if i == ult)
                padroes.append({"tf": tf, "padrao": pk, "nome": meta["nome"], "direcao": direc})
    estrutura = []
    for chave, tf in _BT_TF_ESTRUTURA:
        df = _bt_parse_candles(det.get(chave))
        niveis = _bt_niveis_sr(df)
        for nv in niveis:
            estrutura.append({"tf": tf, **nv})
    if not padroes and not estrutura:
        return None
    testando = [e for e in estrutura if e.get("testando")]
    return {"padroes": padroes, "estrutura": estrutura,
            "resumo": {"padroes_formando": len(padroes),
                       "testando_nivel": len(testando)}}


# ── IA GERENCIADORA (o maestro): junta regime + padrão + estrutura e traduz numa
# LEITURA acionável, propondo entre as estratégias que o usuário JÁ APROVOU.
# Read-only: é uma leitura pro copiloto/monitor — NÃO comanda o bot (o canal
# nuvem→EA continua fora de escopo, por segurança). Dispara por EVENTO (a maioria
# dos snapshots não gera leitura) e tem cooldown — controle de custo e de ruído.
# Determinística e auditável; a IA em linguagem natural pode narrar isto depois.
def _gatilho_leitura(regime: Optional[dict], offmind: Optional[dict]) -> Optional[dict]:
    """Decide se o momento merece leitura. Conservador de propósito."""
    if not offmind:
        if regime and regime.get("virada"):
            return {"tipo": "virada", "motivo": f"Regime sinalizou {regime.get('estado')}"}
        return None
    padroes = offmind.get("padroes") or []
    testando = [e for e in (offmind.get("estrutura") or []) if e.get("testando")]
    if padroes and testando:
        return {"tipo": "reversao_em_nivel",
                "motivo": "Padrão formando com o preço testando um nível de estrutura"}
    if padroes and regime and regime.get("virada"):
        return {"tipo": "virada_confirmada",
                "motivo": "Padrão formando junto de uma virada de regime"}
    if regime and regime.get("virada"):
        return {"tipo": "virada", "motivo": f"Regime {regime.get('estado')}"}
    return None

def _mapear_estrategia(gatilho: dict, offmind: Optional[dict]) -> list:
    """Mapeia a situação ao vivo → estratégia(s) PRÉ-APROVADAS que casam.
    Nunca inventa gatilho: aponta entre as estratégias da galeria (ESTRATEGIAS_PRONTAS)."""
    tipo = gatilho.get("tipo")
    if tipo == "reversao_em_nivel":
        ids = ["topo_fundo_duplo", "sr_dia_anterior", "bollinger_reversao"]
    elif tipo in ("virada_confirmada", "virada"):
        ids = ["engolfo_tendencia", "rsi_reversao"]
    else:
        ids = []
    nome = {e["id"]: e["nome"] for e in ESTRATEGIAS_PRONTAS}
    return [{"id": i, "nome": nome.get(i, i)} for i in ids if i in nome]

def _leitura_ao_vivo(gat: dict, regime: Optional[dict], offmind: Optional[dict],
                     snap) -> dict:
    """Leitura estruturada do gerente: o que está se formando + estratégia
    aprovada que casa + contexto. Regra pura (custo zero, auditável)."""
    padroes = (offmind or {}).get("padroes") or []
    testando = [e for e in ((offmind or {}).get("estrutura") or []) if e.get("testando")]
    ests = _mapear_estrategia(gat, offmind)
    simbolo = getattr(snap, "simbolo", "") or ""
    reg = (regime or {}).get("estado", "?")
    partes = []
    if padroes:
        p = padroes[0]
        partes.append(f"{p['nome']} formando no {p['tf']} (direção {p['direcao']})")
    if testando:
        t = testando[0]
        partes.append(f"preço testando {t['tipo']} em {t['nivel']} no {t['tf']} ({t['toques']} toques)")
    partes.append(f"regime {reg}")
    contexto = "; ".join(partes)
    nomes = ", ".join(e["nome"] for e in ests)
    texto = (f"{simbolo}: {contexto}. "
             + (f"Setup compatível com estratégia(s) que você aprovou: {nomes}. " if ests else "")
             + "Leitura ao vivo — histórico medido, não promessa; a decisão é sua e do bot.")
    return {"gatilho": gat, "simbolo": simbolo, "contexto": contexto,
            "estrategias_sugeridas": ests, "texto": texto}


@app.post("/conector/snapshot")
def conector_snapshot(snap: ConectorSnapshot):
    """Recebe snapshot read-only do conector. Atualiza ping, grava e roda o agente."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    bot = _bot_por_token(sb, snap.bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    # MULTI-BOT — guarda contra snapshot entregue no token ERRADO. O magic que o
    # EA imprime é derivado do token (determinístico). Se o snapshot chega com um
    # magic que NÃO bate com este bot, ele é de OUTRO bot do mesmo usuário (outro
    # gráfico) e foi roteado pro token errado. Ignora: NÃO atualiza ping/posições —
    # senão a trilha acende "Operar" pra um bot que nem está no gráfico ainda.
    _magic_rec = int(getattr(snap, "magic_number", 0) or 0)
    if _magic_rec and _magic_rec != _magic_do_token(bot.get("bot_token") or snap.bot_token):
        return {"ok": True,
                "ignorado": "magic nao confere com o bot (snapshot de outro bot)",
                "sugestoes_novas": []}
    user_id = bot.get("user_id")
    agora = _dt.now(_tz.utc).isoformat()
    # ── VISÃO → REGIME: sintetiza a partir das zonas cruas (as duas juntas) ──
    det = dict(snap.detalhe or {})
    regime = _regime_das_zonas(det)
    if regime:
        det["regime"] = regime                       # cru + sintetizado no mesmo JSON
    # ── OFFMIND AO VIVO: só quando a leva de candles chega (~1x/min) ──
    if any(k in det for k, _ in _BT_TF_MECANICA) or any(k in det for k, _ in _BT_TF_ESTRUTURA):
        try:
            om = _offmind_ao_vivo(det)
            if om:
                det["offmind"] = om                  # padrões + estrutura ao vivo
        except Exception as _e:
            import sys as _sys
            print(f"[offmind vivo] {_e}", file=_sys.stderr)
    # ── CONFIRMAÇÃO CONTEXTUAL (v6.48): cenário de agora × banco histórico ──
    try:
        conf = _confirmacao_contextual(det, snap.simbolo)
        if conf:
            det["confirmacao"] = conf
    except Exception as _e:
        import sys as _sys
        print(f"[confirmacao] {_e}", file=_sys.stderr)
    # reaproveita a coluna ultima_direcao/direcao_d1 (vinha vazia) pro estado do regime
    direcao_final = (regime or {}).get("estado") or snap.direcao_d1
    # ── IA GERENCIADORA: leitura acionável por EVENTO (com cooldown) ──
    # Read-only: vira sugestão no monitor, NÃO comanda o bot.
    try:
        gat = _gatilho_leitura(regime, det.get("offmind"))
        if gat and not _agente_em_cooldown(sb, user_id, "LEITURA"):
            leitura = _leitura_ao_vivo(gat, regime, det.get("offmind"), snap)
            det["leitura"] = leitura
            _agente_emite(sb, user_id, "LEITURA", "operacao",
                          leitura["texto"], "info", leitura)
    except Exception as _e:
        import sys as _sys
        print(f"[leitura ao vivo] {_e}", file=_sys.stderr)
    try:
        # v6.53: só atualiza os campos que VIERAM no snapshot — snapshot velho
        # (bots pré-v6.37 sem "lucro=") não deve mais sobrescrever com NULL o
        # que um snapshot novo escreveu antes. Ping e posições sempre vão.
        _upd = {"ultimo_ping": agora, "posicoes_abertas": snap.posicoes_abertas}
        if snap.equity is not None:         _upd["ultimo_equity"] = snap.equity
        if snap.drawdown_atual is not None: _upd["ultimo_dd"] = snap.drawdown_atual
        if direcao_final is not None:       _upd["ultima_direcao"] = direcao_final
        if snap.padrao_ativo is not None:   _upd["ultimo_padrao"] = snap.padrao_ativo
        sb.table("conector_bots").update(_upd).eq("id", bot["id"]).execute()
        sb.table("conector_snapshots").insert({
            "user_id": user_id, "bot_token": snap.bot_token,
            "conta_login": snap.conta_login, "corretora": snap.corretora,
            "simbolo": snap.simbolo, "magic_number": snap.magic_number,
            "equity": snap.equity, "balance": snap.balance,
            "margem_livre": snap.margem_livre,
            "posicoes_abertas": snap.posicoes_abertas,
            "lucro_flutuante": snap.lucro_flutuante,
            "drawdown_atual": snap.drawdown_atual,
            "direcao_d1": direcao_final, "padrao_ativo": snap.padrao_ativo,
            "detalhe_json": det,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gravar snapshot: {e}")
    novas = _agente_bloco_f(sb, user_id, bot, snap)
    # v6.74 — DETECTOR DE OPORTUNIDADE. Roda 24/7 aqui pra funcionar mesmo com
    # cockpit fechado. Nao chama IA se bot esta em modo observar (~99% dos casos).
    try:
        _leit = _anl_ler_leitura(sb, user_id, bot.get("id"))
        if _leit:
            fatos = _analisar_bot_tecnica(
                None, _leit.get("ema_h"), _leit.get("ema_l"),
                _leit.get("preco"), _leit.get("regime"),
                _leit.get("posicoes"),
                offmind={"padroes": _leit.get("padroes"),
                         "estrutura": (det.get("offmind") or {}).get("estrutura") or []},
            ) or {}
            # complementa fatos com o que o detector precisa
            fatos["regime"] = str((_leit.get("regime") or {}).get("estado") or "").upper()
            fatos["preco"] = _leit.get("preco")
            fatos["distancia_ema_h"] = _leit.get("ema_h")
            fatos["distancia_ema_l"] = _leit.get("ema_l")
            # ultima analise cruzada da IA se houver
            ult_anl = list(_anl_hist(bot.get("id")))[-1:] or [None]
            veredito = ult_anl[0] if ult_anl and ult_anl[0] else None
            _detectar_oportunidade(
                sb, {**bot, "posicoes_abertas": snap.posicoes_abertas},
                fatos, _leit, veredito=veredito,
                snap_dict={"equity": snap.equity},
            )
    except Exception as _e:
        try: print(f"[detector] {_e}")
        except Exception: pass
    return {"ok": True, "sugestoes_novas": novas}


# ════════════════════════════════════════════════════════════════════════════
#  v6.74 — Endpoints do DETECTOR DE OPORTUNIDADE
# ════════════════════════════════════════════════════════════════════════════

class BotConfigIn(BaseModel):
    modo_operacional:   Optional[str] = None   # observar|copiloto|automatico
    modo_sensibilidade: Optional[str] = None   # conservador|moderado|agressivo
    drawdown_max_dia:   Optional[float] = None
    max_operacoes_dia:  Optional[int] = None
    estrelas_min_auto:  Optional[int] = None
    pausado:            Optional[bool] = None
    lote_padrao:        Optional[float] = None


@app.get("/monitor/bot/{bot_id}/config")
def monitor_bot_config_get(bot_id: int):
    """Retorna a config atual do bot (ou defaults conservadores se nunca setado)."""
    return {"config": _bot_config_get(bot_id)}


@app.post("/monitor/bot/{bot_id}/config")
def monitor_bot_config_set(bot_id: int, inp: BotConfigIn):
    """Atualiza config do bot. Campos nao enviados ficam como estao."""
    novo = {}
    for k, v in inp.model_dump(exclude_none=True).items():
        novo[k] = v
    # valida enums
    if "modo_operacional" in novo and novo["modo_operacional"] not in ("observar", "copiloto", "automatico"):
        raise HTTPException(status_code=400, detail="modo_operacional invalido")
    if "modo_sensibilidade" in novo and novo["modo_sensibilidade"] not in ("conservador", "moderado", "agressivo"):
        raise HTTPException(status_code=400, detail="modo_sensibilidade invalido")
    if "estrelas_min_auto" in novo and not (1 <= int(novo["estrelas_min_auto"]) <= 5):
        raise HTTPException(status_code=400, detail="estrelas_min_auto deve ser 1-5")
    cfg = _bot_config_set(bot_id, novo)
    return {"ok": True, "config": cfg}


@app.get("/monitor/bot/{bot_id}/oportunidades")
def monitor_bot_oportunidades(bot_id: int, limite: int = 10):
    """Oportunidades detectadas recentemente pra este bot. Mais novas por ultimo."""
    hist = list(_oportunidade_hist(bot_id))
    limite = max(1, min(50, int(limite)))
    return {"oportunidades": hist[-limite:]}


class OportExecutarIn(BaseModel):
    bot_token: str


@app.post("/monitor/oportunidade/{oport_id}/executar")
def monitor_oportunidade_executar(oport_id: str, inp: OportExecutarIn):
    """Executa uma oportunidade em modo copiloto (usuario clicou Executar).
    Cria comando via /mt5/comando internamente com origem=copiloto."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponivel")
    bot = _bot_por_token(sb, inp.bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token invalido")
    hist = _oportunidade_hist(bot.get("id"))
    oport = next((o for o in hist if o.get("id") == oport_id), None)
    if not oport:
        raise HTTPException(status_code=404, detail="oportunidade nao encontrada")
    if oport.get("status") in ("auto_executada", "executada", "expirada"):
        raise HTTPException(status_code=409, detail=f"oportunidade ja esta {oport.get('status')}")
    config = _bot_config_get(bot.get("id"))
    lote = float(config.get("lote_padrao") or 0.01)
    tipo = "buy" if oport["direcao"] == "long" else "sell"
    try:
        r = sb.table("mt5_comandos").insert({
            "bot_token": inp.bot_token,
            "user_id":   bot.get("user_id"),
            "bot_id":    bot.get("id"),
            "tipo":      tipo,
            "params":    {"lote": lote, "sl": oport["stop"], "tp": oport["alvo1"]},
            "status":    "pendente",
            "origem":    "copiloto",
        }).execute()
        cmd = (r.data or [{}])[0]
        oport["comando_id"] = cmd.get("id")
        oport["status"] = "executada"
        import time
        st = _CIRCUIT_STATE.get(bot.get("id")) or {}
        st["ops_hoje"] = int(st.get("ops_hoje") or 0) + 1
        st["ultima_op_ts"] = time.time()
        _CIRCUIT_STATE[bot.get("id")] = st
        # v6.76 — BabyMachine registra a decisao do copiloto (non-blocking)
        try:
            _leit_bm = _anl_ler_leitura(sb, bot.get("user_id"), bot.get("id"))
            _bm_registrar_do_detector(sb, bot, oport, _leit_bm, None,
                                      cmd.get("id"), "detector_copiloto")
        except Exception as _e2:
            try: print(f"[bm copiloto] {_e2}")
            except Exception: pass
        return {"ok": True, "comando_id": cmd.get("id"), "oportunidade": oport}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao executar: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  v6.73 — CANAL DE COMANDO CLOUD→EA (Sessão 1 do loop fechado)
#
#  Estas rotas fecham o círculo que estava aberto desde o dia 1: a plataforma
#  agora pode MANDAR ordens pro EA (não só receber snapshots). A inteligência
#  que a gente construiu (BOT + IA + veredito + banco) passa a ter mão.
#
#  Fluxo de um comando:
#    1. POST /mt5/comando cria linha com status=pendente na mt5_comandos
#    2. Conector PY faz GET /mt5/comando/pendente a cada 3-5s por bot
#    3. Backend retorna o mais antigo, marca como entregue
#    4. Conector escreve arquivo bt_cmd_<magic>.txt na pasta MQL5/Files
#    5. EA (função BTLerComando injetada) lê, executa, grava bt_ok_<magic>.txt
#    6. Conector lê bt_ok e chama POST /mt5/comando/confirmar
#    7. Backend atualiza status → executado ou falhou
#
#  Circuit breakers básicos (sessão 3 refina):
#    • Bot precisa estar ONLINE (ultimo_ping < OFFLINE_APOS_SEGUNDOS)
#    • MAX_COMANDOS_DIA por bot (protege contra bug em cascata)
#    • Comandos vencidos (expira_em < now()) viram expirado via
#      _mt5_expirar_comandos() (throttle no código pra não rodar toda request)
# ════════════════════════════════════════════════════════════════════════════

MAX_COMANDOS_DIA_POR_BOT = 20  # circuit breaker inicial — sessão 3 refina
_MT5_EXPIRAR_THROTTLE = {"ultimo": 0.0}
_MT5_TIPOS_VALIDOS = {"buy", "sell", "close", "close_all",
                      "mover_sl", "mover_tp", "cancelar"}


class MT5ComandoIn(BaseModel):
    bot_token: str
    tipo: str
    params: dict = {}
    origem: str = "manual"        # manual | copiloto | auto_detector | admin


class MT5ComandoConfirmIn(BaseModel):
    comando_id: int
    sucesso: bool
    resultado: dict = {}          # {ticket, preco_real, erro}


def _mt5_expirar_throttled(sb):
    """Chama _mt5_expirar_comandos() no Supabase no máximo 1x por 30s.
    Comandos expirados NÃO são urgência — throttle protege o banco."""
    import time
    agora = time.time()
    if agora - _MT5_EXPIRAR_THROTTLE["ultimo"] < 30:
        return
    _MT5_EXPIRAR_THROTTLE["ultimo"] = agora
    try:
        sb.rpc("_mt5_expirar_comandos").execute()
    except Exception as _e:
        try: print(f"[mt5 expirar] {_e}")
        except Exception: pass


def _mt5_bot_online(bot: dict) -> bool:
    """Bot precisa estar emitindo snapshots recentes pra receber comandos.
    Sem essa checagem, poderíamos criar comando pra bot morto."""
    ping = bot.get("ultimo_ping")
    if not ping: return False
    try:
        p = _dt.fromisoformat(str(ping).replace("Z", "+00:00"))
        return (_dt.now(_tz.utc) - p).total_seconds() < OFFLINE_APOS_SEGUNDOS
    except Exception:
        return False


def _mt5_contar_comandos_dia(sb, bot_id: int) -> int:
    """Conta comandos criados nas últimas 24h pro bot. Base do circuit breaker."""
    try:
        desde = (_dt.now(_tz.utc) - timedelta(days=1)).isoformat()
        r = (sb.table("mt5_comandos")
             .select("id", count="exact")
             .eq("bot_id", bot_id)
             .gte("criado_em", desde)
             .execute())
        return int(getattr(r, "count", None) or len(r.data or []))
    except Exception:
        return 0


@app.post("/mt5/comando")
def mt5_comando_criar(inp: MT5ComandoIn):
    """Cria um comando na fila pra ser puxado pelo conector PY. Valida bot
    online, tipo suportado, e limite diário. UI, detector automático e admin
    usam este mesmo endpoint — diferença fica em 'origem'."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponivel")
    tipo = (inp.tipo or "").lower().strip()
    if tipo not in _MT5_TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"tipo invalido (validos: {sorted(_MT5_TIPOS_VALIDOS)})")
    bot = _bot_por_token(sb, inp.bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token invalido")
    # Bot precisa estar online — sem ping recente, comando fica pendurado
    if not _mt5_bot_online(bot):
        raise HTTPException(status_code=409, detail="bot offline — nao emite snapshot ha mais de 45s")
    # Circuit breaker: limite de comandos por dia por bot (sessao 3 refina)
    if _mt5_contar_comandos_dia(sb, bot.get("id")) >= MAX_COMANDOS_DIA_POR_BOT:
        raise HTTPException(status_code=429, detail=f"limite diario de {MAX_COMANDOS_DIA_POR_BOT} comandos atingido")
    origem = (inp.origem or "manual").lower().strip()
    if origem not in ("manual", "copiloto", "auto_detector", "admin"):
        origem = "manual"
    linha = {
        "bot_token": inp.bot_token,
        "user_id": bot.get("user_id"),
        "bot_id": bot.get("id"),
        "tipo": tipo,
        "params": inp.params or {},
        "status": "pendente",
        "origem": origem,
    }
    try:
        r = sb.table("mt5_comandos").insert(linha).execute()
        criado = (r.data or [{}])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao criar comando: {e}")
    _mt5_expirar_throttled(sb)
    return {"ok": True, "comando_id": criado.get("id"), "status": criado.get("status"), "expira_em": criado.get("expira_em")}


@app.get("/mt5/comando/pendente")
def mt5_comando_pendente(bot_token: str):
    """Poll do conector PY. Retorna o comando pendente mais antigo pra este
    bot e marca como entregue (evita 2 conectores puxarem o mesmo). Se
    nao ha pendente, retorna {comando: null}. Chamado a cada 3-5s por bot."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponivel")
    bot = _bot_por_token(sb, bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token invalido")
    _mt5_expirar_throttled(sb)
    try:
        r = (sb.table("mt5_comandos")
             .select("*")
             .eq("bot_token", bot_token)
             .eq("status", "pendente")
             .order("criado_em")
             .limit(1)
             .execute())
        linhas = r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao buscar comando: {e}")
    if not linhas:
        return {"comando": None}
    cmd = linhas[0]
    # Marca como entregue — evita corrida com outro poll
    try:
        sb.table("mt5_comandos").update({
            "status": "entregue",
            "entregue_em": _dt.now(_tz.utc).isoformat(),
        }).eq("id", cmd["id"]).eq("status", "pendente").execute()
    except Exception:
        pass
    return {"comando": {
        "id": cmd["id"],
        "tipo": cmd["tipo"],
        "params": cmd.get("params") or {},
        "criado_em": cmd.get("criado_em"),
        "expira_em": cmd.get("expira_em"),
    }}


@app.post("/mt5/comando/confirmar")
def mt5_comando_confirmar(inp: MT5ComandoConfirmIn):
    """EA confirma execucao (via conector PY). resultado.ticket + preco_real
    quando sucesso; resultado.erro quando falhou. Idempotente: se ja foi
    confirmado, retorna o estado atual sem sobrescrever."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponivel")
    try:
        atual = (sb.table("mt5_comandos").select("*").eq("id", inp.comando_id).limit(1).execute().data or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao buscar: {e}")
    if not atual:
        raise HTTPException(status_code=404, detail="comando nao encontrado")
    cmd = atual[0]
    if cmd.get("status") in ("executado", "falhou", "expirado", "cancelado"):
        return {"ok": True, "status": cmd["status"], "ja_confirmado": True}
    novo_status = "executado" if inp.sucesso else "falhou"
    try:
        sb.table("mt5_comandos").update({
            "status": novo_status,
            "confirmado_em": _dt.now(_tz.utc).isoformat(),
            "resultado": inp.resultado or {},
        }).eq("id", inp.comando_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao confirmar: {e}")
    # v6.76 — se comando executou com sucesso, BabyMachine marca pendente como aberta
    if inp.sucesso:
        try: _bm_marcar_aberta_por_comando(sb, inp.comando_id, inp.resultado or {})
        except Exception as _e:
            try: print(f"[bm confirmar] {_e}")
            except Exception: pass
    return {"ok": True, "status": novo_status}


@app.get("/mt5/comandos")
def mt5_comandos_listar(bot_id: int, limite: int = 20):
    """Historico de comandos do bot pro cockpit mostrar. Mais recentes primeiro."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponivel")
    limite = max(1, min(200, int(limite)))
    try:
        r = (sb.table("mt5_comandos")
             .select("id,tipo,params,status,origem,criado_em,entregue_em,confirmado_em,resultado")
             .eq("bot_id", bot_id)
             .order("id", desc=True)
             .limit(limite)
             .execute())
        return {"comandos": r.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao listar: {e}")


@app.post("/conector/evento")
def conector_evento(ev: ConectorEvento):
    """Evento do bot (trade aberto/fechado, reversão, pirâmide...)."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    bot = _bot_por_token(sb, ev.bot_token)
    if not bot:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    # v6.66: enriquece o detalhe_json com bot_token e bot_nome. A auditoria do
    # Monitor lê daqui pra mostrar "BOTTESTED_10 · ABRIU BUY" em vez de só ABRIU.
    # Zero mudança de schema — cabem dentro do JSONB que já existia.
    det = dict(ev.detalhe or {})
    det.setdefault("bot_token", ev.bot_token)
    det.setdefault("bot_nome", bot.get("nome") or "")
    _bm_evento_id = None
    try:
        _r_ev = sb.table("agente_eventos").insert({
            "user_id": bot.get("user_id"), "tipo": f"bot_{ev.tipo}",
            "regra": None, "detalhe_json": det,
        }).execute()
        _bm_evento_id = ((_r_ev.data or [{}])[0]).get("id")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gravar evento: {e}")
    # v6.76 — BabyMachine acompanha abertura e fechamento (non-blocking)
    _tipo_bm = str(ev.tipo or "").lower()
    if _tipo_bm == "aberto":
        try: _bm_processar_abertura(sb, bot, det, _bm_evento_id)
        except Exception as _e:
            try: print(f"[bm hook aberto] {_e}")
            except Exception: pass
    elif _tipo_bm == "fechado":
        try: _bm_processar_fechamento(sb, bot, det, _bm_evento_id)
        except Exception as _e:
            try: print(f"[bm hook fechado] {_e}")
            except Exception: pass
    # v6.69 — FIM DE VIDA IMEDIATO: se o conector PY detectar BOTTESTED_FIM e
    # mandar tipo=fim, zera ultimo_ping AGORA (bot offline em segundos, não espera
    # os 45s do timeout). Silencioso se falhar — o timeout é a rede de segurança.
    if str(ev.tipo or "").lower() == "fim":
        try:
            sb.table("conector_bots").update({
                "ultimo_ping": None,
            }).eq("id", bot.get("id")).execute()
        except Exception as _e:
            try: print(f"[fim-imediato] {_e}")
            except Exception: pass
    # v6.67: ANÁLISE CRUZADA IMEDIATA. Sem cooldown — evento é prioridade máxima
    # (o usuário quer ver a análise da entrada/saída logo depois). Best effort.
    try:
        _tipo_low = str(ev.tipo or "").lower()
        _gatilho = "evento_abriu" if _tipo_low == "aberto" else (
                   "evento_fechou" if _tipo_low == "fechado" else "status")
        if _gatilho.startswith("evento_") and bot.get("id"):
            _leit = _anl_ler_leitura(sb, bot.get("user_id"), bot.get("id"))
            _analisar_por_gatilho(sb, bot.get("id"), bot.get("user_id"),
                                  _gatilho, leitura_atual=_leit,
                                  ctx_extra={
                                      "tipo": _tipo_low,
                                      "lado": det.get("lado"),
                                      "simbolo": det.get("simbolo"),
                                      "preco": det.get("preco"),
                                  })
    except Exception as _e:
        try: print(f"[analise-evento] {_e}")
        except Exception: pass
    return {"ok": True}


@app.post("/conector/bot/excluir")
def conector_bot_excluir(req: ConectorExcluir):
    """Remove um bot do painel (soft delete): marca como excluído e some da
    lista, mas preserva o histórico (snapshots/eventos) no banco. Valida que
    o bot pertence ao user_id antes de mexer."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    # user_id pode vir direto (plataforma) ou ser resolvido pelo token (conector)
    user_id = req.user_id
    if not user_id and req.bot_token:
        dono = _bot_por_token(sb, req.bot_token)
        if dono:
            user_id = dono.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id ou bot_token obrigatório")
    try:
        r = (sb.table("conector_bots").select("id,user_id")
             .eq("id", req.bot_id).limit(1).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar bot: {e}")
    if not r.data:
        raise HTTPException(status_code=404, detail="Bot não encontrado")
    if str(r.data[0].get("user_id")) != str(user_id):
        # não é dono — nega sem revelar nada
        raise HTTPException(status_code=403, detail="Sem permissão para este bot")
    try:
        sb.table("conector_bots").update({"excluido": True}).eq("id", req.bot_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao excluir bot: {e}")
    return {"ok": True, "bot_id": req.bot_id}


@app.get("/usuario/progresso")
def usuario_progresso(user_id: str = "", bot_token: str = "", desde: str = ""):
    """Trilha da jornada: em que etapa o usuário está, a partir de dados REAIS.
    Etapas: 1 Criar (logado) · 2 Testar (tem backtest) · 3 Ajustar (testou, pode ajustar)
    · 4 Enviar (registrou bot) · 5 Conectar (bot já pingou) · 6 Operar (bot lendo o gráfico ao vivo).
    Se bot_token for informado, as etapas 5/6 olham SÓ esse bot (a trilha segue UM bot da
    estratégia atual, não o histórico da conta). Sem bot_token, olha todos (retrocompat).
    Se 'desde' (ISO) for informado, etapa 6 só conta ping POSTERIOR a esse momento — assim
    um ping velho (de antes de você enviar nesta sessão) nunca infla a trilha.
    Retorna a etapa MÁXIMA alcançada — a barra acende até ali."""
    if not user_id:
        return {"etapa": 1, "etapas_ok": [1]}
    sb = _sb_admin()
    if sb is None:
        return {"etapa": 1, "etapas_ok": [1]}
    etapa = 1  # logado = criou/entrou
    try:
        # 2 Testar: tem ao menos 1 backtest gravado
        rbt = (sb.table("backtests_historico").select("id")
               .eq("user_id", user_id).limit(1).execute())
        if rbt.data:
            etapa = max(etapa, 3)  # testou → 2 e 3 (ajustar é opcional, já liberou)
    except Exception:
        pass
    try:
        # 4/5/6: olha os bots do conector
        q = sb.table("conector_bots").select("*").eq("user_id", user_id)
        if bot_token:
            q = q.eq("bot_token", bot_token)  # só o bot da sessão atual
        rb = q.limit(50).execute()
        bots = [b for b in (rb.data or []) if not b.get("excluido")]
        if bots:
            etapa = max(etapa, 4)  # registrou/enviou pelo menos 1 bot
            agora = _dt.now(_tz.utc)
            # âncora de tempo: só conta operar se o ping vier DEPOIS do envio da sessão
            marco = None
            if desde:
                try:
                    marco = _dt.fromisoformat(str(desde).replace("Z", "+00:00"))
                except Exception:
                    marco = None
            for b in bots:
                # 5 CONECTAR / 6 OPERAR vêm do SENSOR DE PRESENÇA (fonte única).
                # Estado PARADO não acende nada (trilha REBAIXA quando o bot para).
                et = _presenca_etapa(b, marco, agora)
                if et:
                    etapa = max(etapa, et)
    except Exception:
        pass
    return {"etapa": etapa, "etapas_ok": list(range(1, etapa + 1))}


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
        if b.get("excluido"):
            continue  # soft delete: some da lista, histórico fica no banco
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


def _parse_candles_para_lista(candles_str):
    """v6.72 — parseia string O,H,L,C ou O,H,L,C,V. Volume default 0."""
    cs = []
    for parte in str(candles_str or "").split(";"):
        vs = parte.split(",")
        if len(vs) >= 4:
            try:
                cs.append({
                    "o": float(vs[0]), "h": float(vs[1]),
                    "l": float(vs[2]), "c": float(vs[3]),
                    "v": float(vs[4]) if len(vs) >= 5 else 0,
                })
            except Exception:
                pass
    return cs


def _detectar_topos_fundos(cs, janela=3):
    """v6.70 — detecta swing highs e swing lows (topos/fundos locais). Uma
    vela é topo se sua HIGH é a maior da janela ao redor; fundo se sua LOW é
    a menor. Retorna listas com preço + indice (velas atras)."""
    topos, fundos = [], []
    n = len(cs)
    if n < janela * 2 + 1:
        return topos, fundos
    for i in range(janela, n - janela):
        h = cs[i]["h"]; l = cs[i]["l"]
        eh_topo = all(cs[i]["h"] >= cs[j]["h"] for j in range(i - janela, i + janela + 1) if j != i)
        eh_fundo = all(cs[i]["l"] <= cs[j]["l"] for j in range(i - janela, i + janela + 1) if j != i)
        if eh_topo:
            topos.append({"preco": round(h, 4), "velas_atras": n - 1 - i})
        if eh_fundo:
            fundos.append({"preco": round(l, 4), "velas_atras": n - 1 - i})
    # ordena do mais recente pro mais antigo
    topos.sort(key=lambda x: x["velas_atras"])
    fundos.sort(key=lambda x: x["velas_atras"])
    return topos[:3], fundos[:3]


def _detectar_padrao_ultima_vela(cs):
    """v6.70 — identifica o padrão da última vela pronta (a que fechou).
    Retorna string com nome + direção implícita."""
    if len(cs) < 2:
        return None
    ult = cs[-1]; ant = cs[-2]
    o, h, l, c = ult["o"], ult["h"], ult["l"], ult["c"]
    corpo = abs(c - o)
    range_total = h - l
    if range_total <= 0:
        return None
    corpo_pct = corpo / range_total
    sombra_sup = h - max(o, c)
    sombra_inf = min(o, c) - l
    # Marubozu: corpo dominante (>80% do range)
    if corpo_pct > 0.80:
        return "marubozu de alta" if c > o else "marubozu de baixa"
    # Doji: corpo mínimo (<10%)
    if corpo_pct < 0.10:
        return "doji (indecisão)"
    # Martelo: sombra inferior grande + corpo pequeno em cima
    if sombra_inf > corpo * 2 and sombra_sup < corpo * 0.5:
        return "martelo (possível reversão de baixa)"
    # Estrela cadente: sombra superior grande + corpo pequeno embaixo
    if sombra_sup > corpo * 2 and sombra_inf < corpo * 0.5:
        return "estrela cadente (possível reversão de alta)"
    # Engolfo de alta: vela atual verde engloba corpo da anterior vermelha
    if c > o and ant["c"] < ant["o"] and c > ant["o"] and o < ant["c"]:
        return "engolfo de alta"
    # Engolfo de baixa
    if c < o and ant["c"] > ant["o"] and c < ant["o"] and o > ant["c"]:
        return "engolfo de baixa"
    return None



# ════════════════════════════════════════════════════════════════════════════
#  v6.79 — DETECTOR DE LATERALIZAÇÃO (RANGE) + RAIO-X DO COCKPIT
#
#  Lição do BOTTESTED_14 (BTCUSD 15m): o pipeline enxergava as PEÇAS (suporte
#  com N toques, resistência com M toques, preço no meio) mas não NOMEAVA o
#  QUADRO — lateralização clássica: bate no suporte, volta pro canal, bate de
#  novo, sem sair do lugar. E quando o range rompeu, nada disparou. Estas
#  funções são a camada de CONCLUSÃO: detectam o estado, medem o tamanho do
#  canal e projetam o rompimento por measured move (geometria, não promessa).
#  Tudo determinístico — custo zero de IA.
# ════════════════════════════════════════════════════════════════════════════

def _atr_de_candles(cs, period=14):
    """v6.79 — ATR simples (média do True Range) da lista [{o,h,l,c}].
    Retorna em pontos do ativo, ou None se não há velas suficientes."""
    if not cs or len(cs) < 3:
        return None
    trs = []
    for i in range(1, len(cs)):
        h, l, pc = cs[i]["h"], cs[i]["l"], cs[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    janela = trs[-period:] if len(trs) > period else trs
    if not janela:
        return None
    return sum(janela) / len(janela)


def _detectar_range_lateral(cs, atr=None, preco=None):
    """v6.79 — detector determinístico de LATERALIZAÇÃO no TF de operação.

    NÚCLEO + CAUDA: o range é medido num NÚCLEO de velas (a janela menos até
    3 velas finais); a CAUDA (velas finais + vela atual) é classificada contra
    ele. Sem isso, a própria vela do rompimento redefinia o extremo na leitura
    seguinte e o range 'sumia' — impossível anunciar rompimento confirmado.

    Critérios do núcleo (conservadores de propósito):
      - teto = cluster das máximas; fundo = cluster das mínimas
        (toque = encostar a 18%% da altura do extremo — tolerância RELATIVA
        ao range, funciona igual em BTC 64k e EURUSD 1.08);
      - 2+ toques em CADA extremo;
      - >= 75%% das velas do núcleo FECHARAM dentro;
      - altura sã: >= 0.7×ATR e <= 8×ATR (nem ruído, nem o gráfico inteiro).

    Estado pela vela ATUAL: dentro | rompeu_cima | rompeu_baixo (fechamento
    além do limiar = máx(0.35×ATR, 8%% da altura)); 'confirmado' quando uma
    vela FECHADA anterior também está fora do mesmo lado. Projeções por
    measured move (teto+altura / fundo-altura). Rompimento que já percorreu
    >140%% da projeção deixa de ser reportado — virou história. Puro, sem I/O."""
    try:
        if not cs or len(cs) < 8:
            return None
        base = cs[:-1]
        if preco is None:
            preco = cs[-1]["c"]
        preco = float(preco)

        def _medir_nucleo(nucleo):
            highs = [v["h"] for v in nucleo]
            lows = [v["l"] for v in nucleo]
            teto_raw, fundo_raw = max(highs), min(lows)
            altura_raw = teto_raw - fundo_raw
            if altura_raw <= 0:
                return None
            tol_toque = altura_raw * 0.18
            idx_teto = [i for i, h in enumerate(highs) if h >= teto_raw - tol_toque]
            idx_fundo = [i for i, l in enumerate(lows) if l <= fundo_raw + tol_toque]
            if len(idx_teto) < 2 or len(idx_fundo) < 2:
                return None
            # ALTERNÂNCIA (anti-tendência): range de verdade REVISITA os dois
            # extremos ao longo do tempo. Numa tendência, os toques do fundo
            # ficam todos no início e os do teto todos no fim (ou vice-versa)
            # — o "range" seria só o envelope da janela. Exige toque de fundo
            # DEPOIS de um toque de teto E toque de teto DEPOIS de um de fundo.
            if not (max(idx_fundo) > min(idx_teto) and max(idx_teto) > min(idx_fundo)):
                return None
            hs = [highs[i] for i in idx_teto]
            ls = [lows[i] for i in idx_fundo]
            teto = sum(hs) / len(hs)
            fundo = sum(ls) / len(ls)
            altura = teto - fundo
            if altura <= 0:
                return None
            if atr:
                if altura < 0.7 * atr or altura > 8 * atr:
                    return None
            elif altura > preco * 0.04:
                return None
            marg = altura * 0.10
            dentro = sum(1 for v in nucleo if (fundo - marg) <= v["c"] <= (teto + marg))
            if dentro < 0.75 * len(nucleo):
                return None
            return {"teto": teto, "fundo": fundo, "altura": altura,
                    "toques_topo": len(hs), "toques_fundo": len(ls),
                    "velas_dentro": dentro, "velas_total": len(nucleo)}

        # varre janelas: k tira até 3 velas FINAIS (cauda do rompimento — o
        # range continua existindo como referência depois de 1-3 velas fora);
        # s tira até 7 velas INICIAIS (cabeça de tendência — cobre o caso do
        # mercado que subiu e ENTROU em range recentemente: sem isso, a mínima
        # da subida viraria "fundo" e mataria a detecção). Prefere o núcleo
        # maior (s=0, k=0) e aceita o primeiro válido.
        med = None
        cauda = []
        for s in (0, 3, 5, 7):
            for k in (0, 1, 2, 3):
                nucleo = base[s:len(base) - k] if k else base[s:]
                if len(nucleo) < 7:
                    continue
                med = _medir_nucleo(nucleo)
                if med:
                    cauda = base[s + len(nucleo):]
                    break
            if med:
                break
        if not med:
            return None
        teto, fundo, altura = med["teto"], med["fundo"], med["altura"]
        lim = max(float(atr or 0) * 0.35, altura * 0.08)
        c_atual = float(cs[-1]["c"])
        estado, confirmado, avanco = "dentro", False, None
        fora_cima = [v for v in cauda if v["c"] > teto + lim]
        fora_baixo = [v for v in cauda if v["c"] < fundo - lim]
        if c_atual > teto + lim:
            estado = "rompeu_cima"
            confirmado = bool(fora_cima)
            avanco = int(round((c_atual - teto) / altura * 100))
        elif c_atual < fundo - lim:
            estado = "rompeu_baixo"
            confirmado = bool(fora_baixo)
            avanco = int(round((fundo - c_atual) / altura * 100))
        elif fora_cima or fora_baixo:
            # cauda fechou fora mas a vela atual voltou pra dentro: rompimento
            # que falhou (fakeout). O range segue valendo — reporta como dentro.
            estado = "dentro"
        if avanco is not None and avanco > 140:
            return None  # rompimento antigo, projeção consumida — range virou história
        pos_pct = int(round((preco - fundo) / altura * 100))
        pos_pct = max(-50, min(150, pos_pct))
        return {
            "ativo": True,
            "topo": round(teto, 4), "fundo": round(fundo, 4),
            "altura_pts": round(altura, 4),
            "altura_atr": round(altura / atr, 2) if atr else None,
            "toques_topo": med["toques_topo"], "toques_fundo": med["toques_fundo"],
            "velas_dentro": med["velas_dentro"], "velas_total": med["velas_total"],
            "posicao_pct": pos_pct,
            "estado": estado, "confirmado": confirmado,
            "avanco_rompimento_pct": avanco,
            "proj_alta": round(teto + altura, 4),
            "proj_baixa": round(fundo - altura, 4),
        }
    except Exception:
        return None


def _detectar_estrutura_swing(cs, atr=None, preco=None):
    """v6.80 — ESTRUTURA DE SWING ao vivo (pivô 1-2-3) no TF de operação.

    BAIXA: topo1 -> fundo (neckline) -> topo2 MAIS BAIXO (margem 0.25×ATR).
    ALTA: espelho. Estados: 'formando' (2º extremo feito, neckline segurando)
    e 'rompeu' (fechamento além da neckline; 'confirmado' com 2 fechamentos).
    Projeção = measured move (neckline ∓ altura da estrutura). Invalidação =
    além do 2º extremo. Rompimento >140%% da projeção some (virou história).
    Puro, sem I/O — complementa o detector de range (que exige extremos no
    MESMO nível; aqui o 2º extremo é mais fraco DE PROPÓSITO = reversão)."""
    try:
        if not cs or len(cs) < 9:
            return None
        if preco is None:
            preco = cs[-1]["c"]
        preco = float(preco)
        topos, fundos = _detectar_topos_fundos(cs, janela=2)
        n = len(cs)
        c_atual = float(cs[-1]["c"])
        c_ant = float(cs[-2]["c"])
        marg_min = max(float(atr or 0) * 0.25, preco * 0.0006)

        def _monta(direcao, p1, p2, neck):
            altura = abs((p1 + p2) / 2.0 - neck)
            if altura <= 0:
                return None
            lim = max(float(atr or 0) * 0.3, altura * 0.08)
            if direcao == "baixa":
                if c_atual > p1:
                    return None  # invalidada: novo topo acima do 1º
                rompeu = c_atual < neck - lim
                confirmado = rompeu and c_ant < neck - lim
                avanco = int(round((neck - c_atual) / altura * 100)) if rompeu else None
                proj = neck - altura
            else:
                if c_atual < p1:
                    return None
                rompeu = c_atual > neck + lim
                confirmado = rompeu and c_ant > neck + lim
                avanco = int(round((c_atual - neck) / altura * 100)) if rompeu else None
                proj = neck + altura
            if avanco is not None and avanco > 140:
                return None
            return {"direcao": direcao,
                    "estado": "rompeu" if rompeu else "formando",
                    "confirmado": bool(confirmado),
                    "p1": round(p1, 4), "p2": round(p2, 4),
                    "neckline": round(neck, 4),
                    "altura_pts": round(altura, 4),
                    "proj": round(proj, 4),
                    "invalidacao": round(p2, 4),
                    "avanco_pct": avanco}

        # BAIXA: 2 topos mais recentes, o novo MAIS BAIXO, com fundo entre eles
        if len(topos) >= 2:
            t2, t1 = topos[0], topos[1]      # [0] = mais recente
            if (t1["preco"] - t2["preco"]) >= marg_min and t2["velas_atras"] >= 1:
                pos_t1 = n - 1 - t1["velas_atras"]
                pos_t2 = n - 1 - t2["velas_atras"]
                entre = [f for f in fundos if pos_t1 < (n - 1 - f["velas_atras"]) < pos_t2]
                if entre:
                    r = _monta("baixa", t1["preco"], t2["preco"],
                               min(f["preco"] for f in entre))
                    if r:
                        return r
        # ALTA: 2 fundos mais recentes, o novo MAIS ALTO, com topo entre eles
        if len(fundos) >= 2:
            f2, f1 = fundos[0], fundos[1]
            if (f2["preco"] - f1["preco"]) >= marg_min and f2["velas_atras"] >= 1:
                pos_f1 = n - 1 - f1["velas_atras"]
                pos_f2 = n - 1 - f2["velas_atras"]
                entre = [t for t in topos if pos_f1 < (n - 1 - t["velas_atras"]) < pos_f2]
                if entre:
                    r = _monta("alta", f1["preco"], f2["preco"],
                               max(t["preco"] for t in entre))
                    if r:
                        return r
        return None
    except Exception:
        return None


def _extras_cockpit(det, s):
    """v6.79 — RAIO-X DO MERCADO: números determinísticos que o snapshot já
    carrega, expostos pro usuário como informação de primeira classe:
      canal  — largura do canal EMA20 H/L (pts / %% / ×ATR), posição do preço
               no canal, distância pra romper cada lado;
      atr    — quanto o mercado anda em média por vela do TF (régua honesta);
      range  — lateralização detectada + projeções de rompimento;
      níveis — escada S/R do offmind: 3 acima + 3 abaixo com toques e
               distância em pts (corredor livre até o próximo obstáculo).
    Custo zero de IA. NON-BLOCKING: qualquer falha devolve None."""
    try:
        if not isinstance(det, dict) or not det:
            return None
        tf_op = str(det.get("tfop") or "").lower()
        chave_op = {"1m": "c1m", "5m": "c5m", "15m": "c15m", "30m": "c30m",
                    "60m": "c60m", "1h": "c60m", "4h": "c4h", "1d": "c4h"}.get(tf_op, "c15m")
        cs = _parse_candles_para_lista(det.get(chave_op) or det.get("c15m"))
        if len(cs) < 5:
            return None
        def _f(v):
            try:
                return float(v)
            except Exception:
                return None
        preco = _f(det.get("preco")) or cs[-1]["c"]
        ema_h, ema_l = _f(det.get("emaH")), _f(det.get("emaL"))
        atr = _atr_de_candles(cs)
        canal = None
        if ema_h is not None and ema_l is not None and ema_h > ema_l and preco:
            larg = ema_h - ema_l
            canal = {
                "ema_h": round(ema_h, 4), "ema_l": round(ema_l, 4),
                "largura_pts": round(larg, 4),
                "largura_pct": round(larg / preco * 100, 3),
                "largura_atr": round(larg / atr, 2) if atr else None,
                "posicao_pct": int(round((preco - ema_l) / larg * 100)),
                "dist_romper_cima": round(ema_h - preco, 4) if preco < ema_h else None,
                "dist_romper_baixo": round(preco - ema_l, 4) if preco > ema_l else None,
            }
        rng = _detectar_range_lateral(cs, atr, preco)
        acima, abaixo = [], []
        for e in ((det.get("offmind") or {}).get("estrutura") or []):
            nv = _f(e.get("nivel"))
            if nv is None or not preco:
                continue
            item = {"tf": e.get("tf"), "tipo": e.get("tipo"),
                    "nivel": round(nv, 4), "toques": e.get("toques"),
                    "dist_pts": round(abs(nv - preco), 4),
                    "testando": bool(e.get("testando"))}
            (acima if nv >= preco else abaixo).append(item)
        acima.sort(key=lambda x: x["nivel"])
        abaixo.sort(key=lambda x: -x["nivel"])
        corredor = None
        if acima or abaixo:
            corredor = {"livre_cima": acima[0]["dist_pts"] if acima else None,
                        "livre_baixo": abaixo[0]["dist_pts"] if abaixo else None}
        # v6.80 — estrutura de swing + catálogo INTEIRO de padrões do banco
        # (o front mostra todos em tempo real: acesos quando formando).
        sw = _detectar_estrutura_swing(cs, atr, preco)
        catalogo = [{"chave": k, "nome": v["nome"], "categoria": v["categoria"]}
                    for k, v in PADROES_OFFMIND.items()]
        return {"tf": tf_op or None,
                "atr_pts": round(atr, 4) if atr else None,
                "canal": canal, "range": rng, "swing": sw,
                "padroes_catalogo": catalogo,
                "niveis_acima": acima[:3], "niveis_abaixo": abaixo[:3],
                "corredor": corredor}
    except Exception:
        return None


def _analisar_bot_tecnica(candles_str, ema_h, ema_l, preco, regime, posicoes, offmind=None):
    """v6.70 -> v6.71 — o BOT como analista técnico. Prioriza o OFFMIND (que
    já detecta padrões e níveis S/R clustered com múltiplos toques via
    detectores robustos do backend); complementa com micro-fatos das últimas
    velas (padrão vela a vela, momentum) só como reforço.

    Output alimenta o prompt do _narrar_bot_analitico. Determinístico."""
    cs = _parse_candles_para_lista(candles_str)
    if len(cs) < 5:
        return None
    # normaliza preço/EMAs
    try:
        preco_f = float(preco) if preco is not None else cs[-1]["c"]
    except Exception:
        preco_f = cs[-1]["c"]
    try:
        ema_h_f = float(ema_h) if ema_h is not None else None
        ema_l_f = float(ema_l) if ema_l is not None else None
    except Exception:
        ema_h_f = ema_l_f = None
    # topos e fundos recentes
    topos, fundos = _detectar_topos_fundos(cs, janela=2)
    # padrão da última vela
    padrao = _detectar_padrao_ultima_vela(cs)
    # momentum: força das últimas 3 velas
    if len(cs) >= 3:
        u3 = cs[-3:]
        altas = sum(1 for v in u3 if v["c"] > v["o"])
        baixas = sum(1 for v in u3 if v["c"] < v["o"])
        if altas == 3:
            momentum = "3 velas de alta consecutivas"
        elif baixas == 3:
            momentum = "3 velas de baixa consecutivas"
        elif altas == 2:
            momentum = "2 velas de alta e 1 de baixa"
        elif baixas == 2:
            momentum = "2 velas de baixa e 1 de alta"
        else:
            momentum = "movimento misto/indeciso"
    else:
        momentum = None
    # distâncias
    dist_ema_h = round(ema_h_f - preco_f, 4) if ema_h_f and preco_f < ema_h_f else None
    dist_ema_l = round(preco_f - ema_l_f, 4) if ema_l_f and preco_f > ema_l_f else None
    # posição no range das velas visíveis
    highs = [v["h"] for v in cs]
    lows = [v["l"] for v in cs]
    rng_hi = max(highs); rng_lo = min(lows)
    if rng_hi > rng_lo:
        pos_pct = int(round((preco_f - rng_lo) / (rng_hi - rng_lo) * 100))
    else:
        pos_pct = 50
    # gatilhos: se preço está PRÓXIMO de topo/fundo relevante
    gatilho = None
    if topos and preco_f < topos[0]["preco"]:
        d = topos[0]["preco"] - preco_f
        gatilho = f"rompimento acima de {topos[0]['preco']:.2f} (falta {d:.2f})"
    elif fundos and preco_f > fundos[0]["preco"]:
        d = preco_f - fundos[0]["preco"]
        gatilho = f"perda de {fundos[0]['preco']:.2f} como suporte (falta {d:.2f})"
    # regime resumido
    reg = ""
    if regime:
        reg = str(regime.get("estado") or regime.get("regime") or "").upper()
    fatos = {
        "preco": preco_f,
        "posicoes": posicoes or 0,
        "regime": reg,
        "topos_recentes": topos,
        "fundos_recentes": fundos,
        "ultimo_padrao": padrao,
        "momentum": momentum,
        "distancia_ema_h": dist_ema_h,
        "distancia_ema_l": dist_ema_l,
        "preco_no_range_pct": pos_pct,
        "gatilho_proximo": gatilho,
    }
    # v6.71 — INTEGRA OFFMIND: padrões formais (engolfo, martelo, etc.) e
    # níveis S/R clustered com múltiplos toques. Esses são MAIS ROBUSTOS que
    # os swing highs/lows crus calculados acima — o EA já roda detectores
    # dedicados. O BOT deve citar ESSES como estrutura primária.
    if offmind and isinstance(offmind, dict):
        # padrões formando AGORA (última vela) em cada TF
        pads_offmind = offmind.get("padroes") or []
        if pads_offmind:
            fatos["padroes_formais"] = [
                {"tf": p.get("tf"), "nome": p.get("nome"),
                 "direcao": p.get("direcao")}
                for p in pads_offmind[:4]
            ]
        # níveis S/R clustered (2+ toques): estrutura de mercado real
        estr = offmind.get("estrutura") or []
        if estr:
            # separa em testando agora vs próximos (não testando)
            testando = [e for e in estr if e.get("testando")]
            proximos = [e for e in estr if not e.get("testando")][:3]
            if testando:
                fatos["niveis_sendo_testados"] = [
                    {"tf": e.get("tf"), "tipo": e.get("tipo"),
                     "nivel": e.get("nivel"), "toques": e.get("toques")}
                    for e in testando[:3]
                ]
            if proximos:
                fatos["niveis_proximos"] = [
                    {"tf": e.get("tf"), "tipo": e.get("tipo"),
                     "nivel": e.get("nivel"), "toques": e.get("toques")}
                    for e in proximos
                ]
    # v6.79 — DETECTOR DE LATERALIZAÇÃO: mercado preso entre dois níveis é um
    # ESTADO que o bot precisa nomear (acumulação); o rompimento dele é o
    # gatilho mais clássico que existe. Projeção = altura do range (geometria).
    atr_v = _atr_de_candles(cs)
    if atr_v:
        fatos["atr_pts"] = round(atr_v, 4)
    rng = _detectar_range_lateral(cs, atr_v, preco_f)
    if rng:
        fatos["range_lateral"] = rng
    # v6.80 — ESTRUTURA DE SWING (pivô 1-2-3): reversão por perda de força
    # topo a topo (ou fundo a fundo). O range detecta acumulação; isto detecta
    # a REVERSÃO — os dois quadros que faltavam além da tendência.
    sw = _detectar_estrutura_swing(cs, atr_v, preco_f)
    if sw:
        fatos["estrutura_swing"] = sw
    return fatos


# ════════════════════════════════════════════════════════════════════════════
#  v6.82 — SCANNER MULTI-TF + ESTADO DO CAÇADOR (pedido do dono)
#
#  O BOT varre os timeframes A PARTIR DO 1M e classifica o comportamento de
#  cada um. Disso nascem três leituras determinísticas, custo ZERO de IA:
#    - cascata_reversao: reversão detectada no 1m -> confirmando no 5m ->
#      aguardando o 15m (pente-fino em REVERSÕES);
#    - alinhamento_tfs: quantos TFs puxam pro mesmo lado (pente-fino em
#      TENDÊNCIAS);
#    - estado_gatilho: PROCURANDO GATILHO DE ENTRADA (o que está caçando,
#      com preços) -> GATILHO LOCALIZADO + probabilidade em PONTOS (alvo,
#      risco até a invalidação, R:R, histórico medido, estrelas do detector).
#  Tudo entra nos fatos do BOT (narração) E no contexto da IA — mais dados
#  pra identificar padrões em construção. Números medidos, nunca promessa.
# ════════════════════════════════════════════════════════════════════════════

_SCAN_TFS = (("1m", "c1m", "z1"), ("5m", "c5m", "z5"), ("15m", "c15m", "z15"),
             ("30m", "c30m", "z15"), ("60m", "c60m", "z60"), ("4h", "c4h", "z240"))


def _scanner_multitf(det):
    """Varre os TFs do 1m em diante e classifica o comportamento de cada um.
    TF sem candles suficientes é pulado (bots antigos podem não emitir c1m)."""
    try:
        om = (det or {}).get("offmind") or {}
        pads_por_tf = {}
        for p in (om.get("padroes") or []):
            pads_por_tf.setdefault(str(p.get("tf") or "").lower(), []).append(p)
        saida = []
        for tf, ck, zk in _SCAN_TFS:
            cs = _parse_candles_para_lista(det.get(ck))
            if len(cs) < 5:
                continue
            ult = cs[-5:]
            altas = sum(1 for v in ult if v["c"] > v["o"])
            baixas = sum(1 for v in ult if v["c"] < v["o"])
            if altas >= 4:
                comp = "tendencia_alta"
            elif baixas >= 4:
                comp = "tendencia_baixa"
            elif altas == 3 and baixas <= 2:
                comp = "inclinando_alta"
            elif baixas == 3 and altas <= 2:
                comp = "inclinando_baixa"
            else:
                comp = "lateral"
            # sinal de reversão: padrão da última vela CONTRA o movimento recente
            rev = None
            pvl = str(_detectar_padrao_ultima_vela(cs) or "").lower()
            if ("martelo" in pvl or "engolfo de alta" in pvl) and baixas >= 3:
                rev = {"direcao": "alta", "evidencia": pvl.split(" (")[0]}
            elif ("estrela" in pvl or "engolfo de baixa" in pvl) and altas >= 3:
                rev = {"direcao": "baixa", "evidencia": pvl.split(" (")[0]}
            # padrões formais do OffMind no TF detectam/reforçam
            if rev is None:
                for p in pads_por_tf.get(tf, []):
                    d = str(p.get("direcao") or "").lower()
                    if "alta" in d and baixas >= 2:
                        rev = {"direcao": "alta", "evidencia": p.get("nome") or "padrao de alta"}
                        break
                    if "baixa" in d and altas >= 2:
                        rev = {"direcao": "baixa", "evidencia": p.get("nome") or "padrao de baixa"}
                        break
            if rev:
                comp = "reversao_" + rev["direcao"] + "_formando"
            item = {"tf": tf, "comportamento": comp,
                    "velas": str(altas) + " alta / " + str(baixas) + " baixa (ult. " + str(len(ult)) + ")"}
            z = det.get(zk)
            if isinstance(z, str) and z.strip():
                item["zona_canal"] = z.strip().lower()
            if rev:
                item["sinal_reversao"] = rev
            saida.append(item)
        return saida or None
    except Exception:
        return None


def _cascata_reversao(scanner):
    """Reversão detectada no menor TF -> confirmando no seguinte -> aguardando
    o próximo. O pente-fino de reversões: 1m detecta, 5m confirma, 15m decide."""
    if not scanner:
        return None
    por = {i.get("tf"): i for i in scanner}
    ordem = ["1m", "5m", "15m"]
    det_tf, rev = None, None
    for tf in ordem:
        r = (por.get(tf) or {}).get("sinal_reversao")
        if r:
            det_tf, rev = tf, r
            break
    if not rev:
        return None
    d = rev.get("direcao")
    tfs, passou, confirmados = {}, False, 0
    for tf in ordem:
        it = por.get(tf)
        if tf == det_tf:
            tfs[tf] = "detectada: " + str(rev.get("evidencia") or "padrao de reversao")
            passou = True
            continue
        if not passou:
            continue
        if not it:
            tfs[tf] = "sem dados"
            continue
        r = it.get("sinal_reversao")
        comp = str(it.get("comportamento") or "")
        if r and r.get("direcao") == d:
            tfs[tf] = "confirmando: " + str(r.get("evidencia") or "")
            confirmados += 1
        elif (d == "alta" and "alta" in comp) or (d == "baixa" and "baixa" in comp):
            tfs[tf] = "inclinando a favor"
            confirmados += 1
        else:
            tfs[tf] = "aguardando"
    if confirmados >= 2:
        estado = "confirmada ate o 15m"
    elif confirmados == 1:
        estado = "confirmando"
    else:
        estado = "detectada, aguardando confirmacao"
    return {"direcao": d, "detectada_no": det_tf, "tfs": tfs, "estado": estado}


def _alinhamento_tfs(scanner):
    """Quantos TFs puxam pro mesmo lado — o pente-fino de tendências."""
    if not scanner:
        return None
    alta = [i["tf"] for i in scanner if "alta" in str(i.get("comportamento") or "")]
    baixa = [i["tf"] for i in scanner if "baixa" in str(i.get("comportamento") or "")]
    tot = len(scanner)
    if len(baixa) > len(alta) and len(baixa) >= 2:
        return {"lado": "baixa", "resumo": str(len(baixa)) + " de " + str(tot) + " TFs a favor da baixa (" + ", ".join(baixa) + ")"}
    if len(alta) > len(baixa) and len(alta) >= 2:
        return {"lado": "alta", "resumo": str(len(alta)) + " de " + str(tot) + " TFs a favor da alta (" + ", ".join(alta) + ")"}
    return {"lado": "misto", "resumo": "TFs divididos: " + str(len(alta)) + " pra alta x " + str(len(baixa)) + " pra baixa"}


def _scanner_pacote(det):
    """Empacota scanner + cascata + alinhamento pro /monitor/leitura e pra IA."""
    sc = _scanner_multitf(det)
    if not sc:
        return None
    pac = {"tfs": sc}
    casc = _cascata_reversao(sc)
    if casc:
        pac["cascata_reversao"] = casc
    ali = _alinhamento_tfs(sc)
    if ali:
        pac["alinhamento"] = ali
    return pac


def _estado_gatilho(fatos, det, bot_id):
    """PROCURANDO GATILHO DE ENTRADA -> GATILHO LOCALIZADO, com cálculo de
    probabilidade em PONTOS (alvo provável, risco até a invalidação, R:R,
    histórico medido do banco, estrelas/confluência do detector)."""
    try:
        try:
            pos = int(fatos.get("posicoes") or 0)
        except Exception:
            pos = 0
        if pos > 0:
            return {"estado": "em_operacao"}
        preco = fatos.get("preco")
        conf = (det or {}).get("confirmacao") or {}
        historico = None
        if conf.get("veredito"):
            historico = {"score": conf.get("score"), "veredito": conf.get("veredito")}

        def _prob(entrada, alvo, invalida, origem):
            try:
                e, a, i = float(entrada), float(alvo), float(invalida)
            except Exception:
                return None
            alvo_pts = round(abs(a - e), 2)
            risco_pts = round(abs(e - i), 2)
            out = {"origem": origem, "alvo_provavel": round(a, 2),
                   "alvo_pts": alvo_pts, "risco_pts": risco_pts}
            if risco_pts > 0:
                out["rr"] = round(alvo_pts / risco_pts, 2)
            if historico:
                out["historico_medido"] = historico
            return out

        # 1) oportunidade recente do detector (a mais específica: níveis reais)
        try:
            hist = list(_oportunidade_hist(bot_id)) if bot_id else []
        except Exception:
            hist = []
        if hist:
            o = hist[-1]
            recente = False
            try:
                ts = _dt.fromisoformat(str(o.get("ts")).replace("Z", "+00:00"))
                recente = (_dt.now(_tz.utc) - ts).total_seconds() < 900
            except Exception:
                pass
            if recente:
                alvo = o.get("alvo1") or o.get("alvo") or ((o.get("alvos") or [None])[0])
                p = _prob(o.get("entrada"), alvo, o.get("stop"), "detector de oportunidade")
                if p is not None:
                    if o.get("estrelas") is not None:
                        p["estrelas"] = o.get("estrelas")
                    if o.get("confluencia") is not None:
                        p["confluencia"] = o.get("confluencia")
                return {"estado": "localizado", "direcao": o.get("direcao"),
                        "gatilho": str(o.get("cenario") or "oportunidade do detector"),
                        "probabilidade": p}
        # 2) rompimento de range / pivô disparado = gatilho clássico localizado
        rng = fatos.get("range_lateral") or {}
        sw = fatos.get("estrutura_swing") or {}
        if rng.get("estado") == "rompeu_baixo":
            return {"estado": "localizado", "direcao": "short",
                    "gatilho": "fechamento abaixo do fundo " + str(rng.get("fundo")) + " (saiu da caixa pra baixo)",
                    "probabilidade": _prob(preco, rng.get("proj_baixa"), rng.get("fundo"), "rompimento do range"),
                    "invalidacao": "fechar de volta dentro do range"}
        if rng.get("estado") == "rompeu_cima":
            return {"estado": "localizado", "direcao": "long",
                    "gatilho": "fechamento acima do teto " + str(rng.get("topo")) + " (saiu da caixa pra cima)",
                    "probabilidade": _prob(preco, rng.get("proj_alta"), rng.get("topo"), "rompimento do range"),
                    "invalidacao": "fechar de volta dentro do range"}
        if sw.get("estado") == "rompeu":
            curto = sw.get("direcao") == "baixa"
            return {"estado": "localizado", "direcao": "short" if curto else "long",
                    "gatilho": "pivô 1-2-3 disparou — fechamento " + ("abaixo" if curto else "acima") + " da neckline " + str(sw.get("neckline")),
                    "probabilidade": _prob(preco, sw.get("proj"), sw.get("neckline"), "reversão por estrutura"),
                    "invalidacao": ("acima de " if curto else "abaixo de ") + str(sw.get("invalidacao"))}
        # 3) sem gatilho armado: PROCURANDO — lista o que está caçando, com preços
        cacando = []
        if rng.get("estado") == "dentro":
            cacando.append({"gatilho": "fechamento fora da caixa",
                            "rompe_teto": rng.get("topo"), "se_cima_busca": rng.get("proj_alta"),
                            "perde_fundo": rng.get("fundo"), "se_baixo_busca": rng.get("proj_baixa")})
        if sw.get("estado") == "formando":
            cacando.append({"gatilho": ("fechar abaixo" if sw.get("direcao") == "baixa" else "fechar acima")
                                       + " da neckline " + str(sw.get("neckline")),
                            "se_disparar_busca": sw.get("proj"), "cancela_se": sw.get("invalidacao")})
        for nv in (fatos.get("niveis_sendo_testados") or [])[:2]:
            cacando.append({"gatilho": "reação no " + str(nv.get("tipo") or "nível") + " "
                                       + str(nv.get("nivel")) + " (" + str(nv.get("toques") or "?")
                                       + " toques no " + str(nv.get("tf") or "?") + ")"})
        if not cacando and fatos.get("gatilho_proximo"):
            cacando.append({"gatilho": fatos.get("gatilho_proximo")})
        out = {"estado": "procurando", "cacando": cacando[:3]}
        if historico:
            out["historico_medido"] = historico
        return out
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  v6.70 — BOT ANALITICO (Caminho C: hibrido determinístico + IA voz humana)
#
#  Cache com assinatura curta: se nada mudou nos últimos 30s, reutiliza o
#  texto — evita gastar tokens quando o gráfico ainda não avançou.
# ════════════════════════════════════════════════════════════════════════════
_NARR_BOT_CACHE = {}   # bot_token -> {"assinatura": str, "ts": float, "texto": str}
_NARR_BOT_MIN_INTERVAL = 30  # segundos mínimos entre chamadas de IA


def _bot_assinatura(fatos):
    """Assinatura curta pra cache: se muda, é motivo pra re-narrar."""
    if not fatos: return ""
    pad = fatos.get("ultimo_padrao") or ""
    mom = fatos.get("momentum") or ""
    reg = fatos.get("regime") or ""
    pos = fatos.get("posicoes") or 0
    pos_range = fatos.get("preco_no_range_pct") or 0
    # arredonda pos_range em blocos de 10% pra não invalidar por pequenas
    pos_range_b = int(pos_range / 10) * 10
    rng = (fatos.get("range_lateral") or {}).get("estado") or ""
    swf = fatos.get("estrutura_swing") or {}
    sw = (swf.get("direcao") or "") + ":" + (swf.get("estado") or "") if swf else ""
    # v6.82 — estado do caçador e cascata de reversão viram parte da assinatura:
    # PROCURANDO->LOCALIZADO ou 1m->5m->15m mudando = re-narra NA HORA.
    eg = (fatos.get("estado_gatilho") or {}).get("estado") or ""
    casc = fatos.get("cascata_reversao") or {}
    cz = (str(casc.get("direcao") or "") + ":" + str(casc.get("estado") or "")) if casc else ""
    return f"{reg}|{pos}|{pad}|{mom}|{pos_range_b}|{rng}|{sw}|{eg}|{cz}"


def _narrar_bot_analitico(fatos, tf_op, bot_token):
    """v6.70 — pega os fatos determinísticos e formata em texto de trader
    executor. IA (Haiku, temperatura baixa) usada só pra dar voz humana
    aos números já calculados. Cache de 30s por bot pra economizar tokens."""
    import sys, time
    if not fatos:
        return None
    ass_agora = _bot_assinatura(fatos)
    agora = time.time()
    cache = _NARR_BOT_CACHE.get(bot_token) or {}
    # Se nada mudou e passou menos de MIN_INTERVAL: reusa
    if (cache.get("assinatura") == ass_agora
            and (agora - float(cache.get("ts") or 0)) < _NARR_BOT_MIN_INTERVAL):
        return cache.get("texto")
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return None
    try:
        import httpx
        sistema = (
            "Você é o BOT EXECUTOR de trading. Você olha o gráfico do TF de operação "
            "AGORA e reporta o que VÊ, mecanicamente, como sniper focado no gatilho técnico "
            "imediato. NÃO contextualize com histórico nem opine sobre cenário macro (isso é papel "
            "da IA MENTOR que fala em outro quadro). Outros TFs: cite SOMENTE o que o seu SCANNER "
            "multi-TF reportou (campos scanner_tfs/cascata_reversao/alinhamento_tfs) — leitura "
            "mecânica sua, não opinião. "
            "SÓ o que está no gráfico agora: ESTRUTURA DE MERCADO (níveis S/R com múltiplos toques — "
            "duplos/triplos topos e fundos), PADRÕES FORMAIS (engolfo, martelo, estrela cadente, 3 velas "
            "consecutivas), momentum das últimas velas, distância pra rompimento, setup de entrada se houver.\n\n"
            "PRIORIZE ESTRUTURA E PADRÕES FORMAIS:\n"
            "- Campo padroes_formais lista padrões CLÁSSICOS detectados agora em cada TF (ex.: engolfo de baixa "
            "no 5m, martelo no 15m). CITE-OS quando existirem.\n"
            "- Campo niveis_sendo_testados lista suportes/resistências com MÚLTIPLOS TOQUES que o preço está "
            "encostando AGORA. Isso é ESTRUTURA DE MERCADO — muito mais forte que swing high/low de curto prazo. "
            "Se tem resistência com 2 toques testada agora, é DUPLO TOPO se formando. Se tem suporte com 3 toques, "
            "é PISO defendido. NARRE ISSO.\n"
            "- Campo niveis_proximos são níveis relevantes que ainda não estão sendo testados — cite como próximos "
            "alvos técnicos.\n"
            "- topos_recentes e fundos_recentes são swing highs/lows brutos (janela pequena). Use SÓ se não tiver "
            "níveis do offmind — são complemento, não estrutura primária.\n\n"
            "LATERALIZAÇÃO (campo range_lateral) — QUANDO PRESENTE, É O FATO PRINCIPAL:\n"
            "- estado='dentro': o mercado está PRESO num range (acumulação clássica: bate num extremo, volta, "
            "bate de novo, sem sair do lugar). ABRA a leitura nomeando isso: 'LATERALIZAÇÃO: N velas presas "
            "entre FUNDO (X toques) e TETO (Y toques) — range de Z pts'. Dentro do range NÃO há trade — diga "
            "isso com todas as letras. O gatilho é o FECHAMENTO fora, pra qualquer lado: rompimento acima do "
            "teto projeta proj_alta; perda do fundo projeta proj_baixa (projeção = altura do range, geometria, "
            "não promessa). SEMPRE cite fundo, teto e as duas projeções em preço.\n"
            "- estado='rompeu_cima' ou 'rompeu_baixo': ANUNCIE O ROMPIMENTO como manchete: 'ROMPEU o range de "
            "N pts pra baixo — fechou em X abaixo do fundo Y (Z toques); projeção da altura aponta W'. Se "
            "confirmado=true, diga 'confirmado com 2 fechamentos fora'. Invalidação = fechar de volta DENTRO "
            "do range. avanco_rompimento_pct diz quanto da projeção já andou — se alto (>70), avise que boa "
            "parte do movimento projetado já aconteceu.\n\n"
            "ESTRUTURA DE SWING (campo estrutura_swing) — reversão clássica pivô 1-2-3:\n"
            "- direcao='baixa' + estado='formando': 'segundo topo em p2, MAIS BAIXO que o primeiro em p1 — "
            "compradores perdendo força; perda de neckline confirma a reversão com projeção proj'. Invalidação "
            "acima de p2. Espelho pra alta (fundo mais alto = vendedores perdendo força).\n"
            "- estado='rompeu': MANCHETE: 'PIVÔ 1-2-3 DE BAIXA disparado — fechou abaixo da neckline X; "
            "projeção da altura da estrutura aponta proj'. Se confirmado=true, diga 'confirmado com 2 "
            "fechamentos'. avanco_pct alto (>70) = boa parte do movimento projetado já aconteceu, avise.\n"
            "- Se range_lateral E estrutura_swing existirem juntos, o RANGE manda a leitura; cite o swing "
            "como reforço da direção.\n\n"
            "ESTADO DO CAÇADOR (campo estado_gatilho) — SEM POSIÇÃO, ABRA A LEITURA COM ELE:\n"
            "- estado='procurando': comece com 'PROCURANDO GATILHO DE ENTRADA — ' e diga o que está "
            "caçando (campo cacando), sempre com preços: fechamento fora da caixa (rompe_teto busca "
            "se_cima_busca; perde_fundo busca se_baixo_busca), neckline do pivô, reação em nível "
            "testado.\n"
            "- estado='localizado': MANCHETE 'GATILHO DE ENTRADA LOCALIZADO — ' + o gatilho + a "
            "direção. Na sequência, o CÁLCULO DE PROBABILIDADE EM PONTOS (campo probabilidade): "
            "'alvo provável X (+N pts), risco até a invalidação M pts, R:R ~Z'. Se houver "
            "historico_medido, cite o veredito medido; se houver estrelas/confluencia do detector, "
            "cite também. São números MEDIDOS do gráfico e do banco — proibido prometer ('vai "
            "subir', 'garantido').\n"
            "- estado='em_operacao': aplica a regra do trade aberto (regra 6).\n\n"
            "SCANNER MULTI-TF (scanner_tfs, cascata_reversao, alinhamento_tfs) — SEU PENTE-FINO do "
            "1m em diante:\n"
            "- cascata_reversao, quando existir, é FATO DE MANCHETE: narre NA ORDEM dos TFs usando "
            "os estados exatos dos campos, ex.: 'Reversão de alta detectada no 1m (martelo), "
            "confirmando no 5m (engolfo de alta), aguardando o 15m'.\n"
            "- alinhamento_tfs resume a tendência ('N de M TFs a favor da baixa (1m, 5m, 15m)') — "
            "cite quando reforça ou contradiz o gatilho.\n"
            "- scanner_tfs é o detalhe por TF (comportamento + velas + zona); use pra dar cor, sem "
            "listar tudo.\n\n"
            "REGRAS:\n"
            "(1) 2 a 5 frases curtas, máx ~430 caracteres, sem markdown, sem crases;\n"
            "(2) tom DIRETO, TÉCNICO, sniper — não use 'talvez', 'pode ser', 'tende'. Use frases "
            "diretas: 'duplo topo se formando em X', 'setup de compra ativo acima de Y', 'suporte em Z "
            "com 3 toques segurando';\n"
            "(3) SEMPRE cite preços concretos dos fatos (não invente números);\n"
            "(4) SEMPRE mencione um gatilho técnico se houver: 'rompimento acima de X confirma', "
            "'perda de Y invalida estrutura';\n"
            "(5) Se posições=0 e sem setup claro: descreva a ESTRUTURA (níveis com toques) e diga o que "
            "precisa acontecer pra ter setup;\n"
            "(6) Se posições>0: descreva onde está o trade em relação à estrutura e o próximo alvo/invalidação;\n"
            "(7) NUNCA fale sobre outros usuários, comunidade, ou dados históricos gerais. "
            "SÓ o gráfico AGORA."
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
                "max_tokens": 340,
                "temperature": 0.4,
                "system": sistema,
                "messages": [{"role": "user", "content":
                    f"TF de operação: {tf_op or '?'}\n"
                    f"Fatos técnicos observados agora (JSON):\n{json.dumps(fatos, ensure_ascii=False)}"}],
            },
            timeout=8.0,
        )
        if r.status_code != 200:
            print(f"NARRAR BOT status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return cache.get("texto")  # usa último válido, se houver
        texto = "".join(b.get("text", "") for b in r.json().get("content", []))
        texto = texto.strip()
        if not texto:
            return cache.get("texto")
        _NARR_BOT_CACHE[bot_token] = {"assinatura": ass_agora, "ts": agora, "texto": texto[:500]}
        return texto[:500]
    except Exception as e:
        print(f"NARRAR BOT erro: {e}", file=sys.stderr)
        return cache.get("texto")


def _narracao_bot(det: dict, s: dict) -> str:
    """v6.49 — a VOZ DO BOT no monitor: narra em uma frase o que o executor está
    fazendo agora, montada dos dados mecânicos do snapshot (sem custo de IA).
    A voz da IA (leitura/confirmação) fica no outro quadro — os dois lados."""
    try:
        pos = int(s.get("posicoes_abertas") or 0)
    except Exception:
        pos = 0
    tf = str(det.get("tfop") or "").lower()
    zmap = {"1m": "z1", "5m": "z5", "15m": "z15", "30m": "z15", "60m": "z60",
            "1h": "z60", "4h": "z240", "1d": "zD", "d1": "zD"}
    zona = det.get(zmap.get(tf, "z15"))
    ztxt = {"acima": "acima do canal", "dentro": "dentro do canal (lateral)",
            "abaixo": "abaixo do canal"}.get(str(zona or "").lower(), "canal sem leitura")
    preco = det.get("preco")
    ptxt = f" · preço {preco}" if preco not in (None, "", "0") else ""
    if pos > 0:
        lado = str(det.get("lado") or "").lower()
        ltxt = "Comprado" if ("buy" in lado or "compra" in lado) else ("Vendido" if ("sell" in lado or "venda" in lado) else f"{pos} posição(ões)")
        extras = []
        if det.get("entrada"): extras.append(f"entrada {det['entrada']}")
        if det.get("tp"): extras.append(f"TP {det['tp']}")
        if det.get("sl"): extras.append(f"SL {det['sl']}")
        if det.get("idade"): extras.append(f"há {det['idade']}")
        flu = s.get("lucro_flutuante")
        flutxt = f" · flutuante {'+' if (flu or 0) >= 0 else ''}{flu}" if flu is not None else ""
        return f"{ltxt} ({pos} pos.) · " + " · ".join(extras[:3]) + f"{flutxt}{ptxt} · {ztxt} no {tf or '?'}"
    return f"Sem posição{ptxt} · {ztxt} no {tf or '?'} · aguardando o gatilho da estratégia"


def _bot_narracao_hibrida(det, s, b):
    """v6.70 — CAMINHO C (híbrido):
      1. Calcula fatos técnicos DETERMINÍSTICOS dos candles (topos, fundos,
         padrões, momentum, gatilhos concretos).
      2. Passa os fatos pra Haiku formatar em texto de trader executor.
      3. Cache 30s por bot_token pra economizar tokens.
    Fallback: se algo falhar (sem candles, IA fora, chave ausente), cai
    no _narracao_bot antigo — sempre entrega algo, nunca vazio."""
    try:
        tf_op = str(det.get("tfop") or "").lower()
        # pega os candles do TF do operação
        chave_op = {"1m": "c1m", "5m": "c5m", "15m": "c15m",
                    "30m": "c15m", "60m": "c5m", "1h": "c5m",
                    "4h": "c4h", "1d": "c4h", "d": "c4h"}.get(tf_op)
        candles_str = det.get(chave_op) if chave_op else None
        if not candles_str:
            # sem candles (bot velho): fallback
            return _narracao_bot(det, s)
        fatos = _analisar_bot_tecnica(
            candles_str,
            det.get("emaH"), det.get("emaL"),
            det.get("preco"), det.get("regime"),
            (s or {}).get("posicoes_abertas"),
            offmind=det.get("offmind"),  # v6.71: usa detectores do OffMind
        )
        if not fatos:
            return _narracao_bot(det, s)
        # v6.82 — SCANNER MULTI-TF + ESTADO DO CAÇADOR entram nos fatos
        pac = _scanner_pacote(det)
        if pac:
            fatos["scanner_tfs"] = pac.get("tfs")
            if pac.get("cascata_reversao"):
                fatos["cascata_reversao"] = pac["cascata_reversao"]
            if pac.get("alinhamento"):
                fatos["alinhamento_tfs"] = pac["alinhamento"]
        eg = _estado_gatilho(fatos, det, (b or {}).get("id"))
        if eg:
            fatos["estado_gatilho"] = eg
        texto = _narrar_bot_analitico(fatos, tf_op, (b or {}).get("bot_token"))
        # Se a IA não devolveu (sem chave, falha, etc): fallback
        return texto if texto else _narracao_bot(det, s)
    except Exception as _e:
        try: print(f"[bot-hibrido] {_e}")
        except Exception: pass
        return _narracao_bot(det, s)


# ════════════════════════════════════════════════════════════════════════════
#  v6.67 — /monitor/analise (GET) + /monitor/analise/tick (POST)
#
#  O cockpit do bot faz polling de 6s aqui:
#    - GET  /monitor/analise?bot_id=X&desde=<iso>  → análises novas
#    - POST /monitor/analise/tick                  → dispara análise se merecer
#
#  O TICK decide se vale analisar agora (assinatura mudou, silêncio > 90s,
#  respeita cooldown de 30s). Se não vale, 200 sem gerar — custo zero de IA.
# ════════════════════════════════════════════════════════════════════════════

class AnlTickIn(BaseModel):
    user_id: str
    bot_id: int


def _momentum_semantico(candles_str):
    """v6.68 — traduz string de candles "O,H,L,C;O,H,L,C;..." em RESUMO
    SEMANTICO curto pra IA usar como mentor humano. Nao passa candles crus
    (custaria tokens caros); passa uma leitura descritiva do momentum
    recente daquele TF: forca, direcao, corpo, extremos."""
    try:
        cs = []
        for parte in str(candles_str or "").split(";"):
            vs = parte.split(",")
            if len(vs) == 4:
                try: cs.append([float(x) for x in vs])
                except Exception: pass
        n = len(cs)
        if n < 3: return None
        ult = cs[-5:] if n >= 5 else cs
        altas = sum(1 for v in ult if v[3] > v[0])
        baixas = sum(1 for v in ult if v[3] < v[0])
        doji = len(ult) - altas - baixas
        if len(ult) >= 4:
            corpo_ini = sum(abs(v[3] - v[0]) for v in ult[:2]) / 2
            corpo_fim = sum(abs(v[3] - v[0]) for v in ult[-2:]) / 2
            if corpo_fim > corpo_ini * 1.3: tendencia_corpo = "crescentes"
            elif corpo_fim < corpo_ini * 0.7: tendencia_corpo = "encolhendo"
            else: tendencia_corpo = "estaveis"
        else:
            tendencia_corpo = "estaveis"
        highs = [v[1] for v in cs]
        lows  = [v[2] for v in cs]
        rng_hi = max(highs); rng_lo = min(lows)
        preco = cs[-1][3]
        if rng_hi > rng_lo:
            pos_pct = (preco - rng_lo) / (rng_hi - rng_lo)
            if pos_pct > 0.75: posicao = "proximo do topo do range recente"
            elif pos_pct < 0.25: posicao = "proximo do fundo do range recente"
            else: posicao = "no meio do range recente"
        else:
            posicao = "range apertado"
        if altas >= 4 and baixas == 0:
            recentes = f"{altas} velas de alta consecutivas, corpos {tendencia_corpo}"
        elif baixas >= 4 and altas == 0:
            recentes = f"{baixas} velas de baixa consecutivas, corpos {tendencia_corpo}"
        elif altas >= 3 and baixas <= 1:
            recentes = f"predominancia de alta ({altas} de {len(ult)}), corpos {tendencia_corpo}"
        elif baixas >= 3 and altas <= 1:
            recentes = f"predominancia de baixa ({baixas} de {len(ult)}), corpos {tendencia_corpo}"
        elif doji >= 2:
            recentes = f"indecisao - {doji} dojis nas ultimas {len(ult)}"
        else:
            recentes = f"alternancia ({altas} de alta / {baixas} de baixa), corpos {tendencia_corpo}"
        ultima = cs[-1]
        ult_desc = None
        if ultima[0] > 0:
            var_pct = (ultima[3] - ultima[0]) / ultima[0] * 100
            if abs(var_pct) < 0.05:
                ult_desc = "ultima vela quase parada"
            elif var_pct > 0:
                ult_desc = f"ultima vela fechou em alta ({var_pct:+.2f}% vs abertura)"
            else:
                ult_desc = f"ultima vela fechou em baixa ({var_pct:+.2f}% vs abertura)"
        out = {"velas": n, "recentes": recentes, "posicao": posicao}
        if ult_desc: out["ultima"] = ult_desc
        return out
    except Exception:
        return None


def _anl_ler_leitura(sb, user_id, bot_id):
    """Reaproveita o shape do /monitor/leitura, mas 1 bot só. Rápido."""
    try:
        bots = (sb.table("conector_bots")
                .select("id,nome,simbolo,bot_token,ultimo_ping")
                .eq("user_id", user_id).eq("id", bot_id).limit(1).execute().data or [])
        if not bots:
            return None
        b = bots[0]
        snaps = (sb.table("conector_snapshots")
                 .select("simbolo,detalhe_json,equity,balance,lucro_flutuante,posicoes_abertas")
                 .eq("bot_token", b.get("bot_token")).order("id", desc=True)
                 .limit(1).execute().data or [])
        if not snaps:
            return None
        s = snaps[0]; det = s.get("detalhe_json") or {}
        om = det.get("offmind") or {}
        zonas = {tf: (det.get(k).strip().lower() if isinstance(det.get(k), str) else None)
                 for k, tf in (("z1", "1m"), ("z5", "5m"), ("z15", "15m"),
                               ("z60", "1H"), ("z240", "4H"), ("zD", "D"))}
        return {
            "simbolo": det.get("simbolo") or s.get("simbolo") or b.get("simbolo"),
            "tf_op": (str(det.get("tfop") or "").lower()) or None,
            "preco": det.get("preco"),
            "ema_h": det.get("emaH"),
            "ema_l": det.get("emaL"),
            "posicoes": s.get("posicoes_abertas"),
            "flutuante": s.get("lucro_flutuante"),
            "regime": det.get("regime"),
            "padroes": om.get("padroes") or [],
            "estrutura": [e for e in (om.get("estrutura") or []) if e.get("testando")][:4],
            "zonas": zonas,
            "confirmacao": det.get("confirmacao"),
            "narracao_bot": _bot_narracao_hibrida(det, s, b),
            # v6.82 — pente-fino multi-TF do BOT vira dado pra IA também
            "scanner": _scanner_pacote(det),
            "momentum_tfs": {
                tf: _momentum_semantico(det.get(chave))
                for chave, tf in (("c5m", "5m"), ("c15m", "15m"),
                                  ("c60m", "60m"), ("c4h", "4h"))
                if _momentum_semantico(det.get(chave))
            },
        }
    except Exception:
        return None


@app.get("/monitor/analise")
def monitor_analise(bot_id: int, desde: Optional[str] = None):
    """Análises cruzadas do bot mais novas que 'desde' (ISO). Se 'desde' é
    omitido, devolve TODO o histórico (o cockpit acabou de abrir)."""
    hist = list(_anl_hist(bot_id))
    if desde:
        hist = [a for a in hist if (a.get("ts") or "") > desde]
    return {"analises": hist}


@app.post("/monitor/analise/tick")
def monitor_analise_tick(inp: AnlTickIn):
    """O cockpit chama a cada 6s. Verifica se vale analisar:
      - assinatura do momento mudou (regime, padrões, posições) -> analisa
      - senão, silêncio > 90s -> analisa observação
      - respeita cooldown geral de 30s pra não spamar
    Retorna se analisou ou não (o front só usa pra debug)."""
    sb = _sb_admin()
    if sb is None:
        return {"analisou": False, "motivo": "supabase_off"}
    leit = _anl_ler_leitura(sb, inp.user_id, inp.bot_id)
    if not leit:
        return {"analisou": False, "motivo": "sem_leitura"}
    agora = _time_anl.time()
    ass_agora = _anl_assinatura(leit)
    ult = _ANL_LAST.get(inp.bot_id) or {}
    ass_ant = ult.get("assinatura") or ""
    ts_ant = float(ult.get("ts") or 0)
    tempo_desde = agora - ts_ant
    # gatilho: assinatura mudou (novo padrão, virou regime, posição abriu/fechou)
    if ass_agora != ass_ant and tempo_desde >= _ANL_COOLDOWN_SEG:
        gatilho = "padrao"
        try:
            reg_agora = ((leit.get("regime") or {}).get("estado") or "").lower()
            if ass_ant:
                reg_ant = ass_ant.split("|", 1)[0]
                if reg_agora != reg_ant:
                    gatilho = "regime"
        except Exception: pass
        _analisar_por_gatilho(sb, inp.bot_id, inp.user_id, gatilho, leitura_atual=leit)
        return {"analisou": True, "gatilho": gatilho}
    # gatilho: silêncio prolongado -> observação factual
    if tempo_desde >= _ANL_SILENCIO_SEG:
        _analisar_por_gatilho(sb, inp.bot_id, inp.user_id, "silencio", leitura_atual=leit)
        return {"analisou": True, "gatilho": "silencio"}
    return {"analisou": False, "motivo": "sem_novidade",
            "espera_s": int(max(0, _ANL_SILENCIO_SEG - tempo_desde))}


class VisaoOpIn(BaseModel):
    user_id: str
    bot_id: int
    texto: Optional[str] = None
    imagem_b64: Optional[str] = None
    imagem_tipo: Optional[str] = None


@app.post("/monitor/visao")
def monitor_visao(inp: VisaoOpIn):
    """v6.81 — VISÃO DO OPERADOR: texto e/ou print entram na análise cruzada
    por 2h. Dispara análise IMEDIATA (mesma prioridade de evento ABRIU/FECHOU).
    Orientação de LEITURA — nunca execução: ordem só pelos botões do Copiloto."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    dono = (sb.table("conector_bots").select("id")
            .eq("user_id", inp.user_id).eq("id", inp.bot_id)
            .limit(1).execute().data or [])
    if not dono:
        raise HTTPException(status_code=404, detail="Bot não encontrado")
    texto = (inp.texto or "").strip()[:500]
    img = (inp.imagem_b64 or "").strip()
    if img and len(img) > 7_000_000:      # ~5MB decodificado
        raise HTTPException(status_code=413, detail="Print muito grande (máx ~5MB)")
    if not texto and not img:
        raise HTTPException(status_code=400, detail="Envie um texto e/ou um print")
    resumo_img = None
    if img:
        resumo_img = _visao_op_extrair_print(img, inp.imagem_tipo,
                                             _anl_idioma_do_user(sb, inp.user_id))
    if not texto and not resumo_img:
        raise HTTPException(status_code=422,
                            detail="Não consegui ler o print — tenta descrever em texto")
    agora = _time_anl.time()
    _VISAO_OP[inp.bot_id] = {"texto": texto or None, "resumo_img": resumo_img,
                             "ts": agora, "expira": agora + _VISAO_OP_TTL_SEG}
    # análise IMEDIATA com a visão nova (não espera tick nem cooldown —
    # mesma prioridade de evento ABRIU/FECHOU)
    try:
        leit = _anl_ler_leitura(sb, inp.user_id, inp.bot_id)
        if leit:
            _analisar_por_gatilho(sb, inp.bot_id, inp.user_id, "visao_operador",
                                  leitura_atual=leit)
    except Exception:
        pass
    return {"ok": True, "visao": _visao_op_publica(inp.bot_id)}


@app.delete("/monitor/visao")
def monitor_visao_limpar(user_id: str, bot_id: int):
    """v6.81 — limpa a visão ativa do operador pro bot."""
    sb = _sb_admin()
    if sb is not None:
        dono = (sb.table("conector_bots").select("id")
                .eq("user_id", user_id).eq("id", bot_id)
                .limit(1).execute().data or [])
        if not dono:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
    _VISAO_OP.pop(bot_id, None)
    return {"ok": True}


@app.get("/monitor/leitura")
def monitor_leitura(user_id: str):
    """v6.47 — OLHOS DO MONITOR (Leitura ao Vivo): devolve, por bot do usuário,
    o que o bot está ENXERGANDO agora — zonas do canal EMA20 H/L por TF, regime
    sintetizado, padrões se FORMANDO (OffMind na mecânica 1m/5m/15m), níveis de
    topo/fundo sendo testados (estrutura 30m/60m/4h), a última leitura da IA e
    uma janela de candles 15m pro mini-gráfico. Tudo já viaja no snapshot — a
    rota só abre a janela pro front. Read-only."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    try:
        bots = (sb.table("conector_bots")
                .select("id,nome,simbolo,bot_token,excluido,ultimo_ping")
                .eq("user_id", user_id).execute().data or [])
        bots = [b for b in bots if not b.get("excluido")]
        snaps = (sb.table("conector_snapshots")
                 .select("bot_token,simbolo,detalhe_json,equity,balance,lucro_flutuante,posicoes_abertas")
                 .eq("user_id", user_id).order("id", desc=True)
                 .limit(150).execute().data or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na leitura: {e}")
    ultimo = {}
    for s in snaps:
        tk = s.get("bot_token")
        if tk and tk not in ultimo:
            ultimo[tk] = s              # snaps vêm do mais novo pro mais velho
    saida = []
    for b in bots:
        s = ultimo.get(b.get("bot_token")) or {}
        det = s.get("detalhe_json") or {}
        zonas = {tf: (det.get(k).strip().lower() if isinstance(det.get(k), str) else None)
                 for k, tf in (("z1", "1m"), ("z5", "5m"), ("z15", "15m"),
                               ("z60", "1H"), ("z240", "4H"), ("zD", "D"))}
        def _parse_c(chave):
            out = []
            for parte in str(det.get(chave) or "").split(";"):
                vs = parte.split(",")
                # v6.72: aceita 4 (bots velhos) ou 5 valores (bots novos com volume)
                if len(vs) >= 4:
                    try:
                        out.append([float(x) for x in vs[:5]])
                    except Exception:
                        pass
            return out
        c15 = _parse_c("c15m")
        # v6.51: o gráfico do card é o TF que o usuário ARRASTOU no MT5 (tfop)
        tf_op = str(det.get("tfop") or "").lower()
        chave_op = {"1m": "c1m", "5m": "c5m", "15m": "c15m", "30m": "c30m",
                    "60m": "c60m", "1h": "c60m", "4h": "c4h", "1d": "c4h"}.get(tf_op, "c15m")
        c_op = _parse_c(chave_op) or c15
        def _f(v):
            try:
                return float(v)
            except Exception:
                return None
        om = det.get("offmind") or {}
        online = False
        if b.get("ultimo_ping"):
            try:
                _ping = _dt.fromisoformat(str(b["ultimo_ping"]).replace("Z", "+00:00"))
                online = (_dt.now(_tz.utc) - _ping).total_seconds() < OFFLINE_APOS_SEGUNDOS
            except Exception:
                pass
        # v6.53 — FIX SÍMBOLO/FLUTUANTE:
        # 1) o "simbolo" do bot no banco é o do momento do envio (às vezes fica
        #    genérico tipo "US30"); o símbolo REAL é o que vem no snapshot, que
        #    o EA lê do gráfico atual (_Symbol). PRIORIZAR o do snapshot.
        # 2) flutuante NULL virava 0.0 no front — passa a devolver o número real
        #    (float) e o front só desenha se != null (evita "+0,00" falso).
        _sim_real = det.get("simbolo") or s.get("simbolo") or b.get("simbolo")
        _flu = s.get("lucro_flutuante")
        if _flu is None and det.get("lucro") is not None:
            try: _flu = float(det.get("lucro"))
            except Exception: pass
        saida.append({
            "id": b.get("id"), "nome": b.get("nome"), "online": online,
            "equity": s.get("equity"), "balance": s.get("balance"),
            "flutuante": _flu, "posicoes": s.get("posicoes_abertas"),
            "narracao_bot": _bot_narracao_hibrida(det, s, b) if s else None,
            "simbolo": _sim_real,
            "zonas": zonas,
            "regime": det.get("regime"),
            "padroes": om.get("padroes") or [],
            "estrutura": [e for e in (om.get("estrutura") or []) if e.get("testando")][:4],
            "leitura": (det.get("leitura") or {}).get("texto"),
            "confirmacao": det.get("confirmacao"),
            "candles15": c15[-14:],
            "tf_op": tf_op or None,
            "candles_op": c_op[-18:],
            "ema_h": _f(det.get("emaH")), "ema_l": _f(det.get("emaL")),
            "preco": _f(det.get("preco")),
            # v6.79 — RAIO-X DO MERCADO: canal, ATR, range de lateralizacao e
            # escada de niveis. Deterministico, custo zero de IA.
            "extras": _extras_cockpit(det, s),
            # v6.81 — VISÃO DO OPERADOR: chip 👁 do cockpit lê daqui
            "visao_operador": _visao_op_publica(b.get("id")),
            # v6.82 — SCANNER MULTI-TF (comportamento por TF + cascata + alinhamento)
            "scanner": _scanner_pacote(det),
        })
    return {"bots": saida}


@app.get("/monitor/geral")
def monitor_geral(user_id: str):
    """v6.49 — PERFORMANCE GERAL do topo do Monitor. Só o que é REAL nos dados:
    Equity total, Balance total, Flutuante agora, bots operando (ping <3min),
    em trade (posições>0) e as barras do flutuante por bot. Winners/Losers por
    trade exige P&L no evento fechado (capítulo futuro do prompt do EA)."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    try:
        bots = (sb.table("conector_bots")
                .select("id,nome,bot_token,excluido,ultimo_ping,ultimo_equity,posicoes_abertas")
                .eq("user_id", user_id).execute().data or [])
        bots = [b for b in bots if not b.get("excluido")]
        snaps = (sb.table("conector_snapshots")
                 .select("bot_token,equity,balance,lucro_flutuante,posicoes_abertas")
                 .eq("user_id", user_id).order("id", desc=True)
                 .limit(150).execute().data or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no geral: {e}")
    ult = {}
    for s in snaps:
        tk = s.get("bot_token")
        if tk and tk not in ult:
            ult[tk] = s
    agora = _dt.now(_tz.utc)
    eq = bal = flu = 0.0
    operando = em_trade = 0
    barras = []
    for b in bots:
        s = ult.get(b.get("bot_token")) or {}
        online = False
        if b.get("ultimo_ping"):
            try:
                online = (agora - _dt.fromisoformat(str(b["ultimo_ping"]).replace("Z", "+00:00"))).total_seconds() < OFFLINE_APOS_SEGUNDOS
            except Exception:
                pass
        if online:
            operando += 1
            eq += float(s.get("equity") or 0)
            bal += float(s.get("balance") or 0)
            f = float(s.get("lucro_flutuante") or 0)
            flu += f
            if int(s.get("posicoes_abertas") or 0) > 0:
                em_trade += 1
            barras.append({"nome": b.get("nome"), "flutuante": round(f, 2)})
    return {"equity_total": round(eq, 2), "balance_total": round(bal, 2),
            "flutuante_total": round(flu, 2), "operando": operando,
            "em_trade": em_trade, "total_bots": len(bots), "barras": barras}


@app.get("/monitor/eventos")
def monitor_eventos(user_id: str, limite: int = 30):
    """v6.49 — AUDITORIA em tempo real: cada entrada/saída dos bots (evento
    bot_aberto/bot_fechado com lado/símbolo/preço/hora), do mais novo pro mais
    velho. É o livro-razão vivo do Monitor.
    v6.66: cada linha ganha bot_nome. Eventos NOVOS já carregam bot_nome no
    detalhe_json (v6.66+ do /conector/evento). Eventos VELHOS (gravados sem
    bot_nome) recebem fallback: casa por símbolo com os bots do usuário."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    try:
        evs = (sb.table("agente_eventos")
               .select("tipo,detalhe_json,criado_em")
               .eq("user_id", user_id).like("tipo", "bot_%")
               .order("id", desc=True).limit(max(1, min(int(limite or 30), 100)))
               .execute().data or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro nos eventos: {e}")
    # fallback por símbolo pra eventos gravados antes da v6.66 (sem bot_nome
    # no detalhe_json). Cobre o caso comum: 1 bot por ativo. Se o usuário
    # tem 2 bots no mesmo símbolo, mostra o primeiro — imperfeito, mas
    # melhor que "?". Zero SELECT extra se todos os eventos já têm bot_nome.
    _precisa_fallback = any(not ((e.get("detalhe_json") or {}).get("bot_nome"))
                            for e in evs)
    bots_por_sim = {}
    if _precisa_fallback:
        try:
            _bs = (sb.table("conector_bots").select("nome,simbolo")
                   .eq("user_id", user_id).execute().data or [])
            for b in _bs:
                s = str(b.get("simbolo") or "").upper()
                if s and s not in bots_por_sim:
                    bots_por_sim[s] = b.get("nome") or ""
        except Exception:
            pass
    out = []
    for e in evs:
        d = e.get("detalhe_json") or {}
        nome = (d.get("bot_nome")
                or bots_por_sim.get(str(d.get("simbolo") or "").upper())
                or "")
        out.append({"quando": e.get("criado_em"),
                    "tipo": str(e.get("tipo") or "").replace("bot_", ""),
                    "lado": d.get("lado"), "simbolo": d.get("simbolo"),
                    "preco": d.get("preco"),
                    "bot_nome": nome})
    return {"eventos": out}


@app.get("/conector/meus-bots")
def conector_meus_bots(bot_token: str):
    """Lista os bots do usuário DONO deste token — pro card 'Meus bots' do
    conector. Resolve o user_id pelo token, então o conector não precisa saber
    o user_id. Devolve nome, símbolo, magic, filename e online/offline."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    dono = _bot_por_token(sb, bot_token)
    if not dono:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    uid = dono.get("user_id")
    try:
        r = (sb.table("conector_bots").select("*")
             .eq("user_id", uid).order("criado_em", desc=True).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar bots: {e}")
    agora = _dt.now(_tz.utc)
    bots = []
    for b in (r.data or []):
        if b.get("excluido"):
            continue
        online = False
        if b.get("ultimo_ping"):
            try:
                ping = _dt.fromisoformat(str(b["ultimo_ping"]).replace("Z", "+00:00"))
                online = (agora - ping).total_seconds() < OFFLINE_APOS_SEGUNDOS
            except Exception:
                pass
        nome = b.get("nome") or "Meu Bot"
        filename = b.get("mq5_filename") or (_nome_arquivo_bot(nome) + ".mq5")
        tem_mq5 = bool(b.get("mq5_codigo"))
        bots.append({
            "id": b.get("id"), "nome": nome, "simbolo": b.get("simbolo") or "",
            "magic_number": b.get("magic_number"), "filename": filename,
            "online": online, "tem_mq5": tem_mq5,
            "ultimo_equity": b.get("ultimo_equity"),
        })
    return {"bots": bots}


@app.get("/conector/tokens")
def conector_tokens(bot_token: str):
    """MULTI-BOT: dado UM token válido, devolve os tokens de TODOS os bots do
    MESMO usuário — pro conector vigiar/validar todos ao mesmo tempo (um conector,
    vários bots). Resolve o dono pelo token; só bots ativos (não excluídos).

    NOTA DE SEGURANÇA (decisão consciente): diferente das outras rotas, que fazem
    pop do bot_token, esta ENTREGA os tokens ao conector — é o que o multi-bot
    exige. Requer um token válido de um bot do próprio usuário: quem não tem um
    token do usuário não recebe os outros. O token segue sendo a credencial do bot
    (deriva o magic, autentica o snapshot)."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    dono = _bot_por_token(sb, bot_token)
    if not dono:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    uid = dono.get("user_id")
    try:
        r = (sb.table("conector_bots").select("*")
             .eq("user_id", uid).order("criado_em", desc=True).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar tokens: {e}")
    tokens = []
    for b in (r.data or []):
        if b.get("excluido"):
            continue
        tk = (b.get("bot_token") or "").strip()
        if not tk:
            continue
        tokens.append({
            "id": b.get("id"),
            "nome": b.get("nome") or "Meu Bot",
            "bot_token": tk,
            "filename": b.get("mq5_filename") or "",
            "magic_number": _magic_do_token(tk),
            "simbolo": b.get("simbolo") or "",
        })
    return {"tokens": tokens}


@app.get("/conector/bot/mq5")
def conector_bot_mq5(bot_token: str, bot_id: int):
    """Devolve o .mq5 salvo de um bot pro conector REINSTALAR sem regenerar.
    Valida que o bot pertence ao dono do token. Se o bot foi criado antes de
    passarmos a salvar o código, devolve tem_mq5=False (o usuário reenvia pelo
    Editor)."""
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    dono = _bot_por_token(sb, bot_token)
    if not dono:
        raise HTTPException(status_code=401, detail="bot_token inválido")
    try:
        r = (sb.table("conector_bots").select("id,user_id,nome,mq5_codigo,mq5_filename")
             .eq("id", bot_id).limit(1).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar bot: {e}")
    if not r.data:
        raise HTTPException(status_code=404, detail="Bot não encontrado")
    b = r.data[0]
    if str(b.get("user_id")) != str(dono.get("user_id")):
        raise HTTPException(status_code=403, detail="Sem permissão para este bot")
    codigo = b.get("mq5_codigo") or ""
    if not codigo.strip():
        return {"tem_mq5": False, "filename": b.get("mq5_filename") or ""}
    nome = b.get("nome") or "Meu Bot"
    filename = b.get("mq5_filename") or (_nome_arquivo_bot(nome) + ".mq5")
    return {"tem_mq5": True, "codigo": codigo, "filename": filename}


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
    # catálogo COMPLETO (todos os ativos da biblioteca), marcando quais já têm
    # dados — pra o seletor da matriz mostrar tudo (ex: BTC/USD antes de rodar)
    com_dados = {o["ativo"] for o in out}
    catalogo = [{"ativo": nome, "tem_dados": nome in com_dados}
                for nome in _bib_lista_todos_ativos()]
    return {"ativos": out, "total": len(out), "catalogo": catalogo}


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
         .order("data_evento", desc=False))
    rows = _sb_ler_paginado(lambda a, b: q.range(a, b))

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
    _q_cal = (sb.table("calendario_economico")
            .select("titulo,moeda,impacto,data_evento")
            .gte("data_evento", de.isoformat())
            .lte("data_evento", ate.isoformat())
            .order("data_evento", desc=False))
    rows = _sb_ler_paginado(lambda a, b: _q_cal.range(a, b))
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
    _q_cal2 = (sb.table("calendario_economico")
            .select("titulo,moeda,impacto,data_evento,forecast,previous,actual")
            .gte("data_evento", de.isoformat())
            .lte("data_evento", ate.isoformat())
            .order("data_evento", desc=False))
    rows = _sb_ler_paginado(lambda a, b: _q_cal2.range(a, b))
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
            # v6.45 — PAGINAÇÃO: o PostgREST/Supabase tem teto padrão de ~1000
            # linhas por requisição MESMO pedindo .limit(8000). Com a biblioteca
            # completa (6.720 linhas), a vitrine agregava só ~15% do banco — por
            # isso estratégias plenamente medidas apareciam "Em medição".
            rows = []
            _pg = 0
            while True:
                lote = (sb.table("estudo_biblioteca")
                        .select("estrategia_id,ativo,sharpe,profit_factor,retorno,win_rate,trades,forca,timeframe,periodo")
                        .range(_pg * 1000, _pg * 1000 + 999).execute().data or [])
                rows.extend(lote)
                if len(lote) < 1000 or _pg >= 15:   # teto de segurança: 16k linhas
                    break
                _pg += 1
            print(f"[vitrine] biblioteca: {len(rows)} linhas agregadas ({_pg + 1} páginas)")
            # ── SEM AÇÕES NA VITRINE (v6.41) ─────────────────────────────────
            # Ações (Magnificent 7, Ações Pro, B3) ficam FORA da vitrine: o bull
            # de longo prazo delas (Google/Microsoft etc.) distorce as médias e
            # não é referência estável — os setores estão mudando. A vitrine
            # compara a estratégia em Índices, Forex, Commodities e Cripto.
            # (As ações continuam no catálogo pra quem quiser testar por conta.)
            _CATS_ACOES = ("Magnificent 7", "Ações Pro", "B3 — Brasil")
            _ATIVOS_ACOES = set()
            for _cat in _CATS_ACOES:
                for _a in CATALOGO_ATIVOS.get(_cat, []):
                    _ATIVOS_ACOES.add(_a.get("nome"))
            rows = [r for r in rows if r.get("ativo") not in _ATIVOS_ACOES]
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
                # acumula sharpe + trades + timeframe por ativo (p/ achar onde a estratégia
                # mais funciona). Estratégias diárias são avaliadas só no D1 (ver _TF_NATURAL);
                # as demais, pelo melhor timeframe robusto.
                ativo_nome = r.get("ativo")
                if ativo_nome:
                    pa = por_ativo.setdefault(eid, {}).setdefault(ativo_nome, {"combos": []})
                    pa["combos"].append({"sh": float(r.get("sharpe") or 0),
                                         "trades": int(r.get("trades") or 0),
                                         "tf": str(r.get("timeframe") or "").strip().lower(),
                                         "periodo": str(r.get("periodo") or "").strip(),
                                         "ret": float(r.get("retorno") or 0),
                                         "wr": float(r.get("win_rate") or 0)})
            # top 3 ativos por estratégia
            # ── FILTRO DE ROBUSTEZ ──────────────────────────────────────────
            # Estratégias DIÁRIAS por natureza (leem o D1: Escalonada, Suporte&Resistência
            # do dia anterior, Fechamento Ímã, Gap de abertura) são avaliadas SÓ no
            # timeframe diário — é onde elas operam de verdade. Avaliá-las no melhor TF
            # qualquer deixava resultados intraday (5m/15m) sem sentido dominarem o ranking
            # e empurrarem pra fora ativos que vão bem no diário (ex: BTC na Escalonada).
            # As demais estratégias continuam pelo MELHOR timeframe robusto.
            # Critérios (iguais p/ ambas): combo com trades suficientes, mín. de medições,
            # sharpe acima do piso. Sem ativos robustos -> top vazio -> fallback "mercados".
            _MIN_BACKTESTS_ATIVO = 2     # nº mínimo de medições por ativo
            _MIN_TRADES_COMBO    = 20    # trades mínimos no combo (mesma régua do estudo)
            _PISO_SHARPE_ATIVO   = 0.5   # melhor sharpe mínimo p/ ser sugerível
            # estratégias que LEEM o D1: avaliadas só no diário
            _TF_NATURAL = {
                "tendencia_diaria_piramide": "1d",   # Escalonada
                "sr_dia_anterior": "1d",             # Suporte & Resistência do dia anterior
                "fechamento_ima": "1d",              # Fechamento Anterior como Ímã
                "abertura_gap": "1d",                # Gap de Abertura
            }
            # ── CURADORIA DO DONO ───────────────────────────────────────────
            # Ativos fixados manualmente em cards específicos: entram SEMPRE na
            # frente da linha de ativos, independente do ranking automático.
            # Motivo: algumas estratégias (ex: a Escalonada, com escalonamento de
            # lote) não são bem capturadas pela métrica de backtest padrão — a
            # decisão de exibição é do dono, que fará a revisão completa da vitrine.
            _ATIVOS_FIXOS_VITRINE = {
                "tendencia_diaria_piramide": ["BTC/USD"],   # Escalonada — decisão do dono
            }
            top_ativos_por_est = {}
            _MELHOR_COMBO_EST = {}
            for eid, ativos in por_ativo.items():
                tf_natural = _TF_NATURAL.get(eid)   # None p/ estratégias multi-timeframe
                ranking = []
                melhor_combo_do_ativo = {}
                for ativo_nome, d in ativos.items():
                    combos = d["combos"]
                    if len(combos) < _MIN_BACKTESTS_ATIVO:
                        continue
                    if tf_natural:
                        # estratégia diária: só conta o combo do timeframe natural (D1)
                        robustos = [c for c in combos
                                    if c["tf"] == tf_natural and c["trades"] >= _MIN_TRADES_COMBO]
                    else:
                        # multi-timeframe: melhor combo entre os que têm trades suficientes
                        robustos = [c for c in combos if c["trades"] >= _MIN_TRADES_COMBO]
                    # v6.41: combo precisa ter dado RETORNO POSITIVO — a vitrine não
                    # pode destacar um ativo que, testado no clique, sai negativo.
                    robustos = [c for c in robustos if c["ret"] > 0]
                    if not robustos:
                        continue
                    melhor = max(robustos, key=lambda c: c["sh"])
                    if melhor["sh"] < _PISO_SHARPE_ATIVO:
                        continue
                    melhor_combo_do_ativo[ativo_nome] = melhor
                    ranking.append((ativo_nome, melhor["sh"], len(combos)))
                ranking.sort(key=lambda x: x[1], reverse=True)
                auto = [nome for (nome, _sh, _n) in ranking[:3]]
                # melhor combo do 1º ativo do card (fixo do dono tem prioridade se
                # tiver combo robusto; senão cai pro 1º do ranking automático)
                _prefer = (_ATIVOS_FIXOS_VITRINE.get(eid, []) + auto)
                for _nome in _prefer:
                    mc = melhor_combo_do_ativo.get(_nome)
                    if mc:
                        _MELHOR_COMBO_EST[eid] = {"ativo": _nome, "periodo": mc["periodo"],
                                                  "timeframe": mc["tf"],
                                                  "retorno": round(mc["ret"], 2),
                                                  "win_rate": round(mc["wr"], 1)}
                        break
                fixos = _ATIVOS_FIXOS_VITRINE.get(eid, [])
                if fixos:
                    # fixos na frente, sem duplicar, completa com o ranking até 3
                    top_ativos_por_est[eid] = list(dict.fromkeys(fixos + auto))[:3]
                else:
                    top_ativos_por_est[eid] = auto
            def _med(xs):
                xs = [x for x in xs if x is not None]
                return round(sum(xs) / len(xs), 2) if xs else None
            for eid, a in acc.items():
                medias[eid] = {
                    "sharpe_medio": _med(a["sh"]),
                    "pf_medio": _med(a["pf"]),
                    "retorno_medio": _med(a["ret"]),
                    "winrate_medio": _med(a["wr"]),
                    "combos": a["n"],
                    "forte_pct": round(100 * a["forte"] / a["n"]) if a["n"] else 0,
                    "top_ativos": top_ativos_por_est.get(eid, []),
                    "melhor_combo": _MELHOR_COMBO_EST.get(eid),
                }
        except Exception as e:
            print(f"[vitrine] erro ao agregar: {e}")

    # v6.41: fallback "mercados" dos cards também sai sem ações
    _VITRINE_ACOES_OUT = set()
    for _cat in ("Magnificent 7", "Ações Pro", "B3 — Brasil"):
        for _a in CATALOGO_ATIVOS.get(_cat, []):
            _VITRINE_ACOES_OUT.add(_a.get("nome"))
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
            "mercados": [x for x in est.get("mercados", []) if x not in _VITRINE_ACOES_OUT],
            "top_ativos": ((m.get("top_ativos")
                            or [x for x in est.get("mercados", []) if x not in _VITRINE_ACOES_OUT])[:3]),
            "melhor_combo": m.get("melhor_combo"),
            "medida": bool(m.get("melhor_combo")),
            "casa": bool(est.get("casa")),
            "codigo": est.get("codigo", ""),
            "sharpe_medio": m.get("sharpe_medio"),
            "pf_medio": m.get("pf_medio"),
            "retorno_medio": m.get("retorno_medio"),
            "winrate_medio": m.get("winrate_medio"),
            "combos": m.get("combos", 0),
            "forte_pct": m.get("forte_pct", 0),
        })
    # v6.43: estratégias MEDIDAS (com combo positivo) primeiro; as "em medição"
    # descem pro fim da grade — a vitrine lidera com o que pode provar.
    itens.sort(key=lambda x: 0 if x.get("medida") else 1)
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
    ativo: str = ""               # ativo selecionado no dropdown (contexto p/ o Editor)
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

# ════════════════════════════════════════════════════════════════════════════
#  /editor/dialogo — IA de DIÁLOGO do Editor (conversa + gera código)
#  Uma chamada ao modelo. Ele DECIDE: só conversa, ou conversa + escreve a
#  estratégia dentro de [[CODIGO]]...[[/CODIGO]]. O backend separa o código
#  (vai pro editor de baixo) do texto (vai pro chat). Sem regra de palavra:
#  quem entende a intenção é a própria IA, lendo o usuário.
#  Modelo: EDITOR_IA_MODELO (default Sonnet — melhor pra escrever código).
# ════════════════════════════════════════════════════════════════════════════
def _editor_dialogo_system(idioma: str) -> str:
    idi = {"pt": "português do Brasil", "en": "English", "es": "español"}.get(idioma, "português do Brasil")
    return f"""Você é a IA do Editor de estratégias do BotTested, uma plataforma de backtesting para traders.

Você CONVERSA com o usuário em {idi}. Ele pode te perguntar qualquer coisa (o que é drawdown, como funciona um indicador, o que pode estar errado na estratégia dele) OU pedir que você monte uma estratégia. Trate tudo como um diálogo natural — não como um formulário.

QUANDO GERAR CÓDIGO:
- Só escreva o código quando o usuário pedir uma estratégia E você já tiver detalhes suficientes pra montá-la (pelo menos a lógica de entrada e de saída).
- Se o pedido for vago (ex.: "quero ganhar dinheiro", "uma estratégia pra lucrar 50 por dia"), NÃO gere. Converse e faça 1 ou 2 perguntas objetivas pra entender o que ele quer (que tipo de sinal, qual indicador, qual ativo, qual estilo).
- Se ele só quer tirar uma dúvida ou conversar, NÃO gere código — apenas responda.

COMO GERAR O CÓDIGO (quando for o caso):
- Escreva uma classe Python da biblioteca backtesting.py (herda de Strategy), com os métodos init() e next(). Use self.I() para indicadores, self.data.Close / self.data.High / self.data.Low, self.buy(), self.position e self.position.close(). O pandas está disponível como pd.
- Coloque o código COMPLETO dentro da tag abaixo, sem crases e sem markdown:
[[CODIGO]]
class MinhaEstrategia(Strategy):
    ...
[[/CODIGO]]
- FORA da tag, escreva uma resposta curta no chat explicando em 1-2 frases o que você montou e dizendo pra ele apertar o botão Run Test pra testar.

EXEMPLO do estilo da casa (canal de EMA das máximas e das mínimas, opera no rompimento):
[[CODIGO]]
class CanalEMAHighLow(Strategy):
    ema_period = 20
    def init(self):
        self.ema_high = self.I(lambda h: pd.Series(h).ewm(span=self.ema_period, adjust=False).mean().values, self.data.High)
        self.ema_low = self.I(lambda l: pd.Series(l).ewm(span=self.ema_period, adjust=False).mean().values, self.data.Low)
    def next(self):
        preco = self.data.Close[-1]
        if not self.position:
            if preco > self.ema_high[-1]:
                self.buy()
        else:
            if preco < self.ema_low[-1]:
                self.position.close()
[[/CODIGO]]

REGRAS IMPORTANTES:
- O backtest SEMPRE roda no ativo selecionado na barra lateral. Então o ativo que você menciona TEM que ser o mesmo que vai ser testado — nunca fale de um ativo diferente do selecionado sem sincronizar.
- Se você montar (ou o usuário pedir) uma estratégia para um ativo ESPECÍFICO, emita ao final, em uma linha própria, a tag [[ATIVO:NOME]] com um destes: EUR/USD, GBP/USD, USD/JPY, AUD/USD, XAU/USD, BTC/USD, S&P500, NAS100, US30, IBOVESPA, USD/BRL. O sistema vai selecionar esse ativo automaticamente para o teste rodar certo — e aí você pode dizer que já deixou o ativo selecionado. Ex.: se montou pro ouro, escreva [[ATIVO:XAU/USD]].
- Se a estratégia serve para qualquer ativo (é genérica), NÃO emita [[ATIVO]] e peça pro usuário escolher o ativo na barra lateral antes de testar.
- NUNCA prometa retorno ou lucro. Resultado é histórico medido, não promessa.
- Texto curto: no máximo 2 parágrafos. Se precisar destacar algo, use HTML simples (<b>, <br>) — nunca markdown.
- Não invente números de desempenho e não fale de detalhes internos da plataforma."""


@app.post("/editor/dialogo")
def editor_dialogo(req: RadarChatReq):
    idioma = req.idioma if req.idioma in ("pt", "en", "es") else "pt"
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return {"ok": False, "resposta": "IA indisponível no momento.", "codigo": None}
    msg = (req.mensagem or "").strip()
    if not msg:
        return {"ok": False, "resposta": "", "codigo": None}
    try:
        import httpx, sys, re as _re
        mensagens = []
        for m in (req.historico or [])[-12:]:
            papel = "assistant" if m.get("role") == "assistant" else "user"
            cont = str(m.get("content", ""))[:4000]
            if cont:
                mensagens.append({"role": papel, "content": cont})
        conteudo = msg[:4000]
        if req.ativo:
            conteudo += f"\n\n[Ativo selecionado agora na barra lateral: {req.ativo}]"
        if req.codigo:
            conteudo += ("\n\n[Código que JÁ está no editor agora, como contexto. "
                         "Se o usuário pedir um ajuste, parta deste código]:\n" + req.codigo[:4000])
        mensagens.append({"role": "user", "content": conteudo})
        modelo = os.environ.get("EDITOR_IA_MODELO", "claude-sonnet-4-6")
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": modelo,
                "max_tokens": 2600,
                "temperature": 0.6,
                "system": _editor_dialogo_system(idioma),
                "messages": mensagens,
            },
            timeout=45.0,
        )
        if r.status_code != 200:
            print(f"EDITOR DIALOGO status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return {"ok": False, "resposta": "Não consegui responder agora. Tente de novo em instantes.", "codigo": None}
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        # ── extrai [[CODIGO]]...[[/CODIGO]] ──
        codigo = None
        m = _re.search(r"\[\[\s*CODIGO\s*\]\](.*?)\[\[\s*/\s*CODIGO\s*\]\]", texto, _re.IGNORECASE | _re.DOTALL)
        if m:
            codigo = m.group(1).strip()
            # remove crases acidentais (```python ... ```)
            codigo = _re.sub(r"^```[a-zA-Z]*\s*\n?", "", codigo)
            codigo = _re.sub(r"\n?\s*```$", "", codigo).strip()
            # tira o bloco do texto visível
            texto = _re.sub(r"\[\[\s*CODIGO\s*\]\].*?\[\[\s*/\s*CODIGO\s*\]\]", "", texto,
                            flags=_re.IGNORECASE | _re.DOTALL).strip()
        # limpa qualquer tag órfã que tenha escapado
        texto = _re.sub(r"\[\[\s*/?\s*CODIGO\s*\]\]", "", texto, flags=_re.IGNORECASE).strip()
        # ── extrai [[ATIVO:NOME]] (qual ativo a estratégia é / deve rodar) ──
        ativo = None
        ma = _re.search(r"\[\[\s*ATIVO\s*:\s*([^\]]+?)\s*\]\]", texto, _re.IGNORECASE)
        if ma:
            ativo = ma.group(1).strip()
            texto = _re.sub(r"\[\[\s*ATIVO\s*:[^\]]*\]\]", "", texto, flags=_re.IGNORECASE).strip()
        if not texto:
            texto = ("Pronto — escrevi a estratégia no editor. Aperta ▶ Run Test pra testar."
                     if codigo else "…")
        return {"ok": True, "resposta": texto, "codigo": codigo, "ativo": ativo}
    except Exception as e:
        print(f"EDITOR DIALOGO erro: {e}")
        return {"ok": False, "resposta": "Não consegui responder agora. Tente de novo em instantes.", "codigo": None}

# ════════════════════════════════════════════════════════════════════════════
#  /editor/analisar-oos — a IA LÊ o resultado da validação out-of-sample e diz,
#  como um mentor, se está bom ou ruim (e POR QUÊ, olhando os números reais) e
#  o que fazer pra melhorar. Diferencial: não é texto genérico por veredito —
#  é análise contextual da amostra específica (ex.: "só 3 trades no teste →
#  ruído, não robustez"). Nunca promete retorno.
# ════════════════════════════════════════════════════════════════════════════
def _analise_oos_system(idioma: str) -> str:
    idi = {"pt": "português do Brasil", "en": "English", "es": "español"}.get(idioma, "português do Brasil")
    return f"""Você é o copiloto de validação do BotTested — um mentor que fala disciplina e nunca prevê o mercado.

Você recebe o resultado de uma validação OUT-OF-SAMPLE (treino 70% / teste 30% nunca visto) de uma estratégia de trading. Responda em {idi}, de forma honesta e didática, cobrindo DUAS coisas:
1) O que esse resultado significa — está bom ou ruim, e POR QUÊ, olhando os números reais que recebeu.
2) O que o usuário pode fazer pra melhorar (ações concretas).

COMO ANALISAR (use os números que recebeu, seja específico):
- Compare treino vs teste. Se o desempenho no teste desabou em relação ao treino → sinal de overfitting (ajustada demais ao passado).
- OLHE O NÚMERO DE TRADES com atenção. Poucos trades (abaixo de ~15-20, e principalmente abaixo de 10) tornam Sharpe, Profit Factor e retorno POUCO CONFIÁVEIS — são ruído de amostra pequena, não robustez. Se o teste tem pouquíssimos trades (ex.: 3), diga claramente que aqueles números altos ali são acaso de janela, não prova de qualidade.
- Um veredito "misto" ou até "robusto" em cima de uma amostra minúscula NÃO é bom sinal — é falta de dados. Seja honesto sobre isso; não deixe o usuário se empolgar com Sharpe alto vindo de 3 operações.

COMO SUGERIR MELHORIA (escolha o que faz sentido pro caso):
- Amostra pequena (poucos trades) → aumentar o período (ex.: de 2 para 5 anos), usar um timeframe menor (gera mais operações), ou testar em outros ativos. O objetivo é ter dados suficientes pra o resultado significar algo.
- Queda forte de treino pra teste → a lógica pode estar superajustada; vale simplificar a estratégia ou reduzir parâmetros.
- Se estiver realmente sólido COM amostra decente → reconheça que é bom sinal, mas reforce que backtest não garante futuro e sugira validar em mais períodos/ativos antes de levar pro MT5.

REGRAS:
- NUNCA prometa retorno ou lucro. Histórico medido, não promessa.
- Seja específico aos números recebidos (cite valores, ex.: "só 3 trades no teste", "o Sharpe caiu de X pra Y"). Nada de frase genérica que serviria pra qualquer resultado.
- HTML simples (<b>) pra destacar — nunca markdown, nunca crases.

FORMATO DA RESPOSTA (obrigatório, exatamente assim, com as duas tags):
[[RESUMO]]
2 a 3 frases curtas com os PRINCIPAIS motivos — o suficiente pro usuário entender na hora se pode confiar ou não e qual o principal passo. Direto, sem enrolação. Pode destacar 1 ou 2 números-chave com <b>.
[[/RESUMO]]
[[DETALHE]]
A análise completa, em no máximo 2 parágrafos: o que o resultado significa (com os números) e o que fazer pra melhorar. É o aprofundamento pra quem quiser ler mais.
[[/DETALHE]]"""


class AnaliseOOSReq(BaseModel):
    treino: dict = {}
    teste: dict = {}
    veredito: dict = {}
    ativo: str = ""
    periodo: str = ""
    timeframe: str = ""
    idioma: str = "pt"


@app.post("/editor/analisar-oos")
def editor_analisar_oos(req: AnaliseOOSReq):
    idioma = req.idioma if req.idioma in ("pt", "en", "es") else "pt"
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return {"ok": False, "analise": ""}
    try:
        import httpx, sys, json as _json
        tr = req.treino or {}
        te = req.teste or {}
        v = req.veredito or {}
        dados = {
            "ativo": req.ativo, "periodo": req.periodo, "timeframe": req.timeframe,
            "treino": {"retorno_pct": tr.get("retorno"), "sharpe": tr.get("sharpe"),
                       "profit_factor": tr.get("profit_factor"), "trades": tr.get("total_trades")},
            "teste_nunca_visto": {"retorno_pct": te.get("retorno"), "sharpe": te.get("sharpe"),
                                  "profit_factor": te.get("profit_factor"), "trades": te.get("total_trades")},
            "veredito_nivel": v.get("nivel"),
        }
        prompt = ("Analise este resultado de validação out-of-sample e responda no formato pedido "
                  "(o que significa + como melhorar):\n" + _json.dumps(dados, ensure_ascii=False))
        modelo = os.environ.get("ANALISE_OOS_MODELO", os.environ.get("EDITOR_IA_MODELO", "claude-sonnet-4-6"))
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": modelo,
                "max_tokens": 800,
                "temperature": 0.5,
                "system": _analise_oos_system(idioma),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=40.0,
        )
        if r.status_code != 200:
            print(f"ANALISE OOS status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return {"ok": False, "analise": ""}
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        import re as _re
        resumo = ""
        detalhe = ""
        mr = _re.search(r"\[\[\s*RESUMO\s*\]\](.*?)\[\[\s*/\s*RESUMO\s*\]\]", texto, _re.IGNORECASE | _re.DOTALL)
        md = _re.search(r"\[\[\s*DETALHE\s*\]\](.*?)\[\[\s*/\s*DETALHE\s*\]\]", texto, _re.IGNORECASE | _re.DOTALL)
        if mr:
            resumo = mr.group(1).strip()
        if md:
            detalhe = md.group(1).strip()
        # fallback: modelo não usou as tags → texto todo vira detalhe; 1º parágrafo vira resumo
        if not resumo and not detalhe:
            limpo = _re.sub(r"\[\[\s*/?\s*(RESUMO|DETALHE)\s*\]\]", "", texto, flags=_re.IGNORECASE).strip()
            detalhe = limpo
            resumo = (limpo.split("\n\n")[0] if limpo else limpo)[:500]
        elif not resumo:
            resumo = (detalhe.split("\n\n")[0] if detalhe else "")[:500]
        return {"ok": True, "resumo": resumo, "detalhe": detalhe, "analise": detalhe or resumo}
    except Exception as e:
        print(f"ANALISE OOS erro: {e}")
        return {"ok": False, "analise": ""}

# ════════════════════════════════════════════════════════════════════════════
#  PONTE "ENVIAR PRO MT5" — geração do .mq5 + validação na máquina do usuário
#  Fluxo: front aperta Enviar pro MT5 → /mt5/enviar gera o .mq5 (IA) e cria um
#  job "validando" → o conector do usuário pega em /mt5/pendente, instala e
#  COMPILA (metaeditor /compile, sem tocar no terminal de trading) → reporta em
#  /mt5/veredito → o modal do front acompanha por /mt5/status.
#  v6.65: jobs vivem na tabela mt5_jobs do SUPABASE (fonte única da verdade).
#  O dict _MT5_JOBS em memória morreu: com >1 worker o job criado num worker
#  era invisível pros outros, e restart apagava jobs em validação (F4 do
#  MAPA_PIPELINE). Agora criar/ler/atualizar é sempre no banco.
# ════════════════════════════════════════════════════════════════════════════
import time as _time_mt5
_MT5_POLLS = {}  # bot_token -> ts do último polling do conector (telemetria por worker; ok em memória)
_VISTO_DB = {}   # bot_token -> ts da última gravação de conector_visto_em (só throttle; a verdade está no Supabase)
_MT5_RAISE = {}  # bot_token -> ts do pedido "trazer o conector pra frente" (atalho mesmo-worker; verdade no Supabase)
_MT5_LIMPEZA = {"ts": 0.0}  # throttle da limpeza de jobs velhos (1x/5min por worker)


def _mt5_job_criar(job: dict) -> bool:
    """INSERT do job no Supabase. False se o banco estiver fora — o envio
    falha EXPLÍCITO (melhor que um job fantasma que só um worker enxerga)."""
    try:
        sb = _sb_admin()
        if sb is None:
            return False
        sb.table("mt5_jobs").insert(job).execute()
        return True
    except Exception as _e:
        try: print(f"[mt5-jobs] criar falhou: {_e}")
        except Exception: pass
        return False


def _mt5_job_buscar(job_id: str):
    if not (job_id or "").strip():
        return None
    try:
        sb = _sb_admin()
        if sb is None:
            return None
        r = sb.table("mt5_jobs").select("*").eq("job_id", job_id).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception as _e:
        try: print(f"[mt5-jobs] buscar falhou: {_e}")
        except Exception: pass
        return None


def _mt5_jobs_pendentes_tokens(toks: list) -> list:
    """Tokens (entre os informados) com job 'validando' — 1 SELECT em lote,
    qualquer worker vê o mesmo (era o pior sintoma do dict em memória)."""
    if not toks:
        return []
    try:
        sb = _sb_admin()
        if sb is None:
            return []
        r = (sb.table("mt5_jobs").select("bot_token")
             .in_("bot_token", toks).eq("status", "validando").execute())
        return sorted({x.get("bot_token") for x in (r.data or []) if x.get("bot_token")})
    except Exception as _e:
        try: print(f"[mt5-jobs] pendentes falhou: {_e}")
        except Exception: pass
        return []


def _mt5_job_pendente_do_token(bot_token: str):
    """Job 'validando' mais RECENTE deste bot (o conector valida um por vez)."""
    try:
        sb = _sb_admin()
        if sb is None:
            return None
        r = (sb.table("mt5_jobs").select("job_id,mq5,filename,pre_validado")
             .eq("bot_token", bot_token).eq("status", "validando")
             .order("criado_em", desc=True).limit(1).execute())
        return r.data[0] if r.data else None
    except Exception as _e:
        try: print(f"[mt5-jobs] pendente falhou: {_e}")
        except Exception: pass
        return None


def _mt5_slug(nome):
    import re as _re
    s = _re.sub(r"[^A-Za-z0-9_]+", "_", (nome or "").strip()).strip("_")
    return (s or "BotTested_EA")[:48]


def _mt5_limpar_velhos():
    """v6.65: apaga jobs com mais de 1h da tabela mt5_jobs (higiene). Throttle
    de 5min por worker — é manutenção, não precisa rodar a cada envio."""
    agora = _time_mt5.time()
    if agora - _MT5_LIMPEZA["ts"] < 300:
        return
    _MT5_LIMPEZA["ts"] = agora
    try:
        sb = _sb_admin()
        if sb is not None:
            corte = (_dt.now(_tz.utc) - _td(hours=1)).isoformat()
            sb.table("mt5_jobs").delete().lt("criado_em", corte).execute()
    except Exception as _e:
        try: print(f"[mt5-jobs] limpeza falhou: {_e}")
        except Exception: pass


def _mq5_system():
    return """Você converte uma estratégia de trading escrita em Python (biblioteca backtesting.py) em um Expert Advisor MQL5 COMPLETO e COMPILÁVEL para MetaTrader 5 (build recente).

Requisitos do EA:
- Comece com #property strict e #include <Trade/Trade.mqh>; use um objeto CTrade para abrir/fechar posições.
- Declare inputs (input) para os parâmetros (períodos de indicadores, stop, take).
- Implemente OnInit(), OnDeinit() e OnTick() com a MESMA lógica de entrada/saída do Python.
- Use as APIs corretas de MQL5: crie handles de indicadores no OnInit (iMA, iRSI, iBands, etc.) e leia com CopyBuffer no OnTick. NÃO use assinaturas antigas de MQL4.
- Opere uma posição por vez (cheque PositionSelect(_Symbol)).
- Stop e take em PONTOS: converta com _Point. MAS respeite a distância MÍNIMA — e ela NÃO é só o stops level (que em BTCUSD, índices e cripto costuma vir 0). Calcule usando também o SPREAD: double _sp = SymbolInfoDouble(_Symbol,SYMBOL_ASK) - SymbolInfoDouble(_Symbol,SYMBOL_BID); double _lvl = (SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL) + 10) * _Point; double dist_min = MathMax(_lvl, _sp * 3.0); — e NUNCA envie SL/TP mais perto do preço que dist_min. Se o SL/TP calculado ficar mais perto, empurre pra dist_min. Isso evita o 'invalid stops' (stop dentro do spread é rejeitado). Ajuste o lado correto (compra: SL abaixo, TP acima; venda: inverso) e NormalizeDouble(_Digits) antes de enviar.

Monitoramento BotTested (OBRIGATÓRIO — o conector lê estas linhas do log):
- Ao abrir: Print("BOTTESTED_EVENTO|aberto|"+(ehCompra?"BUY":"SELL")+"|"+_Symbol+"|preco="+DoubleToString(preco,_Digits));
- Ao fechar: Print("BOTTESTED_EVENTO|fechado|"+_Symbol+"|preco="+DoubleToString(preco,_Digits));
- SNAPSHOT: NÃO defina nenhuma função de snapshot. NÃO chame nada de snapshot. NÃO configure EventSetTimer para snapshot. A plataforma injeta AUTOMATICAMENTE no seu OnInit/OnTick/OnDeinit uma função BTVisaoTick() que emite o BOTTESTED_SNAPSHOT enriquecido (com zonas multi-TF, regime, canal EMA, lucro, tfop, preço) e grava no arquivo bt_snap_<magic>.txt. Você não precisa fazer NADA além de garantir que OnInit, OnTick e OnDeinit existam como funções normais.
- FIM DE VIDA (o desligar do monitoramento depende disso): no OnDeinit, DEPOIS do EventKillTimer, inclua EXATAMENTE este bloco (copie como está): if(reason==REASON_REMOVE || reason==REASON_CHARTCLOSE || reason==REASON_PROGRAM){ int bt_f = FileOpen("bt_snap_"+IntegerToString((long)InpMagic)+".txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ); if(bt_f!=INVALID_HANDLE){ FileWriteString(bt_f, "BOTTESTED_FIM|magic="+IntegerToString((long)InpMagic)+"\\n"); FileClose(bt_f); } }
  Isso avisa o BotTested Conector NA HORA que o bot saiu do gráfico (removido, gráfico fechado ou terminal fechando). IMPORTANTE: só nesses 3 reasons — troca de timeframe/símbolo (REASON_CHARTCHANGE) NÃO escreve o FIM, porque o OnInit roda de novo em seguida.


REGRAS:
- O código TEM que compilar no MetaEditor sem erros. Prefira o simples ao esperto.
- Responda APENAS com o código .mq5 puro. Sem crases, sem markdown, sem explicação, sem texto antes ou depois."""


# ── CACHE DE GERAÇÃO (v6.38) — a validação estava lenta porque a IA regerava
# o MESMO EA a cada envio (os bots da vitrine têm sempre o mesmo Python) e o
# MetaEditor recompilava o que já tinha sido aprovado. O cache guarda o .mq5
# NEUTRO (sem magic — o magic é re-injetado por bot) por hash do (código+sl+tp).
# O ativo NÃO entra no hash: o EA usa _Symbol em runtime, o código não muda.
# v6.65: SÓ SUPABASE. A camada de memória (_MQ5_GER_CACHE) foi REMOVIDA — ela
# era consultada ANTES do banco e sobreviveu ao DELETE FROM mq5_cache no dia
# 15/jul, servindo uma geração envenenada até o restart (o "fantasma"). Agora
# invalidar = DELETE no Supabase, ponto final. Vale pra todos os workers, sem
# restart. Custo: 1 SELECT por envio (~dezenas de ms) — irrelevante no fluxo.


def _mq5_hash_geracao(codigo_python, sl=None, tp=None) -> str:
    # v6.42: SL/TP FORA do hash (ideia do dono). Eles são `input` no .mq5 —
    # trocar o valor de um input não muda a compilação — então o cache guarda o
    # código NEUTRO e re-injeta o stop/take do usuário na hora (igual ao magic).
    # Consequência: usuário ajustou SL/TP (a sugestão mais comum do Radar) e o
    # envio CONTINUA relâmpago; só mudança de CÓDIGO exige validação completa.
    # (sl/tp ficam na assinatura por compatibilidade; são ignorados.)
    base = f"{(codigo_python or '')[:6000]}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _mq5_cache_buscar(gen_hash: str):
    """v6.65 — SUPABASE É A ÚNICA FONTE DA VERDADE. Sem camada de memória:
    DELETE FROM mq5_cache mata o cache de verdade, em qualquer worker."""
    if not (gen_hash or "").strip():
        return None
    try:
        sb = _sb_admin()
        if sb is not None:
            r = (sb.table("mq5_cache").select("mq5,aprovado")
                 .eq("gen_hash", gen_hash).limit(1).execute())
            if r.data and (r.data[0].get("mq5") or ""):
                return {"mq5": r.data[0]["mq5"],
                        "aprovado": bool(r.data[0].get("aprovado"))}
    except Exception as _e:
        try: print(f"[mq5-cache] busca supabase: {_e}")
        except Exception: pass
    return None


def _neutralizar_magic_mql5(codigo: str) -> str:
    """Remove a identidade do bot do .mq5 pra cachear: tira o magic literal da
    linha BOTTESTED_SNAPSHOT e zera o InpMagic pro placeholder. Na reutilização,
    _forcar_magic_mql5 re-injeta o magic do NOVO bot (o guard dele exige que a
    linha esteja sem magic — por isso a neutralização é obrigatória aqui)."""
    import re as _re
    if not codigo:
        return codigo
    codigo = _re.sub(r"BOTTESTED_SNAPSHOT\|magic=\d+\|", "BOTTESTED_SNAPSHOT|", codigo)
    codigo = _re.sub(r"(InpMagic\s*=\s*)\d+", r"\g<1>20250", codigo, count=1)
    # v6.42: SL/TP neutros no cache — re-injetados por bot no uso
    codigo = _re.sub(r"(InpSL\s*=\s*)[\d.]+", r"\g<1>60.0", codigo, count=1)
    codigo = _re.sub(r"(InpTP\s*=\s*)[\d.]+", r"\g<1>120.0", codigo, count=1)
    return codigo


def _forcar_sl_tp_mql5(codigo: str, sl, tp) -> str:
    """v6.42 — injeta o stop/take do USUÁRIO no .mq5 vindo do cache (que guarda
    os neutros 60/120). Só troca o valor default dos inputs — não altera lógica
    nem compilação, por isso o espelho de validação continua valendo."""
    import re as _re
    try:
        _sl, _tp = float(sl), float(tp)
    except Exception:
        return codigo
    codigo = _re.sub(r"(InpSL\s*=\s*)[\d.]+", lambda m: m.group(1) + f"{_sl:g}", codigo, count=1)
    codigo = _re.sub(r"(InpTP\s*=\s*)[\d.]+", lambda m: m.group(1) + f"{_tp:g}", codigo, count=1)
    return codigo


def _mq5_cache_guardar(gen_hash: str, mq5_neutro: str):
    """v6.65 — upsert direto no Supabase (única camada). aprovado volta a
    False DE PROPÓSITO: conteúdo novo ou regravado (ex.: defesa v6.58 que
    instrumenta cache legado) mudou o código → precisa de UMA validação real
    no MT5 antes de voltar a ser relâmpago. (A versão antiga não zerava o
    aprovado no banco ao regravar — memória dizia False, banco dizia True.)"""
    try:
        sb = _sb_admin()
        if sb is None:
            print("[mq5-cache] supabase indisponível — geração segue SEM cache")
            return
        sb.table("mq5_cache").upsert({
            "gen_hash": gen_hash, "mq5": mq5_neutro, "aprovado": False,
            "atualizado_em": _dt.now(_tz.utc).isoformat(),
        }, on_conflict="gen_hash").execute()
    except Exception as _e:
        try: print(f"[mq5-cache] upsert supabase: {_e}")
        except Exception: pass


def _mq5_cache_aprovar(gen_hash: str):
    """Veredito aprovado no MT5 real -> marca no Supabase (única camada). A
    partir daqui QUALQUER usuário que envie esse código ganha a validação
    relâmpago."""
    try:
        sb = _sb_admin()
        if sb is not None:
            sb.table("mq5_cache").update({
                "aprovado": True, "atualizado_em": _dt.now(_tz.utc).isoformat(),
            }).eq("gen_hash", gen_hash).execute()
    except Exception as _e:
        try: print(f"[mq5-cache] aprovar supabase: {_e}")
        except Exception: pass


def _gerar_mq5_de_codigo(codigo_python, params, idioma="pt"):
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave or not (codigo_python or "").strip():
        return ""
    try:
        import httpx, sys, re as _re
        ativo = params.get("ativo", "")
        sl = params.get("stop_loss", 60)
        tp = params.get("take_profit", 120)
        magic = int(params.get("magic", 0) or 0)
        # CACHE (v6.38): mesmo código+sl+tp = mesmo EA. Pula a IA (~15-40s) e
        # re-injeta só o magic deste bot. É o caso comum da vitrine.
        gen_hash = _mq5_hash_geracao(codigo_python, sl, tp)
        hit = _mq5_cache_buscar(gen_hash)
        if hit and hit.get("mq5"):
            texto = hit["mq5"]
            # v6.58: DEFESA contra cache legado — entrada sem a VISÃO (BTVisaoTick)
            # é instrumentada agora e regravada. Entradas novas já nascem prontas.
            if "BTVisaoTick" not in texto:
                texto = _instrumentar_log_mql5(texto)
                _mq5_cache_guardar(gen_hash, _neutralizar_magic_mql5(texto))
            if magic:
                texto = _forcar_magic_mql5(texto, magic)
            texto = _forcar_sl_tp_mql5(texto, sl, tp)   # v6.42: SL/TP do usuário
            print(f"[mq5-cache] HIT {gen_hash[:10]} (aprovado={hit.get('aprovado')}) — IA pulada")
            return texto
        instr_magic = (f"Declare EXATAMENTE: input long InpMagic = {magic}; e no OnInit chame "
                       f"trade.SetExpertMagicNumber(InpMagic); — este magic identifica ESTE bot, "
                       f"não invente outro.\n") if magic else ""
        prompt = (f"Converta esta estratégia (Python, backtesting.py) em um Expert Advisor MQL5 "
                  f"completo e compilável.\nAtivo alvo: {ativo}. Stop loss (pontos): {sl}. "
                  f"Take profit (pontos): {tp}.\n{instr_magic}\nCódigo Python:\n{codigo_python[:6000]}")
        modelo = os.environ.get("MQL5_IA_MODELO", os.environ.get("EDITOR_IA_MODELO", "claude-sonnet-4-6"))
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": modelo, "max_tokens": 4000, "temperature": 0.2,
                  "system": _mq5_system(), "messages": [{"role": "user", "content": prompt}]},
            timeout=90.0,
        )
        if r.status_code != 200:
            print(f"GERAR MQL5 status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return ""
        texto = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        texto = _re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", texto)
        texto = _re.sub(r"\n?```\s*$", "", texto).strip()
        # v6.58 — INSTRUMENTAR AQUI (causa-raiz do snapshot mudo no /mt5/enviar):
        # este caminho NUNCA chamava _instrumentar_log_mql5 — o comentário antigo
        # ("a injeção quebrava a compilação") era da era v6.35. A injeção atual é
        # DEFENSIVA (SELO+VISÃO só se achar OnInit; clamp só se achar o include;
        # busca de chave robusta) e foi validada na v6.56 contra EA real da IA.
        # Sem isto, v6.55/v6.56 não tinham efeito algum neste fluxo: o prompt
        # parou de pedir snapshot E a VISÃO nunca era injetada → EA sem snapshot
        # nenhum (BOTTESTED_03 provou: EventKillTimer órfão = faxina nunca rodou).
        # O cache guarda a versão NEUTRA já INSTRUMENTADA — HIT herda a visão.
        if texto:
            texto = _instrumentar_log_mql5(texto)
            _mq5_cache_guardar(gen_hash, _neutralizar_magic_mql5(texto))
        if magic:
            texto = _forcar_magic_mql5(texto, magic)
        return texto
    except Exception as e:
        print(f"GERAR MQL5 erro: {e}")
        return ""


class MT5EnviarReq(BaseModel):
    user_id: str = ""
    bot_nome: str = ""
    bot_token: str = ""
    codigo: str = ""
    ativo: str = ""
    stop_loss: float = 60
    take_profit: float = 120
    ema_period: int = 20
    timeframe: str = "1d"
    idioma: str = "pt"


# ════════════════════════════════════════════════════════════════════════════
#  v6.83 — SENTINELA DE SANIDADE + AUTO-CURA + CÓDIGOS DE REPROVAÇÃO (BT-xx)
#
#  Caso BOTTESTED_15: entrada envenenada no mq5_cache (string com \n colapsado
#  em quebra REAL -> error 112) reprovava 4x idêntico. A sentinela detecta a
#  classe inteira ANTES do envio; a auto-cura apaga a entrada podre e regenera
#  sozinha — usuário nunca roda SQL. O classificador traduz o compile.log que
#  o conector já manda em CÓDIGOS identificáveis na hora.
# ════════════════════════════════════════════════════════════════════════════

def _mq5_sanidade(texto):
    """v6.84 — SENTINELA v2 (fix do falso positivo BT-G01): entende comentário
    de BLOCO /* ... */ atravessando linhas — aspas dentro de comentário não
    contam. Mantém a v1: string MQL5 não atravessa linha; respeita \\" escapado,
    // comentário de linha e char literal tipo \'"\'.
    Retorna (ok, num_linha, trecho). Nunca bloqueia por bug próprio."""
    try:
        em_bloco = False
        for num, linha in enumerate(str(texto or "").split("\n"), 1):
            dentro = False
            i, n = 0, len(linha)
            while i < n:
                if em_bloco:
                    f = linha.find("*/", i)
                    if f < 0:
                        i = n
                        break
                    em_bloco = False
                    i = f + 2
                    continue
                ch = linha[i]
                if dentro:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == '"':
                        dentro = False
                elif ch == "/" and i + 1 < n and linha[i + 1] == "/":
                    break   # comentário de linha: aspas soltas não contam
                elif ch == "/" and i + 1 < n and linha[i + 1] == "*":
                    em_bloco = True
                    i += 2
                    continue
                elif ch == '"':
                    dentro = True
                elif ch == "'":
                    # char literal ('|', '"', '\\x'): pula até o fechamento na linha
                    passo = 2 if (i + 1 < n and linha[i + 1] == "\\") else 1
                    j = linha.find("'", i + passo)
                    if j > i:
                        i = j
                i += 1
            if dentro:
                return (False, num, linha.strip()[:160])
        return (True, 0, "")
    except Exception:
        return (True, 0, "")


def _mq5_cache_apagar(gen_hash: str) -> bool:
    """v6.83 — remove UMA entrada do cache (auto-cura da sentinela)."""
    try:
        sb = _sb_admin()
        if sb is None or not gen_hash:
            return False
        sb.table("mq5_cache").delete().eq("gen_hash", gen_hash).execute()
        print(f"[mq5-cache] entrada {gen_hash[:10]} APAGADA (auto-cura da sentinela)")
        return True
    except Exception as _e:
        try: print(f"[mq5-cache] apagar {gen_hash[:10]} falhou: {_e}")
        except Exception: pass
        return False


_BT_CODIGOS_COMPILE = (
    ("BT-C01", ("error 112", "closing quote")),
    ("BT-C02", ("'ask'", "'bid'", "wrong parameters count")),
    ("BT-C04", ("already defined",)),
    ("BT-C05", ("cannot convert",)),
    ("BT-C03", ("unbalanced", "unexpected end of program", "'}' -", "'{' -")),
)


def _classificar_reprovacao(log: str):
    """v6.83 — traduz o compile.log num CÓDIGO BT-xx + resumo das primeiras
    linhas de erro. O PRIMEIRO erro decide (o resto costuma ser cascata)."""
    txt = str(log or "")
    baixo = txt.lower()
    linhas_erro = [l.strip() for l in txt.split("\n") if ": error " in l.lower()][:3]
    resumo = "\n".join(l[:200] for l in linhas_erro)
    if not txt.strip():
        return {"codigo": "BT-X01", "resumo_log": ""}
    alvo = (linhas_erro[0].lower() if linhas_erro else baixo)
    for cod, marcas in _BT_CODIGOS_COMPILE:
        if any(m in alvo for m in marcas):
            return {"codigo": cod, "resumo_log": resumo}
    for cod, marcas in _BT_CODIGOS_COMPILE:
        if any(m in baixo for m in marcas):
            return {"codigo": cod, "resumo_log": resumo}
    if linhas_erro:
        return {"codigo": "BT-C99", "resumo_log": resumo}
    return {"codigo": "BT-X01", "resumo_log": txt.strip()[:200]}


@app.post("/mt5/enviar")
def mt5_enviar(req: MT5EnviarReq):
    _mt5_limpar_velhos()
    if not req.bot_token:
        return {"ok": False, "erro": "sem_token", "codigo": "BT-T01"}
    if not (req.codigo or "").strip():
        return {"ok": False, "erro": "sem_codigo", "codigo": "BT-T02"}
    # magic único por bot (do token) e nome do arquivo = nome do bot
    magic = _magic_do_token(req.bot_token, f"{req.ativo}|{req.bot_nome}")
    _params_ger = {"ativo": req.ativo, "stop_loss": req.stop_loss,
                   "take_profit": req.take_profit, "magic": magic}
    _gh = _mq5_hash_geracao(req.codigo, req.stop_loss, req.take_profit)
    mq5 = _gerar_mq5_de_codigo(req.codigo, _params_ger, req.idioma)
    if not mq5:
        return {"ok": False, "erro": "falha_gerar_mq5", "codigo": "BT-G02"}
    # v6.83 — SENTINELA + AUTO-CURA: se o .mq5 (fresco ou vindo do cache) tem
    # string quebrada (classe do \n colapsado — os 4x idênticos do
    # BOTTESTED_15), APAGA a entrada envenenada e regenera UMA vez. O usuário
    # nunca precisa rodar SQL: o próprio envio se cura.
    _ok_s, _ln_s, _tr_s = _mq5_sanidade(mq5)
    if not _ok_s:
        try:
            print(f"[mq5-sanidade] malformado (linha {_ln_s}: {_tr_s[:80]!r}) — "
                  f"auto-cura: apagando cache {_gh[:10]} e regenerando")
        except Exception:
            pass
        _mq5_cache_apagar(_gh)
        mq5 = _gerar_mq5_de_codigo(req.codigo, _params_ger, req.idioma)
        _ok_s, _ln_s, _tr_s = _mq5_sanidade(mq5 or "")
        if not mq5 or not _ok_s:
            return {"ok": False, "erro": "codigo_malformado", "codigo": "BT-G01",
                    "resumo_log": (f"linha {_ln_s}: {_tr_s}" if _tr_s else "")}
    import uuid
    job_id = uuid.uuid4().hex[:16]
    filename = _nome_arquivo_bot(req.bot_nome, fallback=_mt5_slug(req.bot_nome)) + ".mq5"
    # PRÉ-VALIDADO (v6.38): recalculado APÓS a sentinela — se a auto-cura
    # apagou a entrada, o pré-validado cai junto e o conector compila de verdade.
    _pre_ok = bool((_mq5_cache_buscar(_gh) or {}).get("aprovado"))
    ok_job = _mt5_job_criar({
        "job_id": job_id,
        "bot_token": req.bot_token,
        "filename": filename,
        "magic": magic,
        "mq5": mq5,
        "status": "validando",
        "aprovado": None,
        "log": "",
        "gen_hash": _gh,
        "pre_validado": _pre_ok,
    })
    if not ok_job:
        # sem banco não existe job que o conector consiga ver — falha explícita
        return {"ok": False, "erro": "supabase_indisponivel", "codigo": "BT-S01"}
    # guarda o .mq5 na nuvem pra o card "Meus bots" poder REINSTALAR sem regenerar.
    # try/except isolado: se a coluna ainda não existir no Supabase, não quebra o envio.
    try:
        sb = _sb_admin()
        if sb is not None and req.bot_token:
            sb.table("conector_bots").update({
                "mq5_codigo": mq5, "mq5_filename": filename, "magic_number": magic,
            }).eq("bot_token", req.bot_token).execute()
    except Exception as _e:
        try: print(f"[mt5_enviar] aviso: não persistiu mq5 ({_e})")
        except Exception: pass
    return {"ok": True, "job_id": job_id}


class Mt5Presenca(BaseModel):
    tokens: list


@app.post("/mt5/presenca")
def mt5_presenca(req: Mt5Presenca):
    """v6.52 — PRESENÇA EM LOTE: o conector bate o coração de TODOS os tokens
    numa requisição só (era 1 GET /mt5/pendente por token em SÉRIE — com 19
    bots a varredura passava de 25s e o bot novo nascia "invisível" pro front).
    Toca conector_visto_em de todos (1 update com .in_) e devolve só os tokens
    que TÊM trabalho pendente — o GET individual passa a rodar apenas quando há
    o que validar. Custo de rede constante, qualquer que seja o nº de bots."""
    toks = [str(t) for t in (req.tokens or []) if t][:200]
    if not toks:
        return {"ok": True, "pendentes": []}
    agora_ts = _time_mt5.time()
    for t in toks:
        _MT5_POLLS[t] = agora_ts
    precisa_db = [t for t in toks if agora_ts - _VISTO_DB.get(t, 0) > _PRESENCA_THROTTLE_HB]
    if precisa_db:
        for t in precisa_db:
            _VISTO_DB[t] = agora_ts
        try:
            _sbp = _sb_admin()
            if _sbp is not None:
                _sbp.table("conector_bots").update(
                    {"conector_visto_em": _dt.now(_tz.utc).isoformat()}
                ).in_("bot_token", precisa_db).execute()
        except Exception:
            pass
    pend = _mt5_jobs_pendentes_tokens(toks)   # v6.65: Supabase — todo worker vê
    return {"ok": True, "pendentes": pend}


@app.get("/mt5/pendente")
def mt5_pendente(bot_token: str = ""):
    if not bot_token:
        return {"pendente": False}
    agora_ts = _time_mt5.time()
    _MT5_POLLS[bot_token] = agora_ts   # conector deu sinal de vida (em memória)
    # HEARTBEAT PERSISTENTE (trilha etapa CONECTAR): o conector consulta esta rota
    # a cada ~5s por token; gravamos conector_visto_em no bot (throttle ~30s) pra a
    # trilha saber que o conector pareou com este bot — SEM depender do bot estar
    # num gráfico (isso é a etapa OPERAR). Multi-worker-safe (vai pro Supabase).
    if agora_ts - _VISTO_DB.get(bot_token, 0) > _PRESENCA_THROTTLE_HB:
        _VISTO_DB[bot_token] = agora_ts
        try:
            _sbp = _sb_admin()
            if _sbp is not None:
                _sbp.table("conector_bots").update(
                    {"conector_visto_em": _dt.now(_tz.utc).isoformat()}
                ).eq("bot_token", bot_token).execute()
        except Exception:
            pass
    j = _mt5_job_pendente_do_token(bot_token)   # v6.65: Supabase — todo worker vê
    if not j:
        return {"pendente": False}
    return {"pendente": True, "job_id": j.get("job_id"),
            "codigo": j.get("mq5") or "", "filename": j.get("filename") or "",
            "pre_validado": bool(j.get("pre_validado"))}


class PresencaParar(BaseModel):
    tokens: Optional[List[str]] = None
    bot_token: Optional[str] = None   # compat: um só


@app.post("/presenca/parar")
def presenca_parar(req: PresencaParar):
    """PRESENÇA — corte IMEDIATO: o coletor (conector/Tryd) avisa que PAROU. Marca
    conector_parado_em = agora nos bots; como o Parar passa a ser o sinal mais
    recente, a presença vira PARADO na hora e a trilha REBAIXA no próximo polling
    (sem esperar timeout). Aceita lista de tokens (o conector monitora vários)."""
    sb = _sb_admin()
    if sb is None:
        return {"ok": False, "erro": "supabase indisponivel"}
    toks = [t for t in (req.tokens or []) if t]
    if not toks and req.bot_token:
        toks = [req.bot_token]
    agora_iso = _dt.now(_tz.utc).isoformat()
    n = 0
    for t in toks:
        try:
            sb.table("conector_bots").update(
                {"conector_parado_em": agora_iso}).eq("bot_token", t).execute()
            _VISTO_DB.pop(t, None)     # zera o throttle do heartbeat
            _MT5_POLLS.pop(t, None)    # limpa heartbeat em memória
            n += 1
        except Exception as _e:
            _presenca_log(f"parar falhou p/ {str(t)[:8]}…: {_e}")
    _presenca_log(f"PARAR sinalizado — {n}/{len(toks)} bot(s) marcados como parados")
    return {"ok": True, "parados": n}


@app.get("/mt5/conector-status")
def mt5_conector_status(bot_token: str = ""):
    """O conector está online? (fez polling nos últimos 15s)"""
    ts = _MT5_POLLS.get(bot_token, 0)
    delta = _time_mt5.time() - ts if ts else None
    return {"online": bool(ts and delta is not None and delta < 15),
            "visto_ha_seg": (round(delta, 1) if delta is not None else None)}


class MT5SubirReq(BaseModel):
    bot_token: str = ""


@app.post("/mt5/subir-conector")
def mt5_subir_conector(req: MT5SubirReq):
    """A plataforma pede pra trazer o conector pra frente (usuário apertou
    'Entendi' na guia, ou o ✅ chegou com a guia suprimida). Grava o sinal no
    Supabase (assim QUALQUER worker do Railway enxerga) e também na memória
    local como atalho rápido. Quem age é o conector, que consulta isso."""
    if req.bot_token:
        _MT5_RAISE[req.bot_token] = _time_mt5.time()   # atalho (mesmo worker)
        try:
            sb = _sb_admin()
            if sb is not None:
                sb.table("conector_bots").update(
                    {"subir_pedido_em": _dt.now(_tz.utc).isoformat()}
                ).eq("bot_token", req.bot_token).execute()
        except Exception as _e:
            try: print(f"[subir-conector] aviso ao gravar: {_e}")
            except Exception: pass
    return {"ok": True}


@app.get("/mt5/subir-conector")
def mt5_subir_conector_check(bot_token: str = ""):
    """O conector consulta aqui (rápido). One-shot: lê e LIMPA o sinal, então
    ele só sobe uma vez por pedido. Válido por 180s pra pedido velho não subir
    o conector fora de hora. Checa memória (rápido) e Supabase (confiável)."""
    if not bot_token:
        return {"subir": False}
    # 1) atalho em memória (se caiu no mesmo worker que gravou)
    ts = _MT5_RAISE.pop(bot_token, 0)
    if ts and (_time_mt5.time() - ts) < 180:
        try:
            sb = _sb_admin()
            if sb is not None:
                sb.table("conector_bots").update({"subir_pedido_em": None}).eq("bot_token", bot_token).execute()
        except Exception: pass
        return {"subir": True}
    # 2) Supabase (qualquer worker vê o mesmo sinal)
    try:
        sb = _sb_admin()
        if sb is not None:
            r = (sb.table("conector_bots").select("subir_pedido_em")
                 .eq("bot_token", bot_token).limit(1).execute())
            val = r.data[0].get("subir_pedido_em") if r.data else None
            if val:
                try:
                    pedido = _dt.fromisoformat(str(val).replace("Z", "+00:00"))
                    recente = (_dt.now(_tz.utc) - pedido).total_seconds() < 180
                except Exception:
                    recente = True
                if recente:
                    sb.table("conector_bots").update({"subir_pedido_em": None}).eq("bot_token", bot_token).execute()
                    return {"subir": True}
    except Exception:
        pass
    return {"subir": False}


class MT5VeredictoReq(BaseModel):
    bot_token: str = ""
    job_id: str = ""
    aprovado: bool = False
    log: str = ""


@app.post("/mt5/veredito")
def mt5_veredito(req: MT5VeredictoReq):
    j = _mt5_job_buscar(req.job_id)   # v6.65: Supabase — o veredito pode cair
    if not j:                          # em OUTRO worker que não criou o job
        return {"ok": False, "erro": "job_inexistente"}
    try:
        sb = _sb_admin()
        if sb is None:
            return {"ok": False, "erro": "supabase_indisponivel"}
        sb.table("mt5_jobs").update({
            "status": "aprovado" if req.aprovado else "reprovado",
            "aprovado": bool(req.aprovado),
            "log": (req.log or "")[:4000],
            "atualizado_em": _dt.now(_tz.utc).isoformat(),
        }).eq("job_id", req.job_id).execute()
    except Exception as _e:
        try: print(f"[mt5-jobs] veredito update falhou: {_e}")
        except Exception: pass
        return {"ok": False, "erro": "update_falhou"}
    # v6.38: aprovou no MT5 real -> marca o cache; próximos envios do MESMO
    # código pulam a IA E o compile (pré-validado, veredito na hora).
    try:
        if req.aprovado and j.get("gen_hash"):
            _mq5_cache_aprovar(j["gen_hash"])
    except Exception:
        pass
    return {"ok": True}


@app.get("/mt5/status")
def mt5_status(job_id: str = ""):
    j = _mt5_job_buscar(job_id)   # v6.65: Supabase — o modal do front pode
    if not j:                      # cair em qualquer worker
        return {"status": "desconhecido"}
    out = {"status": j.get("status"), "aprovado": j.get("aprovado"),
           "log": j.get("log") or ""}
    # v6.83 — CÓDIGO DO MOTIVO: reprovação sai com BT-xx + resumo do erro
    if j.get("status") == "reprovado":
        out.update(_classificar_reprovacao(j.get("log") or ""))
    return out


# ── AQUECIMENTO DE FÁBRICA (v6.39) ─────────────────────────────────────────
# Gera o .mq5 de TODAS as estratégias prontas UMA vez (sl/tp padrão 60/120) e
# guarda no cache persistente. Depois do aquecimento + 1 rodada de aprovação
# no MT5 (o admin envia cada uma 1x), NENHUM usuário paga a IA nem o compile:
# a vitrine inteira valida em ~5-10s pra sempre. Admin-only, roda em background
# (14 estratégias x ~20-40s de IA = alguns minutos; o status mostra o progresso).
_MQ5_AQUECER = {"rodando": False, "feitas": 0, "total": 0, "erros": [], "inicio": 0.0}


def _mq5_aquecer_worker():
    try:
        alvos = [e for e in ESTRATEGIAS_PRONTAS if (e.get("codigo") or "").strip()]
        _MQ5_AQUECER.update(rodando=True, feitas=0, total=len(alvos),
                            erros=[], inicio=_time_mt5.time())
        for est in alvos:
            cod = est["codigo"]
            h = _mq5_hash_geracao(cod, 60, 120)
            if _mq5_cache_buscar(h):
                _MQ5_AQUECER["feitas"] += 1
                print(f"[mq5-aquecer] {est.get('id')} já no cache ({h[:10]})")
                continue
            mq5 = _gerar_mq5_de_codigo(cod, {"ativo": "", "stop_loss": 60,
                                             "take_profit": 120, "magic": 0})
            if not mq5:
                _MQ5_AQUECER["erros"].append(est.get("id") or "?")
                print(f"[mq5-aquecer] FALHOU {est.get('id')}")
            else:
                print(f"[mq5-aquecer] gerado {est.get('id')} ({h[:10]})")
            _MQ5_AQUECER["feitas"] += 1
    except Exception as _e:
        try: _MQ5_AQUECER["erros"].append(f"worker: {_e}")
        except Exception: pass
    finally:
        _MQ5_AQUECER["rodando"] = False


@app.delete("/admin/mq5/invalidar")
def admin_mq5_invalidar(estrategia_id: str = "", token: str = ""):
    """v6.54 — INVALIDAR CACHE DE UMA ESTRATÉGIA. Remove o .mq5 cacheado
    (memória + Supabase) da estratégia indicada; o próximo envio dela regenera
    do zero com o PROMPT ATUAL, herdando os campos ricos do snapshot (zonas,
    regime, offmind, lucro, tfop). Admin-only. Uso pro loop de fechamento:
    identificamos que os EAs atuais no MT5 emitem snapshot esqueleto — cache
    foi feito antes da v6.36. Invalidar + reenviar 1 bot = teste do loop.

    curl -X DELETE 'https://.../admin/mq5/invalidar?estrategia_id=tripla_media_9_21_50&token=SEU_TOKEN'
    """
    tok_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not tok_certo or token != tok_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    eid = (estrategia_id or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="estrategia_id obrigatório")
    est = next((e for e in ESTRATEGIAS_PRONTAS if e.get("id") == eid), None)
    if est is None:
        raise HTTPException(status_code=404, detail=f"estratégia '{eid}' não existe")
    codigo = (est.get("codigo") or "").strip()
    if not codigo:
        raise HTTPException(status_code=400, detail="estratégia sem código")
    gen_hash = _mq5_hash_geracao(codigo)
    # v6.65: só existe UMA camada (Supabase). DELETE aqui = cache morto de
    # verdade, em todos os workers, sem restart — fim do ritual DELETE+RESTART.
    removidos = {"supabase": False}
    try:
        sb = _sb_admin()
        if sb is not None:
            r = sb.table("mq5_cache").delete().eq("gen_hash", gen_hash).execute()
            removidos["supabase"] = bool(r.data)
    except Exception as e:
        return {"ok": True, "estrategia_id": eid, "hash": gen_hash[:10],
                "removidos": removidos, "aviso": f"supabase: {e}"}
    return {"ok": True, "estrategia_id": eid, "hash": gen_hash[:10],
            "removidos": removidos,
            "proximo_passo": "reenvie um bot com esta estratégia — a IA regenera com o prompt novo"}


@app.post("/admin/mq5/aquecer")
def admin_mq5_aquecer(token: str = ""):
    """Dispara o aquecimento em background. Chame 1x após o deploy; acompanhe
    em GET /admin/mq5/cache. Idempotente: estratégia já cacheada é pulada."""
    tok_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not tok_certo or token != tok_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    if _MQ5_AQUECER["rodando"]:
        return {"ok": False, "erro": "ja_rodando", **{k: _MQ5_AQUECER[k] for k in ("feitas", "total")}}
    import threading as _th
    _th.Thread(target=_mq5_aquecer_worker, daemon=True).start()
    return {"ok": True, "msg": "aquecimento iniciado em background",
            "estrategias": len([e for e in ESTRATEGIAS_PRONTAS if (e.get("codigo") or "").strip()])}


@app.get("/admin/mq5/cache")
def admin_mq5_cache(token: str = ""):
    """Estado do cache de geração: progresso do aquecimento + contagem no
    Supabase (única camada desde a v6.65). Admin-only."""
    tok_certo = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not tok_certo or token != tok_certo:
        raise HTTPException(status_code=403, detail="Token inválido")
    db = {"total": None, "aprovados": None}
    try:
        sb = _sb_admin()
        if sb is not None:
            r = sb.table("mq5_cache").select("gen_hash,aprovado").execute()
            rows = r.data or []
            db = {"total": len(rows),
                  "aprovados": sum(1 for x in rows if x.get("aprovado"))}
    except Exception as _e:
        db = {"erro": str(_e)[:120]}
    # mapa estratégia -> hash/estado (pra conferir a vitrine de relance)
    vitrine = []
    for est in ESTRATEGIAS_PRONTAS:
        cod = (est.get("codigo") or "").strip()
        if not cod:
            continue
        h = _mq5_hash_geracao(cod, 60, 120)
        e = _mq5_cache_buscar(h)
        vitrine.append({"id": est.get("id"), "hash": h[:10],
                        "cacheado": bool(e), "aprovado": bool(e and e.get("aprovado"))})
    return {"aquecimento": dict(_MQ5_AQUECER),
            "memoria": "removida na v6.65 — Supabase é a única camada",
            "supabase": db, "vitrine": vitrine}


# ══════════════════════════════════════════════════════════════════════════
# ║  PAINEL DE INTELIGÊNCIA DO USUÁRIO — lê o radar_chat_log e mostra os     ║
# ║  padrões: o que os usuários perguntam pra IA, onde travam, que ativo/    ║
# ║  estratégia gera mais dúvida. Transforma o histórico já coletado numa    ║
# ║  bússola de produto. Admin-only (BIBLIOTECA_ADMIN_TOKEN).                ║
# ══════════════════════════════════════════════════════════════════════════

def _re_html(s):
    """Escapa HTML minimo pra exibir perguntas do usuario com seguranca."""
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

# stopwords PT/EN/ES — palavras genéricas que não são sinal (termos de trading
# tipo "stop", "ativo", "backtest" NÃO entram aqui de propósito: são sinal).
_RADAR_STOPWORDS = set("""
a o e de da do das dos em no na nos nas um uma uns umas que se com por para pra
como mais mas ou ao aos à às os as é ser tem ter foi era são está estão estou
eu voce você me te lhe nos vos meu minha seu sua isso isto esse essa este esta
aquele aquela quando onde porque por que qual quais quero posso pode fazer faz
não sim ja já só muito bem aqui ali la lá tudo nada algo cada entre sobre até
the of and to in a is it for on with as at by an be this that i you my your we
they he she them from or if not what how when where why can do does are was were
el la los las de en un una y que se con por para como mas o su sus es ser esta
estan estoy yo tu me te le nos os mi mis muy bien aqui alli todo nada
""".split())

def _radar_insights(sb, limite: int = 5000) -> dict:
    from collections import Counter
    import re as _re2
    rows = (sb.table("radar_chat_log")
            .select("plano,idioma,ativo,estrategia_id,pergunta,created_at")
            .order("created_at", desc=True).limit(limite).execute().data or [])
    total = len(rows)
    por_plano = Counter((r.get("plano") or "?") for r in rows)
    por_idioma = Counter((r.get("idioma") or "?") for r in rows)
    por_ativo = Counter(r.get("ativo") for r in rows if r.get("ativo"))
    por_estrat = Counter(r.get("estrategia_id") for r in rows if r.get("estrategia_id"))
    # frequência de palavras nas perguntas (tema/dúvida recorrente)
    palavras = Counter()
    for r in rows:
        for w in _re2.findall(r"[a-zA-Zà-úÀ-Ú0-9]{3,}", (r.get("pergunta") or "").lower()):
            if w not in _RADAR_STOPWORDS:
                palavras[w] += 1
    # volume por dia (últimos 14)
    por_dia = Counter()
    for r in rows:
        d = str(r.get("created_at") or "")[:10]
        if d:
            por_dia[d] += 1
    dias = sorted(por_dia.items())[-14:]
    # perguntas recentes cruas (ler a dor do usuário)
    recentes = [{"pergunta": (r.get("pergunta") or "").strip()[:220],
                 "ativo": r.get("ativo"), "plano": r.get("plano"),
                 "quando": str(r.get("created_at") or "")[:16]}
                for r in rows[:40] if (r.get("pergunta") or "").strip()]
    return {
        "total": total,
        "por_plano": por_plano.most_common(),
        "por_idioma": por_idioma.most_common(),
        "top_ativos": por_ativo.most_common(10),
        "top_estrategias": por_estrat.most_common(10),
        "top_palavras": palavras.most_common(25),
        "volume_dia": dias,
        "recentes": recentes,
    }


@app.get("/admin/radar/link")
def admin_radar_link(user_id: str = ""):
    """Entrega o link do painel do Radar já autenticado — só pro admin.
    O front chama isto com o user_id logado; se for o admin, devolve a URL
    do painel com o token embutido. Assim o token NUNCA fica escrito no
    app.html (código-fonte público). Quem não for o admin recebe 403."""
    if not user_id or user_id != _BIB_ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="Acesso restrito")
    tok = os.getenv("BIBLIOTECA_ADMIN_TOKEN", "")
    if not tok:
        raise HTTPException(status_code=500, detail="Token admin não configurado")
    return {"url": f"/admin/radar/painel?token={tok}"}


@app.get("/admin/radar/insights")
def admin_radar_insights(token: str = "", limite: int = 5000):
    """Agregações do radar_chat_log em JSON. Admin-only."""
    if not os.getenv("BIBLIOTECA_ADMIN_TOKEN", "") or token != os.getenv("BIBLIOTECA_ADMIN_TOKEN", ""):
        raise HTTPException(status_code=403, detail="Token inválido")
    sb = _sb_admin()
    if sb is None:
        raise HTTPException(status_code=500, detail="Supabase indisponível")
    return _radar_insights(sb, max(100, min(int(limite or 5000), 20000)))


@app.get("/admin/radar/painel", response_class=HTMLResponse)
def admin_radar_painel(token: str = ""):
    """Dashboard HTML: o que os usuários perguntam pra IA. Admin-only."""
    if not os.getenv("BIBLIOTECA_ADMIN_TOKEN", "") or token != os.getenv("BIBLIOTECA_ADMIN_TOKEN", ""):
        return HTMLResponse("<h3 style='font-family:sans-serif;color:#c33'>Token inválido</h3>", status_code=403)
    sb = _sb_admin()
    if sb is None:
        return HTMLResponse("<h3>Supabase indisponível</h3>", status_code=500)
    d = _radar_insights(sb)
    if not d["total"]:
        return HTMLResponse("<body style='background:#0a0f14;color:#e8ecf1;font-family:sans-serif;padding:40px'>"
                            "<h2>Painel do Radar</h2><p>Ainda não há conversas registradas.</p></body>")

    def barras(itens, cor="#00d084", maxn=10):
        itens = itens[:maxn]
        top = max((v for _, v in itens), default=1) or 1
        linhas = ""
        for nome, v in itens:
            pct = int(100 * v / top)
            linhas += (f"<div class='row'><div class='lbl'>{nome}</div>"
                       f"<div class='bar'><div class='fill' style='width:{pct}%;background:{cor}'></div></div>"
                       f"<div class='val'>{v}</div></div>")
        return linhas or "<p class='muted'>sem dados</p>"

    palavras_html = "".join(
        f"<span class='chip' style='font-size:{min(26, 12 + v)}px'>{w} <b>{v}</b></span>"
        for w, v in d["top_palavras"])

    vol_html = barras([(dia[5:], n) for dia, n in d["volume_dia"]], "#4aa3ff", 14)

    recentes_html = "".join(
        f"<tr><td class='q'>{_re_html(r['pergunta'])}</td><td>{r.get('ativo') or '—'}</td>"
        f"<td>{r.get('plano') or '—'}</td><td class='muted'>{r['quando']}</td></tr>"
        for r in d["recentes"])

    plano_html = " · ".join(f"<b>{p}</b>: {n}" for p, n in d["por_plano"])
    idioma_html = " · ".join(f"<b>{i}</b>: {n}" for i, n in d["por_idioma"])

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Painel do Radar — BotTested</title><meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
body{{background:#0a0f14;color:#e8ecf1;font-family:system-ui,-apple-system,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;line-height:1.5}}
h1{{color:#00d084;font-size:24px;margin-bottom:2px}} .sub{{color:#8a96a6;font-size:13px;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} @media(max-width:720px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:#0d1520;border:1px solid #1e2a3a;border-radius:12px;padding:16px 18px;margin-bottom:16px}}
.card h3{{margin:0 0 12px;font-size:14px;color:#c9d3df;font-weight:600}}
.big{{font-size:34px;font-weight:800;color:#00d084}}
.row{{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:13px}}
.lbl{{width:150px;color:#c9d3df;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar{{flex:1;background:#152233;border-radius:6px;height:14px;overflow:hidden}}
.fill{{height:100%;border-radius:6px}} .val{{width:40px;text-align:right;color:#8a96a6}}
.chip{{display:inline-block;margin:3px 6px 3px 0;color:#c9d3df}} .chip b{{color:#00d084}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td{{border-bottom:1px solid #16202c;padding:7px 8px;vertical-align:top}}
.q{{color:#e8ecf1}} .muted{{color:#5f6e7d}}
th{{text-align:left;color:#8a96a6;font-size:12px;padding:6px 8px;border-bottom:1px solid #1e2a3a}}
</style></head><body>
<h1>🧠 Painel do Radar</h1>
<div class='sub'>O que os usuários estão perguntando pra IA — {d['total']} conversas · {plano_html} · idiomas: {idioma_html}</div>

<div class='card'><h3>Volume de conversas por dia (últimos 14)</h3>{vol_html}</div>

<div class='grid'>
<div class='card'><h3>🎯 Ativos que mais geram dúvida</h3>{barras(d['top_ativos'], '#00d084')}</div>
<div class='card'><h3>🧩 Estratégias que mais geram dúvida</h3>{barras(d['top_estrategias'], '#ffb830')}</div>
</div>

<div class='card'><h3>💬 Temas recorrentes (palavras nas perguntas)</h3><div>{palavras_html}</div></div>

<div class='card'><h3>🕐 Perguntas recentes (a dor do usuário, cru)</h3>
<table><tr><th>Pergunta</th><th>Ativo</th><th>Plano</th><th>Quando</th></tr>{recentes_html}</table></div>

<p class='muted' style='font-size:12px'>Fonte: radar_chat_log · histórico coletado a cada conversa · use pra virar FAQ, achar onde o usuário trava e onde a IA pode melhorar.</p>
</body></html>"""
    return HTMLResponse(html)
