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
module_migration = (ROOT / 'database/202609290001_real_world_agent.sql').read_text().replace('begin;\n', '', 1).rsplit('commit;', 1)[0]
module_checks = (ROOT / 'test/real_world_agent_database.sql').read_text()
leo_setup = """
create schema auth;
create function auth.uid() returns uuid language sql as 'select null::uuid';
create function auth.jwt() returns jsonb language sql as 'select ''{}''::jsonb';
grant usage on schema auth to anon,authenticated;
"""
leo_migrations = ''.join((ROOT / 'database' / name).read_text().replace('begin;\n','',1).rsplit('commit;',1)[0]
    for name in ('202610040001_leo_study.sql','202610040002_leo_prompt_publication.sql'))
leo_checks = (ROOT / 'test/leo_study_database.sql').read_text()
http2_migrations = ''.join((ROOT / 'database' / name).read_text().replace('begin;\n','',1).rsplit('commit;',1)[0]
    for name in ('202610040003_http2_study.sql','202610040004_http2_prompt_publication.sql','202610040005_http2_unsigned_error_codes.sql','202610040006_agent_answer_provenance.sql','202610040007_http2_manual_prompt_review.sql','202610040008_agent_model_usage.sql','202610040009_agent_evidence_rendering.sql'))
http2_checks = (ROOT / 'test/http2_study_database.sql').read_text()
storage_setup="""
reset role;
create schema storage;
grant usage on schema storage to anon,authenticated,service_role;
create table storage.buckets(id text primary key,name text,public boolean);
create table storage.objects(id integer primary key,bucket_id text);
alter table storage.objects enable row level security;
grant select,insert,update,delete on storage.objects to anon,authenticated,service_role;
create policy existing_shared_storage_access on storage.objects for all to anon,authenticated using(true) with check(true);
insert into storage.objects values(1,'other-bucket'),(2,'http2-study-artifacts');
"""
storage_migration=(ROOT/'database/202610040010_http2_raw_storage.sql').read_text().replace('begin;\n','',1).rsplit('commit;',1)[0]
storage_checks="""
set local role anon;
do $$ begin
 if (select count(*) from storage.objects)<>1 then raise exception 'Anonymous private bytes exposed'; end if;
 begin insert into storage.objects values(3,'http2-study-artifacts'); raise exception 'Anonymous storage write allowed'; exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
 if (select count(*) from storage.objects)<>1 then raise exception 'Authenticated private bytes exposed'; end if;
 begin update storage.objects set bucket_id='http2-study-artifacts' where id=1; raise exception 'Browser bucket move allowed'; exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role service_role;
do $$ begin
 if (select count(*) from storage.objects)<>2 then raise exception 'Backend byte access denied'; end if;
end $$;
reset role;
do $$ begin
 if (select public from storage.buckets where id='http2-study-artifacts') then raise exception 'Original bucket became public'; end if;
end $$;
"""
subprocess.run([psql, url, '-X', '-v', 'ON_ERROR_STOP=1', '-q'],
               input=setup + migration + checks + module_migration + module_checks + leo_setup + leo_migrations + leo_checks + http2_migrations + http2_checks + storage_setup + storage_migration + storage_checks + '\nrollback;\n', text=True, check=True)
print('Prompt schema tests passed (all test data rolled back)')
