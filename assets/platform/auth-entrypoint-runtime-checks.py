"""Frozen prior checks plus real Node/SQLite symlink auth regressions."""
import hashlib,importlib.util,json,subprocess,sys,unittest
from pathlib import Path
path=Path(__file__).with_name('captured-failure-checks.py')
if hashlib.sha256(path.read_bytes()).hexdigest()!='883af117284bfcda986be7816aa3dcf7b6f1d78517eaf61ccefb36e6ddc7501f':raise ValueError('Frozen captured failure checks differ.')
spec=importlib.util.spec_from_file_location('fixed_captured_checks',path);previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
class AuthEntrypointQualification(unittest.TestCase):
 def test_native_auth_owner_and_symlinked_entrypoints(self):
  self.assertEqual(subprocess.check_output(['node','--version'],text=True).strip(),'v24.16.0')
  result=subprocess.run(['node','--test','--test-reporter=tap','research_workflow/tests/openclaw_auth_test.mjs','research_workflow/tests/openclaw_auth_entrypoint_test.mjs'],capture_output=True,text=True,timeout=60)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('# tests 21',result.stdout);self.assertIn('# pass 21',result.stdout);self.assertIn('# fail 0',result.stdout)
if __name__=='__main__':
 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(previous.base.OperationalQualification),unittest.defaultTestLoader.loadTestsFromTestCase(previous.FailureQualification),unittest.defaultTestLoader.loadTestsFromTestCase(AuthEntrypointQualification)])
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 print(json.dumps(dict(passed=result.wasSuccessful(),profile='auth-helper-entrypoint-v1',tests=result.testsRun,native_tests=21,provider_calls=0)))
 sys.exit(0 if result.wasSuccessful() else 1)
