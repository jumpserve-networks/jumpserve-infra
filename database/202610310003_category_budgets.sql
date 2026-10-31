begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Current, editable policy. -1 is the only unlimited sentinel; NULL/missing
-- categories are errors. Reservation estimates and scientific resource bounds
-- are not budgets and remain unchanged.
create table public.autonomy_budget_categories (
 category text primary key check(category in ('research_assessment','platform_manual','platform_maintenance','platform_repair')),
 label text not null, scope text not null check(scope in ('assessment','platform-task')),
 max_spend_cents integer not null check(max_spend_cents>=-1),
 max_model_calls integer not null check(max_model_calls>=-1),
 revision bigint not null default 1 check(revision>0),
 change_reason text not null default 'Budget configuration update' check(length(change_reason) between 1 and 1000),
 updated_at timestamptz not null default clock_timestamp()
);
create table public.autonomy_budget_history (
 id bigint generated always as identity primary key, category text not null,
 revision bigint not null, previous jsonb, current jsonb not null,
 actor_id uuid, database_actor text not null,
 created_at timestamptz not null default clock_timestamp(),unique(category,revision)
);
create function public.autonomy_budget_audit() returns trigger language plpgsql security definer set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Budget categories cannot be deleted';end if;
 if tg_op='UPDATE' then
  if (new.category,new.label,new.scope) is distinct from (old.category,old.label,old.scope) then raise exception 'Budget category identity is fixed';end if;
  new.revision=old.revision+1;new.updated_at=clock_timestamp();
 end if;
 insert into public.autonomy_budget_history(category,revision,previous,current,actor_id,database_actor)
 values(new.category,new.revision,case when tg_op='UPDATE' then to_jsonb(old) else null end,to_jsonb(new),auth.uid(),session_user);
 insert into public.platform_events(id,actor,kind,message,details) values(gen_random_uuid(),'budget-policy','budget-policy-updated',
  'Autonomy budget category updated. -1 means unlimited; retained commitments, deadlines and uncertain action identities are unchanged.',
  jsonb_build_object('category',new.category,'revision',new.revision,'max_spend_cents',new.max_spend_cents,'max_model_calls',new.max_model_calls,'change_reason',new.change_reason));
 return new;
end$$;

create function public.autonomy_assessment_budget_terms() returns jsonb language sql stable security definer set search_path='' as $$
 select jsonb_build_object('version','autonomy-category-budgets-v1','category',category,'revision',revision,
  'max_spend_cents',max_spend_cents,'max_model_calls',max_model_calls)
 from public.autonomy_budget_categories where category='research_assessment'
$$;
create function public.research_category_budget_allows(p_study uuid,p_task uuid,p_cents integer,p_calls_delta integer) returns boolean
language plpgsql security definer set search_path='' as $$declare spent bigint;calls bigint;begin
 select committed_cents into strict spent from public.research_autonomy_workflows where study_id=p_study;
 select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;
 if public.autonomy_budget_allows('research_assessment',spent,calls,p_cents,p_calls_delta) then return true;end if;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(p_study,p_task,'category-budget-denied',
  jsonb_build_object('policy',public.autonomy_assessment_budget_terms(),'committed_cents',spent,'model_calls',calls,
   'requested_cents',p_cents,'requested_model_calls',p_calls_delta,'provider_dispatched',false));
 return false;
end$$;
create trigger autonomy_budget_audit before insert or update or delete on public.autonomy_budget_categories
 for each row execute function public.autonomy_budget_audit();
create trigger autonomy_budget_history_immutable before update or delete on public.autonomy_budget_history
 for each row execute function public.platform_immutable();
insert into public.autonomy_budget_categories(category,label,scope,max_spend_cents,max_model_calls,change_reason) values
 ('research_assessment','Research assessments','assessment',-1,-1,'User requested all category budgets = -1 (unlimited).'),
 ('platform_manual','Owner-requested platform improvements','platform-task',-1,-1,'User requested all category budgets = -1 (unlimited).'),
 ('platform_maintenance','Platform maintenance','platform-task',-1,-1,'User requested all category budgets = -1 (unlimited).'),
 ('platform_repair','Assessment blocker repairs','platform-task',-1,-1,'User requested all category budgets = -1 (unlimited).');
alter table public.autonomy_budget_categories enable row level security;
alter table public.autonomy_budget_history enable row level security;
revoke all on public.autonomy_budget_categories,public.autonomy_budget_history from public,anon,authenticated,service_role;
grant select on public.autonomy_budget_categories,public.autonomy_budget_history to service_role,authenticated;
grant update(max_spend_cents,max_model_calls,change_reason) on public.autonomy_budget_categories to authenticated;
create policy autonomy_budget_operator_read on public.autonomy_budget_categories for select to authenticated using((select public.platform_is_operator(false)));
create policy autonomy_budget_owner_update on public.autonomy_budget_categories for update to authenticated
 using((select public.platform_is_operator(true))) with check((select public.platform_is_operator(true)));
create policy autonomy_budget_history_operator_read on public.autonomy_budget_history for select to authenticated using((select public.platform_is_operator(false)));

create function public.autonomy_budget_snapshot() returns jsonb language sql stable security definer set search_path='' as $$
 select jsonb_build_object('version','autonomy-category-budgets-v1','categories',jsonb_agg(to_jsonb(b) order by category)) from public.autonomy_budget_categories b
$$;
-- Called only inside the original serialized admission transactions. SHARE
-- prevents a concurrent policy edit from racing its corresponding admission.
create function public.autonomy_budget_allows(p_category text,p_spent bigint,p_calls bigint,p_cents integer,p_calls_delta integer)
 returns boolean language plpgsql security definer set search_path='' as $$
declare b public.autonomy_budget_categories;begin
 if p_spent is null or p_calls is null or p_cents is null or p_calls_delta is null or least(p_spent,p_calls,p_cents,p_calls_delta)<0 then raise exception 'Nonnegative recorded usage and reservation required';end if;
 select * into strict b from public.autonomy_budget_categories where category=p_category for share;
 return (b.max_spend_cents=-1 or p_spent<=b.max_spend_cents and p_cents<=b.max_spend_cents-p_spent)
  and (b.max_model_calls=-1 or p_calls<=b.max_model_calls and p_calls_delta<=b.max_model_calls-p_calls);
end$$;

-- Legacy assessment projections keep their established NULL representation.
-- Only the policy table uses -1. Amounts below already retained commitments are
-- valid prospective stops; historical commitments are never refunded.
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_max_spend_cents_check;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_max_spend_cents_check check(max_spend_cents is null or max_spend_cents>=0);
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_committed_cents_check;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_committed_cents_check check(committed_cents>=0);
create function public.autonomy_budget_sync_assessments() returns void language plpgsql security definer set search_path='' as $$
declare b public.autonomy_budget_categories;w public.research_autonomy_workflows;ceiling integer;resumed uuid[];begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict b from public.autonomy_budget_categories where category='research_assessment' for share;
 ceiling=nullif(b.max_spend_cents,-1);
 for w in select * from public.research_autonomy_workflows where status in ('running','completed-with-blockers','budget')
  and deadline_at>clock_timestamp() and max_spend_cents is distinct from ceiling order by study_id for update
 loop
  insert into public.research_autonomy_events(study_id,event,details) values(w.study_id,'budget-authorization-amended',jsonb_build_object(
   'version','assessment-budget-amendment-v2','transaction_id',pg_current_xact_id()::text,
   'previous_max_spend_cents',w.max_spend_cents,'max_spend_cents',ceiling,
   'authorized_by','Supabase autonomy_budget_categories policy','reason',b.change_reason,
   'category',b.category,'policy_revision',b.revision,'initial_sha256',w.initial_sha256,
   'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'resume_budget_tasks',false,
   'scope','Prospective category policy; original counters, deadlines, evidence and uncertain identities retained.'));
  update public.research_autonomy_workflows set max_spend_cents=ceiling,updated_at=clock_timestamp() where study_id=w.study_id;
 end loop;
 with changed as (
  update public.research_autonomy_tasks t set status='queued',lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp(),
   reason='Current category budget permits continuation; original checkpoint, usage and deadline retained.'
  from public.research_autonomy_workflows parent where t.study_id=parent.study_id and t.status='budget'
   and parent.status in ('running','completed-with-blockers','budget') and parent.deadline_at>clock_timestamp()+interval '180 seconds'
   and parent.reason<>'Usage exceeded the reserved price ceiling; reconcile costs before further work.'
   and public.autonomy_budget_allows('research_assessment',parent.committed_cents,
    (select coalesce(sum(attempts),0) from public.research_autonomy_tasks where study_id=parent.study_id),100,1)
   and (t.reason='Paper budget cannot admit another controller slot.' or exists(
    select 1 from public.research_autonomy_events e where e.task_id=t.id and e.event='category-budget-denied'
     and not exists(select 1 from public.research_autonomy_turns r where r.task_id=t.id and r.created_at>e.created_at)
     and not exists(select 1 from public.research_builder_calls c where c.task_id=t.id and c.created_at>e.created_at)))
   and not exists(select 1 from public.research_autonomy_turns r where r.task_id=t.id and r.status in ('running','unknown'))
   and not exists(select 1 from public.research_builder_calls c where c.task_id=t.id and c.status in ('running','unknown'))
   and not exists(select 1 from public.research_model_dispatches d where d.task_id=t.id and (d.status in ('queued','running') or d.status='unknown' and not exists(select 1 from public.research_model_reconciliations rr where rr.dispatch_id=d.id and rr.request_sha256=d.request_sha256)))
  returning t.id,t.study_id
 ) select array_agg(id) into resumed from changed;
 if resumed is not null then
  insert into public.research_autonomy_events(study_id,task_id,event,details)
   select study_id,id,'category-budget-resumed',jsonb_build_object('policy',public.autonomy_assessment_budget_terms(),'attempts',attempts,'deadline_at',deadline_at)
   from public.research_autonomy_tasks join public.research_autonomy_workflows using(study_id) where id=any(resumed);
  update public.research_autonomy_workflows set status='running',updated_at=clock_timestamp()
   where study_id in (select study_id from public.research_autonomy_tasks where id=any(resumed)) and status in ('budget','completed-with-blockers');
 end if;
end$$;
create or replace function public.research_autonomy_initial_budget() returns trigger language plpgsql security definer set search_path='' as $$
declare b public.autonomy_budget_categories;begin
 select * into strict b from public.autonomy_budget_categories where category='research_assessment' for share;
 new.max_spend_cents=nullif(b.max_spend_cents,-1);return new;
end$$;
create or replace function public.research_assessment_inherit_budget_policy() returns trigger language plpgsql security definer set search_path='' as $$
declare b public.autonomy_budget_categories;begin
 select * into strict b from public.autonomy_budget_categories where category='research_assessment' for share;
 insert into public.research_autonomy_events(study_id,event,details) values(new.study_id,'budget-policy-inherited',jsonb_build_object(
  'version','autonomy-category-budgets-v1','category',b.category,'policy_revision',b.revision,
  'max_spend_cents',new.max_spend_cents,'max_model_calls',b.max_model_calls,'initial_sha256',new.initial_sha256,
  'committed_cents',new.committed_cents,'deadline_at',new.deadline_at));return new;
end$$;
alter function public.research_autonomy_control(text,uuid,uuid,jsonb) rename to research_autonomy_before_category_budgets_v1;
revoke all on function public.research_autonomy_before_category_budgets_v1(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.research_autonomy_control(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb) returns jsonb
 language plpgsql security definer set search_path='' as $$declare original text;result jsonb;begin
 if p_operation in ('start','lease','begin','reserve-job') then perform public.autonomy_budget_sync_assessments();end if;
 if p_operation='start' and not exists(select 1 from public.research_autonomy_workflows where study_id=p_study)
  and not public.autonomy_budget_allows('research_assessment',0,0,500,0) then return jsonb_build_object('denied','budget');end if;
 if p_operation='start' then
  select initial_prompt into original from public.research_autonomy_workflows where study_id=p_study;
  if found and left(ltrim(original),1)='{' and left(ltrim(p_payload->>'initial_prompt'),1)='{' and
    (original::jsonb-'defaults')=((p_payload->>'initial_prompt')::jsonb-'defaults') then
   -- Replay the exact original bytes when only a current default changed. The
   -- predecessor still enforces owner and immutable paper/request identity.
   p_payload=jsonb_set(p_payload,'{initial_prompt}',to_jsonb(original));
  end if;
 end if;
 result=public.research_autonomy_before_category_budgets_v1(p_operation,p_actor,p_study,p_payload);
 if p_operation='start' and result ? 'autonomy' then
  result=jsonb_set(result,'{autonomy,budget_policy}',public.autonomy_assessment_budget_terms());
 end if;return result;
end$$;

-- Preserve the deployed implementations and insert only current policy checks.
-- Attempts include the containing builder turn; the first native request uses
-- that existing admission, while later requests increment the original counter.
do $$declare definition text;before text;after text;begin
 definition=pg_get_functiondef('public.research_autonomy_before_confirmation(text,uuid,uuid,jsonb)'::regprocedure);
 before=$old$if (w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents) then return jsonb_build_object('denied','budget'); end if;$old$;
 after=$new$if not public.research_category_budget_allows(p_study,t.id,cents,1)
   or (w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents) then return jsonb_build_object('denied','budget');end if;$new$;
 if strpos(definition,before)=0 then raise exception 'Unexpected assessment model admission guard';end if;
 definition=replace(definition,before,after);
 before=$old$if w.status<>'running' or w.deadline_at<=clock_timestamp()+make_interval(secs=>(p_payload->>'required_seconds')::integer) or cents is null or cents<1 or (w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents) then$old$;
 after=$new$if w.status<>'running' or w.deadline_at<=clock_timestamp()+make_interval(secs=>(p_payload->>'required_seconds')::integer) or cents is null or cents<1 or not public.research_category_budget_allows(p_study,t.id,cents,0) or (w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents) then$new$;
 if strpos(definition,before)=0 then raise exception 'Unexpected experiment reservation guard';end if;
 definition=replace(definition,before,after);
 definition=replace(definition,$old$'maximum_spend_usd',null,$old$,$new$'maximum_spend_usd',w.max_spend_cents/100.0,$new$);
 execute definition;
 definition=pg_get_functiondef('public.research_builder_call(text,jsonb)'::regprocedure);
 before=$old$perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected builder admission gate';end if;
 definition=replace(definition,before,before||' perform public.autonomy_budget_sync_assessments();');
 before=$old$if (w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents) then return jsonb_build_object('denied','budget'); end if;$old$;
 after=$new$if not public.research_category_budget_allows(w.study_id,t.id,cents,case when cents>0 then 1 else 0 end)
  or (w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents) then return jsonb_build_object('denied','budget');end if;$new$;
 if strpos(definition,before)=0 then raise exception 'Unexpected builder funding guard';end if;
 execute replace(definition,before,after);
end$$;

alter table public.platform_tasks add column budget_category text not null default 'platform_manual' references public.autonomy_budget_categories(category);
update public.platform_tasks t set budget_category=case
 when exists(select 1 from public.platform_assessment_repair_links l where l.platform_task_id=t.id) then 'platform_repair'
 when exists(select 1 from public.platform_events e where e.task_id=t.id and e.kind='maintenance-queued') then 'platform_maintenance' else 'platform_manual' end;
alter table public.platform_tasks drop constraint platform_tasks_max_reserved_cents_check;
alter table public.platform_tasks add constraint platform_tasks_max_reserved_cents_check check(max_reserved_cents>=-1);
alter table public.platform_tasks drop constraint platform_tasks_check;
alter table public.platform_tasks add constraint platform_tasks_committed_cents_check check(committed_cents>=0);
create function public.platform_category_budget() returns trigger language plpgsql security definer set search_path='' as $$
declare b public.autonomy_budget_categories;begin
 if new.budget_category not in ('platform_manual','platform_maintenance','platform_repair') then raise exception 'Invalid platform budget category';end if;
 select * into strict b from public.autonomy_budget_categories where category=new.budget_category for share;
 new.max_reserved_cents=b.max_spend_cents;return new;
end$$;
create trigger platform_category_budget before insert on public.platform_tasks for each row execute function public.platform_category_budget();
create function public.autonomy_budget_sync_platform() returns void language plpgsql security definer set search_path='' as $$begin
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 -- Config editors lock only policy rows, never work records. Keep the existing
 -- research/platform lock order and do not acquire the research admission lock.
 perform 1 from public.autonomy_budget_categories where scope='platform-task' order by category for share;
 with changed as (
  update public.platform_tasks t set max_reserved_cents=b.max_spend_cents,updated_at=clock_timestamp()
  from public.autonomy_budget_categories b where t.budget_category=b.category
   and t.status not in ('completed','rolled-back','cancelled','deadline') and t.deadline_at>clock_timestamp()
   and t.max_reserved_cents is distinct from b.max_spend_cents returning t.id,t.budget_category,t.max_reserved_cents,t.committed_cents,t.deadline_at
 ) insert into public.platform_events(id,task_id,actor,kind,message,details)
 select gen_random_uuid(),id,'budget-policy','task-budget-policy-applied','Current category budget applied without resetting usage or deadline.',to_jsonb(changed) from changed;
 with resumed as (
  update public.platform_tasks t set status='implementing',reason='Category budget now permits continuation; retained source, usage and action identities preserved.',updated_at=clock_timestamp()
  where t.status='budget' and not t.cancel_requested and t.deadline_at>clock_timestamp()+interval '90 seconds'
   and not exists(select 1 from public.platform_assessment_repair_links l join public.platform_assessment_blockers signal on signal.id=l.blocker_id
    join public.research_autonomy_workflows parent on parent.study_id=signal.study_id where l.platform_task_id=t.id
     and (parent.status in ('cancelled','budget','deadline') or parent.deadline_at<=clock_timestamp()))
   and public.autonomy_budget_allows(t.budget_category,t.committed_cents,(select count(*) from public.platform_runs r where r.task_id=t.id),100,1)
   and not exists(select 1 from public.platform_runs r where r.task_id=t.id and (r.status='running' or r.status='unknown' and not exists(select 1 from public.platform_run_reconciliations rr where rr.run_id=r.id)))
   and not exists(select 1 from public.platform_operations o where o.task_id=t.id and o.status in ('pending','unknown'))
  returning t.id,t.committed_cents,t.deadline_at
 ) insert into public.platform_events(id,task_id,actor,kind,message,details)
 select gen_random_uuid(),id,'budget-policy','budget-task-resumed','Safe budget-stopped platform work resumed under the current category policy.',to_jsonb(resumed) from resumed;
end$$;

do $$declare definition text;before text;begin
 definition=pg_get_functiondef('public.platform_control(text,uuid,uuid,jsonb)'::regprocedure);
 before=$old$coalesce((p_payload->>'max_reserved_cents')::integer,10000) not between 100 and 1000000$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected owner task budget validation';end if;
 execute replace(definition,before,$new$coalesce((p_payload->>'max_reserved_cents')::integer,-1)<-1$new$);
 definition=pg_get_functiondef('public.platform_worker_before_assessment_v1(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 before='repositories,authorization_version,max_reserved_cents,deadline_at)';
 if strpos(definition,before)=0 then raise exception 'Unexpected maintenance task admission';end if;
 definition=replace(definition,before,'repositories,authorization_version,budget_category,max_reserved_cents,deadline_at)');
 definition=replace(definition,'s.authorization_version,10000,clock_timestamp()', 's.authorization_version,''platform_maintenance'',10000,clock_timestamp()');
 definition=replace(definition,'Daily maintenance admitted within a six-hour, $100 reservation limit; actual subscription charges remain unknown.','Daily maintenance admitted under the current Supabase category budget and original six-hour deadline; actual subscription charges remain unknown.');
 before=$old$where lease_token is null and authorization_version=s.authorization_version and status in$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected task claim selector';end if;
 definition=replace(definition,before,$new$where lease_token is null and (not (p_payload ? 'only_task') or id=(p_payload->>'only_task')::uuid) and authorization_version=s.authorization_version and status in$new$);
 before=$old$  select * into t from public.platform_tasks where lease_token is null$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected scoped task claim boundary';end if;
 definition=replace(definition,before,$new$  if p_payload ? 'only_task' and exists(select 1 from public.platform_tasks other_task
   where other_task.id is distinct from (p_payload->>'only_task')::uuid
    and (other_task.status='reconciling' or other_task.checkpoint->>'cleanup_unknown'='true')) then return null;end if;
$new$||before);
 before=$old$if t.committed_cents+100>t.max_reserved_cents then return jsonb_build_object('denied','budget');end if;$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected platform model funding guard';end if;
 definition=replace(definition,before,$new$if not public.autonomy_budget_allows(t.budget_category,t.committed_cents,(select count(*) from public.platform_runs where task_id=t.id),100,1) then return jsonb_build_object('denied','budget');end if;$new$);
 execute definition;
 definition=pg_get_functiondef('public.platform_worker(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 before='authorization_version,priority,max_reserved_cents,deadline_at)';
 if strpos(definition,before)=0 then raise exception 'Unexpected blocker repair admission';end if;
 definition=replace(definition,before,'authorization_version,budget_category,priority,max_reserved_cents,deadline_at)');
 definition=replace(definition,'s.authorization_version,0,10000,least(', 's.authorization_version,''platform_repair'',0,10000,least(');
 definition=replace(definition,$old$'max_reserved_cents',10000,'actual_charges'$old$,$new$'max_reserved_cents',(select max_spend_cents from public.autonomy_budget_categories where category='platform_repair'),'actual_charges'$new$);
 execute definition;
end$$;
alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_category_budgets_v1;
revoke all on function public.platform_worker_before_category_budgets_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$declare result jsonb;begin
 if p_operation in ('maintenance','claim','lease','begin-run') then perform public.autonomy_budget_sync_platform();end if;
 result=public.platform_worker_before_category_budgets_v1(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation='lease' then
  return result||(select jsonb_build_object('budget_category',t.budget_category,'max_model_calls',b.max_model_calls,
   'model_calls',(select count(*) from public.platform_runs where task_id=t.id),'budget_policy_revision',b.revision)
   from public.platform_tasks t join public.autonomy_budget_categories b on b.category=t.budget_category where t.id=p_task);
 end if;return result;
end$$;

-- Existing private dashboard consumes the same task records; include the policy
-- rows through its checked projection, not anonymous SQL access.
alter function public.platform_snapshot(uuid,bigint,uuid) rename to platform_snapshot_before_category_budgets_v1;
revoke all on function public.platform_snapshot_before_category_budgets_v1(uuid,bigint,uuid) from public,anon,authenticated,service_role;
create function public.platform_snapshot(p_task uuid default null,p_before_event bigint default null,p_before_task uuid default null) returns jsonb
 language plpgsql security definer set search_path='' as $$declare result jsonb;begin
 result=public.platform_snapshot_before_category_budgets_v1(p_task,p_before_event,p_before_task);
 return result||jsonb_build_object('budget_categories',public.autonomy_budget_snapshot()->'categories');
end$$;

revoke all on function public.autonomy_assessment_budget_terms(),public.research_category_budget_allows(uuid,uuid,integer,integer),public.autonomy_budget_audit(),public.autonomy_budget_snapshot(),public.autonomy_budget_allows(text,bigint,bigint,integer,integer),public.autonomy_budget_sync_assessments(),public.autonomy_budget_sync_platform(),public.platform_category_budget(),public.platform_worker(text,uuid,uuid,uuid,jsonb),public.research_autonomy_control(text,uuid,uuid,jsonb),public.platform_snapshot(uuid,bigint,uuid) from public,anon,authenticated,service_role;
grant execute on function public.autonomy_budget_snapshot(),public.platform_worker(text,uuid,uuid,uuid,jsonb),public.research_autonomy_control(text,uuid,uuid,jsonb) to service_role;
grant execute on function public.platform_snapshot(uuid,bigint,uuid) to authenticated;
select public.autonomy_budget_sync_assessments();
select public.autonomy_budget_sync_platform();
notify pgrst,'reload schema';
commit;
