begin;

-- A completed review can find no evidence-backed recommendation.
create or replace function public.research_skill_save_coach_report(p_owner uuid, p_hash text, p_report jsonb)
returns uuid language plpgsql security definer set search_path = '' as $$
declare
  saved_id uuid;
  source_ids uuid[];
  requested_count integer;
begin
  if p_owner is null or p_hash is null or p_hash !~ '^[a-f0-9]{64}$'
    or p_report->>'version' is distinct from 'jumpserve-coach-report-v1'
    or octet_length(p_report::text) > 85000
    or jsonb_typeof(p_report->'summary') is distinct from 'string'
    or jsonb_typeof(p_report->'sources') is distinct from 'array'
    or jsonb_typeof(p_report->'recommendations') is distinct from 'array'
    or jsonb_typeof(p_report->'limitations') is distinct from 'array'
  then raise exception 'Invalid Coach report' using errcode = '22023'; end if;

  requested_count := jsonb_array_length(p_report->'sources');
  if requested_count not between 1 and 20 or jsonb_array_length(p_report->'recommendations') > 20
    or requested_count <> (select count(distinct s.verification_id)
      from jsonb_to_recordset(p_report->'sources') as s(verification_id uuid))
  then raise exception 'Invalid Coach report sources or recommendations' using errcode = '22023'; end if;

  perform pg_advisory_xact_lock_shared(hashtextextended('research-autonomy-v1', 0));
  select array_agg(v.id) into source_ids
    from jsonb_to_recordset(p_report->'sources') as src(verification_id uuid, assessment_sha256 text)
    join public.research_skill_verifier_results v on v.id = src.verification_id and v.assessment_sha256 = src.assessment_sha256
    join public.research_skill_generator_results g on g.id = v.generator_result_id
    join public.research_skill_submissions s on s.id = g.assessment_id
    where s.owner_id = p_owner and v.split = 'development' and not public.research_assessment_deleted(s.id);
  if cardinality(source_ids) is distinct from requested_count then
    raise exception 'Development Verifier scorecard not found' using errcode = 'P0002';
  end if;

  insert into public.research_skill_coach_reports(owner_id, report_sha256, report)
    values (p_owner, p_hash, p_report)
    on conflict (owner_id, report_sha256) do nothing returning id into saved_id;
  if saved_id is null then
    select id into saved_id from public.research_skill_coach_reports
      where owner_id = p_owner and report_sha256 = p_hash and report = p_report;
    if saved_id is null then raise exception 'Coach report hash conflict' using errcode = '22023'; end if;
    return saved_id;
  end if;

  insert into public.research_skill_coach_sources(coach_report_id, verification_id)
    select saved_id, unnest(source_ids);
  return saved_id;
end
$$;

commit;
