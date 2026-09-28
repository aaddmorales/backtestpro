"""T1-T8 — RPC r01_claim_e_comando + migracoes 0002/0003 em POSTGRES REAL isolado.
Sem skip por construcao: ambiente ausente = FALHA (nunca SKIP).
Exige BT_PG_ISOLADO_URL e BT_PG_CONFIRMO_ISOLADO=1; o banco precisa ter
public._bt_homolog_marker (sentinela do isolado)."""
import os, json, secrets, threading, uuid
from datetime import datetime, timedelta, timezone
import psycopg2, pytest

URL = os.environ.get("BT_PG_ISOLADO_URL", "")


@pytest.fixture(scope="module")
def dsn():
    assert URL, "BT_PG_ISOLADO_URL ausente (FALHA, nao skip)"
    assert os.environ.get("BT_PG_CONFIRMO_ISOLADO") == "1", "confirmacao de isolamento ausente"
    c = psycopg2.connect(URL); cur = c.cursor()
    cur.execute("select to_regclass('public._bt_homolog_marker') is not null")
    assert cur.fetchone()[0], "sentinela _bt_homolog_marker ausente: NAO e o isolado"
    c.close()
    return URL


def _con(dsn, role="service_role"):
    c = psycopg2.connect(dsn); c.autocommit = True
    cur = c.cursor(); cur.execute(f"set role {role}")
    return c


@pytest.fixture
def bot(dsn):
    c = psycopg2.connect(dsn); c.autocommit = True; cur = c.cursor()
    uid = str(uuid.uuid4())
    cur.execute("insert into auth.users(id, email, aud, role) values (%s,%s,'authenticated','authenticated')",
                (uid, f"t{uid[:8]}@example.com"))
    tok = secrets.token_hex(16)
    cur.execute("insert into conector_bots(user_id, bot_token, nome, simbolo) values (%s,%s,'T','XAUUSD') returning id",
                (uid, tok))
    bid = cur.fetchone()[0]
    c.close()
    return {"id": bid, "token": tok, "user": uid, "simbolo": "XAUUSD"}


_SEQ = [0]
def _decisao(dsn, bot, lado=1, contrato="r01v4", cv1="autorizada", expira=900):
    _SEQ[0] += 1
    ts = datetime(2026, 9, 28, tzinfo=timezone.utc) + timedelta(minutes=15 * _SEQ[0])
    did = secrets.token_hex(16)
    ver = {"contrato": contrato, "cv1_veredito": cv1, "topdown": ["autorizada", "favor"]}
    c = psycopg2.connect(dsn); c.autocommit = True; cur = c.cursor()
    cur.execute("""insert into ciclo_decisoes(id,bot_id,simbolo,lado,uid,ts_barra,veredito,expira_em)
                   values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (did, bot["id"], bot["simbolo"], lado, f"{bot['id']}-{_SEQ[0]}-{'B' if lado==1 else 'S'}",
                 ts, json.dumps(ver), datetime.now(timezone.utc) + timedelta(seconds=expira)))
    c.close()
    return did


def _rpc(dsn, bot, did, tipo="buy", token=None, user=None, role="service_role"):
    c = _con(dsn, role); cur = c.cursor()
    cur.execute("select * from r01_claim_e_comando(%s,%s,%s,%s,%s,%s,%s)",
                (did, bot["id"], token or bot["token"], user or bot["user"], tipo,
                 json.dumps({"volume": 0.01}), "teste"))
    r = cur.fetchone(); c.close(); return r


def _status(dsn, did):
    c = psycopg2.connect(dsn); cur = c.cursor()
    cur.execute("select status from ciclo_decisoes where id=%s", (did,)); s = cur.fetchone()[0]; c.close(); return s


def _n_cmd(dsn, bot):
    c = psycopg2.connect(dsn); cur = c.cursor()
    cur.execute("select count(*) from mt5_comandos where bot_id=%s and tipo in ('buy','sell')", (bot["id"],))
    n = cur.fetchone()[0]; c.close(); return n


def test_T1_claim_e_comando_na_mesma_transacao(dsn, bot):
    did = _decisao(dsn, bot)
    ok, motivo, cmd = _rpc(dsn, bot, did)
    assert ok and cmd and motivo == "ok"
    assert _status(dsn, did) == "consumida" and _n_cmd(dsn, bot) == 1
    c = psycopg2.connect(dsn); cur = c.cursor()
    cur.execute("select params->>'uid', d.uid from mt5_comandos m join ciclo_decisoes d on d.id=%s where m.id=%s", (did, cmd))
    a, b = cur.fetchone(); c.close()
    assert a == b  # uid do comando = uid do servidor


def test_T2_replay_recusado(dsn, bot):
    did = _decisao(dsn, bot)
    assert _rpc(dsn, bot, did)[0]
    ok, motivo, cmd = _rpc(dsn, bot, did)
    assert not ok and motivo.startswith("decisao_nao_emitida") and cmd is None
    assert _n_cmd(dsn, bot) == 1


def test_T3_vinculo_conferido_no_banco(dsn, bot):
    did = _decisao(dsn, bot)
    assert _rpc(dsn, bot, did, token="0" * 32) [1] == "vinculo_bot_invalido"
    assert _rpc(dsn, bot, did, user=str(uuid.uuid4()))[1] == "vinculo_bot_invalido"
    assert _rpc(dsn, bot, did, tipo="sell")[1] == "decisao_lado_incoerente"
    c = psycopg2.connect(dsn); c.autocommit = True; cur = c.cursor()
    cur.execute("update conector_bots set simbolo='BTCUSD' where id=%s", (bot["id"],)); c.close()
    assert _rpc(dsn, bot, did)[1] == "decisao_de_outro_simbolo"
    assert _status(dsn, did) == "emitida" and _n_cmd(dsn, bot) == 0


def test_T4_vencida_recusada(dsn, bot):
    did = _decisao(dsn, bot, expira=-5)
    ok, motivo, _ = _rpc(dsn, bot, did)
    assert not ok and motivo == "decisao_vencida"
    assert _status(dsn, did) == "emitida" and _n_cmd(dsn, bot) == 0


def test_T5_unique_violation_desfaz_o_claim(dsn, bot):
    did = _decisao(dsn, bot)
    c = psycopg2.connect(dsn); c.autocommit = True; cur = c.cursor()
    cur.execute("select uid from ciclo_decisoes where id=%s", (did,)); u = cur.fetchone()[0]
    cur.execute("insert into mt5_comandos(bot_id,tipo,params) values (%s,'buy',%s)", (bot["id"], json.dumps({"uid": u})))
    c.close()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _rpc(dsn, bot, did)
    assert _status(dsn, did) == "emitida"   # claim desfeito pela transacao
    assert _n_cmd(dsn, bot) == 1            # so o pre-existente


def test_T6_concorrencia_um_vencedor(dsn, bot):
    did = _decisao(dsn, bot)
    res, barreira = [], threading.Barrier(8)
    def corre():
        c = _con(dsn); cur = c.cursor(); barreira.wait()
        try:
            cur.execute("select ok from r01_claim_e_comando(%s,%s,%s,%s,'buy','{}'::jsonb,'t6')",
                        (did, bot["id"], bot["token"], bot["user"]))
            res.append(cur.fetchone()[0])
        except Exception as e:
            res.append(repr(e))
        c.close()
    th = [threading.Thread(target=corre) for _ in range(8)]
    [t.start() for t in th]; [t.join() for t in th]
    assert res.count(True) == 1 and len(res) == 8
    assert _n_cmd(dsn, bot) == 1


def test_T7_contrato_e_veto_cv1(dsn, bot):
    d1 = _decisao(dsn, bot, contrato="r01v3")
    d2 = _decisao(dsn, bot, cv1="bloqueada")
    d3 = _decisao(dsn, bot, cv1="neutra")
    for d in (d1, d2, d3):
        ok, motivo, _ = _rpc(dsn, bot, d)
        assert not ok and motivo == "decisao_contrato_invalido"
        assert _status(dsn, d) == "emitida"
    assert _rpc(dsn, bot, _decisao(dsn, bot), tipo="close")[1] == "tipo_nao_e_abertura"
    assert _n_cmd(dsn, bot) == 0


def test_T8_grants_e_rls(dsn, bot):
    did = _decisao(dsn, bot)
    for role in ("anon", "authenticated"):
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            _rpc(dsn, bot, did, role=role)
        c = _con(dsn, role); cur = c.cursor()
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("select count(*) from ciclo_decisoes")
        c.close()
    c = psycopg2.connect(dsn); cur = c.cursor()
    cur.execute("select relrowsecurity, relforcerowsecurity from pg_class where oid='public.ciclo_decisoes'::regclass")
    assert cur.fetchone() == (True, True)
    cur.execute("select indexdef from pg_indexes where indexname='ux_mt5_comandos_abertura_uid'")
    assert "WHERE (tipo = ANY" in cur.fetchone()[0]
    c.close()
    assert _status(dsn, did) == "emitida"
