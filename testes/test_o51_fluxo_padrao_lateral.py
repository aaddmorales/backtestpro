"""ORDEM 051 — cartão "Rompimento de Lateralização" no FLUXO PADRÃO, em ambiente SIMULADO (não é teste ao vivo):
plataforma (rotas /lateral reais sobre Supabase FALSO) → trilha 1-7 → 🔑 token no passo Enviar → Conector HOMOLOG hml18 ("Meus bots" + ponte em
sombra com o motor O48 inalterado) → MT5 SIMULADO (ticks sintéticos dos CSVs BTCUSD de 14-16/out do repo, com TICKVOL=1 e SPREAD=1500 pontos
ACRESCENTADOS — dado SIMULADO) → "Conectado" → semana de coleta → Monitor de Bots.
Uso: python -I testes/test_o51_fluxo_padrao_lateral.py [SAIDA.json]"""
import os, sys, json, glob, tempfile, hashlib, importlib
import pandas as pd
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HML = os.path.join(RAIZ, "conector_homolog", "hml18"); PKG_SIM = os.path.join(RAIZ, "leitor_lateral_o48")
sys.path[:0] = [RAIZ, HML, os.path.join(RAIZ, "testes")]
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import lateral_o48 as LT, fake_sb_o48 as FS
import ponte_lateral_hml18 as PO
RES = []
def reg(n, ok, d=""): RES.append({"teste": n, "ok": bool(ok), "detalhe": str(d)}); print("OK   " if ok else "FALHA", n, "·", d, flush=True)

# ── dados SIMULADOS: CSVs do repo + colunas que o terminal simulado exige ──
DADOS = tempfile.mkdtemp(prefix="o51_dados_")
for f in glob.glob(os.path.join(RAIZ, "testes", "dados_c27r55", "BTCUSD_*_202610.csv")):
    d = pd.read_csv(f, sep="\t"); d["<TICKVOL>"] = 1; d["<SPREAD>"] = 1500; d.to_csv(os.path.join(DADOS, os.path.basename(f)), sep="\t", index=False)
sys.path.insert(0, PKG_SIM)
import mt5_falso_ticks as F
F.configurar(DADOS, pd.Timestamp("2026-10-15 06:00"), common=tempfile.mkdtemp())
MQL5 = os.path.join(tempfile.mkdtemp(prefix="o51_term_"), "MQL5"); os.makedirs(MQL5)

class Term:                                                                    # terminal simulado com a pasta de dados da instalação fixada
    data_path = os.path.dirname(MQL5)
class MT5(object):
    def __getattr__(self, k): return getattr(F, k)
    def terminal_info(self): return Term()
M = MT5()

os.environ["BT_CARD_TESTE_USER"] = "u-admin"; SB = FS.FakeSB()
def sessao(auth):
    if not auth.startswith("Bearer "): raise HTTPException(status_code=401, detail="sem sessão")
    return auth[7:]
relogio = lambda: F._F._S["agora"].tz_localize("UTC").to_pydatetime()
app = FastAPI(); app.include_router(LT.criar_router(lambda: SB, sessao, relogio)); C = TestClient(app); H = {"Authorization": "Bearer u-admin"}
def post_plat(rota, corpo):
    r = C.post(rota, content=PO.corpo_json(corpo), headers={"Content-Type": "application/json"})
    if r.status_code != 200: raise RuntimeError(f"HTTP {r.status_code} em {rota}: {r.text[:120]}")
    return r.json()

# 1 · trilha antes de criar
t0 = C.post("/lateral/bots/listar", json={}, headers=H).json()["trilha"]
reg("trilha 1-7 com os nomes do fluxo padrão; nada feito antes de criar", [e["nome"] for e in t0["etapas"]] == ["Criar", "Testar", "Ajustar", "Enviar", "Conectar", "Operar", "Monitorar"] and t0["atual"] == 1, t0["atual"])

# 2 · Criar (BTC nos 3 TF — os CSVs do repo são só BTC)
d = C.post("/lateral/bots/criar", json={"ativos": ["BTCUSD"], "tfs": ["M15", "M30", "H1"]}, headers=H).json()
ids = [b["id"] for b in d["criados"]]
t1 = C.post("/lateral/bots/listar", json={}, headers=H).json()["trilha"]
reg("Criar: 3 bots; trilha vai a 'Enviar' com Testar/Ajustar marcados 'não se aplica' (nunca como medidos)",
    len(ids) == 3 and t1["atual"] == 4 and "não se aplica" in t1["etapas"][1]["nota"] and "não se aplica" in t1["etapas"][2]["nota"], t1["etapas"][1]["nota"])

# 3 · Enviar: token + enviar
tk = C.post("/lateral/token/gerar", json={}, headers=H).json(); TOK = tk["bot_token"]
C.post("/lateral/bots/enviar", json={"bot_ids": ids}, headers=H)
lst = C.post("/lateral/bots/listar", json={}, headers=H).json()
guardado = [r for r in SB.t.get("lateral_chaves", []) if r.get("user_id") == "u-admin"]
reg("Enviar: 🔑 token 'lat_' gerado (só o hash guardado) e bots 'enviado'; trilha em 'Conectar'",
    TOK.startswith("lat_") and guardado and guardado[0]["chave_hash"] != TOK and TOK not in json.dumps(SB.t.get("lateral_chaves")) and lst["trilha"]["atual"] == 5
    and all(b["estado"] == "enviado" for b in lst["bots"]), f"trilha atual {lst['trilha']['atual']}")
reg("rota antiga /lateral/chave/gerar segue como sinônimo (pacote O48/O49)", C.post("/lateral/chave/gerar", json={}, headers=H).json()["chave"].startswith("lat_"))
TOK = C.post("/lateral/token/gerar", json={}, headers=H).json()["bot_token"]                       # o último token gerado é o que vale

# 4 · Conector: separar tokens + Meus bots
camp, lat = PO.separar_tokens(f"fda1campanha00000000 {TOK}\n{TOK}")
reg("campo do token: campanha e lat_ separados, sem repetir", camp == ["fda1campanha00000000"] and lat == [TOK], f"{len(camp)} campanha · {len(lat)} lateral")
ok, bots = PO.listar_bots_laterais(TOK, post=post_plat)
reg("'Meus bots' do Conector lista os 3 bots do cartão como sombra, sem EA", ok and len(bots) == 3 and all(b["_lateral"] and b["modo"] == "sombra" and b["tem_mq5"] is False for b in bots),
    [b["nome"] for b in bots] if ok else bots)
ok2, err = PO.listar_bots_laterais("lat_invalido_123456", post=post_plat)
reg("token inválido não lista nada", not ok2 and "401" in err, err)

# 5 · recusas antes de ler
F._F._S["modo"] = F.ACCOUNT_TRADE_MODE_REAL
p_real = PO.PonteLateral([TOK], MQL5, mt5_mod=M, post=post_plat, pasta_base=tempfile.mkdtemp())
reg("conta não-DEMO: ponte RECUSA e não lê nada", not p_real.preparar() and "DEMO" in p_real.recusa and not p_real.leitores, p_real.recusa)
F._F._S["modo"] = F.ACCOUNT_TRADE_MODE_DEMO
p_pasta = PO.PonteLateral([TOK], os.path.join(tempfile.mkdtemp(), "OUTRA", "MQL5"), mt5_mod=M, post=post_plat, pasta_base=tempfile.mkdtemp())
reg("terminal diferente da instalação fixada: ponte RECUSA", not p_pasta.preparar() and "instalação fixada" in p_pasta.recusa, p_pasta.recusa)

# 6 · ponte real (sobre o terminal simulado): confirma → conectado → coleta
marcas = {"mt5": 0, "nuvem": 0}
P = PO.PonteLateral([TOK], MQL5, mt5_mod=M, post=post_plat, pasta_base=tempfile.mkdtemp(),
                    ao_mt5=lambda: marcas.__setitem__("mt5", marcas["mt5"] + 1), ao_nuvem=lambda: marcas.__setitem__("nuvem", marcas["nuvem"] + 1))
reg("ponte prepara: DEMO + instalação fixada conferidas pelo terminal", P.preparar() and P.recusa is None and len(P.leitores) == 1, P.recusa)
seg = lambda: F._F._S["agora"].timestamp()
def rodar(minutos):
    for _ in range(minutos): P.passo(seg()); F.avancar(1)
rodar(5)
lst = {b["id"]: b for b in C.post("/lateral/bots/listar", json={}, headers=H).json()["bots"]}
tr = C.post("/lateral/bots/listar", json={}, headers=H).json()["trilha"]
reg("Conectar: os 3 bots confirmados pelo terminal (símbolo, TF, regra, sombra, cotação, DEMO) → 'conectado'; trilha em 'Operar'",
    all(b["estado"] == "conectado" and b["confirmacao"]["modo"] == "sombra" and b["confirmacao"]["terminal"]["demo"] for b in lst.values()) and tr["atual"] == 6,
    [b["estado"] for b in lst.values()])
jan = {(b["coleta_inicio"], b["coleta_fim"]) for b in lst.values()}
reg("semana de coleta com o MESMO início e fim nos 3 TF", len(jan) == 1 and list(jan)[0][0] is not None, list(jan)[0])
reg("trilha da janela do Conector acende com dado real (MT5 e plataforma)", marcas["mt5"] > 0 and marcas["nuvem"] > 0, marcas)
rodar(26 * 60)                                                                                      # ~26 h simuladas (até o fim dos CSVs)
lst = {b["id"]: b for b in C.post("/lateral/bots/listar", json={}, headers=H).json()["bots"]}
evs = SB.t.get("lateral_eventos", [])
tipos = sorted({e["tipo"] for e in evs})
reg("Operar: bots 'coletando' e eventos do motor O48 chegando (posições VIRTUAIS)",
    all(b["estado"] == "coletando" for b in lst.values()) and "contadores" in tipos and "leitura_canal" in tipos, f"{len(evs)} eventos · tipos {tipos}")
reg("nenhuma chamada de ordem no terminal simulado", F.CHAMADAS_PROIBIDAS == [], F.CHAMADAS_PROIBIDAS[:2])
fonte = open(os.path.join(HML, "ponte_lateral_hml18.py"), encoding="utf-8").read()
reg("a ponte não contém chamada de ordem (order_send/order_check/positions)", not any(x in fonte for x in ("order_send(", "order_check(", "positions_get(")), "busca no código")
reg("token não vai para URL nem para a pasta de estado", TOK not in "".join(os.listdir(P.pasta_base)), os.listdir(P.pasta_base))

# 7 · Monitor de Bots
mon = C.post("/lateral/monitor", json={}, headers=H).json()
reg("Monitorar: seção do Monitor com os 3 bots, Conector online, contadores da semana", len(mon["bots"]) == 3 and all(b["conector_online"] for b in mon["bots"]) and "nenhuma ordem" in mon["aviso"],
    [(b["nome"], b["estado"], b["entradas_semana"], b["R_semana"]) for b in mon["bots"]])
tr = C.post("/lateral/bots/listar", json={}, headers=H).json()["trilha"]
reg("trilha completa até 'Monitorar'", all(e["feito"] for e in tr["etapas"]), tr["atual"])

# 8 · motor inalterado + trava de rede
man = json.load(open(os.path.join(HML, "lateral", "MANIFESTO_MOTOR_O48.json"))); o48 = json.load(open(os.path.join(PKG_SIM, "MANIFESTO_O48.json")))
iguais = all(hashlib.sha256(open(os.path.join(HML, "lateral", f), "rb").read()).hexdigest() == h == o48[f] for f, h in man.items())
reg("motor da O48 dentro do Conector é byte a byte o do pacote O48 (regra não mudou)", iguais and len(man) == 9, f"{len(man)} arquivos")
import conector_nucleo_homolog as NU
def bloqueia(u):
    try: NU._hml_checar("POST", u); return False
    except RuntimeError: return True
reg("trava de rede: só https em homolog-homolog e lm-relatorio-homolog; produção e http recusados",
    not bloqueia("https://lm-relatorio-homolog.up.railway.app/lateral/x") and not bloqueia("https://homolog-homolog.up.railway.app/x")
    and bloqueia("https://bottested.com/x") and bloqueia("https://web-production-xyz.up.railway.app/x") and bloqueia("http://lm-relatorio-homolog.up.railway.app/x"),
    NU.APP_VERSAO.split(" ")[0])

# 9 · Parar (só os bots do cartão)
C.post("/lateral/bots/parar", json={"bot_ids": [ids[0]]}, headers=H); rodar(2)
rodando = sum(len(G.inst) for L in P.leitores for G in L.G.values())
reg("Parar na plataforma encerra só aquele bot no Conector", rodando == 2, f"{rodando} instâncias seguem")

falhas = [r for r in RES if not r["ok"]]
print(f"\n{len(RES) - len(falhas)}/{len(RES)} OK")
if len(sys.argv) > 1: json.dump({"ordem": "051", "ambiente": "SIMULADO", "resultados": RES}, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.exit(1 if falhas else 0)
