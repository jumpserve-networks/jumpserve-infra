begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Read-only, incident-specific eligibility. Absence of a local file is never
-- evidence of zero transport. The immutable DB claim fence is authoritative.
create function public.research_queued_dispatch_diagnostic(p_dispatch uuid,p_request_sha256 text) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_turns;reasons jsonb='[]';kind text;begin
 select * into strict d from public.research_model_dispatches where id=p_dispatch;
 if d.request_sha256 is distinct from p_request_sha256 then raise exception 'Exact original queued request hash required';end if;
 select * into strict t from public.research_autonomy_turns where id=d.id;
 kind=case when jsonb_typeof(d.request_raw::jsonb->'builder')='object' then 'builder' else 'controller' end;
 if d.status<>'queued' then reasons=reasons||'"dispatch-not-queued"'::jsonb;end if;
 if d.runtime<>'openclaw-production-v1' then reasons=reasons||'"unsupported-runtime"'::jsonb;end if;
 if d.lease_token is not null or d.lease_until is not null then reasons=reasons||'"claim-fence-present"'::jsonb;end if;
 if d.ended_at is not null or d.response_artifact_id is not null or d.response_sha256 is not null or d.provenance<>'{}'::jsonb then reasons=reasons||'"transport-or-outcome-record-present"'::jsonb;end if;
 if t.status not in ('failed','unknown','invalid-output') or t.ended_at is null then reasons=reasons||'"parent-not-terminal"'::jsonb;end if;
 if t.model_id<>'gpt-6.1-sol' then reasons=reasons||'"parent-model-mismatch"'::jsonb;end if;
 if (t.study_id,t.task_id,t.request_sha256,t.request_raw) is distinct from (d.study_id,d.task_id,d.request_sha256,d.request_raw) then reasons=reasons||'"original-request-identity-mismatch"'::jsonb;end if;
 if jsonb_typeof(d.request_raw::jsonb) is distinct from 'object' then reasons=reasons||'"request-not-object"'::jsonb;end if;
 if exists(select 1 from public.research_builder_calls where dispatch_id=d.id) then reasons=reasons||'"native-admission-present"'::jsonb;end if;
 if exists(select 1 from public.research_artifacts where study_id=d.study_id and provenance->>'dispatch_id'=d.id::text) then reasons=reasons||'"dispatch-artifacts-present"'::jsonb;end if;
 return jsonb_build_object('version','queued-dispatch-diagnostic-v1','dispatch_id',d.id,'study_id',d.study_id,'task_id',d.task_id,
  'request_sha256',d.request_sha256,'request_kind',kind,'dispatch_status',d.status,'parent_turn_status',t.status,
  'eligible',jsonb_array_length(reasons)=0,'reason_codes',reasons,
  'scope','Current recorded eligibility only. The atomic adapter must lock and recheck before recording zero-transport closure; no cleanup, replay or resumption is implied.');
end$$;
revoke all on function public.research_queued_dispatch_diagnostic(uuid,text) from public,anon,authenticated,service_role;

create or replace function public.research_model_reconcile_queued(p_dispatch uuid,p_request_sha256 text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_turns;r public.research_queued_dispatch_reconciliations;
 original text;h text;proof jsonb;diagnostic jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict d from public.research_model_dispatches where id=p_dispatch for update;
 if d.request_sha256 is distinct from p_request_sha256 then raise exception 'Exact original queued request hash required';end if;
 select * into r from public.research_queued_dispatch_reconciliations where dispatch_id=d.id;
 if found then
  if d.status<>'failed' or d.provenance->'queued_admission_reconciliation' is distinct from r.proof then raise exception 'Queued reconciliation differs from its original terminal receipt';end if;
  return jsonb_build_object('reconciled',true,'dispatch_id',d.id,'snapshot_sha256',r.snapshot_sha256);
 end if;
 select * into strict t from public.research_autonomy_turns where id=d.id for update;
 diagnostic=public.research_queued_dispatch_diagnostic(d.id,p_request_sha256);
 if diagnostic->>'eligible' is distinct from 'true' then
  return jsonb_build_object('reconciled',false,'reason','Original admission is not proven pristine and unclaimed.','diagnostic',diagnostic);
 end if;
 original=to_jsonb(d)::text;h=encode(sha256(convert_to(original,'UTF8')),'hex');
 proof=jsonb_build_object('version','queued-dispatch-reconciliation-v1','dispatch_id',d.id,'study_id',d.study_id,'task_id',d.task_id,
  'request_sha256',d.request_sha256,'snapshot_sha256',h,'original_status','queued','terminal_status','failed',
  'parent_turn_status',t.status,'parent_turn_request_sha256',t.request_sha256,'provider_calls',0,'provider_request_sent',false,
  'admission_state','pristine-unclaimed','claim_fence','original-dispatch-row-lock;terminal-parent-turn',
  'scope','Pre-transport admission closure only; no container cleanup claim, inference replay, refund, deadline reset or scientific validation.');
 -- Existing builder proofs remain byte-for-byte compatible. The new version
 -- explicitly distinguishes an ordinary controller admission from a builder.
 if diagnostic->>'request_kind'='controller' then
  proof=proof||jsonb_build_object('version','queued-dispatch-reconciliation-v2','request_kind','controller');
 end if;
 insert into public.research_queued_dispatch_reconciliations(dispatch_id,study_id,task_id,request_sha256,snapshot_raw,snapshot_sha256,parent_turn_status,proof)
  values(d.id,d.study_id,d.task_id,d.request_sha256,original,h,t.status,proof);
 update public.research_model_dispatches set status='failed',ended_at=clock_timestamp(),
  provenance=jsonb_build_object('queued_admission_reconciliation',proof) where id=d.id;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(d.study_id,d.task_id,'queued-dispatch-reconciled',proof);
 return jsonb_build_object('reconciled',true,'dispatch_id',d.id,'snapshot_sha256',h);
end$$;

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
   or (d.status='queued' and public.research_queued_dispatch_diagnostic(d.id,d.request_sha256)->>'eligible'='true'))
 order by d.id limit 8
$$;
revoke all on function public.research_model_reconcile_queued(uuid,text),public.research_model_reconciliation_candidates(uuid) from public,anon,authenticated;
grant execute on function public.research_model_reconcile_queued(uuid,text),public.research_model_reconciliation_candidates(uuid) to service_role;

alter function public.platform_repair_recovery_contract() rename to platform_repair_recovery_contract_before_controller_v4;
revoke all on function public.platform_repair_recovery_contract_before_controller_v4() from public,anon,authenticated,service_role;
create function public.platform_repair_recovery_contract() returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_set(public.platform_repair_recovery_contract_before_controller_v4(),'{queued_admission}',
  public.platform_repair_recovery_contract_before_controller_v4()->'queued_admission'||jsonb_build_object(
   'accepted_proof_versions',jsonb_build_array('queued-dispatch-reconciliation-v1','queued-dispatch-reconciliation-v2'),
   'supported_queued_request_kinds',jsonb_build_array('builder','controller'),
   'diagnostic',jsonb_build_object('version','queued-dispatch-diagnostic-v1','scope','Private current-state diagnostic, rechecked under original row locks by the unchanged-authority adapter.')))
$$;
revoke all on function public.platform_repair_recovery_contract() from public,anon,authenticated,service_role;

alter function public.platform_repair_context_data(uuid) rename to platform_repair_context_data_before_controller_v4;
revoke all on function public.platform_repair_context_data_before_controller_v4(uuid) from public,anon,authenticated,service_role;
create function public.platform_repair_context_data(p_task uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare data jsonb;diagnostics jsonb;begin
 data=public.platform_repair_context_data_before_controller_v4(p_task);
 if data is null then return null;end if;
 select coalesce(jsonb_agg(value order by created_at,id),'[]') into diagnostics from (
  select d.id,d.created_at,public.research_queued_dispatch_diagnostic(d.id,d.request_sha256) value
  from public.research_model_dispatches d where d.study_id=(data->>'assessment_id')::uuid
   and d.task_id=(data->>'assessment_task_id')::uuid and d.status='queued'
  order by d.created_at,d.id limit 8)x;
 return data||jsonb_build_object('queued_admission_diagnostics',diagnostics,'evidence_revision',
  encode(sha256(convert_to(jsonb_build_object('previous',data->>'evidence_revision','queued_admission_diagnostics',diagnostics)::text,'UTF8')),'hex'));
end$$;
revoke all on function public.platform_repair_context_data(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
