"""Prepare exact uploads and one SSM request; never upload, install or resume."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import uuid

ROOT=Path(__file__).resolve().parents[1]
HOST='i-00dc52abbcf706670'
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def build(directory,outputs):
 directory=Path(directory);packet=json.loads((directory/'packet.json').read_bytes());values=outputs['JumpServeIntakeStack']
 release=packet['release_id'];binding=packet['manifest']['source_binding']
 if str(uuid.UUID(release))!=release or not re.fullmatch('[a-f0-9]{64}',binding):raise ValueError('Exact release and source binding required.')
 if values['IntakeInstanceId']!=HOST or values['IntakeRuntimeBucket']!=BUCKET or values['IntakeSourceBinding'] not in (binding,packet['previous_manifest']['source_binding']):
  raise ValueError('Existing fixed intake host and original/repaired source required.')
 if packet['installed'] is not False or packet['production_mutations']!=0 or packet['scope']['changed_files']!=['autonomy.py'] or packet['research_checks']<1:
  raise ValueError('Uninstalled, locally qualified initializer packet required.')
 if digest((directory/'bundle.zip').read_bytes())!=packet['bundle_sha256']:raise ValueError('Retained archive differs.')
 gate=ROOT/'assets/platform/intake-initialization-gate.py'
 if digest(gate.read_bytes())!=packet['gate_sha256']:raise ValueError('Frozen initialization gate changed after qualification.')
 files={'packet.json':directory/'packet.json','bundle.zip':directory/'bundle.zip',
  'intake-initialization-gate.py':gate,'install-intake-initialization.py':ROOT/'assets/platform/install-intake-initialization.py'}
 target='/opt/jumpserve/intake-initializer-tools/'+release
 commands=['set -eu','umask 077','test "$(aws sts get-caller-identity --query Account --output text --region us-east-1)" = 395567831870','mkdir -p '+shlex.quote(target)]
 uploads=[]
 for name,path in files.items():
  sha=digest(path.read_bytes());key='intake-repair/'+binding+'/'+sha+'-'+name
  uploads.append(dict(source=str(path.resolve()),bucket=BUCKET,key=key,sha256=sha))
  destination=target+'/'+name
  commands+=['aws s3 cp '+shlex.quote('s3://'+BUCKET+'/'+key)+' '+shlex.quote(destination)+' --region us-east-1 --only-show-errors',
   'echo '+shlex.quote(sha+'  '+destination)+' | sha256sum --check']
 commands.append('/opt/jumpserve/python/bin/python -B '+shlex.quote(target+'/install-intake-initialization.py')+' --packet '+shlex.quote(target+'/packet.json')+' --bundle '+shlex.quote(target+'/bundle.zip'))
 request=dict(DocumentName='AWS-RunShellScript',InstanceIds=[HOST],Comment='Intake initializer repair '+release,TimeoutSeconds=600,
  Parameters=dict(commands=commands,executionTimeout=['540']))
 return dict(uploads=uploads,request=request,release_id=release,source_binding=binding,
  required_read_prefix='arn:aws:s3:::'+BUCKET+'/intake-repair/'+binding+'/*',
  routing_must_be_disabled=True,reconcile_original_ssm_command_before_retry=True,executed=False,production_mutations=0)


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--packet-directory',type=Path,required=True)
 parser.add_argument('--outputs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args();value=build(args.packet_directory,json.loads(args.outputs.read_bytes()))
 if args.output.exists():raise ValueError('Keep the original prepared installation receipt; choose a new output only after review.')
 args.output.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(prepared=str(args.output),executed=False,production_mutations=0)))
