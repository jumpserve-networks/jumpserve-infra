begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
create table public.research_runtime_worker_install_intents (
 operation_id uuid primary key references public.platform_operations(id),task_id uuid not null references public.platform_tasks(id),
 revision text not null check(revision~'^[a-f0-9]{40}$'),source_binding text not null check(source_binding~'^[a-f0-9]{64}$'),
 created_at timestamptz not null default clock_timestamp()
);
create table public.research_runtime_worker_install_receipts (
 operation_id uuid primary key references public.research_runtime_worker_install_intents(operation_id),command_id uuid not null unique,
 created_at timestamptz not null default clock_timestamp()
);
create table public.research_runtime_worker_activations (
 operation_id uuid primary key references public.research_runtime_worker_install_receipts(operation_id),
 manifest jsonb not null,verification jsonb not null,created_at timestamptz not null default clock_timestamp()
);
do $$declare name text;begin
 foreach name in array array['research_runtime_worker_install_intents','research_runtime_worker_install_receipts','research_runtime_worker_activations'] loop
  execute format('alter table public.%I enable row level security',name);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',name);
  execute format('grant select on public.%I to service_role',name);
  execute format('create trigger %I before update or delete on public.%I for each row execute function public.platform_immutable()',name||'_immutable',name);
 end loop;
end $$;
create function public.research_runtime_worker_install(p_operation uuid,p_revision text,p_command uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare o public.platform_operations;t public.platform_tasks;i public.research_runtime_worker_install_intents;r public.research_runtime_worker_install_receipts;
 h public.research_runtime_maintenance_holds;binding text;created timestamptz;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict o from public.platform_operations where id=p_operation for update;
 select * into strict t from public.platform_tasks where id=o.task_id for update;
 if o.kind<>'deploy' or o.request->>'component' is distinct from 'research-runtime'
  or o.request->>'repository' is distinct from 'jumpserve-networks/jumpserve-back-end' or o.request->>'revision' is distinct from p_revision
 then raise exception 'Original research worker deployment identity required';end if;
 select * into i from public.research_runtime_worker_install_intents where operation_id=o.id;
 select * into r from public.research_runtime_worker_install_receipts where operation_id=o.id;
 if p_command is not null then
  if i.operation_id is null then raise exception 'Original worker install intent required';end if;
  if r.operation_id is not null and r.command_id<>p_command then raise exception 'Original worker command identity is immutable';end if;
  insert into public.research_runtime_worker_install_receipts(operation_id,command_id) values(o.id,p_command) on conflict(operation_id) do nothing;
  return jsonb_build_object('command_id',p_command,'dispatch_allowed',false);
 end if;
 if i.operation_id is not null then return jsonb_build_object('dispatch_allowed',false,'command_id',r.command_id);end if;
 binding=t.checkpoint->'research_runtime'->'scope'->>'source_binding';
 if o.status not in ('pending','unknown') or t.cancel_requested or t.deadline_at<=clock_timestamp()+interval '660 seconds'
  or exists(select 1 from public.platform_settings where id and (paused or not automatic_releases or authorization_version is distinct from t.authorization_version))
  or t.checkpoint->'research_runtime'->'certificate'->'passed' is distinct from 'true'::jsonb
  or t.checkpoint->'research_runtime'->'scope'->>'qualification_profile' is distinct from 'captured-provider-failures-v1'
  or coalesce(binding,'')!~'^[a-f0-9]{64}$'
 then raise exception 'Qualified active worker release and original controls required';end if;
 if exists(select 1 from public.research_runtime_maintenance_holds other
  where other.id<>o.id and other.expires_at>clock_timestamp()
   and (other.task_id is distinct from t.id or other.source_binding is distinct from binding)
   and not exists(select 1 from public.research_runtime_maintenance_releases where hold_id=other.id))
 then return jsonb_build_object('wait_for_safe_boundary',true,'dispatch_allowed',false);end if;
 select * into h from public.research_runtime_maintenance_holds where id=o.id;
 if not found then
  created=clock_timestamp();insert into public.research_runtime_maintenance_holds(id,task_id,source_binding,reason,created_at,expires_at)
   values(o.id,t.id,binding,'Drain active research before installing the qualified captured-result recovery worker.',created,least(t.deadline_at,created+interval '20 minutes')) returning * into h;
 end if;
 if h.task_id is distinct from t.id or h.source_binding is distinct from binding or h.expires_at<=clock_timestamp()+interval '660 seconds'
  or exists(select 1 from public.research_runtime_maintenance_releases where hold_id=h.id) then raise exception 'Original worker handoff expired or already released';end if;
 if exists(select 1 from public.research_autonomy_tasks where status='running' and lease_until>clock_timestamp())
  or exists(select 1 from public.research_model_dispatches where status in ('queued','running'))
  or exists(select 1 from public.research_builder_calls where status='running')
 then return jsonb_build_object('wait_for_safe_boundary',true,'dispatch_allowed',false);end if;
 insert into public.research_runtime_worker_install_intents(operation_id,task_id,revision,source_binding) values(o.id,t.id,p_revision,binding);
 return jsonb_build_object('dispatch_allowed',true,'command_id',null,'wait_for_safe_boundary',false);
end $$;
create function public.research_runtime_worker_activate(p_operation uuid,p_manifest jsonb,p_verification jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare i public.research_runtime_worker_install_intents;r public.research_runtime_worker_install_receipts;a public.research_runtime_worker_activations;t public.platform_tasks;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict i from public.research_runtime_worker_install_intents where operation_id=p_operation;
 select * into strict r from public.research_runtime_worker_install_receipts where operation_id=i.operation_id;
 select * into strict t from public.platform_tasks where id=i.task_id;
 if p_manifest->>'source_revision' is distinct from i.revision or p_verification->>'revision' is distinct from i.revision
  or p_verification->>'command_id' is distinct from r.command_id::text or p_verification->>'source_binding' is distinct from i.source_binding
  or p_verification->'passed' is distinct from 'true'::jsonb or p_verification->'installed_files_verified' is distinct from 'true'::jsonb
  or p_verification->'spool_unchanged' is distinct from 'true'::jsonb or p_verification->'credentials_unchanged' is distinct from 'true'::jsonb
  or p_verification->'provider_calls' is distinct from '0'::jsonb or p_verification->'scientific_completion' is distinct from 'false'::jsonb
  or p_manifest->'files' is distinct from ((t.checkpoint->'research_runtime'->'scope'->'files')||jsonb_build_object('policies/autonomous-repair-release-v1.json',t.checkpoint->'research_runtime'->>'approval_sha256'))
  or p_manifest->'source_overlay' is distinct from t.checkpoint->'research_runtime'->'scope'->'source_overlay'
 then raise exception 'Exact installed worker source and original command proof required';end if;
 select * into a from public.research_runtime_worker_activations where operation_id=i.operation_id;
 if found then
  if (a.manifest,a.verification) is distinct from (p_manifest,p_verification) then raise exception 'Worker activation is immutable';end if;return a.verification;
 end if;
 insert into public.research_runtime_worker_activations(operation_id,manifest,verification) values(i.operation_id,p_manifest,p_verification);
 insert into public.research_runtime_maintenance_releases(hold_id,reason) values(i.operation_id,'Qualified research worker installed and exact source read back.') on conflict(hold_id) do nothing;
 return p_verification;
end $$;

-- Once installation is admitted, cancellation cannot drop its short hold in
-- the middle of a switch. Existing operation reconciliation stays available.
do $$declare definition text;begin
 definition=pg_get_functiondef('public.research_runtime_maintenance_active()'::regprocedure);
 execute replace(definition,'FUNCTION public.research_runtime_maintenance_active(','FUNCTION public.research_runtime_maintenance_active_before_worker_v1(');
end $$;
create or replace function public.research_runtime_maintenance_active() returns boolean
language sql stable security definer set search_path='' as $$
 select public.research_runtime_maintenance_active_before_worker_v1() or exists(
  select 1 from public.research_runtime_worker_install_intents i join public.research_runtime_maintenance_holds h on h.id=i.operation_id
  where h.expires_at>clock_timestamp() and not exists(select 1 from public.research_runtime_maintenance_releases where hold_id=h.id))
$$;
revoke all on function public.research_runtime_maintenance_active_before_worker_v1() from public,anon,authenticated,service_role;
revoke all on function public.research_runtime_worker_install(uuid,text,uuid),public.research_runtime_worker_activate(uuid,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_runtime_worker_install(uuid,text,uuid),public.research_runtime_worker_activate(uuid,jsonb,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
