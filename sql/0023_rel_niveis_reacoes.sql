-- 0023 (C27R55) — rel_niveis_reacoes: por barra M15 avaliada, só o necessário para confrontar a leitura com o gráfico — níveis por TF
-- (leitor 1.9), estrutura gravada (localização, eventos, último topo/fundo), movimento em formação, candidatos com estado/nível/elegibilidade
-- e os portões fechados, escolha e autoridade. Só LEITURA. Idempotente.
create or replace function public.rel_niveis_reacoes(p_bot bigint, p_de timestamptz, p_ate timestamptz)
returns jsonb language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'id', s.id, 'barra_m15', s.barra_m15, 'versao', s.avaliacao->>'versao', 'preco', s.avaliacao->>'preco_ea',
      'escolha_uid', s.escolha_uid, 'n_candidatos', s.n_candidatos, 'n_elegiveis', s.n_elegiveis,
      'mov', jsonb_build_object('rotulo', s.avaliacao->'movimento_em_formacao'->>'rotulo'),
      'est', s.avaliacao->'continuidade'->'estrutura_por_tf',
      'niv', case when jsonb_typeof(s.avaliacao->'niveis_por_tf') = 'object' then s.avaliacao->'niveis_por_tf' else null end,
      'a5', jsonb_build_object('motivo', s.avaliacao->'autoridade_r01v5'->>'motivo', 'execucao_real', s.avaliacao->'autoridade_r01v5'->>'execucao_real',
                               'decisao_emitida', s.avaliacao->'autoridade_r01v5'->>'decisao_emitida'),
      'contagem', s.avaliacao->'resumo'->'confirmacao'->'contagem',
      'candidatos', (select coalesce(jsonb_agg(jsonb_build_object(
           'uid', c->>'uid', 'timeframe', g.key, 'lado', c->>'lado',
           'card', coalesce(c->'estrategia'->>'card', split_part(c->>'uid', '|', 1)),
           'estado', c->'sinal'->>'estado', 'nivel', c->'sinal'->>'nivel', 'barra_do_sinal_utc', c->'sinal'->>'barra_do_sinal_utc',
           'confirmado_utc', c->'frescor'->>'confirmado_utc', 'elegibilidade', c->>'elegibilidade',
           'escolhido', c->'escolha'->>'escolhido', 'primeiro_impedimento', c->>'primeiro_impedimento',
           'falhas', (select coalesce(jsonb_agg((q->>'portao') || ': ' || left(coalesce(q->>'detalhe', ''), 220) order by nullif(regexp_replace(split_part(q->>'portao', '.', 1), '\D', '', 'g'), '')::int), '[]'::jsonb)
                      from jsonb_array_elements(coalesce(c->'portoes', '[]'::jsonb)) q where q->'ok' = 'false'::jsonb))), '[]'::jsonb)
         from jsonb_each(coalesce(s.avaliacao->'grupos', '{}'::jsonb)) g,
              jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) c)
    ) order by s.barra_m15), '[]'::jsonb)
  from public.selecao_avaliacoes s
  where s.bot_id = p_bot and s.barra_m15 > p_de and s.barra_m15 <= p_ate;
$$;
revoke all on function public.rel_niveis_reacoes(bigint, timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.rel_niveis_reacoes(bigint, timestamptz, timestamptz) to service_role;
notify pgrst, 'reload schema';
