"""marcações das operações (bancada): candles M15, canais 20/10 das barras ANTERIORES, sinal, execução, stop e saída com motivo."""
import sys, os, numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, "codigo"); import romp_m15 as RM, bancada_romp as B
m15 = B.ler("M15"); K = RM.canais(m15); ops = pd.read_csv("saida/bancada/ROMP_operacoes.csv", sep=";"); ops = ops[~ops.aberta_no_fim_dos_dados]
oos = ops[pd.to_datetime(ops.barra_sinal) >= "2026-05-01"]
esc = {"maior ganho (fora da amostra)": oos.loc[oos.usd_1lote.idxmax()], "maior perda (fora da amostra)": oos.loc[oos.usd_1lote.idxmin()],
       "primeira venda fora da amostra": oos[oos.lado < 0].iloc[0], "primeira compra fora da amostra": oos[oos.lado > 0].iloc[0]}
os.makedirs("saida/graficos", exist_ok=True)
for nome, o in esc.items():
    i0 = int(np.searchsorted(m15.t.values, np.datetime64(o.barra_sinal))); i1 = int(np.searchsorted(m15.t.values, np.datetime64(pd.Timestamp(o.t_sai)), side="right"))
    a, b = max(0, i0 - 30), min(len(m15), i1 + 8); d = m15.iloc[a:b]; k = K.iloc[a:b]; x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(14, 6)); cor = np.where(d.c >= d.o, "#2a9d4a", "#d33")
    ax.vlines(x, d.l, d.h, color=cor, lw=0.8); ax.bar(x, (d.c - d.o).abs().clip(lower=0.02), bottom=np.minimum(d.o, d.c), color=cor, width=0.6)
    ax.step(x, k.LS20, where="mid", color="#1f77b4", lw=1.2, label="LS20/LI20 (20 anteriores)"); ax.step(x, k.LI20, where="mid", color="#1f77b4", lw=1.2)
    ax.step(x, k.LS10, where="mid", color="#ff8c00", lw=1, ls=":", label="LS10/LI10 (10 anteriores)"); ax.step(x, k.LI10, where="mid", color="#ff8c00", lw=1, ls=":")
    xs = i0 - a; xe = xs + 1; xo = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(o.t_sai)), side="right")) - 1
    ax.annotate("SINAL " + ("COMPRA" if o.lado > 0 else "VENDA"), (xs, d.c.iloc[xs]), xytext=(xs - 6, d.c.iloc[xs] + (1 if o.lado < 0 else -1) * 3 * o.atr), arrowprops=dict(arrowstyle="->"), fontsize=9)
    ax.plot([xe], [o.entrada], marker="^" if o.lado > 0 else "v", ms=11, color="lime", mec="k", label=f"execução {o.entrada:.2f}")
    ax.hlines(o.stop, xe, xo, color="red", ls="--", lw=1, label=f"stop {o.stop:.2f} (2×ATR {o.atr:.2f})")
    ax.plot([xo], [o.saida], marker="X", ms=11, color="magenta", mec="k", label=f"saída {o.saida:.2f} — {o.motivo_saida}")
    ax.set_xticks(x[::8]); ax.set_xticklabels([t.strftime("%d/%m %H:%M") for t in d.t.iloc[::8]], rotation=30, fontsize=8)
    ax.set_title(f"XAUUSD M15 · {RM.VERSAO} · {o.id} · {nome} · {o.R:+.2f} R · US$ {o.usd_1lote:+.0f}/lote (bancada; hora do servidor)", fontsize=10); ax.legend(fontsize=8, loc="best"); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(f"saida/graficos/ROMP_{o.id}.png", dpi=110); plt.close(fig); print(nome, o.id)
