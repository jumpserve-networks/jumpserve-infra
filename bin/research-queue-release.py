"""Fixed-target queue release and read-only verification; no experiments or prompt writes.

Uses the existing project guard and scoped benchmark CDK entry point. Credentials
are passed only in the child environment. Failed receipts and original deployed
Lambda ZIPs remain in the ignored release evidence directory.
"""
import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'jumpserve-back-end'
spec = importlib.util.spec_from_file_location('queue_project_guard', ROOT / 'bin/research-ideas-release.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
STACK = 'JumpServeBenchmarkStack'
BASE = 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research'
PRIVATE = {'research_autonomy_repairs', 'research_autonomy_repair_events', 'research_study_owners', 'research_artifacts', 'research_audit_events', 'research_paper_uploads',
           'research_queue_jobs', 'research_queue_events', 'research_prepared_plans',
           'research_idea_packets', 'research_idea_sessions', 'research_idea_runs',
           'research_idea_readiness', 'research_idea_campaign_links',
           'research_network_executions'}


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def aws(*args):
    return json.loads(subprocess.check_output(
        ['aws', *args, '--profile', 'jumpserve', '--region', 'us-east-1', '--output', 'json'], timeout=60))


def source():
    manifest = json.loads((ROOT / 'research-workflow-runtime.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((BACKEND / 'research_workflow' / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Declared backend bytes differ: ' + name)
    return manifest


def state():
    stack = aws('cloudformation', 'describe-stacks', '--stack-name', STACK)['Stacks'][0]
    if ':395567831870:' not in stack['StackId']:
        raise RuntimeError('Wrong stack account')
    return dict(stack_id=stack['StackId'], status=stack['StackStatus'], parameters=stack.get('Parameters', []))


def security():
    rows = guard.admin.query("""select c.relname,c.relrowsecurity,
        has_table_privilege('anon',c.oid,'SELECT') anon_read,
        has_table_privilege('authenticated',c.oid,'SELECT') browser_read,
        has_table_privilege('anon',c.oid,'INSERT,UPDATE,DELETE') anon_write,
        has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE') browser_write
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relname like 'research_%' and c.relkind='r' order by c.relname""")
    if not PRIVATE.issubset({row['relname'] for row in rows}):
        raise RuntimeError('Required private research relations are missing')
    for row in rows:
        readable = row['relname'] not in PRIVATE
        if not row['relrowsecurity'] or row['anon_write'] or row['browser_write'] or row['anon_read'] != readable or row['browser_read'] != readable:
            raise RuntimeError('Research relation security differs: ' + row['relname'])
    functions = guard.admin.query("""select p.proname,
        has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,
        has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute
        from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.proname in
        ('research_queue_enqueue','research_queue_claim','research_queue_finish',
         'research_queue_action','research_queue_snapshot','research_prepare_plan') order by p.proname""")
    if len(functions) != 6 or any(row['anon_execute'] or row['browser_execute'] for row in functions):
        raise RuntimeError('Queue/preparation RPC security differs')
    if guard.admin.query("select public from storage.buckets where id='research-workflow-raw'") != [{'public': False}]:
        raise RuntimeError('Original artifacts bucket must be private')
    return dict(relations=rows, functions=functions, private_bucket=True,
                original_migration_bytes_verified=False,
                limitation='Read-only catalog verification does not recover originally executed SQL.')


def archives(directory, manifest=None):
    resources = aws('cloudformation', 'list-stack-resources', '--stack-name', STACK)['StackResourceSummaries']
    # The existing package handlers share the same declared runtime asset.
    selected = [r for r in resources if r['ResourceType'] == 'AWS::Lambda::Function'
                and any(r['LogicalResourceId'].startswith(prefix) for prefix in
                        ('ResearchWorkflowApi', 'ResearchWorkflowQueueWorker', 'ResearchWorkflowPackageExecutor',
                         'ResearchWorkflowPackageReaper', 'ResearchWorkflowPackageIngest'))]
    if len(selected) != 5:
        raise RuntimeError('Expected the research API, queue worker and three existing package handlers')
    functions = []
    notified = None
    for item in selected:
        value = aws('lambda', 'get-function', '--function-name', item['PhysicalResourceId'])
        config = value['Configuration']
        if ':395567831870:' not in config['FunctionArn'] or config['Environment']['Variables']['SUPABASE_URL'] != 'https://regphejnlvfpyokpniny.supabase.co':
            raise RuntimeError('Lambda target mismatch')
        with guard.OPEN.open(value['Code']['Location'], timeout=30) as response:
            raw = response.read(8_000_001)
        if len(raw) > 8_000_000 or base64.b64encode(hashlib.sha256(raw).digest()).decode() != config['CodeSha256']:
            raise RuntimeError('Deployed archive size/hash mismatch')
        (directory / (config['FunctionName'] + '.zip')).write_bytes(raw)
        if manifest:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name, expected_sha in manifest['files'].items():
                    if hashlib.sha256(archive.read(name)).hexdigest() != expected_sha:
                        raise RuntimeError('Deployed original source mismatch: ' + name)
        functions.append(dict(name=config['FunctionName'], handler=config['Handler'], arn=config['FunctionArn'],
            sha256=hashlib.sha256(raw).hexdigest(), source_files=len(manifest['files']) if manifest else None,
            memory_mb=config['MemorySize'], timeout_seconds=config['Timeout'], last_modified=config['LastModified']))
        if config['Handler'] == 'api.handler':
            notified = config['Environment']['Variables'].get('RESEARCH_QUEUE_WORKER_FUNCTION')
    return functions, notified


def verify(directory, manifest):
    functions, notified = archives(directory, manifest)
    worker = next(f for f in functions if f['handler'] == 'worker.handler')
    if notified != worker['arn']:
        raise RuntimeError('API worker notification target differs')
    event_config = aws('lambda', 'get-function-event-invoke-config', '--function-name', worker['name'])
    if event_config['MaximumRetryAttempts'] != 0:
        raise RuntimeError('Unexpected asynchronous experiment retries')
    with guard.OPEN.open(BASE + '/capabilities', timeout=20) as response:
        cap = json.load(response)
    if cap['queue']['overview_version'] != 'research-queue-overview-v1' or cap['preparation']['gap_queue_version'] != 'research-gap-queue-v1' or cap['queue']['workers_enabled'] is not True:
        raise RuntimeError('Released queue capabilities differ')
    denials = []
    for suffix, method, forged in [('/queue', 'GET', False), ('/queue', 'GET', True),
        ('/studies/00000000-0000-4000-8000-000000000001/gap-experiments', 'GET', False),
        ('/studies/00000000-0000-4000-8000-000000000001/gap-experiments', 'POST', False)]:
        headers = {'Origin': 'https://jumpserve.quaint-lab.org', 'Content-Type': 'application/json'}
        if forged:
            headers['Authorization'] = 'Bearer invalid-release-verification-token'
        request = urllib.request.Request(BASE + suffix, data=b'{}' if method == 'POST' else None, method=method, headers=headers)
        try:
            with guard.OPEN.open(request, timeout=20) as response:
                status, cors = response.status, response.headers.get('Access-Control-Allow-Origin')
        except urllib.error.HTTPError as error:
            status, cors = error.code, error.headers.get('Access-Control-Allow-Origin')
        if status not in (401, 403) or cors != '*':
            raise RuntimeError('Private endpoint denial/CORS differs: ' + suffix + ' ' + str(status))
        denials.append(dict(path=suffix, method=method, forged_bearer=forged, status=status, cors=cors))
    return dict(functions=functions, capabilities=cap, anonymous_denials=denials,
        asynchronous_retries=event_config['MaximumRetryAttempts'], database_security=security(),
        notification_execution='Configuration verified; no synthetic authenticated request or new scientific job was submitted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inspect', 'diff', 'deploy', 'verify'])
    mode = parser.parse_args().mode
    directory = ROOT / '.test-artifacts/research-queue-release' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, exist_ok=False)
    report = dict(mode=mode, started_at=stamp(), status='running', measured_charges_usd=None,
        authorization='User requested all outstanding changes committed/pushed to main and production deployment on 2026-10-17.',
        new_model_calls=0, new_experiment_instances=0,
        reviewer=dict(identity='Primary Codex implementer', type='AI', independent=False))
    try:
        report['targets'] = guard.target()
        report['manifest'] = manifest = source()
        report['before'] = before = state()
        if mode == 'inspect':
            report['database_security'] = security()
            report['rollback_originals'], _ = archives(directory)
        elif mode == 'verify':
            report['verification'] = verify(directory, manifest)
        else:
            if mode == 'deploy':
                revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip()
                if manifest['source_revision'] != revision:
                    raise RuntimeError('Release must pin the exact committed backend revision')
                if subprocess.check_output(['git', 'status', '--porcelain'], cwd=BACKEND, text=True).strip():
                    raise RuntimeError('Backend must have no uncommitted changes before deployment')
                security()
            credentials = aws('configure', 'export-credentials', '--format', 'process')
            env = dict(os.environ, AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],
                AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'], AWS_SESSION_TOKEN=credentials['SessionToken'],
                AWS_DEFAULT_REGION='us-east-1')
            env.pop('AWS_PROFILE', None)
            command = ['npm', 'run', 'cdk:benchmark', '--', mode, STACK]
            command += ['--no-change-set'] if mode == 'diff' else ['--require-approval', 'never', '--outputs-file', str(directory / 'outputs.json')]
            report['command'] = command
            with (directory / 'cdk.log').open('w') as log:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            if result.returncode:
                raise RuntimeError('CDK failed; inspect retained cdk.log')
            if mode == 'deploy':
                report['after'] = state()
                parameters = lambda value: {p['ParameterKey']: p['ParameterValue'] for p in value['parameters']}
                if parameters(report['after']) != parameters(before):
                    raise RuntimeError('Existing benchmark stack parameters changed; inspect before frontend release')
        report['status'] = 'complete'
    except Exception as error:
        report.update(status='failed', reason=str(error))
        raise
    finally:
        report['ended_at'] = stamp()
        (directory / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(directory=str(directory), status=report['status'], reason=report.get('reason'))))


if __name__ == '__main__':
    main()
