"""Fixed-host Slack Gateway installer, used only for an authorized release.

Stage and validate the exact source first. Activation touches only the Slack
service; the research and platform workers are not restarted.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import zipfile

BASE = Path('/var/lib/jumpserve-platform-slack')
NODE = Path('/opt/jumpserve/node/bin/node')
CLI = Path('/opt/jumpserve/openclaw/node_modules/openclaw/openclaw.mjs')
FILES = {'slack_gateway.py','slack_api.py','slack-channel-policy.json','jumpserve-platform-slack.service',
         'install-slack-gateway.py','slack-tools/index.js','slack-tools/openclaw.plugin.json','slack-tools/package.json','qualification.json'}


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=300, **kwargs)
    if result.returncode:
        BASE.mkdir(mode=0o700,parents=True,exist_ok=True)
        log=BASE/'installer.log'
        with log.open('ab') as sink:
            sink.write(b'Failed fixed check: '+str(command[:3]).encode()+b'\n'+result.stdout[:500000]+result.stderr[:500000]+b'\n')
        log.chmod(0o600)
        raise RuntimeError('Fixed Slack installation check failed; private installer log retains diagnostics.')
    return result.stdout


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sha256'); parser.add_argument('--activate', action='store_true'); args=parser.parse_args()
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{64}', args.sha256):
        raise ValueError('Root and an exact qualified bundle hash are required.')
    identity=json.loads(run(['aws','sts','get-caller-identity','--region','us-east-1','--output','json']))
    if identity['Account']!='395567831870': raise ValueError('AWS account differs.')
    archive=BASE/'install'/(args.sha256+'.zip')
    original=archive.read_bytes()
    if hashlib.sha256(original).hexdigest()!=args.sha256: raise ValueError('Bundle hash differs.')
    release=Path('/opt/jumpserve/platform-slack-releases')/args.sha256
    release.mkdir(parents=True,exist_ok=True)
    release.parent.chmod(0o755); release.chmod(0o755)
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        if set(source.namelist())!=FILES or len(source.infolist())!=len(FILES): raise ValueError('Bundle inventory differs.')
        for item in source.infolist():
            if stat.S_ISLNK(item.external_attr>>16) or item.file_size>5000000: raise ValueError('Unsupported bundle member.')
            target=release/item.filename; target.parent.mkdir(parents=True,exist_ok=True)
            target.parent.chmod(0o755)
            raw=source.read(item)
            if target.exists() and target.read_bytes()!=raw: raise ValueError('Existing frozen source differs.')
            target.write_bytes(raw); target.chmod(0o644)
    proof=json.loads((release/'qualification.json').read_bytes())
    if proof.get('passed') is not True or proof.get('node_version')!='24.16.0' or proof.get('openclaw_version')!='2026.10.5':
        raise ValueError('Qualified native runtime differs.')
    for name, sha in proof['files'].items():
        if name not in FILES-{'qualification.json'} or hashlib.sha256((release/name).read_bytes()).hexdigest()!=sha:
            raise ValueError('Qualified source identity differs.')
    if set(proof['files'])!=FILES-{'qualification.json'}: raise ValueError('Qualification source inventory differs.')
    if run([str(NODE),'--version']).strip()!=b'v24.16.0': raise ValueError('Installed Node version differs.')
    package=json.loads((CLI.parent/'package.json').read_bytes())
    if package['version']!='2026.10.5': raise ValueError('Installed OpenClaw version differs.')
    uid=pwd.getpwnam('jumpserve').pw_uid; gid=pwd.getpwnam('jumpserve').pw_gid
    BASE.mkdir(mode=0o700,parents=True,exist_ok=True); os.chown(BASE,uid,gid); BASE.chmod(0o700)
    environment={}
    for line in Path('/etc/jumpserve-platform.env').read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1); environment[key]=value.strip("'\"")
    supabase=environment['SUPABASE_SECRET_ARN']
    if not re.fullmatch(r'arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/supabase-service-key(?:-[A-Za-z0-9]{6})?',supabase):
        raise ValueError('Supabase secret target differs.')
    slack='arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/platform-supervisor-slack-0gjzzA'
    env={'PATH':'/opt/jumpserve/node/bin:/usr/bin:/bin','LANG':'C.UTF-8',
         'OPENCLAW_STATE_DIR':str(BASE/'state'),'OPENCLAW_CONFIG_PATH':str(BASE/'openclaw.json'),
         'OPENCLAW_SKIP_CHANNELS':'1','OPENCLAW_DISABLE_DISCOVERY':'1',
         'SLACK_BOT_TOKEN':'xoxb-synthetic-offline','SLACK_APP_TOKEN':'xapp-synthetic-offline'}
    config=BASE/'openclaw.json'
    if not config.exists():
        config.write_text(json.dumps({'gateway':{'mode':'local'},'plugins':{'enabled':True}})); config.chmod(0o600); os.chown(config,uid,gid)
    # Only official, exact-version Slack code is installed. CLI state is isolated
    # from the research owner's profiles and from its OpenClaw installation.
    marker=BASE/'slack-plugin-installed.json'
    if not marker.exists():
        run(['/usr/sbin/runuser','-u','jumpserve','--',str(NODE),str(CLI),'plugins','install','@openclaw/slack@2026.10.5'],env=env)
    inspected=json.loads(run(['/usr/sbin/runuser','-u','jumpserve','--',str(NODE),str(CLI),'plugins','inspect','slack','--json'],env=env))
    if inspected.get('install',{}).get('integrity')!='sha512-AzWaSLfUQZWPwDdrLXzXeQ/AraXPEnkTTWKTKq4MFO39futFAxy+FulsYSStDYEd1B0YjtWGvXswBjdrmwRlBw==':
        raise ValueError('Official Slack plugin integrity differs.')
    vendor=Path(inspected['plugin']['rootDir']).resolve()
    if not vendor.is_relative_to(BASE): raise ValueError('Slack plugin state is not isolated.')
    version=json.loads((vendor/'package.json').read_bytes())['version']
    if version!='2026.10.5': raise ValueError('Installed Slack plugin version differs.')
    marker.write_text(json.dumps(dict(version=version,path=str(vendor)))); marker.chmod(0o600)
    sys.path.insert(0,str(release)); import slack_gateway as gateway
    candidate=gateway.configuration(BASE,'http://127.0.0.1:18801','synthetic-offline-bridge-token',json.loads((release/'slack-channel-policy.json').read_bytes()))
    installed=json.loads(config.read_bytes()).get('plugins',{})
    candidate['plugins']['load']['paths'].append(str(vendor))
    for key in ('installs',):
        if key in installed: candidate['plugins'][key]=installed[key]
    if 'slack' in installed.get('entries',{}): candidate['plugins']['entries']['slack']=installed['entries']['slack']
    staged=BASE/'qualified-config.json'; staged.write_bytes(gateway.canonical(candidate)); staged.chmod(0o600); os.chown(staged,uid,gid)
    check_env=dict(env,OPENCLAW_CONFIG_PATH=str(staged))
    gateway.write_configuration(candidate,staged,NODE,CLI,check_env,run_as_user=True)
    for command in (['config','validate','--json'],['plugins','inspect','jumpserve-supervisor','--runtime','--json'],
                    ['plugins','inspect','slack','--runtime','--json']):
        observed=json.loads(run(['/usr/sbin/runuser','-u','jumpserve','--',str(NODE),str(CLI),*command],env=check_env))
        if command[0]=='config' and observed.get('valid') is not True: raise ValueError('Native configuration validation failed.')
        if command[0]=='plugins':
            if observed['plugin'].get('status')!='loaded': raise ValueError('Native plugin failed to load.')
            if command[2]=='jumpserve-supervisor' and set(observed['plugin']['toolNames'])!=set(gateway.TOOLS):
                raise ValueError('Native supervisor tool registration differs.')
            if command[2]=='slack' and observed['plugin'].get('trustedOfficialInstall') is not True:
                raise ValueError('Slack plugin provenance was not trusted.')
    if not args.activate:
        print(json.dumps(dict(staged=True,bundle_sha256=args.sha256,service_started=False))); return
    # Staging precedes migrations; activation must prove the new read-only RPC
    # contract before touching the running service. No owner JWT is synthesized.
    sys.path.insert(0,'/opt/jumpserve/platform')
    from platform_supervisor.credentials import Credentials
    from platform_supervisor.store import Store
    credential=Credentials()
    store=Store(lambda:credential.secret(supabase),BASE,'7100785f-1d80-40be-bfb0-d9170caad095')
    gateway.verify_operations(store)
    # An explicit release has now qualified the source and native plugin. Keep
    # original calls/state across upgrades; never erase an unknown-call fence.
    run(['systemctl','stop','jumpserve-platform-slack.service']) if Path('/etc/systemd/system/jumpserve-platform-slack.service').exists() else None
    gateway.write_configuration(candidate,config,NODE,CLI,env,run_as_user=True)
    link=Path('/opt/jumpserve/platform-slack')
    if link.exists() and not link.is_symlink(): raise ValueError('Existing unversioned Slack installation needs reconciliation.')
    temporary=link.with_name('platform-slack.next')
    if temporary.is_symlink(): temporary.unlink()
    temporary.symlink_to(release); temporary.replace(link)
    target=Path('/etc/jumpserve-platform-slack.env')
    target.write_text('SUPABASE_SECRET_ARN='+supabase+'\nSLACK_SECRET_ARN='+slack+'\nAWS_DEFAULT_REGION=us-east-1\n'); target.chmod(0o600)
    unit=Path('/etc/systemd/system/jumpserve-platform-slack.service')
    unit.write_bytes((release/unit.name).read_bytes()); unit.chmod(0o644)
    run(['systemctl','daemon-reload']); run(['systemctl','enable','--now','jumpserve-platform-slack.service'])
    run(['systemctl','is-active','--quiet','jumpserve-platform-slack.service'])
    print(json.dumps(dict(installed=True,bundle_sha256=args.sha256,research_worker_restarted=False,
                          platform_worker_restarted=False,live_slack_conversation_verified=False)))


if __name__=='__main__': main()
