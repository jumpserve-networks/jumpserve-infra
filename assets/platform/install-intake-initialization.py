"""Install the narrowly qualified initializer on the existing dedicated host."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.request
import zipfile


def load_gate():
 path=Path(__file__).with_name('intake-initialization-gate.py')
 spec=importlib.util.spec_from_file_location('fixed_intake_gate',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def database_reader():
 import boto3
 session=boto3.Session(region_name='us-east-1')
 if session.get_credentials().method!='iam-role' or session.client('sts').get_caller_identity()['Account']!='395567831870':raise ValueError('JumpServe instance role required.')
 key=session.client('secretsmanager').get_secret_value(SecretId='jumpserve/supabase-service-key')['SecretString']
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):raise ValueError('Redirect refused.')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 paths={
  'runtime':'research_intake_runtime?select=enabled,status,seen_at,configuration',
  'leases':'research_autonomy_tasks?select=id&stage=eq.intake&lease_token=not.is.null&limit=1',
  'dispatches':'research_model_dispatches?select=id&dispatch_lane=eq.intake&status=in.(queued,running)&limit=1'}
 def read(name):
  req=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/rest/v1/'+paths[name],headers={'apikey':key,'Authorization':'Bearer '+key})
  with opener.open(req,timeout=20) as response:return json.load(response)
 return read


def drained(read):
 runtime=read('runtime')
 if len(runtime)!=1 or runtime[0]['enabled'] is not False or read('leases') or read('dispatches'):
  raise ValueError('Disable intake routing and drain original leases/dispatches before installing.')


def stage(packet,bundle,root,gate):
 old=packet['previous_manifest'];new=packet['manifest'];scope=packet['scope']
 if packet.get('version')!=gate.VERSION or packet.get('gate_sha256')!=gate.digest(Path(gate.__file__).read_bytes()) or packet.get('production_mutations')!=0:
  raise ValueError('Exact locally qualified repair packet required.')
 if not re.fullmatch('[a-f0-9]{64}',new.get('source_binding','')) or not re.fullmatch('[a-f0-9]{40}',new.get('source_revision','')):
  raise ValueError('Exact repaired source identity required.')
 if set(new['files'])!=set(old['files']) or scope.get('changed_files')!=['autonomy.py']:
  raise ValueError('Original runtime file coverage must remain unchanged.')
 if new['source_revision']!=packet['source_revision'] or new['version']!='warm-intake-v1' or old['version']!='warm-intake-v1' or gate.digest(gate.canonical(old['files']))!=old['source_binding']:
  raise ValueError('Original and repaired runtime identities differ.')
 if gate.digest(bundle.read_bytes())!=packet['bundle_sha256']:raise ValueError('Repair archive hash differs.')
 current=root/'intake-runtime';original=current.resolve()
 if current.is_symlink() and original!=root/'intake-releases'/old['source_binding']:raise ValueError('Original intake pointer differs.')
 manifest=json.loads((original/'intake-manifest.json').read_bytes())
 if manifest!=old:raise ValueError('Actual original intake manifest differs; reconcile before replacement.')
 target=root/'intake-releases'/new['source_binding']
 if target.is_symlink() or target.parent.is_symlink():raise ValueError('Release directory cannot be a link.')
 target.mkdir(parents=True,exist_ok=True);target.parent.chmod(0o755);target.chmod(0o755)
 with zipfile.ZipFile(bundle) as archive:
  expected={*new['files'],'intake-manifest.json'}
  if len(archive.infolist())!=len(expected) or set(archive.namelist())!=expected:raise ValueError('Repair archive coverage differs.')
  for item in archive.infolist():
   name=item.filename
   if name.startswith('/') or '..' in Path(name).parts or stat.S_ISLNK(item.external_attr>>16) or item.file_size>2000000:
    raise ValueError('Repair archive path or size is unsafe.')
   raw=archive.read(name)
   if name=='intake-manifest.json':
    if json.loads(raw)!=new:raise ValueError('Repaired archive manifest differs.')
   elif gate.digest(raw)!=new['files'][name]:raise ValueError('Repaired file hash differs.')
   path=target/name
   if any(p.is_symlink() for p in [path,*path.parents] if p.is_relative_to(target)):raise ValueError('Release file cannot be a link.')
   path.parent.mkdir(parents=True,exist_ok=True)
   if path.exists() and path.read_bytes()!=raw:raise ValueError('Existing immutable repair source differs.')
   if not path.exists():path.write_bytes(raw)
   path.chmod(0o644)
 for directory,_,_ in os.walk(target):Path(directory).chmod(0o755)
 # The local gate normally also verifies predecessor tests. Those tests are
 # qualified before credentials; installation independently rechecks every
 # runtime byte and the exact two AST edits against the actual old host files.
 for name,expected in old['files'].items():
  previous=gate.read(original,name);candidate=gate.read(target,name)
  if gate.digest(previous)!=expected:raise ValueError('Actual original source hash differs.')
  if name=='autonomy.py':
   if gate.normalized(previous)!=gate.normalized(candidate,corrected=True):raise ValueError('Initializer scope differs.')
  elif previous!=candidate:raise ValueError('Protected runtime file changed.')
 if new['files']!=scope['files'] or gate.digest(gate.canonical(new['files']))!=new['source_binding']:
  raise ValueError('Source binding differs from qualified repair.')
 return current,target


def install(packet,bundle,read,root=Path('/opt/jumpserve'),run=subprocess.run):
 root=Path(root).resolve()
 gate=load_gate();drained(read);current,target=stage(packet,Path(bundle),root,gate)
 run(['runuser','-u','jumpserve','--','/opt/jumpserve/python/bin/python','-B','-c',
  'import sys;sys.path.insert(0,'+repr(str(target))+');import intake_worker;intake_worker.runtime.verify_runtime()'],check=True,timeout=60,capture_output=True)
 drained(read)
 previous=current.resolve() if current.is_symlink() else current.parent/'intake-releases'/packet['previous_manifest']['source_binding']
 if not current.is_symlink() and previous.exists():raise ValueError('Original intake directory backup already exists.')
 temporary=current.with_name('intake-initializer-pending')
 if temporary.exists() or temporary.is_symlink():raise ValueError('Original install pointer requires reconciliation.')
 run(['systemctl','stop','jumpserve-intake.service'],check=True,timeout=250)
 try:
  if not current.is_symlink():
   current.rename(previous)
  temporary.symlink_to(target,target_is_directory=True);os.replace(temporary,current)
  run(['systemctl','start','jumpserve-intake.service'],check=True,timeout=60)
 except BaseException:
  if previous.exists():
   rollback=current.with_name('intake-initializer-rollback')
   if rollback.exists() or rollback.is_symlink():raise ValueError('Original rollback pointer requires reconciliation.')
   rollback.symlink_to(previous,target_is_directory=True);os.replace(rollback,current)
  if current.exists():run(['systemctl','start','jumpserve-intake.service'],check=True,timeout=60)
  raise
 if not all(gate.digest(gate.read(current.resolve(),n))==h for n,h in packet['manifest']['files'].items()):raise ValueError('Installed source verification differs.')
 drained(read)
 return dict(installed_files_verified=True,
  source_binding=packet['manifest']['source_binding'],source_revision=packet['source_revision'],
  release_id=packet['release_id'],routing_enabled=False,requires_fresh_ready_heartbeat_before_resume=True)


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--packet',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
 args=parser.parse_args();print(json.dumps(install(json.loads(args.packet.read_bytes()),args.bundle,database_reader())))
