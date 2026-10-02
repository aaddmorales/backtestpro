-- 0008 (C27R19) — SELEÇÃO DE OPORTUNIDADES M15/M30/H1 (modo observar).
-- Uma avaliação por (bot, barra M15 fechada): candidatos dos cards do Professor por timeframe,
-- portões, pontuação e escolha — pelo contrato PROPOSTO e pela configuração ATUAL (r01v4).
-- É registro de observação: nada aqui emite decisão ou comando. Idempotente.
-- Sem BEGIN/COMMIT (o apply_migration ja envolve em transacao).
create table if not exists public.selecao_avaliacoes (
  id                 bigint generated always as identity primary key,
  bot_id             bigint not null references public.conector_bots(id) on delete cascade,
  user_id            uuid,
  simbolo            text not null,
  magic              bigint,
  barra_m15          timestamptz not null,
  criado_em          timestamptz not null default now(),
  versao             text not null,
  n_candidatos       integer not null default 0,
  n_elegiveis        integer not null default 0,
  n_elegiveis_atual  integer not null default 0,
  escolha_uid        text,
  escolha_atual_uid  text,
  avaliacao          jsonb not null,
  acompanhamento     jsonb,
  unique (bot_id, barra_m15)
);
create index if not exists ix_selecao_bot_barra on public.selecao_avaliacoes (bot_id, barra_m15 desc);
alter table public.selecao_avaliacoes enable row level security;
alter table public.selecao_avaliacoes force row level security;
revoke all on public.selecao_avaliacoes from anon, authenticated;
grant all on public.selecao_avaliacoes to service_role;

alter table public.ciclo_trilha drop constraint if exists ciclo_trilha_etapa_check;
alter table public.ciclo_trilha add constraint ciclo_trilha_etapa_check check (etapa in (
  'snapshot','leituras','ciclos','motor','decisao','veto','persistencia','rpc','comando',
  'resposta_mt5','abertura','fechamento','divergencia','falha_coleta','atestado','selecao'));
