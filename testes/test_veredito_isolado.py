"""C27R10 — /mt5/veredito contra o AMBIENTE ISOLADO LOCAL real (API + Auth +
PostgREST + Postgres). Ambiente ausente = FALHA (nunca skip).
Prova: token ausente/errado/de outro bot/de bot excluido, job inexistente,
job_id ausente = MESMA recusa 403 byte-identica e ZERO alteracao em mt5_jobs
e mq5_cache; aprovacao legitima 1x; replay/reaprovacao/troca de veredito = 409
sem alteracao; corrida de 8 aprovacoes = 1 vencedor."""
import json, os, secrets, threading, uuid, urllib.request, urllib.error
import psycopg2, pytest

E = {k: os.environ.get(k, "") for k in ("BT_ISO_API", "BT_ISO_SUPABASE", "BT_ISO_ANON", "BT_ISO_EMAIL",
                                         "BT_ISO_SENHA", "BT_PG_ISOLADO_URL")}


def _req(metodo, url, corpo=None, tok=None, extra=None):
    h = {"Content-Type": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    h.update(extra or {})
    rq = urllib.request.Request(url, data=(json.dumps(corpo).encode() if corpo is not None else None), headers=h, method=metodo)
    try:
        r = urllib.request.urlopen(rq, timeout=120); return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _pg():
    c = psycopg2.connect(E["BT_PG_ISOLADO_URL"]); c.autocommit = True; return c


@pytest.fixture(scope="module")
def amb():
    faltam = [k for k, v in E.items() if not v]
    assert not faltam and os.environ.get("BT_PG_CONFIRMO_ISOLADO") == "1", f"ambiente ausente (FALHA, nao skip): {faltam}"
    c = _pg(); cur = c.cursor()
    cur.execute("select to_regclass('public._bt_homolog_marker') is not null"); assert cur.fetchone()[0]
    c.close()
    s, j = _req("POST", E["BT_ISO_SUPABASE"] + "/auth/v1/token?grant_type=password",
                {"email": E["BT_ISO_EMAIL"], "password": E["BT_ISO_SENHA"]}, extra={"apikey": E["BT_ISO_ANON"]})
    tok = json.loads(j)["access_token"]
    s, v = _req("GET", E["BT_ISO_API"] + "/estrategias/vitrine?lang=pt", tok=tok)
    card = [e for e in json.loads(v)["estrategias"] if e["id"] == "teste_integracao_mt5"][0]
    bots = {}
    for k in ("A", "B", "X"):
        s, r = _req("POST", E["BT_ISO_API"] + "/conector/registrar",
                    {"nome": f"pytest-veredito-{k}-" + uuid.uuid4().hex[:6], "simbolo": "XAUUSD"}, tok=tok)
        bots[k] = json.loads(r)["bot_token"]
    return {"tok": tok, "card": card, "bots": bots}


def _novo_job(amb, bot="A"):
    s, r = _req("POST", E["BT_ISO_API"] + "/mt5/enviar", {
        "bot_nome": "Pytest Veredito", "bot_token": amb["bots"][bot], "codigo": amb["card"]["codigo"],
        "ativo": "XAU/USD (Ouro)", "timeframe": "15m", "estrategia_id": "teste_integracao_mt5"}, tok=amb["tok"])
    j = json.loads(r); assert s == 200 and j["ok"], j
    c = _pg(); cur = c.cursor()   # cache do codigo volta a NAO aprovado (so no isolado)
    cur.execute("update mq5_cache set aprovado=false where gen_hash=(select gen_hash from mt5_jobs where job_id=%s)", (j["job_id"],))
    c.close()
    return j["job_id"]


def _foto(job_id):
    """Estado completo: a linha do job, a linha do cache e o hash de TODAS as
    linhas de mt5_jobs e mq5_cache (qualquer escrita em qualquer linha muda)."""
    c = _pg(); cur = c.cursor()
    cur.execute("select row_to_json(j)::text from mt5_jobs j where job_id=%s", (job_id,)); a = cur.fetchone()
    cur.execute("select row_to_json(m)::text from mq5_cache m where gen_hash=(select gen_hash from mt5_jobs where job_id=%s)", (job_id,)); b = cur.fetchone()
    cur.execute("select md5(string_agg(row_to_json(j)::text, '|' order by job_id)) from mt5_jobs j"); t1 = cur.fetchone()
    cur.execute("select md5(string_agg(row_to_json(m)::text, '|' order by gen_hash)) from mq5_cache m"); t2 = cur.fetchone()
    c.close(); return (a, b, t1, t2)


def _ver(corpo):
    return _req("POST", E["BT_ISO_API"] + "/mt5/veredito", corpo)


RECUSA = b'{"ok":false,"erro":"veredito_recusado","codigo":"BT-V01"}'


def test_recusas_uniformes_sem_alterar_nada(amb):
    jid = _novo_job(amb, "A")
    antes = _foto(jid)
    casos = {
        "token_ausente": {"job_id": jid, "aprovado": True, "log": "0 errors"},
        "token_vazio": {"bot_token": "   ", "job_id": jid, "aprovado": True},
        "token_errado": {"bot_token": secrets.token_hex(16), "job_id": jid, "aprovado": True},
        "token_de_outro_bot": {"bot_token": amb["bots"]["B"], "job_id": jid, "aprovado": True},
        "job_inexistente": {"bot_token": amb["bots"]["A"], "job_id": uuid.uuid4().hex[:16], "aprovado": True},
        "job_id_ausente": {"bot_token": amb["bots"]["A"], "aprovado": True},
        "reprovar_com_token_errado": {"bot_token": secrets.token_hex(16), "job_id": jid, "aprovado": False},
    }
    for nome, corpo in casos.items():
        s, b = _ver(corpo)
        assert (s, b) == (403, RECUSA), (nome, s, b)
        assert _foto(jid) == antes, nome


def test_bot_excluido_recusado_sem_alterar(amb):
    jid = _novo_job(amb, "X")
    c = _pg(); cur = c.cursor()
    cur.execute("update conector_bots set excluido=true where bot_token=%s", (amb["bots"]["X"],)); c.close()
    antes = _foto(jid)
    s, b = _ver({"bot_token": amb["bots"]["X"], "job_id": jid, "aprovado": True})
    assert (s, b) == (403, RECUSA) and _foto(jid) == antes


def test_aprovacao_legitima_depois_replay_e_troca_imutaveis(amb):
    jid = _novo_job(amb, "A")
    s, b = _ver({"bot_token": amb["bots"]["A"], "job_id": jid, "aprovado": True, "log": "0 errors, 0 warnings"})
    assert s == 200 and json.loads(b) == {"ok": True}
    a, cache, _, _ = _foto(jid)
    a, cache = json.loads(a[0]), json.loads(cache[0])
    assert a["status"] == "aprovado" and a["aprovado"] is True and a["log"] == "0 errors, 0 warnings"
    assert cache["aprovado"] is True
    final = _foto(jid)
    for corpo in ({"bot_token": amb["bots"]["A"], "job_id": jid, "aprovado": True, "log": "replay"},
                  {"bot_token": amb["bots"]["A"], "job_id": jid, "aprovado": False, "log": "virar reprovado"}):
        s, b = _ver(corpo)
        assert s == 409 and json.loads(b)["erro"] == "veredito_final_imutavel"
        assert _foto(jid) == final


def test_reprovado_final_nao_vira_aprovado_nem_marca_cache(amb):
    jid = _novo_job(amb, "A")
    s, b = _ver({"bot_token": amb["bots"]["A"], "job_id": jid, "aprovado": False, "log": "1 error"})
    assert s == 200
    final = _foto(jid)
    assert json.loads(final[1][0])["aprovado"] is False
    s, b = _ver({"bot_token": amb["bots"]["A"], "job_id": jid, "aprovado": True, "log": "forjado"})
    assert s == 409 and _foto(jid) == final


def test_corrida_oito_aprovacoes_um_vencedor(amb):
    jid = _novo_job(amb, "A")
    res, bar = [], threading.Barrier(8)
    def vai():
        bar.wait(); res.append(_ver({"bot_token": amb["bots"]["A"], "job_id": jid, "aprovado": True, "log": "0 errors"})[0])
    th = [threading.Thread(target=vai) for _ in range(8)]
    [t.start() for t in th]; [t.join() for t in th]
    assert sorted(res) == [200] + [409] * 7
