-- ═══════════════════════════════════════════════════════════════════════
--  BotTested v6.65 — FONTE ÚNICA DA VERDADE
--  Rodar ANTES do deploy do api.py (Supabase → SQL Editor → Run).
--  Idempotente: pode rodar mais de uma vez sem quebrar nada.
-- ═══════════════════════════════════════════════════════════════════════

-- ── 1) TABELA NOVA: mt5_jobs (substitui o dict _MT5_JOBS em memória) ─────
-- Jobs de validação do fluxo Enviar→Pendente→Veredito→Status.
-- Qualquer worker do Railway vê o mesmo estado; sobrevive a deploy/restart.
create table if not exists public.mt5_jobs (
  job_id        text primary key,
  bot_token     text not null,
  filename      text not null default '',
  magic         bigint not null default 0,
  mq5           text not null default '',
  status        text not null default 'validando',  -- validando | aprovado | reprovado
  aprovado      boolean,                             -- null enquanto valida
  log           text not null default '',
  gen_hash      text not null default '',
  pre_validado  boolean not null default false,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

-- Índices dos dois acessos quentes:
-- (a) conector buscando o job 'validando' mais recente de um bot;
-- (b) limpeza de jobs com mais de 1h (delete por idade).
create index if not exists mt5_jobs_bot_status_idx
  on public.mt5_jobs (bot_token, status, criado_em desc);
create index if not exists mt5_jobs_criado_idx
  on public.mt5_jobs (criado_em);

-- Trava anon/authenticated. A API usa a service key, que bypassa RLS.
alter table public.mt5_jobs enable row level security;

-- ── 2) mq5_cache — garante o shape que a v6.65 espera (idempotente) ──────
-- A tabela já existe em produção; isto só cobre ambientes novos e garante
-- as colunas/defaults. Na v6.65 ela vira a ÚNICA camada do cache:
-- DELETE FROM mq5_cache = cache morto de verdade, sem restart.
create table if not exists public.mq5_cache (
  gen_hash      text primary key,
  mq5           text not null default '',
  aprovado      boolean not null default false,
  atualizado_em timestamptz not null default now()
);
alter table public.mq5_cache add column if not exists aprovado boolean;
alter table public.mq5_cache add column if not exists atualizado_em timestamptz;
alter table public.mq5_cache alter column aprovado set default false;
update public.mq5_cache set aprovado = false where aprovado is null;
alter table public.mq5_cache enable row level security;
