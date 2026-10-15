"""Fixed-target publication/deployment of the evaluated v11 idea guide.

No arbitrary SQL, files, model calls, studies or experiment resources accepted.
Receipts retain failed as well as successful actions; credentials never printed.
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
import tarfile
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('previous_ideas_release', ROOT/'bin/research-ideas-release.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
admin = previous.admin
CANDIDATE = 'ba16759e-ff38-4491-ae21-5766261e710b'
PRIOR = 'e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8'
EVALUATION = ROOT/'.test-artifacts/research-ideas/evaluations/20261015T032302556316Z'
MIGRATIONS = (
    '202610140001_idea_interview_prompt.sql', '202610140002_idea_interview_prompt_v4.sql',
    '202610140003_idea_interview_prompt_v5.sql', '202610140004_idea_interview_prompt_v6.sql',
    '202610140005_idea_interview_prompt_v7.sql', '202610140006_idea_interview_prompt_v8.sql',
    '202610140007_idea_review_sources_v9.sql', '202610140008_idea_review_sources_v10.sql',
    '202610140009_idea_review_sources_v11.sql',
)
EVIDENCE = ('docs/idea-interview-evidence-v1.tar.gz', 'docs/idea-review-source-fidelity-evidence-v1.tar.gz',
            'docs/idea-interview-validation-v1.json', 'docs/idea-review-source-fidelity-validation-v1.json',
            'docs/idea-interview-release-protocol-v1.json')

def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def aws(*args):
    return json.loads(subprocess.check_output(['aws', *args, '--profile', 'jumpserve', '--region', 'us-east-1', '--output', 'json'], timeout=60))

def evaluated():
    validation = json.loads((ROOT/'docs/idea-review-source-fidelity-validation-v1.json').read_text())
    report = json.loads((EVALUATION/'evaluation-report.json').read_text())
    seed = json.loads((ROOT/'database/seed-research-ideas-prompt-v11.json').read_text())
    if sha((EVALUATION/'evaluation-report.json').read_bytes()) != validation['actual_answer_evaluation']['report_sha256']:
        raise RuntimeError('Reviewed evaluation changed')
    if report['prompt_version_id'] != CANDIDATE or report['publication_eligible'] is not True or report['reviewer']['passed'] is not True or len(report['cases']) != 21 or not all(c['passed'] and c['status'] == 'complete' for c in report['cases']):
        raise RuntimeError('Exact candidate did not pass its declared development review')
    if sha((seed['system_prompt']+'\n\n'+seed['research_context']).encode()) != report['prompt_content_sha256']:
        raise RuntimeError('Candidate seed content changed')
    for name, digest in report['runtime_hashes'].items():
        if sha((ROOT/name).read_bytes()) != digest: raise RuntimeError('Evaluated runtime changed: '+name)
    for case in report['cases']:
        for suffix, key in (('-output.txt', 'output_sha256'), ('-rendered.json', 'rendered_sha256')):
            if sha((EVALUATION/(case['name']+suffix)).read_bytes()) != case[key]: raise RuntimeError('Original answer changed')
    for name, historical in (('idea-interview', 'idea-interview-validation-v1.json'), ('idea-review-source-fidelity', 'idea-review-source-fidelity-validation-v1.json')):
        record = json.loads((ROOT/'docs'/historical).read_text())
        path = ROOT/record['evidence_bundle']['path']
        if sha(path.read_bytes()) != record['evidence_bundle']['sha256']: raise RuntimeError('Evidence bundle changed')
        with tarfile.open(path, 'r:gz') as archive:
            manifest = json.load(archive.extractfile('manifest.json'))
            for item in manifest:
                raw = archive.extractfile(item['path']).read()
                if sha(raw) != item['sha256'] or len(raw) != item['bytes']: raise RuntimeError('Archived original differs')
    return report

def pointers(): return admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id')
def active():
    return admin.query("select v.id,v.version,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id='research-verification'")
def function():
    resource = aws('cloudformation', 'describe-stack-resource', '--stack-name', 'JumpServeAgentStack', '--logical-resource-id', 'AgentFnC1FD126F')
    return resource['StackResourceDetail']['PhysicalResourceId']

def deployed(directory, require_candidate=False):
    report = evaluated()
    result = aws('lambda', 'get-function', '--function-name', function())
    config = result['Configuration']
    if ':395567831870:' not in config['FunctionArn'] or config['Environment']['Variables']['SUPABASE_URL'] != 'https://regphejnlvfpyokpniny.supabase.co': raise RuntimeError('Deployed function target differs')
    with previous.OPEN.open(result['Code']['Location'], timeout=30) as response: raw = response.read()
    if base64.b64encode(hashlib.sha256(raw).digest()).decode() != config['CodeSha256']: raise RuntimeError('Deployed ZIP checksum differs')
    (directory/'deployed-agent.zip').write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name, digest in report['runtime_hashes'].items():
            if sha(archive.read(name.removeprefix('agent/'))) != digest: raise RuntimeError('Deployed runtime differs: '+name)
    if require_candidate:
        rows = active()
        if len(rows) != 1 or rows[0]['id'] != CANDIDATE or rows[0]['content_sha256'] != report['prompt_content_sha256'] or not rows[0]['published_at']: raise RuntimeError('Published candidate differs')
    return dict(function=config['FunctionName'], zip_sha256=sha(raw), runtime_hashes=report['runtime_hashes'],
                layers=config.get('Layers', []), memory_mb=config['MemorySize'], timeout_seconds=config['Timeout'],
                last_modified=config['LastModified'], active=active(), security=previous.verify())

def archive_evidence():
    report = evaluated()
    key = aws('secretsmanager', 'get-secret-value', '--secret-id', 'jumpserve/supabase-service-key')['SecretString']
    base = 'https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'
    public = json.loads((ROOT/'cdk.json').read_text())['context']['supabaseAnonKey']
    objects = []; total = 0
    for name in EVIDENCE:
        raw = (ROOT/name).read_bytes(); total += len(raw)
        if total > 16_000_000: raise RuntimeError('Declared evidence storage budget exceeded')
        path = 'release-verification/idea-interview-20261015/'+sha(raw)+'/'+Path(name).name
        headers = {'apikey': key, 'Authorization': 'Bearer '+key}
        try:
            request = urllib.request.Request(base+path, data=raw, method='POST', headers={**headers, 'Content-Type': 'application/gzip' if name.endswith('.gz') else 'application/json', 'x-upsert': 'false'})
            with previous.OPEN.open(request, timeout=45) as response: response.read()
        except urllib.error.HTTPError as error:
            if error.code != 409: raise RuntimeError('Private artifact upload failed: HTTP '+str(error.code)) from None
        with previous.OPEN.open(urllib.request.Request(base+path, headers=headers), timeout=45) as response: restored = response.read(16_000_001)
        if sha(restored) != sha(raw) or restored != raw: raise RuntimeError('Retrieved original artifact differs')
        status = 200
        try:
            with previous.OPEN.open(urllib.request.Request(base+path, headers={'apikey': public}), timeout=20) as response: response.read(1)
        except urllib.error.HTTPError as error: status = error.code
        if status not in (400, 401, 403, 404): raise RuntimeError('Private artifact anonymous denial differs')
        objects.append(dict(original_path=name, bucket='research-workflow-raw', path=path, sha256=sha(raw), bytes=len(raw), retrieved_hash_verified=True, anonymous_status=status))
    return dict(objects=objects, total_bytes=total, retrieved_original_hashes_verified=True, measured_charges_usd=None)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect', 'prepare-layer', 'migrate', 'diff', 'deploy', 'publish', 'verify'))
    args = parser.parse_args()
    directory = ROOT/'.test-artifacts/idea-interview/release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(protocol='idea-interview-production-release-v1', mode=args.mode, status='running', started_at=stamp(), measured_charges_usd=None, new_model_calls=0)
    def save(): (directory/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    save()
    try:
        receipt['targets'] = previous.target(); report = evaluated(); save()
        if args.mode == 'inspect':
            receipt['inspection'] = previous.inspect()
            receipt['candidates'] = admin.query("select id,version,content_sha256,published_at from agent_prompt_versions where module_id='research-verification' order by created_at")
        elif args.mode == 'prepare-layer':
            # Native AWS login is supported by the CLI even when the locally
            # installed boto3 credential chain cannot read that login session.
            config = aws('lambda', 'get-function-configuration', '--function-name', function())
            layers = config.get('Layers', [])
            if len(layers) != 1: raise RuntimeError('Unexpected deployed layer set')
            layer = aws('lambda', 'get-layer-version-by-arn', '--arn', layers[0]['Arn'])
            with previous.OPEN.open(layer['Content']['Location'], timeout=45) as response: raw = response.read()
            if base64.b64encode(hashlib.sha256(raw).digest()).decode() != layer['Content']['CodeSha256']: raise RuntimeError('Dependency layer ZIP checksum differs')
            destination = ROOT/'agent/layer'
            if destination.exists() and any(destination.iterdir()): raise RuntimeError('Restore only into an empty clean-release layer directory')
            destination.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for entry in archive.infolist():
                    path = Path(entry.filename)
                    if path.is_absolute() or '..' in path.parts: raise RuntimeError('Invalid dependency layer path')
                archive.extractall(destination)
            receipt['dependency_layer'] = dict(arn=layers[0]['Arn'], zip_sha256=sha(raw), bytes=len(raw), original_bytes_verified=True)
        elif args.mode == 'migrate':
            before = previous.inspect(); receipt['before'] = before; receipt['migrations'] = []; save()
            if active()[0]['id'] != PRIOR: raise RuntimeError('Inspect unexpected existing prompt before migration')
            existing = admin.query("select id from agent_prompt_versions where module_id='research-verification' and version in ('research-ideas-v3','research-ideas-v4','research-ideas-v5','research-ideas-v6','research-ideas-v7','research-ideas-v8','research-ideas-v9','research-ideas-v10','research-ideas-v11')")
            if existing: raise RuntimeError('Draft migrations already partially/presently applied; inspect prior receipt, do not overwrite history')
            for name in MIGRATIONS:
                raw = (ROOT/'database'/name).read_bytes(); item = dict(name=name, sha256=sha(raw), bytes=len(raw), status='running'); receipt['migrations'].append(item); save()
                admin.query(raw.decode(), read_only=False); item.update(status='complete', ended_at=stamp()); save()
            after = previous.inspect(); receipt['after'] = after
            if before['pointers'] != after['pointers']: raise RuntimeError('Active pointers changed during migration')
            if before['scientific_counts'] != after['scientific_counts']: raise RuntimeError('Scientific counts changed; investigate concurrent writes')
            receipt['security'] = previous.verify()
            candidate = admin.query('select id,version,content_sha256,published_at from agent_prompt_versions where id='+admin.literal(CANDIDATE)+'::uuid')
            if len(candidate) != 1 or candidate[0]['published_at'] is not None or candidate[0]['content_sha256'] != report['prompt_content_sha256']: raise RuntimeError('Draft differs from evaluated candidate')
            receipt['candidate'] = candidate
        elif args.mode in ('diff', 'deploy'):
            previous.verify()
            if active()[0]['id'] != PRIOR: raise RuntimeError('Keep old prompt active until compatible agent deployed')
            original = aws('lambda', 'get-function', '--function-name', function())
            if args.mode == 'deploy':
                with previous.OPEN.open(original['Code']['Location'], timeout=30) as response: raw = response.read()
                (directory/'previous-agent.zip').write_bytes(raw)
                receipt['rollback'] = dict(function=original['Configuration']['FunctionName'], zip_sha256=sha(raw), active=active()); save()
            credentials = aws('configure', 'export-credentials', '--format', 'process')
            env = dict(os.environ, AWS_ACCESS_KEY_ID=credentials['AccessKeyId'], AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'], AWS_SESSION_TOKEN=credentials['SessionToken'], AWS_DEFAULT_REGION='us-east-1')
            env.pop('AWS_PROFILE', None)
            command = ['npx', 'cdk', args.mode, 'JumpServeAgentStack', '--exclusively']
            command += ['--no-change-set'] if args.mode == 'diff' else ['--require-approval', 'never', '--outputs-file', str(directory/'outputs.json')]
            receipt['command'] = command; save()
            with (directory/'cdk.log').open('w') as stream: result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            if result.returncode: raise RuntimeError('Scoped CDK '+args.mode+' failed; inspect retained log')
            if args.mode == 'deploy': receipt['verification'] = deployed(directory)
        elif args.mode == 'publish':
            receipt['deployed'] = deployed(directory)
            before = pointers(); current = active()[0]['id']
            if current != PRIOR: raise RuntimeError('Unexpected active prompt; inspect before publication')
            receipt['private_artifacts'] = archive_evidence(); save()
            report = dict(report, release_artifacts=receipt['private_artifacts'])
            sql = 'select publish_agent_prompt('+','.join([admin.literal(CANDIDATE)+'::uuid', admin.literal(PRIOR)+'::uuid', admin.literal(report['prompt_content_sha256']), admin.literal(json.dumps(report))+'::jsonb', admin.literal('Primary Codex AI implementer; user-authorized v11 production release; non-independent AI review'), admin.literal('research-verification')])+')'
            receipt['publication_result'] = admin.query(sql, read_only=False)
            receipt['verification'] = deployed(directory, require_candidate=True)
            after = pointers()
            if [r for r in before if r['module_id'] != 'research-verification'] != [r for r in after if r['module_id'] != 'research-verification']: raise RuntimeError('Unrelated prompt pointer changed')
            receipt['other_module_pointers_preserved'] = True
        else: receipt['verification'] = deployed(directory, require_candidate=True)
        receipt['status'] = 'complete'
    except Exception as error:
        receipt.update(status='failed', reason=str(error)); raise
    finally:
        receipt['ended_at'] = stamp(); save()
        print(json.dumps(dict(directory=str(directory), mode=args.mode, status=receipt['status'], reason=receipt.get('reason'))))

if __name__ == '__main__': main()
