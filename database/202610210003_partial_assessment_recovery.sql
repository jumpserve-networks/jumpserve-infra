begin;
create function public.research_autonomy_resume_partial(p_study uuid,p_task uuid,p_implementation text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.research_autonomy_tasks;w public.research_autonomy_workflows;r public.research_autonomy_turns;remaining jsonb;begin
 if p_implementation is distinct from 'continue-retained-checks-v1' then raise exception 'Corrected partial-assessment controller required';end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict t from public.research_autonomy_tasks where study_id=p_study and id=p_task for update;
 if exists(select 1 from public.research_autonomy_events where task_id=t.id and event='partial-assessment-resumed' and details->>'implementation'=p_implementation) then return jsonb_build_object('replayed',true,'task_id',t.id,'status',t.status);end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 if w.status not in ('running','completed-with-blockers') or w.max_attempts is not null or w.committed_cents+100>w.max_spend_cents or w.deadline_at<=clock_timestamp()+interval '180 seconds' then raise exception 'Original paper authorization prevents continuation';end if;
 if t.status<>'blocked' or t.stage<>'assessment' or t.label<>'inconclusive' then raise exception 'Retained partial-assessment pause required';end if;
 select * into strict r from public.research_autonomy_turns where id=(t.context->>'last_turn_id')::uuid and task_id=t.id and study_id=p_study;
 if r.status<>'complete' or r.output->>'action'<>'assess' or r.output->>'assessment_label' not in ('inconclusive','untested') or jsonb_array_length(r.output->'blockers')=0
  or exists(select 1 from jsonb_array_elements(r.output->'blockers') b where b->>'kind' is distinct from 'missing-data') then raise exception 'Only the demonstrated missing-future-results assessment can continue';end if;
 if exists(select 1 from public.research_autonomy_turns where task_id=t.id and status in ('running','unknown','failed')) then raise exception 'Reconcile original model outcomes before continuation';end if;
 if jsonb_array_length(coalesce(t.context->'job_ids','[]'))=0 or exists(
  select 1 from jsonb_array_elements_text(t.context->'job_ids') j where not exists(
   select 1 from public.research_queue_jobs q join public.research_runs n on n.study_id=q.study_id and n.id=q.run_id
    where q.study_id=p_study and q.id=j::uuid and q.status in ('awaiting-review','reviewed') and n.status='complete')) then raise exception 'Completed retained current experiment identities required';end if;
 select coalesce(jsonb_agg(j->>'id'),'[]') into remaining from public.research_prepared_plans p cross join lateral jsonb_array_elements(p.jobs) j
  where p.study_id=p_study and p.id=(t.context->>'prepared_id')::uuid and j->>'execution_mode'='automatic'
   and not ((coalesce(t.context->'tried_check_ids','[]')||coalesce(t.context->'completed_job_ids','[]')||coalesce(t.context->'job_ids','[]')) ? (j->>'id'))
   and not exists(select 1 from public.research_queue_jobs q where q.study_id=p_study and q.id=(j->>'id')::uuid)
   and exists(select 1 from public.research_claim_checks c where c.study_id=p_study and c.claim_id=t.claim_id and c.campaign_id=(j->>'campaign_id')::uuid and c.applicability='applicable');
 if jsonb_array_length(remaining)=0 then raise exception 'No unexecuted retained automatic check remains for this exact claim';end if;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(p_study,t.id,'partial-assessment-resumed',jsonb_build_object('implementation',p_implementation,'old_task',to_jsonb(t)-array['lease_token'],'remaining_check_ids',remaining,'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'scope','Continue the retained assessment stage; no old prompt, finding, counter, resource limit or experiment is replaced.'));
 update public.research_autonomy_tasks set status='queued',reason='Available frozen checks remain; corrected controller will reconsider this retained partial assessment.',lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp() where id=t.id;
 update public.research_autonomy_workflows set status='running',reason='Retained partial assessment continues within its original paper authorization.',updated_at=clock_timestamp() where study_id=p_study;
 return jsonb_build_object('replayed',false,'task_id',t.id,'status','queued','remaining_check_ids',remaining,'attempts',t.attempts);
end $$;
revoke all on function public.research_autonomy_resume_partial(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.research_autonomy_resume_partial(uuid,uuid,text) to service_role;
notify pgrst,'reload schema';
commit;
