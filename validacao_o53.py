"""ORDEM 053 — validação do lateral-r1 na BabyMachine (seção 5 do Diagnóstico geral da LM).

Três estados SEPARADOS, nunca somados:
  • replay   — motor de referência (testes/referencia_o53/ao_vivo_o53.py, o MESMO que o EA reproduz tick a tick no teste) sobre os candles gravados
               (auditoria_candles): R0 (antes) × R1 (depois: filtro de espaço + corte estrutural), mais as variantes "só filtro" e "só corte";
  • sombra   — reversão avaliada como decisão independente (replay) e os eventos reversao_sombra do EA (sem ordem);
  • execução observada — operações da BabyMachine, eventos do EA (tipo=lateral) e negócios confirmados pelo MT5, com a reconciliação.
Especificação congelada: testes/referencia_o53/O53_especificacao_congelada.txt. Só leitura: não cria decisão, comando nem ordem."""
import os, sys, random, datetime as _dt
import numpy as np, pandas as pd

_AQUI = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_AQUI, "testes", "referencia_o53"), os.path.join(_AQUI, "testes", "referencia_o51")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import ao_vivo_o53 as R1  # noqa: E402
import pivos_o53b as PV  # noqa: E402
import rompz_o53c as RZ  # noqa: E402
import romp_m15 as _RM  # noqa: E402

VERSAO = "validacao-o53-1.1 (" + R1.VERSAO + " + " + RZ.VERSAO + ")"
UTC = _dt.timezone.utc
SEMENTE = 53
AMARELO = "#ffd60a"
TF_SEG = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600}
TF_CFG = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "60m": "H1"}
ESPEC = ("lateral-r1 (O53), congelada antes do replay: zonas = memória estrutural O39 (fractal 2+2, zona 0,25·ATR14) do TF do gráfico + H1, "
         "aquecida com até 1200 barras fechadas; filtro: bloqueia se a entrada estiver DENTRO da primeira zona à frente ou se o espaço líquido "
         "(distância − spread) for < 1,0 R (R = 2·ATR14); corte: primeiro fechamento além da máxima (venda) / mínima (compra) da barra de entrada; "
         "saída pelo canal EMA20 e stop 2 ATR inalterados; reversão só em sombra.")


def _dt_(x):
    if x in (None, ""):
        return None
    if isinstance(x, _dt.datetime):
        return x if x.tzinfo else x.replace(tzinfo=UTC)
    try:
        d = _dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _iso(d):
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _loc(d, tz):
    return d.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S") if d else None


def _pag(montar, maximo=60000):
    out, i = [], 0
    while len(out) < maximo:
        lote = montar().range(i, i + 999).execute().data or []
        out.extend(lote)
        if len(lote) < 1000:
            return out
        i += 1000
    return out


def candles(sb, simbolo, tf, d0, d1):
    """candles FECHADOS do símbolo (qualquer bot), um por abertura (o último visto), em [d0, d1)."""
    rows = _pag(lambda: sb.table("auditoria_candles").select("abertura_utc,o,h,l,c,fechado,ultimo_visto_utc").eq("simbolo", simbolo).eq("tf", tf)
                .gte("abertura_utc", _iso(d0)).lt("abertura_utc", _iso(d1)).order("abertura_utc"))
    m = {}
    for r in rows:
        if not r.get("fechado") or r.get("o") is None:
            continue
        k = _dt_(r["abertura_utc"])
        if k is None:
            continue
        if k not in m or str(r.get("ultimo_visto_utc") or "") >= str(m[k].get("ultimo_visto_utc") or ""):
            m[k] = r
    # O53: histórico que o PRÓPRIO EA exportou do MT5 (evento ev=historico, horário do servidor − off = UTC) completa o que a coleta não tem
    try:
        hist = _pag(lambda: sb.table("agente_eventos").select("detalhe_json").eq("tipo", "bot_lateral").eq("detalhe_json->>ev", "historico")
                    .eq("detalhe_json->>tf", tf).eq("detalhe_json->>simbolo", simbolo).order("id"), 5000)
    except Exception:
        hist = []
    for e in hist:
        dj = e.get("detalhe_json") or {}
        try:
            off = int(float(dj.get("off") or 0))
        except Exception:
            off = 0
        for item in str(dj.get("barras") or "").split(";"):
            pp = item.split(",")
            if len(pp) != 5:
                continue
            try:
                k = _dt.datetime.fromtimestamp(int(pp[0]) - off, UTC)
            except Exception:
                continue
            if d0 <= k < d1 and k not in m:
                m[k] = {"o": pp[1], "h": pp[2], "l": pp[3], "c": pp[4], "fonte": "historico do EA (MT5)"}
    ks = sorted(m)
    return pd.DataFrame({"ep": [int(k.timestamp()) for k in ks], "open": [float(m[k]["o"]) for k in ks], "high": [float(m[k]["h"]) for k in ks],
                         "low": [float(m[k]["l"]) for k in ks], "close": [float(m[k]["c"]) for k in ks]})


def _cobertura(df, tf, d0, d1):
    seg = TF_SEG[tf]
    if df is None or not len(df):
        return {"tf": tf, "barras": 0, "lacunas": [], "primeira": None, "ultima": None}
    ep = df.ep.values; lac = []
    for a, b in zip(ep[:-1], ep[1:]):
        if b - a > seg:
            lac.append({"de": _iso(_dt.datetime.fromtimestamp(int(a) + seg, UTC)), "ate": _iso(_dt.datetime.fromtimestamp(int(b), UTC)), "barras_faltando": int((b - a) // seg - 1)})
    return {"tf": tf, "barras": int(len(df)), "primeira": _iso(_dt.datetime.fromtimestamp(int(ep[0]), UTC)), "ultima": _iso(_dt.datetime.fromtimestamp(int(ep[-1]), UTC)),
            "lacunas": lac[:20], "lacunas_total": len(lac)}


def _op(o, at):
    return {"id": o["id"], "lado": "venda" if o["lado"] < 0 else "compra", "t_entrada": _iso(_dt.datetime.fromtimestamp(o["t_ent_ms"] / 1000, UTC)), "entrada": round(o["entrada"], 2),
            "stop": round(o["stop"], 2), "t_saida": _iso(_dt.datetime.fromtimestamp(o["t_sai_ms"] / 1000, UTC)), "saida": round(o["saida"], 2), "motivo_saida": o["motivo_saida"],
            "R": round(o["R"], 3), "pts": round(o["pts"], 2), "ref_invalidacao": None if o.get("ref_inval") is None else round(o["ref_inval"], 2), "ref_def": o.get("ref_def"),
            "espaco": _esp(o.get("espaco"))}


def _esp(e):
    if not e:
        return None
    z = e.get("zona")
    return {"motivo": e.get("motivo"), "E": e.get("E"), "spread": None if e.get("spread") is None else round(e["spread"], 2), "R": None if e.get("R") is None else round(e["R"], 2),
            "d": None if e.get("d") is None else round(e["d"], 2), "espaco_R": None if e.get("espaco_R") is None else round(e["espaco_R"], 3),
            "espaco_atr": None if e.get("espaco_atr") is None else round(e["espaco_atr"], 3),
            "zona": None if not z else {"tf": z["tf"], "funcao": z["funcao"], "base": round(z["base"], 2), "topo": round(z["topo"], 2), "estado": z["estado"],
                                         "testes": z["testes"], "rejeicoes": z["rejeicoes"], "membros": z["membros"]}}


def _resumo(ops):
    R = [o["R"] for o in ops]
    return {"operacoes": len(R), "R_total": round(sum(R), 3), "R_medio": round(sum(R) / len(R), 3) if R else None, "vencedoras": sum(1 for r in R if r > 0),
            "perdedoras": sum(1 for r in R if r <= 0), "pior_R": round(min(R), 3) if R else None, "melhor_R": round(max(R), 3) if R else None}


def replay(sb, simbolo, tf, de, ate, spread=None):
    """R0 × R1 sobre os candles gravados. spread: em preço (None = mediana observada nos snapshots não disponível → 0, registrado)."""
    seg = TF_SEG[tf]
    bars = candles(sb, simbolo, tf, de - _dt.timedelta(seconds=seg * 1229), ate)
    h1 = candles(sb, simbolo, "H1", de - _dt.timedelta(hours=1229), ate) if tf != "H1" else None
    m1 = candles(sb, simbolo, "M1", de, ate)
    cob = {"tf": _cobertura(bars, tf, de, ate), "H1": _cobertura(h1, "H1", de, ate) if h1 is not None else None, "M1": _cobertura(m1, "M1", de, ate)}
    if bars is None or len(bars) < 30 or m1 is None or not len(m1):
        return {"situacao": "sem dados suficientes para o replay", "cobertura": cob}
    for k in ("T1", "T5"):
        R1.TF_MIN.setdefault(k, int(k[1:]))
    tfm = {"M1": "T1", "M5": "T5"}.get(tf, tf)
    ini = int(max(de.timestamp(), bars.ep.iloc[min(28, len(bars) - 1)] + seg))
    sp = float(spread or 0.0)
    V = {"R0 (antes)": dict(filtro=False, corte=False, reversao_sombra=False), "R1 (depois)": dict(), "só filtro": dict(corte=False, reversao_sombra=False),
         "só corte": dict(filtro=False)}
    res, inst = {}, {}
    for nome, kw in V.items():
        I = R1.rodar(simbolo, tfm, bars, m1, h1, ini, sp, **kw); inst[nome] = I
        res[nome] = {"resumo": _resumo(I.ops), "contadores": I.cont, "operacoes": [_op(o, simbolo) for o in I.ops]}
    B = inst["R1 (depois)"]
    bloqueios = [{"sinal": e["sinal"], "t": _iso(_dt.datetime.fromtimestamp(e["t_ms"] / 1000, UTC)), "lado": "venda" if e["lado"] < 0 else "compra", "motivo": e["motivo"],
                  "E": e["E"], "spread": round(e["spread"], 2), "R": round(e["R"], 2), "d": None if e.get("d") is None else round(e["d"], 2),
                  "espaco_R": None if e.get("espaco_R") is None else round(e["espaco_R"], 3), "espaco_atr": None if e.get("espaco_atr") is None else round(e["espaco_atr"], 3),
                  "zona": _esp({"zona": e.get("zona")})["zona"]} for e in B.eventos if e["tipo"] == "bloqueado_espaco"]
    sombra = {"avaliacoes": [{"t": _iso(_dt.datetime.fromtimestamp(e["t_ms"] / 1000, UTC)), "posicao": e["id"], "lado_reversao": "venda" if e["lado"] < 0 else "compra",
                              "passa": e["passa"], "motivo": e["motivo"], "espaco_R": e.get("espaco_R")} for e in B.eventos if e["tipo"] == "reversao_sombra_avaliada"],
              "operacoes_sombra": [_op(o, simbolo) for o in B.ops_sombra], "resumo_sombra": _resumo(B.ops_sombra),
              "nota": "SOMBRA: posição contrária avaliada como decisão independente após o corte estrutural; nunca enviada ao MT5 e nunca somada ao resultado."}
    # pareamento caso a caso: o que o R1 fez com cada entrada do R0
    r1_ent = {o["sinal"]: o for o in B.ops}
    r1_bl = {e["sinal"]: e for e in B.eventos if e["tipo"] == "bloqueado_espaco"}
    pares = []
    for o in inst["R0 (antes)"].ops:
        s = o["sinal"]; x = {"sinal": s, "R0": _op(o, simbolo)}
        if s in r1_ent:
            x["R1"] = _op(r1_ent[s], simbolo); x["destino"] = "entrou também — " + ("saiu igual" if abs(r1_ent[s]["R"] - o["R"]) < 1e-9 else f"saiu por {r1_ent[s]['motivo_saida']}")
        elif s in r1_bl:
            x["destino"] = "bloqueado pelo filtro: " + r1_bl[s]["motivo"]; x["R1"] = None
        else:
            x["destino"] = "não entrou no R1 (posição aberta de outro sinal ou gatilho não superado)"; x["R1"] = None
        x["delta_R"] = round((r1_ent[s]["R"] if s in r1_ent else 0.0) - o["R"], 3); pares.append(x)
    velas = {"ep": [int(x) for x in bars.ep], "o": [float(x) for x in bars.open], "h": [float(x) for x in bars.high], "l": [float(x) for x in bars.low], "c": [float(x) for x in bars.close]}
    return {"situacao": "ok", "rotulo": "REPLAY — motor de referência sobre candles gravados (ticks: 4 por M1); não é execução", "simbolo": simbolo, "tf": tf,
            "spread_usado": sp, "inicio_efetivo": _iso(_dt.datetime.fromtimestamp(ini, UTC)), "cobertura": cob, "variantes": res, "bloqueios_R1": bloqueios,
            "pares_R0_R1": pares, "sombra": sombra, "_velas": velas,
            "aviso_aquecimento": None if (h1 is None or len(h1[h1.ep < de.timestamp()]) >= 60) else
            f"H1 com só {int(len(h1[h1.ep < de.timestamp()]))} barras antes do início: zonas H1 mais antigas não existem no replay (o EA no MT5 tem até 1200)."}


# ════════════════════════════════════════════════════════════════════════
# execução observada + reconciliação
# ════════════════════════════════════════════════════════════════════════
def _kv(raw):
    d = {}
    for p in str(raw or "").split("|"):
        if "=" in p:
            k, v = p.split("=", 1); d[k.strip()] = v.strip()
    return d


def observado(sb, bot, de, ate, tz):
    bid = int(bot["id"]); mg = str(bot.get("magic_number") or "")
    ops = sb.table("babymachine_operacoes").select("id,status,ticket_mt5,ts_entrada,ts_saida,decisao,resultado,fonte").eq("bot_id", bid) \
        .gte("ts_criada", _iso(de - _dt.timedelta(days=2))).lte("ts_criada", _iso(ate)).order("id").limit(500).execute().data or []
    evs = _pag(lambda: sb.table("agente_eventos").select("id,tipo,detalhe_json,criado_em").eq("user_id", bot["user_id"]).eq("detalhe_json->>magic", mg)
               .gte("criado_em", _iso(de - _dt.timedelta(days=2))).lte("criado_em", _iso(ate)).order("id"), 20000) if mg else []
    lat = []
    for e in evs:
        dj = e.get("detalhe_json") or {}
        if e.get("tipo") == "bot_lateral":
            kv = dict(dj); kv.update(_kv(dj.get("raw"))); lat.append({"id": e["id"], "t": e["criado_em"], **{k: v for k, v in kv.items() if k not in ("raw", "bot_token")}})
    snap = sb.table("conector_snapshots").select("posicoes_abertas,criado_em").eq("magic_number", int(mg) if mg.isdigit() else -1).order("id", desc=True).limit(1).execute().data or []
    agora = _dt.datetime.now(UTC)
    linhas = []
    for o in ops:
        dec, res = o.get("decisao") or {}, o.get("resultado") or {}
        tk = str(dec.get("ticket") or (res.get("detalhe_ea") or {}).get("ticket") or o.get("ticket_mt5") or "")
        te, ts = _dt_(o.get("ts_entrada")), _dt_(o.get("ts_saida"))
        if not ((te and de <= te < ate) or (ts and de <= ts < ate) or (o.get("status") == "aberta")):
            continue
        ab = [e for e in evs if e["tipo"] == "bot_aberto" and str((e.get("detalhe_json") or {}).get("ticket")) == tk]
        fe = [e for e in evs if e["tipo"] == "bot_fechado" and str((e.get("detalhe_json") or {}).get("ticket")) == tk]
        cmd = [x for x in lat if x.get("ev") == "comando_fechar" and x.get("ticket") == tk]
        razao = next((_kv((e.get("detalhe_json") or {}).get("raw")).get("razao") for e in fe if _kv((e.get("detalhe_json") or {}).get("raw")).get("razao")), None)
        if o.get("status") == "orfa":
            dup = tk and any(str(((x.get("decisao") or {}).get("ticket")) or "") == tk and x["id"] != o["id"] for x in ops)
            estado = "evento de fechamento duplicado do mesmo ticket (já casado com a operação do ticket)" if dup else "estado não confirmado no MT5 (fechamento sem abertura registrada)"
        elif o.get("status") == "aberta":
            s = snap[0] if snap else None; idade = (agora - _dt_(s["criado_em"])).total_seconds() if s else None
            if s is None or idade is None or idade > 120:
                estado = "estado não confirmado no MT5 (sem snapshot recente)"
            elif int(s.get("posicoes_abertas") or 0) == 0:
                estado = "estado não confirmado no MT5 (último snapshot mostra 0 posições)"
            elif cmd:
                estado = "estado não confirmado no MT5 (comando de fechar enviado e posição ainda aberta)"
            else:
                estado = "aberta — confirmada pelo último snapshot"
        else:
            estado = "confirmado no MT5 (abertura e fechamento)" if (ab and fe) else "estado não confirmado no MT5 (falta evento de " + ("abertura" if not ab else "fechamento") + ")"
        ent, sai, stop = dec.get("entrada"), res.get("preco_saida"), dec.get("stop")
        lado = -1 if str(dec.get("direcao") or "").lower() in ("short", "sell", "venda") else 1
        R = ((float(sai) - float(ent)) * lado / abs(float(ent) - float(stop))) if (ent and sai and stop and float(ent) != float(stop)) else None
        trilha = [x for x in lat if x.get("ticket") == tk or (te and ts and te <= _dt_(x["t"]) <= ts + _dt.timedelta(seconds=90))]
        linhas.append({"op": o["id"], "ticket": tk or None, "status": o.get("status"), "estado_mt5": estado, "lado": "venda" if lado < 0 else "compra",
                       "entrada_utc": _iso(te), "entrada_local": _loc(te, tz) if te else None, "preco_entrada": ent, "stop": stop, "alvo": dec.get("alvo"),
                       "saida_utc": _iso(ts), "saida_local": _loc(ts, tz) if ts else None, "preco_saida": sai, "razao_mt5": razao, "R": None if R is None else round(R, 3),
                       "comandos_fechar_do_ea": len(cmd), "eventos_do_ea": [{k: v for k, v in x.items() if k not in ("user_id",)} for x in trilha][:60]})
    return {"rotulo": "EXECUÇÃO OBSERVADA — negócios do MT5 e eventos do EA gravados na BabyMachine", "operacoes": linhas,
            "eventos_lateral_no_periodo": len([x for x in lat if de <= _dt_(x["t"]) < ate]),
            "versoes_do_ea_vistas": sorted({x.get("v") for x in lat if x.get("v")}),
            "sem_eventos_r1": not any(x.get("v") for x in lat),
            "nota_sem_eventos": None if any(x.get("v") for x in lat) else
            "nenhum evento do EA lateral-r1 no período: o EA no gráfico ainda é o anterior (R0) ou não houve barra com o novo EA — o comportamento do R1 NÃO está confirmado no terminal.",
            "ultimo_snapshot": snap[0] if snap else None}


# ════════════════════════════════════════════════════════════════════════
# janelas de gráfico (sorteio fixo, semente 53)
# ════════════════════════════════════════════════════════════════════════
def _ema(x, n=20):
    a = 2.0 / (n + 1); out = []
    for i, v in enumerate(x):
        out.append(v if i == 0 else out[-1] + a * (v - out[-1]))
    return out


def _janela(rep, cat, titulo, t_ini, t_fim, marcas, rotulo):
    V = rep["_velas"]; ep = V["ep"]; seg = TF_SEG[rep["tf"]]
    if not ep:
        return None
    eH, eL = _ema(V["h"]), _ema(V["l"])
    i_a = max(0, int(np.searchsorted(ep, t_ini, side="right")) - 1 - 24); i_b = min(len(ep), int(np.searchsorted(ep, t_fim, side="right")) + 6)
    idx = lambda t: None if t is None else int(np.searchsorted(ep, t, side="right")) - 1 - i_a
    m = dict(marcas)
    for k in ("entrada", "saida_r1", "saida_r0", "pivo"):
        if m.get(k):
            m[k] = [idx(m[k][0]), m[k][1]]
    for k in ("barra_sinal", "conf"):
        if m.get(k) is not None:
            m[k] = idx(m[k])
    return {"categoria": cat, "titulo": titulo, "rotulo": rotulo, "tf": rep["tf"], "velas": [[ep[i], V["o"][i], V["h"][i], V["l"][i], V["c"][i]] for i in range(i_a, i_b)],
            "ema20_high": [round(x, 4) for x in eH[i_a:i_b]], "ema20_low": [round(x, 4) for x in eL[i_a:i_b]], "ema_aquecimento_barras": i_a, "marcas": m, "seg": seg}


def _t(s):
    d = _dt_(s)
    return int(d.timestamp()) if d else None


def janelas(rep, obs, tz):
    out = []
    if not rep or rep.get("situacao") != "ok":
        return out
    rng = random.Random(SEMENTE)
    rot = "REPLAY — candles gravados; não é execução"
    for o in (obs or {}).get("operacoes", [])[:4]:
        if not o.get("entrada_utc"):
            continue
        par = next((p for p in rep["pares_R0_R1"] if abs((_t(p["R0"]["t_entrada"]) or 0) - (_t(o["entrada_utc"]) or 0)) <= 900), None)
        z = None
        if par and par.get("R1") and par["R1"].get("espaco"):
            z = par["R1"]["espaco"].get("zona")
        else:
            bl = next((b for b in rep["bloqueios_R1"] if par and b["sinal"] == par["sinal"]), None); z = bl and bl.get("zona")
        mk = {"entrada": [_t(o["entrada_utc"]), o.get("preco_entrada")], "saida_r0": [_t(o["saida_utc"]), o.get("preco_saida")] if o.get("saida_utc") else None,
              "stop": o.get("stop"), "R": o.get("R"), "zona": z}
        if par and par.get("R1"):
            mk["saida_r1"] = [_t(par["R1"]["t_saida"]), par["R1"]["saida"]]; mk["R_r1"] = par["R1"]["R"]; mk["ref"] = par["R1"]["ref_invalidacao"]
        dest = par["destino"] if par else "sem par no replay (dados do período não cobrem a entrada)"
        out.append(_janela(rep, "operação observada", f"OBSERVADA op {o['op']} ticket {o.get('ticket')} · {o['lado']} · entrada {o.get('entrada_local')} · saída {o.get('razao_mt5') or '—'} "
                           f"{'' if o.get('R') is None else f'{o[chr(82)]:+.2f} R'} · R1 no replay: {dest}", _t(o["entrada_utc"]) - 3600, _t(o.get("saida_utc") or o["entrada_utc"]) + 1800, mk,
                           "EXECUÇÃO OBSERVADA (preços do MT5) + destino no REPLAY do R1"))
    cats = {"R1 bloqueou (deixou passar)": [("bl", b) for b in rep["bloqueios_R1"]],
            "R1 corte estrutural": [("op", o) for o in rep["variantes"]["R1 (depois)"]["operacoes"] if o["motivo_saida"] == "corte estrutural"],
            "R1 saída pelo canal ou stop": [("op", o) for o in rep["variantes"]["R1 (depois)"]["operacoes"] if o["motivo_saida"] != "corte estrutural"],
            "reversão em sombra": [("sb", o) for o in rep["sombra"]["operacoes_sombra"]]}
    for cat, itens in cats.items():
        if not itens:
            out.append({"categoria": cat, "titulo": f"sem caso no período: {cat}", "sem_grafico": True}); continue
        for i in sorted(rng.sample(range(len(itens)), min(2, len(itens)))):
            tipo, x = itens[i]
            if tipo == "bl":
                par = next((p for p in rep["pares_R0_R1"] if p["sinal"] == x["sinal"]), None)
                mk = {"entrada": [_t(x["t"]), x["E"]], "zona": x.get("zona"), "R": None}
                if par:
                    mk["saida_r0"] = [_t(par["R0"]["t_saida"]), par["R0"]["saida"]]; mk["stop"] = par["R0"]["stop"]; mk["R_r0"] = par["R0"]["R"]
                tt = (f"DEIXOU PASSAR (R1) · {x['lado']} · {_loc(_dt_(x['t']), tz)} · {x['motivo']} · espaço {x.get('espaco_R')} R ({x.get('espaco_atr')} ATR) até "
                      f"{(x.get('zona') or {}).get('funcao', '—')} {(x.get('zona') or {}).get('tf', '')} {(x.get('zona') or {}).get('base', '')}–{(x.get('zona') or {}).get('topo', '')}"
                      + (f" · o R0 entrou e fez {par['R0']['R']:+.2f} R" if par else ""))
                fim = _t(par["R0"]["t_saida"]) if par else _t(x["t"])
                out.append(_janela(rep, cat, tt, _t(x["t"]), fim + 900, mk, rot))
            else:
                par = next((p for p in rep["pares_R0_R1"] if p["R1"] and p["R1"]["id"] == x["id"]), None) if tipo == "op" else None
                mk = {"entrada": [_t(x["t_entrada"]), x["entrada"]], "saida_r1": [_t(x["t_saida"]), x["saida"]], "stop": x["stop"], "ref": x.get("ref_invalidacao"),
                      "R_r1": x["R"], "zona": (x.get("espaco") or {}).get("zona")}
                if par:
                    mk["saida_r0"] = [_t(par["R0"]["t_saida"]), par["R0"]["saida"]]; mk["R_r0"] = par["R0"]["R"]
                pre = "SOMBRA (reversão, nunca enviada)" if tipo == "sb" else "R1"
                tt = (f"{pre} · {x['lado']} · entrada {_loc(_dt_(x['t_entrada']), tz)} · saída por {x['motivo_saida']} {x['R']:+.2f} R"
                      + (f" · R0 na mesma entrada: {par['R0']['R']:+.2f} R ({par['R0']['motivo_saida']})" if par else ""))
                out.append(_janela(rep, cat, tt, _t(x["t_entrada"]), max(_t(x["t_saida"]), _t(par["R0"]["t_saida"]) if par else 0) + 900, mk,
                                   "SOMBRA (replay) — nenhuma ordem" if tipo == "sb" else rot))
    return [j for j in out if j]


def grafico_png(j):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    V = j["velas"]; M = j["marcas"]; n = len(V)
    fig, ax = plt.subplots(figsize=(11, 4.6), facecolor="#fcfcfb")
    z = M.get("zona")
    if z and z.get("base") is not None:
        cor = "#1baf7a" if str(z.get("funcao") or "").startswith("suporte") else "#eb6834"
        ax.axhspan(z["base"], z["topo"], color=cor, alpha=0.18, zorder=0, label=f"zona {z.get('funcao')} {z.get('tf')} {z['base']:.2f}–{z['topo']:.2f} ({z.get('estado')}, {z.get('testes')} testes)")
    for x, (t, o, h, l, c) in enumerate(V):
        ax.plot([x, x], [l, h], color="#52514e", lw=0.8, zorder=2)
        ax.add_patch(Rectangle((x - 0.3, min(o, c)), 0.6, max(abs(c - o), 1e-9), facecolor="#ffffff" if c >= o else "#52514e", edgecolor="#52514e", lw=0.7, zorder=3))
    xs = list(range(n))
    ax.plot(xs, j["ema20_high"], color=AMARELO, lw=2.4, zorder=4, label="EMA20 High")
    ax.plot(xs, j["ema20_low"], color=AMARELO, lw=2.4, zorder=4, label="EMA20 Low")
    zp = M.get("zona_pivo")
    if zp:
        ax.axhspan(zp[0], zp[1], color="#8b3fd6", alpha=0.14, zorder=0, label=f"zona do pivô (O39) {zp[0]:.2f}–{zp[1]:.2f}")
    if M.get("pivo") and M["pivo"][0] is not None:
        ax.plot(M["pivo"][0], M["pivo"][1], marker="o", ms=11, mfc="none", mec="#8b3fd6", mew=2.2, zorder=7, label=f"extremo {M['pivo'][1]:.2f}")
    if M.get("conf") is not None and 0 <= M["conf"] < n:
        t_, o_, h_, l_, c_ = V[M["conf"]]
        ax.add_patch(Rectangle((M["conf"] - 0.45, l_), 0.9, h_ - l_, fill=False, edgecolor="#eb6834", lw=2, zorder=5))
        ax.text(M["conf"], h_, M.get("rotulo_conf") or "pivô confirmável\n(fechamento i+2)", color="#eb6834", fontsize=7, ha="center", va="bottom")
    if M.get("gatilho"):
        ax.axhline(M["gatilho"], color="#6250d6", lw=1.1, ls="--", zorder=1, label=f"gatilho {M['gatilho']:.2f}")
    if M.get("stop"):
        ax.axhline(M["stop"], color="#d63a3a", lw=1.0, ls=":", zorder=1, label=f"stop {M['stop']:.2f}")
    if M.get("ref"):
        ax.axhline(M["ref"], color="#6250d6", lw=1.2, ls="--", zorder=1, label=f"invalidação (barra de entrada) {M['ref']:.2f}")
    if M.get("entrada") and M["entrada"][1] is not None and M["entrada"][0] is not None:
        ax.plot(M["entrada"][0], float(M["entrada"][1]), marker="v" if ("venda" in j["titulo"] or "TOPO" in j["titulo"]) else "^", ms=10, color="#6250d6", zorder=6, label=f"entrada/gatilho {float(M['entrada'][1]):.2f}")
    if M.get("saida_r0") and M["saida_r0"][0] is not None and M["saida_r0"][1] is not None:
        r0 = M.get("R_r0", M.get("R"))
        ax.plot(M["saida_r0"][0], float(M["saida_r0"][1]), "X", ms=9, color="#8a8a8a", zorder=6, label="saída R0 / observada" + (f" {r0:+.2f} R" if r0 is not None else ""))
    if M.get("saida_r1") and M["saida_r1"][0] is not None:
        r1 = M.get("R_r1")
        ax.plot(M["saida_r1"][0], float(M["saida_r1"][1]), "X", ms=10, color="#1baf7a" if (r1 or 0) > 0 else "#d63a3a", zorder=7, label=(M.get("rotulo_saida") or "saída R1") + (f" {r1:+.2f} R" if r1 is not None else ""))
    tzj = _dt.timezone(_dt.timedelta(hours=2))
    try:
        from zoneinfo import ZoneInfo
        tzj = ZoneInfo("Europe/Kyiv")
    except Exception:
        pass
    st = max(1, n // 8)
    ax.set_xticks(range(0, n, st)); ax.set_xticklabels([_dt.datetime.fromtimestamp(V[i][0], UTC).astimezone(tzj).strftime("%d/%m %H:%M") for i in range(0, n, st)], fontsize=7)
    ax.set_xlabel(f"barras {j.get('tf')} (abertura, Europe/Kyiv)", fontsize=7); ax.set_xlim(-1, n + 3)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color="#e6e5e0", lw=0.5); ax.tick_params(labelsize=7); ax.legend(loc="upper left", fontsize=6.3, frameon=False, ncol=3)
    ax.set_title(j["rotulo"], fontsize=7, loc="right", color="#52514e")
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png", dpi=110, facecolor="#fcfcfb"); plt.close(fig)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════
# O53-B — auditoria de topos/fundos e REV-0 em sombra (replay × leitura original da LM × eventos do EA)
# ════════════════════════════════════════════════════════════════════════
def _lm_registro(sb, bot, de, ate):
    """leitura contínua original da LM (auditoria_leituras): por barra M15 (fechamento), a última leitura com estrutura M15."""
    rows = _pag(lambda: sb.table("auditoria_leituras").select("ts,barra_m15_utc,estrutura_por_tf").eq("bot_id", int(bot["id"]))
                .gte("ts", _iso(de - _dt.timedelta(hours=2))).lte("ts", _iso(ate + _dt.timedelta(hours=1))).order("id"), 120000)
    por = {}
    for r in rows:
        m = ((r.get("estrutura_por_tf") or {}) if isinstance(r.get("estrutura_por_tf"), dict) else {}).get("M15")
        b = _dt_(r.get("barra_m15_utc"))
        if isinstance(m, dict) and b:
            por[int(b.timestamp())] = m
    return por


def pivos_auditoria(sb, bot, tf, de, ate, tz):
    if tf != "M15":
        return {"situacao": "a auditoria de pivôs (REV-0) é só em M15 (especificação O53-B)"}
    sim = str(bot.get("simbolo") or "").upper()
    m15 = candles(sb, sim, "M15", de - _dt.timedelta(seconds=900 * 1229), ate)
    h1 = candles(sb, sim, "H1", de - _dt.timedelta(hours=1229), ate)
    if m15 is None or len(m15) < 30:
        return {"situacao": "sem candles M15 suficientes no período"}
    res = PV.auditar(m15, h1, int(de.timestamp()), int(ate.timestamp()), sim)
    lm = _lm_registro(sb, bot, de, ate)
    ks = sorted(lm)
    mg = str(bot.get("magic_number") or "")
    try:
        evs = _pag(lambda: sb.table("agente_eventos").select("detalhe_json,criado_em").eq("tipo", "bot_lateral").eq("detalhe_json->>magic", mg)
                   .in_("detalhe_json->>ev", ["pivo", "rev0"]).gte("criado_em", _iso(de)).lte("criado_em", _iso(ate + _dt.timedelta(hours=1))).order("id"), 5000) if mg else []
    except Exception:
        evs = []
    ea_rev = {}
    for e in evs:
        d = e.get("detalhe_json") or {}
        if d.get("ev") == "rev0" and d.get("id"):
            ea_rev[d["id"]] = d.get("estado")
    ep = [int(x) for x in m15.ep]; C = dict(zip(ep, [float(x) for x in m15.close]))
    L = lambda e: _loc(_dt.datetime.fromtimestamp(int(e), UTC), tz)
    linhas = []
    for p in res["pivos"]:
        if p["situacao"] != "confirmado":
            continue
        r = p.get("rev") or {}
        x = p["extremo"]; chave = "ultimo_topo" if p["tipo"] == "topo" else "ultimo_fundo"
        k_lm = next((k for k in ks if k >= p["barra"] and abs(float(lm[k].get(chave) or 0) - x) < 0.02), None)
        ev_lm = sorted({e for k in ks if p["barra"] + 900 <= k <= p["barra"] + 3600 for e in (lm[k].get("eventos") or []) if str(e).startswith(("sacudida", "exaustao"))})
        iid = ("F-" if p["tipo"] == "fundo" else "T-") + str(p["barra"])
        est = r.get("estado")
        onde = {"sem rejeição": "exaustão/rejeição não confirmada no pivô", "gatilho não alcançado": "gatilho ausente (não alcançado na barra seguinte)",
                "bloqueada pelo espaço": "entrada bloqueada pelo espaço", "entrou (sombra)": "oportunidade registrada só em sombra",
                "aguardando barra seguinte": "gatilho armado no fim do período"}.get(est, est)
        linhas.append({"id": iid, "tipo": p["tipo"], "extremo": x, "hora_extremo": L(p["barra"]), "confirmavel_em": L(p["confirmado_em"]),
                       "preco_na_confirmacao": C.get(p["confirmado_em"] - 900), "zona_pivo": p["zona"],
                       "lm_registrou_em": L(k_lm) if k_lm else None, "lm_eventos": ev_lm,
                       "sombra_pct": r.get("sombra_pct"), "rejeicao_zona": r.get("rejeicao_zona_o39"), "gatilho": r.get("gatilho"), "entrada": r.get("entrada"),
                       "stop": r.get("stop"), "R": r.get("R"), "espaco_R": r.get("espaco_R"), "zona_a_frente": r.get("zona_a_frente"),
                       "estado_rev0": est, "decisao": r.get("decisao"), "onde_parou": onde, "classe": r.get("classe"), "R_final": r.get("R_final"), "MFE_R": r.get("MFE_R"),
                       "ea_rev0": ea_rev.get(iid) or "sem evidência no EA (EA sem O53-B no gráfico ou fora do período)",
                       "_t": p["barra"], "_conf": p["confirmado_em"] - 900, "_atr": p.get("atr")})
    toq = res["toques"]
    cont = {k: sum(1 for t in toq if t["desfecho"] == k) for k in ("reação", "continuidade", "indefinido")}
    # janelas: todos os pivôs até 12, sorteio fixo por categoria de estado
    rng = random.Random(SEMENTE); cats = {}
    for l_ in linhas:
        cats.setdefault(l_["estado_rev0"], []).append(l_)
    escolhidos = []
    for c, it in cats.items():
        escolhidos += [it[i] for i in sorted(rng.sample(range(len(it)), min(3, len(it))))]
    escolhidos = sorted(escolhidos, key=lambda z: z["_t"])[:12]
    rep = {"tf": "M15", "_velas": {"ep": ep, "o": [float(v) for v in m15.open], "h": [float(v) for v in m15.high], "l": [float(v) for v in m15.low], "c": [float(v) for v in m15.close]}}
    jan = []
    for l_ in escolhidos:
        za = l_.get("zona_a_frente")
        mk = {"pivo": [l_["_t"], l_["extremo"]], "conf": l_["_conf"], "zona_pivo": l_["zona_pivo"], "gatilho": l_["gatilho"], "stop": l_["stop"],
              "zona": None if not za else {"tf": za.get("tf"), "funcao": za.get("funcao"), "base": za.get("base"), "topo": za.get("topo"), "estado": za.get("estado"), "testes": za.get("testes")}}
        j = _janela(rep, "pivô", f"{l_['tipo'].upper()} {l_['extremo']:.2f} às {l_['hora_extremo'][11:16]} · confirmável {l_['confirmavel_em'][11:16]} · LM registrou "
                    f"{(l_['lm_registrou_em'] or '—')[11:16]} · REV-0: {l_['onde_parou']}" + (f" ({l_['espaco_R']} R até a zona)" if l_.get("espaco_R") is not None else ""),
                    l_["_t"] - 900 * 4, l_["_conf"] + 900 * 8, mk, "REPLAY M15 fechado (só dados disponíveis em cada barra) — REV-0 em SOMBRA, nenhuma ordem")
        if j:
            jan.append(j)
    for l_ in linhas:
        for k in ("_t", "_conf", "_atr"):
            l_.pop(k, None)
    return {"situacao": "ok", "versao": PV.VERSAO, "pivos": linhas, "descartados": sum(1 for p in res["pivos"] if p["situacao"] == "descartado"),
            "toques_de_zona": cont, "janelas": jan,
            "resumo_rev0": {k: sum(1 for l_ in linhas if l_["estado_rev0"] == k) for k in sorted({l_["estado_rev0"] for l_ in linhas})},
            "nota": "Pivô = fractal 2+2 da O39, reconhecível só no fechamento da barra i+2. 'LM registrou' = 1ª leitura contínua com o valor como último topo/fundo."}


# ════════════════════════════════════════════════════════════════════════
# O53-C — trilha barra de rompimento → gatilho → barra seguinte → ordem ou bloqueio
# ════════════════════════════════════════════════════════════════════════
def diag_r0(l, h, c, atr, b):
    """1ª condição da R0 (O44/O51, a do EA BTLatDetectar) que falha na barra b, sentido VENDA sobre ticks (compra: espelho). Mesma conta do EA."""
    if b < 14 or not np.isfinite(atr[b - 1]) or atr[b - 1] <= 0:
        return "histórico insuficiente"
    amp = (h[b - 12:b].max() - l[b - 12:b].min()) * 0.01; lim = 3.0 * atr[b - 1]
    if amp > lim + 1e-12:
        return f"caixa: amplitude {amp:.2f} > 3 ATR {lim:.2f}"
    p = next((q for q in range(b - 3, b - 13, -1) if q - 2 >= 0 and l[q] < min(l[q - 2], l[q - 1], l[q + 1], l[q + 2])), None)
    if p is None:
        return "pivô: nenhum pivô 2+2 dentro da caixa"
    F = l[p]; nv = f"{abs(F) * 0.01:.2f}"
    if not c[b] < F:
        return f"fechamento não passou do nível {nv}"
    tent = 0
    for q in range(p + 1, b):
        if c[q] >= F:
            tent += int(l[q] < F)
        elif q + 1 <= b - 1 and not (l[q + 1] <= l[q] - 1) and c[q + 1] >= F:
            tent += 1
        else:
            return f"fechamento anterior além do nível {nv} já confirmado"
    return f"sem tentativa anterior no nível {nv}" if tent == 0 else f"formação ok no nível {nv}"


def _saida_sombra(m15, m1, lado, E, stop, t_ent):
    """gestão R0 neutra só para medir a sombra: stop 2 ATR pelo M1 (bid/ask como no replay) e saída no fechamento de volta ao canal EMA20 High/Low."""
    ep = m15.ep.values.astype(np.int64); eH, eL = _ema(list(m15.high)), _ema(list(m15.low))
    for i in range(int(np.searchsorted(ep, (t_ent // 900) * 900)), len(ep)):
        k = (m1.ep >= max(ep[i], t_ent)) & (m1.ep < ep[i] + 900)
        if k.any():
            if lado < 0 and float(m1.high[k].max()) >= stop or lado > 0 and float(m1.low[k].min()) <= stop:
                return ep[i], stop, "stop 2 ATR"
        if ep[i] + 900 > t_ent and (lado < 0 and float(m15.close.iloc[i]) >= eL[i] or lado > 0 and float(m15.close.iloc[i]) <= eH[i]):
            return ep[i], float(m15.close.iloc[i]), "canal EMA20"
    return (int(ep[-1]), float(m15.close.iloc[-1]), "em aberto no fim dos dados (R marcado no último fechamento)") if len(ep) else (None, None, "sem dados")


def _lm_por_barra(sb, bot, de, ate):
    """1ª leitura contínua da LM que descreve cada barra M15 FECHADA (campo barra_corretora, horário do servidor) — quando e o que leu."""
    rows = _pag(lambda: sb.table("auditoria_leituras").select("ts,estrutura_por_tf").eq("bot_id", int(bot["id"]))
                .gte("ts", _iso(de)).lte("ts", _iso(ate)).order("id"), 120000)
    out = {}
    for r in rows:
        m = ((r.get("estrutura_por_tf") or {}) if isinstance(r.get("estrutura_por_tf"), dict) else {}).get("M15")
        if isinstance(m, dict) and m.get("barra_corretora") and str(m["barra_corretora"]) not in out:
            out[str(m["barra_corretora"])] = (r.get("ts"), m)
    return out


def trilha_rompz(sb, bot, tf, de, ate, tz):
    """cada barra que FECHOU além de um suporte/resistência da memória O39 (TF do gráfico) no período: o que a R0 do gráfico decidiu nela, o que a
    LM leu, o gatilho na mínima/máxima, o 1º preço além dele na barra seguinte (M1 gravado — não há tick histórico), o espaço até a 1ª zona,
    o que o EA registrou e se houve ordem. Só leitura."""
    if tf != "M15":
        return {"situacao": "a trilha de rompimento (O53-C) é só em M15"}
    sim = str(bot.get("simbolo") or "").upper()
    m15 = candles(sb, sim, "M15", de - _dt.timedelta(seconds=900 * 1229), ate + _dt.timedelta(hours=6))
    h1 = candles(sb, sim, "H1", de - _dt.timedelta(hours=1229), ate)
    m1 = candles(sb, sim, "M1", de - _dt.timedelta(minutes=30), ate + _dt.timedelta(hours=6))
    if m15 is None or len(m15) < 30 or m1 is None or not len(m1):
        return {"situacao": "sem candles M15/M1 suficientes no período"}
    ini = max(int(de.timestamp()), int(m1.ep.iloc[0]))
    ev = RZ.rodar(m15, h1, m1, ini, 0.0)
    ep = m15.ep.values.astype(np.int64); A = _RM.atr_wilder(m15.high, m15.low, m15.close)
    T = lambda x: np.rint(np.asarray(x, float) / 0.01).astype(np.int64)
    hT, lT, cT = T(m15.high), T(m15.low), T(m15.close)
    lm = _lm_por_barra(sb, bot, de, ate + _dt.timedelta(hours=7))
    mg = str(bot.get("magic_number") or "")
    try:
        evs = _pag(lambda: sb.table("agente_eventos").select("detalhe_json,criado_em").eq("tipo", "bot_lateral").eq("detalhe_json->>magic", mg)
                   .in_("detalhe_json->>ev", ["inicio", "rompz_armado", "rompz_disparo", "rompz_expirado", "barra"])
                   .gte("criado_em", _iso(de - _dt.timedelta(days=3))).lte("criado_em", _iso(ate + _dt.timedelta(hours=7))).order("id"), 20000) if mg else []
    except Exception:
        evs = []
    D = [dict(e.get("detalhe_json") or {}, **_kv((e.get("detalhe_json") or {}).get("raw"))) for e in evs]
    off = next((int(float(x.get("off") or 0)) for x in reversed(D) if x.get("ev") == "inicio" and x.get("off") not in (None, "")), None)
    ea_r = {}
    for x in D:
        if str(x.get("ev", "")).startswith("rompz") and x.get("sinal") and off is not None:
            pre, n_ = x["sinal"][:3], x["sinal"][3:]
            ea_r.setdefault(pre + str(int(n_) - off), []).append(x)
    ea_barra = {int(x["t"]) - (off or 0): x for x in D if x.get("ev") == "barra" and x.get("t")}
    ops = sb.table("babymachine_operacoes").select("id,ts_entrada,decisao,status").eq("bot_id", int(bot["id"])) \
        .gte("ts_criada", _iso(de)).lte("ts_criada", _iso(ate + _dt.timedelta(hours=7))).order("id").execute().data or []
    L = lambda e: _loc(_dt.datetime.fromtimestamp(int(e), UTC), tz)
    def num_barra(e):
        d = _dt.datetime.fromtimestamp(int(e), UTC).astimezone(tz)
        return (d.hour * 60 + d.minute) // 15 + 1
    arm = {e["sinal"]: e for e in ev if e["ev"] == "rompz_armado"}; fim = {e["sinal"]: e for e in ev if e["ev"] in ("rompz_disparo", "rompz_expirado")}
    linhas = []
    for sid, a in arm.items():
        b0 = a["barra_rompimento"]
        if not (de.timestamp() <= b0 < ate.timestamp()):
            continue
        s = a["lado"]; b = int(np.searchsorted(ep, b0)); f = fim.get(sid) or {}
        r0 = diag_r0(lT, hT, cT, A, b) if s < 0 else diag_r0(-hT, -lT, -cT, A, b)
        srv = _dt.datetime.fromtimestamp(b0 + (off if off is not None else 7200), UTC).strftime("%Y-%m-%d %H:%M:%S")
        t_lm, lmb = lm.get(srv) or (None, {})
        nxt0, nxt1 = b0 + 900, b0 + 1800
        mm = m1[(m1.ep >= nxt0) & (m1.ep < nxt1)]
        cruz = mm[(mm.low <= a["gatilho"])] if s < 0 else mm[(mm.high >= a["gatilho"])]
        p_ab = float(mm.open.iloc[0]) if len(mm) else None
        o = next((x for x in ops if x.get("ts_entrada") and nxt0 <= _dt_(x["ts_entrada"]).timestamp() < nxt1), None)
        er = ea_r.get(sid) or []
        ea_txt = ("; ".join(f"{x['ev']}" + (f" t={x.get('t')} bid={x.get('bid')} espaço passa={x.get('espaco_passa')}" if x["ev"] == "rompz_disparo" else
                                            f" {x.get('resultado')}" if x["ev"] == "rompz_expirado" else f" gatilho {x.get('gatilho')}") for x in er)
                  if er else ("sem evidência: o EA no gráfico não registra o ROMPZ (só lateral-r1.2) — " +
                              (f"registro da barra: R0 venda «{ea_barra[b0].get('r0_venda')}»" if ea_barra.get(b0) else "e o EA não registrou esta barra (R0 só escreve no log Experts do MT5)")))
        lin = {"id": sid, "lado": "venda" if s < 0 else "compra", "barra_rompimento": L(b0), "n_barra_dia": num_barra(b0), "zonas_rompidas": a["zonas"],
               "fechamento": float(m15.close.iloc[b]), "extremo": a["extremo"], "gatilho": a["gatilho"], "atr": round(a["atr"], 2),
               "r0_na_barra": r0, "lm_na_barra": {"ultimo_fundo": lmb.get("ultimo_fundo"), "ultimo_topo": lmb.get("ultimo_topo"), "localizacao": lmb.get("localizacao"),
                                                   "eventos": lmb.get("eventos"), "barra_lida": lmb.get("barra_corretora")} if lmb else None,
               "lm_leu_a_barra_em": _loc(_dt_(t_lm), tz) if t_lm else None,
               "lm_registra_suporte_rompido": None if not lmb else any(abs(float(lmb.get("ultimo_fundo" if s < 0 else "ultimo_topo") or 0) - z) < 0.02
                                                                    for zz in a["zonas"] for z in zz),
               "barra_seguinte": L(nxt0), "n_barra_seguinte": num_barra(nxt0), "abertura_seguinte": p_ab,
               "primeiro_minuto_alem": L(int(cruz.ep.iloc[0])) if len(cruz) else None,
               "abriu_alem_do_gatilho": None if p_ab is None else (p_ab <= a["gatilho"] if s < 0 else p_ab >= a["gatilho"]),
               "resultado_replay": f.get("ev", "aguardando").replace("rompz_", ""), "preco_disparo": f.get("bid" if s < 0 else "ask"),
               "espaco_R": None if f.get("espaco_R") is None else round(f["espaco_R"], 3), "motivo_espaco": f.get("motivo"),
               "zona_a_frente": f.get("zona_a_frente"), "ea": ea_txt, "ordem": (f"op {o['id']} ({o.get('status')})" if o else "nenhuma ordem na barra seguinte"),
               "_b0": b0, "_t": f.get("t")}
        if f.get("ev") == "rompz_disparo":
            E = lin["preco_disparo"]; stop = round(E - s * 2.0 * a["atr"], 2)
            t_s, px, mot = _saida_sombra(m15, m1, s, E, stop, int(f["t"]))
            lin.update(stop=stop, saida_sombra=None if px is None else round(px, 2), saida_sombra_em=None if t_s is None else L(t_s), motivo_saida_sombra=mot,
                       R_sombra=None if px is None else round((px - E) * s / abs(E - stop), 3), _ts=t_s)
            lin["onde_parou"] = ("ordem enviada" if o else
                                 "disparo válido na barra seguinte; " + ("o filtro de espaço O53 bloquearia (" + str(lin["motivo_espaco"]) + ")" if f.get("espaco_passa") == "nao" else "o filtro de espaço passaria")
                                 + "; a R0 do gráfico não armou: " + r0)
        else:
            lin["onde_parou"] = {"expirado": "gatilho não superado dentro da barra seguinte (" + str(f.get("resultado")) + ")"}.get(lin["resultado_replay"], "sem dados M1 até o fim da barra seguinte (resultado em aberto)")
        linhas.append(lin)
    rng = random.Random(SEMENTE)
    disp = [l_ for l_ in linhas if l_["resultado_replay"] == "disparo"][:8]; exp = [l_ for l_ in linhas if l_["resultado_replay"] != "disparo"]
    escolhidos = sorted(disp + [exp[i] for i in sorted(rng.sample(range(len(exp)), min(2, len(exp))))], key=lambda z: z["_b0"])
    rep = {"tf": "M15", "_velas": {"ep": [int(x) for x in ep], "o": [float(v) for v in m15.open], "h": [float(v) for v in m15.high], "l": [float(v) for v in m15.low],
                                   "c": [float(v) for v in m15.close]}}
    jan = []
    for l_ in escolhidos:
        z0 = l_["zonas_rompidas"][0]
        mk = {"zona": {"tf": "M15", "funcao": "suporte rompido" if l_["lado"] == "venda" else "resistência rompida", "base": z0[0], "topo": z0[1], "estado": "ROMPIMENTO PENDENTE",
                       "testes": "—"}, "conf": l_["_b0"], "gatilho": l_["gatilho"], "stop": l_.get("stop")}
        if l_.get("_t"):
            mk["entrada"] = [l_["_t"], l_["preco_disparo"]]
        if l_.get("_ts"):
            mk["saida_r1"] = [l_["_ts"], l_["saida_sombra"]]; mk["R_r1"] = l_.get("R_sombra")
        tit = (f"{l_['lado']} · barra {l_['n_barra_dia']} ({l_['barra_rompimento'][11:16]}) fecha {l_['fechamento']:.2f} além de "
               + " e ".join(f"{z[0]:.2f}–{z[1]:.2f}" for z in l_["zonas_rompidas"]) + f" · gatilho {l_['gatilho']:.2f} · barra {l_['n_barra_seguinte']}: "
               + (f"1º minuto além {l_['primeiro_minuto_alem'][11:16]}, disparo {l_['preco_disparo']:.2f}" if l_["resultado_replay"] == "disparo" else l_["onde_parou"])
               + f" · R0 do gráfico: {l_['r0_na_barra']} · {l_['ordem']}"
               + (f" · DEIXOU PASSAR (sombra {l_['R_sombra']:+.2f} R, {l_['motivo_saida_sombra']})" if l_.get("R_sombra") is not None and not l_["ordem"].startswith("op") else ""))
        j = _janela(rep, "rompz", tit, l_["_b0"] - 900 * 6, l_["_b0"] + 900 * 8, mk, "REPLAY M15 fechado + M1 gravado (sem tick histórico) — ROMPZ em SOMBRA, nenhuma ordem")
        if j:
            j["marcas"]["rotulo_conf"] = "barra de rompimento"
            j["marcas"]["rotulo_saida"] = "DEIXOU PASSAR — sombra" if not l_["ordem"].startswith("op") else "saída"
            jan.append(j)
    for l_ in linhas:
        for k in ("_b0", "_t", "_ts"):
            l_.pop(k, None)
    return {"situacao": "ok", "versao": RZ.VERSAO, "linhas": linhas, "janelas": jan, "offset_servidor_s": off,
            "nota": ("Rompimento = fechamento além de suporte/resistência da memória O39 do M15 (só barras fechadas). Gatilho = mínima (venda) / máxima (compra) da barra "
                     "de rompimento ± 1 tick, válido só na barra seguinte. O 1º preço além é medido no M1 gravado: o tick exato não existe no histórico. "
                     "Espaço = filtro O53 (1,0 R líquido até a 1ª zona, M15 + H1). Resultado da sombra com gestão R0 neutra (stop 2 ATR, saída no canal EMA20).")}


# ════════════════════════════════════════════════════════════════════════
# seção 5
# ════════════════════════════════════════════════════════════════════════
def _eh_lateral(b):
    cod = str(b.get("mq5_codigo") or "")
    return ("BTLatDetectar" in cod) or ("BT_LATERAL" in cod)


def secao_5(sb, ids, de, ate, tz):
    if not ids:
        return {"titulo": "5. Lateral (O53): replay × sombra × execução observada", "bots": [], "nota": "nenhum bot no escopo"}
    rows = sb.table("conector_bots").select("id,nome,simbolo,magic_number,user_id,bot_token,config_operacional,mq5_codigo,excluido").in_("id", list(ids)).execute().data or []
    bots = []
    for b in rows:
        if not _eh_lateral(b) or b.get("excluido"):
            continue
        cfg = b.get("config_operacional") or {}
        tf = TF_CFG.get(str(cfg.get("timeframe_envio") or "15m").lower(), "M15")
        cod = str(b.get("mq5_codigo") or "")
        ea_v = "lateral-r1.2 (O53-C)" if "lateral-r1.2" in cod else "lateral-r1.1 (O53-B)" if "lateral-r1.1" in cod else ("lateral-r1 (O53)" if "lateral-r1" in cod else "R0 (O51)")
        obs = observado(sb, b, de, ate, tz)
        try:
            rep = replay(sb, str(b.get("simbolo") or "").upper(), tf, de, ate, spread=None)
        except Exception as e:
            rep = {"situacao": f"replay falhou: {str(e)[:200]}"}
        jan = janelas(rep, obs, tz)
        try:
            piv = pivos_auditoria(sb, b, tf, de, ate, tz)
        except Exception as e:
            piv = {"situacao": f"auditoria de pivôs falhou: {str(e)[:200]}"}
        try:
            trz = trilha_rompz(sb, b, tf, de, ate, tz)
        except Exception as e:
            trz = {"situacao": f"trilha de rompimento falhou: {str(e)[:200]}"}
        if isinstance(rep, dict):
            rep.pop("_velas", None)
        bots.append({"bot_id": int(b["id"]), "bot": b.get("nome"), "simbolo": b.get("simbolo"), "tf": tf, "ea_registrado_na_plataforma": ea_v,
                     "replay": rep, "observado": obs, "janelas": jan, "pivos": piv, "rompz": trz})
    return {"titulo": "5. Lateral (O53): replay × sombra × execução observada", "versao": VERSAO, "especificacao_congelada": ESPEC,
            "estados": {"replay": "motor de referência sobre candles gravados (equivalência tick a tick com o EA provada no teste local)",
                        "sombra": "decisões avaliadas sem ordem (reversão)", "execucao_observada": "negócios e eventos confirmados pelo MT5 via conector",
                        "regra": "código publicado, teste local e comportamento confirmado no terminal são três estados diferentes"},
            "criterio_das_janelas": f"todas as operações observadas (até 4) + sorteio fixo random.Random({SEMENTE}) de até 2 casos por categoria, nunca pelo resultado",
            "marcas": {"canal EMA20 High / Low": AMARELO + " (amarelo)", "zona à frente": "faixa verde (suporte) / laranja (resistência)", "invalidação": "violeta tracejado",
                       "stop 2 ATR": "vermelho pontilhado", "entrada": "triângulo violeta", "saída R0/observada": "X cinza", "saída R1": "X verde/vermelho com o R"},
            "bots": bots}
