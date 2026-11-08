-- ORDEM 050 — Relatório geral de diagnóstico da Learning Machine (BabyMachine).
-- SÓ LEITURA dos registros que já existem + uma tabela própria para gravar o relatório gerado.
-- Não altera nenhuma tabela da campanha, nenhuma regra e nenhum bot.
--   lm_diagnosticos       : relatório gravado (o PDF e o JSON saem do MESMO registro: mesmo período, filtros e corte)
--   lm_diag_o50(...)      : agrega no banco, numa chamada, tudo o que o relatório usa no período [p_de, p_ate)
-- Reverter: sql/0026_lm_diagnostico_o50_reverter.sql

create table if not exists lm_diagnosticos (
    id          text primary key,
    user_id     uuid not null,
    criado_em   timestamptz not null default now(),
    periodo     jsonb not null,
    filtros     jsonb not null,
    corte_utc   timestamptz not null,
    sha256      text not null,
    conteudo    jsonb not null
);
create index if not exists lm_diagnosticos_user_idx on lm_diagnosticos (user_id, criado_em desc);
alter table lm_diagnosticos enable row level security;   -- só a API (service role) lê e grava

create or replace function lm_diag_o50(p_de timestamptz, p_ate timestamptz, p_bots bigint[], p_users text[] default null, p_gap_s integer default 120)
returns jsonb
language sql
stable
as $$
with
bots as (
    select b.id, b.nome, b.simbolo, b.user_id, b.bot_token, b.excluido, b.ultimo_ping, b.conector_parado_em, b.conector_visto_em,
           b.config_operacional->>'estrategia_nome' as estrategia_nome, b.config_operacional->>'timeframe_envio' as timeframe_envio
    from conector_bots b where b.id = any(p_bots)
),
snap as (
    select s.criado_em, b.id as bot_id
    from conector_snapshots s join bots b on b.bot_token = s.bot_token
    where s.criado_em >= p_de and s.criado_em < p_ate
),
snap_lag as (
    select bot_id, criado_em, criado_em - lag(criado_em) over (partition by bot_id order by criado_em) as d
    from snap
),
snap_barra as (
    select bot_id, date_bin('15 minutes', criado_em, timestamptz '2000-01-01 00:00+00') as barra, count(*) as n from snap group by 1, 2
),
lacunas as (
    select bot_id, criado_em - d as de, criado_em as ate, extract(epoch from d)::numeric(12,1) as s
    from snap_lag where d > make_interval(secs => p_gap_s)
),
coleta as (
    select b.id as bot_id,
           (select count(*) from snap x where x.bot_id = b.id) as n_snapshots,
           (select min(criado_em) from snap x where x.bot_id = b.id) as primeiro,
           (select max(criado_em) from snap x where x.bot_id = b.id) as ultimo,
           (select max(s.criado_em) from conector_snapshots s where s.bot_token = b.bot_token and s.criado_em < p_ate) as ultimo_antes_do_corte,
           (select count(*) from lacunas l where l.bot_id = b.id) as n_lacunas,
           (select coalesce(sum(s), 0) from lacunas l where l.bot_id = b.id) as lacunas_s_total,
           (select coalesce(jsonb_agg(jsonb_build_object('de', l.de, 'ate', l.ate, 's', l.s) order by l.s desc), '[]'::jsonb)
              from (select * from lacunas l where l.bot_id = b.id order by s desc limit 40) l) as lacunas
    from bots b
),
cand as (
    select c.bot_id, c.simbolo, c.tf, c.abertura_utc, c.fechamento_utc, c.o, c.h, c.l, c.c, c.fechado, c.primeiro_visto_utc
    from auditoria_candles c where c.bot_id = any(p_bots) and c.abertura_utc >= p_de and c.abertura_utc < p_ate
),
cand_tf as (
    select bot_id, simbolo, tf, count(*) as n, max(abertura_utc) as ultima_abertura,
           percentile_cont(0.5) within group (order by extract(epoch from (primeiro_visto_utc - fechamento_utc))) filter (where fechado and primeiro_visto_utc >= fechamento_utc) as atraso_p50_s,
           percentile_cont(0.95) within group (order by extract(epoch from (primeiro_visto_utc - fechamento_utc))) filter (where fechado and primeiro_visto_utc >= fechamento_utc) as atraso_p95_s
    from cand group by 1, 2, 3
),
cl as (
    select l.* from ciclo_leituras l where l.bot_id = any(p_bots) and l.barra_m15 >= p_de and l.barra_m15 < p_ate
),
barras as (      -- cada barra M15 fechada (candle gravado) × o que a LM fez nela
    select c.bot_id, c.abertura_utc as barra,
           l.decisao, l.regra, l.completa, l.falhas->>'motor_ult' as motor_ult,
           extract(epoch from (l.primeira_em - c.abertura_utc))::numeric(10,1) as atraso_primeira_leitura_s,
           coalesce(sb.n, 0) as snapshots
    from cand c left join cl l on l.bot_id = c.bot_id and l.barra_m15 = c.abertura_utc
         left join snap_barra sb on sb.bot_id = c.bot_id and sb.barra = c.abertura_utc
    where c.tf = 'M15' and c.fechado and c.fechamento_utc <= p_ate
),
leituras_sem_candle as (
    select l.bot_id, l.barra_m15, l.decisao, l.regra from cl l
    where not exists (select 1 from cand c where c.bot_id = l.bot_id and c.tf = 'M15' and c.abertura_utc = l.barra_m15 and c.fechado)
),
aud as (
    select a.bot_id, count(*) as n,
           count(*) filter (where jsonb_typeof(a.zonas) = 'object' and a.zonas <> '{}'::jsonb) as com_zonas,
           count(*) filter (where jsonb_typeof(a.estrutura_por_tf) = 'object' and a.estrutura_por_tf <> '{}'::jsonb) as com_estrutura_por_tf,
           count(*) filter (where a.regime is not null and jsonb_typeof(a.regime) <> 'null') as com_regime,
           count(*) filter (where jsonb_typeof(a.indicadores) = 'object' and a.indicadores <> '{}'::jsonb) as com_indicadores,
           count(*) filter (where a.offmind is not null and jsonb_typeof(a.offmind) <> 'null') as com_offmind,
           count(*) filter (where jsonb_typeof(a.candidatos) in ('array', 'object') and a.candidatos <> '[]'::jsonb and a.candidatos <> '{}'::jsonb) as com_candidatos,
           count(*) filter (where a.atestado is not null and jsonb_typeof(a.atestado) <> 'null') as com_atestado,
           count(*) filter (where a.gestao_assinada is not null and jsonb_typeof(a.gestao_assinada) <> 'null') as com_gestao_assinada,
           count(*) filter (where a.motor is not null and jsonb_typeof(a.motor) <> 'null') as com_motor
    from auditoria_leituras a where a.bot_id = any(p_bots) and a.ts >= p_de and a.ts < p_ate group by 1
),
cond as (
    select l.bot_id, tf, coalesce(l.leituras->'motor'->'por_tf'->tf->>'regime', '(não registrado)') as regime,
           coalesce(l.leituras->'motor'->'por_tf'->tf->>'estrutura', '(não registrado)') as estrutura,
           coalesce(l.leituras->'motor'->'por_tf'->tf->>'volatilidade', '(não registrado)') as volatilidade,
           count(*) as n
    from cl l cross join unnest(array['M15', 'H1', 'H4']) tf group by 1, 2, 3, 4, 5
),
sel as (
    select s.* from selecao_avaliacoes s where s.bot_id = any(p_bots) and s.criado_em >= p_de and s.criado_em < p_ate
),
escolhas as (
    select distinct on (s.bot_id, s.escolha_uid) s.bot_id, s.escolha_uid, s.barra_m15, s.criado_em, s.versao,
           s.avaliacao->'escolha'->>'card' as card, s.avaliacao->'escolha'->>'lado' as lado, (s.avaliacao->'escolha'->>'entrada')::numeric as entrada,
           (s.avaliacao->'escolha'->>'stop')::numeric as stop, s.avaliacao->'escolha'->>'timeframe' as timeframe, left(s.avaliacao->'escolha'->>'motivo', 160) as motivo,
           (s.avaliacao->'niveis_por_tf'->'por_tf'->'M15'->'suporte'->>'preco')::numeric as suporte_m15,
           (s.avaliacao->'niveis_por_tf'->'por_tf'->'M15'->'resistencia'->>'preco')::numeric as resistencia_m15
    from sel s where s.escolha_uid is not null order by s.bot_id, s.escolha_uid, s.criado_em
),
decs as (
    select d.id, d.bot_id, d.lado, d.ts_barra, d.status, d.ts_emissao, d.ts_consumo, d.veredito->>'contrato' as contrato,
           d.veredito->'candidato'->>'card' as card, d.veredito->'candidato'->>'uid' as candidato_uid, d.veredito->'candidato'->>'tf' as tf,
           (d.veredito->'candidato'->>'preco_ref')::numeric as preco_ref, (d.veredito->'candidato'->>'stop')::numeric as stop,
           (select coalesce(jsonb_agg(x->>'condicao'), '[]'::jsonb) from jsonb_array_elements(case when jsonb_typeof(d.veredito->'condicoes') = 'array' then d.veredito->'condicoes' else '[]'::jsonb end) x
             where (x->>'ok') = 'false') as condicoes_reprovadas
    from ciclo_decisoes d where d.bot_id = any(p_bots) and d.ts_emissao >= p_de and d.ts_emissao < p_ate
),
abs_ as (
    select a.id, a.sessao_teste_id, a.bot_id, a.simbolo, a.decisao_id, a.candidato_uid, a.card, a.tf, a.lado, a.ts_barra, a.lote, a.preco_ref,
           a.stop_inicial, a.stop_atual, a.risco_planejado_usd, a.estado, a.comando_id, a.ticket, a.preco_entrada, a.preco_saida,
           a.ts_reserva, a.ts_abertura, a.ts_fechamento, a.resultado_usd, a.comissao, a.swap, a.motivo_saida, a.motivo_cancelamento
    from sessao_aberturas a
    where a.bot_id = any(p_bots) and a.ts_reserva < p_ate
      and ((a.ts_reserva >= p_de) or (a.ts_fechamento >= p_de) or (a.ts_fechamento is null and a.estado <> 'cancelada'))
),
cmds as (
    select m.id, m.bot_id, m.tipo, m.status, m.origem, m.criado_em, m.entregue_em, m.confirmado_em, left(m.resultado::text, 100) as resultado
    from mt5_comandos m where m.bot_id = any(p_bots) and m.criado_em >= p_de and m.criado_em < p_ate
),
tri as (
    select t.bot_id, t.etapa, t.estado, t.motivo from ciclo_trilha t where t.bot_id = any(p_bots) and t.ts >= p_de and t.ts < p_ate
)
select jsonb_build_object(
  'funcao', 'lm_diag_o50', 'p_de', p_de, 'p_ate', p_ate, 'p_gap_s', p_gap_s, 'bots_pedidos', to_jsonb(p_bots),
  'bots', (select coalesce(jsonb_agg(to_jsonb(b) - 'bot_token' order by b.id), '[]'::jsonb) from bots b),
  'coleta', (select coalesce(jsonb_agg(to_jsonb(c) order by c.bot_id), '[]'::jsonb) from coleta c),
  'candles_por_tf', (select coalesce(jsonb_agg(to_jsonb(x) order by x.bot_id, x.tf), '[]'::jsonb) from cand_tf x),
  'barras_m15_colunas', jsonb_build_array('bot_id', 'barra_epoch_utc', 'decisao', 'regra', 'completa', 'motor_ult', 'atraso_primeira_leitura_s', 'snapshots_na_barra'),
  'barras_m15', (select coalesce(jsonb_agg(jsonb_build_array(bot_id, extract(epoch from barra)::bigint, decisao, regra, completa, motor_ult, atraso_primeira_leitura_s, snapshots)
                                           order by bot_id, barra), '[]'::jsonb) from barras),
  'leituras_sem_candle_m15', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from leituras_sem_candle x),
  'leituras_por_regra', (select coalesce(jsonb_agg(to_jsonb(x) order by x.bot_id, x.n desc), '[]'::jsonb)
                           from (select bot_id, decisao, regra, count(*) as n, count(*) filter (where completa) as completas, min(left(motivo, 260)) as exemplo_motivo,
                                        count(*) filter (where motivo is null or motivo = '') as sem_motivo from cl group by 1, 2, 3) x),
  'versoes', jsonb_build_object(
       'ciclo_leituras', (select coalesce(jsonb_agg(to_jsonb(x) order by x.n desc), '[]'::jsonb) from (select bot_id, versoes, count(*) as n, min(barra_m15) as de, max(barra_m15) as ate from cl group by 1, 2) x),
       'leitor_motor', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from (select bot_id, leituras->'motor'->>'leitor' as leitor, leituras->>'eav' as ea, count(*) as n from cl group by 1, 2, 3) x),
       'selecao', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from (select bot_id, versao, count(*) as n from sel group by 1, 2) x)),
  'referencias', (select coalesce(jsonb_agg(to_jsonb(a) order by a.bot_id), '[]'::jsonb) from aud a),
  'condicoes', (select coalesce(jsonb_agg(to_jsonb(c)), '[]'::jsonb) from cond c),
  'selecao', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from (select bot_id, count(*) as n, coalesce(sum(n_candidatos), 0) as candidatos, coalesce(sum(n_elegiveis), 0) as elegiveis,
                                                                          count(*) filter (where escolha_uid is not null) as com_escolha, count(distinct escolha_uid) as escolhas_distintas from sel group by 1) x),
  'escolhas', (select coalesce(jsonb_agg(to_jsonb(e) order by e.criado_em), '[]'::jsonb) from escolhas e),
  'decisoes', (select coalesce(jsonb_agg(to_jsonb(d) order by d.ts_emissao), '[]'::jsonb) from decs d),
  'aberturas', (select coalesce(jsonb_agg(to_jsonb(a) order by a.ts_reserva), '[]'::jsonb) from abs_ a),
  'comandos', (select coalesce(jsonb_agg(to_jsonb(m) order by m.criado_em), '[]'::jsonb) from cmds m),
  'trilha_contagem', (select coalesce(jsonb_agg(to_jsonb(x) order by x.bot_id, x.n desc), '[]'::jsonb) from (select bot_id, etapa, estado, count(*) as n from tri group by 1, 2, 3) x),
  'trilha_motivos', (select coalesce(jsonb_agg(to_jsonb(x) order by x.etapa, x.n desc), '[]'::jsonb)
                       from (select etapa, estado, left(motivo, 160) as motivo, count(*) as n,
                                    row_number() over (partition by etapa, estado order by count(*) desc) as rk
                               from tri where etapa in ('gestao', 'veto', 'limites', 'autoridade_r01v5', 'falha_coleta', 'divergencia', 'persistencia', 'atestado', 'mercado', 'snapshot', 'motor', 'fechamento', 'abertura')
                              group by 1, 2, 3) x where x.rk <= 5),
  'sombra_e_origem', jsonb_build_object(
       'lateral_eventos', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from (select tipo, count(*) as n from lateral_eventos e where e.recebido_em >= p_de and e.recebido_em < p_ate and (p_users is null or e.user_id = any(p_users)) group by 1) x),
       'lateral_bots', (select count(*) from lateral_bots e where (p_users is null or e.user_id = any(p_users))),
       'lm_eventos', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from (select tipo, modulo, classe, count(*) as n from lm_eventos e where e.recebido_em >= p_de and e.recebido_em < p_ate and (p_users is null or e.user_id = any(p_users)) group by 1, 2, 3) x),
       'babymachine_operacoes', (select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) from (select fonte, status, count(*) as n from babymachine_operacoes o where o.bot_id = any(p_bots) and o.ts_criada >= p_de and o.ts_criada < p_ate group by 1, 2) x)),
  'candles_m15_colunas', jsonb_build_array('bot_id', 'abertura_epoch_utc', 'o', 'h', 'l', 'c'),
  'candles_m15_grafico', (select coalesce(jsonb_agg(jsonb_build_array(c.bot_id, extract(epoch from c.abertura_utc)::bigint, c.o, c.h, c.l, c.c) order by c.bot_id, c.abertura_utc), '[]'::jsonb)
                            from auditoria_candles c where c.bot_id = any(p_bots) and c.tf = 'M15' and c.fechado and c.abertura_utc >= p_de - interval '25 hours' and c.fechamento_utc <= p_ate)
);
$$;

comment on function lm_diag_o50(timestamptz, timestamptz, bigint[], text[], integer) is 'ORDEM 050 — diagnóstico geral da LM: só leitura; agrega no banco o período [p_de, p_ate)';
