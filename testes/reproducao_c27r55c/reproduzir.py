# -*- coding: utf-8 -*-
"""C27R55c — reprodução cronológica SEM dados futuros das correções C5/C6/C7 sobre o que foi GRAVADO ao vivo.
Entradas (C5/C7): cada avaliação gravada (selecao_avaliacoes) é reavaliada só com o que ela mesma registrou na barra: estrutura por TF
(continuidade.estrutura_por_tf) e os portões 1–9 gravados de cada candidato. Os portões 10/11/12 são recalculados com o código ANTERIOR
(d3aa25a, sel-6) e com o CORRIGIDO (sel-7). Saídas (C6): para cada posição, as avaliações das barras em que ela estava aberta; a regra
§5.3 usa os eventos do M15 gravados na barra e na barra anterior e os fechamentos M15 gravados (lado do rompimento = sinal do fechamento
anterior − atual). BTC: conferência adicional com o motor congelado (bt_ciclo_v1.caixa_estado) sobre os candles coletados ao vivo."""
import importlib.util, json, os, sys, collections
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(AQUI))
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9"); os.environ.setdefault("SUPABASE_SERVICE_KEY", "x"); os.environ.setdefault("BT_CV_SEGREDO", "x")
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "motor_ciclos")); sys.path.insert(0, os.path.join(REPO, "testes"))
import api as NOVO
import subprocess, tempfile
_ant = os.path.join(tempfile.mkdtemp(), "api_antigo.py")
open(_ant, "wb").write(subprocess.check_output(["git", "-C", REPO, "show", "d3aa25a:api.py"]))   # implementação anterior (sel-6 / gestao-4)
spec = importlib.util.spec_from_file_location("api_antigo", _ant); ANT = importlib.util.module_from_spec(spec); spec.loader.exec_module(ANT)

AV = json.load(open(os.path.join(AQUI, "avaliacoes.json")))
POS = json.load(open(os.path.join(AQUI, "posicoes.json")))
dt = lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00"))
kyiv = lambda d: (d + timedelta(hours=3)).strftime("%d/%m %H:%M")


def portoes(M, c, mov):
    cobj = {"estrategia": {"card": c["card"]}, "lado_num": int(c.get("lado") or 0), "sinal": {"nivel": c.get("nivel")}}
    comp = M._sel_compatibilidade(cobj, mov)
    g10 = len(comp.get("alertas_de_estrutura") or []) < 2
    g11 = M._sel_ciclo_na_entrada(cobj, mov)
    g12 = comp["grau"] >= 1
    return comp, g10, g11, g12


def elegib(c, comp, g10, g11, g12, sem9=False):
    g = dict(c.get("g") or {})
    if sem9:          # portão 9 'já escolhido' é artefato do que foi escolhido AO VIVO; no contrafactual o sinal aguardou e não foi escolhido
        g["9"] = True
    base = all(g.get(k) is True for k in ("1", "2", "3", "4", "6", "7", "8", "9"))
    if not base:
        return "aguardando" if c.get("estado") != "confirmado" else "vetada_1a9"
    if not g10:
        return "vetada_10"
    if g11["ok"] is not True:
        return ("aguardando_caixa" if g11.get("aguardar") else ("vetada_11" if g11["ok"] is False else "sem_dados_11"))
    if not g12:
        return "vetada_12"
    return "elegivel"


def chave(c, comp):
    return (-comp["grau"], -(c.get("pf") or 0), -(c.get("pfm") or 0), -(c.get("tr") or 0), c["card"], c["tf"])


linhas, valid, aguard = [], collections.Counter(), {}
for e in AV:
    est = e.get("est") or {}
    if not est.get("M15"):
        continue
    mov_a, mov_n = ANT._sel_movimento_em_formacao(est), NOVO._sel_movimento_em_formacao(est)
    res = []
    for c in (e.get("c") or []):
        ca, a10, a11, a12 = portoes(ANT, c, mov_a); cn, n10, n11, n12 = portoes(NOVO, c, mov_n)
        ea, en = elegib(c, ca, a10, a11, a12), elegib(c, cn, n10, n11, n12)
        res.append((c, ca, cn, ea, en, a11, n11))
        if e["v"] == "sel-6":                       # conferência: o código anterior recalculado reproduz o gravado ao vivo?
            valid[(ea == "elegivel") == (c.get("el") == "elegivel")] += 1
    ela = sorted([r for r in res if r[3] == "elegivel"], key=lambda r: chave(r[0], r[1]))
    eln = sorted([r for r in res if r[4] == "elegivel"], key=lambda r: chave(r[0], r[2]))
    esc_a, esc_n = (ela[0][0]["uid"] if ela else None), (eln[0][0]["uid"] if eln else None)
    mud = [r for r in res if r[3] != r[4]]
    if mud or esc_a != esc_n:
        linhas.append({"sim": e["sim"], "barra": e["b"], "v": e["v"], "mov_novo": mov_n["rotulo"], "eventos_m15": (est.get("M15") or {}).get("eventos"),
                       "escolha_gravada": e.get("esc"), "escolha_anterior": esc_a, "escolha_corrigida": esc_n,
                       "mudancas": [{"uid": r[0]["uid"], "antes": r[3], "depois": r[4], "grau_antes": r[1]["grau"], "grau_depois": r[2]["grau"],
                                     "p11_depois": r[6]["detalhe"][:160]} for r in mud]})
    for r in res:
        if r[4] == "aguardando_caixa":
            aguard.setdefault((e["sim"], r[0]["uid"]), []).append((e["b"], "aguardando_caixa"))
        elif (e["sim"], r[0]["uid"]) in aguard:
            c_ = r[0]; g_ = c_.get("g") or {}
            st = elegib(c_, r[2], *portoes(NOVO, c_, mov_n)[1:], sem9=True)
            falhas = [k for k in ("1", "2", "3", "4", "6", "7", "8") if g_.get(k) is not True]
            det = st + ("" if st == "elegivel" else " [falhou " + ",".join(falhas + ([] if r[6]["ok"] is not False else ["11"])) + "]")
            aguard[(e["sim"], r[0]["uid"])].append((e["b"], det))

print("=== conferência (avaliações sel-6 gravadas ao vivo): elegibilidade recalculada com o código anterior == gravada:", dict(valid))
print("=== C5/C7 — avaliações com mudança:", len(linhas))
for l in linhas:
    print(f"\n{l['sim']} {kyiv(dt(l['barra']))} Kyiv ({l['v']}) mov: {l['mov_novo']} | M15 {l['eventos_m15']}")
    print(f"   escolha gravada={l['escolha_gravada']} | anterior(recalc)={l['escolha_anterior']} | corrigida={l['escolha_corrigida']}")
    for m in l["mudancas"]:
        print(f"   {m['uid']}: {m['antes']} -> {m['depois']} (grau {m['grau_antes']}->{m['grau_depois']})")
entraria = {k: v for k, v in aguard.items() if any(x[1] == "elegivel" for x in v[1:])}
print("\n=== C5 — aguardaram e ficaram ELEGÍVEIS numa barra seguinte (portão 9 neutralizado):", len(entraria))
print("\n=== C5 — sinais que passaram a AGUARDAR e o que aconteceu nas barras seguintes (só o gravado em cada barra):")
for (sim, uid), seq in aguard.items():
    print(f"   {sim} {uid}: " + " → ".join(f"{kyiv(dt(b))} {s}" for b, s in seq))

# ------------------------------- C6 -------------------------------------------------------------------------
porbot = collections.defaultdict(dict)
for e in AV:
    porbot[e["sim"]][dt(e["b"])] = e
print("\n=== C6 — saídas: regra §5.3 nas barras em que cada posição estava aberta (eventos M15 gravados) ===")
res_c6 = []
for p in POS:
    k_ent = datetime.fromtimestamp((int(dt(p["ab"]).timestamp()) // 900) * 900, timezone.utc)
    t, fim = k_ent + timedelta(minutes=15), dt(p["f"])
    passos = []
    while t <= fim + timedelta(minutes=1):
        e, ep = porbot[p["sim"]].get(t), porbot[p["sim"]].get(t - timedelta(minutes=15))
        if e and ep and t <= fim:
            ev, evp = ((e.get("est") or {}).get("M15") or {}).get("eventos") or [], ((ep.get("est") or {}).get("M15") or {}).get("eventos") or []
            f, fp = e.get("f15"), ep.get("f15")
            voltou = "voltou_compressao" in ev and any(str(x).startswith(("rompimento_pendente", "rompimento_confirmado")) for x in evp)
            lado_r = (1 if float(fp) > float(f) else -1) if (voltou and f is not None and fp is not None) else 0
            outros = [x for x in ev if any(str(x).startswith(k) for k in ("sacudida", "voltou", "rompimento", "quebra", "exaust"))]
            passos.append((t, voltou, lado_r, outros))
        t += timedelta(minutes=15)
    disp = [x for x in passos if x[1] and x[2] == p["lado"]]
    contra = [x for x in passos if x[1] and x[2] == -p["lado"]]
    res_c6.append((p, passos, disp, contra))
    alvo = (f"FECHARIA na avaliação de {kyiv(disp[0][0])} (§5.3, rompimento do lado da posição voltou para a caixa)" if disp else "sem disparo da §5.3")
    print(f"op {p['id']} {p['sim']} {'compra' if p['lado'] > 0 else 'venda'} {p['card']} {p['tf']}: aberta {kyiv(dt(p['ab']))}, saiu {kyiv(dt(p['f']))} ({p['mot']}, {p['usd']}) → {alvo}"
          + (f" | voltou contra a posição (não fecha): {', '.join(kyiv(x[0]) for x in contra)}" if contra else "")
          + f" | barras avaliadas {len(passos)}; eventos M15 de pullback/sacudida sem disparo: "
          + "; ".join(f"{kyiv(x[0])} {x[3]}" for x in passos if x[3] and not (x[1] and x[2] == p["lado"]))[:400])

# conferência BTC com o motor congelado (candles coletados ao vivo, espelho cortado na barra)
try:
    import shutil
    import test_niveis_reacoes as T
    import bt_motor_leitura_hml as L
    print("\n=== C6 — conferência BTC com bt_ciclo_v1.caixa_estado nos candles coletados (sem dado posterior à barra) ===")
    for p, passos, disp, contra in res_c6:
        if p["sim"] != "BTCUSD" or dt(p["ab"]) < datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc):
            continue
        achou, sem_dado = None, False
        for (t, *_r) in passos:
            d = T._espelho_ate((t + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"))
            try:
                cx = L._caixa_m15(d, "BTCUSD")
            finally:
                shutil.rmtree(d, ignore_errors=True)
            if str(cx.get("barra") or "") < (t + timedelta(hours=3) - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M"):
                sem_dado = True; break
            if cx.get("voltou_agora") and int(cx.get("lado_do_rompimento") or 0) == p["lado"]:
                achou = (t, cx); break
        print(f"op {p['id']}: motor → " + (f"voltou_agora {kyiv(achou[0])} caixa [{achou[1]['fundo']}, {achou[1]['topo']}] rompida em {achou[1]['barra_do_rompimento']} (corretora)" if achou else ("SEM DADO (candles da coleta terminam antes da barra)" if sem_dado else "sem disparo"))
              + " | gravado → " + (kyiv(disp[0][0]) if disp else "sem disparo"))
except Exception as ex:
    print("conferência BTC não rodou:", type(ex).__name__, ex)
