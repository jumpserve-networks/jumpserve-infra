begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
do $$ begin
 if to_regclass('public.research_model_reconciliations') is null then raise exception 'Builder reconciliation migration is required before optional budgets';end if;
end $$;

-- NULL is an explicit operator-authorized absence of an aggregate ceiling.
-- No existing assessment is amended or resumed by this migration.
alter table public.research_autonomy_workflows alter column max_spend_cents drop not null;
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_max_spend_cents_check;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_max_spend_cents_check
 check(max_spend_cents is null or max_spend_cents>=10000);
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_committed_cents_check;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_committed_cents_check
 check(committed_cents>=0 and (max_spend_cents is null or committed_cents<=max_spend_cents));
comment on column public.research_autonomy_workflows.max_spend_cents is
 'Aggregate reservation ceiling in cents; explicit NULL means unlimited by audited operator authorization. Default remains 10000. Original limits remain in immutable prompts and amendment events.';
create function public.research_autonomy_initial_budget() returns trigger language plpgsql set search_path='' as $$ begin
 if new.max_spend_cents is distinct from 10000 then raise exception 'New assessments require the unchanged default budget; amend explicitly after creation';end if;
 return new;
end $$;
create trigger research_autonomy_initial_budget before insert on public.research_autonomy_workflows for each row execute function public.research_autonomy_initial_budget();
revoke all on function public.research_autonomy_initial_budget() from public,anon,authenticated;

-- Retain the existing immutable identity/counter guards. Require a matching
-- same-transaction audit for both unlimited authorization and a later cap.
do $migration$ declare definition text; previous text; replacement text; begin
 definition=pg_get_functiondef('public.research_autonomy_immutable()'::regprocedure);
 previous=$old$if new.max_spend_cents is distinct from old.max_spend_cents and (
   new.max_spend_cents<=old.max_spend_cents or not exists(
    select 1 from public.research_autonomy_events e where e.study_id=old.study_id and e.event='budget-authorization-amended'
     and e.details->>'transaction_id'=pg_current_xact_id()::text
     and e.details->>'previous_max_spend_cents'=old.max_spend_cents::text
     and e.details->>'max_spend_cents'=new.max_spend_cents::text
     and length(e.details->>'authorized_by')>0
   )) then raise exception 'A same-transaction audited operator budget increase is required';end if;$old$;
 replacement=$new$if new.max_spend_cents is distinct from old.max_spend_cents and not exists(
    select 1 from public.research_autonomy_events e where e.study_id=old.study_id and e.event='budget-authorization-amended'
     and e.details->>'transaction_id'=pg_current_xact_id()::text
     and e.details ? 'previous_max_spend_cents' and e.details ? 'max_spend_cents'
     and e.details->'previous_max_spend_cents' = coalesce(to_jsonb(old.max_spend_cents),'null'::jsonb)
     and e.details->'max_spend_cents' = coalesce(to_jsonb(new.max_spend_cents),'null'::jsonb)
     and e.details->>'version' in ('assessment-budget-amendment-v1','assessment-budget-amendment-v2')
     and length(e.details->>'authorized_by')>0
   ) then raise exception 'A same-transaction audited operator budget amendment is required';end if;$new$;
 if strpos(definition,previous)=0 then raise exception 'Unexpected original budget audit guard';end if;
 definition=replace(definition,previous,replacement);
 execute replace(definition,$old$if tg_table_name='research_autonomy_workflows' then$old$,$new$if tg_table_name='research_autonomy_workflows' then
  if new.committed_cents<old.committed_cents then raise exception 'Recorded commitments cannot be refunded or reset';end if;$new$);
end $migration$;

-- Update the actual latest function bodies, preserving intervening wrappers,
-- leases, source confirmation, cancellation, resource quotes and unknown fences.
do $migration$ declare item record; definition text; original text; before text; after text; i integer; changes integer:=0;
 patterns text[][]:=array[
  ['w.committed_cents+5>w.max_spend_cents','(w.max_spend_cents is not null and w.committed_cents+5>w.max_spend_cents)'],
  ['w.committed_cents+100>w.max_spend_cents','(w.max_spend_cents is not null and w.committed_cents+100>w.max_spend_cents)'],
  ['w.committed_cents+cents>w.max_spend_cents','(w.max_spend_cents is not null and w.committed_cents+cents>w.max_spend_cents)'],
  ['committed_cents+5>max_spend_cents','(max_spend_cents is not null and committed_cents+5>max_spend_cents)'],
  ['w.committed_cents>=w.max_spend_cents','(w.max_spend_cents is not null and w.committed_cents>=w.max_spend_cents)'],
  ['w.committed_cents+5<=w.max_spend_cents','(w.max_spend_cents is null or w.committed_cents+5<=w.max_spend_cents)'],
  ['b.committed_cents+5<=b.max_spend_cents','(b.max_spend_cents is null or b.committed_cents+5<=b.max_spend_cents)'],
  ['w.committed_cents<=w.max_spend_cents','(w.max_spend_cents is null or w.committed_cents<=w.max_spend_cents)'],
  ['w.committed_cents<w.max_spend_cents','(w.max_spend_cents is null or w.committed_cents<w.max_spend_cents)']
 ];
begin
 for item in select p.oid,p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname in (
   'research_autonomy_before_confirmation','research_autonomy_resume_context','research_autonomy_context_candidates',
   'research_autonomy_resume_budget','research_autonomy_budget_candidates','research_autonomy_resume_turns',
   'research_model_dispatch','research_autonomy_resume_partial','research_paper_review_before_selection',
   'research_paper_review','research_builder_call','research_autonomy_repair','research_autonomy_repair_candidates')
 loop
  definition=pg_get_functiondef(item.oid);original=definition;
  for i in 1..array_length(patterns,1) loop
   before=patterns[i][1];after=patterns[i][2];definition=replace(definition,before,after);
  end loop;
  if definition<>original then execute definition;changes=changes+1;end if;
 end loop;
 if changes<>13 then raise exception 'Expected 13 current budget admission functions, found %',changes;end if;
end $migration$;

create function public.research_autonomy_set_budget(p_study uuid,p_request uuid,p_max_cents integer,p_resume boolean,p_authorized_by text,p_reason text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w public.research_autonomy_workflows; prior public.research_autonomy_events; resumed uuid[]:=array[]::uuid[];
begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_request is null or (p_max_cents is not null and p_max_cents<10000) or p_resume is null
  or p_authorized_by is null or length(p_authorized_by) not between 1 and 500
  or p_reason is null or length(p_reason) not between 1 and 3000 then raise exception 'Explicit operator budget authorization required';end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 select * into prior from public.research_autonomy_events where id=p_request;
 if found then
  if prior.study_id<>p_study or prior.event<>'budget-authorization-amended'
   or prior.details->>'version'<>'assessment-budget-amendment-v2'
   or prior.details->'max_spend_cents' is distinct from coalesce(to_jsonb(p_max_cents),'null'::jsonb)
   or prior.details->>'authorized_by' is distinct from p_authorized_by or prior.details->>'reason' is distinct from p_reason
   or prior.details->'resume_budget_tasks' is distinct from to_jsonb(p_resume) then raise exception 'Budget amendment request identity conflict';end if;
  return jsonb_build_object('replayed',true,'max_spend_cents',w.max_spend_cents,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'status',w.status);
 end if;
 if w.status in ('cancelled','completed','deadline') or w.deadline_at<=clock_timestamp()+interval '480 seconds'
  or (p_max_cents is not null and p_max_cents<w.committed_cents) then raise exception 'Unexpired authorization and a ceiling covering retained commitments required';end if;
 insert into public.research_autonomy_events(id,study_id,event,details) values(p_request,p_study,'budget-authorization-amended',jsonb_build_object(
  'version','assessment-budget-amendment-v2','transaction_id',pg_current_xact_id()::text,'previous_max_spend_cents',w.max_spend_cents,'max_spend_cents',p_max_cents,
  'authorized_by',p_authorized_by,'reason',p_reason,'resume_budget_tasks',p_resume,'initial_sha256',w.initial_sha256,
  'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,
  'scope','Prospective budget amendment; no refund, deadline reset, scientific relabeling, unknown-call replay or relaxation of per-invocation resources.'));
 update public.research_autonomy_workflows set max_spend_cents=p_max_cents,updated_at=clock_timestamp() where study_id=p_study;
 if p_resume and (p_max_cents is null or w.committed_cents+100<=p_max_cents) then
  -- Only budget-stopped work may be released here. Blocked/waiting tasks and
  -- every uncertain original dispatch remain available to ordinary diagnosis.
  with updated as (
   update public.research_autonomy_tasks t set status='queued',lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp(),
    reason='Explicit operator budget amendment; retained checkpoint and prior evidence preserved.'
   where t.study_id=p_study and t.status='budget'
    and not exists(select 1 from public.research_autonomy_turns r where r.task_id=t.id and r.status='running')
    and not exists(select 1 from public.research_model_dispatches d where d.task_id=t.id and (
     d.status in ('queued','running') or (d.status='unknown' and not exists(
      select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id and r.study_id=d.study_id
       and r.task_id=d.task_id and r.request_sha256=d.request_sha256))))
    and not exists(select 1 from public.research_builder_calls c where c.task_id=t.id and c.status in ('running','unknown'))
   returning id
  ) select coalesce(array_agg(id),array[]::uuid[]) into resumed from updated;
  update public.research_autonomy_workflows set status='running',reason='Explicit operator budget amendment; retained work may continue within the original deadline.',updated_at=clock_timestamp()
   where study_id=p_study and status='budget';
  insert into public.research_autonomy_events(study_id,event,details) values(p_study,'budget-tasks-resumed',jsonb_build_object('request_id',p_request,'task_ids',resumed,
   'scope','Budget-stopped tasks only; blocked and uncertain original work was not replayed.'));
 end if;
 return jsonb_build_object('replayed',false,'max_spend_cents',p_max_cents,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,
  'status',(select status from public.research_autonomy_workflows where study_id=p_study),'resumed_task_ids',resumed);
end $$;
revoke all on function public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text) from public,anon,authenticated;
grant execute on function public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text) to service_role;
notify pgrst,'reload schema';
commit;
