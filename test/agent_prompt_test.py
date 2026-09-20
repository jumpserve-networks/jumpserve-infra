import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from prompt import PromptUnavailable, PromptVersion, load_active_prompt
from prompt_publication import evaluation_snapshot, publish_evaluated_prompt
from evaluate_agent import grading_payload


def record(version='one', identifier='00000000-0000-4000-8000-000000000001'):
    system, research = f'System {version}', f'Research {version} α'
    return {'id': identifier, 'version': version, 'system_prompt': system,
            'research_context': research, 'published_at': '2026-09-20T00:00:00Z',
            'content_sha256': hashlib.sha256((system + '\n\n' + research).encode()).hexdigest()}


class PromptLoadingTest(unittest.TestCase):
    def test_reads_each_request_so_warm_lambda_sees_publication(self):
        database = Mock()
        database.get.side_effect = [[record()], [record('two')]]
        self.assertEqual(load_active_prompt(database).text, 'System one\n\nResearch one α')
        self.assertEqual(load_active_prompt(database).version, 'two')
        self.assertEqual(database.get.call_count, 2)

    def test_missing_duplicate_unpublished_and_tampered_records_fail_closed(self):
        invalid = record()
        invalid['research_context'] = 'changed without matching hash'
        for rows in ([], [record(), record()], [dict(record(), published_at=None)], [invalid], [dict(record(), system_prompt='')]):
            with self.subTest(rows=rows), self.assertRaises(PromptUnavailable):
                load_active_prompt(Mock(get=Mock(return_value=rows)))

    def test_bootstrap_is_explicit_and_does_not_replace_an_existing_active_version(self):
        db = Mock()
        db.get.side_effect = [[{'active_version_id': None}], [record()]]
        prompt, previous = evaluation_snapshot(db, bootstrap_if_empty=True)
        self.assertIsNone(previous)
        self.assertEqual(prompt.version, 'one')
        db.get.side_effect = [[{'active_version_id': record()['id']}], [record()]]
        prompt, previous = evaluation_snapshot(db, bootstrap_if_empty=True)
        self.assertEqual(previous, prompt.id)
        db.get.side_effect = [[{'active_version_id': None}]]
        with self.assertRaisesRegex(RuntimeError, 'No active prompt'):
            evaluation_snapshot(db)

    def test_publication_passes_evaluated_identity_hash_and_expected_pointer(self):
        db = Mock()
        prompt = PromptVersion.from_record(record())
        report = {'cases': []}
        publish_evaluated_prompt(db, prompt, None, report, 'researcher')
        payload = db.rpc.call_args.args[1]
        self.assertEqual(payload['p_expected_content_sha256'], prompt.content_sha256)
        self.assertEqual(payload['p_version_id'], prompt.id)
        self.assertIsNone(payload['p_expected_active_version_id'])
        self.assertIs(payload['p_report'], report)

    def test_grader_receives_the_same_research_snapshot_without_candidate_system_instructions(self):
        prompt = PromptVersion.from_record(record())
        case = {'rubric': 'independent evaluation criteria', 'summary': {'topology': 'single-bottleneck'}}
        payload = grading_payload(case, prompt, 'candidate answer')
        self.assertEqual(payload['research_context'], prompt.research_context)
        self.assertEqual(payload['metrics'], case['summary'])
        self.assertEqual(payload['rubric'], case['rubric'])
        self.assertNotIn(prompt.system_prompt, json.dumps(payload))


class HandlerPromptTest(unittest.TestCase):
    def setUp(self):
        modules = {name: types.ModuleType(name) for name in ('strands', 'strands.models', 'strands.models.bedrock', 'database', 'tools')}
        self.agent = Mock(messages=[{'role': 'assistant', 'content': [{'text': 'answer'}]}], return_value='answer')
        self.agent_factory = Mock(return_value=self.agent)
        modules['strands'].Agent = self.agent_factory
        modules['strands.models.bedrock'].BedrockModel = Mock()
        self.db = Mock()
        modules['database'].Database = Mock(return_value=self.db)
        modules['tools'].ALL_TOOLS = []
        spec = importlib.util.spec_from_file_location('handler_prompt_test', ROOT / 'agent/handler.py')
        self.handler = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.handler)
        self.db.get.side_effect = [[record()], []]
        self.request = {'body': json.dumps({'message': 'Explain run 2352', 'session_id': '00000000-0000-4000-8000-000000000003', 'user_id': 'researcher'})}

    def test_answer_uses_and_records_one_snapshot_without_rereading_active_version(self):
        result = self.handler.lambda_handler(self.request, None)
        self.assertEqual(result['statusCode'], 200)
        response = json.loads(result['body'])
        self.assertEqual(self.agent_factory.call_args.kwargs['system_prompt'], PromptVersion.from_record(record()).text)
        self.assertEqual(response['prompt_version_id'], record()['id'])
        name, payload = self.db.rpc.call_args.args
        self.assertEqual(name, 'save_agent_turn')
        self.assertEqual(payload['p_prompt_version_id'], response['prompt_version_id'])
        self.assertEqual(payload['p_answer_id'], response['answer_id'])
        self.assertEqual(payload['p_response'], 'answer')
        self.assertEqual(payload['p_messages'], self.agent.messages)
        self.assertEqual(self.db.get.call_count, 2)

    def test_loads_existing_history_with_current_prompt(self):
        history = [{'role': 'user', 'content': [{'text': 'prior question'}]}]
        self.db.get.side_effect = [[record('new')], [{'messages': history}]]
        self.handler.lambda_handler(self.request, None)
        self.assertEqual(self.agent.messages, history)
        self.assertIn('System new', self.agent_factory.call_args.kwargs['system_prompt'])

    def test_database_error_or_missing_prompt_does_not_call_model(self):
        for error in (RuntimeError('secret request detail'), None):
            self.db.get.side_effect = error
            self.db.get.return_value = []
            result = self.handler.lambda_handler(self.request, None)
            self.assertEqual(result['statusCode'], 503)
            self.assertNotIn('secret', result['body'])
            self.agent_factory.assert_not_called()

    def test_failed_save_is_reported_and_does_not_claim_success(self):
        self.db.rpc.side_effect = RuntimeError('sensitive detail')
        result = self.handler.lambda_handler(self.request, None)
        self.assertEqual(result['statusCode'], 503)
        self.assertNotIn('sensitive', result['body'])
        self.assertNotIn('response', json.loads(result['body']))

    def test_invalid_session_or_nontext_request_does_not_query_database(self):
        for body in ({'message': 'hi', 'session_id': 'bad'}, {'message': {}}, []):
            result = self.handler.lambda_handler({'body': json.dumps(body)}, None)
            self.assertEqual(result['statusCode'], 400)
        self.db.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
