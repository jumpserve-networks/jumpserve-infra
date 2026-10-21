begin;
create table public.research_model_workers(
 id text primary key check(id='openclaw-production-v1'),status text not null check(status in ('ready','auth-required','paused-quota','unavailable')),
 model_id text not null check(model_id='gpt-6.1-sol'),configuration jsonb not null,updated_at timestamptz not null default clock_timestamp()
);
create table public.research_model_dispatches(
 id uuid primary key references public.research_autonomy_turns(id),study_id uuid not null,task_id uuid not null,
 runtime text not null check(runtime='openclaw-production-v1'),request_raw text not null check(octet_length(request_raw)<=96000),
 request_sha256 text not null check(request_sha256=encode(sha256(convert_to(request_raw,'UTF8')),'hex')),
 status text not null default 'queued' check(status in ('queued','running','complete','failed','unknown','paused-quota','paused-auth','invalid-output')),
 lease_token uuid,lease_until timestamptz,response_artifact_id uuid,response_sha256 text,provenance jsonb not null default '{}',
 created_at timestamptz not null default clock_timestamp(),ended_at timestamptz,
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 foreign key(study_id,response_artifact_id) references public.research_artifacts(study_id,id),
 check(status<>'complete' or (response_artifact_id is not null and response_sha256 ~ '^[a-f0-9]{64}$'))
);
create index research_model_dispatch_ready on public.research_model_dispatches(status,created_at);
create function public.research_model_dispatch_immutable() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or old.status not in ('queued','running') or
  (new.id,new.study_id,new.task_id,new.runtime,new.request_raw,new.request_sha256,new.created_at) is distinct from
  (old.id,old.study_id,old.task_id,old.runtime,old.request_raw,old.request_sha256,old.created_at) then raise exception 'Original model dispatch and terminal receipt are immutable'; end if;
 return new;
end $$;
create trigger research_model_dispatch_immutable before update or delete on public.research_model_dispatches for each row execute function public.research_model_dispatch_immutable();
alter table public.research_model_workers enable row level security;
alter table public.research_model_dispatches enable row level security;
revoke all on public.research_model_workers,public.research_model_dispatches from public,anon,authenticated;
grant select,insert,update on public.research_model_workers,public.research_model_dispatches to service_role;

create function public.research_model_dispatch(p_operation text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_turns;v jsonb;begin
 if p_operation='health' then
  return coalesce((select jsonb_build_object('runtime',id,'model_id',model_id,'status',case when updated_at>clock_timestamp()-interval '30 seconds' then status else 'unavailable' end,'updated_at',updated_at) from public.research_model_workers where id='openclaw-production-v1'),jsonb_build_object('runtime','openclaw-production-v1','model_id','gpt-6.1-sol','status','unavailable','updated_at',null));
 elsif p_operation='heartbeat' then
  insert into public.research_model_workers(id,status,model_id,configuration) values('openclaw-production-v1',p_payload->>'status','gpt-6.1-sol',p_payload->'configuration')
  on conflict(id) do update set status=excluded.status,configuration=excluded.configuration,updated_at=clock_timestamp();
  return jsonb_build_object('retained',true);
 elsif p_operation='enqueue' then
  select * into strict t from public.research_autonomy_turns where id=(p_payload->>'id')::uuid;
  if t.status<>'running' or t.model_id<>'gpt-6.1-sol' or t.study_id is distinct from (p_payload->>'study_id')::uuid or t.task_id is distinct from (p_payload->>'task_id')::uuid
   or t.request_raw is distinct from p_payload->>'request_raw' or t.request_sha256 is distinct from p_payload->>'request_sha256' then raise exception 'Original admitted OpenClaw turn required'; end if;
  select * into d from public.research_model_dispatches where id=t.id;
  if found then return to_jsonb(d)||jsonb_build_object('replayed',true);end if;
  insert into public.research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256)
  values(t.id,t.study_id,t.task_id,p_payload->>'runtime',t.request_raw,t.request_sha256) returning * into d;
  return to_jsonb(d)||jsonb_build_object('replayed',false);
 elsif p_operation='claim' then
  update public.research_model_dispatches set status='unknown',ended_at=clock_timestamp(),provenance=provenance||jsonb_build_object('reason','Model worker lease expired; provider outcome needs reconciliation.') where status='running' and lease_until<=clock_timestamp();
  if (public.research_model_dispatch('health','{}')->>'status') is distinct from 'ready' then return null;end if;
  select a.* into d from public.research_model_dispatches a join public.research_autonomy_turns r on r.id=a.id
   join public.research_autonomy_tasks q on q.id=a.task_id join public.research_autonomy_workflows w on w.study_id=a.study_id
   where a.status='queued' and r.status='running' and q.status='running' and q.lease_until>clock_timestamp()+interval '100 seconds'
   and w.status='running' and w.deadline_at>clock_timestamp()+interval '100 seconds' and w.committed_cents<=w.max_spend_cents
   order by a.created_at,a.id for update of a skip locked limit 1;
  if not found then return null;end if;
  update public.research_model_dispatches set status='running',lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '115 seconds' where id=d.id returning * into d;
  return to_jsonb(d)||jsonb_build_object('actor_id',(select owner_id from public.research_study_owners where study_id=d.study_id));
 elsif p_operation='result' then
  select * into strict d from public.research_model_dispatches where id=(p_payload->>'id')::uuid and study_id=(p_payload->>'study_id')::uuid;
  return to_jsonb(d)-array['request_raw','lease_token'];
 elsif p_operation='finish' then
  select * into strict d from public.research_model_dispatches where id=(p_payload->>'id')::uuid for update;
  if d.status<>'running' or d.lease_token is distinct from (p_payload->>'token')::uuid or d.lease_until<=clock_timestamp() then raise exception 'Current fenced model lease required; do not replace an unknown outcome';end if;
  if p_payload->>'status'='complete' and not exists(select 1 from public.research_artifacts where id=(p_payload->>'response_artifact_id')::uuid and study_id=d.study_id and sha256=p_payload->>'response_sha256') then raise exception 'Hash-verified stored response required';end if;
  update public.research_model_dispatches set status=p_payload->>'status',response_artifact_id=(p_payload->>'response_artifact_id')::uuid,response_sha256=p_payload->>'response_sha256',provenance=p_payload->'provenance',ended_at=clock_timestamp() where id=d.id returning * into d;
  return to_jsonb(d)-array['request_raw','lease_token'];
 end if;
 raise exception 'Unsupported private model operation';
end $$;
revoke all on function public.research_model_dispatch(text,jsonb),public.research_model_dispatch_immutable() from public,anon,authenticated;
grant execute on function public.research_model_dispatch(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
