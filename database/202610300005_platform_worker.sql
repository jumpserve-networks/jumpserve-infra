begin;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.platform_settings;t public.platform_tasks;a public.platform_authorizations;r public.platform_runs;
 artifact public.platform_artifacts;op public.platform_operations;c public.platform_changes;release public.platform_releases;
 result jsonb;ident uuid;previous_status text;begin
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict s from public.platform_settings where id for update;
 if p_worker is null or jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'Invalid platform worker request';end if;
 if p_operation='maintenance' then
  if s.paused or s.authorization_version is null then return null;end if;
  select * into strict a from public.platform_authorizations where version=s.authorization_version;
  if a.policy_sha256 is distinct from p_payload->>'policy_sha256' then raise exception 'Installed policy differs from standing authorization';end if;
  if exists(select 1 from public.platform_tasks where status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling')) or exists(select 1 from public.platform_events where kind='maintenance-queued' and created_at>clock_timestamp()-interval '24 hours') then return null;end if;
  if not exists(select 1 from public.platform_operators where role='owner') then return null;end if;
  ident=gen_random_uuid();
  insert into public.platform_tasks(id,requested_by,title,objective,repositories,authorization_version,max_reserved_cents,deadline_at)
   values(ident,(select user_id from public.platform_operators where role='owner' order by created_at,user_id limit 1),'Improve JumpServe reliability',
   'Inspect the three repositories for a concrete reliability, usability or maintainability improvement. Diagnose the issue, implement a focused correction, run the fixed checks and release only a qualified change. Preserve scientific criteria, measurements, evidence, privacy and existing behavior. If no justified change is found, record that outcome rather than manufacture work.',
   array['jumpserve-networks/jumpserve-front-end','jumpserve-networks/jumpserve-back-end','jumpserve-networks/jumpserve-infra'],s.authorization_version,10000,clock_timestamp()+interval '6 hours');
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),ident,'supervisor','maintenance-queued','Daily maintenance admitted within a six-hour, $100 reservation limit; actual subscription charges remain unknown.','{}');
  return jsonb_build_object('task_id',ident);
 end if;
 if p_operation='heartbeat' then
  if length(coalesce(p_payload->>'status','')) not between 1 and 80 or length(coalesce(p_payload->>'reason',''))>1000 then raise exception 'Invalid worker heartbeat';end if;
  update public.platform_settings set worker_id=p_worker,worker_seen_at=clock_timestamp(),worker_status=p_payload->>'status',worker_reason=p_payload->>'reason',updated_at=clock_timestamp() where id;
  return jsonb_build_object('paused',s.paused,'automatic_releases',s.automatic_releases,'authorization_version',s.authorization_version);
 elsif p_operation='claim' then
  if s.authorization_version is null then return null;end if;
  if to_regclass('public.research_model_dispatches') is not null then
   if to_regclass('public.research_autonomy_tasks') is not null then
    execute 'select to_jsonb(exists(select 1 from public.research_model_dispatches d where d.status=''running'' or d.status=''queued'' and exists(select 1 from public.research_autonomy_tasks q where q.id=d.task_id and q.status=''running'' and q.lease_until>clock_timestamp())))' into result;
   else execute 'select to_jsonb(exists(select 1 from public.research_model_dispatches where status in (''queued'',''running'')))' into result;end if;
   if result='true'::jsonb then return null;end if;
  end if;
  select * into strict a from public.platform_authorizations where version=s.authorization_version;
  if a.policy_sha256 is distinct from p_payload->>'policy_sha256' then raise exception 'Installed policy differs from standing authorization';end if;
  update public.platform_tasks set status='reconciling',reason='Worker lease expired; reconcile original calls and release identities before new work.',lease_token=null,lease_until=null,updated_at=clock_timestamp()
   where lease_token is not null and lease_until<=clock_timestamp();
  if exists(select 1 from public.platform_tasks where lease_token is not null and lease_until>clock_timestamp()) then return null;end if;
  select * into t from public.platform_tasks where lease_token is null and authorization_version=s.authorization_version and status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling')
   and (not s.paused or status='reconciling')
   and coalesce((checkpoint->>'not_before')::timestamptz,'-infinity'::timestamptz)<=clock_timestamp()
   order by case when status='reconciling' then 0 else 1 end,priority,created_at,id limit 1 for update;
  if not found then return null;end if;
  update public.platform_tasks set lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '240 seconds',worker_id=p_worker,
   status=case when status='queued' then 'investigating' else status end,updated_at=clock_timestamp() where id=t.id returning * into t;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','claimed','Supervisor acquired a bounded task lease.',jsonb_build_object('stage',t.status));
  return to_jsonb(t);
 end if;
 select * into strict t from public.platform_tasks where id=p_task for update;
 if p_token is null or t.worker_id is distinct from p_worker or t.lease_token is distinct from p_token or t.lease_until is null or t.lease_until<=clock_timestamp() then raise exception 'Current platform worker lease required';end if;
 if p_operation='progress' then
  if octet_length(coalesce(p_payload->'checkpoint','{}')::text)>1000000 then raise exception 'Platform checkpoint exceeds its bound';end if;
  update public.platform_tasks set checkpoint=coalesce(p_payload->'checkpoint','{}'),updated_at=clock_timestamp() where id=t.id;
  return jsonb_build_object('recorded',true);
 elsif p_operation='lease' then
  update public.platform_tasks set lease_until=clock_timestamp()+interval '240 seconds' where id=t.id;
  return jsonb_build_object('paused',s.paused,'automatic_releases',s.automatic_releases,'cancel_requested',t.cancel_requested,'deadline_at',t.deadline_at,'committed_cents',t.committed_cents,'max_reserved_cents',t.max_reserved_cents);
 elsif p_operation='event' then
  ident=(p_payload->>'id')::uuid;
  if length(coalesce(p_payload->>'message','')) not between 1 and 4000 or octet_length(coalesce(p_payload->'details','{}')::text)>32000 then raise exception 'Event exceeds its bounded projection';end if;
  if exists(select 1 from public.platform_events where id=ident) then
   if not exists(select 1 from public.platform_events where id=ident and task_id=t.id and kind=p_payload->>'kind' and message=p_payload->>'message' and details=coalesce(p_payload->'details','{}')) then raise exception 'Event identity differs';end if;
  else insert into public.platform_events(id,task_id,actor,kind,message,details) values(ident,t.id,'supervisor',p_payload->>'kind',p_payload->>'message',coalesce(p_payload->'details','{}'));end if;
  return jsonb_build_object('recorded',true);
 elsif p_operation='artifact' then
  ident=(p_payload->>'id')::uuid;
  select * into artifact from public.platform_artifacts where id=ident;
  if found then
   if artifact.task_id<>t.id or artifact.sha256 is distinct from p_payload->>'sha256' or artifact.name is distinct from p_payload->>'name' or artifact.provenance is distinct from p_payload->'provenance' then raise exception 'Artifact original is immutable';end if;
   return to_jsonb(artifact);
  end if;
  if p_payload->>'storage_path' is distinct from t.id::text||'/'||(p_payload->>'sha256') or length(coalesce(p_payload->>'name','')) not between 1 and 200 then raise exception 'Artifact identity differs';end if;
  insert into public.platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance)
   values(ident,t.id,p_payload->>'name',p_payload->>'sha256',(p_payload->>'byte_count')::integer,p_payload->>'storage_path',p_payload->>'media_type',p_payload->'provenance') returning * into artifact;
  return to_jsonb(artifact);
 elsif p_operation='begin-run' then
  if s.paused or t.cancel_requested or t.deadline_at<=clock_timestamp()+interval '90 seconds' then return jsonb_build_object('denied','paused-cancelled-or-deadline');end if;
  if exists(select 1 from public.platform_runs pr where pr.task_id=t.id and (pr.status='running' or pr.status='unknown' and not exists(select 1 from public.platform_run_reconciliations rr where rr.run_id=pr.id))) then return jsonb_build_object('denied','unconfirmed-model-call');end if;
  if t.committed_cents+100>t.max_reserved_cents then return jsonb_build_object('denied','budget');end if;
  if not exists(select 1 from public.platform_artifacts where id=(p_payload->>'request_artifact_id')::uuid and task_id=t.id and sha256=p_payload->>'request_sha256') then raise exception 'Original model request required before transport';end if;
  ident=(p_payload->>'id')::uuid;
  if exists(select 1 from public.platform_runs where id=ident) then return jsonb_build_object('denied','retained-model-call');end if;
  update public.platform_tasks set committed_cents=committed_cents+100 where id=t.id;
  insert into public.platform_runs(id,task_id,number,request_sha256,request_artifact_id,reserved_cents)
   values(ident,t.id,(select coalesce(max(number),0)+1 from public.platform_runs where task_id=t.id),p_payload->>'request_sha256',(p_payload->>'request_artifact_id')::uuid,100) returning * into r;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','model-started','Original model request persisted and reserved before transport.',jsonb_build_object('run_id',r.id,'number',r.number,'request_sha256',r.request_sha256));
  return to_jsonb(r);
 elsif p_operation='finish-run' then
  select * into strict r from public.platform_runs where id=(p_payload->>'id')::uuid and task_id=t.id for update;
  if r.status<>'running' then
   if r.status=p_payload->>'status' and r.response_artifact_id is not distinct from (p_payload->>'response_artifact_id')::uuid then return to_jsonb(r);end if;
   raise exception 'Original terminal model outcome is immutable';
  end if;
  if p_payload->>'status' not in ('complete','failed','unknown') then raise exception 'Invalid model result';end if;
  if p_payload->>'response_artifact_id' is not null and not exists(select 1 from public.platform_artifacts where task_id=t.id and id=(p_payload->>'response_artifact_id')::uuid) then raise exception 'Original response artifact required';end if;
  if p_payload->>'status'='complete' and p_payload->>'response_artifact_id' is null then raise exception 'Complete response bytes required';end if;
  update public.platform_runs set status=p_payload->>'status',response_artifact_id=(p_payload->>'response_artifact_id')::uuid,usage=p_payload->'usage',reason=p_payload->>'reason',ended_at=clock_timestamp() where id=r.id returning * into r;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','model-'||r.status,'Model outcome recorded; unknown calls cannot be replayed.',jsonb_build_object('run_id',r.id,'status',r.status,'response_artifact_id',r.response_artifact_id));
  return to_jsonb(r);
 elsif p_operation='reconcile-run' then
  select * into strict r from public.platform_runs where id=(p_payload->>'id')::uuid and task_id=t.id;
  if r.status<>'unknown' or p_payload->'proof'->>'request_sha256' is distinct from r.request_sha256 or p_payload->'proof'->>'status' is distinct from 'complete' then raise exception 'Original unknown identity and verified terminal stream required';end if;
  if not exists(select 1 from public.platform_artifacts where id=(p_payload->>'artifact_id')::uuid and task_id=t.id) then raise exception 'Retained reconciliation proof required';end if;
  insert into public.platform_run_reconciliations(run_id,task_id,artifact_id,proof) values(r.id,t.id,(p_payload->>'artifact_id')::uuid,p_payload->'proof') on conflict(run_id) do nothing;
  if not exists(select 1 from public.platform_run_reconciliations where run_id=r.id and proof=p_payload->'proof' and artifact_id=(p_payload->>'artifact_id')::uuid) then raise exception 'Reconciliation proof is immutable';end if;
  return jsonb_build_object('reconciled',true,'original_status',r.status);
 elsif p_operation='begin-operation' then
  ident=(p_payload->>'id')::uuid;
  select * into op from public.platform_operations where id=ident;
  if found then
   if op.task_id<>t.id or op.kind is distinct from p_payload->>'kind' or op.request_sha256 is distinct from p_payload->>'request_sha256' or op.request is distinct from p_payload->'request' then raise exception 'Operation identity differs';end if;
   return to_jsonb(op)||jsonb_build_object('replayed',true);
  end if;
  if s.paused or t.cancel_requested or t.deadline_at<=clock_timestamp() then raise exception 'New external actions are stopped';end if;
  if p_payload->>'kind' in ('merge','deploy','rollback') and not s.automatic_releases then raise exception 'Automatic release authority disabled';end if;
  if exists(select 1 from public.platform_runs pr where pr.task_id=t.id and (pr.status='running' or pr.status='unknown' and not exists(select 1 from public.platform_run_reconciliations rr where rr.run_id=pr.id))) then raise exception 'Unconfirmed model calls must reconcile first';end if;
  insert into public.platform_operations(id,task_id,kind,request_sha256,request) values(ident,t.id,p_payload->>'kind',p_payload->>'request_sha256',p_payload->'request') returning * into op;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','operation-intent','External action intent persisted before dispatch.',jsonb_build_object('operation_id',op.id,'operation',op.kind,'request_sha256',op.request_sha256));
  return to_jsonb(op)||jsonb_build_object('replayed',false);
 elsif p_operation='finish-operation' then
  select * into strict op from public.platform_operations where id=(p_payload->>'id')::uuid and task_id=t.id for update;
  if op.request_sha256 is distinct from p_payload->>'request_sha256' then raise exception 'Original operation hash required';end if;
  if p_payload->>'status' not in ('confirmed','failed','unknown') or octet_length(coalesce(p_payload->'result','{}')::text)>32000 then raise exception 'Invalid operation receipt';end if;
  if op.status in ('confirmed','failed') and (op.status,op.result) is distinct from (p_payload->>'status',p_payload->'result') then raise exception 'Terminal operation receipt cannot change';end if;
  previous_status=op.status;
  update public.platform_operations set status=p_payload->>'status',result=p_payload->'result',updated_at=clock_timestamp() where id=op.id returning * into op;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','operation-'||op.status,'External action result or reconciliation recorded.',jsonb_build_object('operation_id',op.id,'operation',op.kind,'previous_status',previous_status,'status',op.status,'result',op.result));
  return to_jsonb(op);
 elsif p_operation='change' then
  if not p_payload->>'repository'=any(t.repositories) then raise exception 'Change repository is outside this task';end if;
  ident=(p_payload->>'id')::uuid;
  if not exists(select 1 from public.platform_artifacts where id=(p_payload->>'patch_artifact_id')::uuid and task_id=t.id) or not exists(select 1 from public.platform_artifacts where id=(p_payload->>'checks_artifact_id')::uuid and task_id=t.id) then raise exception 'Frozen patch and executed checks required';end if;
  select * into c from public.platform_changes where id=ident;
  if found and (c.task_id,c.repository,c.base_sha,c.tree_sha256,c.patch_artifact_id,c.checks_artifact_id) is distinct from (t.id,p_payload->>'repository',p_payload->>'base_sha',p_payload->>'tree_sha256',(p_payload->>'patch_artifact_id')::uuid,(p_payload->>'checks_artifact_id')::uuid) then raise exception 'Tested change identity is immutable';end if;
  if found and c.merge_sha is not null and c.merge_sha is distinct from p_payload->>'merge_sha' then raise exception 'Original merge identity is immutable';end if;
  insert into public.platform_changes(id,task_id,repository,base_sha,head_sha,tree_sha256,summary,patch_artifact_id,checks_artifact_id,pr_number,pr_url,merge_sha,status,details)
   values(ident,t.id,p_payload->>'repository',p_payload->>'base_sha',p_payload->>'head_sha',p_payload->>'tree_sha256',p_payload->>'summary',(p_payload->>'patch_artifact_id')::uuid,(p_payload->>'checks_artifact_id')::uuid,(p_payload->>'pr_number')::integer,p_payload->>'pr_url',p_payload->>'merge_sha',p_payload->>'status',coalesce(p_payload->'details','{}'))
   on conflict(id) do update set head_sha=excluded.head_sha,pr_number=excluded.pr_number,pr_url=excluded.pr_url,merge_sha=excluded.merge_sha,status=excluded.status,details=excluded.details,updated_at=clock_timestamp() returning * into c;
  return to_jsonb(c);
 elsif p_operation='release' then
  if not p_payload->>'repository'=any(t.repositories) then raise exception 'Release repository is outside this task';end if;
  ident=(p_payload->>'id')::uuid;
  select * into release from public.platform_releases where id=ident;
  if found and (release.task_id,release.component,release.repository,release.revision) is distinct from (t.id,p_payload->>'component',p_payload->>'repository',p_payload->>'revision') then raise exception 'Release identity is immutable';end if;
  if p_payload->>'status'='verified' and (p_payload->'verification'->>'passed' is distinct from 'true' or p_payload->'verification'->>'revision' is distinct from p_payload->>'revision') then raise exception 'Exact production revision verification required';end if;
  insert into public.platform_releases(id,task_id,component,repository,revision,status,external_id,verification,details) values(ident,t.id,p_payload->>'component',p_payload->>'repository',p_payload->>'revision',p_payload->>'status',p_payload->>'external_id',p_payload->'verification',coalesce(p_payload->'details','{}'))
   on conflict(id) do update set status=excluded.status,external_id=excluded.external_id,verification=excluded.verification,details=excluded.details,updated_at=clock_timestamp() returning * into release;
  return to_jsonb(release);
 elsif p_operation='checkpoint' then
  if p_payload->>'status' not in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling','completed','rolled-back','blocked','cancelled','deadline','budget') or length(coalesce(p_payload->>'reason','')) not between 1 and 4000 or octet_length(coalesce(p_payload->'checkpoint','{}')::text)>1000000 then raise exception 'Invalid platform checkpoint';end if;
  if p_payload->>'status'='completed' and (not exists(select 1 from public.platform_releases where task_id=t.id) or exists(select 1 from public.platform_releases where task_id=t.id and status<>'verified') or exists(select 1 from public.platform_changes pc where pc.task_id=t.id and pc.status<>'superseded' and (pc.merge_sha is null or not exists(select 1 from public.platform_releases pr where pr.task_id=t.id and pr.repository=pc.repository and pr.revision=pc.merge_sha and pr.status='verified'))) or exists(select 1 from public.platform_operations where task_id=t.id and status in ('pending','unknown')) or exists(select 1 from public.platform_runs pr where pr.task_id=t.id and (pr.status='running' or pr.status='unknown' and not exists(select 1 from public.platform_run_reconciliations rr where rr.run_id=pr.id)))) then raise exception 'Recorded production verification required before completion';end if;
  update public.platform_tasks set status=p_payload->>'status',reason=p_payload->>'reason',checkpoint=coalesce(p_payload->'checkpoint','{}'),lease_token=null,lease_until=null,updated_at=clock_timestamp() where id=t.id;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor',p_payload->>'status',p_payload->>'reason',jsonb_build_object('stage',p_payload->>'status'));
  return jsonb_build_object('recorded',true,'status',p_payload->>'status');
 end if;
 raise exception 'Unsupported platform worker operation';
end$$;
revoke all on function public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
