"""BotTested · ORDEM 042 · LEITOR EM MODO SOMBRA — V1-200 (Referência) e as variantes Entrada (E), Saída (S) e Combinada (E+S) com leitura M1/M5.
NÃO envia ordens. As posições são VIRTUAIS (comparação). Campanha LM-0.2, sombra 0.4, ROMP e outros bots intocados.
Funcionamento: a cada M15 concluída, reconstitui minuto a minuto a barra com as M1 FECHADAS, usando o MESMO motor do replay (leitura_o42.ReplayM1).
As decisões levam o horário do minuto em que seriam tomadas (só com dados disponíveis naquele minuto); o registro é gravado no fechamento da M15
(até 15 min depois). Memória inicial: 200 M15 concluídas; depois incremental. Estado persistido; reinício não duplica.
Uso: python bt_estrutura_sombra_o42.py --ativo XAUUSD|BTCUSD [--config config_execucao.json]   (teste: --falso CSV --agora "AAAA-MM-DD HH:MM" --uma-vez)"""
import os, sys, json, time, argparse, traceback
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import bt_lm_executor_v036 as EX, estrutura_o39 as ES, estrategia_o39 as ST, janela_o40 as JN, leitura_o42 as LQ
VERSAO_MODULO = "bt_estrutura_sombra_o42"; EX.VERSAO_MODULO = VERSAO_MODULO; MIN = 60 * 10**9; N_INI = 200; N_JAN = 1200
VARS = {"Ref": (False, False), "E": (True, False), "S": (False, True), "ES": (True, True)}


class Sombra:
    def __init__(self, mt5, cfg, ativo, pasta, classe):
        self.mt5, self.at, self.nome = mt5, ativo, (cfg.get("simbolos") or {}).get(ativo, ativo); os.makedirs(pasta, exist_ok=True); self.pasta = pasta
        self.D = EX.Diario(pasta, classe); self.v = f"{ST.VERSAO} · {JN.VERSAO} · {LQ.VERSAO} · {VERSAO_MODULO}"; self.f = lambda v, x: os.path.join(pasta, f"o42_{v}_{x}.json")
        self.f_ult = os.path.join(pasta, "o42_ultima_barra.json")
        self.ult = json.load(open(self.f_ult))["ult"] if os.path.exists(self.f_ult) else None

    def g(self, chave, tipo, t, payload, op=None): self.D.gravar(f"{self.at}|o42|{chave}", tipo, self.at, t, payload, self.v, op)

    def dados(self):
        m = self.mt5; r15 = m.copy_rates_from_pos(self.nome, m.TIMEFRAME_M15, 1, N_JAN); r1 = m.copy_rates_from_pos(self.nome, m.TIMEFRAME_M1, 1, N_JAN * 15 + 30)
        if r15 is None or r1 is None: raise RuntimeError(f"sem dados: {m.last_error()}")
        f = lambda r: pd.DataFrame(r).assign(t=lambda d: pd.to_datetime(d["time"], unit="s")).rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c", "spread"]].reset_index(drop=True)
        m15, m1 = f(r15), f(r1); m1 = m1[m1.t >= m15.t.iloc[0]].reset_index(drop=True); return m15, m1

    def ciclo(self):
        m15, m1 = self.dados(); ult = int(m15.t.iloc[-1].value)
        if self.ult == ult: return
        t15 = m15.t.values.astype("datetime64[ns]").astype(np.int64)
        for v, (e, s) in VARS.items():
            rp = LQ.ReplayM1(self.at, m15, m1, v, entrada=e, saida=s)
            if self.ult is None:                                                     # 1ª vez: memória com as 200 últimas M15 (sem decisões registradas)
                i0 = len(m15) - N_INI; rp.mem = ES.Memoria(self.at, "M15", 0.01)
                for i in range(i0, len(m15)): rp.mem.nova_barra(str(m15.t.iloc[i]), str(m15.t.iloc[i] + pd.Timedelta(minutes=15)), *(float(m15[k].iloc[i]) for k in "ohlc"))
                ST.salvar_estado(rp, self.f(v, "mem"), self.f(v, "est"), 0); continue
            ST.carregar_estado(rp, self.f(v, "mem"), self.f(v, "est")); n_reg, n_ops = len(rp.reg), len(rp.ops)
            if rp.pos is not None: rp.pos["j_ent"] = int(np.searchsorted(rp.t1, rp.pos["t_ent"]))   # índices da janela atual
            i0 = int(np.searchsorted(t15, self.ult, side="right")); rp.rodar(i0=i0)
            for r in rp.reg[n_reg:]: self.g(f"{v}|{r['decisao']}|{r['barra']}|{r.get('t_m1', '')}", "decisao", r["barra"], {"versao_regra": v, **{k: x for k, x in r.items() if k != "versao"}, "modo": "SOMBRA — nenhuma ordem"}, r.get("id"))
            for o in rp.ops[n_ops:]: self.g(f"{v}|resultado_virtual|{o['id']}", "resultado", str(pd.Timestamp(int(o["t_sai"]))), {"versao_regra": v, "virtual": True, **{k: o[k] for k in ("lado", "entrada", "stop", "saida", "motivo_saida", "R", "t_ent", "t_sai")}}, o["id"])
            rp.reg, rp.ops = rp.reg[-200:], rp.ops[-200:]; ST.salvar_estado(rp, self.f(v, "mem"), self.f(v, "est"), 0)
        if self.ult is None: self.g(f"init|{ult}", "status", agora(), {"evento": f"memória reconstruída com as {N_INI} últimas M15 concluídas (4 variantes)"})
        self.ult = ult; json.dump({"ult": ult}, open(self.f_ult, "w"))


def agora(): return EX.agora_utc()


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
    S = Sombra(mt5, cfg, a.ativo, a.pasta or os.path.join(AQUI, "campanha", a.ativo, "sombra_o42"), "simulado" if a.falso else "sombra")
    print(f"{VERSAO_MODULO} em MODO SOMBRA · {S.v} · nenhuma ordem · destino {destino or 'só registro local'}", flush=True)
    env = EX.Envio(S.pasta, cfg["plataforma_url"], cfg["bot_token"], print); env.start()
    while True:
        if os.path.exists(os.path.join(AQUI, "PARAR")): break
        try: S.ciclo()
        except EX.RegistroFalhou as e: raise SystemExit(f"registro local falhou: {e}")
        except Exception as e: S.g(f"erro|{int(time.time())}", "erro", agora(), {"erro": str(e), "trace": traceback.format_exc(limit=3)})
        if a.uma_vez: break
        time.sleep(cfg["laco_s"])
    env.parar = True; mt5.shutdown()


if __name__ == "__main__": main()
