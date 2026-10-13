-- 0019 (C27R47) — rel_oportunidades passa a devolver também o que a sel-5 grava: células "sem sinal" por barra (critério, valores,
-- motivo), o movimento em formação, e por candidato a compatibilidade com o movimento, as latências (detecção → execução) e a
-- quantidade de reavaliações dentro da barra. Só LEITURA. Idempotente. Mesma assinatura do 0018 (create or replace).
create or replace function public.rel_oportunidades(p_bot bigint, p_de timestamptz, p_ate timestamptz)
returns jsonb language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'id', s.id, 'barra_m15', s.barra_m15, 'versao', s.avaliacao->>'versao', 'preco', s.avaliacao->>'preco_ea',
      'n_candidatos', s.n_candidatos, 'n_elegiveis', s.n_elegiveis, 'escolha_uid', s.escolha_uid,
      'avaliado_utc', s.avaliacao->>'avaliado_utc',
      'reavaliacoes_feitas', s.avaliacao->'controle'->>'reavaliacoes_feitas',
      'primeira_avaliacao_utc', s.avaliacao->'primeira_avaliacao'->>'avaliado_utc',
      'movimento', s.avaliacao->'movimento_em_formacao',
      'a5', jsonb_build_object('motivo', s.avaliacao->'autoridade_r01v5'->>'motivo',
                               'sessao_motivo', s.avaliacao->'autoridade_r01v5'->'sessao'->>'motivo',
                               'decisao_emitida', s.avaliacao->'autoridade_r01v5'->>'decisao_emitida',
                               'seria_emitida', s.avaliacao->'autoridade_r01v5'->>'seria_emitida'),
      'cont', case when s.avaliacao ? 'continuidade' then jsonb_build_object(
                 'compra', s.avaliacao->'continuidade'->'compra'->>'situacao',
                 'venda', s.avaliacao->'continuidade'->'venda'->>'situacao',
                 'propagacao_compra', s.avaliacao->'continuidade'->'compra'->'propagacao'->>'inicio_observado',
                 'propagacao_venda', s.avaliacao->'continuidade'->'venda'->'propagacao'->>'inicio_observado') else null end,
      'sem_sinal', (select coalesce(jsonb_agg(jsonb_build_object('timeframe', g.key, 'card', z->>'card', 'nome', z->>'nome', 'familia', z->>'familia',
                                                                   'criterio', z->>'criterio', 'resultado', z->>'resultado', 'valores', z->'valores', 'motivo', z->>'motivo')), '[]'::jsonb)
                    from jsonb_each(coalesce(s.avaliacao->'grupos', '{}'::jsonb)) g,
                         jsonb_array_elements(coalesce(g.value->'sem_sinal', '[]'::jsonb)) z),
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
           'compatibilidade', c->'compatibilidade', 'latencias', c->'latencias',
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

-- evidências da sel-5 (selo informativo exercitado; sem_sinal gravado; reavaliações dentro da barra; proteção por tempo e reversão confirmada na gestão)
create or replace function public.rel_sel5_evidencias(p_bots bigint[], p_sessao text)
returns jsonb language sql stable set search_path = public as $$
  with s5 as (
    select s.id, s.bot_id, s.barra_m15, s.escolha_uid, s.avaliacao as a
    from public.selecao_avaliacoes s where s.bot_id = any(p_bots) and s.sessao_teste_id = p_sessao and s.avaliacao->>'versao' = 'sel-5'),
  c as (
    select s5.id, s5.bot_id, s5.barra_m15, x as c from s5, jsonb_each(coalesce(s5.a->'grupos', '{}'::jsonb)) g, jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) x),
  selo_nao as (
    select id, bot_id, barra_m15, c->>'uid' as uid, c->>'elegibilidade' as eleg from c
    where (c->'estudo'->>'selo_da_lista') is distinct from 'true'),
  g3 as (
    select ab.id as abertura_id, ab.bot_id, g from public.sessao_aberturas ab, jsonb_array_elements(coalesce(ab.gestao, '[]'::jsonb)) g
    where ab.bot_id = any(p_bots) and ab.sessao_teste_id = p_sessao and g->'regras'->>'contrato_gestao' = 'gestao-3')
  select jsonb_build_object(
    'n_avaliacoes_sel5', (select count(*) from s5),
    'reavaliacoes_total', (select coalesce(sum((a->'controle'->>'reavaliacoes_feitas')::int), 0) from s5),
    'barras_com_reavaliacao', (select count(*) from s5 where coalesce((a->'controle'->>'reavaliacoes_feitas')::int, 0) > 0),
    'sem_sinal_linhas', (select coalesce(sum(jsonb_array_length(coalesce(g.value->'sem_sinal', '[]'::jsonb))), 0) from s5, jsonb_each(coalesce(s5.a->'grupos', '{}'::jsonb)) g),
    'candidatos_sem_selo_total', (select count(*) from selo_nao),
    'candidatos_sem_selo_elegiveis', (select count(*) from selo_nao where eleg = 'elegivel'),
    'candidatos_sem_selo_escolhidos', (select count(*) from selo_nao n join s5 on s5.id = n.id where s5.escolha_uid = n.uid),
    'sem_selo_elegiveis_amostra', (select coalesce(jsonb_agg(jsonb_build_object('avaliacao_id', id, 'barra', barra_m15, 'bot', bot_id, 'uid', uid)), '[]'::jsonb)
                                   from (select * from selo_nao where eleg = 'elegivel' order by id desc limit 5) z),
    'gestao3_avaliacoes', (select count(*) from g3),
    'protecao_por_tempo_acionada', (select count(*) from g3 where (g->'protecao_por_tempo'->>'acionada') = 'true'),
    'protecao_por_tempo_pedida', (select count(*) from g3 where (g->'protecao_por_tempo'->>'pedido') = 'true'),
    'protecao_por_tempo_impedida', (select count(*) from g3 where (g->'protecao_por_tempo'->>'aplicada') = 'false'),
    'protecao_amostra', (select coalesce(jsonb_agg(jsonb_build_object('abertura_id', abertura_id, 'bot', bot_id, 'barra', g->>'barra', 'candles', g->'protecao_por_tempo'->>'candles_fechados',
                                                                      'nivel', g->'protecao_por_tempo'->>'nivel', 'aplicada', g->'protecao_por_tempo'->>'aplicada', 'impedimento', g->'protecao_por_tempo'->>'impedimento', 'comando_id', g->>'comando_id')), '[]'::jsonb)
                         from (select * from g3 where (g->'protecao_por_tempo'->>'acionada') = 'true' order by g->>'barra' desc limit 8) z),
    'reversao_confirmada_fechou', (select count(*) from g3 where g->>'acao' = 'close' and (g->'corte_classificacao'->>'reversao_confirmada') = 'true'),
    'alerta_exaustao_isolado', (select count(*) from g3 where (g->'corte_classificacao'->>'alerta_exaustao_isolado') = 'true'),
    'rotulo_estrutura_defasado', (select count(*) from g3 where (g->'continuidade'->'M15'->>'rotulo_da_estrutura_defasado') = 'true'));
$$;

revoke all on function public.rel_sel5_evidencias(bigint[], text) from public, anon, authenticated;
grant execute on function public.rel_sel5_evidencias(bigint[], text) to service_role;
