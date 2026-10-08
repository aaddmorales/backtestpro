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
        assert c["agora_corretora"] == agora and c["versao"] == "cand-5" and c["confirmacao"]["contrato"] == "conf-rt-1"
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


# ═════════════ C27R25 — contrato corte-ciclo-2: M30, H1 e tempos maiores NÃO provocam corte ═════════════
@pytest.fixture(autouse=True)
def _relogio_falso_restaurado():
    """replay_util.espelho_em fixa BT_FAKE_AGORA: devolve o relógio ao que era ao fim de cada teste."""
    antes = os.environ.get("BT_FAKE_AGORA")
    yield
    if antes is None:
        os.environ.pop("BT_FAKE_AGORA", None)
    else:
        os.environ["BT_FAKE_AGORA"] = antes


def _fichas_do_corte(tmp_path, t=T_H1):
    import contextlib, io
    import bt_motor_leitura_hml as L, bloco1_motor_v3 as B1, professor_cards_v19 as PC
    d = str(tmp_path / "esp"); ab = str(tmp_path / "ab")
    R.espelho_em(d, t)
    L._espelho_com_barra_aberta(d, ab)
    with contextlib.redirect_stdout(io.StringIO()):
        PC._aplicar_ficha("XAUUSD", d)
        lt = B1.LeitorMultiTF(ab, "XAUUSD").carregar()
        F = B1.FichaSerie(lt, "M15", "XAUUSD")
    return L, B1, ab, lt, F, L._corte_contrato(B1, ab, "XAUUSD", F)


def test_6_corte_do_contrato_so_tem_o_m15_como_andar_que_decide(tmp_path):
    """O corte do contrato corte-ciclo-2 é a ficha CONGELADA calculada só com M1/M5/M10/M15. Prova:
    (1) é igual, barra a barra, ao corte da ficha completa em que o M15 foi um dos andares que decidiram;
    (2) todo corte que a integração anterior dava SÓ por M30/H1/H4/D1/W1/MN1 deixa de existir;
    (3) nenhuma origem cita andar fora de M1, M5, M10, M15; (4) nenhum corte novo aparece."""
    L, B1, ab, lt, F, CC = _fichas_do_corte(tmp_path)
    assert CC["contrato"] == "corte-ciclo-2" and L.CORTE_ANDARES == ("M1", "M5", "M10", "M15")
    assert {"M30", "H1", "H4", "Daily"} <= set(lt.andares)             # a ficha completa TEM os tempos maiores
    so_maiores = 0
    for lado in (1, -1):
        for k in range(F.n):
            dec = {p.split(":")[0].strip() for p in str(F.motivo[lado][k]).split("->")[1:] if ":" in p}
            com_m15 = bool(F.corta[lado][k]) and "M15" in dec
            assert bool(CC["corta"][lado][k]) == com_m15, (lado, k, F.motivo[lado][k])
            if F.corta[lado][k] and "M15" not in dec:
                so_maiores += 1
                assert dec <= {"M30", "H1", "H4", "Daily", "W1", "MN1"} and not CC["corta"][lado][k]
            assert not (CC["corta"][lado][k] and not F.corta[lado][k])     # o contrato nunca corta onde o motor não cortava
        for k, itens in CC["origem"][lado].items():
            for it in itens:
                assert it["decidido_por"] and all(x.split(":")[0] == "M15" for x in it["decidido_por"])
                assert it["identificado_em"] and all(x.split(":")[0] in ("M1", "M5", "M10") for x in it["identificado_em"])
    assert so_maiores > 0, "o cenário de teste precisa ter cortes da integração anterior só por tempos maiores"


def test_7_mexer_em_m30_h1_h4_d1_nao_muda_o_corte_do_contrato(tmp_path):
    """Troca as barras de M30, H1, H4 e D1 do espelho por outras (invertidas): o corte do contrato não muda
    em nenhuma barra; o da integração anterior muda. O motor congelado não é tocado."""
    import contextlib, io, glob
    import pandas as pd
    L, B1, ab, lt, F, CC = _fichas_do_corte(tmp_path)
    for tf in ("M30", "H1", "H4", "Daily"):
        arq = glob.glob(os.path.join(ab, f"XAUUSD_{tf}_*.csv"))[0]
        d = pd.read_csv(arq, sep="\t")
        piv = float(d["<CLOSE>"].iloc[0])
        for c in ("<OPEN>", "<CLOSE>"):
            d[c] = 2 * piv - d[c]
        hi, lo = 2 * piv - d["<LOW>"], 2 * piv - d["<HIGH>"]
        d["<HIGH>"], d["<LOW>"] = hi, lo
        d.to_csv(arq, sep="\t", index=False, float_format="%.2f")
    with contextlib.redirect_stdout(io.StringIO()):
        lt2 = B1.LeitorMultiTF(ab, "XAUUSD").carregar()
        F2 = B1.FichaSerie(lt2, "M15", "XAUUSD")
    C2 = L._corte_contrato(B1, ab, "XAUUSD", F2)
    for lado in (1, -1):
        assert (CC["corta"][lado] == C2["corta"][lado]).all()
    assert any((F.corta[lado] != F2.corta[lado]).any() for lado in (1, -1))     # a ficha completa (integração anterior) mudou


def test_8_confirmacao_gestao_e_relato_usam_o_corte_do_contrato(tmp_path):
    """Leitor 1.7: o candidato, a leitura de gestão e o relato de cortes saem do contrato; a divergência com a
    integração anterior fica registrada com os andares que decidiam antes."""
    import bt_motor_leitura_hml as L
    d = str(tmp_path / "esp"); R.espelho_em(d, T_H1)
    c = L._candidatos(d, "XAUUSD", 12)
    assert c["versao"] == "cand-5" and c["leitor"] == "1.7-hml"
    r = c["cortes"]
    assert r["contrato"] == "corte-ciclo-2" and r["andares_do_contrato"] == ["M1", "M5", "M10", "M15"]
    assert r["nao_cortam"] == ["M30", "H1", "H4", "D1", "W1", "MN1"]
    agora, fech = r["barras"]["que_abre_agora"], r["barras"]["ultima_fechada"]
    assert c["confirmacao"]["slot_agora"]["corte_contra_compra"] == agora["compra"]["corta"]
    assert c["confirmacao"]["slot_agora"]["corte_contra_venda"] == agora["venda"]["corta"]
    for nome in ("compra", "venda"):
        g = c["gestao"]["lados"][nome]
        assert g["corte_contrato"] == "corte-ciclo-2"
        assert g["corte_do_ciclo"] == (fech[nome]["corta"] and not c["gestao"]["B1"])
        for b in (agora, fech):
            x = b[nome]
            if x["corta"]:
                assert x["origem"] and all(o.split(":")[0] == "M15" for it in x["origem"] for o in it["decidido_por"])
            if x["integracao_anterior"]["corta"] and not x["corta"]:
                assert "M15" not in x["integracao_anterior"]["andares_que_decidiram"] and "não corta" in x["divergencia"]
    for it in c["itens"]:
        assert it["corte_ciclo_contra_agora"] == agora["compra" if it["lado"] > 0 else "venda"]["corta"]
        assert it["origem_da_confirmacao"]["timeframe_do_card"] == it["tf"]
