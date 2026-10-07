"""C27R22 — D1/H4 como CONTEXTO na seleção M15/M30/H1 (contrato sel-2). Testes SINTÉTICOS do avaliador
(api._sel_avaliar) com candidatos montados à mão; estudos = banco local (cópia literal de XAUUSD).
Células COM selo usadas: card2_rompimento_caixa M15 e M30, card10_donchian20 M15. Nada aqui é evidência da plataforma."""
import os, sys, time
from datetime import datetime, timedelta, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI); sys.path.insert(0, os.path.dirname(AQUI))
import test_ciclos_lm as T
import test_selecao as S

amb = T.amb
api = S.api
D1_ALTA = {"M1": -1, "M5": -1, "M15": -1, "M30": -1, "H1": -1, "H4": 1, "D1": 1}
D1_BAIXA = {"M1": 1, "M5": 1, "M15": 1, "M30": 1, "H1": 1, "H4": -1, "D1": -1}


def _venda(card, tf, **kw):
    return S._cand(card, tf, -1, ent=4100.0, stop=4110.0, **kw)


def test_1_venda_nos_tempos_menores_com_d1_e_h4_em_alta_e_so_contexto(api, amb):
    av, *_ = S._av(api, amb, [_venda("card2_rompimento_caixa", "M15"), _venda("card2_rompimento_caixa", "M30")],
                   dirs=D1_ALTA, veredito="bloqueada", jan={"M1": -1, "M5": -1, "M15": -1}, cv2={"D1": 1, "H4": 1}, preco=4099.8)
    t = S._todos(av)
    assert [c["elegibilidade"] for c in t] == ["elegivel", "elegivel"]                 # demais portões abertos: D1/H4 não fecham nada
    assert all(p["ok"] is True for c in t for p in c["portoes"])
    assert not any("D1" in p["portao"] or "H4" in p["portao"] for c in t for p in c["portoes"])    # não existe portão de D1/H4
    m30 = next(c for c in t if c["timeframe"] == "M30")
    assert m30["contexto_superior"]["frases"][-1] == ("D1: canal de alta na última barra fechada; candidato: venda em M30; "
                                                      "sentidos opostos — contexto, sem veto automático.")
    assert m30["contexto_superior"]["D1"] == "sentidos opostos" and m30["contexto_superior"]["H1"] == "mesmo sentido"
    assert "não exige alinhamento" in m30["contexto_superior"]["exigencia_do_card"]
    ef = {(m["condicao"], m["efeito"], m["onde"]) for m in m30["motivos"]}
    assert ("D1 em sentido oposto", "informa", "seleção (sel-2)") in ef and ("H4 em sentido oposto", "informa", "seleção (sel-2)") in ef
    assert ("autoridade em vigor não autorizaria este lado", "bloqueia a execução", "autoridade (R-CICLO-01 r01v4)") in ef
    assert ("bot em modo observar", "bloqueia a execução", "modo operacional do bot") in ef
    assert not any(m["efeito"] == "bloqueia" for m in m30["motivos"])                  # nada bloqueia a SELEÇÃO
    aut = next(m for m in m30["motivos"] if m["onde"].startswith("autoridade"))
    assert aut["categoria"] == "D1/H4 contra o M15 (veto do contrato em vigor)" and m30["autoridade_em_vigor"]["bloqueio_por_d1_h4"] is True
    assert av["escolha"] is not None and av["escolha_atual"] is None
    assert av["resumo"]["elegiveis_proposto"] == 2 and av["resumo"]["elegiveis_atual"] == 0
    assert av["resumo"]["elegiveis_em_sentido_oposto_a_d1_ou_h4"] == 2
    # contratos nomeados; a seleção NÃO é apresentada como operacional
    K = av["contratos"]
    assert av["versao"] == "sel-2" == K["selecao"]["id"] and K["autoridade"]["id"] == "R-CICLO-01 r01v4"
    assert K["selecao_e_operacional"] is False and "NÃO operacional" in K["selecao"]["estado"] and K["autoridade"]["estado"] == "em vigor"
    assert K["autoridade_nesta_barra"] == {"veredito_do_motor": "bloqueada", "motivo_do_motor": "teste", "vetou_por_d1_h4": True}
    assert all(c["execucao"]["decisao"] is None for c in t)


def test_2_compra_com_d1_em_baixa_e_so_contexto(api, amb):
    av, *_ = S._av(api, amb, [S._cand("card2_rompimento_caixa", "M15", 1), S._cand("card10_donchian20", "M15", 1)],
                   dirs=D1_BAIXA, veredito="bloqueada", cv2={"D1": -1, "H4": -1})
    t = S._todos(av)
    assert [c["elegibilidade"] for c in t] == ["elegivel", "elegivel"]
    c = t[0]
    assert c["contexto_superior"]["frases"][-1] == ("D1: canal de baixa na última barra fechada; candidato: compra em M15; "
                                                    "sentidos opostos — contexto, sem veto automático.")
    assert c["contexto_superior"]["frases"][0].startswith("M30: canal de alta na última barra fechada; candidato: compra em M15; mesmo sentido")
    assert "sentido oposto ao de D1 e H4 (contexto)" == c["contexto_superior"]["resumo"]


def test_3_com_outro_portao_fechado_o_veto_e_o_motivo_verdadeiro(api, amb):
    """D1 em alta contra a venda E um portão real fechado: o motivo do veto é o portão, nunca o D1."""
    av, *_ = S._av(api, amb, [_venda("card2_rompimento_caixa", "M30", idade=5),                # sinal vencido
                              _venda("card3_segunda_entrada", "M30"),                            # célula SEM selo
                              _venda("card2_rompimento_caixa", "M15", corte_ciclo_contra_agora=True)],   # corte do Ciclo
                   dirs=D1_ALTA, veredito="bloqueada", jan={"M1": -1, "M5": -1, "M15": -1}, cv2={"D1": 1, "H4": 1}, preco=4099.8)
    por = {(c["estrategia"]["card"], c["timeframe"]): c for c in S._todos(av)}
    esperado = {("card2_rompimento_caixa", "M30"): ("3.", "sinal vencido"), ("card3_segunda_entrada", "M30"): ("5.", "estudo sem selo"),
                ("card2_rompimento_caixa", "M15"): ("4.", "veto operacional")}
    for k, (num, cat) in esperado.items():
        c = por[k]
        assert c["elegibilidade"] == "vetada" and c["primeiro_impedimento"].startswith(num), (k, c["primeiro_impedimento"])
        bl = [m for m in c["motivos"] if m["efeito"] == "bloqueia"]
        assert len(bl) == 1 and bl[0]["condicao"].startswith(num) and bl[0]["categoria"] == cat
        inf = [m["condicao"] for m in c["motivos"] if m["efeito"] == "informa"]
        assert "D1 em sentido oposto" in inf and "D1" not in c["primeiro_impedimento"]
        assert c["escolha"]["escolhido"] is False and c["escolha"]["motivo"].startswith(num)
    assert av["escolha"] is None and av["resumo"]["conclusao"] == "nenhuma oportunidade elegível"


def test_4_canal_registrado_barra_fechada_conferencias_e_barra_em_formacao(api, amb):
    """Leitor 1.4 envia barra/OHLC/EMA20; o EA envia as velas (penúltima = fechada, última = em formação)."""
    barra = T._barra_m15()
    det, leit, ciclos = S._cenario([_venda("card2_rompimento_caixa", "M30")], barra, dirs=D1_ALTA, veredito="bloqueada",
                                   jan={"M1": -1, "M5": -1, "M15": -1}, cv2={"D1": 1, "H4": 1}, preco=4099.8)
    canal = lambda bc, o, h, l, c, eh, el, d: {"barra_corretora": bc, "fechada": True, "o": o, "h": h, "l": l, "c": c,
                                               "ema20_maximas": eh, "ema20_minimas": el, "dir": d, "barras_no_espelho": 300,
                                               "condicao": "fechamento > EMA20 das máximas" if d > 0 else "fechamento entre a EMA20 das mínimas e a das máximas",
                                               "mt5": {"barras": 1000, "barra_corretora": bc, "o": o, "h": h, "l": l, "c": c, "ema20_maximas": eh,
                                                       "ema20_minimas": el, "mesma_barra": True, "ohlc_confere": True, "ema_confere": True}}
    det["cv_motor"]["candidatos"]["canais"] = {"D1": canal("2026-10-06 00:00:00", 4120.0, 4170.0, 4110.0, 4160.0, 4150.0, 4090.0, 1),
                                               "H4": canal("2026-10-07 00:00:00", 4150.0, 4160.0, 4140.0, 4158.0, 4155.0, 4120.0, 1)}
    det["cv_motor"]["por_tf"]["D1"]["barra_corretora"] = "2026-10-06 00:00:00"
    det["cD"] = "4100,4130,4095,4120,10;4120,4170,4110,4160,10;4160,4162,4095,4099.8,10"        # fechada = 4120/4170/4110/4160; em formação cai
    det["c4h"] = "4150,4160,4140,4158,10;4158,4159,4095,4099.8,10"
    leit["linhas"] = [{"tf": "D1", "canal_ema20": "dentro"}, {"tf": "H4", "canal_ema20": "abaixo"}]
    sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", amb["bots"]["A"]["id"]).execute().data[0]
    T._pg("delete from selecao_avaliacoes where bot_id=%s", bot["id"])
    av = api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time()))
    d1 = av["contexto_superior"]["tempos"]["D1"]
    assert d1["direcao"] == "alta" and "FECHADA" in d1["base"] and d1["condicao"] == "fechamento > EMA20 das máximas"
    assert d1["ohlc"] == {"o": 4120.0, "h": 4170.0, "l": 4110.0, "c": 4160.0} and (d1["ema20_maximas"], d1["ema20_minimas"]) == (4150.0, 4090.0)
    assert d1["barra_corretora"] == "2026-10-06 00:00:00"
    assert d1["barra_abriu_utc"] == "2026-10-05T21:00:00+00:00" and d1["barra_fechou_utc"] == "2026-10-06T21:00:00+00:00"   # fuso da corretora descontado
    assert d1["conferencia_mt5"]["ohlc_confere"] is True and d1["conferencia_mt5"]["ema_confere"] is True
    assert d1["conferencia_ea"]["confere"] is True and d1["conferencia_ea"]["ohlc_do_ea_na_ultima_fechada"]["c"] == 4160.0
    ba = d1["barra_atual"]
    assert (ba["abriu"], ba["preco"], ba["movimento"], ba["posicao_no_canal_segundo_o_ea"]) == (4160.0, 4099.8, "caindo", "dentro")
    assert ba["variacao_pct"] == round((4099.8 - 4160.0) / 4160.0 * 100, 2) and "FORMAÇÃO" in ba["base"]
    c = S._todos(av)[0]
    assert c["elegibilidade"] == "elegivel"                                             # a barra atual caindo não muda portão nenhum
    assert c["contexto_superior"]["frases"][-1].startswith("D1: canal de alta na última barra fechada; candidato: venda em M30; sentidos opostos")
    assert any(f.startswith("D1 agora (barra em formação): abriu 4160.0, preço 4099.8 (-1.45%, caindo); preço dentro do canal")
               for f in c["contexto_superior"]["barra_atual"])
    # EA discordando da vela fechada do motor aparece como NÃO confere (nada é corrigido em silêncio)
    det["cD"] = "4100,4130,4095,4120,10;4120,4170,4110,4161.5,10;4160,4162,4095,4099.8,10"
    av2 = api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time()))
    assert av2["contexto_superior"]["tempos"]["D1"]["conferencia_ea"]["confere"] is False
    # sem os valores (leitor < 1.4): diz que não foram registrados; a direção e a frase continuam
    del det["cv_motor"]["candidatos"]["canais"]
    av3 = api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time()))
    d1c = av3["contexto_superior"]["tempos"]["D1"]
    assert "não registrados" in d1c["valores"] and "ohlc" not in d1c and d1c["direcao"] == "alta"


def test_5_frescor_horarios_alcance_e_regra_inalterada(api, amb):
    barra = T._barra_m15()
    cor = lambda dt: (dt + timedelta(seconds=S.OFF)).strftime("%Y-%m-%d %H:%M:%S")
    k_ult = barra - timedelta(minutes=15)                                   # abertura da última M15 fechada
    itens = [
        # M15, fechamento: sinal na barra k_ult-2, entrada na abertura de k_ult-1 → idade 1 (visto exatamente no limite)
        S._cand("card2_rompimento_caixa", "M15", 1, idade=1, sinal=cor(k_ult - timedelta(minutes=30)),
                ts_entrada_m15=cor(k_ult - timedelta(minutes=15)), modo="fechamento"),
        # H1, fechamento: sinal na H1 que abriu há 2h15; entrada na abertura da H1 seguinte → idade 4 quando enfim aparece
        S._cand("card2_rompimento_caixa", "H1", 1, idade=4, sinal=cor(k_ult - timedelta(minutes=120)),
                ts_entrada_m15=cor(k_ult - timedelta(minutes=60)), modo="fechamento"),
        S._cand("card10_donchian20", "M15", 1, estado="aguardando", sinal=cor(k_ult))]
    av, *_ = S._av(api, amb, itens)
    por = {(c["estrategia"]["card"], c["timeframe"]): c for c in S._todos(av)}
    m15 = por[("card2_rompimento_caixa", "M15")]["frescor"]
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert m15["sinal_barra_fechou_utc"] == m15["entrada_estudada_utc"] == iso(k_ult - timedelta(minutes=15))
    assert m15["primeira_confirmacao_possivel_utc"] == m15["vence_utc"] == iso(k_ult + timedelta(minutes=15))   # uma única barra de avaliação
    assert m15["alcancavel"] is True and "barras M15" in m15["unidade"]
    assert por[("card2_rompimento_caixa", "M15")]["elegibilidade"] == "elegivel"
    h1 = por[("card2_rompimento_caixa", "H1")]
    f = h1["frescor"]
    assert f["sinal_barra_fechou_utc"] == f["entrada_estudada_utc"] == iso(k_ult - timedelta(minutes=60))
    assert f["primeira_confirmacao_possivel_utc"] == iso(k_ult) and f["vence_utc"] == iso(k_ult - timedelta(minutes=30))
    assert f["alcancavel"] is False and "nunca é visto dentro do prazo" in f["aviso"] and "NÃO foi alterada" in f["aviso"]
    assert h1["elegibilidade"] == "vetada" and h1["primeiro_impedimento"].startswith("3. frescor")       # a regra continua valendo: limite 1
    assert next(p for p in h1["portoes"] if p["portao"].startswith("3."))["detalhe"] == "entrada há 4 barra(s) M15; limite 1"
    ag = por[("card10_donchian20", "M15")]["frescor"]
    assert ag["confirmacao"].startswith("pendente") and ag["entrada_estudada_utc"] is None and ag["vence_utc"] is None
    assert av["resumo"]["frescor_inalcancavel"] == 1
