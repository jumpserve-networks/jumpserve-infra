"""Fixed 2026-11-05 assessment HTTP API release; retain all worker configuration."""
import argparse
import base64
import copy
import hashlib
import io
import json
import subprocess
from pathlib import Path
import urllib.request
import zipfile
import boto3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.test-artifacts/assessment-ui-release-20261105'
STACK = 'JumpServeBenchmarkStack'
API = 'ResearchWorkflowApiE04EBDAC'
BUCKET = 'cdk-hnb659fds-assets-395567831870-us-east-1'
CHANGE = 'assessment-ui-20261105-api-v1'
ROUTES = {'GET /research/prompts', 'GET /research/prompts/{versionId}', 'GET /research/papers/{studyId}'}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def session():
    # The AWS CLI supports the browser-login credential provider used by this
    # profile; export only into this process for older installed botocore builds.
    credentials = json.loads(subprocess.check_output(['aws','configure','export-credentials','--profile','jumpserve','--format','process'], timeout=30))
    value = boto3.Session(aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'], region_name='us-east-1')
    if value.client('sts').get_caller_identity()['Account'] != '395567831870': raise ValueError('Wrong AWS account.')
    return value

def template(value):
    return json.loads(value) if isinstance(value, str) else value

def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'change.json').exists(): raise ValueError('Reconcile the recorded change set instead of preparing it again.')
    s = session(); cfn = s.client('cloudformation')
    info = cfn.describe_stacks(StackName=STACK)['Stacks'][0]
    if info['StackStatus'] != 'UPDATE_COMPLETE': raise ValueError('Production stack is not settled.')
    old = template(cfn.get_template(StackName=STACK)['TemplateBody'])
    if any(p['Type'].startswith('AWS::SSM::') for p in old.get('Parameters', {}).values()): raise ValueError('Resolve mutable SSM parameters before preparing a release.')
    generated = json.loads((ROOT/'.test-artifacts/assessment-ui-generated-template.json').read_bytes())
    manifest = json.loads((ROOT/'research-api-runtime.json').read_bytes())
    if manifest['source_revision'] != '5a301cdaebbbcc72f6efb27e99943bff6d058232': raise ValueError('Unexpected qualified API revision.')
    candidate = copy.deepcopy(old)
    selected = {}
    for name, resource in generated['Resources'].items():
        if resource['Type'] == 'AWS::ApiGatewayV2::Route' and resource['Properties']['RouteKey'] in ROUTES:
            selected[name] = resource
        if resource['Type'] == 'AWS::Lambda::Permission' and any('/*/*/'+route.removeprefix('GET /') in resource['Properties'].get('SourceArn', {}).get('Fn::Join', ['', []])[1] for route in ROUTES):
            selected[name] = resource
    if len(selected) != 6: raise ValueError('Expected three routes and three exact invocation permissions.')
    for name, resource in selected.items():
        if name in old['Resources'] and old['Resources'][name] != resource: raise ValueError('Existing route differs; reconcile production.')
        candidate['Resources'][name] = resource
    api = candidate['Resources'][API]
    api['Properties']['Code'] = generated['Resources'][API]['Properties']['Code']
    key = api['Properties']['Code']['S3Key']
    if len(key) != 68 or not key.endswith('.zip') or any(c not in '0123456789abcdef' for c in key[:-4]): raise ValueError('Expected content-addressed API asset.')
    api.setdefault('Metadata', {})['aws:asset:path'] = 'asset.'+key[:-4]
    assert {n for n in old['Resources'] if old['Resources'][n] != candidate['Resources'][n]} == {API}
    assert set(candidate['Resources']) - set(old['Resources']) == set(selected)
    for key in set(old)-{'Resources'}: assert candidate[key] == old[key]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name, expected in manifest['files'].items():
            raw = (ROOT/'.runtime-api/research_workflow'/name).read_bytes()
            if sha(raw) != expected: raise ValueError('API source differs: '+name)
            member = zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0)); member.compress_type=zipfile.ZIP_DEFLATED; member.external_attr=0o644<<16
            zipped.writestr(member, raw)
    raw = archive.getvalue(); code = api['Properties']['Code']
    if code['S3Bucket'] != BUCKET: raise ValueError('Wrong asset bucket.')
    (OUT/'previous-template.json').write_bytes(encoded(old)); (OUT/'template.json').write_bytes(encoded(candidate)); (OUT/'api.zip').write_bytes(raw)
    receipt = dict(change_set=CHANGE, source_revision=manifest['source_revision'], files=manifest['files'], zip_sha256=sha(raw), added_resources=sorted(selected), updated_resources=[API], code=code, prepared=True)
    (OUT/'change.json').write_bytes(encoded(receipt))
    s3 = s.client('s3')
    s3.put_object(Bucket=BUCKET, Key=code['S3Key'], Body=raw, IfNoneMatch='*', ServerSideEncryption='AES256')
    body = encoded(candidate); key = sha(body)+'.json'
    s3.put_object(Bucket=BUCKET, Key=key, Body=body, ServerSideEncryption='AES256')
    result = cfn.create_change_set(StackName=STACK, ChangeSetName=CHANGE, ChangeSetType='UPDATE', TemplateURL=f'https://{BUCKET}.s3.us-east-1.amazonaws.com/{key}', Capabilities=['CAPABILITY_NAMED_IAM'], Parameters=[dict(ParameterKey=p['ParameterKey'], UsePreviousValue=True) for p in info.get('Parameters', [])], Description='Qualified assessment metadata, author review and authenticated prompt HTTP API; workers preserved.')
    receipt['change_set_id'] = result['Id']; (OUT/'change.json').write_bytes(encoded(receipt))
    print(json.dumps(dict(change_set=CHANGE, added_resources=len(selected), updated_resources=[API], source_revision=manifest['source_revision'])))

def check():
    s = session(); cfn = s.client('cloudformation'); receipt = json.loads((OUT/'change.json').read_bytes())
    expected = json.loads((OUT/'template.json').read_bytes())
    actual = template(cfn.get_template(StackName=STACK)['TemplateBody'])
    if actual != expected: raise ValueError('Deployed stack differs from the reviewed release.')
    physical = cfn.describe_stack_resource(StackName=STACK, LogicalResourceId=API)['StackResourceDetail']['PhysicalResourceId']
    function = s.client('lambda').get_function(FunctionName=physical)
    with urllib.request.urlopen(function['Code']['Location'], timeout=30) as response: raw = response.read(12000001)
    if sha(raw) != receipt['zip_sha256'] or base64.b64encode(bytes.fromhex(sha(raw))).decode() != function['Configuration']['CodeSha256']: raise ValueError('Installed API archive differs.')
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        if set(zipped.namelist()) != set(receipt['files']) or any(sha(zipped.read(n)) != h for n,h in receipt['files'].items()): raise ValueError('Installed API source differs.')
    receipt.update(deployed=True, installed_source_verified=True, function=physical)
    (OUT/'verification.json').write_bytes(encoded(receipt)); print(json.dumps(dict(deployed=True, files=len(receipt['files']), source_verified=True)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=['prepare','check']); args=parser.parse_args()
    prepare() if args.mode == 'prepare' else check()
