begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
create table public.platform_supervisor_install_intents (
 operation_id uuid primary key references public.platform_operations(id),task_id uuid not null references public.platform_tasks(id),
 revision text not null check(revision ~ '^[a-f0-9]{40}$'),request_sha256 text not null,
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_supervisor_install_receipts (
 operation_id uuid primary key references public.platform_supervisor_install_intents(operation_id),
 command_id uuid not null unique,created_at timestamptz not null default clock_timestamp()
);
create table public.platform_supervisor_activations (
 id uuid primary key default gen_random_uuid(),operation_id uuid unique references public.platform_operations(id),
 source_revision text not null check(source_revision ~ '^[a-f0-9]{40}$'),bundle_sha256 text not null check(bundle_sha256 ~ '^[a-f0-9]{64}$'),
 manifest jsonb not null,verification jsonb not null,created_at timestamptz not null default clock_timestamp()
);
do $$declare name text;begin
 foreach name in array array['platform_supervisor_install_intents','platform_supervisor_install_receipts','platform_supervisor_activations'] loop
  execute format('alter table public.%I enable row level security',name);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',name);
  execute format('grant select on public.%I to service_role',name);
  execute format('create trigger %I before update or delete on public.%I for each row execute function public.platform_immutable()',name||'_immutable',name);
 end loop;
end$$;
create function public.platform_supervisor_runtime() returns jsonb language sql stable security definer set search_path='' as $$
 select manifest from public.platform_supervisor_activations order by created_at desc,id desc limit 1
$$;
create function public.platform_supervisor_activate(p_operation uuid,p_manifest jsonb,p_verification jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare o public.platform_operations;old public.platform_supervisor_activations;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 if p_manifest->>'version' is distinct from 'platform-supervisor-self-repair-v1'
  or p_manifest->>'source_revision' !~ '^[a-f0-9]{40}$' or p_manifest->>'bundle_sha256' !~ '^[a-f0-9]{64}$'
  or jsonb_typeof(p_manifest->'files') is distinct from 'object' or octet_length(p_manifest::text)>32000
  or not (p_manifest->'files' ?& array['policy.json','worker.py','self_runtime.py','store.py','common.py'])
  or exists(select 1 from jsonb_each_text(p_manifest->'files') f where f.key !~ '^[a-zA-Z0-9_]+\.(py|json)$' or f.value !~ '^[a-f0-9]{64}$')
  or p_verification->'passed' is distinct from 'true'::jsonb
  or p_verification->>'revision' is distinct from p_manifest->>'source_revision'
  or p_verification->>'bundle_sha256' is distinct from p_manifest->>'bundle_sha256'
  or p_verification->'installed_files_verified' is distinct from 'true'::jsonb
  then raise exception 'Exact installed supervisor source proof required';end if;
 if p_operation is null then
  select * into old from public.platform_supervisor_activations order by created_at limit 1;
  if found then
   if old.operation_id is null and old.manifest=p_manifest and old.verification=p_verification then return old.manifest;end if;
   raise exception 'Initial activation is already recorded';
  end if;
 else
  select * into strict o from public.platform_operations where id=p_operation;
  if o.request->>'component' is distinct from 'supervisor-runtime' or o.request->>'revision' is distinct from p_manifest->>'source_revision'
   or not exists(select 1 from public.platform_supervisor_install_receipts where operation_id=o.id and command_id=(p_verification->>'command_id')::uuid)
   then raise exception 'Original supervisor installation receipt required';end if;
  select * into old from public.platform_supervisor_activations where operation_id=o.id;
  if found then
   if old.manifest is distinct from p_manifest or old.verification is distinct from p_verification then raise exception 'Activation proof is immutable';end if;
   return old.manifest;
  end if;
 end if;
 insert into public.platform_supervisor_activations(operation_id,source_revision,bundle_sha256,manifest,verification)
 values(p_operation,p_manifest->>'source_revision',p_manifest->>'bundle_sha256',p_manifest,p_verification);
 if p_operation is not null then
  insert into public.research_runtime_maintenance_releases(hold_id,reason)
   select p_operation,'Qualified supervisor source installed and read back.'
   where exists(select 1 from public.research_runtime_maintenance_holds where id=p_operation)
   on conflict(hold_id) do nothing;
 end if;
 -- A verified capability change is substantive evidence. Repeated heartbeats,
 -- retries and an unchanged manifest never create a new wake signal.
 insert into public.research_autonomy_events(study_id,task_id,event,details)
 select t.study_id,t.id,'platform-supervisor-runtime-activated',
  jsonb_build_object('version','platform-supervisor-self-repair-v1','revision',p_manifest->>'source_revision',
   'bundle_sha256',p_manifest->>'bundle_sha256','scientific_completion',false)
 from public.research_autonomy_tasks t join public.research_autonomy_workflows w on w.study_id=t.study_id
 where w.status in ('running','completed-with-blockers') and w.deadline_at>statement_timestamp()
  and t.status in ('waiting','blocked') and t.claim_id is not null;
 return p_manifest;
end$$;
create function public.platform_supervisor_install(p_operation uuid,p_revision text,p_command uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare o public.platform_operations;t public.platform_tasks;s public.platform_settings;i public.platform_supervisor_install_intents;
 receipt public.platform_supervisor_install_receipts;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict o from public.platform_operations where id=p_operation for update;
 select * into strict t from public.platform_tasks where id=o.task_id for update;
 select * into strict s from public.platform_settings where id;
 if o.kind<>'deploy' or o.request->>'component' is distinct from 'supervisor-runtime'
  or o.request->>'repository' is distinct from 'jumpserve-networks/jumpserve-back-end'
  or o.request->>'revision' is distinct from p_revision then raise exception 'Original qualified supervisor release identity required';end if;
 select * into i from public.platform_supervisor_install_intents where operation_id=o.id;
 select * into receipt from public.platform_supervisor_install_receipts where operation_id=o.id;
 if p_command is not null then
  if i.operation_id is null or i.revision<>p_revision then raise exception 'Original installation intent required';end if;
  if receipt.operation_id is not null and receipt.command_id<>p_command then raise exception 'Original installation command is immutable';end if;
  insert into public.platform_supervisor_install_receipts(operation_id,command_id) values(o.id,p_command) on conflict(operation_id) do nothing;
  return jsonb_build_object('recorded',true,'command_id',p_command,'dispatch_allowed',false);
 elsif i.operation_id is not null then
  if i.revision<>p_revision or i.request_sha256<>o.request_sha256 then raise exception 'Original installation intent differs';end if;
  return jsonb_build_object('dispatch_allowed',false,'command_id',receipt.command_id);
 end if;
 if s.paused or not s.automatic_releases or t.cancel_requested or t.deadline_at<=clock_timestamp()
  or t.authorization_version is distinct from s.authorization_version or o.status not in ('pending','unknown')
  or t.status in ('completed','rolled-back','cancelled','deadline','budget','blocked')
  or exists(select 1 from public.platform_assessment_repair_bindings l join public.platform_assessment_blockers b on b.id=l.blocker_id
    join public.research_autonomy_workflows w on w.study_id=b.study_id where l.platform_task_id=t.id
     and (w.status not in ('running','completed-with-blockers') or w.deadline_at<=clock_timestamp()))
  or exists(select 1 from public.platform_runs r where r.status='unknown' and r.task_id=t.id and not exists(select 1 from public.platform_run_reconciliations x where x.run_id=r.id))
  or exists(select 1 from public.platform_operations other where other.id<>o.id and other.task_id=t.id and other.status in ('pending','unknown'))
  or exists(select 1 from public.platform_operations other where other.id<>o.id and other.status in ('pending','unknown') and other.request->>'component' in ('supervisor-runtime','research-runtime'))
  or t.checkpoint->>'cleanup_unknown'='true' then raise exception 'Safe authorized supervisor release boundary required';end if;
 if not exists(select 1 from public.platform_artifacts a where a.task_id=t.id and a.id=(o.request->>'qualification_artifact_id')::uuid and a.name='supervisor-runtime-qualification.json')
  then raise exception 'Retained supervisor qualification certificate required';end if;
 -- The original deploy operation was admitted with a live controller lease.
 -- CI runs asynchronously after that polling lease is released. Reserve a
 -- bounded maintenance handoff; do not require a chance overlap with a poll.
 insert into public.research_runtime_maintenance_holds(id,task_id,source_binding,reason,expires_at)
 values(o.id,t.id,o.request_sha256,'Qualified operational supervisor installation; original research calls drain without replacement.',clock_timestamp()+interval '10 minutes')
 on conflict(id) do nothing;
 if not exists(select 1 from public.research_runtime_maintenance_holds where id=o.id and task_id=t.id and source_binding=o.request_sha256 and expires_at>clock_timestamp()
  and not exists(select 1 from public.research_runtime_maintenance_releases where hold_id=o.id)) then raise exception 'Original supervisor handoff expired; no installation dispatched';end if;
 if exists(select 1 from public.platform_tasks p where p.id<>t.id and p.lease_token is not null)
  or exists(select 1 from public.platform_runs r where r.status='running')
  or exists(select 1 from public.research_model_dispatches d where d.status='running')
  or exists(select 1 from public.research_autonomy_tasks r where r.lease_token is not null and r.lease_until>clock_timestamp()) then
  return jsonb_build_object('dispatch_allowed',false,'wait_for_safe_boundary',true,'command_id',null);
 end if;
 if not exists(select 1 from public.research_runtime_maintenance_holds where id=o.id and expires_at>clock_timestamp()+interval '330 seconds') then
  raise exception 'Original supervisor handoff has insufficient time for the bounded install; no command dispatched';
 end if;
 insert into public.platform_supervisor_install_intents(operation_id,task_id,revision,request_sha256) values(o.id,t.id,p_revision,o.request_sha256);
 insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'release-broker','supervisor-install-admitted',
  'Qualified self-update admitted once under standing owner authority. An uncertain SSM acknowledgment must reconcile its original command.',jsonb_build_object('operation_id',o.id,'revision',p_revision));
 return jsonb_build_object('dispatch_allowed',true,'command_id',null);
end$$;
revoke all on function public.platform_supervisor_install(uuid,text,uuid) from public,anon,authenticated;
grant execute on function public.platform_supervisor_install(uuid,text,uuid) to service_role;
revoke all on function public.platform_supervisor_runtime(),public.platform_supervisor_activate(uuid,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.platform_supervisor_runtime(),public.platform_supervisor_activate(uuid,jsonb,jsonb) to service_role;

-- The idle check and remote restart are asynchronous. Keep new host work
-- fenced through readback (even if the owner cancels after command admission).
-- Original calls and receipts remain reconcilable; the hold cannot be renewed.
create function public.platform_supervisor_handoff_task() returns uuid
language sql stable security definer set search_path='' as $$
 select h.task_id from public.research_runtime_maintenance_holds h
 join public.platform_operations o on o.id=h.id and o.task_id=h.task_id
 join public.platform_tasks t on t.id=h.task_id
 where o.kind='deploy' and o.request->>'component'='supervisor-runtime'
  and h.expires_at>clock_timestamp()
  and not exists(select 1 from public.research_runtime_maintenance_releases r where r.hold_id=h.id)
  and (exists(select 1 from public.platform_supervisor_install_intents i where i.operation_id=o.id)
   or not t.cancel_requested and t.deadline_at>clock_timestamp()
    and t.status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling'))
 order by h.created_at,h.id limit 1
$$;
revoke all on function public.platform_supervisor_handoff_task() from public,anon,authenticated,service_role;

alter function public.research_runtime_maintenance_active() rename to research_runtime_maintenance_before_supervisor_v1;
revoke all on function public.research_runtime_maintenance_before_supervisor_v1() from public,anon,authenticated,service_role;
create function public.research_runtime_maintenance_active() returns boolean
language sql stable security definer set search_path='' as $$
 select public.research_runtime_maintenance_before_supervisor_v1() or public.platform_supervisor_handoff_task() is not null
$$;
revoke all on function public.research_runtime_maintenance_active() from public,anon,authenticated;
grant execute on function public.research_runtime_maintenance_active() to service_role;

alter function public.research_autonomy_control(text,uuid,uuid,jsonb) rename to research_autonomy_before_self_install_v1;
revoke all on function public.research_autonomy_before_self_install_v1(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.research_autonomy_control(p_operation text,p_actor uuid default null,p_study uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$begin
 if p_operation='lease' then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  if public.platform_supervisor_handoff_task() is not null then return null;end if;
 end if;
 return public.research_autonomy_before_self_install_v1(p_operation,p_actor,p_study,p_payload);
end$$;
revoke all on function public.research_autonomy_control(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_autonomy_control(text,uuid,uuid,jsonb) to service_role;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_self_install_v1;
revoke all on function public.platform_worker_before_self_install_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare held uuid;begin
 if p_operation in ('claim','begin-run') then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  held=public.platform_supervisor_handoff_task();
  if held is not null then
   if p_operation='claim' then
    if p_payload?'only_task' and (p_payload->>'only_task')::uuid is distinct from held then return null;end if;
    return public.platform_worker_before_self_install_v1(p_operation,p_worker,p_task,p_token,p_payload||jsonb_build_object('only_task',held));
   end if;
   perform public.platform_worker_before_self_install_v1('lease',p_worker,p_task,p_token,'{}');
   return jsonb_build_object('denied','supervisor-install-maintenance');
  end if;
 end if;
 return public.platform_worker_before_self_install_v1(p_operation,p_worker,p_task,p_token,p_payload);
end$$;
revoke all on function public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;

alter function public.research_model_dispatch(text,jsonb) rename to research_model_dispatch_before_self_install_v1;
revoke all on function public.research_model_dispatch_before_self_install_v1(text,jsonb) from public,anon,authenticated,service_role;
create function public.research_model_dispatch(p_operation text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$begin
 if p_operation='claim' then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  if public.platform_supervisor_handoff_task() is not null then return null;end if;
 end if;
 return public.research_model_dispatch_before_self_install_v1(p_operation,p_payload);
end$$;
revoke all on function public.research_model_dispatch(text,jsonb) from public,anon,authenticated;
grant execute on function public.research_model_dispatch(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
