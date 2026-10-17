# -*- coding: utf-8 -*-
"""Exemplos gráficos (acertos e erros reais), escolhidos de forma determinística: primeiro caso cronológico fora do
desenvolvimento que satisfaz a condição. Nada aqui é usado na medição."""
import os, pickle, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import alternativas as M

OUT = os.path.join(M.AQUI, "graficos"); os.makedirs(OUT, exist_ok=True)
COR = dict(up="#2a9d6f", dn="#c8553d", ev="#1f4e8c", lim="#888888", ext="#b8860b", box="#7a5cc7")


def velas(ax, a, i0, i1, ate=None):
    for k in range(i0, i1):
        c = COR["up"] if a.c[k] >= a.o[k] else COR["dn"]
        if ate is not None and k > ate:
            c = "#b9bec2"                                   # depois da decisão: não disponível no instante
        ax.vlines(k, a.l[k], a.h[k], color=c, lw=0.8)
        ax.add_patch(plt.Rectangle((k - 0.35, min(a.o[k], a.c[k])), 0.7, max(abs(a.c[k] - a.o[k]), 1e-9), color=c))
    f = (ate + 1) if ate is not None else i1
    ax.plot(range(i0, f), a.emaH[i0:f], color="#c9a227", lw=0.7); ax.plot(range(i0, f), a.emaL[i0:f], color="#c9a227", lw=0.7)


def eixo(ax, A, i0, i1):
    pos = list(range(i0, i1, 8)); ax.set_xticks(pos)
    ax.set_xticklabels([str(A.ts[p])[5:16] for p in pos], rotation=30, fontsize=7); ax.tick_params(axis="y", labelsize=7)
    ax.grid(alpha=0.15)


def grafico_p1(A, x, titulo, arq):
    a = A.a; i = x["i"]; i0, i1 = max(0, i - 50), min(a.n, i + M.H + 6)
    fig, ax = plt.subplots(figsize=(8.6, 3.6), dpi=110); velas(ax, a, i0, i1, ate=i)
    ax.axvline(i, color=COR["ev"], lw=1, ls="--", label="decisão (fechamento da barra)"); ax.axvspan(i + 0.5, i + M.H + 0.5, color="#888888", alpha=0.08, label="depois da decisão (não disponível)")
    ax.hlines(x["E"], i0, i, color=COR["ext"], lw=1, label=f"extremo da perna conhecido em i = {x['E']:.2f}")
    p = A.piv[i]
    for nome, k, v in (("último topo confirmado", p["k_topo"], p["ultimo_topo"]), ("último fundo confirmado", p["k_fundo"], p["ultimo_fundo"])):
        if k is not None and k >= i0:
            ax.plot([k], [v], marker="v" if "topo" in nome else "^", color="#444", ms=6, ls="none", label=f"{nome} (visível desde {str(A.ts[k + 2] + np.timedelta64(15, 'm'))[5:16]})")
    atr = a.atr[i]
    ax.hlines([a.c[i] + atr, a.c[i] - atr], i, i + M.H, colors=COR["lim"], linestyles=":", lw=1, label="±1 ATR a partir da decisão (só para medir depois)")
    ax.set_title(titulo, fontsize=9); ax.legend(fontsize=7, loc="best"); eixo(ax, A, i0, i1)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, arq)); plt.close(fig)


def grafico_p2(A, x, titulo, arq):
    a = A.a; i = x["i"]; i0, i1 = max(0, i - 40), min(a.n, i + M.H + 6)
    dec = x["A0"] if x["A0"] is not None else i
    fig, ax = plt.subplots(figsize=(8.6, 3.6), dpi=110); velas(ax, a, i0, i1, ate=dec)
    ax.axvspan(dec + 0.5, i1, color="#888888", alpha=0.08, label="depois da confirmação A0 (não disponível)")
    ax.hlines([x["topo"], x["fundo"]], i0, i1, colors=COR["box"], lw=1, label="caixa do M15 (armada antes do rompimento)")
    ax.axvline(i, color=COR["ev"], lw=1, ls="--", label="pendente (1º fechamento fora)")
    if x["A0"] is not None: ax.axvline(x["A0"], color="#e07a1f", lw=1.2, label="confirma A0 (máx/mín)")
    if x["A3"] is not None: ax.axvline(x["A3"], color="#2a9d6f", lw=1.2, ls="-.", label="confirma A3 (fechamento)")
    if x.get("rearmou"): ax.axvline(x["rearmou"], color="#999", lw=1, ls=":", label="motor rearma a caixa")
    alvo = x["topo"] + x["atr"] if x["lado"] > 0 else x["fundo"] - x["atr"]
    ax.axhline(alvo, color=COR["lim"], ls=":", lw=1, label="fronteira + 1 ATR (verdade)")
    ax.set_title(titulo, fontsize=9); ax.legend(fontsize=7, loc="best"); eixo(ax, A, i0, i1)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, arq)); plt.close(fig)


def primeiro(lst, cond):
    for x in sorted(lst, key=lambda e: e["i"]):
        if cond(x):
            return x


def gerar(sim):
    A = M.Ativo(sim); CV1 = M.CV1
    t0 = lambda j: (abs(A.D[j]) >= CV1.P("D_AFASTAMENTO")) or (A.Lcor[j][1] >= CV1.P("L_PERNA_TARDIA"))
    pop = A.p1(); ex0 = {x["i"]: A.exaustao(x["i"], t0) for x in pop}
    rot = M.rotular(A, pop, "A0", lambda i, d: ex0[i]["degrau"] >= 2 and ex0[i]["lado"] == -d); pend = A.pendentes(); feitos = []
    fora = lambda x: A.periodo(x["i"]) != "desenvolvimento"
    casos = [("exaustão", "FIM", "ACERTO — leu exaustão e o extremo não foi renovado em 16 barras"),
             ("exaustão", "CONTINUA", "ERRO — leu exaustão e o extremo foi renovado"),
             ("pausa", "CONTINUA", "ACERTO — leu pausa e o extremo foi renovado"),
             ("pausa", "FIM", "ERRO — leu pausa e o extremo não foi renovado em 16 barras")]
    for r, v, t in casos:
        x = primeiro(rot, lambda e: e["rot"] == r and e["verdade"] == v and A.periodo(e["i"]) == "validação")
        if x:
            arq = f"{sim}_p1_{r[:3]}_{v}.png"
            dirt = "alta" if x["d"] > 0 else "baixa"
            grafico_p1(A, x, f"{sim} · {t}\nperna de {dirt}; decisão {str(A.ts[x['i']] + np.timedelta64(15,'m'))[:16]} (corretora); "
                             f"preço {A.a.c[x['i']]:.2f}; ATR {A.a.atr[x['i']]:.2f}", arq)
            feitos.append(dict(arq=arq, titulo=t, i=x["i"], ts=str(A.ts[x["i"]]), op=A.barreiras(x["i"], x["d"])))
    casos2 = [(lambda e: e["A0"] is not None and e["A3"] is None and e["verdade"] == "FALSO", "A3 FILTROU — A0 confirmou um rompimento FALSO que A3 não confirmou"),
              (lambda e: e["A0"] is not None and e["A3"] is None and e["verdade"] == "SUSTENTADO", "A3 PERDEU — rompimento SUSTENTADO que só A0 confirmou"),
              (lambda e: e["A3"] is not None and e["verdade"] == "FALSO", "ERRO DOS DOIS — A3 (e A0) confirmaram e o rompimento falhou")]
    for k, (cond, t) in enumerate(casos2):
        x = primeiro(pend, lambda e: A.periodo(e["i"]) == "validação" and cond(e))
        if x:
            arq = f"{sim}_p2_{k}.png"
            grafico_p2(A, x, f"{sim} · {t}\npendente {str(A.ts[x['i']] + np.timedelta64(15,'m'))[:16]}; lado {'compra' if x['lado']>0 else 'venda'}; ATR {x['atr']:.2f}", arq)
            feitos.append(dict(arq=arq, titulo=t, i=x["i"], ts=str(A.ts[x["i"]])))
    return feitos


if __name__ == "__main__":
    out = {s: gerar(s) for s in ("BTCUSD", "XAUUSD")}
    json.dump(out, open(os.path.join(M.AQUI, "graficos.json"), "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:3000])
