begin;
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_claim_v5;
revoke all on function public.publish_agent_prompt_before_claim_v5(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated,service_role;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default 'congestion-control-emulated')
returns uuid language plpgsql security definer set search_path='' as $$
declare current_id uuid; candidate public.agent_prompt_versions; required text[]=array['design-networking','design-missing-data','design-equipment','design-causal','design-units','design-injection','design-missing-source','design-complete','design-correlated','design-equivalence','design-null-result','design-config-change','review-comprehension','review-complete','review-units','review-injection','design-known-placement','design-equivalent-units','design-optical-proxy','design-owner-supplied-plan']; begin
 select * into candidate from public.agent_prompt_versions where id=p_version_id;
 if p_module_id<>'research-claim-design' or candidate.version is distinct from 'research-claim-design-v5' then
  return public.publish_agent_prompt_before_claim_v5(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);
 end if;
 select active_version_id into current_id from public.agent_prompt_settings where module_id=p_module_id for update;
 if not found or current_id is distinct from p_expected_active_version_id then raise exception 'Prompt pointer changed'; end if;
 select * into strict candidate from public.agent_prompt_versions where id=p_version_id for update;
 if candidate.module_id<>p_module_id or candidate.content_sha256<>p_expected_content_sha256 or p_report->>'prompt_content_sha256' is distinct from candidate.content_sha256
  or p_report->>'prompt_version_id' is distinct from candidate.id::text or p_report->>'prompt_version' is distinct from candidate.version
  or p_report->>'module_id' is distinct from p_module_id or p_report->>'analysis_version' is distinct from 'claim-experiment-design-v1'
  or p_report->>'protocol' is distinct from 'claim-experiment-design-protocol-v3'
  or p_report->>'evaluation_kind' is distinct from 'actual-model-development'
  or p_report->>'response_version' is distinct from 'claim-design-response-v2'
  or p_report->>'runner_context_sha256' is distinct from 'fb87cf77a216294862ceba39636a787274890ad1b457d24b2d12d1b5f01a162d'
  or p_report->>'response_channel_sha256' is distinct from 'fd61f9d6f7eea788d005b9767d55a463e685d883ab8bee92d21279cada5b09dc'
  or p_report->'input_sha256'->>'agent/claim_experiment_design.py' is distinct from 'b5b836eada5263ecd91834577ec72cf212c5ae8d218e335aa7ad4ed6343524d2'
  or p_report->'input_sha256'->>'agent/research_ideas.py' is distinct from '2142a5dc00ac61663c200e19f19e77e7cfcd5a7915d52bf6393a1ddff2d2b967'
  or p_report->'decision_policy' is distinct from '{"version": "claim-decision-policy-v1", "sha256": "15f01c489c51ca834279f6226bd9048da3abd5e2334d363daba33a7b3e1ad6f3", "mode": "descriptive-only"}'::jsonb
  or p_report->>'cases_sha256' is distinct from 'dc3e804671d82d836d3c9547deb80021e15da9c9fb141a38139a8bf3346988af'
  or coalesce(btrim(p_report->>'model_id'),'')='' or coalesce(btrim(p_actor),'')='' then
  raise exception 'Corrective campaign exact provenance required'; end if;
 if jsonb_typeof(p_report->'cases') is distinct from 'array' then raise exception 'Evaluation cases required'; end if;
 if jsonb_array_length(p_report->'cases')<>cardinality(required) or exists(select 1 from unnest(required) name where
  (select count(*) from jsonb_array_elements(p_report->'cases') c where c->>'name'=name and c->'passed'='true'::jsonb and c->>'status'='complete' and c->>'output_sha256' ~ '^[a-f0-9]{64}$' and c->'raw_answer_reviewed'='true'::jsonb and c->'rendered_answer_reviewed'='true'::jsonb and c->>'rendered_output_sha256' ~ '^[a-f0-9]{64}$')<>1) then raise exception 'All twenty raw and rendered answer reviews must pass'; end if;
 if exists(select 1 from (values(p_report->'evaluator'),(p_report->'reviewer')) a(person) where
  coalesce(person->>'type','') not in ('human','AI') or coalesce(btrim(person->>'identity'),'')='' or jsonb_typeof(person->'independent') is distinct from 'boolean')
  or p_report->'reviewer'->'passed' is distinct from 'true'::jsonb then raise exception 'Explicit evaluator/reviewer identity and independence required'; end if;
 if candidate.published_at is null then update public.agent_prompt_versions set published_at=clock_timestamp(),updated_by=p_actor where id=p_version_id; end if;
 insert into public.agent_prompt_publications(prompt_version_id,previous_version_id,published_by,evaluation_report) values(p_version_id,current_id,p_actor,p_report);
 update public.agent_prompt_settings set active_version_id=p_version_id,updated_at=clock_timestamp() where module_id=p_module_id;
 return p_version_id;
end $$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,'reload schema';
commit;
