begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Add a supplemental FAILED observation. Originals, usage, reservations and
-- unknown calls without captured failure evidence remain unchanged.
alter function public.research_builder_call_reconcile(uuid,uuid,text,jsonb) rename to research_builder_call_reconcile_before_failures_v1;
revoke all on function public.research_builder_call_reconcile_before_failures_v1(uuid,uuid,text,jsonb) from public,anon,authenticated,service_role;
create function public.research_builder_call_reconcile(p_call uuid,p_artifact uuid,p_sha256 text,p_proof jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare c public.research_builder_calls;d public.research_model_dispatches;t public.research_autonomy_tasks;r public.research_builder_call_reconciliations;f jsonb;begin
 if p_proof->>'version' is distinct from 'captured-provider-failure-v1' then
  return public.research_builder_call_reconcile_before_failures_v1(p_call,p_artifact,p_sha256,p_proof);end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict c from public.research_builder_calls where id=p_call for update;
 select * into r from public.research_builder_call_reconciliations where call_id=c.id;
 if found then
  if (r.artifact_id,r.sha256,r.proof) is distinct from (p_artifact,p_sha256,p_proof) then raise exception 'Original failure reconciliation is immutable';end if;
  return to_jsonb(r);
 end if;
 select * into strict d from public.research_model_dispatches where id=c.dispatch_id for update;
 select * into strict t from public.research_autonomy_tasks where id=c.task_id and study_id=c.study_id for update;
 if c.status<>'failed' or c.ended_at is null or c.response_received is not true or c.http_status not in (200,429,500,502,503,504)
  or c.response_sha256 is null or c.response_artifact_id is null or d.status not in ('failed','unknown','invalid-output')
  or not(d.request_raw::jsonb ? 'builder') or t.status='running' or (d.task_id,d.study_id) is distinct from (c.task_id,c.study_id)
  or exists(select 1 from public.research_model_dispatches where task_id=t.id and status in ('queued','running'))
  or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status='running')
 then raise exception 'Quiescent original captured native failure required';end if;
 f=p_proof->'failure';
 if p_proof->>'call_id' is distinct from c.id::text or p_proof->>'dispatch_id' is distinct from d.id::text
  or p_proof->>'study_id' is distinct from c.study_id::text or p_proof->>'task_id' is distinct from c.task_id::text
  or p_proof->>'request_sha256' is distinct from c.request_sha256 or p_proof->>'response_sha256' is distinct from c.response_sha256
  or p_proof->>'original_status' is distinct from c.status or p_proof->>'status' is distinct from 'failed'
  or p_proof->'http_status' is distinct from to_jsonb(c.http_status) or p_proof->'response_received' is distinct from 'true'::jsonb
  or p_proof->>'error_code' is distinct from c.reason or p_proof->>'container_cleanup' is distinct from 'stopped'
  or p_proof->'provider_replay' is distinct from 'false'::jsonb or p_proof->'scientific_completion' is distinct from 'false'::jsonb
  or f->>'version' is distinct from 'captured-provider-failure-v1' or f->>'request_sha256' is distinct from c.request_sha256
  or f->>'response_sha256' is distinct from c.response_sha256 or f->>'error_code' is distinct from c.reason
  or f->'http_status' is distinct from to_jsonb(c.http_status) or f->>'model' is distinct from 'gpt-6.1-sol'
  or f->>'evidence_kind' is distinct from (case when c.http_status=200 then 'framed-stream-error' else 'explicit-http-error' end)
  or f->'response_forwarded_to_agent' is distinct from 'false'::jsonb or f->'tool_calls_executed_from_response' is distinct from '0'::jsonb
  or f->'provider_processing_unknown' is distinct from 'true'::jsonb or f->'provider_replay' is distinct from 'false'::jsonb
  or f->'scientific_completion' is distinct from 'false'::jsonb
 then raise exception 'Exact captured native failure proof required';end if;
 if not exists(select 1 from public.research_artifacts where id=p_artifact and study_id=c.study_id and sha256=p_sha256
   and provenance->>'kind'='builder-native-call-reconciliation' and provenance->>'dispatch_id'=d.id::text)
  or not exists(select 1 from public.research_artifacts where id=(p_proof->'response'->>'artifact_id')::uuid and study_id=c.study_id
   and sha256=c.response_sha256 and byte_count<=1048576 and byte_count=(f->>'response_bytes')::integer
   and provenance->>'kind'='builder-reconciled-native-response' and provenance->>'dispatch_id'=d.id::text)
  or not exists(select 1 from public.research_artifacts where id=(p_proof->'completion'->>'artifact_id')::uuid and study_id=c.study_id
   and sha256=p_proof->'completion'->>'sha256' and byte_count<=16000
   and provenance->>'kind'='builder-reconciled-native-completion' and provenance->>'dispatch_id'=d.id::text)
  or not exists(select 1 from public.research_artifacts where id=c.request_artifact_id and study_id=c.study_id and sha256=c.request_sha256)
  or not exists(select 1 from public.research_artifacts where id=c.response_artifact_id and study_id=c.study_id and sha256=c.response_sha256)
 then raise exception 'Stored original native response, capture and failure proof required';end if;
 insert into public.research_builder_call_reconciliations(call_id,dispatch_id,study_id,task_id,request_sha256,artifact_id,sha256,response_artifact_id,response_sha256,proof)
 values(c.id,d.id,c.study_id,c.task_id,c.request_sha256,p_artifact,p_sha256,(p_proof->'response'->>'artifact_id')::uuid,c.response_sha256,p_proof) returning * into r;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(c.study_id,c.task_id,'native-failure-accounted',
  jsonb_build_object('call_id',c.id,'dispatch_id',d.id,'artifact_id',p_artifact,'sha256',p_sha256,'original_status',c.status,'provider_replay',false,'scientific_completion',false));
 return to_jsonb(r);
end $$;

alter function public.research_controller_dispatch_reconcile(uuid,uuid,text,jsonb) rename to research_controller_dispatch_reconcile_before_failures_v1;
revoke all on function public.research_controller_dispatch_reconcile_before_failures_v1(uuid,uuid,text,jsonb) from public,anon,authenticated,service_role;
create function public.research_controller_dispatch_reconcile(p_dispatch uuid,p_artifact uuid,p_sha256 text,p_proof jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_tasks;parent public.research_autonomy_turns;r public.research_model_reconciliations;
 f jsonb;reference jsonb;name text;begin
 if p_proof->>'version' is distinct from 'captured-provider-failure-v1' then
  return public.research_controller_dispatch_reconcile_before_failures_v1(p_dispatch,p_artifact,p_sha256,p_proof);end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict d from public.research_model_dispatches where id=p_dispatch for update;
 select * into r from public.research_model_reconciliations where dispatch_id=d.id;
 if found then
  if (r.artifact_id,r.sha256,r.proof) is distinct from (p_artifact,p_sha256,p_proof) then raise exception 'Original captured controller failure is immutable';end if;
  return to_jsonb(r);
 end if;
 select * into strict t from public.research_autonomy_tasks where id=d.task_id and study_id=d.study_id for update;
 select * into strict parent from public.research_autonomy_turns where id=d.id for update;
 if d.status<>'failed' or d.ended_at is null or d.runtime<>'openclaw-production-v1' or d.request_raw::jsonb ? 'builder' or t.status='running'
  or parent.status not in ('failed','unknown','invalid-output') or parent.ended_at is null or parent.model_id<>'gpt-6.1-sol'
  or (parent.task_id,parent.study_id,parent.request_sha256,parent.request_raw) is distinct from (d.task_id,d.study_id,d.request_sha256,d.request_raw)
  or exists(select 1 from public.research_model_dispatches where task_id=t.id and status in ('queued','running'))
  or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status='running')
  or exists(select 1 from public.research_builder_calls where dispatch_id=d.id)
 then raise exception 'Quiescent original data-only captured failure required';end if;
 f=p_proof->'failure';
 if p_proof->>'dispatch_id' is distinct from d.id::text or p_proof->>'task_id' is distinct from d.task_id::text
  or p_proof->>'study_id' is distinct from d.study_id::text or p_proof->>'request_sha256' is distinct from d.request_sha256
  or p_proof->>'original_status' is distinct from d.status or p_proof->>'request_kind' is distinct from 'controller'
  or p_proof->>'status' is distinct from 'failed' or p_proof->'provider_calls' is distinct from '1'::jsonb
  or p_proof->'provider_request_sent' is distinct from 'true'::jsonb or p_proof->'response_received' is distinct from 'true'::jsonb
  or p_proof->'provider_retries' is distinct from '0'::jsonb or p_proof->'provider_replay' is distinct from 'false'::jsonb
  or p_proof->'scientific_completion' is distinct from 'false'::jsonb
  or d.provenance->>'status' is distinct from 'failed' or d.provenance->>'runtime' is distinct from 'openclaw-production-v1'
  or d.provenance->>'model_id' is distinct from 'gpt-6.1-sol' or d.provenance->'provider_calls' is distinct from '1'::jsonb
  or d.provenance->'provider_request_sent' is distinct from 'true'::jsonb or d.provenance->'response_received' is distinct from 'true'::jsonb
  or d.provenance->'provider_retries' is distinct from '0'::jsonb or d.provenance->'paid_fallback' is distinct from 'false'::jsonb
  or f->>'version' is distinct from 'captured-provider-failure-v1' or f->'http_status' is distinct from d.provenance->'http_status'
  or f->>'error_code' is distinct from d.provenance->>'error_code' or f->>'model' is distinct from 'gpt-6.1-sol'
  or f->'http_status' not in ('200'::jsonb,'429'::jsonb,'500'::jsonb,'502'::jsonb,'503'::jsonb,'504'::jsonb)
  or f->>'evidence_kind' is distinct from (case when f->'http_status'='200'::jsonb then 'framed-stream-error' else 'explicit-http-error' end)
  or f->'response_forwarded_to_agent' is distinct from 'false'::jsonb or f->'tool_calls_executed_from_response' is distinct from '0'::jsonb
  or f->'provider_processing_unknown' is distinct from 'true'::jsonb or f->'provider_replay' is distinct from 'false'::jsonb
  or f->'scientific_completion' is distinct from 'false'::jsonb
  or jsonb_typeof(p_proof->'references') is distinct from 'object' or (select count(*) from jsonb_object_keys(p_proof->'references'))<>4
  or p_proof->'references'->'logical.json'->>'sha256' is distinct from d.request_sha256
  or p_proof->'references'->'provider-request.json'->>'sha256' is distinct from f->>'request_sha256'
  or p_proof->'references'->'provider-response.bin'->>'sha256' is distinct from f->>'response_sha256'
 then raise exception 'Exact one-operation captured controller failure proof required';end if;
 foreach name in array array['logical.json','provider-request.json','provider-response.bin','receipt.json'] loop
  reference=p_proof->'references'->name;
  if not exists(select 1 from public.research_artifacts a where a.study_id=d.study_id and a.id=(reference->>'artifact_id')::uuid
    and a.sha256=reference->>'sha256' and a.byte_count<=case name when 'provider-response.bin' then 1048576 when 'receipt.json' then 150000 else 96000 end
    and a.provenance->>'kind'='model-runtime-original' and a.provenance->>'dispatch_id'=d.id::text and a.provenance->>'filename'=name)
   or (select count(*) from jsonb_array_elements(d.provenance->'artifacts') x where x->>'name'=name)<>1
   or not exists(select 1 from jsonb_array_elements(d.provenance->'artifacts') x where x->>'name'=name
    and x->>'id'=reference->>'artifact_id' and x->>'sha256'=reference->>'sha256')
  then raise exception 'Exact dispatch-bound captured controller originals required';end if;
 end loop;
 if not exists(select 1 from public.research_artifacts where study_id=d.study_id and id=p_artifact and sha256=p_sha256
  and provenance->>'kind'='controller-dispatch-reconciliation' and provenance->>'dispatch_id'=d.id::text)
 then raise exception 'Stored original controller failure proof required';end if;
 insert into public.research_model_reconciliations(dispatch_id,study_id,task_id,request_sha256,artifact_id,sha256,proof)
 values(d.id,d.study_id,d.task_id,d.request_sha256,p_artifact,p_sha256,p_proof) returning * into r;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(d.study_id,d.task_id,'controller-failure-accounted',
  jsonb_build_object('dispatch_id',d.id,'artifact_id',p_artifact,'sha256',p_sha256,'provider_calls',1,'decision_reused',false,'provider_replay',false,'scientific_completion',false));
 return to_jsonb(r);
end $$;

do $migration$ declare definition text;old text;begin
 definition=pg_get_functiondef('public.research_model_reconcile(uuid,uuid,text,jsonb)'::regprocedure);
 old=$old$as x(id uuid,request_sha256 text,response_sha256 text)$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected native coverage schema';end if;
 definition=replace(definition,old,'as x(id uuid,request_sha256 text,response_sha256 text,status text)');
 old=$old$and nr.response_sha256=c.response_sha256))$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected native supplemental coverage';end if;
 definition=replace(definition,old,$new$and nr.response_sha256=c.response_sha256 and
   ((nr.proof->>'status'='complete' and coalesce(c.status,'complete')='complete')
    or (nr.proof->>'version'='captured-provider-failure-v1' and nr.proof->>'status'='failed' and b.status='failed' and c.status='failed'))))$new$);
 execute definition;
 definition=pg_get_functiondef('public.research_model_reconciliation_candidates(uuid)'::regprocedure);
 old=$old$d.status='invalid-output' and not(d.request_raw::jsonb ? 'builder') and d.provenance->>'error_code'='invalid-structured-decision'$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected controller candidate boundary';end if;
 definition=replace(definition,old,$new$(d.status='invalid-output' and d.provenance->>'error_code'='invalid-structured-decision'
   or d.status='failed' and d.provenance->>'status'='failed' and d.provenance->>'response_received'='true')
   and not(d.request_raw::jsonb ? 'builder')$new$);
 execute definition;
end $migration$;

alter function public.research_model_reconcile(uuid,uuid,text,jsonb) rename to research_model_reconcile_before_diagnostics_v1;
revoke all on function public.research_model_reconcile_before_diagnostics_v1(uuid,uuid,text,jsonb) from public,anon,authenticated,service_role;
create function public.research_model_reconcile(p_dispatch uuid,p_artifact uuid,p_sha256 text,p_proof jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_tasks;r public.research_runtime_observations;source jsonb;begin
 if p_proof->>'version' is distinct from 'worker-runtime-diagnostics-v1' then
  return public.research_model_reconcile_before_diagnostics_v1(p_dispatch,p_artifact,p_sha256,p_proof);end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict d from public.research_model_dispatches where id=p_dispatch;
 select * into strict t from public.research_autonomy_tasks where id=d.task_id and study_id=d.study_id;
 if d.status not in ('complete','failed','unknown','invalid-output') or t.status='running'
  or p_proof->>'dispatch_id' is distinct from d.id::text or p_proof->>'task_id' is distinct from t.id::text
  or p_proof->>'study_id' is distinct from t.study_id::text or p_proof->>'request_sha256' is distinct from d.request_sha256
  or p_proof->'provider_calls' is distinct from '0'::jsonb or p_proof->'reconciliation_performed' is distinct from 'false'::jsonb
  or p_proof->'cleanup_performed' is distinct from 'false'::jsonb or p_proof->'scientific_completion' is distinct from 'false'::jsonb
  or coalesce(p_proof->>'runtime_source_binding','')!~'^[a-f0-9]{64}$'
  or (p_proof->>'observation_request_id' is not null and not exists(select 1 from public.platform_service_work_refinements refined
    join public.platform_assessment_repair_bindings binding on binding.platform_task_id=refined.parent_task_id
    join public.platform_assessment_blockers blocker on blocker.id=binding.blocker_id
    where refined.id::text=p_proof->>'observation_request_id' and blocker.study_id=t.study_id and blocker.assessment_task_id=t.id))
  or jsonb_typeof(p_proof->'sources') is distinct from 'array' or jsonb_array_length(p_proof->'sources')<>5
  or (select count(distinct x->>'filename') from jsonb_array_elements(p_proof->'sources') x)<>5
  or not exists(select 1 from public.research_artifacts a where a.id=p_artifact and a.study_id=t.study_id and a.sha256=p_sha256 and a.byte_count<=262144
   and a.provenance->>'kind'='worker-runtime-diagnostics-v1' and a.provenance->>'task_id'=t.id::text and a.provenance->>'dispatch_id'=d.id::text)
 then raise exception 'Exact worker-only task-bound runtime observation required';end if;
 for source in select * from jsonb_array_elements(p_proof->'sources') loop
  if source->>'filename' not in ('autonomy_read_progress.py','autonomy.py','autonomy_model.py','dispatch_recovery.py','siwc_protocol.py')
   or (source ? 'artifact' and not exists(select 1 from public.research_artifacts a where a.id=(source->'artifact'->>'artifact_id')::uuid
    and a.study_id=t.study_id and a.sha256=source->>'sha256' and a.sha256=source->'artifact'->>'sha256' and a.byte_count=(source->>'byte_count')::integer
    and a.byte_count<=262144 and a.provenance->>'kind'='worker-installed-source-v1' and a.provenance->>'task_id'=t.id::text
    and a.provenance->>'dispatch_id'=d.id::text and a.provenance->>'filename'=source->>'filename'))
   or (not(source ? 'artifact') and coalesce(source->>'status','') not in ('absent','inaccessible'))
  then raise exception 'Exact fixed installed source observation required';end if;
 end loop;
 select * into r from public.research_runtime_observations where artifact_id=p_artifact;
 if found then
  if (r.dispatch_id,r.study_id,r.task_id,r.sha256,r.proof) is distinct from (d.id,d.study_id,d.task_id,p_sha256,p_proof) then raise exception 'Runtime observation is immutable';end if;
  return to_jsonb(r);
 end if;
 insert into public.research_runtime_observations(artifact_id,study_id,task_id,dispatch_id,sha256,proof)
 values(p_artifact,d.study_id,d.task_id,d.id,p_sha256,p_proof) returning * into r;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(d.study_id,d.task_id,'worker-runtime-observed',
  jsonb_build_object('artifact_id',p_artifact,'sha256',p_sha256,'dispatch_id',d.id,'runtime_source_binding',p_proof->>'runtime_source_binding','provider_calls',0,'scientific_completion',false));
 return to_jsonb(r);
end $$;
revoke all on function public.research_model_reconcile(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.research_model_reconcile(uuid,uuid,text,jsonb) to service_role;

alter function public.research_model_reconciliation_candidates(uuid) rename to research_model_reconciliation_candidates_before_observations_v1;
revoke all on function public.research_model_reconciliation_candidates_before_observations_v1(uuid) from public,anon,authenticated,service_role;
create function public.research_model_reconciliation_candidates(p_after uuid default null) returns setof jsonb
language sql stable security definer set search_path='' as $$
 select x.value from (
  select old as value from public.research_model_reconciliation_candidates_before_observations_v1(p_after) old
  union all
  select distinct to_jsonb(d)||jsonb_build_object('runtime_observation_only',true,'runtime_observation_request_id',refined.id)
  from public.platform_service_work_refinements refined
  join public.platform_tasks parent on parent.id=refined.parent_task_id
  join public.platform_assessment_repair_bindings binding on binding.platform_task_id=refined.parent_task_id
  join public.platform_assessment_blockers blocker on blocker.id=binding.blocker_id
  join public.research_autonomy_tasks task on task.id=blocker.assessment_task_id and task.study_id=blocker.study_id
  join lateral (select dispatch.* from public.research_model_dispatches dispatch where dispatch.task_id=task.id and dispatch.study_id=task.study_id
    and dispatch.status in ('complete','failed','unknown','invalid-output') order by dispatch.created_at desc,dispatch.id desc limit 1) d on true
  where (p_after is null or d.id>p_after) and task.status<>'running'
   and not parent.cancel_requested and parent.deadline_at>clock_timestamp()
   and not exists(select 1 from public.platform_settings where id and paused)
   and not exists(select 1 from public.platform_capability_ancestors(parent.id) ancestor join public.platform_tasks stopped on stopped.id=ancestor.task_id where stopped.cancel_requested or stopped.status='cancelled')
   and exists(select 1 from public.research_autonomy_workflows where study_id=task.study_id and status in ('running','completed-with-blockers') and deadline_at>clock_timestamp())
   and not exists(select 1 from public.research_model_dispatches where task_id=task.id and status in ('queued','running'))
   and not exists(select 1 from public.research_runtime_observations observed where observed.task_id=task.id
    and observed.proof->>'observation_request_id'=refined.id::text)
 ) x order by (x.value->>'id')::uuid limit 8
$$;
revoke all on function public.research_model_reconciliation_candidates(uuid) from public,anon,authenticated;
grant execute on function public.research_model_reconciliation_candidates(uuid) to service_role;

alter function public.research_controller_dispatch_accounted(public.research_model_dispatches) rename to research_controller_dispatch_accounted_before_failures_v1;
revoke all on function public.research_controller_dispatch_accounted_before_failures_v1(public.research_model_dispatches) from public,anon,authenticated,service_role;
create function public.research_controller_dispatch_accounted(d public.research_model_dispatches) returns boolean
language sql stable security definer set search_path='' as $$
 select public.research_controller_dispatch_accounted_before_failures_v1(d) or
 (d.status='failed' and exists(select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id and r.study_id=d.study_id
  and r.task_id=d.task_id and r.request_sha256=d.request_sha256 and r.proof->>'version'='captured-provider-failure-v1'
  and r.proof->>'original_status'=d.status and r.proof->>'status'='failed' and r.proof->>'request_kind'='controller'
  and r.proof->'provider_calls'='1'::jsonb and r.proof->'provider_replay'='false'::jsonb
  and exists(select 1 from public.research_artifacts a where a.id=r.artifact_id and a.study_id=r.study_id and a.sha256=r.sha256)))
$$;
-- SQL callers can retain the old function OID after rename; replace references
-- in the existing runtime resume function explicitly, keeping every other guard.
do $$declare definition text;begin
 definition=pg_get_functiondef('public.research_runtime_resume(uuid)'::regprocedure);
 if strpos(definition,'public.research_controller_dispatch_accounted(')=0 then raise exception 'Unexpected runtime resume accounting boundary';end if;
 execute definition;
end $$;
revoke all on function public.research_controller_dispatch_accounted(public.research_model_dispatches) from public,anon,authenticated,service_role;
revoke all on function public.research_builder_call_reconcile(uuid,uuid,text,jsonb),public.research_controller_dispatch_reconcile(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.research_builder_call_reconcile(uuid,uuid,text,jsonb),public.research_controller_dispatch_reconcile(uuid,uuid,text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
