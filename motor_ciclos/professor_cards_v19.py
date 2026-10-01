# -*- coding: utf-8 -*-
# ============================================================================
#  PROFESSOR — CARDS DO BLOCO 2 SOBRE A FICHA §9
#  VERSAO: 1.0 | BUILD: 2026-08-31a-cards | motor exigido: 3.2.B+
#  Registro: Feito00103
#
#  O QUE E: o teste como fizemos no comeco — TODAS as estrategias listadas,
#  medidas celula por celula (ativo x timeframe), com percentual de acerto,
#  PF e walk-forward em duas metades. So TFs >= 15m (ordem do dono 31/ago:
#  abaixo disso o ruido e alto; M1-M10 seguem sendo a sensibilidade do corte).
#
#  A SEPARACAO QUE ESTA SESSAO ENSINOU (analise com o dono, 31/ago):
#  - BLOCO 1 = os OLHOS. Identifica tudo. Se testa com casos de aceitacao.
#  - BLOCO 2 = os CARDS. Cada um ESCOLHE qual sinal opera. Se testa com PF/WR.
#  Este runner e o Bloco 2 nascendo: cada card define (1) o sinal de entrada e
#  (2) o risco inicial estrutural. A VIDA da posicao e 100% do Ciclo
#  (decisao (b), Feito00082): corte pela ficha, B1/B3/B5, trailing §5.5,
#  SEM take-profit (palavra do dono 28/ago: a posicao e carregada enquanto o
#  Ciclo indicar continuacao).
#
#  RISCO: stop ESTRUTURAL puro (alem do ultimo pivo do andar + buffer 0,3 ATR
#  [REF]). Os tetos da fase de calibracao (800 pts / 1 ATR / 3 ATR) foram
#  REBAIXADOS a referencia provisoria (dono, 31/ago): cada card tera o SEU
#  MAE medido — por isso o relatorio publica o MAE p95 por celula, que e o
#  insumo da calibracao de stop POR CARD na proxima rodada.
#
#  NADA AQUI DECIDE. Imprime numero e gera o pacote do importador
#  (/admin/estudo/v2/importar). Ligar chave e decisao do dono.
# ============================================================================
from __future__ import annotations
import sys, os, json

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_BAR_TOTAL = 1; _bar_i = 0
def _bar(msg):
    global _bar_i
    _bar_i += 1
    pct = min(100, int(100 * _bar_i / max(_BAR_TOTAL, 1)))
    n = pct * 24 // 100
    sys.stderr.write(f"\r[{'█'*n}{'░'*(24-n)}] {pct:3d}% · {msg:<40s}")
    sys.stderr.flush()

from collections import Counter
import numpy as np, pandas as pd

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path: sys.path.insert(0, _AQUI)
import bloco1_motor_v3 as B1

CARDS_VERSAO = "2.0"; BUILD = "2026-09-13a-comissao-raw"
# v20 (Feito00173 — Fases 3-5 da sequencia selada 00172):
#   COMISSAO RAW MODELADA: US$3,50/lote POR LADO = US$7,00 round-turn
#   (extraida de 53.309 deals da conta do dono — ver_comissao.py, 13/set).
#   Classes com comissao (evidencia dos deals): FOREX e METAIS.
#   Indices/energia/cripto: spread-only (classe IC) — comissao 0, declarado.
#   Conversao USD->pontos POR SIMBOLO calculada DOS PROPRIOS CSVs (mediana de
#   fechamento Daily; quote-JPY converte via USDJPY da pasta; quote CHF/CAD/NZD
#   via USDxxx da pasta). pts = 7 / valor_do_ponto_em_USD_por_lote.
#   Contratos: FX 100k · XAU 100oz · XAG 5000oz.
#   SWAP: v21 (agendado, Feito00172). SLIPPAGE: professor x vivo (demo).
SPREAD_PTS = 5; PONTO = 0.01   # sobrescritos POR ATIVO pela FICHA
IGNORAR_B5 = False             # cripto 24/7: B5 nao se aplica (doutrina)
COM_PTS = 0.0                  # comissao em PONTOS do simbolo (v20)
COMISSAO_RT_USD = 7.0
CONTRATO = {"XAUUSD": 100.0, "XAGUSD": 5000.0}   # FX = 100000 padrao
FX_COM = {"EURUSD","GBPUSD","USDCHF","USDJPY","USDCAD","AUDJPY","GBPJPY","AUDNZD"}
METAIS = {"XAUUSD","XAGUSD"}

def _mediana_close(pasta, atv):
    import glob as _g
    for c in sorted(_g.glob(os.path.join(pasta, f"{atv}_Daily_*.csv"))):
        try:
            d = pd.read_csv(c, sep="\t")
            return float(d["<CLOSE>"].median())
        except Exception:
            pass
    return None

def _comissao_pts(ativo, pasta):
    if ativo not in FX_COM and ativo not in METAIS:
        return 0.0
    tam = CONTRATO.get(ativo, 100000.0)
    quote = "USD" if ativo in METAIS else ativo[3:]
    vp_quote = tam * PONTO
    if quote == "USD":
        vp_usd = vp_quote
    elif quote == "JPY":
        uj = _mediana_close(pasta, "USDJPY")
        if not uj:
            print(f"[custo] {ativo}: sem USDJPY na pasta — comissao NAO modelada (declarado)"); return 0.0
        vp_usd = vp_quote / uj
    else:
        m = _mediana_close(pasta, "USD" + quote)
        if not m:
            print(f"[custo] {ativo}: sem USD{quote} na pasta — comissao NAO modelada (declarado)"); return 0.0
        vp_usd = vp_quote / m
    return COMISSAO_RT_USD / vp_usd

# v1.8: spread E ponto medidos do CSV do proprio ativo (mediana do <SPREAD>;
# ponto = 10^-casas decimais do preco). FICHA so guarda a CLASSE (b5).
FICHA = {
    "XAUUSD": dict(ponto="csv", spread="csv", b5=True),
    "BTCUSD": dict(ponto="csv", spread="csv", b5=False),
    "ETHUSD": dict(ponto="csv", spread="csv", b5=False),
    "US500":  dict(ponto="csv", spread="csv", b5=True),
    "US30":   dict(ponto="csv", spread="csv", b5=True),
    "USTEC":  dict(ponto="csv", spread="csv", b5=True),
    "DE40":   dict(ponto="csv", spread="csv", b5=True),
    "HK50":   dict(ponto="csv", spread="csv", b5=True),
    "USDJPY": dict(ponto="csv", spread="csv", b5=True),
    "USDCHF": dict(ponto="csv", spread="csv", b5=True),
    "EURUSD": dict(ponto="csv", spread="csv", b5=True),
    "GBPUSD": dict(ponto="csv", spread="csv", b5=True),
    "USDCAD": dict(ponto="csv", spread="csv", b5=True),
    "AUDJPY": dict(ponto="csv", spread="csv", b5=True),
    # 1a leva nova (carimbo 07/set): prata, energia, trender, Nikkei
    "XAGUSD": dict(ponto="csv", spread="csv", b5=True),
    "XBRUSD": dict(ponto="csv", spread="csv", b5=True),
    "XTIUSD": dict(ponto="csv", spread="csv", b5=True),
    "GBPJPY": dict(ponto="csv", spread="csv", b5=True),
    "JP225":  dict(ponto="csv", spread="csv", b5=True),
}
TFS_ESTUDO = ["M15", "M30", "H1", "H4", "Daily"]     # >= 15m (ordem do dono)
BUFFER_ATR = 0.3                                      # [REF] §5.5, a medir por card

# ============================================================================
#  INDICADORES CLASSICOS (parametros de literatura, nunca inventados)
# ============================================================================
def _ema(x, n):  return pd.Series(x).ewm(span=n, adjust=False).mean().values
def _sma(x, n):  return pd.Series(x).rolling(n).mean().values
def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = pd.Series(up).ewm(alpha=1/n, adjust=False).mean().values
    rd = pd.Series(dn).ewm(alpha=1/n, adjust=False).mean().values
    rs = np.divide(ru, rd, out=np.full_like(ru, np.inf), where=rd > 0)
    return 100 - 100/(1+rs)
def _boll(c, n=20, k=2.0):
    m = _sma(c, n); s = pd.Series(c).rolling(n).std(ddof=0).values
    return m, m + k*s, m - k*s
def _macd(c, f=12, s_=26, sig=9):
    m = _ema(c, f) - _ema(c, s_); return m, _ema(m, sig)

# ============================================================================
#  OS CARDS — cada um devolve a lista de sinais [(i_sinal, lado, nivel, modo)]
#  modo "gatilho"  = arma no nivel; entrada so com CONTINUIDADE (Feito00094)
#  modo "fechamento" = sinal no fechamento; entrada na ABERTURA da barra seguinte
# ============================================================================
def card_reversao_extremo(F, df):
    """Grupo 1 · opera o 3o sinal de REVERSAO da ficha (escada §5.5)."""
    return [(i, lado, nivel, "gatilho") for (i, lado, nivel, tipo, est) in F.gatilhos
            if tipo == "reversao" and est == "ok"]

def card_rompimento_caixa(F, df):
    """Grupo 1 · opera o rompimento de compressao da ficha (§5.1/§5.2),
    ja liquido das recusas por sacudida (§5.7) e absorcao (§5.9)."""
    return [(i, lado, nivel, "gatilho") for (i, lado, nivel, tipo, est) in F.gatilhos
            if tipo == "rompimento" and est == "ok"]

def card_segunda_entrada_sacudida(F, df):
    """Grupo 1 · sacudida no extremo + evento novo confirmado (§5.7.3, Brooks
    Second Entry): varreu o pivo, fechou de volta -> arma no extremo OPOSTO da
    barra da sacudida; so abre com continuidade."""
    out = []
    h = df.high.values; l = df.low.values
    for i, e, det in F.sac[F.andar_op]:
        if "topo" in det or "varreu o ultimo topo" in det:
            out.append((i, -1, float(l[i]), "gatilho"))     # varreu topo -> venda
        elif "fundo" in det or "varreu o ultimo fundo" in det:
            out.append((i, +1, float(h[i]), "gatilho"))     # varreu fundo -> compra
    return out

def card_canal_ema20(F, df):
    """Grupo 2 · Cruzamento do Canal EMA20 H/L (a casa): fechamento cruza para
    fora do canal na direcao — sinal no fechamento."""
    c = df.close.values; eh = df.ema20_h.values; el = df.ema20_l.values
    out = []
    for i in range(1, len(df)):
        if c[i-1] <= eh[i-1] and c[i] > eh[i]: out.append((i, +1, float(c[i]), "fechamento"))
        if c[i-1] >= el[i-1] and c[i] < el[i]: out.append((i, -1, float(c[i]), "fechamento"))
    return out

def card_ema_9_21(F, df):
    c = df.close.values; e9 = _ema(c, 9); e21 = _ema(c, 21)
    out = []
    for i in range(1, len(df)):
        if e9[i-1] <= e21[i-1] and e9[i] > e21[i]: out.append((i, +1, float(c[i]), "fechamento"))
        if e9[i-1] >= e21[i-1] and e9[i] < e21[i]: out.append((i, -1, float(c[i]), "fechamento"))
    return out

def card_tripla_media(F, df):
    c = df.close.values; e9 = _ema(c, 9); e21 = _ema(c, 21); e50 = _ema(c, 50)
    out = []
    for i in range(1, len(df)):
        if e9[i] > e21[i] > e50[i] and not (e9[i-1] > e21[i-1] > e50[i-1]):
            out.append((i, +1, float(c[i]), "fechamento"))
        if e9[i] < e21[i] < e50[i] and not (e9[i-1] < e21[i-1] < e50[i-1]):
            out.append((i, -1, float(c[i]), "fechamento"))
    return out

def card_rsi(F, df):
    """RSI 14 · 30/70 (Wilder): saiu da zona = sinal."""
    r = _rsi(df.close.values, 14); out = []
    for i in range(1, len(df)):
        if r[i-1] < 30 <= r[i]: out.append((i, +1, float(df.close.iloc[i]), "fechamento"))
        if r[i-1] > 70 >= r[i]: out.append((i, -1, float(df.close.iloc[i]), "fechamento"))
    return out

def card_bollinger_reversao(F, df):
    """BB 20/2: fechou fora e VOLTOU pra dentro = reversao a media."""
    c = df.close.values; m, up, dn = _boll(c); out = []
    for i in range(1, len(df)):
        if c[i-1] < dn[i-1] and c[i] > dn[i]: out.append((i, +1, float(c[i]), "fechamento"))
        if c[i-1] > up[i-1] and c[i] < up[i]: out.append((i, -1, float(c[i]), "fechamento"))
    return out

def card_macd(F, df):
    m, sig = _macd(df.close.values); out = []
    for i in range(1, len(df)):
        if m[i-1] <= sig[i-1] and m[i] > sig[i]: out.append((i, +1, float(df.close.iloc[i]), "fechamento"))
        if m[i-1] >= sig[i-1] and m[i] < sig[i]: out.append((i, -1, float(df.close.iloc[i]), "fechamento"))
    return out

def card_donchian20(F, df):
    """Rompimento Donchian 20 — arma no extremo das 20 anteriores; continuidade abre."""
    h = df.high.values; l = df.low.values; c = df.close.values; out = []
    for i in range(21, len(df)):
        hi = float(np.max(h[i-20:i])); lo = float(np.min(l[i-20:i]))
        if c[i] > hi: out.append((i, +1, float(h[i]), "gatilho"))
        elif c[i] < lo: out.append((i, -1, float(l[i]), "gatilho"))
    return out

def card_sr_dia_anterior(F, df):
    """S&R do dia anterior: fechamento alem do high/low de ontem arma o gatilho."""
    if F.andar_op == "Daily": return []
    d = pd.to_datetime(df.ts.values); dia = pd.Series(d).dt.date.values
    h = df.high.values; l = df.low.values; c = df.close.values
    out = []; hoje = None; hi_ant = lo_ant = None; hi = lo = None
    for i in range(len(df)):
        if dia[i] != hoje:
            hi_ant, lo_ant = hi, lo; hi, lo = h[i], l[i]; hoje = dia[i]
        else:
            hi = max(hi, h[i]); lo = min(lo, l[i])
        if hi_ant is None: continue
        if c[i] > hi_ant and (i == 0 or df.close.iloc[i-1] <= hi_ant):
            out.append((i, +1, float(h[i]), "gatilho"))
        if c[i] < lo_ant and (i == 0 or df.close.iloc[i-1] >= lo_ant):
            out.append((i, -1, float(l[i]), "gatilho"))
    return out

def card_engolfo(F, df):
    """Engolfo a favor do canal: corpo engole o corpo anterior, na direcao do estado."""
    o = df.open.values; c = df.close.values; est = df.estado_canal.values; out = []
    for i in range(1, len(df)):
        corpo_ant = abs(c[i-1] - o[i-1]); corpo = abs(c[i] - o[i])
        if corpo <= corpo_ant: continue
        if c[i] > o[i] and c[i-1] < o[i-1] and c[i] > o[i-1] and o[i] < c[i-1] and est[i] > 0:
            out.append((i, +1, float(c[i]), "fechamento"))
        if c[i] < o[i] and c[i-1] > o[i-1] and c[i] < o[i-1] and o[i] > c[i-1] and est[i] < 0:
            out.append((i, -1, float(c[i]), "fechamento"))
    return out

def card_topo_fundo_duplo(F, df):
    """Topo/Fundo duplo: dois pivos consecutivos no mesmo nivel (ate 0,3 ATR)
    + fechamento rompendo o pivo oposto arma a reversao. O historico de pivos e
    reconstruido dos mapas (que guardam so o ULTIMO confirmado por barra)."""
    A = F.lt.andares[F.andar_op]; c = df.close.values; a = df.atr14.values
    h = df.high.values; l = df.low.values; out = []
    topo_ant = None; fundo_ant = None; topo_atu = None; fundo_atu = None
    for i in range(4, len(df)):
        mp = A.mapas[i]
        if mp.ultimo_topo and mp.ultimo_topo != topo_atu:
            topo_ant, topo_atu = topo_atu, mp.ultimo_topo
        if mp.ultimo_fundo and mp.ultimo_fundo != fundo_atu:
            fundo_ant, fundo_atu = fundo_atu, mp.ultimo_fundo
        atr_i = a[i] if np.isfinite(a[i]) else None
        if atr_i is None: continue
        if topo_ant and topo_atu and abs(topo_ant[1] - topo_atu[1]) <= 0.3 * atr_i and fundo_atu:
            if c[i] < fundo_atu[1] and c[i-1] >= fundo_atu[1]:
                out.append((i, -1, float(l[i]), "gatilho"))
        if fundo_ant and fundo_atu and abs(fundo_ant[1] - fundo_atu[1]) <= 0.3 * atr_i and topo_atu:
            if c[i] > topo_atu[1] and c[i-1] <= topo_atu[1]:
                out.append((i, +1, float(h[i]), "gatilho"))
    return out

CARDS = [
    ("card1_reversao_extremo",   "Reversao no Extremo (Ciclo)",     card_reversao_extremo),
    ("card2_rompimento_caixa",   "Rompimento de Compressao (Ciclo)", card_rompimento_caixa),
    ("card3_segunda_entrada",    "Segunda Entrada pos-Sacudida",     card_segunda_entrada_sacudida),
    ("card4_canal_ema20",        "Cruzamento do Canal EMA20 H/L",    card_canal_ema20),
    ("card5_ema_9_21",           "Cruzamento EMA 9/21",              card_ema_9_21),
    ("card6_tripla_media",       "Tripla Media 9/21/50",             card_tripla_media),
    ("card7_rsi",                "RSI Sobrevenda/Sobrecompra",       card_rsi),
    ("card8_bollinger",          "Bandas de Bollinger — Reversao",   card_bollinger_reversao),
    ("card9_macd",               "MACD Cruzamento",                  card_macd),
    ("card10_donchian20",        "Rompimento Donchian 20",           card_donchian20),
    ("card11_sr_dia_anterior",   "S&R do Dia Anterior",              card_sr_dia_anterior),
    ("card12_engolfo",           "Engolfo a Favor",                  card_engolfo),
    ("card13_topo_fundo_duplo",  "Topo/Fundo Duplo",                 card_topo_fundo_duplo),
]

# ============================================================================
#  O SIMULADOR — identico para todos os cards (a unica coisa que muda e o sinal)
# ============================================================================
def simular_card(F, sinais, F15=None):
    """Entrada no TF do card; VIDA DA POSICAO no relogio do M15 (Feito00104):
    a decisao de corte mora no 15m (§2.2 / Feito00093) — avaliar a vida na
    barra do proprio TF fazia cada barra do Daily conter ~96 barras de M15 e
    sempre haver corte dentro dela (Daily zerava). Stop, trailing, B1/B3/B5 e
    comando: tudo nas barras do M15."""
    F15 = F15 or F
    df = F.D; o = df.open.values; h = df.high.values; l = df.low.values
    c = df.close.values; atr = df.atr14.values; ts = F.ts
    d15 = F15.D; o15 = d15.open.values; h15 = d15.high.values; l15 = d15.low.values
    c15 = d15.close.values; a15v = d15.atr14.values; ts15 = F15.ts
    A15 = F15.lt.andares[F15.andar_op]
    tr = []; i_livre = -1
    for (i_sin, lado, nivel, modo) in sorted(sinais, key=lambda x: x[0]):
        if i_sin <= i_livre: continue
        i_ent = None; ent = None
        if modo == "fechamento":
            # B1 ativo na hora do sinal (ex.: rollover do Daily a meia-noite,
            # spread alargado TODO dia) NAO mata o sinal — a execucao ESPERA a
            # primeira barra de M15 liberada (§7: "volta apos N barras na
            # faixa"). Se o Ciclo virar contra antes de liberar, o sinal morre.
            j = i_sin + 1
            if j >= F.n: continue
            k0 = int(np.searchsorted(ts15, ts[j], side="right")) - 1
            if k0 < 0: continue
            for k in range(k0, min(k0 + 96, F15.n)):     # espera ate 1 dia de M15
                if F15.corta[lado][k]: break             # Ciclo contra: morre
                if F15.B1[k] or (F15.B5[k] and not IGNORAR_B5): continue      # espera liberar
                i_ent = j; ent = float(o15[k]) if k > k0 else float(o[j])
                break
        else:
            # continuidade avaliada nas barras do TF do card (Lei de
            # Confirmacao no TF do sinal); comando e blindagens consultados no
            # RELOGIO DO M15 (a decisao mora la — corrigido: consultar no TF do
            # card fazia o Daily "cortar" toda barra e matar todo gatilho)
            for j in range(i_sin + 1, min(i_sin + 40, F.n)):
                kj = int(np.searchsorted(ts15, ts[j], side="right")) - 1
                if kj >= 0 and F15.corta[lado][kj]: break   # Ciclo contra: morre
                if kj >= 0 and (F15.B1[kj] or (F15.B5[kj] and not IGNORAR_B5)): continue
                abre, _m = B1.entrada_com_continuidade(df, i_sin, nivel, lado, j)
                if abre: i_ent = j; ent = float(c[j]); break
        if i_ent is None: continue
        # risco inicial: estrutura do M15 (o andar da decisao)
        k_ent = int(np.searchsorted(ts15, ts[i_ent], side="right")) - 1
        if k_ent < 0 or k_ent + 1 >= F15.n: continue
        mp = A15.mapas[k_ent]
        if not (mp.ultimo_fundo and mp.ultimo_topo): continue
        est = mp.ultimo_fundo[1] if lado > 0 else mp.ultimo_topo[1]
        a = float(a15v[k_ent])
        if not np.isfinite(a) or a <= 0: continue
        stop = est - lado * BUFFER_ATR * a               # estrutural puro (§5.5)
        if (lado > 0 and stop >= ent) or (lado < 0 and stop <= ent): continue
        stop0 = stop; mae = 0.0; saida = None; mot = ""; ntr = 0
        for k in range(k_ent + 1, min(k_ent + 4000, F15.n)):
            mae = max(mae, (ent - l15[k]) if lado > 0 else (h15[k] - ent))
            if (lado > 0 and l15[k] <= stop) or (lado < 0 and h15[k] >= stop):
                saida, mot = stop, ("stop_trailing" if ntr else "stop"); break
            fk = F15.em(k, lado)
            if fk["blindagens"]["B5"] and not IGNORAR_B5:
                if k + 1 >= F15.n: break
                saida, mot = float(o15[k+1]), "B5"; break
            if (k - k_ent) >= 2 and B1.b3_tempo_sem_progresso(F15.lt, ts15[k], lado).get("corta"):
                if k + 1 >= F15.n: break
                saida, mot = float(o15[k+1]), "B3"; break
            mpk = A15.mapas[k]; ak = float(a15v[k])
            pv = (mpk.ultimo_fundo[1] if lado > 0 else mpk.ultimo_topo[1]) if (mpk.ultimo_fundo and mpk.ultimo_topo) else None
            if pv is not None and np.isfinite(ak) and ak > 0:
                nst = pv - lado * BUFFER_ATR * ak
                if (lado > 0 and nst > stop and nst < c15[k]) or (lado < 0 and nst < stop and nst > c15[k]):
                    stop = nst; ntr += 1                 # trailing §5.5 (so aperta)
            if fk["blindagens"]["B1"]: continue          # choque nao e estrutura
            if fk["comando"] == "CORTE_TOTAL":
                if k + 1 >= F15.n: break
                saida, mot = float(o15[k+1]), "ciclo"; break
        if saida is None: continue
        # a proxima entrada deste card so depois desta posicao fechar (no TF do card)
        i_livre = int(np.searchsorted(ts, ts15[k], side="right")) - 1
        tr.append(dict(pts=(saida - ent) * lado / PONTO - SPREAD_PTS - COM_PTS,
                       mae=mae / PONTO, risco=abs(ent - stop0) / PONTO,
                       motivo=mot, ts=pd.Timestamp(ts[i_ent])))
    return pd.DataFrame(tr)

def metricas(T):
    if len(T) == 0: return None
    g = T[T.pts > 0].pts.sum(); p = -T[T.pts < 0].pts.sum()
    meio = T.ts.min() + (T.ts.max() - T.ts.min()) / 2
    def pf(x):
        a = x[x.pts > 0].pts.sum(); b = -x[x.pts < 0].pts.sum()
        return float(a / b) if b > 0 else float("inf")
    pts = T.pts.values; eq = np.cumsum(pts); dd = float((eq - np.maximum.accumulate(eq)).min())
    sh = float(pts.mean() / pts.std()) if pts.std() > 0 else 0.0
    return dict(trades=len(T), pf=float(g/p) if p > 0 else float("inf"),
                wr=float(100 * (T.pts > 0).mean()), liquido=float(T.pts.sum()),
                wf_a=pf(T[T.ts < meio]), wf_b=pf(T[T.ts >= meio]),
                dd=dd, sharpe=sh, mae_p95=float(T.mae.quantile(.95)),
                pior=float(T.pts.min()))

# ============================================================================
def rodar(pasta="Test 12meses", ativo="XAUUSD", tfs=None):
    tfs = tfs or TFS_ESTUDO
    print(f"PROFESSOR — CARDS DO BLOCO 2 v{CARDS_VERSAO} build {BUILD} | "
          f"motor {B1.MOTOR_VERSAO} build {B1.BUILD_TAG} | {B1.DOC_BLOCO1}")
    print(f"ativo={ativo} | TFs do estudo: {', '.join(tfs)} (>= 15m, ordem do dono)")
    print(f"vida da posicao: 100% Ciclo (corte pela ficha + B1/B3/B5 + trailing §5.5) · SEM take-profit")
    print(f"stop: estrutural + {BUFFER_ATR} ATR [REF] · tetos da calibracao REBAIXADOS — MAE p95 por celula publicado\n")
    global _BAR_TOTAL, _bar_i
    _BAR_TOTAL = max(1, len(tfs) * len(CARDS)); _bar_i = 0
    sys.stderr.write("carregando CSVs (a parte lenta — a barra anda card a card depois)...\n")
    lt = B1.LeitorMultiTF(pasta, ativo).carregar()
    F15 = B1.FichaSerie(lt, "M15", ativo) if "M15" in lt.andares else None
    linhas_pacote = []; t0 = t1 = None
    for tf in tfs:
        if tf not in lt.andares:
            _bar_i += len(CARDS)
            print(f"── {tf}: SEM DADO na pasta — pulado (declarado)"); continue
        F = F15 if (tf == "M15" and F15 is not None) else B1.FichaSerie(lt, tf, ativo)
        df = F.D
        t0 = t0 or pd.Timestamp(df.ts.iloc[0]); t1 = pd.Timestamp(df.ts.iloc[-1])
        print(f"── {tf}  ({len(df)} barras · {pd.Timestamp(df.ts.iloc[0]):%d/%m/%y} → {t1:%d/%m/%y})")
        print(f"   {'card':32s} {'trades':>6s} {'ACERTO':>7s} {'PF':>6s} {'wfA':>5s} {'wfB':>5s} {'liq':>9s} {'MAEp95':>7s}")
        for cid, nome, fn in CARDS:
            _bar(f"{tf} · {nome[:32]}")
            try:
                T = simular_card(F, fn(F, df), F15=F15)
            except Exception as e:
                print(f"   {nome:32s} ERRO: {e}"); continue
            m = metricas(T)
            if m is None or m["trades"] < 5:
                print(f"   {nome:32s} {0 if m is None else m['trades']:6d}  (sem amostra)"); continue
            selo = "💪" if (m["trades"] >= 30 and m["pf"] > 1 and m["wf_a"] > 1 and m["wf_b"] > 1) else \
                   ("✓" if (m["pf"] > 1 and m["trades"] >= 20) else "·")
            print(f"   {nome:32s} {m['trades']:6d} {m['wr']:6.1f}% {m['pf']:6.2f} "
                  f"{m['wf_a']:5.2f} {m['wf_b']:5.2f} {m['liquido']:+9.0f} {m['mae_p95']:7.0f}  {selo}")
            linhas_pacote.append(dict(
                estrategia_id=cid, estrategia_nome=nome, timeframe=tf,
                retorno=round(m["liquido"], 2), profit_factor=round(m["pf"], 3),
                win_rate=round(m["wr"], 2), sharpe=round(m["sharpe"], 3),
                trades=m["trades"], dd=round(m["dd"], 2),
                wf_a_pf=round(m["wf_a"], 3), wf_b_pf=round(m["wf_b"], 3),
                carimbo=dict(buffer_atr=BUFFER_ATR, mae_p95=round(m["mae_p95"], 0),
                             pior=round(m["pior"], 0), vida="100% Ciclo, sem TP",
                             stop="estrutural puro (tetos a calibrar por card)")))
        print()
    if linhas_pacote:
        pac = dict(ativo=ativo, periodo=f"12 meses {t0:%b/%y}–{t1:%b/%y}",
                   origem=dict(fonte="barras MT5 reais", corretora="IC Markets",
                               professor_versao=f"cards {CARDS_VERSAO}",
                               motor_versao=B1.MOTOR_VERSAO, bloco1_versao=B1.DOC_BLOCO1,
                               spread=f"{SPREAD_PTS} pts fixos (informado pelo dono — Market Watch)"),
                   linhas=linhas_pacote)
        # v1.7: sanitizar o pacote inteiro — nenhum numero nao-finito sai pro json
        import math as _math
        def _fin_tudo(o):
            if isinstance(o, dict):  return {k: _fin_tudo(v) for k, v in o.items()}
            if isinstance(o, list):  return [_fin_tudo(v) for v in o]
            if isinstance(o, float) and not _math.isfinite(o): return 999.99
            return o
        pac = _fin_tudo(pac)
        with open(f"pacote_estudo_cards_{ativo}.json", "w", encoding="utf-8") as f:
            json.dump(pac, f, ensure_ascii=False, indent=2)
        print(f"pacote: pacote_estudo_cards_{ativo}.json ({len(linhas_pacote)} celulas) — sobe pelo /admin/estudo/v2/importar")
        print("NADA SOBE SEM O CARIMBO DO DONO.")

def _ficha_do_csv(pasta, ativo):
    """le o M15 do ativo e mede: mediana do <SPREAD> + ponto (casas decimais do close)."""
    import glob, csv as _csv, statistics, os as _os
    for arq in sorted(glob.glob(_os.path.join(pasta, f"{ativo}_M15_*.csv"))):
        try:
            vals = []; dec = 0
            with open(arq, encoding="utf-8", errors="replace") as f:
                r = _csv.reader(f, delimiter="\t")
                head = next(r); ks = head.index("<SPREAD>"); kc = head.index("<CLOSE>")
                for i, row in enumerate(r):
                    if len(row) > ks:
                        vals.append(int(row[ks]))
                        if i < 500 and "." in row[kc]:
                            dec = max(dec, len(row[kc].split(".")[1]))
            if vals:
                return int(statistics.median(vals)), (10.0 ** -dec), _os.path.basename(arq)
        except Exception:
            continue
    return None, None, None

def _aplicar_ficha(ativo, pasta):
    global SPREAD_PTS, PONTO, IGNORAR_B5, COM_PTS
    f = FICHA.get(ativo)
    if f is None:
        print(f"[ficha] {ativo}: SEM FICHA — ponto=0.01 spread={SPREAD_PTS} b5=True (conferir!)")
        return True
    sp, pt = f["spread"], f["ponto"]
    if sp == "csv" or pt == "csv":
        msp, mpt, fonte = _ficha_do_csv(pasta, ativo)
        if msp is None:
            print(f"[ficha] {ativo}: sem CSV M15 na pasta — PULADO")
            return False
        if sp == "csv": sp = msp
        if pt == "csv": pt = mpt
        print(f"[ficha] {ativo}: MEDIDO do CSV — spread {sp} pts · ponto {pt} ({fonte})")
        if sp <= 1:
            print(f"[ficha] {ativo}: spread ~ZERO (conta Raw) — custo real e COMISSAO, "
                  f"NAO modelada: numeros SEM custo, declarado")
    if sp is None:
        print(f"[ficha] {ativo}: SPREAD PENDENTE — PULADO (custo nunca chutado)")
        return False
    SPREAD_PTS = int(sp); PONTO = float(pt); IGNORAR_B5 = (not f["b5"])
    COM_PTS = round(_comissao_pts(ativo, pasta), 2)
    if COM_PTS:
        print(f"[custo] {ativo}: COMISSAO {COM_PTS} pts/trade (US$7 RT/lote, conversao da pasta)")
    print(f"[ficha] {ativo}: ponto={PONTO} spread={SPREAD_PTS} pts "
          f"b5={'ATIVO' if f['b5'] else 'ISENTO (cripto 24/7)'}")
    return True

if __name__ == "__main__":
    args = []; todos = False; spread_cli = None
    for a in sys.argv[1:]:
        if a == "--todos": todos = True
        elif a.startswith("--spread="):
            spread_cli = int(float(a.split("=", 1)[1]))
        else:
            args.append(a)
    pasta = args[0] if len(args) > 0 else "Test 12meses"
    if todos:
        feitos, pulados = [], []
        for ativo in FICHA:
            if not _aplicar_ficha(ativo, pasta):
                pulados.append(ativo + " (sem spread/CSV)"); continue
            try:
                rodar(pasta, ativo, None); feitos.append(ativo)
            except FileNotFoundError:
                print(f"[dados] {ativo}: SEM CSV na pasta — pulado")
                pulados.append(ativo + " (sem CSV)")
            except Exception as e:
                print(f"[ERRO] {ativo}: {type(e).__name__}: {e} — pulado, REPORTAR")
                pulados.append(ativo + " (erro)")
        print(f"\nLOTE: rodados={feitos or chr(8212)} | pulados={pulados or chr(8212)}")
        print("um pacote por ativo: pacote_estudo_cards_<ATIVO>.json — NADA SOBE SEM CARIMBO.")
    else:
        ativo = args[1] if len(args) > 1 else "XAUUSD"
        tfs = args[2:] or None
        if _aplicar_ficha(ativo, pasta):
            if spread_cli is not None:
                SPREAD_PTS = spread_cli
                print(f"[custo] spread sobrescrito no comando: {SPREAD_PTS} pts")
            rodar(pasta, ativo, tfs)
