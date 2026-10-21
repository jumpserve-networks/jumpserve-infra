"""Fixed-target PDF ingestion release; leaves published AI prompts unchanged."""
import argparse, datetime as dt, hashlib, importlib.util, io, json, os, subprocess, urllib.error, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paper_prior',ROOT/'bin/autonomy-release.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
MIGRATION='202610200001_private_paper_uploads.sql'
PROMPT='20934b76-08d7-55e9-b101-1bed29db42a0'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
stamp=lambda:dt.datetime.now(dt.timezone.utc).isoformat()

def security():
 result=prior.security()
 bucket=prior.admin.query("select id,public,file_size_limit,allowed_mime_types from storage.buckets where id='research-paper-uploads'")
 if bucket!=[dict(id='research-paper-uploads',public=False,file_size_limit=10000000,allowed_mime_types=['application/pdf'])]:raise RuntimeError('Private PDF bucket differs')
 funcs=prior.admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ('research_paper_upload','research_create_study') order by proname")
 if len(funcs)!=2 or any(r['anon_execute'] or r['browser_execute'] for r in funcs):raise RuntimeError('PDF RPC must remain service-only')
 result.update(upload_bucket=bucket,upload_functions=funcs)
 return result

def control(directory):
 # Blank PDF is a software control, never an academic paper or model input.
 import sys, io
 sys.path.insert(0,str(ROOT/'.runtime-autonomy-python/python'))
 from pypdf import PdfWriter
 writer=PdfWriter();writer.add_blank_page(width=400,height=400);buffer=io.BytesIO();writer.write(buffer);raw=buffer.getvalue()
 filename='JumpServe PDF upload release control.pdf';(directory/filename).write_bytes(raw)
 result=dict(filename=filename,sha256=sha(raw),byte_count=len(raw),text_claims=0,expected_state='missing-text; no model call',data_origin='synthetic software release control')
 (directory/'control.json').write_text(json.dumps(result,indent=2)+'\n')
 return result

def storage(directory):
 key=prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
 public=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey']
 origin='https://regphejnlvfpyokpniny.supabase.co/storage/v1'
 raw=(directory/'JumpServe PDF upload release control.pdf').read_bytes()
 prefix='release-verification/pdf-20261020/'+directory.name+'/'
 def request(path,method='GET',data=None,headers=None):
  try:
   with prior.guard.OPEN.open(urllib.request.Request(origin+path,data=data,method=method,headers=headers or {}),timeout=60) as response:return response.status,response.read(10100001)
  except urllib.error.HTTPError as error:return error.code,error.read(2000)
 def signed(name):
  path=prefix+name;status,body=request('/object/upload/sign/research-paper-uploads/'+path,'POST',b'{}',{'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  if status!=200:raise RuntimeError('Signed permission failed HTTP '+str(status))
  url=json.loads(body)['url']
  if not url.startswith('/object/upload/sign/research-paper-uploads/'+path+'?token='):raise RuntimeError('Scoped signed path differs')
  return path,url
 path,url=signed('original.pdf');status,_=request(url,'PUT',raw,{'apikey':public,'Content-Type':'application/pdf'})
 if status!=200:raise RuntimeError('Signed PDF PUT failed HTTP '+str(status))
 status,stored=request('/object/research-paper-uploads/'+path,headers={'apikey':key,'Authorization':'Bearer '+key})
 if status!=200 or stored!=raw:raise RuntimeError('Remote original bytes differ')
 public_status,_=request('/object/research-paper-uploads/'+path,headers={'apikey':public})
 if public_status not in (400,401,403,404):raise RuntimeError('Original is anonymously readable')
 overwrite,_=request(url,'PUT',raw,{'apikey':public,'Content-Type':'application/pdf'})
 if overwrite not in (400,409):raise RuntimeError('Signed permission permits overwrite')
 _,wrong=signed('wrong-type.pdf');mime,_=request(wrong,'PUT',raw,{'apikey':public,'Content-Type':'text/plain'})
 if mime not in (400,415,422):raise RuntimeError('Wrong MIME was accepted')
 _,large=signed('oversize.pdf');oversize,_=request(large,'PUT',b'%PDF-1.4\n'+b'0'*(10000001-9),{'apikey':public,'Content-Type':'application/pdf'})
 if oversize not in (400,413,422):raise RuntimeError('Oversize was accepted')
 return dict(original_path=path,original_sha256=sha(raw),retrieved_sha256=sha(stored),retrieved_bytes=len(stored),signed_put_status=200,anonymous_read_status=public_status,overwrite_status=overwrite,wrong_mime_status=mime,oversize_status=oversize,oversize_attempt_bytes=10000001,credentials_retained=False)

def control_read(directory):
 expected='41ca0ee1d6ec3a96190266e38063a2c20b7a9cea652eb73f395d461f62244077'
 rows=prior.admin.query("select id,title,paper_url,paper_upload from research_studies where title='JumpServe PDF upload release control R2' and paper_upload->>'sha256'="+prior.admin.literal(expected))
 if len(rows)!=1:raise RuntimeError('Expected exactly one browser-created private release control')
 study=rows[0];condition=' where study_id='+prior.admin.literal(study['id'])+'::uuid'
 result=dict(study=study)
 for table,projection in (('research_autonomy_workflows','*'),('research_autonomy_tasks','*'),('research_autonomy_turns','id,status,stage,number'),('research_sources','*'),('research_artifacts','*'),('research_claims','id'),('research_audit_events','action,details,created_at')):
  result[table]=prior.admin.query('select '+projection+' from '+table+condition)
 workflows=result['research_autonomy_workflows'];tasks=result['research_autonomy_tasks']
 if len(workflows)!=1 or len(tasks)!=1 or result['research_autonomy_turns'] or result['research_claims']:raise RuntimeError('Blank control must have one intake and no claims or model turns')
 w=workflows[0]
 if sha(w['initial_prompt'].encode())!=w['initial_sha256'] or (w['max_spend_cents'],w['max_attempts'])!=(10000,None):raise RuntimeError('Initial prompt integrity or limits differ')
 if tasks[0]['status']!='blocked' or w['status']!='completed-with-blockers':raise RuntimeError('Wait for the deployed parser and explicit blank-PDF blocker before completing verification')
 key=prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key}
 result['retrieved_artifacts']=[]
 packets=[]
 for artifact in result['research_artifacts']:
  url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+artifact['storage_path']
  with prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=30) as response:raw=response.read(10000001)
  if len(raw)!=artifact['byte_count'] or sha(raw)!=artifact['sha256']:raise RuntimeError('Stored original or parsed artifact differs')
  path=directory/(artifact['id']+'.bin');path.write_bytes(raw)
  result['retrieved_artifacts'].append(dict(id=artifact['id'],sha256=sha(raw),bytes=len(raw),path=path.name,provenance=artifact['provenance']))
  if artifact['provenance'].get('kind')=='derived-pdf-text':packets.append(json.loads(raw))
 if len(packets)!=1 or packets[0]['tool_version']!='6.19.0' or packets[0]['original_sha256']!=expected or len(packets[0]['pages'])!=1 or packets[0]['pages'][0]['status']!='missing-text-layer':raise RuntimeError('Require actual pypdf text packet; a dependency failure is a release blocker')
 result['actual_pdf_parser']=dict(version=packets[0]['tool_version'],original_sha256=expected,missing_text_pages=[1],packet_hash_verified=True)
 if not any(a['sha256']==expected for a in result['retrieved_artifacts']):raise RuntimeError('Original PDF artifact missing')
 result['upload']=prior.admin.query('select id,status,reason,original_artifact_id from research_paper_uploads where id='+prior.admin.literal(study['id'])+'::uuid')
 if len(result['upload'])!=1 or result['upload'][0]['status']!='started':raise RuntimeError('Upload was not finalized')
 result['data_origin']='Synthetic blank software control; no scientific finding or actual-model evaluation'
 return result

def archive(directory):
 entries={}
 def add(path,name):
  if path.is_symlink() or not path.is_file():raise RuntimeError('Evidence must be an ordinary file')
  entries[name]=path
 for base in (ROOT/'.test-artifacts/private-paper-release',ROOT/'.test-artifacts/private-paper-production-browser',ROOT.parent/'jumpserve-front-end/.test-artifacts/private-paper-production-browser'):
  if base.exists():
   for path in base.rglob('*'):
    if path.is_file() and path.parent!=directory:add(path,str(path.relative_to(ROOT.parent)))
 for base in (ROOT/'.test-artifacts/research-ideas/database').glob('20261020T*'):
  for path in base.iterdir():
   if path.is_file() and (path.name.startswith('raw-') or path.name.endswith('-report.json') or path.name=='database-fixture-snapshot.json'):add(path,'jumpserve-infra/'+str(path.relative_to(ROOT)))
 inventory=json.loads((ROOT/'docs/private-paper-uploads-validation-v1.json').read_bytes())
 for entry in inventory['evidence']:
  path=ROOT.parent/entry['path']
  # The original development profile was reconstructed and its exact bytes
  # checked against this preexisting inventory before the commit pin changed.
  if entry['path'].endswith('/research-workflow-runtime.json'):
   path=ROOT/'.test-artifacts/private-paper-release/original-local-profile/runtime-development-v28.json'
   if sha(path.read_bytes())!=entry['sha256']:raise RuntimeError('Original development profile bytes differ')
   add(path,'development-input/research-workflow-runtime.json');continue
  if sha(path.read_bytes())!=entry['sha256']:raise RuntimeError('Original local evidence changed: '+entry['path'])
  add(path,entry['path'])
 for path in (ROOT/'docs').glob('private-paper*'):
  if path.is_file():add(path,'jumpserve-infra/'+str(path.relative_to(ROOT)))
 for path in (ROOT/'research-workflow-runtime.json',ROOT/'database'/MIGRATION,ROOT/'bin/private-paper-release.py',ROOT/'test/private-paper-browser-recorder.mjs'):add(path,'jumpserve-infra/'+str(path.relative_to(ROOT)))
 frontend=ROOT.parent/'jumpserve-front-end'
 for base in (frontend/'.test-artifacts/research-autonomy').glob('2026-10-20T*'):
  for path in base.iterdir():
   if path.is_file() and path.suffix in ('.png','.json'):add(path,'jumpserve-front-end/'+str(path.relative_to(frontend)))
 for base in (frontend/'.test-artifacts/autonomy-release-production').glob('2026-10-20T*'):
  for path in base.iterdir():
   if path.is_file() and path.suffix in ('.png','.json'):add(path,'jumpserve-front-end/'+str(path.relative_to(frontend)))
 manifest=[];out=io.BytesIO();total=0
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,path in sorted(entries.items()):
   raw=path.read_bytes();total+=len(raw)
   if total>100000000:raise RuntimeError('Evidence exceeds 100 MB original-byte bound')
   manifest.append(dict(path=name,sha256=sha(raw),bytes=len(raw)));entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;z.writestr(entry,raw)
  z.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
 raw=out.getvalue()
 if len(raw)>32000000:raise RuntimeError('Evidence archive exceeds 32 MB upload bound')
 (directory/'original-evidence.zip').write_bytes(raw)
 key=prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];path='release-verification/private-paper-20261020/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path;headers={'apikey':key,'Authorization':'Bearer '+key}
 try:
  with prior.guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=60) as response:response.read(1000)
 except urllib.error.HTTPError as error:
  if error.code!=409:raise RuntimeError('Private evidence upload failed HTTP '+str(error.code)) from None
 with prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:stored=response.read(32000001)
 if stored!=raw or sha(stored)!=sha(raw):raise RuntimeError('Remote evidence archive hash differs')
 with zipfile.ZipFile(io.BytesIO(stored)) as z:
  if json.loads(z.read('manifest.json'))!=manifest:raise RuntimeError('Stored archive manifest differs')
  for member in manifest:
   content=z.read(member['path'])
   if sha(content)!=member['sha256'] or len(content)!=member['bytes']:raise RuntimeError('Original archived member differs')
 public=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
 try:
  with prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':public}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as error:status=error.code
 if status not in (400,401,403,404):raise RuntimeError('Private evidence archive is anonymously accessible')
 return dict(bucket='research-workflow-raw',path=path,sha256=sha(raw),bytes=len(raw),original_bytes=total,files=len(manifest),retrieved_hash_verified=True,all_member_hashes_verified=True,anonymous_status=status,measured_storage_charges_usd=None)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('inspect','migrate','diff','deploy','activate','repair','verify','storage','control-read','archive','frontend-status'));a=p.parse_args()
 directory=ROOT/'.test-artifacts/private-paper-release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
 receipt=dict(protocol='private-paper-upload-release-protocol-v1',mode=a.mode,status='running',started_at=stamp(),measured_charges_usd=None,new_application_model_calls=0,new_experiment_instances=0)
 def save():(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 save()
 try:
  receipt['targets']=prior.guard.target();before=prior.pointers();receipt['prompt_pointers_before']=before;save()
  if next(r['active_version_id'] for r in before if r['module_id']=='research-autonomy')!=PROMPT:raise RuntimeError('Unexpected active autonomy prompt; never change it in this release')
  if a.mode=='inspect':
   receipt['inspection']=prior.guard.inspect();receipt['rollback_functions']=prior.functions(directory,False);receipt['control']=control(directory)
  elif a.mode=='migrate':
   if prior.admin.query("select to_regclass('public.research_paper_uploads') present")[0]['present'] is not None:raise RuntimeError('PDF schema already exists; inspect prior receipt before continuing')
   if prior.admin.query("select count(*) count from research_autonomy_tasks where status='running'")[0]['count'] or prior.admin.query("select count(*) count from research_autonomy_turns where status='running'")[0]['count']:raise RuntimeError('Drain running autonomous tasks before migration')
   raw=(ROOT/'database'/MIGRATION).read_bytes();receipt['migration']=dict(name=MIGRATION,sha256=sha(raw),bytes=len(raw),status='running');save();prior.admin.query(raw.decode(),read_only=False);receipt['migration']['status']='complete';save();receipt['security']=security()
  elif a.mode in ('diff','deploy','activate','repair'):
   manifest=prior.queue.source();backend=ROOT.parent/'jumpserve-back-end'
   if subprocess.check_output(['git','status','--porcelain'],cwd=backend,text=True).strip() or subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=manifest['source_revision']:raise RuntimeError('Clean committed backend and exact runtime manifest required')
   receipt['security']=security();previous=prior.queue.state()
   if a.mode=='activate':receipt['functions_before_activation']=prior.functions(directory,True)
   credentials=prior.aws('configure','export-credentials','--format','process');env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
   command=['npm','run','cdk:benchmark','--','diff' if a.mode=='diff' else 'deploy',prior.queue.STACK,'-c','researchAutonomyEnabled=true','-c','researchAutonomyAdmissionEnabled='+('true' if a.mode in ('activate','repair') else 'false')]
   command+=['--no-change-set'] if a.mode=='diff' else ['--require-approval','never','--outputs-file',str(directory/'outputs.json')]
   receipt['command']=command;save()
   with (directory/'cdk.log').open('w') as logfile:result=subprocess.run(command,cwd=ROOT,env=env,stdout=logfile,stderr=subprocess.STDOUT,timeout=1800)
   if result.returncode:raise RuntimeError('Scoped CDK command failed; retained cdk.log')
   if prior.queue.state()['parameters']!=previous['parameters']:raise RuntimeError('Existing stack parameters changed')
   if a.mode in ('activate','repair'):
    deployed=prior.functions(directory,True)
    if a.mode=='repair':
     api=next(f for f in deployed if f['handler']=='api.handler');config=prior.aws('lambda','get-function-configuration','--function-name',api['function']);environment=dict(config['Environment']['Variables']);environment['RESEARCH_AUTONOMY_ENABLED']='true'
     updated=prior.aws('lambda','update-function-configuration','--function-name',api['function'],'--environment',json.dumps(dict(Variables=environment)));receipt['restored_admission']=dict(function=api['function'],last_update_status=updated.get('LastUpdateStatus'))
    resources=prior.aws('cloudformation','list-stack-resources','--stack-name',prior.queue.STACK)['StackResourceSummaries'];rules=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
    if len(rules)!=1:raise RuntimeError('Autonomy rule inventory differs')
    subprocess.run(['aws','events','enable-rule','--name',rules[0],'--profile','jumpserve','--region','us-east-1'],check=True,timeout=60);receipt['autonomy_poll_restored']=rules[0]
  elif a.mode=='storage':receipt['control']=control(directory);receipt['remote_storage']=storage(directory)
  elif a.mode=='control-read':receipt['browser_control']=control_read(directory)
  elif a.mode=='archive':receipt['original_evidence']=archive(directory)
  elif a.mode=='frontend-status':
   job=prior.aws('amplify','get-job','--app-id','d24jvguj7brnkj','--branch-name','main','--job-id','118')['job']
   if job['summary']['commitId']!='cc03ebfa33042fd4a4856a1faf8f5c1fcd24f6e3':raise RuntimeError('Frontend source differs')
   receipt['frontend']={key:job['summary'].get(key) for key in ('jobId','status','commitId','startTime','endTime')};receipt['frontend']['steps']=[]
   for step in job['steps']:
    entry={key:step.get(key) for key in ('stepName','status','startTime','endTime')}
    if step.get('logUrl'):
     with prior.guard.OPEN.open(step['logUrl'],timeout=30) as response:raw=response.read(2000001)
     if len(raw)>2000000:raise RuntimeError('Frontend log exceeds bound')
     filename='amplify-'+step['stepName']+'.log';(directory/filename).write_bytes(raw);entry.update(log_path=filename,log_sha256=sha(raw),log_bytes=len(raw))
    receipt['frontend']['steps'].append(entry)
  else:
   receipt['security']=security();receipt['functions']=prior.functions(directory,True)
   receipt['package_functions'],receipt['queue_notification_target']=prior.queue.archives(directory,prior.queue.source())
   with prior.guard.OPEN.open(prior.queue.BASE+'/capabilities',timeout=30) as response:cap=json.load(response)
   if cap.get('paper_uploads')!=dict(version='research-paper-upload-v1',maximum_bytes=10000000,media_type='application/pdf'):raise RuntimeError('PDF capability differs')
   if cap['autonomy']['enabled'] is not True or cap['autonomy']['defaults']!=dict(maximum_spend_usd=100,elapsed_days=7,attempts_per_claim=None,parallel_claims_per_paper=2,global_parallel_claims=4):raise RuntimeError('Autonomy activation/defaults differ')
   receipt['capabilities']=cap;receipt['anonymous_checks']=[]
   for path,method in (('/paper-uploads','POST'),('/queue','GET')):
    try:
     with prior.guard.OPEN.open(urllib.request.Request(prior.queue.BASE+path,method=method,data=b'{}' if method=='POST' else None,headers={'Content-Type':'application/json'}),timeout=20) as response:status=response.status
    except urllib.error.HTTPError as error:status=error.code
    if status not in (401,403):raise RuntimeError('Private API anonymously accessible')
    receipt['anonymous_checks'].append(dict(path=path,status=status))
  if prior.pointers()!=before:raise RuntimeError('Published prompt pointers changed')
  receipt['status']='complete'
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:receipt['ended_at']=stamp();save();print(json.dumps(dict(mode=a.mode,status=receipt['status'],directory=str(directory))))

if __name__=='__main__':main()
