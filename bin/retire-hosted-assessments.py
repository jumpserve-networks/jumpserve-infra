"""Fixed-target retirement of the hosted paper assessment control plane.

Never deletes Supabase data, benchmark launchers, frontend hosting, or chat.
Private receipts retain the exact AWS templates before any mutations.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-artifacts/hosted-assessment-retirement-20261120'
ACCOUNT = '395567831870'
STACKS = ('JumpServeFrontendPaperIntakeStack', 'JumpServeIntakeStack',
          'JumpServeOpenClawStack', 'JumpServePlatformAccessStack',
          'JumpServeBenchmarkStack', 'JumpServeObservabilityStack')

def aws(*args):
    raw = subprocess.check_output(['aws', *args, '--profile', 'default',
        '--region', 'us-east-1', '--output', 'json', '--no-cli-pager'], timeout=120)
    return json.loads(raw) if raw.strip() else {}

def save(name, value):
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = OUT / name
    with open(path, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o600)

def target():
    assert aws('sts', 'get-caller-identity')['Account'] == ACCOUNT, 'Wrong AWS account'

def inventory():
    if (OUT / 'aws-before.json').exists():
        raise ValueError('The original inventory is frozen; use status to reconcile later operations')
    result = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'stacks': {}}
    for name in STACKS:
        stack = aws('cloudformation', 'describe-stacks', '--stack-name', name)['Stacks'][0]
        resources = aws('cloudformation', 'list-stack-resources', '--stack-name', name)['StackResourceSummaries']
        template = aws('cloudformation', 'get-template', '--stack-name', name)['TemplateBody']
        rules = [aws('events', 'describe-rule', '--name', r['PhysicalResourceId'])
                 for r in resources if r['ResourceType'] == 'AWS::Events::Rule']
        result['stacks'][name] = {'stack': stack, 'resources': resources, 'template': template, 'rules': rules}
    result['instances'] = aws('ec2', 'describe-instances', '--filters',
        'Name=instance-state-name,Values=pending,running,stopping,stopped')
    result['executions'] = []
    for machine in aws('stepfunctions', 'list-state-machines')['stateMachines']:
        if 'JumpServe' in machine['name']:
            executions = aws('stepfunctions', 'list-executions', '--state-machine-arn',
                machine['stateMachineArn'], '--status-filter', 'RUNNING')['executions']
            result['executions'].extend(executions)
    save('aws-before.json', result)
    print(json.dumps({'report': str(OUT / 'aws-before.json'), 'stacks': {
        name: {'status': data['stack']['StackStatus'], 'resources': len(data['resources']),
            'rules': [{'name': rule['Name'], 'state': rule['State']} for rule in data['rules']],
            'functions': [{'id': r['LogicalResourceId'], 'name': r['PhysicalResourceId']}
                for r in data['resources'] if r['ResourceType'] == 'AWS::Lambda::Function']}
        for name, data in result['stacks'].items()}, 'instances': [
            {'id': i['InstanceId'], 'state': i['State']['Name'], 'type': i['InstanceType'],
             'tags': i.get('Tags', []), 'volumes': [b['Ebs']['VolumeId'] for b in i.get('BlockDeviceMappings', [])]}
            for r in result['instances']['Reservations'] for i in r['Instances']],
        'running_state_machines': result['executions']}))

def frozen_inventory():
    return json.loads((OUT / 'aws-before.json').read_text())

def freeze():
    before = frozen_inventory()
    receipts = []
    for name in ('JumpServeFrontendPaperIntakeStack', 'JumpServeBenchmarkStack'):
        data = before['stacks'][name]
        for resource in data['resources']:
            logical, physical = resource['LogicalResourceId'], resource.get('PhysicalResourceId')
            if resource['ResourceType'] == 'AWS::Events::Rule' and (
                    logical.startswith('PaperContinuation') or logical.startswith('ResearchWorkflow')):
                aws('events', 'disable-rule', '--name', physical)
                receipts.append({'disabled_rule': physical})
            if resource['ResourceType'] == 'AWS::Lambda::Function' and (
                    logical.startswith('PaperContinuation') or logical.startswith(('ResearchWorkflowAutonomyWorker',
                    'ResearchWorkflowQueueWorker', 'ResearchWorkflowPackageExecutor', 'ResearchWorkflowBoundedTcp'))):
                aws('lambda', 'put-function-concurrency', '--function-name', physical, '--reserved-concurrent-executions', '0')
                receipts.append({'stopped_function': physical})
            if logical == 'ResearchWorkflowApiE04EBDAC':
                configuration = aws('lambda', 'get-function-configuration', '--function-name', physical)
                save('research-api-before.json', configuration)
                environment = dict(configuration.get('Environment', {}).get('Variables', {}))
                for key in ('RESEARCH_AUTONOMY_ENABLED', 'RESEARCH_QUEUE_WORKERS_ENABLED', 'RESEARCH_BUILDER_ENABLED'):
                    environment[key] = 'false'
                aws('lambda', 'update-function-configuration', '--function-name', physical,
                    '--revision-id', configuration['RevisionId'], '--environment', json.dumps({'Variables': environment}))
                receipts.append({'disabled_research_admission': physical})
    for name in ('JumpServeOpenClawStack', 'JumpServeIntakeStack'):
        hosts = [r['PhysicalResourceId'] for r in before['stacks'][name]['resources'] if r['ResourceType'] == 'AWS::EC2::Instance']
        assert len(hosts) == 1
        host = hosts[0]
        instance = aws('ec2', 'describe-instances', '--instance-ids', host)['Reservations'][0]['Instances'][0]
        assert any(t['Key'] == 'aws:cloudformation:stack-name' and t['Value'] == name for t in instance.get('Tags', []))
        if instance['State']['Name'] in ('running', 'pending'):
            receipts.append({'stopped_host': host, 'response': aws('ec2', 'stop-instances', '--instance-ids', host)})
    save('aws-freeze.json', {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'receipts': receipts})
    print(json.dumps({'frozen': True, 'receipts': receipts}))

def snapshot():
    before = frozen_inventory()
    receipts = []
    for name in ('JumpServeOpenClawStack', 'JumpServeIntakeStack'):
        host = next(r['PhysicalResourceId'] for r in before['stacks'][name]['resources'] if r['ResourceType'] == 'AWS::EC2::Instance')
        instance = aws('ec2', 'describe-instances', '--instance-ids', host)['Reservations'][0]['Instances'][0]
        assert instance['State']['Name'] == 'stopped', 'Wait for graceful host shutdown before snapshots'
        for block in instance['BlockDeviceMappings']:
            volume = block['Ebs']['VolumeId']
            existing = aws('ec2', 'describe-snapshots', '--owner-ids', 'self', '--filters',
                'Name=tag:Retirement,Values=local-skill-v1', 'Name=volume-id,Values=' + volume)['Snapshots']
            if not existing:
                receipt = aws('ec2', 'create-snapshot', '--volume-id', volume,
                    '--description', 'JumpServe local skill migration: stopped ' + name + ' recovery evidence',
                    '--tag-specifications', json.dumps([{'ResourceType': 'snapshot', 'Tags': [
                        {'Key': 'Retirement', 'Value': 'local-skill-v1'}, {'Key': 'SourceStack', 'Value': name}]}]))
            else:
                receipt = existing[0]
            assert receipt['Encrypted'], 'Recovery evidence must remain encrypted'
            receipts.append({'host': host, 'volume': volume, 'snapshot': receipt['SnapshotId'], 'state': receipt['State']})
    save('recovery-snapshots.json', {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'snapshots': receipts})
    print(json.dumps({'snapshots': receipts}))

def references(value):
    found = set()
    if isinstance(value, list):
        for child in value: found.update(references(child))
    elif isinstance(value, dict):
        if isinstance(value.get('Ref'), str): found.add(value['Ref'])
        attribute = value.get('Fn::GetAtt')
        if isinstance(attribute, list): found.add(attribute[0])
        elif isinstance(attribute, str): found.add(attribute.split('.')[0])
        for child in value.values(): found.update(references(child))
    return found

def render(name, original):
    """Remove only retired resources; leave every other resource byte-equivalent."""
    template = copy.deepcopy(original)
    resources = template['Resources']
    if name == 'JumpServeFrontendPaperIntakeStack':
        removed = {key for key, value in resources.items() if key.startswith('PaperContinuation')}
    elif name == 'JumpServeBenchmarkStack':
        removed = {key for key, value in resources.items()
            if (key.startswith(('ResearchWorkflowAutonomy', 'ResearchWorkflowQueue',
                 'ResearchWorkflowBoundedTcp', 'ResearchWorkflowPackage')))
            or value['Type'] == 'AWS::ApiGatewayV2::Route'
                and value.get('Properties', {}).get('RouteKey', '').startswith('POST /research/')
            or value['Type'] == 'AWS::Lambda::Permission' and key.startswith('BenchmarkApiPOSTresearch')}
    else:
        raise ValueError('Unapproved stack')
    providers = {key for key in resources if key.startswith('CustomVpcRestrictDefaultSGCustomResourceProvider')}
    if providers and not any(references(value) & providers for key, value in resources.items() if key not in removed | providers):
        removed.update(providers)
    for key in removed:
        if resources[key]['Type'] == 'AWS::Logs::LogGroup':
            assert resources[key].get('DeletionPolicy') == 'Retain', 'Historical logs must be retained'
    # Remove permissions/integrations whose only target was retired.
    while True:
        extra = {key for key, value in resources.items() if key not in removed
            and value['Type'] in ('AWS::Lambda::Permission', 'AWS::ApiGatewayV2::Integration')
            and references(value) & removed}
        if not extra: break
        removed.update(extra)
    for key in removed: del resources[key]
    changed = []
    if name == 'JumpServeBenchmarkStack':
        api = resources['ResearchWorkflowApiE04EBDAC']
        environment = api['Properties']['Environment']['Variables']
        for key in list(environment):
            if key.startswith('NETWORK_') or key in ('RESEARCH_AI_RUNTIME', 'RESEARCH_AUTONOMY_WORKER_FUNCTION', 'RESEARCH_QUEUE_WORKER_FUNCTION'):
                del environment[key]
        for key in ('RESEARCH_AUTONOMY_ENABLED', 'RESEARCH_QUEUE_WORKERS_ENABLED', 'RESEARCH_BUILDER_ENABLED'):
            environment[key] = 'false'
        changed.append('ResearchWorkflowApiE04EBDAC')
        policy_id = 'ResearchWorkflowApiServiceRoleDefaultPolicy378FDA82'
        policy = resources[policy_id]['Properties']['PolicyDocument']
        policy['Statement'] = [s for s in policy['Statement'] if not references(s) & removed]
        changed.append(policy_id)
    # The CDK VPC cleanup provider shares a role across both VPCs. Remove only
    # the permission for the retired package VPC's default security group.
    for key, value in resources.items():
        if value['Type'] == 'AWS::IAM::Policy' and references(value) & removed:
            statements = value['Properties']['PolicyDocument']['Statement']
            value['Properties']['PolicyDocument']['Statement'] = [s for s in statements if not references(s) & removed]
            if key not in changed: changed.append(key)
        dependencies = value.get('DependsOn', [])
        if isinstance(dependencies, str): dependencies = [dependencies]
        if set(dependencies) & removed:
            value['DependsOn'] = [d for d in dependencies if d not in removed]
            if key not in changed: changed.append(key)
        if references(value) & removed:
            raise ValueError('Retained resource references removed resources: ' + key)
    for key, value in list(template.get('Outputs', {}).items()):
        if references(value) & removed: del template['Outputs'][key]
    assert not references(template) & removed
    return template, sorted(removed), sorted(changed)

def prepare():
    before = frozen_inventory()
    manifests = {}
    for name in ('JumpServeFrontendPaperIntakeStack', 'JumpServeBenchmarkStack'):
        original = before['stacks'][name]['template']
        template, removed, changed = render(name, original)
        actual = {p['ParameterKey']: p for p in before['stacks'][name]['stack'].get('Parameters', [])}
        pins = {}
        for key, definition in template.get('Parameters', {}).items():
            if definition['Type'].startswith('AWS::SSM::'):
                value = actual[key]['ResolvedValue']
                assert isinstance(value, str) and value
                definition.update(Type='String', Default=value)
                pins[key] = value
        save(name + '-retired.json', template)
        digest = hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest()
        manifests[name] = {'removed': removed, 'modified': changed, 'sha256': digest, 'parameter_pins': pins,
            'preserved_logs': [key for key, r in original['Resources'].items() if r['Type'] == 'AWS::Logs::LogGroup' and (key not in removed or r.get('DeletionPolicy') == 'Retain')]}
    save('change-plan.json', manifests)
    print(json.dumps(manifests))

def propose():
    before = frozen_inventory()
    manifests = json.loads((OUT / 'change-plan.json').read_text())
    results = {}
    existing = json.loads((OUT / 'change-sets.json').read_text()) if (OUT / 'change-sets.json').exists() else {}
    for name, manifest in manifests.items():
        template = json.loads((OUT / (name + '-retired.json')).read_text())
        assert hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest() == manifest['sha256']
        if name in existing and ('/local-skill-retirement-' + manifest['sha256'][:16] + '/') in existing[name]['Id']:
            results[name] = existing[name]
            continue
        key = 'retirement/local-skill-v1/' + manifest['sha256'] + '.json'
        aws('s3api', 'put-object', '--bucket', 'cdk-hnb659fds-assets-395567831870-us-east-1',
            '--key', key, '--body', str(OUT / (name + '-retired.json')), '--server-side-encryption', 'AES256')
        parameters = [{'ParameterKey': p['ParameterKey'], **({'ParameterValue': manifest['parameter_pins'][p['ParameterKey']]}
            if p['ParameterKey'] in manifest['parameter_pins'] else {'UsePreviousValue': True})}
            for p in before['stacks'][name]['stack'].get('Parameters', [])]
        # Existing deployment parameters are literal String pins, not dynamic AMI lookups.
        assert all(not p.get('Type', '').startswith('AWS::SSM::') for p in template.get('Parameters', {}).values())
        result = aws('cloudformation', 'create-change-set', '--stack-name', name,
            '--change-set-name', 'local-skill-retirement-' + manifest['sha256'][:16], '--change-set-type', 'UPDATE',
            '--client-token', 'local-skill-' + manifest['sha256'], '--description', 'Owner-directed hosted assessment retirement; evidence and result reads retained.',
            '--template-url', 'https://cdk-hnb659fds-assets-395567831870-us-east-1.s3.us-east-1.amazonaws.com/' + key,
            '--parameters', json.dumps(parameters), '--capabilities', 'CAPABILITY_NAMED_IAM',
            '--role-arn', 'arn:aws:iam::395567831870:role/cdk-hnb659fds-cfn-exec-role-395567831870-us-east-1')
        results[name] = result
        save('change-sets.json', results)
    print(json.dumps(results))

def execute():
    manifests = json.loads((OUT / 'change-plan.json').read_text())
    sets = json.loads((OUT / 'change-sets.json').read_text())
    results = {}
    for name, identity in sets.items():
        assert ('/local-skill-retirement-' + manifests[name]['sha256'][:16] + '/') in identity['Id']
        change = aws('cloudformation', 'describe-change-set', '--change-set-name', identity['Id'])
        save(name + '-reviewed-change-set.json', change)
        if change['ExecutionStatus'] in ('EXECUTE_IN_PROGRESS', 'EXECUTE_COMPLETE'):
            results[name] = {'already_submitted': True, 'status': change['ExecutionStatus']}
            continue
        assert change['Status'] == 'CREATE_COMPLETE' and change['ExecutionStatus'] == 'AVAILABLE'
        for item in change['Changes']:
            resource = item['ResourceChange']
            logical = resource['LogicalResourceId']
            if resource['Action'] == 'Remove': assert logical in manifests[name]['removed'], resource
            else:
                assert resource['Action'] == 'Modify', resource
                if logical in manifests[name]['modified']:
                    assert resource.get('Replacement', 'False') == 'False', resource
                else:
                    old = frozen_inventory()['stacks'][name]['template']['Resources'][logical]
                    new = json.loads((OUT / (name + '-retired.json')).read_text())['Resources'][logical]
                    assert old == new and old['Type'] in ('AWS::Lambda::Permission', 'AWS::ApiGatewayV2::Integration'), resource
                    assert resource.get('Replacement') in ('False', 'Conditional'), resource
                    assert all(d['ChangeSource'] == 'ResourceAttribute' and d['Evaluation'] == 'Dynamic'
                        and d['CausingEntity'] == 'ResearchWorkflowApiE04EBDAC.Arn' for d in resource['Details']), resource
                    api_change = next(i['ResourceChange'] for i in change['Changes'] if i['ResourceChange']['LogicalResourceId'] == 'ResearchWorkflowApiE04EBDAC')
                    assert api_change['Replacement'] == 'False', 'API ARN must remain unchanged'
        results[name] = aws('cloudformation', 'execute-change-set', '--change-set-name', identity['Id'],
            '--client-request-token', 'execute-local-skill-' + manifests[name]['sha256'])
        save('executed-change-sets.json', results)
    print(json.dumps({'submitted': list(results)}))

def status():
    sets = json.loads((OUT / 'change-sets.json').read_text()) if (OUT / 'change-sets.json').exists() else {}
    result = {'stacks': {}, 'snapshots': aws('ec2', 'describe-snapshots', '--owner-ids', 'self',
        '--filters', 'Name=tag:Retirement,Values=local-skill-v1')['Snapshots']}
    for name in STACKS:
        stack = aws('cloudformation', 'describe-stacks', '--stack-name', frozen_inventory()['stacks'][name]['stack']['StackId'])['Stacks'][0]
        result['stacks'][name] = {'status': stack['StackStatus']}
        if name in sets:
            change = aws('cloudformation', 'describe-change-set', '--change-set-name', sets[name]['Id'])
            result['stacks'][name].update(change_status=change['Status'], execution=change['ExecutionStatus'],
                changes=[i['ResourceChange'] for i in change.get('Changes', [])])
    save('aws-status.json', result)
    print(json.dumps({'stacks': {n: {k: v for k, v in s.items() if k != 'changes'} for n, s in result['stacks'].items()},
        'snapshots': [{'id': s['SnapshotId'], 'state': s['State'], 'progress': s['Progress']} for s in result['snapshots']]}))

def delete_dedicated_stack(name):
    assert name in ('JumpServeIntakeStack', 'JumpServePlatformAccessStack', 'JumpServeOpenClawStack')
    before = frozen_inventory()['stacks'][name]
    original = before['stack']['StackId']
    stack = aws('cloudformation', 'describe-stacks', '--stack-name', original)['Stacks'][0]
    if stack['StackStatus'] in ('DELETE_IN_PROGRESS', 'DELETE_COMPLETE'):
        print(json.dumps({'stack': name, 'already_submitted': True, 'status': stack['StackStatus']})); return
    assert stack['StackStatus'] in ('CREATE_COMPLETE', 'UPDATE_COMPLETE')
    for resource in before['resources']:
        if resource['ResourceType'] != 'AWS::EC2::Instance': continue
        host = resource['PhysicalResourceId']
        instance = aws('ec2', 'describe-instances', '--instance-ids', host)['Reservations'][0]['Instances'][0]
        assert instance['State']['Name'] == 'stopped'
        for block in instance['BlockDeviceMappings']:
            assert not block['Ebs']['DeleteOnTermination'], 'Original disks must survive host retirement'
            snapshots = aws('ec2', 'describe-snapshots', '--owner-ids', 'self', '--filters',
                'Name=tag:Retirement,Values=local-skill-v1', 'Name=volume-id,Values=' + block['Ebs']['VolumeId'])['Snapshots']
            assert any(s['Encrypted'] and s['State'] in ('pending', 'completed') for s in snapshots)
    # Cross-stack policies must detach before deleting the referenced IAM roles.
    if name == 'JumpServePlatformAccessStack':
        dependency = aws('cloudformation', 'describe-stacks', '--stack-name', frozen_inventory()['stacks']['JumpServeIntakeStack']['stack']['StackId'])['Stacks'][0]
        assert dependency['StackStatus'] == 'DELETE_COMPLETE', 'Retire intake policies before the release role'
    if name == 'JumpServeOpenClawStack':
        dependency = aws('cloudformation', 'describe-stacks', '--stack-name', frozen_inventory()['stacks']['JumpServePlatformAccessStack']['stack']['StackId'])['Stacks'][0]
        assert dependency['StackStatus'] == 'DELETE_COMPLETE', 'Detach supervisor access policies before its host role'
    token = 'local-skill-retire-' + name
    save(name + '-delete-intent.json', {'stack_id': original, 'client_request_token': token,
        'original_disks_retained': True, 'owner_authorized_active_shutdown': True})
    aws('cloudformation', 'delete-stack', '--stack-name', original, '--client-request-token', token,
        '--role-arn', 'arn:aws:iam::395567831870:role/cdk-hnb659fds-cfn-exec-role-395567831870-us-east-1')
    print(json.dumps({'deletion_submitted': name, 'original_disks_retained': True}))

def scan_experiments():
    regions = aws('ec2', 'describe-regions')['Regions']
    def scan(region):
        try:
            raw = subprocess.check_output(['aws', 'ec2', 'describe-instances', '--profile', 'default',
                '--region', region['RegionName'], '--output', 'json', '--cli-connect-timeout', '5', '--cli-read-timeout', '10', '--filters',
                'Name=tag:Project,Values=JumpServe,JumpServeRealWorld,JumpServeNetworkPackage',
                'Name=instance-state-name,Values=pending,running,stopping,stopped'],
                timeout=25, env={**os.environ, 'AWS_MAX_ATTEMPTS': '1'}, stderr=subprocess.PIPE)
            data = json.loads(raw)
            return {'region': region['RegionName'], 'checked': True, 'instances': [i for r in data['Reservations'] for i in r['Instances']]}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            return {'region': region['RegionName'], 'checked': False, 'error': type(error).__name__, 'instances': None}
    with ThreadPoolExecutor(max_workers=6) as pool: results = list(pool.map(scan, regions))
    save('experiment-host-scan.json', {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'regions': results})
    print(json.dumps({'regions_checked': sum(r['checked'] for r in results),
        'unverified_regions': [r['region'] for r in results if not r['checked']], 'instances': [
        {'region': r['region'], 'id': i['InstanceId'], 'state': i['State']['Name']}
        for r in results for i in r['instances'] or []]}))

def retire_workflows():
    names = ('intake-bootstrap-diagnostics.yml', 'intake-publisher-release.yml', 'platform-release.yml',
        'research-runtime-release.yml', 'supervisor-runtime-release.yml', 'platform-diagnostics.yml')
    receipts = []
    for name in names:
        path = 'repos/jumpserve-networks/jumpserve-infra/actions/workflows/' + name
        previous = json.loads(subprocess.check_output(['gh', 'api', path], timeout=30))
        subprocess.check_call(['gh', 'api', '--method', 'PUT', path + '/disable'], timeout=30)
        current = json.loads(subprocess.check_output(['gh', 'api', path], timeout=30))
        assert current['state'] == 'disabled_manually'
        receipts.append({'name': name, 'id': current['id'], 'before': previous['state'], 'after': current['state']})
        save('retired-workflows.json', receipts)
    print(json.dumps({'disabled_workflows': len(receipts)}))

def verify():
    before = frozen_inventory()
    plan = json.loads((OUT / 'change-plan.json').read_text())
    receipts = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'stacks': {}, 'retained_logs': [], 'hosts': []}
    for name, data in before['stacks'].items():
        current = aws('cloudformation', 'describe-stacks', '--stack-name', data['stack']['StackId'])['Stacks'][0]
        expected = 'DELETE_COMPLETE' if name in ('JumpServeIntakeStack', 'JumpServeOpenClawStack', 'JumpServePlatformAccessStack') else data['stack']['StackStatus']
        assert current['StackStatus'] == expected, (name, current['StackStatus'])
        receipts['stacks'][name] = current['StackStatus']
        if name in plan:
            actual = aws('cloudformation', 'get-template', '--stack-name', data['stack']['StackId'])['TemplateBody']
            desired = json.loads((OUT / (name + '-retired.json')).read_text())
            assert actual == desired, name + ' does not match the reviewed template'
            for logical in plan[name]['removed']:
                resource = next(r for r in data['resources'] if r['LogicalResourceId'] == logical)
                if resource['ResourceType'] == 'AWS::Logs::LogGroup':
                    physical = resource['PhysicalResourceId']
                    groups = aws('logs', 'describe-log-groups', '--log-group-name-prefix', physical)['logGroups']
                    assert any(g['logGroupName'] == physical for g in groups), 'Historical logs missing'
                    receipts['retained_logs'].append(physical)
        for resource in data['resources']:
            if resource['ResourceType'] == 'AWS::EC2::Instance':
                host = aws('ec2', 'describe-instances', '--instance-ids', resource['PhysicalResourceId'])['Reservations'][0]['Instances'][0]
                assert host['State']['Name'] == 'terminated'
                receipts['hosts'].append({'id': host['InstanceId'], 'state': host['State']['Name']})
    functions = set(aws('lambda', 'list-functions', '--query', 'Functions[].FunctionName'))
    removed_functions = [r['PhysicalResourceId'] for name, data in before['stacks'].items() if name in plan
        for r in data['resources'] if r['LogicalResourceId'] in plan[name]['removed'] and r['ResourceType'] == 'AWS::Lambda::Function']
    assert not functions & set(removed_functions), 'A retired function remains'
    rules = {r['Name'] for r in aws('events', 'list-rules', '--name-prefix', 'JumpServe')['Rules']}
    removed_rules = [r['PhysicalResourceId'] for name, data in before['stacks'].items() if name in plan
        for r in data['resources'] if r['LogicalResourceId'] in plan[name]['removed'] and r['ResourceType'] == 'AWS::Events::Rule']
    assert not rules & set(removed_rules), 'A retired schedule remains'
    receipts.update(passed=True, removed_functions=len(removed_functions), removed_schedules=len(removed_rules),
        removed_template_resources=sum(len(p['removed']) for p in plan.values()),
        snapshots=aws('ec2', 'describe-snapshots', '--owner-ids', 'self', '--filters', 'Name=tag:Retirement,Values=local-skill-v1')['Snapshots'])
    save('aws-verification.json', receipts)
    print(json.dumps({k: v for k, v in receipts.items() if k not in ('snapshots', 'retained_logs')}, default=str))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inventory', 'freeze', 'snapshot', 'prepare', 'propose', 'execute', 'status', 'retire-intake', 'retire-access', 'retire-openclaw', 'scan-experiments', 'retire-workflows', 'verify'])
    args = parser.parse_args()
    if args.mode != 'prepare': target()
    dedicated = {'retire-intake': 'JumpServeIntakeStack', 'retire-access': 'JumpServePlatformAccessStack', 'retire-openclaw': 'JumpServeOpenClawStack'}
    if args.mode in dedicated: delete_dedicated_stack(dedicated[args.mode])
    elif args.mode == 'scan-experiments': scan_experiments()
    elif args.mode == 'retire-workflows': retire_workflows()
    else: globals()[args.mode]()
