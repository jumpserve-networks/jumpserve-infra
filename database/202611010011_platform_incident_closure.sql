begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Closure is an operational fact, never a qualified code change or a finding.
-- Original blockers, repair outcomes, runs and release records stay immutable.
create table public.platform_assessment_incident_closures (
 blocker_id uuid primary key references public.platform_assessment_blockers(id),
 proof jsonb not null, created_at timestamptz not null default clock_timestamp()
);
alter table public.platform_assessment_incident_closures enable row level security;
revoke all on public.platform_assessment_incident_closures from public,anon,authenticated,service_role;
grant select on public.platform_assessment_incident_closures to service_role;
create trigger incident_closure_immutable before update or delete on public.platform_assessment_incident_closures
 for each row execute function public.platform_immutable();

create function public.platform_assessment_incident_resolution(p_blocker uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare b public.platform_assessment_blockers;t public.research_autonomy_tasks;
 r public.research_autonomy_repairs;d public.research_model_dispatches;w public.research_autonomy_workflows;
 witness record;failed text;begin
 select * into b from public.platform_assessment_blockers where id=p_blocker;if not found then return null;end if;
 select * into strict t from public.research_autonomy_tasks where id=b.assessment_task_id and study_id=b.study_id;
 select * into strict w from public.research_autonomy_workflows where study_id=b.study_id;
 if t.status not in ('queued','running','resolved','finished') or w.status not in ('running','completed-with-blockers','completed')
  or w.deadline_at<=statement_timestamp() then return null;end if;
 select * into r from public.research_autonomy_repairs x where x.study_id=b.study_id and x.task_id=t.id and x.state='resolved'
  and x.evidence->'validated'='true'::jsonb and x.original_stage=b.stage
  and t.context->'repair_progress'->>'id'=x.id::text and t.context->'repair_progress'->>'state'='resolved'
  and t.context->'repair_progress'->>'revision'=x.revision::text
  and ((b.source_kind='repair' and b.source_id=x.id)
   or (b.source_kind='dispatch' and x.incident_raw::jsonb->>'failed_turn_id'=b.source_id::text)
   or (b.source_kind='task' and b.source_id=t.id and encode(sha256(convert_to(x.incident_raw::jsonb->>'reason','UTF8')),'hex')=b.original_reason_sha256))
 order by x.updated_at desc,x.id limit 1;
 if not found or not exists(select 1 from public.research_autonomy_repair_events e where e.repair_id=r.id and e.task_id=t.id
  and e.study_id=b.study_id and e.revision=r.revision and e.state='resolved' and e.details->'evidence'=r.evidence)
  or exists(select 1 from public.research_autonomy_repairs where task_id=t.id and state in ('diagnosing','repairing','validating','resuming','waiting'))
  or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status in ('running','unknown'))
  or exists(select 1 from public.research_builder_calls where task_id=t.id and status in ('running','unknown'))
  or exists(select 1 from public.research_model_dispatches where task_id=t.id and status in ('queued','running','unknown'))
 then return null;end if;
 failed=r.incident_raw::jsonb->>'failed_turn_id';
 if failed is not null then
  if failed!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' then return null;end if;
  select * into d from public.research_model_dispatches where id=failed::uuid and study_id=b.study_id and task_id=t.id;
  if not found or not public.research_controller_dispatch_accounted(d) then return null;end if;
 end if;
 select x.id,x.number,x.request_sha256,x.response_sha256,m.response_artifact_id,m.response_sha256 artifact_sha256 into witness
 from public.research_autonomy_turns x join public.research_model_dispatches m on m.id=x.id and m.task_id=x.task_id and m.study_id=x.study_id
 join public.research_artifacts a on a.id=m.response_artifact_id and a.study_id=m.study_id and a.sha256=m.response_sha256
 where x.task_id=t.id and x.study_id=b.study_id and x.status='complete' and x.ended_at is not null and x.response_sha256 is not null
  and x.created_at>r.updated_at and x.created_at>b.created_at and x.model_id='gpt-6.1-sol'
  and m.status='complete' and m.request_sha256=x.request_sha256
 order by x.created_at,x.id limit 1;
 if not found then return null;end if;
 return jsonb_build_object('version','platform-incident-closure-v1','blocker_id',b.id,'assessment_id',b.study_id,'assessment_task_id',t.id,
  'source_kind',b.source_kind,'source_id',b.source_id,'repair_id',r.id,'repair_revision',r.revision,'incident_sha256',r.incident_sha256,
  'continuation_turn_id',witness.id,'continuation_request_sha256',witness.request_sha256,'continuation_response_sha256',witness.response_sha256,
  'continuation_artifact_id',witness.response_artifact_id,'continuation_artifact_sha256',witness.artifact_sha256,
  'outcome','resolved-with-recorded-continuation','qualified_platform_change',false,'scientific_completion',false,'provider_replay',false);
end$$;
revoke all on function public.platform_assessment_incident_resolution(uuid) from public,anon,authenticated,service_role;

create function public.platform_close_resolved_incidents(p_task uuid default null) returns void
language plpgsql security definer set search_path='' as $$
declare t public.platform_tasks;b public.platform_assessment_blockers;proof jsonb;inserted boolean;begin
 -- Called only beneath the authenticated worker wrapper with both locks held.
 for t in select p.* from public.platform_tasks p join public.platform_assessment_repair_links l on l.platform_task_id=p.id
  where (p_task is null and p.lease_token is null or p.id=p_task)
   and not p.cancel_requested and p.deadline_at>statement_timestamp()
   and p.authorization_version=(select authorization_version from public.platform_settings where id)
   and p.status in ('queued','investigating','implementing','testing','blocked')
   and coalesce(p.checkpoint->>'cleanup_unknown','false')<>'true'
   and not exists(select 1 from public.platform_runs x where x.task_id=p.id and x.status in ('running','unknown'))
   and not exists(select 1 from public.platform_operations x where x.task_id=p.id and x.status in ('pending','unknown'))
   and not exists(select 1 from public.platform_changes x where x.task_id=p.id)
   and not exists(select 1 from public.platform_releases x where x.task_id=p.id)
  order by p.updated_at,p.id limit 64 for update of p skip locked
 loop
  select signal.* into strict b from public.platform_assessment_repair_links l join public.platform_assessment_blockers signal on signal.id=l.blocker_id where l.platform_task_id=t.id;
  proof=public.platform_assessment_incident_resolution(b.id);if proof is null then continue;end if;
  insert into public.platform_assessment_incident_closures(blocker_id,proof) values(b.id,proof) on conflict(blocker_id) do nothing;
  inserted=found;
  if t.lease_token is null then
   update public.platform_tasks set status='completed',reason='Original operational incident resolved with recorded controller continuation; no platform change or scientific completion claimed.',updated_at=clock_timestamp() where id=t.id;
   insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'assessment-monitor','assessment-incident-closed',
    'The research controller resolved this exact incident and completed a subsequent recorded turn. No further platform coding call is needed; original evidence, limits and outcomes are retained.',proof);
  elsif inserted then
   insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'assessment-monitor','assessment-incident-closure-available',
    'Exact incident closure is available at the next safe worker boundary; no uncertain action is inferred complete.',proof);
  end if;
 end loop;
 -- Do not mint a new investigation for an old, already resolved outbox entry.
 for b in select signal.* from public.platform_assessment_blockers signal
  where not exists(select 1 from public.platform_assessment_repair_links l where l.blocker_id=signal.id)
   and not exists(select 1 from public.platform_assessment_incident_closures c where c.blocker_id=signal.id)
   and exists(select 1 from public.research_autonomy_repairs r where r.task_id=signal.assessment_task_id and r.state='resolved')
  order by signal.created_at,signal.id limit 64
 loop
  proof=public.platform_assessment_incident_resolution(b.id);
  if proof is not null then
   insert into public.platform_assessment_incident_closures(blocker_id,proof) values(b.id,proof) on conflict(blocker_id) do nothing;
   if found then insert into public.platform_events(id,actor,kind,message,details) values(gen_random_uuid(),'assessment-monitor','assessment-incident-closed',
    'A resolved historical incident with recorded continuation requires no new supervisor task.',proof);end if;
  end if;
 end loop;
end$$;
revoke all on function public.platform_close_resolved_incidents(uuid) from public,anon,authenticated,service_role;

create function public.platform_wake_working_evidence() returns void
language plpgsql security definer set search_path='' as $$begin
 -- One capability handoff for retained plans. The worker must verify the
 -- original bytes before a new coding call; file deletion cannot rearm it.
 with changed as (
  update public.platform_tasks p set status='investigating',checkpoint=checkpoint-'not_before',updated_at=clock_timestamp(),
   reason='Original checkpoint delivery is available; verify the retained bytes before further coding.'
  where p.status='blocked' and not p.cancel_requested and p.lease_token is null and p.deadline_at>statement_timestamp()
   and p.authorization_version=(select authorization_version from public.platform_settings where id)
   and p.checkpoint->>'working_evidence_contract' is distinct from 'platform-working-evidence-v1'
   and coalesce(p.checkpoint->>'cleanup_unknown','false')<>'true'
   and exists(select 1 from public.platform_assessment_repair_links l where l.platform_task_id=p.id)
   and exists(select 1 from public.platform_artifacts a where a.task_id=p.id and a.name='repair-source-refresh-plan.json')
   and not exists(select 1 from public.platform_runs x where x.task_id=p.id and x.status in ('running','unknown'))
   and not exists(select 1 from public.platform_operations x where x.task_id=p.id and x.status in ('pending','unknown'))
  returning p.id
 ) insert into public.platform_events(id,task_id,actor,kind,message,details)
  select gen_random_uuid(),id,'assessment-monitor','working-checkpoint-delivery-available',
   'The controller can now deliver a task-bound original working checkpoint locally; retained bytes must verify before coding. Original limits and deadlines are unchanged.',
   jsonb_build_object('version','platform-working-evidence-v1','provider_calls',0) from changed;
end$$;
revoke all on function public.platform_wake_working_evidence() from public,anon,authenticated,service_role;

-- Preserve the existing queue, policy, category, lease, uncertainty and host
-- checks. Only resolved immutable incidents are excluded from new triage.
do $$declare definition text;selector text;begin
 definition=pg_get_functiondef('public.platform_worker_before_category_budgets_v1(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 selector=$old$where not exists(select 1 from public.platform_assessment_repair_links l where l.blocker_id=signal.id)$old$;
 if strpos(definition,selector)=0 then raise exception 'Unexpected assessment outbox selector';end if;
 execute replace(definition,selector,selector||' and not exists(select 1 from public.platform_assessment_incident_closures c where c.blocker_id=signal.id)');
end$$;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_incident_closure_v7;
revoke all on function public.platform_worker_before_incident_closure_v7(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;s public.platform_settings;t public.platform_tasks;closed jsonb;begin
 if p_operation='checkpoint' and p_payload->>'status'='completed' and p_payload->'checkpoint' ? 'incident_closure' then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  result=public.platform_worker_before_incident_closure_v7('lease',p_worker,p_task,p_token,'{}');
  select * into strict t from public.platform_tasks where id=p_task for update;
  select c.proof||jsonb_build_object('platform_task_id',p_task) into closed from public.platform_assessment_repair_links l
   join public.platform_assessment_incident_closures c on c.blocker_id=l.blocker_id where l.platform_task_id=p_task;
  if closed is null or closed is distinct from p_payload->'checkpoint'->'incident_closure'
   or coalesce((result->>'paused')::boolean,true) or coalesce((result->>'cancel_requested')::boolean,true)
   or t.deadline_at<=clock_timestamp() or t.checkpoint->>'cleanup_unknown'='true'
   or (p_payload-array['status','reason','checkpoint'])<>'{}'::jsonb
   or jsonb_typeof(p_payload->'checkpoint') is distinct from 'object' or octet_length((p_payload->'checkpoint')::text)>1000000
   or exists(select 1 from public.platform_runs where task_id=p_task and status in ('running','unknown'))
   or exists(select 1 from public.platform_operations where task_id=p_task and status in ('pending','unknown'))
   or exists(select 1 from public.platform_changes where task_id=p_task)
   or exists(select 1 from public.platform_releases where task_id=p_task)
  then raise exception 'Exact quiescent no-change incident closure required';end if;
  update public.platform_tasks set status='completed',reason='Original operational incident resolved with recorded controller continuation; no platform change or scientific completion claimed.',
   checkpoint=t.checkpoint||jsonb_build_object('incident_closure',closed),lease_token=null,lease_until=null,updated_at=clock_timestamp() where id=p_task;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),p_task,'assessment-monitor','assessment-incident-closed',
   'The original worker stopped at a verified incident-closure boundary. No code change, release qualification or scientific conclusion is claimed.',closed);
  update public.platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until=clock_timestamp()+interval '60 seconds'
   where id and task_id=p_task and lease_token=p_token;
  if found then insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),p_task,'supervisor','host-turn-released',
   'Supervisor incident closed without a source change; research receives its normal admission window.',jsonb_build_object('research_window_seconds',60));end if;
  return jsonb_build_object('recorded',true,'incident_closed',true,'qualified_platform_change',false);
 end if;
 if p_operation in ('maintenance','claim','lease','begin-run','begin-operation') then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  if p_operation in ('lease','begin-run','begin-operation') then
   result=public.platform_worker_before_incident_closure_v7('lease',p_worker,p_task,p_token,'{}');
   if not coalesce((result->>'paused')::boolean,true) and not coalesce((result->>'cancel_requested')::boolean,true) then
    perform public.platform_close_resolved_incidents(p_task);
    select c.proof||jsonb_build_object('platform_task_id',p_task) into closed from public.platform_assessment_repair_links l
     join public.platform_assessment_incident_closures c on c.blocker_id=l.blocker_id where l.platform_task_id=p_task;
    if closed is not null then
     if p_operation='lease' then return result||jsonb_build_object('incident_closure',closed);end if;
     return jsonb_build_object('denied','incident-closed','incident_closure',closed);
    end if;
   end if;
   if p_operation='lease' then return result;end if;
  else
   select * into strict s from public.platform_settings where id;
   if p_worker is null or jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'Invalid platform worker request';end if;
   if not s.paused and s.authorization_version is not null then
    if not exists(select 1 from public.platform_authorizations where version=s.authorization_version and policy_sha256=p_payload->>'policy_sha256') then raise exception 'Installed policy differs from standing authorization';end if;
    perform public.platform_close_resolved_incidents();
    perform public.platform_wake_working_evidence();
   end if;
  end if;
 end if;
 return public.platform_worker_before_incident_closure_v7(p_operation,p_worker,p_task,p_token,p_payload);
end$$;
revoke all on function public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;

alter function public.platform_repair_context_data(uuid) rename to platform_repair_context_data_before_closure_v7;
revoke all on function public.platform_repair_context_data_before_closure_v7(uuid) from public,anon,authenticated,service_role;
create function public.platform_repair_context_data(p_task uuid) returns jsonb
language sql stable security definer set search_path='' as $$
 select public.platform_repair_context_data_before_closure_v7(p_task)||jsonb_build_object('working_checkpoint_delivery','platform-working-evidence-v1',
  'incident_closure',(select to_jsonb(c) from public.platform_assessment_repair_links l join public.platform_assessment_incident_closures c on c.blocker_id=l.blocker_id where l.platform_task_id=p_task))
$$;
revoke all on function public.platform_repair_context_data(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
