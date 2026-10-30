"""Exact staged optional-budget qualification; never replace the worker runtime."""
import importlib.util,json,sys,traceback,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('completion_qualification',ROOT/'completion_qualification.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def native():
 assert not (ROOT/'native.json').exists() and json.loads((ROOT/'prepared.json').read_bytes())['status']=='passed'
 sys.path.insert(0,str(ROOT/'research_workflow/tests'));suite=unittest.TestSuite()
 for name in ('test_openclaw.py','test_optional_budget.py','test_assessment_recovery.py'):
  suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'research_workflow/tests'),pattern=name))
 with (ROOT/'native-tests.log').open('w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 report=dict(status='passed' if result.wasSuccessful() and result.testsRun==23 and not result.skipped else 'failed',tests=dict(run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)),live_provider_calls=0,source_revision=base.packet['source_revision'])
 base.save('native.json',report);assert report['status']=='passed',report
if __name__=='__main__':
 action=sys.argv[1];assert action in ('prepare','native','live','evidence')
 try:
  if action=='native':native()
  else:getattr(base,action)()
 except Exception:base.save(action+'-failure.json',dict(status='failed',traceback=traceback.format_exc()));raise
