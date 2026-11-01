begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- A reservation stops NEW parent leases, not dispatches belonging to existing
-- parents. Those original turns must drain through the unchanged native gate.
-- This is scheduler state, not an authorization, budget or task deadline.
create table public.platform_host_turn (
 id boolean primary key default true check(id),
 task_id uuid references public.platform_tasks(id),
 requested_at timestamptz, expires_at timestamptz, lease_token uuid,
 cooldown_until timestamptz not null default '-infinity',
 check ((task_id is null and requested_at is null and expires_at is null and lease_token is null)
  or (task_id is not null and requested_at is not null and expires_at is not null and expires_at>requested_at
   and expires_at<=requested_at+interval '10 minutes'))
);
insert into public.platform_host_turn(id) values(true);
alter table public.platform_host_turn enable row level security;
revoke all on public.platform_host_turn from public,anon,authenticated,service_role;
grant select on public.platform_host_turn to service_role;

create function public.platform_host_task_eligible(p_task uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.platform_tasks t join public.platform_settings s on s.id
  where t.id=p_task and t.authorization_version=s.authorization_version
   and t.status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling')
   and (not s.paused or t.status='reconciling')
   and coalesce((t.checkpoint->>'not_before')::timestamptz,'-infinity')<=clock_timestamp()
   and (t.status='reconciling' or t.checkpoint->>'cleanup_unknown'='true'
    or (not t.cancel_requested and t.deadline_at>clock_timestamp()+interval '180 seconds'
     and not exists(select 1 from public.platform_assessment_repair_links l
      join public.platform_assessment_blockers b on b.id=l.blocker_id
      join public.research_autonomy_workflows w on w.study_id=b.study_id
      where l.platform_task_id=t.id and (w.status not in ('running','completed-with-blockers')
       or w.deadline_at<=clock_timestamp()+interval '180 seconds'
       or w.max_spend_cents is not null and w.committed_cents>=w.max_spend_cents)))))
$$;
create function public.platform_host_reservation_active() returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.platform_host_turn h join public.platform_settings s on s.id
  where h.id and h.task_id is not null and h.lease_token is null
   and h.expires_at>clock_timestamp()
   and s.worker_seen_at>clock_timestamp()-interval '60 seconds'
   and public.platform_host_task_eligible(h.task_id))
$$;
revoke all on function public.platform_host_task_eligible(uuid),public.platform_host_reservation_active()
 from public,anon,authenticated,service_role;

-- Bind a normal worker's selected turn without converting it into an operator
-- only_task request. The existing only_task guard intentionally refuses to pass
-- OTHER reconciling tasks; applying it to every worker poll would deadlock two
-- simultaneous reconciling tasks. All existing admission checks stay in place.
do $$declare definition text;selector text;begin
 definition=pg_get_functiondef('public.platform_worker_before_assessment_v1(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 selector=$old$where lease_token is null and (not (p_payload ? 'only_task') or id=(p_payload->>'only_task')::uuid) and authorization_version=s.authorization_version$old$;
 if strpos(definition,selector)=0 then raise exception 'Unexpected platform claim selector; no admission function changed';end if;
 execute replace(definition,selector,selector||$new$ and (not(p_payload?'host_turn_task') or id=(p_payload->>'host_turn_task')::uuid)$new$);
 -- A qualified runtime's existing maintenance hold must also belong to the
 -- selected turn, rather than pausing research for an unrelated queued release.
 definition=pg_get_functiondef('public.platform_worker_before_repair_context_v1(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 selector=$old$and (not(p_payload?'only_task') or a.id=(p_payload->>'only_task')::uuid)$old$;
 if strpos(definition,selector)=0 then raise exception 'Unexpected qualified runtime handoff selector';end if;
 execute replace(definition,selector,selector||$new$ and (not(p_payload?'host_turn_task') or a.id=(p_payload->>'host_turn_task')::uuid)$new$);
end$$;

alter function public.research_autonomy_control(text,uuid,uuid,jsonb) rename to research_autonomy_before_fair_scheduling_v1;
revoke all on function public.research_autonomy_before_fair_scheduling_v1(text,uuid,uuid,jsonb)
 from public,anon,authenticated,service_role;
create function public.research_autonomy_control(p_operation text,p_actor uuid default null,p_study uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$begin
 if p_operation='lease' then
  -- Match the release/maintenance lock order, including concurrent parent and
  -- supervisor claims. Renewals, finishes and all retained calls still delegate.
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  if public.platform_host_reservation_active() or exists(select 1 from public.platform_tasks
   where lease_token is not null or checkpoint->>'cleanup_unknown'='true') then return null;end if;
 end if;
 return public.research_autonomy_before_fair_scheduling_v1(p_operation,p_actor,p_study,p_payload);
end$$;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_fair_scheduling_v1;
revoke all on function public.platform_worker_before_fair_scheduling_v1(text,uuid,uuid,uuid,jsonb)
 from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.platform_settings;h public.platform_host_turn;t public.platform_tasks;result jsonb;begin
 if p_operation='claim' then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  select * into strict s from public.platform_settings where id;
  if p_worker is null or jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'Invalid platform worker request';end if;
  if s.authorization_version is null then return null;end if;
  if not exists(select 1 from public.platform_authorizations where version=s.authorization_version
   and policy_sha256=p_payload->>'policy_sha256') then raise exception 'Installed policy differs from standing authorization';end if;
  if p_payload?'only_task' and exists(select 1 from public.platform_tasks other_task
   where other_task.id is distinct from (p_payload->>'only_task')::uuid
    and (other_task.status='reconciling' or other_task.checkpoint->>'cleanup_unknown'='true')) then return null;end if;

  -- Close only unstarted/settled expired work. Never infer an uncertain native
  -- or external operation's completion, clear cleanup fences or reset a limit.
  with expired as (
   update public.platform_tasks a set status='deadline',
    reason='Original task deadline elapsed before another supervisor turn; retained work and receipts are unchanged.',updated_at=clock_timestamp()
   where a.lease_token is null and a.deadline_at<=clock_timestamp()
    and a.status in ('queued','investigating','implementing','testing')
    and coalesce(a.checkpoint->>'cleanup_unknown','false')<>'true'
    and not exists(select 1 from public.platform_runs r where r.task_id=a.id
     and (r.status='running' or r.status='unknown' and not exists(select 1 from public.platform_run_reconciliations x where x.run_id=r.id)))
    and not exists(select 1 from public.platform_operations o where o.task_id=a.id and o.status in ('pending','unknown'))
   returning a.id,a.reason
  ) insert into public.platform_events(id,task_id,actor,kind,message,details)
   select gen_random_uuid(),id,'supervisor','deadline',reason,'{}'::jsonb from expired;

  select * into strict h from public.platform_host_turn where id for update;
  -- Adopt an existing lease during an in-place upgrade, including an expired
  -- lease that still requires the original controller's cleanup/reconciliation.
  if h.task_id is null then
   select * into t from public.platform_tasks where lease_token is not null order by created_at,id limit 1;
   if found then
    if p_payload?'only_task' and t.id is distinct from (p_payload->>'only_task')::uuid then return null;end if;
    update public.platform_host_turn set task_id=t.id,requested_at=statement_timestamp(),
     expires_at=statement_timestamp()+interval '10 minutes',lease_token=t.lease_token where id returning * into h;
   end if;
  end if;
  if h.task_id is not null then
   if p_payload?'only_task' and h.task_id is distinct from (p_payload->>'only_task')::uuid then return null;end if;
   select * into strict t from public.platform_tasks where id=h.task_id;
   if h.lease_token is not null and t.lease_token is not distinct from h.lease_token then
    -- A current lease stays exclusive. If stale, the existing controller must
    -- reclaim/reconcile that exact task before any competing native tool starts.
    if t.lease_until>clock_timestamp() then return null;end if;
   elsif h.lease_token is not null or not public.platform_host_reservation_active() then
    insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),h.task_id,'supervisor','host-turn-released',
     'Host reservation released; no existing call was interrupted and original task limits remain unchanged.',
     jsonb_build_object('reservation_expired',h.expires_at<=clock_timestamp(),'research_window_seconds',60));
    update public.platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,
     cooldown_until=clock_timestamp()+interval '60 seconds' where id returning * into h;
   end if;
  end if;
  if h.task_id is null then
   if s.worker_seen_at is null or s.worker_seen_at<=clock_timestamp()-interval '60 seconds'
    or h.cooldown_until>clock_timestamp() or exists(select 1 from public.platform_tasks where lease_token is not null) then return null;end if;
   select a.* into t from public.platform_tasks a where a.lease_token is null
    and public.platform_host_task_eligible(a.id)
    and (not(p_payload?'only_task') or a.id=(p_payload->>'only_task')::uuid)
    order by case when a.status='reconciling' or a.checkpoint->>'cleanup_unknown'='true' then 0 else 1 end,a.priority,
     coalesce((select max(e.created_at) from public.platform_events e where e.task_id=a.id and e.kind='claimed'),'-infinity'::timestamptz),a.created_at,a.id
    limit 1;
   if not found then return null;end if;
   update public.platform_host_turn set task_id=t.id,requested_at=statement_timestamp(),expires_at=statement_timestamp()+interval '10 minutes' where id returning * into h;
   insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),t.id,'supervisor','host-turn-reserved',
    'Repair turn reserved: new research leases briefly wait while original research calls drain. No in-flight work is stopped.',
    jsonb_build_object('maximum_drain_seconds',600,'expires_at',h.expires_at));
  end if;
  -- Parents admitted before the reservation may still enqueue their original
  -- dispatch. Do not strand those requests or admit the platform in that gap.
  if exists(select 1 from public.research_autonomy_tasks where status='running' and lease_until>clock_timestamp()) then return null;end if;
  result=public.platform_worker_before_fair_scheduling_v1(p_operation,p_worker,p_task,p_token,
   p_payload||jsonb_build_object('host_turn_task',h.task_id));
  if result is not null then
   update public.platform_host_turn set lease_token=(result->>'lease_token')::uuid where id;
  end if;
  return result;
 end if;
 result=public.platform_worker_before_fair_scheduling_v1(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation='checkpoint' then
  -- The original RPC validates the lease/token and persists the source/outcome
  -- first. A stopped or unknown action retains all of its existing fences.
  update public.platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,
   cooldown_until=clock_timestamp()+interval '60 seconds'
   where id and task_id=p_task and lease_token=p_token;
  if found then insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),p_task,'supervisor','host-turn-released',
   'Supervisor turn checkpointed; research receives an admission window before the next repair turn.',jsonb_build_object('research_window_seconds',60));end if;
 end if;
 return result;
end$$;
revoke all on function public.research_autonomy_control(text,uuid,uuid,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb)
 from public,anon,authenticated;
grant execute on function public.research_autonomy_control(text,uuid,uuid,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
