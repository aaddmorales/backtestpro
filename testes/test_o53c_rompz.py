"""ORDEM 053-C — Bot 01 (BTCUSD M15) não vendeu na barra 71 de 10/11/2026.
(1) a R0 que estava no gráfico falha na 1ª condição (caixa de 12 barras > 3 ATR) na barra 70 — EA e referência O44 dizem o mesmo;
(2) ROMPZ em sombra (EA lateral-r1.2): três casos sobre os dados reais do MT5 (BabyMachine): rompimento válido na 71 dispara; tocar a mínima
    não dispara; superar só depois da 71 não dispara — EA (C++ sobre o shim) = referência Python rompz_o53c;
(3) EA ≡ referência em um mês de BTCUSD M15 (outubro) e nenhuma ordem nasce do ROMPZ."""
import os, re, sys, shutil, calendar, subprocess, tempfile
import numpy as np, pandas as pd, pytest

AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
REF51 = os.path.join(AQUI, "referencia_o51"); REF53 = os.path.join(AQUI, "referencia_o53")
D53C = os.path.join(AQUI, "dados_o53c"); D55 = os.path.join(AQUI, "dados_c27r55")
sys.path[:0] = [RAIZ, REF53, REF51]
import rompz_o53c as RZ, formacao_o44 as FO, romp_m15 as RM  # noqa: E402

B70, B71, B72 = 1794323700, 1794324600, 1794325500          # aberturas UTC (17:15, 17:30, 17:45 no servidor) das barras 70, 71, 72
SP = 1500


@pytest.fixture(scope="module")
def SIM():
    os.environ["BT_CARD_TESTE_USER"] = "u-master"
    import api as A
    from test_o53_lateral_r1 import _traduzir
    tmp = tempfile.mkdtemp()
    for f in ("mt5shim.h", "main.cpp"):
        shutil.copy(os.path.join(REF53, "shim", f), tmp)
    assert 'BTLAT_VERSAO "lateral-r1.2 (O53-C)"' in A._BT_LATERAL_R0_MQL5
    _traduzir(A._BT_LATERAL_R0_MQL5, os.path.join(tmp, "ea.cpp"))
    r = subprocess.run(["g++", "-std=c++17", "-O2", "-o", os.path.join(tmp, "sim"), os.path.join(tmp, "main.cpp")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    return os.path.join(tmp, "sim"), tmp


def _ler(arq):
    d = pd.read_csv(arq, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
    d["ep"] = [calendar.timegm(x.timetuple()) for x in pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")]
    return d


def _gravar(d, arq):
    import datetime as dt
    with open(arq, "w") as f:
        f.write("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n")
        for e, o, h, l, c in zip(d.ep, d.open, d.high, d.low, d.close):
            f.write(dt.datetime.fromtimestamp(int(e), dt.timezone.utc).strftime("%Y.%m.%d\t%H:%M:%S") + f"\t{o:.2f}\t{h:.2f}\t{l:.2f}\t{c:.2f}\n")


def _rodar(sim, f15, f1, fh, ini):
    out = subprocess.run([sim, "15", f15, f1, str(ini), str(SP), fh], capture_output=True, text=True).stdout.split("\n")
    ev = [dict(p.split("=", 1) for p in l.split("|")[1:] if "=" in p) for l in out if l.startswith("EVT|")]
    ea = [(e["ev"], e["sinal"], e.get("gatilho"), e.get("t"), e.get("bid"), e.get("resultado"), e.get("espaco_passa")) for e in ev if e.get("ev", "").startswith("rompz")]
    py = [(e["ev"], e["sinal"], None if e["ev"] == "rompz_expirado" else f'{e["gatilho"]:.2f}', str(e["t"]) if "t" in e else None,
           f'{e["bid"]:.2f}' if "bid" in e else None, e.get("resultado"), e.get("espaco_passa"))
          for e in RZ.rodar(_ler(f15), _ler(fh), _ler(f1), ini, SP * 0.01)]
    assert ea == py, (ea, py)                                                    # EA no shim = referência Python, evento a evento
    assert all(e.get("modo") == "SOMBRA - nenhuma ordem" for e in ev if e.get("ev", "").startswith("rompz"))
    return ev, out


def _caso(tmp, nome, barra71_m1, barra71_m15, barra72_aber=None):
    """copia os dados reais de 10/11 e troca só a barra 71 (M1 e M15) — e, se pedido, a abertura da 72."""
    m15, m1 = _ler(os.path.join(D53C, "BTCUSD_M15_20261110.csv")), _ler(os.path.join(D53C, "BTCUSD_M1_20261110.csv"))
    k = m1.ep.between(B71, B72 - 1)
    for col, v in zip(("open", "high", "low", "close"), np.array(barra71_m1, float).T): m1.loc[k, col] = v
    m15.loc[m15.ep == B71, ["open", "high", "low", "close"]] = barra71_m15
    f15, f1 = os.path.join(tmp, f"{nome}_m15.csv"), os.path.join(tmp, f"{nome}_m1.csv"); _gravar(m15, f15); _gravar(m1, f1)
    return f15, f1


def test_1_r0_do_grafico_falha_na_caixa_na_barra_70(SIM):
    sim, _ = SIM
    ev, out = _rodar(sim, *(os.path.join(D53C, f"BTCUSD_{x}_20261110.csv") for x in ("M15", "M1", "H1")), B70 - 900 * 3)
    b70 = [e for e in ev if e.get("ev") == "barra" and e.get("t") == str(B70)][0]
    assert b70["r0_venda"] == "caixa: amplitude 1402.52 > 3 ATR 1013.22" and b70["gatilho"] == "nenhum"
    assert not any(e.get("ev") == "gatilho_armado" for e in ev) and not any(l.startswith("ORDEM") for l in out)
    # mesma conta na referência O44 (a R0 congelada): nenhuma formação na barra 70
    m15 = _ler(os.path.join(D53C, "BTCUSD_M15_20261110.csv")); b = int(np.nonzero(m15.ep.values == B70)[0][0])
    A = RM.atr_wilder(m15.high, m15.low, m15.close); T = FO.tk
    h, l, c = T(m15.high.values), T(m15.low.values), T(m15.close.values)
    assert FO.detectar_venda(l, h, c, A, b) is None
    amp = (h[b - 12:b].max() - l[b - 12:b].min()) * 0.01
    assert round(amp, 2) == 1402.52 and round(3 * A[b - 1], 2) == 1013.22


def test_2_rompz_tres_casos_da_barra_71(SIM):
    sim, tmp = SIM
    fh = os.path.join(D53C, "BTCUSD_H1_20261110.csv")
    # (a) dados reais: a 70 fecha abaixo dos suportes 74009,30–74070,81 e 74041,89–74115,18; gatilho 73956,78; o 1º tick abaixo cai na 71
    ev, out = _rodar(sim, os.path.join(D53C, "BTCUSD_M15_20261110.csv"), os.path.join(D53C, "BTCUSD_M1_20261110.csv"), fh, B70 - 900 * 3)
    arm = [e for e in ev if e.get("ev") == "rompz_armado" and e["sinal"] == f"ZV-{B70}"][0]
    assert arm["gatilho"] == "73956.78" and arm["extremo"] == "73956.79" and arm["zonas"] == "74009.30-74070.81;74041.89-74115.18"
    assert (int(arm["valido_de"]), int(arm["valido_ate"])) == (B71, B72)
    dis = [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{B70}"]
    assert len(dis) == 1 and B71 <= int(dis[0]["t"]) < B72 and float(dis[0]["bid"]) <= 73956.78
    assert not any(l.startswith("ORDEM") for l in out)                          # sombra: nenhuma ordem
    # (b) a 71 só TOCA a mínima da 70 (73956,79) e não passa: não dispara; expira como "toque sem superação"
    m1b = [(73990.0, 74010.0, 73970.0, 73985.0)] * 15; m1b[3] = (73985.0, 73990.0, 73956.79, 73980.0)
    f15, f1 = _caso(tmp, "toque", m1b, (73990.0, 74010.0, 73956.79, 73980.0))
    ev, out = _rodar(sim, f15, f1, fh, B70 - 900 * 3)
    assert not [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{B70}"]
    assert [e["resultado"] for e in ev if e.get("ev") == "rompz_expirado" and e["sinal"] == f"ZV-{B70}"] == ["toque sem superacao"]
    # (c) a 71 fica acima do gatilho e volta para dentro do suporte; o preço só passa de 73956,78 na 72: não dispara
    m1c = [(74030.0, 74060.0, 73990.0, 74040.0)] * 15; m1c[5] = (74040.0, 74050.0, 73960.0, 74045.0)
    f15, f1 = _caso(tmp, "depois", m1c, (73995.04, 74060.0, 73960.0, 74045.0))
    ev, out = _rodar(sim, f15, f1, fh, B70 - 900 * 3)
    assert not [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{B70}"]
    assert [e["resultado"] for e in ev if e.get("ev") == "rompz_expirado" and e["sinal"] == f"ZV-{B70}"] == ["nao alcancou"]
    assert _ler(f1).query(f"ep >= {B72}").low.min() < 73956.78                 # o preço passou, mas só depois da 71


def test_3_ea_igual_referencia_em_outubro_e_sem_ordem_do_rompz(SIM):
    sim, _ = SIM
    f15, f1, fh = (os.path.join(D55, f"BTCUSD_{x}_202610.csv") for x in ("M15", "M1", "H1"))
    b, m1 = _ler(f15), _ler(f1); ini = int(max(b.ep.iloc[0] + 29 * 900, m1.ep.iloc[0]))
    ev, out = _rodar(sim, f15, f1, fh, ini)
    kinds = [e["ev"] for e in ev if e.get("ev", "").startswith("rompz")]
    assert kinds.count("rompz_armado") >= 20 and kinds.count("rompz_disparo") >= 10 and "rompz_expirado" in kinds
    assert all(e.get("r0_venda") and e.get("r0_compra") for e in ev if e.get("ev") == "barra")
    # as ordens são só as da R1 (mesma contagem de gatilhos armados → entradas); ROMPZ nunca chama Buy/Sell
    n_ent = sum(e.get("ev") == "entrada" for e in ev); assert sum(l.startswith("ORDEM") for l in out) == n_ent


def test_4_trilha_no_diagnostico_geral_e_pdf():
    """a seção 5 do Diagnóstico geral da LM monta a trilha barra 70 → gatilho → barra 71 → ordem/bloqueio a partir do que está gravado."""
    import datetime as dt, validacao_o53 as V
    from zoneinfo import ZoneInfo
    from test_o53_lateral_r1 import _SB
    iso = lambda e: dt.datetime.fromtimestamp(int(e), dt.timezone.utc).isoformat()
    def linhas(tf, x):
        return [{"simbolo": "BTCUSD", "tf": tf, "abertura_utc": iso(e), "o": o, "h": h, "l": l, "c": c, "fechado": True, "ultimo_visto_utc": "x"}
                for e, o, h, l, c in zip(x.ep, x.open, x.high, x.low, x.close)]
    m15, m1, h1 = (_ler(os.path.join(D53C, f"BTCUSD_{x}_20261110.csv")) for x in ("M15", "M1", "H1"))
    # leitura contínua original da LM (auditoria_leituras, 10/11): a 1ª leitura que descreve a barra 70 saiu às 15:30:39 UTC
    lm = [{"bot_id": 15, "ts": "2026-11-10T15:15:38+00:00", "estrutura_por_tf": {"M15": {"barra_corretora": "2026-11-10 17:00:00", "ultimo_fundo": 73513.61,
                                                                                      "localizacao": "na_resistencia", "eventos": ["sacudida_topo"]}}},
          {"bot_id": 15, "ts": "2026-11-10T15:30:39+00:00", "estrutura_por_tf": {"M15": {"barra_corretora": "2026-11-10 17:15:00", "ultimo_fundo": 73513.61,
                                                                                      "localizacao": "meio_da_faixa", "eventos": ["sacudida_topo", "rompimento_pendente(por_barra)"]}}}]
    sb = _SB({"auditoria_candles": linhas("M15", m15) + linhas("M1", m1) + linhas("H1", h1), "auditoria_leituras": lm, "agente_eventos": [], "babymachine_operacoes": []})
    de, ate = dt.datetime(2026, 11, 10, 14, 0, tzinfo=dt.timezone.utc), dt.datetime(2026, 11, 10, 16, 0, tzinfo=dt.timezone.utc)
    T = V.trilha_rompz(sb, {"id": 15, "simbolo": "BTCUSD", "magic_number": 138448864, "user_id": "u"}, "M15", de, ate, ZoneInfo("Europe/Kyiv"))
    assert T["situacao"] == "ok"
    x = [l for l in T["linhas"] if l["id"] == f"ZV-{B70}"][0]
    assert (x["n_barra_dia"], x["n_barra_seguinte"], x["gatilho"], x["extremo"]) == (70, 71, 73956.78, 73956.79)
    assert x["r0_na_barra"] == "caixa: amplitude 1402.52 > 3 ATR 1013.22"
    assert x["resultado_replay"] == "disparo" and x["primeiro_minuto_alem"][11:16] == "17:30" and x["abriu_alem_do_gatilho"] is False
    assert x["motivo_espaco"] == "espaço insuficiente" and x["ordem"] == "nenhuma ordem na barra seguinte" and x["ea"].startswith("sem evidência")
    assert x["lm_leu_a_barra_em"].endswith("17:30:39") and x["lm_registra_suporte_rompido"] is False
    assert x["R_sombra"] is not None and x["stop"] > x["preco_disparo"]
    j = [j for j in T["janelas"] if "· barra 70 (" in j["titulo"]][0]
    assert "DEIXOU PASSAR" in j["titulo"] and V.grafico_png(j)[:4] == b"\x89PNG"
    import diagnostico_lm_o50 as D, json
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    d = FPDF(); d.set_auto_page_break(True, margin=14); d.add_page()
    def p(t, b=False, tam=8): d.set_font("Helvetica", "B" if b else "", tam); d.multi_cell(0, 4, D._t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    def tab(cab, linhas, larg, lim=90): [p(" | ".join(D._t(x, 30) for x in l)) for l in [cab] + list(linhas)]
    S5 = {"titulo": "5.", "estados": {}, "bots": [{"bot": "ML New Bot 01", "simbolo": "BTCUSD", "tf": "M15", "bot_id": 15, "ea_registrado_na_plataforma": "R0 (O51)",
                                                     "observado": {"operacoes": []}, "replay": {"situacao": "x"}, "pivos": {"situacao": "x"}, "janelas": [],
                                                     "rompz": json.loads(json.dumps(T, default=str))}]}
    D._pdf_secao_5(d, S5, lambda t: p(t, True, 12), lambda t: p(t, True, 9), p, lambda ps: [p(f"{k}: {v}") for k, v in ps], tab, 186)
    assert bytes(d.output())[:4] == b"%PDF"
