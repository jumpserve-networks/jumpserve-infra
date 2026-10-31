"""Trusted scoped release/verification; no arbitrary stack, shell or SQL input.

Infrastructure is synthesized without credentials before this script is invoked.
Only rendered templates are deployed, preserving existing literal parameters.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import urllib.request
import uuid
import zipfile

ACCOUNT='395567831870'
SITE='https://jumpserve.quaint-lab.org'
REPOSITORIES={'frontend':'jumpserve-networks/jumpserve-front-end','infrastructure':'jumpserve-networks/jumpserve-infra','backend':'jumpserve-networks/jumpserve-back-end'}
STACKS=('JumpServeBenchmarkStack','JumpServeAgentStack')
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
ALLOWED_TYPES={'AWS::Lambda::Function','AWS::Lambda::LayerVersion','AWS::Lambda::Permission','AWS::ApiGateway::Method','AWS::ApiGateway::Resource','AWS::ApiGateway::Deployment','AWS::ApiGateway::Stage','AWS::Events::Rule','AWS::Logs::LogGroup'}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def guard_template(previous, candidate):
    """No deletion/replacement of machines, storage, identities or IAM policies."""
    if set(candidate)-{'Description','Resources','Parameters','Outputs','Mappings','Conditions','Metadata','Rules','AWSTemplateFormatVersion','Transform'}:raise ValueError('Unknown template section.')
    if candidate.get('Transform') or candidate.get('Parameters')!=previous.get('Parameters') or candidate.get('Mappings')!=previous.get('Mappings') or candidate.get('Conditions')!=previous.get('Conditions'):raise ValueError('Automatic release cannot change template execution or parameter definitions.')
    old=previous.get('Resources',{});new=candidate.get('Resources',{})
    changes=[]
    for name in sorted(set(old)|set(new)):
        if old.get(name)==new.get(name):continue
        if name not in new:raise ValueError('Automatic infrastructure release cannot delete resources: '+name)
        if name in old and old[name].get('Type')!=new[name].get('Type'):raise ValueError('Resource type changed: '+name)
        if new[name]['Type'] not in ALLOWED_TYPES:raise ValueError('Changed resource needs a dedicated release: '+name)
        if new[name]['Type']=='AWS::Lambda::Function':
            if name not in old:raise ValueError('New function identities need a dedicated release.')
            for field in ('Role','FunctionName','VpcConfig','FileSystemConfigs','PackageType'):
                if old[name].get('Properties',{}).get(field)!=new[name].get('Properties',{}).get(field):raise ValueError('Function authority or placement changed: '+name)
        changes.append(dict(logical_id=name,type=new[name]['Type']))
    return changes

def wait(predicate, seconds=1800):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        time.sleep(15)
    raise RuntimeError('Production verification exceeded its bounded wait; reconcile the original release.')

def publish_assets(session,candidate):
    s3=session.client('s3');proof=[];directory=(candidate/'cdk.out').resolve()
    for stack in STACKS:
        manifest=json.loads((directory/(stack+'.assets.json')).read_bytes())
        if manifest.get('dockerImages'):raise ValueError('Container image assets require their dedicated release.')
        for item in manifest.get('files',{}).values():
            source=item['source'];path=(directory/source['path']).resolve()
            if not path.is_relative_to(directory) or path.is_symlink():raise ValueError('Asset path escapes the rendered assembly.')
            if source.get('packaging')=='zip' and path.is_dir():
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
                    total=0
                    for file in sorted(path.rglob('*')):
                        if file.is_symlink():raise ValueError('Linked assets require a dedicated release.')
                        if not file.is_file():continue
                        raw=file.read_bytes();total+=len(raw)
                        if total>250000000:raise ValueError('Asset expansion exceeds its bound.')
                        info=zipfile.ZipInfo(file.relative_to(path).as_posix(),date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(file.stat().st_mode&0o777)<<16;archive.writestr(info,raw)
                raw=buffer.getvalue()
            elif source.get('packaging')=='file' and path.is_file():raw=path.read_bytes()
            else:raise ValueError('Unexpected asset packaging.')
            if len(raw)>50000000:raise ValueError('Asset transport exceeds 50 MB.')
            for destination in item['destinations'].values():
                key=destination['objectKey']
                if destination['bucketName']!=BUCKET or destination['region']!='us-east-1' or not re.fullmatch(r'[a-f0-9]{64}(?:\.zip|\.json)?',key):raise ValueError('Asset destination differs from the existing account bucket.')
                # Code assets are content addressed. Preserve existing CDK
                # objects; a newly generated ZIP need not match CDK ZIP metadata.
                try:head=s3.head_object(Bucket=BUCKET,Key=key)
                except Exception as error:
                    if getattr(error,'response',{}).get('ResponseMetadata',{}).get('HTTPStatusCode')!=404:raise
                    s3.put_object(Bucket=BUCKET,Key=key,Body=raw,ServerSideEncryption='AES256',Metadata={'platform-sha256':sha(raw)})
                    head=s3.head_object(Bucket=BUCKET,Key=key)
                proof.append(dict(key=key,byte_count=head['ContentLength'],uploaded_sha256=(head.get('Metadata') or {}).get('platform-sha256')))
    return proof

def frontend(session, revision):
    cf=session.client('cloudformation');amplify=session.client('amplify')
    stack=cf.describe_stacks(StackName='JumpServeAmplifyStack')['Stacks'][0]
    app=next(x['OutputValue'] for x in stack['Outputs'] if x['OutputKey']=='AmplifyAppId')
    def completed():
        jobs=amplify.list_jobs(appId=app,branchName='main',maxResults=50)['jobSummaries']
        jobs=[j for j in jobs if j.get('commitId')==revision]
        if not jobs:return None
        job=amplify.get_job(appId=app,branchName='main',jobId=jobs[0]['jobId'])['job']['summary']
        if job['status'] in ('FAILED','CANCELLED'):raise RuntimeError('Exact frontend build failed or was cancelled.')
        return job if job['status']=='SUCCEED' and job.get('commitId')==revision else None
    job=wait(completed)
    def public_revision():
        with urllib.request.urlopen(SITE+'/api/platform-version',timeout=30) as response:
            proof=json.loads(response.read(10000))
        return proof if proof.get('revision')==revision else None
    identity=wait(public_revision,300)
    with urllib.request.urlopen(SITE,timeout=30) as response:
        if response.status!=200:raise RuntimeError('Public frontend smoke check failed.')
    return dict(amplify_app=app,job_id=job['jobId'],public_revision=identity['revision'],public_smoke_passed=True)

def infrastructure(session, candidate, operation):
    cf=session.client('cloudformation');proof=[]
    # All comparisons complete before the first mutation. A rejected stack can
    # never leave an earlier stack deployed as a partial "successful" release.
    plans=[]
    for stack in STACKS:
        path=candidate/'cdk.out'/(stack+'.template.json')
        if not path.is_file():raise ValueError('Both fixed stack templates are required.')
        original=cf.get_template(StackName=stack,TemplateStage='Original')['TemplateBody']
        if isinstance(original,str):original=json.loads(original)
        template=json.loads(path.read_bytes());changes=guard_template(original,template)
        info=cf.describe_stacks(StackName=stack)['Stacks'][0]
        if info['StackStatus'] not in ('CREATE_COMPLETE','UPDATE_COMPLETE','UPDATE_ROLLBACK_COMPLETE'):raise RuntimeError('Stack is not settled: '+stack)
        if changes:plans.append((stack,template,changes,info))
    if not plans:raise ValueError('No supported rendered production change was found.')
    assets=publish_assets(session,candidate)
    for stack,template,changes,info in plans:
        body=encoded(template)
        if len(body)>1000000:raise ValueError('Rendered template exceeds its bounded deployment size.')
        template_argument=dict(TemplateBody=body.decode())
        if len(body)>51200:
            key='platform-releases/'+sha(body)+'.json';s3=session.client('s3')
            s3.put_object(Bucket=BUCKET,Key=key,Body=body,ServerSideEncryption='AES256')
            if s3.get_object(Bucket=BUCKET,Key=key)['Body'].read(1000001)!=body:raise ValueError('Rendered template readback differs.')
            template_argument=dict(TemplateURL='https://'+BUCKET+'.s3.us-east-1.amazonaws.com/'+key)
        token='platform-'+operation+'-'+stack
        # Native CloudFormation request tokens survive a lost update response.
        # Preserve all parameter values, tags and notification destinations.
        parameters=[dict(ParameterKey=p['ParameterKey'],ParameterValue=p['ParameterValue']) for p in info.get('Parameters',[])]
        result=cf.update_stack(StackName=stack,**template_argument,Parameters=parameters,Capabilities=['CAPABILITY_IAM','CAPABILITY_NAMED_IAM'],RoleARN='arn:aws:iam::395567831870:role/JumpServePlatformCloudFormation',ClientRequestToken=token,Tags=info.get('Tags',[]),NotificationARNs=info.get('NotificationARNs',[]))
        def settled():
            current=cf.describe_stacks(StackName=stack)['Stacks'][0];status=current['StackStatus']
            if status.endswith('_IN_PROGRESS'):return None
            if status!='UPDATE_COMPLETE':raise RuntimeError('CloudFormation rolled back or failed: '+status)
            deployed=cf.get_template(StackName=stack,TemplateStage='Original')['TemplateBody']
            if isinstance(deployed,str):deployed=json.loads(deployed)
            if encoded(deployed)!=body:raise RuntimeError('Deployed template differs from the rendered candidate.')
            return dict(stack=stack,status=status,template_sha256=sha(body),changes=changes,stack_id=result['StackId'])
        proof.append(wait(settled))
    return dict(stacks=proof,assets=assets,scope='Exact rendered templates and settled stacks; application behavior still requires its module-specific checks.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component',choices=REPOSITORIES,required=True);parser.add_argument('--repository',required=True);parser.add_argument('--revision',required=True);parser.add_argument('--operation-id',required=True);parser.add_argument('--candidate',type=Path,default=Path('.candidate'));args=parser.parse_args()
    if args.repository!=REPOSITORIES[args.component] or not re.fullmatch('[a-f0-9]{40}',args.revision):raise ValueError('Exact repository/revision required.')
    args.operation_id=str(uuid.UUID(args.operation_id))
    import boto3
    from botocore.config import Config
    session=boto3.Session(region_name='us-east-1')
    # Mutating AWS SDK calls have no automatic transport retries. The workflow
    # identity or CloudFormation ClientRequestToken performs reconciliation.
    original_client=session.client
    session.client=lambda service:original_client(service,config=Config(retries=dict(total_max_attempts=1),connect_timeout=15,read_timeout=60))
    if session.client('sts').get_caller_identity()['Account']!=ACCOUNT:raise ValueError('AWS account differs.')
    if args.component=='frontend':result=frontend(session,args.revision)
    elif args.component=='infrastructure':result=infrastructure(session,args.candidate,args.operation_id)
    else:
        # The dedicated AMI job produces and verifies the actual selected image.
        proof=json.loads(Path('backend-proof/production-verification.json').read_bytes())
        if proof.get('passed') is not True or proof.get('revision')!=args.revision:raise ValueError('Exact AMI verification receipt required.')
        result=proof
    receipt=dict(version='platform-production-verification-v1',passed=True,operation_id=args.operation_id,component=args.component,repository=args.repository,revision=args.revision,verified_at=dt.datetime.now(dt.timezone.utc).isoformat(),evidence=result)
    Path('production-verification.json').write_bytes(encoded(receipt))

if __name__=='__main__':main()
