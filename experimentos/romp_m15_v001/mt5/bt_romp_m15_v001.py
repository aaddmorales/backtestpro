"""BotTested · EXPERIÊNCIA SEPARADA · estratégia fixa ROMP-M15-0.1 (rompimento do canal de 20 barras M15, stop 2×ATR14 Wilder,
saída pelo canal de 10) · XAUUSD · conta MT5 DEMO apenas · módulo bt_romp_m15_v001.
- NÃO usa a LM para decidir (a LM não altera nem bloqueia). M1/M5 (leitura evolucao-0.1) são só registrados em cada decisão.
- Magic próprio (380380001); só toca posições com esse magic. Uma posição por vez. Recusa conta REAL e endereço de produção.
- Sem lote/risco autorizado na configuração → ordens BLOQUEADAS (cada sinal vira impedimento registrado; nada é inventado).
- Stop no servidor da corretora e conferido; se a proteção não for confirmada → a posição é encerrada na hora.
- Idempotência: um pedido por barra de sinal (id gravado ANTES do envio); depois de reinício/reconexão, a posição e o stop são recuperados
  pelo magic e nada é reenviado para a mesma barra.
Uso: python bt_romp_m15_v001.py [--config config_romp.json]   (teste: --falso CSV --agora "AAAA-MM-DD HH:MM" --uma-vez)"""
import os, sys, json, time, math, argparse, traceback, datetime
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import bt_lm_executor_v036 as EX                                    # só utilitários: registro encadeado, envio ao relatório, destino de homologação
import romp_m15 as RM, evolucao_o38 as EV
VERSAO_MODULO = "bt_romp_m15_v001"; EX.VERSAO_MODULO = VERSAO_MODULO; ts, agora_utc, agora_ms = EX.ts, EX.agora_utc, EX.agora_ms
CFG_PADRAO = {"simbolo": "XAUUSD", "magic": 380380001, "dimensionamento": {"modo": None, "valor": None}, "deviation_pts": 30, "terminal_caminho": "",
              "ambiente": "homolog", "plataforma_url": "https://lm-relatorio-homolog.up.railway.app", "bot_token": "", "laco_s": 2}
ATIVO = "XAUUSD"; MIN = 60 * 10**9


class Romp:
    def __init__(self, mt5, cfg, pasta, classe):
        self.mt5, self.cfg, self.pasta = mt5, cfg, pasta; os.makedirs(pasta, exist_ok=True); self.nome = cfg["simbolo"]; self.magic = int(cfg["magic"])
        self.D = EX.Diario(pasta, classe); self.v = f"{RM.VERSAO} · {VERSAO_MODULO}"; self.f_est = os.path.join(pasta, "estado_romp.json")
        self.est = json.load(open(self.f_est)) if os.path.exists(self.f_est) else {"ultima_barra": None, "posicao": None, "pedidos": {}}
        self.logf = open(os.path.join(pasta, "romp_log.txt"), "a", encoding="utf-8")
        si = mt5.symbol_info(self.nome)
        if si is None: raise SystemExit(f"símbolo {self.nome} inexistente no terminal")
        self.si = si; self.dim = cfg.get("dimensionamento") or {}

    def L(self, m):
        tok = self.cfg.get("bot_token") or ""
        if tok: m = str(m).replace(tok, "***")
        self.logf.write(f"{agora_utc()} {m}\n"); self.logf.flush(); print(m, flush=True)

    def salvar(self):
        tmp = self.f_est + ".tmp"; json.dump(self.est, open(tmp, "w"), default=str, indent=1); os.replace(tmp, self.f_est)

    def g(self, chave, tipo, t, payload, op=None): self.D.gravar(chave, tipo, ATIVO, t, payload, self.v, op)

    # ───── dados ─────
    def barras(self, tf, n):
        m = self.mt5; r = m.copy_rates_from_pos(self.nome, {"M1": m.TIMEFRAME_M1, "M5": m.TIMEFRAME_M5, "M15": m.TIMEFRAME_M15, "H1": m.TIMEFRAME_H1, "H4": m.TIMEFRAME_H4}[tf], 1, n)
        if r is None or len(r) == 0: raise RuntimeError(f"sem barras {tf}: {m.last_error()}")
        d = pd.DataFrame(r); d["t"] = pd.to_datetime(d["time"], unit="s"); return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c"]].reset_index(drop=True)

    def observacoes(self, fim_ns, lado):
        """M1/M5/M15 disponíveis no instante (só barras fechadas) — REGISTRO, sem efeito na decisão."""
        try:
            m1 = self.barras("M1", 6000); X = EV.Tabelas(m1).features(np.array([fim_ns], dtype=np.int64), np.array([lado or 1], float), True).iloc[0]
            ch = [f"{tf}_{k}" for tf in ("M1", "M5", "M15") for k in ("estr_rel", "cont_fav", "cont_con", "lateral", "exa_fav", "exa_con", "romp_con_ativo", "romp_fav_ativo", "dist_piv_con", "dist_piv_fav")]
            out = {k: (None if not np.isfinite(X[k]) else round(float(X[k]), 4)) for k in ch}
            ctx = {}
            for tf in ("H1", "H4"):
                d = self.barras(tf, 30); ctx[tf] = {"ultimo_fechamento": float(d.c.iloc[-1]), "maxima_20": float(d.h.tail(20).max()), "minima_20": float(d.l.tail(20).min())}
            return {"leitura": EV.VERSAO, "lado_de_referencia": int(lado or 1), "valores": out, "contexto_superior_sem_veto": ctx, "unidade": "% = atendimento de critérios"}
        except Exception as e:
            return {"erro": str(e)}

    # ───── posição / reconciliação ─────
    def minhas(self):
        return [p for p in (self.mt5.positions_get(symbol=self.nome) or ()) if int(p.magic) == self.magic]

    def reconciliar(self, agora_ns):
        ps = self.minhas(); est = self.est["posicao"]
        if est is None and ps:                                                       # recuperar após reinício
            p = ps[0]; lado = 1 if p.type == self.mt5.POSITION_TYPE_BUY else -1
            self.est["posicao"] = {"id": (p.comment or "").replace("ROMPv01|", "ROMP-XAU-") or f"ROMP-XAU-recuperada-{p.ticket}", "ticket": int(p.ticket), "lado": lado, "entrada": float(p.price_open),
                                   "stop": float(p.sl), "volume": float(p.volume), "barra_sinal_fim": int(p.time) * 10**9, "recuperada": True}
            self.g(f"recuperada|{p.ticket}", "status", agora_utc(), {"evento": "posição desta experiência recuperada do servidor após reinício", "ticket": int(p.ticket), "stop_no_servidor": float(p.sl)}, self.est["posicao"]["id"])
            if not p.sl: self.garantir_stop(self.est["posicao"], agora_ns)
            self.salvar()
        elif est is not None and not any(int(p.ticket) == est["ticket"] for p in ps):  # fechada na corretora (stop)
            dl = [d for d in (self.mt5.history_deals_get(position=est["ticket"]) or ()) if d.entry in (self.mt5.DEAL_ENTRY_OUT, getattr(self.mt5, "DEAL_ENTRY_OUT_BY", 3))]
            px = float(dl[-1].price) if dl else None; mot = "stop de proteção (servidor)" if dl and dl[-1].reason == getattr(self.mt5, "DEAL_REASON_SL", 4) else "encerrada na corretora"
            if est.get("saida_pedida"): mot = est["saida_pedida"]
            self.resultado(est, px, mot, dl, agora_ns); self.est["posicao"] = None; self.salvar()

    def resultado(self, est, px, mot, dl, agora_ns):
        com = sum(float(d.commission) for d in (self.mt5.history_deals_get(position=est["ticket"]) or ())); sw = sum(float(getattr(d, "swap", 0.0)) for d in (self.mt5.history_deals_get(position=est["ticket"]) or ()))
        luc = sum(float(d.profit) for d in dl); R0 = abs(est["entrada"] - est["stop_inicial"]) if est.get("stop_inicial") else None
        risco_m = None if not R0 else R0 / self.si.trade_tick_size * self.si.trade_tick_value * est["volume"]; liq = luc + com + sw
        self.g(f"resultado|{est['id']}", "resultado", ts(agora_ns), {"motivo_saida": mot, "motivo": mot, "preco_saida": px, "lucro_bruto_moeda": luc, "comissao": com, "swap": sw,
                                                                     "custos_moeda (comissão+swap+taxa)": com + sw, "resultado_liquido_moeda": round(liq, 2), "R_liquido_moeda": None if not risco_m else round(liq / risco_m, 4),
                                                                     "R_bruto": None if not (px and R0) else round((px - est["entrada"]) * est["lado"] / R0, 4),
                                                                     "ticket": est["ticket"], "deals": [d._asdict() if hasattr(d, "_asdict") else str(d) for d in dl]}, est["id"])
        self.marca("SAIDA", agora_ns, px, est["id"], mot)

    def garantir_stop(self, est, agora_ns):
        """stop no servidor conferido; senão encerra (não mantém posição desprotegida)."""
        m = self.mt5; ok = False
        for _ in range(2):
            p = [x for x in self.minhas() if int(x.ticket) == est["ticket"]]
            if p and p[0].sl and abs(p[0].sl - est["stop"]) <= self.si.point * 1.5: ok = True; break
            req = {"action": m.TRADE_ACTION_SLTP, "symbol": self.nome, "position": int(est["ticket"]), "sl": round(est["stop"], self.si.digits), "tp": 0.0, "magic": self.magic}
            self.g(f"ordem_stop|{est['id']}|{_}|{agora_ms()}", "ordem", ts(agora_ns), {"pedido": req}, est["id"]); r = m.order_send(req)
            self.g(f"resp_stop|{est['id']}|{_}|{agora_ms()}", "resposta_mt5", ts(agora_ns), rd(r, m), est["id"])
        self.g(f"stop_conferido|{est['id']}|{agora_ms()}", "validacao", ts(agora_ns), {"verificacao": "stop instalado e aceito pelo servidor", "ok": ok, "stop": est["stop"]}, est["id"])
        if not ok:
            self.L("stop NÃO confirmado — encerrando a posição (não fica desprotegida)"); self.fechar(est, agora_ns, "falha operacional: stop não confirmado no servidor")
        return ok

    # ───── ciclo ─────
    def ciclo(self):
        m = self.mt5; ti = m.terminal_info()
        if ti is None or not getattr(ti, "connected", True):
            self.g(f"sem_conexao|{int(time.time() // 60)}", "impedimento", agora_utc(), {"motivo": "terminal sem conexão — nada avaliado neste minuto"}); return
        tk = m.symbol_info_tick(self.nome); agora_ns = int(tk.time) * 10**9 if tk else int(time.time()) * 10**9
        self.reconciliar(agora_ns)
        b = self.barras("M15", 3000); t_ab = int(b.t.iloc[-1].value); fim = t_ab + 15 * MIN
        if self.est["ultima_barra"] == t_ab: return                                    # uma avaliação por barra concluída
        if fim > agora_ns: return                                                      # (defesa) barra ainda não concluída
        K = RM.canais(b); k = K.iloc[-1]; o, h, l, c = (float(b[x].iloc[-1]) for x in "ohlc")
        info = {"ativo": ATIVO, "timeframe": "M15", "versao_estrategia": RM.VERSAO, "barra_abertura": ts(t_ab), "barra_fecha": ts(fim), "ohlc": [o, h, l, c],
                "limites_entrada_20": {"LS20": k.LS20, "LI20": k.LI20}, "limites_saida_10": {"LS10": k.LS10, "LI10": k.LI10}, "ATR14_wilder": k.ATR14,
                "atraso_avaliacao_s": round((agora_ns - fim) / 1e9, 1)}
        est = self.est["posicao"]; info["observacoes_M1_M5"] = self.observacoes(fim, est["lado"] if est else None)
        self.g(f"informacao|{t_ab}", "informacao", ts(fim), info)
        decidiu_saida = False
        if est is not None and t_ab >= est["barra_sinal_fim"]:
            cond = RM.sinal_saida(est["lado"], c, k.LS10, k.LI10)
            txt = f"fechamento {c} < mín10 {k.LI10}" if est["lado"] > 0 else f"fechamento {c} > máx10 {k.LS10}"
            self.g(f"gestao|{t_ab}", "gestao", ts(fim), {"condicao": txt, "resultado": bool(cond), "acao": "sair" if cond else "manter", "motivo": "saída por sinal: canal de 10 rompido contra" if cond else "mantida: canal de 10 não rompido",
                                                         "stop_vigente": est["stop"]}, est["id"])
            if cond: self.fechar(est, agora_ns, "saída por sinal (canal 10)", ref=c); decidiu_saida = True
        sig = RM.sinal_entrada(c, k.LS20, k.LI20); cond_e = f"c {c} > LS20 {k.LS20}" if sig > 0 else (f"c {c} < LI20 {k.LI20}" if sig < 0 else f"LI20 {k.LI20} ≤ c {c} ≤ LS20 {k.LS20}")
        if decidiu_saida:
            self.g(f"decisao|{t_ab}", "decisao", ts(fim), {"condicao": cond_e, "resultado": bool(sig), "acao": "nenhuma", "motivo": "saída decidida nesta barra: sem nova entrada na mesma decisão"})
        elif self.est["posicao"] is not None:
            if sig: self.g(f"decisao|{t_ab}", "decisao", ts(fim), {"condicao": cond_e, "resultado": True, "acao": "nenhuma", "motivo": "sinal ignorado: posição desta experiência aberta"}, self.est["posicao"]["id"])
        elif not sig:
            self.g(f"decisao|{t_ab}", "decisao", ts(fim), {"condicao": cond_e, "resultado": False, "acao": "esperar", "motivo": "sem rompimento do canal de 20"})
        else:
            self.entrar(sig, t_ab, fim, k, c, cond_e, agora_ns)
        self.est["ultima_barra"] = t_ab; self.salvar()

    def lote(self, dist):
        modo, val = self.dim.get("modo"), self.dim.get("valor")
        if not modo or val is None: return None, "dimensionamento NÃO autorizado na configuração (lote/risco ausentes) — ordens BLOQUEADAS"
        si = self.si; acc = self.mt5.account_info()
        if modo == "lote_fixo": vol = float(val)
        else:
            risco = acc.equity * float(val) / 100 if modo == "percentual" else float(val); por_lote = dist / si.trade_tick_size * si.trade_tick_value
            vol = risco / por_lote if por_lote > 0 else 0
        vol = math.floor(vol / si.volume_step + 1e-9) * si.volume_step; vol = round(min(vol, si.volume_max), 8)
        if vol < si.volume_min: return None, f"lote calculado {vol} abaixo do mínimo {si.volume_min} — impedimento"
        return vol, None

    def entrar(self, sig, t_ab, fim, k, c, cond_e, agora_ns):
        m = self.mt5; oid = f"ROMP-XAU-{pd.Timestamp(t_ab):%Y%m%d%H%M}"
        if oid in self.est["pedidos"]:                                                   # nunca reenviar para a mesma barra
            self.g(f"dup|{oid}", "impedimento", ts(fim), {"motivo": "pedido desta barra já enviado antes (reinício/reconexão) — não reenviado"}, oid); return
        tk = m.symbol_info_tick(self.nome); px_ref = tk.ask if sig > 0 else tk.bid; dist = RM.K_STOP * k.ATR14
        vol, imp = self.lote(dist)
        dec = {"condicao": cond_e, "resultado": True, "acao": "comprar" if sig > 0 else "vender", "lado": sig, "exposicao": "fixa (sem multiplicador)", "motivo": "rompimento do canal de 20 barras M15", "preco_solicitado_referencia_fechamento": c,
               "cotacao_no_envio": {"bid": tk.bid, "ask": tk.ask, "spread_pts": round((tk.ask - tk.bid) / self.si.point)}, "ATR14": k.ATR14, "distancia_stop": dist, "lote": vol,
               "risco_inicial_moeda": None if vol is None else round(dist / self.si.trade_tick_size * self.si.trade_tick_value * vol, 2)}
        self.g(f"decisao|{t_ab}", "decisao", ts(fim), dec, oid); self.marca("SINAL", fim, c, oid, dec["acao"])
        if imp:
            self.g(f"impedimento|{oid}", "impedimento", ts(fim), {"motivo": imp, "decisao_preservada": dec["acao"], "nao_contar_como_esperar": True}, oid); return
        sl0 = round(px_ref - sig * dist, self.si.digits)
        req = {"action": m.TRADE_ACTION_DEAL, "symbol": self.nome, "volume": vol, "type": m.ORDER_TYPE_BUY if sig > 0 else m.ORDER_TYPE_SELL, "price": px_ref, "sl": sl0, "tp": 0.0,
               "deviation": int(self.cfg["deviation_pts"]), "magic": self.magic, "comment": f"ROMPv01|{pd.Timestamp(t_ab):%Y%m%d%H%M}", "type_time": m.ORDER_TIME_GTC, "type_filling": self.preenchimento()}
        self.est["pedidos"][oid] = {"enviado_utc": agora_ms()}; self.salvar()                 # gravado ANTES do envio
        self.g(f"ordem|{oid}", "ordem", ts(fim), {"pedido": req, "t_envio_utc": agora_ms()}, oid); t0 = time.perf_counter(); r = m.order_send(req); lat = round((time.perf_counter() - t0) * 1000, 1)
        R = rd(r, m); R["latencia_envio_ms"] = lat; self.g(f"resposta|{oid}", "resposta_mt5", ts(fim), R, oid)
        if r is None or r.retcode not in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL):
            self.g(f"falha|{oid}", "impedimento", ts(fim), {"motivo": f"ordem não executada pela corretora (retcode {None if r is None else r.retcode})", "decisao_preservada": dec["acao"]}, oid); return
        ps = [p for p in self.minhas()]; p = ps[-1] if ps else None
        if p is None: self.g(f"sem_pos|{oid}", "erro", ts(fim), {"motivo": "resposta DONE mas posição não encontrada; será reconciliada"}, oid); return
        ent = float(p.price_open); stop = round(RM.stop_inicial(sig, ent, k.ATR14), self.si.digits)
        est = {"id": oid, "ticket": int(p.ticket), "lado": sig, "entrada": ent, "stop": stop, "stop_inicial": stop, "volume": float(p.volume), "barra_sinal_fim": int(fim)}
        self.est["posicao"] = est; self.salvar()
        self.g(f"execucao|{oid}", "execucao", ts(fim), {"ticket": int(p.ticket), "preco_solicitado": px_ref, "preco_executado": ent, "slippage": round((ent - px_ref) * sig, 5), "spread_no_envio": tk.ask - tk.bid, "stop_na_corretora": stop, "lado": sig,
                                                       "atraso_desde_fechamento_s": round((agora_ns - fim) / 1e9, 1), "stop_provisorio_no_envio": sl0, "stop_final_entrada_efetiva": stop, "volume": float(p.volume)}, oid)
        self.marca("ENTRADA", agora_ns, ent, oid, f"{dec['acao']} {p.volume}"); self.marca("STOP", agora_ns, stop, oid, "stop inicial 2×ATR14")
        self.garantir_stop(est, agora_ns)

    def preenchimento(self):
        fm = getattr(self.si, "filling_mode", 1); m = self.mt5
        return m.ORDER_FILLING_FOK if fm & 1 else (m.ORDER_FILLING_IOC if fm & 2 else m.ORDER_FILLING_RETURN)

    def fechar(self, est, agora_ns, motivo, ref=None):
        m = self.mt5; tk = m.symbol_info_tick(self.nome); px = tk.bid if est["lado"] > 0 else tk.ask
        req = {"action": m.TRADE_ACTION_DEAL, "symbol": self.nome, "volume": est["volume"], "type": m.ORDER_TYPE_SELL if est["lado"] > 0 else m.ORDER_TYPE_BUY, "position": int(est["ticket"]), "price": px,
               "deviation": int(self.cfg["deviation_pts"]), "magic": self.magic, "comment": "ROMPv01|fecha", "type_time": m.ORDER_TIME_GTC, "type_filling": self.preenchimento()}
        est["saida_pedida"] = motivo; self.salvar()
        self.g(f"ordem_saida|{est['id']}|{agora_ns}", "ordem", ts(agora_ns), {"motivo": motivo, "pedido": req, "preco_solicitado_referencia": ref, "t_envio_utc": agora_ms()}, est["id"])
        r = m.order_send(req); self.g(f"resp_saida|{est['id']}|{agora_ns}", "resposta_mt5", ts(agora_ns), rd(r, m), est["id"])
        if r is not None and r.retcode in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL):
            dl = [d for d in (m.history_deals_get(position=est["ticket"]) or ()) if d.entry != m.DEAL_ENTRY_IN]
            self.resultado(est, float(r.price) if r.price else px, motivo, dl, agora_ns); self.est["posicao"] = None; self.salvar()
        else:
            est.pop("saida_pedida", None); self.salvar()
            self.g(f"saida_falhou|{est['id']}|{agora_ns}", "erro", ts(agora_ns), {"motivo": "saída não executada; o stop na corretora continua valendo; nova tentativa na próxima barra se a condição persistir"}, est["id"])

    def marca(self, tipo, t_ns, preco, op, txt):
        try:
            d = os.path.join(self.mt5.terminal_info().commondata_path, "Files", "BT_ROMP"); os.makedirs(d, exist_ok=True); f = os.path.join(d, f"marcas_{self.nome}.csv")
            with open(f, "a", encoding="utf-8") as o: o.write(f"{int(t_ns // 10**9)};{tipo};{'' if preco is None else preco};{op};{str(txt).replace(';', ',')}\n")
        except Exception as e: self.L(f"marca não gravada: {e}")


def rd(r, m):
    if r is None: return {"retcode": None, "erro": str(m.last_error())}
    d = r._asdict() if hasattr(r, "_asdict") else dict(r); d.pop("request", None); return d


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--config", default=os.path.join(AQUI, "config_romp.json")); ap.add_argument("--pasta", default=os.path.join(AQUI, "romp_XAUUSD"))
    ap.add_argument("--falso"); ap.add_argument("--agora"); ap.add_argument("--uma-vez", action="store_true"); a = ap.parse_args()
    cfg = dict(CFG_PADRAO); cfg.update({k: v for k, v in (json.load(open(a.config, encoding="utf-8")) if os.path.exists(a.config) else {}).items() if not k.startswith("_")})
    destino = EX.conferir_destino(cfg)
    if a.falso:
        import mt5_falso_exec as mt5; mt5.configurar(a.falso, a.agora)
    else:
        import MetaTrader5 as mt5
        if not mt5.initialize(path=cfg.get("terminal_caminho") or None): raise SystemExit(f"MT5 não inicializou: {mt5.last_error()}")
    acc = mt5.account_info()
    if acc is None or acc.trade_mode != getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0): raise SystemExit("RECUSADO: a conta não é DEMO")
    S = Romp(mt5, cfg, a.pasta, "simulado" if a.falso else "demo_efetiva")
    S.g(f"inicio|{agora_utc()}", "status", agora_utc(), {"evento": "inicio", "modulo": VERSAO_MODULO, "estrategia": RM.VERSAO, "magic": S.magic, "conta": acc.login, "servidor": acc.server,
                                                        "dimensionamento": S.dim, "ordens": "HABILITADAS" if S.dim.get("modo") else "BLOQUEADAS (dimensionamento não autorizado)"})
    S.L(f"{VERSAO_MODULO} ({RM.VERSAO}) iniciado · conta {acc.login} DEMO · ordens {'HABILITADAS' if S.dim.get('modo') else 'BLOQUEADAS (lote/risco não autorizado)'} · destino {destino or 'só registro local'}")
    env = EX.Envio(S.pasta, cfg["plataforma_url"], cfg["bot_token"], S.L); env.start()
    while True:
        if os.path.exists(os.path.join(AQUI, "PARAR")): S.L("PARAR encontrado — encerrado; posição (se houver) segue com o stop na corretora"); break
        try: S.ciclo()
        except EX.RegistroFalhou as e: S.L(f"ENCERRADO: registro local falhou ({e})"); raise SystemExit(4)
        except Exception as e: S.g(f"erro|{int(time.time())}", "erro", agora_utc(), {"erro": str(e), "trace": traceback.format_exc(limit=3)}); S.L(f"FALHA: {e}")
        if a.uma_vez: break
        time.sleep(cfg["laco_s"])
    env.parar = True
    if cfg["plataforma_url"]:
        try: env.enviar_uma_vez()
        except Exception as e: S.L(f"envio final falhou ({e})")
    mt5.shutdown()


if __name__ == "__main__": main()
