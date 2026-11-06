"""BotTested · ORDEM 039 · LEITOR EM MODO SOMBRA da memória estrutural (estrutura-0.1) e da prioridade de suporte/resistência (ESTR-EMA-M15-0.1, V0 e V1).
NÃO envia ordens, NÃO altera stops, NÃO toca a campanha (LM-0.2), a sombra 0.4, o ROMP ou outros bots. Só registra.
- Inicialização: reconstrói a memória com as 200 últimas M15 CONCLUÍDAS (experimental) ou restaura o estado gravado; depois, incremental.
- Cada M15 concluída: atualiza a memória (níveis, estados, histórico) e decide V0 e V1 com a MESMA função do replay (estrategia_o39.decidir_puro).
- Gatilho armado: observa os ticks (bid) SÓ durante a barra seguinte; registra a superação observada (bid, ask, spread, horário) ou a expiração.
- Barras perdidas durante desconexão: memória atualizada em ordem; decisões NÃO são retroativas (registrado).
Uso: python bt_estrutura_sombra_o39.py --ativo XAUUSD|BTCUSD [--config config_execucao.json]   (teste: --falso CSV --agora "AAAA-MM-DD HH:MM" --uma-vez)"""
import os, sys, json, time, argparse, traceback
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import bt_lm_executor_v036 as EX, estrutura_o39 as ES, estrategia_o39 as ST, romp_m15 as RM
VERSAO_MODULO = "bt_estrutura_sombra_o39"; EX.VERSAO_MODULO = VERSAO_MODULO; ts, agora_utc = EX.ts, EX.agora_utc; MIN = 60 * 10**9; N_INI = 200


class Sombra:
    def __init__(self, mt5, cfg, ativo, pasta, classe):
        self.mt5, self.at, self.nome = mt5, ativo, (cfg.get("simbolos") or {}).get(ativo, ativo); os.makedirs(pasta, exist_ok=True); self.pasta = pasta
        self.D = EX.Diario(pasta, classe); self.v = f"{ST.VERSAO} · {ES.VERSAO} · {VERSAO_MODULO}"; self.f_mem = os.path.join(pasta, "memoria_M15.json"); self.f_est = os.path.join(pasta, "estado_sombra_o39.json")
        if os.path.exists(self.f_mem) and os.path.exists(self.f_est):
            self.mem = ES.Memoria.carregar(self.f_mem); self.e = json.load(open(self.f_est)); self.g("restaurado", "status", agora_utc(), {"evento": "memória e gatilhos restaurados", "niveis": len(self.mem.niveis), "ultima_barra": self.e["ult"]})
        else:
            si = mt5.symbol_info(self.nome); self.mem = ES.Memoria(ativo, "M15", getattr(si, "trade_tick_size", None) or si.point); self.e = {"ult": None, "V0": {"gat": None, "espera": None, "obs": None}, "V1": {"gat": None, "espera": None, "obs": None}}
            b = self.barras(N_INI)
            for r in b.itertuples(): self.mem.nova_barra(str(r.t), str(r.t + pd.Timedelta(minutes=15)), r.o, r.h, r.l, r.c)
            self.e["ult"] = int(b.t.iloc[-1].value); self.salvar()
            self.g(f"init|{self.e['ult']}", "status", agora_utc(), {"evento": f"memória reconstruída com as {len(b)} últimas M15 concluídas", "niveis": len(self.mem.niveis), "primeira": str(b.t.iloc[0]), "ultima": str(b.t.iloc[-1])})

    def g(self, chave, tipo, t, payload): self.D.gravar(f"{self.at}|o39|{chave}", tipo, self.at, t, payload, self.v)

    def salvar(self):
        self.mem.salvar(self.f_mem); tmp = self.f_est + ".tmp"; json.dump(self.e, open(tmp, "w"), default=str); os.replace(tmp, self.f_est)

    def barras(self, n):
        r = self.mt5.copy_rates_from_pos(self.nome, self.mt5.TIMEFRAME_M15, 1, n)
        if r is None or len(r) == 0: raise RuntimeError(f"sem M15: {self.mt5.last_error()}")
        d = pd.DataFrame(r); d["t"] = pd.to_datetime(d["time"], unit="s"); return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c"]].reset_index(drop=True)

    def ciclo(self):
        tk = self.mt5.symbol_info_tick(self.nome); agora = int(tk.time) * 10**9 if tk else None
        self.observar_gatilhos(tk, agora)
        b = self.barras(3000); novas = b[b.t.values.astype("datetime64[ns]").astype(np.int64) > self.e["ult"]]
        if not len(novas): return
        if len(novas) > 1: self.g(f"perdidas|{int(novas.t.iloc[0].value)}", "informacao", ts(int(novas.t.iloc[-1].value)), {"evento": f"{len(novas) - 1} barra(s) M15 concluída(s) sem leitura (desconexão): memória atualizada em ordem; decisões NÃO retroativas"})
        EH = pd.Series(b.h).ewm(span=20, adjust=False).mean().values; EL = pd.Series(b.l).ewm(span=20, adjust=False).mean().values; A = RM.atr_wilder(b.h, b.l, b.c)
        for k, r in enumerate(novas.itertuples()):
            fim = int(r.t.value) + 15 * MIN; evs = self.mem.nova_barra(str(r.t), str(pd.Timestamp(fim)), r.o, r.h, r.l, r.c); i = int(np.searchsorted(b.t.values, np.datetime64(r.t)))
            if evs: self.g(f"memoria|{fim}", "informacao", ts(fim), {"eventos_estruturais": evs, "niveis_total": len(self.mem.niveis)})
            self.e["ult"] = int(r.t.value)
            if k < len(novas) - 1 or not np.isfinite(A[i]): continue
            for v in ("V0", "V1"):
                st = self.e[v]
                res = ST.decidir_puro(v, self.mem, st["espera"], b.c[i], b.c[i - 1], EL[i], EL[i - 1], EH[i], EH[i - 1], b.h[i], b.l[i], A[i], str(r.t), fim, evs)
                st["espera"] = res["espera"]
                if res["gat"] is not None: st["gat"] = {**res["gat"], "barra_valida": fim, "observado": False}
                for x in res["regs"]: self.g(f"{v}|{x['decisao']}|{fim}", "decisao", ts(fim), {"versao_regra": v, **x, "modo": "SOMBRA — nenhuma ordem"})
        self.salvar()

    def observar_gatilhos(self, tk, agora):
        if tk is None: return
        for v in ("V0", "V1"):
            g = self.e[v]["gat"]
            if g is None: continue
            ini, fim = g["barra_valida"], g["barra_valida"] + 15 * MIN
            if agora >= fim:
                if not g["observado"]: self.g(f"{v}|expirou|{ini}", "decisao", ts(fim), {"versao_regra": v, "decisao": "gatilho_expirado", "motivo": "a barra seguinte terminou sem superação observada (igualar não confirma)", "nivel_gatilho": g["nivel_gatilho"]})
                self.e[v]["gat"] = None; continue
            if agora < ini or g["observado"]: continue
            s = g["lado"]; ok = (tk.bid <= g["nivel_gatilho"] + 1e-9) if s < 0 else (tk.bid >= g["nivel_gatilho"] - 1e-9)
            if ok:
                g["observado"] = True
                self.g(f"{v}|superacao|{ini}", "decisao", ts(agora), {"versao_regra": v, "decisao": "superacao_observada", "motivo": f"bid {tk.bid} {'≤' if s < 0 else '≥'} {g['nivel_gatilho']:.2f} (≥ 1 tick além do extremo)",
                                                                   "bid": tk.bid, "ask": tk.ask, "spread": round(tk.ask - tk.bid, 5), "preco_executavel": tk.bid if s < 0 else tk.ask, "referencia": g["referencia"], "tipo_referencia": g["tipo"],
                                                                   "modo": "SOMBRA — nenhuma ordem enviada"})
        self.salvar()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ativo", required=True); ap.add_argument("--config", default=os.path.join(AQUI, "config_execucao.json")); ap.add_argument("--pasta", default=None)
    ap.add_argument("--falso"); ap.add_argument("--agora"); ap.add_argument("--uma-vez", action="store_true"); a = ap.parse_args()
    cfg = dict(EX.CFG_PADRAO); cfg.update({k: v for k, v in (json.load(open(a.config, encoding="utf-8")) if os.path.exists(a.config) else {}).items() if not k.startswith("_")})
    destino = EX.conferir_destino(cfg)
    if a.falso:
        import mt5_falso as mt5; mt5.configurar(a.falso, a.agora)
    else:
        import MetaTrader5 as mt5
        if not mt5.initialize(path=cfg.get("terminal_caminho") or None): raise SystemExit(f"MT5 não inicializou: {mt5.last_error()}")
        acc = mt5.account_info()
        if acc is None or acc.trade_mode != getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0): raise SystemExit("RECUSADO: conta não é DEMO")
    S = Sombra(mt5, cfg, a.ativo, a.pasta or os.path.join(AQUI, "campanha", a.ativo, "sombra_o39"), "simulado" if a.falso else "sombra")
    print(f"{VERSAO_MODULO} em MODO SOMBRA · {S.v} · nenhuma ordem · destino {destino or 'só registro local'}", flush=True)
    env = EX.Envio(S.pasta, cfg["plataforma_url"], cfg["bot_token"], print); env.start()
    while True:
        if os.path.exists(os.path.join(AQUI, "PARAR")): break
        try: S.ciclo()
        except EX.RegistroFalhou as e: raise SystemExit(f"registro local falhou: {e}")
        except Exception as e: S.g(f"erro|{int(time.time())}", "erro", agora_utc(), {"erro": str(e), "trace": traceback.format_exc(limit=3)})
        if a.uma_vez: break
        time.sleep(cfg["laco_s"])
    env.parar = True; mt5.shutdown()


if __name__ == "__main__": main()
