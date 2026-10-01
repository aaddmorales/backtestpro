# -*- coding: utf-8 -*-
# ============================================================================
#  PROFESSOR — BLOCO 2 · LABORATORIO (MEDICAO SELETOR)
#  VERSAO: 1.0 | BUILD: 2026-09-08a-seletor-lab | exige: motor 3.2.B + cards 1.9
#  Registro: Feito00160 | Spec: BLOCO2_SPEC_v1.0.md (Feito00157)
#  INTERNO (nunca distribui) — Lei de 09/ago.
#
#  UM MOTOR, DOIS MODOS (decreto 08/set — divide-se a AUDITORIA, nunca o codigo):
#    MODO PRO        = card sozinho, exatamente o professor_cards_v19 (ANCORA:
#                      reproduz as celulas do pacote JSON — se nao bater, PARA).
#    MODO TRADER PRO = o SELETOR: todas as celulas COM SELO do ativo, pilha
#                      protegida (Feito00148), desempate por PF (Feito00153.2),
#                      corte no M15 pilha inteira (Feito00153.3 — inegociavel),
#                      gatilho velho nunca executa (Feito00150.5).
#
#  PROTOCOLO DE CONFERENCIA (ressalva do dono, Feito00159.3 — sem surpresas):
#    C1 ANCORA      celulas seladas re-simuladas pelo caminho v19 x pacote JSON
#    C2 DETERMINISMO seletor roda 2x — resultado byte a byte ou ALARME
#    C3 CONSERVACAO  soma dos trades = liquido; entradas = saidas + abertas
#    C4 AMOSTRA      N trades sorteados com rastro completo pro olho do dono
#    C5 RECUSAS      todo sinal nao operado registrado com motivo (LM do lab)
#
#  A LISTA do ativo = pacote_estudo_cards_<ATIVO>.json, regua do selo IDENTICA
#  ao v19: trades>=30 e PF>1 e wfA>1 e wfB>1. Numero da casa, nunca opiniao.
#  VIDA DA POSICAO: 100% Ciclo no relogio do M15 (herdada do v19, byte a byte).
#  TELEMETRIA DE INDICADORES: fonte unica = professor_cards_v19 (_ema/_rsi/
#  _boll/_macd) — este modulo RE-EXPORTA; a versao viva importara DAQUI.
# ============================================================================
from __future__ import annotations
import sys, os, json, hashlib, random
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np, pandas as pd

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path: sys.path.insert(0, _AQUI)
import bloco1_motor_v3 as B1
import professor_cards_v19 as PC

B2_VERSAO = "1.7"; BUILD = "2026-09-15d-estado-final"
#  v1.7: parametro estado_final (lista) em rodar_seletor — ao terminar, recebe
#  o retrato da pilha viva (card, tf, lado, ent, stop ATUAL, protegida) para a
#  RADIOGRAFIA do Teste Vivo 002. Zero efeito no resultado.
#  v1.6 (Feito00176 — licao do JP225: PONTOS ENGANAM quando o risco por trade
#  varia; a Fase 6 expos +2.59M pts = +57 R com DD -166 R):
#  flag --calibra-r -> a calibragem (N*,K*,T*) escolhe pela SOMA DE R da
#  metade A (entre wfA>1), e as reguas do veredito imprimem R ao lado.
#  Sem a flag: comportamento IDENTICO ao v1.5 (configs seladas intactas).
#  v1.5 (Feito00168 — coerencia de regua, divida declarada do Feito00163/D1):
#  a CALIBRAGEM (N*, K*, T*) passa a escolher pela MESMA regua oficial da casa:
#  LIQUIDO da metade A (entre configs com wfA>1; sem nenhuma, maior liqA).
#  A metade B segue JUIZ CEGO. Antes: escolha por PF-A (incoerente com Regua B).
#  v1.4 (Feito00166 — ganchos do BLOCO 3, spec v1.0 §3/§8-Fase3):
#    pf_dinamico(cd, k) -> pf efetivo   : reorganiza o ranking por barra (contexto)
#    elegivel(cd, k) -> (bool, motivo)  : bloqueio de estrategia incompativel
#  Defaults None = comportamento IDENTICO ao v1.3 (Config Oficial intacta).
#  O Bloco 3 contextualiza; o Seletor escolhe; os portoes autorizam; o Ciclo corta.
#  v1.3: parametro hook_auditoria em rodar_seletor — callback chamado a cada
#  ABERTURA com o retrato da pilha (protegida por posicao). Observabilidade
#  para a aceitacao formal (Feito00164); zero efeito no resultado.
#  v1.2 (Feito00162 — RODADA 3: O TERRITORIO DO 4H, conceito do dono 08/set,
#  validado na pesquisa profissional: HTF bias / trend day / hold-through-pullbacks):
#    territorio(k) = ultima barra de 4H FECHADA com direcao d + continuidade de
#    direcao nos andares (H1 e M30 fechados na MESMA d). Dentro de uma barra de
#    4H cabem 16xM15 e 8xM30 — as janelas de recarga com o olho no direcional.
#    Duas formas MEDIDAS lado a lado (leis intocadas: corte M15, pilha, teto):
#      T1 FILTRO:   fora do territorio = Rodada 2; dentro = SO entradas a favor
#      T2 ESTRITO:  o Seletor SO opera dentro de territorio (fora = zerado)
#    Sem lookahead: territorio da barra k usa apenas barras ja fechadas em k.
#  v1.1 (Feito00161 — MODs da rodada 2, carimbo do dono 08/set):
#    MOD1 RODADA 2a: varredura B3_N (6/12/24, escolha na metade A, cega na B)
#         + VARIANTE "B3 respeita posicao protegida" MEDIDA e impressa —
#         AGUARDA DECRETO (mexe em blindagem; numero primeiro, decisao do dono)
#    MOD2 RODADA 2b: PODA — hierarquia de ocupacao top-K da Lista (K na metade
#         A, valida CEGO na B) — o "maior PF primeiro" governando o ASSENTO
#    MOD3 diagnostico de custo por celula impresso (aplicacao: rodada 3 se preciso)
#    MOD4 veredito com AS DUAS reguas lado a lado (PF puro x liquido/DD) —
#         qual vale e decisao do dono
#    DISPLAY: ordem permanente do dono (08/set) — TODO teste com barra viva
#             no terminal (stderr), fase a fase, mesmo com stdout no arquivo.

# ---- display (ordem do dono: todo teste com barra viva) --------------------
import time as _t
_D0 = _t.time()
def _disp(fase, msg, frac):
    n = max(0, min(24, int(24 * frac)))
    sys.stderr.write(f"\r[{'█'*n}{'░'*(24-n)}] {int(100*frac):3d}% · {fase:14s} · {msg:<42.42s} {int(_t.time()-_D0):4d}s")
    sys.stderr.flush()
def _disp_fim():
    sys.stderr.write("\n"); sys.stderr.flush()

# ---- decretos (fonte: spec v1.0) -------------------------------------------
TETO_PILHA        = 5      # Feito00150.4 (revoga o teto 2)
VALIDADE_FILA_TF  = 4      # [REF] barras do TF do card, sob o principio 00153.5
DESEMPATE         = "pf"   # Feito00153.2 — maior PF primeiro
LEVA1             = ["XAUUSD", "XTIUSD", "JP225", "XAGUSD", "USTEC"]  # Feito00159.2
N_AMOSTRA         = 5      # C4

# ---- TELEMETRIA — fonte unica (decreto 1, Feito00150): re-export -----------
telemetria_ema  = PC._ema
telemetria_sma  = PC._sma
telemetria_rsi  = PC._rsi
telemetria_boll = PC._boll
telemetria_macd = PC._macd

# ============================================================================
#  A LISTA DO ATIVO — celulas COM SELO do pacote (regua identica ao v19)
# ============================================================================
def carregar_lista(ativo: str, pasta_pacotes: str = ".") -> list[dict]:
    cam = None
    for base in (pasta_pacotes, ".", "Pacotes_subidos"):
        c = os.path.join(base, f"pacote_estudo_cards_{ativo}.json")
        if os.path.exists(c): cam = c; break
    if cam is None:
        raise FileNotFoundError(f"pacote_estudo_cards_{ativo}.json nao encontrado "
                                f"(raiz ou Pacotes_subidos) — a Lista nasce do pacote, nunca de chute")
    pac = json.load(open(cam, encoding="utf-8"))
    lista = []
    for ln in pac.get("linhas", []):
        tr, pf = int(ln.get("trades", 0)), float(ln.get("profit_factor", 0))
        wa, wb = float(ln.get("wf_a_pf", 0)), float(ln.get("wf_b_pf", 0))
        if tr >= 30 and pf > 1 and wa > 1 and wb > 1:              # regua do selo (v19)
            lista.append(dict(card=ln["estrategia_id"], nome=ln["estrategia_nome"],
                              tf=ln["timeframe"], pf=pf, trades=tr, wfa=wa, wfb=wb,
                              liq=float(ln.get("retorno", 0)), dd=float(ln.get("dd", 0))))
    lista.sort(key=lambda x: -x["pf"])                             # sequencia de PF (dono)
    return lista

# ============================================================================
#  RESOLVER ENTRADAS — a metade de ENTRADA do PC.simular_card, LOGICA VERBATIM
#  (a vida NAO e simulada aqui: na pilha, a vida e conjunta). Cada candidato:
#  k15 (barra do M15 em que a posicao ABRE), ent, lado, stop0 estrutural.
# ============================================================================
def resolver_entradas(F, sinais, F15):
    df = F.D; c = df.close.values; ts = F.ts
    o15 = F15.D.open.values; ts15 = F15.ts
    A15 = F15.lt.andares[F15.andar_op]; a15v = F15.D.atr14.values
    out = []
    for (i_sin, lado, nivel, modo) in sorted(sinais, key=lambda x: x[0]):
        i_ent = None; ent = None; k_exec = None
        if modo == "fechamento":
            j = i_sin + 1
            if j >= F.n: continue
            k0 = int(np.searchsorted(ts15, ts[j], side="right")) - 1
            if k0 < 0: continue
            for k in range(k0, min(k0 + 96, F15.n)):
                if F15.corta[lado][k]: break
                if F15.B1[k] or (F15.B5[k] and not PC.IGNORAR_B5): continue
                i_ent = j; ent = float(o15[k]) if k > k0 else float(df.open.values[j])
                k_exec = k; break
        else:
            for j in range(i_sin + 1, min(i_sin + 40, F.n)):
                kj = int(np.searchsorted(ts15, ts[j], side="right")) - 1
                if kj >= 0 and F15.corta[lado][kj]: break
                if kj >= 0 and (F15.B1[kj] or (F15.B5[kj] and not PC.IGNORAR_B5)): continue
                abre, _m = B1.entrada_com_continuidade(df, i_sin, nivel, lado, j)
                if abre: i_ent = j; ent = float(c[j]); break
        if i_ent is None: continue
        if k_exec is None:
            k_exec = int(np.searchsorted(ts15, ts[i_ent], side="right")) - 1
        if k_exec < 0 or k_exec + 1 >= F15.n: continue
        mp = A15.mapas[k_exec]
        if not (mp.ultimo_fundo and mp.ultimo_topo): continue
        est = mp.ultimo_fundo[1] if lado > 0 else mp.ultimo_topo[1]
        a = float(a15v[k_exec])
        if not np.isfinite(a) or a <= 0: continue
        stop = est - lado * PC.BUFFER_ATR * a
        if (lado > 0 and stop >= ent) or (lado < 0 and stop <= ent): continue
        out.append(dict(k15=k_exec, i_sin=i_sin, ts_sin=pd.Timestamp(ts[i_sin]),
                        lado=lado, ent=ent, stop0=stop))
    return out

# ============================================================================
#  O SELETOR — MODO TRADER PRO (pilha protegida no relogio do M15)
# ============================================================================
def preparar_candidatos(lt, ativo, lista, F15, fichas_tf):
    """Candidatos de TODAS as celulas da Lista — computados UMA vez por ativo."""
    fn_por_id = {cid: fn for cid, _n, fn in PC.CARDS}
    passo15 = (F15.ts[1] - F15.ts[0]); cand = []
    for j, cel in enumerate(lista):
        _disp("candidatos", f"{cel['nome'][:28]} {cel['tf']}", (j + 1) / max(1, len(lista)))
        F = fichas_tf[cel["tf"]]
        sin = fn_por_id[cel["card"]](F, F.D)
        passo_tf = (F.ts[1] - F.ts[0])
        val15 = max(1, int(VALIDADE_FILA_TF * passo_tf / passo15))
        for cd in resolver_entradas(F, sin, F15):
            cd.update(card=cel["card"], nome=cel["nome"], tf=cel["tf"],
                      pf=cel["pf"], validade15=val15, chave=(cel["card"], cel["tf"]))
            cand.append(cd)
    cand.sort(key=lambda x: (x["k15"], -x["pf"], x["card"], x["tf"]))
    return cand

def preparar_territorio(lt, F15):
    """ter[k] = direcao do territorio na barra k do M15 (+1/-1/0), SEM lookahead:
    usa a ultima barra FECHADA de H4/H1/M30 no instante em que a barra k abre."""
    ts15 = F15.ts; n = F15.n
    ter = np.zeros(n, dtype=int)
    dirs = {}
    for tf in ("H4", "H1", "M30"):
        if tf not in lt.andares: return ter          # sem andar = sem territorio (declarado)
        df = lt.andares[tf].df
        tst = df.ts.values; passo = tst[1] - tst[0]
        d = np.sign(df.close.values - df.open.values).astype(int)
        dirs[tf] = (tst, passo, d)
    for k in range(n):
        dd = []
        for tf in ("H4", "H1", "M30"):
            tst, passo, d = dirs[tf]
            i = int(np.searchsorted(tst, ts15[k] - passo, side="right")) - 1
            if i < 0: dd = []; break
            dd.append(d[i])
        if dd and dd[0] != 0 and dd[0] == dd[1] == dd[2]:
            ter[k] = dd[0]
    return ter

def rodar_seletor(lt, ativo, lista, F15, fichas_tf, cand=None,
                  b3_n=None, b3_prot=False, rotulo="", disp=True,
                  territorio=None, modo_ter=None, hook_auditoria=None,
                  pf_dinamico=None, elegivel=None, estado_final=None):
    """Retorna (trades_df, recusas Counter, trilhas, hist_pilha)."""
    o15 = F15.D.open.values; h15 = F15.D.high.values; l15 = F15.D.low.values
    c15 = F15.D.close.values; a15v = F15.D.atr14.values; ts15 = F15.ts
    A15 = F15.lt.andares[F15.andar_op]
    passo15 = (ts15[1] - ts15[0])

    # 1) candidatos (pre-computados) filtrados ao SUBCONJUNTO da Lista em jogo
    if cand is None:
        cand = preparar_candidatos(lt, ativo, lista, F15, fichas_tf)
    chaves = {(c["card"], c["tf"]) for c in lista}
    cand = [cd for cd in cand if cd["chave"] in chaves]
    por_barra = {}
    for cd in cand: por_barra.setdefault(cd["k15"], []).append(cd)
    # B3 configuravel (MOD1) com memoizacao por (lado, barra)
    _b3P = {"B3_N_BARRAS": int(b3_n)} if b3_n else None
    _b3memo = {}
    def _b3(k, lado):
        key = (k, lado)
        if key not in _b3memo:
            _b3memo[key] = bool(B1.b3_tempo_sem_progresso(lt, ts15[k], lado, _b3P).get("corta"))
        return _b3memo[key]

    # 2) a pilha
    abertas = []            # posicoes vivas
    fila = []               # candidatos aprovados esperando protecao (validade viva)
    trades = []; recusas = Counter(); trilhas = []; hist_pilha = Counter()
    fechadas_n = 0

    def protegida(p):       # decreto 2: max(BE, estrutural+buffer) — o trailing
        return p["stop"] * p["lado"] >= p["ent"] * p["lado"]   # ja passou do BE
    def fechar(p, k, preco, motivo):
        nonlocal fechadas_n
        pts = (preco - p["ent"]) * p["lado"] / PC.PONTO - PC.SPREAD_PTS
        trades.append(dict(pts=pts, mae=p["mae"] / PC.PONTO,
                           risco=abs(p["ent"] - p["stop0"]) / PC.PONTO,
                           motivo=motivo, ts=pd.Timestamp(ts15[p["k_ent"]]),
                           card=p["card"], tf=p["tf"], lado=p["lado"],
                           ent=p["ent"], saida=preco, ts_saida=pd.Timestamp(ts15[k])))
        fechadas_n += 1
    def abrir(cd, k, preco=None):
        if hook_auditoria is not None:
            hook_auditoria(k=k, cd=cd, pilha=[dict(card=p["card"], tf=p["tf"],
                           protegida=protegida(p)) for p in abertas])
        abertas.append(dict(lado=cd["lado"], ent=(preco if preco is not None else cd["ent"]),
                            stop=cd["stop0"], stop0=cd["stop0"], mae=0.0, ntr=0,
                            k_ent=k, card=cd["card"], tf=cd["tf"]))
        trilhas.append(dict(ev="ABRE", k=k, ts=str(pd.Timestamp(ts15[k])), card=cd["card"],
                            tf=cd["tf"], lado=cd["lado"], ent=abertas[-1]["ent"],
                            stop0=cd["stop0"], pf_lista=cd["pf"], pilha=len(abertas)))

    ini = min(por_barra) if por_barra else F15.n
    _tot = max(1, F15.n - ini)
    for k in range(ini, F15.n):
        if disp and (k - ini) % 977 == 0:
            _disp("seletor", f"{rotulo} barra {k-ini}/{_tot} pilha={len(abertas)}", (k - ini) / _tot)
        # ---- VIDA das abertas (ordem do v19: stop -> B5 -> B3 -> trail -> ciclo)
        if abertas:
            lado_p = abertas[0]["lado"]
            fech_todas = None
            for p in abertas:
                p["mae"] = max(p["mae"], (p["ent"] - l15[k]) if p["lado"] > 0 else (h15[k] - p["ent"]))
            vivos = []
            for p in abertas:
                if (p["lado"] > 0 and l15[k] <= p["stop"]) or (p["lado"] < 0 and h15[k] >= p["stop"]):
                    fechar(p, k, p["stop"], "stop_trailing" if p["ntr"] else "stop")
                else:
                    vivos.append(p)
            abertas = vivos
            if abertas:
                if F15.B5[k] and not PC.IGNORAR_B5:
                    fech_todas = "B5"
                elif any((k - p["k_ent"]) >= 2 for p in abertas) and _b3(k, lado_p) \
                        and not (b3_prot and all(protegida(p) for p in abertas)):
                    fech_todas = "B3"      # variante b3_prot: pilha 100% protegida nao expira
                elif F15.corta[lado_p][k] and not F15.B1[k]:
                    fech_todas = "ciclo"
                if fech_todas:
                    if k + 1 < F15.n:
                        for p in abertas: fechar(p, k, float(o15[k + 1]), fech_todas)
                        trilhas.append(dict(ev="CORTE_PILHA", k=k, ts=str(pd.Timestamp(ts15[k])),
                                            motivo=fech_todas, n=len(abertas)))
                        abertas = []
                    fila = []            # historia morreu: fila morre junto (00150.5)
                else:
                    for p in abertas:    # trailing §5.5 — so aperta, por posicao
                        mpk = A15.mapas[k]; ak = float(a15v[k])
                        pv = (mpk.ultimo_fundo[1] if p["lado"] > 0 else mpk.ultimo_topo[1]) \
                             if (mpk.ultimo_fundo and mpk.ultimo_topo) else None
                        if pv is not None and np.isfinite(ak) and ak > 0:
                            nst = pv - p["lado"] * PC.BUFFER_ATR * ak
                            if (p["lado"] > 0 and nst > p["stop"] and nst < c15[k]) or \
                               (p["lado"] < 0 and nst < p["stop"] and nst > c15[k]):
                                p["stop"] = nst; p["ntr"] += 1
        hist_pilha[len(abertas)] += 1

        # ---- FILA (00153.5): re-julga; expira; executa quando os portoes abrem
        if fila:
            viva = []
            for cd in fila:
                if k > cd["k15"] + cd["validade15"]:
                    recusas["gatilho_expirado"] += 1; continue
                if F15.corta[cd["lado"]][k]:
                    recusas["ciclo_contra_na_fila"] += 1; continue
                viva.append(cd)
            fila = viva

        # ---- CANDIDATOS da barra + fila: os portoes do Seletor (passo 6)
        do_bar = por_barra.get(k, [])
        if pf_dinamico is None:
            pendentes = sorted(fila + do_bar, key=lambda x: (-x["pf"], x["card"], x["tf"]))
        else:
            pendentes = sorted(fila + do_bar,
                               key=lambda x: (-float(pf_dinamico(x, k)), x["card"], x["tf"]))
        fila = []
        for cd in pendentes:
            novo = cd["k15"] == k
            if elegivel is not None:
                ok_e, mot_e = elegivel(cd, k)
                if not ok_e:
                    recusas[mot_e] += 1; continue
            if modo_ter and territorio is not None:
                t = int(territorio[k])
                if modo_ter == "estrito" and t == 0:
                    recusas["fora_do_territorio"] += 1; continue
                if t != 0 and cd["lado"] != t:
                    recusas["contra_territorio"] += 1; continue
            if abertas and cd["lado"] != abertas[0]["lado"]:
                recusas["contra_historia"] += 1; continue
            if any(p["card"] == cd["card"] and p["tf"] == cd["tf"] for p in abertas):
                recusas["celula_ja_posicionada"] += 1; continue
            if len(abertas) >= TETO_PILHA:
                recusas["teto_pilha"] += 1; fila.append(cd); continue
            if abertas and not all(protegida(p) for p in abertas):
                recusas["anterior_desprotegida_fila"] += 1; fila.append(cd); continue
            if novo:
                abrir(cd, k)
            else:
                if k + 0 >= F15.n: continue
                ent2 = float(o15[k])
                if (cd["lado"] > 0 and cd["stop0"] >= ent2) or (cd["lado"] < 0 and cd["stop0"] <= ent2):
                    recusas["stop_invalido_na_fila"] += 1; continue
                abrir(cd, k, preco=ent2)

    # abertas no fim do periodo: DESCARTADAS E DECLARADAS (mesma pratica do v19)
    if estado_final is not None:
        for p in abertas:
            estado_final.append(dict(card=p["card"], tf=p["tf"], lado=p["lado"],
                                     ent=p["ent"], stop=p["stop"],
                                     protegida=bool(p["stop"] * p["lado"] >= p["ent"] * p["lado"])))
    return (pd.DataFrame(trades), recusas, trilhas, hist_pilha, len(abertas), fechadas_n)

# ============================================================================
#  C1 — ANCORA: o modo PRO reproduz o pacote (celula a celula)
# ============================================================================
def conferir_ancora(lt, ativo, lista, F15, fichas_tf):
    fn_por_id = {cid: fn for cid, _n, fn in PC.CARDS}
    print(f"   C1 ANCORA — {len(lista)} celulas seladas re-simuladas pelo caminho v19:")
    ok = True
    for _ja, cel in enumerate(lista):
        _disp("ancora", f"{cel['nome'][:28]} {cel['tf']}", (_ja + 1) / len(lista))
        F = fichas_tf[cel["tf"]]
        T = PC.simular_card(F, fn_por_id[cel["card"]](F, F.D), F15=F15)
        m = PC.metricas(T)
        bate = (m is not None and m["trades"] == cel["trades"]
                and abs(m["pf"] - cel["pf"]) < 0.0051)
        tag = "OK " if bate else ">>> DIVERGE <<<"
        if not bate: ok = False
        pf_novo = "-" if m is None else f"{m['pf']:.3f}"
        tr_novo = 0 if m is None else m["trades"]
        print(f"     {tag} {cel['nome'][:30]:30s} {cel['tf']:5s} pacote PF {cel['pf']:.3f}/"
              f"n{cel['trades']}  re-sim PF {pf_novo}/n{tr_novo}")
    return ok

# ============================================================================
#  RELATORIO POR ATIVO
# ============================================================================
def rodar_ativo(pasta, ativo, pasta_pacotes=".", com_ancora=True):
    print("=" * 78)
    print(f"MEDICAO SELETOR — {ativo} | professor_bloco2 v{B2_VERSAO} build {BUILD} | "
          f"motor {B1.MOTOR_VERSAO} | cards {PC.CARDS_VERSAO}")
    if not PC._aplicar_ficha(ativo, pasta):
        print(f"   {ativo}: sem ficha/CSV — PULADO (declarado)"); return None
    lista = carregar_lista(ativo, pasta_pacotes)
    if not lista:
        print(f"   {ativo}: ZERO celulas com selo no pacote — sem Lista, sem Seletor (declarado)")
        return None
    print(f"   LISTA ({len(lista)} celulas com selo, sequencia de PF):")
    for c in lista:
        print(f"     PF {c['pf']:5.2f}  {c['nome'][:30]:30s} {c['tf']:5s} (n={c['trades']}, wf {c['wfa']:.2f}/{c['wfb']:.2f})")
    lt = B1.LeitorMultiTF(pasta, ativo).carregar()
    if "M15" not in lt.andares:
        print("   SEM M15 na pasta — o relogio da decisao nao existe; PULADO"); return None
    F15 = B1.FichaSerie(lt, "M15", ativo)
    fichas_tf = {"M15": F15}
    for tf in sorted({c["tf"] for c in lista}):
        if tf not in fichas_tf:
            if tf not in lt.andares:
                print(f"   TF {tf} da Lista SEM DADO na pasta — celulas desse TF ignoradas (declarado)")
                lista = [c for c in lista if c["tf"] != tf]; continue
            fichas_tf[tf] = B1.FichaSerie(lt, tf, ativo)
    _disp_fim()
    if com_ancora:
        if not conferir_ancora(lt, ativo, lista, F15, fichas_tf):
            print("   >>> ANCORA DIVERGIU — o modulo NAO reproduz o banco. PARA E REPORTA. "
                  "Nada do Seletor vale ate isto bater. <<<")
            return None

    # ---- candidatos UMA vez (todas as celulas) --------------------------------
    cand = preparar_candidatos(lt, ativo, lista, F15, fichas_tf)
    _disp_fim()

    _MODO_R = "--calibra-r" in sys.argv
    def _liq_a(T):
        if T is None or not len(T): return 0.0
        meio = T.ts.min() + (T.ts.max() - T.ts.min()) / 2
        if _MODO_R:
            R = (T.pts / T.risco.replace(0, float("nan"))).fillna(0)
            return float(R[T.ts < meio].sum())
        return float(T.pts[T.ts < meio].sum())
    def _soma_R(T):
        if T is None or not len(T): return 0.0, 0.0
        R = (T.pts / T.risco.replace(0, float("nan"))).fillna(0)
        cum = R.cumsum()
        return float(R.sum()), float((cum - cum.cummax()).min())
    def medir(sub, b3n, prot, rot):
        T, rec, tri, hist, ab_fim, fech = rodar_seletor(
            lt, ativo, sub, F15, fichas_tf, cand=cand, b3_n=b3n, b3_prot=prot, rotulo=rot)
        m = PC.metricas(T)
        if m is not None:
            m["liq_a"] = _liq_a(T)
            m["soma_R"], m["dd_R"] = _soma_R(T)
        return m, T, rec, tri, hist, ab_fim, fech
    def _escolha(cands_dict):
        """Regua B coerente: maior LIQUIDO da metade A entre wfA>1; senao maior liqA."""
        ok = {k: v for k, v in cands_dict.items() if v is not None}
        if not ok: return None
        com = {k: v for k, v in ok.items() if v["wf_a"] > 1}
        base = com if com else ok
        return max(base, key=lambda k: base[k].get("liq_a", -9e18))

    def linha(rot, m, extra=""):
        if m is None:
            print(f"   {rot:22s} (sem trades){extra}"); return
        la = m.get("liq_a")
        la_s = f" liqA {la:+8.0f}" if la is not None else ""
        if m.get("soma_R") is not None:
            la_s += f" | {m['soma_R']:+7.0f} R (DD {m['dd_R']:.0f} R)"
        print(f"   {rot:22s} n={m['trades']:5d} PF {m['pf']:5.2f} ({m['wf_a']:5.2f}/{m['wf_b']:5.2f}) "
              f"liq {m['liquido']:+10.0f} DD {m['dd']:9.0f}{la_s}{extra}")

    # ---- RODADA 2a — MOD1: varredura do B3_N (Lista completa; escolha na A) ---
    print(f"\n   RODADA 2a — B3_N (calibra na metade A, valida CEGO na B; N=6 = baseline v1):")
    curva_b3 = {}
    for nb3 in (6, 12, 24):
        m = medir(lista, nb3, False, f"B3={nb3}")[0]
        curva_b3[nb3] = m; linha(f"B3_N={nb3} ({nb3*5}min)", m)
    n_star = _escolha(curva_b3) or 6
    print(f"   -> N* = {n_star} (maior LIQUIDO da metade A c/ wfA>1 — regua B coerente; a B acima e o cego)")
    m_var = medir(lista, n_star, True, f"B3={n_star}+prot")[0]
    linha(f"VARIANTE prot (N={n_star})", m_var, "   [MEDIDA — AGUARDA DECRETO: mexe em blindagem]")

    # ---- RODADA 2b — MOD2: PODA top-K sobre o N* (escolha na A, cega na B) ----
    print(f"\n   RODADA 2b — PODA top-K da Lista (sequencia de PF do dono; sobre B3_N={n_star}):")
    Ks = sorted({1, 2, 3, 5, len(lista)})
    curva_k = {}
    for K in Ks:
        m = medir(lista[:K], n_star, False, f"top{K}")[0]
        curva_k[K] = m; linha(f"top-{K}", m)
    k_star = _escolha(curva_k) or len(lista)
    print(f"   -> K* = {k_star} (maior liqA c/ wfA>1 — regua B coerente; wfB acima = validacao CEGA)")

    # ---- RODADA 3 — O TERRITORIO DO 4H (sobre N*, K*; leis intocadas) ---------
    ter = preparar_territorio(lt, F15)
    pct_ter = 100.0 * np.count_nonzero(ter) / max(1, len(ter))
    print(f"\n   RODADA 3 — TERRITORIO 4H (H4+H1+M30 fechados na mesma direcao; "
          f"{pct_ter:.0f}% das barras em territorio) sobre [N*={n_star}, top-{k_star}]:")
    m_r2 = curva_k.get(k_star)
    linha("R2 (baseline)", m_r2)
    cfgs_t = {}
    for mt, rot in (("filtro", "T1 filtro direcional"), ("estrito", "T2 so-no-territorio")):
        medir_t = rodar_seletor(lt, ativo, lista[:k_star], F15, fichas_tf, cand=cand,
                                b3_n=n_star, rotulo=f"terr-{mt}",
                                territorio=ter, modo_ter=mt)
        mm = PC.metricas(medir_t[0])
        if mm is not None: mm["liq_a"] = _liq_a(medir_t[0])
        cfgs_t[mt] = (mm, medir_t)
        linha(rot, mm)
    escolha = {"R2": m_r2}
    for mt in ("filtro", "estrito"):
        if cfgs_t[mt][0] is not None: escolha[mt] = cfgs_t[mt][0]
    t_star = _escolha(escolha) or "R2"
    print(f"   -> T* = {t_star} (maior liqA c/ wfA>1 — regua B coerente; a B acima e a validacao CEGA)")

    # ---- CONFIG FINAL: conferencias completas + relatorio -----------------------
    _disp("final", f"config N*={n_star} K*={k_star} T*={t_star}", 0.5)
    _ter_f = ter if t_star != "R2" else None
    _mt_f = t_star if t_star != "R2" else None
    def medir_f(rot):
        Tf, rec, tri, hi, ab, fe = rodar_seletor(lt, ativo, lista[:k_star], F15, fichas_tf,
                                                 cand=cand, b3_n=n_star, rotulo=rot,
                                                 territorio=_ter_f, modo_ter=_mt_f)
        return PC.metricas(Tf), Tf, rec, tri, hi, ab, fe
    m, T, recusas, trilhas, hist, abertas_fim, fechadas = medir_f("final")
    m2 = medir_f("final-2x")[0]
    _disp_fim()
    if m is None:
        print("   CONFIG FINAL: sem trades (declarado)."); return None
    det_ok = (m2 is not None and m2["trades"] == m["trades"] and abs(m2["liquido"] - m["liquido"]) < 1e-6)
    print(f"   C2 DETERMINISMO (config final, 2 rodadas): {'OK' if det_ok else '>>> ALARME <<<'}")
    soma = float(T.pts.sum()); n_ab = sum(1 for t in trilhas if t["ev"] == "ABRE")
    ok_c3 = abs(soma - m["liquido"]) < 1e-6 and n_ab == fechadas + abertas_fim
    print(f"   C3 CONSERVACAO: soma={soma:+.1f}=liq | aberturas={n_ab}=fechadas={fechadas}+abertas_fim={abertas_fim} -> {'OK' if ok_c3 else '>>> FALHA <<<'}")

    melhor = lista[0]
    print(f"\n   ── VEREDITO ({ativo}) — SELETOR[N*={n_star}, top-{k_star}, T*={t_star}] x melhor card "
          f"({melhor['nome'][:22]} {melhor['tf']}) — AS DUAS REGUAS (MOD4, decisao do dono):")
    print(f"   {'':16s} {'trades':>6s} {'PF':>6s} {'wfA':>6s} {'wfB':>6s} {'liq(pts)':>11s} {'DD':>10s}")
    print(f"   {'SELETOR':16s} {m['trades']:6d} {m['pf']:6.2f} {m['wf_a']:6.2f} {m['wf_b']:6.2f} "
          f"{m['liquido']:+11.0f} {m['dd']:10.0f}")
    print(f"   {'melhor card':16s} {melhor['trades']:6d} {melhor['pf']:6.2f} {melhor['wfa']:6.2f} "
          f"{melhor['wfb']:6.2f} {melhor['liq']:+11.0f} {melhor['dd']:10.0f}")
    r_pf  = (m["pf"] > melhor["pf"] and m["wf_a"] > 1 and m["wf_b"] > 1)
    r_liq = (m["liquido"] > melhor["liq"] and m["wf_a"] > 1 and m["wf_b"] > 1)
    print(f"   REGUA A (PF puro nas duas metades > melhor): {'ATRAVESSOU' if r_pf else 'nao atravessou'}")
    print(f"   REGUA B (liquido > melhor, metades >1, DD declarado): {'ATRAVESSOU' if r_liq else 'nao atravessou'}")

    print(f"\n   pilha (barras por profundidade): " +
          " ".join(f"{k}:{v}" for k, v in sorted(hist.items())))
    por_card = T.groupby(["card", "tf"]).agg(n=("pts", "size"), pts=("pts", "sum"))
    print("   contribuicao por celula (config final):")
    for (cd, tf), r in por_card.sort_values("pts", ascending=False).iterrows():
        print(f"     {cd:26s} {tf:5s} n={int(r['n']):4d}  {r['pts']:+10.0f} pts")
    print("   MOD3 custo por celula (liq/trade da celula ISOLADA vs spread — diagnostico, rodada 3 se preciso):")
    for cel in lista:
        med = cel["liq"] / max(1, cel["trades"])
        print(f"     {cel['nome'][:28]:28s} {cel['tf']:5s} {med:+8.1f} pts/trade  (spread {PC.SPREAD_PTS})"
              f"{'  <-- fino' if abs(med) < 3 * PC.SPREAD_PTS else ''}")
    print("   C5 RECUSAS: " + (", ".join(f"{k}:{v}" for k, v in recusas.most_common()) or "nenhuma"))
    print("   saidas: " + ", ".join(f"{k}:{v}" for k, v in Counter(T.motivo).most_common()))

    rng = random.Random(20260908)
    idx = sorted(rng.sample(range(len(T)), min(N_AMOSTRA, len(T))))
    print(f"\n   C4 AMOSTRA ({len(idx)} trades da config final — conferir no MT5):")
    for i in idx:
        r = T.iloc[i]
        print(f"     {r['ts']:%d/%m %H:%M} {('BUY' if r['lado']>0 else 'SELL'):4s} {r['card']:24s} {r['tf']:5s} "
              f"ent={r['ent']:.5g} saida={r['saida']:.5g} ({r['ts_saida']:%d/%m %H:%M}) "
              f"{r['pts']:+8.1f} pts  motivo={r['motivo']}")
    return dict(ativo=ativo, m=m, melhor=melhor, n_star=n_star, k_star=k_star, t_star=t_star,
                r_pf=r_pf, r_liq=r_liq, recusas=dict(recusas), abertas_fim=abertas_fim)

# ============================================================================
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    pasta = args[0] if args else "Test 12meses"
    pasta_pac = "."
    com_ancora = "--sem-ancora" not in flags
    ativos = LEVA1 if "--todos" in flags else [args[1] if len(args) > 1 else "XAUUSD"]
    print(f"PROFESSOR BLOCO 2 v{B2_VERSAO} — MEDICAO SELETOR | leva: {', '.join(ativos)}")
    print(f"decretos: teto={TETO_PILHA} · desempate=PF · corte=M15 pilha inteira · "
          f"validade fila={VALIDADE_FILA_TF} barras do TF [REF] · protegida=stop>=BE (Ciclo carrega)\n")
    placar = []
    for atv in ativos:
        try:
            r = rodar_ativo(pasta, atv, pasta_pac, com_ancora)
            if r: placar.append(r)
        except FileNotFoundError as e:
            print(f"   {atv}: {e} — PULADO")
        except Exception as e:
            print(f"   [ERRO] {atv}: {type(e).__name__}: {e} — pulado, REPORTAR")
    if placar:
        print("\n" + "=" * 78)
        print("PLACAR DA MEDICAO SELETOR (walk-forward, duas metades):")
        for r in placar:
            m = r["m"]
            print(f"  {r['ativo']:8s} [N*={r['n_star']:2d} top-{r['k_star']} T={r['t_star']:7s}] PF {m['pf']:5.2f} "
                  f"({m['wf_a']:.2f}/{m['wf_b']:.2f}) n={m['trades']:4d} liq {m['liquido']:+9.0f} "
                  f"| card PF {r['melhor']['pf']:.2f} liq {r['melhor']['liq']:+9.0f} "
                  f"| regua A(PF): {'SIM' if r['r_pf'] else 'nao'} · regua B(liq): {'SIM' if r['r_liq'] else 'nao'}")
        print("\nNADA SOBE SEM O CARIMBO DO DONO.")
