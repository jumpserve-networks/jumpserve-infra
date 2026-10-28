"""Retain fixed local recovery evidence as a private assessment artifact.

No migrations, budget changes, worker starts, model calls or deployments.
"""
import importlib.util,io,json,pathlib,re,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/builder-continuation-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
r=release.r;m=release.m;STUDY='4055396e-35c0-4962-ba39-cf23e443ad8d'
def main():
 target=r.target();files={}
 backend=BACK/'.test-artifacts/builder-continuation-v1/assessment-recovery-verified.log';b=backend.read_text();assert '\nOK\n' in b and 'FAILED (' not in b
 frontend=FRONT/'.test-artifacts/assessment-recovery-tests.log';f=frontend.read_text();assert 'fail 0' in f
 infra=ROOT/'.test-artifacts/assessment-recovery-infra-tests-verified.log';i=infra.read_text();assert '92 passed' in i and '1 failed' not in i
 database=sorted((ROOT/'.test-artifacts/research-ideas/database').glob('*/assessment-recovery-report.json'))[-1];db=json.loads(database.read_bytes());assert db['passed'] and len(db['checks'])==3 and db['model_builder_lease_seconds']==330
 source=sorted((ROOT/'.test-artifacts/assessment-4055396e').glob('*/offline-replay.json'))[-1];replay=json.loads(source.read_bytes());assert replay['passed']
 authorization=sorted((ROOT/'.test-artifacts/assessment-4055396e-budget').glob('*/receipt.json'))[-1];authorized=json.loads(authorization.read_bytes());assert authorized['workflow_unchanged'] and authorized['authorized_maximum_usd']==1000
 for base,label in ((ROOT,'.'),(BACK,'backend'),(FRONT,'frontend')):
  names=['docs/assessment-4055396e-recovery-protocol-v1.json','database/202610280002_assessment_budget_amendments.sql','database/202610280003_controller_reconciliation_window.sql','test/check_assessment_recovery_database.py','test/research-workflow.test.ts','lib/research-workflow.ts','bin/inspect-assessment-4055396e.py','bin/replay-assessment-4055396e.py','bin/authorize-assessment-4055396e-budget.py','bin/retain-assessment-4055396e-recovery.py'] if base==ROOT else ['research_workflow/'+n for n in ('autonomy.py','autonomy_inputs.py','autonomy_methods.py','autonomy_model.py','experiment_builder.py','model_dispatch.py','netem_iperf.py','openclaw_runtime.py','tests/test_assessment_recovery.py','tests/test_openclaw.py')] if base==BACK else ['lib/research-autonomy.ts','lib/research-public-queue.ts','tests/research-autonomy.test.mjs','tests/research-public-queue.test.mjs']
  for name in names:files[label+'/'+name]=(base/name).read_bytes()
 for p in (ROOT/'.test-artifacts/assessment-4055396e').glob('*/*'):
  if p.is_file():files['originals/'+str(p.relative_to(ROOT/'.test-artifacts/assessment-4055396e'))]=p.read_bytes()
 for p in (ROOT/'.test-artifacts/research-ideas/database').glob('*/assessment-recovery-report.json'):files['database/'+p.parent.name+'/'+p.name]=p.read_bytes()
 for name,p in [('backend-tests.log',backend),('frontend-tests.log',frontend),('infrastructure-tests.log',infra),('authorization.json',authorization),('infrastructure-build.log',ROOT/'.test-artifacts/assessment-recovery-build-final.log')]:files[name]=p.read_bytes()
 report=dict(version='assessment-recovery-validation-v1',assessment=STUDY,status='local-software-checks-passed;release-pending',target=target,recorded_at=r.stamp(),
  checks=dict(backend_tests=int(re.search(r'Ran (\d+) tests',b)[1]),frontend_tests=273,infrastructure_tests=92,infrastructure_optional_skipped=5,isolated_sql=db['checks'],offline_replay=replay,frontend_lint_and_types='passed',infrastructure_types='passed',native_cli='Actual pinned CLI, synthetic provider transport: original logical request forwarded once; oversized preflight recorded as confirmed zero provider calls.'),
  budget=dict(authorized_maximum_usd=1000,effective_maximum_usd=authorized['effective_maximum_usd'],authorization_event_id=authorized['request_id'],state='authorized-pending-compatible-release',application_default_usd=100,existing_commitments_cents=9980,deadline_unchanged=True),
  windows_seconds=dict(builder_slice=180,builder_dispatch=330,builder_controller_wait=350,lambda_timeout=420,task_lease=480),
  limitations=['Software development regressions and original stopped-request replay; no independent, human, held-out or scientific validation.','No production runtime/schema/frontend release or fresh authenticated upload/chat test in this turn.','Historical unknown outcomes retain their original receipts and require guarded reconciliation; no automatic replay is authorized.','The $1000 cap becomes effective only after the compatible frontend/runtime and audited budget RPC are released. New-assessment default remains $100.','File/transport progress is not substantive review or correctness, and a modified file is not proof of useful scientific progress.','Source revisions are uncommitted working-tree byte versions; exact files and hashes are retained. A bounded live model qualification and deployed end-to-end checks remain release work.'],
  new_remote_model_calls=0,new_experiment_instances=0,scientific_completion=False,measured_charges_usd=None,unallocated_storage_and_compute_cost_usd=None,reviewer=dict(identity='Implementing Codex assistant',type='AI',independent=False,human=False))
 files['validation-report.json']=json.dumps(report,sort_keys=True,separators=(',',':')).encode()
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in sorted(files.items()):z.writestr(name,raw)
  z.writestr('artifact-manifest.json',json.dumps([dict(path=n,bytes=len(v),sha256=r.sha(v)) for n,v in sorted(files.items())]))
 raw=buffer.getvalue();assert len(raw)<20000000;sha=r.sha(raw);path=STUDY+'/'+sha;m.storage(path,raw);restored=m.storage(path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as z:
  for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
 actor=r.admin.query('select owner_id from research_study_owners where study_id='+r.admin.literal(STUDY)+'::uuid')[0]['owner_id']
 record=dict(id=str(uuid.uuid5(uuid.UUID(STUDY),'recovery-validation:'+sha)),sha256=sha,byte_count=len(raw),storage_path=path,media_type='application/zip',verified_at=r.stamp(),provenance=dict(kind='assessment-recovery-software-evidence',version=report['version'],status=report['status'],scientific_completion=False,new_model_calls=0,reviewer=report['reviewer']))
 r.admin.query('select public.research_append('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(actor)+'::uuid',r.admin.literal('artifacts'),r.admin.literal(json.dumps(record))+'::jsonb'])+')',read_only=False)
 saved=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(record['id'])+'::uuid')[0];assert saved==dict(sha256=sha,byte_count=len(raw))
 report['evidence']=dict(artifact_id=record['id'],sha256=sha,retrieved_sha256=r.sha(restored),bytes=len(raw),public=False)
 release.save(ROOT/'docs/assessment-4055396e-recovery-validation-v1.json',report)
 print(json.dumps(dict(status=report['status'],checks={k:v for k,v in report['checks'].items() if k in ('backend_tests','frontend_tests','infrastructure_tests')},evidence=report['evidence'],budget=report['budget'])))
if __name__=='__main__':main()
