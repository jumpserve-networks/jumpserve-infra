begin;
-- New stage only; prior prompts, attempts, resource ceilings and findings stay
-- immutable. This migration enables no prompt, worker or existing assessment.
alter table public.research_autonomy_tasks drop constraint research_autonomy_tasks_stage_check;
alter table public.research_autonomy_tasks add constraint research_autonomy_tasks_stage_check
 check(stage in ('intake','planning','building','comprehension','critic','execution','assessment'));

create table public.research_builder_calls(
 id uuid primary key default gen_random_uuid(),study_id uuid not null,task_id uuid not null,
 dispatch_id uuid not null references public.research_model_dispatches(id),number integer not null check(number>=1),
 prompt_version_id uuid not null references public.agent_prompt_versions(id),model_id text not null check(model_id='gpt-6.1-sol'),
 request_artifact_id uuid not null,request_sha256 text not null check(request_sha256 ~ '^[a-f0-9]{64}$'),request_bytes integer not null check(request_bytes between 1 and 256000),
 status text not null default 'running' check(status in ('running','complete','failed','unknown','paused-auth','paused-quota','invalid-output')),
 reserved_cents integer not null check(reserved_cents in (0,100)),response_artifact_id uuid,response_sha256 text,
 usage jsonb,response_received boolean,http_status integer,reason text,
 created_at timestamptz not null default clock_timestamp(),ended_at timestamptz,
 unique(task_id,number),unique(dispatch_id,request_sha256),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 foreign key(study_id,request_artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,response_artifact_id) references public.research_artifacts(study_id,id),
 check(status<>'complete' or (response_artifact_id is not null and response_sha256 ~ '^[a-f0-9]{64}$' and response_received is true))
);
create unique index research_builder_one_call_running on public.research_builder_calls(dispatch_id) where status='running';
create function public.research_builder_call_immutable() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or old.status<>'running' or
 (new.id,new.study_id,new.task_id,new.dispatch_id,new.number,new.prompt_version_id,new.model_id,new.request_artifact_id,new.request_sha256,new.request_bytes,new.reserved_cents,new.created_at)
 is distinct from
 (old.id,old.study_id,old.task_id,old.dispatch_id,old.number,old.prompt_version_id,old.model_id,old.request_artifact_id,old.request_sha256,old.request_bytes,old.reserved_cents,old.created_at)
 then raise exception 'Original builder prompts and terminal calls are immutable'; end if; return new;
end $$;
create trigger research_builder_calls_immutable before update or delete on public.research_builder_calls for each row execute function public.research_builder_call_immutable();
alter table public.research_builder_calls enable row level security;
revoke all on public.research_builder_calls from public,anon,authenticated;
grant select,insert,update on public.research_builder_calls to service_role;

create function public.research_builder_call(p_operation text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_tasks;w public.research_autonomy_workflows;
 r public.research_autonomy_turns;c public.research_builder_calls;cents integer; n integer; begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict d from public.research_model_dispatches where id=(p_payload->>'dispatch_id')::uuid for update;
 if d.status<>'running' or d.lease_token is distinct from (p_payload->>'token')::uuid or d.lease_until<=clock_timestamp() then raise exception 'Current fenced dispatch lease required'; end if;
 select * into strict r from public.research_autonomy_turns where id=d.id;
 select * into strict t from public.research_autonomy_tasks where id=d.task_id for update;
 select * into strict w from public.research_autonomy_workflows where study_id=d.study_id for update;
 if t.stage<>'building' or t.status<>'running' or t.lease_until<=clock_timestamp() or r.stage<>'building' or r.status<>'running' then raise exception 'Current builder controller turn required'; end if;
 if p_operation='begin' then
  -- Refuse duplicates even if terminal: the worker may serve its captured local
  -- response, but must never issue the provider request twice.
  if exists(select 1 from public.research_builder_calls where dispatch_id=d.id and request_sha256=p_payload->>'request_sha256') then return jsonb_build_object('denied','retained-request'); end if;
  if exists(select 1 from public.research_builder_calls where dispatch_id=d.id and status in ('running','unknown')) then return jsonb_build_object('denied','unconfirmed-call'); end if;
  if w.status<>'running' then return jsonb_build_object('denied',w.status); end if;
  if w.deadline_at<=clock_timestamp()+interval '90 seconds' then return jsonb_build_object('denied','deadline'); end if;
  if not exists(select 1 from public.agent_prompt_versions v join public.agent_prompt_settings s on s.active_version_id=v.id and s.module_id=v.module_id where v.id=r.prompt_version_id and v.module_id='research-experiment-builder' and v.published_at is not null) then raise exception 'Published evaluated builder prompt required'; end if;
  if not exists(select 1 from public.research_artifacts where study_id=d.study_id and id=(p_payload->>'request_artifact_id')::uuid and sha256=p_payload->>'request_sha256' and byte_count=(p_payload->>'request_bytes')::integer) then raise exception 'Stored original native prompt with exact byte hash required'; end if;
  -- The containing controller turn has already reserved $1. Its first native
  -- request uses that commitment; every subsequent native request reserves $1.
  cents=case when exists(select 1 from public.research_builder_calls where dispatch_id=d.id) then 100 else 0 end;
  if w.committed_cents+cents>w.max_spend_cents then return jsonb_build_object('denied','budget'); end if;
  n=t.attempts;
  if cents>0 then
   update public.research_autonomy_workflows set committed_cents=committed_cents+cents,updated_at=clock_timestamp() where study_id=w.study_id;
   update public.research_autonomy_tasks set attempts=attempts+1,updated_at=clock_timestamp() where id=t.id returning attempts into n;
  end if;
  insert into public.research_builder_calls(study_id,task_id,dispatch_id,number,prompt_version_id,model_id,request_artifact_id,request_sha256,request_bytes,reserved_cents)
   values(d.study_id,t.id,d.id,n,r.prompt_version_id,r.model_id,(p_payload->>'request_artifact_id')::uuid,p_payload->>'request_sha256',(p_payload->>'request_bytes')::integer,cents) returning * into c;
  return to_jsonb(c);
 elsif p_operation='finish' then
  select * into strict c from public.research_builder_calls where id=(p_payload->>'id')::uuid and dispatch_id=d.id for update;
  if c.status<>'running' then raise exception 'Terminal native response cannot be overwritten'; end if;
  if p_payload->>'response_artifact_id' is not null and not exists(select 1 from public.research_artifacts where study_id=d.study_id and id=(p_payload->>'response_artifact_id')::uuid and sha256=p_payload->>'response_sha256') then raise exception 'Stored original native response with exact byte hash required'; end if;
  update public.research_builder_calls set status=p_payload->>'status',response_artifact_id=(p_payload->>'response_artifact_id')::uuid,response_sha256=p_payload->>'response_sha256',
   usage=p_payload->'usage',response_received=(p_payload->>'response_received')::boolean,http_status=(p_payload->>'http_status')::integer,reason=p_payload->>'reason',ended_at=clock_timestamp() where id=c.id returning * into c;
  return to_jsonb(c);
 end if; raise exception 'Unknown builder call operation';
end $$;
revoke all on function public.research_builder_call(text,jsonb),public.research_builder_call_immutable() from public,anon,authenticated;
grant execute on function public.research_builder_call(text,jsonb) to service_role;

-- Extend only the prompt-module guard for the new stage, leaving all original
-- ownership, fencing, budget/deadline and immutable turn checks in place.
do $migration$ declare definition text; old text; begin
 -- The paper-confirmation migration wraps the original fenced controller.
 definition=pg_get_functiondef('public.research_autonomy_before_confirmation(text,uuid,uuid,jsonb)'::regprocedure);
 old=$old$v.module_id='research-autonomy' and v.published_at is not null$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected autonomous prompt admission definition'; end if;
 execute replace(definition,old,$new$v.module_id=case when t.stage='building' then 'research-experiment-builder' else 'research-autonomy' end and v.published_at is not null$new$);
end $migration$;

alter table public.research_network_executions drop constraint research_network_executions_runner_check;
alter table public.research_network_executions add constraint research_network_executions_runner_check
 check(runner in ('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1','netem-iperf-v1','source-arithmetic-v1','built-package-v1'));
do $migration$ declare definition text; old text; begin
 definition=pg_get_functiondef('public.research_queue_enqueue(uuid,uuid,uuid,jsonb,text)'::regprocedure);
 old=$old$('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1','netem-iperf-v1','source-arithmetic-v1')$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected executable queue runner allowlist'; end if;
 execute replace(definition,old,$new$('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1','netem-iperf-v1','source-arithmetic-v1','built-package-v1')$new$);
end $migration$;
notify pgrst,'reload schema';
commit;
