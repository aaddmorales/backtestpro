-- 0013 (rev. C27R30) — correção do drawdown diário em sessao_diario e da cobertura (barra fechada na virada conta no dia anterior): o pico agora é o MÁXIMO CORRENTE do resultado acumulado
-- do dia (antes era o maior resultado individual, o que podia exagerar a queda); 'autoridade emitiria' conta SERIA/seria (ilike). Só a função; nada é apagado.
create or replace function public.sessao_diario(p_sessao text, p_bots bigint[])
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare s public.sessoes_teste%rowtype; v_fuso text; out jsonb := '{}'::jsonb; b record; v jsonb; d record;
begin
  select * into s from public.sessoes_teste where id = p_sessao;
  if not found or s.inicio is null then return '{}'::jsonb; end if;
  v_fuso := coalesce(s.config->>'fuso_diario', 'UTC');
  for b in select cb.id, cb.simbolo from public.conector_bots cb where cb.id = any(p_bots) loop
    v := '[]'::jsonb;
    for d in
      with dias as (
        select generate_series(((s.primeira_barra at time zone v_fuso))::date, ((least(coalesce(s.fim, now()), now()) at time zone v_fuso))::date, interval '1 day')::date as dia
      ),
      jan as (select dia, (dia::timestamp at time zone v_fuso) as ini, ((dia + 1)::timestamp at time zone v_fuso) as fim from dias),
      fechadas as (select x.janela from jsonb_array_elements(coalesce(s.config->'horarios'->b.simbolo, '[]'::jsonb)) x(janela)),
      esp as (
        select j.dia, count(*) as n
          from jan j, generate_series(greatest(j.ini, s.primeira_barra), least(j.fim, coalesce(s.fim, now())), interval '15 minutes') g
         where g > greatest(j.ini, s.primeira_barra - interval '1 second') and g <= least(j.fim, coalesce(s.fim, now()))
           and not exists (select 1 from fechadas f
                            where extract(isodow from (g - interval '1 minute') at time zone v_fuso)::int in (select jsonb_array_elements_text(f.janela->'dias')::int)
                              and ((g - interval '1 minute') at time zone v_fuso)::time >= (f.janela->>'de')::time
                              and ((g - interval '1 minute') at time zone v_fuso)::time <  (f.janela->>'ate')::time)
         group by j.dia),
      rec as (select ((l.barra_m15 - interval '1 minute') at time zone v_fuso)::date as dia, count(distinct l.barra_m15) as n   -- barra fechada exatamente na virada pertence ao dia anterior (como em esp)
                from public.ciclo_leituras l where l.bot_id = b.id and l.sessao_teste_id = p_sessao group by 1),
      ab as (select (a.ts_reserva at time zone v_fuso)::date as dia, count(*) filter (where a.estado in ('aberta','fechada')) as aberturas,
                    count(*) filter (where a.estado = 'cancelada') as canceladas
               from public.sessao_aberturas a where a.sessao_teste_id = p_sessao and a.bot_id = b.id group by 1),
      fe as (select (a.ts_fechamento at time zone v_fuso)::date as dia, count(*) as fechamentos,
                    round(coalesce(sum(a.resultado_usd), 0), 2) as resultado, round(coalesce(sum(a.lucro), 0), 2) as bruto,
                    round(coalesce(sum(coalesce(a.comissao, 0) + coalesce(a.swap, 0)), 0), 2) as custos,
                    count(*) filter (where a.resultado_usd > 0) as ganhos, count(*) filter (where a.resultado_usd < 0) as perdas
               from public.sessao_aberturas a where a.sessao_teste_id = p_sessao and a.bot_id = b.id and a.estado = 'fechada' group by 1),
      dd as (select dia, round(min(acum - greatest(0, pico)), 2) as drawdown from (
               select dia, acum, max(acum) over (partition by dia order by ts, id rows between unbounded preceding and current row) as pico from (
                 select (a.ts_fechamento at time zone v_fuso)::date as dia, a.ts_fechamento as ts, a.id,
                        sum(a.resultado_usd) over (partition by (a.ts_fechamento at time zone v_fuso)::date order by a.ts_fechamento, a.id) as acum
                   from public.sessao_aberturas a where a.sessao_teste_id = p_sessao and a.bot_id = b.id and a.estado = 'fechada'
                    and a.resultado_usd is not null) q1) q2 group by dia),
      vetoc as (select dia, jsonb_object_agg(m, n) as motivos from (
                  select (sa.barra_m15 at time zone v_fuso)::date as dia, coalesce(split_part(c->>'primeiro_impedimento', ' — ', 1), 'elegível') as m, count(*) as n
                    from public.selecao_avaliacoes sa, jsonb_path_query(sa.avaliacao, '$.grupos.*.candidatos[*]') c
                   where sa.sessao_teste_id = p_sessao and sa.bot_id = b.id group by 1, 2) z group by dia),
      obs as (select (t.ts at time zone v_fuso)::date as dia, count(*) filter (where t.etapa = 'autoridade_r01v5' and t.motivo ilike 'SOMBRA%seria emitida%') as autoridade_emitiria,
                     count(*) filter (where t.etapa = 'limites' and t.estado = 'recusado') as recusadas_pelos_limites
                from public.ciclo_trilha t where t.sessao_teste_id = p_sessao and t.bot_id = b.id group by 1),
      est as (select (a.ts_fechamento at time zone v_fuso)::date as dia,
                     jsonb_object_agg(a.card || ' · ' || a.tf, jsonb_build_object('n', a.n, 'resultado_usd', a.r)) as por_estrategia
                from (select ts_fechamento, card, tf, count(*) over (partition by (ts_fechamento at time zone v_fuso)::date, card, tf) as n,
                             round(sum(resultado_usd) over (partition by (ts_fechamento at time zone v_fuso)::date, card, tf), 2) as r
                        from public.sessao_aberturas where sessao_teste_id = p_sessao and bot_id = b.id and estado = 'fechada') a
               group by 1)
      select j.dia, coalesce(esp.n, 0) as esperadas, coalesce(rec.n, 0) as recebidas,
             coalesce(ab.aberturas, 0) as aberturas, coalesce(ab.canceladas, 0) as canceladas,
             coalesce(fe.fechamentos, 0) as fechamentos, fe.resultado, fe.bruto, fe.custos, coalesce(fe.ganhos, 0) as ganhos,
             coalesce(fe.perdas, 0) as perdas, dd.drawdown, vetoc.motivos, coalesce(obs.autoridade_emitiria, 0) as autoridade_emitiria,
             coalesce(obs.recusadas_pelos_limites, 0) as recusadas_pelos_limites, est.por_estrategia
        from jan j left join esp using (dia) left join rec using (dia) left join ab using (dia) left join fe using (dia)
        left join dd using (dia) left join vetoc using (dia) left join obs using (dia) left join est using (dia)
       order by j.dia
    loop
      v := v || jsonb_build_array(jsonb_build_object(
             'dia', d.dia, 'barras_esperadas', d.esperadas, 'barras_recebidas', d.recebidas,
             'cobertura_pct', case when d.esperadas > 0 then round(100.0 * least(d.recebidas, d.esperadas) / d.esperadas, 1) end,
             'operacoes_reais_demo', d.aberturas, 'reservas_canceladas', d.canceladas, 'fechamentos', d.fechamentos,
             'resultado_liquido_usd', d.resultado, 'resultado_bruto_usd', d.bruto, 'custos_usd', d.custos,
             'ganhos', d.ganhos, 'perdas', d.perdas, 'drawdown_realizado_usd', d.drawdown,
             'observacoes_sem_execucao', jsonb_build_object('autoridade_emitiria', d.autoridade_emitiria,
                                                           'recusadas_pelos_limites', d.recusadas_pelos_limites),
             'motivos_de_veto', coalesce(d.motivos, '{}'::jsonb), 'por_estrategia_tf', coalesce(d.por_estrategia, '{}'::jsonb)));
    end loop;
    out := out || jsonb_build_object(b.id::text, jsonb_build_object('simbolo', b.simbolo, 'fuso', v_fuso, 'dias', v));
  end loop;
  return out;
end $$;
revoke all on function public.sessao_diario(text, bigint[]) from public, anon, authenticated;
grant execute on function public.sessao_diario(text, bigint[]) to service_role;
notify pgrst, 'reload schema';
