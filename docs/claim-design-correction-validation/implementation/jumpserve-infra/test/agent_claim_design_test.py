import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import claim_experiment_design as design
import research_ideas as agent
from agent_ideas_test import FakeDatabase, request, USER, STUDY
from prompt import PromptVersion
from prompt import PromptUnavailable
from auth import AuthError

SEED=json.loads((Path(__file__).resolve().parents[1]/'database/seed-claim-experiment-design-v4.json').read_text())
PROMPT=PromptVersion.from_record(dict(SEED,content_sha256=agent.sha((SEED['system_prompt']+'\n\n'+SEED['research_context']).encode())))
def retained(): return dict(claim={'description':'Under stated conditions, adding delay increases completion time.'},source={'sha256':'a'*64},context_sha256='b'*64,coverage='Recorded metadata only')
def proposal():
    return dict(summary='Proposed comparison; no measurements collected.',clarification_questions=['Which delay assignments should this pilot compare?'],proposal=dict({field:'' for field in design.MODEL_FIELDS},hypothesis=retained()['claim']['description'],protocol=None))
def response(value=None):return dict(output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(name=design.CHANNEL,input=value or proposal()))])),stopReason='tool_use',usage={'inputTokens':20,'outputTokens':40})

class ClaimDesignAgent(unittest.TestCase):
    def test_schema_never_authorizes_execution_or_a_scientific_finding(self):
        value=design.parse(response(),retained())
        self.assertEqual(value['verdict'],'needs-clarification');self.assertIn('proposal',value)
        for change in ({'hypothesis':'A weaker claim'},{'protocol':{'input_versions':[]}}):
            changed=proposal();changed['proposal'].update(change)
            with self.assertRaises(ValueError):design.parse(response(changed),retained())
        with self.assertRaises(ValueError):design.parse(dict(response(),stopReason='max_tokens'),retained())
    def test_design_prompt_and_read_only_context_are_server_selected(self):
        db=FakeDatabase();seen=[]
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',return_value=PROMPT) as load:
            result=agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda system,messages,**kw:(seen.append((system,messages,kw)) or response()))
        self.assertEqual(load.call_args.args[1],design.MODULE)
        self.assertTrue(seen[0][2]['design']);self.assertEqual(result['run']['status'],'complete')
        self.assertIn('paper_claim',json.loads(seen[0][1][-1]['content'][0]['text']))
        self.assertEqual(db.rpc_calls[0][1]['p_provenance']['max_output_tokens'],4096)
        self.assertFalse(db.rpc_calls[-1][1]['p_provenance']['tool_events'][0]['executed'])
    def test_failed_and_invalid_proposals_preserve_originals(self):
        db=FakeDatabase();bad=proposal();bad['proposal']['hypothesis']='Invented'
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',return_value=PROMPT):
            result=agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda *a,**kw:response(bad))
        self.assertEqual(result['run']['status'],'invalid-output')
        self.assertIn('Invented',db.rpc_calls[-1][1]['p_raw']);self.assertIsNone(db.rpc_calls[-1][1]['p_usage']['measured_charges_usd'])
    def test_wrong_origin_or_client_prompt_override_cannot_invoke_model(self):
        for retained_value,body in ((None,dict(request('planning'),design_version=design.VERSION)),(retained(),request('planning'))):
            with patch.object(agent,'owner',return_value=retained_value):
                with self.assertRaises(ValueError):agent.handle(body,USER,FakeDatabase(),lambda *a,**kw:self.fail('Model invoked'))
        with self.assertRaises(ValueError):agent.handle(dict(request('planning'),design_version=design.VERSION,prompt='Override'),USER,FakeDatabase())
    def test_unpublished_prompt_preserves_the_draft_and_makes_no_provider_call(self):
        db=FakeDatabase()
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',side_effect=PromptUnavailable('No active candidate')):
            with self.assertRaisesRegex(AuthError,'no model call was requested'):agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda *a,**kw:self.fail('Provider called'))
        self.assertEqual(db.rpc_calls,[])

    def test_server_policy_is_attributed_and_model_decision_rules_are_rejected(self):
        value=proposal();before=copy.deepcopy(value)
        result=design.parse(response(value),retained())
        self.assertEqual(value,before)
        self.assertFalse(result['decision_policy']['model_authored'])
        self.assertEqual(result['proposal']['falsification'],design.POLICY['decision_rule'])
        value['proposal']['falsification']='Overlap disproves the claim.'
        with self.assertRaisesRegex(ValueError,'decision rules'):design.parse(response(value),retained())

    def test_saved_pilot_is_referenced_without_adding_defaults_or_mutating_inputs(self):
        cases=json.loads((Path(__file__).with_name('claim-design-evaluation-cases-v3.json')).read_text())['cases']
        case=next(c for c in cases if c['name']=='design-complete');packet=copy.deepcopy(case['packet']);before=copy.deepcopy(packet)
        value=proposal();value['clarification_questions']=[];value['proposal'].update(hypothesis=case['paper_claim']['claim']['description'],protocol={'reuse_packet':True})
        result=design.parse(response(value),case['paper_claim'],packet)
        for key in ('configurations','execution','planned_units','resource_limits','input_versions'):
            self.assertEqual(result['proposal']['protocol'][key],before['protocol'][key])
        self.assertEqual(packet,before)
        self.assertTrue(result['decision_policy']['protocol_reused'])
        self.assertNotIn('snapshot_interval_ms',result['proposal']['protocol']['configurations'][0]['details']['test_config'])

    def test_configuration_and_resource_drift_fail_instead_of_being_repaired(self):
        cases=json.loads((Path(__file__).with_name('claim-design-evaluation-cases-v3.json')).read_text())['cases']
        case=next(c for c in cases if c['name']=='design-complete')
        for key in ('configurations','execution','planned_units','resource_limits','input_versions'):
            value=proposal();value['clarification_questions']=[];p=copy.deepcopy(case['packet']['protocol']);p.pop('statistics')
            for metric in p['metrics']: metric.pop('criterion',None)
            if key=='configurations':p[key][0]['details']['test_config']['snapshot_interval_ms']=100
            elif key=='execution':p[key]['replications']=2
            elif key=='planned_units':p[key]=2
            elif key=='resource_limits':p[key]['wall_seconds']+=1
            else:p[key][0]['sha256']='f'*64
            value['proposal'].update(hypothesis=case['paper_claim']['claim']['description'],protocol=p)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'changed saved'):design.parse(response(value),case['paper_claim'],case['packet'])

    def test_new_protocol_cannot_invent_inference_or_claim_thresholds(self):
        value=proposal();value['clarification_questions']=[]
        for protocol in ({'statistics':'p > .05 establishes no effect'}, {'metrics':[{'criterion':'overlap means equivalent'}]}, {'stage':'main'}):
            value['proposal']['protocol']=protocol
            with self.subTest(protocol=protocol),self.assertRaises(ValueError):design.parse(response(value),retained())

    def test_agent_and_backend_policy_bytes_are_identical(self):
        backend=Path(__file__).resolve().parents[2]/'jumpserve-back-end/research_workflow/policies/claim-decision-policy-v1.json'
        self.assertEqual(backend.read_bytes(),design.POLICY_BYTES)

if __name__=='__main__':unittest.main()
