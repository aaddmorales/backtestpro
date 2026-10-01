"""C27R14 rev.2 — recusas do atestado do MOTOR REAL contra a API isolada local.
O atestado é produzido pelo motor congelado (bt_ciclo_v1 via ponte v1.1 +
assinador v0.4) sobre o espelho do leitor (MT5 FALSO); cada caso adultera UM
elo e a verificação da API (a MESMA do emissor R-CICLO-01) tem que recusar."""
import hashlib, os, sys, time
from datetime import datetime, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor_ciclos"))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor_ciclos", "testes"))
import test_ciclos_lm as T          # ambiente isolado real (registrar, snapshot, ao-vivo)
import fixture_motor as FM

amb = T.amb
SEG = T.SEGREDO


@pytest.fixture(scope="module")
def espelho(tmp_path_factory):
    FM.esperar_janela_segura(60)
    d = str(tmp_path_factory.mktemp("dados"))
    r = FM.rodar_leitor(d)
    assert r.returncode == 0, r.stderr[-1500:]
    return os.path.join(d, FM.ler(d, "ATUAL.json")["pasta"])


def _assinar(pasta, tok, magic, simbolo="XAUUSD", off=FM.OFF, segredo=None):
    import bt_conector_atestado as CA
    return CA.LeitorConfiavel(pasta, segredo=segredo or SEG).ler_e_assinar_motor(
        pasta, "XAUUSD", magic, simbolo=simbolo, bot_token=tok, off_corretora_s=off)


def _estado(amb, b, at):
    det = FM.det_ea(T._magic(b["tok"]))
    if at is not None:
        det["cv_atestado"] = at
    s, j, _ = T._snap(b["tok"], det)
    assert s == 200, j
    jj, raw = T._ao_vivo(amb, b["id"])
    return jj["ciclos"]["atestado"], jj["ciclos"]["consolidada"], raw


def test_recusas_e_aceite_do_motor_real(amb, espelho):
    assert SEG, "BT_CV_SEGREDO precisa estar no teste E na API local (FALHA, nao skip)"
    a, b = amb["bots"]["A"], amb["bots"]["B"]
    mg = T._magic(a["tok"])
    casos = {
        "ausente": (None, "atestado_ausente"),
        "invalido": (dict(_assinar(espelho, a["tok"], mg), assinatura="0" * 64), "atestado_assinatura_invalida"),
        "segredo_errado": (_assinar(espelho, a["tok"], mg, segredo="outro-segredo-" + "y" * 20), "atestado_assinatura_invalida"),
        "expirado": (_assinar(espelho, a["tok"], mg, off=FM.OFF + 900), "leitura_vencida"),
        "outro_bot": (_assinar(espelho, b["tok"], mg), "atestado_de_outro_bot"),
        "outro_magic": (_assinar(espelho, a["tok"], mg + 1), "atestado_magic_divergente_do_snapshot"),
        "outro_simbolo": (_assinar(espelho, a["tok"], mg, simbolo="BTCUSD"), "atestado_simbolo_divergente"),
    }
    for nome, (at, motivo) in casos.items():
        info, cons, raw = _estado(amb, a, at)
        assert info["estado"] == "recusado" and str(info["motivo"]).startswith(motivo), (nome, info)
        assert cons["decisao"] == "bloquear", (nome, cons)
        assert a["tok"].encode() not in raw
    at = _assinar(espelho, a["tok"], mg)
    info, cons, _ = _estado(amb, a, at)
    assert info["estado"] == "verificado" and info["versao_motor"] == "cv1-2.4"
    ver = at["cv1"]["veredito"]
    esperado = {"bloqueada": "bloquear", "neutra": "observar"}.get(ver)
    if esperado:
        assert cons["decisao"] == esperado, cons
    else:   # autorizada do motor: a API ainda exige janela M1/M5/M15 toda no lado (fail-closed declarado)
        assert cons["decisao"] in ("comprar", "vender", "bloquear"), cons
    assert T._pg("select count(*) from ciclo_decisoes where bot_id=%s", a["id"])[0][0] == 0
    assert T._pg("select count(*) from mt5_comandos where bot_id=%s and tipo in ('buy','sell')", a["id"])[0][0] == 0


def test_impressao_do_segredo_sem_expor(amb):
    s, j, raw = T._req("GET", T.E["BT_ISO_API"] + "/conector/cv-impressao")
    assert s == 200 and j["configurado"] is True
    assert j["impressao"] == hashlib.sha256(("bt-cv-impressao-v1|" + SEG).encode()).hexdigest()[:16]
    assert SEG.encode() not in raw


def _sintetico(tok, magic, janela, dirs, veredito="autorizada"):
    """Atestado SINTÉTICO (segredo de teste da bancada) — só para exercitar a
    regra da API com combinações que o MT5 falso não produz sob encomenda."""
    import bt_cv_atestado as cvat
    return cvat.assinar({"bot_token_hash": hashlib.sha256(tok.encode()).hexdigest(),
                         "versao_motor": "teste-regra", "simbolo": "XAUUSD", "magic": magic,
                         "ts_barra_m15": T._barra_m15().isoformat(),
                         "cv1": {"janela": janela, "veredito": veredito, "motivo": "item1_referencia_a_favor(D1&H4)"},
                         "cv2": {"dirs": dirs}}, segredo=SEG)


def test_divergencia_motor_api_separada_de_integracao(amb):
    b = amb["bots"]["C"]
    mg = T._magic(b["tok"])
    # motor autorizou (D1=H4=M15=+1), M1 contra: regra adicional da API → divergência
    info, cons, _ = _estado(amb, b, _sintetico(b["tok"], mg, {"M1": -1, "M5": 1, "M15": 1}, {"D1": 1, "H4": 1}))
    assert info["estado"] == "verificado"
    assert cons["regra"] == "R-CICLO-01.divergencia_motor_api" and "divergência" in cons["classe_veto"], cons
    jj, _ = T._ao_vivo(amb, b["id"])
    e = jj["ciclos"]["estagios"]
    assert e["atestado_valido"] is True and e["decisao_vetada"] is True and e["decisao_autorizada"] is False
    assert [g["assinado"] for g in jj["ciclos"]["origem_criterios"]] == [True, False, None]
    assert jj["ciclos"]["origem_criterios"][0]["campos"]["cv1.veredito"] == "autorizada"
    assert jj["ciclos"]["origem_criterios"][2]["campos"]["cv1.janela.M1"] == -1
    # 'autorizada' com H4 contra: o motor nunca produz → integração (incoerente), não divergência
    info, cons, _ = _estado(amb, b, _sintetico(b["tok"], mg, {"M1": 1, "M5": 1, "M15": 1}, {"D1": 1, "H4": -1}))
    assert cons["regra"] == "R-CICLO-01.incoerente" and cons["classe_veto"].startswith("integração"), cons
    # o emissor real recusa a divergência e a trilha marca a classe
    os.environ.setdefault("BT_CV_SEGREDO", SEG)
    import api
    sb = api._sb_admin()
    _estado(amb, b, _sintetico(b["tok"], mg, {"M1": -1, "M5": 1, "M15": 1}, {"D1": 1, "H4": 1}))
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    ok, r = api._r01_emitir_decisao(sb, bot, "buy")
    assert not ok and str(r).startswith("atestado_incoerente(autorizada_com_janela_contra:M1)"), r
    assert T._pg("select count(*) from ciclo_trilha where bot_id=%s and etapa='veto' and motivo like %s",
                 b["id"], "%DIVERGÊNCIA MOTOR×API%")[0][0] >= 1
    assert T._pg("select count(*) from ciclo_decisoes where bot_id=%s", b["id"])[0][0] == 0
