"""BotTested · ORDEM 048 · LEITOR DO CARTÃO "Rompimento de Lateralização" (Experimental · teste em sombra).
Roda no computador do MT5. Busca na plataforma os bots ENVIADOS pelo cartão, lê as cotações (bid/ask, ticks) e as barras do terminal,
roda a R0 da O44 (motor por tick da O47) e mantém UMA POSIÇÃO VIRTUAL POR BOT. NÃO ENVIA ORDENS: não existe chamada de ordem neste arquivo.
Cada bot confirma na plataforma o ID, o símbolo efetivo da corretora, o timeframe, a versão da regra e o modo sombra, com cotação lida
→ "Conectado". Depois da verificação técnica (1 h), a plataforma fixa a semana de coleta (mesmo início e fim para os 3 TF de cada ativo).
"Parar" na plataforma encerra só os bots deste cartão; a campanha, o conector e os outros bots não são tocados.
Primeira execução:  py bt_lateral_leitor_o48.py --configurar   (pede a chave do leitor gerada no cartão; registra o início com o Windows)
Teste local:        --falso CSV --agora "AAAA-MM-DD HH:MM" """
import os, sys, json, time, argparse, traceback, hashlib, urllib.request
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import ao_vivo_o47 as AV, leitura_canal_o49 as LC
VERSAO_LEITOR = "leitor-lateral-o48-1.1 (O49: leitura do canal EMA20 em sombra)"; REGRA = "lateral-tf-0.1 (R0 da O44) · leitor-o48"
N_JAN = 1200; GAP_MS = 5 * 60_000; JAN_RET_MS = 15 * 60_000; POLL_S = 30; CONT_S = 300; N_BARRAS_GRAF = 40
CFG_ARQ = os.path.join(os.path.expanduser("~"), "BotTested_Lateral_O48_config.json"); PLATAFORMA = "https://lm-relatorio-homolog.up.railway.app"
TFC = {"M15": "TIMEFRAME_M15", "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1"}


def agora_iso(): return pd.Timestamp.now(tz="UTC").isoformat()


class Plataforma:
    """cliente HTTP mínimo (JSON). A chave vai no corpo, nunca em URL nem no log."""
    def __init__(self, url, chave, post=None): self.url, self.chave, self._post = url.rstrip("/"), chave, post
    def post(self, rota, corpo):
        corpo = {"chave": self.chave, **corpo}
        if self._post: return self._post(rota, corpo)
        req = urllib.request.Request(self.url + rota, data=json.dumps(corpo, default=_js).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read().decode())


def _js(x):
    if hasattr(x, "item"): return x.item()
    return str(x)


class Grupo:
    """um ativo: um fluxo de ticks para todas as instâncias (bots) desse ativo; cada bot tem a própria Instancia (posição virtual)."""
    def __init__(self, L, ativo):
        self.L, self.at = L, ativo; self.nome = L.simbolos.get(ativo, ativo); self.inst = {}; self.meta = {}; self.canal = {}; self.ult_tick_ms = None; self.ret_pend = []; self.ultimo_r = {}

    def ev(self, bot_id, tipo, t, payload, chave=None):
        self.L.fila.setdefault(bot_id, []).append({"chave": chave or f"{tipo}|{t}|{hashlib.sha1(json.dumps(payload, sort_keys=True, default=_js).encode()).hexdigest()[:12]}", "tipo": tipo, "t": t, "payload": payload})

    def barras(self, tf, n=N_BARRAS_GRAF):
        r = self.ultimo_r.get(tf)
        if r is None: return []
        eh = r.h.ewm(span=20, adjust=False).mean(); el = r.l.ewm(span=20, adjust=False).mean()          # canal EMA20 High/Low (referência do dono), com todo o histórico da janela
        x = r.tail(n); EH, EL = eh.tail(n), el.tail(n)
        return [[str(t), round(float(o), 2), round(float(h), 2), round(float(l), 2), round(float(c), 2), round(float(a), 2), round(float(b_), 2)]
                for t, o, h, l, c, a, b_ in zip(x.t, x.o, x.h, x.l, x.c, EH, EL)]

    def ciclo(self):
        m = self.L.mt5
        if not self.inst: return
        tfs = sorted({i.tf for i in self.inst.values()})
        R = {}
        for tf in tfs:
            r = m.copy_rates_from_pos(self.nome, getattr(m, TFC[tf]), 1, N_JAN)
            if r is None or not len(r):
                for b in self.inst: self.ev(b, "falha_leitura", agora_iso(), {"o_que": f"barras {tf}", "erro": str(m.last_error())}, chave=f"falha|{tf}|{int(time.time() // 60)}")
                return
            R[tf] = pd.DataFrame(r).assign(t=lambda d: pd.to_datetime(d["time"], unit="s")).rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["t", "o", "h", "l", "c", "spread"]]
        self.ultimo_r = R
        q = m.symbol_info_tick(self.nome)
        if q is None:
            for b in self.inst: self.ev(b, "falha_leitura", agora_iso(), {"o_que": "cotação", "erro": str(m.last_error())}, chave=f"falha|tick|{int(time.time() // 60)}")
            return
        agora_ms = int(q.time_msc); de_ms = (self.ult_tick_ms + 1) if self.ult_tick_ms is not None else agora_ms - 3_600_000
        tk = m.copy_ticks_range(self.nome, pd.Timestamp(de_ms, unit="ms").to_pydatetime(), pd.Timestamp(agora_ms + 1, unit="ms").to_pydatetime(), getattr(m, "COPY_TICKS_INFO", 1))
        if tk is None:
            for b in self.inst: self.ev(b, "falha_leitura", agora_iso(), {"o_que": "ticks", "erro": str(m.last_error())}, chave=f"falha|ticks|{int(time.time() // 60)}")
            return
        self.L.confirmar(self, q, R)
        T, B, A = tk["time_msc"].astype(np.int64), tk["bid"].astype(float), tk["ask"].astype(float)
        TM = {tf: R[tf].t.values.astype("datetime64[ms]").astype(np.int64) for tf in tfs}; dur = {tf: AV.TF_MIN[tf] * 60_000 for tf in tfs}
        evs = []
        for bid_, I in self.inst.items():
            fil = [len(TM[I.tf]) - 1] if I.ult_barra_ms is None else list(np.nonzero(TM[I.tf] > I.ult_barra_ms)[0])
            evs += [(int(TM[I.tf][k]) + dur[I.tf], 0, bid_, int(k)) for k in fil]
        ult_ab = {tf: int(TM[tf][-1]) for tf in tfs}; lim = None; ant = self.ult_tick_ms
        for n in range(len(T)):
            t = int(T[n])
            if ant is not None and any((t // dur[tf]) > (ant // dur[tf]) and (ant // dur[tf]) * dur[tf] > ult_ab[tf] for tf in tfs): lim = t; break
            ant = t
        evs += [(int(T[n]), 1, None, n) for n in range(len(T)) if lim is None or T[n] < lim]
        evs.sort(key=lambda e: (e[0], e[1]))
        for t, pri, bid_, k in evs:
            if pri == 0:
                I = self.inst.get(bid_)
                if I is not None:
                    df = R[I.tf].iloc[:k + 1].reset_index(drop=True); I.fecha_barra(df)
                    try: self.canal_barra(bid_, I.tf, df)                                  # O49: leitura do canal (programada, sombra; não decide nada)
                    except Exception as e: self.ev(bid_, "falha_leitura", agora_iso(), {"o_que": "leitura do canal", "erro": str(e)}, chave=f"falha|canal|{int(time.time() // 60)}")
                continue
            lac = self.ult_tick_ms is not None and t - self.ult_tick_ms > GAP_MS
            if lac:
                for b in self.inst: self.ev(b, "periodo_sem_ticks", str(pd.Timestamp(t, unit="ms")), {"de": str(pd.Timestamp(self.ult_tick_ms, unit="ms")), "ate": str(pd.Timestamp(t, unit="ms")), "minutos": round((t - self.ult_tick_ms) / 60000, 1)}, chave=f"gap|{self.ult_tick_ms}")
            for I in self.inst.values(): I.tick(t, B[k], A[k], lac)
            self.ult_tick_ms = t
        self.drenar()

    def canal_barra(self, b, tf, df):
        lc = self.canal.setdefault(b, LC.LeitorCanal(self.at, tf)); r = lc.barra(df)
        x = {"barra": r["barra"], "disponivel": r["disponivel"], "versao": r["versao"], "origem": r["origem"]}
        if r["disponivel"]:
            e = r["estrutura"]; f = lambda z: None if not z else {k: z[k] for k in ("zona", "estado", "dist_preco", "dist_atr", "posicao_vs_canal", "no_caminho", "espaco_ate_o_seguinte_atr")}
            x.update({"canal": r["canal"], "eventos": {k: v for k, v in r["eventos"].items() if v}, "resistencia_acima": f(e["resistencia_acima"]), "suporte_abaixo": f(e["suporte_abaixo"]),
                      "rompimentos_5b": len(e["rompimentos_ultimas_5_barras"]), "concordancia": r["concordancia"], "evidencia_pct": {k: v for k, v in r["evidencia_pct"].items() if k != "formula"},
                      "leitura_produzida": r["leitura_produzida"]})
        else: x["ausencia"] = r["ausencia"]
        self.meta[b]["canal"] = x; self.ev(b, "leitura_canal", r["barra"], x, chave=f"canal|{r['barra']}")

    def drenar(self):
        for b, I in self.inst.items():
            meta = self.meta[b]
            for e in I.eventos:
                p = {k: v for k, v in e.items() if k not in ("instancia", "tipo", "t")}
                if e["tipo"] == "gatilho_armado": meta["sinais"][e["sinal"]] = {"nivel": e["nivel"], "gatilho": e["gatilho"], "extremo": e["extremo"], "lado": e["lado"]}
                s = meta["sinais"].get(p.get("sinal") or p.get("id")) or {}
                p.update({k: v for k, v in s.items() if k not in p})
                if e["tipo"] in ("gatilho_armado", "gatilho_expirado", "entrada_virtual", "bloqueado_posicao_aberta"):
                    p["barras"] = self.barras(I.tf); p["canal_no_instante"] = meta.get("canal")          # O49: leitura do canal da última barra fechada
                if e["tipo"] == "entrada_virtual": self.ret_pend.append({"bot": b, "id": e["id"], "lado": e["lado"], "extremo": p.get("extremo"), "nivel": p.get("nivel"), "tau_ms": int(pd.Timestamp(e["t"]).value // 10**6)})
                self.ev(b, e["tipo"], e["t"], {**p, "tf": I.tf, "regra_versao": REGRA, "modo": "SOMBRA — nenhuma ordem"}, chave=f"{e['tipo']}|{p.get('sinal', p.get('id', ''))}|{e['t']}")
            for o in I.ops:
                self.ev(b, "resultado", str(pd.Timestamp(o["t_sai_ms"], unit="ms")), {k: v for k, v in o.items() if k != "saida_pendente"}, chave=f"resultado|{o['id']}")
            I.eventos, I.ops = [], []
        resta = []
        for r in self.ret_pend:                                                           # retorno A/B/C (diagnóstico O45): 15 min, fechamentos M1
            if self.ult_tick_ms is None or self.ult_tick_ms < r["tau_ms"] + JAN_RET_MS + 60_000: resta.append(r); continue
            m1 = self.L.mt5.copy_rates_range(self.nome, self.L.mt5.TIMEFRAME_M1, pd.Timestamp(r["tau_ms"], unit="ms").floor("min").to_pydatetime(), pd.Timestamp(r["tau_ms"] + JAN_RET_MS - 1, unit="ms").to_pydatetime())
            c = [] if m1 is None else [float(x) for x in m1["close"]]; s = r["lado"]; al = (lambda x, y: x > y + 1e-9) if s < 0 else (lambda x, y: x < y - 1e-9)
            g = "C" if any(al(x, r["nivel"]) for x in c) else ("B" if any(al(x, r["extremo"]) for x in c) else "A")
            self.ev(r["bot"], "retorno", str(pd.Timestamp(r["tau_ms"], unit="ms")), {"id": r["id"], "grupo": g, "n_m1": len(c), "completo": len(c) == 15}, chave=f"retorno|{r['id']}")
        self.ret_pend = resta


class Leitor:
    def __init__(self, mt5, plat, pasta, simbolos=None, demo_obrigatoria=True):
        self.mt5, self.P, self.pasta = mt5, plat, pasta; os.makedirs(pasta, exist_ok=True); self.simbolos = simbolos or {}
        self.G = {}; self.fila = {}; self.t_poll = 0; self.t_cont = 0; self.confirmados = set(); self.f_est = os.path.join(pasta, "o48_estado.json"); self.demo = demo_obrigatoria
        if os.path.exists(self.f_est):
            d = json.load(open(self.f_est)); self.fila = {int(k): v for k, v in d.get("fila", {}).items()}
            for at, g in d.get("grupos", {}).items():
                G = self.G.setdefault(at, Grupo(self, at)); G.ult_tick_ms = g["ult_tick_ms"]; G.ret_pend = g["ret_pend"]
                for b, x in g["inst"].items():
                    I = AV.Instancia(at, x["tf"]); I.restaurar(x["estado"]); G.inst[int(b)] = I; G.meta[int(b)] = {"sinais": x.get("sinais", {}), "estado": x.get("estado_plat")}

    def sincronizar(self):
        d = self.P.post("/lateral/leitor/bots", {}); vivos = set()
        for b in d.get("bots", []):
            bid_ = int(b["bot_id"]); G = self.G.setdefault(b["ativo"], Grupo(self, b["ativo"]))
            if not b["rodar"]:
                if bid_ in G.inst:
                    I = G.inst.pop(bid_); G.meta.pop(bid_, None)
                    G.ev(bid_, "status", agora_iso(), {"evento": "bot parado pela plataforma — instância encerrada (só este bot)", "posicao_virtual_aberta": I.pos is not None}, chave=f"parado|{bid_}")
                continue
            vivos.add(bid_)
            if bid_ not in G.inst:
                G.inst[bid_] = AV.Instancia(b["ativo"], b["tf"]); G.meta[bid_] = {"sinais": {}, "estado": b["estado"]}
                G.ev(bid_, "status", agora_iso(), {"evento": "instância iniciada no leitor", "bot_id": bid_, "ativo": b["ativo"], "tf": b["tf"], "versao_leitor": VERSAO_LEITOR}, chave=f"inicio|{bid_}|{int(time.time())}")
            I = G.inst[bid_]; G.meta[bid_]["estado"] = b["estado"]
            ini, fim = b.get("coleta_inicio"), b.get("coleta_fim")
            I.ativo_desde_ms = None if not ini else int(pd.Timestamp(ini).tz_convert(None).value // 10**6) if pd.Timestamp(ini).tzinfo else int(pd.Timestamp(ini).value // 10**6)
            if fim and I.ativo_desde_ms is not None:
                fim_ms = int(pd.Timestamp(fim).tz_convert(None).value // 10**6) if pd.Timestamp(fim).tzinfo else int(pd.Timestamp(fim).value // 10**6)
                if G.ult_tick_ms is not None and G.ult_tick_ms >= fim_ms: I.ativo_desde_ms = 2**62      # semana encerrada: não arma sinal novo
        for G in self.G.values():
            for b in [b for b in G.inst if b not in vivos]: G.inst.pop(b); G.meta.pop(b, None)

    def confirmar(self, G, q, R):
        acc = self.mt5.account_info(); ti = self.mt5.terminal_info()
        for b, I in G.inst.items():
            if b in self.confirmados or G.meta[b].get("estado") not in ("enviado", "conectado"): continue
            if I.tf not in R or q.bid <= 0 or q.ask <= 0: continue
            r = self.P.post("/lateral/leitor/confirmar", {"bot_id": b, "simbolo_efetivo": G.nome, "timeframe": I.tf, "regra_versao": REGRA, "modo": "sombra",
                                                        "cotacao": {"bid": float(q.bid), "ask": float(q.ask), "t": str(pd.Timestamp(int(q.time_msc), unit="ms"))},
                                                        "terminal": {"servidor": getattr(acc, "server", None), "demo": getattr(acc, "trade_mode", 1) == getattr(self.mt5, "ACCOUNT_TRADE_MODE_DEMO", 0),
                                                                     "empresa": getattr(acc, "company", None), "build": getattr(ti, "build", None)}})
            if r.get("ok"): self.confirmados.add(b); G.ev(b, "status", agora_iso(), {"evento": "conectado: terminal confirmou cotações", "simbolo_efetivo": G.nome, "tf": I.tf}, chave=f"conectado|{b}")
            else: G.ev(b, "falha_leitura", agora_iso(), {"o_que": "confirmação", "resposta": r}, chave=f"confirma|{b}|{int(time.time() // 300)}")

    def contadores(self, agora_s):
        for G in self.G.values():
            for b, I in G.inst.items(): G.ev(b, "contadores", agora_iso(), {**I.cont, "posicao_virtual_aberta": I.pos is not None, "ult_tick": None if G.ult_tick_ms is None else str(pd.Timestamp(G.ult_tick_ms, unit="ms"))}, chave=f"contadores|{int(agora_s // CONT_S)}")

    def enviar(self):
        for b in list(self.fila):
            lote = self.fila[b][:200]
            if not lote: continue
            try: self.P.post("/lateral/leitor/eventos", {"bot_id": b, "eventos": lote}); self.fila[b] = self.fila[b][len(lote):]
            except Exception as e: print(f"[o48] envio pendente ({len(self.fila[b])} eventos do bot {b}): {e}", flush=True)

    def salvar(self):
        d = {"fila": self.fila, "grupos": {at: {"ult_tick_ms": G.ult_tick_ms, "ret_pend": G.ret_pend, "inst": {str(b): {"tf": I.tf, "estado": I.estado(), "sinais": G.meta[b]["sinais"], "estado_plat": G.meta[b].get("estado")} for b, I in G.inst.items()}} for at, G in self.G.items()}}
        json.dump(d, open(self.f_est + ".tmp", "w"), default=_js); os.replace(self.f_est + ".tmp", self.f_est)

    def ciclo(self, agora_s=None):
        agora_s = agora_s or time.time()
        if agora_s - self.t_poll >= POLL_S: self.sincronizar(); self.t_poll = agora_s
        for G in self.G.values(): G.ciclo()
        if agora_s - self.t_cont >= CONT_S: self.contadores(agora_s); self.t_cont = agora_s
        self.enviar(); self.salvar()


def registrar_autostart():
    """Windows: inicia com o Windows (HKCU\\...\\Run), silencioso. Só o leitor O48; o conector e a campanha não são tocados."""
    if os.name != "nt": return False
    import winreg
    py = sys.executable.replace("python.exe", "pythonw.exe"); cmd = f'"{py}" "{os.path.abspath(__file__)}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS) as k:
        try:
            if winreg.QueryValueEx(k, "BotTestedLateralO48")[0] == cmd: return True
        except OSError: pass
        winreg.SetValueEx(k, "BotTestedLateralO48", 0, winreg.REG_SZ, cmd)
    return True


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--configurar", action="store_true"); ap.add_argument("--falso"); ap.add_argument("--agora"); ap.add_argument("--uma-vez", action="store_true")
    a = ap.parse_args(); cfg = json.load(open(CFG_ARQ, encoding="utf-8")) if os.path.exists(CFG_ARQ) else {}
    pasta = os.path.join(os.path.expanduser("~"), "BotTested_Lateral_O48"); os.makedirs(pasta, exist_ok=True)
    if sys.executable.lower().endswith("pythonw.exe") or sys.stdout is None:                    # início com o Windows: sem janela → registra em arquivo
        sys.stdout = sys.stderr = open(os.path.join(pasta, "leitor_o48.log"), "a", encoding="utf-8", buffering=1)
    if a.configurar or not cfg.get("chave"):
        print("Cole a CHAVE DO LEITOR gerada no cartão 'Rompimento de Lateralização' (ela fica só neste computador):", flush=True)
        cfg["chave"] = input().strip(); cfg.setdefault("plataforma_url", PLATAFORMA); cfg.setdefault("terminal_caminho", ""); cfg.setdefault("simbolos", {"XAUUSD": "XAUUSD", "BTCUSD": "BTCUSD"})
        json.dump(cfg, open(CFG_ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("configuração salva; início com o Windows:", registrar_autostart(), flush=True)
    if a.falso:
        import mt5_falso_ticks as mt5; mt5.configurar(a.falso, a.agora)
    else:
        import MetaTrader5 as mt5
        if not mt5.initialize(path=cfg.get("terminal_caminho") or None): raise SystemExit(f"MT5 não inicializou: {mt5.last_error()}")
        acc = mt5.account_info()
        if acc is None or acc.trade_mode != getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0): raise SystemExit("RECUSADO: conta não é DEMO")
        for s in (cfg.get("simbolos") or {}).values(): mt5.symbol_select(s, True)
    L = Leitor(mt5, Plataforma(cfg.get("plataforma_url", PLATAFORMA), cfg["chave"]), os.path.join(os.path.expanduser("~"), "BotTested_Lateral_O48"), cfg.get("simbolos"))
    print(f"{VERSAO_LEITOR} · {REGRA} · MODO SOMBRA — nenhuma ordem", flush=True)
    while True:
        if os.path.exists(os.path.join(os.path.expanduser("~"), "BotTested_Lateral_O48", "PARAR")): break
        try: L.ciclo()
        except Exception as e: print(f"[o48] erro no ciclo: {e}\n{traceback.format_exc(limit=3)}", flush=True)
        if a.uma_vez: break
        time.sleep(1)
    mt5.shutdown()


if __name__ == "__main__": main()
