_CV_LEITOR = None
_CV_AVISOU = set()
_CV_CACHE = {}
_CV_CAND_ENVIOS = {}            # (pasta da barra, magic) -> nº de snapshots que já levaram os candidatos
_CV_CAND_MAX = 3                # hml10: candidatos vão nos 3 primeiros snapshots da barra (a API guarda 1x por barra)
_CV_HEARTBEAT_MAX_S = 90        # leitor do motor passa a cada 20 s; 90 s sem batimento = parado


def _cv_ler_json(cam):
    import json as _j
    try:
        with open(cam, encoding="utf-8") as f:
            return _j.load(f)
    except Exception:
        return None


def _cv_int(v):
    try:
        return int(float(v))
    except Exception:
        return None


def _cv_iso_idade(iso):
    from datetime import datetime as _d, timezone as _z
    try:
        t = _d.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=_z.utc)
        return (_d.now(_z.utc) - t).total_seconds()
    except Exception:
        return None


def _cv_barra_ea(dados):
    """(abertura_corretora_epoch, ohlc) da barra M15 FECHADA vista pelo EA
    (cvt = iTime(tf,1) na ordem MN1.W1.D1.H4.H1.M30.M15.M5.M1; c15m vem de
    CopyRates a partir do shift 0, mais antiga primeiro → fechada = penúltima)."""
    partes = str(dados.get("cvt") or "").split(".")
    ab = _cv_int(partes[6]) if len(partes) == 9 else None
    ohlc = None
    velas = [p.split(",") for p in str(dados.get("c15m") or "").split(";") if p.count(",") >= 3]
    if len(velas) >= 2:
        try:
            v = velas[-2]
            ohlc = {"o": float(v[0]), "h": float(v[1]), "l": float(v[2]), "c": float(v[3])}
        except Exception:
            ohlc = None
    return ab, ohlc


def _cv_epoch_corretora(txt):
    from datetime import datetime as _d, timezone as _z
    try:
        return int(_d.strptime(str(txt)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_z.utc).timestamp())
    except Exception:
        return None


def _cv_atestar(dados, bot_token=""):
    """hml8 — ponte do motor dos Ciclos. Lê o LEITOR DO MOTOR (BT_CV_ESPELHO =
    pasta de dados do bt_motor_leitura_hml: SAUDE.json + ATUAL.json + barras/),
    confere identidade (conta, símbolo, instalação MT5, barra e OHLC) e fuso
    (EA × motor), e só então assina com bt_conector_atestado v0.4. Nunca
    levanta: falha vira dados['cv_atestado_falha'] (motivo curto, sem segredo);
    a saúde do motor vai SEMPRE em dados['cv_motor'] (telemetria, não autoridade)."""
    global _CV_LEITOR
    import hashlib as _h
    dados.pop("cv_atestado", None)
    dados.pop("cv_atestado_falha", None)
    dados.pop("cv_motor", None)
    mot = {"versao_ponte_conector": "hml11"}
    dados["cv_motor"] = mot

    def falha(estado, motivo):
        mot["estado"] = estado
        mot["motivo"] = motivo
        dados["cv_atestado_falha"] = f"{estado}: {motivo}"

    base = os.environ.get("BT_CV_ESPELHO", "").strip()
    if not base:
        return falha("nao_configurado", "BT_CV_ESPELHO ausente no PC (pasta de dados do leitor do motor)")
    if not os.path.isdir(base):
        return falha("nao_configurado", "BT_CV_ESPELHO aponta para pasta inexistente")
    sau = _cv_ler_json(os.path.join(base, "SAUDE.json"))
    if not sau:
        return falha("processo_parado", "SAUDE.json ausente — leitor do motor nunca rodou nesta pasta")
    idade_hb = _cv_iso_idade(sau.get("agora_utc"))
    mot.update({"heartbeat_idade_s": None if idade_hb is None else int(idade_hb),
                "pid": sau.get("pid"), "leitor": sau.get("leitor"), "login": sau.get("login"),
                "servidor": sau.get("servidor"), "conta_demo": sau.get("conta_demo"),
                "ativo": sau.get("ativo"), "off_motor_s": sau.get("off_corretora_s"),
                "off_motor_fonte": sau.get("off_fonte"), "erro_ultimo": sau.get("erro_ultimo"),
                "hashes": {k: (v or "")[:16] for k, v in (sau.get("hashes") or {}).items()}})
    if idade_hb is None or idade_hb > _CV_HEARTBEAT_MAX_S:
        return falha("processo_parado", f"leitor do motor sem batimento há {mot['heartbeat_idade_s']}s")
    if sau.get("erro_ultimo"):
        return falha("motor_com_erro", str(sau.get("erro_ultimo"))[:160])

    simbolo = (dados.get("simbolo") or "").strip()
    magic = _cv_int(dados.get("magic")) or 0
    if not simbolo or magic <= 0:
        return falha("snapshot_invalido", f"snapshot sem simbolo/magic validos (simbolo={simbolo!r} magic={magic})")
    # identidade: conta, símbolo, instalação MT5
    conta_ea = _cv_int(dados.get("conta"))
    mot["conta_ea"] = conta_ea
    if sau.get("login") is None or conta_ea is None or int(sau["login"]) != conta_ea:
        return falha("identidade_divergente", f"conta do motor {sau.get('login')} ≠ conta do EA {conta_ea}")
    if not sau.get("conta_demo"):
        return falha("identidade_divergente", "leitor do motor não está em conta DEMO")
    if str(sau.get("ativo")) != simbolo:
        return falha("identidade_divergente", f"motor lê {sau.get('ativo')} e o EA é {simbolo}")
    try:
        pin = ler_mt5_pin()
    except Exception:
        pin = None
    dp = sau.get("data_path") or ""
    if pin and dp:
        mesmo = os.path.normcase(os.path.normpath(os.path.dirname(pin.rstrip("\\/")))) == \
            os.path.normcase(os.path.normpath(dp))
        mot["instalacao_confere"] = bool(mesmo)
        if not mesmo:
            return falha("identidade_divergente", "instalação MT5 do motor ≠ instalação fixada no conector")
    else:
        mot["instalacao_confere"] = None
    # fuso: EA (TimeCurrent − TimeGMT) é a referência; o motor confere pelo tick
    tsrv, tgmt = _cv_int(dados.get("tsrv")), _cv_int(dados.get("tgmt"))
    off_ea = int(round((tsrv - tgmt) / 60.0)) * 60 if (tsrv and tgmt) else None
    mot["off_ea_s"] = off_ea
    if off_ea is None:
        return falha("fuso_indisponivel", "EA sem tsrv/tgmt (EA < v7.80) — sem conversão corretora→UTC")
    if sau.get("off_corretora_s") is not None and int(sau["off_corretora_s"]) != off_ea:
        return falha("fuso_divergente", f"fuso EA {off_ea}s ≠ fuso medido pelo motor {sau['off_corretora_s']}s")
    # barra: a pasta publicada pelo motor tem que ser a barra M15 fechada do EA
    atual = _cv_ler_json(os.path.join(base, "ATUAL.json"))
    if not atual or not atual.get("pasta"):
        return falha("espelho_ausente", "ATUAL.json ausente — motor ainda não publicou barra")
    mot.update({"barra_motor_corretora": atual.get("barra_corretora"),
                "publicado_idade_s": (lambda x: None if x is None else int(x))(_cv_iso_idade(atual.get("publicado_utc"))),
                "ohlc_motor": atual.get("m15")})
    if atual.get("erro_motor"):
        return falha("motor_com_erro", f"motor não calculou a barra: {str(atual['erro_motor'])[:140]}")
    ab_ea, ohlc_ea = _cv_barra_ea(dados)
    ab_mot = _cv_epoch_corretora(atual.get("barra_corretora"))
    mot["barra_ea_corretora_epoch"] = ab_ea
    mot["barra_motor_corretora_epoch"] = ab_mot
    mot["ohlc_ea"] = ohlc_ea
    if ab_ea is None or ab_mot is None:
        return falha("barra_indisponivel", "barra M15 do EA ou do motor sem carimbo")
    if ab_mot < ab_ea:
        return falha("espelho_atrasado", f"motor na barra {atual.get('barra_corretora')} e o EA já fechou a seguinte (atraso {ab_ea - ab_mot}s)")
    if ab_mot > ab_ea:
        return falha("espelho_adiantado", f"motor {ab_mot - ab_ea}s à frente do EA (EA atrasado ou outra fonte)")
    om = atual.get("m15") or {}
    if ohlc_ea and om:
        try:
            pt = float(dados.get("pt") or 0)
        except Exception:
            pt = 0.0
        tol = 0.5 * pt if pt > 0 else abs(float(om.get("c") or 1.0)) * 1e-6
        mot["ohlc_tolerancia"] = tol
        confere = all(k in om and abs(float(om[k]) - float(ohlc_ea[k])) <= tol
                      for k in ("o", "h", "l", "c"))
        mot["ohlc_confere"] = bool(confere)
        if not confere:
            return falha("identidade_divergente", "OHLC da barra M15 do motor ≠ OHLC do EA (fonte diferente)")
    else:
        mot["ohlc_confere"] = None
    if not os.environ.get("BT_CV_SEGREDO", "").strip():
        return falha("segredo_ausente", "BT_CV_SEGREDO ausente no PC")
    if not bot_token:
        return falha("token_ausente", "snapshot sem bot_token")
    mdir = os.environ.get("BT_CV_MOTOR_DIR", "").strip()
    if mdir and mdir not in sys.path:
        sys.path.insert(0, mdir)
    pasta_barra = os.path.join(base, atual["pasta"])
    chave = (pasta_barra, magic, simbolo, off_ea, _h.sha256(bot_token.encode("utf-8")).hexdigest())
    try:
        if chave in _CV_CACHE:
            at, resumo = _CV_CACHE[chave]
            mot["cache"] = True
        else:
            if _CV_LEITOR is None:
                from bt_conector_atestado import LeitorConfiavel, VERSAO as _V
                _CV_LEITOR = LeitorConfiavel(base)
                mot["assinador"] = _V
            at, resumo = _CV_LEITOR.ler_e_assinar_motor(
                pasta_barra, simbolo, magic, simbolo=simbolo, bot_token=bot_token,
                off_corretora_s=off_ea, agora_utc=_d_agora_utc(), com_resumo=True)
            _CV_CACHE.clear()
            _CV_CACHE[chave] = (at, resumo)
            mot["cache"] = False
        # frescor no envio (o cache não pode reapresentar leitura vencida)
        idade = _cv_iso_idade(at.get("ts_barra_m15"))
        if idade is None or idade > 900:
            return falha("leitura_antiga", f"atestado da barra fechada há {None if idade is None else int(idade)}s")
        dados["cv_atestado"] = at
        mot.update({"estado": "ok", "motivo": "atestado assinado pelo motor nesta barra",
                    "leitura": {k: resumo.get(k) for k in ("topdown", "estado_unico", "classificacao",
                                                           "janela_10_15", "degrau_m15", "fase", "conclusao")},
                    "dirs": {k: (v or {}).get("dir") for k, v in (resumo.get("por_tf") or {}).items()},
                    "por_tf": resumo.get("por_tf")})
        # hml10 (C27R19) — candidatos M15/M30/H1 calculados pelo leitor (telemetria NÃO assinada).
        # Só vão junto de uma barra cuja identidade conferiu; nos 3 primeiros snapshots da barra.
        try:
            kc = (pasta_barra, magic)
            n_env = _CV_CAND_ENVIOS.get(kc, 0)
            if n_env < _CV_CAND_MAX:
                cand = _cv_ler_json(os.path.join(pasta_barra, "candidatos.json"))
                if cand:
                    mot["candidatos"] = cand
                    if len(_CV_CAND_ENVIOS) > 50:
                        _CV_CAND_ENVIOS.clear()
                    _CV_CAND_ENVIOS[kc] = n_env + 1
        except Exception as _e:
            mot["candidatos_erro"] = f"{type(_e).__name__}"
        # hml11 (C27R23) — ATESTADO DE CANDIDATOS (contrato r01v5): os candidatos CONFIRMADOS em tempo real e
        # ainda válidos viajam ASSINADOS (mesmo HMAC, mesmo vínculo de bot/símbolo/magic/barra), em todo
        # snapshot da barra. É outro atestado: o cv_atestado (r01v4) segue intacto. Só descreve; quem decide é a API.
        try:
            kc5 = (pasta_barra, magic, _h.sha256(bot_token.encode("utf-8")).hexdigest())
            at5 = _CV_CAND_AT.get(kc5)
            if at5 is None:
                cand5 = _cv_ler_json(os.path.join(pasta_barra, "candidatos.json")) or {}
                at5 = _cv_assinar_candidatos(at, cand5, resumo, off_ea)
                if len(_CV_CAND_AT) > 50:
                    _CV_CAND_AT.clear()
                _CV_CAND_AT[kc5] = at5
            if at5:
                dados["cv_atestado_cand"] = at5
        except Exception as _e:
            mot["candidatos_assinatura_erro"] = f"{type(_e).__name__}: {str(_e)[:120]}"
        dbg(f"cv_atestado: motor {at.get('versao_motor')} barra {at.get('ts_barra_m15')} "
            f"veredito={((at.get('cv1') or {}).get('veredito'))}")
    except Exception as e:
        motivo = f"{type(e).__name__}: {str(e)[:160]}"
        falha("assinatura_recusada", motivo)
        if type(e).__name__ not in _CV_AVISOU:
            _CV_AVISOU.add(type(e).__name__)
            dbg(f"cv_atestado: falhou ({motivo}) — snapshot sem atestado")


_CV_CAND_AT = {}


def _cv_utc(txt_corretora, off_s):
    from datetime import datetime as _d, timezone as _z, timedelta as _t
    t = _d.strptime(str(txt_corretora)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_z.utc) - _t(seconds=int(off_s))
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cv_assinar_candidatos(at, cand, resumo, off_s):
    """Monta e assina o atestado r01v5. Só entram candidatos da MESMA barra e do MESMO ativo do atestado
    do motor, com confirmação em tempo real (conf-rt-1). Números viajam como texto: a assinatura não
    pode depender de como cada lado escreve um decimal. Devolve None se não houver o que assinar."""
    import bt_cv_atestado as _cvat5
    if not isinstance(cand, dict) or cand.get("erro") or not isinstance(cand.get("confirmacao"), dict):
        return None
    if str(cand.get("ativo")) != str(at.get("simbolo")):
        return None
    if _cv_utc(cand.get("agora_corretora"), off_s) != str(at.get("ts_barra_m15")).replace("+00:00", "Z")[:19] + "Z":
        return None                                    # candidatos de outra barra: não assina
    por_tf = (resumo or {}).get("por_tf") or {}
    lista = []
    for it in cand.get("itens") or []:
        if it.get("estado") != "confirmado":
            continue
        lista.append({"uid": str(it.get("uid")), "card": str(it.get("card")), "tf": str(it.get("tf")),
                      "lado": int(it.get("lado")), "modo": str(it.get("modo")),
                      "sinal_abre_utc": _cv_utc(it.get("ts_sinal"), off_s), "sinal_fecha_utc": _cv_utc(it.get("ts_sinal_fecha"), off_s),
                      "confirmado_utc": _cv_utc(it.get("ts_confirmacao"), off_s), "vence_utc": _cv_utc(it.get("ts_vence"), off_s),
                      "preco_ref": "%.6f" % float(it.get("preco_ref")), "stop": "%.6f" % float(it.get("stop")),
                      "corte_do_ciclo_agora": 1 if it.get("corte_ciclo_contra_agora") else 0,
                      "dir_do_timeframe": (por_tf.get(str(it.get("tf"))) or {}).get("dir")})
    slot = (cand.get("confirmacao") or {}).get("slot_agora") or {}
    corpo = {k: at[k] for k in ("bot_token_hash", "versao_motor", "simbolo", "magic", "ts_barra_m15", "cv1", "cv2")}
    corpo.update({"contrato": "r01v5", "confirmacao": str((cand.get("confirmacao") or {}).get("contrato")),
                  "leitor": str(cand.get("leitor")), "cards": str((cand.get("codigo") or {}).get("cards")),
                  "blindagem_agora": 1 if (slot.get("B1") or slot.get("B5")) else 0,
                  "candidatos": lista})
    return _cvat5.assinar(corpo)


def _d_agora_utc():
    from datetime import datetime as _d, timezone as _z
    return _d.now(_z.utc)


def enviar_snapshot(bot_token, dados):
    """Manda snapshot pro /conector/snapshot. Read-only.
    hml8: antes do POST, anexa saúde do motor (cv_motor) e, se toda a cadeia
    conferir, o atestado assinado (cv_atestado)."""
    if requests is None:
        return False
    _cv_atestar(dados, bot_token)