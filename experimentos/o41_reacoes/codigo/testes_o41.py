"""ORDEM 041 — casos de fronteira: reações (episódio, conhecimento, janela), qualificação, travessia × mudança de borda, Testes A/B, reinício e ausência de futuro.
Uso: python testes_o41.py SAIDA.json"""
import os, sys, json, time, tempfile, copy
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrutura_o39 as ES, estrategia_o39 as ST, janela_o40 as JN, reacoes_o41 as RQ
RES = []
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
t0 = pd.Timestamp("2026-01-05")


class Sim:
    def __init__(self): self.mem = ES.Memoria("T", "M15"); self.rc = RQ.Reacoes(); self.k = 0
    def barra(self, l, c=100.5, h=101.0, o=100.5):
        cp = self.mem.c_ant; tf = str(t0 + pd.Timedelta(minutes=15 * (self.k + 1)))
        ev = self.mem.nova_barra(str(t0 + pd.Timedelta(minutes=15 * self.k)), tf, o, h, l, c); self.rc.atualizar(self.mem, ev, h, l, c, cp, self.mem.atr, tf); self.k += 1; return ev
    def n(self, ext): return next(x for x in self.mem.niveis if any(abs(m["extremo"] - ext) < 1e-9 for m in x["membros"]))


S = Sim()
for _ in range(30): S.barra(100.0)
S.barra(99.0); S.barra(100.0); r_antes = list(S.rc.s.values())                       # barra 31 = extremo; 32 = i+1 (nível ainda não conhecido)
S.barra(100.0); lv = S.n(99.0); rs = S.rc.s[lv["id"]]["lista"]
reg("reação da formação só fica conhecida na confirmação (i+2), nunca antes", r_antes == [] and len(rs) == 1 and rs[0]["conhecida_n"] == 33 and rs[0]["inicio_n"] == 31,
    f"antes de i+2: {len(r_antes)} estados; depois: reação início n={rs[0]['inicio_n'] if rs else None}, conhecida n={rs[0]['conhecida_n'] if rs else None}, afastamento {rs[0]['afastamento_atr'] if rs else None} ATR")
for _ in range(5): S.barra(100.0)
for _ in range(4): S.barra(99.1, c=99.3, h=99.6)                                       # 4 barras seguidas na zona, sem afastar ≥ 0,5 ATR
n_meio = len(S.rc.s[lv["id"]]["lista"]); ep = S.rc.s[lv["id"]]["ep"]
S.barra(99.2, c=99.25, h=99.5)                                                         # novo toque com o episódio ainda aberto
S.barra(99.4, c=100.6, h=100.8); rs = S.rc.s[lv["id"]]["lista"]
reg("várias barras na zona = 1 episódio; toque dentro do episódio aberto não abre outro; reação conhecida só no afastamento",
    n_meio == 1 and ep is not None and len(rs) == 2 and rs[1]["inicio_n"] == 39, f"durante: {n_meio} reação, episódio aberto desde n={ep['inicio_n'] if ep else None}; depois do afastamento: {len(rs)} reações (2ª começou em n={rs[1]['inicio_n'] if len(rs) > 1 else None})")
q2 = RQ.qualificado(S.mem, S.rc, lv, "suporte")[0]
reg("nível com 2 reações na janela fica QUALIFICADO", q2 is not None, f"zona elegível {q2}")
# isolado não bloqueia; qualificado bloqueia (Teste A)
S2 = Sim()
for _ in range(30): S2.barra(100.0)
S2.barra(99.0); S2.barra(100.0); S2.barra(100.0)
for _ in range(5): S2.barra(100.0)
r_iso = RQ.decidir_q("A", S2.mem, S2.rc, None, 99.8, 100.5, 100.0, 100.0, 101.0, 101.0, 100.6, 99.6, 1.0, "s1", 0)
r_q = RQ.decidir_q("A", S.mem, S.rc, None, 99.8, 100.5, 100.0, 100.0, 101.0, 101.0, 100.6, 99.6, 1.0, "s2", 0)
reg("pivô isolado (1 reação) NÃO bloqueia no Teste A e fica registrado como referência", r_iso["gat"] is not None and r_iso["regs"][0]["bloqueio_evitado_isolado"] and r_iso["regs"][0]["obstaculo"]["mais_proximo"]["reacoes_na_janela"] == 1,
    f"isolado: {r_iso['regs'][0]['decisao']} · mais próximo {r_iso['regs'][0]['obstaculo']['mais_proximo']['nivel']} a {r_iso['regs'][0]['obstaculo']['mais_proximo']['dist_atr']:.2f} ATR")
reg("nível qualificado (2 reações) bloqueia no Teste A", r_q["gat"] is None and r_q["regs"][0]["decisao"] == "aguardando" and r_q["regs"][0]["obstaculo"]["bloqueador"]["reacoes_na_janela"] == 2,
    f"{r_q['regs'][0]['decisao']} · bloqueador {r_q['regs'][0]['obstaculo']['bloqueador']['nivel']}")
# travessia × igualdade
esp = {"lado": -1, "nivel": lv["id"], "sinal": "s2"}; z = RQ.qualificado(S.mem, S.rc, lv, "suporte")[0]
r_ig = RQ.decidir_q("A", S.mem, S.rc, esp, z[0], z[0] + 0.1, 99.5, 99.5, 101.0, 101.0, 99.4, z[0] - 0.05, 1.0, "b", 0)
r_tr = RQ.decidir_q("A", S.mem, S.rc, esp, z[0] - 0.01, z[0] + 0.1, 99.5, 99.5, 101.0, 101.0, 99.4, z[0] - 0.2, 1.0, "b", 0)
reg("fechamento IGUAL à borda não é rompimento; fechamento além com o anterior dentro arma o gatilho (só para a barra seguinte)", r_ig["gat"] is None and r_ig["espera"] is not None and r_tr["gat"] is not None,
    f"igual: espera mantida; além: {r_tr['regs'][0]['decisao']} com gatilho {r_tr['gat']['nivel_gatilho']:.2f}")
# mudança de borda sem travessia (pivô antigo sai da janela) — Testes × Referência
S3 = Sim()
for _ in range(30): S3.barra(100.0)
S3.barra(99.0); S3.barra(100.0); S3.barra(100.0)
for _ in range(170): S3.barra(100.0)
S3.barra(99.2); S3.barra(100.0); S3.barra(100.0)                                       # membro recente (agrupado) + reação
for _ in range(8): S3.barra(100.0)
S3.barra(99.22); S3.barra(100.0); S3.barra(100.0)                                      # outro membro recente + reação
lv3 = S3.n(99.0); e3 = {"lado": -1, "nivel": lv3["id"], "sinal": "s3"}
while S3.mem.n_barras < 229: S3.barra(100.0)
z_antes = JN.zona_elegivel(lv3, S3.mem.n_barras, 200, "suporte"); r_dentro = RQ.decidir_q("A", S3.mem, S3.rc, e3, 99.15, 99.16, 99.5, 99.5, 101.0, 101.0, 99.3, 99.1, 1.0, "b", 0)
S3.barra(100.0); S3.barra(100.0)                                                       # n = 231: o membro da barra 31 sai
z_dep = JN.zona_elegivel(lv3, S3.mem.n_barras, 200, "suporte")
r_A = RQ.decidir_q("A", S3.mem, S3.rc, e3, 99.15, 99.16, 99.5, 99.5, 101.0, 101.0, 99.3, 99.1, 1.0, "b", 0)
r_Ref = JN.decidir_janela(S3.mem, e3, 99.15, 99.16, 99.5, 99.5, 101.0, 101.0, 99.3, 99.1, 1.0, "b", 0)
reg("borda mudou (pivô saiu da janela) sem o preço atravessar: Teste A NÃO arma gatilho e encerra a espera; a Referência arma (defeito medido no diagnóstico)",
    r_dentro["espera"] is not None and r_A["gat"] is None and r_A["regs"][0]["decisao"] == "espera_encerrada_borda" and r_Ref["gat"] is not None,
    f"zona elegível {z_antes} → {z_dep}; fechamento 99,15 (anterior 99,16): A = {r_A['regs'][0]['decisao']}; Referência = {r_Ref['regs'][0]['decisao']}")
# reações fora da janela desqualificam (pivô recente continua elegível) → espera encerrada sem liberar
S4 = copy.deepcopy(S)
while S4.mem.n_barras < 148: S4.barra(100.0)
S4.barra(99.4, c=99.6, h=99.8); S4.barra(99.15, c=99.2, h=99.3)                        # novo pivô (agrupado) na barra 150
while S4.mem.n_barras < 232: S4.barra(99.16, c=99.2, h=99.25)                          # preço fica na zona: episódio aberto, sem nova reação
rs4 = RQ.Reacoes.na_janela(S4.rc, lv, S4.mem.n_barras)
a_ok = RQ.decidir_q("A", S4.mem, S4.rc, esp, 99.18, 99.2, 100.0, 100.0, 101.0, 101.0, 99.25, 99.16, 1.0, "b", 0)
S4.barra(99.16, c=99.2, h=99.25); rs5 = RQ.Reacoes.na_janela(S4.rc, lv, S4.mem.n_barras)
r_out = RQ.decidir_q("A", S4.mem, S4.rc, esp, 99.18, 99.2, 100.0, 100.0, 101.0, 101.0, 99.25, 99.16, 1.0, "b", 0)
reg("1ª reação sai da janela (pivô recente ainda elegível) → nível perde a qualificação → espera encerrada, sinal antigo não liberado",
    len(rs4) == 2 and a_ok["espera"] is not None and len(rs5) == 1 and r_out["espera"] is None and r_out["gat"] is None and r_out["regs"][0]["decisao"] == "espera_encerrada_inelegivel",
    f"n=232: {len(rs4)} reações, espera mantida; n=233: {len(rs5)} reação → {r_out['regs'][0]['decisao']}; pivô recente (barra 150) elegível: {bool(JN.zona_elegivel(S4.n(99.0), S4.mem.n_barras, 200, 'suporte'))}")
# Teste B × A após o rompimento com outro nível qualificado próximo
S5 = copy.deepcopy(S)
for _ in range(5): S5.barra(100.0)
S5.barra(98.6); S5.barra(100.0); S5.barra(100.0)
for _ in range(3): S5.barra(100.0)
S5.barra(98.7, c=100.4); S5.barra(100.0)                                              # 2ª reação do nível 98,6 (agrupado)
lvb = S5.n(99.0); eB = {"lado": -1, "nivel": lvb["id"], "sinal": "s5"}; zb = RQ.qualificado(S5.mem, S5.rc, lvb, "suporte")[0]
rA = RQ.decidir_q("A", S5.mem, S5.rc, eB, zb[0] - 0.05, zb[0] + 0.05, 99.9, 99.9, 101.0, 101.0, 99.3, zb[0] - 0.1, 1.0, "b", 0)
rB = RQ.decidir_q("B", S5.mem, S5.rc, eB, zb[0] - 0.05, zb[0] + 0.05, 99.9, 99.9, 101.0, 101.0, 99.3, zb[0] - 0.1, 1.0, "b", 0)
ob = rB["regs"][0]["obstaculo"]["bloqueador"]
reg("após romper o 1º nível com outro qualificado a ≤ 2×ATR: Teste A espera o 2º; Teste B arma o gatilho e registra o próximo com distância (preço, ATR, R)",
    rA["gat"] is None and rA["regs"][0].get("segundo_nivel") and rB["gat"] is not None and rB["regs"][0]["liberado_com_nivel_proximo"] and ob and ob["dist_R"] is not None,
    f"A: {rA['regs'][0]['decisao']}; B: {rB['regs'][0]['decisao']} · próximo {ob and ob['nivel']} d={ob and round(ob['distancia'], 3)} = {ob and round(ob['dist_atr'], 2)} ATR = {ob and round(ob['dist_R'], 2)} R")
# reinício e ausência de futuro com dados reais
m15 = ST.ler("XAUUSD", "M15").iloc[:3000].reset_index(drop=True); m1a = ST.ler("XAUUSD", "M1"); m1 = m1a[m1a.t < m15.t.iloc[-1] + pd.Timedelta(minutes=15)].reset_index(drop=True)
full = RQ.ReplayQ("XAUUSD", m15, m1, "A"); full.rodar(); d = tempfile.mkdtemp()
a = RQ.ReplayQ("XAUUSD", m15, m1, "A"); a.rodar(i1=2000); ST.salvar_estado(a, f"{d}/m.json", f"{d}/e.json", 2000); json.dump(a.reac.para_json(), open(f"{d}/r.json", "w"))
b = RQ.ReplayQ("XAUUSD", m15, m1, "A"); ip = ST.carregar_estado(b, f"{d}/m.json", f"{d}/e.json"); b.reac = RQ.Reacoes.de_json(json.load(open(f"{d}/r.json")))
mem = b.mem; nb = mem.nova_barra
def nb2(t_ab, t_fecha, o, h, l, c, mem=mem, nb=nb, rp=b):
    cp = mem.c_ant; ev = nb(t_ab, t_fecha, o, h, l, c); rp.reac.atualizar(mem, ev, h, l, c, cp, mem.atr, t_fecha); return ev
mem.nova_barra = nb2; b.rodar(i0=ip)
reg("reinício (memória + reações + espera + gatilho) reproduz as mesmas decisões", [(r["decisao"], r["barra"]) for r in b.reg] == [(r["decisao"], r["barra"]) for r in full.reg] and len(b.ops) == len(full.ops),
    f"{len(full.reg)} decisões e {len(full.ops)} operações idênticas")
t2 = RQ.ReplayQ("XAUUSD", m15.iloc[:2000].reset_index(drop=True), m1[m1.t < m15.t.iloc[1999] + pd.Timedelta(minutes=15)].reset_index(drop=True), "A"); t2.rodar()
reg("sem dados futuros: reações e memória com dados até a barra 2.000 = estado da execução completa naquela barra", json.dumps(t2.reac.s, sort_keys=True, default=str) == json.dumps(a.reac.s, sort_keys=True, default=str)
    and json.dumps(t2.mem.niveis, sort_keys=True) == json.dumps(a.mem.niveis, sort_keys=True), f"{sum(len(v['lista']) for v in a.reac.s.values())} reações iguais")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
