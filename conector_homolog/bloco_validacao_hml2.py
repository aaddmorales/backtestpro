# ═══════════════════════════════════════════════════════════════════
#  HOMOLOG hml2/hml4 — CONFERÊNCIA DO MT5 DEMO + COMPILAÇÃO ESTRITA
#  Substitui o validar_pendente da v1.35 nesta cópia:
#   • sem conferência DEMO confirmada para a instalação fixada → o job NEM é
#     buscado (fica pendente na nuvem) — BT-HML-D0x no log/status;
#   • pre_validado é IGNORADO (nunca antecipa aprovação);
#   • sem MetaEditor da instalação DEMO → veredito FALSO "INDISPONIVEL";
#   • aprovado SOMENTE com: .mq5 em disco idêntico ao do job + compile.log NOVO
#     com linha de resultado "0 errors" citando o .mq5 do job + .ex5 NOVO
#     (criado depois do início da compilação). Nada de checagem de sintaxe.
# ═══════════════════════════════════════════════════════════════════
import hashlib as _hl

_DEMO_CONF = {"mql5": None, "login": None, "servidor": None}
# hml4: a confirmação visual fica salva no config HOMOLOG (instalação+conta).
# Assim o conector aberto SOZINHO pelo Enviar (bottested://) já nasce apto;
# a cada job o diário é relido e conta/servidor precisam continuar iguais.
try:
    _dc = _ler_config().get("demo_conf") or {}
    if _dc.get("mql5") and _dc.get("servidor"):
        _DEMO_CONF.update({k: _dc.get(k) for k in ("mql5", "login", "servidor")})
except Exception:
    pass
_RE_AUTH = re.compile(r"'(\d+)'\s*:\s*authorized on\s+([^\s,]+)", re.I)
_RE_ALGO = re.compile(r"(?:automated|algo(?:rithmic)?)\s+trading\s+is\s+(enabled|disabled)", re.I)
_RE_RES = re.compile(r"(\d+)\s+error(?:s|\(s\))?\s*,\s*(\d+)\s+warning", re.I)


def _ler_texto_mt5(caminho):
    """Arquivos do MT5 vêm em UTF-16 (com BOM) na maioria das builds; alguns
    em UTF-8. Decide pelo conteúdo, não por tentativa-e-erro."""
    with open(caminho, "rb") as f:
        b = f.read()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16", errors="ignore")
    if b[:3] == b"\xef\xbb\xbf":
        return b[3:].decode("utf-8", errors="ignore")
    if len(b) > 1 and b.count(b"\x00") > len(b) // 4:
        return b.decode("utf-16-le", errors="ignore")
    return b.decode("utf-8", errors="ignore")


def _servidor_demo(servidor):
    s = (servidor or "").lower()
    return ("demo" in s) and not any(k in s for k in ("live", "real"))


def conferir_demo(mql5_dir):
    """Identifica a instalação fixada e a conta que ela autorizou por último.
    Fonte principal: diário do terminal (<terminal>\\logs\\AAAAMMDD.log, linha
    "'<login>': authorized on <servidor>"). Reserva: config\\common.ini.
    AutoTrading: última linha "automated/algo trading is enabled|disabled".
    Retorna dict — nunca decide sozinho: a GUI exige a conferência visual."""
    terminal = os.path.dirname(os.path.normpath(mql5_dir or ""))
    info = {"mql5": mql5_dir, "terminal": terminal, "programa": "", "login": "",
            "servidor": "", "fonte": "nenhuma", "autotrading": "desconhecido",
            "demo": False}
    try:
        org = os.path.join(terminal, "origin.txt")
        if os.path.isfile(org):
            info["programa"] = _ler_texto_mt5(org).strip()
    except Exception:
        pass
    try:
        logs = sorted(glob.glob(os.path.join(terminal, "logs", "*.log")))
        for arq in logs:
            for linha in _ler_texto_mt5(arq).splitlines():
                m = _RE_AUTH.search(linha)
                if m:
                    info["login"], info["servidor"] = m.group(1), m.group(2)
                    info["fonte"] = "diario:" + os.path.basename(arq)
                a = _RE_ALGO.search(linha)
                if a:
                    info["autotrading"] = "on" if a.group(1).lower() == "enabled" else "off"
    except Exception as e:
        dbg(f"conferir_demo diario: {e}")
    if not info["servidor"]:
        try:
            ini = os.path.join(terminal, "config", "common.ini")
            if os.path.isfile(ini):
                sec = ""
                for linha in _ler_texto_mt5(ini).splitlines():
                    t = linha.strip()
                    if t.startswith("["):
                        sec = t.lower()
                    elif sec == "[common]" and "=" in t:
                        k, v = t.split("=", 1)
                        if k.strip().lower() == "login":
                            info["login"] = v.strip()
                        elif k.strip().lower() == "server":
                            info["servidor"] = v.strip()
                if info["servidor"]:
                    info["fonte"] = "common.ini"
        except Exception as e:
            dbg(f"conferir_demo ini: {e}")
    info["demo"] = _servidor_demo(info["servidor"])
    return info


def confirmar_demo(mql5_dir, info):
    """Chamado pela GUI SÓ depois do 'Sim' na conferência visual. Vale para
    esta sessão (não é salvo em disco) e só para esta instalação/conta."""
    _DEMO_CONF.update({"mql5": mql5_dir, "login": info.get("login"),
                       "servidor": info.get("servidor")})
    _salvar_config({"demo_conf": dict(_DEMO_CONF)})
    dbg(f"HOMOLOG: DEMO confirmada | servidor={info.get('servidor')} "
        f"autotrading={info.get('autotrading')} terminal={info.get('terminal')}")


def resetar_demo():
    _DEMO_CONF.update({"mql5": None, "login": None, "servidor": None})
    try:
        _salvar_config({"demo_conf": {}})
    except Exception:
        pass


def gate_demo(mql5_dir):
    """(ok, motivo). Refaz a leitura a cada job: trocou conta/servidor, ligou o
    AutoTrading ou mudou a instalação desde a confirmação → bloqueia."""
    if not mql5_dir:
        return False, "BT-HML-D01 nenhum MT5 fixado"
    if _DEMO_CONF.get("mql5") != mql5_dir:
        return False, "BT-HML-D02 conferência DEMO pendente (botão 'Conferir MT5 DEMO')"
    info = conferir_demo(mql5_dir)
    if not info["demo"]:
        return False, f"BT-HML-D03 servidor não é DEMO ({info['servidor'] or '?'})"
    if (info["login"], info["servidor"]) != (_DEMO_CONF.get("login"), _DEMO_CONF.get("servidor")):
        resetar_demo()
        return False, "BT-HML-D04 conta mudou desde a conferência — confira de novo"
    if info["autotrading"] == "on":
        # hml3 (decisão do dono 29/set): conta DEMO com bots rodando — Algo Trading
        # LIGADO é aceito; só registra. A trava continua sendo: servidor DEMO +
        # mesma conta confirmada visualmente.
        dbg("HOMOLOG: aviso — AutoTrading LIGADO na DEMO (aceito por decisão do dono)")
    return True, "ok"


def achar_metaeditor_hml(mql5_dir):
    """Só o MetaEditor da PRÓPRIA instalação DEMO (origin.txt dela), ou um
    caminho posto à mão em 'metaeditor_hml' no config HOMOLOG. Nunca varre
    Program Files (poderia pegar o MetaEditor do MT5 real)."""
    p = (_ler_config().get("metaeditor_hml") or "").strip()
    if p and os.path.isfile(p):
        return p
    try:
        org = os.path.join(os.path.dirname(os.path.normpath(mql5_dir)), "origin.txt")
        if os.path.isfile(org):
            prog = _ler_texto_mt5(org).strip()
            cand = os.path.join(prog, "metaeditor64.exe")
            if prog and os.path.isfile(cand):
                return cand
    except Exception:
        pass
    return None


def _sha256_arquivo(caminho):
    h = _hl.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def compilar_estrito(caminho_mq5, codigo, metaeditor, mql5_dir, _executar=None):
    """Retorna (status, log) com status em aprovado | reprovado | indisponivel.
    _executar: só para teste (substitui o subprocess)."""
    if not metaeditor or not os.path.isfile(metaeditor):
        return "indisponivel", "BT-HML-M01 MetaEditor da instalação DEMO não encontrado"
    try:
        # hml5: no Windows o instalar_ea grava em modo texto (\n vira \r\n) —
        # compara o CONTEÚDO com fim de linha normalizado, não os bytes crus.
        with open(caminho_mq5, "rb") as _f:
            _disco = _f.read().replace(b"\r\n", b"\n")
        _job = codigo.replace("\r\n", "\n").encode("utf-8")
        if _hl.sha256(_disco).hexdigest() != _hl.sha256(_job).hexdigest():
            return "reprovado", "BT-HML-C03 .mq5 em disco difere do código do job"
    except Exception as e:
        return "reprovado", f"BT-HML-C03 .mq5 ilegível: {e}"
    base = caminho_mq5[:-4] if caminho_mq5.lower().endswith(".mq5") else caminho_mq5
    ex5, log_path = base + ".ex5", base + "_compile.log"
    for velho in (ex5, log_path):          # nada de sobra de build anterior
        try:
            if os.path.isfile(velho):
                os.remove(velho)
        except Exception as e:
            return "indisponivel", f"BT-HML-M03 não consegui limpar {os.path.basename(velho)}: {e}"
    t0 = time.time()
    cmd = [metaeditor, f"/compile:{caminho_mq5}", f"/inc:{mql5_dir}", f"/log:{log_path}"]
    try:
        if _executar:
            _executar(cmd)
        else:
            import subprocess
            subprocess.run(cmd, capture_output=True, timeout=180,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return "indisponivel", f"BT-HML-M02 MetaEditor não executou: {e}"
    if not os.path.isfile(log_path):
        return "reprovado", "BT-HML-C01 compile.log não foi gerado"
    log = _ler_texto_mt5(log_path).strip()
    res = _RE_RES.findall(log)
    if not res:
        return "reprovado", "BT-HML-C01 compile.log sem linha de resultado\n" + log[-1500:]
    erros = int(res[-1][0])
    if erros != 0:
        return "reprovado", f"BT-HML-C02 {erros} error(s)\n" + log[-2500:]
    if os.path.basename(caminho_mq5).lower() not in log.lower():
        return "reprovado", "BT-HML-C05 compile.log não cita o .mq5 do job\n" + log[-1500:]
    if not os.path.isfile(ex5) or os.path.getmtime(ex5) < t0 - 2:
        return "reprovado", "BT-HML-C04 .ex5 novo não foi gerado\n" + log[-1500:]
    dbg(f"HOMOLOG: compilado ex5_sha256={_sha256_arquivo(ex5)} "
        f"mq5_sha256={_sha256_arquivo(caminho_mq5)} log={os.path.basename(log_path)}")
    return "aprovado", log[-3500:]


def validar_pendente(bot_token, mql5_dir, ao_iniciar=None, ao_terminar=None,
                     ao_instalar=None, _executar=None):
    """HOMOLOG: gate DEMO → pega o job → instala → compila de verdade →
    veredito. Retorna (houve_pendente, aprovado, msg)."""
    ok_gate, motivo_gate = gate_demo(mql5_dir)
    if not ok_gate:
        dbg(f"HOMOLOG: job NÃO buscado — {motivo_gate}")
        return False, None, motivo_gate
    job = buscar_bot_pendente(bot_token)
    if not job:
        return False, None, "sem pendente"
    if ao_iniciar:
        try: ao_iniciar()
        except Exception: pass
    try:
        codigo = job.get("codigo", "")
        nome = job.get("filename") or "BotTested_EA.mq5"
        job_id = job.get("job_id", "")
        dbg(f"HOMOLOG validar_pendente: job_id={job_id} nome={nome} "
            f"pre_validado={bool(job.get('pre_validado'))} (ignorado: compile real sempre)")
        ok_inst, destino = instalar_ea(codigo, nome, mql5_dir)
        if not ok_inst:
            reportar_veredito(bot_token, job_id, False, f"BT-HML-I01 falha ao instalar: {destino}")
            return True, False, "BT-HML-I01 falha ao instalar o arquivo"
        if ao_instalar:
            try:
                _mg = magic_do_mq5(codigo)
                if _mg:
                    ao_instalar(_mg)
            except Exception:
                pass
        status, log = compilar_estrito(destino, codigo, achar_metaeditor_hml(mql5_dir),
                                       mql5_dir, _executar=_executar)
        if status == "indisponivel":
            log = "INDISPONIVEL (não é aprovação): " + log
        aprovado = (status == "aprovado")
        reportar_veredito(bot_token, job_id, aprovado, log)
        dbg(f"HOMOLOG: job={job_id} status={status}")
        return True, aprovado, f"{status}: {log.splitlines()[0][:100] if log else ''}"
    finally:
        if ao_terminar:
            try: ao_terminar()
            except Exception: pass


