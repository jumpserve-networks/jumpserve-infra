"""Run transactional schema tests against an isolated jumpserve_prompt_test DB."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
psql = shutil.which('psql') or '/opt/homebrew/opt/postgresql@17/bin/psql'
url = os.environ.get('PROMPT_TEST_DATABASE_URL')
if not url:
    raise SystemExit('Set PROMPT_TEST_DATABASE_URL to an isolated jumpserve_prompt_test database')
migration = (ROOT / 'database/202609200001_agent_prompts.sql').read_text()
migration = migration.replace('begin;\n', '', 1).rsplit('commit;', 1)[0]
setup = """
begin;
do $$ begin
    if current_database() <> 'jumpserve_prompt_test' then
        raise exception 'Refusing schema tests outside jumpserve_prompt_test';
    end if;
end $$;
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
grant usage on schema public to service_role, anon, authenticated;
create table public.agent_sessions (
    id uuid primary key, user_id text not null, messages jsonb not null default '[]',
    created_at timestamptz default now(), updated_at timestamptz default now()
);
grant all on public.agent_sessions to service_role;
"""
checks = (ROOT / 'test/agent_prompt_database.sql').read_text()
subprocess.run([psql, url, '-X', '-v', 'ON_ERROR_STOP=1', '-q'],
               input=setup + migration + checks + '\nrollback;\n', text=True, check=True)
print('Prompt schema tests passed (all test data rolled back)')
