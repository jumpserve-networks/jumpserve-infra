begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
-- Stop only NEW claim leases, never an existing provider/experiment operation.
-- Holds are immutable and expire within twenty minutes without resetting work.
create table public.research_runtime_maintenance_holds (
 id uuid primary key, task_id uuid references public.platform_tasks(id),
 source_binding text, reason text not null check(length(reason) between 1 and 1000),
 created_at timestamptz not null default clock_timestamp(), expires_at timestamptz not null,
 check(expires_at>created_at and expires_at<=created_at+interval '20 minutes'),
 check(task_id is null or (source_binding is not null and source_binding~'^[a-f0-9]{64}$'))
);
create table public.research_runtime_maintenance_releases (
 hold_id uuid primary key references public.research_runtime_maintenance_holds(id),
 reason text not null,created_at timestamptz not null default clock_timestamp()
);
alter table public.research_runtime_maintenance_holds enable row level security;
alter table public.research_runtime_maintenance_releases enable row level security;
revoke all on public.research_runtime_maintenance_holds,public.research_runtime_maintenance_releases from public,anon,authenticated,service_role;
grant select on public.research_runtime_maintenance_holds,public.research_runtime_maintenance_releases to service_role;
create trigger runtime_maintenance_hold_immutable before update or delete on public.research_runtime_maintenance_holds for each row execute function public.platform_immutable();
create trigger runtime_maintenance_release_immutable before update or delete on public.research_runtime_maintenance_releases for each row execute function public.platform_immutable();

create function public.research_runtime_maintenance_active() returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.research_runtime_maintenance_holds h
  where h.expires_at>clock_timestamp() and not exists(select 1 from public.research_runtime_maintenance_releases r where r.hold_id=h.id)
   and (h.task_id is null or exists(select 1 from public.platform_tasks t where t.id=h.task_id and not t.cancel_requested
    and t.deadline_at>clock_timestamp() and t.status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling'))))
$$;
alter function public.research_autonomy_control(text,uuid,uuid,jsonb) rename to research_autonomy_before_runtime_handoff_v1;
revoke all on function public.research_autonomy_before_runtime_handoff_v1(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.research_autonomy_control(p_operation text,p_actor uuid default null,p_study uuid default null,p_payload jsonb default '{}') returns jsonb
 language plpgsql security definer set search_path='' as $$begin
 if p_operation='lease' and public.research_runtime_maintenance_active() then return null;end if;
 return public.research_autonomy_before_runtime_handoff_v1(p_operation,p_actor,p_study,p_payload);
end$$;

-- A tested operational-runtime candidate automatically receives one bounded
-- hand-off per source binding. Ordinary coding/model tasks retain research priority.
alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_runtime_handoff_v1;
revoke all on function public.platform_worker_before_runtime_handoff_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.platform_tasks;binding text;ident uuid;created timestamptz;begin
 if p_operation='claim' then
  select a.* into t from public.platform_tasks a join public.platform_settings s on s.id
   where not s.paused and s.automatic_releases and a.authorization_version=s.authorization_version and not a.cancel_requested
    and a.lease_token is null and a.deadline_at>clock_timestamp()+interval '180 seconds'
    and a.status in ('publishing','merging','deploying','verifying','reconciling')
    and (not(p_payload?'only_task') or a.id=(p_payload->>'only_task')::uuid)
    and a.checkpoint->'research_runtime'->'certificate'->>'passed'='true'
    and a.checkpoint->'research_runtime'->'scope'->>'version'='research-controller-recovery-v1'
    and a.checkpoint->'research_runtime'->'scope'->>'scientific_and_request_content_unchanged'='true'
    and a.checkpoint->'research_runtime'->'scope'->>'existing_tests_unchanged'='true'
   order by a.priority,a.created_at,a.id limit 1;
  if found then
   binding=t.checkpoint->'research_runtime'->'scope'->>'source_binding';
   if binding~'^[a-f0-9]{64}$' then
    ident=md5('qualified-runtime-maintenance-v1:'||t.id::text||':'||binding)::uuid;created=clock_timestamp();
    insert into public.research_runtime_maintenance_holds(id,task_id,source_binding,reason,created_at,expires_at)
     values(ident,t.id,binding,'Qualified operational runtime release; existing calls drain before the platform lease.',created,least(t.deadline_at,created+interval '20 minutes')) on conflict(id) do nothing;
    if found then insert into public.platform_events(id,task_id,actor,kind,message,details)
     values(gen_random_uuid(),t.id,'supervisor','qualified-runtime-handoff','New research claim leases briefly wait while original calls drain for this qualified runtime release. Existing calls, cancellation, budgets and deadlines are unchanged.',jsonb_build_object('hold_id',ident,'source_binding',binding,'maximum_seconds',1200));end if;
   end if;
  end if;
 end if;
 return public.platform_worker_before_runtime_handoff_v1(p_operation,p_worker,p_task,p_token,p_payload);
end$$;
revoke all on function public.research_runtime_maintenance_active(),public.research_autonomy_control(text,uuid,uuid,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.research_runtime_maintenance_active(),public.research_autonomy_control(text,uuid,uuid,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
