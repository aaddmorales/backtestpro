"""C27R19 — seleção de oportunidades M15/M30/H1 em MODO OBSERVAR. Testes SINTÉTICOS do avaliador
(api._sel_avaliar) com candidatos montados à mão; os estudos são os do banco local (cópia literal
de XAUUSD). O percurso real leitor → conector → API está em conector_homolog (test_h19)."""
import os, sys, time
from datetime import datetime, timezone, timedelta
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI); sys.path.insert(0, os.path.dirname(AQUI))
import test_ciclos_lm as T

amb = T.amb
OFF = 10800


@pytest.fixture(scope="module")
def api():
    os.environ.setdefault("BT_CV_SEGREDO", T.SEGREDO or "x")
    import api as _api
    return _api


def _cand(card, tf, lado, estado="confirmado", idade=1, ent=4100.0, stop=4090.0, sinal="2026-10-02 20:00:00", **kw):
    d = {"card": card, "nome": card, "tf": tf, "lado": lado, "estado": estado, "validade_m15": 4,
         "uid": f"{card}|{tf}|{sinal}|{lado}", "ts_sinal": sinal, "corte_ciclo_contra_agora": False}
    if estado == "confirmado":
        d.update(idade_m15=idade, entrada=ent, stop=stop, risco_pts=abs(ent - stop) / 0.01, ts_entrada_m15=sinal)
    else:
        d.update(modo="gatilho", nivel=ent, espera="armado no nível; só entra com continuidade", barras_desde_o_sinal=0)
    d.update(kw); return d


def _cenario(itens, barra_utc, dirs=None, veredito="neutra", jan=None, cv2=None, motor="ok", atest="verificado",
             preco=4100.2, spr=12, barra_cand=None, ativo="XAUUSD"):
    dirs = dirs or {"M1": 1, "M5": 1, "M15": 1, "M30": 1, "H1": 1, "H4": 1, "D1": 1}
    bc = barra_cand or (barra_utc - timedelta(seconds=900) + timedelta(seconds=OFF)).strftime("%Y-%m-%d %H:%M:%S")
    det = {"simbolo": ativo, "preco": str(preco), "spr": str(spr), "pt": "0.01",
           "cv_motor": {"estado": motor, "motivo": "teste", "off_ea_s": OFF,
                        "por_tf": {k: {"dir": v, "ultimo_topo": 4130.0, "ultimo_fundo": 4070.0} for k, v in dirs.items()},
                        "leitura": {"fase": {"fase": 3}, "janela_10_15": None},
                        "candidatos": {"versao": "cand-1", "ativo": ativo, "leitor": "1.3-hml",
                                       "codigo": {"cards": "2.0", "bloco2": "1.7", "bloco1": "3.2.B"},
                                       "barra_m15_corretora": bc, "territorio_h4_h1_m30": 0,
                                       "tfs": {tf: {"barra_corretora": bc} for tf in ("M15", "M30", "H1")}, "itens": itens}}}
    leit = {"barra_m15_utc": barra_utc.isoformat()}
    ciclos = {"atestado": {"estado": atest, "motivo": None if atest == "verificado" else "leitura_vencida(900s)",
                           "cv1": {"veredito": veredito, "motivo": "teste", "janela": jan or {"M1": 1, "M5": 1, "M15": 1}},
                           "cv2": {"dirs": cv2 or {"D1": dirs["D1"], "H4": dirs["H4"]}}}}
    return det, leit, ciclos


def _av(api, amb, itens, **kw):
    barra = T._barra_m15()
    det, leit, ciclos = _cenario(itens, barra, **kw)
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", amb["bots"]["A"]["id"]).execute().data[0]
    T._pg("delete from selecao_avaliacoes where bot_id=%s", bot["id"])
    return api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time())), sb, bot, (det, leit, ciclos)


def _todos(av):
    return [c for g in av["grupos"].values() for c in g["candidatos"]]


def test_1_oportunidade_valida_em_cada_escala_e_escolha_pelo_pf(api, amb):
    # células COM selo no estudo de XAUUSD: card2 M15 (PF 1,938), card2 M30 (PF 2,344), card10 M15 (PF 1,201)
    av, *_ = _av(api, amb, [_cand("card2_rompimento_caixa", "M15", 1), _cand("card2_rompimento_caixa", "M30", 1),
                             _cand("card10_donchian20", "M15", 1)], veredito="autorizada",
                 jan={"M1": 1, "M5": 1, "M15": 1}, cv2={"D1": 1, "H4": 1})
    t = _todos(av)
    assert [c["elegibilidade"] for c in t] == ["elegivel"] * 3
    assert av["escolha"]["card"] == "card2_rompimento_caixa" and av["escolha"]["timeframe"] == "M30"   # maior PF, não o TF menor
    pret = [c for c in t if not c["escolha"]["escolhido"]]
    assert len(pret) == 2 and all(c["escolha"]["motivo"].startswith("preterido") for c in pret)
    assert av["resumo"]["elegiveis_proposto"] == 3 == av["resumo"]["elegiveis_atual"]
    assert all(c["estudo"]["estudo_id"].startswith("v2:") and "probabilidade" in c["estudo"]["nota"] for c in t)


def test_2_contexto_superior_contrario_informa_no_proposto_e_veta_no_atual(api, amb):
    dirs = {"M1": -1, "M5": -1, "M15": -1, "M30": -1, "H1": -1, "H4": 0, "D1": 1}     # D1 contra a venda (caso real do BTC)
    av, *_ = _av(api, amb, [_cand("card2_rompimento_caixa", "M30", -1, ent=4100.0, stop=4110.0)], dirs=dirs,
                 veredito="bloqueada", jan={"M1": -1, "M5": -1, "M15": -1}, cv2={"D1": 1, "H4": 0}, preco=4099.8)
    c = _todos(av)[0]
    assert c["elegibilidade"] == "elegivel" and c["escolha"]["escolhido"] is True
    assert c["contexto_superior"]["D1"] == "contra" and "contratendência" in c["contexto_superior"]["resumo"]
    assert c["configuracao_atual"]["autorizaria"] is False and "bloqueada" in c["configuracao_atual"]["motivo"]
    assert av["resumo"]["elegiveis_proposto"] == 1 and av["resumo"]["elegiveis_atual"] == 0
    assert av["escolha_atual"] is None


def test_3_nenhuma_oportunidade_e_pontuacao_nao_compensa_portao(api, amb):
    av, *_ = _av(api, amb, [])
    assert av["escolha"] is None and av["resumo"]["conclusao"] == "nenhuma oportunidade elegível"
    # melhor PF do banco (card2 M30) com o Ciclo cortando o lado: fica VETADA e a de PF menor é a escolhida
    av, *_ = _av(api, amb, [_cand("card2_rompimento_caixa", "M30", 1, corte_ciclo_contra_agora=True),
                             _cand("card10_donchian20", "M15", 1)])
    por = {c["estrategia"]["card"]: c for c in _todos(av)}
    assert por["card2_rompimento_caixa"]["elegibilidade"] == "vetada"
    assert por["card2_rompimento_caixa"]["primeiro_impedimento"].startswith("4.")
    assert av["escolha"]["card"] == "card10_donchian20"
    # estudo sem selo, sinal velho, Ciclo da escala contra, custo alto, preço longe, aguardando gatilho
    av, *_ = _av(api, amb, [
        _cand("card7_rsi", "M15", 1),                                       # PF 1,003 e 2ª metade 0,81 → sem selo
        _cand("card2_rompimento_caixa", "M15", 1, idade=3),                 # sinal velho
        _cand("card10_donchian20", "M15", -1, ent=4100.0, stop=4110.0),     # continuação de venda com canal M15 de alta
        _cand("card2_rompimento_caixa", "M30", 1, ent=4100.0, stop=4099.8, sinal="2026-10-02 19:30:00"),   # risco 20 pts, spread 12
        _cand("card12_engolfo", "M30", 1, ent=4050.0, stop=4040.0),         # preço a 5050 pts da entrada
        _cand("card11_sr_dia_anterior", "M15", 1, estado="aguardando")])
    imp = {c["uid"].split("|")[0] + c["timeframe"]: (c["elegibilidade"], (c["primeiro_impedimento"] or "")[:2]) for c in _todos(av)}
    assert imp["card7_rsiM15"] == ("vetada", "5.")
    assert imp["card2_rompimento_caixaM15"] == ("vetada", "3.")
    assert imp["card10_donchian20M15"] == ("vetada", "6.")
    assert imp["card2_rompimento_caixaM30"] == ("vetada", "7.")
    assert imp["card12_engolfoM30"] == ("vetada", "8.")
    assert imp["card11_sr_dia_anteriorM15"] == ("aguardando", "2.")
    assert av["escolha"] is None


def test_4_dado_vencido_ou_desencontrado_vira_sem_dados(api, amb):
    it = [_cand("card2_rompimento_caixa", "M15", 1)]
    for kw, trecho in (({"atest": "recusado"}, "atestado recusado"), ({"motor": "espelho_atrasado"}, "motor espelho_atrasado"),
                       ({"barra_cand": "2026-01-01 00:00:00"}, "≠ barra M15 do EA"), ({"ativo": "BTCUSD"}, "o bot é XAUUSD")):
        det_kw = dict(kw)
        av, sb, bot, (det, leit, ciclos) = _av(api, amb, it, **det_kw)
        if "ativo" in kw:                                   # candidatos de outro ativo chegando no bot de XAUUSD
            assert av["integridade"]["ok"] is False
        c = _todos(av)[0]
        assert c["elegibilidade"] == "sem_dados" and av["escolha"] is None, kw
        assert any(trecho in m for m in av["integridade"]["motivos"]), (kw, av["integridade"])
    av, *_ = _av(api, amb, [_cand("card_que_nao_existe", "M15", 1)])
    assert _todos(av)[0]["elegibilidade"] == "sem_dados" and _todos(av)[0]["estudo"]["existe"] is False


def test_5_troca_de_candidato_reinicio_e_duplicacao_entre_barras(api, amb):
    b = amb["bots"]["A"]
    a1 = _cand("card10_donchian20", "M15", 1, sinal="2026-10-02 20:00:00")
    av, sb, bot, (det, leit, ciclos) = _av(api, amb, [a1])
    assert av["escolha"]["card"] == "card10_donchian20"
    barra_ant = T._barra_m15(int(time.time()) - 900)
    T._pg("insert into selecao_avaliacoes (bot_id, simbolo, barra_m15, versao, escolha_uid, avaliacao) values (%s,'XAUUSD',%s,'sel-1',%s,'{}')",
          b["id"], barra_ant, a1["uid"])
    # barra seguinte: o MESMO sinal continua fresco e aparece um candidato melhor em outro TF
    a2 = _cand("card2_rompimento_caixa", "M30", 1, sinal="2026-10-02 20:30:00")
    det2, leit2, ciclos2 = _cenario([a1, a2], T._barra_m15())
    av2 = api._sel_avaliar(sb, bot, det2, leit2, ciclos2, int(time.time()))
    por = {c["estrategia"]["card"]: c for c in _todos(av2)}
    assert por["card10_donchian20"]["elegibilidade"] == "vetada" and por["card10_donchian20"]["primeiro_impedimento"].startswith("9.")
    assert av2["escolha"]["card"] == "card2_rompimento_caixa"
    # reinício: a avaliação gravada para a barra não é refeita nem duplicada
    n0 = T._pg("select count(*) from selecao_avaliacoes where bot_id=%s", b["id"])[0][0]
    orig = api._clm_avaliar
    api._clm_avaliar = lambda *_a, **_k: (leit2, ciclos2)
    try:
        r1 = api._sel_ingerir(sb, bot, det2); r2 = api._sel_ingerir(sb, bot, det2)
    finally:
        api._clm_avaliar = orig
    assert r1 is not None and r2 is None
    assert T._pg("select count(*) from selecao_avaliacoes where bot_id=%s", b["id"])[0][0] == n0 + 1
    assert T._pg("select count(*) from ciclo_decisoes where bot_id=%s", b["id"])[0][0] == 0


def test_6_acompanhamento_prospectivo_e_observacao_nao_operacao(api, amb):
    b = amb["bots"]["B"]
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    T._pg("delete from selecao_avaliacoes where bot_id=%s", b["id"])
    agora = int(time.time())
    barra = T._barra_m15(agora - 10 * 900)                                  # avaliada há 10 barras
    av = {"grupos": {"M15": {"candidatos": [{"uid": "u1", "lado_num": 1, "elegibilidade": "elegivel",
                                             "escolha": {"escolhido": True}, "niveis": {"entrada": 100.0, "stop": 99.0}}]}}}
    T._pg("insert into selecao_avaliacoes (bot_id, simbolo, barra_m15, versao, avaliacao) values (%s,'XAUUSD',%s,'sel-1',%s::jsonb)",
          b["id"], barra, __import__("json").dumps(av))
    n = 18; ab_form = (agora // 900) * 900
    velas = []
    for k in range(n):
        ab = ab_form - 900 * (n - 1 - k)
        dentro = barra.timestamp() <= ab < barra.timestamp() + 8 * 900
        velas.append("100.00,102.50,99.40,101.00,10" if dentro else "100.00,100.10,99.90,100.00,10")
    det = {"c15m": ";".join(velas), "tsrv": str(agora + OFF), "tgmt": str(agora),
           "cvt0": ".".join(["0"] * 6 + [str(ab_form + OFF)] + ["0", "0"])}
    api._SEL_ACOMP_MEM.clear()
    api._sel_acompanhar(sb, bot, det)
    ac = T._pg("select acompanhamento from selecao_avaliacoes where bot_id=%s", b["id"])[0][0]
    assert ac["itens"]["u1"] == {"elegibilidade": "elegivel", "escolhido": True, "a_favor_max_R": 2.5,
                                 "contra_max_R": 0.6, "tocou_o_stop": False, "fim_da_janela_R": 1.0}
    assert "NÃO é operação" in ac["nota"]
