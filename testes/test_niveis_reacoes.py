"""C27R55 (ordem do dono 16/10 06:17 Kyiv) — o sistema reconhece suporte/resistência, relaciona aos cards e explica por que entrou ou aguardou?

Dados REAIS do BTCUSD de 14→16/10 (candles da coleta ao vivo, sem lacuna na janela; horário da corretora = UTC+3) e a avaliação gravada
na homolog entre 15/10 20:15Z e 16/10 03:30Z (RPC rel_niveis_reacoes). Nada de barra futura: o espelho é cortado no instante avaliado.

  1. leitor 1.9 — níveis do motor por andar: reproduz as localizações GRAVADAS ao vivo às 03:00Z e 03:15Z e mostra o nível por trás de cada uma;
     o suporte 81.830,73 (M15 de 20:45Z = 23:45 Kyiv de 15/10) é o pivô 'suporte' do M15/M30 e o 'último fundo' do H1.
  2. leitor 1.9 — evidência de cada card × TF (executado, barras, valores comparados) prova o 'sem sinal' de compra no toque.
  3. API — 'sem sinal' com e sem evidência; nível no texto do portão 10; níveis compactos na avaliação.
  4. API — relatório 'niveis_e_reacoes': classe de cada barra (03:00Z = sinal confirmado recusado pelos portões; 20:30Z = executado)."""
import json, os, shutil, sys, tempfile
import pandas as pd
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI); sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "motor_ciclos"))
DADOS = os.path.join(AQUI, "dados_c27r55")
PER = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "Daily": 1440}


def _espelho_ate(lim_corretora):
    """Cópia do espelho só com as barras FECHADAS até o instante (horário da corretora)."""
    d = tempfile.mkdtemp(prefix="c27r55_")
    lim = pd.Timestamp(lim_corretora)
    for nome in os.listdir(DADOS):
        if not nome.endswith(".csv"):
            continue
        tf = nome.split("_")[1]
        x = pd.read_csv(os.path.join(DADOS, nome), sep="\t", dtype=str)
        ts = pd.to_datetime(x["<DATE>"] + " " + x["<TIME>"], format="%Y.%m.%d %H:%M:%S")
        x[ts + pd.Timedelta(minutes=PER[tf]) <= lim].to_csv(os.path.join(d, nome), sep="\t", index=False)
    return d


def _api():
    os.environ.setdefault("BT_CV_SEGREDO", "x")
    import api as _a
    return _a


@pytest.fixture(scope="module")
def L():
    import bt_motor_leitura_hml as L_
    return L_


def test_1_niveis_reproduzem_o_gravado_e_mostram_o_suporte(L):
    # gravado ao vivo (selecao_avaliacoes.continuidade.estrutura_por_tf, bot 13)
    gravado = {"2026-10-16 06:00": {"M1": "no_suporte", "M5": "no_suporte", "M15": "fundo_da_faixa", "M30": "fundo_da_faixa", "H1": "meio_da_faixa"},
               "2026-10-16 06:15": {"M1": "topo_da_faixa", "M5": "na_resistencia", "M15": "meio_da_faixa", "M30": "fundo_da_faixa", "H1": "meio_da_faixa"}}
    for instante, esperado in gravado.items():
        d = _espelho_ate(instante)
        try:
            n = L._niveis_por_tf(d, "BTCUSD")["por_tf"]
        finally:
            shutil.rmtree(d, ignore_errors=True)
        for tf, loc in esperado.items():
            assert n[tf]["localizacao"] == loc, (instante, tf, n[tf]["regra_da_localizacao"])
            for k in ("ultimo_topo", "ultimo_fundo", "resistencia", "suporte"):
                if n[tf][k]:
                    assert n[tf][k]["confere_com_o_motor"] is True
        if instante.endswith("06:00"):
            # o toque de 05:45 Kyiv: M1/M5 'no_suporte' pelos pivôs DELES (81.936,85 / 81.947,07), dentro de 0,3×ATR
            assert n["M5"]["suporte"]["preco"] == 81947.07 and n["M5"]["suporte"]["dentro_da_banda"]
            # o suporte do gráfico: pivô de 23:45 (corretora) = 'suporte' do M15 e 'último fundo' do H1, registrado ANTES da aproximação
            assert n["M15"]["suporte"]["preco"] == 81830.73 and n["M15"]["suporte"]["barra_do_pivo"] == "2026-10-15 23:45:00"
            assert n["H1"]["ultimo_fundo"]["preco"] == 81830.73 and n["H1"]["ultimo_fundo"]["dentro_da_banda"] is True
            # e mesmo assim o H1 diz 'meio_da_faixa': a localização do motor compara com o pivô ANTERIOR (79.660,43) — divergência documentada
            assert n["H1"]["suporte"]["preco"] == 79660.43 and n["H1"]["localizacao"] == "meio_da_faixa"


def test_2_evidencia_dos_cards_prova_o_sem_sinal_de_compra(L):
    d = _espelho_ate("2026-10-16 06:15")
    try:
        c = L._candidatos(d, "BTCUSD")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ev = c["avaliacao_por_card"]["por_card"]
    assert c["versao"] == "cand-6" and c["leitor"] == "1.10-hml"
    assert len(ev) == 13 and all(set(x) == {"M15", "M30", "H1"} for x in ev.values())
    assert all(v.get("executado") is True and not v.get("erro_da_evidencia") for x in ev.values() for v in x.values())
    m15 = {k: v["M15"] for k, v in ev.items()}
    # Bollinger: o fechamento de 05:45 (81.931,60) NÃO ficou fora da banda inferior (81.886,79) — só o pavio tocou: sem sinal de reversão
    bb = m15["card8_bollinger"]["valores"]
    assert bb["fechamento_anterior"] > bb["banda_inferior_anterior"] and not m15["card8_bollinger"]["sinal_na_ultima_barra"]
    # RSI longe de 30
    assert m15["card7_rsi"]["valores"]["rsi14"] > 30 and m15["card7_rsi"]["valores"]["rsi14_anterior"] > 30
    # topo/fundo duplo: os dois fundos CONSECUTIVOS do mapa são 81.830,73 e 82.039,97 (não o 81.879,43) — fora da tolerância
    td = m15["card13_topo_fundo_duplo"]["valores"]
    assert td["fundo_anterior"]["preco"] == 81830.73 and td["fundos_no_mesmo_nivel"] is False
    # o que existe de compra é a segunda entrada pós-sacudida, armada no extremo da barra de 06:00 e aguardando continuidade
    cmp_ = [i for i in c["itens"] if i["card"] == "card3_segunda_entrada" and i["lado"] == 1]
    assert cmp_ and cmp_[0]["estado"] == "aguardando" and cmp_[0]["nivel"] == 82089.37
    assert "fundo" in m15["card3_segunda_entrada"]["valores"]["ultima_sacudida"]["detalhe"]


def test_3_api_sem_sinal_nivel_no_portao_10_e_niveis_compactos():
    api = _api()
    r, v, m = api._sel_sem_sinal_evidencia(None)
    assert "não exporta" in v and "não é prova" in m
    r, v, m = api._sel_sem_sinal_evidencia({"executado": True, "barras": 488, "aquecimento_minimo": 15, "dados_suficientes": True,
                                            "sinal_na_ultima_barra": False, "ultimo_sinal": {"barra": "x", "lado": 1, "barras_atras": 54},
                                            "valores": {"rsi14": 48.49}})
    assert "executado no PC sobre 488" in r and m.startswith("recusa: critério não atendido") and v["valores"]["rsi14"] == 48.49
    r, v, m = api._sel_sem_sinal_evidencia({"executado": False, "motivo": "sem série do H1 no espelho"})
    assert r.startswith("NÃO avaliado") and m.startswith("dado indisponível")
    r, v, m = api._sel_sem_sinal_evidencia({"executado": True, "barras": 10, "aquecimento_minimo": 50, "dados_suficientes": False})
    assert m.startswith("dado insuficiente")
    cand = {"niveis_por_tf": {"contrato": "niveis-1", "definicao": "d", "por_tf": {
        "M5": {"barra": "2026-10-16 05:55:00", "fechamento": 81931.6, "atr14": 102.3, "banda_0_3_atr": 30.69,
               "suporte": {"preco": 81947.07, "barra_do_pivo": "2026-10-16 05:05:00", "distancia_atr": -0.151, "dentro_da_banda": True, "confere_com_o_motor": True},
               "localizacao": "no_suporte", "regra_da_localizacao": "|fechamento − suporte| = 15.47 < 0,3×ATR = 30.69"},
        "D1": {"erro": "andar ausente no espelho"}}}}
    nv = api._sel_niveis_compacto(cand)
    assert nv["por_tf"]["M5"]["suporte"]["preco"] == 81947.07 and nv["por_tf"]["D1"]["erro"]
    t = api._sel_nivel_txt(nv, "M5", "no_suporte")
    assert "81947.07" in t and "05:05" in t and "-0.151 ATR" in t
    assert api._sel_nivel_txt(nv, "M5", "meio_da_faixa") is None and api._sel_nivel_txt(None, "M5", "no_suporte") is None
    assert api._sel_niveis_compacto({}) is None


def test_4_relatorio_classifica_cada_barra_pelo_estagio_alcancado():
    api = _api()
    rows = json.load(open(os.path.join(DADOS, "rpc_rel_niveis_reacoes_btc_1520_1603.json"), encoding="utf-8"))
    velas = []
    x = pd.read_csv(os.path.join(DADOS, "BTCUSD_M15_202610.csv"), sep="\t")
    for _, b in x.iterrows():
        t = pd.Timestamp(b["<DATE>"] + " " + b["<TIME>"]) - pd.Timedelta(hours=3)
        velas.append({"abertura_utc": t.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "o": b["<OPEN>"], "h": b["<HIGH>"], "l": b["<LOW>"], "c": b["<CLOSE>"], "carimbo": "ea"})

    class Q:
        def __init__(s, d): s.d = d
        def __getattr__(s, k): return lambda *a, **kw: s
        def execute(s): return type("R", (), {"data": s.d})()

    class SB:
        def rpc(s, n, p): return Q(rows)
        def table(s, n): return Q(velas)

    abs_ = [{"bot_id": 13, "candidato_uid": "card4_canal_ema20|M15|2026-10-15 23:15:00|1", "id": 66, "ticket": 2012915548, "estado": "fechada"}]
    tz, _ = api._rel_tz("Europe/Kiev")
    out = api._rel_niveis_reacoes(SB(), [{"id": 13, "simbolo": "BTCUSD"}], abs_, "2026-10-15T20:15:00+00:00", "2026-10-16T03:30:00+00:00", tz)["BTCUSD"]
    por = {b["barra_m15_fechou_utc"][:16]: b for b in out["por_barra"]}
    b0300 = por["2026-10-16T03:00"]
    assert b0300["classe"] == "sinal confirmado recusado pelos portões"
    assert any("teste de suporte" in p_ for p_ in b0300["padrao_detectado"])            # M1/M5 no_suporte
    assert any("quebra de estrutura para baixo" in p_ for p_ in b0300["padrao_detectado"])
    assert b0300["candle_m15"]["l"] == 81879.43                                        # a barra que tocou a região (05:45–06:00 Kyiv)
    assert all(c_["elegibilidade"] != "elegivel" for c_ in b0300["estrategias_candidatas"])
    assert por["2026-10-15T20:30"]["classe"] == "comando emitido e execução confirmada"
    assert sum(out["contagem_por_classe"].values()) == len(rows)
    assert por["2026-10-16T03:15"]["classe"] == "sinal confirmado recusado pelos portões"
    assert any("sacudida" in p_ for p_ in por["2026-10-16T03:15"]["padrao_detectado"])
