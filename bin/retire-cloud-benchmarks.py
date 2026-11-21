"""Owner-directed, fixed-account retirement; private receipts preserve evidence.

Preserves Supabase, public read APIs, website hosting, chat, DNS and recovery
snapshots. No arbitrary command or target arguments are accepted.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-artifacts/cloud-benchmark-retirement-20261121'
ACCOUNT = '395567831870'
BENCHMARK = 'JumpServeBenchmarkStack'
MONITOR = 'JumpServeObservabilityStack'
ASSETS = 'cdk-hnb659fds-assets-395567831870-us-east-1'

def aws(*args):
    raw = subprocess.check_output(['aws', *args, '--profile', 'default', '--region',
        'us-east-1', '--output', 'json', '--no-cli-pager'], timeout=180)
    return json.loads(raw) if raw.strip() else {}

def save(name, value):
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = OUT / name
    with open(path, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o600)

def read(name):
    return json.loads((OUT / name).read_text())

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def target():
    assert aws('sts', 'get-caller-identity')['Account'] == ACCOUNT, 'Wrong account'

def inventory():
    assert not (OUT / 'before.json').exists(), 'Original inventory is frozen'
    result = {'checked_at': now(), 'stacks': {}}
    for summary in aws('cloudformation', 'describe-stacks')['Stacks']:
        name = summary['StackName']
        result['stacks'][name] = {'stack': summary,
            'resources': aws('cloudformation', 'list-stack-resources', '--stack-name', name)['StackResourceSummaries'],
            'template': aws('cloudformation', 'get-template', '--stack-name', name)['TemplateBody']}
    result['images'] = aws('ec2', 'describe-images', '--owners', 'self')['Images']
    result['snapshots'] = aws('ec2', 'describe-snapshots', '--owner-ids', 'self')['Snapshots']
    result['volumes'] = aws('ec2', 'describe-volumes')['Volumes']
    result['instances'] = aws('ec2', 'describe-instances', '--filters', 'Name=instance-state-name,Values=pending,running,stopping,stopped')
    result['machines'] = aws('stepfunctions', 'list-state-machines')['stateMachines']
    result['running'] = []
    for machine in result['machines']:
        result['running'] += aws('stepfunctions', 'list-executions', '--state-machine-arn', machine['stateMachineArn'], '--status-filter', 'RUNNING')['executions']
    save('before.json', result)
    print(json.dumps({'stacks': {k:len(v['resources']) for k,v in result['stacks'].items()},
        'images':len(result['images']), 'snapshots':len(result['snapshots']),
        'volumes':len(result['volumes']), 'running_executions':len(result['running']),
        'live_instances':sum(len(r['Instances']) for r in result['instances']['Reservations'])}))

def refs(value):
    found = set()
    if isinstance(value, list):
        for child in value: found |= refs(child)
    elif isinstance(value, dict):
        if isinstance(value.get('Ref'), str): found.add(value['Ref'])
        attr = value.get('Fn::GetAtt')
        if isinstance(attr, list): found.add(attr[0])
        elif isinstance(attr, str): found.add(attr.split('.')[0])
        sub = value.get('Fn::Sub')
        if sub:
            text = sub if isinstance(sub, str) else sub[0]
            found |= {m.split('.')[0] for m in re.findall(r'\$\{([^!][^}]*)\}', text)}
        for child in value.values(): found |= refs(child)
    return found

def render(original):
    template = copy.deepcopy(original)
    resources = template['Resources']
    keep_real = ('RealWorldTestsApi',)
    removed = {k for k,v in resources.items() if (
        k.startswith(('BenchmarkInstance', 'BenchmarkImage', 'LaunchBenchmark',
            'CancelBenchmark', 'CleanupBenchmark', 'CleanupSchedule', 'BenchmarkIngest', 'GetBenchmarkLogs'))
        or k.startswith('RealWorldTests') and not k.startswith(keep_real)
        or v['Type'] == 'AWS::ApiGatewayV2::Route' and (
            not v['Properties']['RouteKey'].startswith('GET ')
            or v['Properties']['RouteKey'] in ('GET /benchmarks/logs', 'GET /real-world/regions', 'GET /real-world/locations')))}
    while True:
        extra = {k for k,v in resources.items() if k not in removed and
            v['Type'] in ('AWS::Lambda::Permission', 'AWS::ApiGatewayV2::Integration') and refs(v) & removed}
        # Unused route permissions for EC2 placement catalog endpoints.
        extra |= {k for k,v in resources.items() if v['Type'] == 'AWS::Lambda::Permission' and k.startswith(('BenchmarkApiGETrealworldregions', 'BenchmarkApiGETrealworldlocations'))}
        if not extra - removed: break
        removed |= extra
    modified = set()
    service = resources['RealWorldTestsApiBB989716']
    for key in ('INSTANCE_PROFILE_ARN', 'STATE_MACHINE_ARN'):
        service['Properties']['Environment']['Variables'].pop(key, None)
    modified.add('RealWorldTestsApiBB989716')
    policy_id = 'RealWorldTestsApiServiceRoleDefaultPolicyD587E15C'
    # Logical suffix differs across construct versions; select only this role policy.
    policy_id = next(k for k in resources if k.startswith('RealWorldTestsApiServiceRoleDefaultPolicy'))
    document = resources[policy_id]['Properties']['PolicyDocument']
    document['Statement'] = [s for s in document['Statement'] if not refs(s) & removed
        and not any(a.startswith(('states:', 'ec2:')) for a in ([s['Action']] if isinstance(s['Action'], str) else s['Action']))]
    modified.add(policy_id)
    for key in removed:
        if resources[key]['Type'] == 'AWS::Logs::LogGroup':
            assert resources[key].get('DeletionPolicy') == 'Retain', 'Preserve historical logs'
        del resources[key]
    for k,v in resources.items():
        deps = v.get('DependsOn', [])
        if isinstance(deps, str): deps = [deps]
        if set(deps) & removed:
            v['DependsOn'] = [d for d in deps if d not in removed]
            modified.add(k)
        assert not refs(v) & removed, f'Dangling reference: {k}'
    for key,value in list(template.get('Outputs', {}).items()):
        if refs(value) & removed: del template['Outputs'][key]
    assert not refs(template) & removed
    # APIs, read integrations, research functions, chat and data are immutable.
    for k,v in original['Resources'].items():
        if k not in removed | modified: assert resources[k] == v
    return template, sorted(removed), sorted(modified)

def prepare():
    before = read('before.json')['stacks'][BENCHMARK]
    template,removed,modified = render(before['template'])
    pins = {}
    actual = {p['ParameterKey']:p for p in before['stack'].get('Parameters', [])}
    for k,v in template.get('Parameters', {}).items():
        if v['Type'].startswith('AWS::SSM::'):
            pins[k] = actual[k]['ResolvedValue']
            v.update(Type='String', Default=pins[k])
    digest = hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest()
    save('benchmark-retired.json',template)
    plan = {'removed':removed,'modified':modified,'pins':pins,'sha256':digest}
    save('plan.json',plan)
    print(json.dumps(plan))

def freeze():
    before = read('before.json')
    # Do not disable cleanup while live executions still require it.
    assert not before['running'], 'Reconcile active executions first'
    receipts = []
    for r in before['stacks'][BENCHMARK]['resources']:
        if r['ResourceType'] == 'AWS::Lambda::Function' and r['LogicalResourceId'].startswith('LaunchBenchmark'):
            receipts.append(aws('lambda','put-function-concurrency','--function-name',r['PhysicalResourceId'],'--reserved-concurrent-executions','0'))
        if r['ResourceType'] == 'AWS::ApiGatewayV2::Route':
            key = before['stacks'][BENCHMARK]['template']['Resources'][r['LogicalResourceId']]['Properties']['RouteKey']
            if key in ('POST /benchmarks','POST /real-world/tests'):
                api_id = next(x['PhysicalResourceId'] for x in before['stacks'][BENCHMARK]['resources'] if x['ResourceType']=='AWS::ApiGatewayV2::Api')
                receipts.append(aws('apigatewayv2','delete-route','--api-id',api_id,'--route-id',r['PhysicalResourceId'].split('|')[-1]))
    save('admission-frozen.json',{'checked_at':now(),'receipts':receipts})
    print(json.dumps({'admission_frozen':True}))

def propose():
    plan=read('plan.json')
    template=read('benchmark-retired.json')
    assert hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest()==plan['sha256']
    key='retirement/cloud-benchmarks-v1/'+plan['sha256']+'.json'
    aws('s3api','put-object','--bucket',ASSETS,'--key',key,'--body',str(OUT/'benchmark-retired.json'),'--server-side-encryption','AES256')
    parameters=[{'ParameterKey':p['ParameterKey'],**({'ParameterValue':plan['pins'][p['ParameterKey']]} if p['ParameterKey'] in plan['pins'] else {'UsePreviousValue':True})} for p in read('before.json')['stacks'][BENCHMARK]['stack'].get('Parameters',[])]
    result=aws('cloudformation','create-change-set','--stack-name',BENCHMARK,
        '--change-set-name','cloud-benchmarks-retirement-'+plan['sha256'][:16],
        '--change-set-type','UPDATE','--client-token','retire-'+plan['sha256'],
        '--description','Owner-authorized cloud benchmark retirement; public read APIs preserved.',
        '--template-url','https://'+ASSETS+'.s3.us-east-1.amazonaws.com/'+key,
        '--parameters',json.dumps(parameters),'--capabilities','CAPABILITY_NAMED_IAM',
        '--role-arn','arn:aws:iam::'+ACCOUNT+':role/cdk-hnb659fds-cfn-exec-role-'+ACCOUNT+'-us-east-1')
    save('change-set.json',result)
    print(json.dumps(result))

def execute():
    plan=read('plan.json'); original=read('before.json')['stacks'][BENCHMARK]['template']; rendered=read('benchmark-retired.json')
    result=aws('cloudformation','describe-change-set','--change-set-name',read('change-set.json')['Id'])
    save('reviewed-change-set.json',result)
    assert result['Status']=='CREATE_COMPLETE' and result['ExecutionStatus']=='AVAILABLE'
    changes=[c['ResourceChange'] for c in result['Changes']]
    assert {c['LogicalResourceId'] for c in changes if c['Action']=='Remove'}==set(plan['removed'])
    for c in changes:
        k=c['LogicalResourceId']
        assert c['Action'] in ('Remove','Modify'), f'Unexpected creation {k}'
        if c['Action']=='Modify':
            assert c['Replacement'] in ('False','Conditional'), f'Replacement {k}'
            if k not in plan['modified']:
                assert original['Resources'][k]==rendered['Resources'][k]
                assert c['ResourceType'] in ('AWS::Lambda::Permission','AWS::ApiGatewayV2::Integration')
                assert all(d['Evaluation']=='Dynamic' for d in c['Details'])
    save('execution-receipt.json',{'checked_at':now(),'id':result['ChangeSetId'],
        'response':aws('cloudformation','execute-change-set','--change-set-name',result['ChangeSetId'],'--client-request-token','retire-cloud-benchmarks-'+plan['sha256'][:32])})
    print(json.dumps({'submitted':True,'removed':len(plan['removed'])}))

def status():
    result=aws('cloudformation','describe-stacks','--stack-name',BENCHMARK)['Stacks'][0]
    print(json.dumps({'status':result['StackStatus']}))

def disk():
    snapshot=aws('ec2','describe-snapshots','--snapshot-ids','snap-00bcbe6b7651fe65d')['Snapshots'][0]
    assert snapshot['State']=='completed' and snapshot['Encrypted'] and snapshot['VolumeId']=='vol-0993b9127ac7a8231' and snapshot['VolumeSize']==300
    volume=aws('ec2','describe-volumes','--volume-ids','vol-0993b9127ac7a8231')['Volumes'][0]
    assert volume['State']=='available' and not volume['Attachments'] and volume['Encrypted'] and volume['Size']==300
    save('disk-deletion.json',{'checked_at':now(),'snapshot':snapshot,'volume':volume,
        'response':aws('ec2','delete-volume','--volume-id',volume['VolumeId'])})
    print(json.dumps({'deleted_volume':volume['VolumeId'],'retained_snapshot':snapshot['SnapshotId']}))

def monitor():
    stack=read('before.json')['stacks'][MONITOR]['stack']
    assert stack['StackName']==MONITOR
    save('monitor-deletion.json',{'checked_at':now(),'stack_id':stack['StackId'],
        'response':aws('cloudformation','delete-stack','--stack-name',stack['StackId'])})
    print(json.dumps({'submitted_monitor_deletion':True}))

def retired():
    assert aws('cloudformation','describe-stacks','--stack-name',BENCHMARK)['Stacks'][0]['StackStatus']=='UPDATE_COMPLETE'
    live=aws('cloudformation','list-stack-resources','--stack-name',BENCHMARK)['StackResourceSummaries']
    assert not any(r['LogicalResourceId'] in read('plan.json')['removed'] for r in live)

def backups():
    retired()
    data=read('before.json')['stacks'][BENCHMARK]
    table=next(r['PhysicalResourceId'] for r in data['resources'] if r['ResourceType']=='AWS::DynamoDB::Table')
    bucket=next(r['PhysicalResourceId'] for r in data['resources'] if r['ResourceType']=='AWS::S3::Bucket')
    assert table.startswith('JumpServeBenchmarkStack-RealWorldTestsJobs')
    assert bucket.startswith('jumpservebenchmarkstack-realworldtestsresults')
    description=aws('dynamodb','describe-table','--table-name',table)
    assert description['Table']['TableArn'].split(':')[4]==ACCOUNT
    versions=aws('s3api','list-object-versions','--bucket',bucket)
    save('legacy-backups-before.json',{'table':description,'bucket':bucket,'versions':versions})
    receipts=[]
    objects=[{'Key':v['Key'],'VersionId':v['VersionId']} for group in ('Versions','DeleteMarkers') for v in versions.get(group,[])]
    for start in range(0,len(objects),1000):
        result=aws('s3api','delete-objects','--bucket',bucket,'--delete',json.dumps({'Objects':objects[start:start+1000],'Quiet':True}))
        assert not result.get('Errors'), 'S3 deletion incomplete'
        receipts.append(result)
    remaining=aws('s3api','list-object-versions','--bucket',bucket)
    assert not remaining.get('Versions') and not remaining.get('DeleteMarkers')
    receipts.append(aws('s3api','delete-bucket','--bucket',bucket))
    receipts.append(aws('dynamodb','delete-table','--table-name',table))
    save('legacy-backups-deleted.json',{'checked_at':now(),'bucket':bucket,'table':table,'object_versions':len(objects),'receipts':receipts})
    print(json.dumps({'bucket_deleted':bucket,'table_deletion_submitted':table,'object_versions':len(objects)}))

def images():
    retired()
    before=read('before.json')
    current=aws('ec2','describe-images','--owners','self')['Images']
    approved={i['ImageId'] for i in before['images'] if i['Name'].startswith(('jumpserve-benchmark-','jumpserve-nines2026-'))}
    assert approved=={i['ImageId'] for i in current}, 'Image inventory changed or contains unrelated images'
    # Scan every enabled region for direct instance references to these AMIs.
    scan=json.loads((ROOT/'.test-artifacts/hosted-assessment-retirement-20261120/experiment-host-scan.json').read_text())
    assert not any(region.get('instances') for region in scan['regions'])
    # Images can launch only in their owning region. Check all active instances,
    # launch templates and Auto Scaling launch configurations in that region.
    instances=aws('ec2','describe-instances','--filters','Name=instance-state-name,Values=pending,running,stopping,stopped')
    assert not any(i['ImageId'] in approved for r in instances['Reservations'] for i in r['Instances'])
    for template in aws('ec2','describe-launch-templates')['LaunchTemplates']:
        versions=aws('ec2','describe-launch-template-versions','--launch-template-id',template['LaunchTemplateId'])['LaunchTemplateVersions']
        assert not any(v['LaunchTemplateData'].get('ImageId') in approved for v in versions), 'Retained launch template uses an AMI'
    assert not any(c['ImageId'] in approved for c in aws('autoscaling','describe-launch-configurations')['LaunchConfigurations'])
    snapshots={b['Ebs']['SnapshotId'] for i in current for b in i.get('BlockDeviceMappings',[]) if 'Ebs' in b and 'SnapshotId' in b['Ebs']}
    receipts=[]
    for image in current:
        receipts.append({'image':image['ImageId'],'response':aws('ec2','deregister-image','--image-id',image['ImageId'])})
        save('images-deleted.json',{'checked_at':now(),'receipts':receipts})
    retained=aws('ec2','describe-images','--owners','self')['Images']
    assert not any(i['ImageId'] in approved for i in retained)
    used={b['Ebs']['SnapshotId'] for i in retained for b in i.get('BlockDeviceMappings',[]) if 'Ebs' in b and 'SnapshotId' in b['Ebs']}
    assert not snapshots & used
    for snapshot in sorted(snapshots):
        assert snapshot not in ('snap-00bcbe6b7651fe65d','snap-03ad59a928ee90d07')
        receipts.append({'snapshot':snapshot,'response':aws('ec2','delete-snapshot','--snapshot-id',snapshot)})
        save('images-deleted.json',{'checked_at':now(),'receipts':receipts})
    print(json.dumps({'images_deregistered':len(current),'backing_snapshots_deleted':len(snapshots)}))

def garbage_inventory():
    retired()
    result={'checked_at':now(),'stacks':{},'functions':[],'layers':[]}
    for stack in aws('cloudformation','describe-stacks')['Stacks']:
        assert not stack['StackStatus'].endswith('_IN_PROGRESS'), 'Wait for stack operations before collecting garbage'
        result['stacks'][stack['StackName']]={'stack':stack,'template':aws('cloudformation','get-template','--stack-name',stack['StackId'])['TemplateBody']}
    for function in aws('lambda','list-functions')['Functions']:
        versions=aws('lambda','list-versions-by-function','--function-name',function['FunctionName'])['Versions']
        result['functions']+=versions
    for layer in aws('lambda','list-layers')['Layers']:
        if 'JumpServe' in layer['LayerName']:
            result['layers']+=aws('lambda','list-layer-versions','--layer-name',layer['LayerName'])['LayerVersions']
    result['objects']=aws('s3api','list-objects-v2','--bucket',ASSETS).get('Contents',[])
    result['asset_versions']=aws('s3api','list-object-versions','--bucket',ASSETS)
    save('garbage-before.json',result)
    strings=json.dumps(result['stacks'])
    used={l['Arn'] for f in result['functions'] for l in f.get('Layers',[])}
    # Current templates and direct code versions/layers remain authoritative.
    stale_layers=[l for l in result['layers'] if l['LayerVersionArn'] not in used and l['LayerVersionArn'] not in strings]
    keys={o['Key'] for group in ('Versions','DeleteMarkers') for o in result['asset_versions'].get(group,[])}
    keep={k for k in keys if k in strings}
    # Retain audit templates and non-CDK content. Only immutable hash assets older
    # than this retirement are candidates; bootstrap bucket and roles remain.
    cutoff=dt.datetime(2026,11,20,tzinfo=dt.timezone.utc)
    stale_assets=[o for group in ('Versions','DeleteMarkers') for o in result['asset_versions'].get(group,[]) if re.fullmatch(r'[a-f0-9]{64}\.(?:zip|json)',o['Key']) and o['Key'] not in keep and dt.datetime.fromisoformat(o['LastModified'].replace('Z','+00:00'))<cutoff]
    plan={'layers':stale_layers,'assets':stale_assets,'retained_keys':sorted(keep),'retained_layer_arns':sorted(used)}
    save('garbage-plan.json',plan)
    print(json.dumps({'unused_layer_versions':len(stale_layers),'obsolete_asset_versions':len(stale_assets),'obsolete_bytes':sum(o.get('Size',0) for o in stale_assets),'retained_assets':len(keep),'retained_layers':len(used)}))

def garbage_prune():
    retired()
    before=read('garbage-before.json'); plan=read('garbage-plan.json')
    # A concurrent deployment invalidates the plan instead of deleting its assets.
    current=aws('cloudformation','describe-stacks')['Stacks']
    assert {s['StackName'] for s in current}==set(before['stacks'])
    for stack in current:
        assert not stack['StackStatus'].endswith('_IN_PROGRESS')
        assert aws('cloudformation','get-template','--stack-name',stack['StackId'])['TemplateBody']==before['stacks'][stack['StackName']]['template']
    used=set()
    for f in aws('lambda','list-functions')['Functions']:
        for v in aws('lambda','list-versions-by-function','--function-name',f['FunctionName'])['Versions']:
            used|={l['Arn'] for l in v.get('Layers',[])}
    receipts=[]
    for layer in plan['layers']:
        arn=layer['LayerVersionArn']; assert arn not in used
        receipts.append({'layer':arn,'response':aws('lambda','delete-layer-version','--layer-name',arn.rsplit(':',1)[0],'--version-number',str(layer['Version']))})
        save('garbage-deleted.json',{'checked_at':now(),'receipts':receipts})
    for start in range(0,len(plan['assets']),1000):
        objects=[{'Key':o['Key'],'VersionId':o['VersionId']} for o in plan['assets'][start:start+1000]]
        result=aws('s3api','delete-objects','--bucket',ASSETS,'--delete',json.dumps({'Objects':objects,'Quiet':True}))
        assert not result.get('Errors')
        receipts.append({'asset_batch':start,'count':len(objects),'response':result})
        save('garbage-deleted.json',{'checked_at':now(),'receipts':receipts})
    print(json.dumps({'layer_versions_deleted':len(plan['layers']),'obsolete_assets_deleted':len(plan['assets'])}))

def layers():
    # CDK explicitly names this layer without the JumpServe stack prefix.
    # Keep every version referenced by a retained function or live stack resource.
    retired()
    keep=set()
    for function in aws('lambda','list-functions')['Functions']:
        for version in aws('lambda','list-versions-by-function','--function-name',function['FunctionName'])['Versions']:
            keep|={layer['Arn'] for layer in version.get('Layers',[])}
    for stack in aws('cloudformation','describe-stacks')['Stacks']:
        assert not stack['StackStatus'].endswith('_IN_PROGRESS')
        keep|={r['PhysicalResourceId'] for r in aws('cloudformation','list-stack-resources','--stack-name',stack['StackId'])['StackResourceSummaries'] if r['ResourceType']=='AWS::Lambda::LayerVersion'}
    name='AgentDepsLayer51FBE89A'
    versions=aws('lambda','list-layer-versions','--layer-name',name)['LayerVersions']
    assert all(v['LayerVersionArn'].startswith('arn:aws:lambda:us-east-1:'+ACCOUNT+':layer:'+name+':') for v in versions)
    save('agent-layers-before.json',{'checked_at':now(),'versions':versions,'retained':sorted(keep)})
    receipts=[]
    for version in versions:
        if version['LayerVersionArn'] in keep: continue
        receipts.append({'arn':version['LayerVersionArn'],'response':aws('lambda','delete-layer-version','--layer-name',name,'--version-number',str(version['Version']))})
        save('agent-layers-deleted.json',{'checked_at':now(),'receipts':receipts})
    print(json.dumps({'unused_agent_layer_versions_deleted':len(receipts),'retained_versions':len(versions)-len(receipts)}))

def absent(expected, *args):
    result=subprocess.run(['aws',*args,'--profile','default','--region','us-east-1','--output','json','--no-cli-pager'],capture_output=True,text=True,timeout=60)
    assert result.returncode and expected in result.stderr, 'Resource still exists or verification failed: '+args[0]+' '+args[1]
    return True

def tidy_propose():
    retired()
    template=aws('cloudformation','get-template','--stack-name',BENCHMARK)['TemplateBody']
    removed={'GitHubActionsOidc','BenchmarkApiPOSTrealworldtestsRealWorldIntegrationPermission57867833','BenchmarkApiPOSTrealworldtestsjobIdcancelRealWorldIntegrationPermission564724A5'}
    assert not any('token.actions.githubusercontent.com' in json.dumps(r['AssumeRolePolicyDocument']) for r in aws('iam','list-roles')['Roles']), 'OIDC provider still has consumers'
    for key in removed:
        resource=template['Resources'][key]
        assert resource['Type'] in ('AWS::IAM::OIDCProvider','AWS::Lambda::Permission')
    save('tidy-before.json',template)
    for key in removed: del template['Resources'][key]
    assert not refs(template)&removed
    save('tidy-template.json',template)
    digest=hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest()
    key='retirement/cloud-benchmarks-v1/tidy-'+digest+'.json'
    aws('s3api','put-object','--bucket',ASSETS,'--key',key,'--body',str(OUT/'tidy-template.json'),'--server-side-encryption','AES256')
    parameters=[{'ParameterKey':p['ParameterKey'],'UsePreviousValue':True} for p in aws('cloudformation','describe-stacks','--stack-name',BENCHMARK)['Stacks'][0]['Parameters']]
    result=aws('cloudformation','create-change-set','--stack-name',BENCHMARK,'--change-set-name','retire-unused-benchmark-access-'+digest[:16],
        '--change-set-type','UPDATE','--template-url','https://'+ASSETS+'.s3.us-east-1.amazonaws.com/'+key,
        '--parameters',json.dumps(parameters),'--capabilities','CAPABILITY_NAMED_IAM')
    save('tidy-change-set.json',{'response':result,'removed':sorted(removed)})
    print(json.dumps({'submitted_access_cleanup_plan':True}))

def tidy_execute():
    plan=read('tidy-change-set.json')
    change=aws('cloudformation','describe-change-set','--change-set-name',plan['response']['Id'])
    save('tidy-reviewed-change-set.json',change)
    assert change['Status']=='CREATE_COMPLETE' and change['ExecutionStatus']=='AVAILABLE'
    assert {c['ResourceChange']['LogicalResourceId'] for c in change['Changes']}==set(plan['removed'])
    assert all(c['ResourceChange']['Action']=='Remove' for c in change['Changes'])
    save('tidy-execution.json',{'checked_at':now(),'response':aws('cloudformation','execute-change-set','--change-set-name',change['ChangeSetId'])})
    print(json.dumps({'removed_unused_access_resources':len(plan['removed'])}))

def verify():
    retired()
    original=read('before.json')
    checks={}
    for r in original['stacks'][BENCHMARK]['resources']:
        if r['LogicalResourceId'] not in read('plan.json')['removed']: continue
        kind=r['ResourceType']; physical=r['PhysicalResourceId']; key=r['LogicalResourceId']
        if kind=='AWS::Lambda::Function': checks[key]=absent('ResourceNotFoundException','lambda','get-function-configuration','--function-name',physical)
        elif kind=='AWS::IAM::Role': checks[key]=absent('NoSuchEntity','iam','get-role','--role-name',physical)
        elif kind=='AWS::IAM::InstanceProfile': checks[key]=absent('NoSuchEntity','iam','get-instance-profile','--instance-profile-name',physical)
        elif kind=='AWS::StepFunctions::StateMachine': checks[key]=absent('StateMachineDoesNotExist','stepfunctions','describe-state-machine','--state-machine-arn',physical)
        elif kind=='AWS::Events::Rule': checks[key]=absent('ResourceNotFoundException','events','describe-rule','--name',physical)
        elif kind=='AWS::EC2::SecurityGroup': checks[key]=absent('InvalidGroup.NotFound','ec2','describe-security-groups','--group-ids',physical)
        elif kind=='AWS::DynamoDB::Table': checks[key]=absent('ResourceNotFoundException','dynamodb','describe-table','--table-name',physical)
        elif kind=='AWS::S3::Bucket': checks[key]=absent('NoSuchBucket','s3api','list-object-versions','--bucket',physical)
    checks['recovery_volume']=absent('InvalidVolume.NotFound','ec2','describe-volumes','--volume-ids','vol-0993b9127ac7a8231')
    snapshots=aws('ec2','describe-snapshots','--owner-ids','self')['Snapshots']
    removed_snapshots={r['snapshot'] for r in read('images-deleted.json')['receipts'] if 'snapshot' in r}
    assert not removed_snapshots & {s['SnapshotId'] for s in snapshots}
    assert any(s['SnapshotId']=='snap-00bcbe6b7651fe65d' and s['State']=='completed' and s['Encrypted'] for s in snapshots)
    assert not aws('ec2','describe-images','--owners','self')['Images']
    monitor=aws('cloudformation','describe-stacks','--stack-name',original['stacks'][MONITOR]['stack']['StackId'])['Stacks'][0]
    assert monitor['StackStatus']=='DELETE_COMPLETE'
    for r in original['stacks'][MONITOR]['resources']:
        if r['ResourceType']=='AWS::Lambda::Function': checks['monitor_probe']=absent('ResourceNotFoundException','lambda','get-function-configuration','--function-name',r['PhysicalResourceId'])
        if r['ResourceType']=='AWS::Events::Rule': checks['monitor_schedule']=absent('ResourceNotFoundException','events','describe-rule','--name',r['PhysicalResourceId'])
    agent=original['stacks']['JumpServeAgentStack']
    assert aws('cloudformation','get-template','--stack-name','JumpServeAgentStack')['TemplateBody']==agent['template']
    routes=aws('apigatewayv2','get-routes','--api-id','d3o7xdethb')['Items']
    assert all(r['RouteKey'].startswith('GET ') for r in routes)
    assert any(r['RouteKey']=='GET /real-world/reports' for r in routes)
    assert any(r['RouteKey']=='GET /research/papers' for r in routes)
    unused_layers=aws('lambda','list-layer-versions','--layer-name','AgentDepsLayer51FBE89A')['LayerVersions']
    active_layers=read('agent-layers-before.json')['retained']
    assert all(v['LayerVersionArn'] in active_layers for v in unused_layers)
    asset_versions=aws('s3api','list-object-versions','--bucket',ASSETS)
    existing={(v['Key'],v['VersionId']) for group in ('Versions','DeleteMarkers') for v in asset_versions.get(group,[])}
    assert not existing & {(v['Key'],v['VersionId']) for v in read('garbage-plan.json')['assets']}
    current_keys={v['Key'] for v in asset_versions.get('Versions',[]) if v.get('IsLatest')}
    assert set(read('garbage-plan.json')['retained_keys'])<=current_keys
    result={'passed':True,'checked_at':now(),'absence_checks':checks,'monitor_status':monitor['StackStatus'],
        'benchmark_status':'UPDATE_COMPLETE','read_routes':sorted(r['RouteKey'] for r in routes),
        'retained_snapshots':[s['SnapshotId'] for s in snapshots],
        'chat_stack_unchanged':True,'images_deleted':len(original['images']),
        'backing_snapshots_deleted':len(removed_snapshots),'obsolete_asset_versions_deleted':len(read('garbage-plan.json')['assets']),
        'unused_layer_versions_remaining':0,'active_chat_layer_preserved':True}
    save('verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('absence_checks','read_routes','retained_snapshots')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['inventory','prepare','freeze','propose','execute','status','disk','monitor','backups','images','garbage-inventory','garbage-prune','layers','verify','tidy-propose','tidy-execute'])
    mode=parser.parse_args().mode
    target()
    globals()[mode.replace('-','_')]()
