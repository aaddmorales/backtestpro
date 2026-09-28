-- 0001_homolog_estrutura_producao.sql  (C27R11 · 28/set/2026)
-- ESCOPO: SOMENTE Supabase de HOMOLOGACAO (hvraqquuvybzpqwkqlcu). NUNCA producao.
-- ORIGEM: ESTRUTURA lida do catalogo da producao (hdnhyceyzljommcvkejq) em 28/set,
-- SO LEITURA (pg_attribute/pg_constraint/pg_indexes/pg_policies/pg_proc), ZERO dados.
-- Recria: 17 tabelas public com colunas/tipos/defaults/identity, PK/UNIQUE/CHECK/FK,
-- indices, RLS + policies, 3 funcoes e o trigger de perfil. Coluna "Adriano"
-- (smallint, sem uso no codigo) reproduzida como esta na producao.
-- Sentinela _bt_homolog_marker: prova que o banco e o isolado (producao nao tem).
BEGIN;
CREATE TABLE public._bt_homolog_marker (id int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  ambiente text NOT NULL DEFAULT 'homolog-supabase', criado_em timestamptz NOT NULL DEFAULT now());
INSERT INTO public._bt_homolog_marker(id) VALUES (1);
ALTER TABLE public._bt_homolog_marker ENABLE ROW LEVEL SECURITY;

CREATE TABLE public.perfis (
  id uuid NOT NULL, email text NOT NULL, nome text, plano text DEFAULT 'free'::text,
  backtests_mes integer DEFAULT 0, backtests_limite integer DEFAULT 5,
  stripe_customer_id text, stripe_subscription_id text, plano_ativo_ate timestamptz,
  criado_em timestamptz DEFAULT now(), atualizado_em timestamptz DEFAULT now(),
  "Adriano" smallint, plano_valido_ate timestamptz,
  CONSTRAINT perfis_pkey PRIMARY KEY (id),
  CONSTRAINT perfis_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE,
  CONSTRAINT perfis_plano_check CHECK ((plano = ANY (ARRAY['free'::text, 'pro'::text, 'trader_pro'::text]))));

CREATE TABLE public.agente_eventos (
  id bigint GENERATED ALWAYS AS IDENTITY, user_id uuid, tipo text NOT NULL, regra text,
  detalhe_json jsonb, criado_em timestamptz DEFAULT now(),
  CONSTRAINT agente_eventos_pkey PRIMARY KEY (id),
  CONSTRAINT agente_eventos_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id));

CREATE TABLE public.agente_sugestoes (
  id bigint GENERATED ALWAYS AS IDENTITY, user_id uuid, regra text NOT NULL, categoria text,
  mensagem text NOT NULL, severidade text DEFAULT 'info'::text, contexto_json jsonb,
  lida boolean DEFAULT false, criado_em timestamptz DEFAULT now(),
  CONSTRAINT agente_sugestoes_pkey PRIMARY KEY (id),
  CONSTRAINT agente_sugestoes_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id));

CREATE SEQUENCE public.babymachine_operacoes_id_seq AS bigint;
CREATE TABLE public.babymachine_operacoes (
  id bigint NOT NULL DEFAULT nextval('babymachine_operacoes_id_seq'::regclass),
  user_id uuid NOT NULL, bot_id bigint NOT NULL, bot_nome text, ativo text, timeframe text,
  fonte text NOT NULL, status text NOT NULL DEFAULT 'pendente'::text, oportunidade_id text,
  comando_id bigint, ticket_mt5 bigint, evento_id_abriu bigint, evento_id_fechou bigint,
  contexto_entrada jsonb, decisao jsonb, resultado jsonb,
  ts_criada timestamptz NOT NULL DEFAULT now(), ts_entrada timestamptz, ts_saida timestamptz,
  atualizada_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT babymachine_operacoes_pkey PRIMARY KEY (id));
ALTER SEQUENCE public.babymachine_operacoes_id_seq OWNED BY public.babymachine_operacoes.id;

CREATE TABLE public.backtests_historico (
  id uuid NOT NULL DEFAULT gen_random_uuid(), user_id uuid, criado_em timestamptz NOT NULL DEFAULT now(),
  ativo text, timeframe text, periodo text, estrategia_nome text, codigo_hash text, parametros jsonb,
  retorno numeric, win_rate numeric, sharpe numeric, max_drawdown numeric, profit_factor numeric,
  total_trades integer, sessao_id uuid, permite_treino boolean NOT NULL DEFAULT true,
  CONSTRAINT backtests_historico_pkey PRIMARY KEY (id),
  CONSTRAINT backtests_historico_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE);

CREATE TABLE public.calendario_economico (
  id bigint GENERATED ALWAYS AS IDENTITY, titulo text NOT NULL, moeda text NOT NULL, impacto text NOT NULL,
  data_evento timestamptz NOT NULL, forecast text, previous text, actual text,
  fonte text DEFAULT 'forexfactory'::text, atualizado_em timestamptz DEFAULT now(),
  CONSTRAINT calendario_economico_pkey PRIMARY KEY (id),
  CONSTRAINT calendario_economico_moeda_data_evento_titulo_key UNIQUE (moeda, data_evento, titulo));

CREATE TABLE public.codigos_acesso (
  codigo text NOT NULL, plano text NOT NULL DEFAULT 'trader_pro'::text, dias integer NOT NULL DEFAULT 30,
  usado boolean NOT NULL DEFAULT false, usado_por uuid, usado_em timestamptz,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT codigos_acesso_pkey PRIMARY KEY (codigo));

CREATE TABLE public.conector_bots (
  id bigint GENERATED ALWAYS AS IDENTITY, user_id uuid NOT NULL, bot_token text NOT NULL,
  nome text DEFAULT 'Meu Bot'::text, simbolo text, magic_number bigint, ultimo_ping timestamptz,
  ultimo_equity numeric, ultimo_dd numeric, ultima_direcao text, ultimo_padrao text,
  posicoes_abertas integer DEFAULT 0, criado_em timestamptz DEFAULT now(), excluido boolean DEFAULT false,
  mq5_codigo text, mq5_filename text, subir_pedido_em timestamptz, conector_parado_em timestamptz,
  conector_visto_em timestamptz, config_operacional jsonb,
  CONSTRAINT conector_bots_pkey PRIMARY KEY (id),
  CONSTRAINT conector_bots_bot_token_key UNIQUE (bot_token),
  CONSTRAINT conector_bots_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id));

CREATE TABLE public.conector_snapshots (
  id bigint GENERATED ALWAYS AS IDENTITY, user_id uuid, bot_token text NOT NULL, conta_login text,
  corretora text, simbolo text, magic_number bigint, equity numeric, balance numeric, margem_livre numeric,
  posicoes_abertas integer DEFAULT 0, lucro_flutuante numeric, drawdown_atual numeric, direcao_d1 text,
  padrao_ativo text, detalhe_json jsonb, criado_em timestamptz DEFAULT now(),
  CONSTRAINT conector_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT conector_snapshots_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id));

CREATE TABLE public.estudo_biblioteca (
  id uuid NOT NULL DEFAULT gen_random_uuid(), ativo text NOT NULL, periodo text NOT NULL, timeframe text NOT NULL,
  estrategia_id text NOT NULL, estrategia_nome text NOT NULL, retorno double precision, profit_factor double precision,
  win_rate double precision, sharpe double precision, trades integer, forca text,
  medido_em timestamptz NOT NULL DEFAULT now(), parametros jsonb, codigo_hash text, regras_versao text,
  captura_pct numeric, janela text,
  CONSTRAINT estudo_biblioteca_pkey PRIMARY KEY (id),
  CONSTRAINT estudo_biblioteca_uniq UNIQUE (ativo, periodo, timeframe, estrategia_id));

CREATE SEQUENCE public.estudo_biblioteca_v2_id_seq AS bigint;
CREATE TABLE public.estudo_biblioteca_v2 (
  id bigint NOT NULL DEFAULT nextval('estudo_biblioteca_v2_id_seq'::regclass), ativo text NOT NULL,
  periodo text NOT NULL, timeframe text NOT NULL, estrategia_id text NOT NULL, estrategia_nome text,
  retorno double precision, profit_factor double precision, win_rate double precision, sharpe double precision,
  trades integer, dd double precision, wf_a_pf double precision, wf_b_pf double precision,
  captura_pct double precision, carimbo jsonb DEFAULT '{}'::jsonb, origem jsonb DEFAULT '{}'::jsonb,
  medido_em timestamptz DEFAULT now(),
  CONSTRAINT estudo_biblioteca_v2_pkey PRIMARY KEY (id),
  CONSTRAINT estudo_biblioteca_v2_ativo_periodo_timeframe_estrategia_id_key UNIQUE (ativo, periodo, timeframe, estrategia_id));
ALTER SEQUENCE public.estudo_biblioteca_v2_id_seq OWNED BY public.estudo_biblioteca_v2.id;

CREATE TABLE public.mq5_cache (
  gen_hash text NOT NULL, mq5 text NOT NULL, aprovado boolean DEFAULT false,
  criado_em timestamptz DEFAULT now(), atualizado_em timestamptz DEFAULT now(),
  CONSTRAINT mq5_cache_pkey PRIMARY KEY (gen_hash));

CREATE SEQUENCE public.mt5_comandos_id_seq AS bigint;
CREATE TABLE public.mt5_comandos (
  id bigint NOT NULL DEFAULT nextval('mt5_comandos_id_seq'::regclass), bot_token text NOT NULL,
  user_id uuid NOT NULL, bot_id bigint, tipo text NOT NULL, params jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pendente'::text, origem text NOT NULL DEFAULT 'manual'::text,
  criado_em timestamptz NOT NULL DEFAULT now(), entregue_em timestamptz, confirmado_em timestamptz,
  expira_em timestamptz NOT NULL DEFAULT (now() + '00:01:00'::interval), resultado jsonb,
  CONSTRAINT mt5_comandos_pkey PRIMARY KEY (id));
ALTER SEQUENCE public.mt5_comandos_id_seq OWNED BY public.mt5_comandos.id;

CREATE TABLE public.mt5_jobs (
  job_id text NOT NULL, bot_token text NOT NULL, filename text NOT NULL DEFAULT ''::text,
  magic bigint NOT NULL DEFAULT 0, mq5 text NOT NULL DEFAULT ''::text, status text NOT NULL DEFAULT 'validando'::text,
  aprovado boolean, log text NOT NULL DEFAULT ''::text, gen_hash text NOT NULL DEFAULT ''::text,
  pre_validado boolean NOT NULL DEFAULT false, criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT mt5_jobs_pkey PRIMARY KEY (job_id));

CREATE TABLE public.radar_analises_cache (
  chave text NOT NULL, mensagens jsonb NOT NULL, criado_em timestamptz DEFAULT now(),
  CONSTRAINT radar_analises_cache_pkey PRIMARY KEY (chave));

CREATE TABLE public.radar_chat_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(), user_id uuid, plano text, idioma text, pergunta text,
  resposta text, ativo text, estrategia_id text, resultado jsonb, config jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT radar_chat_log_pkey PRIMARY KEY (id));

CREATE TABLE public.radar_chat_uso (
  user_id uuid NOT NULL, semana text NOT NULL, usados integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT radar_chat_uso_pkey PRIMARY KEY (user_id, semana));

CREATE INDEX idx_agente_eventos_user ON public.agente_eventos USING btree (user_id, criado_em DESC);
CREATE INDEX idx_sugestoes_user ON public.agente_sugestoes USING btree (user_id, lida, criado_em DESC);
CREATE INDEX babymachine_op_bot_idx ON public.babymachine_operacoes USING btree (bot_id, ts_criada DESC);
CREATE INDEX babymachine_op_status_idx ON public.babymachine_operacoes USING btree (bot_id, status, ts_entrada) WHERE (status = ANY (ARRAY['pendente'::text, 'aberta'::text]));
CREATE INDEX babymachine_op_user_idx ON public.babymachine_operacoes USING btree (user_id, ts_criada DESC);
CREATE INDEX idx_bh_criado ON public.backtests_historico USING btree (criado_em);
CREATE INDEX idx_bh_sessao ON public.backtests_historico USING btree (sessao_id);
CREATE INDEX idx_bh_user ON public.backtests_historico USING btree (user_id);
CREATE INDEX idx_bh_user_data ON public.backtests_historico USING btree (user_id, criado_em);
CREATE INDEX idx_calecon_data ON public.calendario_economico USING btree (data_evento);
CREATE INDEX idx_calecon_impacto ON public.calendario_economico USING btree (impacto);
CREATE INDEX conector_bots_modo_op_idx ON public.conector_bots USING btree (((config_operacional ->> 'modo_operacional'::text))) WHERE (config_operacional IS NOT NULL);
CREATE INDEX idx_conector_bots_token ON public.conector_bots USING btree (bot_token);
CREATE INDEX idx_conector_bots_user ON public.conector_bots USING btree (user_id);
CREATE INDEX idx_snapshots_token ON public.conector_snapshots USING btree (bot_token, criado_em DESC);
CREATE INDEX idx_snapshots_user ON public.conector_snapshots USING btree (user_id, criado_em DESC);
CREATE INDEX idx_estudo_bib_regras ON public.estudo_biblioteca USING btree (regras_versao);
CREATE INDEX idx_estudo_biblioteca_ativo ON public.estudo_biblioteca USING btree (ativo);
CREATE INDEX idx_estudo_biblioteca_combo ON public.estudo_biblioteca USING btree (ativo, periodo, timeframe);
CREATE INDEX idx_estudo_biblioteca_sharpe ON public.estudo_biblioteca USING btree (ativo, sharpe DESC);
CREATE UNIQUE INDEX estudo_v2_celula_unica ON public.estudo_biblioteca_v2 USING btree (ativo, periodo, timeframe, estrategia_id);
CREATE INDEX idx_estudo_v2_ativo ON public.estudo_biblioteca_v2 USING btree (ativo, periodo);
CREATE INDEX mt5_comandos_bot_idx ON public.mt5_comandos USING btree (bot_id, criado_em DESC);
CREATE INDEX mt5_comandos_expira_idx ON public.mt5_comandos USING btree (expira_em) WHERE (status = ANY (ARRAY['pendente'::text, 'entregue'::text]));
CREATE INDEX mt5_comandos_pendentes_idx ON public.mt5_comandos USING btree (bot_token, status, criado_em) WHERE (status = ANY (ARRAY['pendente'::text, 'entregue'::text]));
CREATE INDEX mt5_jobs_bot_status_idx ON public.mt5_jobs USING btree (bot_token, status, criado_em DESC);
CREATE INDEX mt5_jobs_criado_idx ON public.mt5_jobs USING btree (criado_em);
CREATE INDEX idx_radar_chat_log_user_time ON public.radar_chat_log USING btree (user_id, created_at DESC);

ALTER TABLE public.perfis ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agente_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agente_sugestoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.babymachine_operacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtests_historico ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calendario_economico ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.codigos_acesso ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conector_bots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conector_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.estudo_biblioteca ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.estudo_biblioteca_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mq5_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mt5_comandos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mt5_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.radar_analises_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.radar_chat_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.radar_chat_uso ENABLE ROW LEVEL SECURITY;

CREATE POLICY leitura_propria_eventos ON public.agente_eventos AS PERMISSIVE FOR SELECT TO public USING ((auth.uid() = user_id));
CREATE POLICY leitura_propria_sugestoes ON public.agente_sugestoes AS PERMISSIVE FOR SELECT TO public USING ((auth.uid() = user_id));
CREATE POLICY marcar_lida ON public.agente_sugestoes AS PERMISSIVE FOR UPDATE TO public USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));
CREATE POLICY usuario_le_proprio_historico ON public.backtests_historico AS PERMISSIVE FOR SELECT TO public USING ((auth.uid() = user_id));
CREATE POLICY "leitura publica calendario" ON public.calendario_economico AS PERMISSIVE FOR SELECT TO public USING (true);
CREATE POLICY leitura_propria_bots ON public.conector_bots AS PERMISSIVE FOR SELECT TO public USING ((auth.uid() = user_id));
CREATE POLICY leitura_propria_snapshots ON public.conector_snapshots AS PERMISSIVE FOR SELECT TO public USING ((auth.uid() = user_id));
CREATE POLICY usuario_ve_proprio_perfil ON public.perfis AS PERMISSIVE FOR ALL TO public USING ((auth.uid() = id));

CREATE OR REPLACE FUNCTION public._bm_operacoes_limpar_antigas() RETURNS integer LANGUAGE plpgsql AS $function$
declare n integer;
begin
  delete from public.babymachine_operacoes where ts_criada < now() - interval '90 days';
  get diagnostics n = row_count;
  return n;
end;
$function$;
CREATE OR REPLACE FUNCTION public._mt5_expirar_comandos() RETURNS integer LANGUAGE plpgsql AS $function$
declare n integer;
begin
  update public.mt5_comandos
     set status = 'expirado', resultado = coalesce(resultado, '{}'::jsonb) || jsonb_build_object('erro', 'expirou sem confirmacao')
   where status in ('pendente', 'entregue') and expira_em < now();
  get diagnostics n = row_count;
  return n;
end;
$function$;
CREATE OR REPLACE FUNCTION public.criar_perfil_usuario() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $function$
BEGIN
  INSERT INTO public.perfis (id, email, nome) VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data->>'nome');
  RETURN NEW;
END;
$function$;
CREATE TRIGGER ao_criar_usuario AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.criar_perfil_usuario();
COMMIT;
