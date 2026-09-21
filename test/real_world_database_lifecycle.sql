-- Isolated fixture tests only: creation, cancellation races, and stale leases.
set local role service_role;
do $$
declare
    id uuid := '55555555-0000-4000-8000-000000000001';
    token uuid; replacement uuid; value jsonb; visible jsonb;
begin
    value := jsonb_build_object('job_id',id,'owner','private-owner','created_at',1,'updated_at',1,'schema_version',1,
        'active','yes','deadline',1,'status','provisioning','config','{}'::jsonb,'nodes','[]'::jsonb);
    visible := value - 'owner' - 'active';
    if not public.real_world_put_job(value,visible,true) then raise exception 'Creation failed'; end if;
    if public.real_world_put_job(value,visible,true) then raise exception 'Duplicate job created'; end if;
    token := public.real_world_claim_job(id);
    if token is null or public.real_world_claim_job(id) is not null then raise exception 'Lease not exclusive'; end if;
    perform public.real_world_cancel_job(id);
    if not public.real_world_put_job(value || '{"status":"running"}',visible || '{"status":"running","cancel_requested":false}',false,token) then
        raise exception 'Valid lease cannot save';
    end if;
    if not (select cancel_requested from public.real_world_jobs where job_id=id)
        or not (select (record->>'cancel_requested')::boolean from public.real_world_runs where job_id=id) then
        raise exception 'Worker overwrote cancellation';
    end if;
    update public.real_world_jobs set lease_until=clock_timestamp()-interval '1 second' where job_id=id;
    if public.real_world_put_job(value,visible,false,token) then raise exception 'Expired lease wrote state'; end if;
    replacement := public.real_world_claim_job(id);
    perform public.real_world_release_job(id,token);
    if (select lease_token from public.real_world_jobs where job_id=id) is distinct from replacement then
        raise exception 'Stale worker released successor lease';
    end if;
    if public.real_world_put_job(value,visible,false,token) then raise exception 'Stale worker wrote state'; end if;
    perform public.real_world_release_job(id,replacement);
end $$;
reset role;
set local role anon;
set local request.jwt.claims='{}';
do $$ begin
    if not exists(select 1 from public.real_world_runs where job_id='55555555-0000-4000-8000-000000000001') then
        raise exception 'Public results hidden by RLS';
    end if;
end $$;
reset role;
-- Even an accidentally broad Storage policy must not expose this bucket.
grant usage on schema storage to anon,authenticated;
grant select,insert on storage.objects to anon,authenticated;
insert into storage.objects values(gen_random_uuid(),'real-world-results');
create policy broad_storage_fixture on storage.objects for all to anon,authenticated using(true) with check(true);
set local role anon;
do $$ begin
    if exists(select 1 from storage.objects where bucket_id='real-world-results') then raise exception 'Raw storage exposed'; end if;
end $$;
select pg_temp.expect_permission_denied('insert into storage.objects values(gen_random_uuid(),''real-world-results'')');
reset role;
