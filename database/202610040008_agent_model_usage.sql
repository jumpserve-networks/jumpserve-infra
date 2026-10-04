begin;
alter table public.agent_answers add column if not exists model_usage jsonb;
alter table public.agent_answers add column if not exists estimated_model_cost_usd numeric check(estimated_model_cost_usd>=0);
alter table public.agent_answers add column if not exists pricing_provenance jsonb;
grant insert(model_usage,estimated_model_cost_usd,pricing_provenance) on public.agent_answers to service_role;
drop function if exists public.save_agent_turn(uuid,text,jsonb,uuid,uuid,text,text,text,text);
create or replace function public.save_agent_turn(
 p_session_id uuid,p_user_id text,p_messages jsonb,p_answer_id uuid,
 p_prompt_version_id uuid,p_model_id text,p_analysis_version text,p_response text,
 p_module_id text default 'congestion-control-emulated',p_model_usage jsonb default null,
 p_estimated_model_cost_usd numeric default null,p_pricing_provenance jsonb default null
) returns uuid language plpgsql security invoker set search_path='' as $$
declare changed integer;
begin
 if jsonb_typeof(p_messages) is distinct from 'array' then raise exception 'Messages must be an array'; end if;
 if not exists(select 1 from public.agent_prompt_versions where id=p_prompt_version_id and published_at is not null and module_id=p_module_id) then
  raise exception 'Answer must reference a published prompt in the requested module'; end if;
 insert into public.agent_sessions(id,user_id,messages,module_id,updated_at)
 values(p_session_id,p_user_id,p_messages,p_module_id,now())
 on conflict(id) do update set messages=excluded.messages,updated_at=excluded.updated_at
 where agent_sessions.user_id=excluded.user_id and agent_sessions.module_id=excluded.module_id;
 get diagnostics changed=row_count;
 if changed<>1 then raise exception 'Conversation owner or module mismatch'; end if;
 insert into public.agent_answers(id,session_id,prompt_version_id,model_id,analysis_version,response,model_usage,estimated_model_cost_usd,pricing_provenance)
 values(p_answer_id,p_session_id,p_prompt_version_id,p_model_id,p_analysis_version,p_response,p_model_usage,p_estimated_model_cost_usd,p_pricing_provenance);
 return p_answer_id;
end;
$$;
revoke all on function public.save_agent_turn(uuid,text,jsonb,uuid,uuid,text,text,text,text,jsonb,numeric,jsonb) from public,anon,authenticated;
grant execute on function public.save_agent_turn(uuid,text,jsonb,uuid,uuid,text,text,text,text,jsonb,numeric,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
