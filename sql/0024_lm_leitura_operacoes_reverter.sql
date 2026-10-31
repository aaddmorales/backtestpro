-- Reverte 0024 (só homologação). Apaga SOMENTE lm_eventos e lm_correcoes. Nenhuma outra tabela é tocada.
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker — reversão só em homologação';
  END IF;
END $$;
drop table if exists public.lm_correcoes;
drop table if exists public.lm_eventos;
