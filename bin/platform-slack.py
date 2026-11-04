"""Configure and check the fixed JumpServe Slack secret without printing tokens.

Credentials enter through a non-echoing terminal prompt, remain in memory, and
reach AWS through its SDK. They never enter argv, source or evidence files.
This utility does not start a Gateway or send Slack messages.
"""
import argparse
import datetime as dt
import getpass
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
import boto3

ACCOUNT = '395567831870'
REGION = 'us-east-1'
PROFILE = 'jumpserve'
SECRET = 'jumpserve/platform-supervisor-slack'
ROOT = Path(__file__).resolve().parents[1]
TEAM = 'T01J887B6CE'
CHANNEL = 'C0CEXNJE0HX'
APP = 'A0CEQTE50TF'
_SESSION = None


def aws(service, operation, payload):
    global _SESSION
    if (service, operation) not in {('sts', 'get-caller-identity'), ('secretsmanager', 'get-secret-value'), ('secretsmanager', 'put-secret-value')}:
        raise ValueError('AWS operation is outside this utility.')
    if service == 'secretsmanager' and payload.get('SecretId') != SECRET:
        raise ValueError('AWS secret target differs.')
    try:
        if _SESSION is None:
            # This SDK predates `aws login`; borrow the CLI's temporary session
            # in memory rather than writing static keys or credentials to disk.
            result = subprocess.run(['aws', 'configure', 'export-credentials', '--profile', PROFILE, '--format', 'process'],
                                    capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise RuntimeError('AWS CLI session is unavailable.')
            credential = json.loads(result.stdout)
            _SESSION = boto3.Session(aws_access_key_id=credential['AccessKeyId'], aws_secret_access_key=credential['SecretAccessKey'],
                                     aws_session_token=credential['SessionToken'], region_name=REGION)
        client = _SESSION.client(service, verify='/etc/ssl/cert.pem' if sys.platform == 'darwin' else True)
        return getattr(client, operation.replace('-', '_'))(**payload)
    except Exception as error:
        # SDK errors can quote submitted values. Emit only the error class.
        raise RuntimeError('AWS ' + service + '/' + operation + ' failed (' + type(error).__name__ + '); no credential values were logged.') from None


def load_secret():
    if aws('sts', 'get-caller-identity', {})['Account'] != ACCOUNT:
        raise RuntimeError('AWS account differs from JumpServe.')
    record = aws('secretsmanager', 'get-secret-value', {'SecretId': SECRET})
    if not record['ARN'].startswith('arn:aws:secretsmanager:' + REGION + ':' + ACCOUNT + ':secret:' + SECRET + '-'):
        raise RuntimeError('Secret destination differs.')
    value = json.loads(record['SecretString'])
    if any(value.get(k) != v for k, v in {'team_id': TEAM, 'channel_id': CHANNEL, 'app_id': APP}.items()):
        raise RuntimeError('Stored Slack workspace, channel or app differs.')
    if not re.fullmatch(r'xoxb-[A-Za-z0-9-]+', value.get('bot_token', '')):
        raise RuntimeError('The installed bot credential is missing.')
    return record, value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Slack credential redirects are disabled.')


def slack(method, token, **payload):
    if method not in {'auth.test', 'apps.connections.open', 'conversations.info', 'users.info'}:
        raise ValueError('Slack method is outside this utility.')
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform == 'darwin' else None)
    context.keylog_filename = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(
        'https://slack.com/api/' + method, method='POST',
        data=urllib.parse.urlencode(payload).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with opener.open(request, timeout=25) as response:
            raw = response.read(1000001)
            if len(raw) > 1000000:
                raise RuntimeError('Slack response exceeds its bound.')
            value = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise RuntimeError('Slack returned HTTP ' + str(error.code) + '.') from None
    if not value.get('ok'):
        code = value.get('error', 'unknown_error')
        code = code if isinstance(code, str) and re.fullmatch('[a-z_]{1,60}', code) else 'unknown_error'
        raise RuntimeError('Slack ' + method + ': ' + code)
    return value


def app_connection(token):
    if not isinstance(token, str) or not re.fullmatch(r'xapp-\d+-' + APP + r'-[A-Za-z0-9-]+', token):
        raise RuntimeError('App credential does not identify the prepared Slack app.')
    result = slack('apps.connections.open', token)
    url = urllib.parse.urlsplit(result.get('url', ''))
    if url.scheme != 'wss' or url.hostname not in {'wss-primary.slack.com', 'wss-backup.slack.com'}:
        raise RuntimeError('Slack did not return an expected Socket Mode endpoint.')
    # The short-lived websocket URL is a credential too; never return or log it.
    return True


def store_token(token):
    record, current = load_secret()
    app_connection(token)
    if current.get('app_token') == token and 'pending' not in current:
        return {'stored': True, 'changed': False, 'secret_version': record['VersionId']}
    updated = dict(current, app_token=token)
    updated.pop('pending', None)
    request_id = str(uuid.uuid4())
    try:
        aws('secretsmanager', 'put-secret-value', {
            'SecretId': SECRET, 'ClientRequestToken': request_id,
            'SecretString': json.dumps(updated, separators=(',', ':')),
        })
    except Exception:
        # Reconcile the original write through readback, not a second mutation.
        actual_record, actual = load_secret()
        if actual != updated:
            raise RuntimeError('Secret write is unconfirmed; no replacement write was sent.') from None
        return {'stored': True, 'changed': True, 'secret_version': actual_record['VersionId'], 'reconciled': True}
    actual_record, actual = load_secret()
    if actual != updated:
        raise RuntimeError('Secret readback differs; connection remains inactive.')
    return {'stored': True, 'changed': True, 'secret_version': actual_record['VersionId']}


def verify():
    record, value = load_secret()
    identity = slack('auth.test', value['bot_token'])
    if identity.get('team_id') != TEAM or not identity.get('bot_id'):
        raise RuntimeError('Bot identity differs from the installed workspace app.')
    profile = slack('users.info', value['bot_token'], user=identity['user_id'])['user']
    if profile.get('profile', {}).get('api_app_id') != APP:
        raise RuntimeError('Bot profile does not identify the prepared Slack app.')
    app_connection(value.get('app_token'))
    member = False
    try:
        channel = slack('conversations.info', value['bot_token'], channel=CHANNEL)['channel']
        if channel.get('id') != CHANNEL or not channel.get('is_private'):
            raise RuntimeError('Shared channel identity or visibility differs.')
        member = channel.get('is_member') is True
    except RuntimeError as error:
        if str(error) != 'Slack conversations.info: channel_not_found':
            raise
    return {
        'version': 'jumpserve-slack-credentials-v1',
        'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'account': ACCOUNT, 'team_id': TEAM, 'app_id': APP, 'channel_id': CHANNEL,
        'bot_user_id': identity['user_id'], 'bot_id': identity['bot_id'],
        'bot_token_valid': True, 'socket_mode_token_valid': True,
        'channel_member': member, 'secret_version': record['VersionId'],
        'gateway_started_by_this_check': False,
    }


def prepare():
    """Validate only: isolated local state and synthetic credentials, no listener."""
    root = ROOT / '.test-artifacts/slack-setup-v1'
    qualification = root / 'qualification'
    qualification.mkdir(mode=0o700, parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('slack_gateway', ROOT / 'assets/platform/slack_gateway.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    policy = json.loads((ROOT / 'assets/platform/slack-channel-policy.json').read_bytes())
    config = module.configuration(qualification, 'http://127.0.0.1:18801', 'synthetic-offline-bridge-token', policy)
    install_state = root/'install-qualification/state'
    installed = list((install_state/'npm/projects').glob('*/node_modules/@openclaw/slack/package.json'))
    if len(installed) != 1:
        raise RuntimeError('Qualify the isolated, official pinned Slack plugin installation first.')
    config['plugins']['load']['paths'].append(str(installed[0].parent))
    path = qualification / 'openclaw.json'
    module.save(path, module.canonical(config))
    node = root / 'node/bin/node'
    cli = root / 'vendor/node_modules/openclaw/openclaw.mjs'
    env = dict(PATH=os.environ.get('PATH','/usr/bin:/bin'), LANG='C.UTF-8',
               OPENCLAW_CONFIG_PATH=str(path), OPENCLAW_STATE_DIR=str(install_state),
               OPENCLAW_SKIP_CHANNELS='1', OPENCLAW_DISABLE_DISCOVERY='1',
               SLACK_BOT_TOKEN='xoxb-synthetic-offline', SLACK_APP_TOKEN='xapp-synthetic-offline')
    module.write_configuration(config,path,node,cli,env)
    results = []
    for args in (['config', 'validate', '--json'], ['plugins', 'inspect', 'jumpserve-supervisor', '--runtime', '--json'],
                 ['plugins','inspect','slack','--runtime','--json']):
        result = subprocess.run([str(node), str(cli), *args], env=env, capture_output=True, text=True, timeout=120,
                                cwd=qualification)
        results.append(dict(command=args, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            module.save(qualification/'native-validation.json', module.canonical(dict(passed=False,results=results)))
            raise RuntimeError('Pinned OpenClaw offline validation failed; see the local synthetic-credential report.')
        observed=json.loads(result.stdout)
        if args[0]=='config':
            if observed.get('valid') is not True: raise RuntimeError('Native configuration was not validated.')
        elif observed['plugin'].get('status')!='loaded': raise RuntimeError('Native plugin did not load.')
        elif args[2]=='jumpserve-supervisor' and set(observed['plugin']['toolNames'])!=set(module.TOOLS):
            raise RuntimeError('Native supervisor tool inventory differs.')
        elif args[2]=='slack' and (observed['plugin'].get('trustedOfficialInstall') is not True
            or observed.get('install',{}).get('integrity')!='sha512-AzWaSLfUQZWPwDdrLXzXeQ/AraXPEnkTTWKTKq4MFO39futFAxy+FulsYSStDYEd1B0YjtWGvXswBjdrmwRlBw=='):
            raise RuntimeError('Official Slack installation provenance differs.')
    module.save(qualification/'native-validation.json', module.canonical(dict(passed=True,results=results)))
    for command in ([sys.executable,'-B','-m','unittest','discover','-s','test','-p','platform_slack_test.py','-v'],
                    [str(node),'--test','assets/platform/slack-tools/index.test.js']):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=90)
        results.append(dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if result.returncode: raise RuntimeError('Slack regression checks failed.')
    migration=ROOT/'database/202611040001_platform_slack_gateway.sql'
    database_reports=sorted((ROOT/'.test-artifacts/research-ideas/database').glob('*/platform-slack-report.json'))
    if not database_reports: raise RuntimeError('Passed local Slack database checks are required.')
    database=json.loads(database_reports[-1].read_bytes())
    if database.get('passed') is not True or database['migration_sha256'].get(migration.name)!=module.digest(migration.read_bytes()):
        raise RuntimeError('Local database qualification does not match this migration.')
    names=['slack_gateway.py','slack_api.py','slack-channel-policy.json','jumpserve-platform-slack.service',
           'install-slack-gateway.py','slack-tools/index.js','slack-tools/openclaw.plugin.json','slack-tools/package.json']
    files={name:(ROOT/'assets/platform'/name).read_bytes() for name in names}
    proof=dict(passed=True,version='platform-slack-qualification-v1',openclaw_version='2026.10.5',node_version='24.16.0',
               files={name:module.digest(raw) for name,raw in files.items()},migration_sha256=module.digest(migration.read_bytes()),
               database_report=str(database_reports[-1]),results=results,provider_calls=0,live_conversation_verified=False)
    files['qualification.json']=module.canonical(proof)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;archive.writestr(info,raw)
    bundle=buffer.getvalue(); bundle_sha=module.digest(bundle)
    module.save(qualification/'platform-slack.zip',bundle)
    packet=dict(version='platform-slack-release-v1',bundle_sha256=bundle_sha,migration=migration.name,
                migration_sha256=proof['migration_sha256'],target_account=ACCOUNT,target_region=REGION,
                target_instance='i-087f1493809643115',secret_id=SECRET,team_id=TEAM,channel_id=CHANNEL,app_id=APP,
                qualified=True,activated=False,live_conversation_verified=False)
    owner_file=root/'owner-binding-preflight.json'
    if owner_file.exists():
        binding=json.loads(owner_file.read_bytes())
        if binding.get('owner_available') is not True: raise RuntimeError('An existing Google platform owner is required for Slack task delegation.')
        packet['delegated_by']=str(uuid.UUID(binding['delegated_by']))
    host_file=root/'host-preflight-result.json'
    if host_file.exists():packet['host_preflight']=json.loads(host_file.read_bytes())
    module.save(qualification/'release-packet.json',module.canonical(packet))
    return dict(passed=True, native_version='2026.10.5', node_version='24.16.0',
                report=str(qualification/'native-validation.json'),bundle_sha256=bundle_sha,
                packet=str(qualification/'release-packet.json'),gateway_started=False,provider_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['store-app-token', 'verify', 'prepare'])
    args = parser.parse_args()
    if args.action == 'store-app-token':
        if not sys.stdin.isatty():
            raise RuntimeError('Use a terminal with hidden credential input.')
        result = store_token(getpass.getpass('Slack app token (hidden): ').strip())
    elif args.action == 'verify':
        result = verify()
    else:
        result = prepare()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        # Only our fixed error text is emitted, never provider response bodies.
        print(str(error) if isinstance(error, RuntimeError) else 'Slack setup failed; credential values were not logged.', file=sys.stderr)
        sys.exit(1)
