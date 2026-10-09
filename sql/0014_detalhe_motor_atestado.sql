-- 0014 (C27R31) — sessao_detalhe: leituras do motor por timeframe contadas pelo ATESTADO assinado de cada barra (antes: mapa
-- 'dirs' do último snapshot, vazio no fim da barra → 45 onde havia 85). Só a função; nada é apagado. A contagem antiga fica
-- em 'leituras_dirs_ultimo_snapshot'.
-- Detalhe por timeframe (mesma fonte para tela, JSON e PDF): leituras e mudanças de direção por tempo
-- (EA e motor), escolhas da seleção, sombra/autoridade r01v5 e decisões, por timeframe do candidato.
create or replace function public.sessao_detalhe(p_sessao text, p_bot bigint)
returns jsonb language sql stable security definer set search_path = public as $$
  with lr as (select x.barra_m15, x.leituras_ult from ciclo_leituras x
               where x.bot_id = p_bot and coalesce(x.sessao_teste_id, '') = coalesce(p_sessao, '')),
  ea as (select lr.barra_m15, e->>'tf' as tf, e->>'direcao' as d, e->>'estado_dado' as ed
           from lr, jsonb_array_elements(coalesce(lr.leituras_ult->'linhas', '[]'::jsonb)) e),
  ea2 as (select *, lag(d) over (partition by tf order by barra_m15) as ant from ea),
  -- C27R31: a leitura do motor por barra é o ATESTADO assinado (cv1.janela M1/M5/M15 + cv2.dirs D1/H4), presente em toda
  -- barra verificada. O mapa 'dirs' do último snapshot fica vazio quando a leitura publicada já está 'antiga' no fim da
  -- barra — por isso contava 45 onde havia 85 atestados. O número antigo segue à parte (leituras_dirs_ultimo_snapshot).
  lra as (select x.barra_m15, x.leituras_ult, x.ciclos from ciclo_leituras x
           where x.bot_id = p_bot and coalesce(x.sessao_teste_id, '') = coalesce(p_sessao, '')),
  mo as (select barra_m15, tf, d from (
           select lra.barra_m15, k.key as tf, k.value as d
             from lra, jsonb_each_text(coalesce(lra.ciclos->'atestado'->'cv1'->'janela', '{}'::jsonb) || coalesce(lra.ciclos->'atestado'->'cv2'->'dirs', '{}'::jsonb)) k
            where lra.ciclos->'atestado' is not null
           union all
           select lra.barra_m15, k.key as tf, k.value as d
             from lra, jsonb_each_text(coalesce(lra.leituras_ult->'motor'->'dirs', '{}'::jsonb)) k
            where lra.ciclos->'atestado' is null) q),
  mod as (select lr.barra_m15, k.key as tf, k.value as d
            from lr, jsonb_each_text(coalesce(lr.leituras_ult->'motor'->'dirs', '{}'::jsonb)) k),
  mo2 as (select *, lag(d) over (partition by tf order by barra_m15) as ant from mo),
  se as (select s.barra_m15, s.escolha_uid, s.avaliacao->'escolha'->>'timeframe' as tf,
                s.avaliacao->'autoridade_r01v5' as a
           from selecao_avaliacoes s where s.bot_id = p_bot and coalesce(s.sessao_teste_id, '') = coalesce(p_sessao, ''))
  select jsonb_build_object(
    'leituras_ea_por_tf', coalesce((select jsonb_object_agg(tf, j) from (
        select tf, jsonb_build_object('leituras', count(*),
               'mudancas_de_direcao', count(*) filter (where ant is not null and ant is distinct from d),
               'alta', count(*) filter (where d = 'alta'), 'baixa', count(*) filter (where d = 'baixa'),
               'lateral', count(*) filter (where d = 'lateral'),
               'dado_nao_atual', count(*) filter (where ed is distinct from 'atual'),
               'direcao_na_ultima_barra', (array_agg(d order by barra_m15 desc))[1],
               'ultima_mudanca', max(barra_m15) filter (where ant is not null and ant is distinct from d)) as j
          from ea2 group by tf) t), '{}'::jsonb),
    'leituras_motor_por_tf', coalesce((select jsonb_object_agg(tf, j) from (
        select tf, jsonb_build_object('leituras', count(*),
               'mudancas_de_direcao', count(*) filter (where ant is not null and ant is distinct from d),
               'alta', count(*) filter (where d = '1'), 'baixa', count(*) filter (where d = '-1'),
               'lateral', count(*) filter (where d = '0'),
               'direcao_na_ultima_barra', (array_agg(d order by barra_m15 desc))[1],
               'ultima_mudanca', max(barra_m15) filter (where ant is not null and ant is distinct from d),
               'fonte', 'atestado assinado por barra (cv1.janela + cv2.dirs)',
               'leituras_dirs_ultimo_snapshot', (select count(*) from mod where mod.tf = mo2.tf)) as j
          from mo2 group by tf) t), '{}'::jsonb),
    'selecao_por_tf', coalesce((select jsonb_object_agg(coalesce(tf, 'sem escolha'), j) from (
        select tf, jsonb_build_object('barras', count(*),
               'sombra_seria_emitida', count(*) filter (where a->>'seria_emitida' = 'true'),
               'decisao_emitida', count(*) filter (where a->>'decisao_emitida' = 'true'),
               'comando_criado', count(*) filter (where a->>'comando_criado' = 'true')) as j
          from se group by tf) t), '{}'::jsonb),
    'motivos_da_autoridade', coalesce((select jsonb_agg(t) from (
        select coalesce(tf, 'sem escolha') as tf,
               split_part(coalesce(a->>'motivo', '?'), ' — ', 1) as motivo,
               coalesce(a->'sessao'->>'motivo', '') as limite, count(*) as n
          from se group by 1, 2, 3 order by 4 desc limit 40) t), '[]'::jsonb),
    'decisoes_por_tf', coalesce((select jsonb_object_agg(tf, n) from (
        select coalesce(d.veredito->'candidato'->>'tf', 'r01v4') as tf, count(*) as n from ciclo_decisoes d
         where d.bot_id = p_bot and coalesce(d.sessao_teste_id, '') = coalesce(p_sessao, '') group by 1) t), '{}'::jsonb));
$$;
revoke all on function public.sessao_detalhe(text, bigint) from public, anon, authenticated;
grant execute on function public.sessao_detalhe(text, bigint) to service_role;
notify pgrst, 'reload schema';
