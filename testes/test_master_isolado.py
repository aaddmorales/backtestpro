"""C27R9 — card MASTER contra o AMBIENTE ISOLADO LOCAL real (API + GoTrue +
PostgREST + Postgres). Ambiente ausente = FALHA (nunca skip).
Envs: BT_ISO_API (ex. http://127.0.0.1:8000), BT_ISO_SUPABASE, BT_ISO_ANON,
BT_ISO_EMAIL/BT_ISO_SENHA (usuario do BT_CARD_TESTE_USER) e
BT_PG_ISOLADO_URL + BT_PG_CONFIRMO_ISOLADO=1."""
import json, os, uuid, urllib.request, urllib.error
import psycopg2, pytest

E = {k: os.environ.get(k, "") for k in ("BT_ISO_API", "BT_ISO_SUPABASE", "BT_ISO_ANON", "BT_ISO_EMAIL",
                                         "BT_ISO_SENHA", "BT_PG_ISOLADO_URL")}


def _req(metodo, url, corpo=None, tok=None, extra=None):
    h = {"Content-Type": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    h.update(extra or {})
    rq = urllib.request.Request(url, data=(json.dumps(corpo).encode() if corpo is not None else None), headers=h, method=metodo)
    try:
        r = urllib.request.urlopen(rq, timeout=120); return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _login(email, senha):
    s, j = _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/token?grant_type=password",
                {"email": email, "password": senha}, extra={"apikey": E["BT_ISO_ANON"]})
    assert s == 200, j
    return j["access_token"]


@pytest.fixture(scope="module")
def amb():
    faltam = [k for k, v in E.items() if not v]
    assert not faltam and os.environ.get("BT_PG_CONFIRMO_ISOLADO") == "1", f"ambiente ausente (FALHA, nao skip): {faltam}"
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); cur = c.cursor()
    cur.execute("select to_regclass('public._bt_homolog_marker') is not null"); assert cur.fetchone()[0]
    c.close()
    tok = _login(E["BT_ISO_EMAIL"], E["BT_ISO_SENHA"])
    s, v = _req("GET", E["BT_ISO_API"] + "/estrategias/vitrine?lang=pt", tok=tok)
    card = [e for e in v["estrategias"] if e["id"] == "teste_integracao_mt5"][0]
    s, r = _req("POST", E["BT_ISO_API"] + "/conector/registrar", {"nome": "pytest-master-" + uuid.uuid4().hex[:6], "simbolo": "XAU/USD (Ouro)"}, tok=tok)
    assert s == 200
    return {"tok": tok, "card": card, "bot": r["bot_token"]}


def _corpo(amb, **kw):
    c = {"bot_nome": "Pytest Master", "bot_token": amb["bot"], "codigo": amb["card"]["codigo"],
         "ativo": "XAU/USD (Ouro)", "timeframe": "15m", "estrategia_id": "teste_integracao_mt5",
         "estrategia_nome": amb["card"]["nome"]}
    c.update(kw); return c


def _jobs(bot):
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); cur = c.cursor()
    cur.execute("select count(*) from mt5_jobs where bot_token=%s", (bot,)); n = cur.fetchone()[0]; c.close(); return n


def test_vitrine_card_so_para_o_usuario_de_teste(amb):
    s, v = _req("GET", E["BT_ISO_API"] + "/estrategias/vitrine?lang=pt")
    assert "teste_integracao_mt5" not in [e["id"] for e in v["estrategias"]]
    outro = f"outro-{uuid.uuid4().hex[:8]}@example.com"
    _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/signup", {"email": outro, "password": "Outra-Senha-Local-1"}, extra={"apikey": E["BT_ISO_ANON"]})
    s, v = _req("GET", E["BT_ISO_API"] + "/estrategias/vitrine?lang=pt", tok=_login(outro, "Outra-Senha-Local-1"))
    assert "teste_integracao_mt5" not in [e["id"] for e in v["estrategias"]]
    c = amb["card"]
    assert c["nome"] == "MASTER TESTE MT5 — DEMO"
    assert c["ensaio"] == {"ativo": "XAU/USD (Ouro)", "periodo": "6 meses", "timeframe": "15m",
                           "ativos": ["XAU/USD (Ouro)", "BTC/USD"]}
    assert "BT_EXECUTOR_PURO" in c["codigo"]


def test_registro_simbolo_canonico(amb):
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); cur = c.cursor()
    cur.execute("select simbolo from conector_bots where bot_token=%s", (amb["bot"],))
    assert cur.fetchone()[0] == "XAUUSD"; c.close()


@pytest.mark.parametrize("campo,valor,motivo", [
    ("codigo", "# outro\nclass X(Strategy):\n    def next(self): self.buy()\n", "master_codigo_diverge_do_card"),
    ("ativo", "EUR/USD", "master_ativo_diverge_do_card"),
    ("ativo", "BTC/USD (Bitcoin)", "master_ativo_diverge_do_card"),          # só o nome exato da lista
    ("timeframe", "1d", "master_timeframe_diverge_do_card"),
    ("bot_nome", "   ", "master_sem_nome_de_bot")])
def test_envio_master_divergente_recusado_sem_escrita(amb, campo, valor, motivo):
    antes = _jobs(amb["bot"])
    s, j = _req("POST", E["BT_ISO_API"] + "/mt5/enviar", _corpo(amb, **{campo: valor}), tok=amb["tok"])
    assert s == 422 and j["detail"] == motivo
    assert _jobs(amb["bot"]) == antes


def test_envio_master_ok_identidade_e_compile_real(amb):
    s, j = _req("POST", E["BT_ISO_API"] + "/mt5/enviar", _corpo(amb), tok=amb["tok"])
    assert s == 200 and j["ok"] and len(j["job_id"]) == 16
    i = j["identidade"]
    assert i["estrategia_id"] == "teste_integracao_mt5" and i["ativo"] == "XAU/USD (Ouro)" and i["timeframe"] == "15m"
    assert i["bot_nome"] == "Pytest Master" and i["filename"] == "Pytest_Master.mq5" and i["pre_validado"] is False
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); cur = c.cursor()
    cur.execute("select status, pre_validado, magic from mt5_jobs where job_id=%s", (j["job_id"],))
    st, pv, mg = cur.fetchone()
    assert st == "validando" and pv is False and mg == i["magic"]
    cur.execute("select config_operacional from conector_bots where bot_token=%s", (amb["bot"],))
    cfg = cur.fetchone()[0]; c.close()
    assert cfg["estrategia_id"] == "teste_integracao_mt5" and cfg["timeframe_envio"] == "15m"
    assert cfg["bot_nome_envio"] == "Pytest Master" and cfg["codigo_sha1"] == i["codigo_sha1"]


def test_envio_de_outro_card_inalterado(amb):
    outro = "class Y(Strategy):\n    def init(self): pass\n    def next(self): return\n"
    s, j = _req("POST", E["BT_ISO_API"] + "/mt5/enviar",
                _corpo(amb, codigo="BT_MARCADOR = \"BT_EXECUTOR_PURO\"\n" + outro, estrategia_id="", ativo="BTC/USD", timeframe="1h"),
                tok=amb["tok"])
    assert s == 200 and j["ok"] and "identidade" not in j


def test_backtest_master_sem_fallback_silencioso(amb):
    base = {"ativo": "XAU/USD (Ouro)", "periodo": "6 meses", "timeframe": "15m", "indicador": "__custom__",
            "estrategia_id": "teste_integracao_mt5"}
    ruim = "class Quebra(Strategy):\n    def init(self):\n        raise ValueError('proposital')\n    def next(self): return\n"
    s, j = _req("POST", E["BT_ISO_API"] + "/backtest/custom", dict(base, codigo=ruim), tok=amb["tok"])
    assert s == 422 and j["detail"].startswith("master_codigo_falhou")
    s, j = _req("POST", E["BT_ISO_API"] + "/backtest/custom", dict(base, codigo=amb["card"]["codigo"]), tok=amb["tok"])
    assert s == 200 and j["total_trades"] == 0


def test_envio_master_btc_aceito_lista_fechada(amb):
    """C27R17: MASTER em BTC/USD 15m (ensaio no fim de semana). Símbolo canônico BTCUSD, identidade completa."""
    assert amb["card"]["mercados"] == ["XAU/USD (Ouro)", "BTC/USD"]
    s, r = _req("POST", E["BT_ISO_API"] + "/conector/registrar",
                {"nome": "pytest-master-btc-" + uuid.uuid4().hex[:6], "simbolo": "BTC/USD"}, tok=amb["tok"])
    assert s == 200
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); cur = c.cursor()
    cur.execute("select simbolo from conector_bots where bot_token=%s", (r["bot_token"],))
    assert cur.fetchone()[0] == "BTCUSD"
    s, j = _req("POST", E["BT_ISO_API"] + "/mt5/enviar",
                _corpo(amb, bot_token=r["bot_token"], bot_nome="Pytest Master BTC", ativo="BTC/USD"), tok=amb["tok"])
    assert s == 200 and j["ok"], j
    i = j["identidade"]
    assert i["estrategia_id"] == "teste_integracao_mt5" and i["ativo"] == "BTC/USD" and i["timeframe"] == "15m"
    cur.execute("select config_operacional from conector_bots where bot_token=%s", (r["bot_token"],))
    cfg = cur.fetchone()[0]; c.close()
    assert cfg["ativo_envio"] == "BTC/USD" and cfg["estrategia_id"] == "teste_integracao_mt5"
    # o EA gerado continua sendo o executor puro: nenhuma entrada nativa
    s, d = _req("POST", E["BT_ISO_API"] + "/mt5/pendente/checar", {"bot_token": r["bot_token"]})
    cod = d.get("codigo") or ""
    assert d.get("pendente") and "BTLerComando" in cod and "EXECUTOR PURO" in cod
