"""ORDEM 043 — gráficos anotados: (1) onde estava o suporte/resistência, (2) onde rompeu e fechou, (3) onde a barra seguinte superou o extremo,
(4) o que M1/M5 mostravam naquele instante. Uso: python graficos_o43.py SAIDA_REPLAY SAIDA_GRAFICOS"""
import os, sys, json
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estrategia_o39 as ST
INK, INK2, MUT, SURF = "#0b0b0b", "#52514e", "#a3a29c", "#fcfcfb"; AZUL, LAR, VERDE, VIOL = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"


def velas(ax, d, w=0.6, cor_up="#ffffff", cor_dn=INK2):
    for x, r in enumerate(d.itertuples()):
        ax.plot([x, x], [r.l, r.h], color=INK2, lw=0.9, zorder=2)
        lo, hi = min(r.o, r.c), max(r.o, r.c); ax.add_patch(Rectangle((x - w / 2, lo), w, max(hi - lo, 1e-9), facecolor=cor_up if r.c >= r.o else cor_dn, edgecolor=INK2, lw=0.8, zorder=3))


def figura(s, m15, m1, rotulo, f):
    lado = int(s["lado"]); t_b = pd.Timestamp(s["barra_rompimento"]); i_b = int(np.searchsorted(m15.t.values, np.datetime64(t_b)))
    i0, i1 = i_b - 16, i_b + 7; d = m15.iloc[i0:i1].reset_index(drop=True); xb = i_b - i0
    fig = plt.figure(figsize=(14, 6.4), facecolor=SURF); gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1], wspace=0.18)
    ax = fig.add_subplot(gs[0]); ax.set_facecolor(SURF); velas(ax, d)
    xc = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(s["caixa_inicio"]))))
    ax.axvspan(xc - 0.5, xb - 0.5, color=AZUL, alpha=0.06, zorder=0); F = s["referencia"]
    ax.axhline(F, color=AZUL, lw=2, zorder=1); ax.text(xc - 0.4, F, f" (1) {'suporte' if lado < 0 else 'resistência'} {F:.2f}", color=AZUL, va="bottom" if lado < 0 else "top", fontsize=9, fontweight="bold", bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=7)
    xp = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(s["t_pivo"])))); ax.plot(xp, F, "o", ms=8, mfc=SURF, mec=AZUL, mew=2, zorder=5)
    for n_, t in enumerate(str(s["tentativas"]).split("; ")):
        tb, tp = t.rsplit(" tipo ", 1); xt = int(np.searchsorted(d.t.values, np.datetime64(pd.Timestamp(tb))))
        ax.annotate(f"tentativa\ntipo {tp}", (xt, d.l[xt] if lado < 0 else d.h[xt]), xytext=(0, (-26 - 24 * (n_ % 2)) if lado < 0 else (22 + 24 * (n_ % 2))), textcoords="offset points", ha="center", fontsize=7, color=INK2, arrowprops=dict(arrowstyle="-", color=MUT), bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=0.5), zorder=7)
    ax.add_patch(Rectangle((xb - 0.45, d.l[xb]), 0.9, d.h[xb] - d.l[xb], fill=False, edgecolor=LAR, lw=2.2, zorder=4))
    ext = s["extremo_rompimento"]; ax.annotate(f"(2) rompeu e fechou {s['fech_rompimento']:.2f}\nextremo {ext:.2f}", (xb, d.c[xb]), xytext=(-175, -70 if lado < 0 else 70), textcoords="offset points", fontsize=8.5, color=LAR, bbox=dict(fc=SURF, ec="none", alpha=0.85, pad=1), zorder=8,
                                               fontweight="bold", arrowprops=dict(arrowstyle="->", color=LAR))
    ax.axvspan(xb + 0.5, xb + 1.5, color=VIOL, alpha=0.08, zorder=0); ax.hlines(s["T"], xb + 0.5, xb + 1.5, color=VIOL, lw=1.6, linestyle="--", zorder=5)
    ax.text(xb + 1.6, s["T"], f" gatilho {s['T']:.2f}\n (1 tick além)", color=VIOL, fontsize=8, va="center")
    if s["resultado_gatilho"] == "superou":
        ax.plot(xb + 1, s["T"], marker="v" if lado < 0 else "^", ms=11, color=VIOL, zorder=6)
        ax.annotate(f"(3) superou às {str(s['tau'])[11:16]}", (xb + 1, s["T"]), xytext=(18, -30 if lado < 0 else 26), textcoords="offset points", fontsize=8.5, color=VIOL, fontweight="bold", arrowprops=dict(arrowstyle="->", color=VIOL))
    else:
        ax.annotate(f"(3) barra seguinte: {s['resultado_gatilho']}", (xb + 1, ext), xytext=(18, -30 if lado < 0 else 26), textcoords="offset points", fontsize=8.5, color=VIOL, fontweight="bold", arrowprops=dict(arrowstyle="->", color=VIOL))
    ax.set_xticks(range(0, len(d), 4)); ax.set_xticklabels([t.strftime("%H:%M") for t in d.t[::4]], fontsize=7.5, color=INK2)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8); ax.grid(axis="y", color="#e6e5e0", lw=0.6); ax.set_title(f"M15 · {s['ativo']} · {d.t.iloc[0]:%d/%m/%Y %H:%M} a {d.t.iloc[-1]:%d/%m %H:%M} UTC", loc="left", fontsize=10, color=INK)
    yl = ax.get_ylim(); ax.set_ylim(yl[0] - (yl[1] - yl[0]) * 0.12, yl[1] + (yl[1] - yl[0]) * 0.12)
    # painel M1/M5
    a2 = fig.add_subplot(gs[1]); a2.set_facecolor(SURF)
    if s["resultado_gatilho"] == "superou":
        tau = pd.Timestamp(s["tau"]); j = int(np.searchsorted(m1.t.values, np.datetime64(tau))); e = m1.iloc[j - 15:j + 1].reset_index(drop=True)
        velas(a2, e, w=0.55); a2.axvspan(14.5, 15.5, color=VIOL, alpha=0.10); a2.axhline(s["T"], color=VIOL, lw=1.2, ls="--"); a2.axhline(ext, color=LAR, lw=1, ls=":")
        a2.annotate("M1 da superação\n(em formação: fora da leitura)", (15, e.h.iloc[-1]), xytext=(-60, 30), textcoords="offset points", ha="center", fontsize=7, color=VIOL, arrowprops=dict(arrowstyle="->", color=VIOL))
        marcas = str(s["m1_marcas_15"]).split(" ")
        for x, mk in enumerate(marcas[-15:]): a2.text(x, e.l.min() - (e.h.max() - e.l.min()) * 0.06, mk, ha="center", fontsize=7, color=INK2, family="monospace")
        g5 = (e.t.dt.floor("5min"));
        for gg in g5.unique():
            xs = np.nonzero((g5 == gg).values)[0]; fim = pd.Timestamp(gg) + pd.Timedelta(minutes=5)
            if fim <= tau and len(xs) == 5 or (fim <= tau and xs[0] > 0):
                sub = e.iloc[xs]; a2.add_patch(Rectangle((xs[0] - 0.5, sub.l.min()), len(xs), sub.h.max() - sub.l.min(), fill=False, edgecolor=VERDE, lw=1.2, ls="-", zorder=1))
        a2.set_xticks(range(0, 16, 3)); a2.set_xticklabels([t.strftime("%H:%M") for t in e.t[::3]], fontsize=7.5, color=INK2)
        cor = lambda st: {"CONFIRMA": VERDE, "CONTRARIA": LAR}.get(st, INK2)
        a2.set_title("(4) leitura no instante da superação (só M1/M5 fechadas)", loc="left", fontsize=10, color=INK)
        txt = (f"M1 (15 fechadas): {s['m1_estado']}  · avanço {s['m1_avanco']} · rejeição {s['m1_rejeicao']} · pressão {s['m1_pressao']}\n"
               f"M5 (3 fechadas): {s['m5_estado']}   [{s['m5_3']}]\n"
               f"R0: entra · R1 (M1 e M5 confirmam): {s['R1_decisao']} · R2 (M1 confirma, M5 não contrária): {s['R2_decisao']}")
        fig.text(0.535, 0.015, txt, fontsize=8, color=INK, family="monospace")
        lo_, hi_ = a2.get_ylim(); a2.set_ylim(lo_ - (hi_ - lo_) * 0.08, hi_ + (hi_ - lo_) * 0.30)
        a2.text(0.01, 0.98, f"M1 {s['m1_estado']}", transform=a2.transAxes, color=cor(s["m1_estado"]), fontsize=10, fontweight="bold", va="top")
        a2.text(0.01, 0.91, f"M5 {s['m5_estado']} (caixas verdes = M5 fechadas)", transform=a2.transAxes, color=cor(s["m5_estado"]), fontsize=9, fontweight="bold", va="top")
    else:
        a2.axis("off"); a2.text(0.02, 0.6, f"Sem superação na barra seguinte ({s['resultado_gatilho']}).\nNenhuma leitura M1/M5 é feita: o sinal expira\nno fim da barra seguinte e nada abre depois.", fontsize=10, color=INK, va="top")
    for sp in ("top", "right"): a2.spines[sp].set_visible(False)
    a2.tick_params(colors=INK2, labelsize=8)
    res = "" if pd.isna(s.get("iso_R")) else f" · desfecho (isolado, igual em R0/R1/R2 quando entram): {s['iso_R']:+.2f} R, {s['iso_motivo_saida']}" + (" · AMBÍGUO" if s.get("iso_ambiguo") is True else "")
    fig.suptitle(f"{rotulo} — {s['id']}{res}", x=0.01, ha="left", fontsize=11, color=INK, fontweight="bold")
    fig.text(0.01, 0.015, f"amplitude do rompimento {s['amp_rompimento_atr']:.2f} ATR · próximo nível a {s['prox_nivel_dist_atr'] if not pd.isna(s['prox_nivel_dist_atr']) else 'n/d'} ATR · devolução: "
             f"{('não devolveu em 15 min' if pd.isna(s.get('desfecho_devolucao_min')) else str(s['desfecho_devolucao_min']) + ' min') if s['resultado_gatilho'] == 'superou' else 'n/a'} (desfecho, não usado na decisão)", fontsize=7.5, color=INK2)
    fig.savefig(f, dpi=110, facecolor=SURF, bbox_inches="tight"); plt.close(fig)


def main():
    rep, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True); idx = []
    for at in ("XAUUSD", "BTCUSD"):
        S = pd.read_csv(f"{rep}/O43_{at}_sinais.csv", sep=";"); S["ativo"] = at; m15, m1 = ST.ler(at, "M15"), ST.ler(at, "M1"); sup = S[S.resultado_gatilho == "superou"]
        rng = np.random.default_rng(43)                                                  # escolha por sorteio fixo dentro de cada categoria (não por resultado)
        pick = lambda d: None if not len(d) else d.iloc[int(rng.integers(0, len(d)))]
        cats = [("venda · entrada confirmada (R1)", sup[(sup.lado < 0) & (sup.R1_decisao == "entra") & (sup.iso_R > 0)]),
                ("compra · entrada confirmada (R1)", sup[(sup.lado > 0) & (sup.R1_decisao == "entra") & (sup.iso_R > 0)]),
                ("toque sem superação", S[S.resultado_gatilho == "toque sem superação"]),
                ("barra seguinte não alcançou", S[S.resultado_gatilho == "não alcançou"]),
                ("superação sem confirmação (R1 e R2 descartam)", sup[(sup.R1_decisao == "descarta") & (sup.R2_decisao == "descarta")]),
                ("entrada confirmada que depois falhou", sup[(sup.R1_decisao == "entra") & (sup.iso_R < 0)])]
        for k, (rot, d) in enumerate(cats):
            s = pick(d)
            if s is None: idx.append({"ativo": at, "categoria": rot, "arquivo": None, "nota": "sem casos"}); continue
            f = f"{out}/O43_{at}_{k + 1}_{rot.split(' ')[0].replace('·', '')}.png"; figura(s, m15, m1, f"{at} · {rot}", f)
            idx.append({"ativo": at, "categoria": rot, "arquivo": os.path.basename(f), "sinal": s["id"], "candidatos": int(len(d))})
    json.dump(idx, open(f"{out}/O43_graficos_indice.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(idx, ensure_ascii=False, indent=1))


if __name__ == "__main__": main()
