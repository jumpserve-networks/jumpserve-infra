"""The prepared installation cannot target another host, account or source."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
import intake_initialization_install_test as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('intake_prepare_install',ROOT/'bin/prepare-intake-initialization-install.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


class IntakePreparation(unittest.TestCase):
 def setUp(self):
  self.fixture=fixture.IntakeInstallation();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  packet=self.fixture.packet();packet.update(installed=False,research_checks=529)
  (self.fixture.root/'packet.json').write_text(json.dumps(packet));self.packet=packet
  self.outputs={'JumpServeIntakeStack':dict(IntakeInstanceId=prepare.HOST,IntakeRuntimeBucket=prepare.BUCKET,IntakeSourceBinding=packet['previous_manifest']['source_binding'])}

 def test_prepares_immutable_uploads_and_the_exact_existing_host_without_executing(self):
  result=prepare.build(self.fixture.root,self.outputs)
  self.assertFalse(result['executed']);self.assertEqual(result['production_mutations'],0)
  self.assertTrue(result['routing_must_be_disabled']);self.assertTrue(result['reconcile_original_ssm_command_before_retry'])
  self.assertEqual(result['request']['InstanceIds'],[prepare.HOST])
  for item in result['uploads']:
   self.assertEqual(item['sha256'],prepare.digest(Path(item['source']).read_bytes()))
   self.assertTrue(item['key'].startswith('intake-repair/'+result['source_binding']+'/'))
   self.assertEqual(item['bucket'],prepare.BUCKET)
  self.assertNotIn('refresh_token',json.dumps(result));self.assertNotIn('jumpserve-platform.service',json.dumps(result))

 def test_wrong_host_account_or_source_and_modified_archive_are_refused(self):
  for key,value in (('IntakeInstanceId','i-00000000000000000'),('IntakeRuntimeBucket','another-account'),('IntakeSourceBinding','f'*64)):
   bad=copy.deepcopy(self.outputs);bad['JumpServeIntakeStack'][key]=value
   with self.assertRaises(ValueError):prepare.build(self.fixture.root,bad)
  self.fixture.bundle.write_bytes(b'different archive')
  with self.assertRaises(ValueError):prepare.build(self.fixture.root,self.outputs)


if __name__=='__main__':unittest.main()
