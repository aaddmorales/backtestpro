-- 0003_r01_claim_transacional.sql  (reautoria C27R9 · 28/set/2026)
-- A 0003 v3 auditada em 27/set NAO chegou a esta bancada; reescrita do contrato
-- chamado pelo api.py (_r01_abrir_via_rpc): args p_decisao_id, p_bot_id,
-- p_bot_token, p_user_id, p_tipo, p_params, p_origem -> linhas (ok, motivo, comando_id).
-- Claim emitida->consumida + INSERT do comando na MESMA transacao; vinculo
-- token/user/simbolo conferido NO BANCO; unique_violation -> RAISE (desfaz tudo).
DO $$ BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: sem _bt_homolog_marker (so ambiente isolado)';
  END IF;
  IF to_regclass('public.ciclo_decisoes') IS NULL THEN
    RAISE EXCEPTION 'ABORTADO: aplicar 0002 antes da 0003';
  END IF; END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mt5_comandos_abertura_uid
  ON public.mt5_comandos (bot_id, (params->>'uid'))
  WHERE tipo IN ('buy', 'sell');

CREATE OR REPLACE FUNCTION public.r01_claim_e_comando(
  p_decisao_id text, p_bot_id bigint, p_bot_token text, p_user_id uuid,
  p_tipo text, p_params jsonb, p_origem text)
RETURNS TABLE (ok boolean, motivo text, comando_id bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  d public.ciclo_decisoes%ROWTYPE;
  b public.conector_bots%ROWTYPE;
  v_lado smallint;
  v_cmd bigint;
BEGIN
  IF p_tipo NOT IN ('buy','sell') THEN
    RETURN QUERY SELECT false, 'tipo_nao_e_abertura'::text, NULL::bigint; RETURN;
  END IF;
  v_lado := CASE WHEN p_tipo = 'buy' THEN 1 ELSE -1 END;

  SELECT * INTO b FROM public.conector_bots WHERE id = p_bot_id;
  IF NOT FOUND OR b.excluido
     OR b.bot_token IS DISTINCT FROM p_bot_token
     OR b.user_id  IS DISTINCT FROM p_user_id THEN
    RETURN QUERY SELECT false, 'vinculo_bot_invalido'::text, NULL::bigint; RETURN;
  END IF;

  -- claim atomico: so UMA transacao muda emitida->consumida
  UPDATE public.ciclo_decisoes
     SET status = 'consumida', consumida_em = now()
   WHERE id = p_decisao_id
     AND bot_id = p_bot_id
     AND status = 'emitida'
     AND simbolo = b.simbolo
     AND lado = v_lado
     AND expira_em > now()
     AND veredito->>'contrato' = 'r01v4'
     AND veredito->>'cv1_veredito' = 'autorizada'
     AND veredito->'topdown'->>0 = 'autorizada'
  RETURNING * INTO d;
  IF NOT FOUND THEN
    SELECT * INTO d FROM public.ciclo_decisoes WHERE id = p_decisao_id;
    RETURN QUERY SELECT false,
      (CASE WHEN NOT FOUND THEN 'decisao_inexistente'
            WHEN d.bot_id <> p_bot_id THEN 'decisao_de_outro_bot'
            WHEN d.status <> 'emitida' THEN 'decisao_nao_emitida(' || d.status || ')'
            WHEN d.simbolo IS DISTINCT FROM b.simbolo THEN 'decisao_de_outro_simbolo'
            WHEN d.lado <> v_lado THEN 'decisao_lado_incoerente'
            WHEN d.expira_em <= now() THEN 'decisao_vencida'
            ELSE 'decisao_contrato_invalido' END)::text, NULL::bigint;
    RETURN;
  END IF;

  -- mesmo uid da decisao no comando (o servidor e a fonte do uid)
  INSERT INTO public.mt5_comandos (bot_id, bot_token, user_id, tipo, params, status, origem)
  VALUES (p_bot_id, p_bot_token, p_user_id, p_tipo,
          jsonb_set(coalesce(p_params,'{}'::jsonb), '{uid}', to_jsonb(d.uid)),
          'pendente', p_origem)
  RETURNING id INTO v_cmd;
  -- unique_violation no INSERT propaga como excecao: a transacao inteira
  -- (inclusive o claim acima) e desfeita pelo Postgres.
  RETURN QUERY SELECT true, 'ok'::text, v_cmd;
END $$;

REVOKE ALL ON FUNCTION public.r01_claim_e_comando(text,bigint,text,uuid,text,jsonb,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.r01_claim_e_comando(text,bigint,text,uuid,text,jsonb,text) TO service_role;
