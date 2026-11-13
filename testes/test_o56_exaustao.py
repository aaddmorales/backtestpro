"""ORDEM 056-A — saída por exaustão (exaustao-1), EA lateral-r1.4 (O56).
(1) caso BTC 13/11 (ZV-1794542400): gestão anterior sai no canal em 68998,02 (+2,41 R, igual ao acompanhamento externo);
    com exaustão: reação na barra 06:00 UTC (08:00 srv), gatilho 68306,81 superado na barra seguinte → saída (+3,50 R no replay M1);
(2) controle: barra 04:30 UTC esticada (2,49 ATR) e compradora SEM desaceleração → mantém; a queda continuou até 67508,90;
(3) gatilho: tocar não fecha; renovar a mínima da reação cancela; mesma M1 cruza e renova = indeterminado (mantém);
(4) EA (C++ no shim) ≡ referência Python no XAU 30/10–12/11 com envio ligado e filtros desligados (mais posições);
(5) conta não DEMO: nenhuma ordem sai (bloqueio fixo)."""
import os, sys, calendar, subprocess
import numpy as np, pandas as pd, pytest
AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
sys.path[:0] = [RAIZ, os.path.join(AQUI, "referencia_o56"), AQUI]
import exaustao_o56 as EX  # noqa: E402
from test_o55_compz import _sim, XAU, INI, _ler  # noqa: E402

D56 = os.path.join(AQUI, "dados_o56")
T_ENT, E0, ST0, ATR0 = 1794536241, 70418.07, 71008.32, 295.1227


@pytest.fixture(scope="module")
def A():
    os.environ["BT_CARD_TESTE_USER"] = "u-master"
    import api as A
    assert 'BTLAT_VERSAO "lateral-r1.4 (O56)"' in A._BT_LATERAL_R0_MQL5 and "BTExTick" in A._BT_LATERAL_R0_MQL5 and "BTLatDemo" in A._BT_LATERAL_R0_MQL5
    return A


def _caso_btc(exaustao):
    m15 = _ler(os.path.join(D56, "BTCUSD_M15_1113.csv")); m1 = _ler(os.path.join(D56, "BTCUSD_M1_1113_0400_0900srv.csv"))
    I = EX.InstanciaE("BTCUSD", "M15", exaustao=exaustao, caixa=False, rompz=False, compz=False, filtro=False, reversao_sombra=False)
    I.ativo_desde_ms = 0; ult = None; aberto = False; ep = m15.ep.values
    df = lambda x: pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)
    for t, px, hl in EX.ticks_m1(m1, None):
        t0 = (t // 900) * 900
        if t0 != ult:
            n = int(np.searchsorted(ep + 900, t, side="right")); I.fecha_barra(df(m15.iloc[max(0, n - 1200):n]), None); ult = t0
        if not aberto and t >= T_ENT:
            I.pos = {"id": "ZV-1794542400", "sinal": "ZV-1794542400", "lado": -1, "t_ent_ms": T_ENT * 1000, "entrada": E0, "stop": ST0, "atr": ATR0,
                     "barra_ent_ms": (T_ENT // 900) * 900 * 1000, "ref_inval": None, "ref_def": "máxima da barra de entrada", "saida_pendente": False,
                     "saida_apos_ms": None, "motivo_dec": None, "spread_ent": 5.0, "espaco": {}}; aberto = True
        I.m1_atual = hl; bid = round(px, 2); I.tick(t * 1000, bid, round(bid + 5.0, 2))
        if aberto and I.pos is None: break
    return I


def test_1_caso_btc_1311_canal_x_exaustao():
    a = _caso_btc(False); assert len(a.ops) == 1
    o = a.ops[0]; assert o["motivo_saida"] == "canal" and o["saida"] == 68998.02 and round(o["pts"], 2) == 1420.05 and round(o["pts"] / 590.25, 2) == 2.41
    b = _caso_btc(True); assert len(b.ops) == 1
    reac = [e for e in b.eventos if e["tipo"] == "exaustao_reacao"]
    assert len(reac) == 1 and reac[0]["barra_ms"] == 1794549600000 and reac[0]["gat"] == 68306.81 and reac[0]["cancel"] == 67811.5
    assert reac[0]["dist_max"] >= 1.5 and reac[0]["desaceleracao"] and reac[0]["clv_ant"] >= 0.5 and reac[0]["clv"] >= 0.6
    o = b.ops[0]; assert o["motivo_saida"] == "exaustao" and o["t_sai_ms"] // 1000 == 1794550530 and o["saida"] > 68306.81
    assert o["pts"] > 1420.05 and round(o["pts"] / 590.25, 2) == 3.50


def test_2_controle_esticado_continua():
    b = _caso_btc(True)
    ctx = {e["barra_ms"] // 1000: e for e in b.eventos if e["tipo"] == "exaustao_contexto"}
    e = ctx[1794543300]                         # 04:30 UTC (06:30 srv): 2,49 ATR abaixo da EMA20 Low, barra compradora
    assert e["contexto"] and e["dist_atr"] > 2.4 and not e["desaceleracao"] and not e["alerta"] and not e["reacao"]
    assert len(ctx) >= 12                        # esticada desde 02:45 UTC, sem saída
    m15 = _ler(os.path.join(D56, "BTCUSD_M15_1113.csv"))
    assert m15[(m15.ep > 1794543300) & (m15.ep <= 1794548700)].low.min() == 67508.9   # a queda continuou depois


def _inst_sintetica(m1_real=True):
    """venda aberta; barra de reação fabricada; a barra seguinte é alimentada tick a tick pelo teste."""
    I = EX.InstanciaE("BTCUSD", "M15", caixa=False, rompz=False, compz=False, filtro=False, reversao_sombra=False); I.ativo_desde_ms = 0
    t0 = 1_800_000_000 - (1_800_000_000 % 900)
    I.pos = {"id": "S", "sinal": "S", "lado": -1, "t_ent_ms": 0, "entrada": 100.0, "stop": 200.0, "atr": 5.0, "barra_ent_ms": 0, "ref_inval": 1e9,
             "ref_def": "", "saida_pendente": False, "saida_apos_ms": None, "motivo_dec": None, "spread_ent": 0.0, "espaco": {}}
    I.exa["pos"] = {"id": "S", "gat_t": EX.tk(50.0) + 1, "gat": 50.01, "can_t": EX.tk(40.0) - 1, "cancel": 39.99, "ini_ms": t0 * 1000, "fim_ms": (t0 + 900) * 1000, "lado": -1, "tocou": False}
    return I, t0


def test_3_gatilho_toque_cancela_indeterminado():
    I, t0 = _inst_sintetica(); I.m1_atual = (50.0, 45.0); I.tick(t0 * 1000 + 1, 50.0, 50.0)           # tocar a máxima não fecha
    assert I.pos is not None and I.exa["pos"] is not None
    I.m1_atual = (49.0, 39.99); I.tick(t0 * 1000 + 2, 39.99, 39.99)                                     # renovou a mínima: cancela
    assert I.pos is not None and I.exa["pos"] is None and any(e["tipo"] == "exaustao_cancelada" for e in I.eventos)
    I, t0 = _inst_sintetica(); I.m1_atual = (50.01, 39.0); I.tick(t0 * 1000 + 1, 50.01, 50.01)          # mesma M1 cruzou e renovou
    assert I.pos is not None and any(e["tipo"] == "exaustao_indeterminada" for e in I.eventos)
    I, t0 = _inst_sintetica(); I.m1_atual = (50.01, 45.0); I.tick(t0 * 1000 + 1, 50.01, 50.02)          # superou 1 tick: fecha
    assert I.pos is None and I.ops[0]["motivo_saida"] == "exaustao" and I.ops[0]["saida"] == 50.02


def _ops_ea(out):
    ev = [l.split("|") for l in out if l.startswith(("ORDEM", "FECHA"))]
    return [(x[0], x[1], int(x[2]), x[3]) for x in ev]


def test_4_ea_igual_referencia_xau(A):
    sim = _sim(A, InpEnviarOrdens="true", InpRompZFiltro="false", InpCompzFiltro="false", InpExaustao="true")
    out = subprocess.run([sim, "15", XAU("M15"), XAU("M1"), str(INI), "10", XAU("H1")], capture_output=True, text=True).stdout.split("\n")
    I = EX.rodar(_ler(XAU("M15")), _ler(XAU("H1")), _ler(XAU("M1")), INI, 0.10, enviar=True, filtro_rompz=False, filtro_compz=False, m1_real=False)
    py = []
    for o in sorted(I.ops, key=lambda o: o["t_ent_ms"]):
        py.append(("ORDEM", "sell" if o["lado"] < 0 else "buy", o["t_ent_ms"] // 1000, f'{o["entrada"]:.2f}'))
        py.append(("FECHA", "stop" if o["motivo_saida"].startswith("stop") else "cmd", o["t_sai_ms"] // 1000, f'{o["saida"]:.2f}'))
    ea = _ops_ea(out)
    assert ea == py and len(ea) > 20
    exa_ea = [l for l in out if "|ev=exaustao_saida|" in l]; exa_py = [o for o in I.ops if o["motivo_saida"] == "exaustao"]
    assert len(exa_ea) == len(exa_py) >= 3
    ini = [l for l in out if "|ev=inicio|" in l][0]
    assert "versao=lateral-r1.4 (O56)" in ini and "exaustao=sim" in ini and "conta=DEMO" in ini and "envio_ordens=ligado (DEMO)" in ini
    assert any("|ev=ordem|" in l and "envio=enviada" in l and "|negocio=" in l for l in out)


def test_5_conta_real_nada_sai(A):
    sim = _sim(A, InpEnviarOrdens="true", InpRompZFiltro="false", InpCompzFiltro="false", InpExaustao="true")
    out = subprocess.run([sim, "15", XAU("M15"), XAU("M1"), str(INI), "10", XAU("H1")], capture_output=True, text=True,
                         env={**os.environ, "SIM_CONTA_REAL": "1"}).stdout.split("\n")
    assert not any(l.startswith(("ORDEM", "FECHA|cmd")) for l in out)
    assert any("conta nao e DEMO (bloqueio fixo O56)" in l for l in out)
    ini = [l for l in out if "|ev=inicio|" in l][0]; assert "conta=NAO-DEMO" in ini and "bloqueado (conta nao e DEMO)" in ini


def test_6_diagnostico_exaustao_e_cadeia_demo_pdf():
    import datetime as dt, json, validacao_o53 as V
    from zoneinfo import ZoneInfo
    from test_o53_lateral_r1 import _SB
    iso = lambda e: dt.datetime.fromtimestamp(int(e), dt.timezone.utc).isoformat()
    def linhas(tf, x):
        return [{"simbolo": "BTCUSD", "tf": tf, "abertura_utc": iso(e), "o": o, "h": h, "l": l, "c": c, "fechado": True, "ultimo_visto_utc": "x"}
                for e, o, h, l, c in zip(x.ep, x.open, x.high, x.low, x.close)]
    m15 = _ler(os.path.join(D56, "BTCUSD_M15_1113.csv")); m1 = _ler(os.path.join(D56, "BTCUSD_M1_1113_0400_0900srv.csv"))
    raw = ("tipo=lateral|simbolo=BTCUSD|v=lateral-r1.2 (O53-D)|ev=rompz_disparo|sinal=ZV-1794542400|lado=-1|t=1794543441|bid=70418.07|ask=70423.07|gatilho=70422.13|"
           "posicao_aberta=nao|espaco_passa=sim|E=70418.07|spread=5.00|R=590.25|atr=295.1227|motivo=sem zona a frente|stop=71008.32|decisao=sinal disparado; ordem autorizada")
    ini = "tipo=lateral|simbolo=BTCUSD|v=lateral-r1.4 (O56)|ev=inicio|versao=lateral-r1.4 (O56)|off=7200|exaustao=sim|conta=DEMO|envio_ordens=ligado (DEMO)|tf=M15|magic=138448864"
    ev = [{"tipo": "bot_lateral", "id": 1, "criado_em": "2026-11-13T02:17:29+00:00", "detalhe_json": {"magic": "138448864", "ev": "rompz_disparo", "raw": raw}},
          {"tipo": "bot_lateral", "id": 2, "criado_em": "2026-11-13T02:17:30+00:00", "detalhe_json": {"magic": "138448864", "ev": "rompz_disparo", "raw": raw}},
          {"tipo": "bot_lateral", "id": 3, "criado_em": "2026-11-13T18:00:00+00:00", "detalhe_json": {"magic": "138448864", "ev": "inicio", "raw": ini}}]
    sb = _SB({"auditoria_candles": linhas("M15", m15) + linhas("M1", m1), "agente_eventos": ev, "babymachine_operacoes": [], "mt5_jobs": [], "conector_snapshots": []})
    de, ate = dt.datetime(2026, 11, 13, 0, 0, tzinfo=dt.timezone.utc), dt.datetime(2026, 11, 13, 7, 0, tzinfo=dt.timezone.utc)
    bot = {"id": 15, "nome": "ML New Bot 01", "simbolo": "BTCUSD", "magic_number": 138448864, "user_id": "u", "bot_token": None}
    V._spread_mediano = lambda sb_, s_: 5.0                                    # spread do registro (bid/ask do disparo)
    T = V.gestao_exaustao(sb, bot, "M15", de, ate, ZoneInfo("Europe/Kyiv"))
    assert T["situacao"] == "ok" and len(T["linhas"]) == 1                     # reenvio duplicado do EA não duplica a posição
    x = T["linhas"][0]
    assert x["gestao_anterior"]["motivo"] == "canal" and x["gestao_anterior"]["saida"] == 68998.02 and x["gestao_anterior"]["R"] == 2.41
    assert x["com_exaustao"]["motivo"] == "exaustao" and x["com_exaustao"]["R"] == 3.5 and x["com_exaustao"]["quando"][11:16] == "08:15"
    assert x["exemplo_esticado_mantido"] and any(e["tipo"] == "exaustao_reacao" for e in x["eventos_exaustao_replay"])
    png = V.grafico_png(T["janelas"][0]); assert png[:4] == b"\x89PNG"
    open(os.path.join(D56, "O56_caso_btc_1311_janela.png"), "wb").write(png)
    C = V.cadeia_demo(sb, bot, de, ate + dt.timedelta(hours=12), ZoneInfo("Europe/Kyiv"))
    assert C["carregado"].startswith("lateral-r1.4 (O56)") and C["envio_demo_ativo"] == "ligado (DEMO)" and C["primeiro_sinal_elegivel"] == "DEMO ativo, aguardando sinal elegível"
    assert C["comprovacao_ponta_a_ponta"] == "pendente"
    import diagnostico_lm_o50 as D
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    d = FPDF(); d.set_auto_page_break(True, margin=14); d.add_page()
    def p(t, b=False, tam=8): d.set_font("Helvetica", "B" if b else "", tam); d.multi_cell(0, 4, D._t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    def tab(cab, linhas, larg, lim=90): [p(" | ".join(D._t(x, 30) for x in l)) for l in [cab] + list(linhas)]
    S5 = {"titulo": "5.", "estados": {}, "bots": [{"bot": "ML New Bot 01", "simbolo": "BTCUSD", "tf": "M15", "bot_id": 15, "ea_registrado_na_plataforma": "lateral-r1.4 (O56)",
                                                     "observado": {"operacoes": []}, "replay": {"situacao": "x"}, "pivos": {"situacao": "x"}, "janelas": [],
                                                     "rompz": {"situacao": "x"}, "compz": {"situacao": "x"}, "demo": C, "exaustao": json.loads(json.dumps(T, default=str))}]}
    D._pdf_secao_5(d, S5, lambda t: p(t, True, 12), lambda t: p(t, True, 9), p, lambda ps: [p(f"{k}: {v}") for k, v in ps], tab, 186)
    pdf = bytes(d.output()); assert pdf[:4] == b"%PDF"
    open(os.path.join(D56, "O56_secao5_amostra.pdf"), "wb").write(pdf)
