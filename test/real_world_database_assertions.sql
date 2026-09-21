-- Read-only checks suitable for a production migration transaction.
do $$ declare relation text; routine regprocedure; begin
    foreach relation in array array['real_world_jobs','real_world_runs','real_world_artifacts','real_world_reports'] loop
        if not (select relrowsecurity from pg_class where oid=('public.'||relation)::regclass) then
            raise exception 'RLS missing on %',relation;
        end if;
        if has_table_privilege('authenticated','public.'||relation,'INSERT,UPDATE,DELETE,TRUNCATE') then
            raise exception 'Client write access on %',relation;
        end if;
        if has_table_privilege('authenticated','public.'||relation,'SELECT') is distinct from (relation in ('real_world_runs','real_world_reports')) then
            raise exception 'Unexpected client read access on %',relation;
        end if;
    end loop;
    for routine in select oid::regprocedure from pg_proc where proname like 'real_world_%' and pronamespace='public'::regnamespace loop
        if has_function_privilege('anon',routine,'EXECUTE') or has_function_privilege('authenticated',routine,'EXECUTE')
            or not has_function_privilege('service_role',routine,'EXECUTE') then
            raise exception 'Unexpected RPC privileges: %',routine;
        end if;
    end loop;
    if not exists(select 1 from storage.buckets where id='real-world-results' and public=false and file_size_limit=33554432) then
        raise exception 'Private measurement bucket not configured';
    end if;
    if not exists(select 1 from pg_policies where schemaname='storage' and tablename='objects'
        and policyname='jumpserve_real_world_private' and permissive='RESTRICTIVE') then
        raise exception 'Measurement storage policy missing';
    end if;
end $$;
set local role anon;
select * from public.real_world_runs limit 0;
select * from public.real_world_reports limit 0;
select pg_temp.expect_permission_denied('select * from public.real_world_jobs');
select pg_temp.expect_permission_denied('select * from public.real_world_artifacts');
select pg_temp.expect_permission_denied('select public.real_world_claim_job(gen_random_uuid())');
select pg_temp.expect_permission_denied('insert into public.real_world_runs default values');
reset role;
