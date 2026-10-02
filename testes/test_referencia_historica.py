"""C27R15 — Referência histórica da estratégia na BabyMachine, contra o ambiente
isolado local. O banco v2 local contém a CÓPIA LITERAL do estudo de XAUUSD da
produção (sql/0006, md5 conferido). Nenhum número é criado nos testes: os valores
esperados são lidos do próprio banco e da rota do Admin (/admin/estudo/v2/ler)."""
import json, os, sys, time
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI); sys.path.insert(0, os.path.dirname(AQUI))
import test_ciclos_lm as T

amb = T.amb
MD5_METRICAS_PRODUCAO = "0c6fa03734f43eab8bd5d235640c1ae1"


def _cfg(bot_id, cfg):
    T._pg("update conector_bots set config_operacional=%s::jsonb where id=%s", json.dumps(cfg), bot_id)


def _ref(amb, bot_id):
    s, j, raw = T._req("POST", T.E["BT_ISO_API"] + "/learning/estudo/referencia", {"bot_id": bot_id}, tok=amb["sess"])
    assert s == 200, j
    return j, raw


def test_0_copia_do_estudo_identica_a_producao():
    r = T._pg("select count(*), md5(string_agg(id||'|'||timeframe||'|'||estrategia_id||'|'||coalesce(retorno::text,'')||'|'"
              "||coalesce(profit_factor::text,'')||'|'||coalesce(win_rate::text,'')||'|'||coalesce(sharpe::text,'')||'|'"
              "||coalesce(trades::text,'')||'|'||coalesce(dd::text,'')||'|'||coalesce(wf_a_pf::text,'')||'|'"
              "||coalesce(wf_b_pf::text,''), ';' order by id)) from estudo_biblioteca_v2 where ativo='XAUUSD'")
    assert r[0] == (55, MD5_METRICAS_PRODUCAO)


def test_1_master_sem_estudo_associado(amb):
    b = amb["bots"]["A"]
    _cfg(b["id"], {"estrategia_id": "teste_integracao_mt5", "estrategia_nome": "MASTER TESTE MT5 — DEMO",
                   "ativo_envio": "XAU/USD (Ouro)", "timeframe_envio": "15m"})
    j, raw = _ref(amb, b["id"])
    assert j["situacao"] == "master_sem_estudo" and j["mensagem"] == "MASTER sem estudo de estratégia associado"
    assert j["estudos"] == [] and "profit_factor" not in raw.decode()        # nenhum desempenho de outro card
    assert j["participacao_na_decisao"]["papel"] == "referência informativa"
    assert j["regime"]["disponivel"] is False
    assert b["tok"].encode() not in raw


def test_2_bot_com_estudo_confere_com_o_admin(amb):
    b = amb["bots"]["B"]
    _cfg(b["id"], {"estrategia_id": "rompimento_donchian", "estrategia_nome": "Rompimento Donchian 20",
                   "ativo_envio": "XAU/USD (Ouro)", "timeframe_envio": "15m", "sl_envio_pts": 50, "tp_envio_pts": 75,
                   "codigo_sha1": "a" * 40})
    j, raw = _ref(amb, b["id"])
    # vínculo Vitrine × card do Professor é por NOME: nunca aparece como desempenho do bot
    assert j["situacao"] == "correspondencia_nao_comprovada" and "NÃO COMPROVADA" in j["mensagem"]
    e = [x for x in j["estudos"] if x["banco"] == "estudo_biblioteca_v2"][0]
    linha = T._pg("select id, trades, win_rate, profit_factor, sharpe, retorno, dd, wf_a_pf, wf_b_pf, periodo "
                  "from estudo_biblioteca_v2 where ativo='XAUUSD' and timeframe='M15' and estrategia_id='card10_donchian20'")[0]
    m = e["metricas"]
    assert e["estudo_id"] == f"v2:{linha[0]}" == "v2:2601"
    assert (m["trades"], m["win_rate_pct"], m["profit_factor"], m["sharpe"], m["retorno"], m["drawdown"]) == linha[1:7]
    # o que o banco chama de walk-forward são as duas METADES do período: não é fora da amostra
    assert e["fora_da_amostra"] == {"existe": False, "tipo": "não registrado"}
    em = e["estabilidade_em_metades"]
    assert (em["pf_metade_1"], em["pf_metade_2"]) == linha[7:9] and e["periodo"] == linha[9]
    assert "NÃO é avaliação fora da amostra" in em["tipo"]
    assert m["retorno_unidade"] == "pontos" and e["custos"]["comissao"] == "não registrado" == e["custos"]["slippage"]
    assert e["custos"]["spread"].startswith("5 pts fixos") and e["versao"]["professor"] == "cards 1.9"
    c = e["correspondencia"]
    assert c["nivel"] == "nao_comprovada" and c["parametros"].startswith("DIFERENTES")
    assert c["implementacao"]["entrada"] == "diferente" and c["implementacao"]["saida"] == "diferente"
    assert "cards 1.9" in c["implementacao"]["comparado_com"]
    assert e["por_regime"] is None
    assert j["regime"]["mensagem"] == "O estudo contém desempenho agregado; não permite estimar desempenho neste regime."
    # MESMOS valores e MESMA ordem que a aba Estudo do Admin (rota real, sessão do admin simulada em processo)
    os.environ.setdefault("BT_CV_SEGREDO", T.SEGREDO or "x")
    import api
    orig = api._sessao_user_id
    api._sessao_user_id = lambda a="": api._BIB_ADMIN_USER_ID
    try:
        adm = api.admin_estudo_v2_ler(api.EstudoV2LerReq(ativo="XAUUSD"), authorization="")
    finally:
        api._sessao_user_id = orig
    cel = [l for l in adm["linhas"] if l["id"] == "card10_donchian20"][0]["cels"]["M15"]
    assert (cel["trades"], cel["wr"], cel["pf"], cel["sharpe"], cel["retorno"], cel["dd"]) == \
           (m["trades"], m["win_rate_pct"], m["profit_factor"], m["sharpe"], m["retorno"], m["drawdown"])
    assert cel["forca"] == em["selo_admin"]
    pos_admin = [(t["id"], t["tf"]) for t in adm["tops"]].index(("card10_donchian20", "M15")) + 1
    assert e["ranking"]["posicao"] == pos_admin == 9 and e["ranking"]["no_top10_do_admin"] is True
    assert "Sharpe" in e["ranking"]["criterio"]
    assert any("comissão e slippage não registrados" in x for x in j["limitacoes"])
    assert any("sem avaliação fora da amostra" in x for x in j["limitacoes"])
    assert b["tok"].encode() not in raw


def test_3_sem_identidade_e_sem_correspondencia(amb):
    c = amb["bots"]["C"]
    _cfg(c["id"], {"estrategia_nome": "Executor BotTested"})
    j, _ = _ref(amb, c["id"])
    assert j["situacao"] == "sem_identidade" and j["estudos"] == []
    _cfg(c["id"], {"estrategia_id": "fibonacci_retracao", "estrategia_nome": "Fibonacci — Retração (Golden Zone)",
                   "ativo_envio": "XAU/USD (Ouro)", "timeframe_envio": "15m"})
    j, _ = _ref(amb, c["id"])
    assert j["situacao"] == "sem_correspondencia" and j["estudos"] == []
    assert any("sem card do banco v2 relacionado" in a for a in j["avisos"])


def test_4_painel_separa_as_tres_informacoes_e_exporta_o_estudo(amb):
    b = amb["bots"]["B"]
    barra = T._barra_m15()
    T._pg("delete from ciclo_trilha where bot_id=%s", b["id"]); T._pg("delete from ciclo_leituras where bot_id=%s", b["id"])
    s, _, _ = T._snap(b["tok"], T._det(b["tok"])); assert s == 200
    j, raw = T._ao_vivo(amb, b["id"])
    R = j["referencia_historica"]
    assert set(R) == {"desempenho_historico", "pontuacao_checklist", "autorizacao_operacional"}
    assert R["desempenho_historico"]["situacao"] == "correspondencia_nao_comprovada"
    assert R["autorizacao_operacional"]["estudo_influenciou"] is False
    assert R["autorizacao_operacional"]["regra"] == j["ciclos"]["consolidada"]["regra"]
    assert "prontidao_pct" in R["pontuacao_checklist"] or "mensagem" in R["pontuacao_checklist"]
    s, ex, rawx = T._req("POST", T.E["BT_ISO_API"] + "/learning/ciclos/exportar",
                         {"bot_id": b["id"], "barra_m15": barra.isoformat()}, tok=amb["sess"])
    assert s == 200
    nb = ex["estudo_referencia"]["na_barra"]
    assert nb["situacao"] == "correspondencia_nao_comprovada" and nb["papel"] == "referência informativa"
    v2 = [x for x in nb["estudos"] if x["banco"] == "estudo_biblioteca_v2"][0]
    assert v2["estudo_id"] == "v2:2601" and v2["versao"]["professor"] == "cards 1.9" and v2["versao"]["motor"] == "3.2.B"
    assert ex["estudo_referencia"]["atual"]["estudos"][0]["estudo_id"] == "v2:2601"
    assert b["tok"].encode() not in rawx
    # a decisão da barra NÃO mudou por existir estudo: continua vindo do R-CICLO-01
    assert j["ciclos"]["consolidada"]["regra"] == "R-CICLO-01.atestado"


def test_5_snapshot_apos_a_validade_nao_reescreve_a_decisao(amb):
    d = amb["bots"]["D"]
    T._pg("delete from ciclo_trilha where bot_id=%s", d["id"]); T._pg("delete from ciclo_leituras where bot_id=%s", d["id"])
    velho = int(time.time()) - 1000                       # EA ainda carimbando a barra anterior
    barra = T._barra_m15(velho)
    for _ in range(3):
        s, _, _ = T._snap(d["tok"], T._det(d["tok"], agora=velho)); assert s == 200
    assert T._pg("select n_snapshots from ciclo_leituras where bot_id=%s and barra_m15=%s", d["id"], barra)[0][0] == 3
    et = T._pg("select etapa, estado from ciclo_trilha where bot_id=%s and barra_m15=%s order by id", d["id"], barra)
    assert et.count(("snapshot", "aviso")) == 1                                  # um aviso por ESTADO distinto
    assert [e for e, _ in et].count("atestado") == 1 and [e for e, _ in et].count("veto") == 1


def test_6_pontuacao_veto_e_autorizacao_separados(amb):
    """Prontidão % é medida; veto é portão FECHADO; autorização exige os 8 avaliados e abertos."""
    b = amb["bots"]["B"]
    s, _, _ = T._snap(b["tok"], T._det(b["tok"])); assert s == 200
    j, raw = T._ao_vivo(amb, b["id"])
    A = j["referencia_historica"]["autorizacao_operacional"]; K = j["referencia_historica"]["pontuacao_checklist"]
    P = A["portoes"]
    assert [p["portao"][:2] for p in P] == [f"{i}." for i in range(1, 9)]          # ordem de aplicação
    por = {p["portao"][0]: p for p in P}
    assert por["1"]["aberto"] is False and "observar" in por["1"]["detalhe"]        # bot novo nasce em observar
    assert por["7"]["aberto"] is False and "R-CICLO-01.atestado" in por["7"]["detalhe"]
    assert por["4"]["aberto"] is None and por["5"]["aberto"] is None and por["8"]["aberto"] is None
    assert A["primeiro_fechado"].startswith("1.") and A["todos_abertos"] is False
    assert set(A["nao_avaliados_aqui"]) == {por[k]["portao"] for k in "458"}
    # pontuação alta NÃO vira autorização: o checklist tem % e mesmo assim a barra está vetada
    assert isinstance(K["prontidao_pct"], int) and por["6"]["aberto"] == K["pode_entrar"]
    assert "papel" in K and A["decisao"] == "bloquear" and A["estudo_influenciou"] is False
    # ler o quadro NÃO cria estado no servidor (sem efeito colateral nos disjuntores/config/histórico)
    assert b["tok"].encode() not in raw


def test_7_decisao_da_barra_preservada_e_falha_atual_visivel(amb):
    """Barra anterior terminou com o atestado RECUSADO por um motivo; depois da validade o EA
    segue carimbando a mesma barra com OUTRO estado. A decisão registrada não muda e a
    situação de agora aparece separada (com o elo em falha)."""
    d = amb["bots"]["D"]
    T._pg("delete from ciclo_trilha where bot_id=%s", d["id"]); T._pg("delete from ciclo_leituras where bot_id=%s", d["id"])
    velho = int(time.time()) - 1000
    barra = T._barra_m15(velho)
    s, _, _ = T._snap(d["tok"], T._det(d["tok"], agora=velho)); assert s == 200
    antes = T._pg("select decisao, regra, motivo, falhas->'atestado_ult'->>'estado' from ciclo_leituras "
                  "where bot_id=%s and barra_m15=%s", d["id"], barra)[0]
    for _ in range(2):
        s, _, _ = T._snap(d["tok"], T._det(d["tok"], agora=velho)); assert s == 200
    depois = T._pg("select decisao, regra, motivo, falhas->'atestado_ult'->>'estado', falhas->'pos_validade'->>'n' "
                   "from ciclo_leituras where bot_id=%s and barra_m15=%s", d["id"], barra)[0]
    assert depois[:4] == antes and depois[4] == "2"                              # decisão intacta; 2 pós-validade contados
    j, _ = T._ao_vivo(amb, d["id"])
    B = j["barra_registrada"]
    assert (B["registrada"]["decisao"], B["registrada"]["regra"], B["registrada"]["motivo"]) == antes[:3]
    assert B["validade"]["encerrada"] is True and B["validade"]["restam_s"] < 0
    assert B["registrada"]["pos_validade"]["n"] == 2 and len(B["registrada"]["pos_validade"]["estados"]) == 1
    # a falha de AGORA não é escondida pela barra registrada
    assert B["integracao_agora"]["falha"] is True and B["integracao_agora"]["elo_em_falha"].startswith("1.")
    assert T._pg("select count(*) from ciclo_decisoes where bot_id=%s", d["id"])[0][0] == 0


def test_8_banco_da_fabrica_so_e_comprovado_por_hash(amb):
    """estudo_biblioteca (fábrica): mesmo id da Vitrine NÃO basta. Só é 'comprovada' quando o
    codigo_hash do estudo e o codigo_sha1 do envio batem com o código atual do card e
    stop/alvo são os mesmos. Linhas reais do banco local (cópia), nenhum número criado."""
    import hashlib
    os.environ.setdefault("BT_CV_SEGREDO", T.SEGREDO or "x")
    import api
    cod = next(x["codigo"] for x in api.ESTRATEGIAS_PRONTAS if x["id"] == "rompimento_donchian")
    h256 = hashlib.sha256(cod.encode("utf-8", "ignore")).hexdigest()[:16]
    linhas = T._pg("select codigo_hash, (parametros->>'stop_loss')::float, (parametros->>'take_profit')::float "
                   "from estudo_biblioteca where ativo='EUR/USD' and timeframe='15m' and estrategia_id='rompimento_donchian'")
    assert linhas, "banco v1 local sem EUR/USD 15m rompimento_donchian"
    estudo_bate = all(l[0] == h256 for l in linhas)
    sl, tp = linhas[0][1], linhas[0][2]
    c = amb["bots"]["C"]
    base = {"estrategia_id": "rompimento_donchian", "estrategia_nome": "Rompimento Donchian 20",
            "ativo_envio": "EUR/USD", "timeframe_envio": "15m", "sl_envio_pts": sl, "tp_envio_pts": tp}
    _cfg(c["id"], dict(base, codigo_sha1=hashlib.sha1(cod.encode("utf-8")).hexdigest()))
    j, _ = _ref(amb, c["id"])
    e1 = [x for x in j["estudos"] if x["banco"] == "estudo_biblioteca"][0]
    im = e1["correspondencia"]["implementacao"]
    assert im["estudo_mediu_o_codigo_atual_do_card"] is estudo_bate and im["bot_enviado_com_o_codigo_atual_do_card"] is True
    assert e1["correspondencia"]["nivel"] == ("comprovada" if estudo_bate else "nao_comprovada")
    _cfg(c["id"], dict(base, codigo_sha1="b" * 40))                               # bot enviado com OUTRO código
    j, _ = _ref(amb, c["id"])
    e1 = [x for x in j["estudos"] if x["banco"] == "estudo_biblioteca"][0]
    assert e1["correspondencia"]["nivel"] == "nao_comprovada"
    assert e1["correspondencia"]["implementacao"]["bot_enviado_com_o_codigo_atual_do_card"] is False
    assert j["situacao"] != "com_estudo" or any((x.get("correspondencia") or {}).get("nivel") == "comprovada" for x in j["estudos"])


def test_9_ranking_demonstrativo_marcado():
    s, j, _ = T._req("GET", T.E["BT_ISO_API"] + "/ranking", None)
    assert s == 200 and j["demonstracao"] is True and "aviso" in j


def test_10_corrida_da_virada_nao_reescreve_a_decisao(amb):
    """Visto na plataforma (02/out, 19:30:00 UTC): a ingestão começou antes do fim da validade e a
    verificação rodou depois; a decisão 'observar' virou 'bloquear leitura_vencida'. Aqui o relógio
    do INÍCIO da ingestão é forçado para 1 s antes do fim da validade."""
    import hashlib
    os.environ.setdefault("BT_CV_SEGREDO", T.SEGREDO or "x")
    import api, bt_cv_atestado as cvat
    a = amb["bots"]["A"]
    T._pg("delete from ciclo_trilha where bot_id=%s", a["id"]); T._pg("delete from ciclo_leituras where bot_id=%s", a["id"])
    fim = (int(time.time()) // 900) * 900                  # fim da validade da barra anterior (já passou)
    ea = fim - 1                                           # o EA ainda carimba a barra anterior
    barra = T._barra_m15(ea)
    at = cvat.assinar({"bot_token_hash": hashlib.sha256(a["tok"].encode()).hexdigest(), "versao_motor": "teste-bancada",
                       "simbolo": "XAUUSD", "magic": T._magic(a["tok"]), "ts_barra_m15": barra.isoformat(),
                       "cv1": {"janela": {"M1": 1, "M5": 1, "M15": 0}, "veredito": "neutra", "motivo": "referencia_neutra"},
                       "cv2": {"dirs": {"D1": -1, "H4": -1}}}, segredo=T.SEGREDO)
    s, _, _ = T._snap(a["tok"], T._det(a["tok"], agora=ea, extra={"cv_atestado": at})); assert s == 200
    antes = T._pg("select decisao, regra, motivo from ciclo_leituras where bot_id=%s and barra_m15=%s", a["id"], barra)[0]
    det2 = T._det(a["tok"], agora=ea)                      # snapshot seguinte: SEM atestado (outro estado)
    s, _, _ = T._snap(a["tok"], det2); assert s == 200
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", a["id"]).execute().data[0]
    chamadas = []
    real = api._clm_agora_s
    api._clm_agora_s = lambda: (chamadas.append(1), (fim - 1) if len(chamadas) == 1 else real())[1]
    try:
        api._clm_ingerir(sb, bot, None, dict(det2, tgmt=str(int(det2["tgmt"]) + 1)))
    finally:
        api._clm_agora_s = real
    assert len(chamadas) >= 2                              # o relógio foi lido de novo depois da verificação
    depois = T._pg("select decisao, regra, motivo, (falhas->'pos_validade'->>'n')::int from ciclo_leituras "
                   "where bot_id=%s and barra_m15=%s", a["id"], barra)[0]
    assert depois[:3] == antes and depois[3] >= 2
