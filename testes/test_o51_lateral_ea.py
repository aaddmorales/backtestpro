"""ORDEM 051 — cartão "Rompimento de Lateralização" (R0 da O44) no FLUXO PADRÃO da plataforma de homologação.
Prova que a regra NÃO mudou ao sair do leitor Python (O47) e entrar no EA nativo BT_LATERAL_R0:
  1. código do cartão (passo Testar): detecção idêntica à formacao_o44 em todas as barras (BTCUSD M1/M5/M15/M30, testes/dados_c27r55);
  2. EA (_BT_LATERAL_R0_MQL5) traduzido para C++ com uma camada que imita a API do MT5 (testes/referencia_o51/shim — NÃO é o MT5 nem o
     MetaEditor) e rodado tick a tick (ticks SINTÉTICOS: 4 cotações por M1, spread 1500 pontos) contra o motor ao_vivo_o47: mesmos gatilhos,
     entradas (hora, lado, preço, stop) e saídas (hora, motivo, preço). Pula se não houver g++;
  3. integração: gerador, instrumentação no mesmo perfil do Donchian, Ciclo ausente, validador de código, portão do card de teste, envio.
A compilação real no MetaEditor acontece no PC, pelo Conector HOMOLOG (veredito do job), como em todo envio."""
import os, re, sys, glob, shutil, calendar, subprocess, tempfile
import numpy as np, pandas as pd, pytest
AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI); REF = os.path.join(AQUI, "referencia_o51"); DADOS = os.path.join(AQUI, "dados_c27r55")
sys.path[:0] = [RAIZ, REF]
import formacao_o44 as FO, ao_vivo_o47 as AV, romp_m15 as RM


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


def test_1_codigo_do_cartao_detecta_igual_a_o44(A):
    from backtesting import Backtest, Strategy
    sand = {"pd": pd, "np": np, "Strategy": Strategy, "__builtins__": A.SAFE_BUILTINS}
    ok, motivo = A.verificar_codigo_seguro(A.ESTRATEGIA_LATERAL_R0["codigo"]); assert ok, motivo
    exec(A.ESTRATEGIA_LATERAL_R0["codigo"], sand)
    tot = 0
    for arq in ("M1", "M5", "M15", "M30"):
        d = _ler(os.path.join(DADOS, f"BTCUSD_{arq}_202610.csv"))
        H, L, C = (np.rint(d[k].values / 0.01).astype(np.int64) for k in ("high", "low", "close")); Atr = RM.atr_wilder(d.high, d.low, d.close)
        o44, card = [], []
        for b in range(len(d)):
            ant = float(Atr[b - 1]) if b > 0 else float("nan")
            for s in (-1, 1):
                x = FO.detectar_venda(L, H, C, Atr, b) if s < 0 else FO.detectar_venda(-H, -L, -C, Atr, b)
                if x is not None: o44.append((b, s, x["p"]))
                p = sand["DETECTAR"](list(L), list(H), list(C), ant, b) if s < 0 else sand["DETECTAR"](list(-H), list(-L), list(-C), ant, b)
                if p >= 0: card.append((b, s, p))
        assert o44 == card, arq; tot += len(o44)
        df = d.set_index(pd.to_datetime(d.ep, unit="s")).rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})[["Open", "High", "Low", "Close"]]
        Backtest(df, sand["RompimentoLateralizacaoR0"], cash=1_000_000, finalize_trades=True).run()      # o passo Testar roda
    assert tot >= 50


def _traduzir(mq5, dst):
    s = mq5.replace("#include <Trade\\Trade.mqh>", '#include "mt5shim.h"')
    s = re.sub(r"^input\s+", "static ", s, flags=re.M)
    s = re.sub(r"const (double|long|string) &(\w+)\[\]", r"const std::vector<\1>& \2", s)
    s = re.sub(r"(?<![\w<])(double|long|string) &(\w+)\[\]", r"std::vector<\1>& \2", s)
    s = re.sub(r"^(\s*)(double|long|string|MqlRates)\s+((?:\w+\[\],?\s*)+);",
               lambda m: m.group(1) + f"std::vector<{m.group(2)}> " + ",".join(n.strip().rstrip("[]") for n in m.group(3).split(",")) + ";", s, flags=re.M)
    open(dst, "w").write(s)


@pytest.mark.skipif(shutil.which("g++") is None, reason="sem g++ (a camada do MT5 é C++)")
def test_2_ea_tick_a_tick_igual_ao_motor_o47(A):
    tmp = tempfile.mkdtemp(); shutil.copy(os.path.join(REF, "shim", "mt5shim.h"), tmp); shutil.copy(os.path.join(REF, "shim", "main.cpp"), tmp)
    _traduzir(A._BT_LATERAL_R0_MQL5, os.path.join(tmp, "ea.cpp"))
    r = subprocess.run(["g++", "-std=c++17", "-O2", "-o", os.path.join(tmp, "sim"), os.path.join(tmp, "main.cpp")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    SP = 1500; m1 = _ler(os.path.join(DADOS, "BTCUSD_M1_202610.csv")); tot_e = 0
    for tf, arq in ((15, "M15"), (5, "M5"), (1, "M1"), (30, "M30")):
        f_tf = os.path.join(DADOS, f"BTCUSD_{arq}_202610.csv"); bars = _ler(f_tf); dur = tf * 60
        ini = int(max(bars.ep.iloc[0] + 29 * dur, m1.ep.iloc[0]))
        out = subprocess.run([os.path.join(tmp, "sim"), str(tf), f_tf, os.path.join(DADOS, "BTCUSD_M1_202610.csv"), str(ini), str(SP)], capture_output=True, text=True).stdout.split("\n")
        ev = [l.split("|") for l in out if l.startswith(("ORDEM", "FECHA"))]
        ea_e = [(int(x[2]), x[1], float(x[3]), float(x[4])) for x in ev if x[0] == "ORDEM"]; ea_s = [(int(x[2]), x[1], float(x[3])) for x in ev if x[0] == "FECHA"]
        AV.TF_MIN.setdefault(f"T{tf}", tf); I = AV.Instancia("BTCUSD", f"T{tf}"); I.ativo_desde_ms = 0; ult = None
        for b in m1.itertuples():
            up = b.close >= b.open; p1, p2 = (b.low, b.high) if up else (b.high, b.low)
            for px, dt in zip((b.open, p1, p2, b.close), (0, 15, 30, 59)):
                t = int(b.ep) + dt
                if t < ini: continue
                t0 = (t // dur) * dur
                if t0 != ult:
                    f = bars[bars.ep + dur <= t]
                    if len(f) >= 29:
                        I.fecha_barra(pd.DataFrame({"t": pd.to_datetime(f.ep, unit="s"), "o": f.open, "h": f.high, "l": f.low, "c": f.close}).reset_index(drop=True)); ult = t0
                I.tick(t * 1000, round(px, 2), round(px + SP * 0.01, 2))
        py_e = [(int(pd.Timestamp(e["t"]).value // 10**9), "buy" if e["lado"] > 0 else "sell", round(e["preco"], 2), round(e["stop"], 2)) for e in I.eventos if e["tipo"] == "entrada_virtual"]
        py_s = [(int(pd.Timestamp(e["t"]).value // 10**9), "stop" if e["motivo"].startswith("stop") else "canal", round(e["preco"], 2)) for e in I.eventos if e["tipo"] == "saida_virtual"]
        assert sum("gatilho_armado" in l for l in out) == sum(e["tipo"] == "gatilho_armado" for e in I.eventos), tf
        assert len(ea_e) == len(py_e) and all(a[:3] == b[:3] and abs(a[3] - b[3]) <= 0.011 for a, b in zip(ea_e, py_e)), (tf, ea_e[:4], py_e[:4])
        assert ea_s == py_s, (tf, ea_s[:4], py_s[:4]); tot_e += len(ea_e)
    assert tot_e >= 30


def test_3_gerador_no_perfil_do_donchian(A):
    lat = A._gerar_mq5_de_codigo(A.ESTRATEGIA_LATERAL_R0["codigo"], {"magic": 123456789, "stop_loss": 0, "take_profit": 0, "ativo": "BTC/USD"})
    don = A._gerar_mq5_de_codigo(next(e for e in A.ESTRATEGIAS_PRONTAS if e["id"] == "rompimento_donchian")["codigo"], {"magic": 1, "stop_loss": 60, "take_profit": 0, "ativo": "BTC/USD"})
    assert lat and "BTLatDetectar" in lat and re.search(r"input\s+long\s+InpMagic\s*=\s*123456789", lat)
    for m in ("BT_DISCIPLINA_V3", "BT_OTT_V2", "BT_MAGIC_ISO_V1", "BTTrade", "BTPainelTick();", "BTVisaoTick();", "BTLerComando();"):
        assert (m in lat) == (m in don), m
    assert "InpCicloAtivo" not in lat and A._bt_base_ligar(A.ESTRATEGIA_LATERAL_R0["codigo"], lat, "BTC/USD") == lat     # Ciclo ausente: a R0 roda pura
    assert (lat.count("{") - lat.count("}")) == (don.count("{") - don.count("}"))
    assert A._mq5_sanidade(lat)[0]
    assert "order" not in A._BT_LATERAL_R0_MQL5.lower().replace("ordem", "")                                                # só trade.Buy/Sell/PositionClose


def test_4_portao_do_card_de_teste_e_sem_medicao(A):
    A._sessao_user_id = lambda auth: auth.replace("Bearer ", "")
    v = A._vitrine_com_card_teste({"estrategias": [{"id": "x"}]}, "Bearer u-master"); o = A._vitrine_com_card_teste({"estrategias": [{"id": "x"}]}, "Bearer outro")
    assert [e["id"] for e in v["estrategias"]] == ["x", "teste_integracao_mt5", "lateral_r0"] and [e["id"] for e in o["estrategias"]] == ["x"]
    c = v["estrategias"][-1]
    assert c["melhor_combo"] is None and c["celulas_aprovadas"] == [] and c["winrate_medio"] is None and c["medida"] is False and "BT_LATERAL_R0" in c["codigo"]
    assert "timeframe" not in c["ensaio"]                                                                                     # o TF é escolhido no Editor (M15, M30 ou H1)


def test_5_envio_desliga_protetor_e_guardiao_so_no_lateral(A):
    src = open(os.path.join(RAIZ, "api.py"), encoding="utf-8").read()
    assert 'if "BT_LATERAL_R0" in _cod46:' in src and '_fl46["protecao"] = False; _fl46["guardiao"] = False' in src
    assert 'req.estrategia_nome = "Rompimento de Lateralizacao (R0)"' in src
    assert A.API_VERSAO.startswith("8.31-o51-lateral-r0") and A.BUILD_TAG == "2026-11-08-lateral-r0-o51"
