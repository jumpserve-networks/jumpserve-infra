begin;
-- Supplement original unknown calls with verified retained completions. Never
-- overwrite the original outcome, reserve again, or infer that an absent stream
-- means that a provider was not invoked.
create table public.research_builder_call_reconciliations (
 call_id uuid primary key references public.research_builder_calls(id),
 dispatch_id uuid not null references public.research_model_dispatches(id),
 study_id uuid not null,task_id uuid not null,request_sha256 text not null,
 artifact_id uuid not null,sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
 response_artifact_id uuid not null,response_sha256 text not null check(response_sha256 ~ '^[a-f0-9]{64}$'),
 proof jsonb not null,created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 foreign key(study_id,artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,response_artifact_id) references public.research_artifacts(study_id,id)
);
alter table public.research_builder_call_reconciliations enable row level security;
revoke all on public.research_builder_call_reconciliations from public,anon,authenticated,service_role;
grant select on public.research_builder_call_reconciliations to service_role;
create trigger research_builder_call_reconciliations_immutable before update or delete on public.research_builder_call_reconciliations
 for each row execute function public.research_immutable();

create function public.research_builder_call_reconcile(p_call uuid,p_artifact uuid,p_sha256 text,p_proof jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare c public.research_builder_calls;d public.research_model_dispatches;t public.research_autonomy_tasks;r public.research_builder_call_reconciliations;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict c from public.research_builder_calls where id=p_call for update;
 select * into r from public.research_builder_call_reconciliations where call_id=c.id;
 if found then
  if (r.artifact_id,r.sha256,r.proof) is distinct from (p_artifact,p_sha256,p_proof) then raise exception 'Original native reconciliation is immutable';end if;
  return to_jsonb(r);
 end if;
 select * into strict d from public.research_model_dispatches where id=c.dispatch_id for update;
 select * into strict t from public.research_autonomy_tasks where id=c.task_id and study_id=c.study_id for update;
 if c.status<>'unknown' or d.status not in ('unknown','failed','invalid-output') or t.status='running'
  or not (d.request_raw::jsonb ? 'builder') or d.study_id<>c.study_id or d.task_id<>c.task_id
  or exists(select 1 from public.research_model_dispatches live where live.task_id=t.id and live.status in ('queued','running'))
  or exists(select 1 from public.research_autonomy_turns turn where turn.task_id=t.id and turn.status='running')
  then raise exception 'Quiescent original unknown native call required';end if;
 if p_proof->>'version' is distinct from 'builder-native-call-reconciliation-v1'
  or p_proof->>'call_id' is distinct from c.id::text or p_proof->>'dispatch_id' is distinct from d.id::text
  or p_proof->>'task_id' is distinct from c.task_id::text or p_proof->>'study_id' is distinct from c.study_id::text
  or p_proof->>'request_sha256' is distinct from c.request_sha256 or p_proof->>'original_status' is distinct from c.status
  or p_proof->>'status' is distinct from 'complete' or p_proof->>'response_received' is distinct from 'true'
  or p_proof->>'http_status' is distinct from '200' or p_proof->>'container_cleanup' is distinct from 'stopped'
  or p_proof->'response'->>'sha256' is distinct from p_proof->>'response_sha256'
  or (c.response_sha256 is not null and c.response_sha256 is distinct from p_proof->>'response_sha256')
  then raise exception 'Exact original native completion proof required';end if;
 if not exists(select 1 from public.research_artifacts where study_id=c.study_id and id=p_artifact and sha256=p_sha256
   and provenance->>'kind'='builder-native-call-reconciliation' and provenance->>'dispatch_id'=d.id::text)
  or not exists(select 1 from public.research_artifacts where study_id=c.study_id and id=(p_proof->'response'->>'artifact_id')::uuid and sha256=p_proof->>'response_sha256'
   and provenance->>'kind'='builder-reconciled-native-response' and provenance->>'dispatch_id'=d.id::text)
  or not exists(select 1 from public.research_artifacts where study_id=c.study_id and id=(p_proof->'completion'->>'artifact_id')::uuid and sha256=p_proof->'completion'->>'sha256'
   and provenance->>'kind'='builder-reconciled-native-completion' and provenance->>'dispatch_id'=d.id::text)
  then raise exception 'Stored original response, completion receipt and proof required';end if;
 insert into public.research_builder_call_reconciliations(call_id,dispatch_id,study_id,task_id,request_sha256,artifact_id,sha256,response_artifact_id,response_sha256,proof)
 values(c.id,d.id,c.study_id,c.task_id,c.request_sha256,p_artifact,p_sha256,(p_proof->'response'->>'artifact_id')::uuid,p_proof->>'response_sha256',p_proof) returning * into r;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(c.study_id,c.task_id,'native-call-reconciled',
  jsonb_build_object('call_id',c.id,'dispatch_id',d.id,'request_sha256',c.request_sha256,'artifact_id',p_artifact,'sha256',p_sha256,'scientific_completion',false));
 return to_jsonb(r);
end $$;

create function public.research_builder_unresolved(p_task uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.research_builder_calls c where c.task_id=p_task and
  (c.status='running' or (c.status='unknown' and not exists(select 1 from public.research_builder_call_reconciliations r
   where r.call_id=c.id and r.dispatch_id=c.dispatch_id and r.task_id=c.task_id and r.study_id=c.study_id and r.request_sha256=c.request_sha256))))
$$;
revoke all on function public.research_builder_call_reconcile(uuid,uuid,text,jsonb),public.research_builder_unresolved(uuid) from public,anon,authenticated;
grant execute on function public.research_builder_call_reconcile(uuid,uuid,text,jsonb),public.research_builder_unresolved(uuid) to service_role;

-- Existing admission/recovery gates accept only these exact supplemental
-- identities. Running work and original unknowns without proof remain fenced.
do $migration$ declare signature text;definition text;old text;begin
 foreach signature in array array['public.research_builder_call(text,jsonb)','public.research_autonomy_repair(text,uuid,uuid,uuid,jsonb)',
  'public.research_model_reconcile(uuid,uuid,text,jsonb)','public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text)'] loop
  definition=pg_get_functiondef(signature::regprocedure);
  old='exists(select 1 from public.research_builder_calls where task_id=t.id and status in (''running'',''unknown''))';
  if strpos(definition,old)>0 then definition=replace(definition,old,'public.research_builder_unresolved(t.id)');
  else
   old='exists(select 1 from public.research_builder_calls c where c.task_id=t.id and c.status in (''running'',''unknown''))';
   if strpos(definition,old)=0 then raise exception 'Unexpected native reconciliation guard: %',signature;end if;
   definition=replace(definition,old,'public.research_builder_unresolved(t.id)');
  end if;
  execute definition;
 end loop;
 definition=pg_get_functiondef('public.research_model_reconcile(uuid,uuid,text,jsonb)'::regprocedure);
 old='and b.status=''complete'' and b.http_status=200 and b.response_received is true and b.request_sha256=c.request_sha256 and b.response_sha256=c.response_sha256';
 if strpos(definition,old)=0 then raise exception 'Unexpected original completed-call gate';end if;
 execute replace(definition,old,$new$and b.request_sha256=c.request_sha256 and ((b.status='complete' and b.http_status=200 and b.response_received is true and b.response_sha256=c.response_sha256)
  or exists(select 1 from public.research_builder_call_reconciliations nr where nr.call_id=b.id and nr.dispatch_id=b.dispatch_id and nr.task_id=b.task_id and nr.study_id=b.study_id and nr.request_sha256=b.request_sha256 and nr.response_sha256=c.response_sha256))$new$);
end $migration$;

create or replace function public.research_model_reconciliation_candidates(p_after uuid default null) returns setof jsonb
language sql stable security definer set search_path='' as $$
 select to_jsonb(d) from public.research_model_dispatches d join public.research_autonomy_tasks t on t.id=d.task_id and t.study_id=d.study_id
 where d.status in ('unknown','failed','invalid-output') and d.request_raw::jsonb ? 'builder' and (p_after is null or d.id>p_after)
 and t.status<>'running' and not exists(select 1 from public.research_autonomy_turns turn where turn.task_id=t.id and turn.status='running')
 and not exists(select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id)
 and not exists(select 1 from public.research_builder_calls c where c.task_id=t.id and c.status='running')
 and not exists(select 1 from public.research_model_dispatches live where live.task_id=t.id and live.status in ('queued','running'))
 order by d.id limit 8
$$;
notify pgrst,'reload schema';
commit;
