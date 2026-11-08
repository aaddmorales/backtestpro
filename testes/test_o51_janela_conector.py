"""ORDEM 051 — janela do Conector HOMOLOG hml18 com tkinter SIMULADO (sem tela): tokens separados, Meus bots com campanha + 🧪 sombra, botões em bot sombra, Conectar/Parar ligando a ponte. Uso: python -I testes/test_o51_janela_conector.py"""
import sys, types, threading
from unittest import mock
import os
HML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conector_homolog", "hml18"); sys.path.insert(0, HML)
tkm = mock.MagicMock(); sys.modules['tkinter'] = tkm; sys.modules['tkinter.ttk'] = tkm.ttk; sys.modules['tkinter.messagebox'] = tkm.messagebox
import conector_homolog as CH
msgs = []; CH.messagebox = types.SimpleNamespace(showinfo=lambda *a: msgs.append(a), showwarning=lambda *a: msgs.append(a), showerror=lambda *a: msgs.append(a), askyesno=lambda *a: True)
class Entry:
    def __init__(s): s.v = ""
    def get(s): return s.v
    def delete(s, *a): s.v = ""
    def insert(s, i, t): s.v = t
class Combo(dict):
    def __init__(s): super().__init__(); s.txt = None; s.idx = 0
    def set(s, t): s.txt = t
    def current(s, i=None):
        if i is None: return s.idx
        s.idx = i
root = mock.MagicMock(); root.after = lambda ms, f=None, *a: (f(*a) if f else None)
CH.ConectorApp._detectar_mt5 = lambda self: None
CH.ConectorApp._loop_monitor = lambda self: setattr(self, "_campanha_rodou", True)
pontes = []
class FakePonte:
    def __init__(s, toks, mql5, **k): s.toks = toks; s.parado = False; pontes.append(s)
    def iniciar(s): return True
    def parar(s, *a): s.parado = True
CH.PonteLateral = FakePonte
CH.listar_meus_bots = lambda t: (True, [{"id": 13, "nome": "Demo BTC 01", "simbolo": "BTCUSD", "online": False}])
CH.listar_bots_laterais = lambda t: (True, [{"id": 1, "nome": "XAU M15 · Lateral R0", "estado": "enviado", "_lateral": True}])
CH.salvar_token = lambda t: None; CH.sinalizar_parada = lambda t: None
app = CH.ConectorApp(root)
app.entry_token = Entry(); app.combo_bots = Combo(); app.lbl_status = mock.MagicMock(); app.btn_conectar = mock.MagicMock(); app.mql5_dir = "C:/x/MQL5"
app.entry_token.insert(0, "tokCampanha123 lat_abcdefghijkl")
ok = []
camp, lat = app._tokens_campo(); ok.append(("separa tokens", camp == ["tokCampanha123"] and lat == ["lat_abcdefghijkl"]))
app._carregar_meus_bots("tokCampanha123", lat)
ok.append(("Meus bots junta campanha + 🧪", list(app.combo_bots["values"]) == ["Demo BTC 01 · BTCUSD  (◌ offline)", "🧪 XAU M15 · Lateral R0  (sombra · enviado)"]))
app.combo_bots.idx = 1; n0 = len(msgs); app._reinstalar_click(); app._desinstalar_click(); app._deletar_click()
ok.append(("botões em bot sombra só explicam", len(msgs) == n0 + 3 and all("SOMBRA" in m[1] for m in msgs[n0:])))
app._toggle_conectar(); import time; time.sleep(0.2)
ok.append(("Conectar: campanha + ponte com só o lat_", app.rodando and app.bot_token == "tokCampanha123" and getattr(app, "_campanha_rodou", False) and pontes and pontes[-1].toks == ["lat_abcdefghijkl"]))
app._toggle_conectar(); time.sleep(0.2)
ok.append(("Parar desliga a ponte", not app.rodando and pontes[-1].parado))
app.entry_token.delete(0); app.entry_token.insert(0, "lat_soLateral000"); app.__dict__.pop("_campanha_rodou", None); app._toggle_conectar(); time.sleep(0.2)
ok.append(("só token lat_: não liga a campanha, liga a ponte", app.rodando and app.bot_token == "" and not getattr(app, "_campanha_rodou", False) and pontes[-1].toks == ["lat_soLateral000"]))
for n, v in ok: print("OK   " if v else "FALHA", n)
sys.exit(0 if all(v for _, v in ok) else 1)
