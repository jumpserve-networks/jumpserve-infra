"""Fixed-target optional-budget release; immutable evidence and audited amendment."""
import argparse,datetime as dt,importlib.util,io,json,pathlib,subprocess,sys,uuid,zipfile
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
spec=importlib.util.spec_from_file_location('completion_release',ROOT/'bin/autonomy-completion-release.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
q,r,m=c.q,c.r,c.m;BASE=ROOT/'.test-artifacts/optional-budget-release-v1';q.BASE=BASE;STUDY=c.STUDY
SQL='202610300001_optional_assessment_budget.sql';REQUEST=str(uuid.uuid5(uuid.UUID(STUDY),'operator-unlimited-budget-20261030'))
AUTHORIZATION="Let's make the budget unlimited for now.";ACTOR='Lab operator via Codex conversation, 2026-10-30'
def snapshot(source,out):
 identity=r.admin.literal(STUDY)+'::uuid';w=r.admin.query('select to_jsonb(w) record from research_autonomy_workflows w where study_id='+identity)[0]['record']
 if source and (source/'assessment-before.json').exists():
  before=json.loads((source/'assessment-before.json').read_bytes());assert all(before[k]==w[k] for k in ('initial_prompt','initial_sha256','deadline_at','max_attempts','created_at')) and w['committed_cents']>=before['committed_cents']
  assert w['max_spend_cents'] is None if (source/'budget-applied.json').exists() else w['max_spend_cents']==before['max_spend_cents']
 data=dict(recorded_at=r.stamp(),workflow=w,tasks=r.admin.query('select id,claim_id,stage,status,label,attempts,reason,updated_at from research_autonomy_tasks where study_id='+identity+' order by created_at'),jobs=r.admin.query('select id,status,reason,updated_at from research_queue_jobs where study_id='+identity+' order by created_at'),scope='Separate bounded read-only queries; no scientific completion inferred.')
 q.save(out/'assessment-snapshot.json',data);return data
def freeze(out):
 r.auth_maintenance_guard()
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip() and subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision']
 previous=json.loads(subprocess.check_output(['git','show','aed13a8:research-workflow-runtime.json'],cwd=ROOT));changed={n for n,h in manifest['files'].items() if previous['files'].get(n)!=h};assert changed=={'autonomy.py','autonomy_model.py','paper_uploads.py'}
 local=json.loads((ROOT/'docs/optional-assessment-budget-local-v1-status.json').read_bytes());assert local['backend_tests']==398 and local['frontend_tests']==278 and local['database_report']['passed']
 raw=(ROOT/'database'/SQL).read_bytes();assert local['database_report']['migration_sha256'][SQL]==r.sha(raw)
 local_bytes=(ROOT/local['evidence']['path']).read_bytes();assert r.sha(local_bytes)==local['evidence']['sha256']
 prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder')")
 assert {p['version'] for p in prompts}=={'research-autonomy-v10','research-experiment-builder-v2'}
 for p in prompts:assert p['published_at'] and r.sha((p['system_prompt']+'\n\n'+p['research_context']).encode())==p['content_sha256']
 sys.path.insert(0,str(BACK/'research_workflow'));import autonomy_model as model
 context=dict(task='planning',evaluation_scope='Explicit operational software fixture; no paper or scientific measurement.',initial_prompt='No research paper, source data, claim, or target has been supplied. Do not invent one or execute an experiment. Return blocked for missing source data, with no claims, evidence, proposal or scientific label and coverage_complete=false.',registered_checks=[],shared_acquisitions=[],available_built_packages=[],remaining_commitment_cents=None,resource_authorization=dict(version='assessment-budget-amendment-v2',max_spend_cents=None,committed_cents=100000,deadline_at='2026-11-04T20:25:04.587324+00:00'),scope='Explicit unlimited assessment authority does not authorize inventing inputs. This qualification permits one response only; no campaign or paid fallback.')
 p=next(p for p in prompts if p['module_id']=='research-autonomy')
 with patch.object(model,'OPENCLAW',True),patch.object(model,'MODEL','gpt-6.1-sol'):logical=model.request(p['system_prompt']+'\n\n'+p['research_context'],context)
 files={'research_workflow/'+n:(BACK/'research_workflow'/n).read_bytes() for n in manifest['files']};assert all(r.sha(files['research_workflow/'+n])==h for n,h in manifest['files'].items())
 for path in (BACK/'research_workflow/tests').glob('*.py'):files['research_workflow/tests/'+path.name]=path.read_bytes()
 files.update({'qualification.py':(ROOT/'bin/optional_budget_qualification_host.py').read_bytes(),'completion_qualification.py':(ROOT/'bin/autonomy_completion_qualification_host.py').read_bytes(),'base_qualification.py':(ROOT/'bin/builder_continuation_qualification_host.py').read_bytes(),'research_workflow/experiment-builder.Dockerfile':(BACK/'research_workflow/experiment-builder.Dockerfile').read_bytes(),'migration.sql':raw,'local-evidence.zip':local_bytes,'local-validation.json':json.dumps(local,sort_keys=True).encode()})
 packet=dict(protocol=json.loads((ROOT/'docs/optional-budget-release-protocol-v1.json').read_bytes()),source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(v) for n,v in files.items()},prompts=prompts,live_context=context,live_logical=logical,image='sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64',frozen_at=r.stamp(),inherited_qualification=dict(previous_source_revision=previous['source_revision'],unchanged_files=[n for n in manifest['files'] if n not in changed],previous_archive_sha256='18e46bc8307f1a1252bc936334d2bb7d884016d30acabce1acdf8ef598d77b5b',scope='Builder, netem, transport, credential recovery and dispatch implementations are byte-identical; changed budget authority is separately qualified. Not paper completion.'))
 if (BASE/'selected.txt').exists():
  parent=q.selected();old=json.loads((parent/'frozen.json').read_bytes());native=json.loads((parent/'native.json').read_bytes());pointer=json.loads((parent/'host-status.json').read_bytes())['evidence.json']
  assert not (parent/'live-command.json').exists() and native['status']=='passed' and native['tests']==dict(run=23,failures=0,errors=0,skipped=0)
  assert old['runtime_manifest']['files']==manifest['files'] and old['source_files']['migration.sql']!=r.sha(raw) and r.sha(m.storage(pointer['path']))==pointer['sha256']
  paused=dict(outcome='failed-or-paused',reason='The release was paused before any live model call: a new real PostgreSQL regression demonstrated that the initial SQL resume query excluded a historical unknown dispatch even after a matching append-only reconciliation proof. Preserve the passed 23 native checks, original SQL and failed local tests; qualify the proof-aware migration as a separate follow-up.',actual_provider_calls=0,native=native,protocol=old['protocol'],archive=pointer,reviewer=old['protocol']['reviewer'])
  report=json.dumps(paused,sort_keys=True,separators=(',',':'));report_sha=r.sha(report.encode())
  for prompt in prompts:
   r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(prompt['id'])+'::uuid',r.admin.literal('failed-or-paused'),r.admin.literal(report),r.admin.literal(report_sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI; nonindependent pre-provider release review, not a scientific or human review')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
   assert r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(prompt['id'])+'::uuid and report_sha256='+r.admin.literal(report_sha))[0]['report_raw']==report
  q.save(parent/'evaluations-recorded.json',dict(status='failed-or-paused',report_sha256=report_sha,archive=pointer))
  packet['protocol']['version']='optional-budget-release-followup-v2';packet['pre_provider_sql_followup']=dict(parent=parent.name,archive=pointer,actual_calls_inherited=0,reason=paused['reason'],unchanged_runtime_files=True)
 files['frozen.json']=json.dumps(packet,sort_keys=True,separators=(',',':')).encode();q.save(out/'frozen.json',packet);files['artifact-manifest.json']=json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in files.items()]).encode();stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in sorted(files.items()):z.writestr(n,v)
 archive=stream.getvalue();(out/'candidate.zip').write_bytes(archive);path='qualification/optional-budget-release-v1/'+out.name+'/'+r.sha(archive)+'.zip';m.storage(path,archive);assert m.storage(path)==archive
 q.save(out/'candidate.json',dict(path=path,sha256=r.sha(archive),bytes=len(archive)));(BASE/'selected.txt').write_text(out.name+'\n');q.save(out/'assessment-before.json',snapshot(None,out)['workflow'])
 return dict(source_revision=manifest['source_revision'],changed_files=sorted(changed),maximum_actual_provider_calls=1,candidate_sha256=r.sha(archive))
def migrate(source):
 assert json.loads((source/'evaluations-recorded.json').read_bytes())['status']=='passed';r.auth_maintenance_guard();raw=(ROOT/'database'/SQL).read_bytes();assert r.sha(raw)==json.loads((source/'frozen.json').read_bytes())['source_files']['migration.sql']
 before=r.admin.query("select p.proname,pg_get_functiondef(p.oid) definition from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'research_%' and strpos(pg_get_functiondef(p.oid),'max_spend_cents')>0 order by p.proname");q.save(source/'migration-before-functions.json',before)
 present=r.admin.query("select to_regprocedure('public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text)') is not null present")[0]['present'];path='release-migrations/optional-budget-v1/'+r.sha(raw)+'-'+SQL;m.storage(path,raw);assert m.storage(path)==raw
 if not present:r.admin.query(raw.decode(),read_only=False)
 expected_body=raw.decode().split("returns jsonb language plpgsql security definer set search_path='' as $$",1)[1].split('$$;',1)[0]
 installed=r.admin.query("select prosrc from pg_proc where oid='public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text)'::regprocedure")[0]['prosrc'];assert installed==expected_body,'Installed budget RPC differs from the exact frozen source'
 checks=r.admin.query("select column_default,is_nullable from information_schema.columns where table_schema='public' and table_name='research_autonomy_workflows' and column_name='max_spend_cents'");assert checks==[dict(column_default='10000',is_nullable='YES')]
 security=r.admin.query("select has_function_privilege('anon','public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text)','EXECUTE') anon_execute,has_function_privilege('authenticated','public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text)','EXECUTE') browser_execute");assert security==[dict(anon_execute=False,browser_execute=False)]
 result=dict(status='passed',migration=SQL,sha256=r.sha(raw),present_before=present,defaults=checks,security=security,assessment_unchanged=snapshot(source,source)['workflow']['max_spend_cents']==100000);assert result['assessment_unchanged'];q.save(source/'migration-applied.json',result);return result
def frontend(source,start=False):
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=FRONT,text=True).strip();jobs=r.aws('amplify','list-jobs','--app-id','d24jvguj7brnkj','--branch-name','main','--max-results','10')['jobSummaries'];q.save(source/'frontend-jobs.json',jobs);matching=[j for j in jobs if j.get('commitId')==revision]
 command=source/'frontend-command.json'
 if command.exists():
  previous=json.loads(command.read_bytes());assert previous['revision']==revision;matching=[dict(jobId=previous['job_id'])]
 if start and not matching and not command.exists():
  job=r.aws('amplify','start-job','--app-id','d24jvguj7brnkj','--branch-name','main','--job-type','RELEASE','--commit-id',revision)['jobSummary'];q.save(source/'frontend-command.json',dict(revision=revision,job_id=job['jobId']));return job
 if not matching:return dict(status='not-started',revision=revision)
 assert jobs[0].get('commitId')==revision,'A different frontend release is newer than this qualified commit'
 job=r.aws('amplify','get-job','--app-id','d24jvguj7brnkj','--branch-name','main','--job-id',matching[0]['jobId'])['job'];q.save(source/'frontend-status.json',job);return dict(revision=revision,job_id=job['summary']['jobId'],status=job['summary']['status'])
def budget(source):
 held=json.loads((source/'held-verified.json').read_bytes());assert held['status']=='passed' and held['source_revision']==json.loads((ROOT/'research-workflow-runtime.json').read_bytes())['source_revision']
 assert frontend(source)['status']=='SUCCEED';r.auth_maintenance_guard()
 # A lost response is reconciled against the exact immutable operator event,
 # not converted into a new funding identity or another resume operation.
 existing=r.admin.query('select details from research_autonomy_events where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(REQUEST)+'::uuid')
 if existing and not (source/'budget-applied.json').exists():
  event=existing[0]['details'];assert event['version']=='assessment-budget-amendment-v2' and event['max_spend_cents'] is None and event['authorized_by']==ACTOR and event['reason']==AUTHORIZATION and event['resume_budget_tasks'] is True
  q.save(source/'budget-applied.json',dict(status='passed',request_id=REQUEST,reconciled_from_original_event=True,event=event,authority=AUTHORIZATION))
 before=snapshot(source,source)['workflow']
 if existing:return dict(status='passed',maximum=None,committed_cents=before['committed_cents'],deadline_at=before['deadline_at'],replayed=True,reconciled_from_original_event=True)
 result=r.admin.query('select public.research_autonomy_set_budget('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(REQUEST)+'::uuid','null','true',r.admin.literal(ACTOR),r.admin.literal(AUTHORIZATION)])+') result',read_only=False)[0]['result'];assert result['max_spend_cents'] is None
 q.save(source/'budget-applied.json',dict(status='passed',request_id=REQUEST,result=result,before=before,authority=AUTHORIZATION));after=snapshot(source,source)['workflow'];assert after['max_spend_cents'] is None and after['committed_cents']==before['committed_cents']
 return dict(status='passed',maximum=None,committed_cents=after['committed_cents'],deadline_at=after['deadline_at'],resumed_task_ids=result.get('resumed_task_ids',[]),replayed=result['replayed'])
def retain(source,out):
 pending_path=source/'release-pending.json'
 if pending_path.exists():pending=json.loads(pending_path.read_bytes())
 else:
  active=json.loads((source/'active-verified.json').read_bytes());budget_result=json.loads((source/'budget-applied.json').read_bytes());browser=json.loads((source/'browser-verified.json').read_bytes());evaluation=json.loads((source/'evaluations-recorded.json').read_bytes())
  assert active['status']==budget_result['status']==evaluation['status']=='passed' and active['admission'] and browser['passed'] and not browser['reviewer']['independent']
  manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert manifest['source_revision']==active['source_revision']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()
  front=frontend(source);assert front['status']=='SUCCEED';state=snapshot(source,out);assert state['workflow']['max_spend_cents'] is None
  executors=json.loads(sorted(BASE.glob('*/executors-verified.json'))[-1].read_bytes());public=json.loads(sorted(BASE.glob('*/public-verified.json'))[-1].read_bytes());assert executors['status']==public['status']=='passed' and executors['source_revision']==manifest['source_revision']
  volume=r.aws('ec2','describe-volumes','--volume-ids','vol-0993b9127ac7a8231')['Volumes'][0];assert volume['Size']==300 and volume['Encrypted'] and any(v['InstanceId']=='i-087f1493809643115' for v in volume['Attachments'])
  report=dict(version='optional-assessment-budget-production-v1',status='deployed-and-authorized',recorded_at=r.stamp(),release_blocking_checks_passed=True,assessment_id=STUDY,runtime_manifest=manifest,frontend=front,active=active,evaluation=evaluation,executors=executors,public=public,browser=browser,budget=budget_result,assessment_snapshot=state,default_budget_usd=100,scientific_completion=False,new_qualification_provider_calls=1,qualification_reservation_cents=100,measured_charges_usd=None,subscription_allocation_usd=None,unallocated_host_storage_cost_usd=None,worker_replaced=False,worker_disk_gib=300,encrypted=True,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False))
  files={'release-report.json':json.dumps(report,sort_keys=True,separators=(',',':')).encode()}
  for p in BASE.rglob('*'):
   if p.is_file() and p.suffix in ('.json','.bin','.zip','.log') and p.name not in ('candidate.zip','release-pending.json','release-evidence.zip'):files[str(p.relative_to(ROOT))]=p.read_bytes()
  for n in ('bin/optional-budget-release.py','bin/optional_budget_qualification_host.py','docs/optional-budget-release-protocol-v1.json','database/'+SQL,'docs/optional-assessment-budget-v1.md','docs/optional-assessment-budget-production-v1.md','docs/optional-assessment-budget-local-v1-status.json','research-workflow-runtime.json'):files[n]=(ROOT/n).read_bytes()
  files['backend-unit.log']=(BACK/'.test-artifacts/optional-budget-unit.log').read_bytes()
  for n in ('optional-budget-tests.log','optional-budget-build.log','optional-budget-public-roundtrip.log'):files[n]=(FRONT/'.test-artifacts'/n).read_bytes()
  for n in ('optional-budget-infra.log','optional-budget-infra-build.log'):files[n]=(ROOT/'.test-artifacts'/n).read_bytes()
  for directory in (ROOT/'.test-artifacts/openclaw-release').glob('20261030T*'):
   if directory.name<'20261030T213700000000Z':continue
   for p in directory.iterdir():
    if p.is_file() and p.name in ('receipt.json','cdk.log','outputs.json','parameter-comparison.json','host-update-result.json'):files[str(p.relative_to(ROOT))]=p.read_bytes()
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
   for n,v in sorted(files.items()):z.writestr(n,v)
   z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in files.items()]))
  raw=stream.getvalue();assert len(raw)<20000000;(out/'release-evidence.zip').write_bytes(raw);pending=dict(archive=str((out/'release-evidence.zip').relative_to(ROOT)),sha256=r.sha(raw),report=report,members=len(files));q.save(pending_path,pending)
 raw=(ROOT/pending['archive']).read_bytes();assert r.sha(raw)==pending['sha256'];path=STUDY+'/'+pending['sha256'];m.storage(path,raw);restored=m.storage(path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as z:
  for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
 ident=str(uuid.uuid5(uuid.UUID(STUDY),'optional-budget-production:'+pending['sha256']));owner=r.admin.query('select owner_id from research_study_owners where study_id='+r.admin.literal(STUDY)+'::uuid')[0]['owner_id'];record=dict(id=ident,sha256=pending['sha256'],byte_count=len(raw),storage_path=path,media_type='application/zip',verified_at=r.stamp(),provenance=dict(kind='production-budget-authorization-and-release',version='optional-assessment-budget-production-v1',scientific_completion=False,reviewer=pending['report']['reviewer']))
 existing=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')
 if not existing:r.admin.query('select public.research_append('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(owner)+'::uuid',r.admin.literal('artifacts'),r.admin.literal(json.dumps(record))+'::jsonb'])+')',read_only=False)
 assert r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')==[dict(sha256=pending['sha256'],byte_count=len(raw))]
 report=pending['report'];report['evidence']=dict(artifact_id=ident,sha256=pending['sha256'],retrieved_sha256=r.sha(restored),bytes=len(raw),members=pending['members'],public=False);q.save(ROOT/'docs/optional-assessment-budget-production-v1-status.json',report);return dict(status=report['status'],evidence=report['evidence'])
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['pin','freeze','prepare','native','live','evidence','status','collect','record-review','approve','migrate','verify-held','verify-active','verify-executors','public-checks','frontend-release','frontend-status','apply-budget','snapshot','record-release']);args=parser.parse_args();BASE.mkdir(exist_ok=True);stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out=BASE/(stamp if args.mode=='freeze' else stamp+'-'+uuid.uuid4().hex[:8]);out.mkdir();receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:
  if args.mode=='pin':result=c.prior.pin()
  else:
   receipt['targets']=r.target()
   if args.mode=='freeze':result=freeze(out)
   elif args.mode=='snapshot':result=snapshot(q.selected(),out)
   elif args.mode in ('prepare','native','live','evidence'):
    if args.mode in ('native','live'):assert json.loads((q.selected()/'host-status.json').read_bytes())['prepared.json' if args.mode=='native' else 'native.json']['status']=='passed'
    result=q.dispatch(q.selected(),args.mode)
   elif args.mode in ('status','collect'):result=getattr(q,args.mode)(q.selected());result.pop('cases',None)
   elif args.mode=='record-review':result=c.record(q.selected())
   elif args.mode=='approve':result=c.prior.old.prior.approve(q.selected())
   elif args.mode=='migrate':result=migrate(q.selected())
   elif args.mode in ('verify-held','verify-active'):
    r.prior.PRIVATE|={'research_model_reconciliations','research_autonomy_repairs','research_autonomy_repair_events'};result=c.prior.old.prior.verify(q.selected(),out,args.mode=='verify-active')
   elif args.mode=='verify-executors':result=c.prior.verify_executors(out)
   elif args.mode=='public-checks':result=c.prior.public_checks(out)
   elif args.mode in ('frontend-release','frontend-status'):result=frontend(q.selected(),args.mode=='frontend-release')
   elif args.mode=='apply-budget':result=budget(q.selected())
   elif args.mode=='record-release':result=retain(q.selected(),out)
  receipt.update(status='complete',result=result)
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:q.save(out/'receipt.json',receipt);print(json.dumps(dict(directory=str(out),**receipt)))
if __name__=='__main__':main()
