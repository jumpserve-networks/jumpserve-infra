-- Deny signed-out access to every application table. Supabase-owned auth,
-- storage, realtime, and extension schemas retain their managed permissions.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- A schema grant alone must not expose a new table, view, sequence, or RPC.
revoke all on schema public from public, anon;
grant usage on schema public to authenticated, service_role;
revoke all on all tables in schema public from public, anon;
revoke all on all sequences in schema public from public, anon;
revoke all on all functions in schema public from public, anon;

do $$
declare
    relation record;
    columns text;
begin
    for relation in
        select c.relname, c.relkind from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f')
    loop
        -- Table-level REVOKE does not remove independent column grants.
        select string_agg(quote_ident(a.attname), ', ') into columns
        from pg_attribute a
        where a.attrelid = format('public.%I', relation.relname)::regclass
          and a.attnum > 0 and not a.attisdropped and a.attacl is not null;
        if columns is not null then
            execute format('revoke select (%1$s), insert (%1$s), update (%1$s), references (%1$s)
                on public.%2$I from public, anon', columns, relation.relname);
        end if;
        if relation.relkind in ('r', 'p') then
            execute format('alter table public.%I enable row level security', relation.relname);
            execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I', relation.relname);
            -- RESTRICTIVE combines with, rather than replaces, existing policies.
            -- Anonymous Supabase Auth sessions use the authenticated role too.
            execute format('create policy jumpserve_require_signed_in_user on public.%I
                as restrictive for all to anon, authenticated
                using ((select auth.uid()) is not null
                    and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')
                with check ((select auth.uid()) is not null
                    and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')', relation.relname);
        elsif relation.relkind = 'v' then
            execute format('alter view public.%I set (security_invoker = true)', relation.relname);
        end if;
    end loop;
end;
$$;

-- Measurements are shared among signed-in researchers; only trusted backend
-- jobs write them. Keep existing config/session/job policies and prompt ACLs.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'congestion_control_algorithms', 'emulated_parent_runs', 'emulated_runs',
        'emulated_snapshot_stats', 'network_events', 'per_second_stats',
        'run_stats', 'runs', 'services'
    ] loop
        execute format('revoke all on public.%I from authenticated', table_name);
        execute format('grant select on public.%I to authenticated', table_name);
        execute format('drop policy if exists authenticated_read_measurements on public.%I', table_name);
        execute format('create policy authenticated_read_measurements on public.%I
            for select to authenticated using (true)', table_name);
    end loop;
end;
$$;

-- PostgreSQL's default PUBLIC EXECUTE grant is global, so revoke it globally
-- for objects created by the migration role as well as schema-specific grants.
alter default privileges for role postgres in schema public revoke all on tables from public, anon;
alter default privileges for role postgres in schema public revoke all on sequences from public, anon;
alter default privileges for role postgres revoke execute on functions from public;
alter default privileges for role postgres in schema public revoke all on functions from public, anon;

-- New application tables start closed even when created outside migrations.
-- No permissive policy is added: each new table needs an explicit access design.
create or replace function public.jumpserve_secure_new_tables() returns event_trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare
    command record;
begin
    for command in select * from pg_event_trigger_ddl_commands()
        where schema_name = 'public' and object_type in ('table', 'partitioned table')
    loop
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
drop event trigger if exists jumpserve_secure_new_tables;
create event trigger jumpserve_secure_new_tables on ddl_command_end
    when tag in ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
    execute function public.jumpserve_secure_new_tables();

notify pgrst, 'reload schema';
commit;
