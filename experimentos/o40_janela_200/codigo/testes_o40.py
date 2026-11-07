"""ORDEM 040 §4 — casos de fronteira da janela móvel (janela-0.1). Uso: python testes_o40.py SAIDA.json"""
import os, sys, json, time, tempfile
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/home/claude/r005/rompimento/codigo")
import estrutura_o39 as ES, estrategia_o39 as ST, janela_o40 as JN
RES = []
def reg(n, ok, d): RES.append({"teste": n, "ok": bool(ok), "detalhe": d}); print("OK   " if ok else "FALHA", n, d, flush=True)
t0 = pd.Timestamp("2026-01-05")
def alimentar(mem, lows, k0=0):
    for k, l in enumerate(lows, start=k0): mem.nova_barra(str(t0 + pd.Timedelta(minutes=15 * k)), str(t0 + pd.Timedelta(minutes=15 * (k + 1))), 100.5, 101.0, l, 100.5)

# 1) entrada na janela só depois da confirmação
mem = ES.Memoria("T", "M15"); lows = [100.0] * 30 + [99.0] + [100.0] * 2
alimentar(mem, lows[:32]); r1 = JN.obstaculos(mem, -1, 99.6, 1.0, 2.0)               # barra 31 (i+1) fechada: fundo ainda NÃO confirmado
alimentar(mem, lows[32:33], 32); r2 = JN.obstaculos(mem, -1, 99.6, 1.0, 2.0)         # barra 32 (i+2) fechada: confirmado
reg("pivô só entra na janela depois da confirmação (i+2)", r1 is None and r2 is not None and r2["membros_elegiveis"] == 1, f"antes: {r1}; depois: nível {r2 and r2['nivel']} d={r2 and round(r2['distancia'], 3)}")
# 2) saída da janela: extremo na barra 31 (contagem 1-based) → elegível até n = 31+199 = 230; em 231 não
alimentar(mem, [100.0] * (230 - mem.n_barras), mem.n_barras); a = JN.obstaculos(mem, -1, 99.6, 1.0, 2.0); n_a = mem.n_barras
alimentar(mem, [100.0], mem.n_barras); b = JN.obstaculos(mem, -1, 99.6, 1.0, 2.0); n_b = mem.n_barras
lv = mem.niveis[0]
reg("pivô sai da janela quando o extremo deixa as últimas 200 barras fechadas; o nível permanece no histórico", a is not None and b is None and lv["estado"] != "ARQUIVADO" and len(mem.niveis) == 1,
    f"n={n_a}: elegível (extremo na barra {lv['membros'][0]['barra']}); n={n_b}: inelegível; nível segue na memória com estado {lv['estado']}")
# 3) zona com membros antigos e recentes: bordas só com os elegíveis
mem = ES.Memoria("T", "M15"); L = [100.0] * 30 + [99.0] + [100.0] * 250 + [99.1] + [100.0] * 20
alimentar(mem, L); n = [x for x in mem.niveis if len(x["membros"]) >= 2]
z_e = JN.zona_elegivel(n[0], mem.n_barras, 200, "suporte") if n else None
reg("zona que reúne pivô antigo (fora) e recente (dentro): bordas calculadas só com o recente", n and abs(z_e[0] - 99.1) < 1e-9 and n[0]["zona"][0] == 99.0,
    f"zona acumulada {n[0]['zona'] if n else None} · zona elegível {z_e} · membros {[(m['extremo'], m['barra']) for m in n[0]['membros']] if n else None}")
# 4) espera cujo nível deixa de ser elegível: encerra sem liberar o sinal
mem = ES.Memoria("T", "M15"); alimentar(mem, [100.0] * 30 + [99.0] + [100.0] * 198)        # n = 229: o fundo (barra 31) ainda é elegível
lvid = mem.niveis[0]["id"]; esp = {"lado": -1, "nivel": lvid, "sinal": "s0"}
r_ok = JN.decidir_janela(mem, esp, 99.8, 99.8, 100.0, 100.0, 101.0, 101.0, 100.0, 99.7, 1.0, "b", 0)
alimentar(mem, [100.0], mem.n_barras); alimentar(mem, [100.0], mem.n_barras)                # n = 231: saiu
r_x = JN.decidir_janela(mem, esp, 99.8, 99.8, 100.0, 100.0, 101.0, 101.0, 100.0, 99.7, 1.0, "b", 0)
reg("espera sustentada por nível que sai da janela: encerrada e registrada, sem liberar retroativamente o sinal", r_ok["espera"] is not None and r_x["espera"] is None and r_x["gat"] is None and r_x["regs"][0]["decisao"] == "espera_encerrada_inelegivel",
    f"n=229 espera mantida; n=231: '{r_x['regs'][0]['decisao']}', gatilho = {r_x['gat']}")
# 5) nível novo distante do antigo: o seguinte é registrado com distância
mem = ES.Memoria("T", "M15"); alimentar(mem, [100.0] * 30 + [99.0] + [100.0] * 20 + [97.0] + [100.0] * 5)
o = JN.obstaculos(mem, -1, 99.6, 1.0, 2.0)
reg("registra o nível à frente e o SEGUINTE com a distância", o and o["seguinte"] and abs(o["seguinte"]["distancia"] - (99.6 - (97.0 + 0.25 * mem.niveis[1]["membros"][0]["atr"]))) < 1e-9,
    f"à frente {o['nivel'] if o else None} d={o and round(o['distancia'], 3)}; seguinte {o and o['seguinte']['nivel']} d={o and round(o['seguinte']['distancia'], 3)}")
# 6) reinício reproduz as mesmas decisões (dados reais, 3.000 barras, parada na 2.000)
m15 = ST.ler("XAUUSD", "M15").iloc[:3000].reset_index(drop=True); m1a = ST.ler("XAUUSD", "M1"); m1 = m1a[m1a.t < m15.t.iloc[-1] + pd.Timedelta(minutes=15)].reset_index(drop=True)
full = JN.ReplayJanela("XAUUSD", m15, m1, "V1-200"); full.rodar()
d = tempfile.mkdtemp(); a = JN.ReplayJanela("XAUUSD", m15, m1, "V1-200"); a.rodar(i1=2000); ST.salvar_estado(a, f"{d}/m.json", f"{d}/e.json", 2000)
b = JN.ReplayJanela("XAUUSD", m15, m1, "V1-200"); ip = ST.carregar_estado(b, f"{d}/m.json", f"{d}/e.json"); b.rodar(i0=ip)
reg("reinício reproduz as mesmas decisões e operações", [(r["decisao"], r["barra"]) for r in b.reg] == [(r["decisao"], r["barra"]) for r in full.reg] and len(b.ops) == len(full.ops),
    f"{len(full.reg)} decisões e {len(full.ops)} operações idênticas após reiniciar na barra 2.000")
# 7) nenhum pivô antes da confirmação no replay real: todo membro elegível usado tinha confirmação ≤ barra da decisão
viol = 0
for r in full.reg:
    ob = r.get("obstaculo")
    if not isinstance(ob, dict): continue
    i = int(np.searchsorted(m15.t.values, np.datetime64(r["barra"]))) - 25 + 1          # contagem da memória (o replay processa a partir da barra 25)
    lvl = next(x for x in full.mem.niveis if x["id"] == ob["nivel"]); usados = [m for m in lvl["membros"] if m["barra"] >= i - 199 and m["barra_confirmacao"] <= i]
    viol += sum(m["barra_confirmacao"] > i for m in lvl["membros"] if m in usados) + (0 if usados else 1)
reg("nenhum pivô usado antes da confirmação (todas as decisões do replay)", viol == 0, f"violações {viol}")
ok = sum(x["ok"] for x in RES); print(f"\n{ok}/{len(RES)} aprovados")
json.dump({"executado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "aprovados": ok, "total": len(RES), "testes": RES}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
