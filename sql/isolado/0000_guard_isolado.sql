-- 0000_guard_isolado.sql  (C27R10 · 28/set/2026) — SO LEITURA, zero DDL/DML.
-- Roda ANTES de 0002/0003. Aborta (RAISE) se o banco alvo nao tiver a
-- sentinela public._bt_homolog_marker (criada pela 0001 do isolado).
-- Substitui o guard que a reescrita C27R9 embutia DENTRO da 0002/0003: as
-- migracoes voltaram ao texto AUDITADO (27/set) e o guard ficou separado.
-- NAO e o 0000_precheck.sql auditado (esse nao foi recuperado por inteiro).
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker — so ambiente isolado';
  END IF;
  IF to_regclass('public.ciclo_decisoes') IS NOT NULL THEN
    RAISE EXCEPTION 'ABORTADO: ciclo_decisoes ja existe — 0002 ja aplicada ou banco sujo';
  END IF;
END $$;
