"""Guarded maintenance of the existing OpenClaw host; no release campaigns."""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('openclaw_security', ROOT / 'bin/research-security.py')
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)
admin = security.admin

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def aws(*args):
 raw=subprocess.check_output(['aws',*args,'--profile','jumpserve','--region','us-east-1','--output','json'],timeout=60)
 return json.loads(raw) if raw.strip() else {}

def target():
 account=aws('sts','get-caller-identity')['Account']
 if account!='395567831870' or admin.PROJECT_REF!='regphejnlvfpyokpniny':raise RuntimeError('Release target mismatch')
 result=security.target()
 return dict(result,aws_account=account,supabase_project=admin.PROJECT_REF)

def instance():
 stack=aws('cloudformation','describe-stacks','--stack-name','JumpServeOpenClawStack')['Stacks'][0]
 result=next(r['OutputValue'] for r in stack['Outputs'] if r['OutputKey']=='OpenClawWorkerInstanceId')
 if not re.fullmatch(r'i-[a-f0-9]+',result):raise RuntimeError('Invalid worker identity')
 return result

def ssm(commands):
 result=aws('ssm','send-command','--instance-ids',instance(),'--document-name','AWS-RunShellScript','--parameters',json.dumps(dict(commands=commands)))
 return dict(command_id=result['Command']['CommandId'],instance_id=instance())

def functions():
 resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
 return {kind:next(r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Lambda::Function' and r['LogicalResourceId'].startswith(prefix)) for kind,prefix in [('api','ResearchWorkflowApi'),('autonomy','ResearchWorkflowAutonomyWorker')]}

def auth_maintenance_guard():
 # Native interactive login does not acquire our Python refresh-owner lock by
 # itself. Require held admission/polling and drained calls before stopping it.
 config=aws('lambda','get-function-configuration','--function-name',functions()['api'])
 resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
 rules=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
 if config['Environment']['Variables'].get('RESEARCH_AUTONOMY_ENABLED')!='false' or len(rules)!=1 or aws('events','describe-rule','--name',rules[0])['State']!='DISABLED':raise RuntimeError('Hold new admission and autonomous polling before native authorization maintenance.')
 if admin.query("select (select count(*) from research_autonomy_tasks where status='running')+(select count(*) from research_model_dispatches where status in ('queued','running') or (status='unknown' and greatest(created_at,coalesce(lease_until,created_at),coalesce(ended_at,created_at))>clock_timestamp()-interval '10 minutes')) count")[0]['count']:raise RuntimeError('Drain active or recent uncertain model work before authorization maintenance; preserve original outcomes.')

def auth_maintenance_script(login):
 # login is an internal fixed command, never a caller-supplied CLI argument.
 return "set -eu; task_worker_active=0; if systemctl is-active --quiet jumpserve-openclaw.service; then task_worker_active=1; systemctl stop jumpserve-openclaw.service; fi; trap 'if test \"$task_worker_active\" = 1; then systemctl start jumpserve-openclaw.service; fi' EXIT; "+login

def native_auth_command():
 login='runuser -u jumpserve -- env HOME=/var/lib/jumpserve-openclaw OPENCLAW_STATE_DIR=/var/lib/jumpserve-openclaw/auth OPENCLAW_CONFIG_PATH=/var/lib/jumpserve-openclaw/auth/config.json PATH=/opt/jumpserve/node/bin:/usr/bin:/bin flock -x /var/lib/jumpserve-openclaw/auth/refresh.lock /opt/jumpserve/node/bin/node /opt/jumpserve/openclaw/node_modules/openclaw/openclaw.mjs models auth login --provider openai --method siwc'
 return 'stty cols 2000; sudo -n /bin/bash -c '+shlex.quote(auth_maintenance_script(login))

def host_refresh_command():
 program="import json,sys\nsys.path.insert(0,'/opt/jumpserve/runtime')\nimport openclaw_runtime as r\nr.verify_runtime()\nr.credential(force_refresh=True)\nprint(json.dumps(dict(native_refresh_verified=True,credential_contents_emitted=False)))"
 return 'runuser -u jumpserve -- env RESEARCH_AI_RUNTIME=openclaw-production-v1 /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['target', 'native-auth', 'host-refresh', 'host-check'])
    args = parser.parse_args()
    target_identity = target()
    if args.mode == 'target':
        print(json.dumps(target_identity))
        return
    directory = ROOT / '.test-artifacts/openclaw-maintenance' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, mode=0o700)
    receipt = dict(mode=args.mode, targets=target_identity, started_at=stamp(), status='running')
    path = directory / 'receipt.json'
    def save():
        path.write_text(json.dumps(receipt, indent=2) + '\n')
        path.chmod(0o600)
    save()
    try:
        if args.mode == 'native-auth':
            auth_maintenance_guard()
            command = ['aws', 'ssm', 'start-session', '--profile', 'jumpserve', '--region', 'us-east-1', '--target', instance(), '--document-name', 'AWS-StartInteractiveCommand', '--parameters', json.dumps(dict(command=[native_auth_command()]))]
            # Retain the previously installed, scoped Session Manager plugin path.
            env = dict(os.environ)
            env['PATH'] = str(ROOT / '.test-artifacts/openclaw-release/tools/sessionmanager-bundle/bin') + ':' + env.get('PATH', '')
            completed = subprocess.run(command, env=env, timeout=900)
            if completed.returncode:
                raise RuntimeError('Native host authorization did not complete; preserve its host-specific state and retry sign-in, never inference.')
            receipt.update(native_session_closed=True, authorization_verified=False)
        elif args.mode == 'host-refresh':
            receipt['ssm'] = ssm([host_refresh_command()])
        else:
            expected = json.loads((ROOT / 'research-workflow-runtime.json').read_bytes())['files']
            program = "import hashlib,json,sys\nfrom pathlib import Path\nexpected=" + repr(expected) + "\nactual={n:hashlib.sha256((Path('/opt/jumpserve/runtime')/n).read_bytes()).hexdigest() for n in expected}\nassert actual==expected,'Pinned host source hashes differ'\nsys.path.insert(0,'/opt/jumpserve/runtime')\nimport openclaw_runtime as r\nr.verify_runtime()\ncatalog=r.catalog(r.credential())\nprint(json.dumps(dict(runtime=r.VERSION,native_refresh_interface_verified=True,catalog=catalog,api_key_fallback=False,credential_contents_emitted=False)))"
            command = 'runuser -u jumpserve -- env RESEARCH_AI_RUNTIME=openclaw-production-v1 /opt/jumpserve/python/bin/python -B -c ' + shlex.quote(program)
            receipt['ssm'] = ssm([command])
        receipt['status'] = 'complete'
    except Exception as error:
        receipt.update(status='failed', reason=str(error))
        raise
    finally:
        receipt['ended_at'] = stamp()
        save()
        print(json.dumps(dict(directory=str(directory), **receipt)))

if __name__ == '__main__':
    main()
