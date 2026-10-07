"""Freeze preparation release evidence without replacing the earlier protocols/results."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT.parent/'jumpserve-front-end'
DEST=ROOT/'docs/research-preparation-validation'
REPORT=ROOT/'docs/research-preparation-production-release-v1.json'
if REPORT.exists():raise SystemExit('Preserve this release report; use a versioned amendment.')
original=ROOT/'.test-artifacts/research-release/20261007T221548717353Z'
followup=ROOT/'.test-artifacts/research-release/20261007T222058320533Z'
browser=FRONT/'.test-artifacts/research-production/2026-10-07T22-19-14.502Z'
first=json.loads((original/'production-server-report.json').read_text())
server=json.loads((followup/'production-server-report.json').read_text())
ui=json.loads((browser/'browser-report.json').read_text())
security=json.loads((DEST/'production-security-v1.json').read_text())
app=json.loads((DEST/'production-amplify-job-106-v1.json').read_text())
manifest=json.loads((ROOT/'research-workflow-runtime.json').read_text())
usage=json.loads((DEST/'production-usage-v1.json').read_text())
assert not first['passed'] and server['passed'] and ui['passed'] and security['passed']
assert len(security['security'])==21
assert server['followup_of']['experiment_repeated'] is False and server['followup_of']['production_writes'] is False
assert app['summary']['status']=='SUCCEED' and app['summary']['commitId']=='849a33891ba30adfcabe9cfc2858cae61e8b7885'
assert server['checks'][2]['evidence']['cells']==1152
assert security['targets']['aws_account']=='395567831870' and security['targets']['supabase_project']=='regphejnlvfpyokpniny'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def preserve_copy(source,target):
    raw=source.read_bytes()
    if target.exists():
        assert digest(target.read_bytes())==digest(raw), 'Prior evidence bytes differ; never replace them'
    else:shutil.copyfile(source,target)
    assert digest(target.read_bytes())==digest(raw)
artifacts=[]
for directory,label in [(original,'production-server-initial-v1'),(followup,'production-server-followup-v2')]:
    for file in sorted(directory.iterdir()):
        if not file.is_file():continue
        raw=file.read_bytes();record=dict(origin=str(file.relative_to(ROOT)),sha256=digest(raw),byte_count=len(raw),repository_bytes_retained=False)
        if file.name in ('production-server-report.json','capabilities.json','fixture-definition.json','preparation-partial-status.json'):
            target=DEST/label/file.name;target.parent.mkdir(parents=True,exist_ok=True)
            preserve_copy(file,target)
            record.update(path=str(target.relative_to(ROOT)),repository_bytes_retained=True,copy_hash_verified=True)
        artifacts.append(record)
for file in sorted(browser.iterdir()):
    if not file.is_file():continue
    target=DEST/'production-browser-v1'/file.name;target.parent.mkdir(parents=True,exist_ok=True)
    raw=file.read_bytes();preserve_copy(file,target)
    artifacts.append(dict(origin=str(file.relative_to(FRONT)),path=str(target.relative_to(ROOT)),sha256=digest(raw),byte_count=len(raw),repository_bytes_retained=True,copy_hash_verified=True))
for file in sorted(DEST.glob('production-*')):
    if file.is_file():artifacts.append(dict(path=str(file.relative_to(ROOT)),sha256=digest(file.read_bytes()),byte_count=file.stat().st_size,repository_bytes_retained=True))
remote=[]
for study_id,records in [(first['private_fixture']['study_id'],first['checks'][2]['evidence']['artifacts']),(server['preparation_fixture']['study_id'],server['checks'][2]['evidence']['artifacts'])]:
    remote.extend(dict(record,study_id=study_id,bucket='research-workflow-raw',storage_path=study_id+'/'+record['sha256'],access='Private backend-only; not publicly downloadable',origin='Operator release fixture') for record in records)
assert len(remote)==18 and all(r['retrieved_hash_verified'] for r in remote)
local=json.loads((DEST/'implementation-manifest-v1.json').read_text())
current=[];changes=[]
for record in local['files']:
    file=ROOT.parent/record['repository']/record['path'];raw=file.read_bytes();sha=digest(raw)
    current.append(dict(record,sha256=sha,bytes=len(raw)))
    if sha!=record['sha256']:changes.append(dict(repository=record['repository'],path=record['path'],previous_sha256=record['sha256'],current_sha256=sha))
assert [(r['repository'],r['path']) for r in changes]==[('jumpserve-infra','research-workflow-runtime.json')]
for filename,sha in manifest['files'].items():assert digest((ROOT.parent/'jumpserve-back-end/research_workflow'/filename).read_bytes())==sha
protocols={name:digest((ROOT/'docs'/name).read_bytes()) for name in ['research-preparation-protocol-v1.md','research-preparation-production-protocol-v1.md','research-preparation-production-amendment-v2.md']}
report=dict(version=1,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),authorization='Fresh explicit request: Oh, please deploy to production',targets=server['targets'],protocol_sha256=protocols,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independence='Not independent; exposed development and release regressions'),software=dict(status='Deployed and verified within declared conditional limits',release_blockers_passed=True,frontend_revision=app['summary']['commitId'],amplify_job_id='106',backend_revision=manifest['source_revision'],infrastructure_application_revision='599805d',infrastructure_verifier_revision='05d162d',frontend_verifier_revision='2f994db',infrastructure_branch='release/research-workflow-20261007',backend_branch='release/research-preparation-20261007',local_checks=local['local_checks'],production_checks=dict(security_relations=21,service_only_rpcs=11,lambda_archives=2,runtime_hashes_per_archive=8,browser_groups=6,scheduled_synthetic_runs=2,scheduled_archived_runs=6,manual_tasks_preserved=14,stored_artifacts_hash_verified=18,google_authenticated_request=False),benchmark_ami='ami-0808d1157e26c65cb',concurrency='Shared AWS pool 10; database queued-job caps global 4/study 2'),scientific=dict(scope='Archived numerical rechecks under exposed 0.0051 percentage-point tolerance; no independent reproduction or new network measurements',matched_cells=1152,numerical_agreement_cells=1152,claims_upgraded=0,previous_labels=dict(reproduced=3,discrepant=3,inconclusive=5,untested=4),private_fixture_assessments_imported=15,private_fixture_assessments_changed=0,publication=False,limitation='Numerical cell agreement is not correctness, causality, compliance, generalizability or a resolution of all paper claims; source metadata import does not retrieve or fully review every referenced text'),existing_user_workspace=server['existing_user_workspace'],usage=json.loads((DEST/'production-usage-v1.json').read_text()),conditional_gaps=['Legitimate Google owner preparation/enqueue request, cross-owner HTTP request and provider round trip; no session was available','Completed generic-study production charts/CSV/JSON await genuine reviewed publication; isolated completed/missing/invalid data checks passed','Live expired-lease recovery remains conditional; prior isolated PostgreSQL fencing checks passed','Generic AI extraction/chat remains disabled pending separately evaluated prompts and domain integrations'],preserved_failures=[dict(report=str((original/'production-server-report.json').relative_to(ROOT)),reason='Verifier applied 256 KB input bound to larger preparation artifacts; corrected read-only audit reused all retained runs without runtime changes'),dict(kind='Sandbox endpoint status check',reason='One CloudFormation endpoint connection failed; elevated read-only check confirmed UPDATE_COMPLETE'),dict(kind='Ad hoc local inspection',reason='Relative sibling path and a screenshot timestamp inferred with a one-millisecond offset did not resolve; corrected to resolved repository path and enumerated artifact paths before successful inspection')],changed_since_local_validation=changes,application_source_sha256=current,artifact_manifest=artifacts,private_stored_originals=remote,reproduction_commands=dict(runtime='python3 -B bin/prepare-research-runtime.py',database='python3 -B bin/research-workflow-database.py --preparation --output NEW_VERSIONED_REPORT',browser='npm run verify:research:production -- --preparation',retained_fixture_read_only='python3 -B bin/verify-research-production.py --preparation-followup',usage='python3 -B bin/collect-research-preparation-usage.py (refuses replacing this capture)',new_fixture='python3 -B bin/verify-research-production.py --preparation (production writes require a new explicit authorization)'),limitations=['Migration hashes identify submitted bytes and apply receipt; catalog verification cannot recover originally executed SQL','Raw fixture payloads and Lambda archives remain in local ignored artifact directories; fixture originals are also retained privately in Supabase and have retrieved-byte hashes','CLI response snapshots are serialized evidence, not original HTTP transport bytes','Review is by the implementing AI; no human or independent review is asserted','Observed cell counts are a fixed archived census; no inferential confidence intervals are justified','Unallocated and missing usage/charges must not be treated as zero'])
with REPORT.open('x') as output:output.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(report=str(REPORT),release_blockers_passed=True,artifacts=len(artifacts),remote_hashes_verified=len(remote),application_changed_since_local_validation=changes)))
