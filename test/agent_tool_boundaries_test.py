"""Agent data adapters against synthetic HTTP, secrets and public study rows."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))


def load(name, dependencies):
    path = ROOT / 'agent' / name
    spec = importlib.util.spec_from_file_location('agent_boundaries_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, dependencies):
        spec.loader.exec_module(module)
    return module


class AgentToolBoundaries(unittest.TestCase):
    def setUp(self):
        self.http = types.ModuleType('httpx')
        self.response = Mock()
        self.response.json.return_value = {'recorded': True}
        for name in ['get', 'post', 'delete']:
            setattr(self.http, name, Mock(return_value=self.response))
        self.boto = types.ModuleType('boto3')
        self.secrets = Mock()
        self.secrets.get_secret_value.return_value = {'SecretString': 'synthetic-service-key'}
        self.boto.client = Mock(return_value=self.secrets)
        self.strands = types.ModuleType('strands')
        self.strands.tool = lambda fn=None, **_options: fn if fn else lambda value: value
        self.strands.ToolContext = object
        self.dependencies = {'httpx': self.http, 'boto3': self.boto, 'strands': self.strands}
        self.enterContext(patch.dict(os.environ, SUPABASE_URL='https://synthetic.example.test',
            SUPABASE_SECRET_ARN='synthetic-secret-arn', BENCHMARK_API_URL='https://api.example.test'))
        self.config = load('tools/config.py', self.dependencies)
        self.query = load('tools/query.py', self.dependencies)
        self.benchmark = load('tools/benchmark.py', self.dependencies)
        self.database = load('database.py', self.dependencies)
        self.context = types.SimpleNamespace(invocation_state={'authorization': 'Bearer synthetic-user-session'})

    def test_secret_loaders_cache_only_after_a_confirmed_secret_response(self):
        with patch.dict(sys.modules, {'boto3': self.boto}):
            for module in [self.config, self.query, self.benchmark]:
                with self.subTest(module=module.__name__):
                    self.assertEqual(module._get_supabase_key(), 'synthetic-service-key')
                    self.assertEqual(module._get_supabase_key(), 'synthetic-service-key')
            self.assertEqual(self.secrets.get_secret_value.call_count, 3)
            self.secrets.get_secret_value.assert_called_with(SecretId='synthetic-secret-arn')
            self.config._supabase_key = None
            failure = TimeoutError('Synthetic secret retrieval unconfirmed')
            self.secrets.get_secret_value.side_effect = failure
            with self.assertRaises(TimeoutError) as caught:
                self.config._get_supabase_key()
            self.assertIs(caught.exception, failure)
            self.assertIsNone(self.config._supabase_key)

    def test_database_requires_https_and_passes_exact_query_rpc_and_credential_boundaries(self):
        for url in ['', 'http://example.test', 'file:///private', 'postgresql://localhost/test']:
            with self.subTest(url=url), patch.dict(os.environ, SUPABASE_URL=''), self.assertRaises(ValueError):
                self.database.Database(url)
        database = self.database.Database('https://synthetic.example.test///')
        self.assertEqual(database.url, 'https://synthetic.example.test')
        self.assertEqual(database.get('public_results', {'id': 'eq.original'}), {'recorded': True})
        self.assertEqual(database.rpc('owner_action', {'request_id': 'original'}), {'recorded': True})
        headers = {'apikey': 'synthetic-service-key', 'Authorization': 'Bearer synthetic-service-key'}
        self.http.get.assert_called_once_with('https://synthetic.example.test/rest/v1/public_results', params={'id': 'eq.original'}, headers=headers, timeout=15)
        self.http.post.assert_called_once_with('https://synthetic.example.test/rest/v1/rpc/owner_action', json={'request_id': 'original'}, headers=headers, timeout=15)
        self.boto.client.assert_called_once_with('secretsmanager', region_name='us-east-1')
        with patch.dict(os.environ, {}, clear=True):
            self.database._service_key = None
            self.database.Database('https://synthetic.example.test').headers()
        self.secrets.get_secret_value.assert_called_with(SecretId='jumpserve/supabase-service-key')

    def test_database_http_failures_are_not_parsed_as_successful_data(self):
        self.database._service_key = 'synthetic-cached-key'
        failure = RuntimeError('Synthetic HTTP rejection')
        self.response.raise_for_status.side_effect = failure
        database = self.database.Database()
        for operation in [lambda: database.get('results'), lambda: database.rpc('action', {})]:
            with self.assertRaises(RuntimeError) as caught:
                operation()
            self.assertIs(caught.exception, failure)
        self.response.json.assert_not_called()

    def test_saved_config_list_save_delete_and_prepare_use_the_original_configuration(self):
        self.config._supabase_key = 'synthetic-cached-key'
        original = {'num_clients': 2, 'client_delays_ms': [0, 20], 'unknown': None}
        row = {'id': 'original-config', 'name': 'Retained config', 'description': 'Recorded settings', 'config': original}
        self.response.json.return_value = [row]
        self.assertEqual(self.config.list_configs(), [row])
        self.assertEqual(self.config.save_config(row['name'], row['description'], original), row)
        self.assertEqual(self.http.post.call_args.kwargs['json'], {key: row[key] for key in ['name', 'description', 'config']})
        self.assertEqual(self.http.post.call_args.kwargs['headers']['Prefer'], 'return=representation')
        self.assertEqual(self.config.run_saved_config('original-config'), {'status': 'ready_to_launch', **{key: row[key] for key in ['name', 'description', 'config']}})
        self.assertEqual(self.http.get.call_args.args[0], 'https://synthetic.example.test/rest/v1/benchmark_configs?id=eq.original-config&select=*')
        self.assertEqual(self.config.delete_config('original-config'), {'status': 'deleted', 'id': 'original-config'})
        self.assertEqual(self.http.delete.call_args.args[0], 'https://synthetic.example.test/rest/v1/benchmark_configs?id=eq.original-config')
        self.response.json.return_value = []
        self.assertEqual(self.config.save_config('name', 'description', {}), {'status': 'saved'})
        self.assertEqual(self.config.run_saved_config('missing'), {'error': 'Config not found'})
        self.assertEqual(original, {'num_clients': 2, 'client_delays_ms': [0, 20], 'unknown': None})

    def test_saved_config_and_query_http_rejections_stop_before_reading_a_payload(self):
        failure = RuntimeError('Synthetic storage rejection')
        self.response.raise_for_status.side_effect = failure
        self.config._supabase_key = self.query._supabase_key = 'synthetic-cached-key'
        for operation in [self.config.list_configs, lambda: self.config.save_config('name', 'description', {}),
                          lambda: self.config.delete_config('original'), lambda: self.config.run_saved_config('original'),
                          lambda: self.query._supabase_get('public_results')]:
            with self.assertRaises(RuntimeError) as caught:
                operation()
            self.assertIs(caught.exception, failure)
        self.response.json.assert_not_called()

    def test_job_listing_summarizes_recorded_configs_and_retains_empty_or_missing_configs(self):
        self.query._supabase_key = 'synthetic-cached-key'
        rows = [{'id': 'configured', 'config': {'num_clients': 2, 'client_ccas': ['cubic', 'bbr'], 'client_delays_ms': [0, 20], 'bottleneck_all_client_rate_mbit': 100, 'bottleneck_buffer_kbytes': 125}}, {'id': 'empty', 'config': {}}, {'id': 'missing'}]
        self.response.json.return_value = rows
        result = self.query.list_jobs(3, 'completed')
        self.assertEqual(result[0]['config_summary'], '2 clients, CCAs: cubic,bbr, delays: [0, 20]ms, rate: 100 Mbit, buffer: 125 KB')
        self.assertNotIn('config_summary', result[1]); self.assertNotIn('config_summary', result[2])
        params = parse_qs(urlsplit(self.http.get.call_args.args[0]).query)
        self.assertEqual(params['limit'], ['3']); self.assertEqual(params['status'], ['eq.completed'])
        self.response.json.return_value = []
        self.assertEqual(self.query.list_jobs(), [])
        self.assertNotIn('status=', self.http.get.call_args.args[0])
        self.assertEqual(self.query.get_job_status('missing'), {'error': 'Job not found'})
        self.response.json.return_value = [{'id': 'original-job', 'status': 'running'}]
        self.assertEqual(self.query.get_job_status('original-job'), {'id': 'original-job', 'status': 'running'})
        self.response.json.return_value = []
        self.assertEqual(self.query.get_run_results(123), {'error': 'Parent run not found'})

    def test_search_propagates_only_the_requested_parent_configuration_filters(self):
        with patch.object(self.query, '_supabase_get', return_value=[]) as read:
            self.assertEqual(self.query.search_runs(), [])
            defaults = parse_qs(urlsplit(read.call_args.args[0]).query)
            self.assertEqual(defaults['limit'], ['10'])
            self.query.search_runs(num_clients=2, min_rate_mbit=50, max_rate_mbit=100, tag='paired', experiment_name='original', limit=5)
            params = parse_qs(urlsplit(read.call_args.args[0]).query)
        self.assertEqual(params['number_of_clients'], ['eq.2'])
        self.assertEqual(params['bottleneck_rate_megabit'], ['gte.50', 'lte.100'])
        self.assertEqual(params['tags'], ['cs.{paired}'])
        self.assertEqual(params['experiment_name'], ['ilike.*original*'])
        self.assertEqual(params['limit'], ['5'])

    def test_benchmark_actions_use_request_auth_and_preserve_optional_fields(self):
        inputs = dict(num_clients=2, client_ccas=['cubic', 'bbr'], client_delays_ms=[0, 20], client_file_sizes_mbytes=[1, 2], bottleneck_rate_mbit=100, buffer_size_kbytes=125)
        self.assertEqual(self.benchmark.run_benchmark(self.context, **inputs, loss_pct=1, experiment_name='original', tags=['paired'], notes='retained', client_start_delays_ms=[0, 25]), {'recorded': True})
        config = self.http.post.call_args.kwargs['json']['config']
        self.assertEqual(config['client_start_delays_ms'], [0, 25]); self.assertEqual(config['loss_pct'], 1)
        self.assertEqual(config['experiment_name'], 'original'); self.assertEqual(config['tags'], ['paired']); self.assertEqual(config['notes'], 'retained')
        self.assertEqual(self.http.post.call_args.kwargs['headers'], {'Authorization': 'Bearer synthetic-user-session'})
        self.assertEqual(self.benchmark.cancel_benchmark('original-job', self.context), {'recorded': True})
        self.http.post.assert_called_with('https://api.example.test/benchmarks/cancel', headers={'Authorization': 'Bearer synthetic-user-session'}, json={'jobId': 'original-job'}, timeout=15)
        self.http.post.reset_mock()
        unauthenticated = types.SimpleNamespace(invocation_state={})
        self.assertIn('Sign in', self.benchmark.run_benchmark(unauthenticated, **inputs)['error'])
        self.assertIn('Sign in', self.benchmark.cancel_benchmark('original-job', unauthenticated)['error'])
        self.http.post.assert_not_called()

    def test_benchmark_logs_keep_original_line_count_and_only_the_last_fifty_events(self):
        for events in [[], [{'message': str(i)} for i in range(3)], [{'message': str(i)} for i in range(60)]]:
            self.response.json.return_value = {'events': events}
            result = self.benchmark.get_benchmark_logs('original-job')
            self.assertEqual(result, {'events': events[-50:], 'total_lines': len(events)})
        self.response.json.return_value = {}
        self.assertEqual(self.benchmark.get_benchmark_logs('original-job'), {'events': [], 'total_lines': 0})


class StudyReaderBoundaries(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        strands = types.ModuleType('strands'); strands.tool = lambda fn: fn
        database = types.ModuleType('database'); database.Database = Mock(return_value=self.db)
        self.modules = {family: load('tools/' + family + '_study.py', {'strands': strands, 'database': database}) for family in ['ipv6', 'reliable', 'http2', 'leo']}

    def test_ipv6_and_reliable_results_preserve_missing_metadata_and_bounded_configuration_catalogues(self):
        for family in ['ipv6', 'reliable']:
            module = self.modules[family]; read = getattr(module, 'get_' + family + '_study_results')
            self.db.get.reset_mock(); self.db.get.side_effect = [[]]
            self.assertEqual(read()['status'], 'unavailable'); self.assertEqual(self.db.get.call_count, 1)
            replies = [[{'analysis_version': 'retained-v1'}]]
            if family == 'reliable': replies += [[{'id': 'main'}, {'id': 'followup'}]]
            replies += [[{'id': 'claim'}], [{'id': 'original-config'}]]
            self.db.get.side_effect = replies
            result = read()
            self.assertEqual(result['status'], 'recorded'); self.assertEqual(result['configuration_ids'], ['original-config'])
            self.assertEqual(result['meta'], {'analysis_version': 'retained-v1'})
            self.assertTrue(all(call.args[0].startswith(family + '_study_') for call in self.db.get.call_args_list))
            self.assertTrue(all(call.kwargs['params']['limit'] <= 144 for call in self.db.get.call_args_list))

    def test_configuration_ids_are_bounded_before_database_reads_and_missing_summaries_remain_unavailable(self):
        for family, bound in [('ipv6', 100), ('reliable', 90)]:
            read = getattr(self.modules[family], 'get_' + family + '_configuration')
            self.db.get.reset_mock()
            for identifier in [None, 1, '', '../private', 'id&select=*', 'x' * (bound + 1)]:
                with self.subTest(family=family, identifier=identifier), self.assertRaises(ValueError): read(identifier)
            self.db.get.assert_not_called()
            for configs, summaries in [([], []), ([{'id': 'original'}], []), ([], [{'retained': True}]), ([{'id': 'original'}], [{'retained': True}])]:
                self.db.get.side_effect = [configs, summaries] + ([[]] if family == 'reliable' else [])
                result = read('original')
                self.assertEqual(result['status'], 'recorded' if configs and summaries else 'unavailable')
                self.assertEqual(result['configuration'], configs[0] if configs else None)

    def test_literature_pagination_preserves_all_review_counts_and_explicit_reference_zero(self):
        rows = [{'reference_number': i, 'review_status': 'complete' if i == 0 else 'partial', 'access_status': 'retrieved'} for i in range(12)]
        for family, maximum, direct in [('ipv6', 73, 72), ('reliable', 46, 45)]:
            read = getattr(self.modules[family], 'get_' + family + '_literature')
            for kwargs in [{}, {'offset': 10}, {'reference_number': 0}, {'reference_number': maximum}]:
                self.db.get.side_effect = [copy.deepcopy(rows), [rows[0]]]
                result = read(**kwargs)
                self.assertEqual(result['total_source_records'], 12); self.assertEqual(result['direct_references'], direct)
                self.assertEqual(result['review_counts'], {'complete': 1, 'partial': 11})
                self.assertEqual(result['access_counts'], {'retrieved': 12})
                self.assertEqual(result['next_offset'], 10 if kwargs == {} else None)
                if 'reference_number' in kwargs:
                    self.assertEqual(self.db.get.call_args.kwargs['params']['reference_number'], 'eq.' + str(kwargs['reference_number']))
                    self.assertEqual(self.db.get.call_args.kwargs['params']['offset'], 0)
            self.db.get.reset_mock()
            for kwargs in [{'offset': -1}, {'offset': maximum + 1}, {'offset': True}, {'limit': 0}, {'limit': 11}, {'limit': '1'}, {'reference_number': True}, {'reference_number': '1'}, {'reference_number': -1}, {'reference_number': maximum + 1}]:
                with self.subTest(family=family, kwargs=kwargs), self.assertRaises(ValueError): read(**kwargs)
            self.db.get.assert_not_called()

    def test_http2_configuration_pages_have_a_sentinel_row_and_keep_missing_runs_unavailable(self):
        module = self.modules['http2']
        for configs, runs in [([], []), ([{'id': 'original'}], [])]:
            self.db.get.side_effect = [configs, runs]
            self.assertEqual(module.get_http2_configuration('original')['status'], 'unavailable')
        for count in [1, 2]:
            self.db.get.side_effect = [[{'id': 'original'}], [{'id': 'original-run'}], [{'test_id': i + 1} for i in range(count)]]
            result = module.get_http2_configuration('original', offset=50, limit=1)
            self.assertEqual(result['measurements'], [{'test_id': 1}])
            self.assertEqual(result['next_offset'], 51 if count == 2 else None)
            params = self.db.get.call_args.kwargs['params']
            self.assertEqual(params['offset'], 50); self.assertEqual(params['limit'], 2)
            self.assertEqual(params['run_id'], 'eq.original-run')

    def test_http2_projection_excludes_large_provenance_and_retains_unavailable_campaign(self):
        module = self.modules['http2']; self.db.get.side_effect = [[]]
        self.assertEqual(module.get_http2_study_results()['status'], 'unavailable')
        self.db.get.side_effect = [[{'id': module.CAMPAIGN, 'provenance': {'analysis_version': 'original-v1', 'source_inventory_sha256': 'a' * 64, 'private_unbounded_vector': 'x' * 10000}}], [], [], []]
        result = module.get_http2_study_results()
        self.assertEqual(result['campaign']['provenance'], {'analysis_version': 'original-v1', 'source_inventory_sha256': 'a' * 64})
        self.assertNotIn('private_unbounded_vector', json.dumps(result))
        self.assertTrue(all(call.args[0].startswith('http2_study_') for call in self.db.get.call_args_list))

    def test_leo_missing_initial_and_saturation_campaigns_are_not_filled_with_other_measurements(self):
        module = self.modules['leo']; self.db.get.side_effect = [[]]
        self.assertEqual(module.get_leo_study_results()['status'], 'unavailable')
        self.db.get.side_effect = [[{'id': module.CAMPAIGN}], [], [{'country': 'haiti', 'mean_gbps': 0}], []]
        result = module.get_leo_study_results('haiti')
        self.assertEqual(result['summaries'], [{'country': 'haiti', 'mean_gbps': 0}])
        self.assertEqual(result['saturation_followup'], {'status': 'unavailable'})
        with self.assertRaisesRegex(ValueError, 'country is required'): module.get_leo_scenarios(None)

    def test_leo_saturation_results_retain_a_separate_campaign_and_country_filter(self):
        module = self.modules['leo']
        self.db.get.side_effect = [[{'id': module.CAMPAIGN}], [], [{'mean_gbps': 1}], [{'id': module.SATURATION_CAMPAIGN}], [{'mean_gbps': 2}]]
        result = module.get_leo_study_results('haiti')
        self.assertEqual(result['summaries'], [{'mean_gbps': 1}])
        self.assertEqual(result['saturation_followup']['summaries'], [{'mean_gbps': 2}])
        self.assertEqual(self.db.get.call_args.kwargs['params']['country'], 'eq.haiti')
        self.assertEqual(self.db.get.call_args.kwargs['params']['campaign_id'], 'eq.' + module.SATURATION_CAMPAIGN)

    def test_http2_literature_preserves_reference_zero_and_review_counts(self):
        module = self.modules['http2']
        self.db.get.side_effect = None
        self.db.get.return_value = [{'reference_number': 0, 'review_status': 'partial'}]
        result = module.get_http2_literature(0)
        self.assertEqual(result['review_counts'], {'partial': 1})
        self.assertEqual(result['returned_source_count'], 1)
        self.assertEqual(self.db.get.call_args.kwargs['params']['reference_number'], 'eq.0')
        self.db.get.return_value = []
        self.assertEqual(module.get_http2_literature()['returned_source_count'], 0)
        for value in [-1, 49, True, '0']:
            with self.assertRaises(ValueError): module.get_http2_literature(value)

    def test_tool_catalogue_keeps_study_modules_read_only_and_launch_tools_emulated_only(self):
        dependencies = {}
        groups = {
            'benchmark': ['run_benchmark', 'cancel_benchmark', 'get_benchmark_logs'],
            'query': ['list_jobs', 'get_job_status', 'get_run_results', 'compare_runs', 'search_runs'],
            'config': ['list_configs', 'save_config', 'delete_config', 'run_saved_config'],
            'real_world': ['search_real_world_tests', 'get_real_world_results', 'get_real_world_trace', 'compare_real_world_tests'],
            'leo_study': ['get_leo_study_results', 'get_leo_scenarios', 'get_leo_literature'],
            'http2_study': ['get_http2_study_results', 'get_http2_configuration', 'get_http2_literature'],
            'ipv6_study': ['get_ipv6_study_results', 'get_ipv6_configuration', 'get_ipv6_literature'],
            'reliable_study': ['get_reliable_study_results', 'get_reliable_configuration', 'get_reliable_literature'],
        }
        for group, names in groups.items():
            module = types.ModuleType('tools.' + group)
            for name in names: setattr(module, name, Mock(name=name))
            dependencies[module.__name__] = module
        catalogue = load('tools/__init__.py', dependencies)
        self.assertEqual(len(catalogue.ALL_TOOLS), 12)
        self.assertEqual(set(catalogue.MODULE_TOOLS), {'congestion-control-emulated', 'congestion-control-real-world', 'leo-emergency-failover', 'http2-compliance-study', 'ipv6-dns-study', 'reliable-sketch-study'})
        launch = dependencies['tools.benchmark'].run_benchmark
        cancel = dependencies['tools.benchmark'].cancel_benchmark
        self.assertIn(launch, catalogue.MODULE_TOOLS['congestion-control-emulated'])
        for module, tools in catalogue.MODULE_TOOLS.items():
            if module != 'congestion-control-emulated':
                self.assertNotIn(launch, tools); self.assertNotIn(cancel, tools)


if __name__ == '__main__':
    unittest.main()
