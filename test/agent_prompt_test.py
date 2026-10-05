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
from modules import EMULATED_MODULE, REAL_WORLD_MODULE, LEO_MODULE, HTTP2_MODULE


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
        modules = {name: types.ModuleType(name) for name in ('strands', 'strands.models', 'strands.models.bedrock', 'database', 'tools', 'httpx')}
        self.agent = Mock(messages=[{'role': 'assistant', 'content': [{'text': 'answer'}]}], return_value='answer')
        self.agent_factory = Mock(return_value=self.agent)
        modules['strands'].Agent = self.agent_factory
        modules['strands.models.bedrock'].BedrockModel = Mock()
        self.db = Mock()
        modules['database'].Database = Mock(return_value=self.db)
        modules['tools'].MODULE_TOOLS = {EMULATED_MODULE: ['emulated-tool'], REAL_WORLD_MODULE: ['real-world-tool'], LEO_MODULE: ['leo-read-tool'], HTTP2_MODULE: ['http2-read-tool']}
        spec = importlib.util.spec_from_file_location('handler_prompt_test', ROOT / 'agent/handler.py')
        self.handler = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.handler)
        self.auth_patch = patch.object(self.handler, 'authenticate', return_value=({'id': 'verified-id', 'email': 'researcher'}, 'Bearer verified-session'))
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.snapshot_patch=patch.object(self.handler,'_http2_evidence',return_value={'status':'fixture'})
        self.snapshot_patch.start();self.addCleanup(self.snapshot_patch.stop)
        self.db.get.side_effect = [[record()], []]
        self.request = {'body': json.dumps({'message': 'Explain run 2352', 'session_id': '00000000-0000-4000-8000-000000000003', 'user_id': 'forged-owner'})}

    def test_reliable_history_persistence_and_server_selected_renderer(self):
        module='reliable-sketch-study'
        prompt=dict(record(),module_id=module)
        history=[{'role':'user','content':[{'text':'old question'}]}, {'role':'assistant','content':[{'text':'old answer'}]}]
        self.db.get.side_effect=[[prompt],[{'messages':history,'user_id':'researcher','module_id':module}]]
        self.request['body']=json.dumps({'message':'memory','module_id':module})
        from reliable_answers import ReliableAnswerPlan
        self.agent.return_value=types.SimpleNamespace(structured_output=ReliableAnswerPlan(topics=['memory']))
        with patch.object(self.handler,'reliable_hooks',return_value={}), patch.object(self.handler,'get_reliable_evidence',return_value={'meta':{'analysis_version':'reliable-assessment-v1','assessment_sha256':'a'},'claims':[]}), patch.object(self.handler,'render_reliable_evidence',return_value=('recorded memory', [{'name':'get_reliable_study_results','input':{}}])):
            result=self.handler.lambda_handler(self.request,None)
        self.assertEqual(result['statusCode'],200)
        self.assertEqual(self.agent_factory.call_args.kwargs['tools'],[])
        messages=self.db.rpc.call_args.args[1]['p_messages']
        self.assertEqual(messages[:2],history)
        self.assertEqual(sum(m==history[0] for m in messages),1)
        self.assertEqual(messages[-1]['content'][0]['text'],'recorded memory')
        self.assertEqual(self.db.rpc.call_args.args[1]['p_analysis_version'],'reliable-assessment-v1')

    def test_answer_uses_and_records_one_snapshot_without_rereading_active_version(self):
        result = self.handler.lambda_handler(self.request, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(self.handler.BedrockModel.call_args.kwargs['temperature'], 0)
        response = json.loads(result['body'])
        self.assertEqual(self.agent_factory.call_args.kwargs['system_prompt'], PromptVersion.from_record(record()).text)
        self.assertEqual(response['prompt_version_id'], record()['id'])
        name, payload = self.db.rpc.call_args.args
        self.assertEqual(name, 'save_agent_turn')
        self.assertEqual(payload['p_prompt_version_id'], response['prompt_version_id'])
        self.assertEqual(payload['p_answer_id'], response['answer_id'])
        self.assertEqual(payload['p_response'], 'answer')
        self.assertEqual(payload['p_user_id'], 'researcher')
        self.agent.assert_called_once_with('Explain run 2352', authorization='Bearer verified-session')
        self.assertEqual(payload['p_messages'], self.agent.messages)
        self.assertEqual(self.db.get.call_count, 2)

    def test_loads_existing_history_with_current_prompt(self):
        history = [{'role': 'user', 'content': [{'text': 'prior question'}]}]
        self.db.get.side_effect = [[record('new')], [{'messages': history, 'user_id': 'researcher'}]]
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

    def test_anonymous_request_never_reads_private_context_or_calls_model(self):
        with patch.object(self.handler, 'authenticate', side_effect=self.handler.AuthError(401, 'Sign in')):
            result = self.handler.lambda_handler(self.request, None)
        self.assertEqual(result['statusCode'], 401)
        self.db.get.assert_not_called()
        self.agent_factory.assert_not_called()

    def test_other_users_session_cannot_be_read_or_overwritten(self):
        self.db.get.side_effect = [[record()], [{'messages': [], 'user_id': 'another-user'}]]
        result = self.handler.lambda_handler(self.request, None)
        self.assertEqual(result['statusCode'], 403)
        self.agent_factory.assert_not_called()
        self.db.rpc.assert_not_called()

    def test_module_selects_prompt_tools_and_persisted_answer_identity(self):
        self.db.get.side_effect = [[dict(record(), module_id=REAL_WORLD_MODULE)], []]
        self.request['body'] = json.dumps({'message': 'Explain this EC2 test', 'module_id': REAL_WORLD_MODULE})
        result = self.handler.lambda_handler(self.request, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(json.loads(result['body'])['module_id'], REAL_WORLD_MODULE)
        self.assertEqual(self.agent_factory.call_args.kwargs['tools'], ['real-world-tool'])
        self.assertEqual(self.db.get.call_args_list[0].kwargs['params'], {'p_module_id': REAL_WORLD_MODULE})
        self.assertEqual(self.db.rpc.call_args.args[1]['p_module_id'], REAL_WORLD_MODULE)
        self.assertEqual(self.db.rpc.call_args.args[1]['p_analysis_version'], 'real-world-chat-v1')

    def test_other_module_history_and_wrong_prompt_are_rejected_before_model(self):
        self.request['body'] = json.dumps({'message': 'Explain EC2 results', 'module_id': REAL_WORLD_MODULE})
        self.db.get.side_effect = [[dict(record(), module_id=REAL_WORLD_MODULE)], [{'messages': [], 'user_id': 'researcher', 'module_id': EMULATED_MODULE}]]
        self.assertEqual(self.handler.lambda_handler(self.request, None)['statusCode'], 409)
        self.db.get.side_effect = [[record()]]
        self.assertEqual(self.handler.lambda_handler(self.request, None)['statusCode'], 503)
        self.agent_factory.assert_not_called()
        self.db.rpc.assert_not_called()

    def test_leo_prompt_tools_audit_identity_and_history_are_server_owned(self):
        self.request['body']=json.dumps({'message':'Explain Haiti','module_id':LEO_MODULE})
        self.db.get.side_effect=[[dict(record(),module_id=LEO_MODULE)],[]]
        response=self.handler.lambda_handler(self.request,None)
        self.assertEqual(response['statusCode'],200)
        self.assertEqual(self.agent_factory.call_args.kwargs['tools'],['leo-read-tool'])
        self.assertEqual(self.db.rpc.call_args.args[1]['p_analysis_version'],'leo-failover-chat-v1')
        self.assertEqual(self.db.rpc.call_args.args[1]['p_module_id'],LEO_MODULE)
        self.agent_factory.reset_mock(); self.db.rpc.reset_mock()
        self.db.get.side_effect=[[dict(record(),module_id=LEO_MODULE)],[{'messages':[],'user_id':'researcher','module_id':REAL_WORLD_MODULE}]]
        self.assertEqual(self.handler.lambda_handler(self.request,None)['statusCode'],409)
        self.agent_factory.assert_not_called(); self.db.rpc.assert_not_called()

    def test_unknown_modules_are_not_prompt_or_tool_selectors(self):
        for module in ('arbitrary-prompt', None, {}, []):
            result = self.handler.lambda_handler({'body': json.dumps({'message': 'hi', 'module_id': module})}, None)
            self.assertEqual(result['statusCode'], 400)
        self.db.get.assert_not_called()
        self.agent_factory.assert_not_called()

    def test_http2_prompt_tools_provenance_and_cross_module_history(self):
        self.request['body'] = json.dumps({'message': 'Explain Figure8', 'module_id': HTTP2_MODULE})
        self.db.get.side_effect = [[dict(record(), module_id=HTTP2_MODULE)], []]
        self.agent.return_value=types.SimpleNamespace(structured_output={'topics':['discrepancy']})
        with patch.object(self.handler,'_render_http2_evidence',return_value='recorded evidence'):
            response = json.loads(self.handler.lambda_handler(self.request, None)['body'])
        self.assertEqual(self.agent_factory.call_args.kwargs['tools'], ['http2-read-tool'])
        self.assertEqual(self.handler.BedrockModel.call_args.kwargs['model_id'], 'us.anthropic.claude-sonnet-4-6')
        self.assertEqual(response['prompt_content_sha256'], record()['content_sha256'])
        self.assertEqual(response['analysis_version'], 'http2-assessment-v3')
        self.assertEqual(self.db.rpc.call_args.args[1]['p_module_id'], HTTP2_MODULE)
        self.assertEqual(response['answer_provenance']['plan']['topics'],['discrepancy'])
        self.assertEqual(self.db.rpc.call_args.args[1]['p_answer_provenance'],response['answer_provenance'])
        self.agent_factory.reset_mock(); self.db.rpc.reset_mock()
        self.db.get.side_effect = [[dict(record(), module_id=HTTP2_MODULE)], [{'user_id': 'researcher', 'module_id': LEO_MODULE, 'messages': []}]]
        self.assertEqual(self.handler.lambda_handler(self.request, None)['statusCode'], 409)
        self.agent_factory.assert_not_called(); self.db.rpc.assert_not_called()

    def test_model_usage_preserves_absence_and_records_actual_module_price(self):
        self.assertEqual(self.handler._usage('no-metrics',HTTP2_MODULE),(None,None,None))
        result=types.SimpleNamespace(metrics=types.SimpleNamespace(accumulated_usage={'inputTokens':1000,'outputTokens':100}))
        tokens,price,source=self.handler._usage(result,HTTP2_MODULE)
        self.assertEqual(tokens['inputTokens'],1000)
        self.assertAlmostEqual(price,0.00495)
        self.assertEqual(source['input_usd_per_million'],3.3)

    def test_http2_failed_model_call_is_saved_without_inventing_usage(self):
        self.request['body']=json.dumps({'message':'Explain the study','module_id':HTTP2_MODULE})
        self.db.get.side_effect=[[dict(record(),module_id=HTTP2_MODULE)],[]]
        self.agent.side_effect=RuntimeError('sensitive model details')
        response=self.handler.lambda_handler(self.request,None)
        self.assertEqual(response['statusCode'],503)
        self.assertNotIn('sensitive',response['body'])
        payload=self.db.rpc.call_args.args[1]
        self.assertEqual(payload['p_answer_provenance']['status'],'failed')
        self.assertEqual(payload['p_answer_provenance']['reason'],'RuntimeError')
        self.assertIsNone(payload['p_model_usage']);self.assertIsNone(payload['p_estimated_model_cost_usd'])

    def test_capability_probe_is_authenticated_and_never_calls_model_or_database(self):
        request = {'body': json.dumps({'action': 'capabilities', 'module_id': REAL_WORLD_MODULE})}
        result = self.handler.lambda_handler(request, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertIn(REAL_WORLD_MODULE, json.loads(result['body'])['modules'])
        with patch.object(self.handler, 'authenticate', side_effect=self.handler.AuthError(401, 'Sign in')):
            self.assertEqual(self.handler.lambda_handler(request, None)['statusCode'], 401)
        self.db.get.assert_not_called()
        self.agent_factory.assert_not_called()

    def test_tool_badges_contain_current_turn_strands_calls_only(self):
        self.agent.messages = [{'role': 'assistant', 'content': [{'toolUse': {'name': 'old', 'input': {}}}]}]
        def answer(*args, **kwargs):
            self.agent.messages.extend([{'role': 'assistant', 'content': [{'toolUse': {'name': 'get_real_world_results', 'input': {'job_id': 'test'}}}]}])
            return 'answer'
        self.agent.side_effect = answer
        result = json.loads(self.handler.lambda_handler(self.request, None)['body'])
        self.assertEqual([event['name'] for event in result['tool_events']], ['get_real_world_results'])


if __name__ == '__main__':
    unittest.main()
