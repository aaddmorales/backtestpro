# -*- coding: utf-8 -*-
"""bt_motor_leitura_hml.py — v1.0-hml (C27R14, 01/out/2026)

LEITOR DO MOTOR DOS CICLOS para a HOMOLOGAÇÃO. Só LÊ: puxa as barras FECHADAS
do MT5 demo fixado, grava o espelho com a função CONGELADA
bt_vivo_sombra.puxar_e_espelhar (v7.4, sha 47a2ade7…), roda o motor CONGELADO
bt_ciclo_v1.avaliar (v2.4, sha 9ac1af94…) uma vez por barra M15 fechada e
publica a pasta da barra + a leitura original do motor para o Conector HOMOLOG
assinar. NÃO decide, NÃO executa, NÃO envia ordem:
  · não chama sombra()/executar()/trail/proteção do bt_vivo_sombra — só
    puxar_e_espelhar;
  · antes de importar qualquer módulo do motor, mt5.order_send e
    mt5.order_check são substituídos por uma função que levanta erro;
  · recusa subir se a conta não for DEMO ou não for o login fixado;
  · o terminal é fixado pelo caminho do terminal64.exe (--terminal).
A plataforma continua sendo a ÚNICA origem de comandos (R-CICLO-01).

Uso (PowerShell):
  py bt_motor_leitura_hml.py --ativo XAUUSD --login 52648209 ^
     --terminal "C:\\Program Files\\...\\terminal64.exe" ^
     --dados C:\\BotTested_HOMOLOG\\motor\\dados

Saídas em --dados (o Conector HOMOLOG lê BT_CV_ESPELHO = esta pasta):
  SAUDE.json   batimento a cada passada (processo vivo, conta, terminal, fuso,
               última barra, último erro, hashes dos módulos)
  ATUAL.json   ponteiro ATÔMICO para a pasta da barra publicada mais recente
  barras/<AAAAmmdd_HHMM>/  espelho imutável da barra + leitura_motor.json
Reinício: a pasta da barra é imutável e o ponteiro é trocado com os.replace;
ao subir de novo, a barra já publicada não é republicada (sem duplicar).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

LEITOR_VERSAO = "1.5-hml"
CAND_VERSAO = "cand-3"
CONF_CONTRATO = "conf-rt-1"                 # confirmação em TEMPO REAL (C27R23)
VALIDADE_ENTRADA_S = 1800                   # 30 min a contar da confirmação (= IDADE_MAX de 1 barra M15 do executor congelado)
TFS_CANDIDATOS = ("M15", "M30", "H1")     # escopo da seleção (C27R19)
AQUI = os.path.dirname(os.path.abspath(__file__))
MODULOS = ("bt_ciclo_v1.py", "bt_vivo_sombra.py", "bloco1_motor_v3.py",
           "professor_cards_v19.py", "professor_bloco2.py", "professor_bloco3.py",
           "bt_ponte_ciclo_v1.py", "bt_conector_atestado.py", "bt_cv_atestado.py",
           "bt_motor_leitura_hml.py")
MANTER_BARRAS = 12


def _agora():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _sha(cam):
    try:
        with open(cam, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def _grava_json_atomico(cam, obj):
    tmp = f"{cam}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)
    os.replace(tmp, cam)


def _ler_json(cam):
    try:
        with open(cam, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _bloquear_ordens(mt5):
    def _proibido(*_a, **_k):
        raise RuntimeError("leitor_sem_ordens: o leitor do motor nunca envia ordem")
    for nome in ("order_send", "order_check"):
        if hasattr(mt5, nome):
            setattr(mt5, nome, _proibido)


_TICK_ANT = {"t": None}


def _fuso_por_tick(mt5, ativo):
    """(off_s, fonte). off = horário do servidor − UTC, em múltiplos de 15 min.
    v1.1: só confia em tick NOVO (o horário do tick avançou desde a passada
    anterior) com resíduo < 120 s. Na 1.0 um tick velho do terminal recém-ligado,
    por coincidência múltiplo de 15 min, virou fuso −28800 s por uma passada
    (02/out, 10:38 UTC: 'fuso_divergente' até o tick seguinte)."""
    try:
        tk = mt5.symbol_info_tick(ativo)
        if not tk or not tk.time:
            return None, "sem_tick"
        ant, _TICK_ANT["t"] = _TICK_ANT["t"], int(tk.time)
        if ant is None:
            return None, "aguardando_segundo_tick"
        if int(tk.time) <= ant:
            return None, "tick_parado(mercado fechado ou terminal sem cotação)"
        bruto = float(tk.time) - time.time()
        off = int(round(bruto / 900.0)) * 900
        if abs(bruto - off) > 120:
            return None, f"tick_antigo({bruto - off:+.0f}s)"
        return off, "tick_novo"
    except Exception as e:
        return None, f"erro({type(e).__name__})"


def _espera(intervalo, agora_s, periodo_publicado):
    """Segundos até a próxima passada. v1.2: perto da virada da M15 o leitor não espera o
    intervalo inteiro (na plataforma, o 1º snapshot da barra nova chegava até 20 s antes do
    motor publicar e a barra abria como 'espelho_atrasado').
      · virada dentro do intervalo -> acorda 2 s depois dela;
      · 1º minuto da barra e a barra nova ainda não publicada -> a cada 3 s;
      · resto do tempo -> o intervalo normal."""
    intervalo = max(5, int(intervalo))
    pos = agora_s % 900
    falta = 900 - pos
    if pos < 60 and periodo_publicado != int(agora_s // 900):
        return 3
    if falta < intervalo:
        return max(1, falta + 2)
    return intervalo


def _espelho_com_barra_aberta(pasta, destino):
    """Cópia do espelho com UMA barra a mais em cada timeframe: a barra que está ABERTA agora, sem
    informação nenhuma (abertura = máxima = mínima = fechamento = último fechamento conhecido).
    Por quê: o detector de eventos congelado (bloco1_motor_v3.eventos_escada) não avalia a ÚLTIMA barra
    da série, então no espelho de barras fechadas os eventos da barra que acabou de fechar só aparecem
    quando a seguinte fecha (15 min depois no M15, 1 h depois no H1). Com a barra aberta acrescentada,
    o MESMO código congelado avalia a última barra fechada — usando só dados que já existem. A prova de
    que isso não inventa nada está no teste de reprodução cronológica (resultado igual ao que o motor
    congelado grava depois, com as barras reais)."""
    import glob
    os.makedirs(destino, exist_ok=True)
    for f in os.listdir(destino):
        os.remove(os.path.join(destino, f))
    for arq in sorted(glob.glob(os.path.join(pasta, "*.csv"))):
        with open(arq, encoding="utf-8") as fh:
            linhas = [l.rstrip("\r\n") for l in fh if l.strip()]
        if len(linhas) >= 3:
            cab = linhas[0].split("\t"); a = dict(zip(cab, linhas[-2].split("\t"))); u = dict(zip(cab, linhas[-1].split("\t")))
            fmt = "%Y.%m.%d %H:%M:%S"
            ta = datetime.strptime(a["<DATE>"] + " " + a.get("<TIME>", "00:00:00"), fmt)
            tu = datetime.strptime(u["<DATE>"] + " " + u.get("<TIME>", "00:00:00"), fmt)
            nome = os.path.basename(arq)
            passo = None
            for tag, seg in (("_M1_", 60), ("_M5_", 300), ("_M15_", 900), ("_M30_", 1800), ("_H1_", 3600), ("_H4_", 14400), ("_Daily_", 86400)):
                if tag in nome:
                    passo = seg
            tn = tu + (tu - ta if passo is None else __import__("datetime").timedelta(seconds=passo))
            n = dict(u); c = u["<CLOSE>"]
            n.update({"<DATE>": tn.strftime("%Y.%m.%d"), "<OPEN>": c, "<HIGH>": c, "<LOW>": c, "<CLOSE>": c})
            if "<TIME>" in n:
                n["<TIME>"] = tn.strftime("%H:%M:%S")
            if "<TICKVOL>" in n:
                n["<TICKVOL>"] = "0"
            linhas.append("\t".join(n[k] for k in cab))
        with open(os.path.join(destino, os.path.basename(arq)), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(linhas) + "\n")
    return destino


def _confirmar_rt(B1, PC, F, F15, sinais, n_tf, n15):
    # F e F15 vêm da visão COM a barra aberta: têm uma casa a mais (índices n_tf e n15) que só serve para
    # ler corte/blindagem da barra que abre agora. Preços, sinais e stops usam apenas índices < n reais.
    """CONFIRMAÇÃO EM TEMPO REAL (contrato conf-rt-1). Mesmas condições do resolvedor do estudo
    (professor_bloco2.resolver_entradas), mas decididas só com o que já fechou:
      · fechamento: confirma quando a barra do sinal FECHA (abertura da M15 seguinte), se o Ciclo não
        corta o lado e não há blindagem; com blindagem, tenta de novo na M15 seguinte; corte cancela;
      · gatilho: confirma quando uma barra do timeframe do card FECHA com continuidade além do nível
        (B1.entrada_com_continuidade, congelada).
    O resolvedor do estudo espera barras POSTERIORES para devolver a entrada; aqui nenhuma é usada.
    Preço de referência = último preço conhecido no instante da confirmação. Stop = último pivô do M15
    ∓ BUFFER×ATR14, lidos na última M15 fechada ANTES da confirmação (o estudo lê na barra da entrada)."""
    import numpy as np
    ts = F.ts; n = int(n_tf); ts15 = F15.ts; n15 = int(n15)
    passo_tf = ts[1] - ts[0]; passo15 = ts15[1] - ts15[0]; T = ts15[n15]            # abertura da M15 que abre agora
    o15 = F15.D.open.values; c15 = F15.D.close.values; c = F.D.close.values
    A15 = F15.lt.andares[F15.andar_op]; atr15 = F15.D.atr14.values
    ign_b5 = bool(PC.IGNORAR_B5)

    def casa(lado, k):                                    # k <= n15 (n15 = a barra que abre agora)
        return bool(F15.corta[lado][k]), bool(F15.B1[k] or (F15.B5[k] and not ign_b5))

    out = []
    for (i_sin, lado, nivel, modo) in sorted(sinais, key=lambda x: x[0]):
        i_sin = int(i_sin); lado = int(lado); modo = str(modo)
        fecha_sinal = ts[i_sin] + passo_tf
        r = {"i_sin": i_sin, "lado": lado, "modo": modo, "nivel": (None if nivel is None else float(nivel)),
             "estado": "aguardando", "motivo": None, "t_conf": None, "preco_ref": None}
        if modo == "fechamento":
            if fecha_sinal > T:
                r["motivo"] = "barra do sinal ainda não consta fechada no relógio do M15"
            else:
                k0 = int(np.searchsorted(ts15, fecha_sinal, side="left"))       # M15 que abre no fechamento do sinal (n15 = agora)
                r["motivo"] = "sem casa M15 para avaliar"
                for k in range(k0, min(k0 + 96, n15 + 1)):
                    cortou, blind = casa(lado, k)
                    if cortou:
                        r.update(estado="cancelado", motivo="corte do Ciclo contra o lado antes da entrada"); break
                    if blind:
                        r["motivo"] = "blindagem ativa (B1/B5): tenta na M15 seguinte"; continue
                    if k < 1:
                        continue
                    r.update(estado="confirmado", motivo="barra do sinal fechou; Ciclo sem corte e sem blindagem",
                             t_conf=ts15[k], preco_ref=float(c15[k - 1]),
                             preco_ref_base="fechamento da última M15 antes da confirmação (último preço conhecido naquele instante)")
                    break
                else:
                    if k0 + 96 <= n15:
                        r.update(estado="expirado", motivo="96 barras M15 sem conseguir entrar")
        else:
            r["motivo"] = "armado no nível; espera uma barra fechar com continuidade"
            for j in range(i_sin + 1, min(i_sin + 40, n)):
                kj = int(np.searchsorted(ts15, ts[j], side="right")) - 1
                if kj >= 0 and F15.corta[lado][kj]:
                    r.update(estado="cancelado", motivo="corte do Ciclo contra o lado com o gatilho armado"); break
                if kj >= 0 and (F15.B1[kj] or (F15.B5[kj] and not ign_b5)):
                    continue
                abre, _m = B1.entrada_com_continuidade(F.D, i_sin, nivel, lado, j)
                if abre:
                    r.update(estado="confirmado", motivo="barra fechou além do nível com corpo a favor (continuidade)",
                             t_conf=ts[j] + passo_tf, preco_ref=float(c[j]),
                             preco_ref_base=f"fechamento da barra de continuidade ({F.andar_op})")
                    break
            else:
                if i_sin + 40 <= n:
                    r.update(estado="expirado", motivo="40 barras do timeframe sem continuidade")
        if r["estado"] == "confirmado":
            k_ref = int(np.searchsorted(ts15, r["t_conf"], side="left")) - 1     # última M15 fechada ANTES da confirmação
            mp = A15.mapas[k_ref] if 0 <= k_ref < n15 else None
            a = float(atr15[k_ref]) if mp is not None else float("nan")
            if mp is None or not (mp.ultimo_fundo and mp.ultimo_topo) or not np.isfinite(a) or a <= 0:
                r.update(estado="invalido", motivo="sem pivô ou ATR do M15 para o stop")
            else:
                est = mp.ultimo_fundo[1] if lado > 0 else mp.ultimo_topo[1]
                stop = float(est - lado * PC.BUFFER_ATR * a)
                if (lado > 0 and stop >= r["preco_ref"]) or (lado < 0 and stop <= r["preco_ref"]):
                    r.update(estado="invalido", motivo="stop estrutural do lado errado do preço")
                else:
                    r["stop"] = stop
                    r["stop_base"] = "pivô e ATR14 do M15 na última barra fechada antes da confirmação"
        out.append(r)
    return out


def _candidatos(pasta, ativo, spread_tick=None):
    """v1.3 — CANDIDATOS por timeframe (M15, M30, H1) com o código do Professor, SEM alteração:
    professor_cards (sinais dos 13 cards em barras FECHADAS de cada TF), professor_bloco2.
    resolver_entradas (entrada no relógio do M15, stop estrutural = pivô do M15 ∓ 0,3×ATR14,
    blindagens e corte do Ciclo) e preparar_territorio (H4/H1/M30). É o mesmo percurso do
    bt_vivo_sombra.decidir até a montagem dos candidatos; o Seletor (pilha) NÃO roda aqui.
    Só lê o espelho. Não decide, não escolhe e não envia nada: é telemetria para a plataforma."""
    import contextlib, io
    import numpy as np
    import bloco1_motor_v3 as B1
    import professor_cards_v19 as PC
    import professor_bloco2 as B2
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        ficha_ok = bool(PC._aplicar_ficha(ativo, pasta))
        lt = B1.LeitorMultiTF(pasta, ativo).carregar()
        F15 = B1.FichaSerie(lt, "M15", ativo)
        fichas = {"M15": F15}
        for tf in TFS_CANDIDATOS:
            if tf not in fichas and tf in lt.andares:
                fichas[tf] = B1.FichaSerie(lt, tf, ativo)
        ter = B2.preparar_territorio(lt, F15)
        # visão COM a barra aberta: o mesmo código congelado, agora avaliando a última barra FECHADA
        import tempfile
        pasta_ab = tempfile.mkdtemp(prefix="bt_aberta_")
        try:
            _espelho_com_barra_aberta(pasta, pasta_ab)
            ltp = B1.LeitorMultiTF(pasta_ab, ativo).carregar()
            F15p = B1.FichaSerie(ltp, "M15", ativo)
            fichas_p = {"M15": F15p}
            for tf in TFS_CANDIDATOS:
                if tf not in fichas_p and tf in ltp.andares:
                    fichas_p[tf] = B1.FichaSerie(ltp, tf, ativo)
        finally:
            shutil.rmtree(pasta_ab, ignore_errors=True)
    n15 = int(F15.n); k_ult = n15 - 1
    assert int(F15p.n) == n15 + 1, "visão com a barra aberta tem de ter exatamente uma M15 a mais"
    passo15 = (F15.ts[1] - F15.ts[0])
    ts_txt = lambda t: str(np.datetime_as_string(np.datetime64(t), unit="s")).replace("T", " ")
    ponto = float(getattr(PC, "PONTO", 0) or 0)
    T = F15p.ts[n15]                                   # abertura da M15 que abre agora = fechamento da última do espelho
    ign_b5 = bool(PC.IGNORAR_B5)
    slot = {"T": T, "corta": {1: bool(F15p.corta[1][n15]), -1: bool(F15p.corta[-1][n15])},
            "B1": bool(F15p.B1[n15]), "B5": bool(F15p.B5[n15] and not ign_b5),
            "B5_nota": ("B5 (fim de semana) vale nos 30 min finais de sexta no estudo; em tempo real o fim da sessão não é conhecido "
                        "e a blindagem fica ligada para a barra que abre agora" if (F15p.B5[n15] and not ign_b5) else None)}
    seg = lambda dt: int(dt / np.timedelta64(1, "s"))
    itens = []; cont = {"confirmado": 0, "aguardando": 0, "cancelado": 0, "expirado": 0, "invalido": 0}
    comp = {"confirmados_rt": 0, "com_entrada_do_estudo": 0, "mesma_barra_de_entrada": 0, "mesmo_preco": 0,
            "estudo_posiciona_antes": 0, "estudo_ainda_nao_resolveu": 0}
    for cid, nome, fn in PC.CARDS:
        for tf in TFS_CANDIDATOS:
            F = fichas.get(tf)
            if F is None:
                continue
            Fp = fichas_p.get(tf)
            if Fp is None or int(Fp.n) != int(F.n) + 1:
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                sin = fn(F, F.D)
                res = B2.resolver_entradas(F, sin, F15)          # resolvedor RETROSPECTIVO do estudo: só referência
                sin_p = [x for x in fn(Fp, Fp.D) if int(x[0]) < int(F.n)]      # sinais só em barras FECHADAS
                rt = _confirmar_rt(B1, PC, Fp, F15p, sin_p, int(F.n), n15)     # confirmação possível em TEMPO REAL
            passo_tf = (F.ts[1] - F.ts[0])
            val15 = max(1, int(B2.VALIDADE_FILA_TF * passo_tf / passo15))
            base = {"card": cid, "nome": nome, "tf": tf, "validade_m15": val15}
            est_por = {int(r["i_sin"]): r for r in res}
            for r in rt:
                i_sin = r["i_sin"]; lado = r["lado"]
                if r["estado"] in ("cancelado", "expirado", "invalido"):
                    if i_sin >= F.n - B2.VALIDADE_FILA_TF:
                        cont[r["estado"]] += 1
                    continue
                uid = f"{cid}|{tf}|{ts_txt(F.ts[i_sin])}|{lado}"
                comum = dict(base, lado=lado, uid=uid, ts_sinal=ts_txt(F.ts[i_sin]),
                             ts_sinal_fecha=ts_txt(F.ts[i_sin] + passo_tf), modo=r["modo"],
                             nivel=(None if r["nivel"] is None else round(r["nivel"], 6)),
                             corte_ciclo_contra_agora=bool(slot["corta"][lado]))
                if r["estado"] == "confirmado":
                    idade_s = seg(T - r["t_conf"])
                    if idade_s > val15 * 900:                     # fora da janela de exibição (bem depois de vencido)
                        continue
                    cont["confirmado"] += 1; comp["confirmados_rt"] += 1
                    e = est_por.get(i_sin)
                    retro = None
                    if e is not None:
                        comp["com_entrada_do_estudo"] += 1
                        mesma = bool(F15.ts[int(e["k15"])] == r["t_conf"])
                        comp["mesma_barra_de_entrada"] += 1 if mesma else 0
                        antes_s = seg(r["t_conf"] - F15.ts[int(e["k15"])])
                        comp["mesmo_preco"] += 1 if abs(float(e["ent"]) - r["preco_ref"]) <= max(ponto, 1e-9) else 0
                        comp["estudo_posiciona_antes"] += 1 if antes_s > 900 else 0
                        retro = {"barra_m15_da_entrada": ts_txt(F15.ts[int(e["k15"])]), "entrada": round(float(e["ent"]), 6),
                                 "posiciona_a_entrada_s_antes_da_confirmacao": antes_s,
                                 "stop": round(float(e["stop0"]), 6), "mesma_barra_da_confirmacao": mesma,
                                 "dif_preco_pts": (round(abs(float(e["ent"]) - r["preco_ref"]) / ponto, 1) if ponto > 0 else None),
                                 "dif_stop_pts": (round(abs(float(e["stop0"]) - r["stop"]) / ponto, 1) if ponto > 0 else None)}
                    else:
                        comp["estudo_ainda_nao_resolveu"] += 1
                    itens.append(dict(comum, estado="confirmado",
                                      confirmacao={"contrato": CONF_CONTRATO, "base": r["motivo"]},
                                      ts_confirmacao=ts_txt(r["t_conf"]), ts_entrada_m15=ts_txt(r["t_conf"]),
                                      ts_vence=ts_txt(r["t_conf"] + np.timedelta64(VALIDADE_ENTRADA_S, "s")),
                                      idade_s=idade_s, idade_m15=int(idade_s // 900),
                                      preco_ref=round(r["preco_ref"], 6), preco_ref_base=r.get("preco_ref_base"),
                                      entrada=round(r["preco_ref"], 6), stop=round(r["stop"], 6), stop_base=r.get("stop_base"),
                                      risco_pts=(round(abs(r["preco_ref"] - r["stop"]) / ponto, 1) if ponto > 0 else None),
                                      estudo_retro=retro))
                else:
                    if i_sin < F.n - B2.VALIDADE_FILA_TF:
                        continue
                    cont["aguardando"] += 1
                    itens.append(dict(comum, estado="aguardando", barras_desde_o_sinal=int(F.n - 1 - i_sin),
                                      espera=r["motivo"]))
    return {"versao": CAND_VERSAO, "ativo": ativo, "leitor": LEITOR_VERSAO,
            "codigo": {"cards": getattr(PC, "CARDS_VERSAO", None), "bloco2": getattr(B2, "B2_VERSAO", None),
                       "bloco1": getattr(B1, "MOTOR_VERSAO", None)},
            "barra_m15_corretora": ts_txt(F15.ts[k_ult]), "n15": n15,
            "agora_corretora": ts_txt(T),
            "confirmacao": {"contrato": CONF_CONTRATO, "validade_s": VALIDADE_ENTRADA_S,
                            "regra": "confirma com o que já fechou; a entrada vale 30 min a contar da confirmação e não é reaproveitada",
                            "contagem": cont, "comparacao_com_o_estudo": comp,
                            "slot_agora": {"corte_contra_compra": bool(slot["corta"][1]), "corte_contra_venda": bool(slot["corta"][-1]),
                                           "B1": bool(slot["B1"]), "B5": bool(slot["B5"]), "B5_nota": slot["B5_nota"]}},
            "tfs": {tf: {"barra_corretora": ts_txt(F.ts[F.n - 1]), "barras": int(F.n)} for tf, F in fichas.items()},
            "territorio_h4_h1_m30": int(ter[k_ult]) if len(ter) else 0,
            "blindagens_m15": {"B1": bool(slot["B1"]), "B5": bool(slot["B5"]),
                               "corte_contra_compra": bool(slot["corta"][1]),
                               "corte_contra_venda": bool(slot["corta"][-1]),
                               "base": "barra M15 que abre agora (antes, 1.3/1.4: última M15 fechada)"},
            "ficha": {"aplicada": ficha_ok, "ponto": ponto or None,
                      "spread_modelado_pts": getattr(PC, "SPREAD_PTS", None),
                      "ignora_b5": bool(getattr(PC, "IGNORAR_B5", False))},
            "spread_tick_pts": (None if spread_tick is None else int(spread_tick)),
            "contrato_do_estudo": {"stop": "pivô do M15 ∓ 0,3×ATR14 do M15", "saida": "100% Ciclo, sem alvo fixo",
                                   "frescor_para_entrada_nova": "30 min a contar da confirmação em tempo real (IDADE_MAX de 1 barra M15 do vivo)",
                                   "validade_na_fila": "4 barras do TF do card"},
            "itens": itens, "calculo_ms": int((time.time() - t0) * 1000),
            "nota": "telemetria NÃO assinada: descreve candidatos; não autoriza abertura"}


def _ema20(valores):
    """Mesma conta do motor (Andar._derivados): EMA de período 20, k = 2/21, semente = 1º valor."""
    k = 2.0 / 21.0
    e = float(valores[0])
    for v in valores[1:]:
        e = e + k * (float(v) - e)
    return e


def _canais(pasta, ativo, mt5=None):
    """v1.4 — AUDITORIA do canal EMA20 por timeframe, SEM tocar no motor: lê os mesmos andares
    (CV1.carregar_andares) e a mesma barra que CV1.avaliar usa (idx_ate do fim da M15) e registra
    barra, OHLC, EMA20 das máximas, EMA20 das mínimas e a condição que dá a direção
    (fechamento > EMA20 das máximas = alta; < EMA20 das mínimas = baixa; senão lateral).
    Com o MT5 à mão, confere contra barras FECHADAS puxadas na hora, com histórico mais longo.
    Só telemetria: não entra no atestado e não decide nada."""
    import pandas as pd
    import bt_ciclo_v1 as CV1
    A = CV1.carregar_andares(pasta, ativo)
    if "M15" not in A:
        return {"erro": "espelho sem M15"}
    i15 = A["M15"].n - 1
    fim15 = pd.Timestamp(A["M15"].ts[i15]) + pd.Timedelta(minutes=15)
    cods = {}
    if mt5 is not None:
        cods = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "Daily": mt5.TIMEFRAME_D1}
    out = {}
    for tf in CV1.ANDARES:
        nm = CV1.NOME.get(tf, tf)
        a = A.get(tf)
        if a is None:
            out[nm] = {"erro": "andar ausente no espelho"}; continue
        i = a.idx_ate(fim15 - pd.Timedelta(seconds=1))
        if i < 25:
            out[nm] = {"erro": "amostra insuficiente"}; continue
        c, eh, el = float(a.c[i]), float(a.emaH[i]), float(a.emaL[i])
        d = 1 if c > eh else (-1 if c < el else 0)
        item = {"barra_corretora": str(pd.Timestamp(a.ts[i])), "fechada": True,
                "fonte": "espelho do MT5 (copy_rates_from_pos a partir da posição 1: só barras fechadas)",
                "o": float(a.o[i]), "h": float(a.h[i]), "l": float(a.l[i]), "c": c,
                "simbolo": ativo, "timeframe": nm,
                "ema20_maximas": round(eh, 6), "ema20_minimas": round(el, 6), "dir": d,
                "base_ema": {"periodo": 20, "fator": "2/21", "sobre": "máximas e mínimas", "inicializacao": "primeira barra do espelho",
                             "barras": int(a.n), "erro_de_inicializacao": "desprezível acima de ~150 barras"},
                "condicao": ("fechamento > EMA20 das máximas" if d > 0 else
                             ("fechamento < EMA20 das mínimas" if d < 0 else
                              "fechamento entre a EMA20 das mínimas e a das máximas")),
                "barras_no_espelho": int(a.n)}
        if tf in cods:
            try:
                r = mt5.copy_rates_from_pos(ativo, cods[tf], 1, 1000)
                if r is None or len(r) < 60:
                    item["mt5"] = {"erro": f"MT5 devolveu {0 if r is None else len(r)} barras", "estado": "não conferido"}
                elif str(pd.to_datetime(int(r[-1]["time"]), unit="s")) != item["barra_corretora"]:
                    # virada: o MT5 já fechou outra barra (ou ainda não fechou a do espelho) — não é erro de cálculo
                    item["mt5"] = {"simbolo": ativo, "timeframe": nm, "barras": int(len(r)),
                                   "barra_corretora": str(pd.to_datetime(int(r[-1]["time"]), unit="s")),
                                   "mesma_barra": False, "estado": "aguardando sincronização",
                                   "ohlc_confere": None, "ema_confere": None,
                                   "nota": "barras diferentes no espelho e no MT5: OHLC e EMA não são comparados"}
                else:
                    u = r[-1]
                    mh, ml = _ema20([x["high"] for x in r]), _ema20([x["low"] for x in r])
                    tol = max(abs(c) * 1e-6, 1e-6)
                    mesma = str(pd.to_datetime(int(u["time"]), unit="s")) == item["barra_corretora"]
                    item["mt5"] = {"simbolo": ativo, "timeframe": nm,
                                   "barras": int(len(r)), "barra_corretora": str(pd.to_datetime(int(u["time"]), unit="s")),
                                   "tolerancia_ohlc": tol, "tolerancia_ema_relativa": 1e-5,
                                   "o": float(u["open"]), "h": float(u["high"]), "l": float(u["low"]), "c": float(u["close"]),
                                   "ema20_maximas": round(mh, 6), "ema20_minimas": round(ml, 6),
                                   "mesma_barra": bool(mesma),
                                   "ohlc_confere": bool(mesma and all(abs(float(u[k]) - item[q]) <= tol for k, q in
                                                                      (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c")))),
                                   "ema_confere": bool(mesma and abs(mh - eh) <= max(abs(eh) * 1e-5, 1e-6)
                                                       and abs(ml - el) <= max(abs(el) * 1e-5, 1e-6)),
                                   "nota": "EMA20 recalculada sobre até 1000 barras fechadas do MT5; não é a leitura do indicador do gráfico"}
                    item["mt5"]["estado"] = "confere" if (item["mt5"]["ohlc_confere"] and item["mt5"]["ema_confere"]) else "diverge"
            except Exception as e:
                item["mt5"] = {"erro": f"{type(e).__name__}: {e}"[:200]}
        out[nm] = item
    return out


def _ultima_linha_m15(pasta, ativo):
    import glob
    arqs = sorted(glob.glob(os.path.join(pasta, f"{ativo}_M15_*.csv")))
    if not arqs:
        return None
    with open(arqs[-1], encoding="utf-8") as f:
        linhas = [l.rstrip("\r\n") for l in f if l.strip()]
    if len(linhas) < 2:
        return None
    cab = linhas[0].split("\t")
    val = linhas[-1].split("\t")
    d = dict(zip(cab, val))
    return {"barra_corretora": f"{d['<DATE>'].replace('.', '-')} {d['<TIME>']}",
            "o": float(d["<OPEN>"]), "h": float(d["<HIGH>"]),
            "l": float(d["<LOW>"]), "c": float(d["<CLOSE>"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Leitor do motor dos Ciclos (homolog, só leitura)")
    ap.add_argument("--ativo", required=True)
    ap.add_argument("--login", required=True, type=int)
    ap.add_argument("--terminal", required=True, help="caminho do terminal64.exe da instalação DEMO")
    ap.add_argument("--dados", required=True, help="pasta de saída (BT_CV_ESPELHO do conector)")
    ap.add_argument("--intervalo", type=int, default=20)
    ap.add_argument("--uma-vez", action="store_true", help="uma passada e sai (prova)")
    a = ap.parse_args(argv)

    if "--executa" in sys.argv:
        raise SystemExit("o leitor não aceita --executa")
    dados = os.path.abspath(a.dados)
    os.makedirs(os.path.join(dados, "barras"), exist_ok=True)
    os.chdir(dados)                       # memória do CV1 é só LIDA aqui (gravar_mem=False)
    if AQUI not in sys.path:
        sys.path.insert(0, AQUI)

    import MetaTrader5 as mt5
    _bloquear_ordens(mt5)
    if not os.path.isfile(a.terminal):
        raise SystemExit(f"terminal inexistente: {a.terminal}")
    if not mt5.initialize(path=a.terminal):
        raise SystemExit(f"MT5 não inicializou neste terminal: {mt5.last_error()}")
    info = mt5.account_info()
    tinfo = mt5.terminal_info()
    if info is None or tinfo is None:
        raise SystemExit("MT5 sem conta/terminal")
    if int(info.login) != int(a.login):
        mt5.shutdown()
        raise SystemExit(f"conta {info.login} ≠ login fixado {a.login} — ABORTADO")
    if int(info.trade_mode) != 0:
        mt5.shutdown()
        raise SystemExit("conta NÃO é DEMO — ABORTADO")
    if not mt5.symbol_select(a.ativo, True):
        mt5.shutdown()
        raise SystemExit(f"símbolo {a.ativo} indisponível")

    import bt_ciclo_v1 as CV1
    import bt_vivo_sombra as S            # congelado: só puxar_e_espelhar é usado
    import bt_ponte_ciclo_v1 as PONTE
    staging = os.path.join(dados, "_staging")
    S.PASTA_ESPELHO = staging             # global lido em tempo de chamada

    hashes = {m: _sha(os.path.join(AQUI, m)) for m in MODULOS}
    inicio = _agora()
    atual = _ler_json(os.path.join(dados, "ATUAL.json")) or {}
    ult_pub = atual.get("barra_corretora")
    off, off_fonte = None, "ainda_nao_medido"
    erro = None
    print(f"LEITOR DO MOTOR v{LEITOR_VERSAO} · {a.ativo} · conta DEMO {info.login} ({info.server}) · "
          f"terminal {tinfo.path} · ordens BLOQUEADAS · retomada: {ult_pub or 'nenhuma barra publicada'}",
          flush=True)

    periodo_pub = None
    _fuso_por_tick(mt5, a.ativo)          # 1ª amostra do tick (a medição exige tick NOVO)
    time.sleep(1.2)
    while True:
        try:
            o2, f2 = _fuso_por_tick(mt5, a.ativo)
            if o2 is not None:
                off, off_fonte = o2, f2
            else:                      # sem medição confiável nesta passada: não afirma fuso
                off, off_fonte = None, f2
            ts_m15, _spread = S.puxar_e_espelhar(mt5, a.ativo)
            barra = str(ts_m15)
            if barra != ult_pub:
                nome = ts_m15.strftime("%Y%m%d_%H%M")
                destino = os.path.join(dados, "barras", nome)
                if not os.path.isdir(destino):
                    tmp = destino + f".tmp{os.getpid()}"
                    shutil.rmtree(tmp, ignore_errors=True)
                    shutil.copytree(staging, tmp)
                    leit = {"leitor": LEITOR_VERSAO, "cv1": CV1.CV1_VERSAO,
                            "ponte": PONTE.PONTE_VERSAO, "ativo": a.ativo,
                            "barra_corretora": barra, "calculado_utc": _iso(_agora()),
                            "m15": _ultima_linha_m15(tmp, a.ativo)}
                    try:
                        ficha, leituras = CV1.avaliar(tmp, a.ativo)
                        leit["leitura"] = PONTE.resumo_motor(ficha, leituras)
                        leit["erro"] = None
                    except Exception as e:
                        leit["leitura"] = None
                        leit["erro"] = f"{type(e).__name__}: {e}"
                    _grava_json_atomico(os.path.join(tmp, "leitura_motor.json"), leit)
                    try:                               # v1.3: candidatos M15/M30/H1 (só telemetria)
                        cand = _candidatos(tmp, a.ativo, _spread)
                    except Exception as e:
                        cand = {"versao": CAND_VERSAO, "erro": f"{type(e).__name__}: {e}"[:300], "itens": []}
                    try:                               # v1.4: auditoria do canal EMA20 por TF (só telemetria)
                        cand["canais"] = _canais(tmp, a.ativo, mt5)
                    except Exception as e:
                        cand["canais"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    _grava_json_atomico(os.path.join(tmp, "candidatos.json"), cand)
                    os.replace(tmp, destino)
                else:
                    leit = _ler_json(os.path.join(destino, "leitura_motor.json")) or {}
                _grava_json_atomico(os.path.join(dados, "ATUAL.json"), {
                    "barra_corretora": barra, "pasta": os.path.join("barras", nome),
                    "publicado_utc": _iso(_agora()), "m15": leit.get("m15"),
                    "erro_motor": leit.get("erro"), "leitor": LEITOR_VERSAO})
                ult_pub = barra
                periodo_pub = int(time.time() // 900)
                velhas = sorted(d for d in os.listdir(os.path.join(dados, "barras"))
                                if not d.endswith(".tmp") and ".tmp" not in d)
                for d in velhas[:-MANTER_BARRAS]:
                    shutil.rmtree(os.path.join(dados, "barras", d), ignore_errors=True)
                print(f"{_agora():%H:%M:%S}Z barra M15 {barra} (corretora) publicada · "
                      f"motor {'ok' if not leit.get('erro') else leit['erro']}", flush=True)
            erro = None
        except KeyboardInterrupt:
            break
        except Exception as e:
            erro = f"{type(e).__name__}: {e}"
            print(f"{_agora():%H:%M:%S}Z [aviso] {erro}", flush=True)
            try:                                       # religa o MT5 na próxima passada
                mt5.shutdown()
                mt5.initialize(path=a.terminal)
                _bloquear_ordens(mt5)
            except Exception:
                pass
        try:
            ai = mt5.account_info()
            _grava_json_atomico(os.path.join(dados, "SAUDE.json"), {
                "leitor": LEITOR_VERSAO, "pid": os.getpid(), "inicio_utc": _iso(inicio),
                "agora_utc": _iso(_agora()), "intervalo_s": a.intervalo,
                "ativo": a.ativo, "login": int(ai.login) if ai else None,
                "servidor": ai.server if ai else None,
                "conta_demo": bool(ai and int(ai.trade_mode) == 0),
                "terminal": tinfo.path, "data_path": tinfo.data_path,
                "off_corretora_s": off, "off_fonte": off_fonte,
                "ultima_barra_corretora": ult_pub, "erro_ultimo": erro,
                "ordens": "bloqueadas (order_send/order_check substituídos)",
                "hashes": hashes})
        except Exception as e:
            print(f"[aviso] SAUDE.json não gravado: {e}", flush=True)
        if a.uma_vez:
            break
        time.sleep(_espera(a.intervalo, time.time(), periodo_pub))
    mt5.shutdown()


if __name__ == "__main__":
    main()
