begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
-- Defaults stay $100. A separately recorded operator authorization may raise
-- one existing assessment to at most $1,000; it cannot reset time or spending.
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_max_spend_cents_check;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_max_spend_cents_check check(max_spend_cents between 10000 and 100000);
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_committed_cents_check;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_committed_cents_check check(committed_cents>=0 and committed_cents<=max_spend_cents);
do $migration$ declare definition text;before text;begin
 definition=pg_get_functiondef('public.research_autonomy_immutable()'::regprocedure);
 before='new.initial_sha256,new.max_spend_cents,new.max_attempts';
 if strpos(definition,before)=0 then raise exception 'Unexpected authorization guard';end if;
 definition=replace(definition,before,'new.initial_sha256,new.max_attempts');
 before='old.initial_sha256,old.max_spend_cents,old.max_attempts';
 if strpos(definition,before)=0 then raise exception 'Unexpected prior authorization guard';end if;
 definition=replace(definition,before,'old.initial_sha256,old.max_attempts');
 before=$old$if tg_table_name='research_autonomy_workflows' then$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected immutable workflow branch';end if;
 execute replace(definition,before,$new$if tg_table_name='research_autonomy_workflows' then
  if new.max_spend_cents is distinct from old.max_spend_cents and (
   new.max_spend_cents<=old.max_spend_cents or not exists(
    select 1 from public.research_autonomy_events e where e.study_id=old.study_id and e.event='budget-authorization-amended'
     and e.details->>'transaction_id'=pg_current_xact_id()::text
     and e.details->>'previous_max_spend_cents'=old.max_spend_cents::text
     and e.details->>'max_spend_cents'=new.max_spend_cents::text
     and length(e.details->>'authorized_by')>0
   )) then raise exception 'A same-transaction audited operator budget increase is required';end if;$new$);
end $migration$;
create function public.research_autonomy_amend_budget(p_study uuid,p_request uuid,p_max_cents integer,p_authorized_by text,p_reason text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare w public.research_autonomy_workflows;prior public.research_autonomy_events;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_request is null or p_max_cents is null or p_max_cents not between 10001 and 100000 or p_authorized_by is null or length(p_authorized_by) not between 1 and 500 or p_reason is null or length(p_reason) not between 1 and 3000 then raise exception 'Explicit bounded operator authorization required';end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 select * into prior from public.research_autonomy_events where id=p_request;
 if found then
  if prior.study_id<>p_study or prior.event<>'budget-authorization-amended' or prior.details->>'max_spend_cents'<>p_max_cents::text or prior.details->>'authorized_by'<>p_authorized_by or prior.details->>'reason'<>p_reason then raise exception 'Budget request identity conflicts with its original authorization';end if;
  return jsonb_build_object('replayed',true,'max_spend_cents',w.max_spend_cents,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'status',w.status);
 end if;
 if p_max_cents<=w.max_spend_cents or w.status in ('cancelled','completed','deadline') or w.deadline_at<=clock_timestamp() then raise exception 'Only an unexpired assessment budget may be increased';end if;
 insert into public.research_autonomy_events(id,study_id,event,details) values(p_request,p_study,'budget-authorization-amended',jsonb_build_object(
  'version','assessment-budget-amendment-v1','transaction_id',pg_current_xact_id()::text,'previous_max_spend_cents',w.max_spend_cents,'max_spend_cents',p_max_cents,
  'authorized_by',p_authorized_by,'reason',p_reason,'initial_sha256',w.initial_sha256,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,
  'scope','Explicit prospective funding amendment only. Original prompts, counters, costs, deadline, outcomes and claims remain unchanged. This operation does not resume tasks.'));
 update public.research_autonomy_workflows set max_spend_cents=p_max_cents,updated_at=clock_timestamp() where study_id=p_study;
 return jsonb_build_object('replayed',false,'max_spend_cents',p_max_cents,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'status',w.status);
end $$;
revoke all on function public.research_autonomy_amend_budget(uuid,uuid,integer,text,text) from public,anon,authenticated;
grant execute on function public.research_autonomy_amend_budget(uuid,uuid,integer,text,text) to service_role;
notify pgrst,'reload schema';
commit;
