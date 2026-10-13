"""Scope a reviewed HTTP/2 agent release to the existing verified Agent stack."""
import argparse
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--diff',action='store_true');mode.add_argument('--deploy',action='store_true');a=p.parse_args()
    profile='jumpserve'
    identity=json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--profile',profile],text=True))
    if identity['Account']!='395567831870':raise RuntimeError('Wrong AWS account')
    if json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Wrong Supabase project')
    if a.deploy:
        spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
        rows=admin.query("select v.id,v.version,v.content_sha256,p.evaluation_report->'human_review'->'passed' reviewed,p.evaluation_report->'human_review'->'runtime_hashes' runtime_hashes,p.evaluation_report->>'tools_sha256' tools_sha256,p.evaluation_report->>'context_sha256' context_sha256,p.evaluation_report->>'renderer_sha256' renderer_sha256,p.evaluation_report->>'model_id' model_id from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id join agent_prompt_publications p on p.prompt_version_id=v.id where s.module_id='http2-compliance-study' order by p.published_at desc limit 1")
        if not rows or rows[0]['reviewed'] is not True:raise RuntimeError('No evaluated and manually reviewed HTTP2 prompt; deployment refused')
        settings_spec=importlib.util.spec_from_file_location('release_settings',ROOT/'agent/settings.py');settings=importlib.util.module_from_spec(settings_spec);settings_spec.loader.exec_module(settings)
        if rows[0]['model_id']!=settings.HTTP2_MODEL_ID:raise RuntimeError('Evaluated model differs from deployed module model')
        for field,file in [('tools_sha256','agent/tools/http2_study.py'),('context_sha256','agent/http2_context.py'),('renderer_sha256','agent/http2_answers.py')]:
            if rows[0][field]!=hashlib.sha256((ROOT/file).read_bytes()).hexdigest():raise RuntimeError('Evaluated research implementation changed')
        for file in ('agent/handler.py','agent/settings.py','agent/http2_answers.py','agent/http2_context.py'):
            if rows[0]['runtime_hashes'].get(file)!=hashlib.sha256((ROOT/file).read_bytes()).hexdigest():raise RuntimeError('Reviewed runtime code changed')
    credentials=json.loads(subprocess.check_output(['aws','configure','export-credentials','--profile',profile,'--format','process'],text=True))
    env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1')
    env.pop('AWS_PROFILE',None)
    command=['npx','cdk','deploy' if a.deploy else 'diff','JumpServeAgentStack']
    if a.deploy:command.extend(['--require-approval','never','--outputs-file','.test-artifacts/http2-agent-outputs.json'])
    subprocess.run(command,cwd=ROOT,env=env,check=True)
if __name__=='__main__':main()
