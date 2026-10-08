"""C27R24 — SESSÃO DE ENSAIO: carimbo pelo banco, recorte no backend, dois ativos, limites comuns,
lote pelo risco, gestão pelo contrato do estudo e resultado pelos negócios assinados.
BANCADA (ambiente isolado local): bots, candidatos, especificação, posições e negócios são SINTÉTICOS,
assinados pelas funções reais da ponte do conector. Nada aqui é evidência da plataforma nem do MT5."""
import ast, hashlib, json, os, sys, time, uuid
from datetime import datetime, timedelta, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI); sys.path.insert(0, RAIZ)
import test_ciclos_lm as T
import test_selecao as S
import test_r01v5 as R

amb = T.amb
api = S.api
URL = T.E["BT_ISO_API"]
OFF = S.OFF
CFG = {"risco_pct_patrimonio": 0.10, "risco_max_por_operacao_usd": 10, "max_aberturas": 6, "max_posicoes_simultaneas": 2,
       "max_posicoes_por_ativo": 1, "risco_agregado_max_usd": 20, "max_perdas_consecutivas": 3, "perda_realizada_max_usd": 30}
ESP = {"XAUUSD": {"simbolo": "XAUUSD", "moeda_de_lucro": "USD", "digitos": 2, "ponto": 0.01, "tick_tamanho": 0.01, "tick_valor": 1.0,
                  "tick_valor_perda": 1.0, "contrato": 100.0, "volume_min": 0.01, "volume_passo": 0.01, "volume_max": 100.0,
                  "modo_de_negociacao": 4, "distancia_minima_stop_pts": 0, "margem_1_lote": {"compra": 8200.0, "venda": 8200.0},
                  "bid": 4099.8, "ask": 4099.92, "tick_idade_s": 1},
       "BTCUSD": {"simbolo": "BTCUSD", "moeda_de_lucro": "USD", "digitos": 2, "ponto": 0.01, "tick_tamanho": 0.01, "tick_valor": 0.01,
                  "tick_valor_perda": 0.01, "contrato": 1.0, "volume_min": 0.01, "volume_passo": 0.01, "volume_max": 50.0,
                  "modo_de_negociacao": 4, "distancia_minima_stop_pts": 0, "margem_1_lote": {"compra": 43000.0, "venda": 43000.0},
                  "bid": 86000.0, "ask": 86012.0, "tick_idade_s": 2}}


def _ponte():
    fonte = open(os.path.join(RAIZ, "conector_homolog", "ponte_motor_hml8.py"), encoding="utf-8").read()
    nos = [n for n in ast.parse(fonte).body if isinstance(n, ast.FunctionDef)
           and n.name in ("_cv_utc", "_cv_txt", "_cv_assinar_candidatos", "_cv_assinar_negocios")]
    assert len(nos) == 4
    d = {}
    exec(compile(ast.Module(body=nos, type_ignores=[]), "ponte_motor_hml8.py", "exec"), d)
    return d


P = _ponte()


def _bot(amb, simbolo):
    s, r, _ = T._req("POST", URL + "/conector/registrar", {"nome": "ses-" + simbolo[:3] + "-" + uuid.uuid4().hex[:6], "simbolo": simbolo}, tok=amb["sess"])
    assert s == 200, r
    return {"tok": r["bot_token"], "id": T._pg("select id from conector_bots where bot_token=%s", r["bot_token"])[0][0], "sim": simbolo}


def _snap(b, det, equity=610000.0, pos=0):
    return T._req("POST", URL + "/conector/snapshot", {
        "bot_token": b["tok"], "conta_login": "52648209", "corretora": "Raw Trading Ltd", "simbolo": b["sim"],
        "magic_number": T._magic(b["tok"]), "equity": equity, "balance": equity, "margem_livre": equity,
        "posicoes_abertas": pos, "lucro_flutuante": 0, "drawdown_atual": 0, "detalhe": det})


def _det(b, itens=(), gestao=None, posicoes=(), negocios=(), preco=None, com_esp=True, esp=None, conta_pos=None):
    """Snapshot: EA + atestado r01v4 + candidatos + atestado r01v5 (com especificação e gestão) + negócios assinados."""
    import bt_cv_atestado as cvat
    sim = b["sim"]; barra = T._barra_m15()
    dirs = R.ALTA_CONTRA_VENDA
    at = cvat.assinar({"bot_token_hash": hashlib.sha256(b["tok"].encode()).hexdigest(), "versao_motor": "teste-ses",
                       "simbolo": sim, "magic": T._magic(b["tok"]), "ts_barra_m15": barra.isoformat(),
                       "cv1": {"janela": {k: dirs[k] for k in ("M1", "M5", "M15")}, "veredito": "bloqueada", "motivo": "item1_referencia_contra(D1)"},
                       "cv2": {"dirs": {"D1": dirs["D1"], "H4": dirs["H4"]}}}, segredo=T.SEGREDO)
    cand = {"versao": "cand-5", "ativo": sim, "leitor": "1.7-hml", "codigo": {"cards": "2.0", "bloco2": "1.7", "bloco1": "3.2.B"},
            "barra_m15_corretora": R._cor(barra - timedelta(seconds=900)), "agora_corretora": R._cor(barra), "territorio_h4_h1_m30": 0,
            "tfs": {tf: {"barra_corretora": R._cor(barra - timedelta(seconds=900))} for tf in ("M15", "M30", "H1")},
            "confirmacao": {"contrato": "conf-rt-1", "validade_s": 1800,
                            "slot_agora": {"corte_contra_compra": False, "corte_contra_venda": False, "B1": False, "B5": False}},
            "itens": list(itens)}
    import corte_util as CU
    cand["cortes"] = CU.cortes(fech_venda=bool((gestao or {}).get("corte")), contrato=(gestao or {}).get("contrato_corte", "corte-ciclo-2"),
                               origem=(gestao or {}).get("origem"))
    if com_esp:
        cand["especificacao"] = dict(esp or ESP[sim], lido_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if gestao is not None:
        cand["gestao"] = {"contrato": "gestao-1", "barra_m15_corretora": R._cor(barra - timedelta(seconds=900)), "fechamento": 4099.0,
                          "B1": False, "B5": gestao.get("B5", False),
                          "lados": {"compra": {"corte_do_ciclo": False, "B3": False, "stop_estrutural": None, "stop_do_lado_certo": False},
                                    "venda": {"corte_do_ciclo": gestao.get("corte", False), "corte_origem": (gestao.get("origem", CU.OR) if gestao.get("corte") else []), "B3": gestao.get("B3", False),
                                              "stop_estrutural": gestao.get("stop"), "stop_do_lado_certo": gestao.get("stop") is not None}}}
    por_tf = {k: {"dir": v, "ultimo_topo": 4130.0, "ultimo_fundo": 4070.0} for k, v in dirs.items()}
    os.environ["BT_CV_SEGREDO"] = T.SEGREDO
    neg = {"versao": "neg-1", "ativo": sim, "lido_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "off_s": OFF, "erro": None,
           "conta": {"equity": 610000.0, "balance": 609800.0, "margem": 430.0, "margem_livre": 609570.0, "nivel_de_margem": 1400.0,
                     "flutuante": 200.0, "moeda": "USD"},
           "conta_posicoes": conta_pos or {"total": len(posicoes), "por_simbolo": {sim: len(posicoes)}},
           "posicoes": list(posicoes), "negocios": list(negocios)}
    extra = {"simbolo": sim, "cv_atestado": at, "preco": preco or ("4099.80" if sim == "XAUUSD" else "86000.00"),
             "spr": "12" if sim == "XAUUSD" else "1200", "pt": "0.01",
             "cv_motor": {"estado": "ok", "motivo": "teste", "off_ea_s": OFF, "por_tf": por_tf, "leitura": {"fase": {"fase": 3}}, "candidatos": cand,
                          "leitor": "1.7-hml", "versao_ponte_conector": "hml13"},
             "cv_atestado_cand": P["_cv_assinar_candidatos"](at, cand, {"por_tf": por_tf}, OFF),
             "cv_negocios": P["_cv_assinar_negocios"](at, neg, T._magic(b["tok"]))}
    return T._det(b["tok"], extra=extra), barra


def _cont(b):
    return (T._pg("select count(*) from ciclo_decisoes where bot_id=%s", b["id"])[0][0],
            T._pg("select count(*) from mt5_comandos where bot_id=%s and tipo in ('buy','sell')", b["id"])[0][0])


def _painel(amb, b, sessao=None):
    s, j, _ = T._req("POST", URL + "/learning/sessao/painel", {"bot_id": b["id"], "sessao": sessao}, tok=amb["sess"])
    assert s == 200, j
    return j


def _ses(sid, col="estado"):
    return T._pg(f"select {col} from sessoes_teste where id=%s", sid)[0][0]


def _res(sid, bot, risco=5.0, reservar=False, dec=None, lado=-1, barra=None, lote=0.01):
    r = T._pg("select ok, motivo, abertura_id, uso from sessao_reservar(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb)",
              sid, bot["id"], reservar, dec or uuid.uuid4().hex, "uid-" + uuid.uuid4().hex[:6], "cardX", "M15", lado,
              barra or T._barra_m15(), lote, 4100.0, 4105.0, risco, bot["sim"], T._magic(bot["tok"]))[0]
    return r


@pytest.fixture(scope="module")
def ses(amb):
    """Dois bots (XAUUSD e BTCUSD), histórico anterior sintético e uma sessão PREPARADA (padrão)."""
    T._pg("update sessoes_teste set padrao=false, estado='encerrada', fim=coalesce(fim, now()) where estado <> 'encerrada'")
    x, b = _bot(amb, "XAUUSD"), _bot(amb, "BTCUSD")
    uid = T._pg("select user_id from conector_bots where id=%s", x["id"])[0][0]
    antiga = T._barra_m15() - timedelta(hours=30)
    for bot in (x, b):                                   # histórico anterior: 3 barras, 2 eventos, 1 comando
        for i in range(3):
            T._pg("insert into ciclo_leituras (bot_id, user_id, simbolo, magic, barra_m15, n_snapshots, completa, decisao, leituras, ciclos) "
                  "values (%s,%s,%s,%s,%s,4,true,'bloquear','{}'::jsonb,'{}'::jsonb)", bot["id"], uid, bot["sim"], T._magic(bot["tok"]), antiga + timedelta(minutes=15 * i))
        for i in range(2):
            T._pg("insert into ciclo_trilha (bot_id, user_id, simbolo, barra_m15, etapa, estado, origem, motivo) values (%s,%s,%s,%s,'veto','recusado','api','antigo')",
                  bot["id"], uid, bot["sim"], antiga + timedelta(minutes=15 * i))
        T._pg("insert into mt5_comandos (bot_token, user_id, bot_id, tipo, params, status, origem) values (%s,%s,%s,'close_all','{}'::jsonb,'expirado','teste_antigo')",
              bot["tok"], uid, bot["id"])
    sid = "ENS-TESTE-" + uuid.uuid4().hex[:8]
    T._pg("insert into sessoes_teste (id, nome, user_id, bots, estado, fim_previsto, config) values (%s,%s,%s,%s,'preparada', now() + interval '1 day', %s::jsonb)",
          sid, "Ensaio de bancada", uid, [x["id"], b["id"]], json.dumps(CFG))
    time.sleep(5.5)                                      # cache de sessões do servidor (5 s)
    yield {"id": sid, "x": x, "b": b, "uid": uid}
    T._pg("update autoridade_contratos set emissao_habilitada=false where contrato='r01v5'")
    T._pg("update sessoes_teste set estado='encerrada', padrao=false, fim=coalesce(fim, now()) where id=%s", sid)


def test_1_sessao_preparada_comeca_zerada_e_o_historico_fica_inteiro(amb, ses):
    x, b = ses["x"], ses["b"]
    det, barra = _det(x)
    assert _snap(x, det)[0] == 200                      # antes do início: grava, mas SEM carimbo
    p = _painel(amb, x)
    assert p["recorte"]["sessao_teste_id"] == ses["id"] and p["painel"]["sessao"]["estado"] == "preparada"
    assert p["painel"]["sessao"]["inicio"] is None and p["painel"]["sessao"]["novas_aberturas"] == "bloqueadas"
    for sim in ("XAUUSD", "BTCUSD"):
        c = p["painel"]["ativos"][sim]["contadores"]
        assert all(c[k] == 0 for k in ("barras", "snapshots", "candidatos", "vetos", "decisoes", "comandos", "aberturas", "fechamentos", "eventos_da_trilha")), c
        assert c["resultado_usd"] is None
    h = p["painel"]["ativos"]["XAUUSD"]["historico_anterior"]
    assert h["barras"] == 4 and h["comandos"] == 1 and h["vetos"] >= 2            # 3 antigas + a barra em curso
    assert p["painel"]["ativos"]["BTCUSD"]["historico_anterior"]["barras"] == 3
    assert T._pg("select count(*) from ciclo_leituras where bot_id in (%s,%s) and sessao_teste_id is not null", x["id"], b["id"])[0][0] == 0
    # o painel ao vivo, no recorte padrão (a sessão), também vem zerado; o histórico anterior continua acessível
    s, j, _ = T._req("POST", URL + "/learning/ciclos/ao-vivo", {"bot_id": x["id"]}, tok=amb["sess"])
    assert s == 200 and j["recorte"]["sessao_teste_id"] == ses["id"] and j["contadores"]["barras_analisadas"] == 0
    s, j, _ = T._req("POST", URL + "/learning/ciclos/ao-vivo", {"bot_id": x["id"], "sessao": "anterior", "dias": 3}, tok=amb["sess"])
    assert s == 200 and j["recorte"]["recorte"] == "anterior" and j["contadores"]["barras_analisadas"] == 4
    s, j, _ = T._req("POST", URL + "/learning/ciclos/trilha", {"bot_id": x["id"], "sessao": "anterior"}, tok=amb["sess"])
    assert s == 200 and j["total"] >= 2 and all(t["sessao_teste_id"] is None for t in j["trilha"])
    s, j, _ = T._req("POST", URL + "/learning/ciclos/trilha", {"bot_id": x["id"]}, tok=amb["sess"])
    assert s == 200 and j["total"] == 0


def test_2_inicio_carimba_so_o_que_e_da_sessao_no_ativo_certo_e_nao_duplica(api, amb, ses):
    x, b, sid = ses["x"], ses["b"], ses["id"]
    T._pg("select sessao_iniciar(%s)", sid)
    ini, pb = _ses(sid, "inicio"), _ses(sid, "primeira_barra")
    assert _ses(sid) == "ativa" and pb >= ini and (pb - ini) <= timedelta(minutes=15) and pb.minute % 15 == 0
    assert _ses(sid, "aberturas_habilitadas") is False
    with pytest.raises(Exception):
        T._pg("select sessao_iniciar(%s)", sid)          # não reinicia (o início não é reescrito)
    assert _ses(sid, "inicio") == ini
    time.sleep(5.5)
    # barra em curso no início = ANTERIOR (sem carimbo); barra velha chegando agora = ATRASADA
    det, barra = _det(x)
    assert _snap(x, det)[0] == 200
    # (o único evento sem barra — o estado do mercado, gravado depois do início — já é da sessão)
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and sessao_teste_id=%s and etapa <> 'mercado'", x["id"], sid)[0][0] == 0
    assert T._pg("select etapa, estado from ciclo_trilha where bot_id=%s and sessao_teste_id=%s", x["id"], sid) == [("mercado", "ok")]
    T._pg("insert into ciclo_trilha (bot_id, user_id, simbolo, barra_m15, etapa, estado, origem, motivo) values (%s,%s,'XAUUSD',%s,'snapshot','ok','conector','chegou tarde')",
          x["id"], ses["uid"], barra - timedelta(hours=2))
    assert T._pg("select sessao_teste_id, sessao_atraso_de from ciclo_trilha where bot_id=%s and motivo='chegou tarde'", x["id"])[0] == (None, sid)
    # BANCADA: a 1ª barra da sessão passa a ser a barra atual (na plataforma, espera-se a virada da M15)
    T._pg("update sessoes_teste set primeira_barra=%s where id=%s", barra, sid)
    T._pg("delete from ciclo_leituras where bot_id=%s and barra_m15=%s", x["id"], barra)
    T._pg("delete from selecao_avaliacoes where bot_id=%s and barra_m15=%s", x["id"], barra)
    time.sleep(5.5)
    it = R._rt("card2_rompimento_caixa", "M30", -1, barra, preco=4100.0, stop=4105.0)
    det, barra = _det(x, [it])
    assert _snap(x, det)[0] == 200
    lin = T._pg("select sessao_teste_id, sessao_atraso_de, n_snapshots from ciclo_leituras where bot_id=%s and barra_m15=%s", x["id"], barra)
    assert lin == [(sid, None, 1)]
    assert T._pg("select sessao_teste_id from selecao_avaliacoes where bot_id=%s and barra_m15=%s", x["id"], barra) == [(sid,)]
    p = _painel(amb, x)["painel"]
    cx, cb = p["ativos"]["XAUUSD"]["contadores"], p["ativos"]["BTCUSD"]["contadores"]
    assert cx["barras"] == 1 and cx["snapshots"] == 1 and cx["candidatos"] == 1 and cx["elegiveis"] == 1 and cx["eventos_da_trilha"] > 0
    assert cb["barras"] == 0 and cb["candidatos"] == 0 and cb["eventos_da_trilha"] == 0          # nada do ouro caiu no bitcoin
    assert cx["atrasados"]["trilha"] == 1
    assert p["ativos"]["XAUUSD"]["por_timeframe"]["M30"]["candidatos"]["elegivel"] == 1
    assert p["ativos"]["XAUUSD"]["por_timeframe"]["M15"]["candidatos"]["avaliacoes_de_candidato"] == 0
    assert p["ativos"]["XAUUSD"]["historico_anterior"]["barras"] == 3                            # o histórico não mudou
    # sombra com a chave DESLIGADA: plano de lote e limites conferidos, nada criado
    s5 = R._sel(x, barra)["autoridade_r01v5"]
    assert s5["seria_emitida"] is True and s5["emissao_habilitada"] is False and s5["sessao"]["permitido"] is False
    assert s5["sessao"]["motivo"] == "aberturas_nao_habilitadas" and s5["sessao"]["plano"]["lote"] == 0.01
    assert s5["sessao"]["plano"]["risco_planejado_usd"] == 5.2 and s5["sessao"]["plano"]["risco_alvo_usd"] == 10.0
    assert _cont(x) == (0, 0)
    # o mesmo snapshot de novo (página recarregada, conector reenviando, API reiniciada): não duplica nem zera
    antes = {k: cx[k] for k in ("barras", "candidatos", "elegiveis", "eventos_da_trilha", "avaliacoes_de_selecao")}
    assert _snap(x, det)[0] == 200
    api._SES_CACHE.update({"t": 0.0, "rows": []}); api._SEL_ESTUDOS_CACHE.clear()                # "reinício" do processo que lê
    p2 = _painel(amb, x)["painel"]["ativos"]["XAUUSD"]["contadores"]
    assert {k: p2[k] for k in antes} == antes and p2["snapshots"] == 2
    # bitcoin: registro novo aparece no bitcoin
    detb, _ = _det(b)
    assert _snap(b, detb)[0] == 200
    p3 = _painel(amb, b)["painel"]
    assert p3["ativos"]["BTCUSD"]["contadores"]["barras"] == 1 and p3["ativos"]["XAUUSD"]["contadores"]["barras"] == 1
    assert p3["consolidado"]["contadores"]["barras"] == 2
    # conta: uma vez, não por bot
    assert p3["consolidado"]["conta"]["equity"] == 610000.0 and "uma vez" in p3["consolidado"]["conta"]["nota"]
    # tela × banco: os contadores do painel são os do banco
    for bot, sim in ((x, "XAUUSD"), (b, "BTCUSD")):
        n = T._pg("select count(*), coalesce(sum(n_snapshots),0) from ciclo_leituras where bot_id=%s and sessao_teste_id=%s", bot["id"], sid)[0]
        assert (p3["ativos"][sim]["contadores"]["barras"], p3["ativos"][sim]["contadores"]["snapshots"]) == (n[0], int(n[1]))
    ses["barra"], ses["it"], ses["det"] = barra, it, det


def test_3_lote_pelo_risco_com_a_especificacao_do_proprio_simbolo(api, amb, ses):
    sb = api._sb_admin()
    S_ = {"id": ses["id"], "config": CFG}
    cx = {"lado": -1, "preco_ref": "4100.000000", "stop": "4105.000000"}
    bx = {"simbolo": "XAUUSD", "equity": 610000.0, "margem_livre": 600000.0}
    tx = lambda e: json.loads(json.dumps(P["_cv_txt"](e)))
    pl, m = api._ses_plano(S_, bx, {"especificacao": tx(ESP["XAUUSD"])}, cx, {"preco": "4099.80", "spr": "12", "pt": "0.01"})
    assert m is None and pl["lote"] == 0.01 and pl["risco_planejado_usd"] == 5.2 and pl["risco_alvo_usd"] == 10.0
    # 0,10% do patrimônio quando é MENOR que US$ 10: conta de US$ 5.000 → alvo US$ 5 → o lote mínimo (US$ 5,20) não cabe
    pl, m = api._ses_plano(S_, dict(bx, equity=5000.0, margem_livre=5000.0), {"especificacao": tx(ESP["XAUUSD"])}, cx, {"preco": "4099.80", "spr": "12", "pt": "0.01"})
    assert pl is None and m.startswith("lote_minimo_nao_cabe_no_risco")
    # stop mais longe: nem o lote mínimo cabe em US$ 10
    pl, m = api._ses_plano(S_, bx, {"especificacao": tx(ESP["XAUUSD"])}, dict(cx, stop="4112.000000"), {"preco": "4099.80", "spr": "12", "pt": "0.01"})
    assert pl is None and m.startswith("lote_minimo_nao_cabe_no_risco")
    # bitcoin com a especificação DELE: 1 lote = 1 BTC; stop a US$ 400 → 0,02 lote = US$ 8,24 (arredonda para baixo)
    cb = {"lado": 1, "preco_ref": "86000.000000", "stop": "85600.000000"}
    bb = {"simbolo": "BTCUSD", "equity": 610000.0, "margem_livre": 600000.0}
    pl, m = api._ses_plano(S_, bb, {"especificacao": tx(ESP["BTCUSD"])}, cb, {"preco": "86000.00", "spr": "1200", "pt": "0.01"})
    assert m is None and pl["lote"] == 0.02 and pl["risco_planejado_usd"] == 8.24 and pl["entrada_estimada"] == 86012.0
    # especificação de OUTRO símbolo nunca serve; sem especificação, sem cotação, mercado fechado: não abre
    assert api._ses_plano(S_, bb, {"especificacao": tx(ESP["XAUUSD"])}, cb, {"preco": "86000", "spr": "1200", "pt": "0.01"}) == (None, "especificacao_de_outro_simbolo")
    assert api._ses_plano(S_, bb, {}, cb, {"preco": "86000"})[1].startswith("especificacao_do_simbolo_ausente")
    assert api._ses_plano(S_, bb, {"especificacao": tx(dict(ESP["BTCUSD"], tick_idade_s=4000))}, cb, {"preco": "86000", "spr": "1200", "pt": "0.01"})[1].startswith("sem_cotacao_recente")
    assert api._ses_plano(S_, bb, {"especificacao": tx(dict(ESP["BTCUSD"], modo_de_negociacao=0))}, cb, {"preco": "86000", "spr": "1200", "pt": "0.01"})[1].startswith("simbolo_sem_negociacao_plena")
    assert api._ses_plano(S_, dict(bb, margem_livre=500.0), {"especificacao": tx(ESP["BTCUSD"])}, cb, {"preco": "86000", "spr": "1200", "pt": "0.01"})[1].startswith("margem_livre_insuficiente")
    assert sb is not None


def test_4_abertura_real_so_com_chave_sessao_habilitada_e_limites(api, amb, ses):
    x, b, sid, barra, it, det = ses["x"], ses["b"], ses["id"], ses["barra"], ses["it"], ses["det"]
    sb = api._sb_admin()
    bot = dict(sb.table("conector_bots").select("*").eq("id", x["id"]).execute().data[0], equity=610000.0, margem_livre=600000.0, posicoes_abertas=0)
    api._SES_CACHE.update({"t": 0.0, "rows": []})
    sombra = lambda: api._r05_sombra(sb, bot, det, R._sel(x, barra), int(time.time()))
    # chave ligada, aberturas da sessão DESLIGADAS: nada
    R._chave(True)
    try:
        s5 = api._ses_executar(sb, bot, sombra(), det)
        assert s5["decisao_emitida"] is False and "sem aberturas habilitadas" in s5["execucao_real"] and _cont(x) == (0, 0)
        # sessão habilitada: decisão + reserva + comando, com o lote do plano e o stop assinado
        T._pg("update sessoes_teste set aberturas_habilitadas=true, aberturas_habilitadas_em=now() where id=%s", sid)
        api._SES_CACHE.update({"t": 0.0, "rows": []})
        s5 = api._ses_executar(sb, bot, sombra(), det)
        assert s5["decisao_emitida"] is True and s5["comando_criado"] is True, s5
        c = T._pg("select id, tipo, status, origem, params, sessao_teste_id from mt5_comandos where bot_id=%s and tipo='sell'", x["id"])
        assert len(c) == 1 and c[0][1:4] == ("sell", "pendente", "sessao_r01v5") and c[0][5] == sid
        assert c[0][4]["lote"] == 0.01 and c[0][4]["sl"] == 4105.0 and "tp" not in c[0][4]
        d = T._pg("select status, sessao_teste_id from ciclo_decisoes where bot_id=%s", x["id"])
        assert d == [("consumida", sid)]
        ab = T._pg("select estado, lote, risco_planejado_usd, comando_id, tf, lado from sessao_aberturas where sessao_teste_id=%s and bot_id=%s", sid, x["id"])
        assert ab == [("reservada", 0.01, 5.2, c[0][0], "M30", -1)] or (ab[0][0] == "reservada" and float(ab[0][1]) == 0.01 and float(ab[0][2]) == 5.2)
        # repetição: o mesmo candidato não abre de novo; o ativo já tem reserva
        s5b = api._ses_executar(sb, bot, sombra(), det)
        assert s5b["comando_criado"] is False and _cont(x) == (1, 1)
        assert _res(sid, x)[:2] == (False, "ativo_ja_tem_posicao_ou_reserva")
        # o caminho r01v4 e o protetor legado não atuam em bot de sessão
        assert api._r01_abrir_via_rpc(sb, bot, "buy", {}, "teste")[1].startswith("bot_em_sessao_de_ensaio")
        assert api._protetor_posicao(sb, bot, None, {}) is None
        # MT5 (sintético) responde: executado → posição aberta no livro
        s, j, _ = T._req("POST", URL + "/mt5/comando/confirmar", {"comando_id": c[0][0], "sucesso": True, "bot_token": x["tok"],
                                                                 "resultado": {"ticket": 777001, "preco_real": 4099.75, "retcode": 10009}})
        assert s == 200 and j["status"] == "executado"
        pos = [{"ticket": 777001, "posicao_id": 777001, "magic": T._magic(x["tok"]), "tipo": 1, "volume": 0.01, "preco_abertura": 4099.75,
                "sl": 4105.0, "tp": 0.0, "lucro": -0.1, "swap": 0.0, "aberta_corretora": int(time.time()) + OFF},
               {"ticket": 1864270384, "posicao_id": 1864270384, "magic": 0, "tipo": 0, "volume": 0.05, "preco_abertura": 4000.0,
                "sl": 0.0, "tp": 0.0, "lucro": 180.0, "swap": 0.0, "aberta_corretora": 1}]
        detp, _ = _det(x, [it], posicoes=pos)
        assert _snap(x, detp, pos=1)[0] == 200
        ab = T._pg("select estado, ticket, preco_entrada from sessao_aberturas where sessao_teste_id=%s and bot_id=%s", sid, x["id"])[0]
        assert ab[0] == "aberta" and ab[1] == 777001 and float(ab[2]) == 4099.75
        p = _painel(amb, x)["painel"]
        assert p["ativos"]["XAUUSD"]["contadores"]["aberturas"] == 1 and p["consolidado"]["limites"]["risco_aberto_usd"] == 5.2
        assert p["ativos"]["XAUUSD"]["por_timeframe"]["M30"]["aberturas"] == 1 and p["ativos"]["XAUUSD"]["por_timeframe"]["M15"]["aberturas"] == 0
        # posição de outro magic: fora do resultado, dentro da exposição
        outras = p["ativos"]["XAUUSD"]["saude"]["posicoes_de_outros_magics_no_simbolo"]
        assert len(outras) == 1 and outras[0]["magic"] == 0 and p["ativos"]["XAUUSD"]["contadores"]["posicoes_abertas"] == 1
        ses["pos"] = pos
    finally:
        pass


def test_5_limites_comuns_aos_dois_ativos(amb, ses):
    x, b, sid = ses["x"], ses["b"], ses["id"]
    assert _res(sid, b, risco=10.01)[:2] == (False, "risco_acima_do_limite_por_operacao")
    assert _res(sid, b, risco=14.81)[1] == "risco_acima_do_limite_por_operacao"
    ok, mot, _i, uso = _res(sid, b, risco=10.0)                       # 5,20 (ouro) + 10 = 15,20 ≤ 20
    assert ok is True and uso["risco_aberto_usd"] == 5.2 and uso["posicoes_abertas"] == 1
    assert _res(sid, b, risco=9.0, barra=T._barra_m15() - timedelta(hours=1))[1] == "barra_anterior_ao_inicio_da_sessao"
    ok, mot, ab_b, _u = _res(sid, b, risco=10.0, reservar=True, dec="dec-b-1", lado=1)
    assert ok is True and ab_b
    assert _res(sid, b, risco=1.0)[1] == "ativo_ja_tem_posicao_ou_reserva"
    # terceiro bot hipotético não existe: o limite de 2 simultâneas aparece liberando um ativo e tentando de novo
    T._pg("update sessao_aberturas set estado='cancelada', motivo_cancelamento='teste' where id=%s", ab_b)
    assert _res(sid, b, risco=14.9)[1] == "risco_acima_do_limite_por_operacao"
    T._pg("update sessoes_teste set config = config || '{\"risco_max_por_operacao_usd\": 16}'::jsonb where id=%s", sid)
    assert _res(sid, b, risco=14.9)[:2] == (False, "risco_agregado_acima_do_limite")           # 5,20 + 14,90 > 20: o orçamento não é usado duas vezes
    T._pg("update sessoes_teste set config = config || '{\"risco_max_por_operacao_usd\": 10, \"max_posicoes_simultaneas\": 1}'::jsonb where id=%s", sid)
    assert _res(sid, b, risco=5.0)[1] == "maximo_de_posicoes_simultaneas"
    T._pg("update sessoes_teste set config = config || '{\"max_posicoes_simultaneas\": 2}'::jsonb where id=%s", sid)
    # cancelada não conta como abertura; 6 aberturas é o teto da sessão inteira
    assert _res(sid, b, risco=5.0)[3]["aberturas"] == 1
    for i in range(5):
        T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, decisao_id, candidato_uid, lado, ts_barra, lote, stop_inicial, risco_planejado_usd, estado, resultado_usd, ts_fechamento) "
              "values (%s,%s,'BTCUSD',%s,'u',1,now(),0.01,1,5,'fechada',%s, now() - make_interval(mins => %s))", sid, b["id"], "hist-%d" % i, 3.0, 50 - i)
    assert _res(sid, b, risco=5.0)[:2] == (False, "maximo_de_aberturas_da_sessao")
    T._pg("delete from sessao_aberturas where sessao_teste_id=%s and decisao_id like 'hist-%%'", sid)
    # três perdas seguidas → para (e a suspensão fica gravada); um ganho no meio zera a sequência
    for i, r in enumerate((-4.0, 2.0, -3.0, -3.0)):
        T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, decisao_id, candidato_uid, lado, ts_barra, lote, stop_inicial, risco_planejado_usd, estado, resultado_usd, ts_fechamento) "
              "values (%s,%s,'BTCUSD',%s,'u',1,now(),0.01,1,5,'fechada',%s, now() - make_interval(mins => %s))", sid, b["id"], "seq-%d" % i, r, 40 - i)
    ok, mot, _i, uso = _res(sid, b, risco=5.0)
    assert ok is True and uso["perdas_consecutivas"] == 2 and uso["resultado_realizado_usd"] == -8.0
    T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, decisao_id, candidato_uid, lado, ts_barra, lote, stop_inicial, risco_planejado_usd, estado, resultado_usd, ts_fechamento) "
          "values (%s,%s,'BTCUSD','seq-9','u',1,now(),0.01,1,5,'fechada',-1.0, now())", sid, b["id"])
    assert _res(sid, b, risco=5.0)[:2] == (False, "tres_perdas_consecutivas")
    assert _ses(sid, "motivo_suspensao") == "tres_perdas_consecutivas" and _ses(sid, "aberturas_suspensas_em") is not None
    assert _res(sid, b, risco=5.0)[1] == "aberturas_suspensas(tres_perdas_consecutivas)"
    T._pg("update sessoes_teste set aberturas_suspensas_em=null, motivo_suspensao=null where id=%s", sid)
    T._pg("delete from sessao_aberturas where sessao_teste_id=%s and decisao_id like 'seq-%%'", sid)
    # perda realizada acumulada de US$ 30 → para
    for i, r in enumerate((-12.0, 5.0, -11.5, -11.5)):
        T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, decisao_id, candidato_uid, lado, ts_barra, lote, stop_inicial, risco_planejado_usd, estado, resultado_usd, ts_fechamento) "
              "values (%s,%s,'BTCUSD',%s,'u',1,now(),0.01,1,5,'fechada',%s, now() - make_interval(mins => %s))", sid, b["id"], "per-%d" % i, r, 40 - i)
    assert _res(sid, b, risco=5.0)[:2] == (False, "perda_realizada_acumulada_no_limite")
    T._pg("update sessoes_teste set aberturas_suspensas_em=null, motivo_suspensao=null where id=%s", sid)
    # fechamento sem resultado apurado bloqueia (fail-closed)
    T._pg("delete from sessao_aberturas where sessao_teste_id=%s and decisao_id like 'per-%%'", sid)
    T._pg("insert into sessao_aberturas (sessao_teste_id, bot_id, simbolo, decisao_id, candidato_uid, lado, ts_barra, lote, stop_inicial, risco_planejado_usd, estado) "
          "values (%s,%s,'BTCUSD','pend-1','u',1,now(),0.01,1,5,'fechada')", sid, b["id"])
    assert _res(sid, b, risco=5.0)[1] == "resultado_de_fechamento_pendente(fail_closed)"
    T._pg("delete from sessao_aberturas where sessao_teste_id=%s and decisao_id in ('pend-1','dec-b-1')", sid)
    assert _res(sid, b, risco=5.0)[0] is True


def test_6_gestao_pelo_contrato_do_estudo_e_resultado_pelos_negocios(api, amb, ses):
    x, sid, it, pos = ses["x"], ses["id"], ses["it"], ses["pos"]
    ab_id = T._pg("select id from sessao_aberturas where sessao_teste_id=%s and bot_id=%s and estado='aberta'", sid, x["id"])[0][0]
    n_cmd = lambda t: T._pg("select count(*) from mt5_comandos where bot_id=%s and tipo=%s", x["id"], t)[0][0]
    # barra anterior à entrada: a gestão não se aplica
    det, barra = _det(x, [it], gestao={"corte": True}, posicoes=pos)
    assert _snap(x, det, pos=1)[0] == 200 and n_cmd("close") == 0
    # BANCADA: a posição passa a ter 2 barras (na plataforma, o tempo passa sozinho)
    T._pg("update sessao_aberturas set ts_abertura = now() - interval '31 minutes' where id=%s", ab_id)
    # trailing estrutural: só aperta (venda: stop desce de 4105 para 4103), e só uma vez por barra
    det, barra = _det(x, [it], gestao={"stop": 4103.0}, posicoes=pos)
    assert _snap(x, det, pos=1)[0] == 200 and _snap(x, det, pos=1)[0] == 200
    c = T._pg("select tipo, status, origem, params, sessao_teste_id from mt5_comandos where bot_id=%s and tipo='mover_sl'", x["id"])
    assert len(c) == 1 and c[0][2] == "sessao_gestao" and c[0][3]["sl"] == 4103.0 and c[0][3]["ticket"] == 777001 and c[0][4] == sid
    assert c[0][3]["uid_gestao"].startswith(f"G-{ab_id}-")
    g = T._pg("select gestao from sessao_aberturas where id=%s", ab_id)[0][0]
    assert len(g) == 1 and g[0]["acao"] == "mover_sl" and g[0]["barras_de_posicao"] >= 1
    # C27R25: o MT5 devolve o stop arredondado pela corretora (4103.0 → 4103.004 na bancada, < 1 ponto): é o do comando, não "FORA da plataforma"
    pos_r = [dict(pos[0], sl=4103.004), pos[1]]
    det, barra = _det(x, [it], gestao={"stop": 4103.0}, posicoes=pos_r)
    assert _snap(x, det, pos=1)[0] == 200
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='gestao' and estado='aviso' and motivo like '%%FORA da plataforma%%'", x["id"])[0][0] == 0
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='gestao' and estado='ok' and motivo like 'stop vigente no MT5: 4103.004%%'", x["id"])[0][0] == 1
    # stop que AFROUXA nunca é enviado; corte do Ciclo fecha (outra barra: bancada limpa o registro da barra)
    T._pg("update sessao_aberturas set gestao='[]'::jsonb where id=%s", ab_id)
    T._pg("delete from mt5_comandos where bot_id=%s and tipo='mover_sl'", x["id"])
    det, barra = _det(x, [it], gestao={"stop": 4108.0}, posicoes=pos)
    assert _snap(x, det, pos=1)[0] == 200 and n_cmd("mover_sl") == 0
    assert T._pg("select gestao->0->>'acao' from sessao_aberturas where id=%s", ab_id)[0][0] == "manter"
    # C27R25 — corte que NÃO é do contrato corte-ciclo-2 não fecha: (a) contrato anterior, (b) origem decidida por H1, (c) por M30
    for g_ruim, falha in (({"corte": True, "contrato_corte": "corte-ciclo-1"}, "contrato_de_corte_diferente"),
                          ({"corte": True, "origem": [{"identificado_em": ["M5:x"], "decidido_por": ["H1:y"]}]}, "corte_com_origem_fora_do_contrato"),
                          ({"corte": True, "origem": [{"identificado_em": ["M1:x"], "decidido_por": ["M30:y"]}]}, "corte_com_origem_fora_do_contrato")):
        T._pg("update sessao_aberturas set gestao='[]'::jsonb where id=%s", ab_id)
        det, barra = _det(x, [it], gestao=g_ruim, posicoes=pos)
        assert _snap(x, det, pos=1)[0] == 200 and n_cmd("close") == 0
        gr = T._pg("select gestao->0 from sessao_aberturas where id=%s", ab_id)[0][0]
        assert gr["acao"] == "manter" and gr["corte"]["ignorado"].startswith(falha) and gr["corte"]["exigido"] == "corte-ciclo-2"
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='gestao' and estado='aviso' and motivo like '%%corte do Ciclo IGNORADO%%'", x["id"])[0][0] >= 1
    T._pg("update sessao_aberturas set gestao='[]'::jsonb where id=%s", ab_id)
    det, barra = _det(x, [it], gestao={"corte": True, "stop": 4103.0}, posicoes=pos)
    assert _snap(x, det, pos=1)[0] == 200 and _snap(x, det, pos=1)[0] == 200
    c = T._pg("select params from mt5_comandos where bot_id=%s and tipo='close'", x["id"])
    assert len(c) == 1 and c[0][0]["ticket"] == 777001 and c[0][0]["motivo"] == "ciclo" and n_cmd("mover_sl") == 0
    gr = T._pg("select gestao->0 from sessao_aberturas where id=%s", ab_id)[0][0]              # a regra original responsável fica no registro
    assert gr["corte"]["contrato"] == "corte-ciclo-2" and gr["corte"]["origem"] == ["M5:rompe_fundo -> M15:fecha_abaixo_canal"]
    assert "FichaSerie._cortes" in gr["corte"]["regra_original"] and gr["corte"]["nao_cortam"][:2] == ["M30", "H1"]
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='gestao' and motivo like '%%corte-ciclo-2%%M15:fecha_abaixo_canal%%'", x["id"])[0][0] == 1
    # stop mexido FORA da plataforma (trailing do próprio EA): registrado como aviso, o livro acompanha
    pos2 = [dict(pos[0], sl=4101.5), pos[1]]
    det, barra = _det(x, [it], gestao={"corte": True}, posicoes=pos2)
    assert _snap(x, det, pos=1)[0] == 200
    assert float(T._pg("select stop_atual from sessao_aberturas where id=%s", ab_id)[0][0]) == 4101.5
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='gestao' and estado='aviso' and motivo like '%%FORA da plataforma%%'", x["id"])[0][0] == 1
    # posição some, negócio de saída ainda não chegou: espera (não inventa resultado)
    det, barra = _det(x, [it], posicoes=[pos[1]])
    assert _snap(x, det, pos=0)[0] == 200
    assert T._pg("select estado from sessao_aberturas where id=%s", ab_id)[0][0] == "aberta"
    # negócios do MT5: entrada (magic do bot) + saída por comando (EA) → resultado = lucro + comissão + swap
    mg = T._magic(x["tok"]); agora_c = int(time.time()) + OFF
    negs = [{"ticket": 91, "ordem": 777001, "posicao_id": 777001, "magic": mg, "tipo": 1, "entrada": 0, "volume": 0.01, "preco": 4099.75,
             "lucro": 0.0, "comissao": -0.04, "swap": 0.0, "taxa": 0.0, "motivo": 3, "hora_corretora": agora_c - 2000},
            {"ticket": 92, "ordem": 777002, "posicao_id": 777001, "magic": 0, "tipo": 0, "entrada": 1, "volume": 0.01, "preco": 4096.25,
             "lucro": 3.5, "comissao": -0.04, "swap": -0.01, "taxa": 0.0, "motivo": 3, "hora_corretora": agora_c - 5},
            {"ticket": 50, "ordem": 50, "posicao_id": 1864270384, "magic": 0, "tipo": 0, "entrada": 0, "volume": 0.05, "preco": 4000.0,
             "lucro": 0.0, "comissao": 0.0, "swap": 0.0, "taxa": 0.0, "motivo": 0, "hora_corretora": 1}]
    det, barra = _det(x, [it], posicoes=[pos[1]], negocios=negs)
    assert "1864270384" not in json.dumps(det["cv_negocios"]["negocios"])       # negócio manual não viaja
    assert _snap(x, det, pos=0)[0] == 200 and _snap(x, det, pos=0)[0] == 200
    r = T._pg("select estado, resultado_usd, lucro, comissao, swap, motivo_saida, preco_saida from sessao_aberturas where id=%s", ab_id)[0]
    assert r[0] == "fechada" and float(r[1]) == 3.41 and float(r[2]) == 3.5 and float(r[3]) == -0.08 and float(r[4]) == -0.01
    assert r[5] == "ciclo" and float(r[6]) == 4096.25
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='fechamento' and sessao_teste_id=%s", x["id"], sid)[0][0] == 1
    p = _painel(amb, x)["painel"]
    assert p["ativos"]["XAUUSD"]["contadores"]["fechamentos"] == 1 and p["ativos"]["XAUUSD"]["contadores"]["resultado_usd"] == 3.41
    assert p["consolidado"]["contadores"]["resultado_usd"] == 3.41 and p["ativos"]["BTCUSD"]["contadores"]["resultado_usd"] is None
    assert p["consolidado"]["limites"]["posicoes_abertas"] == 0 and p["consolidado"]["limites"]["resultado_realizado_usd"] == 3.41
    assert p["ativos"]["XAUUSD"]["por_timeframe"]["M30"]["resultado_usd"] == 3.41
    # negócios adulterados ou de outro bot não fecham nada
    ruim = json.loads(json.dumps(det)); ruim["cv_negocios"]["negocios"][1]["lucro"] = "999.0"
    assert api._ses_negocios({"bot_token": x["tok"], "simbolo": "XAUUSD"}, ruim)[0] is None
    assert api._ses_negocios({"bot_token": ses["b"]["tok"], "simbolo": "XAUUSD"}, det)[1] == "negocios_de_outro_bot(fail_closed)"


def test_7_relatorio_json_e_pdf_com_o_mesmo_recorte(amb, ses):
    x, sid = ses["x"], ses["id"]
    s, j, _ = T._req("POST", URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao"}, tok=amb["sess"])
    assert s == 200 and j["sessao_teste_id"] == sid and j["recorte"]["sessao_teste_id"] == sid and j["escopo"] == "XAUUSD", str(j)[:300]
    p = _painel(amb, x)["painel"]
    for sim in ("XAUUSD", "BTCUSD"):
        a, c = j["sessao_teste"]["ativos"][sim]["contadores"], p["ativos"][sim]["contadores"]
        assert {k: a[k] for k in ("barras", "candidatos", "elegiveis", "decisoes", "comandos", "aberturas", "fechamentos", "resultado_usd")} == \
               {k: c[k] for k in ("barras", "candidatos", "elegiveis", "decisoes", "comandos", "aberturas", "fechamentos", "resultado_usd")}
    bd = T._pg("select count(*) from ciclo_leituras where bot_id=%s and sessao_teste_id=%s", x["id"], sid)[0][0]
    assert j["sessao_teste"]["ativos"]["XAUUSD"]["contadores"]["barras"] == bd
    assert "token" not in json.dumps(j).lower().replace("bot_token_hash", "")
    assert T._pg("select sessao_teste_id from relatorios_gerados where id=%s", j["relatorio_id"])[0][0] == sid
    rq = __import__("urllib.request").request
    for fmt, assin in (("pdf", b"%PDF"), ("json", b"{")):
        q = rq.Request(URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": j["relatorio_id"], "formato": fmt}).encode(),
                       headers={"Content-Type": "application/json", "Authorization": "Bearer " + amb["sess"]}, method="POST")
        raw = rq.urlopen(q, timeout=120).read()
        assert raw[:len(assin)] == assin and len(raw) > 2000
        if fmt == "json":
            assert json.loads(raw)["sessao_teste"]["sessao"]["sessao_teste_id"] == sid
    # consolidado: só a sessão (os dois ativos), sem repetir a conta
    s, k, _ = T._req("POST", URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "sessao", "consolidado": True}, tok=amb["sess"])
    assert s == 200 and k["escopo"] == "Ensaio consolidado" and "resumo" not in k and set(k["sessao_teste"]["ativos"]) == {"XAUUSD", "BTCUSD"}
    q = rq.Request(URL + "/learning/relatorio/baixar", data=json.dumps({"relatorio_id": k["relatorio_id"], "formato": "pdf"}).encode(),
                   headers={"Content-Type": "application/json", "Authorization": "Bearer " + amb["sess"]}, method="POST")
    assert rq.urlopen(q, timeout=120).read()[:4] == b"%PDF"
    # histórico anterior continua acessível pelo relatório
    s, h, _ = T._req("POST", URL + "/learning/relatorio/gerar", {"bot_id": x["id"], "periodo": "7d", "sessao": "anterior"}, tok=amb["sess"])
    assert s == 200 and h["recorte"]["recorte"] == "anterior" and h["sessao_teste_id"] is None and "sessao_teste" not in h
    # posse: outro usuário/bot não lê a sessão
    s, _j, _ = T._req("POST", URL + "/learning/sessao/painel", {"bot_id": x["id"]})
    assert s in (401, 403)


def test_8_termino_suspende_aberturas_e_preserva_a_gestao(amb, ses):
    x, b, sid = ses["x"], ses["b"], ses["id"]
    ok, mot, ab_b, _u = _res(sid, b, risco=6.0, reservar=True, dec="dec-fim", lado=1)
    assert ok is True
    T._pg("update sessao_aberturas set estado='aberta', ticket=888001, posicao_id=888001, ts_abertura=now(), stop_inicial=85600, stop_atual=85600 where id=%s", ab_b)
    T._pg("update sessoes_teste set fim_previsto = now() - interval '1 second' where id=%s", sid)
    time.sleep(5.5)
    mgb = T._magic(b["tok"])
    posb = [{"ticket": 888001, "posicao_id": 888001, "magic": mgb, "tipo": 0, "volume": 0.01, "preco_abertura": 86000.0, "sl": 85600.0, "tp": 0.0,
             "lucro": 1.0, "swap": 0.0, "aberta_corretora": int(time.time()) + OFF}]
    det, barra = _det(b, posicoes=posb)
    assert _snap(b, det, pos=1)[0] == 200
    assert _ses(sid, "motivo_suspensao") == "termino_previsto" and _ses(sid) == "ativa"          # posição aberta: a sessão segue gerindo
    assert _res(sid, x, risco=5.0)[1] in ("aberturas_suspensas(termino_previsto)", "sessao_no_termino_previsto(novas_aberturas_suspensas)")
    assert T._pg("select estado from sessao_aberturas where id=%s", ab_b)[0][0] == "aberta"
    time.sleep(5.5)
    negs = [{"ticket": 71, "ordem": 888001, "posicao_id": 888001, "magic": mgb, "tipo": 0, "entrada": 0, "volume": 0.01, "preco": 86000.0,
             "lucro": 0.0, "comissao": 0.0, "swap": 0.0, "taxa": 0.0, "motivo": 3, "hora_corretora": int(time.time()) + OFF - 900},
            {"ticket": 72, "ordem": 888002, "posicao_id": 888001, "magic": mgb, "tipo": 1, "entrada": 1, "volume": 0.01, "preco": 85600.0,
             "lucro": -4.0, "comissao": 0.0, "swap": 0.0, "taxa": 0.0, "motivo": 4, "hora_corretora": int(time.time()) + OFF - 3}]
    det, barra = _det(b, negocios=negs)
    assert _snap(b, det, pos=0)[0] == 200
    r = T._pg("select estado, resultado_usd, motivo_saida from sessao_aberturas where id=%s", ab_b)[0]
    assert r[0] == "fechada" and float(r[1]) == -4.0 and r[2] == "stop"
    assert _ses(sid) == "encerrada" and _ses(sid, "fim") is not None
    # depois de encerrada: registros novos NÃO entram na sessão; os da sessão continuam lá
    n = T._pg("select count(*) from ciclo_trilha where sessao_teste_id=%s", sid)[0][0]
    time.sleep(5.5)
    det, barra = _det(b)
    assert _snap(b, det)[0] == 200
    assert T._pg("select count(*) from ciclo_trilha where sessao_teste_id=%s", sid)[0][0] == n and n > 0
    p = _painel(amb, x, sid)["painel"]
    assert p["sessao"]["estado"] == "encerrada" and p["consolidado"]["contadores"]["resultado_usd"] == -0.59
