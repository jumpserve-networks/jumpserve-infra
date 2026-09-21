-- Authoritative real-world records and analysis; raw evidence uses Supabase Storage.
begin;
set local statement_timeout = '60s';

create or replace function public.jumpserve_secure_new_tables() returns event_trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare
    command record;
begin
    for command in select * from pg_event_trigger_ddl_commands()
        where schema_name = 'public' and object_type in ('table', 'partitioned table')
    loop
        -- FK creation can report an already secured referenced table.
        if exists(select 1 from pg_policy where polrelid=command.objid
            and polname='jumpserve_require_signed_in_user') then continue; end if;
        execute format('alter table %s enable row level security', command.object_identity);
        execute format('revoke all on %s from public, anon', command.object_identity);
        execute format('create policy jumpserve_require_signed_in_user on %s
            as restrictive for all to anon, authenticated
            using ((select auth.uid()) is not null
                and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')
            with check ((select auth.uid()) is not null
                and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')', command.object_identity);
    end loop;
end;
$$;
revoke all on function public.jumpserve_secure_new_tables() from public, anon, authenticated;


create table if not exists public.real_world_jobs (
    job_id uuid primary key,
    record jsonb not null check (jsonb_typeof(record) = 'object' and record->>'job_id' = job_id::text),
    owner text generated always as (record->>'owner') stored not null,
    created_at bigint generated always as ((record->>'created_at')::bigint) stored not null,
    schema_version integer generated always as ((record->>'schema_version')::integer) stored not null,
    active text generated always as (record->>'active') stored not null,
    deadline bigint generated always as ((record->>'deadline')::bigint) stored not null,
    cancel_requested boolean not null default false,
    lease_token uuid,
    lease_until timestamptz
);
create index if not exists real_world_jobs_owner_created on public.real_world_jobs(owner,created_at desc,job_id desc);
create index if not exists real_world_jobs_active_deadline on public.real_world_jobs(deadline,job_id) where active='yes';

create table if not exists public.real_world_runs (
    job_id uuid primary key references public.real_world_jobs(job_id),
    record jsonb not null check (jsonb_typeof(record) = 'object' and record->>'job_id' = job_id::text
        and not (record ?| array['owner','lease_token','lease_until','_lease_token','upload_url'])),
    created_at bigint generated always as ((record->>'created_at')::bigint) stored not null,
    schema_version integer generated always as ((record->>'schema_version')::integer) stored not null,
    status text generated always as (record->>'status') stored not null,
    config jsonb generated always as (record->'config') stored not null
);
create index if not exists real_world_runs_created on public.real_world_runs(schema_version,created_at desc,job_id desc);

create table if not exists public.real_world_artifacts (
    job_id uuid not null references public.real_world_jobs(job_id),
    node_name text not null check (node_name ~ '^(server|bottleneck|receiver-[1-9][0-9]?)$'),
    object_path text not null unique,
    sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
    bytes bigint not null check (bytes>=0),
    legacy_version_id text,
    primary key(job_id,node_name),
    check (object_path = job_id::text || '/archive/' || node_name || '/' || sha256 || '.json')
);

create table if not exists public.real_world_reports (
    job_id uuid primary key references public.real_world_jobs(job_id),
    report jsonb not null check (jsonb_typeof(report) = 'object' and report->'job'->>'job_id' = job_id::text),
    analysis_version text generated always as (report->>'analysis_version') stored not null,
    comparison_key text generated always as (report->'comparison'->>'key') stored,
    summary jsonb generated always as (report->'summary') stored not null,
    receivers jsonb generated always as (report->'receivers') stored not null,
    updated_at timestamptz not null default now()
);
create index if not exists real_world_reports_comparison on public.real_world_reports(comparison_key) where comparison_key is not null;

-- All writes and orchestration RPCs are backend-only. Public result tables never
-- contain requester identities, signed URLs, network keys, or SSM commands.
do $$ declare relation text; begin
    foreach relation in array array['real_world_jobs','real_world_runs','real_world_artifacts','real_world_reports'] loop
        execute format('alter table public.%I enable row level security',relation);
        execute format('revoke all on public.%I from public,anon,authenticated',relation);
        execute format('grant all on public.%I to service_role',relation);
        if relation in ('real_world_runs','real_world_reports') then
            execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I',relation);
            execute format('create policy jumpserve_require_signed_in_user on public.%I as restrictive for all to authenticated
                using (auth.uid() is not null and auth.jwt()->>''is_anonymous'' is distinct from ''true'')
                with check (auth.uid() is not null and auth.jwt()->>''is_anonymous'' is distinct from ''true'')',relation);
            execute format('drop policy if exists jumpserve_public_results on public.%I',relation);
            execute format('create policy jumpserve_public_results on public.%I for select to anon,authenticated using (true)',relation);
            execute format('grant select on public.%I to anon,authenticated',relation);
        end if;
    end loop;
end $$;

create or replace function public.real_world_put_job(payload jsonb, visible jsonb, create_only boolean, token uuid default null)
returns boolean language plpgsql security invoker set search_path='' as $$
declare target uuid := (payload->>'job_id')::uuid; cancelled boolean; changed integer;
begin
    if visible->>'job_id' is distinct from payload->>'job_id' then raise exception 'Job identity mismatch'; end if;
    if create_only then
        insert into public.real_world_jobs(job_id,record,cancel_requested)
            values(target,payload - 'cancel_requested' - 'lease_until' - '_lease_token',coalesce((payload->>'cancel_requested')::boolean,false))
            on conflict do nothing;
        get diagnostics changed=row_count;
        if changed=0 then return false; end if;
    else
        update public.real_world_jobs set record=payload - 'cancel_requested' - 'lease_until' - '_lease_token'
            where job_id=target and lease_token=token and lease_until>clock_timestamp();
        get diagnostics changed=row_count;
        if changed=0 then return false; end if;
    end if;
    select cancel_requested into cancelled from public.real_world_jobs where job_id=target;
    insert into public.real_world_runs(job_id,record)
        values(target,visible || jsonb_build_object('cancel_requested',cancelled))
        on conflict(job_id) do update set record=excluded.record;
    return true;
end $$;

create or replace function public.real_world_claim_job(target uuid)
returns uuid language plpgsql security invoker set search_path='' as $$
declare token uuid;
begin
    update public.real_world_jobs set lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '5 minutes'
        where job_id=target and (lease_until is null or lease_until<clock_timestamp()) returning lease_token into token;
    return token;
end $$;

create or replace function public.real_world_release_job(target uuid, token uuid)
returns void language sql security invoker set search_path='' as $$
    update public.real_world_jobs set lease_token=null,lease_until=null where job_id=target and lease_token=token;
$$;

create or replace function public.real_world_cancel_job(target uuid)
returns void language plpgsql security invoker set search_path='' as $$
begin
    update public.real_world_jobs set cancel_requested=true where job_id=target and active='yes';
    if found then
        update public.real_world_runs set record=record || '{"cancel_requested":true}'::jsonb where job_id=target;
    end if;
end $$;

create or replace function public.real_world_reap_candidates(after_id uuid default null)
returns table(job_id uuid) language sql security invoker set search_path='' as $$
    select j.job_id from public.real_world_jobs j
    where (after_id is null or j.job_id>after_id) and (
        (j.active='yes' and j.deadline<=extract(epoch from clock_timestamp())::bigint)
        or (j.active='no' and not exists(select 1 from public.real_world_reports r where r.job_id=j.job_id
            and r.report->'job'->>'updated_at' is not distinct from j.record->>'updated_at')))
    order by j.job_id limit 50;
$$;

revoke all on function public.real_world_put_job(jsonb,jsonb,boolean,uuid),public.real_world_claim_job(uuid),
    public.real_world_release_job(uuid,uuid),public.real_world_cancel_job(uuid),public.real_world_reap_candidates(uuid) from public,anon,authenticated;
grant execute on function public.real_world_put_job(jsonb,jsonb,boolean,uuid),public.real_world_claim_job(uuid),
    public.real_world_release_job(uuid,uuid),public.real_world_cancel_job(uuid),public.real_world_reap_candidates(uuid) to service_role;

-- Private bucket. The API signs only expected per-machine measurement objects.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('real-world-results','real-world-results',false,33554432,array['application/json'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists jumpserve_real_world_private on storage.objects;
create policy jumpserve_real_world_private on storage.objects as restrictive for all to anon,authenticated
    using(bucket_id <> 'real-world-results') with check(bucket_id <> 'real-world-results');
notify pgrst,'reload schema';
commit;
