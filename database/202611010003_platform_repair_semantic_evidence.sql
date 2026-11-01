begin;
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- This projection is only a wake decision. Every original event, including its
-- full usage/timing object, remains in the private packet and immutable ledger.
create function public.platform_repair_event_evidence(value jsonb) returns jsonb
language sql immutable set search_path='' as $$
 select case when jsonb_typeof(value)='object' then value-array['created_at','updated_at','at','timestamp','revision','usage','attempts','committed_cents','lease_until','next_at'] else value end
$$;

alter function public.platform_repair_context_data(uuid) rename to platform_repair_context_data_before_semantic_v2;
revoke all on function public.platform_repair_context_data_before_semantic_v2(uuid) from public,anon,authenticated,service_role;
create function public.platform_repair_context_data(p_task uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare data jsonb;token_data jsonb;begin
 data=public.platform_repair_context_data_before_semantic_v2(p_task);
 if data is null then return null;end if;
 data=data||jsonb_build_object('evidence_revision_protocol','platform-repair-semantic-evidence-v2',
  'queued_reconciliations',coalesce((select jsonb_agg(value order by dispatch_id) from (
   select r.dispatch_id,jsonb_build_object('dispatch_id',r.dispatch_id,'request_sha256',r.request_sha256,
    'snapshot_sha256',r.snapshot_sha256,'parent_turn_status',r.parent_turn_status,'proof',r.proof) value
   from public.research_queued_dispatch_reconciliations r
   where r.study_id=(data->>'assessment_id')::uuid and r.task_id=(data->>'assessment_task_id')::uuid
   order by r.created_at desc,r.dispatch_id limit 100)x),'[]'));
 data=jsonb_set(data,'{coverage,queued_reconciliations_total}',to_jsonb((select count(*)
  from public.research_queued_dispatch_reconciliations r
  where r.study_id=(data->>'assessment_id')::uuid and r.task_id=(data->>'assessment_task_id')::uuid)));
 token_data=(data-'evidence_revision'-'repairs'-'repair_events'-'events'-'coverage')
  #- '{task,lease_until}' #- '{task,lease_token_sha256}' #- '{task,context_sha256}'
  #- '{task,status}' #- '{task,attempts}' #- '{task,references,repair_progress}' #- '{workflow,committed_cents}';
 token_data=token_data||jsonb_build_object(
  'repairs',(select coalesce(jsonb_agg(v order by v),'[]') from (select distinct
    jsonb_build_object('incident_sha256',value->'incident_sha256','evidence',value->'evidence') v
    from jsonb_array_elements(data->'repairs'))r),
  'events_sha256',(select encode(sha256(convert_to(coalesce(string_agg(v,'' order by v),''),'UTF8')),'hex') from (select distinct
    encode(sha256(convert_to(jsonb_build_object('event',e.event,
     'details',public.platform_repair_event_evidence(e.details))::text,'UTF8')),'hex') v
    from public.research_autonomy_events e
    where e.task_id=(data->>'assessment_task_id')::uuid and e.study_id=(data->>'assessment_id')::uuid
     and public.platform_repair_event_evidence(e.details)<>'{}'::jsonb)e),
  'ledger_counts',jsonb_build_object('native_calls',data->'coverage'->'native_calls_total',
    'turns',data->'coverage'->'turns_total','dispatches',data->'coverage'->'dispatches_total',
    'queued_reconciliations',data->'coverage'->'queued_reconciliations_total'));
 return data||jsonb_build_object('evidence_revision',encode(sha256(convert_to(token_data::text,'UTF8')),'hex'));
end$$;

-- Installing a different fingerprint algorithm is not new incident evidence.
-- Append a baseline without overwriting the old guard, progress or counters.
do $$declare t public.platform_tasks;packet jsonb;begin
 for t in select p.* from public.platform_tasks p join public.platform_assessment_repair_links l on l.platform_task_id=p.id
  where p.status='blocked' and p.lease_token is null and not p.cancel_requested and p.deadline_at>clock_timestamp()
   and p.checkpoint->'repair_guard'->>'version'='platform-repair-handoff-v1'
   and p.checkpoint->'repair_guard'->>'waiting'='true' for update of p
 loop
  packet=public.platform_repair_context_data(t.id);
  update public.platform_tasks set checkpoint=jsonb_set(checkpoint,'{repair_guard,semantic_baseline}',
   jsonb_build_object('version','platform-repair-semantic-evidence-v2','evidence_revision',packet->>'evidence_revision')) where id=t.id;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'interactive-migration','repair-evidence-baseline-upgraded',
   'Timing-only controller updates no longer reactivate this repair. Its original blocked report, deadline, counters and commitments are retained.',
   jsonb_build_object('previous_evidence_revision',t.checkpoint->'repair_guard'->>'evidence_revision','evidence_revision',packet->>'evidence_revision','model_calls',0));
 end loop;
end$$;

-- Preserve every existing admission/release check. Only the evidence comparison
-- understands the appended migration baseline until genuinely new data arrives.
do $$declare definition text;before text;after text;begin
 definition=pg_get_functiondef('public.platform_worker(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 before=$old$if packet->>'evidence_revision' is distinct from t.checkpoint->'repair_guard'->>'evidence_revision' then$old$;
 after=$new$if packet->>'evidence_revision' is distinct from coalesce(
   case when t.checkpoint->'repair_guard'->'semantic_baseline'->>'version'='platform-repair-semantic-evidence-v2'
    then t.checkpoint->'repair_guard'->'semantic_baseline'->>'evidence_revision' end,
   t.checkpoint->'repair_guard'->>'evidence_revision') then$new$;
 if strpos(definition,before)=0 then raise exception 'Unexpected repair evidence comparison; no admission wrapper changed';end if;
 execute replace(definition,before,after);
end$$;
revoke all on function public.platform_repair_event_evidence(jsonb),public.platform_repair_context_data(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
