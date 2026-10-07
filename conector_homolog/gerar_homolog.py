"""Gera a cópia de HOMOLOGAÇÃO do conector v1.35 a partir dos originais intactos.
Cada troca é exata (assert de ocorrência única) — se o original mudar, falha alto."""
import hashlib, pathlib, sys

ORIG = pathlib.Path(__file__).parent / "orig"
OUT = pathlib.Path(__file__).parent / "hml"
OUT.mkdir(exist_ok=True)
SHA_ESPERADO = {
    "conector.py": "bb2a95e0947a577153d9e1b7992db504c3a4f3a97931345a2db9553ee1cd7493",
    "conector_nucleo.py": "af8e9e99520d261df6a0f328805a50bf5fb26a55dfa79954748bb111a3741adb",
}
for n, h in SHA_ESPERADO.items():
    assert hashlib.sha256((ORIG / n).read_bytes()).hexdigest() == h, f"original {n} diverge"


def troca(txt, velho, novo, rotulo):
    c = txt.count(velho)
    assert c == 1, f"[{rotulo}] esperado 1 ocorrência, achei {c}"
    return txt.replace(velho, novo)


# ═════════════════════════ NÚCLEO ═════════════════════════
n = (ORIG / "conector_nucleo.py").read_text(encoding="utf-8")

# H1 — destino exclusivo + trava de rede (qualquer URL fora do homolog é RECUSADA)
n = troca(n, 'API_BASE = "https://backtestpro-production-eb9a.up.railway.app"',
'''API_BASE = "https://homolog-homolog.up.railway.app"   # HOMOLOG — nunca produção
HOMOLOG = True
_HML_HOST = "homolog-homolog.up.railway.app"''', "H1-api_base")

n = troca(n, 'APP_NOME = "BotTested Conector"', 'APP_NOME = "BotTested Conector HOMOLOG"', "H2-nome")
n = troca(n, 'APP_VERSAO = "v1.35"', 'APP_VERSAO = "v1.35-hml12"', "H2-versao")

# H3 — log de depuração separado
n = troca(n, '"BotTested_Conector_debug.log"', '"BotTested_Conector_HOMOLOG_debug.log"', "H3-log")
# H4 — config/estado separado (ultimo_token, cache do MetaEditor, pin do MT5)
n = troca(n, '"BotTested_Conector_config.json"', '"BotTested_Conector_HOMOLOG_config.json"', "H4-config")

# H1b — trava de rede (hml2: cobre redirecionamentos) instalada logo após o dbg existir
n = troca(n, "def _rotulo_instalacao(terminal_dir, mql5_dir):",
'''# ── HOMOLOG H1b: TRAVA DE REDE (hml2) ──────────────────────────────────
# Duas barreiras no requests:
#  (a) Session.request: host precisa ser o homolog e allow_redirects é FORÇADO
#      a False — um 301/302/303/307/308 volta como resposta (e fica no log),
#      nunca é seguido;
#  (b) Session.send: toda requisição preparada (inclusive as geradas por
#      resolve_redirects) é conferida de novo e allow_redirects=False.
# Qualquer host diferente de homolog-homolog.up.railway.app é recusado ANTES
# de chegar ao adaptador HTTP (nada sai da máquina).
def _hml_host(url):
    from urllib.parse import urlsplit
    try:
        return (urlsplit(str(url)).hostname or "").lower()
    except Exception:
        return ""


def _hml_checar(metodo, url):
    host = _hml_host(url)
    if host != _HML_HOST or not str(url).lower().startswith("https://"):
        dbg(f"HOMOLOG: BLOQUEADO {metodo} host={host}")
        raise RuntimeError(f"HOMOLOG: destino proibido ({host})")


def _hml_instalar_trava():
    if requests is None:
        return
    S = requests.sessions.Session
    if getattr(S.request, "_hml_trava", False):
        return
    _orig_req, _orig_send = S.request, S.send

    def _req(self, method, url, *a, **kw):
        _hml_checar(method, url)
        kw["allow_redirects"] = False
        r = _orig_req(self, method, url, *a, **kw)
        if 300 <= r.status_code < 400:
            dbg(f"HOMOLOG: redirecionamento RECUSADO HTTP {r.status_code} "
                f"-> host={_hml_host(r.headers.get('Location', ''))}")
        return r

    def _send(self, request, **kw):
        _hml_checar(getattr(request, "method", "?"), getattr(request, "url", ""))
        kw["allow_redirects"] = False
        return _orig_send(self, request, **kw)

    _req._hml_trava = True
    _send._hml_trava = True
    S.request = _req
    S.send = _send


_hml_instalar_trava()


def _rotulo_instalacao(terminal_dir, mql5_dir):''', "H1b-trava")

# H6 — token fora da URL: usa os gêmeos POST (mesma resposta, api 7.79)
n = troca(n, '''        r = requests.get(f"{API_BASE}/conector/meus-bots",
                         params={"bot_token": tok}, timeout=20)''',
'''        r = requests.post(f"{API_BASE}/conector/meus-bots/listar",
                          json={"bot_token": tok}, timeout=20)''', "H6-meus-bots")
n = troca(n, '''        r = requests.get(f"{API_BASE}/conector/tokens",
                         params={"bot_token": tok}, timeout=20)''',
'''        r = requests.post(f"{API_BASE}/conector/tokens/listar",
                          json={"bot_token": tok}, timeout=20)''', "H6-tokens")
n = troca(n, '''        r = requests.get(f"{API_BASE}/conector/bot/mq5",
                         params={"bot_token": (bot_token or "").strip(),
                                 "bot_id": bot_id}, timeout=25)''',
'''        r = requests.post(f"{API_BASE}/conector/bot/mq5/baixar",
                          json={"bot_token": (bot_token or "").strip(),
                                "bot_id": bot_id}, timeout=25)''', "H6-bot-mq5")
n = troca(n, '''        r = requests.get(f"{API_BASE}/mt5/pendente",
                         params={"bot_token": bot_token}, timeout=20)''',
'''        r = requests.post(f"{API_BASE}/mt5/pendente/checar",
                          json={"bot_token": bot_token}, timeout=20)''', "H6-pendente")
n = troca(n, '''        r = requests.get(f"{API_BASE}/mt5/subir-conector",
                         params={"bot_token": (bot_token or "").strip()}, timeout=8)''',
'''        r = requests.post(f"{API_BASE}/mt5/subir-conector/checar",
                          json={"bot_token": (bot_token or "").strip()}, timeout=8)''', "H6-subir")

# H7 — veredito: registra no log o 403 (BT-V01) / 409 (BT-V02) em vez de engolir
n = troca(n, '''            "aprovado": bool(aprovado), "log": (log or "")[:4000],
        }, timeout=20)
        return r.status_code == 200''',
'''            "aprovado": bool(aprovado), "log": (log or "")[:4000],
        }, timeout=20)
        if r.status_code != 200:
            try:
                d = r.json()
                det = d.get("detail", d) if isinstance(d, dict) else d
                cod = det.get("codigo") if isinstance(det, dict) else None
            except Exception:
                cod = None
            dbg(f"veredito RECUSADO job={job_id} HTTP {r.status_code} codigo={cod}")
        else:
            dbg(f"veredito aceito job={job_id} aprovado={bool(aprovado)}")
        return r.status_code == 200''', "H7-veredito")

# H5 — sem autostart e sem protocolo bottested:// (não sequestra os da produção)
n = troca(n, '''    der (nao-Windows, sem permissao), so loga — nunca quebra o app."""
    try:
        import winreg''',
'''    der (nao-Windows, sem permissao), so loga — nunca quebra o app."""
    if HOMOLOG:   # H5: a entrada Run\\BotTestedConector pertence à produção
        dbg("HOMOLOG: autostart DESLIGADO (registro do Windows intocado)")
        return False
    try:
        import winreg''', "H5-autostart")
n = troca(n, '''    Silencioso: se não der (não-Windows, sem permissão), só loga."""
    try:
        import winreg''',
'''    Silencioso: se não der (não-Windows, sem permissão), só loga."""
    if HOMOLOG:   # H5 (hml4): protocolo TEMPORÁRIO com backup do da produção
        return _hml_registrar_protocolo()
    try:
        import winreg''', "H5-protocolo")

# H8 — pin da instalação MT5 (demo) no config do homolog
n = troca(n, "def salvar_token(token):",
'''_PROTO_BACKUP = os.path.join(os.path.expanduser("~"), "BotTested_protocolo_PRODUCAO_backup.txt")
_PROTO_CHAVE = r"Software\\Classes\\bottested\\shell\\open\\command"


def _hml_alvo_protocolo():
    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")   # sem janela de console
    if exe.lower().endswith("python.exe") and os.path.isfile(pw):
        exe = pw
    if exe.lower().endswith(("python.exe", "pythonw.exe")):
        return f'"{exe}" "{os.path.abspath(sys.argv[0])}" "%1"'
    return f'"{exe}" "%1"'


def _hml_ler_protocolo_atual():
    import winreg
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PROTO_CHAVE)
        v, _ = winreg.QueryValueEx(k, "")
        winreg.CloseKey(k)
        return v or ""
    except Exception:
        return ""


def _hml_registrar_protocolo():
    """hml4 — decisão do dono (29/set): durante o ensaio o bottested:// abre o
    conector HOMOLOG, para o Enviar da plataforma funcionar como antes.
    Antes de trocar, guarda o comando da PRODUÇÃO (1x) em arquivo e no config.
    Devolver: py conector_homolog.py --restaurar-protocolo (ou abrir o conector
    de produção, que re-registra o dele a cada abertura)."""
    try:
        import winreg
    except Exception:
        return False
    try:
        alvo = _hml_alvo_protocolo()
        atual = _hml_ler_protocolo_atual()
        if atual and "conector_homolog" not in atual.lower():
            with open(_PROTO_BACKUP, "w", encoding="utf-8") as f:
                f.write(atual)
            _salvar_config({"protocolo_backup": atual})
            dbg("HOMOLOG: comando bottested:// da PRODUÇÃO guardado em backup")
        if atual != alvo:
            base = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\bottested")
            winreg.SetValueEx(base, "", 0, winreg.REG_SZ, "URL:BotTested Conector")
            winreg.SetValueEx(base, "URL Protocol", 0, winreg.REG_SZ, "")
            cmd = winreg.CreateKey(base, r"shell\open\command")
            winreg.SetValueEx(cmd, "", 0, winreg.REG_SZ, alvo)
            winreg.CloseKey(cmd); winreg.CloseKey(base)
        dbg("HOMOLOG: bottested:// -> conector HOMOLOG (temporário)")
        return True
    except Exception as e:
        dbg(f"HOMOLOG registrar_protocolo falhou: {e}")
        return False


def restaurar_protocolo():
    """Devolve o bottested:// ao conector de PRODUÇÃO (valor do backup)."""
    import winreg
    bk = (_ler_config().get("protocolo_backup") or "").strip()
    if not bk and os.path.isfile(_PROTO_BACKUP):
        bk = open(_PROTO_BACKUP, encoding="utf-8").read().strip()
    if not bk:
        return False, "sem backup do protocolo da produção"
    cmd = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _PROTO_CHAVE)
    winreg.SetValueEx(cmd, "", 0, winreg.REG_SZ, bk)
    winreg.CloseKey(cmd)
    dbg("HOMOLOG: bottested:// devolvido à PRODUÇÃO")
    return True, bk


def ler_mt5_pin():
    """HOMOLOG H8: pasta MQL5 do MT5 DEMO escolhida à mão (vazio = sem pin)."""
    return (_ler_config().get("mt5_pin") or "").strip()


def salvar_mt5_pin(mql5_dir):
    if mql5_dir:
        _salvar_config({"mt5_pin": mql5_dir})


def salvar_token(token):''', "H8-pin")

# H10 (hml2) — validar_pendente substituído: gate DEMO + compilação estrita
_i = n.index("def validar_pendente(bot_token, mql5_dir")
_f = n.index("def checar_subir_conector(bot_token):")
assert n.count("def validar_pendente(") == 1 and _i < _f
n = n[:_i] + (pathlib.Path(__file__).parent / "bloco_validacao_hml2.py").read_text(encoding="utf-8") + n[_f:]
assert "validar_sintaxe_mq5(codigo)" not in n[n.index("def validar_pendente("):n.index("def checar_subir_conector")]

# H13 (hml6, C27R13) — o snapshot leva a versão do conector (saúde na Learning Machine)
n = troca(n, '''        "detalhe": dados,''', '''        "detalhe": dict(dados, conector_versao=f"{APP_NOME} {APP_VERSAO}"),''', "H13-versao-snapshot")

# H14 (hml7, C27R14) — PONTE DO MOTOR (contrato v1.37.0-ciclovivo): antes do POST,
# anexa detalhe.cv_atestado assinado pelo motor dos Ciclos (bt_ciclo_v1 via
# bt_conector_atestado.ler_e_assinar_motor) para o MESMO símbolo/magic do bt_snap.
# Pasta do espelho, pasta dos módulos e segredo vêm SÓ do ambiente local
# (BT_CV_ESPELHO / BT_CV_MOTOR_DIR / BT_CV_SEGREDO). Falha = snapshot SEM atestado
# e o motivo vai em detalhe.cv_atestado_falha (a API mostra qual elo falhou).
# H15 (hml8, C27R14 rev.2) — a ponte passa a ler o LEITOR DO MOTOR
# (bt_motor_leitura_hml: SAUDE.json/ATUAL.json/barras) e confere identidade
# (conta, símbolo, instalação, barra e OHLC) e fuso EA×motor antes de assinar;
# a saúde do motor vai sempre em detalhe.cv_motor. Bloco em ponte_motor_hml8.py.
n = troca(n, """def enviar_snapshot(bot_token, dados):
    \"\"\"Manda snapshot pro /conector/snapshot. Read-only.\"\"\"
    if requests is None:
        return False""", (pathlib.Path(__file__).parent / "ponte_motor_hml8.py").read_text(encoding="utf-8"),
    "H14/H15-ponte-motor")

# H16 (hml9, C27R16) — CANAL DE COMANDO nuvem → conector → EA, só com a DEMO conferida.
# O conector transporta o comando que a API criou pela RPC dos Ciclos; não decide nada.
n = troca(n, "def checar_subir_conector(bot_token):\n",
          (pathlib.Path(__file__).parent / "comando_hml9.py").read_text(encoding="utf-8"), "H16-comando")

(OUT / "conector_nucleo_homolog.py").write_text(n, encoding="utf-8")

# ═════════════════════════ JANELA ═════════════════════════
c = (ORIG / "conector.py").read_text(encoding="utf-8")

c = troca(c, "from conector_nucleo import (", "from conector_nucleo_homolog import (", "J0-import")
c = troca(c, "    registrar_autostart,\n)", "    registrar_autostart,\n    ler_mt5_pin, salvar_mt5_pin, HOMOLOG,\n)", "J0-import2")

# H9 — lock de instância única em porta própria (não conversa com a produção)
c = troca(c, "_LOCK_PORT = 50573", "_LOCK_PORT = 50574   # HOMOLOG H9 (produção usa 50573)", "H9-lock")

# H8 — seleção inicial: só o pin; sem pin e com >1 MT5, nada é vigiado até escolher
c = troca(c, '''        idx0 = self._idx_instalacao_ativa()
        self.combo_mt5.current(idx0)
        self.mql5_dir = self.instalacoes[idx0]["mql5"]
''', '''        # HOMOLOG H8: nada de "instalação mais fresca" — só a DEMO fixada à mão.
        pin = ler_mt5_pin()
        idx0 = next((i for i, inst in enumerate(self.instalacoes)
                     if inst.get("mql5") == pin), None)
        if idx0 is None and len(self.instalacoes) == 1:
            idx0 = 0
        if idx0 is None:
            self.mql5_dir = None
            self.frame_seletor.pack(fill="x", padx=22, pady=(0, 6),
                                    after=self.lbl_mt5)
            self.lbl_mt5.config(
                text="⚠ HOMOLOG: escolha abaixo o MT5 DEMO — ele fica fixado.",
                fg=COR_VERMELHO)
            return
        self.combo_mt5.current(idx0)
        self.mql5_dir = self.instalacoes[idx0]["mql5"]
''', "H8-detectar")
c = troca(c, '''        idx = self.combo_mt5.current()
        if 0 <= idx < len(self.instalacoes):
            self._trocar_instalacao(idx, origem="manual")''',
'''        idx = self.combo_mt5.current()
        if 0 <= idx < len(self.instalacoes):
            self._trocar_instalacao(idx, origem="manual")
            salvar_mt5_pin(self.instalacoes[idx]["mql5"])   # HOMOLOG H8
            dbg(f"HOMOLOG: MT5 fixado -> {self.instalacoes[idx]['mql5']}")''', "H8-manual")
c = troca(c, '''        try:
            if len(self.instalacoes) > 1 and self.mql5_dir:
                ign = self._magics_orfaos()''',
'''        try:
            if not HOMOLOG and len(self.instalacoes) > 1 and self.mql5_dir:   # H8: radar off
                ign = self._magics_orfaos()''', "H8-radar")

# H10 (hml2) — importa a conferência DEMO
c = troca(c, "    ler_mt5_pin, salvar_mt5_pin, HOMOLOG,\n)",
          "    ler_mt5_pin, salvar_mt5_pin, HOMOLOG,\n    conferir_demo, confirmar_demo, resetar_demo, restaurar_protocolo,\n)", "H10-import")
# H16 (hml9) — laço do canal de comando em thread própria (não atrasa a leitura do snapshot)
c = troca(c, "    conferir_demo, confirmar_demo, resetar_demo, restaurar_protocolo,\n)",
          "    conferir_demo, confirmar_demo, resetar_demo, restaurar_protocolo, cmd_passo,\n)", "H16-import")
c = troca(c, """        threading.Thread(target=self._loop_eventos, daemon=True).start()  # v1.35
""", """        threading.Thread(target=self._loop_eventos, daemon=True).start()  # v1.35
        threading.Thread(target=self._loop_comandos, daemon=True).start()  # HOMOLOG H16
""", "H16-thread")
c = troca(c, """    def _loop_eventos(self):""", """    def _loop_comandos(self):
        \"\"\"HOMOLOG H16 — canal de comando: só para bots com snapshot FRESCO (EA vivo no
        gráfico) e com a DEMO conferida. Um passo por bot a cada ~2 s.\"\"\"
        while self.rodando:
            try:
                agora = time.time()
                for mg in list(self._snaps_por_magic.keys()):
                    tok = self._token_por_magic.get(mg)
                    if not mg or not tok or not self.mql5_dir:
                        continue
                    if (agora - self._lido_por_magic.get(mg, 0)) > 35:
                        continue          # EA sem sinal: não entrega comando a ninguém
                    msg = cmd_passo(tok, mg, self.mql5_dir)
                    if msg:
                        self._set_status(f"{time.strftime('%H:%M:%S')} {msg}"[:110])
            except Exception as e:
                dbg(f"loop comandos: {e}")
            time.sleep(2)

    def _loop_eventos(self):""", "H16-laco")
# H10 — botão "Conferir MT5 DEMO" logo acima do Conectar
c = troca(c, "        self.btn_conectar = tk.Button(self.root, text=\"▶  Conectar e monitorar\",",
'''        self.btn_demo = tk.Button(self.root, text="🔎  Conferir MT5 DEMO (obrigatório antes do job)",
                                  command=self._hml_conferir_demo, bg=COR_CARD, fg=COR_TEXTO,
                                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2")
        self.btn_demo.pack(fill="x", padx=22, pady=(10, 0))
        self.btn_conectar = tk.Button(self.root, text="▶  Conectar e monitorar",''', "H10-botao")
c = troca(c, "    def _trocar_instalacao(self, idx, origem=\"radar\"):",
'''    def _hml_conferir_demo(self):
        """HOMOLOG H10: conferência da conta DEMO. Leitura automática (diário do
        terminal) + confirmação VISUAL obrigatória na janela do MT5."""
        if not self.mql5_dir:
            messagebox.showwarning(APP_NOME, "Escolha primeiro o MT5 DEMO no seletor.")
            return
        info = conferir_demo(self.mql5_dir)
        txt = (f"Instalação: {info['terminal']}\\n"
               f"Programa: {info['programa'] or '?'}\\n"
               f"Conta (login): {info['login'] or '?'}\\n"
               f"Servidor: {info['servidor'] or '?'}  (fonte: {info['fonte']})\\n"
               f"AutoTrading (último registro do diário): {info['autotrading']}\\n\\n")
        if not info["demo"]:
            resetar_demo()
            messagebox.showerror(APP_NOME, txt + "✗ Servidor NÃO identificado como DEMO.\\n"
                                 "Jobs continuam BLOQUEADOS nesta instalação.")
            self.lbl_mt5.config(text="✗ HOMOLOG: instalação NÃO é demo — jobs bloqueados",
                                fg=COR_VERMELHO)
            return
        if info["autotrading"] == "on":   # hml3: aceito na DEMO, só avisa
            txt += ("⚠ Algo Trading LIGADO nesta DEMO: o EA do MASTER, se for arrastado\\n"
                    "ao gráfico, pode operar nesta conta demo.\\n\\n")
        ok = messagebox.askyesno(APP_NOME, txt +
            "Agora confira NA JANELA DO MT5 desta instalação:\\n"
            "• Navegador → Contas: este login, com o servidor Demo;\\n"
            "• barra de título com o mesmo login e 'Demo Account';\\n"
            "• (Algo Trading pode ficar como está — conta DEMO).\\n\\n"
            "Tudo confere?")
        if ok:
            confirmar_demo(self.mql5_dir, info)
            self.lbl_mt5.config(text=f"✓ HOMOLOG: DEMO conferida — {info['servidor']} "
                                     f"(login {info['login']})\\n{self.mql5_dir}", fg=COR_VERDE)
        else:
            resetar_demo()
            self.lbl_mt5.config(text="⚠ HOMOLOG: conferência DEMO recusada — jobs bloqueados",
                                fg=COR_VERMELHO)

    def _trocar_instalacao(self, idx, origem="radar"):
        resetar_demo()   # HOMOLOG H10: trocou de instalação → confere de novo''', "H10-conferir")
# H10 — status mostra o bloqueio do gate
c = troca(c, '''                                + (f" — {msg[:50]}" if msg else ""))
                    except Exception as e:''',
'''                                + (f" — {msg[:50]}" if msg else ""))
                        elif msg and msg.startswith("BT-HML-D"):
                            self._set_status("⚠ " + msg[:90])
                    except Exception as e:''', "H10-status")
# H12 (hml4) — "py conector_homolog.py --restaurar-protocolo" devolve o bottested:// à produção e sai
c = troca(c, """def main():
    if tk is None:""", """def main():
    if "--restaurar-protocolo" in sys.argv[1:]:
        ok, det = restaurar_protocolo()
        print("OK: bottested:// devolvido ao conector de PRODUCAO" if ok else "FALHOU: " + det)
        return
    if tk is None:""", "H12-restaurar")
# H17 (hml9) — "--conectar": ao abrir pelo instalador, liga o monitor sozinho SE já houver token
# salvo e MT5 fixado (sem caixa de diálogo). A conferência DEMO continua manual.
c = troca(c, """    threading.Thread(target=_servir_tokens, args=(srv, app), daemon=True).start()
    root.mainloop()""", """    threading.Thread(target=_servir_tokens, args=(srv, app), daemon=True).start()
    if "--conectar" in argv:
        root.after(2500, app._hml_autoconectar)
    root.mainloop()""", "H17-main")
c = troca(c, "    def _toggle_conectar(self):", """    def _hml_autoconectar(self):
        try:
            if self.rodando:
                return
            if not self.entry_token.get().strip() or not self.mql5_dir:
                self._set_status("HOMOLOG: --conectar sem token salvo ou sem MT5 fixado — clique em Conectar")
                return
            dbg("HOMOLOG: conexão automática (--conectar)")
            self._toggle_conectar()
        except Exception as e:
            dbg(f"autoconectar: {e}")

    def _toggle_conectar(self):""", "H17-metodo")

# H18 (hml10) — rótulo da trilha: sem sinal do MT5 não é "sem conexão com a plataforma"
c = troca(c, 'text="sem conexão com a plataforma",',
          'text=("nada a enviar: sem sinal do MT5" if not e_mt5 else "sem conexão com a plataforma"),', "H18-rotulo")

# H11 — nada de fragmento de token ou argv no log
c = c.replace("token {tok[:8]}…", "token ***")
assert "{tok[:8]}" in c
c = troca(c, 'dbg(f"validar_pendente({tok[:8]}…) no loop: {e}")', 'dbg(f"validar_pendente(***) no loop: {e}")', "H11-loop")
c = troca(c, 'dbg(f"aberto via protocolo: {argv} |', 'dbg(f"aberto via protocolo: {len(argv)} arg(s) |', "H11-argv")
assert "[:8]}" not in c

(OUT / "conector_homolog.py").write_text(c, encoding="utf-8")

for f in ("conector_homolog.py", "conector_nucleo_homolog.py"):
    print(hashlib.sha256((OUT / f).read_bytes()).hexdigest(), f)
