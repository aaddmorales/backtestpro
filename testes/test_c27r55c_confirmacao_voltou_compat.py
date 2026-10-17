"""C27R55c (ordem do dono 16/10 21:29 Kyiv) — C5 entrada (Lei de Confirmação da caixa), C6 saída (voltou pra compressão), C7 compatibilidade
das reversões estruturais. Objetivo: cumprir o desenho existente, sem ampliar entradas nem antecipar saídas.

Dados: avaliações GRAVADAS ao vivo na homolog (selecao_avaliacoes: estrutura por TF da barra, portões 1–9 de cada candidato, escolha) —
testes/dados_c27r55/avaliacoes_c27r55c.json — e candles REAIS do BTCUSD 14→16/10 (coleta ao vivo) cortados no instante avaliado.
Nenhum dado posterior à barra. Resultado financeiro não entra em asserção de regra."""
import ast, json, os, shutil, sys
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI); sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "motor_ciclos"))
DADOS = os.path.join(AQUI, "dados_c27r55")
os.environ.setdefault("BT_CV_SEGREDO", "x")


@pytest.fixture(scope="module")
def api():
    import api as _a
    return _a


@pytest.fixture(scope="module")
def AV():
    av = json.load(open(os.path.join(DADOS, "avaliacoes_c27r55c.json"), encoding="utf-8"))
    return {(e["sim"], e["b"][:16]): e for e in av}


def _c(card, lado, nivel=None):
    return {"estrategia": {"card": card}, "lado_num": lado, "sinal": {"nivel": nivel}}


def _elegib(api, cand, mov):
    """Mesma ordem da seleção: portões 1–9 GRAVADOS na barra (o 5 é informativo desde a sel-5), 10/11/12 recalculados."""
    g = cand.get("g") or {}
    c = _c(cand["card"], int(cand["lado"]), cand.get("nivel"))
    comp = api._sel_compatibilidade(c, mov)
    g11 = api._sel_ciclo_na_entrada(c, mov)
    if not all(g.get(k) is True for k in ("1", "2", "3", "4", "6", "7", "8", "9")):
        return "fora_1a9", comp, g11
    if len(comp.get("alertas_de_estrutura") or []) >= 2:
        return "vetada_10", comp, g11
    if g11["ok"] is not True:
        return ("aguardando" if g11.get("aguardar") else "vetada_11"), comp, g11
    return ("elegivel" if comp["grau"] >= 1 else "vetada_12"), comp, g11


def test_1_contratos(api):
    assert api.SEL_VERSAO == "sel-7" and api.GESTAO_CONTRATO == "gestao-5" and api.API_VERSAO.startswith(("8.27", "8.28"))
    assert api.SEL_CONTRATO["id"] == "sel-7" and "mudou_em_relacao_a_sel_6" in api.SEL_CONTRATO
    assert "voltou_compressao" in api._REL_SAIDAS


# ------------------------------------------------------------------ C5 entrada ------------------------------------------------------------------
def test_2_c5_op69_aguarda_a_confirmacao_da_caixa(api, AV):
    """16/10 03:45Z (06:45 Kyiv): o Donchian confirmou o card (fechamento 81.780,09 < mínima de 20 = 81.879,43), mas a CAIXA do M15
    [81.879,43; 82.112,71] estava só com rompimento PENDENTE. Pela §5.1/§5.2 a entrada aguarda a próxima M15."""
    e = AV[("BTCUSD", "2026-10-16T03:45")]
    mov = api._sel_movimento_em_formacao(e["est"])
    assert mov["ciclo_na_entrada"]["rompimento_m15_pendente"] is True
    don = [c for c in e["c"] if c["uid"] == e["esc"]][0]
    assert don["card"] == "card10_donchian20" and don["el"] == "elegivel"           # o que a sel-6 gravou ao vivo
    st, comp, g11 = _elegib(api, don, mov)
    assert st == "aguardando" and g11["aguardar"] is True and g11["ok"] is False
    assert "Lei de Confirmação" in g11["detalhe"] and "81879.43" in g11["detalhe"] and "outra régua" in g11["detalhe"]
    # nenhum candidato da barra fica elegível: a barra termina SEM escolha (aguardando)
    assert all(_elegib(api, c, mov)[0] != "elegivel" for c in e["c"])


def test_3_c5_barra_seguinte_voltou_recusa(api, AV):
    """04:00Z: a M15 fechou DE VOLTA dentro da caixa (82.005,45) — voltou_compressao: o mesmo sinal é recusado (não entra atrasado)."""
    e = AV[("BTCUSD", "2026-10-16T04:00")]
    mov = api._sel_movimento_em_formacao(e["est"])
    assert "voltou_compressao" in e["est"]["M15"]["eventos"]
    g11 = api._sel_ciclo_na_entrada(_c("card10_donchian20", -1, 81879.43), mov)
    assert g11["ok"] is False and not g11.get("aguardar") and g11["regra"].startswith("§5.1")


@pytest.mark.parametrize("barra,uid", [
    ("2026-10-15T03:30", "card4_canal_ema20|M30|2026-10-15 06:00:00|-1"),     # op 55
    ("2026-10-15T08:30", "card5_ema_9_21|M15|2026-10-15 11:00:00|1"),        # op 61
    ("2026-10-16T12:00", "card9_macd|H1|2026-10-16 14:00:00|1"),             # op 70
])
def test_4_c5_entradas_que_continuam(api, AV, barra, uid):
    """Rompimento da caixa já CONFIRMADO (ou sem caixa) e M15 confirmando o lado: a correção não muda nada — continua elegível e escolhida."""
    e = AV[("BTCUSD", barra)]
    mov = api._sel_movimento_em_formacao(e["est"])
    assert not mov["ciclo_na_entrada"]["rompimento_m15_pendente"]
    c = [c for c in e["c"] if c["uid"] == uid][0]
    assert c["el"] == "elegivel" and e["esc"] == uid
    st, comp, g11 = _elegib(api, c, mov)
    assert st == "elegivel" and g11["ok"] is True


def test_5_c5_avaliacao_antiga_sem_campo_usa_os_eventos(api):
    mov = {"ciclo_na_entrada": {"dir_m15": -1, "quebra_m15": -1, "caixa_m15_ativa": False, "eventos_m15": ["rompimento_pendente(por_barra)"]}}
    assert api._sel_ciclo_na_entrada(_c("card4_canal_ema20", -1), mov).get("aguardar") is True
    mov["ciclo_na_entrada"]["eventos_m15"] = ["rompimento_confirmado(por_barra)"]
    assert api._sel_ciclo_na_entrada(_c("card4_canal_ema20", -1), mov)["ok"] is True
    mov["ciclo_na_entrada"].update(caixa_m15_ativa=True, eventos_m15=["voltou_compressao"])
    r = api._sel_ciclo_na_entrada(_c("card4_canal_ema20", -1), mov)
    assert r["ok"] is False and not r.get("aguardar")


# ------------------------------------------------------------------ C7 compatibilidade ------------------------------------------------------------
def test_6_c7_reversao_estrutural_no_sentido_da_quebra(api, AV):
    """XAU 13/10 13:15Z (16:15 Kyiv): fase 'quebra confirmada' para baixo. A sel-6 zerava TODA reversão; a regra autorizada (§5.5 3º sinal,
    item 10) só autoriza a reversão ESTRUTURAL no mesmo sentido da quebra: card 1 venda passa de 0 para 2 e vira a escolha."""
    e = AV[("XAUUSD", "2026-10-13T13:15")]
    mov = api._sel_movimento_em_formacao(e["est"])
    assert mov["fase"].startswith("quebra confirmada") and mov["ciclo_na_entrada"]["quebra_m15"] == -1
    c1 = [c for c in e["c"] if c["card"] == "card1_reversao_extremo" and int(c["lado"]) == -1][0]
    st, comp, g11 = _elegib(api, c1, mov)
    assert comp["grau"] == 2 and "reversão estrutural no sentido da quebra" in comp["rotulo"] and st == "elegivel"
    # correspondência exigida: direção (= quebra), estrutura (fase quebra confirmada), família (reversão), regra autorizada (card no conjunto)
    assert api._sel_compatibilidade(_c("card1_reversao_extremo", 1), mov)["grau"] == 0              # contra a quebra
    assert api._sel_compatibilidade(_c("card13_topo_fundo_duplo", -1), mov)["grau"] == 2
    for card in ("card7_rsi", "card8_bollinger"):                                                   # reversão de indicador: segue 0
        assert api._sel_compatibilidade(_c(card, -1), mov)["grau"] == 0
    mov2 = dict(mov, fase="compressão")
    assert api._sel_compatibilidade(_c("card1_reversao_extremo", -1), mov2)["grau"] == 0          # sem quebra confirmada: segue 0


def test_7_c7_nao_torna_toda_reversao_elegivel(api, AV):
    """BTC 16/10 03:00Z: as cinco vendas recusadas continuam recusadas na sel-7 (portões 8/10/11/12 — nenhuma vira elegível)."""
    e = AV[("BTCUSD", "2026-10-16T03:00")]
    mov = api._sel_movimento_em_formacao(e["est"])
    st = {c["uid"]: _elegib(api, c, mov)[0] for c in e["c"]}
    assert st and all(v != "elegivel" for v in st.values()), st


# ------------------------------------------------------------------ C6 saída --------------------------------------------------------------------
def _ptf_op69():
    return {"M1": {"dir": 1, "estrutura": "ascendente", "ultimo_topo": 82060.0, "ultimo_fundo": 81950.0, "eventos": ["compressao_armada"]},
            "M5": {"dir": 0, "estrutura": "mista", "ultimo_topo": 82112.71, "ultimo_fundo": 81780.0, "eventos": ["compressao_armada"]},
            "M15": {"dir": -1, "estrutura": "descendente", "ultimo_topo": 82600.0, "ultimo_fundo": 81830.73, "eventos": ["sacudida_fundo", "voltou_compressao"]},
            "M30": {"dir": -1, "estrutura": "descendente", "ultimo_topo": 82600.0, "ultimo_fundo": 81830.73, "eventos": ["compressao_armada"]}}


CX_69 = {"contrato": "caixa-m15-1", "barra": "2026-10-16 06:45:00", "estado": "voltou_compressao", "estado_anterior": "rompida_pendente",
         "mesma_caixa_da_barra_anterior": 1, "lado_do_rompimento": -1, "topo": "82112.71", "fundo": "81879.43",
         "barra_do_rompimento": "2026-10-16 06:30:00", "fechamento": "82005.45", "voltou_agora": 1}


def test_8_c6_voltou_do_lado_da_posicao_fecha_mesmo_com_continuidade(api):
    L = {"corte_do_ciclo": 0, "B3": 0}
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 82005.45, "caixa_m15": CX_69}, None, _ptf_op69(), 1, [])
    assert acao == "close" and motivo == "voltou_compressao" and cls["estado"] == "invalidação estrutural confirmada"
    assert "§5.3" in exp and "não neutraliza" in exp and cls["voltou_compressao"] is True


def test_9_c6_nao_fecha_por_pullback_alerta_ou_lado_oposto(api):
    L = {"corte_do_ciclo": 0, "B3": 0}
    # a mesma caixa rompida CONTRA a posição (compra) que volta: não invalida a compra
    acao, motivo, *_ = api._gestao2_decidir(1, L, {"B5": 0, "fechamento": 82005.45, "caixa_m15": CX_69}, None, _ptf_op69(), 1, [])
    assert motivo != "voltou_compressao"
    # rompimento ainda pendente/confirmado (pullback dentro do rompimento, sacudida): sem disparo
    for est in ("rompida_pendente", "rompida_confirmada", "ativa"):
        cx = dict(CX_69, estado=est, voltou_agora=0)
        acao, motivo, *_ = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 81950.0, "caixa_m15": cx}, None, _ptf_op69(), 1, [])
        assert motivo != "voltou_compressao", est
    # sem bloco assinado (leitor < 1.10 / conector < hml17): regra não aplicada e isso fica escrito
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 82005.45}, None, _ptf_op69(), 1, [])
    assert motivo != "voltou_compressao" and "não assinada" in cls["caixa_m15"]
    # alerta isolado continua alerta (não fecha)
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 82005.45, "caixa_m15": dict(CX_69, voltou_agora=0, estado="ativa")},
                                                       None, _ptf_op69(), 1, [])
    assert acao is None or acao == "proteger"
    # B5 continua primeiro
    assert api._gestao2_decidir(-1, L, {"B5": 1, "caixa_m15": CX_69}, None, _ptf_op69(), 1, [])[1] == "B5"


def test_10_c6_retorno_em_barra_sem_gestao_e_detectado_depois(api):
    L = {"corte_do_ciclo": 0, "B3": 0}
    cx_depois = dict(CX_69, barra="2026-10-16 07:00:00", estado_anterior="voltou_compressao", voltou_agora=0)
    ant = [{"acao": None, "corte_classificacao": {"caixa_m15": dict(CX_69, barra="2026-10-16 06:30:00", estado="rompida_pendente", voltou_agora=0)}}]
    acao, motivo, cont, cls, exp = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 82010.0, "caixa_m15": cx_depois}, None, _ptf_op69(), 2, ant)
    assert acao == "close" and motivo == "voltou_compressao" and "atraso" in exp
    # sem registro anterior da MESMA caixa rompida (posição aberta depois do retorno): não fecha
    acao, motivo, *_ = api._gestao2_decidir(-1, L, {"B5": 0, "fechamento": 82010.0, "caixa_m15": cx_depois}, None, _ptf_op69(), 2, [])
    assert motivo != "voltou_compressao"


# ------------------------------------------------------------------ leitor 1.10 + conector hml17 -------------------------------------------------
def test_11_leitor_caixa_m15_nos_candles_reais():
    import test_niveis_reacoes as T
    import bt_motor_leitura_hml as L
    assert L.LEITOR_VERSAO == "1.10-hml"
    esperado = {"2026-10-16 06:45": ("rompida_pendente", False, -1),         # barra 06:30 (corretora) fechou fora: pendente
                "2026-10-16 07:00": ("voltou_compressao", True, -1),         # barra 06:45 fechou 82.005,45 dentro: voltou
                "2026-10-16 07:15": ("voltou_compressao", False, -1),        # continua dentro: não 'agora'
                "2026-10-15 07:45": ("voltou_compressao", True, -1)}         # op 55: caixa [81.337,28; 81.774,31]
    for t, (est, agora, lado) in esperado.items():
        d = T._espelho_ate(t)
        try:
            cx = L._caixa_m15(d, "BTCUSD")
        finally:
            shutil.rmtree(d, ignore_errors=True)
        assert cx["contrato"] == "caixa-m15-1" and cx["estado"] == est and cx["voltou_agora"] is agora and cx["lado_do_rompimento"] == lado, (t, cx)
        if t == "2026-10-16 07:00":
            assert cx["topo"] == 82112.71 and cx["fundo"] == 81879.43 and cx["barra_do_rompimento"] == "2026-10-16 06:30:00"


def test_12_conector_assina_a_caixa_m15():
    fonte = open(os.path.join(RAIZ, "conector_homolog", "hml", "conector_nucleo_homolog.py"), encoding="utf-8").read()
    arv = ast.parse(fonte)
    assert 'APP_VERSAO = "v1.39-hml17"' in fonte
    fn = [n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name == "_cv_assinar_candidatos"][0]
    txt = ast.get_source_segment(fonte, fn)
    for q in ("caixa_m15", "voltou_agora", "lado_do_rompimento", "estado_anterior", "barra_do_rompimento"):
        assert q in txt, q
    assert 'not ges["caixa_m15"].get("erro")' in txt                         # bloco com erro não viaja
