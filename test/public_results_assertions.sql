-- Metadata and role checks; no production rows are changed or returned.
do $$
declare relation record; column_record record;
begin
    if not has_schema_privilege('anon','public','usage') then raise exception 'Public schema inaccessible'; end if;
    for relation in select c.oid,c.relname,c.relkind,c.relrowsecurity from pg_class c
        join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p','v','m','f') loop
        if relation.relkind in ('r','p') and not relation.relrowsecurity then
            raise exception 'RLS disabled: %',relation.relname;
        end if;
        if has_table_privilege('anon',relation.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            or has_any_column_privilege('anon',relation.oid,'INSERT,UPDATE,REFERENCES') then
            raise exception 'Anonymous write grant: %',relation.relname;
        end if;
        if relation.relname in ('congestion_control_algorithms','emulated_parent_runs','emulated_runs','emulated_snapshot_stats','real_world_runs','real_world_reports') then
            if not has_table_privilege('anon',relation.oid,'SELECT') then raise exception 'Public results inaccessible: %',relation.relname; end if;
        elsif relation.relname = 'benchmark_jobs' then
            for column_record in select attnum,attname from pg_attribute where attrelid=relation.oid and attnum>0 and not attisdropped loop
                if has_column_privilege('anon',relation.oid,column_record.attnum,'SELECT') is distinct from
                    (column_record.attname = any(array['id','created_at','updated_at','status','config','ec2_instance_id','parent_run_id','error_message'])) then
                    raise exception 'Unexpected benchmark column visibility: %',column_record.attname;
                end if;
            end loop;
        elsif has_table_privilege('anon',relation.oid,'SELECT') or has_any_column_privilege('anon',relation.oid,'SELECT') then
            raise exception 'Private table exposed: %',relation.relname;
        end if;
    end loop;
    if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and has_function_privilege('anon',p.oid,'EXECUTE')) then raise exception 'Public RPC exposed'; end if;
    if exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relkind='S'
        and case when c.relkind='S' then has_sequence_privilege('anon',c.oid,'USAGE,SELECT,UPDATE') else false end) then raise exception 'Public sequence exposed'; end if;
    if not exists(select 1 from pg_event_trigger where evtname='jumpserve_secure_new_tables' and evtenabled='O') then
        raise exception 'New-table guard missing'; end if;
end $$;

create temporary table public_result_visibility (name text, populated boolean);
do $$ declare table_name text; populated boolean; begin
    foreach table_name in array array['congestion_control_algorithms','emulated_parent_runs','emulated_runs','emulated_snapshot_stats','benchmark_jobs'] loop
        execute format('select exists(select id from public.%I limit 1)',table_name) into populated;
        insert into public_result_visibility values(table_name,populated);
    end loop;
end $$;
grant select on public_result_visibility to anon;
set local role anon;
set local request.jwt.claims = '{}';
do $$ declare expected record; populated boolean; begin
    for expected in select * from public_result_visibility loop
        execute format('select exists(select id from public.%I limit 1)',expected.name) into populated;
        if populated is distinct from expected.populated then raise exception 'RLS hid public results: %',expected.name; end if;
    end loop;
end $$;
reset role;

create or replace function pg_temp.expect_permission_denied(statement text) returns void language plpgsql security invoker as $$
begin
    begin execute statement; exception when insufficient_privilege then return; end;
    raise exception 'Expected permission denied: %',statement;
end $$;
grant execute on function pg_temp.expect_permission_denied(text) to anon,authenticated;
set local role anon;
select pg_temp.expect_permission_denied('select requested_by from public.benchmark_jobs limit 0');
select pg_temp.expect_permission_denied('select * from public.agent_sessions limit 0');
select pg_temp.expect_permission_denied('select * from public.benchmark_configs limit 0');
select pg_temp.expect_permission_denied('select * from public.agent_prompt_versions limit 0');
select pg_temp.expect_permission_denied('select * from public.get_active_agent_prompt()');
select pg_temp.expect_permission_denied('insert into public.emulated_runs default values');
select pg_temp.expect_permission_denied('update public.benchmark_jobs set status=''cancelled'' where false');
select pg_temp.expect_permission_denied('delete from public.emulated_runs where false');
reset role;
set local role service_role;
select count(*) >= 0 as backend_prompt_access from public.get_active_agent_prompt();
reset role;
drop table public_result_visibility;
