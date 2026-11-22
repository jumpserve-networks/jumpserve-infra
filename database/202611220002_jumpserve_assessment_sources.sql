begin;

create table public.research_skill_sources (
  id uuid primary key,
  owner_id uuid not null,
  sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
  byte_count integer not null check (byte_count between 1 and 10000000)
);
alter table public.research_skill_sources enable row level security;
revoke all on public.research_skill_sources from public, anon, authenticated;
grant select, insert on public.research_skill_sources to service_role;

alter table public.research_skill_submissions
  add column source_id uuid references public.research_skill_sources(id),
  add constraint research_skill_submission_source_id check (source_id is null or source_id = id),
  drop constraint research_skill_submissions_owner_id_bundle_sha256_key;
create unique index research_skill_legacy_bundle on public.research_skill_submissions(owner_id, bundle_sha256)
  where source_id is null;

create function public.research_skill_preview_for_source(p_owner uuid, p_hash text, p_bundle jsonb, p_assessment_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare preview public.research_skill_submissions;
begin
  perform pg_advisory_xact_lock(hashtextextended('research-skill:' || p_owner::text, 0));
  if p_assessment_id is not null and not exists (
    select 1 from public.research_skill_sources
    where id = p_assessment_id and owner_id = p_owner
      and sha256 = p_bundle #>> '{paper,sha256}'
      and to_jsonb(byte_count) = p_bundle #> '{paper,byte_count}'
      and p_bundle #> '{paper,pdf_copy}' = 'true'::jsonb
  ) then
    raise exception 'Assessment source does not match' using errcode = '22023';
  end if;
  delete from public.research_skill_submissions
    where owner_id = p_owner and study_id is null and expires_at <= clock_timestamp();
  select * into preview from public.research_skill_submissions
    where owner_id = p_owner and (
      (p_assessment_id is not null and source_id = p_assessment_id) or
      (p_assessment_id is null and source_id is null and bundle_sha256 = p_hash)
    );
  if preview.id is null then
    if (select count(*) from public.research_skill_submissions where owner_id = p_owner and study_id is null) >= 8 then
      raise exception 'Too many pending previews' using errcode = '54000';
    end if;
    if p_assessment_id is not null and exists (select 1 from public.research_studies where id = p_assessment_id) then
      raise exception 'Assessment ID already in use' using errcode = '23505';
    end if;
    insert into public.research_skill_submissions(id, owner_id, bundle_sha256, bundle, source_id)
      values (coalesce(p_assessment_id, gen_random_uuid()), p_owner, p_hash, p_bundle, p_assessment_id) returning * into preview;
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

create or replace function public.research_skill_preview(p_owner uuid, p_hash text, p_bundle jsonb)
returns jsonb language sql security definer set search_path = '' as $$
  select public.research_skill_preview_for_source(p_owner, p_hash, p_bundle, null::uuid)
$$;

revoke all on function public.research_skill_preview_for_source(uuid,text,jsonb,uuid) from public, anon, authenticated;
grant execute on function public.research_skill_preview_for_source(uuid,text,jsonb,uuid) to service_role;

notify pgrst, 'reload schema';
commit;
