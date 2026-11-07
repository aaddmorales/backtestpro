"""BotTested · ORDEM 043 · LEITOR EM MODO SOMBRA — rompimento da lateralização M15 com confirmação IMEDIATA M1/M5 (regras R0, R1 e R2 em paralelo).
NÃO envia ordens. Posições VIRTUAIS (comparação). Campanha LM-0.2, sombra 0.4, O42, ROMP e outros bots intocados.
A cada M15 concluída: reconstitui a barra com as M1 FECHADAS usando o MESMO motor do replay (formacao_o43.Motor.barra). Decisões levam o horário
do minuto em que seriam tomadas (só dados disponíveis naquele minuto); o registro é gravado no fechamento da M15. Memória inicial: 200 M15 concluídas.
Estado persistido (memória, fundos já usados, sinal pendente, posições virtuais); reinício não duplica.
Uso: python bt_lateral_sombra_o43.py --ativo XAUUSD|BTCUSD [--config config_execucao.json]   (teste: --falso CSV --agora "AAAA-MM-DD HH:MM" --uma-vez)"""
import os, sys, json, time, argparse, traceback
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import bt_lm_executor_v036 as EX, estrutura_o39 as ES, formacao_o43 as FO
VERSAO_MODULO = "bt_lateral_sombra_o43"; EX.VERSAO_MODULO = VERSAO_MODULO; N_INI = 200; N_JAN = 1200


class Sombra:
    def __init__(self, mt5, cfg, ativo, pasta, classe):
        self.mt5, self.at, self.nome = mt5, ativo, (cfg.get("simbolos") or {}).get(ativo, ativo); os.makedirs(pasta, exist_ok=True); self.pasta = pasta
        self.D = EX.Diario(pasta, classe); self.v = f"{FO.VERSAO} · {VERSAO_MODULO}"
        self.f_mem, self.f_est, self.f_ult = (os.path.join(pasta, f"o43_{x}.json") for x in ("mem", "est", "ultima_barra"))
        self.ult = json.load(open(self.f_ult))["ult"] if os.path.exists(self.f_ult) else None

    def g(self, chave, tipo, t, payload, op=None): self.D.gravar(f"{self.at}|o43|{chave}", tipo, self.at, t, payload, self.v, op)

    def dados(self):
        m = self.mt5; r15 = m.copy_rates_from_pos(self.nome, m.TIMEFRAME_M15, 1, N_JAN); r1 = m.copy_rates_from_pos(self.nome, m.TIMEFRAME_M1, 1, N_JAN * 15 + 30)
        if r15 is None or r1 is None: raise RuntimeError(f"sem dados: {m.last_error()}")
        f = lambda r: pd.DataFrame(r).assign(t=lambda d: pd.to_datetime(d["time"], unit="s")).rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c", "spread"]].reset_index(drop=True)
        m15, m1 = f(r15), f(r1); m1 = m1[m1.t >= m15.t.iloc[0]].reset_index(drop=True); return m15, m1

    def ciclo(self):
        m15, m1 = self.dados(); ult = int(m15.t.iloc[-1].value)
        if self.ult == ult: return
        M = FO.Motor(self.at, m15, m1)
        if self.ult is None:                                                              # 1ª vez: memória com as 200 últimas M15 (sem decisões)
            M.mem = ES.Memoria(self.at, "M15", 0.01)
            for i in range(len(m15) - N_INI, len(m15)): M.mem.nova_barra(str(m15.t.iloc[i]), str(m15.t.iloc[i] + pd.Timedelta(minutes=15)), *(float(m15[k].iloc[i]) for k in "ohlc"))
            FO.salvar_estado(M, self.f_mem, self.f_est)
            self.g(f"init|{ult}", "status", agora(), {"evento": f"memória reconstruída com as {N_INI} últimas M15 concluídas (R0, R1, R2)", "modo": "SOMBRA — nenhuma ordem"})
        else:
            FO.carregar_estado(M, self.f_mem, self.f_est); t15 = m15.t.values.astype("datetime64[ns]").astype(np.int64)
            i0 = int(np.searchsorted(t15, self.ult, side="right")); M.rodar(i0=i0)
            for r in M.reg:
                self.g(f"{r['decisao']}|{r['barra']}|{r.get('regra', '')}|{r.get('sinal', r.get('id', ''))}", "decisao", r["barra"], {**{k: x for k, x in r.items() if k != "versao"}, "modo": "SOMBRA — nenhuma ordem"}, r.get("id"))
            for rg in FO.REGRAS:
                for o in M.ops[rg]:
                    self.g(f"resultado_virtual|{o['id']}", "resultado", str(pd.Timestamp(int(o["t_sai"]))), {"regra": rg, "virtual": True, **{k: o[k] for k in ("lado", "entrada", "stop", "saida", "motivo_saida", "R", "t_ent", "t_sai", "ambiguo")}}, o["id"])
            FO.salvar_estado(M, self.f_mem, self.f_est)
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
    S = Sombra(mt5, cfg, a.ativo, a.pasta or os.path.join(AQUI, "campanha", a.ativo, "sombra_o43"), "simulado" if a.falso else "sombra")
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
