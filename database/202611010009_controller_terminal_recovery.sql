begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- The trusted worker validates retained bytes, including a consistent terminal
-- stream. This adapter binds that supplemental proof to the original DB rows.
-- It never updates a failed turn/dispatch or returns its rejected decision.
create function public.research_controller_dispatch_reconcile(p_dispatch uuid,p_artifact uuid,p_sha256 text,p_proof jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_tasks;parent public.research_autonomy_turns;
 r public.research_model_reconciliations;name text;reference jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict d from public.research_model_dispatches where id=p_dispatch for update;
 select * into r from public.research_model_reconciliations where dispatch_id=d.id;
 if found then
  if (r.artifact_id,r.sha256,r.proof) is distinct from (p_artifact,p_sha256,p_proof) then raise exception 'Controller reconciliation original is immutable';end if;
  return to_jsonb(r);
 end if;
 select * into strict t from public.research_autonomy_tasks where id=d.task_id and study_id=d.study_id for update;
 select * into strict parent from public.research_autonomy_turns where id=d.id for update;
 if d.status<>'invalid-output' or d.ended_at is null or d.runtime<>'openclaw-production-v1'
  or d.request_raw::jsonb ? 'builder' or t.status='running'
  or parent.status not in ('failed','unknown','invalid-output') or parent.ended_at is null or parent.model_id<>'gpt-6.1-sol'
  or (parent.study_id,parent.task_id,parent.request_sha256,parent.request_raw) is distinct from (d.study_id,d.task_id,d.request_sha256,d.request_raw)
  or exists(select 1 from public.research_model_dispatches where task_id=t.id and status in ('queued','running'))
  or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status='running')
  or exists(select 1 from public.research_builder_calls where dispatch_id=d.id)
 then raise exception 'Quiescent original data-only invalid controller decision required';end if;
 if jsonb_typeof(p_proof) is distinct from 'object'
  or p_proof->>'version' is distinct from 'controller-terminal-reconciliation-v1'
  or p_proof->>'dispatch_id' is distinct from d.id::text or p_proof->>'task_id' is distinct from d.task_id::text
  or p_proof->>'study_id' is distinct from d.study_id::text or p_proof->>'request_sha256' is distinct from d.request_sha256
  or p_proof->>'original_status' is distinct from d.status or p_proof->>'request_kind' is distinct from 'controller'
  or p_proof->>'terminal_status' is distinct from 'completed' or p_proof->'decision_accepted' is distinct from 'false'::jsonb
  or p_proof->'provider_calls' is distinct from '1'::jsonb or p_proof->'provider_request_sent' is distinct from 'true'::jsonb
  or p_proof->'response_received' is distinct from 'true'::jsonb or p_proof->'http_status' is distinct from '200'::jsonb
  or p_proof->'provider_retries' is distinct from '0'::jsonb or p_proof->>'error_code' is distinct from 'invalid-structured-decision'
  or not coalesce(p_proof->>'terminal_sha256'~'^[a-f0-9]{64}$',false)
  or not coalesce(length(p_proof->>'response_id') between 1 and 200,false)
  or jsonb_typeof(p_proof->'references') is distinct from 'object'
  or (select count(*) from jsonb_object_keys(p_proof->'references'))<>4
  or p_proof->'references'->'logical.json'->>'sha256' is distinct from d.request_sha256
  or d.provenance->>'runtime' is distinct from 'openclaw-production-v1'
  or d.provenance->>'model_id' is distinct from 'gpt-6.1-sol'
  or d.provenance->>'status' is distinct from 'invalid-output'
  or d.provenance->>'error_code' is distinct from 'invalid-structured-decision'
  or d.provenance->'provider_calls' is distinct from '1'::jsonb or d.provenance->'provider_request_sent' is distinct from 'true'::jsonb
  or d.provenance->'response_received' is distinct from 'true'::jsonb or d.provenance->'http_status' is distinct from '200'::jsonb
  or d.provenance->'provider_retries' is distinct from '0'::jsonb or d.provenance->'paid_fallback' is distinct from 'false'::jsonb
 then raise exception 'Exact one-operation terminal rejection proof required';end if;
 foreach name in array array['logical.json','provider-request.json','provider-response.bin','receipt.json'] loop
  reference=p_proof->'references'->name;
  if not exists(select 1 from public.research_artifacts a where a.study_id=d.study_id
    and a.id=(reference->>'artifact_id')::uuid and a.sha256=reference->>'sha256'
    and a.byte_count<=case name when 'provider-response.bin' then 1048576 when 'receipt.json' then 150000 else 96000 end
    and a.provenance->>'kind'='model-runtime-original' and a.provenance->>'dispatch_id'=d.id::text and a.provenance->>'filename'=name)
   or (select count(*) from jsonb_array_elements(d.provenance->'artifacts') x where x->>'name'=name)<>1
   or not exists(select 1 from jsonb_array_elements(d.provenance->'artifacts') x
    where x->>'name'=name and x->>'id'=reference->>'artifact_id' and x->>'sha256'=reference->>'sha256')
  then raise exception 'Exact study/dispatch-bound original controller artifacts required';end if;
 end loop;
 if not exists(select 1 from public.research_artifacts where study_id=d.study_id and id=p_artifact and sha256=p_sha256
  and provenance->>'kind'='controller-dispatch-reconciliation' and provenance->>'dispatch_id'=d.id::text)
 then raise exception 'Stored original controller proof required';end if;
 insert into public.research_model_reconciliations(dispatch_id,study_id,task_id,request_sha256,artifact_id,sha256,proof)
 values(d.id,d.study_id,d.task_id,d.request_sha256,p_artifact,p_sha256,p_proof) returning * into r;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(d.study_id,d.task_id,'controller-terminal-reconciled',
  jsonb_build_object('dispatch_id',d.id,'request_sha256',d.request_sha256,'original_status',d.status,'artifact_id',p_artifact,'sha256',p_sha256,
   'provider_calls',1,'decision_reused',false,'provider_replay',false,'scientific_completion',false));
 return to_jsonb(r);
end$$;
revoke all on function public.research_controller_dispatch_reconcile(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.research_controller_dispatch_reconcile(uuid,uuid,text,jsonb) to service_role;

create or replace function public.research_model_reconciliation_candidates(p_after uuid default null) returns setof jsonb
language sql stable security definer set search_path='' as $$
 select to_jsonb(d) from public.research_model_dispatches d
 join public.research_autonomy_tasks q on q.id=d.task_id and q.study_id=d.study_id
 join public.research_autonomy_turns t on t.id=d.id
 where (p_after is null or d.id>p_after)
  and not exists(select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id)
  and not exists(select 1 from public.research_queued_dispatch_reconciliations r where r.dispatch_id=d.id)
  and ((jsonb_typeof(d.request_raw::jsonb->'builder')='object' and d.status in ('unknown','failed','invalid-output') and q.status<>'running'
    and not exists(select 1 from public.research_autonomy_turns turn where turn.task_id=q.id and turn.status='running')
    and not exists(select 1 from public.research_builder_calls c where c.task_id=q.id and c.status='running')
    and not exists(select 1 from public.research_model_dispatches live where live.task_id=q.id and live.status in ('queued','running')))
   or (d.status='queued' and public.research_queued_dispatch_diagnostic(d.id,d.request_sha256)->>'eligible'='true')
   or (d.status='invalid-output' and not(d.request_raw::jsonb ? 'builder') and d.provenance->>'error_code'='invalid-structured-decision'
    and q.status<>'running' and t.status in ('failed','unknown','invalid-output') and t.ended_at is not null
    and not exists(select 1 from public.research_autonomy_turns turn where turn.task_id=q.id and turn.status='running')
    and not exists(select 1 from public.research_builder_calls c where c.dispatch_id=d.id)
    and not exists(select 1 from public.research_model_dispatches live where live.task_id=q.id and live.status in ('queued','running'))))
 order by d.id limit 8
$$;

-- Private admission predicate: accepted original responses or independently
-- recorded supplemental closure. It never treats a receipt alone as proof.
create function public.research_controller_dispatch_accounted(d public.research_model_dispatches) returns boolean
language sql stable security definer set search_path='' as $$
 select (d.status='complete' and exists(select 1 from public.research_artifacts a where a.id=d.response_artifact_id and a.study_id=d.study_id and a.sha256=d.response_sha256))
 or (d.status='failed' and exists(select 1 from public.research_queued_dispatch_reconciliations r where r.dispatch_id=d.id
  and r.study_id=d.study_id and r.task_id=d.task_id and r.request_sha256=d.request_sha256
  and r.proof->>'version' in ('queued-dispatch-reconciliation-v1','queued-dispatch-reconciliation-v2')
  and r.proof=d.provenance->'queued_admission_reconciliation' and r.proof->>'admission_state'='pristine-unclaimed'
  and r.proof->'provider_calls'='0'::jsonb and r.proof->'provider_request_sent'='false'::jsonb))
 or (d.status='invalid-output' and exists(select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id
  and r.study_id=d.study_id and r.task_id=d.task_id and r.request_sha256=d.request_sha256
  and r.proof->>'version'='controller-terminal-reconciliation-v1' and r.proof->>'original_status'=d.status
  and r.proof->>'dispatch_id'=d.id::text and r.proof->>'task_id'=d.task_id::text and r.proof->>'study_id'=d.study_id::text
  and r.proof->>'request_sha256'=d.request_sha256 and r.proof->'provider_calls'='1'::jsonb
  and r.proof->>'terminal_status'='completed' and r.proof->'decision_accepted'='false'::jsonb
  and exists(select 1 from public.research_artifacts a where a.id=r.artifact_id and a.study_id=r.study_id and a.sha256=r.sha256)))
$$;
revoke all on function public.research_controller_dispatch_accounted(public.research_model_dispatches) from public,anon,authenticated,service_role;

do $migration$ declare definition text;old text;begin
 definition=pg_get_functiondef('public.research_runtime_resume(uuid)'::regprocedure);
 old=$old$a.reason in ('A UUID identifier is required.','Worker lease expired; reconcile retained provider/experiment identity before more work.')$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected verified runtime stop selector';end if;
 definition=replace(definition,old,$new$a.reason in ('A UUID identifier is required.','Worker lease expired; reconcile retained provider/experiment identity before more work.',
  'Evidence page byte budget is outside the reader bound.','Source page and provenance exceed the bounded reader; no text was silently truncated.')$new$);
 old=$old$select 1 from public.research_model_dispatches d where d.task_id=a.id and d.status<>'complete'$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected original dispatch resume gate';end if;
 definition=replace(definition,old,'select 1 from public.research_model_dispatches d where d.task_id=a.id and not public.research_controller_dispatch_accounted(d)');
 old=$old$where d.task_id=a.id and not exists($old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected completed-response artifact gate';end if;
 definition=replace(definition,old,$new$where d.task_id=a.id and d.status='complete' and not exists($new$);
 old=$old$where r.task_id=a.id and r.status in ('running','unknown')$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected original unknown-turn gate';end if;
 definition=replace(definition,old,$new$where r.task_id=a.id and r.status in ('running','unknown') and
  (r.status='running' or not exists(select 1 from public.research_model_dispatches d where d.id=r.id
   and d.study_id=r.study_id and d.task_id=r.task_id and d.request_sha256=r.request_sha256 and public.research_controller_dispatch_accounted(d)))$new$);
 execute definition;
end $migration$;
notify pgrst,'reload schema';
commit;
