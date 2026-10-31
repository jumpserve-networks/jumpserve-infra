"""Frozen operational qualification; run without credentials or network."""
import copy,io,json,sys,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
root=Path.cwd()/'research_workflow';sys.path[:0]=[str(root),str(root/'tests')]
import autonomy,autonomy_model as model,autonomous_repair as repair,store,siwc_protocol as wire
from test_autonomy import answer,response,task
class OperationalQualification(unittest.TestCase):
 def test_invalid_read_identifiers_are_rejected_before_evidence_transport(self):
  for value in ['bounded-tcp-v1','invented',' ']:
   decision=answer('inspect');decision.update(reason='retained-evidence',read_request=dict(kind='runtime-contract',id=value,cursor=0))
   with self.assertRaises(ValueError):model.parse(response(decision))
  identity=str(uuid.uuid4());decision=answer('inspect');decision.update(reason='retained-evidence',read_request=dict(kind='runtime-contract',id=identity,cursor=0))
  self.assertEqual(model.parse(response(decision))['read_request']['id'],identity)
 def test_missing_original_expired_turn_evidence_never_admits_a_replacement(self):
  item=task();item['claim_id']=str(uuid.uuid4());turn=dict(id=str(uuid.uuid4()),task_id=item['id'],study_id=item['study_id'],request_sha256='a'*64)
  def rows(t,kind,**query):return [turn] if kind=='autonomy_turns' and query.get('status')=='eq.unknown' else []
  with patch.object(repair,'rows',side_effect=rows),patch.object(repair,'original') as original:
   result=repair.diagnose(item,dict(category='runtime'))
  self.assertTrue(result['waiting']);original.assert_not_called()
 def test_optional_housekeeping_failure_keeps_ordinary_admission_checks(self):
  calls=[]
  def rpc(name,payload):
   calls.append(name)
   if name=='research_autonomy_resume_turns':raise store.StoreError('Synthetic maintenance fault')
   if name=='research_autonomy_runtime_observe':return dict(recorded=True)
   if name=='research_autonomy_control':self.assertEqual(payload['p_operation'],'lease');return None
   raise AssertionError(name)
  with patch.object(model,'OPENCLAW',False),patch.object(model,'load_prompt'),patch.object(repair,'discover',return_value=[]),patch.object(store,'rpc',side_effect=rpc),patch.dict('os.environ',RESEARCH_AUTONOMY_CONTEXT_RECOVERY=''):
   result=autonomy.handler({},None)
  self.assertEqual(calls.count('research_autonomy_control'),2);self.assertEqual(len(result['maintenance_faults']),1)
 def test_truncated_generation_is_never_a_terminal_completion(self):
  raw=b'event: response.created\ndata: {"type":"response.created","response":{"id":"retained-incomplete","status":"in_progress","model":"gpt-6.1-sol"}}\n\nevent: response.function_call_arguments.delta\ndata: {"type":"response.function_call_arguments.delta","delta":"partial"}\n\n'
  with self.assertRaises(Exception):wire.read_terminal_stream(io.BytesIO(raw),io.BytesIO(),time.monotonic()+5,10000)
 def test_scientific_phase_and_coverage_restrictions_remain_enforced(self):
  decision=answer('assess');decision.update(assessment_label='reproduced',evidence_ids=[str(uuid.uuid4())])
  with self.assertRaises(ValueError):model.validate_phase(decision,dict(task='planning'))
  decision=answer('inspect');decision.update(read_request=dict(kind='runtime-contract',id=str(uuid.uuid4()),cursor=0),coverage_complete=True)
  with self.assertRaises(ValueError):model.parse(response(decision))
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(OperationalQualification);result=unittest.TextTestRunner(verbosity=2).run(suite)
 print(json.dumps(dict(version='research-runtime-checks-v1',passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),provider_calls=0,network_required=False)))
 sys.exit(0 if result.wasSuccessful() else 1)
