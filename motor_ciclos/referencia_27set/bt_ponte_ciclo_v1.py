# -*- coding: utf-8 -*-
"""bt_ponte_ciclo_v1.py — v1.0-ciclovivo (27/set/2026, ordem B3)

A PONTE MÍNIMA entre a saída REAL do motor Python (bt_ciclo_v1.avaliar — a
ficha que bt_vivo_sombra injeta em contra["ciclo"], l.1373–1382) e o payload
do atestado que a API candidata verifica (_r01_ler_ciclos_servidor).

O QUE ELA É: uma TRADUÇÃO de campos, sem uma regra nova sequer —
  cv1.veredito  = 12_veredito.topdown[0]      (autorizada|neutra|bloqueada)
  cv1.janela    = dirs de M1/M5/M15 da MESMA leitura (le["dir"] por andar)
  cv1.motivo    = topdown[1]                  (o traço do motor)
  cv2.dirs      = dirs de D1/H4 da MESMA leitura
  ts_barra_m15  = FECHAMENTO da barra da ficha (ts_barra + 15min), em UTC
  versao_motor  = CV1_VERSAO do módulo real

DIVERGÊNCIA SEMÂNTICA DECLARADA (achado da radiografia, NÃO corrigido aqui):
  o motor autoriza por D1×H4 vs s15 (bt_ciclo_v1 l.392–415) SEM consultar
  M1/M5; o verificador/emissor da API v4 exige, para "autorizada", a janela
  M1/M5/M15 TODA no lado. Logo existe estado legítimo do motor — autorizada
  com M1 ainda contra — que a API recusa como atestado_incoerente. EFEITO:
  fail-closed (a integração nunca abre a MAIS que o motor; pode abrir a
  MENOS). Alinhar rótulo/limiar = mudança de regra → medição e decisão
  separadas (ordem B5); esta ponte transporta a leitura CRUA e nada muda.

ACHADO DE TIMESTAMP (radiografia 27/set, item B "compare timestamps"): o
motor rotula a barra M15 pela ABERTURA (bt_ciclo_v1: ts15 = A["M15"].ts[i15];
a barra fecha em ts15+15min). O verificador da API mede o frescor por
(agora − ts_barra_m15) ≤ 900s — convenção de rótulo pelo FECHAMENTO (com o
rótulo de abertura, todo snapshot pós-fechamento estaria vencido). A ponte
faz a CONVERSÃO DE CONVENÇÃO, declarada e auditável: ts_barra_m15 =
ficha.ts_barra + 15min. Não é regra nova — é o mesmo instante físico (o fim
da barra fechada) escrito na convenção que o verificador espera.

A ponte NÃO aceita ficha vinda de cliente: quem a usa é o LeitorConfiavel
(bt_conector_atestado v0.3), que CHAMA o motor real no mesmo processo/PC.
Timestamps do espelho são tratados como UTC (o espelho do MT5/IC é o relógio
do servidor; a conversão fica declarada e auditável no payload).
"""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt_ciclo_v1 as CV1

_ANDARES_JANELA = ("M1", "M5", "M15")
_ANDARES_REF = ("D1", "H4")


def ficha_para_payload(ficha, leituras, simbolo, magic):
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
    ts = pd.Timestamp(ficha["ts_barra"]) + pd.Timedelta(minutes=15)
    if ts.tzinfo is None:                      # abertura → FECHAMENTO (achado
        ts = ts.tz_localize("UTC")             # de convenção; ver docstring)
    if not isinstance(magic, int) or magic <= 0:
        raise ValueError("magic_invalido")
    cv1 = {"janela": jan, "veredito": topdown[0]}
    if len(topdown) > 1 and topdown[1]:
        cv1["motivo"] = str(topdown[1])
    return {"versao_motor": f"cv1-{CV1.CV1_VERSAO}", "simbolo": simbolo,
            "magic": magic, "ts_barra_m15": ts.isoformat(),
            "cv1": cv1, "cv2": {"dirs": ref}}


def ler_motor_e_montar(pasta_espelho, ativo, simbolo, magic, ts_m15=None):
    """CHAMA o motor real (mesmo PC/processo — a topologia documentada em
    RADIOGRAFIA_CICLO_M1_M5_M15.md) e devolve o payload. Nenhum conteúdo de
    leitura entra por parâmetro — só a FONTE (pasta do espelho)."""
    ficha, leituras = CV1.avaliar(pasta_espelho, ativo, ts_m15=ts_m15)
    return ficha_para_payload(ficha, leituras, simbolo, magic)
