-- T1–T8 (exceto a corrida T6, feita por chamadas paralelas) no Supabase de HOMOLOGACAO.
-- Tudo dentro de UM bloco DO: ao final RAISE EXCEPTION com o placar => o Postgres
-- DESFAZ todos os fixtures (nada fica no banco). Sem skip: qualquer falha = FALHA:<Tn>.
DO $$
DECLARE
  u1 uuid := gen_random_uuid(); u2 uuid := gen_random_uuid();
  tok text := md5(random()::text); tok2 text := md5(random()::text);
  b bigint; b2 bigint; did text; r record; n int; st text; placar text := '';
  ts0 timestamptz := date_trunc('hour', now()) - interval '1 day';
  seq int := 0;
BEGIN
  IF to_regclass('public._bt_homolog_marker') IS NULL THEN RAISE EXCEPTION 'FALHA: nao e homolog'; END IF;
  INSERT INTO auth.users(id, email, aud, role, instance_id) VALUES
    (u1, 't18a-'||left(u1::text,8)||'@example.com','authenticated','authenticated','00000000-0000-0000-0000-000000000000'),
    (u2, 't18b-'||left(u2::text,8)||'@example.com','authenticated','authenticated','00000000-0000-0000-0000-000000000000');
  INSERT INTO conector_bots(user_id, bot_token, nome, simbolo) VALUES (u1, tok, 'T18', 'XAUUSD') RETURNING id INTO b;
  INSERT INTO conector_bots(user_id, bot_token, nome, simbolo) VALUES (u2, tok2, 'T18b', 'XAUUSD') RETURNING id INTO b2;

  -- helper inline: nova decisao
  -- T1
  seq := seq+1; did := md5('d'||seq||random());
  INSERT INTO ciclo_decisoes(id,bot_id,simbolo,lado,uid,ts_barra,veredito,expira_em) VALUES
   (did,b,'XAUUSD',1,b||'-'||seq||'-B',ts0+seq*interval '15 min',
    '{"contrato":"r01v4","cv1_veredito":"autorizada","topdown":["autorizada","favor"]}',now()+interval '15 min');
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'buy','{"volume":0.01}','t1');
  IF NOT (r.ok AND r.motivo='ok' AND r.comando_id IS NOT NULL AND r.uid=b||'-'||seq||'-B') THEN RAISE EXCEPTION 'FALHA:T1 %', row_to_json(r); END IF;
  SELECT status INTO st FROM ciclo_decisoes WHERE id=did;
  SELECT count(*) INTO n FROM mt5_comandos WHERE id=r.comando_id AND params->>'uid'=r.uid AND params->'decisao'->>'id'=did;
  IF st<>'consumida' OR n<>1 THEN RAISE EXCEPTION 'FALHA:T1b st=% n=%',st,n; END IF;
  placar := placar||'T1 ok; ';
  -- T2 replay
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t2');
  SELECT count(*) INTO n FROM mt5_comandos WHERE bot_id=b;
  IF r.ok OR r.motivo<>'decisao_invalida_vencida_ou_ja_consumida' OR n<>1 THEN RAISE EXCEPTION 'FALHA:T2 % n=%',row_to_json(r),n; END IF;
  placar := placar||'T2 ok; ';
  -- T3 vinculo (token alheio, user alheio, lado, simbolo)
  seq := seq+1; did := md5('d'||seq||random());
  INSERT INTO ciclo_decisoes(id,bot_id,simbolo,lado,uid,ts_barra,veredito,expira_em) VALUES
   (did,b,'XAUUSD',1,b||'-'||seq||'-B',ts0+seq*interval '15 min',
    '{"contrato":"r01v4","cv1_veredito":"autorizada","topdown":["autorizada","favor"]}',now()+interval '15 min');
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok2,u1,'buy','{}','t3'); IF r.motivo<>'vinculo_bot_invalido(token_user)' THEN RAISE EXCEPTION 'FALHA:T3a %',row_to_json(r); END IF;
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u2,'buy','{}','t3'); IF r.motivo<>'vinculo_bot_invalido(token_user)' THEN RAISE EXCEPTION 'FALHA:T3b %',row_to_json(r); END IF;
  SELECT * INTO r FROM r01_claim_e_comando(did,b2,tok2,u2,'buy','{}','t3'); IF r.ok THEN RAISE EXCEPTION 'FALHA:T3c outro bot abriu'; END IF;
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'sell','{}','t3'); IF r.ok THEN RAISE EXCEPTION 'FALHA:T3d lado'; END IF;
  UPDATE conector_bots SET simbolo='BTCUSD' WHERE id=b;
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t3'); IF r.ok THEN RAISE EXCEPTION 'FALHA:T3e simbolo'; END IF;
  UPDATE conector_bots SET simbolo='XAUUSD' WHERE id=b;
  SELECT status INTO st FROM ciclo_decisoes WHERE id=did; SELECT count(*) INTO n FROM mt5_comandos WHERE bot_id IN (b,b2);
  IF st<>'emitida' OR n<>1 THEN RAISE EXCEPTION 'FALHA:T3f st=% n=%',st,n; END IF;
  placar := placar||'T3 ok; ';
  -- T4 vencida
  seq := seq+1; did := md5('d'||seq||random());
  INSERT INTO ciclo_decisoes(id,bot_id,simbolo,lado,uid,ts_barra,veredito,expira_em) VALUES
   (did,b,'XAUUSD',1,b||'-'||seq||'-B',ts0+seq*interval '15 min',
    '{"contrato":"r01v4","cv1_veredito":"autorizada","topdown":["autorizada","favor"]}',now()-interval '5 s');
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t4');
  SELECT status INTO st FROM ciclo_decisoes WHERE id=did;
  IF r.ok OR r.motivo<>'decisao_invalida_vencida_ou_ja_consumida' OR st<>'emitida' THEN RAISE EXCEPTION 'FALHA:T4'; END IF;
  placar := placar||'T4 ok; ';
  -- T5 unique_violation desfaz o claim
  seq := seq+1; did := md5('d'||seq||random());
  INSERT INTO ciclo_decisoes(id,bot_id,simbolo,lado,uid,ts_barra,veredito,expira_em) VALUES
   (did,b,'XAUUSD',1,b||'-'||seq||'-B',ts0+seq*interval '15 min',
    '{"contrato":"r01v4","cv1_veredito":"autorizada","topdown":["autorizada","favor"]}',now()+interval '15 min');
  INSERT INTO mt5_comandos(bot_id,bot_token,user_id,tipo,params) VALUES (b,tok,u1,'buy',jsonb_build_object('uid',b||'-'||seq||'-B'));
  BEGIN
    SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t5');
    RAISE EXCEPTION 'FALHA:T5 nao levantou';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM LIKE 'FALHA:%' THEN RAISE; END IF;
    IF SQLERRM <> 'uid_ja_comandado(dedup_unique)' THEN RAISE EXCEPTION 'FALHA:T5 msg=%',SQLERRM; END IF;
  END;
  SELECT status INTO st FROM ciclo_decisoes WHERE id=did; SELECT count(*) INTO n FROM mt5_comandos WHERE bot_id=b;
  IF st<>'emitida' OR n<>2 THEN RAISE EXCEPTION 'FALHA:T5b st=% n=%',st,n; END IF;
  placar := placar||'T5 ok; ';
  -- T7 contrato/CV1 e tipo de gestao
  FOR r IN SELECT * FROM (VALUES ('{"contrato":"r01v3","cv1_veredito":"autorizada"}'::jsonb),
                                 ('{"contrato":"r01v4","cv1_veredito":"bloqueada"}'::jsonb),
                                 ('{"contrato":"r01v4","cv1_veredito":"neutra"}'::jsonb)) v(ver) LOOP
    seq := seq+1; did := md5('d'||seq||random());
    INSERT INTO ciclo_decisoes(id,bot_id,simbolo,lado,uid,ts_barra,veredito,expira_em) VALUES
     (did,b,'XAUUSD',1,b||'-'||seq||'-B',ts0+seq*interval '15 min',r.ver,now()+interval '15 min');
    PERFORM 1 FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t7') x WHERE x.ok;
    IF FOUND THEN RAISE EXCEPTION 'FALHA:T7 % abriu', r.ver; END IF;
    SELECT status INTO st FROM ciclo_decisoes WHERE id=did; IF st<>'emitida' THEN RAISE EXCEPTION 'FALHA:T7 st'; END IF;
  END LOOP;
  SELECT * INTO r FROM r01_claim_e_comando(did,b,tok,u1,'close','{}','t7');
  IF r.motivo<>'emissao_so_para_abertura' THEN RAISE EXCEPTION 'FALHA:T7 close'; END IF;
  placar := placar||'T7 ok; ';
  -- T8 grants e RLS (papel de cliente)
  EXECUTE 'SET LOCAL ROLE anon';
  BEGIN PERFORM 1 FROM ciclo_decisoes LIMIT 1; RAISE EXCEPTION 'FALHA:T8 anon leu';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN PERFORM 1 FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t8'); RAISE EXCEPTION 'FALHA:T8 anon executou';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  EXECUTE 'SET LOCAL ROLE authenticated';
  BEGIN PERFORM 1 FROM ciclo_decisoes LIMIT 1; RAISE EXCEPTION 'FALHA:T8 authenticated leu';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN PERFORM 1 FROM r01_claim_e_comando(did,b,tok,u1,'buy','{}','t8'); RAISE EXCEPTION 'FALHA:T8 authenticated executou';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  EXECUTE 'RESET ROLE';
  placar := placar||'T8 ok';
  RAISE EXCEPTION 'RESULTADO_T1_T8: % (fixtures desfeitos por este RAISE)', placar;
END $$;
