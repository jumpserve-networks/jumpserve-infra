-- Read-only checks: suitable for both production verification and local tests.
-- The caller wraps these in a transaction and rolls it back.
do $$
declare
    relation record;
begin
    if has_schema_privilege('anon', 'public', 'usage') then
        raise exception 'Anonymous role retains public schema access';
    end if;
    for relation in select c.oid, c.relname, c.relkind, c.relrowsecurity
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relkind in ('r','p','v','m','f')
    loop
        if relation.relkind in ('r','p') and not relation.relrowsecurity then
            raise exception 'RLS disabled: %', relation.relname;
        end if;
        if has_table_privilege('anon', relation.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            or has_any_column_privilege('anon', relation.oid, 'SELECT,INSERT,UPDATE,REFERENCES') then
            raise exception 'Anonymous table or column grant remains: %', relation.relname;
        end if;
    end loop;
    if exists (select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and has_function_privilege('anon',p.oid,'EXECUTE')) then
        raise exception 'Anonymous RPC grant remains';
    end if;
    if exists (select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relkind='S'
        and case when c.relkind='S' then has_sequence_privilege('anon',c.oid,'USAGE,SELECT,UPDATE') else false end) then
        raise exception 'Anonymous sequence grant remains';
    end if;
    if not exists (select 1 from pg_event_trigger
        where evtname='jumpserve_secure_new_tables' and evtenabled='O') then
        raise exception 'New-table RLS guard missing';
    end if;
end;
$$;

-- Save only row-existence booleans to confirm RLS does not hide all research
-- data from legitimate users. No live row contents are read or returned.
create temporary table rls_expected_visibility (name text, populated boolean);
do $$
declare
    table_name text;
    populated boolean;
begin
    foreach table_name in array array[
        'congestion_control_algorithms','emulated_parent_runs','emulated_runs',
        'emulated_snapshot_stats','network_events','per_second_stats','run_stats',
        'runs','services','benchmark_configs','benchmark_jobs','agent_sessions'
    ] loop
        execute format('select exists (select 1 from public.%I limit 1)',table_name) into populated;
        insert into rls_expected_visibility values (table_name,populated);
    end loop;
end;
$$;
grant select on rls_expected_visibility to authenticated;

create function pg_temp.assert_visibility(expected_visible boolean) returns void
language plpgsql security invoker as $$
declare
    expected record;
    populated boolean;
begin
    for expected in select * from rls_expected_visibility loop
        execute format('select exists (select 1 from public.%I limit 1)',expected.name) into populated;
        if populated is distinct from (expected_visible and expected.populated) then
            raise exception 'Unexpected visibility as % on %',current_user,expected.name;
        end if;
    end loop;
end;
$$;

create function pg_temp.expect_permission_denied(statement text) returns void
language plpgsql security invoker as $$
begin
    begin
        execute statement;
    exception when insufficient_privilege then return;
    end;
    raise exception 'Expected permission denied: %',statement;
end;
$$;

grant execute on function pg_temp.assert_visibility(boolean) to authenticated;
grant execute on function pg_temp.expect_permission_denied(text) to anon, authenticated;

set local role anon;
select pg_temp.expect_permission_denied('select 1 from public.emulated_runs limit 1');
select pg_temp.expect_permission_denied('select * from public.get_active_agent_prompt()');
reset role;

set local role authenticated;
set local request.jwt.claims = '{}';
select pg_temp.assert_visibility(false);
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000099","role":"authenticated","is_anonymous":true}';
select pg_temp.assert_visibility(false);
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000099","role":"authenticated","is_anonymous":false}';
select pg_temp.assert_visibility(true);
select pg_temp.expect_permission_denied('select 1 from public.agent_prompt_versions limit 1');
select pg_temp.expect_permission_denied('select 1 from public.agent_answers limit 1');
select pg_temp.expect_permission_denied('insert into public.emulated_runs default values');
select pg_temp.expect_permission_denied('select * from public.get_active_agent_prompt()');
reset role;

set local role service_role;
-- Trusted backend access still works without an end-user session.
set local request.jwt.claims = '{}';
select count(*) >= 0 as backend_prompt_access from public.get_active_agent_prompt();
select count(*) >= 0 as backend_settings_access from public.agent_prompt_settings;
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'congestion_control_algorithms','emulated_parent_runs','emulated_runs',
        'emulated_snapshot_stats','network_events','per_second_stats','run_stats',
        'runs','services','benchmark_configs','benchmark_jobs','agent_sessions'
    ] loop
        execute format('select 1 from public.%I limit 1',table_name);
        if not has_table_privilege(current_user,format('public.%I',table_name),'INSERT')
            or not has_table_privilege(current_user,format('public.%I',table_name),'UPDATE') then
            raise exception 'Backend write privilege missing: %',table_name;
        end if;
    end loop;
end;
$$;
reset role;
