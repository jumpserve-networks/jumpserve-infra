"""Independent fixed checks plus all former operational qualification checks."""
import hashlib,importlib.util,io,json,sys,unittest
from pathlib import Path
root=Path.cwd()/'research_workflow';sys.path[:0]=[str(root),str(root/'tests')]
import dispatch_recovery as recovery,openclaw_runtime,experiment_builder
from workflow import canonical
from unittest.mock import patch
base_path=Path(__file__).with_name('base-checks.py')
if hashlib.sha256(base_path.read_bytes()).hexdigest()!='cff4d858f4763c587b423be2fde6481d5ba19e501d10dea5d678d725f7b9fa08':raise ValueError('Frozen predecessor checks differ.')
spec=importlib.util.spec_from_file_location('frozen_base_checks',base_path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
class FailureQualification(unittest.TestCase):
 def test_only_explicit_original_error_is_accounted_for_without_dispatch(self):
  request=canonical(dict(model='gpt-6.1-sol',store=False,stream=True,tools=[dict(type='function',name='read')]))
  failed=b'data: '+canonical(dict(type='error',error=dict(code='server_is_overloaded')))+b'\n\n'
  with patch.object(openclaw_runtime,'credential') as credential,patch.object(openclaw_runtime,'http_request') as provider,patch.object(experiment_builder,'container_action') as cleanup:
   proof=recovery.captured_failure(request,failed+b'data: partial',200,'server_is_overloaded')
   self.assertFalse(proof['response_forwarded_to_agent']);self.assertEqual(proof['tool_calls_executed_from_response'],0);self.assertTrue(proof['provider_processing_unknown'])
   for raw in (failed[:-1],b'data: {"type":"response.completed"}\n\n'+failed,b'data: incomplete',b''):
    self.assertIsNone(recovery.captured_failure(request,raw,200,'server_is_overloaded'))
   self.assertIsNone(recovery.captured_failure(request,failed,200,'different-code'))
  credential.assert_not_called();provider.assert_not_called();cleanup.assert_not_called()
if __name__=='__main__':
 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(base.OperationalQualification),unittest.defaultTestLoader.loadTestsFromTestCase(FailureQualification)])
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 print(json.dumps(dict(passed=result.wasSuccessful(),profile='captured-provider-failures-v1',tests=result.testsRun,provider_calls=0)))
 sys.exit(0 if result.wasSuccessful() else 1)
