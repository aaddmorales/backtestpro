"""C27R12 — consulta do plano estrita: falha != Free.
Offline: classificacao da credencial. Isolado (API real + Auth + PostgREST +
Postgres locais; ausente = FALHA, nunca skip):
  - servidor com chave PUBLICA (anon) -> backtest MASTER = 503 perfil_indisponivel
    (antes: 403 ativo_bloqueado, o sintoma da plataforma);
  - servidor com service_role -> PRO roda o MASTER em XAU/15m/6 meses: 0 trades,
    linha em backtests_historico com estrategia_id;
  - conta Free continua 403 ativo_bloqueado em XAU;
  - perfil inexistente -> 503 (nunca Free)."""
import base64, json, os, subprocess, sys, time, uuid, urllib.request, urllib.error
import psycopg2, pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
E = {k: os.environ.get(k, "") for k in ("BT_ISO_API", "BT_ISO_SUPABASE", "BT_ISO_ANON", "BT_ISO_EMAIL",
                                         "BT_ISO_SENHA", "BT_PG_ISOLADO_URL", "BT_ISO_API_PUBLICA")}


def _jwt(role):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return b({"alg": "HS256"}) + "." + b({"role": role}) + ".x"


@pytest.mark.parametrize("valor,tipo", [("", "ausente"), (_jwt("service_role"), "service_role"),
    (_jwt("anon"), "publica"), (_jwt("authenticated"), "publica"), ("sb_publishable_abc", "publica"),
    ("sb_secret_abc", "secret"), ("lixo", "desconhecida")])
def test_classe_da_credencial(monkeypatch, valor, tipo):
    import api
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", valor)
    assert api._sb_credencial_tipo() == tipo


def _req(metodo, url, corpo=None, tok=None, extra=None):
    h = {"Content-Type": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    h.update(extra or {})
    rq = urllib.request.Request(url, data=(json.dumps(corpo).encode() if corpo is not None else None), headers=h, method=metodo)
    try:
        r = urllib.request.urlopen(rq, timeout=180); return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _login(email, senha):
    s, j = _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/token?grant_type=password",
                {"email": email, "password": senha}, extra={"apikey": E["BT_ISO_ANON"]})
    assert s == 200, j
    return j["access_token"], j["user"]["id"]


@pytest.fixture(scope="module")
def amb():
    faltam = [k for k, v in E.items() if not v]
    assert not faltam and os.environ.get("BT_PG_CONFIRMO_ISOLADO") == "1", f"ambiente ausente (FALHA, nao skip): {faltam}"
    tok, uid = _login(E["BT_ISO_EMAIL"], E["BT_ISO_SENHA"])
    s, v = _req("GET", E["BT_ISO_API"] + "/estrategias/vitrine?lang=pt", tok=tok)
    card = [e for e in v["estrategias"] if e["id"] == "teste_integracao_mt5"][0]
    return {"tok": tok, "uid": uid, "card": card}


def _corpo(amb, **kw):
    c = {"ativo": "XAU/USD (Ouro)", "periodo": "6 meses", "timeframe": "15m", "indicador": "__custom__",
         "estrategia_id": "teste_integracao_mt5", "codigo": amb["card"]["codigo"], "sessao_id": str(uuid.uuid4())}
    c.update(kw); return c


def test_servidor_com_chave_publica_da_503_e_nao_ativo_bloqueado(amb):
    s, j = _req("POST", E["BT_ISO_API_PUBLICA"] + "/backtest/custom", _corpo(amb), tok=amb["tok"])
    assert s == 503 and j["detail"]["code"] == "perfil_indisponivel", (s, j)
    s, v = _req("GET", E["BT_ISO_API_PUBLICA"] + "/versao")
    assert v["supabase_credencial_servidor"] == "publica"


def test_pro_roda_master_xau_e_grava_historico(amb):
    sid = str(uuid.uuid4())
    s, j = _req("POST", E["BT_ISO_API"] + "/backtest/custom", _corpo(amb, sessao_id=sid), tok=amb["tok"])
    assert s == 200 and j["total_trades"] == 0 and j["_credito"]["plano"] == "pro", (s, j)
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); cur = c.cursor()
    cur.execute("select ativo, timeframe, periodo, total_trades, parametros->>'estrategia_id' from backtests_historico where sessao_id=%s", (sid,))
    assert cur.fetchone() == ("XAU/USD (Ouro)", "15m", "6 meses", 0, "teste_integracao_mt5"); c.close()
    s, v = _req("GET", E["BT_ISO_API"] + "/versao")
    assert v["supabase_credencial_servidor"] == "service_role"


def test_free_continua_bloqueado_em_xau(amb):
    email = f"free-{uuid.uuid4().hex[:8]}@example.com"
    _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/signup", {"email": email, "password": "Free-Senha-Local-1"}, extra={"apikey": E["BT_ISO_ANON"]})
    tok, uid = _login(email, "Free-Senha-Local-1")
    s, j = _req("POST", E["BT_ISO_API"] + "/backtest/custom",
                _corpo(amb, estrategia_id=None, codigo=amb["card"]["codigo"]), tok=tok)
    assert s == 403 and j["detail"]["code"] == "ativo_bloqueado" and j["detail"]["plano"] == "free", (s, j)


def test_perfil_inexistente_503_nunca_free(amb):
    email = f"semperfil-{uuid.uuid4().hex[:8]}@example.com"
    _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/signup", {"email": email, "password": "Sem-Perfil-Local-1"}, extra={"apikey": E["BT_ISO_ANON"]})
    tok, uid = _login(email, "Sem-Perfil-Local-1")
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); c.autocommit = True; cur = c.cursor()
    cur.execute("delete from perfis where id=%s", (uid,)); c.close()
    s, j = _req("POST", E["BT_ISO_API"] + "/backtest/custom", _corpo(amb, ativo="S&P500", estrategia_id=None), tok=tok)
    assert s == 503 and j["detail"]["code"] == "perfil_indisponivel", (s, j)
