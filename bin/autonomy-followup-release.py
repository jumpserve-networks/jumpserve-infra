"""Fixed v8 release gates. Default check is local; other modes need release authorization."""
import argparse,base64,datetime as dt,hashlib,importlib.util,io,json,os,subprocess,urllib.error,urllib.request,zipfile
from pathlib import Path
from autonomy_trajectory_evidence import POLICY_PATH, publication_status
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prior_autonomy_release',ROOT/'bin/autonomy-release.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
sha=lambda b:hashlib.sha256(b).hexdigest()
MIGRATIONS=tuple('20261019000'+suffix for suffix in ('1_bounded_followups.sql','2_autonomy_prompt_v7.sql','3_autonomy_v7_publication_guard.sql','4_bounded_tcp_queue.sql','5_autonomy_prompt_v8.sql','6_autonomy_v8_publication_guard.sql','7_autonomy_v8_review_criteria.sql','8_autonomy_completion_publication_guard.sql','9_application_trajectory_guard.sql'))+('202610190010_rejected_turn_review.sql',)

def evidence_archive(directory, upload=False):
 # Only this feature's research fixtures, source profiles and reports. Never
 # include environment files, browser profiles, credentials or general logs.
 entries={}
 def add(path, name):
  if path.is_symlink() or not path.is_file():raise RuntimeError('Evidence must be an ordinary retained file: '+name)
  entries[name]=path
 for base in (ROOT/'.test-artifacts/autonomy-followups'/v for v in ('v1','v2','v3','v4','application-trajectory-v1','application-trajectory-v2','application-trajectory-v3')):
  for path in base.rglob('*'):
   if path.is_file():add(path,'jumpserve-infra/'+str(path.relative_to(ROOT)))
 for base in (p for p in (ROOT/'.test-artifacts/research-ideas/database').iterdir() if p.is_dir() and p.name.startswith(('20261019T','20261020T'))):
  for path in base.iterdir():
   if path.is_file() and (path.name=='autonomy-validation-report.json' or path.name.startswith('raw-')):add(path,'jumpserve-infra/'+str(path.relative_to(ROOT)))
 frontend=ROOT.parent/'jumpserve-front-end'
 for base in (frontend/'.test-artifacts/research-autonomy').glob('2026-10-19T*'):
  for path in base.iterdir():
   if path.is_file() and path.suffix in ('.json','.png','.html'):add(path,'jumpserve-front-end/'+str(path.relative_to(frontend)))
 files=[ROOT/'research-workflow-runtime.json']+[ROOT/'database'/n for n in MIGRATIONS]
 files.extend(ROOT/'database'/n for n in ('seed-autonomy-v7.json','seed-autonomy-v8.json'))
 files.extend(p for p in (ROOT/'docs').glob('autonomy-bounded-followups-*') if p.suffix in ('.json','.md') and p.name!='autonomy-bounded-followups-artifacts-v3.json')
 files.extend((POLICY_PATH,ROOT/'test/autonomy_trajectory_policy_test.py',ROOT/'bin/autonomy_trajectory_evidence.py'))
 files.append(ROOT/'test/evaluate_autonomy_trajectory.py')
 files.extend(ROOT/'test'/n for n in ('autonomy-followup-cases-v1.json','autonomy-followup-cases-v2.json','autonomy-followup-judgments-v3.json','evaluate_autonomy_followups.py','evaluate_autonomy_followup_completion.py','evaluate_autonomy_followup_completion_v2.py','autonomy_fixtures.py','check_autonomy_database.py','check_research_ideas_database.py','research-workflow.test.ts'))
 files.extend(ROOT/'bin'/n for n in ('autonomy-release.py','autonomy-followup-release.py','review-autonomy-followups.py','review-autonomy-trajectory.py','verify-bounded-autonomy-release.py','report-autonomy-followups.py','prepare-autonomy-followup-candidate.py','prepare-autonomy-v8-candidate.py'))
 files.append(ROOT/'lib/research-workflow.ts')
 for path in files:add(path,'jumpserve-infra/'+str(path.relative_to(ROOT)))
 for name in ('lib/research-autonomy.ts','lib/network-execution.ts','app/components/research-workflow/autonomous-assessments.tsx','app/components/research-workflow/networking-fields.tsx','app/components/research-ideas/network-protocol-editor.tsx','scripts/verify-research-autonomy.mjs','scripts/verify-autonomy-release.mjs','tests/research-autonomy.test.mjs'):add(frontend/name,'jumpserve-front-end/'+name)
 manifest=[];buffer=io.BytesIO();total=0
 with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  for name,path in sorted(entries.items()):
   raw=path.read_bytes();total+=len(raw)
   if total>100000000:raise RuntimeError('Evidence exceeds 100 MB original-byte bound')
   manifest.append(dict(path=name,sha256=sha(raw),bytes=len(raw)))
   entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(entry,raw)
  archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
 raw=buffer.getvalue()
 if len(raw)>32000000:raise RuntimeError('Evidence archive exceeds 32 MB upload bound')
 destination=directory/'original-evidence.zip';destination.write_bytes(raw)
 # Retrieve our stored bytes and independently verify every decompressed file.
 retrieved=destination.read_bytes()
 if sha(retrieved)!=sha(raw):raise RuntimeError('Local archive retrieval hash differs')
 with zipfile.ZipFile(io.BytesIO(retrieved)) as archive:
  if json.loads(archive.read('manifest.json'))!=manifest:raise RuntimeError('Archive manifest differs')
  for entry in manifest:
   content=archive.read(entry['path'])
   if sha(content)!=entry['sha256'] or len(content)!=entry['bytes']:raise RuntimeError('Archived original file hash differs')
 result=dict(version='autonomy-followup-artifacts-v3',sha256=sha(raw),bytes=len(raw),original_bytes=total,files=len(manifest),local_retrieval_hash_verified=True,all_member_hashes_verified=True,remote_retrieval_hash_verified=False,measured_storage_charges_usd=None,manifest=manifest)
 inventory=ROOT/'docs/autonomy-bounded-followups-artifacts-v3.json';encoded=(json.dumps(result,indent=2)+'\n').encode()
 if inventory.exists() and inventory.read_bytes()!=encoded and not upload:raise RuntimeError('Artifact inventory already exists; preserve it and create a versioned correction')
 if not inventory.exists():inventory.write_bytes(encoded)
 if upload:
  if prior.admin.query("select public from storage.buckets where id='research-workflow-raw'")!=[{'public':False}]:raise RuntimeError('Original archive bucket must be private')
  key=prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];path='release-verification/autonomy-followups-20261019/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path;headers={'apikey':key,'Authorization':'Bearer '+key}
  try:
   with prior.guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=60) as response:response.read(1000)
  except urllib.error.HTTPError as error:
   if error.code!=409:raise RuntimeError('Private follow-up archive upload failed: HTTP '+str(error.code)) from None
  with prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retrieved=response.read(32000001)
  if retrieved!=raw or sha(retrieved)!=sha(raw):raise RuntimeError('Remote original archive retrieval hash differs')
  status=200;public=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey']
  try:
   with prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':public,'Authorization':'Bearer '+public}),timeout=20) as response:response.read(1)
  except urllib.error.HTTPError as error:status=error.code
  if status not in (400,401,403,404):raise RuntimeError('Private original archive is anonymously accessible')
  result.update(bucket='research-workflow-raw',path=path,remote_retrieval_hash_verified=True,anonymous_status=status)
 return {k:v for k,v in result.items() if k!='manifest'}

def reviewed():
 base=ROOT/'.test-artifacts/autonomy-followups/v2';report=json.loads((base/'evaluation-reviewed.json').read_bytes());packet=json.loads((base/'frozen-inputs.json').read_bytes())
 seed=json.loads((ROOT/'database/seed-autonomy-v8.json').read_bytes());manifest=prior.queue.source();cases=json.loads((ROOT/'test/autonomy-followup-cases-v2.json').read_bytes())
 if report['prompt_version_id']!=seed['id'] or report['prompt_version']!=seed['version'] or report['live_provider_calls']!=9 or report['input_sha256']!=manifest['files'] or len(report['cases'])!=9 or {c['name'] for c in report['cases']}!={c['name'] for c in cases['cases']}:raise RuntimeError('Exact final candidate, source and nine cases required')
 if report['cases_sha256']!=sha((ROOT/'test/autonomy-followup-cases-v2.json').read_bytes()) or report['request_manifest_sha256']!=packet['request_manifest_sha256'] or report['prompt_content_sha256']!=sha((seed['system_prompt']+'\n\n'+seed['research_context']).encode()):raise RuntimeError('Frozen prompt/cases differ')
 if report['reviewer']['passed'] is not True or report.get('integration_passed') is not True or sha((ROOT/report['integration_report']).read_bytes())!=report['integration_report_sha256']:raise RuntimeError('Passing actual-answer and final integration reviews required')
 if not json.loads((ROOT/report['integration_report']).read_bytes())['passed']:raise RuntimeError('Integration report contains a release blocker')
 if report['judgment_criteria_sha256']!=sha((ROOT/'test/autonomy-followup-judgments-v3.json').read_bytes()) or report['review_amendment']!='autonomy-bounded-followups-amendment-v4' or report['original_strict_checks_passed']!=8 or report['original_strict_checks_total']!=9 or report['intermediate_only_cases']!=['earlier-partial-discrepancy']:raise RuntimeError('Explicit tuned criteria and original strict failures are required')
 for case in report['cases']:
  if case['status']!='complete' or case['passed'] is not True or case['raw_answer_reviewed'] is not True or case['rendered_answer_reviewed'] is not True or not all(case['deterministic_checks'].values()):raise RuntimeError('Every actual answer must pass; failed cases remain history')
  for ending,key in (('-provider.json','provider_response_sha256'),('-message.json','output_sha256'),('-request.json','request_sha256')):
   if sha((base/(case['name']+ending)).read_bytes())!=case[key]:raise RuntimeError('Original evaluation bytes changed')
 trajectory_path=ROOT/'.test-artifacts/autonomy-followups/application-trajectory-v3/evaluation-reviewed.json'
 if not trajectory_path.exists():raise RuntimeError('Trajectory verification pending under the application 25-attempt/$100/seven-day limits. The old two-turn observation is incomplete evidence, not an application failure.')
 trajectory=json.loads(trajectory_path.read_bytes())
 if publication_status(trajectory)!='eligible-for-review':raise RuntimeError('Trajectory evaluation is incomplete; valid evidence reads may continue within the original application limits.')
 if trajectory['reviewer']['passed'] is not True or trajectory['input_sha256']!=manifest['files'] or trajectory['policy_sha256']!=sha(POLICY_PATH.read_bytes()):raise RuntimeError('Trajectory policy/runtime/actual-answer review differs')
 for case in trajectory['cases']:
  rejected=case.get('status')=='provider-rejected'
  if not case['passed'] or (not rejected and (not case['raw_answer_reviewed'] or not case['rendered_answer_reviewed'])):raise RuntimeError('Trajectory actual-answer review missing')
  if rejected:
   if not case.get('no_answer_received') or case.get('failure_code')!='ThrottlingException' or not case.get('failure_reviewed') or not case.get('provider_attempt_not_replayed') or sha((trajectory_path.parent/(case['name']+'-error.bin')).read_bytes())!=case['failure_sha256']:raise RuntimeError('Explicit rejected-call provenance/review missing')
  for ending,key in (('-provider.json','provider_response_sha256'),('-message.json','output_sha256'),('-request.json','request_sha256')):
   if rejected and ending=='-message.json':continue
   if sha((trajectory_path.parent/(case['name']+ending)).read_bytes())!=case[key]:raise RuntimeError('Trajectory original bytes differ')
 report.update(trajectory_report=trajectory,trajectory_report_sha256=sha(trajectory_path.read_bytes()),trajectory_policy_sha256=sha(POLICY_PATH.read_bytes()))
 return report

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mode',choices=['check','migrate','publish','diff','deploy','activate','verify'],default='check');args=parser.parse_args()
 directory=ROOT/'.test-artifacts/autonomy-followup-release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
 receipt=dict(mode=args.mode,status='running',measured_charges_usd=None)
 def save():(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 try:
  if args.mode=='check':receipt['original_evidence']=evidence_archive(directory);save()
  report=reviewed();seed=json.loads((ROOT/'database/seed-autonomy-v8.json').read_bytes());receipt['candidate']=seed['id'];save()
  if args.mode=='check':receipt['local_evidence_passed']=True
  else:
   receipt['targets']=prior.guard.target();before=prior.pointers();receipt['pointers_before']=before;save()
   if args.mode=='migrate':
    if prior.admin.query("select to_regprocedure('public.research_autonomy_resume_context(uuid,uuid,uuid,text)') present")[0]['present'] is not None:raise RuntimeError('Migrations partly/already applied; inspect retained receipts before continuing')
    receipt['migrations']=[]
    for name in MIGRATIONS:
     raw=(ROOT/'database'/name).read_bytes();entry=dict(name=name,sha256=sha(raw),status='running');receipt['migrations'].append(entry);save();prior.admin.query(raw.decode(),read_only=False);entry['status']='complete';save()
    if prior.pointers()!=before:raise RuntimeError('A migration changed an active prompt pointer')
   elif args.mode=='publish':
    resources=prior.aws('cloudformation','list-stack-resources','--stack-name',prior.queue.STACK)['StackResourceSummaries']
    rules=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
    apis=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Lambda::Function' and r['LogicalResourceId'].startswith('ResearchWorkflowApi')]
    if len(rules)!=1 or len(apis)!=1 or prior.aws('events','describe-rule','--name',rules[0])['State']!='DISABLED':raise RuntimeError('Hold the old autonomous poll before publishing v8')
    admission=prior.aws('lambda','get-function-configuration','--function-name',apis[0]);changed=dt.datetime.fromisoformat(admission['LastModified'].replace('Z','+00:00'))
    if admission['Environment']['Variables'].get('RESEARCH_AUTONOMY_ENABLED')!='false' or (dt.datetime.now(dt.timezone.utc)-changed).total_seconds()<70:raise RuntimeError('Hold API admission and allow at least 70 seconds for previously queued notifications to expire')
    if prior.admin.query("select count(*) count from research_autonomy_tasks where status='running'")[0]['count']!=0 or prior.admin.query("select count(*) count from research_autonomy_turns where status='running'")[0]['count']!=0:raise RuntimeError('Hold admission/polling and drain running turns before switching prompt versions')
    active=next(r['active_version_id'] for r in before if r['module_id']=='research-autonomy')
    if active not in (None,'83e26515-7b18-5730-9473-f34555a1a1b4',seed['id']):raise RuntimeError('Unexpected active autonomy prompt')
    receipt['original_evidence']=evidence_archive(directory,upload=True);report['release_artifacts']=receipt['original_evidence'];save()
    values=[prior.admin.literal(seed['id'])+'::uuid',prior.admin.literal(active)+'::uuid' if active else 'null::uuid',prior.admin.literal(report['prompt_content_sha256']),prior.admin.literal(json.dumps(report))+'::jsonb',prior.admin.literal('Codex AI implementer; explicitly authorized v8 release'),prior.admin.literal('research-autonomy')]
    receipt['publication']=prior.admin.query('select public.publish_agent_prompt('+','.join(values)+')',read_only=False)
   elif args.mode in ('diff','deploy','activate'):
    manifest=prior.queue.source();backend=ROOT.parent/'jumpserve-back-end'
    if subprocess.check_output(['git','status','--porcelain'],cwd=backend,text=True).strip() or subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=manifest['source_revision']:raise RuntimeError('Commit and pin the exact clean backend before deployment')
    if args.mode!='diff' and next(r['active_version_id'] for r in before if r['module_id']=='research-autonomy')!=seed['id']:raise RuntimeError('Publish the passing v8 prompt before runtime deployment')
    if args.mode=='activate':prior.functions(directory,True)
    prior.security();previous=prior.queue.state();credentials=prior.aws('configure','export-credentials','--format','process');env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
    command=['npm','run','cdk:benchmark','--','diff' if args.mode=='diff' else 'deploy',prior.queue.STACK,'-c','researchAutonomyEnabled=true','-c','researchAutonomyAdmissionEnabled='+('true' if args.mode=='activate' else 'false')];command+=['--no-change-set'] if args.mode=='diff' else ['--require-approval','never','--outputs-file',str(directory/'outputs.json')];receipt['command']=command;save()
    with (directory/'cdk.log').open('w') as stream:result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
    if result.returncode:raise RuntimeError('Scoped deployment failed; original log retained')
    if prior.queue.state()['parameters']!=previous['parameters']:raise RuntimeError('Existing stack parameters changed')
   else:
    functions=prior.functions(directory,True);worker=next(r for r in functions if r['handler']=='worker.handler');config=prior.aws('lambda','get-function-configuration','--function-name',worker['arn']);target=config['Environment']['Variables']['NETWORK_BOUNDED_FUNCTION'];bound=prior.aws('lambda','get-function','--function-name',target)
    if not target.rsplit(':',1)[-1].isdigit() or bound['Configuration']['MemorySize']!=128 or bound['Configuration']['Timeout']!=5:raise RuntimeError('Deployed bounded version/resources differ')
    with prior.guard.OPEN.open(bound['Code']['Location'],timeout=30) as response:raw=response.read(1000001)
    if base64.b64encode(hashlib.sha256(raw).digest()).decode()!=bound['Configuration']['CodeSha256']:raise RuntimeError('Deployed bounded ZIP hash differs')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
     if sha(archive.read('index.py'))!=report['input_sha256']['bounded_network.py']:raise RuntimeError('Deployed bounded implementation differs')
    (directory/'bounded-original.zip').write_bytes(raw);receipt['deployed_functions']=functions;receipt['bounded_version']=dict(arn=target,zip_sha256=sha(raw),source_sha256=report['input_sha256']['bounded_network.py'])
  receipt['status']='complete'
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:save();print(json.dumps(dict(mode=args.mode,status=receipt['status'],directory=str(directory))))

if __name__=='__main__':main()
