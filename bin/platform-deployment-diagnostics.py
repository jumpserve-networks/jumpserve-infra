"""Read bounded failure evidence for one original benchmark-stack operation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

STACK='JumpServeBenchmarkStack'
def collect(session,operation):
    operation=str(uuid.UUID(operation));cf=session.client('cloudformation')
    stack=cf.describe_stacks(StackName=STACK)['Stacks'][0]
    template=cf.get_template(StackName=STACK,TemplateStage='Original')['TemplateBody']
    if isinstance(template,str):template=json.loads(template)
    events=[];token=None
    for _ in range(5):
        page=cf.describe_stack_events(StackName=STACK,**({'NextToken':token} if token else {}))
        for event in page['StackEvents']:
            if str(event.get('ClientRequestToken','')).startswith('platform-'+operation+'-'):
                events.append({key:event[key] for key in ('EventId','Timestamp','LogicalResourceId','PhysicalResourceId','ResourceType','ResourceStatus','ResourceStatusReason','ClientRequestToken') if key in event})
        token=page.get('NextToken')
        if not token or events:break
    parameters=[{key:item[key] for key in ('ParameterKey','ParameterValue','ResolvedValue') if key in item} for item in stack.get('Parameters',[]) if item['ParameterKey'] in ('BenchmarkAmiId','BootstrapVersion') or item['ParameterKey'].startswith('SsmParameterValueawsservicecanonicalubuntu')]
    return dict(version='platform-deployment-diagnostics-v1',read_only=True,operation_id=operation,stack=STACK,stack_status=stack['StackStatus'],stack_status_reason=stack.get('StackStatusReason'),template_sha256=hashlib.sha256(json.dumps(template,sort_keys=True,separators=(',',':')).encode()).hexdigest(),parameters=parameters,matching_events=events,matching_events_found=bool(events),mutations=0)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--operation-id',required=True);args=parser.parse_args();operation=str(uuid.UUID(args.operation_id))
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SESSION_TOKEN'):result=dict(read_only=True,operation_id=operation,status='No AWS role obtained; no cloud request made.',mutations=0)
    else:
        import boto3
        from botocore.config import Config
        session=boto3.Session(region_name='us-east-1');original=session.client
        session.client=lambda service:original(service,config=Config(retries=dict(total_max_attempts=1),connect_timeout=15,read_timeout=60))
        if session.client('sts').get_caller_identity()['Account']!='395567831870':raise ValueError('AWS account differs.')
        result=collect(session,operation)
    out=Path('.test-artifacts/platform-release');out.mkdir(parents=True,exist_ok=True);(out/'diagnostics.json').write_text(json.dumps(result,default=str,indent=2)+'\n')
    print(json.dumps(dict(read_only=True,stack_status=result.get('stack_status'),matching_events_found=result.get('matching_events_found'),failures=[{key:event.get(key) for key in ('LogicalResourceId','ResourceStatus','ResourceStatusReason')} for event in result.get('matching_events',[]) if event.get('ResourceStatus','').endswith('FAILED')],mutations=0)))
if __name__=='__main__':main()
