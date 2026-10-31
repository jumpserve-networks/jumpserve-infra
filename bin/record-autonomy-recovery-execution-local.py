"""Retain fixed local qualification evidence. No inference or remote writes."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1];BACKEND=ROOT.parent/'jumpserve-back-end'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def latest(pattern,predicate=lambda r:True):
 found=[]
 for path in ROOT.glob(pattern):
  value=json.loads(path.read_bytes())
  if value.get('passed') and predicate(value):found.append((path,value))
 if not found:raise ValueError('Required passing local evidence is unavailable: '+pattern)
 return sorted(found,key=lambda p:str(p[0]))[-1]

def main():
 migrations={p.name:sha(p.read_bytes()) for p in [ROOT/'database/202610300002_native_call_reconciliation.sql',ROOT/'database/202610300003_research_append_normalization.sql']}
 builder,builder_report=latest('.test-artifacts/research-ideas/database/*/report.json',lambda r:r.get('protocol')=='experiment-builder-validation-v1' and all(r.get('migration_sha256',{}).get(k)==v for k,v in migrations.items()))
 completion,completion_report=latest('.test-artifacts/research-ideas/database/*/autonomy-completion-report.json',lambda r:r.get('restart',{}).get('real_process_restart') and all(r.get('migration_sha256',{}).get(k)==v for k,v in migrations.items() if 'normalization' in k))
 persistence,persistence_report=latest('.test-artifacts/research-ideas/database/*/netem-persistence-report.json',lambda r:r.get('readback',{}).get('measurements')==75 and r.get('migration_sha256',{}).get('202610300003_research_append_normalization.sql')==migrations['202610300003_research_append_normalization.sql'])
 live=BACKEND/'.test-artifacts/native-repair-handoff/retained-review-460ab36d272b4300b7ec03cab314a50d.json';live_report=json.loads(live.read_bytes());assert live_report['status']=='passed' and live_report['aggregate_actual_provider_calls']==22
 grid_selection=json.loads((BACKEND/'.test-artifacts/executable-methods/linux/full-grid-selected.json').read_bytes());grid=Path(grid_selection['directory']);assert sha((grid/'report.json').read_bytes())==grid_selection['report_sha256'];grid_report=json.loads((grid/'report.json').read_bytes());assert grid_report['passed'] and grid_report['observations']==75
 synthetic=BACKEND/'.test-artifacts/native-repair-handoff/20261030T231417869681Z';assert json.loads((synthetic/'report.json').read_bytes())['status']=='passed'
 out=ROOT/'.test-artifacts/autonomy-recovery-execution-v1'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
 files={}
 def include(path,label):
  if path.is_symlink():raise ValueError('Evidence must not follow symlinks.')
  if path.is_file():files[label]=path.read_bytes()
 def tree(directory,label):
  excluded={'state','home','node_modules','__pycache__','node-compile-cache','compile-cache','.cache'}
  for folder,directories,names in os.walk(directory,followlinks=False):
   directories[:]=sorted(d for d in directories if d not in excluded and not (Path(folder)/d).is_symlink())
   for name in sorted(names):
    path=Path(folder)/name
    if name=='config.json':continue
    if path.is_file():include(path,label+'/'+path.relative_to(directory).as_posix())
 source_paths=[*sorted((BACKEND/'research_workflow').glob('*.py')),*sorted((BACKEND/'research_workflow/policies').glob('*.json')),BACKEND/'research_workflow/experiment-builder.Dockerfile']
 source_paths+=[BACKEND/'research_workflow/tests'/name for name in ('build_experiment_builder_image.py','check_native_repair_handoff_linux.py','check_netem_iperf_linux.py','test_native_repair_handoff.py','test_dispatch_recovery.py','test_network_execution.py','test_autonomous_repair.py','test_autonomy_followups.py')]
 source_paths+=[ROOT/'database'/name for name in migrations]
 source_paths+=[ROOT/'test'/name for name in ('check_autonomy_completion_database.py','check_experiment_builder_database.py','check_research_ideas_database.py','check_netem_measurement_persistence.py')]
 source_paths+=[*[p for p in sorted((ROOT/'docs').glob('autonomy-recovery-execution-*.json')) if not p.name.endswith('-status.json')],ROOT/'docs/autonomy-recovery-execution-v1.md',ROOT/'package.json',Path(__file__)]
 source_inventory={}
 for path in source_paths:
  repo=BACKEND if path.is_relative_to(BACKEND) else ROOT;label='source/'+repo.name+'/'+path.relative_to(repo).as_posix();include(path,label);source_inventory[label]=dict(sha256=sha(files[label]),bytes=len(files[label]))
 for name in ('20261030T230421562931Z','20261030T230544880097Z','20261030T230853018072Z','20261030T231115228195Z',synthetic.name):tree(BACKEND/'.test-artifacts/native-repair-handoff'/name,'native/'+name)
 include(live,'native/'+live.name);tree(grid,'linux-grid');include(BACKEND/'.test-artifacts/builder-image/selected-linux-amd64.json','image/selected-linux-amd64.json')
 for report in (builder,completion,persistence):tree(report.parent,'database/'+report.parent.name)
 # Failed database reports remain separate evidence; only these fixed task
 # protocols and this task's UTC range are eligible, never unrelated papers.
 for directory in sorted((ROOT/'.test-artifacts/research-ideas/database').iterdir()):
  if directory.name<'20261030T230326':continue
  for name in ('netem-persistence-report.json','autonomy-completion-report.json','report.json'):
   path=directory/name
   if not path.is_file():continue
   value=json.loads(path.read_bytes())
   if not value.get('passed') and (name!='report.json' or value.get('protocol')=='experiment-builder-validation-v1'):include(path,'failed-database/'+directory.name+'/'+name)
 records={name:dict(sha256=sha(raw),bytes=len(raw)) for name,raw in files.items()};files['evidence-manifest.json']=canonical(records)
 archive=out/'evidence.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
  for name,raw in sorted(files.items()):zipped.writestr(name,raw)
 with zipfile.ZipFile(archive) as zipped:
  assert set(zipped.namelist())==set(files)
  for name,raw in files.items():assert zipped.read(name)==raw
 report=dict(version='autonomy-recovery-execution-local-v1',status='implemented-and-verified-locally;not-deployed',recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),
  revisions={repo.name:subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip() for repo in (BACKEND,ROOT)},uncommitted_source=source_inventory,migrations=migrations,
  checks=dict(backend_tests=422,infrastructure_tests=100,infrastructure_typescript='passed',unit_and_build_output_scope='Observed command outputs in the Codex transcript; not copied as original log files into this archive.',
   native_live_review=dict(path=str(live),sha256=sha(live.read_bytes()),actual_provider_calls=22,platform='linux/amd64 Docker emulated on arm64; installed production image not newly qualified'),
   native_synthetic=dict(path=str(synthetic),responses=7,actual_provider_calls=0),
   native_sql=dict(path=str(builder),sha256=sha(builder.read_bytes()),checks=builder_report['checks']),
   pdf_completion=dict(path=str(completion),sha256=sha(completion.read_bytes()),checks=completion_report['checks'],restart=completion_report['restart']),
   full_grid=dict(path=str(grid),observations=75,transfers=15,conditions=[0,1,2,5,10],duration_seconds=30,replications=3,statuses=grid_report['statuses']),
   netem_persistence=dict(path=str(persistence),sha256=sha(persistence.read_bytes()),readback=persistence_report['readback'])),
  scientific_completion=False,production_writes=0,published_prompts_changed=False,runtime_manifest_changed=False,measured_charges_usd=None,subscription_allocation_usd=None,unallocated_local_compute_storage_cost_usd=None,
  coverage_limits=['Exposed development cases reviewed by the implementing AI; no human, independent or held-out evaluation.','Real models repaired a software fixture; PDF campaign model judgments and Google/Lambda transports are synthetic.','PostgreSQL research relations and durable filesystem Storage transport are real local checks; remote Supabase Storage is not newly exercised.','Grid rows are a retrospective qualification import, not evidence attached to the production paper. Original acquisition UTC bounds remain unavailable.','Production image/native worker qualification, coordinated deployment and original-assessment experiment completion remain pending an explicit deployment request.'],
  evidence=dict(path=str(archive.relative_to(ROOT)),sha256=sha(archive.read_bytes()),local_readback_sha256=sha(archive.read_bytes()),bytes=archive.stat().st_size,members=len(files),public=False,storage='Private local archive; not uploaded to production Supabase.',exclusions='Runtime credentials/configuration, installed dependencies and compilation caches; original response/checkpoint ZIP bytes remain unchanged.'),
  reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False))
 (out/'status.json').write_bytes(canonical(report));(ROOT/'docs/autonomy-recovery-execution-local-v1-status.json').write_bytes(canonical(report));print(json.dumps(dict(status=report['status'],evidence=report['evidence'])))

if __name__=='__main__':main()
