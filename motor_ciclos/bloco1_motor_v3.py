# -*- coding: utf-8 -*-
# ============================================================================
#  BotTested — bloco1_motor_v3.py
#  VERSAO: 3.2.B | BUILD: 2026-08-30l-gatilho-rompimento | INTERNO (nunca distribui)
#  CICLO DE VERIFICACAO POR TIME FRAME — BLOCO 1 v4.0 (doc oficial 28/ago/2026)
#
#  PARTE A — FUNDACAO (lista de construcao §12, itens 1-4):
#    (1) leitor multi-TF MT5 + agregacao W1/MN1 a partir do D1 + ATR14 + canal EMA20 High/Low
#    (2) mapa de pivos N=2 por andar (ultimo topo/fundo, resistencia/suporte, sequencia)
#    (3) contador de perna L por andar
#    (4) afastamento D do canal (em ATR14) por andar
#  + log de fidelidade (barras lidas, periodo, spread) — auditavel.
#  PARTE B — REGUAS: (5) compressao -> CAIXA (§5.1) · (6) rompimento + Lei de Confirmacao (§5.2) ·
#                    (7) rompimento falso: sustentado / voltou_compressao / sacudida (§5.3, §5.7 parte da caixa)
#  PARTE C — EVENTOS: (8) exaustao E1/E2/E3 + contexto tardio + caixa pos-exaustao (regra b do dono)
#                     (9) escada fina §5.5.1 (sem_continuidade, alertas empilhados, 2o/3o sinal) + corte graduado
#                     (10) respiro esperado §5.6 (perna curta -> pullback presumido, sem alerta)
#
#  LEI DA NAO-CONTAMINACAO: nenhuma regua do bloco1_motor.py v1.0 (22/ago) entra aqui.
#  Motor nasce do zero a partir do documento v4.0. Reguas (parte B) e motor (parte C)
#  entram em arquivos/versoes seguintes, item por item, apos carimbo do dono.
# ============================================================================
MOTOR_VERSAO = "3.2.B"
BUILD_TAG    = "2026-08-30l-gatilho-rompimento"
DOC_BLOCO1   = "CICLO_BLOCO1_CHECKLIST_OFICIAL_v3.md v4.0"

import os, glob, math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# ANDARES (TFs) — nomes como saem do MT5 na pasta Test 12meses
# ---------------------------------------------------------------------------
ANDARES_MT5  = ["M1", "M5", "M10", "M15", "M30", "H1", "H4", "Daily"]   # M10 exportado pelo dono 28/ago (degrau da sequencia: M1->M5->M10->M15)
ANDARES_AGG  = ["W1", "MN1"]                       # agregados do Daily (nunca exportados)
ANDARES      = ANDARES_MT5 + ANDARES_AGG
MINUTOS      = {"M1":1, "M5":5, "M15":15, "M30":30, "H1":60, "H4":240, "Daily":1440}

# ponto (tamanho do <SPREAD> em preco) por ativo — spread do MT5 vem em pontos
# [FROTA] valores da IC Markets conforme digitos do simbolo; conferir no log
PONTO = {"XAUUSD":0.01, "XAGUSD":0.001, "BTCUSD":0.01, "ETHUSD":0.01,
         "USDJPY":0.001, "AUDJPY":0.001, "DE40":0.01, "HK50":0.01,
         "US500":0.01, "USTEC":0.01}

# spread liquido fixo (fallback quando a barra nao traz spread, ex.: Daily) — [FROTA] medicoes 09/ago
SPREAD_FIXO = {"XAUUSD":0.30, "BTCUSD":13.0}       # os demais: preencher com a tabela do dono

# ---------------------------------------------------------------------------
# (1) LEITOR MT5
# ---------------------------------------------------------------------------
def ler_csv_mt5(caminho: str) -> pd.DataFrame:
    """Le um CSV exportado pelo MT5 (TAB, CRLF). Daily nao tem <TIME>."""
    df = pd.read_csv(caminho, sep="\t", engine="c")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    if "time" in df.columns:
        ts = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    else:
        ts = pd.to_datetime(df["date"], format="%Y.%m.%d")
    out = pd.DataFrame({
        "ts":     ts,
        "open":   df["open"].astype(float),
        "high":   df["high"].astype(float),
        "low":    df["low"].astype(float),
        "close":  df["close"].astype(float),
        "tickvol":df.get("tickvol", pd.Series(np.zeros(len(df)))).astype(float),  # TELEMETRIA — nunca voto
        "spread": df.get("spread", pd.Series(np.zeros(len(df)))).astype(float),   # pontos
    })
    out = out.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    return out

def achar_csv(pasta: str, ativo: str, andar: str) -> Optional[str]:
    padrao = os.path.join(pasta, f"{ativo}_{andar}_*.csv")
    lst = sorted(glob.glob(padrao))
    return lst[-1] if lst else None

def agregar(df_d1: pd.DataFrame, regra: str) -> pd.DataFrame:
    """W1 = semana ISO (seg-dom), MN1 = mes calendario — mesma matematica do MT5 (barra fechada)."""
    g = df_d1.set_index("ts")
    if regra == "W1":
        grp = g.groupby([g.index.isocalendar().year, g.index.isocalendar().week])
    else:
        grp = g.groupby([g.index.year, g.index.month])
    agg = grp.agg(ts=("open", lambda s: s.index[0]), open=("open","first"), high=("high","max"),
                  low=("low","min"), close=("close","last"), tickvol=("tickvol","sum"))
    agg["spread"] = 0.0
    return agg.reset_index(drop=True).sort_values("ts").reset_index(drop=True)

# ---------------------------------------------------------------------------
# (1) INDICADORES DE BASE — ATR14 e canal EMA20 High/Low (as duas medias do dono)
# ---------------------------------------------------------------------------
def atr14(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"]-df["low"], (df["high"]-pc).abs(), (df["low"]-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0/n, adjust=False, min_periods=n).mean()     # Wilder RMA (= iATR do MT5)

def ema(s: pd.Series, n: int = 20) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

# ---------------------------------------------------------------------------
# (2) PIVOS N=2 — fractal classico de 5 barras; confirmado 2 barras apos o extremo (atraso declarado)
#     ESTRUTURA = PIVOS, nunca extremo generico de N barras (§4.2)
# ---------------------------------------------------------------------------
N_PIVO = 2

def pivos(df: pd.DataFrame, n: int = N_PIVO) -> Tuple[pd.Series, pd.Series]:
    h = df["high"].values; l = df["low"].values; m = len(df)
    topo = np.zeros(m, dtype=bool); fundo = np.zeros(m, dtype=bool)
    for j in range(n, m-n):
        hj = h[j]; lj = l[j]
        if all(hj > h[j-k] and hj > h[j+k] for k in range(1, n+1)): topo[j] = True
        if all(lj < l[j-k] and lj < l[j+k] for k in range(1, n+1)): fundo[j] = True
    return pd.Series(topo, index=df.index), pd.Series(fundo, index=df.index)

@dataclass
class MapaPivos:
    """Estado do mapa em uma barra i (so pivos CONFIRMADOS ate i, i.e. extremo <= i-N)."""
    ultimo_topo:  Optional[Tuple[int,float]] = None   # (idx, preco) — regua de quebra
    ultimo_fundo: Optional[Tuple[int,float]] = None
    resistencia:  Optional[Tuple[int,float]] = None   # topo anterior ao ultimo
    suporte:      Optional[Tuple[int,float]] = None   # fundo anterior ao ultimo
    seq_topos:    str = "?"                            # asc / desc / mista / ?
    seq_fundos:   str = "?"

def mapa_por_barra(df: pd.DataFrame, topo: pd.Series, fundo: pd.Series, n: int = N_PIVO) -> List[MapaPivos]:
    """Constroi o mapa barra a barra, respeitando o atraso: pivo em j so existe a partir de i=j+n."""
    h = df["high"].values; l = df["low"].values; m = len(df)
    mapas: List[MapaPivos] = []
    ts_list: List[Tuple[int,float]] = []; fs_list: List[Tuple[int,float]] = []
    tp = topo.values; fd = fundo.values
    for i in range(m):
        j = i - n
        if j >= 0:
            if tp[j]: ts_list.append((j, float(h[j])))
            if fd[j]: fs_list.append((j, float(l[j])))
        mp = MapaPivos()
        if ts_list:
            mp.ultimo_topo = ts_list[-1]
            if len(ts_list) >= 2:
                mp.resistencia = ts_list[-2]
                mp.seq_topos = "asc" if ts_list[-1][1] > ts_list[-2][1] else ("desc" if ts_list[-1][1] < ts_list[-2][1] else "mista")
        if fs_list:
            mp.ultimo_fundo = fs_list[-1]
            if len(fs_list) >= 2:
                mp.suporte = fs_list[-2]
                mp.seq_fundos = "asc" if fs_list[-1][1] > fs_list[-2][1] else ("desc" if fs_list[-1][1] < fs_list[-2][1] else "mista")
        mapas.append(mp)
    return mapas

# ---------------------------------------------------------------------------
# (3) CONTADOR DE PERNA L — barras consecutivas na mesma direcao sem respiro (§4.3)
#     direcao da barra = sinal de (close - open); doji (=0) nao quebra nem soma
# ---------------------------------------------------------------------------
def contador_perna(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    d = np.sign(df["close"].values - df["open"].values)
    L = np.zeros(len(d), dtype=int); dirs = np.zeros(len(d), dtype=int)
    run_dir = 0; run_len = 0
    for i, di in enumerate(d):
        if di == 0:
            pass
        elif di == run_dir:
            run_len += 1
        else:
            run_dir = int(di); run_len = 1
        L[i] = run_len; dirs[i] = run_dir
    return pd.Series(L, index=df.index), pd.Series(dirs, index=df.index)

# ---------------------------------------------------------------------------
# (4) AFASTAMENTO D — distancia do fechamento ao canal EMA20 H/L, em multiplos de ATR14 (§4.4)
#     positivo = acima da EMA20 High; negativo = abaixo da EMA20 Low; 0 = dentro do canal
# ---------------------------------------------------------------------------
def afastamento(df: pd.DataFrame) -> pd.Series:
    c = df["close"]; eh = df["ema20_h"]; el = df["ema20_l"]; a = df["atr14"]
    dist = np.where(c > eh, (c-eh), np.where(c < el, (c-el), 0.0))
    return pd.Series(dist, index=df.index) / a.replace(0, np.nan)

# ---------------------------------------------------------------------------
# ANDAR — um TF carregado e enriquecido
# ---------------------------------------------------------------------------
@dataclass
class Andar:
    ativo: str
    nome: str
    df: pd.DataFrame
    mapas: List[MapaPivos] = field(default_factory=list)
    origem: str = ""                 # caminho do CSV ou "agregado(Daily)"

    def enriquecer(self):
        df = self.df
        df["atr14"]   = atr14(df)
        df["ema20_h"] = ema(df["high"])
        df["ema20_l"] = ema(df["low"])
        df["canal_w"] = df["ema20_h"] - df["ema20_l"]
        df["estado_canal"] = np.where(df["close"] > df["ema20_h"], 1, np.where(df["close"] < df["ema20_l"], -1, 0))
        tp, fd = pivos(df)
        df["pivo_topo"] = tp; df["pivo_fundo"] = fd
        self.mapas = mapa_por_barra(df, tp, fd)
        df["perna_L"], df["perna_dir"] = contador_perna(df)
        df["afast_D"] = afastamento(df)
        return self

# ---------------------------------------------------------------------------
# LEITOR MULTI-TF
# ---------------------------------------------------------------------------
class LeitorMultiTF:
    def __init__(self, pasta: str, ativo: str):
        self.pasta = pasta; self.ativo = ativo
        self.andares: Dict[str, Andar] = {}
        self.log: List[str] = []

    def carregar(self, andares: List[str] = None) -> "LeitorMultiTF":
        andares = andares or ANDARES
        for a in [x for x in andares if x in ANDARES_MT5]:
            cam = achar_csv(self.pasta, self.ativo, a)
            if not cam:
                self.log.append(f"  {a:6s} AUSENTE — sem leitura neste andar (declarado)"); continue
            df = ler_csv_mt5(cam)
            self.andares[a] = Andar(self.ativo, a, df, origem=os.path.basename(cam)).enriquecer()
        if "Daily" in self.andares:
            for a in [x for x in andares if x in ANDARES_AGG]:
                df = agregar(self.andares["Daily"].df[["ts","open","high","low","close","tickvol","spread"]].copy(), a)
                self.andares[a] = Andar(self.ativo, a, df, origem="agregado(Daily)").enriquecer()
        return self

    # ---- log de fidelidade (auditavel) ----
    def relatorio_fidelidade(self) -> str:
        L = [f"BLOCO 1 v3 — FUNDACAO | motor {MOTOR_VERSAO} build {BUILD_TAG} | doc {DOC_BLOCO1}",
             f"ativo={self.ativo} pasta={self.pasta}",
             f"ponto={PONTO.get(self.ativo,'?')} spread_fixo_fallback={SPREAD_FIXO.get(self.ativo,'?')}"]
        for a in ANDARES:
            if a not in self.andares: L.append(f"  {a:6s} AUSENTE"); continue
            d = self.andares[a].df
            sp = d["spread"]; sp_txt = (f"spread(pts) mediana={sp.median():.0f} p95={sp.quantile(.95):.0f} max={sp.max():.0f}"
                                        if sp.max() > 0 else "spread=0 (usa fallback)")
            L.append(f"  {a:6s} barras={len(d):7d}  {d['ts'].iloc[0]} -> {d['ts'].iloc[-1]}  "
                     f"topos={int(d['pivo_topo'].sum()):6d} fundos={int(d['pivo_fundo'].sum()):6d}  "
                     f"ATR14(ult)={d['atr14'].iloc[-1]:.4f} (nan = menos de 14 barras, declarado)  {sp_txt}  origem={self.andares[a].origem}")
        L += self.log
        return "\n".join(L)


# ===========================================================================
# PARTE B — (5) DETECTOR DE COMPRESSAO -> OBJETO CAIXA  (doc v3.4 §5.1)
#   "Pequeno" e sempre RELATIVO ao ATR14 do proprio andar. Quatro testes por barra:
#     T1 SOBREPOSICAO : barra atual dentro de >= Z do range da anterior            [TRAD] Brooks
#     T2 RANGE RELATIVO: range < min(range das N_NR-1 anteriores) (NR-N) OU < X*ATR14  [LIVRO] Crabel / [FROTA]
#     T3 AVANCO REAL  : |close_i - close_{i-N_AV}| < W*ATR14                       [DONO]
#     T4 CANAL        : largura EMA20 H/L < K*ATR14                                [TRAD] Keltner
#   Barra "comprimida" = pelo menos MIN_TESTES dos 4 batendo (default 3 — [TRAD], v5 mede 2/3/4).
#   CAIXA arma quando N_CAIXA barras consecutivas comprimidas (3 = barbwire [LIVRO]; 2 = candidata).
#   Fronteiras = max/min do bloco que armou. Caixa vive enquanto os FECHAMENTOS ficam dentro;
#   fechamento fora = fim da caixa (estado 'rompida_pendente' — a confirmacao e o item 6).
#   Teste-irmao: altura da caixa <= ALT_UP * ATR14 do ANDAR DE CIMA -> 'apertada'; senao 'larga'
#   (candle grande com sobreposicao alta TAMBEM e lateral — Brooks; 'larga' nao invalida).
#   Doji/corpo pequeno = reforco (contado), nunca condicao.
# ===========================================================================
PARAMS_COMPRESSAO = dict(Z=0.50, N_NR=7, X=0.8, N_AV=3, W=1.0, K=1.0, MIN_TESTES=3, N_CAIXA=3, ALT_UP=0.25, DOJI=0.35)


def testes_compressao(df: pd.DataFrame, P: dict = None) -> pd.DataFrame:
    P = {**PARAMS_COMPRESSAO, **(P or {})}
    h=df["high"].values; l=df["low"].values; o=df["open"].values; c=df["close"].values; a=df["atr14"].values
    m=len(df); rng=h-l
    t1=np.zeros(m,bool); t2=np.zeros(m,bool); t3=np.zeros(m,bool); t4=np.zeros(m,bool); dj=np.zeros(m,bool)
    ch=(df["ema20_h"]-df["ema20_l"]).values
    for i in range(1,m):
        if not np.isfinite(a[i]) or a[i]<=0: continue
        rp=rng[i-1]
        if rp>0:
            ov=min(h[i],h[i-1])-max(l[i],l[i-1])
            t1[i]= ov/rp >= P["Z"]
        j0=max(0,i-P["N_NR"]+1)
        nr = i-j0>=1 and rng[i] < np.min(rng[j0:i])
        t2[i]= nr or rng[i] < P["X"]*a[i]
        k=i-P["N_AV"]
        if k>=0: t3[i]= abs(c[i]-c[k]) < P["W"]*a[i]
        t4[i]= ch[i] < P["K"]*a[i]
        dj[i]= rng[i]>0 and abs(c[i]-o[i]) <= P["DOJI"]*rng[i]
    out=pd.DataFrame({"t1":t1,"t2":t2,"t3":t3,"t4":t4,"doji":dj}, index=df.index)
    out["n_testes"]=out[["t1","t2","t3","t4"]].sum(axis=1)
    out["comprimida"]=out["n_testes"]>=P["MIN_TESTES"]
    return out

def atr_andar_de_cima(df: pd.DataFrame, df_up: Optional[pd.DataFrame]) -> Optional[np.ndarray]:
    """ATR14 de um andar de referencia alinhado por tempo (ultima barra FECHADA do andar de cima <= ts)."""
    if df_up is None: return None
    up = df_up[["ts","atr14"]].dropna()
    if len(up) == 0: return None
    idx = np.searchsorted(up["ts"].values, df["ts"].values, side="right")-1
    vals = np.where(idx>=0, up["atr14"].values[np.clip(idx,0,len(up)-1)], np.nan)
    return vals

@dataclass
class Caixa:
    andar: str
    i_ini: int; ts_ini: object
    i_fim: int; ts_fim: object
    piso: float; teto: float                 # fronteiras = min/max do bloco INTEIRO (Darvas/Brooks)
    teto_conf: bool; piso_conf: bool         # fronteira CONFIRMADA = 3 barras sem exceder (Darvas N=3 [LIVRO])
    altura: float
    altura_atr_d1: Optional[float]           # altura / ATR14 do D1 (Brooks: range apertado vs range diario)
    altura_atr_andar: float                  # altura / ATR14 do proprio andar (minimo p/ nao ser ruido)
    classe: str                              # 'apertada' | 'normal' | 'micro'
    n_barras: int
    range_maduro: bool                       # > 20 barras (Brooks: perde influencia da tendencia anterior)
    reativada: int                           # 'voltou pra compressao' absorvidos (§5.3)
    sacudidas: int                           # violinas dentro da caixa (§5.7)
    fim: str                                 # rompida_pendente_cima / rompida_pendente_baixo / fim_dados
    testes_medios: Tuple[float,float,float,float]
    doji_pct: float

PARAMS_CAIXA = dict(N_CONF=3, ALT_APERTADA_D1=0.25, ALT_MICRO_ANDAR=0.5, MADURO=20,
                    # (7) ROMPIMENTO FALSO [TRAD, v5 mede]: apos confirmacao, N_SUST barras para SUSTENTAR
                    #   sustentado = fechamento >= fronteira + X_SUST*ATR14 (avanco real alem da caixa)
                    #   voltou     = fechamento de volta DENTRO -> caixa reativa (une)
                    #   sacudida   = furo + volta dentro + barra seguinte vai pro outro lado (carimbo)
                    N_SUST=3, X_SUST=1.0,
                    # UNIAO de caixas vizinhas (Brooks: range = zona): caixa nova arma em ate M_UNE barras
                    #   apos o fim da anterior SEM que o preco tenha avancado X_UNE*ATR alem da fronteira antiga
                    M_UNE=6, X_UNE=1.0,
                    # TETO de altura de caixa no andar (§5.9): acima disso e range do andar de cima, nao compressao
                    ALT_MAX_D1=0.5)

def _atr_ref_altura(df, lt_andares, andar_nome):
    """referencia de altura: D1 para andares intraday; W1 para D1 e acima (Brooks, range vs dia)."""
    ref = "D1" if andar_nome in ("M1","M5","M15","M30","H1","H4") else "W1"
    ref = {"D1":"Daily"}.get(ref, ref)
    if lt_andares is None or ref not in lt_andares: return None
    return atr_andar_de_cima(df, lt_andares[ref].df)

def detectar_caixas(andar: "Andar", lt_andares: Dict[str,"Andar"] = None, P: dict = None, PC: dict = None) -> List[Caixa]:
    P = {**PARAMS_COMPRESSAO, **(P or {})}; PC = {**PARAMS_CAIXA, **(PC or {})}
    df=andar.df; T=testes_compressao(df,P); comp=T["comprimida"].values
    h=df["high"].values; l=df["low"].values; c=df["close"].values; ts=df["ts"].values; a=df["atr14"].values
    atr_ref = _atr_ref_altura(df, lt_andares, andar.nome)
    caixas: List[Caixa]=[]; i=0; m=len(df); run=0
    while i<m:
        run = run+1 if comp[i] else 0
        if run>=P["N_CAIXA"]:
            i0=i-P["N_CAIXA"]+1
            piso=float(np.min(l[i0:i+1])); teto=float(np.max(h[i0:i+1]))
            j=i+1; fim="fim_dados"
            # CRESCIMENTO: incorpora enquanto o FECHAMENTO fica dentro; fronteiras = extremos do bloco inteiro.
            # FIM so por rompimento CONFIRMADO (§5.2 Lei de Confirmacao): fechamento fora = pendente; a barra
            # seguinte precisa quebrar o extremo da barra que rompeu. Sem confirmacao = "voltou pra compressao"
            # (§5.3): a caixa CONTINUA (reativa) e a barra que furou entra nas fronteiras.
            voltas=0; sacud=0
            while j<m:
                if c[j]>teto or c[j]<piso:
                    cima = c[j]>teto
                    conf = j+1<m and ((cima and h[j+1]>h[j]) or ((not cima) and l[j+1]<l[j]))
                    if not conf:
                        # (6) fechamento fora SEM confirmacao = pendente que falhou -> voltou (§5.3)
                        voltas+=1
                        teto=max(teto,float(h[j])); piso=min(piso,float(l[j]))
                        if j+1<m: teto=max(teto,float(h[j+1])); piso=min(piso,float(l[j+1]))
                        j+=2; continue
                    # (7) CONFIRMADO: precisa SUSTENTAR em N_SUST barras
                    fr = teto if cima else piso; atr_j = a[j] if np.isfinite(a[j]) and a[j]>0 else 0.0
                    k=j+2; res="sem_avanco"
                    while k<m and k<=j+1+PC["N_SUST"]:
                        if (cima and c[k]>=fr+PC["X_SUST"]*atr_j) or ((not cima) and c[k]<=fr-PC["X_SUST"]*atr_j):
                            res="sustentado"; break
                        if piso<=c[k]<=teto:
                            res="voltou"; break
                        k+=1
                    if res=="voltou":
                        voltas+=1
                        # sacudida: a barra seguinte a volta cruza para o outro lado da caixa (§5.7)
                        if k+1<m and ((cima and c[k+1]<c[k]) or ((not cima) and c[k+1]>c[k])): sacud+=1
                        for q in range(j, min(k,m-1)+1): teto=max(teto,float(h[q])); piso=min(piso,float(l[q]))
                        j=k+1; continue
                    fim = ("rompida_confirmada_cima" if cima else "rompida_confirmada_baixo") + ("" if res=="sustentado" else "_sem_avanco")
                    break
                if h[j]>teto: teto=float(h[j])
                if l[j]<piso: piso=float(l[j])
                if atr_ref is not None and np.isfinite(atr_ref[j]) and (teto-piso) > PC["ALT_MAX_D1"]*atr_ref[j]:
                    fim="virou_range_maior"; j+=1; break
                j+=1
            j_fim=min(j,m-1) if fim!="fim_dados" else m-1
            ult = j_fim if fim=="fim_dados" else j-1          # ultima barra DENTRO
            # FRONTEIRAS CONFIRMADAS (Darvas): N_CONF barras apos o extremo sem excede-lo, dentro da caixa
            def confirmada(vals, ext, maior):
                idx=[k for k in range(i0, ult+1) if vals[k]==ext]
                if not idx: return False
                k=idx[0]; fim_k=min(k+PC["N_CONF"], ult)
                return (fim_k-k)>=PC["N_CONF"] and all((vals[q]<ext) if maior else (vals[q]>ext) for q in range(k+1,fim_k+1))
            teto_conf = confirmada(h, teto, True); piso_conf = confirmada(l, piso, False)
            alt=teto-piso
            ar = atr_ref[i] if atr_ref is not None and np.isfinite(atr_ref[i]) else None
            aa = a[i] if np.isfinite(a[i]) and a[i]>0 else np.nan
            alt_d1 = (alt/ar) if ar else None; alt_andar = alt/aa if np.isfinite(aa) else np.nan
            if np.isfinite(alt_andar) and alt_andar < PC["ALT_MICRO_ANDAR"]: classe="micro"
            elif alt_d1 is not None and alt_d1 <= PC["ALT_APERTADA_D1"]: classe="apertada"
            else: classe="normal"
            nb = ult-i0+1
            cx = Caixa(andar.nome, i0, ts[i0], ult, ts[ult], piso, teto, teto_conf, piso_conf, alt, alt_d1, alt_andar, classe,
                       nb, nb>PC["MADURO"], voltas, sacud, fim,
                       tuple(float(T[t].iloc[i0:ult+1].mean()) for t in ("t1","t2","t3","t4")), float(T["doji"].iloc[i0:ult+1].mean()))
            # UNIAO (Brooks: range = zona; §5.3): caixa nova em ate M_UNE barras apos a anterior, e o preco
            # nao avancou X_UNE*ATR alem da fronteira antiga entre as duas -> e a MESMA caixa (une)
            if caixas:
                pv=caixas[-1]; gap = cx.i_ini - pv.i_fim - 1
                if gap <= PC["M_UNE"]:
                    seg = c[pv.i_fim+1:cx.i_fim+1]; atr_ref_une = a[cx.i_ini] if np.isfinite(a[cx.i_ini]) else 0.0
                    subiu = float(np.max(seg)) - pv.teto if len(seg) else 0.0
                    caiu  = pv.piso - float(np.min(seg)) if len(seg) else 0.0
                    novo_teto=max(pv.teto, cx.teto, float(np.max(h[pv.i_ini:cx.i_fim+1]))); novo_piso=min(pv.piso, cx.piso, float(np.min(l[pv.i_ini:cx.i_fim+1])))
                    cabe = (ar is None) or ((novo_teto-novo_piso) <= PC["ALT_MAX_D1"]*ar)
                    sobrepoe = min(pv.teto,cx.teto) > max(pv.piso,cx.piso)
                    if cabe and (sobrepoe or max(subiu, caiu) < PC["X_UNE"]*atr_ref_une):
                        pv.i_fim=cx.i_fim; pv.ts_fim=cx.ts_fim
                        pv.piso=min(pv.piso, cx.piso, float(np.min(l[pv.i_ini:cx.i_fim+1]))); pv.teto=max(pv.teto, cx.teto, float(np.max(h[pv.i_ini:cx.i_fim+1])))
                        pv.altura=pv.teto-pv.piso; pv.n_barras=pv.i_fim-pv.i_ini+1; pv.range_maduro=pv.n_barras>PC["MADURO"]
                        pv.reativada+=cx.reativada+1; pv.sacudidas+=cx.sacudidas; pv.fim=cx.fim
                        pv.teto_conf=pv.teto_conf or cx.teto_conf; pv.piso_conf=pv.piso_conf or cx.piso_conf
                        pv.altura_atr_d1=(pv.altura/ar) if ar else None; pv.altura_atr_andar=pv.altura/aa if np.isfinite(aa) else np.nan
                        pv.classe = "micro" if (np.isfinite(pv.altura_atr_andar) and pv.altura_atr_andar<PC["ALT_MICRO_ANDAR"]) else ("apertada" if (pv.altura_atr_d1 is not None and pv.altura_atr_d1<=PC["ALT_APERTADA_D1"]) else "normal")
                        i=j+1; run=0; continue
            caixas.append(cx)
            i=j+1; run=0; continue
        i+=1
    if "n_testes" not in andar.df.columns: andar.df=pd.concat([df, T], axis=1)
    return caixas

def imprimir_caixas(caixas: List[Caixa], desde=None, ate=None, digitos=2, so_estruturais=False):
    L=[]
    for cx in caixas:
        if desde is not None and pd.Timestamp(cx.ts_fim)<pd.Timestamp(desde): continue
        if ate is not None and pd.Timestamp(cx.ts_ini)>pd.Timestamp(ate): continue
        if so_estruturais and cx.classe=="micro": continue
        ad = f"{cx.altura_atr_d1:.2f}xATR_D1" if cx.altura_atr_d1 is not None else "ATR_D1=n/d"
        L.append(f"  {pd.Timestamp(cx.ts_ini):%d/%m %H:%M} -> {pd.Timestamp(cx.ts_fim):%d/%m %H:%M}  n={cx.n_barras:3d}{' MADURO' if cx.range_maduro else ''}"
                 f"{(' voltou x'+str(cx.reativada)) if cx.reativada else ''}{(' SACUDIDA x'+str(cx.sacudidas)) if cx.sacudidas else ''}  [{cx.piso:.{digitos}f} , {cx.teto:.{digitos}f}] "
                 f"teto{'✓' if cx.teto_conf else '?'} piso{'✓' if cx.piso_conf else '?'}  alt={cx.altura:.{digitos}f} ({cx.altura_atr_andar:.1f}xATR {ad}) {cx.classe.upper()}  "
                 f"T1/T2/T3/T4={'/'.join(f'{x:.0%}' for x in cx.testes_medios)} doji={cx.doji_pct:.0%}  fim={cx.fim}")
    return "\n".join(L) if L else "  (nenhuma caixa no trecho)"


# ===========================================================================
# PARTE C — (8)(9)(10) EXAUSTAO + ESCADA FINA + RESPIRO  (doc v3.5 §5.4/§5.5.1/§5.6)
#   Roda barra a barra, sem ver o futuro. Cada evento sai com carimbo e barra.
# ===========================================================================
PARAMS_ESCADA = dict(
    L_TARDIO=20, D_TARDIO=2.0,      # contexto tardio: perna >= L ou afastamento >= D x ATR   [TRAD]
    E1_RANGE=2.0, E1_CORPO=0.6,     # E1 climax: range >= 2xATR com corpo dominante           [LIVRO Brooks]
    E2_PAVIO=2/3,                    # E2 rejeicao: pavio reverso >= 2/3 do range               [LIVRO Nison/Fuller]
    DOJI=0.35,                       # corpo <= 35% do range                                     [TRAD]
    L_SEMCONT=3,                     # sem_continuidade: perna >= 3 barras                       [dono, §5.5.1]
    RESPIRO_PASSO=0.7,               # respiro: barra contra com corpo <= 0.7x passo medio       [TRAD Raschke]
)
# §11 — PARAMETRO UNICO EM TODOS OS ANDARES (decisao do dono, 28/ago, Feito00089).
# Revoga a calibracao por andar do v3.6 (Daily L=10/D=1,0/E2=0,60), que era
# curve-fitting meu: eu baixava o numero ate o caso acender.
# FUNDAMENTO (pesquisa profissional trazida ao dono, 28/ago):
#   L=20  — Brooks aplica "mais de 20 barras na tendencia = exaustao" TAMBEM no
#           grafico DIARIO (EURUSD diario: maior barra de baixa em meses depois de
#           um movimento de 20+ barras = barra de exaustao, nao rompimento) e usa
#           10-20 no semanal. Nao existe numero menor "para TF grande".
#   E2=2/3 — a literatura converge: pavio >= 2/3 do range; abaixo disso o setup e
#           marginal e estatisticamente rende menos. E pin bar de Daily/H4 e MAIS
#           confiavel que de TF menor — logo o criterio no Daily nao se afrouxa.
# POR QUE ISSO FUNCIONA SEM CALIBRAR POR ANDAR: o contexto tardio nao precisa ser
# acumulado pelo andar sozinho — quem entrega "tarde na perna" e o CICLO subindo
# (uma perna de 4 dias no Daily = 24 barras de H4 = ~96 de H1 = ~400 de M15).
# O andar de cima recebe o contexto ja confirmado pelos de baixo (doutrina-mae).
# Depende do item 16 da §12 (replicacao entre andares) — declarado.
PARAMS_ESCADA_ANDAR = {}   # vazio de proposito: o Ciclo e completo em todos os andares

def eventos_escada(andar: "Andar", P: dict = None, tardio_ext=None) -> List[Tuple[int,str,str]]:
    """(8)+(9)+(10): eventos por barra no andar. Retorna [(i, evento, detalhe)].
    tardio_ext (item 16, replicacao): vetor booleano por barra dizendo que os
    ANDARES DE BAIXO ja confirmam contexto tardio nesta barra. O contexto tardio
    deixa de ser calculado so pelo proprio andar e passa a ser o Ciclo subindo —
    'o Ciclo tem que ser completo na visao por inteiro, na conversa entre os
    andares' (dono, 28/ago). Sem o vetor, cai no calculo do proprio andar."""
    P = {**PARAMS_ESCADA, **PARAMS_ESCADA_ANDAR.get(andar.nome, {}), **(P or {})}
    df=andar.df; h=df.high.values; l=df.low.values; o=df.open.values; c=df.close.values
    a=df.atr14.values; L=df.perna_L.values; dirn=df.perna_dir.values; D=df.afast_D.values
    m=len(df); rng=h-l; corpo=np.abs(c-o); ev=[]
    passo=pd.Series(rng).rolling(10).mean().values          # passo medio das 10 [TRAD]
    exa_dir=0; exa_i=-1; exa_ext=np.nan                     # ultima exaustao identificada (direcao da perna exausta)
    alerta=0; alerta_dir=0                                   # alertas empilhados (§5.5.1)
    topo_cand=None; fundo_cand=None                          # pivo candidato N=1 (i, preco)
    for i in range(2, m-1):
        if not np.isfinite(a[i]) or a[i]<=0: continue
        tardio = (L[i]>=P["L_TARDIO"]) or (abs(D[i])>=P["D_TARDIO"]) if np.isfinite(D[i]) else (L[i]>=P["L_TARDIO"])
        if tardio_ext is not None and i < len(tardio_ext) and tardio_ext[i]:
            tardio = True          # os andares de baixo ja contaram a perna longa
        no_ext_alta = dirn[i]>0 and h[i]>=np.max(h[max(0,i-10):i+1])
        no_ext_baixa= dirn[i]<0 and l[i]<=np.min(l[max(0,i-10):i+1])
        no_ext = no_ext_alta or no_ext_baixa
        # ---- (10) RESPIRO ESPERADO: perna SEM contexto tardio + barra contra rasa = pullback presumido
        if not tardio and L[i-1]>=P["L_SEMCONT"] and dirn[i-1]!=0 and np.sign(c[i]-o[i])==-dirn[i-1] \
           and np.isfinite(passo[i]) and corpo[i]<=P["RESPIRO_PASSO"]*passo[i]:
            ev.append((i,"respiro_esperado",f"perna L={int(L[i-1])} {'U' if dirn[i-1]>0 else 'D'}, recuo raso"))
        # ---- (8) EXAUSTAO: contexto tardio + gatilho no extremo
        if tardio and no_ext:
            e1 = rng[i]>=P["E1_RANGE"]*a[i] and corpo[i]>=P["E1_CORPO"]*rng[i] and L[i]>=3   # §5.6: barra grande CEDO na perna = rompimento, nunca exaustao
            pav = (h[i]-max(o[i],c[i])) if dirn[i]>0 else (min(o[i],c[i])-l[i])
            e2 = rng[i]>0 and pav>=P["E2_PAVIO"]*rng[i]
            e3 = False
            if i>=4 and dirn[i]>0 and dirn[i-1]>0 and dirn[i-2]>0:
                a1=h[i-2]-h[i-3] if i>=3 else np.nan; a2=h[i-1]-h[i-2]; a3=h[i]-h[i-1]
                e3 = np.isfinite(a1) and a1>0 and a2>0 and a3>0 and a3<a2<a1
            if i>=4 and dirn[i]<0 and dirn[i-1]<0 and dirn[i-2]<0:
                a1=l[i-3]-l[i-2] if i>=3 else np.nan; a2=l[i-2]-l[i-1]; a3=l[i-1]-l[i]
                e3 = e3 or (np.isfinite(a1) and a1>0 and a2>0 and a3>0 and a3<a2<a1)
            gat = ("E1" if e1 else "")+("E2" if e2 else "")+("E3" if e3 else "")
            if gat:
                exa_dir=int(dirn[i]); exa_i=i; exa_ext = h[i] if dirn[i]>0 else l[i]
                alerta=0
                ev.append((i,"exaustao_identificada",f"{gat} {'topo' if dirn[i]>0 else 'fundo'} perna L={int(L[i])} D={D[i]:+.1f}ATR"))
        # ---- (9) ESCADA FINA §5.5.1 — contra a perna vigente (protecao de posicao a favor)
        d_prev = dirn[i-1]
        if d_prev>0 and L[i-1]>=P["L_SEMCONT"]:
            if h[i]<=h[i-1]:
                ev.append((i,"sem_continuidade","alta: nao superou a maxima da anterior"))
                if alerta_dir!=1: alerta,alerta_dir=0,1
                alerta=max(alerta,1)
            elif c[i]<c[i-1] and c[i]<o[i]:
                ev.append((i,"sem_continuidade","alta: furou a maxima e FECHOU contra (furo sem fechamento)"))
                if alerta_dir!=1: alerta,alerta_dir=0,1
                alerta=max(alerta,1)
        if d_prev<0 and L[i-1]>=P["L_SEMCONT"]:
            if l[i]>=l[i-1]:
                ev.append((i,"sem_continuidade","baixa: nao perdeu a minima da anterior"))
                if alerta_dir!=-1: alerta,alerta_dir=0,-1
                alerta=max(alerta,1)
            elif c[i]>c[i-1] and c[i]>o[i]:
                ev.append((i,"sem_continuidade","baixa: furou a minima e FECHOU contra (furo sem fechamento)"))
                if alerta_dir!=-1: alerta,alerta_dir=0,-1
                alerta=max(alerta,1)
        # pivo candidato N=1 (2o alerta) — confirmado na barra i para extremo em i-1
        if i>=2 and l[i-1]<l[i-2] and l[i-1]<l[i] :
            fundo_cand=(i-1,float(l[i-1]))
            if alerta_dir==1 and alerta>=1:
                alerta=max(alerta,2); ev.append((i,"pivo_candidato_fundo",f"fundo N=1 em {l[i-1]:.2f} (alerta 2)"))
        if i>=2 and h[i-1]>h[i-2] and h[i-1]>h[i]:
            topo_cand=(i-1,float(h[i-1]))
            if alerta_dir==-1 and alerta>=1:
                alerta=max(alerta,2); ev.append((i,"pivo_candidato_topo",f"topo N=1 em {h[i-1]:.2f} (alerta 2)"))
        # doji no extremo (3o alerta)
        if rng[i]>0 and corpo[i]<=P["DOJI"]*rng[i] and alerta>=2:
            alerta=3
            ev.append((i,"alerta_empilhado_3","sem_continuidade + pivo candidato + doji -> CORTE com posicao a favor (§5.5.1)"))
            alerta=0
        # 2o SINAL FINO: minima/maxima da barra do topo/fundo rompida por FECHAMENTO da seguinte
        if topo_cand and i>topo_cand[0] and i<=topo_cand[0]+2 and c[i]<l[topo_cand[0]]:
            ev.append((i,"topo_barra_rompida",f"2o sinal: fechamento {c[i]:.2f} < minima da barra do topo ({l[topo_cand[0]]:.2f})"))
            topo_cand=None
        if fundo_cand and i>fundo_cand[0] and i<=fundo_cand[0]+2 and c[i]>h[fundo_cand[0]]:
            ev.append((i,"fundo_barra_rompido",f"2o sinal: fechamento {c[i]:.2f} > maxima da barra do fundo ({h[fundo_cand[0]]:.2f})"))
            fundo_cand=None
        # 3o SINAL: ultimo fundo/topo do mapa rompido por fechamento -> corte total + entrada
        mp = andar.mapas[i]
        if mp.ultimo_fundo and c[i] < mp.ultimo_fundo[1] and c[i-1] >= mp.ultimo_fundo[1]:
            ctxq = "REVERSAO (3o sinal: corte total + entrada)" if dirn[i-1]>0 or exa_dir>0 else "continuacao da baixa"
            ev.append((i,"rompeu_ultimo_fundo",f"fechou {c[i]:.2f} < ultimo fundo {mp.ultimo_fundo[1]:.2f} — {ctxq}"))
        if mp.ultimo_topo and c[i] > mp.ultimo_topo[1] and c[i-1] <= mp.ultimo_topo[1]:
            ctxq = "REVERSAO (3o sinal: corte total + entrada)" if dirn[i-1]<0 or exa_dir<0 else "continuacao da alta"
            ev.append((i,"rompeu_ultimo_topo",f"fechou {c[i]:.2f} > ultimo topo {mp.ultimo_topo[1]:.2f} — {ctxq}"))
    return ev

def caixa_pos_exaustao(andar: "Andar", i_exa: int, dir_exa: int, PC: dict = None) -> Optional[Caixa]:
    """(8b) REGRA B DO DONO: exaustao identificada -> caixa nasce na barra SEGUINTE, com o extremo
    da barra de exaustao como fronteira ('olhar pra tras'). Cresce/termina pelas mesmas leis do item 5-7."""
    PC = {**PARAMS_CAIXA, **(PC or {})}
    df=andar.df; h=df.high.values; l=df.low.values; c=df.close.values; ts=df.ts.values; a=df.atr14.values
    m=len(df); i0=i_exa
    if i0+1>=m: return None
    teto=float(h[i0]); piso=float(l[i0]); j=i0+1; fim="fim_dados"; voltas=0; sacud=0
    atr_ref=_atr_ref_altura(df, {a2.nome:a2 for a2 in []} or None, andar.nome)  # sem ref: altura em ATR do andar
    while j<m:
        if c[j]>teto or c[j]<piso:
            cima=c[j]>teto
            conf = j+1<m and ((cima and h[j+1]>h[j]) or ((not cima) and l[j+1]<l[j]))
            if not conf:
                voltas+=1; teto=max(teto,float(h[j])); piso=min(piso,float(l[j]))
                if j+1<m: teto=max(teto,float(h[j+1])); piso=min(piso,float(l[j+1]))
                j+=2; continue
            fr=teto if cima else piso; atr_j=a[j] if np.isfinite(a[j]) and a[j]>0 else 0.0
            k=j+2; res="sem_avanco"
            while k<m and k<=j+1+PC["N_SUST"]:
                if (cima and c[k]>=fr+PC["X_SUST"]*atr_j) or ((not cima) and c[k]<=fr-PC["X_SUST"]*atr_j): res="sustentado"; break
                if piso<=c[k]<=teto: res="voltou"; break
                k+=1
            if res=="voltou":
                voltas+=1
                if k+1<m and ((cima and c[k+1]<c[k]) or ((not cima) and c[k+1]>c[k])): sacud+=1
                for q in range(j,min(k,m-1)+1): teto=max(teto,float(h[q])); piso=min(piso,float(l[q]))
                j=k+1; continue
            fim=("rompida_confirmada_cima" if cima else "rompida_confirmada_baixo")+("" if res=="sustentado" else "_sem_avanco")
            break
        if h[j]>teto: teto=float(h[j])
        if l[j]<piso: piso=float(l[j])
        j+=1
    ult = j-1 if fim!="fim_dados" else m-1
    alt=teto-piso; aa=a[i0] if np.isfinite(a[i0]) and a[i0]>0 else np.nan
    return Caixa(andar.nome, i0, ts[i0], ult, ts[ult], piso, teto, True, True, alt, None,
                 alt/aa if np.isfinite(aa) else np.nan,
                 "pos_exaustao", ult-i0+1, (ult-i0+1)>PC["MADURO"], voltas, sacud, fim,
                 (0,0,0,0), 0.0)



# ===========================================================================
# ITEM 16 — REPLICACAO ENTRE ANDARES (doc §6; Feito00090)
#   "O Ciclo tem que ser completo na visao por inteiro, na conversa entre os
#    andares dos TF" (dono, 28/ago). Duas entregas:
#   (a) CONTEXTO TARDIO PELO CICLO: a perna longa nao precisa caber no andar —
#       ela e contada pelos andares de BAIXO e sobe confirmada. Uma perna de 4
#       dias no D1 sao ~24 barras de H4 e ~400 de M15: o L=20 unico (§11) so
#       funciona porque quem acumula as barras e o Ciclo, nao o andar sozinho.
#   (b) REGISTRO DE REPLICACAO: em quais andares a MESMA estrutura (exaustao ->
#       caixa -> rompimento) se repetiu na mesma janela de tempo. Insumo da R3 e
#       numero que o v5 mede (quantos andares separam respiro de virada).
# ===========================================================================
ESCADA_ANDARES = ["M1","M5","M10","M15","M30","H1","H4","Daily","W1","MN1"]

def contexto_tardio_replicado(lt: "LeitorMultiTF", nome: str, P: dict = None):
    """(a) Vetor booleano por barra do andar `nome`: os andares ABAIXO ja
    confirmam perna tardia (>= L_TARDIO) ou afastamento (>= D_TARDIO) na MESMA
    direcao da perna deste andar, no instante daquela barra.
    Sem olhar o futuro: usa a ultima barra FECHADA do andar de baixo."""
    P = {**PARAMS_ESCADA, **(P or {})}
    if nome not in lt.andares: return None
    A = lt.andares[nome]; df = A.df; m = len(df)
    if nome not in ESCADA_ANDARES: return None
    abaixo = [x for x in ESCADA_ANDARES[:ESCADA_ANDARES.index(nome)] if x in lt.andares]
    if not abaixo: return None
    fora = np.zeros(m, dtype=bool)
    ts_a = df.ts.values; dir_a = df.perna_dir.values
    for nb in abaixo:
        B = lt.andares[nb]; ts_b = B.df.ts.values
        L_b = B.df.perna_L.values; d_b = B.df.perna_dir.values; D_b = B.df.afast_D.values
        # para cada barra de A, a ultima barra FECHADA de B (searchsorted = zero lookahead)
        idx = np.searchsorted(ts_b, ts_a, side="right") - 1
        ok = idx >= 0
        j = np.where(ok, idx, 0)
        tardio_b = (L_b[j] >= P["L_TARDIO"]) | (np.abs(np.nan_to_num(D_b[j])) >= P["D_TARDIO"])
        mesma_dir = (d_b[j] != 0) & (d_b[j] == dir_a)
        fora |= (ok & tardio_b & mesma_dir)
    return fora

def eventos_escada_ciclo(lt: "LeitorMultiTF", nome: str, P: dict = None):
    """eventos_escada do andar JA com o contexto tardio replicado do Ciclo."""
    return eventos_escada(lt.andares[nome], P=P,
                          tardio_ext=contexto_tardio_replicado(lt, nome, P))

# --- (b) registro de replicacao ---------------------------------------------
_REPLICA_GRUPO = {
    "exaustao_identificada": "exaustao",
    "alerta_empilhado_3":    "exaustao",
    "topo_barra_rompida":    "reversao",
    "fundo_barra_rompido":   "reversao",
    "rompeu_ultimo_topo":    "rompimento",
    "rompeu_ultimo_fundo":   "rompimento",
}

def replicacao(lt: "LeitorMultiTF", ts, janela_barras_ref: int = 3,
               andar_ref: str = "M15", ev_por_andar: dict = None) -> dict:
    """Em quais andares cada estrutura apareceu na janela que termina em `ts`.
    A janela e medida em barras do andar de referencia (padrao 3 barras do 15m).
    Devolve {grupo: {"andares":[...], "n":k, "eventos":[(andar, ev, quando)]}}."""
    ts = pd.Timestamp(ts)
    ref = lt.andares.get(andar_ref)
    if ref is None: return {}
    i_ref = _idx_ts(ref.df, ts)
    if i_ref < 0: return {}
    t_ini = pd.Timestamp(ref.df.ts.iloc[max(0, i_ref - janela_barras_ref + 1)])
    out = {}
    for nm in ESCADA_ANDARES:
        if nm not in lt.andares: continue
        A = lt.andares[nm]
        evs = (ev_por_andar or {}).get(nm) or eventos_escada_ciclo(lt, nm)
        for i, e, det in evs:
            t = pd.Timestamp(A.df.ts.iloc[i])
            if t < t_ini or t > ts: continue
            g = _REPLICA_GRUPO.get(e)
            if not g: continue
            d = out.setdefault(g, {"andares": [], "eventos": []})
            if nm not in d["andares"]: d["andares"].append(nm)
            d["eventos"].append((nm, e, f"{t:%d/%m %H:%M}"))
    for g, d in out.items():
        d["andares"].sort(key=lambda x: ESCADA_ANDARES.index(x))
        d["n"] = len(d["andares"])
    return out




# ===========================================================================
# LEI DA CONTINUIDADE NA ENTRADA (Feito00094 — palavra do dono, 28/ago)
#   "nao e so tocar acima do rompimento: tem que dar CONTINUIDADE no movimento.
#    Se nao der continuidade nao abre, espera a continuidade. Se nao confirmar,
#    ele poderia ter invertido — nesse caso nao poderia ter aberto operacao."
#   Corrige a leitura errada do D5 que eu tinha feito (toque puro). O decreto
#   sempre disse "a maxima do candle-gatilho rompida NA CONTINUIDADE e a entrada".
#
#   REGRA (mesma regua da forma 2 do sem_continuidade §5.5.1, espelhada):
#   - o toque ARMA, nao abre;
#   - a barra que fura o nivel tem de FECHAR sustentando a direcao (fechamento
#     alem do nivel do gatilho e a favor do corpo). Furou e fechou aquem/contra
#     (doji, corpo contrario) = SEM CONTINUIDADE -> NAO ABRE;
#   - o gatilho SEGUE ARMADO esperando a continuidade, que pode vir na barra
#     seguinte (foi o caso da 154 -> 155);
#   - o gatilho vive enquanto o Ciclo confirmar e morre pela decisao do 15m
#     (Feito00088 item 7) — nunca por contagem de barras.
# ===========================================================================
def entrada_com_continuidade(df, i_gatilho: int, nivel: float, lado: int,
                             i_atual: int) -> Tuple[bool, str]:
    """A barra i_atual abre a operacao? Devolve (abre, motivo).
    lado +1 compra (nivel = maxima do candle-gatilho) / -1 venda (minima)."""
    if i_atual <= i_gatilho: return False, "ainda no candle-gatilho"
    h = df.high.values; l = df.low.values; o = df.open.values; c = df.close.values
    tocou = (h[i_atual] >= nivel) if lado > 0 else (l[i_atual] <= nivel)
    if not tocou: return False, "nivel nao tocado — gatilho segue armado"
    # CONTINUIDADE: fechou alem do nivel E com corpo a favor
    if lado > 0:
        cont = c[i_atual] > nivel and c[i_atual] > o[i_atual]
    else:
        cont = c[i_atual] < nivel and c[i_atual] < o[i_atual]
    if cont:
        return True, f"tocou {nivel:.2f} e DEU CONTINUIDADE (fechou {c[i_atual]:.2f} sustentando)"
    return False, (f"furou {nivel:.2f} e NAO deu continuidade (fechou {c[i_atual]:.2f}) — "
                   f"NAO ABRE, gatilho segue armado esperando a continuidade")


# ===========================================================================
# ITENS 11, 12, 13 — SACUDIDA, GAP E CAIXA DENTRO DE CAIXA (§5.7, §5.8, §5.9)
# ===========================================================================
PARAMS_BLIND = dict(
    # B1 detector de choque (§7) — [REF]/[TRAD] do doc, a medir no v5
    B1_S_SPREAD=3.0,      # spread > S x mediana da sessao
    B1_V_RANGE=3.0,       # range > V x ATR14 do 1m
    B1_N_VOLTA=5,         # N barras de 1m dentro da faixa para voltar a ler
    # B2 calendario (§7) — [REF] prop firms; sem fonte de dados = degrada honesto
    B2_ANTES_MIN=10,      # para de abrir 10 min ANTES
    B2_DEPOIS_MIN=30,     # volta 30 min DEPOIS
    # B3 tempo-sem-progresso (§7) — [TRAD] 6 barras de 5m
    B3_N_BARRAS=6, B3_ANDAR="M5",
    # B5 fim de semana (§7) — 30 min antes do encerramento de sexta (valor do dono)
    B5_MIN_ANTES=30,
)

def eventos_sacudida(andar: "Andar", caixas: List["Caixa"] = None) -> List[Tuple[int,str,str]]:
    """ITEM 11 (§5.7): sacudida = pavio ALEM da fronteira + FECHAMENTO de volta
    dentro + estrutura intacta. Evento proprio da ficha (antes so existia como
    contador interno da caixa). Nao e acidente: e SETUP (liquidez coletada)."""
    df = andar.df; h=df.high.values; l=df.low.values; c=df.close.values
    caixas = caixas if caixas is not None else detectar_caixas(andar)
    ev=[]
    for cx in caixas:
        for i in range(cx.i_ini, min(cx.i_fim+1, len(df))):
            if h[i] > cx.teto and c[i] <= cx.teto:
                ev.append((i,"sacudida", f"pavio {h[i]:.2f} alem do teto {cx.teto:.2f}, fechou dentro "
                                          f"({c[i]:.2f}) — liquidez coletada no topo (SETUP, §5.7)"))
            if l[i] < cx.piso and c[i] >= cx.piso:
                ev.append((i,"sacudida", f"pavio {l[i]:.2f} alem do piso {cx.piso:.2f}, fechou dentro "
                                          f"({c[i]:.2f}) — liquidez coletada no fundo (SETUP, §5.7)"))
    # pivo varrido e devolvido (sacudida fora de caixa)
    for i in range(2, len(df)):
        mp = andar.mapas[i]
        if mp.ultimo_topo and h[i] > mp.ultimo_topo[1] and c[i] <= mp.ultimo_topo[1]:
            ev.append((i,"sacudida", f"varreu o ultimo topo {mp.ultimo_topo[1]:.2f} e fechou de volta — estrutura intacta"))
        if mp.ultimo_fundo and l[i] < mp.ultimo_fundo[1] and c[i] >= mp.ultimo_fundo[1]:
            ev.append((i,"sacudida", f"varreu o ultimo fundo {mp.ultimo_fundo[1]:.2f} e fechou de volta — estrutura intacta"))
    ev.sort(key=lambda x: x[0])
    return ev

def stop_por_sacudida(andar: "Andar", i: int, nivel_stop: float, lado: int) -> Optional[str]:
    """ITEM 11 (§5.7 ponto 2): o stop do servidor disparou no pavio E a barra
    fechou de volta dentro. Depende do nivel de stop, que vem do Bloco 2 —
    por isso e funcao consultada, nao evento automatico. Reentrada NUNCA por
    'o stop errou': so por evento novo confirmado (ponto 3)."""
    df=andar.df; h=df.high.values; l=df.low.values; c=df.close.values
    if lado > 0 and l[i] <= nivel_stop and c[i] > nivel_stop:
        return (f"stop_por_sacudida: minima {l[i]:.2f} varreu o stop {nivel_stop:.2f} e a barra fechou "
                f"em {c[i]:.2f} — reentrada SO com evento novo confirmado (§5.7.3)")
    if lado < 0 and h[i] >= nivel_stop and c[i] < nivel_stop:
        return (f"stop_por_sacudida: maxima {h[i]:.2f} varreu o stop {nivel_stop:.2f} e a barra fechou "
                f"em {c[i]:.2f} — reentrada SO com evento novo confirmado (§5.7.3)")
    return None

def eventos_gap(andar: "Andar") -> List[Tuple[int,str,str]]:
    """ITEM 12 (§5.8): gap = rompimento que nao passou pelos precos intermediarios.
    Ninguem classifica na hora — a barra SEGUINTE diz (Lei de Confirmacao).
    Pivo saltado por gap = rompimento PENDENTE; gap reversal = falhou, pivo
    continua valido e vira ima de preenchimento. Carimbo rompimento_por_gap."""
    df=andar.df; o=df.open.values; h=df.high.values; l=df.low.values; c=df.close.values
    ev=[]
    for i in range(2, len(df)-1):
        gap_cima  = o[i] > h[i-1]
        gap_baixo = o[i] < l[i-1]
        if not (gap_cima or gap_baixo): continue
        mp = andar.mapas[i]
        lado = +1 if gap_cima else -1
        alvo = (mp.ultimo_topo[1] if mp.ultimo_topo else None) if lado>0 else (mp.ultimo_fundo[1] if mp.ultimo_fundo else None)
        saltou = alvo is not None and ((lado>0 and o[i] > alvo and h[i-1] < alvo) or
                                       (lado<0 and o[i] < alvo and l[i-1] > alvo))
        base = f"gap {'de alta' if lado>0 else 'de baixa'}: abriu {o[i]:.2f} alem do range da anterior"
        if saltou:
            ev.append((i,"rompimento_pendente_por_gap",
                       f"{base}; pivo {alvo:.2f} SALTADO — pendente ate a barra seguinte quebrar "
                       f"o extremo desta ({(h[i] if lado>0 else l[i]):.2f}), §5.8"))
            # a barra seguinte diz
            j=i+1
            if (lado>0 and h[j] > h[i]) or (lado<0 and l[j] < l[i]):
                ev.append((j,"rompimento_confirmado_por_gap",
                           f"barra seguinte quebrou {(h[i] if lado>0 else l[i]):.2f} — pivo {alvo:.2f} "
                           f"ROMPIDO (carimbo rompimento_por_gap)"))
            elif (lado>0 and c[j] < o[i]) or (lado<0 and c[j] > o[i]):
                ev.append((j,"gap_reversal",
                           f"barra seguinte voltou pra dentro do gap — rompimento FALHOU, pivo {alvo:.2f} "
                           f"continua valido e vira ima de preenchimento (§5.8)"))
        else:
            ev.append((i,"gap", base + " — 1a barra pos-gap tratada como barra NORMAL com papel de candle que rompeu"))
    return ev

def caixa_dentro_de_caixa(lt: "LeitorMultiTF", ts, andar_menor: str, andar_maior: str = "M15") -> Optional[str]:
    """ITEM 13 (§5.9): andar MAIOR manda no ESTADO, andar MENOR gera o EVENTO.
    O fechamento do andar maior e o DESEMPATE: fechou FORA da caixa maior =
    rompimento replicado nos dois andares; fechou DENTRO = movimento interno da
    caixa maior -> o bloco entrega COMPRESSAO (estado) com o evento do menor
    registrado como ABSORVIDO."""
    if andar_menor not in lt.andares or andar_maior not in lt.andares: return None
    Am, AM = lt.andares[andar_menor], lt.andares[andar_maior]
    im, iM = _idx_ts(Am.df, ts), _idx_ts(AM.df, ts)
    if im < 0 or iM < 0: return None
    cx_m = [c for c in detectar_caixas(Am, lt_andares=lt.andares) if c.i_fim == im and c.fim.startswith("rompida_confirmada")]
    if not cx_m: return None
    cx_M = [c for c in detectar_caixas(AM, lt_andares=lt.andares) if c.i_ini <= iM <= c.i_fim]
    if not cx_M:
        return (f"caixa do {andar_menor} rompida e o {andar_maior} nao esta em caixa — "
                f"rompimento vale (sem caixa maior para absorver)")
    cM = cx_M[-1]; fech = float(AM.df.close.iloc[iM])
    if fech > cM.teto or fech < cM.piso:
        return (f"ROMPIMENTO REPLICADO: caixa do {andar_menor} rompida E o {andar_maior} fechou "
                f"{fech:.2f} FORA da caixa [{cM.piso:.2f},{cM.teto:.2f}] — o bloco entrega rompimento (§5.9)")
    return (f"COMPRESSAO (estado): o {andar_maior} fechou {fech:.2f} DENTRO da caixa "
            f"[{cM.piso:.2f},{cM.teto:.2f}] — o evento do {andar_menor} fica registrado como ABSORVIDO (§5.9)")

# ===========================================================================
# BLINDAGENS DE CAPITAL — B1, B2, B3, B5 (§7; itens 19-22 da §12)
#   "Ligadas de fabrica". Feito00041: protecao nunca espera numero.
# ===========================================================================
def b1_choque(lt: "LeitorMultiTF", ts, P: dict = None) -> dict:
    """B1 (§7): duas reguas na barra de 1m — spread > S x mediana da sessao OU
    range > V x ATR14 do 1m -> estado mercado_anormal: nenhuma entrada, nenhum
    corte POR LEITURA (a barra nao e estrutura); o stop no servidor segue.
    O Ciclo volta a ler apos N barras com volatilidade dentro da faixa."""
    P = {**PARAMS_BLIND, **(P or {})}
    if "M1" not in lt.andares: return {"ativa": False, "motivo": "sem M1 — B1 nao pode ler (declarado)"}
    df = lt.andares["M1"].df; i = _idx_ts(df, ts)
    if i < 20: return {"ativa": False, "motivo": "barras insuficientes"}
    sp = df["spread"].values if "spread" in df.columns else None
    rng = (df.high.values - df.low.values); atr = df.atr14.values
    anormal_i = None
    for j in range(i, max(0, i - P["B1_N_VOLTA"]) - 1, -1):
        cho = []
        if sp is not None and np.isfinite(sp[j]):
            med = np.nanmedian(sp[max(0, j-240):j+1])       # mediana da sessao (~4h de 1m)
            if med > 0 and sp[j] > P["B1_S_SPREAD"] * med:
                cho.append(f"spread {sp[j]:.0f} > {P['B1_S_SPREAD']}x mediana {med:.0f}")
        if np.isfinite(atr[j]) and atr[j] > 0 and rng[j] > P["B1_V_RANGE"] * atr[j]:
            cho.append(f"range {rng[j]:.2f} > {P['B1_V_RANGE']}x ATR14 {atr[j]:.2f}")
        if cho:
            anormal_i = j; motivo = "; ".join(cho); break
    if anormal_i is None:
        return {"ativa": False, "motivo": "mercado dentro da faixa"}
    faltam = P["B1_N_VOLTA"] - (i - anormal_i)
    return {"ativa": faltam > 0, "motivo": f"MERCADO ANORMAL em {pd.Timestamp(df.ts.iloc[anormal_i]):%d/%m %H:%M} ({motivo})"
                                           f" — sem entrada e sem corte por leitura por mais {max(faltam,0)} barra(s) de 1m; stop no servidor segue"}

def b2_calendario(ts, eventos_calendario: List[dict] = None, P: dict = None) -> dict:
    """B2 (§7): para de abrir ANTES da noticia de alto impacto, retorna DEPOIS.
    Consome o modulo de calendario da plataforma. SEM fonte de dados o modulo
    DEGRADA COM HONESTIDADE (declara que nao ha calendario), nunca finge."""
    P = {**PARAMS_BLIND, **(P or {})}
    if not eventos_calendario:
        return {"ativa": False, "sem_fonte": True,
                "motivo": "sem calendario carregado — B2 declarado INATIVO (defesa fica com B1 + stop no servidor, §10.4)"}
    ts = pd.Timestamp(ts)
    for ev in eventos_calendario:
        t = pd.Timestamp(ev["quando"])
        if (t - pd.Timedelta(minutes=P["B2_ANTES_MIN"])) <= ts <= (t + pd.Timedelta(minutes=P["B2_DEPOIS_MIN"])):
            return {"ativa": True, "sem_fonte": False,
                    "motivo": f"janela de noticia de alto impacto ({ev.get('nome','evento')} {t:%d/%m %H:%M}): "
                              f"-{P['B2_ANTES_MIN']}min / +{P['B2_DEPOIS_MIN']}min — nao abre"}
    return {"ativa": False, "sem_fonte": False, "motivo": "fora de janela de noticia"}

def b3_tempo_sem_progresso(lt: "LeitorMultiTF", ts, lado_posicao: int, P: dict = None) -> dict:
    """B3 (§7): posicao aberta + compressao/lateral por N barras SEM PROGRESSO
    = a tese expirou -> corte de protecao. Nao e relogio: e ausencia de avanco
    (a distincao que separa o B3 do time stop cego)."""
    P = {**PARAMS_BLIND, **(P or {})}
    nm = P["B3_ANDAR"]
    if lado_posicao == 0 or nm not in lt.andares:
        return {"corta": False, "motivo": "sem posicao ou sem andar"}
    A = lt.andares[nm]; i = _idx_ts(A.df, ts); N = P["B3_N_BARRAS"]
    if i < N: return {"corta": False, "motivo": "barras insuficientes"}
    # cache (30/ago): recalcular as caixas do M5 a cada barra tornava o B3
    # ~100x mais caro que o resto da simulacao junta; mesmas caixas, calculadas 1x
    if not hasattr(lt, "_b3_cx"): lt._b3_cx = {}
    if nm not in lt._b3_cx: lt._b3_cx[nm] = detectar_caixas(A, lt_andares=lt.andares)
    cxs = [c for c in lt._b3_cx[nm] if c.i_ini <= i <= c.i_fim]
    if not cxs: return {"corta": False, "motivo": "sem compressao/lateral no andar do B3"}
    jan = A.df.iloc[i-N+1:i+1]
    avanco = float(jan.close.iloc[-1] - jan.close.iloc[0])
    atr = float(A.df.atr14.iloc[i])
    progresso_favor = avanco * lado_posicao
    if np.isfinite(atr) and atr > 0 and progresso_favor <= 0:
        return {"corta": True,
                "motivo": (f"B3: posicao {'comprada' if lado_posicao>0 else 'vendida'} dentro de compressao "
                           f"[{cxs[-1].piso:.2f},{cxs[-1].teto:.2f}] por {N} barras de {nm} sem progresso "
                           f"(avanco a favor {progresso_favor:+.2f} = {progresso_favor/atr:+.2f} ATR) — tese expirou")}
    return {"corta": False, "motivo": f"B3: ha progresso a favor ({progresso_favor:+.2f})"}

def b5_fim_de_semana(lt: "LeitorMultiTF", ts, ativo: str = "", P: dict = None) -> dict:
    """B5 (§7): nos ativos que podem abrir com gap (XAU, indices, forex) fecha
    TODAS as posicoes 30 minutos antes do encerramento de sexta (valor do dono)
    e nao abre nova ate a reabertura. Cripto 24/7 fora.
    O horario de encerramento vem dos DADOS (ultima barra da sexta) enquanto o
    modulo de calendario/sessao nao existe — declarado."""
    P = {**PARAMS_BLIND, **(P or {})}
    if any(k in ativo.upper() for k in ("BTC","ETH","XRP","SOL","LTC","DOGE")):
        return {"ativa": False, "motivo": "cripto 24/7 — B5 nao se aplica (§7)"}
    ts = pd.Timestamp(ts)
    nm = "M15" if "M15" in lt.andares else next(iter(lt.andares))
    df = lt.andares[nm].df
    if ts.weekday() != 4:  # 4 = sexta
        return {"ativa": False, "motivo": "nao e sexta-feira"}
    dia = df[(df.ts >= ts.normalize()) & (df.ts < ts.normalize() + pd.Timedelta(days=1))]
    if dia.empty: return {"ativa": False, "motivo": "sem barras da sexta nos dados"}
    fecha = pd.Timestamp(dia.ts.iloc[-1])
    limite = fecha - pd.Timedelta(minutes=P["B5_MIN_ANTES"])
    if ts >= limite:
        return {"ativa": True,
                "motivo": (f"B5: encerramento de sexta {fecha:%H:%M} (dos dados) — a partir de {limite:%H:%M} "
                           f"fecha TODAS as posicoes e nao abre nova ate a reabertura")}
    return {"ativa": False, "motivo": f"sexta, mas ainda antes de {limite:%H:%M}"}

def blindagens(lt: "LeitorMultiTF", ts, ativo: str = "", lado_posicao: int = 0,
               eventos_calendario: List[dict] = None) -> dict:
    """Estado das quatro blindagens nesta barra (item 10 da ficha §9)."""
    return {"B1": b1_choque(lt, ts),
            "B2": b2_calendario(ts, eventos_calendario),
            "B3": b3_tempo_sem_progresso(lt, ts, lado_posicao),
            "B5": b5_fim_de_semana(lt, ts, ativo)}

# ===========================================================================
# ITEM 25 — TELEMETRIA / LEARNING MACHINE (§9 item 11)
#   "Tudo acima, mais RECUSAS com motivo. Auditavel celula por celula."
# ===========================================================================
class Telemetria:
    """Coletor da Learning Machine: registra eventos, comandos e RECUSAS com
    motivo, prontos para subir. Nada de resumo — linha por linha, auditavel."""
    def __init__(self, ativo: str):
        self.ativo = ativo; self.linhas: List[dict] = []
    def registrar(self, ts, tipo: str, andar: str = "", evento: str = "",
                  detalhe: str = "", lado: int = 0, motivo: str = ""):
        self.linhas.append(dict(ativo=self.ativo, ts=str(pd.Timestamp(ts)), tipo=tipo,
                                andar=andar, evento=evento, detalhe=detalhe,
                                lado=lado, motivo=motivo,
                                motor=MOTOR_VERSAO, build=BUILD_TAG, doc=DOC_BLOCO1))
    def recusa(self, ts, motivo: str, andar: str = "", detalhe: str = ""):
        self.registrar(ts, "recusa", andar=andar, detalhe=detalhe, motivo=motivo)
    def comando(self, ts, lado: int, motivo: str, andar: str = ""):
        self.registrar(ts, "comando", andar=andar, lado=lado, motivo=motivo)
    def to_csv(self, caminho: str = "telemetria_bloco1.csv") -> str:
        if not self.linhas: return "telemetria vazia"
        pd.DataFrame(self.linhas).to_csv(caminho, index=False, encoding="utf-8")
        return f"{len(self.linhas)} linhas -> {caminho}"

# ===========================================================================
# CHECKLIST DO BLOCO 1 RODANDO EM CADA ANDAR (§3 + §6; Feito00092)
#   Palavra do dono (28/ago): "o Bloco 1 tem que ser rodado em TODOS os andares,
#   respondendo tudo que ja desenhamos". Nao e evento subindo entre andares:
#   e o CHECKLIST INTEIRO respondido pelas barras do PROPRIO andar.
#   A conversa entre andares (o Ciclo) e a pergunta se repetindo degrau a degrau:
#   M1 -> M5: o que esta acontecendo nessas barras, qual a direcao?
#   M5 -> M10: o andar de cima CONFIRMA o comportamento identificado embaixo?
#              nao confirmando, a pergunta se REFAZ nesse andar.
#   M10 -> M15: confirma o que foi identificado -> no 15m sai a DECISAO.
#   E segue na sequencia pelos andares superiores.
# ===========================================================================
@dataclass
class RespostaChecklist:
    andar: str
    i: int
    ts: object
    sentido: int                  # pergunta-mae: +1 alta / -1 baixa / 0 sem sentido
    itens: dict                   # numero do item (§3) -> (resposta, detalhe)
    confirma_abaixo: Optional[bool] = None   # confirmou o andar de baixo?
    detalhe_conf: str = ""

def checklist_andar(lt: "LeitorMultiTF", nome: str, ts, ev_cache: dict = None,
                    cx_cache: dict = None, lado_posicao: int = 0) -> Optional[RespostaChecklist]:
    """Responde o checklist §3 INTEIRO com as barras do andar `nome`, na barra
    fechada <= ts. Nada de opiniao: cada item sai das reguas ja construidas."""
    if nome not in lt.andares: return None
    A = lt.andares[nome]; df = A.df
    i = _idx_ts(df, ts)
    if i < 2: return None
    r = df.iloc[i]; mp = A.mapas[i]
    ev_cache = ev_cache if ev_cache is not None else {}
    cx_cache = cx_cache if cx_cache is not None else {}
    if nome not in ev_cache: ev_cache[nome] = eventos_escada_ciclo(lt, nome)
    if nome not in cx_cache: cx_cache[nome] = detectar_caixas(A, lt_andares=lt.andares)
    evb = [(e, det) for j, e, det in ev_cache[nome] if j == i]
    nomes_ev = {e for e, _ in evb}
    it = {}
    # PERGUNTA-MAE: qual o SENTIDO do que esta se formando nesse espaco de barras?
    sent = int(r.perna_dir) if r.perna_L >= 2 else int(r.estado_canal)
    it["mae"] = (sent, f"perna L={int(r.perna_L)}{'U' if r.perna_dir>0 else 'D' if r.perna_dir<0 else 'L'} "
                       f"canal={int(r.estado_canal):+d} D={r.afast_D:+.1f}ATR")
    # 1) a favor da referencia do Ciclo 2 (amplitude, nunca veto — Feito00088)
    ref = 0; det_ref = []
    for nm2 in ORDEM_C2:
        if nm2 not in lt.andares or nm2 == nome: continue
        d2 = lt.andares[nm2].df; j = _idx_ts(d2, ts)
        if j < 0: continue
        e2 = int(d2.estado_canal.iloc[j]); ref += e2
        det_ref.append(f"{nm2}{e2:+d}")
    it[1] = (("a favor" if ref*sent > 0 else "contra" if ref*sent < 0 else "neutro"),
             "amplitude C2: " + " ".join(det_ref))
    # 2) e 3) a favor / contra a NOSSA ENTRADA
    it[2] = ((lado_posicao != 0 and sent == lado_posicao), f"posicao={lado_posicao:+d}")
    it[3] = ((lado_posicao != 0 and sent == -lado_posicao), f"posicao={lado_posicao:+d}")
    # 4) esta formando uma REVERSAO? (escada dos 3 sinais, §5.5/§5.5.1)
    deg = 0; det4 = []
    if "sem_continuidade" in nomes_ev: deg = max(deg,1); det4.append("sem_continuidade")
    if {"pivo_candidato_topo","pivo_candidato_fundo"} & nomes_ev: deg = max(deg,1); det4.append("pivo candidato")
    if "alerta_empilhado_3" in nomes_ev: deg = max(deg,2); det4.append("3 alertas")
    if {"topo_barra_rompida","fundo_barra_rompido"} & nomes_ev: deg = max(deg,2); det4.append("2o sinal")
    if any(e.startswith("rompeu_ultimo") and "REVERSAO" in d for e,d in evb): deg = 3; det4.append("3o sinal")
    it[4] = (deg > 0, f"degrau {deg}/3" + (" — " + ", ".join(det4) if det4 else ""))
    # 5) esta QUEBRANDO A ESTRUTURA? (pivo do proprio andar rompido por fechamento)
    q5 = any(e.startswith("rompeu_ultimo") for e in nomes_ev)
    it[5] = (q5, [d for e,d in evb if e.startswith("rompeu_ultimo")][0] if q5 else "estrutura intacta")
    # 6) TOPO em ponto de EXAUSTAO, numa resistencia ou suporte?
    exa = [d for e,d in evb if e == "exaustao_identificada"]
    perto = ""
    if mp.ultimo_topo and abs(r.close-mp.ultimo_topo[1]) <= 0.3*r.atr14: perto = "no ultimo topo (resistencia)"
    if mp.ultimo_fundo and abs(r.close-mp.ultimo_fundo[1]) <= 0.3*r.atr14: perto = "no ultimo fundo (suporte)"
    it[6] = (bool(exa), (exa[0] if exa else "sem exaustao") + (f" · {perto}" if perto else ""))
    # 7) TOPOS E FUNDOS identificados? (mapa de pivos N=2 do andar)
    it[7] = (bool(mp.ultimo_topo or mp.ultimo_fundo),
             f"topo={mp.ultimo_topo[1]:.2f}" if mp.ultimo_topo else "topo=—",)
    it[7] = (it[7][0], (f"topo={mp.ultimo_topo[1]:.2f} " if mp.ultimo_topo else "topo=— ") +
                       (f"fundo={mp.ultimo_fundo[1]:.2f} " if mp.ultimo_fundo else "fundo=— ") +
                       f"seqT={mp.seq_topos} seqF={mp.seq_fundos}")
    # 8) COMPRESSAO se formando? (caixa ativa nesta barra, §5.1)
    cxa = [c for c in cx_cache[nome] if c.i_ini <= i <= c.i_fim]
    it[8] = (bool(cxa), (f"CAIXA [{cxa[-1].piso:.2f},{cxa[-1].teto:.2f}] n={cxa[-1].n_barras}"
                         f"{' MADURA' if cxa[-1].range_maduro else ''}") if cxa else "sem compressao")
    # 9) ROMPENDO resistencia / topo / fundo de compressao? (§5.2 Lei de Confirmacao)
    romp = [c for c in cx_cache[nome] if c.i_fim == i and c.fim.startswith("rompida_confirmada")]
    it[9] = (bool(romp), (f"caixa [{romp[0].piso:.2f},{romp[0].teto:.2f}] {romp[0].fim}") if romp else "sem rompimento confirmado")
    # 10) TOPOS MAIS BAIXOS rompendo o ULTIMO FUNDO? (assinatura completa, regua de entrada)
    assin = (mp.seq_topos == "desc" and any(e == "rompeu_ultimo_fundo" for e in nomes_ev)) or \
            (mp.seq_fundos == "asc" and any(e == "rompeu_ultimo_topo" for e in nomes_ev))
    it[10] = (assin, "assinatura completa" if assin else f"seqT={mp.seq_topos} seqF={mp.seq_fundos}")
    # 11) EXAUSTAO identificada (contexto tardio + gatilho + pivo)
    it[11] = (bool(exa), exa[0] if exa else "nao")
    # 13) DECRETO: posicao aberta + reversao identificada = FECHAR
    it[13] = ((lado_posicao != 0 and deg >= 2 and sent == -lado_posicao),
              "CORTE (reversao identificada contra a posicao)" if (lado_posicao != 0 and deg >= 2 and sent == -lado_posicao) else "sem corte")
    return RespostaChecklist(nome, i, pd.Timestamp(r.ts), sent, it)

def ciclo_checklist(lt: "LeitorMultiTF", ts, andares: List[str] = None,
                    lado_posicao: int = 0) -> List[RespostaChecklist]:
    """O CICLO: o checklist rodando em CADA andar, subindo, com o andar de cima
    respondendo se CONFIRMA o comportamento identificado no de baixo. Nao
    confirmando, a pergunta se refaz nesse andar (o sentido dele passa a valer)."""
    andares = andares or [a for a in ESCADA_ANDARES if a in lt.andares]
    ev_cache = {}; cx_cache = {}
    out = []; sent_abaixo = None; andar_abaixo = None
    for nm in andares:
        r = checklist_andar(lt, nm, ts, ev_cache, cx_cache, lado_posicao)
        if r is None: continue
        if sent_abaixo is None:
            r.confirma_abaixo = None
            r.detalhe_conf = "base da leitura (nao ha andar abaixo)"
        elif sent_abaixo == 0:
            r.confirma_abaixo = None
            r.detalhe_conf = f"{andar_abaixo} sem sentido definido — pergunta refeita aqui"
        elif r.sentido == sent_abaixo:
            r.confirma_abaixo = True
            r.detalhe_conf = f"CONFIRMA o {andar_abaixo}"
        elif r.sentido == 0:
            r.confirma_abaixo = False
            r.detalhe_conf = f"nao confirma o {andar_abaixo} (sem sentido proprio) — pergunta refeita"
        else:
            r.confirma_abaixo = False
            r.detalhe_conf = f"NAO confirma o {andar_abaixo} (le {'alta' if r.sentido>0 else 'baixa'}) — pergunta refeita"
        out.append(r)
        sent_abaixo = r.sentido; andar_abaixo = nm
    return out

def estado_unico(respostas: List[RespostaChecklist]) -> str:
    """§6: sentido + profundidade da confirmacao ('ALTA, confirmada do 1m ate o 30m')."""
    if not respostas: return "sem leitura"
    base = respostas[0]
    if base.sentido == 0: return "SEM SENTIDO na base da leitura"
    topo = base.andar
    for r in respostas[1:]:
        if r.sentido == base.sentido: topo = r.andar
        else: break
    return (f"{'ALTA' if base.sentido>0 else 'BAIXA'}, confirmada do {base.andar} ate o {topo}"
            + ("" if topo != base.andar else " (so na base)"))


# ===========================================================================
# DECISAO DE CORTE — A PARTIR DO M15, SEGUIDO DE CONFIRMACAO (Feito00093)
#   Palavra do dono (28/ago): "colocamos o funcionamento do corte para filtrar
#   os ruidos: o corte a partir do M15 seguido de confirmacao. Claro que se nao
#   houve a confirmacao ele estara CARREGANDO a operacao ate identificar uma
#   possivel mudanca de comportamento para o corte."
#   Logo:
#   - M1 / M5 / M10 IDENTIFICAM e MONITORAM. Nunca cortam. (o filtro de ruido)
#   - O corte nasce do M15 para cima, e so com CONFIRMACAO: o comportamento
#     (reversao ou exaustao) identificado nos andares de baixo, confirmado no
#     andar de decisao.
#   - Sem confirmacao: CARREGA a posicao. Nao existe corte por leitura solta.
# ===========================================================================
ANDARES_QUE_DECIDEM = ["M15","M30","H1","H4","Daily","W1","MN1"]   # §2.2 / D2
ANDARES_QUE_IDENTIFICAM = ["M1","M5","M10"]                        # so leem

def decisao_de_corte(lt: "LeitorMultiTF", ts, lado_posicao: int,
                     andar_decisao: str = "M15") -> dict:
    """Devolve o veredito do Ciclo para a posicao aberta nesta barra:
       {"corta": bool, "andar": str, "identificado_em": [...], "confirmado_por": [...],
        "motivo": str, "leitura": [RespostaChecklist...]}
       Sem confirmacao -> corta=False e a posicao SEGUE CARREGADA."""
    if lado_posicao == 0: return {"corta": False, "motivo": "sem posicao"}
    res = ciclo_checklist(lt, ts, lado_posicao=lado_posicao)
    por_andar = {r.andar: r for r in res}
    # 1) IDENTIFICACAO nos andares de baixo: reversao (escada) ou exaustao,
    #    com o sentido do andar CONTRA a posicao.
    ident = []
    for nm in ANDARES_QUE_IDENTIFICAM:
        r = por_andar.get(nm)
        if r is None or r.sentido != -lado_posicao: continue
        rev = r.itens[4][0]; exa = r.itens[11][0]; quebra = r.itens[5][0]
        if rev or exa or quebra:
            que = []
            if exa: que.append(f"exaustao ({r.itens[11][1]})")
            if rev: que.append(f"reversao {r.itens[4][1]}")
            if quebra: que.append("quebra de estrutura")
            ident.append((nm, "; ".join(que)))
    if not ident:
        return {"corta": False, "andar": None, "identificado_em": [], "confirmado_por": [],
                "motivo": "nada identificado contra a posicao nos andares de leitura — CARREGA",
                "leitura": res}
    # 2) CONFIRMACAO a partir do andar de decisao (M15 para cima)
    idx0 = ANDARES_QUE_DECIDEM.index(andar_decisao)
    for nm in ANDARES_QUE_DECIDEM[idx0:]:
        r = por_andar.get(nm)
        if r is None: continue
        if r.sentido != -lado_posicao:      # este andar nao confirma o comportamento
            continue
        conf = []
        if r.confirma_abaixo: conf.append("confirma o andar de baixo")
        if r.itens[4][0]:  conf.append(f"reversao {r.itens[4][1]}")
        if r.itens[11][0]: conf.append(f"exaustao ({r.itens[11][1]})")
        if r.itens[5][0]:  conf.append("quebra de estrutura")
        if conf:
            return {"corta": True, "andar": nm, "identificado_em": ident,
                    "confirmado_por": [(nm, "; ".join(conf))],
                    "motivo": f"identificado em {', '.join(a for a,_ in ident)} e CONFIRMADO no {nm}",
                    "leitura": res}
    return {"corta": False, "andar": None, "identificado_em": ident, "confirmado_por": [],
            "motivo": (f"identificado em {', '.join(a for a,_ in ident)} mas SEM confirmacao "
                       f"do {andar_decisao} para cima — CARREGA a operacao"),
            "leitura": res}

# ===========================================================================
# CORTE PELO CICLO — a conversa entre os andares vira DECISAO (Feito00091)
#   Palavra do dono (28/ago): "foi identificado uma reversao ou uma exaustao;
#   se foi identificado e foi confirmado pelo Ciclo, corta."
#   Portanto: NAO existe quorum, NAO se conta cor de barra (medido e REPROVADO
#   em 28/ago: contagem de barras contra na janela = 35% vs 35% da base, sem
#   valor de aviso; coerente com a medicao de 27/ago — barra isolada e ruido).
#   O que sobe entre andares e o EVENTO ja identificado pelas reguas do Bloco 1
#   (exaustao E1/E2/E3, escada dos 3 sinais, escada fina). A CONFIRMACAO e o
#   Ciclo: o mesmo evento aparecendo no andar seguinte. A DECISAO sai no 15m.
# ===========================================================================
_EV_REVERSAO = {"topo_barra_rompida":+1, "fundo_barra_rompido":-1,
                "rompeu_ultimo_topo":-1, "rompeu_ultimo_fundo":+1,
                "alerta_empilhado_3":0}          # 0 = lado vem da perna vigente
_EV_EXAUSTAO = {"exaustao_identificada":0}

def corte_pelo_ciclo(lt: "LeitorMultiTF", andar_decisao: str = "M15",
                     andares_leitura: List[str] = None, ev_cache: dict = None):
    """Devolve {i_decisao: [(andar, evento, lado_cortado, quando)]} — os cortes
    que o Ciclo identificou nos andares de baixo E confirmou subindo, com a
    decisao saindo na barra do andar de decisao (15m por desenho, §2.2).
    lado_cortado = +1 -> quem esta COMPRADO sai; -1 -> quem esta VENDIDO sai."""
    if andar_decisao not in lt.andares: return {}
    andares_leitura = andares_leitura or [a for a in ESCADA_ANDARES[:ESCADA_ANDARES.index(andar_decisao)+1]
                                          if a in lt.andares]
    D = lt.andares[andar_decisao]; ts_d = D.df.ts.values
    ev_cache = ev_cache if ev_cache is not None else {}
    def EV(nm):
        if nm not in ev_cache: ev_cache[nm] = eventos_escada_ciclo(lt, nm)
        return ev_cache[nm]
    # 1) identificacao: todo evento de reversao/exaustao, por andar, com lado
    ident = {}          # (i_decisao) -> lista de (andar, evento, lado, ts)
    for nm in andares_leitura:
        A = lt.andares[nm]; dirn = A.df.perna_dir.values; ts_a = A.df.ts.values
        for i, e, det in EV(nm):
            lado = _EV_REVERSAO.get(e, _EV_EXAUSTAO.get(e))
            if lado is None: continue
            if lado == 0:                     # lado vem da perna vigente / do texto
                if e == "exaustao_identificada":
                    lado = +1 if "topo" in det else -1 if "fundo" in det else 0
                else:
                    d = int(dirn[i-1]) if i > 0 else 0
                    lado = d
            if lado == 0: continue
            if e == "rompeu_ultimo_topo" and "REVERSAO" not in det: continue
            if e == "rompeu_ultimo_fundo" and "REVERSAO" not in det: continue
            t = ts_a[i]
            k = int(np.searchsorted(ts_d, t, side="left"))   # barra do 15m que DECIDE
            if k >= len(ts_d): continue
            ident.setdefault(k, []).append((nm, e, lado, pd.Timestamp(t)))
    # 2) CONFIRMACAO PELO CICLO — SEQUENCIAL, nunca simultanea.
    #    Fundamento (dono, 28/ago): identifica no 1M->5M, "confirma no 10M e
    #    entre o 10M e o 15M chega a confirmacao das informacoes passadas pelos
    #    candles de baixo". Logo o andar de cima confirma DEPOIS, no tempo.
    #    Contar o mesmo evento aparecendo no mesmo minuto em M1/M5/M15 NAO e
    #    confirmacao — e o mesmo evento contado tres vezes (defeito medido:
    #    80% das barras virariam corte). Exigencia: identificacao no andar de
    #    BAIXO e, ESTRITAMENTE DEPOIS, confirmacao num andar SUPERIOR.
    out = {}
    for k, lst in ident.items():
        for lado in (+1, -1):
            do_lado = [(nm, e, l, t) for nm, e, l, t in lst if l == lado]
            if len(do_lado) < 2: continue
            ok = False
            for nm_i, e_i, _, t_i in do_lado:
                p_i = ESCADA_ANDARES.index(nm_i)
                for nm_c, e_c, _, t_c in do_lado:
                    if ESCADA_ANDARES.index(nm_c) > p_i and t_c > t_i:
                        ok = True; break          # andar superior confirmou DEPOIS
                if ok: break
            if ok:
                out.setdefault(k, []).extend(do_lado)
    return out

# ===========================================================================
# FICHA §9 — SAIDA DO BLOCO 1 (o contrato percepcao -> execucao; doc v3.6 §9)
#   Publicada por barra fechada. O Bloco 2 SO enxerga isto. v1: itens 1-9;
#   B1-B5 e telemetria LM = proximos itens (declarado).
# ===========================================================================
ORDEM_C1 = ["M1","M5","M10","M15","M30","H1","H4","Daily"]
ORDEM_C2 = ["MN1","W1","Daily","H4","H1","M30","M15","M10","M5"]   # §1.1: desce ate o 5m

def _idx_ts(df, ts):
    ix = df.index[df.ts <= ts]
    return int(ix[-1]) if len(ix) else -1

def ficha_saida(lt: "LeitorMultiTF", ts, andar_ref: str = "M15", lado_posicao: int = 0) -> str:
    """Gera a ficha §9 no fechamento da barra <= ts.
    lado_posicao: +1 comprado / -1 vendido / 0 sem posicao — a ficha comanda
    SOBRE A POSICAO ABERTA (um unico comando, §9)."""
    ts = pd.Timestamp(ts)
    ev_cache = {}; cx_cache = {}; _sac_cache = {}; _gap_cache = {}
    def EV(nm):
        if nm not in ev_cache: ev_cache[nm] = eventos_escada_ciclo(lt, nm)   # item 16: contexto tardio pelo Ciclo
        return ev_cache[nm]
    def CX(nm):
        if nm not in cx_cache: cx_cache[nm] = detectar_caixas(lt.andares[nm], lt_andares=lt.andares)
        return cx_cache[nm]
    L=[]; L.append(f"FICHA §9 — {lt.ativo} @ {ts}  (motor {MOTOR_VERSAO})")
    # 2) referencia do Ciclo 2
    ref=[]
    for nm in ORDEM_C2:
        if nm not in lt.andares: continue
        d=lt.andares[nm].df; i=_idx_ts(d, ts)
        if i<0: continue
        r=d.iloc[i]; est=int(r.estado_canal) if np.isfinite(r.estado_canal) else 0
        ref.append(f"{nm}:{'+1' if est>0 else '-1' if est<0 else '0'}({int(r.perna_L)}{'U' if r.perna_dir>0 else 'D' if r.perna_dir<0 else 'L'})")
    L.append("2) REFERENCIA C2: " + "  ".join(ref))
    # 1/3/4/5/6/7 por andar do Ciclo 1
    sinais=[]; cortes=[]
    for nm in ORDEM_C1:
        if nm not in lt.andares: continue
        A=lt.andares[nm]; d=A.df; i=_idx_ts(d, ts)
        if i<0: continue
        r=d.iloc[i]; mp=A.mapas[i]
        est=int(r.estado_canal) if np.isfinite(r.estado_canal) else 0
        lin=f"{nm:5s} barra={pd.Timestamp(r.ts):%d/%m %H:%M} estado={est:+d} perna={int(r.perna_L)}{'U' if r.perna_dir>0 else 'D' if r.perna_dir<0 else 'L'} D={r.afast_D:+.1f}ATR"
        ut = f"topo={mp.ultimo_topo[1]:.2f}" if mp.ultimo_topo else "topo=—"
        uf = f"fundo={mp.ultimo_fundo[1]:.2f}" if mp.ultimo_fundo else "fundo=—"
        lin += f" | {ut} {uf}"
        # caixa ativa neste instante
        atv=[c for c in CX(nm) if c.i_ini<=i<=c.i_fim]
        if atv:
            c=atv[-1]; lin += f" | CAIXA[{c.piso:.2f},{c.teto:.2f}] n={c.n_barras}{' MADURA' if c.range_maduro else ''} teto{'v' if c.teto_conf else '?'} piso{'v' if c.piso_conf else '?'}"
        # eventos DESTA barra (escada + sacudida §5.7 + gap §5.8)
        if nm not in _sac_cache: _sac_cache[nm] = eventos_sacudida(lt.andares[nm], CX(nm))
        if nm not in _gap_cache: _gap_cache[nm] = eventos_gap(lt.andares[nm])
        evb=[(e,det) for j,e,det in EV(nm) if j==i]
        evb+=[(e,det) for j,e,det in _sac_cache[nm] if j==i]
        evb+=[(e,det) for j,e,det in _gap_cache[nm] if j==i]
        for e,det in evb:
            lin += f" | {e}"
            if e=="alerta_empilhado_3": cortes.append((nm,"reversao_alertas_empilhados"))   # so telemetria
            if e.startswith("rompeu_ultimo") and "REVERSAO" in det:
                cortes.append((nm,"reversao_3sinal"))
                _dfn=lt.andares[nm].df
                _lado = +1 if e=="rompeu_ultimo_topo" else -1
                _niv  = float(_dfn.high.iloc[i]) if _lado>0 else float(_dfn.low.iloc[i])
                sinais.append((nm,"gatilho_armado_reversao",
                    f"3o sinal ({det}); gatilho = {'maxima' if _lado>0 else 'minima'} {_niv:.2f} do candle do sinal "
                    f"— ENTRADA so com CONTINUIDADE (Feito00094), nunca no toque puro"))
            if e in ("topo_barra_rompida","fundo_barra_rompido"): cortes.append((nm,"reversao_2sinal_fino"))
        # rompimento de caixa confirmado NESTA barra -> sinal de entrada
        for c in CX(nm):
            if c.fim.startswith("rompida_confirmada") and c.i_fim==i and "sem_avanco" not in c.fim:
                lado="compra" if "cima" in c.fim else "venda"
                sinais.append((nm,"gatilho_armado_rompimento",f"caixa [{c.piso:.2f},{c.teto:.2f}] rompida ({lado}); gatilho = extremo do candle que rompeu — ENTRADA so com CONTINUIDADE (Feito00094), nunca no toque puro"))
        L.append("   "+lin)
    # 6c) CORTE PELO CICLO (decisao no 15m; identificado + confirmado)
    cc = corte_pelo_ciclo(lt, "M15", ev_cache=ev_cache) if "M15" in lt.andares else {}
    k15 = _idx_ts(lt.andares["M15"].df, ts) if "M15" in lt.andares else -1
    corte_ciclo_agora = cc.get(k15, [])
    # 6b) REPLICACAO ENTRE ANDARES (item 16, §6) — insumo da R3 e do v5
    rep = replicacao(lt, ts, ev_por_andar=ev_cache)
    if rep:
        L.append("6b) REPLICACAO (mesma estrutura repetida na janela):")
        for g in ("exaustao","reversao","rompimento"):
            if g in rep:
                L.append(f"   {g}: {rep[g]['n']} andar(es) — " + ", ".join(rep[g]["andares"]))
    else:
        L.append("6b) REPLICACAO: nenhuma estrutura repetida na janela")
    # 8) sinais ao Bloco 2
    L.append("8) SINAIS AO BLOCO 2:" + ("" if sinais else " (nenhum nesta barra)"))
    for nm,sg,det in sinais: L.append(f"   {nm}: {sg} — {det}")
    # 9) COMANDO AO EXECUTOR — UM SO (§9). Fonte unica: decisao_de_corte()
    #    (a partir do M15, seguido de confirmacao — Feito00093). O mecanismo
    #    antigo "CORTE_TOTAL condicional por andar" foi REMOVIDO: dois comandos
    #    na mesma barra viola o contrato da ficha (defeito achado no AB3).
    if lado_posicao == 0:
        L.append("9) COMANDO: nenhum (sem posicao aberta — a ficha so comanda sobre o que esta aberto)")
        L.append("   leitura de corte disponivel para os dois lados via decisao_de_corte(lt, ts, lado)")
    else:
        dcx = decisao_de_corte(lt, ts, lado_posicao)
        if dcx.get("corta"):
            ident = "; ".join(f"{a}: {q}" for a, q in dcx["identificado_em"])
            conf  = "; ".join(f"{a}: {q}" for a, q in dcx["confirmado_por"])
            L.append(f"9) COMANDO: CORTE_TOTAL — fecha {'COMPRA' if lado_posicao>0 else 'VENDA'} "
                     f"(decisao no {dcx['andar']})")
            L.append(f"   identificado em: {ident}")
            L.append(f"   confirmado por : {conf}")
        else:
            L.append(f"9) COMANDO: nenhum — CARREGA a posicao {'COMPRADA' if lado_posicao>0 else 'VENDIDA'}")
            L.append(f"   motivo: {dcx['motivo']}")
    # 10) BLINDAGENS ATIVAS (§9 item 10; itens 19-22 da §12)
    bl = blindagens(lt, ts, ativo=lt.ativo, lado_posicao=lado_posicao)
    L.append("10) BLINDAGENS:")
    for k in ("B1","B2","B3","B5"):
        b = bl[k]
        on = b.get("ativa", b.get("corta", False))
        L.append(f"   {k} {'ATIVA' if on else 'ok   '} — {b['motivo']}")
    if bl["B3"].get("corta") and lado_posicao != 0:
        L.append("   >>> B3 manda CORTE DE PROTECAO (tese expirou)")
    if bl["B5"].get("ativa") and lado_posicao != 0:
        L.append("   >>> B5 manda FECHAR TUDO (30 min antes do encerramento de sexta)")
    # 13) caixa dentro de caixa (§5.9) — desempate do andar maior
    cdc = caixa_dentro_de_caixa(lt, ts, "M5", "M15")
    if cdc: L.append(f"13) CAIXA DENTRO DE CAIXA: {cdc}")
    L.append(f"11) TELEMETRIA LM: ficha completa auditavel (motor {MOTOR_VERSAO} build {BUILD_TAG}) — "
             f"coletor Telemetria() disponivel para gravar eventos, comandos e recusas")
    return "\n".join(L)


# ===========================================================================
# FICHA §9 ESTRUTURADA — A FONTE UNICA (Feito00101)
#   Ate 30/ago a ficha so existia em TEXTO, e por isso o medidor (e o card)
#   chamavam funcoes internas por baixo — furando o proprio contrato §9 e
#   perdendo sacudida, gap, caixa-dentro-de-caixa e o checklist por andar.
#   Esta classe publica a ficha em DADOS, pre-computada uma vez, para que
#   Bloco 2 e Professor consumam EXCLUSIVAMENTE dela. Uma fonte, um contrato.
# ===========================================================================
class FichaSerie:
    """Pre-computa a ficha §9 para todas as barras do andar de operacao.
    Consulta: .em(i, lado_posicao) -> dict com TUDO que a §9 manda publicar."""

    def __init__(self, lt: "LeitorMultiTF", andar_op: str = "M15", ativo: str = ""):
        self.lt = lt; self.andar_op = andar_op; self.ativo = ativo or lt.ativo
        self.D = lt.andares[andar_op].df
        self.ts = self.D.ts.values; self.n = len(self.D)
        self.andares = [a for a in ESCADA_ANDARES if a in lt.andares]
        # --- caches por andar (uma vez) ---
        self.ev = {nm: eventos_escada_ciclo(lt, nm) for nm in self.andares}
        self.cx = {nm: detectar_caixas(lt.andares[nm], lt_andares=lt.andares) for nm in self.andares}
        self.sac = {nm: eventos_sacudida(lt.andares[nm], self.cx[nm]) for nm in self.andares}
        self.gap = {nm: eventos_gap(lt.andares[nm]) for nm in self.andares}
        self._indexar()
        self._blindagens()
        self._gatilhos()
        self._cortes()

    # ---------- eventos mapeados para a barra do andar de operacao ----------
    def _passo(self, nm):
        t = self.lt.andares[nm].df.ts.values
        return (t[1] - t[0]) if len(t) > 1 else np.timedelta64(0, "s")

    def _indexar(self):
        """Todo evento de todo andar (escada + SACUDIDA + GAP) na barra do andar
        de operacao em que ele ja pode ser usado (apos a barra do andar FECHAR)."""
        self.eventos_por_barra = [[] for _ in range(self.n)]
        for nm in self.andares:
            ts_a = self.lt.andares[nm].df.ts.values; passo = self._passo(nm)
            for fonte, tag in ((self.ev[nm], "escada"), (self.sac[nm], "sacudida"), (self.gap[nm], "gap")):
                for i, e, det in fonte:
                    k = int(np.searchsorted(self.ts, ts_a[i] + passo, side="left"))
                    if k < self.n:
                        self.eventos_por_barra[k].append((nm, e, det, tag))

    # ---------- blindagens (§7) vetorizadas ----------
    def _blindagens(self):
        n = self.n
        self.B1 = np.zeros(n, bool); self.B5 = np.zeros(n, bool)
        if "M1" in self.lt.andares:
            m1 = self.lt.andares["M1"].df
            rg = (m1.high.values - m1.low.values); at = m1.atr14.values
            cho = rg > PARAMS_BLIND["B1_V_RANGE"] * np.nan_to_num(at, nan=1e9)
            if "spread" in m1.columns:
                sp = m1["spread"].values.astype(float)
                med = pd.Series(sp).rolling(240, min_periods=30).median().values
                cho |= sp > PARAMS_BLIND["B1_S_SPREAD"] * np.nan_to_num(med, nan=1e9)
            jan = pd.Series(cho).rolling(PARAMS_BLIND["B1_N_VOLTA"], min_periods=1).max().values.astype(bool)
            k1 = np.searchsorted(m1.ts.values, self.ts, side="right") - 1
            self.B1 = np.where(k1 >= 0, jan[np.clip(k1, 0, len(jan)-1)], False)
        if not any(x in self.ativo.upper() for x in ("BTC","ETH","XRP","SOL","LTC","DOGE")):
            t = pd.Series(pd.to_datetime(self.ts)); sx = t.dt.weekday == 4
            if sx.any():
                ult = t[sx].groupby(t[sx].dt.date).transform("max")
                self.B5[sx.values] = (t[sx] >= ult - pd.Timedelta(minutes=PARAMS_BLIND["B5_MIN_ANTES"])).values

    # ---------- gatilhos armados (§5.2 + Lei da Continuidade) ----------
    def _gatilhos(self):
        """A barra que FECHA alem da fronteira arma o gatilho no proprio extremo.
        Sem saber se vai confirmar (vies de sobrevivencia corrigido, Feito00099).
        SACUDIDA e CAIXA-DENTRO-DE-CAIXA entram aqui como o doc manda (§5.7/§5.9)."""
        A = self.lt.andares[self.andar_op]; df = A.df
        hh = df.high.values; ll = df.low.values; cc = df.close.values
        # BUG CORRIGIDO (Feito00102): a versao anterior comparava o fechamento
        # contra teto/piso FINAIS da caixa — que ja INCLUEM a barra do rompimento
        # (por definicao nenhum fechamento supera o proprio maximo). Resultado:
        # ZERO gatilhos de rompimento; o medidor operou so reversoes e deu
        # negativo. Agora a fronteira e reconstruida barra a barra usando SO as
        # barras ANTERIORES (extremos de i_ini..j-1): decidivel na propria
        # barra, sem futuro. A barra que FECHA alem dessa fronteira ARMA.
        sac_i = {i for i, e, d in self.sac[self.andar_op]}
        self.gatilhos = []
        N_ARMA = 3            # caixa armada com 3 barras (§5.1, barbwire [TRAD])
        for c in self.cx[self.andar_op]:
            fim = min(c.i_fim + 2, self.n)     # a barra do rompimento pode ser i_fim+1
            for j in range(c.i_ini + N_ARMA, fim):
                teto_j = float(np.max(hh[c.i_ini:j]))   # fronteiras ATE a barra anterior
                piso_j = float(np.min(ll[c.i_ini:j]))
                lado = +1 if cc[j] > teto_j else (-1 if cc[j] < piso_j else 0)
                if lado == 0: continue
                if j in sac_i:            # §5.7: varreu e voltou = setup, nao rompimento
                    self.gatilhos.append((j, lado, float(hh[j] if lado>0 else ll[j]),
                                          "rompimento", "RECUSADO_sacudida")); break
                absorvido = self._absorvido(j, lado)   # §5.9: andar maior desempata
                self.gatilhos.append((j, lado, float(hh[j] if lado>0 else ll[j]),
                                      "rompimento", "RECUSADO_absorvido" if absorvido else "ok")); break
        # 3o sinal de reversao
        for i, e, det in self.ev[self.andar_op]:
            if e.startswith("rompeu_ultimo") and "REVERSAO" in det:
                lado = +1 if e == "rompeu_ultimo_topo" else -1
                self.gatilhos.append((i, lado, float(hh[i] if lado>0 else ll[i]), "reversao", "ok"))
        self.gatilhos.sort(key=lambda x: x[0])

    def _absorvido(self, i, lado):
        """§5.9: o andar MAIOR manda no estado. Se o rompimento do andar de
        operacao acontece DENTRO de uma caixa ativa do andar acima, e movimento
        interno — o evento fica registrado como ABSORVIDO e nao vira entrada."""
        idx = ESCADA_ANDARES.index(self.andar_op)
        if idx + 1 >= len(ESCADA_ANDARES): return False
        nm_maior = ESCADA_ANDARES[idx + 1]
        if nm_maior not in self.lt.andares: return False
        AM = self.lt.andares[nm_maior]
        j = _idx_ts(AM.df, self.ts[i])
        if j < 0: return False
        fech = float(self.lt.andares[self.andar_op].df.close.iloc[i])
        for c in self.cx[nm_maior]:
            if c.i_ini <= j <= c.i_fim and c.piso < fech < c.teto:
                return True
        return False

    # ---------- comando de corte (§9 item 9) ----------
    def _cortes(self):
        self.corta = {+1: np.zeros(self.n, bool), -1: np.zeros(self.n, bool)}
        self.motivo = {+1: [""]*self.n, -1: [""]*self.n}
        ident = {+1: np.zeros(self.n, bool), -1: np.zeros(self.n, bool)}
        def lado_do(e, det, dirn, i):
            if e == "exaustao_identificada": return +1 if "topo" in det else -1 if "fundo" in det else 0
            if e == "topo_barra_rompida": return +1
            if e == "fundo_barra_rompido": return -1
            if e == "rompeu_ultimo_fundo": return +1
            if e == "rompeu_ultimo_topo": return -1
            if e == "alerta_empilhado_3": return int(dirn[i-1]) if i > 0 else 0
            return 0
        for grupo, alvo in ((ANDARES_QUE_IDENTIFICAM, ident), (ANDARES_QUE_DECIDEM, self.corta)):
            for nm in grupo:
                if nm not in self.lt.andares: continue
                A = self.lt.andares[nm]; dirn = A.df.perna_dir.values
                ts_a = A.df.ts.values; passo = self._passo(nm)
                for i, e, det in self.ev[nm]:
                    ld = lado_do(e, det, dirn, i)
                    if ld == 0: continue
                    k = int(np.searchsorted(self.ts, ts_a[i] + passo, side="left"))
                    if k >= self.n: continue
                    if alvo is ident:
                        ident[ld][k] = True
                        self.motivo[ld][k] = (self.motivo[ld][k] + f" {nm}:{e}").strip()
                    elif ident[ld][k]:
                        self.corta[ld][k] = True
                        self.motivo[ld][k] = (self.motivo[ld][k] + f" -> {nm}:{e}").strip()

    # ---------- a ficha da barra ----------
    def em(self, i: int, lado_posicao: int = 0) -> dict:
        """A ficha §9 da barra i. TUDO o que o Bloco 2 pode enxergar."""
        evb = self.eventos_por_barra[i]
        gat = [g for g in self.gatilhos if g[0] == i]
        return dict(
            i=i, ts=pd.Timestamp(self.ts[i]), ativo=self.ativo, andar=self.andar_op,
            eventos=evb,
            sacudida=[(nm, d) for nm, e, d, tag in evb if tag == "sacudida"],
            gap=[(nm, e, d) for nm, e, d, tag in evb if tag == "gap"],
            gatilhos=[dict(lado=g[1], nivel=g[2], tipo=g[3], estado=g[4]) for g in gat],
            comando=("CORTE_TOTAL" if (lado_posicao != 0 and self.corta[lado_posicao][i]) else None),
            motivo_corte=(self.motivo[lado_posicao][i] if lado_posicao != 0 else ""),
            blindagens=dict(B1=bool(self.B1[i]), B5=bool(self.B5[i]),
                            B2=dict(ativa=False, sem_fonte=True)),
        )

# ---------------------------------------------------------------------------
# USO: python bloco1_motor_v3.py <pasta> <ativo>
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else "Test 12meses"
    ativo = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
    modo  = sys.argv[3] if len(sys.argv) > 3 else "fundacao"      # fundacao | caixas
    desde = sys.argv[4] if len(sys.argv) > 4 else None
    ate   = sys.argv[5] if len(sys.argv) > 5 else None
    lt = LeitorMultiTF(pasta, ativo).carregar()
    print(lt.relatorio_fidelidade())
    if modo == "ficha":
        # USO: python bloco1_motor_v3.py "Test 12meses" XAUUSD ficha "2026-08-18 04:30"
        _lado = 0
        if len(sys.argv) > 5:
            _lado = {"comprado": 1, "compra": 1, "buy": 1, "+1": 1,
                     "vendido": -1, "venda": -1, "sell": -1, "-1": -1}.get(str(sys.argv[5]).lower(), 0)
        print(); print(ficha_saida(lt, desde or pd.Timestamp.now(), lado_posicao=_lado))
    if modo == "eventos":
        # USO: ... eventos 2026-08-18 2026-08-19  -> escada/exaustao do M15 e Daily no trecho
        for nm in ("M15","Daily"):
            if nm not in lt.andares: continue
            A=lt.andares[nm]; print(f"\nEVENTOS — {nm}:")
            for i,e,det in eventos_escada(A):
                t=pd.Timestamp(A.df.ts.iloc[i])
                if desde and t<pd.Timestamp(desde): continue
                if ate and t>pd.Timestamp(ate)+pd.Timedelta(days=1): continue
                print(f"  {t:%d/%m %H:%M} {e}: {det}")
    if modo == "caixas":
        ordem = ["M1","M5","M15","M30","H1","H4","Daily","W1","MN1"]
        print(f"\nITEM 5 — CAIXAS DE COMPRESSAO | testes={PARAMS_COMPRESSAO} | caixa={PARAMS_CAIXA}")
        for k,a in enumerate(ordem):
            if a not in lt.andares: continue
            cxs = detectar_caixas(lt.andares[a], lt.andares)
            n=len(cxs); cls={}; fins={}
            for x in cxs: cls[x.classe]=cls.get(x.classe,0)+1; fins[x.fim]=fins.get(x.fim,0)+1
            dur=np.mean([x.n_barras for x in cxs]) if cxs else 0; mad=sum(1 for x in cxs if x.range_maduro); rea=sum(x.reativada for x in cxs)
            print(f"\n  {a}: caixas={n} classes={cls} duracao_media={dur:.1f} barras maduras(>20)={mad} reativacoes={rea} fins={fins}")
            if desde or ate:
                print(imprimir_caixas(cxs, desde, ate))
    # amostra do mapa: ultimas 3 barras do Daily
    if "Daily" in lt.andares:
        d = lt.andares["Daily"]; n = len(d.df)
        print("\nAMOSTRA — Daily, ultimas 3 barras (mapa so com pivos CONFIRMADOS, atraso N=2 respeitado):")
        for i in range(n-3, n):
            r = d.df.iloc[i]; mp = d.mapas[i]
            print(f"  {r['ts'].date()} O={r['open']:.2f} H={r['high']:.2f} L={r['low']:.2f} C={r['close']:.2f} | "
                  f"ATR14={r['atr14']:.2f} canal=[{r['ema20_l']:.2f},{r['ema20_h']:.2f}] estado={int(r['estado_canal']):+d} "
                  f"L={int(r['perna_L'])}{'U' if r['perna_dir']>0 else 'D' if r['perna_dir']<0 else ''} D={r['afast_D']:+.2f}ATR | "
                  f"ult_topo={mp.ultimo_topo} ult_fundo={mp.ultimo_fundo} seqT={mp.seq_topos} seqF={mp.seq_fundos}")
