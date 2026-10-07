"""C27R23 — AUTORIDADE r01v5 (candidato assinado) e seleção sel-3 com confirmação em tempo real.
Contra o AMBIENTE ISOLADO LOCAL. O atestado de candidatos é montado e assinado pela MESMA função do
conector (conector_nucleo_homolog._cv_assinar_candidatos); os candidatos são sintéticos (formato cand-3).
A chave de emissão (autoridade_contratos.r01v5) só é ligada DENTRO do teste de emissão e desligada ao fim.
Nada aqui é evidência da plataforma."""
import copy, hashlib, json, os, sys, time, uuid
from datetime import datetime, timedelta, timezone
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI); sys.path.insert(0, RAIZ)
import test_ciclos_lm as T
import test_selecao as S

amb = T.amb
api = S.api
URL = T.E["BT_ISO_API"]
OFF = S.OFF
def _funcoes_da_ponte():
    """As funções REAIS de assinatura da ponte do conector (conector_homolog/ponte_motor_hml8.py), extraídas
    do arquivo-fonte e executadas isoladas — sem importar o conector inteiro (que instala guardas globais)."""
    import ast, types
    fonte = open(os.path.join(RAIZ, "conector_homolog", "ponte_motor_hml8.py"), encoding="utf-8").read()
    arv = ast.parse(fonte)
    nos = [n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name in ("_cv_utc", "_cv_assinar_candidatos")]
    assert len(nos) == 2
    ns = types.SimpleNamespace()
    d = {}
    exec(compile(ast.Module(body=nos, type_ignores=[]), "ponte_motor_hml8.py", "exec"), d)
    ns._cv_assinar_candidatos = d["_cv_assinar_candidatos"]
    return ns


N = _funcoes_da_ponte()
ALTA_CONTRA_VENDA = {"M1": -1, "M5": -1, "M15": -1, "M30": -1, "H1": -1, "H4": 1, "D1": 1}


def _bot(amb):
    s, r, _ = T._req("POST", URL + "/conector/registrar", {"nome": "r05-" + uuid.uuid4().hex[:8], "simbolo": "XAUUSD"}, tok=amb["sess"])
    assert s == 200, r
    return {"tok": r["bot_token"], "id": T._pg("select id from conector_bots where bot_token=%s", r["bot_token"])[0][0]}


def _cor(dt):
    return (dt + timedelta(seconds=OFF)).strftime("%Y-%m-%d %H:%M:%S")


def _rt(card, tf, lado, conf, preco=4100.0, stop=4110.0, modo="fechamento", corte=False, seg_tf=None):
    """Candidato CONFIRMADO em tempo real (formato do leitor 1.5). `conf` = instante da confirmação (UTC)."""
    seg_tf = seg_tf or {"M15": 900, "M30": 1800, "H1": 3600}[tf]
    sinal = conf - timedelta(seconds=seg_tf)
    return {"card": card, "nome": card, "tf": tf, "validade_m15": 4 * seg_tf // 900, "lado": lado,
            "uid": f"{card}|{tf}|{_cor(sinal)}|{lado}", "ts_sinal": _cor(sinal), "ts_sinal_fecha": _cor(conf), "modo": modo,
            "nivel": None, "corte_ciclo_contra_agora": corte, "estado": "confirmado",
            "confirmacao": {"contrato": "conf-rt-1", "base": "barra do sinal fechou; Ciclo sem corte e sem blindagem"},
            "ts_confirmacao": _cor(conf), "ts_entrada_m15": _cor(conf), "ts_vence": _cor(conf + timedelta(seconds=1800)),
            "idade_s": 0, "idade_m15": 0, "preco_ref": preco, "preco_ref_base": "fechamento da última M15 antes da confirmação",
            "entrada": preco, "stop": stop, "stop_base": "pivô e ATR14 do M15 na última barra fechada antes da confirmação",
            "risco_pts": abs(preco - stop) / 0.01, "estudo_retro": None}


def _det(b, itens, dirs, veredito, barra=None, preco="4099.80", assinar_cand=True, corte_slot=False, agora=None):
    """Snapshot completo: EA + atestado r01v4 + telemetria do motor com candidatos + atestado r01v5 (ponte real)."""
    import bt_cv_atestado as cvat
    barra = barra or T._barra_m15(agora)
    at = cvat.assinar({"bot_token_hash": hashlib.sha256(b["tok"].encode()).hexdigest(), "versao_motor": "teste-r05",
                       "simbolo": "XAUUSD", "magic": T._magic(b["tok"]), "ts_barra_m15": barra.isoformat(),
                       "cv1": {"janela": {k: dirs[k] for k in ("M1", "M5", "M15")}, "veredito": veredito, "motivo": "item1_referencia_contra(D1)" if veredito == "bloqueada" else "teste"},
                       "cv2": {"dirs": {"D1": dirs["D1"], "H4": dirs["H4"]}}}, segredo=T.SEGREDO)
    cand = {"versao": "cand-3", "ativo": "XAUUSD", "leitor": "1.5-hml", "codigo": {"cards": "2.0", "bloco2": "1.7", "bloco1": "3.2.B"},
            "barra_m15_corretora": _cor(barra - timedelta(seconds=900)), "agora_corretora": _cor(barra), "territorio_h4_h1_m30": 0,
            "tfs": {tf: {"barra_corretora": _cor(barra - timedelta(seconds=900))} for tf in ("M15", "M30", "H1")},
            "confirmacao": {"contrato": "conf-rt-1", "validade_s": 1800,
                            "slot_agora": {"corte_contra_compra": False, "corte_contra_venda": corte_slot, "B1": False, "B5": False}},
            "itens": itens}
    por_tf = {k: {"dir": v, "ultimo_topo": 4130.0, "ultimo_fundo": 4070.0} for k, v in dirs.items()}
    extra = {"cv_atestado": at, "preco": preco, "spr": "12", "pt": "0.01",
             "cv_motor": {"estado": "ok", "motivo": "teste", "off_ea_s": OFF, "por_tf": por_tf, "leitura": {"fase": {"fase": 3}}, "candidatos": cand}}
    if assinar_cand:
        os.environ["BT_CV_SEGREDO"] = T.SEGREDO
        extra["cv_atestado_cand"] = N._cv_assinar_candidatos(at, cand, {"por_tf": por_tf}, OFF)
    return T._det(b["tok"], agora=agora, extra=extra), barra, at


def _sel(b, barra):
    r = T._pg("select avaliacao from selecao_avaliacoes where bot_id=%s and barra_m15=%s", b["id"], barra)
    return r[0][0] if r else None


def _contagens(b):
    return (T._pg("select count(*) from ciclo_decisoes where bot_id=%s", b["id"])[0][0],
            T._pg("select count(*) from mt5_comandos where bot_id=%s", b["id"])[0][0])


def _chave(ligar):
    T._pg("update autoridade_contratos set emissao_habilitada=%s where contrato='r01v5'", bool(ligar))


def test_1_sombra_d1_contra_e_contexto_e_a_r01v4_continua_vetando(amb):
    """Venda em M30 com D1 e H4 em alta. Seleção: elegível e escolhida. r01v5 (sombra): SERIA emitida, com
    D1/H4 gravados como contexto. r01v4 (em vigor): veta a barra. Nada é emitido: zero decisão, zero comando."""
    assert T._pg("select emissao_habilitada from autoridade_contratos where contrato='r01v5'")[0][0] is False
    b = _bot(amb)
    barra = T._barra_m15()
    it = _rt("card2_rompimento_caixa", "M30", -1, barra)
    det, barra, at4 = _det(b, [it], ALTA_CONTRA_VENDA, "bloqueada")
    assert T._snap(b["tok"], det)[0] == 200
    av = _sel(b, barra)
    assert av and av["versao"] == "sel-3" and av["contratos"]["confirmacao_em_tempo_real"] is True
    c = av["grupos"]["M30"]["candidatos"][0]
    assert c["elegibilidade"] == "elegivel" and av["escolha"]["uid"] == it["uid"]
    assert c["frescor"]["situacao"] == "válida" and c["frescor"]["contrato_da_confirmacao"] == "conf-rt-1"
    assert c["frescor"]["confirmado_utc"] == barra.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert c["frescor"]["vence_utc"] == (barra + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert c["contexto_superior"]["D1"] == "sentidos opostos"
    assert c["estudo"]["comparabilidade"]["selo_valida_o_contrato_ao_vivo"] is False
    assert any(d["item"] == "stop" for d in c["estudo"]["comparabilidade"]["diferencas"])
    s5 = av["autoridade_r01v5"]
    assert s5["seria_emitida"] is True and s5["emissao_habilitada"] is False and s5["decisao_emitida"] is False and s5["comando_criado"] is False
    assert "desligado" in s5["execucao_real"]
    r = s5["avaliacao"]
    assert [x["condicao"][:2] for x in r["condicoes"]] == ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10", "11", "12"]
    assert all(x["ok"] is True for x in r["condicoes"])
    assert not any("D1" in x["condicao"] or "H4" in x["condicao"] or "veredito" in x["condicao"] for x in r["condicoes"])
    k = r["contexto"]
    assert (k["D1"], k["H4"], k["D1_frente_ao_candidato"], k["veredito_do_motor_congelado"]) == ("alta", "alta", "sentidos opostos", "bloqueada")
    assert "referência histórica" in k["veredito_do_motor_papel"] and "não é condição" in k["papel"]
    assert r["candidato"]["stop"] == "4110.000000" and r["candidato"]["card"] == "card2_rompimento_caixa" and r["candidato"]["tf"] == "M30"
    # a autoridade EM VIGOR vetou a mesma barra por D1; e nada foi criado
    assert T._pg("select decisao, regra from ciclo_leituras where bot_id=%s and barra_m15=%s", b["id"], barra)[0] == ("bloquear", "R-CICLO-01.cv1_bloqueada")
    assert _contagens(b) == (0, 0)
    tr = T._pg("select estado, motivo from ciclo_trilha where bot_id=%s and etapa='autoridade_r01v5'", b["id"])
    assert len(tr) == 1 and tr[0][0] == "ok" and tr[0][1].startswith("SOMBRA · r01v5 SERIA emitida")
    # as assinaturas não vão para a avaliação gravada
    bruto = json.dumps(av)
    assert at4["assinatura"] not in bruto and det["cv_atestado_cand"]["assinatura"] not in bruto and b["tok"] not in bruto


def test_2_nao_e_bloqueada_virando_autorizada(api, amb):
    """O veredito do motor não decide na r01v5 — nem para vetar, nem para liberar. Com o motor dizendo
    'autorizada' e D1/H4 a favor, um candidato NÃO assinado, com corte do Ciclo ou fora da validade não passa."""
    b = _bot(amb); sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    favor = {"M1": 1, "M5": 1, "M15": 1, "M30": 1, "H1": 1, "H4": 1, "D1": 1}
    barra = T._barra_m15()
    it = _rt("card2_rompimento_caixa", "M15", 1, barra, preco=4100.0, stop=4090.0)
    agora = barra + timedelta(seconds=30)
    # (a) candidato só na telemetria, sem atestado de candidatos
    det, _, _ = _det(b, [it], favor, "autorizada", preco="4100.20", assinar_cand=False)
    r = api._r05_avaliar(sb, bot, it["uid"], det=det, escolha_uid=it["uid"], agora=agora)
    assert r["seria_emitida"] is False and r["primeiro_impedimento"].startswith("1. atestado r01v5 verificado — atestado_de_candidatos_ausente")
    # (b) atestado assinado, mas o uid pedido não está nele
    det, _, _ = _det(b, [it], favor, "autorizada", preco="4100.20")
    r = api._r05_avaliar(sb, bot, it["uid"].replace("card2_rompimento_caixa", "card10_donchian20"), det=det, escolha_uid="x", agora=agora)
    assert r["seria_emitida"] is False and r["primeiro_impedimento"].startswith("2. candidato presente no atestado")
    # (c) assinado com corte do Ciclo contra o lado
    det, _, _ = _det(b, [dict(it, corte_ciclo_contra_agora=True)], favor, "autorizada", preco="4100.20")
    r = api._r05_avaliar(sb, bot, it["uid"], det=det, escolha_uid=it["uid"], agora=agora)
    assert r["seria_emitida"] is False and r["primeiro_impedimento"].startswith("5. Ciclo sem corte")
    # (d) válido às +29 min, vencido às +31 min (a barra do atestado ainda dentro dos 900 s não salva)
    velho = barra - timedelta(minutes=30)
    it2 = _rt("card2_rompimento_caixa", "M15", 1, velho, preco=4100.0, stop=4090.0)
    det, _, _ = _det(b, [it2], favor, "autorizada", preco="4100.20")
    r = api._r05_avaliar(sb, bot, it2["uid"], det=det, escolha_uid=it2["uid"], agora=barra + timedelta(seconds=60))
    assert r["seria_emitida"] is False and r["primeiro_impedimento"].startswith("4. dentro da validade") and "VENCIDA" in r["primeiro_impedimento"]
    # (e) tudo certo, mas a seleção escolheu outro candidato
    det, _, _ = _det(b, [it], favor, "autorizada", preco="4100.20")
    r = api._r05_avaliar(sb, bot, it["uid"], det=det, escolha_uid="outro|M15|x|1", agora=agora)
    assert [x["condicao"][:3] for x in r["condicoes"] if x["ok"] is not True] == ["12."]
    # (f) e passa quando é o escolhido — com o motor dizendo 'neutra' também (o veredito não entra)
    for ver in ("autorizada", "neutra", "bloqueada"):
        det, _, _ = _det(b, [it], favor, ver, preco="4100.20")
        assert api._r05_avaliar(sb, bot, it["uid"], det=det, escolha_uid=it["uid"], agora=agora)["seria_emitida"] is True, ver


def test_3_assinatura_vinculo_e_forma(api, amb):
    b, outro = _bot(amb), _bot(amb); sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    barra = T._barra_m15(); agora = barra + timedelta(seconds=20)
    it = _rt("card2_rompimento_caixa", "M30", -1, barra)
    det, _, _ = _det(b, [it], ALTA_CONTRA_VENDA, "bloqueada")
    def falha(d, ag=agora):
        return api._r05_ler_atestado(sb, bot, det=d, agora=ag)[2]
    assert falha(det) is None
    for campo, valor in (("stop", "4090.000000"), ("lado", 1), ("vence_utc", "2099-01-01T00:00:00Z"), ("tf", "H1")):
        d = copy.deepcopy(det); d["cv_atestado_cand"]["candidatos"][0][campo] = valor          # adulterado depois de assinado
        assert falha(d) == "atestado_assinatura_invalida", campo
    d = copy.deepcopy(det); d["cv_atestado_cand"]["contrato"] = "r01v4"
    assert falha(d) == "atestado_assinatura_invalida"
    # atestado legítimo de OUTRO bot
    det_o, _, _ = _det(outro, [it], ALTA_CONTRA_VENDA, "bloqueada")
    d = copy.deepcopy(det); d["cv_atestado_cand"] = det_o["cv_atestado_cand"]
    assert falha(d) == "atestado_de_outro_bot(fail_closed)"
    # o atestado r01v4 NÃO serve como atestado de candidatos (assinatura válida, contrato errado)
    d = copy.deepcopy(det); d["cv_atestado_cand"] = d["cv_atestado"]
    assert falha(d) == "atestado_de_outro_contrato"
    # barra do atestado vencida (mais de 900 s) e barra futura
    assert falha(det, barra + timedelta(seconds=901)).startswith("leitura_vencida")
    assert falha(det, barra - timedelta(seconds=1)) == "barra_em_formacao_ou_futura"
    # forma: uid que não corresponde ao card/timeframe/lado assinados
    import bt_cv_atestado as cvat
    corpo = {k: v for k, v in det["cv_atestado_cand"].items() if k != "assinatura"}
    corpo["candidatos"] = [dict(corpo["candidatos"][0], uid="card10_donchian20|M30|x|-1")]
    d = copy.deepcopy(det); d["cv_atestado_cand"] = cvat.assinar(corpo, segredo=T.SEGREDO)
    assert falha(d) == "atestado_candidato_uid_incoerente"
    # números viajam como texto: a assinatura sobrevive à ida e volta pelo jsonb do banco
    assert T._snap(b["tok"], det)[0] == 200
    volta = T._pg("select detalhe_json->'cv_atestado_cand' from conector_snapshots where bot_token=%s order by id desc limit 1", b["tok"])[0][0]
    assert cvat.verificar(volta, segredo=T.SEGREDO) == (True, None) and isinstance(volta["candidatos"][0]["stop"], str)


def test_4_emissao_consumo_unico_e_comando_so_com_as_tres_travas(api, amb):
    """Bancada: chave r01v5 LIGADA só aqui + bot em automático. Decisão com o candidato assinado, consumo
    único pela RPC, comando com o stop assinado, repetição recusada. Sem a chave: nada."""
    b = _bot(amb); sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    barra = T._barra_m15()
    it = _rt("card2_rompimento_caixa", "M30", -1, barra)
    det, barra, _ = _det(b, [it], ALTA_CONTRA_VENDA, "bloqueada")
    assert T._snap(b["tok"], det)[0] == 200                       # ingestão pela API: seleção + sombra
    assert _sel(b, barra)["autoridade_r01v5"]["seria_emitida"] is True and _contagens(b) == (0, 0)
    # chave DESLIGADA: emissão recusada e a RPC recusa mesmo com uma decisão plantada no banco
    assert api._r05_emitir_decisao(sb, bot, it["uid"]) == (False, "contrato_r01v5_desligado(so_sombra)")
    duid = api._r05_uid_decisao(b["id"], it["uid"])
    T._pg("insert into ciclo_decisoes (id, bot_id, simbolo, lado, uid, ts_barra, veredito, status, expira_em) values "
          "('plantada-'||%s, %s, 'XAUUSD', -1, %s, %s, %s::jsonb, 'emitida', now() + interval '10 min')",
          str(b["id"]), b["id"], duid, barra,
          json.dumps({"contrato": "r01v5", "candidato": {"uid": it["uid"], "card": it["card"], "tf": "M30", "lado": -1, "modo": "fechamento",
                      "sinal_abre_utc": "2026-01-01T00:00:00Z", "sinal_fecha_utc": "2026-01-01T00:30:00Z", "confirmado_utc": "2026-01-01T00:30:00Z",
                      "vence_utc": (barra + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), "preco_ref": "4100.000000", "stop": "4110.000000",
                      "corte_do_ciclo_agora": 0, "dir_do_timeframe": -1}}))
    assert api._r05_abrir_via_rpc(sb, bot, "plantada-" + str(b["id"]), 0.01) == (False, "contrato_r01v5_desligado(so_sombra)")
    assert _contagens(b) == (1, 0)
    T._pg("delete from ciclo_decisoes where bot_id=%s", b["id"])
    try:
        _chave(True)
        # ligada, mas bot em OBSERVAR: a escolha não é executada
        s5 = api._r05_executar_escolha(sb, bot, api._r05_sombra(sb, bot, det, _sel(b, barra), int(time.time())))
        assert s5["emissao_habilitada"] is True and s5["modo_do_bot"] == "observar" and s5["decisao_emitida"] is False and _contagens(b) == (0, 0)
        # ligada + automático: decisão e comando
        api._bot_config_set(b["id"], {"modo_operacional": "automatico"})
        s5 = api._r05_executar_escolha(sb, bot, api._r05_sombra(sb, bot, det, _sel(b, barra), int(time.time())))
        assert s5["decisao_emitida"] is True and s5["comando_criado"] is True, s5
        d = T._pg("select uid, lado, status, veredito, expira_em, ts_barra from ciclo_decisoes where bot_id=%s", b["id"])
        assert len(d) == 1 and d[0][0] == duid and d[0][1] == -1 and d[0][2] == "consumida"
        v = d[0][3]
        assert v["contrato"] == "r01v5" and v["candidato"]["uid"] == it["uid"] and v["candidato"]["stop"] == "4110.000000"
        assert v["contexto"]["D1_frente_ao_candidato"] == "sentidos opostos" and v["contexto"]["veredito_do_motor_congelado"] == "bloqueada"
        assert len(v["condicoes"]) == 12 and all(c["ok"] is True for c in v["condicoes"])
        assert d[0][4] == d[0][5] + timedelta(seconds=900)                                 # expira com a barra (antes do vencimento do candidato)
        c = T._pg("select tipo, status, origem, params from mt5_comandos where bot_id=%s", b["id"])
        assert len(c) == 1 and c[0][:3] == ("sell", "pendente", "selecao_r01v5")
        p = c[0][3]
        assert p["sl"] == 4110.0 and p["uid"] == duid and p["decisao"]["veredito"]["contrato"] == "r01v5"
        assert p["candidato"]["card"] == "card2_rompimento_caixa" and p["candidato"]["tf"] == "M30" and "tp" not in p
        amb['r05_params'] = p
        # REPETIÇÃO: o mesmo candidato não gera outra decisão; a mesma decisão não é consumida de novo
        ok, m = api._r05_emitir_decisao(sb, bot, it["uid"])
        assert ok is False and m.startswith("11. candidato e barra ainda sem decisão")
        did = T._pg("select id from ciclo_decisoes where bot_id=%s", b["id"])[0][0]
        assert api._r05_abrir_via_rpc(sb, bot, did, 0.01)[1] == "decisao_invalida_vencida_ou_ja_consumida"
        # as duas RPCs não se cruzam: a r01 (v4) recusa decisão v5
        r4 = sb.rpc("r01_claim_e_comando", {"p_decisao_id": did, "p_bot_id": b["id"], "p_bot_token": b["tok"],
                                             "p_user_id": bot["user_id"], "p_tipo": "sell", "p_params": {}, "p_origem": "teste"}).execute().data[0]
        assert r4["ok"] is False
        # posse: a decisão de um bot não abre comando em outro
        o = _bot(amb); bot_o = sb.table("conector_bots").select("*").eq("id", o["id"]).execute().data[0]
        assert api._r05_abrir_via_rpc(sb, bot_o, did, 0.01) == (False, "decisao_de_outro_bot")
        assert _contagens(b) == (1, 1)
    finally:
        _chave(False)
        api._bot_config_set(b["id"], {"modo_operacional": "observar"})
    assert T._pg("select emissao_habilitada from autoridade_contratos where contrato='r01v5'")[0][0] is False


def test_5_validade_vencida_e_entrada_perdida_sem_reaproveitar(api, amb):
    """30 min a contar da confirmação. Passou disso: 'vencida' se houve avaliação dentro do prazo,
    'entrada perdida' se a confirmação só foi vista depois. Em nenhum caso o sinal volta a ser elegível."""
    b = _bot(amb); sb = api._sb_admin()
    bot = sb.table("conector_bots").select("*").eq("id", b["id"]).execute().data[0]
    barra = T._barra_m15()
    conf = barra - timedelta(minutes=45)                                           # confirmado há 45 min: fora da validade
    it = _rt("card2_rompimento_caixa", "M30", -1, conf)
    det, barra, _ = _det(b, [dict(it, idade_s=2700, idade_m15=3)], ALTA_CONTRA_VENDA, "bloqueada")
    assert T._snap(b["tok"], det)[0] == 200                       # o atestado é verificado sobre o último snapshot do bot
    gravada = _sel(b, barra)                                      # e a ingestão já gravou a mesma conclusão
    assert gravada["grupos"]["M30"]["candidatos"][0]["frescor"]["situacao"] == "entrada perdida" and gravada["escolha"] is None
    assert gravada["autoridade_r01v5"]["seria_emitida"] is False and "não escolheu" in gravada["autoridade_r01v5"]["motivo"]
    leit, ciclos = api._clm_avaliar(sb, bot, det, int(time.time()))
    av = api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time()))
    assert av["integridade"]["ok"] is True, av["integridade"]
    c = av["grupos"]["M30"]["candidatos"][0]
    assert c["elegibilidade"] == "vetada" and c["primeiro_impedimento"].startswith("3. frescor do sinal — ENTRADA PERDIDA")
    assert c["frescor"]["situacao"] == "entrada perdida" and c["frescor"]["avaliada_dentro_da_validade"] is False
    assert [m["categoria"] for m in c["motivos"] if m["efeito"] == "bloqueia"] == ["entrada perdida"]
    assert av["escolha"] is None and av["resumo"]["entradas_perdidas"] == 1
    # com uma avaliação gravada dentro da validade (barra que fechou 30 min atrás): 'vencida', não 'perdida'
    T._pg("insert into selecao_avaliacoes (bot_id, simbolo, barra_m15, versao, avaliacao) values (%s,'XAUUSD',%s,'sel-3','{}'::jsonb)",
          b["id"], barra - timedelta(minutes=30))
    av = api._sel_avaliar(sb, bot, det, leit, ciclos, int(time.time()))
    c = av["grupos"]["M30"]["candidatos"][0]
    assert c["frescor"]["situacao"] == "vencida" and c["frescor"]["avaliada_dentro_da_validade"] is True
    assert c["elegibilidade"] == "vetada" and [m["categoria"] for m in c["motivos"] if m["efeito"] == "bloqueia"] == ["sinal vencido"]
    # na borda: aos 30 min exatos ainda vale; um segundo depois não
    it3 = _rt("card2_rompimento_caixa", "M30", -1, barra - timedelta(minutes=30))
    det3, _, _ = _det(b, [it3], ALTA_CONTRA_VENDA, "bloqueada")
    t0 = int(barra.timestamp())
    assert api._sel_avaliar(sb, bot, det3, leit, ciclos, t0)["grupos"]["M30"]["candidatos"][0]["frescor"]["situacao"] == "válida"
    assert api._sel_avaliar(sb, bot, det3, leit, ciclos, t0 + 1)["grupos"]["M30"]["candidatos"][0]["frescor"]["situacao"] != "válida"
    # a autoridade também recusa o vencido, mesmo que alguém o apresente como escolhido
    r = api._r05_avaliar(sb, bot, it["uid"], det=det, escolha_uid=it["uid"], agora=barra + timedelta(seconds=5))
    assert r["seria_emitida"] is False and "VENCIDA" in r["primeiro_impedimento"]
