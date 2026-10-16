"""C27R54 (ordem do dono 15/10 22:48 Kyiv) — gestao-4 (D1), janela 10→15 (D3), EA 7.82 / bloqueio do Gold (item 5).

D1: as decisões gravadas na homolog para as ops 55, 61, 64 (BTC) e 60 (Gold) são reavaliadas com OS MESMOS dados de cada instante
    (leitura do corte, origem assinada, estrutura por tempo gravada na continuidade, candles M15 do snapshot). Nada de dado posterior.
D3: a função do leitor 1.8 que lê a janela 10→15 roda minuto a minuto sobre os candles M1/M5/M15 reais do BTC de 15/10, só com barras
    fechadas até o instante; a API só aceita a leitura assinada, fresca, do bot/símbolo/magic.
Resultados financeiros não entram em asserção de regra."""
import ast, hashlib, json, os, sys
from datetime import datetime, timezone, timedelta
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI); sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "motor_ciclos"))
import test_selecao as S

api = S.api


def _ptf(lista):
    return {x["tf"]: {k: x.get(k) for k in ("dir", "estrutura", "ultimo_topo", "ultimo_fundo", "eventos")} for x in lista}


# decisões gravadas (sessao_aberturas.gestao, homolog): leitura do corte + estrutura por tempo da continuidade naquele instante
CASOS = {
    "55@04:00": dict(lado=-1, fech=80809.07, B3=1, barras=2, origem=["M1:fundo_barra_rompido M1:rompeu_ultimo_topo M1:alerta_empilhado_3 M5:alerta_empilhado_3 -> M15:alerta_empilhado_3"],
                     ptf=[{"tf": "M1", "dir": 0, "eventos": ["compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 80917.32, "ultimo_fundo": 80784.58},
                          {"tf": "M5", "dir": -1, "eventos": ["compressao_armada"], "estrutura": "descendente", "ultimo_topo": 80954.59, "ultimo_fundo": 80620.16},
                          {"tf": "M15", "dir": -1, "eventos": ["rompimento_confirmado(por_barra)"], "estrutura": "mista", "ultimo_topo": 81830.6, "ultimo_fundo": 80075.91},
                          {"tf": "M30", "dir": -1, "eventos": ["rompimento_confirmado(por_barra)"], "estrutura": "descendente", "ultimo_topo": 81830.6, "ultimo_fundo": 80075.91}],
                     antes="manter(protegido) + trailing 81940 (gestao-3: degrau 2 sem direção)"),
    "61@09:15": dict(lado=1, fech=81164.58, B3=1, barras=2, origem=["M1:topo_barra_rompida -> M15:alerta_empilhado_3"],
                     ptf=[{"tf": "M1", "dir": -1, "eventos": ["voltou_compressao"], "estrutura": "mista", "ultimo_topo": 81243.52, "ultimo_fundo": 81105.39},
                          {"tf": "M5", "dir": 0, "eventos": ["compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 81306.67, "ultimo_fundo": 81058.19},
                          {"tf": "M15", "dir": 0, "eventos": ["compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 81475.7, "ultimo_fundo": 81058.19},
                          {"tf": "M30", "dir": 0, "eventos": ["compressao_armada"], "estrutura": "mista", "ultimo_topo": 81475.7, "ultimo_fundo": 80369.4}],
                     antes="mover_sl (proteger) — fechou 1 barra depois pelo B3"),
    "64@15:30": dict(lado=1, fech=82295.43, B3=0, barras=4, origem=["M1:topo_barra_rompida M5:alerta_empilhado_3 -> M15:exaustao_identificada"],
                     ptf=[{"tf": "M1", "dir": 0, "eventos": ["sacudida_fundo", "compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 82544.72, "ultimo_fundo": 82276.8},
                          {"tf": "M5", "dir": 1, "eventos": ["sacudida_topo", "compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 82310.28, "ultimo_fundo": 80888.3},
                          {"tf": "M15", "dir": 1, "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"], "estrutura": "descendente", "ultimo_topo": 81087.61, "ultimo_fundo": 79660.43},
                          {"tf": "M30", "dir": 1, "eventos": ["rompimento_confirmado(por_barra)", "quebra_estrutura_alta"], "estrutura": "descendente", "ultimo_topo": 81475.7, "ultimo_fundo": 79660.43}],
                     antes="manter(protegido) (gestao-3: exaustão = alerta)"),
    "Gold60@09:30": dict(lado=1, fech=4158.17, B3=0, barras=7, origem=["M1:topo_barra_rompida -> M15:alerta_empilhado_3"],
                         ptf=[{"tf": "M1", "dir": 0, "eventos": ["compressao_armada"], "estrutura": "mista", "ultimo_topo": 4160.61, "ultimo_fundo": 4157.25},
                              {"tf": "M5", "dir": 1, "eventos": ["sacudida_topo", "compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 4158.91, "ultimo_fundo": 4148.52},
                              {"tf": "M15", "dir": 1, "eventos": ["sacudida_topo", "voltou_compressao"], "estrutura": "ascendente", "ultimo_topo": 4158.91, "ultimo_fundo": 4148.52},
                              {"tf": "M30", "dir": 1, "eventos": ["rompimento_confirmado(por_barra)"], "estrutura": "mista", "ultimo_topo": 4161.78, "ultimo_fundo": 4131.17}],
                         antes="manter(protegido) (gestao-3: degrau 2 sem direção)"),
}
GOLD_0845 = dict(lado=1, fech=4151.53, B3=0, barras=4, origem=["M1:topo_barra_rompida M1:rompeu_ultimo_fundo M5:topo_barra_rompida -> M15:topo_barra_rompida"],
                 ptf=[{"tf": "M1", "dir": -1, "eventos": ["compressao_armada", "quebra_estrutura_baixa"], "estrutura": "mista", "ultimo_topo": 4154.83, "ultimo_fundo": 4151.87},
                      {"tf": "M5", "dir": 1, "eventos": ["compressao_armada"], "estrutura": "ascendente", "ultimo_topo": 4158.91, "ultimo_fundo": 4148.52},
                      {"tf": "M15", "dir": 1, "eventos": ["rompimento_confirmado(por_barra)"], "estrutura": "mista", "ultimo_topo": 4158.91, "ultimo_fundo": 4131.17},
                      {"tf": "M30", "dir": 1, "eventos": ["rompimento_pendente(por_barra)"], "estrutura": "mista", "ultimo_topo": 4161.78, "ultimo_fundo": 4131.17}])
# snapshot 63698 (bot 14, 09:00:22Z): candles M15 do EA — a penúltima é a barra 08:45 que decidiu (fechamento 4151.53)
C15M_63698 = "4146.02,4154.31,4145.19,4153.92,6978;4153.92,4158.91,4151.70,4155.79,7148;4155.80,4158.41,4150.22,4150.58,7351;4150.59,4154.83,4148.52,4151.53,5621;4151.56,4151.60,4151.48,4151.54,48"


def _decide(c, api):
    L = {"corte_do_ciclo": 1, "corte_origem": c["origem"], "B3": c["B3"]}
    return api._gestao2_decidir(c["lado"], L, {"B5": 0, "fechamento": c["fech"]}, {"contrato": "corte-ciclo-2"}, _ptf(c["ptf"]), c["barras"], [])


def test_1_corte_estrutural_confirmado_fecha_mesmo_com_continuidade(api):
    assert api.GESTAO_CONTRATO == "gestao-5"
    for nome, c in CASOS.items():
        acao, motivo, cont, cls, exp = _decide(c, api)
        assert acao == "close" and motivo == "ciclo", (nome, acao, exp)
        assert cls["estado"] == "invalidação estrutural confirmada" and cls["estrutural"], nome
        assert "não neutraliza" in exp, nome
    # 55 e 64: a continuidade estava INTACTA no instante — antes ela neutralizava o corte; agora não
    assert _decide(CASOS["55@04:00"], api)[2]["ok"] is True and _decide(CASOS["64@15:30"], api)[2]["ok"] is True


def test_2_segundo_sinal_fino_vira_protecao_efetiva_no_extremo_da_barra(api):
    acao, motivo, cont, cls, exp = _decide(GOLD_0845, api)
    assert acao == "proteger" and motivo == "ciclo" and cls["estado"] == "necessidade de proteção" and cls.get("protecao_efetiva_exigida")
    det = {"c15m": C15M_63698, "preco": "4151.54", "spr": "5", "pt": "0.01"}
    g = {"fechamento": 4151.53}
    b = api._g4_barra_de_decisao(g, det)
    assert b["minima"] == 4148.52 and b["maxima"] == 4154.83 and "mesmo snapshot" in b["fonte"]
    # stop vigente 4148.52 (já no extremo): preservado, nada a pedir
    pef = api._g4_protecao_efetiva(None, {"id": 14}, {"stop_atual": 4148.52}, {"sl": "4148.52"}, {"especificacao": {"distancia_minima_stop_pts": 0}}, det, g, 1)
    assert pef["nivel"] == 4148.52 and pef["pedir"] is False and pef["fechar"] is False and pef["aplicada"] is True
    # stop vigente no empate antigo (4129.12): pede o extremo da barra
    pef = api._g4_protecao_efetiva(None, {"id": 14}, {"stop_atual": 4129.12}, {"sl": "4129.12"}, {"especificacao": {"distancia_minima_stop_pts": 0}}, det, g, 1)
    assert pef["pedir"] is True and pef["nivel"] == 4148.52
    # preço já abaixo do extremo: a proteção não cabe → fecha (nunca "proteger" sem proteção)
    pef = api._g4_protecao_efetiva(None, {"id": 14}, {"stop_atual": 4129.12}, {"sl": "4129.12"}, {"especificacao": {"distancia_minima_stop_pts": 0}}, dict(det, preco="4148.00"), g, 1)
    assert pef["fechar"] is True
    # sem a barra de decisão (nem leitor 1.8 nem candles no snapshot): fail_closed → fecha
    pef = api._g4_protecao_efetiva(None, {"id": 14}, {}, {}, {}, {"preco": "4151.54", "pt": "0.01"}, g, 1)
    assert pef["fechar"] is True and "fail_closed" in pef["como"]
    # leitor 1.8: máxima/mínima vêm no próprio bloco assinado
    assert api._g4_barra_de_decisao({"fechamento": 1.0, "maxima": 2.0, "minima": 0.5}, {})["fonte"].startswith("leitor")
    # venda: máxima + spread (o stop da venda dispara no ask)
    pefv = api._g4_protecao_efetiva(None, {"id": 1}, {}, {"sl": "4170"}, {}, dict(det, preco="4150.00"), g, -1)
    assert pefv["nivel"] == round(4154.83 + 5 * 0.01, 2) and pefv["pedir"] is True
    # o mesmo 2º sinal fino COM direção contrária (M1 e M5 contra) fecha
    c2 = json.loads(json.dumps(GOLD_0845)); c2["ptf"][1]["dir"] = -1
    assert _decide(c2, api)[0] == "close"


def test_3_alerta_isolado_mantem(api):
    # sem corta=1: eventos contra a compra em M1/M5 = alerta de enfraquecimento; mantém (trailing só aperta)
    ptf = _ptf(GOLD_0845["ptf"])
    acao, motivo, cont, cls, exp = api._gestao2_decidir(1, {"corte_do_ciclo": 0, "B3": 0}, {"B5": 0, "fechamento": 4151.53}, None, ptf, 4, [])
    assert acao is None and cls["estado"] == "alerta de enfraquecimento" and "M1:quebra_estrutura_baixa" in cls["alertas_contrarios"]
    # B5 continua fechando sempre
    assert api._gestao2_decidir(1, {"corte_do_ciclo": 0, "B3": 0}, {"B5": 1}, None, ptf, 4, [])[0] == "close"


def _andares(D, t):
    import pandas as pd, bt_ciclo_v1 as CV1
    def df(rows, passo):
        r = [x for x in rows if pd.Timestamp(f"2026-{x[0][0:2]}-{x[0][2:4]} {x[0][4:6]}:{x[0][6:8]}") + pd.Timedelta(minutes=passo) <= t]
        ts = [pd.Timestamp(f"2026-{x[0][0:2]}-{x[0][2:4]} {x[0][4:6]}:{x[0][6:8]}") for x in r]
        return pd.DataFrame({"<DATE>": [x.strftime("%Y.%m.%d") for x in ts], "<TIME>": [x.strftime("%H:%M:%S") for x in ts],
                             "<OPEN>": [x[1] for x in r], "<HIGH>": [x[2] for x in r], "<LOW>": [x[3] for x in r], "<CLOSE>": [x[4] for x in r]})
    return {"M1": CV1.Andar("M1", df(D["M1"][-1500:], 1).tail(400).reset_index(drop=True)),
            "M5": CV1.Andar("M5", df(D["M5"], 5).tail(300).reset_index(drop=True)),
            "M15": CV1.Andar("M15", df(D["M15"], 15).tail(200).reset_index(drop=True))}


def test_4_janela_10_15_reproducao_cronologica_btc(api):
    import pandas as pd, bt_ciclo_v1 as CV1, bt_motor_leitura_hml as L
    D = json.load(open(os.path.join(AQUI, "dados_c27r54_btc_m1_m5_m15.json"), encoding="utf-8"))
    # fora da janela (minuto < 10): nada é publicado
    assert L._intrabarra_de_andares(CV1, _andares(D, pd.Timestamp("2026-10-15 02:20"))) is None
    # 02:25–02:29: única confirmação do dia (M1 degrau 2 + M5 degrau 1, exaustão apontando para CIMA) → corta VENDA, não a compra
    ib = L._intrabarra_de_andares(CV1, _andares(D, pd.Timestamp("2026-10-15 02:25")), "x")
    assert ib["minuto"] == 10 and ib["lados"]["venda"]["corta"] and not ib["lados"]["compra"]["corta"]
    assert ib["barra_m15_aberta"] == "2026-10-15 02:15:00" and ib["m1_ultima_fechada"] == "2026-10-15 02:24:00"
    # durante as 8 operações de BTC, minuto a minuto da janela: nenhuma confirmação contra a posição (o critério não corta por oscilação)
    cortes = []
    for o in D["ops"]:
        lado = int(o["lado"]); nome = "compra" if lado > 0 else "venda"
        t = pd.Timestamp(o["ta"]).tz_convert(None).ceil("min"); fim = pd.Timestamp(o["tf"]).tz_convert(None)
        while t <= fim:
            if t.minute % 15 >= 10:
                x = L._intrabarra_de_andares(CV1, _andares(D, t))
                if x and x["lados"][nome]["corta"]:
                    cortes.append((o["id"], str(t)))
            t = (t.floor("15min") + pd.Timedelta(minutes=10)) if t.minute % 15 < 9 else t + pd.Timedelta(minutes=1)
    assert cortes == []


def _conector():
    fonte = open(os.path.join(RAIZ, "conector_homolog", "hml", "conector_nucleo_homolog.py"), encoding="utf-8").read()
    nos = [n for n in ast.parse(fonte).body if isinstance(n, ast.FunctionDef) and n.name in ("_cv_utc", "_cv_txt", "_cv_assinar_intrabarra")]
    d = {}
    exec(compile(ast.Module(body=nos, type_ignores=[]), "conector_nucleo_homolog.py", "exec"), d)
    return d


def test_5_janela_assinada_e_verificada_pela_api(api, monkeypatch):
    import bt_cv_atestado as cvat
    seg = os.environ.get("BT_CV_SEGREDO") or "segredo-teste-c27r54"
    monkeypatch.setenv("BT_CV_SEGREDO", seg)
    tok = "tok-teste-c27r54"
    bot = {"bot_token": tok, "simbolo": "BTCUSD"}
    magic = api._magic_do_token(tok)
    at = {"bot_token_hash": hashlib.sha256(tok.encode()).hexdigest(), "versao_motor": "t", "simbolo": "BTCUSD", "magic": magic, "ts_barra_m15": "2026-10-15T02:15:00+00:00",
          "cv1": {"janela": {"M1": -1, "M5": -1, "M15": 1}, "veredito": "bloqueada", "motivo": "teste"}, "cv2": {"dirs": {"D1": 1, "H4": 1}}}
    agora = datetime.now(timezone.utc)
    ib = {"contrato": "janela-10-15-1", "leitor": "1.8-hml", "barra_m15_aberta": "2026-10-15 05:15:00", "minuto": 10, "m1_ultima_fechada": "2026-10-15 05:24:00",
          "m5_ultima_fechada": "2026-10-15 05:20:00", "M1": {"barra": "2026-10-15 05:24:00", "dir": -1}, "M5": {"barra": "2026-10-15 05:20:00", "dir": -1},
          "lados": {"compra": {"corta": True, "alerta": False, "texto": "M1 degrau 2 lado -1 · M5 degrau 1 lado -1"}, "venda": {"corta": False, "alerta": False, "texto": ""}},
          "calculado_utc": agora.strftime("%Y-%m-%dT%H:%M:%SZ")}
    C = _conector()
    ass = C["_cv_assinar_intrabarra"](at, ib, 10800)
    assert ass["barra_m15_aberta_utc"] == "2026-10-15T02:15:00Z" and ass["M1"]["barra_utc"] == "2026-10-15T02:24:00Z"
    ok, falha = api._ses_intrabarra(bot, {"cv_intrabarra": ass}, agora)
    assert ok and falha is None
    ruim = json.loads(json.dumps(ass)); ruim["lados"]["compra"]["corta"] = 0
    assert api._ses_intrabarra(bot, {"cv_intrabarra": ruim}, agora)[0] is None                      # adulterado
    assert api._ses_intrabarra({"bot_token": "outro", "simbolo": "BTCUSD"}, {"cv_intrabarra": ass}, agora)[1].startswith("janela_de_outro_bot")
    assert api._ses_intrabarra(bot, {"cv_intrabarra": ass}, agora + timedelta(seconds=300))[1].startswith("janela_antiga")
    assert api._ses_intrabarra(bot, {}, agora)[1].startswith("janela_ausente")


def test_6_ea_782_trailing_local_desligado_e_informado(api):
    src = (api._EA782_INPUT_ANTIGO + "\n//| BotTested — EXECUTOR PURO\n   if(!InpBTTrailingBarra) return;\n"
           '      "|cvt0=%s|m15h=%s|cD=%s|cW=%s|cMN=%s",\n      cvt0,m15h,cD,cW,cMN);\n "|eav=7.81-ciclos-lm2|"')
    t = api._ea_782_patch(src)
    assert "InpBTTrailingBarra" not in t and "input bool   InpBTTrailingLocal = false;" in t and "if(!InpBTTrailingLocal) return;" in t
    assert "|tbar=%d" in t and "(int)InpBTTrailingLocal);" in t and "eav=7.83-ciclos-lm2" in t
    assert api._ea_782_patch(t) == t                                                        # idempotente
    assert api._ea_782_patch("EA nativo " + api._EA782_INPUT_ANTIGO) == "EA nativo " + api._EA782_INPUT_ANTIGO   # só o executor puro
    assert '"|cvt0=%s|m15h=%s|cD=%s|cW=%s|cMN=%s|tbar=%d",' in api._BT_VISAO_MQL5 and "eav=7.83-ciclos-lm2" in api._BT_VISAO_MQL5
    # 7.83: sinal de conexão com a plataforma no selo (pulsa até 75 s do último snapshot aceito; cinza parado depois)
    assert "BT_LINK_V1" in api._BT_PAINEL_MQL5 and "   BTLinkPlataforma();\n" + api._EA783_STATUS in api._BT_PAINEL_MQL5
    sel = api._EA783_TICK_ANTES + "\n" + api._EA783_STATUS + "EXECUTOR PURO"
    ps = api._ea_782_patch(sel)
    assert ps.count("BT_LINK_V1") == 1 and "BTLinkPlataforma();" in ps and api._ea_782_patch(ps) == ps           # todo EA novo informa o trailing
    e = api._ea_trailing_estado({"eav": "7.82-ciclos-lm2", "tbar": "0"})
    assert e["tbar"] == 0 and "DESLIGADO" in e["estado"]
    assert api._ea_trailing_estado({"eav": "7.81-ciclos-lm2"})["tbar"] is None


class _Q:
    def __init__(self, sb, t): self.sb, self.t, self.upd = sb, t, None
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def update(self, d): self.upd = d; return self
    def insert(self, d): self.sb.ins.append((self.t, d)); return self
    def execute(self):
        class R: pass
        r = R()
        if self.upd is not None:
            self.sb.cfg.update(self.upd["config"]) if self.t == "sessoes_teste" else None
            r.data = [self.upd]
        else:
            r.data = [{"config": json.loads(json.dumps(self.sb.cfg))}]
        return r


class _SB:
    def __init__(self, cfg): self.cfg, self.ins = cfg, []
    def table(self, t): return _Q(self, t)


def test_7_bloqueio_do_gold_retirado_quando_o_ea_informa_trailing_desligado(api, monkeypatch):
    monkeypatch.setattr(api, "_ses_trilha", lambda *a, **k: None)
    bq = {"14": {"motivo": "stop da abertura 60 alterado fora da plataforma (...trailing por barra do EA (BTvTrailingBarra)) — desligar o trailing do EA (InpBTTrailingBarra=false)",
                 "desde_utc": "2026-10-15T08:32:24Z", "ref": {"abertura_id": 60}}}
    sb = _SB({"bloqueios_por_bot": json.loads(json.dumps(bq))})
    ses = {"id": "CAMP", "config": {"bloqueios_por_bot": json.loads(json.dumps(bq))}}
    # EA 7.81 (sem tbar): nada muda
    api._ses_trailing_ea(sb, ses, {"id": 14}, {"eav": "7.81-ciclos-lm2"})
    assert "14" in sb.cfg["bloqueios_por_bot"]
    # EA 7.82 com tbar=1: continua bloqueado
    api._ses_trailing_ea(sb, ses, {"id": 14}, {"eav": "7.82-ciclos-lm2", "tbar": "1"})
    assert "14" in sb.cfg["bloqueios_por_bot"]
    # EA 7.82 com tbar=0: causa resolvida e VERIFICADA no dado → retirado, histórico preservado
    api._ses_trailing_ea(sb, ses, {"id": 14}, {"eav": "7.82-ciclos-lm2", "tbar": "0", "_snapshot_id": 999})
    assert "14" not in sb.cfg["bloqueios_por_bot"]
    lib = sb.cfg["bloqueios_liberados"][-1]
    assert lib["bot_id"] == 14 and lib["bloqueio"]["ref"]["abertura_id"] == 60 and lib["evidencia"] == {"snapshot_id": 999, "eav": "7.82-ciclos-lm2", "tbar": 0}
    # um bloqueio de OUTRA causa não é retirado pelo tbar
    sb2 = _SB({"bloqueios_por_bot": {"13": {"motivo": "perda do dia", "desde_utc": "x"}}})
    api._ses_trailing_ea(sb2, {"id": "C", "config": json.loads(json.dumps(sb2.cfg))}, {"id": 13}, {"eav": "7.82-ciclos-lm2", "tbar": "0"})
    assert "13" in sb2.cfg["bloqueios_por_bot"]
