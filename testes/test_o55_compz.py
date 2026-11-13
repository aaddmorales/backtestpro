"""ORDEM 055 — COMPZ ("última vela que respeitou o suporte/resistência" depois da mudança de estrutura), EA lateral-r1.3 (O55).
(1) pivôs: a memória O39 da BabyMachine = fractal N=2 (estilo do indicador de estrutura do CodeBase MQL5) — nada novo a detectar;
(2) caso do dono, XAUUSD 11/11 (op51): mudança confirmada no fechamento da op42, referências op43 → op47 → op51, sinal no 1º cruzamento
    da mínima da op51 (4047,19) na op52 — e NÃO a mínima da vela que fechou fora da zona (ROMPZ: 4053,37 / 4047,99 / 4044,29);
    autorização separada: o filtro vigente bloqueia ("entrada dentro da zona"); sem filtro (sombra) a venda sai pelo canal com +5,37 R;
(3) EA (C++ no shim) ≡ referência Python, evento a evento, no XAU 11–12/11 (sombra) e no BTC de outubro com envio ligado;
(4) com envio desligado nenhuma ordem sai. Dados XAU: histórico do MT5 enviado pelo EA + velas do Conector; op42–op52 de 11/11 lidas do
    print do dono (lacuna do Conector) — ver dados_o55/LEIA.txt."""
import os, sys, shutil, calendar, subprocess, tempfile
import numpy as np, pandas as pd, pytest

AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
REF51, REF53, REF55 = (os.path.join(AQUI, f"referencia_o{x}") for x in ("51", "53", "55"))
D55X = os.path.join(AQUI, "dados_o55"); D55 = os.path.join(AQUI, "dados_c27r55")
sys.path[:0] = [RAIZ, REF55, REF53, REF51, AQUI]
import compz_o55 as CZ, estrutura_ref_o55 as ER, estrutura_o39 as EO  # noqa: E402

OP41 = 1794387600                              # 11/11 11:00 srv (abertura UTC 09:00)
OP = lambda n: OP41 + (n - 41) * 900
XAU = lambda x: os.path.join(D55X, f"XAUUSD_{x}_1112.csv")
INI = 1794351600                               # 11/11 01:00 srv


def _ler(arq):
    d = pd.read_csv(arq, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
    d["ep"] = [calendar.timegm(x.timetuple()) for x in pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")]
    return d.reset_index(drop=True)


@pytest.fixture(scope="module")
def A():
    os.environ["BT_CARD_TESTE_USER"] = "u-master"
    import api as A
    assert 'BTLAT_VERSAO "lateral-r1.3 (O55)"' in A._BT_LATERAL_R0_MQL5 and "BTLatCompzTick" in A._BT_LATERAL_R0_MQL5
    return A


def _sim(A, **cfg):
    from test_o53_lateral_r1 import _traduzir, _cfg
    tmp = tempfile.mkdtemp()
    for f in ("mt5shim.h", "main.cpp"):
        shutil.copy(os.path.join(REF53, "shim", f), tmp)
    _traduzir(_cfg(A._BT_LATERAL_R0_MQL5, **cfg), os.path.join(tmp, "ea.cpp"))
    r = subprocess.run(["g++", "-std=c++17", "-O2", "-o", os.path.join(tmp, "sim"), os.path.join(tmp, "main.cpp")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    return os.path.join(tmp, "sim")


def _cz_ea(out):
    ev = [dict(p.split("=", 1) for p in l.split("|")[1:] if "=" in p) for l in out if l.startswith("EVT|")]
    cz = [(e["ev"], e["sinal"], e.get("ref") or e.get("lh"), e.get("t") if e["ev"] == "compz_disparo" else None, e.get("bid"), e.get("decisao"), e.get("motivo"))
          for e in ev if e.get("ev", "").startswith("compz")]
    return ev, cz


def _cz_py(I):
    f = lambda x: None if x is None else f"{x:.2f}"
    return [(e["tipo"], e["sinal"], f(e.get("ref") if e["tipo"] != "compz_mudanca" else e.get("lh")), str(e["t_ms"] // 1000) if e["tipo"] == "compz_disparo" else None,
             f(e.get("bid")), e.get("decisao"), e.get("motivo")) for e in I.eventos if e["tipo"].startswith("compz")]


def _norm_motivo(cz):
    """o texto do cancelamento do EA não tem acentos/·; compara-se o início do motivo."""
    k = lambda m: None if m is None else m.split(" ")[0].replace("ç", "c").replace("ã", "a").replace("é", "e")
    return [(a, b, c, d, e, f, k(g)) for a, b, c, d, e, f, g in cz]


def test_1_pivos_o39_iguais_ao_fractal_do_indicador():
    for arq, at in ((XAU("M15"), "XAUUSD"), (os.path.join(D55, "BTCUSD_M15_202610.csv"), "BTCUSD")):
        m = _ler(arq); M = EO.Memoria(at, "M15"); idx = {int(t): i for i, t in enumerate(m.ep)}; P = set()
        for i, r in enumerate(m.itertuples()):
            for e in M.nova_barra(int(r.ep), int(r.ep) + 900, r.open, r.high, r.low, r.close):
                if e["evento"] in ("confirmado", "agrupado"):
                    n = next(x for x in M.niveis if x["id"] == e["nivel"]); te = n["t_extremo"] if e["evento"] == "confirmado" else n["membros"][-1]["t_extremo"]
                    P.add(("fundo" if n["funcao"] == "suporte" else "topo", idx[int(te)], i))
        F = {(a, b, c) for a, b, _, c in ER.fractal_n(m.high.values, m.low.values, 2)}
        assert P <= F and len(F - P) <= 3                                  # mesmo pivô, mesma barra de confirmação (i+2)


def test_2_caso_op51_xau_1111():
    I = CZ.rodar(_ler(XAU("M15")), _ler(XAU("H1")), _ler(XAU("M1")), INI, 0.10, caixa=False, rompz=False, compz=True)
    mud = [e for e in I.eventos if e["tipo"] == "compz_mudanca" and e["lado"] < 0 and OP(41) <= e["t_ms"] // 1000 <= OP(44)]
    assert len(mud) == 1 and mud[0]["sinal"] == f"CV-{OP(42)}" and mud[0]["lh"] == 4061.77 and mud[0]["anterior"] == 4066.91
    ref = [(e["barra_ref"], e["ref"]) for e in I.eventos if e["tipo"] == "compz_referencia" and e["sinal"] == f"CV-{OP(42)}"]
    assert ref == [(OP(43), 4046.4), (OP(47), 4047.0), (OP(51), 4047.2)]
    d = [e for e in I.eventos if e["tipo"] == "compz_disparo" and e["sinal"] == f"CV-{OP(42)}"][0]
    assert d["t_ms"] // 1000 == OP(52) and d["gatilho"] == 4047.19 and d["bid"] <= 4047.19
    assert d["decisao"] == "sinal disparado; bloqueado: entrada dentro da zona"            # filtro vigente preservado
    I0 = CZ.rodar(_ler(XAU("M15")), _ler(XAU("H1")), _ler(XAU("M1")), INI, 0.10, caixa=False, rompz=False, compz=True, filtro_compz=False)
    op = [o for o in I0.ops if o["sinal"] == f"CV-{OP(42)}"][0]
    assert op["entrada"] == 4047.0 and op["motivo_saida"] == "canal" and round(op["saida"], 2) == 3985.5 and op["R"] > 5
    # a ROMPZ (vela que fechou fora da zona) arma em outras barras — a diferença do teste do dono
    IR = CZ.rodar(_ler(XAU("M15")), _ler(XAU("H1")), _ler(XAU("M1")), INI, 0.10, caixa=False, rompz=True, compz=False)
    g = sorted({e["gatilho"] for e in IR.eventos if e["tipo"] == "rompz_armado" and e["lado"] < 0 and OP(41) <= e["t_ms"] // 1000 <= OP(53)})
    assert g == [4044.29, 4047.99, 4053.37] and 4047.19 not in g


def test_3_ea_igual_referencia_xau_e_btc(A):
    # XAU 11–12/11, sombra (só COMPZ)
    sim = _sim(A, InpEntradaCaixa="false", InpEntradaRompZ="false")
    out = subprocess.run([sim, "15", XAU("M15"), XAU("M1"), str(INI), "10", XAU("H1")], capture_output=True, text=True).stdout.split("\n")
    ev, ea = _cz_ea(out)
    I = CZ.rodar(_ler(XAU("M15")), _ler(XAU("H1")), _ler(XAU("M1")), INI, 0.10, caixa=False, rompz=False, compz=True, enviar=False)
    assert _norm_motivo(ea) == _norm_motivo(_cz_py(I)) and len(ea) > 50
    assert not any(l.startswith("ORDEM") for l in out)
    ini_ev = [e for e in ev if e.get("ev") == "inicio"][0]
    assert ini_ev["versao"] == "lateral-r1.3 (O55)" and ini_ev["compz"] == "sim" and ini_ev["envio_ordens"] == "desligado (sombra)"
    # BTC outubro, envio LIGADO e filtro da COMPZ desligado (só para provar a execução): entradas e saídas iguais
    f15, f1, fh = (os.path.join(D55, f"BTCUSD_{x}_202610.csv") for x in ("M15", "M1", "H1"))
    b, m1 = _ler(f15), _ler(f1); ini = int(max(b.ep.iloc[0] + 29 * 900, m1.ep.iloc[0]))
    sim2 = _sim(A, InpEnviarOrdens="true", InpEntradaCaixa="false", InpEntradaRompZ="false", InpCompzFiltro="false")
    out2 = subprocess.run([sim2, "15", f15, f1, str(ini), "1500", fh], capture_output=True, text=True).stdout.split("\n")
    ev2, ea2 = _cz_ea(out2)
    I2 = CZ.rodar(b, _ler(fh), m1, ini, 15.0, at="BTCUSD", caixa=False, rompz=False, compz=True, filtro_compz=False, enviar=True)
    assert _norm_motivo(ea2) == _norm_motivo(_cz_py(I2))
    ea_e = [(int(x.split("|")[2]), x.split("|")[1], float(x.split("|")[3])) for x in out2 if x.startswith("ORDEM")]
    ea_s = [(int(x.split("|")[2]), x.split("|")[1], float(x.split("|")[3])) for x in out2 if x.startswith("FECHA")]
    py_e = [(e["t_ms"] // 1000, "buy" if e["lado"] > 0 else "sell", round(e["preco"], 2)) for e in I2.eventos if e["tipo"] == "entrada_virtual"]
    py_s = [(e["t_ms"] // 1000, "stop" if e["motivo"].startswith("stop") else "cmd", round(e["preco"], 2)) for e in I2.eventos if e["tipo"] == "saida_virtual"]
    assert ea_e == py_e and ea_s == py_s and len(ea_e) >= 1
    assert any(e.get("ev") == "ordem" and e.get("entrada") == "compz" for e in ev2)


def test_4_toque_nao_dispara_e_ultima_vela():
    """se a barra seguinte só IGUALA a mínima da última vela que respeitou (toque), não há sinal; a referência é sempre a última vela."""
    m15, m1 = _ler(XAU("M15")), _ler(XAU("M1"))
    k15 = m15.ep == OP(52); k1 = m1.ep.between(OP(52), OP(53) - 1)
    for d in (m15.loc[k15], m1.loc[k1]):
        pass
    m15.loc[k15, ["open", "high", "low", "close"]] = [4048.0, 4049.5, 4047.20, 4048.5]        # op52 só toca 4047,20 (= mínima da op51)
    m1.loc[k1, ["open", "high", "low", "close"]] = [4048.0, 4049.5, 4047.20, 4048.5]
    I = CZ.rodar(m15, _ler(XAU("H1")), m1, INI, 0.10, caixa=False, rompz=False, compz=True)
    d = [e for e in I.eventos if e["tipo"] == "compz_disparo" and e["sinal"] == f"CV-{OP(42)}"]
    assert not d or d[0]["t_ms"] // 1000 >= OP(53)                                            # nada na op52: toque não dispara
    ref = [(e["barra_ref"], e["ref"]) for e in I.eventos if e["tipo"] == "compz_referencia" and e["sinal"] == f"CV-{OP(42)}"]
    assert ref[:3] == [(OP(43), 4046.4), (OP(47), 4047.0), (OP(51), 4047.2)]


def test_5_trilha_compz_no_diagnostico_e_pdf():
    import datetime as dt, json, validacao_o53 as V
    from zoneinfo import ZoneInfo
    from test_o53_lateral_r1 import _SB
    iso = lambda e: dt.datetime.fromtimestamp(int(e), dt.timezone.utc).isoformat()
    def linhas(tf, x):
        return [{"simbolo": "XAUUSD", "tf": tf, "abertura_utc": iso(e), "o": o, "h": h, "l": l, "c": c, "fechado": True, "ultimo_visto_utc": "x"}
                for e, o, h, l, c in zip(x.ep, x.open, x.high, x.low, x.close)]
    m15, m1, h1 = (_ler(XAU(x)) for x in ("M15", "M1", "H1"))
    ev = [{"tipo": "bot_lateral", "criado_em": "2026-11-11T07:40:00+00:00", "detalhe_json": {"magic": "444198325", "ev": "inicio",
           "raw": "tipo=lateral|simbolo=XAUUSD|v=lateral-r1.3 (O55)|ev=inicio|versao=lateral-r1.3 (O55)|off=7200|compz=sim|envio_ordens=desligado (sombra)|tf=M15"}}]
    sb = _SB({"auditoria_candles": linhas("M15", m15) + linhas("M1", m1) + linhas("H1", h1), "auditoria_leituras": [], "agente_eventos": ev, "babymachine_operacoes": []})
    de, ate = dt.datetime(2026, 11, 11, 8, 0, tzinfo=dt.timezone.utc), dt.datetime(2026, 11, 11, 13, 0, tzinfo=dt.timezone.utc)
    T = V.trilha_compz(sb, {"id": 16, "simbolo": "XAUUSD", "magic_number": 444198325, "user_id": "u"}, "M15", de, ate, ZoneInfo("Europe/Kyiv"))
    assert T["situacao"] == "ok"
    x = [l for l in T["linhas"] if l["id"] == f"CV-{OP(42)}"][0]
    assert x["mudanca"]["lh"] == 4061.77 and x["mudanca"]["anterior"] == 4066.91 and x["ultima_vela"]["preco"] == 4047.2 and x["gatilho"] == 4047.19
    assert x["disparo"][11:16] == "13:45" and x["decisao"] == "sinal reconhecido; entrada bloqueada — entrada dentro da zona"
    assert T["estados"]["compz_ativa_no_terminal"].startswith("sim") and T["janelas"] and V.grafico_png(T["janelas"][0])[:4] == b"\x89PNG"
    import diagnostico_lm_o50 as D
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    d = FPDF(); d.set_auto_page_break(True, margin=14); d.add_page()
    def p(t, b=False, tam=8): d.set_font("Helvetica", "B" if b else "", tam); d.multi_cell(0, 4, D._t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    def tab(cab, linhas, larg, lim=90): [p(" | ".join(D._t(x, 30) for x in l)) for l in [cab] + list(linhas)]
    S5 = {"titulo": "5.", "estados": {}, "bots": [{"bot": "ML New Bot 02", "simbolo": "XAUUSD", "tf": "M15", "bot_id": 16, "ea_registrado_na_plataforma": "lateral-r1.3 (O55)",
                                                     "observado": {"operacoes": []}, "replay": {"situacao": "x"}, "pivos": {"situacao": "x"}, "janelas": [],
                                                     "rompz": {"situacao": "x"}, "compz": json.loads(json.dumps(T, default=str))}]}
    D._pdf_secao_5(d, S5, lambda t: p(t, True, 12), lambda t: p(t, True, 9), p, lambda ps: [p(f"{k}: {v}") for k, v in ps], tab, 186)
    assert bytes(d.output())[:4] == b"%PDF"
