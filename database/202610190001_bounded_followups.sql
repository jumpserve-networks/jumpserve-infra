begin;
alter table public.research_network_executions drop constraint research_network_executions_runner_check;
alter table public.research_network_executions add constraint research_network_executions_runner_check
 check(runner in ('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1'));

-- Operator-only recovery of known pre-dispatch context failures. Scientific
-- outcomes, original prompts, limits, attempts and commitments are unchanged.
create function public.research_autonomy_resume_context(p_study uuid,p_actor uuid,p_task uuid,p_version text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w public.research_autonomy_workflows;t public.research_autonomy_tasks; begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_version is distinct from 'autonomy-evidence-v2' or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Verified owner and recovery implementation required'; end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 select * into strict t from public.research_autonomy_tasks where study_id=p_study and id=p_task for update;
 if w.status not in ('running','completed-with-blockers') or w.deadline_at<=clock_timestamp()+interval '180 seconds' or w.committed_cents+5>w.max_spend_cents or t.attempts>=w.max_attempts then raise exception 'Original paper limits prevent recovery'; end if;
 if t.status<>'blocked' or t.stage not in ('planning','assessment') or t.reason not in (
  'Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.',
  'Evidence context exceeds the interactive measurement bound; retain unresolved status without truncation.') then raise exception 'Only known pre-dispatch context failures can resume'; end if;
 if exists(select 1 from public.research_autonomy_events where task_id=p_task and event='context-recovery' and details->>'implementation'=p_version) then raise exception 'This version already attempted recovery; preserve the repeated blocker'; end if;
 if exists(select 1 from public.research_autonomy_turns where task_id=p_task and status in ('running','unknown','failed'))
  or exists(select 1 from public.research_queue_jobs where id in (select value::uuid from jsonb_array_elements_text(coalesce(t.context->'job_ids','[]')||coalesce(t.context->'completed_job_ids','[]'))) and status in ('queued','running')) then raise exception 'Reconcile unconfirmed model/experiment identities before recovery'; end if;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(p_study,p_task,'context-recovery',jsonb_build_object('implementation',p_version,'original_reason',t.reason,'attempts',t.attempts,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at));
 -- v6 kept the last selection/reviews after assessment. Preserve those actual
 -- review identities as completed work before clearing the stale selection.
 if t.stage='planning' and t.context->>'selected_check_id' is not null
  and coalesce(t.context->'completed_job_ids','[]') ? (t.context->>'selected_check_id')
  and jsonb_array_length(coalesce(t.context->'reviews','[]'))=2
  and (select count(distinct r.stage) from jsonb_array_elements(t.context->'reviews') review
       join public.research_autonomy_turns r on r.id=(review->>'turn_id')::uuid and r.task_id=t.id
       where r.stage in ('comprehension','critic') and r.status='complete' and r.output->'ready'='true'::jsonb)=2 then
  t.context=jsonb_set(t.context,'{completed_reviews}',coalesce(t.context->'completed_reviews','{}')||jsonb_build_object(t.context->>'selected_check_id',t.context->'reviews'))-'selected_check_id'-'proposal'-'evidence_read';
 end if;
 update public.research_autonomy_tasks set status='queued',context=t.context,reason='Known context failure recovered using retained evidence; original limits remain.',next_at=clock_timestamp(),updated_at=clock_timestamp() where id=p_task returning * into t;
 update public.research_autonomy_workflows set status='running',reason='Retained task resumed within original authorization.',updated_at=clock_timestamp() where study_id=p_study;
 return to_jsonb(t)-array['lease_token'];
end $$;
revoke all on function public.research_autonomy_resume_context(uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.research_autonomy_resume_context(uuid,uuid,uuid,text) to service_role;
create function public.research_autonomy_context_candidates() returns jsonb language sql security definer set search_path='' as $$
 select coalesce(jsonb_agg(to_jsonb(c)),'[]') from (
  select t.id,t.study_id,o.owner_id from public.research_autonomy_tasks t
  join public.research_autonomy_workflows w on w.study_id=t.study_id
  join public.research_study_owners o on o.study_id=t.study_id
  where t.status='blocked' and t.stage in ('planning','assessment') and t.attempts<w.max_attempts
   and w.status in ('running','completed-with-blockers') and w.deadline_at>clock_timestamp()+interval '180 seconds' and w.committed_cents+5<=w.max_spend_cents
   and t.reason in ('Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.','Evidence context exceeds the interactive measurement bound; retain unresolved status without truncation.')
   and not exists(select 1 from public.research_autonomy_events e where e.task_id=t.id and e.event='context-recovery' and e.details->>'implementation'='autonomy-evidence-v2')
   and not exists(select 1 from public.research_autonomy_turns r where r.task_id=t.id and r.status in ('running','unknown','failed'))
  order by t.updated_at,t.id limit 2
 ) c;
$$;
revoke all on function public.research_autonomy_context_candidates() from public,anon,authenticated;
grant execute on function public.research_autonomy_context_candidates() to service_role;
notify pgrst,'reload schema';
commit;
