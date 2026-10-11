-- 0016 (C27R35) — DIVERGÊNCIA COMPROVADA NA CONSOLIDAÇÃO DAS ORDENS: a API 8.03/8.04 (aud-2, C27R33) monta
-- 'estrutura_por_tf', 'gestao_assinada' e 'atestado' em cada leitura viva, mas a tabela não tinha as colunas e a função
-- auditoria_registrar (0015) ignorava as três chaves — nada disso chegou ao banco entre 07:20 UTC de 11/10 e esta
-- migração. Correção: colunas + função lendo as chaves. Só grava; nenhuma decisão depende disto. Nada é apagado.
alter table public.auditoria_leituras add column if not exists estrutura_por_tf jsonb;
alter table public.auditoria_leituras add column if not exists gestao_assinada  jsonb;
alter table public.auditoria_leituras add column if not exists atestado         jsonb;

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
                                           off_servidor_s, motor, zonas, regime, indicadores, offmind, candidatos, sessao_teste_id,
                                           estrutura_por_tf, gestao_assinada, atestado)
    values (p_bot, p_simbolo, p_snapshot_id, p_ts, (p_leitura->>'barra_m15_utc')::timestamptz, (p_leitura->>'preco')::numeric,
            (p_leitura->>'spread_pts')::numeric, (p_leitura->>'point')::numeric, (p_leitura->>'flutuante')::numeric,
            (p_leitura->>'posicoes')::integer, (p_leitura->>'off_servidor_s')::integer, p_leitura->'motor', p_leitura->'zonas',
            p_leitura->'regime', p_leitura->'indicadores', p_leitura->'offmind', p_leitura->'candidatos', p_leitura->>'sessao_teste_id',
            p_leitura->'estrutura_por_tf', p_leitura->'gestao_assinada', p_leitura->'atestado');
    n_l := 1;
  end if;
  return jsonb_build_object('candles', n_c, 'leituras', n_l, 'versao', 'aud-2');
end $$;
revoke all on function public.auditoria_registrar(bigint, text, bigint, timestamptz, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.auditoria_registrar(bigint, text, bigint, timestamptz, jsonb, jsonb) to service_role;
notify pgrst, 'reload schema';
