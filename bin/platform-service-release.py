"""Execute fixed infrastructure service adapters under original release identities."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import ssl
import shlex
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='https://regphejnlvfpyokpniny.supabase.co'
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
PROFILES=('assessment-evidence-v1','intake-parser-recovery-v1')
INTAKE_BINDING='ce289f36b6683d30523ff3b5aaf7626bd7042002a4968015f7fd779eb0dc1e05'


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def validate_manifest(value,request_id,profile):
 expected=dict(version='platform-service-manifest-v1',request_id=str(uuid.UUID(request_id)),profile=profile)
 if profile not in PROFILES or value!=expected:raise ValueError('Exact fixed-profile service manifest required.')
 return expected


class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('Private service redirects are disabled.')


class Database:
 def __init__(self,key):self.key=key;self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
 def request(self,path,body=None,raw=False):
  if not path.startswith(('/rest/v1/','/storage/v1/object/')) or '..' in path:raise ValueError('Fixed private service path required.')
  headers={'apikey':self.key,'Authorization':'Bearer '+self.key,'Content-Type':'application/json'}
  req=urllib.request.Request(ORIGIN+path,data=encoded(body) if body is not None else None,headers=headers)
  try:
   with self.opener.open(req,timeout=30) as response:value=response.read(10000001)
  except urllib.error.HTTPError as error:raise ValueError('Private service persistence failed (HTTP '+str(error.code)+'); reconcile the original operation.') from None
  if len(value)>10000000:raise ValueError('Service response exceeds its byte bound.')
  return value if raw else json.loads(value)
 def release(self,operation,revision,manifest=None,result=None):
  return self.request('/rest/v1/rpc/platform_service_release',dict(p_operation=operation,p_revision=revision,p_manifest=manifest,p_result=result))
 def original(self,study,artifact):
  if artifact['storage_path']!=study+'/'+artifact['sha256']:raise ValueError('Original artifact is not assessment-bound.')
  value=self.request('/storage/v1/object/research-workflow-raw/'+artifact['storage_path'],raw=True)
  if len(value)!=artifact['byte_count'] or sha(value)!=artifact['sha256']:raise ValueError('Retained original artifact differs.')
  return value


def record(db,table,study,ident):
 ident=str(uuid.UUID(ident));study=str(uuid.UUID(study))
 rows=db.request('/rest/v1/research_'+table+'?study_id=eq.'+study+'&id=eq.'+ident+'&select=*&limit=2')
 if len(rows)!=1:raise ValueError('One exact retained record required.')
 return rows[0]


def verify_intake_environment(session,operation):
 """Read actual installed bytes and run the parser as the intake service user."""
 pin=json.loads((ROOT/'intake-worker-runtime.json').read_bytes())
 if pin['source_binding']!=INTAKE_BINDING:raise ValueError('This recovery adapter needs its qualified intake predecessor.')
 pdf=json.loads((ROOT/'autonomy-pdf-runtime.json').read_bytes())
 code='FILES='+repr(pin['files'])+'\nPDF='+repr({n:h for n,h in pdf['files'].items() if n.startswith('pypdf/')})+'\n'
 code+='CHECK='+repr(sha((ROOT/'assets/openclaw/verify-intake-pdf.py').read_bytes()))+'\nSERVICE='+repr(sha((ROOT/'assets/openclaw/jumpserve-intake.service').read_bytes()))+'\n'
 code+='''import hashlib,json,pathlib,subprocess
r=pathlib.Path('/opt/jumpserve/intake-runtime');site=pathlib.Path('/opt/jumpserve/python/lib/python3.12/site-packages')
assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==h for n,h in FILES.items())
assert all(hashlib.sha256((site/n).read_bytes()).hexdigest()==h for n,h in PDF.items())
assert hashlib.sha256(pathlib.Path('/opt/jumpserve/intake-pdf-check.py').read_bytes()).hexdigest()==CHECK
assert hashlib.sha256(pathlib.Path('/etc/systemd/system/jumpserve-intake.service').read_bytes()).hexdigest()==SERVICE
subprocess.run(['systemctl','is-active','--quiet','jumpserve-intake.service'],check=True,timeout=10)
result=subprocess.run(['runuser','-u','jumpserve','--','/opt/jumpserve/python/bin/python','-B','/opt/jumpserve/intake-pdf-check.py'],check=True,capture_output=True,text=True,timeout=45)
probe=json.loads(result.stdout);assert probe['passed'] and probe['actual_parser_subprocess'] and probe['version']=='6.19.0'
print(json.dumps(dict(passed=True,intake_files_verified=len(FILES),pdf_files_verified=len(PDF),actual_parser_subprocess=True)))
'''
 request=dict(DocumentName='AWS-RunShellScript',InstanceIds=['i-00dc52abbcf706670'],
  Comment='service-intake-parser-check-'+operation,Parameters=dict(commands=['set -eu','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(code)],executionTimeout=['90']))
 s3=session.client('s3');ssm=session.client('ssm');key='platform-supervisor/service-work/'+operation+'/parser-check-intent.json';intent=encoded(request);created=False
 try:s3.put_object(Bucket=BUCKET,Key=key,Body=intent,IfNoneMatch='*',ServerSideEncryption='AES256');created=True
 except Exception:
  if s3.get_object(Bucket=BUCKET,Key=key)['Body'].read()!=intent:raise ValueError('Original parser-check intent differs.') from None
 options=dict(InstanceId=request['InstanceIds'][0],MaxResults=50,Filters=[dict(key='InvokedAfter',value=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=1)).isoformat())]);matches=[]
 for _ in range(20):
  page=ssm.list_commands(**options);matches.extend(c for c in page['Commands'] if c.get('Comment')==request['Comment'])
  if not page.get('NextToken'):break
  options['NextToken']=page['NextToken']
 else:raise ValueError('Original parser-check lookup exceeds its bound.')
 if matches:
  if len(matches)!=1 or any(matches[0].get(k)!=request[k] for k in ('DocumentName','InstanceIds','Parameters')):raise ValueError('Original parser-check command identity differs.')
  command=matches[0]['CommandId']
 elif created:command=ssm.send_command(**request)['Command']['CommandId']
 else:raise ValueError('Original parser-check acknowledgment is uncertain; no command resent.')
 for _ in range(60):
  try:result=ssm.get_command_invocation(CommandId=command,InstanceId=request['InstanceIds'][0])
  except ssm.exceptions.InvocationDoesNotExist:time.sleep(2);continue
  if result['Status'] in ('Pending','InProgress','Delayed'):time.sleep(2);continue
  if result['Status']!='Success' or result['ResponseCode']!=0:raise ValueError('Actual installed parser verification failed; retain command '+command)
  proof=json.loads(result['StandardOutputContent'].splitlines()[-1])
  if proof.get('passed') is not True or proof.get('actual_parser_subprocess') is not True:raise ValueError('Actual parser proof differs.')
  return dict(intake_environment_verified=True,environment_command_id=command,environment_checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),environment=proof)
 raise ValueError('Original parser-check command remains pending: '+command)


def recover(db,session,context,operation,revision,candidate):
 evidence=context['evidence'];study=evidence['assessment_id'];task=evidence['task']
 if (task['stage']!='intake' or task['status']!='blocked' or task['attempts']!=0
  or task['context']!={'intake_pool_version':'warm-intake-v1'} or evidence['review']['status']!='failed'
  or evidence['review']['confirmed'] or evidence['review']['candidate_count']!=0):raise ValueError('Only untouched retained intake failures can use parser recovery.')
 failures=[a for a in evidence['artifacts'] if a['kind']=='failed-text-extraction']
 if not failures:raise ValueError('Retained extraction failure required.')
 failure=record(db,'artifacts',study,failures[0]['id']);failure_raw=db.original(study,failure);failure_data=json.loads(failure_raw)
 if "No module named 'pypdf'" not in failure_data.get('reason',''):raise ValueError('This fixed service repairs a missing PDF parser only.')
 original=record(db,'artifacts',study,failure['provenance']['original_artifact_id']);original_raw=db.original(study,original)
 if original['sha256']!=failure_data.get('original_sha256') or not original_raw[:1024].lstrip().startswith(b'%PDF-'):raise ValueError('Failure and retained PDF identities differ.')
 sources=[s for s in evidence['sources'] if s['sha256']==original['sha256']]
 if len(sources)!=1:raise ValueError('One original source record must be retained and reused.')
 intake=evidence['intake']
 if not intake['enabled'] or intake['status']!='ready' or intake['configuration'].get('source_binding')!=INTAKE_BINDING or intake['configuration'].get('gateway_verified') is not True:
  raise ValueError('Qualified repaired intake source must be ready.')
 environment=verify_intake_environment(session,operation)
 # This object is private, immutable, and addressed by the ORIGINAL operation.
 # A lost storage acknowledgment or CI restart reuses its exact parsed bytes.
 s3=session.client('s3');key='platform-supervisor/service-work/'+operation+'/text.json'
 try:packet=s3.get_object(Bucket=BUCKET,Key=key)['Body'].read(3000001)
 except s3.exceptions.NoSuchKey:packet=None
 if packet is None:
  lock=json.loads((ROOT/'autonomy-pdf-runtime.json').read_bytes())
  if lock['requirement']!='pypdf==6.19.0':raise ValueError('Pinned parser differs.')
  dependencies=ROOT/'.runtime-autonomy-python/python'
  for name,h in lock['files'].items():
   if sha((dependencies/name).read_bytes())!=h:raise ValueError('Fixed parser dependency source differs.')
  sys.path[:0]=[str(candidate/'.runtime-research-api/research_workflow'),str(dependencies)]
  expected=json.loads((ROOT/'research-api-runtime.json').read_bytes())['files']
  runtime=candidate/'.runtime-research-api/research_workflow'
  for name in ('intake.py','workflow.py','store.py'):
   if sha((runtime/name).read_bytes())!=expected[name]:raise ValueError('Pinned parser/store implementation differs.')
  import intake as parser
  if Path(parser.__file__).resolve()!=(runtime/'intake.py').resolve():raise ValueError('Pinned parser import identity differs.')
  with tempfile.TemporaryDirectory(prefix='jumpserve-service-pdf-') as folder:
   source=Path(folder)/'original.pdf';output=Path(folder)/'text.json';source.write_bytes(original_raw)
   parser.text_packet(source,output);packet=output.read_bytes()
  try:s3.put_object(Bucket=BUCKET,Key=key,Body=packet,IfNoneMatch='*',ServerSideEncryption='AES256')
  except Exception:
   retained=s3.get_object(Bucket=BUCKET,Key=key)['Body'].read(3000001)
   if retained!=packet:raise ValueError('Original staged text differs; no replacement permitted.') from None
 if len(packet)>3000000:raise ValueError('Retained parsed text exceeds its bound.')
 parsed=json.loads(packet)
 if parsed.get('original_sha256')!=original['sha256'] or parsed.get('tool_version')!='6.19.0' or not parsed.get('pages'):
  raise ValueError('Retained text packet identity differs.')
 # Use the existing audited, content-addressed research artifact writer.
 sys.path.insert(0,str(candidate/'.runtime-research-api/research_workflow'))
 expected=json.loads((ROOT/'research-api-runtime.json').read_bytes())['files']
 for name in ('store.py','workflow.py'):
  if sha((candidate/'.runtime-research-api/research_workflow'/name).read_bytes())!=expected[name]:raise ValueError('Trusted persistence source differs.')
 import store
 if Path(store.__file__).resolve()!=(candidate/'.runtime-research-api/research_workflow/store.py').resolve():raise ValueError('Pinned persistence import identity differs.')
 store.service_key=lambda:db.key;os.environ['SUPABASE_URL']=ORIGIN
 owners=db.request('/rest/v1/research_study_owners?study_id=eq.'+study+'&select=owner_id&limit=2')
 if len(owners)!=1:raise ValueError('Original assessment owner binding is required.')
 ident=str(uuid.uuid5(uuid.UUID(study),'paper-text:'+sha(packet)))
 artifact=store.artifact(study,owners[0]['owner_id'],packet,ident,'application/json',dict(kind='derived-pdf-text',original_artifact_id=original['id'],original_sha256=original['sha256'],transformation='intake.text_packet; pypdf; text extraction is not substantive review'))
 store.append(study,owners[0]['owner_id'],'artifacts',artifact)
 if db.original(study,record(db,'artifacts',study,artifact['id']))!=packet:raise ValueError('Persisted text readback differs.')
 return dict(environment,passed=True,profile=context['profile'],request_id=context['request_id'],revision=revision,
  intake_source_binding=INTAKE_BINDING,parser_version='6.19.0',failure_verified=True,
  failure_artifact_id=failure['id'],failure_sha256=failure['sha256'],original_reason_sha256=task['reason_sha256'],
  source_id=sources[0]['id'],original_artifact_id=original['id'],text_artifact_id=artifact['id'],text_sha256=artifact['sha256'],
  pages=len(parsed['pages']),characters=sum(len(p['text']) for p in parsed['pages']),
  provider_calls=0,original_source_reused=True,scientific_completion=False)


def execute(session,candidate,operation,revision):
 key=session.client('secretsmanager').get_secret_value(SecretId='jumpserve/supabase-service-key')['SecretString'];db=Database(key)
 context=db.release(operation,revision)
 if context is None:return None
 if context.get('verified') is True:return context
 path=candidate/context['manifest_path']
 if path.is_symlink() or path.parent.is_symlink() or not path.is_file() or path.stat().st_size>16000:raise ValueError('Source-bound service manifest required.')
 manifest=validate_manifest(json.loads(path.read_bytes()),context['request_id'],context['profile'])
 if context['profile']=='intake-parser-recovery-v1':result=recover(db,session,context,operation,revision,candidate)
 else:
  evidence=context['evidence'];verified=[]
  for a in evidence['artifacts']:
   if a['kind']=='failed-text-extraction':
    original=record(db,'artifacts',evidence['assessment_id'],a['id']);raw=db.original(evidence['assessment_id'],original)
    json.loads(raw);verified.append(dict(id=a['id'],sha256=sha(raw)))
  if not evidence.get('schema') or not evidence.get('task'):raise ValueError('Executed task-bound schema/evidence read required.')
  result=dict(passed=True,profile=context['profile'],request_id=context['request_id'],revision=revision,
   task_bound_evidence_verified=True,retained_failures_verified=verified,schema_sha256=sha(encoded(evidence['schema'])),
   provider_calls=0,scientific_completion=False)
 return db.release(operation,revision,manifest,result)


def qualify(candidate):
 directory=candidate/'services';count=0
 if directory.exists():
  if directory.is_symlink():raise ValueError('Service manifest directory cannot be a link.')
  for path in directory.iterdir():
   if path.is_symlink() or not path.is_file() or path.suffix!='.json' or path.stat().st_size>16000:raise ValueError('Plain bounded service manifest required.')
   value=json.loads(path.read_bytes());validate_manifest(value,path.stem,value.get('profile'));count+=1
   if count>1000:raise ValueError('Service manifest count exceeds its bound.')
 return dict(passed=True,manifests=count,credentials_used=False,provider_calls=0)


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qualify',action='store_true');parser.add_argument('--candidate',type=Path,default=Path('.candidate'));args=parser.parse_args()
 if not args.qualify:raise ValueError('Execution is owned by the fixed platform release broker.')
 print(json.dumps(qualify(args.candidate)))
