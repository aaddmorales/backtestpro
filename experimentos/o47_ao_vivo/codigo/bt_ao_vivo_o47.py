"""BotTested · ORDEM 047 · LEITOR AO VIVO (SOMBRA) — R0 da O44 em M15, M30 e H1 de UM ativo, por tick (bid/ask do MT5), posições VIRTUAIS.
NÃO envia ordens (não chama order_send/order_check). Campanha, DEMO, sombra 0.4, O42/O43, ROMP e outros bots intocados.
Um processo por ativo: as 3 instâncias (M15, M30, H1) recebem o MESMO fluxo de ticks, cada uma com a própria posição virtual.
Ordem dos eventos: fechamento de barra do TF antes dos ticks ≥ fim da barra; ticks além da barra ainda não fechada no terminal ficam para o ciclo seguinte.
Reinício: busca no histórico de ticks do terminal desde o último processado; nada é gravado 2×.
Uso: python bt_ao_vivo_o47.py --ativo XAUUSD|BTCUSD --inicio "AAAA-MM-DD" [--config config_execucao.json]
     (teste: --falso CSV --agora "AAAA-MM-DD HH:MM" --uma-vez)"""
import os, sys, json, time, argparse, traceback
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import bt_lm_executor_v036 as EX, ao_vivo_o47 as AV
VERSAO_MODULO = "bt_ao_vivo_o47"; EX.VERSAO_MODULO = VERSAO_MODULO; N_JAN = 1200; GAP_MS = 5 * 60_000; JAN_RET_MS = 15 * 60_000


class Leitor:
    def __init__(self, mt5, cfg, ativo, pasta, classe, inicio):
        self.mt5, self.at, self.nome = mt5, ativo, (cfg.get("simbolos") or {}).get(ativo, ativo); os.makedirs(pasta, exist_ok=True); self.pasta = pasta
        self.D = EX.Diario(pasta, classe); self.v = f"{AV.VERSAO} · {VERSAO_MODULO}"; self.f_est = os.path.join(pasta, "o47_estado.json")
        self.TF = {"M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1}; self.I = {tf: AV.Instancia(ativo, tf) for tf in self.TF}
        self.inicio_ms = int(pd.Timestamp(inicio).value // 10**6); self.ult_tick_ms = None; self.conectado = True; self.ret_pend = []; self.n_ev = {tf: 0 for tf in self.TF}; self.n_sig = {tf: 0 for tf in self.TF}; self.n_op = {tf: 0 for tf in self.TF}
        for i in self.I.values(): i.ativo_desde_ms = self.inicio_ms
        if os.path.exists(self.f_est):
            d = json.load(open(self.f_est)); self.ult_tick_ms, self.ret_pend = d["ult_tick_ms"], d["ret_pend"]
            for tf, x in d["inst"].items(): self.I[tf].restaurar(x)
        self.g("status", agora(), {"evento": "leitor iniciado", "inicio_congelado": str(pd.Timestamp(self.inicio_ms, unit="ms")), "retomado_de": None if self.ult_tick_ms is None else str(pd.Timestamp(self.ult_tick_ms, unit="ms")),
                                    "modo": "SOMBRA AO VIVO — nenhuma ordem"}, chave=f"status|inicio|{int(time.time())}")

    def g(self, tipo, t, payload, chave, op=None): self.D.gravar(f"{self.at}|o47|{chave}", tipo, self.at, t, payload, self.v, op)

    def rates(self, tf):
        r = self.mt5.copy_rates_from_pos(self.nome, self.TF[tf], 1, N_JAN)
        if r is None or not len(r): return None
        return pd.DataFrame(r).assign(t=lambda d: pd.to_datetime(d["time"], unit="s")).rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c", "spread"]]

    def ciclo(self):
        m = self.mt5; ti = m.terminal_info(); con = bool(getattr(ti, "connected", True))
        if con != self.conectado:
            self.conectado = con; self.g("dados", agora(), {"evento": "reconexão" if con else "desconexão", "terminal_conectado": con}, chave=f"conexao|{'on' if con else 'off'}|{time.time_ns()}")
        if not con: return
        R = {tf: self.rates(tf) for tf in self.TF}
        if any(r is None for r in R.values()): self.g("dados", agora(), {"evento": "sem candles do terminal", "erro": str(m.last_error())}, chave=f"semdados|{int(time.time() // 60)}"); return
        q = m.symbol_info_tick(self.nome)
        if q is None: return
        agora_ms = int(q.time_msc); de_ms = (self.ult_tick_ms + 1) if self.ult_tick_ms is not None else max(self.inicio_ms - 3_600_000, agora_ms - 3_600_000)
        tk = m.copy_ticks_range(self.nome, pd.Timestamp(de_ms, unit="ms").to_pydatetime(), pd.Timestamp(agora_ms + 1, unit="ms").to_pydatetime(), getattr(m, "COPY_TICKS_INFO", 1))
        if tk is None: self.g("dados", agora(), {"evento": "copy_ticks_range sem resposta", "erro": str(m.last_error())}, chave=f"semticks|{int(time.time() // 60)}"); return
        T, B, A = tk["time_msc"].astype(np.int64), tk["bid"].astype(float), tk["ask"].astype(float)
        # fechamentos pendentes por TF (barras fechadas ainda não processadas), em ordem
        TM = {tf: R[tf].t.values.astype("datetime64[ms]").astype(np.int64) for tf in self.TF}
        fil = {tf: ([len(TM[tf]) - 1] if self.I[tf].ult_barra_ms is None else list(np.nonzero(TM[tf] > self.I[tf].ult_barra_ms)[0])) for tf in self.TF}
        dur = {tf: self.I[tf].dur_ms for tf in self.TF}
        # um tick só é processado se, em cada TF, a barra do tick anterior já apareceu FECHADA no terminal quando o tick está numa barra posterior
        ult_ab = {tf: int(TM[tf][-1]) for tf in self.TF}; lim = None; ant = self.ult_tick_ms
        for n in range(len(T)):
            t = int(T[n])
            if ant is not None and any((t // dur[tf]) > (ant // dur[tf]) and (ant // dur[tf]) * dur[tf] > ult_ab[tf] for tf in self.TF): lim = t; break
            ant = t
        evs = [(int(TM[tf][k]) + dur[tf], 0, tf, int(k)) for tf in self.TF for k in fil[tf]] + [(int(T[n]), 1, None, n) for n in range(len(T)) if lim is None or T[n] < lim]
        evs.sort(key=lambda e: (e[0], e[1]))
        for t, pri, tf, k in evs:
            if pri == 0:
                self.I[tf].fecha_barra(R[tf].iloc[:k + 1].reset_index(drop=True)); continue
            lac = self.ult_tick_ms is not None and t - self.ult_tick_ms > GAP_MS
            if lac: self.g("dados", str(pd.Timestamp(t, unit="ms")), {"evento": "período sem ticks", "de": str(pd.Timestamp(self.ult_tick_ms, unit="ms")), "ate": str(pd.Timestamp(t, unit="ms")), "minutos": round((t - self.ult_tick_ms) / 60000, 1)}, chave=f"gap|{self.ult_tick_ms}")
            for inst in self.I.values(): inst.tick(t, B[k], A[k], lac)
            self.ult_tick_ms = t
        self.registrar(R)

    def registrar(self, R):
        for tf, inst in self.I.items():
            for e in inst.eventos[self.n_ev[tf]:]: self.g("decisao", e["t"], {**e, "versao": AV.VERSAO}, chave=f"{tf}|{e['tipo']}|{e.get('sinal', e.get('id', ''))}|{e['t']}", op=e.get("id"))
            for s in inst.sinais[self.n_sig[tf]:]:
                if s.get("decisao") == "entrou": self.ret_pend.append({"tf": tf, "id": s["id"], "lado": s["lado"], "extremo": s["extremo"], "nivel": s["nivel"], "tau_ms": s["tau_ms"]})
            for o in inst.ops[self.n_op[tf]:]:
                self.g("resultado", str(pd.Timestamp(o["t_sai_ms"], unit="ms")), {"tf": tf, "virtual": True, **{k: v for k, v in o.items() if k not in ("saida_pendente",)}}, chave=f"{tf}|resultado|{o['id']}", op=o["id"])
            self.n_ev[tf], self.n_sig[tf], self.n_op[tf] = len(inst.eventos), len(inst.sinais), len(inst.ops)
            inst.eventos, inst.sinais, inst.ops = [], [], []; self.n_ev[tf] = self.n_sig[tf] = self.n_op[tf] = 0
        # retorno A/B/C (diagnóstico, O45): janela de 15 min com fechamentos M1 do terminal, depois que a janela termina
        resta = []
        for r in self.ret_pend:
            if self.ult_tick_ms is None or self.ult_tick_ms < r["tau_ms"] + JAN_RET_MS + 60_000: resta.append(r); continue
            m1 = self.mt5.copy_rates_range(self.nome, self.mt5.TIMEFRAME_M1, pd.Timestamp(r["tau_ms"], unit="ms").floor("min").to_pydatetime(), pd.Timestamp(r["tau_ms"] + JAN_RET_MS - 1, unit="ms").to_pydatetime())
            c = [] if m1 is None else list(m1["close"]); s = r["lado"]; al = (lambda x, y: x > y + 1e-9) if s < 0 else (lambda x, y: x < y - 1e-9)
            grp = "C" if any(al(x, r["nivel"]) for x in c) else ("B" if any(al(x, r["extremo"]) for x in c) else "A")
            self.g("diagnostico", str(pd.Timestamp(r["tau_ms"], unit="ms")), {"tf": r["tf"], "sinal": r["id"], "grupo_retorno_15min": grp, "n_m1_janela": len(c), "completo": len(c) == 15}, chave=f"{r['tf']}|retorno|{r['id']}")
        self.ret_pend = resta
        json.dump({"ult_tick_ms": self.ult_tick_ms, "ret_pend": self.ret_pend, "inst": {tf: i.estado() for tf, i in self.I.items()}}, open(self.f_est + ".tmp", "w"), default=lambda x: x.item() if hasattr(x, "item") else str(x))
        os.replace(self.f_est + ".tmp", self.f_est)


def agora(): return EX.agora_utc()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ativo", required=True); ap.add_argument("--inicio", required=True); ap.add_argument("--config", default=os.path.join(AQUI, "config_execucao.json")); ap.add_argument("--pasta")
    ap.add_argument("--falso"); ap.add_argument("--agora"); ap.add_argument("--uma-vez", action="store_true"); a = ap.parse_args()
    cfg = dict(EX.CFG_PADRAO); cfg.update({k: v for k, v in (json.load(open(a.config, encoding="utf-8")) if os.path.exists(a.config) else {}).items() if not k.startswith("_")})
    destino = EX.conferir_destino(cfg)
    if a.falso:
        import mt5_falso_ticks as mt5; mt5.configurar(a.falso, a.agora)
    else:
        import MetaTrader5 as mt5
        if not mt5.initialize(path=cfg.get("terminal_caminho") or None): raise SystemExit(f"MT5 não inicializou: {mt5.last_error()}")
        acc = mt5.account_info()
        if acc is None or acc.trade_mode != getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0): raise SystemExit("RECUSADO: conta não é DEMO")
    L = Leitor(mt5, cfg, a.ativo, a.pasta or os.path.join(AQUI, "campanha", a.ativo, "ao_vivo_o47"), "simulado" if a.falso else "sombra_ao_vivo", a.inicio)
    print(f"{VERSAO_MODULO} · {L.v} · M15/M30/H1 · nenhuma ordem · destino {destino or 'só registro local'}", flush=True)
    env = EX.Envio(L.pasta, cfg["plataforma_url"], cfg["bot_token"], print); env.start()
    while True:
        if os.path.exists(os.path.join(AQUI, "PARAR")): break
        try: L.ciclo()
        except EX.RegistroFalhou as e: raise SystemExit(f"registro local falhou: {e}")
        except Exception as e: L.g("erro", agora(), {"erro": str(e), "trace": traceback.format_exc(limit=3)}, chave=f"erro|{int(time.time())}")
        if a.uma_vez: break
        time.sleep(1)
    env.parar = True; mt5.shutdown()


if __name__ == "__main__": main()
