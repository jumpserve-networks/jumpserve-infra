#!/usr/bin/env python3
"""Select a verified AMI through the existing stack; retain a guarded rollback checkpoint."""
import argparse
import json
import os
import pathlib
import subprocess

from build import ACCOUNT, aws, wait_until

STACK = 'JumpServeBenchmarkStack'
CHECKPOINT = pathlib.Path('cdk.out/benchmark-ami-promotion.json')


def stack_info(args):
    return aws(args, 'cloudformation', 'describe-stacks', '--stack-name', STACK)['Stacks'][0]


def current_image(stack):
    return next(p['ParameterValue'] for p in stack['Parameters'] if p['ParameterKey'] == 'BenchmarkAmiId')


def wait_for_stack(args):
    def settled():
        status = stack_info(args)['StackStatus']
        if status.endswith('_IN_PROGRESS'):
            return False
        if status not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE'):
            raise RuntimeError(f'Benchmark stack did not update successfully: {status}')
        return True
    wait_until(settled, 900, 'benchmark stack update')


def select_image(args, stack, image):
    if current_image(stack) == image:
        return
    parameters = [({'ParameterKey': p['ParameterKey'], 'ParameterValue': image}
                   if p['ParameterKey'] == 'BenchmarkAmiId'
                   else {'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True})
                  for p in stack['Parameters']]
    aws(args, 'cloudformation', 'update-stack', '--stack-name', STACK,
        '--use-previous-template', '--parameters', json.dumps(parameters),
        '--capabilities', 'CAPABILITY_NAMED_IAM')
    wait_for_stack(args)
    if current_image(stack_info(args)) != image:
        raise RuntimeError('The selected AMI does not match the requested AMI')


def validate_candidate(args, manifest, reports):
    if manifest['account_id'] != ACCOUNT or manifest['region'] != args.region:
        raise ValueError('Manifest account or region does not match')
    if (len(reports) != 2 or {r['status'] for r in reports} != {'completed', 'failed'}
            or any(r['amiId'] != manifest['ami_id'] or r['backendCommit'] != manifest['backend_commit']
                   for r in reports)):
        raise ValueError('Matching success and failure verification reports are required')
    image = aws(args, 'ec2', 'describe-images', '--image-ids', manifest['ami_id'])['Images'][0]
    tags = {t['Key']: t['Value'] for t in image.get('Tags', [])}
    if (image['OwnerId'] != ACCOUNT or image['State'] != 'available' or image.get('Public')
            or tags.get('Purpose') != 'BenchmarkAMI' or tags.get('BackendCommit') != manifest['backend_commit']):
        raise ValueError('Candidate image ownership, availability or commit does not match')
    latest = subprocess.run(['git', 'ls-remote', 'https://github.com/jumpserve-networks/jumpserve-back-end.git',
                             'refs/heads/main'], check=True, capture_output=True, text=True, timeout=60)
    if latest.stdout.split()[0] != manifest['backend_commit']:
        raise ValueError('Backend main advanced; refusing to promote an outdated commit')


def promote(args):
    if aws(args, 'sts', 'get-caller-identity')['Account'] != ACCOUNT:
        raise ValueError('Refusing promotion in a different AWS account')
    if args.rollback:
        if not CHECKPOINT.exists():
            print('No promotion checkpoint; nothing to roll back')
            return
        state = json.loads(CHECKPOINT.read_text())
        if state['account_id'] != ACCOUNT or state['region'] != args.region:
            raise ValueError('Invalid rollback checkpoint')
        # A cancelled CLI may have left an update in flight.
        wait_for_stack(args)
        stack = stack_info(args)
        if current_image(stack) != state['candidate_ami']:
            print('Candidate is no longer selected; leaving the current AMI unchanged')
            return
        print(f"Restoring {state['previous_ami']}")
        if args.apply:
            select_image(args, stack, state['previous_ami'])
        return

    manifest = json.loads(pathlib.Path('cdk.out/benchmark-ami.json').read_text())
    reports = json.loads(pathlib.Path('cdk.out/benchmark-ami-verification.json').read_text())
    validate_candidate(args, manifest, reports)
    wait_for_stack(args)
    stack = stack_info(args)
    state = {'account_id': ACCOUNT, 'region': args.region, 'previous_ami': current_image(stack),
             'candidate_ami': manifest['ami_id'], 'backend_commit': manifest['backend_commit']}
    print(json.dumps(state))
    if args.apply:
        CHECKPOINT.write_text(json.dumps(state, indent=2) + '\n')
        select_image(args, stack, manifest['ami_id'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default=os.environ.get('AWS_PROFILE'))
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    promote(parser.parse_args())
