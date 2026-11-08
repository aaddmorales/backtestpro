"""ORDEM 049 — janelas de gráfico dos dois pilotos (REPLAY): canal EMA20 High/Low em amarelo + nível estrutural + rompimento, gatilho, entrada, saída e R,
com a leitura do canal registrada no instante e o que o modelo LM-0.2 recebe hoje. Casos: canal e estrutura concordam; divergem; neutro; deixou passar.
Sorteio fixo dentro de cada categoria (não pelo resultado). Uso: python graficos_o49.py REPLAY_DIR SAIDA_DIR"""
import os, sys, json, textwrap
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estrategia_o39 as ST, leitura_canal_o49 as LC
INK, INK2, MUT, SURF = "#0b0b0b", "#52514e", "#a3a29c", "#fcfcfb"; AZUL, LAR, VERDE, VIOL, AMAR = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e0b400"
PIL = [("XAUUSD", "M30", 30), ("BTCUSD", "M15", 15)]


def janela(ax, d, eH, eL, q, reg, mn):
    ib = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(q["barra_rompimento"]))))
    isai = ib + 2
    if isinstance(q.get("iso_t_sai"), str) and q["iso_t_sai"]:
        isai = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(q["iso_t_sai"]) if not str(q["iso_t_sai"]).isdigit() else pd.Timestamp(int(q["iso_t_sai"]))), side="right")) - 1
    i0, i1 = ib - 22, min(max(isai + 3, ib + 6), ib + 40); w = d.iloc[i0:i1].reset_index(drop=True); xb = ib - i0
    for x, r in enumerate(w.itertuples()):
        ax.plot([x, x], [r.l, r.h], color=INK2, lw=0.8, zorder=2); lo, hi = min(r.o, r.c), max(r.o, r.c)
        ax.add_patch(Rectangle((x - 0.3, lo), 0.6, max(hi - lo, 1e-9), facecolor="#ffffff" if r.c >= r.o else INK2, edgecolor=INK2, lw=0.7, zorder=3))
    xs = np.arange(len(w)); ax.plot(xs, eH[i0:i1], color=AMAR, lw=2.0, zorder=4, label="EMA20 High"); ax.plot(xs, eL[i0:i1], color=AMAR, lw=2.0, zorder=4, ls="-", label="EMA20 Low")
    lc = reg["leitura_canal"]
    for nome, cor in (("resistencia_acima", LAR), ("suporte_abaixo", VERDE)):
        z = (lc.get("estrutura") or {}).get(nome)
        if z: ax.axhspan(z["zona"][0], z["zona"][1], color=cor, alpha=0.10, zorder=0); ax.text(0.2, z["zona"][1], f" {'resistência' if nome[0] == 'r' else 'suporte'} elegível · {z['dist_atr']:.2f} ATR{' · no caminho' if z['no_caminho'] else ''}", color=cor, fontsize=7.5, va="bottom")
    F = q["referencia"]; ax.axhline(F, color=AZUL, lw=1.6, zorder=1); ax.text(len(w) - 0.5, F, f" nível da formação {F:.2f}", color=AZUL, fontsize=7.5, va="center")
    ax.add_patch(Rectangle((xb - 0.45, w.l[xb]), 0.9, w.h[xb] - w.l[xb], fill=False, edgecolor=LAR, lw=2, zorder=5)); ax.text(xb, w.h[xb], "rompimento", color=LAR, fontsize=7.5, ha="center", va="bottom")
    ax.hlines(q["T"], xb + 0.5, xb + 1.5, color=VIOL, lw=1.6, ls="--", zorder=5); ax.text(xb + 1.6, q["T"], f" gatilho {q['T']:.2f}", color=VIOL, fontsize=7.5, va="center")
    if q["resultado_gatilho"] == "superou" and pd.notna(q.get("iso_entrada")):
        ax.plot(xb + 1, q["iso_entrada"], marker="v" if q["lado"] < 0 else "^", ms=9, color=VIOL, zorder=6)
        xsai = isai - i0
        if 0 <= xsai < len(w) and pd.notna(q.get("iso_saida")):
            ax.plot(xsai, q["iso_saida"], "X", ms=9, color=VERDE if q["iso_R"] > 0 else LAR, zorder=6); ax.text(xsai, q["iso_saida"], f"  saída {q['iso_R']:+.2f} R", fontsize=7.5, color=INK, va="center")
    yl = ax.get_ylim(); ax.set_ylim(yl[0] - (yl[1] - yl[0]) * 0.08, yl[1] + (yl[1] - yl[0]) * 0.08)
    st = max(1, len(w) // 7); ax.set_xticks(range(0, len(w), st)); ax.set_xticklabels([t.strftime("%d/%m %H:%M") for t in w.t[::st]], fontsize=7, color=INK2)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=7); ax.grid(axis="y", color="#e6e5e0", lw=0.5); ax.set_facecolor(SURF); ax.legend(loc="upper left", fontsize=7, frameon=False, labelcolor=INK)
    return lc


def main():
    rep, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); idx = []
    for at, tf, mn in PIL:
        Q = pd.read_csv(f"{rep}/O49_{at}_{tf}_sinais_com_canal.csv", sep=";"); REG = json.load(open(f"{rep}/O49_{at}_{tf}_registro_por_instante.json"))
        d = ST.ler(at, tf); eH, eL = LC.emas(d.h.values.astype(float), d.l.values.astype(float)); rng = np.random.default_rng(49); sup = Q[Q.resultado_gatilho == "superou"]
        cats = [("canal e estrutura CONCORDAM (entrou)", sup[sup.concordancia == "concordam"]), ("canal e estrutura DIVERGEM — nível no caminho (entrou)", sup[sup.concordancia == "divergem"]),
                ("dentro do canal — NEUTRO (entrou)", sup[sup.concordancia == "neutro"]), ("deixou passar (barra seguinte não superou)", Q[Q.resultado_gatilho != "superou"])]
        fig, axs = plt.subplots(2, 2, figsize=(20, 12.5), facecolor=SURF)
        for ax, (rot, g) in zip(axs.ravel(), cats):
            if not len(g): ax.axis("off"); ax.text(0.1, 0.5, f"sem caso: {rot}"); continue
            q = g.iloc[int(rng.integers(0, len(g)))]; reg = REG[str(pd.Timestamp(q["barra_rompimento"]))]; lc = janela(ax, d, eH, eL, q, reg, mn)
            lm = reg["lm02_recebe_hoje"]["campos"] or {}
            res = (f"entrou {'venda' if q['lado'] < 0 else 'compra'} · {q['iso_R']:+.2f} R ({q['iso_motivo_saida']})" if q["resultado_gatilho"] == "superou" else f"não entrou: {q['resultado_gatilho']} — a barra seguinte terminou")
            ax.set_title(f"{rot}\n{q['id']} · {res}", loc="left", fontsize=9.5, color=INK, fontweight="bold")
            txt = ("LEITURA DO CANAL no fechamento da barra de rompimento (cálculo programado, sombra): " + lc.get("leitura_produzida", lc.get("ausencia", "")) +
                   f"  |  LM-0.2 (modelo treinado, M15) recebe hoje: canal_pos={lm.get('m15_canal_pos')}, canal_incl_atr={lm.get('m15_canal_incl_atr')}, canal_afast_atr={lm.get('m15_canal_afast_atr')} — sem largura, sem inclinação por média, sem relação nível × canal.")
            ax.text(0.0, -0.13, "\n".join(textwrap.wrap(txt, 150)), transform=ax.transAxes, fontsize=7.4, color=INK, va="top")
            idx.append({"piloto": f"{at} {tf}", "categoria": rot, "sinal": q["id"], "candidatos": int(len(g))})
        fig.suptitle(f"{at} {tf} · O49 · canal EMA20 High/Low (amarelo) + estrutura na leitura da LM — REPLAY (dados históricos), nenhuma ordem", x=0.01, ha="left", fontsize=12.5, fontweight="bold", color=INK)
        fig.tight_layout(rect=(0, 0.02, 1, 0.97)); fig.subplots_adjust(hspace=0.42); f = f"{out}/O49_{at}_{tf}.png"; fig.savefig(f, dpi=100, facecolor=SURF, bbox_inches="tight"); plt.close(fig)
    json.dump(idx, open(f"{out}/O49_graficos_indice.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(idx, ensure_ascii=False))


if __name__ == "__main__": main()
