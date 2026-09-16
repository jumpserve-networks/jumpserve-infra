#!/usr/bin/env python3
"""Build a private benchmark AMI; never changes the live benchmark launcher."""
import argparse
import base64
import datetime
import json
import os
import pathlib
import re
import subprocess
import time

ACCOUNT = '395567831870'


def aws(args, service, operation, *options):
    try:
        result = subprocess.run([
            'aws', *(['--profile', args.profile] if args.profile else []), '--region', args.region,
            '--no-cli-pager', '--output', 'json', service, operation, *options,
        ], check=True, capture_output=True, text=True, timeout=90)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'AWS {service} {operation}: {error.stderr.strip()}') from None
    return json.loads(result.stdout) if result.stdout.strip() else {}


def wait_until(check, timeout_seconds, description, interval=15):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(interval)
    raise TimeoutError(f'Timed out waiting for {description}')


def build(args):
    identity = aws(args, 'sts', 'get-caller-identity')
    if identity['Account'] != ACCOUNT:
        raise ValueError(f'Expected AWS account {ACCOUNT}; refusing to build elsewhere')
    base = aws(args, 'ec2', 'describe-images', '--image-ids', args.base_ami)['Images'][0]
    if (base['OwnerId'] != '099720109477' or base['Architecture'] != 'x86_64'
            or base['State'] != 'available' or 'ubuntu-jammy-22.04' not in base['Name']):
        raise ValueError('The base must be an available Canonical Ubuntu 22.04 x86_64 AMI')
    if not re.fullmatch(r'[0-9a-f]{40}', args.backend_commit):
        raise ValueError('Pin --backend-commit to a full, lowercase Git commit SHA')

    provision = pathlib.Path(__file__).with_name('provision.sh').read_text()
    provision = provision.replace('__BACKEND_COMMIT__', args.backend_commit)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    role_name = f'JumpServeAmiBuilder-{stamp}'
    name = f'jumpserve-benchmark-{stamp}-{args.backend_commit[:12]}'
    tags = [
        {'Key': 'Project', 'Value': 'JumpServe'},
        {'Key': 'Purpose', 'Value': 'BenchmarkAMI'},
        {'Key': 'BackendCommit', 'Value': args.backend_commit},
        {'Key': 'Name', 'Value': name},
        {'Key': 'BuildId', 'Value': role_name},
    ]
    request = {
        'ImageId': args.base_ami,
        'ClientToken': role_name,
        'InstanceType': 't3.medium',
        'MinCount': 1, 'MaxCount': 1,
        'InstanceInitiatedShutdownBehavior': 'stop',
        'MetadataOptions': {'HttpTokens': 'required', 'HttpEndpoint': 'enabled'},
        'NetworkInterfaces': [{
            'DeviceIndex': 0, 'SubnetId': args.subnet_id,
            'Groups': [args.security_group_id], 'AssociatePublicIpAddress': True,
        }],
        'BlockDeviceMappings': [{
            'DeviceName': base['RootDeviceName'],
            'Ebs': {'VolumeSize': 8, 'VolumeType': 'gp3', 'DeleteOnTermination': True, 'Encrypted': True},
        }],
        # A temporary SSM-only profile is added after read-only preview.
        'UserData': base64.b64encode(provision.encode()).decode(),
        'TagSpecifications': [
            {'ResourceType': resource, 'Tags': tags} for resource in ('instance', 'volume')
        ],
    }
    print(json.dumps({'account': ACCOUNT, 'region': args.region, 'base_ami': args.base_ami,
                      'name': name, 'backend_commit': args.backend_commit,
                      'subnet': args.subnet_id, 'security_group': args.security_group_id,
                      'output': args.output, 'apply': args.apply}), flush=True)
    if not args.apply:
        return

    instance_id = None
    image_id = None
    # Persist before the first mutation so an always-run CI cleanup can recover
    # even if the process is cancelled between an AWS response and local writes.
    state = pathlib.Path(args.output).with_name('benchmark-ami-build-state.json')
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({'account_id': ACCOUNT, 'region': args.region,
                                'role_name': role_name, 'backend_commit': args.backend_commit}) + '\n')
    role_created = False
    profile_created = False
    policy_attached = False
    profile_attached = False
    try:
        aws(args, 'iam', 'create-role', '--role-name', role_name,
            '--assume-role-policy-document', json.dumps({
                'Version': '2012-10-17', 'Statement': [{
                    'Effect': 'Allow', 'Principal': {'Service': 'ec2.amazonaws.com'},
                    'Action': 'sts:AssumeRole',
                }],
            }))
        role_created = True
        aws(args, 'iam', 'attach-role-policy', '--role-name', role_name,
            '--policy-arn', 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        policy_attached = True
        aws(args, 'iam', 'create-instance-profile', '--instance-profile-name', role_name)
        profile_created = True
        aws(args, 'iam', 'add-role-to-instance-profile', '--instance-profile-name', role_name,
            '--role-name', role_name)
        profile_attached = True
        # IAM profile changes are eventually consistent with EC2.
        time.sleep(20)
        request['IamInstanceProfile'] = {'Name': role_name}
        result = aws(args, 'ec2', 'run-instances', '--cli-input-json', json.dumps(request))
        instance_id = result['Instances'][0]['InstanceId']
        print(f'Builder {instance_id}: provisioning; waiting for Systems Manager', flush=True)

        def managed():
            info = aws(args, 'ssm', 'describe-instance-information', '--filters',
                       json.dumps([{'Key': 'InstanceIds', 'Values': [instance_id]}]))
            return any(item['PingStatus'] == 'Online' for item in info['InstanceInformationList'])

        wait_until(managed, 600, 'builder SSM connection')
        command = aws(args, 'ssm', 'send-command', '--instance-ids', instance_id,
                      '--document-name', 'AWS-RunShellScript', '--parameters', json.dumps({
                          'executionTimeout': ['1200'],
                          'commands': [
                              'set -eu',
                              'cloud-init status --wait',
                              'test -f /etc/jumpserve-image.json',
                              # The command acknowledgement reaches SSM before the
                              # sealer stops its agent and removes cached identity.
                              'systemd-run --unit=jumpserve-seal-image-trigger --on-active=20s '
                              '/usr/bin/systemctl start jumpserve-seal-image.service',
                          ],
                      }))
        command_id = command['Command']['CommandId']

        def verified():
            result = aws(args, 'ssm', 'list-command-invocations', '--command-id', command_id, '--details')
            invocations = result['CommandInvocations']
            if not invocations:
                return False
            status = invocations[0]['Status']
            if status in ('Failed', 'Cancelled', 'TimedOut'):
                raise RuntimeError(f'Builder provisioning failed (SSM command {command_id})')
            return status == 'Success'

        wait_until(verified, 1500, 'successful provisioning verification')
        print(f'Builder {instance_id}: provisioning verified; sealing and stopping', flush=True)

        def stopped():
            info = aws(args, 'ec2', 'describe-instances', '--instance-ids', instance_id)
            state = info['Reservations'][0]['Instances'][0]['State']['Name']
            if state in ('terminated', 'shutting-down'):
                raise RuntimeError(f'Builder unexpectedly {state}')
            return state == 'stopped'

        # The sealer powers off only on success; an error leaves the builder
        # running and this bounded wait fails instead of registering an image.
        wait_until(stopped, 300, 'builder to seal and stop')
        created = aws(args, 'ec2', 'create-image', '--instance-id', instance_id,
                      '--name', name, '--description', 'JumpServe benchmark dependencies and pinned backend; no credentials',
                      '--tag-specifications', json.dumps([
                          {'ResourceType': resource, 'Tags': tags} for resource in ('image', 'snapshot')
                      ]))
        image_id = created['ImageId']
        print(f'Image {image_id}: waiting for snapshots to become available', flush=True)

        def available():
            info = aws(args, 'ec2', 'describe-images', '--image-ids', image_id)['Images'][0]
            if info['State'] == 'failed':
                raise RuntimeError(f'Image creation failed: {image_id}')
            return info['State'] == 'available'

        wait_until(available, 1800, 'AMI availability')
        manifest = {'ami_id': image_id, 'base_ami_id': args.base_ami,
                    'backend_commit': args.backend_commit, 'region': args.region,
                    'account_id': ACCOUNT, 'builder_instance_id': instance_id}
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(manifest), flush=True)
    finally:
        if instance_id:
            # Scope cleanup to the builder created by this invocation.
            aws(args, 'ec2', 'terminate-instances', '--instance-ids', instance_id)
            print(f'Termination requested for builder {instance_id}', flush=True)
        if profile_attached:
            aws(args, 'iam', 'remove-role-from-instance-profile', '--instance-profile-name', role_name,
                '--role-name', role_name)
        if profile_created:
            aws(args, 'iam', 'delete-instance-profile', '--instance-profile-name', role_name)
        if policy_attached:
            aws(args, 'iam', 'detach-role-policy', '--role-name', role_name,
                '--policy-arn', 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        if role_created:
            aws(args, 'iam', 'delete-role', '--role-name', role_name)
        if image_id:
            print(f'AMI retained: {image_id}; live launcher unchanged', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default=os.environ.get('AWS_PROFILE'))
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--base-ami', required=True)
    parser.add_argument('--subnet-id', required=True)
    parser.add_argument('--security-group-id', required=True)
    parser.add_argument('--backend-commit', required=True)
    parser.add_argument('--output', default='cdk.out/benchmark-ami.json')
    parser.add_argument('--apply', action='store_true', help='Create one builder and a private AMI (AWS charges apply)')
    build(parser.parse_args())


if __name__ == '__main__':
    main()
