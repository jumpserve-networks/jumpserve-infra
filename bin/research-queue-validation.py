"""Record fixed local queue release checks and preserve original-byte receipts.

No deployment, credentials, remote data or arbitrary commands. Database/browser
campaigns have their own entry points and timestamped original reports; this
command collects those plus fixed backend/frontend/CDK regressions.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT.parent/'jumpserve-back-end'; FRONTEND=ROOT.parent/'jumpserve-front-end'
DESTINATION=ROOT/'docs/research-queue-validation'
STAMP=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
RECEIPTS=ROOT/'.test-artifacts/research-queue-release'/STAMP

def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    report_path=ROOT/'docs/research-queue-validation-v1.json'
    if report_path.exists():raise SystemExit('Preserve v1; append an explicitly versioned report for later changes.')
    RECEIPTS.mkdir(parents=True,exist_ok=False);DESTINATION.mkdir(parents=True,exist_ok=True)
    report=dict(version=1,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
      protocol='research-queue-protocol-v1.md',amendment='research-queue-amendment-v2.md',
      reviewer=dict(identity='Primary Codex AI implementer',type='AI',independence='Not independent'),
      design='Development regressions; no held-out or human scientific review. No paper claims are strengthened.',
      commands=[],artifacts=[],implementation=[],
      release=dict(production_deployed=False,remote_migrations_applied=False,conditional_gaps=[
        'Legitimate Google-authenticated owner enqueue/review/cancel and remote owner-isolation request',
        'Remote Supabase Storage round-trip original-byte hashes',
        'Scheduled AWS worker invocation and deployed end-to-end verification']),
      usage=dict(measured_charges_usd=None,estimated_charges_usd=None,model_usage=None,experiment_instances_launched=0,
        limitations='Local hosting/storage/Codex usage unallocated; missing usage is not zero cost. Synthetic worker fixtures make no model or experiment-instance calls.'))
    def preserve(path,label):
        raw=path.read_bytes();name=label
        target=DESTINATION/name
        if target.exists():raise ValueError('Receipt collision; original evidence must not be overwritten: '+name)
        target.write_bytes(raw)
        assert target.read_bytes()==raw and sha(target.read_bytes())==sha(raw)
        report['artifacts'].append(dict(path=str(target.relative_to(ROOT)),origin=str(path),byte_count=len(raw),sha256=sha(raw),retrieved_hash_verified=True))
    checks=[('backend-tests',BACKEND,['python3','-B','-m','unittest','discover','-s','research_workflow/tests','-v'],60),
      ('frontend-tests',FRONTEND,['npm','test'],60),('frontend-lint',FRONTEND,['npm','run','lint'],60),
      ('frontend-build',FRONTEND,['npm','run','build'],120),('runtime-staging',ROOT,['python3','-B','bin/prepare-research-runtime.py'],30),
      ('infra-build',ROOT,['npm','run','build'],60),('infra-tests',ROOT,['npm','test','--','--runInBand'],120)]
    for name,cwd,command,timeout in checks:
        tick=time.monotonic();environment=os.environ.copy();environment.pop('NEXT_PUBLIC_RESEARCH_WORKFLOW_API_URL',None)
        try:
            completed=subprocess.run(command,cwd=cwd,env=environment,capture_output=True,timeout=timeout)
            stdout,stderr,status=completed.stdout,completed.stderr,completed.returncode
        except subprocess.TimeoutExpired as error:
            stdout,stderr,status=error.stdout or b'',error.stderr or b'',None
        for suffix,raw in [('stdout',stdout),('stderr',stderr)]:
            path=RECEIPTS/(name+'-'+suffix+'.txt');path.write_bytes(raw);preserve(path,path.name)
        report['commands'].append(dict(name=name,cwd=str(cwd),command=command,exit_code=status,wall_seconds=time.monotonic()-tick,passed=status==0))
        print(name+': '+('passed' if status==0 else 'failed'),flush=True)
    database_reports=sorted((ROOT/'.test-artifacts/research-queue').glob('*/database-report.json'))
    browser_reports=sorted((FRONTEND/'.test-artifacts/research-workflow').glob('*-browser-report.json'))
    current_browser=[p for p in browser_reports if p.name>='2026-10-07T16-59-00']
    if not database_reports or not current_browser:raise ValueError('Original database/browser campaign reports required.')
    for p in database_reports:preserve(p,p.parent.name+'-database-report.json')
    for p in current_browser:preserve(p,p.name)
    latest_database=database_reports[-1];latest_browser=current_browser[-1]
    db=json.loads(latest_database.read_bytes());browser=json.loads(latest_browser.read_bytes())
    report['database_campaign']=dict(passed=db['passed'],report=str(latest_database),checks=db['checks'],database=db['database'],local_storage_transport=True)
    report['browser_campaign']=dict(passed=browser['passed'],report=str(latest_browser),checks=browser['checks'],conditional_gaps=browser['conditional_gaps'])
    for path in sorted(latest_database.parent.iterdir()):
        if path.name!='database-report.json' and path.is_file():preserve(path,latest_database.parent.name+'-'+path.name)
    browser_prefix=latest_browser.name.removesuffix('-browser-report.json')
    for path in sorted(latest_browser.parent.glob(browser_prefix+'*')):
        if path!=latest_browser and path.is_file():preserve(path,path.name)
    for name in ('research-queue-protocol-v1.md','research-queue-amendment-v2.md'):
        preserve(ROOT/'docs'/name,'frozen-'+name)
    preserve(ROOT/'research-workflow-runtime.json','runtime-manifest-v2.json')
    source_paths=[*(BACKEND/'research_workflow').glob('*.py'),
      BACKEND/'research_workflow/tests/test_scheduler.py',ROOT/'database/202610070002_research_queue.sql',
      ROOT/'lib/research-workflow.ts',ROOT/'bin/research-workflow-database.py',
      ROOT/'test/check_research_queue_database.py',ROOT/'test/research-workflow.test.ts',
      FRONTEND/'lib/research-queue.ts',FRONTEND/'lib/research-queue-example.ts',
      FRONTEND/'app/components/research-workflow/claim-queue.tsx',FRONTEND/'app/components/research-workflow/queue-example.tsx',
      FRONTEND/'app/components/research-workflow/workspace.tsx',FRONTEND/'app/module/research-verification/methods/page.tsx',
      FRONTEND/'tests/research-queue.test.mjs',FRONTEND/'scripts/verify-research-workflow.mjs',Path(__file__)]
    for path in source_paths:
        raw=path.read_bytes();report['implementation'].append(dict(path=str(path),byte_count=len(raw),sha256=sha(raw)))
    report['release']['local_blockers_passed']=all(c['passed'] for c in report['commands']) and db['passed'] and browser['passed']
    report['release']['scientific_coverage']='No new paper evaluation. Original IPv6 register remains 3 reproduced, 3 discrepant, 5 inconclusive, 4 untested under its original conditions.'
    report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    with report_path.open('x') as output:output.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(report_path),local_blockers_passed=report['release']['local_blockers_passed'],original_artifacts=len(report['artifacts']),production_deployed=False)))
    if not report['release']['local_blockers_passed']:raise SystemExit(1)
if __name__=='__main__':main()
