"""Record fixed local repair qualification; no credentials, network or deployment."""
import datetime as dt,hashlib,io,json,pathlib,re,subprocess,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
 out=ROOT/'.test-artifacts/autonomous-repair-local'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 backend=BACK/'.test-artifacts/autonomous-repair-backend-tests-v3.log';frontend=FRONT/'.test-artifacts/autonomous-repair-frontend-tests-v2.log';infra=ROOT/'.test-artifacts/autonomous-repair-infra-tests-v3.log'
 assert 'Ran 363 tests' in backend.read_text() and '\nOK\n' in backend.read_text()
 assert 'pass 275' in frontend.read_text() and 'fail 0' in frontend.read_text()
 assert '93 passed' in infra.read_text() and '5 skipped' in infra.read_text() and not re.search(r'\d+ failed',infra.read_text())
 sqls=sorted((ROOT/'.test-artifacts/research-ideas/database').glob('*/autonomous-repair-report.json'));sql=json.loads(sqls[-1].read_bytes());assert sql['passed'] and len(sql['checks'])==4
 native_path=sorted((BACK/'.test-artifacts/repair-validation-linux').glob('*/report.json'))[-1];native=json.loads(native_path.read_bytes());assert native['passed'] and len(native['checks'])==5 and not native['production_image_tested']
 browser_path=FRONT/'.test-artifacts/public-experiment-queue/2026-10-28T23-47-51.628Z/report.json';browser=json.loads(browser_path.read_bytes());assert browser['passed'] and len(browser['checks'])==19
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert manifest['version']==58 and manifest['source_dirty'] and len(manifest['files'])==53
 for name,digest in manifest['files'].items():assert sha((BACK/'research_workflow'/name).read_bytes())==digest
 assert not json.loads((BACK/'research_workflow/policies/autonomous-repair-release-v1.json').read_bytes())['approved_for_lab_recovery']
 files={};sources={}
 groups={
  'backend':(BACK,['research_workflow/'+n for n in ('autonomous_repair.py','autonomy.py','autonomy_inputs.py','autonomy_model.py','experiment_builder.py','repair_validation.py','scheduler.py','store.py','policies/autonomous-repair-release-v1.json','tests/test_autonomous_repair.py','tests/check_repair_validation_linux.py','tests/public_queue_fixture.py')]),
  'frontend':(FRONT,['app/components/research-workflow/autonomous-assessments.tsx','lib/research-autonomy.ts','lib/research-public-queue.ts','scripts/verify-public-experiment-queue.mjs','tests/research-autonomy.test.mjs','tests/research-public-queue.test.mjs']),
  'infrastructure':(ROOT,['database/202610280004_autonomous_repair.sql','lib/research-workflow.ts','research-workflow-runtime.json','package.json','test/check_research_ideas_database.py','test/check_autonomous_repair_database.py','test/network-execution.test.ts','bin/research-queue-release.py','bin/record-autonomous-repair-local.py','docs/autonomous-repair-protocol-v1.json','docs/autonomous-repair-live-protocol-v1.json'])}
 for group,(base,names) in groups.items():
  sources[group]=dict(base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=base,text=True).strip(),working_tree_files={n:sha((base/n).read_bytes()) for n in names})
  for name in names:files[group+'/'+name]=(base/name).read_bytes()
 for path in (backend,frontend,infra,ROOT/'.test-artifacts/autonomous-repair-infra-tests-v1.log',ROOT/'.test-artifacts/autonomous-repair-infra-tests-v2.log',ROOT/'.test-artifacts/autonomous-repair-infra-build-v1.log',ROOT/'.test-artifacts/autonomous-repair-infra-build-v2.log',ROOT/'.test-artifacts/autonomous-repair-infra-targeted-final.log',FRONT/'.test-artifacts/autonomous-repair-build-v1.log'):
  files['logs/'+path.name]=path.read_bytes()
 for path in sqls:
  for p in path.parent.iterdir():
   if p.is_file() and (p.name=='autonomous-repair-report.json' or p.name.startswith('raw-')):files['database/'+path.parent.name+'/'+p.name]=p.read_bytes()
 for base,label in ((native_path.parent,'linux'),(browser_path.parent,'browser')):
  for p in base.rglob('*'):
   if p.is_file():files[label+'/'+str(p.relative_to(base))]=p.read_bytes()
 report=dict(version='autonomous-repair-local-status-v1',recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),status='implemented-locally;live-qualification-and-release-pending',sources=sources,
  checks=dict(backend=363,frontend=275,infrastructure=93,optional_infrastructure_skipped=5,infrastructure_targeted_final=6,isolated_postgres_checks=4,linux_controls=5,linux_actual_successful_fixture=1,linux_expected_rejections=4,browser_checks=19,desktop_mobile_light_dark=True,visual_inspection='Implementing AI inspected mobile light and desktop dark captures.',lint_and_build_types='passed'),
  implementation=['Durable service-only repair incidents and immutable event history, using existing claim leases and authorization.','Automatic diagnosis and original-identity reconciliation; uncertain outcomes remain fenced with backoff.','Hash-verified native diagnosis delivery with labeled/redacted original log excerpts and unchanged admitted requests.','Exact logical/provider-wire preflight, scoped retrievable executable contracts and retained source/turn references.','Native experiment-code repair with incident-bound executed software checks, frozen package identity and fresh scientific reviews.','Public/owner queue progress and bounded shared repair incident/event history.'],
  limits=dict(application_default_usd=100,existing_assessment_cap_unchanged=True,deadline_and_prior_commitments_preserved=True,ai_turn_cap=None,new_live_model_calls=0,new_cloud_experiment_instances=0,new_scientific_measurements=0,production_writes=0,deployed=False,measured_charges_usd=None,unallocated_local_compute_storage_cost_usd=None),
  evaluator=dict(identity='Implementing Codex assistant',type='AI',independent=False,human=False,held_out=False),
  gaps=['Live actual-answer OpenClaw repair qualification has not run; exact-source activation approval remains false.','The real Docker control used cached local image '+native['image']+'; the production image was not available locally.','No production migration, runtime rollout, authenticated repair request or Supabase Storage round trip was performed.','General global application/infrastructure self-patching is outside experiment-worker authority.','Unavailable apparatus/data/authorization or an irreconcilable provider outcome can still prevent results; scientific findings are never forced.','AI-authored software tests and source inspection do not establish independent correctness or scientific validation.'],
  retained_failures=[dict(report=str(p.relative_to(ROOT)),reason=json.loads(p.read_bytes()).get('error')) for p in sqls if not json.loads(p.read_bytes()).get('passed')],
  commands=['python3 -B -m unittest discover -s research_workflow/tests -p test_*.py (backend)','npm test (frontend)','npm run test:research:repair (infrastructure; isolated local Postgres)','python3 -B research_workflow/tests/check_repair_validation_linux.py (backend; cached local image only)','npm run verify:research:public-queue (frontend; local synthetic API)','npm test -- --runInBand (infrastructure)'])
 files['local-status.json']=json.dumps(report,sort_keys=True,separators=(',',':')).encode();buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for n,raw in sorted(files.items()):z.writestr(n,raw)
  z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())]))
 raw=buffer.getvalue();path=out/'evidence.zip';path.write_bytes(raw);restored=path.read_bytes();assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as z:
  assert z.testzip() is None
  for entry in json.loads(z.read('artifact-manifest.json')):assert sha(z.read(entry['path']))==entry['sha256'] and len(z.read(entry['path']))==entry['bytes']
 report['evidence']=dict(path=str(path.relative_to(ROOT)),sha256=sha(raw),retrieved_sha256=sha(restored),bytes=len(raw),members=len(files),remote_storage_verified=False)
 (ROOT/'docs/autonomous-repair-local-status-v1.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],checks=report['checks'],evidence=report['evidence'],deployed=False)))
if __name__=='__main__':main()
