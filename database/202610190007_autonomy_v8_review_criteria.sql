begin;
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_autonomy_v8_criteria;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default $$congestion-control-emulated$$) returns uuid language plpgsql security definer set search_path='' as $body$
begin
 if exists(select 1 from public.agent_prompt_versions where id=p_version_id and version=$$research-autonomy-v8$$) then
  if p_report->>$$judgment_criteria_sha256$$ is distinct from $$1f887eec52fe7eb03c7e4dccc41cda39e11c77fe693f44cc80e177f0cdebd840$$
   or p_report->>$$review_amendment$$ is distinct from $$autonomy-bounded-followups-amendment-v4$$
   or p_report->$$original_strict_checks_passed$$ is distinct from $$8$$::jsonb
   or p_report->$$original_strict_checks_total$$ is distinct from $$9$$::jsonb
   or p_report->$$intermediate_only_cases$$ is distinct from $$["earlier-partial-discrepancy"]$$::jsonb
   or coalesce(p_report->>$$original_evaluation_report_sha256$$,$$$$) !~ $$^[a-f0-9]{64}$$ then raise exception $$Preserve original strict failures and explicit intermediate-only review criteria$$; end if;
 end if;
 return public.publish_agent_prompt_before_autonomy_v8_criteria(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);
end $body$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_autonomy_v8_criteria(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_autonomy_v8_criteria(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,$$reload schema$$;
commit;
