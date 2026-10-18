"""Fixed-target autonomous assessment release. No arbitrary commands or SQL inputs."""
import argparse,base64,datetime as dt,hashlib,importlib.util,io,json,os,subprocess,urllib.error,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('autonomy_queue_release',ROOT/'bin/research-queue-release.py');queue=importlib.util.module_from_spec(spec);spec.loader.exec_module(queue)
guard=queue.guard;admin=guard.admin;aws=queue.aws
MODULE='research-autonomy';CANDIDATE='cc0c5299-e41d-588f-9d00-cf4d817bf72b'
PRIVATE={'research_autonomy_'+n for n in ('workflows','tasks','turns','job_commitments','events')}
MIGRATIONS=('202610180002_autonomous_assessments.sql','202610180003_autonomy_prompt_candidate.sql','202610180004_autonomy_publication_guard.sql','202610180005_autonomy_prompt_v2.sql','202610180006_autonomy_v2_publication_guard.sql','202610180007_autonomy_prompt_v3.sql','202610180008_autonomy_v3_publication_guard.sql','202610180009_autonomy_prompt_v4.sql','202610180010_autonomy_v4_publication_guard.sql','202610180011_autonomy_prompt_v5.sql','202610180012_autonomy_v5_publication_guard.sql','202610180013_autonomy_provider_recovery_guard.sql')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def pointers():return admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id')
def security():
 old=queue.PRIVATE
 try:queue.PRIVATE=old|PRIVATE|{'research_claim_designs'};result=queue.security()
 finally:queue.PRIVATE=old
 funcs=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ('research_autonomy_control','publish_agent_prompt')")
 if len(funcs)!=2 or any(r['anon_execute'] or r['browser_execute'] for r in funcs):raise RuntimeError('Autonomous service-only RPC permissions differ')
 result['autonomy_functions']=funcs;return result
def reviewed():
 paths=[p for p in (ROOT/'.test-artifacts/autonomy-evaluation').glob('*/evaluation-reviewed.json') if json.loads(p.read_bytes())['prompt_version_id']==CANDIDATE and json.loads(p.read_bytes())['reviewer']['passed'] is True]
 if len(paths)!=1:raise RuntimeError('Exactly one passing reviewed candidate campaign is required')
 report=json.loads(paths[0].read_bytes());lock=json.loads((ROOT/'test/autonomy-implementation-lock-v5.json').read_bytes())
 if report['prompt_version_id']!=CANDIDATE or report['live_provider_calls']!=19 or report['prior_live_provider_calls']!=14 or report['prior_failed_provider_calls']!=5 or report['new_provider_calls']!=5 or report['reused_answer_count']!=9 or report['reviewer']['passed'] is not True or len(report['cases'])!=14 or not all(c['passed'] and c['status']=='complete' and c['raw_answer_reviewed'] and c['rendered_answer_reviewed'] and all(c['deterministic_checks'].values()) for c in report['cases']):raise RuntimeError('Actual-answer publication criteria failed')
 source=ROOT/report['recovery_source_report'];original=json.loads(source.read_bytes())
 if sha(source.read_bytes())!=report['recovery_source_sha256'] or original['prompt_version_id']!=CANDIDATE or original['live_provider_calls']!=14:raise RuntimeError('Original recovery campaign differs')
 if sum(c['answer_provenance']=='reused-completed-answer' for c in report['cases'])!=9 or sum(c['answer_provenance']=='new-provider-call' for c in report['cases'])!=5:raise RuntimeError('Recovery answer accounting differs')
 for name,digest in lock['files'].items():
  if report['input_sha256'].get(name)!=digest or sha((ROOT.parent/'jumpserve-back-end/research_workflow'/name).read_bytes())!=digest:raise RuntimeError('Reviewed implementation differs')
 for c in report['cases']:
  raw=(paths[0].parent/(c['name']+'-provider.json')).read_bytes()
  if sha(raw)!=c['provider_response_sha256']:raise RuntimeError('Original provider bytes differ')
  old=next(x for x in original['cases'] if x['name']==c['name'])
  if c['answer_provenance']=='reused-completed-answer':
   if old['status']!='complete' or raw!=(source.parent/(c['name']+'-provider.json')).read_bytes():raise RuntimeError('Reused answer differs')
  elif old['status']!='failed' or (source.parent/(c['name']+'-provider.json')).read_bytes()!=b'':raise RuntimeError('Only unanswered failed calls may be recovered')
  message=json.dumps(json.loads(raw)['output']['message'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
  if sha(message)!=c['output_sha256']:raise RuntimeError('Original message differs')
 seed=json.loads((ROOT/'database/seed-autonomy-v5.json').read_bytes())
 if sha((seed['system_prompt']+'\n\n'+seed['research_context']).encode())!=report['prompt_content_sha256']:raise RuntimeError('Reviewed prompt differs')
 return report
def bundle(directory):
 entries=[]
 for base in (ROOT/'.test-artifacts/autonomy-evaluation',ROOT/'docs/autonomous-assessment-validation-v1',ROOT/'docs/autonomous-assessment-production-evidence-v1'):
  entries.extend(p for p in base.rglob('*') if p.is_file())
 entries.extend(ROOT/'docs'/n for n in ('autonomous-assessment-production-protocol-v1.md','autonomous-assessment-production-amendment-v2.md','autonomous-assessment-production-amendment-v3.md','autonomous-assessment-production-amendment-v4.md','autonomous-assessment-production-amendment-v5.md','autonomous-assessment-production-amendment-v6.md','autonomous-assessment-protocol-v1.md','autonomous-assessments.md','autonomous-assessment-validation-v1.md','autonomous-assessment-validation-v1.json'))
 entries.extend(ROOT/'database'/n for n in MIGRATIONS)
 manifest=[];buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  for path in sorted(entries):
   raw=path.read_bytes();name=str(path.relative_to(ROOT));manifest.append(dict(path=name,sha256=sha(raw),bytes=len(raw)));entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(entry,raw)
  archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
 raw=buffer.getvalue()
 if len(raw)>32000000:raise RuntimeError('Evidence archive exceeds declared bound')
 (directory/'original-evidence.zip').write_bytes(raw)
 key=aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];path='release-verification/autonomy-20261018/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path;headers={'apikey':key,'Authorization':'Bearer '+key}
 try:
  with guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=60) as response:response.read(1000)
 except urllib.error.HTTPError as error:
  if error.code!=409:raise RuntimeError('Private archive upload failed: HTTP '+str(error.code)) from None
 with guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retrieved=response.read(32000001)
 if sha(retrieved)!=sha(raw) or retrieved!=raw:raise RuntimeError('Downloaded archive bytes differ')
 status=200;public=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey']
 try:
  with guard.OPEN.open(urllib.request.Request(url,headers={'apikey':public}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as error:status=error.code
 if status not in (400,401,403,404):raise RuntimeError('Original archive is anonymously accessible')
 return dict(bucket='research-workflow-raw',path=path,sha256=sha(raw),bytes=len(raw),files=len(manifest),retrieved_hash_verified=True,anonymous_status=status,measured_storage_charges_usd=None)
def functions(directory,expected=False):
 resources=aws('cloudformation','list-stack-resources','--stack-name',queue.STACK)['StackResourceSummaries'];out=[]
 for resource in resources:
  if resource['ResourceType']!='AWS::Lambda::Function' or not resource['LogicalResourceId'].startswith(('ResearchWorkflowApi','ResearchWorkflowQueueWorker','ResearchWorkflowAutonomyWorker')):continue
  value=aws('lambda','get-function','--function-name',resource['PhysicalResourceId']);config=value['Configuration'];environment=config['Environment']['Variables']
  if ':395567831870:' not in config['FunctionArn'] or environment['SUPABASE_URL']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Function target differs')
  with guard.OPEN.open(value['Code']['Location'],timeout=30) as response:raw=response.read(8000001)
  if len(raw)>8000000 or base64.b64encode(hashlib.sha256(raw).digest()).decode()!=config['CodeSha256']:raise RuntimeError('Deployed original ZIP hash differs')
  (directory/(config['FunctionName']+'.zip')).write_bytes(raw);manifest=queue.source()
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   hashes={name:sha(archive.read(name)) for name in manifest['files'] if name in archive.namelist()}
   if expected and hashes!=manifest['files']:raise RuntimeError('Deployed runtime differs from exact committed manifest')
  out.append(dict(logical_id=resource['LogicalResourceId'],function=config['FunctionName'],arn=config['FunctionArn'],zip_sha256=sha(raw),source_hashes=hashes,handler=config['Handler'],runtime=config['Runtime'],memory_mb=config['MemorySize'],timeout=config['Timeout'],layers=config.get('Layers',[]),autonomy_enabled=environment.get('RESEARCH_AUTONOMY_ENABLED'),worker_target=environment.get('RESEARCH_AUTONOMY_WORKER_FUNCTION')))
 if len(out)!=(3 if expected else 2):raise RuntimeError('Unexpected research function inventory')
 return out
def verify(directory):
 result=dict(security=security(),functions=functions(directory,True))
 active=admin.query("select v.id,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id='research-autonomy'")
 if len(active)!=1 or active[0]['id']!=CANDIDATE or active[0]['content_sha256']!=reviewed()['prompt_content_sha256']:raise RuntimeError('Evaluated autonomous prompt is not active')
 with guard.OPEN.open(queue.BASE+'/capabilities',timeout=30) as response:capability=json.load(response)
 if capability['autonomy']['version']!='research-autonomy-v1' or capability['autonomy']['enabled'] is not True:raise RuntimeError('Autonomous API capability is not active')
 result.update(active_prompt=active,capabilities=capability,anonymous_checks=[])
 for path in ('/queue','/studies/10000000-0000-4000-8000-000000000001/autonomy'):
  try:
   with guard.OPEN.open(queue.BASE+path,timeout=20) as response:status=response.status
  except urllib.error.HTTPError as error:status=error.code
  if status not in (401,403):raise RuntimeError('Anonymous private endpoint was not denied')
  result['anonymous_checks'].append(dict(path=path,status=status))
 resources=aws('cloudformation','list-stack-resources','--stack-name',queue.STACK)['StackResourceSummaries'];rules=[r for r in resources if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
 if len(rules)!=1:raise RuntimeError('Durable controller schedule missing')
 rule=aws('events','describe-rule','--name',rules[0]['PhysicalResourceId'])
 if rule['State']!='ENABLED' or rule['ScheduleExpression']!='rate(1 minute)':raise RuntimeError('Controller schedule differs')
 result['schedule']={k:rule[k] for k in ('Name','State','ScheduleExpression')};return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('inspect','migrate','publish','diff','deploy','verify','archive','frontend-release','frontend-status'));a=p.parse_args()
 directory=ROOT/'.test-artifacts/autonomy-release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,exist_ok=False)
 receipt=dict(protocol='autonomous-assessment-production-protocol-v1',mode=a.mode,status='running',started_at=stamp(),measured_charges_usd=None,authorization='Current explicit user request to merge main and deploy this release',new_experiment_instances=0)
 def save():(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 save()
 try:
  receipt['targets']=guard.target();receipt['prompt_pointers_before']=before=pointers();save()
  if a.mode=='inspect':
   receipt['inspection']=guard.inspect();receipt['rollback_functions']=functions(directory)
  elif a.mode=='migrate':
   if admin.query("select to_regclass('public.research_autonomy_workflows') present")[0]['present'] is not None:raise RuntimeError('Autonomy migrations partly/already applied; inspect retained receipts')
   receipt['migrations']=[]
   for name in MIGRATIONS:
    raw=(ROOT/'database'/name).read_bytes();entry=dict(name=name,sha256=sha(raw),bytes=len(raw),status='running');receipt['migrations'].append(entry);save();admin.query(raw.decode(),read_only=False);entry.update(status='complete',ended_at=stamp());save()
   if [r for r in pointers() if r['module_id']!=MODULE]!=before:raise RuntimeError('Other active prompt pointers changed')
   receipt['security']=security()
  elif a.mode=='publish':
   report=reviewed();receipt['original_evidence']=bundle(directory);report['release_artifacts']=receipt['original_evidence'];save()
   active=next(r['active_version_id'] for r in before if r['module_id']==MODULE)
   if active not in (None,CANDIDATE):raise RuntimeError('Unexpected autonomous prompt is active')
   if active is None:
    args=[admin.literal(CANDIDATE)+'::uuid','null::uuid',admin.literal(report['prompt_content_sha256']),admin.literal(json.dumps(report))+'::jsonb',admin.literal('Codex AI implementer; user-authorized production release'),admin.literal(MODULE)]
    receipt['publication']=admin.query('select publish_agent_prompt('+','.join(args)+')',read_only=False)
   receipt['pointers_after']=pointers()
  elif a.mode in ('diff','deploy'):
   manifest=queue.source();receipt['manifest']=manifest;receipt['stack_before']=queue.state()
   if a.mode=='deploy':
    security();reviewed();backend=ROOT.parent/'jumpserve-back-end'
    if subprocess.check_output(['git','status','--porcelain'],cwd=backend,text=True).strip() or subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=manifest['source_revision']:raise RuntimeError('Exact committed clean backend revision required')
    if next(r['active_version_id'] for r in before if r['module_id']==MODULE)!=CANDIDATE:raise RuntimeError('Passing evaluated prompt must be active before deployment')
   credentials=aws('configure','export-credentials','--format','process');env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
   command=['npm','run','cdk:benchmark','--',a.mode,queue.STACK,'-c','researchAutonomyEnabled=true'];command+=['--no-change-set'] if a.mode=='diff' else ['--require-approval','never','--outputs-file',str(directory/'outputs.json')];receipt['command']=command;save()
   with (directory/'cdk.log').open('w') as log:r=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
   if r.returncode:raise RuntimeError('Scoped CDK operation failed; cdk.log retained')
   if a.mode=='deploy':
    receipt['stack_after']=queue.state()
    if receipt['stack_after']['parameters']!=receipt['stack_before']['parameters']:raise RuntimeError('Existing benchmark parameters changed')
  elif a.mode=='verify':receipt['verification']=verify(directory)
  elif a.mode=='archive':receipt['original_evidence']=bundle(directory)
  elif a.mode=='frontend-release':
   resources=aws('cloudformation','list-stack-resources','--stack-name',queue.STACK)['StackResourceSummaries']
   if not any(r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyWorker') for r in resources):raise RuntimeError('Backend must be deployed before frontend')
   jobs=aws('amplify','list-jobs','--app-id','d24jvguj7brnkj','--branch-name','main','--max-results','3')['jobSummaries'];revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent/'jumpserve-front-end',text=True).strip()
   if not any(j.get('commitId')==revision and j['status'] in ('PENDING','PROVISIONING','RUNNING','SUCCEED') for j in jobs):receipt['build']=aws('amplify','start-job','--app-id','d24jvguj7brnkj','--branch-name','main','--job-type','RELEASE','--commit-id',revision)
   else:receipt['existing_builds']=jobs
  else:receipt['jobs']=aws('amplify','list-jobs','--app-id','d24jvguj7brnkj','--branch-name','main','--max-results','3')['jobSummaries']
  receipt['status']='complete'
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:receipt['ended_at']=stamp();save();print(json.dumps(dict(directory=str(directory),mode=a.mode,status=receipt['status'],reason=receipt.get('reason'))))

if __name__=='__main__':main()
