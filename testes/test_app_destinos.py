"""C27R9 — GET /app: destinos BT_APP_* tudo-ou-nada + literal JS seguro (offline)."""
import base64, json, os, shutil, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOMES = ("BT_APP_SUPABASE_URL", "BT_APP_SUPABASE_ANON", "BT_APP_API_BASE")


def _jwt(role):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return b({"alg": "HS256", "typ": "JWT"}) + "." + b({"role": role, "iss": "t"}) + ".assinatura_de_teste_xx"


BOM = {"BT_APP_SUPABASE_URL": "https://abcdefghijklmnop.supabase.co",
       "BT_APP_SUPABASE_ANON": _jwt("anon"),
       "BT_APP_API_BASE": "https://api-isolada.example.com"}


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.chdir(RAIZ)
    for n in NOMES:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    import api
    api._APP_CACHE.clear()
    return TestClient(api.app), monkeypatch, api


def test_sem_env_serve_cru_fail_closed(cli):
    c, mp, api = cli
    r = c.get("/app")
    assert r.status_code == 200
    assert r.content == open(os.path.join(RAIZ, "app.html"), "rb").read()
    assert r.text.count("CONFIGURAR") == 3


def test_tres_validas_injeta_como_literal_json(cli):
    c, mp, api = cli
    for k, v in BOM.items():
        mp.setenv(k, v)
    r = c.get("/app")
    assert r.status_code == 200 and "CONFIGURAR" not in r.text
    assert 'const SUPABASE_URL = "https://abcdefghijklmnop.supabase.co";' in r.text
    assert 'const API = "https://api-isolada.example.com";' in r.text
    assert f'const SUPABASE_ANON = "{BOM["BT_APP_SUPABASE_ANON"]}";' in r.text


@pytest.mark.parametrize("presentes", [("BT_APP_SUPABASE_URL",), ("BT_APP_SUPABASE_URL", "BT_APP_API_BASE"),
                                       ("BT_APP_SUPABASE_ANON",), ("BT_APP_API_BASE", "BT_APP_SUPABASE_ANON")])
def test_parcial_recusa_503_sem_vazar_valor(cli, presentes):
    c, mp, api = cli
    for k in presentes:
        mp.setenv(k, BOM[k])
    r = c.get("/app")
    assert r.status_code == 503
    j = r.json()
    assert j["erro"] == "app_destinos_invalidos"
    assert set(j["envs_com_defeito"]) == set(NOMES) - set(presentes)
    for k in presentes:
        assert BOM[k] not in r.text


@pytest.mark.parametrize("url", [
    "https://x.supabase.co';alert(1);//", "https://x.supabase.co/</script><script>alert(1)</script>",
    "https://user:pw@x.supabase.co", "https://x.supabase.co/rest", "https://x.supabase.co?a=1",
    "https://x.supabase.co#f", "http://x.supabase.co", "javascript:alert(1)", "https://X.supabase.co",
    " https://x.supabase.co", "https://localhost@evil.example", "https://semponto", "ftp://x.example.com",
    "http://127.0.0.1.evil.example"])
def test_url_hostil_ou_fora_da_forma_recusada(cli, url):
    c, mp, api = cli
    for k, v in BOM.items():
        mp.setenv(k, v)
    mp.setenv("BT_APP_SUPABASE_URL", url)
    r = c.get("/app")
    assert r.status_code == 503 and r.json()["envs_com_defeito"] == ["BT_APP_SUPABASE_URL"]
    assert "alert(1)" not in r.text


def test_loopback_http_aceito_so_literal(cli):
    c, mp, api = cli
    for k, v in BOM.items():
        mp.setenv(k, v)
    mp.setenv("BT_APP_API_BASE", "http://127.0.0.1:8000")
    assert c.get("/app").status_code == 200


@pytest.mark.parametrize("anon", [_jwt("service_role"), _jwt("authenticated"), "sb_secret_abcdefghijklmnopqrstuvwxyz",
                                  "chave'invalida\"</script>xxxxxxxxxxxxxx", "curta"])
def test_chave_que_nao_e_anon_recusada(cli, anon):
    c, mp, api = cli
    for k, v in BOM.items():
        mp.setenv(k, v)
    mp.setenv("BT_APP_SUPABASE_ANON", anon)
    r = c.get("/app")
    assert r.status_code == 503 and r.json()["envs_com_defeito"] == ["BT_APP_SUPABASE_ANON"]
    assert anon not in r.text


def test_service_key_nunca_vai_pro_navegador(cli):
    c, mp, api = cli
    for k, v in BOM.items():
        mp.setenv(k, v)
    mp.setenv("SUPABASE_SERVICE_KEY", BOM["BT_APP_SUPABASE_ANON"])
    r = c.get("/app")
    assert r.status_code == 503 and r.json()["envs_com_defeito"] == ["BT_APP_SUPABASE_ANON"]


def test_ancora_duplicada_ou_ausente_fail_closed(cli, tmp_path):
    c, mp, api = cli
    for k, v in BOM.items():
        mp.setenv(k, v)
    html = open(os.path.join(RAIZ, "app.html"), encoding="utf-8").read()
    dup = html.replace("const API = 'https://CONFIGURAR-API-ISOLADA.invalid';",
                       "const API = 'https://CONFIGURAR-API-ISOLADA.invalid';\nconst API = 'https://CONFIGURAR-API-ISOLADA.invalid';")
    (tmp_path / "app.html").write_text(dup, encoding="utf-8")
    mp.chdir(tmp_path)
    api._APP_CACHE.clear()
    r = c.get("/app")
    assert r.status_code == 500 and r.json() == {"erro": "app_ancora_ausente_ou_duplicada", "env": "BT_APP_API_BASE"}


def test_literal_js_nao_fecha_string_nem_tag():
    import api
    s = api._app_literal_js("</script><b>&'\" ")
    assert "<" not in s and ">" not in s and "&" not in s and " " not in s
    assert json.loads(s.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")) == "</script><b>&'\" "
