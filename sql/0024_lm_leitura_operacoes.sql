-- 0024_lm_leitura_operacoes.sql  (ORDEM 033 + 033-A · par da api 8.31 / app v10.90)
-- ESCOPO: SOMENTE ambiente de HOMOLOGAÇÃO (banco com a sentinela public._bt_homolog_marker). Em banco sem a sentinela ABORTA
-- (a produção não tem a sentinela). Só CRIA duas tabelas novas; nenhuma tabela existente é alterada.
-- Reversão: 0024_lm_leitura_operacoes_reverter.sql (apaga só estas duas tabelas, também protegida pela sentinela).
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker — 0024 só roda em homologação';
  END IF;
END $$;

create table if not exists public.lm_eventos (
  id            bigserial primary key,
  user_id       text        not null,
  chave         text        not null,
  tipo          text        not null,
  ativo         text,
  t_evento      text,
  op_id         text,
  versao        text,
  modulo        text,
  classe        text        not null default 'desconhecida'
                check (classe in ('demo_efetiva','sombra','simulado','simulacao_historica','desconhecida')),
  payload       jsonb       not null default '{}'::jsonb,
  hash_anterior text,
  gravado_local text,
  recebido_em   timestamptz not null default now(),
  constraint lm_eventos_user_chave_uk unique (user_id, chave)
);
create index if not exists lm_eventos_user_receb_idx on public.lm_eventos (user_id, recebido_em);
create index if not exists lm_eventos_user_op_idx    on public.lm_eventos (user_id, op_id);

create table if not exists public.lm_correcoes (
  id            bigserial primary key,
  user_id       text        not null,
  chave_ref     text        not null,
  op_id         text,
  ativo         text,
  t_ref         text,
  minha_leitura text        not null,
  regiao        text,
  conceito      text,
  acao_usuario  text,
  justificativa text,
  viu_desfecho  boolean,
  conjunto      text        not null default 'correcoes-v1',
  autor         text        not null default 'usuario',
  criado_em     timestamptz not null default now()
);
create index if not exists lm_correcoes_user_idx on public.lm_correcoes (user_id, criado_em);

-- acesso só pelo backend (service role); anon/autenticado direto não leem nem escrevem
alter table public.lm_eventos   enable row level security;
alter table public.lm_correcoes enable row level security;
revoke all on public.lm_eventos, public.lm_correcoes from anon, authenticated;
