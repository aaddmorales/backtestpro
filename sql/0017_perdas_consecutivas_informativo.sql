-- 0017 (C27R42) — ORDEM DO DONO (12/10/2026 18:51 Kyiv): na campanha DEMO CAMP-20261008-856229fe, as perdas consecutivas
-- passam a ser INFORMAÇÃO (continuam contadas e expostas em 'uso'), sem suspender novas aberturas. Mecanismo: chave de
-- config POR CAMPANHA 'perdas_consecutivas_bloqueia' (ausente = true = comportamento da 0012; false = não bloqueia).
-- Nada mais muda: os demais limites (teto por operação, perda do dia, aberturas do dia, posições simultâneas, risco
-- agregado, fail-closed de resultado pendente), a suspensão por perda acumulada da sessão de ensaio e a gestão continuam.
-- A alteração vive em sessoes_teste.config (persiste em reinicializações) e só vale para a sessão que tiver a chave.
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
                              'resultado_realizado_usd', v_perda, 'perdas_consecutivas', v_seq, 'resultados_pendentes', v_pend,
                              'perdas_consecutivas_bloqueia', coalesce((c->>'perdas_consecutivas_bloqueia')::boolean, true));
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
  elsif coalesce((c->>'perdas_consecutivas_bloqueia')::boolean, true) and v_seq >= (c->>'max_perdas_consecutivas')::int then v_mot := 'tres_perdas_consecutivas';
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
