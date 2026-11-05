"""Publisher request preparation cannot copy a refresh grant or replace old workers."""
import json,runpy,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];module=runpy.run_path(str(ROOT/'bin/prepare-intake-publisher.py'))

class IntakeRelease(unittest.TestCase):
 def outputs(self):
  binding=json.loads((ROOT/'intake-worker-runtime.json').read_bytes())['source_binding']
  return {'JumpServeIntakeStack':dict(IntakeSourceBinding=binding,IntakeRuntimeBucket='cdk-hnb659fds-assets-395567831870-us-east-1',IntakePublisherBucket='cdk-hnb659fds-assets-395567831870-us-east-1',IntakeRuntimeObject='a'*64+'.zip',IntakePublisherObject='b'*64+'.service')}
 def test_only_adds_a_publisher_to_the_exact_existing_owner(self):
  value=module['build'](self.outputs());commands='\n'.join(value['Parameters']['commands'])
  self.assertEqual(value['InstanceIds'],['i-087f1493809643115']);self.assertIn('sha256sum --check',commands)
  self.assertIn('m["source_revision"]',commands);self.assertIn('m["source_binding"]',commands)
  self.assertIn('systemctl enable --now jumpserve-intake-access.service',commands)
  for excluded in ('restart jumpserve-openclaw','stop jumpserve-openclaw','refresh_token','get-parameter','get-secret-value'):
   self.assertNotIn(excluded,commands)
 def test_wrong_source_account_or_mutable_asset_is_refused_before_a_request_exists(self):
  for key,value in (('IntakeSourceBinding','f'*64),('IntakeRuntimeBucket','another-account'),('IntakePublisherObject','latest.service'),('IntakeRuntimeObject','a'*64+';whoami')):
   outputs=self.outputs();outputs['JumpServeIntakeStack'][key]=value
   with self.assertRaises(ValueError):module['build'](outputs)

if __name__=='__main__':unittest.main()
