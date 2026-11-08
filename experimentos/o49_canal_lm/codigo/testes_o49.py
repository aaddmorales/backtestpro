"""ORDEM 049 — testes da leitura do canal (cálculo, causalidade, disponibilidade, eventos, concordância, incremental × replay). Uso: python testes_o49.py SAIDA.json"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leitura_canal_o49 as LC, estrategia_o39 as ST, romp_m15 as RM
RES = []
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)

d = ST.ler("XAUUSD", "M30").iloc[-3000:].reset_index(drop=True); h, l, c, o = (d[k].values.astype(float) for k in "hlco")
eH, eL = LC.emas(h, l); man = np.empty(len(h)); man[0] = h[0]; al = 2 / 21
for i in range(1, len(h)): man[i] = al * h[i] + (1 - al) * man[i - 1]
reg("EMA20 High = fórmula recursiva (α = 2/21, início no 1º valor)", np.allclose(man, eH, atol=1e-9), f"diferença máx {np.abs(man - eH).max():.2e}")

def rodar(df, ate):
    L = LC.LeitorCanal("XAUUSD", "M30"); T = df.t.values; o_, h_, l_, c_ = (df[k].values.astype(float) for k in "ohlc"); A = RM.atr_wilder(df.h, df.l, df.c); a_, b_ = LC.emas(h_, l_)
    for i in range(ate + 1): L.alimentar_uma(T[i], 30, o_[i], h_[i], l_[i], c_[i])
    return L.ler(T, o_, h_, l_, c_, A, a_, b_, ate)
i0 = 2500; base = rodar(d, i0); fut = d.copy(); fut.loc[i0 + 1:, ["o", "h", "l", "c"]] *= 1.05
reg("leitura no fechamento usa só barras até o instante (futuro alterado em +5% não muda nada)", rodar(fut, i0) == base, base["leitura_produzida"][:120])
curto = rodar(d.iloc[:40].reset_index(drop=True), 39)
reg("histórico insuficiente é sinalizado (40 barras < 60)", curto["disponivel"] is False and "insuficiente" in curto["ausencia"], curto["ausencia"])

# eventos e posição (série sintética controlada)
n = 120; t = pd.date_range("2026-01-05", periods=n, freq="30min"); c_ = np.full(n, 100.0); h_ = c_ + 0.5; l_ = c_ - 0.5; o_ = c_.copy()
def L_sint(c_, h_, l_, i):
    df = pd.DataFrame({"t": t, "o": o_, "h": h_, "l": l_, "c": c_}); return rodar(df, i)
c2, h2, l2 = c_.copy(), h_.copy(), l_.copy(); c2[100] = 101.5; h2[100] = 101.8; l2[100] = 100.0; r = L_sint(c2, h2, l2, 100)
reg("fechamento acima da EMA20 High é evento separado e posição 'acima'", r["eventos"]["fechou_acima_do_canal"] and r["canal"]["posicao"].startswith("acima") and not r["eventos"]["toque_ema_high"], r["leitura_produzida"][:90])
c3, h3, l3 = c2.copy(), h2.copy(), l2.copy(); c3[101] = 100.0; h3[101] = 101.0; l3[101] = 99.8; r = L_sint(c3, h3, l3, 101)
reg("fechamento de volta para dentro por cima registrado separadamente", r["eventos"]["voltou_para_dentro_por_cima"] and r["canal"]["posicao"] == "dentro do canal", str({k: v for k, v in r["eventos"].items() if v}))
c4, h4, l4 = c_.copy(), h_.copy(), l_.copy(); h4[100] = 101.0; r = L_sint(c4, h4, l4, 100)
reg("toque na EMA20 High sem fechar além = 'toque'", r["eventos"]["toque_ema_high"] and not r["eventos"]["fechou_acima_do_canal"] and r["canal"]["posicao"] == "dentro do canal", "toque registrado")
eh100 = LC.emas(h_, l_)[0][100]; c5 = c_.copy(); c5[100] = eh100; r = L_sint(c5, np.maximum(h_, c5), l_, 100)
reg("fechar IGUAL à EMA20 High é 'dentro do canal' (igualar não atravessa)", r["canal"]["posicao"] == "dentro do canal", f"c = EMA20 High = {eh100:.4f}")
reg("distâncias em preço e em ATR; largura em ATR", all(k in r["canal"]["dist_ema_high"] for k in ("preco", "atr")) and isinstance(r["canal"]["largura_atr"], float), json.dumps(r["canal"]["dist_ema_high"]))

# concordância × estrutura em dados reais: acima do canal com resistência ≤ 1 ATR = divergem; sem = concordam
P = pd.read_csv("/home/claude/r005/lm049/saida/replay/O49_XAUUSD_M30_leitura_por_barra.csv.gz", sep=";"); P = P[P.disponivel == True]
acima = P[P.posicao.str.startswith("acima")]; div = acima[acima.concordancia == "divergem"]; con = acima[acima.concordancia == "concordam"]
reg("regra: acima do canal + resistência no caminho (≤ 1 ATR) → DIVERGEM; sem → CONCORDAM (estrutura prevalece)", (div.res_dist_atr <= 1.0).all() and ((con.res_dist_atr.isna()) | (con.res_dist_atr > 1.0)).all(),
    f"divergem {len(div)} · concordam {len(con)} (barras acima do canal, XAU M30)")
reg("dentro do canal é sempre NEUTRO (o canal sozinho não indica avanço)", (P[P.posicao == "dentro do canal"].concordancia == "neutro").all(), f"{(P.posicao == 'dentro do canal').sum()} barras")
reg("pontuações 0–100% dentro da faixa (evidência, não probabilidade)", P[["compressao_pct", "av_alta_pct", "av_baixa_pct"]].stack().between(0, 100).all(), "compressão e evidência de avanço")

# incremental (como no leitor ao vivo: janela de 1200 barras, recalcula a cada fechamento) × replay com todo o histórico
full = ST.ler("XAUUSD", "M30"); k = len(full) - 1; jan = full.iloc[k - 1199:k + 1].reset_index(drop=True)
Lr = LC.LeitorCanal("XAUUSD", "M30"); T = full.t.values; o_, h_, l_, c_ = (full[x].values.astype(float) for x in "ohlc"); A = RM.atr_wilder(full.h, full.l, full.c); a_, b_ = LC.emas(h_, l_)
for i in range(k - 1199, k + 1): Lr.alimentar_uma(T[i], 30, o_[i], h_[i], l_[i], c_[i])
rep = Lr.ler(T, o_, h_, l_, c_, A, a_, b_, k); viv = LC.LeitorCanal("XAUUSD", "M30").barra(jan)
reg("leitor ao vivo (janela de 1.200 barras, mesma memória inicial) = replay no mesmo instante", rep["canal"] == viv["canal"] and rep["eventos"] == viv["eventos"] and rep["concordancia"] == viv["concordancia"],
    rep["leitura_produzida"][:110])
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "versao": LC.VERSAO, "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
