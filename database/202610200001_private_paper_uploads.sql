begin;

-- Uploaded papers retain their actual identity; no synthetic public URL.
alter table public.research_studies add column paper_upload jsonb;
alter table public.research_studies drop constraint research_studies_check;
alter table public.research_studies add constraint research_studies_paper_input_check check (
 (study_kind='idea' and paper_url is null and paper_upload is null) or
 (study_kind='paper' and (
  (paper_url is not null and paper_url ~ '^https://[^[:space:]]+$' and paper_upload is null) or
  (paper_url is null and paper_upload is not null and jsonb_typeof(paper_upload)='object'
   and paper_upload->>'sha256' ~ '^[a-f0-9]{64}$' and (paper_upload->>'byte_count')::bigint between 1 and 10000000
   and length(paper_upload->>'filename') between 1 and 200)
 ))
);

create table public.research_paper_uploads (
 id uuid primary key, owner_id uuid not null, paper jsonb not null,
 status text not null default 'pending' check(status in ('pending','verified','started','rejected')),
 reason text, original_artifact_id uuid,
 created_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null default clock_timestamp()+interval '2 hours',
 check(jsonb_typeof(paper)='object' and paper->>'study_kind'='paper' and paper->>'paper_url' is null and paper->'paper_upload' is not null)
);
create index research_pending_paper_uploads on public.research_paper_uploads(owner_id,expires_at) where status='pending';
create function public.research_protect_paper_upload() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or old.status in ('started','rejected') or
  (to_jsonb(new)-array['status','reason','original_artifact_id']) is distinct from (to_jsonb(old)-array['status','reason','original_artifact_id']) or
  not ((old.status='pending' and new.status in ('verified','rejected')) or (old.status='verified' and new.status='started')) then
  raise exception 'Original upload identity and terminal outcomes are immutable';
 end if;
 return new;
end $$;
create trigger research_paper_upload_immutable before update or delete on public.research_paper_uploads for each row execute function public.research_protect_paper_upload();
alter table public.research_paper_uploads enable row level security;
revoke all on public.research_paper_uploads from public,anon,authenticated;
grant all on public.research_paper_uploads to service_role;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('research-paper-uploads','research-paper-uploads',false,10000000,array['application/pdf']);
create policy research_paper_uploads_private on storage.objects as restrictive for all to anon,authenticated
 using(bucket_id<>'research-paper-uploads') with check(bucket_id<>'research-paper-uploads');

create or replace function public.research_create_study(p_actor uuid,p_id uuid,p_document jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare existing public.research_studies; kind text=coalesce(p_document->>'study_kind','paper'); expected jsonb; upload jsonb=p_document->'paper_upload'; begin
 perform pg_advisory_xact_lock(hashtextextended(p_id::text,0));
 if p_actor is null or p_id is null or kind not in ('paper','idea') or
  (kind='idea' and (p_document->>'paper_url' is not null or upload is not null and upload<>'null'::jsonb)) or
  (kind='paper' and (upload is null or upload='null'::jsonb) and coalesce(p_document->>'paper_url','') !~ '^https://[^[:space:]]+$') then raise exception 'Invalid paper or unpublished-idea origin'; end if;
 if upload is not null and upload<>'null'::jsonb and not exists(
  select 1 from public.research_paper_uploads u where u.id=p_id and u.owner_id=p_actor
   and u.status in ('verified','started') and u.paper=p_document
 ) then raise exception 'Uploaded paper requires verified original bytes before study creation'; end if;
 expected=p_document||jsonb_build_object('study_kind',kind,'paper_upload',coalesce(upload,'null'::jsonb));
 select * into existing from public.research_studies where id=p_id;
 if found then
  if not exists(select 1 from public.research_study_owners where study_id=p_id and owner_id=p_actor) then raise exception 'Study not found'; end if;
  if (to_jsonb(existing)-'created_at'-'id') is distinct from expected then raise exception 'Request ID already used for different study details'; end if;
  return to_jsonb(existing);
 end if;
 insert into public.research_studies(id,title,paper_url,paper_upload,domain,scope,origin_module,study_kind)
 values(p_id,p_document->>'title',p_document->>'paper_url',nullif(upload,'null'::jsonb),p_document->>'domain',p_document->>'scope',p_document->>'origin_module',kind) returning * into existing;
 insert into public.research_study_owners values(p_id,p_actor);
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_id,p_actor,'intake',jsonb_build_object('request_id',p_id,'study_kind',kind,'input_origin',case when upload is null or upload='null'::jsonb then 'url-or-idea' else 'owner-upload' end));
 return to_jsonb(existing);
end $$;

create function public.research_paper_upload(p_operation text,p_actor uuid,p_id uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare u public.research_paper_uploads; meta jsonb; artifact jsonb; result jsonb; begin
 -- Same lock order as autonomous start. Storage I/O occurs outside this gate.
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or p_id is null then raise exception 'Authenticated upload identity required'; end if;
 select * into u from public.research_paper_uploads where id=p_id for update;
 if found and u.owner_id<>p_actor then raise exception 'Private paper upload not found'; end if;
 if p_operation='reserve' then
  meta=p_payload->'paper_upload';
  if p_payload->>'study_kind' is distinct from 'paper' or p_payload->>'paper_url' is not null or
   jsonb_typeof(meta) is distinct from 'object' or coalesce(meta->>'sha256','') !~ '^[a-f0-9]{64}$' or
   jsonb_typeof(meta->'byte_count') is distinct from 'number' or (meta->>'byte_count')::bigint not between 1 and 10000000 or
   coalesce(meta->>'filename','') !~* '^[^/\\[:cntrl:]]{0,196}\.pdf$' or
   length(btrim(coalesce(p_payload->>'title',''))) not between 1 and 300 or
   length(btrim(coalesce(p_payload->>'domain',''))) not between 1 and 5000 or
   length(btrim(coalesce(p_payload->>'scope',''))) not between 1 and 5000 then raise exception 'Invalid bounded PDF upload metadata'; end if;
  if u.id is not null then
   if u.paper is distinct from p_payload then raise exception 'Request ID already identifies different file or assessment details'; end if;
   if u.status='pending' and u.expires_at<=clock_timestamp() then raise exception 'Upload reservation expired; preserve it and start a new submission'; end if;
   return to_jsonb(u);
  end if;
  if exists(select 1 from public.research_studies where id=p_id) then raise exception 'Request ID already identifies a study'; end if;
  if (select count(*) from public.research_paper_uploads where owner_id=p_actor and status='pending' and expires_at>clock_timestamp())>=10 then raise exception 'Ten pending uploads already exist; finish an existing upload first'; end if;
  insert into public.research_paper_uploads(id,owner_id,paper) values(p_id,p_actor,p_payload) returning * into u;
  return to_jsonb(u);
 end if;
 if p_operation='copy' then
  if not exists(select 1 from public.research_studies s join public.research_study_owners o on o.study_id=s.id
   where s.id=(p_payload->>'source_study_id')::uuid and o.owner_id=p_actor and s.id<>p_id
    and s.paper_upload=p_payload->'paper'->'paper_upload' and s.paper_upload is not null) then raise exception 'Only the source PDF owner may copy it to a private workspace'; end if;
  if u.id is null then
   insert into public.research_paper_uploads(id,owner_id,paper) values(p_id,p_actor,p_payload->'paper') returning * into u;
  elsif u.paper is distinct from p_payload->'paper' then raise exception 'Workspace already identifies another paper'; end if;
 end if;
 if u.id is null then raise exception 'Private paper upload not found'; end if;
 if p_operation='reject' then
  if u.status<>'pending' or length(coalesce(p_payload->>'reason','')) not between 1 and 1000 then raise exception 'Only a pending upload can record a verification rejection'; end if;
  update public.research_paper_uploads set status='rejected',reason=p_payload->>'reason' where id=p_id returning * into u;
  return to_jsonb(u);
 end if;
 if p_operation not in ('start','copy') then raise exception 'Unknown paper upload operation'; end if;
 if u.status='started' then
  if p_payload->'paper' is distinct from u.paper then raise exception 'Original paper identity changed'; end if;
  if p_operation='copy' then return public.research_create_study(p_actor,p_id,u.paper); end if;
  return public.research_autonomy_control('start',p_actor,p_id,p_payload-'artifact');
 end if;
 if u.status<>'pending' or u.expires_at<=clock_timestamp() then raise exception 'Only a current pending upload can start'; end if;
 meta=u.paper->'paper_upload';artifact=p_payload->'artifact';
 if p_payload->'paper' is distinct from u.paper or artifact->>'sha256' is distinct from meta->>'sha256' or
  artifact->>'byte_count' is distinct from meta->>'byte_count' or artifact->>'media_type' is distinct from 'application/pdf' or
  artifact->>'storage_path' is distinct from p_id::text||'/'||(meta->>'sha256') or
  artifact->'provenance'->>'kind' is distinct from 'paper-original-upload' then raise exception 'Verified artifact does not match the reserved paper'; end if;
 update public.research_paper_uploads set status='verified' where id=p_id;
 if p_operation='copy' then result=public.research_create_study(p_actor,p_id,u.paper);
 else result=public.research_autonomy_control('start',p_actor,p_id,p_payload-'artifact'); end if;
 perform public.research_append(p_id,p_actor,'artifacts',artifact);
 update public.research_paper_uploads set status='started',original_artifact_id=(artifact->>'id')::uuid where id=p_id;
 return result;
end $$;

revoke all on function public.research_paper_upload(text,uuid,uuid,jsonb),public.research_create_study(uuid,uuid,jsonb),public.research_protect_paper_upload() from public,anon,authenticated;
grant execute on function public.research_paper_upload(text,uuid,uuid,jsonb),public.research_create_study(uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
