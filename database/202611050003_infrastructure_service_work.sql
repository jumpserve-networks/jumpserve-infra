begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

create table public.platform_service_work_requests (
 id uuid primary key,parent_task_id uuid not null references public.platform_tasks(id),
 implementation_task_id uuid not null unique references public.platform_tasks(id),
 profile text not null check(profile in ('assessment-evidence-v1','intake-parser-recovery-v1')),
 spec jsonb not null,spec_sha256 text not null check(spec_sha256~'^[a-f0-9]{64}$'),
 artifact_id uuid not null references public.platform_artifacts(id),created_at timestamptz not null default clock_timestamp(),
 unique(parent_task_id,spec_sha256),unique(parent_task_id,profile),check(parent_task_id<>implementation_task_id)
);
create table public.platform_service_work_activations (
 request_id uuid primary key references public.platform_service_work_requests(id),
 operation_id uuid not null unique references public.platform_operations(id),
 revision text not null check(revision~'^[a-f0-9]{40}$'),manifest_sha256 text not null check(manifest_sha256~'^[a-f0-9]{64}$'),
 verification jsonb not null,created_at timestamptz not null default clock_timestamp()
);
do $$declare n text;begin
 foreach n in array array['platform_service_work_requests','platform_service_work_activations'] loop
  execute format('alter table public.%I enable row level security',n);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',n);
  execute format('grant select on public.%I to service_role',n);
  execute format('create trigger %I before update or delete on public.%I for each row execute function public.platform_immutable()',n||'_immutable',n);
 end loop;
end $$;

create or replace function public.platform_capability_ancestors(p_task uuid) returns table(task_id uuid)
language sql stable security definer set search_path='' as $$
 with recursive edges(parent,child) as (
  select parent_task_id,implementation_task_id from public.platform_capability_requests
  union select parent_task_id,implementation_task_id from public.platform_service_work_requests
 ),parents(id) as (select p_task union select e.parent from edges e join parents p on e.child=p.id)
 select id from parents
$$;
create or replace function public.platform_repair_family(p_task uuid) returns table(task_id uuid)
language sql stable security definer set search_path='' as $$
 with recursive edges(parent,child) as (
  select root_task_id,platform_task_id from public.platform_assessment_repair_attempts
  union select parent_task_id,implementation_task_id from public.platform_capability_requests
  union select parent_task_id,implementation_task_id from public.platform_service_work_requests
 ),related(id) as (select p_task union select case when e.parent=r.id then e.child else e.parent end
  from related r join edges e on e.parent=r.id or e.child=r.id)
 select id from related
$$;
create or replace view public.platform_assessment_repair_bindings as
 with recursive edges(parent,child,created_at) as (
  select parent_task_id,implementation_task_id,created_at from public.platform_capability_requests
  union select parent_task_id,implementation_task_id,created_at from public.platform_service_work_requests
 ),bindings(blocker_id,platform_task_id,created_at) as (
  select blocker_id,platform_task_id,created_at from public.platform_assessment_repair_links
  union select blocker_id,platform_task_id,created_at from public.platform_assessment_repair_attempts
  union select b.blocker_id,e.child,e.created_at from bindings b join edges e on e.parent=b.platform_task_id)
 select blocker_id,platform_task_id,created_at from bindings;
revoke all on public.platform_assessment_repair_bindings from public,anon,authenticated,service_role;

create function public.platform_service_evidence(p_task uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare b public.platform_assessment_blockers;begin
 select x.* into b from public.platform_assessment_repair_bindings l join public.platform_assessment_blockers x on x.id=l.blocker_id
 where l.platform_task_id=p_task order by x.created_at desc,x.id limit 1;
 if not found then return null;end if;
 return jsonb_build_object('version','platform-assessment-service-evidence-v1','assessment_id',b.study_id,'assessment_task_id',b.assessment_task_id,
  'task',(select jsonb_build_object('id',id,'stage',stage,'status',status,'attempts',attempts,'reason',public.platform_assessment_diagnostic(reason),
   'reason_sha256',encode(sha256(convert_to(reason,'UTF8')),'hex'),
   'context',public.platform_repair_detail(context),'context_sha256',encode(sha256(convert_to(context::text,'UTF8')),'hex')) from public.research_autonomy_tasks where id=b.assessment_task_id),
  'workflow',(select jsonb_build_object('status',status,'deadline_at',deadline_at,'max_spend_cents',max_spend_cents,'max_attempts',max_attempts,'committed_cents',committed_cents) from public.research_autonomy_workflows where study_id=b.study_id),
  'review',(select jsonb_build_object('status',status,'revision',revision,'candidate_count',jsonb_array_length(seeds),'confirmed',confirmed_at is not null) from public.research_paper_reviews where study_id=b.study_id),
  'sources',coalesce((select jsonb_agg(to_jsonb(x)) from (select id,sha256,byte_count,access_status,review_status from public.research_sources where study_id=b.study_id order by created_at,id limit 20)x),'[]'),
  'artifacts',coalesce((select jsonb_agg(to_jsonb(x)) from (select id,sha256,byte_count,media_type,provenance->>'kind' kind from public.research_artifacts where study_id=b.study_id
    and provenance->>'kind' in ('failed-text-extraction','derived-pdf-text','paper-original-upload','paper-original') order by created_at desc,id limit 20)x),'[]'),
  'schema',(select jsonb_object_agg(table_name,cols) from (select table_name,jsonb_agg(column_name order by ordinal_position) cols from information_schema.columns
    where table_schema='public' and table_name in ('research_sources','research_artifacts','research_paper_reviews','research_autonomy_tasks','research_model_dispatches','research_intake_runtime') group by table_name)x),
  'intake',(select jsonb_build_object('status',status,'enabled',enabled,'seen_at',seen_at,'configuration',configuration) from public.research_intake_runtime where id),
  'instructions','Task-bound service evidence. Artifact identifiers and hashes refer to retained originals. No private storage location, credential, SQL execution or scientific completion is exposed.');
end $$;

create function public.platform_service_work_resume() returns void
language plpgsql security definer set search_path='' as $$declare r record;begin
 if exists(select 1 from public.platform_settings where id and paused) then return;end if;
 for r in select q.*,a.revision,a.operation_id from public.platform_service_work_requests q
  join public.platform_service_work_activations a on a.request_id=q.id
  join public.platform_tasks p on p.id=q.parent_task_id
  where p.status='blocked' and p.lease_token is null and not p.cancel_requested and p.deadline_at>clock_timestamp()
   and p.checkpoint->'service_work_wait'->>'id'=q.id::text
   and p.authorization_version=(select authorization_version from public.platform_settings where id)
   and not exists(select 1 from public.platform_assessment_repair_bindings l join public.platform_assessment_blockers b on b.id=l.blocker_id
    join public.research_autonomy_workflows w on w.study_id=b.study_id where l.platform_task_id=p.id and (w.deadline_at<=clock_timestamp() or w.status not in ('running','completed-with-blockers')))
   and public.autonomy_budget_allows(p.budget_category,
    (select coalesce(sum(x.reserved_cents),0)::integer from public.platform_repair_family(p.id) f join public.platform_runs x on x.task_id=f.task_id),
    (select count(*)::integer from public.platform_repair_family(p.id) f join public.platform_runs x on x.task_id=f.task_id),100,1)
   and exists(select 1 from public.platform_operations o where o.id=a.operation_id and o.status='confirmed')
   and exists(select 1 from public.platform_releases l where l.task_id=q.implementation_task_id and l.component='infrastructure'
    and l.revision=a.revision and l.external_id=a.operation_id::text and l.status='verified')
   and not exists(select 1 from public.platform_capability_ancestors(p.id) f join public.platform_tasks t on t.id=f.task_id where t.cancel_requested or t.status='cancelled')
   and not exists(select 1 from public.platform_repair_family(p.id) f join public.platform_tasks t on t.id=f.task_id where t.checkpoint->>'cleanup_unknown'='true')
   and not exists(select 1 from public.platform_repair_family(p.id) f join public.platform_operations o on o.task_id=f.task_id where o.status in ('pending','unknown'))
   and not exists(select 1 from public.platform_repair_family(p.id) f join public.platform_runs x on x.task_id=f.task_id
    where x.status='running' or x.status='unknown' and not exists(select 1 from public.platform_run_reconciliations y where y.run_id=x.id))
 loop
  update public.platform_tasks set status='implementing',reason='Infrastructure service has a verified release; continuing the retained parent work.',
   checkpoint=(checkpoint-'not_before'-'pending_service_work')||jsonb_build_object('service_work_activation',r.id),updated_at=clock_timestamp() where id=r.parent_task_id;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),r.parent_task_id,'service-broker','service-parent-resumed',
   'Infrastructure-owned service activated and verified; original task may continue without resetting limits or uncertain outcomes.',jsonb_build_object('request_id',r.id,'operation_id',r.operation_id,'revision',r.revision,'scientific_completion',false));
 end loop;
end $$;

create function public.platform_service_work(p_operation text,p_worker uuid,p_task uuid,p_token uuid,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.platform_tasks;s public.platform_settings;q public.platform_service_work_requests;
 v_spec jsonb;ident uuid;child uuid;binding text;flags jsonb;result jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict s from public.platform_settings where id;
 select * into strict t from public.platform_tasks where id=p_task for update;
 if jsonb_typeof(p_payload) is distinct from 'object' or p_worker is null or p_token is null
  or t.worker_id is distinct from p_worker or t.lease_token is distinct from p_token or t.lease_until<=clock_timestamp()
  or t.lease_until is null or t.authorization_version is distinct from s.authorization_version then raise exception 'Current service-work lease required';end if;
 if p_operation='context' then
  if p_payload<>'{}'::jsonb then raise exception 'Unexpected service context fields';end if;
  select * into q from public.platform_service_work_requests where implementation_task_id=t.id;
  return jsonb_build_object('version','platform-service-work-v1',
   'implementation',case when q.id is not null then jsonb_build_object('id',q.id,'profile',q.profile,'spec',q.spec,'parent_task_id',q.parent_task_id) end,
   'activation',(select jsonb_build_object('request_id',a.request_id,'profile',r.profile,'revision',a.revision,'operation_id',a.operation_id)
    from public.platform_service_work_requests r join public.platform_service_work_activations a on a.request_id=r.id
    where r.parent_task_id=t.id and t.checkpoint->>'service_work_activation'=r.id::text),
   'evidence',public.platform_service_evidence(t.id),'requires_further_owner_approval',false);
 elsif p_operation<>'request' then raise exception 'Unsupported service-work operation';end if;
 if (p_payload-array['id','spec','artifact_id'])<>'{}'::jsonb then raise exception 'Unexpected service request fields';end if;
 ident=(p_payload->>'id')::uuid;v_spec=p_payload->'spec';
 if ident is null or jsonb_typeof(v_spec) is distinct from 'object' or (v_spec-array['version','profile','objective','acceptance'])<>'{}'::jsonb
  or v_spec->>'version' is distinct from 'platform-service-work-v1' or coalesce(v_spec->>'profile','') not in ('assessment-evidence-v1','intake-parser-recovery-v1')
  or jsonb_typeof(v_spec->'objective') is distinct from 'string' or length(coalesce(v_spec->>'objective','')) not between 1 and 8000
  or jsonb_typeof(v_spec->'acceptance') is distinct from 'array' or jsonb_array_length(v_spec->'acceptance') not between 1 and 12
  or exists(select 1 from jsonb_array_elements(v_spec->'acceptance') x where jsonb_typeof(x) is distinct from 'string' or length(x#>>'{}') not between 1 and 500)
  or octet_length(v_spec::text)>16000 then raise exception 'Invalid service work specification';end if;
 if not exists(select 1 from public.platform_artifacts a where a.id=(p_payload->>'artifact_id')::uuid and a.task_id=t.id
  and a.name='infrastructure-service-request.json' and a.byte_count<=16000) then raise exception 'Retained task-bound service request required';end if;
 binding=encode(sha256(convert_to(v_spec::text,'UTF8')),'hex');
 select * into q from public.platform_service_work_requests where id=ident;
 if found and (q.parent_task_id,q.spec,q.artifact_id) is distinct from (t.id,v_spec,(p_payload->>'artifact_id')::uuid) then raise exception 'Service request identity differs';end if;
 if not found then select * into q from public.platform_service_work_requests where parent_task_id=t.id and spec_sha256=binding;end if;
 if q.id is not null then return jsonb_build_object('id',q.id,'implementation_task_id',q.implementation_task_id,'profile',q.profile,'replayed',true);end if;
 if exists(select 1 from public.platform_service_work_requests where parent_task_id=t.id and profile=v_spec->>'profile') then raise exception 'Retain the original service profile request';end if;
 flags=public.platform_worker('lease',p_worker,p_task,p_token,'{}');
 if s.paused or flags->>'cancel_requested'='true' or t.deadline_at<=clock_timestamp()+interval '180 seconds'
  or t.status in ('completed','rolled-back','cancelled','deadline','budget')
  or public.platform_service_evidence(t.id) is null
  or exists(select 1 from public.platform_assessment_repair_bindings l join public.platform_assessment_blockers b on b.id=l.blocker_id
   join public.research_autonomy_workflows w on w.study_id=b.study_id where l.platform_task_id=t.id and (w.deadline_at<=clock_timestamp() or w.status not in ('running','completed-with-blockers')))
  or exists(select 1 from public.platform_capability_ancestors(t.id) f join public.platform_tasks a on a.id=f.task_id where a.cancel_requested or a.status='cancelled')
  or exists(select 1 from public.platform_repair_family(t.id) f join public.platform_tasks a on a.id=f.task_id where a.checkpoint->>'cleanup_unknown'='true')
  or exists(select 1 from public.platform_repair_family(t.id) f join public.platform_operations o on o.task_id=f.task_id where o.status in ('pending','unknown'))
  or exists(select 1 from public.platform_repair_family(t.id) f join public.platform_runs x on x.task_id=f.task_id
   where x.status='running' or x.status='unknown' and not exists(select 1 from public.platform_run_reconciliations y where y.run_id=x.id))
  then raise exception 'Original controls or uncertain actions prevent service admission';end if;
 if exists(select 1 from public.platform_capability_ancestors(t.id) f join public.platform_service_work_requests a on a.implementation_task_id=f.task_id where a.profile=v_spec->>'profile')
  then raise exception 'Service dependency cycle';end if;
 if not public.autonomy_budget_allows(t.budget_category,(flags->>'committed_cents')::integer,(flags->>'model_calls')::integer,0,0)
  then raise exception 'Original category budget prevents service work';end if;
 child=gen_random_uuid();
 insert into public.platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,priority,max_reserved_cents,deadline_at,checkpoint)
 values(child,t.requested_by,left('Implement infrastructure service: '||(v_spec->>'profile'),160),
  'Activate the fixed infrastructure-owned service for the retained request. The trusted controller derives its configuration; protected CI and the source-bound release workflow execute and verify the adapter. Requested work: '||(v_spec->>'objective'),
  array['jumpserve-networks/jumpserve-infra'],t.authorization_version,t.budget_category,greatest(0,t.priority-1),t.max_reserved_cents,t.deadline_at,jsonb_build_object('service_work_request_id',ident));
 insert into public.platform_service_work_requests(id,parent_task_id,implementation_task_id,profile,spec,spec_sha256,artifact_id)
 values(ident,t.id,child,v_spec->>'profile',v_spec,binding,(p_payload->>'artifact_id')::uuid);
 result=jsonb_build_object('id',ident,'implementation_task_id',child,'profile',v_spec->>'profile');
 update public.platform_tasks set status='blocked',reason='Infrastructure service assigned to its owning repository; waiting for a verified release.',
  checkpoint=jsonb_set(checkpoint,'{service_work_wait}',result),updated_at=clock_timestamp() where id=t.id;
 insert into public.platform_events(id,task_id,actor,kind,message,details) values(ident,t.id,'service-broker','infrastructure-service-requested',
  'Missing infrastructure service became linked work in jumpserve-infra. Parent scope, limits, cancellation and original call identities are retained.',result||jsonb_build_object('spec_sha256',binding));
 return result;
end $$;

create function public.platform_service_release(p_operation uuid,p_revision text,p_manifest jsonb default null,p_result jsonb default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare o public.platform_operations;t public.platform_tasks;q public.platform_service_work_requests;s public.platform_settings;
 a public.platform_service_work_activations;e jsonb;expected jsonb;rt public.research_autonomy_tasks;w public.research_autonomy_workflows;
 artifact public.research_artifacts;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict o from public.platform_operations where id=p_operation for update;
 select * into strict t from public.platform_tasks where id=o.task_id for update;
 select * into q from public.platform_service_work_requests where implementation_task_id=t.id;
 if q.id is null then return null;end if;
 select * into strict s from public.platform_settings where id;
 if o.kind<>'deploy' or o.request->>'repository' is distinct from 'jumpserve-networks/jumpserve-infra'
  or o.request->>'component' is distinct from 'infrastructure' or o.request->>'revision' is distinct from p_revision
  or p_revision!~'^[a-f0-9]{40}$' then raise exception 'Original infrastructure service release required';end if;
 select * into a from public.platform_service_work_activations where request_id=q.id;
 if a.request_id is not null then
  if a.operation_id<>o.id or a.revision<>p_revision then raise exception 'Original service activation differs';end if;
  return jsonb_build_object('verified',true,'request_id',q.id,'profile',q.profile,'verification',a.verification);
 end if;
 if s.paused or not s.automatic_releases or t.cancel_requested or t.deadline_at<=clock_timestamp()
  or t.status in ('completed','blocked','rolled-back','cancelled','deadline','budget')
  or t.authorization_version is distinct from s.authorization_version or o.status not in ('pending','unknown')
  or exists(select 1 from public.platform_capability_ancestors(t.id) f join public.platform_tasks p on p.id=f.task_id where p.cancel_requested or p.status='cancelled')
  or exists(select 1 from public.platform_repair_family(t.id) f join public.platform_tasks p on p.id=f.task_id where p.checkpoint->>'cleanup_unknown'='true')
  or exists(select 1 from public.platform_repair_family(t.id) f join public.platform_operations p on p.task_id=f.task_id where p.id<>o.id and p.status in ('pending','unknown'))
  or exists(select 1 from public.platform_repair_family(t.id) f join public.platform_runs r on r.task_id=f.task_id where r.status='running' or r.status='unknown' and not exists(select 1 from public.platform_run_reconciliations x where x.run_id=r.id))
  then raise exception 'Safe original service release boundary required';end if;
 e=public.platform_service_evidence(t.id);
 if e is null or (e->'workflow'->>'deadline_at')::timestamptz<=clock_timestamp()
  or e->'workflow'->>'status' not in ('running','completed-with-blockers') then raise exception 'Original assessment limits prevent service work';end if;
 if p_manifest is null and p_result is null then return jsonb_build_object('version','platform-service-work-v1','request_id',q.id,'profile',q.profile,
  'manifest_path','services/'||q.id::text||'.json','evidence',e,'parent_task_id',q.parent_task_id);end if;
 expected=jsonb_build_object('version','platform-service-manifest-v1','request_id',q.id,'profile',q.profile);
 if p_manifest is distinct from expected or jsonb_typeof(p_result) is distinct from 'object' or octet_length(p_result::text)>32000 or p_result->>'passed' is distinct from 'true'
  or p_result->>'profile' is distinct from q.profile or p_result->>'request_id' is distinct from q.id::text
  or p_result->>'revision' is distinct from p_revision or p_result->>'scientific_completion' is distinct from 'false'
  then raise exception 'Executed, exact service manifest proof required';end if;
 if q.profile='assessment-evidence-v1' and (p_result->>'task_bound_evidence_verified' is distinct from 'true' or coalesce(p_result->>'schema_sha256','')!~'^[a-f0-9]{64}$')
  then raise exception 'Executed task-bound evidence read required';end if;
 if q.profile='intake-parser-recovery-v1' then
  select * into strict rt from public.research_autonomy_tasks where id=(e->>'assessment_task_id')::uuid for update;
  select * into strict w from public.research_autonomy_workflows where study_id=rt.study_id for update;
  if rt.stage<>'intake' or rt.claim_id is not null or rt.intake_parent_id is not null or rt.status<>'blocked' or rt.attempts<>0 or rt.lease_token is not null
   or rt.context<>'{"intake_pool_version":"warm-intake-v1"}'::jsonb
   or encode(sha256(convert_to(rt.reason,'UTF8')),'hex') is distinct from p_result->>'original_reason_sha256'
   or w.deadline_at<=clock_timestamp()+interval '480 seconds'
   or w.max_spend_cents is not null and w.committed_cents+5>w.max_spend_cents
   or w.max_attempts is not null and rt.attempts>=w.max_attempts
   or not exists(select 1 from public.research_artifacts where study_id=rt.study_id and id=(p_result->>'failure_artifact_id')::uuid
    and sha256=p_result->>'failure_sha256' and provenance->>'kind'='failed-text-extraction' and provenance->>'original_artifact_id'=p_result->>'original_artifact_id')
   or not exists(select 1 from public.research_paper_reviews where study_id=rt.study_id and status='failed' and confirmed_at is null and confirmation is null and seeds='[]'::jsonb)
   or exists(select 1 from public.research_autonomy_turns where study_id=rt.study_id)
   or exists(select 1 from public.research_builder_calls where study_id=rt.study_id)
   or exists(select 1 from public.research_model_dispatches where study_id=rt.study_id)
   or exists(select 1 from public.research_claims where study_id=rt.study_id)
   or exists(select 1 from public.research_autonomy_tasks where study_id=rt.study_id and id<>rt.id)
   or not exists(select 1 from public.research_intake_runtime where id and enabled and status='ready' and seen_at>clock_timestamp()-interval '25 seconds'
    and configuration->>'gateway_verified'='true' and configuration->>'source_binding'=p_result->>'intake_source_binding')
   or p_result->>'parser_version' is distinct from '6.19.0' or p_result->>'failure_verified' is distinct from 'true'
   or p_result->>'intake_environment_verified' is distinct from 'true'
   or coalesce(p_result->>'environment_command_id','')!~'^[a-f0-9-]{36}$'
   or coalesce((p_result->>'environment_checked_at')::timestamptz,'-infinity'::timestamptz)<=clock_timestamp()-interval '10 minutes'
   or p_result->>'provider_calls' is distinct from '0' or not public.autonomy_budget_allows('research_assessment',w.committed_cents,0,5,0)
   then raise exception 'Only an unchanged zero-call parser failure can resume';end if;
  select * into strict artifact from public.research_artifacts where study_id=rt.study_id and id=(p_result->>'text_artifact_id')::uuid
   and sha256=p_result->>'text_sha256' and provenance->>'kind'='derived-pdf-text';
  if not exists(select 1 from public.research_sources where study_id=rt.study_id and id=(p_result->>'source_id')::uuid and sha256=artifact.provenance->>'original_sha256')
   or artifact.provenance->>'original_artifact_id' is distinct from p_result->>'original_artifact_id'
   or not exists(select 1 from public.research_artifacts where study_id=rt.study_id and id=(p_result->>'original_artifact_id')::uuid and sha256=artifact.provenance->>'original_sha256')
   then raise exception 'Recovered source/text artifact binding differs';end if;
  insert into public.research_autonomy_events(study_id,task_id,event,details) values(rt.study_id,rt.id,'infrastructure-service-intake-recovered',
   jsonb_build_object('operation_id',o.id,'request_id',q.id,'original_reason',rt.reason,'original_context',rt.context,'original_deadline_at',w.deadline_at,
    'original_attempts',rt.attempts,'original_committed_cents',w.committed_cents,'text_artifact_id',artifact.id,'provider_replay',false));
  update public.research_autonomy_tasks set context=context||jsonb_build_object('source_id',p_result->>'source_id','original_artifact_id',p_result->>'original_artifact_id',
   'text_artifact_id',artifact.id,'chunk_index',0),status='queued',reason='Qualified infrastructure service recovered the retained PDF text; original intake resumed.',next_at=clock_timestamp(),updated_at=clock_timestamp() where id=rt.id;
  update public.research_autonomy_workflows set status='running',updated_at=clock_timestamp() where study_id=rt.study_id;
  update public.research_paper_reviews set status='preparing',revision=revision+1,reason='Retained PDF text recovered by the qualified infrastructure service.',updated_at=clock_timestamp() where study_id=rt.study_id;
 end if;
 insert into public.platform_service_work_activations(request_id,operation_id,revision,manifest_sha256,verification)
 values(q.id,o.id,p_revision,encode(sha256(convert_to(p_manifest::text,'UTF8')),'hex'),p_result);
 insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'service-release','infrastructure-service-activated',
  'Infrastructure service executed under the original release identity; parent resumption awaits its confirmed operation and verified release.',
  jsonb_build_object('request_id',q.id,'profile',q.profile,'operation_id',o.id,'revision',p_revision,'scientific_completion',false));
 return jsonb_build_object('verified',true,'request_id',q.id,'profile',q.profile,'verification',p_result);
end $$;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_services_v1;
revoke all on function public.platform_worker_before_services_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;related boolean;spent integer;calls integer;category text;begin
 if p_operation in ('claim','lease','begin-run','maintenance','release','finish-operation') then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 end if;
 if p_operation in ('claim','lease','begin-run') then
  update public.platform_tasks child set cancel_requested=true,status=case when child.status='queued' then 'cancelled' else child.status end
   where exists(select 1 from public.platform_service_work_requests r where r.implementation_task_id=child.id)
    and not child.cancel_requested and exists(select 1 from public.platform_capability_ancestors(child.id) f join public.platform_tasks p on p.id=f.task_id where p.cancel_requested or p.status='cancelled');
 end if;
 related=exists(select 1 from public.platform_service_work_requests where parent_task_id=p_task or implementation_task_id=p_task);
 if related and p_operation in ('lease','begin-run') then
  select budget_category into strict category from public.platform_tasks where id=p_task;
  select coalesce(sum(r.reserved_cents),0),count(*) into spent,calls from public.platform_repair_family(p_task) f join public.platform_runs r on r.task_id=f.task_id;
  if p_operation='begin-run' then
   perform public.platform_worker_before_services_v1('lease',p_worker,p_task,p_token,'{}');
   if not public.autonomy_budget_allows(category,spent,calls,100,1) then return jsonb_build_object('denied','budget');end if;
  end if;
 end if;
 result=public.platform_worker_before_services_v1(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation='lease' then
  result=result||jsonb_build_object('service_work_contract','platform-service-work-v1');
  if related then result=result||jsonb_build_object('committed_cents',spent,'model_calls',calls);end if;
 end if;
 if p_operation in ('maintenance','release','finish-operation') then perform public.platform_service_work_resume();end if;
 return result;
end $$;
revoke all on function public.platform_service_evidence(uuid),public.platform_service_work_resume(),public.platform_capability_ancestors(uuid),public.platform_repair_family(uuid) from public,anon,authenticated,service_role;
revoke all on function public.platform_service_work(text,uuid,uuid,uuid,jsonb),public.platform_service_release(uuid,text,jsonb,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_service_work(text,uuid,uuid,uuid,jsonb),public.platform_service_release(uuid,text,jsonb,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
