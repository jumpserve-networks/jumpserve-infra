begin;

-- Separate from the historical v2 recovery. This gate is enabled only by the
-- corrected runtime after it serializes a fitting request without a model call.
create function public.research_autonomy_resume_budget(p_study uuid,p_actor uuid,p_task uuid,p_request_sha256 text,p_request_bytes integer)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w public.research_autonomy_workflows;t public.research_autonomy_tasks; begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_request_sha256 is null or p_request_sha256 !~ '^[a-f0-9]{64}$' or p_request_bytes is null or p_request_bytes not between 1 and 96000
  or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Verified owner and bounded request preflight required'; end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 select * into strict t from public.research_autonomy_tasks where study_id=p_study and id=p_task for update;
 if w.status not in ('running','completed-with-blockers') or w.deadline_at<=clock_timestamp()+interval '180 seconds'
  or w.committed_cents+5>w.max_spend_cents or t.attempts>=w.max_attempts then raise exception 'Original paper limits prevent recovery'; end if;
 if t.status<>'blocked' or t.stage not in ('planning','assessment') or t.reason is distinct from
  'Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.' then raise exception 'Only known pre-dispatch context failures can resume'; end if;
 if exists(select 1 from public.research_autonomy_events where task_id=p_task and event='context-budget-recovery' and details->>'implementation'='autonomy-context-budget-v1') then raise exception 'This version already attempted recovery; preserve the repeated blocker'; end if;
 if exists(select 1 from public.research_autonomy_turns where task_id=p_task and status in ('running','unknown','failed'))
  or exists(select 1 from public.research_queue_jobs where id in (select value::uuid from jsonb_array_elements_text(coalesce(t.context->'job_ids','[]')||coalesce(t.context->'completed_job_ids','[]'))) and status in ('queued','running')) then raise exception 'Reconcile unconfirmed model/experiment identities before recovery'; end if;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(p_study,p_task,'context-budget-recovery',jsonb_build_object(
  'implementation','autonomy-context-budget-v1','original_reason',t.reason,'preflight_request_sha256',p_request_sha256,'preflight_request_bytes',p_request_bytes,
  'attempts',t.attempts,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'scope','Serialization preflight only; no model call or scientific finding'));
 update public.research_autonomy_tasks set status='queued',reason='Current request fits the context budget; original limits and evidence are retained.',next_at=clock_timestamp(),updated_at=clock_timestamp() where id=p_task returning * into t;
 update public.research_autonomy_workflows set status='running',reason='Known context pause resumed within original authorization.',updated_at=clock_timestamp() where study_id=p_study;
 return to_jsonb(t)-array['lease_token'];
end $$;

create function public.research_autonomy_budget_candidates() returns jsonb language sql security definer set search_path='' as $$
 select coalesce(jsonb_agg(to_jsonb(c)),'[]') from (
  select t.id,t.study_id,o.owner_id from public.research_autonomy_tasks t
  join public.research_autonomy_workflows w on w.study_id=t.study_id
  join public.research_study_owners o on o.study_id=t.study_id
  where t.status='blocked' and t.stage in ('planning','assessment') and t.attempts<w.max_attempts
   and w.status in ('running','completed-with-blockers') and w.deadline_at>clock_timestamp()+interval '180 seconds' and w.committed_cents+5<=w.max_spend_cents
   and t.reason='Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.'
   and not exists(select 1 from public.research_autonomy_events e where e.task_id=t.id and e.event='context-budget-recovery' and e.details->>'implementation'='autonomy-context-budget-v1')
   and not exists(select 1 from public.research_autonomy_turns r where r.task_id=t.id and r.status in ('running','unknown','failed'))
   and not exists(select 1 from public.research_queue_jobs j where j.id in (select value::uuid from jsonb_array_elements_text(coalesce(t.context->'job_ids','[]')||coalesce(t.context->'completed_job_ids','[]'))) and j.status in ('queued','running'))
  order by t.updated_at,t.id limit 2
 ) c;
$$;
revoke all on function public.research_autonomy_resume_budget(uuid,uuid,uuid,text,integer),public.research_autonomy_budget_candidates() from public,anon,authenticated;
grant execute on function public.research_autonomy_resume_budget(uuid,uuid,uuid,text,integer),public.research_autonomy_budget_candidates() to service_role;
notify pgrst,'reload schema';
commit;
