"""atualizar_ea_782.py - C27R54 - SOMENTE HOMOLOGACAO / MT5 DEMO.
Reinstala e RECOMPILA os EAs dos bots da campanha (BTCUSD id 13, XAUUSD id 14) com o EA 7.83 que a API homolog entrega (7.82 + sinal de conexao com a plataforma no selo):
  - o snapshot passa a informar o trailing local do EA (|tbar=0/1);
  - o executor puro nasce com InpBTTrailingLocal=false (input renomeado: o valor true antigo do grafico nao e herdado).
Tokens: lidos da configuracao do Conector HOMOLOG e da nuvem homolog; NUNCA impressos. Nao envia ordem, nao toca em conta real.
Uso: py atualizar_ea_782.py <pasta do conector instalado> <ids separados por virgula>"""
import json, os, sys

dest, ids = sys.argv[1], [int(x) for x in sys.argv[2].split(",") if x.strip()]
sys.path.insert(0, dest)
import conector_nucleo_homolog as N

cfg = json.load(open(os.path.join(os.path.expanduser("~"), "BotTested_Conector_HOMOLOG_config.json"), encoding="utf-8"))
pin = cfg.get("mt5_pin")
if not pin:
    print("PARADO: conector sem instalacao MT5 fixada"); sys.exit(1)
tok0 = (cfg.get("ultimo_token") or cfg.get("bot_token") or "").strip()
if not tok0:
    print("PARADO: conector sem token salvo (abra o conector e conecte uma vez)"); sys.exit(1)
ok, lst = N.listar_tokens_do_usuario(tok0)
if not ok:
    print("PARADO: nao consegui listar os bots na nuvem homolog:", lst); sys.exit(1)
por_id = {int(x.get("id") or 0): x for x in lst}
falhou = False
for bid in ids:
    b = por_id.get(bid)
    if not b:
        print(f"PARADO: bot {bid} nao pertence a este usuario na homolog"); falhou = True; continue
    ok, destino = N.reinstalar_bot(b.get("bot_token"), bid, pin)
    if not ok:
        print(f"bot {bid}: reinstalar FALHOU: {destino}"); falhou = True; continue
    txt = open(destino, encoding="utf-8").read()
    marcas = {"eav 7.83": "eav=7.83-ciclos-lm2" in txt, "sinal de conexao no selo": "BT_LINK_V1" in txt, "tbar no snapshot": "|tbar=%d" in txt,
              "trailing local desligado": "input bool   InpBTTrailingLocal = false;" in txt, "sem o input antigo": "InpBTTrailingBarra" not in txt}
    me = N.achar_metaeditor_hml(pin) if hasattr(N, "achar_metaeditor_hml") else None
    okc, log = N.compilar_mq5(destino, me)
    print(f"bot {bid} ({b.get('nome')}): {os.path.basename(destino)} | " + " | ".join(f"{k}={'sim' if v else 'NAO'}" for k, v in marcas.items())
          + f" | compilado={'sim' if okc else ('sem compilador' if okc is None else 'NAO')}")
    if not okc or not all(marcas.values()):
        falhou = True
        if okc is False:
            print(str(log)[-800:])
sys.exit(1 if falhou else 0)
