# -*- coding: utf-8 -*-
"""Efeito da gestão POR OPERAÇÃO (uma linha por posição; nada somado entre avaliações da mesma posição).
Base fixa definida antes do cálculo: a mesma entrada (preço executado), o stop INICIAL, sem nenhuma ação de gestão,
mantida até o fechamento da 16ª barra M15 completa após a entrada; se a mínima/máxima tocar o stop, sai no stop
(quando a barra toca o stop e não há informação intrabarra, assume o stop primeiro — desfavorável à base).
R = (preço de saída − entrada)·lado ÷ |entrada − stop inicial|. Fonte: auditoria_candles M15 (homolog)."""
import json, datetime as dt
C = json.load(open("candles_m15.json")); OPS = json.load(open("ops_base.json"))
P = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
bars = {}
for x in C: bars.setdefault(x["s"], []).append((P(x["t"]), float(x["h"]), float(x["l"]), float(x["c"]), x["f"]))
H = 16; out = []
for op, sim, lado, ent, st, sai, ta, tf, mot, usd in OPS:
    risco = abs(ent - st); ta = P(ta)
    b = [k for k in bars[sim] if k[0] + dt.timedelta(minutes=15) > ta]   # barra da entrada em diante
    seq = b[:H + 1]                                                    # barra da entrada (parcial) + 16 completas
    base, saiu = None, None
    for t, h, l, c, f in seq:
        if (lado > 0 and l <= st) or (lado < 0 and h >= st):
            base, saiu = st, f"stop inicial tocado na barra {t:%d/%m %H:%M}"; break
    if base is None:
        base, saiu = seq[-1][3], f"fechamento da barra {seq[-1][0]:%d/%m %H:%M} (horizonte)"
    Rr = (sai - ent) * lado / risco; Rb = (base - ent) * lado / risco
    out.append(dict(op=op, ativo=sim, lado="compra" if lado > 0 else "venda", motivo_saida=mot, R_real=round(Rr, 2), R_base_sem_gestao=round(Rb, 2),
                    efeito_R=round(Rr - Rb, 2), base_saida=saiu, barras_disponiveis=len(seq) - 1, completo=len(seq) == H + 1))
for o in out: print(o)
ef = [o["efeito_R"] for o in out]
res = dict(definicao=__doc__, n_operacoes=len(out), operacoes=out,
           soma_efeito_R=round(sum(ef), 2), melhores=sum(e > 0.05 for e in ef), piores=sum(e < -0.05 for e in ef), neutras=sum(abs(e) <= 0.05 for e in ef),
           mediana_efeito_R=sorted(ef)[len(ef) // 2])
print({k: v for k, v in res.items() if k not in ("operacoes", "definicao")})
json.dump(res, open("efeito_por_operacao.json", "w"), ensure_ascii=False, indent=1)
