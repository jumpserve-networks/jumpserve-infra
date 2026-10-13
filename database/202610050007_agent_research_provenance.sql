-- Read-only provenance for the authenticated Google user's own module history.
begin;
drop function public.get_agent_answer_provenance(uuid,text);
create function public.get_agent_answer_provenance(p_session_id uuid, p_module_id text)
returns table(answer_id uuid,response text,prompt_version text,prompt_version_id uuid,prompt_content_sha256 text,analysis_version text,created_at timestamptz,answer_provenance jsonb)
language sql stable security definer set search_path='' as $$
 select a.id,a.response,v.version,v.id,v.content_sha256,a.analysis_version,a.created_at,a.answer_provenance
 from public.agent_answers a
 join public.agent_sessions s on s.id=a.session_id
 join public.agent_prompt_versions v on v.id=a.prompt_version_id
 where s.id=p_session_id and s.module_id=p_module_id and v.module_id=p_module_id
   and s.user_id=auth.jwt()->>'email' and auth.uid() is not null
   and (auth.jwt()->'app_metadata'->'providers') ? 'google'
 order by a.created_at,a.id;
$$;
revoke all on function public.get_agent_answer_provenance(uuid,text) from public,anon,authenticated;
grant execute on function public.get_agent_answer_provenance(uuid,text) to authenticated;
commit;
