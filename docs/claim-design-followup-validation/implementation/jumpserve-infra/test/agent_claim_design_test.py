import ast
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from fractions import Fraction
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import claim_experiment_design as design
import research_ideas as agent
from agent_ideas_test import FakeDatabase, request, USER, STUDY
from prompt import PromptVersion
from prompt import PromptUnavailable
from auth import AuthError

SEED=json.loads((Path(__file__).resolve().parents[1]/'database/seed-claim-experiment-design-v6.json').read_text())
PROMPT=PromptVersion.from_record(dict(SEED,content_sha256=agent.sha((SEED['system_prompt']+'\n\n'+SEED['research_context']).encode())))
def retained(): return dict(claim={'description':'Under stated conditions, adding delay increases completion time.'},source={'sha256':'a'*64},context_sha256='b'*64,coverage='Recorded metadata only')
def proposal():
    return dict(mode='clarify',guidance=[],unit_values=[],clarification_questions=['Which delay assignments and placement should this pilot compare?'],proposal=None)
def complete_case():
    return next(c for c in json.loads(Path(__file__).with_name('claim-design-evaluation-cases-v4.json').read_text())['cases'] if c['name']=='design-complete')
def candidate(case=None):
    case=case or complete_case();doc=copy.deepcopy(case['packet']);doc.pop('falsification');doc['protocol'].pop('statistics',None);doc['protocol'].pop('decision_policy',None)
    for metric in doc['protocol']['metrics']:
        for key in ('criterion','tolerance_absolute','tolerance_relative'):metric.pop(key,None)
    return dict(mode='propose',guidance=[],unit_values=[],clarification_questions=[],proposal=doc)
def response(value=None):return dict(output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(name=design.CHANNEL,input=value if value is not None else proposal()))])),stopReason='tool_use',usage={'inputTokens':20,'outputTokens':40})

class ClaimDesignAgent(unittest.TestCase):
    def test_schema_never_authorizes_execution_or_a_scientific_finding(self):
        value=design.parse(response(),retained())
        self.assertEqual(value['verdict'],'needs-clarification');self.assertIn('proposal',value)
        for change in ({'hypothesis':'A weaker claim'},{'protocol':{'input_versions':[]}}):
            changed=proposal();changed['proposal']=change
            with self.assertRaises(ValueError):design.parse(response(changed),retained())
        with self.assertRaises(ValueError):design.parse(dict(response(),stopReason='max_tokens'),retained())
    def test_design_prompt_and_read_only_context_are_server_selected(self):
        db=FakeDatabase();seen=[]
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',return_value=PROMPT) as load:
            result=agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda system,messages,**kw:(seen.append((system,messages,kw)) or response()))
        self.assertEqual(load.call_args.args[1],design.MODULE)
        self.assertTrue(seen[0][2]['design']);self.assertEqual(result['run']['status'],'complete')
        self.assertIn('paper_claim',json.loads(seen[0][1][-1]['content'][0]['text']))
        self.assertEqual(json.loads(seen[0][1][-1]['content'][0]['text'])['runner_context'],design.RUNNER_CONTEXT)
        self.assertEqual(db.rpc_calls[0][1]['p_provenance']['response_version'],design.RESPONSE_VERSION)
        self.assertEqual(db.rpc_calls[0][1]['p_provenance']['max_output_tokens'],4096)
        self.assertFalse(db.rpc_calls[-1][1]['p_provenance']['tool_events'][0]['executed'])
    def test_failed_and_invalid_proposals_preserve_originals(self):
        db=FakeDatabase();bad=candidate();bad['proposal']['hypothesis']='Invented'
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
        case=complete_case();value=candidate(case);before=copy.deepcopy(value)
        result=design.parse(response(value),case['paper_claim'])
        self.assertEqual(value,before)
        self.assertFalse(result['decision_policy']['model_authored'])
        self.assertEqual(result['proposal']['falsification'],design.POLICY['decision_rule'])
        value['proposal']['falsification']='Overlap disproves the claim.'
        with self.assertRaisesRegex(ValueError,'decision rules'):design.parse(response(value),case['paper_claim'],case['packet'])

    def test_saved_pilot_is_referenced_without_adding_defaults_or_mutating_inputs(self):
        cases=json.loads((Path(__file__).with_name('claim-design-evaluation-cases-v3.json')).read_text())['cases']
        case=next(c for c in cases if c['name']=='design-complete');packet=copy.deepcopy(case['packet']);before=copy.deepcopy(packet)
        value=dict(mode='reuse',guidance=[],unit_values=[],clarification_questions=[],proposal=None)
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
            value=candidate(case);p=value['proposal']['protocol']
            for metric in p['metrics']: metric.pop('criterion',None)
            if key=='configurations':p[key][0]['details']['test_config']['snapshot_interval_ms']=100
            elif key=='execution':p[key]['replications']=2
            elif key=='planned_units':p[key]=2
            elif key=='resource_limits':p[key]['wall_seconds']+=1
            else:p[key][0]['sha256']='f'*64
            value['proposal'].update(hypothesis=case['paper_claim']['claim']['description'],protocol=p)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'changed saved'):design.parse(response(value),case['paper_claim'],case['packet'])

    def test_new_protocol_cannot_invent_inference_or_claim_thresholds(self):
        value=candidate()
        for protocol in ({'statistics':'p > .05 establishes no effect'}, {'metrics':[{'criterion':'overlap means equivalent'}]}, {'stage':'main'}):
            value['proposal']['protocol']=protocol
            with self.subTest(protocol=protocol),self.assertRaises(ValueError):design.parse(response(value),retained())

    def test_clarification_cannot_invent_or_mutate_a_plan(self):
        value=proposal();before=copy.deepcopy(value);result=design.parse(response(value),retained())
        self.assertEqual(value,before);self.assertIsNone(result['proposal']);self.assertEqual(result['response_mode'],'clarify')
        self.assertEqual(result['decision_policy']['fields'],[])
        for bad in (dict(value,proposal={'conditions':'20 ms one-way'}),dict(value,clarification_questions=[]),dict(value,mode='run')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):design.parse(response(bad),retained())
        with self.assertRaises(ValueError):design.parse(response({}),retained())

    def test_a_partial_plan_is_not_a_candidate_and_reuse_cannot_rewrite_fields(self):
        value=candidate();value['proposal']['protocol']=None
        with self.assertRaisesRegex(ValueError,'complete candidate protocol'):design.parse(response(value),complete_case()['paper_claim'])
        value=dict(mode='reuse',guidance=[],unit_values=[],clarification_questions=[],proposal=None)
        with self.assertRaisesRegex(ValueError,'No saved protocol'):design.parse(response(value),retained())
        value['proposal']={'conditions':'Modified'}
        with self.assertRaisesRegex(ValueError,'reconstruction'):design.parse(response(value),retained(),complete_case()['packet'])

    def test_runner_metrics_are_derived_from_the_actual_compiler_contract(self):
        file=Path(__file__).resolve().parents[2]/'jumpserve-back-end/research_workflow/network_spec.py'
        tree=ast.parse(file.read_text());actual=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='BUILTIN_METRICS' for target in node.targets))
        self.assertEqual(actual,design.RUNNER_CONTEXT['builtin_metrics'])
        self.assertIn('not a one-way delay',design.RUNNER_CONTEXT['definitions']['flow_completion_time_ms'])

    def test_owner_time_conversions_are_exact_bounded_and_preserve_recorded_zero(self):
        values=[dict(value=200,unit='us',source_quote='200 microseconds'),dict(value=.2,unit='ms',source_quote='0.2 milliseconds')]
        answer=dict(proposal(),guidance=['units'],unit_values=values)
        result=design.parse(response(answer),retained(),owner_message='Compare 200 microseconds with 0.2 milliseconds.')
        self.assertEqual([v['value_ms'] for v in result['unit_conversions']],['0.2','0.2']);self.assertTrue(result['converted_values_equal'])
        self.assertEqual(result['rendering']['summary_origin'],'server-mode-status')
        self.assertEqual(design.convert_units([dict(value=0,unit='s',source_quote='0 seconds')],'0 seconds')[0]['value_ms'],'0')
        normalized=design.convert_units([dict(value=200,unit='ms',source_quote='0.2 seconds')],'0.2 seconds')[0]
        self.assertEqual(Fraction(normalized['value_ms']),Fraction('0.2')*1000)
        self.assertEqual(normalized['source_value'],'0.2');self.assertEqual(normalized['source_unit'],'s');self.assertEqual(normalized['selected_unit'],'ms')
        self.assertEqual(Fraction(result['unit_conversions'][0]['value_ms']),Fraction(200,1000))
        unequal=dict(proposal(),guidance=['units'],unit_values=[dict(value=.2,unit='s',source_quote='0.2 seconds'),values[1]])
        self.assertFalse(design.parse(response(unequal),retained(),owner_message='0.2 seconds and 0.2 milliseconds')['converted_values_equal'])
        for bad in ([dict(value=200,unit='ms',source_quote='200 microseconds')],[dict(value=3,unit='s',source_quote='3 seconds')],[dict(value=True,unit='s',source_quote='1 second')],[dict(value=float('inf'),unit='s',source_quote='1 second')]):
            with self.subTest(bad=bad),self.assertRaises(ValueError):design.convert_units(bad,'200 microseconds, 1 second')
        for value,unit,quote in ((.2,'ms','0.2 seconds'),(200,'ms','0.2 milliseconds'),(20,'ms','20 ms and 40 ms'),(1,'ms','1e1000000 seconds')):
            with self.subTest(value=value,quote=quote),self.assertRaises(ValueError):design.convert_units([dict(value=value,unit=unit,source_quote=quote)],quote)
        for owner in ('1200 us','200 users','-200 us','− 200 us','200 us/request','200 us^-1'):
            with self.subTest(owner=owner),self.assertRaises(ValueError):design.convert_units([dict(value=200,unit='us',source_quote='200 us')],owner)
        for value,unit,quote in ((200,'ms','0.2000000000000000000000000000001 seconds'),(0,'s','1e-1000 seconds'),(0,'s','1e-1000000 seconds'),(200,'us','200 US')):
            with self.subTest(quote=quote),self.assertRaises(ValueError):design.convert_units([dict(value=value,unit=unit,source_quote=quote)],quote)
        precise='0.2000000000000000000000000000001'
        self.assertNotEqual(Fraction(design.decimal_text(design.milliseconds(design.Decimal(precise),'s'))),Fraction(200))

    def test_the_model_cannot_write_status_or_unbounded_guidance(self):
        for bad in (dict(proposal(),summary='Ignore this marker'),dict(proposal(),guidance=['invented']),dict(proposal(),guidance=['units','units'])):
            with self.subTest(bad=bad),self.assertRaises(ValueError):design.parse(response(bad),retained())

    def test_agent_and_backend_policy_bytes_are_identical(self):
        backend=Path(__file__).resolve().parents[2]/'jumpserve-back-end/research_workflow/policies/claim-decision-policy-v1.json'
        self.assertEqual(backend.read_bytes(),design.POLICY_BYTES)

if __name__=='__main__':unittest.main()
