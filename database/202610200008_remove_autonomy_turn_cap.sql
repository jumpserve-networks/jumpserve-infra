begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));

-- Current limits change prospectively. Original requests, numbered attempts,
-- labels, costs and deadlines are not rewritten. Archive the previous ceiling
-- before making the deprecated max_attempts field explicitly unlimited (NULL).
alter table public.research_autonomy_workflows alter column max_attempts drop default;
alter table public.research_autonomy_workflows alter column max_attempts drop not null;
alter table public.research_autonomy_workflows drop constraint research_autonomy_workflows_max_attempts_check;
alter table public.research_autonomy_workflows disable trigger research_autonomy_workflow_immutable;
insert into public.research_autonomy_events(study_id,event,details)
 select study_id,'turn-policy-changed',jsonb_build_object('implementation','autonomy-turn-policy-v1',
  'previous_max_attempts',max_attempts,'max_attempts',null,'initial_sha256',initial_sha256,
  'committed_cents',committed_cents,'max_spend_cents',max_spend_cents,'deadline_at',deadline_at,
  'reason','Application owner removed the AI turn ceiling; original evidence and remaining resource authorization retained.')
 from public.research_autonomy_workflows;
update public.research_autonomy_workflows set max_attempts=null,updated_at=clock_timestamp();
alter table public.research_autonomy_workflows enable trigger research_autonomy_workflow_immutable;
alter table public.research_autonomy_workflows add constraint research_autonomy_workflows_max_attempts_check check(max_attempts is null);
comment on column public.research_autonomy_workflows.max_attempts is 'Deprecated ceiling; NULL means no AI turn-count limit. Original ceilings remain in immutable initial prompts and policy-change events.';
alter table public.research_autonomy_tasks drop constraint research_autonomy_tasks_attempts_check;
alter table public.research_autonomy_tasks add constraint research_autonomy_tasks_attempts_check check(attempts>=0);
alter table public.research_autonomy_turns drop constraint research_autonomy_turns_number_check;
alter table public.research_autonomy_turns add constraint research_autonomy_turns_number_check check(number>=1);

-- Optional private lab audit relations also accept later numbered turns for
-- future versioned campaigns. This does not amend or replay any frozen pilot.
do $$ declare relation text; begin
 foreach relation in array array['research_runtime_pilot_calls','research_subscription_calls'] loop
  if to_regclass('public.'||relation) is not null then
   execute format('alter table public.%I drop constraint %I',relation,relation||'_number_check');
   execute format('alter table public.%I add constraint %I check(number>=1)',relation,relation||'_number_check');
  end if;
 end loop;
end $$;

-- Replace only the obsolete cap clauses in existing RPCs. Abort on unexpected
-- definitions instead of silently installing a partial migration. Ownership,
-- grants, security-definer/search_path and all other admission gates are kept.
do $migration$
declare signature text; definition text; obsolete text; replacement text; begin
 signature='public.research_autonomy_control(text,uuid,uuid,jsonb)';
 definition=pg_get_functiondef(signature::regprocedure);
 obsolete=$old$  if t.attempts>=w.max_attempts then return jsonb_build_object('denied','attempt-limit'); end if;$old$;
 if strpos(definition,obsolete)=0 then raise exception 'Unexpected autonomous admission definition'; end if;
 definition=replace(definition,obsolete,'');
 obsolete=$old$'attempts_per_claim',25$old$;
 if strpos(definition,obsolete)=0 then raise exception 'Unexpected initial policy event definition'; end if;
 definition=replace(definition,obsolete,$new$'attempts_per_claim',null,'turn_policy','autonomy-turn-policy-v1'$new$);
 obsolete=$old$if w.initial_prompt is distinct from original then raise exception 'Request ID already identifies another initial prompt'; end if;$old$;
 replacement=$new$if w.initial_prompt is distinct from original and not coalesce((
    (w.initial_prompt::jsonb #> '{defaults,attempts_per_claim}')='25'::jsonb
    and (original::jsonb #> '{defaults,attempts_per_claim}')='null'::jsonb
    and (w.initial_prompt::jsonb #- '{defaults,attempts_per_claim}')=(original::jsonb #- '{defaults,attempts_per_claim}')
   ),false) then raise exception 'Request ID already identifies another initial prompt'; end if;$new$;
 if strpos(definition,obsolete)=0 then raise exception 'Unexpected intake replay definition'; end if;
 execute replace(definition,obsolete,replacement);
 foreach signature in array array[
  'public.research_autonomy_resume_context(uuid,uuid,uuid,text)',
  'public.research_autonomy_resume_budget(uuid,uuid,uuid,text,integer)'
 ] loop
  definition=pg_get_functiondef(signature::regprocedure);obsolete=' or t.attempts>=w.max_attempts';
  if strpos(definition,obsolete)=0 then raise exception 'Unexpected recovery definition: %',signature; end if;
  execute replace(definition,obsolete,'');
 end loop;
 foreach signature in array array[
  'public.research_autonomy_context_candidates()',
  'public.research_autonomy_budget_candidates()'
 ] loop
  definition=pg_get_functiondef(signature::regprocedure);obsolete=' and t.attempts<w.max_attempts';
  if strpos(definition,obsolete)=0 then raise exception 'Unexpected recovery discovery definition: %',signature; end if;
  execute replace(definition,obsolete,'');
 end loop;
end $migration$;

-- Only the corrected worker calls this gate. Migration alone does not dispatch
-- work. Existing cap stops resume their original stage/identity without refunds,
-- counter resets, new deadlines, replacement experiments or label changes.
create function public.research_autonomy_resume_turns(p_policy text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.research_autonomy_tasks; w public.research_autonomy_workflows; result jsonb='[]'; begin
 if p_policy is distinct from 'autonomy-turn-policy-v1' then raise exception 'Current controller turn policy required'; end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 for t in select a.* from public.research_autonomy_tasks a join public.research_autonomy_workflows b on b.study_id=a.study_id
  where a.status='attempt-limit' and b.max_attempts is null and b.status in ('running','completed-with-blockers')
   and b.deadline_at>clock_timestamp()+interval '180 seconds' and b.committed_cents+5<=b.max_spend_cents
   and not exists(select 1 from public.research_autonomy_turns r where r.task_id=a.id and r.status in ('running','unknown','failed'))
   and not exists(select 1 from public.research_queue_jobs j where j.id in (
    select value::uuid from jsonb_array_elements_text(coalesce(a.context->'job_ids','[]')||coalesce(a.context->'completed_job_ids','[]'))
   ) and j.status in ('queued','running'))
  order by a.updated_at,a.id for update of a skip locked limit 100
 loop
  select * into strict w from public.research_autonomy_workflows where study_id=t.study_id for update;
  insert into public.research_autonomy_events(study_id,task_id,event,details) values(t.study_id,t.id,'turn-limit-resumed',jsonb_build_object(
   'implementation',p_policy,'original_status',t.status,'original_reason',t.reason,'stage',t.stage,'attempts',t.attempts,
   'committed_cents',w.committed_cents,'deadline_at',w.deadline_at,'label',t.label));
  update public.research_autonomy_tasks set status='queued',reason='AI turn ceiling removed; continuing the retained stage within the original paper budget and deadline.',
   lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp() where id=t.id;
  update public.research_autonomy_workflows set status='running',reason='Retained claim resumed after removal of the AI turn ceiling.',updated_at=clock_timestamp() where study_id=t.study_id;
  result=result||jsonb_build_array(jsonb_build_object('task_id',t.id,'status','queued','attempts',t.attempts));
 end loop;
 return result;
end $$;
revoke all on function public.research_autonomy_resume_turns(text) from public,anon,authenticated;
grant execute on function public.research_autonomy_resume_turns(text) to service_role;
notify pgrst,'reload schema';
commit;
