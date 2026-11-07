"""corte-estrutural-0.1 (ORDEM 046) — G1 = G0 (O44) + corte por perda do nível ORIGINAL: alerta M1 (janela de 15 min após o gatilho, posição aberta)
→ confirmação no 1º fechamento M15 → execução na abertura da M1 seguinte (lado correto + spread + deslizamento). Especificação: O46_especificacao_congelada.txt."""
import numpy as np, pandas as pd
VERSAO = "corte-estrutural-0.1 (ORDEM 046)"; MIN = 60 * 10**9; M15 = 15 * MIN; JAN = 15


class Mercado:
    """M1 (bid) e M15 do servidor de um ativo."""
    def __init__(self, m1, m15):
        self.t1 = m1.t.values.astype("datetime64[ns]").astype(np.int64); self.o1, self.h1, self.l1, self.c1 = (m1[k].values.astype(float) for k in "ohlc"); self.sp = m1.spread.values * 0.01
        self.t15 = m15.t.values.astype("datetime64[ns]").astype(np.int64); self.f15 = self.t15 + M15; self.C15 = m15.c.values.astype(float)


def corte(mk, op, N, K, desl=1.0):
    """op: operação G0 (dict com lado, j_ent, j_sai, entrada, stop, R). Devolve dict com eventos e o resultado G1 (= G0 se não houver corte)."""
    s = op["lado"]; j0, js = int(op["j_ent"]), int(op["j_sai"]); t1, c1 = mk.t1, mk.c1; fim_jan = t1[j0] + JAN * MIN
    alem = (lambda x: x > N + 1e-9) if s < 0 else (lambda x: x < N - 1e-9); volta = (lambda x: x < N - 1e-9) if s < 0 else (lambda x: x > N + 1e-9)
    ev = {"alertas": [], "n_alertas": 0, "recuperados": 0, "expirados": 0, "encerrados_por_G0": 0, "confirmado": False, "cortou": False, "empate": False, "ordem_incerta": False,
          "j_alerta1": None, "j_corte": None, "t_decisao15": None}
    k = j0
    while k < len(t1) and t1[k] < fim_jan:
        if js <= k: break                                                                 # posição já encerrada no início/durante esta M1
        if not alem(c1[k]): k += 1; continue
        ev["n_alertas"] += 1; a = {"j": k, "t_alerta": int(t1[k]) + MIN}; ev["j_alerta1"] = k if ev["j_alerta1"] is None else ev["j_alerta1"]
        i15 = int(np.searchsorted(mk.f15, t1[k], side="right")); fecha = int(mk.f15[i15]); kend = int(np.searchsorted(t1, fecha)) - 1   # última M1 da barra M15
        a["t_decisao15"] = fecha; a["c15"] = float(mk.C15[i15]) if mk.t15[i15] <= t1[k] < fecha else None
        rec = next((q for q in range(k + 1, kend + 1) if volta(c1[q])), None)
        if js <= kend and (rec is None or js <= rec):                                    # G0 sai antes de a decisão M15 existir
            a["fim"] = "saída G0 antes da confirmação"; ev["encerrados_por_G0"] += 1; ev["alertas"].append(a); break
        if rec is not None:
            a["fim"] = "recuperado"; a["j_fim"] = rec; ev["recuperados"] += 1; ev["alertas"].append(a); k = rec + 1; continue
        if a["c15"] is not None and alem(a["c15"]):
            ev["confirmado"] = True; ev["t_decisao15"] = fecha; m = int(np.searchsorted(t1, fecha))
            a["fim"] = "confirmado"; ev["alertas"].append(a)
            if m >= len(t1): break
            if js < m: a["fim"] = "confirmado, mas G0 saiu antes da execução"; break
            if js == m: ev["empate"] = True; a["fim"] = "confirmado; empate com a saída G0 (mesma M1)"; break
            px = mk.o1[m] + mk.sp[m] + desl * mk.sp[m] if s < 0 else mk.o1[m] - desl * mk.sp[m]
            ev["ordem_incerta"] = bool((mk.h1[m] + mk.sp[m] >= op["stop"]) if s < 0 else (mk.l1[m] <= op["stop"]))
            ev.update({"cortou": True, "j_corte": m, "px_corte": float(px)}); break
        a["fim"] = "expirado (M15 não confirmou)"; ev["expirados"] += 1; ev["alertas"].append(a); k = kend + 1
    r0 = abs(op["entrada"] - op["stop"]); com = 2 * K["com_lado"] / K["contrato"] / r0
    if ev["cortou"]:
        ev["R_G1"] = (ev["px_corte"] - op["entrada"]) * s / r0 - com; ev["j_sai_G1"] = ev["j_corte"]; ev["usd_G1"] = (ev["px_corte"] - op["entrada"]) * s * K["contrato"] - 2 * K["com_lado"]
    else: ev["R_G1"] = op["R"]; ev["j_sai_G1"] = js; ev["usd_G1"] = op["usd_1lote"]
    a1 = ev["j_alerta1"]
    if a1 is not None:                                                                    # tempo do 1º alerta × saída G0 (correção O45)
        ta, tsai = int(t1[a1]) + MIN, int(t1[js]); ev["aviso_vs_saida_G0"] = "anterior" if ta < tsai else ("simultaneo" if ta == tsai else "posterior")
    return ev


def mfe(mk, op, j_fim):
    s = op["lado"]; r0 = abs(op["entrada"] - op["stop"]); a, b = int(op["j_ent"]), int(j_fim)
    if b <= a: return 0.0
    return max(0.0, float(((mk.c1[a:b] - op["entrada"]) * s).max() / r0))
