"""Deployment parameter guards; synthetic configurations, no AWS calls."""
import copy,importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
spec=importlib.util.spec_from_file_location('paper_release',ROOT/'bin/paper-confirmation-release.py');paper=importlib.util.module_from_spec(spec);spec.loader.exec_module(paper)
class ParameterGuards(unittest.TestCase):
 def setUp(self):
  self.before=dict(parameters=[dict(ParameterKey='BenchmarkAmiId',ParameterValue='ami-fixed'),dict(ParameterKey='Fallback',ParameterValue='/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id',ResolvedValue='ami-old'),dict(ParameterKey='BootstrapVersion',ParameterValue='/cdk-bootstrap/hnb659fds/version',ResolvedValue='31')]);self.image=dict(ami_id='ami-fixed',mode='prebaked')
 def test_metadata_order_and_only_inactive_fallback_resolution_are_recorded(self):
  after=copy.deepcopy(self.before);after['parameters'][1]['ResolvedValue']='ami-new';after['parameters'].reverse()
  value=release.compare_parameters(self.before,after,self.image);self.assertEqual(value['resolved_lookup_changes'],[dict(key='Fallback',before='ami-old',after='ami-new')]);self.assertTrue(value['literal_parameters_unchanged'])
 def test_literal_or_active_image_changes_remain_blocking(self):
  after=copy.deepcopy(self.before);after['parameters'][0]['ParameterValue']='ami-other'
  with self.assertRaisesRegex(RuntimeError,'Literal'):release.compare_parameters(self.before,after,self.image)
  for image in (dict(ami_id='ami-other',mode='prebaked'),dict(ami_id='ami-fixed',mode='base')):
   with self.assertRaisesRegex(RuntimeError,'Active'):release.compare_parameters(self.before,self.before,image)
 def test_unrelated_resolved_parameter_changes_remain_blocking(self):
  after=copy.deepcopy(self.before);after['parameters'][2]['ResolvedValue']='32'
  with self.assertRaisesRegex(RuntimeError,'Unexpected'):release.compare_parameters(self.before,after,self.image)
 def test_corrective_package_pin_removes_only_its_original_mutable_lookup(self):
  before=copy.deepcopy(self.before);before['parameters'].append(dict(ParameterKey='PackageImage',ParameterValue=paper.PACKAGE_LOOKUP,ResolvedValue=paper.PACKAGE_AMI))
  def aws(service,operation,*args):
   return dict(StackResourceSummaries=[dict(ResourceType='AWS::Lambda::Function',LogicalResourceId='ResearchWorkflowPackageExecutor',PhysicalResourceId='fixed-package')]) if operation=='list-stack-resources' else dict(Environment=dict(Variables=dict(NETWORK_PACKAGE_AMI=paper.PACKAGE_AMI)))
  with patch.object(paper.r,'aws',side_effect=aws):
   value=paper.compare_paper_parameters(before,self.before,self.image)
   self.assertEqual(value['package_image_pinned'],paper.PACKAGE_AMI);self.assertEqual(len(value['removed_mutable_package_lookup']),1)
   with self.assertRaisesRegex(RuntimeError,'Mutable package lookup'):paper.compare_paper_parameters(before,before,self.image)
   changed=copy.deepcopy(self.before);changed['parameters'][0]['ParameterValue']='ami-other'
   with self.assertRaisesRegex(RuntimeError,'Literal'):paper.compare_paper_parameters(before,changed,self.image)
 def test_corrective_package_guard_rejects_changed_deployed_image(self):
  def aws(service,operation,*args):
   return dict(StackResourceSummaries=[dict(ResourceType='AWS::Lambda::Function',LogicalResourceId='ResearchWorkflowPackageExecutor',PhysicalResourceId='fixed-package')]) if operation=='list-stack-resources' else dict(Environment=dict(Variables=dict(NETWORK_PACKAGE_AMI='ami-unreviewed')))
  with patch.object(paper.r,'aws',side_effect=aws),self.assertRaisesRegex(RuntimeError,'Package experiment image'):paper.compare_paper_parameters(self.before,self.before,self.image)
if __name__=='__main__':unittest.main()
