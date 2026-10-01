# -*- coding: utf-8 -*-
"""bt_conector_atestado.py — v0.4-hml (C27R14: vínculo do bot + fuso da corretora + frescor)

MUDANÇA v0.4 (C27R14, 01/out/2026) — sobre a v0.3-ciclovivo (sha 71b34a58…):
  ler_e_assinar_motor ganha bot_token (o hash sha256 entra no atestado; o
  token nunca é gravado nem logado), off_corretora_s (fuso corretora − UTC,
  obrigatório — o espelho está no horário do servidor da corretora) e
  agora_utc (recusa assinar leitura antiga/futura). com_resumo=True devolve
  também a leitura original do motor para telemetria. Regras do motor: zero
  mudança. Detalhes: bt_ponte_ciclo_v1 v1.1 (C1–C3) e LEIA_MOTOR.md.

MUDANÇA v0.3 (ordem correção P2 + Ciclo vivo, item B3):
  ler_e_assinar_motor(pasta_espelho, ativo, magic, simbolo) — a PONTE REAL:
  o leitor CHAMA o motor Python de verdade (bt_ciclo_v1.avaliar, o MESMO que
  bt_vivo_sombra injeta em contra["ciclo"]) via bt_ponte_ciclo_v1, no mesmo
  PC/processo do conector, e assina a ficha traduzida. NENHUM conteúdo de
  leitura entra por parâmetro — só a FONTE (pasta do espelho + ativo), então
  sequência fabricada por cliente continua sem caminho. A rota do snapshot
  do EA (ler_e_assinar) permanece com o parser em lacuna nomeada; a
  autoridade declarada é o MOTOR PYTHON (RADIOGRAFIA_CICLO_M1_M5_M15.md).

O elo entre o MOTOR DE SETEMBRO e o assinador bt_cv_atestado.

MUDANÇA v0.2 (ordem de fechamento P1–P4, item P3.2):
  A v0.1 expunha assinar_de_leitura(dict) — uma API que ACEITAVA um dict
  vindo de quem chamasse, "provando" origem por um campo origem='motor_v741'
  que qualquer caller podia escrever. Isso morreu: NÃO EXISTE MAIS função
  pública que assine um dict fornecido por cliente. A leitura que vira
  atestado é OBTIDA POR ESTE MÓDULO, do arquivo/processo confiável no PC do
  MT5, e o carimbo de origem é interno — o chamador só aponta a FONTE
  (caminho do arquivo de snapshot do terminal), nunca o conteúdo.

DESENHO DE POSSE DO SEGREDO (inalterado da v0.1):
  BT_CV_SEGREDO vive em EXATAMENTE dois lugares: o servidor da API isolada e
  ESTE conector, no PC do MT5, via env do par isolado. O SEGREDO NUNCA ENTRA
  NO EA (EA_GATE_SPEC.md): o EA obedece ao gate file que este conector — que
  verifica — escreve. Nenhum valor de segredo neste arquivo nem no pacote.

LIMITE DECLARADO (continua): o HMAC atesta que a leitura passou POR ESTE
  conector; não dispensa a prova de que o conector leu o CV1/CV2 VIVOS do
  EA real — essa prova exige o EA de setembro compilado emitindo snapshot
  (P3.4) e é parte do aceite, não deste módulo.

LACUNA NOMEADA (P3 NÃO VERDE — registro exigido pela ordem):
  _parse_cv1/_parse_cv2 — o formato REAL das strings cv1=/cv2= do EA de
  SETEMBRO (telemetria D3 v7.51: cv1= Ciclo1 M1.M5.M15.M30.H1; cv2= Ciclo2
  MN1.W1.D1.H4) não está nesta bancada: as fontes de setembro NÃO EXISTEM no
  container (só BOTTESTED_100..103.mq5 de AGOSTO). Inventar o parser seria
  assinar leitura que ninguém emitiu. O parser levanta NotImplementedError
  nomeado; buy/sell seguem bloqueados pelo fail-closed do servidor.
  RETOMADA: FALTA_EXATA.md traz os comandos PowerShell somente-leitura pra
  localizar fontes/cache no PC + 1 linha real de snapshot; com isso em mãos,
  implementar os dois parsers aqui com teste de ida-e-volta.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bt_cv_atestado as _cvat

VERSAO = "0.4-hml"
_ORIGEM_INTERNA = "conector_isolado"   # carimbo INTERNO — nenhum caller escolhe

_CAMPOS = ("bot_token_hash", "versao_motor", "simbolo", "magic", "ts_barra_m15", "cv1", "cv2")


class LeitorConfiavel:
    """Obtém a leitura DA FONTE (arquivo de snapshot do terminal MT5) e a
    assina internamente. O chamador nunca fornece o conteúdo da leitura —
    só o caminho da pasta Files do terminal e o magic do bot."""

    def __init__(self, pasta_files: str, segredo: str | None = None):
        self._pasta = pasta_files
        self._seg = segredo if segredo is not None else os.environ.get("BT_CV_SEGREDO")

    def ler_e_assinar(self, magic: int) -> dict:
        """Lê bt_snap_<magic>.txt (o arquivo que SÓ o EA escreve na pasta
        Files do terminal), extrai cv1=/cv2= com o parser do formato real e
        devolve o atestado assinado. Fail-closed em qualquer desvio."""
        if not self._seg:
            raise ValueError("segredo_ausente(par_isolado_nao_configurado)")
        if not isinstance(magic, int) or magic <= 0:
            raise ValueError("magic_invalido")
        cam = os.path.join(self._pasta, f"bt_snap_{magic}.txt")
        if not os.path.isfile(cam):
            raise ValueError(f"snapshot_ausente({os.path.basename(cam)})")
        with open(cam, "r", encoding="utf-8", errors="replace") as f:
            linha = f.read().strip().splitlines()[-1] if f else ""
        leitura = self._parse_snapshot(linha)          # LACUNA: levanta hoje
        leitura["origem"] = _ORIGEM_INTERNA            # carimbo interno
        return self._assinar_leitura_carimbada(leitura)

    # ── internos: NENHUM é API de cliente ──────────────────────────────────
    def _assinar_leitura_carimbada(self, leitura: dict) -> dict:
        if leitura.get("origem") != _ORIGEM_INTERNA:   # cinto: só o leitor carimba
            raise ValueError("leitura_sem_carimbo_interno")
        faltando = [c for c in _CAMPOS if leitura.get(c) in (None, "", {})]
        if faltando:
            raise ValueError(f"leitura_incompleta({'/'.join(faltando)})")
        corpo = {c: leitura[c] for c in _CAMPOS}
        return _cvat.assinar(corpo, segredo=self._seg)

    def _parse_snapshot(self, linha_snapshot: str) -> dict:
        """LACUNA NOMEADA — ver docstring do módulo. Não inventamos formato."""
        raise NotImplementedError(
            "parser_cv1_cv2_indisponivel: o formato real das strings cv1=/cv2= "
            "do EA de setembro nao esta nesta bancada (fontes de setembro "
            "ausentes; BOTTESTED_100..103 sao de agosto). Buy/sell permanecem "
            "bloqueados (fail-closed sem atestado). Retomada: rodar as "
            "consultas de FALTA_EXATA.md no PC, capturar 1 linha real de "
            "snapshot sem segredo e implementar _parse_cv1/_parse_cv2 com "
            "ida-e-volta.")


    def ler_e_assinar_motor(self, pasta_espelho: str, ativo: str,
                            magic: int, simbolo: str | None = None,
                            bot_token: str | None = None,
                            off_corretora_s: int | None = None,
                            agora_utc=None, com_resumo: bool = False):
        """PONTE DO MOTOR: chama bt_ciclo_v1.avaliar() (motor REAL) na pasta de
        espelho local e assina a ficha traduzida. Fail-closed em qualquer
        lacuna; o carimbo de origem segue interno. com_resumo=True devolve
        (atestado, leitura_original_do_motor)."""
        if not self._seg:
            raise ValueError("segredo_ausente(par_isolado_nao_configurado)")
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("bot_token_ausente(vinculo_do_bot)")
        import bt_ponte_ciclo_v1 as _ponte
        h = hashlib.sha256(bot_token.encode("utf-8")).hexdigest()
        leitura, resumo = _ponte.ler_motor_e_montar(
            pasta_espelho, ativo, simbolo or ativo, magic, h, off_corretora_s,
            agora_utc=agora_utc, com_resumo=True)
        leitura["origem"] = _ORIGEM_INTERNA
        at = self._assinar_leitura_carimbada(leitura)
        return (at, resumo) if com_resumo else at


def parser_snapshot_cv(linha_snapshot: str):
    """Compat de nome com a v0.1 — mesma lacuna nomeada."""
    return LeitorConfiavel("/dev/null")._parse_snapshot(linha_snapshot)
