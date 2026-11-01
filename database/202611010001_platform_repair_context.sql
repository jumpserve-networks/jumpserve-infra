begin;

-- These helpers return data only. They cannot reconcile, resume, reserve funds,
-- change scientific state or authorize any release.
create function public.platform_repair_detail(value jsonb) returns jsonb
language sql immutable set search_path='' as $$
 select case when octet_length(value::text)<=16000 then value else
  jsonb_build_object('representation','bounded-json-excerpt','complete',false,
   'original_sha256',encode(sha256(convert_to(value::text,'UTF8')),'hex'),
   'bytes',octet_length(value::text),'excerpt',left(value::text,12000)) end
$$;

create function public.platform_repair_context_data(p_task uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare b public.platform_assessment_blockers;t public.research_autonomy_tasks;
 w public.research_autonomy_workflows;data jsonb;token_data jsonb;begin
 select signal.* into b from public.platform_assessment_repair_links l
  join public.platform_assessment_blockers signal on signal.id=l.blocker_id where l.platform_task_id=p_task;
 if not found then return null;end if;
 select * into strict t from public.research_autonomy_tasks where id=b.assessment_task_id and study_id=b.study_id;
 select * into strict w from public.research_autonomy_workflows where study_id=b.study_id;
 data=jsonb_build_object('version','platform-repair-handoff-v1','platform_task_id',p_task,
  'assessment_id',b.study_id,'assessment_task_id',t.id,
  'blocker',jsonb_build_object('id',b.id,'source_kind',b.source_kind,'source_id',b.source_id,'stage',b.stage,
   'source_status',b.source_status,'diagnostic',b.diagnostic,'original_reason_sha256',b.original_reason_sha256),
  'workflow',jsonb_build_object('status',w.status,'deadline_at',w.deadline_at,'max_spend_cents',w.max_spend_cents,'committed_cents',w.committed_cents),
  'task',jsonb_build_object('id',t.id,'stage',t.stage,'status',t.status,'reason',public.platform_assessment_diagnostic(t.reason),
   'attempts',t.attempts,'lease_until',t.lease_until,'lease_token_sha256',case when t.lease_token is not null then encode(sha256(convert_to(t.lease_token::text,'UTF8')),'hex') end,
   'context_sha256',encode(sha256(convert_to(t.context::text,'UTF8')),'hex'),
   'references',jsonb_build_object('builder_checkpoint',t.context->'builder_checkpoint','last_turn_id',t.context->'last_turn_id',
    'repair_progress',t.context->'repair_progress','repair_validation',t.context->'repair_validation',
    'native_repair_handoff',t.context->'native_repair_handoff','diagnosis',t.context->'repair_packet'->'diagnosis',
    'builder_feedback',public.platform_assessment_diagnostic(t.context->>'builder_feedback'))),
  'repairs',coalesce((select jsonb_agg(x.value order by x.created_at desc,x.id) from (
   select r.id,r.created_at,jsonb_build_object('id',r.id,'state',r.state,'revision',r.revision,'category',r.category,
    'reason',public.platform_assessment_diagnostic(r.reason),'incident_sha256',r.incident_sha256,
    'incident',public.platform_repair_detail(r.incident_raw::jsonb),'evidence',public.platform_repair_detail(r.evidence)) value
   from public.research_autonomy_repairs r where r.task_id=t.id and r.study_id=t.study_id order by r.created_at desc,r.id limit 8)x),'[]'),
  'repair_events',coalesce((select jsonb_agg(x.value order by x.created_at desc,x.id) from (
   select e.id,e.created_at,jsonb_build_object('id',e.id,'repair_id',e.repair_id,'revision',e.revision,'state',e.state,
    'details',public.platform_repair_detail(e.details)) value from public.research_autonomy_repair_events e
   where e.task_id=t.id and e.study_id=t.study_id order by e.created_at desc,e.id limit 24)x),'[]'),
  'events',coalesce((select jsonb_agg(x.value order by x.created_at desc,x.id) from (
   select e.id,e.created_at,jsonb_build_object('id',e.id,'event',e.event,'details',public.platform_repair_detail(e.details)) value
   from public.research_autonomy_events e where e.task_id=t.id and e.study_id=t.study_id order by e.created_at desc,e.id limit 24)x),'[]'),
  'turns',coalesce((select jsonb_agg(x.value order by x.number desc,x.id) from (
   select r.id,r.number,jsonb_build_object('id',r.id,'number',r.number,'stage',r.stage,'status',r.status,
    'request_sha256',r.request_sha256,'response_sha256',r.response_sha256,'reason',public.platform_assessment_diagnostic(r.reason)) value
   from public.research_autonomy_turns r where r.task_id=t.id and r.study_id=t.study_id
   order by case when r.status in ('running','unknown') then 0 else 1 end,r.number desc,r.id limit 100)x),'[]'),
  'dispatches',coalesce((select jsonb_agg(x.value order by x.created_at desc,x.id) from (
   select d.id,d.created_at,jsonb_build_object('id',d.id,'status',d.status,'request_sha256',d.request_sha256,
    'response_sha256',d.response_sha256,'response_artifact_id',d.response_artifact_id,'provenance',public.platform_repair_detail(d.provenance)) value
   from public.research_model_dispatches d where d.task_id=t.id and d.study_id=t.study_id
   order by case when d.status in ('running','unknown','queued') then 0 else 1 end,d.created_at desc,d.id limit 100)x),'[]'),
  'native_calls',coalesce((select jsonb_agg(x.value order by x.number desc,x.id) from (
   select c.id,c.number,jsonb_build_object('id',c.id,'dispatch_id',c.dispatch_id,'number',c.number,'status',c.status,
    'request_artifact_id',c.request_artifact_id,'request_sha256',c.request_sha256,'response_artifact_id',c.response_artifact_id,
    'response_sha256',c.response_sha256,'response_received',c.response_received,'http_status',c.http_status,'reason',public.platform_assessment_diagnostic(c.reason)) value
   from public.research_builder_calls c where c.task_id=t.id and c.study_id=t.study_id
   order by case when c.status in ('running','unknown') then 0 else 1 end,c.number desc,c.id limit 100)x),'[]'),
  'native_reconciliations',coalesce((select jsonb_agg(x.value order by x.created_at desc,x.call_id) from (
   select c.call_id,c.created_at,jsonb_build_object('call_id',c.call_id,'dispatch_id',c.dispatch_id,'request_sha256',c.request_sha256,
    'artifact_id',c.artifact_id,'sha256',c.sha256,'response_artifact_id',c.response_artifact_id,'response_sha256',c.response_sha256,
    'proof',public.platform_repair_detail(c.proof)) value from public.research_builder_call_reconciliations c
   where c.task_id=t.id and c.study_id=t.study_id order by c.created_at desc,c.call_id limit 100)x),'[]'),
  'model_reconciliations',coalesce((select jsonb_agg(x.value order by x.created_at desc) from (
   select r.created_at,jsonb_build_object('dispatch_id',r.dispatch_id,'request_sha256',r.request_sha256,
    'artifact_id',r.artifact_id,'sha256',r.sha256,'proof',public.platform_repair_detail(r.proof)) value from public.research_model_reconciliations r
   where r.task_id=t.id and r.study_id=t.study_id order by r.created_at desc,r.dispatch_id limit 100)x),'[]'),
  'artifacts',coalesce((select jsonb_agg(x.value order by x.created_at desc,x.id) from (
   select a.id,a.created_at,jsonb_build_object('id',a.id,'sha256',a.sha256,'byte_count',a.byte_count,'storage_path',a.storage_path,
    'provenance',a.provenance) value from public.research_artifacts a where a.study_id=t.study_id and
    (a.provenance->>'task_id'=t.id::text or a.provenance->>'dispatch_id' in (select d.id::text from public.research_model_dispatches d where d.study_id=t.study_id and d.task_id=t.id)
     or a.id::text in (t.context->'builder_checkpoint'->>'artifact_id',t.context->'repair_packet'->'diagnosis'->>'artifact_id'))
   order by case when a.id::text in (t.context->'builder_checkpoint'->>'artifact_id',t.context->'repair_packet'->'diagnosis'->>'artifact_id') then 0
    when a.provenance->>'filename' in ('checkpoint.zip','failed-checkpoint.zip','post-validation-checkpoint.zip','repair-handoff-baseline.zip',
     'stdout.bin','stderr.bin','receipt.json','diagnosis.json','repair-validation.json','repair-check-stdout.bin','repair-check-stderr.bin') then 1 else 2 end,
    a.created_at desc,a.id limit 12)x),'[]'),
  'coverage',jsonb_build_object('scope','Bounded latest evidence with unresolved calls prioritized; original ledgers remain private and unchanged.',
   'repairs_total',(select count(*) from public.research_autonomy_repairs where task_id=t.id and study_id=t.study_id),
   'repair_events_total',(select count(*) from public.research_autonomy_repair_events where task_id=t.id and study_id=t.study_id),
   'events_total',(select count(*) from public.research_autonomy_events where task_id=t.id and study_id=t.study_id),
   'turns_total',(select count(*) from public.research_autonomy_turns where task_id=t.id and study_id=t.study_id),
   'dispatches_total',(select count(*) from public.research_model_dispatches where task_id=t.id and study_id=t.study_id),
   'native_calls_total',(select count(*) from public.research_builder_calls where task_id=t.id and study_id=t.study_id),
   'unresolved_native_total',(select count(*) from public.research_builder_calls where task_id=t.id and study_id=t.study_id and status in ('running','unknown'))));
 -- Renewed leases, heartbeat timestamps and spent counters are not new incident
 -- evidence. Distinct diagnostic content, source hashes and actual call ledger
 -- changes are. Repair phase/revision churn alone must not restart blocked work.
 token_data=(data-'repairs'-'repair_events'-'events'-'coverage')
  #- '{task,lease_until}' #- '{task,lease_token_sha256}' #- '{task,context_sha256}'
  #- '{task,references,repair_progress}' #- '{workflow,committed_cents}';
 token_data=token_data||jsonb_build_object(
  'repairs',(select coalesce(jsonb_agg(v order by v),'[]') from (select distinct
    jsonb_build_object('incident_sha256',value->'incident_sha256','evidence',value->'evidence') v
    from jsonb_array_elements(data->'repairs')) r),
  -- Hash distinct semantic events across the ledger. The bounded display window
  -- rolling past an old event or repeated status/timestamp rows is not new data.
  'events_sha256',(select encode(sha256(convert_to(coalesce(string_agg(v,'' order by v),''),'UTF8')),'hex') from (select distinct
    encode(sha256(convert_to(jsonb_build_object('event',e.event,
      'details',e.details-array['created_at','updated_at','at','timestamp','revision'])::text,'UTF8')),'hex') v
    from public.research_autonomy_events e where e.task_id=t.id and e.study_id=t.study_id) e),
  'ledger_counts',jsonb_build_object('native_calls',data->'coverage'->'native_calls_total',
    'turns',data->'coverage'->'turns_total','dispatches',data->'coverage'->'dispatches_total'));
 return data||jsonb_build_object('evidence_revision',encode(sha256(convert_to(token_data::text,'UTF8')),'hex'));
end$$;

create function public.platform_repair_context(p_worker uuid,p_task uuid,p_token uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare t public.platform_tasks;s public.platform_settings;begin
 select * into strict t from public.platform_tasks where id=p_task;
 select * into strict s from public.platform_settings where id;
 if p_worker is null or p_token is null or t.worker_id is distinct from p_worker or t.lease_token is distinct from p_token
  or t.lease_until is null or t.lease_until<=statement_timestamp() or t.cancel_requested or s.paused or t.deadline_at<=statement_timestamp()
  or t.authorization_version is distinct from s.authorization_version then raise exception 'Current authorized platform repair lease required';end if;
 if exists(select 1 from public.platform_assessment_repair_links l
  join public.platform_assessment_blockers b on b.id=l.blocker_id
  join public.research_autonomy_workflows w on w.study_id=b.study_id
  where l.platform_task_id=t.id and (w.status not in ('running','completed-with-blockers') or w.deadline_at<=statement_timestamp()))
  then raise exception 'Original assessment authorization is no longer active';end if;
 return public.platform_repair_context_data(p_task);
end$$;

-- The original admission, budget, host, operation and release implementations
-- remain intact below this adapter. No counters/deadlines/unknowns are reset.
alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_repair_context_v1;
revoke all on function public.platform_worker_before_repair_context_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;t public.platform_tasks;packet jsonb;s public.platform_settings;begin
 result=public.platform_worker_before_repair_context_v1(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation='claim' and result is not null then
  return result||jsonb_build_object('assessment_repair',exists(select 1 from public.platform_assessment_repair_links where platform_task_id=(result->>'id')::uuid));
 elsif p_operation='maintenance' then
  select * into strict s from public.platform_settings where id;
  if s.paused or p_worker is null or not exists(select 1 from public.platform_authorizations where version=s.authorization_version and policy_sha256=p_payload->>'policy_sha256') then return result;end if;
  for t in select p.* from public.platform_tasks p
   join public.platform_assessment_repair_links l on l.platform_task_id=p.id
   join public.platform_assessment_blockers b on b.id=l.blocker_id
   join public.research_autonomy_workflows w on w.study_id=b.study_id
   where p.status='blocked' and not p.cancel_requested and p.lease_token is null and p.deadline_at>clock_timestamp()
    and p.authorization_version=s.authorization_version
    and w.status in ('running','completed-with-blockers') and w.deadline_at>clock_timestamp()
    and p.checkpoint->'repair_guard'->>'version'='platform-repair-handoff-v1'
    and p.checkpoint->'repair_guard'->>'waiting'='true'
   order by p.updated_at,p.id limit 16 for update of p skip locked
  loop
   packet=public.platform_repair_context_data(t.id);
   if packet->>'evidence_revision' is distinct from t.checkpoint->'repair_guard'->>'evidence_revision' then
    update public.platform_tasks set status='investigating',reason='New incident evidence is available; resume the original retained repair.',
     checkpoint=checkpoint-'not_before',updated_at=clock_timestamp() where id=t.id;
    insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'assessment-monitor','repair-evidence-updated',
     'Changed incident evidence reactivated the original repair. Commitments, counters, deadline and uncertain outcomes are retained.',
     jsonb_build_object('previous_evidence_revision',t.checkpoint->'repair_guard'->>'evidence_revision','evidence_revision',packet->>'evidence_revision'));
   end if;
  end loop;
 end if;
 return result;
end$$;
revoke all on function public.platform_repair_detail(jsonb),public.platform_repair_context_data(uuid),public.platform_repair_context(uuid,uuid,uuid),public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.platform_repair_context(uuid,uuid,uuid),public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
