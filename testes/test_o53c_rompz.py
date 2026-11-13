"""ORDEM 053-C/053-D — Bot 01 (BTCUSD M15), barras 70–71 de 10/11/2026.
(1) a R0 do gráfico falha na 1ª condição (caixa de 12 barras > 3 ATR) na barra 70 — EA e referência O44 dizem o mesmo;
(2) ROMPZ (EA lateral-r1.2 O53-D): rompimento de zona O39 JÁ CONFIRMADA → gatilho na mínima/máxima → SINAL só na barra seguinte; a ordem é
    autorizada à parte (filtro 1,0 R). Casos: 70–71 real (sinal disparado; bloqueado por falta de espaço), toque sem superação, superação após
    a expiração, compra espelhada, zona ainda não confirmada — EA (C++ sobre o shim) = referência Python rompz_o53c, evento a evento;
(3) EA ≡ referência em outubro com ENVIO LIGADO (entradas de caixa + ROMPZ, saídas, stop) e, com envio DESLIGADO, nenhuma ordem;
(4) Diagnóstico geral da LM: trilha zona → fechamento da 70 → mínima → superação na 71 → próximo suporte → decisão; PDF."""
import os, re, sys, shutil, calendar, subprocess, tempfile
import numpy as np, pandas as pd, pytest

AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
REF51 = os.path.join(AQUI, "referencia_o51"); REF53 = os.path.join(AQUI, "referencia_o53")
D53C = os.path.join(AQUI, "dados_o53c"); D55 = os.path.join(AQUI, "dados_c27r55")
sys.path[:0] = [RAIZ, REF53, REF51, AQUI]
import rompz_o53c as RZ, formacao_o44 as FO, romp_m15 as RM  # noqa: E402

B70, B71, B72 = 1794323700, 1794324600, 1794325500          # aberturas UTC (17:15, 17:30, 17:45 no servidor) das barras 70, 71, 72
SP = 1500


@pytest.fixture(scope="module")
def A():
    os.environ["BT_CARD_TESTE_USER"] = "u-master"
    import api as A
    assert 'BTLAT_VERSAO "lateral-r1.4 (O56)"' in A._BT_LATERAL_R0_MQL5
    return A


_SIMS = {}


def _sim(A, **cfg):
    from test_o53_lateral_r1 import _traduzir, _cfg
    k = tuple(sorted(cfg.items()))
    if k not in _SIMS:
        tmp = tempfile.mkdtemp()
        for f in ("mt5shim.h", "main.cpp"):
            shutil.copy(os.path.join(REF53, "shim", f), tmp)
        _traduzir(_cfg(A._BT_LATERAL_R0_MQL5, **{"InpEntradaCompz": "false", "InpEnviarOrdens": "false", "InpExaustao": "false", **cfg}), os.path.join(tmp, "ea.cpp"))   # O55: COMPZ desligada nos testes da ROMPZ
        r = subprocess.run(["g++", "-std=c++17", "-O2", "-o", os.path.join(tmp, "sim"), os.path.join(tmp, "main.cpp")], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-1500:]
        _SIMS[k] = (os.path.join(tmp, "sim"), tmp)
    return _SIMS[k]


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


def _rodar(sim, f15, f1, fh, ini, enviar=False, caixa=True, **kw):
    """roda o EA no shim e a referência; exige igualdade evento a evento do ROMPZ (armado, disparo com decisão, expirado)."""
    out = subprocess.run([sim, "15", f15, f1, str(ini), str(SP), fh], capture_output=True, text=True).stdout.split("\n")
    ev = [dict(p.split("=", 1) for p in l.split("|")[1:] if "=" in p) for l in out if l.startswith("EVT|")]
    ea = [(e["ev"], e["sinal"], e.get("gatilho"), e.get("t"), e.get("bid"), e.get("resultado"), e.get("decisao")) for e in ev if e.get("ev", "").startswith("rompz")]
    I = RZ.rodar(_ler(f15), _ler(fh), _ler(f1), ini, SP * 0.01, enviar=enviar, caixa=caixa, **kw)
    py = [(e["tipo"], e["sinal"], None if e["tipo"] == "rompz_expirado" else f'{e["gatilho"]:.2f}', str(e["t_ms"] // 1000) if e["tipo"] == "rompz_disparo" else None,
           f'{e["bid"]:.2f}' if "bid" in e else None, e.get("resultado"), e.get("decisao")) for e in I.eventos if e["tipo"].startswith("rompz")]
    assert ea == py, (ea, py)
    return ev, out, I


def _caso(tmp, nome, barra71_m1, barra71_m15):
    """copia os dados reais de 10/11 e troca só a barra 71 (M1 e M15)."""
    m15, m1 = _ler(os.path.join(D53C, "BTCUSD_M15_20261110.csv")), _ler(os.path.join(D53C, "BTCUSD_M1_20261110.csv"))
    k = m1.ep.between(B71, B72 - 1)
    for col, v in zip(("open", "high", "low", "close"), np.array(barra71_m1, float).T): m1.loc[k, col] = v
    m15.loc[m15.ep == B71, ["open", "high", "low", "close"]] = barra71_m15
    f15, f1 = os.path.join(tmp, f"{nome}_m15.csv"), os.path.join(tmp, f"{nome}_m1.csv"); _gravar(m15, f15); _gravar(m1, f1)
    return f15, f1


ARQ = lambda x: os.path.join(D53C, f"BTCUSD_{x}_20261110.csv")


def test_1_r0_do_grafico_falha_na_caixa_na_barra_70(A):
    sim, _ = _sim(A)
    ev, out, _ = _rodar(sim, ARQ("M15"), ARQ("M1"), ARQ("H1"), B70 - 900 * 3)
    b70 = [e for e in ev if e.get("ev") == "barra" and e.get("t") == str(B70)][0]
    assert b70["r0_venda"] == "caixa: amplitude 1402.52 > 3 ATR 1013.22" and b70["gatilho"] == "nenhum"
    assert not any(e.get("ev") == "gatilho_armado" for e in ev) and not any(l.startswith("ORDEM") for l in out)
    m15 = _ler(ARQ("M15")); b = int(np.nonzero(m15.ep.values == B70)[0][0])
    At = RM.atr_wilder(m15.high, m15.low, m15.close); T = FO.tk
    h, l, c = T(m15.high.values), T(m15.low.values), T(m15.close.values)
    assert FO.detectar_venda(l, h, c, At, b) is None
    assert round((h[b - 12:b].max() - l[b - 12:b].min()) * 0.01, 2) == 1402.52 and round(3 * At[b - 1], 2) == 1013.22


def test_2_barras_70_71_sinal_disparado_e_bloqueado_por_falta_de_espaco(A):
    sim, _ = _sim(A)
    ev, out, I = _rodar(sim, ARQ("M15"), ARQ("M1"), ARQ("H1"), B70 - 900 * 3)
    arm = [e for e in ev if e.get("ev") == "rompz_armado" and e["sinal"] == f"ZV-{B70}"][0]
    # as duas zonas de suporte foram confirmadas ANTES da barra 70 (horário de confirmação ≤ abertura da 70)
    zs = [z.split("@conf=") for z in arm["zonas"].split(";")]
    assert [z[0] for z in zs] == ["74009.30-74070.81", "74041.89-74115.18"] and all(int(z[1]) <= B70 for z in zs)
    assert arm["gatilho"] == "73956.78" and arm["extremo"] == "73956.79" and (int(arm["valido_de"]), int(arm["valido_ate"])) == (B71, B72)
    d = [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{B70}"][0]
    assert B71 <= int(d["t"]) < B72 and float(d["bid"]) <= 73956.78
    assert d["decisao"] == "sinal disparado; bloqueado por falta de espaco" and d["sem_filtro_sombra"] == "entraria (sombra)"
    # o cálculo: próximo suporte H1 73642,49–73774,81; d = E − topo; líquido = d − spread; R = 2 ATR
    E, topo, sp, R = float(d["E"]), float(d["zona_topo"]), float(d["spread"]), float(d["R"])
    assert d["zona_tf"] == "H1" and d["zona_base"] == "73642.49" and abs(float(d["d"]) - (E - topo)) < 0.011
    assert abs(float(d["espaco_R"]) - (E - topo - sp) / R) < 0.001 and float(d["espaco_R"]) < 0.25
    assert not any(l.startswith("ORDEM") for l in out) and not any(e.get("ev") == "ordem" for e in ev)
    # sem filtro (só sombra): a referência abre a posição; com filtro, não
    I0 = RZ.rodar(_ler(ARQ("M15")), _ler(ARQ("H1")), _ler(ARQ("M1")), B70 - 900 * 3, SP * 0.01, filtro_rompz=False, caixa=False)
    assert I0.pos is not None and I0.pos["sinal"] == f"ZV-{B70}" and I.pos is None


def test_3_controles_toque_expiracao_compra_espelhada_e_zona_nao_confirmada(A):
    sim, tmp = _sim(A)
    # (a) a 71 só TOCA a mínima da 70 (73956,79): não dispara; expira como "toque sem superação"
    m1b = [(73990.0, 74010.0, 73970.0, 73985.0)] * 15; m1b[3] = (73985.0, 73990.0, 73956.79, 73980.0)
    f15, f1 = _caso(tmp, "toque", m1b, (73990.0, 74010.0, 73956.79, 73980.0))
    ev, _, _ = _rodar(sim, f15, f1, ARQ("H1"), B70 - 900 * 3)
    assert not [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{B70}"]
    assert [e["resultado"] for e in ev if e.get("ev") == "rompz_expirado" and e["sinal"] == f"ZV-{B70}"] == ["toque sem superacao"]
    # (b) a 71 fica acima do gatilho; o preço só passa de 73956,78 na 72 (depois da expiração): não dispara
    m1c = [(74030.0, 74060.0, 73990.0, 74040.0)] * 15; m1c[5] = (74040.0, 74050.0, 73960.0, 74045.0)
    f15, f1 = _caso(tmp, "depois", m1c, (73995.04, 74060.0, 73960.0, 74045.0))
    ev, _, _ = _rodar(sim, f15, f1, ARQ("H1"), B70 - 900 * 3)
    assert not [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{B70}"]
    assert [e["resultado"] for e in ev if e.get("ev") == "rompz_expirado" and e["sinal"] == f"ZV-{B70}"] == ["nao alcancou"]
    assert _ler(f1).query(f"ep >= {B72}").low.min() < 73956.78
    # (c) compra espelhada: preço p → 150000 − p (máxima ↔ mínima); resistência rompida na 70, gatilho na máxima + 1 tick, disparo na 71
    K = 150000.0
    for x, nome in (("M15", "esp15"), ("M1", "esp1"), ("H1", "esph")):
        d = _ler(ARQ(x)); d2 = d.copy(); d2["open"], d2["close"], d2["high"], d2["low"] = K - d.open, K - d.close, K - d.low, K - d.high
        _gravar(d2, os.path.join(tmp, nome + ".csv"))
    ev, _, _ = _rodar(sim, *(os.path.join(tmp, n + ".csv") for n in ("esp15", "esp1", "esph")), B70 - 900 * 3)
    arm = [e for e in ev if e.get("ev") == "rompz_armado" and e["sinal"] == f"ZC-{B70}"][0]
    assert arm["lado"] == "1" and arm["gatilho"] == f"{K - 73956.79 + 0.01:.2f}"
    d = [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZC-{B70}"][0]
    assert B71 <= int(d["t"]) < B72 and float(d["bid"]) >= K - 73956.79 + 0.01 and d["decisao"].startswith("sinal disparado")
    # (d) zona ainda NÃO confirmada: o fundo da barra 50 (990) só seria confirmado no fechamento da 52; a 52 rompe abaixo dele → sem sinal.
    #     Controle: com o fundo confirmado (52 fica acima) e o fechamento abaixo na 53, o sinal arma e dispara na 54.
    def serie(nao_confirmada):
        t0 = 1793000700; rows = []
        for i in range(60):
            o = 1000.0 + (1.0 if i % 2 else -1.0); rows.append([t0 + 900 * i, o, o + 2.0 + (i % 3) * 0.5, o - 2.0 - (i % 2) * 0.5, o + (0.5 if i % 2 else -0.5)])
        rows[50][1:] = [996.0, 999.0, 990.0, 997.0]
        rows[51][1:] = [997.0, 1000.0, 995.0, 998.0]
        rows[52][1:] = ([998.0, 999.0, 984.0, 985.0] if nao_confirmada else [998.0, 1001.0, 995.5, 999.0])
        rows[53][1:] = ([985.0, 986.0, 980.0, 981.0] if nao_confirmada else [999.0, 999.5, 986.0, 987.0])
        rows[54][1:] = [981.0 if nao_confirmada else 987.0, 988.0, 975.0, 977.0]
        m15 = pd.DataFrame(rows, columns=["ep", "open", "high", "low", "close"]); m1 = []
        for e, o, h, l, c in rows:
            for j in range(15):
                v = o if j == 0 else l if j == 6 else h if j == 3 else c
                m1.append([e + 60 * j, v, v, v, v])
        m1 = pd.DataFrame(m1, columns=["ep", "open", "high", "low", "close"])
        h1 = m15.groupby(m15.ep // 3600 * 3600).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")).reset_index()
        fs = [os.path.join(tmp, f"zn{int(nao_confirmada)}_{k}.csv") for k in ("m15", "m1", "h1")]
        for df_, f in zip((m15, m1, h1), fs): _gravar(df_, f)
        return fs, t0
    fs, t0 = serie(True)
    ev, _, _ = _rodar(sim, *fs, t0 + 900 * 35)
    assert not [e for e in ev if e.get("ev") == "rompz_armado" and int(e["barra_rompimento"]) >= t0 + 900 * 50]
    fs, t0 = serie(False)
    ev, _, _ = _rodar(sim, *fs, t0 + 900 * 35)
    arm = [e for e in ev if e.get("ev") == "rompz_armado" and e["sinal"] == f"ZV-{t0 + 900 * 53}"]
    assert arm and arm[0]["zonas"].startswith("990.00-") and int(arm[0]["zonas"].split("@conf=")[1]) == t0 + 900 * 53
    d = [e for e in ev if e.get("ev") == "rompz_disparo" and e["sinal"] == f"ZV-{t0 + 900 * 53}"][0]
    assert t0 + 900 * 54 <= int(d["t"]) < t0 + 900 * 55
    assert d["decisao"] == "sinal disparado; bloqueado: distancia nao calculavel (historico insuficiente)" and d.get("historico", "").startswith("insuficiente")


def test_4_ea_igual_referencia_com_envio_e_sem_envio(A):
    f15, f1, fh = (os.path.join(D55, f"BTCUSD_{x}_202610.csv") for x in ("M15", "M1", "H1"))
    b, m1 = _ler(f15), _ler(f1); ini = int(max(b.ep.iloc[0] + 29 * 900, m1.ep.iloc[0]))
    # envio LIGADO: entradas de caixa + ROMPZ autorizadas, saídas e stop iguais à referência
    # (nesta amostra o filtro bloqueia todos os sinais; para provar a execução, o filtro do ROMPZ é desligado AQUI — no Bot 01 ele fica ligado)
    sim, _ = _sim(A, InpEnviarOrdens="true", InpRompZFiltro="false")
    ev, out, I = _rodar(sim, f15, f1, fh, ini, enviar=True, filtro_rompz=False)
    ea_e = [(int(x.split("|")[2]), x.split("|")[1], float(x.split("|")[3])) for x in out if x.startswith("ORDEM")]
    ea_s = [(int(x.split("|")[2]), x.split("|")[1], float(x.split("|")[3])) for x in out if x.startswith("FECHA")]
    py_e = [(e["t_ms"] // 1000, "buy" if e["lado"] > 0 else "sell", round(e["preco"], 2)) for e in I.eventos if e["tipo"] == "entrada_virtual"]
    py_s = [(e["t_ms"] // 1000, "stop" if e["motivo"].startswith("stop") else "cmd", round(e["preco"], 2)) for e in I.eventos if e["tipo"] == "saida_virtual"]
    assert ea_e == py_e and ea_s == py_s and len(ea_e) >= 5
    rz = [e for e in ev if e.get("ev") == "ordem" and e.get("entrada") == "rompz"]
    assert rz and all(e["decisao"].startswith("sinal disparado") for e in ev if e.get("ev") == "rompz_disparo")
    assert sum(1 for e in ev if e.get("ev") == "rompz_disparo" and e["posicao_aberta"] == "nao") == len(rz)
    # envio DESLIGADO (validação em sombra): mesmos sinais, nenhuma ordem
    sim0, _ = _sim(A, InpRompZFiltro="false")
    ev0, out0, _ = _rodar(sim0, f15, f1, fh, ini, enviar=False, filtro_rompz=False)
    assert not any(l.startswith(("ORDEM", "FECHA|cmd")) for l in out0)
    assert all(e.get("ev") != "ordem" or e.get("retcode") is None for e in ev0)
    assert any(e.get("ev") == "ordem" for e in ev0) and all(e["envio"].startswith("nao enviada: envio desligado") for e in ev0 if e.get("ev") == "ordem")
    inicio = [e for e in ev0 if e.get("ev") == "inicio"][0]
    assert inicio["versao"] == "lateral-r1.4 (O56)" and inicio["envio_ordens"] == "desligado (sombra)" and inicio["tf"] == "M15" and inicio["rompz"] == "sim"


def test_5_trilha_no_diagnostico_geral_e_pdf():
    """a seção 5 do Diagnóstico geral da LM monta zona → fechamento da 70 → mínima → superação na 71 → próximo suporte → decisão."""
    import datetime as dt, json, validacao_o53 as V
    from zoneinfo import ZoneInfo
    from test_o53_lateral_r1 import _SB
    iso = lambda e: dt.datetime.fromtimestamp(int(e), dt.timezone.utc).isoformat()
    def linhas(tf, x):
        return [{"simbolo": "BTCUSD", "tf": tf, "abertura_utc": iso(e), "o": o, "h": h, "l": l, "c": c, "fechado": True, "ultimo_visto_utc": "x"}
                for e, o, h, l, c in zip(x.ep, x.open, x.high, x.low, x.close)]
    m15, m1, h1 = (_ler(ARQ(x)) for x in ("M15", "M1", "H1"))
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
    assert all(z["confirmada_antes"] for z in x["zonas_rompidas"])
    assert x["r0_na_barra"] == "caixa: amplitude 1402.52 > 3 ATR 1013.22"
    assert x["resultado_replay"] == "disparo" and x["primeiro_minuto_alem"][11:16] == "17:30" and x["abriu_alem_do_gatilho"] is False
    assert x["decisao_com_filtro"] == "sinal disparado; bloqueado por falta de espaço" and x["sem_filtro_sombra"] == "entraria (sombra)"
    assert x["calculo_espaco"]["zona"]["tf"] == "H1" and x["calculo_espaco"]["espaco_R"] < 0.25 and "formula" in x["calculo_espaco"]
    assert x["ordem"] == "nenhuma ordem na barra seguinte" and x["ea_no_terminal"].startswith("sem evidência")
    assert x["lm_leu_a_barra_em"].endswith("17:30:39") and x["lm_registra_suporte_rompido"] is False
    L = x["lado_a_lado"]
    assert L["R0 do gráfico"].startswith("não armou") and L["R1.2 com filtro"].startswith("sinal disparado") and L["R1.2 sem filtro (sombra)"].startswith("entrada simulada")
    j = [j for j in T["janelas"] if "· barra 70 (" in j["titulo"]][0]
    assert "bloqueado por falta de espaço" in j["titulo"] and V.grafico_png(j)[:4] == b"\x89PNG"
    import diagnostico_lm_o50 as D
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
