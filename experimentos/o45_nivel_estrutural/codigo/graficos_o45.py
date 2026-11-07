"""ORDEM 045 — exemplos anotados: B que depois avançou, C que perdeu e C vencedora (sorteio fixo dentro da categoria).
Em cima: contexto no próprio TF (caixa, nível, rompimento, gatilho, saída). Embaixo: M1 em torno do gatilho, com extremo E, nível N, janela de 15 min e o fechamento que define o grupo."""
import os, sys, json
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estrategia_o39 as ST, graficos_o44 as G
O44 = "/home/claude/r005/lm044/saida/replay"; INK, INK2, SURF = G.INK, G.INK2, G.SURF; AZUL, LAR, VERDE, VIOL = G.AZUL, G.LAR, G.VERDE, G.VIOL


def painel_m1(ax, c, m1):
    tau = pd.Timestamp(c["tau"]); j = int(np.searchsorted(m1.t.values, np.datetime64(tau))); e = m1.iloc[j - 10:j + 30].reset_index(drop=True); x0 = 10
    G.velas(ax, e, w=0.55); ax.axvspan(x0 - 0.5, x0 + 14.5, color=VIOL, alpha=0.07, zorder=0); ax.text(x0, 0.97, "janela 15 min (fechamentos M1)", transform=ax.get_xaxis_transform(), color=VIOL, fontsize=7, va="top")
    ax.axhline(c["E_extremo"], color=LAR, lw=1.4, ls="--"); ax.axhline(c["N_nivel"], color=AZUL, lw=2)
    ax.text(len(e) - 0.5, c["E_extremo"], f" E extremo {c['E_extremo']:.2f}", color=LAR, fontsize=7.5, va="center"); ax.text(len(e) - 0.5, c["N_nivel"], f" N nível {c['N_nivel']:.2f}", color=AZUL, fontsize=7.5, va="center", fontweight="bold")
    for k, cor, txt in (("aviso_N", AZUL, "1º fechamento além de N"), ("aviso_E", LAR, "1º fechamento além de E")):
        if isinstance(c.get(k), str):
            xk = int(np.searchsorted(e.t.values, np.datetime64(pd.Timestamp(c[k]) - pd.Timedelta(minutes=1)))); ax.plot(xk, e.c[xk], "o", ms=9, mfc="none", mec=cor, mew=2, zorder=6)
            ax.annotate(f"{txt}\n{c[k][11:16]} ({'antes' if c['aviso_grupo_antes_da_saida'] else 'depois'} da saída)" if (k == "aviso_N") == (c["grupo"] == "C") else txt, (xk, e.c[xk]),
                        xytext=(20, 26 if k == "aviso_N" else -30), textcoords="offset points", fontsize=7, color=cor, arrowprops=dict(arrowstyle="->", color=cor), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=8)
            if c["grupo"] == "C" and k == "aviso_E": break
    ts = pd.Timestamp(c["saida"]); xs = int(np.searchsorted(e.t.values, np.datetime64(ts)))
    if xs < len(e): ax.axvline(xs, color=INK2, lw=1, ls=":"); ax.text(xs, 0.02, " saída", transform=ax.get_xaxis_transform(), fontsize=7, color=INK2)
    ax.set_xticks(range(0, len(e), 5)); ax.set_xticklabels([t.strftime("%H:%M") for t in e.t[::5]], fontsize=7, color=INK2); ax.set_xlim(-0.8, len(e) + 5)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=7); ax.set_title(f"M1 · grupo {c['grupo']} · resultado {c['iso_R']:+.2f} R", loc="left", fontsize=8.5, color=INK)


def main():
    rep, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); idx = []
    for at, tf in (("XAUUSD", "M15"), ("XAUUSD", "M30"), ("BTCUSD", "M15")):
        C = pd.read_csv(f"{rep}/O45_{at}_{tf}_classificacao.csv", sep=";"); C = C[C.completo]; S = pd.read_csv(f"{O44}/O44_{at}_{tf}_sinais.csv", sep=";").set_index("id")
        d_all = ST.ler(at, tf); m1 = ST.ler(at, "M1"); rng = np.random.default_rng(45)
        cats = [("B · voltou só ao extremo e depois avançou", C[(C.grupo == "B") & (C.iso_R > 0)]), ("C · cruzou de volta o nível e perdeu", C[(C.grupo == "C") & (C.iso_R < 0)]),
                ("C · cruzou de volta o nível e ainda venceu", C[(C.grupo == "C") & (C.iso_R > 0)])]
        fig, axs = plt.subplots(2, 3, figsize=(21, 10), facecolor=SURF, gridspec_kw={"height_ratios": [1.15, 1]})
        for col, (rot, d) in enumerate(cats):
            for r_ in (0, 1): axs[r_, col].set_facecolor(SURF)
            if not len(d): axs[0, col].axis("off"); axs[1, col].axis("off"); axs[0, col].text(0.1, 0.5, f"sem caso: {rot}", fontsize=10); idx.append({"ativo": at, "tf": tf, "categoria": rot, "id": None, "candidatos": 0}); continue
            c = d.iloc[int(rng.integers(0, len(d)))]; s = S.loc[c["id"]].copy(); s["id"] = c["id"]
            G.painel(axs[0, col], s, d_all, tf, rot); painel_m1(axs[1, col], c, m1); idx.append({"ativo": at, "tf": tf, "categoria": rot, "id": c["id"], "candidatos": int(len(d))})
        fig.suptitle(f"{at} · {tf} · O45: retorno ao extremo (E) × perda do nível estrutural (N) — diagnóstico, não altera a entrada", x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
        fig.tight_layout(); f = f"{out}/O45_{at}_{tf}.png"; fig.savefig(f, dpi=100, facecolor=SURF, bbox_inches="tight"); plt.close(fig)
    json.dump(idx, open(f"{out}/O45_graficos_indice.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(idx, ensure_ascii=False))


if __name__ == "__main__": main()
