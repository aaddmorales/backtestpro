"""C27R21 — relatório da BabyMachine (/learning/relatorio/gerar e /baixar), contra o AMBIENTE ISOLADO
LOCAL. Testes SINTÉTICOS: snapshots e avaliações fabricados aqui. Cada número do relatório é conferido
contra o banco, não contra um valor suposto. Nada disto é evidência da plataforma."""
import hashlib, json, os, sys, time, uuid
from datetime import datetime, timezone, timedelta
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI); sys.path.insert(0, os.path.dirname(AQUI))
import test_ciclos_lm as T
import test_selecao as S

amb = T.amb
api = S.api
URL = T.E["BT_ISO_API"]


def _bot(amb, simbolo="XAUUSD"):
    s, r, _ = T._req("POST", URL + "/conector/registrar", {"nome": "rel-" + uuid.uuid4().hex[:8], "simbolo": simbolo}, tok=amb["sess"])
    assert s == 200, r
    return {"tok": r["bot_token"], "id": T._pg("select id from conector_bots where bot_token=%s", r["bot_token"])[0][0]}


def _gerar(amb, bot_id, **kw):
    s, j, raw = T._req("POST", URL + "/learning/relatorio/gerar", dict({"bot_id": bot_id, "fuso": "Europe/Helsinki"}, **kw), tok=amb["sess"])
    return s, j, raw


def _baixar(amb, rid, fmt, tok="sess"):
    import urllib.request, urllib.error
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = "Bearer " + amb[tok]
    rq = urllib.request.Request(URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": rid, "formato": fmt}).encode(), headers=h, method="POST")
    try:
        r = urllib.request.urlopen(rq, timeout=120)
        return r.status, dict((k.lower(), v) for k, v in r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, {}, e.read()


def _atestado(b, veredito, d1=1, h4=1, jan=None, agora=None):
    import bt_cv_atestado as cvat
    return cvat.assinar({"bot_token_hash": hashlib.sha256(b["tok"].encode()).hexdigest(), "versao_motor": "teste-rel",
                         "simbolo": "XAUUSD", "magic": T._magic(b["tok"]), "ts_barra_m15": T._barra_m15(agora).isoformat(),
                         "cv1": {"janela": jan or {"M1": 1, "M5": 1, "M15": 1}, "veredito": veredito, "motivo": "teste"},
                         "cv2": {"dirs": {"D1": d1, "H4": h4}}}, segredo=T.SEGREDO)


def _etapa(j, prefixo):
    return next(e for e in j["cadeia"]["etapas"] if e["etapa"].startswith(prefixo))


def _sem_segredo(raw, b):
    t = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    assert b["tok"] not in t and "bot_token" not in t and "sb_secret" not in t and "service_role" not in t
    import re
    assert not re.search(r'"[^"]*(assinatura|token|segredo|secret|hmac)[^"]*"\s*:', t.lower())      # nenhuma CHAVE com cara de segredo


def test_1_sem_operacao_e_falha_de_integracao_pdf_e_json_iguais(amb):
    """Bot sem atestado: a barra fica BLOQUEADA por integração. O relatório existe mesmo sem operação."""
    b = _bot(amb)
    assert T._snap(b["tok"], T._det(b["tok"]))[0] == 200
    s, j, raw = _gerar(amb, b["id"], periodo="hoje")
    assert s == 200, j
    _sem_segredo(raw, b)
    assert j["persistido"] is True and j["relatorio_id"].startswith("REL-%d-" % b["id"])
    linha = T._pg("select decisao, regra, n_snapshots from ciclo_leituras where bot_id=%s", b["id"])
    assert len(linha) == 1 and linha[0][:2] == ("bloquear", "R-CICLO-01.atestado")
    assert _etapa(j, "1.")["barras"] == {"valor": 1, "situacao": "contado"}
    assert _etapa(j, "4.")["barras"] == {"valor": 0, "situacao": "zero confirmado"}
    for k in ("6.", "7.", "8."):
        assert _etapa(j, k)["barras"]["situacao"] == "zero confirmado"
    v = j["cadeia"]["resultado_por_regra"][0]
    assert (v["regra"], v["classe"], v["barras"]) == ("R-CICLO-01.atestado", "falha de integração", 1)
    assert j["saude"]["contagens"]["operacoes"] == {"valor": 0, "situacao": "zero confirmado"}
    assert j["selecao"]["avaliacoes_no_periodo"]["valor"] == 0 and j["selecao"]["ultima_avaliacao"] is None
    assert "nenhuma execução é disparada" in j["selecao"]["frase"]
    assert j["identificacao"]["modo_operacional"] == "observar" and j["identificacao"]["magic"] == T._magic(b["tok"])
    assert len(j["leituras_por_timeframe"]["linhas"]) == 9
    assert [q["pergunta"][:9] for q in j["resumo"]["perguntas"]][0] == "O sistema" and len(j["resumo"]["perguntas"]) == 6
    assert any("sem atestado válido" in a for a in j["resumo"]["atencao"])
    el = j["saude"]["elos_do_atestado"]["elos"]
    assert len(el) == 8 and [e["elo"][:2] for e in el] == [f"{i}." for i in range(1, 9)]
    # fuso: horário local = UTC + diferença informada; abertura = fechamento − 15 min
    br = j["leituras_por_timeframe"]["barra_de_referencia"]
    f = datetime.strptime(br["fechamento_utc"], "%Y-%m-%dT%H:%M:%SZ")
    assert datetime.strptime(br["abertura_utc"], "%Y-%m-%dT%H:%M:%SZ") == f - timedelta(minutes=15)
    assert j["fuso"]["nome"] == "Europe/Helsinki" and j["fuso"]["diferenca_para_utc"] in ("+0200", "+0300")
    assert datetime.strptime(br["fechamento_local"], "%Y-%m-%d %H:%M:%S") == f + timedelta(hours=int(j["fuso"]["diferenca_para_utc"][:3]))
    # o gravado é o que se baixa: JSON idêntico e PDF com o mesmo identificador
    s1, h1, corpo = _baixar(amb, j["relatorio_id"], "json")
    assert s1 == 200 and "attachment" in h1["content-disposition"] and j["relatorio_id"] in h1["content-disposition"]
    g = json.loads(corpo)
    for k in ("resumo", "selecao", "cadeia", "saude", "leituras_por_timeframe", "evidencia", "sha256_do_conteudo", "relatorio_id"):
        assert g[k] == j[k], k
    sem = {k: v for k, v in g.items() if k not in ("relatorio_id", "sha256_do_conteudo", "persistido")}
    assert hashlib.sha256(json.dumps(sem, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == g["sha256_do_conteudo"]
    s2, h2, pdf = _baixar(amb, j["relatorio_id"], "pdf")
    assert s2 == 200 and h2["content-type"] == "application/pdf" and pdf[:5] == b"%PDF-" and len(pdf) > 4000
    from pypdf import PdfReader
    import io
    txt = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)
    assert j["relatorio_id"] in txt and "R-CICLO-01.atestado" in txt and "Resumo" in txt and b["tok"] not in txt
    amb["rel1"] = {"bot": b, "rid": j["relatorio_id"]}


def test_2_veto_do_motor_e_d1_h4(amb):
    """Atestado VÁLIDO com D1 contra: veto do motor (não é falha de integração)."""
    b = _bot(amb)
    at = _atestado(b, "bloqueada", d1=-1)
    assert T._snap(b["tok"], T._det(b["tok"], extra={"cv_atestado": at}))[0] == 200
    s, j, raw = _gerar(amb, b["id"], periodo="hoje")
    assert s == 200, j
    _sem_segredo(raw, b)
    assert at["assinatura"].encode() not in raw
    reg = T._pg("select decisao, regra, motivo from ciclo_leituras where bot_id=%s", b["id"])[0]
    assert reg[:2] == ("bloquear", "R-CICLO-01.cv1_bloqueada")
    v = j["cadeia"]["resultado_por_regra"][0]
    assert (v["regra"], v["classe"]) == ("R-CICLO-01.cv1_bloqueada", "veto do motor") and v["exemplo"]["valores_usados"] == reg[2]
    assert _etapa(j, "4.")["barras"]["valor"] == 1 and _etapa(j, "5.")["barras"]["valor"] == 0
    D = j["selecao"]["d1_h4"]
    assert D["veto_por_d1_h4_no_periodo"]["valor"] == 1 and "CONTEXTO" in D["selecao_proposta_sel_1"] and "VETO" in D["contrato_atual_r01v4"]
    H = j["historico_x_agora"]
    assert H["registrada"]["regra"] == "R-CICLO-01.cv1_bloqueada" and H["registrada"]["atestado_na_barra"] == "verificado"
    assert [t["etapa"] for t in H["trilha_da_barra"]].count("veto") == 1


def test_3_autorizada_em_observar_nao_vira_comando(amb):
    b = _bot(amb)
    at = _atestado(b, "autorizada")
    assert T._snap(b["tok"], T._det(b["tok"], extra={"cv_atestado": at}))[0] == 200
    s, j, _ = _gerar(amb, b["id"], periodo="ultima_barra")
    assert s == 200, j
    assert j["periodo"]["tipo"] == "ultima_barra" and j["evidencia"]["barras_no_periodo"] == 1
    assert _etapa(j, "5.")["barras"]["valor"] == 1
    assert _etapa(j, "6.")["barras"] == {"valor": 0, "situacao": "zero confirmado"} and "observar" in _etapa(j, "6.")["detalhe"]
    assert T._pg("select count(*) from ciclo_decisoes where bot_id=%s", b["id"])[0][0] == 0
    assert T._pg("select count(*) from mt5_comandos where bot_id=%s", b["id"])[0][0] == 0      # gerar relatório não cria nada
    assert "modo observar" in j["resumo"]["perguntas"][4]["resposta"]


def test_4_nenhuma_elegivel_motivos_e_unidade_da_idade(api, amb):
    """Avaliação gravada pelo avaliador real (candidatos sintéticos): sinal vencido em H1, estudo sem selo,
    aguardando confirmação. O relatório não recalcula: repete o gravado e classifica o motivo."""
    b = _bot(amb)
    assert T._snap(b["tok"], T._det(b["tok"], extra={"cv_atestado": _atestado(b, "neutra")}))[0] == 200
    barra = T._barra_m15()
    sinal_h1 = (barra - timedelta(hours=3) + timedelta(seconds=S.OFF)).strftime("%Y-%m-%d %H:%M:%S")
    itens = [S._cand("card5_ema_9_21", "H1", -1, idade=8, sinal=sinal_h1),              # confirmado, mas velho
             S._cand("card2_rompimento_caixa", "M15", 1, estado="aguardando"),          # armado, sem confirmação
             S._cand("card3_segunda_entrada", "M30", 1)]            # confirmado e fresco, célula SEM selo
    det, leit, ciclos = S._cenario(itens, barra)
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    av = api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time()))
    T._pg("insert into selecao_avaliacoes (bot_id, simbolo, barra_m15, versao, n_candidatos, n_elegiveis, n_elegiveis_atual, avaliacao) "
          "values (%s,'XAUUSD',%s,'sel-1',%s,%s,%s,%s::jsonb)", b["id"], barra, av["resumo"]["candidatos"],
          av["resumo"]["elegiveis_proposto"], av["resumo"]["elegiveis_atual"], json.dumps(av, default=str))
    s, j, raw = _gerar(amb, b["id"], periodo="hoje")
    assert s == 200, j
    Sel = j["selecao"]
    assert Sel["avaliacoes_no_periodo"]["valor"] == 1 and Sel["candidatos_no_periodo"]["por_estado"] == av["resumo"]["por_estado"]
    pe = Sel["por_escala_no_periodo"]
    gravado = {tf: {e: sum(1 for c in av["grupos"][tf]["candidatos"] if c["elegibilidade"] == e)
                    for e in ("elegivel", "aguardando", "vetada", "sem_dados")} for tf in ("M15", "M30", "H1")}
    for tf in ("M15", "M30", "H1"):
        assert {e: pe[tf][e] for e in gravado[tf]} == gravado[tf], tf
        assert pe[tf]["candidatos"] == 1 and len(pe[tf]["todos_os_portoes"]) == 9
    assert pe["H1"]["categorias_do_primeiro_bloqueador"] == {"sinal vencido": {"n": 1, "portoes": {"3. frescor do sinal": 1}}}
    assert list(pe["M15"]["categorias_do_primeiro_bloqueador"]) == ["sinal aguardando confirmação"]
    assert list(pe["M30"]["categorias_do_primeiro_bloqueador"]) == ["estudo sem selo"]
    U = Sel["ultima_avaliacao"]
    h1 = U["por_escala"]["H1"]["candidatos"][0]
    g_h1 = av["grupos"]["H1"]["candidatos"][0]
    assert h1["primeiro_bloqueador"]["categoria"] == "sinal vencido" and h1["primeiro_bloqueador"]["detalhe"] in g_h1["primeiro_impedimento"]
    assert h1["idade"]["regra"] == 8 and "barras M15" in h1["idade"]["unidade_da_regra"] and h1["idade"]["limite_da_regra"] == 1
    assert h1["idade"]["barras_do_proprio_timeframe"] == 2 and h1["idade"]["tempo_desde_o_fechamento_da_barra_do_sinal_min"] == 120
    m3 = next(m for m in h1["motivos"] if m["portao"].startswith("3."))
    assert m3["escala_da_regra"] == "M15" and m3["primeiro_bloqueador"] is True            # regra em M15 sob candidato H1: explícito
    assert len(h1["motivos"]) == sum(1 for p in g_h1["portoes"] if p["ok"] is not True and not (p["portao"][0] == "3" and p["ok"] is None))
    m15 = U["por_escala"]["M15"]["candidatos"][0]
    assert m15["sinal"] == "aguardando" and m15["elegibilidade"] == g_m15_estado(av)
    assert Sel["barras_com_elegivel"] == [] and j["resumo"]["perguntas"][2]["resposta"].startswith("Não.")
    assert "sinal vencido: 1" in j["resumo"]["perguntas"][3]["resposta"]
    assert Sel["ausencia_de_sinal"]["situacao"] == "não coletado por célula"
    s2, _, pdf = _baixar(amb, j["relatorio_id"], "pdf")
    assert s2 == 200 and pdf[:5] == b"%PDF-"


def g_m15_estado(av):
    return av["grupos"]["M15"]["candidatos"][0]["elegibilidade"]


def test_5_periodo_sem_dados_nao_inventa(amb):
    b = amb["rel1"]["bot"]
    de = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ate = (datetime.now(timezone.utc) - timedelta(days=3) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s, j, _ = _gerar(amb, b["id"], periodo="personalizado", de=de, ate=ate)
    assert s == 200, j
    assert (j["periodo"]["de_utc"], j["periodo"]["ate_utc"]) == (de, ate)
    assert j["evidencia"]["barras_no_periodo"] == 0 and j["resumo"]["perguntas"][0]["estado"] == "falha"
    assert j["leituras_por_timeframe"]["situacao"] == "não coletado" and j["leituras_por_timeframe"]["linhas"] == []
    assert j["saude"]["elos_do_atestado"]["situacao"] == "não coletado" and j["saude"]["elos_do_atestado"]["elos"] is None
    assert j["saude"]["cobertura"]["barras_m15_registradas"] == {"valor": 0, "situacao": "zero confirmado"}
    assert j["saude"]["cobertura"]["barras_m15_no_intervalo"] == 8
    assert j["saude"]["cobertura"]["lacunas"]["intervalos"] == 0          # sem barra vizinha não se atribui causa
    assert j["historico_x_agora"]["registrada"] is None
    assert _baixar(amb, j["relatorio_id"], "pdf")[2][:5] == b"%PDF-"
    assert _gerar(amb, b["id"], periodo="personalizado", de=ate, ate=de)[0] == 422
    assert _gerar(amb, b["id"], periodo="mes_que_vem")[0] == 422


def test_6_snapshots_repetidos_contados_como_no_banco(amb):
    b = _bot(amb)
    det = T._det(b["tok"])
    for _ in range(3):
        assert T._snap(b["tok"], det)[0] == 200                          # o MESMO snapshot três vezes
    n, dup = T._pg("select n_snapshots, coalesce((falhas->>'duplicados')::int, 0) from ciclo_leituras where bot_id=%s", b["id"])[0]
    s, j, _ = _gerar(amb, b["id"], periodo="hoje")
    assert s == 200, j
    assert j["saude"]["cobertura"]["snapshots_recebidos"]["valor"] == n
    assert j["saude"]["persistencia"]["snapshots_repetidos"]["valor"] == dup
    assert j["evidencia"]["barras_do_periodo"][0]["snapshots"] == n and j["evidencia"]["barras_no_periodo"] == 1
    assert j["saude"]["persistencia"]["decisoes_duplicadas"] == {"valor": 0, "situacao": "zero confirmado"}


def test_7_virada_de_barra_historico_nao_e_reescrito(amb):
    """Barra antiga, com snapshots chegando depois da validade: a decisão registrada fica; o 'agora' aparece ao lado."""
    b = _bot(amb)
    velho = int(time.time()) - 1000
    barra = T._barra_m15(velho)
    at = _atestado(b, "neutra", agora=velho)
    assert T._snap(b["tok"], T._det(b["tok"], agora=velho, extra={"cv_atestado": at}))[0] == 200
    antes = T._pg("select decisao, regra, motivo from ciclo_leituras where bot_id=%s and barra_m15=%s", b["id"], barra)[0]
    for _ in range(2):
        assert T._snap(b["tok"], T._det(b["tok"], agora=velho, extra={"cv_atestado": at}))[0] == 200
    depois = T._pg("select decisao, regra, motivo, falhas->'pos_validade'->>'n' from ciclo_leituras where bot_id=%s and barra_m15=%s", b["id"], barra)[0]
    assert depois[:3] == antes
    s, j, _ = _gerar(amb, b["id"], periodo="ultima_barra")
    assert s == 200, j
    H = j["historico_x_agora"]
    assert (H["registrada"]["decisao"], H["registrada"]["regra"], H["registrada"]["motivo"]) == antes
    assert H["barra_de_referencia"]["fechamento_utc"] == barra.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert str((H["registrada"]["avisos_pos_validade"] or {}).get("n")) == str(depois[3])
    assert j["saude"]["cobertura"]["barras_com_snapshot_depois_da_validade"]["valor"] == (1 if depois[3] else 0)
    assert "integracao_no_momento_da_geracao" in H and "motor" in H["integracao_no_momento_da_geracao"]
    assert "não é reescrita" in H["nota"]


def test_8_acesso_exige_sessao_e_posse(amb):
    b, rid = amb["rel1"]["bot"], amb["rel1"]["rid"]
    assert T._req("POST", URL + "/learning/relatorio/gerar", {"bot_id": b["id"]})[0] == 401          # sem sessão
    assert _baixar(amb, rid, "json", tok=None)[0] == 401
    assert _gerar(amb, 987654321)[0] == 404                                                          # bot inexistente
    assert _baixar(amb, "REL-1-20260101T000000Z-0123456789", "json")[0] == 404                       # relatório inexistente
    assert _baixar(amb, "../../etc/passwd", "json")[0] == 404
    assert _baixar(amb, rid, "exe")[0] == 422
    dono = T._pg("select user_id from conector_bots where id=%s", b["id"])[0][0]
    outro = T._pg("select id from auth.users where id <> %s limit 1", dono)[0][0]              # outro usuário REAL do ambiente
    try:
        T._pg("update conector_bots set user_id=%s where id=%s", outro, b["id"])                      # o bot passa a ser de OUTRO usuário
        assert _gerar(amb, b["id"])[0] == 404
        assert _baixar(amb, rid, "json")[0] == 404 and _baixar(amb, rid, "pdf")[0] == 404              # nem o relatório já gravado
    finally:
        T._pg("update conector_bots set user_id=%s where id=%s", dono, b["id"])
    try:
        T._pg("update relatorios_gerados set user_id=%s where id=%s", outro, rid)                     # relatório de outro usuário
        assert _baixar(amb, rid, "json")[0] == 404
    finally:
        T._pg("update relatorios_gerados set user_id=%s where id=%s", dono, rid)
    assert _baixar(amb, rid, "json")[0] == 200
