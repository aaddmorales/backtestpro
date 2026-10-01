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
