"""Freeze this release's fixed evidence inventory; refuse replacement of prior reports."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT.parent/'jumpserve-front-end'
REPORT=ROOT/'docs/research-workflow-release-v1.json'
DESTINATION=ROOT/'docs/research-workflow-release-validation'
if REPORT.exists() or DESTINATION.exists():raise SystemExit('Preserve the prior release; use a versioned amendment.')
server=ROOT/'.test-artifacts/research-release/20261007T193726747891Z/production-server-report.json'
browser=FRONT/'.test-artifacts/research-production/2026-10-07T19-45-13.798Z/browser-report.json'
s=json.loads(server.read_text());b=json.loads(browser.read_text())
assert s['passed'] and b['passed'] and b['origin']=='https://jumpserve.quaint-lab.org'
app=json.loads((ROOT/'.test-artifacts/research-release/amplify-job-105.json').read_text())
assert app['summary']['status']=='SUCCEED' and app['summary']['commitId']=='bc6f87abb480c966dd56b828a60f5c279d8fc83f'
security=json.loads((ROOT/'.test-artifacts/research-release/database-postdeploy-v1.json').read_text())
assert security['passed'] and len(security['security'])==20

def digest(raw):return hashlib.sha256(raw).hexdigest()
artifacts=[]
origins=[(ROOT/'.test-artifacts/research-release','server'),(FRONT/'.test-artifacts/research-production','browser')]
for origin,label in origins:
    for source in sorted(origin.rglob('*')):
        if not source.is_file():continue
        target=DESTINATION/label/source.relative_to(origin);target.parent.mkdir(parents=True,exist_ok=True)
        raw=source.read_bytes();shutil.copyfile(source,target);assert digest(target.read_bytes())==digest(raw)
        artifacts.append(dict(path=str(target.relative_to(ROOT)),origin=str(source),sha256=digest(raw),byte_count=len(raw),copy_retrieval_hash_verified=True))
protocols={}
for name in ('research-workflow-release-protocol-v1.md','research-workflow-release-amendment-v2.md'):
    source=ROOT/'docs'/name;protocols[name]=digest(source.read_bytes());target=DESTINATION/source.name
    shutil.copyfile(source,target);assert digest(target.read_bytes())==protocols[name]
    artifacts.append(dict(path=str(target.relative_to(ROOT)),origin=str(source),sha256=protocols[name],byte_count=target.stat().st_size,copy_retrieval_hash_verified=True))
prior=json.loads((ROOT/'docs/research-queue-validation-v2.json').read_text())
changed=[item['path'] for item in prior['implementation'] if digest(Path(item['path']).read_bytes())!=item['sha256']]
assert set(changed)=={str(ROOT/'lib/research-workflow.ts'),str(ROOT/'bin/research-workflow-database.py'),str(ROOT/'test/research-workflow.test.ts')}
manifest=json.loads((ROOT/'research-workflow-runtime.json').read_text())
for name,sha in manifest['files'].items():assert digest((ROOT.parent/'jumpserve-back-end/research_workflow'/name).read_bytes())==sha
implementation={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in [ROOT/'cdk.json',ROOT/'lib/research-workflow.ts',ROOT/'bin/verify-research-production.py',ROOT/'bin/research-workflow-database.py',ROOT/'research-workflow-runtime.json',ROOT/'.github/workflows/deploy.yml']}
implementation['frontend/scripts/verify-research-production.mjs']=digest((FRONT/'scripts/verify-research-production.mjs').read_bytes())
report=dict(version=1,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
 authorization='Current explicit production deployment request; no standing future deployment authority',
 targets=security['targets'],frontend='https://jumpserve.quaint-lab.org/module/research-verification',
 protocols=protocols,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independence='Not independent'),
 design='Development and production software checks; no new paper experiment, held-out evaluation or human review',
 software=dict(status='deployed',release_blockers_passed=True,amplify_job_id='105',frontend_revision=app['summary']['commitId'],backend_revision=manifest['source_revision'],infrastructure_application_revision='1addd11a7b34bacfad6d6ae340b379a8a49f0702',infrastructure_source_branch='release/research-workflow-20261007',frontend_verifier_branch='release/research-verification-evidence-20261007',frontend_verifier_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=FRONT,text=True).strip(),configuration='researchReservedConcurrencyEnabled=false; shared AWS Lambda pool=10; PostgreSQL queued-job caps global=4/study=2',local_checks=dict(backend_tests=46,frontend_tests=120,infrastructure_tests=84,lint='passed',frontend_build='passed',infrastructure_build='passed',isolated_database_and_browser='Prior successful exact-byte development evidence reused'),production_checks=dict(database_relations=20,server_groups=3,browser_groups=5,scheduled_jobs=2,scheduled_claiming_invocations=1,stored_originals_retrieved_and_hash_verified=4,google_authenticated_owner_request=False)),
 scientific=dict(status='No new paper assessment',claims_upgraded=0,public_generic_studies=0,synthetic_fixture_published=False,existing_ipv6_labels=dict(reproduced=3,discrepant=3,inconclusive=5,untested=4),limitation='Original assessment conditions apply; deployment and synthetic controls do not strengthen these labels. Generic AI chat is disabled.'),
 conditional_gaps=['Legitimate Google-owner intake/enqueue/review/cancel and cross-owner requests','Actual Google provider round trip','Live expired-lease recovery; local actual PostgreSQL fencing passed','Completed generic-study production charts/CSV/JSON require a genuine reviewed publication; isolated completed and invalid data checks passed'],
 preserved_failures=['CloudFormation v1 quota failure and complete rollback','AWS quota request for 16 rejected: desired value must exceed default 1000; no quota increase or support case','Local verifier SDK credentials and incomplete first-page resource inventory','Production browser intake-link selector mismatch','Two captured Git build logs normalized initially; original-byte checkout preservation corrected','Filtered CloudWatch captures empty; bounded direct stream retrieval recovered REPORT records'],
 available_usage=json.loads((ROOT/'.test-artifacts/research-release/available-usage-v2.json').read_text()),
 reproduction_commands=dict(database='python3 -B bin/research-workflow-database.py --queue --output NEW_REPORT',runtime='python3 -B bin/prepare-research-runtime.py',public_browser='npm run verify:research:production',server='python3 -B bin/verify-research-production.py (authorized production operator only; creates a private software fixture)',limits='Commands perform bounded software checks, not universal paper verification; future production mutations need explicit authorization.'),
 evidence_source_hashes=implementation,changed_since_local_validation=changed,artifact_manifest=artifacts,
 limitations=['Original SQL server bytes are not recoverable from catalog verification; submitted migration hashes and apply receipts are preserved','Intermediate failed verifier outputs are retained, but not every intermediate uncommitted verifier source revision was snapshotted','CLI snapshots are serialized response evidence, not original HTTP transport captures','AWS/Supabase/Amplify/Codex charges are unallocated; missing is not zero','Use the pinned infrastructure release branch for subsequent infrastructure synthesis; pre-release main does not define this research feature'])
REPORT.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(report=str(REPORT),artifacts=len(artifacts),copied_hashes_verified=True,software_status=report['software']['status'])))
