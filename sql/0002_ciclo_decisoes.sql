-- 0002_ciclo_decisoes.sql — c27r2 (aplicação: SÓ pelo dono, nunca da bancada)
-- Tabela da AUTORIDADE de decisão dos dois Ciclos (api v7.69-c27r2).
create table if not exists ciclo_decisoes (
  id          text primary key,                 -- secrets.token_hex(16) server-side
  bot_id      bigint not null,
  simbolo     text   not null,
  lado        smallint not null check (lado in (1, -1)),
  uid         text   not null,
  ts_barra    timestamptz not null,             -- barra M15 FECHADA (leitura do servidor)
  veredito    jsonb  not null,
  status      text   not null default 'emitida'
              check (status in ('emitida', 'consumida')),
  ts_emissao  timestamptz not null default now(),
  ts_consumo  timestamptz,
  expira_em   timestamptz not null,
  unique (bot_id, uid),
  unique (bot_id, ts_barra, lado)               -- emissão idempotente
);
create index if not exists idx_ciclo_dec_bot on ciclo_decisoes (bot_id, status);
-- RECOMENDAÇÃO (defesa extra no funil de comandos; avaliar com o schema real):
-- create unique index if not exists uq_mt5_cmd_abertura_uid
--   on mt5_comandos (bot_id, (params->>'uid'))
--   where tipo in ('buy','sell') and params ? 'uid';
-- RLS: mesma doutrina das demais tabelas (service key só no backend).
