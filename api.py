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
API_BASE = "https://backtestpro-production-eb9a.up.railway.app"
INTERVALO_SNAPSHOT = 20      # segundos entre snapshots pra nuvem (v1.25: era 60 — presença mais viva e religar rápido)
APP_NOME = "BotTested Conector"
APP_VERSAO = "v1.30"         # v1.30 F2: EVENTOS POR ARQUIVO (ler_eventos_arquivo le bt_ev_<magic>.txt append-consume — canal confiavel pra BabyMachine, log vira fallback anti-duplicado). AUTOSTART obrigatorio/silencioso/auto-curavel (sobe com o Windows -> reboot nunca deixa a plataforma cega; re-registra a cada abertura se algo remover) + FIX DA MENTIRA SISTEMATICA no parser de posicoes (campo "posicoes" ausente vira None, nao 0 -> nao dispara reconciliacao de orfas indevida, incidente v6.91). Botao de reabrir ja existe via bottested:// (plataforma).          # v1.29: presenca em lote (1 POST p/ todos os tokens; fila serial so p/ quem tem job). v1.28: refresh de tokens 30s->8s (token de bot NOVO descoberto antes da janela de ~25s do front — matava o "could not reach the connector" no 1o envio). v1.27: VALIDACAO RELAMPAGO — job pre_validado (nuvem v6.38: mesmo codigo ja aprovado antes) instala, reporta o veredito NA HORA e compila em 2o plano (so pra gerar o .ex5). Corta a validacao repetida de ~25-55s pra ~5-10s. v1.26: FIM DE VIDA (EA escreve BOTTESTED_FIM no OnDeinit -> parada sinalizada na hora) + WATCHDOG (dado >35s sem leitura nova NAO e reenviado e sinaliza parada -> snapshot velho nunca mais segura o OPERANDO vivo) + rede pesada em thread propria (loop de leitura nunca bloqueia). v1.25: (1) magic->token mapeado NA INSTALACAO (extrai o magic do proprio .mq5 baixado -> zero dependencia da nuvem pro bot novo); (2) RELIGAR imediato (gap >25s no arquivo bt_snap = bot voltou -> envia ja, sem esperar o intervalo); (3) INTERVALO 60->20s; (4) aviso de EA ORFAO (magic sem dono na nuvem). v1.24: snapshot por arquivo dedicado. v1.23: throttle proprio 2s + diagnostico com hora.


# ── 0. Log de debug em arquivo ─────────────────────────────────────
# Como o .exe roda com --windowed (sem console), qualquer erro fica
# invisível. Este log grava o que o conector faz num arquivo de texto
# fácil de achar (na pasta do usuário). Reseta sozinho se passar de 2 MB.
DEBUG = True
DEBUG_PATH = os.path.join(os.path.expanduser("~"), "BotTested_Conector_debug.log")


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
        r = requests.get(f"{API_BASE}/conector/meus-bots",
                         params={"bot_token": tok}, timeout=20)
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
        r = requests.get(f"{API_BASE}/conector/tokens",
                         params={"bot_token": tok}, timeout=20)
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
        r = requests.get(f"{API_BASE}/conector/bot/mq5",
                         params={"bot_token": (bot_token or "").strip(),
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
        try:
            tam = os.path.getsize(a)
        except Exception:
            continue
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
def enviar_snapshot(bot_token, dados):
    """Manda snapshot pro /conector/snapshot. Read-only."""
    if requests is None:
        return False
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
        "detalhe": dados,
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
_CONFIG_PATH = os.path.join(os.path.expanduser("~"), "BotTested_Conector_config.json")


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
        r = requests.get(f"{API_BASE}/mt5/pendente",
                         params={"bot_token": bot_token}, timeout=20)
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
        return r.status_code == 200
    except Exception as e:
        dbg(f"reportar_veredito erro: {e}")
        return False


def validar_pendente(bot_token, mql5_dir, ao_iniciar=None, ao_terminar=None,
                     ao_instalar=None):
    """Fluxo completo de validação de um envio pro MT5:
      1) pega o .mq5 pendente na nuvem
      2) instala na pasta Experts
      3) compila (ou, sem compilador, checa a sintaxe)
      4) reporta o veredito
    Retorna (houve_pendente, aprovado, msg).
    ao_iniciar/ao_terminar: callbacks opcionais chamados quando um job é pego e
    quando ele termina — a GUI usa pra se minimizar/voltar e não disputar a tela
    com a janela de validação/guia da plataforma.
    ao_instalar(magic): v1.25 — chamado logo após instalar, com o magic extraído
    do próprio .mq5 (magic_do_mq5). O conector mapeia magic->token NA HORA, sem
    depender do refresh da nuvem (a variação de 13-40s pra acender o Operar era
    o mapa chegando atrasado)."""
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
        dbg(f"validar_pendente: job_id={job_id} nome={nome}")

        ok_inst, destino = instalar_ea(codigo, nome, mql5_dir)
        if not ok_inst:
            reportar_veredito(bot_token, job_id, False, f"falha ao instalar: {destino}")
            return True, False, "falha ao instalar o arquivo"
        if ao_instalar:
            try:
                _mg = magic_do_mq5(codigo)
                if _mg:
                    ao_instalar(_mg)
            except Exception:
                pass

        # VALIDAÇÃO RELÂMPAGO (v1.27): a nuvem marcou pre_validado = este MESMO
        # código (neutro) já foi aprovado no MT5 antes (só o magic difere, e
        # trocar o valor de um input não muda a compilação). Reporta o veredito
        # NA HORA e compila em 2º plano só pra gerar o .ex5 pro terminal.
        if job.get("pre_validado"):
            reportar_veredito(bot_token, job_id, True,
                              "pré-validado: código idêntico já aprovado no MT5 antes")
            def _compilar_bg(_destino=destino):
                try:
                    me = achar_metaeditor()
                    if me:
                        okc, _ = compilar_mq5(_destino, me)
                        dbg(f"compile em 2o plano (pre-validado): ok={okc}")
                except Exception as _e:
                    dbg(f"compile bg: {_e}")
            threading.Thread(target=_compilar_bg, daemon=True).start()
            return True, True, "pré-validado (compilando em 2º plano)"

        metaeditor = achar_metaeditor()
        if metaeditor:
            ok, log = compilar_mq5(destino, metaeditor)
            if ok is None:   # não deveria (achou o exe), mas por segurança
                ok, motivo = validar_sintaxe_mq5(codigo)
                log = "sem compilador (sintaxe): " + motivo
        else:
            ok, motivo = validar_sintaxe_mq5(codigo)
            log = "sem compilador na máquina (checagem de sintaxe): " + motivo

        reportar_veredito(bot_token, job_id, bool(ok), log)
        return True, bool(ok), (log or "")
    finally:
        if ao_terminar:
            try: ao_terminar()
            except Exception: pass


def checar_subir_conector(bot_token):
    """Pergunta à nuvem se a plataforma pediu pra trazer o conector pra frente
    (usuário apertou 'Entendi' na guia, ou ✅ com guia suprimida). One-shot: o
    backend limpa o sinal ao ler. Retorna True uma única vez por pedido."""
    if requests is None:
        return False
    try:
        r = requests.get(f"{API_BASE}/mt5/subir-conector",
                         params={"bot_token": (bot_token or "").strip()}, timeout=8)
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
