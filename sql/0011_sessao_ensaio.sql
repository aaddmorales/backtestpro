-- 0011 — C27R24 · SESSÃO DE ENSAIO (auditoria) + limites compartilhados + livro de aberturas
-- SOMENTE homologação. Nada é apagado: os registros anteriores ficam sem carimbo ("histórico anterior").
-- O carimbo é posto pelo BANCO (gatilho BEFORE INSERT), não pela tela: reiniciar a API, o conector ou
-- recarregar a página não zera nem duplica — o recorte é uma coluna gravada na própria linha.

create table if not exists public.sessoes_teste (
  id                    text primary key,
  nome                  text not null,
  user_id               uuid,
  bots                  bigint[] not null,
  estado                text not null default 'preparada' check (estado in ('preparada','ativa','encerrada')),
  padrao                boolean not null default true,          -- a BabyMachine abre nela por padrão
  criada_em             timestamptz not null default now(),
  inicio                timestamptz,                             -- instante em que a sessão foi iniciada
  primeira_barra        timestamptz,                             -- 1ª barra M15 (abertura UTC) que pertence à sessão
  fim_previsto          timestamptz not null,
  fim                   timestamptz,
  aberturas_habilitadas boolean not null default false,
  aberturas_habilitadas_em timestamptz,
  aberturas_suspensas_em timestamptz,
  motivo_suspensao      text,
  config                jsonb not null,
  preservacao           jsonb not null default '{}'::jsonb     -- contagem do histórico no momento da criação
);
alter table public.sessoes_teste enable row level security;

-- carimbos (linhas antigas ficam NULL = histórico anterior)
do $$
declare t text;
begin
  foreach t in array array['ciclo_leituras','ciclo_trilha','selecao_avaliacoes','ciclo_decisoes','mt5_comandos','babymachine_operacoes'] loop
    execute format('alter table public.%I add column if not exists sessao_teste_id text', t);
    execute format('alter table public.%I add column if not exists sessao_atraso_de text', t);
    execute format('create index if not exists ix_%s_sessao on public.%I (sessao_teste_id) where sessao_teste_id is not null', t, t);
  end loop;
end $$;
alter table public.relatorios_gerados add column if not exists sessao_teste_id text;

-- Gatilho: TG_ARGV[0] = coluna com a barra de referência ('' = registro sem barra: vale o instante da gravação).
--   barra >= primeira_barra da sessão .......... registro DO ENSAIO (sessao_teste_id)
--   barra <  barra em curso no início .......... registro ANTERIOR RECEBIDO COM ATRASO (sessao_atraso_de)
--   barra em curso no início ................... anterior ao início (sem carimbo)
create or replace function public.sessao_carimbar() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  s public.sessoes_teste%rowtype;
  v_ref timestamptz;
  v_txt text;
begin
  new.sessao_teste_id := null; new.sessao_atraso_de := null;      -- o carimbo nunca vem de fora
  if new.bot_id is null then return new; end if;
  select * into s from public.sessoes_teste x
   where x.estado = 'ativa' and x.inicio is not null and x.inicio <= now() and new.bot_id = any(x.bots)
   order by x.inicio desc limit 1;
  if not found then return new; end if;
  if coalesce(TG_ARGV[0], '') <> '' then
    v_txt := to_jsonb(new)->>TG_ARGV[0];
    if v_txt is not null then v_ref := v_txt::timestamptz; end if;
  end if;
  if v_ref is null then
    new.sessao_teste_id := s.id;
  elsif v_ref >= s.primeira_barra then
    new.sessao_teste_id := s.id;
  elsif v_ref < s.primeira_barra - interval '15 minutes' then
    new.sessao_atraso_de := s.id;
  end if;
  return new;
end $$;

drop trigger if exists tg_sessao_leituras on public.ciclo_leituras;
create trigger tg_sessao_leituras before insert on public.ciclo_leituras for each row execute function public.sessao_carimbar('barra_m15');
drop trigger if exists tg_sessao_trilha on public.ciclo_trilha;
create trigger tg_sessao_trilha before insert on public.ciclo_trilha for each row execute function public.sessao_carimbar('barra_m15');
drop trigger if exists tg_sessao_selecao on public.selecao_avaliacoes;
create trigger tg_sessao_selecao before insert on public.selecao_avaliacoes for each row execute function public.sessao_carimbar('barra_m15');
drop trigger if exists tg_sessao_decisoes on public.ciclo_decisoes;
create trigger tg_sessao_decisoes before insert on public.ciclo_decisoes for each row execute function public.sessao_carimbar('ts_barra');
drop trigger if exists tg_sessao_comandos on public.mt5_comandos;
create trigger tg_sessao_comandos before insert on public.mt5_comandos for each row execute function public.sessao_carimbar('');
drop trigger if exists tg_sessao_operacoes on public.babymachine_operacoes;
create trigger tg_sessao_operacoes before insert on public.babymachine_operacoes for each row execute function public.sessao_carimbar('');

-- o carimbo não muda depois de gravado
create or replace function public.sessao_carimbo_fixo() returns trigger
language plpgsql set search_path = public as $$
begin
  new.sessao_teste_id := old.sessao_teste_id; new.sessao_atraso_de := old.sessao_atraso_de;
  return new;
end $$;
do $$
declare t text;
begin
  foreach t in array array['ciclo_leituras','ciclo_trilha','selecao_avaliacoes','ciclo_decisoes','mt5_comandos','babymachine_operacoes'] loop
    execute format('drop trigger if exists tg_sessao_fixo on public.%I', t);
    execute format('create trigger tg_sessao_fixo before update on public.%I for each row execute function public.sessao_carimbo_fixo()', t);
  end loop;
end $$;

-- LIVRO DE ABERTURAS da sessão: uma linha por reserva de risco. É a fonte dos limites e dos resultados.
create table if not exists public.sessao_aberturas (
  id               bigserial primary key,
  sessao_teste_id  text not null references public.sessoes_teste(id),
  bot_id           bigint not null,
  simbolo          text not null,
  magic            bigint,
  decisao_id       text not null,
  candidato_uid    text not null,
  card             text, tf text, lado smallint not null,
  ts_barra         timestamptz not null,
  lote             numeric not null,
  preco_ref        numeric, stop_inicial numeric not null, stop_atual numeric,
  risco_planejado_usd numeric not null,
  plano            jsonb not null default '{}'::jsonb,
  estado           text not null default 'reservada' check (estado in ('reservada','aberta','fechada','cancelada')),
  comando_id       bigint, ticket bigint, posicao_id bigint,
  preco_entrada    numeric, preco_saida numeric,
  ts_reserva       timestamptz not null default now(),
  ts_abertura      timestamptz, ts_fechamento timestamptz,
  resultado_usd    numeric, lucro numeric, comissao numeric, swap numeric,
  motivo_saida     text, motivo_cancelamento text,
  gestao           jsonb not null default '[]'::jsonb,
  unique (sessao_teste_id, decisao_id)
);
alter table public.sessao_aberturas enable row level security;
create index if not exists ix_sessao_aberturas on public.sessao_aberturas (sessao_teste_id, bot_id, estado);

-- comando de GESTÃO da sessão: no máximo um por (posição, barra, tipo), mesmo com reinício da API
create unique index if not exists uq_mt5_cmd_gestao on public.mt5_comandos ((params->>'uid_gestao')) where params ? 'uid_gestao';

-- Limites compartilhados, conferidos e RESERVADOS na mesma transação (trava por sessão).
-- p_reservar=false só confere (nada é gravado). Cancelada não consome orçamento nem conta como abertura.
create or replace function public.sessao_reservar(
  p_sessao text, p_bot bigint, p_reservar boolean, p_decisao_id text, p_uid text, p_card text, p_tf text,
  p_lado int, p_ts_barra timestamptz, p_lote numeric, p_preco_ref numeric, p_stop numeric, p_risco numeric,
  p_simbolo text, p_magic bigint, p_plano jsonb default '{}'::jsonb
) returns table (ok boolean, motivo text, abertura_id bigint, uso jsonb)
language plpgsql security definer set search_path = public as $$
declare
  s public.sessoes_teste%rowtype;
  c jsonb; v_n int; v_abertas int; v_risco numeric; v_perda numeric; v_seq int; v_pend int; v_id bigint; v_uso jsonb;
  v_mot text := null; r record;
begin
  perform pg_advisory_xact_lock(hashtext('sessao_teste:' || p_sessao));
  select * into s from public.sessoes_teste where id = p_sessao for update;
  if not found then return query select false, 'sessao_inexistente', null::bigint, null::jsonb; return; end if;
  c := s.config;
  select count(*) filter (where estado in ('reservada','aberta','fechada')),
         count(*) filter (where estado in ('reservada','aberta')),
         coalesce(sum(risco_planejado_usd) filter (where estado in ('reservada','aberta')), 0),
         coalesce(sum(resultado_usd) filter (where estado = 'fechada'), 0),
         count(*) filter (where estado = 'fechada' and resultado_usd is null)
    into v_n, v_abertas, v_risco, v_perda, v_pend
    from public.sessao_aberturas where sessao_teste_id = p_sessao;
  v_seq := 0;
  for r in select resultado_usd from public.sessao_aberturas
            where sessao_teste_id = p_sessao and estado = 'fechada' order by ts_fechamento desc nulls last, id desc loop
    exit when r.resultado_usd is null or r.resultado_usd >= 0;
    v_seq := v_seq + 1;
  end loop;
  v_uso := jsonb_build_object('aberturas', v_n, 'posicoes_abertas', v_abertas, 'risco_aberto_usd', v_risco,
                              'resultado_realizado_usd', v_perda, 'perdas_consecutivas', v_seq, 'resultados_pendentes', v_pend);
  if s.estado <> 'ativa' or s.inicio is null then v_mot := 'sessao_nao_iniciada_ou_encerrada';
  elsif not s.aberturas_habilitadas then v_mot := 'aberturas_nao_habilitadas';
  elsif s.aberturas_suspensas_em is not null then v_mot := 'aberturas_suspensas(' || coalesce(s.motivo_suspensao, '?') || ')';
  elsif now() >= s.fim_previsto then v_mot := 'sessao_no_termino_previsto(novas_aberturas_suspensas)';
  elsif not (p_bot = any(s.bots)) then v_mot := 'bot_fora_da_sessao';
  elsif p_ts_barra < s.primeira_barra then v_mot := 'barra_anterior_ao_inicio_da_sessao';
  elsif p_lado not in (1, -1) or p_lote is null or p_lote <= 0 or p_stop is null or p_stop <= 0 then v_mot := 'plano_invalido';
  elsif p_risco is null or p_risco <= 0 then v_mot := 'risco_planejado_invalido';
  elsif p_risco > (c->>'risco_max_por_operacao_usd')::numeric + 0.005 then v_mot := 'risco_acima_do_limite_por_operacao';
  elsif v_pend > 0 then v_mot := 'resultado_de_fechamento_pendente(fail_closed)';
  elsif v_seq >= (c->>'max_perdas_consecutivas')::int then v_mot := 'tres_perdas_consecutivas';
  elsif v_perda <= -((c->>'perda_realizada_max_usd')::numeric) then v_mot := 'perda_realizada_acumulada_no_limite';
  elsif v_n >= (c->>'max_aberturas')::int then v_mot := 'maximo_de_aberturas_da_sessao';
  elsif exists (select 1 from public.sessao_aberturas where sessao_teste_id = p_sessao and bot_id = p_bot and estado in ('reservada','aberta'))
     then v_mot := 'ativo_ja_tem_posicao_ou_reserva';
  elsif v_abertas >= (c->>'max_posicoes_simultaneas')::int then v_mot := 'maximo_de_posicoes_simultaneas';
  elsif v_risco + p_risco > (c->>'risco_agregado_max_usd')::numeric + 0.005 then v_mot := 'risco_agregado_acima_do_limite';
  end if;
  if v_mot in ('tres_perdas_consecutivas', 'perda_realizada_acumulada_no_limite') and s.aberturas_suspensas_em is null then
    update public.sessoes_teste set aberturas_suspensas_em = now(), motivo_suspensao = v_mot where id = p_sessao;
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

-- Contadores por bot. p_sessao = id → registros da sessão; '' → histórico anterior (sem carimbo) dos bots dados.
-- É a MESMA função para a tela, o JSON e o PDF.
create or replace function public.sessao_contadores(p_sessao text, p_bots bigint[])
returns jsonb language sql stable security definer set search_path = public as $$
  with b as (select unnest(p_bots) as bot_id),
  f as (select coalesce(p_sessao, '') as s)
  select coalesce(jsonb_object_agg(b.bot_id::text, jsonb_build_object(
    'barras', (select count(*) from ciclo_leituras x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'snapshots', (select coalesce(sum(n_snapshots), 0) from ciclo_leituras x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'leituras_completas', (select count(*) from ciclo_leituras x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s and x.completa),
    'primeira_barra', (select min(barra_m15) from ciclo_leituras x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'ultima_barra', (select max(barra_m15) from ciclo_leituras x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'avaliacoes_de_selecao', (select count(*) from selecao_avaliacoes x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'candidatos', (select coalesce(sum(n_candidatos), 0) from selecao_avaliacoes x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'elegiveis', (select coalesce(sum(n_elegiveis), 0) from selecao_avaliacoes x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'vetos', (select count(*) from ciclo_trilha x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s and x.etapa = 'veto'),
    'eventos_da_trilha', (select count(*) from ciclo_trilha x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'trilha_por_etapa', (select coalesce(jsonb_object_agg(k, n), '{}'::jsonb) from (
        select x.etapa || ':' || x.estado as k, count(*) as n from ciclo_trilha x, f
         where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s group by 1) t),
    'decisoes', (select count(*) from ciclo_decisoes x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'comandos', (select count(*) from mt5_comandos x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'comandos_de_abertura', (select count(*) from mt5_comandos x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s and x.tipo in ('buy','sell')),
    'comandos_de_gestao', (select count(*) from mt5_comandos x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s and x.tipo not in ('buy','sell')),
    'comandos_executados', (select count(*) from mt5_comandos x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s and x.status = 'executado'),
    'operacoes_babymachine', (select count(*) from babymachine_operacoes x, f where x.bot_id = b.bot_id and coalesce(x.sessao_teste_id, '') = f.s),
    'aberturas', (select count(*) from sessao_aberturas x, f where x.bot_id = b.bot_id and x.sessao_teste_id = f.s and x.estado in ('aberta','fechada')),
    'reservas_em_curso', (select count(*) from sessao_aberturas x, f where x.bot_id = b.bot_id and x.sessao_teste_id = f.s and x.estado = 'reservada'),
    'reservas_canceladas', (select count(*) from sessao_aberturas x, f where x.bot_id = b.bot_id and x.sessao_teste_id = f.s and x.estado = 'cancelada'),
    'posicoes_abertas', (select count(*) from sessao_aberturas x, f where x.bot_id = b.bot_id and x.sessao_teste_id = f.s and x.estado = 'aberta'),
    'fechamentos', (select count(*) from sessao_aberturas x, f where x.bot_id = b.bot_id and x.sessao_teste_id = f.s and x.estado = 'fechada'),
    'resultado_usd', (select sum(resultado_usd) from sessao_aberturas x, f where x.bot_id = b.bot_id and x.sessao_teste_id = f.s and x.estado = 'fechada'),
    'atrasados', case when p_sessao is null or p_sessao = '' then null else jsonb_build_object(
        'leituras', (select count(*) from ciclo_leituras x where x.bot_id = b.bot_id and x.sessao_atraso_de = p_sessao),
        'trilha', (select count(*) from ciclo_trilha x where x.bot_id = b.bot_id and x.sessao_atraso_de = p_sessao),
        'selecao', (select count(*) from selecao_avaliacoes x where x.bot_id = b.bot_id and x.sessao_atraso_de = p_sessao),
        'decisoes', (select count(*) from ciclo_decisoes x where x.bot_id = b.bot_id and x.sessao_atraso_de = p_sessao)) end
  )), '{}'::jsonb) from b;
$$;
revoke all on function public.sessao_contadores(text, bigint[]) from public, anon, authenticated;
grant execute on function public.sessao_contadores(text, bigint[]) to service_role;

-- agregados do relatório com recorte de sessão ('*' = tudo, '' = histórico anterior, id = sessão)
create or replace function public.rel_selecao_agregado(p_bot bigint, p_de timestamptz, p_ate timestamptz, p_sessao text)
returns jsonb language sql stable set search_path = public as $$
  with c as (
    select s.barra_m15, x.value as c
    from public.selecao_avaliacoes s,
         jsonb_each(s.avaliacao->'grupos') g,
         jsonb_array_elements(coalesce(g.value->'candidatos', '[]'::jsonb)) x
    where s.bot_id = p_bot and s.barra_m15 > p_de and s.barra_m15 <= p_ate
      and (p_sessao = '*' or coalesce(s.sessao_teste_id, '') = p_sessao)
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
create or replace function public.rel_trilha_agregado(p_bot bigint, p_de timestamptz, p_ate timestamptz, p_sessao text)
returns jsonb language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(t), '[]'::jsonb) from (
    select etapa, estado, count(*) as n, count(distinct barra_m15) as barras, max(ts) as ultimo
    from public.ciclo_trilha
    where bot_id = p_bot and barra_m15 > p_de and barra_m15 <= p_ate
      and (p_sessao = '*' or coalesce(sessao_teste_id, '') = p_sessao)
    group by 1, 2 order by 1, 2) t;
$$;
revoke all on function public.rel_selecao_agregado(bigint, timestamptz, timestamptz, text) from public, anon, authenticated;
revoke all on function public.rel_trilha_agregado(bigint, timestamptz, timestamptz, text) from public, anon, authenticated;
grant execute on function public.rel_selecao_agregado(bigint, timestamptz, timestamptz, text) to service_role;
grant execute on function public.rel_trilha_agregado(bigint, timestamptz, timestamptz, text) to service_role;

-- etapas novas da trilha: sessão, limites, gestão
alter table public.ciclo_trilha drop constraint if exists ciclo_trilha_etapa_check;
alter table public.ciclo_trilha add constraint ciclo_trilha_etapa_check check (etapa in (
  'snapshot','leituras','ciclos','motor','decisao','veto','persistencia','rpc','comando',
  'resposta_mt5','abertura','fechamento','divergencia','falha_coleta','atestado','selecao','autoridade_r01v5',
  'sessao','limites','gestao','mercado'));

-- Início da sessão: instante comum + 1ª barra M15 que pertence a ela (a próxima a abrir). Aberturas seguem DESLIGADAS.
create or replace function public.sessao_iniciar(p_sessao text) returns public.sessoes_teste
language plpgsql security definer set search_path = public as $$
declare s public.sessoes_teste%rowtype; v_agora timestamptz := now();
begin
  update public.sessoes_teste
     set estado = 'ativa', inicio = v_agora,
         primeira_barra = to_timestamp(ceil(extract(epoch from v_agora) / 900.0) * 900)
   where id = p_sessao and estado = 'preparada' and inicio is null
  returning * into s;
  if not found then raise exception 'sessao_inexistente_ou_ja_iniciada'; end if;
  return s;
end $$;
revoke all on function public.sessao_iniciar(text) from public, anon, authenticated;
grant execute on function public.sessao_iniciar(text) to service_role;

-- Detalhe por timeframe (mesma fonte para tela, JSON e PDF): leituras e mudanças de direção por tempo
-- (EA e motor), escolhas da seleção, sombra/autoridade r01v5 e decisões, por timeframe do candidato.
create or replace function public.sessao_detalhe(p_sessao text, p_bot bigint)
returns jsonb language sql stable security definer set search_path = public as $$
  with lr as (select x.barra_m15, x.leituras_ult from ciclo_leituras x
               where x.bot_id = p_bot and coalesce(x.sessao_teste_id, '') = coalesce(p_sessao, '')),
  ea as (select lr.barra_m15, e->>'tf' as tf, e->>'direcao' as d, e->>'estado_dado' as ed
           from lr, jsonb_array_elements(coalesce(lr.leituras_ult->'linhas', '[]'::jsonb)) e),
  ea2 as (select *, lag(d) over (partition by tf order by barra_m15) as ant from ea),
  mo as (select lr.barra_m15, k.key as tf, k.value as d
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
               'ultima_mudanca', max(barra_m15) filter (where ant is not null and ant is distinct from d)) as j
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

-- acesso só do servidor (service_role); nada para anon/authenticated
grant select, insert, update on public.sessoes_teste, public.sessao_aberturas to service_role;
grant usage, select on sequence public.sessao_aberturas_id_seq to service_role;
revoke all on public.sessoes_teste, public.sessao_aberturas from anon, authenticated;
