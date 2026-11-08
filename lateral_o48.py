"""ORDEM 048 — cartão "Rompimento de Lateralização" (Experimental · teste em sombra) e os bots do teste.
R0 da O44 (caixa de 12 barras, amplitude ≤ 3 ATR, tentativa prévia, fechamento além do nível, superação ≥ 1 tick só na barra seguinte,
stop 2 ATR, saída pelo canal EMA20 do TF escolhido; M1/M5 fora da decisão; sem o corte da O46). Os bots NÃO enviam ordens: o leitor no
computador do MT5 lê as cotações (bid/ask) do terminal e mantém POSIÇÕES VIRTUAIS — uma por bot — e devolve eventos para o relatório.

Fluxo: cartão (vitrine) → Criar bot → Enviar ao MT5 (o bot fica "enviado" até o leitor confirmar) → o leitor confirma no terminal
ID do bot, símbolo efetivo da corretora, timeframe, versão da regra e modo sombra, com cotação lida → "Conectado" → 1 h de verificação
técnica → uma semana de coleta com o MESMO início e fim para os 3 TF de cada ativo → relatório por bot.
Isolado da campanha: tabelas próprias (sql/0025), rotas próprias (/lateral/…), nenhuma tabela/rota existente é alterada.
Visível só para o usuário de teste (env BT_CARD_TESTE_USER), como o card MASTER."""
import os, hmac, hashlib, secrets, datetime as _dt
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

VERSAO_REGRA = "lateral-tf-0.1 (R0 da O44) · leitor-o48"
ATIVOS = ("XAUUSD", "BTCUSD"); TFS = ("M15", "M30", "H1")
VERIFICACAO_H = 1; SEMANA_D = 7; MAX_EVENTOS_LOTE = 500
CARD_ID = "lateral_r0"
CARD = {
    "id": CARD_ID, "nome": "Rompimento de Lateralização", "emoji": "\U0001f9ea", "categoria": "teste", "nivel": "interno",
    "selo": "Experimental · teste em sombra",
    "desc": ("Caixa de 12 barras com amplitude de até 3 ATR, tentativa prévia e fechamento além do suporte ou da resistência. "
             "A entrada só vale na barra seguinte, quando o preço supera por pelo menos um tick o extremo da barra de rompimento; "
             "tocar não abre. Stop de 2 ATR e saída pelo canal EMA20 no timeframe escolhido. M1/M5 fora da decisão. "
             "Modo sombra: posições virtuais com bid/ask do terminal, nenhuma ordem. Resultados ainda NÃO medidos."),
    "tags": ["EXPERIMENTAL", "SOMBRA"], "mercados": ["XAUUSD", "BTCUSD"], "timeframes": list(TFS),
    "regra_versao": VERSAO_REGRA,
    # nunca herda medição: sem taxa de acerto, sem célula aprovada, sem ranking
    "melhor_combo": None, "escada_tf": {}, "celulas_aprovadas": [], "aprovacao": "em_medicao", "medida": False, "casa": False,
    "cor_destaque": None, "sharpe_medio": None, "pf_medio": None, "retorno_medio": None, "winrate_medio": None, "combos": 0, "forte_pct": 0,
    "top_ativos": ["XAUUSD", "BTCUSD"], "lateral": True,
}


def _agora(): return _dt.datetime.now(_dt.timezone.utc)
def _iso(x): return x.isoformat() if x else None
def _hash(ch): return hashlib.sha256(("lateral-o48|" + ch).encode()).hexdigest()


def _parse(t):
    if not t: return None
    if isinstance(t, _dt.datetime): return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)
    s = str(t).replace("Z", "+00:00")
    try: d = _dt.datetime.fromisoformat(s)
    except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)


def estado_publico(b, agora=None):
    """estado mostrado ao usuário (derivado dos horários): criado · enviado (aguardando o terminal) · conectado (verificação técnica) ·
    coletando · semana encerrada · parado. "Conectado" só existe depois que o leitor confirmou a leitura de cotações do terminal."""
    agora = agora or _agora(); e = b.get("estado")
    if e == "parado": return "parado"
    if e in ("criado", "enviado"): return e
    ini, fim = _parse(b.get("coleta_inicio")), _parse(b.get("coleta_fim"))
    if ini is None or agora < ini: return "conectado"
    if fim is not None and agora >= fim: return "semana encerrada"
    return "coletando"


class _Criar(BaseModel):
    ativos: List[str]
    tfs: List[str]
    user_id: Optional[str] = None


class _Ids(BaseModel):
    bot_ids: List[int]
    user_id: Optional[str] = None


class _Rel(BaseModel):
    bot_id: Optional[int] = None
    user_id: Optional[str] = None


class _LeitorBots(BaseModel):
    chave: str


class _LeitorConfirma(BaseModel):
    chave: str
    bot_id: int
    simbolo_efetivo: str
    timeframe: str
    regra_versao: str
    modo: str
    cotacao: dict = {}
    terminal: dict = {}


class _LeitorEventos(BaseModel):
    chave: str
    bot_id: int
    eventos: list = []


def criar_router(sb_admin, sessao_user_id, relogio=None):
    """sb_admin(): cliente Supabase (service role) ou None; sessao_user_id(authorization) -> user_id (levanta 401 sem sessão).
    relogio(): horário UTC (padrão: agora; os testes passam o relógio do terminal simulado)."""
    r = APIRouter(); _now = relogio or _agora

    def _sb():
        sb = sb_admin()
        if sb is None: raise HTTPException(status_code=503, detail="Supabase indisponível")
        return sb

    def _uid(authorization, uid_corpo=None):
        uid = sessao_user_id(authorization)
        if (uid_corpo or "").strip() and uid_corpo.strip() != uid: raise HTTPException(status_code=403, detail="user_id divergente da sessão")
        alvo = (os.environ.get("BT_CARD_TESTE_USER") or "").strip()
        if not alvo or not hmac.compare_digest(str(uid), alvo): raise HTTPException(status_code=404, detail="não encontrado")   # sem oráculo do cartão
        return uid

    def _meus(sb, uid, ids=None):
        q = sb.table("lateral_bots").select("*").eq("user_id", uid)
        bots = q.execute().data or []
        return [b for b in bots if ids is None or int(b["id"]) in set(int(i) for i in ids)]

    def _pub(b):
        x = {k: b.get(k) for k in ("id", "nome", "ativo", "tf", "regra_versao", "modo", "criado_em", "enviado_em", "conectado_em", "parado_em",
                                   "confirmacao", "coleta_inicio", "coleta_fim", "ultimo_contato")}
        x["estado"] = estado_publico(b, _now()); return x

    @r.post("/lateral/cartao")
    def cartao(p: _Rel, authorization: str = Header("")):
        _uid(authorization, p.user_id); return CARD

    @r.post("/lateral/bots/criar")
    def criar(p: _Criar, authorization: str = Header("")):
        uid = _uid(authorization, p.user_id); sb = _sb()
        ats = [a for a in p.ativos if a in ATIVOS]; tfs = [t for t in p.tfs if t in TFS]
        if not ats or not tfs: raise HTTPException(status_code=422, detail="escolha XAUUSD/BTCUSD e M15/M30/H1")
        ativos = {(b["ativo"], b["tf"]): b for b in _meus(sb, uid) if b.get("estado") != "parado"}
        criados, existentes = [], []
        for a in ats:
            for t in tfs:
                if (a, t) in ativos: existentes.append(_pub(ativos[(a, t)])); continue
                nome = f"{a[:3]} {t} · Lateral R0"
                row = sb.table("lateral_bots").insert({"user_id": uid, "nome": nome, "ativo": a, "tf": t, "regra_versao": VERSAO_REGRA, "modo": "sombra", "estado": "criado"}).execute().data
                criados.append(_pub(row[0]))
        return {"ok": True, "criados": criados, "ja_existiam": existentes}

    @r.post("/lateral/bots/listar")
    def listar(p: _Rel, authorization: str = Header("")):
        uid = _uid(authorization, p.user_id); sb = _sb()
        ch = sb.table("lateral_chaves").select("criada_em").eq("user_id", uid).execute().data or []
        return {"bots": [_pub(b) for b in sorted(_meus(sb, uid), key=lambda b: int(b["id"]))], "chave_do_leitor": bool(ch), "chave_criada_em": ch[0]["criada_em"] if ch else None,
                "cartao": {"id": CARD_ID, "regra_versao": VERSAO_REGRA}}

    @r.post("/lateral/bots/enviar")
    def enviar(p: _Ids, authorization: str = Header("")):
        uid = _uid(authorization, p.user_id); sb = _sb(); out = []
        for b in _meus(sb, uid, p.bot_ids):
            if b["estado"] == "criado":
                sb.table("lateral_bots").update({"estado": "enviado", "enviado_em": _iso(_now())}).eq("id", b["id"]).eq("user_id", uid).execute()
            out.append(b["id"])
        return {"ok": True, "enviados": out, "aviso": "o bot fica 'enviado' até o leitor no computador do MT5 confirmar a leitura de cotações"}

    @r.post("/lateral/bots/parar")
    def parar(p: _Ids, authorization: str = Header("")):
        uid = _uid(authorization, p.user_id); sb = _sb(); out = []
        for b in _meus(sb, uid, p.bot_ids):                                              # só bots DESTE cartão (tabela própria): nada da campanha é tocado
            if b["estado"] != "parado":
                sb.table("lateral_bots").update({"estado": "parado", "parado_em": _iso(_now())}).eq("id", b["id"]).eq("user_id", uid).execute(); out.append(b["id"])
        return {"ok": True, "parados": out}

    @r.post("/lateral/chave/gerar")
    def gerar_chave(p: _Rel, authorization: str = Header("")):
        uid = _uid(authorization, p.user_id); sb = _sb(); ch = "lat_" + secrets.token_urlsafe(24)
        sb.table("lateral_chaves").upsert({"user_id": uid, "chave_hash": _hash(ch), "criada_em": _iso(_now())}, on_conflict="user_id").execute()
        return {"ok": True, "chave": ch, "aviso": "copie agora: a chave não é mostrada de novo. Ela fica só no computador do MT5 (configuração do leitor)."}

    @r.post("/lateral/relatorio")
    def relatorio(p: _Rel, authorization: str = Header("")):
        uid = _uid(authorization, p.user_id); sb = _sb(); bots = _meus(sb, uid, [p.bot_id] if p.bot_id else None); out = {}
        for b in bots:
            evs, ini = [], 0
            while ini < 20000:
                lote = (sb.table("lateral_eventos").select("chave,tipo,t_evento,payload").eq("bot_id", b["id"]).order("id").range(ini, ini + 999).execute().data or [])
                evs += lote
                if len(lote) < 1000: break
                ini += 1000
            out[str(b["id"])] = {"bot": _pub(b), "eventos": evs}
        return {"ok": True, "bots": out, "gerado_em": _iso(_now())}

    # ── rotas do LEITOR (computador do MT5): autenticadas pela chave do leitor ──
    def _uid_chave(ch):
        if not ch or len(ch) < 10: raise HTTPException(status_code=401, detail="chave do leitor inválida")
        rows = _sb().table("lateral_chaves").select("user_id,chave_hash").eq("chave_hash", _hash(ch)).execute().data or []
        if not rows or not hmac.compare_digest(rows[0]["chave_hash"], _hash(ch)): raise HTTPException(status_code=401, detail="chave do leitor inválida")
        return rows[0]["user_id"]

    @r.post("/lateral/leitor/bots")
    def leitor_bots(p: _LeitorBots):
        uid = _uid_chave(p.chave); sb = _sb(); agora = _now(); out = []
        for b in _meus(sb, uid):
            if b["estado"] == "criado": continue
            sb.table("lateral_bots").update({"ultimo_contato": _iso(agora)}).eq("id", b["id"]).execute()
            out.append({"bot_id": int(b["id"]), "nome": b["nome"], "ativo": b["ativo"], "tf": b["tf"], "regra_versao": b["regra_versao"], "modo": "sombra",
                        "estado": b["estado"], "rodar": b["estado"] in ("enviado", "conectado"), "coleta_inicio": b.get("coleta_inicio"), "coleta_fim": b.get("coleta_fim")})
        return {"ok": True, "bots": out, "regra_versao": VERSAO_REGRA, "agora": _iso(agora)}

    @r.post("/lateral/leitor/confirmar")
    def leitor_confirmar(p: _LeitorConfirma):
        uid = _uid_chave(p.chave); sb = _sb(); bs = _meus(sb, uid, [p.bot_id])
        if not bs: raise HTTPException(status_code=404, detail="bot não encontrado")
        b = bs[0]
        if b["estado"] not in ("enviado", "conectado"): return {"ok": False, "motivo": f"bot está '{b['estado']}'"}
        erros = []
        if p.timeframe != b["tf"]: erros.append(f"timeframe {p.timeframe} ≠ {b['tf']}")
        if p.regra_versao != b["regra_versao"]: erros.append("versão da regra diferente")
        if p.modo != "sombra": erros.append("modo não é sombra")
        if not p.simbolo_efetivo or b["ativo"][:3] not in p.simbolo_efetivo.upper(): erros.append(f"símbolo {p.simbolo_efetivo} não corresponde a {b['ativo']}")
        if not (p.cotacao.get("bid") and p.cotacao.get("ask")): erros.append("sem cotação lida do terminal")
        if erros: return {"ok": False, "erros": erros}
        agora = _now(); conf = {"simbolo_efetivo": p.simbolo_efetivo, "timeframe": p.timeframe, "regra_versao": p.regra_versao, "modo": p.modo,
                                  "cotacao": {k: p.cotacao.get(k) for k in ("bid", "ask", "t")}, "terminal": {k: p.terminal.get(k) for k in ("servidor", "demo", "build", "empresa")},
                                  "confirmado_em": _iso(agora)}
        upd = {"confirmacao": conf, "ultimo_contato": _iso(agora)}
        if b["estado"] == "enviado": upd.update({"estado": "conectado", "conectado_em": _iso(agora)})
        sb.table("lateral_bots").update(upd).eq("id", b["id"]).execute()
        # mesma janela para os 3 TF do ativo: quando todos os bots ativos do ativo estiverem conectados → +1 h de verificação → 7 dias
        irmaos = [x for x in _meus(sb, uid) if x["ativo"] == b["ativo"] and x["estado"] != "parado"]
        if all((x["estado"] == "conectado" or int(x["id"]) == int(b["id"])) for x in irmaos) and not any(x.get("coleta_inicio") for x in irmaos):
            ini = (agora + _dt.timedelta(hours=VERIFICACAO_H)).replace(minute=0, second=0, microsecond=0) + _dt.timedelta(hours=1)
            fim = ini + _dt.timedelta(days=SEMANA_D)
            for x in irmaos: sb.table("lateral_bots").update({"coleta_inicio": _iso(ini), "coleta_fim": _iso(fim)}).eq("id", x["id"]).execute()
        return {"ok": True, "estado": "conectado"}

    @r.post("/lateral/leitor/eventos")
    def leitor_eventos(p: _LeitorEventos):
        uid = _uid_chave(p.chave); sb = _sb()
        if not _meus(sb, uid, [p.bot_id]): raise HTTPException(status_code=404, detail="bot não encontrado")
        linhas = []
        for e in (p.eventos or [])[:MAX_EVENTOS_LOTE]:
            if not isinstance(e, dict) or not e.get("chave") or not e.get("tipo"): continue
            pl = {k: v for k, v in (e.get("payload") or {}).items() if not any(s in str(k).lower() for s in ("token", "chave_do_leitor", "senha", "password", "secret"))}
            linhas.append({"user_id": uid, "bot_id": int(p.bot_id), "chave": str(e["chave"])[:240], "tipo": str(e["tipo"])[:40], "t_evento": e.get("t"), "payload": pl})
        if linhas: sb.table("lateral_eventos").upsert(linhas, on_conflict="bot_id,chave", ignore_duplicates=True).execute()
        sb.table("lateral_bots").update({"ultimo_contato": _iso(_now())}).eq("id", int(p.bot_id)).execute()
        return {"ok": True, "recebidos": len(linhas)}

    return r


def card_para_vitrine(out, uid):
    """O51 (08/11/2026, decisão do dono): o cartão migrou para a plataforma de homologação, no fluxo padrão (EA nativo
    BT_LATERAL_R0, branch ensaio/vitrine-c27r7-isolado). Este caminho paralelo (leitor separado com chave própria) está
    DESATIVADO: a vitrine daqui não mostra mais o cartão. Rotas e tabelas ficam só para consulta do histórico."""
    return out
    """(desativado) apensava o cartão numa CÓPIA da resposta da vitrine só para o usuário de teste."""
    alvo = (os.environ.get("BT_CARD_TESTE_USER") or "").strip()
    if not alvo or not uid or not hmac.compare_digest(str(uid), alvo): return out
    if any((e or {}).get("id") == CARD_ID for e in (out or {}).get("estrategias") or []): return out
    c = dict(out or {}); c["estrategias"] = [dict(CARD)] + list((out or {}).get("estrategias") or []); c["total"] = len(c["estrategias"]); return c
