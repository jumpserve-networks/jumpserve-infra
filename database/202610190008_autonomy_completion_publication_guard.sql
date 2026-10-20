begin;
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_autonomy_completion;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default $$congestion-control-emulated$$) returns uuid language plpgsql security definer set search_path='' as $body$
declare completion jsonb:=p_report->'completion_report';
begin
 if exists(select 1 from public.agent_prompt_versions where id=p_version_id and version=$$research-autonomy-v8$$) then
  if completion->>'version' is distinct from 'autonomy-followup-completion-v2'
   or completion->'passed' is distinct from 'true'::jsonb
   or completion->'reviewer'->'passed' is distinct from 'true'::jsonb
   or completion->>'decision_protocol_sha256' is distinct from '529daa2302a49e8742d5bf9520fd387c3bdd2876362ab0032d16bf71deac1d37'
   or completion->'input_sha256' is distinct from p_report->'input_sha256'
   or coalesce(p_report->>'completion_report_sha256','') !~ '^[a-f0-9]{64}$'
   or coalesce(completion->>'fixture_sha256','') !~ '^[a-f0-9]{64}$'
   or coalesce(completion->>'frozen_inputs_sha256','') !~ '^[a-f0-9]{64}$'
   or jsonb_typeof(completion->'cases') is distinct from 'array'
   or jsonb_array_length(completion->'cases') not between 1 and 2
   or exists(select 1 from jsonb_array_elements(completion->'cases') c where c->'passed' is distinct from 'true'::jsonb or c->'raw_answer_reviewed' is distinct from 'true'::jsonb or c->'rendered_answer_reviewed' is distinct from 'true'::jsonb)
   or (completion->'cases'->-1->'output'->>'assessment_label') is distinct from 'inconclusive'
   then raise exception 'Passing predeclared completion and actual-answer review required; safe intermediate reads alone do not establish a final judgment'; end if;
 end if;
 return public.publish_agent_prompt_before_autonomy_completion(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);
end $body$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_autonomy_completion(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_autonomy_completion(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,$$reload schema$$;
commit;
