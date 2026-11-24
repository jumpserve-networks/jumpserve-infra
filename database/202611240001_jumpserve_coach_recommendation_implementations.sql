begin;

create table public.research_skill_coach_recommendation_implementations (
  coach_report_id uuid not null references public.research_skill_coach_reports(id),
  recommendation_number integer not null check (recommendation_number between 1 and 20),
  generator_publication_id bigint references public.research_skill_instruction_publications(id),
  git_commit_sha text check (git_commit_sha ~ '^[a-f0-9]{40}$'),
  recorded_at timestamptz not null default clock_timestamp(),
  recorded_by text not null default current_user,
  primary key (coach_report_id, recommendation_number),
  check (generator_publication_id is not null or git_commit_sha is not null)
);
create index research_skill_coach_implementations_publication
  on public.research_skill_coach_recommendation_implementations(generator_publication_id);

alter table public.research_skill_coach_recommendation_implementations enable row level security;
revoke all on public.research_skill_coach_recommendation_implementations from public, anon, authenticated, service_role;

-- Saved Coach reports retain their original recommendation order.
create view public.research_skill_coach_recommendations with (security_invoker = true) as
  select r.id as coach_report_id, r.owner_id, r.created_at as report_created_at,
    recommendation.number::integer as recommendation_number,
    recommendation.item->>'title' as title,
    recommendation.item->>'proposed_change' as proposed_change,
    recommendation.item->>'regression_check' as regression_check,
    case when implementation.coach_report_id is null then 'unrecorded' else 'implemented' end as status,
    publication.version_id as generator_version_id,
    publication.published_at as generator_published_at,
    implementation.git_commit_sha, implementation.recorded_at, implementation.recorded_by
  from public.research_skill_coach_reports r
  cross join lateral jsonb_array_elements(r.report->'recommendations') with ordinality as recommendation(item, number)
  left join public.research_skill_coach_recommendation_implementations implementation
    on implementation.coach_report_id = r.id and implementation.recommendation_number = recommendation.number
  left join public.research_skill_instruction_publications publication
    on publication.id = implementation.generator_publication_id;
revoke all on public.research_skill_coach_recommendations from public, anon, authenticated, service_role;

create function public.research_skill_record_coach_implementation(
  p_coach_report_id uuid, p_recommendation_number integer,
  p_generator_version_id uuid default null, p_git_commit_sha text default null
) returns void language plpgsql set search_path = '' as $$
declare
  matched_publication_id bigint;
begin
  if p_recommendation_number is null or p_recommendation_number not between 1 and 20 then
    raise exception 'Supply the one-based Coach recommendation number' using errcode = '22023';
  end if;
  if (p_generator_version_id is null and p_git_commit_sha is null)
    or (p_git_commit_sha is not null and p_git_commit_sha !~ '^[a-f0-9]{40}$') then
    raise exception 'Supply a published Generator version or a full Git commit SHA' using errcode = '22023';
  end if;

  if not exists (select 1 from public.research_skill_coach_reports r where r.id = p_coach_report_id
    and jsonb_typeof(r.report->'recommendations'->(p_recommendation_number - 1)) = 'object') then
    raise exception 'Coach recommendation does not exist' using errcode = 'P0002';
  end if;

  if p_generator_version_id is not null then
    select p.id into matched_publication_id from public.research_skill_instruction_publications p
      where p.role = 'generator' and p.version_id = p_generator_version_id order by p.id limit 1;
    if not found then
      raise exception 'Generator guidance version has no publication' using errcode = 'P0002';
    end if;
  end if;

  insert into public.research_skill_coach_recommendation_implementations
    (coach_report_id, recommendation_number, generator_publication_id, git_commit_sha)
    values (p_coach_report_id, p_recommendation_number, matched_publication_id, p_git_commit_sha)
    on conflict (coach_report_id, recommendation_number) do nothing;

  if not found and not exists (
    select 1 from public.research_skill_coach_recommendation_implementations i
    where i.coach_report_id = p_coach_report_id and i.recommendation_number = p_recommendation_number
      and i.generator_publication_id is not distinct from matched_publication_id
      and i.git_commit_sha is not distinct from p_git_commit_sha
  ) then
    raise exception 'Recommendation already has different implementation evidence' using errcode = '23505';
  end if;
end
$$;
revoke all on function public.research_skill_record_coach_implementation(uuid,integer,uuid,text)
  from public, anon, authenticated, service_role;

notify pgrst, 'reload schema';
commit;
