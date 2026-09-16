#!/usr/bin/env python3
"""Recover temporary resources recorded by this AMI workflow, including cancellation."""
import argparse
import json
import os
import pathlib
import re

from build import ACCOUNT, aws


def cleanup(args):
    if aws(args, 'sts', 'get-caller-identity')['Account'] != ACCOUNT:
        raise ValueError('Refusing cleanup in a different AWS account')
    errors = []

    def attempt(service, operation, *options):
        try:
            return aws(args, service, operation, *options)
        except RuntimeError as error:
            # A completed build already removed these resources.
            if 'NoSuchEntity' not in str(error) and 'InvalidInstanceID.NotFound' not in str(error):
                errors.append(str(error))
            return {}

    state_path = pathlib.Path(args.directory) / 'benchmark-ami-build-state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        role = state['role_name']
        if (state['account_id'] != ACCOUNT or state['region'] != args.region
                or not re.fullmatch(r'JumpServeAmiBuilder-\d{8}T\d{6}Z', role)):
            raise ValueError('Invalid builder cleanup checkpoint')
        result = aws(args, 'ec2', 'describe-instances', '--filters', json.dumps([
            {'Name': 'tag:Project', 'Values': ['JumpServe']},
            {'Name': 'tag:Purpose', 'Values': ['BenchmarkAMI']},
            {'Name': 'tag:BuildId', 'Values': [role]},
            {'Name': 'tag:BackendCommit', 'Values': [state['backend_commit']]},
        ]))
        for reservation in result['Reservations']:
            for instance in reservation['Instances']:
                if instance['State']['Name'] not in ('terminated', 'shutting-down'):
                    attempt('ec2', 'terminate-instances', '--instance-ids', instance['InstanceId'])
        attempt('iam', 'remove-role-from-instance-profile', '--instance-profile-name', role, '--role-name', role)
        attempt('iam', 'delete-instance-profile', '--instance-profile-name', role)
        attempt('iam', 'detach-role-policy', '--role-name', role,
                '--policy-arn', 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        attempt('iam', 'delete-role', '--role-name', role)

    jobs_path = pathlib.Path(args.directory) / 'benchmark-ami-verification-instances.json'
    if jobs_path.exists():
        for job in json.loads(jobs_path.read_text()):
            result = attempt('ec2', 'describe-instances', '--instance-ids', job['instanceId'])
            for reservation in result.get('Reservations', []):
                for instance in reservation['Instances']:
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    if (tags.get('Project') != 'JumpServe' or tags.get('BenchmarkJobId') != job['jobId']
                            or instance['ImageId'] != job['amiId']):
                        raise ValueError('Verification cleanup ownership check failed')
                    if instance['State']['Name'] not in ('terminated', 'shutting-down'):
                        attempt('ec2', 'terminate-instances', '--instance-ids', instance['InstanceId'])
    if errors:
        raise RuntimeError('\n'.join(errors))
    print('Temporary builder resources and verification instances cleaned up')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default=os.environ.get('AWS_PROFILE'))
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--directory', default='cdk.out')
    cleanup(parser.parse_args())
