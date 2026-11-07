-- 0025_lateral_o48.sql  (ORDEM 048 · par da api 8.29.5 / app v10.88.5)
-- Cartão "Rompimento de Lateralização" (Experimental · teste em sombra): bots do teste, chave do leitor e eventos.
-- ESCOPO: SOMENTE homologação (exige public._bt_homolog_marker; a produção não tem). Só CRIA 3 tabelas novas;
-- nenhuma tabela existente é alterada (conector_bots, lm_eventos e as da campanha ficam intocadas).
-- Reversão: 0025_lateral_o48_reverter.sql.
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker — 0025 só roda em homologação';
  END IF;
END $$;

create table if not exists public.lateral_bots (
  id             bigserial primary key,
  user_id        text        not null,
  nome           text        not null,
  ativo          text        not null check (ativo in ('XAUUSD','BTCUSD')),
  tf             text        not null check (tf in ('M15','M30','H1')),
  regra_versao   text        not null,
  modo           text        not null default 'sombra' check (modo = 'sombra'),
  estado         text        not null default 'criado' check (estado in ('criado','enviado','conectado','parado')),
  criado_em      timestamptz not null default now(),
  enviado_em     timestamptz,
  conectado_em   timestamptz,
  parado_em      timestamptz,
  confirmacao    jsonb       not null default '{}'::jsonb,
  coleta_inicio  timestamptz,
  coleta_fim     timestamptz,
  ultimo_contato timestamptz
);
create unique index if not exists lateral_bots_ativo_uk on public.lateral_bots (user_id, ativo, tf) where estado <> 'parado';
create index if not exists lateral_bots_user_idx on public.lateral_bots (user_id);

create table if not exists public.lateral_chaves (
  user_id    text        primary key,
  chave_hash text        not null unique,
  criada_em  timestamptz not null default now()
);

create table if not exists public.lateral_eventos (
  id          bigserial primary key,
  user_id     text        not null,
  bot_id      bigint      not null references public.lateral_bots(id) on delete cascade,
  chave       text        not null,
  tipo        text        not null,
  t_evento    timestamptz,
  payload     jsonb       not null default '{}'::jsonb,
  recebido_em timestamptz not null default now(),
  constraint lateral_eventos_bot_chave_uk unique (bot_id, chave)
);
create index if not exists lateral_eventos_bot_idx on public.lateral_eventos (bot_id, t_evento);

alter table public.lateral_bots    enable row level security;
alter table public.lateral_chaves  enable row level security;
alter table public.lateral_eventos enable row level security;
revoke all on public.lateral_bots, public.lateral_chaves, public.lateral_eventos from anon, authenticated;
