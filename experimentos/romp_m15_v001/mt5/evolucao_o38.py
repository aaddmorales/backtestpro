"""evolucao-0.1 (ORDEM 038) — leitura entre timeframes a partir de M1: estrutura com empate, pivôs com horário de conhecimento,
rompimentos/rejeições com invalidação, canal EMA20 H/L, Bollinger, ATR, graus 0–100% (continuidade, lateralização, exaustão),
evolução temporal por TF, níveis do dia, M15 em formação (provisório) e elegibilidade do corte na escala M15 (C1/C2/C3).
Especificação: O38_especificacao_congelada.txt (sha f92243be…). Mesmo código na bancada e no leitor MT5.
Uso: T = Tabelas(m1); X = T.features(tempos_ns, lados, formacao=True)"""
import numpy as np, pandas as pd
VERSAO = "evolucao-0.1 (ORDEM 038)"
MINNS = 60 * 10**9
DUR = {"M1": 1, "M5": 5, "M15": 15}
JAN = {"M1": (5, 15), "M5": (3, 6), "M15": (2, 4)}


def _ns(v): return pd.to_datetime(v).values.astype("datetime64[ns]").astype(np.int64)


def agregar(m1, tf):
    """barras do TF agregadas das M1 (abertura alinhada ao relógio). Mesma função no leitor."""
    if tf == "M1": d = m1[["t", "o", "h", "l", "c"]].copy()
    else:
        g = m1.assign(k=m1.t.dt.floor(f"{DUR[tf]}min")).groupby("k", sort=True)
        d = pd.DataFrame({"t": g.t.first().index, "o": g.o.first().values, "h": g.h.max().values, "l": g.l.min().values, "c": g.c.last().values})
    d = d.reset_index(drop=True); d["fecha"] = _ns(d.t) + DUR[tf] * MINNS
    return d


def _atr(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]; tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().values


def _pivos(h, l):
    """fractal k=2; empate → o PRIMEIRO da sequência (estritamente maior que os 2 da esquerda, ≥ os 2 da direita); conhecido em i+2."""
    n = len(h); top = np.zeros(n, bool); bot = np.zeros(n, bool)
    if n >= 5:
        i = np.arange(2, n - 2)
        top[i] = (h[i] > h[i - 1]) & (h[i] > h[i - 2]) & (h[i] >= h[i + 1]) & (h[i] >= h[i + 2])
        bot[i] = (l[i] < l[i - 1]) & (l[i] < l[i - 2]) & (l[i] <= l[i + 1]) & (l[i] <= l[i + 2])
    return np.nonzero(top)[0], np.nonzero(bot)[0]


def _ultimos(idx_piv, val, n):
    """para cada barra j: valor do último e do penúltimo pivô CONHECIDOS (conhecido em i+2 ≤ j) e o índice da barra do último."""
    conhecido = idx_piv + 2; j = np.arange(n); k = np.searchsorted(conhecido, j, side="right") - 1
    u = np.where(k >= 0, val[idx_piv[np.clip(k, 0, None)]] if len(idx_piv) else np.nan, np.nan)
    p = np.where(k >= 1, val[idx_piv[np.clip(k - 1, 0, None)]] if len(idx_piv) else np.nan, np.nan)
    ib = np.where(k >= 0, idx_piv[np.clip(k, 0, None)] if len(idx_piv) else -1, -1)
    return u.astype(float), p.astype(float), ib


def _corrida(b):
    """comprimento da sequência atual de True (0 se False)."""
    out = np.zeros(len(b)); c = 0
    for i, x in enumerate(b): c = c + 1 if x else 0; out[i] = c
    return out


def _media(cols):
    M = np.column_stack(cols); ok = np.isfinite(M)
    with np.errstate(invalid="ignore"):
        return 100 * np.where(ok.sum(1) > 0, np.nansum(M, 1) / np.maximum(ok.sum(1), 1), np.nan), ok.sum(1) / M.shape[1]


def tabela_tf(d):
    """leituras por barra FECHADA do TF (índice = barra; 'fecha' = instante em que fica conhecida)."""
    o, h, l, c = (d[k].to_numpy(float) for k in "ohlc"); n = len(c); A = _atr(h, l, c)
    eH = pd.Series(h).ewm(span=20, adjust=False, min_periods=20).mean().values; eL = pd.Series(l).ewm(span=20, adjust=False, min_periods=20).mean().values
    mid = (eH + eL) / 2; bm = pd.Series(c).rolling(20).mean().values; bs = pd.Series(c).rolling(20).std(ddof=0).values; bu, bd = bm + 2 * bs, bm - 2 * bs
    with np.errstate(invalid="ignore", divide="ignore"): pctb = (c - bd) / (bu - bd)
    it, ib = _pivos(h, l); t1, t0, _ = _ultimos(it, h, n); f1, f0, _ = _ultimos(ib, l, n); eps = 0.05 * A
    with np.errstate(invalid="ignore"):
        igual = ((np.abs(t1 - t0) <= eps) | (np.abs(f1 - f0) <= eps)).astype(float)
        alta = (t1 > t0 + eps) & (f1 > f0 + eps); baixa = (t1 < t0 - eps) & (f1 < f0 - eps)
    estr = np.where(alta, 1.0, np.where(baixa, -1.0, 0.0)); indef = ~(np.isfinite(t0) & np.isfinite(f0) & np.isfinite(A))
    estr[indef] = np.nan; igual[indef] = np.nan
    with np.errstate(invalid="ignore"):
        br_dn = (c < f1) & np.isfinite(f1); br_up = (c > t1) & np.isfinite(t1)
        rej_dn = ((l < f1) & (c >= f1)).astype(float); rej_up = ((h > t1) & (c <= t1)).astype(float)
    dc = np.r_[np.nan, np.diff(c)]
    up5 = pd.Series((dc > 0).astype(float)).rolling(5).mean().values; dn5 = pd.Series((dc < 0).astype(float)).rolling(5).mean().values
    r8 = c - np.r_[np.full(8, np.nan), c[:-8]]
    with np.errstate(invalid="ignore", divide="ignore"):
        c1u = np.where(np.isfinite(eH), np.where(c > eH, 1.0, np.where(c < eL, 0.0, 0.5)), np.nan); c1d = np.where(np.isfinite(eL), np.where(c < eL, 1.0, np.where(c > eH, 0.0, 0.5)), np.nan)
        c3u = np.where(np.isnan(estr), np.nan, np.where(estr == 1, 1.0, np.where(estr == -1, 0.0, 0.5))); c3d = np.where(np.isnan(estr), np.nan, np.where(estr == -1, 1.0, np.where(estr == 1, 0.0, 0.5)))
        c4u = np.clip(r8 / (1.5 * A), 0, 1); c4d = np.clip(-r8 / (1.5 * A), 0, 1)
        cont_up, cov_cu = _media([c1u, up5, c3u, c4u]); cont_dn, cov_cd = _media([c1d, dn5, c3d, c4d])
        l1 = np.where(np.isfinite(eH), ((c <= eH) & (c >= eL)).astype(float), np.nan)
        net = np.abs(c - np.r_[np.full(12, np.nan), c[:-12]]); gross = pd.Series(np.abs(dc)).rolling(12).sum().values; l2 = 1 - np.where(gross > 0, net / gross, np.nan)
        amp = pd.Series(h).rolling(12).max().values - pd.Series(l).rolling(12).min().values; l3 = np.clip(1 - amp / (4 * A), 0, 1)
        lado_mid = np.sign(c - mid); cruz = pd.Series((np.r_[0, np.diff(lado_mid)] != 0).astype(float)).rolling(12).sum().values; l4 = np.minimum(cruz / 3, 1)
        lat, cov_l = _media([l1, l2, l3, l4])
        corpo = c - o; rng = h - l
        e1u = np.where(np.isfinite(bu), (h >= bu).astype(float), np.nan); e1d = np.where(np.isfinite(bd), (l <= bd).astype(float), np.nan)
        e2u = np.clip((c - eH) / (2 * A), 0, 1); e2d = np.clip((eL - c) / (2 * A), 0, 1)
        b1, b2, b3 = corpo, np.r_[np.nan, corpo[:-1]], np.r_[np.nan, np.nan, corpo[:-2]]
        e3u = ((b1 > 0) & (b2 > 0) & (b3 > 0) & (b1 < b2) & (b2 < b3)).astype(float); e3d = ((b1 < 0) & (b2 < 0) & (b3 < 0) & (b1 > b2) & (b2 > b3)).astype(float)
        e4u = np.where(rng > 0, (h - np.maximum(o, c)) / rng, np.nan); e4d = np.where(rng > 0, (np.minimum(o, c) - l) / rng, np.nan)
        exa_up, cov_eu = _media([e1u, e2u, e3u, e4u]); exa_dn, cov_ed = _media([e1d, e2d, e3d, e4d])
    T = pd.DataFrame({"fecha": d.fecha.values, "c": c, "atr": A, "eH": eH, "eL": eL, "mid": mid, "pctb": pctb, "estr": estr, "igual": igual,
                      "topo": t1, "fundo": f1, "br_up": br_up.astype(float), "br_dn": br_dn.astype(float), "br_up_id": _corrida(br_up), "br_dn_id": _corrida(br_dn),
                      "rej_up": rej_up, "rej_dn": rej_dn, "cont_up": cont_up, "cont_dn": cont_dn, "lat": lat, "exa_up": exa_up, "exa_dn": exa_dn,
                      "cov_cont": (cov_cu + cov_cd) / 2, "cov_lat": cov_l, "cov_exa": (cov_eu + cov_ed) / 2, "up_frac": dc > 0, "dn_frac": dc < 0})
    return T


class Tabelas:
    def __init__(self, m1):
        m1 = m1.copy(); m1["t"] = pd.to_datetime(m1["t"]); m1 = m1.sort_values("t").reset_index(drop=True)
        self.m1 = m1; self.D = {tf: agregar(m1, tf) for tf in DUR}; self.T = {tf: tabela_tf(self.D[tf]) for tf in DUR}
        self.f = {tf: self.T[tf].fecha.values for tf in DUR}
        # dia (UTC): máxima/mínima do dia anterior e acumuladas do dia corrente até a M1
        d = m1.t.dt.floor("D"); self.m1_fecha = _ns(m1.t) + MINNS
        dh = m1.groupby(d).h.max(); dl = m1.groupby(d).l.min(); prev_h = dh.shift(1); prev_l = dl.shift(1)
        self.dia_ant_h = d.map(prev_h).values.astype(float); self.dia_ant_l = d.map(prev_l).values.astype(float)
        self.dia_h = m1.groupby(d).h.cummax().values; self.dia_l = m1.groupby(d).l.cummin().values
        g15 = m1.t.dt.floor("15min"); self.g15 = _ns(g15)
        gb = m1.groupby(g15); self.f_o = gb.o.transform("first").values; self.f_h = gb.h.cummax().values; self.f_l = gb.l.cummin().values
        dcm = np.r_[np.nan, np.diff(m1.c.values)]; m1 = m1.assign(_up=(dcm > 0).astype(float), _dn=(dcm < 0).astype(float))
        self.f_n = gb.cumcount().values + 1; self.f_up = m1.groupby(g15)._up.cumsum().values; self.f_dn = m1.groupby(g15)._dn.cumsum().values
        self.c1 = m1.c.values

    def _idx(self, tf, T):
        return np.searchsorted(self.f[tf], T, side="right") - 1                    # última barra FECHADA em T

    def features(self, T, s, formacao=False):
        """T: instantes (ns, int64); s: lados (+1/−1). Devolve DataFrame com as colunas relativas ao lado (spec §2–§7)."""
        T = np.asarray(T, dtype=np.int64); s = np.asarray(s, dtype=float); out = {}
        for tf in DUR:
            X = self.T[tf]; i = self._idx(tf, T); ok = i >= 0; ii = np.clip(i, 0, None)
            g = lambda col: np.where(ok, X[col].values[ii], np.nan)
            up = s > 0; c, A = g("c"), g("atr"); k1, k2 = JAN[tf]
            def lag(col, k):
                j = np.clip(ii - k, 0, None); return np.where(ok & (ii - k >= 0), X[col].values[j], np.nan)
            cu, cd, eu, ed, la = g("cont_up"), g("cont_dn"), g("exa_up"), g("exa_dn"), g("lat")
            p = f"{tf}_"
            out[p + "estr_rel"] = g("estr") * s; out[p + "estr_igual"] = g("igual")
            with np.errstate(invalid="ignore", divide="ignore"):
                out[p + "dist_piv_con"] = np.where(up, (c - g("fundo")) / A, (g("topo") - c) / A)
                out[p + "dist_piv_fav"] = np.where(up, (g("topo") - c) / A, (c - g("fundo")) / A)
                out[p + "canal_rel"] = (c - g("mid")) / A * s
            out[p + "romp_con_ativo"] = np.where(up, g("br_dn"), g("br_up")); out[p + "romp_con_idade"] = np.where(out[p + "romp_con_ativo"] == 1, np.where(up, g("br_dn_id"), g("br_up_id")), np.nan)
            out[p + "romp_fav_ativo"] = np.where(up, g("br_up"), g("br_dn")); out[p + "romp_fav_idade"] = np.where(out[p + "romp_fav_ativo"] == 1, np.where(up, g("br_up_id"), g("br_dn_id")), np.nan)
            out[p + "rej_con"] = np.where(up, g("rej_dn"), g("rej_up"))
            out[p + "fora_canal_con"] = np.where(np.isfinite(g("eL")), np.where(up, c < g("eL"), c > g("eH")).astype(float), np.nan)
            out[p + "fora_canal_fav"] = np.where(np.isfinite(g("eH")), np.where(up, c > g("eH"), c < g("eL")).astype(float), np.nan)
            out[p + "bb_rel"] = np.where(up, g("pctb"), 1 - g("pctb"))
            out[p + "cont_fav"] = np.where(up, cu, cd); out[p + "cont_con"] = np.where(up, cd, cu); out[p + "lateral"] = la
            out[p + "exa_fav"] = np.where(up, eu, ed); out[p + "exa_con"] = np.where(up, ed, eu)
            for k in (k1, k2):
                out[p + f"d_cont_con_{k}"] = out[p + "cont_con"] - np.where(up, lag("cont_dn", k), lag("cont_up", k))
                out[p + f"d_exa_fav_{k}"] = out[p + "exa_fav"] - np.where(up, lag("exa_up", k), lag("exa_dn", k))
                out[p + f"d_lateral_{k}"] = la - lag("lat", k)
                with np.errstate(invalid="ignore", divide="ignore"): out[p + f"ret_rel_{k}"] = (c - lag("c", k)) / A * s
            fc = np.where(up, X["dn_frac"].astype(float).rolling(k2).mean().values[ii], X["up_frac"].astype(float).rolling(k2).mean().values[ii]); out[p + f"frac_con_{k2}"] = np.where(ok & (ii >= k2), fc, np.nan)
            out[p + "cov_cont"] = g("cov_cont"); out[p + "cov_lat"] = g("cov_lat"); out[p + "cov_exa"] = g("cov_exa")
        # níveis do dia (M1 fechadas até T), em ATR15
        j = np.searchsorted(self.m1_fecha, T, side="right") - 1; okj = j >= 0; jj = np.clip(j, 0, None); A15 = np.where(self._idx("M15", T) >= 0, self.T["M15"].atr.values[np.clip(self._idx("M15", T), 0, None)], np.nan)
        c1 = np.where(okj, self.c1[jj], np.nan); up = s > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            pa_h, pa_l, dh, dl = (np.where(okj, v[jj], np.nan) for v in (self.dia_ant_h, self.dia_ant_l, self.dia_h, self.dia_l))
            out["dia_ant_fav"] = np.where(up, pa_h - c1, c1 - pa_l) / A15; out["dia_ant_con"] = np.where(up, c1 - pa_l, pa_h - c1) / A15
            out["dia_cor_fav"] = np.where(up, dh - c1, c1 - dl) / A15; out["dia_cor_con"] = np.where(up, c1 - dl, dh - c1) / A15
        if formacao:
            out.update(self.formacao(T, s, j, okj, A15))
        return pd.DataFrame(out)

    def formacao(self, T, s, j, okj, A15):
        """M15 em formação (provisório): só M1 fechadas do M15 corrente; + elegibilidade C1/C2/C3 (spec §7)."""
        up = s > 0; jj = np.clip(j, 0, None); ini = (T // (15 * MINNS)) * 15 * MINNS
        tem = okj & (self.g15[jj] == ini) & (T > ini)                              # há M1 fechada dentro do M15 corrente
        X = self.T["M15"]; i = self._idx("M15", T); ok = i >= 0; ii = np.clip(i, 0, None)
        piv_con = np.where(ok, np.where(up, X.fundo.values[ii], X.topo.values[ii]), np.nan)
        c = np.where(tem, self.c1[jj], np.nan); o = np.where(tem, self.f_o[jj], np.nan); n = np.where(tem, self.f_n[jj], np.nan)
        out = {}
        with np.errstate(invalid="ignore", divide="ignore"):
            out["F_min"] = np.where(tem, (T - ini) / MINNS, 0.0)
            out["F_ret_rel"] = (c - o) / A15 * s; out["F_amp"] = np.where(tem, (self.f_h[jj] - self.f_l[jj]), np.nan) / A15
            out["F_dist_piv_con"] = (c - piv_con) * s / A15
            out["F_alem_piv_con"] = np.where(np.isfinite(out["F_dist_piv_con"]), (out["F_dist_piv_con"] < 0).astype(float), np.nan)
            eL, eH = np.where(ok, X.eL.values[ii], np.nan), np.where(ok, X.eH.values[ii], np.nan)
            out["F_fora_canal_con"] = np.where(tem & np.isfinite(eL), np.where(up, c < eL, c > eH).astype(float), np.nan)
            out["F_m1_con"] = np.where(tem, np.where(up, self.f_dn[jj], self.f_up[jj]) / n, np.nan)
            # elegibilidade (contrato, spec §7)
            c15 = np.where(ok, X.c.values[ii], np.nan); estr15 = np.where(ok, X.estr.values[ii], np.nan) * s
            C1 = ok & np.isfinite(piv_con) & ((c15 - piv_con) * s < 0)
            C2 = ok & np.isfinite(eL) & np.where(up, c15 < eL, c15 > eH) & ~(estr15 > 0)
            i5 = self._idx("M5", T); c5 = np.where(i5 >= 0, self.T["M5"].c.values[np.clip(i5, 0, None)], np.nan)
            k5 = np.zeros(len(T))
            for q in range(5):
                jq = jj - q; cq = np.where(jq >= 0, self.c1[np.clip(jq, 0, None)], np.nan); k5 += np.nan_to_num(((cq - piv_con) * s < 0).astype(float))
            C3 = tem & np.isfinite(piv_con) & ((c - piv_con) * s <= -0.25 * A15) & ((c5 - piv_con) * s < 0) & (k5 >= 3)
        out["elig_C1"] = C1.astype(float); out["elig_C2"] = C2.astype(float); out["elig_C3_provisorio"] = C3.astype(float); out["elegivel_corte_M15"] = (C1 | C2 | C3).astype(float)
        return out


def colunas(formacao=False):
    """ordem congelada das colunas (para o vetor do modelo e para o leitor)."""
    import io
    m1 = pd.DataFrame({"t": pd.date_range("2026-01-01", periods=3000, freq="1min"), "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "spread": 1})
    return list(Tabelas(m1).features(np.array([_ns(m1.t)[-1]]), np.array([1]), formacao).columns)
