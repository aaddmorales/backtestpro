"""C27R20 — versão do app servido, soma por conta no Monitor e vazio da Learning Machine.
Contra o AMBIENTE ISOLADO LOCAL (API + GoTrue + PostgREST + Postgres). Testes SINTÉTICOS:
os snapshots são fabricados aqui; nada disto é evidência da plataforma."""
import hashlib, json, os, re, urllib.request
import pytest
import uuid
from test_ciclos_lm import E, _req, _pg, _det, _magic, amb          # noqa: F401  (mesmo ambiente e usuário)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get(caminho):
    r = urllib.request.urlopen(urllib.request.Request(E["BT_ISO_API"] + caminho), timeout=60)
    return r.status, dict((k.lower(), v) for k, v in r.headers.items()), r.read()


def _app_local():
    bruto = open(os.path.join(RAIZ, "app.html"), "rb").read()
    return bruto, re.search(rb"const APP_VERSAO = '([^']+)'", bruto).group(1).decode()


def test_1_app_sem_cache_e_com_versao_no_cabecalho():
    bruto, ver = _app_local()
    st, h, corpo = _get("/app")
    assert st == 200
    assert "no-store" in h.get("cache-control", ""), h
    assert h.get("x-bt-app-versao") == ver
    assert ("const APP_VERSAO = '%s'" % ver).encode() in corpo
    assert b"btConferirVersao" in corpo and b"clmSelBox" in corpo
    assert b'id="vtag-selo">v10.' not in corpo      # o selo nunca nasce com uma versão escrita à mão


def test_2_app_versao_bate_com_o_arquivo():
    bruto, ver = _app_local()
    st, h, corpo = _get("/app/versao")
    d = json.loads(corpo)
    assert st == 200 and "no-store" in h.get("cache-control", "")
    assert d["app_versao"] == ver
    assert d["sha256_arquivo"] == hashlib.sha256(bruto).hexdigest()
    assert d["bytes_arquivo"] == len(bruto)
    assert d["api"].startswith("7.89-c27r20")
    txt = corpo.decode().lower()
    assert "eyj" not in txt and "sb_secret" not in txt and "service_role" not in txt


def _snapc(tok, magic, simbolo, conta, eq, bal, flu, pos=0):
    return _req("POST", E["BT_ISO_API"] + "/conector/snapshot", {
        "bot_token": tok, "conta_login": conta, "corretora": "Raw Trading Ltd", "simbolo": simbolo,
        "magic_number": magic, "equity": eq, "balance": bal, "margem_livre": eq, "posicoes_abertas": pos,
        "lucro_flutuante": flu, "drawdown_atual": 0, "detalhe": {"magic": str(magic), "simbolo": simbolo}})


def test_3_monitor_soma_uma_vez_por_conta_e_separa_fora_dos_bots(amb):
    """Dois bots na MESMA conta (como XAU e BTC do ensaio) + um bot em outra conta.
    A conta compartilhada tem +204,43 de flutuante que não é de nenhum bot."""
    uid = _pg("select user_id from conector_bots where id = %s", amb["bots"]["A"]["id"])[0][0]
    _pg("update conector_bots set ultimo_ping = null where user_id = %s", uid)   # só os bots deste teste ficam online
    toks, nomes = [], []
    for nome, simb in (("c20-xau", "XAUUSD"), ("c20-btc", "BTCUSD"), ("c20-outra", "XAUUSD")):
        nm = nome + "-" + uuid.uuid4().hex[:6]
        st, r, _ = _req("POST", E["BT_ISO_API"] + "/conector/registrar", {"nome": nm, "simbolo": simb}, tok=amb["sess"])
        assert st == 200, r
        toks.append(r["bot_token"]); nomes.append(nm)
    r0 = _snapc(toks[0], _magic(toks[0]), "XAUUSD", "52648209", 610085.89, 609881.34, 0); assert r0[0] == 200, r0[1]
    assert _snapc(toks[1], _magic(toks[1]), "BTCUSD", "52648209", 610085.77, 609881.34, 0)[0] == 200
    assert _snapc(toks[2], _magic(toks[2]), "XAUUSD", "777", 1000.00, 990.00, 10.00, pos=1)[0] == 200
    st, g, _ = _req("GET", E["BT_ISO_API"] + "/monitor/geral", tok=amb["sess"])
    assert st == 200, g
    assert g["operando"] == 3 and g["n_contas"] == 2
    assert g["equity_total"] == round(610085.77 + 1000.00, 2)          # e não 2×610 mil + 1000
    assert g["balance_total"] == round(609881.34 + 990.00, 2)
    assert g["flutuante_total"] == 10.00                               # só o que é dos bots
    c = {x["conta"]: x for x in g["contas"]}
    assert sorted(c["52648209"]["bots"]) == sorted(nomes[:2])
    assert c["52648209"]["flutuante_dos_bots"] == 0 and c["52648209"]["posicoes_dos_bots"] == 0
    assert c["52648209"]["flutuante_fora_dos_bots"] == 204.43 and c["52648209"]["ha_posicao_fora_dos_bots"] is True
    assert c["777"]["flutuante_fora_dos_bots"] == 0 and c["777"]["ha_posicao_fora_dos_bots"] is False
    assert "bot_token" not in json.dumps(g)
    amb["c20"] = toks


def test_4_vazio_sem_ordem_nao_manda_reinstalar(amb):
    """Bot sem posição e sem comando: o vazio é 'sem_ordem'. Com posição do bot e nenhum evento: 'sem_eventos'."""
    toks = amb["c20"]
    ids = {t: _pg("select id from conector_bots where bot_token = %s", t)[0][0] for t in toks}
    st, d, _ = _req("POST", E["BT_ISO_API"] + "/babymachine/operacoes", {"bot_id": ids[toks[1]], "dias": 1}, tok=amb["sess"])
    assert st == 200 and d["total"] == 0
    assert d["diagnostico"]["motivo"] == "sem_ordem", d["diagnostico"]
    assert d["diagnostico"]["posicoes_do_bot"] == 0 and d["diagnostico"]["comandos_no_periodo"] == 0
    st, d, _ = _req("POST", E["BT_ISO_API"] + "/babymachine/operacoes", {"bot_id": ids[toks[2]], "dias": 1}, tok=amb["sess"])
    assert d["diagnostico"]["motivo"] == "sem_eventos", d["diagnostico"]
    app = open(os.path.join(RAIZ, "app.html"), encoding="utf-8").read()
    assert "reenvie o bot com um NOME NOVO" not in app


def test_5_selecao_diz_onde_a_cadeia_para(amb):
    """Bot sem avaliação gravada cujo motor lê outro ativo: a mensagem nomeia o elo (motor), não 'leitor antigo'."""
    import time
    tok = amb["c20"][0]
    bid = _pg("select id from conector_bots where bot_token = %s", tok)[0][0]
    det = _det(tok)
    det["cv_motor"] = {"estado": "identidade_divergente", "motivo": "motor lê BTCUSD e o EA é XAUUSD", "leitor": "1.3-hml"}
    st, r, _ = _req("POST", E["BT_ISO_API"] + "/conector/snapshot", {
        "bot_token": tok, "conta_login": "52648209", "corretora": "Raw Trading Ltd", "simbolo": "XAUUSD",
        "magic_number": _magic(tok), "equity": 1, "balance": 1, "margem_livre": 1, "posicoes_abertas": 0,
        "lucro_flutuante": 0, "drawdown_atual": 0, "detalhe": det})
    assert st == 200, r
    st, d, _ = _req("POST", E["BT_ISO_API"] + "/learning/ciclos/ao-vivo", {"bot_id": bid, "dias": 1}, tok=amb["sess"])
    assert st == 200, d
    S = d["selecao"]
    assert S["disponivel"] is False and S["parou_em"] == "motor", S
    assert "identidade_divergente" in S["mensagem"] and "outro ativo" in S["mensagem"]
