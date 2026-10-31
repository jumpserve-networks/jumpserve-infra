begin;
-- A verified operational release can reopen only these known controller stops.
-- Provider outcomes, scientific findings, context, labels, counters, commitments
-- and deadlines are retained. All ordinary admission checks still run at lease.
create function public.research_runtime_resume(p_release uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare release public.platform_releases; t public.research_autonomy_tasks;
 resumed uuid[]:=array[]::uuid[]; binding text;
begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict release from public.platform_releases where id=p_release;
 binding=release.verification->>'source_binding';
 if release.status is distinct from 'verified' or release.component is distinct from 'research-runtime'
  or release.repository is distinct from 'jumpserve-networks/jumpserve-back-end'
  or release.verification->>'passed' is distinct from 'true'
  or release.verification->>'revision' is distinct from release.revision
  or release.verification->>'component' is distinct from release.component
  or release.verification->>'all_other_template_content_preserved' is distinct from 'true'
  or release.verification->>'scientific_and_request_content_unchanged' is distinct from 'true'
  or release.verification->>'existing_tests_unchanged' is distinct from 'true'
  or not coalesce(binding~'^[a-f0-9]{64}$',false)
  or not exists(select 1 from public.platform_releases p where p.task_id=release.task_id and p.component='research-runtime-pin'
   and p.status='verified' and p.revision=release.verification->>'pin_revision' and p.verification->>'source_binding'=binding)
 then raise exception 'Exact verified operational production release and pin required';end if;
 if exists(select 1 from public.platform_settings where id and paused) then return jsonb_build_object('resumed_task_ids',resumed,'paused',true);end if;
 for t in select a.* from public.research_autonomy_tasks a
  join public.research_autonomy_workflows w on w.study_id=a.study_id
  where a.claim_id is not null and a.status='blocked' and a.stage='planning'
   and a.reason in ('A UUID identifier is required.','Worker lease expired; reconcile retained provider/experiment identity before more work.')
   and w.status in ('running','completed-with-blockers') and w.deadline_at>clock_timestamp()+interval '480 seconds'
   and (w.max_spend_cents is null or w.committed_cents+100<=w.max_spend_cents)
   and (w.max_attempts is null or a.attempts<w.max_attempts)
   and public.research_category_budget_allows(a.study_id,a.id,100,1)
   and not exists(select 1 from public.research_autonomy_events e where e.task_id=a.id and e.event='runtime-release-resumed' and e.details->>'source_binding'=binding)
   and not exists(select 1 from public.research_autonomy_turns r where r.task_id=a.id and r.status in ('running','unknown'))
   and not exists(select 1 from public.research_builder_calls b where b.task_id=a.id and b.status in ('running','unknown'))
   and not exists(select 1 from public.research_model_dispatches d where d.task_id=a.id and d.status<>'complete')
   and not exists(select 1 from public.research_model_dispatches d where d.task_id=a.id and not exists(
    select 1 from public.research_artifacts ar where ar.id=d.response_artifact_id and ar.study_id=a.study_id and ar.sha256=d.response_sha256))
   and not exists(select 1 from public.research_queue_jobs j where j.id in (
    select value::uuid from jsonb_array_elements_text(coalesce(a.context->'job_ids','[]')||coalesce(a.context->'completed_job_ids','[]')))
    and j.status in ('queued','running','unknown'))
  order by a.updated_at,a.id limit 16 for update of a
 loop
  insert into public.research_autonomy_events(study_id,task_id,event,details)
  values(t.study_id,t.id,'runtime-release-resumed',jsonb_build_object('release_id',p_release,'source_binding',binding,'revision',release.revision,
   'original_reason',t.reason,'original_stage',t.stage,'original_context_sha256',encode(sha256(convert_to(t.context::text,'UTF8')),'hex'),
   'attempts',t.attempts,'label',t.label,'scope','Operational recovery only; scientific criteria and findings unchanged.'));
  update public.research_autonomy_tasks set status='queued',reason='Verified operational controller release; original evidence, findings and limits retained.',
   lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp() where id=t.id;
  update public.research_autonomy_workflows set status='running',updated_at=clock_timestamp() where study_id=t.study_id;
  resumed=array_append(resumed,t.id);
 end loop;
 return jsonb_build_object('resumed_task_ids',resumed,'source_binding',binding,'uncertain_calls_replayed',false,'scientific_completion',false);
end$$;
revoke all on function public.research_runtime_resume(uuid) from public,anon,authenticated;
grant execute on function public.research_runtime_resume(uuid) to service_role;
notify pgrst,'reload schema';
commit;
