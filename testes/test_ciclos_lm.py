"""C27R13 — Learning Machine dos Ciclos contra o AMBIENTE ISOLADO LOCAL real
(API + GoTrue + PostgREST + Postgres, schema 0004 aplicado). Ambiente ausente = FALHA.
Cobre: leitura registrada por barra M15 (1 linha por barra, n_snapshots), trilha
snapshot→leituras→ciclos→atestado→veto, ordem fixa dos TFs, decisão consolidada do
backend (sem atestado = INCOMPLETO/BLOQUEADO), snapshot atrasado, EA sem carimbo
(barra estimada + falha_coleta), divergência de magic, posição sem evento de abertura,
atestado válido → AUTORIZADA e a repetição de decisão (reuso idempotente + consumo único
pela RPC) registrada na trilha. Nenhum token/segredo na resposta do painel."""
import hashlib, json, os, sys, time, uuid, urllib.request, urllib.error
import psycopg2, pytest

E = {k: os.environ.get(k, "") for k in ("BT_ISO_API", "BT_ISO_SUPABASE", "BT_ISO_ANON", "BT_ISO_EMAIL",
                                         "BT_ISO_SENHA", "BT_PG_ISOLADO_URL")}
SEGREDO = os.environ.get("BT_CV_SEGREDO", "")
OFF = 3 * 3600                                  # fuso da "corretora" no teste


def _req(metodo, url, corpo=None, tok=None):
    h = {"Content-Type": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    rq = urllib.request.Request(url, data=(json.dumps(corpo).encode() if corpo is not None else None),
                                headers=h, method=metodo)
    try:
        r = urllib.request.urlopen(rq, timeout=120); raw = r.read(); return r.status, json.loads(raw or b"{}"), raw
    except urllib.error.HTTPError as e:
        raw = e.read(); return e.code, json.loads(raw or b"{}"), raw


def _pg(sql, *a):
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); c.autocommit = True; cur = c.cursor()
    cur.execute(sql, a); r = cur.fetchall() if cur.description else None; c.close(); return r


def _magic(tok):
    h = hashlib.sha1(("bot|" + tok).encode()).hexdigest()
    return 100000 + (int(h[:12], 16) % 1_900_000_000)


def _det(tok, agora=None, cvt=True, cv1="U.U.U^.L.D", cv2="U.U.U.U", tgmt_atraso=0, extra=None, m15_sem=()):
    agora = int(agora or time.time())
    seg = {"MN1": None, "W1": 604800, "D1": 86400, "H4": 14400, "H1": 3600, "M30": 1800, "M15": 900, "M5": 300, "M1": 60}
    tempos = []
    for tf in ("MN1", "W1", "D1", "H4", "H1", "M30", "M15", "M5", "M1"):
        s = seg[tf] or 2592000
        tempos.append(str((agora // s) * s - s + OFF))
    vela = "4160.1,4161.2,4159.8,4160.9,120"
    d = {"magic": str(_magic(tok)), "simbolo": "XAUUSD", "tfop": "15m", "preco": "4162.92",
         "z1": "acima", "z5": "acima", "z15": "dentro", "z30": "acima", "z60": "acima", "z240": "abaixo", "zD": "acima",
         "c5m": ";".join([vela] * 18), "c15m": ";".join([vela] * 18), "c60m": ";".join([vela] * 18),
         "c4h": ";".join([vela] * 18), "c1m": ";".join([vela] * 18), "c30m": ";".join([vela] * 18),
         "cv1": cv1, "cv2": cv2, "eav": "7.80-ciclos-lm1", "spr": "12", "pt": "0.01",
         "tsrv": str(agora - tgmt_atraso + OFF), "tgmt": str(agora - tgmt_atraso)}
    if cvt:
        d["cvt"] = ".".join(tempos)
        t0s = []
        for tf in ("MN1", "W1", "D1", "H4", "H1", "M30", "M15", "M5", "M1"):
            s_ = seg[tf] or 2592000
            t0s.append(str((agora // s_) * s_ + OFF))
        d["cvt0"] = ".".join(t0s)
        # m15h: aberturas das 96 M15 fechadas que a "corretora" teve (exceto m15_sem, em UTC de abertura)
        ab = [(agora // 900) * 900 - 900 * k for k in range(1, 97)]
        ab = [x for x in ab if x not in set(m15_sem)]
        d["m15h"] = ",".join([str(ab[0] + OFF)] + [str((ab[i - 1] - ab[i]) // 900) for i in range(1, len(ab))])
        d["cD"] = ";".join([vela] * 12); d["eav"] = "7.81-ciclos-lm2"
    d.update(extra or {})
    return d


def _snap(tok, det, magic=None, pos=0):
    return _req("POST", E["BT_ISO_API"] + "/conector/snapshot", {
        "bot_token": tok, "conta_login": "52648209", "corretora": "Raw Trading Ltd", "simbolo": "XAUUSD",
        "magic_number": magic if magic is not None else _magic(tok), "equity": 1000, "balance": 1000,
        "margem_livre": 1000, "posicoes_abertas": pos, "lucro_flutuante": 0, "drawdown_atual": 0,
        "detalhe": det})


def _barra_m15(agora=None):
    agora = int(agora or time.time())
    from datetime import datetime, timezone
    return datetime.fromtimestamp((agora // 900) * 900, timezone.utc)   # instante em que a M15 FECHOU


@pytest.fixture(scope="module")
def amb():
    faltam = [k for k, v in E.items() if not v]
    assert not faltam and os.environ.get("BT_PG_CONFIRMO_ISOLADO") == "1", f"ambiente ausente (FALHA): {faltam}"
    assert _pg("select to_regclass('public._bt_homolog_marker') is not null")[0][0]
    assert _pg("select to_regclass('public.ciclo_trilha') is not null")[0][0], "0004 nao aplicada"
    s, j, _ = _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/token?grant_type=password",
                   {"email": E["BT_ISO_EMAIL"], "password": E["BT_ISO_SENHA"]})
    if s != 200:   # GoTrue exige apikey
        rq = urllib.request.Request(E["BT_ISO_SUPABASE"] + "/auth/v1/token?grant_type=password",
                                    data=json.dumps({"email": E["BT_ISO_EMAIL"], "password": E["BT_ISO_SENHA"]}).encode(),
                                    headers={"Content-Type": "application/json", "apikey": E["BT_ISO_ANON"]}, method="POST")
        j = json.loads(urllib.request.urlopen(rq, timeout=60).read())
    sess = j["access_token"]
    bots = {}
    for k in ("A", "B", "C", "D"):
        s, r, _ = _req("POST", E["BT_ISO_API"] + "/conector/registrar",
                       {"nome": f"clm-{k}-" + uuid.uuid4().hex[:6], "simbolo": "XAUUSD"}, tok=sess)
        assert s == 200, r
        bid = _pg("select id from conector_bots where bot_token=%s", r["bot_token"])[0][0]
        bots[k] = {"tok": r["bot_token"], "id": bid}
    return {"sess": sess, "bots": bots}


def _ao_vivo(amb, bot_id):
    s, j, raw = _req("POST", E["BT_ISO_API"] + "/learning/ciclos/ao-vivo", {"bot_id": bot_id}, tok=amb["sess"])
    assert s == 200, j
    return j, raw


def test_1_leitura_por_barra_e_trilha(amb):
    b = amb["bots"]["A"]
    s, j, _ = _snap(b["tok"], _det(b["tok"]))
    assert s == 200 and not j.get("ignorado"), j
    barra = _barra_m15()
    rows = _pg("select n_snapshots, completa, decisao, regra, motivo, alinhado_c1, alinhado_c2 from ciclo_leituras "
               "where bot_id=%s and barra_m15=%s", b["id"], barra)
    assert len(rows) == 1
    n, completa, dec, regra, motivo, a1, a2 = rows[0]
    assert (n, completa, dec, regra) == (1, True, "bloquear", "R-CICLO-01.atestado")
    assert "atestado_ausente" in motivo and a1 is True and a2 is True
    _snap(b["tok"], _det(b["tok"]))                              # 2º snapshot da MESMA barra
    assert _pg("select n_snapshots from ciclo_leituras where bot_id=%s and barra_m15=%s", b["id"], barra)[0][0] == 2
    etapas = [r[0] for r in _pg("select etapa from ciclo_trilha where bot_id=%s and barra_m15=%s order by id",
                                b["id"], barra)]
    assert etapas == ["snapshot", "leituras", "ciclos", "atestado", "veto"], etapas


def test_2_painel_ordem_resumo_e_sem_segredos(amb):
    b = amb["bots"]["A"]
    j, raw = _ao_vivo(amb, b["id"])
    tfs = [l["tf"] for l in j["leituras"]["linhas"]]
    assert tfs == ["D1", "H4", "H1", "M30", "M15", "M5", "M1", "W1", "MN1"]
    por = {l["tf"]: l for l in j["leituras"]["linhas"]}
    assert por["M15"]["referencia_decisao"] and por["M15"]["estado_dado"] == "atual"
    from datetime import timedelta
    assert por["M15"]["barra_fechada_utc"] == (_barra_m15() - timedelta(minutes=15)).isoformat()
    assert por["M15"]["barra_formacao_desde_utc"] == _barra_m15().isoformat() == j["leituras"]["barra_m15_utc"]
    assert por["M5"]["estrutura"]["rompimento_iminente"] is False and por["M15"]["estrutura"]["rompimento_iminente"]
    assert por["H1"]["direcao"] == "baixa" and por["M30"]["resultado"] == "neutro" and por["D1"]["resultado"] == "favoravel_compra"
    assert por["M30"]["canal_ema20"] == "acima" and por["H4"]["posicao_preco"].startswith("abaixo")
    assert por["D1"]["ranking"] is None                             # nenhum contrato define ranking: não inventa
    c = j["ciclos"]
    assert c["ciclo1"]["etapa"] == "M1 → M5 → M15 (completo)" and c["ciclo2"]["alinhado"]
    cons = c["consolidada"]
    assert cons["decisao"] == "bloquear" and cons["estado"] == "INCOMPLETO/BLOQUEADO"
    assert cons["modo_operacional"] == "observar"
    assert j["contadores"]["barras_analisadas"] >= 1 and j["contadores"]["vetos_por_motivo"].get("R-CICLO-01.atestado")
    assert j["saude"]["versoes"]["ea"] == "7.81-ciclos-lm2" and j["saude"]["mt5"] == "online"
    assert b["tok"].encode() not in raw and b"bot_token" not in raw


def test_3_snapshot_atrasado(amb):
    b = amb["bots"]["B"]
    _snap(b["tok"], _det(b["tok"], tgmt_atraso=300))
    j, _ = _ao_vivo(amb, b["id"])
    assert {l["estado_dado"] for l in j["leituras"]["linhas"] if l["tf"] in ("M1", "M5", "M15")} == {"atrasado"}


def test_4_ea_sem_carimbo_barra_estimada(amb):
    b = amb["bots"]["C"]
    s, j, _ = _snap(b["tok"], _det(b["tok"], cvt=False))
    assert s == 200
    jj, _ = _ao_vivo(amb, b["id"])
    assert {l["estado_dado"] for l in jj["leituras"]["linhas"] if l["tf"] != "MN1"} == {"sem_carimbo"}
    assert any("carimbo" in f for f in jj["ciclos"]["faltam"])
    assert jj["ciclos"]["consolidada"]["regra"] == "CLM.leitura_obrigatoria"
    r = _pg("select falhas from ciclo_leituras where bot_id=%s", b["id"])
    assert r and "barra_estimada" in r[0][0]
    assert _pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='falha_coleta'", b["id"])[0][0] == 1


def test_5_divergencia_de_magic(amb):
    b = amb["bots"]["C"]
    s, j, _ = _snap(b["tok"], _det(b["tok"]), magic=_magic(b["tok"]) + 1)
    assert s == 200 and j.get("ignorado")
    assert _pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='divergencia' and motivo like 'snapshot com magic%%'",
               b["id"])[0][0] == 1


def test_6_posicao_sem_evento_de_abertura(amb):
    b = amb["bots"]["D"]
    _snap(b["tok"], _det(b["tok"]), pos=1)
    assert _pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='divergencia' and motivo like 'MT5 informa%%'",
               b["id"])[0][0] == 1
    j, _ = _ao_vivo(amb, b["id"])
    assert j["saude"]["divergencia_posicao"] is True and j["saude"]["operacoes_abertas_bm"] == 0


def test_7_atestado_valido_autoriza_e_repeticao_de_decisao(amb):
    assert SEGREDO, "BT_CV_SEGREDO precisa estar no teste E na API local (FALHA, nao skip)"
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import bt_cv_atestado as cvat
    b = amb["bots"]["D"]
    barra = _barra_m15()
    at = cvat.assinar({"bot_token_hash": hashlib.sha256(b["tok"].encode()).hexdigest(),
                       "versao_motor": "teste-local-clm", "simbolo": "XAUUSD", "magic": _magic(b["tok"]),
                       "ts_barra_m15": barra.isoformat(),
                       "cv1": {"janela": {"M1": 1, "M5": 1, "M15": 1}, "veredito": "autorizada"},
                       "cv2": {"dirs": {"D1": 1, "H4": 1}}}, segredo=SEGREDO)
    _snap(b["tok"], _det(b["tok"], extra={"cv_atestado": at}))
    j, raw = _ao_vivo(amb, b["id"])
    cons = j["ciclos"]["consolidada"]
    assert (cons["decisao"], cons["estado"]) == ("comprar", "AUTORIZADA"), cons
    assert j["ciclos"]["atestado"]["estado"] == "verificado"
    assert at["assinatura"].encode() not in raw                 # assinatura só truncada
    # repetição de decisão pela autoridade real (em processo, mesmo banco)
    os.environ.setdefault("BT_CV_SEGREDO", SEGREDO)
    import api
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    ok1, d1 = api._r01_emitir_decisao(sb, bot, "buy")
    ok2, d2 = api._r01_emitir_decisao(sb, bot, "buy")
    assert ok1 and ok2 and d1["id"] == d2["id"], (d1, d2)       # reuso idempotente na mesma barra
    okr, cmd = api._r01_abrir_via_rpc(sb, bot, "buy", {"decisao_id": d1["id"], "volume": 0.01}, "teste_clm")
    assert okr, cmd
    okr2, mot = api._r01_abrir_via_rpc(sb, bot, "buy", {"decisao_id": d1["id"], "volume": 0.01}, "teste_clm")
    assert not okr2                                              # consumo único
    et = _pg("select etapa, estado from ciclo_trilha where bot_id=%s and correlacao=%s order by id", b["id"], d1["uid"])
    assert ("persistencia", "ok") in et and ("rpc", "ok") in et and ("comando", "pendente") in et, et
    assert _pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='rpc' and estado='recusado'", b["id"])[0][0] >= 1
    # exportação da barra: decisão + comando + trilha, sem token
    s, ex, raw = _req("POST", E["BT_ISO_API"] + "/learning/ciclos/exportar",
                      {"bot_id": b["id"], "barra_m15": barra.isoformat()}, tok=amb["sess"])
    assert s == 200 and ex["leitura"] and ex["decisoes"] and ex["comandos"], ex
    assert b["tok"].encode() not in raw
    # entrega ao conector → resposta do MT5 → evento de abertura: tudo na mesma trilha
    s, ent, _ = _req("POST", E["BT_ISO_API"] + "/mt5/comando/pendente/checar", {"bot_token": b["tok"]})
    assert s == 200 and (ent.get("comando") or {}).get("id") == cmd["id"], ent
    s, cf, _ = _req("POST", E["BT_ISO_API"] + "/mt5/comando/confirmar",
                    {"comando_id": cmd["id"], "sucesso": True, "resultado": {"ticket": 998877, "preco_real": 4162.9}})
    assert s == 200 and cf["status"] == "executado", cf
    s, ev, _ = _req("POST", E["BT_ISO_API"] + "/conector/evento",
                    {"bot_token": b["tok"], "tipo": "aberto",
                     "detalhe": {"lado": "buy", "preco": "4162.9", "ticket": "998877", "razao": "expert"}})
    assert s == 200, ev
    et = _pg("select etapa, estado from ciclo_trilha where bot_id=%s and correlacao=%s order by id", b["id"], d1["uid"])
    assert ("comando", "ok") in et and ("resposta_mt5", "ok") in et, et
    assert _pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='abertura'", b["id"])[0][0] == 1
    j, _ = _ao_vivo(amb, b["id"])
    c0 = [c for c in j["autoridade"]["comandos"] if c["id"] == cmd["id"]][0]
    assert c0["executada"] and c0["ticket"] == 998877 and c0["uid"] == d1["uid"]
    assert [d for d in j["autoridade"]["decisoes"] if d["uid"] == d1["uid"]][0]["consumo_unico"] is True


def test_8_idades_separadas_e_rotulo_da_corretora(amb):
    b = amb["bots"]["B"]
    _snap(b["tok"], _det(b["tok"]))
    j, _ = _ao_vivo(amb, b["id"])
    por = {l["tf"]: l for l in j["leituras"]["linhas"]}
    agora = int(time.time())
    m15 = por["M15"]
    assert m15["tempo_em_formacao_s"] is not None and 0 <= m15["tempo_em_formacao_s"] < 900
    assert m15["idade_barra_fechada_s"] == m15["tempo_em_formacao_s"]           # mercado contínuo: fechou quando a atual abriu
    assert m15["idade_snapshot_s"] is not None and m15["idade_snapshot_s"] <= 5
    assert por["D1"]["barra_corretora"].startswith("dia ") and "UTC+3" in por["D1"]["barra_corretora"]
    assert por["MN1"]["barra_fechada_fim_utc"] is not None                       # MN1 pelo calendário da corretora
    assert por["M5"]["forca"]["fonte"].startswith("contrato _sinal_forca") and por["M5"]["ranking"] is None
    assert por["D1"]["volatilidade_range_medio"] is not None                     # cD (EA 7.81)
    assert j["ciclos"]["estagios"]["decisao_autorizada"] is False and j["ciclos"]["estagios"]["leitura_coletada"]
    assert [e["estado"] for e in j["ciclos"]["elos"]][:2] == ["falha", "falha"]   # conector de teste sem ponte


def test_9_lacunas_coleta_x_mercado_fechado(amb):
    b = amb["bots"]["C"]
    agora = int(time.time())
    base = (agora // 900) * 900
    _snap(b["tok"], _det(b["tok"], agora=agora - 3600))                          # barra T-60min
    # a "corretora" NÃO teve as barras que fecharam em T-30 e T-15 (abertas em T-45 e T-30)
    _snap(b["tok"], _det(b["tok"], m15_sem=(base - 2700, base - 1800)))
    j, _ = _ao_vivo(amb, b["id"])
    lb = j["saude"]["lacunas_barras"]
    assert (lb["ausencia_de_coleta"], lb["mercado_fechado"]) == (1, 2), j["saude"]["lacunas_m15"]


def test_10_rotulos_de_ciclo_sem_direcao(amb):
    b = amb["bots"]["B"]
    _snap(b["tok"], _det(b["tok"], cv1="L.L.U.L.L", cv2="L.D.L.L"))
    j, _ = _ao_vivo(amb, b["id"])
    c1, c2 = j["ciclos"]["ciclo1"], j["ciclos"]["ciclo2"]
    assert c1["calculado"] and not c1["alinhado"] and c1["etapa"].startswith("escada não começa: M1 lateral")
    assert c1["leituras_txt"] == "M1 lateral · M5 lateral · M15 alta"
    assert c2["etapa"] == "D1 lateral · H4 lateral — sem direção de referência"
