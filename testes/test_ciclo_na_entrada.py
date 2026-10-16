"""C27R53 (ordem do dono 15/10 21:38 Kyiv) — sel-6 e lote-3 sobre as LEITURAS REAIS gravadas na homolog.

1. As 8 entradas de BTC do relatório (ops 54–64): as leituras do M15/M5/M1/M30 são as que o servidor tinha ANTES da decisão
   (selecao_avaliacoes da barra de decisão, gravadas ao vivo). Nada de candle posterior.
2. Reprodução cronológica das 205 avaliações de 14/10 16:45Z a 15/10 19:00Z (bots 13 e 14): os elegíveis gravados passam pelos
   portões novos (11 pela função real da API; 12 e 10 pelos graus/alertas gravados) e a ordem da sel-6 é refeita barra a barra.
3. lote-3 com os números reais da op 54 (lote-2 deu 1,01 e perdeu US$ 114,75 com teto de US$ 100).
Os resultados financeiros NÃO entram em nenhuma asserção: o que se testa é a regra do desenho."""
import json, os, sys
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI); sys.path.insert(0, os.path.dirname(AQUI))
import test_selecao as S

api = S.api

V = lambda d, reg, ev, loc="meio_da_faixa", est="mista", **k: dict(dir=d, regime=reg, eventos=ev, localizacao=loc, estrutura=est, **k)

# leituras gravadas na barra de decisão (selecao_avaliacoes.avaliacao.movimento_em_formacao.valores) — homolog hvraqquuvybzpqwkqlcu
ENTRADAS = {
    54: dict(card="card8_bollinger", tf="M15", lado=1, por_tf={
        "M15": V(-1, "lateral", ["sacudida_fundo", "rompimento_confirmado(por_barra)"], ultimo_topo=81871.89, ultimo_fundo=81524.72),
        "M5": V(0, "compressao", ["sacudida_topo", "compressao_armada"], est="descendente"),
        "M1": V(0, "compressao", ["compressao_armada"]), "M30": V(-1, "compressao", [], loc="fundo_da_faixa", est="descendente", momentum="estavel")}),
    55: dict(card="card4_canal_ema20", tf="M30", lado=-1, por_tf={
        "M15": V(-1, "lateral", ["rompimento_confirmado(por_barra)"], ultimo_topo=81830.6, ultimo_fundo=80075.91),
        "M5": V(-1, "compressao", ["compressao_armada", "quebra_estrutura_baixa"]),
        "M1": V(-1, "compressao", ["compressao_armada"], loc="no_suporte"), "M30": V(-1, "tendencia", [], est="descendente", momentum="enfraquecendo")}),
    57: dict(card="card7_rsi", tf="H1", lado=1, por_tf={
        "M15": V(1, "compressao", ["voltou_compressao"], loc="topo_da_faixa", est="ascendente", ultimo_topo=81830.6, ultimo_fundo=80620.16),
        "M5": V(1, "compressao", ["sacudida_topo", "compressao_armada"], loc="topo_da_faixa"),
        "M1": V(0, "compressao", ["sacudida_fundo", "compressao_armada"], loc="no_suporte"), "M30": V(0, "compressao", [], est="descendente", momentum="estavel")}),
    58: dict(card="card8_bollinger", tf="M30", lado=1, por_tf={
        "M15": V(-1, "lateral", ["rompimento_confirmado(por_barra)"], ultimo_topo=81641.44, ultimo_fundo=80620.16),
        "M5": V(0, "lateral", ["rompimento_confirmado(por_barra)"], est="descendente"),
        "M1": V(1, "tendencia", ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"], loc="topo_da_faixa"), "M30": V(-1, "tendencia", [], est="descendente", momentum="estavel")}),
    61: dict(card="card5_ema_9_21", tf="M15", lado=1, por_tf={
        "M15": V(0, "lateral", ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"], ultimo_topo=80972.63, ultimo_fundo=80629.33),
        "M5": V(0, "compressao", ["compressao_armada"], est="ascendente"),
        "M1": V(0, "compressao", ["voltou_compressao"]), "M30": V(0, "lateral", [], momentum="estavel")}),
    62: dict(card="card4_canal_ema20", tf="H1", lado=-1, por_tf={
        "M15": V(0, "compressao", ["compressao_armada"], ultimo_topo=81306.67, ultimo_fundo=81058.19, momentum="enfraquecendo"),
        "M5": V(0, "compressao", ["compressao_armada"]),
        "M1": V(-1, "lateral", ["rompimento_pendente(por_barra)", "quebra_estrutura_baixa"]), "M30": V(0, "compressao", [], momentum="enfraquecendo")}),
    63: dict(card="card4_canal_ema20", tf="M15", lado=-1, por_tf={
        "M15": V(-1, "compressao", ["compressao_armada"], est="descendente", ultimo_topo=81092.34, ultimo_fundo=80733.51),
        "M5": V(0, "compressao", ["voltou_compressao"], est="ascendente"),
        "M1": V(1, "lateral", ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"], loc="na_resistencia"), "M30": V(-1, "compressao", [], momentum="estavel")}),
    64: dict(card="card8_bollinger", tf="M15", lado=1, por_tf={
        "M15": V(1, "compressao", ["sacudida_topo", "voltou_compressao"], loc="na_resistencia", est="descendente", ultimo_topo=81087.61, ultimo_fundo=79660.43),
        "M5": V(1, "lateral", ["rompimento_confirmado(por_barra)"], loc="topo_da_faixa"),
        "M1": V(0, "compressao", ["compressao_armada"]), "M30": V(0, "compressao", [], momentum="estavel")}),
}
# regra do desenho (constituição do Bloco 1): 55 e 61 conformes; as demais não
ESPERADO = {54: (False, "§5.4/§5.5"), 55: (True, "§2.2"), 57: (False, "§5.1"), 58: (False, "§5.4/§5.5"),
            61: (True, "§2.2"), 62: (False, "§5.1"), 63: (False, "§5.1"), 64: (False, "§5.1")}


def _cand(e):
    return {"estrategia": {"card": e["card"]}, "lado_num": e["lado"], "timeframe": e["tf"]}


def test_1_as_8_entradas_btc_pela_regra_original_do_ciclo(api):
    for op, e in ENTRADAS.items():
        mov = api._sel_movimento_em_formacao(e["por_tf"])
        r = api._sel_ciclo_na_entrada(_cand(e), mov)
        ok, regra = ESPERADO[op]
        assert r["ok"] is ok and r["regra"].startswith(regra), (op, r)
        comp = api._sel_compatibilidade(_cand(e), mov)
        if op == 58:                                     # reversão contra a retomada vendedora: contrária (0) → portão 12 também veta
            assert comp["grau"] == 0
    # 61: a quebra de estrutura do M15 (fechamento acima do último topo 80972,63) é a confirmação do lado — canal do M15 = 0
    mov61 = api._sel_movimento_em_formacao(ENTRADAS[61]["por_tf"])
    assert mov61["ciclo_na_entrada"]["quebra_m15"] == 1 and mov61["ciclo_na_entrada"]["dir_m15"] == 0
    # 54: compra de reversão no fundo PROVISÓRIO (sacudida) com a caixa do M15 rompida para BAIXO: 3º sinal ausente
    r54 = api._sel_ciclo_na_entrada(_cand(ENTRADAS[54]), api._sel_movimento_em_formacao(ENTRADAS[54]["por_tf"]))
    assert "3º sinal" in r54["detalhe"]
    # sem leitura do M15: dado indisponível (não autoriza)
    assert api._sel_ciclo_na_entrada(_cand(ENTRADAS[55]), api._sel_movimento_em_formacao({}))["ok"] is None


def test_2_reproducao_cronologica_das_avaliacoes_gravadas(api):
    D = json.load(open(os.path.join(AQUI, "dados_c27r53_selecao_14_15out.json"), encoding="utf-8"))
    assert len(D) == 205
    mudou, mantidas, novas = [], [], []
    for r in D:
        mov = api._sel_movimento_em_formacao({"M15": {"dir": r["m15"]["d"], "regime": r["m15"]["reg"], "eventos": r["m15"]["ev"] or []}})
        eleg = []
        for c in r["c"]:
            if c["el"] != "elegivel":
                continue
            card, lado = c["uid"].split("|")[0], int(c["uid"].split("|")[-1])
            if api._sel_ciclo_na_entrada({"estrategia": {"card": card}, "lado_num": lado}, mov)["ok"] is not True:
                continue                                                         # portão 11
            if c["g"] is not None and int(c["g"]) < 1:
                continue                                                         # portão 12
            if (c["nal"] or 0) >= 2:
                continue                                                         # portão 10 sem isenção
            eleg.append(c)
        eleg.sort(key=lambda c: (-(c["g"] if c["g"] is not None else 1), -(c["pf"] or 0), -(c["pfm"] or 0), -(c["tr"] or 0)))
        novo = eleg[0]["uid"] if eleg else None
        if r["executada"]:
            (mantidas if novo == r["esc"] else mudou).append((r["bot"], r["b"]))
        if novo is not None and novo != r["esc"]:
            novas.append((r["bot"], r["b"], novo))
    # executadas mantidas: BTC 55 (03:30) e 61 (08:30); Gold 60 (bot 14). Bloqueadas: BTC 54, 57, 58, 62, 63, 64, 65; Gold 56
    # C27R55c (sel-7, C5): Gold 59 (bot 14, 06:45Z) passa a AGUARDAR — M15 com rompimento PENDENTE da caixa (§5.1/§5.2)
    assert (13, "2026-10-15T03:30") in mantidas and (13, "2026-10-15T08:30") in mantidas
    assert sorted(b for b in mudou) == sorted([(13, "2026-10-14T23:00"), (14, "2026-10-15T04:15"), (13, "2026-10-15T05:00"), (13, "2026-10-15T06:30"),
                                              (13, "2026-10-15T10:00"), (13, "2026-10-15T12:15"), (13, "2026-10-15T14:30"), (13, "2026-10-15T17:00"),
                                              (14, "2026-10-15T06:45")])
    assert novas == []                                       # os portões novos não promovem nenhum outro candidato: só deixam de abrir


def test_3_lote_3_na_op_54(api):
    esp = {"simbolo": "BTCUSD", "tick_tamanho": 0.01, "tick_valor": 0.01, "volume_min": 0.01, "volume_passo": 0.01, "volume_max": 10, "ponto": 0.01,
           "contrato": 1, "modo_de_negociacao": 4, "tick_idade_s": 5, "distancia_minima_stop_pts": 0, "margem_1_lote": {"compra": 163.13, "venda": 163.13}}
    ses = {"id": "t", "config": {"risco_pct_patrimonio": 0.1, "risco_max_por_operacao_usd": 100}}
    bot = {"simbolo": "BTCUSD", "equity": 610698.16, "margem_livre": 610696.89}
    cand = {"lado": 1, "preco_ref": "81540.540000", "stop": "81458.546107"}
    pl, m = api._ses_plano(ses, bot, {"especificacao": esp}, cand, {"preco": "81557.36", "spr": "0", "pt": "0.01"})
    assert m is None and pl["versao"] == "lote-3"
    adm = pl["distancias"]["pior_entrada_admitida_ao_stop"]
    assert adm["limite_pts"] == 3000.0 and adm["pior_entrada"] == 81570.54            # ref + max(3000 pts, 10% de 8199 pts)
    assert pl["lote"] == 0.89 and pl["risco_planejado_usd"] <= 100.0                   # lote-2 dava 1,01 (distância 98,81 até a estimativa)
    # preenchimento REAL 81569,87 (dentro do admitido) e saída REAL 81456,26 (2,29 abaixo do stop): o residual é só o da saída
    perda = round((81569.87 - 81456.26) * pl["lote"], 2)
    assert perda == 101.11 and round((81458.546107 - 81456.26) * pl["lote"], 2) == 2.03
    assert any(c["controle"] == "pior entrada admitida (lote-3)" and "deslizamento do stop" in c["risco_residual"] for c in pl["controles"])
