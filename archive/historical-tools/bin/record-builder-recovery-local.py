"""Aggregate fixed local recovery evidence. No SQL, AWS, model or deployment calls."""
import datetime as dt,hashlib,json,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def main():
    protocol=BACK/'research_workflow/policies/builder-recovery-validation-v3.json'
    units=BACK/'.test-artifacts/builder-recovery-v3-unit-final.log'
    native=BACK/'.test-artifacts/experiment-builder/20261029T213923112418Z/report.json'
    database=ROOT/'.test-artifacts/research-ideas/database/20261029T213349143062Z/report.json'
    replay=ROOT/'.test-artifacts/assessment-4055396e/20261029T213554831096Z/report.json'
    sources={
        'backend':(BACK,['research_workflow/'+name for name in ('autonomous_repair.py','autonomy.py','experiment_builder.py','openclaw_runtime.py','dispatch_recovery.py','store.py','policies/builder-recovery-validation-v3.json','tests/test_autonomous_repair.py','tests/test_experiment_builder.py','tests/test_dispatch_recovery.py','builder-recovery-20261029.md')]),
        'infra':(ROOT,['database/202610290001_builder_reconciliation.sql','test/check_experiment_builder_database.py','test/check_research_ideas_database.py','bin/inspect-assessment-4055396e.py','bin/record-builder-recovery-local.py'])}
    text=units.read_text();assert re.search(r'Ran 379 tests in [\d.]+s\s+OK',text)
    n=json.loads(native.read_bytes());d=json.loads(database.read_bytes());p=json.loads(replay.read_bytes())
    assert n['status']=='passed' and n['live_provider_calls']==0 and n['slots']==3 and d['passed'] and len(d['checks'])==5 and p['passed']
    assert d['checks'][-1]['evidence']['actual_worker_to_database_reconciliation'] is True
    for name,record in n['source_files'].items():assert sha((BACK/'research_workflow'/name).read_bytes())==record['sha256'],'Native control source changed: '+name
    migration='202610290001_builder_reconciliation.sql'
    assert d['migration_sha256'][migration]==sha((ROOT/'database'/migration).read_bytes())
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out=ROOT/'.test-artifacts/builder-recovery-v3'/stamp;out.mkdir(parents=True,mode=0o700)
    entries=[]
    def record(path,role,copy_to=None):
        raw=path.read_bytes();digest=sha(raw)
        # Independent hash implementation over the same unchanged original.
        other=subprocess.check_output(['shasum','-a','256',str(path)],text=True).split()[0];assert other==digest
        if copy_to:
            dest=out/'original-source'/copy_to;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);assert sha(dest.read_bytes())==digest
        entries.append(dict(path=str(path),sha256=digest,independent_sha256=other,bytes=len(raw),role=role))
    for repo,(root,names) in sources.items():
        for name in names:record(root/name,'examined-source',repo+'/'+name)
    for path in (units,native,database,replay):record(path,'validation-report')
    for directory in ('20261029T201122273408Z','20261029T201649511755Z','20261029T213731633407Z'):
        for path in sorted((ROOT/'.test-artifacts/assessment-4055396e'/directory).iterdir()):
            if path.is_file():record(path,'retained-original-or-labeled-derived-diagnostic')
    record(replay.parent/'original-artifact-manifest.json','original-artifact-manifest')
    record(replay.parent/'current-public-queue.json','public-snapshot-at-2136-UTC')
    result=dict(version='builder-recovery-local-evidence-v3',recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),protocol_sha256=sha(protocol.read_bytes()),
        assessment_id='4055396e-35c0-4962-ba39-cf23e443ad8d',unit_tests=379,postgres_check_groups=5,native_slots=3,
        independent_hash_implementation='Perl shasum SHA-256, compared with Python hashlib for every listed file; shared original bytes, not independent scientific evidence.',
        reviewer=dict(identity='Codex',type='AI',independent=False),validation_kind='development regressions; recorded cases exposed, synthetic provider responses; no held-out validation',
        new_live_model_calls=0,new_cloud_instances=0,production_mutations=0,merged=False,deployed=False,measured_charges_usd=None,subscription_allocation_usd=None,
        remaining=['Exact production linux/amd64 runtime qualification','Separately frozen bounded live-model qualification','Explicit merge/deployment request and new committed runtime pin including dispatch_recovery.py','Production migration, worker/controller activation and no-replay resumption verification','Actual scientific acquisition and claim evaluation'],
        review_scope='Runtime changes, selected failure receipts/history and actual regression outputs examined. A file hash/inventory does not assert complete paper/literature review; no scientific campaign performed.',artifacts=entries)
    raw=(json.dumps(result,indent=2)+'\n').encode();(out/'manifest.json').write_bytes(raw)
    print(json.dumps(dict(manifest=str(out/'manifest.json'),sha256=sha(raw),artifacts=len(entries),unit_tests=379,deployed=False)))

if __name__=='__main__':main()
