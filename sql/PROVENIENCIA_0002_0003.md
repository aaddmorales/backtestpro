# Proveniência das migrações 0002/0003 (C27R10 · 28/set/2026)

## 1. Onde as auditadas foram localizadas
- **Não estão** no GitHub (nenhuma ref), no Google Drive nem nos uploads desta sessão.
- **Os zips que as carregavam não chegaram aqui:**
  - `FECHAMENTO_P1P4_27SET.zip` (sha 0db39b43…)
  - `CORRETIVA_P2_CONECTOR_OP_27SET.zip` (sha bffb8e50…)
- **Fonte usada:** o registro literal do chat de 27/set ("Registro de etapa 1A-S-R1 e retomada de projeto", claude.ai/chat/3ee6a664-…). Ele guarda o texto exato das ferramentas que criaram e editaram cada arquivo:
  - **0002 c27r2:** heredoc integral (`cat > ../relatorios/0002_ciclo_decisoes.sql`), na bancada corretiva2. Sem edição posterior registrada.
  - **0003:** montada em 4 passos:
    1. `create_file` v7.70-c27r3 (bancada final)
    2. `sed` do cabeçalho → v7.71-c27r4
    3. patch v2 c27r4/P1+P2: predicados do contrato r01v4 na RPC e rodapé T6–T8
    4. patch v3 c27r4fim: vínculo token/user/símbolo conferido no banco e T5b
- A reconstrução reaplica exatamente esses textos, na mesma ordem, com as entidades HTML (`&gt;` `&lt;`) desfeitas.

## 2. SHAs

| Arquivo | SHA-256 |
|---|---|
| 0002 auditada (original) | **NÃO DISPONÍVEL** — os bytes originais não existem em nenhuma fonte alcançável e nenhum SHA por arquivo foi registrado |
| 0002 auditada (reconstruída) = `sql/0002_ciclo_decisoes.sql` deste commit | `ff5a8a91625c55406d423d102ab60cba9c88336224a665c90d39fd05a2812f71` |
| 0003 v3 auditada (original) | **NÃO DISPONÍVEL** (mesmo motivo) |
| 0003 v3 auditada (reconstruída) = `sql/0003_r01_claim_transacional.sql` deste commit | `9e9b447b44a5c985cdb988914543d591b861b652f94f85082c6e17f2570500dc` |
| 0002 reescrita C27R9 (commit 120bf09, SUPERADA) | `4a1949ac4ba126572500d80bbcd6ba7699a5c0826687c1fb0f30b902fc51e06d` |
| 0003 reescrita C27R9 (commit 120bf09, SUPERADA) | `b9d52ab5f5958233dcbcf3f95e47e9a930bb6bee00ee4814a00c27e63627f29d` |

**Para fechar a conferência por byte:** anexar um dos dois zips (de preferência o FECHAMENTO_P1P4) e rodar `sha256sum` nos dois `.sql`. Se divergirem da reconstrução, vale o original, e esta reconstrução é descartada.

## 3. Diferenças de contrato: reescrita C27R9 × auditada

Resolução aplicada: **o contrato auditado vence**. O que a reescrita acrescentou sem auditoria sai, ou vira proposta.

| # | Ponto | Reescrita C27R9 | Auditada (vigente agora) | Resolução |
|---|---|---|---|---|
| 1 | Retorno da RPC | (ok, motivo, comando_id) | (ok, motivo, comando_id, **uid**) | auditada; a API lê só ok/motivo/comando_id, compatível |
| 2 | Defaults | sem | p_params `'{}'`, p_origem `'manual'` | auditada |
| 3 | Motivos | detalhados (decisao_inexistente, …_de_outro_simbolo, …_vencida, …) | genéricos: `emissao_so_para_abertura`, `vinculo_bot_invalido(token_user)`, `decisao_invalida_vencida_ou_ja_consumida` | auditada (menos oráculo) |
| 4 | Duplicata de uid | unique_violation cru propagado | `EXCEPTION WHEN unique_violation → RAISE 'uid_ja_comandado(dedup_unique)'`, que desfaz o claim | auditada |
| 5 | params do comando | só o uid do banco | params ‖ {uid, decisao{id, uid, ts_barra, veredito}} vindos do **banco** | auditada |
| 6 | Checagem do topdown na RPC | `veredito->'topdown'->>0='autorizada'` | só contrato=r01v4 + cv1_veredito=autorizada (o topdown é checado pela API) | auditada; o topdown na RPC vira **proposta** |
| 7 | Bot excluído na RPC | recusava `excluido` | não confere `excluido` | auditada; conferir `excluido` na RPC vira **proposta** |
| 8 | Índice parcial | `WHERE tipo IN (buy,sell)` | `… AND params ? 'uid'` | auditada |
| 9 | FK bot_id | inline na 0002 | adicionada na 0003: `fk_ciclo_decisoes_bot` NOT VALID + VALIDATE | auditada |
| 10 | RLS/grants de ciclo_decisoes | na 0002; SELECT/INSERT/UPDATE para service_role; REVOKE também de PUBLIC | na 0003; `GRANT ALL` service_role; REVOKE de anon/authenticated | auditada |
| 11 | status | + 'expirada' | só emitida/consumida | auditada |
| 12 | coluna de consumo | consumida_em | **ts_consumo** | auditada (a API não lê nenhuma das duas) |
| 13 | CHECK do id (32 hex) | tinha | não tem | auditada |
| 14 | índice idx_ciclo_dec_bot(bot_id, status) | faltava | tem | auditada |
| 15 | nomes das UNIQUE | nomeadas ux_… | automáticas (`unique (…)`) | auditada |
| 16 | guard de isolamento | DO $$ embutido na 0002/0003 | fora das migrações (0000_precheck auditado) | guard movido para `sql/isolado/0000_guard_isolado.sql`. O 0000_precheck auditado não foi recuperado por inteiro |
| 17 | transação | implícita | `BEGIN; … COMMIT;` explícitos na 0003 | auditada |

## 4. Aplicação no isolado local (bancada)
1. Desfeitas as reescritas da C27R9: drop da função, do índice e da ciclo_decisoes; limpeza de mt5_comandos.
2. Aplicadas, nesta ordem: `0000_guard_isolado` → `0002` (auditada) → `0003` (auditada).
3. `pg_get_function_result` = `TABLE(ok boolean, motivo text, comando_id bigint, uid text)`, idêntico ao que o 0000_precheck v3 auditado exige.
4. T1–T8 reescritos para o contrato auditado: **8/8, 0 skip**.
