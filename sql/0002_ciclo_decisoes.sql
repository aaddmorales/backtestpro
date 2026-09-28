-- 0002_ciclo_decisoes.sql  (reautoria C27R9 · 28/set/2026)
-- A 0002 auditada em 27/set NAO chegou a esta bancada; esta e reescrita do
-- contrato que o api.py v7.77 le/escreve (_r01_emitir_decisao/_r01_validar_decisao).
-- Aplicar SO em ambiente isolado. Ordem: 0002 -> 0003.
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker (so ambiente isolado)';
  END IF; END $$;

CREATE TABLE IF NOT EXISTS public.ciclo_decisoes (
  id          text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
  bot_id      bigint NOT NULL REFERENCES public.conector_bots(id) ON DELETE CASCADE,
  simbolo     text NOT NULL,
  lado        smallint NOT NULL CHECK (lado IN (1, -1)),
  uid         text NOT NULL,
  ts_barra    timestamptz NOT NULL,
  veredito    jsonb NOT NULL,
  status      text NOT NULL DEFAULT 'emitida' CHECK (status IN ('emitida','consumida','expirada')),
  ts_emissao  timestamptz NOT NULL DEFAULT now(),
  expira_em   timestamptz NOT NULL,
  consumida_em timestamptz,
  CONSTRAINT ux_ciclo_decisoes_bot_uid UNIQUE (bot_id, uid),
  CONSTRAINT ux_ciclo_decisoes_bot_barra_lado UNIQUE (bot_id, ts_barra, lado));

ALTER TABLE public.ciclo_decisoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ciclo_decisoes FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.ciclo_decisoes FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.ciclo_decisoes TO service_role;
-- service_role tem BYPASSRLS; anon/authenticated: nenhuma policy = deny-all.
