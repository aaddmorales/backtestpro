"""leitura-canal-0.1 (ORDEM 049) — leitura PROGRAMADA (não é modelo treinado) do canal EMA20 High/Low junto com a estrutura (suporte/resistência).
Por barra FECHADA do timeframe do piloto (XAUUSD M30, BTCUSD M15), só com dados disponíveis no fechamento dessa barra:
  posição no canal · inclinação de cada média (ATR/barra) · largura (ATR) e evolução · distâncias (preço e ATR) às médias e aos níveis ·
  eventos (toque, fechamento além, fechamento de volta) · relação nível × canal · espaço até o próximo nível · concordância canal × estrutura.
Estrutura = memória estrutura-0.1 (O39) com elegibilidade da janela de 200 barras (O40) — a MESMA dos pilotos (reaproveitada, não duplicada).
Prioridade: o canal NUNCA substitui o rompimento de um suporte/resistência no caminho; nenhum veto, gatilho, stop ou saída é alterado aqui.
Pontuações 0–100% = grau de atendimento de critérios documentados (abaixo), NÃO probabilidade de acerto. Valores marcados [P] são propostas do Claude."""
import numpy as np, pandas as pd
import estrutura_o39 as ES, janela_o40 as JN, romp_m15 as RM
VERSAO = "leitura-canal-0.1 (ORDEM 049)"
SPAN = 20; MIN_HIST = 60                      # [P] barras mínimas para EMA20/ATR14 estáveis; abaixo disso → "histórico insuficiente"
PLANO_ATR = 0.03                              # [P] |inclinação| < 0,03 ATR/barra = plana
EVOL_BARRAS, EVOL_ATR = 5, 0.15               # [P] largura muda > 0,15 ATR em 5 barras = abrindo/fechando
COMPRESSAO_ESTREITO, COMPRESSAO_LARGO = 1.0, 2.0   # [P] largura ≤ 1 ATR → 100%; ≥ 2 ATR → 0% (linear entre)
OBST_ATR = 1.0                                # [P] nível elegível a ≤ 1 ATR à frente = "no caminho"


def _dir(x):
    if not np.isfinite(x): return None
    return "subindo" if x >= PLANO_ATR else ("caindo" if x <= -PLANO_ATR else "plana")


def emas(h, l):
    return (pd.Series(h).ewm(span=SPAN, adjust=False).mean().values, pd.Series(l).ewm(span=SPAN, adjust=False).mean().values)


class LeitorCanal:
    """incremental: chame barra(df) com o DataFrame das barras FECHADAS (t,o,h,l,c) a cada fechamento; mantém a memória estrutural."""
    def __init__(self, ativo, tf):
        self.ativo, self.tf = ativo, tf; self.mem = ES.Memoria(ativo, tf, 0.01); self.ult_t = None

    def _alimentar(self, d):
        ts = d.t.values
        ini = 0 if self.ult_t is None else int(np.searchsorted(ts, np.datetime64(self.ult_t), side="right"))
        dur = pd.Timedelta(minutes={"M15": 15, "M30": 30, "H1": 60}.get(self.tf, 15))
        for i in range(ini, len(d)):
            self.mem.nova_barra(str(d.t.iloc[i]), str(d.t.iloc[i] + dur), float(d.o.iloc[i]), float(d.h.iloc[i]), float(d.l.iloc[i]), float(d.c.iloc[i]))
        self.ult_t = d.t.iloc[-1]

    def barra(self, d):
        """d: barras fechadas até a barra que acabou de fechar (inclusive). Devolve a leitura do instante (dict JSON-serializável)."""
        self._alimentar(d); h, l, c, o = (d[k].values.astype(float) for k in "hlco"); A = RM.atr_wilder(d.h, d.l, d.c); eH, eL = emas(h, l)
        return self.ler(d.t.values, o, h, l, c, A, eH, eL, len(d) - 1)

    def alimentar_uma(self, t, dur_min, o, h, l, c):
        """replay: alimenta a memória com UMA barra fechada (mesma ordem do incremental)."""
        self.mem.nova_barra(str(pd.Timestamp(t)), str(pd.Timestamp(t) + pd.Timedelta(minutes=dur_min)), float(o), float(h), float(l), float(c)); self.ult_t = pd.Timestamp(t)

    def ler(self, T, o, h, l, c, A, eH, eL, i):
        """leitura no fechamento da barra i com séries já calculadas (só índices ≤ i são usados) e memória alimentada até i."""
        n = i + 1; t_i = pd.Timestamp(T[i])
        base = {"versao": VERSAO, "ativo": self.ativo, "tf": self.tf, "barra": str(t_i), "barras_usadas": n,
                "dados_recebidos": {"o": o[i], "h": h[i], "l": l[i], "c": c[i]}, "origem": "cálculo programado (não é saída de modelo treinado)"}
        if n < MIN_HIST or not np.isfinite(A[i]) or A[i] <= 0:
            return {**base, "disponivel": False, "ausencia": f"histórico insuficiente ({n} barras < {MIN_HIST}) ou ATR indisponível"}
        a = float(A[i]); ci, ch, cl = c[i], h[i], l[i]; cp = c[i - 1]
        pos = "acima da EMA20 High" if ci > eH[i] else ("abaixo da EMA20 Low" if ci < eL[i] else "dentro do canal")
        iH, iL = (eH[i] - eH[i - 1]) / a, (eL[i] - eL[i - 1]) / a
        larg = (eH[i] - eL[i]) / a; larg5 = (eH[i - EVOL_BARRAS] - eL[i - EVOL_BARRAS]) / A[i - EVOL_BARRAS] if np.isfinite(A[i - EVOL_BARRAS]) else np.nan
        dl = larg - larg5; evol = None if not np.isfinite(dl) else ("abrindo" if dl > EVOL_ATR else ("fechando" if dl < -EVOL_ATR else "estável"))
        compr = float(np.clip((COMPRESSAO_LARGO - larg) / (COMPRESSAO_LARGO - COMPRESSAO_ESTREITO), 0, 1) * 100)
        ev = {"toque_ema_high": bool(ch >= eH[i] and ci <= eH[i]), "toque_ema_low": bool(cl <= eL[i] and ci >= eL[i]),
              "fechou_acima_do_canal": bool(ci > eH[i] and cp <= eH[i - 1]), "fechou_abaixo_do_canal": bool(ci < eL[i] and cp >= eL[i - 1]),
              "voltou_para_dentro_por_cima": bool(ci <= eH[i] and cp > eH[i - 1]), "voltou_para_dentro_por_baixo": bool(ci >= eL[i] and cp < eL[i - 1])}
        # estrutura: nível elegível acima (resistência) e abaixo (suporte) do fechamento, e o seguinte (espaço até o próximo nível conhecido)
        est = {}
        for lado, nome in ((1, "resistencia_acima"), (-1, "suporte_abaixo")):
            ob = JN.obstaculos(self.mem, lado, ci, a, 2 * a)
            if ob is None: est[nome] = None; continue
            z = ob["zona_elegivel"]; ref = z[0] if lado > 0 else z[1]
            pos_n = "acima do canal" if ref > eH[i] else ("abaixo do canal" if ref < eL[i] else "dentro do canal")
            est[nome] = {"nivel": ob["nivel"], "zona": [round(z[0], 2), round(z[1], 2)], "estado": ob["estado"], "dist_preco": round(ob["distancia"], 2), "dist_atr": round(ob["dist_atr"], 3),
                         "posicao_vs_canal": pos_n, "no_caminho": bool(ob["dist_atr"] <= OBST_ATR), "membros_elegiveis": ob["membros_elegiveis"],
                         "espaco_ate_o_seguinte_atr": None if not ob["seguinte"] else round(ob["seguinte"]["dist_atr"], 3)}
        romp = [{"nivel": x["id"], "funcao": x["funcao"], "zona": [round(x["zona"][0], 2), round(x["zona"][1], 2)], "estado": x["estado"]}
                for x in self.mem.niveis if x["estado"] in ("ROMPIMENTO PENDENTE", "ROMPIMENTO CONFIRMADO") and x["historico"] and x["historico"][-1][0] >= str(pd.Timestamp(T[max(0, i - 4)]))]
        # concordância canal × estrutura (regra programada; a estrutura prevalece; nenhum veto)
        if pos.startswith("acima"):
            r = est["resistencia_acima"]
            conc = ("divergem", f"canal indica avanço de alta, mas há resistência {r['zona']} a {r['dist_atr']:.2f} ATR no caminho — a estrutura prevalece") if r and r["no_caminho"] else \
                   ("concordam", "alta: fechamento acima do canal sem resistência elegível a ≤ 1 ATR")
        elif pos.startswith("abaixo"):
            s_ = est["suporte_abaixo"]
            conc = ("divergem", f"canal indica avanço de baixa, mas há suporte {s_['zona']} a {s_['dist_atr']:.2f} ATR no caminho — a estrutura prevalece") if s_ and s_["no_caminho"] else \
                   ("concordam", "baixa: fechamento abaixo do canal sem suporte elegível a ≤ 1 ATR")
        else: conc = ("neutro", "preço dentro do canal: o canal não indica avanço; vale a leitura da estrutura")
        sem_res = not (est["resistencia_acima"] and est["resistencia_acima"]["no_caminho"]); sem_sup = not (est["suporte_abaixo"] and est["suporte_abaixo"]["no_caminho"])
        av_alta = 100 * np.mean([ci > eH[i], iH > 0 and iL > 0, evol == "abrindo", sem_res]); av_baixa = 100 * np.mean([ci < eL[i], iH < 0 and iL < 0, evol == "abrindo", sem_sup])
        leitura = (f"{pos}; EMA20 High {_dir(iH)} ({iH:+.3f} ATR/barra), EMA20 Low {_dir(iL)} ({iL:+.3f}); largura {larg:.2f} ATR {evol or 'sem histórico'}"
                   f"{' (compressão ' + str(round(compr)) + '%)' if compr > 0 else ''}. Canal × estrutura: {conc[0]} — {conc[1]}.")
        return {**base, "disponivel": True, "atr": round(a, 4),
                "canal": {"ema20_high": round(float(eH[i]), 2), "ema20_low": round(float(eL[i]), 2), "posicao": pos,
                          "inclinacao_high_atr_por_barra": round(float(iH), 4), "direcao_high": _dir(iH), "inclinacao_low_atr_por_barra": round(float(iL), 4), "direcao_low": _dir(iL),
                          "largura_atr": round(float(larg), 3), "largura_variacao_5b_atr": None if not np.isfinite(dl) else round(float(dl), 3), "evolucao": evol,
                          "compressao_pct": round(compr, 1),
                          "dist_ema_high": {"preco": round(float(ci - eH[i]), 2), "atr": round(float((ci - eH[i]) / a), 3)},
                          "dist_ema_low": {"preco": round(float(ci - eL[i]), 2), "atr": round(float((ci - eL[i]) / a), 3)}},
                "eventos": ev, "estrutura": {**est, "rompimentos_ultimas_5_barras": romp},
                "concordancia": {"estado": conc[0], "explicacao": conc[1]},
                "evidencia_pct": {"avanco_alta": round(float(av_alta), 1), "avanco_baixa": round(float(av_baixa), 1),
                                  "formula": "média de 4 critérios ×100: fechamento além do canal; as 2 médias inclinadas a favor; canal abrindo; sem nível elegível a ≤ 1 ATR no caminho (grau de atendimento, não probabilidade)"},
                "leitura_produzida": leitura}
