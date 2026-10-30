"""Append private local verification evidence to the fixed retained assessment."""
import datetime as dt,importlib.util,io,json,pathlib,subprocess,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('completion_release',ROOT/'bin/builder-stall-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
r,m=release.r,release.m;STUDY=release.STUDY;BASE=ROOT/'.test-artifacts/autonomy-completion-v1'
def main():
 target=r.target();native_path=sorted((BASE/'native').glob('*/report.json'))[-1]
 native=json.loads(native_path.read_bytes());assert native['status']=='passed' and native['live_provider_calls']==0
 pending_path=BASE/('retention-pending-'+r.sha(native_path.read_bytes())[:16]+'.json')
 if pending_path.exists():pending=json.loads(pending_path.read_bytes())
 else:
  database_path=sorted((ROOT/'.test-artifacts/research-ideas/database').glob('*/autonomy-completion-report.json'))[-1];database=json.loads(database_path.read_bytes());assert database['passed'] and database['live_provider_calls']==0 and database['manual_running_campaign_edits']==0
  units=(BACK/'.test-artifacts/autonomy-completion-final-unit.log').read_bytes();assert b'Ran 396 tests' in units and b'\nOK\n' in units
  linux_path=sorted((BACK/'.test-artifacts/executable-methods/linux').glob('*/report.json'))[-1];linux=json.loads(linux_path.read_bytes());assert linux['passed']
  files={}
  def add(path,name):
   assert path.is_file() and not path.is_symlink();raw=path.read_bytes();assert len(raw)<=4000000;files[name]=raw
  for name in ('bin/retain-autonomy-completion.py','bin/check-autonomy-planner-local.py','bin/inspect-builder-stall-4055396e.py','test/check_autonomy_completion_database.py','docs/autonomy-completion-protocol-v1.json','docs/autonomy-completion-retention-v1.json','docs/autonomy-completion-local-v1.md'):add(ROOT/name,name)
  for name in ('openclaw_runtime.py','model_dispatch.py','tests/test_openclaw.py'):add(BACK/'research_workflow'/name,'backend/'+name)
  for path in BASE.rglob('*'):
   if path.is_file() and path.suffix in ('.json','.bin') and path.name!='config.json' and not path.name.startswith('retention-pending') and 'retention' not in path.parts:add(path,str(path.relative_to(ROOT)))
  for directory in [p.parent for p in (ROOT/'.test-artifacts/research-ideas/database').glob('*/autonomy-completion-report.json')]:
   for path in directory.rglob('*'):
    if path.is_file() and path.name!='config.json' and (path.parent==directory or path.parent.parent.name=='native-spool') and path.suffix in ('.json','.bin','.txt'):add(path,str(path.relative_to(ROOT)))
  for path in linux_path.parent.iterdir():
   if path.is_file():add(path,'linux/'+path.name)
  files['backend/autonomy-completion-final-unit.log']=units
  add(ROOT/'.test-artifacts/autonomy-completion-final-database.log','reports/autonomy-completion-final-database.log')
  report=dict(version='autonomy-completion-local-v1',recorded_at=r.stamp(),target=target,assessment_id=STUDY,scientific_completion=False,deployed=False,publication_status='local implementation and exposed development verification only',backend_base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip(),working_source_sha256={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in ('openclaw_runtime.py','model_dispatch.py','tests/test_openclaw.py')},protocol_sha256=r.sha((ROOT/'docs/autonomy-completion-protocol-v1.json').read_bytes()),native=native,database=database,linux=linux,backend_tests=396,new_live_provider_calls=0,new_cloud_instances=0,measured_charges_usd=None,unallocated_cost_usd=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False),production_remaining='Original assessment has not used these local changes. Explicit deployment and subsequent live model/execution verification remain required.')
  files['verification-report.json']=json.dumps(report,sort_keys=True,separators=(',',':')).encode();buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
   for name,raw in sorted(files.items()):archive.writestr(name,raw)
   archive.writestr('artifact-manifest.json',json.dumps([dict(path=n,bytes=len(raw),sha256=r.sha(raw)) for n,raw in sorted(files.items())]))
  raw=buffer.getvalue();assert len(raw)<=20000000;out=BASE/('retention-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(mode=0o700);path=out/'evidence.zip';path.write_bytes(raw)
  pending=dict(archive=str(path.relative_to(ROOT)),sha256=r.sha(raw),byte_count=len(raw),members=len(files),report=report);release.q.save(pending_path,pending)
 path=(ROOT/pending['archive']).resolve();assert path.is_relative_to(BASE.resolve());raw=path.read_bytes();assert r.sha(raw)==pending['sha256'];storage_path=STUDY+'/'+pending['sha256'];m.storage(storage_path,raw);restored=m.storage(storage_path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as archive:
  for item in json.loads(archive.read('artifact-manifest.json')):assert r.sha(archive.read(item['path']))==item['sha256']
 actor=r.admin.query('select owner_id from research_study_owners where study_id='+r.admin.literal(STUDY)+'::uuid')[0]['owner_id'];identity=str(uuid.uuid5(uuid.UUID(STUDY),'autonomy-completion-local-v1:'+pending['sha256']))
 record=dict(id=identity,sha256=pending['sha256'],byte_count=len(raw),storage_path=storage_path,media_type='application/zip',verified_at=r.stamp(),provenance=dict(kind='local-operational-verification',version='autonomy-completion-local-v1',scientific_completion=False,deployed=False,reviewer=pending['report']['reviewer']))
 saved=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(identity)+'::uuid')
 if not saved:r.admin.query('select public.research_append('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(actor)+'::uuid',r.admin.literal('artifacts'),r.admin.literal(json.dumps(record))+'::jsonb'])+')',read_only=False)
 assert r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(identity)+'::uuid')==[dict(sha256=pending['sha256'],byte_count=len(raw))]
 result=dict(status='retained; local only',artifact_id=identity,sha256=pending['sha256'],retrieved_sha256=r.sha(restored),bytes=len(raw),members=pending['members'],public=False);release.q.save(ROOT/'docs/autonomy-completion-local-v1-status.json',dict(result,backend_tests=396,new_live_provider_calls=0,database_checks=pending['report']['database']['checks'],conditional_gaps=pending['report']['database']['conditional_gaps']));print(json.dumps(result))
if __name__=='__main__':main()
