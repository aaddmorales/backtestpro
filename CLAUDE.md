# BotTested — regras permanentes do projeto

## Relatórios: sempre com janelas de gráfico explicativas (regra do dono, 08/11/2026)
Todo relatório gerado pela plataforma ou entregue numa ordem tem, além das tabelas, **janelas de gráfico** que expliquem as decisões e os dados do relatório.
- Cada janela marca no próprio gráfico: o nível (suporte/resistência) que justificou a decisão, a barra de sinal/rompimento, o gatilho, a entrada, a saída e o resultado em R.
- Toda janela desenha também o **canal EMA20 High / EMA20 Low** (média móvel exponencial de 20 das máximas e das mínimas, calculada com histórico suficiente antes da janela, no timeframe do gráfico), em **amarelo** (#ffd60a, traço mais grosso que as velas), com legenda — referência do dono em todos os gráficos (regra de 08/11/2026).
- Casos em que o sistema **deixou passar** também ganham janela, com o motivo escrito no título (ex.: "tocou sem superar", "não alcançou", "já havia posição aberta", "M15 não confirmou").
- O título de cada janela diz em uma linha o que aconteceu e por quê; legenda curta para cada marca (cor/linha).
- Exemplos escolhidos por sorteio fixo dentro de cada categoria (não pelo resultado), cobrindo pelo menos: um caso que entrou e um que deixou passar; quando houver, um que perdeu e um que venceu.
- Referência de formato: painel "Rompimento de Lateralização" (O48, `app.html` → `latCardHTML`/`grafico()`; relatórios das O43–O46 em `experimentos/`).
- Dados simulados ou de replay são rotulados como tais na própria janela.
