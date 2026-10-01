-- 0005 (C27R14 rev.2) — a trilha dos Ciclos passa a registrar a etapa 'motor'
-- (saúde do leitor do motor no PC: processo, espelho, identidade, fuso, assinatura).
-- Sem BEGIN/COMMIT (o apply_migration ja envolve em transacao). Idempotente.
alter table public.ciclo_trilha drop constraint if exists ciclo_trilha_etapa_check;
alter table public.ciclo_trilha add constraint ciclo_trilha_etapa_check check (etapa in (
  'snapshot','leituras','ciclos','motor','decisao','veto','persistencia','rpc','comando',
  'resposta_mt5','abertura','fechamento','divergencia','falha_coleta','atestado'));
