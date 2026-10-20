"""Fixed-target PDF ingestion release; leaves published AI prompts unchanged."""
import argparse, datetime as dt, hashlib, importlib.util, json, os, subprocess, urllib.error, urllib.request
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

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('inspect','migrate','diff','deploy','activate','verify','storage'));a=p.parse_args()
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
  elif a.mode in ('diff','deploy','activate'):
   manifest=prior.queue.source();backend=ROOT.parent/'jumpserve-back-end'
   if subprocess.check_output(['git','status','--porcelain'],cwd=backend,text=True).strip() or subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=manifest['source_revision']:raise RuntimeError('Clean committed backend and exact runtime manifest required')
   receipt['security']=security();previous=prior.queue.state()
   if a.mode=='activate':receipt['functions_before_activation']=prior.functions(directory,True)
   credentials=prior.aws('configure','export-credentials','--format','process');env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
   command=['npm','run','cdk:benchmark','--','diff' if a.mode=='diff' else 'deploy',prior.queue.STACK,'-c','researchAutonomyEnabled=true','-c','researchAutonomyAdmissionEnabled='+('true' if a.mode=='activate' else 'false')]
   command+=['--no-change-set'] if a.mode=='diff' else ['--require-approval','never','--outputs-file',str(directory/'outputs.json')]
   receipt['command']=command;save()
   with (directory/'cdk.log').open('w') as logfile:result=subprocess.run(command,cwd=ROOT,env=env,stdout=logfile,stderr=subprocess.STDOUT,timeout=1800)
   if result.returncode:raise RuntimeError('Scoped CDK command failed; retained cdk.log')
   if prior.queue.state()['parameters']!=previous['parameters']:raise RuntimeError('Existing stack parameters changed')
   if a.mode=='activate':
    resources=prior.aws('cloudformation','list-stack-resources','--stack-name',prior.queue.STACK)['StackResourceSummaries'];rules=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
    if len(rules)!=1:raise RuntimeError('Autonomy rule inventory differs')
    subprocess.run(['aws','events','enable-rule','--name',rules[0],'--profile','jumpserve','--region','us-east-1'],check=True,timeout=60);receipt['autonomy_poll_restored']=rules[0]
  elif a.mode=='storage':receipt['control']=control(directory);receipt['remote_storage']=storage(directory)
  else:
   receipt['security']=security();receipt['functions']=prior.functions(directory,True)
   with prior.guard.OPEN.open(prior.queue.BASE+'/capabilities',timeout=30) as response:cap=json.load(response)
   if cap.get('paper_uploads')!=dict(version='research-paper-upload-v1',maximum_bytes=10000000,media_type='application/pdf'):raise RuntimeError('PDF capability differs')
   if cap['autonomy']['enabled'] is not True or cap['autonomy']['defaults']!=dict(maximum_spend_usd=100,elapsed_days=7,attempts_per_claim=25,parallel_claims_per_paper=2,global_parallel_claims=4):raise RuntimeError('Autonomy activation/defaults differ')
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
