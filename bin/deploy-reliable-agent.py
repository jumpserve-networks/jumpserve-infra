"""Deploy only reviewed ReliableSketch code in the existing JumpServe Agent stack."""
import argparse,hashlib,importlib.util,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--diff',action='store_true');m.add_argument('--deploy',action='store_true');a=p.parse_args()
 if json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve']))['Account']!='395567831870' or json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Target mismatch')
 if a.deploy:
  report=json.loads((ROOT/'docs/reliable-study-validation/chat-evaluation-v3.json').read_text())
  if len(report['cases'])!=12 or not all(c['passed'] for c in report['cases']) or not report.get('secondary_review',{}).get('passed'):raise RuntimeError('Actual answer evaluations/review incomplete')
  for file,digest in report['runtime_hashes'].items():
   if hashlib.sha256((ROOT/file).read_bytes()).hexdigest()!=digest:raise RuntimeError('Reviewed runtime changed')
  spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
  rows=admin.query("select v.id,v.content_sha256 from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id='reliable-sketch-study' and v.published_at is not null")
  if len(rows)!=1 or rows[0]['id']!=report['prompt_version_id'] or rows[0]['content_sha256']!=report['prompt_content_sha256']:raise RuntimeError('Published prompt differs')
  readiness=json.loads((ROOT/'docs/reliable-study-validation/predeployment.json').read_text())
  if readiness['release_blocking_checks_passed'] is not True:raise RuntimeError('Release blockers remain')
 c=json.loads(subprocess.check_output(['aws','configure','export-credentials','--profile','jumpserve','--format','process']))
 env=dict(os.environ,AWS_ACCESS_KEY_ID=c['AccessKeyId'],AWS_SECRET_ACCESS_KEY=c['SecretAccessKey'],AWS_SESSION_TOKEN=c['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
 command=['npx','cdk','deploy' if a.deploy else 'diff','JumpServeAgentStack']
 if a.deploy:command+=['--require-approval','never','--outputs-file','docs/reliable-study-validation/agent-outputs.json']
 subprocess.run(command,cwd=ROOT,env=env,check=True)
if __name__=='__main__':main()
