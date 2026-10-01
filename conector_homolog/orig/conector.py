"""
════════════════════════════════════════════════════════
 BotTested Conector v1.35 — interface (tkinter) + loop de monitoramento.
 v1.35: SNAPSHOT NUNCA MAIS DISPUTA COM EVENTO (caso BOTTESTED_40, 26/jul):
        o POST de cada evento saía DENTRO do loop de leitura (1.5s) — na
        enxurrada de recusadas do EA pré-v7.19 (dezenas por segundo, teto de
        posições + tentativa por tick), o loop passava o ciclo inteiro em
        HTTP e o snapshot atrasava 45-60s -> backend derrubava aos 45s ->
        card OFFLINE intermitente com trilha verde. Agora:
        (a) FILA DE ENVIO — o loop de leitura só ENFILEIRA o evento; uma
            thread própria (_loop_eventos) drena e faz os POSTs. Leitura e
            envio de snapshot nunca mais bloqueiam atrás de evento.
        (b) COALESCÊNCIA DE RECUSADAS — mesmo magic+motivo+lado dentro de
            30s é repetição sem informação nova: descartada antes da fila.
            Defesa em profundidade: o EA v7.19 já debounça na origem, mas um
            EA velho ainda no gráfico não pode mais afogar o Conector.
        (c) Fila órfã drenada também via fila de envio (nunca HTTP inline).
        Núcleo: APP_VERSAO enfim bumpado (ficou em v1.33 por engano) +
        backlog de bt_ev_ visto pela 1ª vez parado >90s drena sem emitir
        (a regra (e) da v1.34 que faltava no núcleo).
 v1.34: BLINDAGEM PÓS-SAGA DO EA FANTASMA (23/jul) — pré-requisito do recomeço
        limpo (bots novos só depois desta versão no ar):
        (a) EVENTO DE MAGIC ÓRFÃO NUNCA CAI NO FALLBACK DO TOKEN — a raiz da
            bagunça: EA velho ainda no gráfico (deletado na nuvem) disparava
            eventos e o conector, sem dono pro magic, atribuía ao token da
            SESSÃO -> bot novo nascia com 0✅ 4❌ de operações alheias e a IA
            narrava símbolo errado. Agora: evento sem dono vai pra uma FILA
            curta (até 50 por magic, TTL 120s) esperando o mapa; se o magic
            ganhar dono (bot novo recém-mapeado), a fila DRENA pro token certo
            — nenhum evento real do bot novo se perde; se nunca ganhar (EA
            fantasma), DESCARTA com aviso claro na tela: "⚠ EA órfão magic X
            operando — remova do gráfico". Magic 0 (bot antigo sem magic) é
            ambíguo -> descarta + aviso pra reenviar pelo Editor.
        (b) AVISO DE SNAPSHOT SEGURADO NUNCA SILENCIA — antes, após 3 falhas
            de mapa o "⏳ sem token" parava de aparecer e o snapshot ficava
            retido em silêncio. Agora repete 1x/60s por magic enquanto houver
            snapshot segurado (órfão ou aguardando mapa), pra sempre.
        (c) RADAR IGNORA FRESCOR DE MAGIC ÓRFÃO — EA fantasma escrevendo
            bt_snap_/bt_ev_ mantinha a instalação errada "ativa" e segurava o
            radar nela. _frescor_pasta agora pula arquivos de magics órfãos.
        (d) FECHAR A JANELA NÃO MATA O CONECTOR POR ACIDENTE — com o monitor
            rodando, o X pergunta: fechar de verdade (bots param de reportar)
            ou só minimizar (padrão; reabrir = clicar na barra de tarefas).
            Caminho de reabrir sempre visível: janela minimizada na taskbar +
            bottested:// pela plataforma.
        (e) BACKLOG NÃO É DADO FRESCO — o núcleo (ler_eventos_arquivo) drena
            sem emitir o histórico de bt_ev_ parado >90s visto pela 1ª vez;
            a trilha e a nuvem só recebem o que é vivo de verdade.
        FIX RAIZ: faltava `import glob` neste arquivo — o radar v1.32
        (_frescor_pasta) dava NameError engolido e devolvia sempre None:
        o radar NUNCA funcionou. Corrigido; radar passa a operar de fato.
 v1.33: janela 520->620px + redimensionável na vertical (a trilha v1.31
        empurrou a linha de status pra fora da janela fixa).
 v1.32: RADAR DE INSTALAÇÃO — a detecção escolhe a instalação com
        bt_snap_/bt_ev_ mais fresco; radar de 12s troca sozinho quando a
        atual está muda >120s e outra tem atividade <90s.
 v1.31: TRILHA DE CONEXÃO (desenho do dono): MT5 ◯ ━━ ◯ Conector ◯ ━━ ◯
        Plataforma com circulação viva; fix do magic 0 no núcleo.
 v1.30: autostart obrigatório/silencioso/auto-curável + fix do parser de
        posições + F2 eventos por arquivo (bt_ev_<magic>.txt).
 v1.29: PRESENÇA EM LOTE (par do api v6.52) — 1 POST /mt5/presenca com todos os
        tokens por ciclo (heartbeat de todos de uma vez) e validar_pendente roda
        só nos que têm job. Ciclo volta a ~2s com QUALQUER nº de bots (a série
        de GETs com 19 bots passava de 25s e derrubava o envio de bot novo).
        Fallback: se a rota não existir (api antiga), volta ao modo série.
 v1.28: DESCOBERTA DE TOKEN NOVO em 8s (era 30s) — enviar um bot novo cria um
        token novo e o front espera ~25s pelo sinal de vida dele; o refresh de
        30s as vezes chegava depois e o envio falhava com "could not reach the
        connector" (passava no retry). Custo: 1 GET /conector/tokens a cada 8s.
 v1.27: VALIDACAO RELAMPAGO (par da api v6.38) — quando a nuvem marca o job
        como pre_validado (mesmo codigo ja aprovado no MT5 antes; so o magic
        difere), o conector instala, reporta o veredito NA HORA e compila em
        2o plano so pra gerar o .ex5. Junto com o cache de geracao da nuvem
        (a IA so roda na 1a vez de cada estrategia), a validacao repetida cai
        de ~25-55s pra ~5-10s.
 v1.26: DESLIGAR consistente + loop desbloqueado (bugs achados no teste v1.25:
        desligar erratico ate 3min7s; ligar ~30s com religar de 14s):
        (1) BUG RAIZ do desligar: quando o EA saia do grafico, o conector
            continuava REENVIANDO o snapshot VELHO do cache a cada INTERVALO —
            com 20s de intervalo o ultimo_ping nunca envelhecia alem da janela
            de 90s do backend e o OPERANDO ficava aceso artificialmente.
            Agora: WATCHDOG — dado sem leitura NOVA ha >35s nao e reenviado
            (o EA escreve a cada 10s; 35s de silencio = saiu mesmo) e a parada
            daquele token e sinalizada 1x pra nuvem.
        (2) FIM DE VIDA — o EA (api v6.37+) escreve BOTTESTED_FIM no arquivo
            quando REMOVIDO do grafico (OnDeinit): o conector sinaliza a parada
            NA HORA -> desligar em ~5-12s SEM depender do botao Parar.
        (3) REDE PESADA EM THREAD PROPRIA — validacao de pendentes (1 GET por
            token a cada 5s), refresh de tokens (30s) e Meus bots (20s) saem do
            loop de leitura. Com varios bots, essas chamadas sequenciais
            bloqueavam a leitura por segundos e atrasavam o Operar. O loop de
            leitura agora SO le arquivo/log e envia (ciclo estavel de 1.5s).
        (4) DIAGNOSTICO DO LIGAR: "🚀 1º snapshot enviado" com HORA — compare
            com a hora do drag e a hora que o Operar acende: se o 🚀 sai em ~5s
            e o Operar demora 30s, a gordura esta no polling do front.
 v1.25: caça aos segundos que SOBRARAM do teste v1.24 (ligar 13-40s, religar
        32-42s):
        (1) MAPA NA INSTALACAO — ao instalar o .mq5 baixado, extrai o magic do
            proprio codigo e grava magic->token NA HORA (o token e o da rota que
            baixou). Zero dependencia do refresh da nuvem pro bot novo — era o
            ramo "⏳ sem token no mapa" que fazia o ligar variar de 13 a 40s.
        (2) RELIGAR IMEDIATO — gap >25s entre escritas do bt_snap_<magic>.txt
            (EA escreve a cada 10s) = bot saiu e VOLTOU: zera o throttle daquele
            magic e envia no mesmo ciclo. Era a causa do religar em 32-42s (o
            conector lia na hora mas esperava o resto do INTERVALO de 60s).
        (3) INTERVALO_SNAPSHOT 60s -> 20s (presenca mais viva; religar pior
            caso cai junto).
        (4) EA ORFAO com aviso claro — magic que segue sem dono na nuvem apos
            3 refreshes e marcado orfao: para de forcar refresh (nao gasta rede)
            e avisa 1x/min "remova do grafico" (bot deletado na nuvem mas ainda
            rodando no MT5 — o 'zerar tudo' deixa esses pra tras).
 v1.24: SNAPSHOT POR ARQUIVO DEDICADO — o EA (gerado pela api v6.36+) grava a
        linha BOTTESTED_SNAPSHOT em <MQL5>/Files/bt_snap_<magic>.txt com flush
        imediato; o loop le esse arquivo a CADA CICLO (1.5s), ANTES do log.
        Mata a inconsistencia de 22s-2min15s pra acender o Operar, cuja causa
        era o BUFFERING do log do MT5 (a linha existia mas demorava a ir pro
        disco). O log continua como fallback (bots antigos) e pros EVENTOS
        (aberto/fechado). Diagnostico na tela distingue: "(arquivo)" vs "(log)".
 v1.23: (1) FIX mapa de magic->token lento p/ bot novo: o refresh ao ver magic
        novo tinha throttle amarrado no _tokens_ts, que o refresh periodico de
        30s mantinha "recente" e BLOQUEAVA — bot novo esperava ate 30s pra ser
        mapeado. Agora throttle proprio de 2s. (2) DIAGNOSTICO na tela: o status
        mostra com HORA quando LEU o snapshot, se o magic esta mapeado e quando
        ENVIOU — pra achar onde estao os segundos por print, sem depender do log.
 v1.22: FIX velocidade INCONSISTENTE (14s a 2min pra acender): o log do EA
        (MQL5/Logs, onde sai o BOTTESTED_SNAPSHOT) as vezes caia pra fora do
        top-2 por mtime (o journal do terminal ficava mais recente) e o conector
        PARAVA de ler o snapshot. Agora achar_logs_mt5 poe o log do EA SEMPRE
        primeiro; loop le os 3 mais recentes e roda a cada 1.5s (era 3s). Operar
        acende rapido e CONSISTENTE.
 v1.21: LISTA COERENTE — a lista "Meus bots" agora atualiza SOZINHA: logo apos
        enviar um bot (aparece na hora) e a cada ~20s (online/offline + bots
        novos). Quando o conector esta ligado mas nao ha bot registrado, o
        status deixa claro ("Conector ligado - nenhum bot enviado ainda"). Todas
        as buscas rodam em BACKGROUND (nao travam a UI). Deletar agora e 2 cliques
        (Deletar -> confirmar); tirei o popup final de "deletado".
 v1.20: OPERAR ACENDE RAPIDO — envio de snapshot agora e POR-BOT: um bot novo
        (recem-arrastado) e enviado IMEDIATAMENTE (nao espera o ciclo global de
        60s); depois cada bot respeita o INTERVALO em regime (custo baixo). Alem
        disso, ao ver um magic novo/desconhecido no snapshot, atualiza o mapa de
        tokens NA HORA (max 1x/5s) em vez de esperar o refresh de 30s. Corta o
        tempo pra o Operar acender de ~2min pra ~poucos segundos.
 v1.19: PRESENCA — ao apertar Parar, avisa a nuvem NA HORA (POST /presenca/parar)
        e limpa o cache de snapshot (para de reenviar residual). Corte imediato:
        a trilha/monitor rebaixa no proximo polling, sem esperar timeout. Ponta
        do coletor que o Tryd vai reusar (backend e a fonte de verdade).
 v1.18: ROTEAMENTO ESTRITO POR MAGIC (com o backend v6.23 emitindo magic no
        snapshot). Snapshot SEM magic e AMBIGUO (nao da pra saber de qual bot
        e) entao NAO e enviado — mata o falso "Operar" (bot fora do grafico
        acendia a trilha porque um snapshot residual/de outro bot caia no
        token da sessao pelo fallback do v1.17). Cada snapshot vai pro token
        do dono do magic; bot fora do grafico nunca pinga. Bot antigo sem
        magic: reenviar pelo Editor pra o .mq5 sair com magic.
 v1.17: FALLBACK p/ snapshot SEM magic — os EAs ainda nao emitem magic no
        BOTTESTED_SNAPSHOT, entao o roteamento por magic (v1.16) descartava
        TODOS os snapshots e nada pingava. Agora: snapshot com magic roteia
        pelo magic; snapshot SEM magic cai no token da sessao (comportamento
        antigo) — o bot no grafico volta a pingar. Quando o backend passar a
        emitir magic no snapshot (api v6.23+), o roteamento fica exato.
 v1.16: SNAPSHOT ROTEADO POR MAGIC — cada bot manda o dado vivo pro SEU token
        (o magic no snapshot identifica o bot). Conserta o falso "Operar" na
        trilha (acendia pra um bot que só estava no Navegador, não no gráfico,
        porque o snapshot de OUTRO bot ia pro token errado) e faz o multi-bot
        de verdade: rodando vários gráficos, cada um atualiza o seu no Monitor.
        Snapshot sem magic conhecido é descartado (nunca vira ping falso).
 v1.15: SINGLE-INSTANCE (lock por socket local na porta 50573: a 2ª tentativa de
        abrir repassa o token pra 1ª janela e sai — acaba a bagunça de várias
        janelas abrindo e conflitando) + MULTI-BOT (o loop valida TODOS os tokens
        do usuário via /conector/tokens, não só o colado — conserta o "Não
        aprovado / não consegui falar com o conector" que acontecia quando a
        janela vigiava o token de um bot e o envio era de outro). Um conector,
        vários bots, todos vigiados/validados juntos.
 v1.14: "ⓘ Como rodar no MT5" em texto azul, sem a caixa preenchida — destaque
        pela cor, mais leve.
 v1.13: o botão "ⓘ Como rodar no MT5" ficou destacado (antes passava batido).
 v1.9: quando pega um job de validação, o conector se MINIMIZA sozinho — assim
        ele e a janela do Fab/guia nunca disputam a tela; só uma por vez.
 v1.8: botão ⓘ "Como rodar no MT5" abre uma guia offline.
 v1.7: card "Meus bots" — Reinstalar / Desinstalar / Deletar pelo token.
 v1.6: o botão Instalar nomeia o EA pelo bot + magic do token.
 v1.5: abre via bottested://validar?token=XYZ e auto-conecta.
 Junta o núcleo (conector_nucleo) numa janelinha simples:
   - cola o token
   - acha o MT5 sozinho
   - instala o EA
   - mostra status (conectado / enviando)
   - lê o log e reporta em segundo plano

 Compilar (Windows):
   pip install requests pyinstaller
   pyinstaller --onefile --windowed --name "BotTested Conector" conector.py
════════════════════════════════════════════════════════
"""
import os
import sys
import glob
import time
import socket
import threading
import traceback
import collections   # v1.35: fila de envio de eventos

# importa o núcleo (no .exe os dois arquivos viram um; aqui mantemos separado
# pra organização — na hora de compilar, junte ou use --add-data)
import requests   # v1.29: usado pela presença em lote (/mt5/presenca)
from conector_nucleo import (
    API_BASE, INTERVALO_SNAPSHOT, APP_NOME, APP_VERSAO,
    achar_pastas_mt5, pasta_experts, baixar_e_instalar_ea,
    achar_logs_mt5, ler_novas_linhas, parse_linha_log, ler_snapshots_arquivo,
    ler_eventos_arquivo,
    magic_do_mq5,
    enviar_snapshot, enviar_evento, dbg, DEBUG_PATH,
    validar_pendente, registrar_protocolo, salvar_token, ler_token_salvo,
    extrair_token_do_protocolo,
    listar_meus_bots, listar_tokens_do_usuario,
    reinstalar_bot, desinstalar_ea_local, deletar_bot,
    checar_subir_conector, sinalizar_parada,
    registrar_autostart,
)

# porta local fixa usada como "lock" de instância única (single-instance).
# Se conseguir bindar, esta é a 1ª janela (dona). Se não, já há um conector
# aberto — a 2ª tentativa repassa o token pra ele e sai (sem abrir outra janela).
_LOCK_PORT = 50573

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    tk = None

# Cores da marca BotTested
COR_BG = "#0e1c30"
COR_CARD = "#13243a"
COR_VERDE = "#00d084"
COR_TEXTO = "#e6edf3"
COR_MUTED = "#9aa7b8"
COR_VERMELHO = "#ff5a5a"


class ConectorApp:
    def __init__(self, root, via_protocolo=False, token_inicial=""):
        self.root = root
        self.bot_token = ""
        self.mql5_dir = None
        self.instalacoes = []     # lista de dicts {mql5, terminal, rotulo}
        self.rodando = False
        self.thread = None
        self._log_pos = {}        # caminho_log -> última posição lida
        self._tokens_todos = []   # MULTI-BOT: todos os tokens do usuário (cache)
        self._tokens_ts = 0       # quando o cache de tokens foi atualizado
        self._token_por_magic = {}  # magic (int) -> token do bot dono daquele magic
        self._snaps_por_magic = {}  # magic (int) -> último snapshot daquele bot
        self._envio_por_magic = {}  # magic (int) -> ts do último envio (por-bot)
        self._snap_file_mtime = {}  # v1.24: bt_snap_*.txt -> mtime da última leitura
        self._ev_file_pos = {}      # v1.30 F2: bt_ev_*.txt -> offset (bytes) já lido
        self._magic_falhas = {}     # v1.25: magic -> nº de refreshes sem achar dono (órfão?)
        self._orfao_aviso_ts = {}   # v1.25: magic órfão -> ts do último aviso na tela
        self._lido_por_magic = {}   # v1.26: magic -> ts da última LEITURA fresca (watchdog)
        self._parada_sinalizada = set()  # v1.26: magics cuja parada já foi avisada à nuvem
        self._ts_mt5 = 0.0    # v1.31 trilha: ts da última leitura REAL vinda do MT5 (snapshot/evento)
        self._ts_cloud = 0.0  # v1.31 trilha: ts do último POST ACEITO pela plataforma (200)
        self._bots_ts = 0           # ts do último refresh da lista 'Meus bots'
        self._ev_pendentes = {}     # v1.34: magic sem dono -> [(ts, evento)] esperando o mapa (TTL 120s, máx 50)
        self._seguro_aviso_ts = {}  # v1.34: magic -> ts do último aviso de snapshot SEGURADO (nunca silencia)
        self._ev_fila_envio = collections.deque(maxlen=400)  # v1.35: (token, evento) aguardando POST — drenada pela _loop_eventos
        self._rec_ult = {}          # v1.35: "magic|motivo|lado" -> ts da última recusada aceita (coalescência 30s)
        self._montar_ui()
        self._detectar_mt5()
        # v1.34 (d): fechar a janela com o monitor rodando pergunta; padrão = minimizar
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._fechar_janela)
        except Exception:
            pass
        # Token: prioridade pro que a plataforma mandou na URL (bottested://…?token=);
        # senão, o salvo da última vez. Assim a 1ª vez já funciona sem colar nada.
        tok = (token_inicial or "").strip()
        if not tok:
            try:
                tok = ler_token_salvo()
            except Exception:
                tok = ""
        if tok:
            try:
                self.entry_token.delete(0, "end")
                self.entry_token.insert(0, tok)
            except Exception:
                pass
            if token_inicial:            # veio da plataforma → já guarda pro futuro
                try: salvar_token(tok)
                except Exception: pass
        # aberto pela plataforma (bottested://) → conecta sozinho, sem clique
        if via_protocolo:
            self.root.after(600, self._auto_conectar)

    def _auto_conectar(self):
        try:
            if not self.rodando and self.entry_token.get().strip() and self.mql5_dir:
                self._toggle_conectar()
                self.lbl_status.config(text="Aberto pela plataforma — conectado e validando…",
                                       fg=COR_VERDE)
        except Exception as e:
            dbg(f"_auto_conectar: {e}")

    def _fechar_janela(self):
        """v1.34 (d) — o X da janela não mata mais o Conector por acidente.
        Com o monitor RODANDO: pergunta; 'Não' (padrão do fluxo) só MINIMIZA —
        o Conector segue vivo na barra de tarefas (caminho visível de reabrir:
        clicar nela; ou bottested:// pela plataforma). 'Sim' fecha de verdade
        e sinaliza a parada. Parado: fecha direto."""
        try:
            if self.rodando:
                if messagebox.askyesno(
                        APP_NOME,
                        "O Conector está monitorando seus bots.\n\n"
                        "Fechar DE VERDADE? (os bots param de reportar pra plataforma)\n\n"
                        "Escolha 'Não' pra apenas minimizar — ele continua rodando\n"
                        "na barra de tarefas e você reabre com um clique."):
                    try:
                        toks = list(self._tokens_todos) or ([self.bot_token] if self.bot_token else [])
                        sinalizar_parada(toks)
                    except Exception:
                        pass
                    self.root.destroy()
                else:
                    self.root.iconify()
                    self._set_status("Conector minimizado — segue monitorando. Reabra pela barra de tarefas.")
            else:
                self.root.destroy()
        except Exception:
            try:
                self.root.destroy()
            except Exception:
                pass

    # ── UI ──────────────────────────────────────────────────────
    def _montar_ui(self):
        self.root.title(f"{APP_NOME} {APP_VERSAO}")
        self.root.configure(bg=COR_BG)
        # v1.33 — a trilha (v1.31) adicionou ~70px e a janela fixa de 520 empurrou
        # a LINHA DE STATUS (o diagnóstico vivo) pra fora da tela, sem como
        # expandir (resizable estava travado). Agora: altura que comporta tudo
        # + redimensionável na vertical.
        self.root.geometry("460x620")
        self.root.minsize(460, 560)
        self.root.resizable(False, True)

        # Cabeçalho
        topo = tk.Frame(self.root, bg=COR_BG)
        topo.pack(fill="x", padx=22, pady=(20, 10))
        tk.Label(topo, text="BotTested", bg=COR_BG, fg=COR_VERDE,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(topo, text=" Conector", bg=COR_BG, fg=COR_TEXTO,
                 font=("Segoe UI", 18)).pack(side="left")
        tk.Label(topo, text=APP_VERSAO, bg=COR_BG, fg=COR_MUTED,
                 font=("Segoe UI", 9)).pack(side="right")

        # ── v1.31: TRILHA DE CONEXÃO (desenho do dono) ─────────────────────
        # MT5 ◯ ━━ ◯ Conector ◯ ━━ ◯ Plataforma — mostra a CIRCULAÇÃO de
        # dados em tempo real (pulso viajando), não status parado. Se o bot
        # sai do MT5, o sinal CAI do lado do MT5 (pra baixo); se a nuvem
        # corta, CAI do lado da Plataforma (pra cima). Um olhar diz qual
        # elo morreu.
        self.trilha_canvas = tk.Canvas(self.root, width=420, height=66,
                                       bg=COR_BG, highlightthickness=0)
        self.trilha_canvas.pack(padx=22, pady=(2, 0))
        self.root.after(900, self._trilha_tick)
        self.root.after(6000, self._mt5_auto_radar)   # v1.32: radar de instalação

        # Status MT5 + seletor de instalação
        self.lbl_mt5 = tk.Label(self.root, text="Procurando o MetaTrader 5…",
                                bg=COR_BG, fg=COR_MUTED, font=("Segoe UI", 10),
                                wraplength=410, justify="left")
        self.lbl_mt5.pack(fill="x", padx=22, pady=(4, 4))

        # seletor (só aparece se houver mais de 1 instalação) — pack feito depois
        self.frame_seletor = tk.Frame(self.root, bg=COR_BG)
        tk.Label(self.frame_seletor, text="Qual MT5 usar:", bg=COR_BG,
                 fg=COR_MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.combo_mt5 = ttk.Combobox(self.frame_seletor, state="readonly",
                                      font=("Segoe UI", 9))
        self.combo_mt5.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.combo_mt5.bind("<<ComboboxSelected>>", self._mt5_selecionado)

        # Campo do token
        card1 = tk.Frame(self.root, bg=COR_CARD)
        card1.pack(fill="x", padx=22, pady=8)
        tk.Label(card1, text="1. Cole o token do painel BotTested",
                 bg=COR_CARD, fg=COR_VERDE, font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", padx=14, pady=(12, 4))
        self.entry_token = tk.Entry(card1, font=("Consolas", 11),
                                    bg="#0a1626", fg=COR_TEXTO,
                                    insertbackground=COR_TEXTO, relief="flat")
        self.entry_token.pack(fill="x", padx=14, pady=(0, 12), ipady=6)

        # Card "Meus bots" — lista os bots que o usuário criou (puxados da nuvem
        # pelo token). Criar é na plataforma (Editor → Enviar pro MT5); aqui a
        # gente gerencia: reinstala, desinstala ou deleta.
        card2 = tk.Frame(self.root, bg=COR_CARD)
        card2.pack(fill="x", padx=22, pady=8)
        topo2 = tk.Frame(card2, bg=COR_CARD)
        topo2.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(topo2, text="2. Meus bots", bg=COR_CARD, fg=COR_VERDE,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Button(topo2, text="↻ Atualizar", command=self._atualizar_bots_bg,
                  bg=COR_CARD, fg=COR_MUTED, relief="flat", bd=0,
                  activebackground=COR_CARD, activeforeground=COR_TEXTO,
                  font=("Segoe UI", 8), cursor="hand2").pack(side="right")
        tk.Button(topo2, text="ⓘ Como rodar no MT5", command=self._abrir_guia_mt5,
                  bg=COR_CARD, fg="#4aa3ff", relief="flat", bd=0,
                  activebackground=COR_CARD, activeforeground="#7dc0ff",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=6).pack(side="right", padx=(0, 10))
        self.combo_bots = ttk.Combobox(card2, state="readonly", font=("Segoe UI", 9))
        self.combo_bots.pack(fill="x", padx=14, pady=(0, 8), ipady=3)
        self.combo_bots.set("Conecte pra ver seus bots…")
        self._bots_map = []       # índice do combo -> dict do bot
        linha_btns = tk.Frame(card2, bg=COR_CARD)
        linha_btns.pack(fill="x", padx=14, pady=(0, 12))
        tk.Button(linha_btns, text="Reinstalar", command=self._reinstalar_click,
                  bg=COR_VERDE, fg="#06231a", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10).pack(side="left")
        tk.Button(linha_btns, text="Desinstalar", command=self._desinstalar_click,
                  bg="#243447", fg=COR_TEXTO, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10).pack(side="left", padx=(8, 0))
        tk.Button(linha_btns, text="Deletar", command=self._deletar_click,
                  bg="#3a1620", fg="#ff9aa8", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10).pack(side="right")

        # Botão conectar (liga o monitoramento)
        self.btn_conectar = tk.Button(self.root, text="▶  Conectar e monitorar",
                                      command=self._toggle_conectar,
                                      bg=COR_VERDE, fg="#06231a", relief="flat",
                                      font=("Segoe UI", 12, "bold"), pady=10)
        self.btn_conectar.pack(fill="x", padx=22, pady=(16, 8))

        # Status do monitoramento
        self.lbl_status = tk.Label(self.root, text="Parado.",
                                   bg=COR_BG, fg=COR_MUTED, font=("Segoe UI", 10))
        self.lbl_status.pack(fill="x", padx=22, pady=(4, 2))

        # Rodapé de segurança
        tk.Label(self.root,
                 text="Read-only: só lê e envia. Nunca pede senha de corretora\n"
                      "nem comanda o seu robô.",
                 bg=COR_BG, fg=COR_MUTED, font=("Segoe UI", 8),
                 justify="center").pack(side="bottom", pady=12)

    # ── Lógica ────────────────────────────────────────────────────────
    def _detectar_mt5(self):
        self.instalacoes = achar_pastas_mt5()
        if not self.instalacoes:
            self.lbl_mt5.config(
                text="⚠ MetaTrader 5 não encontrado. Abra o MT5 ao menos uma "
                     "vez e reinicie este conector.", fg=COR_VERMELHO)
            self.mql5_dir = None
            self.frame_seletor.pack_forget()
            return
        # monta os rótulos pro seletor
        rotulos = []
        for i, inst in enumerate(self.instalacoes):
            rotulos.append(f"{i+1}. {inst['rotulo']}")
        self.combo_mt5["values"] = rotulos
        # v1.32 — RADAR DE INSTALAÇÃO: a v1.31 SEMPRE forçava a instalação [0]
        # a cada abertura (a escolha do usuário nunca sobrevivia ao restart —
        # o "dropdown que não funciona"). Agora a detecção escolhe a instalação
        # com ATIVIDADE REAL: a que tem bt_snap_/bt_ev_ mais fresco. Sem
        # atividade em nenhuma, cai na [0] como antes.
        idx0 = self._idx_instalacao_ativa()
        self.combo_mt5.current(idx0)
        self.mql5_dir = self.instalacoes[idx0]["mql5"]

        if len(self.instalacoes) > 1:
            # mostra o seletor — usuário escolhe qual MT5
            self.frame_seletor.pack(fill="x", padx=22, pady=(0, 6),
                                    after=self.lbl_mt5)
            self.lbl_mt5.config(
                text=f"✓ {len(self.instalacoes)} instalações do MetaTrader 5 "
                     "encontradas. Escolha qual usar abaixo:", fg=COR_VERDE)
        else:
            self.frame_seletor.pack_forget()
            self.lbl_mt5.config(
                text=f"✓ MetaTrader 5 encontrado.\n{self.mql5_dir}",
                fg=COR_VERDE)

    def _mt5_selecionado(self, event=None):
        idx = self.combo_mt5.current()
        if 0 <= idx < len(self.instalacoes):
            self._trocar_instalacao(idx, origem="manual")

    # ── v1.32: RADAR DE INSTALAÇÃO ────────────────────────────────────
    def _magics_orfaos(self):
        """v1.34 (c) — conjunto de magics já marcados ÓRFÃOS (3+ refreshes sem
        dono na nuvem). O radar e o frescor de pasta ignoram os arquivos deles:
        EA fantasma escrevendo não pode segurar o radar na instalação errada."""
        try:
            return {int(mg) for mg, f in self._magic_falhas.items() if f >= 3}
        except Exception:
            return set()

    @staticmethod
    def _frescor_pasta(mql5_dir, ignorar_magics=None):
        """Segundos desde o arquivo bt_snap_/bt_ev_ mais recente da instalação.
        None = nenhum arquivo BotTested (instalação sem atividade).
        v1.34 (c): arquivos de magic ÓRFÃO são ignorados — atividade de EA
        fantasma não conta como frescor."""
        try:
            import re as _re
            ign = ignorar_magics or set()
            pasta = os.path.join(mql5_dir, "Files")
            arqs = (glob.glob(os.path.join(pasta, "bt_snap_*.txt"))
                    + glob.glob(os.path.join(pasta, "bt_ev_*.txt")))
            if ign:
                filtrados = []
                for a in arqs:
                    m = _re.search(r"bt_(?:snap|ev)_(\d+)\.txt$", os.path.basename(a))
                    try:
                        if m and int(m.group(1)) in ign:
                            continue
                    except Exception:
                        pass
                    filtrados.append(a)
                arqs = filtrados
            if not arqs:
                return None
            m = max(os.path.getmtime(a) for a in arqs)
            return max(0.0, time.time() - m)
        except Exception:
            return None

    def _idx_instalacao_ativa(self):
        """Índice da instalação com o arquivo BotTested mais FRESCO; 0 se nada."""
        melhor, melhor_fr = 0, None
        ign = self._magics_orfaos()
        for i, inst in enumerate(self.instalacoes):
            fr = self._frescor_pasta(inst.get("mql5") or "", ign)
            if fr is not None and (melhor_fr is None or fr < melhor_fr):
                melhor, melhor_fr = i, fr
        return melhor

    def _trocar_instalacao(self, idx, origem="radar"):
        """Aponta o conector pra instalação idx e ZERA os caches de leitura
        (posições de log/arquivo pertencem à pasta antiga)."""
        self.mql5_dir = self.instalacoes[idx]["mql5"]
        try:
            self.combo_mt5.current(idx)
        except Exception:
            pass
        self._snap_file_mtime.clear()
        self._ev_file_pos.clear()
        try:
            self._log_pos.clear()
        except Exception:
            pass
        rot = self.instalacoes[idx].get("rotulo", "?")
        pre = "MT5 selecionado" if origem == "manual" else "🔀 atividade detectada — troquei pro"
        self._set_status(f"{pre}: {rot}")
        try:
            self.lbl_mt5.config(text=f"✓ Vigiando: {rot}\n{self.mql5_dir}", fg=COR_VERDE)
        except Exception:
            pass

    def _mt5_auto_radar(self):
        """A cada 12s: se a instalação ATUAL está muda (>120s sem arquivo novo)
        e OUTRA tem atividade fresca (<90s), troca sozinho. O usuário nunca
        mais precisa adivinhar dropdown — o dado manda.
        v1.34 (c): frescor de magic órfão não conta (EA fantasma não manda)."""
        try:
            if len(self.instalacoes) > 1 and self.mql5_dir:
                ign = self._magics_orfaos()
                fr_atual = self._frescor_pasta(self.mql5_dir, ign)
                if fr_atual is None or fr_atual > 120:
                    for i, inst in enumerate(self.instalacoes):
                        if inst.get("mql5") == self.mql5_dir:
                            continue
                        fr = self._frescor_pasta(inst.get("mql5") or "", ign)
                        if fr is not None and fr < 90:
                            self._trocar_instalacao(i, origem="radar")
                            break
        except Exception:
            pass
        try:
            self.root.after(12000, self._mt5_auto_radar)
        except Exception:
            pass

    def _carregar_meus_bots(self, token=None):
        """Busca na nuvem os bots do usuário (pelo token) e atualiza o combo.
        Pode ser chamado de QUALQUER thread: a rede roda aqui, mas a atualização
        do combo é agendada no main thread (via after). Interativo (botão/connect)
        chama sem token (lê o campo); em background, passa self.bot_token."""
        if token is None:
            try:
                token = (self.entry_token.get() or "").strip()
            except Exception:
                token = self.bot_token or ""
        token = (token or "").strip()
        if not token:
            self.root.after(0, lambda: self.combo_bots.set("Cole o token e conecte primeiro…"))
            return
        ok, res = listar_meus_bots(token)
        self.root.after(0, lambda: self._preencher_combo(ok, res))

    def _preencher_combo(self, ok, res):
        """Atualiza o combo 'Meus bots' (roda no main thread)."""
        self._bots_map = []
        self.combo_bots["values"] = []
        if not ok:
            self.combo_bots.set("Não consegui buscar seus bots.")
            dbg(f"meus-bots erro: {res}")
            return
        self._bots_map = res or []
        if not self._bots_map:
            # COERÊNCIA: conector ligado, mas nenhum bot registrado na nuvem.
            self.combo_bots.set("Nenhum bot ainda — crie um no Editor.")
            if self.rodando:
                self._set_status("Conector ligado — nenhum bot enviado ainda. Crie um no Editor.")
            return
        rotulos = []
        for b in self._bots_map:
            est = "◯ online" if b.get("online") else "◌ offline"
            sim = (b.get("simbolo") or "").strip()
            rot = b.get("nome", "Meu Bot")
            if sim:
                rot += f" · {sim}"
            rot += f"  ({est})"
            rotulos.append(rot)
        self.combo_bots["values"] = rotulos
        try:
            self.combo_bots.current(0)
        except Exception:
            pass

    # ── v1.31: TRILHA DE CONEXÃO ────────────────────────────────────
    def _trilha_tick(self):
        try:
            self._trilha_desenhar()
        except Exception:
            pass
        try:
            self.root.after(700, self._trilha_tick)
        except Exception:
            pass

    def _trilha_desenhar(self):
        agora = time.time()

        def est(ts):
            if not ts:
                return 0
            dt = agora - ts
            return 2 if dt < 45 else (1 if dt < 120 else 0)

        e_mt5 = est(self._ts_mt5)
        e_cld = est(self._ts_cloud)
        cores = {2: "#00d084", 1: "#ffb830", 0: "#ff5252"}
        c = self.trilha_canvas
        c.delete("all")
        y = 24
        xs = (70, 210, 350)
        self._trilha_fase = (getattr(self, "_trilha_fase", 0) + 1) % 4

        def pulso(x0, x1, cor):
            c.create_line(x0 + 8, y, x1 - 8, y, fill=cor, width=3)
            frac = 0.15 + 0.7 * (self._trilha_fase / 3.0)
            px = x0 + (x1 - x0) * frac
            c.create_oval(px - 4, y - 4, px + 4, y + 4, fill=cor, outline="")

        # trecho MT5 -> Conector
        if e_mt5:
            pulso(xs[0], xs[1], cores[e_mt5])
        else:
            # CAIU DO LADO DO MT5: sinal despenca PRA BAIXO
            c.create_line(xs[0] + 8, y, xs[0] + 60, y + 24,
                          fill=cores[0], width=3, arrow="last")
            c.create_text((xs[0] + xs[1]) / 2, y + 30, text="sem sinal do MT5",
                          fill=cores[0], font=("Segoe UI", 8))
        # trecho Conector -> Plataforma
        if e_cld:
            pulso(xs[1], xs[2], cores[e_cld])
        else:
            # CAIU DO LADO DA PLATAFORMA: sinal se solta PRA CIMA
            c.create_line(xs[2] - 8, y, xs[2] - 60, y - 20,
                          fill=cores[0], width=3, arrow="last")
            c.create_text((xs[1] + xs[2]) / 2, y + 30, text="sem conexão com a plataforma",
                          fill=cores[0], font=("Segoe UI", 8))
        # bolinhas + rótulos
        rot = ("MT5", "Conector", "Plataforma")
        cor_no = (cores[e_mt5], "#00d084", cores[e_cld])
        for i, x in enumerate(xs):
            c.create_oval(x - 7, y - 7, x + 7, y + 7, fill=cor_no[i],
                          outline="#0a1626", width=2)
            c.create_text(x, y + 20, text=rot[i], fill="#8fa3bd",
                          font=("Segoe UI", 8, "bold"))
        # frescor honesto (há quanto tempo cada lado deu sinal)
        if self._ts_mt5:
            c.create_text(xs[0], y - 16, text=f"há {int(agora - self._ts_mt5)}s",
                          fill="#5c728c", font=("Segoe UI", 7))
        if self._ts_cloud:
            c.create_text(xs[2], y - 16, text=f"há {int(agora - self._ts_cloud)}s",
                          fill="#5c728c", font=("Segoe UI", 7))

    def _atualizar_bots_bg(self):
        """Dispara a busca de 'Meus bots' em BACKGROUND (não trava a UI). Lê o
        token aqui no main thread e passa pra thread — evita tocar widget fora dela."""
        try:
            tok = (self.entry_token.get() or "").strip()
        except Exception:
            tok = self.bot_token or ""
        self._bots_ts = 0
        import threading as _th
        _th.Thread(target=self._carregar_meus_bots, args=(tok,), daemon=True).start()

    def _bot_selecionado(self):
        idx = self.combo_bots.current()
        if 0 <= idx < len(self._bots_map):
            return self._bots_map[idx]
        return None

    def _reinstalar_click(self):
        if not self.mql5_dir:
            messagebox.showwarning(APP_NOME, "MT5 não encontrado.")
            return
        bot = self._bot_selecionado()
        if not bot:
            messagebox.showinfo(APP_NOME, "Escolha um bot na lista (aperte ↻ Atualizar se estiver vazia).")
            return
        token = (self.entry_token.get() or "").strip()
        self.lbl_status.config(text=f"Reinstalando {bot.get('nome')}…", fg=COR_MUTED)
        self.root.update()
        ok, msg = reinstalar_bot(token, bot.get("id"), self.mql5_dir)
        if ok:
            messagebox.showinfo(
                APP_NOME,
                f"{bot.get('nome')} reinstalado!\n\nNo MT5: botão direito em "
                "'Expert Advisors' no Navegador → Atualizar, e arraste pro gráfico. "
                "Use conta DEMO primeiro.")
            self.lbl_status.config(text="Bot reinstalado.", fg=COR_VERDE)
        else:
            messagebox.showerror(APP_NOME, f"Não deu pra reinstalar:\n{msg}")
            self.lbl_status.config(text="Falha ao reinstalar.", fg=COR_VERMELHO)

    def _desinstalar_click(self):
        if not self.mql5_dir:
            messagebox.showwarning(APP_NOME, "MT5 não encontrado.")
            return
        bot = self._bot_selecionado()
        if not bot:
            messagebox.showinfo(APP_NOME, "Escolha um bot na lista.")
            return
        if not messagebox.askyesno(
                APP_NOME,
                f"Tirar {bot.get('nome')} do MT5?\n\nO arquivo sai da pasta (some do "
                "Navegador após Atualizar), mas o bot continua no seu histórico — "
                "dá pra reinstalar quando quiser."):
            return
        ok, msg = desinstalar_ea_local(self.mql5_dir, bot.get("filename", ""))
        if ok:
            messagebox.showinfo(
                APP_NOME,
                f"{bot.get('nome')} desinstalado.\n\nNo MT5: botão direito em "
                "'Expert Advisors' → Atualizar pra ele sumir da lista.")
            self.lbl_status.config(text="Bot desinstalado.", fg=COR_VERDE)
        else:
            messagebox.showerror(APP_NOME, f"Não deu pra desinstalar:\n{msg}")

    def _deletar_click(self):
        bot = self._bot_selecionado()
        if not bot:
            messagebox.showinfo(APP_NOME, "Escolha um bot na lista.")
            return
        if not messagebox.askyesno(
                APP_NOME,
                f"DELETAR {bot.get('nome')} de vez?\n\nEle some do seu histórico e sai "
                "do MT5. Essa ação não tem volta."):
            return
        token = (self.entry_token.get() or "").strip()
        ok, msg = deletar_bot(token, bot.get("id"), self.mql5_dir, bot.get("filename", ""))
        if ok:
            # sem popup de "deletado" (era o 3º clique) — o feedback é a lista sumir
            # o bot + o status. Delete = 2 cliques: Deletar -> confirmar.
            self.lbl_status.config(text=f"{bot.get('nome')} deletado.", fg=COR_VERDE)
            self._atualizar_bots_bg()
        else:
            messagebox.showerror(APP_NOME, f"Não deu pra deletar:\n{msg}")

    def _abrir_guia_mt5(self):
        """Janela-guia offline com o caminho pra ver e rodar o bot no MT5.
        Espelha a janela-guia da plataforma; fica sempre disponível pelo ⓘ,
        mesmo que o usuário tenha marcado 'não mostrar mais' lá na web."""
        bot = self._bot_selecionado()
        nome = (bot.get("nome") if bot else "") or "seu bot"
        win = tk.Toplevel(self.root)
        win.title("Como rodar o bot no MT5")
        win.configure(bg=COR_BG)
        win.resizable(False, False)
        try: win.transient(self.root)
        except Exception: pass

        tk.Label(win, text="Falta 1 passo pra o bot rodar",
                 bg=COR_BG, fg=COR_VERDE, font=("Segoe UI", 12, "bold")
                 ).pack(anchor="w", padx=20, pady=(18, 2))
        tk.Label(win, text=f"O {nome} já está instalado no MT5. Pra vê-lo e colocar pra operar:",
                 bg=COR_BG, fg=COR_TEXTO, font=("Segoe UI", 9), wraplength=380,
                 justify="left").pack(anchor="w", padx=20, pady=(0, 10))

        arvore = ("Navigator\n"
                  "  ▾ Expert Advisors\n"
                  "      Advisors\n"
                  "      Examples\n"
                  f"    ▸ {nome}        ← seu bot\n"
                  "\n"
                  "  (botão direito em Expert Advisors)\n"
                  "      ↻ Refresh   ← clique aqui")
        caixa = tk.Frame(win, bg="#0a0f18",
                         highlightbackground=COR_CARD, highlightthickness=1)
        caixa.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(caixa, text=arvore, bg="#0a0f18", fg="#cfd6e0",
                 font=("Consolas", 10), justify="left").pack(anchor="w", padx=12, pady=10)

        passos = ("1) No Navegador do MT5, botão direito em \u201cExpert Advisors\u201d \u2192 Refresh.\n"
                  f"2) Arraste o {nome} pro gráfico do ativo que você quer.")
        tk.Label(win, text=passos, bg=COR_BG, fg=COR_TEXTO, font=("Segoe UI", 9),
                 wraplength=380, justify="left").pack(anchor="w", padx=20, pady=(0, 10))

        tk.Label(win, text="⚠ Se depois do Refresh o bot não aparecer, feche o MT5 e "
                           "abra de novo — ele vai estar lá.",
                 bg=COR_CARD, fg=COR_MUTED, font=("Segoe UI", 8), wraplength=360,
                 justify="left").pack(fill="x", padx=20, pady=(0, 14))

        tk.Button(win, text="Entendi", command=win.destroy,
                  bg=COR_VERDE, fg="#06231a", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=20, pady=6).pack(pady=(0, 16))

    def _toggle_conectar(self):
        if self.rodando:
            self.rodando = False
            self.btn_conectar.config(text="▶  Conectar e monitorar", bg=COR_VERDE)
            self.lbl_status.config(text="Parado.", fg=COR_MUTED)
            # PRESENÇA: avisa a nuvem AGORA (corte imediato da trilha/monitor) e
            # para de reenviar snapshot residual — o bot não está mais operando.
            try:
                toks = list(self._tokens_todos) or ([self.bot_token] if self.bot_token else [])
                threading.Thread(target=sinalizar_parada, args=(toks,), daemon=True).start()
            except Exception:
                pass
            try:
                self._snaps_por_magic.clear()
                self._envio_por_magic.clear()
                self._snap_file_mtime.clear()   # religar relê os arquivos na hora
                self._ev_file_pos.clear()       # v1.30 F2: idem pros eventos
                self._lido_por_magic.clear()
                self._parada_sinalizada.clear()
                self._ev_pendentes.clear()      # v1.34: fila de órfãos zera junto
                self._seguro_aviso_ts.clear()
            except Exception:
                pass
            return
        token = self.entry_token.get().strip()
        if not token:
            messagebox.showwarning(APP_NOME, "Cole o token do painel primeiro.")
            return
        if not self.mql5_dir:
            messagebox.showwarning(APP_NOME, "MT5 não encontrado.")
            return
        self.bot_token = token
        try: salvar_token(token)
        except Exception: pass
        self.rodando = True
        self.btn_conectar.config(text="■  Parar", bg=COR_VERMELHO)
        self.lbl_status.config(text="Conectado. Lendo o robô…", fg=COR_VERDE)
        self.thread = threading.Thread(target=self._loop_monitor, daemon=True)
        self.thread.start()
        # já puxa a lista "Meus bots" do usuário (pelo token) assim que conecta
        try:
            self.root.after(800, self._atualizar_bots_bg)
        except Exception:
            pass

    @staticmethod
    def _magic_de(dados):
        """Lê o magic (int) de dentro de um snapshot/evento. 0 se não houver."""
        try:
            return int(float(str((dados or {}).get("magic", 0)).strip() or 0))
        except Exception:
            return 0

    def _mapear_magic(self, mg, tok):
        """v1.25 — mapeia magic->token NA INSTALAÇÃO: o .mq5 acabou de ser baixado
        pela rota do token `tok` e carrega o magic literal. Grava direto no mapa,
        sem esperar o refresh da nuvem (era a variação de 13-40s do Operar).
        v1.34: magic recém-mapeado DRENA a fila de eventos órfãos dele."""
        try:
            if mg and tok:
                self._token_por_magic[int(mg)] = tok
                self._magic_falhas.pop(int(mg), None)
                dbg(f"magic {mg} mapeado NA INSTALACAO -> token {tok[:8]}…")
                self._set_status(f"🔗 {time.strftime('%H:%M:%S')} magic {mg} mapeado na instalação")
                self._flush_ev_pendentes(int(mg), tok)
        except Exception as e:
            dbg(f"_mapear_magic: {e}")

    # ── v1.34 (a): fila de eventos de magic sem dono ─────────────────
    def _flush_ev_pendentes(self, mg, tok):
        """Magic acabou de ganhar dono: envia (em ordem) os eventos que estavam
        na fila esperando o mapa — nenhum evento real do bot novo se perde."""
        try:
            fila = self._ev_pendentes.pop(mg, None)
            if not fila or not tok:
                return
            agora = time.time()
            enviados = 0
            for ts, ev in fila:
                if (agora - ts) > 120:
                    continue                      # velho demais: descarta
                # v1.35 (c) — via fila de envio (a _loop_eventos faz o POST)
                self._ev_fila_envio.append((tok, ev))
                enviados += 1
            if enviados:
                dbg(f"fila órfã drenada: {enviados} evento(s) do magic {mg} -> token {tok[:8]}…")
                self._set_status(f"📤 {time.strftime('%H:%M:%S')} {enviados} evento(s) na fila entregues (magic {mg})")
        except Exception as e:
            dbg(f"_flush_ev_pendentes: {e}")

    def _evento_rotear(self, ev, mg, origem):
        """v1.34 (a) — roteia um evento SEM NUNCA cair no fallback do token da
        sessão. Com dono no mapa: envia pro token certo. Sem dono: guarda na
        fila curta (máx 50/magic, TTL 120s) esperando o mapa, avisa 1x/60s e
        força a busca do mapa; se o magic for órfão confirmado ou 0 (bot antigo
        sem magic — ambíguo), o evento morre na fila e o aviso manda remover o
        EA do gráfico / reenviar pelo Editor."""
        agora = time.time()
        tok_ev = self._token_por_magic.get(mg) if mg else None
        if tok_ev:
            # v1.35 (b) — COALESCÊNCIA DE RECUSADAS: EA antigo (pré-api v7.19)
            # emite recusada por TICK; mesmo magic+motivo+lado dentro de 30s é
            # repetição sem informação nova — descarta antes da fila.
            if str(ev.get("tipo", "")) == "recusada":
                _ch = f"{mg}|{ev.get('motivo','')}|{ev.get('lado','')}"
                if (agora - self._rec_ult.get(_ch, 0)) < 30:
                    return
                self._rec_ult[_ch] = agora
            # v1.35 (a) — NUNCA faz HTTP aqui (loop de leitura): só enfileira;
            # a _loop_eventos drena em thread própria. Snapshot nunca espera.
            self._ev_fila_envio.append((tok_ev, ev))
            self._set_status(f"📤 {time.strftime('%H:%M:%S')} evento {ev.get('tipo','')} ({origem}, magic {mg})")
            return
        # sem dono: NUNCA usa o token da sessão (era a raiz do histórico alheio)
        if mg:
            fila = self._ev_pendentes.setdefault(mg, [])
            if len(fila) < 50:
                fila.append((agora, ev))
            # limpa itens vencidos da fila
            self._ev_pendentes[mg] = [(t, e) for (t, e) in fila if (agora - t) <= 120]
            self._refresh_por_magic_novo(mg)   # tenta achar o dono já
            orfao = self._magic_falhas.get(mg, 0) >= 3
            if (agora - self._orfao_aviso_ts.get(mg, 0)) >= 60:
                self._orfao_aviso_ts[mg] = agora
                if orfao:
                    self._set_status(f"⚠ EA órfão (magic {mg}) OPERANDO — evento {ev.get('tipo','')} descartado; remova o EA do gráfico do MT5")
                else:
                    self._set_status(f"⏳ evento {ev.get('tipo','')} na fila (magic {mg} ainda sem dono — buscando mapa)")
            dbg(f"evento sem dono ({origem}): magic {mg} tipo {ev.get('tipo','')} -> fila ({len(self._ev_pendentes.get(mg, []))})")
        else:
            # magic 0 = ambíguo (bot antigo sem magic): descarta com aviso
            if (agora - self._orfao_aviso_ts.get(0, 0)) >= 60:
                self._orfao_aviso_ts[0] = agora
                self._set_status("⚠ evento sem magic descartado — bot antigo: reenvie pelo Editor pra monitorar")
            dbg(f"evento sem magic descartado ({origem}): tipo {ev.get('tipo','')}")

    def _refresh_por_magic_novo(self, mg):
        """v1.25 — magic desconhecido apareceu num snapshot: tenta atualizar o
        mapa (throttle próprio de 2s, v1.23). Se depois de 3 tentativas o magic
        segue sem dono, marca ÓRFÃO (bot deletado na nuvem mas EA ainda no
        gráfico): para de gastar rede (1 tentativa a cada 5min) e avisa 1x/min."""
        agora = time.time()
        falhas = self._magic_falhas.get(mg, 0)
        if falhas >= 3:
            # órfão: aviso claro, sem spam; retry de rede só a cada 5 min
            if (agora - self._orfao_aviso_ts.get(mg, 0)) >= 60:
                self._orfao_aviso_ts[mg] = agora
                self._set_status(f"⚠️ EA órfão no gráfico (magic {mg}) — esse bot não existe mais na nuvem; remova do gráfico do MT5")
            if (agora - getattr(self, "_ult_refresh_magic", 0)) >= 300:
                self._ult_refresh_magic = agora
                self._refrescar_tokens()
                if mg in self._token_por_magic:
                    self._magic_falhas.pop(mg, None)
                    self._flush_ev_pendentes(mg, self._token_por_magic.get(mg))
            return
        if (agora - getattr(self, "_ult_refresh_magic", 0)) >= 2:
            self._ult_refresh_magic = agora
            self._set_status(f"⏳ {time.strftime('%H:%M:%S')} magic {mg} novo — atualizando mapa")
            self._refrescar_tokens()
            if mg in self._token_por_magic:
                self._magic_falhas.pop(mg, None)
                self._flush_ev_pendentes(mg, self._token_por_magic.get(mg))
            else:
                self._magic_falhas[mg] = falhas + 1

    def _snapshot_inicial(self, logs):
        """Lê o final dos logs e guarda o ÚLTIMO snapshot de CADA bot (por magic),
        sem disparar eventos antigos — pra os cards ficarem online já no boot, sem
        esperar a próxima barra. MULTI-BOT: um log pode ter snapshots de vários
        bots (vários gráficos); cada magic guarda o seu."""
        for log in logs[:3]:
            try:
                tam = os.path.getsize(log)
                ini = max(0, tam - 65536)        # últimos 64 KB
                novas, _ = ler_novas_linhas(log, ini)
            except Exception:
                continue
            for linha in novas:
                tipo, dados = parse_linha_log(linha)
                if tipo == "snapshot":
                    mg = self._magic_de(dados)   # 0 se sem magic (fallback p/ sessão)
                    self._snaps_por_magic[mg] = dados
                    # v1.26: benefício da dúvida no boot — envia 1x; se o bot não
                    # escrever nada novo em 35s, o watchdog sinaliza a parada.
                    self._lido_por_magic[mg] = time.time()
        return bool(self._snaps_por_magic)

    def _conector_minimizar(self):
        """Ao pegar um job de validação, minimiza pra a plataforma (Fab/guia)
        ficar sozinha na tela — e começa a vigiar o sinal 'subir' da nuvem, que
        chega quando o usuário aperta 'Entendi' na guia."""
        try:
            self.root.after(0, self.root.iconify)
        except Exception:
            pass
        if not getattr(self, "_watch_ativo", False):
            self._watch_ativo = True
            threading.Thread(target=self._watch_subir_conector, daemon=True).start()

    def _trazer_frente(self):
        """Restaura a janela e traz pra frente (nativo consegue; a web não)."""
        def _f():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.after(400, lambda: self.root.attributes("-topmost", False))
                try: self.root.focus_force()
                except Exception: pass
            except Exception:
                pass
        try:
            self.root.after(0, _f)
        except Exception:
            pass

    def _watch_subir_conector(self):
        """Vigia o sinal 'subir' por até ~2min. Quando a plataforma pede (Entendi),
        traz o conector pra frente. Se ninguém pedir nesse tempo, volta assim mesmo
        (fallback), pra ele nunca ficar preso minimizado."""
        import time as _t
        fim = _t.time() + 130
        try:
            while self.rodando and _t.time() < fim:
                try:
                    if checar_subir_conector(self.bot_token):
                        self._trazer_frente()
                        return
                except Exception:
                    pass
                _t.sleep(0.5)   # vigia rápida: alvo ~1s do clique "Entendi" até subir
            self._trazer_frente()   # fallback: destrava sozinho
        finally:
            self._watch_ativo = False

    def _refrescar_tokens(self):
        """MULTI-BOT: baixa da nuvem os tokens de TODOS os bots do usuário, pra
        validar qualquer um que tenha .mq5 pendente — não só o token colado. É o
        que faz o 'um clique' funcionar pra qualquer bot e conserta o erro de a
        validação pedir um token que a janela não estava vigiando."""
        self._tokens_ts = time.time()
        try:
            ok, lst = listar_tokens_do_usuario(self.bot_token)
            if ok and isinstance(lst, list):
                toks = []
                mapa = {}
                for it in lst:
                    if not isinstance(it, dict):
                        continue
                    t = (it.get("bot_token") or "").strip()
                    if not t or t in toks:
                        continue
                    toks.append(t)
                    try:
                        mg = int(it.get("magic_number") or 0)
                    except Exception:
                        mg = 0
                    if mg:
                        mapa[mg] = t   # magic -> token, pra rotear o snapshot certo
                # garante o token da sessão na lista (mesmo se a nuvem demorar)
                if self.bot_token and self.bot_token not in toks:
                    toks.insert(0, self.bot_token)
                if toks:
                    self._tokens_todos = toks
                if mapa:
                    novos = set(mapa) - set(self._token_por_magic)
                    self._token_por_magic = mapa
                    dbg(f"multi-bot: {len(toks)} token(s), {len(mapa)} magic(s) mapeado(s)")
                    # v1.34: magics que acabaram de ganhar dono drenam a fila órfã
                    for mg in novos:
                        try:
                            self._magic_falhas.pop(mg, None)
                            self._flush_ev_pendentes(mg, mapa.get(mg))
                        except Exception:
                            pass
        except Exception as e:
            dbg(f"_refrescar_tokens: {e}")

    def injetar_token(self, tok):
        """SINGLE-INSTANCE: chamada quando OUTRA tentativa de abrir o conector
        chega (via protocolo bottested://). Em vez de abrir outra janela, injeta o
        token novo NESTA janela, conecta se ainda não estiver rodando, força um
        refresh dos tokens multi-bot (pra já incluir o bot novo) e traz a janela
        pra frente."""
        def _apl():
            try:
                t = (tok or "").strip()
                if t:
                    try:
                        self.entry_token.delete(0, "end")
                        self.entry_token.insert(0, t)
                    except Exception:
                        pass
                    try: salvar_token(t)
                    except Exception: pass
                    self.bot_token = t
                    if not self.rodando and self.mql5_dir:
                        self._toggle_conectar()   # mesmo fluxo do auto-conectar
                    self._tokens_ts = 0           # força refresh imediato no loop
                    # Cenário A: bot recém-enviado deve APARECER na lista na hora.
                    # A busca (rede) roda em background pra não travar a UI.
                    self._bots_ts = 0
                    import threading as _th
                    _th.Thread(target=self._carregar_meus_bots,
                               args=(t,), daemon=True).start()
                self._trazer_frente()
            except Exception as e:
                dbg(f"injetar_token: {e}")
        try:
            self.root.after(0, _apl)
        except Exception:
            pass

    def _loop_monitor(self):
        dbg(f"=== conectar | mql5={self.mql5_dir}")
        # v1.26: rede pesada (validação/pendentes/refreshes) em thread própria —
        # este loop fica livre pra ler arquivo/log e enviar a cada 1.5s.
        threading.Thread(target=self._loop_rede, daemon=True).start()
        threading.Thread(target=self._loop_eventos, daemon=True).start()  # v1.35

        # Primeira passada: captura o último snapshot de CADA bot já presente no
        # log (pra ficar online em segundos), monta o mapa magic->token e marca a
        # posição de cada log no fim, pra não reprocessar eventos antigos.
        try:
            self._refrescar_tokens()   # já deixa o mapa magic->token pronto
            logs0 = achar_logs_mt5(self.mql5_dir)
            dbg(f"logs achados: {len(logs0)} -> {[os.path.basename(l) for l in logs0[:2]]}")
            if self._snapshot_inicial(logs0):
                dbg(f"snapshots iniciais (por magic): {list(self._snaps_por_magic.keys())}")
            else:
                dbg("nenhum snapshot no fim do log ainda (espera a proxima barra)")
            for log in logs0[:3]:
                try:
                    self._log_pos[log] = os.path.getsize(log)
                except Exception:
                    self._log_pos[log] = 0
        except Exception as e:
            dbg(f"erro no primeiro scan: {e}")

        while self.rodando:
            try:
                # v1.24 — ARQUIVO DEDICADO primeiro: o EA (api v6.36+) grava o
                # snapshot em <MQL5>/Files/bt_snap_<magic>.txt com flush imediato.
                # Chega em <=1.5s, SEM depender do buffering do log do MT5 (a
                # causa do 22s-2min15s). O log segue abaixo como fallback (bots
                # antigos) e pros eventos aberto/fechado.
                # v1.30 FASE 2 — EVENTOS por arquivo dedicado bt_ev_<magic>.txt
                # (api v6.97+): canal CONFIAVEL pra BabyMachine. Cada abertura/
                # fechamento chega em <=1.5s com flush imediato, sem depender do
                # buffer do log (que atrasava/perdia eventos na rajada). O log
                # segue abaixo como fallback pra bots antigos.
                # v1.34 (a) — roteamento estrito: evento sem dono no mapa NUNCA
                # cai no token da sessão (vai pra fila / é descartado com aviso).
                try:
                    for ev in ler_eventos_arquivo(self.mql5_dir, self._ev_file_pos):
                        self._ts_mt5 = time.time()          # v1.31 trilha: MT5 vivo
                        mg_ev = self._magic_de(ev)
                        self._evento_rotear(ev, mg_ev, "arquivo")
                except Exception as _e_ev:
                    dbg(f"ler_eventos_arquivo: {_e_ev}")

                for dados in ler_snapshots_arquivo(self.mql5_dir, self._snap_file_mtime):
                    self._ts_mt5 = time.time()              # v1.31 trilha: MT5 vivo
                    mg = self._magic_de(dados)
                    # FIM DE VIDA (v1.26): o EA escreveu BOTTESTED_FIM no OnDeinit
                    # (removido do gráfico / gráfico fechado) -> parada NA HORA.
                    if dados.get("_fim"):
                        self._snaps_por_magic.pop(mg, None)
                        self._envio_por_magic.pop(mg, None)
                        self._lido_por_magic.pop(mg, None)
                        if mg not in self._parada_sinalizada:
                            self._parada_sinalizada.add(mg)
                            tok_f = self._token_por_magic.get(mg)
                            if tok_f:
                                threading.Thread(target=sinalizar_parada,
                                                 args=([tok_f],), daemon=True).start()
                            self._set_status(f"🛑 {time.strftime('%H:%M:%S')} bot saiu do gráfico (magic {mg}) — parada sinalizada")
                        continue
                    # RELIGAR (v1.25): gap >25s nas escritas do arquivo = o bot
                    # saiu e voltou -> zera o throttle e envia no MESMO ciclo
                    # (era a causa do religar em 32-42s).
                    if dados.pop("_religou", None) and mg:
                        self._envio_por_magic.pop(mg, None)
                        self._set_status(f"🔁 {time.strftime('%H:%M:%S')} bot religou (magic {mg}) — enviando já")
                    self._snaps_por_magic[mg] = dados
                    self._lido_por_magic[mg] = time.time()   # v1.26: leitura FRESCA
                    self._parada_sinalizada.discard(mg)
                    self._set_status(f"📥 {time.strftime('%H:%M:%S')} snapshot lido (arquivo, magic {mg})")
                    # magic novo (bot recém-arrastado) -> atualiza o mapa JÁ;
                    # magic órfão -> aviso 1x/min, sem gastar rede (v1.25).
                    if mg and mg not in self._token_por_magic:
                        self._refresh_por_magic_novo(mg)

                logs = achar_logs_mt5(self.mql5_dir)
                for log in logs[:3]:
                    if log not in self._log_pos:
                        # log novo (ex: virou o dia): começa do fim, sem
                        # reprocessar histórico
                        try:
                            self._log_pos[log] = os.path.getsize(log)
                        except Exception:
                            self._log_pos[log] = 0
                        continue
                    pos = self._log_pos[log]
                    novas, nova_pos = ler_novas_linhas(log, pos)
                    self._log_pos[log] = nova_pos
                    if novas:
                        dbg(f"{os.path.basename(log)}: {len(novas)} linha(s) nova(s)")
                    for linha in novas:
                        tipo, dados = parse_linha_log(linha)
                        if tipo:
                            self._ts_mt5 = time.time()      # v1.31 trilha: MT5 vivo
                        if tipo == "evento":
                            # roteia o evento pro token do bot certo (pelo magic).
                            mg = self._magic_de(dados)
                            # v1.30 F2 — ANTI-DUPLICATA: se este bot já grava eventos
                            # em arquivo (bt_ev_<magic>.txt existe), o arquivo é a
                            # fonte da verdade e o log vira ruído duplicado -> ignora.
                            # Bots antigos (sem arquivo) seguem pelo log, intactos.
                            try:
                                _ev_arq = os.path.join(self.mql5_dir, "Files",
                                                       f"bt_ev_{mg}.txt")
                                if mg and os.path.exists(_ev_arq):
                                    continue
                            except Exception:
                                pass
                            # v1.34 (a) — sem fallback pro token da sessão
                            self._evento_rotear(dados, mg, "log")
                        elif tipo == "snapshot":
                            # guarda o último snapshot de CADA bot separadamente.
                            mg = self._magic_de(dados)
                            self._snaps_por_magic[mg] = dados
                            self._lido_por_magic[mg] = time.time()   # v1.26
                            self._parada_sinalizada.discard(mg)
                            # DIAGNÓSTICO na tela: mostra quando LEU o snapshot (compare
                            # com a hora que você arrastou pra ver se o atraso é aqui).
                            self._set_status(f"📥 {time.strftime('%H:%M:%S')} snapshot lido (log, magic {mg})")
                            # magic novo -> atualiza o mapa JÁ; órfão -> aviso (v1.25).
                            if mg and mg not in self._token_por_magic:
                                self._refresh_por_magic_novo(mg)

                # snapshot: manda o estado de CADA bot pro token certo (por magic).
                # POR-BOT: um bot NOVO (nunca enviado) vai IMEDIATAMENTE; depois disso,
                # cada bot respeita o INTERVALO_SNAPSHOT (custo baixo em regime). Assim o
                # Operar acende em segundos ao arrastar, sem esperar o ciclo global.
                agora = time.time()
                enviados = 0
                tinha_sem_magic = False
                tinha_magic = False
                for mg, snap in list(self._snaps_por_magic.items()):
                    if mg == 0:
                        tinha_sem_magic = True
                        continue   # sem magic: ambíguo -> não manda
                    tinha_magic = True
                    # WATCHDOG (v1.26): dado VELHO não sustenta presença. O EA
                    # escreve a cada 10s; >35s sem leitura nova = saiu do gráfico
                    # (ou MT5 fechou/caiu). Para de reenviar e sinaliza a parada
                    # 1x — era o reenvio do cache que segurava o OPERANDO aceso
                    # (desligar errático de até 3min).
                    if (agora - self._lido_por_magic.get(mg, agora)) > 35:
                        self._snaps_por_magic.pop(mg, None)
                        if mg not in self._parada_sinalizada:
                            self._parada_sinalizada.add(mg)
                            tok_w = self._token_por_magic.get(mg)
                            if tok_w and mg in self._envio_por_magic:
                                threading.Thread(target=sinalizar_parada,
                                                 args=([tok_w],), daemon=True).start()
                                self._set_status(f"💤 {time.strftime('%H:%M:%S')} bot silencioso >35s (magic {mg}) — parada sinalizada")
                        continue
                    tok = self._token_por_magic.get(mg)
                    if not tok:
                        # v1.34 (b) — aviso de snapshot SEGURADO nunca silencia:
                        # repete 1x/60s por magic enquanto o snapshot estiver
                        # retido, seja aguardando o mapa ou órfão confirmado.
                        if (agora - self._seguro_aviso_ts.get(mg, 0)) >= 60:
                            self._seguro_aviso_ts[mg] = agora
                            if self._magic_falhas.get(mg, 0) >= 3:
                                self._set_status(f"⚠ EA órfão (magic {mg}) — snapshot SEGURADO; remova o EA do gráfico do MT5")
                            else:
                                self._set_status(f"⏳ {time.strftime('%H:%M:%S')} snapshot SEGURADO — magic {mg} sem dono ainda ({len(self._token_por_magic)} mapeados)")
                        continue
                    self._seguro_aviso_ts.pop(mg, None)
                    if (agora - self._envio_por_magic.get(mg, 0)) >= INTERVALO_SNAPSHOT:
                        primeiro = mg not in self._envio_por_magic
                        if enviar_snapshot(tok, snap):
                            self._ts_cloud = time.time()    # v1.31 trilha: nuvem aceitou
                            self._envio_por_magic[mg] = agora
                            enviados += 1
                            if primeiro:
                                # v1.26 — marco do LIGAR: compare esta hora com a do
                                # drag e a do Operar acender. Se o 🚀 sai rápido e o
                                # Operar demora, a gordura está no polling do front.
                                self._set_status(f"🚀 {time.strftime('%H:%M:%S')} 1º snapshot enviado (magic {mg})")
                if enviados:
                    self._set_status(f"✓ {time.strftime('%H:%M:%S')} Snapshot enviado ({enviados} bot)")
                elif tinha_sem_magic and not tinha_magic:
                    self._set_status("Bot antigo (sem magic) — reenvie pelo Editor pra monitorar")

                # "Enviar pro MT5", refresh de tokens e Meus bots rodam no
                # _loop_rede (thread própria, v1.26) — este loop SÓ lê e envia.
            except Exception as e:
                dbg(f"erro no loop: {e}")
                self._set_status("Erro de leitura (continua tentando)…")
            time.sleep(1.5)

    def _loop_eventos(self):
        """v1.35 (a) — ENVIO DE EVENTOS EM THREAD PRÓPRIA: drena a fila que o
        loop de leitura alimenta e faz os POSTs. Um POST lento (Railway frio,
        rede ruim) ou uma rajada de eventos nunca mais atrasa o snapshot."""
        while self.rodando:
            try:
                try:
                    tok, ev = self._ev_fila_envio.popleft()
                except IndexError:
                    time.sleep(0.2)
                    continue
                if enviar_evento(tok, ev.get("tipo", "info"), ev):
                    self._ts_cloud = time.time()
            except Exception as e:
                dbg(f"loop eventos: {e}")
                time.sleep(0.5)

    def _loop_rede(self):
        """v1.26 — REDE PESADA em thread própria: validação de pendentes (1 GET
        por token a cada 5s), refresh de tokens (30s) e da lista Meus bots (20s).
        Antes rodava DENTRO do loop de leitura: com vários bots, as chamadas
        sequenciais bloqueavam a leitura do snapshot por segundos e atrasavam o
        Operar. Agora o loop de leitura mantém o ciclo estável de 1.5s."""
        while self.rodando:
            try:
                agora = time.time()
                # atualiza a lista de tokens do usuário de tempos em tempos
                # v1.28: 30s -> 8s. Bot novo criado no Enviar = token novo; o front
                # espera ~25s pelo sinal de vida do token e o refresh de 30s às
                # vezes chegava DEPOIS ("could not reach the connector" no envio,
                # resolvia no retry). Com 8s a descoberta cabe folgada na janela.
                if (agora - self._tokens_ts) >= 8 or not self._tokens_todos:
                    self._refrescar_tokens()
                # refresh periódico da lista 'Meus bots' (online/offline + bots
                # novos) a cada ~20s; atualiza a UI via after.
                if (agora - getattr(self, "_bots_ts", 0)) >= 20:
                    self._bots_ts = agora
                    try:
                        self._carregar_meus_bots(self.bot_token)
                    except Exception as _e:
                        dbg(f"refresh meus-bots loop: {_e}")
                # MULTI-BOT v1.29: PRESENÇA EM LOTE — bate o coração de TODOS os
                # tokens numa requisição só (/mt5/presenca) e o servidor devolve
                # quais têm trabalho pendente; o validar_pendente individual roda
                # SÓ nesses. Antes: 1 GET por token em série — com 19 bots a
                # varredura passava de 25s e bot novo nascia invisível pro front.
                alvos = self._tokens_todos or [self.bot_token]
                try:
                    rl = requests.post(f"{API_BASE}/mt5/presenca",
                                       json={"tokens": alvos}, timeout=8)
                    pend = (rl.json() or {}).get("pendentes") or []
                    alvos = [t for t in alvos if t in set(pend)]
                except Exception as _e:
                    dbg(f"presenca lote: {_e}")   # servidor antigo? cai no modo série
                for tok in alvos:
                    if not self.rodando:
                        break
                    if not tok:
                        continue
                    try:
                        houve, aprovado, msg = validar_pendente(
                            tok, self.mql5_dir,
                            ao_iniciar=self._conector_minimizar,
                            ao_instalar=lambda mg, _t=tok: self._mapear_magic(mg, _t))
                        if houve:
                            self._set_status(
                                ("✓ Bot aprovado no MT5" if aprovado
                                 else "✗ Bot reprovado na validação")
                                + (f" — {msg[:50]}" if msg else ""))
                    except Exception as e:
                        dbg(f"validar_pendente({tok[:8]}…) no loop: {e}")
            except Exception as e:
                dbg(f"erro no loop de rede: {e}")
            time.sleep(5)

    def _set_status(self, txt):
        try:
            self.root.after(0, lambda: self.lbl_status.config(
                text=txt, fg=COR_VERDE))
        except Exception:
            pass


def _tentar_ser_unico(proto_arg):
    """SINGLE-INSTANCE via socket local.
      • Se conseguir bindar a porta -> esta é a 1ª janela (dona): devolve o
        socket-servidor (o main() vai escutar nele por novas tentativas).
      • Se NÃO conseguir (porta ocupada) -> JÁ HÁ um conector aberto: manda a URL
        do protocolo (com o token novo) pra ele e devolve None -> esta instância
        deve sair sem abrir janela nenhuma.
    Não usa SO_REUSEADDR de propósito: no Windows o 2º bind falha quando a porta
    está em uso, que é exatamente o sinal que a gente quer."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", _LOCK_PORT))
        srv.listen(5)
        return srv                      # sou a dona
    except OSError:
        # já há um conector rodando -> repassa a URL/token pra ele e sai
        try:
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(2)
            c.connect(("127.0.0.1", _LOCK_PORT))
            c.sendall(("URL:" + (proto_arg or "")).encode("utf-8", "ignore"))
            c.close()
        except Exception as e:
            dbg(f"single-instance: falha ao repassar pro conector aberto: {e}")
        try: srv.close()
        except Exception: pass
        return None


def _servir_tokens(srv, app):
    """Thread da janela DONA: aceita conexões das novas tentativas de abrir o
    conector. Cada uma manda 'URL:<bottested://…?token=…>' — a gente extrai o
    token e injeta na janela existente (que se traz pra frente). Sem token (aberto
    à mão), só traz a janela pra frente."""
    while True:
        try:
            conn, _ = srv.accept()
        except Exception:
            break
        try:
            conn.settimeout(2)
            data = conn.recv(8192).decode("utf-8", "ignore")
            conn.close()
        except Exception:
            continue
        raw = ""
        if data.startswith("URL:"):
            raw = data[4:].strip()
        try:
            tok = extrair_token_do_protocolo([raw]) if raw else ""
        except Exception:
            tok = ""
        dbg(f"single-instance: nova tentativa recebida | token: {'sim' if tok else 'nao'}")
        try:
            app.injetar_token(tok)      # injeta e traz pra frente (sem 2ª janela)
        except Exception as e:
            dbg(f"_servir_tokens: {e}")


def main():
    if tk is None:
        print("tkinter não disponível neste ambiente.")
        return
    # registra o protocolo bottested:// (1ª execução) — deixa a plataforma
    # abrir este conector sozinha no "Enviar pro MT5"
    try:
        registrar_protocolo()
    except Exception:
        pass
    # v1.30 — autostart obrigatório/silencioso/auto-curável: registra a cada
    # abertura (se algo remover a entrada, ela volta). Reboot nunca mais deixa
    # a plataforma cega.
    try:
        registrar_autostart()
    except Exception:
        pass
    argv = sys.argv[1:]
    via_protocolo = any(str(a).lower().startswith("bottested:") for a in argv)
    token_url = extrair_token_do_protocolo(argv)
    proto_arg = next((str(a) for a in argv
                      if str(a).lower().startswith("bottested:")), "")
    if via_protocolo:
        dbg(f"aberto via protocolo: {argv} | token na URL: {'sim' if token_url else 'nao'}")

    # SINGLE-INSTANCE: se já houver um conector aberto, repassa o token pra ele e
    # sai — nunca abre uma 2ª janela.
    srv = _tentar_ser_unico(proto_arg)
    if srv is None:
        dbg("single-instance: já há um conector aberto — token repassado, saindo.")
        return

    root = tk.Tk()
    app = ConectorApp(root, via_protocolo=via_protocolo, token_inicial=token_url)
    # escuta novas tentativas de abrir (elas trazem esta janela pra frente + token)
    threading.Thread(target=_servir_tokens, args=(srv, app), daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
