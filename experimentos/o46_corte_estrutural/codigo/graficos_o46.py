"""ORDEM 046 — três exemplos anotados (sorteio fixo dentro da categoria, escopos agrupados): corte que reduziu a perda; alerta cancelado por recuperação;
corte que tirou uma operação que teria melhorado. Marca: nível original N, fechamento M1 do alerta, fechamento M15 da decisão, saída G0 e saída G1."""
import os, sys, json
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estrategia_o39 as ST, graficos_o44 as G
O44 = "/home/claude/r005/lm044/saida/replay"; INK, INK2, SURF = G.INK, G.INK2, G.SURF; AZUL, LAR, VERDE, VIOL = G.AZUL, G.LAR, G.VERDE, G.VIOL; ESC = [("XAUUSD", "M15"), ("XAUUSD", "M30"), ("BTCUSD", "M15")]


def m1_painel(ax, p, m1, m15):
    tau = pd.Timestamp(p["t_ent"]); als = json.loads(p["alertas"]); fim_z = max([pd.Timestamp(a["t_decisao15"]) for a in als] + [tau]) + pd.Timedelta(minutes=12)
    t_g1 = pd.Timestamp(p["t_sai_G1"]); t_g0 = pd.Timestamp(p["t_sai_G0"]); fim_z = max(fim_z, min(t_g0, tau + pd.Timedelta(minutes=75)) + pd.Timedelta(minutes=3))
    e = m1[(m1.t >= tau - pd.Timedelta(minutes=6)) & (m1.t <= fim_z)].reset_index(drop=True); G.velas(ax, e, w=0.55); X = lambda t: int(np.searchsorted(e.t.values, np.datetime64(t)))
    ax.axhline(p["N"], color=AZUL, lw=2); ax.text(len(e) - 0.5, p["N"], f" N nível original {p['N']:.2f}", color=AZUL, fontsize=7.5, va="center", fontweight="bold")
    ax.axvspan(X(tau) - 0.5, X(tau + pd.Timedelta(minutes=15)) - 0.5, color=VIOL, alpha=0.07); ax.text(X(tau), 0.97, "janela do alerta (15 min)", transform=ax.get_xaxis_transform(), fontsize=7, color=VIOL, va="top")
    ax.plot(X(tau), p["entrada"], marker="v" if p["lado"] < 0 else "^", ms=10, color=VIOL, zorder=7)
    for n, a in enumerate(als):
        xa = X(pd.Timestamp(a["t_alerta"]) - pd.Timedelta(minutes=1)); ax.plot(xa, e.c[xa], "o", ms=9, mfc="none", mec=LAR, mew=2, zorder=7)
        ax.annotate(f"alerta {n + 1}: M1 fecha além de N\n({a['t_alerta'][11:16]})", (xa, e.c[xa]), xytext=(-70, 30 - 46 * (n % 2)), textcoords="offset points", fontsize=7, color=LAR, arrowprops=dict(arrowstyle="->", color=LAR), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=9)
        td = pd.Timestamp(a["t_decisao15"]); xd = X(td) - 1
        if a["fim"].startswith("recuperado"):
            xr = X(m1.t.iloc[a["j_fim"]]); ax.plot(xr, e.c[xr], "s", ms=8, mfc="none", mec=VERDE, mew=2, zorder=7)
            ax.annotate("recuperou o nível → alerta cancelado", (xr, e.c[xr]), xytext=(14, -34), textcoords="offset points", fontsize=7, color=VERDE, arrowprops=dict(arrowstyle="->", color=VERDE), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=9)
        elif 0 <= xd < len(e):
            ax.axvline(xd + 0.5, color=INK2, lw=1.2, ls="--"); c15 = float(m15.c[m15.t == td - pd.Timedelta(minutes=15)].iloc[0])
            ax.text(xd + 0.6, 0.06, f"fechamento M15 {td:%H:%M}\n{c15:.2f}: {a['fim']}", transform=ax.get_xaxis_transform(), fontsize=7, color=INK, bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1))
    if p["cortou"]:
        xg = X(t_g1); ax.plot(xg, p["px_corte"], "X", ms=11, color=LAR, zorder=8)
        ax.annotate(f"saída G1 (corte) {p['px_corte']:.2f}\n{t_g1:%H:%M} · {p['R_G1']:+.2f} R", (xg, p["px_corte"]), xytext=(16, 22), textcoords="offset points", fontsize=7.5, color=LAR, fontweight="bold", arrowprops=dict(arrowstyle="->", color=LAR), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=9)
    x0 = X(t_g0)
    txt = f"saída G0 {t_g0:%d/%m %H:%M} · {p['R_G0']:+.2f} R ({'canal' if str(p['motivo_G0']).startswith('saída') else 'stop'})"
    if x0 < len(e): ax.axvline(x0, color=VERDE, lw=1.4, ls=":"); ax.text(x0, 0.9, " " + txt, transform=ax.get_xaxis_transform(), fontsize=7.5, color=INK, bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1))
    else: ax.text(0.99, 0.9, txt + " →", transform=ax.transAxes, ha="right", fontsize=7.5, color=INK, bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1))
    st = max(1, len(e) // 8); ax.set_xticks(range(0, len(e), st)); ax.set_xticklabels([t.strftime("%H:%M") for t in e.t[::st]], fontsize=7, color=INK2); ax.set_xlim(-0.8, len(e) + 7)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=7)


def main():
    out = sys.argv[1]; P = []
    for at, tf in ESC:
        x = pd.read_csv(f"{out}/O46_{at}_{tf}_pareado.csv", sep=";"); x["ativo"], x["tf"] = at, tf; P.append(x)
    P = pd.concat(P, ignore_index=True); rng = np.random.default_rng(46)
    cats = [("corte que reduziu a perda", P[P.cortou & (P.R_G0 < 0) & (P.R_G1 > P.R_G0)]), ("alerta cancelado: o preço recuperou o nível", P[(P.recuperados > 0) & ~P.cortou & ~P.empate]),
            ("corte que tirou uma operação que teria melhorado", P[P.cortou & (P.R_G1 < P.R_G0)])]
    fig, axs = plt.subplots(2, 3, figsize=(22, 10.5), facecolor=SURF, gridspec_kw={"height_ratios": [1, 1.1]}); idx = []
    for col, (rot, d) in enumerate(cats):
        p = d.iloc[int(rng.integers(0, len(d)))]; at, tf = p["ativo"], p["tf"]; s = pd.read_csv(f"{O44}/O44_{at}_{tf}_sinais.csv", sep=";").set_index("id").loc[p["id"]].copy(); s["id"] = p["id"]
        d_all = ST.ler(at, tf); m1 = ST.ler(at, "M1"); m15 = ST.ler(at, "M15")
        for r_ in (0, 1): axs[r_, col].set_facecolor(SURF)
        G.painel(axs[0, col], s, d_all, tf, f"{at} {tf} · {rot}")
        if p["cortou"]:
            ib = int(np.searchsorted(d_all.t.values, np.datetime64(pd.Timestamp(s["barra_rompimento"])))); xg = int(np.searchsorted(d_all.t.values, np.datetime64(pd.Timestamp(p["t_sai_G1"])), side="right")) - 1 - (ib - 15)
            axs[0, col].plot(xg, p["px_corte"], "X", ms=10, color=LAR, zorder=9); axs[0, col].annotate("saída G1", (xg, p["px_corte"]), xytext=(-10, -26 if p["lado"] > 0 else 18), textcoords="offset points", fontsize=7.5, color=LAR, fontweight="bold")
        m1_painel(axs[1, col], p, m1, m15); axs[1, col].set_title(f"M1 · G0 {p['R_G0']:+.2f} R × G1 {p['R_G1']:+.2f} R (diferença {p['R_G1'] - p['R_G0']:+.2f} R)", loc="left", fontsize=9, color=INK)
        idx.append({"categoria": rot, "id": p["id"], "ativo": at, "tf": tf, "candidatos": int(len(d)), "R_G0": round(float(p["R_G0"]), 3), "R_G1": round(float(p["R_G1"]), 3)})
    fig.suptitle("O46 · corte estrutural (alerta M1 + confirmação M15) × saída original — replay, nenhuma ordem", x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout(); fig.savefig(f"{out}/graficos/O46_exemplos.png", dpi=100, facecolor=SURF, bbox_inches="tight"); plt.close(fig)
    json.dump(idx, open(f"{out}/graficos/O46_graficos_indice.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(idx, ensure_ascii=False))


if __name__ == "__main__": main()
