"""Seal local budget-mode evidence only; no cloud, database or model calls."""
import datetime as dt,hashlib,io,json,pathlib,re,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
sha=lambda value:hashlib.sha256(value).hexdigest()
def main():
 sql='database/202610300001_optional_assessment_budget.sql';migration=(ROOT/sql).read_bytes()
 reports=sorted((ROOT/'.test-artifacts/research-ideas/database').glob('*/optional-budget-report.json'));passed=[p for p in reports if json.loads(p.read_bytes()).get('passed') and json.loads(p.read_bytes())['migration_sha256'].get(pathlib.Path(sql).name)==sha(migration)]
 assert passed,'Current migration must pass the isolated database checks';selected=passed[-1]
 back=(BACK/'.test-artifacts/optional-budget-unit.log').read_bytes();front=(FRONT/'.test-artifacts/optional-budget-tests.log').read_bytes();build=(FRONT/'.test-artifacts/optional-budget-build.log').read_bytes();roundtrip=(FRONT/'.test-artifacts/optional-budget-public-roundtrip.log').read_bytes()
 assert b'\nOK\n' in back and b'\nFAILED ' not in back and b'fail 0' in front and b'Compiled successfully' in build and b'"passed":true' in roundtrip
 backend_count=int(re.search(rb'Ran (\d+) tests',back)[1]);frontend_count=int(re.search(rb'tests (\d+)',front)[1])
 files={sql:migration,'backend-unit.log':back,'frontend-tests.log':front,'frontend-build.log':build,'public-roundtrip.log':roundtrip}
 names={ROOT:['bin/retain-optional-budget-local.py','test/check_optional_budget_database.py','docs/optional-assessment-budget-v1.md'],BACK:['research_workflow/autonomy.py','research_workflow/autonomy_model.py','research_workflow/paper_uploads.py','research_workflow/tests/test_optional_budget.py'],FRONT:['lib/research-autonomy.ts','lib/research-public-queue.ts','lib/research-paper-review.ts','app/components/research-workflow/autonomous-assessments.tsx','tests/research-autonomy.test.mjs','tests/research-public-queue.test.mjs','tests/research-paper-review.test.mjs']}
 for root,paths in names.items():
  for name in paths:files[root.name+'/'+name]=(root/name).read_bytes()
 for p in reports:files['database/'+p.parent.name+'/'+p.name]=p.read_bytes()
 for p in (ROOT/'.test-artifacts/research-ideas/database').glob('*/reconciled-resume-failure.json'):files['database/'+p.parent.name+'/'+p.name]=p.read_bytes()
 files['database/public-unlimited-queue.json']=(selected.parent/'public-unlimited-queue.json').read_bytes()
 manifest=[dict(path=n,sha256=sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())];files['artifact-manifest.json']=json.dumps(manifest,sort_keys=True).encode()
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,raw in sorted(files.items()):archive.writestr(name,raw)
 directory=ROOT/'.test-artifacts/optional-budget-local-v1'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True);path=directory/'evidence.zip';raw=stream.getvalue();path.write_bytes(raw);path.chmod(0o600);restored=path.read_bytes();assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as archive:
  for item in json.loads(archive.read('artifact-manifest.json')):assert sha(archive.read(item['path']))==item['sha256']
 report=dict(version='optional-assessment-budget-local-v1',status='local-verified-production-unchanged',assessment_id='4055396e-35c0-4962-ba39-cf23e443ad8d',recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),operator_request="Let's make the budget unlimited for now.",scope='This assessment only; $100 new-assessment default unchanged.',backend_tests=backend_count,frontend_tests=frontend_count,frontend_build='passed',database_report=json.loads(selected.read_bytes()),actual_public_api_frontend_validation='passed',new_provider_calls=0,new_cloud_instances=0,production_changes=0,measured_charges_usd=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False),evidence=dict(path=str(path.relative_to(ROOT)),sha256=sha(raw),retrieved_sha256=sha(restored),bytes=len(raw),members=len(files),storage='local only; Supabase retention pending release'),conditional_gaps=['Compatible database/backend/frontend release and exact-source runtime qualification','Applied operator authorization and live resumption','Deployed desktop/mobile unlimited-budget display'])
 (ROOT/'docs/optional-assessment-budget-local-v1-status.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],evidence=report['evidence'],backend_tests=backend_count,frontend_tests=frontend_count)))
if __name__=='__main__':main()
