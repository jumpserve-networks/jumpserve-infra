begin;
-- Append-only supplemental proof. Original dispatches, native calls, controller
-- outcomes and commitments are never rewritten by reconciliation.
create table public.research_model_reconciliations(
 dispatch_id uuid primary key references public.research_model_dispatches(id),
 study_id uuid not null,task_id uuid not null,request_sha256 text not null,
 artifact_id uuid not null,sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
 proof jsonb not null,created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 foreign key(study_id,artifact_id) references public.research_artifacts(study_id,id)
);
alter table public.research_model_reconciliations enable row level security;
revoke all on public.research_model_reconciliations from public,anon,authenticated,service_role;
grant select on public.research_model_reconciliations to service_role;
create trigger research_model_reconciliations_immutable before update or delete on public.research_model_reconciliations for each row execute function public.research_immutable();

create function public.research_model_reconcile(p_dispatch uuid,p_artifact uuid,p_sha256 text,p_proof jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_tasks;r public.research_model_reconciliations;c record;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict d from public.research_model_dispatches where id=p_dispatch for update;
 select * into r from public.research_model_reconciliations where dispatch_id=d.id;
 if found then
  if (r.artifact_id,r.sha256,r.proof) is distinct from (p_artifact,p_sha256,p_proof) then raise exception 'Reconciliation original is immutable';end if;
  return to_jsonb(r);
 end if;
 select * into strict t from public.research_autonomy_tasks where id=d.task_id for update;
 if d.status not in ('unknown','failed','invalid-output') or t.status='running'
  or not ((d.request_raw::jsonb) ? 'builder')
  or exists(select 1 from public.research_model_dispatches where task_id=t.id and status in ('queued','running'))
  or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status='running')
  or exists(select 1 from public.research_builder_calls where task_id=t.id and status in ('running','unknown'))
  then raise exception 'No active or uncertain native work may be reconciled';end if;
 if p_proof->>'version' is distinct from 'builder-dispatch-reconciliation-v1'
  or p_proof->>'dispatch_id' is distinct from d.id::text
  or p_proof->>'request_sha256' is distinct from d.request_sha256
  or p_proof->>'original_status' is distinct from d.status
  or p_proof->>'container_cleanup' is distinct from 'stopped'
  or jsonb_typeof(p_proof->'calls') is distinct from 'array'
  then raise exception 'Exact builder identity and cleanup proof required';end if;
 -- The worker verifies canonical bytes after retrieval. Bind their original
 -- artifact here; PostgreSQL jsonb rendering is a different byte encoding.
 if not exists(select 1 from public.research_artifacts where study_id=d.study_id and id=p_artifact and sha256=p_sha256
    and provenance->>'kind'='builder-dispatch-reconciliation' and provenance->>'dispatch_id'=d.id::text)
    then raise exception 'Stored original reconciliation artifact required';end if;
 if jsonb_array_length(p_proof->'calls')<>(select count(*) from public.research_builder_calls where dispatch_id=d.id)
  or (select count(distinct item->>'id') from jsonb_array_elements(p_proof->'calls') item)<>jsonb_array_length(p_proof->'calls')
  then raise exception 'Complete distinct native call coverage required';end if;
 for c in select * from jsonb_to_recordset(p_proof->'calls') as x(id uuid,request_sha256 text,response_sha256 text) loop
  if not exists(select 1 from public.research_builder_calls b where b.id=c.id and b.dispatch_id=d.id and b.task_id=t.id and b.study_id=d.study_id
    and b.status='complete' and b.http_status=200 and b.response_received is true and b.request_sha256=c.request_sha256 and b.response_sha256=c.response_sha256)
    then raise exception 'Original native request and completed response required';end if;
 end loop;
 if not exists(select 1 from public.research_artifacts where study_id=d.study_id and id=(p_proof->'checkpoint'->>'artifact_id')::uuid
    and sha256=p_proof->'checkpoint'->>'sha256' and provenance->>'kind'='builder-reconciled-workspace' and provenance->>'dispatch_id'=d.id::text)
    then raise exception 'Stored reconciled checkpoint required';end if;
 insert into public.research_model_reconciliations(dispatch_id,study_id,task_id,request_sha256,artifact_id,sha256,proof)
 values(d.id,d.study_id,d.task_id,d.request_sha256,p_artifact,p_sha256,p_proof) returning * into r;
 insert into public.research_autonomy_events(study_id,task_id,event,details)
 values(d.study_id,d.task_id,'model-dispatch-reconciled',jsonb_build_object('dispatch_id',d.id,'original_status',d.status,'artifact_id',p_artifact,'sha256',p_sha256,'native_calls',jsonb_array_length(p_proof->'calls'),'scientific_completion',false));
 return to_jsonb(r);
end $$;
revoke all on function public.research_model_reconcile(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.research_model_reconcile(uuid,uuid,text,jsonb) to service_role;
create function public.research_model_reconciliation_candidates(p_after uuid default null) returns setof jsonb
language sql stable security definer set search_path='' as $$
 select to_jsonb(d) from public.research_model_dispatches d
 join public.research_autonomy_tasks t on t.id=d.task_id and t.study_id=d.study_id
 where d.status in ('unknown','failed','invalid-output') and d.request_raw::jsonb ? 'builder' and (p_after is null or d.id>p_after)
 and t.status<>'running'
 and not exists(select 1 from public.research_autonomy_turns turn where turn.task_id=t.id and turn.status='running')
 and not exists(select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id)
 and not exists(select 1 from public.research_builder_calls c where c.task_id=t.id and c.status in ('running','unknown'))
 and not exists(select 1 from public.research_model_dispatches live where live.task_id=t.id and live.status in ('queued','running'))
 order by d.id limit 8
$$;
revoke all on function public.research_model_reconciliation_candidates(uuid) from public,anon,authenticated;
grant execute on function public.research_model_reconciliation_candidates(uuid) to service_role;
notify pgrst,'reload schema';
commit;
