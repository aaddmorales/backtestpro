# Skills de terceiros — registro de importação (ORDEM 054-A, 12/11/2026)

Escopo: repositório (`.claude/skills/`), pasta que o Claude Code carrega como skills do projeto. Nenhuma skill daqui envia ordem,
fala com corretora ou exige credencial. Instruções revisadas antes da instalação (sem `curl`/`wget`, sem rede, sem segredos).

## Fontes fixadas

| Fonte | Commit fixado | Licença | Cópia da licença |
|---|---|---|---|
| github.com/ml4t/skills | `691857537a0c8befc11dc2f2ad7a458b7c7e801c` (27/10/2026) | Apache-2.0 (+ NOTICE) | `skills_licencas/ml4t-skills_LICENSE_Apache-2.0`, `skills_licencas/ml4t-skills_NOTICE` |
| github.com/tradermonty/claude-trading-skills | `4251eaaeb05d720f5ffe8e899e3b6ec1cf48e96f` (12/11/2026) | MIT | `skills_licencas/tradermonty_LICENSE_MIT` |
| github.com/marian2js/trading-skills | `f1ae7d481154b49192681187cb08d39d7e2d4524` (16/03/2026) | MIT | `skills_licencas/marian2js_LICENSE_MIT` |

## Skills instaladas

| Skill | Fonte | Pedida na ordem | Partes desligadas / dependências |
|---|---|---|---|
| ml4t-point-in-time | ml4t | sim | depende de `ml4t-lookahead-bias` (instalada). Exemplos usam pacotes `ml4t-*` (não instalados → só leitura); provedor FRED exige API key → desligado |
| ml4t-lookahead-bias | ml4t | sim | exemplos `ml4t-*` não instalados |
| ml4t-regime-awareness | ml4t | sim | exemplos `ml4t-*` não instalados |
| ml4t-walk-forward-cv | ml4t | sim | declara `purging-embargo` (NÃO instalada — fora da lista da ordem); exemplos `ml4t-*` não instalados |
| ml4t-cost-model | ml4t | sim | declara `transaction-costs` (NÃO instalada — fora da lista da ordem); exemplos `ml4t-*` não instalados |
| backtest-expert | tradermonty | sim | `scripts/evaluate_backtest.py` só stdlib, sem rede, sem API key (testado) |
| pre-trade-check | marian2js | sim | roteia para watchlist-review, catalyst-map, evidence-gap-check, thesis-validation, earnings-preview, macro-event-analysis, market-regime-analysis, portfolio-concentration — NÃO instaladas (ações/eventos; regime coberto por ml4t-regime-awareness). Auxiliares trazidas: risk-reward-sanity-check, execution-plan-check, position-sizing |
| position-management | marian2js | sim | cita post-trade-review (trazida), macro-event-analysis / earnings-preview (não instaladas) |
| post-trade-debrief | marian2js | sim | exige post-trade-review (trazida); journal-pattern-analyzer opcional (não instalada) |
| risk-reward-sanity-check | marian2js | auxiliar | usa `_lib/calculations.py` (stdlib) |
| execution-plan-check | marian2js | auxiliar | — |
| position-sizing | marian2js | auxiliar | usa `_lib/calculations.py` (stdlib) |
| post-trade-review | marian2js | auxiliar | — |
| technical-analyst | tradermonty (mesmo commit `4251eaae…`) | sim (complemento ORDEM 055, 12/11) | só leitura de gráfico; `scripts/` NÃO importada (exige `requests`, rede e FMP_API_KEY). Feita para gráfico semanal; nota de instalação inserida após o frontmatter |

Excluído de propósito: `live-trade/etoro` (acesso a corretora) e qualquer skill fora da lista da ordem.

## Patches aplicados (só caminho; nenhum conteúdo de regra)

- `backtest-expert/SKILL.md`: `skills/backtest-expert/` → `.claude/skills/backtest-expert/`.
- `references/calculation-helpers.md` (position-sizing, risk-reward-sanity-check): `skills/_lib/calculations.py` → `.claude/skills/_lib/calculations.py`.

## Patch adicional

- `technical-analyst/SKILL.md`: nota de instalação BotTested após o frontmatter (scripts desligados, referência = bottested-trader-m15).

## Arquivos importados (sha256, 16 primeiros caracteres)

| Arquivo | sha256 |
|---|---|
| `skills/_lib/calculations.py` | `12c4f20178ff1087` |
| `skills/backtest-expert/SKILL.md` | `de807ce721879515` |
| `skills/backtest-expert/references/failed_tests.md` | `84fe35cd098a2d2f` |
| `skills/backtest-expert/references/methodology.md` | `eb2a73ca5cab78c1` |
| `skills/backtest-expert/requirements.txt` | `73634381ea0c101a` |
| `skills/backtest-expert/scripts/evaluate_backtest.py` | `cffb9ae1e2a619c9` |
| `skills/backtest-expert/scripts/tests/conftest.py` | `e10033aa10fcd683` |
| `skills/backtest-expert/scripts/tests/test_evaluate_backtest.py` | `6aa5c7c7c3b91f9f` |
| `skills/execution-plan-check/SKILL.md` | `7fb32d3307b6a951` |
| `skills/execution-plan-check/references/execution-checklist.md` | `861f15e93561d328` |
| `skills/ml4t-cost-model/SKILL.md` | `6fe10bce1b17e7f1` |
| `skills/ml4t-lookahead-bias/SKILL.md` | `26d18ce123aabee4` |
| `skills/ml4t-point-in-time/SKILL.md` | `cff8e72b709d54be` |
| `skills/ml4t-regime-awareness/SKILL.md` | `460a78e9ffab166b` |
| `skills/ml4t-walk-forward-cv/SKILL.md` | `230a9d26991b4bcf` |
| `skills/position-management/SKILL.md` | `986dc544154101e4` |
| `skills/position-management/references/management-framework.md` | `5a497405bb3f6d0a` |
| `skills/position-sizing/SKILL.md` | `90f3d6bec35061e1` |
| `skills/position-sizing/assets/trade-plan-template.md` | `7513a21d698f4577` |
| `skills/position-sizing/references/calculation-helpers.md` | `6aa3661cf66bdc99` |
| `skills/position-sizing/references/methodology.md` | `21747a92fbe9164d` |
| `skills/post-trade-debrief/SKILL.md` | `dd934f0945216c75` |
| `skills/post-trade-debrief/references/workflow-framework.md` | `53ca4366251e227c` |
| `skills/post-trade-review/SKILL.md` | `1a2702bc00b74e01` |
| `skills/post-trade-review/references/review-rubric.md` | `7f01ee6d765d4014` |
| `skills/pre-trade-check/SKILL.md` | `540e40d969fce70c` |
| `skills/pre-trade-check/references/workflow-framework.md` | `43e6a0626963b067` |
| `skills/risk-reward-sanity-check/SKILL.md` | `d1a25e8f08fefdc8` |
| `skills/risk-reward-sanity-check/references/calculation-helpers.md` | `3f9e12f728a0cb74` |
| `skills/risk-reward-sanity-check/references/failure-modes.md` | `e4cd3beca82b157b` |
| `skills_licencas/marian2js_LICENSE_MIT` | `1126322e2cc8d165` |
| `skills_licencas/ml4t-skills_LICENSE_Apache-2.0` | `e97825a2b0db1501` |
| `skills_licencas/ml4t-skills_NOTICE` | `a8f05028aa76c237` |
| `skills_licencas/tradermonty_LICENSE_MIT` | `87c93cde8c3a000c` |
| `skills/technical-analyst/SKILL.md` | `2584efcd1fbfbe4f` (com nota) |
| `skills/technical-analyst/assets/analysis_template.md` | `0f9a703857cbfa08` |
| `skills/technical-analyst/references/contrarian-confirmation-checklist.md` | `2ae0a6900a30f005` |
| `skills/technical-analyst/references/technical_analysis_framework.md` | `a530ffebf10c04f2` |
