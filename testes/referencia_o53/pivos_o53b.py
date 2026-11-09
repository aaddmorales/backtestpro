"""ORDEM 053-B — auditoria de topos/fundos e REV-0 (reversão em SOMBRA no pivô). Especificação: O53B_reversao_sombra_congelada.txt.
Replay barra a barra em M15 FECHADO: em cada barra usa só o que estava disponível no fechamento dela (memória O39 do M15 + H1)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "referencia_o51"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ao_vivo_o53 as R1

VERSAO = "rev-0 (ORDEM 053-B)"
TICK = 0.01; K_ZONA = 0.25; K_ESPACO_R = 1.0; SOMBRA_MIN = 0.5; N_TOQUE = 4


def _df(x):
    return pd.DataFrame({"t": pd.to_datetime(x.ep, unit="s"), "o": x.open, "h": x.high, "l": x.low, "c": x.close}).reset_index(drop=True)


def auditar(m15, h1=None, ini=None, fim=None, ativo="BTCUSD"):
    """m15/h1: DataFrames ep,open,high,low,close (barras fechadas, ordem crescente). ini/fim: epochs do período auditado (aberturas).
    Devolve dict com pivôs (um por pivô confirmado/descartado), REV-0 em sombra e toques de zona."""
    mem = R1.Memorias(ativo, "M15")
    ep = m15.ep.values.astype(np.int64); H, L, O, C = (m15[k].values.astype(float) for k in ("high", "low", "open", "close"))
    n = len(m15); cand = {}; pivos = []; toques = []; eventos_por_barra = {}; rej_por_barra = {}
    atr_seq = []
    for i in range(n):
        fecha = int(ep[i]) + 900
        Mtf = mem.m["M15"]; antes = Mtf.n_barras
        rates = _df(m15.iloc[:i + 1])
        # alimentação idêntica ao EA/motor: TF do gráfico, depois H1 fechado até este instante
        Mtf_ev = []
        if mem.ult["M15"] is None:
            ini_feed = max(0, len(rates) - R1.N_JANELA)
        else:
            ini_feed = len(rates) - 1
        for j in range(ini_feed, len(rates)):
            evs = Mtf.nova_barra(int(ep[j]), int(ep[j]) + 900, float(O[j]), float(H[j]), float(L[j]), float(C[j])); mem.ult["M15"] = int(ep[j])
            if j == i:
                Mtf_ev = evs
        if h1 is not None:
            mem.alimentar("H1", _df(h1[h1.ep + 3600 <= fecha]))
        atr_seq.append(Mtf.atr)
        eventos_por_barra[i] = Mtf_ev
        for e in Mtf_ev:
            if e["evento"] == "candidato":
                cand[(e["tipo"], round(e["extremo"], 2))] = i
            elif e["evento"] == "candidato_descartado":
                k = cand.pop((e["tipo"], round(e["extremo"], 2)), None)
                if k is not None and (ini is None or ep[k] >= ini) and (fim is None or ep[k] < fim):
                    pivos.append({"tipo": e["tipo"], "barra": int(ep[k]), "extremo": round(e["extremo"], 2), "situacao": "descartado",
                                  "motivo": "barra seguinte igualou/ultrapassou o extremo", "decidido_em": fecha})
            elif e["evento"] in ("confirmado", "agrupado"):
                x = round(e["extremo"], 2)
                tipo = "fundo" if e["evento"] == "confirmado" and e.get("funcao") == "suporte" else ("topo" if e["evento"] == "confirmado" else None)
                if tipo is None:
                    tipo = "fundo" if ("fundo", x) in cand else "topo"
                k = cand.pop((tipo, x), None)
                if k is None or (ini is not None and ep[k] < ini) or (fim is not None and ep[k] >= fim):
                    continue
                niv = next((nv for nv in Mtf.niveis if nv["id"] == e["nivel"]), None)
                pivos.append({"tipo": tipo, "barra": int(ep[k]), "idx": k, "idx_conf": i, "extremo": x, "situacao": "confirmado", "evento_o39": e["evento"],
                              "confirmado_em": fecha, "zona": None if niv is None else [round(niv["zona"][0], 2), round(niv["zona"][1], 2)],
                              "zona_membros": None if niv is None else len(niv["membros"]), "atr": Mtf.atr})
            elif e["evento"] == "teste":
                niv = next((nv for nv in Mtf.niveis if nv["id"] == e["nivel"]), None)
                if niv is not None and e.get("rejeicao"):
                    rej_por_barra.setdefault(i, set()).add(niv["funcao"])
                if niv is not None and (ini is None or ep[i] >= ini) and (fim is None or ep[i] < fim):
                    toques.append({"barra": int(ep[i]), "idx": i, "nivel": e["nivel"], "funcao": niv["funcao"], "zona": [round(niv["zona"][0], 2), round(niv["zona"][1], 2)],
                                   "rejeicao": bool(e.get("rejeicao")), "atr": Mtf.atr})
        # REV-0: avalia os pivôs confirmados NESTA barra (gatilho na barra seguinte)
        for p in pivos:
            if p.get("idx_conf") == i and "rev" not in p:
                p["rev"] = _rev_avaliar(p, mem, H, L, O, C, rej_por_barra, i)
    # REV-0: andamento até a saída (usa as barras seguintes, uma a uma)
    for p in pivos:
        r = p.get("rev")
        if r and r.get("estado") == "pendente":
            _rev_seguir(p, r, ep, H, L, O, C, n, pivos)
    # toques de zona: continuidade × reação
    for t in toques:
        t.update(_toque_desfecho(t, ep, H, L, C, n, pivos))
    return {"versao": VERSAO, "pivos": pivos, "toques": toques}


def _rev_avaliar(p, mem, H, L, O, C, rejb, i):
    k = p["idx"]; s = 1 if p["tipo"] == "fundo" else -1
    rng = H[k] - L[k]
    somb = ((min(O[k], C[k]) - L[k]) / rng if s > 0 else (H[k] - max(O[k], C[k])) / rng) if rng > 0 else 0.0
    rej_zona = ("suporte" if s > 0 else "resistencia") in rejb.get(k, set())
    out = {"sombra_pct": round(100 * somb, 1), "rejeicao_zona_o39": rej_zona}
    if not (somb >= SOMBRA_MIN or rej_zona):
        return {**out, "estado": "sem rejeição", "decisao": "pivô sem rejeição: sem oportunidade de reversão"}
    gat = round((H[i] + TICK) if s > 0 else (L[i] - TICK), 2)
    z = mem.obstaculo(s, gat)                      # primeira zona à frente com a memória do fechamento da barra de confirmação
    return {**out, "estado": "pendente", "gatilho": gat, "lado": "compra" if s > 0 else "venda",
            "zona_a_frente": None if z is None else {k: (round(v, 2) if isinstance(v, float) else v) for k, v in z.items() if k in ("tf", "funcao", "base", "topo", "estado", "testes", "rejeicoes")}}


def _rev_seguir(p, r, ep, H, L, O, C, n, pivos):
    i = p["idx_conf"]; s = 1 if p["tipo"] == "fundo" else -1; j = i + 1
    if j >= n:
        r.update(estado="aguardando barra seguinte", decisao="pivô confirmado na última barra do período"); return
    g = r["gatilho"]
    alcan = (H[j] >= g) if s > 0 else (L[j] <= g)
    if not alcan:
        r.update(estado="gatilho não alcançado", decisao=f"gatilho {g:.2f} não alcançado na barra seguinte"); return
    E = (max(O[j], g) if s > 0 else min(O[j], g))
    atr = p["atr"] or 0.0
    stop = round(p["extremo"] - s * K_ZONA * atr, 2); R = abs(E - stop)
    r.update(entrada=round(E, 2), stop=stop, R=round(R, 2), t_entrada=int(ep[j]))
    z = r.get("zona_a_frente")
    if z is not None:
        d = max(0.0, (z["base"] - E) if s > 0 else (E - z["topo"]))
        r.update(espaco_pts=round(d, 2), espaco_R=round(d / R, 2) if R > 0 else None)
        if d == 0.0 or d < K_ESPACO_R * R - 1e-9:
            r.update(estado="bloqueada pelo espaço", decisao=f"{'entrada dentro da zona' if d == 0.0 else 'espaço insuficiente'}: {r['espaco_R']} R até "
                     f"{z['funcao']} {z['tf']} {z['base']:.2f}–{z['topo']:.2f}")
            return
    else:
        r.update(espaco_pts=None, espaco_R=None)
    mfe = 0.0; saida = None
    for q in range(j, n):
        fav = ((H[q] - E) if s > 0 else (E - L[q])) / R if R > 0 else 0.0
        mfe = max(mfe, fav)
        if (L[q] <= stop) if s > 0 else (H[q] >= stop):
            saida = (q, stop, "stop"); break
        if q > j and ((C[q] < p["extremo"]) if s > 0 else (C[q] > p["extremo"])):
            saida = (q, C[q], "fechamento além do extremo"); break
        opp = next((x for x in pivos if x.get("idx_conf") == q and x["tipo"] != p["tipo"] and x["situacao"] == "confirmado"), None)
        if opp is not None and q > j:
            saida = (q, C[q], "pivô contrário confirmado"); break
    if saida is None:
        saida = (n - 1, C[n - 1], "fim do período (em aberto)")
    q, px, mot = saida
    res = ((px - E) * s) / R if R > 0 else 0.0
    cls = "reversão" if mfe >= 1.0 else ("continuidade" if mot in ("stop", "fechamento além do extremo") else "indefinido")
    r.update(estado="entrou (sombra)", t_saida=int(ep[q]), saida=round(px, 2), motivo_saida=mot, R_final=round(res, 2), MFE_R=round(mfe, 2), classe=cls,
             decisao=f"sombra: {r['lado']} em {E:.2f}, stop {stop:.2f}; {cls} (MFE {mfe:.2f} R, saída {mot} {res:+.2f} R)")


def _toque_desfecho(t, ep, H, L, C, n, pivos):
    i = t["idx"]; b, tz = t["zona"]; sup = t["funcao"] == "suporte"; atr = t["atr"] or 0.0
    for q in range(i + 1, min(n, i + 1 + N_TOQUE)):
        if (C[q] < b) if sup else (C[q] > tz):
            return {"desfecho": "continuidade", "barras_ate": q - i}
        if (H[q] >= tz + atr) if sup else (L[q] <= b - atr):
            return {"desfecho": "reação", "barras_ate": q - i}
    return {"desfecho": "indefinido", "barras_ate": None}

