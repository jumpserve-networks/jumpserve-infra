"""Exact operational controller release, with source and production readback.

Qualification happens before OIDC. Execution changes only Code and matching
asset metadata for the three existing controllers in the settled live template.
"""
import argparse,base64,copy,datetime as dt,hashlib,importlib.util,io,json,os,re,time,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'.test-artifacts/research-runtime-release'
CONTROLLERS={'ResearchWorkflowApiE04EBDAC','ResearchWorkflowAutonomyWorker1BCFF82C','ResearchWorkflowQueueWorker702E601D'}
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
STACK='JumpServeBenchmarkStack'
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,value):BASE.mkdir(parents=True,exist_ok=True);(BASE/name).write_bytes(encoded(value))
def read(name):return json.loads((BASE/name).read_bytes())
def module():
 spec=importlib.util.spec_from_file_location('runtime_gate',ROOT/'assets/platform/research-runtime-gate.py');value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def public_main(repo):
 with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/jumpserve-networks/'+repo+'/git/ref/heads/main',headers={'User-Agent':'JumpServe-Research-Runtime'}),timeout=30) as response:return json.load(response)['object']['sha']
def inputs():
 operation=os.environ['PLATFORM_OPERATION_ID'];revision=os.environ['RESEARCH_RUNTIME_REVISION'];pin=os.environ['RESEARCH_RUNTIME_PIN_REVISION']
 if str(uuid.UUID(operation))!=operation or not all(re.fullmatch('[a-f0-9]{40}',s) for s in (revision,pin)):raise ValueError('Exact operational runtime identities required.')
 if public_main('jumpserve-back-end')!=revision or public_main('jumpserve-infra')!=pin:raise ValueError('Main advanced after source qualification; preserve the old intent and requalify.')
 return operation,revision,pin
def certificate():
 gate=module();manifest=json.loads((ROOT/'.pin/research-workflow-runtime.json').read_bytes())
 if manifest['source_revision']!=os.environ['RESEARCH_RUNTIME_REVISION']:raise ValueError('Runtime pin does not bind the backend source.')
 binding=sha(encoded({n:h for n,h in manifest['files'].items() if n!=gate.APPROVAL}))
 value=json.loads((ROOT/'.pin/research-runtime-qualifications'/ (binding+'.json')).read_bytes())
 if value['manifest']!=manifest or value['backend_revision']!=manifest['source_revision'] or value['passed'] is not True or value['provider_calls']!=0 or value['credential_free'] is not True:raise ValueError('Operational certificate differs.')
 if value['driver_sha256']!=sha((ROOT/'assets/platform/research-runtime-checks.py').read_bytes()) or value['gate_sha256']!=sha((ROOT/'assets/platform/research-runtime-gate.py').read_bytes()):raise ValueError('Trusted qualification profile changed.')
 return value
def pins():
 inputs();value=certificate()
 with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('previous='+value['previous_manifest']['source_revision']+'\n')
def qualify():
 operation,revision,pin=inputs();gate=module();value=certificate()
 scope=gate.inspect(ROOT/'.previous/research_workflow',ROOT/'.backend/research_workflow',value['previous_manifest'])
 # Approval metadata is the sole derived source difference from the earlier
 # candidate scope; every executable/scientific byte must agree.
 actual=dict(scope);expected=dict(value['scope']);actual['files']=dict(actual['files']);expected['files']=dict(expected['files']);actual['files'].pop(gate.APPROVAL);expected['files'].pop(gate.APPROVAL)
 if actual!=expected:raise ValueError('Independent source scope verification failed.')
 clean={k:v for k,v in value.items() if k not in ('backend_revision','previous_manifest','manifest')}
 approval=json.loads((ROOT/'.backend/research_workflow'/gate.APPROVAL).read_bytes())
 if approval!=gate.approval(scope,sha(encoded(clean))):raise ValueError('Derived approval does not bind its immutable certificate.')
 for name,expected_sha in value['manifest']['files'].items():
  if sha((ROOT/'.backend/research_workflow'/name).read_bytes())!=expected_sha:raise ValueError('Pinned source differs: '+name)
 import subprocess
 image='jumpserve-research-release:'+sha((ROOT/'assets/platform/Dockerfile').read_bytes())[:16]
 subprocess.run(['docker','build','--tag',image,'--file','assets/platform/Dockerfile','.'],check=True,timeout=900)
 commands=[['python3','-B','-m','unittest','discover','-s','research_workflow/tests','-v'],['python3','-B','/qualification/checks.py']]
 receipts=[]
 for index,command in enumerate(commands):
  args=['docker','run','--rm','--name','research-runtime-check-'+str(index),'--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=1g','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','256','--memory','2g','--env','HOME=/tmp','--mount','type=bind,source='+str(ROOT/'.backend')+',target=/workspace,readonly','--mount','type=bind,source='+str(ROOT/'assets/platform/research-runtime-checks.py')+',target=/qualification/checks.py,readonly','--workdir','/workspace',image,*command]
  result=subprocess.run(args,capture_output=True,timeout=600)
  save('checks-'+str(index)+'.json',dict(command=command,exit_code=result.returncode,stdout=result.stdout[-300000:].decode(errors='replace'),stderr=result.stderr[-300000:].decode(errors='replace')))
  if result.returncode:raise ValueError('Independent credential-free qualification failed; retained output identifies the failure.')
  receipts.append(dict(index=index,passed=True,stdout_sha256=sha(result.stdout),stderr_sha256=sha(result.stderr)))
 save('qualification.json',dict(passed=True,operation_id=operation,revision=revision,pin_revision=pin,scope=scope,manifest=value['manifest'],previous_manifest=value['previous_manifest'],independent_checks=receipts,certificate_sha256=sha(encoded(clean))))
 print(json.dumps(dict(qualified=True,source_binding=scope['source_binding'],provider_calls=0)))
def render(previous,key):
 if not re.fullmatch('[a-f0-9]{64}\\.zip',key):raise ValueError('Content-addressed runtime object required.')
 candidate=copy.deepcopy(previous)
 for name in sorted(CONTROLLERS):
  resource=candidate['Resources'][name]
  if resource['Type']!='AWS::Lambda::Function':raise ValueError('Existing controller identity differs.')
  resource['Properties']['Code']=dict(S3Bucket=BUCKET,S3Key=key)
  resource.setdefault('Metadata',{})['aws:asset:path']='asset.'+key[:-4]
 return candidate
def installed(session,template,files):
 result=[]
 for name in sorted(CONTROLLERS):
  code=template['Resources'][name]['Properties']['Code']
  if set(code)!={'S3Bucket','S3Key'} or code['S3Bucket']!=BUCKET:raise ValueError('Unexpected deployed code location.')
  # Fixed function names are passed from the bootstrap-maintained release
  # profile, then cross-checked against Lambda's immutable account/ARN fields.
  physical=json.loads((ROOT/'research-runtime-targets.json').read_bytes())[name]
  value=session.client('lambda').get_function(FunctionName=physical)
  config=value['Configuration']
  if config['FunctionArn']!='arn:aws:lambda:us-east-1:395567831870:function:'+physical:raise ValueError('Controller ARN differs.')
  with urllib.request.urlopen(value['Code']['Location'],timeout=60) as response:raw=response.read(12000001)
  if len(raw)>12000000 or base64.b64encode(hashlib.sha256(raw).digest()).decode()!=config['CodeSha256']:raise ValueError('Actual Lambda ZIP checksum differs.')
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   if set(archive.namelist())!=set(files) or {n:sha(archive.read(n)) for n in files}!=files:raise ValueError('Actual Lambda source differs from its qualified pin.')
  result.append(dict(logical_id=name,function=physical,code_sha256=config['CodeSha256'],source_verified=True))
 return result
def execute():
 import boto3
 operation,revision,pin=inputs();qualification=read('qualification.json')
 if not qualification['passed'] or (qualification['operation_id'],qualification['revision'],qualification['pin_revision'])!=(operation,revision,pin):raise ValueError('Source-bound pre-credential qualification required.')
 session=boto3.Session(region_name='us-east-1')
 if session.client('sts').get_caller_identity()['Account']!='395567831870':raise ValueError('Wrong AWS account.')
 cfn=session.client('cloudformation');s3=session.client('s3')
 info=cfn.describe_stacks(StackName=STACK)['Stacks'][0]
 if info['StackStatus']!='UPDATE_COMPLETE':raise ValueError('Reconcile existing stack operation before a new release.')
 previous=cfn.get_template(StackName=STACK,TemplateStage='Original')['TemplateBody']
 if isinstance(previous,str):previous=json.loads(previous)
 installed(session,previous,qualification['previous_manifest']['files'])
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,expected in sorted(qualification['manifest']['files'].items()):
   raw=(ROOT/'.backend/research_workflow'/name).read_bytes()
   if sha(raw)!=expected:raise ValueError('Source changed after qualification.')
   item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(item,raw)
 raw=stream.getvalue();key=sha(raw)+'.zip';candidate=render(previous,key)
 save('template-before.json',previous);save('template-candidate.json',candidate)
 s3.put_object(Bucket=BUCKET,Key=key,Body=raw,ServerSideEncryption='AES256',IfNoneMatch='*')
 body=encoded(candidate);template_key='platform-releases/'+sha(body)+'.json';s3.put_object(Bucket=BUCKET,Key=template_key,Body=body,ServerSideEncryption='AES256')
 request=dict(StackName=STACK,TemplateURL='https://'+BUCKET+'.s3.us-east-1.amazonaws.com/'+template_key,Parameters=[dict(ParameterKey=p['ParameterKey'],ParameterValue=p['ParameterValue']) for p in info.get('Parameters',[])],Capabilities=['CAPABILITY_IAM','CAPABILITY_NAMED_IAM'],RoleARN='arn:aws:iam::395567831870:role/JumpServePlatformCloudFormation',ClientRequestToken='research-runtime-'+operation,Tags=info.get('Tags',[]),NotificationARNs=info.get('NotificationARNs',[]))
 save('deployment-intent.json',dict(request=request,previous_template_sha256=sha(encoded(previous)),candidate_template_sha256=sha(body)))
 cfn.update_stack(**request)
 deadline=time.monotonic()+1800
 while time.monotonic()<deadline:
  current=cfn.describe_stacks(StackName=STACK)['Stacks'][0]
  if current['StackStatus'].endswith('_IN_PROGRESS'):time.sleep(15);continue
  if current['StackStatus']!='UPDATE_COMPLETE':raise ValueError('Original CloudFormation operation did not complete successfully: '+current['StackStatus'])
  actual=cfn.get_template(StackName=STACK,TemplateStage='Original')['TemplateBody'];actual=json.loads(actual) if isinstance(actual,str) else actual
  if actual!=candidate or current.get('Parameters',[])!=info.get('Parameters',[]) or current.get('Outputs',[])!=info.get('Outputs',[]):raise ValueError('Actual settled production template differs.')
  functions=installed(session,actual,qualification['manifest']['files'])
  proof=dict(passed=True,operation_id=operation,repository='jumpserve-networks/jumpserve-back-end',revision=revision,component='research-runtime',pin_revision=pin,source_binding=qualification['scope']['source_binding'],certificate_sha256=qualification['certificate_sha256'],template_sha256=sha(encoded(actual)),functions=functions,all_other_template_content_preserved=True,scientific_and_request_content_unchanged=True,existing_tests_unchanged=True,verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
  (ROOT/'production-verification.json').write_bytes(encoded(proof));print(json.dumps(proof));return
 raise TimeoutError('Original deployment remains unconfirmed; never redispatch from a missing receipt.')
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['pins','qualify','execute']);globals()[parser.parse_args().action]()
