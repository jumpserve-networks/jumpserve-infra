"""Verify atomic, job-scoped ingestion in the dedicated local PostgreSQL DB."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
migration = (ROOT / 'database/202609210001_benchmark_ingestion.sql').read_text()
sql = (ROOT / 'test/benchmark_ingest_database.sql').read_text()
sql += migration.replace('begin;\n', '', 1).rsplit('commit;', 1)[0]
sql += (ROOT / 'test/benchmark_ingest_assertions.sql').read_text()
result = subprocess.run([shutil.which('psql') or '/opt/homebrew/opt/postgresql@17/bin/psql',
    '-X', '-v', 'ON_ERROR_STOP=1', '-q', os.environ.get('PROMPT_TEST_DATABASE_URL', 'postgresql:///jumpserve_prompt_test')],
    input=sql, text=True, capture_output=True)
if result.returncode:
    raise SystemExit(result.stderr)
print('Ingestion isolation, expiry, replay, cancellation, rollback and ID linkage checks passed.')
