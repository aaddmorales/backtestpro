"""replay_trilha.py — skill bottested-trader-m15 v1.0 (ORDEM 054-A).

Replay SEM ORDENS da regra de rompimento de zona (ROMPZ, EA lateral-r1.2 O53-D) sobre dados exportados do MT5,
usando a referência Python já validada contra o EA (testes/referencia_o53/rompz_o53c.py). Não reimplementa a regra:
só chama RZ.rodar(...) e imprime, sinal a sinal, as QUATRO decisões separadas:
  1. leitura do contexto  (zona já conhecida? confirmada antes da barra de rompimento?)
  2. disparo do sinal     (fechamento além da zona arma o gatilho; 1º tick ≥ 1 tick além, só na barra seguinte)
  3. autorização da ordem (filtro de espaço de 1,0 R; bloqueio vira "sinal reconhecido; ordem bloqueada — <motivo>")
  4. gestão               (entrada/saída virtuais da referência; posição aberta → continuidade, sem duplicar)

Uso (a partir da raiz do repositório):
  python .claude/skills/bottested-trader-m15/scripts/replay_trilha.py M15.csv M1.csv H1.csv --ini <epoch_utc> --spread 15.00 \
      [--ativo BTCUSD] [--sem-filtro-sombra] [--json saida.json]
Arquivos no formato de exportação do MT5 (<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE>, tab), horários em UTC.
--ini = epoch UTC a partir do qual os ticks são simulados (o histórico anterior só aquece a memória O39).
Nada aqui fala com corretora, terminal ou banco: é leitura de arquivo + simulação."""
import os, sys, json, argparse, calendar, datetime as dt
import pandas as pd

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(RAIZ, "testes", "referencia_o53"), os.path.join(RAIZ, "testes", "referencia_o51")]
import rompz_o53c as RZ  # noqa: E402

VERSAO = "replay-trilha-1.0 (bottested-trader-m15 v1.0 / ORDEM 054-A)"
SERVIDOR = 7200  # corretora: UTC+2 (Kyiv, inverno). Barra do dia = minutos desde 00:00 do servidor / 15 + 1.


def ler(arq):
    d = pd.read_csv(arq, sep="\t"); d.columns = [c.strip("<>").lower() for c in d.columns]
    d["ep"] = [calendar.timegm(x.timetuple()) for x in pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")]
    return d


def srv(ep):
    t = dt.datetime.fromtimestamp(int(ep) + SERVIDOR, dt.timezone.utc)
    return f"{t:%d/%m %H:%M} srv (barra {(t.hour * 60 + t.minute) // 15 + 1})"


BLOQUEIO = {  # string do EA/referência → registro da skill
    "sinal disparado; bloqueado por falta de espaco": "sinal reconhecido; ordem bloqueada — falta de espaço (< 1,0 R até a próxima zona)",
    "sinal disparado; bloqueado: entrada dentro da zona": "sinal reconhecido; ordem bloqueada — entrada dentro da zona",
    "sinal disparado; bloqueado: distancia nao calculavel (historico insuficiente)": "sinal reconhecido; ordem bloqueada — distância não calculável (histórico < 200 barras)",
    "sinal disparado; bloqueado: posicao aberta": "sinal reconhecido; CONTINUIDADE — posição já aberta, entrada não duplicada",
    "sinal disparado; ordem autorizada": "sinal reconhecido; ordem autorizada (replay: nenhuma ordem enviada)",
}


def trilha(I):
    linhas = []
    gest = [e for e in I.eventos if e["tipo"] in ("entrada_virtual", "saida_virtual")]
    for p in I.sinais_rz:
        lado = "venda (suporte rompido)" if p["lado"] < 0 else "compra (resistência rompida)"
        ctx = [{"zona": f'{z["base"]:.2f}–{z["topo"]:.2f}', "confirmada_em": srv(z["confirmada_em"]),
                "confirmada_antes_do_rompimento": z["confirmada_em"] <= p["barra_rompimento"], "testes": z["testes"]} for z in p["zonas"]]
        l = {"sinal": p["id"], "lado": lado,
             "1_contexto": {"zonas_conhecidas": ctx, "exaustao_lateralizacao": "não avaliada aqui — vem da leitura LM (auditoria_leituras.eventos); o EA não a usa na entrada"},
             "2_sinal": {"barra_rompimento": srv(p["barra_rompimento"]), "fechamento": round(p["fechamento"], 2), "extremo": p["extremo"],
                         "gatilho": p["gatilho"], "valido_na_barra": srv(p["barra_rompimento"] + 900)}}
        if p["resultado"] != "disparo":
            l["2_sinal"]["resultado"] = f'expirado — {p["resultado"]}'
            l["3_autorizacao"] = "não se aplica (sem sinal)"; l["4_gestao"] = "não se aplica"
        else:
            e = p["espaco"]
            l["2_sinal"]["resultado"] = f'disparado em {dt.datetime.fromtimestamp(p["t"] + SERVIDOR, dt.timezone.utc):%H:%M:%S} srv, bid {p["bid"]:.2f}'
            l["3_autorizacao"] = {"registro": BLOQUEIO.get(p["decisao"], p["decisao"]), "decisao_motor": p["decisao"], "motivo_espaco": e.get("motivo"),
                                  "espaco_R": None if e.get("espaco_R") is None else round(e["espaco_R"], 3), "zona_a_frente": e.get("zona"),
                                  "sem_filtro_sombra": p["sem_filtro_sombra"]}
            g = [x for x in gest if x.get("id") == p["id"]]
            l["4_gestao"] = [{k: v for k, v in x.items() if k in ("tipo", "preco", "stop", "motivo", "R")} for x in g] or "sem posição aberta por este sinal"
        linhas.append(l)
    return linhas


def main():
    a = argparse.ArgumentParser(); a.add_argument("m15"); a.add_argument("m1"); a.add_argument("h1")
    a.add_argument("--ini", type=int, required=True); a.add_argument("--spread", type=float, required=True)
    a.add_argument("--ativo", default="BTCUSD"); a.add_argument("--sem-filtro-sombra", action="store_true"); a.add_argument("--json")
    o = a.parse_args()
    I = RZ.rodar(ler(o.m15), ler(o.h1), ler(o.m1), o.ini, o.spread, at=o.ativo, caixa=False, filtro_rompz=not o.sem_filtro_sombra)
    out = {"versao": VERSAO, "motor": RZ.VERSAO, "variante": "SEM filtro (só sombra)" if o.sem_filtro_sombra else "COM filtro 1,0 R (fluxo autorizado)",
           "trilha": trilha(I), "resumo_operacoes_fechadas": RZ.resumo(I.ops), "posicao_em_aberto": I.pos is not None}
    txt = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    if o.json: open(o.json, "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
