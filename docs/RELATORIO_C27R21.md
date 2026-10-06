# Relatório da BabyMachine (C27R21, 06/out/2026)

Botão **📄 Gerar relatório** no cabeçalho da aba Learning Machine de cada bot. Disponível com ou sem operação.

## O que foi reaproveitado

| seção do relatório | fonte (já existia) |
|---|---|
| Leituras por timeframe | `ciclo_leituras.leituras` da barra de referência (linhas do EA, `motor.por_tf`, scanner) |
| Elos do atestado, estágios, decisão da barra | `ciclo_leituras.ciclos` (`elos`, `estagios`, `consolidada`, `origem_criterios`) |
| Seleção M15/M30/H1 | `selecao_avaliacoes` (candidatos, portões, escolha proposta × atual) |
| Trilha | `ciclo_trilha` |
| Decisões, comandos, operações | `ciclo_decisoes`, `mt5_comandos`, `babymachine_operacoes` (filtrados por bot) |
| Saúde no momento da geração, referência de estudo, checklist | o mesmo painel da tela (`/learning/ciclos/ao-vivo`) |
| Conta (equity/balance uma vez por conta) | `/monitor/geral` |

Nenhuma regra de decisão foi escrita para o relatório: ele conta, agrupa e explica o que está gravado.

## O que é novo

- `POST /learning/relatorio/gerar` — monta o relatório com um horário de corte e grava em `relatorios_gerados`.
- `POST /learning/relatorio/baixar` — devolve o relatório **gravado** em JSON ou PDF (mesmo conteúdo, mesmo identificador `REL-<bot>-<corte>-<hash>`).
- `sql/0009_relatorios.sql` — a tabela e duas funções de leitura que agregam no banco (candidatos por escala/estado/portão; trilha por etapa/estado).
- Dependências: `fpdf2` (PDF) e `tzdata` (fusos).

Sessão e posse do bot são exigidas para gerar e para baixar. Tokens, segredos e assinaturas não entram no relatório.

## Períodos

Hoje (últimas 24 h, igual ao filtro da tela), 7, 30 e 90 dias, personalizado (até 92 dias) e última barra fechada. Entram as barras M15 cujo **fechamento** está no intervalo.

## Limites conhecidos

- **Ausência de sinal** não é gravada por célula: o leitor só envia estratégias com sinal na fila. O relatório diz isso em vez de contar.
- **Causa de lacuna**: só há prova quando a barra seguinte traz a lista de barras da corretora (EA 7.81). O motivo da parada (PC, MT5, conector) não fica registrado.
- **Posições fora do magic do bot**: o EA não informa ticket nem magic de outras posições da conta; aparece só o valor (`equity − balance − flutuante dos bots`).
- A lista de barras no JSON é limitada às 400 mais recentes (as contagens usam todas); o PDF lista 120.
- "Saúde no momento da geração" vem do último snapshot e não altera o histórico.
