"""Credential-free CDK synthesis in a container, with a fixed command set."""
import hashlib
import os
from pathlib import Path
import subprocess

def main():
    root=Path.cwd();candidate=(root/'.candidate').resolve()
    # Use the workflow's reviewed tool recipe, not candidate-controlled code.
    recipe=root/'assets/platform/Dockerfile'
    if not recipe.is_file():raise ValueError('Reviewed platform tool recipe is missing.')
    tag='jumpserve-platform-release:'+hashlib.sha256(recipe.read_bytes()).hexdigest()[:16]
    out=root/'.test-artifacts/platform-release';out.mkdir(parents=True,exist_ok=True)
    with (out/'image.log').open('wb') as log:subprocess.run(['docker','build','--platform','linux/amd64','-t',tag,'-f',str(recipe),str(recipe.parent)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    commands=[['npm','ci','--ignore-scripts'],['python3','-B','bin/prepare-research-runtime.py','--backend','.runtime-research'],['python3','-B','bin/prepare-autonomy-runtime.py'],['node','node_modules/aws-cdk/bin/cdk','synth','--app','node node_modules/ts-node/dist/bin.js --prefer-ts-exts bin/benchmark.ts','JumpServeBenchmarkStack','--quiet','--no-lookups']]
    # Match the bind-mounted checkout owner while retaining the dropped capabilities.
    user=str(os.getuid())+':'+str(os.getgid())
    for i,command in enumerate(commands):
        with (out/('synth-'+str(i)+'.log')).open('wb') as log:
            subprocess.run(['docker','run','--rm','--user',user,'--network','bridge','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','512','--memory','5g','--cpus','2','--mount','type=bind,source='+str(candidate)+',target=/workspace','--workdir','/workspace','--env','HOME=/tmp',tag,*command],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)

if __name__=='__main__':main()
