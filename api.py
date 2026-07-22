# ============================================================
#  BotTested API — v6.94  (a versão REAL está em API_VERSAO/BUILD_TAG, ~linha 640, e no /versao)
#  Build: 2026-07-19s-fix-raiz-ia-nameerror | Deploy: Railway
#  >>> AO ENTREGAR NOVO api.py: atualizar ESTA linha + API_VERSAO + BUILD_TAG juntos <<<
#  Novidades v3.1:
#  - FIX CRITICO: rodar_codigo_custom agora executa de verdade com o motor
#    backtesting.py (antes engolia erro e devolvia sempre 0 trades).
#    Editor Python, IA e galeria de estrategias passam a funcionar de fato.
#  - Parser do /gerar-bot-ia entende portugues (canal high/low, cruzamento
#    com periodos, tolerante a typos; "2 medias de 20" = periodo 20).
#  Historico anterior:
#  Novidades v3.0:
#  - Catalogo 40 ativos em 7 categorias com gating por plano (/ativos/catalogo)
#  - Galeria de 10 estrategias prontas, 2 assinaturas da casa (/estrategias/prontas)
#  - Conector MT5 read-only: /conector/registrar, /conector/snapshot,
#    /conector/evento, /conector/bots (token, nunca credenciais de corretora)
#  - Agente Bloco F (F1-F4): consistencia vivo x backtest, cooldown anti-spam
#    (/agente/sugestoes, /agente/sugestoes/lida)
#  Historico anterior:
#  Novidades v2.1:
#  - v3.3: /radar/analisar (OffMind + coletivo -> sugestao aplicavel no chat do Radar)
#  - /babymachine/contador: endpoint leve que retorna total de backtests
#    do usuario (count exact) p/ contador no topo da coluna esquerda.
#  Historico anterior:
#  Novidades v2.0:
#  - BabyMachine: comportamento agora inclui serie evolucao (Sharpe e
#    retorno de cada backtest do usuario em ordem cronologica) p/ 2 graficos.
#  Historico anterior:
#  Novidades v1.9:
#  - BabyMachine analise: /babymachine/analisar le os dados coletados e
#    gera (B) aprendizado coletivo anonimo (tendencias do banco inteiro) +
#    (C) deteccao de comportamento de risco da jornada do usuario
#    (overfitting manual, win-alto/retorno-negativo, etc). Analise por
#    regras puras. user_id se logado, senao sessao_id. Sempre honesto.
#  Historico anterior:
#  Novidades v1.8:
#  - Renomeacao interna da feature de padroes para OffMind.
#    Rotas /offmind/analisar e /offmind/padroes. Tecnicas-chave protegidas no backend.
#  Historico anterior:
#  Novidades v1.7:
