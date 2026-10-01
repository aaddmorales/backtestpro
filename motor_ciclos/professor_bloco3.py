# -*- coding: utf-8 -*-
# ============================================================================
#  PROFESSOR — BLOCO 3 · v0 (FASE 0: SOMBRA NO LABORATORIO)
#  VERSAO: 0.1 | BUILD: 2026-09-10b-ranking-contextual | exige: bloco2 v1.4
#  Registro: Feito00167 | Spec: BLOCO3_SPEC_v1.0.md (Feito00165)
#  INTERNO (nunca distribui) — Lei de 09/ago.
#
#  A PRIMEIRA TAREFA (os 7 passos do dono, spec §4):
#    etiqueta cada trade das celulas SELADAS com o CENARIO do instante da
#    entrada (FichaSerie no k — anti-lookahead POR CONSTRUCAO), separa o
#    desempenho por cenario, imprime o RANKING CONTEXTUAL, e roda a RODADA 4:
#    Seletor da Config Oficial x Seletor apoiado pelo mapa do Bloco 3.
#
#  CENARIOS v0 — GROSSOS (spec §4, antidoto da fragmentacao; max 9 buckets):
#    alinhamento com o territorio 4H {favor, neutro, contra}
#      x sessao {asia <08h, europa 08-16h, ny >=16h}  [REF horas do CSV]
#  PISO DE AMOSTRA: bucket com n<30 = "anedota" — declarado, nunca usado.
#
#  ANTI-LOOKAHEAD DE META-NIVEL: o mapa usado na RODADA 4 nasce APENAS dos
#  trades da METADE A; a metade B julga CEGA. A tabela do ano inteiro e
#  impressa SO para estudo, nunca para decidir.
#
#  AUTORIDADES TESTADAS (spec §8 Fase 3, em laboratorio):
#    R4a  re-rank : pf efetivo = PF contextual (metade A) quando n>=30
#    R4b  re-rank + bloqueio: cenario com PF_A<1 e n>=30 -> recusa bloco3_incompativel
#  O Bloco 3 contextualiza; o Seletor escolhe; os portoes autorizam; o Ciclo corta.
# ============================================================================
from __future__ import annotations
import sys, os
from collections import defaultdict
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import numpy as np, pandas as pd

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path: sys.path.insert(0, _AQUI)
import bloco1_motor_v3 as B1
import professor_cards_v19 as PC
import professor_bloco2 as B2

B3_VERSAO = "0.5"; BUILD = "2026-09-14a-leva-v3"
# v0.5 (Feito00180): CONFIG = LEVA TRADER PRO v3 completa (Feitos 00174/00177)
# — 24 meses, custo liquido v20, JP225 na config-R. A RODADA 4 re-julga o mapa
# contextual sobre as fundacoes definitivas; a sombra so vira Fase 1 (viva)
# onde atravessar AQUI. Lei nº1 do mapa segue: exige Lista rica.
# v0.4: XTIUSD com a CONFIG-24m (Feito00169, regua B coerente v1.5):
#       B3_N=6 · top-2 · sem territorio — cega de UM ANO (2.22). Aguarda carimbo.
# v0.3: flag --grosso — cenarios so por ALINHAMENTO ao territorio (3 buckets),
# o antidoto da fragmentacao (spec §4/§9.1) pro ativo de amostra curta (XTI).
# Historico V2 auditado 10/set: museu de testes de agosto (janelas <=6m dentro
# dos 12m atuais) — NAO estende amostra; opcao morta pelo fato, declarado.
# v0.2: correcao pega no fumo — o re-rank preserva a OCUPACAO top-K (ranking
# vivo reordena quem senta; nunca reabre a lista inteira — licao da Rodada 2).
PISO_N = 30            # [REF] piso de amostra por bucket
LEVA = ["XAUUSD", "US30", "BTCUSD", "USDJPY", "JP225",
        "GBPJPY", "EURUSD", "GBPUSD", "DE40", "XTIUSD"]   # leva v3 (00174/00177)
CONFIG_OFICIAL = {"XAUUSD": (6, 13), "US30": (6, 14), "BTCUSD": (6, 5),
                  "USDJPY": (24, 4), "JP225": (24, 3), "GBPJPY": (12, 2),
                  "EURUSD": (12, 3), "GBPUSD": (6, 2), "DE40": (12, 2),
                  "XTIUSD": (6, 2)}

def sessao(ts):
    h = pd.Timestamp(ts).hour
    return "asia" if h < 8 else ("europa" if h < 16 else "ny")

def alinh(ter_k, lado):
    if ter_k == 0: return "neutro"
    return "favor" if ter_k == lado else "contra"

MODO_CEN = "fino"          # fino = alinhamento x sessao (9) | grosso = so alinhamento (3)
def cenario(ter, ts15, k, lado):
    a = alinh(int(ter[k]), lado)
    return a if MODO_CEN == "grosso" else f"{a}·{sessao(ts15[k])}"

# ============================================================================
def etiquetar(lt, ativo, lista, F15, fichas, ter):
    """Passos 2-4 do dono: re-simula cada celula selada (caminho ancorado) e
    etiqueta cada trade com o cenario do instante da entrada."""
    fn = {cid: f for cid, _n, f in PC.CARDS}
    ts15 = F15.ts; linhas = []
    for j, cel in enumerate(lista):
        B2._disp("etiqueta", f"{cel['nome'][:28]} {cel['tf']}", (j + 1) / len(lista))
        F = fichas[cel["tf"]]
        T = PC.simular_card(F, fn[cel["card"]](F, F.D), F15=F15)
        if T is None or not len(T): continue
        for _, r in T.iterrows():
            k = int(np.searchsorted(ts15, np.datetime64(r["ts"]), side="right")) - 1
            if k < 0: continue
            linhas.append(dict(card=cel["card"], tf=cel["tf"], ts=r["ts"],
                               lado=int(r["lado"]) if "lado" in r else 0,
                               pts=float(r["pts"]),
                               cen=cenario(ter, ts15, k, int(r.get("lado", 0)))))
    return pd.DataFrame(linhas)

def tabela_ctx(E):
    """P(celula paga | cenario): PF, n, pts/trade por (celula, cenario)."""
    tab = {}
    for (cd, tf, cen), g in E.groupby(["card", "tf", "cen"]):
        gan = g.pts[g.pts > 0].sum(); per = -g.pts[g.pts < 0].sum()
        pf = gan / per if per > 0 else (99.0 if gan > 0 else 0.0)
        tab[(cd, tf, cen)] = dict(n=len(g), pf=round(float(pf), 2),
                                  med=round(float(g.pts.mean()), 1))
    return tab

# ============================================================================
def rodar_ativo(pasta, ativo):
    print("=" * 78)
    nb3, K = CONFIG_OFICIAL.get(ativo, (24, None))
    print(f"BLOCO 3 v{B3_VERSAO} — RANKING CONTEXTUAL + RODADA 4 | {ativo} | "
          f"config oficial: B3_N={nb3}, top-{K if K else '?'} | bloco2 v{B2.B2_VERSAO}")
    if not PC._aplicar_ficha(ativo, pasta):
        print("   sem ficha/CSV — PULADO"); return None
    lista = B2.carregar_lista(ativo)
    if not lista: print("   sem celulas seladas — PULADO"); return None
    if K is None:
        K = min(3, len(lista)); print(f"   [REF] ativo fora da Config Oficial — top-{K} provisorio")
    lt = B1.LeitorMultiTF(pasta, ativo).carregar()
    F15 = B1.FichaSerie(lt, "M15", ativo)
    fichas = {"M15": F15}
    for tf in sorted({c["tf"] for c in lista}):
        if tf not in fichas:
            if tf not in lt.andares:
                lista = [c for c in lista if c["tf"] != tf]; continue
            fichas[tf] = B1.FichaSerie(lt, tf, ativo)
    ter = B2.preparar_territorio(lt, F15)
    ts15 = F15.ts

    # ---- etiquetagem + tabelas -------------------------------------------
    E = etiquetar(lt, ativo, lista, F15, fichas, ter)
    B2._disp_fim()
    if E.empty: print("   zero trades etiquetados — PULADO"); return None
    meio = E.ts.min() + (E.ts.max() - E.ts.min()) / 2
    tab_ano = tabela_ctx(E)
    tab_A = tabela_ctx(E[E.ts < meio])          # o mapa da RODADA 4: SO metade A

    print(f"   RANKING CONTEXTUAL ({ativo}) — ano inteiro, SO PARA ESTUDO "
          f"(buckets n<{PISO_N} = anedota, marcados):")
    pf_glob = {(c["card"], c["tf"]): c["pf"] for c in lista}
    for cel in lista:
        ch = (cel["card"], cel["tf"])
        cns = {cen: v for (cd, tf, cen), v in tab_ano.items() if (cd, tf) == ch}
        if not cns: continue
        partes = []
        for cen in sorted(cns, key=lambda c: -cns[c]["pf"]):
            v = cns[cen]
            marca = "" if v["n"] >= PISO_N else "*"
            partes.append(f"{cen} PF {v['pf']}{marca}(n={v['n']})")
        print(f"     {cel['nome'][:26]:26s} {cel['tf']:5s} PFglobal {cel['pf']:.2f} | " + " · ".join(partes))
    print(f"     (* = amostra < {PISO_N}: anedota declarada, o mapa NUNCA usa)")

    # ---- RODADA 4 ---------------------------------------------------------
    cand = B2.preparar_candidatos(lt, ativo, lista, F15, fichas)
    B2._disp_fim()
    def pf_ctx(card, tf, pf_glob_c, lado, k):
        v = tab_A.get((card, tf, cenario(ter, ts15, k, lado)))
        return v["pf"] if (v and v["n"] >= PISO_N) else pf_glob_c
    def pf_efetivo(cd, k):
        return pf_ctx(cd["card"], cd["tf"], cd["pf"], cd["lado"], k)
    _cels = [(c["card"], c["tf"], c["pf"]) for c in lista]
    def topk_dinamico(cd, k):
        """Elegivel se a CELULA do candidato esta no top-K do ranking VIVO da
        barra (pf contextual da metade A, lado do candidato)."""
        ranking = sorted(_cels, key=lambda c: (-pf_ctx(c[0], c[1], c[2], cd["lado"], k), -c[2], c[0]))
        topo = {(c[0], c[1]) for c in ranking[:K]}
        if (cd["card"], cd["tf"]) in topo: return True, ""
        return False, "bloco3_fora_do_topK_vivo"
    def bloqueio(cd, k):
        v = tab_A.get((cd["card"], cd["tf"], cenario(ter, ts15, k, cd["lado"])))
        if v and v["n"] >= PISO_N and v["pf"] < 1.0:
            return False, "bloco3_incompativel"
        return True, ""

    def medir(rot, pfd=None, ele=None, sub=None):
        T, rec, tri, hist, ab, fe = B2.rodar_seletor(
            lt, ativo, (sub if sub is not None else lista[:K]), F15, fichas, cand=cand,
            b3_n=nb3, rotulo=rot, pf_dinamico=pfd, elegivel=ele)
        return PC.metricas(T), rec, hist

    print(f"\n   RODADA 4 — Config Oficial x Seletor APOIADO pelo Bloco 3 "
          f"(mapa da METADE A; B = juizo CEGO):")
    m0, r0, h0 = medir("R4-base")
    mA, rA, hA = medir("R4a-rerank", pfd=pf_efetivo, ele=topk_dinamico, sub=lista)
    def bloq_e_topk(cd, k):
        ok1, m1 = topk_dinamico(cd, k)
        if not ok1: return ok1, m1
        return bloqueio(cd, k)
    mB, rB, hB = medir("R4b-rerank+bloq", pfd=pf_efetivo, ele=bloq_e_topk, sub=lista)
    B2._disp_fim()
    def linha(rot, m, extra=""):
        if m is None: print(f"   {rot:22s} (sem trades){extra}"); return
        print(f"   {rot:22s} n={m['trades']:5d} PF {m['pf']:5.2f} ({m['wf_a']:5.2f}/{m['wf_b']:5.2f}) "
              f"liq {m['liquido']:+10.0f} DD {m['dd']:9.0f}{extra}")
    linha("Config Oficial", m0)
    linha("R4a re-rank", mA, f"   [bloco3 no desempate/ordem]")
    linha("R4b re-rank+bloqueio", mB, f"   [+recusas bloco3_incompativel={rB.get('bloco3_incompativel', 0)}]")

    # veredito pela REGUA B (oficial da casa) contra a Config Oficial
    ok = {}
    for rot, m in (("R4a", mA), ("R4b", mB)):
        ok[rot] = (m is not None and m0 is not None and m["liquido"] > m0["liquido"]
                   and m["wf_a"] > 1 and m["wf_b"] > 1)
    print(f"   REGUA B (liquido > Config Oficial, metades >1): "
          f"R4a {'ATRAVESSOU' if ok['R4a'] else 'nao'} · R4b {'ATRAVESSOU' if ok['R4b'] else 'nao'}")
    if not (ok["R4a"] or ok["R4b"]):
        print("   -> o mapa v0 (cenarios grossos) NAO melhora este ativo — declarado; o numero manda.")
    return dict(ativo=ativo, m0=m0, mA=mA, mB=mB, ok=ok)

# ============================================================================
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    pasta = args[0] if args else "Test 12meses"
    ativos = LEVA if "--todos" in flags else [args[1] if len(args) > 1 else "XAUUSD"]
    if "--grosso" in flags:
        MODO_CEN = "grosso"; globals()["MODO_CEN"] = "grosso"
    print(f"PROFESSOR BLOCO 3 v{B3_VERSAO} build {BUILD} — FASE 0 (sombra no laboratorio)")
    print(f"cenarios: {MODO_CEN} ({'3 buckets: alinhamento' if MODO_CEN=='grosso' else '9 buckets: alinhamento x sessao'}) · piso n>={PISO_N} · "
          f"mapa da metade A, juizo cego na B · Regua B oficial\n")
    placar = []
    for atv in ativos:
        try:
            r = rodar_ativo(pasta, atv)
            if r: placar.append(r)
        except FileNotFoundError as e:
            print(f"   {atv}: {e}")
        except Exception as e:
            print(f"   [ERRO] {atv}: {type(e).__name__}: {e} — pulado, REPORTAR")
    if placar:
        print("\n" + "=" * 78)
        print("PLACAR DA RODADA 4 (Bloco 3 em sombra — Regua B vs Config Oficial):")
        for r in placar:
            m0, mA, mB = r["m0"], r["mA"], r["mB"]
            print(f"  {r['ativo']:8s} oficial {m0['liquido']:+10.0f} | R4a {mA['liquido'] if mA else 0:+10.0f} "
                  f"({'SIM' if r['ok']['R4a'] else 'nao'}) | R4b {mB['liquido'] if mB else 0:+10.0f} "
                  f"({'SIM' if r['ok']['R4b'] else 'nao'})")
        print("\nO Bloco 3 contextualiza; o Seletor escolhe; o numero decide; o carimbo e do dono.")
