"""Fixed workflow input binding; untrusted strings never become shell code."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import uuid

def inputs():
    component=os.environ['PLATFORM_COMPONENT'];repository=os.environ['PLATFORM_REPOSITORY'];revision=os.environ['PLATFORM_REVISION'];operation=os.environ['PLATFORM_OPERATION_ID']
    expected={'frontend':'jumpserve-networks/jumpserve-front-end','infrastructure':'jumpserve-networks/jumpserve-infra'}
    if expected.get(component)!=repository or not re.fullmatch('[a-f0-9]{40}',revision) or str(uuid.UUID(operation))!=operation:raise ValueError('Exact platform release identity required.')
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/'+repository+'/git/ref/heads/main',headers={'User-Agent':'JumpServe-Platform-Release'}),timeout=30) as response:main=json.loads(response.read(100000))['object']['sha']
    if main!=revision:raise ValueError('Production main advanced; do not deploy a stale revision.')
    return component,repository,revision,operation

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pins',action='store_true');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    component,repository,revision,operation=inputs()
    if args.pins:
        pins=dict(research=json.loads(Path('.candidate/research-workflow-runtime.json').read_bytes())['source_revision'],real_world=json.loads(Path('.candidate/real-world-runtime.json').read_bytes())['revision'])
        if any(not re.fullmatch('[a-f0-9]{40}',value) for value in pins.values()):raise ValueError('Invalid runtime pin.')
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:
            for name,value in pins.items():output.write(name+'='+value+'\n')
    if args.execute:subprocess.run(['python3','-B','bin/platform-production.py','--component',component,'--repository',repository,'--revision',revision,'--operation-id',operation],check=True,timeout=4000)

if __name__=='__main__':main()
