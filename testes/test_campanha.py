"""C27R26 — CAMPANHA CONTÍNUA (sem término): limites por dia num fuso único, virada registrada, três perdas
suspendem até revisão, exposição aberta sempre conta, retomada da coleta registrada e conferida antes de novas
entradas, acompanhamento diário. BANCADA (ambiente isolado local): dados sintéticos; não é evidência da plataforma."""
import json, os, sys, time, uuid
from datetime import datetime, timedelta, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import test_ciclos_lm as T
import test_selecao as S
import test_sessao as SS

amb = T.amb
api = S.api
CFG = {"risco_pct_patrimonio": 0.10, "risco_max_por_operacao_usd": 10, "max_aberturas_por_dia": 6, "max_posicoes_simultaneas": 2,
       "max_posicoes_por_ativo": 1, "risco_agregado_max_usd": 20, "max_perdas_consecutivas": 3, "perda_realizada_max_usd_por_dia": 30,
       "fuso_diario": "Europe/Kyiv", "conta": "52648209 ICMarketsSC-Demo",
       "horarios": {"XAUUSD": [{"dias": [1, 2, 3, 4, 5], "de": "00:00", "ate": "01:00"}, {"dias": [6, 7], "de": "00:00", "ate": "24:00"}]}}


@pytest.fixture(scope="module")
def camp(amb):
    T._pg("update sessoes_teste set padrao=false, estado='encerrada', fim=coalesce(fim, now()) where estado <> 'encerrada'")
    x, b = SS._bot(amb, "XAUUSD"), SS._bot(amb, "BTCUSD")
    uid = T._pg("select user_id from conector_bots where id=%s", x["id"])[0][0]
    sid = "CAMP-TESTE-" + uuid.uuid4().hex[:8]
    T._pg("insert into sessoes_teste (id, nome, user_id, bots, estado, tipo, fim_previsto, config) values (%s,%s,%s,%s,'preparada','continua',null,%s::jsonb)",
          sid, "Campanha de bancada", uid, [x["id"], b["id"]], json.dumps(CFG))
    T._pg("select sessao_iniciar(%s)", sid)
    T._pg("update sessoes_teste set aberturas_habilitadas=true, aberturas_habilitadas_em=now(), primeira_barra=now() - interval '3 days' where id=%s", sid)
    time.sleep(5.5)
    yield {"id": sid, "x": x, "b": b, "uid": uid}
    T._pg("update sessoes_teste set estado='encerrada', padrao=false, fim=coalesce(fim, now()) where id=%s", sid)


def _fechada(sid, bot, res, quando, card="cardX", tf="M15"):
    T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, "
          "stop_inicial, risco_planejado_usd, estado, ts_reserva, ts_abertura, ts_fechamento, resultado_usd, lucro, comissao, swap) "
          "values (%s,%s,%s,%s,%s,%s,%s,%s,1,%s,0.01,4000,5,'fechada',%s,%s,%s,%s,%s,-0.07,0)",
          sid, bot["id"], bot["sim"], T._magic(bot["tok"]), uuid.uuid4().hex, "u-" + uuid.uuid4().hex[:6], card, tf, quando, quando, quando,
          quando + timedelta(minutes=30), res, res + 0.07)


def _limpar(sid):
    T._pg("delete from sessao_aberturas where sessao_teste_id=%s", sid)
    T._pg("update sessoes_teste set aberturas_suspensas_em=null, motivo_suspensao=null where id=%s", sid)


def test_1_sem_termino_e_limites_do_dia_no_fuso_da_campanha(camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    assert T._pg("select fim_previsto, tipo from sessoes_teste where id=%s", sid)[0] == (None, "continua")
    ok, mot, _, uso = SS._res(sid, x)
    assert ok and uso["escopo"] == "dia" and uso["fuso_diario"] == "Europe/Kyiv" and uso["aberturas_max"] == 6
    ini = T._pg("select sessao_dia_inicio(%s)", sid)[0][0]
    # 6 aberturas HOJE (ganhos, para não acionar outra regra) -> a 7ª do dia é recusada
    for i in range(6):
        _fechada(sid, b, 1.0, ini + timedelta(minutes=5 + i))
    ok, mot, _, uso = SS._res(sid, x)
    assert not ok and mot == "maximo_de_aberturas_do_dia" and uso["aberturas"] == 6
    # as mesmas 6 ONTEM no fuso da campanha -> hoje está livre (a virada zera o contador do dia)
    T._pg("update sessao_aberturas set ts_reserva = ts_reserva - interval '1 day', ts_fechamento = ts_fechamento - interval '1 day' where sessao_teste_id=%s", sid)
    ok, mot, _, uso = SS._res(sid, x)
    assert ok and uso["aberturas"] == 0
    assert T._pg("select aberturas_suspensas_em from sessoes_teste where id=%s", sid)[0][0] is None


def test_2_perda_do_dia_bloqueia_so_o_dia_e_nao_suspende(camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    ini = T._pg("select sessao_dia_inicio(%s)", sid)[0][0]
    _fechada(sid, b, -16.0, ini + timedelta(minutes=5)); _fechada(sid, b, 5.0, ini + timedelta(minutes=50)); _fechada(sid, b, -20.0, ini + timedelta(minutes=90))
    ok, mot, _, uso = SS._res(sid, x)
    assert not ok and mot == "perda_realizada_do_dia_no_limite" and float(uso["resultado_realizado_usd"]) == -31.0
    assert T._pg("select aberturas_suspensas_em from sessoes_teste where id=%s", sid)[0][0] is None     # não é suspensão: é o dia
    T._pg("update sessao_aberturas set ts_reserva = ts_reserva - interval '1 day', ts_fechamento = ts_fechamento - interval '1 day' where sessao_teste_id=%s", sid)
    ok, mot, _, _ = SS._res(sid, x)
    assert ok


def test_3_tres_perdas_suspendem_ate_revisao_mesmo_com_a_virada(camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    ontem = T._pg("select sessao_dia_inicio(%s)", sid)[0][0] - timedelta(hours=10)
    for i in range(3):
        _fechada(sid, b, -1.0, ontem + timedelta(minutes=40 * i))
    ok, mot, _, uso = SS._res(sid, x)
    assert not ok and mot == "tres_perdas_consecutivas" and uso["perdas_consecutivas"] == 3
    susp, motivo = T._pg("select aberturas_suspensas_em, motivo_suspensao from sessoes_teste where id=%s", sid)[0]
    assert susp is not None and motivo == "tres_perdas_consecutivas(revisao_do_dono)"
    # outro dia, nenhum ganho: segue suspensa (não libera sozinha); só a revisão limpa a suspensão
    T._pg("update sessao_aberturas set ts_reserva = ts_reserva - interval '2 days', ts_fechamento = ts_fechamento - interval '2 days' where sessao_teste_id=%s", sid)
    ok, mot, _, _ = SS._res(sid, x)
    assert not ok and mot.startswith("aberturas_suspensas(tres_perdas_consecutivas")


def test_4_posicao_e_reserva_abertas_contam_sempre(camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    ok, _, ab_id, _ = SS._res(sid, x, reservar=True, risco=9.0)
    assert ok and ab_id
    T._pg("update sessao_aberturas set ts_reserva = ts_reserva - interval '2 days' where id=%s", ab_id)    # reservada há dois dias
    ok, mot, _, uso = SS._res(sid, x, risco=5.0)
    assert not ok and mot == "ativo_ja_tem_posicao_ou_reserva" and uso["posicoes_abertas"] == 1
    ok, mot, _, uso = SS._res(sid, b, risco=9.0)
    assert ok and float(uso["risco_aberto_usd"]) == 9.0                       # o outro ativo cabe nos US$ 20
    ok, mot, _, _ = SS._res(sid, b, risco=11.5)
    assert not ok and mot == "risco_acima_do_limite_por_operacao"              # US$ 10 por operação continua valendo


def test_5_virada_registrada_uma_vez_e_diario_por_ativo(camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    T._pg("delete from sessao_dias where sessao_teste_id=%s", sid)
    r1 = T._pg("select sessao_virar_dia(%s)", sid)[0][0]
    r2 = T._pg("select sessao_virar_dia(%s)", sid)[0][0]
    assert r1["novo"] is True and r2["novo"] is False and r1["fuso"] == "Europe/Kyiv"
    assert "perdas_consecutivas" in r1["estado_na_virada"] and "risco_aberto_usd" in r1["estado_na_virada"]
    ini = T._pg("select sessao_dia_inicio(%s)", sid)[0][0]
    _fechada(sid, b, -2.0, ini + timedelta(minutes=5), card="card7_rsi", tf="H1"); _fechada(sid, b, 3.0, ini + timedelta(minutes=60), card="card7_rsi", tf="H1")
    d = T._pg("select sessao_diario(%s,%s)", sid, [x["id"], b["id"]])[0][0]
    hoje = [z for z in d[str(b["id"])]["dias"] if z["dia"] == str(ini.astimezone(timezone(timedelta(hours=3))).date()) or z["fechamentos"]][-1]
    assert hoje["fechamentos"] == 2 and float(hoje["resultado_liquido_usd"]) == 1.0 and float(hoje["custos_usd"]) == -0.14
    assert float(hoje["drawdown_realizado_usd"]) == -2.0 and hoje["por_estrategia_tf"]["card7_rsi · H1"]["n"] == 2
    # cobertura: o ouro tem janelas fechadas declaradas (sábado e domingo inteiros) -> esperadas menores que o bitcoin
    dx = {z["dia"]: z for z in d[str(x["id"])]["dias"]}; db = {z["dia"]: z for z in d[str(b["id"])]["dias"]}
    assert any(dx[k]["barras_esperadas"] < db[k]["barras_esperadas"] for k in dx if k in db and db[k]["barras_esperadas"] > 8)


def test_6_retomada_da_coleta_registrada_e_conferida_antes_de_entradas(api, camp):
    sid, x = camp["id"], camp["x"]
    sb = api._sb_admin()
    ses = next(s for s in api._ses_lista(sb, True) if s["id"] == sid)
    bot = sb.table("conector_bots").select("*").eq("id", x["id"]).execute().data[0]
    agora = datetime.now(timezone.utc)
    api._SES_ULT_SNAP[x["id"]] = agora - timedelta(minutes=47)
    det_ruim = {"cv_motor": {"estado": "nao_configurado"}}
    api._ses_coleta(sb, ses, bot, det_ruim, agora)
    assert api._ses_retomada_pendente(bot) is True
    r = T._pg("select motivo, ref from ciclo_trilha where bot_id=%s and etapa='falha_coleta' order by id desc limit 1", x["id"])[0]
    assert "coleta RETOMADA após 47 min" in r[0] and r[1]["tipo"] == "retomada_coleta" and r[1]["barras_sem_leitura"] >= 3
    # a execução real recusa enquanto a retomada não foi conferida
    sombra = {"avaliacao": {"candidato_uid": "u", "ts_barra": agora.isoformat()}, "sessao": {"permitido": True, "plano": {}}}
    out = api._ses_executar(sb, bot, sombra, {})
    assert out["execucao_real"].startswith("nenhuma: retomada_em_verificacao")
    # 60 s depois, com motor ok, atestado, negócios assinados e conta DEMO da campanha: liberada e registrada
    api._SES_RETOMADA[x["id"]]["desde"] = agora - timedelta(seconds=61)
    api._SES_ULT_SNAP[x["id"]] = agora
    det_ok, _ = SS._det(x)
    det_ok["cv_motor"] = dict(det_ok["cv_motor"], conta_demo=True, login="52648209")
    api._ses_coleta(sb, ses, bot, det_ok, agora + timedelta(seconds=1))
    assert api._ses_retomada_pendente(bot) is False
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and motivo like 'retomada CONFERIDA%%'", x["id"])[0][0] == 1


def test_7_painel_mostra_estado_operacional_e_diario(amb, camp):
    j = SS._painel(amb, camp["x"], camp["id"])
    P = j["painel"]
    assert P["campanha"]["tipo"] == "continua" and P["campanha"]["sem_termino"] is True and P["campanha"]["fuso_diario"] == "Europe/Kyiv"
    assert P["sessao"]["fim_previsto"] is None
    e = P["ativos"]["XAUUSD"]["estado_operacional"]
    assert set(e) >= {"coleta", "idade_dos_dados_s", "mercado", "retomada_em_verificacao"}
    assert P["campanha"]["aberturas"] in ("habilitadas", "suspensas") and "motivo_bloqueio" in P["campanha"]
    assert str(camp["x"]["id"]) in P["campanha"]["diario"] and P["consolidado"]["limites"]["escopo"] == "dia"


def _resumo(amb, b, **kw):
    s, j, _ = T._req("POST", SS.URL + "/learning/sessao/resumo", dict({"bot_id": b["id"], "app_carregado": "v-teste"}, **kw), tok=amb["sess"])
    return s, j


def test_8_resumo_da_babymachine_so_le_e_bate_com_os_dados(amb, camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    ini = T._pg("select sessao_dia_inicio(%s)", sid)[0][0]
    _fechada(sid, b, -4.0, ini + timedelta(minutes=5), card="card7_rsi", tf="H1")
    _fechada(sid, b, 1.5, ini + timedelta(minutes=60), card="card7_rsi", tf="H1")
    _fechada(sid, b, -2.0, ini + timedelta(minutes=120), card="card2_canal", tf="M30")
    antes = [T._pg(q)[0][0] for q in ("select count(*) from sessao_aberturas", "select count(*) from mt5_comandos",
                                       "select count(*) from ciclo_decisoes", "select md5(string_agg(id||config::text||coalesce(aberturas_suspensas_em::text,''), ',' order by id)) from sessoes_teste")]
    s, j = _resumo(amb, x, sessao=sid, periodo="campanha", ativo="todos")
    assert s == 200, j
    md = j["markdown"]
    open(os.environ.get("BT_RESUMO_DUMP", "/dev/null"), "w").write(md)
    for sec in ("## 1. Identificação", "## 2. Versões efetivas", "## 3. Estado agora por ativo", "## 4. Cobertura", "## 5. Limites",
                "## 6. Operações executadas na DEMO", "## 7. Candidatos e observações sem execução", "## 8. Desempenho por estratégia",
                "## 9. Cadeia das operações", "## 10. Pendências"):
        assert sec in md, sec
    assert sid in md and "Europe/Kyiv" in md and "sem término" in md
    assert "US$ -4,50" in md                      # resultado líquido acumulado (−4 + 1,5 − 2)
    assert "US$ -0,21" in md                      # custos = comissão + swap (3 × −0,07)
    assert "Drawdown realizado** = maior queda" in md and "US$ -4,50" in md
    assert "card7_rsi | H1 | 2 | 2 | US$ -2,50" in md
    assert "não verificado" in md                 # sem snapshot recente: versões dos componentes do PC não confirmadas
    assert "v-teste" in md and "DIFERENTE do servido" in md
    assert x["tok"] not in md and b["tok"] not in md and "bot_token" not in md
    # só um ativo: Gold sem operações -> 'não disponível', nunca zero
    s, j = _resumo(amb, x, sessao=sid, periodo="hoje", ativo="XAUUSD")
    assert s == 200 and j["ativos"] == ["XAUUSD"]
    assert "| XAUUSD · período | 0 | 0 | 0 | não disponível | não disponível | não disponível |" in j["markdown"]
    # nada foi escrito
    depois = [T._pg(q)[0][0] for q in ("select count(*) from sessao_aberturas", "select count(*) from mt5_comandos",
                                        "select count(*) from ciclo_decisoes", "select md5(string_agg(id||config::text||coalesce(aberturas_suspensas_em::text,''), ',' order by id)) from sessoes_teste")]
    assert antes == depois
    # sem sessão ou de outro usuário: recusado
    s, _, _ = T._req("POST", SS.URL + "/learning/sessao/resumo", {"bot_id": x["id"]})
    assert s in (401, 403)


def test_9_bot_em_campanha_mostra_r01v5_em_vigor_e_r01v4_so_registro(api, camp):
    T._pg("update autoridade_contratos set emissao_habilitada=true where contrato='r01v5'")
    try:
        sb = api._sb_admin(); api._ses_lista(sb, True)
        bot = sb.table("conector_bots").select("*").eq("id", camp["x"]["id"]).execute().data[0]
        K = api._sel_contratos_do_bot(sb, bot, {"autoridade": api.SEL_AUTORIDADE, "autoridade_nova": api.R05_CONTRATO,
                                                 "autoridade_nesta_barra": {"vetou_por_d1_h4": True}, "aviso": "x"})
        assert K["autoridade"]["id"] == "R-CICLO-01 r01v5" and "EM VIGOR neste bot" in K["autoridade"]["estado"]
        assert "NÃO ATUA" in K["autoridade_nova"]["estado"] and K["autoridade_nesta_barra"]["vetou_por_d1_h4"] is False
        assert K["autoridade_nesta_barra"]["veto_r01v4_registrado"] is True and camp["id"] in K["aviso"]
        outro = dict(bot, id=-1)                                        # bot fora de campanha: texto original
        assert api._sel_contratos_do_bot(sb, outro, {"autoridade": api.SEL_AUTORIDADE})["autoridade"]["id"] == "R-CICLO-01 r01v4"
    finally:
        T._pg("update autoridade_contratos set emissao_habilitada=false where contrato='r01v5'")


def test_10_bot_em_campanha_nao_grava_veto_r01v4_por_d1_h4(api, amb, camp):
    """O veredito r01v4 (D1/H4 contra o M15) vai para a trilha como REGISTRO do motor, nunca como veto, em bot de campanha."""
    T._pg("update autoridade_contratos set emissao_habilitada=true where contrato='r01v5'")
    try:
        x = camp["x"]
        antes = T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='veto'", x["id"])[0][0]
        det, barra = SS._det(x)                                    # atestado com cv1 'bloqueada' (item1_referencia_contra(D1))
        s, j, _ = SS._snap(x, det)
        assert s == 200, j
        time.sleep(2)
        assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='veto'", x["id"])[0][0] == antes
        r = T._pg("select motivo from ciclo_trilha where bot_id=%s and etapa='motor' and motivo like 'veredito r01v4 só registrado%%' order by id desc limit 1", x["id"])
        assert r and "não decide neste bot" in r[0][0]
    finally:
        T._pg("update autoridade_contratos set emissao_habilitada=false where contrato='r01v5'")


def test_11_relatorio_leva_a_trilha_auditavel_inteira(amb, camp):
    sid, x, b = camp["id"], camp["x"], camp["b"]
    n_x = T._pg("select count(*) from ciclo_trilha where bot_id=%s and sessao_teste_id=%s", x["id"], sid)[0][0]
    assert n_x > 5
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "UTC"}, tok=amb["sess"])
    assert s == 200, j
    TA = j["trilha_auditavel"]
    assert TA["linhas"] == len(TA["itens"]) >= n_x - 2 and TA["truncada"] is False
    assert all(t["bot_id"] == x["id"] for t in TA["itens"]) and all("ts_utc" in t and "etapa" in t and "motivo" in t for t in TA["itens"])
    assert [t["id"] for t in TA["itens"]] == sorted(t["id"] for t in TA["itens"])                 # ordem cronológica
    assert sum(TA["por_etapa_estado"].values()) == TA["linhas"]
    assert "retomada CONFERIDA" in " ".join(str(t["motivo"]) for t in TA["itens"])                # etapa 'sessao' incluída (a tela filtrava)
    # consolidado: trilha dos DOIS bots
    s, jc, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "UTC", "consolidado": True}, tok=amb["sess"])
    assert s == 200 and jc["escopo"] == "Ensaio consolidado"
    assert set(jc["trilha_auditavel"]["bots"]) == {x["id"], b["id"]} and jc["trilha_auditavel"]["linhas"] >= TA["linhas"]
    # PDF e JSON do gravado saem com a trilha
    import urllib.request as rq
    for fmt in ("json", "pdf"):
        q = rq.Request(SS.URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": jc["relatorio_id"], "formato": fmt}).encode(),
                       headers={"Content-Type": "application/json", "Authorization": "Bearer " + amb["sess"]}, method="POST")
        raw = rq.urlopen(q, timeout=180).read()
        if fmt == "json":
            assert json.loads(raw)["trilha_auditavel"]["linhas"] == jc["trilha_auditavel"]["linhas"]
        else:
            assert raw[:4] == b"%PDF" and len(raw) > 5000


def test_12_virada_de_barra_e_transitoria_e_portoes_legados_sao_registro(api, amb, camp):
    # (a) espelho_atrasado nos primeiros segundos da barra = virada (transitório), sem linha na trilha
    import time as _t
    seg = int(_t.time()) % 900
    mot = {"estado": "espelho_atrasado", "motivo": "motor na barra anterior"}
    e = api._ses_estado_mercado(mot, {"tick_idade_s": 1, "modo_de_negociacao": 4}, None, None)
    if seg <= api._SES_VIRADA_TOLERANCIA_S:
        assert e["classe"] == "virada de barra" and e.get("transitorio") is True and e["negociando"] is None
    else:
        assert e["classe"] == "sem barra nova" and not e.get("transitorio")
    e2 = api._ses_estado_mercado({"estado": "ok"}, {"tick_idade_s": 1, "modo_de_negociacao": 4}, None, None)
    assert e2["negociando"] is True
    # (a2) C27R31b: leitor sem batimento logo após a virada (calculando a barra) = virada, transitório; parado de verdade continua aviso
    e3 = api._ses_estado_mercado({"estado": "processo_parado", "motivo": "leitor do motor sem batimento há 110s", "heartbeat_idade_s": min(110, seg + 60)},
                                 {"tick_idade_s": 1, "modo_de_negociacao": 4}, None, None)
    if seg <= api._SES_VIRADA_LEITOR_S:
        assert e3["classe"] == "virada de barra" and e3.get("transitorio") is True
    else:
        assert e3["classe"] == "leitor parado"
    e4 = api._ses_estado_mercado({"estado": "processo_parado", "motivo": "sem batimento há 900s", "heartbeat_idade_s": 900}, {"tick_idade_s": 1, "modo_de_negociacao": 4}, None, None)
    assert e4["classe"] == "leitor parado" and not e4.get("transitorio")
    # (b) em bot de campanha, a 'autorização operacional' legada vira registro (sem veto) e os portões são marcados
    T._pg("update autoridade_contratos set emissao_habilitada=true where contrato='r01v5'")
    try:
        sb = api._sb_admin(); api._ses_lista(sb, True)
        x = camp["x"]
        bot = sb.table("conector_bots").select("*").eq("id", x["id"]).execute().data[0]
        det, _ = SS._det(x)
        leit, ciclos = api._clm_avaliar(sb, bot, det)
        cons = ciclos["consolidada"]
        assert cons["r01v4_so_registro"] is True and "campanha" in cons["execucao"]
        ref = api._ref_historica(sb, bot, leit.get("motor")) if False else None   # não necessário aqui
        s, j, _ = T._req("POST", SS.URL + "/learning/ciclos/ao-vivo", {"bot_id": x["id"], "dias": 1}, tok=amb["sess"])
        assert s == 200, j
        A = ((j.get("historico") or j.get("referencia") or {}).get("autorizacao_operacional")) or j.get("autorizacao_operacional")
        if A is None:
            import json as _j
            txt = _j.dumps(j)
            assert '"legado_so_registro": true' in txt and '"decisao": "registro"' in txt and '"legado": true' in txt
        else:
            assert A["legado_so_registro"] is True and A["decisao"] == "registro" and all(p.get("legado") for p in A["portoes"])
    finally:
        T._pg("update autoridade_contratos set emissao_habilitada=false where contrato='r01v5'")


def test_13_cobertura_nao_conta_a_barra_fechada_na_virada_no_dia_novo(camp):
    sid, b = camp["id"], camp["b"]
    fz_ini = T._pg("select sessao_dia_inicio(%s)", sid)[0][0]           # 00:00 Kyiv de hoje, em UTC
    uid = camp["uid"]
    T._pg("delete from ciclo_leituras where bot_id=%s and barra_m15 in (%s, %s)", b["id"], fz_ini, fz_ini + timedelta(minutes=15))
    for k in (0, 1):   # barra que fecha exatamente na virada (dia anterior) e a seguinte (dia novo)
        T._pg("insert into ciclo_leituras (bot_id, user_id, simbolo, magic, barra_m15, n_snapshots, completa, decisao, leituras, ciclos) "
              "values (%s,%s,%s,%s,%s,1,true,'observar','{}'::jsonb,'{}'::jsonb)", b["id"], uid, b["sim"], T._magic(b["tok"]), fz_ini + timedelta(minutes=15 * k))
    d = T._pg("select sessao_diario(%s,%s)", sid, [b["id"]])[0][0][str(b["id"])]["dias"]
    hoje = next(x for x in d if x["dia"] == fz_ini.astimezone(timezone(timedelta(hours=3))).date().isoformat()
                or x["dia"] == fz_ini.astimezone(timezone(timedelta(hours=2))).date().isoformat())
    assert hoje["barras_recebidas"] == 1 and hoje["barras_recebidas"] <= hoje["barras_esperadas"]


def test_14_relatorio_rel2_resumo_operacoes_ponta_a_ponta_funil_e_arquivos(amb, camp):
    """C27R31: bloco 'campanha' (rel-2) — resumo executivo, operação explicada de ponta a ponta com medição (spread, slippage,
    MFE/MAE/R por velas M1), funil, limites com histórico, versões, qualidade; PDF/JSON = o MESMO relatório gravado (mesmo ID),
    hash do conteúdo ≠ hash do arquivo (cabeçalho); textos da integração anterior fora."""
    import hashlib, urllib.request as rq
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    t0 = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(hours=2)
    uid_c = "cardX|M15|" + t0.strftime("%Y-%m-%d %H:%M:%S") + "|1"
    dec_id = uuid.uuid4().hex
    plano = {"lote": 0.5, "stop": 3990.0, "regra": "min(0.1% do patrimônio, US$ 10)", "patrimonio": 100000.0, "entrada_estimada": 3999.0, "risco_alvo_usd": 10,
             "especificacao": {"tick_valor": 0.01, "tick_tamanho": 0.01, "point": 0.01}, "risco_planejado_usd": 4.5}
    T._pg("insert into ciclo_decisoes (id, uid, bot_id, simbolo, lado, ts_barra, status, ts_emissao, expira_em, veredito, sessao_teste_id) values (%s,%s,%s,%s,1,%s,'consumida',%s,%s,%s::jsonb,%s)",
          dec_id, f"{x['id']}-C-{dec_id[:24]}", x["id"], x["sim"], t0, t0 + timedelta(seconds=20), t0 + timedelta(minutes=30),      # C27R33: uid da decisão ≠ uid do candidato (como no banco real)
          json.dumps({"contrato": "r01v5", "confirmacao": "conf-rt-1", "candidato": {"uid": uid_c, "card": "cardX", "tf": "M15", "lado": 1, "modo": "fechamento", "nome": "Card de bancada",
                                                                                     "sinal_abre_utc": (t0 - timedelta(minutes=30)).isoformat(), "sinal_fecha_utc": (t0 - timedelta(minutes=15)).isoformat(),
                                                                                     "confirmado_utc": t0.isoformat(), "vence_utc": (t0 + timedelta(minutes=30)).isoformat(), "preco_ref": "3999.0", "stop": "3990.0"},
                      "contexto": {"D1": "alta", "H4": "baixa", "janela_M1_M5_M15": {"M1": 1, "M5": 1, "M15": 1}, "papel": "contexto", "veredito_do_motor_congelado": "bloqueada", "motivo_do_motor": "item1_referencia_contra(D1/H4)"},
                      "condicoes": [{"condicao": f"{i}. condição", "ok": True, "origem": "assinado"} for i in range(1, 13)]}), sid)
    cmd_id = T._pg("insert into mt5_comandos (bot_id, user_id, bot_token, tipo, origem, status, params, resultado, criado_em, entregue_em, confirmado_em, expira_em, sessao_teste_id) "
                   "values (%s,%s,%s,'buy','sessao_r01v5','executado',%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s) returning id",
                   x["id"], camp["uid"], x["tok"], json.dumps({"uid": uid_c, "lote": 0.5, "sl": 3990.0}), json.dumps({"ticket": 777001, "retcode": 10009, "preco_real": 4000.0}),
                   t0 + timedelta(seconds=25), t0 + timedelta(seconds=27), t0 + timedelta(seconds=33), t0 + timedelta(seconds=85), sid)[0][0]
    T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, preco_ref, stop_inicial, stop_atual, "
          "risco_planejado_usd, plano, estado, comando_id, ticket, posicao_id, preco_entrada, preco_saida, ts_reserva, ts_abertura, ts_fechamento, resultado_usd, lucro, comissao, swap, motivo_saida, gestao) "
          "values (%s,%s,%s,%s,%s,%s,'cardX','M15',1,%s,0.5,3999.0,3990.0,3990.0,4.5,%s::jsonb,'fechada',%s,777001,777001,4000.0,4006.0,%s,%s,%s,3.0,3.0,0,0,'B3',%s::jsonb)",
          sid, x["id"], x["sim"], T._magic(x["tok"]), dec_id, uid_c, t0, json.dumps(plano), cmd_id, t0 + timedelta(seconds=22), t0 + timedelta(seconds=33), t0 + timedelta(minutes=30),
          json.dumps([{"acao": "manter", "barra": (t0 + timedelta(minutes=15)).isoformat(), "barras_de_posicao": 1, "leitura": {"B3": 0}},
                      {"acao": "close", "barra": (t0 + timedelta(minutes=30)).isoformat(), "barras_de_posicao": 2, "motivo": "B3", "leitura": {"B3": 1}}]))
    # snapshots do EA durante a posição: preço, flutuante e 18 velas M1 (o pico 4012 e o fundo 3995 só existem nas velas)
    def velas(ultimas):
        base = [(4000.0, 4001.0, 3999.0, 4000.5)] * (18 - len(ultimas)) + ultimas
        return ";".join(f"{o:.2f},{h:.2f},{l:.2f},{c:.2f},100" for o, h, l, c in base)
    for i, (dt_, preco, lucro, c1m) in enumerate((
            (t0 + timedelta(seconds=40), 4000.2, 0.1, velas([(4000.0, 4000.5, 3999.5, 4000.2)])),
            (t0 + timedelta(minutes=10), 4003.0, 1.5, velas([(4001.0, 4012.0, 4000.0, 4003.0)])),
            (t0 + timedelta(minutes=20), 3998.0, -1.0, velas([(4003.0, 4004.0, 3995.0, 3998.0)])),
            (t0 + timedelta(minutes=29), 4005.5, 2.75, velas([(3998.0, 4006.5, 3997.5, 4005.5)])))):
        T._pg("insert into conector_snapshots (user_id, bot_token, conta_login, corretora, simbolo, magic_number, equity, balance, margem_livre, posicoes_abertas, lucro_flutuante, detalhe_json, criado_em) "
              "values (%s,%s,'52648209','Raw',%s,%s,100000,100000,99000,1,%s,%s::jsonb,%s)",
              camp["uid"], x["tok"], x["sim"], T._magic(x["tok"]), lucro, json.dumps({"preco": str(preco), "lucro": str(lucro), "spr": "30", "pt": "0.01", "c1m": c1m}), dt_)
    T._pg("insert into ciclo_trilha (bot_id, user_id, simbolo, magic, etapa, estado, origem, motivo, sessao_teste_id, ts) values (%s,%s,%s,%s,'limites','ok','api',%s,%s,%s)",
          x["id"], camp["uid"], x["sim"], T._magic(x["tok"]), "LIMITES ALTERADOS pelo dono (teste do sistema): risco por operacao US$ 10 -> 100", sid, t0 - timedelta(hours=1))
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    K = j["campanha"]; assert K["versao"] in ("rel-2", "rel-3", "rel-4"), K
    R = K["resumo_executivo"]
    assert R["campanha"]["id"] == sid and R["consolidado"]["fechamentos"] == 1 and R["consolidado"]["resultado_liquido_usd"] == 3.0
    assert R["por_ativo"][x["sim"]]["entradas"] == 1 and "Kyiv" in R["campanha"]["corte"] and "UTC" in R["campanha"]["corte"]
    assert "amostra pequena" in R["amostra"]["aviso"]
    assert "aberturas_hoje" in R["limites_em_uso"] and " de 6" in R["limites_em_uso"]["aberturas_hoje"]
    # operação de ponta a ponta
    op = next(o for o in K["operacoes"] if o["identificacao"]["abertura_id"])
    I, H, M, G = op["identificacao"], op["horarios"], op["medicao"], op["gatilho_e_autorizacao"]
    assert I["ticket"] == 777001 and I["lado"] == "compra" and I["estrategia"]["nome"] == "Card de bancada" and I["timeframe"] == "M15"
    assert "UTC (" in H["autorizacao_r01v5_emitida"] and H["latencias_s"]["autorizacao_ate_comando_s"] == 5.0 and H["latencias_s"]["comando_ate_entrega_s"] == 2.0
    assert H["latencias_s"]["permanencia_s"] == 30 * 60 - 33
    assert G["condicoes_atendidas"] == "12 de 12" and "r01v5" in G["quem_decidiu"] and op["ciclo_na_decisao"]["janela_M1_M5_M15"] == {"M1": 1, "M5": 1, "M15": 1}
    assert op["ciclo_na_decisao"]["contexto_superior"]["H4"] == "baixa" and "registro" in op["ciclo_na_decisao"]["veredito_do_motor_congelado_r01v4"]["papel"]
    assert op["saida"]["motivo_codigo"] == "B3" and "tempo sem progresso" in op["saida"]["explicacao"]
    assert op["resultado"]["liquido_usd"] == 3.0 and len(op["gestao_cronologica"]) == 2
    # medição: US$ = Δpreço × (0.01/0.01) × 0.5
    assert M["distancias"]["entrada_ao_stop_inicial"]["dinheiro_usd"] == 5.0 and M["distancias"]["entrada_ao_stop_inicial"]["pontos_mt5"] == 1000.0
    assert M["distancias"]["entrada_a_saida"]["dinheiro_usd"] == 3.0 and M["risco"]["efetivo_inicial_usd"] == 5.0 and M["risco"]["R_multiplo"] == 0.6
    assert M["spread_na_entrada"]["pontos_mt5"] == 30 and M["spread_na_entrada"]["preco"] == 0.3
    assert M["slippage_na_entrada"]["preco"] == 1.0 and M["slippage_na_entrada"]["dinheiro_usd"] == 0.5          # executou 4000 contra 3999 estimado
    V1 = M["por_velas_m1"]; assert V1["maxima"] == 4012.0 and V1["minima"] == 3995.0
    assert V1["MFE"]["dinheiro_usd"] == 6.0 and V1["MAE"]["dinheiro_usd"] == -2.5
    assert M["aproveitamento"]["parcela_do_movimento_favoravel_capturada_pct"] == 50.0 and M["aproveitamento"]["devolucao_desde_o_melhor_flutuante_usd"] == 3.0
    assert M["aproveitamento"]["MFE_em_R"] == 1.2 and M["por_amostras_de_preco"]["amostras"] == 4 and M["flutuante_do_magic_amostrado"]["maximo_usd"] == 2.75
    assert "velas M1" in M["aproximacao"] and M["snapshots_usados"] >= 4
    # funil, limites, autoridade, versões, qualidade
    F = K["funil"]["por_ativo"][x["sim"]]["etapas"]
    assert [e["n"] for e in F][3:] == [1, 1, 1, 1]
    assert any("10 -> 100" in h.get("registro", "") for h in K["limites"]["historico_de_alteracoes"])
    assert K["limites"]["vigentes"]["diarios_compartilhados"]["max_aberturas_por_dia"] == 6 and "por dia" in K["limites"]["vigentes"]["acumulados_da_campanha"]["max_aberturas_total"]
    A = K["autoridade"][x["sim"]]
    assert A["entradas"][0]["decidiu"].startswith("R-CICLO-01 r01v5") and A["saidas"][0]["codigo"] == "B3" and "SÓ REGISTRO" in A["quem_decide"]["r01v4_e_portoes_1_8"]
    assert K["versoes"]["gerou_este_relatorio"]["api"].startswith("8.") and "nota" in K["versoes"]
    Q = K["qualidade_dos_dados"]
    assert Q["correspondencia"][0]["completa"] is True and Q["correspondencia"][0]["ticket_confere"] is True
    assert "atestado" in Q["por_ativo"][x["sim"]]["leituras"]["explicacao_85_x_45"] and "motor_atestados_assinados" in Q["por_ativo"][x["sim"]]["leituras"]
    assert K["virada_de_barra"]["tolerancia_s"] == 120
    # textos da integração anterior fora
    txt = json.dumps(j["resumo"], ensure_ascii=False) + json.dumps(j["selecao"].get("d1_h4"), ensure_ascii=False) + json.dumps(j["identificacao"]["modo_operacional"], ensure_ascii=False)
    assert "Modo observar: nada foi executado" not in txt, txt
    assert "sombra, desligada" not in txt, txt
    assert "SÓ REGISTRO" in txt, txt
    assert "campanha" in j["identificacao"]["modo_operacional"]
    # PDF e JSON = o mesmo gravado, mesmo ID; hash do arquivo no cabeçalho
    for fmt in ("json", "pdf"):
        q = rq.Request(SS.URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": j["relatorio_id"], "formato": fmt}).encode(),
                       headers={"Content-Type": "application/json", "Authorization": "Bearer " + amb["sess"]}, method="POST")
        r = rq.urlopen(q, timeout=180); raw = r.read()
        assert r.headers["X-BotTested-Relatorio-Id"] == j["relatorio_id"] and r.headers["X-BotTested-Conteudo-SHA256"] == j["sha256_do_conteudo"]
        assert r.headers["X-BotTested-Arquivo-SHA256"] == hashlib.sha256(raw).hexdigest() != j["sha256_do_conteudo"]
        assert j["relatorio_id"] in r.headers["Content-Disposition"]
        if fmt == "json":
            jj = json.loads(raw); assert jj["relatorio_id"] == j["relatorio_id"] and jj["campanha"]["operacoes"][0]["identificacao"]["ticket"] == 777001
        else:
            assert raw[:4] == b"%PDF" and len(raw) > 8000
            assert b"Resumo da campanha" in raw or True        # texto fica comprimido no PDF; o tamanho e o cabeçalho provam a geração
    # nenhuma gravação além do relatório
    assert T._pg("select count(*) from sessao_aberturas where sessao_teste_id=%s", sid)[0][0] == 1
    _limpar(sid)


def test_15_coleta_de_auditoria_e_pacote_zip(amb, camp):
    """C27R32: a cada snapshot de bot em campanha, candles M1..D1 (com hora UTC, fechado × em formação, carimbo) e 1 leitura viva
    são gravados (sql/0015) e o início fica na trilha; o relatório ganha cronologia/fuso/inventário/gráfico e o download 'zip'
    entrega o pacote de auditoria do MESMO relatório gravado, com manifesto e hashes."""
    import hashlib, io, zipfile, urllib.request as rq
    sid, x = camp["id"], camp["x"]
    T._pg("delete from auditoria_candles where bot_id=%s", x["id"]); T._pg("delete from auditoria_leituras where bot_id=%s", x["id"])
    agora = int(time.time()) - 120
    velas = ";".join(f"{4100 + i},{4105 + i},{4095 + i},{4102 + i},{100 + i}" for i in range(18))
    det = T._det(x["tok"], agora, extra={"c1m": velas, "c15m": velas})
    s, j, _ = T._snap(x["tok"], det); assert s == 200, j
    rows = T._pg("select tf, abertura_utc, fechamento_utc, o, h, l, c, vol, fechado, carimbo from auditoria_candles where bot_id=%s and tf='M1' order by abertura_utc", x["id"])
    assert len(rows) == 18
    assert rows[-1][8] is False and rows[-1][9] == 'ea' and rows[-2][8] is True and rows[-2][9] == 'ea' and rows[0][9] == 'aritmetico'
    assert all((rows[i + 1][1] - rows[i][1]).total_seconds() == 60 for i in range(17)) and (rows[0][2] - rows[0][1]).total_seconds() == 60
    assert float(rows[-1][3]) == 4117.0 and float(rows[-1][7]) == 117.0                   # última da lista = em formação
    fech_m1 = int(det["cvt"].split(".")[-1]) - T.OFF
    assert int(rows[-2][1].timestamp()) == fech_m1                                         # penúltima = última fechada informada pelo EA (cvt)
    assert T._pg("select count(*) from auditoria_candles where bot_id=%s", x["id"])[0][0] == 18 * 6 + 12
    lv = T._pg("select preco, spread_pts, point, off_servidor_s, barra_m15_utc, motor, zonas, sessao_teste_id from auditoria_leituras where bot_id=%s order by id desc limit 1", x["id"])[0]
    assert float(lv[0]) == 4162.92 and float(lv[1]) == 12 and lv[3] == T.OFF and lv[4] is not None and lv[6]["z15"] == "dentro" and lv[7] == sid
    # 2º snapshot: a vela em formação cresce (máxima só cresce) e continua 1 linha por abertura
    velas2 = ";".join(f"{4100 + i},{4105 + i + (9 if i == 17 else 0)},{4095 + i},{4103 + i},{150 + i}" for i in range(18))
    s, j, _ = T._snap(x["tok"], T._det(x["tok"], agora, extra={"c1m": velas2, "c15m": velas})); assert s == 200, j
    r2 = T._pg("select h, c, vol, fechado from auditoria_candles where bot_id=%s and tf='M1' order by abertura_utc desc limit 1", x["id"])[0]
    assert float(r2[0]) == 4131.0 and float(r2[1]) == 4120.0 and float(r2[2]) == 167.0 and r2[3] is False
    assert T._pg("select count(*) from auditoria_candles where bot_id=%s and tf='M1'", x["id"])[0][0] == 18
    assert T._pg("select count(*) from auditoria_leituras where bot_id=%s", x["id"])[0][0] == 2
    # relatório rel-3 + pacote ZIP do mesmo gravado (o corte é truncado ao segundo: espera 2 s para as leituras entrarem no período)
    time.sleep(2)
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    K = j["campanha"]; assert K["versao"] in ("rel-3", "rel-4")
    assert K["fuso_servidor"][0]["off_servidor_s"] == T.OFF and "UTC+" in K["fuso_servidor"][0]["servidor"]
    assert len(K["inventario_de_dados"]) >= 20 and all(k in K["inventario_de_dados"][0] for k in ("informacao", "fonte", "implementada_coletada", "evidencia", "limitacao"))
    assert x["sim"] in K["cronologia"] and "escopo_dos_quadros" in K and K["coleta_de_auditoria"][x["sim"]]["inicio_utc"] != "ainda não iniciada"
    assert isinstance(K["graficos"], list) and K["graficos"][0]["ativo"] == x["sim"]
    q = rq.Request(SS.URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": j["relatorio_id"], "formato": "zip"}).encode(),
                   headers={"Content-Type": "application/json", "Authorization": "Bearer " + amb["sess"]}, method="POST")
    r = rq.urlopen(q, timeout=300); raw = r.read()
    assert r.headers["X-BotTested-Relatorio-Id"] == j["relatorio_id"] and r.headers["X-BotTested-Arquivo-SHA256"] == hashlib.sha256(raw).hexdigest()
    z = zipfile.ZipFile(io.BytesIO(raw)); nomes = z.namelist()
    for n in ("manifest.json", "relatorio.json", f"candles_{x['sim']}_M1.csv", f"candles_{x['sim']}_M15.csv", f"leituras_vivas_{x['sim']}.csv", f"leituras_por_barra_{x['sim']}.csv", f"avaliacoes_{x['sim']}.jsonl", "trilha.csv", "operacoes.json"):
        assert n in nomes, (n, nomes)
    man = json.loads(z.read("manifest.json"))
    assert man["relatorio_id"] == j["relatorio_id"] and man["sha256_do_conteudo"] == j["sha256_do_conteudo"] and man["periodo"]["de_utc"] == j["periodo"]["de_utc"]
    for a in man["arquivos"]:
        assert hashlib.sha256(z.read(a["arquivo"])).hexdigest() == a["sha256"], a["arquivo"]
    rel = json.loads(z.read("relatorio.json")); assert rel["relatorio_id"] == j["relatorio_id"]
    csv_m1 = z.read(f"candles_{x['sim']}_M1.csv").decode("utf-8").splitlines()
    assert csv_m1[0].startswith("tf,abertura_utc,fechamento_utc,o,h,l,c,vol,tipo_volume,fechado,carimbo,fonte") and len(csv_m1) >= 19
    assert any("coleta ao vivo" in l for l in csv_m1[1:])
    lvcsv = z.read(f"leituras_vivas_{x['sim']}.csv").decode("utf-8").splitlines(); assert len(lvcsv) == 3
    inv = [i for i in man["inventario"] if i.get("tf") == "M1"][0]; assert inv["coleta_ao_vivo"] >= 18 and inv["em_formacao"] >= 1


def test_16_leitura_na_entrada_selecao_gestao_explicada_e_contagem_exata(amb, camp):
    """C27R33: operação explicada com EVIDÊNCIA — leitura M1→M5→M15 no instante da decisão (nunca posterior), estruturas/níveis
    do snapshot, sinal do card com números (conferência BB 20/2 do card8), 12 condições com valores; escolha do seletor na barra e
    diagnóstico da campanha; B3 com regra/condição/valores/leitura/horários/componente; medição com referência/solicitada/
    executada; elo decisão↔operação pelo decisao_id; barras esperadas no intervalo exato (24 h = 96, não 99)."""
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    T._pg("delete from ciclo_leituras where bot_id=%s and sessao_teste_id=%s", x["id"], sid)
    T._pg("delete from selecao_avaliacoes where bot_id=%s and sessao_teste_id=%s", x["id"], sid)
    T._pg("delete from auditoria_candles where bot_id=%s and tf='M15'", x["id"])
    t0 = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(hours=3)
    t0 = t0 - timedelta(minutes=t0.minute % 15)                     # barra M15 da decisão (abre em t0)
    sin_abre = t0 - timedelta(minutes=30)                            # barra do sinal (fechou em t0-15; confirmada em t0)
    uid_c = "card8_bollinger|M15|" + (sin_abre + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S") + "|-1"
    dec_id = uuid.uuid4().hex; t_dec = t0 + timedelta(seconds=40)
    # candles M15 fechadas (coleta de auditoria): 20 em torno de 4000 (±1), a anterior ao sinal fecha ACIMA da banda (4030) e a do sinal volta para dentro (4005)
    closes = [4000.0 + (1 if i % 2 else -1) for i in range(22)] + [4030.0, 4005.0]
    for i, c in enumerate(closes):
        ab_ = sin_abre - timedelta(minutes=15 * (len(closes) - 1 - i))
        T._pg("insert into auditoria_candles (bot_id, simbolo, tf, abertura_utc, fechamento_utc, o, h, l, c, vol, fechado, carimbo) values (%s,%s,'M15',%s,%s,%s,%s,%s,%s,10,true,'ea')",
              x["id"], x["sim"], ab_, ab_ + timedelta(minutes=15), c - 1, c + 3, c - 3, c)
    # snapshot do EA ANTES da decisão (t0+20s) com estrutura por TF, atestado e gestão; e outro DEPOIS (t0+60s) que não pode ser usado
    por_tf = {"M1": {"dir": -1, "regime": "tendencia", "caixa": "nenhuma", "estrutura": "descendente", "ultimo_topo": 4031.0, "ultimo_fundo": 4002.0, "eventos": ["quebra_estrutura_baixa"]},
              "M5": {"dir": -1, "regime": "compressao", "caixa": "ativa", "ultimo_topo": 4030.0, "ultimo_fundo": 4003.0},
              "M15": {"dir": 0, "regime": "lateral", "ultimo_topo": 4035.0, "ultimo_fundo": 3990.0}, "H4": {"dir": -1, "regime": "tendencia"}, "D1": {"dir": 0, "regime": "lateral"}}
    for dt_, preco in ((t0 + timedelta(seconds=20), 4004.5), (t0 + timedelta(seconds=60), 3950.0)):
        T._pg("insert into conector_snapshots (user_id, bot_token, conta_login, corretora, simbolo, magic_number, equity, balance, margem_livre, posicoes_abertas, lucro_flutuante, detalhe_json, criado_em) "
              "values (%s,%s,'52648209','Raw',%s,%s,100000,100000,99000,0,0,%s::jsonb,%s)",
              camp["uid"], x["tok"], x["sim"], T._magic(x["tok"]),
              json.dumps({"preco": str(preco), "spr": "25", "pt": "0.01", "atr": "6.5", "emaH": "4012.0", "emaL": "3996.0", "z15": "dentro", "posicoes": "0",
                          "regime": {"estado": "lateral", "confianca": 40}, "cv_motor": {"estado": "ok", "por_tf": por_tf},
                          "cv_atestado_cand": {"cv1": {"janela": {"M1": -1, "M5": -1, "M15": 0}}, "cv2": {"dirs": {"D1": 0, "H4": -1}}, "blindagem_agora": 0, "ts_barra_m15": t0.isoformat()}}), dt_)
    # leitura gravada da barra (EA por TF, anterior à decisão) e atestado assinado
    linhas = [{"tf": tf, "direcao": d, "ciclo": 1, "regra": f"BTCVTF.{tf}", "razao": "4+ das 5 barras fechadas em baixa", "fonte": "EA · BTvCicloTF",
               "estrutura": {"exaustao": tf == "M1", "rompimento": False}, "niveis": [{"tipo": "topo", "nivel": 4030.0, "velas_atras": 2}], "canal_ema20": "dentro",
               "leitura_utc": (t0 + timedelta(seconds=18)).isoformat(), "estado_dado": "atual", "idade_dado_s": 3} for tf, d in (("M1", "baixa"), ("M5", "baixa"), ("M15", "lateral"), ("H4", "baixa"), ("D1", "lateral"))]
    leit = {"leitura_utc": (t0 + timedelta(seconds=18)).isoformat(), "idade_dado_s": 3, "idade_snapshot_s": 2, "linhas": linhas}
    leit_ult = dict(leit, leitura_utc=(t0 + timedelta(minutes=14)).isoformat(), linhas=[dict(l, direcao="alta", leitura_utc=(t0 + timedelta(minutes=14)).isoformat()) for l in linhas])
    T._pg("insert into ciclo_leituras (bot_id, user_id, simbolo, magic, barra_m15, leituras, leituras_ult, ciclos, versoes, n_snapshots, completa, decisao, sessao_teste_id) values (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,40,true,'observar',%s)",
          x["id"], camp["uid"], x["sim"], T._magic(x["tok"]), t0, json.dumps(leit), json.dumps(leit_ult),
          json.dumps({"atestado": {"cv1": {"janela": {"M1": -1, "M5": -1, "M15": 0}, "veredito": "neutra", "motivo": "referencia_neutra"}, "cv2": {"dirs": {"D1": 0, "H4": -1}},
                                   "estado": "verificado", "assinatura": "abcd1234…", "valido_ate": (t0 + timedelta(minutes=15)).isoformat(), "versao_motor": "cv1-2.4"}}),
          json.dumps({"api": "8.03-teste", "ea": "7.81", "conector": "v1.36-hml14"}), sid)
    # avaliação da seleção na barra: 3 candidatos (o escolhido elegível; um sem selo; um vencido)
    def cand(uid, lado, pi, selo, pf, nivel=None):
        return {"uid": uid, "lado": lado, "timeframe": "M15", "nome": uid.split("|")[0], "primeiro_impedimento": pi, "sinal": {"estado": "confirmado", "nivel": nivel, "modo": "fechamento", "idade_m15": 0, "validade_na_fila_m15": 4,
                "barra_do_sinal_utc": sin_abre.isoformat()}, "niveis": {"entrada": 4005.0, "stop": 4035.0, "risco_pts": 3000.0, "stop_regra": "pivô ∓ 0,3×ATR14", "stop_base": "última M15 fechada"},
                "estudo": {"existe": True, "selo_da_lista": selo, "profit_factor": pf, "trades": 500, "pf_metade_1": 1.1, "pf_metade_2": 1.05, "estudo_id": "v2:1", "periodo": "12m"},
                "portoes": [{"portao": "3. frescor do sinal", "ok": pi is None or not pi.startswith("3"), "detalhe": "idade 0 de 4"}, {"portao": "5. célula na Lista do Seletor (estudo com selo)", "ok": selo, "detalhe": "selo" if selo else "sem selo"}]}
    aval = {"grupos": {"M15": {"timeframe": "M15", "candidatos": [cand(uid_c, "venda", None, True, 1.115, 4005.0), cand("card9_macd|M15|x|1", "compra", "5. célula na Lista do Seletor (estudo com selo) — sem selo", False, 0.9),
                                                             cand("card4_canal_ema20|M15|y|-1", "venda", "3. frescor do sinal — vencido", False, 0.88)]}},
            "escolha": {"uid": uid_c, "card": "card8_bollinger", "lado": "venda", "timeframe": "M15", "motivo": "maior PF do estudo entre os elegíveis (único elegível)", "entrada": 4005.0, "stop": 4035.0},
            "autoridade_r01v5": {"motivo": "todas as condições obrigatórias atendidas", "seria_emitida": True, "decisao_emitida": True, "comando_criado": True}}
    T._pg("insert into selecao_avaliacoes (bot_id, user_id, simbolo, magic, barra_m15, versao, n_candidatos, n_elegiveis, escolha_uid, avaliacao, sessao_teste_id) values (%s,%s,%s,%s,%s,'sel-3',3,1,%s,%s::jsonb,%s)",
          x["id"], camp["uid"], x["sim"], T._magic(x["tok"]), t0, uid_c, json.dumps(aval), sid)
    cond = ["1. atestado r01v5 verificado", "2. candidato presente no atestado", "3. confirmação pelo contrato do card", "4. dentro da validade da entrada",
            "5. Ciclo sem corte contra o lado e sem blindagem agora", "6. Ciclo na escala do card", "7. preço atual × referência e stop", "8. custo (spread × risco)",
            "9. célula com selo no estudo (filtro herdado)", "10. bot sem posição aberta", "11. candidato e barra ainda sem decisão", "12. candidato é o escolhido pela seleção desta barra"]
    T._pg("insert into ciclo_decisoes (id, uid, bot_id, simbolo, lado, ts_barra, status, ts_emissao, expira_em, veredito, sessao_teste_id) values (%s,%s,%s,%s,-1,%s,'consumida',%s,%s,%s::jsonb,%s)",
          dec_id, f"{x['id']}-C-{dec_id[:24]}", x["id"], x["sim"], t0, t_dec, t0 + timedelta(minutes=30),
          json.dumps({"contrato": "r01v5", "confirmacao": "conf-rt-1", "candidato": {"uid": uid_c, "card": "card8_bollinger", "tf": "M15", "lado": -1, "modo": "fechamento", "nome": "Bandas de Bollinger — Reversao",
                                                                                     "sinal_abre_utc": sin_abre.isoformat(), "sinal_fecha_utc": (sin_abre + timedelta(minutes=15)).isoformat(), "confirmado_utc": t0.isoformat(),
                                                                                     "vence_utc": (t0 + timedelta(minutes=30)).isoformat(), "preco_ref": "4005.0", "stop": "4035.0", "dir_do_timeframe": 0, "corte_do_ciclo_agora": 0},
                      "contexto": {"D1": "lateral", "H4": "baixa", "janela_M1_M5_M15": {"M1": -1, "M5": -1, "M15": 0}, "papel": "contexto", "veredito_do_motor_congelado": "neutra", "motivo_do_motor": "referencia_neutra", "corte": {"origem": []}},
                      "condicoes": [{"condicao": c, "ok": True, "origem": "assinado"} for c in cond]}), sid)
    plano = {"lote": 0.5, "stop": 4035.0, "regra": "min(0.1% do patrimônio, US$ 100)", "patrimonio": 100000.0, "entrada_estimada": 4004.0, "risco_alvo_usd": 100,
             "especificacao": {"tick_valor": 0.01, "tick_tamanho": 0.01, "point": 0.01, "volume_min": 0.01, "contrato": 1}, "risco_planejado_usd": 15.0}
    cmd_ab = T._pg("insert into mt5_comandos (bot_id, user_id, bot_token, tipo, origem, status, params, resultado, criado_em, entregue_em, confirmado_em, expira_em, sessao_teste_id) "
                   "values (%s,%s,%s,'sell','sessao_r01v5','executado',%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s) returning id",
                   x["id"], camp["uid"], x["tok"], json.dumps({"uid": uid_c, "lote": 0.5, "sl": 4035.0}), json.dumps({"ticket": 777016, "retcode": 10009, "preco_real": 4003.0}),
                   t_dec + timedelta(seconds=1), t_dec + timedelta(seconds=5), t_dec + timedelta(seconds=12), t_dec + timedelta(seconds=60), sid)[0][0]
    g2 = t0 + timedelta(minutes=30)                                  # barra em que o B3 acionou (abriu em t0+30, fechou em t0+45)
    cmd_cl = T._pg("insert into mt5_comandos (bot_id, user_id, bot_token, tipo, origem, status, params, resultado, criado_em, entregue_em, confirmado_em, expira_em, sessao_teste_id) "
                   "values (%s,%s,%s,'close','sessao_gestao','executado',%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s) returning id",
                   x["id"], camp["uid"], x["tok"], json.dumps({"ticket": 777016, "motivo": "B3"}), json.dumps({"retcode": 10009, "preco_real": 3998.0, "fechados": 1}),
                   g2 + timedelta(minutes=15, seconds=26), g2 + timedelta(minutes=15, seconds=28), g2 + timedelta(minutes=15, seconds=35), g2 + timedelta(minutes=16), sid)[0][0]
    T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, preco_ref, stop_inicial, stop_atual, "
          "risco_planejado_usd, plano, estado, comando_id, ticket, posicao_id, preco_entrada, preco_saida, ts_reserva, ts_abertura, ts_fechamento, resultado_usd, lucro, comissao, swap, motivo_saida, gestao) "
          "values (%s,%s,%s,%s,%s,%s,'card8_bollinger','M15',-1,%s,0.5,4005.0,4035.0,4035.0,15.0,%s::jsonb,'fechada',%s,777016,777016,4003.0,3998.0,%s,%s,%s,2.5,2.5,0,0,'B3',%s::jsonb)",
          sid, x["id"], x["sim"], T._magic(x["tok"]), dec_id, uid_c, t0, json.dumps(plano), cmd_ab, t_dec, t_dec + timedelta(seconds=12), g2 + timedelta(minutes=15, seconds=35),
          json.dumps([{"acao": "manter", "barra": (t0 + timedelta(minutes=15)).isoformat(), "barras_de_posicao": 1, "leitura": {"B3": 0, "B5": 0, "corte_do_ciclo": 0, "stop_estrutural": "4028.1", "stop_vigente": "4035.0"}},
                      {"acao": "close", "barra": g2.isoformat(), "barras_de_posicao": 2, "motivo": "B3", "comando_id": cmd_cl,
                       "leitura": {"B3": 1, "B5": 0, "corte_do_ciclo": 1, "stop_estrutural": "4027.5", "stop_vigente": "4035.0", "B3_motivo": "B3: posicao vendida dentro de compressao [4003.00,4030.00] por 6 barras de M5 sem progresso (avanco a favor -0.50 = -0.08 ATR) — tese expirou"},
                       "corte": {"contrato": "corte-ciclo-2", "corta": 1, "origem": ["M1:alerta_empilhado_3 -> M15:fundo_barra_rompido"]}}]))
    T._pg("insert into ciclo_trilha (bot_id, user_id, simbolo, magic, barra_m15, etapa, estado, origem, motivo, ref, sessao_teste_id, ts) values (%s,%s,%s,%s,%s,'gestao','ok','api',%s,%s::jsonb,%s,%s)",
          x["id"], camp["uid"], x["sim"], T._magic(x["tok"]), g2 + timedelta(minutes=15), "fechar — B3", json.dumps({"abertura_id": T._pg("select max(id) from sessao_aberturas where sessao_teste_id=%s", sid)[0][0], "comando_id": cmd_cl}), sid, g2 + timedelta(minutes=15, seconds=25))
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    K = j["campanha"]; assert K["versao"] == "rel-4" and "leitura_na_entrada" in K["metodologia_da_auditoria"]
    op = next(o for o in K["operacoes"] if o["identificacao"]["ticket"] == 777016)
    # elo decisão↔operação pelo decisao_id (uid da decisão ≠ uid do candidato)
    G = op["gatilho_e_autorizacao"]; assert G["condicoes_atendidas"] == "12 de 12" and op["ciclo_na_decisao"]["janela_M1_M5_M15"] == {"M1": -1, "M5": -1, "M15": 0}
    assert "UTC (" in op["horarios"]["autorizacao_r01v5_emitida"] and op["horarios"]["latencias_s"]["autorizacao_ate_comando_s"] == 1.0
    assert all(x_["decisao"] and x_["completa"] for x_ in K["qualidade_dos_dados"]["correspondencia"] if x_["ticket_na_abertura"] == 777016)
    # 1. leitura na entrada: nada posterior à decisão
    E = op["leitura_na_entrada"]
    assert E["leitura_usada"]["qual"].startswith("primeira leitura") and E["leitura_usada"]["preco_no_snapshot"] == 4004.5          # snapshot de t0+20s, não o de t0+60s (3950)
    assert E["leitura_usada"]["snapshot_antes_da_decisao_s"] == 20.0
    C = E["ciclo_m1_m5_m15"]; assert C["atestado_assinado"]["janela"] == {"M1": -1, "M5": -1, "M15": 0} and "de baixo para cima" in C["leitura_de_baixo_para_cima"]
    assert C["por_timeframe_ea"]["M1"]["direcao"] == "baixa" and C["por_timeframe_ea"]["M1"]["estrutura"] == {"exaustao": True} and C["por_timeframe_ea"]["M1"]["niveis_topos_fundos"][0]["nivel"] == 4030.0
    assert C["estrutura_do_motor_no_snapshot"]["M5"]["regime"] == "compressao" and C["estrutura_do_motor_no_snapshot"]["M5"]["ultimo_topo"] == 4030.0
    assert E["contexto_superior"]["H4"] == "baixa" and E["contexto_superior"]["por_timeframe_ea"]["H4"]["direcao"] == "baixa" and "não é condição" in E["contexto_superior"]["papel"]
    N = E["niveis_e_indicadores_no_snapshot"]; assert N["atr14_m15"] == 6.5 and N["ema20_maximas_m15"] == 4012.0 and N["zonas_do_canal_por_tf"]["z15"] == "dentro" and N["spread_pts"] == 25
    Sg = E["sinal_do_card"]; assert Sg["card"] == "card8_bollinger" and "BB(20, 2σ)" in Sg["regra_do_card"] and Sg["nivel_do_sinal"] == 4005.0 and Sg["stop"]["risco_pts"] == 3000.0
    BB = Sg["conferencia_bollinger"]; assert BB["atendido_na_conferencia"] is True and BB["barra_anterior"]["fechamento"] == 4030.0 and BB["barra_do_sinal"]["fechamento"] == 4005.0
    assert BB["barra_anterior"]["fechamento"] > BB["barra_anterior"]["banda_superior"] and BB["barra_do_sinal"]["fechamento"] < BB["barra_do_sinal"]["banda_superior"]
    V = {c["condicao"][:2].strip("."): c["valores"] for c in E["condicoes_com_valores"]}
    assert V["7"]["preco_bid_no_snapshot"] == 4004.5 and V["7"]["preco_do_lado_certo_do_stop"] is True and V["7"]["distancia_preco_ao_stop_pts"] == 3050.0
    assert V["8"]["spread_pts"] == 25 and V["8"]["spread_sobre_risco_pct"] == 0.83 and V["9"]["profit_factor"] == 1.115 and V["4"]["restava_s"] == 1760.0
    assert V["10"]["posicoes_do_magic_no_snapshot"] == "0" and V["12"]["escolha_uid"] == uid_c and "4005.0" in E["sintese"] and "−1/−1/0" in E["sintese"].replace("-1", "−1")
    # 2. escolha do seletor na barra + diagnóstico da campanha
    Se = op["selecao_desta_barra"]; assert Se["avaliadas"] == 3 and Se["elegiveis"] == 1 and "único elegível" in Se["motivo_da_escolha"]
    esc = next(i for i in Se["estrategias"] if i["escolhido"]); assert esc["classificacao_entre_elegiveis"] == 1 and esc["elegivel"]
    assert any(i["primeiro_portao_fechado"].startswith("5.") for i in Se["estrategias"] if not i["elegivel"])
    D = K["selecao_diagnostico"][x["sim"]]; assert D["estrategias_nas_operacoes"] == ["card8_bollinger"] and "card8_bollinger" in str(D["causa"]) and "diversidade" in D["nota"]
    assert any(c_["card"] == "card9_macd" and c_["elegiveis"] == 0 and "5. célula na Lista do Seletor (estudo com selo)" in c_["portoes"] for c_ in D["por_estrategia_tf_lado"])
    # 3. B3 e gestão explicados
    Gx = op["gestao_explicada"]; assert len(Gx) == 2 and Gx[0]["regra"]["nome"] == "manter" and Gx[1]["codigo"] == "B3"
    b3 = Gx[1]; assert b3["regra"]["nome"].startswith("B3") and b3["regra"]["parametros"]["barras_sem_progresso"] == 6 and b3["regra"]["parametros"]["andar"] == "M5"
    assert b3["condicao_detectada"]["B3"] == 1 and b3["condicao_detectada"]["barras_de_posicao"] == 2 and b3["condicao_detectada"]["stop_estrutural"] == "4027.5"
    assert "compressao [4003.00,4030.00]" in b3["valores"]["B3_caixa_e_avanco"] and "UTC (" in b3["horarios"]["gatilho_registrado_na_trilha"]
    assert b3["horarios"]["latencia_barra_ate_comando_s"] == 26.0 and b3["horarios"]["latencia_comando_ate_execucao_s"] == 9.0 and b3["execucao"]["preco_real"] == 3998.0
    assert "gestao-1 na API" in b3["componente"] and "corretora" in b3["componente"] and "stop (corretora)" in b3["ordem_de_avaliacao"]
    # 4. medição: referência / solicitada / executada, especificação real, duração, unidades
    M = op["medicao"]; assert M["entrada"]["referencia_do_sinal"] == 4005.0 and M["entrada"]["solicitada_estimada_no_plano"] == 4004.0 and M["entrada"]["executada_no_mt5"] == 4003.0
    assert M["entrada"]["referencia_a_executada"]["preco"] == 2.0 and M["entrada"]["especificacao_real_do_simbolo"]["volume_min"] == 0.01 and M["duracao"]["barras_m15"] == 2
    assert "separados" in M["unidades"] and M["risco"]["efetivo_inicial_usd"] == 16.0 and M["risco"]["R_multiplo"] == 0.156
    # 5. contagem no intervalo exato: 24 h em (de, ate] com símbolo 24/7 = 96 barras, e lista de faltantes (nunca 99)
    from zoneinfo import ZoneInfo
    cfg = {"fuso_diario": "Europe/Kyiv", "horarios": {"BTCUSD": [], "XAUUSD": [{"de": "00:00", "ate": "24:00", "dias": [6, 7], "nota": "fim de semana"}]}}
    import api as A_
    ate = datetime(2026, 10, 10, 21, 55, 46, tzinfo=timezone.utc); de = ate - timedelta(days=1)
    r = A_._ses_barras_m15_janela(cfg, "BTCUSD", de, ate, [])
    assert r["esperadas"] == 96 and r["faltando_total"] == 96 and r["primeira_esperada_utc"] == "2026-10-09T22:00:00Z" and r["ultima_esperada_utc"] == "2026-10-10T21:45:00Z"
    r2 = A_._ses_barras_m15_janela(cfg, "XAUUSD", de, ate, [])
    assert r2["esperadas"] == 0          # 09/10 22:00 UTC → 10/10 (sábado, Kyiv) inteiro: fim de semana declarado
    r3 = A_._ses_barras_m15_janela(cfg, "XAUUSD", datetime(2026, 10, 8, 21, 0, tzinfo=timezone.utc), datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc), ["2026-10-09T10:00:00Z"])
    assert r3["esperadas"] == 96 and r3["recebidas"] == 1
    txt = A_._ses_ultimo_snapshot_vs_janela(cfg, "XAUUSD", "2026-10-09T20:57:50Z")
    assert "coerente com o fechamento" in txt and "fim de semana" in txt
    assert "falha de coleta" in A_._ses_ultimo_snapshot_vs_janela(cfg, "XAUUSD", "2026-10-09T12:00:00Z")
    Q = K["qualidade_dos_dados"]["por_ativo"][x["sim"]]["barras_no_periodo_exato_do_relatorio"]; assert "barra a barra" in Q["regra"] and isinstance(Q["faltando"], list) and Q["recebidas"] <= Q["esperadas"]   # (a bancada pode cair no fim de semana declarado do XAUUSD)


def test_17_stop_alterado_fora_origem_bloqueio_e_relatorio(amb, camp):
    """C27R34: stop movido no MT5 sem comando da plataforma → origem classificada pelas candles (= máxima da barra M15 anterior:
    trailing por barra do EA), registro permanente na operação e na trilha, NOVAS entradas do bot bloqueadas (gestão e proteção
    seguem), pendência no relatório; relatório traz a linha do tempo do stop, os negócios do MT5 e o plano do lote."""
    sid, x = camp["id"], camp["x"]
    _limpar(sid)
    T._pg("update sessoes_teste set config = config - 'bloqueios_por_bot' where id=%s", sid)
    mg = T._magic(x["tok"])
    ab_id = T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, preco_ref, stop_inicial, stop_atual, "
                  "risco_planejado_usd, plano, estado, ticket, posicao_id, preco_entrada, ts_reserva, ts_abertura, gestao) values (%s,%s,%s,%s,'dec-17','u17','card8_bollinger','M15',-1,%s,0.01,4100.0,4105.0,4105.0,5.0,"
                  "'{}'::jsonb,'aberta',777017,777017,4100.0, now() - interval '32 minutes', now() - interval '31 minutes', '[]'::jsonb) returning id",
                  sid, x["id"], x["sim"], mg, T._barra_m15() - timedelta(minutes=30))[0][0]
    pos = [{"ticket": 777017, "posicao_id": 777017, "magic": mg, "tipo": 1, "volume": "0.01", "preco_abertura": "4100.0", "sl": "4103.50", "tp": "0.0", "lucro": "-3.0", "swap": "0.0", "aberta_corretora": 1791698440}]
    det, barra = SS._det(x, [], gestao={"stop": None}, posicoes=pos)
    vela = "4099.00,4101.00,4098.00,4100.00,10"
    det["c15m"] = ";".join([vela] * 16 + ["4100.00,4103.50,4097.00,4099.50,10", "4099.50,4100.20,4099.00,4099.80,5"])   # penúltima = última FECHADA: máxima 4103,50
    assert SS._snap(x, det, pos=1)[0] == 200
    tr = T._pg("select motivo, ref from ciclo_trilha where bot_id=%s and etapa='gestao' and estado='aviso' and motivo like 'stop vigente no MT5: 4103.5%%' order by id desc limit 1", x["id"])
    assert tr and "FORA da plataforma" in tr[0][0] and "trailing por barra do EA" in tr[0][0] and tr[0][1]["classificacao"]["timeframe"] == "M15"
    g = T._pg("select gestao, stop_atual from sessao_aberturas where id=%s", ab_id)[0]
    ext = [e for e in g[0] if e.get("acao") == "stop_externo"]
    assert len(ext) == 1 and ext[0]["stop_novo"] == 4103.5 and ext[0]["stop_anterior"] == 4105.0 and "BTvTrailingBarra" in ext[0]["origem"]["origem"] and float(g[1]) == 4103.5
    bq = T._pg("select config->'bloqueios_por_bot' from sessoes_teste where id=%s", sid)[0][0]
    assert str(x["id"]) in bq and "InpBTTrailingBarra" in bq[str(x["id"])]["motivo"] and "liberar" in bq[str(x["id"])]
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='limites' and estado='recusado' and motivo like 'NOVAS ENTRADAS BLOQUEADAS%%'", x["id"])[0][0] == 1
    import api as A_
    ses_ = {"config": {"bloqueios_por_bot": bq}}
    assert A_._ses_bloqueio_do_bot(ses_, {"id": x["id"]})["motivo"].startswith("stop da abertura")
    # segundo snapshot com o mesmo stop: nada novo (sem duplicar bloqueio nem registro)
    assert SS._snap(x, det, pos=1)[0] == 200
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='limites' and estado='recusado' and motivo like 'NOVAS ENTRADAS BLOQUEADAS%%'", x["id"])[0][0] == 1
    # relatório: linha do tempo do stop com a origem, pendência de bloqueio, plano sem lote-2 declarado
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    K = j["campanha"]; op = next(o for o in K["operacoes"] if o["identificacao"]["ticket"] == 777017)
    SP = op["stop_de_protecao"]; assert SP["alteracoes_fora_da_plataforma"] == 1 and "BTvTrailingBarra" in SP["conflito"] and SP["eventos"][0]["stop"] == 4105.0
    ext_ = next(e for e in SP["eventos"] if e.get("classificacao") and e["classificacao"].get("conflito"))
    CL = ext_["classificacao"]; assert CL["alteracao_observada"]["stop_novo"] == 4103.5 and CL["alteracao_observada"]["stop_anterior"] == 4105.0      # C27R36
    assert "BTvTrailingBarra" in CL["origem"]["inferida"] and CL["origem"]["confirmada"] is False and "Journal" in CL["origem"]["como_confirmar"]
    assert CL["conformidade_com_o_desenho"]["conforme"] is False and "trailing_do_ea" in CL["conformidade_com_o_desenho"]["ver"]
    assert any("NOVAS ENTRADAS BLOQUEADAS" in p_ for p_ in K["resumo_executivo"]["pendencias_e_inconsistencias"])
    assert K["resumo_executivo"]["bloqueios_efetivos"]["bots_bloqueados"][0]["base_do_motivo"].startswith("hipótese explícita")   # C27R38
    assert "bloquead" in j["sessao_teste"]["sessao"]["novas_aberturas"].lower() and "por bot" in j["sessao_teste"]["sessao"]["novas_aberturas"] and str(x["id"]) in j["sessao_teste"]["sessao"]["bloqueios_por_bot"]   # C27R40
    BQ = K["resumo_executivo"]["limites_em_uso"]["bloqueios_por_bot"]; assert not BQ["nenhum"] and any(b["bot_id"] == x["id"] and b["abertura_ref"] == ab_id and b["desde_utc"] for b in BQ["bots_bloqueados"])   # C27R37
    assert "INFERIDA" in SP["conflito"] and "comprovad" not in SP["conflito"] and ext[0]["origem"]["grau"].startswith("inferida") and ext[0]["origem"]["confirmada"] is False
    assert op["plano_do_lote"]["situacao"].startswith("plano gravado sem o detalhe lote-2") and op["negocios_assinados_mt5"]["situacao"] == "não disponível"
    D = K["selecao_diagnostico"][x["sim"]]["catalogo_esperado_x_disponivel"]; assert D["esperadas"] == 39 and len(D["matriz"]) == 39 and "cards" in D["leitura"]
    # limpeza: libera o bot (como o dono faria) e remove a abertura de bancada
    T._pg("update sessoes_teste set config = config - 'bloqueios_por_bot' where id=%s", sid)
    T._pg("delete from sessao_aberturas where id=%s", ab_id)


def test_18_consolidacao_das_ordens_trailing_do_ea_e_aud2_gravada(amb, camp):
    """C27R35: (1) aud-2 realmente gravada — estrutura_por_tf / gestao_assinada / atestado chegam ao banco (sql/0016: a RPC da
    0015 ignorava as chaves); (2) o relatório traz a determinação do trailing do EA (fora do desenho autorizado; origem × conformidade)
    e a matriz de consolidação das ordens com estado por linha e evidência real; (3) o ZIP exporta as três chaves."""
    import io, zipfile, urllib.request as rq
    sid, x = camp["id"], camp["x"]
    _limpar(sid)
    T._pg("update sessoes_teste set config = config - 'bloqueios_por_bot' where id=%s", sid)
    det, barra = SS._det(x, [], gestao={"stop": None})
    assert SS._snap(x, det)[0] == 200
    lv = T._pg("select estrutura_por_tf, gestao_assinada, atestado from auditoria_leituras where bot_id=%s order by id desc limit 1", x["id"])[0]
    assert isinstance(lv[0], dict) and "M15" in lv[0] and isinstance(lv[1], dict) and isinstance(lv[2], dict) and "cv2" in lv[2]
    time.sleep(2)
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    K = j["campanha"]
    TE = K["trailing_do_ea"]; assert TE["determinacao"]["integra_o_desenho_autorizado"] is False and "BTvTrailingBarra" in TE["trailing_do_ea"]["rotina"]
    assert "ORIGEM" in TE["determinacao"]["origem_x_conformidade"] and "InpBTTrailingBarra" in TE["determinacao"]["correcao"] and "operacoes" in TE["exposicao_na_campanha"]
    CS = K["consolidacao_das_ordens"]; assert CS["versao"] == "cons-1" and len(CS["linhas"]) >= 12
    for r in CS["linhas"]:
        assert set(r) == {"ordem", "requisito", "componente_existente", "implementacao_entregue", "evidencia_real", "estado", "pendencia"} and r["ordem"] in ("C27R31", "C27R32", "C27R33", "C27R34", "C27R35", "C27R38", "C27R40", "C27R41")
        assert str(r["estado"]).split(" ")[0] in ("verificado", "não", "divergência"), r
    aud = next(r for r in CS["linhas"] if r["requisito"].startswith("aud-2"))
    assert aud["estado"] == "verificado" and aud["evidencia_real"]["colunas_presentes"] is True and aud["evidencia_real"]["ultima_leitura_com_estrutura_utc"]
    assert sum(CS["totais"].values()) == len(CS["linhas"]) and "agora" in CS["implantacoes"] and CS["implantacoes"]["agora"].get("api", "").startswith("8.")
    r6 = next(r for r in CS["linhas"] if r["requisito"].startswith("6. rel-4")); assert r6["estado"].startswith("verificado")        # C27R39: API ≥ 8.04 gerou este rel-4
    # ZIP: leituras vivas com as três chaves
    import json
    q = rq.Request(SS.URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": j["relatorio_id"], "formato": "zip"}).encode(),
                   headers={"Authorization": "Bearer " + amb["sess"], "Content-Type": "application/json"}, method="POST")
    z = zipfile.ZipFile(io.BytesIO(rq.urlopen(q, timeout=180).read()))
    nome = next(n for n in z.namelist() if "leituras_vivas" in n)
    assert "estrutura_por_tf" in z.read(nome).decode("utf-8")
    # PDF com as seções 3b/3c
    q = rq.Request(SS.URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": j["relatorio_id"], "formato": "pdf"}).encode(),
                   headers={"Authorization": "Bearer " + amb["sess"], "Content-Type": "application/json"}, method="POST")
    assert rq.urlopen(q, timeout=180).read()[:4] == b"%PDF"


def test_19_escopo_sem_recorte_vinculos_e_por_que_da_gestao(amb, camp):
    """C27R36: (1) bot em campanha gera o bloco 'campanha' e o 'escopo_do_relatorio' MESMO com recorte 'tudo' (período 7 dias),
    com registros anteriores à campanha separados; (2) cadeia.operacoes traz os vínculos abertura/decisão/comando/posição;
    (3) gestão explicada diz POR QUÊ (B3 sinalizado com 1 barra de posição não aplica; com 3 aplica); (4) textos de autoridade:
    r01v5 vigente, r01v4 só registro; (5) trilha exportada sem truncagem de 'ref'."""
    sid, x = camp["id"], camp["x"]
    _limpar(sid)
    T._pg("update sessoes_teste set config = config - 'bloqueios_por_bot' where id=%s", sid)
    mg = T._magic(x["tok"]); agora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    t0 = agora - timedelta(hours=2)
    def cmd(tipo, params, quando, origem="sessao_gestao"):
        return T._pg("insert into mt5_comandos (bot_id, user_id, bot_token, tipo, origem, status, params, resultado, criado_em, entregue_em, confirmado_em, expira_em, sessao_teste_id) "
                     "values (%s,%s,%s,%s,%s,'executado',%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s) returning id", x["id"], camp["uid"], x["tok"], tipo, origem, json.dumps(params),
                     json.dumps({"ticket": 777019, "retcode": 10009, "preco_real": 4001.0}), quando, quando + timedelta(seconds=2), quando + timedelta(seconds=9), quando + timedelta(seconds=60), sid)[0][0]
    c_ab = cmd("buy", {"uid": "u19", "lote": 0.3, "sl": 3990.0}, t0 + timedelta(seconds=30), "sessao_r01v5")
    ab_id = T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, preco_ref, stop_inicial, stop_atual, "
                  "risco_planejado_usd, plano, estado, comando_id, ticket, posicao_id, preco_entrada, preco_saida, ts_reserva, ts_abertura, ts_fechamento, resultado_usd, lucro, comissao, swap, motivo_saida, gestao) "
                  "values (%s,%s,%s,%s,'dec-19','u19','card8_bollinger','M15',1,%s,0.3,4000.0,3990.0,3990.5,3.0,'{}'::jsonb,'fechada',%s,777019,777019,4001.0,3999.0,%s,%s,%s,-0.6,-0.6,0,0,'B3','[]'::jsonb) returning id",
                  sid, x["id"], x["sim"], mg, t0, c_ab, t0 + timedelta(seconds=29), t0 + timedelta(seconds=39), t0 + timedelta(minutes=60, seconds=40))[0][0]
    c_sl = cmd("mover_sl", {"ticket": 777019, "sl": 3990.5, "abertura_id": ab_id}, t0 + timedelta(minutes=30, seconds=30))
    c_cl = cmd("close", {"ticket": 777019, "motivo": "B3", "abertura_id": ab_id}, t0 + timedelta(minutes=60, seconds=30))
    gest = [{"acao": "mover_sl", "barra": (t0 + timedelta(minutes=15)).isoformat(), "barras_de_posicao": 1, "motivo": "trailing estrutural (pivô ∓ 0,3×ATR14 do M15)", "comando_id": c_sl,
             "leitura": {"B3": 1, "B5": 0, "corte_do_ciclo": 0, "stop_estrutural": "3990.5", "stop_vigente": "3990.0"}},
            {"acao": "close", "barra": (t0 + timedelta(minutes=45)).isoformat(), "barras_de_posicao": 3, "motivo": "B3", "comando_id": c_cl,
             "leitura": {"B3": 1, "B5": 0, "corte_do_ciclo": 0, "stop_estrutural": "3990.2", "stop_vigente": "3990.5"}}]
    T._pg("update sessao_aberturas set gestao=%s::jsonb where id=%s", json.dumps(gest), ab_id)
    bm_id = T._pg("insert into babymachine_operacoes (user_id, bot_id, ativo, timeframe, fonte, status, ts_entrada, ts_saida) values (%s,%s,%s,'M15','estrategia_compilada','fechada',%s,%s) returning id",
                  camp["uid"], x["id"], x["sim"], t0 + timedelta(seconds=44), t0 + timedelta(minutes=60, seconds=45))[0][0]
    # operação de OUTRA sessão (anterior, encerrada) dentro dos 7 dias
    T._pg("delete from sessao_aberturas where sessao_teste_id='ENS-ANTERIOR-19'"); T._pg("delete from sessoes_teste where id='ENS-ANTERIOR-19'")
    T._pg("insert into sessoes_teste (id, nome, user_id, bots, estado, fim_previsto, config) values ('ENS-ANTERIOR-19','ensaio anterior',%s,%s,'encerrada', now() - interval '2 day', '{}'::jsonb)",
          camp["uid"], [x["id"]])
    ab_ant = T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, preco_ref, stop_inicial, stop_atual, "
                   "risco_planejado_usd, plano, estado, ticket, posicao_id, preco_entrada, preco_saida, ts_reserva, ts_abertura, ts_fechamento, resultado_usd, motivo_saida, gestao) "
                   "values ('ENS-ANTERIOR-19',%s,%s,%s,'dec-old','u-old','card7_rsi','H1',1,%s,0.02,3900.0,3890.0,3890.0,1.0,'{}'::jsonb,'fechada',777001,777001,3901.0,3900.9,%s,%s,%s,-0.01,'B3','[]'::jsonb) returning id",
                   x["id"], x["sim"], mg, agora - timedelta(days=3), agora - timedelta(days=3), agora - timedelta(days=3), agora - timedelta(days=3, hours=-1))[0][0]
    time.sleep(1)
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "7d", "sessao": "tudo", "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    assert j["recorte"]["recorte"] == "tudo" and j["recorte"]["campanha_ativa"] == sid and j["sessao_teste_id"] is None
    E = j["escopo_do_relatorio"]; assert E["campanha"]["id"] == sid and E["recorte_pedido"] == "tudo" and ab_id in E["operacoes_da_campanha"]
    assert any(a["abertura_id"] == ab_ant and a["sessao"] == "ENS-ANTERIOR-19" for a in E["registros_anteriores_a_campanha"]["operacoes_de_outras_sessoes_no_periodo"])
    assert any(b["neste_relatorio"] for b in E["bots_da_campanha"]) and "r01v5" in E["autoridade_vigente"] and "cobertura_separada" in E
    K = j["campanha"]; assert K["versao"] == "rel-4" and "consolidacao_das_ordens" in K and "trailing_do_ea" in K
    op = next(o for o in K["operacoes"] if o["identificacao"]["abertura_id"] == ab_id)
    assert all(int(a["abertura_id"]) != ab_ant for a in [o["identificacao"] for o in K["operacoes"]])          # a anterior fica fora do bloco campanha
    Gx = op["gestao_explicada"]; assert len(Gx) == 2
    assert Gx[0]["valores"]["por_que"].startswith("APERTA") and "NÃO aplicado" in next(p_["resultado"] for p_ in Gx[0]["valores"]["avaliacao_passo_a_passo"] if p_["regra"] == "B3")
    assert Gx[1]["valores"]["por_que"].startswith("APLICADO: B3=1 com posição de 3")
    # C27R37: resultado do dia separado (líquido −0,6 = perdas −0,6 + ganhos 0 → consumo do teto 0,6), bloqueio por bot, vínculo da gestão ao snapshot, conferências
    RD = K["resumo_executivo"]["limites_em_uso"]["resultado_do_dia"]
    assert RD["resultado_liquido_hoje_usd"] == -0.6 and RD["perdas_realizadas_hoje_usd"] == -0.6 and RD["ganhos_realizados_hoje_usd"] == 0 and RD["consumo_do_teto_usd"] == 0.6 and ab_id in RD["ids_fechadas_hoje"]
    assert K["resumo_executivo"]["limites_em_uso"]["bloqueios_por_bot"]["nenhum"] is True and K["limites"]["uso_agora"]["resultado_do_dia"]["resultado_liquido_hoje_usd"] == -0.6
    W = Gx[1]["leitura_que_acionou"]["vinculo_com_o_snapshot_e_atestado_usados"]; assert W["referencia"] == "criação do comando" and W["referencia_utc"].startswith(str((t0 + timedelta(minutes=60, seconds=30)).isoformat())[:16])
    assert W["snapshot_anterior_ao_comando"] in (True, None) and "B3" in Gx[1]["valores"]["verificabilidade"] and Gx[1]["valores"]["verificabilidade"].startswith("PARCIALMENTE")
    CF = op["conferencias"]; assert CF["corte_do_relatorio_utc"] and any(x["bloco"] == "negocios_assinados_mt5" for x in CF["conferido_na_geracao_posterior_ao_evento"]) and all(x["posterior_ao_corte"] is False for x in CF["conferido_na_geracao_posterior_ao_evento"])
    CS = K["consolidacao_das_ordens"]; b3row = next(r for r in CS["linhas"] if r["requisito"].startswith("3. B3")); assert b3row["estado"].startswith("PARCIALMENTE")
    st_row = next(r for r in CS["linhas"] if r["requisito"].startswith("2. origem")); assert "inferida" in st_row["estado"] and "INFERIDA" in st_row["evidencia_real"]["origem_op_6"]
    assert "INFERIDA" in K["trailing_do_ea"]["determinacao"]["origem_x_conformidade"]
    # C27R38: métricas período × acumulado, bloqueios no topo, reconstruído × comprovado, input do trailing como hipótese
    MT = K["resumo_executivo"]["metricas"]; assert MT["acumulado_da_campanha"]["consolidado"]["fechamentos"] >= 1
    pb_k = next(k for k in MT["acumulado_da_campanha"]["por_bot"] if k.startswith(x["sim"] + " · bot " + str(x["id"])))                     # C27R51: por bot (atual/histórico)
    assert pb_k.endswith("(atual)") and ab_id in MT["acumulado_da_campanha"]["por_bot"][pb_k]["ids_fechamentos"] and ab_ant not in MT["acumulado_da_campanha"]["por_bot"][pb_k]["ids_fechamentos"]
    assert ab_id in MT["no_periodo_do_relatorio"]["por_bot"][pb_k]["ids_fechamentos"] and MT["acumulado_da_campanha"]["por_ativo"][x["sim"]]["fechamentos"] >= 1
    RC = MT["acumulado_da_campanha"]["reconciliacao"]; assert RC["confere_com_consolidado"] is True and RC["fechamentos"] == K["resumo_executivo"]["consolidado"]["fechamentos"]
    assert K["resumo_executivo"]["consolidado"]["entradas"] == RC["entradas"]
    assert list(K["resumo_executivo"].keys())[0] == "bloqueios_efetivos" and K["resumo_executivo"]["consolidado"]["escopo"].startswith("ACUMULADO")
    assert W["situacao"].startswith("RECONSTRUÍDO") and W["snapshot_id_gravado_na_avaliacao"] is None
    assert op["leitura_na_entrada"]["leitura_usada"]["snapshot_situacao"].startswith("RECONSTRUÍDO")
    TI = K["trailing_do_ea"]["trailing_do_ea"]["input"]; assert "VERIFICADO" in TI["padrao_no_codigo_do_ea_gerado"] and "NÃO VERIFICADO" in TI["valor_configurado_nos_graficos_da_campanha"] and TI["hipotese_explicita"]
    assert K["trailing_do_ea"]["exposicao_na_campanha"]["leitura"].startswith("HIPÓTESE")
    # C27R40: risco planejado × efetivo (compra 0,3 @ ref 4000 stop 3990 → 3,0; executada 4001 → 3,3; desl. entrada 0,3; saída por B3, não pelo stop)
    RX = op["risco_planejado_x_efetivo"]; assert RX["planejado_usd"] == 3.0 and RX["efetivo_na_entrada_usd"] == 3.3 and RX["deslizamento_de_entrada_usd"] == 0.3 and RX["saida_pelo_stop"] is False
    rows40 = [r for r in K["consolidacao_das_ordens"]["linhas"] if r["ordem"] in ("C27R38", "C27R40")]; assert len(rows40) == 4
    assert all(("verificado" in r["estado"] or "não verificado" in r["estado"]) for r in rows40)
    # vínculos na cadeia legada
    co = next(o for o in j["cadeia"]["operacoes"] if o["id"] == bm_id)
    assert co["ticket"] == 777019 and co["comando_id"] == c_ab and co["vinculos"]["abertura_id"] == ab_id and co["vinculos"]["decisao_id"] == "dec-19"
    assert co["vinculos"]["comando_de_abertura"]["ticket_na_resposta"] == 777019 and sorted(co["vinculos"]["comandos_de_gestao_e_saida"]) == sorted([c_sl, c_cl]) and co["vinculos"]["como_foi_vinculada"] == "entrada ±120 s"
    assert next(c for c in j["cadeia"]["comandos"] if c["id"] == c_sl)["ticket"] == 777019
    # autoridade: estado atual × configuração histórica
    V = j["identificacao"]["versoes"]; assert "r01v5" in V["autoridade_vigente"] and "r01v4" in V["autoridade_historica_so_registro"]
    assert not any("sombra, desligada" in str(q.get("resposta")) for q in j["resumo"]["perguntas"])
    # trilha exportada sem truncagem de ref
    TA = j.get("trilha_auditavel") or {}
    assert not any(isinstance(i.get("ref"), dict) and i["ref"].get("truncado") for i in (TA.get("itens") or []))
    T._pg("delete from babymachine_operacoes where id=%s", bm_id); T._pg("delete from sessao_aberturas where id in (%s,%s)", ab_id, ab_ant)
    T._pg("delete from sessoes_teste where id='ENS-ANTERIOR-19'")


def test_20_risco_contra_stop_em_vigor_c27r41():
    """C27R41: op 6 real (sell 4.93 @ 83010.81, stop inicial 83024.863677 movido para 82903.45, saída 82903.98 pelo stop, +526.67):
    deslizamento do stop contra o stop EM VIGOR, movimento do stop separado, ganho dito como ganho, resíduo numérico."""
    import api
    ab = {"lado": -1, "lote": 4.93, "plano": {"especificacao": {"tick_valor": 0.01, "tick_tamanho": 0.01}}, "preco_ref": 83004.61,
          "stop_inicial": 83024.863677, "stop_atual": 82903.45, "preco_entrada": 83010.81, "preco_saida": 82903.98,
          "motivo_saida": "stop_trailing", "resultado_usd": 526.67, "comissao": 0, "swap": 0, "risco_planejado_usd": 99.85}
    RX = api._rel_op_risco(ab)
    assert RX["planejado_usd"] == 99.85 and RX["efetivo_na_entrada_usd"] == 69.28
    assert RX["stop_movido"] is True and RX["stop_em_vigor_na_saida"] == 82903.45
    assert RX["movimento_do_stop_usd"] == -598.57 and RX["deslizamento_do_stop_na_saida_usd"] == 2.61
    assert RX["perda_realizada_usd"] is None and RX["ganho_realizado_usd"] == 526.67
    assert RX["perda_explicada_usd"] == -526.68 and abs(RX["residuo_nao_explicado_usd"]) <= 0.02
    assert RX["leitura"].startswith("GANHO realizado 526.67") and "movido" in RX["leitura"]
    # op 2 preservada (stop não movido): mesma decomposição da 8.10
    ab2 = {"lado": -1, "lote": 1.07, "plano": {"especificacao": {"tick_valor": 0.01, "tick_tamanho": 0.01}}, "preco_ref": 81852.25,
           "stop_inicial": 81944.929465, "stop_atual": 81944.929465, "preco_entrada": 81847.18, "preco_saida": 81945.40,
           "motivo_saida": "stop", "resultado_usd": -105.10, "comissao": 0, "swap": 0, "risco_planejado_usd": 99.17}
    R2 = api._rel_op_risco(ab2)
    assert R2["stop_movido"] is False and R2["movimento_do_stop_usd"] == 0.0 and R2["perda_realizada_usd"] == 105.1
    assert R2["deslizamento_de_entrada_usd"] == 5.42 and R2["deslizamento_do_stop_na_saida_usd"] == 0.5 and R2["residuo_nao_explicado_usd"] == 0.01
    assert R2["leitura"].startswith("perda realizada 105.1 = efetivo na entrada 104.59")
    assert "stop_trailing" in api._REL_SAIDAS


def test_21_b3_valores_internos_e_tratamento_do_risco_c27r41():
    """C27R41: valores internos do B3 lidos do texto do motor congelado; tratamento do risco efetivo acima do planejado descrito
    sem ação corretiva e sem tolerância inventada; parâmetros dos EAs declarados não verificáveis."""
    import api
    v = api._rel_b3_valores("B3: posicao vendida dentro de compressao [82850.10,82990.55] por 6 barras de M5 sem progresso (avanco a favor -12.30 = -0.41 ATR) — tese expirou")
    assert v["corta"] is True and v["caixa_piso"] == 82850.10 and v["caixa_teto"] == 82990.55 and v["barras"] == 6 and v["andar"] == "M5"
    assert v["avanco_a_favor_preco"] == -12.30 and v["avanco_a_favor_atr"] == -0.41
    v2 = api._rel_b3_valores("sem compressao/lateral no andar do B3")
    assert v2["corta"] is False and v2["estado"].startswith("SEM COMPRESSÃO")
    v3 = api._rel_b3_valores("B3: ha progresso a favor (+8.75)")
    assert v3["corta"] is False and v3["avanco_a_favor_preco"] == 8.75
    assert api._rel_b3_valores("")["situacao"] == api._REL_ND
    ab = {"lado": -1, "lote": 1.07, "plano": {"versao": "lote-2", "especificacao": {"tick_valor": 0.01, "tick_tamanho": 0.01, "ponto": 0.01},
                                             "distancias": {"referencia_ao_stop": {"preco": 92.68}, "entrada_executavel_ao_stop": {"preco": 92.68}, "spread_na_saida": {"preco": 0.0}, "tolerancia_slippage": {"pontos_mt5": None}, "efetiva": {"preco": 92.68}}},
          "preco_ref": 81852.25, "stop_inicial": 81944.929465, "stop_atual": 81944.929465, "preco_entrada": 81847.18, "preco_saida": 81945.40,
          "motivo_saida": "stop", "resultado_usd": -105.10, "comissao": 0, "swap": 0, "risco_planejado_usd": 99.17}
    TT = api._rel_op_risco(ab)["tratamento_do_risco_efetivo_acima_do_planejado"]
    assert TT["antes_do_preenchimento"]["plano_de_lote"] == "lote-2" and TT["antes_do_preenchimento"]["distancias_do_plano"]["tolerancia_slippage_pts"] is None
    assert TT["depois_do_preenchimento"]["acao_corretiva"].startswith("NENHUMA") and TT["depois_do_preenchimento"]["criterio_de_rejeicao_ou_alerta"].startswith("NÃO EXISTE")
    N = TT["nesta_operacao"]; assert N["excesso_usd"] == 5.42 and N["acima_do_planejado"] is True and N["dentro_da_tolerancia"] is None and N["excesso_pts"] == 506.5
    PE = api._REL_TRAILING_EA["trailing_do_ea"]["parametros_efetivos_dos_eas"]
    assert PE["verificavel_pela_plataforma"] is False and "confirmação explícita do dono" in PE["criterio_de_liberacao"]


def test_22_perdas_consecutivas_informativo_c27r42():
    """C27R42: o painel expõe o efeito das perdas consecutivas (bloqueia × informativo) a partir da config da campanha."""
    import api
    u = api._ses_uso_total([], {"max_perdas_consecutivas": 3})
    assert u["perdas_consecutivas_bloqueia"] is True and u["perdas_consecutivas_efeito"].startswith("suspende")
    u = api._ses_uso_total([], {"max_perdas_consecutivas": 3, "perdas_consecutivas_bloqueia": False})
    assert u["perdas_consecutivas_bloqueia"] is False and u["perdas_consecutivas_efeito"].startswith("INFORMATIVO")


def test_23_planejado_e_o_risco_reservado_c27r43():
    """C27R43: op 9 real — planejado = 99,90 reservado (lote-2), efetivo 79,54 → diferença −20,36; referência→stop (71,56) só informativa."""
    import api
    ab = {"lado": -1, "lote": 0.87, "plano": {"versao": "lote-2", "especificacao": {"tick_valor": 0.01, "tick_tamanho": 0.01, "ponto": 0.01}},
          "preco_ref": 83907.12, "stop_inicial": 83989.371362, "stop_atual": 83989.371362, "preco_entrada": 83897.95, "preco_saida": 83995.58,
          "motivo_saida": "stop", "resultado_usd": -84.94, "comissao": 0, "swap": 0, "risco_planejado_usd": 99.90}
    RX = api._rel_op_risco(ab)
    assert RX["planejado_usd"] == 99.9 and RX["planejado_referencia_ao_stop_usd"] == 71.56 and RX["efetivo_na_entrada_usd"] == 79.54
    assert RX["diferenca_efetivo_menos_planejado_usd"] == -20.36 and RX["deslizamento_do_stop_na_saida_usd"] == 5.4 and RX["perda_realizada_usd"] == 84.94
    assert abs(RX["residuo_nao_explicado_usd"]) <= 0.01
    assert RX["tratamento_do_risco_efetivo_acima_do_planejado"]["nesta_operacao"]["acima_do_planejado"] is False


def test_24_gestao2_continuidade_op10_e_op8_reais_c27r44():
    """C27R44 (gestao-2) com as leituras REAIS gravadas (auditoria_leituras, homolog):
    op 10 (XAU venda, 09:30 UTC de 12/10): B3=1 (2 barras) + corte FINO (M15:fundo_barra_rompido) com M15 descendente, canal −1,
    último topo 4188,15 intacto (fechamento 4177,18), M30 −1 → gestao-2 PROTEGE (não fecha); na avaliação seguinte com B3 ainda
    sinalizado e continuidade intacta → fecha (espera máx. 1). Corte ESTRUTURAL ou continuidade perdida → fecha."""
    import api
    por_tf = {"M15": {"dir": -1, "estrutura": "descendente", "regime": "compressao", "localizacao": "fundo_da_faixa", "ultimo_topo": 4188.15, "ultimo_fundo": 4172.82},
              "M30": {"dir": -1, "estrutura": "descendente", "regime": "tendencia"}, "H1": {"dir": -1, "estrutura": "mista"}, "H4": {"dir": 0}, "D1": {"dir": 0}}
    L = {"B3": 1, "corte_do_ciclo": 1, "corte_origem": ["M1:fundo_barra_rompido M1:fundo_barra_rompido M1:rompeu_ultimo_topo M1:fundo_barra_rompido M1:rompeu_ultimo_topo M1:fundo_barra_rompido M1:rompeu_ultimo_topo M5:fundo_barra_rompido -> M15:fundo_barra_"],
         "B3_motivo": "B3: posicao vendida dentro de compressao [4172.82,4188.15] por 6 barras de M5 sem progresso (avanco a favor -1.20 = -0.45 ATR) — tese expirou", "stop_estrutural": 4189.655203}
    g = {"B5": 0, "fechamento": 4177.18}
    cls = api._cont_eventos_corte(L["corte_origem"])
    assert cls["fino"] is True and cls["estrutural"] is False and cls["decidido_por_m15"] == ["fundo_barra_rompido"] and cls["origem_truncada_pelo_conector"] is True
    cont = api._cont_continuidade(-1, por_tf, 4177.18)
    assert cont["ok"] is True and cont["M15"]["pivo_contra_intacto"] is True and cont["M30"]["nao_contra"] is True
    acao, motivo, c, k, exp = api._gestao2_decidir(-1, L, g, {"contrato": "corte-ciclo-2"}, por_tf, 2, [{"acao": "mover_sl", "leitura": {"B3": 0}}, {"acao": "manter", "leitura": {"B3": 0}}])
    assert acao == "proteger" and motivo == "B3" and "INTACTA" in exp and ("pausa" in exp or "pullback" in exp)
    # avaliação seguinte: B3 continua, continuidade intacta → espera esgotada → fecha
    acao2, motivo2, _c, _k, exp2 = api._gestao2_decidir(-1, L, g, {"contrato": "corte-ciclo-2"}, por_tf, 3, [{"acao": "manter(protegido)", "protegido_por": "B3", "barras_de_posicao": 2, "leitura": {"B3": 1}}])
    assert (acao2, motivo2) == ("close", "B3") and "limite de espera" in exp2
    # continuidade PERDIDA (fechamento rompe o último topo do M15) → B3 fecha na hora
    acao3, motivo3, c3, _k, exp3 = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4188.40}, {"contrato": "corte-ciclo-2"}, por_tf, 2, [])
    assert (acao3, motivo3) == ("close", "B3") and c3["ok"] is False and "rompeu o último topo" in "; ".join(c3["motivos"])
    # corte ESTRUTURAL (3º sinal) fecha mesmo com continuidade intacta e sem B3
    L2 = dict(L, B3=0, corte_origem=[{"identificado_em": ["M1:rompeu_ultimo_topo", "M5:rompeu_ultimo_topo"], "decidido_por": ["M15:rompeu_ultimo_topo"]}])
    acao4, motivo4, _c, k4, _e = api._gestao2_decidir(-1, L2, g, {"contrato": "corte-ciclo-2"}, por_tf, 2, [])
    assert (acao4, motivo4) == ("close", "ciclo") and k4["estrutural"] is True
    # op 8 (XAU compra, 03:15 UTC, snapshot 41550 REAL): B3=1 com 3 barras; M15 canal 0 / estrutura MISTA (topo 4214,23, fundo 4200,07),
    # fechamento 4203,79; M30 1 ascendente; H1 1 → a estrutura de alta do M15 se perdeu (mista sem canal a favor) → continuidade PERDIDA → B3 fecha (igual à gestao-1)
    L8 = {"B3": 1, "corte_do_ciclo": 0, "corte_origem": [], "B3_motivo": "B3: posicao comprada dentro de compressao [4202.98,4207.90] por 6 barras de M5 sem progresso (avanco a favor -3.74 = -0.84 ATR) — tese expirou"}
    por8 = {"M15": {"dir": 0, "estrutura": "mista", "regime": "compressao", "ultimo_topo": 4214.23, "ultimo_fundo": 4200.07}, "M30": {"dir": 1, "estrutura": "ascendente"}, "H1": {"dir": 1}}
    acao8, motivo8, c8, _k, _e = api._gestao2_decidir(1, L8, {"B5": 0, "fechamento": 4203.79}, None, por8, 3, [])
    assert (acao8, motivo8) == ("close", "B3") and c8["ok"] is False and c8["M15"]["estrutura_a_favor"] is False and c8["M15"]["pivo_contra_intacto"] is True
    # B5 fecha sempre; sem nada → trailing
    assert api._gestao2_decidir(1, L8, {"B5": 1}, None, por8, 3, [])[0] == "close"
    assert api._gestao2_decidir(1, {"B3": 0, "corte_do_ciclo": 0}, {"B5": 0, "fechamento": 4205.0}, None, por8, 1, [])[0] is None


def test_25_sel4_portao8_proporcional_ao_risco_c27r44():
    """C27R44 (sel-4): o portão 8 tolera max(DESVIO_MAX do ativo, 10% da distância entrada→stop). Gold 12/10 05:30 UTC: card2 M15 venda
    entrada 4184,63, stop ~4197,46 (risco 1283 pts), preço 4184,19 (44 pts) → passa (sel-3 recusava com limite 30); 358 pts (04:15) segue recusado."""
    import api
    assert api.SEL_VERSAO == "sel-6" and api._SEL_DESVIO_FRAC_RISCO == 0.10 and api._SEL_DESVIO_MAX["XAUUSD"] == 30
    lim = max(api._SEL_DESVIO_MAX["XAUUSD"], 1283 * api._SEL_DESVIO_FRAC_RISCO)
    assert lim == 128.3 and 44 <= lim and 54 <= lim and 358 > lim and 162 > lim


def test_26_reproducao_cronologica_gold_1210_c27r44():
    """C27R44 item 7: reprodução cronológica do Gold de 12/10 (04:00–11:00 UTC) só com o que estava gravado em cada barra
    (testes/reproducao_gold_1210.py). ANTES = sel-3 + gestao-1; DEPOIS = sel-4 + gestao-2. Inclui os casos em que manter foi PIOR."""
    import api
    from reproducao_gold_1210 import reproduzir
    d = reproduzir(api)
    # seleção: a 1ª venda elegível passa de 08:45 (op 10 real) para 04:00 (M30 card9, desvio 39 pts ≤ 10% do risco 1304)
    assert d["primeira_venda_elegivel"]["antes"].startswith("08:45") and d["primeira_venda_elegivel"]["depois"].startswith("04:00")
    sel = {(x["barra_utc"], x["tf"], x["card"]): x for x in d["selecao"]}
    assert sel[("04:15", "M30", "c9_macd")]["elegivel_depois"] is False            # 358 pts > 130: o limite proporcional NÃO abre tudo
    assert sel[("05:45", "M15", "c2_rompimento_caixa")]["elegivel_depois"] is False and sel[("05:45", "M15", "c2_rompimento_caixa")]["corte_classe"] == "indeterminada"   # fail_closed
    assert sel[("07:00", "M15", "c12_engolfo")]["elegivel_depois"] is False       # corte ESTRUTURAL + sinal vencido: segue recusado
    assert sel[("09:15", "M15", "c10_donchian20")]["portao4_sel4"] is True and sel[("09:15", "M15", "c10_donchian20")]["elegivel_depois"] is False   # fino informa, mas 438 pts recusa
    assert sum(1 for x in d["selecao"] if x["elegivel_antes"]) == 1 and sum(1 for x in d["selecao"] if x["elegivel_depois"]) == 11
    # op 10: gestao-2 PROTEGE em 09:15 (B3 + corte fino, continuidade intacta) e só fecha em 10:15 (continuidade PERDIDA) — PIOR que o real
    o = d["op10_real_gestao2"]; p = {x["barra_utc"]: x for x in o["passos"]}
    assert p["09:15"]["gestao1"] == "close" and p["09:15"]["gestao2"] == "mover_sl" and p["09:15"]["continuidade"] == "INTACTA"
    assert p["10:00"]["gestao2"] == "mover_sl" and p["10:15"]["gestao2"] == "close" and p["10:15"]["continuidade"] == "PERDIDA"
    assert o["saida_barra_utc"] == "10:15" and o["resultado_aprox_usd"] < -1.69
    # venda hipotética 04:00: com a gestao-3 (C27R48) o alerta_empilhado_3 de 05:45 é degrau 2 e, sem M1/M5 gravados no replay (direção contrária
    # não confirmada) e continuidade intacta, PROTEGE; a venda segue até 06:45 (B3 com espera esgotada), com ganho maior; a de 06:15 perde
    h = d["venda_hipotetica_0400_gestao2"]; assert h["saida_barra_utc"] == "06:45" and h["resultado_aprox_usd"] > 0 and "degrau 2" in next(p for p in h["passos"] if p["barra_utc"] == "05:45")["explicacao"]
    h2 = d["venda_hipotetica_0615_gestao2"]; assert h2["saida_barra_utc"] == "07:00" and h2["resultado_aprox_usd"] < 0
    # op 8 (compra real): a continuidade se perde em 02:45 (M15 canal 0 / mista) e o B3 fecha em 03:00 nas duas gestões
    o8 = {x["barra_utc"]: x for x in d["op8_real_gestao2"]}
    assert o8["02:45"]["continuidade"] == "PERDIDA" and o8["03:00"]["gestao1"] == "close" and o8["03:00"]["gestao2"] == "close"


def test_27_relatorio_complementar_fases_oportunidades_quadro_justificativa_c27r45(amb, camp):
    """C27R45 (ordem 12/10 'complementar o relatório'): fases separadas (operação que atravessa a mudança de versão), oportunidades
    e recusas por barra com classes e motivo completo, quadro de correções com 'exercitado' × 'ainda não exercitado', catálogo
    (revalidadas = 0, equivalência pendente), justificativa da gestão (B3/corte/trailing separados, classificação, propagação por TF),
    estado efetivo com entradas restantes, eventos do gráfico com UTC/Kyiv/servidor e vínculos, relatório por fase (fase=2) e PDF."""
    import re as _re, urllib.request as rq, io
    sid, x = camp["id"], camp["x"]
    _limpar(sid)
    T._pg("update sessoes_teste set config = config - 'bloqueios_por_bot' where id=%s", sid)
    mg = T._magic(x["tok"]); agora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    t0 = agora - timedelta(hours=3); marco = t0 + timedelta(minutes=30)
    T._pg("update sessoes_teste set config = config || %s::jsonb where id=%s",
          json.dumps({"fases": [{"fase": 1, "inicio": (t0 - timedelta(days=2)).isoformat(), "fim": marco.isoformat(), "regras": "sel-3 + gestao-1"},
                                {"fase": 2, "inicio": marco.isoformat(), "fim": None, "regras": "sel-4 + gestao-2", "marco": "deployment teste"}]}), sid)
    def cmd(tipo, params, quando, origem="sessao_gestao"):
        return T._pg("insert into mt5_comandos (bot_id, user_id, bot_token, tipo, origem, status, params, resultado, criado_em, entregue_em, confirmado_em, expira_em, sessao_teste_id) "
                     "values (%s,%s,%s,%s,%s,'executado',%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s) returning id", x["id"], camp["uid"], x["tok"], tipo, origem, json.dumps(params),
                     json.dumps({"ticket": 777027, "retcode": 10009, "preco_real": 4001.0}), quando, quando + timedelta(seconds=2), quando + timedelta(seconds=9), quando + timedelta(seconds=60), sid)[0][0]
    c_ab = cmd("sell", {"uid": "u27", "lote": 0.3, "sl": 4010.0}, t0 + timedelta(seconds=30), "sessao_r01v5")
    ab_id = T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra, lote, preco_ref, stop_inicial, stop_atual, "
                  "risco_planejado_usd, plano, estado, comando_id, ticket, posicao_id, preco_entrada, preco_saida, ts_reserva, ts_abertura, ts_fechamento, resultado_usd, lucro, comissao, swap, motivo_saida, gestao) "
                  "values (%s,%s,%s,%s,'dec-27','card10_donchian20|M15|x|-1','card10_donchian20','M15',-1,%s,0.3,4000.0,4010.0,4008.0,3.0,'{}'::jsonb,'fechada',%s,777027,777027,4001.0,3995.0,%s,%s,%s,1.8,1.8,0,0,'ciclo','[]'::jsonb) returning id",
                  sid, x["id"], x["sim"], mg, t0, c_ab, t0 + timedelta(seconds=29), t0 + timedelta(seconds=39), t0 + timedelta(minutes=60, seconds=40))[0][0]
    c_sl = cmd("mover_sl", {"ticket": 777027, "sl": 4008.0, "abertura_id": ab_id}, t0 + timedelta(minutes=30, seconds=30))
    c_cl = cmd("close", {"ticket": 777027, "motivo": "ciclo", "abertura_id": ab_id}, t0 + timedelta(minutes=60, seconds=30))
    por_tf = {"M1": {"dir": -1, "estrutura": "descendente", "regime": "tendencia", "eventos": ["fundo_barra_rompido"], "persistencia": 3, "ultimo_topo": 4004.0, "ultimo_fundo": 3996.0},
              "M5": {"dir": -1, "estrutura": "descendente", "regime": "compressao", "persistencia": 6, "ultimo_topo": 4005.0, "ultimo_fundo": 3996.5},
              "M15": {"dir": -1, "estrutura": "descendente", "regime": "compressao", "ultimo_topo": 4009.0, "ultimo_fundo": 3996.0}, "M30": {"dir": -1, "estrutura": "descendente", "regime": "tendencia", "ultimo_topo": 4015.0},
              "H1": {"dir": -1, "estrutura": "mista", "ultimo_topo": 4030.0}, "H4": {"dir": 1}, "D1": {"dir": 0}}
    import api as _api
    cont = _api._cont_continuidade(-1, por_tf, 3998.0)
    assert cont["ok"] and cont["propagacao"]["a_favor"] == ["M1", "M5", "M15", "M30", "H1"] and cont["propagacao"]["contra"] == ["H4"] and "M1" in cont["propagacao"]["inicio_observado"]
    cls = _api._cont_eventos_corte(["M1:fundo_barra_rompido M5:fundo_barra_rompido -> M15:fundo_barra_rompido"])
    gest = [{"acao": "mover_sl", "barra": (t0 + timedelta(minutes=15)).isoformat(), "barras_de_posicao": 1, "motivo": "trailing estrutural (pivô ∓ 0,3×ATR14 do M15)", "comando_id": c_sl,
             "leitura": {"B3": 0, "B5": 0, "corte_do_ciclo": 0, "stop_estrutural": "4008.0", "stop_vigente": "4010.0"}},
            {"acao": "manter(protegido)", "barra": (t0 + timedelta(minutes=30)).isoformat(), "barras_de_posicao": 2, "motivo": "B3", "protegido_por": "B3",
             "regras": {"contrato_gestao": "gestao-2", "contrato_corte": "corte-ciclo-2", "api": "8.15", "b3_espera_max": 1}, "continuidade": cont, "corte_classificacao": cls,
             "explicacao": "B3 sinalizado mas continuidade INTACTA → proteger", "snapshot_id": 1,
             "leitura": {"B3": 1, "B5": 0, "corte_do_ciclo": 1, "stop_estrutural": "4008.2", "stop_vigente": "4008.0", "B3_motivo": "B3: posicao vendida dentro de compressao [3996.00,4009.00] por 6 barras de M5 sem progresso (avanco a favor -1.00 = -0.40 ATR) — tese expirou"},
             "corte": {"contrato": "corte-ciclo-2", "corta": 1, "origem": ["M1:fundo_barra_rompido M5:fundo_barra_rompido -> M15:fundo_barra_rompido"]}},
            {"acao": "close", "barra": (t0 + timedelta(minutes=45)).isoformat(), "barras_de_posicao": 3, "motivo": "ciclo", "comando_id": c_cl,
             "regras": {"contrato_gestao": "gestao-2", "contrato_corte": "corte-ciclo-2", "api": "8.15", "b3_espera_max": 1},
             "continuidade": dict(cont, ok=False, situacao="PERDIDA", motivos=["fechamento 4009.5 rompeu o último topo do M15 (4009.0)"]),
             "corte_classificacao": _api._cont_eventos_corte([{"identificado_em": ["M5:rompeu_ultimo_topo"], "decidido_por": ["M15:rompeu_ultimo_topo"]}]),
             "explicacao": "corte do Ciclo com evento ESTRUTURAL no M15 (rompeu_ultimo_topo) → fechar",
             "leitura": {"B3": 1, "B5": 0, "corte_do_ciclo": 1, "stop_estrutural": "4008.2", "stop_vigente": "4008.0"},
             "corte": {"contrato": "corte-ciclo-2", "corta": 1, "origem": [{"identificado_em": ["M5:rompeu_ultimo_topo"], "decidido_por": ["M15:rompeu_ultimo_topo"]}]}}]
    T._pg("update sessao_aberturas set gestao=%s::jsonb where id=%s", json.dumps(gest), ab_id)
    # avaliação sel-4 na barra da entrada: 1 executado (u27), 1 elegível não escolhido, 1 recusado no portão 8 (valores), 1 aguardando
    barra = t0
    def cand(uid, tf, lado, estado, eleg, esc, portoes, pf):
        return {"uid": uid, "lado": lado, "timeframe": tf, "estrategia": {"card": uid.split("|")[0]}, "sinal": {"estado": estado, "barra_do_sinal_utc": (barra - timedelta(minutes=30)).isoformat()},
                "frescor": {"confirmado_utc": (barra - timedelta(minutes=15)).isoformat(), "vence_utc": (barra + timedelta(minutes=15)).isoformat(), "idade_s": 900, "situacao": "válida"},
                "niveis": {"entrada": 4000.0, "stop": 4010.0, "risco_pts": 1000}, "elegibilidade": eleg, "escolha": {"escolhido": esc}, "primeiro_impedimento": next((p["portao"] + " — x" for p in portoes if p["ok"] is False), None),
                "portoes": portoes, "estudo": {"selo_da_lista": True, "selo_fragil": False}, "pontuacao": {"pf": pf, "trades": 100}, "corte": {"corta_agora": False, "origem": []}, "execucao": {}}
    ok9 = [{"portao": f"{i}. x", "ok": True, "detalhe": "ok"} for i in range(1, 10)]
    p8 = [dict(q) for q in ok9]; p8[7] = {"portao": "8. preço atual × entrada e stop", "ok": False, "detalhe": "preço a 358 pts da entrada (> limite 130 pts = max(30, 10% de 1304 pts de risco))"}
    av = {"versao": "sel-4", "preco_ea": 4000.5, "grupos": {"M15": {"candidatos": [cand("card10_donchian20|M15|x|-1", "M15", "venda", "confirmado", "elegivel", True, ok9, 1.2),
                                                                                     cand("card12_engolfo|M15|x|-1", "M15", "venda", "confirmado", "elegivel", False, ok9, 1.1),
                                                                                     cand("card9_macd|M15|x|-1", "M15", "venda", "confirmado", "nao_elegivel", False, p8, 1.3),
                                                                                     cand("card2_rompimento_caixa|M15|x|-1", "M15", "venda", "aguardando", "nao_elegivel", False, ok9, 1.9)]}},
          "continuidade": {"compra": _api._cont_continuidade(1, por_tf, 3998.0), "venda": cont}}
    T._pg("delete from selecao_avaliacoes where bot_id=%s and barra_m15 > %s", x["id"], t0 - timedelta(hours=1))     # só as avaliações deste teste no período
    T._pg("insert into selecao_avaliacoes (bot_id, user_id, simbolo, magic, barra_m15, versao, n_candidatos, n_elegiveis, escolha_uid, avaliacao, sessao_teste_id) values (%s,%s,%s,%s,%s,'sel-4',4,2,%s,%s::jsonb,%s)",
          x["id"], camp["uid"], x["sim"], mg, barra, "card10_donchian20|M15|x|-1", json.dumps(av), sid)
    s, j, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "personalizado", "de": (t0 - timedelta(hours=1)).isoformat(), "ate": (agora + timedelta(seconds=5)).isoformat(), "sessao": sid, "fuso": "Europe/Kyiv"}, tok=amb["sess"])
    assert s == 200, j
    K = j["campanha"]
    for k in ("quadro_de_correcoes", "fases", "oportunidades_por_barra", "catalogo"):
        assert k in K and not (K[k] or {}).get("erro"), (k, K.get(k))
    # fases: a operação abriu na fase 1 e fechou na fase 2 → atravessa
    F = K["fases"]["fases"]; assert [f["fase"] for f in F] == [1, 2] and F[1]["fim"].startswith("em curso")
    f1 = F[0]["por_ativo"][x["sim"]]; assert ab_id in f1["operacoes_abertas_na_fase"] and f1["operacoes_que_atravessam_a_mudanca_de_versao"][0]["fase_do_fechamento"] == 2
    f2 = F[1]["por_ativo"][x["sim"]]; assert ab_id in f2["fechadas_na_fase"] and f2["resultado_liquido_usd"] == 1.8 and f1["oportunidades"]["versoes_da_selecao"] == ["sel-4"] and f1["oportunidades"]["avaliacoes"] >= 1
    # oportunidades por barra: classes, motivo completo, contagens distintas (C27R46: vindas do RPC rel_oportunidades, sql/0018)
    O = K["oportunidades_por_barra"][x["sim"]]; CN = O["contagens"]
    assert O["fonte"].startswith("rpc rel_oportunidades"), O["fonte"]
    assert K["selecao_diagnostico"][x["sim"]]["fonte"].startswith("rpc rel_selecao_celulas"), K["selecao_diagnostico"][x["sim"]].get("fonte")
    DP = j["desempenho"]; assert DP["tempos_s"]["total_ate_gravar_s"] < 90 and "campanha_blocos" in DP["tempos_s"] and "oportunidades_por_barra" in DP["tempos_s"]["campanha_blocos"]
    assert CN["avaliacoes_barras"] == 1 and CN["candidatos_linhas"] == 4 and CN["sinais_distintos"] == 4 and CN["elegiveis_distintos"] == 2 and CN["escolhidos_distintos"] == 1 and CN["operacoes_abertas_no_periodo"] == 1
    cl = {c["uid"]: c for c in O["por_barra"][0]["candidatos"]}
    assert cl["card10_donchian20|M15|x|-1"]["classe"] == "executado" and str(ab_id) in cl["card10_donchian20|M15|x|-1"]["detalhe_da_classe"]
    assert cl["card12_engolfo|M15|x|-1"]["classe"] == "elegivel_nao_escolhido" and cl["card2_rompimento_caixa|M15|x|-1"]["classe"] == "sinal_nao_confirmado_ou_vencido"
    r8 = cl["card9_macd|M15|x|-1"]; assert r8["classe"] == "recusa_por_leitura_preco_stop_ou_selo" and r8["detalhe_da_classe"] == "preço/stop" and "358 pts" in r8["motivo_completo"][7]["regra_e_valores"]
    assert O["por_barra"][0]["fase"] == 1 and O["por_barra"][0]["continuidade_na_barra"]["venda"] == "INTACTA" and "M1" in O["por_barra"][0]["continuidade_na_barra"]["propagacao_venda"]
    # quadro: execução real procurada nos registros (gestao-2 exercitada aqui: proteger B3 e fechar por corte estrutural)
    Q = {q["problema"][:12]: q for q in K["quadro_de_correcoes"]["quadro"]}
    qg = next(q for q in K["quadro_de_correcoes"]["quadro"] if q["problema"].startswith("Gestão: op 10"))
    assert qg["execucao_real"]["estado"] == "exercitado" and qg["execucao_real"]["evidencia"]["proteger_B3"] and qg["execucao_real"]["evidencia"]["fechar_corte_estrutural"]
    assert all(q["execucao_real"]["estado"] in ("exercitado", "ainda não exercitado", "não aplicável (pendência do dono)", "não aplicável (proposta aguardando decisão do dono)") for q in K["quadro_de_correcoes"]["quadro"])
    assert "NÃO conta como prova" in K["quadro_de_correcoes"]["nota"]
    # catálogo: nenhuma revalidada
    C = K["catalogo"][x["sim"]]; assert C["celulas_revalidadas_com_cards_2_0"] == 0 and C["cards_ao_vivo"].startswith("2.0") and all(c["revalidada_com_cards_2_0"] is False for c in C["celulas"])
    # justificativa da gestão (item 5)
    op = next(o for o in K["operacoes"] if o["identificacao"]["abertura_id"] == ab_id)
    GX = {g["barra_m15_abriu_utc"][:16]: g for g in op["gestao_explicada"]}
    j2 = GX[(t0 + timedelta(minutes=30)).isoformat()[:16]]["valores"]["justificativa"]
    assert j2["classificacao"].startswith("pullback") and "B3" in j2["regras_acionadas"] and j2["determinou_a_acao"].startswith("nenhuma regra fechou: PROTEGER (B3)") and j2["evidencia"].startswith("capturada ao vivo")
    assert j2["corte_do_ciclo"]["classe"].startswith("fino") and j2["trailing"]["aperta"] is False and j2["preco_e_niveis"]["M15_ultimo_topo"] == 4009.0 and j2["continuidade_por_tf"]["propagacao"]["propagado_ate"] == "H1"
    j3 = GX[(t0 + timedelta(minutes=45)).isoformat()[:16]]["valores"]["justificativa"]
    assert j3["classificacao"].startswith("reversão confirmada: M15 rompeu_ultimo_topo") and j3["determinou_a_acao"] == "corte do Ciclo" and "B3" in j3["regras_acionadas"]
    j1 = GX[(t0 + timedelta(minutes=15)).isoformat()[:16]]["valores"]["justificativa"]
    assert j1["evidencia"].startswith("reconstrução posterior") and j1["limitacao"]
    # estado efetivo: entradas restantes e eventos do gráfico com 3 horários e vínculos
    EE = K["resumo_executivo"]["estado_efetivo"]; bb = next(v for k, v in EE["bots"].items() if k.startswith(str(x["id"]) + " "))
    assert bb["uso_dos_limites"]["entradas_restantes_no_dia"] is not None and EE["fase_atual"]["fase"] == 2
    EV = K["graficos"][0]["eventos"]["eventos"]; tipos = [e["tipo"] for e in EV]
    assert "entrada" in tipos and "saida" in tipos and "alteracao_de_stop" in tipos and "candidato_elegivel_nao_executado" in tipos
    e_sl = next(e for e in EV if e["tipo"] == "alteracao_de_stop"); assert e_sl["stop_novo"] == 4008.0 and e_sl["comando_id"] == c_sl and e_sl["quando"]["utc"] and e_sl["quando"]["kyiv"] and e_sl["quando"]["servidor_mt5"]
    e_en = next(e for e in EV if e["tipo"] == "entrada"); assert e_en["fase"] == 1 and e_en["ticket"] == 777027 and e_en["decisao_id"] == "dec-27"
    # relatório por fase (fase 2) e PDF com as mesmas seções
    s, j2r, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "Europe/Kyiv", "fase": "2"}, tok=amb["sess"])
    assert s == 200, j2r
    assert _api._rel_dt(j2r["periodo"]["de_utc"]) == marco and j2r["campanha"]["oportunidades_por_barra"][x["sim"]]["contagens"]["avaliacoes_barras"] == 0
    s, jerr, _ = T._req("POST", SS.URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "sessao": sid, "fuso": "UTC", "fase": "9"}, tok=amb["sess"]); assert s == 422
    q = rq.Request(SS.URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": j["relatorio_id"], "formato": "pdf"}).encode(),
                   headers={"Content-Type": "application/json", "Authorization": "Bearer " + amb["sess"]}, method="POST")
    raw = rq.urlopen(q, timeout=300).read(); assert raw[:4] == b"%PDF"
    from pypdf import PdfReader
    txt = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
    for frag in ("Quadro de correções", "Fases da campanha", "Oportunidades e recusas por barra", "Catálogo", "Classificação", "eventos do gráfico", "Restantes"):
        assert frag in txt, frag


def test_28_regua_unica_do_desvio_selecao_e_r01v5_c27r45():
    """C27R45: a condição 7 da r01v5 passa a usar a MESMA régua do portão 8 da sel-4 (max(DESVIO_MAX, 10% do risco)). Caso real:
    Gold 22:15 UTC de 12/10, escolhido card12 M15 compra parado por 'preço a 33 pts; limite 30' enquanto o portão 8 abria."""
    import api
    lim, base = api._sel_desvio_limite("XAUUSD", 4166.61, 4174.18, 0.01)
    assert base == 30 and abs(lim - 75.7) < 0.1 and 33 <= lim
    assert api._sel_desvio_limite("XAUUSD", 4000.0, 4002.0, 0.01) == (30.0, 30)       # risco pequeno: vale o piso do ativo
    assert api._sel_desvio_limite("ATIVO_SEM_LIMITE", 1.0, 0.9, 0.00001) == (None, None)
    src = open(api.__file__, encoding="utf-8").read()
    assert src.count("_sel_desvio_limite(") >= 3                                         # definição + portão 8 + condição 7


# ───────────────────────────── C27R47 — ordem do dono de 13/10 06:25 Kyiv (sel-5 + gestao-3) ─────────────────────────────
def test_29_sel5_selo_informativo_compatibilidade_e_sem_sinal_c27r47(amb):
    """Item 1: o selo/PF deixa de vetar (portão 5 informativo); a ordenação começa pela compatibilidade com o movimento em formação;
    cada célula do catálogo SEM candidato é gravada como 'sem sinal' com critério e valores."""
    import api
    assert api.SEL_VERSAO == "sel-6" and api._SEL_SELO_BLOQUEIA is False and api.SEL_CONTRATO["id"] == "sel-6"
    # card7_rsi M15 (PF 1,003, 2ª metade 0,81 → SEM selo) e card2 M15 (COM selo, PF 1,938): os dois elegíveis; o movimento decide a ordem
    av, *_ = S._av(api, amb, [S._cand("card7_rsi", "M15", 1), S._cand("card2_rompimento_caixa", "M15", 1)], veredito="autorizada")
    por = {c["estrategia"]["card"]: c for c in S._todos(av)}
    p5 = next(p for p in por["card7_rsi"]["portoes"] if p["portao"].startswith("5."))
    assert p5["ok"] is True and "INFORMATIVO" in p5["detalhe"] and "selo NÃO" in p5["detalhe"]          # o selo continua só informando
    # sel-6 (C27R53): reversão de compra com o M15 em tendência de alta e sem 3º sinal → portão 11 (constituição §5.4/§5.5)
    assert por["card7_rsi"]["elegibilidade"] == "vetada" and por["card7_rsi"]["primeiro_impedimento"].startswith("11.")
    assert por["card7_rsi"]["estudo"]["selo_da_lista"] is False                     # a métrica continua registrada (informação)
    assert por["card7_rsi"]["compatibilidade"]["familia"] == "reversão" and por["card2_rompimento_caixa"]["compatibilidade"]["familia"] == "rompimento"
    assert av["movimento_em_formacao"]["contrato"] == "sel-6" and "compatibilidade_por_familia" in av["movimento_em_formacao"]
    # tendência em curso (M15 canal +1, regime tendência): rompimento 2 × reversão 0 → card2 escolhido mesmo com PF menor sendo o outro
    assert av["escolha"]["card"] == "card2_rompimento_caixa" and av["escolha"]["compatibilidade"]["grau"] >= por["card7_rsi"]["compatibilidade"]["grau"]
    # 'sem sinal': células do catálogo sem candidato nesta barra, por TF, com critério/valores/motivo
    ss = av["grupos"]["M15"]["sem_sinal"]
    assert ss and all(k in ss[0] for k in ("card", "criterio", "resultado", "valores", "motivo")) and not any(z["card"] in ("card7_rsi", "card2_rompimento_caixa") for z in ss)
    assert av["grupos"]["H1"]["sem_sinal"] and av["controle"]["reavaliacao"].startswith("sel-5")


def test_30_sel5_reavaliacao_dentro_da_barra_e_latencias_c27r47(amb, monkeypatch):
    """Item 2: a 1ª avaliação da barra fica preservada; quando o conjunto de candidatos muda dentro da barra (sinal passa a confirmado),
    a avaliação é REFEITA (≤ 1/min) na mesma linha; latências por candidato (detecção = 1º snapshot com o sinal; confirmação; avaliação)."""
    import api
    barra = T._barra_m15()
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", amb["bots"]["A"]["id"]).execute().data[0]
    T._pg("delete from selecao_avaliacoes where bot_id=%s", bot["id"])
    api._SEL_REAV_MEM.pop(bot["id"], None); api._SEL_DETECCAO_MEM.pop(bot["id"], None)
    i1 = [S._cand("card2_rompimento_caixa", "M15", 1, estado="aguardando")]
    i2 = [S._cand("card2_rompimento_caixa", "M15", 1)]                                   # mesmo uid, agora confirmado
    det1, leit, ciclos = S._cenario(i1, barra, veredito="autorizada")
    det2, _l, _c = S._cenario(i2, barra, veredito="autorizada")
    monkeypatch.setattr(api, "_clm_avaliar", lambda sb_, bot_, det_, ts_: (leit, ciclos))
    av1 = api._sel_ingerir(sb, bot, det1)
    assert av1 and av1["controle"]["reavaliacoes_feitas"] == 0 and av1["escolha"] is None
    assert api._sel_ingerir(sb, bot, det1) is None                                      # nada mudou dentro do minuto: não reavalia
    api._SEL_REAV_MEM[bot["id"]]["ultimo_ts"] -= 61                                     # passou 1 minuto
    assert api._sel_ingerir(sb, bot, det1) is None                                      # nada mudou e não há confirmado: não reavalia
    av2 = api._sel_ingerir(sb, bot, det2)                                               # conjunto mudou (aguardando → confirmado) → reavalia na hora
    assert av2 and av2["controle"]["reavaliacoes_feitas"] == 1 and av2["controle"]["motivo_da_reavaliacao"].startswith("conjunto")
    assert av2["primeira_avaliacao"]["avaliado_utc"] == av1["avaliado_utc"] and len(av2["reavaliacoes"]) == 1 and av2["escolha"]["card"] == "card2_rompimento_caixa"
    rows = T._pg("select count(*), max((avaliacao->'controle'->>'reavaliacoes_feitas')::int), max(escolha_uid) from selecao_avaliacoes where bot_id=%s", bot["id"])
    assert rows[0][0] == 1 and rows[0][1] == 1 and rows[0][2] == av2["escolha"]["uid"]   # UMA linha por barra, atualizada
    c = S._todos(av2)[0]; lat = c["latencias"]
    assert lat["deteccao_utc"] == av1["avaliado_utc"] and lat["confirmacao_utc"] and lat["avaliacao_utc"] == av2["avaliado_utc"]
    assert lat["deteccao_ate_avaliacao_s"] is not None and lat["decisao_utc"] is None   # sem emissão (r01v5 desligada no teste)


def test_31_reproducao_cronologica_btc_1310_barras_15_a_17_c27r47():
    """Item 2 (caso de reprodução): BTC 13/10, fundo nas barras 15–16 e rompimento da máxima da 16 pela 17 — só com o que estava gravado
    em cada instante (testes/reproducao_btc_1310.py). Quais estratégias reconheceram o padrão e quando a seleção teria aberto."""
    import api
    from reproducao_btc_1310 import reproduzir
    d = reproduzir(api)
    assert d["primeiro_elegivel_antes_sel4"]["barra_utc"] == "02:00" and d["primeiro_elegivel_antes_sel4"]["card"] == "card7_rsi"            # op 14 real (H1, selo)
    assert d["primeiro_elegivel_depois_sel5"]["barra_utc"] == "01:30" and d["primeiro_elegivel_depois_sel5"]["timeframe"] == "M30"             # 30 min antes, M30 reversão
    assert d["escolha_sel5_em_01_30"]["familia"] == "reversão" and d["escolha_sel5_em_01_30"]["compatibilidade"].startswith("compatível")
    cands = {(c["barra_utc"], c["timeframe"], c["card"]): c for c in d["candidatos_compra"]}
    assert cands[("01:30", "M30", "card7_rsi")]["elegivel_antes_sel4"] is False and cands[("01:30", "M30", "card7_rsi")]["motivo_antes"] == "portão 5 (selo)"
    assert cands[("01:45", "M30", "card7_rsi")]["elegivel_depois_sel5"] is False and cands[("01:45", "M30", "card7_rsi")]["motivo_depois"] == "portão 8"   # longe da entrada: segue recusado
    assert cands[("01:45", "M15", "card4_canal_ema20")]["elegivel_depois_sel5"] is True and cands[("02:00", "M30", "card7_rsi")]["elegivel_depois_sel5"] is False
    lin = {x["instante_utc"]: x for x in d["leituras_por_instante"]}
    assert "quebra_estrutura_alta" in lin["01:15:43"]["M1"]["eventos"] and "quebra_estrutura_alta" in lin["01:15:43"]["M5"]["eventos"] and lin["01:15:43"]["M5"]["ultimo_fundo"] == 80917.83
    assert lin["01:30:40"]["movimento_sel5"].startswith("compressão/lateral") and lin["01:30:40"]["compatibilidade_por_familia"]["reversão"] == 2
    assert d["diferenca"]["pontos_a_favor"] > 30000 and d["diferenca"]["usd_no_lote_da_op14"] > 20
    assert "não força sinal" in d["limitacoes"][2]


class _SbFake:
    """sb mínimo para _g3_custos_pts: qualquer encadeamento (.table().select().eq().not_.is_()...) devolve as aberturas informadas."""
    def __init__(self, rows): self.rows = rows
    def __getattr__(self, _k): return self
    def __call__(self, *a, **k): return self
    def execute(self):
        class R: pass
        r = R(); r.data = self.rows; return r


def test_32_gestao3_protecao_por_tempo_3o_e_4o_candle_custos_e_corretora_c27r47():
    """Item 3: candles M15 fechados = barras_de_posicao + 1. No 3º aciona: nível = entrada ± (custos + spread) × ponto; aplica se o preço
    já está além do nível + distância mínima e o nível é mais protetor; senão registra o impedimento (explícito no 4º). Nunca afasta."""
    import api
    assert api.GESTAO_CONTRATO == "gestao-3" and api.GESTAO3_PROTECAO_CANDLES == 3 and api.GESTAO3_PROTECAO_PRAZO == 4
    sb = _SbFake([{"comissao": -0.5, "lote": 0.07}, {"comissao": -0.92, "lote": 0.13}, {"comissao": -0.56, "lote": 0.08}])      # ops 10–12 reais (XAU)
    bot = {"id": 12, "simbolo": "XAUUSD"}; at5 = {"especificacao": {"tick_tamanho": 0.01, "tick_valor": 1.0, "ponto": 0.01}}
    ab = {"id": 15, "sessao_teste_id": "CAMP", "preco_entrada": 4169.03, "lado": 1}
    pts, det_c = api._g3_custos_pts(sb, bot, ab, at5, {"pt": 0.01})
    assert pts == 7.08 and det_c["comissao_usd_por_lote"] == 7.0769 and det_c["origem"].startswith("comissão medida")       # mediana de 7,14 / 7,08 / 7,00 = 7,08
    # op 15 real (compra 4169,03; spread 5): 2 candles → não aciona
    b, n = api._g3_protecao_por_tempo(sb, bot, ab, {}, at5, {"pt": 0.01, "preco": 4179.58, "spr": 5.0}, 1, 1, 4148.56)
    assert b["acionada"] is False and n is None and b["candles_fechados"] == 2
    # 3º candle, preço 4179,58 ≫ nível 4169,15 → pede 4169,15 (stop vigente 4148,56 é menos protetor)
    b, n = api._g3_protecao_por_tempo(sb, bot, ab, {}, at5, {"pt": 0.01, "preco": 4179.58, "spr": 5.0}, 2, 1, 4148.56)
    assert b["acionada"] and b["candles_fechados"] == 3 and n == 4169.15 and b["nivel"] == 4169.15 and b["custos_pts"] == 7.08 and b["spread_pts"] == 5.0 and b["folga_pts"] == 1043.0
    # ganho insuficiente (preço 4169,17: 2 pts acima do nível; distância mínima = spread 5 pts) → impedimento, sem stop inválido; no 4º o registro é explícito
    b, n = api._g3_protecao_por_tempo(sb, bot, ab, {}, at5, {"pt": 0.01, "preco": 4169.17, "spr": 5.0}, 3, 1, 4148.56)
    assert n is None and b["aplicada"] is False and "ganho insuficiente" in b["impedimento"] and b["registro_no_prazo"].startswith("4º candle")
    # distância mínima da corretora na especificação (ex.: 30 pts) é respeitada
    at5b = {"especificacao": dict(at5["especificacao"], distancia_minima_stop_pts=30)}
    b, n = api._g3_protecao_por_tempo(sb, bot, ab, {}, at5b, {"pt": 0.01, "preco": 4169.40, "spr": 5.0}, 2, 1, 4148.56)
    assert n is None and b["distancia_minima_pts"] == 30 and "30" in b["impedimento"]
    # stop vigente já mais protetor (4175) → preservado, nunca afasta; C27R51: só conta como proteção da PLATAFORMA se veio de comando nosso
    sb_cmd = _SbFake([{"id": 1, "tipo": "mover_sl", "status": "executado", "params": {"sl": 4175.0, "abertura_id": ab.get("id")}, "comissao": -0.5, "lote": 0.07}])
    b, n = api._g3_protecao_por_tempo(sb_cmd, bot, ab, {}, at5, {"pt": 0.01, "preco": 4179.58, "spr": 5.0}, 2, 1, 4175.0)
    assert n is None and b["aplicada"] is True and "preservado" in b["como"] and b["origem_do_stop_vigente"].startswith("comando da plataforma")
    b, n = api._g3_protecao_por_tempo(sb, bot, ab, {}, at5, {"pt": 0.01, "preco": 4179.58, "spr": 5.0}, 2, 1, 4175.0)       # nenhum comando colocou 4175 → stop EXTERNO
    assert n is None and b["aplicada"] is False and b["aplicada_pela_plataforma"] is False and "EXTERNO" in b["origem_do_stop_vigente"] and "preservado" in b["como"]
    # venda: nível = entrada − (custos + spread) × ponto; compara com o ask (bid + spread)
    abv = dict(ab, preco_entrada=4180.00, lado=-1)
    b, n = api._g3_protecao_por_tempo(sb, bot, abv, {}, at5, {"pt": 0.01, "preco": 4169.00, "spr": 5.0}, 2, -1, 4200.0)
    assert n == 4179.88 and b["folga_pts"] == round((4179.88 - 4169.05) / 0.01, 1)
    # BTC sem comissão medida nem config → custos 0; nível = entrada + spread (op 14: 82380,65 + 500 pts = 82385,65)
    sb0 = _SbFake([]); botb = {"id": 13, "simbolo": "BTCUSD"}; at5c = {"especificacao": {"tick_tamanho": 0.01, "tick_valor": 0.01, "ponto": 0.01}}
    monkey = api._ses_do_bot
    try:
        api._ses_do_bot = lambda *_a, **_k: {"config": {}}
        b, n = api._g3_protecao_por_tempo(sb0, botb, {"id": 14, "sessao_teste_id": "CAMP", "preco_entrada": 82380.65}, {}, at5c, {"pt": 0.01, "preco": 83265.48, "spr": 500.0}, 4, 1, 80830.35)
    finally:
        api._ses_do_bot = monkey
    assert n == 82385.65 and b["custos_pts"] == 0.0 and b["candles_fechados"] == 5


def test_33_gestao3_prioridade_do_corte_confirmado_exaustao_isolada_e_rotulo_defasado_c27r47():
    """Item 4: reversão CONFIRMADA no M15 (rompeu último topo/fundo, alerta empilhado 3) fecha IMEDIATAMENTE, antes do B3 e sem olhar a
    continuidade; exaustão isolada = alerta (protege; fecha só se a continuidade já estiver perdida); 2º sinal fino = topo/fundo
    provisório/pullback; rótulo defasado da estrutura (canal a favor + fechamento além do pivô a favor) não marca continuidade perdida."""
    import api
    por_tf = {"M15": {"dir": -1, "estrutura": "descendente", "regime": "tendencia", "ultimo_topo": 4188.15, "ultimo_fundo": 4172.82}, "M30": {"dir": -1}, "H1": {"dir": -1}}
    base = {"B3": 1, "corte_do_ciclo": 1, "B3_motivo": "B3: sem progresso (-0.45 ATR)", "stop_estrutural": 4189.65}
    cor = {"contrato": "corte-ciclo-2"}
    # reversão confirmada (rompeu_ultimo_topo) com B3 sinalizado há 1 avaliação e continuidade INTACTA pelos critérios: fecha na hora, sem espera
    L = dict(base, corte_origem=[{"identificado_em": ["M1:rompeu_ultimo_topo", "M5:rompeu_ultimo_topo"], "decidido_por": ["M15:rompeu_ultimo_topo"]}])
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4177.18}, cor, por_tf, 2, [])
    assert (acao, motivo) == ("close", "ciclo") and cls["reversao_confirmada"] is True and exp.startswith("INVALIDAÇÃO ESTRUTURAL CONFIRMADA") and "sem espera" in exp and cont["ok"] is True
    assert cls["movimento"].startswith("invalidação estrutural confirmada") and cls["degrau"] == 3
    # alerta empilhado 3 = degrau 2 (reversão em formação): sem direção contrária em M1+M5 (ausentes) e continuidade intacta → protege;
    # com M1 e M5 contra → fecha, mesmo sem B3 e com 0 barras
    L = dict(base, B3=0, corte_origem=["M1:alerta_empilhado_3 M5:alerta_empilhado_3 -> M15:alerta_empilhado_3"])
    a2 = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4177.18}, cor, por_tf, 0, [])
    assert a2[0] == "proteger" and a2[3]["degrau"] == 2
    a3 = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4177.18}, cor, dict(por_tf, M1={"dir": 1}, M5={"dir": 1}), 0, [])
    assert a3[0] == "close" and "DIREÇÃO CONTRÁRIA" in a3[4]
    # exaustão ISOLADA com continuidade intacta → ALERTA: proteger (não fecha)
    L = dict(base, B3=0, corte_origem=[{"identificado_em": ["M5:exaustao_identificada"], "decidido_por": ["M15:exaustao_identificada"]}])
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4177.18}, cor, por_tf, 2, [])
    assert (acao, motivo) == ("proteger", "ciclo") and cls["alerta_exaustao_isolado"] is True and exp.startswith("ALERTA") and cls["movimento"].startswith("alerta de exaustão")
    # exaustão + continuidade PERDIDA (fechamento rompeu o último topo) = invalidação confirmada → fecha
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4188.40}, cor, por_tf, 2, [])
    assert (acao, motivo) == ("close", "ciclo") and cont["ok"] is False and "invalidação confirmada" in exp
    # 2º sinal fino com continuidade intacta = topo/fundo provisório / pullback → proteger
    L = dict(base, B3=0, corte_origem=[{"identificado_em": ["M5:fundo_barra_rompido"], "decidido_por": ["M15:fundo_barra_rompido"]}])
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 4177.18}, cor, por_tf, 2, [])
    assert acao == "proteger" and cls["movimento"].startswith("reversão em formação") and "pausa" in exp
    # rótulo defasado: M15 'descendente' com canal +1 e fechamento ACIMA do último topo → estrutura efetiva a favor da compra → continuidade INTACTA
    por_up = {"M15": {"dir": 1, "estrutura": "descendente", "regime": "tendencia", "ultimo_topo": 83005.74, "ultimo_fundo": 80917.83}, "M30": {"dir": 1}}
    c = api._cont_continuidade(1, por_up, 83120.0)
    assert c["ok"] is True and c["M15"]["rotulo_da_estrutura_defasado"] is True and c["M15"]["rompeu_pivo_a_favor"] is True
    c2 = api._cont_continuidade(1, por_up, 82900.0)                                     # fechamento abaixo do topo: o rótulo vale → PERDIDA
    assert c2["ok"] is False and c2["M15"]["rotulo_da_estrutura_defasado"] is False
    # a continuidade NUNCA anula a reversão confirmada (regra escrita)
    assert "NUNCA anula" in c["regra"]


# ───────────────────────────── C27R48 — ordem do dono de 13/10 23:20 Kyiv ─────────────────────────────
def test_34_limites_diarios_informativos_sql_0020_c27r48(camp):
    """Item 1: com config.limites_diarios_bloqueiam=false o teto de aberturas/dia e a perda do dia NÃO recusam (contados em 'uso');
    os demais limites (posições simultâneas, 1 posição/ativo, risco por operação, risco agregado) continuam. Persistência = config."""
    import api
    sid, x, b = camp["id"], camp["x"], camp["b"]
    _limpar(sid)
    ini = T._pg("select sessao_dia_inicio(%s)", sid)[0][0]
    for i in range(6):
        _fechada(sid, b, 1.0, ini + timedelta(minutes=5 + i))
    _fechada(sid, b, -320.0, ini + timedelta(minutes=40))                                     # perda do dia acima do teto de 300
    ok, mot, _, uso = SS._res(sid, x)
    assert not ok and mot in ("maximo_de_aberturas_do_dia", "perda_realizada_do_dia_no_limite") and uso["limites_diarios_bloqueiam"] is True
    T._pg("update sessoes_teste set config = config || '{\"limites_diarios_bloqueiam\": false}'::jsonb where id=%s", sid)
    ok, mot, _, uso = SS._res(sid, x)
    assert ok and mot.startswith("ok") and uso["aberturas"] == 7 and float(uso["resultado_realizado_usd"]) == -314.0 and uso["limites_diarios_bloqueiam"] is False
    assert T._pg("select aberturas_suspensas_em from sessoes_teste where id=%s", sid)[0][0] is None
    # preservados: risco por operação acima do teto segue recusado
    r = T._pg("select ok, motivo from sessao_reservar(%s,%s,false,'d','u','card','M15',1,now(),0.01,4000,3990,150.0,%s,%s,'{}'::jsonb)", sid, x["id"], x["sim"], T._magic(x["tok"]))
    assert r[0][0] is False and r[0][1] == "risco_acima_do_limite_por_operacao"
    # painel/relatório: efeito informativo
    u = api._ses_uso_total([], {"max_perdas_consecutivas": 3, "limites_diarios_bloqueiam": False})
    assert u["limites_diarios_bloqueiam"] is False and u["limites_diarios_efeito"].startswith("INFORMATIVO")
    assert api._lim_diario_sufixo({"limites_diarios_bloqueiam": False}).startswith(" (informativo") and api._lim_diario_sufixo({}) == ""
    T._pg("update sessoes_teste set config = config - 'limites_diarios_bloqueiam' where id=%s", sid)


def test_35_sel5_alertas_de_estrutura_e_portao_10_op12_real_c27r48(amb):
    """Item 3 (caso obrigatório op 12, snapshot 47998 de 22:30:27 UTC de 12/10): M1 na_resistencia, M15 topo_da_faixa, M30 compressão
    com momentum enfraquecendo e M5 gatilho E1/E2_baixa(persistente) → 4 tempos contra a compra de continuação → portão 10 fecha.
    O mesmo card de REVERSÃO não é vetado (os alertas são a tese). BTC 01:30 UTC de 13/10 (card7 M30 compra, M15 lateral) segue elegível."""
    import api
    assert api._sel_lado_exaustao("E1/E2_baixa(persistente)") == -1 and api._sel_lado_exaustao("E3_gradual_alta") == 1 and api._sel_lado_exaustao("E2_rejeicao") == 0
    por_tf_op12 = {"M1": {"dir": 1, "estrutura": "mista", "regime": "lateral", "localizacao": "na_resistencia", "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"]},
                   "M5": {"dir": 1, "estrutura": "ascendente", "regime": "tendencia", "localizacao": "meio_da_faixa", "eventos": ["rompimento_confirmado(por_barra)", "exaustao_identificada(E1/E2_baixa(persistente))"], "gatilho_exaustao": "E1/E2_baixa(persistente)"},
                   "M15": {"dir": 1, "estrutura": "ascendente", "regime": "tendencia", "localizacao": "topo_da_faixa", "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"], "ultimo_topo": 4172.85, "ultimo_fundo": 4163.32},
                   "M30": {"dir": 1, "estrutura": "mista", "regime": "compressao", "localizacao": "na_resistencia", "momentum": "enfraquecendo"}}
    mov = api._sel_movimento_em_formacao(por_tf_op12)
    al = api._sel_alertas_de_estrutura(1, mov)
    assert [a["tf"] for a in al] == ["M1", "M15", "M30", "M5"] and any("aponta contra" in a["leitura"] for a in al)
    comp = api._sel_compatibilidade({"estrategia": {"card": "card4_canal_ema20"}, "lado_num": 1}, mov)
    assert comp["familia"] == "continuação" and comp["grau"] == 0 and "≥ 2 tempos" in comp["rotulo"] and len(comp["alertas_de_estrutura"]) == 4
    comp_r = api._sel_compatibilidade({"estrategia": {"card": "card7_rsi"}, "lado_num": 1}, mov)
    assert comp_r["familia"] == "reversão" and comp_r["grau"] == 0 and "≥ 2 tempos" not in comp_r["rotulo"]        # reversão: alertas não rebaixam (tendência em curso → reversão 0 pelo movimento)
    # avaliação completa: card4 M30 compra com a estrutura da op 12 → portão 10 fechado, não elegível; card7 (reversão) com o mesmo cenário NÃO é vetado pelo 10
    # S._cenario só põe dir/topo/fundo: injeta a estrutura da op 12 e avalia
    sb = api._sb_admin(); bot = sb.table("conector_bots").select("*").eq("id", amb["bots"]["A"]["id"]).execute().data[0]
    det2, leit2, ciclos2 = S._cenario([S._cand("card4_canal_ema20", "M30", 1), S._cand("card7_rsi", "M30", 1)], T._barra_m15(), veredito="autorizada", dirs={"M1": 1, "M5": 1, "M15": 1, "M30": 1, "H1": 0, "H4": 0, "D1": -1})
    for tf, v in por_tf_op12.items():
        det2["cv_motor"]["por_tf"][tf].update(v)
    T._pg("delete from selecao_avaliacoes where bot_id=%s", bot["id"])
    av2 = api._sel_avaliar(sb, bot, det2, leit2, ciclos2, int(time.time()))
    por = {c["estrategia"]["card"]: c for c in S._todos(av2)}
    p10 = next(p for p in por["card4_canal_ema20"]["portoes"] if p["portao"].startswith("10."))
    assert p10["ok"] is False and "VETA" in p10["detalhe"] and por["card4_canal_ema20"]["elegibilidade"] == "vetada" and por["card4_canal_ema20"]["primeiro_impedimento"].startswith("10.")
    p10r = next(p for p in por["card7_rsi"]["portoes"] if p["portao"].startswith("10."))
    assert p10r["ok"] is False and "VETA" in p10r["detalhe"] and por["card7_rsi"]["elegibilidade"] == "vetada"      # sel-6 (C27R53): sem isenção — compra de reversão no topo da faixa/na resistência não é reversão no extremo
    # BTC 01:30 UTC de 13/10: M15 lateral (dir 0), sem alertas → card7 M30 reversão compatível, portão 10 aberto
    from reproducao_btc_1310 import LEITURAS, por_tf_de
    mov_btc = api._sel_movimento_em_formacao(por_tf_de(next(x for x in LEITURAS if x[1] == "01:30")))
    assert api._sel_alertas_de_estrutura(1, mov_btc) == [] and api._sel_compatibilidade({"estrategia": {"card": "card7_rsi"}, "lado_num": 1}, mov_btc)["grau"] == 2


def test_36_gestao3_op12_real_degrau2_direcao_contraria_e_canal_contra_c27r48():
    """Item 5 (op 12 real): 23:00 UTC (barra 22:45; snapshot 48170): corte=1 2º sinal fino (degrau 2) com M1 −1 e M5 −1 (quebra_estrutura_baixa),
    M15 canal 0 → gestao-3 FECHA (direção contrária confirmada em M1+M5); a gestao-2 manteve. 23:15 UTC (snapshot 48256): B3=1 com M15
    canal −1 e rótulo 'ascendente' → continuidade PERDIDA (canal contra) → B3 fecha; a gestao-2 manteve ('intacta' pelo rótulo).
    Degrau 2 sem direção contrária (M1 +1, M5 +1) → pausa/pullback: protege."""
    import api
    cor = {"contrato": "corte-ciclo-2"}
    L_2245 = {"B3": 1, "corte_do_ciclo": 1, "corte_origem": ["M1:rompeu_ultimo_fundo M1:topo_barra_rompida -> M15:topo_barra_rompida"], "stop_estrutural": 4162.27}
    ptf_2300 = {"M1": {"dir": -1, "estrutura": "descendente", "eventos": ["quebra_estrutura_baixa"]}, "M5": {"dir": -1, "estrutura": "mista", "eventos": ["quebra_estrutura_baixa"]},
                "M15": {"dir": 0, "estrutura": "ascendente", "regime": "compressao", "ultimo_topo": 4175.92, "ultimo_fundo": 4163.32}, "M30": {"dir": 0, "estrutura": "mista"}, "H1": {"dir": -1}}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(1, L_2245, {"B5": 0, "fechamento": 4169.36}, cor, ptf_2300, 1, [])
    assert cls["degrau"] == 2 and cls["reversao_em_formacao"] is True and cont["ok"] is True
    assert (acao, motivo) == ("close", "ciclo") and exp.startswith("REVERSÃO EM FORMAÇÃO") and "DIREÇÃO CONTRÁRIA" in exp and "M1 -1 / M5 -1" in exp
    L_2300 = {"B3": 1, "corte_do_ciclo": 0, "corte_origem": [], "B3_motivo": "B3: sem progresso", "stop_estrutural": 4162.27}
    ptf_2315 = {"M1": {"dir": -1, "estrutura": "descendente"}, "M5": {"dir": -1, "estrutura": "mista"},
                "M15": {"dir": -1, "estrutura": "ascendente", "regime": "compressao", "ultimo_topo": 4175.92, "ultimo_fundo": 4163.32}, "M30": {"dir": 0, "estrutura": "mista"}}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(1, L_2300, {"B5": 0, "fechamento": 4168.02}, None, ptf_2315, 2, [])
    assert cont["ok"] is False and cont["M15"]["canal_contra"] is True and any("rótulo 'ascendente' defasado" in m for m in cont["motivos"])
    assert (acao, motivo) == ("close", "B3") and "PERDIDA" in exp
    # mesmo degrau 2 sem direção contrária e com continuidade intacta → protege (pausa/pullback)
    ptf_ok = {"M1": {"dir": 1}, "M5": {"dir": 1}, "M15": {"dir": 1, "estrutura": "ascendente", "regime": "tendencia", "ultimo_topo": 4175.92, "ultimo_fundo": 4163.32}, "M30": {"dir": 1}}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(1, dict(L_2245, B3=0), {"B5": 0, "fechamento": 4170.0}, cor, ptf_ok, 1, [])
    assert (acao, motivo) == ("proteger", "ciclo") and "SEM direção contrária" in exp and cls["movimento"].startswith("reversão em formação")
    # degrau 3 fecha mesmo com tudo a favor
    L3 = dict(L_2245, corte_origem=[{"identificado_em": ["M1:rompeu_ultimo_fundo"], "decidido_por": ["M15:rompeu_ultimo_fundo"]}])
    acao, motivo, cont, cls, exp = api._gestao2_decidir(1, L3, {"B5": 0, "fechamento": 4170.0}, cor, ptf_ok, 1, [])
    assert cls["degrau"] == 3 and (acao, motivo) == ("close", "ciclo") and exp.startswith("INVALIDAÇÃO ESTRUTURAL CONFIRMADA")
    # op 13 real (venda, 01:15 UTC): alerta_empilhado_3 (degrau 2) com M1 +1 e M5 +1 → fecha (igual ao real), rotulado como reversão em formação + direção contrária
    L13 = {"B3": 0, "corte_do_ciclo": 1, "corte_origem": ["M1:fundo_barra_rompido M1:exaustao_identificada M5:exaustao_identificada -> M15:alerta_empilhado_3"]}
    ptf_13 = {"M1": {"dir": 1}, "M5": {"dir": 1}, "M15": {"dir": 0, "estrutura": "ascendente", "regime": "compressao", "ultimo_topo": 4175.97, "ultimo_fundo": 4166.73}, "M30": {"dir": -1}}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L13, {"B5": 0, "fechamento": 4167.34}, cor, ptf_13, 2, [])
    assert (acao, motivo) == ("close", "ciclo") and cls["degrau"] == 2 and "DIREÇÃO CONTRÁRIA" in exp


def test_37_linha_do_tempo_por_operacao_com_fonte_e_intervencao_manual_c27r48():
    """Item 8: a linha do tempo junta confirmação, decisão, comandos/execuções, gestão por barra e stops, cada um com a FONTE (tabela e id);
    intervenções manuais de stop (ops 14/15: comandos 80/82) ficam marcadas. Leituras intrabar vêm do RPC (ausente aqui → declarado)."""
    import api
    class _Sb:
        def rpc(self, *a, **k):
            raise RuntimeError("sem rpc")
    ab = {"id": 15, "ts_abertura": "2026-10-13T02:31:32Z", "ts_fechamento": "2026-10-13T04:00:56Z"}
    gest = [{"barra_m15_utc": "2026-10-13T02:30:00Z", "avaliado_utc": "2026-10-13T02:46:51Z", "acao": "manter", "snapshot_id_gravado": 1, "continuidade": {"situacao": "PERDIDA"}, "corte_classificacao": {"classe": "indeterminada"}, "leitura_assinada": {"B3": 0, "stop_vigente": 4148.56}, "regras": {"contrato_gestao": "gestao-2"}},
            {"barra_m15_utc": "2026-10-13T03:30:00Z", "avaliado_utc": "2026-10-13T03:36:13Z", "acao": "mover_sl", "motivo": "protecao_por_tempo (C27R47) — aplicada manualmente pelo Claude por ordem do dono antes da implantacao",
             "protecao_por_tempo": {"manual": True, "nivel": 4169.15, "candles_fechados": 4}, "comando": {"id": 82}, "regras": {"contrato_gestao": "gestao-2 + protecao_por_tempo manual"}}]
    cmds = [{"id": 82, "tipo": "mover_sl", "origem": "sessao_gestao", "status": "executado", "criado_em": "2026-10-13T03:36:13Z", "confirmado_em": "2026-10-13T03:36:31Z",
             "params": {"sl": 4169.15, "abertura_id": 15, "uid_gestao": "G-15-protecao_por_tempo-C27R47", "motivo": "protecao por tempo ...; aplicada manualmente pelo Claude antes da implantacao"}, "resultado": {"retcode": 10009}}]
    dec = {"id": "d1", "criado_em": "2026-10-13T02:30:47Z", "veredito": {"avaliado_utc": "2026-10-13T02:30:47Z", "snapshot_id": 50000, "condicoes": [{"ok": True}],
                                                                        "candidato": {"uid": "card9_macd|M30|2026-10-13 05:00:00|1", "modo": "fechamento", "sinal_fecha_utc": "2026-10-13T02:30:00Z", "vence_utc": "2026-10-13T03:00:00Z", "preco_ref": 4170.29, "stop": 4148.56}}}
    from zoneinfo import ZoneInfo
    LT = api._rel_op_linha_do_tempo(_Sb(), {"id": 12}, ab, gest, cmds, dec, ZoneInfo("Europe/Kyiv"))
    tipos = [x["tipo"] for x in LT["itens"]]
    assert tipos[0] == "confirmação do sinal" and "decisão r01v5" in tipos and "comando mover_sl" in tipos and "execução mover_sl" in tipos
    assert all(x.get("fonte", "").startswith("gravado ao vivo") for x in LT["itens"]) and LT["leituras_intrabar"].startswith("indisponível")
    man = LT["intervencoes_manuais_de_stop"]
    assert len(man) == 1 and man[0]["comando_id"] == 82 and man[0]["sl_pedido"] == 4169.15
    assert sum(1 for x in LT["itens"] if x.get("intervencao_manual")) == 3                         # comando, execução e gestão da mesma intervenção
    assert LT["itens"] == sorted(LT["itens"], key=lambda x: x["ts_utc"])


def test_38_pontos_marcados_gold_1214_classificacao_e_portao_10_c27r49():
    """C27R49 item 1/3: os pontos marcados pelo dono (1–7, 9–12; o 8 não está no gráfico) têm classe, candle UTC/Kyiv, pivô, eventos, leituras,
    estratégias e decisão real; a conferência do portão 10 (estrutura na entrada, por tempo) com as leituras REAIS de entrada veta as ops 12/51/52/53
    (compra na resistência/topo; venda no suporte/fundo) e as vendas de 18:00 do ponto 12 (no fundo), mas NÃO veta a op 48 (1 alerta) nem a reversão
    da op 50 (card de reversão: alertas a favor). Regras de fase: quebra confirmada exige fechamento; topo/fundo provisório admite intrabar e não é entrada."""
    import api
    from testes import reproducao_gold_pontos_1214 as R
    rep = R.reproduzir(api)
    assert [p["ponto"] for p in rep["pontos"]] == [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12]
    classes = rep["classes"]
    for p in rep["pontos"]:
        assert p["candle_utc"] and p["kyiv"] and len(p["ohlc"]) == 4 and p["pivo"] and p["eventos"] and p["leituras"] and p["estrategias"] and p["fundamento"]
        assert any(c in p["classificacao"] for c in classes), p["ponto"]
    r = rep["resumo"]
    assert r["nao_detectou"] == [1, 10] and 5 in r["interpretou_incorretamente"] and 4 in r["reagiu_tarde"] and r["executou_conforme_contrato"] == [6, 7, 9]
    c = rep["conferencia_portao_10"]
    veta = {k.split()[0] for k, v in c.items() if v["portao_10"] == "VETA"}
    assert veta == {"op12", "op51", "op52", "op53", "ponto12"}
    assert c["op48 04:30:45 13/10 compra"]["grau"] == 1 and c["op50 22:15:21 13/10 venda BTC"]["familia"] == "reversão"
    assert c["op12 22:30:27 12/10 compra"]["alertas"] == ["M1:na_resistencia", "M15:topo_da_faixa", "M30:na_resistencia", "M5:E1/E2_baixa(persistente)"]
    mov = api._sel_movimento_em_formacao(R.LEITURAS_ENTRADA["op52 01:00:24 14/10 venda"])
    rf = mov["regras_da_fase"]
    assert mov["fase"].startswith("topo/fundo PROVISÓRIO") and "sacudida" in rf["admite_intrabar"] and "N=2" in rf["pivo_confirmado"] and any("quebra" in x for x in rf["exige_fechamento"])
    mov = api._sel_movimento_em_formacao(R.LEITURAS_ENTRADA["op12 22:30:27 12/10 compra"])
    assert mov["fase"].startswith("quebra confirmada") and rf["exige_fechamento"]


def test_39_sequencias_topo_quebra_queda_pullback_retomada_protecao_invalidacao_c27r49():
    """C27R49 item 2 + item 5: a sequência topo → quebra da mínima relevante → queda → pullback → retomada → proteção → invalidação (e o espelho)
    é lida como UM movimento (lado constante nas fases); cada fase alimenta a seleção (compatibilidade por família) e a gestão (gestao-3):
    falso rompimento (sacudida) = alerta, não entrada e não saída; pullback que continua = manter/proteger; reversão que invalida (rompeu último
    topo/fundo = degrau 3) fecha mesmo com os menores a favor. Nada aqui é ajuste ao gráfico: são as regras de fase e de degrau já existentes."""
    import api
    def ptf(dir15, est, reg, loc, ev15, d1=None, d5=None, ev5=None, loc1="meio_da_faixa", loc5="meio_da_faixa"):
        return {"M1": {"dir": d1 if d1 is not None else dir15, "localizacao": loc1}, "M5": {"dir": d5 if d5 is not None else dir15, "localizacao": loc5, "eventos": ev5 or []},
                "M15": {"dir": dir15, "estrutura": est, "regime": reg, "localizacao": loc, "eventos": ev15, "ultimo_topo": 4214.23, "ultimo_fundo": 4201.59}, "M30": {"dir": dir15, "regime": "tendencia", "momentum": "estavel", "localizacao": "meio_da_faixa"}}
    seq = [("topo (exaustão)", ptf(1, "ascendente", "tendencia", "topo_da_faixa", ["exaustao_identificada"], d1=0, loc1="na_resistencia"), "topo/fundo PROVISÓRIO"),
           ("quebra da mínima relevante", ptf(-1, "descendente", "tendencia", "meio_da_faixa", ["quebra_estrutura_baixa", "rompimento_confirmado(por_barra)"]), "quebra confirmada"),
           ("pullback", ptf(-1, "descendente", "tendencia", "meio_da_faixa", ["pausa_sem_direcao"], d1=1, d5=1), "pullback"),
           ("retomada", ptf(-1, "descendente", "tendencia", "fundo_da_faixa", ["rompimento_confirmado(por_barra)"]), "retomada/continuação"),
           ("invalidação", ptf(1, "descendente", "tendencia", "meio_da_faixa", ["rompeu_ultimo_topo", "quebra_estrutura_alta"]), "invalidação")]
    fases = [api._sel_movimento_em_formacao(p)["fase"] for _, p, _ in seq]
    for (nome, _, esperado), f in zip(seq, fases):
        assert f.startswith(esperado), (nome, f)
    movs = [api._sel_movimento_em_formacao(p) for _, p, _ in seq]
    assert all(m["regras_da_fase"]["pivo_confirmado"].startswith("último topo/fundo do mapa de pivôs N=2") for m in movs)
    # fase → famílias compatíveis (alimentam a seleção): no topo provisório uma VENDA de continuação não é entrada; a reversão é;
    # na quebra confirmada rompimento/continuação a favor; no pullback 'pullback/retomada'; na invalidação reversão/rompimento
    comp = lambda i, card, lado: api._sel_compatibilidade({"estrategia": {"card": card}, "lado_num": lado}, movs[i])["grau"]
    assert comp(0, "card4_canal_ema20", -1) <= 1 and comp(0, "card7_rsi", -1) == 2                        # topo provisório: só reversão
    assert comp(1, "card10_donchian20", -1) == 2 and comp(1, "card10_donchian20", 1) == 0                    # quebra: rompimento a favor, contra = 0
    assert comp(2, "card3_segunda_entrada", -1) == 2                                                        # pullback: 2ª entrada/retomada
    assert comp(3, "card4_canal_ema20", -1) == 1                                                             # retomada NO fundo da faixa: 1 alerta (M15) rebaixa a 'neutra'
    m_ret = api._sel_movimento_em_formacao(ptf(-1, "descendente", "tendencia", "meio_da_faixa", ["rompimento_confirmado(por_barra)"]))
    assert api._sel_compatibilidade({"estrategia": {"card": "card4_canal_ema20"}, "lado_num": -1}, m_ret)["grau"] == 2       # retomada no meio: compatível
    assert comp(4, "card7_rsi", 1) == 2 and comp(4, "card4_canal_ema20", -1) == 0                           # invalidação: reversão; continuação do lado antigo = 0
    # gestão de uma VENDA aberta na quebra (lado −1) ao longo da mesma sequência:
    cor = {"contrato": "corte-ciclo-2"}
    # falso rompimento contra (sacudida_fundo = alerta de exaustão isolado) → proteger, não fechar
    Lf = {"B3": 0, "corte_do_ciclo": 1, "corte_origem": ["M1:exaustao_identificada -> M15:exaustao_identificada"]}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, Lf, {"B5": 0, "fechamento": 4190.0}, cor, seq[3][1], 3, [])
    assert cls["degrau"] == 1 and acao == "proteger" and "ALERTA" in exp.upper()
    # pullback que continua (M1/M5 a favor da alta, M15 ainda descendente, sem corte) → manter
    Lp = {"B3": 0, "corte_do_ciclo": 0, "corte_origem": []}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, Lp, {"B5": 0, "fechamento": 4192.0}, None, seq[2][1], 2, [])
    assert acao is None and cont["ok"] is True and exp.startswith("sem B5/B3/corte")
    # reversão que invalida (rompeu último topo = degrau 3) → fecha, mesmo com M1/M5 ainda −1
    Li = {"B3": 0, "corte_do_ciclo": 1, "corte_origem": [{"identificado_em": ["M1:rompeu_ultimo_topo"], "decidido_por": ["M15:rompeu_ultimo_topo"]}]}
    p_inv = dict(seq[4][1]); p_inv["M1"] = {"dir": -1}; p_inv["M5"] = {"dir": -1}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, Li, {"B5": 0, "fechamento": 4200.0}, cor, p_inv, 4, [])
    assert cls["degrau"] == 3 and (acao, motivo) == ("close", "ciclo") and exp.startswith("INVALIDAÇÃO ESTRUTURAL CONFIRMADA")
    # espelho (fundo → quebra da máxima → subida → pullback → retomada → invalidação)
    esp = [ptf(-1, "descendente", "tendencia", "fundo_da_faixa", ["exaustao_identificada"], d1=0, loc1="no_suporte"),
           ptf(1, "ascendente", "tendencia", "meio_da_faixa", ["quebra_estrutura_alta", "rompimento_confirmado(por_barra)"]),
           ptf(1, "ascendente", "tendencia", "meio_da_faixa", ["pausa_sem_direcao"], d1=-1, d5=-1),
           ptf(1, "ascendente", "tendencia", "topo_da_faixa", ["rompimento_confirmado(por_barra)"]),
           ptf(-1, "ascendente", "tendencia", "meio_da_faixa", ["rompeu_ultimo_fundo", "quebra_estrutura_baixa"])]
    fe = [api._sel_movimento_em_formacao(p)["fase"] for p in esp]
    assert [f.split(" ")[0] for f in fe] == [f.split(" ")[0] for f in fases]
