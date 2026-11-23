begin;

create table public.research_skill_generator_results (
  id uuid primary key default gen_random_uuid(),
  assessment_id uuid not null references public.research_skill_submissions(id),
  bundle_sha256 text not null check (bundle_sha256 ~ '^[a-f0-9]{64}$'),
  paper_sha256 text not null check (paper_sha256 ~ '^[a-f0-9]{64}$'),
  result_kind text not null check (result_kind in ('assessment', 'replay_analysis')),
  bundle jsonb not null check (jsonb_typeof(bundle) = 'object' and octet_length(bundle::text) <= 700000),
  created_at timestamptz not null default clock_timestamp(),
  unique (assessment_id, bundle_sha256)
);
create index research_skill_generator_paper on public.research_skill_generator_results(paper_sha256, created_at);

create table public.research_skill_generator_claims (
  result_id uuid not null references public.research_skill_generator_results(id),
  claim_ref text not null,
  page integer check (page > 0),
  claim text not null,
  criterion text not null,
  outcome text not null check (outcome in ('untested', 'inconclusive', 'reproduced', 'discrepant')),
  finding text not null,
  primary key (result_id, claim_ref)
);

create table public.research_skill_generator_runs (
  result_id uuid not null references public.research_skill_generator_results(id),
  run_ref text not null,
  experiment_ref text,
  configuration text not null,
  started_at timestamptz not null,
  artifact_sha256 text not null check (artifact_sha256 ~ '^[a-f0-9]{64}$'),
  primary key (result_id, run_ref)
);

create table public.research_skill_generator_measurements (
  result_id uuid not null,
  run_ref text not null,
  ordinal integer not null check (ordinal > 0),
  claim_ref text not null,
  metric text not null,
  units text not null,
  paper_value numeric,
  observed_value numeric not null,
  primary key (result_id, run_ref, ordinal),
  foreign key (result_id, run_ref) references public.research_skill_generator_runs(result_id, run_ref),
  foreign key (result_id, claim_ref) references public.research_skill_generator_claims(result_id, claim_ref)
);

create table public.research_skill_verifier_results (
  id uuid primary key default gen_random_uuid(),
  generator_result_id uuid not null references public.research_skill_generator_results(id),
  verifier_version text not null check (verifier_version ~ '^[A-Za-z0-9][A-Za-z0-9._+-]{0,79}$'),
  scorecard_sha256 text not null check (scorecard_sha256 ~ '^[a-f0-9]{64}$'),
  assessment_sha256 text not null check (assessment_sha256 ~ '^[a-f0-9]{64}$'),
  answer_key_sha256 text not null check (answer_key_sha256 ~ '^[a-f0-9]{64}$'),
  split text not null check (split in ('development', 'held_out')),
  mode text not null check (mode in ('fresh', 'replay')),
  scenario text,
  integrity_status text not null check (integrity_status in ('verified', 'legacy_archive_matched', 'fixture_only', 'failed')),
  status text not null check (status in ('scored', 'blocked', 'failed')),
  score_earned numeric,
  applicable_maximum numeric,
  rubric_maximum numeric,
  scorecard jsonb not null check (jsonb_typeof(scorecard) = 'object' and octet_length(scorecard::text) <= 110000),
  created_at timestamptz not null default clock_timestamp(),
  unique (generator_result_id, verifier_version, scorecard_sha256),
  unique (id, generator_result_id),
  check ((mode = 'fresh') = (scenario is null)),
  check (num_nonnulls(score_earned, applicable_maximum, rubric_maximum) in (0, 3)),
  check (score_earned >= 0 and score_earned <= applicable_maximum and applicable_maximum <= rubric_maximum)
);
create index research_skill_verifier_key on public.research_skill_verifier_results(answer_key_sha256, verifier_version);

create table public.research_skill_verifier_claims (
  verification_id uuid not null,
  generator_result_id uuid not null,
  key_claim_ref text not null,
  assessment_claim_ref text,
  reported_outcome text check (reported_outcome in ('untested', 'inconclusive', 'reproduced', 'discrepant')),
  supported_outcome text check (supported_outcome in ('untested', 'inconclusive', 'reproduced', 'discrepant')),
  grade text not null check (grade in ('correct', 'incorrect', 'unscored')),
  evidence jsonb not null check (jsonb_typeof(evidence) = 'array'),
  finding text not null,
  primary key (verification_id, key_claim_ref),
  foreign key (verification_id, generator_result_id) references public.research_skill_verifier_results(id, generator_result_id),
  foreign key (generator_result_id, assessment_claim_ref) references public.research_skill_generator_claims(result_id, claim_ref),
  check ((assessment_claim_ref is null) = (reported_outcome is null))
);

alter table public.research_skill_generator_results enable row level security;
alter table public.research_skill_generator_claims enable row level security;
alter table public.research_skill_generator_runs enable row level security;
alter table public.research_skill_generator_measurements enable row level security;
alter table public.research_skill_verifier_results enable row level security;
alter table public.research_skill_verifier_claims enable row level security;
revoke all on public.research_skill_generator_results, public.research_skill_generator_claims,
  public.research_skill_generator_runs, public.research_skill_generator_measurements,
  public.research_skill_verifier_results, public.research_skill_verifier_claims from public, anon, authenticated, service_role;
grant select on public.research_skill_generator_results, public.research_skill_generator_claims,
  public.research_skill_generator_runs, public.research_skill_generator_measurements,
  public.research_skill_verifier_results, public.research_skill_verifier_claims to service_role;

-- Shared projection for Step 1 saves, backfill, and explicit additional results.
create function public.research_skill_record_generator_result(p_assessment_id uuid, p_hash text, p_bundle jsonb)
returns uuid language plpgsql set search_path = '' as $$
declare saved_id uuid;
begin
  insert into public.research_skill_generator_results(assessment_id, bundle_sha256, paper_sha256, result_kind, bundle)
    values (p_assessment_id, p_hash, p_bundle #>> '{paper,sha256}',
      case when p_bundle->>'version' = 'jumpserve-replay-analysis-v1' then 'replay_analysis' else 'assessment' end, p_bundle)
    on conflict (assessment_id, bundle_sha256) do nothing returning id into saved_id;
  if saved_id is null then
    select id into saved_id from public.research_skill_generator_results
      where assessment_id = p_assessment_id and bundle_sha256 = p_hash and bundle = p_bundle;
    if saved_id is null then raise exception 'Generator result hash conflict' using errcode = '22023'; end if;
    return saved_id;
  end if;

  insert into public.research_skill_generator_claims(result_id, claim_ref, page, claim, criterion, outcome, finding)
    select saved_id, c->>'id', (c->>'page')::integer, c->>'claim', c->>'criterion', c->>'outcome', c->>'finding'
    from jsonb_array_elements(p_bundle->'claims') c;
  insert into public.research_skill_generator_runs(result_id, run_ref, experiment_ref, configuration, started_at, artifact_sha256)
    select saved_id, r->>'id', r->>'experiment_id', r->>'configuration', (r->>'started_at')::timestamptz, r->>'artifact_sha256'
    from jsonb_array_elements(p_bundle->'runs') r;
  insert into public.research_skill_generator_measurements(result_id, run_ref, ordinal, claim_ref, metric, units, paper_value, observed_value)
    select saved_id, r->>'id', m.ordinal, m.entry->>'claim_id', m.entry->>'metric', m.entry->>'units',
      (m.entry->>'paper_value')::numeric, (m.entry->>'observed_value')::numeric
    from jsonb_array_elements(p_bundle->'runs') r,
      lateral jsonb_array_elements(r->'measurements') with ordinality m(entry, ordinal);
  return saved_id;
end
$$;
revoke all on function public.research_skill_record_generator_result(uuid,text,jsonb) from public, anon, authenticated, service_role;

create function public.research_skill_project_completed_generator()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  perform public.research_skill_record_generator_result(new.id, new.bundle_sha256, new.bundle);
  return new;
end
$$;
revoke all on function public.research_skill_project_completed_generator() from public, anon, authenticated, service_role;
create trigger research_skill_project_completed_generator
  after insert or update of completed_at, pdf_verified_at on public.research_skill_submissions
  for each row when (new.completed_at is not null) execute function public.research_skill_project_completed_generator();

do $$
declare saved record;
begin
  for saved in select id, bundle_sha256, bundle from public.research_skill_submissions
    where completed_at is not null or study_id is not null
  loop
    perform public.research_skill_record_generator_result(saved.id, saved.bundle_sha256, saved.bundle);
  end loop;
end
$$;

create function public.research_skill_save_generator_result(p_owner uuid, p_assessment_id uuid, p_hash text, p_bundle jsonb)
returns uuid language plpgsql security definer set search_path = '' as $$
declare source_bundle jsonb;
begin
  perform pg_advisory_xact_lock_shared(hashtextextended('research-autonomy-v1', 0));
  select bundle into source_bundle from public.research_skill_submissions
    where id = p_assessment_id and owner_id = p_owner and (completed_at is not null or study_id is not null);
  if not found or public.research_assessment_deleted(p_assessment_id) then
    raise exception 'Completed assessment not found' using errcode = 'P0002';
  end if;
  if coalesce(p_bundle->>'version', '') not in ('jumpserve-assessment-v1', 'jumpserve-replay-analysis-v1')
    or p_bundle #>> '{paper,sha256}' is distinct from source_bundle #>> '{paper,sha256}'
    or (p_bundle->>'version' = 'jumpserve-assessment-v1' and
        p_bundle #> '{paper,byte_count}' is distinct from source_bundle #> '{paper,byte_count}')
  then raise exception 'Assessment result has a different paper or unknown format' using errcode = '22023'; end if;
  return public.research_skill_record_generator_result(p_assessment_id, p_hash, p_bundle);
end
$$;
revoke all on function public.research_skill_save_generator_result(uuid,uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.research_skill_save_generator_result(uuid,uuid,text,jsonb) to service_role;

create function public.research_skill_save_verifier_result(p_owner uuid, p_assessment_id uuid, p_generator_hash text,
  p_bundle jsonb, p_verifier_version text, p_hash text, p_scorecard jsonb)
returns uuid language plpgsql security definer set search_path = '' as $$
declare
  generator public.research_skill_generator_results;
  saved_id uuid;
begin
  perform pg_advisory_xact_lock_shared(hashtextextended('research-autonomy-v1', 0));
  select g.* into generator from public.research_skill_generator_results g
    join public.research_skill_submissions s on s.id = g.assessment_id
    where g.assessment_id = p_assessment_id and g.bundle_sha256 = p_generator_hash and s.owner_id = p_owner;
  if not found or public.research_assessment_deleted(p_assessment_id) then
    raise exception 'Generator result not found' using errcode = 'P0002';
  end if;
  if generator.bundle is distinct from p_bundle
    or p_scorecard->>'version' is distinct from 'jumpserve-verifier-scorecard-v1'
    or p_scorecard->>'paper_sha256' is distinct from generator.paper_sha256
    or (generator.result_kind = 'replay_analysis') is distinct from (p_scorecard #>> '{evidence_integrity,status}' = 'fixture_only')
    or (generator.result_kind = 'replay_analysis' and (p_scorecard->>'mode' is distinct from 'replay'
      or p_scorecard->>'scenario' is distinct from generator.bundle->>'scenario'))
    or exists (
      select 1 from jsonb_array_elements(p_scorecard->'claims') c
      where (c->>'assessment_claim_id' is not null and not exists (
        select 1 from public.research_skill_generator_claims g
        where g.result_id = generator.id and g.claim_ref = c->>'assessment_claim_id' and g.outcome = c->>'reported_outcome'
      )) or (c->>'assessment_claim_id' is null and c->>'reported_outcome' is not null)
    )
  then raise exception 'Scorecard does not match the saved Generator result' using errcode = '22023'; end if;

  insert into public.research_skill_verifier_results(generator_result_id, verifier_version, scorecard_sha256,
    assessment_sha256, answer_key_sha256, split, mode, scenario, integrity_status, status, score_earned, applicable_maximum, rubric_maximum, scorecard)
    values (generator.id, p_verifier_version, p_hash, p_scorecard->>'assessment_sha256', p_scorecard->>'answer_key_sha256',
      p_scorecard->>'split', p_scorecard->>'mode', p_scorecard->>'scenario', p_scorecard #>> '{evidence_integrity,status}',
      p_scorecard->>'status', (p_scorecard #>> '{score,earned}')::numeric, (p_scorecard #>> '{score,applicable_maximum}')::numeric,
      (p_scorecard #>> '{score,rubric_maximum}')::numeric, p_scorecard)
    on conflict (generator_result_id, verifier_version, scorecard_sha256) do nothing returning id into saved_id;
  if saved_id is null then
    select id into saved_id from public.research_skill_verifier_results
      where generator_result_id = generator.id and verifier_version = p_verifier_version
        and scorecard_sha256 = p_hash and scorecard = p_scorecard;
    if saved_id is null then raise exception 'Verifier result hash conflict' using errcode = '22023'; end if;
    return saved_id;
  end if;

  insert into public.research_skill_verifier_claims(verification_id, generator_result_id, key_claim_ref,
    assessment_claim_ref, reported_outcome, supported_outcome, grade, evidence, finding)
    select saved_id, generator.id, c->>'key_claim_id', c->>'assessment_claim_id', c->>'reported_outcome', c->>'supported_outcome',
      c->>'assessment', c->'evidence', c->>'finding'
    from jsonb_array_elements(p_scorecard->'claims') c;
  return saved_id;
end
$$;
revoke all on function public.research_skill_save_verifier_result(uuid,uuid,text,jsonb,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.research_skill_save_verifier_result(uuid,uuid,text,jsonb,text,text,jsonb) to service_role;

notify pgrst, 'reload schema';
commit;
