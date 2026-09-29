import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from real_world_analysis import compare_reports, summarize_report
from real_world_agent_cases import fixture, FIRST, SECOND, cases


class RealWorldAnalysisTest(unittest.TestCase):
    def summary(self, *args):
        report = fixture(*args)
        return summarize_report(report, report['job'])

    def test_summary_preserves_units_zero_and_missing_without_exposing_private_job_fields(self):
        report = fixture()
        report['job'].update(owner='private-email', nodes=[{'name': 'server', 'private_key': 'secret', 'public_ip': '192.0.2.1'}])
        report['receivers'][0]['retransmits'] = None
        result = summarize_report(report, report['job'])
        self.assertEqual(result['summary']['combined_mean_mbit_per_second'], 25)
        self.assertEqual(result['receivers'][1]['rtt']['median'], 78)
        self.assertEqual(result['summary']['queue_delay']['median'], 1.6)
        self.assertEqual(result['summary']['observed_queue_drops'], 0)
        self.assertIsNone(result['receivers'][0]['retransmits'])
        self.assertNotIn('throughput', result['receivers'][0])
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('private-email', json.dumps(result))
        self.assertNotIn('192.0.2.1', json.dumps(result))

    def test_two_matched_tests_are_descriptive_and_not_paired_replicates(self):
        result = compare_reports([self.summary(), self.summary(SECOND, 'bbr', 30)], 'cubic', 'bbr', 'combined_mean_mbit_per_second')
        block = result['blocks'][0]
        self.assertEqual(result['matched_blocks'], 1)
        self.assertEqual(block['delta'], 5)
        self.assertIsNone(block['interval'])
        self.assertIsNone(block['baseline']['interval'])
        self.assertFalse(result['method']['paired'])

    def test_missing_and_stale_results_are_excluded_without_zero_imputation(self):
        missing = self.summary()
        missing['summary']['combined_mean_mbit_per_second'] = None
        raw = fixture(SECOND, 'bbr')
        current = dict(raw['job'], updated_at=2000)
        stale = summarize_report(raw, current)
        result = compare_reports([missing, stale], 'cubic', 'bbr', 'combined_mean_mbit_per_second')
        self.assertEqual(result['blocks'], [])
        self.assertEqual(len(result['excluded']), 2)
        self.assertEqual(stale['report_status'], 'stale')

    def test_matching_checks_configuration_and_software_instead_of_trusting_same_key(self):
        left, right = self.summary(), self.summary(SECOND, 'bbr')
        for field, value in [('rate_mbit', 200), ('duration_seconds', 60), ('buffer_kbytes', 500)]:
            other = copy.deepcopy(right)
            other['comparison']['configuration']['configuration'][field] = value
            result = compare_reports([left, other], 'cubic', 'bbr', 'combined_mean_mbit_per_second')
            self.assertEqual(result['matched_blocks'], 0)
            self.assertEqual(len(result['blocks']), 2)
        other = dict(right, analysis_version='changed')
        self.assertEqual(compare_reports([left, other], 'cubic', 'bbr', 'jain_fairness')['matched_blocks'], 0)

    def test_whole_test_bootstrap_threshold_duplicates_and_direction(self):
        reports = [self.summary(f'00000000-0000-4000-8000-{i:012d}', cca, 10 + i)
                   for cca, indices in [('cubic', range(1, 6)), ('bbr', range(6, 11))] for i in indices]
        result = compare_reports(reports + [reports[0]], 'cubic', 'bbr', 'combined_mean_mbit_per_second')
        block = result['blocks'][0]
        self.assertEqual(block['baseline']['count'], 5)
        self.assertEqual(block['comparison']['count'], 5)
        self.assertEqual(block['delta'], 5)
        self.assertEqual(len(result['excluded']), 1)
        self.assertLess(block['interval']['low'], 5)
        self.assertGreater(block['interval']['high'], 5)
        # Shared reference case from the TypeScript reporting implementation.
        self.assertEqual(block['baseline']['interval'], {'low': 11, 'high': 15})
        self.assertEqual(block['comparison']['interval'], {'low': 16, 'high': 20})
        self.assertEqual(block['interval'], {'low': 2, 'high': 8})
        repeated = compare_reports(list(reversed(reports)), 'cubic', 'bbr', 'combined_mean_mbit_per_second')
        self.assertEqual(repeated['blocks'], result['blocks'])
        sparse = compare_reports(reports[1:], 'cubic', 'bbr', 'combined_mean_mbit_per_second')
        self.assertIsNone(sparse['blocks'][0]['interval'])

    def test_evaluation_cases_cover_the_database_publication_contract(self):
        names = {case['name'] for case in cases()}
        self.assertEqual(len(names), 8)
        migration = (ROOT / 'database/202609290001_real_world_agent.sql').read_text()
        for name in names:
            self.assertIn("'" + name + "'", migration)


class RealWorldToolsTest(unittest.TestCase):
    def setUp(self):
        modules = {name: types.ModuleType(name) for name in ('strands', 'database')}
        modules['strands'].tool = lambda fn: fn
        self.db = Mock()
        modules['database'].Database = Mock(return_value=self.db)
        spec = importlib.util.spec_from_file_location('real_world_tools_test', ROOT / 'agent/tools/real_world.py')
        self.tools = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.tools)

    def serve(self, report=None):
        report = report or fixture()
        self.db.get.side_effect = [[{'record': report['job']}], [{'report': report}]]

    def test_results_use_only_public_relations_and_bounded_identifier_filter(self):
        self.serve()
        result = self.tools.get_real_world_results(FIRST)
        self.assertEqual(result['summary']['combined_mean_mbit_per_second'], 25)
        self.assertEqual([call.args[0] for call in self.db.get.call_args_list], ['real_world_runs', 'real_world_reports'])
        self.assertEqual(self.db.get.call_args.kwargs['params']['job_id'], f'eq.{FIRST}')

    def test_missing_report_is_explicit_and_queries_do_not_accept_injected_filters(self):
        self.db.get.side_effect = [[{'record': fixture()['job']}], []]
        self.assertEqual(self.tools.get_real_world_results(FIRST)['report_status'], 'unavailable')
        self.db.reset_mock()
        for identifier in ('2352', FIRST + '&select=*', '../agent_sessions'):
            with self.assertRaises(ValueError):
                self.tools.get_real_world_results(identifier)
        self.db.get.assert_not_called()

    def test_search_pagination_is_explicit_and_does_not_read_private_jobs(self):
        self.db.get.return_value = [{'record': fixture()['job']}, {'record': fixture(SECOND)['job']}]
        result = self.tools.search_real_world_tests(limit=1, cca='cubic')
        self.assertEqual(result['next_offset'], 1)
        self.assertEqual(len(result['tests']), 1)
        self.assertEqual(self.db.get.call_args.args[0], 'real_world_runs')
        for kwargs in ({'limit': 0}, {'limit': 26}, {'offset': -1}, {'status': 'completed&select=*'}):
            with self.assertRaises(ValueError):
                self.tools.search_real_world_tests(**kwargs)

    def test_trace_pages_preserve_zero_gaps_nulls_and_clock_definitions(self):
        self.serve()
        page = self.tools.get_real_world_trace(FIRST, 'throughput', 'receiver-1', limit=1)
        self.assertEqual(page['points'][0]['mbit_per_second'], 0)
        self.assertEqual(page['next_offset'], 1)
        self.assertEqual(page['total_points'], 2)
        self.serve()
        page = self.tools.get_real_world_trace(FIRST, 'throughput', 'receiver-1', offset=1)
        self.assertEqual(page['points'][0]['start'], 2)
        self.assertIn('receiver transfer', page['clock'])
        self.serve()
        page = self.tools.get_real_world_trace(FIRST, 'tcp', 'receiver-1')
        self.assertIsNone(page['points'][0]['rtt_ms'])
        self.assertEqual(page['points'][1]['rtt_ms'], 26)
        self.assertIn('scheduled start', page['clock'])

    def test_comparison_keeps_missing_ids_and_duplicate_exclusions(self):
        first = fixture()
        self.db.get.side_effect = [[{'record': first['job']}], [{'report': first}], []]
        result = self.tools.compare_real_world_tests([FIRST, FIRST, SECOND], 'cubic', 'bbr')
        self.assertEqual(len(result['excluded']), 2)
        self.assertEqual(self.db.get.call_count, 3)
        self.assertEqual(result['matched_blocks'], 0)


if __name__ == '__main__':
    unittest.main()
