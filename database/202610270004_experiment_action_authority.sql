begin;
-- Standing authority is versioned separately from the immutable base prompt.
-- Historical prompt/evaluation/publication records are not rewritten.
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_action_policy_v1;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default 'congestion-control-emulated')
returns uuid language plpgsql security definer set search_path='' as $$
declare names text[]=array['routine-setup-no-consent-loop','unsupported-capability-not-executed'];begin
 if p_module_id='research-experiment-builder' then
  if p_report->>'execution_policy_version' is distinct from 'experiment-action-policy-v1'
   or p_report->>'execution_policy_sha256' is distinct from '973ae76b13a64f4205ca2f581722da8c237cd8afb61d68e2a36e187562be3e52'
   or p_report->>'authority_amendment' is distinct from 'experiment-action-policy-live-amendment-v1'
   or jsonb_typeof(p_report->'authority_case_reviews') is distinct from 'array'
   then raise exception 'Retained actual-answer evaluation under the current experiment authority is required';end if;
  if jsonb_array_length(p_report->'authority_case_reviews')<>2 or exists(select 1 from unnest(names) name where
   (select count(*) from jsonb_array_elements(p_report->'authority_case_reviews') c where c->>'name'=name
    and c->'passed'='true'::jsonb and c->'actual_answer_reviewed'='true'::jsonb
    and c->>'provider_response_sha256' ~ '^[a-f0-9]{64}$' and coalesce(btrim(c->>'review_notes'),'')<>''
    and c->>'source_set'='development')<>1)
   then raise exception 'Routine autonomy and capability-honesty answer checks must both pass';end if;
 end if;
 return public.publish_agent_prompt_before_action_policy_v1(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);
end $$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_action_policy_v1(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,'reload schema';
commit;
