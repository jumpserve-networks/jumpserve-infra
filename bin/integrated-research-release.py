"""Render a qualified research runtime rollout from the actual deployed template.

Interactive release only. This renderer grants no deployment authority and does
not alter the supervisor's narrower operational-release adapter.
"""
import base64,copy,hashlib,json,re

BUCKET='cdk-hnb659fds-assets-395567831870-us-east-1'
CONTROLLERS={'ResearchWorkflowApiE04EBDAC','ResearchWorkflowAutonomyWorker1BCFF82C','ResearchWorkflowQueueWorker702E601D'}
PACKAGES={'ResearchWorkflowPackageExecutor32D08CE2','ResearchWorkflowPackageIngestAA97237D','ResearchWorkflowPackageReaperED8C6D40'}
EXECUTOR='ResearchWorkflowPackageExecutor32D08CE2'
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()

def render(previous,key,policies,security_group_pin=None):
 if not re.fullmatch(r'[a-f0-9]{64}\.zip',key):raise ValueError('Content-addressed runtime ZIP required.')
 expected={'built-package-v1':('built-package-costs-v3',2000),'netem-iperf-v1':('netem-iperf-costs-v3',100)}
 if set(policies)!=set(expected):raise ValueError('Both exact v3 policies required.')
 for runner,(version,cents) in expected.items():
  p=policies[runner]
  if p.get('version')!=version or p.get('approved_for_lab_execution') is not True or p.get('max_network_bytes')!=100000000000 or p.get('maximum_cents')!=cents or p.get('instance_type')!='t3.medium' or p.get('max_instances')!=1 or p.get('max_wall_seconds')!=1800 or p.get('max_output_bytes')!=3000000 or p.get('cpu_credits')!='standard':raise ValueError('Qualified policy envelope differs.')
 old=previous['Resources'];versions=[n for n,r in old.items() if r['Type']=='AWS::Lambda::Version' and r.get('Properties',{}).get('FunctionName')=={'Ref':EXECUTOR}]
 if not versions:raise ValueError('Existing immutable executor version required.')
 result=copy.deepcopy(previous);new_version='ResearchWorkflowPackageExecutorIntegratedVersion'+key[:24]
 if new_version in old:raise ValueError('This immutable release version already exists; reconcile its original deployment.')
 for name in CONTROLLERS|PACKAGES:
  resource=result['Resources'][name]
  if resource['Type']!='AWS::Lambda::Function' or resource['Properties'].get('Runtime')!='python3.12':raise ValueError('Existing research function identity/runtime differs.')
  resource['Properties']['Code']={'S3Bucket':BUCKET,'S3Key':key}
  resource.setdefault('Metadata',{})['aws:asset:path']='asset.'+key[:-4]
  if name in CONTROLLERS:
   env=resource['Properties']['Environment']['Variables']
   for prefix,runner in [('BUILT_PACKAGE','built-package-v1'),('NETEM_IPERF','netem-iperf-v1')]:
    if env.get('NETWORK_'+prefix+'_FUNCTION') not in [{'Ref':v} for v in versions]:raise ValueError('Controller no longer uses the reviewed immutable executor.')
    env['NETWORK_'+prefix+'_FUNCTION']={'Ref':new_version}
    env['NETWORK_'+prefix+'_POLICY_SHA256']=digest(canonical(policies[runner]))
  elif 'NETWORK_PACKAGE_SECURITY_GROUP' in resource['Properties'].get('Environment',{}).get('Variables',{}):
   # CloudFormation re-reads GetAtt attributes even during a code-only update.
   # The fixed release caller verifies this pin against both installed Lambda
   # environments and the existing stack's physical security-group identity.
   env=resource['Properties']['Environment']['Variables'];value=env['NETWORK_PACKAGE_SECURITY_GROUP']
   if value!={'Fn::GetAtt':['ResearchWorkflowPackageMachinesF1AA60C3','GroupId']} or not isinstance(security_group_pin,str) or not re.fullmatch(r'sg-(?:[a-f0-9]{8}|[a-f0-9]{17})',security_group_pin):raise ValueError('Existing network placement must have a verified literal pin.')
   if old['ResearchWorkflowPackageMachinesF1AA60C3']['Type']!='AWS::EC2::SecurityGroup':raise ValueError('Existing security group identity differs.')
   env['NETWORK_PACKAGE_SECURITY_GROUP']=security_group_pin
 result['Resources'][new_version]={'Type':'AWS::Lambda::Version','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{'FunctionName':{'Ref':EXECUTOR},'CodeSha256':base64.b64encode(bytes.fromhex(key[:-4])).decode(),'Description':'Qualified integrated research runtime '+key[:-4]}}
 # Existing invocations retain their original executor version. No role,
 # permission, endpoint, machine, storage or stack parameter changes enter here.
 assert {n for n in old if old[n]!=result['Resources'][n]}==CONTROLLERS|PACKAGES
 for section in set(previous)-{'Resources'}:assert previous[section]==result[section]
 return result,new_version
