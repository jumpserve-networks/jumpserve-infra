begin;
alter table public.agent_prompt_versions drop constraint agent_prompt_versions_module_id_check;
alter table public.agent_prompt_versions add constraint agent_prompt_versions_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover','http2-compliance-study','reliable-sketch-study','ipv6-dns-study','research-verification'));
alter table public.agent_prompt_settings drop constraint agent_prompt_settings_module_id_check;
alter table public.agent_prompt_settings add constraint agent_prompt_settings_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover','http2-compliance-study','reliable-sketch-study','ipv6-dns-study','research-verification'));
alter table public.agent_sessions drop constraint agent_sessions_module_id_check;
alter table public.agent_sessions add constraint agent_sessions_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover','http2-compliance-study','reliable-sketch-study','ipv6-dns-study','research-verification'));
insert into public.agent_prompt_settings(module_id) values('research-verification');

-- Retain every existing module's publication checks, including later IPv6
-- review amendments. Only the new module uses this additional branch.
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_research_ideas;
revoke all on function public.publish_agent_prompt_before_research_ideas(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated,service_role;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default 'congestion-control-emulated')
returns uuid language plpgsql security definer set search_path='' as $$
declare current_id uuid; candidate public.agent_prompt_versions; required text[]=array['idea-planning','idea-comprehension','idea-critic','idea-missing','idea-novelty','idea-untrusted','idea-clear-plan','idea-scope']; begin
 if p_module_id<>'research-verification' then
  return public.publish_agent_prompt_before_research_ideas(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);
 end if;
 select active_version_id into current_id from public.agent_prompt_settings where module_id=p_module_id for update;
 if not found or current_id is distinct from p_expected_active_version_id then raise exception 'Idea prompt pointer changed'; end if;
 select * into strict candidate from public.agent_prompt_versions where id=p_version_id for update;
 if candidate.module_id<>p_module_id or candidate.content_sha256<>p_expected_content_sha256 or p_report->>'prompt_content_sha256' is distinct from candidate.content_sha256
  or p_report->>'prompt_version_id' is distinct from candidate.id::text or p_report->>'prompt_version' is distinct from candidate.version
  or p_report->>'module_id' is distinct from p_module_id or p_report->>'analysis_version' is distinct from 'research-ideas-v1'
  or p_report->>'evaluation_kind' is distinct from 'actual-model-development' or coalesce(btrim(p_report->>'model_id'),'')='' or coalesce(btrim(p_actor),'')=''
  or coalesce(p_report->>'cases_sha256','') !~ '^[a-f0-9]{64}$' then raise exception 'Exact candidate and actual-answer evaluation provenance required'; end if;
 if jsonb_typeof(p_report->'cases') is distinct from 'array' then raise exception 'Evaluation cases required'; end if;
 if jsonb_array_length(p_report->'cases')<>cardinality(required) or exists(select 1 from unnest(required) name where
  (select count(*) from jsonb_array_elements(p_report->'cases') c where c->>'name'=name and c->'passed'='true'::jsonb and c->>'status'='complete' and c->>'output_sha256' ~ '^[a-f0-9]{64}$')<>1) then raise exception 'Every declared actual-answer development case must pass'; end if;
 if coalesce(p_report->'reviewer'->>'type','') not in ('human','AI') or coalesce(btrim(p_report->'reviewer'->>'identity'),'')='' or
  jsonb_typeof(p_report->'reviewer'->'independent') is distinct from 'boolean' or p_report->'reviewer'->'passed' is distinct from 'true'::jsonb then raise exception 'Declared answer review and independence required; AI review is not human review'; end if;
 if candidate.published_at is null then update public.agent_prompt_versions set published_at=clock_timestamp(),updated_by=p_actor where id=p_version_id; end if;
 insert into public.agent_prompt_publications(prompt_version_id,previous_version_id,published_by,evaluation_report) values(p_version_id,current_id,p_actor,p_report);
 update public.agent_prompt_settings set active_version_id=p_version_id,updated_at=clock_timestamp() where module_id=p_module_id;
 return p_version_id;
end $$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,'reload schema';
commit;
