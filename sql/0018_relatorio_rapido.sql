-- 0018 (C27R46) — RELATÓRIO RÁPIDO: o trabalho pesado sobre selecao_avaliacoes (≈55 KB por barra) e auditoria_leituras
-- passa a ser feito NO BANCO, devolvendo só o que o relatório usa. Antes a API baixava o JSON inteiro de cada barra
-- (32 MB para a campanha) e demorava 200–300 s; o navegador desistia aos 300 s (BT-R02).
-- Só LEITURA. Nada aqui decide, veta ou executa. Idempotente. Sem BEGIN/COMMIT (o apply_migration já envolve).

-- 1) oportunidades e recusas por barra, compacto (campos usados pelo relatório; portões completos com regra e valores)
create or replace function public.rel_oportunidades(p_bot bigint, p_de timestamptz, p_ate timestamptz)
returns jsonb language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'id', s.id, 'barra_m15', s.barra_m15, 'versao', s.avaliacao->>'versao', 'preco', s.avaliacao->>'preco_ea',
      'n_candidatos', s.n_candidatos, 'n_elegiveis', s.n_elegiveis, 'escolha_uid', s.escolha_uid,
      'a5', jsonb_build_object('motivo', s.avaliacao->'autoridade_r01v5'->>'motivo',
                               'sessao_motivo', s.avaliacao->'autoridade_r01v5'->'sessao'->>'motivo',
                               'decisao_emitida', s.avaliacao->'autoridade_r01v5'->>'decisao_emitida',
                               'seria_emitida', s.avaliacao->'autoridade_r01v5'->>'seria_emitida'),
      'cont', case when s.avaliacao ? 'continuidade' then jsonb_build_object(
                 'compra', s.avaliacao->'continuidade'->'compra'->>'situacao',
                 'venda', s.avaliacao->'continuidade'->'venda'->>'situacao',
                 'propagacao_compra', s.avaliacao->'continuidade'->'compra'->'propagacao'->>'inicio_observado',
                 'propagacao_venda', s.avaliacao->'continuidade'->'venda'->'propagacao'->>'inicio_observado') else null end,
      'candidatos', (select coalesce(jsonb_agg(jsonb_build_object(
           'uid', c->>'uid', 'timeframe', g.key, 'lado', c->>'lado',
           'card', coalesce(c->'estrategia'->>'card', split_part(c->>'uid', '|', 1)), 'nome', c->'estrategia'->>'nome',
           'estado', c->'sinal'->>'estado', 'formacao_utc', c->'sinal'->>'barra_do_sinal_utc',
           'confirmado_utc', c->'frescor'->>'confirmado_utc', 'vence_utc', c->'frescor'->>'vence_utc',
           'idade_s', c->'frescor'->>'idade_s', 'frescor', c->'frescor'->>'situacao',
           'entrada', c->'niveis'->>'entrada', 'stop', c->'niveis'->>'stop', 'risco_pts', c->'niveis'->>'risco_pts',
           'elegibilidade', c->>'elegibilidade', 'escolhido', c->'escolha'->>'escolhido', 'primeiro_impedimento', c->>'primeiro_impedimento',
           'pf', c->'pontuacao'->>'pf', 'trades', c->'pontuacao'->>'trades', 'pf_metade_min', c->'pontuacao'->>'pf_metade_min',
           'selo', c->'estudo'->>'selo_da_lista', 'selo_fragil', c->'estudo'->>'selo_fragil',
           'portoes', (select coalesce(jsonb_agg(jsonb_build_object('portao', q->>'portao', 'ok', q->'ok', 'detalhe', q->>'detalhe', 'proposto', q->'proposto')
                                                 order by q->>'portao'), '[]'::jsonb)
                       from jsonb_array_elements(coalesce(c->'portoes', '[]'::jsonb)) q),
           'corta_agora', c->'corte'->>'corta_agora', 'corte_origem', c->'corte'->'origem', 'execucao', c->'execucao')),
         '[]'::jsonb)
         from jsonb_each(coalesce(s.avaliacao->'grupos', '{}'::jsonb)) g,
              jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) c)
    ) order by s.barra_m15), '[]'::jsonb)
  from public.selecao_avaliacoes s
  where s.bot_id = p_bot and s.barra_m15 > p_de and s.barra_m15 <= p_ate;
$$;

-- 2) diagnóstico do seletor: estratégia × TF × lado em toda a campanha (avaliações, sinais distintos, elegíveis, escolhidas,
--    primeiro portão fechado, selo/PF/trades) — antes a API baixava todas as avaliações da campanha
create or replace function public.rel_selecao_celulas(p_bot bigint, p_sessao text)
returns jsonb language sql stable set search_path = public as $$
  with c as (
    select s.escolha_uid, g.key as tf, x as c
    from public.selecao_avaliacoes s,
         jsonb_each(coalesce(s.avaliacao->'grupos', '{}'::jsonb)) g,
         jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) x
    where s.bot_id = p_bot and s.sessao_teste_id = p_sessao),
  base as (
    select split_part(c->>'uid', '|', 1) as card, tf, c->>'lado' as lado, c->>'uid' as uid,
           c->>'primeiro_impedimento' as pi, (c->>'uid' = escolha_uid) as esc,
           c->'estrategia'->>'nome' as nome, c->'estudo' as est
    from c),
  pi_counts as (
    select card, tf, lado, coalesce(split_part(pi, ' — ', 1), 'elegível') as k, count(*) as n
    from base group by 1, 2, 3, 4),
  pi_json as (select card, tf, lado, jsonb_object_agg(k, n) as portoes from pi_counts group by 1, 2, 3)
  select coalesce(jsonb_agg(t order by t.elegiveis desc, t.avaliacoes desc), '[]'::jsonb) from (
    select b.card, b.tf as timeframe, b.lado, max(b.nome) as nome,
           count(*) as avaliacoes, count(distinct b.uid) as sinais,
           count(*) filter (where b.pi is null) as elegiveis, count(*) filter (where b.esc) as escolhidas,
           (select p.portoes from pi_json p where p.card = b.card and p.tf = b.tf and p.lado = b.lado) as portoes,
           bool_or((b.est->>'selo_da_lista')::boolean) as selo,
           max((b.est->>'profit_factor')::double precision) as profit_factor,
           max((b.est->>'trades')::int) as trades
    from base b group by b.card, b.tf, b.lado) t;
$$;

-- 3) evidências de execução real da sel-4 (portão 8 proporcional ao risco; portão 4 fino informa / indeterminado veta)
create or replace function public.rel_sel4_evidencias(p_bots bigint[], p_sessao text)
returns jsonb language sql stable set search_path = public as $$
  with c as (
    select s.id, s.bot_id, s.barra_m15, x as c
    from public.selecao_avaliacoes s,
         jsonb_each(coalesce(s.avaliacao->'grupos', '{}'::jsonb)) g,
         jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) x
    where s.bot_id = any(p_bots) and s.sessao_teste_id = p_sessao and s.avaliacao->>'versao' = 'sel-4'),
  p as (
    select id, bot_id, barra_m15, c->>'uid' as uid, q->>'portao' as portao, q->>'ok' as ok, q->>'detalhe' as det
    from c, jsonb_array_elements(coalesce(c->'portoes', '[]'::jsonb)) q),
  g8 as (select * from p where portao like '8.%' and ok = 'true' and (substring(det from 'preço a (\d+) pts'))::int > 30),
  g4f as (select * from p where portao like '4.%' and det like '%FINO%'),
  g4i as (select * from p where portao like '4.%' and det like '%INDETERMINADO%')
  select jsonb_build_object(
    'n_avaliacoes_sel4', (select count(*) from public.selecao_avaliacoes where bot_id = any(p_bots) and sessao_teste_id = p_sessao and avaliacao->>'versao' = 'sel-4'),
    'g8_ok_acima30_total', (select count(*) from g8),
    'g8_ok_acima30', (select coalesce(jsonb_agg(jsonb_build_object('avaliacao_id', id, 'barra', barra_m15, 'bot', bot_id, 'uid', uid, 'detalhe', det)), '[]'::jsonb)
                      from (select * from g8 order by id desc limit 5) z),
    'g4_fino_total', (select count(*) from g4f),
    'g4_fino', (select coalesce(jsonb_agg(jsonb_build_object('avaliacao_id', id, 'barra', barra_m15, 'bot', bot_id, 'uid', uid)), '[]'::jsonb)
                from (select * from g4f order by id desc limit 5) z),
    'g4_indeterminado_total', (select count(*) from g4i),
    'g4_indeterminado', (select coalesce(jsonb_agg(jsonb_build_object('avaliacao_id', id, 'barra', barra_m15, 'bot', bot_id, 'uid', uid)), '[]'::jsonb)
                         from (select * from g4i order by id desc limit 5) z));
$$;

-- 4) sequência intrabar (mudanças de estado motor/regime por barra) — antes a API baixava todas as leituras vivas do período
create or replace function public.rel_cronologia_intrabar(p_bot bigint, p_de timestamptz, p_ate timestamptz)
returns jsonb language sql stable set search_path = public as $$
  with l as (
    select ts, barra_m15_utc, motor->>'estado' as me, regime->>'estado' as re
    from public.auditoria_leituras
    where bot_id = p_bot and ts >= p_de and ts <= p_ate),
  w as (
    select *, lag(me) over (partition by barra_m15_utc order by ts) as pme,
              lag(re) over (partition by barra_m15_utc order by ts) as pre,
              row_number() over (partition by barra_m15_utc order by ts) as rn
    from l)
  select jsonb_build_object(
    'leituras', (select count(*) from l),
    'por_barra', (select coalesce(jsonb_object_agg(k, seq), '{}'::jsonb) from (
        select barra_m15_utc::text as k,
               jsonb_agg(jsonb_build_object('ts', ts, 'motor', me, 'regime', re) order by ts) as seq
        from w where rn = 1 or pme is distinct from me or pre is distinct from re
        group by 1) z));
$$;

-- 5) origens do corte gravadas na gestão assinada (para conferir a truncagem do conector)
create or replace function public.rel_corte_origens(p_bots bigint[], p_desde timestamptz, p_limite int)
returns jsonb language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(t), '[]'::jsonb) from (
    select a.id as leitura_id, a.bot_id as bot, a.ts, a.atestado->>'versao_ponte_conector' as ponte, l.key as lado, o as origem
    from public.auditoria_leituras a,
         jsonb_each(coalesce(a.gestao_assinada->'lados', '{}'::jsonb)) l,
         jsonb_array_elements(coalesce(l.value->'corte_origem', '[]'::jsonb)) o
    where a.bot_id = any(p_bots) and a.ts >= p_desde and a.gestao_assinada is not null
    order by a.id desc limit greatest(1, least(p_limite, 500))) t;
$$;

revoke all on function public.rel_oportunidades(bigint, timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function public.rel_selecao_celulas(bigint, text) from public, anon, authenticated;
revoke all on function public.rel_sel4_evidencias(bigint[], text) from public, anon, authenticated;
revoke all on function public.rel_cronologia_intrabar(bigint, timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function public.rel_corte_origens(bigint[], timestamptz, int) from public, anon, authenticated;
grant execute on function public.rel_oportunidades(bigint, timestamptz, timestamptz) to service_role;
grant execute on function public.rel_selecao_celulas(bigint, text) to service_role;
grant execute on function public.rel_sel4_evidencias(bigint[], text) to service_role;
grant execute on function public.rel_cronologia_intrabar(bigint, timestamptz, timestamptz) to service_role;
grant execute on function public.rel_corte_origens(bigint[], timestamptz, int) to service_role;
