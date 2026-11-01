"""The qualified reader exception cannot admit arbitrary evidence/auth edits."""
import ast,importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reader_gate',ROOT/'assets/platform/research-runtime-gate.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
OLD="""def inspect_evidence(task,request):
 if request['id']!=task['source_id']:raise ValueError('outside claim')
 extracted=True
 envelope=dict(source_material={k:v for k,v in material.items() if k!='inline_passage'},record_kind='extracted-paper-text' if extracted else 'source-metadata-only')
 result=evidence.page(records,cursor,byte_budget=10000-len(canonical(envelope))-64)
 return result
"""
NEW=OLD.replace(" envelope=dict", " inline_fields=('inline_passage','inline_fragments','inline_fragment_coverage','inline_reading_guidance')\n envelope=dict").replace("k!='inline_passage'","k not in inline_fields")
class SourceGate(unittest.TestCase):
 def test_exact_envelope_fix_is_eligible_with_every_other_reader_node_frozen(self):
  self.assertEqual(gate.protected_tree(OLD,'autonomy.py'),gate.protected_tree(NEW,'autonomy.py'))
 def test_auth_fragment_content_budget_and_coverage_changes_are_rejected(self):
  for bad in (NEW.replace("request['id']!=task['source_id']","False"),NEW.replace('page(records,','page([], '),NEW.replace('10000','1000000'),NEW.replace("'inline_fragment_coverage'","'delivery_progress'")):
   self.assertNotEqual(gate.protected_tree(OLD,'autonomy.py'),gate.protected_tree(bad,'autonomy.py'))
 def test_controller_helper_does_not_allow_transport_or_policy_changes(self):
  old="import io\nVERSION='frozen'\ndef frozen_transport():\n return 1\n"
  new=old+"CONTROLLER_VERSION='controller-terminal-reconciliation-v1'\ndef controller_terminal(task,dispatch,receipt,original,rows):\n return None\n"
  self.assertEqual(gate.protected_tree(old,'dispatch_recovery.py'),gate.protected_tree(new,'dispatch_recovery.py'))
  for bad in (new.replace("VERSION='frozen'","VERSION='changed'"),new.replace('return 1','return 2'),new.replace('reconciliation-v1','reconciliation-v2')):
   self.assertNotEqual(gate.protected_tree(old,'dispatch_recovery.py'),gate.protected_tree(bad,'dispatch_recovery.py'))
  route="def rpc(name,payload):\n if name=='research_controller_dispatch_reconcile':return request('/rest/v1/rpc/'+name,'POST',payload)\n return frozen(name,payload)\n"
  baseline="def rpc(name,payload):\n return frozen(name,payload)\n"
  self.assertEqual(gate.protected_tree(baseline,'store.py'),gate.protected_tree(route,'store.py'))
  self.assertNotEqual(gate.protected_tree(baseline,'store.py'),gate.protected_tree(route.replace('research_controller_dispatch_reconcile','anything'),'store.py'))

if __name__=='__main__':unittest.main()
