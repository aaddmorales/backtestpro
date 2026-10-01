"""Testes da cópia HOMOLOG do conector v1.35 contra a bancada isolada (api 7.79 = commit 2b0e292).
Rede: o host homolog é reescrito para 127.0.0.1:8000 ABAIXO da trava (no HTTPAdapter.send),
de modo que a trava do conector é exercida exatamente como no PC. Nenhum token é impresso."""
import importlib, json, os, sys, types, uuid, pathlib, socket, tempfile
import pytest, requests

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI / "hml"))
sys.path.insert(0, str(AQUI.parent / "testes"))

HOME = tempfile.mkdtemp(prefix="hmlhome_")
os.environ["HOME"] = HOME; os.environ["USERPROFILE"] = HOME
os.environ["APPDATA"] = os.path.join(HOME, "AppData", "Roaming")

# winreg falso com memória (HKCU) — registra todo uso
CHAMADAS_REG = []
REG = {r"Software\Classes\bottested\shell\open\command": {"": '"C:\\Prod\\BotTested Conector.exe" "%1"'}}
fake = types.ModuleType("winreg")
fake.HKEY_CURRENT_USER = 1; fake.REG_SZ = 1
def _ck(root, path): CHAMADAS_REG.append(("CreateKey", path)); REG.setdefault(path, {}); return path
def _ok(root, path):
    if path not in REG: raise OSError("nao existe")
    return path
def _sub(base, sub): p = base + "\\" + sub; REG.setdefault(p, {}); CHAMADAS_REG.append(("CreateKey", p)); return p
fake.CreateKey = lambda root, path: _sub(root, path) if isinstance(root, str) else _ck(root, path)
fake.OpenKey = _ok
fake.SetValueEx = lambda k, name, r, t, v: (CHAMADAS_REG.append(("Set", k, name)), REG[k].__setitem__(name, v))
fake.QueryValueEx = lambda k, name: (REG[k][name], 1)
fake.CloseKey = lambda k: None
sys.modules["winreg"] = fake

# roteamento de teste (ABAIXO da trava, no HTTPAdapter.send):
#   homolog -> API local 127.0.0.1:8000 (ou o servidor-armadilha de redirect)
#   produção -> servidor-sentinela que CONTA acessos (tem que ficar em zero)
ROTAS = []
MAPA = {"https://homolog-homolog.up.railway.app": "http://127.0.0.1:8000"}
_send = requests.adapters.HTTPAdapter.send
def _send_local(self, req, **kw):
    ROTAS.append((req.method, req.url))
    for de, para in MAPA.items():
        if req.url.startswith(de + "/") or req.url == de:
            req.url = para + req.url[len(de):]
            break
    return _send(self, req, **kw)
requests.adapters.HTTPAdapter.send = _send_local

N = importlib.import_module("conector_nucleo_homolog")
import test_veredito_isolado as TV   # fixtures reais do ambiente isolado (registrar/enviar)


def test_h1_destino_e_trava():
    assert N.API_BASE == "https://homolog-homolog.up.railway.app"
    for url in ("https://backtestpro-production-eb9a.up.railway.app/mt5/presenca",
                "https://homolog-homolog.up.railway.app.evil.com/x", "http://127.0.0.1:8000/versao"):
        n0 = len(ROTAS)
        with pytest.raises(RuntimeError):
            requests.post(url, json={})
        assert len(ROTAS) == n0          # nada saiu: bloqueio ANTES do adaptador
    s = requests.Session()
    with pytest.raises(RuntimeError):
        s.get("https://backtestpro-production-eb9a.up.railway.app/versao")


def test_h2_identidade():
    assert N.APP_NOME == "BotTested Conector HOMOLOG" and N.APP_VERSAO == "v1.35-hml8"


def test_h3_h4_arquivos_separados():
    assert N.DEBUG_PATH == os.path.join(HOME, "BotTested_Conector_HOMOLOG_debug.log")
    assert N._CONFIG_PATH == os.path.join(HOME, "BotTested_Conector_HOMOLOG_config.json")
    N.salvar_token("tok-teste"); N.salvar_mt5_pin("C:/X/MQL5")
    assert N.ler_token_salvo() == "tok-teste" and N.ler_mt5_pin() == "C:/X/MQL5"
    assert "BotTested_Conector_config.json" not in os.listdir(HOME)
    assert "BotTested_Conector_debug.log" not in os.listdir(HOME)


def test_h5_autostart_intocado_protocolo_temporario_com_backup(monkeypatch):
    monkeypatch.setattr(N.sys, "executable", r"C:\Py\python.exe")   # como no PC (py -> python.exe)
    monkeypatch.setattr(N.sys, "argv", [os.path.join(HOME, "conector_homolog.py")])
    CMD = r"Software\Classes\bottested\shell\open\command"
    prod = REG[CMD][""]
    assert N.registrar_autostart() is False
    assert not any("Run" in str(c) for c in CHAMADAS_REG)                 # autostart da produção intocado
    assert N.registrar_protocolo() is True
    assert "conector_homolog" in REG[CMD][""] and REG[CMD][""].endswith('"%1"')
    bk = os.path.join(HOME, "BotTested_protocolo_PRODUCAO_backup.txt")
    assert open(bk, encoding="utf-8").read() == prod
    assert N.registrar_protocolo() is True                                # 2a vez: backup NÃO é sobrescrito
    assert open(bk, encoding="utf-8").read() == prod
    ok, det = N.restaurar_protocolo()
    assert ok and REG[CMD][""] == prod                                    # devolvido à produção
    N.registrar_protocolo()                                               # volta ao homolog p/ o ensaio


@pytest.fixture(scope="module")
def amb():
    E, _req = TV.E, TV._req
    assert all(E.values()) and os.environ.get("BT_PG_CONFIRMO_ISOLADO") == "1", "ambiente ausente (FALHA)"
    s, j = _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/token?grant_type=password",
                {"email": E["BT_ISO_EMAIL"], "password": E["BT_ISO_SENHA"]}, extra={"apikey": E["BT_ISO_ANON"]})
    tok = json.loads(j)["access_token"]
    s, v = _req("GET", E["BT_ISO_API"] + "/estrategias/vitrine?lang=pt", tok=tok)
    card = [e for e in json.loads(v)["estrategias"] if e["id"] == "teste_integracao_mt5"][0]
    bots = {}
    for k in ("A", "B", "M"):
        s, r = _req("POST", E["BT_ISO_API"] + "/conector/registrar",
                    {"nome": f"hml-conector-{k}-" + uuid.uuid4().hex[:6], "simbolo": "XAUUSD"}, tok=tok)
        bots[k] = json.loads(r)["bot_token"]
    return {"tok": tok, "card": card, "bots": bots}


def test_h6_h7_fluxo_real_na_api(amb):
    tA, tB = amb["bots"]["A"], amb["bots"]["B"]
    ROTAS.clear()
    ok, toks = N.listar_tokens_do_usuario(tA); assert ok and any(t["bot_token"] == tA for t in toks)
    ok, bots = N.listar_meus_bots(tA); assert ok and len(bots) >= 3
    assert N.listar_tokens_do_usuario("token-invalido") == (False, "HTTP 401")
    assert N.buscar_bot_pendente(tA) is None                     # sem job ainda
    job = TV._novo_job(amb, "A")
    p = N.buscar_bot_pendente(tA)
    assert p and p["job_id"] == job and p["pre_validado"] is False and "OnInit" in p["codigo"]
    bot_id = [b for b in bots][0]["id"]
    ok, msg = N.reinstalar_bot(tA, bot_id, os.path.join(HOME, "MQL5"))   # POST twin responde
    assert isinstance(ok, bool)
    assert N.checar_subir_conector(tA) is False
    # presença em lote (mesma chamada do conector.py)
    r = requests.post(f"{N.API_BASE}/mt5/presenca", json={"tokens": [tA, tB]}, timeout=8)
    assert r.status_code == 200 and tA in (r.json().get("pendentes") or [])
    # H7: veredito com token de OUTRO bot -> 403 BT-V01 registrado; legítimo -> 200; replay -> 409 BT-V02
    assert N.reportar_veredito(tB, job, True, "x") is False
    assert N.reportar_veredito(tA, job, True, "compile ok") is True
    assert N.reportar_veredito(tA, job, False, "replay") is False
    log = open(N.DEBUG_PATH, encoding="utf-8").read()
    assert f"veredito RECUSADO job={job} HTTP 403 codigo=BT-V01" in log
    assert f"veredito aceito job={job} aprovado=True" in log
    assert f"veredito RECUSADO job={job} HTTP 409 codigo=BT-V02" in log
    # H6: nenhum token em URL; todos os destinos = homolog
    for m, u in ROTAS:
        assert u.startswith("https://homolog-homolog.up.railway.app/"), u
        assert "bot_token" not in u and tA not in u and tB not in u, "token em URL"
    usados = {u.split("railway.app")[1] for _, u in ROTAS}
    assert {"/conector/tokens/listar", "/conector/meus-bots/listar", "/mt5/pendente/checar",
            "/conector/bot/mq5/baixar", "/mt5/subir-conector/checar", "/mt5/presenca",
            "/mt5/veredito"} <= usados
    assert tA not in log and tB not in log                      # log não guarda token


def test_h8_h9_janela_estatico():
    c = (AQUI / "hml" / "conector_homolog.py").read_text(encoding="utf-8")
    assert "from conector_nucleo_homolog import (" in c and "from conector_nucleo import" not in c
    assert "_LOCK_PORT = 50574" in c and "_LOCK_PORT = 50573" not in c
    assert "if not HOMOLOG and len(self.instalacoes) > 1" in c
    assert "_idx_instalacao_ativa()\n        self.combo_mt5.current(idx0)" not in c
    assert "salvar_mt5_pin(self.instalacoes[idx][\"mql5\"])" in c


def test_h9_portas_independentes():
    a = socket.socket(); a.bind(("127.0.0.1", 50573)); a.listen(1)   # "produção" aberta
    b = socket.socket(); b.bind(("127.0.0.1", 50574)); b.listen(1)   # homolog consegue ser dona
    a.close(); b.close()


# ═════════════════════════ hml2 ═════════════════════════
import threading, time, http.server

PROD = "https://backtestpro-production-eb9a.up.railway.app"
HML = "https://homolog-homolog.up.railway.app"


class _Srv:
    """Servidor local; conta hits. modo='redirect' responde 3xx p/ produção."""
    def __init__(self, codigo=None):
        self.hits, self.codigo = [], codigo
        dono = self
        class H(http.server.BaseHTTPRequestHandler):
            def _r(self):
                dono.hits.append((self.command, self.path))
                n = int(self.headers.get("Content-Length") or 0)
                if n: self.rfile.read(n)
                if dono.codigo:
                    self.send_response(dono.codigo)
                    self.send_header("Location", PROD + "/conector/tokens/listar?bot_token=segredo")
                    self.send_header("Content-Length", "0"); self.end_headers()
                else:
                    b = b'{"tokens":[]}'
                    self.send_response(200); self.send_header("Content-Length", str(len(b)))
                    self.end_headers(); self.wfile.write(b)
            do_GET = do_POST = do_PUT = _r
            def log_message(self, *a): pass
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.s.server_address[1]}"
        threading.Thread(target=self.s.serve_forever, daemon=True).start()


@pytest.mark.parametrize("codigo", [301, 302, 303, 307, 308])
def test_r1_redirect_para_producao_nunca_sai(codigo):
    armadilha, sentinela = _Srv(codigo), _Srv()
    MAPA_ant = dict(MAPA)
    MAPA.clear(); MAPA[HML] = armadilha.url; MAPA[PROD] = sentinela.url
    try:
        ok, msg = N.listar_tokens_do_usuario("tok-redirect")          # POST com token no corpo
        assert ok is False and msg == f"HTTP {codigo}"
        r = requests.get(HML + "/x", allow_redirects=True, timeout=5)  # pedido explícito p/ seguir
        assert r.status_code == codigo
        with requests.Session() as s:                                  # resolve_redirects manual
            r = s.post(HML + "/y", json={"bot_token": "tok"}, timeout=5)
            with pytest.raises(RuntimeError):
                list(s.resolve_redirects(r, r.request))
        with pytest.raises(RuntimeError):                              # send direto
            requests.Session().send(requests.Request("GET", PROD + "/z").prepare())
        assert sentinela.hits == [], "chegou requisição na 'produção'"
        assert len(armadilha.hits) == 3
        log = open(N.DEBUG_PATH, encoding="utf-8").read()
        assert f"redirecionamento RECUSADO HTTP {codigo} -> host=backtestpro-production-eb9a.up.railway.app" in log
        assert "segredo" not in log
    finally:
        MAPA.clear(); MAPA.update(MAPA_ant)
        armadilha.s.shutdown(); sentinela.s.shutdown()


# ── MT5 falso (estrutura real de pastas do Windows) ──
def _terminal(nome, servidor="ICMarketsSC-Demo", login="52012345", algo="disabled", diario=True, ini=False):
    term = os.path.join(os.environ["APPDATA"], "MetaQuotes", "Terminal", nome)
    mql5 = os.path.join(term, "MQL5")
    os.makedirs(os.path.join(mql5, "Experts"), exist_ok=True)
    os.makedirs(os.path.join(term, "logs"), exist_ok=True)
    prog = os.path.join(HOME, "Programas", nome); os.makedirs(prog, exist_ok=True)
    me = os.path.join(prog, "metaeditor64.exe"); open(me, "wb").write(b"MZ")
    open(os.path.join(term, "origin.txt"), "wb").write(("﻿" + prog).encode("utf-16-le"))
    if diario:
        linhas = [f"LL\t0\t10:00:01.000\tNetwork\t'{login}': authorized on {servidor} through Access Point EU 1"]
        if algo:
            linhas.append(f"QS\t0\t10:00:02.000\tExperts\tautomated trading is {algo}")
        _grava_diario(term, "20260929.log", linhas)
    if ini:
        os.makedirs(os.path.join(term, "config"), exist_ok=True)
        open(os.path.join(term, "config", "common.ini"), "wb").write(
            ("﻿[Common]\r\nLogin=" + login + "\r\nServer=" + servidor + "\r\n").encode("utf-16-le"))
    return mql5, me


def _grava_diario(term, arq, linhas, modo="wb"):
    with open(os.path.join(term, "logs", arq), modo) as f:
        f.write(("﻿" if modo == "wb" else "").encode("utf-16-le") + ("\r\n".join(linhas) + "\r\n").encode("utf-16-le"))


def _exec_ok(cmd, erros=0, cita=True, gera_ex5=True):
    mq5 = cmd[1].split(":", 1)[1]; log = cmd[3].split(":", 1)[1]
    assert cmd[2] == "/inc:" + os.path.dirname(os.path.dirname(mq5))   # includes da própria DEMO
    nome = mq5 if cita else "outro.mq5"
    txt = (f"{nome} : information: compiling '{os.path.basename(nome)}'\r\n"
           f"Result: {erros} errors, 0 warnings, 312 msec elapsed, cpu='X64 Regular'\r\n")
    open(log, "wb").write(b"\xff\xfe" + txt.encode("utf-16-le"))
    if gera_ex5 and erros == 0:
        open(mq5[:-4] + ".ex5", "wb").write(b"EX5-" + os.urandom(8))


def test_d1_conferencia_demo_e_gate():
    mql5, _ = _terminal("A" * 32)
    N.resetar_demo()
    info = N.conferir_demo(mql5)
    assert (info["servidor"], info["login"], info["demo"], info["autotrading"]) == \
           ("ICMarketsSC-Demo", "52012345", True, "off")
    assert info["programa"].endswith("A" * 32) and info["fonte"] == "diario:20260929.log"
    assert N.gate_demo(mql5)[1].startswith("BT-HML-D02")               # sem confirmação visual
    N.confirmar_demo(mql5, info); assert N.gate_demo(mql5) == (True, "ok")
    assert N._ler_config()["demo_conf"]["mql5"] == mql5                  # hml4: confirmação persiste
    outro, _ = _terminal("B" * 32)
    assert N.gate_demo(outro)[1].startswith("BT-HML-D02")              # outra instalação: não vale
    term = os.path.dirname(mql5)
    _grava_diario(term, "20260929.log", ["x\tExperts\tautomated trading is enabled"], modo="ab")
    assert N.gate_demo(mql5) == (True, "ok")                           # hml3: AutoTrading ligado aceito na DEMO
    assert "AutoTrading LIGADO na DEMO" in open(N.DEBUG_PATH, encoding="utf-8").read()
    _grava_diario(term, "20260930.log", ["x\tNetwork\t'52099999': authorized on ICMarketsSC-Demo02 through AP"])
    _grava_diario(term, "20260930.log", ["x\tExperts\tautomated trading is disabled"], modo="ab")
    assert N.gate_demo(mql5)[1].startswith("BT-HML-D04")               # trocou de conta
    _grava_diario(term, "20261001.log", ["x\tNetwork\t'1234': authorized on ICMarketsSC-Live07 through AP"])
    i2 = N.conferir_demo(mql5); assert i2["demo"] is False
    N.confirmar_demo(mql5, i2); assert N.gate_demo(mql5)[1].startswith("BT-HML-D03")   # conta real
    real, _ = _terminal("C" * 32, servidor="ICMarketsSC-Live12", login="999")
    assert N.conferir_demo(real)["demo"] is False
    ini, _ = _terminal("D" * 32, diario=False, ini=True)
    i3 = N.conferir_demo(ini); assert i3["demo"] and i3["fonte"] == "common.ini" and i3["autotrading"] == "desconhecido"
    assert N.gate_demo(None)[1].startswith("BT-HML-D01")
    N.resetar_demo()


def test_c1_compilacao_estrita_casos():
    mql5, me = _terminal("E" * 32)
    cod = "//+ MASTER teste\nint OnInit(){return 0;}\nvoid OnTick(){}\n"
    ok, dest = N.instalar_ea(cod, "Bot HML.mq5", mql5)
    C = lambda **k: N.compilar_estrito(dest, cod, me, mql5, _executar=lambda c: _exec_ok(c, **k))
    st, log = C(); assert st == "aprovado" and "0 errors" in log and os.path.isfile(dest[:-4] + ".ex5")
    assert C(erros=2)[1].startswith("BT-HML-C02") and C(erros=2)[0] == "reprovado"
    assert C(cita=False)[1].startswith("BT-HML-C05")
    assert C(gera_ex5=False)[1].startswith("BT-HML-C04")
    # log/ex5 ANTIGOS com 0 errors não servem: são apagados antes; MetaEditor mudo -> C01
    C(); st, log = N.compilar_estrito(dest, cod, me, mql5, _executar=lambda c: None)
    assert (st, log[:10]) == ("reprovado", "BT-HML-C01") and not os.path.isfile(dest[:-4] + ".ex5")
    assert N.compilar_estrito(dest, cod + "x", me, mql5, _executar=_exec_ok)[1].startswith("BT-HML-C03")
    # hml5: como o Windows grava (modo texto, \r\n) — o mesmo código TEM que passar
    open(dest, "wb").write(cod.replace("\n", "\r\n").encode("utf-8"))
    assert C()[0] == "aprovado"
    open(dest, "wb").write((cod + "//x").replace("\n", "\r\n").encode("utf-8"))
    assert C()[1].startswith("BT-HML-C03")
    open(dest, "wb").write(cod.replace("\n", "\r\n").encode("utf-8"))   # volta ao código do job
    assert N.compilar_estrito(dest, cod, None, mql5)[0] == "indisponivel"
    def _falha(c): raise OSError("acesso negado")
    assert N.compilar_estrito(dest, cod, me, mql5, _executar=_falha)[1].startswith("BT-HML-M02")
    assert N.achar_metaeditor_hml(mql5) == me                          # só o da própria instalação
    assert N.achar_metaeditor_hml(os.path.join(HOME, "sem", "MQL5")) is None


def _job_db(job_id):
    c = TV._pg(); cur = c.cursor()
    cur.execute("select status, aprovado, pre_validado, left(log, 60) from mt5_jobs where job_id=%s", (job_id,))
    r = cur.fetchone(); c.close(); return r


def test_v1_fluxo_real_api_veredito_so_apos_compile(amb):
    tA = amb["bots"]["A"]
    mql5, me = _terminal("F" * 32)
    N.resetar_demo()
    # 1) gate fechado: o job NEM é buscado e fica 'validando'
    job = TV._novo_job(amb, "A")
    ROTAS.clear()
    assert N.validar_pendente(tA, mql5, _executar=_exec_ok)[2].startswith("BT-HML-D02")
    assert not any("/mt5/pendente" in u for _, u in ROTAS)
    assert _job_db(job)[:2] == ("validando", None)
    N.confirmar_demo(mql5, N.conferir_demo(mql5))
    # 2) sem MetaEditor -> veredito FALSO explícito (indisponível), nunca aprovação
    os.rename(me, me + ".off")
    h, ap, msg = N.validar_pendente(tA, mql5, _executar=_exec_ok)
    assert (h, ap) == (True, False) and msg.startswith("indisponivel")
    st = _job_db(job); assert st[0] != "aprovado" and st[1] is False and st[3].startswith("INDISPONIVEL")
    os.rename(me + ".off", me)
    # 3) erro de compilação -> reprovado
    job = TV._novo_job(amb, "A")
    h, ap, msg = N.validar_pendente(tA, mql5, _executar=lambda c: _exec_ok(c, erros=3))
    assert (h, ap) == (True, False) and _job_db(job)[1] is False
    # 4) pre_validado=True forçado no job -> ainda compila; sem compile real não aprova
    job = TV._novo_job(amb, "A")
    orig = N.buscar_bot_pendente
    N.buscar_bot_pendente = lambda t: dict(orig(t) or {}, pre_validado=True)
    try:
        h, ap, msg = N.validar_pendente(tA, mql5, _executar=lambda c: None)   # MetaEditor mudo
    finally:
        N.buscar_bot_pendente = orig
    assert ap is False and _job_db(job)[1] is False
    # 5) positivo: compile.log 0 errors + .ex5 novo -> aprovado na nuvem
    job = TV._novo_job(amb, "A")
    assert _job_db(job)[2] is False                                    # MASTER: servidor manda pre_validado=False
    h, ap, msg = N.validar_pendente(tA, mql5, _executar=_exec_ok)
    assert (h, ap) == (True, True) and msg.startswith("aprovado")
    st = _job_db(job); assert st[1] is True and st[0] == "aprovado", st
    # 6) mesmo código já aprovado (cache aprovado) -> MASTER continua pre_validado=False
    s, r = TV._req("POST", TV.E["BT_ISO_API"] + "/mt5/enviar", {
        "bot_nome": "Pytest Veredito", "bot_token": tA, "codigo": amb["card"]["codigo"],
        "ativo": "XAU/USD (Ouro)", "timeframe": "15m", "estrategia_id": "teste_integracao_mt5"}, tok=amb["tok"])
    assert s == 200 and N.buscar_bot_pendente(tA)["pre_validado"] is False
    log = open(N.DEBUG_PATH, encoding="utf-8").read()
    assert "HOMOLOG: compilado ex5_sha256=" in log and tA not in log
    N.resetar_demo()


def test_h10_h11_janela_estatico():
    c = (AQUI / "hml" / "conector_homolog.py").read_text(encoding="utf-8")
    assert "self._hml_conferir_demo" in c and "resetar_demo()   # HOMOLOG H10" in c
    assert "[:8]}" not in c and "{argv}" not in c
    n = (AQUI / "hml" / "conector_nucleo_homolog.py").read_text(encoding="utf-8")
    corpo = n[n.index("def validar_pendente("):n.index("def checar_subir_conector")]
    assert "validar_sintaxe_mq5" not in corpo and "achar_metaeditor()" not in corpo
    assert "reportar_veredito(bot_token, job_id, True" not in corpo    # nenhum atalho de aprovação


def test_h13_snapshot_leva_versao_do_conector(amb):
    tA = amb["bots"]["A"]
    import hashlib as _h
    mg = 100000 + (int(_h.sha1(("bot|" + tA).encode()).hexdigest()[:12], 16) % 1_900_000_000)
    assert N.enviar_snapshot(tA, {"magic": str(mg), "simbolo": "XAUUSD", "posicoes": "0", "equity": "1000"})
    r = TV._pg().cursor(); r.execute("select detalhe_json->>'conector_versao' from conector_snapshots where bot_token=%s order by id desc limit 1", (tA,))
    assert r.fetchone()[0] == "BotTested Conector HOMOLOG v1.35-hml8"


# ═════════════════════ hml8 — ponte do motor real (leitor + motor congelado) ═════════════════════
sys.path.insert(0, str(AQUI.parent / "motor_ciclos" / "testes"))
import fixture_motor as FM          # leitor REAL do motor + MT5 FALSO (barras sintéticas)


def _magic(tok):
    import hashlib as _h
    return 100000 + (int(_h.sha1(("bot|" + tok).encode()).hexdigest()[:12], 16) % 1_900_000_000)


@pytest.fixture()
def motor_pc(tmp_path, monkeypatch):
    FM.esperar_janela_segura()
    dados = tmp_path / "dados"; data_path = tmp_path / "Terminal" / "ABC"
    r = FM.rodar_leitor(str(dados), data_path=str(data_path))
    assert r.returncode == 0, r.stderr[-1500:]
    monkeypatch.setenv("BT_CV_ESPELHO", str(dados))
    monkeypatch.setenv("BT_CV_MOTOR_DIR", FM.MOTOR)
    monkeypatch.setattr(N, "ler_mt5_pin", lambda: str(data_path / "MQL5"))
    N._CV_LEITOR = None; N._CV_CACHE.clear()
    sys.modules.pop("bt_conector_atestado", None)
    return dados


def test_h15_ponte_motor_falhas_nomeadas(motor_pc, monkeypatch):
    import json as _j
    d0 = FM.det_ea(123456)
    monkeypatch.delenv("BT_CV_ESPELHO", raising=False)
    d = dict(d0); N._cv_atestar(d, "tok")
    assert d["cv_motor"]["estado"] == "nao_configurado" and "cv_atestado" not in d
    monkeypatch.setenv("BT_CV_ESPELHO", str(motor_pc))
    monkeypatch.delenv("BT_CV_SEGREDO", raising=False)
    d = dict(d0); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "segredo_ausente"
    monkeypatch.setenv("BT_CV_SEGREDO", "x" * 32)
    d = dict(d0, conta="999"); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "identidade_divergente"
    d = dict(d0, simbolo="BTCUSD"); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "identidade_divergente"
    d = dict(d0, tsrv=str(int(d0["tgmt"]) + 7200)); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "fuso_divergente"
    v = d0["c15m"].split(";"); x = v[-2].split(","); x[3] = f"{float(x[3]) + 1:.2f}"; v[-2] = ",".join(x)
    d = dict(d0, c15m=";".join(v)); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "identidade_divergente"
    pv = d0["cvt"].split("."); pv[6] = str(int(pv[6]) + 900)
    d = dict(d0, cvt=".".join(pv)); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "espelho_atrasado"
    monkeypatch.setattr(N, "ler_mt5_pin", lambda: "/outra/instalacao/MQL5")
    d = dict(d0); N._cv_atestar(d, "tok"); assert d["cv_motor"]["estado"] == "identidade_divergente"
    sau = _j.load(open(motor_pc / "SAUDE.json")); sau["agora_utc"] = "2026-01-01T00:00:00+00:00"
    _j.dump(sau, open(motor_pc / "SAUDE.json", "w"))
    d = dict(d0); N._cv_atestar(d, "tok")
    assert d["cv_motor"]["estado"] == "processo_parado" and "cv_atestado_falha" in d
    for v_ in d.values():
        assert "x" * 32 not in str(v_)


def test_h15_motor_real_ate_a_api(amb, motor_pc, monkeypatch):
    seg = os.environ.get("BT_CV_SEGREDO_API", "")
    assert seg, "BT_CV_SEGREDO_API (o mesmo da API local) obrigatório (FALHA, não skip)"
    monkeypatch.setenv("BT_CV_SEGREDO", seg)
    tA = amb["bots"]["M"]   # bot só do motor: 1º snapshot da barra já vem da ponte
    dados = FM.det_ea(_magic(tA))
    assert N.enviar_snapshot(tA, dict(dados))
    cur = TV._pg().cursor()
    cur.execute("select detalhe_json->'cv_atestado'->>'versao_motor', detalhe_json->'cv_motor'->>'estado', "
                "detalhe_json->'cv_atestado'->>'ts_barra_m15' "
                "from conector_snapshots where bot_token=%s order by id desc limit 1", (tA,))
    vm, est, tsb = cur.fetchone()
    assert (vm, est) == ("cv1-2.4", "ok"), (vm, est)
    bid = TV._pg().cursor(); bid.execute("select id from conector_bots where bot_token=%s", (tA,))
    b_id = bid.fetchone()[0]
    s, j = TV._req("POST", TV.E["BT_ISO_API"] + "/learning/ciclos/ao-vivo", {"bot_id": b_id}, tok=amb["tok"])
    j = json.loads(j)
    elos = [(e["elo"][:2], e["estado"]) for e in j["ciclos"]["elos"]]
    assert all(st == "ok" for _, st in elos), j["ciclos"]["elos"]
    assert j["ciclos"]["atestado"]["estado"] == "verificado"
    assert j["leituras"]["barra_m15_utc"] == j["ciclos"]["atestado"]["ts_barra_m15"] == tsb.replace("Z", "+00:00")
    assert j["leituras"]["motor"]["leitura"]["topdown"][0] == j["ciclos"]["atestado"]["cv1"]["veredito"]
    # mais 3 snapshots da MESMA barra: 1 linha, nenhuma decisão/comando, atestado registrado uma vez
    cur.execute("select n_snapshots from ciclo_leituras where bot_id=%s and barra_m15=%s", (b_id, tsb))
    n0 = cur.fetchone()[0]
    for _ in range(3):
        assert N.enviar_snapshot(tA, dict(dados))
    cur.execute("select count(*), max(n_snapshots) from ciclo_leituras where bot_id=%s and barra_m15=%s",
                (b_id, tsb))
    assert cur.fetchone() == (1, n0 + 3)
    cur.execute("select etapa, estado from ciclo_trilha where bot_id=%s and barra_m15=%s order by id", (b_id, tsb))
    et = cur.fetchall()
    assert [e for e, _ in et].count("atestado") == 1 and ("motor", "ok") in et and ("atestado", "ok") in et, et
    cur.execute("select count(*) from ciclo_decisoes where bot_id=%s", (b_id,)); assert cur.fetchone()[0] == 0
    cur.execute("select count(*) from mt5_comandos where bot_id=%s and tipo in ('buy','sell')", (b_id,))
    assert cur.fetchone()[0] == 0