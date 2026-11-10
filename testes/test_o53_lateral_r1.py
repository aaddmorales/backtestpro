"""ORDEM 053 — lateral-r1: (1) o EA gerado reproduz TICK A TICK o motor de referência ao_vivo_o53 (entradas, saídas, motivo corte/canal,
bloqueios do filtro de espaço com o motivo, avaliação da reversão em sombra), em 5 timeframes com dados reais BTCUSD; (2) com filtro e corte
desligados o motor O53 é idêntico ao O47 (a R0 não mudou); (3) o gerador entrega o EA r1 com a disciplina neutra; (4) evento de fechamento
duplicado do mesmo ticket não vira órfã; (5) a seção 5 do Diagnóstico geral da LM monta replay × sombra × observado e o PDF sai com os gráficos."""
import os, re, sys, json, shutil, calendar, subprocess, tempfile, datetime as _dt
import numpy as np, pandas as pd, pytest

AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
REF51 = os.path.join(AQUI, "referencia_o51"); REF53 = os.path.join(AQUI, "referencia_o53"); DADOS = os.path.join(AQUI, "dados_c27r55")
sys.path[:0] = [RAIZ, REF53, REF51]
import ao_vivo_o53 as R1, ao_vivo_o47 as AV  # noqa: E402

SP = 1500


@pytest.fixture(scope="module")
def A():
    os.environ["BT_CARD_TESTE_USER"] = "u-master"
    import api as A
    A._mq5_cache_buscar = lambda h: None; A._mq5_cache_guardar = lambda h, t: True
    return A


def _ler(arq):
    d = pd.read_csv(arq, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
    d["ep"] = [calendar.timegm(x.timetuple()) for x in pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")]
    return d


def _traduzir(mq5, dst):
    s = mq5.replace("#include <Trade\\Trade.mqh>", '#include "mt5shim.h"')
    s = re.sub(r"^input\s+", "static ", s, flags=re.M)
    s = re.sub(r"const (double|long|string|MqlRates) &(\w+)\[\]", r"const std::vector<\1>& \2", s)
    s = re.sub(r"(?<![\w<])(double|long|string) &(\w+)\[\]", r"std::vector<\1>& \2", s)
    s = re.sub(r"^(\s*)(double|long|string|MqlRates|int|bool)\s+((?:\w+\[\],?\s*)+);",
               lambda m: m.group(1) + f"std::vector<{m.group(2)}> " + ",".join(n.strip().rstrip("[]") for n in m.group(3).split(",")) + ";", s, flags=re.M)
    open(dst, "w").write(s)


TFS = ((15, "M15", "M15"), (5, "M5", "T5"), (1, "M1", "T1"), (30, "M30", "M30"), (60, "H1", "H1"))


def test_1_ea_tick_a_tick_igual_ao_motor_o53(A):
    for k in ("T1", "T5"):
        R1.TF_MIN.setdefault(k, int(k[1:]))
    tmp = tempfile.mkdtemp()
    for f in ("mt5shim.h", "main.cpp"):
        shutil.copy(os.path.join(REF53, "shim", f), tmp)
    _traduzir(A._BT_LATERAL_R0_MQL5, os.path.join(tmp, "ea.cpp"))
    r = subprocess.run(["g++", "-std=c++17", "-O2", "-o", os.path.join(tmp, "sim"), os.path.join(tmp, "main.cpp")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    m1f = os.path.join(DADOS, "BTCUSD_M1_202610.csv"); h1f = os.path.join(DADOS, "BTCUSD_H1_202610.csv")
    m1, h1 = _ler(m1f), _ler(h1f); tot = {"entradas": 0, "bloqueios": 0, "cortes": 0, "reversoes": 0}
    for tf, arq, nome in TFS:
        f = os.path.join(DADOS, f"BTCUSD_{arq}_202610.csv"); bars = _ler(f); dur = tf * 60
        ini = int(max(bars.ep.iloc[0] + 29 * dur, m1.ep.iloc[0]))
        out = subprocess.run([os.path.join(tmp, "sim"), str(tf), f, m1f, str(ini), str(SP), h1f], capture_output=True, text=True).stdout.split("\n")
        ev = [l.split("|") for l in out if l.startswith(("ORDEM", "FECHA"))]
        ea_e = [(int(x[2]), x[1], float(x[3]), float(x[4])) for x in ev if x[0] == "ORDEM"]; ea_s = [(int(x[2]), x[1], float(x[3])) for x in ev if x[0] == "FECHA"]
        lat = [dict(p.split("=", 1) for p in l.split("|")[1:] if "=" in p) for l in out if l.startswith("EVT|")]
        I = R1.rodar("BTCUSD", nome, bars, m1, h1 if nome != "H1" else None, ini, SP * 0.01)
        py_e = [(e["t_ms"] // 1000, "buy" if e["lado"] > 0 else "sell", round(e["preco"], 2), round(e["stop"], 2)) for e in I.eventos if e["tipo"] == "entrada_virtual"]
        py_s = [(e["t_ms"] // 1000, "stop" if e["motivo"].startswith("stop") else "cmd", round(e["preco"], 2)) for e in I.eventos if e["tipo"] == "saida_virtual"]
        assert len(ea_e) == len(py_e) and all(a[:3] == b[:3] and abs(a[3] - b[3]) <= 0.011 for a, b in zip(ea_e, py_e)), (tf, ea_e[:3], py_e[:3])
        assert ea_s == py_s, (tf, ea_s[:3], py_s[:3])
        assert [d["motivo"] for d in lat if d.get("ev") == "saida"] == ["corte estrutural" if e["motivo"] == "corte estrutural" else "canal"
                                                                         for e in I.eventos if e["tipo"] == "saida_decidida" and not e["sombra"]], tf
        assert [d["motivo"] for d in lat if d.get("ev") == "bloqueado_espaco"] == [e["motivo"].replace("ç", "c") for e in I.eventos if e["tipo"] == "bloqueado_espaco"], tf
        assert [d["passa"] for d in lat if d.get("ev") == "reversao_sombra"] == ["sim" if e["passa"] else "nao" for e in I.eventos if e["tipo"] == "reversao_sombra_avaliada"], tf
        assert sum(d.get("ev") == "gatilho_armado" for d in lat) == I.cont["gatilhos_armados"], tf
        # reconciliação: cada fechamento do EA é confirmado; o de stop aparece como fechamento externo com a razão
        assert sum(d.get("ev") == "fechamento_confirmado" for d in lat) + sum(d.get("ev") == "fechamento_externo" for d in lat) >= len(ea_s) - 1
        assert all(d.get("v") == "lateral-r1.2 (O53-C)" for d in lat)
        hist = [d for d in lat if d.get("ev") == "historico"]                          # o histórico do MT5 vai para a BabyMachine (replay)
        assert hist and all(len(d["barras"].split(";")) <= 60 for d in hist) and {d["tf"] for d in hist} == ({"H1"} if tf == 60 else {"M30", "H1"} if tf == 30 else {"M15", "H1"})
        tot["entradas"] += len(ea_e); tot["bloqueios"] += I.cont["bloq_espaco"] + I.cont["bloq_dentro_zona"]; tot["cortes"] += I.cont["saidas_corte"]; tot["reversoes"] += I.cont["rev_avaliadas"]
    assert tot["bloqueios"] >= 20 and tot["entradas"] >= 3 and tot["cortes"] >= 1 and tot["reversoes"] >= 1, tot


def test_2_sem_filtro_e_sem_corte_e_a_r0_da_o47():
    for tf, arq, nome in TFS[:4]:
        AV.TF_MIN.setdefault(nome, tf); R1.TF_MIN.setdefault(nome, tf)
        bars = _ler(os.path.join(DADOS, f"BTCUSD_{arq}_202610.csv")); m1 = _ler(os.path.join(DADOS, "BTCUSD_M1_202610.csv")); dur = tf * 60
        ini = int(max(bars.ep.iloc[0] + 29 * dur, m1.ep.iloc[0]))
        I = R1.rodar("BTCUSD", nome, bars, m1, None, ini, SP * 0.01, filtro=False, corte=False, reversao_sombra=False)
        J = AV.Instancia("BTCUSD", nome); J.ativo_desde_ms = 0; ult = None
        for b in m1.itertuples():
            up = b.close >= b.open; p1, p2 = (b.low, b.high) if up else (b.high, b.low)
            for px, dt in zip((b.open, p1, p2, b.close), (0, 15, 30, 59)):
                t = int(b.ep) + dt
                if t < ini:
                    continue
                t0 = (t // dur) * dur
                if t0 != ult:
                    f = bars[bars.ep + dur <= t]
                    if len(f) >= 29:
                        J.fecha_barra(pd.DataFrame({"t": pd.to_datetime(f.ep, unit="s"), "o": f.open, "h": f.high, "l": f.low, "c": f.close}).reset_index(drop=True)); ult = t0
                J.tick(t * 1000, round(px, 2), round(px + SP * 0.01, 2))
        assert [(round(o["entrada"], 2), round(o["saida"], 2), round(o["R"], 6)) for o in I.ops] == [(round(o["entrada"], 2), round(o["saida"], 2), round(o["R"], 6)) for o in J.ops], tf


def test_3_gerador_entrega_o_ea_r1(A):
    lat = A._gerar_mq5_de_codigo(A.ESTRATEGIA_LATERAL_R0["codigo"], {"magic": 99, "stop_loss": 0, "take_profit": 0, "ativo": "BTC/USD"})
    assert 'BTLAT_VERSAO "lateral-r1.2 (O53-C)"' in lat and "class CBTMem" in lat and "BTLatEspaco" in lat and "BTLatReconciliar" in lat
    assert re.search(r"input\s+\w+\s+InpBTAlvoRR\s*=\s*0\.0;", lat) and re.search(r"input\s+\w+\s+InpBTTrailingBarra\s*=\s*false;", lat)
    assert "void BTvGravarEvento(const string linha_evento)" in lat                       # o canal confiável da BabyMachine existe no EA instrumentado
    assert A._mq5_sanidade(lat)[0]
    A._mq5_cache_buscar = lambda h: {"mq5": lat.replace("lateral-r1.2 (O53-C)", "x")}         # cache antigo (R0) não pode voltar
    assert "lateral-r1.2 (O53-C)" in A._gerar_mq5_de_codigo(A.ESTRATEGIA_LATERAL_R0["codigo"], {"magic": 99, "stop_loss": 0, "take_profit": 0, "ativo": "BTC/USD"})
    A._mq5_cache_buscar = lambda h: None
    assert "8.33-o53-lateral-r1" in A.API_VERSAO


class _Q:
    def __init__(s, sb, nome):
        s.sb, s.nome, s.f, s.r, s.lim, s.desc, s.upd, s.ins = sb, nome, [], None, None, False, None, None

    def select(s, *a): return s
    def eq(s, k, v): s.f.append(("eq", k, v)); return s
    def gte(s, k, v): s.f.append(("gte", k, v)); return s
    def lte(s, k, v): s.f.append(("lte", k, v)); return s
    def lt(s, k, v): s.f.append(("lt", k, v)); return s
    def in_(s, k, v): s.f.append(("in", k, v)); return s
    def order(s, k, desc=False): s.desc = desc; s.ok = k; return s
    def limit(s, n): s.lim = n; return s
    def range(s, a, b): s.r = (a, b); return s
    def update(s, d): s.upd = d; return s
    def insert(s, d): s.ins = d; return s

    def _v(s, r, k):
        if "->>" in k:
            a, b = k.split("->>"); return str((r.get(a) or {}).get(b))
        return r.get(k)

    def execute(s):
        rows = list(s.sb.t.get(s.nome, []))
        for op, k, v in s.f:
            def ok(r):
                x = s._v(r, k)
                if op == "eq": return str(x) == str(v)
                if op == "in": return x in v
                if x is None: return False
                X, V = (pd.Timestamp(x), pd.Timestamp(v)) if isinstance(v, str) and "T" in v else (x, v)
                return X >= V if op == "gte" else X <= V if op == "lte" else X < V
            rows = [r for r in rows if ok(r)]
        if s.ins is not None:
            s.sb.log.append(("insert", s.nome, s.ins)); return type("R", (), {"data": [dict(s.ins, id=999)]})()
        if s.upd is not None:
            s.sb.log.append(("update", s.nome, s.upd, [r.get("id") for r in rows])); return type("R", (), {"data": rows})()
        if s.desc:
            rows = rows[::-1]
        if s.r:
            rows = rows[s.r[0]:s.r[1] + 1]
        if s.lim:
            rows = rows[:s.lim]
        return type("R", (), {"data": rows})()


class _SB:
    def __init__(s, t): s.t, s.log = t, []
    def table(s, n): return _Q(s, n)


def test_4_fechamento_duplicado_do_mesmo_ticket_nao_vira_orfa(A):
    sb = _SB({"babymachine_operacoes": [{"id": 118, "bot_id": 15, "status": "fechada", "decisao": {"ticket": "2071138432"}, "resultado": {"pnl_pts": -177.15}}]})
    A._bm_processar_fechamento(sb, {"id": 15, "user_id": "u"}, {"tipo": "fechado", "ticket": "2071138432", "simbolo": "BTCUSD", "deal": "1665279404", "razao": "expert"}, 1516)
    assert not any(x[0] == "insert" for x in sb.log)
    up = [x for x in sb.log if x[0] == "update"]
    assert up and up[0][3] == [118] and up[0][2]["resultado"]["confirmacao_mt5"]["razao"] == "expert"


def test_5_secao_5_do_diagnostico_e_pdf(A):
    import validacao_o53 as V, diagnostico_lm_o50 as D
    def linhas(tf, arq):
        d = _ler(os.path.join(DADOS, f"BTCUSD_{arq}_202610.csv"))
        return [{"simbolo": "BTCUSD", "tf": tf, "abertura_utc": _dt.datetime.fromtimestamp(int(e), _dt.timezone.utc).isoformat(), "o": o, "h": h, "l": l, "c": c, "fechado": True,
                 "ultimo_visto_utc": "2026-10-16T12:00:00+00:00"} for e, o, h, l, c in zip(d.ep, d.open, d.high, d.low, d.close)]
    cand = linhas("M1", "M1") + linhas("M15", "M15") + linhas("H1", "H1")
    sb = _SB({"auditoria_candles": cand, "conector_bots": [{"id": 15, "nome": "ML New Bot 01", "simbolo": "BTCUSD", "magic_number": 7, "user_id": "u", "bot_token": "t",
                                                            "config_operacional": {"timeframe_envio": "15m"}, "mq5_codigo": A._BT_LATERAL_R0_MQL5, "excluido": False}],
              "babymachine_operacoes": [], "agente_eventos": [], "conector_snapshots": []})
    de = _dt.datetime(2026, 10, 14, 0, 0, tzinfo=_dt.timezone.utc); ate = _dt.datetime(2026, 10, 16, 12, 0, tzinfo=_dt.timezone.utc)
    S5 = V.secao_5(sb, [15], de, ate, _dt.timezone.utc)
    b = S5["bots"][0]; R = b["replay"]
    assert R["situacao"] == "ok" and set(R["variantes"]) == {"R0 (antes)", "R1 (depois)", "só filtro", "só corte"}
    assert R["variantes"]["R1 (depois)"]["contadores"]["bloq_espaco"] + R["variantes"]["R1 (depois)"]["contadores"]["bloq_dentro_zona"] >= 1
    assert b["observado"]["sem_eventos_r1"] and "NÃO está confirmado no terminal" in b["observado"]["nota_sem_eventos"]
    assert any(j.get("velas") for j in b["janelas"]) and V.grafico_png(next(j for j in b["janelas"] if j.get("velas")))[:4] == b"\x89PNG"
    c = {"relatorio_id": "DIAG-20261016T120000Z-abcdef0123", "sha256_do_conteudo": "0" * 64, "secao_5": json.loads(json.dumps(S5, default=str))}
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    d = FPDF(); d.set_auto_page_break(True, margin=14); d.add_page()
    def p(t, b=False, tam=8): d.set_font("Helvetica", "B" if b else "", tam); d.multi_cell(0, 4, D._t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    def kv(ps): [p(f"{k}: {v}") for k, v in ps]
    def tab(cab, linhas, larg, lim=90): [p(" | ".join(D._t(x, 30) for x in l)) for l in [cab] + list(linhas)]
    D._pdf_secao_5(d, c["secao_5"], lambda t: p(t, True, 12), lambda t: p(t, True, 9), p, kv, tab, 186)
    out = bytes(d.output()); assert out[:4] == b"%PDF" and d.page_no() >= 2


def test_6_ea_pivos_e_rev0_iguais_ao_replay_o53b(A):
    """O53-B: cada pivô confirmado (O39, M15 fechado) e o estado da REV-0 em sombra que o EA registra = replay pivos_o53b (dados reais BTCUSD M15+H1)."""
    import pivos_o53b as PV
    tmp = tempfile.mkdtemp()
    for f in ("mt5shim.h", "main.cpp"):
        shutil.copy(os.path.join(REF53, "shim", f), tmp)
    _traduzir(A._BT_LATERAL_R0_MQL5, os.path.join(tmp, "ea.cpp"))
    r = subprocess.run(["g++", "-std=c++17", "-O2", "-o", os.path.join(tmp, "sim"), os.path.join(tmp, "main.cpp")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    f15, fh1 = os.path.join(DADOS, "BTCUSD_M15_202610.csv"), os.path.join(DADOS, "BTCUSD_H1_202610.csv")
    out = subprocess.run([os.path.join(tmp, "sim"), "15", f15, f15, "0", "0", fh1], capture_output=True, text=True).stdout.split("\n")
    ev = [dict(p.split("=", 1) for p in l.split("|")[1:] if "=" in p) for l in out if l.startswith("EVT|")]
    piv = [(int(e["t_extremo"]), float(e["extremo"]), int(e["confirmado_no_fechamento_de"])) for e in ev if e.get("ev") == "pivo"]
    rev = {e["id"]: e["estado"] for e in ev if e.get("ev") == "rev0"}
    assert all("SOMBRA" in e.get("modo", "SOMBRA") for e in ev if e.get("ev") == "rev0") and not any(l.startswith("ORDEM") for l in out if "rev" in l)
    m15 = _ler(f15).iloc[:-1].reset_index(drop=True); h1 = _ler(fh1)
    res = PV.auditar(m15, h1)
    first = min(p[2] for p in piv)
    conf = [p for p in res["pivos"] if p["situacao"] == "confirmado" and p["confirmado_em"] - 900 >= first]
    assert piv == [(p["barra"], p["extremo"], p["confirmado_em"] - 900) for p in conf] and len(piv) >= 30
    mp = {"sem rejeição": "sem rejeicao", "gatilho não alcançado": "gatilho nao alcancado", "entrou (sombra)": "entraria (sombra)", "aguardando barra seguinte": "armado"}
    def est(p):
        x = p["rev"]
        if x["estado"] == "bloqueada pelo espaço":
            return "bloqueada: " + ("entrada dentro da zona" if x["decisao"].startswith("entrada dentro") else "espaco insuficiente")
        return mp.get(x["estado"], x["estado"])
    assert rev == {("F-" if p["tipo"] == "fundo" else "T-") + str(p["barra"]): est(p) for p in conf}
    assert len(set(rev.values())) >= 3


def test_7_auditoria_de_pivos_no_diagnostico(A):
    import validacao_o53 as V, datetime as dt_
    d = _ler(os.path.join(DADOS, "BTCUSD_M15_202610.csv")); h = _ler(os.path.join(DADOS, "BTCUSD_H1_202610.csv"))
    linhas = lambda tf, x: [{"simbolo": "BTCUSD", "tf": tf, "abertura_utc": _dt.datetime.fromtimestamp(int(e), _dt.timezone.utc).isoformat(), "o": o, "h": hh, "l": l, "c": c,
                            "fechado": True, "ultimo_visto_utc": "x"} for e, o, hh, l, c in zip(x.ep, x.open, x.high, x.low, x.close)]
    sb = _SB({"auditoria_candles": linhas("M15", d) + linhas("H1", h), "auditoria_leituras": [], "agente_eventos": []})
    de = _dt.datetime(2026, 10, 15, 0, 0, tzinfo=_dt.timezone.utc); ate = _dt.datetime(2026, 10, 16, 11, 0, tzinfo=_dt.timezone.utc)
    P = V.pivos_auditoria(sb, {"id": 15, "simbolo": "BTCUSD", "magic_number": 7}, "M15", de, ate, _dt.timezone.utc)
    assert P["situacao"] == "ok" and len(P["pivos"]) >= 10 and P["janelas"]
    assert all(x["onde_parou"] and x["confirmavel_em"] > x["hora_extremo"] for x in P["pivos"])
    assert all(x["lm_registrou_em"] is None and x["ea_rev0"].startswith("sem evidência") for x in P["pivos"])
    assert V.grafico_png(P["janelas"][0])[:4] == b"\x89PNG"
