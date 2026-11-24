begin;

create table public.research_skill_instruction_versions (
  role text not null check (role in ('generator', 'verifier', 'coach')),
  version_id uuid not null default gen_random_uuid(),
  instructions text not null check (instructions ~ '[^[:space:]]' and octet_length(instructions) <= 24000),
  sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz not null default clock_timestamp(),
  primary key (role, version_id)
);

create table public.research_skill_instruction_settings (
  role text primary key check (role in ('generator', 'verifier', 'coach')),
  active_version_id uuid,
  foreign key (role, active_version_id) references public.research_skill_instruction_versions(role, version_id)
);

create table public.research_skill_instruction_publications (
  id bigint generated always as identity primary key,
  role text not null,
  version_id uuid not null,
  previous_version_id uuid,
  actor text not null,
  published_at timestamptz not null default clock_timestamp(),
  foreign key (role, version_id) references public.research_skill_instruction_versions(role, version_id),
  foreign key (role, previous_version_id) references public.research_skill_instruction_versions(role, version_id)
);
create index research_skill_instruction_publications_version
  on public.research_skill_instruction_publications(role, version_id);

alter table public.research_skill_instruction_versions enable row level security;
alter table public.research_skill_instruction_settings enable row level security;
alter table public.research_skill_instruction_publications enable row level security;
revoke all on public.research_skill_instruction_versions, public.research_skill_instruction_settings,
  public.research_skill_instruction_publications from public, anon, authenticated, service_role;

create function public.research_skill_hash_instructions()
returns trigger language plpgsql set search_path = '' as $$
begin
  if tg_op <> 'INSERT' then
    raise exception 'Create a new version to change skill instructions' using errcode = '22023';
  end if;
  new.sha256 := encode(sha256(convert_to(new.instructions, 'UTF8')), 'hex');
  return new;
end
$$;
revoke all on function public.research_skill_hash_instructions() from public, anon, authenticated, service_role;
create trigger research_skill_hash_instructions
  before insert or update or delete on public.research_skill_instruction_versions
  for each row execute function public.research_skill_hash_instructions();

create function public.research_skill_get_instructions(p_role text, p_version_id uuid default null)
returns table (role text, version_id uuid, sha256 text, instructions text)
language sql stable security definer set search_path = '' as $$
  select v.role, v.version_id, v.sha256, v.instructions
  from public.research_skill_instruction_versions v
  join public.research_skill_instruction_settings s on s.role = v.role
  where v.role = p_role and v.version_id = coalesce(p_version_id, s.active_version_id)
    and exists (select 1 from public.research_skill_instruction_publications p
      where p.role = v.role and p.version_id = v.version_id);
$$;
revoke all on function public.research_skill_get_instructions(text,uuid) from public, anon, authenticated, service_role;
grant execute on function public.research_skill_get_instructions(text,uuid) to service_role;

create function public.research_skill_activate_instructions(
  p_role text, p_version_id uuid, p_expected_sha256 text, p_expected_active_version_id uuid
) returns uuid language plpgsql set search_path = '' as $$
declare
  current_version_id uuid;
  version_sha256 text;
begin
  select s.active_version_id into current_version_id
    from public.research_skill_instruction_settings s where s.role = p_role for update;
  if not found then
    raise exception 'Unknown skill role' using errcode = '22023';
  end if;
  if current_version_id is distinct from p_expected_active_version_id then
    raise exception 'Active skill instructions changed during review' using errcode = '40001';
  end if;

  select v.sha256 into version_sha256 from public.research_skill_instruction_versions v
    where v.role = p_role and v.version_id = p_version_id;
  if not found or version_sha256 is distinct from p_expected_sha256 then
    raise exception 'Reviewed skill instruction version or checksum does not match' using errcode = '22023';
  end if;
  if current_version_id = p_version_id then return p_version_id; end if;

  insert into public.research_skill_instruction_publications(role, version_id, previous_version_id, actor)
    values (p_role, p_version_id, current_version_id, session_user);
  update public.research_skill_instruction_settings set active_version_id = p_version_id where role = p_role;
  return p_version_id;
end
$$;
revoke all on function public.research_skill_activate_instructions(text,uuid,text,uuid)
  from public, anon, authenticated, service_role;

insert into public.research_skill_instruction_settings(role) values ('generator'), ('verifier'), ('coach');

-- Initial published versions match the fallback files in the plugin.
insert into public.research_skill_instruction_versions(role, instructions) values
  ('generator', $generator$# Generator workflow

1. Extract text with page boundaries, mark extraction gaps, and distinguish what the paper reports from your interpretation. Cite PDF pages in the Access, Experiment, Data, and Validate breakdown.
2. Use the paper's methods, supplements, and artifacts to specify the testbed, workload, instrumentation, and repetitions. Check dependencies early. Reuse the authors' runnable artifacts where feasible, or rebuild an isolated testbed from the documented setup. When an exact match is unavailable, look for a feasible reconstruction that still tests a specific claim and document the adaptations.
3. Write the ordered experiment steps while preparing the frozen specification. For each claim record its comparison conditions, metric, and decision rule. Record the setup, run, and cleanup commands under the corresponding experiment and steps, with the shareable script files they require.
4. Use preflight and smoke-test output to diagnose setup. Repair and retry recoverable failures within scope and retain raw trial output, configuration, run receipts, and failures. Retrieve the evidence and record any outstanding cleanup as a blocker.
5. Compare fresh observations against the frozen criteria and paper-reported values where comparable. Use figures and tables for paper-reported reference values. Skip figure and text consistency audits. Mark claims untested when the needed experiment never ran and inconclusive when observations are insufficient or noncomparable. Keep any independent Validate report distinct from the experiment's interpretation. Update each experiment with the actual findings and any command or script availability limits.
$generator$),
  ('verifier', $verifier$# Verifier workflow

Match claims to the key by paper citation and meaning. Independently check the method, eligible coverage, units, calculations, and decision rule. Document actual evidence with local relative file and row references. Record the assessment's verdict and the verdict the evidence supports for each claim.

Record blockers and critical failures before awarding credit. Identify the evidence that supports each awarded or withheld point. Preserve unscored criteria and their applicable denominator.
$verifier$),
  ('coach', $coach$# Coach workflow

Identify what worked and what the Verifier observed. Distinguish reporting gaps from method, execution, or evidence integrity issues. Interpret blockers, unscored criteria, and synthetic replays within their scope. Leave unscored criteria out of point deductions. Read the relevant Generator guidance or checks before proposing a change. Label suspected causes as hypotheses and count distinct paper hashes before claiming a pattern across papers.

Cite the development finding or rubric item, identify the smallest supported change, and specify a regression check with an observable pass condition. Carry other findings forward as recommendations. Record which checks ran and their outcomes.
$coach$);

select public.research_skill_activate_instructions(role, version_id, sha256, null)
  from public.research_skill_instruction_versions;

notify pgrst, 'reload schema';
commit;
