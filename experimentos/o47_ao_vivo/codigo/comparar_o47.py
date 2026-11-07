"""ORDEM 047 — comparação M15 × M30 × H1 a partir dos registros do leitor AO VIVO (eventos_LM.jsonl de cada ativo).
Só operações com entrada em [início, início + 84 dias) e já fechadas; abertas no fim ficam de fora (marcadas). Regras de suficiência e IC: O47_especificacao_congelada.txt.
Uso: python comparar_o47.py --inicio AAAA-MM-DD --pasta-xau DIR --pasta-btc DIR --saida DIR [--dias 84]"""
import os, sys, json, argparse
import numpy as np, pandas as pd
MIN_OPS = 30; TFS = ("M15", "M30", "H1")


def ler(pasta):
    ev = [json.loads(l) for l in open(os.path.join(pasta, "eventos_LM.jsonl"), encoding="utf-8") if l.strip()]
    if any(e.get("classe") != "sombra_ao_vivo" for e in ev if e["tipo"] in ("resultado", "decisao")): print("ATENÇÃO: há eventos que não são da classe 'sombra_ao_vivo' (ex.: simulado) — não contam como teste ao vivo", flush=True)
    return ev


def boot(d, n=2000):
    d = np.asarray(d, float); rng = np.random.default_rng(47); bs = [d[rng.integers(0, len(d), len(d))].sum() for _ in range(n)]; lo, hi = np.percentile(bs, [2.5, 97.5]); return round(float(lo), 2), round(float(hi), 2)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--inicio", required=True); ap.add_argument("--pasta-xau"); ap.add_argument("--pasta-btc"); ap.add_argument("--saida", required=True); ap.add_argument("--dias", type=int, default=84)
    a = ap.parse_args(); ini = pd.Timestamp(a.inicio); fim = ini + pd.Timedelta(days=a.dias); os.makedirs(a.saida, exist_ok=True); R = {"inicio": str(ini), "fim": str(fim), "amostra_minima": MIN_OPS, "ativos": {}}
    dias = pd.date_range(ini, fim - pd.Timedelta(days=1), freq="D"); horas = a.dias * 24
    for at, p in (("XAUUSD", a.pasta_xau), ("BTCUSD", a.pasta_btc)):
        if not p: continue
        ev = ler(p); res = [e["payload"] for e in ev if e["tipo"] == "resultado"]; dec = [e["payload"] for e in ev if e["tipo"] == "decisao"]; dia = [e["payload"] for e in ev if e["tipo"] == "diagnostico"]
        dados = [e["payload"] for e in ev if e["tipo"] == "dados"]; O = pd.DataFrame(res); A = {}
        if len(O): O["t_ent"] = pd.to_datetime(O.t_ent_ms, unit="ms"); O = O[(O.t_ent >= ini) & (O.t_ent < fim)]
        abertas = [d for d in dec if d["tipo"] == "entrada_virtual" and d["id"] not in set(O.id if len(O) else [])]
        G = pd.DataFrame(dia)
        for tf in TFS:
            o = O[O.tf == tf] if len(O) else O; cnt = pd.Series([d["tipo"] for d in dec if d["instancia"].endswith(tf)]).value_counts().to_dict()
            m = {"contadores_eventos": cnt, "operacoes_fechadas": int(len(o)), "abertas_no_fim_excluidas": sum(1 for d in abertas if d["instancia"].endswith(tf))}
            if len(o):
                cum = np.cumsum(o.sort_values("t_sai_ms").R.values); dd = float((cum - np.maximum.accumulate(np.r_[0, cum])[1:]).min())
                daily = o.R.groupby(o.t_ent.dt.floor("D")).sum().reindex(dias, fill_value=0).values
                m.update({"R_liquido": round(float(o.R.sum()), 2), "R_por_operacao": round(float(o.R.mean()), 4), "IC95_R_total_dia": boot(daily), "DD_R": round(dd, 2), "acerto": round(float((o.R > 0).mean()), 3),
                          "custos_usd_1lote": {"spread_pago": round(float(o.spread_pago_usd.sum()), 2), "comissao_estimada": round(float(o.comissao_usd.sum()), 2)}, "tempo_em_posicao_pct": round(float(o.horas.sum() / horas * 100), 2),
                          "saidas": o.motivo_saida.value_counts().to_dict(), "com_lacuna_de_dados": int(o.com_lacuna.sum()), "R_sem_lacuna": round(float(o.R[~o.com_lacuna.astype(bool)].sum()), 2),
                          "suficiente": bool(len(o) >= MIN_OPS)})
            g = G[G.tf == tf] if len(G) else G
            if len(g): g = g[g.completo]; m["retorno_15min"] = {k: int((g.grupo_retorno_15min == k).sum()) for k in "ABC"}; m["perda_do_nivel_C_pct"] = round(float((g.grupo_retorno_15min == "C").mean() * 100), 1) if len(g) else None
            A[tf] = m
        dif = {}
        for x, y in (("M30", "M15"), ("H1", "M15"), ("H1", "M30")):
            ox, oy = (O[O.tf == t] if len(O) else O for t in (x, y))
            dx = ox.R.groupby(ox.t_ent.dt.floor("D")).sum().reindex(dias, fill_value=0).values if len(ox) else np.zeros(len(dias))
            dy = oy.R.groupby(oy.t_ent.dt.floor("D")).sum().reindex(dias, fill_value=0).values if len(oy) else np.zeros(len(dias))
            lo, hi = boot(dx - dy); suf = len(ox) >= MIN_OPS and len(oy) >= MIN_OPS
            dif[f"{x}-{y}"] = {"diferenca_R": round(float((dx - dy).sum()), 2), "IC95": [lo, hi], "conclusao": "inconclusiva (amostra < 30 em alguma instância)" if not suf else ("inconclusiva (IC95 inclui zero)" if lo <= 0 <= hi else (f"{x} maior" if lo > 0 else f"{y} maior"))}
        R["ativos"][at] = {"instancias": A, "diferencas": dif, "periodos_sem_ticks": sum(1 for d in dados if d.get("evento") == "período sem ticks"), "desconexoes": sum(1 for d in dados if d.get("evento") == "desconexão")}
    json.dump(R, open(os.path.join(a.saida, "O47_comparacao.json"), "w"), ensure_ascii=False, indent=1, default=str); print(json.dumps(R, ensure_ascii=False, indent=1, default=str)[:4000])


if __name__ == "__main__": main()
