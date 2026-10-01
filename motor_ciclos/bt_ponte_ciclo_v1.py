# -*- coding: utf-8 -*-
"""bt_ponte_ciclo_v1.py — v1.1-hml (C27R14, 01/out/2026)

A PONTE MÍNIMA entre a saída REAL do motor Python (bt_ciclo_v1.avaliar — a
ficha que bt_vivo_sombra injeta em contra["ciclo"]) e o payload do atestado
que a API verifica (_r01_ler_ciclos_servidor). TRADUÇÃO de campos, nenhuma
regra de leitura nova:
  cv1.veredito  = 12_veredito.topdown[0]      (autorizada|neutra|bloqueada)
  cv1.janela    = dirs de M1/M5/M15 da MESMA leitura (le["dir"] por andar)
  cv1.motivo    = topdown[1]                  (o traço do motor)
  cv2.dirs      = dirs de D1/H4 da MESMA leitura
  ts_barra_m15  = FECHAMENTO da barra da ficha, em UTC
  versao_motor  = CV1_VERSAO do módulo real

CORREÇÕES DA v1.1 SOBRE A v1.0-ciclovivo (27/set, sha 89e4b4be…) — registradas
em motor_ciclos/LEIA_MOTOR.md §Correções; nenhuma mexe em regra do motor:
  C1  FUSO DA CORRETORA. A v1.0 tratava o horário do espelho como UTC. O espelho
      é gravado por bt_vivo_sombra.puxar_e_espelhar com o campo `time` de
      mt5.copy_rates_* — horário do SERVIDOR da corretora (IC Markets = UTC+3 no
      horário de verão europeu). Sem a correção o atestado nasceria 3h no futuro
      e a API recusaria (barra_em_formacao_ou_futura). Agora o chamador PRECISA
      informar off_corretora_s (segundos, corretora − UTC) e
        ts_barra_m15(UTC) = abertura_corretora + 15min − off_corretora_s.
  C2  VÍNCULO DO BOT. O verificador da API (bt_cv_atestado 1.2-c27r6) exige
      bot_token_hash = sha256(bot_token). A v1.0 não o emitia — todo atestado
      seria recusado como atestado_sem_vinculo_bot. Agora é parâmetro obrigatório.
  C3  NÃO ASSINAR LEITURA ANTIGA. Com agora_utc informado, a ponte recusa barra
      fechada há mais de 900s (leitura_antiga) e barra no futuro (barra_futura) —
      o mesmo limite do verificador, aplicado ANTES de assinar.

DIVERGÊNCIA SEMÂNTICA DECLARADA (radiografia 27/set, NÃO alterada): o motor
autoriza por D1×H4 vs s15 sem consultar M1/M5; o emissor da API exige, para
"autorizada", a janela M1/M5/M15 toda no lado. Efeito: fail-closed (a
integração nunca abre a MAIS que o motor; pode abrir a MENOS).
"""
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt_ciclo_v1 as CV1

PONTE_VERSAO = "1.1-hml"
_ANDARES_JANELA = ("M1", "M5", "M15")
_ANDARES_REF = ("D1", "H4")
TTL_LEITURA_S = 900


def _off_valido(off):
    if isinstance(off, bool) or not isinstance(off, int):
        raise ValueError("fuso_corretora_ausente(off_corretora_s)")
    if abs(off) > 14 * 3600 or off % 900 != 0:
        raise ValueError(f"fuso_corretora_invalido({off})")
    return off


def barra_utc(ficha, off_corretora_s):
    """(abertura_corretora, fechamento_utc) da barra M15 avaliada pela ficha."""
    off = _off_valido(off_corretora_s)
    ab = pd.Timestamp(ficha["ts_barra"])
    if ab.tzinfo is not None:
        raise ValueError("ts_barra_do_motor_com_fuso(esperado horario da corretora sem fuso)")
    fech = (ab + pd.Timedelta(minutes=15) - pd.Timedelta(seconds=off)).tz_localize("UTC")
    return ab, fech


def ficha_para_payload(ficha, leituras, simbolo, magic, bot_token_hash,
                       off_corretora_s, agora_utc=None):
    """Traduz a ficha REAL de CV1.avaliar() no corpo do atestado. Levanta
    ValueError nomeado em qualquer lacuna — nunca completa no escuro."""
    if not isinstance(ficha, dict) or "12_veredito" not in ficha:
        raise ValueError("ficha_do_motor_invalida")
    v = ficha["12_veredito"]
    topdown = v.get("topdown") or ()
    if not topdown or topdown[0] not in ("autorizada", "neutra", "bloqueada"):
        raise ValueError("topdown_invalido")
    dirs = {nm: (le["dir"] if le else None) for nm, le in (leituras or {}).items()}
    jan = {}
    for nm in _ANDARES_JANELA:
        if dirs.get(nm) is None:
            raise ValueError(f"janela_incompleta({nm})")
        jan[nm] = int(dirs[nm])
    ref = {}
    for nm in _ANDARES_REF:
        if dirs.get(nm) is None:
            raise ValueError(f"referencia_incompleta({nm})")
        ref[nm] = int(dirs[nm])
    if not isinstance(magic, int) or isinstance(magic, bool) or magic <= 0:
        raise ValueError("magic_invalido")
    if not isinstance(bot_token_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", bot_token_hash):
        raise ValueError("bot_token_hash_ausente")
    _ab, ts = barra_utc(ficha, off_corretora_s)
    if agora_utc is not None:
        agora = pd.Timestamp(agora_utc)
        agora = agora.tz_localize("UTC") if agora.tzinfo is None else agora.tz_convert("UTC")
        idade = (agora - ts).total_seconds()
        if idade < 0:
            raise ValueError(f"barra_futura({idade:.0f}s; conferir fuso da corretora)")
        if idade > TTL_LEITURA_S:
            raise ValueError(f"leitura_antiga({idade:.0f}s > {TTL_LEITURA_S}s)")
    cv1 = {"janela": jan, "veredito": topdown[0]}
    if len(topdown) > 1 and topdown[1]:
        cv1["motivo"] = str(topdown[1])
    return {"bot_token_hash": bot_token_hash,
            "versao_motor": f"cv1-{CV1.CV1_VERSAO}", "simbolo": simbolo,
            "magic": magic, "ts_barra_m15": ts.isoformat(),
            "cv1": cv1, "cv2": {"dirs": ref}}


def resumo_motor(ficha, leituras):
    """Leitura ORIGINAL do motor para telemetria/auditoria (não é autoridade:
    a autoridade é o atestado assinado). Só campos que o motor calculou."""
    v = ficha.get("12_veredito") or {}
    fase = ficha.get("15_fase") or {}
    conc = ficha.get("16_conclusao") or {}
    fichas = ficha.get("13_fichas_tf") or {}
    por_tf = {}
    for nm, le in (leituras or {}).items():
        if not le:
            por_tf[nm] = {"fonte": (ficha.get("fontes") or {}).get(nm)}
            continue
        fx = fichas.get(nm) or {}
        por_tf[nm] = {
            "barra_corretora": le.get("ts"), "dir": le.get("dir"),
            "estrutura": (le.get("pivos") or {}).get("sequencia"),
            "ultimo_topo": (le.get("pivos") or {}).get("ultimo_topo"),
            "ultimo_fundo": (le.get("pivos") or {}).get("ultimo_fundo"),
            "caixa": (le.get("caixa") or {}).get("estado") if le.get("caixa") else None,
            "degrau": (le.get("exaustao") or {}).get("degrau"),
            "gatilho_exaustao": (le.get("exaustao") or {}).get("gatilho"),
            "perna_L": (le.get("perna") or (0, 0))[1], "afastamento_D": le.get("afastamento"),
            "eventos": list(le.get("eventos") or [])[:6],
            "regime": fx.get("regime"), "forca": fx.get("forca"),
            "confianca": fx.get("confianca"), "volatilidade": fx.get("volatilidade"),
            "localizacao": fx.get("localizacao"), "momentum": fx.get("momentum"),
            "persistencia": fx.get("persistencia"),
        }
    return {
        "ts_barra_corretora": ficha.get("ts_barra"),
        "topdown": list(v.get("topdown") or []),
        "apoio": v.get("apoio"), "conflito": v.get("conflito"),
        "degrau_m15": v.get("degrau"), "lado_exaustao_m15": v.get("lado_ex"),
        "janela_10_15": v.get("janela_conf"), "voltou_compressao": v.get("voltou"),
        "classificacao": v.get("classif"),
        "estado_unico": (ficha.get("1_estado_unico") or {}).get("texto"),
        "fase": {"fase": fase.get("fase"), "direcao": fase.get("direcao"),
                 "rotulo": fase.get("rotulo"), "estado": fase.get("estado")},
        "conclusao": {"decisao": conc.get("decisao"), "ciclo1": conc.get("ciclo1"),
                      "ciclo2": conc.get("ciclo2"), "classificacao": conc.get("classificacao"),
                      "conflitos": conc.get("conflitos")},
        "sinal_bloco2": ficha.get("8_sinais_ao_bloco2"),
        "por_tf": por_tf,
        "fontes": ficha.get("fontes"),
    }


def ler_motor_e_montar(pasta_espelho, ativo, simbolo, magic, bot_token_hash,
                       off_corretora_s, agora_utc=None, com_resumo=False):
    """CHAMA o motor real (mesmo PC/processo) e devolve o payload (e, se pedido,
    o resumo da leitura original). Nenhum conteúdo de leitura entra por
    parâmetro — só a FONTE (pasta do espelho)."""
    ficha, leituras = CV1.avaliar(pasta_espelho, ativo)
    payload = ficha_para_payload(ficha, leituras, simbolo, magic, bot_token_hash,
                                 off_corretora_s, agora_utc=agora_utc)
    if com_resumo:
        return payload, resumo_motor(ficha, leituras)
    return payload
