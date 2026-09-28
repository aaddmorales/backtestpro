-- ═══════════════════════════════════════════════════════════════════════════
-- 0003_r01_claim_transacional.sql — v3-c27r4fim (27/set/2026, fechamento P1-P4)
-- v3: a função confere NO BANCO (join conector_bots) que p_bot_token,
-- p_user_id e o símbolo da decisão pertencem ao MESMO bot — a RPC não
-- confia na leitura prévia da API (ordem de fechamento, P2.3).
-- APLICAÇÃO: SOMENTE PELO DONO, SOMENTE no Postgres/Supabase ISOLADO.
-- NÃO aplicar em produção (decisão C10/B13 é posterior e escrita).
--
-- ORDEM DE APLICAÇÃO: 0002_ciclo_decisoes.sql PRIMEIRO (cria ciclo_decisoes
-- com UNIQUE(bot_id,uid) e UNIQUE(bot_id,ts_barra,lado)); depois este 0003.
--
-- O QUE ESTE ARQUIVO FECHA (auditoria 3, ordem única de 27/set):
--  (1) claim emitida→consumida ANTES de um INSERT que pode falhar sem
--      recuperação → função transacional r01_claim_e_comando: UPDATE
--      condicional + INSERT no MESMO bloco atômico (BEGIN implícito de
--      função plpgsql) — falha em qualquer ponto desfaz TUDO;
--  (2) UNIQUE de uid de abertura em mt5_comandos que na 0002 ficou apenas
--      COMENTADA → índice único parcial EFETIVO aqui;
--  (3) FK, RLS e grants/revogação explícitos.
--
-- NOTA DE ESQUEMA (honestidade): a bancada não tem acesso ao esquema real do
-- ambiente isolado. A FK abaixo assume conector_bots(id) BIGINT/INTEGER PK —
-- confirmar tipo/nome antes de aplicar; se divergirem, ajustar SÓ a linha da
-- FK e registrar no relatório de aplicação.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ── (2) UNIQUE EFETIVA: um único comando de ABERTURA por (bot, uid) ─────────
-- Parcial de propósito: gestão (close/close_all/mover_sl/mover_tp/cancelar)
-- pode referenciar o mesmo uid sem colidir.
CREATE UNIQUE INDEX IF NOT EXISTS ux_mt5_comandos_abertura_uid
    ON public.mt5_comandos (bot_id, (params->>'uid'))
    WHERE tipo IN ('buy','sell') AND params ? 'uid';

-- ── (3a) FK: decisão sempre pertence a um bot existente ─────────────────────
ALTER TABLE public.ciclo_decisoes
    ADD CONSTRAINT fk_ciclo_decisoes_bot
    FOREIGN KEY (bot_id) REFERENCES public.conector_bots(id)
    ON DELETE CASCADE
    NOT VALID;                       -- valida sem travar a tabela na aplicação
ALTER TABLE public.ciclo_decisoes
    VALIDATE CONSTRAINT fk_ciclo_decisoes_bot;

-- ── (3b) RLS: a tabela é DO SERVIDOR. Nenhum papel de cliente lê/escreve ────
ALTER TABLE public.ciclo_decisoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ciclo_decisoes FORCE ROW LEVEL SECURITY;
-- Sem policy criada = anon/authenticated não enxergam NADA (deny-all).
REVOKE ALL   ON public.ciclo_decisoes FROM anon, authenticated;
GRANT  ALL   ON public.ciclo_decisoes TO service_role;

-- ── (1) A OPERAÇÃO ATÔMICA: claim + comando num único bloco ─────────────────
-- Chamada pelo servidor (service_role) via RPC. Semântica:
--   * decisão precisa estar 'emitida', do bot, do símbolo, do lado, no prazo;
--   * UPDATE condicional consome (um vencedor sob corrida — row lock);
--   * INSERT do comando na MESMA transação: se estourar (UNIQUE, FK, o que
--     for), o claim é desfeito JUNTO — jamais decisão consumida sem comando;
--   * dedup de uid garantido pelo índice parcial acima (erro vira recusa).
CREATE OR REPLACE FUNCTION public.r01_claim_e_comando(
    p_decisao_id text,
    p_bot_id     bigint,
    p_bot_token  text,
    p_user_id    uuid,
    p_tipo       text,
    p_params     jsonb DEFAULT '{}'::jsonb,
    p_origem     text  DEFAULT 'manual'
) RETURNS TABLE (ok boolean, motivo text, comando_id bigint, uid text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    d   public.ciclo_decisoes%ROWTYPE;
    cid bigint;
    v_simbolo text;
BEGIN
    IF p_tipo NOT IN ('buy','sell') THEN
        RETURN QUERY SELECT false, 'emissao_so_para_abertura', NULL::bigint, NULL::text;
        RETURN;
    END IF;

    -- v3 (P2.3): VÍNCULO CONFERIDO NO BANCO, não na leitura prévia da API —
    -- token, usuário e bot têm que ser a MESMA linha de conector_bots, e o
    -- símbolo dessa linha é capturado pra conferir contra o da decisão.
    -- NOTA DE ESQUEMA: assume conector_bots(id, bot_token, user_id, simbolo);
    -- confirmar nomes/tipos no isolado ANTES de aplicar (0000_precheck.sql).
    SELECT b.simbolo INTO v_simbolo
      FROM public.conector_bots b
     WHERE b.id = p_bot_id
       AND b.bot_token = p_bot_token
       AND b.user_id = p_user_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'vinculo_bot_invalido(token_user)', NULL::bigint, NULL::text;
        RETURN;
    END IF;

    -- Claim atômico: só consome se ainda 'emitida', do bot certo, no prazo,
    -- do lado certo. RETURNING trava a linha e devolve os dados num passo.
    UPDATE public.ciclo_decisoes c
       SET status = 'consumida', ts_consumo = now()
     WHERE c.id = p_decisao_id
       AND c.status = 'emitida'
       -- c27r4/P1: contrato v4 TAMBÉM no banco (cinto duplo com a API) —
       -- decisão pré-conserto ou forjada sem o carimbo NUNCA vira comando:
       AND c.veredito->>'contrato' = 'r01v4'
       AND c.veredito->>'cv1_veredito' = 'autorizada'
       AND c.bot_id = p_bot_id
       AND c.simbolo = v_simbolo          -- v3: símbolo da decisão = do bot
       AND c.lado   = CASE WHEN p_tipo = 'buy' THEN 1 ELSE -1 END
       AND c.expira_em > now()
    RETURNING c.* INTO d;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false,
            'decisao_invalida_vencida_ou_ja_consumida', NULL::bigint, NULL::text;
        RETURN;
    END IF;

    BEGIN
        INSERT INTO public.mt5_comandos
            (bot_token, user_id, bot_id, tipo, params, status, origem)
        VALUES
            (p_bot_token, p_user_id, p_bot_id, p_tipo,
             p_params || jsonb_build_object(
                 'uid', d.uid,
                 'decisao', jsonb_build_object(
                     'id', d.id, 'uid', d.uid,
                     'ts_barra', d.ts_barra, 'veredito', d.veredito)),
             'pendente', p_origem)
        RETURNING id INTO cid;
    EXCEPTION WHEN unique_violation THEN
        -- uid já comandado (índice parcial). O RAISE desfaz a transação
        -- INTEIRA da função — o claim acima volta sozinho.
        RAISE EXCEPTION 'uid_ja_comandado(dedup_unique)';
    END;

    RETURN QUERY SELECT true, 'ok', cid, d.uid;
END;
$$;

REVOKE ALL ON FUNCTION public.r01_claim_e_comando(text,bigint,text,uuid,text,jsonb,text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.r01_claim_e_comando(text,bigint,text,uuid,text,jsonb,text)
    TO service_role;

COMMIT;

-- ═══ TESTES DE ACEITE (rodar no isolado; NADA disto toca produção) ══════════
-- T1 corrida: 2 conexões psql chamam ao mesmo tempo
--     SELECT * FROM r01_claim_e_comando('<id>', <bot>, '<tok>', '<uuid>', 'buy');
--   → exatamente 1 (ok=true) e 1 linha em mt5_comandos.
-- T2 replay: repetir a chamada → ok=false decisao_invalida_...; contagem igual.
-- T3 falha de INSERT: inserir antes um buy com o MESMO uid (viola o índice)
--   e chamar a função → erro uid_ja_comandado; SELECT status FROM
--   ciclo_decisoes → segue 'emitida' (claim desfeito pela transação).
-- T4 expirada: decisão com expira_em < now() → ok=false.
-- T5 outro bot/lado: p_bot_id/p_tipo trocados → ok=false.
-- T5b (v3) vínculo: p_bot_token de OUTRO bot, p_user_id de OUTRO usuário,
--   ou decisão com símbolo divergente do bot → ok=false vinculo/decisao;
--   claim NÃO acontece (status segue 'emitida').

-- ═══ ROLLBACK (ordem inversa) ═══════════════════════════════════════════════
-- BEGIN;
-- DROP FUNCTION IF EXISTS public.r01_claim_e_comando(text,bigint,text,uuid,text,jsonb,text);
-- ALTER TABLE public.ciclo_decisoes DROP CONSTRAINT IF EXISTS fk_ciclo_decisoes_bot;
-- ALTER TABLE public.ciclo_decisoes NO FORCE ROW LEVEL SECURITY;
-- ALTER TABLE public.ciclo_decisoes DISABLE ROW LEVEL SECURITY;
-- DROP INDEX IF EXISTS public.ux_mt5_comandos_abertura_uid;
-- COMMIT;

-- ── c27r4/P2: testes adicionais T6–T8 (Postgres isolado; NÃO EXECUTADOS
--    nesta bancada — sem Postgres, P2 permanece NÃO VALIDADO) ──────────────
-- T6 RESPOSTA PERDIDA APÓS COMMIT: sessão A chama a RPC e o commit conclui,
--    mas a resposta se perde (simular matando o cliente após o commit, ou
--    pg_terminate_backend na volta). A repetição NÃO re-chama a RPC às cegas:
--    consulta por uid — SELECT id FROM mt5_comandos WHERE bot_id=:b AND
--    tipo IN ('buy','sell') AND params->>'uid' = :uid — e responde o comando
--    existente. Prova: contagens de ciclo_decisoes/mt5_comandos idênticas
--    antes e depois da repetição (1 consumida, 1 comando).
-- T7 FALHA DE CONEXÃO ANTES DO COMMIT: matar a conexão no meio da RPC
--    (pg_terminate_backend durante pg_sleep injetado em cópia de teste).
--    Prova: decisão segue 'emitida', zero comando — o retry limpo é seguro.
-- T8 RESTART DE WORKER: após T6, derrubar e subir o worker da API; a
--    recuperação por uid continua achando o comando (estado no BANCO, não em
--    memória). Prova: nenhuma duplicata após o restart.
