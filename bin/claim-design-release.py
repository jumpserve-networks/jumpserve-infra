"""Fixed-target claim designer release; no model calls or scientific jobs.

Keeps failed receipts and original deployed archives, and uses the existing
Supabase administration and scoped CDK entry points without printing credentials.
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
MODULE = 'research-claim-design'
CANDIDATE = '3da220d0-cde0-5ab5-b8cd-ccbd23ece025'
API = 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research'
AGENT = 'https://idk3jouyc6g2uolmge5ctuizwq0kpgcf.lambda-url.us-east-1.on.aws/'
REPORT = ROOT / 'docs/claim-design-followup-validation/v6-replay-exact-final/evaluation-reviewed.json'
MIGRATIONS = (
    '202610170001_claim_experiment_design.sql', '202610170002_claim_design_prompt.sql',
    '202610170003_claim_design_prompt_v2.sql', '202610170004_claim_design_prompt_v3.sql',
    '202610170005_claim_design_prompt_v4.sql', '202610170006_claim_design_policy_guard.sql',
    '202610170007_claim_design_prompt_v5.sql', '202610170008_claim_design_v5_publication_guard.sql',
    '202610170009_claim_design_prompt_v6.sql', '202610170010_claim_design_v6_publication_guard.sql',
    '202610170011_claim_design_replay_publication_guard.sql',
    '202610170012_claim_design_quote_publication_guard.sql',
    '202610170013_claim_design_exact_units_publication_guard.sql',
)


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'bin' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


queue = load_module('claim_release_queue', 'research-queue-release.py')
guard = queue.guard
admin = guard.admin


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def aws(*args):
    return queue.aws(*args)


def pointers():
    return admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id')


def active():
    return admin.query("select s.active_version_id,v.version,v.content_sha256,v.published_at "
                       "from agent_prompt_settings s left join agent_prompt_versions v on v.id=s.active_version_id "
                       "where s.module_id='research-claim-design'")


def evaluated():
    report = json.loads(REPORT.read_text())
    if (report['prompt_version_id'] != CANDIDATE or report['reviewer']['passed'] is not True
            or report['evaluation_kind'] != 'archived-model-output-replay'
            or report['new_provider_calls'] != 0 or len(report['cases']) != 20
            or not all(c['passed'] and c['status'] == 'complete' and c['raw_answer_reviewed']
                       and c['rendered_answer_reviewed'] for c in report['cases'])):
        raise RuntimeError('Exact reviewed replay is not eligible')
    for name in ('agent/claim_experiment_design.py', 'agent/research_ideas.py'):
        if sha((ROOT / name).read_bytes()) != report['input_sha256'][name]:
            raise RuntimeError('Evaluated agent source changed: ' + name)
    seed = json.loads((ROOT / 'database/seed-claim-experiment-design-v6.json').read_text())
    if sha((seed['system_prompt'] + '\n\n' + seed['research_context']).encode()) != report['prompt_content_sha256']:
        raise RuntimeError('Evaluated prompt content changed')
    # These manifests preserve earlier failures, not just the final passing report.
    verified = []
    for folder in ('claim-design-validation', 'claim-design-correction-validation', 'claim-design-followup-validation'):
        base = ROOT / 'docs' / folder
        manifest = json.loads((base / 'artifact-manifest.json').read_text())
        files = manifest['files']
        entries = files.items() if isinstance(files, dict) else ((v['path'], v) for v in files)
        count = 0
        for name, item in entries:
            raw = (base / name).read_bytes()
            if sha(raw) != item['sha256'] or len(raw) != item.get('byte_count', item.get('bytes')):
                raise RuntimeError('Archived evidence differs: ' + folder + '/' + name)
            count += 1
        verified.append(dict(folder=folder, files=count, manifest_sha256=sha((base / 'artifact-manifest.json').read_bytes())))
    return report, verified


def security():
    # Existing queue security plus the new private immutable claim context.
    original = queue.PRIVATE
    try:
        queue.PRIVATE = original | {'research_claim_designs'}
        result = queue.security()
    finally:
        queue.PRIVATE = original
    functions = admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,"
                            "has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute "
                            "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                            "where n.nspname='public' and proname in ('research_initialize_claim_design','publish_agent_prompt')")
    if len(functions) != 2 or any(r['anon_execute'] or r['browser_execute'] for r in functions):
        raise RuntimeError('Claim design/publication browser RPC permissions differ')
    definition = admin.query("select pg_get_functiondef('public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text)'::regprocedure) definition")[0]['definition']
    if 'publish_agent_prompt_before_claim_v6_exact' not in definition:
        raise RuntimeError('Final exact-unit publication guard is missing')
    result['claim_functions'] = functions
    result['final_publication_guard_sha256'] = sha(definition.encode())
    return result


def agent_archive(directory, expected=False):
    resource = aws('cloudformation', 'describe-stack-resource', '--stack-name', 'JumpServeAgentStack',
                   '--logical-resource-id', 'AgentFnC1FD126F')['StackResourceDetail']
    value = aws('lambda', 'get-function', '--function-name', resource['PhysicalResourceId'])
    config = value['Configuration']
    if (':395567831870:' not in config['FunctionArn']
            or config['Environment']['Variables']['SUPABASE_URL'] != 'https://regphejnlvfpyokpniny.supabase.co'):
        raise RuntimeError('Agent target differs')
    with guard.OPEN.open(value['Code']['Location'], timeout=45) as response:
        raw = response.read(90_000_001)
    if len(raw) > 90_000_000 or base64.b64encode(hashlib.sha256(raw).digest()).decode() != config['CodeSha256']:
        raise RuntimeError('Agent ZIP size/hash differs')
    (directory / 'agent-original.zip').write_bytes(raw)
    names = ('handler.py', 'modules.py', 'research_ideas.py', 'claim_experiment_design.py', 'claim-decision-policy-v1.json')
    hashes = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in names:
            if name not in archive.namelist():
                if expected:
                    raise RuntimeError('Deployed agent file absent: ' + name)
                continue
            hashes[name] = sha(archive.read(name))
            if expected and hashes[name] != sha((ROOT / 'agent' / name).read_bytes()):
                raise RuntimeError('Deployed agent source differs: ' + name)
    return dict(function=config['FunctionName'], runtime=config['Runtime'], memory_mb=config['MemorySize'],
                timeout_seconds=config['Timeout'], zip_sha256=sha(raw), bytes=len(raw), source_hashes=hashes,
                layers=config.get('Layers', []), last_modified=config['LastModified'])


def archive_evidence(directory):
    entries = []
    for folder in ('claim-design-validation', 'claim-design-correction-validation', 'claim-design-followup-validation'):
        entries.extend(p for p in sorted((ROOT / 'docs' / folder).rglob('*')) if p.is_file())
    entries += sorted((ROOT / 'docs').glob('claim-experiment-design*.md'))
    entries += [ROOT / 'docs/claim-design-release-protocol-v1.md']
    manifest = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in entries:
            raw = path.read_bytes()
            name = str(path.relative_to(ROOT))
            manifest.append(dict(path=name, sha256=sha(raw), bytes=len(raw)))
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, raw)
        archive.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
    raw = buffer.getvalue()
    if len(raw) > 32_000_000:
        raise RuntimeError('Declared storage budget exceeded')
    (directory / 'evaluation-originals.zip').write_bytes(raw)
    key = aws('secretsmanager', 'get-secret-value', '--secret-id', 'jumpserve/supabase-service-key')['SecretString']
    path = 'release-verification/claim-design-20261018/' + sha(raw) + '.zip'
    url = 'https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/' + path
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    try:
        request = urllib.request.Request(url, data=raw, method='POST', headers={**headers, 'Content-Type': 'application/zip', 'x-upsert': 'false'})
        with guard.OPEN.open(request, timeout=60) as response:
            response.read(1000)
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise RuntimeError('Private evidence upload failed: HTTP ' + str(error.code)) from None
    with guard.OPEN.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
        restored = response.read(32_000_001)
    if restored != raw or sha(restored) != sha(raw):
        raise RuntimeError('Retrieved original archive hash differs')
    public = json.loads((ROOT / 'cdk.json').read_text())['context']['supabaseAnonKey']
    status = 200
    try:
        with guard.OPEN.open(urllib.request.Request(url, headers={'apikey': public}), timeout=20) as response:
            response.read(1)
    except urllib.error.HTTPError as error:
        status = error.code
    if status not in (400, 401, 403, 404):
        raise RuntimeError('Private evidence anonymous access is not denied')
    return dict(bucket='research-workflow-raw', path=path, sha256=sha(raw), bytes=len(raw), files=len(manifest),
                retrieved_hash_verified=True, anonymous_status=status, measured_storage_charges_usd=None)


def deny(endpoint, payload=None):
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={'Content-Type': 'application/json', 'Origin': 'https://jumpserve.quaint-lab.org'})
    status = 200
    try:
        with guard.OPEN.open(request, timeout=25) as response:
            response.read(1000)
    except urllib.error.HTTPError as error:
        status = error.code
    if status not in (401, 403):
        raise RuntimeError('Private/model anonymous request not denied: ' + str(status))
    return dict(endpoint=endpoint, method=request.method, status=status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect', 'migrate', 'diff-api', 'deploy-api', 'diff-agent', 'deploy-agent', 'publish', 'verify', 'frontend-release', 'frontend-status'))
    args = parser.parse_args()
    directory = ROOT / '.test-artifacts/claim-design/release' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(protocol='claim-design-production-release-v1', mode=args.mode, status='running', started_at=stamp(),
                   authorization='User explicitly requested merging all current changes to main and production deployment.',
                   new_model_calls=0, new_experiment_instances=0, measured_charges_usd=None)
    def save():
        (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    save()
    try:
        receipt['targets'] = guard.target()
        report, receipt['evidence_integrity'] = evaluated()
        receipt['evaluated_report_sha256'] = sha(REPORT.read_bytes())
        receipt['runtime_manifest'] = manifest = queue.source()
        save()
        if args.mode == 'inspect':
            receipt['database'] = guard.inspect()
            receipt['agent'] = agent_archive(directory)
            receipt['api_originals'], _ = queue.archives(directory)
            receipt['frontend'] = aws('amplify', 'list-jobs', '--app-id', 'd24jvguj7brnkj', '--branch-name', 'main', '--max-results', '3')['jobSummaries']
        elif args.mode == 'migrate':
            before = guard.inspect()
            receipt['before'] = before
            if admin.query("select to_regclass('public.research_claim_designs') present")[0]['present'] is not None or active():
                raise RuntimeError('Claim migrations already partly/presently applied; inspect retained receipts before resuming')
            receipt['migrations'] = []
            for name in MIGRATIONS:
                raw = (ROOT / 'database' / name).read_bytes()
                item = dict(name=name, sha256=sha(raw), bytes=len(raw), status='running')
                receipt['migrations'].append(item)
                save()
                admin.query(raw.decode(), read_only=False)
                item.update(status='complete', ended_at=stamp())
                save()
            receipt['after'] = after = guard.inspect()
            if [r for r in after['pointers'] if r['module_id'] != MODULE] != before['pointers']:
                raise RuntimeError('Unrelated prompt pointers changed')
            if before['scientific_counts'] != after['scientific_counts']:
                raise RuntimeError('Scientific counts changed; investigate concurrent writes')
            receipt['security'] = security()
        elif args.mode.startswith(('diff-', 'deploy-')):
            deploying = args.mode.startswith('deploy-')
            kind = args.mode.split('-')[1]
            receipt['security'] = security()
            if deploying:
                if manifest['source_revision'] != subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip() or subprocess.check_output(['git', 'status', '--porcelain'], cwd=BACKEND, text=True).strip():
                    raise RuntimeError('Release must pin a clean committed backend')
                if kind == 'api':
                    receipt['previous_api'], _ = queue.archives(directory)
                else:
                    receipt['previous_agent'] = agent_archive(directory)
            credentials = aws('configure', 'export-credentials', '--format', 'process')
            env = dict(os.environ, AWS_ACCESS_KEY_ID=credentials['AccessKeyId'], AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],
                       AWS_SESSION_TOKEN=credentials['SessionToken'], AWS_DEFAULT_REGION='us-east-1')
            env.pop('AWS_PROFILE', None)
            stack = 'JumpServeBenchmarkStack' if kind == 'api' else 'JumpServeAgentStack'
            receipt['before_stack'] = aws('cloudformation', 'describe-stacks', '--stack-name', stack)['Stacks'][0]['Parameters']
            command = ['npx', 'cdk', 'deploy' if deploying else 'diff', stack, '--app',
                       'npx ts-node --prefer-ts-exts bin/' + ('benchmark.ts' if kind == 'api' else 'agent.ts'), '--exclusively']
            command += ['--require-approval', 'never', '--outputs-file', str(directory / 'outputs.json')] if deploying else ['--no-change-set']
            receipt['command'] = command
            save()
            with (directory / 'cdk.log').open('w') as stream:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
            if result.returncode:
                raise RuntimeError('Scoped CDK failed; inspect retained log')
            if deploying:
                after = aws('cloudformation', 'describe-stacks', '--stack-name', stack)['Stacks'][0]
                receipt['after_stack'] = dict(status=after['StackStatus'], parameters=after['Parameters'])
                if receipt['before_stack'] != after['Parameters']:
                    raise RuntimeError('Existing stack parameters changed')
                if kind == 'api':
                    receipt['api'], _ = queue.archives(directory, manifest)
                else:
                    receipt['agent'] = agent_archive(directory, expected=True)
        elif args.mode == 'publish':
            receipt['security'] = security()
            receipt['agent'] = agent_archive(directory, expected=True)
            receipt['api'], _ = queue.archives(directory, manifest)
            if active()[0]['active_version_id'] is not None:
                raise RuntimeError('Inspect existing active pointer; do not republish silently')
            before = pointers()
            receipt['private_originals'] = archive_evidence(directory)
            save()
            publication = dict(report, release_artifacts=receipt['private_originals'])
            sql = 'select publish_agent_prompt(' + ','.join((admin.literal(CANDIDATE) + '::uuid', 'null::uuid',
                admin.literal(report['prompt_content_sha256']), admin.literal(json.dumps(publication)) + '::jsonb',
                admin.literal('Primary Codex AI implementer; user-authorized production release; non-independent AI review'), admin.literal(MODULE))) + ')'
            receipt['publication'] = admin.query(sql, read_only=False)
            receipt['active'] = active()
            if receipt['active'][0]['active_version_id'] != CANDIDATE:
                raise RuntimeError('Published pointer differs')
            if [r for r in before if r['module_id'] != MODULE] != [r for r in pointers() if r['module_id'] != MODULE]:
                raise RuntimeError('Unrelated prompt pointers changed')
        elif args.mode == 'verify':
            receipt['security'] = security()
            receipt['agent'] = agent_archive(directory, expected=True)
            receipt['api'], _ = queue.archives(directory, manifest)
            receipt['active'] = active()
            if len(receipt['active']) != 1 or receipt['active'][0]['active_version_id'] != CANDIDATE or receipt['active'][0]['content_sha256'] != report['prompt_content_sha256'] or not receipt['active'][0]['published_at']:
                raise RuntimeError('Evaluated prompt is not active/published')
            with guard.OPEN.open(API + '/capabilities', timeout=25) as response:
                receipt['capabilities'] = json.load(response)
            if receipt['capabilities']['preparation']['claim_design_version'] != 'claim-experiment-design-v1':
                raise RuntimeError('Claim design capability differs')
            study = '00000000-0000-4000-8000-000000000001'
            receipt['anonymous_denials'] = [deny(API + '/studies/' + study + '/idea'),
                deny(API + '/studies/' + study + '/gap-experiments', dict(action='design')),
                deny(AGENT, dict(action='idea', design_version='claim-experiment-design-v1')),
                deny(AGENT, dict(action='capabilities'))]
            receipt['conditional_gaps'] = ['Legitimate Google-authenticated planning/provider/persistence round trip',
                'Authenticated plan-artifact Storage round trip', 'Actual networking experiment execution']
        elif args.mode == 'frontend-release':
            if active()[0]['active_version_id'] != CANDIDATE:
                raise RuntimeError('Publish compatible prompt before frontend release')
            receipt['job'] = aws('amplify', 'start-job', '--app-id', 'd24jvguj7brnkj', '--branch-name', 'main', '--job-type', 'RELEASE')['jobSummary']
        elif args.mode == 'frontend-status':
            jobs = aws('amplify', 'list-jobs', '--app-id', 'd24jvguj7brnkj', '--branch-name', 'main', '--max-results', '3')['jobSummaries']
            receipt['jobs'] = jobs
        receipt['status'] = 'complete'
    except Exception as error:
        receipt.update(status='failed', reason=str(error))
        raise
    finally:
        receipt['ended_at'] = stamp()
        save()
        print(json.dumps(dict(directory=str(directory), status=receipt['status'], reason=receipt.get('reason'))))


if __name__ == '__main__':
    main()
