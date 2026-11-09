"""Fixed original invalid controller response; passive and credential free.

Private original bytes stay in ignored artifacts. No archive source is executed,
no provider call is replayed, and no database/assessment state is changed.
"""
import importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACK=ROOT.parent/'jumpserve-back-end'
sys.path[:0]=[str(BACK),str(BACK/'research_workflow')]
import dispatch_recovery as recovery
from workflow import digest
from platform_supervisor import incident_evidence,repair

def main():
 base=ROOT/'.test-artifacts/controller-terminal-v1'
 hashes={
  'logical.json':'ff885e2cff72fd2db7c03c89d44ae566dba34b3b5dc1a10140520df177eb033c',
  'provider-request.json':'247f185d1afdee104763e5e87dd5d39b7feb37c544dd9d84a24a043cdad34ddb',
  'provider-response.bin':'783e3aec47f4bd88e59ff33e295684962daf6f16ee8b1861df580f6121b8941a',
  'receipt.json':'de8d3471da419c463fd2254a4fa2a6635584406647e8f3a9a3b1f62e9056b222'}
 originals={name:(base/name).read_bytes() for name in hashes}
 assert all(digest(raw)==hashes[name] for name,raw in originals.items())
 d=json.loads((base/'dispatch.json').read_bytes());assert d['id']=='970716c3-1869-5ee9-a4bf-8bf6c92c70d7'
 assert d['study_id']=='444d171c-2fac-4ba9-b33c-2b46304cb0ec' and d['task_id']=='e2ea52ec-858b-5847-9b44-b945d903990a'
 task=dict(id=d['task_id'],study_id=d['study_id']);receipt=json.loads(originals['receipt.json'])
 refs={r['id']:r for r in d['provenance']['artifacts'] if r.get('name') in hashes}
 def original(t,p,maximum=150000):
  assert t==task
  r=refs[p.get('id') or p.get('artifact_id')];raw=originals[r['name']]
  assert len(raw)<=maximum and digest(raw)==p['sha256']==hashes[r['name']]
  return raw
 proof=recovery.controller_terminal(task,d,receipt,original,lambda *a,**k:[])
 assert proof and proof['provider_calls']==1 and proof['decision_accepted'] is False
 view=incident_evidence.controller_response_view(originals['provider-response.bin'])
 assert view['terminal_complete'] and view['decision_valid'] is False
 assert view['terminal_sha256']==proof['terminal_sha256']
 projected,_=repair._project(view);assert projected['original_sha256']==hashes['provider-response.bin']
 # Removing the terminal event must never turn HTTP 200 into completion proof.
 import io,time,siwc_protocol as wire
 try:wire.read_stream(io.BytesIO(b'data: {"type":"response.created"}\n\n'),io.BytesIO(),time.monotonic()+1,1048576)
 except (ValueError,KeyError,TypeError):pass
 else:raise AssertionError('Incomplete stream accepted')
 # Compare current changes to exact committed baseline and immutable source pin.
 spec=importlib.util.spec_from_file_location('terminal_scope',ROOT/'assets/platform/research-runtime-gate.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());before=base/'baseline/research_workflow'
 if (BACK/'.git').exists():
  names=list(manifest['files'])
  names+=subprocess.check_output(['git','ls-tree','-r','--name-only',manifest['source_revision'],'research_workflow'],cwd=BACK,text=True).splitlines()
  names=[n.removeprefix('research_workflow/') for n in names]
  for name in names:
   path=before/name;path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(subprocess.check_output(['git','show',manifest['source_revision']+':research_workflow/'+name],cwd=BACK))
 else:
  # Isolated qualification receives the same committed baseline as immutable
  # source-packet members, without a Git checkout or publisher credential.
  index=json.loads((base/'baseline-manifest.json').read_bytes())
  assert index['source_revision']==manifest['source_revision']
  for name,h in index['files'].items():
   assert not Path(name).is_absolute() and '..' not in Path(name).parts
   assert digest((before/name).read_bytes())==h
  assert all(index['files'][n]==h for n,h in manifest['files'].items())
 scope=gate.inspect(before,BACK/'research_workflow',manifest)
 report=dict(version='controller-terminal-retained-control-v1',passed=True,originals=hashes,
  terminal_complete=True,decision_accepted=False,original_provider_calls=1,new_provider_calls=0,production_mutations=0,
  changed_runtime_files=scope['changed_files'],scientific_and_request_content_unchanged=scope['scientific_and_request_content_unchanged'],
  existing_tests_unchanged=scope['existing_tests_unchanged'],source_binding=scope['source_binding'],
  reviewer='Primary implementing AI; not independent',scope='Software-only retained original and source-bound checks. No production qualification, resumption or scientific completion claim.')
 (base/'retained-control-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
