"""Install the pinned intake access publisher through the existing GitHub OIDC role."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import time
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
BUCKET = 'cdk-hnb659fds-assets-395567831870-us-east-1'
OWNER = 'i-087f1493809643115'
OUT = ROOT / '.test-artifacts/intake-publisher-release'
encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def request_for(release_id, runtime_object, publisher_object):
    if str(uuid.UUID(release_id)) != release_id:
        raise ValueError('Original release UUID required.')
    pin = json.loads((ROOT / 'intake-worker-runtime.json').read_bytes())
    outputs = {'JumpServeIntakeStack': dict(IntakeSourceBinding=pin['source_binding'],
        IntakeRuntimeBucket=BUCKET, IntakePublisherBucket=BUCKET,
        IntakeRuntimeObject=runtime_object, IntakePublisherObject=publisher_object)}
    request = runpy.run_path(str(ROOT / 'bin/prepare-intake-publisher.py'))['build'](outputs)
    request['Comment'] = 'Warm intake publisher ' + release_id
    return request


def existing_command(ssm, request):
    token = None
    for _ in range(20):
        options = dict(InstanceId=OWNER, MaxResults=50, Filters=[dict(key='InvokedAfter', value=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=1)).isoformat())])
        if token:
            options['NextToken'] = token
        result = ssm.list_commands(**options)
        matches = [item for item in result['Commands'] if item.get('Comment') == request['Comment']]
        if matches:
            if len(matches) != 1 or matches[0]['Parameters'] != request['Parameters'] or matches[0]['DocumentName'] != request['DocumentName'] or matches[0]['InstanceIds'] != request['InstanceIds']:
                raise ValueError('Original publisher command identity differs.')
            return matches[0]['CommandId']
        token = result.get('NextToken')
        if not token:
            return None
    raise ValueError('Original command lookup exceeds its bound; no new command sent.')


def dispatch_once(s3, ssm, release_id, request):
    key = 'intake-publisher-release/' + release_id + '/intent.json'
    intent = dict(version='warm-intake-publisher-v1', request=request,
        request_sha256=hashlib.sha256(encode(request)).hexdigest())
    created = False
    try:
        s3.put_object(Bucket=BUCKET, Key=key, Body=encode(intent), IfNoneMatch='*', ServerSideEncryption='AES256')
        created = True
    except ClientError as error:
        if error.response['Error']['Code'] not in ('PreconditionFailed', '412'):
            raise
        retained = json.loads(s3.get_object(Bucket=BUCKET, Key=key)['Body'].read())
        if retained != intent:
            raise ValueError('Retained release intent differs.') from None
    command = existing_command(ssm, request)
    if command:
        return command
    if not created:
        raise ValueError('Original publisher outcome remains unconfirmed; no replay permitted.')
    # Client retries are disabled. The durable intent prevents replays after a
    # lost send acknowledgement; the original command is reconciled by UUID.
    return ssm.send_command(**request)['Command']['CommandId']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--runtime-object', required=True)
    parser.add_argument('--publisher-object', required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}', args.revision) or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != args.revision:
        raise ValueError('Exact protected source revision required.')
    request = request_for(args.release_id, args.runtime_object, args.publisher_object)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'request.json').write_bytes(encode(request))
    if args.prepare_only:
        print(json.dumps(dict(prepared=True, request_sha256=hashlib.sha256(encode(request)).hexdigest(), cloud_calls=0)))
        return
    session = boto3.Session(region_name='us-east-1')
    config = Config(retries={'total_max_attempts': 1}, connect_timeout=10, read_timeout=30)
    identity = session.client('sts', config=config).get_caller_identity()
    if identity['Account'] != '395567831870' or not identity['Arn'].startswith('arn:aws:sts::395567831870:assumed-role/JumpServePlatformRelease/'):
        raise ValueError('Qualified GitHub release role required.')
    s3 = session.client('s3', config=config); ssm = session.client('ssm', config=config)
    command = dispatch_once(s3, ssm, args.release_id, request)
    receipt = dict(release_id=args.release_id, command_id=command, instance_id=OWNER, revision=args.revision)
    (OUT / 'receipt.json').write_bytes(encode(receipt))
    print(json.dumps(receipt), flush=True)
    deadline = time.monotonic() + 650
    while time.monotonic() < deadline:
        try:
            result = ssm.get_command_invocation(CommandId=command, InstanceId=OWNER)
        except ClientError as error:
            if error.response['Error']['Code'] != 'InvocationDoesNotExist':
                raise
            time.sleep(5); continue
        if result['Status'] in ('Pending', 'InProgress', 'Delayed'):
            time.sleep(5); continue
        receipt.update(status=result['Status'], response_code=result['ResponseCode'],
            publisher_active=result['StandardOutputContent'].strip().splitlines()[-1:] == ['active'],
            checked_at=dt.datetime.now(dt.timezone.utc).isoformat())
        (OUT / 'receipt.json').write_bytes(encode(receipt))
        s3.put_object(Bucket=BUCKET, Key='intake-publisher-release/' + args.release_id + '/receipt.json', Body=encode(receipt), ServerSideEncryption='AES256')
        if result['Status'] != 'Success' or result['ResponseCode'] != 0 or not receipt['publisher_active']:
            raise ValueError('Retained publisher command failed; reconcile its original ID before retrying.')
        print(json.dumps(receipt)); return
    raise TimeoutError('Original publisher command remains pending; its ID is retained.')


if __name__ == '__main__':
    main()
