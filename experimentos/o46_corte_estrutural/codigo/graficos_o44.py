"""ORDEM 044 — em cada TF e ativo, um rompimento que deu sequência e um que voltou (sorteio fixo dentro da categoria, não por resultado):
caixa, nível, barra de rompimento, gatilho, entrada e saída. Uso: python graficos_o44.py SAIDA_REPLAY SAIDA_GRAFICOS"""
import os, sys, json
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estrategia_o39 as ST
INK, INK2, MUT, SURF = "#0b0b0b", "#52514e", "#a3a29c", "#fcfcfb"; AZUL, LAR, VERDE, VIOL = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
TFM = {"M15": 15, "M30": 30, "H1": 60}


def velas(ax, d, w=0.6):
    for x, r in enumerate(d.itertuples()):
        ax.plot([x, x], [r.l, r.h], color=INK2, lw=0.9, zorder=2)
        lo, hi = min(r.o, r.c), max(r.o, r.c); ax.add_patch(Rectangle((x - w / 2, lo), w, max(hi - lo, 1e-9), facecolor="#ffffff" if r.c >= r.o else INK2, edgecolor=INK2, lw=0.8, zorder=3))


def painel(ax, s, d_all, tf, titulo):
    mn = TFM[tf]; lado = int(s["lado"]); tb = pd.Timestamp(s["barra_rompimento"]); ib = int(np.searchsorted(d_all.t.values, np.datetime64(tb)))
    ts = pd.Timestamp(s["iso_t_sai"]) if isinstance(s["iso_t_sai"], str) else pd.Timestamp(int(s["iso_t_sai"]))
    isai = int(np.searchsorted(d_all.t.values, np.datetime64(ts), side="right")) - 1
    i0, i1 = ib - 15, min(max(isai + 3, ib + 6), ib + 40); d = d_all.iloc[i0:i1].reset_index(drop=True); xb = ib - i0; velas(ax, d)
    xc = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(s["caixa_inicio"])))); F = s["referencia"]
    ax.axvspan(xc - 0.5, xb - 0.5, color=AZUL, alpha=0.07, zorder=0); ax.text(xc - 0.4, 0.97, "caixa 12 barras", transform=ax.get_xaxis_transform(), color=AZUL, fontsize=7.5, va="top")
    ax.hlines(F, xc - 0.5, len(d) - 0.5, color=AZUL, lw=2, zorder=1); ax.text(len(d) - 0.5, F, f" nível {F:.2f}", color=AZUL, fontsize=8, va="center", fontweight="bold")
    ax.add_patch(Rectangle((xb - 0.45, d.l[xb]), 0.9, d.h[xb] - d.l[xb], fill=False, edgecolor=LAR, lw=2.2, zorder=4))
    ax.annotate("rompimento\n(fechou além)", (xb, d.l[xb] if lado < 0 else d.h[xb]), xytext=(-60, -38 if lado < 0 else 30), textcoords="offset points", fontsize=7.5, color=LAR, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=LAR), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=8)
    ax.axvspan(xb + 0.5, xb + 1.5, color=VIOL, alpha=0.08, zorder=0); ax.hlines(s["T"], xb + 0.5, xb + 1.5, color=VIOL, lw=1.8, ls="--", zorder=5)
    ax.plot(xb + 1, s["iso_entrada"], marker="v" if lado < 0 else "^", ms=10, color=VIOL, zorder=6)
    ax.annotate(f"gatilho {s['T']:.2f}\nentrada {str(s['t_superacao'])[11:16]}", (xb + 1, s["iso_entrada"]), xytext=(14, -34 if lado < 0 else 26), textcoords="offset points", fontsize=7.5, color=VIOL,
                arrowprops=dict(arrowstyle="->", color=VIOL), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=8)
    xs = isai - i0
    if 0 <= xs < len(d):
        ax.plot(xs, s["iso_saida"], marker="X", ms=10, color=VERDE if s["iso_R"] > 0 else LAR, zorder=7)
        ax.annotate(f"saída {s['iso_R']:+.2f} R\n{'canal EMA20' if str(s['iso_motivo_saida']).startswith('saída') else 'stop'}", (xs, s["iso_saida"]), xytext=(10, 22 if lado < 0 else -34), textcoords="offset points", fontsize=7.5,
                    color=INK, arrowprops=dict(arrowstyle="->", color=MUT), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=8)
    yl = ax.get_ylim(); ax.set_ylim(yl[0] - (yl[1] - yl[0]) * 0.1, yl[1] + (yl[1] - yl[0]) * 0.1)
    step = max(1, len(d) // 7); ax.set_xticks(range(0, len(d), step)); ax.set_xticklabels([t.strftime("%d/%m %H:%M") for t in d.t[::step]], fontsize=7, color=INK2)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=7.5); ax.grid(axis="y", color="#e6e5e0", lw=0.6); ax.set_xlim(-0.8, len(d) + 2.5)
    r15 = s["retorno_15min_min"]; rb = s["retorno_fim_barra_min"]
    ax.set_title(f"{titulo} · {'venda' if lado < 0 else 'compra'} · {s['id']}\nretorno ao extremo: 15 min {'NÃO' if pd.isna(r15) else f'sim ({r15:.0f} min)'} · até o fim da barra {tf} {'NÃO' if pd.isna(rb) else f'sim ({rb:.0f} min)'}"
                 + (" · AMBÍGUO" if s.get("iso_ambiguo") is True else ""), loc="left", fontsize=8.5, color=INK)


def main():
    rep, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); idx = []
    for at in ("XAUUSD", "BTCUSD"):
        for tf in TFM:
            S = pd.read_csv(f"{rep}/O44_{at}_{tf}_sinais.csv", sep=";"); d_all = ST.ler(at, tf); sup = S[S.resultado_gatilho == "superou"]
            seq = sup[sup.retorno_15min_min.isna() & sup.retorno_fim_barra_min.isna() & (sup.iso_R > 0)]; vol = sup[sup.retorno_15min_min.notna()]
            rng = np.random.default_rng(44); a = seq.iloc[int(rng.integers(0, len(seq)))] if len(seq) else None; b = vol.iloc[int(rng.integers(0, len(vol)))] if len(vol) else None
            fig, axs = plt.subplots(1, 2, figsize=(16, 5.6), facecolor=SURF)
            for ax, s, t in ((axs[0], a, "deu sequência"), (axs[1], b, "voltou ao extremo")):
                ax.set_facecolor(SURF)
                if s is None: ax.axis("off"); ax.text(0.1, 0.5, f"sem caso de '{t}'", fontsize=11); continue
                painel(ax, s, d_all, tf, t)
            fig.suptitle(f"{at} · {tf} · caixa de 12 barras = {12 * TFM[tf] / 60:g} h · R0 da O43 no próprio TF (M1 só executa)", x=0.01, ha="left", fontsize=11, fontweight="bold", color=INK)
            fig.tight_layout(); f = f"{out}/O44_{at}_{tf}.png"; fig.savefig(f, dpi=110, facecolor=SURF, bbox_inches="tight"); plt.close(fig)
            idx.append({"ativo": at, "tf": tf, "arquivo": os.path.basename(f), "sequencia": None if a is None else a["id"], "candidatos_sequencia": int(len(seq)), "voltou": None if b is None else b["id"], "candidatos_voltou": int(len(vol))})
    json.dump(idx, open(f"{out}/O44_graficos_indice.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(idx, ensure_ascii=False))


if __name__ == "__main__": main()
