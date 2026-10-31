"""Prepare and explicitly bootstrap the fixed-target platform supervisor.

Preparation is read-only outside local artifacts. Mutation commands are separate
and must be invoked only for an explicitly authorized initial deployment.
No owner email, service key or GitHub credential is committed into source.
"""
import argparse
import hashlib
import importlib.util
import io
import gzip
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
MIGRATIONS=['202610300004_platform_supervisor.sql','202610300005_platform_worker.sql','202610300006_platform_host_coordination.sql']
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
def aws(*args):
    raw=subprocess.check_output(['aws',*args,'--profile','jumpserve','--region','us-east-1','--output','json'],timeout=60)
    return json.loads(raw) if raw.strip() else None
def target():
    if aws('sts','get-caller-identity')['Account']!='395567831870':raise ValueError('AWS target differs.')
def admin():
    spec=importlib.util.spec_from_file_location('platform_admin',ROOT/'bin/agent-prompts.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if module.PROJECT_REF!='regphejnlvfpyokpniny':raise ValueError('Supabase target differs.')
    return module
def package():
    buffer=io.BytesIO();files={}
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((BACK/'platform_supervisor').iterdir()):
            if not path.is_file() or path.suffix not in ('.py','.json') or path.is_symlink():continue
            raw=path.read_bytes();name='platform_supervisor/'+path.name;files[name]=sha(raw)
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,raw)
        for name in ('jumpserve-platform.service','install-platform.sh'):
            raw=(ROOT/'assets/platform'/name).read_bytes();files[name]=sha(raw)
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,raw)
    return buffer.getvalue(),files
def validate(packet):
    for name,digest in packet['migration_sha256'].items():
        if sha((ROOT/'database'/name).read_bytes())!=digest:raise ValueError('Prepared migration changed.')
    raw,files=package()
    if sha(raw)!=packet['bundle_sha256'] or files!=packet['files']:raise ValueError('Prepared platform source changed; prepare a new review packet.')
    policy=(BACK/'platform_supervisor/policy.json').read_bytes()
    if packet['policy']!=json.loads(policy) or packet['policy_sha256']!=sha(policy) or packet['aws_account']!='395567831870' or packet['supabase_project']!='regphejnlvfpyokpniny' or packet['bucket']!=BUCKET:raise ValueError('Prepared authorization differs.')
    return raw
def prepare(owners_file,out):
    owners=json.loads(owners_file.read_bytes())
    if not isinstance(owners,list) or not owners or len(owners)>20 or len(set(owners))!=len(owners) or any(not isinstance(email,str) or email!=email.lower() or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) for email in owners):raise ValueError('Private verified owner address list required.')
    target();resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeOpenClawStack')['StackResourceSummaries']
    worker=next(x['PhysicalResourceId'] for x in resources if x['ResourceType']=='AWS::EC2::Instance')
    role=next(x['PhysicalResourceId'] for x in resources if x['ResourceType']=='AWS::IAM::Role')
    if not re.fullmatch('i-[a-f0-9]{17}',worker) or not re.fullmatch('JumpServeOpenClawStack-[A-Za-z0-9_-]+',role):raise ValueError('Worker target differs.')
    metadata=aws('ec2','describe-instances','--instance-ids',worker)['Reservations'][0]['Instances'][0]['MetadataOptions']
    requires_hardening=metadata.get('HttpTokens')!='required' or metadata.get('HttpPutResponseHopLimit')!=1
    raw,files=package();out.mkdir(parents=True,exist_ok=True);(out/'runtime.zip').write_bytes(raw)
    if (ROOT/'assets/platform/Dockerfile').read_bytes()!=(BACK/'platform_supervisor/Dockerfile').read_bytes():raise ValueError('Worker and release tool recipes differ.')
    subject=json.loads(subprocess.check_output(['gh','api','repos/jumpserve-networks/jumpserve-infra/actions/oidc/customization/sub'],timeout=60))
    if subject.get('use_immutable_subject') is not False or subject.get('use_default') is not True or subject.get('sub_claim_prefix')!='repo:jumpserve-networks/jumpserve-infra':raise ValueError('GitHub OIDC subject format differs from the reviewed trust policy.')
    policy=(BACK/'platform_supervisor/policy.json').read_bytes()
    packet=dict(version='platform-bootstrap-v1',aws_account='395567831870',supabase_project='regphejnlvfpyokpniny',worker_id=worker,worker_role=role,bucket=BUCKET,api_ids=['d3o7xdethb'],bundle_sha256=sha(raw),files=files,policy_sha256=sha(policy),policy=json.loads(policy),owners=owners,migration_sha256={name:sha((ROOT/'database'/name).read_bytes()) for name in MIGRATIONS},automatic_releases=True,initially_paused=True,metadata_options_before=metadata,requires_metadata_hardening=requires_hardening)
    save(out/'private-packet.json',packet);(out/'private-packet.json').chmod(0o600)
    command=['npx','cdk','--app','npx ts-node --prefer-ts-exts bin/platform.ts','synth','JumpServePlatformAccessStack','--quiet','-c','platformWorkerRoleName='+role,'-c','platformAssetBucketName='+BUCKET,'-c','platformApiIds=d3o7xdethb','--output',str(out/'cdk.out')]
    subprocess.run(command,cwd=ROOT,check=True,timeout=120,capture_output=True)
    print(json.dumps(dict(prepared=True,packet=str(out/'private-packet.json'),owners=len(owners),worker_replaced=False,aws_static_keys=False,initially_paused=True,requires_metadata_hardening=requires_hardening)))
def harden(packet):
    validate(packet);target()
    current=aws('ec2','describe-instances','--instance-ids',packet['worker_id'])['Reservations'][0]['Instances'][0]['MetadataOptions']
    if current.get('HttpTokens')!='required' or current.get('HttpPutResponseHopLimit')!=1:
        aws('ec2','modify-instance-metadata-options','--instance-id',packet['worker_id'],'--http-tokens','required','--http-put-response-hop-limit','1')
    print(json.dumps(dict(requested_imdsv2=True,requested_hop_limit=1,worker_replaced=False,verification_required=True)))
def migrate(packet):
    validate(packet);db=admin()
    for name in MIGRATIONS:
        marker={'202610300004_platform_supervisor.sql':"to_regclass('public.platform_settings')",'202610300005_platform_worker.sql':"to_regprocedure('public.platform_worker(text,uuid,uuid,uuid,jsonb)')",'202610300006_platform_host_coordination.sql':"to_regprocedure('public.research_model_dispatch_before_platform_v1(text,jsonb)')"}[name]
        exists=db.query('select '+marker+' is not null present')[0]['present']
        if not exists:db.query((ROOT/'database'/name).read_text(),read_only=False)
    literal=db.literal
    for email in packet['owners']:db.query('insert into public.platform_operator_enrollments(email,role) values('+literal(email)+",'owner') on conflict(email) do update set role='owner'",read_only=False)
    policy=json.dumps(packet['policy'],sort_keys=True,separators=(',',':'))
    db.query('insert into public.platform_authorizations(version,policy_sha256,document,source_instruction) values('+','.join([literal(packet['policy']['version']),literal(packet['policy_sha256']),literal(policy)+'::jsonb',literal('User explicitly requested the named autonomous platform supervisor with merge and production deployment authority for the three JumpServe repositories.')])+') on conflict(version) do nothing',read_only=False)
    current=db.query('select policy_sha256 from public.platform_authorizations where version='+literal(packet['policy']['version']))
    if current!=[dict(policy_sha256=packet['policy_sha256'])]:raise ValueError('Existing immutable authority differs; append a newly authorized version.')
    db.query('update public.platform_settings set authorization_version='+literal(packet['policy']['version'])+',paused=true where id',read_only=False)
    print(json.dumps(dict(migrated=True,owners=len(packet['owners']),paused=True)))
def access(packet):
    validate(packet);target()
    subprocess.run(['npx','cdk','--app','npx ts-node --prefer-ts-exts bin/platform.ts','deploy','JumpServePlatformAccessStack','--require-approval','never','--profile','jumpserve','-c','platformWorkerRoleName='+packet['worker_role'],'-c','platformAssetBucketName='+BUCKET,'-c','platformApiIds='+','.join(packet['api_ids'])],cwd=ROOT,check=True,timeout=900)
def protect(packet):
    validate(packet)
    body=dict(required_status_checks=dict(strict=True,contexts=['Platform validation']),enforce_admins=True,required_pull_request_reviews=dict(required_approving_review_count=0,dismiss_stale_reviews=True,require_code_owner_reviews=False),restrictions=None,allow_force_pushes=False,allow_deletions=False,required_conversation_resolution=True)
    for repo in packet['policy']['repositories']:
        subprocess.run(['gh','api','--method','PUT','repos/'+repo+'/branches/main/protection','--input','-'],input=json.dumps(body).encode(),stdout=subprocess.DEVNULL,check=True,timeout=60)
    print(json.dumps(dict(protected_repositories=3,strict=True,admin_bypass=False)))
def install(packet,packet_path):
    raw=validate(packet);target();directory=packet_path.parent
    metadata=aws('ec2','describe-instances','--instance-ids',packet['worker_id'])['Reservations'][0]['Instances'][0]['MetadataOptions']
    if metadata.get('HttpTokens')!='required' or metadata.get('HttpPutResponseHopLimit')!=1 or metadata.get('State')!='applied':raise ValueError('Verify applied IMDSv2/hop-limit-one settings before installing service credentials or dependency containers.')
    image=json.loads((BACK/'.test-artifacts/platform-native/image.json').read_bytes())
    if image['recipe_sha256']!=sha((BACK/'platform_supervisor/Dockerfile').read_bytes()):raise ValueError('Tool image recipe changed.')
    reports=[]
    for path in (BACK/'.test-artifacts/platform-native').glob('*/report.json'):
        value=json.loads(path.read_bytes())
        if value.get('passed') and value.get('live') and value.get('image')==image['image']:reports.append(path)
    if not reports:raise ValueError('Passed bounded live coding control for this image is required.')
    # Secret bytes stay in memory/stdin; never command arguments or artifacts.
    existing=aws('secretsmanager','list-secrets')['SecretList']
    platform=next((item for item in existing if item['Name']=='jumpserve/platform-supervisor'),None)
    if not platform:
        original=aws('secretsmanager','get-secret-value','--secret-id','jumpserve/github-token')['SecretString']
        try:decoded=json.loads(original);token=decoded.get('github_token') or decoded.get('token')
        except ValueError:token=original
        if not isinstance(token,str) or not token:raise ValueError('Existing GitHub service token is unavailable.')
        sys.path.insert(0,str(BACK));from platform_supervisor.github import GitHub
        github=GitHub(token)
        for repository in packet['policy']['repositories']:
            permissions=github.request('GET','/repos/'+repository).get('permissions') or {}
            if permissions.get('push') is not True:raise ValueError('GitHub service credential lacks push permission for an authorized repository.')
        response=subprocess.run(['aws','secretsmanager','create-secret','--name','jumpserve/platform-supervisor','--secret-string','file:///dev/stdin','--profile','jumpserve','--region','us-east-1','--output','json'],input=json.dumps(dict(github_token=token)).encode(),capture_output=True,check=True,timeout=60)
        platform=json.loads(response.stdout)
    archive=directory/'platform-image.tar.gz'
    if sha((directory/'runtime.zip').read_bytes())!=packet['bundle_sha256']:raise ValueError('Prepared runtime archive changed.')
    if not archive.exists():
        temporary=directory/'platform-image.tar'
        subprocess.run(['docker','save','--output',str(temporary),image['image']],check=True,timeout=300)
        with temporary.open('rb') as source,archive.open('wb') as file,gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0) as compressed:shutil.copyfileobj(source,compressed)
        temporary.unlink()
    with archive.open('rb') as original:image_archive_sha=hashlib.file_digest(original,'sha256').hexdigest()
    for name,path in [(packet['bundle_sha256']+'.zip',directory/'runtime.zip'),('images/'+image_archive_sha+'.tar.gz',archive)]:
        aws('s3api','put-object','--bucket',BUCKET,'--key','platform-supervisor/'+name,'--body',str(path),'--server-side-encryption','AES256')
    comment='platform-install-'+packet['bundle_sha256'][:32];intent=directory/'install-intent.json'
    if intent.exists():
        commands=aws('ssm','list-commands','--max-results','50')['Commands'];matches=[c for c in commands if c.get('Comment')==comment and packet['worker_id'] in c.get('InstanceIds',[])]
        if len(matches)!=1:raise ValueError('Original installation dispatch remains uncertain; no duplicate command was sent.')
        print(json.dumps(dict(command_id=matches[0]['CommandId'],reconciled=True)));return
    script=ROOT/'assets/platform/install-platform.sh';destination='/tmp/jumpserve-platform-'+packet['bundle_sha256']+'.zip';host_script='/tmp/jumpserve-platform-'+packet['bundle_sha256']+'.sh'
    commands=['set -eu','aws s3 cp '+shlex.quote('s3://'+BUCKET+'/platform-supervisor/'+packet['bundle_sha256']+'.zip')+' '+shlex.quote(destination)+' --region us-east-1 --only-show-errors',"echo "+shlex.quote(packet['bundle_sha256']+'  '+destination)+' | sha256sum --check',"python3.12 -c "+shlex.quote('import pathlib,zipfile;pathlib.Path('+repr(host_script)+').write_bytes(zipfile.ZipFile('+repr(destination)+').read("install-platform.sh"))'),'bash '+shlex.quote(host_script)+' '+' '.join(shlex.quote(v) for v in (packet['bundle_sha256'],image['image'],image_archive_sha,platform['ARN'],BUCKET))]
    save(intent,dict(comment=comment,worker_id=packet['worker_id'],bundle_sha256=packet['bundle_sha256'],image=image['image'],image_archive_sha256=image_archive_sha,qualification=str(reports[-1])))
    result=aws('ssm','send-command','--instance-ids',packet['worker_id'],'--document-name','AWS-RunShellScript','--comment',comment,'--parameters',json.dumps(dict(commands=commands)))
    save(directory/'install-command.json',dict(command_id=result['Command']['CommandId'],instance_id=packet['worker_id']))
    print(json.dumps(dict(command_id=result['Command']['CommandId'],submitted=True,production_verified=False)))
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','migrate','access','protect','harden','install']);parser.add_argument('--owners-file',type=Path);parser.add_argument('--packet',type=Path);parser.add_argument('--output',type=Path,default=ROOT/'.test-artifacts/platform-bootstrap/v1');args=parser.parse_args()
    if args.action=='prepare':
        if not args.owners_file:parser.error('--owners-file is required')
        prepare(args.owners_file,args.output)
    else:
        if not args.packet:parser.error('--packet is required')
        packet=json.loads(args.packet.read_bytes())
        if args.action=='install':install(packet,args.packet)
        else:globals()[args.action](packet)

if __name__=='__main__':main()
