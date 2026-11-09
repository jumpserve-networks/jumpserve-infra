"""Profile isolated database-unit checks without touching any existing PostgreSQL server.

The report is deliberately partial: retained PL/pgSQL functions are measured;
DDL, anonymous migration blocks, SQL-language bodies and older replaced versions
remain unmeasured. Passing database checks cannot satisfy the repository's 100%
coverage gate until that inventory is measured too.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse

from setup_sql_coverage import REVISION, TOOLS

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ['database/202610300004_platform_supervisor.sql', 'database/202610300005_platform_worker.sql', 'database/202610300006_platform_host_coordination.sql']
PORT = 54479
LIMITATIONS = ['Only the platform database-unit fixture is currently profiled.', 'DDL, anonymous migration blocks and SQL-language functions are not measured.', 'Earlier function bodies replaced by later migrations are not measured.', 'A real local PostgreSQL engine and synthetic authentication/Storage fixtures are used; no production or scientific validation is claimed.']


def literal(value): return "'" + str(value).replace("'", "''") + "'"


def verified_tool():
    receipt = json.loads((TOOLS / 'sql-profiler.json').read_bytes())
    if receipt['revision'] != REVISION: raise RuntimeError('Run the pinned SQL profiler setup first.')
    library = Path(receipt['library']).resolve()
    bindir = Path(receipt['bindir']).resolve()
    if not bindir.is_relative_to(TOOLS.resolve()) or not bindir.is_dir(): raise RuntimeError('A staged local PostgreSQL installation is required.')
    if not library.is_relative_to(TOOLS.resolve()) or hashlib.sha256(library.read_bytes()).hexdigest() != receipt['sha256']:
        raise RuntimeError('SQL profiler bytes differ from the local build receipt.')
    return receipt


def query(psql, url, sql):
    target = urllib.parse.urlsplit(url)
    if target.scheme != 'postgresql' or target.hostname != '127.0.0.1' or target.port != PORT or target.username != 'unit_coverage' or target.password or target.query or target.fragment:
        raise ValueError('SQL coverage accepts only its dedicated local test cluster.')
    if target.path != '/postgres' and not target.path.startswith('/jumpserve_platform_test_'):
        raise ValueError('SQL coverage accepts only the isolated fixture database.')
    result = subprocess.run([str(psql), url, '-X', '-qAt', '-v', 'ON_ERROR_STOP=1'], input=sql, capture_output=True, text=True, timeout=30)
    if result.returncode: raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    tool = verified_tool()
    bindir = Path(tool['bindir'])
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / '.test-artifacts/sql-coverage' / stamp; out.mkdir(parents=True)
    data = out / 'data'
    report = dict(passed=False, target_met=False, coverage_kind='retained-plpgsql-functions', applied_migrations={name:hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in MIGRATIONS}, limitations=LIMITATIONS, tool=tool, functions=[])
    started = False
    try:
        subprocess.run([str(bindir / 'initdb'), '-D', str(data), '-U', 'unit_coverage', '-A', 'trust', '--no-locale', '-E', 'UTF8'], check=True, capture_output=True, text=True)
        # A dedicated port and brand-new cluster prevent accidental use of the
        # developer's retained databases. No existing service is reconfigured.
        port = PORT
        options = ['-h', '127.0.0.1', '-p', str(port), '-k', '', '-c', 'shared_preload_libraries=plpgsql,' + tool['library'], '-c', 'plpgsql_check.profiler=on', '-c', 'max_connections=20']
        import shlex
        subprocess.run([str(bindir / 'pg_ctl'), '-D', str(data), '-l', str(out / 'postgres.log'), '-w', '-t', '15', '-o', shlex.join(options), 'start'], check=True, capture_output=True, text=True)
        started = True
        origin = f'postgresql://unit_coverage@127.0.0.1:{port}/postgres'
        env = dict(os.environ, PLATFORM_TEST_DATABASE_URL=origin)
        checks = subprocess.run([sys.executable, str(ROOT / 'test/check_platform_database.py')], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        (out / 'database-checks.log').write_text(checks.stdout + checks.stderr)
        psql = bindir / 'psql'
        names = json.loads(query(psql, origin, "select coalesce(json_agg(datname),'[]') from pg_database where datname like 'jumpserve_platform_test_%';"))
        if len(names) != 1: raise RuntimeError('Expected exactly one isolated platform fixture database.')
        url = origin.removesuffix('postgres') + names[0]
        query(psql, url, 'create extension plpgsql_check;')
        functions = json.loads(query(psql, url, "select coalesce(jsonb_agg(jsonb_build_object('signature',p.oid::regprocedure::text,'body',p.prosrc) order by p.oid::regprocedure::text),'[]') from pg_proc p join pg_namespace n on n.oid=p.pronamespace join pg_language l on l.oid=p.prolang where n.nspname='public' and l.lanname='plpgsql';"))
        for function in functions:
            report['reading_signature'] = function['signature']
            signature = literal(function['signature']) + '::regprocedure'
            # Each psql call is a fresh backend. Initialize PL/pgSQL's compiler
            # before the profiler compiles a retained, possibly uncalled body.
            metrics = json.loads(query(psql, url, "do $unit_init$ begin null; end $unit_init$; select jsonb_build_object('statement_coverage',public.plpgsql_coverage_statements(" + signature + "),'branch_coverage',public.plpgsql_coverage_branches(" + signature + "),'statements',(select coalesce(jsonb_agg(to_jsonb(s) order by s.stmtid),'[]') from public.plpgsql_profiler_function_statements_tb(" + signature + ') s));'))
            locations = []
            for name in MIGRATIONS:
                raw = (ROOT / name).read_text(); index = raw.find(function['body'])
                if index >= 0: locations.append(dict(file=name, body_start_line=raw.count('\n', 0, index) + 1))
            report['functions'].append(dict(function, **metrics, body_sha256=hashlib.sha256(function['body'].encode()).hexdigest(), source_locations=locations))
        report.pop('reading_signature', None)
        report['passed'] = checks.returncode == 0
        report['fixture_database'] = names[0]
        report['profiled_functions_complete'] = bool(report['functions']) and all(f['statement_coverage'] == 1 and f['branch_coverage'] == 1 for f in report['functions'])
        if not report['passed']: report['reason'] = 'Database-unit checks failed; see the retained original log.'
    except Exception as error:
        report['reason'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            report['command_stdout'] = error.stdout
            report['command_stderr'] = error.stderr
    finally:
        if started or (data / 'postmaster.pid').exists():
            stop = subprocess.run([str(bindir / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', '-t', '15', 'stop'], capture_output=True, text=True)
            if stop.returncode:
                report['fast_shutdown_error'] = stop.stderr
                # A profiler crash can leave crash recovery waiting. This is
                # our newly created, disposable cluster, never an existing DB.
                stop = subprocess.run([str(bindir / 'pg_ctl'), '-D', str(data), '-m', 'immediate', '-w', '-t', '10', 'stop'], capture_output=True, text=True)
            report['cluster_stopped'] = stop.returncode == 0
            if stop.returncode: report['passed'] = False; report['cleanup_error'] = stop.stderr
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        directory = ROOT / 'coverage/sql'; directory.mkdir(parents=True, exist_ok=True)
        (directory / 'partial-report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(passed=report['passed'], target_met=False, functions=len(report['functions']), report=str(out / 'report.json'), reason=report.get('reason'))))
    return 1 if not report['passed'] else 2 if args.check else 0


if __name__ == '__main__': raise SystemExit(main())
