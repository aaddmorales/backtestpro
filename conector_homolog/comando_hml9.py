# ── H16 (hml9, C27R16) — CANAL DE COMANDO nuvem → conector → EA (SOMENTE HOMOLOG/DEMO) ──
# O conector v1.35 nunca teve esta perna (a API diz: "o canal de comando nunca integrou").
# Sem ela, uma decisão autorizada vira comando 'pendente' e morre na fila.
#
# O conector NÃO decide nada: só transporta o comando que a API já criou pela RPC
# r01_claim_e_comando (decisão dos Ciclos emitida e consumida uma única vez).
#   1. POST /mt5/comando/pendente/checar   (claim atômico na nuvem: 'entregue')
#   2. confere: DEMO conferida nesta sessão, tipo conhecido, validade, números
#   3. grava <MQL5>/Files/bt_cmd_<magic>.txt   ("id|tipo|json")
#   4. o EA (BTLerComando) consome, chama OrderSend e grava bt_ok_<magic>.txt
#   5. POST /mt5/comando/confirmar com ticket / preço / retcode, ou o erro
# Nunca reentrega: cada id é entregue no máximo uma vez por instalação (registro em disco).
# Qualquer dúvida = falha confirmada com o motivo; nenhuma ordem é reenviada.
CMD_TIPOS = ("buy", "sell", "close", "close_all", "mover_sl", "mover_tp")
CMD_ESPERA_CONSUMO_S = 20      # EA lê no tick; sem consumo neste prazo o arquivo é retirado
CMD_ESPERA_RESPOSTA_S = 45     # depois de consumido, prazo para o bt_ok aparecer
CMD_RETCODES_OK = (10008, 10009)   # TRADE_RETCODE_PLACED / TRADE_RETCODE_DONE
_CMD_ESTADO = {}               # magic -> {"cmd":…, "fase": "entregue|consumido", "t0":…}
_CMD_LOCK = threading.Lock()
_CMD_GATE = {}                 # conferência DEMO em cache curto (20 s) só para decidir se BUSCA comando


def _cmd_arq(mql5_dir, prefixo, magic):
    return os.path.join(mql5_dir, "Files", f"{prefixo}_{int(magic)}.txt")


def _cmd_registro(mql5_dir):
    return os.path.join(mql5_dir, "Files", "bt_hml_comandos_entregues.json")


def _cmd_ja_entregue(mql5_dir, cmd_id):
    try:
        with open(_cmd_registro(mql5_dir), encoding="utf-8") as f:
            return str(cmd_id) in (json.load(f) or {})
    except Exception:
        return False


def _cmd_registrar(mql5_dir, cmd_id, magic, tipo):
    cam = _cmd_registro(mql5_dir)
    try:
        with open(cam, encoding="utf-8") as f:
            reg = json.load(f) or {}
    except Exception:
        reg = {}
    reg[str(cmd_id)] = {"magic": int(magic), "tipo": tipo, "em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if len(reg) > 500:
        for k in sorted(reg, key=lambda x: reg[x].get("em") or "")[:len(reg) - 500]:
            reg.pop(k, None)
    tmp = cam + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f)
    os.replace(tmp, cam)


def cmd_checar(bot_token):
    """Comando pendente deste bot (ou None). O claim é da nuvem: quem recebe é dono da entrega."""
    if requests is None:
        return None
    r = requests.post(f"{API_BASE}/mt5/comando/pendente/checar", json={"bot_token": bot_token}, timeout=10)
    if r.status_code != 200:
        dbg(f"cmd_checar HTTP {r.status_code}")
        return None
    return (r.json() or {}).get("comando")


def cmd_confirmar(bot_token, cmd_id, sucesso, resultado):
    if requests is None:
        return False
    try:
        r = requests.post(f"{API_BASE}/mt5/comando/confirmar", timeout=10,
                          json={"comando_id": int(cmd_id), "sucesso": bool(sucesso),
                                "resultado": resultado or {}, "bot_token": bot_token})
        dbg(f"cmd_confirmar id={cmd_id} sucesso={bool(sucesso)} HTTP {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        dbg(f"cmd_confirmar erro: {e}")
        return False


def _cmd_expirado(cmd, agora=None):
    exp = cmd.get("expira_em")
    if not exp:
        return False
    try:
        t = datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (agora or datetime.datetime.now(datetime.timezone.utc)) >= t
    except Exception:
        return True                      # validade ilegível = não entrega


def _cmd_linha(cmd):
    """(linha "id|tipo|json", None) ou (None, motivo). Só números limpos chegam ao EA —
    o extrator do EA é mínimo; uid/decisão ficam na nuvem."""
    tipo = str(cmd.get("tipo") or "").lower()
    if tipo not in CMD_TIPOS:
        return None, f"tipo_desconhecido({tipo})"
    try:
        cid = int(cmd.get("id"))
    except Exception:
        return None, "id_invalido"
    if cid <= 0:
        return None, "id_invalido"
    p = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    limpo = {}
    for k in ("lote", "sl", "tp", "ticket"):
        if p.get(k) is None:
            continue
        try:
            v = float(p[k])
        except Exception:
            return None, f"parametro_invalido({k})"
        if v != v or v in (float("inf"), float("-inf")) or v < 0:
            return None, f"parametro_invalido({k})"
        limpo[k] = int(v) if k == "ticket" else v
    if tipo in ("buy", "sell"):
        if not (0 < float(limpo.get("lote") or 0) <= 100):
            return None, "lote_invalido"
        if not (p.get("decisao") or {}).get("id") or not p.get("uid"):
            return None, "abertura_sem_decisao_dos_ciclos"      # só a RPC cria abertura
    return f"{cid}|{tipo}|{json.dumps(limpo, separators=(',', ':'))}", None


def _cmd_ler_ok(mql5_dir, magic, cmd_id):
    """None enquanto não há resposta DESTE comando; senão (sucesso, resultado)."""
    arq = _cmd_arq(mql5_dir, "bt_ok", magic)
    try:
        with open(arq, encoding="latin-1") as f:
            linha = f.read().strip().splitlines()[0]
    except Exception:
        return None
    partes = linha.split("|", 2)
    if len(partes) < 2 or partes[0].strip() != str(int(cmd_id)):
        return None                       # resposta de outro comando (antiga)
    extra = partes[2] if len(partes) > 2 else ""
    campos = dict(x.split("=", 1) for x in extra.split(";") if "=" in x)
    res = {"bruto": extra[:200]}
    try:
        rc = int(campos.get("retcode")) if campos.get("retcode") not in (None, "") else None
    except Exception:
        rc = None
    res["retcode"] = rc
    ok_ea = partes[1].strip().lower() == "ok"
    if "ticket" in campos:
        try:
            res["ticket"] = int(campos["ticket"])
        except Exception:
            pass
    if "preco" in campos:
        try:
            res["preco_real"] = float(campos["preco"])
        except Exception:
            pass
    if "fechados" in campos:
        res["fechados"] = campos["fechados"]
    sucesso = ok_ea and (rc is None or rc in CMD_RETCODES_OK)
    if ok_ea and rc is not None and rc not in CMD_RETCODES_OK:
        sucesso = False
    if not sucesso:
        res["erro"] = (f"MT5 retcode {rc}" if rc is not None else (extra or "EA respondeu erro"))[:200]
    try:
        os.remove(arq)
    except Exception:
        pass
    return sucesso, res


def cmd_passo(bot_token, magic, mql5_dir, agora=None):
    """Um passo da máquina de estados do comando deste bot. Devolve um texto curto
    para a linha de status (ou None). Nunca levanta."""
    agora = agora if agora is not None else time.time()
    try:
        with _CMD_LOCK:
            est = _CMD_ESTADO.get(magic)
        if est is None:
            if agora - _CMD_GATE.get("t", 0) > 20 or _CMD_GATE.get("dir") != mql5_dir:
                _CMD_GATE.update({"t": agora, "dir": mql5_dir, "ok": gate_demo(mql5_dir)[0]})
            if not _CMD_GATE.get("ok"):
                return None               # sem DEMO conferida não se busca comando (fica na fila até expirar)
            cmd = cmd_checar(bot_token)
            if not cmd:
                return None
            cid, tipo = cmd.get("id"), str(cmd.get("tipo") or "").lower()
            linha, falha = _cmd_linha(cmd)
            if not falha and _cmd_expirado(cmd):
                falha = "comando_expirado_antes_da_entrega"
            if not falha and _cmd_ja_entregue(mql5_dir, cid):
                falha = "comando_ja_entregue_nesta_instalacao(nao_reentrega)"
            if not falha:
                ok_demo, mot = gate_demo(mql5_dir)
                if not ok_demo:
                    falha = f"demo_nao_conferida({mot})"
            if falha:
                dbg(f"HOMOLOG comando {cid} ({tipo}) NAO entregue: {falha}")
                cmd_confirmar(bot_token, cid, False, {"erro": falha, "etapa": "conector"})
                return f"⛔ comando {cid} não entregue: {falha}"
            try:
                os.remove(_cmd_arq(mql5_dir, "bt_ok", magic))      # resposta velha não confunde
            except Exception:
                pass
            _cmd_registrar(mql5_dir, cid, magic, tipo)             # registra ANTES de gravar: nunca reentrega
            arq = _cmd_arq(mql5_dir, "bt_cmd", magic)
            tmp = arq + ".tmp"
            with open(tmp, "w", encoding="ascii", newline="") as f:
                f.write(linha + "\n")
            os.replace(tmp, arq)
            with _CMD_LOCK:
                _CMD_ESTADO[magic] = {"cmd": cmd, "fase": "entregue", "t0": agora, "tok": bot_token}
            dbg(f"HOMOLOG comando {cid} ({tipo}) gravado para o EA (magic {magic})")
            return f"📨 comando {cid} ({tipo}) entregue ao EA"
        cid = est["cmd"].get("id")
        r = _cmd_ler_ok(mql5_dir, magic, cid)
        if r is not None:
            sucesso, res = r
            cmd_confirmar(est["tok"], cid, sucesso, res)
            with _CMD_LOCK:
                _CMD_ESTADO.pop(magic, None)
            dbg(f"HOMOLOG comando {cid} resposta do EA: sucesso={sucesso} retcode={res.get('retcode')} "
                f"ticket={res.get('ticket')}")
            return (f"✅ comando {cid} executado (ticket {res.get('ticket')})" if sucesso
                    else f"✖ comando {cid} recusado pelo MT5: {res.get('erro')}")
        arq = _cmd_arq(mql5_dir, "bt_cmd", magic)
        if est["fase"] == "entregue":
            if not os.path.exists(arq):
                est["fase"] = "consumido"; est["t0"] = agora       # EA pegou; aguarda bt_ok
                return None
            if agora - est["t0"] > CMD_ESPERA_CONSUMO_S:
                try:
                    os.remove(arq)
                except Exception:
                    return None                                    # EA abrindo o arquivo agora: espera
                r = _cmd_ler_ok(mql5_dir, magic, cid)              # corrida: consumiu no último instante?
                if r is None and not os.path.exists(arq):
                    cmd_confirmar(est["tok"], cid, False,
                                  {"erro": f"ea_nao_consumiu_em_{CMD_ESPERA_CONSUMO_S}s(arquivo retirado; nenhuma ordem enviada)",
                                   "etapa": "ea"})
                    with _CMD_LOCK:
                        _CMD_ESTADO.pop(magic, None)
                    return f"✖ comando {cid}: EA não consumiu (retirado)"
                if r is not None:
                    cmd_confirmar(est["tok"], cid, r[0], r[1])
                    with _CMD_LOCK:
                        _CMD_ESTADO.pop(magic, None)
            return None
        if agora - est["t0"] > CMD_ESPERA_RESPOSTA_S:
            cmd_confirmar(est["tok"], cid, False,
                          {"erro": "ea_consumiu_e_nao_respondeu(estado da ordem DESCONHECIDO — conferir posições no MT5)",
                           "etapa": "ea"})
            with _CMD_LOCK:
                _CMD_ESTADO.pop(magic, None)
            return f"⚠ comando {cid}: EA consumiu e não respondeu — confira o MT5"
        return None
    except Exception as e:
        dbg(f"cmd_passo erro (magic {magic}): {e}")
        return None


def checar_subir_conector(bot_token):
