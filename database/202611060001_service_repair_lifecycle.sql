begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Consumption survives stale checkpoint delivery. Historical activations and
-- repeated events remain intact; neither an old wait nor an old lease rearms it.
create table public.platform_service_work_resumptions (
 request_id uuid primary key references public.platform_service_work_requests(id),
 parent_task_id uuid not null references public.platform_tasks(id),
 operation_id uuid not null references public.platform_operations(id),
 revision text not null check(revision~'^[a-f0-9]{40}$'),
 created_at timestamptz not null default clock_timestamp()
);
alter table public.platform_service_work_resumptions enable row level security;
revoke all on public.platform_service_work_resumptions from public,anon,authenticated,service_role;
grant select on public.platform_service_work_resumptions to service_role;
create trigger service_resumption_immutable before update or delete on public.platform_service_work_resumptions
 for each row execute function public.platform_immutable();
insert into public.platform_service_work_resumptions(request_id,parent_task_id,operation_id,revision)
 select q.id,q.parent_task_id,a.operation_id,a.revision from public.platform_service_work_requests q
 join public.platform_service_work_activations a on a.request_id=q.id
 join public.platform_tasks p on p.id=q.parent_task_id
 join public.platform_operations o on o.id=a.operation_id and o.status='confirmed'
 where exists(select 1 from public.platform_releases l where l.task_id=q.implementation_task_id and l.component='infrastructure'
  and l.revision=a.revision and l.external_id=a.operation_id::text and l.status='verified')
 and (p.checkpoint->>'service_work_activation'=q.id::text or exists(select 1 from public.platform_events e
  where e.task_id=q.parent_task_id and e.kind='service-parent-resumed'
   and e.details->>'request_id'=q.id::text and e.details->>'operation_id'=a.operation_id::text));

create or replace function public.platform_service_work_resume() returns void
language plpgsql security definer set search_path='' as $$declare r record;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 if exists(select 1 from public.platform_settings where id and paused) then return;end if;
 for r in select q.*,a.revision,a.operation_id from public.platform_service_work_requests q
  join public.platform_service_work_activations a on a.request_id=q.id
  join public.platform_tasks p on p.id=q.parent_task_id
  where p.status='blocked' and p.lease_token is null and not p.cancel_requested and p.deadline_at>clock_timestamp()
   and p.checkpoint->'service_work_wait'->>'id'=q.id::text
   and not exists(select 1 from public.platform_service_work_resumptions consumed where consumed.request_id=q.id)
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
  for update of p
 loop
  insert into public.platform_service_work_resumptions(request_id,parent_task_id,operation_id,revision)
   values(r.id,r.parent_task_id,r.operation_id,r.revision) on conflict(request_id) do nothing;
  if not found then continue;end if;
  update public.platform_tasks set status='implementing',reason='Infrastructure service has a verified release; continuing the retained parent work.',
   checkpoint=(checkpoint-'not_before'-'pending_service_work')||jsonb_build_object('service_work_activation',r.id),updated_at=clock_timestamp() where id=r.parent_task_id;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),r.parent_task_id,'service-broker','service-parent-resumed',
   'Infrastructure-owned service activated and verified; original task may continue without resetting limits or uncertain outcomes.',jsonb_build_object('request_id',r.id,'operation_id',r.operation_id,'revision',r.revision,'scientific_completion',false));
 end loop;
end $$;

-- Continuation attempts are repair roots too. Capability/service descendants
-- retain their own outcome; resolving a paper does not certify their code.
create view public.platform_assessment_repair_roots as
 select blocker_id,platform_task_id from public.platform_assessment_repair_links
 union select blocker_id,platform_task_id from public.platform_assessment_repair_attempts;
revoke all on public.platform_assessment_repair_roots from public,anon,authenticated,service_role;

create function public.platform_intake_incident_resolution(p_blocker uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare b public.platform_assessment_blockers;t public.research_autonomy_tasks;v public.research_paper_reviews;
 a record;witnesses jsonb;chunks integer;begin
 select * into b from public.platform_assessment_blockers where id=p_blocker;
 if not found or b.stage<>'intake' or b.source_kind<>'task' then return null;end if;
 select * into t from public.research_autonomy_tasks where id=b.assessment_task_id and study_id=b.study_id;
 if not found or b.source_id<>t.id or t.stage<>'intake' or t.claim_id is not null or t.intake_parent_id is not null
  or t.status<>'finished' or t.lease_token is not null then return null;end if;
 if not exists(select 1 from public.research_autonomy_workflows where study_id=b.study_id
  and status in ('running','completed-with-blockers','completed') and deadline_at>statement_timestamp()) then return null;end if;
 select * into v from public.research_paper_reviews where study_id=b.study_id;
 if not found or v.status not in ('ready','confirmed') or jsonb_array_length(v.seeds)=0
  or v.metadata->'selection'->>'status' is distinct from 'ready'
  or v.metadata->'selection'->'candidate_count' is distinct from to_jsonb(jsonb_array_length(v.seeds)) then return null;end if;
 select q.id request_id,x.operation_id,x.revision,x.verification,e.details,e.created_at recovered_at into a
 from public.platform_service_work_requests q join public.platform_service_work_activations x on x.request_id=q.id
 join public.platform_operations o on o.id=x.operation_id and o.status='confirmed'
 join public.research_autonomy_events e on e.study_id=b.study_id and e.task_id=t.id and e.event='infrastructure-service-intake-recovered'
  and e.details->>'request_id'=q.id::text and e.details->>'operation_id'=x.operation_id::text
 join public.research_artifacts text_artifact on text_artifact.study_id=b.study_id and text_artifact.id::text=x.verification->>'text_artifact_id'
  and text_artifact.sha256=x.verification->>'text_sha256' and text_artifact.verified_at is not null
  and text_artifact.provenance->>'kind'='derived-pdf-text'
 join public.research_artifacts original on original.study_id=b.study_id and original.id::text=x.verification->>'original_artifact_id'
  and text_artifact.provenance->>'original_artifact_id'=original.id::text and text_artifact.provenance->>'original_sha256'=original.sha256
 join public.research_artifacts failure on failure.study_id=b.study_id and failure.id::text=x.verification->>'failure_artifact_id'
  and failure.sha256=x.verification->>'failure_sha256' and failure.provenance->>'kind'='failed-text-extraction'
  and failure.provenance->>'original_artifact_id'=original.id::text
 join public.research_sources source on source.study_id=b.study_id and source.id::text=x.verification->>'source_id' and source.sha256=original.sha256
 where q.profile='intake-parser-recovery-v1' and exists(select 1 from public.platform_assessment_repair_bindings l where l.platform_task_id=q.parent_task_id and l.blocker_id=b.id)
  and x.verification->>'passed'='true' and x.verification->>'provider_calls'='0' and x.verification->>'scientific_completion'='false'
  and x.verification->>'original_reason_sha256'=b.original_reason_sha256
  and encode(sha256(convert_to(e.details->>'original_reason','UTF8')),'hex')=b.original_reason_sha256
  and e.details->'original_context'='{"intake_pool_version":"warm-intake-v1"}'::jsonb and e.details->>'original_attempts'='0'
  and e.details->>'provider_replay'='false' and e.details->>'text_artifact_id'=text_artifact.id::text
  and t.context->>'source_id'=source.id::text and t.context->>'text_artifact_id'=text_artifact.id::text
  and e.created_at>b.created_at and v.updated_at>=x.created_at
  and exists(select 1 from public.platform_releases r where r.task_id=q.implementation_task_id and r.component='infrastructure'
   and r.revision=x.revision and r.external_id=x.operation_id::text and r.status='verified')
 order by x.created_at,x.request_id limit 1;
 if not found then return null;end if;
 select count(*) into chunks from public.research_autonomy_tasks where intake_parent_id=t.id;
 if chunks=0 or t.context->'chunk_index' is distinct from to_jsonb(chunks)
  or (select min(intake_chunk_index)<>0 or max(intake_chunk_index)<>chunks-1 from public.research_autonomy_tasks where intake_parent_id=t.id)
  or exists(select 1 from public.research_autonomy_tasks child where child.intake_parent_id=t.id and (child.study_id<>b.study_id or child.status<>'finished'
   or child.lease_token is not null or child.context->>'text_artifact_id' is distinct from t.context->>'text_artifact_id'
   or child.context->>'source_id' is distinct from t.context->>'source_id')) then return null;end if;
 if exists(select 1 from public.research_autonomy_turns z join public.research_autonomy_tasks task on task.id=z.task_id
   where (task.id=t.id or task.intake_parent_id=t.id) and z.status in ('running','unknown'))
  or exists(select 1 from public.research_model_dispatches d join public.research_autonomy_tasks task on task.id=d.task_id
   where (task.id=t.id or task.intake_parent_id=t.id) and d.status in ('queued','running','unknown'))
  or exists(select 1 from public.research_builder_calls c join public.research_autonomy_tasks task on task.id=c.task_id
   where (task.id=t.id or task.intake_parent_id=t.id) and c.status in ('running','unknown')) then return null;end if;
 select jsonb_agg(jsonb_build_object('task_id',task.id,'turn_id',z.id,'request_sha256',z.request_sha256,
   'response_sha256',z.response_sha256,'artifact_id',d.response_artifact_id,'artifact_sha256',artifact.sha256) order by task.id) into witnesses
 from public.research_autonomy_tasks task join public.research_autonomy_turns z on z.task_id=task.id and z.study_id=b.study_id
  and z.id::text=case when task.id=t.id then v.metadata->'selection'->>'last_turn_id' else task.context->>'last_turn_id' end
  and z.status='complete' and z.ended_at is not null and z.response_sha256 is not null and z.created_at>a.recovered_at
 join public.research_model_dispatches d on d.id=z.id and d.task_id=task.id and d.study_id=b.study_id and d.status='complete'
  and d.request_sha256=z.request_sha256
 join public.research_artifacts artifact on artifact.id=d.response_artifact_id and artifact.study_id=b.study_id and artifact.sha256=d.response_sha256
 where task.id=t.id or task.intake_parent_id=t.id;
 if coalesce(jsonb_array_length(witnesses),0)<>chunks+1 then return null;end if;
 return jsonb_build_object('version','platform-incident-closure-v1','resolution_kind','intake-preparation-completed',
  'blocker_id',b.id,'assessment_id',b.study_id,'assessment_task_id',t.id,'service_request_id',a.request_id,'operation_id',a.operation_id,'revision',a.revision,
  'text_artifact_id',a.verification->>'text_artifact_id','text_sha256',a.verification->>'text_sha256',
  'candidate_count',jsonb_array_length(v.seeds),'review_revision',v.revision,'completed_chunks',chunks,'continuation_witnesses',witnesses,
  'outcome','resolved-with-recorded-continuation','qualified_platform_change',false,'scientific_completion',false,'provider_replay',false);
end $$;

-- Keep the earlier general-repair proof intact and preserve its public OID.
do $$declare definition text;begin
 definition=pg_get_functiondef('public.platform_assessment_incident_resolution(uuid)'::regprocedure);
 if strpos(definition,'FUNCTION public.platform_assessment_incident_resolution(')=0 then raise exception 'Unexpected original incident resolver';end if;
 execute replace(definition,'FUNCTION public.platform_assessment_incident_resolution(','FUNCTION public.platform_assessment_incident_resolution_before_intake_v1(');
end $$;
create or replace function public.platform_assessment_incident_resolution(p_blocker uuid) returns jsonb
language sql stable security definer set search_path='' as $$
 select coalesce(public.platform_assessment_incident_resolution_before_intake_v1(p_blocker),public.platform_intake_incident_resolution(p_blocker))
$$;

do $$declare definition text;p record;n integer=0;needle text;begin
 definition=pg_get_functiondef('public.platform_close_resolved_incidents(uuid)'::regprocedure);
 needle='proof=public.platform_assessment_incident_resolution(b.id);if proof is null then continue;end if;';
 if strpos(definition,'public.platform_assessment_repair_bindings')=0 or strpos(definition,needle)=0 then raise exception 'Unexpected closure root selector';end if;
 execute replace(definition,needle,needle||$guard$
  if proof->>'resolution_kind'='intake-preparation-completed' and not exists(select 1 from public.platform_assessment_repair_roots root where root.platform_task_id=t.id and root.blocker_id=b.id) then continue;end if;$guard$);
 for p in select oid from pg_proc where pronamespace='public'::regnamespace
  and strpos(prosrc,'Exact quiescent no-change incident closure required')>0 loop
  definition=pg_get_functiondef(p.oid);
  if (length(definition)-length(replace(definition,'public.platform_assessment_repair_bindings','')))/length('public.platform_assessment_repair_bindings')<>2
   then raise exception 'Unexpected authenticated closure bindings';end if;
  -- A closure for another continuation cannot certify an outstanding patch
  -- or an uncertain call on this root. Those tasks retire through cancellation.
  definition=replace(definition,'where l.platform_task_id=p_task;',$guard$where l.platform_task_id=p_task
   and (c.proof->>'resolution_kind' is distinct from 'intake-preparation-completed'
    or exists(select 1 from public.platform_assessment_repair_roots root where root.platform_task_id=p_task and root.blocker_id=l.blocker_id))
   and not exists(select 1 from public.platform_changes where task_id=p_task)
   and not exists(select 1 from public.platform_releases where task_id=p_task)
   and not exists(select 1 from public.platform_runs where task_id=p_task and status in ('running','unknown'))
   and not exists(select 1 from public.platform_operations where task_id=p_task and status in ('pending','unknown'))
   and not exists(select 1 from public.platform_tasks where id=p_task and checkpoint->>'cleanup_unknown'='true');$guard$);
  execute definition;n=n+1;
 end loop;
 if n<>1 then raise exception 'Expected one authenticated closure wrapper';end if;
end $$;

create function public.platform_retire_intake_repair_dependencies() returns void
language plpgsql security definer set search_path='' as $$declare child public.platform_tasks;closure record;busy boolean;b record;proof jsonb;begin
 if exists(select 1 from public.platform_settings where id and paused) then return;end if;
 -- Proven preparation can resolve an incident even when its platform candidate
 -- must be retained/reconciled instead of being certified as a completed fix.
 for b in with candidates as materialized (
  select signal.id,public.platform_intake_incident_resolution(signal.id) proof
  from public.platform_assessment_blockers signal join public.research_autonomy_tasks task on task.id=signal.assessment_task_id and task.study_id=signal.study_id
  join public.research_paper_reviews review on review.study_id=signal.study_id
  where signal.stage='intake' and signal.source_kind='task' and task.status='finished' and review.status in ('ready','confirmed')
   and not exists(select 1 from public.platform_assessment_incident_closures closed where closed.blocker_id=signal.id)
   and exists(select 1 from public.platform_service_work_requests requested join public.platform_service_work_activations activated on activated.request_id=requested.id
    join public.platform_assessment_repair_bindings binding on binding.platform_task_id=requested.parent_task_id
    where requested.profile='intake-parser-recovery-v1' and binding.blocker_id=signal.id)
 ) select available.id,available.proof from candidates available where available.proof is not null order by available.id limit 64 loop
  proof=b.proof;
  if proof is not null then
   insert into public.platform_assessment_incident_closures(blocker_id,proof) values(b.id,proof) on conflict(blocker_id) do nothing;
   if found then insert into public.platform_events(id,actor,kind,message,details) values(gen_random_uuid(),'assessment-monitor','assessment-intake-incident-resolved',
    'The exact intake incident has verified preparation evidence. This is not a qualification of any remaining platform candidate or a scientific finding.',proof);end if;
  end if;
 end loop;
 for child in select t.* from public.platform_tasks t where not t.cancel_requested and t.deadline_at>clock_timestamp()
  and t.status not in ('completed','rolled-back','cancelled','deadline','budget')
  and exists(select 1 from public.platform_assessment_repair_bindings binding join public.platform_assessment_incident_closures closed on closed.blocker_id=binding.blocker_id
   where binding.platform_task_id=t.id and closed.proof->>'resolution_kind'='intake-preparation-completed')
  and not (exists(select 1 from public.platform_assessment_repair_roots root where root.platform_task_id=t.id)
   and not exists(select 1 from public.platform_changes where task_id=t.id)
   and not exists(select 1 from public.platform_releases where task_id=t.id)
   and not exists(select 1 from public.platform_runs where task_id=t.id and status in ('running','unknown'))
   and not exists(select 1 from public.platform_operations where task_id=t.id and status in ('pending','unknown'))
   and coalesce(t.checkpoint->>'cleanup_unknown','false')<>'true') for update of t
 loop
  select binding.platform_task_id,closed.blocker_id into strict closure from public.platform_assessment_repair_bindings binding
   join public.platform_assessment_incident_closures closed on closed.blocker_id=binding.blocker_id
   where binding.platform_task_id=child.id and closed.proof->>'resolution_kind'='intake-preparation-completed' order by closed.blocker_id limit 1;
  busy=child.checkpoint->>'cleanup_unknown'='true'
   or exists(select 1 from public.platform_runs r where r.task_id=child.id and (r.status='running' or r.status='unknown'
    and not exists(select 1 from public.platform_run_reconciliations reconciled where reconciled.run_id=r.id)))
   or exists(select 1 from public.platform_operations o where o.task_id=child.id and o.status in ('pending','unknown'));
  update public.platform_tasks set cancel_requested=true,
   status=case when child.lease_token is not null then child.status when busy then 'reconciling' else 'cancelled' end,
   reason='Repair dependency retired because the exact original intake incident has a verified completion. Pending original outcomes still require reconciliation.',
   checkpoint=checkpoint||jsonb_build_object('incident_retirement',jsonb_build_object('blocker_id',closure.blocker_id,'previous_status',child.status)),updated_at=clock_timestamp() where id=child.id;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),child.id,'assessment-monitor','resolved-intake-dependency-retired',
   'No further repair is needed for this completed intake incident. Original candidate files, outcomes, calls and limits are retained; active or uncertain actions reconcile before stopping.',
   jsonb_build_object('blocker_id',closure.blocker_id,'previous_status',child.status,'reconciliation_required',coalesce(busy,false),'scientific_completion',false));
 end loop;
end $$;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_service_lifecycle_v1;
revoke all on function public.platform_worker_before_service_lifecycle_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$declare result jsonb;begin
 if p_operation in ('maintenance','claim','lease','begin-run','begin-operation','checkpoint','release','finish-operation') then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 end if;
 if p_operation in ('begin-run','begin-operation') then
  -- Authenticate the existing lease before retirement, and stop unnecessary
  -- work before the frozen admission functions reserve or dispatch anything.
  perform public.platform_worker_before_service_lifecycle_v1('lease',p_worker,p_task,p_token,'{}');
  if not exists(select 1 from public.platform_settings where id and paused) then
   perform public.platform_close_resolved_incidents();perform public.platform_retire_intake_repair_dependencies();
  end if;
 end if;
 result=public.platform_worker_before_service_lifecycle_v1(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation in ('maintenance','claim','lease','begin-run','begin-operation','checkpoint','release','finish-operation') then
  if not exists(select 1 from public.platform_settings where id and paused) then
   perform public.platform_close_resolved_incidents();perform public.platform_retire_intake_repair_dependencies();
  end if;
 end if;
 if p_operation='lease' and exists(select 1 from public.platform_tasks where id=p_task and cancel_requested) then
  result=jsonb_set(result,'{cancel_requested}','true');
 end if;
 return result;
end $$;
revoke all on function public.platform_service_work_resume(),public.platform_intake_incident_resolution(uuid),public.platform_assessment_incident_resolution_before_intake_v1(uuid),
 public.platform_assessment_incident_resolution(uuid),public.platform_retire_intake_repair_dependencies() from public,anon,authenticated,service_role;
revoke all on function public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
