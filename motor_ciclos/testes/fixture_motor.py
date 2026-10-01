"""Bancada do motor dos Ciclos: roda o LEITOR REAL (bt_motor_leitura_hml + motor
congelado) contra o MetaTrader5 FALSO (barras sintéticas determinísticas no
horário do servidor) e monta a linha do EA (BTVisaoTick v7.81) com AS MESMAS
barras — para provar identidade/fuso/barra sem corretora real."""
import json, os, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.dirname(AQUI)
FAKE = os.path.join(AQUI, "fake_mt5")
PY = sys.executable
OFF = 10800
LOGIN = 52648209
SEG = {"MN1": 2592000, "W1": 604800, "D1": 86400, "H4": 14400, "H1": 3600,
       "M30": 1800, "M15": 900, "M5": 300, "M1": 60}


def esperar_janela_segura(margem=40):
    """Evita rodar o leitor e o 'EA' em barras M15 diferentes (virada no meio)."""
    r = time.time() % 900
    if r > 900 - margem or r < 3:
        time.sleep(900 - r + 4 if r > 3 else 4 - r)


def rodar_leitor(dados, data_path="/fake/data/ABC", extra_env=None, args=()):
    env = dict(os.environ, PYTHONPATH=FAKE + os.pathsep + MOTOR, BT_FAKE_DATA=data_path)
    env.update(extra_env or {})
    r = subprocess.run([PY, os.path.join(MOTOR, "bt_motor_leitura_hml.py"), "--ativo", "XAUUSD",
                        "--login", str(LOGIN), "--terminal", sys.executable, "--dados", dados,
                        "--uma-vez", *args], env=env, capture_output=True, text=True, timeout=600)
    return r


def ler(dados, nome):
    with open(os.path.join(dados, nome), encoding="utf-8") as f:
        return json.load(f)


def det_ea(magic, simbolo="XAUUSD", agora=None, conta=LOGIN, off=OFF):
    """Linha BOTTESTED_SNAPSHOT (já parseada) coerente com o MT5 falso."""
    sys.path.insert(0, FAKE)
    import MetaTrader5 as F
    agora = int(agora or time.time())
    srv = agora + off
    cvt, cvt0 = [], []
    for tf in ("MN1", "W1", "D1", "H4", "H1", "M30", "M15", "M5", "M1"):
        s = SEG[tf]
        cvt.append(str((srv // s) * s - s)); cvt0.append(str((srv // s) * s))

    def velas(s, n=18):
        ab = (srv // s) * s
        return ";".join(",".join(f"{x:.2f}" for x in F.barra(s, ab - k * s)) + ",100"
                        for k in range(n - 1, -1, -1))
    ab15 = [(srv // 900) * 900 - 900 * k for k in range(1, 97)]
    return {"magic": str(magic), "simbolo": simbolo, "conta": str(conta), "corretora": "Raw Trading Ltd",
            "tfop": "15m", "preco": "2000.00", "z1": "dentro", "z5": "dentro", "z15": "dentro", "z30": "dentro",
            "z60": "dentro", "z240": "dentro", "zD": "dentro", "cv1": "L.L.L.L.L", "cv2": "L.L.L.L",
            "c1m": velas(60), "c5m": velas(300), "c15m": velas(900), "c30m": velas(1800),
            "c60m": velas(3600), "c4h": velas(14400), "cD": velas(86400, 12), "cW": velas(604800, 12),
            "cMN": velas(2592000, 12), "eav": "7.81-ciclos-lm2", "spr": "12", "pt": "0.01",
            "tsrv": str(srv), "tgmt": str(agora), "cvt": ".".join(cvt), "cvt0": ".".join(cvt0),
            "m15h": ",".join([str(ab15[0])] + ["1"] * 95), "posicoes": "0", "equity": "1000"}
