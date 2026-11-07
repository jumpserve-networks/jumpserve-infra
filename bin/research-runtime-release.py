"""Exact operational controller release, with source and production readback.

Qualification happens before OIDC. Execution changes only Code and matching
asset metadata for the declared controllers in the settled live template.
"""
import argparse,base64,copy,datetime as dt,hashlib,importlib.util,io,json,os,re,time,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'.test-artifacts/research-runtime-release'
CONTROLLERS={'ResearchWorkflowApiE04EBDAC','ResearchWorkflowAutonomyWorker1BCFF82C','ResearchWorkflowQueueWorker702E601D'}
HTTP_API='ResearchWorkflowApiE04EBDAC'
WORKER_PROFILES={'captured-provider-failures-v1','auth-helper-entrypoint-v1'}
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
STACK='JumpServeBenchmarkStack'
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,value):BASE.mkdir(parents=True,exist_ok=True);(BASE/name).write_bytes(encoded(value))
def read(name):return json.loads((BASE/name).read_bytes())
def module():
 path=ROOT/'assets/platform/research-runtime-gate.py';pin=ROOT/'.pin/research-workflow-runtime.json'
 if pin.is_file():
  manifest=json.loads(pin.read_bytes());binding=sha(encoded({n:h for n,h in manifest['files'].items() if n!='policies/autonomous-repair-release-v1.json'}))
  certificate_path=ROOT/'.pin/research-runtime-qualifications'/(binding+'.json')
  if certificate_path.is_file():
   profile=json.loads(certificate_path.read_bytes())['scope'].get('qualification_profile')
   if profile=='captured-provider-failures-v1':path=ROOT/'assets/platform/captured-failure-runtime-gate.py'
   elif profile=='auth-helper-entrypoint-v1':path=ROOT/'assets/platform/auth-entrypoint-runtime-gate.py'
   elif profile is not None:raise ValueError('Unknown dedicated runtime qualification profile.')
 spec=importlib.util.spec_from_file_location('runtime_gate',path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def public_main(repo):
 headers={'User-Agent':'JumpServe-Research-Runtime'}
 token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
 if token:headers['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/jumpserve-networks/'+repo+'/git/ref/heads/main',headers=headers),timeout=30) as response:return json.load(response)['object']['sha']
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
 if value['driver_sha256']!=sha((ROOT/'assets/platform'/getattr(gate,'CHECKS','research-runtime-checks.py')).read_bytes()) or value['gate_sha256']!=sha(Path(gate.__file__).read_bytes()):raise ValueError('Trusted qualification profile changed.')
 return value
def pins():
 inputs();value=certificate()
 gate=module();base=gate.overlay(value['previous_manifest'])['base_revision'] if value['scope'].get('source_overlay') else ''
 with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('previous='+value['previous_manifest']['source_revision']+'\nbase='+base+'\n')
def qualify():
 operation,revision,pin=inputs();gate=module();value=certificate()
 previous=ROOT/'.previous';candidate=ROOT/'.backend'
 if value['scope'].get('source_overlay'):
  overlay=gate.overlay(value['previous_manifest'])
  if value['manifest'].get('source_overlay')!=overlay or value['scope']['source_overlay']!=overlay:raise ValueError('Exact source composition differs.')
  if value['previous_manifest'].get('source_overlay'):previous=gate.compose(ROOT/'.base',previous,ROOT/'.qualified-previous')
  candidate=gate.compose(ROOT/'.base',candidate,ROOT/'.qualified-backend')
 scope=gate.inspect(previous/'research_workflow',candidate/'research_workflow',value['previous_manifest'])
 if value['scope'].get('source_overlay'):scope['source_overlay']=gate.overlay(value['previous_manifest'])
 # Approval metadata is the sole derived source difference from the earlier
 # candidate scope; every executable/scientific byte must agree.
 actual=dict(scope);expected=dict(value['scope']);actual['files']=dict(actual['files']);expected['files']=dict(expected['files']);actual['files'].pop(gate.APPROVAL);expected['files'].pop(gate.APPROVAL)
 if actual!=expected:raise ValueError('Independent source scope verification failed.')
 clean={k:v for k,v in value.items() if k not in ('backend_revision','previous_manifest','manifest')}
 approval=json.loads((ROOT/'.backend/research_workflow'/gate.APPROVAL).read_bytes())
 if approval!=gate.approval(scope,sha(encoded(clean))):raise ValueError('Derived approval does not bind its immutable certificate.')
 for name,expected_sha in value['manifest']['files'].items():
  if sha((candidate/'research_workflow'/name).read_bytes())!=expected_sha:raise ValueError('Pinned source differs: '+name)
 import subprocess
 image='jumpserve-research-release:'+sha((ROOT/'assets/platform/Dockerfile').read_bytes())[:16]
 subprocess.run(['docker','build','--tag',image,'--file','assets/platform/Dockerfile','.'],check=True,timeout=900)
 commands=[['python3','-B','-m','unittest','discover','-s','research_workflow/tests','-v'],['python3','-B','/qualification/checks.py']]
 receipts=[]
 for index,command in enumerate(commands):
  driver=ROOT/'assets/platform'/getattr(gate,'CHECKS','research-runtime-checks.py')
  args=['docker','run','--rm','--name','research-runtime-check-'+str(index),'--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=1g','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','256','--memory','2g','--env','HOME=/tmp','--mount','type=bind,source='+str(candidate)+',target=/workspace,readonly','--mount','type=bind,source='+str(driver)+',target=/qualification/checks.py,readonly','--workdir','/workspace',image,*command]
  if getattr(gate,'CHECKS',None):args[2:2]=['--mount','type=bind,source='+str(ROOT/'assets/platform/research-runtime-checks.py')+',target=/qualification/base-checks.py,readonly']
  if scope.get('qualification_profile')=='auth-helper-entrypoint-v1':args[2:2]=['--mount','type=bind,source='+str(ROOT/'assets/platform/captured-failure-runtime-checks.py')+',target=/qualification/captured-failure-checks.py,readonly']
  result=subprocess.run(args,capture_output=True,timeout=600)
  save('checks-'+str(index)+'.json',dict(command=command,exit_code=result.returncode,stdout=result.stdout[-300000:].decode(errors='replace'),stderr=result.stderr[-300000:].decode(errors='replace')))
  if result.returncode:raise ValueError('Independent credential-free qualification failed; retained output identifies the failure.')
  receipts.append(dict(index=index,passed=True,stdout_sha256=sha(result.stdout),stderr_sha256=sha(result.stderr)))
 save('qualification.json',dict(passed=True,operation_id=operation,revision=revision,pin_revision=pin,scope=scope,manifest=value['manifest'],previous_manifest=value['previous_manifest'],independent_checks=receipts,certificate_sha256=sha(encoded(clean))))
 print(json.dumps(dict(qualified=True,source_binding=scope['source_binding'],provider_calls=0)))
def controller_targets(scope):
 # The captured-result adapter runs in execution controllers and the OpenClaw
 # worker. The separately pinned HTTP API has its own source and release owner.
 return CONTROLLERS-{HTTP_API} if scope.get('qualification_profile') in WORKER_PROFILES else CONTROLLERS
def render(previous,key,controllers=None):
 if not re.fullmatch('[a-f0-9]{64}\\.zip',key):raise ValueError('Content-addressed runtime object required.')
 controllers=CONTROLLERS if controllers is None else controllers
 if controllers not in (CONTROLLERS,CONTROLLERS-{HTTP_API}):raise ValueError('Fixed qualified controller targets required.')
 candidate=copy.deepcopy(previous)
 for name in sorted(controllers):
  resource=candidate['Resources'][name]
  if resource['Type']!='AWS::Lambda::Function':raise ValueError('Existing controller identity differs.')
  resource['Properties']['Code']=dict(S3Bucket=BUCKET,S3Key=key)
  resource.setdefault('Metadata',{})['aws:asset:path']='asset.'+key[:-4]
 return candidate
def installed(session,template,files,controllers=None):
 result=[]
 for name in sorted(CONTROLLERS if controllers is None else controllers):
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
def controller_baseline(session,template,qualification,selected):
 try:
  installed(session,template,qualification['previous_manifest']['files'],selected)
  return 'qualified-predecessor'
 except ValueError:
  if qualification['scope'].get('qualification_profile') not in WORKER_PROFILES:raise
  # A prior operation can finish its Lambda updates before worker installation
  # fails. Accept only the entire exact candidate, never a mixed/unknown state.
  installed(session,template,qualification['manifest']['files'],selected)
  return 'already-qualified-candidate'
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
 selected=controller_targets(qualification['scope']);api_manifest=None
 if selected!=CONTROLLERS:
  api_manifest=json.loads((ROOT/'research-api-runtime.json').read_bytes())
  installed(session,previous,api_manifest['files'],{HTTP_API})
 baseline=controller_baseline(session,previous,qualification,selected)
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,expected in sorted(qualification['manifest']['files'].items()):
   qualified=ROOT/'.qualified-backend' if qualification['manifest'].get('source_overlay') else ROOT/'.backend'
   raw=(qualified/'research_workflow'/name).read_bytes()
   if sha(raw)!=expected:raise ValueError('Source changed after qualification.')
   item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(item,raw)
 raw=stream.getvalue();key=sha(raw)+'.zip';candidate=render(previous,key,selected)
 if baseline=='already-qualified-candidate' and candidate!=previous:raise ValueError('Already qualified controller template differs; reconcile the original release.')
 save('template-before.json',previous);save('template-candidate.json',candidate)
 try:s3.put_object(Bucket=BUCKET,Key=key,Body=raw,ServerSideEncryption='AES256',IfNoneMatch='*')
 except Exception:
  if s3.get_object(Bucket=BUCKET,Key=key)['Body'].read()!=raw:raise ValueError('Original qualified controller bundle differs.') from None
 body=encoded(candidate);template_key='platform-releases/'+sha(body)+'.json';s3.put_object(Bucket=BUCKET,Key=template_key,Body=body,ServerSideEncryption='AES256')
 request=dict(StackName=STACK,TemplateURL='https://'+BUCKET+'.s3.us-east-1.amazonaws.com/'+template_key,Parameters=[dict(ParameterKey=p['ParameterKey'],ParameterValue=p['ParameterValue']) for p in info.get('Parameters',[])],Capabilities=['CAPABILITY_IAM','CAPABILITY_NAMED_IAM'],RoleARN='arn:aws:iam::395567831870:role/JumpServePlatformCloudFormation',ClientRequestToken='research-runtime-'+operation,Tags=info.get('Tags',[]),NotificationARNs=info.get('NotificationARNs',[]))
 save('deployment-intent.json',dict(request=request,previous_template_sha256=sha(encoded(previous)),candidate_template_sha256=sha(body),controller_baseline=baseline,controller_update_required=baseline=='qualified-predecessor'))
 if baseline=='qualified-predecessor':cfn.update_stack(**request)
 deadline=time.monotonic()+1800
 while time.monotonic()<deadline:
  current=cfn.describe_stacks(StackName=STACK)['Stacks'][0]
  if current['StackStatus'].endswith('_IN_PROGRESS'):time.sleep(15);continue
  if current['StackStatus']!='UPDATE_COMPLETE':raise ValueError('Original CloudFormation operation did not complete successfully: '+current['StackStatus'])
  actual=cfn.get_template(StackName=STACK,TemplateStage='Original')['TemplateBody'];actual=json.loads(actual) if isinstance(actual,str) else actual
  if actual!=candidate or current.get('Parameters',[])!=info.get('Parameters',[]) or current.get('Outputs',[])!=info.get('Outputs',[]):raise ValueError('Actual settled production template differs.')
  functions=installed(session,actual,qualification['manifest']['files'],selected)
  preserved_api=installed(session,actual,api_manifest['files'],{HTTP_API}) if api_manifest else None
  worker=None
  if qualification['scope'].get('qualification_profile') in WORKER_PROFILES:
   spec=importlib.util.spec_from_file_location('fixed_captured_failure_worker',ROOT/'bin/captured-failure-worker-release.py');broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
   worker=broker.install(session,operation,revision,qualification,raw)
  proof=dict(passed=True,operation_id=operation,repository='jumpserve-networks/jumpserve-back-end',revision=revision,component='research-runtime',pin_revision=pin,source_binding=qualification['scope']['source_binding'],certificate_sha256=qualification['certificate_sha256'],template_sha256=sha(encoded(actual)),functions=functions,all_other_template_content_preserved=True,scientific_and_request_content_unchanged=True,existing_tests_unchanged=True,verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
  if worker is not None:proof['research_worker']=worker;proof['qualification_profile']=qualification['scope']['qualification_profile']
  if preserved_api is not None:proof['preserved_http_api']=dict(source_revision=api_manifest['source_revision'],functions=preserved_api,source_unchanged=True)
  proof['controller_baseline']=baseline
  (ROOT/'production-verification.json').write_bytes(encoded(proof));print(json.dumps(proof));return
 raise TimeoutError('Original deployment remains unconfirmed; never redispatch from a missing receipt.')
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['pins','qualify','execute']);globals()[parser.parse_args().action]()
