import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('category_release',Path(__file__).resolve().parents[1]/'bin/category-budgets-runtime-release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
class CategoryReleaseTests(unittest.TestCase):
 def template(self):
  functions={name:dict(Type='AWS::Lambda::Function',Properties=dict(Code={'S3Key':'old.zip'},Role='existing-role',Environment={'Variables':{'ORIGINAL':'retained'}},Description='old'),Metadata={'original':'retained'}) for name in release.CONTROLLERS}
  functions['Executor']=dict(Type='AWS::Lambda::Version',Properties={'FunctionName':'frozen-executor'})
  functions['ExistingRole']=dict(Type='AWS::IAM::Role',Properties={'Policies':['original-policy']})
  return dict(Resources=functions,Parameters={'Pinned':{'Type':'String','Default':'original'}},Outputs={'Original':{'Value':'retained'}})
 def test_only_three_controller_codes_and_declared_policy_settings_change(self):
  before=self.template();original=copy.deepcopy(before);after=release.render(before,'a'*64+'.zip')
  self.assertEqual(before,original)
  expected=copy.deepcopy(before)
  for name in release.CONTROLLERS:
   resource=expected['Resources'][name]
   resource['Properties']['Code']={'S3Bucket':release.BUCKET,'S3Key':'a'*64+'.zip'}
   resource['Metadata']['aws:asset:path']='asset.'+'a'*64
   if name in release.FLAGS:resource['Properties']['Environment']['Variables']['RESEARCH_CATEGORY_BUDGETS_ENABLED']='true'
   if name=='ResearchWorkflowAutonomyWorker1BCFF82C':resource['Properties']['Description']=release.DESCRIPTION
  self.assertEqual(after,expected)
 def test_unknown_controller_identity_and_arbitrary_code_keys_are_rejected(self):
  for key in ['other.zip','../../escape.zip','a'*64+'.json']:
   with self.assertRaises(ValueError):release.render(self.template(),key)
  before=self.template();before['Resources']['ResearchWorkflowApiE04EBDAC']['Type']='AWS::IAM::Role'
  with self.assertRaises(ValueError):release.render(before,'a'*64+'.zip')
if __name__=='__main__':unittest.main()
