"""Handler failure, serialization and module ownership boundaries; no model I/O."""
import copy
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

import agent_prompt_test as fixtures


class AgentHandlerBoundaries(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.HandlerPromptTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.handler, self.db, self.agent = fixture.handler, fixture.db, fixture.agent

    def test_message_serialization_preserves_structured_blocks_and_normalizes_plain_text(self):
        original_block = {'toolUse': {'name': 'retained-read', 'input': {'zero': 0}}}
        raw_message = {'role': 'assistant', 'content': ['original text', 0]}
        original_message = copy.deepcopy(raw_message)
        value = self.handler._serialize_messages([
            [('role', 'assistant'), ('content', [original_block, 'text block', 0, None])],
            {'role': 'user', 'content': 'original non-list content'}, {'role': 'user'}, raw_message,
        ])
        self.assertEqual(value, [
            {'role': 'assistant', 'content': [original_block, {'type': 'text', 'text': 'text block'}, {'type': 'text', 'text': '0'}, {'type': 'text', 'text': 'None'}]},
            {'role': 'user', 'content': 'original non-list content'}, {'role': 'user'},
            {'role': 'assistant', 'content': [{'type': 'text', 'text': 'original text'}, {'type': 'text', 'text': '0'}]},
        ])
        self.assertEqual(raw_message, original_message)

    def test_malformed_request_bodies_and_oversized_study_questions_stop_before_private_reads(self):
        for body in ['{', 'null', '[]', '1']:
            with self.subTest(body=body):
                self.assertEqual(self.handler.lambda_handler({'body': body}, None)['statusCode'], 400)
        for module in ['ipv6-dns-study', 'reliable-sketch-study']:
            result = self.handler.lambda_handler({'body': json.dumps({'message': 'x' * 4001, 'module_id': module})}, None)
            self.assertEqual(result['statusCode'], 400)
        self.db.get.assert_not_called()
        self.fixture.agent_factory.assert_not_called()

    def test_idea_entrypoint_uses_verified_user_and_reports_typed_failures_without_claiming_a_saved_answer(self):
        module = types.ModuleType('research_ideas')
        module.handle = Mock(return_value={'run': {'id': 'retained-run', 'status': 'complete'}})
        body = {'action': 'idea', 'request_id': 'original-request'}
        with patch.dict(sys.modules, {'research_ideas': module}):
            result = self.handler.lambda_handler({'body': json.dumps(body)}, None)
            self.assertEqual(result['statusCode'], 200)
            self.assertEqual(result['headers']['Cache-Control'], 'no-store')
            self.assertEqual(json.loads(result['body']), module.handle.return_value)
            self.assertEqual(module.handle.call_args.args, (body, {'id': 'verified-id', 'email': 'researcher'}, self.db))
            for failure, expected in [(self.handler.AuthError(403, 'Wrong owner'), 403), (ValueError('Invalid request'), 400),
                                      (TypeError('Invalid shape'), 400), (KeyError('missing'), 400), (AttributeError('invalid'), 400),
                                      (TimeoutError('private model diagnostic'), 503)]:
                module.handle.side_effect = failure
                with self.subTest(failure=type(failure).__name__):
                    result = self.handler.lambda_handler({'body': json.dumps(body)}, None)
                    self.assertEqual(result['statusCode'], expected)
                    self.assertNotIn('private model diagnostic', result['body'])
                    self.assertNotIn('response', json.loads(result['body']))
        self.fixture.agent_factory.assert_not_called()

    def test_lazy_study_adapters_call_only_their_own_readers_and_record_the_initial_read(self):
        self.fixture.snapshot_patch.stop()
        modules = {}
        for family in ['ipv6', 'reliable', 'http2']:
            module = types.ModuleType('tools.' + family + '_study')
            for name in ['study_results', 'literature', 'configuration']:
                setattr(module, 'get_' + family + '_' + name, Mock(return_value={'recorded': family}))
            modules[module.__name__] = module
        for family, class_name in [('ipv6', 'IPv6Limits'), ('reliable', 'ReliableLimits')]:
            module = types.ModuleType(family + '_limits'); setattr(module, class_name, Mock(return_value=family + '-hook'))
            modules[module.__name__] = module
        with patch.dict(sys.modules, modules):
            self.assertEqual(self.handler.ipv6_hooks(), {'hooks': ['ipv6-hook']})
            self.assertEqual(self.handler.reliable_hooks(), {'hooks': ['reliable-hook']})
            for family in ['ipv6', 'reliable', 'http2']:
                readers = modules['tools.' + family + '_study']
                get = getattr(self.handler, 'get_' + family + '_evidence' if family != 'http2' else '_http2_evidence')
                self.assertEqual(get(), {'recorded': family})
                getattr(readers, 'get_' + family + '_study_results').assert_called_once_with()
                plan, evidence = object(), {'retained': True}
                function = getattr(self.handler, 'render_' + family + '_evidence' if family != 'http2' else '_render_http2_evidence')
                with patch.object(self.handler, 'render_' + family + '_answer', return_value='recorded' if family == 'http2' else ('recorded', [])) as render:
                    result = function(plan, evidence)
                    render.assert_called_once_with(plan, evidence, getattr(readers, 'get_' + family + '_literature'), getattr(readers, 'get_' + family + '_configuration'))
                self.assertEqual(result, 'recorded' if family == 'http2' else ('recorded', [{'name': 'get_' + family + '_study_results', 'input': {}}]))

    def test_study_evidence_failure_stops_before_any_model_invocation(self):
        for module, function in [('http2-compliance-study', '_http2_evidence'), ('ipv6-dns-study', 'get_ipv6_evidence'), ('reliable-sketch-study', 'get_reliable_evidence')]:
            self.db.get.side_effect = [[dict(fixtures.record(), module_id=module)], []]
            with patch.object(self.handler, function, side_effect=RuntimeError('private original evidence unavailable')), \
                    patch.object(self.handler, 'ipv6_hooks', return_value={}), patch.object(self.handler, 'reliable_hooks', return_value={}):
                result = self.handler.lambda_handler({'body': json.dumps({'message': 'Explain units', 'module_id': module})}, None)
            self.assertEqual(result['statusCode'], 503)
            self.assertNotIn('private original', result['body'])
        self.agent.assert_not_called()
        self.db.rpc.assert_not_called()

    def test_failed_model_and_render_calls_remain_failed_even_when_failure_persistence_is_unconfirmed(self):
        for module, family in [('http2-compliance-study', 'http2'), ('ipv6-dns-study', 'ipv6'), ('reliable-sketch-study', 'reliable')]:
            for stage in ['model', 'render']:
                self.db.get.side_effect = [[dict(fixtures.record(), module_id=module)], []]
                self.db.rpc.reset_mock(); self.db.rpc.side_effect = TimeoutError('private persistence diagnostic')
                self.agent.messages = []
                self.agent.side_effect = RuntimeError('private model diagnostic') if stage == 'model' else None
                self.agent.return_value = types.SimpleNamespace(structured_output={'topics': ['units']})
                evidence_function = '_http2_evidence' if family == 'http2' else 'get_' + family + '_evidence'
                render_function = '_render_http2_evidence' if family == 'http2' else 'render_' + family + '_evidence'
                with patch.object(self.handler, evidence_function, return_value={'meta': {}, 'claims': []}), \
                        patch.object(self.handler, render_function, side_effect=ValueError('private rendering diagnostic')), \
                        patch.object(self.handler, 'ipv6_hooks', return_value={}), patch.object(self.handler, 'reliable_hooks', return_value={}):
                    response = self.handler.lambda_handler({'body': json.dumps({'message': 'Explain units', 'module_id': module})}, None)
                with self.subTest(module=module, stage=stage):
                    self.assertEqual(response['statusCode'], 503)
                    self.assertNotIn('private', response['body'])
                    self.assertNotIn('response', json.loads(response['body']))
                    self.db.rpc.assert_called_once()
                    payload = self.db.rpc.call_args.args[1]
                    self.assertEqual(payload['p_module_id'], module)
                    self.assertEqual(payload['p_answer_provenance']['status'], 'failed')
                    self.assertEqual(payload['p_answer_provenance']['reason'], 'RuntimeError' if stage == 'model' else 'ValueError')
                    self.assertIsNone(payload['p_model_usage'])
                    self.assertIsNone(payload['p_estimated_model_cost_usd'])

    def test_current_turn_tool_events_ignore_nonobjects_missing_names_and_user_text(self):
        old = {'role': 'assistant', 'content': [{'toolUse': {'name': 'old-read'}}]}
        self.agent.messages = [copy.deepcopy(old)]
        def answer(*_args, **_kwargs):
            self.agent.messages.extend([
                {'role': 'user', 'content': [{'toolUse': {'name': 'untrusted-user-data'}}]},
                {'role': 'assistant', 'content': ['original string', {'text': 'answer'}, {'toolUse': None},
                    {'toolUse': {'name': 1}}, {'type': 'tool_use', 'name': 'legacy-read', 'input': {'zero': 0}},
                    {'toolUse': {'name': 'current-read', 'input': None}}]},
            ])
            return 'Recorded answer'
        self.agent.side_effect = answer
        response = self.handler.lambda_handler(self.fixture.request, None)
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(json.loads(response['body'])['tool_events'], [
            {'name': 'legacy-read', 'input': {'zero': 0}}, {'name': 'current-read', 'input': None}])


if __name__ == '__main__':
    unittest.main()
