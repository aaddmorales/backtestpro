"""ORDEM 052 — resumo do bot SEM campanha = leitura do mercado no período (candles BTCUSD M15 reais de testes/dados_c27r55 + leituras SINTÉTICAS com exaustão; Supabase falso). Confere: markdown com as seções, formações R0 iguais à O44, janelas PNG com EMA20 amarela."""
import sys, os, base64, json, pandas as pd
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, RAIZ)
import api as A
d=pd.read_csv('' + os.path.join(RAIZ, 'testes', 'dados_c27r55') + '/BTCUSD_M15_202610.csv',sep='\t'); d.columns=[c.strip('<>').lower() for c in d.columns]
d['t']=pd.to_datetime(d['date']+' '+d['time'],format='%Y.%m.%d %H:%M:%S').dt.tz_localize('UTC')
cand=[{"tf":"M15","abertura_utc":t.isoformat(),"fechamento_utc":(t+pd.Timedelta(minutes=15)).isoformat(),"o":o,"h":h,"l":l,"c":c,"fechado":True} for t,o,h,l,c in zip(d.t,d.open,d.high,d.low,d.close)]
leit=[]
for k,(t,h,l) in enumerate(zip(d.t,d.high,d.low)):
    if k%2: continue
    ev=["sacudida_topo"] if k in (60,120) else (["quebra_estrutura_baixa"] if k==90 else [])
    leit.append({"ts":(t+pd.Timedelta(minutes=14)).isoformat(),"barra_m15_utc":(t+pd.Timedelta(minutes=15)).isoformat(),"preco":float(h),
      "estrutura_por_tf":{"M15":{"dir":1,"estrutura":"ascendente","regime":"lateral","localizacao":"na_resistencia","ultimo_topo":float(h)+50,"ultimo_fundo":float(l)-60,"eventos":ev,"gatilho_exaustao":None},
                          "H1":{"dir":0,"estrutura":"mista","localizacao":"meio_da_faixa","eventos":[]}},"regime":{"estado":"lateral"}})
class Q:
    def __init__(s,rows): s.rows=rows; s.f=[]
    def select(s,*a): return s
    def eq(s,k,v): return s
    def gte(s,k,v): s.f.append((k,'>=',v)); return s
    def lte(s,k,v): s.f.append((k,'<=',v)); return s
    def order(s,*a,**k): return s
    def limit(s,n): return s
    def range(s,a,b): s.r=(a,b); return s
    def execute(s):
        rows=s.rows
        for k,op,v in s.f:
            rows=[r for r in rows if r.get(k) is not None and ((pd.Timestamp(r[k])>=pd.Timestamp(v)) if op=='>=' else (pd.Timestamp(r[k])<=pd.Timestamp(v)))]
        a,b=getattr(s,'r',(0,10**9)); return type('R',(),{'data':rows[a:b+1]})()
class SB:
    def table(s,n): return Q({"auditoria_candles":cand,"auditoria_leituras":leit}.get(n,[]))
fim=d.t.iloc[-1]+pd.Timedelta(minutes=30)
class FakeDT(A._dt):
    @classmethod
    def now(cls,tz=None): return fim.to_pydatetime()
_DT0=A._dt; A._dt=FakeDT
bot={"id":15,"nome":"ML New Bot 01","simbolo":"BTCUSD","criado_em":d.t.iloc[0].isoformat(),"config_operacional":{"estrategia_nome":"Rompimento de Lateralização","timeframe_envio":"15m"}}
req=A.SesResumoIn(bot_id=15,periodo="7d")
try:
    out=A._res_leitura_bot(SB(),"u",bot,req)
finally:
    A._dt=_DT0
md=out["markdown"]



def test_o52_resumo_sem_campanha():
    for s_ in ("## 1. Identificação", "## 2. Coleta da leitura", "## 3. Resumo do período", "## 4. Linha do tempo", "## 5. Leitura por barra M15", "## 6. Operações", "## 7. Janelas de gráfico"):
        assert s_ in md, s_
    assert "| Formações R0 (gatilho armado) | 3 |" in md and "EXAUSTÃO" in md and "ROMPIMENTO DA MÉDIA" in md
    assert len(out["janelas"]) >= 3 and all(base64.b64decode(j["png_b64"])[:4] == b"\x89PNG" for j in out["janelas"])
    assert out["sessao"].startswith("sem campanha")


def test_o52_rota_com_sessao_leitura():
    """a tela manda sessao='leitura' (bot sem campanha): a ROTA tem que ir para a leitura, nunca procurar campanha."""
    chamado = {}
    orig, orig_r = A._res_leitura_bot, A._ses_resolver
    A._res_leitura_bot = lambda sb, uid, bot, req: chamado.setdefault("ok", req.sessao) or {"markdown": "ok"}
    A._ses_resolver = (lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia procurar campanha")))
    try:
        A._ses_resumo(SB(), "u", bot, A.SesResumoIn(bot_id=15, sessao="leitura", periodo="hoje"))
    finally:
        A._res_leitura_bot, A._ses_resolver = orig, orig_r
    assert chamado.get("ok") == "leitura"
