begin;
-- Deployment only: keep every original case/reviewer/authority gate.
create or replace function public.publish_agent_prompt_before_action_policy_v1(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default 'congestion-control-emulated')
returns uuid language plpgsql security definer set search_path='' as $$
declare candidate public.agent_prompt_versions;current_id uuid;names text[]=array['new-implementation','dependency-repair','units-and-bounds','source-injection','missing-equipment','missing-data','checkpoint-resume','budget-stop','heldout-method-a','heldout-method-b'];begin
 if p_module_id<>'research-experiment-builder' then return public.publish_agent_prompt_before_builder_v1(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);end if;
 select * into strict candidate from public.agent_prompt_versions where id=p_version_id and module_id=p_module_id;
 select active_version_id into strict current_id from public.agent_prompt_settings where module_id=p_module_id for update;
 if candidate.version not in ('research-experiment-builder-v1','research-experiment-builder-v2') or current_id is distinct from p_expected_active_version_id or candidate.content_sha256<>p_expected_content_sha256
  or p_report->>'prompt_sha256' is distinct from candidate.content_sha256 or p_report->>'prompt_id' is distinct from candidate.id::text
  or p_report->>'protocol' is distinct from 'experiment-builder-live-evaluation-v1' or p_report->>'runtime' is distinct from 'experiment-builder-v1'
  or p_report->>'status' is distinct from 'passed' or p_report->>'model_id' is distinct from 'gpt-6.1-sol'
  or coalesce((p_report->>'live_provider_calls')::integer,0)<10 or p_report->'local_release_checks_passed' is distinct from 'true'::jsonb
  or jsonb_typeof(p_report->'cases') is distinct from 'array' or jsonb_array_length(p_report->'cases')<>10
  or coalesce(btrim(p_actor),'')='' then raise exception 'Declared actual-answer builder evaluation required; mocked tests cannot publish';end if;
 if exists(select 1 from unnest(names) name where (select count(*) from jsonb_array_elements(p_report->'cases') c
  where c->>'name'=name and c->'passed'='true'::jsonb and c->'actual_answer_reviewed'='true'::jsonb and c->>'provider_response_sha256' ~ '^[a-f0-9]{64}$'
  and coalesce(c->>'review_notes','')<>'' and c->>'set'=case when name like 'heldout-%' then 'held-out' else 'development' end)<>1)
  or p_report->'reviewer'->'passed' is distinct from 'true'::jsonb
  or exists(select 1 from (values(p_report->'evaluator'),(p_report->'reviewer')) people(person) where coalesce(person->>'type','') not in ('AI','human') or coalesce(person->>'identity','')='' or jsonb_typeof(person->'independent') is distinct from 'boolean')
  or not exists(select 1 from public.agent_prompt_evaluations where prompt_version_id=candidate.id and outcome='passed' and report_raw::jsonb=p_report)
  then raise exception 'All ten retained actual-answer checks and identified reviewers must pass';end if;
 if candidate.version='research-experiment-builder-v2' and (p_report->>'amendment' is distinct from 'experiment-builder-live-amendment-v6' or coalesce(p_report->>'runtime_candidate_sha256','') !~ '^[a-f0-9]{64}$' or coalesce(p_report->>'execution_contract_sha256','') !~ '^[a-f0-9]{64}$' or p_report->'operational_release_checks_passed' is distinct from 'true'::jsonb) then raise exception 'Exact corrected runtime, executor contract and operational checks required';end if;
 if candidate.published_at is null then update public.agent_prompt_versions set published_at=clock_timestamp(),updated_by=p_actor where id=p_version_id;end if;
 insert into public.agent_prompt_publications(prompt_version_id,previous_version_id,published_by,evaluation_report) values(p_version_id,current_id,p_actor,p_report);
 update public.agent_prompt_settings set active_version_id=p_version_id,updated_at=clock_timestamp() where module_id=p_module_id;
 return p_version_id;
end $$;
revoke all on function public.publish_agent_prompt_before_action_policy_v1(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
notify pgrst,'reload schema';
commit;
