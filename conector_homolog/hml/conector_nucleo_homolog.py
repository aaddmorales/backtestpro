"""
═══════════════════════════════════════════════════════════════════════
 BotTested Conector v1.7 — app desktop (Windows) que liga o MT5 à plataforma.
 Read-only: instala o EA na pasta certa, lê o log e reporta pra nuvem.
 NUNCA pede senha de corretora. NUNCA comanda o bot.
 v1.7: card "Meus bots" — lista os bots do usuário pelo token e permite
       Reinstalar (do .mq5 salvo na nuvem), Desinstalar (tira do MT5, mantém
       no histórico) e Deletar (some do histórico + tira do MT5).
 v1.6: botão Instalar manda NOME DO BOT + token → o EA no MT5 leva o nome do bot
       (não o da estratégia) e ganha magic único (nunca colide no multi-bot).
 v1.5: extrair_token_do_protocolo() lê o ?token= da URL bottested:// (o front
       já mandava; o conector descartava) → auto-conecta na 1ª vez sem colar nada.

 Compilar no Windows:
   pip install requests
   pip install pyinstaller
   pyinstaller --onefile --windowed --name "BotTested Conector" conector.py

 Resultado: dist/BotTested Conector.exe
═══════════════════════════════════════════════════════════════════════
"""
import os
import sys
import re
import glob
import time
import json
import shutil
import threading
import traceback
import datetime

try:
    import requests
except Exception:
    requests = None

# ── Configuração ───────────────────────────────────────────────────
API_BASE = "https://homolog-homolog.up.railway.app"   # HOMOLOG — nunca produção
HOMOLOG = True
_HML_HOST = "homolog-homolog.up.railway.app"
INTERVALO_SNAPSHOT = 20      # segundos entre snapshots pra nuvem (v1.25: era 60 — presença mais viva e religar rápido)
APP_NOME = "BotTested Conector HOMOLOG"
APP_VERSAO = "v1.35-hml11"  # v1.35: fila de envio de eventos + coalescencia de recusadas (conector.py) + backlog bt_ev_ 1a vez >90s drena sem emitir + fix do rotulo de versao (ficou v1.33 por engano na v1.34).  # v1.33: janela 520->620px + redimensionavel na vertical — a trilha da v1.31 empurrou a LINHA DE STATUS (diagnostico vivo) pra fora da janela fixa e o dono nao conseguia expandir. v1.32: radar de instalacao.  # v1.32: RADAR DE INSTALACAO — fix do dropdown que nao funcionava (deteccao SEMPRE forcava a instalacao [0] a cada abertura; escolha nunca sobrevivia ao restart) + a deteccao agora escolhe a instalacao com bt_snap_/bt_ev_ mais FRESCO, troca manual limpa os caches de leitura e mostra a pasta vigiada, e um radar de 12s troca SOZINHO pra instalacao com atividade quando a atual esta muda >120s — o usuario nunca mais adivinha qual MT5: o dado manda. v1.31: fix magic 0 (nome do arquivo) + trilha de conexao.  # v1.31: (1) FIX DO MAGIC 0 — ler_eventos_arquivo deriva o magic do NOME bt_ev_<magic>.txt (a linha do EA nao carimba magic=; conector assumia 0, roteava errado, backend rejeitava, BabyMachine cega — vale p/ todos os bots ja instalados, sem reenvio); (2) TRILHA DE CONEXAO no conector.py (desenho do dono): MT5 -> Conector -> Plataforma com circulacao viva.         # v1.30 F2: EVENTOS POR ARQUIVO (ler_eventos_arquivo le bt_ev_<magic>.txt append-consume — canal confiavel pra BabyMachine, log vira fallback anti-duplicado). AUTOSTART obrigatorio/silencioso/auto-curavel (sobe com o Windows -> reboot nunca deixa a plataforma cega; re-registra a cada abertura se algo remover) + FIX DA MENTIRA SISTEMATICA no parser de posicoes (campo "posicoes" ausente vira None, nao 0 -> nao dispara reconciliacao de orfas indevida, incidente v6.91). Botao de reabrir ja existe via bottested:// (plataforma).          # v1.29: presenca em lote (1 POST p/ todos os tokens; fila serial so p/ quem tem job). v1.28: refresh de tokens 30s->8s (token de bot NOVO descoberto antes da janela de ~25s do front — matava o "could not reach the connector" no 1o envio). v1.27: VALIDACAO RELAMPAGO — job pre_validado (nuvem v6.38: mesmo codigo ja aprovado antes) instala, reporta o veredito NA HORA e compila em 2o plano (so pra gerar o .ex5). Corta a validacao repetida de ~25-55s pra ~5-10s. v1.26: FIM DE VIDA (EA escreve BOTTESTED_FIM no OnDeinit -> parada sinalizada na hora) + WATCHDOG (dado >35s sem leitura nova NAO e reenviado e sinaliza parada -> snapshot velho nunca mais segura o OPERANDO vivo) + rede pesada em thread propria (loop de leitura nunca bloqueia). v1.25: (1) magic->token mapeado NA INSTALACAO (extrai o magic do proprio .mq5 baixado -> zero dependencia da nuvem pro bot novo); (2) RELIGAR imediato (gap >25s no arquivo bt_snap = bot voltou -> envia ja, sem esperar o intervalo); (3) INTERVALO 60->20s; (4) aviso de EA ORFAO (magic sem dono na nuvem). v1.24: snapshot por arquivo dedicado. v1.23: throttle proprio 2s + diagnostico com hora.


# ── 0. Log de debug em arquivo ─────────────────────────────────────
# Como o .exe roda com --windowed (sem console), qualquer erro fica
# invisível. Este log grava o que o conector faz num arquivo de texto
# fácil de achar (na pasta do usuário). Reseta sozinho se passar de 2 MB.
DEBUG = True
DEBUG_PATH = os.path.join(os.path.expanduser("~"), "BotTested_Conector_HOMOLOG_debug.log")


def dbg(msg):
    """Escreve uma linha no log de debug do conector."""
    if not DEBUG:
        return
    try:
        if os.path.isfile(DEBUG_PATH) and os.path.getsize(DEBUG_PATH) > 2_000_000:
            os.remove(DEBUG_PATH)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(DEBUG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── 1. Encontrar a pasta de dados do MT5 (MQL5/Experts) ────────────
# ── HOMOLOG H1b: TRAVA DE REDE (hml2) ──────────────────────────────────
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


def _rotulo_instalacao(terminal_dir, mql5_dir):
    """Tenta dar um nome legível à instalação (corretora/servidor) lendo
    arquivos de config do MT5. Cai pro fim do caminho se não achar."""
    # 1) tenta o origin.txt (caminho do terminal de origem, costuma ter o nome)
    try:
        org = os.path.join(terminal_dir, "origin.txt")
        if os.path.isfile(org):
            with open(org, "r", encoding="utf-16", errors="ignore") as f:
                txt = f.read().strip()
            if txt:
                # pega a última pasta do caminho (ex: "MetaTrader 5 IC Markets")
                base = os.path.basename(txt.rstrip("\\/"))
                if base:
                    return base
    except Exception:
        pass
    # 2) tenta achar o nome do servidor nos .ini de config
    try:
        cfg = os.path.join(terminal_dir, "config")
        if os.path.isdir(cfg):
            for ini in glob.glob(os.path.join(cfg, "*.ini")):
                with open(ini, "r", encoding="utf-16", errors="ignore") as f:
                    for linha in f:
                        if linha.lower().startswith("server="):
                            srv = linha.split("=", 1)[1].strip()
                            if srv:
                                return f"Servidor: {srv}"
                break
    except Exception:
        pass
    # 3) fallback: hash curto do caminho
    h = os.path.basename(os.path.dirname(mql5_dir))
    return f"Instalação …{h[-6:]}" if h else "MetaTrader 5"


def achar_pastas_mt5():
    """Acha as instalações do MT5 no Windows. Retorna lista de dicts:
    {'mql5': caminho_MQL5, 'rotulo': nome_legivel, 'terminal': pasta_terminal}.
    O MT5 guarda os dados em %APPDATA%\\MetaQuotes\\Terminal\\<hash>\\MQL5."""
    achadas = []
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        user = os.environ.get("USERPROFILE", "")
        appdata = os.path.join(user, "AppData", "Roaming")
    base = os.path.join(appdata, "MetaQuotes", "Terminal")
    if not os.path.isdir(base):
        return achadas
    for nome in os.listdir(base):
        caminho = os.path.join(base, nome)
        mql5 = os.path.join(caminho, "MQL5")
        if os.path.isdir(mql5) and re.fullmatch(r"[0-9A-Fa-f]{20,40}", nome):
            achadas.append({
                "mql5": mql5,
                "terminal": caminho,
                "rotulo": _rotulo_instalacao(caminho, mql5),
            })
    return achadas


def pasta_experts(mql5_dir):
    """Caminho da pasta Experts dentro de uma instalação MQL5."""
    return os.path.join(mql5_dir, "Experts")


def instalar_ea(conteudo_mq5, nome_arquivo, mql5_dir):
    """Salva o .mq5 na pasta Experts da instalação escolhida.
    Retorna (ok, mensagem)."""
    try:
        exp = pasta_experts(mql5_dir)
        os.makedirs(exp, exist_ok=True)
        if not nome_arquivo.lower().endswith(".mq5"):
            nome_arquivo += ".mq5"
        destino = os.path.join(exp, nome_arquivo)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(conteudo_mq5)
        return True, destino
    except Exception as e:
        return False, str(e)


def baixar_e_instalar_ea(estrategia_id, estrategia_nome, mql5_dir, params=None,
                         bot_nome="", bot_token=""):
    """Pede o .mq5 pra API (endpoint /exportar/mql5) e instala na pasta.
    params: dict opcional com ativo/stop_loss/take_profit/ema_period.
    bot_nome: vira o NOME DO ARQUIVO/EA no MT5 (identidade do bot).
    bot_token: deriva o MAGIC único por bot (não colide com outros bots)."""
    if requests is None:
        return False, "Biblioteca 'requests' ausente."
    body = {
        "estrategia_id": estrategia_id,
        "estrategia_nome": estrategia_nome,
        "codigo": "",
        "ativo": (params or {}).get("ativo", ""),
        "stop_loss": (params or {}).get("stop_loss", 50),
        "take_profit": (params or {}).get("take_profit", 100),
        "ema_period": (params or {}).get("ema_period", 20),
        "timeframe": (params or {}).get("timeframe", "1d"),
        "bot_nome": (bot_nome or "").strip(),
        "bot_token": (bot_token or "").strip(),
    }
    try:
        r = requests.post(f"{API_BASE}/exportar/mql5", json=body, timeout=25)
        if r.status_code != 200:
            return False, f"API status {r.status_code}"
        d = r.json()
        if not d.get("codigo"):
            return False, d.get("aviso", "Sem código retornado.")
        return instalar_ea(d["codigo"], d.get("filename", "BotTested_EA.mq5"), mql5_dir)
    except Exception as e:
        return False, str(e)


# ── Card "Meus bots": listar / reinstalar / desinstalar / deletar ──────
def listar_meus_bots(bot_token):
    """Lista os bots do usuário DONO do token (pro card 'Meus bots').
    Retorna (ok, lista_de_bots) ou (False, msg_erro). Cada bot tem
    id, nome, simbolo, magic_number, filename, online, tem_mq5."""
    if requests is None:
        return False, "Biblioteca 'requests' ausente."
    tok = (bot_token or "").strip()
    if not tok:
        return False, "sem token"
    try:
        r = requests.post(f"{API_BASE}/conector/meus-bots/listar",
                          json={"bot_token": tok}, timeout=20)
        if r.status_code == 200:
            return True, (r.json().get("bots") or [])
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def listar_tokens_do_usuario(bot_token):
    """MULTI-BOT: dado UM token válido, busca na nuvem os tokens de TODOS os bots
    do usuário — pra vigiar/validar todos ao mesmo tempo (um conector, vários
    bots). Retorna (ok, lista) onde cada item tem id, nome, bot_token, filename;
    ou (False, msg_erro)."""
    if requests is None:
        return False, "Biblioteca 'requests' ausente."
    tok = (bot_token or "").strip()
    if not tok:
        return False, "sem token"
    try:
        r = requests.post(f"{API_BASE}/conector/tokens/listar",
                          json={"bot_token": tok}, timeout=20)
        if r.status_code == 200:
            return True, (r.json().get("tokens") or [])
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


# ── PRESENÇA (sensor de atividade) — ponta do coletor ────────────────────────
# Este pedaço é o que a plataforma futura (Tryd) vai reusar: o coletor só EMPURRA
# sinais pro backend, que é a fonte de verdade. Heartbeat já é o /mt5/pendente;
# snapshot já é o /conector/snapshot; aqui fica o aviso EXPLÍCITO de PARADA, que
# dá o corte imediato da trilha/monitor quando o usuário aperta Parar.
def sinalizar_parada(tokens):
    """Avisa a nuvem que o coletor PAROU (corte imediato). Aceita lista de tokens
    (o conector monitora vários bots). Retorna True se o POST saiu."""
    if requests is None:
        return False
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return False
    try:
        requests.post(f"{API_BASE}/presenca/parar",
                      json={"tokens": toks}, timeout=8)
        dbg(f"presenca: parada sinalizada p/ {len(toks)} token(s)")
        return True
    except Exception as e:
        dbg(f"sinalizar_parada: {e}")
        return False


def reinstalar_bot(bot_token, bot_id, mql5_dir):
    """Puxa o .mq5 salvo do bot na nuvem e reinstala na pasta Experts.
    Retorna (ok, msg)."""
    if requests is None:
        return False, "Biblioteca 'requests' ausente."
    try:
        r = requests.post(f"{API_BASE}/conector/bot/mq5/baixar",
                          json={"bot_token": (bot_token or "").strip(),
                                "bot_id": bot_id}, timeout=25)
    except Exception as e:
        return False, str(e)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    d = r.json()
    if not d.get("tem_mq5"):
        return False, ("Esse bot foi criado antes de guardarmos o código na nuvem. "
                       "Reenvie ele uma vez pelo Editor (Enviar pro MT5) e o reinstalar passa a funcionar.")
    return instalar_ea(d.get("codigo", ""), d.get("filename", "MeuBot.mq5"), mql5_dir)


def desinstalar_ea_local(mql5_dir, filename):
    """Remove o .mq5 do bot da pasta Experts (tira do MT5), mas o bot continua
    no histórico. Retorna (ok, msg)."""
    try:
        exp = pasta_experts(mql5_dir)
        fn = filename or ""
        if not fn.lower().endswith(".mq5"):
            fn += ".mq5"
        alvo = os.path.join(exp, fn)
        if os.path.exists(alvo):
            os.remove(alvo)
            return True, alvo
        return True, "arquivo já não estava na pasta"
    except Exception as e:
        return False, str(e)


def deletar_bot(bot_token, bot_id, mql5_dir=None, filename=""):
    """Deleta o bot: soft-delete na nuvem (some do histórico/lista) e, de quebra,
    remove o .mq5 local se der. Retorna (ok, msg)."""
    if requests is None:
        return False, "Biblioteca 'requests' ausente."
    try:
        r = requests.post(f"{API_BASE}/conector/bot/excluir",
                          json={"bot_token": (bot_token or "").strip(), "bot_id": bot_id},
                          timeout=20)
    except Exception as e:
        return False, str(e)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if mql5_dir and filename:
        try: desinstalar_ea_local(mql5_dir, filename)
        except Exception: pass
    return True, "bot deletado"


# ── 2. Ler o log do EA (read-only) ─────────────────────────────────
def achar_logs_mt5(mql5_dir):
    """Os logs do EA (onde sai o BOTTESTED_SNAPSHOT) ficam em <terminal>/MQL5/Logs.
    O terminal também escreve em <terminal>/Logs (journal). PRIORIDADE: o log do
    EA (MQL5/Logs) SEMPRE primeiro — o loop lê os primeiros da lista, e antes a
    ordenação por mtime às vezes jogava o log do EA pra fora do top-2 (o journal do
    terminal ficava mais recente), fazendo o conector PARAR de ler o snapshot até a
    ordem mudar. Era a causa da variação grande no tempo de acender (14s a 2min)."""
    terminal_dir = os.path.dirname(mql5_dir)  # sobe de MQL5 pro terminal

    def _recentes(d):
        if not os.path.isdir(d):
            return []
        arqs = glob.glob(os.path.join(d, "*.log"))
        arqs.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                  reverse=True)
        return arqs

    experts  = _recentes(os.path.join(mql5_dir, "Logs"))       # onde o EA imprime
    terminal = _recentes(os.path.join(terminal_dir, "Logs"))   # journal do terminal
    return experts + terminal   # EA primeiro, sempre


def _detectar_encoding(caminho_log):
    """Detecta o encoding do log do MT5 lendo o BOM / primeiros bytes.
    O MT5 grava os .log em UTF-16 LE (com BOM) na grande maioria das
    builds, mas algumas gravam UTF-8. Retorna o nome do encoding."""
    try:
        with open(caminho_log, "rb") as f:
            inicio = f.read(4)
    except Exception:
        return "utf-8"
    if inicio[:2] == b"\xff\xfe":
        return "utf-16-le"
    if inicio[:2] == b"\xfe\xff":
        return "utf-16-be"
    # sem BOM: heurística pelos nulls (texto ASCII em UTF-16 tem 0x00
    # intercalado em cada caractere)
    if len(inicio) >= 2 and inicio[1] == 0:
        return "utf-16-le"
    if len(inicio) >= 1 and inicio[0] == 0:
        return "utf-16-be"
    return "utf-8"


def ler_novas_linhas(caminho_log, posicao_anterior):
    """Lê só as linhas novas de um log desde a última posição (em bytes).
    Trabalha em modo binário e decodifica com o encoding detectado, pra
    suportar os logs UTF-16 do MT5 sem quebrar o controle de posição.
    Só consome até a última quebra de linha completa (não pega linha
    pela metade). Retorna (linhas_novas, nova_posicao_em_bytes)."""
    try:
        tamanho = os.path.getsize(caminho_log)
    except Exception:
        return [], posicao_anterior
    if tamanho < posicao_anterior:
        posicao_anterior = 0          # log rotacionou / recriado
    if tamanho <= posicao_anterior:
        return [], posicao_anterior   # nada novo
    enc = _detectar_encoding(caminho_log)
    try:
        with open(caminho_log, "rb") as f:
            f.seek(posicao_anterior)
            bruto = f.read()
    except Exception:
        return [], posicao_anterior
    if not bruto:
        return [], posicao_anterior
    texto = bruto.decode(enc, errors="ignore")
    corte = texto.rfind("\n")
    if corte == -1:
        return [], posicao_anterior   # ainda não há linha completa
    consumido = texto[:corte + 1]
    novas = consumido.splitlines()
    try:
        # quantos bytes do arquivo o texto consumido representa, pra
        # avançar a posição corretamente no encoding original
        bytes_consumidos = len(consumido.encode(enc, errors="ignore"))
    except Exception:
        bytes_consumidos = len(bruto)
    nova_pos = posicao_anterior + bytes_consumidos
    return novas, nova_pos


# Marcadores que o EA do BotTested imprime no log (Print no MQL5).
# O EA pode ser instrumentado pra imprimir linhas assim:
#   "BOTTESTED_EVENTO|aberto|BUY|XAUUSD|preco=2345.6"
#   "BOTTESTED_SNAPSHOT|equity=633180|dd=2.1|posicoes=1"
_RE_EVENTO = re.compile(r"BOTTESTED_EVENTO\|([^|]+)\|(.*)")
_RE_SNAPSHOT = re.compile(r"BOTTESTED_SNAPSHOT\|(.*)")
_RE_FIM = re.compile(r"BOTTESTED_FIM\|(.*)")   # v1.26: EA avisa que saiu do gráfico (OnDeinit)


def parse_linha_log(linha):
    """Interpreta uma linha do log do EA. Retorna ('evento', dados) ou
    ('snapshot', dados) ou (None, None)."""
    m = _RE_EVENTO.search(linha)
    if m:
        tipo = m.group(1).strip()
        resto = m.group(2).strip()
        dados = {"tipo": tipo, "raw": resto}
        for par in resto.split("|"):
            if "=" in par:
                k, v = par.split("=", 1)
                dados[k.strip()] = v.strip()
        return "evento", dados
    m = _RE_SNAPSHOT.search(linha)
    if m:
        resto = m.group(1).strip()
        dados = {}
        for par in resto.split("|"):
            if "=" in par:
                k, v = par.split("=", 1)
                dados[k.strip()] = v.strip()
        return "snapshot", dados
    return None, None


# ── 2b. Snapshot por ARQUIVO DEDICADO (v1.24) ──────────────────────
def ler_snapshots_arquivo(mql5_dir, mtimes_cache):
    """Lê os arquivos <MQL5>/Files/bt_snap_<magic>.txt. O EA (api v6.36+) grava
    ali o último snapshot com flush imediato (FileClose) — diferente do log do
    MT5, que tem buffer e às vezes demora MINUTOS pra ir ao disco (a causa do
    Operar acender em 22s–2min15s). Lendo o arquivo, o snapshot chega em <=1 ciclo
    do loop (1.5s), consistente.

    mtimes_cache: dict {caminho -> mtime da última leitura}. Só retorna arquivos
    que MUDARAM desde a última chamada (o EA regrava a cada 10s; sem isso o loop
    reprocessaria o mesmo snapshot a cada 1.5s).

    Ignora arquivos parados há mais de 120s: bot que saiu do gráfico deixa o
    arquivo pra trás — snapshot velho não pode reacender o Operar.

    Retorna lista de dicts de snapshot já parseados (mesmo formato do log)."""
    out = []
    pasta = os.path.join(mql5_dir, "Files")
    if not os.path.isdir(pasta):
        return out
    try:
        arquivos = glob.glob(os.path.join(pasta, "bt_snap_*.txt"))
    except Exception:
        return out
    agora = time.time()
    for a in arquivos:
        try:
            mt = os.path.getmtime(a)
        except Exception:
            continue
        mt_anterior = mtimes_cache.get(a)
        if mt_anterior == mt:
            continue                      # nada novo neste arquivo
        if (agora - mt) > 120:
            mtimes_cache[a] = mt          # velho demais: marca e ignora
            continue
        try:
            with open(a, "rb") as f:
                bruto = f.read(8192)
        except Exception:
            # o EA pode estar escrevendo neste instante (lock do Windows);
            # NÃO marca o mtime — tenta de novo no próximo ciclo (1.5s).
            continue
        mtimes_cache[a] = mt
        # RELIGAR (v1.25): o EA regrava a cada 10s; um gap >25s entre escritas
        # significa que ele saiu e VOLTOU (religou / re-arrastou). Marca o
        # snapshot pra o conector zerar o throttle e enviar JÁ — sem isso o
        # religar esperava o resto do intervalo (era a causa dos 32-42s).
        religou = bool(mt_anterior is not None and (mt - mt_anterior) > 25)
        # tolerante a encoding: FILE_ANSI é o esperado, mas se a IA usar
        # FILE_UNICODE (UTF-16) os nulls são descartados e o texto sobrevive.
        texto = bruto.replace(b"\x00", b"").decode("utf-8", errors="ignore")
        for linha in texto.splitlines():
            # FIM DE VIDA (v1.26): o EA (api v6.37+) escreve BOTTESTED_FIM no
            # OnDeinit quando é REMOVIDO do gráfico — o conector sinaliza a
            # parada na hora (desligar ~5-12s, em vez de errático até 3min).
            mfim = _RE_FIM.search(linha)
            if mfim:
                dfim = {"_fim": "1"}
                for par in mfim.group(1).split("|"):
                    if "=" in par:
                        k, v = par.split("=", 1)
                        dfim[k.strip()] = v.strip()
                out.append(dfim)
                continue
            tipo, dados = parse_linha_log(linha)
            if tipo == "snapshot":
                if religou:
                    dados["_religou"] = "1"   # interno: o conector remove antes de enviar
                out.append(dados)
    return out


def ler_eventos_arquivo(mql5_dir, pos_cache):
    """v1.30 FASE 2 — Lê os arquivos <MQL5>/Files/bt_ev_<magic>.txt, onde o EA
    (api v6.97+) grava CADA evento (aberto/rejeitado/fechado) numa linha com
    flush imediato (FileClose). Canal CONFIAVEL: diferente do log do MT5 (buffer
    que atrasa/perde eventos na rajada), o arquivo chega em <=1 ciclo do loop.

    APPEND-CONSUME: o EA SÓ adiciona linhas (nunca sobrescreve), então este leitor
    rastreia a POSIÇÃO em bytes já lida de cada arquivo (pos_cache: {caminho ->
    offset}). Cada chamada devolve só as linhas NOVAS desde a última — nunca
    reprocessa um evento, nunca perde um (ao contrário do snapshot, que só quer o
    ÚLTIMO estado; aqui cada evento importa).

    Retorna lista de dicts de evento já parseados (mesmo formato do log)."""
    out = []
    pasta = os.path.join(mql5_dir, "Files")
    if not os.path.isdir(pasta):
        return out
    try:
        arquivos = glob.glob(os.path.join(pasta, "bt_ev_*.txt"))
    except Exception:
        return out
    for a in arquivos:
        # v1.31 — FIX DO MAGIC 0: a linha do evento gravada pelo EA NÃO carimba
        # magic= (só tipo e simbolo), então o parser devolvia evento sem magic,
        # o conector assumia 0 e roteava pro token errado -> backend rejeitava
        # -> BabyMachine cega. O NOME do arquivo sempre teve a resposta:
        # bt_ev_<magic>.txt. Deriva daqui e injeta em cada evento deste arquivo.
        # Funciona pra TODOS os bots já instalados, sem reenviar nada.
        try:
            _m_arq = re.search(r"bt_ev_(\d+)\.txt$", os.path.basename(a))
            magic_arq = _m_arq.group(1) if _m_arq else None
        except Exception:
            magic_arq = None
        try:
            tam = os.path.getsize(a)
        except Exception:
            continue
        # v1.35 — BACKLOG NÃO É DADO FRESCO (regra (e) da v1.34 que faltava
        # aqui): arquivo visto pela PRIMEIRA vez nesta sessão e parado há >90s
        # é histórico (Conector reaberto / EA antigo) — drena a posição sem
        # emitir, senão o backlog inteiro vira flood de POSTs no 1º ciclo.
        if a not in pos_cache:
            try:
                if (time.time() - os.path.getmtime(a)) > 90:
                    pos_cache[a] = tam
                    continue
            except Exception:
                pass
        ini = pos_cache.get(a, 0)
        # arquivo encolheu (recriado / novo dia / limpeza) -> relê do começo
        if tam < ini:
            ini = 0
        if tam == ini:
            continue                      # nada novo neste arquivo
        try:
            with open(a, "rb") as f:
                f.seek(ini)
                bruto = f.read(tam - ini)
        except Exception:
            # o EA pode estar escrevendo neste instante (lock do Windows);
            # NÃO avança a posição — tenta de novo no próximo ciclo (1.5s).
            continue
        # só avança a posição depois de ler com sucesso — evento nunca se perde
        pos_cache[a] = tam
        # tolerante a encoding (FILE_ANSI é o esperado; nulls de UTF-16 caem fora)
        texto = bruto.replace(b"\x00", b"").decode("utf-8", errors="ignore")
        for linha in texto.splitlines():
            linha = linha.strip()
            if not linha:
                continue
            tipo, dados = parse_linha_log(linha)
            if tipo == "evento":
                # v1.31 — injeta o magic do nome do arquivo quando a linha não traz
                if magic_arq and not str(dados.get("magic") or "").strip():
                    dados["magic"] = magic_arq
                out.append(dados)
    return out


def magic_do_mq5(codigo):
    """Extrai o magic (int) do próprio código .mq5 gerado pela nuvem — a linha
    BOTTESTED_SNAPSHOT leva magic=<n> literal (injetado pelo backend) e o input
    é InpMagic = <n>. Usado pra mapear magic->token NA INSTALAÇÃO, sem depender
    do refresh da nuvem (v1.25). Retorna 0 se não achar."""
    try:
        m = re.search(r"BOTTESTED_SNAPSHOT\|magic=(\d+)", codigo or "")
        if not m:
            m = re.search(r"InpMagic\s*=\s*(\d+)", codigo or "")
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


# ── 3. Reportar pra nuvem ──────────────────────────────────────────
_CV_LEITOR = None
_CV_AVISOU = set()
_CV_CACHE = {}
_CV_CAND_ENVIOS = {}            # (pasta da barra, magic) -> nº de snapshots que já levaram os candidatos
_CV_CAND_MAX = 3                # hml10: candidatos vão nos 3 primeiros snapshots da barra (a API guarda 1x por barra)
_CV_HEARTBEAT_MAX_S = 90        # leitor do motor passa a cada 20 s; 90 s sem batimento = parado


def _cv_ler_json(cam):
    import json as _j
    try:
        with open(cam, encoding="utf-8") as f:
            return _j.load(f)
    except Exception:
        return None


def _cv_int(v):
    try:
        return int(float(v))
    except Exception:
        return None


def _cv_iso_idade(iso):
    from datetime import datetime as _d, timezone as _z
    try:
        t = _d.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=_z.utc)
        return (_d.now(_z.utc) - t).total_seconds()
    except Exception:
        return None


def _cv_barra_ea(dados):
    """(abertura_corretora_epoch, ohlc) da barra M15 FECHADA vista pelo EA
    (cvt = iTime(tf,1) na ordem MN1.W1.D1.H4.H1.M30.M15.M5.M1; c15m vem de
    CopyRates a partir do shift 0, mais antiga primeiro → fechada = penúltima)."""
    partes = str(dados.get("cvt") or "").split(".")
    ab = _cv_int(partes[6]) if len(partes) == 9 else None
    ohlc = None
    velas = [p.split(",") for p in str(dados.get("c15m") or "").split(";") if p.count(",") >= 3]
    if len(velas) >= 2:
        try:
            v = velas[-2]
            ohlc = {"o": float(v[0]), "h": float(v[1]), "l": float(v[2]), "c": float(v[3])}
        except Exception:
            ohlc = None
    return ab, ohlc


def _cv_epoch_corretora(txt):
    from datetime import datetime as _d, timezone as _z
    try:
        return int(_d.strptime(str(txt)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_z.utc).timestamp())
    except Exception:
        return None


def _cv_atestar(dados, bot_token=""):
    """hml8 — ponte do motor dos Ciclos. Lê o LEITOR DO MOTOR (BT_CV_ESPELHO =
    pasta de dados do bt_motor_leitura_hml: SAUDE.json + ATUAL.json + barras/),
    confere identidade (conta, símbolo, instalação MT5, barra e OHLC) e fuso
    (EA × motor), e só então assina com bt_conector_atestado v0.4. Nunca
    levanta: falha vira dados['cv_atestado_falha'] (motivo curto, sem segredo);
    a saúde do motor vai SEMPRE em dados['cv_motor'] (telemetria, não autoridade)."""
    global _CV_LEITOR
    import hashlib as _h
    dados.pop("cv_atestado", None)
    dados.pop("cv_atestado_falha", None)
    dados.pop("cv_motor", None)
    mot = {"versao_ponte_conector": "hml11"}
    dados["cv_motor"] = mot

    def falha(estado, motivo):
        mot["estado"] = estado
        mot["motivo"] = motivo
        dados["cv_atestado_falha"] = f"{estado}: {motivo}"

    base = os.environ.get("BT_CV_ESPELHO", "").strip()
    if not base:
        return falha("nao_configurado", "BT_CV_ESPELHO ausente no PC (pasta de dados do leitor do motor)")
    if not os.path.isdir(base):
        return falha("nao_configurado", "BT_CV_ESPELHO aponta para pasta inexistente")
    sau = _cv_ler_json(os.path.join(base, "SAUDE.json"))
    if not sau:
        return falha("processo_parado", "SAUDE.json ausente — leitor do motor nunca rodou nesta pasta")
    idade_hb = _cv_iso_idade(sau.get("agora_utc"))
    mot.update({"heartbeat_idade_s": None if idade_hb is None else int(idade_hb),
                "pid": sau.get("pid"), "leitor": sau.get("leitor"), "login": sau.get("login"),
                "servidor": sau.get("servidor"), "conta_demo": sau.get("conta_demo"),
                "ativo": sau.get("ativo"), "off_motor_s": sau.get("off_corretora_s"),
                "off_motor_fonte": sau.get("off_fonte"), "erro_ultimo": sau.get("erro_ultimo"),
                "hashes": {k: (v or "")[:16] for k, v in (sau.get("hashes") or {}).items()}})
    if idade_hb is None or idade_hb > _CV_HEARTBEAT_MAX_S:
        return falha("processo_parado", f"leitor do motor sem batimento há {mot['heartbeat_idade_s']}s")
    if sau.get("erro_ultimo"):
        return falha("motor_com_erro", str(sau.get("erro_ultimo"))[:160])

    simbolo = (dados.get("simbolo") or "").strip()
    magic = _cv_int(dados.get("magic")) or 0
    if not simbolo or magic <= 0:
        return falha("snapshot_invalido", f"snapshot sem simbolo/magic validos (simbolo={simbolo!r} magic={magic})")
    # identidade: conta, símbolo, instalação MT5
    conta_ea = _cv_int(dados.get("conta"))
    mot["conta_ea"] = conta_ea
    if sau.get("login") is None or conta_ea is None or int(sau["login"]) != conta_ea:
        return falha("identidade_divergente", f"conta do motor {sau.get('login')} ≠ conta do EA {conta_ea}")
    if not sau.get("conta_demo"):
        return falha("identidade_divergente", "leitor do motor não está em conta DEMO")
    if str(sau.get("ativo")) != simbolo:
        return falha("identidade_divergente", f"motor lê {sau.get('ativo')} e o EA é {simbolo}")
    try:
        pin = ler_mt5_pin()
    except Exception:
        pin = None
    dp = sau.get("data_path") or ""
    if pin and dp:
        mesmo = os.path.normcase(os.path.normpath(os.path.dirname(pin.rstrip("\\/")))) == \
            os.path.normcase(os.path.normpath(dp))
        mot["instalacao_confere"] = bool(mesmo)
        if not mesmo:
            return falha("identidade_divergente", "instalação MT5 do motor ≠ instalação fixada no conector")
    else:
        mot["instalacao_confere"] = None
    # fuso: EA (TimeCurrent − TimeGMT) é a referência; o motor confere pelo tick
    tsrv, tgmt = _cv_int(dados.get("tsrv")), _cv_int(dados.get("tgmt"))
    off_ea = int(round((tsrv - tgmt) / 60.0)) * 60 if (tsrv and tgmt) else None
    mot["off_ea_s"] = off_ea
    if off_ea is None:
        return falha("fuso_indisponivel", "EA sem tsrv/tgmt (EA < v7.80) — sem conversão corretora→UTC")
    if sau.get("off_corretora_s") is not None and int(sau["off_corretora_s"]) != off_ea:
        return falha("fuso_divergente", f"fuso EA {off_ea}s ≠ fuso medido pelo motor {sau['off_corretora_s']}s")
    # barra: a pasta publicada pelo motor tem que ser a barra M15 fechada do EA
    atual = _cv_ler_json(os.path.join(base, "ATUAL.json"))
    if not atual or not atual.get("pasta"):
        return falha("espelho_ausente", "ATUAL.json ausente — motor ainda não publicou barra")
    mot.update({"barra_motor_corretora": atual.get("barra_corretora"),
                "publicado_idade_s": (lambda x: None if x is None else int(x))(_cv_iso_idade(atual.get("publicado_utc"))),
                "ohlc_motor": atual.get("m15")})
    if atual.get("erro_motor"):
        return falha("motor_com_erro", f"motor não calculou a barra: {str(atual['erro_motor'])[:140]}")
    ab_ea, ohlc_ea = _cv_barra_ea(dados)
    ab_mot = _cv_epoch_corretora(atual.get("barra_corretora"))
    mot["barra_ea_corretora_epoch"] = ab_ea
    mot["barra_motor_corretora_epoch"] = ab_mot
    mot["ohlc_ea"] = ohlc_ea
    if ab_ea is None or ab_mot is None:
        return falha("barra_indisponivel", "barra M15 do EA ou do motor sem carimbo")
    if ab_mot < ab_ea:
        return falha("espelho_atrasado", f"motor na barra {atual.get('barra_corretora')} e o EA já fechou a seguinte (atraso {ab_ea - ab_mot}s)")
    if ab_mot > ab_ea:
        return falha("espelho_adiantado", f"motor {ab_mot - ab_ea}s à frente do EA (EA atrasado ou outra fonte)")
    om = atual.get("m15") or {}
    if ohlc_ea and om:
        try:
            pt = float(dados.get("pt") or 0)
        except Exception:
            pt = 0.0
        tol = 0.5 * pt if pt > 0 else abs(float(om.get("c") or 1.0)) * 1e-6
        mot["ohlc_tolerancia"] = tol
        confere = all(k in om and abs(float(om[k]) - float(ohlc_ea[k])) <= tol
                      for k in ("o", "h", "l", "c"))
        mot["ohlc_confere"] = bool(confere)
        if not confere:
            return falha("identidade_divergente", "OHLC da barra M15 do motor ≠ OHLC do EA (fonte diferente)")
    else:
        mot["ohlc_confere"] = None
    if not os.environ.get("BT_CV_SEGREDO", "").strip():
        return falha("segredo_ausente", "BT_CV_SEGREDO ausente no PC")
    if not bot_token:
        return falha("token_ausente", "snapshot sem bot_token")
    mdir = os.environ.get("BT_CV_MOTOR_DIR", "").strip()
    if mdir and mdir not in sys.path:
        sys.path.insert(0, mdir)
    pasta_barra = os.path.join(base, atual["pasta"])
    chave = (pasta_barra, magic, simbolo, off_ea, _h.sha256(bot_token.encode("utf-8")).hexdigest())
    try:
        if chave in _CV_CACHE:
            at, resumo = _CV_CACHE[chave]
            mot["cache"] = True
        else:
            if _CV_LEITOR is None:
                from bt_conector_atestado import LeitorConfiavel, VERSAO as _V
                _CV_LEITOR = LeitorConfiavel(base)
                mot["assinador"] = _V
            at, resumo = _CV_LEITOR.ler_e_assinar_motor(
                pasta_barra, simbolo, magic, simbolo=simbolo, bot_token=bot_token,
                off_corretora_s=off_ea, agora_utc=_d_agora_utc(), com_resumo=True)
            _CV_CACHE.clear()
            _CV_CACHE[chave] = (at, resumo)
            mot["cache"] = False
        # frescor no envio (o cache não pode reapresentar leitura vencida)
        idade = _cv_iso_idade(at.get("ts_barra_m15"))
        if idade is None or idade > 900:
            return falha("leitura_antiga", f"atestado da barra fechada há {None if idade is None else int(idade)}s")
        dados["cv_atestado"] = at
        mot.update({"estado": "ok", "motivo": "atestado assinado pelo motor nesta barra",
                    "leitura": {k: resumo.get(k) for k in ("topdown", "estado_unico", "classificacao",
                                                           "janela_10_15", "degrau_m15", "fase", "conclusao")},
                    "dirs": {k: (v or {}).get("dir") for k, v in (resumo.get("por_tf") or {}).items()},
                    "por_tf": resumo.get("por_tf")})
        # hml10 (C27R19) — candidatos M15/M30/H1 calculados pelo leitor (telemetria NÃO assinada).
        # Só vão junto de uma barra cuja identidade conferiu; nos 3 primeiros snapshots da barra.
        try:
            kc = (pasta_barra, magic)
            n_env = _CV_CAND_ENVIOS.get(kc, 0)
            if n_env < _CV_CAND_MAX:
                cand = _cv_ler_json(os.path.join(pasta_barra, "candidatos.json"))
                if cand:
                    mot["candidatos"] = cand
                    if len(_CV_CAND_ENVIOS) > 50:
                        _CV_CAND_ENVIOS.clear()
                    _CV_CAND_ENVIOS[kc] = n_env + 1
        except Exception as _e:
            mot["candidatos_erro"] = f"{type(_e).__name__}"
        # hml11 (C27R23) — ATESTADO DE CANDIDATOS (contrato r01v5): os candidatos CONFIRMADOS em tempo real e
        # ainda válidos viajam ASSINADOS (mesmo HMAC, mesmo vínculo de bot/símbolo/magic/barra), em todo
        # snapshot da barra. É outro atestado: o cv_atestado (r01v4) segue intacto. Só descreve; quem decide é a API.
        try:
            kc5 = (pasta_barra, magic, _h.sha256(bot_token.encode("utf-8")).hexdigest())
            at5 = _CV_CAND_AT.get(kc5)
            if at5 is None:
                cand5 = _cv_ler_json(os.path.join(pasta_barra, "candidatos.json")) or {}
                at5 = _cv_assinar_candidatos(at, cand5, resumo, off_ea)
                if len(_CV_CAND_AT) > 50:
                    _CV_CAND_AT.clear()
                _CV_CAND_AT[kc5] = at5
            if at5:
                dados["cv_atestado_cand"] = at5
        except Exception as _e:
            mot["candidatos_assinatura_erro"] = f"{type(_e).__name__}: {str(_e)[:120]}"
        dbg(f"cv_atestado: motor {at.get('versao_motor')} barra {at.get('ts_barra_m15')} "
            f"veredito={((at.get('cv1') or {}).get('veredito'))}")
    except Exception as e:
        motivo = f"{type(e).__name__}: {str(e)[:160]}"
        falha("assinatura_recusada", motivo)
        if type(e).__name__ not in _CV_AVISOU:
            _CV_AVISOU.add(type(e).__name__)
            dbg(f"cv_atestado: falhou ({motivo}) — snapshot sem atestado")


_CV_CAND_AT = {}


def _cv_utc(txt_corretora, off_s):
    from datetime import datetime as _d, timezone as _z, timedelta as _t
    t = _d.strptime(str(txt_corretora)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_z.utc) - _t(seconds=int(off_s))
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cv_assinar_candidatos(at, cand, resumo, off_s):
    """Monta e assina o atestado r01v5. Só entram candidatos da MESMA barra e do MESMO ativo do atestado
    do motor, com confirmação em tempo real (conf-rt-1). Números viajam como texto: a assinatura não
    pode depender de como cada lado escreve um decimal. Devolve None se não houver o que assinar."""
    import bt_cv_atestado as _cvat5
    if not isinstance(cand, dict) or cand.get("erro") or not isinstance(cand.get("confirmacao"), dict):
        return None
    if str(cand.get("ativo")) != str(at.get("simbolo")):
        return None
    if _cv_utc(cand.get("agora_corretora"), off_s) != str(at.get("ts_barra_m15")).replace("+00:00", "Z")[:19] + "Z":
        return None                                    # candidatos de outra barra: não assina
    por_tf = (resumo or {}).get("por_tf") or {}
    lista = []
    for it in cand.get("itens") or []:
        if it.get("estado") != "confirmado":
            continue
        lista.append({"uid": str(it.get("uid")), "card": str(it.get("card")), "tf": str(it.get("tf")),
                      "lado": int(it.get("lado")), "modo": str(it.get("modo")),
                      "sinal_abre_utc": _cv_utc(it.get("ts_sinal"), off_s), "sinal_fecha_utc": _cv_utc(it.get("ts_sinal_fecha"), off_s),
                      "confirmado_utc": _cv_utc(it.get("ts_confirmacao"), off_s), "vence_utc": _cv_utc(it.get("ts_vence"), off_s),
                      "preco_ref": "%.6f" % float(it.get("preco_ref")), "stop": "%.6f" % float(it.get("stop")),
                      "corte_do_ciclo_agora": 1 if it.get("corte_ciclo_contra_agora") else 0,
                      "dir_do_timeframe": (por_tf.get(str(it.get("tf"))) or {}).get("dir")})
    slot = (cand.get("confirmacao") or {}).get("slot_agora") or {}
    corpo = {k: at[k] for k in ("bot_token_hash", "versao_motor", "simbolo", "magic", "ts_barra_m15", "cv1", "cv2")}
    corpo.update({"contrato": "r01v5", "confirmacao": str((cand.get("confirmacao") or {}).get("contrato")),
                  "leitor": str(cand.get("leitor")), "cards": str((cand.get("codigo") or {}).get("cards")),
                  "blindagem_agora": 1 if (slot.get("B1") or slot.get("B5")) else 0,
                  "candidatos": lista})
    return _cvat5.assinar(corpo)


def _d_agora_utc():
    from datetime import datetime as _d, timezone as _z
    return _d.now(_z.utc)


def enviar_snapshot(bot_token, dados):
    """Manda snapshot pro /conector/snapshot. Read-only.
    hml8: antes do POST, anexa saúde do motor (cv_motor) e, se toda a cadeia
    conferir, o atestado assinado (cv_atestado)."""
    if requests is None:
        return False
    _cv_atestar(dados, bot_token)
    def _f(v, d=0.0):
        try:
            return float(v)
        except Exception:
            return d
    body = {
        "bot_token": bot_token,
        "conta_login": dados.get("conta", ""),
        "corretora": dados.get("corretora", ""),
        "simbolo": dados.get("simbolo", ""),
        "magic_number": int(_f(dados.get("magic", 0))),
        "equity": _f(dados.get("equity")),
        "balance": _f(dados.get("balance")),
        "margem_livre": _f(dados.get("margem_livre")),
        # v1.30 — FIX DA MENTIRA SISTEMATICA: se o EA nao mandou o campo
        # 'posicoes' (chave ausente, nao "0"), NAO afirmar 0 — mandar None pro
        # backend, que ja sabe tratar null como "sem leitura" e NAO dispara a
        # reconciliacao de orfas. Antes: campo ausente -> int(_f(None)) -> 0 ->
        # snapshot AFIRMAVA "zero posicoes" com posicao aberta -> reconciliacao
        # matava operacoes reais (incidente v6.91). So converte pra int quando
        # o EA REALMENTE mandou o valor.
        "posicoes_abertas": (int(_f(dados.get("posicoes")))
                             if dados.get("posicoes") not in (None, "") else None),
        "lucro_flutuante": _f(dados.get("lucro")),
        "drawdown_atual": _f(dados.get("dd")),
        "direcao_d1": dados.get("direcao", ""),
        "padrao_ativo": dados.get("padrao", ""),
        "detalhe": dict(dados, conector_versao=f"{APP_NOME} {APP_VERSAO}"),
    }
    try:
        r = requests.post(f"{API_BASE}/conector/snapshot", json=body, timeout=20)
        if r.status_code == 200:
            dbg(f"snapshot -> 200 OK (simbolo={body['simbolo']} equity={body['equity']})")
        else:
            dbg(f"snapshot -> {r.status_code} | resposta: {r.text[:300]}")
        return r.status_code == 200
    except Exception as e:
        dbg(f"snapshot ERRO de rede: {e}")
        return False


def enviar_evento(bot_token, tipo, detalhe):
    """Manda evento (trade aberto/fechado/etc) pro /conector/evento."""
    if requests is None:
        return False
    try:
        r = requests.post(f"{API_BASE}/conector/evento",
                          json={"bot_token": bot_token, "tipo": tipo,
                                "detalhe": detalhe}, timeout=20)
        if r.status_code != 200:
            dbg(f"evento -> {r.status_code} | resposta: {r.text[:300]}")
        else:
            dbg(f"evento -> 200 OK (tipo={tipo})")
        return r.status_code == 200
    except Exception as e:
        dbg(f"evento ERRO de rede: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#  4. VALIDAÇÃO DO .mq5 (compilação) — ponte "Enviar pro MT5"
#  Quando o usuário aperta "Enviar pro MT5" na plataforma, a nuvem gera
#  o .mq5 e o deixa pendente. O conector pega, instala, e COMPILA usando
#  o metaeditor64.exe /compile — que NÃO abre o terminal de trading, roda
#  de lado, sem tocar na operação. Compilou limpo (gerou .ex5) = aprovado.
# ═══════════════════════════════════════════════════════════════════
_CONFIG_PATH = os.path.join(os.path.expanduser("~"), "BotTested_Conector_HOMOLOG_config.json")


def _ler_config():
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_config(novos):
    try:
        atual = _ler_config()
        atual.update(novos)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(atual, f)
    except Exception:
        pass


def achar_metaeditor(terminais=None):
    """Descobre o metaeditor64.exe SOZINHO, sem perguntar nada ao usuário.
    Camadas, da mais barata pra mais cara — para na primeira que achar:
      1) cache local (achou antes → nunca mais procura)
      2) origin.txt de cada instalação (aponta pra pasta de programas)
      3) locais padrão (Program Files, Program Files (x86), pasta do usuário)
    Retorna o caminho do .exe, ou None (aí o conector cai pra checagem leve)."""
    # 1) cache
    p = _ler_config().get("metaeditor")
    if p and os.path.isfile(p):
        return p

    # 2) origin.txt das instalações (o núcleo já usa esse arquivo p/ o rótulo)
    if terminais is None:
        try:
            terminais = achar_pastas_mt5()
        except Exception:
            terminais = []
    for inst in (terminais or []):
        tdir = inst.get("terminal", "")
        try:
            org = os.path.join(tdir, "origin.txt")
            if os.path.isfile(org):
                with open(org, "r", encoding="utf-16", errors="ignore") as f:
                    prog = f.read().strip()
                if prog:
                    cand = os.path.join(prog, "metaeditor64.exe")
                    if os.path.isfile(cand):
                        _salvar_config({"metaeditor": cand})
                        dbg(f"metaeditor achado via origin.txt: {cand}")
                        return cand
        except Exception:
            pass

    # 3) locais padrão de instalação (glob de 1-2 níveis, rápido)
    bases = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        v = os.environ.get(env)
        if v and v not in bases:
            bases.append(v)
    bases.append(os.path.expanduser("~"))       # portables costumam ficar aqui
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        for padrao in (os.path.join(base, "*", "metaeditor64.exe"),
                       os.path.join(base, "*", "*", "metaeditor64.exe")):
            try:
                achados = glob.glob(padrao)
            except Exception:
                achados = []
            for cand in achados:
                if os.path.isfile(cand):
                    _salvar_config({"metaeditor": cand})
                    dbg(f"metaeditor achado em local padrão: {cand}")
                    return cand

    dbg("metaeditor NÃO encontrado (cairá p/ checagem de sintaxe)")
    return None


def validar_sintaxe_mq5(conteudo):
    """Checagem leve, usada só quando NÃO há compilador na máquina. Não
    garante que compila — pega erros grosseiros (chaves/parênteses
    desbalanceados, falta do esqueleto de EA). Retorna (ok, motivo)."""
    if not conteudo or len(conteudo.strip()) < 30:
        return False, "código vazio ou muito curto"
    if conteudo.count("{") != conteudo.count("}"):
        return False, "chaves { } desbalanceadas"
    if conteudo.count("(") != conteudo.count(")"):
        return False, "parênteses ( ) desbalanceados"
    if "OnTick" not in conteudo:
        return False, "falta a função OnTick (esqueleto de EA)"
    return True, "sintaxe básica ok"


def compilar_mq5(caminho_mq5, metaeditor=None):
    """Compila um .mq5 com o metaeditor64.exe /compile (headless — NÃO abre
    o terminal de trading). Critério de sucesso robusto: se gerou o .ex5,
    compilou. Retorna (ok, log). ok=None se não há compilador."""
    if metaeditor is None:
        metaeditor = achar_metaeditor()
    if not metaeditor or not os.path.isfile(metaeditor):
        return None, "metaeditor_nao_encontrado"
    import subprocess
    base = caminho_mq5[:-4] if caminho_mq5.lower().endswith(".mq5") else caminho_mq5
    ex5 = base + ".ex5"
    log_path = base + "_compile.log"
    # remove .ex5 antigo pra não dar falso positivo de build anterior
    try:
        if os.path.isfile(ex5):
            os.remove(ex5)
    except Exception:
        pass
    try:
        subprocess.run(
            [metaeditor, f"/compile:{caminho_mq5}", f"/log:{log_path}"],
            capture_output=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        dbg(f"compilar_mq5 erro ao executar: {e}")
        return None, f"erro_exec: {e}"
    # lê o log de compilação (UTF-16 na maioria das builds) p/ devolver detalhe
    conteudo = ""
    for enc in ("utf-16", "utf-16-le", "utf-8"):
        try:
            with open(log_path, "r", encoding=enc, errors="ignore") as f:
                conteudo = f.read()
            if conteudo:
                break
        except Exception:
            continue
    ok = os.path.isfile(ex5)   # gerou o .ex5 => compilou com sucesso
    dbg(f"compilar_mq5: ok={ok} ex5={os.path.isfile(ex5)}")
    return ok, (conteudo.strip() or ("compilado" if ok else "falhou (sem log)"))


# ── Ponte com a nuvem: pega bot pendente, valida, reporta veredito ─────
def buscar_bot_pendente(bot_token):
    """Pergunta à nuvem se há um .mq5 pendente de validação pra este token."""
    if requests is None:
        return None
    try:
        r = requests.post(f"{API_BASE}/mt5/pendente/checar",
                          json={"bot_token": bot_token}, timeout=20)
        if r.status_code != 200:
            return None
        d = r.json()
        if d.get("pendente") and d.get("codigo"):
            return d
        return None
    except Exception as e:
        dbg(f"buscar_bot_pendente erro: {e}")
        return None


def reportar_veredito(bot_token, job_id, aprovado, log):
    """Manda o veredito da validação (aprovado/reprovado + log) pra nuvem."""
    if requests is None:
        return False
    try:
        r = requests.post(f"{API_BASE}/mt5/veredito", json={
            "bot_token": bot_token, "job_id": job_id,
            "aprovado": bool(aprovado), "log": (log or "")[:4000],
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
        return r.status_code == 200
    except Exception as e:
        dbg(f"reportar_veredito erro: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#  HOMOLOG hml2/hml4 — CONFERÊNCIA DO MT5 DEMO + COMPILAÇÃO ESTRITA
#  Substitui o validar_pendente da v1.35 nesta cópia:
#   • sem conferência DEMO confirmada para a instalação fixada → o job NEM é
#     buscado (fica pendente na nuvem) — BT-HML-D0x no log/status;
#   • pre_validado é IGNORADO (nunca antecipa aprovação);
#   • sem MetaEditor da instalação DEMO → veredito FALSO "INDISPONIVEL";
#   • aprovado SOMENTE com: .mq5 em disco idêntico ao do job + compile.log NOVO
#     com linha de resultado "0 errors" citando o .mq5 do job + .ex5 NOVO
#     (criado depois do início da compilação). Nada de checagem de sintaxe.
# ═══════════════════════════════════════════════════════════════════
import hashlib as _hl

_DEMO_CONF = {"mql5": None, "login": None, "servidor": None}
# hml4: a confirmação visual fica salva no config HOMOLOG (instalação+conta).
# Assim o conector aberto SOZINHO pelo Enviar (bottested://) já nasce apto;
# a cada job o diário é relido e conta/servidor precisam continuar iguais.
try:
    _dc = _ler_config().get("demo_conf") or {}
    if _dc.get("mql5") and _dc.get("servidor"):
        _DEMO_CONF.update({k: _dc.get(k) for k in ("mql5", "login", "servidor")})
except Exception:
    pass
_RE_AUTH = re.compile(r"'(\d+)'\s*:\s*authorized on\s+([^\s,]+)", re.I)
_RE_ALGO = re.compile(r"(?:automated|algo(?:rithmic)?)\s+trading\s+is\s+(enabled|disabled)", re.I)
_RE_RES = re.compile(r"(\d+)\s+error(?:s|\(s\))?\s*,\s*(\d+)\s+warning", re.I)


def _ler_texto_mt5(caminho):
    """Arquivos do MT5 vêm em UTF-16 (com BOM) na maioria das builds; alguns
    em UTF-8. Decide pelo conteúdo, não por tentativa-e-erro."""
    with open(caminho, "rb") as f:
        b = f.read()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16", errors="ignore")
    if b[:3] == b"\xef\xbb\xbf":
        return b[3:].decode("utf-8", errors="ignore")
    if len(b) > 1 and b.count(b"\x00") > len(b) // 4:
        return b.decode("utf-16-le", errors="ignore")
    return b.decode("utf-8", errors="ignore")


def _servidor_demo(servidor):
    s = (servidor or "").lower()
    return ("demo" in s) and not any(k in s for k in ("live", "real"))


def conferir_demo(mql5_dir):
    """Identifica a instalação fixada e a conta que ela autorizou por último.
    Fonte principal: diário do terminal (<terminal>\\logs\\AAAAMMDD.log, linha
    "'<login>': authorized on <servidor>"). Reserva: config\\common.ini.
    AutoTrading: última linha "automated/algo trading is enabled|disabled".
    Retorna dict — nunca decide sozinho: a GUI exige a conferência visual."""
    terminal = os.path.dirname(os.path.normpath(mql5_dir or ""))
    info = {"mql5": mql5_dir, "terminal": terminal, "programa": "", "login": "",
            "servidor": "", "fonte": "nenhuma", "autotrading": "desconhecido",
            "demo": False}
    try:
        org = os.path.join(terminal, "origin.txt")
        if os.path.isfile(org):
            info["programa"] = _ler_texto_mt5(org).strip()
    except Exception:
        pass
    try:
        logs = sorted(glob.glob(os.path.join(terminal, "logs", "*.log")))
        for arq in logs:
            for linha in _ler_texto_mt5(arq).splitlines():
                m = _RE_AUTH.search(linha)
                if m:
                    info["login"], info["servidor"] = m.group(1), m.group(2)
                    info["fonte"] = "diario:" + os.path.basename(arq)
                a = _RE_ALGO.search(linha)
                if a:
                    info["autotrading"] = "on" if a.group(1).lower() == "enabled" else "off"
    except Exception as e:
        dbg(f"conferir_demo diario: {e}")
    if not info["servidor"]:
        try:
            ini = os.path.join(terminal, "config", "common.ini")
            if os.path.isfile(ini):
                sec = ""
                for linha in _ler_texto_mt5(ini).splitlines():
                    t = linha.strip()
                    if t.startswith("["):
                        sec = t.lower()
                    elif sec == "[common]" and "=" in t:
                        k, v = t.split("=", 1)
                        if k.strip().lower() == "login":
                            info["login"] = v.strip()
                        elif k.strip().lower() == "server":
                            info["servidor"] = v.strip()
                if info["servidor"]:
                    info["fonte"] = "common.ini"
        except Exception as e:
            dbg(f"conferir_demo ini: {e}")
    info["demo"] = _servidor_demo(info["servidor"])
    return info


def confirmar_demo(mql5_dir, info):
    """Chamado pela GUI SÓ depois do 'Sim' na conferência visual. Vale para
    esta sessão (não é salvo em disco) e só para esta instalação/conta."""
    _DEMO_CONF.update({"mql5": mql5_dir, "login": info.get("login"),
                       "servidor": info.get("servidor")})
    _salvar_config({"demo_conf": dict(_DEMO_CONF)})
    dbg(f"HOMOLOG: DEMO confirmada | servidor={info.get('servidor')} "
        f"autotrading={info.get('autotrading')} terminal={info.get('terminal')}")


def resetar_demo():
    _DEMO_CONF.update({"mql5": None, "login": None, "servidor": None})
    try:
        _salvar_config({"demo_conf": {}})
    except Exception:
        pass


def gate_demo(mql5_dir):
    """(ok, motivo). Refaz a leitura a cada job: trocou conta/servidor, ligou o
    AutoTrading ou mudou a instalação desde a confirmação → bloqueia."""
    if not mql5_dir:
        return False, "BT-HML-D01 nenhum MT5 fixado"
    if _DEMO_CONF.get("mql5") != mql5_dir:
        return False, "BT-HML-D02 conferência DEMO pendente (botão 'Conferir MT5 DEMO')"
    info = conferir_demo(mql5_dir)
    if not info["demo"]:
        return False, f"BT-HML-D03 servidor não é DEMO ({info['servidor'] or '?'})"
    if (info["login"], info["servidor"]) != (_DEMO_CONF.get("login"), _DEMO_CONF.get("servidor")):
        resetar_demo()
        return False, "BT-HML-D04 conta mudou desde a conferência — confira de novo"
    if info["autotrading"] == "on":
        # hml3 (decisão do dono 29/set): conta DEMO com bots rodando — Algo Trading
        # LIGADO é aceito; só registra. A trava continua sendo: servidor DEMO +
        # mesma conta confirmada visualmente.
        dbg("HOMOLOG: aviso — AutoTrading LIGADO na DEMO (aceito por decisão do dono)")
    return True, "ok"


def achar_metaeditor_hml(mql5_dir):
    """Só o MetaEditor da PRÓPRIA instalação DEMO (origin.txt dela), ou um
    caminho posto à mão em 'metaeditor_hml' no config HOMOLOG. Nunca varre
    Program Files (poderia pegar o MetaEditor do MT5 real)."""
    p = (_ler_config().get("metaeditor_hml") or "").strip()
    if p and os.path.isfile(p):
        return p
    try:
        org = os.path.join(os.path.dirname(os.path.normpath(mql5_dir)), "origin.txt")
        if os.path.isfile(org):
            prog = _ler_texto_mt5(org).strip()
            cand = os.path.join(prog, "metaeditor64.exe")
            if prog and os.path.isfile(cand):
                return cand
    except Exception:
        pass
    return None


def _sha256_arquivo(caminho):
    h = _hl.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def compilar_estrito(caminho_mq5, codigo, metaeditor, mql5_dir, _executar=None):
    """Retorna (status, log) com status em aprovado | reprovado | indisponivel.
    _executar: só para teste (substitui o subprocess)."""
    if not metaeditor or not os.path.isfile(metaeditor):
        return "indisponivel", "BT-HML-M01 MetaEditor da instalação DEMO não encontrado"
    try:
        # hml5: no Windows o instalar_ea grava em modo texto (\n vira \r\n) —
        # compara o CONTEÚDO com fim de linha normalizado, não os bytes crus.
        with open(caminho_mq5, "rb") as _f:
            _disco = _f.read().replace(b"\r\n", b"\n")
        _job = codigo.replace("\r\n", "\n").encode("utf-8")
        if _hl.sha256(_disco).hexdigest() != _hl.sha256(_job).hexdigest():
            return "reprovado", "BT-HML-C03 .mq5 em disco difere do código do job"
    except Exception as e:
        return "reprovado", f"BT-HML-C03 .mq5 ilegível: {e}"
    base = caminho_mq5[:-4] if caminho_mq5.lower().endswith(".mq5") else caminho_mq5
    ex5, log_path = base + ".ex5", base + "_compile.log"
    for velho in (ex5, log_path):          # nada de sobra de build anterior
        try:
            if os.path.isfile(velho):
                os.remove(velho)
        except Exception as e:
            return "indisponivel", f"BT-HML-M03 não consegui limpar {os.path.basename(velho)}: {e}"
    t0 = time.time()
    cmd = [metaeditor, f"/compile:{caminho_mq5}", f"/inc:{mql5_dir}", f"/log:{log_path}"]
    try:
        if _executar:
            _executar(cmd)
        else:
            import subprocess
            subprocess.run(cmd, capture_output=True, timeout=180,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return "indisponivel", f"BT-HML-M02 MetaEditor não executou: {e}"
    if not os.path.isfile(log_path):
        return "reprovado", "BT-HML-C01 compile.log não foi gerado"
    log = _ler_texto_mt5(log_path).strip()
    res = _RE_RES.findall(log)
    if not res:
        return "reprovado", "BT-HML-C01 compile.log sem linha de resultado\n" + log[-1500:]
    erros = int(res[-1][0])
    if erros != 0:
        return "reprovado", f"BT-HML-C02 {erros} error(s)\n" + log[-2500:]
    if os.path.basename(caminho_mq5).lower() not in log.lower():
        return "reprovado", "BT-HML-C05 compile.log não cita o .mq5 do job\n" + log[-1500:]
    if not os.path.isfile(ex5) or os.path.getmtime(ex5) < t0 - 2:
        return "reprovado", "BT-HML-C04 .ex5 novo não foi gerado\n" + log[-1500:]
    dbg(f"HOMOLOG: compilado ex5_sha256={_sha256_arquivo(ex5)} "
        f"mq5_sha256={_sha256_arquivo(caminho_mq5)} log={os.path.basename(log_path)}")
    return "aprovado", log[-3500:]


def validar_pendente(bot_token, mql5_dir, ao_iniciar=None, ao_terminar=None,
                     ao_instalar=None, _executar=None):
    """HOMOLOG: gate DEMO → pega o job → instala → compila de verdade →
    veredito. Retorna (houve_pendente, aprovado, msg)."""
    ok_gate, motivo_gate = gate_demo(mql5_dir)
    if not ok_gate:
        dbg(f"HOMOLOG: job NÃO buscado — {motivo_gate}")
        return False, None, motivo_gate
    job = buscar_bot_pendente(bot_token)
    if not job:
        return False, None, "sem pendente"
    if ao_iniciar:
        try: ao_iniciar()
        except Exception: pass
    try:
        codigo = job.get("codigo", "")
        nome = job.get("filename") or "BotTested_EA.mq5"
        job_id = job.get("job_id", "")
        dbg(f"HOMOLOG validar_pendente: job_id={job_id} nome={nome} "
            f"pre_validado={bool(job.get('pre_validado'))} (ignorado: compile real sempre)")
        ok_inst, destino = instalar_ea(codigo, nome, mql5_dir)
        if not ok_inst:
            reportar_veredito(bot_token, job_id, False, f"BT-HML-I01 falha ao instalar: {destino}")
            return True, False, "BT-HML-I01 falha ao instalar o arquivo"
        if ao_instalar:
            try:
                _mg = magic_do_mq5(codigo)
                if _mg:
                    ao_instalar(_mg)
            except Exception:
                pass
        status, log = compilar_estrito(destino, codigo, achar_metaeditor_hml(mql5_dir),
                                       mql5_dir, _executar=_executar)
        if status == "indisponivel":
            log = "INDISPONIVEL (não é aprovação): " + log
        aprovado = (status == "aprovado")
        reportar_veredito(bot_token, job_id, aprovado, log)
        dbg(f"HOMOLOG: job={job_id} status={status}")
        return True, aprovado, f"{status}: {log.splitlines()[0][:100] if log else ''}"
    finally:
        if ao_terminar:
            try: ao_terminar()
            except Exception: pass


# ── H16 (hml9, C27R16) — CANAL DE COMANDO nuvem → conector → EA (SOMENTE HOMOLOG/DEMO) ──
# O conector v1.35 nunca teve esta perna (a API diz: "o canal de comando nunca integrou").
# Sem ela, uma decisão autorizada vira comando 'pendente' e morre na fila.
#
# O conector NÃO decide nada: só transporta o comando que a API já criou pela RPC
# r01_claim_e_comando (decisão dos Ciclos emitida e consumida uma única vez).
#   1. POST /mt5/comando/pendente/checar   (claim atômico na nuvem: 'entregue')
#   2. confere: DEMO conferida nesta sessão, tipo conhecido, validade, números
#   3. grava <MQL5>/Files/bt_cmd_<magic>.txt   ("id|tipo|json")
#   4. o EA (BTLerComando) consome, chama OrderSend e grava bt_ok_<magic>.txt
#   5. POST /mt5/comando/confirmar com ticket / preço / retcode, ou o erro
# Nunca reentrega: cada id é entregue no máximo uma vez por instalação (registro em disco).
# Qualquer dúvida = falha confirmada com o motivo; nenhuma ordem é reenviada.
CMD_TIPOS = ("buy", "sell", "close", "close_all", "mover_sl", "mover_tp")
CMD_ESPERA_CONSUMO_S = 20      # EA lê no tick; sem consumo neste prazo o arquivo é retirado
CMD_ESPERA_RESPOSTA_S = 45     # depois de consumido, prazo para o bt_ok aparecer
CMD_RETCODES_OK = (10008, 10009)   # TRADE_RETCODE_PLACED / TRADE_RETCODE_DONE
_CMD_ESTADO = {}               # magic -> {"cmd":…, "fase": "entregue|consumido", "t0":…}
_CMD_LOCK = threading.Lock()
_CMD_GATE = {}                 # conferência DEMO em cache curto (20 s) só para decidir se BUSCA comando


def _cmd_arq(mql5_dir, prefixo, magic):
    return os.path.join(mql5_dir, "Files", f"{prefixo}_{int(magic)}.txt")


def _cmd_registro(mql5_dir):
    return os.path.join(mql5_dir, "Files", "bt_hml_comandos_entregues.json")


def _cmd_ja_entregue(mql5_dir, cmd_id):
    try:
        with open(_cmd_registro(mql5_dir), encoding="utf-8") as f:
            return str(cmd_id) in (json.load(f) or {})
    except Exception:
        return False


def _cmd_registrar(mql5_dir, cmd_id, magic, tipo):
    cam = _cmd_registro(mql5_dir)
    try:
        with open(cam, encoding="utf-8") as f:
            reg = json.load(f) or {}
    except Exception:
        reg = {}
    reg[str(cmd_id)] = {"magic": int(magic), "tipo": tipo, "em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if len(reg) > 500:
        for k in sorted(reg, key=lambda x: reg[x].get("em") or "")[:len(reg) - 500]:
            reg.pop(k, None)
    tmp = cam + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f)
    os.replace(tmp, cam)


def cmd_checar(bot_token):
    """Comando pendente deste bot (ou None). O claim é da nuvem: quem recebe é dono da entrega."""
    if requests is None:
        return None
    r = requests.post(f"{API_BASE}/mt5/comando/pendente/checar", json={"bot_token": bot_token}, timeout=10)
    if r.status_code != 200:
        dbg(f"cmd_checar HTTP {r.status_code}")
        return None
    return (r.json() or {}).get("comando")


def cmd_confirmar(bot_token, cmd_id, sucesso, resultado):
    if requests is None:
        return False
    try:
        r = requests.post(f"{API_BASE}/mt5/comando/confirmar", timeout=10,
                          json={"comando_id": int(cmd_id), "sucesso": bool(sucesso),
                                "resultado": resultado or {}, "bot_token": bot_token})
        dbg(f"cmd_confirmar id={cmd_id} sucesso={bool(sucesso)} HTTP {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        dbg(f"cmd_confirmar erro: {e}")
        return False


def _cmd_expirado(cmd, agora=None):
    exp = cmd.get("expira_em")
    if not exp:
        return False
    try:
        t = datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (agora or datetime.datetime.now(datetime.timezone.utc)) >= t
    except Exception:
        return True                      # validade ilegível = não entrega


def _cmd_linha(cmd):
    """(linha "id|tipo|json", None) ou (None, motivo). Só números limpos chegam ao EA —
    o extrator do EA é mínimo; uid/decisão ficam na nuvem."""
    tipo = str(cmd.get("tipo") or "").lower()
    if tipo not in CMD_TIPOS:
        return None, f"tipo_desconhecido({tipo})"
    try:
        cid = int(cmd.get("id"))
    except Exception:
        return None, "id_invalido"
    if cid <= 0:
        return None, "id_invalido"
    p = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    limpo = {}
    for k in ("lote", "sl", "tp", "ticket"):
        if p.get(k) is None:
            continue
        try:
            v = float(p[k])
        except Exception:
            return None, f"parametro_invalido({k})"
        if v != v or v in (float("inf"), float("-inf")) or v < 0:
            return None, f"parametro_invalido({k})"
        limpo[k] = int(v) if k == "ticket" else v
    if tipo in ("buy", "sell"):
        if not (0 < float(limpo.get("lote") or 0) <= 100):
            return None, "lote_invalido"
        if not (p.get("decisao") or {}).get("id") or not p.get("uid"):
            return None, "abertura_sem_decisao_dos_ciclos"      # só a RPC cria abertura
        _ver = ((p.get("decisao") or {}).get("veredito") or {})
        if _ver.get("contrato") == "r01v5":                     # hml11: abertura por candidato assinado
            _c = _ver.get("candidato") or {}
            if not _c.get("uid") or not _c.get("card") or _c.get("tf") not in ("M15", "M30", "H1"):
                return None, "abertura_r01v5_sem_candidato"
            if (1 if tipo == "buy" else -1) != _c.get("lado"):
                return None, "abertura_r01v5_lado_diferente_do_candidato"
            if not (float(limpo.get("sl") or 0) > 0):
                return None, "abertura_r01v5_sem_stop"          # o stop do candidato é obrigatório
            try:
                if abs(float(limpo["sl"]) - float(_c.get("stop"))) > 1e-6:
                    return None, "abertura_r01v5_stop_diferente_do_assinado"
            except Exception:
                return None, "abertura_r01v5_stop_ilegivel"
    return f"{cid}|{tipo}|{json.dumps(limpo, separators=(',', ':'))}", None


def _cmd_ler_ok(mql5_dir, magic, cmd_id):
    """None enquanto não há resposta DESTE comando; senão (sucesso, resultado)."""
    arq = _cmd_arq(mql5_dir, "bt_ok", magic)
    try:
        with open(arq, encoding="latin-1") as f:
            linha = f.read().strip().splitlines()[0]
    except Exception:
        return None
    partes = linha.split("|", 2)
    if len(partes) < 2 or partes[0].strip() != str(int(cmd_id)):
        return None                       # resposta de outro comando (antiga)
    extra = partes[2] if len(partes) > 2 else ""
    campos = dict(x.split("=", 1) for x in extra.split(";") if "=" in x)
    res = {"bruto": extra[:200]}
    try:
        rc = int(campos.get("retcode")) if campos.get("retcode") not in (None, "") else None
    except Exception:
        rc = None
    res["retcode"] = rc
    ok_ea = partes[1].strip().lower() == "ok"
    if "ticket" in campos:
        try:
            res["ticket"] = int(campos["ticket"])
        except Exception:
            pass
    if "preco" in campos:
        try:
            res["preco_real"] = float(campos["preco"])
        except Exception:
            pass
    if "fechados" in campos:
        res["fechados"] = campos["fechados"]
    sucesso = ok_ea and (rc is None or rc in CMD_RETCODES_OK)
    if ok_ea and rc is not None and rc not in CMD_RETCODES_OK:
        sucesso = False
    if not sucesso:
        res["erro"] = (f"MT5 retcode {rc}" if rc is not None else (extra or "EA respondeu erro"))[:200]
    try:
        os.remove(arq)
    except Exception:
        pass
    return sucesso, res


def cmd_passo(bot_token, magic, mql5_dir, agora=None):
    """Um passo da máquina de estados do comando deste bot. Devolve um texto curto
    para a linha de status (ou None). Nunca levanta."""
    agora = agora if agora is not None else time.time()
    try:
        with _CMD_LOCK:
            est = _CMD_ESTADO.get(magic)
        if est is None:
            if agora - _CMD_GATE.get("t", 0) > 20 or _CMD_GATE.get("dir") != mql5_dir:
                _CMD_GATE.update({"t": agora, "dir": mql5_dir, "ok": gate_demo(mql5_dir)[0]})
            if not _CMD_GATE.get("ok"):
                return None               # sem DEMO conferida não se busca comando (fica na fila até expirar)
            cmd = cmd_checar(bot_token)
            if not cmd:
                return None
            cid, tipo = cmd.get("id"), str(cmd.get("tipo") or "").lower()
            linha, falha = _cmd_linha(cmd)
            if not falha and _cmd_expirado(cmd):
                falha = "comando_expirado_antes_da_entrega"
            if not falha and _cmd_ja_entregue(mql5_dir, cid):
                falha = "comando_ja_entregue_nesta_instalacao(nao_reentrega)"
            if not falha:
                ok_demo, mot = gate_demo(mql5_dir)
                if not ok_demo:
                    falha = f"demo_nao_conferida({mot})"
            if falha:
                dbg(f"HOMOLOG comando {cid} ({tipo}) NAO entregue: {falha}")
                cmd_confirmar(bot_token, cid, False, {"erro": falha, "etapa": "conector"})
                return f"⛔ comando {cid} não entregue: {falha}"
            try:
                os.remove(_cmd_arq(mql5_dir, "bt_ok", magic))      # resposta velha não confunde
            except Exception:
                pass
            _cmd_registrar(mql5_dir, cid, magic, tipo)             # registra ANTES de gravar: nunca reentrega
            arq = _cmd_arq(mql5_dir, "bt_cmd", magic)
            tmp = arq + ".tmp"
            with open(tmp, "w", encoding="ascii", newline="") as f:
                f.write(linha + "\n")
            os.replace(tmp, arq)
            with _CMD_LOCK:
                _CMD_ESTADO[magic] = {"cmd": cmd, "fase": "entregue", "t0": agora, "tok": bot_token}
            dbg(f"HOMOLOG comando {cid} ({tipo}) gravado para o EA (magic {magic})")
            return f"📨 comando {cid} ({tipo}) entregue ao EA"
        cid = est["cmd"].get("id")
        r = _cmd_ler_ok(mql5_dir, magic, cid)
        if r is not None:
            sucesso, res = r
            cmd_confirmar(est["tok"], cid, sucesso, res)
            with _CMD_LOCK:
                _CMD_ESTADO.pop(magic, None)
            dbg(f"HOMOLOG comando {cid} resposta do EA: sucesso={sucesso} retcode={res.get('retcode')} "
                f"ticket={res.get('ticket')}")
            return (f"✅ comando {cid} executado (ticket {res.get('ticket')})" if sucesso
                    else f"✖ comando {cid} recusado pelo MT5: {res.get('erro')}")
        arq = _cmd_arq(mql5_dir, "bt_cmd", magic)
        if est["fase"] == "entregue":
            if not os.path.exists(arq):
                est["fase"] = "consumido"; est["t0"] = agora       # EA pegou; aguarda bt_ok
                return None
            if agora - est["t0"] > CMD_ESPERA_CONSUMO_S:
                try:
                    os.remove(arq)
                except Exception:
                    return None                                    # EA abrindo o arquivo agora: espera
                r = _cmd_ler_ok(mql5_dir, magic, cid)              # corrida: consumiu no último instante?
                if r is None and not os.path.exists(arq):
                    cmd_confirmar(est["tok"], cid, False,
                                  {"erro": f"ea_nao_consumiu_em_{CMD_ESPERA_CONSUMO_S}s(arquivo retirado; nenhuma ordem enviada)",
                                   "etapa": "ea"})
                    with _CMD_LOCK:
                        _CMD_ESTADO.pop(magic, None)
                    return f"✖ comando {cid}: EA não consumiu (retirado)"
                if r is not None:
                    cmd_confirmar(est["tok"], cid, r[0], r[1])
                    with _CMD_LOCK:
                        _CMD_ESTADO.pop(magic, None)
            return None
        if agora - est["t0"] > CMD_ESPERA_RESPOSTA_S:
            cmd_confirmar(est["tok"], cid, False,
                          {"erro": "ea_consumiu_e_nao_respondeu(estado da ordem DESCONHECIDO — conferir posições no MT5)",
                           "etapa": "ea"})
            with _CMD_LOCK:
                _CMD_ESTADO.pop(magic, None)
            return f"⚠ comando {cid}: EA consumiu e não respondeu — confira o MT5"
        return None
    except Exception as e:
        dbg(f"cmd_passo erro (magic {magic}): {e}")
        return None


def checar_subir_conector(bot_token):
    """Pergunta à nuvem se a plataforma pediu pra trazer o conector pra frente
    (usuário apertou 'Entendi' na guia, ou ✅ com guia suprimida). One-shot: o
    backend limpa o sinal ao ler. Retorna True uma única vez por pedido."""
    if requests is None:
        return False
    try:
        r = requests.post(f"{API_BASE}/mt5/subir-conector/checar",
                          json={"bot_token": (bot_token or "").strip()}, timeout=8)
        if r.status_code == 200:
            return bool(r.json().get("subir"))
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════
#  5. PROTOCOLO bottested:// — deixa a PLATAFORMA abrir o conector
#  Na primeira execução, o conector registra o protocolo no Windows
#  (HKCU, sem precisar de admin). Aí o navegador consegue abrir o app
#  via link bottested://validar — usado pelo botão "Enviar pro MT5".
# ═══════════════════════════════════════════════════════════════════
def registrar_autostart():
    """v1.30 — AUTOSTART OBRIGATORIO E SILENCIOSO. Registra o conector pra subir
    junto com o Windows (HKCU\\...\\Run). Sem checkbox: instalou -> funciona pra
    sempre (decisao do dono; checkbox e superficie de falha). CHAMADO A CADA
    ABERTURA (auto-cura): se alguma limpeza/antivirus/o usuario remover a
    entrada, o conector a recoloca no proximo boot manual. Silencioso: se nao
    der (nao-Windows, sem permissao), so loga — nunca quebra o app."""
    if HOMOLOG:   # H5: a entrada Run\BotTestedConector pertence à produção
        dbg("HOMOLOG: autostart DESLIGADO (registro do Windows intocado)")
        return False
    try:
        import winreg
    except Exception:
        return False
    try:
        exe = sys.executable
        # .exe do PyInstaller: sys.executable E o conector -> abre direto.
        # rodando como script: python + caminho do script.
        if exe.lower().endswith(("python.exe", "pythonw.exe")):
            alvo = f'\"{exe}\" \"{os.path.abspath(sys.argv[0])}\"'
        else:
            alvo = f'\"{exe}\"'
        chave = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run")
        # le o valor atual: so reescreve se mudou (evita I/O toda abertura)
        try:
            atual, _ = winreg.QueryValueEx(chave, "BotTestedConector")
        except Exception:
            atual = None
        if atual != alvo:
            winreg.SetValueEx(chave, "BotTestedConector", 0, winreg.REG_SZ, alvo)
            dbg(f"autostart registrado/atualizado -> {alvo}")
        else:
            dbg("autostart ja registrado (ok)")
        winreg.CloseKey(chave)
        return True
    except Exception as e:
        dbg(f"registrar_autostart falhou: {e}")
        return False


def registrar_protocolo():
    """Registra bottested:// apontando pra este .exe (HKCU\\Software\\Classes).
    Silencioso: se não der (não-Windows, sem permissão), só loga."""
    if HOMOLOG:   # H5 (hml4): protocolo TEMPORÁRIO com backup do da produção
        return _hml_registrar_protocolo()
    try:
        import winreg
    except Exception:
        return False
    try:
        exe = sys.executable
        # no .exe do PyInstaller, sys.executable É o conector; rodando como
        # script, aponta pro python + caminho do script
        if exe.lower().endswith(("python.exe", "pythonw.exe")):
            alvo = f'"{exe}" "{os.path.abspath(sys.argv[0])}" "%1"'
        else:
            alvo = f'"{exe}" "%1"'
        base = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\bottested")
        winreg.SetValueEx(base, "", 0, winreg.REG_SZ, "URL:BotTested Conector")
        winreg.SetValueEx(base, "URL Protocol", 0, winreg.REG_SZ, "")
        cmd = winreg.CreateKey(base, r"shell\open\command")
        winreg.SetValueEx(cmd, "", 0, winreg.REG_SZ, alvo)
        winreg.CloseKey(cmd)
        winreg.CloseKey(base)
        dbg(f"protocolo bottested:// registrado -> {alvo}")
        return True
    except Exception as e:
        dbg(f"registrar_protocolo falhou: {e}")
        return False


_PROTO_BACKUP = os.path.join(os.path.expanduser("~"), "BotTested_protocolo_PRODUCAO_backup.txt")
_PROTO_CHAVE = r"Software\Classes\bottested\shell\open\command"


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
            base = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\bottested")
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


def salvar_token(token):
    """Guarda o último token usado (pra auto-conectar quando o conector é
    aberto pela plataforma via bottested://)."""
    if token:
        _salvar_config({"ultimo_token": token.strip()})


def ler_token_salvo():
    return (_ler_config().get("ultimo_token") or "").strip()


def extrair_token_do_protocolo(argv):
    """Quando a plataforma abre o conector via bottested://validar?token=XYZ,
    o Windows passa a URL inteira como argumento (sys.argv). Esta função extrai
    o token de dentro dela pra o conector auto-preencher e auto-conectar JÁ na
    primeira vez, sem o usuário precisar colar nada. Retorna '' se não houver.

    Corrige o furo em que o front mandava o token na URL mas o conector só olhava
    o prefixo 'bottested:' e descartava o '?token=...' — deixando o campo vazio e
    o auto-conectar sem efeito na 1ª execução."""
    for a in (argv or []):
        s = str(a)
        if not s.lower().startswith("bottested:"):
            continue
        # 1) via urllib (trata bottested://validar?token=XYZ e decodifica %XX)
        try:
            from urllib.parse import urlparse, parse_qs
            tok = (parse_qs(urlparse(s).query).get("token", [""])[0] or "").strip()
            if tok:
                return tok
        except Exception:
            pass
        # 2) fallback por regex (variações do handler, com ou sem //)
        try:
            m = re.search(r"[?&]token=([^&\s]+)", s)
            if m:
                from urllib.parse import unquote
                return unquote(m.group(1)).strip()
        except Exception:
            pass
    return ""
