-- Reverte 0025 (só homologação). Apaga SOMENTE lateral_eventos, lateral_chaves e lateral_bots.
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker — reversão só em homologação';
  END IF;
END $$;
drop table if exists public.lateral_eventos;
drop table if exists public.lateral_chaves;
drop table if exists public.lateral_bots;
