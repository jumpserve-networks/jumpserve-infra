import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('retained_control',Path(__file__).resolve().parents[1]/'assets/platform/qualify-retained-control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
class RetainedControlTests(unittest.TestCase):
 def test_settled_local_admission_stop_is_distinct_from_unknown_or_failed_tools(self):
  envelope=dict(error=dict(kind='incomplete_turn'),assistantTurns=7,toolSummary=dict(failures=0));runs=[dict(status='complete') for _ in range(6)];stops=[dict(denied='budget',provider_dispatched=False)]
  control.verify_envelope(envelope,runs,stops)
  for invalid in ('unknown','running','failed'):
   with self.assertRaises(ValueError):control.verify_envelope(envelope,[dict(status=invalid)]+runs[1:],stops)
  with self.assertRaises(ValueError):control.verify_envelope(envelope,runs,[])
  with self.assertRaises(ValueError):control.verify_envelope(dict(envelope,toolSummary=dict(failures=1)),runs,stops)
  with self.assertRaises(ValueError):control.verify_envelope(envelope,runs,[dict(denied='budget',provider_dispatched=True)])
if __name__=='__main__':unittest.main()
