"""ORDEM 050 — Relatório geral de diagnóstico da Learning Machine (BabyMachine).

Botão "🩺 Diagnóstico geral da LM" na tela principal da BabyMachine. Abre em "Últimas 48 horas"; início e fim escolhidos em Europe/Kyiv.
SÓ LEITURA: monta o relatório com o que já está gravado no banco (função lm_diag_o50, sql/0026) e grava o resultado em lm_diagnosticos.
O PDF e o JSON saem do MESMO registro gravado — mesmo período, mesmos filtros, mesmo horário de corte. Gerar o relatório não cria decisão,
comando nem ordem, e não altera campanha, bots ou regras.

Seções: 1 cobertura e saúde da coleta · 2 o que a LM viu e fez · 3 resultados e execução · 4 janelas de gráfico para a revisão diária.
Cada janela marca nível (suporte/resistência), barra do sinal, gatilho, entrada, saída, resultado em R e o canal EMA20 High/Low em amarelo
(#ffd60a), com o motivo no título (regra permanente do dono, 08/11/2026). Escolha das janelas por sorteio fixo (semente 50) dentro de cada
categoria, nunca pelo resultado; o registro completo de eventos vai no JSON."""
import io, json, math, random, hashlib, datetime as _dt
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

VERSAO = "diag-lm-1.0 (O50)"
FUSO_PADRAO = "Europe/Kyiv"
HORAS_PADRAO = 48
MAX_DIAS = 31
LACUNA_S = 120                    # intervalo entre snapshots acima disto = lacuna de coleta
SEMENTE = 50                      # sorteio fixo das janelas de gráfico
JANELAS_POR_CATEGORIA = 2
AMARELO = "#ffd60a"
UTC = _dt.timezone.utc


def _tz(nome):
    from zoneinfo import ZoneInfo
    for n in (nome, "Europe/Kyiv", "Europe/Kiev"):
        try:
            return ZoneInfo(n), n
        except Exception:
            continue
    return UTC, "UTC"


def _p(t):
    if t in (None, ""):
        return None
    if isinstance(t, (int, float)):
        return _dt.datetime.fromtimestamp(float(t), UTC)
    if isinstance(t, _dt.datetime):
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    try:
        d = _dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _iso(d):
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _loc(d, tz):
    return d.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S") if d else None


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _r(v, n=2):
    x = _f(v)
    return None if x is None else round(x, n)


def _conta(it):
    o = {}
    for x in it:
        o[x] = o.get(x, 0) + 1
    return o


def _pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def _quant(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q; i = int(math.floor(k)); j = min(i + 1, len(xs) - 1)
    return round(xs[i] + (xs[j] - xs[i]) * (k - i), 1)


def _dur(s):
    if s is None:
        return "—"
    s = int(round(s)); h, r = divmod(s, 3600); m, _ = divmod(r, 60)
    return (f"{h} h {m:02d} min" if h else f"{m} min") if s >= 60 else f"{s} s"


# ════════════════════════════════════════════════════════════════════════
# período (Europe/Kyiv) e corte
# ════════════════════════════════════════════════════════════════════════
def resolver_periodo(de_local=None, ate_local=None, fuso=FUSO_PADRAO, agora=None):
    """de/ate: 'AAAA-MM-DDTHH:MM' no fuso pedido (padrão Europe/Kyiv). Sem datas: últimas 48 h até o corte (agora).
    O corte nunca passa de 'agora': registros que chegarem depois não entram (o PDF e o JSON ficam iguais)."""
    tz, nome = _tz(fuso or FUSO_PADRAO)
    agora = (agora or _dt.datetime.now(UTC)).replace(microsecond=0)

    def conv(v):
        if v in (None, ""):
            return None
        d = _dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d.replace(tzinfo=tz) if d.tzinfo is None else d).astimezone(UTC)
    try:
        de, ate = conv(de_local), conv(ate_local)
    except Exception:
        raise HTTPException(status_code=422, detail="data inválida (use AAAA-MM-DDTHH:MM)")
    modo = "personalizado" if (de or ate) else "ultimas_48h"
    if ate is None or ate > agora:
        ate = agora
    if de is None:
        de = ate - _dt.timedelta(hours=HORAS_PADRAO)
    if de >= ate:
        raise HTTPException(status_code=422, detail="o início precisa ser antes do fim")
    if ate - de > _dt.timedelta(days=MAX_DIAS):
        raise HTTPException(status_code=422, detail=f"período máximo de {MAX_DIAS} dias")
    return {"modo": modo, "rotulo": "Últimas 48 horas" if modo == "ultimas_48h" else "Personalizado", "fuso": nome,
            "de_utc": _iso(de), "ate_utc": _iso(ate), "de_local": _loc(de, tz), "ate_local": _loc(ate, tz),
            "horas": round((ate - de).total_seconds() / 3600.0, 2), "corte_utc": _iso(ate), "corte_local": _loc(ate, tz),
            "regra_do_corte": "entram os registros com horário ≥ início e < corte; o que chegar depois do corte não entra neste relatório"}


# ════════════════════════════════════════════════════════════════════════
# EMA20 High/Low (mesma fórmula das janelas O48/O49: α = 2/21, início no 1º valor)
# ════════════════════════════════════════════════════════════════════════
def ema(xs, n=20):
    a = 2.0 / (n + 1); out = []; e = None
    for x in xs:
        e = x if e is None else a * x + (1 - a) * e
        out.append(e)
    return out


# ════════════════════════════════════════════════════════════════════════
# montagem do conteúdo (seções 1–4)
# ════════════════════════════════════════════════════════════════════════
CLASSE_REGRA = {   # regra gravada → classe pedida na ordem
    "R-CICLO-01.cv1_neutra": ("sem sinal", "o Ciclo ficou neutro: nenhum lado autorizado"),
    "R-CICLO-01.cv1_bloqueada": ("sinal bloqueado", "veto do motor do Ciclo (D1/H4 contra o M15)"),
    "R-CICLO-01.divergencia_motor_api": ("sinal bloqueado", "o motor autorizou, a API exigiu M1/M5 no lado (regra adicional)"),
    "R-CICLO-01.autorizada": ("sinal autorizado", "Ciclo autorizou o lado"),
    "R-CICLO-01.atestado": ("sem dados para avaliar", "o motor de Ciclos não entregou o atestado assinado da leitura"),
    "CLM.leitura_obrigatoria": ("sem dados para avaliar", "leitura obrigatória ausente"),
}


def _classe(decisao, regra, completa, tem_leitura, snapshots):
    if not tem_leitura:
        return ("sem dados para avaliar", "barra fechada com candle gravado, mas sem leitura da LM" if snapshots else
                "barra sem snapshot do conector (desconectado ou mercado sem cotação)")
    if completa is False:
        return ("sem dados para avaliar", "leitura incompleta")
    if regra in CLASSE_REGRA:
        return CLASSE_REGRA[regra]
    if decisao in ("comprar", "vender"):
        return ("sinal autorizado", regra or "regra não registrada")
    if decisao == "bloquear":
        return ("sinal bloqueado", regra or "regra não registrada")
    if decisao == "observar":
        return ("sem sinal", regra or "regra não registrada")
    return ("sem dados para avaliar", f"decisão não reconhecida: {decisao}")


def _card_de_uid(uid):
    return str(uid or "").split("|")[0] or None


def _lado_txt(v):
    if v in (1, "1", "compra", "comprar"):
        return "compra"
    if v in (-1, "-1", "venda", "vender"):
        return "venda"
    return str(v) if v is not None else "—"


def montar(raw, periodo, filtros, escopo, gerado=None):
    gerado = gerado or _dt.datetime.now(UTC).replace(microsecond=0)
    tz, _ = _tz(periodo["fuso"])
    de, ate = _p(periodo["de_utc"]), _p(periodo["ate_utc"])
    L = lambda d: _loc(_p(d), tz)
    est = (filtros.get("estrategia") or "").strip() or None
    bots = {int(b["id"]): b for b in raw.get("bots") or []}
    nome = lambda i: f"{(bots.get(int(i)) or {}).get('nome') or 'bot'} · {(bots.get(int(i)) or {}).get('simbolo') or '?'} (id {i})"

    # ── registros brutos (com o filtro de estratégia onde ele se aplica) ──
    esc = list(raw.get("escolhas") or [])
    decs = list(raw.get("decisoes") or [])
    abs_ = list(raw.get("aberturas") or [])
    cmds = list(raw.get("comandos") or [])
    cards_vistos = sorted({x for x in [e.get("card") for e in esc] + [d.get("card") for d in decs] + [a.get("card") for a in abs_] if x})
    if est:
        esc = [e for e in esc if e.get("card") == est]
        decs = [d for d in decs if d.get("card") == est]
        abs_ = [a for a in abs_ if a.get("card") == est]
        ids_cmd = {a.get("comando_id") for a in abs_}
        cmds = [m for m in cmds if m.get("id") in ids_cmd]

    # ── SEÇÃO 1 · cobertura e saúde da coleta ──
    col = {int(c["bot_id"]): c for c in raw.get("coleta") or []}
    cols_b = raw.get("barras_m15_colunas") or []
    barras = [dict(zip(cols_b, x)) for x in raw.get("barras_m15") or []]
    por_bot_barras = {}
    for b in barras:
        por_bot_barras.setdefault(int(b["bot_id"]), []).append(b)
    linhas_bots, ativos, tfs = [], {}, {}
    for t in raw.get("candles_por_tf") or []:
        tfs.setdefault(t["simbolo"], {})[t["tf"]] = {"barras": t["n"], "ultima_abertura_local": L(t.get("ultima_abertura"))}
    classes_tot = {"sem sinal": 0, "sinal bloqueado": 0, "sinal autorizado": 0, "sem dados para avaliar": 0}
    classes_bot, motivos_classe = {}, {}
    for bid, b in sorted(bots.items()):
        c = col.get(bid) or {}
        n = int(c.get("n_snapshots") or 0)
        prim, ult, ult_corte = _p(c.get("primeiro")), _p(c.get("ultimo")), _p(c.get("ultimo_antes_do_corte"))
        ini_s = (prim - de).total_seconds() if prim else None
        fim_s = (ate - ult).total_seconds() if ult else None
        bb = por_bot_barras.get(bid, [])
        if not n and not bb and b.get("excluido"):
            continue          # bot excluído sem nenhum registro no período: só entra na contagem
        cb = {k: 0 for k in classes_tot}
        for x in bb:
            k, why = _classe(x.get("decisao"), x.get("regra"), x.get("completa"), x.get("decisao") is not None, x.get("snapshots") or 0)
            cb[k] += 1; classes_tot[k] += 1
            motivos_classe.setdefault(k, {}).setdefault(why, 0); motivos_classe[k][why] += 1
        classes_bot[bid] = cb
        atrasos = [_f(x.get("atraso_primeira_leitura_s")) for x in bb if x.get("decisao") is not None]
        situ = ("coletando até o corte" if (fim_s is not None and fim_s <= LACUNA_S) else
                (f"parou de enviar em {L(ult)} ({_dur(fim_s)} antes do corte)" if ult else
                 (f"sem dados no período — último snapshot em {L(ult_corte)}" if ult_corte else "nenhum snapshot gravado")))
        linhas_bots.append({"bot_id": bid, "bot": b.get("nome"), "ativo": b.get("simbolo"), "estrategia_configurada": b.get("estrategia_nome"),
                            "timeframe_envio": b.get("timeframe_envio"), "excluido": bool(b.get("excluido")),
                            "ultimo_ping_local": L(b.get("ultimo_ping")), "ultimo_snapshot_local": L(ult_corte), "situacao": situ,
                            "snapshots": n, "primeiro_no_periodo_local": L(prim), "ultimo_no_periodo_local": L(ult),
                            "sem_dados_no_inicio": _dur(ini_s) if ini_s and ini_s > LACUNA_S else None,
                            "sem_dados_no_fim": _dur(fim_s) if fim_s and fim_s > LACUNA_S else None,
                            "lacunas_internas": int(c.get("n_lacunas") or 0), "lacunas_internas_total": _dur(_f(c.get("lacunas_s_total")) or 0),
                            "maiores_lacunas": [{"de_local": L(g["de"]), "ate_local": L(g["ate"]), "duracao": _dur(_f(g["s"]))} for g in (c.get("lacunas") or [])[:5]],
                            "barras_m15_fechadas": len(bb), "barras_com_leitura": sum(1 for x in bb if x.get("decisao") is not None),
                            "atraso_1a_leitura_p50_s": _quant(atrasos, .5), "atraso_1a_leitura_p95_s": _quant(atrasos, .95),
                            "classes": cb})
        if b.get("simbolo"):
            ativos.setdefault(b["simbolo"], []).append(bid)
    excl_sem = sum(1 for bid, b in bots.items() if b.get("excluido") and bid not in {x["bot_id"] for x in linhas_bots})
    tri = raw.get("trilha_contagem") or []
    tri_t = {}
    for t in tri:
        tri_t[f"{t['etapa']}·{t['estado']}"] = tri_t.get(f"{t['etapa']}·{t['estado']}", 0) + int(t["n"])
    saude = {k: tri_t.get(k, 0) for k in ("falha_coleta·falha", "falha_coleta·aviso", "snapshot·aviso", "persistencia·falha", "divergencia·aviso",
                                          "motor·aviso", "atestado·recusado", "leituras·aviso", "mercado·aviso")}
    versoes = raw.get("versoes") or {}
    sec1 = {
        "titulo": "1. Cobertura e saúde da coleta",
        "bots": linhas_bots, "bots_excluidos_sem_registro_no_periodo": excl_sem,
        "ativos": {a: [nome(i) for i in v] for a, v in ativos.items()},
        "estrategias": {"configuradas_nos_bots": sorted({b.get("estrategia_nome") for b in bots.values() if b.get("estrategia_nome")}),
                        "cards_com_sinal_no_periodo": cards_vistos, "filtro_aplicado": est or "sem filtro (todas)"},
        "timeframes_recebidos": tfs,
        "versoes": {"leitura_e_regras": [{"bot": nome(v["bot_id"]), "barras": v["n"], "de_local": L(v.get("de")), "ate_local": L(v.get("ate")), **(v.get("versoes") or {})}
                                         for v in versoes.get("ciclo_leituras") or []],
                    "leitor_do_motor": [{"bot": nome(v["bot_id"]), "leitor": v.get("leitor"), "ea": v.get("ea"), "barras": v["n"]} for v in versoes.get("leitor_motor") or []],
                    "selecao": [{"bot": nome(v["bot_id"]), "versao": v.get("versao"), "avaliacoes": v["n"]} for v in versoes.get("selecao") or []],
                    "modelo_treinado": "nenhum registro do modelo treinado no período" if not (raw.get("sombra_e_origem") or {}).get("lm_eventos") else "ver seção 2",
                    "diagnostico": VERSAO},
        "classificacao_das_barras_m15": {"total": classes_tot, "por_bot": {nome(k): v for k, v in classes_bot.items()},
                                         "motivos": motivos_classe,
                                         "regra": ("cada barra M15 fechada com candle gravado recebe UMA classe: 'sem sinal' (Ciclo neutro), 'sinal bloqueado' "
                                                   "(havia lado, uma regra vetou), 'sinal autorizado' (o Ciclo autorizou o lado — a seleção e os limites ainda "
                                                   "decidem se entra), 'sem dados para avaliar' (faltou leitura, atestado ou snapshot)"),
                                         "leituras_sem_candle_m15": len(raw.get("leituras_sem_candle_m15") or [])},
        "saude_na_trilha": saude,
        "regra_das_lacunas": f"lacuna = mais de {LACUNA_S} s sem snapshot do conector dentro do período; início/fim sem dados contam à parte",
    }

    # ── SEÇÃO 2 · o que a LM viu e fez ──
    cond = {}
    for c in raw.get("condicoes") or []:
        k = f"{nome(c['bot_id'])}"
        cond.setdefault(k, {}).setdefault(c["tf"], {}).setdefault(c["regime"], 0)
        cond[k][c["tf"]][c["regime"]] += int(c["n"])
    refs = []
    for a in raw.get("referencias") or []:
        n = int(a["n"])
        refs.append({"bot": nome(a["bot_id"]), "leituras_gravadas": n,
                     **{k: f"{a.get(c, 0)} ({_pct(a.get(c, 0), n)}%)" for k, c in (
                         ("zonas_suporte_resistencia", "com_zonas"), ("estrutura_por_tf", "com_estrutura_por_tf"), ("regime", "com_regime"),
                         ("indicadores", "com_indicadores"), ("offmind_niveis", "com_offmind"), ("candidatos_dos_cards", "com_candidatos"),
                         ("atestado_assinado", "com_atestado"), ("gestao_assinada", "com_gestao_assinada"), ("motor", "com_motor"))}})
    so = raw.get("sombra_e_origem") or {}
    lm_ev = sum(int(x["n"]) for x in so.get("lm_eventos") or [])
    lat_ev = sum(int(x["n"]) for x in so.get("lateral_eventos") or [])
    regras = [{"bot": nome(x["bot_id"]), "decisao": x["decisao"], "regra": x["regra"], "barras": x["n"], "sem_motivo": x["sem_motivo"],
               "classe": CLASSE_REGRA.get(x["regra"], ("—", ""))[0], "exemplo_de_motivo": x.get("exemplo_motivo")} for x in raw.get("leituras_por_regra") or []]
    ab_por_uid = {a.get("candidato_uid"): a for a in abs_}
    deixou = []
    barra_regra = {(int(b["bot_id"]), int(b["barra_epoch_utc"])): b for b in barras}
    for e in esc:
        if e.get("escolha_uid") in ab_por_uid:
            continue
        bm = _p(e.get("barra_m15")); k = (int(e["bot_id"]), int(bm.timestamp())) if bm else None
        bx = barra_regra.get(k) or {}
        motivo = (f"sem abertura até o corte; a barra terminou em '{bx.get('decisao')}' pela regra {bx.get('regra')}" if bx.get("regra") else "sem abertura até o corte — motivo não registrado")
        if bx.get("decisao") in ("comprar", "vender"):
            motivo = f"sem abertura até o corte; o Ciclo autorizou ({bx.get('regra')}) — motivo de não abrir não registrado"
        deixou.append({**e, "motivo_de_nao_entrar": motivo, "barra_decisao": bx.get("decisao"), "barra_regra": bx.get("regra")})
    mot = {}
    for t in raw.get("trilha_motivos") or []:
        mot.setdefault(f"{t['etapa']}·{t['estado']}", []).append({"motivo": t.get("motivo") or "motivo não registrado", "vezes": t["n"]})
    sem_motivo = {"leituras_sem_motivo": sum(int(x["sem_motivo"]) for x in raw.get("leituras_por_regra") or []),
                  "fechamentos_sem_motivo_de_saida": sum(1 for a in abs_ if a.get("estado") == "fechada" and not a.get("motivo_saida")),
                  "escolhas_sem_motivo": sum(1 for e in esc if not e.get("motivo")),
                  "deixou_passar_sem_motivo": sum(1 for d in deixou if "não registrado" in d["motivo_de_nao_entrar"])}
    sec2 = {
        "titulo": "2. O que a LM viu e o que fez",
        "condicoes_de_mercado": {"regime_por_tf (barras M15 com leitura)": cond, "fonte": "leitura do motor de Ciclos gravada por barra (ciclo_leituras.leituras.motor.por_tf)"},
        "referencias_disponiveis": refs,
        "o_que_chegou_a_cada_parte": [
            {"parte": "modelo treinado (LM-0.2, XGBoost congelado)", "origem": "modelo treinado",
             "registros_no_periodo": lm_ev, "leitura": ("nenhum evento do modelo treinado foi gravado no período: o modelo NÃO decidiu nada aqui e não há como "
                                                       "dizer o que ele recebeu" if not lm_ev else f"{lm_ev} eventos gravados (lm_eventos)")},
            {"parte": "regras programadas (Ciclo R-CICLO-01, seleção sel-7, gestão, limites)", "origem": "regra programada",
             "registros_no_periodo": sum(x["barras"] for x in regras), "leitura": "decidem as entradas e saídas da campanha DEMO; detalhe por regra abaixo"},
            {"parte": "leituras em sombra (cartão Rompimento de Lateralização / canal EMA20 O49)", "origem": "sombra",
             "registros_no_periodo": lat_ev, "bots_do_cartao": so.get("lateral_bots", 0),
             "leitura": "nenhuma leitura em sombra gravada no período (o leitor do cartão ainda não rodou no computador do MT5)" if not lat_ev else f"{lat_ev} eventos em sombra"},
        ],
        "decisoes_por_regra": regras,
        "por_que": {
            "entrou": [{"bot": nome(a["bot_id"]), "card": a.get("card"), "lado": _lado_txt(a.get("lado")), "abertura_local": L(a.get("ts_abertura")),
                        "motivo": next((e.get("motivo") for e in esc if e.get("escolha_uid") == a.get("candidato_uid")), None) or "seleção escolheu o candidato (motivo da escolha fora do período ou não registrado)",
                        "decisao_id": a.get("decisao_id")} for a in abs_ if a.get("ts_abertura") and de <= _p(a["ts_abertura"]) < ate],
            "deixou_passar": [{"bot": nome(d["bot_id"]), "card": d.get("card"), "lado": _lado_txt(d.get("lado")), "barra_local": L(d.get("barra_m15")),
                               "motivo": d["motivo_de_nao_entrar"]} for d in deixou],
            "deixou_passar_por_regra": {f"{x['regra']}": sum(y["barras"] for y in regras if y["regra"] == x["regra"]) for x in regras if x["classe"] == "sinal bloqueado"},
            "manteve": mot.get("gestao·ok", []) + mot.get("gestao·aviso", []),
            "fechou": [{"motivo_saida": k, "vezes": v} for k, v in sorted(_conta(a.get("motivo_saida") or "motivo não registrado" for a in abs_
                                                                              if a.get("estado") == "fechada" and _p(a.get("ts_fechamento")) and de <= _p(a["ts_fechamento"]) < ate).items(), key=lambda x: -x[1])],
            "vetos_e_limites": {k: v for k, v in mot.items() if k.split("·")[0] in ("veto", "limites", "autoridade_r01v5", "atestado")},
        },
        "sem_motivo_registrado": sem_motivo,
    }

    # ── SEÇÃO 3 · resultados e execução ──
    fech, abertas_corte, executadas = [], [], []
    for a in abs_:
        ta, tf_ = _p(a.get("ts_abertura")), _p(a.get("ts_fechamento"))
        if ta and de <= ta < ate:
            executadas.append(a)
        if tf_ and de <= tf_ < ate and a.get("estado") == "fechada":
            risco = _f(a.get("risco_planejado_usd")); res = _f(a.get("resultado_usd"))
            custo = (_f(a.get("comissao")) or 0) + (_f(a.get("swap")) or 0)
            fech.append({"id": a["id"], "bot": nome(a["bot_id"]), "card": a.get("card"), "lado": _lado_txt(a.get("lado")),
                         "entrada_local": L(a.get("ts_abertura")), "saida_local": L(a.get("ts_fechamento")),
                         "preco_entrada": _f(a.get("preco_entrada")), "preco_saida": _f(a.get("preco_saida")), "motivo_saida": a.get("motivo_saida") or "motivo não registrado",
                         "resultado_usd": _r(res), "custos_usd": _r(custo), "risco_planejado_usd": _r(risco),
                         "R": _r(res / risco, 2) if (res is not None and risco) else None})
        if ta and ta < ate and (tf_ is None or tf_ >= ate) and a.get("estado") != "cancelada":
            abertas_corte.append({"id": a["id"], "bot": nome(a["bot_id"]), "card": a.get("card"), "lado": _lado_txt(a.get("lado")), "entrada_local": L(a.get("ts_abertura")),
                                  "preco_entrada": _f(a.get("preco_entrada")), "stop_atual": _f(a.get("stop_atual"))})
    Rs = [x["R"] for x in fech if x["R"] is not None]
    dec_ids = {d["id"] for d in decs}
    cmd_stat = {}
    for m in cmds:
        cmd_stat.setdefault(f"{m.get('tipo')}·{m.get('status')}", 0); cmd_stat[f"{m.get('tipo')}·{m.get('status')}"] += 1
    nao_conf = [m for m in cmds if not m.get("confirmado_em")]
    autorizadas = classes_tot["sinal autorizado"]
    divergencias = []
    for d in decs:
        if d.get("status") not in ("consumida", "consumido") and not any(a.get("decisao_id") == d["id"] for a in abs_):
            divergencias.append({"tipo": "decisão emitida sem abertura", "bot": nome(d["bot_id"]), "decisao_id": d["id"], "status": d.get("status"),
                                 "barra_local": L(d.get("ts_barra")), "condicoes_reprovadas": d.get("condicoes_reprovadas")})
    for a in abs_:
        if a.get("ts_reserva") and de <= _p(a["ts_reserva"]) < ate and a.get("decisao_id") and a["decisao_id"] not in dec_ids:
            divergencias.append({"tipo": "abertura cuja decisão não está no período/filtro", "bot": nome(a["bot_id"]), "abertura_id": a["id"], "decisao_id": a["decisao_id"]})
        if a.get("ts_reserva") and de <= _p(a["ts_reserva"]) < ate and not a.get("ts_abertura") and a.get("estado") != "cancelada":
            divergencias.append({"tipo": "reserva sem execução no MT5", "bot": nome(a["bot_id"]), "abertura_id": a["id"], "estado": a.get("estado")})
        if a.get("estado") == "cancelada":
            divergencias.append({"tipo": "abertura cancelada", "bot": nome(a["bot_id"]), "abertura_id": a["id"], "motivo": a.get("motivo_cancelamento") or "motivo não registrado"})
    for x, a in [(x, a) for x in abertas_corte for a in abs_ if a["id"] == x["id"]]:
        uc = _p((col.get(int(a["bot_id"])) or {}).get("ultimo_antes_do_corte"))
        if uc is None or (ate - uc).total_seconds() > 3600:
            divergencias.append({"tipo": "posição aberta no registro sem dados do bot até o corte", "bot": nome(a["bot_id"]), "abertura_id": a["id"],
                                 "aberta_desde_local": L(a.get("ts_abertura")), "ultimo_snapshot_local": L(uc),
                                 "leitura": "o registro diz 'aberta', mas o conector não envia dados desde então: o estado real no MT5 não está confirmado"})
    for m in nao_conf:
        divergencias.append({"tipo": "comando sem confirmação do MT5 até o corte", "bot": nome(m["bot_id"]), "comando_id": m["id"], "comando": m.get("tipo"), "status": m.get("status")})
    if tri_t.get("divergencia·aviso"):
        divergencias.append({"tipo": "divergência registrada na trilha", "vezes": tri_t["divergencia·aviso"], "motivos": mot.get("divergencia·aviso", [])})
    bmo = sum(int(x["n"]) for x in so.get("babymachine_operacoes") or [])
    sec3 = {
        "titulo": "3. Resultados e execução",
        "sinais": {"barras_com_sinal_autorizado_pelo_ciclo": autorizadas, "barras_com_sinal_bloqueado": classes_tot["sinal bloqueado"],
                   "candidatos_escolhidos_pela_selecao": len(esc), "executados_no_mt5": len(executadas),
                   "deixou_passar_escolhidos_sem_abertura": len(deixou),
                   "nota": "o Ciclo autoriza um lado por barra; a seleção escolhe o candidato (card) e os limites decidem a abertura. Os números vêm de tabelas diferentes e não precisam somar."},
        "posicoes": {"abertas_no_periodo": len(executadas), "fechadas_no_periodo": len(fech), "abertas_no_corte": abertas_corte},
        "resultado": {"operacoes_fechadas": fech, "R_total": _r(sum(Rs), 2) if Rs else None, "R_medio": _r(sum(Rs) / len(Rs), 3) if Rs else None,
                      "vencedoras": sum(1 for x in fech if (x["resultado_usd"] or 0) > 0), "perdedoras": sum(1 for x in fech if (x["resultado_usd"] or 0) < 0),
                      "zeradas": sum(1 for x in fech if (x["resultado_usd"] or 0) == 0), "regra_vencedora": "pelo sinal do resultado em US$ (um ganho pequeno pode aparecer com R 0,00 por arredondamento)",
                      "resultado_usd_total": _r(sum(x["resultado_usd"] or 0 for x in fech)), "custos_usd_total": _r(sum(x["custos_usd"] or 0 for x in fech)),
                      "regra_do_R": "R = resultado em US$ ÷ risco planejado em US$ da abertura (stop inicial × lote); custos = comissão + swap"},
        "comandos_mt5": {"por_tipo_e_estado": cmd_stat, "sem_confirmacao": len(nao_conf)},
        "divergencias_decisao_x_execucao": divergencias,
        "origem_dos_dados": [
            {"origem": "replay (histórico reprocessado)", "registros": 0, "nota": "o banco não guarda replay; os replays das ordens O43–O49 estão nos arquivos de cada ordem"},
            {"origem": "simulação", "registros": 0, "nota": "nenhuma simulação gravada no banco"},
            {"origem": "sombra com cotações do MT5", "registros": lat_ev + lm_ev, "nota": "cartão Rompimento de Lateralização e eventos do modelo treinado"},
            {"origem": "ordens DEMO executadas (campanha)", "registros": len(executadas), "nota": "conta DEMO da campanha; operações BabyMachine gravadas no período: %d" % bmo},
        ],
    }

    # ── SEÇÃO 4 · janelas de gráfico ──
    sec4 = janelas(raw, abs_, esc, deixou, barras, tz, nome, de, ate)

    # ── perguntas da revisão diária ──
    total_barras = sum(classes_tot.values())
    viu = (f"{total_barras} barras M15 fechadas com candle em {len(linhas_bots)} bot(s); {sum(x['barras_com_leitura'] for x in linhas_bots)} com leitura da LM. "
           f"Referências presentes em quase todas as leituras (zonas, estrutura por TF, regime, candidatos)." if total_barras else
           "Nada: nenhum candle, snapshot ou leitura gravado no período.")
    fez = (f"Sem sinal {classes_tot['sem sinal']} · bloqueado {classes_tot['sinal bloqueado']} · autorizado {classes_tot['sinal autorizado']} barras; "
           f"{len(esc)} candidatos escolhidos, {len(executadas)} executados no MT5 (DEMO), {len(fech)} fechados"
           + (f", R total {sec3['resultado']['R_total']:+.2f}." if Rs else ".")) if total_barras or abs_ else "Nada: não houve decisão nem execução no período."
    if abertas_corte:
        fez += " Posição aberta no registro no corte: " + "; ".join(f"{x['bot']} {x['card']} {x['lado']} desde {x['entrada_local']}" for x in abertas_corte) + "."
    falt = []
    sem_dados_bots = [x for x in linhas_bots if x["snapshots"] == 0]
    if not linhas_bots or all(x["snapshots"] == 0 for x in linhas_bots):
        ult = max((x["ultimo_snapshot_local"] for x in linhas_bots if x["ultimo_snapshot_local"]), default=None, key=lambda s: _dt.datetime.strptime(s, "%d/%m/%Y %H:%M:%S"))
        falt.append(f"a coleta está parada: nenhum snapshot no período (último recebido em {ult or 'nunca'} {periodo['fuso']})")
    elif sem_dados_bots:
        falt.append("sem snapshot no período: " + ", ".join(f"{x['bot']} ({x['ativo']})" for x in sem_dados_bots))
    if classes_tot["sem dados para avaliar"]:
        falt.append(f"{classes_tot['sem dados para avaliar']} barras sem dados para avaliar ({'; '.join(f'{k}: {v}' for k, v in motivos_classe.get('sem dados para avaliar', {}).items())})")
    if not lm_ev:
        falt.append("modelo treinado (LM-0.2): nenhum registro no banco")
    if not lat_ev:
        falt.append("leituras em sombra (cartão lateral / canal EMA20): nenhum registro")
    for k, v in sem_motivo.items():
        if v:
            falt.append(f"{k.replace('_', ' ')}: {v}")
    if divergencias:
        falt.append(f"{len(divergencias)} divergência(s) entre decisão e execução (seção 3)")
    ausencias = [
        {"parte": "modelo treinado LM-0.2", "situacao": "sem dados" if not lm_ev else "com dados", "registros": lm_ev},
        {"parte": "leituras em sombra (cartão lateral / O49)", "situacao": "sem dados" if not lat_ev else "com dados", "registros": lat_ev},
        {"parte": "replay e simulação no banco", "situacao": "não existe no banco", "registros": 0},
        {"parte": "coleta do conector (snapshots)", "situacao": "sem dados" if not any(x["snapshots"] for x in linhas_bots) else "com dados", "registros": sum(x["snapshots"] for x in linhas_bots)},
        {"parte": "leituras da LM por barra (ciclo_leituras)", "situacao": "sem dados" if not sum(x["barras_com_leitura"] for x in linhas_bots) else "com dados", "registros": sum(x["barras_com_leitura"] for x in linhas_bots)},
        {"parte": "seleção (selecao_avaliacoes)", "situacao": "sem dados" if not raw.get("selecao") else "com dados", "registros": sum(int(x["n"]) for x in raw.get("selecao") or [])},
        {"parte": "decisões emitidas (ciclo_decisoes)", "situacao": "sem dados" if not decs else "com dados", "registros": len(decs)},
        {"parte": "aberturas/execução DEMO (sessao_aberturas)", "situacao": "sem dados" if not abs_ else "com dados", "registros": len(abs_)},
        {"parte": "comandos MT5", "situacao": "sem dados" if not cmds else "com dados", "registros": len(cmds)},
    ]
    conferencia = {"barras_m15": len(barras), "barras_com_leitura": sum(1 for b in barras if b.get("decisao") is not None),
                   "snapshots": sum(int((col.get(i) or {}).get("n_snapshots") or 0) for i in bots), "selecao_avaliacoes": sum(int(x["n"]) for x in raw.get("selecao") or []),
                   "escolhas_distintas": len(raw.get("escolhas") or []), "decisoes": len(raw.get("decisoes") or []), "aberturas_no_recorte": len(raw.get("aberturas") or []),
                   "comandos": len(raw.get("comandos") or []), "trilha": sum(int(t["n"]) for t in tri),
                   "nota": "contagens antes do filtro de estratégia, para conferir com as tabelas de origem"}
    return {
        "tipo": "diagnostico_geral_lm", "versao": VERSAO, "titulo": "Diagnóstico geral da Learning Machine",
        "gerado_utc": _iso(gerado), "gerado_local": _loc(gerado, tz), "periodo": periodo, "filtros": {"estrategia": est or "todas", "bots": filtros.get("bots") or "todos do escopo"},
        "escopo": escopo, "aviso": "Feito só com o que já está gravado. Gerar o relatório não cria decisão, comando nem ordem, e não altera campanha, bots ou regras.",
        "revisao_diaria": {"o_que_a_lm_conseguiu_ver": viu, "o_que_fez_com_isso": fez, "onde_faltou_dado_ou_explicacao": falt or ["nada faltou nos registros do período"]},
        "partes_sem_dados": ausencias,
        "secao_1": sec1, "secao_2": sec2, "secao_3": sec3, "secao_4": sec4,
        "conferencia_de_totais": conferencia,
        "registro_completo": {"barras_m15": barras, "escolhas": raw.get("escolhas") or [], "decisoes": raw.get("decisoes") or [], "aberturas": raw.get("aberturas") or [],
                              "comandos": raw.get("comandos") or [], "trilha_contagem": tri, "trilha_motivos": raw.get("trilha_motivos") or [],
                              "leituras_sem_candle_m15": raw.get("leituras_sem_candle_m15") or [], "coleta": raw.get("coleta") or [],
                              "candles_por_tf": raw.get("candles_por_tf") or [], "sombra_e_origem": so, "fonte": "função lm_diag_o50 (sql/0026)"},
    }


# ════════════════════════════════════════════════════════════════════════
# SEÇÃO 4 — janelas de gráfico (sorteio fixo dentro de cada categoria)
# ════════════════════════════════════════════════════════════════════════
def janelas(raw, abs_, esc, deixou, barras, tz, nome, de, ate):
    cols = raw.get("candles_m15_colunas") or ["bot_id", "abertura_epoch_utc", "o", "h", "l", "c"]
    velas = {}
    for x in raw.get("candles_m15_grafico") or []:
        d = dict(zip(cols, x)); velas.setdefault(int(d["bot_id"]), []).append(d)
    ema_bot = {}
    for b, v in velas.items():
        v.sort(key=lambda d: d["abertura_epoch_utc"])
        ema_bot[b] = (ema([float(d["h"]) for d in v]), ema([float(d["l"]) for d in v]))
    esc_uid = {e.get("escolha_uid"): e for e in esc}
    cat = {"entrou e venceu": [], "entrou e perdeu": [], "deixou passar": []}
    for a in abs_:
        tf_, ta = _p(a.get("ts_fechamento")), _p(a.get("ts_abertura"))
        if a.get("estado") == "fechada" and ta and tf_ and de <= tf_ < ate:
            res = _f(a.get("resultado_usd"))
            if res is None:
                continue
            cat["entrou e venceu" if res > 0 else "entrou e perdeu"].append(("ab", a))
    for d in deixou:
        cat["deixou passar"].append(("dp", d))
    rng = random.Random(SEMENTE); out = []
    criterio = (f"sorteio fixo (random.Random({SEMENTE})) de até {JANELAS_POR_CATEGORIA} casos dentro de cada categoria, na ordem dos registros; "
                "nunca pelo resultado. Categorias: entrou e venceu · entrou e perdeu · deixou passar (candidato escolhido pela seleção sem abertura).")
    for nomecat, itens in cat.items():
        itens = sorted(itens, key=lambda t: str(t[1].get("ts_reserva") or t[1].get("criado_em") or ""))
        esc_ = rng.sample(range(len(itens)), min(JANELAS_POR_CATEGORIA, len(itens))) if itens else []
        if not itens:
            out.append({"categoria": nomecat, "candidatos": 0, "titulo": f"sem caso no período: {nomecat}"}); continue
        for i in sorted(esc_):
            tipo, x = itens[i]
            j = _janela(tipo, x, velas, ema_bot, esc_uid, tz, nome, nomecat, len(itens))
            if j:
                out.append(j)
    return {"titulo": "4. Janelas de gráfico para a revisão diária", "criterio_de_selecao": criterio,
            "marcas": {"canal EMA20 High / EMA20 Low": AMARELO + " (amarelo, traço mais grosso que as velas)", "resistência M15": "#eb6834 (laranja)",
                       "suporte M15": "#1baf7a (verde)", "gatilho / referência do sinal": "#6250d6 (violeta, tracejado)", "stop inicial": "#d63a3a (vermelho, pontilhado)",
                       "barra da decisão / do candidato": "retângulo laranja", "entrada": "triângulo violeta", "saída": "X verde (ganho) ou vermelho (perda) com o R"},
            "rotulo_dos_dados": "dados reais da coleta ao vivo da conta DEMO (snapshots do EA) — não é replay nem simulação",
            "janelas": out}


def _janela(tipo, x, velas, ema_bot, esc_uid, tz, nome, cat, ncand):
    bid = int(x["bot_id"]); v = velas.get(bid) or []
    if not v:
        return {"categoria": cat, "candidatos": ncand, "titulo": f"{cat}: sem candles M15 gravados para {nome(bid)}", "sem_grafico": True}
    eH, eL = ema_bot[bid]
    ts = [d["abertura_epoch_utc"] for d in v]

    def idx(t):
        t = _p(t)
        if not t:
            return None
        e = t.timestamp(); k = max(0, min(len(ts) - 1, int(sum(1 for z in ts if z <= e)) - 1))
        return k
    if tipo == "ab":
        e = esc_uid.get(x.get("candidato_uid")) or {}
        i_sinal = idx(x.get("ts_barra")); i_ent = idx(x.get("ts_abertura")); i_sai = idx(x.get("ts_fechamento"))
        risco = _f(x.get("risco_planejado_usd")); res = _f(x.get("resultado_usd"))
        R = res / risco if (res is not None and risco) else None
        gatilho, stop = _f(x.get("preco_ref")), _f(x.get("stop_inicial"))
        p_ent, p_sai = _f(x.get("preco_entrada")), _f(x.get("preco_saida"))
        motivo = x.get("motivo_saida") or "motivo não registrado"
        titulo = (f"{cat.upper()} · {nome(bid)} · {x.get('card')} {_lado_txt(x.get('lado'))} · entrada {_loc(_p(x.get('ts_abertura')), tz)} · "
                  f"saída por {motivo} · {R:+.2f} R" if R is not None else f"{cat.upper()} · {nome(bid)} · {x.get('card')} · R não calculável (sem risco planejado)")
        por_que = (e.get("motivo") or "motivo da escolha não registrado no período")
    else:
        e = x
        i_sinal = idx(x.get("barra_m15")); i_ent = i_sai = None; R = None
        gatilho, stop, p_ent, p_sai = _f(x.get("entrada")), _f(x.get("stop")), None, None
        titulo = f"DEIXOU PASSAR · {nome(bid)} · {x.get('card')} {_lado_txt(x.get('lado'))} · barra {_loc(_p(x.get('barra_m15')), tz)} · {x.get('motivo_de_nao_entrar')}"
        por_que = x.get("motivo") or "motivo da escolha não registrado"
    if i_sinal is None:
        return {"categoria": cat, "candidatos": ncand, "titulo": titulo + " — barra do sinal fora dos candles gravados", "sem_grafico": True}
    fim = max(i for i in (i_sinal, i_ent, i_sai) if i is not None)
    i0 = max(0, i_sinal - 30); i1 = min(len(v), fim + 6)
    aquec = i0               # barras ANTES da janela usadas para a EMA (o cálculo começa no 1º candle buscado)
    jan = v[i0:i1]
    rel = lambda i: None if i is None else i - i0
    return {"categoria": cat, "candidatos": ncand, "bot": nome(bid), "titulo": titulo, "por_que": por_que, "fuso": getattr(tz, "key", FUSO_PADRAO),
            "nome_barra": "barra da decisão" if tipo == "ab" else "barra do candidato",
            "rotulo": "dados reais da coleta ao vivo (conta DEMO) — não é replay nem simulação",
            "velas": [[d["abertura_epoch_utc"], _f(d["o"]), _f(d["h"]), _f(d["l"]), _f(d["c"])] for d in jan],
            "ema20_high": [_r(z, 4) for z in eH[i0:i1]], "ema20_low": [_r(z, 4) for z in eL[i0:i1]],
            "ema_aquecimento_barras": aquec, "ema_confiavel": aquec >= 60,
            "marcas": {"barra_sinal": rel(i_sinal), "entrada": None if i_ent is None else [rel(i_ent), p_ent], "saida": None if i_sai is None else [rel(i_sai), p_sai],
                       "gatilho": gatilho, "stop": stop, "suporte": _f(e.get("suporte_m15")), "resistencia": _f(e.get("resistencia_m15")), "R": _r(R, 2)}}


# ════════════════════════════════════════════════════════════════════════
# PDF (mesmo conteúdo gravado)
# ════════════════════════════════════════════════════════════════════════
_TROCAS = {"→": "->", "←": "<-", "×": "x", "·": "-", "—": "-", "–": "-", "≥": ">=", "≤": "<=", "≠": "!=", "−": "-", "…": "...", "“": '"', "”": '"',
           "‘": "'", "’": "'", "✔": "ok", "✖": "x", "•": "-", "🩺": ""}


def _t(v, lim=None):
    if v is None:
        s = "—"
    elif isinstance(v, bool):
        s = "sim" if v else "não"
    elif isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
    else:
        s = str(v)
    for a, b in _TROCAS.items():
        s = s.replace(a, b)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s if not lim or len(s) <= lim else s[:lim - 3] + "..."


def grafico_png(j):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    V = j["velas"]; M = j["marcas"]; n = len(V)
    fig, ax = plt.subplots(figsize=(11, 4.4), facecolor="#fcfcfb")
    for x, (t, o, h, l, c) in enumerate(V):
        ax.plot([x, x], [l, h], color="#52514e", lw=0.8, zorder=2)
        ax.add_patch(Rectangle((x - 0.3, min(o, c)), 0.6, max(abs(c - o), 1e-9), facecolor="#ffffff" if c >= o else "#52514e", edgecolor="#52514e", lw=0.7, zorder=3))
    xs = list(range(n))
    ax.plot(xs, j["ema20_high"], color=AMARELO, lw=2.4, zorder=4, label="EMA20 High")
    ax.plot(xs, j["ema20_low"], color=AMARELO, lw=2.4, zorder=4, label="EMA20 Low")
    for serie, txt in ((j["ema20_high"], "EMA20 High"), (j["ema20_low"], "EMA20 Low")):
        if serie and serie[-1] is not None:
            ax.text(n - 0.4, serie[-1], " " + txt, color="#8a6d00", fontsize=6.8, va="center")
    if M.get("resistencia"):
        ax.axhline(M["resistencia"], color="#eb6834", lw=1.3, zorder=1, label=f"resistência M15 (registrada na seleção) {M['resistencia']:.2f}")
    if M.get("suporte"):
        ax.axhline(M["suporte"], color="#1baf7a", lw=1.3, zorder=1, label=f"suporte M15 (registrado na seleção) {M['suporte']:.2f}")
    if M.get("gatilho"):
        ax.axhline(M["gatilho"], color="#6250d6", lw=1.2, ls="--", zorder=1, label=f"gatilho/referência {M['gatilho']:.2f}")
    if M.get("stop"):
        ax.axhline(M["stop"], color="#d63a3a", lw=1.0, ls=":", zorder=1, label=f"stop inicial {M['stop']:.2f}")
    bs = M.get("barra_sinal")
    if bs is not None and 0 <= bs < n:
        t, o, h, l, c = V[bs]
        ax.add_patch(Rectangle((bs - 0.45, l), 0.9, h - l, fill=False, edgecolor="#eb6834", lw=2, zorder=5)); ax.text(bs, h, j.get("nome_barra") or "sinal", color="#eb6834", fontsize=7.5, ha="center", va="bottom")
    if M.get("entrada"):
        xe, pe = M["entrada"]
        if pe is not None:
            ax.plot(xe, pe, marker="^", ms=10, color="#6250d6", zorder=6, label="entrada")
    if M.get("saida"):
        xs_, ps = M["saida"]
        if ps is not None:
            ax.plot(xs_, ps, "X", ms=10, color="#1baf7a" if (M.get("R") or 0) > 0 else "#d63a3a", zorder=6, label="saída")
            if M.get("R") is not None:
                ax.text(xs_, ps, f"  {M['R']:+.2f} R", fontsize=8.5, fontweight="bold", va="center")
    st = max(1, n // 8); tzj, nomej = _tz(j.get("fuso") or FUSO_PADRAO)
    ax.set_xticks(range(0, n, st)); ax.set_xticklabels([_dt.datetime.fromtimestamp(V[i][0], UTC).astimezone(tzj).strftime("%d/%m %H:%M") for i in range(0, n, st)], fontsize=7)
    ax.set_xlabel(f"barras M15 (abertura, horário {nomej})", fontsize=7)
    ax.set_xlim(-1, n + 4)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color="#e6e5e0", lw=0.5); ax.set_facecolor("#fcfcfb"); ax.tick_params(labelsize=7)
    ax.legend(loc="upper left", fontsize=6.5, frameon=False, ncol=4)
    ax.set_title(j["rotulo"], fontsize=7, loc="right", color="#52514e")
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png", dpi=110, facecolor="#fcfcfb"); plt.close(fig)
    return buf.getvalue()


def pdf(c):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    rid = c.get("relatorio_id") or "-"

    class P(FPDF):
        def header(self):
            self.set_font("Helvetica", "", 7); self.set_text_color(110)
            self.cell(0, 4, _t(f"BotTested - Diagnóstico geral da LM - {rid} - corte {c['periodo']['corte_local']} {c['periodo']['fuso']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.ln(1)

        def footer(self):
            self.set_y(-10); self.set_font("Helvetica", "", 7); self.set_text_color(110)
            self.cell(0, 4, _t(f"sha256 do conteúdo {str(c.get('sha256_do_conteudo') or '')[:24]}...   página {self.page_no()}/{{nb}}"), align="R")
    d = P(orientation="P", unit="mm", format="A4"); d.set_auto_page_break(True, margin=14); d.set_margins(12, 12, 12); d.add_page()
    W = 210 - 24

    def h1(t):
        d.ln(2); d.set_font("Helvetica", "B", 12); d.set_text_color(20); d.multi_cell(0, 6, _t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        d.set_draw_color(160); d.line(12, d.get_y(), 198, d.get_y()); d.ln(1.5)

    def h2(t):
        d.ln(1); d.set_font("Helvetica", "B", 9.5); d.set_text_color(40); d.multi_cell(0, 5, _t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def p(t, b=False, tam=8.3):
        d.set_font("Helvetica", "B" if b else "", tam); d.set_text_color(30); d.multi_cell(0, 4.1, _t(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def kv(pares):
        for k, v in pares:
            d.set_font("Helvetica", "B", 8.2); d.set_text_color(60); d.cell(52, 4.3, _t(k, 40))
            d.set_font("Helvetica", "", 8.2); d.set_text_color(20); d.multi_cell(0, 4.3, _t(v), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def tab(cab, linhas, larg, lim=90):
        if not linhas:
            p("sem linhas"); return
        d.set_font("Helvetica", "B", 7); d.set_fill_color(235)
        for k, w in zip(cab, larg):
            d.cell(w, 4.6, _t(k, 40), border=1, fill=True)
        d.ln()
        d.set_font("Helvetica", "", 6.8)
        for l in linhas:
            if d.get_y() > 275:
                d.add_page()
            for k, w in zip(l, larg):
                d.cell(w, 4.3, _t(k, max(6, int(w * 0.62)) if lim else None), border=1)
            d.ln()

    P_ = c["periodo"]
    d.set_font("Helvetica", "B", 15); d.multi_cell(0, 8, _t("Diagnóstico geral da Learning Machine"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    p(c.get("aviso"))
    kv([("Relatório", rid), ("Período", f"{P_['rotulo']}: {P_['de_local']} -> {P_['ate_local']} ({P_['fuso']}) · {P_['horas']} h"),
        ("Período em UTC", f"{P_['de_utc']} -> {P_['ate_utc']}"), ("Corte", f"{P_['corte_local']} {P_['fuso']} ({P_['corte_utc']}) — {P_['regra_do_corte']}"),
        ("Filtros", f"estratégia: {c['filtros']['estrategia']} · bots: {c['filtros']['bots']}"), ("Escopo", c.get("escopo")),
        ("Gerado", f"{c.get('gerado_local')} {P_['fuso']} · {VERSAO}"), ("sha256 do conteúdo", c.get("sha256_do_conteudo"))])
    h1("Revisão diária — as três perguntas")
    R = c["revisao_diaria"]
    kv([("O que a LM conseguiu ver", R["o_que_a_lm_conseguiu_ver"]), ("O que fez com isso", R["o_que_fez_com_isso"])])
    p("Onde faltou dado ou explicação:", b=True)
    for x in R["onde_faltou_dado_ou_explicacao"]:
        p(" - " + x)
    h2("Partes da LM sem dados no período")
    tab(["parte", "situação", "registros"], [[x["parte"], x["situacao"], x["registros"]] for x in c["partes_sem_dados"]], [96, 60, 30])

    S1 = c["secao_1"]; h1(S1["titulo"])
    tab(["bot", "ativo", "situação", "snap.", "barras", "c/ leitura", "atraso p50/p95"],
        [[f"{b['bot']} ({b['bot_id']})", b["ativo"], b["situacao"], b["snapshots"], b["barras_m15_fechadas"], b["barras_com_leitura"],
          f"{b['atraso_1a_leitura_p50_s']}/{b['atraso_1a_leitura_p95_s']} s"] for b in S1["bots"]], [34, 18, 62, 16, 14, 16, 26])
    p(f"Bots excluídos sem registro no período: {S1['bots_excluidos_sem_registro_no_periodo']}. Atraso = segundos entre a abertura da barra M15 e a 1ª leitura gravada.", tam=7.5)
    h2("Desconexões, atrasos e lacunas")
    for b in S1["bots"]:
        kv([(f"{b['bot']} ({b['ativo']})", f"sem dados no início: {b['sem_dados_no_inicio'] or 'não'} · no fim: {b['sem_dados_no_fim'] or 'não'} · lacunas internas: "
                                            f"{b['lacunas_internas']} ({b['lacunas_internas_total']})" + (" · maiores: " + "; ".join(f"{g['de_local']} -> {g['ate_local']} ({g['duracao']})" for g in b["maiores_lacunas"]) if b["maiores_lacunas"] else ""))])
    p(S1["regra_das_lacunas"], tam=7.3)
    h2("Sem sinal × sinal bloqueado × sem dados para avaliar (barras M15)")
    C = S1["classificacao_das_barras_m15"]
    tab(["bot"] + list(C["total"].keys()), [[k] + list(v.values()) for k, v in C["por_bot"].items()] + [["TOTAL"] + list(C["total"].values())], [62, 30, 32, 32, 30])
    for k, v in C["motivos"].items():
        p(f"{k}: " + "; ".join(f"{a} ({b})" for a, b in v.items()), tam=7.4)
    p(C["regra"], tam=7.2)
    h2("Ativos, estratégias, timeframes e versões")
    kv([("Ativos", "; ".join(f"{a}: {', '.join(v)}" for a, v in S1["ativos"].items()) or "nenhum"),
        ("Estratégias", f"configuradas: {', '.join(S1['estrategias']['configuradas_nos_bots']) or '—'} · cards com sinal: {', '.join(S1['estrategias']['cards_com_sinal_no_periodo']) or 'nenhum'} · filtro: {S1['estrategias']['filtro_aplicado']}"),
        ("Timeframes recebidos", "; ".join(f"{a}: " + ", ".join(f"{t} {x['barras']}" for t, x in v.items()) for a, v in S1["timeframes_recebidos"].items()) or "nenhum candle no período")])
    for v in S1["versoes"]["leitura_e_regras"]:
        kv([(v["bot"], f"API {v.get('api')} · EA {v.get('ea')} · conector {v.get('conector')} · regras {v.get('regras')} ({v['barras']} barras)")])
    kv([("Seleção", "; ".join(f"{x['bot']}: {x['versao']} ({x['avaliacoes']})" for x in S1["versoes"]["selecao"]) or "—"),
        ("Modelo treinado", S1["versoes"]["modelo_treinado"]), ("Saúde na trilha", "; ".join(f"{k} {v}" for k, v in S1["saude_na_trilha"].items() if v) or "nenhum aviso/falha")])

    S2 = c["secao_2"]; h1(S2["titulo"])
    h2("Condições de mercado (regime do motor por TF)")
    for b, tfs in S2["condicoes_de_mercado"]["regime_por_tf (barras M15 com leitura)"].items():
        kv([(b, " | ".join(f"{tf}: " + ", ".join(f"{r} {n}" for r, n in sorted(rr.items(), key=lambda z: -z[1])) for tf, rr in tfs.items()))])
    h2("Referências disponíveis nas leituras gravadas")
    for r in S2["referencias_disponiveis"]:
        kv([(r["bot"], " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in r.items() if k not in ("bot",)))])
    h2("O que chegou a cada parte: modelo treinado × regras programadas × sombra")
    tab(["parte", "origem", "registros", "leitura"], [[x["parte"], x["origem"], x["registros_no_periodo"], x["leitura"]] for x in S2["o_que_chegou_a_cada_parte"]], [52, 24, 16, 94])
    h2("Decisões por regra (barras M15)")
    tab(["bot", "decisão", "regra", "classe", "barras", "sem motivo"], [[x["bot"], x["decisao"], x["regra"], x["classe"], x["barras"], x["sem_motivo"]] for x in S2["decisoes_por_regra"]], [46, 18, 56, 32, 14, 20])
    PQ = S2["por_que"]
    h2("Por que entrou")
    for x in PQ["entrou"]:
        p(f"- {x['bot']} · {x['card']} {x['lado']} · {x['abertura_local']}: {x['motivo']}", tam=7.4)
    if not PQ["entrou"]:
        p("nenhuma entrada no período")
    h2("Por que deixou passar")
    for x in PQ["deixou_passar"]:
        p(f"- {x['bot']} · {x['card']} {x['lado']} · barra {x['barra_local']}: {x['motivo']}", tam=7.4)
    p("Barras bloqueadas por regra: " + ("; ".join(f"{k} {v}" for k, v in PQ["deixou_passar_por_regra"].items()) or "nenhuma"), tam=7.6)
    h2("Por que manteve")
    for x in PQ["manteve"][:10]:
        p(f"- ({x['vezes']}x) {x['motivo']}", tam=7.2)
    if not PQ["manteve"]:
        p("nenhum registro de gestão no período")
    h2("Por que fechou")
    p("; ".join(f"{x['motivo_saida']} {x['vezes']}" for x in PQ["fechou"]) or "nenhum fechamento no período")
    h2("Sem motivo registrado")
    kv([(k.replace("_", " "), v) for k, v in S2["sem_motivo_registrado"].items()])

    S3 = c["secao_3"]; h1(S3["titulo"])
    kv([(k.replace("_", " "), v) for k, v in S3["sinais"].items()])
    kv([("Posições abertas no período", S3["posicoes"]["abertas_no_periodo"]), ("Fechadas no período", S3["posicoes"]["fechadas_no_periodo"]),
        ("Abertas no corte", "; ".join(f"{x['bot']} {x['card']} {x['lado']} desde {x['entrada_local']}" for x in S3["posicoes"]["abertas_no_corte"]) or "nenhuma")])
    RR = S3["resultado"]
    kv([("R total / médio", f"{RR['R_total']} / {RR['R_medio']}"), ("Vencedoras / perdedoras / zeradas", f"{RR['vencedoras']} / {RR['perdedoras']} / {RR['zeradas']}"),
        ("Resultado / custos (US$)", f"{RR['resultado_usd_total']} / {RR['custos_usd_total']}"), ("Regra do R", RR["regra_do_R"])])
    tab(["bot", "card", "lado", "entrada", "saída", "motivo", "US$", "custo", "R"],
        [[x["bot"].split(" (")[0], x["card"], x["lado"], x["entrada_local"][:16] if x["entrada_local"] else "—", x["saida_local"][:16] if x["saida_local"] else "—",
          x["motivo_saida"], x["resultado_usd"], x["custos_usd"], x["R"]] for x in RR["operacoes_fechadas"]], [30, 30, 12, 24, 24, 26, 14, 12, 14])
    h2("Comandos ao MT5")
    kv([("Por tipo e estado", "; ".join(f"{k} {v}" for k, v in S3["comandos_mt5"]["por_tipo_e_estado"].items()) or "nenhum"), ("Sem confirmação", S3["comandos_mt5"]["sem_confirmacao"])])
    h2("Divergências entre a decisão registrada e a execução observada")
    for x in S3["divergencias_decisao_x_execucao"]:
        p("- " + "; ".join(f"{k}: {v}" for k, v in x.items()), tam=7.2)
    if not S3["divergencias_decisao_x_execucao"]:
        p("nenhuma divergência nos registros do período")
    h2("Origem dos dados")
    tab(["origem", "registros", "nota"], [[x["origem"], x["registros"], x["nota"]] for x in S3["origem_dos_dados"]], [58, 18, 110])

    S4 = c["secao_4"]; h1(S4["titulo"])
    p(S4["criterio_de_selecao"], tam=7.6); p("Marcas: " + "; ".join(f"{k} = {v}" for k, v in S4["marcas"].items()), tam=7.2); p(S4["rotulo_dos_dados"], b=True, tam=7.6)
    for j in S4["janelas"]:
        if d.get_y() > 190:
            d.add_page()
        p(j["titulo"], b=True, tam=8)
        if j.get("velas"):
            png = grafico_png(j)
            d.image(io.BytesIO(png), x=12, w=W)
            p("Por quê: " + str(j.get("por_que")), tam=7.2)
            p(f"Categoria '{j['categoria']}' com {j['candidatos']} caso(s); EMA20 calculada com {j['ema_aquecimento_barras']} barras antes da janela"
              + ("" if j.get("ema_confiavel") else " (menos de 60: a EMA ainda pode estar se ajustando)"), tam=7)
        d.ln(2)
    h1("Conferência de totais (antes do filtro)")
    kv([(k.replace("_", " "), v) for k, v in c["conferencia_de_totais"].items()])
    p("O registro completo de eventos (barras, escolhas, decisões, aberturas, comandos, trilha) está no JSON deste mesmo relatório.", tam=7.5)
    return bytes(d.output())


# ════════════════════════════════════════════════════════════════════════
# rotas
# ════════════════════════════════════════════════════════════════════════
class DiagIn(BaseModel):
    de: Optional[str] = None          # 'AAAA-MM-DDTHH:MM' no fuso
    ate: Optional[str] = None
    fuso: Optional[str] = FUSO_PADRAO
    estrategia: Optional[str] = None  # card; vazio = todas
    bots: Optional[List[int]] = None  # vazio = todos do escopo


class DiagBaixarIn(BaseModel):
    relatorio_id: str
    formato: str = "pdf"


def criar_router(sb_admin, sessao_user_id, eh_admin, relogio=None):
    r = APIRouter()

    def _sb():
        sb = sb_admin()
        if sb is None:
            raise HTTPException(status_code=500, detail="Supabase indisponível")
        return sb

    def _escopo(sb, uid):
        rows = sb.table("conector_bots").select("id,user_id").execute().data or []
        adm = bool(eh_admin(uid))
        ids = sorted(int(b["id"]) for b in rows if adm or str(b.get("user_id")) == str(uid))
        users = None if adm else [str(uid)]
        return ids, users, ("administrador: todos os bots do ambiente" if adm else "bots desta conta")

    @r.post("/learning/diagnostico/gerar")
    def gerar(req: DiagIn, authorization: str = Header(default="")):
        uid = sessao_user_id(authorization); sb = _sb()
        agora = (relogio() if relogio else _dt.datetime.now(UTC)).replace(microsecond=0)
        per = resolver_periodo(req.de, req.ate, req.fuso, agora)
        ids, users, esc_txt = _escopo(sb, uid)
        if req.bots:
            ids = [i for i in ids if i in set(int(b) for b in req.bots)]
        raw = (sb.rpc("lm_diag_o50", {"p_de": per["de_utc"], "p_ate": per["ate_utc"], "p_bots": ids, "p_users": users, "p_gap_s": LACUNA_S}).execute().data) if ids else {}
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        c = montar(raw or {}, per, {"estrategia": req.estrategia, "bots": req.bots}, esc_txt, gerado=agora)
        bruto = json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        sha = hashlib.sha256(bruto.encode("utf-8")).hexdigest()
        rid = "DIAG-%s-%s" % (per["corte_utc"].replace("-", "").replace(":", ""), sha[:10])
        c = dict(c, relatorio_id=rid, sha256_do_conteudo=sha)
        try:
            sb.table("lm_diagnosticos").insert({"id": rid, "user_id": uid, "periodo": per, "filtros": c["filtros"], "corte_utc": per["corte_utc"],
                                                "sha256": sha, "conteudo": json.loads(json.dumps(c, default=str))}).execute()
            c["persistido"] = True
        except Exception as e:
            c["persistido"] = False; c["aviso_persistencia"] = f"relatório não foi gravado (sql/0026 aplicada?): {str(e)[:140]}"
        return JSONResponse(content=json.loads(json.dumps(c, default=str)), headers={"Cache-Control": "no-store"})

    @r.post("/learning/diagnostico/baixar")
    def baixar(req: DiagBaixarIn, authorization: str = Header(default="")):
        import re
        uid = sessao_user_id(authorization); sb = _sb()
        if not re.fullmatch(r"DIAG-\d{8}T\d{6}Z-[0-9a-f]{10}", str(req.relatorio_id or "")):
            raise HTTPException(status_code=404, detail="relatorio nao encontrado")
        rows = sb.table("lm_diagnosticos").select("id,user_id,sha256,conteudo").eq("id", req.relatorio_id).limit(1).execute().data or []
        if not rows or str(rows[0].get("user_id")) != str(uid):
            raise HTTPException(status_code=404, detail="relatorio nao encontrado")
        c = dict(rows[0]["conteudo"] or {}); c["persistido"] = True
        fmt = str(req.formato or "pdf").lower()
        if fmt == "json":
            corpo = json.dumps(c, ensure_ascii=False, indent=1, default=str).encode("utf-8"); mt = "application/json; charset=utf-8"
        elif fmt == "pdf":
            corpo = pdf(c); mt = "application/pdf"
        else:
            raise HTTPException(status_code=422, detail="formato invalido (pdf ou json)")
        return Response(content=corpo, media_type=mt, headers={
            "Content-Disposition": f'attachment; filename="{rows[0]["id"]}.{fmt}"', "Cache-Control": "no-store",
            "X-BotTested-Relatorio-Id": rows[0]["id"], "X-BotTested-Conteudo-SHA256": str(rows[0].get("sha256") or ""),
            "X-BotTested-Arquivo-SHA256": hashlib.sha256(corpo).hexdigest(),
            "Access-Control-Expose-Headers": "X-BotTested-Relatorio-Id, X-BotTested-Conteudo-SHA256, X-BotTested-Arquivo-SHA256"})

    @r.get("/learning/diagnostico/opcoes")
    def opcoes(authorization: str = Header(default="")):
        uid = sessao_user_id(authorization); sb = _sb()
        ids, _, esc_txt = _escopo(sb, uid)
        rows = sb.table("conector_bots").select("id,nome,simbolo,excluido").execute().data or []
        bots = [{"id": int(b["id"]), "nome": b.get("nome"), "simbolo": b.get("simbolo"), "excluido": bool(b.get("excluido"))} for b in rows if int(b["id"]) in ids]
        return {"fuso_padrao": FUSO_PADRAO, "horas_padrao": HORAS_PADRAO, "escopo": esc_txt, "bots": sorted(bots, key=lambda b: b["id"]), "versao": VERSAO}

    return r
