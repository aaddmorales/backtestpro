-- Reverte a ORDEM 050 (não toca em nenhuma tabela da campanha).
drop function if exists lm_diag_o50(timestamptz, timestamptz, bigint[], text[], integer);
drop table if exists lm_diagnosticos;
