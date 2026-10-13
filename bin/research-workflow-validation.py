"""Archive this local implementation's receipts and original-byte manifests; no cloud calls."""
from pathlib import Path
import datetime as dt
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT.parent/'jumpserve-front-end';BACK=ROOT.parent/'jumpserve-back-end'
DEST=ROOT/'docs/research-workflow-validation';REPORT=ROOT/'docs/research-workflow-validation-v1.json'
STAMP='2026-10-07T16-06-53.053Z'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def main():
    if REPORT.exists():raise SystemExit('Preserve validation v1; create a new version for later evidence.')
    DEST.mkdir(exist_ok=True);manifest=[]
    def keep(path,name=None):
        raw=path.read_bytes();target=DEST/(name or path.name)
        if target.exists():
            if target.read_bytes()!=raw:raise RuntimeError('Evidence version changed: '+str(target))
        else:
            with target.open('xb') as stream:stream.write(raw)
        assert sha(target.read_bytes())==sha(raw)
        manifest.append(dict(path=str(target.relative_to(ROOT)),original_path=str(path.relative_to(ROOT.parent)),sha256=sha(raw),bytes=len(raw),round_trip_hash_verified=True))
    for file in sorted((FRONT/'.test-artifacts/research-workflow').glob('*browser-report.json')):keep(file)
    files=[(ROOT/'.test-artifacts/research-workflow-database-final.json','database-final-v1.json'),(ROOT/'.test-artifacts/research-workflow-infra-final-tests.txt','infra-tests-final-v1.txt'),(FRONT/'.test-artifacts/research-workflow/frontend-final-build.txt','frontend-build-final-v1.txt'),(FRONT/'.test-artifacts/research-workflow/npm-audit-v1.json','npm-audit-v1.json'),(BACK/'.test-artifacts/research-workflow/backend-final-tests.txt','backend-tests-final-v1.txt')]
    files += [(BACK/'.test-artifacts/research-workflow'/name,None) for name in ('workflow-example-protocol-v1.json','workflow-example-frozen-v1.json','workflow-example-results-v1.json','workflow-example-results-v2.json')]
    files.append((FRONT/'.test-artifacts/research-workflow'/f'{STAMP}-ipv6-public.json','ipv6-register-public-fixture-v1.json'))
    files += [(FRONT/'.test-artifacts/research-workflow'/f'{STAMP}-{suffix}',suffix) for suffix in ('desktop-comparisons-dark.png','mobile-plot-light.png','mobile-comparisons-dark.png','desktop-ipv6-gaps.png')]
    for source,name in files:keep(source,name)
    browser=json.loads((DEST/f'{STAMP}-browser-report.json').read_bytes());database=json.loads((DEST/'database-final-v1.json').read_bytes());example=json.loads((DEST/'workflow-example-results-v2.json').read_bytes())
    assert browser['passed'] and database['passed']
    assert sha(canonical({k:v for k,v in example.items() if k!='run'}))==example['run']['output_sha256']
    assert example['run']['provenance']['implementation_sha256']==sha((BACK/'research_workflow/runner.py').read_bytes())
    assert 'Ran 34 tests' in (DEST/'backend-tests-final-v1.txt').read_text() and 'OK' in (DEST/'backend-tests-final-v1.txt').read_text()
    assert '77 passed' in (DEST/'infra-tests-final-v1.txt').read_text() and 'Compiled successfully' in (DEST/'frontend-build-final-v1.txt').read_text()
    packet=BACK/'.test-artifacts/research-workflow/workflow-paper-text-v1.json';text=json.loads(packet.read_bytes())
    private=[dict(path=str(packet.relative_to(ROOT.parent)),sha256=sha(packet.read_bytes()),bytes=packet.stat().st_size,visibility='Ignored local unreviewed text packet; not included in public report files')]
    paths=list((BACK/'research_workflow').rglob('*'))
    for folder in ('app/components/research-workflow','app/module/research-verification'):paths.extend((FRONT/folder).rglob('*'))
    paths.extend(FRONT/name for name in ('lib/research-workflow.ts','lib/research-workflow-api.ts','lib/research-workflow-server.ts','lib/test-modules.ts','package.json','package-lock.json','scripts/verify-research-workflow.mjs','tests/research-workflow.test.mjs'))
    paths.extend(ROOT/name for name in ('database/202610070001_research_workflow.sql','lib/research-workflow.ts','lib/benchmark-orchestrator-stack.ts','test/research-workflow.test.ts','test/check_research_workflow_database.py','test/serve_research_workflow_fixture.py','bin/research-workflow-database.py','bin/prepare-research-runtime.py','bin/research-workflow-validation.py','research-workflow-runtime.json'))
    code=[dict(path=str(p.relative_to(ROOT.parent)),sha256=sha(p.read_bytes()),bytes=p.stat().st_size) for p in sorted(set(paths)) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    report=dict(version=1,recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),implementation_status='Implemented and locally verified; not deployed',protocols=['docs/research-workflow-implementation-v1.md','docs/research-workflow-amendment-v2.md','docs/research-workflow-amendment-v3.md'],reviewer=dict(identity='Primary Codex assistant',type='AI',independence='Implementer; not independent; no human review asserted',expertise='Software implementation; no specialist scientific review asserted'),design='Development regressions and reused fixtures; not independent held-out science or model validation.')
    report['local_release_blockers']={
      'backend':dict(passed=True,command='python3 -B -m unittest discover -s research_workflow/tests -v',tests=34,wall_seconds=0.068),
      'frontend':dict(passed=True,tests=117,test_command='npm test',lint_command='npm run lint',lint_exit_code=0,build_command='NEXT_PUBLIC_RESEARCH_WORKFLOW_API_URL=http://127.0.0.1:4102 npm run build',build_exit_code=0,compile_seconds=2.6,limitation='Fixture origin embedded for local verification; rebuild with production API origin before release. Standalone original-byte test/lint stdout was not retained; successful results are in execution history.'),
      'infrastructure':dict(passed=True,build_command='npm run build',build_exit_code=0,test_command='npm test -- --runInBand',passed_tests=77,skipped_tests=5,seconds=2.671,skip_reason='Existing benchmark CLI cases require JUMPSERVE_BACKEND_CHECKOUT; this optional environment was unset. Separate from research workflow checks.',runtime_manifest='research-workflow-runtime.json',deployment_flag='Boolean true or exact CLI string true; defaults off'),
      'database':dict(passed=True,engine='PostgreSQL 17',isolated_database=database['database'],migration='database/202610070001_research_workflow.sql',check_groups=len(database['checks']),relations=18,rolled_back=True,limitation='Actual local SQL/RLS with modeled Supabase storage tables; not live Supabase Storage API verification.'),
      'browser':dict(passed=True,checks=len(browser['checks']),command='npm run verify:research',playwright='1.62.1',browser='Installed Google Chrome',viewports=[dict(width=1365,height=900),dict(width=390,height=844)],themes=['light','dark'],console_errors=browser['browser_errors'],report=f'docs/research-workflow-validation/{STAMP}-browser-report.json',transport='Actual public api.handler + store.snapshot; only persistence transport replaced by isolated Postgres role anon. Invalid/unavailable transport responses explicitly injected.',visual_inspection='Settled desktop/mobile screenshots inspected by AI implementer; not human review.'),
      'provenance':dict(passed=True,copied_artifact_hashes_verified=True,runtime_files_verified=True,example_payload_output_hash_verified=True,public_exports_exclude_private_artifacts_owners_audit_actors=True)}
    report['scientific_coverage']=dict(new_paper_experiments=False,original_ipv6_assessment_sha256=database['original_assessment_sha256'],imported_sources=74,claims=15,preserved_labels=dict(reproduced=3,discrepant=3,inconclusive=5,untested=4),current_gap_records=9,new_shared_measurements_for_ipv6=0,assessment_changes='None; register import does not strengthen or resolve findings.',test_data='Synthetic numerical and review fixtures, not new paper evidence.',method_scope='Registered matched-numeric-v1 arithmetic; other domains need appropriate implementations or documented external campaigns and substantive review.',ai_scope='Existing study chats linked; no generic prompt/candidate/tools evaluated or published.')
    report['conditional_verification_gaps']=[
      'Production schema/API/frontend deployment not requested or performed this turn.',
      'AWS account and Supabase project are guarded in code/configuration. Live target identity checks occur before an authorized production change; not performed this turn.',
      'No legitimate Google browser session: actual owner intake/write/run/publication and authenticated chat requests unverified. Auth/ownership development cases use mocked auth responses.',
      'No remote Supabase Storage upload/retrieval; actual remote artifact hash checks and deployed latency/timeouts unverified.',
      'Storage outages or Lambda termination cannot guarantee durable failed-run recording; preserve original requests and retry identical IDs.',
      'No independent/human domain review or held-out/model-answer evaluation.',
      'Existing dependency advisories remain: npm audit lists 29 entries (1 low,6 moderate,20 high,2 critical). All affected package paths are unchanged from baseline; new Playwright packages have no listed advisory. This is not a complete security assessment.']
    report['failure_history']=[
      dict(case='Initial SQL qualification',result='Variable naming corrected before successful SQL checks.',original_stdout_sha256=None),
      dict(case='Initial frontend lint',result='Eight native select/table violations corrected to shared components.',original_stdout_sha256=None),
      dict(case='Browser environment and readiness',result='Sandbox launch, wrong label, dev overlay, network-idle and kept-mounted popup assumptions failed. Timestamped original-byte reports retained; corrected verifier passes.'),
      dict(case='Browser fixture seeding',result='Empty sourced claims and object-valued evidence rejected by SQL; corrected isolated fixtures preserve interrupted records and new synthetic reviews. Never production publication.',original_stdout_sha256=None),
      dict(case='PDF output directory',result='Initial attempt failed before an audit could be saved; handling corrected. Actual 22-page extraction succeeded.',original_stdout_sha256=None),
      dict(case='Artifact replay fixture',result='Different study path correctly rejected; fixture corrected to original study. Final backend suite passes.',original_stdout_sha256=None),
      dict(case='Validation receipt generation',result='Initial in-memory draft had an unmatched parenthesis and did not execute. This purpose-specific generator validates receipts and preserves original copies.',original_stdout_sha256=None)]
    report['usage']=dict(measured_example_usage=example['run']['usage'],pdf_text_extraction=dict(original_bytes=text['original_bytes'],pages=len(text['pages']),wall_seconds=text['usage']['wall_seconds'],parser='pypdf '+text['tool_version'],substantive_review='retrieved-unreviewed'),final_browser_wall_seconds=(dt.datetime.fromisoformat(browser['ended_at'].replace('Z','+00:00'))-dt.datetime.fromisoformat(browser['started_at'].replace('Z','+00:00'))).total_seconds(),preserved_public_validation_artifact_bytes=sum(row['bytes'] for row in manifest),private_local_artifact_bytes=sum(row['bytes'] for row in private),measured_charges_usd=None,estimated_charges_usd=None,codex_model_usage=None,model_evaluation_calls=0,new_aws_experiment_instances=0,unallocated_costs='Local compute/storage, Codex usage and incidental hosting requests not billed/reconciled. Missing charges are not zero.')
    report.update(artifacts=manifest,private_artifacts=private,implementation_byte_manifest=code,release_status='Local checks pass under documented fixtures. Production awaits explicit authorization and conditional checks. Scientific coverage remains limited.',cleanup='Only workflow test services stopped; isolated Postgres/evidence files retained. User-staged PDFs unchanged.')
    with REPORT.open('x') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(REPORT),copied_artifacts=len(manifest),hashed_implementation_files=len(code),preserved_bytes=report['usage']['preserved_public_validation_artifact_bytes'],local_checks_passed=True,deployed=False),indent=2))
if __name__=='__main__':main()
