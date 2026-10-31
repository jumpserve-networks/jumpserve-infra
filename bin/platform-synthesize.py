"""Credential-free CDK synthesis in a container, with a fixed command set."""
import hashlib
import json
from pathlib import Path
import subprocess

def main():
    root=Path.cwd();candidate=(root/'.candidate').resolve()
    source=candidate/'.runtime-research/platform_supervisor/Dockerfile'
    # Use the workflow's reviewed tool recipe, not candidate-controlled code.
    recipe=root/'assets/platform/Dockerfile'
    if not recipe.is_file():raise ValueError('Reviewed platform tool recipe is missing.')
    tag='jumpserve-platform-release:'+hashlib.sha256(recipe.read_bytes()).hexdigest()[:16]
    out=root/'.test-artifacts/platform-release';out.mkdir(parents=True,exist_ok=True)
    with (out/'image.log').open('wb') as log:subprocess.run(['docker','build','--platform','linux/amd64','-t',tag,'-f',str(recipe),str(recipe.parent)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    commands=[['npm','ci','--ignore-scripts'],['python3','-B','bin/prepare-research-runtime.py','--backend','.runtime-research'],['python3','-B','bin/prepare-autonomy-runtime.py'],['python3','-m','pip','install','--target','agent/layer/python','--platform','manylinux2014_x86_64','--only-binary=:all:','--python-version','3.12','-r','test/http2-evaluation-requirements.txt'],['node','node_modules/aws-cdk/bin/cdk','synth','JumpServeBenchmarkStack','JumpServeAgentStack','--quiet']]
    for i,command in enumerate(commands):
        with (out/('synth-'+str(i)+'.log')).open('wb') as log:
            subprocess.run(['docker','run','--rm','--network','bridge','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','512','--memory','5g','--cpus','2','--mount','type=bind,source='+str(candidate)+',target=/workspace','--workdir','/workspace','--env','HOME=/tmp',tag,*command],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)

if __name__=='__main__':main()
