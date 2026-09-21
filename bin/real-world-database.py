#!/usr/bin/env python3
"""Apply or verify the fixed real-world Supabase schema without touching test rows."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rls_audit', ROOT / 'bin/supabase-rls.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    checks = (ROOT / 'test/public_results_assertions.sql').read_text() + (ROOT / 'test/real_world_database_assertions.sql').read_text()
    if args.apply:
        sql = (ROOT / 'database/202609200004_real_world_supabase.sql').read_text().rsplit('commit;', 1)[0] + checks + '\ncommit;'
    else:
        sql = 'begin;\n' + checks + '\nrollback;'
    audit.query(sql, read_only=False)
    print(json.dumps({'project': audit.PROJECT_REF, 'real_world_schema': 'verified', 'applied': args.apply}))
