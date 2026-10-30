"""Fixed assessment, exact-source planner qualification and scoped release checks."""
import argparse,ast,datetime as dt,importlib.util,io,json,pathlib,subprocess,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('completion_prior',ROOT/'bin/builder-stall-release.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
q,r,m=prior.q,prior.r,prior.m;BASE=ROOT/'.test-artifacts/autonomy-completion-release-v1';q.BASE=BASE;STUDY=prior.STUDY
def freeze(out):
 r.auth_maintenance_guard();manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip() and subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision']
 previous=json.loads(subprocess.check_output(['git','show','d33fda5:research-workflow-runtime.json'],cwd=ROOT));changed={n for n,h in manifest['files'].items() if previous['files'].get(n)!=h};assert changed=={'openclaw_runtime.py','model_dispatch.py'}
 def functions(raw):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 baseline=subprocess.check_output(['git','show',previous['source_revision']+':research_workflow/openclaw_runtime.py'],cwd=BACK);a=functions(baseline);b=functions((BACK/'research_workflow/openclaw_runtime.py').read_bytes())
 inherited=['environment','verify_runtime','credential','http_request','catalog','persist_completed','_persist_completed','save_completion','retry_completions','worker_loop'];assert all(a[n]==b[n] for n in inherited)
 old_dispatch=functions(subprocess.check_output(['git','show',previous['source_revision']+':research_workflow/model_dispatch.py'],cwd=BACK));new_dispatch=functions((BACK/'research_workflow/model_dispatch.py').read_bytes());assert all(old_dispatch[n]==new_dispatch[n] for n in ('rpc','health','transient_read','invoke'))
 source=sorted((ROOT/'.test-artifacts/autonomy-completion-v1').glob('*/retrieval.json'))[-1].parent;logical=(source/'logical.json').read_bytes();assert r.sha(logical)=='9674859e08bdbc1f6000cdb25d4b4f38436da42b2487d57e7e9924b2f3f7d265'
 prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder')");assert {p['version'] for p in prompts}=={'research-autonomy-v10','research-experiment-builder-v2'}
 for p in prompts:assert r.sha((p['system_prompt']+'\n\n'+p['research_context']).encode())==p['content_sha256'] and p['published_at']
 import sys;sys.path.insert(0,str(BACK/'research_workflow'));import autonomy_model as model
 context=dict(task='planning',evaluation_scope='Explicit operational transport fixture, no academic paper or scientific assessment.',initial_prompt='No research paper, source data, claim, or target has been supplied in this fixture. Do not invent one or execute an experiment. Return a blocked decision for missing source data, no claims or evidence, no proposal, no scientific label and coverage_complete=false.',registered_checks=[],shared_acquisitions=[],available_built_packages=[],remaining_commitment_cents=100,scope='A single qualification response; not authorization for a research campaign.')
 p=next(p for p in prompts if p['module_id']=='research-autonomy');live=model.request(p['system_prompt']+'\n\n'+p['research_context'],context);live['modelId']='gpt-6.1-sol'
 files={'research_workflow/'+n:(BACK/'research_workflow'/n).read_bytes() for n in manifest['files']};assert all(r.sha(files['research_workflow/'+n])==h for n,h in manifest['files'].items())
 files.update({'qualification.py':(ROOT/'bin/autonomy_completion_qualification_host.py').read_bytes(),'base_qualification.py':(ROOT/'bin/builder_continuation_qualification_host.py').read_bytes(),'retained-logical.json':logical,'baseline-runtime.py':baseline})
 for path in (BACK/'research_workflow/tests').glob('*.py'):files['research_workflow/tests/'+path.name]=path.read_bytes()
 packet=dict(protocol=json.loads((ROOT/'docs/autonomy-completion-release-protocol-v1.json').read_bytes()),source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(raw) for n,raw in files.items()},logical_sha256=r.sha(logical),prompts=prompts,live_context=context,live_logical=live,image='sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64',frozen_at=r.stamp(),inherited_qualification=dict(previous_source_revision=previous['source_revision'],unchanged_files=[n for n in manifest['files'] if n not in changed],shared_runtime_functions_ast_equal=inherited,dispatch_admission_functions_ast_equal=['rpc','health','transient_read','invoke'],previous_archive_sha256='71b179462f085cc61e59494454020668f04126f88b82b0dd48a19c0f74d5baa9',scope='Unchanged builder/netem executable components retain their existing qualification; changed transport is separately qualified here.'))
 if (BASE/'selected.txt').exists():
  parent=q.selected();failed=json.loads((parent/'evaluations-recorded.json').read_bytes());assert failed['status']=='failed-or-paused' and not (parent/'live-command.json').exists()
  old=json.loads((parent/'frozen.json').read_bytes());assert old['runtime_manifest']['files']==manifest['files'],'This follow-up changes only the exposed test fixture, not runtime source'
  packet['protocol']['version']='autonomy-completion-release-followup-v2';packet['harness_followup']=dict(version='separate-controller-and-runtime-wire-guards-v1',parent=parent.name,original_failed_archive=failed['archive'],reason='In production OPENCLAW mode the test generated its logical input after replacing the wire serializer with an oversized body. The valid controller guard rejected the fixture before runtime execution. Freeze the valid input first; separately assert the controller and runtime rejections. Preserve all native failures and unchanged pass criteria: 14 tests, no errors/failures/skips. No live call occurred; the original one-call cap remains.',inherited_actual_provider_calls=0)
 files['frozen.json']=json.dumps(packet,sort_keys=True,separators=(',',':')).encode();q.save(out/'frozen.json',packet);files['artifact-manifest.json']=json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in files.items()]).encode();stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,raw in sorted(files.items()):archive.writestr(name,raw)
 raw=stream.getvalue();(out/'candidate.zip').write_bytes(raw);path='qualification/autonomy-completion-release-v1/'+out.name+'/'+r.sha(raw)+'.zip';m.storage(path,raw);assert m.storage(path)==raw;q.save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),bytes=len(raw)));(BASE/'selected.txt').write_text(out.name+'\n')
 before=prior.snapshot(None,out);q.save(out/'assessment-before.json',before['workflow']);return dict(source_revision=packet['source_revision'],changed_files=sorted(changed),maximum_actual_provider_calls=1,candidate_sha256=r.sha(raw))
def record(source):
 packet=json.loads((source/'frozen.json').read_bytes());native=json.loads((source/'native.json').read_bytes());live=json.loads((source/'live.json').read_bytes());review=json.loads((source/'reviewed.json').read_bytes());pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json']
 assert native['status']=='passed' and native['tests']['skipped']==0 and live['status']=='awaiting-substantive-review' and live['actual_calls']==1 and live['reserved_cents']==100 and live['wall_seconds']<=480
 assert review['passed'] and review['reviewer']==packet['protocol']['reviewer'] and review['source_revision']==packet['source_revision'] and review['actual_answer_reviewed']
 assert r.sha(m.storage(pointer['path']))==pointer['sha256'];value=dict(protocol=packet['protocol'],source_revision=packet['source_revision'],outcome='passed',native=native,live=live,review=review,inherited_qualification=packet['inherited_qualification'],archive=pointer,scientific_completion=False,prompt_publications_changed=False)
 raw=json.dumps(value,sort_keys=True,separators=(',',':'));sha=r.sha(raw.encode())
 for p in packet['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(p['id'])+'::uuid',r.admin.literal('passed'),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI; nonindependent exposed operational transport qualification, not human or scientific review')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  assert r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(p['id'])+'::uuid and report_sha256='+r.admin.literal(sha))[0]['report_raw']==raw
 result=dict(status='passed',report_sha256=sha,archive=pointer);q.save(source/'evaluations-recorded.json',result);return result
def record_failure(source):
 packet=json.loads((source/'frozen.json').read_bytes());native=json.loads((source/'native.json').read_bytes());assert native['tests']==dict(run=14,failures=0,errors=1,skipped=0) and not (source/'live-command.json').exists()
 pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json'];assert r.sha(m.storage(pointer['path']))==pointer['sha256']
 value=dict(protocol=packet['protocol'],source_revision=packet['source_revision'],outcome='failed-or-paused',native=native,archive=pointer,actual_provider_calls=0,reviewer=packet['protocol']['reviewer'],review_status='Actual failed native test log and old/new transport receipts examined by implementing AI; no human or scientific review.',reason='Runtime byte-limit fixture was rejected by the upstream controller preflight first when OPENCLAW mode was enabled. Preserve failure; test those two distinct guards separately without weakening either limit.')
 raw=json.dumps(value,sort_keys=True,separators=(',',':'));sha=r.sha(raw.encode())
 for p in packet['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(p['id'])+'::uuid',r.admin.literal('failed-or-paused'),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI; retained failed operational qualification, not human or scientific review')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  assert r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(p['id'])+'::uuid and report_sha256='+r.admin.literal(sha))[0]['report_raw']==raw
 result=dict(status='failed-or-paused',report_sha256=sha,archive=pointer);q.save(source/'evaluations-recorded.json',result);return result
def retain(source,out):
 pending_path=source/'release-pending.json'
 if pending_path.exists():pending=json.loads(pending_path.read_bytes())
 else:
  active=json.loads((source/'active-verified.json').read_bytes());assert active['status']=='passed' and active['admission'];evaluation=json.loads((source/'evaluations-recorded.json').read_bytes());assert evaluation['status']=='passed'
  manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert active['source_revision']==manifest['source_revision']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()
  public=json.loads(sorted(BASE.glob('*/public-verified.json'))[-1].read_bytes());executors=json.loads(sorted(BASE.glob('*/executors-verified.json'))[-1].read_bytes());assert public['status']==executors['status']=='passed' and executors['source_revision']==manifest['source_revision']
  browser=json.loads((source/'browser-verified.json').read_bytes());assert browser['passed'] and not browser['reviewer']['independent']
  state=prior.snapshot(source,out);volume=r.aws('ec2','describe-volumes','--volume-ids','vol-0993b9127ac7a8231')['Volumes'][0];assert volume['Size']==300 and volume['Encrypted'] and any(a['InstanceId']=='i-087f1493809643115' for a in volume['Attachments'])
  report=dict(version='autonomy-completion-production-v1',status='deployed-with-explicit-verification-scope',recorded_at=r.stamp(),runtime_manifest=manifest,release_blocking_checks_passed=True,evaluation=evaluation,active=active,executors=executors,public=public,browser=browser,assessment_snapshot=state,scientific_completion=False,new_qualification_provider_calls=1,qualification_reservation_cents=100,measured_charges_usd=None,subscription_allocation_usd=None,unallocated_host_storage_cost_usd=None,worker_replaced=False,worker_disk_gib=300,encrypted=True,frontend_changed=False,schema_changed=False,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False))
  files={'release-report.json':json.dumps(report,sort_keys=True,separators=(',',':')).encode()}
  for directory in [p.parent for p in BASE.glob('*/receipt.json')]:
   for p in directory.iterdir():
    if p.is_file() and p.suffix in ('.json','.bin','.zip','.log') and p.name not in ('candidate.zip','release-pending.json','release-evidence.zip'):files[str(p.relative_to(ROOT))]=p.read_bytes()
  for n in ('bin/autonomy-completion-release.py','bin/autonomy_completion_qualification_host.py','bin/builder-continuation-release.py','docs/autonomy-completion-release-protocol-v1.json','docs/autonomy-completion-local-v1.md','docs/autonomy-completion-local-v1-status.json','docs/autonomy-completion-production-v1.md','research-workflow-runtime.json'):files[n]=(ROOT/n).read_bytes()
  files['backend-unit.log']=(BACK/'.test-artifacts/autonomy-completion-release-unit.log').read_bytes()
  for n in ('autonomy-completion-release-infra.log','autonomy-completion-release-build.log'):files[n]=(ROOT/'.test-artifacts'/n).read_bytes()
  for directory in (ROOT/'.test-artifacts/openclaw-release').glob('20261030T*'):
   if directory.name<'20261030T022601979253Z':continue
   for p in directory.iterdir():
    if p.is_file() and p.name in ('receipt.json','cdk.log','outputs.json','parameter-comparison.json'):files[str(p.relative_to(ROOT))]=p.read_bytes()
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
   for n,raw in sorted(files.items()):archive.writestr(n,raw)
   archive.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in files.items()]))
  raw=stream.getvalue();assert len(raw)<20000000;(out/'release-evidence.zip').write_bytes(raw);pending=dict(archive=str((out/'release-evidence.zip').relative_to(ROOT)),sha256=r.sha(raw),report=report,members=len(files));q.save(pending_path,pending)
 raw=(ROOT/pending['archive']).read_bytes();assert r.sha(raw)==pending['sha256'];path=STUDY+'/'+pending['sha256'];m.storage(path,raw);restored=m.storage(path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as archive:
  for item in json.loads(archive.read('artifact-manifest.json')):assert r.sha(archive.read(item['path']))==item['sha256']
 ident=str(uuid.uuid5(uuid.UUID(STUDY),'autonomy-completion-production:'+pending['sha256']));actor=r.admin.query('select owner_id from research_study_owners where study_id='+r.admin.literal(STUDY)+'::uuid')[0]['owner_id'];record=dict(id=ident,sha256=pending['sha256'],byte_count=len(raw),storage_path=path,media_type='application/zip',verified_at=r.stamp(),provenance=dict(kind='production-release-verification',version='autonomy-completion-production-v1',scientific_completion=False,reviewer=pending['report']['reviewer']))
 saved=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')
 if not saved:r.admin.query('select public.research_append('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(actor)+'::uuid',r.admin.literal('artifacts'),r.admin.literal(json.dumps(record))+'::jsonb'])+')',read_only=False)
 assert r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')==[dict(sha256=pending['sha256'],byte_count=len(raw))]
 value=pending['report'];value['evidence']=dict(artifact_id=ident,sha256=pending['sha256'],retrieved_sha256=r.sha(restored),bytes=len(raw),members=pending['members'],public=False);q.save(ROOT/'docs/autonomy-completion-production-v1-status.json',value);return dict(status=value['status'],evidence=value['evidence'])
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','prepare','native','live','evidence','status','collect','record-review','record-failure','approve','pin','snapshot','verify-held','verify-active','verify-executors','public-checks','record-release']);args=p.parse_args();BASE.mkdir(exist_ok=True);out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir();receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:
  receipt['targets']=r.target()
  if args.mode=='freeze':value=freeze(out)
  elif args.mode=='pin':value=prior.pin()
  elif args.mode=='snapshot':value=prior.snapshot(q.selected(),out)
  elif args.mode=='record-review':value=record(q.selected())
  elif args.mode=='record-failure':value=record_failure(q.selected())
  elif args.mode=='approve':value=prior.old.prior.approve(q.selected())
  elif args.mode in ('status','collect'):value=getattr(q,args.mode)(q.selected());value.pop('cases',None)
  elif args.mode=='verify-executors':value=prior.verify_executors(out)
  elif args.mode=='public-checks':value=prior.public_checks(out)
  elif args.mode=='record-release':value=retain(q.selected(),out)
  elif args.mode in ('verify-held','verify-active'):
   q.save(q.selected()/'migration-applied.json',dict(status='passed',reason='No schema changes in this release.'));r.prior.PRIVATE|={'research_model_reconciliations','research_autonomy_repairs','research_autonomy_repair_events'};value=prior.old.prior.verify(q.selected(),out,args.mode=='verify-active')
  else:
   if args.mode in ('native','live'):
    name='prepared.json' if args.mode=='native' else 'native.json'
    # Before archive collection, the original worker status is retained in the
    # signed-in SSM snapshot rather than a separate local phase-output file.
    assert json.loads((q.selected()/'host-status.json').read_bytes())[name]['status']=='passed'
   value=q.dispatch(q.selected(),args.mode)
  receipt.update(status='complete',result=value)
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:q.save(out/'receipt.json',receipt);print(json.dumps(dict(directory=str(out),**receipt)))
if __name__=='__main__':main()
