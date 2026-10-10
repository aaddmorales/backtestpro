-- 0015 (C27R32) — COLETA DE AUDITORIA: o que o sistema VIU, ao vivo, para o relatório confrontar mercado × leitura ×
-- decisão × resultado sem extração manual. Só grava; nenhuma decisão, ordem ou alteração operacional depende destas
-- tabelas. Nada é apagado. Acesso só do servidor (service_role).
--
-- auditoria_candles: candles por bot × timeframe × abertura (UTC), vistos nos snapshots do EA (18 por TF a cada ~20 s).
--   'fechado' = a barra já apareceu como fechada num snapshot posterior; 'carimbo' = como a hora da barra foi conhecida
--   ('ea' = veio da posição da última barra fechada ou em formação informada pelo EA; 'aritmetico' = contado para trás a
--   partir dessa barra, sem feriado/fim de semana). A máxima só cresce e a mínima só cai entre snapshots.
-- auditoria_leituras: 1 linha por snapshot (leitura viva): preço/spread/flutuante, estado do motor e sua barra, zonas do
--   canal do EA por TF, regime, ATR/EMA, padrões do OffMind, candidatos presentes — nada de token/segredo.
create table if not exists public.auditoria_candles (
  bot_id        bigint not null,
  simbolo       text not null,
  tf            text not null,
  abertura_utc  timestamptz not null,
  fechamento_utc timestamptz not null,
  o numeric, h numeric, l numeric, c numeric, vol numeric,
  tipo_volume   text not null default 'tick',
  fechado       boolean not null default false,
  carimbo       text not null default 'aritmetico',
  primeiro_visto_utc timestamptz not null default now(),
  ultimo_visto_utc   timestamptz not null default now(),
  snapshot_id   bigint,
  fonte         text not null default 'snapshot do EA (coleta ao vivo)',
  primary key (bot_id, tf, abertura_utc)
);
create index if not exists auditoria_candles_bot_tf_fech on public.auditoria_candles (bot_id, tf, fechamento_utc);

create table if not exists public.auditoria_leituras (
  id            bigserial primary key,
  bot_id        bigint not null,
  simbolo       text not null,
  snapshot_id   bigint,
  ts            timestamptz not null default now(),
  barra_m15_utc timestamptz,
  preco numeric, spread_pts numeric, point numeric, flutuante numeric, posicoes integer,
  off_servidor_s integer,
  motor         jsonb,
  zonas         jsonb,
  regime        jsonb,
  indicadores   jsonb,
  offmind       jsonb,
  candidatos    jsonb,
  sessao_teste_id text
);
create index if not exists auditoria_leituras_bot_ts on public.auditoria_leituras (bot_id, ts);
create index if not exists auditoria_leituras_bot_barra on public.auditoria_leituras (bot_id, barra_m15_utc);

-- registro em UMA chamada por snapshot: upsert dos candles + 1 leitura
create or replace function public.auditoria_registrar(p_bot bigint, p_simbolo text, p_snapshot_id bigint, p_ts timestamptz,
                                                       p_candles jsonb, p_leitura jsonb)
returns jsonb language plpgsql security definer set search_path = public as $$
declare n_c integer := 0; n_l integer := 0;
begin
  if jsonb_typeof(p_candles) = 'array' then
    insert into public.auditoria_candles (bot_id, simbolo, tf, abertura_utc, fechamento_utc, o, h, l, c, vol, tipo_volume, fechado, carimbo,
                                          primeiro_visto_utc, ultimo_visto_utc, snapshot_id)
    select p_bot, p_simbolo, x->>'tf', (x->>'abertura_utc')::timestamptz, (x->>'fechamento_utc')::timestamptz,
           (x->>'o')::numeric, (x->>'h')::numeric, (x->>'l')::numeric, (x->>'c')::numeric, (x->>'vol')::numeric,
           coalesce(x->>'tipo_volume', 'tick'), coalesce((x->>'fechado')::boolean, false), coalesce(x->>'carimbo', 'aritmetico'),
           p_ts, p_ts, p_snapshot_id
      from jsonb_array_elements(p_candles) x
    on conflict (bot_id, tf, abertura_utc) do update set
      h = greatest(public.auditoria_candles.h, excluded.h),
      l = least(public.auditoria_candles.l, excluded.l),
      c = case when excluded.fechado or not public.auditoria_candles.fechado then excluded.c else public.auditoria_candles.c end,
      vol = case when excluded.fechado or not public.auditoria_candles.fechado then excluded.vol else public.auditoria_candles.vol end,
      fechado = public.auditoria_candles.fechado or excluded.fechado,
      carimbo = case when excluded.carimbo = 'ea' then 'ea' else public.auditoria_candles.carimbo end,
      abertura_utc = public.auditoria_candles.abertura_utc,
      ultimo_visto_utc = p_ts, snapshot_id = p_snapshot_id;
    get diagnostics n_c = row_count;
  end if;
  if jsonb_typeof(p_leitura) = 'object' then
    insert into public.auditoria_leituras (bot_id, simbolo, snapshot_id, ts, barra_m15_utc, preco, spread_pts, point, flutuante, posicoes,
                                           off_servidor_s, motor, zonas, regime, indicadores, offmind, candidatos, sessao_teste_id)
    values (p_bot, p_simbolo, p_snapshot_id, p_ts, (p_leitura->>'barra_m15_utc')::timestamptz, (p_leitura->>'preco')::numeric,
            (p_leitura->>'spread_pts')::numeric, (p_leitura->>'point')::numeric, (p_leitura->>'flutuante')::numeric,
            (p_leitura->>'posicoes')::integer, (p_leitura->>'off_servidor_s')::integer, p_leitura->'motor', p_leitura->'zonas',
            p_leitura->'regime', p_leitura->'indicadores', p_leitura->'offmind', p_leitura->'candidatos', p_leitura->>'sessao_teste_id');
    n_l := 1;
  end if;
  return jsonb_build_object('candles', n_c, 'leituras', n_l);
end $$;
revoke all on function public.auditoria_registrar(bigint, text, bigint, timestamptz, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.auditoria_registrar(bigint, text, bigint, timestamptz, jsonb, jsonb) to service_role;
grant select, insert, update on public.auditoria_candles, public.auditoria_leituras to service_role;
grant usage, select on sequence public.auditoria_leituras_id_seq to service_role;
revoke all on public.auditoria_candles, public.auditoria_leituras from anon, authenticated;
notify pgrst, 'reload schema';
