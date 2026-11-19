begin;
-- Durable leases for existing owner-approved work. Neither a webhook nor the
-- scheduler may create assessments, choose scope, replace calls, or alter limits.
create table if not exists public.research_paper_background_leases (
 work_key text primary key,lease_token uuid not null,lease_until timestamptz not null,next_at timestamptz not null,
 updated_at timestamptz not null default clock_timestamp(),last_error text
);
alter table public.research_paper_background_leases enable row level security;
revoke all on public.research_paper_background_leases from public,anon,authenticated,service_role;
grant select on public.research_paper_background_leases to service_role;
create table if not exists public.research_paper_agent_cleanups (
 call_id uuid primary key references public.research_paper_agent_sessions(call_id),provider_session_id text not null,receipt jsonb not null,created_at timestamptz not null default clock_timestamp()
);
alter table public.research_paper_agent_cleanups enable row level security;
revoke all on public.research_paper_agent_cleanups from public,anon,authenticated,service_role;
grant select on public.research_paper_agent_cleanups to service_role;
drop trigger if exists paper_agent_cleanup_immutable on public.research_paper_agent_cleanups;
create trigger paper_agent_cleanup_immutable before update or delete on public.research_paper_agent_cleanups for each row execute function public.research_immutable();
create or replace function public.research_paper_background_candidates() returns table(work_key text,kind text,study_id uuid,owner_id uuid,workflow_id uuid,experiment_index integer) language sql stable set search_path='' as $$
 select 'intake:'||i.study_id,'intake',i.study_id,i.owner_id,null::uuid,0 from public.research_paper_intakes i where i.status in ('uploaded','submitting','processing') and not public.research_assessment_deleted(i.study_id)
 union all select 'plan:'||p.study_id,'plan',p.study_id,p.owner_id,null::uuid,0 from public.research_experiment_plans p where p.status in ('submitting','processing') and not public.research_assessment_deleted(p.study_id)
 union all select 'scripts:'||s.study_id||':'||s.experiment_index,'scripts',s.study_id,s.owner_id,null::uuid,s.experiment_index from public.research_experiment_scripts s where s.status in ('submitting','processing') and not public.research_assessment_deleted(s.study_id)
 union all select 'quality:'||w.id,'quality',w.study_id,w.owner_id,w.id,w.experiment_index from public.research_paper_quality_workflows w left join public.research_paper_quality_calls c on c.id=w.current_call_id
 where (w.status in ('review_pending','repair_pending','running') or w.status='uncertain' and c.provider_type='managed_agent') and not public.research_assessment_deleted(w.study_id)
 union all select 'agent_cleanup:'||s.call_id,'agent_cleanup',s.study_id,s.owner_id,s.call_id,0 from public.research_paper_agent_sessions s
 where s.status in ('completed','failed','cancelled') and s.provider_session_id is not null and s.updated_at<=clock_timestamp()-interval '60 seconds' and not exists(select 1 from public.research_paper_agent_cleanups done where done.call_id=s.call_id)
$$;
create or replace function public.research_paper_agent_cleanup_control(p_operation text,p_call uuid,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
declare s public.research_paper_agent_sessions;receipt jsonb;begin
 select * into s from public.research_paper_agent_sessions where call_id=p_call for update;
 if s.call_id is null or s.status not in ('completed','failed','cancelled') or s.provider_session_id is null then raise exception 'Only retained terminal managed sessions can be cleaned up';end if;
 if p_operation='context' then return jsonb_build_object('session',to_jsonb(s),'done',exists(select 1 from public.research_paper_agent_cleanups where call_id=s.call_id));end if;
 if p_operation<>'record' or jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>100000 then raise exception 'Bounded provider cleanup receipt required';end if;
 receipt=p_payload->'receipt';
 if receipt->>'id' is distinct from s.provider_session_id or not coalesce(receipt->'deleted'='true'::jsonb or receipt->'retrieval_http_status'='404'::jsonb,false) then raise exception 'Original provider deletion or not-found evidence required';end if;
 insert into public.research_paper_agent_cleanups(call_id,provider_session_id,receipt) values(s.call_id,s.provider_session_id,receipt) on conflict(call_id) do nothing;
 return jsonb_build_object('retained',true);
end$$;
create or replace function public.research_paper_background_control(p_operation text,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
#variable_conflict use_variable
declare item record;lease public.research_paper_background_leases;result jsonb='[]';ref text;key text;amount integer;begin
 if jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>2000 then raise exception 'Bounded background continuation request required';end if;
 perform pg_advisory_xact_lock(hashtextextended('paper-background-continuation-v1',0));
 if p_operation='claim' then
  amount=(p_payload->>'limit')::integer;if amount not between 1 and 2 then raise exception 'Bounded background batch required';end if;
  for item in select c.* from public.research_paper_background_candidates() c left join public.research_paper_background_leases l using(work_key)
   where coalesce(l.lease_until,'epoch'::timestamptz)<=clock_timestamp() and coalesce(l.next_at,'epoch'::timestamptz)<=clock_timestamp()
   order by coalesce(l.next_at,'epoch'::timestamptz),c.work_key limit amount loop
   insert into public.research_paper_background_leases(work_key,lease_token,lease_until,next_at) values(item.work_key,gen_random_uuid(),clock_timestamp()+interval '180 seconds',clock_timestamp())
    on conflict(work_key) do update set lease_token=excluded.lease_token,lease_until=excluded.lease_until,updated_at=clock_timestamp() returning * into lease;
   result=result||jsonb_build_array(to_jsonb(item)||jsonb_build_object('lease_token',lease.lease_token));
  end loop;
  return result;
 elsif p_operation='release' then
  update public.research_paper_background_leases set lease_until=clock_timestamp(),next_at=clock_timestamp()+case when p_payload->'failed'='true'::jsonb then interval '60 seconds' else interval '15 seconds' end,updated_at=clock_timestamp(),last_error=case when p_payload->'failed'='true'::jsonb then 'Continuation temporarily unavailable; original identities retained.' else null end
   where work_key=p_payload->>'work_key' and lease_token::text=p_payload->>'lease_token';
  return jsonb_build_object('released',found);
 elsif p_operation='enqueue_provider' then
  ref=p_payload->>'provider_id';if coalesce(ref,'') !~ '^(resp_|sess_)[A-Za-z0-9_-]{1,200}$' then raise exception 'A bounded original provider identity is required';end if;
  -- Unknown IDs are acknowledged without admission. Lost managed acknowledgments
  -- are independently reconciled by retained metadata on the periodic path.
  for key in
   select 'intake:'||study_id from public.research_paper_intakes where provider_response_id=ref
   union select 'plan:'||study_id from public.research_experiment_plans where provider_response_id=ref
   union select 'scripts:'||study_id||':'||experiment_index from public.research_experiment_scripts where provider_response_id=ref
   union select 'quality:'||workflow_id from public.research_paper_quality_calls where provider_response_id=ref
   union select 'quality:'||workflow_id from public.research_paper_agent_sessions where provider_session_id=ref
  loop
   insert into public.research_paper_background_leases(work_key,lease_token,lease_until,next_at) values(key,gen_random_uuid(),'epoch',clock_timestamp())
    on conflict(work_key) do update set next_at=least(research_paper_background_leases.next_at,excluded.next_at);
  end loop;
  return jsonb_build_object('retained',true);
 end if;
 raise exception 'Unknown background continuation operation';
end$$;
revoke all on function public.research_paper_background_candidates(),public.research_paper_background_control(text,jsonb),public.research_paper_agent_cleanup_control(text,uuid,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.research_paper_background_control(text,jsonb),public.research_paper_agent_cleanup_control(text,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
