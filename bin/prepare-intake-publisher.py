"""Prepare an exact SSM publisher installation request; never execute or deploy."""
import argparse,hashlib,json,re,shlex
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OWNER='i-087f1493809643115'
ROLE='JumpServeOpenClawStack-WorkerRoleAAEB1603-AMhySy8UAI7S'

def build(outputs):
 values=outputs['JumpServeIntakeStack'];pin=json.loads((ROOT/'intake-worker-runtime.json').read_bytes())
 if values['IntakeSourceBinding']!=pin['source_binding']:raise ValueError('Deployed intake source differs from the reviewed pin.')
 for name in ('IntakeRuntimeBucket','IntakePublisherBucket'):
  if not re.fullmatch(r'cdk-[a-z0-9]+-assets-395567831870-us-east-1',values[name]):raise ValueError('Account-bound asset bucket required.')
 for name in ('IntakeRuntimeObject','IntakePublisherObject'):
  if not re.fullmatch(r'[a-f0-9]{64}(?:\.[a-z]+)?',values[name]):raise ValueError('Immutable CDK object required.')
 release='/opt/jumpserve/intake-releases/'+pin['source_binding']
 verify='import hashlib,json,pathlib; r=pathlib.Path('+repr(release)+'); m=json.loads((r/"intake-manifest.json").read_bytes()); assert m["source_binding"]=='+repr(pin['source_binding'])+'; assert m["source_revision"]=='+repr(pin['source_revision'])+'; assert hashlib.sha256(json.dumps(m["files"],sort_keys=True,separators=(",",":")).encode()).hexdigest()==m["source_binding"]; assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==h for n,h in m["files"].items())'
 service_sha=hashlib.sha256((ROOT/'assets/openclaw/jumpserve-intake-access.service').read_bytes()).hexdigest()
 commands=['set -eu','umask 077',
  'test "$(aws sts get-caller-identity --query Account --output text --region us-east-1)" = 395567831870',
  'case "$(aws sts get-caller-identity --query Arn --output text --region us-east-1)" in arn:aws:sts::395567831870:assumed-role/'+ROLE+'/*) ;; *) exit 1 ;; esac',
  'test -f /var/lib/jumpserve-openclaw/auth/state/openclaw.sqlite',
  'test ! -e /opt/jumpserve/intake-runtime || test -L /opt/jumpserve/intake-runtime',
  'mkdir -p '+release,
  'aws s3 cp s3://'+values['IntakeRuntimeBucket']+'/'+values['IntakeRuntimeObject']+' /opt/jumpserve/intake-publisher.zip --region us-east-1',
  'unzip -q -o /opt/jumpserve/intake-publisher.zip -d '+release,
  '/opt/jumpserve/python/bin/python -c '+shlex.quote(verify),
  'aws s3 cp s3://'+values['IntakePublisherBucket']+'/'+values['IntakePublisherObject']+' /opt/jumpserve/intake-publisher.service --region us-east-1',
  'echo '+shlex.quote(service_sha+'  /opt/jumpserve/intake-publisher.service')+' | sha256sum --check',
  'systemctl stop jumpserve-intake-access.service || true',
  'chmod a+rx /opt/jumpserve/intake-releases',
  'chmod -R a+rX '+release,
  'ln -sfn '+release+' /opt/jumpserve/intake-runtime',
  "runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c 'import sys; sys.path.insert(0,\"/opt/jumpserve/intake-runtime\"); import intake_worker; intake_worker.runtime.verify_runtime()'",
  'install -m 644 /opt/jumpserve/intake-publisher.service /etc/systemd/system/jumpserve-intake-access.service',
  'systemctl daemon-reload','systemctl enable --now jumpserve-intake-access.service',
  'systemctl is-active jumpserve-intake-access.service']
 return dict(DocumentName='AWS-RunShellScript',InstanceIds=[OWNER],Comment='Install exact warm-intake access publisher; retain the existing refresh owner and workers.',TimeoutSeconds=600,Parameters=dict(commands=commands,executionTimeout=['600']))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--outputs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 args.output.write_text(json.dumps(build(json.loads(args.outputs.read_bytes())),indent=2)+'\n')
 print(json.dumps(dict(prepared=str(args.output),executed=False,production_mutations=0)))

if __name__=='__main__':main()
