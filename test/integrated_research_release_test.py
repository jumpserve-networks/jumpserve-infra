"""Scope and immutable-version guards for the coordinated runtime renderer."""
import copy,importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('integrated',ROOT/'bin/integrated-research-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def fixture():
 version='OriginalExecutorVersion';resources={version:dict(Type='AWS::Lambda::Version',Properties=dict(FunctionName={'Ref':r.EXECUTOR})), 'ExistingAuthority':dict(Type='AWS::IAM::Policy',Properties=dict(PolicyDocument={'Statement':[]})), 'RetainedMachine':dict(Type='AWS::EC2::Instance',Properties=dict(ImageId='ami-fixture'))}
 for name in r.CONTROLLERS|r.PACKAGES:
  env={}
  for prefix in ('BUILT_PACKAGE','NETEM_IPERF'):
   env['NETWORK_'+prefix+'_FUNCTION']={'Ref':version};env['NETWORK_'+prefix+'_POLICY_SHA256']='a'*64
  resources[name]=dict(Type='AWS::Lambda::Function',Metadata={'aws:asset:path':'asset.'+'a'*64},Properties=dict(Code={'S3Bucket':r.BUCKET,'S3Key':'a'*64+'.zip'},Runtime='python3.12',Role={'Fn::GetAtt':['ExistingAuthority','Arn']},Environment=dict(Variables=env)))
 policies={runner:dict(version=version,approved_for_lab_execution=True,max_network_bytes=100000000000,maximum_cents=cents,instance_type='t3.medium',max_instances=1,max_wall_seconds=1800,max_output_bytes=3000000,cpu_credits='standard') for runner,version,cents in [('built-package-v1','built-package-costs-v3',2000),('netem-iperf-v1','netem-iperf-costs-v3',100)]}
 return dict(Resources=resources,Parameters={'PinnedImage':dict(Type='String',Default='ami-fixture')},Outputs={'Endpoint':dict(Value='https://example.invalid')}),policies

class IntegratedRelease(unittest.TestCase):
 def test_only_six_code_objects_and_exact_policy_bindings_change(self):
  before,policies=fixture();original=copy.deepcopy(before);after,version=r.render(before,'b'*64+'.zip',policies)
  self.assertEqual(before,original)
  self.assertEqual(after['Parameters'],before['Parameters']);self.assertEqual(after['Outputs'],before['Outputs'])
  self.assertEqual(after['Resources']['OriginalExecutorVersion'],before['Resources']['OriginalExecutorVersion'])
  for name in r.CONTROLLERS|r.PACKAGES:
   old=before['Resources'][name]['Properties'];new=after['Resources'][name]['Properties']
   self.assertEqual(old['Role'],new['Role']);self.assertEqual(new['Code']['S3Key'],'b'*64+'.zip')
   self.assertEqual(set(old),set(new))
   if name in r.CONTROLLERS:self.assertEqual(new['Environment']['Variables']['NETWORK_BUILT_PACKAGE_FUNCTION'],{'Ref':version})
  for name in ('ExistingAuthority','RetainedMachine'):self.assertEqual(after['Resources'][name],before['Resources'][name])
  self.assertEqual(set(after['Resources'])-set(before['Resources']),{version})
  self.assertEqual(after['Resources'][version]['DeletionPolicy'],'Retain')
  self.assertEqual(after['Resources'][version]['Properties']['CodeSha256'],r.base64.b64encode(bytes.fromhex('b'*64)).decode())
 def test_invalid_approval_or_changed_envelope_denied(self):
  before,policies=fixture()
  for key,bad in [('approved_for_lab_execution',False),('max_network_bytes',100000000001),('maximum_cents',0),('instance_type','t3.large'),('max_wall_seconds',1801)]:
   altered=copy.deepcopy(policies);altered['built-package-v1'][key]=bad
   with self.subTest(key=key),self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',altered)
 def test_unqualified_code_and_original_executor_mismatch_denied(self):
  before,policies=fixture()
  with self.assertRaises(ValueError):r.render(before,'../runtime.zip',policies)
  before['Resources'][next(iter(r.CONTROLLERS))]['Properties']['Environment']['Variables']['NETWORK_BUILT_PACKAGE_FUNCTION']='unqualified-latest'
  with self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',policies)
 def test_already_submitted_version_is_not_replayed(self):
  before,policies=fixture();after,_=r.render(before,'b'*64+'.zip',policies)
  with self.assertRaises(ValueError):r.render(after,'b'*64+'.zip',policies)
 def test_existing_security_group_is_pinned_without_new_authority(self):
  before,policies=fixture();group='ResearchWorkflowPackageMachinesF1AA60C3';before['Resources'][group]=dict(Type='AWS::EC2::SecurityGroup',Properties=dict(VpcId='vpc-fixture'))
  names=[r.EXECUTOR,'ResearchWorkflowPackageReaperED8C6D40']
  for name in names:before['Resources'][name]['Properties']['Environment']['Variables']['NETWORK_PACKAGE_SECURITY_GROUP']={'Fn::GetAtt':[group,'GroupId']}
  with self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',policies)
  after,_=r.render(before,'b'*64+'.zip',policies,'sg-0123456789abcdef0')
  self.assertEqual(before['Resources'][group],after['Resources'][group])
  self.assertEqual(before['Resources']['ExistingAuthority'],after['Resources']['ExistingAuthority'])
  for name in names:self.assertEqual(after['Resources'][name]['Properties']['Environment']['Variables']['NETWORK_PACKAGE_SECURITY_GROUP'],'sg-0123456789abcdef0')
 def test_verified_operator_published_version_needs_no_new_cloudformation_authority(self):
  before,policies=fixture();arn=r.EXECUTOR_ARN+':61'
  after,version=r.render(before,'b'*64+'.zip',policies,published_executor_arn=arn)
  self.assertIsNone(version);self.assertEqual(set(before['Resources']),set(after['Resources']))
  for name in r.CONTROLLERS:self.assertEqual(after['Resources'][name]['Properties']['Environment']['Variables']['NETWORK_BUILT_PACKAGE_FUNCTION'],arn)
  for invalid in (r.EXECUTOR_ARN+':$LATEST',r.EXECUTOR_ARN.replace('395567831870','000000000000')+':61',r.EXECUTOR_ARN.replace('PackageExe','Other')+':61'):
   with self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',policies,published_executor_arn=invalid)
 def test_followup_requires_exact_verified_literal_predecessor_and_network(self):
  before,policies=fixture();group='ResearchWorkflowPackageMachinesF1AA60C3';before['Resources'][group]=dict(Type='AWS::EC2::SecurityGroup',Properties=dict(VpcId='vpc-fixture'))
  sg='sg-0123456789abcdef0';old=r.EXECUTOR_ARN+':14';new=r.EXECUTOR_ARN+':15'
  for name in r.CONTROLLERS:
   for prefix in ('BUILT_PACKAGE','NETEM_IPERF'):before['Resources'][name]['Properties']['Environment']['Variables']['NETWORK_'+prefix+'_FUNCTION']=old
  before['Resources'][r.EXECUTOR]['Properties']['Environment']['Variables']['NETWORK_PACKAGE_SECURITY_GROUP']=sg
  with self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',policies,sg,new)
  with self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',policies,'sg-11111111111111111',new,old)
  with self.assertRaises(ValueError):r.render(before,'b'*64+'.zip',policies,sg,new,r.EXECUTOR_ARN+':13')
  after,version=r.render(before,'b'*64+'.zip',policies,sg,new,old)
  self.assertIsNone(version);self.assertEqual(set(before['Resources']),set(after['Resources']))
  self.assertEqual(after['Resources'][r.EXECUTOR]['Properties']['Environment']['Variables']['NETWORK_PACKAGE_SECURITY_GROUP'],sg)
  for name in r.CONTROLLERS:self.assertEqual(after['Resources'][name]['Properties']['Environment']['Variables']['NETWORK_BUILT_PACKAGE_FUNCTION'],new)

if __name__=='__main__':unittest.main()
