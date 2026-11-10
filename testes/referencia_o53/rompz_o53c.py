"""rompz-0 (ORDEM 053-C) — ROMPIMENTO DE ZONA da memória O39, SÓ EM SOMBRA (nenhuma ordem). Referência Python do que o EA lateral-r1.2 registra.

Regra (do dono, O53-C): a barra que FECHA além de um suporte (venda) / resistência (compra) da memória estrutural O39 do TF do gráfico é a
barra de rompimento; a sua mínima (venda) / máxima (compra) arma o gatilho. O gatilho vale SÓ dentro da barra seguinte: o primeiro tick cujo
BID fica ≥ 1 tick além desse extremo é o ponto de entrada. Igualar o extremo é "toque" e não dispara; passar só depois da barra seguinte não
dispara. Não espera fechamento da barra seguinte, terceira barra nem reteste.
O espaço até a primeira zona (filtro O53, 1,0 R líquido) é só AVALIADO e registrado junto do disparo.
Mesma sequência do EA: na virada de barra (1) expira o gatilho da barra anterior, (2) alimenta as memórias (TF + H1) só com barras fechadas,
(3) arma pelo que a ÚLTIMA barra fechada rompeu (nunca na carga inicial); por tick, avalia o gatilho dentro da janela [início, fim)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "referencia_o51"))
import estrutura_o39 as EO, romp_m15 as RM  # noqa: E402
import ao_vivo_o53 as R1  # noqa: E402

VERSAO = "rompz-0 (ORDEM 053-C)"; TICK = 0.01
tk = lambda x: int(np.rint(x / TICK))


def ticks_m1(m1, ini, sp):
    """mesma sequência de preços do simulador do EA (abertura, extremo 1, extremo 2, fechamento por minuto); bid = preço, ask = bid + spread."""
    for t, o, h, l, c in zip(m1.ep, m1.open, m1.high, m1.low, m1.close):
        up = c >= o; seq = (o, l if up else h, h if up else l, c)
        for k, (dt_, p) in enumerate(zip((0, 15, 30, 59), seq)):
            if t + dt_ < ini: continue
            bid = round(p, 2); yield int(t + dt_), bid, round(bid + sp, 2)


def rodar(m15, h1, m1, ini, sp, dur=900):
    """m15/h1/m1: DataFrames com ep, open, high, low, close (ep = abertura UTC). Devolve a lista de eventos (dicts) na ordem do EA."""
    mem = R1.Memorias("BTCUSD", "M15"); ev = []; pend = {-1: None, 1: None}; ult_barra = None
    E15, E1h = m15.ep.values.astype(np.int64), (h1.ep.values.astype(np.int64) if h1 is not None else np.array([], np.int64))
    for t, bid, ask in ticks_m1(m1, ini, sp):
        t0 = (t // dur) * dur
        if t0 != ult_barra:
            n = int(np.searchsorted(E15, t - dur, side="right"))        # barras com abertura + dur ≤ t
            if n >= 12 + 14 + 3:
                ini_j = max(0, n - 1200); F = m15.iloc[ini_j:n]; b = F.iloc[-1]; fim = int(b.ep) + dur
                for s in (-1, 1):
                    p = pend[s]
                    if p and p["fim"] <= fim:
                        ev.append({"ev": "rompz_expirado", "sinal": p["id"], "resultado": "toque sem superacao" if p["tocou"] else "nao alcancou"}); pend[s] = None
                aquecendo = mem.ult["M15"] is None
                M = mem.m["M15"]; ultimo = []
                ep = F.ep.values.astype(np.int64); i0 = 0 if mem.ult["M15"] is None else int(np.searchsorted(ep, mem.ult["M15"], side="right"))
                for i in range(i0, len(F)):
                    ultimo = M.nova_barra(int(ep[i]), int(ep[i]) + dur, *(float(F[k].iloc[i]) for k in ("open", "high", "low", "close")))
                    mem.ult["M15"] = int(ep[i])
                nh = int(np.searchsorted(E1h, t - 3600, side="right"))
                if nh: mem.alimentar("H1", pd.DataFrame({"t": pd.to_datetime(h1.ep.values[:nh], unit="s"), "o": h1.open.values[:nh], "h": h1.high.values[:nh],
                                                          "l": h1.low.values[:nh], "c": h1.close.values[:nh]}))
                atr = RM.atr_wilder(F.high.values, F.low.values, F.close.values)[-1]
                if not aquecendo and atr > 0:
                    niv = {x["id"]: x for x in M.niveis}
                    for s in (-1, 1):
                        zs = [niv[e["nivel"]]["zona"] for e in ultimo if e["evento"] == "rompimento_pendente" and (niv[e["nivel"]]["funcao"] == "suporte") == (s < 0)]
                        if not zs: continue
                        ext = float(b.low if s < 0 else b.high)
                        pend[s] = {"id": ("ZV-" if s < 0 else "ZC-") + str(int(b.ep)), "lado": s, "ext": tk(ext), "tt": tk(ext) + s, "atr": atr, "ini": fim, "fim": fim + dur,
                                   "tocou": False}
                        ev.append({"ev": "rompz_armado", "sinal": pend[s]["id"], "lado": s, "barra_rompimento": int(b.ep), "extremo": round(ext, 2),
                                   "gatilho": round((tk(ext) + s) * TICK, 2), "atr": float(atr), "zonas": sorted([round(z[0], 2), round(z[1], 2)] for z in zs)})
                ult_barra = t0
        for s in (-1, 1):
            p = pend[s]
            if not p or not (p["ini"] <= t < p["fim"]): continue
            bt = tk(bid)
            if (bt <= p["ext"]) if s < 0 else (bt >= p["ext"]): p["tocou"] = True
            if not ((bt <= p["tt"]) if s < 0 else (bt >= p["tt"])): continue
            esp = R1.avaliar_espaco(mem, s, bid, ask, p["atr"]); pend[s] = None
            ev.append({"ev": "rompz_disparo", "sinal": p["id"], "lado": s, "t": t, "bid": bid, "ask": ask, "atr": float(p["atr"]), "espaco_R": esp.get("espaco_R"), "zona_a_frente": esp.get("zona"), "gatilho": round(p["tt"] * TICK, 2),
                       "espaco_passa": "sim" if esp["passa"] else "nao", "motivo": esp["motivo"]})
    return ev
