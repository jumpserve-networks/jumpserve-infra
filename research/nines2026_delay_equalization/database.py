#!/usr/bin/env python3
"""Apply/test only the dedicated research schema in the verified JumpServe project."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
INFRA = HERE.parents[1]
sys.path.insert(0, str(INFRA/'scripts'))
from audit_supabase_security import PROJECT, query

SCHEMA = INFRA/'database'/'202609270001_delay_study.sql'
ASSERTIONS = """
do $checks$
declare r record; count_tables integer := 0;
begin
  for r in select c.oid, c.relname, c.relrowsecurity from pg_class c
           join pg_namespace n on n.oid=c.relnamespace
           where n.nspname='public' and c.relkind='r' and c.relname like 'delay_study_%'
  loop
    count_tables := count_tables+1;
    assert r.relrowsecurity, 'RLS must be enabled';
    assert has_table_privilege('anon', r.oid, 'SELECT'), 'Public measurements must be readable';
    assert has_table_privilege('authenticated', r.oid, 'SELECT'), 'Researchers must be able to read';
    assert not has_table_privilege('anon', r.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'), 'Anonymous mutation forbidden';
    assert not has_table_privilege('authenticated', r.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'), 'Browser mutation forbidden';
    assert has_table_privilege('service_role', r.oid, 'INSERT'), 'Controller requires inserts';
  end loop;
  assert count_tables=12, 'Expected exactly twelve research relations';
  assert exists(select 1 from pg_constraint where contype='f'
    and conrelid='public.delay_study_config_flows'::regclass
    and confrelid='public.delay_study_configurations'::regclass), 'Configured flows require a parent configuration';
  assert exists(select 1 from pg_constraint where contype='f'
    and conrelid='public.delay_study_trials'::regclass
    and confrelid='public.delay_study_configurations'::regclass
    and array_length(conkey,1)=2), 'Trial campaign and configuration must match';
end
$checks$;
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['test-schema', 'apply-schema', 'verify', 'apply-public-reads'])
    args = parser.parse_args()
    if PROJECT != 'regphejnlvfpyokpniny':
        raise RuntimeError('Refusing a different Supabase project')
    if args.action == 'apply-public-reads':
        migration = INFRA/'database'/'202609270002_delay_study_public_reads.sql'
        query(migration.read_text().rsplit('commit;', 1)[0]+ASSERTIONS+'''
            set local role anon;
            do $reads$ begin
              assert exists(select 1 from public.delay_study_campaigns
                where id='nines2026-balanced-v1'), 'Public campaign must be visible';
              assert (select count(*) from public.delay_study_trials
                where campaign_id='nines2026-balanced-v1')=820, 'Public schedule must be complete';
            end $reads$;
            commit;
        ''')
    elif args.action == 'verify':
        query(ASSERTIONS)
    else:
        existing = query("select tablename from pg_tables where schemaname='public' and tablename like 'delay_study_%'")
        if existing:
            raise RuntimeError('Research tables already exist; verify or write a separate migration')
        sql = SCHEMA.read_text()
        ending = 'rollback;' if args.action == 'test-schema' else 'commit;'
        query(sql.rsplit('commit;', 1)[0]+ASSERTIONS+'\n'+ending)
    print(json.dumps({'project': PROJECT, 'action': args.action, 'status': 'passed'}))


if __name__ == '__main__':
    main()
