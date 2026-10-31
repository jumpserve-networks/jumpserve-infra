"""Dedicated source-qualified category-budget controller release.

Only the three existing research controller code objects, two category-policy
flags and the obsolete autonomy description can change. All experiment code,
versions, roles, resources, parameters and outputs retain their deployed bytes.
"""
import argparse,base64,copy,datetime as dt,hashlib,io,json,ssl,subprocess,sys,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACK=ROOT.parent/'jumpserve-back-end'
BASE=ROOT/'.test-artifacts/category-budgets-runtime-release-v1'
STACK='JumpServeBenchmarkStack'
BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
BINDING='e4637cd12044f0289a8ee9533fc76b8817f69b4724e91a26eec058f59a560f31'
CONTROLLERS={'ResearchWorkflowApiE04EBDAC','ResearchWorkflowAutonomyWorker1BCFF82C','ResearchWorkflowQueueWorker702E601D'}
FLAGS={'ResearchWorkflowApiE04EBDAC','ResearchWorkflowAutonomyWorker1BCFF82C'}
DESCRIPTION='Autonomous paper claims with Supabase category budgets; original deadlines, reservations and uncertain-call safeguards retained.'
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(name):return json.loads((BASE/name).read_bytes())
def save(name,value):
 BASE.mkdir(parents=True,exist_ok=True);p=BASE/name;p.write_bytes(encoded(value));p.chmod(0o600)
def aws(*args):
 raw=subprocess.check_output(['aws',*args,'--profile','jumpserve','--region','us-east-1','--output','json'],timeout=90)
 return json.loads(raw) if raw.strip() else None
def body(value):return json.loads(value) if isinstance(value,str) else value
def render(previous,key):
 if not __import__('re').fullmatch('[a-f0-9]{64}\\.zip',key):raise ValueError('Content-addressed code object required.')
 rendered=copy.deepcopy(previous)
 for name in sorted(CONTROLLERS):
  resource=rendered['Resources'][name]
  if resource['Type']!='AWS::Lambda::Function':raise ValueError('Controller identity differs.')
  resource['Properties']['Code']=dict(S3Bucket=BUCKET,S3Key=key)
  resource.setdefault('Metadata',{})['aws:asset:path']='asset.'+key[:-4]
  if name in FLAGS:resource['Properties']['Environment']['Variables']['RESEARCH_CATEGORY_BUDGETS_ENABLED']='true'
  if name=='ResearchWorkflowAutonomyWorker1BCFF82C':resource['Properties']['Description']=DESCRIPTION
 return rendered
def sources():
 profile=json.loads((ROOT/'category-budgets-runtime-release.json').read_bytes())
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());files=manifest['files']
 assert profile['version']=='category-budgets-runtime-release-v1' and manifest['version']==76
 assert manifest['source_revision']==profile['source_revision']
 assert set(files)==set(profile['previous_source_files'])|{'budget_policy.py'}
 changed={n for n in profile['previous_source_files'] if n!='policies/autonomous-repair-release-v1.json' and files[n]!=profile['previous_source_files'][n]}
 assert changed=={'autonomy.py','autonomy_model.py','paper_uploads.py','scheduler.py','store.py'}
 assert sha(encoded({n:h for n,h in files.items() if n!='policies/autonomous-repair-release-v1.json'}))==BINDING==profile['qualified_files_sha256']
 for name,expected in files.items():assert sha((BACK/'research_workflow'/name).read_bytes())==expected,name
 policy=json.loads((BACK/'research_workflow/policies/autonomous-repair-release-v1.json').read_bytes())
 assert policy['approved_for_lab_recovery'] and policy['qualified_files_sha256']==BINDING and policy['evidence_sha256']==profile['evidence_sha256']
 return profile,manifest
def functions(resources,expected,directory):
 result=[]
 for name in sorted(CONTROLLERS):
  physical=resources[name];value=aws('lambda','get-function','--function-name',physical);config=value['Configuration']
  assert ':395567831870:' in config['FunctionArn']
  context=ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform=='darwin' else None)
  with urllib.request.urlopen(value['Code']['Location'],context=context,timeout=60) as response:raw=response.read(12000001)
  assert len(raw)<=12000000 and base64.b64encode(hashlib.sha256(raw).digest()).decode()==config['CodeSha256']
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   actual={n:sha(archive.read(n)) for n in expected}
  assert actual==expected,'Installed source differs: '+name
  (directory/(name+'.zip')).write_bytes(raw)
  result.append(dict(logical_id=name,function=physical,code_sha256=config['CodeSha256'],runtime=config['Runtime'],handler=config['Handler'],role=config['Role'],category_policy_enabled=config['Environment']['Variables'].get('RESEARCH_CATEGORY_BUDGETS_ENABLED')))
 return result
def prepare():
 profile,manifest=sources()
 if (BASE/'prepared.json').exists():raise ValueError('Prepared release exists; use its original deployment identity.')
 assert aws('sts','get-caller-identity')['Account']=='395567831870'
 info=aws('cloudformation','describe-stacks','--stack-name',STACK)['Stacks'][0];assert info['StackStatus']=='UPDATE_COMPLETE'
 previous=body(aws('cloudformation','get-template','--stack-name',STACK,'--template-stage','Original')['TemplateBody'])
 resources={x['LogicalResourceId']:x['PhysicalResourceId'] for x in aws('cloudformation','list-stack-resources','--stack-name',STACK)['StackResourceSummaries']}
 BASE.mkdir(parents=True,exist_ok=True)
 before=functions(resources,profile['previous_source_files'],BASE)
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
  for name in sorted(manifest['files']):
   item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(item,(BACK/'research_workflow'/name).read_bytes())
 raw=stream.getvalue();key=sha(raw)+'.zip';(BASE/'runtime.zip').write_bytes(raw)
 candidate=render(previous,key)
 assert {n for n in previous['Resources'] if previous['Resources'][n]!=candidate['Resources'][n]}==CONTROLLERS
 for section in set(previous)-{'Resources'}:assert previous[section]==candidate[section]
 save('template-before.json',previous);save('template-candidate.json',candidate)
 operation=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:category-budget-runtime:'+sha(encoded(candidate))))
 result=dict(operation_id=operation,profile=profile,manifest=manifest,code_key=key,code_sha256=sha(raw),previous_template_sha256=sha(encoded(previous)),candidate_template_sha256=sha(encoded(candidate)),parameters=info.get('Parameters',[]),outputs=info.get('Outputs',[]),tags=info.get('Tags',[]),notifications=info.get('NotificationARNs',[]),functions_before=before,resources=resources)
 save('prepared.json',result);print(json.dumps(dict(prepared=True,operation_id=operation,controllers=sorted(CONTROLLERS),source_binding=BINDING,all_other_resources_preserved=True)))
def deploy():
 sources();prepared=read('prepared.json');candidate=read('template-candidate.json');previous=read('template-before.json')
 assert render(previous,prepared['code_key'])==candidate
 if (BASE/'deployment-intent.json').exists():raise ValueError('Original deployment was submitted; verify without redispatch.')
 actual=body(aws('cloudformation','get-template','--stack-name',STACK,'--template-stage','Original')['TemplateBody'])
 assert actual==previous,'Production changed after preparation.'
 raw=(BASE/'runtime.zip').read_bytes();assert sha(raw)==prepared['code_sha256']
 aws('s3api','put-object','--bucket',BUCKET,'--key',prepared['code_key'],'--body',str(BASE/'runtime.zip'),'--server-side-encryption','AES256','--if-none-match','*')
 template=BASE/'template-candidate.json';key='platform-releases/'+sha(template.read_bytes())+'.json'
 aws('s3api','put-object','--bucket',BUCKET,'--key',key,'--body',str(template),'--server-side-encryption','AES256')
 request=dict(StackName=STACK,TemplateURL='https://'+BUCKET+'.s3.us-east-1.amazonaws.com/'+key,Parameters=[dict(ParameterKey=p['ParameterKey'],ParameterValue=p['ParameterValue']) for p in prepared['parameters']],Capabilities=['CAPABILITY_IAM','CAPABILITY_NAMED_IAM'],RoleARN='arn:aws:iam::395567831870:role/JumpServePlatformCloudFormation',ClientRequestToken='category-budgets-'+prepared['operation_id'],Tags=prepared['tags'],NotificationARNs=prepared['notifications'])
 save('deployment-intent.json',dict(request=request,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),source_binding=BINDING));save('stack-request.json',request)
 result=aws('cloudformation','update-stack','--cli-input-json','file://'+str(BASE/'stack-request.json'));save('deployment-acknowledgement.json',result)
 print(json.dumps(dict(submitted=True,operation_id=prepared['operation_id'],stack_id=result['StackId'])))
def verify():
 prepared=read('prepared.json');info=aws('cloudformation','describe-stacks','--stack-name',STACK)['Stacks'][0]
 if info['StackStatus'].endswith('_IN_PROGRESS'):print(json.dumps(dict(status=info['StackStatus'])));return
 assert info['StackStatus']=='UPDATE_COMPLETE',info['StackStatus']
 actual=body(aws('cloudformation','get-template','--stack-name',STACK,'--template-stage','Original')['TemplateBody']);assert actual==read('template-candidate.json')
 assert info.get('Parameters',[])==prepared['parameters'] and info.get('Outputs',[])==prepared['outputs']
 result=functions(prepared['resources'],prepared['manifest']['files'],BASE)
 assert all(x['category_policy_enabled']=='true' for x in result if x['logical_id'] in FLAGS)
 proof=dict(passed=True,operation_id=prepared['operation_id'],source_revision=prepared['manifest']['source_revision'],source_binding=BINDING,template_sha256=sha(encoded(actual)),functions=result,all_other_template_content_preserved=True,verified_at=dt.datetime.now(dt.timezone.utc).isoformat(),interactive_release=True)
 save('production-verification.json',proof);print(json.dumps(proof))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','deploy','verify']);args=parser.parse_args();globals()[args.action]()
