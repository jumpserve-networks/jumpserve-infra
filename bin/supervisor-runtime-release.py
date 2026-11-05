"""Frozen self-update broker: isolated qualification, one install, exact readback."""
import argparse,hashlib,importlib.util,io,json,os,re,shlex,subprocess,time,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.test-artifacts/supervisor-runtime-release'
ACCOUNT='395567831870';REGION='us-east-1';HOST='i-087f1493809643115';BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
ORIGIN='https://regphejnlvfpyokpniny.supabase.co';VERSION='platform-supervisor-self-repair-v1'
def raw(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def save(name,v):OUT.mkdir(parents=True,exist_ok=True);(OUT/name).write_bytes(raw(v))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def pins():
 for key in ('SUPERVISOR_REVISION','PREVIOUS_SUPERVISOR_REVISION'):
  if not re.fullmatch('[a-f0-9]{40}',os.environ[key]):raise ValueError('Exact supervisor revisions required')
 for key in ('PLATFORM_OPERATION_ID','SUPERVISOR_QUALIFICATION_ARTIFACT'):
  if str(uuid.UUID(os.environ[key]))!=os.environ[key]:raise ValueError('Exact original operation/certificate required')
 with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('research='+json.loads((ROOT/'research-workflow-runtime.json').read_bytes())['source_revision']+'\n')
def qualify():
 gate=load('frozen_self_gate',ROOT/'assets/platform/supervisor-runtime-gate.py');previous=ROOT/'.previous/platform_supervisor';candidate=ROOT/'.backend/platform_supervisor'
 manifest=dict(version=VERSION,source_revision=os.environ['PREVIOUS_SUPERVISOR_REVISION'],files=gate.files(previous));scope=gate.inspect(previous,candidate,manifest)
 image='jumpserve-supervisor-qualification:'+scope['source_binding'][:24]
 subprocess.run(['docker','build','--tag',image,'--file','assets/platform/Dockerfile','.'],check=True,timeout=900)
 commands=[['python3','-B','-m','unittest','discover','-s','platform_supervisor/tests','-v'],['python3','-B','-m','unittest','discover','-s','/previous/platform_supervisor/tests','-v']]
 for n,command in enumerate(commands):
  args=['docker','run','--rm','--name','supervisor-qualification-'+str(n),'--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=512m','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','256','--memory','2g','--mount','type=bind,source='+str(ROOT/'.backend')+',target=/workspace,readonly','--mount','type=bind,source='+str(ROOT/'.previous')+',target=/previous,readonly','--mount','type=bind,source='+str(ROOT)+',target=/jumpserve-infra,readonly','--mount','type=bind,source='+str(ROOT/'.runtime/research_workflow')+',target=/workspace/research_workflow,readonly','--workdir','/workspace',image,*command]
  r=subprocess.run(args,capture_output=True,timeout=600);output=r.stdout+b'\n'+r.stderr;OUT.mkdir(parents=True,exist_ok=True);(OUT/('check-'+str(n)+'.log')).write_bytes(output)
  counts=re.findall(rb'Ran ([0-9]+) tests',output)
  if r.returncode or b'skipped=' in output or not counts or int(counts[-1])<1:raise ValueError('Frozen supervisor qualification failed; retain original log')
 if gate.inspect(previous,candidate,manifest)!=scope:raise ValueError('Source changed during self qualification')
 pack=load('frozen_supervisor_packager',ROOT/'bin/platform-supervisor.py');pack.BACK=ROOT/'.backend';bundle,files=pack.package()
 if {n.removeprefix('platform_supervisor/'):h for n,h in files.items() if n.startswith('platform_supervisor/')}!=scope['files']:raise ValueError('Packaged supervisor differs from qualified source')
 (OUT/'bundle.zip').write_bytes(bundle);save('qualified.json',dict(passed=True,scope=scope,bundle_sha256=sha(bundle),bundle_files=files,provider_calls=0))
def request(key,path,body=None):
 req=urllib.request.Request(ORIGIN+path,data=raw(body) if body is not None else None,headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
def install_script(op,digest,files,previous):
 # Every executable byte below belongs to this protected broker, not a model
 # field, candidate script, archive name, objective or provider response.
 header='DIGEST='+repr(digest)+'\nFILES='+repr(files)+'\nPREVIOUS='+repr(previous)+'\nOP='+repr(op)+'\n'
 code=header+"""import hashlib,json,os,pathlib,subprocess
current=pathlib.Path('/opt/jumpserve/platform');target=pathlib.Path('/opt/jumpserve/platform-releases')/DIGEST
assert current.is_symlink() and current.resolve().name==PREVIOUS['bundle_sha256']
assert all(hashlib.sha256((current/n).read_bytes()).hexdigest()==h for n,h in PREVIOUS['bundle_files'].items())
runtime=pathlib.Path('/opt/jumpserve/runtime');science={p.relative_to(runtime).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert all(hashlib.sha256((target/n).read_bytes()).hexdigest()==h for n,h in FILES.items())
old=os.readlink(current);backup=pathlib.Path('/var/lib/jumpserve-platform')/('before-self-update-'+OP+'.txt')
if backup.exists():assert backup.read_text()==old
else:backup.write_text(old);backup.chmod(0o600)
pending=current.with_name('platform-self-update-'+OP);assert not pending.exists();pending.symlink_to(target,target_is_directory=True)
subprocess.run(['systemctl','stop','jumpserve-platform.service'],check=True,timeout=150)
try:
 os.replace(pending,current);subprocess.run(['systemctl','start','jumpserve-platform.service'],check=True,timeout=60)
 subprocess.run(['systemctl','is-active','--quiet','jumpserve-platform.service','jumpserve-openclaw.service'],check=True,timeout=30)
 assert all(hashlib.sha256((current/n).read_bytes()).hexdigest()==h for n,h in FILES.items())
 assert all(hashlib.sha256((runtime/n).read_bytes()).hexdigest()==h for n,h in science.items())
except BaseException:
 rollback=current.with_name('platform-self-rollback-'+OP);rollback.symlink_to(old,target_is_directory=True);os.replace(rollback,current)
 subprocess.run(['systemctl','start','jumpserve-platform.service'],check=True,timeout=60);raise
print(json.dumps(dict(passed=True,bundle_sha256=DIGEST,installed_files_verified=True,research_runtime_unchanged=True)))
"""
 stage=header+"""import hashlib,pathlib,stat,zipfile
archive=pathlib.Path('/tmp/supervisor-self-'+OP+'.zip');assert hashlib.sha256(archive.read_bytes()).hexdigest()==DIGEST
root=pathlib.Path('/opt/jumpserve/platform-releases')/DIGEST;assert not root.is_symlink();root.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(archive) as z:
 assert len(z.infolist())==len(FILES) and set(z.namelist())==set(FILES)
 for name,h in FILES.items():
  assert not name.startswith('/') and '..' not in pathlib.Path(name).parts and not stat.S_ISLNK(z.getinfo(name).external_attr>>16)
  value=z.read(name);assert hashlib.sha256(value).hexdigest()==h;target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():assert target.is_file() and not target.is_symlink() and target.read_bytes()==value
  else:target.write_bytes(value);target.chmod(0o644)
"""
 return ['set -eu','aws s3 cp '+shlex.quote('s3://'+BUCKET+'/platform-supervisor/self/'+digest+'.zip')+' '+shlex.quote('/tmp/supervisor-self-'+op+'.zip')+' --region us-east-1 --only-show-errors','python3.12 -B -c '+shlex.quote(stage),'python3.12 -B -c '+shlex.quote(code)]
def execute():
 import boto3
 session=boto3.Session(region_name=REGION)
 if session.client('sts').get_caller_identity()['Account']!=ACCOUNT:raise ValueError('JumpServe account required')
 key=session.client('secretsmanager').get_secret_value(SecretId='jumpserve/supabase-service-key')['SecretString']
 qualified=json.loads((OUT/'qualified.json').read_bytes());scope=qualified['scope'];op=os.environ['PLATFORM_OPERATION_ID'];revision=os.environ['SUPERVISOR_REVISION']
 headers={'User-Agent':'JumpServe-Supervisor-Release'}
 token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
 if token:headers['Authorization']='Bearer '+token
 req=urllib.request.Request('https://api.github.com/repos/jumpserve-networks/jumpserve-back-end/commits/main',headers=headers)
 with urllib.request.urlopen(req,timeout=30) as response:main=json.load(response)['sha']
 if main!=revision:raise ValueError('Backend main advanced; retain original intent and requalify')
 previous=request(key,'/rest/v1/rpc/platform_supervisor_runtime',{})
 if not previous or previous['source_revision']!=os.environ['PREVIOUS_SUPERVISOR_REVISION'] or previous['files']!=scope['previous_files']:raise ValueError('Actual installed predecessor differs; requalify current source')
 operation=request(key,'/rest/v1/platform_operations?id=eq.'+op+'&select=*')[0]
 expected=operation['request']
 if expected['component']!='supervisor-runtime' or expected['revision']!=revision or expected['previous_revision']!=previous['source_revision'] or expected['qualification_artifact_id']!=os.environ['SUPERVISOR_QUALIFICATION_ARTIFACT'] or expected['workflow_revision']!=os.environ['GITHUB_SHA']:raise ValueError('Original release request identity differs')
 artifact=request(key,'/rest/v1/platform_artifacts?id=eq.'+expected['qualification_artifact_id']+'&task_id=eq.'+operation['task_id']+'&select=id,name,sha256,storage_path')[0]
 req=urllib.request.Request(ORIGIN+'/storage/v1/object/platform-supervisor-private/'+artifact['storage_path'],headers={'apikey':key,'Authorization':'Bearer '+key})
 with urllib.request.urlopen(req,timeout=30) as response:certificate_bytes=response.read(100001)
 certificate=json.loads(certificate_bytes)
 if len(certificate_bytes)>100000 or sha(certificate_bytes)!=artifact['sha256'] or certificate.get('scope')!=scope or certificate.get('passed') is not True or certificate.get('policy_sha256')!=scope['files']['policy.json']:raise ValueError('Original retained qualification differs')
 files=qualified['bundle_files'];old_assets={n:h for n,h in previous['bundle_files'].items() if not n.startswith('platform_supervisor/')}
 if {n:h for n,h in files.items() if not n.startswith('platform_supervisor/')}!=old_assets:raise ValueError('Frozen self-update broker assets require separate qualification')
 value=(OUT/'bundle.zip').read_bytes();digest=sha(value);assert digest==qualified['bundle_sha256']
 s3=session.client('s3');path='platform-supervisor/self/'+digest+'.zip'
 try:s3.put_object(Bucket=BUCKET,Key=path,Body=value,IfNoneMatch='*',ServerSideEncryption='AES256')
 except Exception:assert s3.get_object(Bucket=BUCKET,Key=path)['Body'].read()==value
 admission=None
 for _ in range(90):
  admission=request(key,'/rest/v1/rpc/platform_supervisor_install',dict(p_operation=op,p_revision=revision,p_command=None))
  if not admission.get('wait_for_safe_boundary'):break
  time.sleep(5)
 if admission.get('wait_for_safe_boundary'):raise ValueError('Original research calls did not drain during the bounded self-install handoff; no command dispatched')
 ssm=session.client('ssm');comment='platform-self-update-'+op
 command=admission.get('command_id')
 if not command:
  if admission['dispatch_allowed']:
   save('installation-intent.json',dict(operation_id=op,comment=comment,bundle_sha256=digest))
   command=ssm.send_command(InstanceIds=[HOST],DocumentName='AWS-RunShellScript',Comment=comment,Parameters=dict(commands=install_script(op,digest,files,previous),executionTimeout=['300']))['Command']['CommandId']
  else:
   matches=[c for page in ssm.get_paginator('list_commands').paginate() for c in page['Commands'] if c.get('Comment')==comment and HOST in c.get('InstanceIds',[])]
   if len(matches)!=1:raise ValueError('Original installation acknowledgment is uncertain; no command resent')
   command=matches[0]['CommandId']
  request(key,'/rest/v1/rpc/platform_supervisor_install',dict(p_operation=op,p_revision=revision,p_command=command))
 save('command.json',dict(operation_id=op,command_id=command));result=None
 for _ in range(90):
  try:result=ssm.get_command_invocation(CommandId=command,InstanceId=HOST)
  except ssm.exceptions.InvocationDoesNotExist:time.sleep(5);continue
  if result['Status'] in ('Success','Failed','Cancelled','TimedOut'):break
  time.sleep(5)
 save('command-result.json',result)
 if not result or result['Status']!='Success' or result['ResponseCode']!=0:raise ValueError('Original self-install did not complete; reconcile retained command and rollback result')
 installed=json.loads(result['StandardOutputContent'].splitlines()[-1])
 if installed.get('passed') is not True or installed.get('bundle_sha256')!=digest or installed.get('installed_files_verified') is not True:raise ValueError('Installed source verification differs')
 proof=dict(installed,version='platform-production-verification-v1',component='supervisor-runtime',repository='jumpserve-networks/jumpserve-back-end',revision=revision,operation_id=op,command_id=command)
 manifest=dict(version=VERSION,source_revision=revision,files=scope['files'],bundle_files=files,bundle_sha256=digest)
 request(key,'/rest/v1/rpc/platform_supervisor_activate',dict(p_operation=op,p_manifest=manifest,p_verification=proof))
 Path('production-verification.json').write_bytes(raw(proof));save('production-verification.json',proof)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['pins','qualify','execute']);args=parser.parse_args();globals()[args.action]()
