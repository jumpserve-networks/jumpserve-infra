begin;

-- The connector issues its own opaque, narrowly scoped credentials. Browser
-- sessions and database credentials never leave their existing boundaries.
create table public.jumpserve_mcp_codes (
  code_hash text primary key check (code_hash ~ '^[a-f0-9]{64}$'),
  owner_id uuid not null references auth.users(id) on delete cascade,
  client_id text not null,
  redirect_uri text not null,
  resource text not null,
  challenge text not null check (challenge ~ '^[A-Za-z0-9_-]{43}$'),
  expires_at timestamptz not null default clock_timestamp() + interval '5 minutes'
);
create table public.jumpserve_mcp_tokens (
  access_hash text primary key check (access_hash ~ '^[a-f0-9]{64}$'),
  refresh_hash text not null unique check (refresh_hash ~ '^[a-f0-9]{64}$'),
  owner_id uuid not null references auth.users(id) on delete cascade,
  client_id text not null,
  resource text not null,
  access_expires_at timestamptz not null default clock_timestamp() + interval '1 hour',
  refresh_expires_at timestamptz not null
);
create index jumpserve_mcp_codes_expiry on public.jumpserve_mcp_codes(expires_at);
create index jumpserve_mcp_tokens_expiry on public.jumpserve_mcp_tokens(refresh_expires_at);

create function public.jumpserve_mcp_actor(p_access text, p_resource text)
returns uuid language sql stable security definer set search_path = '' as $$
  select t.owner_id from public.jumpserve_mcp_tokens t join auth.users u on u.id = t.owner_id
  where t.access_hash = p_access and t.resource = p_resource and t.access_expires_at > now()
    and not coalesce(u.is_anonymous, true) and (u.banned_until is null or u.banned_until <= now())
    and exists (select 1 from auth.identities i where i.user_id = u.id and i.provider = 'google')
$$;

create function public.jumpserve_mcp_exchange(
  p_grant text, p_proof_hash text, p_client text, p_resource text,
  p_access text, p_refresh text, p_redirect text default null, p_challenge text default null
) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  actor uuid;
  refresh_deadline timestamptz;
begin
  if p_grant = 'authorization_code' then
    select owner_id into actor from public.jumpserve_mcp_codes
      where code_hash = p_proof_hash and client_id = p_client and resource = p_resource
        and redirect_uri = p_redirect and challenge = p_challenge and expires_at > clock_timestamp();
  elsif p_grant = 'refresh_token' then
    select owner_id into actor from public.jumpserve_mcp_tokens
      where refresh_hash = p_proof_hash and client_id = p_client and resource = p_resource
        and refresh_expires_at > clock_timestamp();
  end if;
  if actor is null then return false; end if;
  perform pg_advisory_xact_lock(hashtextextended('jumpserve-mcp:' || actor::text, 0));
  if p_grant = 'authorization_code' then
    delete from public.jumpserve_mcp_codes
      where code_hash = p_proof_hash and client_id = p_client and resource = p_resource
        and redirect_uri = p_redirect and challenge = p_challenge and expires_at > clock_timestamp()
      returning owner_id into actor;
    refresh_deadline := clock_timestamp() + interval '30 days';
  elsif p_grant = 'refresh_token' then
    delete from public.jumpserve_mcp_tokens
      where refresh_hash = p_proof_hash and client_id = p_client and resource = p_resource
        and refresh_expires_at > clock_timestamp()
      returning owner_id, refresh_expires_at into actor, refresh_deadline;
  else
    return false;
  end if;
  if actor is null then return false; end if;
  if not exists (
    select 1 from auth.users u join auth.identities i on i.user_id = u.id
    where u.id = actor and not coalesce(u.is_anonymous, true) and i.provider = 'google'
      and (u.banned_until is null or u.banned_until <= clock_timestamp())
  ) then return false; end if;
  insert into public.jumpserve_mcp_tokens(access_hash, refresh_hash, owner_id, client_id, resource, refresh_expires_at)
    values (p_access, p_refresh, actor, p_client, p_resource, refresh_deadline);
  return true;
end
$$;

create function public.jumpserve_mcp_revoke(p_owner uuid, p_resource text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('jumpserve-mcp:' || p_owner::text, 0));
  delete from public.jumpserve_mcp_codes where owner_id = p_owner and resource = p_resource;
  delete from public.jumpserve_mcp_tokens where owner_id = p_owner and resource = p_resource;
end
$$;

create table public.research_skill_submissions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  bundle_sha256 text not null check (bundle_sha256 ~ '^[a-f0-9]{64}$'),
  bundle jsonb not null check (
    jsonb_typeof(bundle) = 'object' and bundle->>'version' = 'jumpserve-assessment-v1'
    and octet_length(bundle::text) <= 700000
  ),
  expires_at timestamptz not null default clock_timestamp() + interval '30 minutes',
  approved_at timestamptz,
  study_id uuid unique references public.research_studies(id),
  unique (owner_id, bundle_sha256),
  check (study_id is null or (study_id = id and approved_at is not null))
);

create table public.research_skill_runs (
  study_id uuid not null references public.research_studies(id),
  run_ref text not null,
  configuration text not null,
  started_at timestamptz not null,
  artifact_sha256 text not null check (artifact_sha256 ~ '^[a-f0-9]{64}$'),
  primary key (study_id, run_ref)
);
create table public.research_skill_measurements (
  study_id uuid not null,
  run_ref text not null,
  ordinal integer not null check (ordinal > 0),
  claim_ref text not null,
  metric text not null,
  units text not null,
  paper_value numeric,
  observed_value numeric not null,
  primary key (study_id, run_ref, ordinal),
  foreign key (study_id, run_ref) references public.research_skill_runs(study_id, run_ref)
);
create index research_skill_preview_expiry on public.research_skill_submissions(expires_at) where study_id is null;

create function public.research_skill_preview(p_owner uuid, p_hash text, p_bundle jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare preview public.research_skill_submissions;
begin
  perform pg_advisory_xact_lock(hashtextextended('research-skill:' || p_owner::text, 0));
  delete from public.research_skill_submissions
    where owner_id = p_owner and study_id is null and expires_at <= clock_timestamp();
  select * into preview from public.research_skill_submissions
    where owner_id = p_owner and bundle_sha256 = p_hash;
  if preview.id is null then
    if (select count(*) from public.research_skill_submissions where owner_id = p_owner and study_id is null) >= 8 then
      raise exception 'Too many pending previews' using errcode = '54000';
    end if;
    insert into public.research_skill_submissions(owner_id, bundle_sha256, bundle)
      values (p_owner, p_hash, p_bundle) returning * into preview;
  end if;
  if preview.study_id is not null and public.research_assessment_deleted(preview.study_id) then
    raise exception 'Assessment has been deleted' using errcode = 'P0002';
  end if;
  return jsonb_build_object('preview_id', preview.id, 'study_id', preview.study_id);
end
$$;

create function public.research_skill_submit(p_owner uuid, p_preview uuid)
returns uuid language plpgsql security definer set search_path = '' as $$
declare
  preview public.research_skill_submissions;
  paper jsonb;
  evidence_run jsonb;
begin
  -- Use the same lock order as the existing assessment-deletion flow.
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1', 0));
  select * into preview from public.research_skill_submissions
    where id = p_preview and owner_id = p_owner for update;
  if not found then raise exception 'Preview not found' using errcode = 'P0002'; end if;
  if preview.study_id is not null then
    if public.research_assessment_deleted(preview.study_id) then
      raise exception 'Assessment has been deleted' using errcode = 'P0002';
    end if;
    return preview.study_id;
  end if;
  if preview.expires_at <= clock_timestamp() or preview.approved_at is null then
    raise exception 'Preview requires current owner approval' using errcode = '55000';
  end if;

  paper := preview.bundle->'paper';
  insert into public.research_studies(id, study_kind, title, domain, scope, paper_url, paper_upload)
    values (preview.id, 'paper', paper->>'title', paper->>'domain', preview.bundle->>'summary', paper->>'url',
      case when not (paper ? 'url') then
        jsonb_build_object('sha256', paper->>'sha256', 'byte_count', paper->'byte_count', 'filename', 'source.pdf')
      end);
  insert into public.research_study_owners(study_id, owner_id) values (preview.id, p_owner);
  for evidence_run in select value from jsonb_array_elements(preview.bundle->'runs') loop
    insert into public.research_skill_runs(study_id, run_ref, configuration, started_at, artifact_sha256)
      values (preview.id, evidence_run->>'id', evidence_run->>'configuration',
        (evidence_run->>'started_at')::timestamptz, evidence_run->>'artifact_sha256');
    insert into public.research_skill_measurements
      (study_id, run_ref, ordinal, claim_ref, metric, units, paper_value, observed_value)
    select preview.id, evidence_run->>'id', position, value->>'claim_id', value->>'metric',
      value->>'units', (value->>'paper_value')::numeric, (value->>'observed_value')::numeric
    from jsonb_array_elements(evidence_run->'measurements') with ordinality m(value, position);
  end loop;
  insert into public.research_audit_events(study_id, actor_id, action, details)
    values (preview.id, p_owner, 'share-local-assessment', jsonb_build_object('sha256', preview.bundle_sha256));
  update public.research_skill_submissions set study_id = id where id = preview.id;
  return preview.id;
end
$$;

-- The only anonymous read returns the exact approved bundle for an active
-- public assessment. Owner IDs, pending previews and tokens stay private.
create function public.research_skill_shared(p_study uuid)
returns jsonb language sql stable security definer set search_path = '' as $$
  select s.bundle from public.research_skill_submissions s
  join public.research_studies a on a.id = s.study_id
  where s.study_id = p_study and a.deleted_at is null
$$;

alter table public.jumpserve_mcp_codes enable row level security;
alter table public.jumpserve_mcp_tokens enable row level security;
alter table public.research_skill_submissions enable row level security;
alter table public.research_skill_runs enable row level security;
alter table public.research_skill_measurements enable row level security;
revoke all on public.jumpserve_mcp_codes, public.jumpserve_mcp_tokens,
  public.research_skill_submissions, public.research_skill_runs, public.research_skill_measurements
  from public, anon, authenticated;
grant select, insert, delete on public.jumpserve_mcp_codes to service_role;
grant select, update (approved_at) on public.research_skill_submissions to service_role;
grant select on public.research_skill_runs, public.research_skill_measurements to service_role;
revoke all on function public.jumpserve_mcp_exchange(text,text,text,text,text,text,text,text),
  public.jumpserve_mcp_actor(text,text),
  public.jumpserve_mcp_revoke(uuid,text),
  public.research_skill_preview(uuid,text,jsonb), public.research_skill_submit(uuid,uuid),
  public.research_skill_shared(uuid) from public, anon, authenticated;
grant execute on function public.jumpserve_mcp_exchange(text,text,text,text,text,text,text,text),
  public.jumpserve_mcp_actor(text,text),
  public.jumpserve_mcp_revoke(uuid,text),
  public.research_skill_preview(uuid,text,jsonb), public.research_skill_submit(uuid,uuid) to service_role;
grant execute on function public.research_skill_shared(uuid) to anon, authenticated, service_role;

notify pgrst, 'reload schema';
commit;
