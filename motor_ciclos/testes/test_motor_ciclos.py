"""C27R14 — motor dos Ciclos na bancada (sem rede). Motor CONGELADO real +
leitor + ponte v1.1 + assinador v0.4 contra o MetaTrader5 FALSO."""
import hashlib, json, os, sys, time
from datetime import datetime, timedelta, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.dirname(AQUI)
sys.path.insert(0, MOTOR); sys.path.insert(0, AQUI)
import fixture_motor as FM

CONGELADOS = {   # referência: CORRECAO_P2_CICLO_VIVO_27SET.zip (sha bd33c34a…), entradas/motor e codigo/
    "bt_ciclo_v1.py": "9ac1af947587acaa0a2da56e4d1d9aad75e9217070384fca97f39fe48695077d",
    "bt_vivo_sombra.py": "47a2ade727a2f72d47761dd4069e45a5f1930e74c9c6d795066b96b1a96f505b",
    "bloco1_motor_v3.py": "f6bff47b62d79b8e6fb8b22455493350a134bd970bca91bdb412a5a45812f0f7",
    "professor_cards_v19.py": "bb3e33afaed392c062bc1cc9071588cc34bd579180a35cade3ced8dca647b932",
    "professor_bloco2.py": "fa84b37eb9d60c92ee3aa73262f32e77bd4804afb33d4d0ac98cfb71bd796b32",
    "professor_bloco3.py": "adc6f1f85221ea334d2b70b6dacebbb0b0611329066a198ee98f069389f616f8",
    "referencia_27set/bt_ponte_ciclo_v1.py": "89e4b4be9a4f9d4a11f521492034876e37c2ceef8d5b89181d560a6014ba86e8",
    "referencia_27set/bt_conector_atestado.py": "71b34a5881d3bdc7c09fc0dd980e9475529b5ab197311d0d4bff75bbd114d45f",
}
SEG = "segredo-de-teste-motor-" + "x" * 20     # rotulado: só bancada


def _sha(p):
    return hashlib.sha256(open(os.path.join(MOTOR, p), "rb").read()).hexdigest()


def test_1_congelados_byte_identicos():
    for f, h in CONGELADOS.items():
        assert _sha(f) == h, f
    raiz = os.path.join(os.path.dirname(MOTOR), "bt_cv_atestado.py")
    assert hashlib.sha256(open(raiz, "rb").read()).hexdigest() == _sha("bt_cv_atestado.py")


@pytest.fixture(scope="module")
def leitor(tmp_path_factory):
    FM.esperar_janela_segura()
    d = str(tmp_path_factory.mktemp("dados"))
    r = FM.rodar_leitor(d)
    assert r.returncode == 0, r.stderr[-2000:]
    return d, r


def test_2_leitor_publica_barra_fechada_e_saude(leitor):
    d, r = leitor
    s, a = FM.ler(d, "SAUDE.json"), FM.ler(d, "ATUAL.json")
    srv = int(time.time()) + FM.OFF
    esperado = datetime.fromtimestamp((srv // 900) * 900 - 900, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert a["barra_corretora"] == esperado and s["ultima_barra_corretora"] == esperado
    assert s["conta_demo"] and s["login"] == FM.LOGIN and s["off_corretora_s"] == FM.OFF
    assert s["erro_ultimo"] is None and "bloqueadas" in s["ordens"]
    assert s["hashes"]["bt_ciclo_v1.py"] == CONGELADOS["bt_ciclo_v1.py"]
    lm = FM.ler(os.path.join(d, a["pasta"]), "leitura_motor.json")
    assert lm["erro"] is None and lm["leitura"]["topdown"][0] in ("autorizada", "neutra", "bloqueada")
    assert set(lm["leitura"]["por_tf"]) == {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
    assert lm["m15"]["barra_corretora"] == esperado
    assert "ordens BLOQUEADAS" in r.stdout


def test_3_reinicio_nao_republica(leitor):
    d, _ = leitor
    a0 = FM.ler(d, "ATUAL.json")
    pasta = os.path.join(d, a0["pasta"]); m0 = os.path.getmtime(os.path.join(pasta, "leitura_motor.json"))
    r = FM.rodar_leitor(d)
    assert r.returncode == 0 and "retomada: " + a0["barra_corretora"] in r.stdout
    a1 = FM.ler(d, "ATUAL.json")
    assert a1 == a0 and os.path.getmtime(os.path.join(pasta, "leitura_motor.json")) == m0


def test_4_recusa_conta_real_e_login_errado(tmp_path):
    r = FM.rodar_leitor(str(tmp_path / "a"), extra_env={"BT_FAKE_REAL": "1"})
    assert r.returncode != 0 and "NÃO é DEMO" in (r.stderr + r.stdout)
    r = FM.rodar_leitor(str(tmp_path / "b"), extra_env={"BT_FAKE_LOGIN": "111"})
    assert r.returncode != 0 and "login fixado" in (r.stderr + r.stdout)


def test_5_leitor_bloqueia_ordens_em_processo(tmp_path, monkeypatch):
    sys.path.insert(0, FM.FAKE)
    import MetaTrader5 as F
    import bt_motor_leitura_hml as L
    L._bloquear_ordens(F)
    with pytest.raises(RuntimeError, match="leitor_sem_ordens"):
        F.order_send({"action": 1})
    assert F.ORDENS == []
    src = open(os.path.join(MOTOR, "bt_motor_leitura_hml.py"), encoding="utf-8").read()
    for proibido in ("S.sombra(", "S.executar(", "trail_sl_demo", "_protecao_intrabar", "order_send("):
        assert proibido not in src.replace("\"order_send\"", ""), proibido


def _ficha_e_assinar(d, off, bot_tok="tok-A", magic=123456, agora=None):
    import bt_conector_atestado as CA
    pasta = os.path.join(d, FM.ler(d, "ATUAL.json")["pasta"])
    return CA.LeitorConfiavel(d, segredo=SEG).ler_e_assinar_motor(
        pasta, "XAUUSD", magic, simbolo="XAUUSD", bot_token=bot_tok, off_corretora_s=off,
        agora_utc=agora, com_resumo=True)


def test_6_ponte_converte_fuso_e_vincula_bot(leitor):
    import bt_cv_atestado as cvat
    d, _ = leitor
    at, resumo = _ficha_e_assinar(d, FM.OFF, agora=datetime.now(timezone.utc))
    ab = datetime.strptime(FM.ler(d, "ATUAL.json")["barra_corretora"], "%Y-%m-%d %H:%M:%S")
    esperado = (ab + timedelta(minutes=15) - timedelta(seconds=FM.OFF)).replace(tzinfo=timezone.utc)
    assert at["ts_barra_m15"] == esperado.isoformat()
    assert at["bot_token_hash"] == hashlib.sha256(b"tok-A").hexdigest()
    assert at["cv1"]["veredito"] == resumo["topdown"][0]
    assert at["cv2"]["dirs"] == {"D1": resumo["por_tf"]["D1"]["dir"], "H4": resumo["por_tf"]["H4"]["dir"]}
    assert cvat.verificar(at, segredo=SEG) == (True, None)
    adult = dict(at, cv1=dict(at["cv1"], veredito="autorizada" if at["cv1"]["veredito"] != "autorizada" else "neutra"))
    assert cvat.verificar(adult, segredo=SEG)[0] is False


def test_7_ponte_recusa_antiga_futura_sem_fuso_sem_token(leitor):
    d, _ = leitor
    agora = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="leitura_antiga"):
        _ficha_e_assinar(d, FM.OFF, agora=agora + timedelta(minutes=20))
    with pytest.raises(ValueError, match="barra_futura"):
        _ficha_e_assinar(d, 0, agora=agora)            # espelho tratado como UTC = o bug da v1.0
    with pytest.raises(ValueError, match="fuso_corretora_ausente"):
        _ficha_e_assinar(d, None, agora=agora)
    with pytest.raises(ValueError, match="bot_token_ausente"):
        _ficha_e_assinar(d, FM.OFF, bot_tok="", agora=agora)


def test_8_leitor_acorda_logo_depois_da_virada():
    """v1.2 — visto na plataforma: o 1º snapshot da barra chegava antes de o motor publicar
    (intervalo fixo de 20 s) e a barra abria como espelho_atrasado."""
    import bt_motor_leitura_hml as L
    assert L.LEITOR_VERSAO == "1.2-hml"
    base = 900 * 2_000_000
    assert L._espera(20, base + 400, 2_000_000) == 20            # meio da barra: intervalo normal
    assert L._espera(20, base + 890, 2_000_000) == 12            # virada em 10 s: acorda 2 s depois dela
    assert L._espera(20, base + 2, 1_999_999) == 3               # barra nova ainda não publicada: a cada 3 s
    assert L._espera(20, base + 2, 2_000_000) == 20              # já publicada: volta ao normal
    assert L._espera(20, base + 61, 1_999_999) == 20             # passou 1 min sem barra (mercado fechado): normal
    assert L._espera(1, base + 400, 2_000_000) == 5              # nunca abaixo de 5 s fora da janela
