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

LEITOR_VERSAO = "1.1-hml"
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
                    os.replace(tmp, destino)
                else:
                    leit = _ler_json(os.path.join(destino, "leitura_motor.json")) or {}
                _grava_json_atomico(os.path.join(dados, "ATUAL.json"), {
                    "barra_corretora": barra, "pasta": os.path.join("barras", nome),
                    "publicado_utc": _iso(_agora()), "m15": leit.get("m15"),
                    "erro_motor": leit.get("erro"), "leitor": LEITOR_VERSAO})
                ult_pub = barra
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
        time.sleep(max(5, a.intervalo))
    mt5.shutdown()


if __name__ == "__main__":
    main()
