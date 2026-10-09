-- 0012 — C27R26 · CAMPANHA CONTÍNUA (sem término) sobre a sessão de ensaio da 0011
-- SOMENTE homologação. Nada é apagado: sessões anteriores e histórico ficam como estão.
-- Campanha contínua = sessoes_teste com tipo 'continua' e fim_previsto NULL. Os limites de risco por operação,
-- agregado e de posições não mudam; aberturas e perda realizada passam a contar POR DIA num fuso único
-- (config.fuso_diario). Três perdas consecutivas suspendem até revisão (não liberam com a virada do dia).

alter table public.sessoes_teste alter column fim_previsto drop not null;
alter table public.sessoes_teste add column if not exists tipo text not null default 'ensaio';
do $$ begin
  alter table public.sessoes_teste add constraint sessoes_teste_tipo_check check (tipo in ('ensaio','continua'));
exception when duplicate_object then null; end $$;

-- Dias da campanha: uma linha por virada (o registro da virada é a própria linha; nunca é reescrita).
create table if not exists public.sessao_dias (
  sessao_teste_id  text not null references public.sessoes_teste(id),
  dia              date not null,
  fuso             text not null,
  inicio_utc       timestamptz not null,
  registrado_em    timestamptz not null default now(),
  estado_na_virada jsonb not null default '{}'::jsonb,
  primary key (sessao_teste_id, dia)
);
alter table public.sessao_dias enable row level security;

-- início (UTC) do dia corrente da sessão no fuso dela; sessão de ensaio (sem fuso) = início da sessão
create or replace function public.sessao_dia_inicio(p_sessao text, p_em timestamptz default now())
returns timestamptz language sql stable security definer set search_path = public as $$
  select case when s.tipo = 'continua' and coalesce(s.config->>'fuso_diario', '') <> ''
              then (date_trunc('day', p_em at time zone (s.config->>'fuso_diario'))) at time zone (s.config->>'fuso_diario')
              else s.inicio end
    from public.sessoes_teste s where s.id = p_sessao
$$;

-- registra a virada do dia (idempotente). Devolve {novo, dia, inicio_utc, estado_na_virada}.
create or replace function public.sessao_virar_dia(p_sessao text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare s public.sessoes_teste%rowtype; v_fuso text; v_dia date; v_ini timestamptz; v_est jsonb; v_seq int := 0; r record; v_ok int;
begin
  select * into s from public.sessoes_teste where id = p_sessao;
  if not found or s.tipo <> 'continua' or s.estado <> 'ativa' then return jsonb_build_object('novo', false, 'motivo', 'sem campanha contínua ativa'); end if;
  v_fuso := coalesce(s.config->>'fuso_diario', 'UTC');
  v_dia := (now() at time zone v_fuso)::date;
  v_ini := public.sessao_dia_inicio(p_sessao);
  if exists (select 1 from public.sessao_dias where sessao_teste_id = p_sessao and dia = v_dia) then
    return jsonb_build_object('novo', false, 'dia', v_dia, 'inicio_utc', v_ini);
  end if;
  for r in select resultado_usd from public.sessao_aberturas where sessao_teste_id = p_sessao and estado = 'fechada'
            order by ts_fechamento desc nulls last, id desc loop
    exit when r.resultado_usd is null or r.resultado_usd >= 0;
    v_seq := v_seq + 1;
  end loop;
  select jsonb_build_object(
           'posicoes_e_reservas_abertas', count(*) filter (where estado in ('reservada','aberta')),
           'risco_aberto_usd', coalesce(sum(risco_planejado_usd) filter (where estado in ('reservada','aberta')), 0),
           'perdas_consecutivas', v_seq,
           'aberturas_suspensas', s.aberturas_suspensas_em is not null, 'motivo_suspensao', s.motivo_suspensao,
           'nota', 'contadores do dia zerados (aberturas e perda realizada); perdas consecutivas, posições e reservas abertas continuam valendo')
    into v_est from public.sessao_aberturas where sessao_teste_id = p_sessao;
  insert into public.sessao_dias (sessao_teste_id, dia, fuso, inicio_utc, estado_na_virada)
  values (p_sessao, v_dia, v_fuso, v_ini, v_est) on conflict do nothing;
  get diagnostics v_ok = row_count;
  return jsonb_build_object('novo', v_ok > 0, 'dia', v_dia, 'inicio_utc', v_ini, 'fuso', v_fuso, 'estado_na_virada', v_est);
end $$;

-- Limites conferidos e RESERVADOS na mesma transação (mesma assinatura da 0011).
-- Sessão de ensaio: comportamento idêntico ao da 0011. Campanha contínua: aberturas e perda realizada do DIA
-- (fuso da campanha); a perda do dia bloqueia só o dia; três perdas consecutivas suspendem até revisão.
create or replace function public.sessao_reservar(
  p_sessao text, p_bot bigint, p_reservar boolean, p_decisao_id text, p_uid text, p_card text, p_tf text,
  p_lado int, p_ts_barra timestamptz, p_lote numeric, p_preco_ref numeric, p_stop numeric, p_risco numeric,
  p_simbolo text, p_magic bigint, p_plano jsonb default '{}'::jsonb
) returns table (ok boolean, motivo text, abertura_id bigint, uso jsonb)
language plpgsql security definer set search_path = public as $$
declare
  s public.sessoes_teste%rowtype;
  c jsonb; v_n int; v_abertas int; v_risco numeric; v_perda numeric; v_seq int; v_pend int; v_id bigint; v_uso jsonb;
  v_mot text := null; r record; v_cont boolean; v_ini timestamptz; v_max_ab int; v_max_perda numeric;
begin
  perform pg_advisory_xact_lock(hashtext('sessao_teste:' || p_sessao));
  select * into s from public.sessoes_teste where id = p_sessao for update;
  if not found then return query select false, 'sessao_inexistente', null::bigint, null::jsonb; return; end if;
  c := s.config;
  v_cont := (s.tipo = 'continua');
  v_ini := case when v_cont then public.sessao_dia_inicio(p_sessao) else '-infinity'::timestamptz end;
  v_max_ab := coalesce((c->>'max_aberturas_por_dia')::int, (c->>'max_aberturas')::int);
  v_max_perda := coalesce((c->>'perda_realizada_max_usd_por_dia')::numeric, (c->>'perda_realizada_max_usd')::numeric);
  select count(*) filter (where estado in ('reservada','aberta','fechada') and ts_reserva >= v_ini),
         count(*) filter (where estado in ('reservada','aberta')),
         coalesce(sum(risco_planejado_usd) filter (where estado in ('reservada','aberta')), 0),
         coalesce(sum(resultado_usd) filter (where estado = 'fechada' and coalesce(ts_fechamento, ts_reserva) >= v_ini), 0),
         count(*) filter (where estado = 'fechada' and resultado_usd is null)
    into v_n, v_abertas, v_risco, v_perda, v_pend
    from public.sessao_aberturas where sessao_teste_id = p_sessao;
  v_seq := 0;
  for r in select resultado_usd from public.sessao_aberturas
            where sessao_teste_id = p_sessao and estado = 'fechada' order by ts_fechamento desc nulls last, id desc loop
    exit when r.resultado_usd is null or r.resultado_usd >= 0;
    v_seq := v_seq + 1;
  end loop;
  v_uso := jsonb_build_object('aberturas', v_n, 'aberturas_max', v_max_ab, 'escopo', case when v_cont then 'dia' else 'sessao' end,
                              'dia_inicio_utc', case when v_cont then v_ini end, 'fuso_diario', c->>'fuso_diario',
                              'posicoes_abertas', v_abertas, 'risco_aberto_usd', v_risco,
                              'resultado_realizado_usd', v_perda, 'perdas_consecutivas', v_seq, 'resultados_pendentes', v_pend);
  if s.estado <> 'ativa' or s.inicio is null then v_mot := 'sessao_nao_iniciada_ou_encerrada';
  elsif not s.aberturas_habilitadas then v_mot := 'aberturas_nao_habilitadas';
  elsif s.aberturas_suspensas_em is not null then v_mot := 'aberturas_suspensas(' || coalesce(s.motivo_suspensao, '?') || ')';
  elsif s.fim_previsto is not null and now() >= s.fim_previsto then v_mot := 'sessao_no_termino_previsto(novas_aberturas_suspensas)';
  elsif not (p_bot = any(s.bots)) then v_mot := 'bot_fora_da_sessao';
  elsif p_ts_barra < s.primeira_barra then v_mot := 'barra_anterior_ao_inicio_da_sessao';
  elsif p_lado not in (1, -1) or p_lote is null or p_lote <= 0 or p_stop is null or p_stop <= 0 then v_mot := 'plano_invalido';
  elsif p_risco is null or p_risco <= 0 then v_mot := 'risco_planejado_invalido';
  elsif p_risco > (c->>'risco_max_por_operacao_usd')::numeric + 0.005 then v_mot := 'risco_acima_do_limite_por_operacao';
  elsif v_pend > 0 then v_mot := 'resultado_de_fechamento_pendente(fail_closed)';
  elsif v_seq >= (c->>'max_perdas_consecutivas')::int then v_mot := 'tres_perdas_consecutivas';
  elsif v_perda <= -v_max_perda then v_mot := case when v_cont then 'perda_realizada_do_dia_no_limite' else 'perda_realizada_acumulada_no_limite' end;
  elsif v_n >= v_max_ab then v_mot := case when v_cont then 'maximo_de_aberturas_do_dia' else 'maximo_de_aberturas_da_sessao' end;
  elsif exists (select 1 from public.sessao_aberturas where sessao_teste_id = p_sessao and bot_id = p_bot and estado in ('reservada','aberta'))
     then v_mot := 'ativo_ja_tem_posicao_ou_reserva';
  elsif v_abertas >= (c->>'max_posicoes_simultaneas')::int then v_mot := 'maximo_de_posicoes_simultaneas';
  elsif v_risco + p_risco > (c->>'risco_agregado_max_usd')::numeric + 0.005 then v_mot := 'risco_agregado_acima_do_limite';
  end if;
  -- suspensão que exige revisão (não some com a virada do dia): três perdas; na sessão de ensaio também a perda acumulada
  if s.aberturas_suspensas_em is null and (v_mot = 'tres_perdas_consecutivas' or v_mot = 'perda_realizada_acumulada_no_limite') then
    update public.sessoes_teste set aberturas_suspensas_em = now(),
           motivo_suspensao = v_mot || case when v_cont then '(revisao_do_dono)' else '' end where id = p_sessao;
  end if;
  if v_mot is not null then return query select false, v_mot, null::bigint, v_uso; return; end if;
  if not p_reservar then return query select true, 'ok(conferido_sem_reservar)', null::bigint, v_uso; return; end if;
  insert into public.sessao_aberturas (sessao_teste_id, bot_id, simbolo, magic, decisao_id, candidato_uid, card, tf, lado, ts_barra,
                                       lote, preco_ref, stop_inicial, stop_atual, risco_planejado_usd, plano)
  values (p_sessao, p_bot, p_simbolo, p_magic, p_decisao_id, p_uid, p_card, p_tf, p_lado, p_ts_barra,
          p_lote, p_preco_ref, p_stop, p_stop, p_risco, coalesce(p_plano, '{}'::jsonb))
  returning id into v_id;
  return query select true, 'ok', v_id, v_uso;
end $$;
revoke all on function public.sessao_reservar(text,bigint,boolean,text,text,text,text,int,timestamptz,numeric,numeric,numeric,numeric,text,bigint,jsonb) from public, anon, authenticated;
grant execute on function public.sessao_reservar(text,bigint,boolean,text,text,text,text,int,timestamptz,numeric,numeric,numeric,numeric,text,bigint,jsonb) to service_role;

-- ACOMPANHAMENTO POR DIA (fuso da campanha), por bot: cobertura, operações reais, custos, drawdown realizado,
-- motivos de veto, observações sem execução e desempenho por estratégia × timeframe. Uma fonte para tela e JSON.
-- Barras esperadas: M15 fechadas no dia (a partir da 1ª barra da sessão e até agora), menos as janelas de mercado
-- fechado declaradas em config.horarios[<símbolo>] = [{"dias":[1..7 ISO], "de":"HH:MM", "ate":"HH:MM"}] no fuso da campanha.
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
revoke all on function public.sessao_virar_dia(text) from public, anon, authenticated;
grant execute on function public.sessao_virar_dia(text) to service_role;
revoke all on function public.sessao_dia_inicio(text, timestamptz) from public, anon, authenticated;
grant execute on function public.sessao_dia_inicio(text, timestamptz) to service_role;
