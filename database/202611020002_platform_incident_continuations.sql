begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- An attempt's six-hour window is not the lifetime of the owner's assessment.
-- Append bounded attempts; never renew an old task or erase its reservations.
create table public.platform_assessment_repair_attempts (
 id uuid primary key default gen_random_uuid(),
 blocker_id uuid not null references public.platform_assessment_blockers(id),
 root_task_id uuid not null references public.platform_tasks(id),
 previous_task_id uuid not null unique references public.platform_tasks(id),
 platform_task_id uuid not null unique references public.platform_tasks(id),
 generation integer not null check(generation>0),
 evidence_revision text not null check(evidence_revision ~ '^[a-f0-9]{64}$'),
 carried_cents integer not null check(carried_cents>=0),
 carried_calls integer not null check(carried_calls>=0),
 proof jsonb not null,created_at timestamptz not null default clock_timestamp(),
 unique(blocker_id,generation)
);
alter table public.platform_assessment_repair_attempts enable row level security;
revoke all on public.platform_assessment_repair_attempts from public,anon,authenticated,service_role;
grant select on public.platform_assessment_repair_attempts to service_role;
create trigger repair_attempt_immutable before update or delete on public.platform_assessment_repair_attempts
 for each row execute function public.platform_immutable();
create view public.platform_assessment_repair_bindings as
 select blocker_id,platform_task_id,created_at from public.platform_assessment_repair_links
 union all select blocker_id,platform_task_id,created_at from public.platform_assessment_repair_attempts;
revoke all on public.platform_assessment_repair_bindings from public,anon,authenticated,service_role;

-- The existing context, parent-stop, closure, host and budget gates must see
-- every attempt. Original one-to-one links stay immutable and retain identity.
do $$declare r record;definition text;begin
 for r in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.prokind='f' and p.prosrc like '%public.platform_assessment_repair_links%'
 loop
  definition=pg_get_functiondef(r.oid);
  definition=replace(definition,'public.platform_assessment_repair_links','public.platform_assessment_repair_bindings');
  definition=replace(definition,'where p.status=''blocked'' and not p.cancel_requested',
   'where p.status=''blocked'' and not exists(select 1 from public.platform_assessment_repair_attempts next_attempt where next_attempt.previous_task_id=p.id) and not p.cancel_requested');
  execute replace(definition,'insert into public.platform_assessment_repair_bindings','insert into public.platform_assessment_repair_links');
 end loop;
end$$;

alter function public.platform_repair_context_data(uuid) rename to platform_repair_context_before_continuations_v9;
revoke all on function public.platform_repair_context_before_continuations_v9(uuid) from public,anon,authenticated,service_role;
create function public.platform_repair_context_data(p_task uuid) returns jsonb
language sql stable security definer set search_path='' as $$
 select public.platform_repair_context_before_continuations_v9(p_task)||jsonb_build_object(
  'continuation_contract','platform-incident-continuation-v1',
  'incident_continuation',(select a.proof||jsonb_build_object('platform_task_id',a.platform_task_id,
   'predecessor_failure',(select jsonb_build_object('version',p.checkpoint->'supervisor_failure'->'version',
    'error_type',p.checkpoint->'supervisor_failure'->'error_type','frames',p.checkpoint->'supervisor_failure'->'frames',
    'fingerprint',p.checkpoint->'supervisor_failure'->'fingerprint','original_artifact_id',p.checkpoint->'supervisor_failure'->'original_artifact_id')
    from public.platform_tasks p where p.id=a.previous_task_id and p.checkpoint?'supervisor_failure'),
   'predecessor_operations',(select coalesce(jsonb_agg(jsonb_build_object('id',o.id,'kind',o.kind,'status',o.status,
    'request_sha256',o.request_sha256,'component',o.request->'component','revision',o.request->'revision',
    'workflow_run_id',o.result->'workflow_run_id','conclusion',o.result->'conclusion','production_revision_verified',o.result->'production_revision_verified') order by o.created_at),'[]')
    from (select * from public.platform_operations where task_id=a.previous_task_id and status='failed' order by created_at desc limit 8)o),
   'predecessor_checkpoint',(select jsonb_build_object('task_id',p.id,'artifact_id',x.id,'sha256',x.sha256,'byte_count',x.byte_count,'storage_path',x.storage_path)
    from public.platform_tasks p join public.platform_artifacts x on x.task_id=p.id
     and x.sha256=p.checkpoint->'working_artifact'->>'sha256'
     and x.storage_path=p.checkpoint->'working_artifact'->>'path'
    where p.id=a.previous_task_id and x.name='working-checkpoint.zip'))
   from public.platform_assessment_repair_attempts a where a.platform_task_id=p_task))
$$;

create function public.platform_repair_family(p_task uuid) returns table(task_id uuid)
language sql stable security definer set search_path='' as $$
 with root as (
  select coalesce((select root_task_id from public.platform_assessment_repair_attempts where platform_task_id=p_task),p_task) id
 ) select id from root union all select a.platform_task_id from public.platform_assessment_repair_attempts a join root r on r.id=a.root_task_id
$$;

create function public.platform_continue_assessment_incidents() returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.platform_settings;b public.platform_assessment_blockers;root public.platform_tasks;
 parent public.platform_tasks;w public.research_autonomy_workflows;t public.research_autonomy_tasks;
 previous public.platform_assessment_repair_attempts;packet jsonb;baseline text;ident uuid;
 spent integer;calls integer;generation integer;admitted jsonb='[]';proof jsonb;
 evidence_revision text;failures jsonb;faults jsonb;settled_calls jsonb;begin
 select * into strict s from public.platform_settings where id;
 if s.paused then return admitted;end if;
 for b in select signal.* from public.platform_assessment_blockers signal
  join public.platform_assessment_repair_links l on l.blocker_id=signal.id
  where not exists(select 1 from public.platform_assessment_incident_closures c where c.blocker_id=signal.id)
  order by signal.created_at,signal.id
 loop
  exit when jsonb_array_length(admitted)>=8;
  select * into strict root from public.platform_tasks where id=(select platform_task_id from public.platform_assessment_repair_links where blocker_id=b.id);
  select * into previous from public.platform_assessment_repair_attempts where blocker_id=b.id order by generation desc limit 1;
  select * into strict parent from public.platform_tasks where id=coalesce(previous.platform_task_id,root.id) for update;
  if parent.status not in ('deadline','completed','blocked') or parent.lease_token is not null
   or parent.cancel_requested or root.cancel_requested or root.status='cancelled'
   or parent.authorization_version is distinct from s.authorization_version then continue;end if;
  select * into strict w from public.research_autonomy_workflows where study_id=b.study_id;
  select * into strict t from public.research_autonomy_tasks where id=b.assessment_task_id and study_id=b.study_id;
  if w.status not in ('running','completed-with-blockers') or w.deadline_at<=statement_timestamp()+interval '180 seconds'
   or w.max_spend_cents is not null and w.committed_cents>=w.max_spend_cents
   or t.status in ('resolved','finished','cancelled','budget','deadline','attempt-limit')
   or public.platform_assessment_incident_resolution(b.id) is not null then continue;end if;
  -- One live investigation per claim, even when several historical incidents
  -- described the same failed call. No uncertain original action is displaced.
  if exists(select 1 from public.platform_assessment_repair_bindings l
    join public.platform_assessment_blockers other_b on other_b.id=l.blocker_id
    join public.platform_tasks p on p.id=l.platform_task_id
    where other_b.assessment_task_id=t.id and
     (p.cancel_requested or p.status='cancelled' or p.lease_token is not null
      or p.status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling')))
   or exists(select 1 from public.platform_repair_family(root.id) f join public.platform_tasks p on p.id=f.task_id where p.checkpoint->>'cleanup_unknown'='true')
   or exists(select 1 from public.platform_repair_family(root.id) f join public.platform_operations o on o.task_id=f.task_id where o.status in ('pending','unknown'))
   or exists(select 1 from public.platform_repair_family(root.id) f join public.platform_runs r on r.task_id=f.task_id
     where r.status='running' or r.status='unknown' and not exists(select 1 from public.platform_run_reconciliations x where x.run_id=r.id)) then continue;end if;
  -- Always fingerprint the original binding: a new attempt ID and polling
  -- clocks cannot themselves become new scientific/operational evidence.
  packet=public.platform_repair_context_data(root.id);
  if packet is null or packet->>'evidence_revision' !~ '^[a-f0-9]{64}$' then continue;end if;
  select coalesce(jsonb_agg(jsonb_build_object('id',o.id,'request_sha256',o.request_sha256,'result',o.result) order by o.id),'[]') into failures
   from public.platform_repair_family(root.id) f join public.platform_operations o on o.task_id=f.task_id where o.status='failed';
  select coalesce(jsonb_agg(value order by value),'[]') into faults from (select distinct p.checkpoint->'supervisor_failure'->>'fingerprint' value
   from public.platform_repair_family(root.id) f join public.platform_tasks p on p.id=f.task_id
   where p.checkpoint->'supervisor_failure'->>'version'='platform-supervisor-failure-v1'
    and p.checkpoint->'supervisor_failure'->>'fingerprint' ~ '^[a-f0-9]{64}$') x;
  select coalesce(jsonb_agg(jsonb_build_object('run_id',r.run_id,'proof',r.proof) order by r.run_id),'[]') into settled_calls
   from public.platform_repair_family(root.id) f join public.platform_run_reconciliations r on r.task_id=f.task_id;
  -- Failed releases and trusted controller faults are concrete new evidence;
  -- repetitions, timers and ordinary model-call counts are not.
  if parent.status='blocked' and parent.deadline_at>statement_timestamp() and failures='[]'::jsonb and faults='[]'::jsonb then continue;end if;
  evidence_revision=encode(sha256(convert_to(jsonb_build_object('research',packet->>'evidence_revision',
   'failed_operations',failures,'controller_faults',faults,'settled_original_calls',settled_calls)::text,'UTF8')),'hex');
  baseline=coalesce(previous.evidence_revision,root.checkpoint->'repair_guard'->>'evidence_revision');
  if evidence_revision is not distinct from baseline then continue;end if;
  select coalesce(sum(r.reserved_cents),0),count(*) into spent,calls
   from public.platform_repair_family(root.id) f join public.platform_runs r on r.task_id=f.task_id;
  if not public.autonomy_budget_allows('platform_repair',spent,calls,100,1) then continue;end if;
  generation=coalesce(previous.generation,0)+1;ident=gen_random_uuid();
  proof=jsonb_build_object('version','platform-incident-continuation-v1','blocker_id',b.id,'root_task_id',root.id,
   'previous_task_id',parent.id,'previous_status',parent.status,'previous_deadline_at',parent.deadline_at,
   'assessment_id',w.study_id,'assessment_deadline_at',w.deadline_at,'evidence_revision',evidence_revision,'research_evidence_revision',packet->>'evidence_revision',
   'generation',generation,'carried_cents',spent,'carried_calls',calls,'owner_authorization',s.authorization_version,
   'original_task_modified',false,'uncertain_call_replay',false,'scientific_completion',false);
  insert into public.platform_tasks(id,requested_by,title,objective,repositories,authorization_version,priority,budget_category,
   max_reserved_cents,committed_cents,deadline_at,checkpoint)
  values(ident,root.requested_by,'Continue assessment '||left(w.study_id::text,8)||' recovery',
   root.objective||E'\nContinue the unresolved incident under the existing owner mandate. This is a new bounded operational attempt; preserve all original task outcomes and assessment limits. Inspect the continuation history and retained predecessor checkpoint before coding. Reconcile unknown research calls from original evidence; never replay them. Missing tools, self-repair and release capabilities are implementation work, not missing owner authorization.',
   root.repositories,s.authorization_version,0,'platform_repair',-1,spent,least(w.deadline_at,statement_timestamp()+interval '6 hours'),
   jsonb_build_object('incident_continuation',proof));
  insert into public.platform_assessment_repair_attempts(blocker_id,root_task_id,previous_task_id,platform_task_id,generation,evidence_revision,carried_cents,carried_calls,proof)
   values(b.id,root.id,parent.id,ident,generation,evidence_revision,spent,calls,proof);
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),ident,'assessment-monitor','assessment-repair-continued',
   'Unresolved assessment incident received a bounded follow-up under standing authority. Original tasks, assessment deadline, reservations and uncertain outcomes are retained.',proof);
  admitted=admitted||jsonb_build_array(ident);
 end loop;
 return admitted;
end$$;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_continuations_v9;
revoke all on function public.platform_worker_before_continuations_v9(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;s public.platform_settings;admitted jsonb;spent integer;calls integer;begin
 if p_operation in ('maintenance','begin-run','lease') then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 end if;
 if p_operation='maintenance' then
  select * into strict s from public.platform_settings where id;
  if p_worker is null or jsonb_typeof(p_payload) is distinct from 'object' or not exists(
   select 1 from public.platform_authorizations where version=s.authorization_version and policy_sha256=p_payload->>'policy_sha256') then raise exception 'Current worker policy required';end if;
  admitted=public.platform_continue_assessment_incidents();
 end if;
 if p_operation='begin-run' and exists(select 1 from public.platform_assessment_repair_attempts where platform_task_id=p_task) then
  -- Validate the current live token before returning even a denied admission.
  perform public.platform_worker_before_continuations_v9('lease',p_worker,p_task,p_token,'{}');
  select coalesce(sum(r.reserved_cents),0),count(*) into spent,calls from public.platform_repair_family(p_task) f join public.platform_runs r on r.task_id=f.task_id;
  if not public.autonomy_budget_allows('platform_repair',spent,calls,100,1) then return jsonb_build_object('denied','budget');end if;
 end if;
 result=public.platform_worker_before_continuations_v9(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation='maintenance' and jsonb_array_length(admitted)>0 then
  return coalesce(result,'{}')||jsonb_build_object('assessment_repair_continuations',admitted);
 elsif p_operation='lease' and exists(select 1 from public.platform_assessment_repair_attempts where platform_task_id=p_task) then
  select coalesce(sum(r.reserved_cents),0),count(*) into spent,calls from public.platform_repair_family(p_task) f join public.platform_runs r on r.task_id=f.task_id;
  return result||jsonb_build_object('committed_cents',spent,'model_calls',calls);
 end if;
 return result;
end$$;
revoke all on function public.platform_repair_family(uuid),public.platform_continue_assessment_incidents() from public,anon,authenticated,service_role;
revoke all on function public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
