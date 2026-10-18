begin;
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_autonomy_phase_v6;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default 'congestion-control-emulated') returns uuid language plpgsql security definer set search_path='' as $$
declare candidate public.agent_prompt_versions; current_id uuid; required text[]=array['source-injection','exact-page-grounding','unavailable-input','unavailable-equipment','failed-review-followup','locked-configuration','dependence','units','missing-versus-zero','partial-claim-coverage','no-result-forcing','source-omissions','budget-exhaustion','measured-evidence-only','positive-comprehension','positive-critic']; begin
 if p_module_id<>'research-autonomy' then return public.publish_agent_prompt_before_autonomy_phase_v6(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id); end if;
 select active_version_id into strict current_id from public.agent_prompt_settings where module_id=p_module_id for update;
 if current_id is distinct from p_expected_active_version_id then raise exception 'Active prompt changed'; end if;
 select * into strict candidate from public.agent_prompt_versions where id=p_version_id and module_id=p_module_id;
 if candidate.version<>'research-autonomy-v6' or candidate.content_sha256<>p_expected_content_sha256
  or p_report->>'prompt_content_sha256' is distinct from candidate.content_sha256 or p_report->>'prompt_version_id' is distinct from candidate.id::text
  or p_report->>'module_id' is distinct from p_module_id or p_report->>'analysis_version' is distinct from 'research-autonomy-v1'
  or p_report->>'protocol' is distinct from 'autonomous-assessment-protocol-v1'
  or p_report->>'evaluation_kind' is distinct from 'actual-model-development'
  or p_report->'live_provider_calls' is distinct from '16'::jsonb
  or p_report->>'release_amendment' is distinct from 'autonomous-assessment-production-amendment-v8'
  or p_report->>'model_id' is distinct from 'us.anthropic.claude-opus-4-6-v1'
  or p_report->>'cases_sha256' is distinct from 'f866c1cfb87309748a6847098b7e45d665602a38bea31dc56a837b728246fcda'
  or p_report->>'request_manifest_sha256' is distinct from '7e22f8ee4189fc13e1bc0208a11959d1de392dc91105b1fcca7eba9878b3d26f'
  or p_report->>'response_channel_sha256' is distinct from 'd8beedd8e3c6fc8852456e6cc4a7946fb999b77a58ca71a3e4178ff25b9195cc'
  or p_report->'input_sha256'->>'autonomy.py' is distinct from '91558757e68801089190b70ca93a40c33d22b3f387acbfb232ca51a8e7f26cb9' or
  p_report->'input_sha256'->>'autonomy_model.py' is distinct from '158feca665ba216d7e66ecbdb023a2ad15937369f044e1b84c9b4325895246ea' or
  p_report->'input_sha256'->>'autonomy_sources.py' is distinct from '4f26059b9b4b3baa511c995735ac39af14f01a6e5f957a9d0c72b544ec693474' or
  p_report->'input_sha256'->>'policies/autonomy-experiment-costs-v1.json' is distinct from '395b28c725e892370460d7582c2214124bb51c4c7ee7af9de96804a4daa9566b'
  or coalesce(btrim(p_actor),'')='' then raise exception 'Exact actual-answer autonomous evaluation provenance required'; end if;
 if jsonb_typeof(p_report->'cases') is distinct from 'array' then raise exception 'Actual answer reviews required'; end if;
 if jsonb_array_length(p_report->'cases')<>cardinality(required) or exists(select 1 from unnest(required) name where
  (select count(*) from jsonb_array_elements(p_report->'cases') c where c->>'name'=name and c->'passed'='true'::jsonb and c->>'status'='complete'
   and c->'raw_answer_reviewed'='true'::jsonb and c->'rendered_answer_reviewed'='true'::jsonb
   and c->>'output_sha256' ~ '^[a-f0-9]{64}$' and c->>'provider_response_sha256' ~ '^[a-f0-9]{64}$')<>1) then raise exception 'All sixteen raw and rendered answer checks must pass'; end if;
 if exists(select 1 from (values(p_report->'evaluator'),(p_report->'reviewer')) people(person) where coalesce(person->>'type','') not in ('human','AI') or coalesce(btrim(person->>'identity'),'')='' or jsonb_typeof(person->'independent') is distinct from 'boolean') or p_report->'reviewer'->'passed' is distinct from 'true'::jsonb then raise exception 'Explicit evaluator/reviewer identity and independence required'; end if;
 if candidate.published_at is null then update public.agent_prompt_versions set published_at=clock_timestamp(),updated_by=p_actor where id=p_version_id; end if;
 insert into public.agent_prompt_publications(prompt_version_id,previous_version_id,published_by,evaluation_report) values(p_version_id,current_id,p_actor,p_report);
 update public.agent_prompt_settings set active_version_id=p_version_id,updated_at=clock_timestamp() where module_id=p_module_id;
 return p_version_id;
end $$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_autonomy_phase_v6(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_autonomy_phase_v6(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,'reload schema';
commit;
