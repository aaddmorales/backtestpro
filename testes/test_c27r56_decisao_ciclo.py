"""C27R56 (ordem 17/10 18:21 Kyiv, item 7) — relatório padrão: por decisão de gestão, regras, nível estrutural, leitura,
alerta, confirmação, ação e horários. Registros reproduzem avaliações GRAVADAS na homolog (op 69 às 04:15Z de 16/10 = proteção
efetiva; op 70 às 13:15Z = corte; op 71 às 12:30Z = alerta + proteção por tempo). Só leitura: nenhuma regra muda."""
import os, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI); sys.path.insert(0, os.path.dirname(AQUI))
os.environ.setdefault("BT_CV_SEGREDO", "x")
import api


def _g(**k):
    base = {"barra_m15_utc": None, "leitura_assinada": {}, "corte_classificacao": {}, "comando": None, "regras": {"contrato_gestao": "gestao-5", "api": "8.27"}}
    base.update(k)
    return base


def test_protecao_efetiva_op69():
    g = _g(acao="mover_sl", motivo="proteção efetiva (gestao-4): stop no extremo da barra M15 de decisão 82022.94", estado="necessidade de proteção",
           sl_pedido="82022.94", dado_barra_m15_utc="2026-10-16T04:00:00Z", snapshot_recebido_utc="2026-10-16T04:15:41Z", avaliado_utc="2026-10-16T04:15:41Z",
           leitura_assinada={"corte_do_ciclo": 1, "stop_vigente": "82176.41", "stop_estrutural": "82176.088862", "B3": 1},
           corte_classificacao={"classe": "fino (2º sinal: pausa/pullback de barra)", "decidido_por_m15": ["fundo_barra_rompido"]},
           protecao_efetiva={"nivel": 82022.94},
           comando={"id": 153, "criado_utc": "2026-10-16T04:15:42Z", "entregue_utc": "2026-10-16T04:15:44Z", "confirmado_utc": "2026-10-16T04:15:52Z"})
    d = api._rel_decisao_do_ciclo(g, -1)
    assert d["acao"]["classe"] == "proteção" and d["nivel_estrutural"]["protecao_efetiva"] == 82022.94
    assert d["leitura"]["decidido_por_m15"] == ["fundo_barra_rompido"] and d["alerta"]["estado"] == "necessidade de proteção"
    assert d["horarios_utc"]["barra_fechou"].startswith("2026-10-16T04:15") and d["horarios_utc"]["execucao_confirmada"] == "2026-10-16T04:15:52Z"
    assert d["confirmacao"]["invalidacao_confirmada"] is False


def test_corte_op70_e_alerta_op71():
    corte = _g(acao="close", motivo="ciclo", estado="invalidação estrutural confirmada", dado_barra_m15_utc="2026-10-16T13:00:00Z",
               leitura_assinada={"corte_do_ciclo": 1}, corte_classificacao={"classe": "fino (2º sinal)", "decidido_por_m15": ["topo_barra_rompida"]})
    d = api._rel_decisao_do_ciclo(corte, 1)
    assert d["acao"]["classe"] == "corte" and d["confirmacao"]["invalidacao_confirmada"] is True
    alerta = _g(acao="mover_sl", estado="alerta de enfraquecimento", sl_pedido="81470.04", alertas_contrarios=["M5:sacudida_fundo", "M15:sacudida_fundo"],
                leitura_assinada={"stop_vigente": "81603.41"}, corte_classificacao={"caixa_m15": {"estado": "ativa", "topo": "81551.78", "fundo": "81272.49"}})
    d = api._rel_decisao_do_ciclo(alerta, -1)
    assert d["acao"]["classe"] == "proteção"                       # o stop andou a favor: a ação foi proteger; o estado registra o alerta
    assert d["alerta"]["alertas_contrarios"] == ["M5:sacudida_fundo", "M15:sacudida_fundo"] and d["nivel_estrutural"]["caixa_m15"]["estado"] == "ativa"
    manter = _g(acao="manter", estado="alerta de enfraquecimento", leitura_assinada={"corte_do_ciclo": 0})
    assert api._rel_decisao_do_ciclo(manter, 1)["acao"]["classe"] == "alerta"
    antigo = {"acao": "manter", "leitura_assinada": {}, "corte_classificacao": {}}            # registro da gestao-1: campos ausentes ficam None
    d = api._rel_decisao_do_ciclo(antigo, 1)
    assert d["acao"]["classe"] == "manter" and d["horarios_utc"]["barra_fechou"] is None and "anterior" in d["versao_das_regras"]["contrato_gestao"]
