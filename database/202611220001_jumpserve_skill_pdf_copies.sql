begin;

alter table public.research_skill_submissions
  add column pdf_verified_at timestamptz,
  add constraint research_skill_pdf_approval check (
    case when bundle #>> '{paper,pdf_copy}' = 'true'
      then approved_at is null or pdf_verified_at is not null
      else pdf_verified_at is null
    end
  );
grant update (pdf_verified_at) on public.research_skill_submissions to service_role;

-- Signed uploads last two hours. Retain a margin before removing abandoned files
-- through the Storage API. Approved assessment files use their existing visibility.
create function public.research_skill_expired_pdfs()
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
      and (s.study_id is not null or s.expires_at > now())
    )
  order by o.created_at, o.name
  limit 20
$$;
revoke all on function public.research_skill_expired_pdfs() from public, anon, authenticated;
grant execute on function public.research_skill_expired_pdfs() to service_role;

notify pgrst, 'reload schema';
commit;
