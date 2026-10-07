-- 0010 (C27R23) — AUTORIDADE r01v5: decisão por CANDIDATO assinado (estratégia × timeframe × lado × sinal).
-- (1) autoridade_contratos: chave de emissão por contrato. r01v5 nasce DESLIGADO: enquanto estiver
--     desligado a API só registra "seria emitida" (sombra) e a RPC abaixo recusa qualquer consumo.
-- (2) r05_claim_e_comando: mesmo claim atômico da r01 (emitida→consumida + comando na MESMA transação),
--     para decisões de contrato r01v5. A r01_claim_e_comando (r01v4) NÃO é alterada.
-- (3) etapa 'autoridade_r01v5' na trilha.
-- Idempotente. Sem BEGIN/COMMIT (o apply_migration já envolve em transação).
create table if not exists public.autoridade_contratos (
  contrato           text primary key,
  emissao_habilitada boolean not null default false,
  atualizado_em      timestamptz not null default now(),
  nota               text
);
insert into public.autoridade_contratos (contrato, emissao_habilitada, nota) values
  ('r01v4', true,  'contrato em vigor: veredito do motor (D1/H4 vetam) + M1/M5 no lado'),
  ('r01v5', false, 'candidato assinado; D1/H4 são contexto. DESLIGADO: só sombra até decisão do dono')
on conflict (contrato) do nothing;
alter table public.autoridade_contratos enable row level security;
alter table public.autoridade_contratos force row level security;
revoke all on public.autoridade_contratos from anon, authenticated;
grant all on public.autoridade_contratos to service_role;

create or replace function public.r05_claim_e_comando(
    p_decisao_id text, p_bot_id bigint, p_bot_token text, p_user_id uuid,
    p_tipo text, p_params jsonb default '{}'::jsonb, p_origem text default 'selecao'
) returns table (ok boolean, motivo text, comando_id bigint, uid text)
language plpgsql security definer set search_path = public as $$
declare
    d   public.ciclo_decisoes%rowtype;
    cid bigint;
    v_simbolo text;
    v_ligado boolean;
begin
    if p_tipo not in ('buy','sell') then
        return query select false, 'emissao_so_para_abertura', null::bigint, null::text; return;
    end if;
    select c.emissao_habilitada into v_ligado from public.autoridade_contratos c where c.contrato = 'r01v5';
    if not coalesce(v_ligado, false) then
        return query select false, 'contrato_r01v5_desligado(so_sombra)', null::bigint, null::text; return;
    end if;
    select b.simbolo into v_simbolo from public.conector_bots b
     where b.id = p_bot_id and b.bot_token = p_bot_token and b.user_id = p_user_id;
    if not found then
        return query select false, 'vinculo_bot_invalido(token_user)', null::bigint, null::text; return;
    end if;
    -- claim atômico: só consome se ainda 'emitida', do contrato r01v5, com candidato identificado,
    -- do bot/símbolo/lado certos, dentro da validade da decisão E da validade do candidato.
    update public.ciclo_decisoes c
       set status = 'consumida', ts_consumo = now()
     where c.id = p_decisao_id
       and c.status = 'emitida'
       and c.veredito->>'contrato' = 'r01v5'
       and coalesce(c.veredito->'candidato'->>'uid', '') <> ''
       and (c.veredito->'candidato'->>'lado')::int = c.lado
       and (c.veredito->'candidato'->>'vence_utc')::timestamptz > now()
       and c.bot_id = p_bot_id
       and c.simbolo = v_simbolo
       and c.lado = case when p_tipo = 'buy' then 1 else -1 end
       and c.expira_em > now()
    returning c.* into d;
    if not found then
        return query select false, 'decisao_invalida_vencida_ou_ja_consumida', null::bigint, null::text; return;
    end if;
    begin
        insert into public.mt5_comandos (bot_token, user_id, bot_id, tipo, params, status, origem)
        values (p_bot_token, p_user_id, p_bot_id, p_tipo,
                p_params || jsonb_build_object(
                    'uid', d.uid,
                    'decisao', jsonb_build_object('id', d.id, 'uid', d.uid, 'ts_barra', d.ts_barra, 'veredito', d.veredito)),
                'pendente', p_origem)
        returning id into cid;
    exception when unique_violation then
        raise exception 'uid_ja_comandado(dedup_unique)';
    end;
    return query select true, 'ok', cid, d.uid;
end;
$$;
revoke all on function public.r05_claim_e_comando(text,bigint,text,uuid,text,jsonb,text) from public, anon, authenticated;
grant execute on function public.r05_claim_e_comando(text,bigint,text,uuid,text,jsonb,text) to service_role;

alter table public.ciclo_trilha drop constraint if exists ciclo_trilha_etapa_check;
alter table public.ciclo_trilha add constraint ciclo_trilha_etapa_check check (etapa in (
  'snapshot','leituras','ciclos','motor','decisao','veto','persistencia','rpc','comando',
  'resposta_mt5','abertura','fechamento','divergencia','falha_coleta','atestado','selecao','autoridade_r01v5'));
