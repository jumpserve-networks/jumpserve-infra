#!/usr/bin/env python3
"""Apply and verify the fixed JumpServe job-ingestion security migration."""
import argparse
from pathlib import Path
from audit_supabase_security import management

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'database/202609210001_benchmark_ingestion.sql'
CHECKS = """
do $$ begin
    if exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname in ('public','storage') and c.relkind in ('r','p') and not c.relrowsecurity) then
        raise exception 'Unprotected table';
    end if;
    if has_table_privilege('anon','public.benchmark_ingest_tokens','select') or
       has_table_privilege('authenticated','public.benchmark_ingest_tokens','select') or
       has_function_privilege('anon','public.benchmark_ingest(uuid,text,text,jsonb)','execute') or
       has_function_privilege('authenticated','public.benchmark_ingest(uuid,text,text,jsonb)','execute') or
       has_table_privilege('authenticated','public.benchmark_jobs','truncate') or
       not has_function_privilege('service_role','public.benchmark_ingest(uuid,text,text,jsonb)','execute') then
        raise exception 'Incorrect ingestion permissions';
    end if;
end $$;
"""

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    sql = MIGRATION.read_text().rsplit('commit;', 1)[0] if args.apply else 'begin;'
    management('database/query', {'query': sql + CHECKS + ('commit;' if args.apply else 'rollback;'), 'read_only': False})
    print('JumpServe ingestion migration ' + ('applied and verified.' if args.apply else 'verified.'))
