"""Exercise database access control in an isolated PostgreSQL transaction."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
psql = shutil.which('psql') or '/opt/homebrew/opt/postgresql@17/bin/psql'
url = os.environ.get('PROMPT_TEST_DATABASE_URL', 'postgresql:///jumpserve_prompt_test')


def migration_body(name):
    sql = (ROOT / 'database' / name).read_text()
    return sql.replace('begin;\n', '', 1).rsplit('commit;', 1)[0]


setup = """
begin;
set local client_min_messages = warning;
do $$ begin
    if current_database() <> 'jumpserve_prompt_test' then
        raise exception 'Refusing schema tests outside jumpserve_prompt_test';
    end if;
end $$;
do $$ begin create role postgres superuser; exception when duplicate_object then null; end $$;
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
set session authorization postgres;
create schema storage;
create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid primary key,bucket_id text);
alter table storage.objects enable row level security;
create schema auth;
grant usage on schema auth, public to anon, authenticated, service_role;
create function auth.jwt() returns jsonb language sql stable as $$
    select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb;
$$;
create function auth.uid() returns uuid language sql stable as $$
    select (auth.jwt()->>'sub')::uuid;
$$;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
create table public.agent_sessions (
    id uuid primary key, user_id text not null, messages jsonb not null default '[]',
    created_at timestamptz default now(), updated_at timestamptz default now()
);
insert into public.agent_sessions (id,user_id) values
    ('00000000-0000-4000-8000-000000000001','researcher');
alter table public.agent_sessions enable row level security;
create policy sessions_manage on public.agent_sessions for all to authenticated using (true) with check (true);
create table public.benchmark_configs (id int primary key, notes text);
create table public.benchmark_jobs (id int primary key, notes text, created_at timestamptz, updated_at timestamptz, status text, config jsonb, ec2_instance_id text, parent_run_id bigint, error_message text, requested_by text);
insert into public.benchmark_configs values (1,'fixture');
insert into public.benchmark_jobs (id,notes) values (1,'fixture');
alter table public.benchmark_configs enable row level security;
alter table public.benchmark_jobs enable row level security;
create policy config_read on public.benchmark_configs for select to authenticated using (true);
create policy config_insert on public.benchmark_configs for insert to authenticated with check (true);
create policy job_read on public.benchmark_jobs for select to authenticated using (true);
create policy job_insert on public.benchmark_jobs for insert to authenticated with check (true);
do $$ declare table_name text; begin
    foreach table_name in array array[
        'congestion_control_algorithms','emulated_parent_runs','emulated_runs',
        'emulated_snapshot_stats','network_events','per_second_stats','run_stats','runs','services'
    ] loop
        execute format('create table public.%I (id bigserial primary key, notes text)',table_name);
        execute format('insert into public.%I (notes) values (''fixture'')',table_name);
    end loop;
end $$;
-- Check independent column grants and a view that formerly bypassed RLS.
grant select (notes) on public.emulated_runs to anon, public;
create view public.rls_fixture_view as select * from public.emulated_runs;
"""

extra = """
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000099","role":"authenticated","is_anonymous":false}';
insert into public.benchmark_configs values (2,'signed-in config still works');
insert into public.benchmark_jobs (id,notes) values (2,'signed-in job still works');
update public.agent_sessions set messages='[{}]' where user_id='researcher';
do $$ begin
    if (select count(*) from public.rls_fixture_view) <> 1 then raise exception 'View read broken'; end if;
end $$;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000099","role":"authenticated","is_anonymous":true}';
select pg_temp.expect_permission_denied('insert into public.benchmark_configs values (3,''anonymous'')');
do $$ begin
    if exists(select 1 from public.rls_fixture_view) then raise exception 'View bypasses RLS'; end if;
end $$;
reset role;

-- Actual backend inserts still succeed, including identity sequences.
set local role service_role;
insert into public.emulated_runs (notes) values ('backend write');
reset role;

-- Temporarily restore grants and add a public permissive policy: RLS itself
-- must still reject signed-out requests, independently of the grant revocation.
grant usage on schema public to anon;
grant select on public.emulated_runs to anon;
create policy accidentally_public on public.emulated_runs for select to public using (true);
set local role anon;
set local request.jwt.claims = '{}';
do $$ begin
    if exists(select 1 from public.emulated_runs) then raise exception 'RLS leaked rows to anon'; end if;
end $$;
reset role;
revoke usage on schema public from anon;
revoke select on public.emulated_runs from anon;

-- Creation methods, quoted identifiers, and partitions all start protected.
create table public."New Research Table" (id int);
create table public.rls_fixture_ctas as select 1 as id;
select 1 as id into public.rls_fixture_select_into;
create table public.rls_fixture_partitioned (id int) partition by range (id);
create table public.rls_fixture_partition partition of public.rls_fixture_partitioned for values from (0) to (10);
create function public.rls_fixture_rpc() returns int language sql as 'select 1';
create sequence public.rls_fixture_sequence;
do $$ begin
    if exists (select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relkind in ('r','p') and not c.relrowsecurity) then
        raise exception 'New table did not get RLS';
    end if;
    if has_function_privilege('anon','public.rls_fixture_rpc()','execute') then
        raise exception 'New RPC executable anonymously';
    end if;
    if has_sequence_privilege('anon','public.rls_fixture_sequence','USAGE,SELECT,UPDATE') then
        raise exception 'New sequence accessible anonymously';
    end if;
end $$;
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000099","role":"authenticated","is_anonymous":false}';
do $$ begin
    if exists(select 1 from public.rls_fixture_ctas) then raise exception 'New table not default-deny'; end if;
end $$;
reset role;
"""

migration = migration_body('202609200002_authenticated_table_access.sql')
checks = (ROOT / 'test/database_rls_assertions.sql').read_text()
subprocess.run([psql, url, '-X', '-v', 'ON_ERROR_STOP=1', '-q'],
    input=setup + migration_body('202609200001_agent_prompts.sql')
    + migration + migration + checks + extra
    + migration_body('202609200003_public_test_results.sql') * 2
    + (ROOT / 'test/public_results_assertions.sql').read_text()
    + migration_body('202609200004_real_world_supabase.sql') * 2
    + (ROOT / 'test/public_results_assertions.sql').read_text()
    + (ROOT / 'test/real_world_database_assertions.sql').read_text()
    + (ROOT / 'test/real_world_database_lifecycle.sql').read_text() + """
create table public.public_results_future_table (id int);
set local role anon;
select pg_temp.expect_permission_denied('select * from public.public_results_future_table');
reset role;
rollback;
""",
    text=True, check=True)
print('Database RLS tests passed; all fixtures and DDL rolled back.')
