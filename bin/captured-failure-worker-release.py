"""Install one qualified worker bundle with durable SSM identity and readback."""
import datetime as dt,importlib.util,json,shlex,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HOST='i-087f1493809643115';BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
def script(operation,digest,files,previous):
 header='OP='+repr(operation)+'\nDIGEST='+repr(digest)+'\nFILES='+repr(files)+'\nPREVIOUS='+repr(previous)+'\n'
 code=header+'''import fcntl,hashlib,json,os,pathlib,signal,stat,subprocess,time,zipfile
runtime=pathlib.Path('/opt/jumpserve/runtime');releases=pathlib.Path('/opt/jumpserve/research-runtime-releases');releases.mkdir(exist_ok=True);releases.chmod(0o755)
archive=pathlib.Path('/tmp/research-worker-'+OP+'.zip');assert hashlib.sha256(archive.read_bytes()).hexdigest()==DIGEST
assert all((runtime/n).is_file() and not (runtime/n).is_symlink() and hashlib.sha256((runtime/n).read_bytes()).hexdigest()==h for n,h in PREVIOUS.items())
target=releases/DIGEST;assert not target.is_symlink();target.mkdir(exist_ok=True);target.chmod(0o755)
with zipfile.ZipFile(archive) as z:
 assert set(z.namelist())==set(FILES) and len(z.infolist())==len(FILES)
 for n,h in FILES.items():
  assert not n.startswith('/') and '..' not in pathlib.Path(n).parts and not stat.S_ISLNK(z.getinfo(n).external_attr>>16)
  raw=z.read(n);assert hashlib.sha256(raw).hexdigest()==h
  p=target/n;p.parent.mkdir(parents=True,exist_ok=True)
  for parent in p.parents:
   if parent==releases:break
   assert not parent.is_symlink();parent.chmod(0o755)
  if p.exists():assert p.is_file() and not p.is_symlink() and p.read_bytes()==raw
  else:p.write_bytes(raw);p.chmod(0o644)
assert {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}==set(FILES)
def snapshot(root):
 # Runtime installation has no write path into retained state. Check directory
 # identities and the small credential store; do not crawl experiment data or
 # rebuildable dependency caches. Original payload hashes remain in Supabase.
 entries={};total=0
 for name in ('.','spool','auth','auth/state'):
  p=root/name
  if not p.exists():entries[name]='absent';continue
  info=p.lstat();assert stat.S_ISDIR(info.st_mode) and not p.is_symlink()
  entries[name]=(info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode))
 for name in ('auth/state/openclaw.sqlite','auth/state/openclaw.sqlite-wal','auth/state/openclaw.sqlite-shm'):
  p=root/name
  if not p.exists():entries[name]='absent';continue
  info=p.lstat();assert stat.S_ISREG(info.st_mode) and not p.is_symlink();total+=info.st_size
  assert total<=16_000_000,'Credential store exceeds bounded verification; nothing switched'
  raw=p.read_bytes();assert len(raw)==info.st_size
  entries[name]=(info.st_size,hashlib.sha256(raw).hexdigest())
 return entries
def interrupted(signum,frame):raise TimeoutError('Installation interrupted; restore the prior source')
signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
old=runtime.resolve();backup=releases/('before-'+OP);pending=runtime.with_name('runtime-pending-'+OP)
assert not pending.exists() and not backup.exists()
supervisor=pathlib.Path('/opt/jumpserve/platform').resolve()
switched=False;moved=False;auth_lock=None
try:
 subprocess.run(['systemctl','stop','jumpserve-openclaw.service'],check=True,timeout=150)
 state=pathlib.Path('/var/lib/jumpserve-openclaw');lock=state/'auth/refresh.lock'
 if lock.exists():auth_lock=lock.open('rb');fcntl.flock(auth_lock,fcntl.LOCK_EX)
 before=snapshot(state);env=pathlib.Path('/etc/jumpserve-openclaw.env');env_before=hashlib.sha256(env.read_bytes()).hexdigest()
 if not runtime.is_symlink():runtime.rename(backup);old=backup;moved=True
 pending.symlink_to(target,target_is_directory=True);os.replace(pending,runtime);switched=True
 assert all(hashlib.sha256((runtime/n).read_bytes()).hexdigest()==h for n,h in FILES.items())
 assert snapshot(state)==before and pathlib.Path('/opt/jumpserve/platform').resolve()==supervisor
 assert hashlib.sha256(env.read_bytes()).hexdigest()==env_before
 if auth_lock:auth_lock.close();auth_lock=None
 subprocess.run(['systemctl','start','jumpserve-openclaw.service'],check=True,timeout=60)
 for _ in range(5):
  time.sleep(1)
  subprocess.run(['systemctl','is-active','--quiet','jumpserve-openclaw.service'],check=True,timeout=30)
  current=int(subprocess.check_output(['systemctl','show','jumpserve-openclaw.service','-p','MainPID','--value'],text=True).strip())
  assert current>0 and pathlib.Path('/proc/'+str(current)+'/cwd').resolve()==target
  if _==0:pid=current
  else:assert pid==current,'Worker restarted during source readback'
 assert all(hashlib.sha256((runtime/n).read_bytes()).hexdigest()==h for n,h in FILES.items())
except BaseException:
 if switched:runtime.unlink()
 if moved:backup.rename(runtime)
 elif switched:runtime.symlink_to(old,target_is_directory=True)
 subprocess.run(['systemctl','start','jumpserve-openclaw.service'],check=True,timeout=60)
 raise
finally:
 if auth_lock:auth_lock.close()
print(json.dumps(dict(passed=True,bundle_sha256=DIGEST,installed_files_verified=True,spool_unchanged=True,credentials_unchanged=True,
 retained_state_verified_before_restart=True,retained_state_verification='directory-identities-and-locked-auth-files-v1',
 supervisor_unchanged=True,worker_pid=pid,provider_calls=0,scientific_completion=False)))
'''
 return ['set -eu','aws s3 cp '+shlex.quote('s3://'+BUCKET+'/platform-supervisor/research-runtime/'+digest+'.zip')+' '+shlex.quote('/tmp/research-worker-'+operation+'.zip')+' --region us-east-1 --only-show-errors','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(code)]
def persistence(session):
 s=importlib.util.spec_from_file_location('fixed_service_database',ROOT/'bin/platform-service-release.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 key=session.client('secretsmanager').get_secret_value(SecretId='jumpserve/supabase-service-key')['SecretString'];return m.Database(key)
def install(session,operation,revision,qualification,bundle):
 import hashlib
 db=persistence(session)
 digest=hashlib.sha256(bundle).hexdigest();path='platform-supervisor/research-runtime/'+digest+'.zip';s3=session.client('s3')
 try:s3.put_object(Bucket=BUCKET,Key=path,Body=bundle,IfNoneMatch='*',ServerSideEncryption='AES256')
 except Exception:
  if s3.get_object(Bucket=BUCKET,Key=path)['Body'].read()!=bundle:raise ValueError('Original worker bundle differs.') from None
 def admit(command=None):return db.request('/rest/v1/rpc/research_runtime_worker_install',dict(p_operation=operation,p_revision=revision,p_command=command))
 for _ in range(90):
  admission=admit()
  if not admission.get('wait_for_safe_boundary'):break
  time.sleep(5)
 else:raise ValueError('Active research did not drain; no worker install command dispatched.')
 request=dict(DocumentName='AWS-RunShellScript',InstanceIds=[HOST],Comment='captured-failure-worker-'+operation,TimeoutSeconds=60,
  Parameters=dict(commands=script(operation,digest,qualification['manifest']['files'],qualification['previous_manifest']['files']),executionTimeout=['600']))
 ssm=session.client('ssm');command=admission.get('command_id')
 if not command:
  if admission['dispatch_allowed']:command=ssm.send_command(**request)['Command']['CommandId']
  else:
   matches=[];options=dict(InstanceId=HOST,MaxResults=50,Filters=[dict(key='InvokedAfter',value=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=1)).isoformat())])
   for _ in range(20):
    page=ssm.list_commands(**options);matches.extend(c for c in page['Commands'] if c.get('Comment')==request['Comment'])
    if not page.get('NextToken'):break
    options['NextToken']=page['NextToken']
   else:raise ValueError('Original worker command lookup exceeds its bound.')
   if len(matches)!=1 or any(matches[0].get(k)!=request[k] for k in ('DocumentName','InstanceIds','Parameters','TimeoutSeconds')):raise ValueError('Original worker install acknowledgment is uncertain; no replacement sent.')
   command=matches[0]['CommandId']
  admit(command)
 for _ in range(120):
  try:result=ssm.get_command_invocation(CommandId=command,InstanceId=HOST)
  except ssm.exceptions.InvocationDoesNotExist:time.sleep(5);continue
  if result['Status'] in ('Pending','InProgress','Delayed'):time.sleep(5);continue
  if result['Status']!='Success' or result['ResponseCode']!=0:raise ValueError('Original research worker installation failed; reconcile command '+command)
  proof=json.loads(result['StandardOutputContent'].splitlines()[-1]);break
 else:raise ValueError('Original worker installation remains pending: '+command)
 if proof.get('passed') is not True or proof.get('bundle_sha256')!=digest or proof.get('installed_files_verified') is not True:raise ValueError('Actual installed worker source differs.')
 proof.update(revision=revision,command_id=command,source_binding=qualification['scope']['source_binding'])
 db.request('/rest/v1/rpc/research_runtime_worker_activate',dict(p_operation=operation,p_manifest=qualification['manifest'],p_verification=proof))
 return proof
