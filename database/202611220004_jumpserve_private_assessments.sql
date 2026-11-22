begin;

alter table public.research_skill_submissions
  add column completed_at timestamptz,
  add constraint research_skill_completed_pdf check (
    completed_at is null or (bundle #>> '{paper,pdf_copy}') is distinct from 'true' or pdf_verified_at is not null
  );

-- Preserve completed previews that are still stored. An old PDF whose copy
-- was swept can be staged again using the original assessment ID and bytes.
update public.research_skill_submissions s
set completed_at = coalesce(s.pdf_verified_at, s.expires_at - interval '30 minutes')
where s.study_id is null and (
  (s.bundle #>> '{paper,pdf_copy}') is distinct from 'true'
  or (s.pdf_verified_at is not null and exists (
    select 1 from storage.objects o
    where o.bucket_id = 'research-paper-uploads' and o.name = 'jumpserve-mcp/' || s.id::text || '.pdf'
  ))
);

create index research_skill_private_catalog
  on public.research_skill_submissions(owner_id, completed_at desc, id desc)
  where study_id is null and completed_at is not null;

-- Track completion even when the original connector performs PDF verification.
create function public.research_skill_complete_preview()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.completed_at is null then
    if new.pdf_verified_at is not null then
      new.completed_at := new.pdf_verified_at;
    elsif (new.bundle #>> '{paper,pdf_copy}') is distinct from 'true' then
      new.completed_at := clock_timestamp();
    end if;
  end if;
  return new;
end
$$;

revoke all on function public.research_skill_complete_preview() from public, anon, authenticated;
create trigger research_skill_complete_preview
  before insert or update of pdf_verified_at on public.research_skill_submissions
  for each row execute function public.research_skill_complete_preview();

create or replace function public.research_skill_preview_for_source(p_owner uuid, p_hash text, p_bundle jsonb, p_assessment_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare preview public.research_skill_submissions;
begin
  perform pg_advisory_xact_lock(hashtextextended('research-skill:' || p_owner::text, 0));
  if p_assessment_id is null or not exists (
    select 1 from public.research_skill_sources
    where id = p_assessment_id and owner_id = p_owner
      and sha256 = p_bundle #>> '{paper,sha256}'
      and to_jsonb(byte_count) = p_bundle #> '{paper,byte_count}'
      and p_bundle #> '{paper,pdf_copy}' = 'true'::jsonb
  ) then
    raise exception 'Assessment source does not match' using errcode = '22023';
  end if;
  delete from public.research_skill_submissions
    where owner_id = p_owner and study_id is null and completed_at is null
      and pdf_verified_at is null and expires_at <= clock_timestamp();
  select * into preview from public.research_skill_submissions
    where owner_id = p_owner and source_id = p_assessment_id;
  if preview.id is null then
    if exists (select 1 from public.research_studies where id = p_assessment_id) then
      raise exception 'Assessment ID already in use' using errcode = '23505';
    end if;
    insert into public.research_skill_submissions(id, owner_id, bundle_sha256, bundle, source_id)
      values (p_assessment_id, p_owner, p_hash, p_bundle, p_assessment_id) returning * into preview;
  end if;
  if preview.study_id is not null and public.research_assessment_deleted(preview.study_id) then
    raise exception 'Assessment has been deleted' using errcode = 'P0002';
  end if;
  if preview.bundle_sha256 <> p_hash then
    raise exception 'Assessment already has a different preview' using errcode = '23505';
  end if;
  return jsonb_build_object('preview_id', preview.id, 'study_id', preview.study_id);
end
$$;

-- Older connectors can finish Step 1-backed writes during a rolling release.
-- Current connectors verify and attach the file before saving so the result
-- becomes a completed private assessment in one transaction.
create function public.research_skill_save_from_source(p_owner uuid, p_hash text, p_bundle jsonb, p_assessment_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare saved jsonb;
begin
  if p_assessment_id is null or not exists (
    select 1 from storage.objects
    where bucket_id = 'research-paper-uploads' and name = 'jumpserve-mcp/' || p_assessment_id::text || '.pdf'
  ) then
    raise exception 'The verified Step 1 attachment is unavailable' using errcode = '22023';
  end if;

  saved := public.research_skill_preview_for_source(p_owner, p_hash, p_bundle, p_assessment_id);
  update public.research_skill_submissions set pdf_verified_at = coalesce(pdf_verified_at, clock_timestamp())
    where id = p_assessment_id and source_id = p_assessment_id and owner_id = p_owner
      and study_id is null and completed_at is null;
  return saved;
end
$$;

revoke all on function public.research_skill_save_from_source(uuid,text,jsonb,uuid) from public, anon, authenticated;
grant execute on function public.research_skill_save_from_source(uuid,text,jsonb,uuid) to service_role;

-- The expiry timestamp applies only to legacy unfinished writes. An owner
-- can approve a completed private assessment for public sharing at any time.
create or replace function public.research_skill_submit(p_owner uuid, p_preview uuid)
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
  if preview.completed_at is null or preview.approved_at is null then
    raise exception 'Assessment requires completion and owner approval' using errcode = '55000';
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

create or replace function public.research_skill_expired_pdfs()
returns setof text language sql stable security definer set search_path = '' as $$
  select o.name
  from storage.objects o
  where o.bucket_id = 'research-paper-uploads'
    and o.name ~ '^jumpserve-mcp/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]pdf$'
    and o.created_at <= now() - interval '3 hours'
    and not exists (
      select 1 from public.research_skill_submissions s
      where s.id = case when o.name ~ '^jumpserve-mcp/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]pdf$'
        then substr(o.name, 15, 36)::uuid end
      and (s.study_id is not null or s.completed_at is not null or s.expires_at > now())
    )
  order by o.created_at, o.name
  limit 20
$$;
notify pgrst, 'reload schema';
commit;
