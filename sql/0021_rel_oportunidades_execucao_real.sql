-- 0021 (C27R51) — rel_oportunidades devolve também 'execucao_real' da r01v5 (ex.: "nenhuma: bloqueio_do_bot(...)"): é o que explica
-- um escolhido com 'todas as condições atendidas' + 'sessão ok' que mesmo assim não virou decisão (gate bloqueio_do_bot antes da reserva).
-- Só LEITURA. Idempotente. Mesma assinatura (create or replace).
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
                               'seria_emitida', s.avaliacao->'autoridade_r01v5'->>'seria_emitida',
                               'execucao_real', s.avaliacao->'autoridade_r01v5'->>'execucao_real'),
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
