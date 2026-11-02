begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Preserve the whole admission implementation. Only change selection order:
-- shared cleanup, live calls and external actions remain urgent. An unchanged
-- task-local unknown model result must not consume every independent repair's
-- turn. Within that ordinary class, least recently served tasks go first.
do $$declare definition text;selector text;replacement text;begin
 definition=pg_get_functiondef('public.platform_worker_before_incident_closure_v7(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 selector=$old$order by case when a.status='reconciling' or a.checkpoint->>'cleanup_unknown'='true' then 0 else 1 end,a.priority,
     coalesce((select max(e.created_at) from public.platform_events e where e.task_id=a.id and e.kind='claimed'),'-infinity'::timestamptz),a.created_at,a.id$old$;
 replacement=$new$order by case when a.checkpoint->>'cleanup_unknown'='true'
     or exists(select 1 from public.platform_operations o where o.task_id=a.id and o.status in ('pending','unknown'))
     or exists(select 1 from public.platform_runs r where r.task_id=a.id and r.status='running') then 0 else 1 end,
     a.priority,coalesce((select max(e.created_at) from public.platform_events e where e.task_id=a.id and e.kind='claimed'),'-infinity'::timestamptz),
     a.created_at,a.id$new$;
 if strpos(definition,selector)=0 or length(definition)-length(replace(definition,selector,''))<>length(selector)
 then raise exception 'Unexpected original repair selector; admission is unchanged';end if;
 execute replace(definition,selector,replacement);
end$$;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_http_recovery_v8;
revoke all on function public.platform_worker_before_http_recovery_v8(text,uuid,uuid,uuid,jsonb)
 from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.platform_tasks;r public.platform_runs;existing public.platform_run_reconciliations;
 certificate public.platform_artifacts;source public.platform_artifacts;proof jsonb;reference jsonb;name text;code integer;begin
 if p_operation<>'reconcile-http-error' then
  return public.platform_worker_before_http_recovery_v8(p_operation,p_worker,p_task,p_token,p_payload);
 end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 -- An original live token is required even for supplemental proof. Pause,
 -- cancellation and elapsed deadlines still forbid new work; they do not
 -- forbid recording what happened to an already admitted call.
 perform public.platform_worker_before_http_recovery_v8('lease',p_worker,p_task,p_token,'{}');
 select * into strict t from public.platform_tasks where id=p_task for update;
 select * into strict r from public.platform_runs where id=(p_payload->>'id')::uuid and task_id=t.id for update;
 proof=p_payload->'proof';code=(proof->>'http_status')::integer;
 if r.status<>'unknown' or r.ended_at is null
  or jsonb_typeof(proof) is distinct from 'object' or octet_length(proof::text)>20000
  or proof->>'version' is distinct from 'platform-native-http-reconciliation-v1'
  or proof->>'transport' is distinct from 'buffered-native-function-only-v1'
  or proof->>'run_id' is distinct from r.id::text or proof->>'task_id' is distinct from t.id::text
  or proof->>'request_sha256' is distinct from r.request_sha256
  or proof->>'status' is distinct from 'failed' or proof->>'original_status' is distinct from 'unknown'
  or jsonb_typeof(proof->'http_status') is distinct from 'number' or code not in (500,502,503,504)
  or r.reason is distinct from ('Provider HTTP '||code::text||'.')
  or proof->'response_forwarded_to_agent' is distinct from 'false'::jsonb
  or proof->'tool_calls_executed_from_response' is distinct from '0'::jsonb
  or proof->'provider_calls' is distinct from '1'::jsonb
  or proof->'provider_processing_unknown' is distinct from 'true'::jsonb
  or proof->'measured_charges_usd' is distinct from 'null'::jsonb
  or proof->'provider_replay' is distinct from 'false'::jsonb
  or proof->'scientific_completion' is distinct from 'false'::jsonb
  or jsonb_typeof(proof->'references') is distinct from 'object'
  or (select count(*) from jsonb_object_keys(proof->'references'))<>3
 then raise exception 'Exact buffered function-only HTTP failure proof required';end if;
 foreach name in array array['request','response','receipt'] loop
  reference=proof->'references'->name;
  select * into source from public.platform_artifacts where id=(reference->>'artifact_id')::uuid and task_id=t.id;
  if not found or source.sha256 is distinct from reference->>'sha256'
   or source.byte_count is distinct from (reference->>'byte_count')::integer
   or source.byte_count>(case name when 'request' then 4000000 when 'response' then 1000000 else 150000 end)
   or (name='request' and (source.id is distinct from r.request_artifact_id or source.sha256 is distinct from r.request_sha256))
   or (name='response' and (source.id is distinct from r.response_artifact_id or source.sha256 is distinct from proof->>'response_sha256'))
   or (name='receipt' and (source.provenance->>'kind' is distinct from 'platform-native-original-receipt-v1'
    or source.provenance->>'run_id' is distinct from r.id::text or source.provenance->>'request_sha256' is distinct from r.request_sha256))
  then raise exception 'Original task-bound native artifacts required';end if;
 end loop;
 select * into certificate from public.platform_artifacts where id=(p_payload->>'artifact_id')::uuid and task_id=t.id;
 if not found or certificate.byte_count>20000
  or certificate.provenance->>'kind' is distinct from 'platform-native-http-reconciliation-v1'
  or certificate.provenance->>'run_id' is distinct from r.id::text
  or certificate.provenance->>'request_sha256' is distinct from r.request_sha256
  or certificate.provenance->'proof' is distinct from proof
 then raise exception 'Original HTTP reconciliation certificate required';end if;
 select * into existing from public.platform_run_reconciliations where run_id=r.id;
 if found then
  if existing.artifact_id is distinct from certificate.id or existing.proof is distinct from proof
  then raise exception 'Reconciliation proof is immutable';end if;
  return jsonb_build_object('reconciled',true,'original_status',r.status,'supplemental_outcome','failed');
 end if;
 insert into public.platform_run_reconciliations(run_id,task_id,artifact_id,proof) values(r.id,t.id,certificate.id,proof);
 insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','model-http-error-reconciled',
  'Original HTTP error reconciled from retained buffered-response evidence. The original unknown outcome and reservation remain unchanged; no tools from this response were delivered and no call was replayed.',
  jsonb_build_object('run_id',r.id,'artifact_id',certificate.id,'http_status',code,'original_status',r.status,'supplemental_outcome','failed','measured_charges_usd',null,'scientific_completion',false));
 return jsonb_build_object('reconciled',true,'original_status',r.status,'supplemental_outcome','failed');
end$$;
revoke all on function public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
