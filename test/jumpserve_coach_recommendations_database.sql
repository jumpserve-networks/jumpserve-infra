-- Run against an isolated PostgreSQL database after applying the migration.
begin;

do $$
declare
  report_id uuid;
  other_report_id uuid;
  baseline_id uuid;
  baseline_sha256 text;
  draft_id uuid;
  draft_sha256 text;
  recorded_at_before_retry timestamptz;
  commit_sha text := repeat('a', 40);
  original_report jsonb := '{"version":"jumpserve-coach-report-v1","recommendations":[
    {"title":"Improve summary"}, {"title":"Improve summary"}, {"title":"Record retries"}
  ]}';
begin
  insert into public.research_skill_coach_reports(owner_id, report_sha256, report)
    values (gen_random_uuid(), repeat('a', 64), original_report) returning id into report_id;
  insert into public.research_skill_coach_reports(owner_id, report_sha256, report)
    values (gen_random_uuid(), repeat('b', 64), original_report) returning id into other_report_id;
  if (select count(*) from public.research_skill_coach_recommendations
    where coach_report_id = report_id and status = 'unrecorded') <> 3 then
    raise exception 'Earlier recommendations should be available without an implementation record';
  end if;

  select v.version_id, v.sha256 into strict baseline_id, baseline_sha256
    from public.research_skill_get_instructions('generator') v;
  insert into public.research_skill_instruction_versions(role, instructions)
    values ('generator', 'Synthetic reviewed guidance.') returning version_id, sha256 into draft_id, draft_sha256;
  begin
    perform public.research_skill_record_coach_implementation(report_id, 1, draft_id);
    raise exception 'An unpublished Generator version was recorded';
  exception when no_data_found then null;
  end;
  begin
    perform public.research_skill_record_coach_implementation(report_id, 1,
      (select version_id from public.research_skill_get_instructions('verifier')));
    raise exception 'A non-Generator version was recorded';
  exception when no_data_found then null;
  end;
  begin
    perform public.research_skill_record_coach_implementation(report_id, 4, baseline_id);
    raise exception 'A nonexistent recommendation was recorded';
  exception when no_data_found then null;
  end;
  begin
    perform public.research_skill_record_coach_implementation(report_id, 1, p_git_commit_sha => 'main');
    raise exception 'An invalid Git commit reference was recorded';
  exception when invalid_parameter_value then null;
  end;

  perform public.research_skill_activate_instructions('generator', draft_id, draft_sha256, baseline_id);
  perform public.research_skill_record_coach_implementation(report_id, 1, draft_id);
  select recorded_at into strict recorded_at_before_retry from public.research_skill_coach_recommendations
    where coach_report_id = report_id and recommendation_number = 1;
  perform public.research_skill_record_coach_implementation(report_id, 1, draft_id);
  perform public.research_skill_record_coach_implementation(report_id, 2, p_git_commit_sha => commit_sha);
  begin
    perform public.research_skill_record_coach_implementation(report_id, 2, p_git_commit_sha => repeat('b', 40));
    raise exception 'The original implementation evidence was overwritten';
  exception when unique_violation then null;
  end;
  perform public.research_skill_activate_instructions('generator', baseline_id, baseline_sha256, draft_id);

  if not exists (select 1 from public.research_skill_coach_recommendations
      where coach_report_id = report_id and recommendation_number = 1 and status = 'implemented'
        and generator_version_id = draft_id and generator_published_at is not null
        and recorded_at = recorded_at_before_retry and recorded_by = current_user)
    or not exists (select 1 from public.research_skill_coach_recommendations
      where coach_report_id = report_id and recommendation_number = 2 and status = 'implemented' and git_commit_sha = commit_sha)
    or not exists (select 1 from public.research_skill_coach_recommendations
      where coach_report_id = report_id and recommendation_number = 3 and status = 'unrecorded')
    or exists (select 1 from public.research_skill_coach_recommendations
      where coach_report_id = other_report_id and status <> 'unrecorded')
    or (select report from public.research_skill_coach_reports where id = report_id) <> original_report then
    raise exception 'Implementation tracking changed another recommendation, lost evidence, or changed the original report';
  end if;
end
$$;

do $$
declare
  client text;
begin
  foreach client in array array['anon', 'authenticated', 'service_role'] loop
    if has_table_privilege(client, 'public.research_skill_coach_recommendations', 'SELECT')
      or has_table_privilege(client, 'public.research_skill_coach_recommendation_implementations', 'SELECT,INSERT,UPDATE,DELETE')
      or has_function_privilege(client, 'public.research_skill_record_coach_implementation(uuid,integer,uuid,text)', 'EXECUTE') then
      raise exception 'Unexpected client access to Coach implementation tracking';
    end if;
  end loop;
end
$$;

rollback;
