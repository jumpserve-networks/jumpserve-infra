"""Seal fixed local software checks, originals, amendments and failed replays."""
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def main():
    units=BACK/'.test-artifacts/builder-stall-fix-unit-final.log';infra=ROOT/'.test-artifacts/builder-stall-fix-infra-tests.log';build=ROOT/'.test-artifacts/builder-stall-fix-infra-build.log'
    assert re.search(r'Ran 388 tests',units.read_text()) and '\nOK\n' in units.read_text() and 'FAILED (' not in units.read_text()
    assert '94 passed' in infra.read_text() and '5 skipped' in infra.read_text() and 'tsc' in build.read_text()
    native_path=BACK/'.test-artifacts/experiment-builder/20261029T235305240344Z/report.json';native=json.loads(native_path.read_bytes());assert native['status']=='passed' and native['retained_paper']['status']=='passed' and native['retained_paper']['live_provider_calls']==0
    for name,record in native['source_files'].items():assert sha((BACK/'research_workflow'/name).read_bytes())==record['sha256'],'Native check source changed: '+name
    replays=sorted((ROOT/'.test-artifacts/builder-stall-fix').glob('*/report.json'));replay=json.loads(replays[-1].read_bytes());assert replay['status']=='passed' and len(replay['cases'])==5
    for name,h in replay['source_files'].items():assert sha((BACK/'research_workflow'/name).read_bytes())==h
    assert all(c['fresh_packet_request_bytes']<72000 for c in replay['cases']) and sum(c['historical_counterfactual_fits'] for c in replay['cases'])==4
    changed=['autonomous_repair.py','autonomy.py','autonomy_costs.py','autonomy_inputs.py','experiment_builder.py','netem_iperf.py','network_spec.py','policies/autonomous-repair-release-v1.json','policies/netem-iperf-costs-v2.json','policies/builder-stall-fix-validation-v1.json','policies/builder-stall-fix-validation-v2.json','tests/test_builder_work_packet.py','tests/check_experiment_builder_linux.py']
    assert json.loads((BACK/'research_workflow/policies/autonomous-repair-release-v1.json').read_bytes())['approved_for_lab_recovery'] is False
    assert json.loads((BACK/'research_workflow/policies/netem-iperf-costs-v2.json').read_bytes())['approved_for_lab_execution'] is False
    files={'backend/research_workflow/'+name:(BACK/'research_workflow'/name).read_bytes() for name in changed}
    for name in ('lib/research-workflow.ts','test/research-workflow.test.ts','bin/check-builder-stall-fix-local.py','bin/record-builder-stall-fix-local.py'):files[name]=(ROOT/name).read_bytes()
    for path in (units,infra,build,native_path):files['reports/'+path.name]=path.read_bytes()
    for directory in (native_path.parent,*[p.parent for p in replays]):
        root=BACK if directory.is_relative_to(BACK) else ROOT
        for path in directory.rglob('*'):
            # Native state databases, caches and bridge configuration are not
            # research evidence or portable implementation sources. Requests,
            # responses, captured checkpoints and producer sources are retained.
            if path.is_symlink() or not path.is_file() or path.name=='config.json' or any(p in ('state','node-compile-cache','.cache','.openclaw') for p in path.relative_to(directory).parts):continue
            files[('backend/' if root==BACK else '')+str(path.relative_to(root))]=path.read_bytes()
    native_summary=dict(image=native['image'],platform='linux/arm64',legacy_slots=3,retained_paper=native['retained_paper'],live_provider_calls=0,scope='Actual local CLI/container, synthetic model plan. Production Linux/amd64 qualification and autonomous model behavior remain unverified.')
    report=dict(version='builder-stall-fix-local-v1',recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),status='implemented-and-locally-verified;release-pending',protocols=['builder-stall-fix-validation-v1','builder-stall-fix-validation-v2'],checks=dict(backend_tests=388,infrastructure_tests=94,existing_infrastructure_skips=5,typescript_build='passed',native=native_summary,counterfactual=replay),source_files={k:sha(v) for k,v in files.items() if not k.startswith(('reports/','.test-artifacts/','backend/.test-artifacts/'))},new_live_model_calls=0,new_scientific_experiments=0,production_execution_or_configuration_changes=0,merged=False,deployed=False,measured_charges_usd=None,subscription_allocation_usd=None,storage_charges_usd=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False),remaining=['Exact production linux/amd64 platform qualification with changed sources','Frozen bounded live full-paper-context model evaluation; model selection of implementation and actual candidate/job/measurement ingestion are unverified','New committed runtime pin including netem-iperf-costs-v2.json; historical v1 and current manifest remain unchanged','Publish only exact-source passing repair/resource policy approvals during a separately authorized release','No frontend or SQL schema changes; browser/auth/database/deployed checks were not rerun for this local-only change'],retained_failed_replays=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p.read_bytes()),status=json.loads(p.read_bytes())['status']) for p in replays if json.loads(p.read_bytes())['status']!='passed'],scientific_scope='These are software regressions and counterfactual payload checks. No paper claim has been reclassified, source setting changed or scientific measurement collected. Reused/tuned cases are not held-out validation.')
    files['local-report.json']=json.dumps(report,sort_keys=True,separators=(',',':')).encode()
    out=ROOT/'.test-artifacts/builder-stall-fix-sealed'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):z.writestr(name,raw)
        z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())]))
    raw=stream.getvalue();assert len(raw)<20000000;(out/'evidence.zip').write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO((out/'evidence.zip').read_bytes())) as z:
        for entry in json.loads(z.read('artifact-manifest.json')):assert sha(z.read(entry['path']))==entry['sha256']
    report['evidence']=dict(path=str((out/'evidence.zip').relative_to(ROOT)),sha256=sha(raw),bytes=len(raw),members=len(files),remote_storage_verified=False)
    (ROOT/'docs/builder-stall-fix-local-status-v1.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],backend_tests=388,infrastructure_tests=94,evidence=report['evidence'])))


if __name__=='__main__':main()
