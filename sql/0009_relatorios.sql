-- 0009 (C27R21) — RELATÓRIO DA BABYMACHINE.
-- (1) relatorios_gerados: cada relatório gerado fica gravado (o PDF e o JSON baixados saem DESTE
--     registro, então têm o mesmo conteúdo e o mesmo identificador). Só o servidor lê e escreve.
-- (2) duas funções de LEITURA que agregam no banco o que seria pesado trazer barra a barra:
--     candidatos da seleção por escala/estado/portão e contagem da trilha por etapa/estado.
-- Nada aqui decide, veta ou executa. Idempotente. Sem BEGIN/COMMIT (o apply_migration já envolve).
create table if not exists public.relatorios_gerados (
  id         text primary key,
  user_id    uuid not null,
  bot_id     bigint not null references public.conector_bots(id) on delete cascade,
  criado_em  timestamptz not null default now(),
  periodo    jsonb not null,
  sha256     text not null,
  conteudo   jsonb not null
);
create index if not exists ix_relatorios_bot on public.relatorios_gerados (bot_id, criado_em desc);
alter table public.relatorios_gerados enable row level security;
alter table public.relatorios_gerados force row level security;
revoke all on public.relatorios_gerados from anon, authenticated;
grant all on public.relatorios_gerados to service_role;

create or replace function public.rel_selecao_agregado(p_bot bigint, p_de timestamptz, p_ate timestamptz)
returns jsonb language sql stable set search_path = public as $$
  with c as (
    select s.barra_m15, x.value as c
    from public.selecao_avaliacoes s,
         jsonb_each(s.avaliacao->'grupos') g,
         jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) x
    where s.bot_id = p_bot and s.barra_m15 > p_de and s.barra_m15 <= p_ate
  )
  select jsonb_build_object(
    'por_candidato', coalesce((select jsonb_agg(t) from (
        select c->>'timeframe' as tf, c->'estrategia'->>'card' as card, c->'estrategia'->>'nome' as nome,
               c->>'lado' as lado, c->>'elegibilidade' as estado, c->'sinal'->>'estado' as sinal,
               split_part(coalesce(c->>'primeiro_impedimento', ''), ' — ', 1) as primeiro_portao,
               count(*) as n, count(distinct c->>'uid') as sinais_distintos,
               min(barra_m15) as primeira_barra, max(barra_m15) as ultima_barra
        from c group by 1, 2, 3, 4, 5, 6, 7 order by 1, 2, 4, 5) t), '[]'::jsonb),
    'portoes_fechados', coalesce((select jsonb_agg(t) from (
        select c->>'timeframe' as tf, p->>'portao' as portao, p->>'origem' as origem,
               count(*) filter (where p->>'ok' = 'false') as fechado,
               count(*) filter (where p->>'ok' is null) as sem_dado,
               count(*) filter (where p->>'ok' = 'true') as aberto
        from c, jsonb_array_elements(coalesce(c->'portoes', '[]'::jsonb)) p
        group by 1, 2, 3 order by 1, 2) t), '[]'::jsonb),
    'atual_autorizaria', (select count(*) from c where c->'configuracao_atual'->>'autorizaria' = 'true'));
$$;

create or replace function public.rel_trilha_agregado(p_bot bigint, p_de timestamptz, p_ate timestamptz)
returns jsonb language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(t), '[]'::jsonb) from (
    select etapa, estado, count(*) as n, count(distinct barra_m15) as barras, max(ts) as ultimo
    from public.ciclo_trilha
    where bot_id = p_bot and barra_m15 > p_de and barra_m15 <= p_ate
    group by 1, 2 order by 1, 2) t;
$$;
revoke all on function public.rel_selecao_agregado(bigint, timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function public.rel_trilha_agregado(bigint, timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.rel_selecao_agregado(bigint, timestamptz, timestamptz) to service_role;
grant execute on function public.rel_trilha_agregado(bigint, timestamptz, timestamptz) to service_role;
