-- 0022 (C27R55) — DEFEITO COMPROVADO NA COLETA DE CANDLES (auditoria_candles): a API grava as 18 velas de cada snapshot; só a em formação e a
-- última fechada têm a hora informada pelo EA ('ea'); as anteriores têm hora contada para trás ('aritmetico', sem pausa de mercado). Na pausa
-- diária do Gold (e nos fins de semana) essas velas chegam deslocadas e o 'on conflict' as MISTURAVA na barra real (máxima = greatest, mínima =
-- least, fechamento sobrescrito). Evidência: XAUUSD 15→16/10, 38 de 383 barras M15 com abertura longe do fechamento anterior; H1 com máxima
-- 4177,43 repetida em duas barras. Correção: a vela 'ea' é a verdade e substitui a 'aritmetico'; uma 'aritmetico' nunca altera uma 'ea'.
-- Só grava; nada decide com esta tabela. Linhas já gravadas NÃO são alteradas (histórico preservado; o relatório declara a limitação).
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
      -- aud-3 (C27R55): barra com hora 'ea' (informada pelo EA: em formação ou última fechada) é a verdade; a contada para trás ('aritmetico')
      -- pode estar deslocada por pausa do mercado e NUNCA altera uma 'ea'; uma 'ea' que chega substitui por inteiro a 'aritmetico' guardada.
      o = case when excluded.carimbo = 'ea' and public.auditoria_candles.carimbo <> 'ea' then excluded.o else public.auditoria_candles.o end,
      h = case when excluded.carimbo <> 'ea' and public.auditoria_candles.carimbo = 'ea' then public.auditoria_candles.h
               when excluded.carimbo = 'ea' and public.auditoria_candles.carimbo <> 'ea' then excluded.h
               else greatest(public.auditoria_candles.h, excluded.h) end,
      l = case when excluded.carimbo <> 'ea' and public.auditoria_candles.carimbo = 'ea' then public.auditoria_candles.l
               when excluded.carimbo = 'ea' and public.auditoria_candles.carimbo <> 'ea' then excluded.l
               else least(public.auditoria_candles.l, excluded.l) end,
      c = case when excluded.carimbo <> 'ea' and public.auditoria_candles.carimbo = 'ea' then public.auditoria_candles.c
               when excluded.carimbo = 'ea' and public.auditoria_candles.carimbo <> 'ea' then excluded.c
               when excluded.fechado or not public.auditoria_candles.fechado then excluded.c else public.auditoria_candles.c end,
      vol = case when excluded.carimbo <> 'ea' and public.auditoria_candles.carimbo = 'ea' then public.auditoria_candles.vol
                 when excluded.carimbo = 'ea' and public.auditoria_candles.carimbo <> 'ea' then excluded.vol
                 when excluded.fechado or not public.auditoria_candles.fechado then excluded.vol else public.auditoria_candles.vol end,
      fechado = case when excluded.carimbo <> 'ea' and public.auditoria_candles.carimbo = 'ea' then public.auditoria_candles.fechado
                     when excluded.carimbo = 'ea' and public.auditoria_candles.carimbo <> 'ea' then excluded.fechado
                     else public.auditoria_candles.fechado or excluded.fechado end,
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
  return jsonb_build_object('candles', n_c, 'leituras', n_l, 'versao', 'aud-3');
end $$;
revoke all on function public.auditoria_registrar(bigint, text, bigint, timestamptz, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.auditoria_registrar(bigint, text, bigint, timestamptz, jsonb, jsonb) to service_role;
notify pgrst, 'reload schema';
