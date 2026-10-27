"""Deployment parameter guards; synthetic configurations, no AWS calls."""
import copy,importlib.util,json,os,shlex,subprocess,tempfile,unittest
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

class AuthorizationMaintenance(unittest.TestCase):
 def test_native_login_requires_held_admission_polling_and_drained_work(self):
  def configuration(enabled='false',rule='DISABLED'):
   def aws(service,operation,*args):
    if operation=='get-function-configuration':return dict(Environment=dict(Variables=dict(RESEARCH_AUTONOMY_ENABLED=enabled)))
    if operation=='list-stack-resources':return dict(StackResourceSummaries=[dict(ResourceType='AWS::Events::Rule',LogicalResourceId='ResearchWorkflowAutonomyPoll',PhysicalResourceId='fixed-rule')])
    if operation=='describe-rule':return dict(State=rule)
    raise AssertionError(operation)
   return aws
  with patch.object(release,'functions',return_value=dict(api='fixed-api')):
   for enabled,rule in [('true','DISABLED'),('false','ENABLED')]:
    with self.subTest(enabled=enabled,rule=rule),patch.object(release,'aws',side_effect=configuration(enabled,rule)),self.assertRaisesRegex(RuntimeError,'Hold new admission'):release.auth_maintenance_guard()
   with patch.object(release,'aws',side_effect=configuration()),patch.object(release.admin,'query',return_value=[dict(count=1)]),self.assertRaisesRegex(RuntimeError,'Drain active'):release.auth_maintenance_guard()
   with patch.object(release,'aws',side_effect=configuration()),patch.object(release.admin,'query',return_value=[dict(count=0)]):release.auth_maintenance_guard()
 def test_maintenance_restores_prior_service_state_on_success_or_failure(self):
  # Execute the real shell lifecycle with a synthetic systemctl executable;
  # no sudo, AWS, actual service action, native sign-in or credentials.
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);tool=root/'systemctl';tool.write_text('#!/bin/sh\nif test "$1" = is-active; then test "$TASK_SERVICE_ACTIVE" = 1; else printf "%s\\n" "$1" >> "$TASK_SERVICE_LOG"; fi\n');tool.chmod(0o755)
   for active in ('0','1'):
    for code in (0,7):
     log=root/('calls-'+active+'-'+str(code));env=dict(os.environ,PATH=str(root)+':/usr/bin:/bin',TASK_SERVICE_ACTIVE=active,TASK_SERVICE_LOG=str(log))
     result=subprocess.run(['/bin/bash','-c',release.auth_maintenance_script('/bin/sh -c '+shlex.quote('exit '+str(code)))],env=env,capture_output=True,timeout=5)
     self.assertEqual(result.returncode,code,result.stderr);self.assertEqual(log.read_text().splitlines() if log.exists() else [],['stop','start'] if active=='1' else [])
 def test_native_login_and_forced_refresh_use_the_same_private_owner_lock(self):
  self.assertIn('flock -x /var/lib/jumpserve-openclaw/auth/refresh.lock',release.native_auth_command())
  command=release.host_refresh_command();self.assertIn('r.credential(force_refresh=True)',command);self.assertNotIn('refreshTokenSharingCredential',command);self.assertNotIn('UPDATE config_machine_state',command)
if __name__=='__main__':unittest.main()
