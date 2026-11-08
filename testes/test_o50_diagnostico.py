"""ORDEM 050 — testes do diagnóstico geral da LM (sem banco: dados sintéticos e Supabase em memória). Uso: python test_o50_diagnostico.py [SAIDA.json]"""
import os, sys, json, datetime as dt
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import diagnostico_lm_o50 as D, fake_sb_o48 as FS
RES = []
def reg(n, ok, d=""): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)
UTC = dt.timezone.utc; AG = dt.datetime(2026, 11, 8, 6, 55, 0, tzinfo=UTC)

p = D.resolver_periodo(agora=AG)
reg("sem datas = últimas 48 h até o corte (agora)", p["modo"] == "ultimas_48h" and p["de_utc"] == "2026-11-06T06:55:00Z" and p["ate_utc"] == "2026-11-08T06:55:00Z", f"{p['de_local']} → {p['ate_local']} {p['fuso']}")
p = D.resolver_periodo("2026-10-22T00:00", "2026-10-23T09:00", "Europe/Kyiv", AG)
reg("datas em Europe/Kyiv no horário de verão (UTC+3)", p["de_utc"] == "2026-10-21T21:00:00Z" and p["ate_utc"] == "2026-10-23T06:00:00Z", f"{p['de_utc']} → {p['ate_utc']}")
p = D.resolver_periodo("2026-11-01T00:00", "2026-11-02T00:00", "Europe/Kyiv", AG)
reg("datas em Europe/Kyiv no horário de inverno (UTC+2)", p["de_utc"] == "2026-10-31T22:00:00Z", p["de_utc"])
p = D.resolver_periodo("2026-11-07T00:00", "2026-12-01T00:00", "Europe/Kyiv", AG)
reg("fim no futuro é cortado em 'agora' (o corte nunca passa do instante da geração)", p["ate_utc"] == "2026-11-08T06:55:00Z", p["ate_utc"])
for de, ate, nome in (("2026-11-02T00:00", "2026-11-01T00:00", "início depois do fim"), ("2026-09-01T00:00", "2026-11-01T00:00", "mais de 31 dias")):
    try: D.resolver_periodo(de, ate, "Europe/Kyiv", AG); ok = False
    except HTTPException as e: ok = e.status_code == 422
    reg(f"recusa período inválido: {nome}", ok)
xs = [10, 11, 12, 11, 13]; e = D.ema(xs); m = [10.0]
for x in xs[1:]: m.append(2 / 21 * x + (1 - 2 / 21) * m[-1])
reg("EMA20 = fórmula recursiva (α = 2/21, início no 1º valor) — a mesma das janelas O48/O49", all(abs(a - b) < 1e-12 for a, b in zip(e, m)))
reg("classes: sem sinal / bloqueado / autorizado / sem dados", D._classe("observar", "R-CICLO-01.cv1_neutra", True, True, 5)[0] == "sem sinal"
    and D._classe("bloquear", "R-CICLO-01.cv1_bloqueada", True, True, 5)[0] == "sinal bloqueado" and D._classe("vender", "R-CICLO-01.autorizada", True, True, 5)[0] == "sinal autorizado"
    and D._classe("bloquear", "R-CICLO-01.atestado", True, True, 5)[0] == "sem dados para avaliar" and D._classe(None, None, None, False, 0)[0] == "sem dados para avaliar")

# dados sintéticos: 1 bot, 80 barras M15, 1 entrada vencedora, 1 escolha sem abertura
T0 = int(dt.datetime(2026, 10, 22, 0, 0, tzinfo=UTC).timestamp()); velas = [[1, T0 + 900 * i, 100 + i * .1, 100.5 + i * .1, 99.5 + i * .1, 100.2 + i * .1] for i in range(80)]
iso = lambda i: dt.datetime.fromtimestamp(T0 + 900 * i, UTC).isoformat()
RAW = {"bots": [{"id": 1, "nome": "Bot X", "simbolo": "XAUUSD", "user_id": "u1", "excluido": False}],
       "coleta": [{"bot_id": 1, "n_snapshots": 500, "primeiro": iso(70), "ultimo": iso(79), "ultimo_antes_do_corte": iso(79), "n_lacunas": 1, "lacunas_s_total": 300, "lacunas": [{"de": iso(72), "ate": iso(72), "s": 300}]}],
       "barras_m15_colunas": ["bot_id", "barra_epoch_utc", "decisao", "regra", "completa", "motor_ult", "atraso_primeira_leitura_s", "snapshots_na_barra"],
       "barras_m15": [[1, T0 + 900 * i, d, r, True, None, 5, 40] for i, (d, r) in zip(range(70, 76), [("observar", "R-CICLO-01.cv1_neutra"), ("bloquear", "R-CICLO-01.cv1_bloqueada"), ("vender", "R-CICLO-01.autorizada"),
                                                                                                         ("bloquear", "R-CICLO-01.atestado"), (None, None), ("observar", "R-CICLO-01.cv1_neutra")])],
       "leituras_por_regra": [], "selecao": [{"bot_id": 1, "n": 6}],
       "escolhas": [{"bot_id": 1, "escolha_uid": "card4|M15|x|1", "barra_m15": iso(72), "card": "card4", "lado": "venda", "entrada": 107.2, "stop": 108.0, "suporte_m15": 106.0, "resistencia_m15": 108.5, "motivo": "teste"},
                    {"bot_id": 1, "escolha_uid": "card2|M15|y|1", "barra_m15": iso(71), "card": "card2", "lado": "venda", "entrada": 107.1, "stop": 108.0, "motivo": None}],
       "decisoes": [{"id": "d1", "bot_id": 1, "status": "consumida", "card": "card4", "ts_barra": iso(72)}],
       "aberturas": [{"id": 9, "bot_id": 1, "card": "card4", "lado": -1, "candidato_uid": "card4|M15|x|1", "decisao_id": "d1", "estado": "fechada", "ts_barra": iso(72), "ts_reserva": iso(72),
                      "ts_abertura": iso(73), "ts_fechamento": iso(76), "preco_ref": 107.2, "stop_inicial": 108.0, "preco_entrada": 107.3, "preco_saida": 106.9, "resultado_usd": 50.0, "risco_planejado_usd": 100.0,
                      "comissao": -1.0, "swap": 0, "motivo_saida": "ciclo"}],
       "comandos": [], "trilha_contagem": [], "trilha_motivos": [], "sombra_e_origem": {"lm_eventos": [], "lateral_eventos": [], "lateral_bots": 0, "babymachine_operacoes": []},
       "candles_m15_colunas": ["bot_id", "abertura_epoch_utc", "o", "h", "l", "c"], "candles_m15_grafico": velas}
per = D.resolver_periodo("2026-10-22T20:30", "2026-10-23T03:00", "Europe/Kyiv", AG)
c = D.montar(RAW, per, {}, "teste", gerado=AG)
C1 = c["secao_1"]["classificacao_das_barras_m15"]["total"]
reg("seção 1 classifica cada barra uma vez", C1 == {"sem sinal": 2, "sinal bloqueado": 1, "sinal autorizado": 1, "sem dados para avaliar": 2}, json.dumps(C1, ensure_ascii=False))
R3 = c["secao_3"]["resultado"]
reg("seção 3: R = resultado ÷ risco planejado; custos = comissão + swap", R3["R_total"] == 0.5 and R3["custos_usd_total"] == -1.0 and R3["vencedoras"] == 1, f"R {R3['R_total']} custos {R3['custos_usd_total']}")
reg("deixou passar = escolha sem abertura, com o motivo da barra (ou 'não registrado')", len(c["secao_2"]["por_que"]["deixou_passar"]) == 1 and "cv1_bloqueada" in c["secao_2"]["por_que"]["deixou_passar"][0]["motivo"],
    c["secao_2"]["por_que"]["deixou_passar"][0]["motivo"])
J = [j for j in c["secao_4"]["janelas"] if j.get("velas")]
reg("seção 4: janelas com EMA20 High/Low, nível, gatilho, entrada, saída e R; 1 entrou e 1 deixou passar", len(J) == 2 and all(j["ema20_high"] and j["ema20_low"] for j in J)
    and J[0]["marcas"]["R"] == 0.5 and J[0]["marcas"]["suporte"] == 106.0 and J[0]["marcas"]["entrada"] and J[0]["marcas"]["saida"], [j["titulo"][:60] for j in J])
reg("partes sem dados declaradas (modelo treinado, sombra)", any(x["parte"].startswith("modelo treinado") and x["situacao"] == "sem dados" for x in c["partes_sem_dados"])
    and any("sombra" in x["parte"] and x["situacao"] == "sem dados" for x in c["partes_sem_dados"]))
c2 = D.montar(RAW, per, {"estrategia": "card2"}, "teste", gerado=AG)
reg("filtro de estratégia limita escolhas/aberturas e é registrado", c2["filtros"]["estrategia"] == "card2" and not c2["secao_3"]["resultado"]["operacoes_fechadas"] and c2["secao_1"]["classificacao_das_barras_m15"]["total"] == C1)
vazio = D.montar({}, D.resolver_periodo(agora=AG), {}, "teste", gerado=AG)
reg("período sem registros: diz que nada foi visto e onde faltou", vazio["revisao_diaria"]["o_que_a_lm_conseguiu_ver"].startswith("Nada"), vazio["revisao_diaria"]["onde_faltou_dado_ou_explicacao"][0])
pdfb = D.pdf(dict(c, relatorio_id="DIAG-20261023T000000Z-0000000000", sha256_do_conteudo="0" * 64))
reg("PDF gerado com as janelas (imagens) a partir do mesmo conteúdo", pdfb[:4] == b"%PDF" and pdfb.count(b"/Subtype /Image") >= 2, f"{len(pdfb)} bytes")

# rotas: geração grava; PDF e JSON saem do mesmo registro; outro usuário não baixa; não-admin só vê os seus bots
class SB(FS.FakeSB):
    def __init__(self): super().__init__(); self.t["conector_bots"] = [{"id": 1, "user_id": "u1"}, {"id": 2, "user_id": "u2"}]; self.pedidos = []
    def rpc(self, n, p): self.pedidos.append(p); return type("Q", (), {"execute": lambda s: type("R", (), {"data": RAW})()})()
sb = SB()
def sessao(a):
    if not a.startswith("Bearer "): raise HTTPException(status_code=401, detail="sem sessão")
    return a[7:]
app = FastAPI(); app.include_router(D.criar_router(lambda: sb, sessao, lambda u: u == "adm", relogio=lambda: AG)); C = TestClient(app)
r = C.post("/learning/diagnostico/gerar", json={"de": "2026-10-22T20:30", "ate": "2026-10-23T03:00", "fuso": "Europe/Kyiv"}, headers={"Authorization": "Bearer adm"}).json()
reg("admin: todos os bots do ambiente na consulta", sb.pedidos[-1]["p_bots"] == [1, 2] and sb.pedidos[-1]["p_users"] is None and r["persistido"], r["relatorio_id"])
js = C.post("/learning/diagnostico/baixar", json={"relatorio_id": r["relatorio_id"], "formato": "json"}, headers={"Authorization": "Bearer adm"})
pd_ = C.post("/learning/diagnostico/baixar", json={"relatorio_id": r["relatorio_id"], "formato": "pdf"}, headers={"Authorization": "Bearer adm"})
reg("JSON e PDF baixados do MESMO registro (mesmo id, mesmo sha do conteúdo, mesmo corte)", js.status_code == 200 and pd_.status_code == 200 and js.headers["X-BotTested-Conteudo-SHA256"] == pd_.headers["X-BotTested-Conteudo-SHA256"] == r["sha256_do_conteudo"]
    and json.loads(js.content)["periodo"]["corte_utc"] == r["periodo"]["corte_utc"], r["sha256_do_conteudo"][:16])
reg("outro usuário não baixa o relatório (404)", C.post("/learning/diagnostico/baixar", json={"relatorio_id": r["relatorio_id"], "formato": "pdf"}, headers={"Authorization": "Bearer u2"}).status_code == 404)
C.post("/learning/diagnostico/gerar", json={}, headers={"Authorization": "Bearer u2"})
reg("usuário comum: só os próprios bots", sb.pedidos[-1]["p_bots"] == [2] and sb.pedidos[-1]["p_users"] == ["u2"])
reg("sem sessão = 401", C.post("/learning/diagnostico/gerar", json={}).status_code == 401)
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
if len(sys.argv) > 1: json.dump({"versao": D.VERSAO, "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
