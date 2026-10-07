"""C27R23 — REPRODUÇÃO CRONOLÓGICA da confirmação em tempo real (leitor 1.5, contrato conf-rt-1).
Em cada instante T o espelho só tem as barras que o MT5 (falso, determinístico) já tinha FECHADO em T:
o leitor não tem como ler o futuro. Prova, sem ampliar validade:
  · um candidato H1 aparece CONFIRMADO no instante em que a barra do sinal fecha e ainda válido;
  · o resolvedor do estudo só devolve a mesma entrada uma hora depois (quando ela já venceu);
  · o que foi confirmado em T não muda quando chegam barras novas (sem dependência de barra futura);
  · o corte do Ciclo e a blindagem calculados para "a barra que abre agora" são os MESMOS que o motor
    congelado grava nessa barra depois que ela fecha.
SINTÉTICO (bancada). Não é evidência da plataforma."""
import os, sys
from datetime import datetime, timedelta, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import replay_util as R

OFF = 10800
T_H1 = 1791424800                      # UTC: instante em que fecha a H1 do sinal (corretora 2026-10-08 05:00:00)
CARD, LADO = "card4_canal_ema20", 1
PASSOS = (-900, 0, 900, 1800, 2700, 3600)


def _cor(t_utc):
    return datetime.fromtimestamp(t_utc + OFF, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture(scope="module")
def fita(tmp_path_factory):
    """Uma passada do leitor por instante, em ordem. Guarda os candidatos e, para a casa 'agora',
    o que o motor congelado grava na barra seguinte."""
    import numpy as np
    import bt_motor_leitura_hml as L
    import bloco1_motor_v3 as B1
    import professor_cards_v19 as PC
    pasta = str(tmp_path_factory.mktemp("replay"))
    antes = os.environ.get("BT_FAKE_AGORA")
    out = {}
    try:
        for dp in PASSOS:
            T = T_H1 + dp
            R.espelho_em(pasta, T + 1)                         # 1 s depois da virada: só barras fechadas em T
            cand = L._candidatos(pasta, "XAUUSD", 12)
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                PC._aplicar_ficha("XAUUSD", pasta)
                F15 = B1.FichaSerie(B1.LeitorMultiTF(pasta, "XAUUSD").carregar(), "M15", "XAUUSD")
            k = int(F15.n) - 1
            out[dp] = {"cand": cand, "ult_m15": str(np.datetime_as_string(F15.ts[k], unit="s")).replace("T", " "),
                       "congelado_na_ultima": {"corte_contra_compra": bool(F15.corta[1][k]), "corte_contra_venda": bool(F15.corta[-1][k]),
                                               "B1": bool(F15.B1[k])}}
    finally:
        if antes is None:
            os.environ.pop("BT_FAKE_AGORA", None)
        else:
            os.environ["BT_FAKE_AGORA"] = antes
    return out


def _item(fita, dp):
    uid = f"{CARD}|H1|{_cor(T_H1 - 3600)}|{LADO}"
    return next((i for i in fita[dp]["cand"]["itens"] if i["uid"] == uid), None)


def test_1_nada_do_futuro_em_nenhum_instante(fita):
    for dp in PASSOS:
        c = fita[dp]["cand"]; agora = _cor(T_H1 + dp)
        assert c["agora_corretora"] == agora and c["versao"] == "cand-4" and c["confirmacao"]["contrato"] == "conf-rt-1"
        assert fita[dp]["ult_m15"] == _cor(T_H1 + dp - 900)                     # última barra do espelho fechou exatamente agora
        for i in c["itens"]:
            assert i["ts_sinal_fecha"] <= agora, i                               # a barra do sinal já fechou
            if i["estado"] == "confirmado":
                assert i["ts_confirmacao"] <= agora and i["idade_s"] >= 0, i     # confirmação nunca no futuro
                assert i["confirmacao"]["contrato"] == "conf-rt-1" and i["modo"] in ("fechamento", "gatilho")
                v = datetime.strptime(i["ts_vence"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(i["ts_confirmacao"], "%Y-%m-%d %H:%M:%S")
                assert v == timedelta(minutes=30)                                # validade não ampliada
                assert (i["lado"] > 0 and i["stop"] < i["preco_ref"]) or (i["lado"] < 0 and i["stop"] > i["preco_ref"])


def test_2_h1_confirma_no_fechamento_do_sinal_e_ainda_valido(fita):
    assert _item(fita, -900) is None                    # 15 min antes a barra H1 do sinal nem fechou: o sinal não existe
    x = _item(fita, 0)
    assert x is not None and x["estado"] == "confirmado" and x["tf"] == "H1" and x["modo"] == "fechamento"
    assert x["ts_sinal"] == _cor(T_H1 - 3600) and x["ts_sinal_fecha"] == _cor(T_H1)
    assert x["ts_confirmacao"] == _cor(T_H1) and x["idade_s"] == 0 and x["ts_vence"] == _cor(T_H1 + 1800)
    assert x["estudo_retro"] is None                    # o resolvedor do estudo AINDA não devolve esta entrada
    assert "fechamento da última M15" in x["preco_ref_base"]
    # 15 e 30 min depois: mesma confirmação, ainda dentro da validade; aos 45 min já venceu
    for dp, idade in ((900, 900), (1800, 1800)):
        y = _item(fita, dp)
        assert y["estado"] == "confirmado" and y["idade_s"] == idade and _cor(T_H1 + dp) <= y["ts_vence"]
    assert _item(fita, 2700)["idade_s"] == 2700 and _cor(T_H1 + 2700) > _item(fita, 2700)["ts_vence"]


def test_3_o_estudo_so_enxerga_a_mesma_entrada_uma_hora_depois(fita):
    for dp in (0, 900, 1800, 2700):
        assert _item(fita, dp)["estudo_retro"] is None
    z = _item(fita, 3600)
    r = z["estudo_retro"]
    assert r is not None and r["mesma_barra_da_confirmacao"] is True and r["barra_m15_da_entrada"] == _cor(T_H1)
    assert z["idade_s"] == 3600 and _cor(T_H1 + 3600) > z["ts_vence"]           # quando o estudo devolve, a entrada já venceu
    assert r["dif_preco_pts"] is not None and r["posiciona_a_entrada_s_antes_da_confirmacao"] == 0


def test_4_confirmado_nao_muda_quando_chegam_barras_novas(fita):
    primeiro = {}
    n = 0
    for dp in PASSOS:
        for i in fita[dp]["cand"]["itens"]:
            if i["estado"] != "confirmado":
                continue
            k = (i["ts_confirmacao"], i["preco_ref"], i["stop"], i["modo"])
            if i["uid"] in primeiro:
                assert primeiro[i["uid"]] == k, (i["uid"], primeiro[i["uid"]], k); n += 1
            else:
                primeiro[i["uid"]] = k
    assert n >= 5                                       # houve candidatos acompanhados por mais de um instante


def test_5_casa_agora_igual_ao_motor_congelado_na_barra_seguinte(fita):
    for a, b in zip(PASSOS, PASSOS[1:]):
        agora = fita[a]["cand"]["blindagens_m15"]       # calculado em T para a barra que ABRE em T
        depois = fita[b]["congelado_na_ultima"]         # o que o motor congelado grava nessa barra, visto em T+15min
        assert {k: agora[k] for k in depois} == depois, (a, agora, depois)
