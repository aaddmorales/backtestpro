"""envia ao relatório da homologação ISOLADA LOCAL os eventos de 2 operações do executor ROMP no terminal SIMULADO (classe "simulado")."""
import os, sys, json, tempfile, pandas as pd
os.chdir("/home/claude/r005/rompimento/mt5"); sys.path.insert(0, ".")
import mt5_falso_exec as F, bt_romp_m15_v001 as RX
env = dict(l.strip().split("=", 1) for l in open(sys.argv[1]) if "=" in l); T = tempfile.mkdtemp(prefix="romp_iso_")
ops = pd.read_csv("../saida/bancada/ROMP_operacoes.csv", sep=";"); ops = ops[pd.to_datetime(ops.barra_sinal) >= "2026-05-01"].head(2)
cfg = dict(RX.CFG_PADRAO, plataforma_url="http://127.0.0.1:8000", bot_token=env["LM_BOT_TOKEN"], dimensionamento={"modo": "lote_fixo", "valor": 0.01})
F.configurar("/home/claude/r005/lm014/dados/csv_limpo", pd.Timestamp(ops.barra_sinal.iloc[0]) + pd.Timedelta(minutes=15, seconds=20), common=T + "/c")
S = RX.Romp(F, cfg, T + "/p", "simulado"); fim = pd.Timestamp(ops.t_sai.iloc[1]) + pd.Timedelta(minutes=30)
while F._B._S["agora"] < fim: S.ciclo(); F.avancar(1)
e = RX.EX.Envio(S.pasta, cfg["plataforma_url"], cfg["bot_token"], print); n = 0
while True:
    k = e.enviar_uma_vez(); n += k
    if not k: break
print("enviados", n, "pendentes", e.pendentes(), "resultados", sum('"tipo": "resultado"' in l for l in open(S.D.f)))
