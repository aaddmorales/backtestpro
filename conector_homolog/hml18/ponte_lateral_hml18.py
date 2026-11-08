"""BotTested Conector HOMOLOG v1.40-hml18 · PONTE DO CARTÃO "Rompimento de Lateralização" (ORDEM 051, 08/11/2026).

Decisão do dono (08/11): o cartão segue o FLUXO PADRÃO — o token gerado no passo Enviar da plataforma é colado no Conector, os bots aparecem
em "Meus bots" e a leitura em sombra roda DENTRO do Conector (não há mais programa separado nem início próprio com o Windows).

O que esta ponte faz:
  - recebe os tokens "lat_…" colados no campo do token (junto com o token da campanha, separados por espaço);
  - liga o terminal MT5 FIXADO no Conector (mesma instalação do seletor "Qual MT5 usar") pelo pacote MetaTrader5, confere que o terminal
    conectado é essa instalação e que a conta é DEMO — senão RECUSA e não lê nada;
  - roda o motor da O48 sem nenhuma alteração (pasta lateral/, hashes iguais ao MANIFESTO_O48 → MANIFESTO_MOTOR_O48.json):
    R0 da O44, motor por tick da O47, leitura do canal EMA20 da O49 — uma posição VIRTUAL por bot;
  - fala só com a plataforma do cartão (lm-relatorio-homolog), com o token no corpo (nunca em URL ou log).

NÃO ENVIA ORDENS: este arquivo não chama nenhuma função de ordem do MetaTrader5 (o teste test_o51 confere a ausência no código).
Não toca na campanha: o token da campanha, o EA, os snapshots e os comandos seguem pelo caminho de sempre do Conector.
"""
import os, re, sys, json, time, hashlib, threading, traceback

AQUI = os.path.dirname(os.path.abspath(__file__)); PKG = os.path.join(AQUI, "lateral")
VERSAO_PONTE = "ponte-lateral-hml18-1.0 (ORDEM 051)"
LATERAL_BASE = "https://lm-relatorio-homolog.up.railway.app"
PASTA_BASE = os.path.join(os.path.expanduser("~"), "BotTested_Conector_HOMOLOG_lateral")
SIMBOLOS_PADRAO = {"XAUUSD": "XAUUSD", "BTCUSD": "BTCUSD"}
PREFIXO = "lat_"


def eh_token_lateral(t):
    return (t or "").strip().startswith(PREFIXO)


def separar_tokens(texto):
    """'tokenCampanha lat_xxx' → (['tokenCampanha'], ['lat_xxx']). Aceita espaço, vírgula, ponto e vírgula ou quebra de linha; sem repetidos."""
    vistos, camp, lat = set(), [], []
    for t in re.split(r"[\s,;]+", texto or ""):
        if not t or t in vistos:
            continue
        vistos.add(t); (lat if eh_token_lateral(t) else camp).append(t)
    return camp, lat


def _js(x):
    """mesmo conversor do leitor O48 (numpy → número; o resto → texto)."""
    if hasattr(x, "item"):
        return x.item()
    return str(x)


def corpo_json(corpo):
    return json.dumps(corpo, default=_js)


def _post_http(rota, corpo, timeout=20):
    import requests                                    # passa pela trava de rede do núcleo (só https nos 2 hosts de homologação)
    r = requests.post(LATERAL_BASE + rota, data=corpo_json(corpo).encode("utf-8"), headers={"Content-Type": "application/json"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} em {rota}")
    return r.json()


def listar_bots_laterais(token, post=None):
    """'Meus bots' do cartão (só leitura). (ok, lista) — cada item com _lateral=True."""
    try:
        d = (post or _post_http)("/lateral/conector/listar", {"bot_token": (token or "").strip()})
        return True, [dict(b, _lateral=True) for b in (d.get("bots") or [])]
    except Exception as e:
        return False, str(e)


def caminho_terminal(mql5_dir):
    """pasta MQL5 fixada → terminal64.exe da instalação (via origin.txt da pasta de dados). '' se não achar."""
    try:
        dados = os.path.dirname(os.path.normpath(mql5_dir))
        org = os.path.join(dados, "origin.txt")
        if os.path.isfile(org):
            with open(org, "r", encoding="utf-16", errors="ignore") as f:
                inst = f.read().strip().strip("﻿")
            exe = os.path.join(inst, "terminal64.exe")
            if os.path.isfile(exe):
                return exe
    except Exception:
        pass
    return ""


def _mesma_pasta(a, b):
    n = lambda x: os.path.normcase(os.path.normpath(str(x or ""))).rstrip("\\/")
    return bool(a) and bool(b) and n(a) == n(b)


def _carregar_motor():
    if PKG not in sys.path:
        sys.path.insert(0, PKG)
    import bt_lateral_leitor_o48 as LE                  # motor O48/O49 sem alteração
    return LE


class PonteLateral:
    """uma thread; um Leitor do motor O48 por token lateral; pasta de estado própria por token (hash, nunca o token)."""

    def __init__(self, tokens, mql5_dir, simbolos=None, ao_status=None, ao_mt5=None, ao_nuvem=None, mt5_mod=None, post=None,
                 pasta_base=None, exigir_pasta=True, intervalo_s=1.0):
        self.tokens = [t for t in (tokens or []) if eh_token_lateral(t)]
        self.mql5_dir, self.simbolos = mql5_dir, dict(simbolos or SIMBOLOS_PADRAO)
        self.ao_status, self.ao_mt5, self.ao_nuvem = ao_status or (lambda s: None), ao_mt5 or (lambda: None), ao_nuvem or (lambda: None)
        self._mt5, self._post = mt5_mod, post or _post_http
        self.pasta_base, self.exigir_pasta, self.intervalo_s = pasta_base or PASTA_BASE, exigir_pasta, intervalo_s
        self._parar = threading.Event(); self.thread = None; self.leitores = []; self.recusa = None; self.ciclos = 0; self.erros = 0

    # ── cliente da plataforma: token no corpo como "bot_token" ──
    def _plataforma(self, LE, tok):
        ponte = self

        class _P(LE.Plataforma):
            def post(self_, rota, corpo):
                d = ponte._post(rota, {"bot_token": tok, **corpo})
                ponte.ao_nuvem()
                return d
        return _P(LATERAL_BASE, tok)

    def _pasta(self, tok):
        return os.path.join(self.pasta_base, hashlib.sha256(tok.encode()).hexdigest()[:12])

    def conferir_terminal(self, mt5):
        """None se ok; senão o motivo da recusa (nada é lido)."""
        if self.exigir_pasta:
            ti = mt5.terminal_info()
            esperado = os.path.dirname(os.path.normpath(self.mql5_dir or ""))
            if ti is None or not _mesma_pasta(getattr(ti, "data_path", ""), esperado):
                return f"o terminal conectado não é a instalação fixada no Conector ({getattr(ti, 'data_path', None)} ≠ {esperado})"
        acc = mt5.account_info()
        if acc is None:
            return f"sem conta no terminal ({mt5.last_error()})"
        if getattr(acc, "trade_mode", None) != getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0):
            return "a conta do terminal NÃO é DEMO"
        return None

    def preparar(self):
        LE = _carregar_motor()
        mt5 = self._mt5
        if mt5 is None:
            try:
                import MetaTrader5 as mt5
            except Exception:
                self.recusa = "falta o pacote MetaTrader5 (py -m pip install MetaTrader5 pandas numpy)"
                return False
            exe = caminho_terminal(self.mql5_dir)
            ok = mt5.initialize(path=exe) if exe else mt5.initialize()
            if not ok:
                self.recusa = f"o MT5 não inicializou ({mt5.last_error()})"
                return False
        self._mt5 = mt5
        self.recusa = self.conferir_terminal(mt5)
        if self.recusa:
            return False
        for s in self.simbolos.values():
            try:
                mt5.symbol_select(s, True)
            except Exception:
                pass
        self.leitores = [LE.Leitor(mt5, self._plataforma(LE, t), self._pasta(t), self.simbolos, demo_obrigatoria=True) for t in self.tokens]
        return True

    def passo(self, agora_s=None):
        """um ciclo de todos os leitores (o teste chama direto, com o relógio do terminal simulado)."""
        for L in self.leitores:
            L.ciclo(agora_s)
        self.ciclos += 1
        if any(G.ult_tick_ms is not None for L in self.leitores for G in L.G.values()):
            self.ao_mt5()

    def resumo(self):
        n = sum(len(G.inst) for L in self.leitores for G in L.G.values())
        conf = sum(len(L.confirmados) for L in self.leitores)
        return f"🧪 Lateral (sombra): {n} bot(s) lendo · {conf} confirmado(s) · nenhuma ordem"

    def _rodar(self):
        try:
            if not self.preparar():
                self.ao_status(f"🧪 Lateral RECUSADO: {self.recusa}")
                return
            self.ao_status(f"🧪 Lateral ligado ({VERSAO_PONTE}) — modo sombra, nenhuma ordem")
            ult = 0.0
            while not self._parar.is_set():
                try:
                    self.passo()
                    if time.time() - ult > 30:
                        self.ao_status(self.resumo()); ult = time.time()
                except Exception as e:
                    self.erros += 1
                    self.ao_status(f"🧪 Lateral: erro no ciclo ({e}) — tentando de novo")
                    try:
                        from conector_nucleo_homolog import dbg
                        dbg(f"lateral: {e} | {traceback.format_exc(limit=2)}")
                    except Exception:
                        pass
                    self._parar.wait(5)
                self._parar.wait(self.intervalo_s)
        finally:
            for L in self.leitores:
                try:
                    L.enviar(); L.salvar()
                except Exception:
                    pass

    def iniciar(self):
        if not self.tokens or (self.thread and self.thread.is_alive()):
            return False
        self._parar.clear()
        self.thread = threading.Thread(target=self._rodar, daemon=True); self.thread.start()
        return True

    def parar(self, esperar_s=5):
        self._parar.set()
        if self.thread:
            self.thread.join(esperar_s)
