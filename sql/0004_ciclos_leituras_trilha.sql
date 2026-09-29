-- 0004_ciclos_leituras_trilha.sql — C27R13 (api v7.80-c27r13-ciclos-lm)
-- Learning Machine: registro de CADA ciclo de leitura (inclusive sem trade) e a
-- trilha auditavel snapshot -> leituras -> Ciclos -> decisao/veto -> atestado ->
-- persistencia -> RPC -> comando -> resposta MT5 -> abertura/fechamento.
-- Aplicacao: homologacao (hvraqquuvybzpqwkqlcu) e bancada isolada. Producao: SO pelo dono.
-- Sem BEGIN/COMMIT (o apply_migration ja envolve em transacao).

create table if not exists public.ciclo_leituras (
  id              bigint generated always as identity primary key,
  bot_id          bigint not null references public.conector_bots(id) on delete cascade,
  user_id         uuid   not null,
  simbolo         text,
  magic           bigint,
  barra_m15       timestamptz not null,          -- instante (UTC) em que a barra M15 de referencia FECHOU (= ts_barra do atestado)
  primeira_em     timestamptz not null default now(),
  ultima_em       timestamptz not null default now(),
  n_snapshots     integer not null default 1,
  snapshot_id     bigint,                        -- 1o snapshot da barra (a leitura de referencia)
  snapshot_id_ult bigint,
  leituras        jsonb  not null,               -- por TF, do 1o snapshot da barra (referencia)
  leituras_ult    jsonb,                         -- por TF, do snapshot mais recente da barra
  ciclos          jsonb  not null,               -- resumo Ciclo 1 / Ciclo 2 / decisao consolidada
  completa        boolean not null default false,
  alinhado_c1     boolean,
  alinhado_c2     boolean,
  decisao         text   not null check (decisao in ('comprar','vender','observar','bloquear')),
  regra           text,
  motivo          text,
  versoes         jsonb,
  falhas          jsonb,
  unique (bot_id, barra_m15)
);
create index if not exists idx_ciclo_leit_bot_barra on public.ciclo_leituras (bot_id, barra_m15 desc);

create table if not exists public.ciclo_trilha (
  id          bigint generated always as identity primary key,
  bot_id      bigint references public.conector_bots(id) on delete cascade,
  user_id     uuid,
  simbolo     text,
  magic       bigint,
  barra_m15   timestamptz,
  etapa       text not null check (etapa in ('snapshot','leituras','ciclos','decisao','veto',
                'atestado','persistencia','rpc','comando','resposta_mt5','abertura',
                'fechamento','falha_coleta','divergencia')),
  estado      text not null check (estado in ('ok','recusado','falha','aviso','pendente')),
  origem      text not null check (origem in ('ea','conector','api','rpc','mt5')),
  motivo      text,
  correlacao  text,                              -- uid da decisao ou "<bot>-<barra_m15>"
  ref         jsonb,                             -- snapshot_id, decisao_id, comando_id, ticket...
  ts          timestamptz not null default now()
);
create index if not exists idx_ciclo_trilha_bot_ts on public.ciclo_trilha (bot_id, ts desc);
create index if not exists idx_ciclo_trilha_bot_barra on public.ciclo_trilha (bot_id, barra_m15);

-- Mesma doutrina de ciclo_decisoes: so o backend (service key) le e escreve.
alter table public.ciclo_leituras enable row level security;
alter table public.ciclo_leituras force row level security;
alter table public.ciclo_trilha   enable row level security;
alter table public.ciclo_trilha   force row level security;
revoke all on public.ciclo_leituras from anon, authenticated;
revoke all on public.ciclo_trilha   from anon, authenticated;
grant all on public.ciclo_leituras to service_role;
grant all on public.ciclo_trilha   to service_role;
