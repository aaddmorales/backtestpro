"""ORDEM 054-A — skills do projeto (.claude/skills): (1) todas carregáveis (frontmatter name/description, nome = pasta);
(2) bottested-trader-m15: replay BTCUSD 10/11 barras 70→71 registra 'sinal reconhecido; ordem bloqueada — falta de espaço' sem ordem."""
import os, re, sys, json, subprocess
AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI); SK = os.path.join(RAIZ, ".claude", "skills")
ESPERADAS = {"ml4t-point-in-time", "ml4t-lookahead-bias", "ml4t-regime-awareness", "ml4t-walk-forward-cv", "ml4t-cost-model", "backtest-expert",
             "pre-trade-check", "position-management", "post-trade-debrief", "risk-reward-sanity-check", "execution-plan-check", "position-sizing",
             "post-trade-review", "bottested-trader-m15", "technical-analyst"}


def test_1_skills_carregaveis():
    achadas = set()
    for d in sorted(os.listdir(SK)):
        f = os.path.join(SK, d, "SKILL.md")
        if not os.path.isfile(f): continue
        txt = open(f, encoding="utf-8").read(); m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
        assert m, d
        nome = re.search(r"^name:\s*(\S+)", m.group(1), re.M).group(1); desc = re.search(r"^description:\s*(.+)", m.group(1), re.M).group(1)
        assert nome == d and len(desc) > 20 and len(desc) <= 1024, d
        achadas.add(nome)
    assert achadas == ESPERADAS, achadas ^ ESPERADAS


def test_2_replay_btc_70_71():
    D = os.path.join(AQUI, "dados_o53c"); arq = lambda x: os.path.join(D, f"BTCUSD_{x}_20261110.csv")
    r = subprocess.run([sys.executable, os.path.join(SK, "bottested-trader-m15", "scripts", "replay_trilha.py"), arq("M15"), arq("M1"), arq("H1"),
                        "--ini", str(1794323700 - 2700), "--spread", "15.00"], capture_output=True, text=True, cwd=RAIZ)
    assert r.returncode == 0, r.stderr[-1500:]
    out = json.loads(r.stdout); z = [t for t in out["trilha"] if t["sinal"] == "ZV-1794323700"][0]
    assert all(x["confirmada_antes_do_rompimento"] for x in z["1_contexto"]["zonas_conhecidas"])
    assert z["2_sinal"]["gatilho"] == 73956.78 and "barra 70" in z["2_sinal"]["barra_rompimento"] and "barra 71" in z["2_sinal"]["valido_na_barra"]
    assert z["3_autorizacao"]["registro"].startswith("sinal reconhecido; ordem bloqueada — falta de espaço") and z["3_autorizacao"]["espaco_R"] < 0.25
    assert z["3_autorizacao"]["sem_filtro_sombra"] == "entraria (sombra)" and out["posicao_em_aberto"] is False and out["resumo_operacoes_fechadas"]["operacoes"] == 0
