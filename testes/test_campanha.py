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
