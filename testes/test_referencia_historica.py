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
    assert j["situacao"] == "com_estudo"
    e = [x for x in j["estudos"] if x["banco"] == "estudo_biblioteca_v2"][0]
    linha = T._pg("select id, trades, win_rate, profit_factor, sharpe, retorno, dd, wf_a_pf, wf_b_pf, periodo "
                  "from estudo_biblioteca_v2 where ativo='XAUUSD' and timeframe='M15' and estrategia_id='card10_donchian20'")[0]
    m = e["metricas"]
    assert e["estudo_id"] == f"v2:{linha[0]}" == "v2:2601"
    assert (m["trades"], m["win_rate_pct"], m["profit_factor"], m["sharpe"], m["retorno"], m["drawdown"]) == linha[1:7]
    assert (e["fora_da_amostra"]["wf_a_pf"], e["fora_da_amostra"]["wf_b_pf"]) == linha[7:9] and e["periodo"] == linha[9]
    assert m["retorno_unidade"] == "pontos" and e["custos"]["comissao"] == "não registrado" == e["custos"]["slippage"]
    assert e["custos"]["spread"].startswith("5 pts fixos") and e["versao"]["professor"] == "cards 1.9"
    assert e["correspondencia"]["nivel"] == "identico" and e["correspondencia"]["parametros"].startswith("DIFERENTES")
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
    assert cel["forca"] == e["fora_da_amostra"]["selo_admin"]
    pos_admin = [(t["id"], t["tf"]) for t in adm["tops"]].index(("card10_donchian20", "M15")) + 1
    assert e["ranking"]["posicao"] == pos_admin == 9 and e["ranking"]["no_top10_do_admin"] is True
    assert "Sharpe" in e["ranking"]["criterio"]
    assert any("comissão e slippage não registrados" in x for x in j["limitacoes"])
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
    assert any("sem correspondência declarada" in a for a in j["avisos"])


def test_4_painel_separa_as_tres_informacoes_e_exporta_o_estudo(amb):
    b = amb["bots"]["B"]
    barra = T._barra_m15()
    T._pg("delete from ciclo_trilha where bot_id=%s", b["id"]); T._pg("delete from ciclo_leituras where bot_id=%s", b["id"])
    s, _, _ = T._snap(b["tok"], T._det(b["tok"])); assert s == 200
    j, raw = T._ao_vivo(amb, b["id"])
    R = j["referencia_historica"]
    assert set(R) == {"desempenho_historico", "pontuacao_checklist", "autorizacao_operacional"}
    assert R["desempenho_historico"]["situacao"] == "com_estudo"
    assert R["autorizacao_operacional"]["estudo_influenciou"] is False
    assert R["autorizacao_operacional"]["regra"] == j["ciclos"]["consolidada"]["regra"]
    assert "prontidao_pct" in R["pontuacao_checklist"] or "mensagem" in R["pontuacao_checklist"]
    s, ex, rawx = T._req("POST", T.E["BT_ISO_API"] + "/learning/ciclos/exportar",
                         {"bot_id": b["id"], "barra_m15": barra.isoformat()}, tok=amb["sess"])
    assert s == 200
    nb = ex["estudo_referencia"]["na_barra"]
    assert nb["situacao"] == "com_estudo" and nb["papel"] == "referência informativa"
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
    assert et.count(("snapshot", "aviso")) == 1                                  # registrado uma única vez
    assert [e for e, _ in et].count("atestado") == 1 and [e for e, _ in et].count("veto") == 1
