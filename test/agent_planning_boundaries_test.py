"""Planning-channel budgets, source identities and model request boundaries."""
import copy
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

from agent_ideas_test import FakeDatabase, USER, STUDY, OUTPUT, PROMPT_OBJECT, request, response
import agent_claim_design_test as design_fixtures
import research_ideas as ideas
import claim_experiment_design as design
from auth import AuthError
from prompt import PromptUnavailable


class PlanningBoundaries(unittest.TestCase):
    def test_review_output_schema_rejects_invalid_shapes_and_unresolved_readiness(self):
        changes = [None, [], dict(OUTPUT, summary=' '), dict(OUTPUT, summary=0),
            dict(OUTPUT, summary='x' * 4001), dict(OUTPUT, questions='question'),
            dict(OUTPUT, questions=['q'] * 13), dict(OUTPUT, questions=[' ']),
            dict(OUTPUT, questions=[0]), dict(OUTPUT, findings=None),
            dict(OUTPUT, findings=[{}] * 21), dict(OUTPUT, findings=[None]),
            dict(OUTPUT, findings=[{'severity':'unknown','field':'x','message':'x'}]),
            dict(OUTPUT, findings=[{'severity':'warning','field':' ','message':'x'}]),
            dict(OUTPUT, findings=[{'severity':'warning','field':'x','message':0}]),
            dict(OUTPUT, findings=[{'severity':'warning','field':'x','message':'x' * 1501}])]
        for value in changes:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError): ideas.validate_output(json.dumps(value), 'critic')
        warning = dict(OUTPUT, findings=[dict(severity='warning',field='limits',message='Original limitation')])
        self.assertEqual(ideas.validate_output(json.dumps(warning), 'critic'), warning)
        with self.assertRaises(ValueError): ideas.validate_output('{"summary":NaN}', 'critic')

    def test_model_adapter_selects_one_server_owned_response_channel_without_automatic_retries(self):
        boto = types.ModuleType('boto3'); client = Mock(); boto.client = Mock(return_value=client)
        config_module = types.ModuleType('botocore.config'); config_module.Config = Mock(return_value='synthetic-config')
        with patch.dict(sys.modules, {'boto3':boto, 'botocore':types.ModuleType('botocore'), 'botocore.config':config_module}):
            for options, channel, tokens in [({}, ideas.RESPONSE_CHANNEL, 2048), ({'interview':True}, ideas.idea_interview.CHANNEL, 2048),
                    ({'source_review':True}, ideas.idea_review.CHANNEL, 2048), ({'design':True}, design.CHANNEL, 4096)]:
                original = [{'role':'user','content':[{'text':'Original owner request'}]}]
                self.assertIs(ideas.invoke_model('Trusted system', original, **options), client.converse.return_value)
                args = client.converse.call_args.kwargs
                self.assertEqual(args['messages'], original)
                self.assertEqual(args['inferenceConfig']['maxTokens'], tokens)
                self.assertEqual(args['toolConfig']['toolChoice'], {'tool':{'name':channel}})
            self.assertEqual(config_module.Config.call_args.kwargs['retries']['total_max_attempts'], 1)

    def test_owner_checks_study_kind_and_retained_claim_bytes_before_returning_public_projection(self):
        with self.assertRaisesRegex(AuthError,'misconfigured'):ideas.owner(Mock(url='https://foreign.example.test'),STUDY,USER['id'])
        db = Mock(url=FakeDatabase.url)
        db.get.side_effect = [[{'study_id':STUDY}], [{'study_kind':'paper'}], []]
        with self.assertRaisesRegex(AuthError, 'workspace not found'): ideas.owner(db, STUDY, USER['id'])
        db.get.side_effect = [[{'study_id':STUDY}], [{'study_kind':'unknown'}]]
        with self.assertRaisesRegex(AuthError, 'Planning study not found'): ideas.owner(db, STUDY, USER['id'])
        document = dict(study={'id':STUDY}, claim={'description':'Original claim'}, gap={'reason':'Missing control'}, source={'citation':'Original source','sha256':'a'*64,'private_original_download':'private'})
        raw = ideas.canonical(document).decode(); retained = dict(raw_document=raw,sha256=ideas.sha(raw.encode()),document=document)
        db.get.side_effect = [[{'study_id':STUDY}], [{'study_kind':'paper'}], [retained]]
        result = ideas.owner(db, STUDY, USER['id'])
        self.assertEqual(result['claim'], document['claim'])
        self.assertNotIn('private_original_download', result['source'])
        for change in [{'sha256':'f'*64}, {'document':dict(document, gap={})}]:
            with self.assertRaisesRegex(ValueError, 'retained hash'): design.retained_context(dict(retained, **change))

    def test_invalid_request_versions_packet_cardinality_and_history_are_rejected_before_model_calls(self):
        for body in [dict(request(), task='execute'), dict(request(), interview_version='unknown'),
                dict(request('planning'), design_version='unknown'), dict(request(), preferred_field='inputs'),
                dict(request('planning'), interview_version=ideas.idea_interview.VERSION, preferred_field='execute')]:
            with self.assertRaises(ValueError): ideas.handle(body, USER, FakeDatabase(), Mock(side_effect=AssertionError('model called')))
        db = FakeDatabase(); original = db.get
        for invalid in [[], [db.packet, db.packet]]:
            with patch.object(db, 'get', side_effect=lambda path,params: invalid if path == 'research_idea_packets' else original(path,params)), self.assertRaises(AuthError):
                ideas.handle(request(), USER, db)
        for change in [{'session_id':None}, {'message':None}, {'message':''}, {'message':'x' * 4001}]:
            with self.assertRaisesRegex(ValueError, 'Planning needs'): ideas.handle(dict(request('planning'), **change), USER, FakeDatabase())
        with patch.object(ideas,'load_active_prompt',side_effect=PromptUnavailable('Synthetic unavailable prompt')), self.assertRaises(PromptUnavailable):
            ideas.handle(request(), USER, FakeDatabase())
        with patch.object(ideas,'owner',return_value=design_fixtures.retained()), patch.object(ideas,'load_active_prompt',return_value=PROMPT_OBJECT), self.assertRaisesRegex(AuthError, 'not published yet'):
            ideas.handle(dict(request('planning'),design_version=design.VERSION), USER, FakeDatabase())
        for history in ['invalid', [{}] * 23]:
            db = FakeDatabase(); db.history = history
            with self.assertRaisesRegex(ValueError, 'turn budget'): ideas.handle(request('planning'), USER, db)

    def test_plain_text_model_output_is_retained_but_cannot_be_executed_or_parsed_as_a_review(self):
        db = FakeDatabase(); reply = dict(output={'message':{'role':'assistant','content':[{'text':'Original '},{'text':'unstructured response'}]}},stopReason='end_turn')
        with patch.object(ideas, 'load_active_prompt', return_value=PROMPT_OBJECT):
            result = ideas.handle(request(), USER, db, lambda *_: reply)
        self.assertEqual(result['run']['status'], 'invalid-output')
        self.assertEqual(db.rpc_calls[-1][1]['p_raw'], 'Original unstructured response')
        self.assertEqual(db.rpc_calls[-1][1]['p_provenance']['tool_events'], [])

    def test_a_valid_answer_that_overflows_persisted_history_keeps_original_response_without_saving_a_partial_turn(self):
        db=FakeDatabase(); db.history=[{'role':'user' if index % 2 == 0 else 'assistant','content':[{'text':'x' * 1050}]} for index in range(20)]
        output=dict(OUTPUT,summary='s' * 4000)
        with patch.object(ideas,'load_active_prompt',return_value=PROMPT_OBJECT):
            result=ideas.handle(request('planning'),USER,db,lambda *_:response(output))
        self.assertEqual(result['run']['status'],'invalid-output')
        self.assertIn('persisted planning-history budget',result['run']['reason'])
        self.assertIsNone(db.rpc_calls[-1][1]['p_messages'])
        self.assertIn('s' * 4000,db.rpc_calls[-1][1]['p_raw'])

    def test_design_conversion_event_is_retained_as_a_bounded_computation(self):
        db = FakeDatabase(); body = dict(request('planning'), design_version=design.VERSION, message='Compare 1 second and 1000 milliseconds.')
        value = design_fixtures.proposal()
        value['unit_values'] = [dict(value=1,unit='s',source_quote='1 second'), dict(value=1000,unit='ms',source_quote='1000 milliseconds')]
        with patch.object(ideas,'owner',return_value=design_fixtures.retained()), patch.object(ideas,'load_active_prompt',return_value=design_fixtures.PROMPT):
            result = ideas.handle(body, USER, db, lambda *args,**kwargs: design_fixtures.response(value))
        self.assertEqual(result['run']['status'], 'complete')
        event = db.rpc_calls[-1][1]['p_provenance']['tool_events'][1]
        self.assertEqual(event['name'], design.CONVERSION_VERSION)
        self.assertTrue(event['executed']); self.assertEqual(len(event['conversions']), 2)

    def test_design_questions_guidance_saved_protocol_and_source_identity_remain_bounded(self):
        for values in [None,{},[{}]*4]:
            with self.assertRaisesRegex(ValueError,'At most three'):design.convert_units(values,'Original owner message')
        for change in [{'guidance':['unknown']}, {'guidance':[None]}, {'guidance':None},
                {'clarification_questions':[' ']}, {'clarification_questions':[0]}, {'clarification_questions':None},
                {'clarification_questions':['q'] * 4}, {'mode':'reuse','clarification_questions':[],'proposal':{}}]:
            with self.subTest(change=change), self.assertRaises(ValueError): design.parse(design_fixtures.response(dict(design_fixtures.proposal(), **change)), design_fixtures.retained())
        value = dict(design_fixtures.proposal(), mode='reuse', clarification_questions=[])
        with self.assertRaisesRegex(ValueError, 'saved protocol'): design.parse(design_fixtures.response(value), design_fixtures.retained())
        for stage, statistics in [('main','Descriptive only'), ('pilot','Confidence intervals establish an effect')]:
            with self.assertRaisesRegex(ValueError, 'explicitly descriptive'):
                design.parse(design_fixtures.response(value), design_fixtures.retained(), {'protocol':{'stage':stage,'statistics':statistics}})
        unresolved = design_fixtures.candidate(); unresolved['clarification_questions'] = ['Which input?']
        with self.assertRaisesRegex(ValueError, 'Resolve questions'): design.parse(design_fixtures.response(unresolved), design_fixtures.retained())
        oversized = design_fixtures.candidate(); oversized['proposal']['protocol']['retained_note'] = 'x' * 24001
        with self.assertRaisesRegex(ValueError, 'packet budget'): design.parse(design_fixtures.response(oversized), design_fixtures.complete_case()['paper_claim'])
        case = design_fixtures.complete_case()
        for kind in ['stage','hypotheses','source','unidentified']:
            candidate = design_fixtures.candidate(case); context = copy.deepcopy(case['paper_claim'])
            if kind == 'stage': candidate['proposal']['protocol']['stage'] = 'main'
            elif kind == 'hypotheses': candidate['proposal']['protocol']['hypotheses'] = 'Changed claim'
            elif kind == 'source': candidate['proposal']['protocol']['input_versions'] = []
            else: context['source']['sha256'] = None
            with self.subTest(kind=kind), self.assertRaises(ValueError): design.parse(design_fixtures.response(candidate), context)


if __name__ == '__main__': unittest.main()
