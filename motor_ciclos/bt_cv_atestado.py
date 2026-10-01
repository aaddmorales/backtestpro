# bt_cv_atestado.py — v1.0-c27r3 (27/set/2026, bancada final)
# ATESTADO ASSINADO DOS 2 CICLOS — o elo de autoridade entre o MOTOR (CV1/CV2
# no PC do usuário) e o SERVIDOR que emite decisão de abertura.
#
# POR QUE EXISTE (auditoria da corretiva 2, 27/set): a v7.69-c27r2 lia
# cv2_dirs/ts_barra_m15 do último POST /conector/snapshot — mas QUALQUER
# caller com bot_token válido grava snapshot; leitura fabricada virava
# autoridade. Este módulo fecha esse buraco: o CONECTOR (que roda junto do
# motor e enxerga a leitura REAL do CV1/CV2) assina um ATESTADO com HMAC-SHA256
# e segredo compartilhado (env BT_CV_SEGREDO nos DOIS lados). O servidor só
# emite decisão sobre atestado com assinatura válida.
#
# LIMITE DECLARADO (honestidade): o HMAC autentica a ORIGEM DA INSTALAÇÃO
# (quem conhece o segredo) — protege contra terceiro com bot_token vazado e
# contra snapshot fabricado por script avulso. NÃO protege contra o dono da
# máquina onde o segredo está: quem controla o PC extrai o segredo. Autoridade
# plena exige o motor real assinando a partir da leitura viva; este módulo é o
# CONTRATO e o assinador que o conector de setembro deve embutir.
#
# FAIL-CLOSED POR DESENHO: sem BT_CV_SEGREDO configurado, assinar() e
# verificar() recusam — instalação sem segredo NUNCA produz atestado válido e
# o servidor NUNCA emite decisão. Este é o estado de contenção padrão
# (substitui estruturalmente o BLOQUEIO_CICLOS_27SET: bloqueio por exigência
# não satisfeita, não por chave desligada).

import hashlib
import hmac
import json
import os
import re

VERSAO = "1.2-c27r6"
ENV_SEGREDO = "BT_CV_SEGREDO"

# Campos obrigatórios do payload (sem eles o atestado é inválido nos 2 lados)
_JANELA_CV1 = ("M1", "M5", "M15")          # escada mínima do Ciclo 1
_CV2_OBRIGATORIOS = ("D1", "H4")            # contexto mínimo do Ciclo 2
_CV2_OPCIONAIS = ("MN1", "W1")
_DIR_VALIDAS = (-1, 0, 1)                   # -1 baixa | 0 neutro | 1 alta
# Vocabulário REAL do veredito CV1 (bt_ciclo_v1.py l.413-415 do motor v7.4.1):
# a referência D1×H4 contra → "bloqueada"; a favor → "autorizada"; senão
# "neutra". Estado fora disto é DESCONHECIDO e o atestado é inválido nos 2
# lados (c27r4/P1: o veredito é VETO — nenhum campo o sobrescreve).
VEREDITOS_CV1 = ("autorizada", "neutra", "bloqueada")


def _segredo(segredo=None):
    s = segredo if segredo is not None else os.environ.get(ENV_SEGREDO, "")
    s = (s or "").strip()
    return s or None


def canonico(payload: dict) -> str:
    """Serialização canônica: json ordenado, sem espaços — 1 byte diferente = assinatura diferente."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validar_forma(payload: dict):
    """(ok, motivo). Forma do payload — igual nos 2 lados, fail-closed."""
    if not isinstance(payload, dict):
        return False, "atestado_nao_e_objeto"
    if not isinstance(payload.get("bot_token_hash"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", payload["bot_token_hash"]):
        return False, "atestado_sem_vinculo_bot"
    if not str(payload.get("versao_motor") or "").strip():
        return False, "atestado_sem_versao_motor"
    if not str(payload.get("simbolo") or "").strip():
        return False, "atestado_sem_simbolo"
    try:
        magic = int(payload.get("magic"))
    except (TypeError, ValueError):
        return False, "atestado_magic_invalido"
    if magic <= 0:
        return False, "atestado_magic_zero"        # fecha o bypass magic=0 da auditoria
    ts = payload.get("ts_barra_m15")
    if not isinstance(ts, str) or not ts.strip():
        return False, "atestado_sem_ts_barra"
    cv1 = payload.get("cv1")
    if not isinstance(cv1, dict):
        return False, "atestado_sem_cv1"
    jan = cv1.get("janela")
    if not isinstance(jan, dict):
        return False, "atestado_cv1_sem_janela"
    for tf in _JANELA_CV1:
        if tf not in jan:
            return False, f"atestado_cv1_janela_sem_{tf}"
        if jan[tf] not in _DIR_VALIDAS:
            return False, f"atestado_cv1_janela_{tf}_invalida"
    ver = cv1.get("veredito")
    if not isinstance(ver, str) or not ver.strip():
        return False, "atestado_cv1_sem_veredito"
    if ver not in VEREDITOS_CV1:
        return False, "atestado_cv1_veredito_desconhecido"
    cv2 = payload.get("cv2")
    if not isinstance(cv2, dict):
        return False, "atestado_sem_cv2"
    dirs = cv2.get("dirs")
    if not isinstance(dirs, dict):
        return False, "atestado_cv2_sem_dirs"
    for tf in _CV2_OBRIGATORIOS:
        if tf not in dirs:
            return False, f"atestado_cv2_sem_{tf}"
        if dirs[tf] not in _DIR_VALIDAS:
            return False, f"atestado_cv2_{tf}_invalido"
    for tf in _CV2_OPCIONAIS:
        if tf in dirs and dirs[tf] not in _DIR_VALIDAS:
            return False, f"atestado_cv2_{tf}_invalido"
    return True, None


def assinar(payload: dict, segredo=None):
    """Lado MOTOR/CONECTOR. Devolve o atestado completo (payload + assinatura).
    Levanta ValueError sem segredo ou payload malformado — nunca assina lixo."""
    s = _segredo(segredo)
    if not s:
        raise ValueError("atestado_sem_segredo_configurado")
    ok, motivo = _validar_forma(payload)
    if not ok:
        raise ValueError(motivo)
    corpo = {k: payload[k] for k in payload if k != "assinatura"}
    assin = hmac.new(s.encode("utf-8"), canonico(corpo).encode("utf-8"),
                     hashlib.sha256).hexdigest()
    at = dict(corpo)
    at["assinatura"] = assin
    return at


def verificar(atestado: dict, segredo=None):
    """Lado SERVIDOR. (ok, motivo). Fail-closed em TODO caminho."""
    s = _segredo(segredo)
    if not s:
        return False, "atestado_sem_segredo_configurado"
    if not isinstance(atestado, dict):
        return False, "atestado_nao_e_objeto"
    assin = atestado.get("assinatura")
    if not isinstance(assin, str) or len(assin) != 64:
        return False, "atestado_sem_assinatura"
    corpo = {k: atestado[k] for k in atestado if k != "assinatura"}
    ok, motivo = _validar_forma(corpo)
    if not ok:
        return False, motivo
    esperada = hmac.new(s.encode("utf-8"), canonico(corpo).encode("utf-8"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperada, assin):
        return False, "atestado_assinatura_invalida"
    return True, None
