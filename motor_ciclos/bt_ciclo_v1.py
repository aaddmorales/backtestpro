# -*- coding: utf-8 -*-
# ============================================================================
#  BT CICLO v1 — PERCEPCAO DO BLOCO 1 AO VIVO (constituicao v3.0, 24/ago)
#  VERSAO: 1.0 | BUILD: 2026-09-18d-bloco1-vivo | Registro: construcao por
#  ordem do dono (18/set): "tudo funcionando como tem que ser".
#
#  O QUE E: o modulo de PERCEPCAO da constituicao, consumindo os 7 TFs
#  NATIVOS que o espelho vivo JA grava (M1 M5 M15 M30 H1 H4 Daily) — o M1 e
#  o M5 estavam no disco desde o v1.0 da sombra e NENHUMA percepcao os lia.
#  Roda em CADA andar: pivos N=2, contador de perna L, afastamento D,
#  compressao (4 testes) -> CAIXA, rompimento + Lei de Confirmacao (carimbo
#  por_barra/por_gap), rompimento falso, sacudida, exaustao E1/E2/E3 com
#  contexto tardio, escada dos 3 sinais, respiro esperado, janela 10->15
#  (base 1m->15m), estado unico com profundidade, Ficha do D1 (§8) e a
#  FICHA DE SAIDA (§9) — o contrato percepcao->execucao.
#
#  O QUE NAO E: autoridade. NADA aqui comanda ordem ou corte real.
#  Lei da casa ("nada sobe sem medicao") + decreto do dono (18/set:
#  "nao alterar o executor antes de demonstrar a ligacao"): este modulo
#  NARRA em paralelo (vivo_ficha_<ativo>.csv + --ciclo-prova); o comando
#  CORTE_TOTAL sai como comando_NARRADO. Autoridade so apos medicao
#  (professor do Bloco 1) e carimbo.
#
#  PARAMETROS: TODOS os numeros da tabela §11 estao em PARAMS com
#  medido=False ([REF] da constituicao). O medidor (v5) e quem os crava.
#
#  v2.0 — LEITURA POR INTEIRO (decreto do dono, 19/set): fim do resumo.
#  Cada TF produz a FICHA DE 12 CAMPOS (estrutura, regime, direcao, forca
#  0-100, momentum, localizacao, volatilidade, evento, estado_barra,
#  confianca 0-100, ultima_mudanca, persistencia), SEPARANDO barra FECHADA
#  de barra FORMANDO (a parcial do TF alto lida pelas barras de M1 dentro
#  dela — reagir antes SEM inventar confirmacao). MAQUINA DE FASES da
#  propagacao (1 nascimento -> 2 propagacao -> 3 controle -> 4 H4 formando
#  -> 5 impacto no D1), com MEMORIA em disco (linha do tempo do movimento)
#  e HISTERESE do estado exibido (HISTERESE_BARRAS [REF] — o estado BRUTO
#  e preservado e continua sendo o unico com autoridade ate medicao).
#  CAMADAS: D1/H4=Contexto · H1/M30=Controle · M15=Decisao · M5/M1=Gatilho;
#  MOTOR DE CONFLITOS entre camadas + CONCLUSAO CONJUNTA dos dois Ciclos
#  (Ciclo 2 diz o territorio e a forca; Ciclo 1 diz o que nasce e ate onde
#  propagou; nenhum disputa — a conclusao compara os dois). Formalizacao
#  pullback x reversao pelas fases. Formulas de forca/confianca = [REF],
#  declaradas, nao medidas — o professor as crava.
#  LIMITES DECLARADOS (constituicao §10): barra FECHADA por andar; sem tick
#  (M1 = menor regua); pivo N=2 confirma 2 barras depois; noticia fora
#  (B2 = modulo calendario, inexistente — declarado).
# ============================================================================
import os, glob, sys
import numpy as np
import pandas as pd

CV1_VERSAO = "2.4"
MEM_FORMATO = 2

# ---- §11: tabela de parametros — [REF], NAO MEDIDOS ate o professor rodar --
PARAMS = {
    "Z_SOBREPOSICAO":   dict(v=0.50, medido=False, fonte="Brooks barb-wire"),
    "NR_N":             dict(v=7,    medido=False, fonte="Crabel NR7"),
    "X_RANGE_ATR":      dict(v=0.8,  medido=False, fonte="frota velha LATERAL_ATR"),
    "W_AVANCO_ATR":     dict(v=1.0,  medido=False, fonte="doutrina 17/ago"),
    "K_CANAL_ATR":      dict(v=0.8,  medido=False, fonte="squeeze"),
    "N_CAIXA":          dict(v=3,    medido=False, fonte="Brooks 3+ barras"),
    "L_PERNA_TARDIA":   dict(v=20,   medido=False, fonte="Brooks 20-30"),
    "D_AFASTAMENTO":    dict(v=2.0,  medido=False, fonte="frota velha DIST_MAX_ATR"),
    "X_CLIMAX":         dict(v=2.0,  medido=False, fonte="Brooks maior barra"),
    "R_REJEICAO":       dict(v=0.65, medido=False, fonte="pin bar classico"),
    "K_E3":             dict(v=3,    medido=False, fonte="tres empurroes"),
    "T_E3_ATR":         dict(v=0.5,  medido=False, fonte="parabolic wedge"),
    "N_JANELA_INI":     dict(v=10,   medido=False, fonte="palavra do dono 24/ago"),
    "N_JANELA_FIM":     dict(v=15,   medido=False, fonte="palavra do dono 24/ago"),
    "PIVO_N":           dict(v=2,    medido=False, fonte="fractal classico"),
    "HISTERESE_BARRAS": dict(v=2,    medido=False, fonte="decreto 19/set — so no estado EXIBIDO"),
    "RISCO_CONTRA_MULT": dict(v=0.5, medido=False, fonte="decreto 19/set — contratendencia risco reduzido"),
    "PISO_CONF_FASE":   dict(v=30,   medido=False, fonte="auditoria 19/set — H1 conf=6 promoveu fase 3; piso [REF]"),
    "PISO_PERS_FASE":   dict(v=2,    medido=False, fonte="auditoria 19/set — 1 barra nao e confirmacao"),
}
# v2.1 — os 10 ESTADOS DE PROPAGACAO do decreto (mapa fase -> estado nomeado)
ESTADOS_PROP = ["NEUTRO", "ALERTA_M1", "CONFIRMADO_M5", "CONFIRMADO_M15", "PROPAGANDO_M30",
                "CONTROLE_H1", "FORMANDO_H4", "FORMANDO_D1", "TENDENCIA_CONFIRMADA", "EXAUSTAO_OU_REVERSAO"]
CAMADA = {"D1": "CONTEXTO", "H4": "CONTEXTO", "H1": "CONTROLE", "M30": "CONTROLE",
          "M15": "DECISAO", "M5": "GATILHO", "M1": "GATILHO"}
def P(nome): return PARAMS[nome]["v"]

ANDARES = ["M1", "M5", "M15", "M30", "H1", "H4", "Daily"]
NOME = {"Daily": "D1"}
MIN15 = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "Daily": 1440}


# ============================================================================
#  CARGA — le os CSVs do espelho (formato export, tab, <DATE>/<TIME>/...)
# ============================================================================
class Andar:
    def __init__(self, tf, df):
        self.tf = tf
        tcol = df["<TIME>"] if "<TIME>" in df.columns else "00:00:00"   # v1.4: Daily/W do MT5 nao tem <TIME>
        self.ts = pd.to_datetime(df["<DATE>"] + " " + tcol,
                                 format="%Y.%m.%d %H:%M:%S").values
        self.o = df["<OPEN>"].astype(float).values
        self.h = df["<HIGH>"].astype(float).values
        self.l = df["<LOW>"].astype(float).values
        self.c = df["<CLOSE>"].astype(float).values
        self.n = len(self.c)
        self._derivados()

    def _derivados(self):
        h, l, c = self.h, self.l, self.c
        tr = np.maximum(h[1:] - l[1:],
                        np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
        atr = np.full(self.n, np.nan)
        if self.n > 14:
            atr[14] = tr[:14].mean()
            for i in range(15, self.n):
                atr[i] = (atr[i - 1] * 13 + tr[i - 1]) / 14.0
        self.atr = atr
        k = 2.0 / 21.0
        eh = np.copy(h); el = np.copy(l)
        for i in range(1, self.n):
            eh[i] = eh[i - 1] + k * (h[i] - eh[i - 1])
            el[i] = el[i - 1] + k * (l[i] - el[i - 1])
        self.emaH, self.emaL = eh, el

    def idx_ate(self, ts_lim):
        """ultima barra fechada com ts <= ts_lim (alinhamento entre andares)."""
        return int(np.searchsorted(self.ts, np.datetime64(ts_lim), side="right") - 1)


def carregar_andares(pasta, ativo):
    andares = {}
    for tf in ANDARES:
        arqs = sorted(glob.glob(os.path.join(pasta, f"{ativo}_{tf}_*.csv")))
        if not arqs:
            continue
        df = pd.read_csv(arqs[-1], sep="\t")
        if len(df) >= 30:
            andares[tf] = Andar(tf, df)
    return andares


# ============================================================================
#  REGUAS POR ANDAR (§4/§5) — cada funcao avalia no indice i (barra fechada)
# ============================================================================
def pivos(a, i, lb=120):
    """§4.2 — fractais N=2 confirmados; devolve mapa de estrutura."""
    N = P("PIVO_N")
    ini = max(N, i - lb)
    topos, fundos = [], []
    for k in range(ini, i - N + 1):          # confirmado: N barras de cada lado
        if a.h[k] == max(a.h[k - N:k + N + 1]): topos.append((k, a.h[k]))
        if a.l[k] == min(a.l[k - N:k + N + 1]): fundos.append((k, a.l[k]))
    def seq(pts, cmpf):
        if len(pts) < 2: return "indefinida"
        u, p = pts[-1][1], pts[-2][1]
        return "ascendente" if cmpf(u, p) else "descendente"
    sq_t = seq(topos, lambda u, p: u > p)
    sq_f = seq(fundos, lambda u, p: u > p)
    sequencia = (sq_t if sq_t == sq_f else "mista") if "indefinida" not in (sq_t, sq_f) else "indefinida"
    return dict(
        ultimo_topo=topos[-1][1] if topos else None,
        ultimo_fundo=fundos[-1][1] if fundos else None,
        resistencia=topos[-2][1] if len(topos) > 1 else None,
        suporte=fundos[-2][1] if len(fundos) > 1 else None,
        sequencia=sequencia, k_topo=topos[-1][0] if topos else None,
        k_fundo=fundos[-1][0] if fundos else None)


def perna_L(a, i):
    """§4.3 — barras consecutivas na mesma direcao sem respiro."""
    if i < 1: return 0, 0
    d = 1 if a.c[i] > a.o[i] else (-1 if a.c[i] < a.o[i] else 0)
    if d == 0: return 0, 0
    n = 0
    for k in range(i, 0, -1):
        dk = 1 if a.c[k] > a.o[k] else (-1 if a.c[k] < a.o[k] else 0)
        if dk == d: n += 1
        else: break
    return d, n


def afastamento_D(a, i):
    """§4.4 — distancia do fechamento ao canal, em ATRs."""
    if np.isnan(a.atr[i]) or a.atr[i] <= 0: return 0.0
    if a.c[i] > a.emaH[i]: return (a.c[i] - a.emaH[i]) / a.atr[i]
    if a.c[i] < a.emaL[i]: return -(a.emaL[i] - a.c[i]) / a.atr[i]
    return 0.0


def compressao(a, i):
    """§5.1 — os 4 testes; devolve (comprimida_nas_ultimas_N, testes)."""
    if i < 25 or np.isnan(a.atr[i]): return False, []
    def testes(k):
        t = []
        rng, rng1 = a.h[k] - a.l[k], a.h[k - 1] - a.l[k - 1]
        inter = min(a.h[k], a.h[k - 1]) - max(a.l[k], a.l[k - 1])
        if rng1 > 0 and inter / rng1 >= P("Z_SOBREPOSICAO"): t.append("sobreposicao")
        if rng <= min(a.h[k - P("NR_N"):k] - a.l[k - P("NR_N"):k]) or rng < P("X_RANGE_ATR") * a.atr[k]:
            t.append("range")
        if abs(a.c[k] - a.c[k - P("N_CAIXA")]) < P("W_AVANCO_ATR") * a.atr[k]: t.append("avanco")
        if (a.emaH[k] - a.emaL[k]) < P("K_CANAL_ATR") * a.atr[k]: t.append("canal")
        return t
    ult = [testes(k) for k in range(i - P("N_CAIXA") + 1, i + 1)]
    ok = all(len(t) >= 2 for t in ult)      # 2+ testes batendo em N consecutivas
    return ok, ult[-1]


def caixa_estado(a, i, lb=90):
    """§5.1/5.3/5.9 — acha a ultima caixa armada e acompanha o rompimento.
    Estados: ativa / rompida_pendente / rompida_confirmada / voltou_compressao."""
    k_arm = None
    for k in range(i, max(25, i - lb), -1):
        ok, _ = compressao(a, k)
        if ok: k_arm = k; break
    if k_arm is None: return None
    j0 = k_arm - P("N_CAIXA") + 1
    topo = float(max(a.h[j0:k_arm + 1])); fundo = float(min(a.l[j0:k_arm + 1]))
    cx = dict(topo=topo, fundo=fundo, k_arm=k_arm, estado="ativa",
              origem=None, lado=0, k_romp=None)
    for k in range(k_arm + 1, i + 1):
        est = cx["estado"]
        if est in ("ativa", "voltou_compressao"):
            if a.c[k] > topo or a.c[k] < fundo:
                cx.update(estado="rompida_pendente", k_romp=k,
                          lado=1 if a.c[k] > topo else -1,
                          origem="por_gap" if (a.o[k] > topo or a.o[k] < fundo) else "por_barra")
        elif est == "rompida_pendente":
            kr, ld = cx["k_romp"], cx["lado"]
            conf = (a.h[k] > a.h[kr]) if ld == 1 else (a.l[k] < a.l[kr])     # Lei de Confirmacao
            dentro = fundo <= a.c[k] <= topo
            if conf and not dentro: cx["estado"] = "rompida_confirmada"
            elif dentro: cx["estado"] = "voltou_compressao"                  # §5.3: caixa reativa
        elif est == "rompida_confirmada":
            if fundo <= a.c[k] <= topo: cx["estado"] = "voltou_compressao"
    return cx


def sacudida(a, i, piv):
    """§5.7 — pavio alem da fronteira + fechamento de volta + estrutura intacta."""
    evs = []
    if piv["ultimo_topo"] and a.h[i] > piv["ultimo_topo"] and a.c[i] <= piv["ultimo_topo"]:
        if not (piv["ultimo_fundo"] and a.c[i] < piv["ultimo_fundo"]): evs.append("sacudida_topo")
    if piv["ultimo_fundo"] and a.l[i] < piv["ultimo_fundo"] and a.c[i] >= piv["ultimo_fundo"]:
        if not (piv["ultimo_topo"] and a.c[i] > piv["ultimo_topo"]): evs.append("sacudida_fundo")
    return evs


def exaustao(a, i, piv):
    """§5.4 — contexto tardio + E1/E2/E3; §5.5 escada (degrau)."""
    if np.isnan(a.atr[i]) or a.atr[i] <= 0: return dict(degrau=0, gatilho=None, lado=0)
    d, L = perna_L(a, i)
    D = abs(afastamento_D(a, i))
    tardio = (L >= P("L_PERNA_TARDIA")) or (D >= P("D_AFASTAMENTO"))
    rng = a.h[i] - a.l[i]; corpo = abs(a.c[i] - a.o[i])
    gat = None; lado = 0
    if tardio and d != 0:
        maior20 = rng >= max(a.h[max(0, i - 20):i] - a.l[max(0, i - 20):i]) if i > 20 else False
        if (rng >= P("X_CLIMAX") * a.atr[i] or maior20) and corpo / max(rng, 1e-12) > 0.6:
            gat, lado = ("E1_climax_baixa" if -d < 0 else "E1_climax_alta"), -d
        pavio = (a.h[i] - max(a.o[i], a.c[i])) if d == 1 else (min(a.o[i], a.c[i]) - a.l[i])
        if rng > 0 and pavio / rng >= P("R_REJEICAO"):
            gat, lado = "E2_rejeicao", -d
        if gat is None and i >= P("K_E3"):
            corpos = [abs(a.c[k] - a.o[k]) for k in range(i - P("K_E3") + 1, i + 1)]
            if all(corpos[j] < corpos[j - 1] for j in range(1, len(corpos))):
                gat, lado = ("E3_gradual_baixa" if -d < 0 else "E3_gradual_alta"), -d
    # escada PERSISTENTE (§5.5): o 1o sinal (gatilho) vive ate 6 barras
    # aguardando o pivo confirmar (2o) e a estrutura quebrar (3o) — o topo
    # do BTC de 18/ago provou que gatilho e pivo raramente caem na mesma barra.
    if gat is None:
        for j in range(i - 1, max(24, i - 6), -1):
            dj = 1 if a.c[j] > a.o[j] else (-1 if a.c[j] < a.o[j] else 0)
            if dj == 0 or np.isnan(a.atr[j]) or a.atr[j] <= 0: continue
            _, Lj = perna_L(a, j)
            tj = (Lj >= P("L_PERNA_TARDIA")) or (abs(afastamento_D(a, j)) >= P("D_AFASTAMENTO"))
            if not tj: continue
            rj = a.h[j] - a.l[j]; cj = abs(a.c[j] - a.o[j])
            m20 = rj >= max(a.h[max(0, j - 20):j] - a.l[max(0, j - 20):j]) if j > 20 else False
            pv = (a.h[j] - max(a.o[j], a.c[j])) if dj == 1 else (min(a.o[j], a.c[j]) - a.l[j])
            if ((rj >= P("X_CLIMAX") * a.atr[j] or m20) and cj / max(rj, 1e-12) > 0.6) \
               or (rj > 0 and pv / rj >= P("R_REJEICAO")):
                gat, lado = ("E1/E2_baixa(persistente)" if -dj < 0 else "E1/E2_alta(persistente)"), -dj
                break
    degrau = 1 if gat else 0
    if gat and lado == -1 and piv["k_topo"] is not None and piv["k_topo"] >= i - 6:
        degrau = 2
        if piv["ultimo_fundo"] and a.c[i] < piv["ultimo_fundo"]: degrau = 3
    if gat and lado == 1 and piv["k_fundo"] is not None and piv["k_fundo"] >= i - 6:
        degrau = 2
        if piv["ultimo_topo"] and a.c[i] > piv["ultimo_topo"]: degrau = 3
    return dict(degrau=degrau, gatilho=gat, lado=lado, tardio=tardio, L=L, D=round(D, 2))


def leitura_andar(a, i):
    """Resumo do andar na barra i: direcao do canal, eventos, estrutura."""
    piv = pivos(a, i)
    dir_canal = 1 if a.c[i] > a.emaH[i] else (-1 if a.c[i] < a.emaL[i] else 0)
    cx = caixa_estado(a, i)
    ex = exaustao(a, i, piv)
    evs = sacudida(a, i, piv)
    d, L = perna_L(a, i)
    if L >= P("L_PERNA_TARDIA"): evs.append("respiro_esperado")            # §5.6
    if cx:
        if cx["estado"] == "rompida_pendente": evs.append(f"rompimento_pendente({cx['origem']})")
        if cx["estado"] == "rompida_confirmada": evs.append(f"rompimento_confirmado({cx['origem']})")
        if cx["estado"] == "voltou_compressao": evs.append("voltou_compressao")
        if cx["estado"] == "ativa": evs.append("compressao_armada")
    if ex["gatilho"]: evs.append(f"exaustao_{'identificada' if ex['degrau']>=2 else 'candidata'}({ex['gatilho']})")
    if piv["ultimo_fundo"] and a.c[i] < piv["ultimo_fundo"]: evs.append("quebra_estrutura_baixa")
    if piv["ultimo_topo"] and a.c[i] > piv["ultimo_topo"]: evs.append("quebra_estrutura_alta")
    return dict(dir=dir_canal, pivos=piv, caixa=cx, exaustao=ex, eventos=evs,
                perna=(d, L), afastamento=round(afastamento_D(a, i), 2))


# ============================================================================
#  FICHA DO D1 (§8) — 10 campos
# ============================================================================
def ficha_d1(and_d, i):
    le = leitura_andar(and_d, i)
    piv = le["pivos"]; a = and_d
    rng = a.h[i] - a.l[i]
    prox = None
    if le["dir"] >= 0 and piv["resistencia"]: prox = (piv["resistencia"] - a.c[i]) / max(a.atr[i], 1e-9)
    if le["dir"] < 0 and piv["suporte"]:      prox = (a.c[i] - piv["suporte"]) / max(a.atr[i], 1e-9)
    return {
        "1_pivos": {k: piv[k] for k in ("ultimo_topo", "ultimo_fundo", "resistencia", "suporte", "sequencia")},
        "2_sentido_dias": le["perna"],
        "3_canal_D1": le["dir"],
        "4_caixa_diaria": (le["caixa"] or {}).get("estado"),
        "5_exaustao_diaria": le["exaustao"]["gatilho"],
        "6_perna_L_dias": le["perna"][1],
        "7_P_continuacao": "nao_medido",          # §8.7 — depende do medidor (v5)
        "8_barra_ontem": dict(sentido=int(np.sign(a.c[i] - a.o[i])),
                              tam_atr=round(rng / max(a.atr[i], 1e-9), 2),
                              fech_no_range=round((a.c[i] - a.l[i]) / max(rng, 1e-9), 2)),
        "9_gap_hoje": "so_intradia_no_vivo",
        "10_dist_prox_pivo_atr": None if prox is None else round(float(prox), 2),
    }


# ============================================================================
#  AVALIACAO COMPLETA — Ficha de Saida (§9), estado unico, janela 10->15
# ============================================================================
def avaliar(pasta, ativo, ts_m15=None, lado_posicao=0, andares=None, gravar_mem=False):
    A = andares or carregar_andares(pasta, ativo)
    if "M15" not in A: raise RuntimeError("espelho sem M15")
    i15 = A["M15"].n - 1 if ts_m15 is None else A["M15"].idx_ate(ts_m15)
    ts15 = pd.Timestamp(A["M15"].ts[i15])
    fim15 = ts15 + pd.Timedelta(minutes=15)

    leituras, fontes = {}, {}
    for tf in ANDARES:
        nm = NOME.get(tf, tf)
        if tf in A:
            i = A[tf].idx_ate(fim15 - pd.Timedelta(seconds=1))
            if i >= 25:
                leituras[nm] = leitura_andar(A[tf], i)
                leituras[nm]["ts"] = str(pd.Timestamp(A[tf].ts[i]))
                fontes[nm] = f"nativa_espelho@{pd.Timestamp(A[tf].ts[i]):%d/%m %H:%M}"
            else:
                leituras[nm] = None; fontes[nm] = "amostra_insuficiente"
        else:
            leituras[nm] = None; fontes[nm] = "AUSENTE_NA_FONTE"

    # ---- janela 10->15 (§2.1): barras de M1 DENTRO da M15 corrente ----------
    janela = dict(pos=None, aberta=False, confirmacao=None, base="1m->15m")
    if "M1" in A:
        a1 = A["M1"]
        dentro = [k for k in range(a1.n) if ts15 <= pd.Timestamp(a1.ts[k]) < fim15]
        if dentro:
            janela["pos"] = len(dentro)
            janela["aberta"] = len(dentro) >= P("N_JANELA_INI")
            if janela["aberta"]:
                le1 = leitura_andar(a1, dentro[-1])
                le5 = leituras.get("M5")
                d1 = le1["exaustao"]["degrau"]
                d5 = le5["exaustao"]["degrau"] if le5 else 0
                if d1 >= 2 and d5 >= 1:
                    janela["confirmacao"] = f"escada_M1({d1})+M5({d5})"

    # ---- estado unico (§6): sentido + profundidade da confirmacao -----------
    s15 = leituras["M15"]["dir"] if leituras["M15"] else 0
    prof = []
    for nm in ("D1", "H4", "H1", "M30", "M15"):
        le = leituras.get(nm)
        if le and s15 != 0 and le["dir"] == s15: prof.append(nm)
        else: break
    estado_unico = dict(sentido=s15,
                        texto=("LATERAL" if s15 == 0 else
                               ("ALTA" if s15 > 0 else "BAIXA") +
                               (f" confirmada de {prof[0]} ate {prof[-1]}" if prof else " so no M15")),
                        profundidade=prof, janela=janela)

    # ---- checklist itens 1-4 + reguas R1/R2/R3 (§1.1) ------------------------
    ref_d1 = leituras["D1"]["dir"] if leituras["D1"] else 0
    ref_h4 = leituras["H4"]["dir"] if leituras["H4"] else 0
    ref = "a_favor" if (s15 != 0 and ref_d1 == s15 and ref_h4 == s15) else \
          ("contra" if (s15 != 0 and (ref_d1 == -s15 or ref_h4 == -s15)) else "neutro")

    # ---- comando NARRADO (§9.9) — sem autoridade -----------------------------
    degrau15 = leituras["M15"]["exaustao"]["degrau"] if leituras["M15"] else 0
    voltou = leituras["M15"] and any("voltou_compressao" in e for e in leituras["M15"]["eventos"])
    comando = None
    if lado_posicao != 0:
        if degrau15 >= 2 and leituras["M15"]["exaustao"]["lado"] == -lado_posicao:
            comando = f"CORTE_TOTAL(narrado):reversao_{degrau15}sinal"
        elif janela.get("confirmacao"):
            comando = "CORTE_TOTAL(narrado):janela_10_15"
        elif voltou:
            comando = "CORTE_TOTAL(narrado):voltou_compressao"

    # ---- classificacao pullback x reversao (§5.5/5.6) ------------------------
    # ---- veredito-MAQUINA (decreto 19/set): a autoridade dos dois Ciclos ----
    lado_ex15 = leituras["M15"]["exaustao"]["lado"] if leituras["M15"] else 0
    apoio = [nm for nm in ("D1", "H4", "H1", "M30") if leituras.get(nm) and s15 != 0 and leituras[nm]["dir"] == s15]
    confl = [nm for nm in ("D1", "H4", "H1", "M30") if leituras.get(nm) and s15 != 0 and leituras[nm]["dir"] == -s15]
    if ref == "contra":   topdown = ("bloqueada", "item1_referencia_contra(" + "/".join([n_ for n_ in ("D1","H4") if n_ in confl] or ["D1xH4"]) + ")")
    elif ref == "a_favor": topdown = ("autorizada", "item1_referencia_a_favor(D1&H4)")
    else:                 topdown = ("neutra", "referencia_neutra")
    if degrau15 >= 2: classif = "reversao_identificada"
    elif leituras["M15"] and "respiro_esperado" in leituras["M15"]["eventos"]: classif = "pullback_presumido"
    elif degrau15 == 1: classif = "exaustao_candidata"
    else: classif = "normal"

    fichas12 = {}
    formandos = {}
    fim_agora = fim15
    for nm2, le2 in leituras.items():
        if le2:
            tfk = "Daily" if nm2 == "D1" else nm2
            fichas12[nm2] = ficha_tf(A[tfk], A[tfk].idx_ate(fim_agora - pd.Timedelta(seconds=1)), le2)
    for nm2 in ("D1", "H4", "H1", "M30", "M15"):
        tfk = "Daily" if nm2 == "D1" else nm2
        if tfk in A:
            fo = barra_formando(A, tfk, fim_agora)
            if fo: formandos[nm2] = fo
    fase = fases_propagacao(fichas12, formandos)
    # memoria + histerese (so no estado EXIBIDO; o bruto mantem a autoridade)
    # v2.2: a memoria VIVA so e ESCRITA pelo proprio vivo (gravar_mem=True);
    # provas/replay/bancada LEEM mas nunca gravam — recordacao sem contaminacao
    mem = memoria_ler(ativo)
    bruto = estado_unico["texto"].split(" confirmada")[0].split(" so no")[0]
    if bruto == mem.get("bruto"): mem["exibido_n"] = mem.get("exibido_n", 0) + 1
    else: mem["bruto"] = bruto; mem["exibido_n"] = 1
    if mem.get("exibido") is None or mem["exibido_n"] >= P("HISTERESE_BARRAS"):
        if mem.get("exibido") != bruto:
            mem.setdefault("linha_tempo", []).append([str(ts15), f"{mem.get('exibido')}->{bruto}"])
            mem["linha_tempo"] = mem["linha_tempo"][-30:]
        mem["exibido"] = bruto
    if fase["rotulo"] and (not mem.get("linha_tempo") or mem["linha_tempo"][-1][1] != fase["rotulo"]):
        mem.setdefault("linha_tempo", []).append([str(ts15), fase["rotulo"]])
        mem["linha_tempo"] = mem["linha_tempo"][-30:]
    # v2.1: MOVIMENTO com identidade (#ATV-ddmm-NN) e marcos por estado
    mv = mem.get("movimento") or {}
    if fase["direcao"] != 0:
        if mv.get("dir") != fase["direcao"]:
            seq = int(mem.get("mov_seq", 0)) + 1; mem["mov_seq"] = seq
            mv = dict(id=f"#{ativo[:3]}-{ts15:%d%m}-{seq:02d}", dir=fase["direcao"],
                      nasceu=str(ts15), marcos={})
        est = fase.get("estado", "NEUTRO")
        if est not in mv["marcos"]: mv["marcos"][est] = str(ts15)
        mem["movimento"] = mv
    elif mv:
        mv["encerrado"] = mv.get("encerrado") or str(ts15); mem["movimento"] = mv
    if gravar_mem: memoria_gravar(ativo, mem)

    ficha = {                                              # FICHA DE SAIDA §9
        "ts_barra": str(ts15),
        "1_estado_unico": estado_unico,
        "2_referencia_ciclo2": dict(D1=ref_d1, H4=ref_h4, veredito=ref,
                                    ficha_d1=ficha_d1(A["Daily"], A["Daily"].idx_ate(fim15)) if "Daily" in A else None),
        "3_pivos_por_andar": {nm: (le["pivos"]["sequencia"] if le else fontes[nm]) for nm, le in leituras.items()},
        "4_caixas": {nm: ((le["caixa"] or {}).get("estado") if le else None) for nm, le in leituras.items()},
        "5_contadores": {nm: (dict(L=le["perna"][1], D=le["afastamento"]) if le else None) for nm, le in leituras.items()},
        "6_eventos": {nm: (le["eventos"] if le else []) for nm, le in leituras.items()},
        "7_degrau_escada": {nm: (le["exaustao"]["degrau"] if le else 0) for nm, le in leituras.items()},
        "8_sinais_ao_bloco2": ("sinal_entrada_rompimento" if leituras["M15"] and
                               any("rompimento_confirmado" in e for e in leituras["M15"]["eventos"]) else
                               ("sinal_entrada_reversao" if degrau15 >= 3 else None)),
        "9_comando_narrado": comando,
        "10_blindagens": dict(B1="no_executor", B2="INEXISTENTE(calendario)", B3="no_seletor", B5="flag_no_ciclo"),
        "11_classificacao": classif,
        "12_veredito": dict(topdown=topdown, apoio=apoio, conflito=confl,
                            degrau=degrau15, lado_ex=lado_ex15,
                            janela_conf=janela.get("confirmacao"),
                            voltou=bool(voltou), classif=classif),
        "13_fichas_tf": fichas12,
        "14_formando": formandos,
        "15_fase": fase,
        "16_conclusao": conclusao_conjunta(fichas12, fase, ref, comando, lado_posicao),
        "17_memoria": dict(exibido=mem.get("exibido"), bruto=bruto, movimento=mem.get("movimento"),
                           persistencia_exibido=mem.get("exibido_n"),
                           linha_tempo=mem.get("linha_tempo", [])[-8:]),
        "fontes": fontes,
        "consumo_pelo_seletor": "hoje: contexto D1xH4 + B3/B5; ficha completa NARRADA em paralelo (ligacao plena = FONTE PENDENTE/spec)",
    }
    return ficha, leituras


# ============================================================================
#  v2.0 — FICHA DE 12 CAMPOS POR TF (fechada e formando)
# ============================================================================
def _persistencia(a, i):
    d0 = 1 if a.c[i] > a.emaH[i] else (-1 if a.c[i] < a.emaL[i] else 0)
    n = 1
    for k in range(i - 1, max(24, i - 200), -1):
        dk = 1 if a.c[k] > a.emaH[k] else (-1 if a.c[k] < a.emaL[k] else 0)
        if dk == d0: n += 1
        else:
            return d0, n, str(pd.Timestamp(a.ts[k + 1]))
    return d0, n, str(pd.Timestamp(a.ts[max(25, i - 199)]))

def ficha_tf(a, i, le=None):
    """Os 12 campos do decreto, para a barra FECHADA i do andar."""
    le = le or leitura_andar(a, i)
    piv = le["pivos"]; d, L = le["perna"]; ex = le["exaustao"]
    dir_c, pers, ts_mud = _persistencia(a, i)
    rng20h = float(max(a.h[max(0, i - 20):i + 1])); rng20l = float(min(a.l[max(0, i - 20):i + 1]))
    faixa = max(rng20h - rng20l, 1e-9); pos = (a.c[i] - rng20l) / faixa
    loc = "topo_da_faixa" if pos > 0.8 else ("fundo_da_faixa" if pos < 0.2 else "meio_da_faixa")
    if piv["resistencia"] and abs(a.c[i] - piv["resistencia"]) < 0.3 * (a.atr[i] or faixa): loc = "na_resistencia"
    if piv["suporte"] and abs(a.c[i] - piv["suporte"]) < 0.3 * (a.atr[i] or faixa): loc = "no_suporte"
    atr_med = float(np.nanmean(a.atr[max(14, i - 50):i + 1])) or 1e-9
    vol = "expansao" if a.atr[i] > 1.5 * atr_med else ("baixa" if a.atr[i] < 0.7 * atr_med else "normal")
    cx = (le["caixa"] or {}).get("estado")
    regime = "compressao" if cx in ("ativa", "voltou_compressao") else              ("tendencia" if le["dir"] != 0 and piv["sequencia"] in ("ascendente", "descendente") else "lateral")
    corpo3 = [abs(a.c[k] - a.o[k]) for k in range(max(1, i - 2), i + 1)]
    mom = "acelerando" if len(corpo3) == 3 and corpo3[2] > corpo3[1] > corpo3[0] else           ("enfraquecendo" if len(corpo3) == 3 and corpo3[2] < corpo3[1] < corpo3[0] else "estavel")
    # forca 0-100 [REF]: |D| (ate 40) + perna L (ate 30) + estrutura alinhada (30)
    f_d = min(abs(le["afastamento"]) / 2.0, 1.0) * 40
    f_l = min(L / 10.0, 1.0) * 30
    alin = 30 if (le["dir"] == 1 and piv["sequencia"] == "ascendente") or                  (le["dir"] == -1 and piv["sequencia"] == "descendente") else 0
    forca = int(f_d + f_l + alin)
    # confianca 0-100 [REF]: persistencia + regime batendo com direcao + evento a favor
    conf = min(pers / 8.0, 1.0) * 50 + (25 if regime == "tendencia" and le["dir"] != 0 else 0) +            (25 if any("rompimento_confirmado" in e for e in le["eventos"]) else 0)
    ev = le["eventos"][0] if le["eventos"] else "-"
    return dict(estrutura=piv["sequencia"], regime=regime,
                direcao={1: "alta", -1: "baixa", 0: "neutra"}[le["dir"]],
                forca=forca, momentum=mom, localizacao=loc, volatilidade=vol,
                evento=ev, estado_barra="FECHADA", confianca=int(conf),
                ultima_mudanca=ts_mud, persistencia=pers,
                degrau=ex["degrau"], eventos=le["eventos"])

def barra_formando(A, tf, fim_ts):
    """A barra PARCIAL do TF alto, lida pelas barras de M1 dentro dela.
    Reagir antes SEM inventar confirmacao (rotulo sempre FORMANDO)."""
    if "M1" not in A or tf == "M1": return None
    a1 = A["M1"]; mins = MIN15[tf]
    ini = pd.Timestamp(fim_ts).floor(f"{mins}min")
    ks = [k for k in range(a1.n) if ini <= pd.Timestamp(a1.ts[k]) < ini + pd.Timedelta(minutes=mins)]
    if len(ks) < 2: return None
    o = a1.o[ks[0]]; c = a1.c[ks[-1]]
    h = float(max(a1.h[ks])); l = float(min(a1.l[ks]))
    press = sum(1 for k in ks if a1.c[k] < a1.o[k]) / len(ks)
    dcorpo = 1 if c > o else (-1 if c < o else 0)
    return dict(estado_barra="FORMANDO", completude=f"{len(ks)}/{mins}m",
                corpo={1: "comprador", -1: "vendedor", 0: "doji"}[dcorpo],
                pressao_vendedora=round(press, 2), o=round(float(o), 2), h=round(h, 2),
                l=round(l, 2), c=round(float(c), 2))

# ============================================================================
#  v2.0 — MAQUINA DE FASES DA PROPAGACAO + MEMORIA + CONCLUSAO CONJUNTA
# ============================================================================
def _dir_ou0(fx): return {"alta": 1, "baixa": -1, "neutra": 0}[fx["direcao"]] if fx else 0

def fases_propagacao(fichas, formandos):
    """As 5 fases do decreto, por direcao candidata (queda e alta, espelho)."""
    def lado(sinal):
        # v2.3: PISO DE EVIDENCIA — direcao so conta se conf>=PISO e pers>=PISO_PERS
        # (correcao da auditoria: H1 conf=6/pers=1 promovia fase 3 por alinhamento cru)
        def dv(nm):
            fx = fichas.get(nm)
            if not fx: return 0
            if fx["confianca"] < P("PISO_CONF_FASE") or fx["persistencia"] < P("PISO_PERS_FASE"): return 0
            return _dir_ou0(fx)
        d = {nm: dv(nm) for nm in fichas}
        qb = lambda nm: fichas.get(nm) and any(
            ("quebra_estrutura_baixa" if sinal < 0 else "quebra_estrutura_alta") in e
            for e in fichas[nm]["eventos"])
        f_h4 = formandos.get("H4") or {}
        f_d1 = formandos.get("D1") or {}
        press_h4 = (f_h4.get("pressao_vendedora", 0.5) > 0.6) if sinal < 0 else                    (f_h4.get("pressao_vendedora", 0.5) < 0.4)
        press_d1 = (f_d1.get("corpo") == ("vendedor" if sinal < 0 else "comprador"))
        fase = 0
        if d.get("M1") == sinal and d.get("M5") == sinal and d.get("M15", 0) != sinal: fase = 1
        if d.get("M5") == sinal and (d.get("M15") == sinal or qb("M15")): fase = 2
        if d.get("M15") == sinal and d.get("M30") == sinal and d.get("H1") == sinal: fase = 3
        if fase >= 3 and (press_h4 or d.get("H4") == sinal): fase = 4
        if fase >= 4 and press_d1 and (qb("D1") or d.get("D1") == sinal): fase = 5
        rot = {0: None,
               1: ("ALERTA_DE_QUEDA" if sinal < 0 else "ALERTA_DE_ALTA") + " — confianca baixa",
               2: ("QUEDA_EM_PROPAGACAO" if sinal < 0 else "ALTA_EM_PROPAGACAO") + " — confianca media",
               3: ("MOVIMENTO_VENDEDOR" if sinal < 0 else "MOVIMENTO_COMPRADOR") + " CONFIRMADO — confianca alta",
               4: ("H4_FORMANDO_QUEDA" if sinal < 0 else "H4_FORMANDO_ALTA") + " — continuidade provavel",
               5: ("D1_FORMANDO_QUEDA" if sinal < 0 else "D1_FORMANDO_ALTA")}[fase]
        return fase, rot
    fq, rq = lado(-1); fa, ra = lado(+1)
    out = dict(direcao=0, fase=0, rotulo=None)
    if fq >= fa and fq > 0: out = dict(direcao=-1, fase=fq, rotulo=rq)
    elif fa > 0: out = dict(direcao=+1, fase=fa, rotulo=ra)
    # v2.1: estado nomeado dos 10 (granular, pela profundidade real)
    d = {nm: _dir_ou0(fx) for nm, fx in fichas.items() if fx}
    sg = out["direcao"]
    est = "NEUTRO"
    if sg != 0:
        if d.get("M1") == sg: est = "ALERTA_M1"
        if d.get("M5") == sg: est = "CONFIRMADO_M5"
        if d.get("M15") == sg: est = "CONFIRMADO_M15"
        if d.get("M30") == sg: est = "PROPAGANDO_M30"
        if d.get("H1") == sg: est = "CONTROLE_H1"
        if out["fase"] >= 4: est = "FORMANDO_H4"
        if out["fase"] >= 5: est = "FORMANDO_D1"
        if d.get("D1") == sg and d.get("H4") == sg and out["fase"] >= 3: est = "TENDENCIA_CONFIRMADA"
        f15 = fichas.get("M15") or {}
        if f15.get("degrau", 0) >= 2: est = "EXAUSTAO_OU_REVERSAO"
    out["estado"] = est
    out["evidencia"] = {nm: f"c{fichas[nm]['confianca']}/p{fichas[nm]['persistencia']}"
                        for nm in ("M1", "M5", "M15", "M30", "H1", "H4", "D1") if fichas.get(nm)}
    out["piso"] = f"conf>={P('PISO_CONF_FASE')} pers>={P('PISO_PERS_FASE')} [REF]"
    return out

def _mem_cam(ativo): return f"vivo_ciclo_mem_{ativo}.json"

SESSAO = None                      # o VIVO carimba no boot; provas nunca

def memoria_ler(ativo):
    import json
    try:
        m = json.load(open(_mem_cam(ativo), encoding="utf-8"))
        if m.get("mem_v") != MEM_FORMATO:
            return dict(mem_v=MEM_FORMATO, exibido=None, exibido_n=0, bruto=None, linha_tempo=[],
                        aviso="VERSAO_INCOMPATIVEL(formato antigo descartado)")
        return m
    except Exception:
        return dict(mem_v=MEM_FORMATO, exibido=None, exibido_n=0, bruto=None, linha_tempo=[])

def memoria_gravar(ativo, mem):
    """v2.3: escrita ATOMICA (tmp+replace) + trava simples + versao + sessao."""
    import json
    mem["mem_v"] = MEM_FORMATO
    if SESSAO: mem["sessao"] = SESSAO
    cam = _mem_cam(ativo); lock = cam + ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return                                       # outro processo escrevendo: pula (vivo re-grava na proxima)
    try:
        tmp = cam + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(mem, f)
        os.replace(tmp, cam)
    except Exception: pass
    finally:
        os.close(fd)
        try: os.remove(lock)
        except Exception: pass

def memoria_hash(ativo):
    import hashlib
    try: return hashlib.sha256(open(_mem_cam(ativo), "rb").read()).hexdigest()[:16]
    except Exception: return "SEM_ARQUIVO"

def classificar_contrario(fichas, lado_mov):
    """v2.1 — pullback x reversao pela PROFUNDIDADE do avanco contrario (decreto)."""
    d = {nm: _dir_ou0(fx) for nm, fx in fichas.items() if fx}
    c = -lado_mov
    prof = [nm for nm in ("M1", "M5", "M15", "M30", "H1") if d.get(nm) == c]
    qb15 = fichas.get("M15") and any("quebra_estrutura" in e for e in fichas["M15"]["eventos"])
    if not prof: return "sem_contrario", prof
    if set(prof) <= {"M1"}: return "ruido(M1 sozinho)", prof
    if set(prof) <= {"M1", "M5"} and not qb15: return "pullback(M1+M5, M15 integro)", prof
    if "M15" in prof and "M30" not in prof: return "reversao_em_desenvolvimento(M15 rompeu)", prof
    if "M30" in prof and "H1" not in prof: return "reversao_em_desenvolvimento(M30 acompanhando)", prof
    if "H1" in prof: return "reversao_CONFIRMADA(H1 nova estrutura)", prof
    return "deterioracao", prof

def conclusao_conjunta(fichas, fase, ref, comando, lado_posicao=0):
    """v2.1 — o encontro dos Ciclos no formato do decreto: sem soma de votos;
    camadas com funcoes; CONTRATENDENCIA explicita; escada de manutencao."""
    d = {nm: _dir_ou0(fx) for nm, fx in fichas.items() if fx}
    conflitos = []
    for a_, b_ in (("D1", "M15"), ("H4", "M15"), ("H1", "M15"), ("M30", "M15")):
        if d.get(a_) and d.get(b_) and d[a_] == -d[b_]:
            conflitos.append(f"{a_}({CAMADA[a_]})x{b_}")
    ctx_dir = d.get("D1", 0) + d.get("H4", 0)          # territorio
    sg = fase["direcao"]
    contraT = sg != 0 and ctx_dir != 0 and np.sign(ctx_dir) == -sg
    # CICLO 2 (territorio e forca)
    f_d1 = (fichas.get("D1") or {}).get("forca", 0); f_h4 = (fichas.get("H4") or {}).get("forca", 0)
    mom_ctx = (fichas.get("H4") or {}).get("momentum", "estavel")
    c2 = f"contexto {'comprador' if ctx_dir > 0 else 'vendedor' if ctx_dir < 0 else 'neutro'}" +          (", porem perdendo forca" if mom_ctx == "enfraquecendo" else f", forca D1={f_d1} H4={f_h4}")
    # CICLO 1 (o que nasce e ate onde propagou)
    prop = [nm for nm in ("M1", "M5", "M15", "M30", "H1") if d.get(nm) == sg] if sg else []
    c1 = (f"{'queda' if sg < 0 else 'alta'} propagada de {prop[0]} ate {prop[-1]}" if prop else "nada nascendo")
    # classificacao do contrario ao CONTEXTO (pullback x reversao)
    classif_ctx, prof = classificar_contrario(fichas, int(np.sign(ctx_dir))) if ctx_dir else ("sem_contexto", [])
    # manutencao (posicao aberta): a escada do decreto
    manut = None
    if lado_posicao != 0:
        rot, profp = classificar_contrario(fichas, lado_posicao)
        if comando: manut = f"CORTAR ({comando})"
        elif "reversao_CONFIRMADA" in rot or "M30" in str(profp): manut = f"PROTEGER/CORTAR se M15-M30 confirmarem · {rot}"
        elif "reversao_em_desenvolvimento" in rot: manut = f"PROTEGER · {rot}"
        elif "pullback" in rot: manut = f"MANTER (pullback) · {rot}"
        else: manut = f"MANTER · {rot}"
    # decisao final
    if comando: dec = "CORTAR"
    elif sg != 0 and not contraT and fase["fase"] >= 2 and ref != "contra": dec = f"OPERAR_A_FAVOR({'venda' if sg<0 else 'compra'})"
    elif contraT and fase["fase"] >= 3: dec = f"CONTRATENDENCIA({'venda' if sg<0 else 'compra'}) · risco reduzido x{P('RISCO_CONTRA_MULT')} · alvo curto"
    elif contraT: dec = f"NAO_OPERAR_CONTRA (fase {fase['fase']}<3 — queda no M1 nao e reversao)"
    elif conflitos: dec = "AGUARDAR(conflito de camadas)"
    else: dec = "AGUARDAR"
    return dict(ciclo2=c2, ciclo1=c1, classificacao=classif_ctx, decisao=dec,
                conflitos=conflitos, contratendencia=bool(contraT and fase["fase"] >= 3), manutencao=manut)

# ---- influencia narrada por TF (a tabela do dono) ---------------------------
_INFL = {"D1": "contexto principal (referencia)", "H4": "confirma a referencia",
         "H1": "confirmacao descendo (narrada)", "M30": "confirmacao descendo (narrada)",
         "M15": "DECISAO (quadro completo)", "M5": "julga a janela (narrado)",
         "M1": "sensor/gatilho da janela (narrado)"}

def tabela(ficha, leituras):
    ln = []
    for nm in ("D1", "H4", "H1", "M30", "M15", "M5", "M1"):
        le = leituras.get(nm)
        if le is None:
            ln.append((nm, "-", ficha["fontes"].get(nm, "?"), _INFL[nm], "-")); continue
        txt = {1: "ALTA", -1: "BAIXA", 0: "lateral"}[le["dir"]]
        ev = ",".join(le["eventos"][:3]) or "-"
        ln.append((nm, le.get("ts", "?")[5:16], f"{txt} L={le['perna'][1]} D={le['afastamento']}", _INFL[nm], ev))
    v = ficha["12_veredito"]
    if ficha["9_comando_narrado"]: res = f"{ficha['9_comando_narrado']} · REGRA: ciclo_bottomup"
    elif v["topdown"][0] == "bloqueada": res = f"entrada_bloqueada · REGRA: {v['topdown'][1]}"
    elif ficha["8_sinais_ao_bloco2"]: res = f"{ficha['8_sinais_ao_bloco2']} · REGRA: {v['topdown'][1]}"
    else: res = f"{'entrada_autorizada' if v['topdown'][0]=='autorizada' else 'neutro'} · REGRA: {v['topdown'][1]}"
    return ln, res


def gravar_ficha(ativo, ficha, pasta="."):
    cam = os.path.join(pasta, f"vivo_ficha_{ativo}.csv")
    novo = not os.path.exists(cam)
    import csv
    with open(cam, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["ts_barra", "estado_unico", "referencia", "janela", "degraus",
                        "eventos_M15", "eventos_M5", "eventos_M1", "sinal_b2",
                        "comando_narrado", "classificacao", "fontes", "cv1"])
        w.writerow([ficha["ts_barra"], ficha["1_estado_unico"]["texto"],
                    ficha["2_referencia_ciclo2"]["veredito"],
                    str(ficha["1_estado_unico"]["janela"]), str(ficha["7_degrau_escada"]),
                    "|".join(ficha["6_eventos"].get("M15", [])),
                    "|".join(ficha["6_eventos"].get("M5", [])),
                    "|".join(ficha["6_eventos"].get("M1", [])),
                    ficha["8_sinais_ao_bloco2"], ficha["9_comando_narrado"],
                    ficha["11_classificacao"], str(ficha["fontes"]), CV1_VERSAO])


def prova(pasta, ativo, n_barras=6, lado_posicao=0):
    """--ciclo-prova: a tabela do dono, barra a barra, saindo da maquina."""
    A = carregar_andares(pasta, ativo)
    if "M15" not in A: raise RuntimeError("espelho sem M15")
    print(f"CICLO-PROVA v{CV1_VERSAO} — {ativo} · fontes: " +
          ", ".join(f"{NOME.get(tf,tf)}={'OK' if tf in A else 'AUSENTE'}" for tf in ANDARES))
    print("  parametros §11: TODOS [REF]/nao medidos (medidor = proximo instrumento)")
    n15 = A["M15"].n
    for k in range(max(25, n15 - n_barras), n15):
        ts = pd.Timestamp(A["M15"].ts[k])
        ficha, leit = avaliar(pasta, ativo, ts_m15=ts, lado_posicao=lado_posicao, andares=A)
        ln, res = tabela(ficha, leit)
        print(f"\n═ {ativo} · barra {ts:%d/%m %H:%M} · {ficha['1_estado_unico']['texto']} · "
              f"ref {ficha['2_referencia_ciclo2']['veredito']} · classif {ficha['11_classificacao']}")
        for nm, ts_, le, infl, ev in ln:
            print(f"  {nm:<4} {ts_:<12} {le:<26} {infl:<34} {ev}")
        v = ficha["12_veredito"]
        print(f"  apoio: {v['apoio'] or '-'} · conflito: {v['conflito'] or '-'}")
        print(f"  janela: {ficha['1_estado_unico']['janela']}")
        print(f"  RESULTADO: {res}" + (f" · comando {ficha['9_comando_narrado']}" if ficha['9_comando_narrado'] else ""))
    print("\n  (comando_narrado NUNCA executa — autoridade so apos medicao e carimbo)")


def prova_tf(pasta, ativo, n=6):
    """v1.3 (decreto 19/set): os SETE timeframes SEPARADOS — cada andar com
    as proprias barras, horarios, reguas e eventos (nada consolidado) — e a
    escada M1->M5->M15 mostrada barra de M1 por barra de M1 dentro da M15
    corrente, com horario de cada transicao. Compare com o grafico real:
    os timestamps sao os do servidor."""
    A = carregar_andares(pasta, ativo)
    print(f"PROVA POR TIMEFRAME v{CV1_VERSAO} — {ativo}")
    print("  fontes: " + " ".join(f"{NOME.get(tf,tf)}={'OK('+str(A[tf].n)+'b)' if tf in A else 'AUSENTE'}"
                                  for tf in ANDARES))
    txt = {1: "ALTA", -1: "BAIXA", 0: "lateral"}
    for tf in ("Daily", "H4", "H1", "M30", "M15", "M5", "M1"):
        nm = NOME.get(tf, tf)
        a = A.get(tf)
        if a is None:
            print(f"\n── {nm}: AUSENTE_NA_FONTE"); continue
        print(f"\n── {nm} · {a.n} barras na fonte · ultimas {n} barras DESTE andar:")
        for i in range(max(25, a.n - n), a.n):
            le = leitura_andar(a, i)
            cx = (le["caixa"] or {}).get("estado", "-")
            print(f"   {pd.Timestamp(a.ts[i]):%d/%m %H:%M} · {txt[le['dir']]:<7} "
                  f"L={le['perna'][1]:<3} D={le['afastamento']:<5} caixa={cx:<18} "
                  f"degrau={le['exaustao']['degrau']} · {','.join(le['eventos'][:3]) or '-'}")
    # escada de baixo pra cima: cada M1 dentro da M15 corrente, com horario
    if "M1" in A and "M15" in A:
        a1, a15 = A["M1"], A["M15"]
        i15 = a15.n - 1
        ts15 = pd.Timestamp(a15.ts[i15]); fim15 = ts15 + pd.Timedelta(minutes=15)
        dentro = [k for k in range(a1.n) if ts15 <= pd.Timestamp(a1.ts[k]) < fim15]
        print(f"\n── ESCADA M1->M5->M15 · barra M15 corrente {ts15:%d/%m %H:%M} · "
              f"{len(dentro)} barras de M1 fechadas dentro dela:")
        a5 = A.get("M5")
        for pos, k in enumerate(dentro, 1):
            le1 = leitura_andar(a1, k)
            m5txt = "-"
            if a5 is not None:
                j5 = a5.idx_ate(pd.Timestamp(a1.ts[k]))
                if j5 >= 25:
                    le5 = leitura_andar(a5, j5)
                    m5txt = f"{txt[le5['dir']]},deg{le5['exaustao']['degrau']}"
            marc = " <= JANELA ABERTA" if pos >= P("N_JANELA_INI") else ""
            conf = ""
            if pos >= P("N_JANELA_INI") and le1["exaustao"]["degrau"] >= 2:
                conf = " ** CONFIRMACAO (M1 degrau>=2) **"
            print(f"   M1 #{pos:02d} {pd.Timestamp(a1.ts[k]):%H:%M} · {txt[le1['dir']]:<7} "
                  f"deg={le1['exaustao']['degrau']} · {','.join(le1['eventos'][:2]) or '-'} · "
                  f"M5@mesmo_instante: {m5txt}{marc}{conf}")
        print("   (a janela abre na barra 10; confirmacao = degrau>=2 no M1 com M5 em gatilho)")

def prova_fases(pasta, ativo, n=4):
    """v2.0: a fotografia completa — 12 campos por TF (fechada+formando),
    camadas, conflitos, fase da propagacao, conclusao conjunta, memoria."""
    A = carregar_andares(pasta, ativo)
    a15 = A["M15"]
    for k in range(max(25, a15.n - n), a15.n):
        ts = pd.Timestamp(a15.ts[k])
        fic, leit = avaliar(pasta, ativo, ts_m15=ts, andares=A)
        fs = fic["15_fase"]
        print(f"\n═══ {ativo} · {ts:%d/%m %H:%M} · ESTADO {fs.get('estado','NEUTRO')} (fase {fs['fase']})"
              + (f" · {fs['rotulo']}" if fs['rotulo'] else ""))
        print("CONTEXTO:")
        for nm in ("D1", "H4", "H1", "M30", "M15", "M5", "M1"):
            fx = fic["13_fichas_tf"].get(nm)
            if not fx: continue
            extra = fx["momentum"] if fx["momentum"] != "estavel" else fx["evento"]
            print(f"  {nm}: {fx['direcao']} {fx['regime']} | forca {fx['forca']} conf {fx['confianca']} | "
                  f"pers {fx['persistencia']} | {fx['localizacao']} | {extra}")
            fo = fic["14_formando"].get(nm)
            if fo: print(f"      FORMANDO {fo['completude']} corpo={fo['corpo']} pressao_vend={fo['pressao_vendedora']}")
        cc = fic["16_conclusao"]
        print(f"CICLO 2: {cc['ciclo2']}")
        print(f"CICLO 1: {cc['ciclo1']}")
        print(f"CLASSIFICACAO: {cc['classificacao']}" + (f" · conflitos {cc['conflitos']}" if cc['conflitos'] else ""))
        print(f"DECISAO: {cc['decisao']}" + (f" · manutencao: {cc['manutencao']}" if cc['manutencao'] else ""))
        mv = fic["17_memoria"].get("movimento")
        if mv:
            print(f"MOVIMENTO {mv['id']} (nasceu {mv['nasceu'][11:16]}):")
            for est, tm in mv["marcos"].items(): print(f"  {tm[11:16]} {est}")

def prova_propagacao(pasta, ativo, n_barras=96):
    """v2.0: o FILME — so as transicoes de fase/estado das ultimas N barras."""
    A = carregar_andares(pasta, ativo)
    a15 = A["M15"]
    ult = None
    print(f"PROPAGACAO — {ativo} · ultimas {n_barras} barras M15 · so transicoes:")
    for k in range(max(25, a15.n - n_barras), a15.n):
        ts = pd.Timestamp(a15.ts[k])
        fic, _ = avaliar(pasta, ativo, ts_m15=ts, andares=A)
        chave = (fic["15_fase"]["fase"], fic["15_fase"]["rotulo"], fic["17_memoria"]["exibido"])
        if chave != ult:
            print(f"  {ts:%d/%m %H:%M} · fase {chave[0]} · {chave[1] or '-'} · exibido={chave[2]}")
            ult = chave

def prova_memoria(pasta, ativo):
    """v2.3: PROVA DE ISOLAMENTO — hash da memoria viva antes e depois de
    replays (fases+propagacao+avaliacoes soltas). Identico = isolada."""
    h0 = memoria_hash(ativo)
    A = carregar_andares(pasta, ativo)
    for k in range(max(25, A["M15"].n - 12), A["M15"].n):
        avaliar(pasta, ativo, ts_m15=pd.Timestamp(A["M15"].ts[k]), andares=A)
    prova_propagacao(pasta, ativo, 12)
    h1 = memoria_hash(ativo)
    print(f"\nPROVA DE ISOLAMENTO DA MEMORIA — {ativo}")
    print(f"  hash antes : {h0}\n  hash depois: {h1}")
    print(f"  VEREDITO: {'MEMORIA ISOLADA (byte-identica)' if h0 == h1 else '>>> MEMORIA_CONTAMINADA <<<'}")
    return h0 == h1

def prova_falsos_fase(pasta, ativo, n=300):
    """v2.3: quantos fase>=3 o historico do espelho produz e quantos sao
    FALSOS (preco nao continua na direcao em 8 barras) — com e sem piso."""
    A = carregar_andares(pasta, ativo)
    a15 = A["M15"]
    piso0 = PARAMS["PISO_CONF_FASE"]["v"]
    for rot, piso in (("SEM piso (como estava)", 0), (f"COM piso conf>={piso0} [REF]", piso0)):
        PARAMS["PISO_CONF_FASE"]["v"] = piso
        tot = fal = 0; ult_fase = 0
        for k in range(max(25, a15.n - n), a15.n - 8):
            fic, _ = avaliar(pasta, ativo, ts_m15=pd.Timestamp(a15.ts[k]), andares=A)
            f = fic["15_fase"]
            if f["fase"] >= 3 and ult_fase < 3:
                tot += 1
                cont = np.sign(a15.c[k + 8] - a15.c[k]) == f["direcao"]
                fal += 0 if cont else 1
            ult_fase = f["fase"]
        print(f"  {rot}: eventos fase>=3 = {tot} · FALSOS (sem continuacao 8b) = {fal}"
              + (f" ({100.0*fal/tot:.0f}%)" if tot else ""))
    PARAMS["PISO_CONF_FASE"]["v"] = piso0
    print("  (amostra = profundidade do espelho; medicao funda = professor, proxima leva)")

def relatorio_escada(pasta, ativo, n=6):
    """v2.4 — RELATORIO DE ESCADA (formato do dono, 20/set): para cada barra
    M15, TODAS as menores que a formaram — o que o M1 falou, o que o M5
    confirmou ou negou, a trajetoria ate o M15, a propagacao em minutos,
    a classificacao e o resultado. Sequencias que FALHAM sao registradas
    (M1 iniciou -> M5 nao confirmou -> CANCELADO) — a materia-prima dos
    falsos alertas. Le o espelho; NAO grava memoria."""
    A = carregar_andares(pasta, ativo)
    a15, a5, a1 = A["M15"], A["M5"], A["M1"]
    seqs = dict(completa=0, cancel_m5=0, cancel_m15=0, sem_alerta=0)
    print(f"RELATORIO DE ESCADA — {ativo} · ultimas {n} barras M15 · CV1 v{CV1_VERSAO}")
    for k in range(a15.n - n, a15.n):
        t0 = pd.Timestamp(a15.ts[k]); t1 = t0 + pd.Timedelta(minutes=15)
        fic, _ = avaliar(pasta, ativo, ts_m15=t0, andares=A)
        c15, o15 = a15.c[k], a15.o[k]
        d15 = 1 if c15 > o15 else (-1 if c15 < o15 else 0)
        rot15 = {1: "alta", -1: "baixa", 0: "neutra"}[d15]
        print(f"\n═ M15 {t0:%H:%M}–{t1:%H:%M}  (fechou {rot15})")
        # ---- M1: a historia barra a barra ----
        i1 = [i for i in range(a1.n) if t0 <= pd.Timestamp(a1.ts[i]) < t1]
        rng_med = float(np.mean(a1.h[max(0,(i1[0] if i1 else 0)-20):(i1[0] if i1 else 1)] -
                                a1.l[max(0,(i1[0] if i1 else 0)-20):(i1[0] if i1 else 1)])) or 1e-9
        alerta_dir = 0; t_alerta = None; acum = 0
        print("  M1:")
        for i in i1:
            c, o, h, l = a1.c[i], a1.o[i], a1.h[i], a1.l[i]
            d = 1 if c > o else (-1 if c < o else 0)
            acum = acum + 1 if d == alerta_dir and alerta_dir != 0 else acum
            tags = []
            if alerta_dir == 0 and d != 0:
                lb = min(i, 15)
                if d == 1 and c > float(np.max(a1.h[i-lb:i])): tags.append("ALERTA de alta (quebrou extremo)")
                if d == -1 and c < float(np.min(a1.l[i-lb:i])): tags.append("ALERTA de baixa (quebrou extremo)")
                if tags: alerta_dir = d; t_alerta = pd.Timestamp(a1.ts[i]); acum = 1
            elif alerta_dir != 0:
                if d == alerta_dir: tags.append(f"{'alta' if d==1 else 'baixa'} mantida ({acum})")
                elif d == -alerta_dir: tags.append("contra")
            if (h - l) >= 1.5 * rng_med: tags.append("expansao")
            if tags: print(f"    {pd.Timestamp(a1.ts[i]):%H:%M} {' · '.join(tags)}")
        if alerta_dir == 0:
            print("    (nenhum alerta iniciado no M1)"); seqs["sem_alerta"] += 1
        # ---- M5: confirmacoes da mesma historia ----
        i5 = [i for i in range(a5.n) if t0 <= pd.Timestamp(a5.ts[i]) < t1]
        conf5 = 0; neg5 = False
        print("  M5:")
        if alerta_dir == 0:
            print(f"    ({len(i5)} barras — sem historia do M1 para confirmar)")
            i5 = []
        for j, i in enumerate(i5, 1):
            d5 = 1 if a5.c[i] > a5.o[i] else (-1 if a5.c[i] < a5.o[i] else 0)
            tf = pd.Timestamp(a5.ts[i]) + pd.Timedelta(minutes=5)
            if alerta_dir != 0 and d5 == alerta_dir:
                conf5 += 1; print(f"    {tf:%H:%M} {j}a confirmacao ({'alta' if d5==1 else 'baixa'})")
            elif alerta_dir != 0 and d5 == -alerta_dir:
                neg5 = True; print(f"    {tf:%H:%M} NAO confirmou (fechou contra)")
            else:
                print(f"    {tf:%H:%M} neutra")
        # ---- M15: veredito + propagacao ----
        _evl = (fic.get("6_eventos") or {}).get("M15") or []
        ev15 = "|".join(_evl) if isinstance(_evl, list) else str(_evl)
        cla = fic.get("11_classificacao") or ""
        f15 = (fic.get("13_fichas_tf") or {}).get("M15") or {}
        if not cla: cla = f"{f15.get('2_regime','')} {f15.get('8_evento','')}".strip()
        dec = (fic.get("16_conclusao") or {}).get("decisao", "")
        print(f"  M15:\n    {t1:%H:%M} fechamento {rot15}" + (f" · {ev15}" if ev15 else ""))
        if alerta_dir != 0 and conf5 >= 1 and not neg5 and d15 == alerta_dir:
            mins = int((t1 - t_alerta).total_seconds() // 60); seqs["completa"] += 1
            print(f"  Propagacao: M1 -> M5({conf5}x) -> M15 em {mins} min")
        elif alerta_dir != 0 and (neg5 or conf5 == 0):
            seqs["cancel_m5"] += 1
            print(f"  Propagacao: M1 iniciou ({t_alerta:%H:%M}) -> M5 NAO confirmou -> movimento CANCELADO (falso alerta M1)")
        elif alerta_dir != 0:
            seqs["cancel_m15"] += 1
            print(f"  Propagacao: M1 -> M5({conf5}x) -> M15 fechou {rot15} = NAO replicou (falso M5)")
        print(f"  Classificacao: {cla or '-'}")
        print(f"  Resultado (percepcao): {dec or 'sem decisao'}")
    tot = sum(seqs.values())
    print(f"\nPLACAR DAS SEQUENCIAS ({tot} barras): completas M1->M5->M15 = {seqs['completa']} · "
          f"canceladas no M5 (falso alerta M1) = {seqs['cancel_m5']} · "
          f"nao replicadas no M15 (falso M5) = {seqs['cancel_m15']} · sem alerta = {seqs['sem_alerta']}")
    print("(regua dos rotulos [REF]: alerta = quebra do extremo de 15 M1; confirmacao = M5 fechado na direcao — professor calibra)")

if __name__ == "__main__":
    pasta = sys.argv[1] if len(sys.argv) > 1 else "Espelho_vivo"
    atv = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    prova(pasta, atv, n)
