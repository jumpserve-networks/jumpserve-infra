import copy
import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from run_analysis import summarize_run

FIXTURE = json.loads((ROOT / 'test/fixtures/run-2352.json').read_text())


class RunAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.fixture = copy.deepcopy(FIXTURE)

    def summary(self, **kwargs):
        return summarize_run(self.fixture['parent'], self.fixture['runs'], self.fixture['snapshots'], **kwargs)

    def test_2352_preserves_units_delay_semantics_and_measured_queue_estimates(self):
        result = self.summary()
        a, b = result['clients']
        self.assertEqual([a['configured_added_rtt_ms'], b['configured_added_rtt_ms']], [10, 60])
        self.assertFalse(result['measurement_contract']['delay_is_measured_unloaded_rtt'])
        self.assertEqual(result['measurement_contract']['delay_multiplier_for_added_rtt'], 1)
        self.assertIsNone(result['measurement_contract']['runner_revision'])
        self.assertAlmostEqual(a['metrics']['rtt']['mean'], 25.940244, places=5)
        self.assertAlmostEqual(b['metrics']['rtt']['mean'], 78.408948, places=5)
        self.assertAlmostEqual(b['metrics']['queue_delay']['mean'], 15.450375, places=5)
        self.assertIn('backlog_bytes', result['measurement_contract']['queue_delay_source'])
        self.assertEqual(b['metrics']['rtt']['zero_unavailable_samples'], 22)
        self.assertFalse(any(w['code'] == 'rtt_below_configured_added_delay' for w in result['warnings']))

    def test_2352_zero_throughput_is_valid_and_old_nonzero_means_are_explicit(self):
        result = self.summary()
        a, b = [client['metrics']['throughput'] for client in result['clients']]
        self.assertEqual(a['valid_samples'], 137)
        self.assertEqual(b['valid_samples'], 137)
        self.assertEqual(b['zero_samples'], 22)
        self.assertAlmostEqual(a['nonzero_sample_mean'], 23.301589, places=5)
        self.assertAlmostEqual(b['nonzero_sample_mean'], 26.879810, places=5)
        self.assertAlmostEqual(b['mean'], 22.563344, places=5)
        self.assertIn('different windows', b['nonzero_mean_scope'])
        self.assertTrue(result['fairness']['available'])
        self.assertIn('not isolated concurrent', result['fairness']['scope'])

    def test_numeric_strings_and_numbers_produce_identical_statistics(self):
        original = self.summary()
        for rows in self.fixture['snapshots'].values():
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, (int, float)):
                        row[key] = str(value)
        self.assertEqual(self.summary(), original)

    def test_missing_clients_and_samples_are_retained_without_fabricated_zeros(self):
        self.fixture['snapshots']['5089'] = []
        result = self.summary()
        self.assertEqual(len(result['clients']), 2)
        b = result['clients'][1]
        self.assertEqual(b['num_snapshots'], 0)
        for metric in b['metrics'].values():
            self.assertIsNone(metric['mean'])
            self.assertIsNone(metric['p95'])
        self.assertFalse(result['fairness']['available'])

    def test_invalid_and_negative_values_warn_without_clamping_or_contaminating_metrics(self):
        rows = self.fixture['snapshots']['5089']
        for row, value in zip(rows, [-41.6, 'NaN', 'Infinity', 'bad', None, True]):
            row['bottleneck_queuing_delay_ms'] = value
        rows[6]['round_trip_time_ms'] = 30
        result = self.summary()
        queue = result['clients'][1]['metrics']['queue_delay']
        self.assertEqual(queue['invalid_samples'], 5)
        self.assertEqual(queue['missing_samples'], 1)
        self.assertEqual(queue['valid_samples'], 131)
        self.assertTrue(any(w['code'] == 'invalid_measurement' for w in result['warnings']))
        self.assertTrue(any(w['code'] == 'rtt_below_configured_added_delay' for w in result['warnings']))
        json.dumps(result, allow_nan=False)

    def test_unknown_runner_does_not_inherit_delay_or_instrumentation_assumptions(self):
        result = self.summary(job_config={'script': 'unrecognized.py'})
        self.assertIsNone(result['clients'][1]['configured_added_rtt_ms'])
        self.assertIsNone(result['clients'][1]['metrics']['rtt']['mean'])
        self.assertTrue(any(w['code'] == 'unknown_delay_semantics' for w in result['warnings']))

    def test_multi_bottleneck_placeholder_zeros_are_unavailable(self):
        self.fixture['parent']['topology'] = 'dumbbell'
        for rows in self.fixture['snapshots'].values():
            for row in rows:
                for field in ('round_trip_time_ms', 'bottleneck_queuing_delay_ms', 'congestion_window_bytes', 'in_flight_packets'):
                    row[field] = 0
        result = self.summary(job_config={'script': 'netem_multi_bottleneck.py'})
        for client in result['clients']:
            for name in ('rtt', 'queue_delay', 'congestion_window', 'in_flight'):
                self.assertIsNone(client['metrics'][name]['mean'])
        self.assertFalse(result['fairness']['available'])

    def test_conflicting_runner_and_topology_are_flagged(self):
        result = self.summary(job_config={'script': 'netem_multi_bottleneck.py'})
        self.assertIsNone(result['clients'][0]['configured_added_rtt_ms'])
        self.assertIsNone(result['clients'][0]['metrics']['queue_delay']['mean'])
        self.assertTrue(any(w['code'] == 'conflicting_provenance' for w in result['warnings']))

    def test_zero_queue_delay_is_valid_for_an_instrumented_runner(self):
        for rows in self.fixture['snapshots'].values():
            for row in rows:
                row['bottleneck_queuing_delay_ms'] = 0
        metric = self.summary()['clients'][0]['metrics']['queue_delay']
        self.assertEqual(metric['mean'], 0)
        self.assertEqual(metric['valid_samples'], 137)

    def test_time_weighting_and_fairness_use_the_same_complete_intervals(self):
        rows = [
            {'snapshot_index': 1, 'elapsed_microseconds': 1_000_000, 'megabits_per_second': 10},
            {'snapshot_index': 2, 'elapsed_microseconds': 4_000_000, 'megabits_per_second': 30},
        ]
        self.fixture['snapshots'] = {str(run['id']): copy.deepcopy(rows) for run in self.fixture['runs']}
        result = self.summary()
        throughput = result['clients'][0]['metrics']['throughput']
        self.assertEqual(throughput['mean'], 20)
        self.assertEqual(throughput['time_weighted_mean'], 25)
        self.assertEqual(result['fairness']['jains_index'], 1)
        self.fixture['snapshots']['5089'][1]['elapsed_microseconds'] = 5_000_000
        self.assertFalse(self.summary()['fairness']['available'])

    def test_partial_missing_and_duplicate_timestamps_cannot_claim_full_run_fairness(self):
        self.assertFalse(self.summary(incomplete_run_ids=[5089])['fairness']['available'])
        for time in (None, 0, -1, 'NaN'):
            self.fixture['snapshots']['5089'][1]['elapsed_microseconds'] = time
            self.assertFalse(self.summary()['fairness']['available'])
        del self.fixture['runs'][1]
        self.assertFalse(self.summary()['fairness']['available'])


class QueryToolTest(unittest.TestCase):
    def setUp(self):
        httpx = types.ModuleType('httpx')
        strands = types.ModuleType('strands')
        strands.tool = lambda fn: fn
        spec = importlib.util.spec_from_file_location('query_test_target', ROOT / 'agent/tools/query.py')
        self.query = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'httpx': httpx, 'strands': strands}):
            spec.loader.exec_module(self.query)
        self.paths = []

    def read(self, path):
        self.paths.append(path)
        table = path.split('?')[0]
        query = parse_qs(urlsplit(path).query)
        if table == 'emulated_parent_runs':
            return [FIXTURE['parent']]
        if table == 'emulated_runs':
            return FIXTURE['runs']
        if table == 'benchmark_jobs':
            self.assertEqual(query['select'], ['config'])
            return [{'config': {'script': 'netem_cubic_benchmark_nines.py', 'snapshot_metrics_source': 'kernel'}}]
        if table == 'emulated_snapshot_stats':
            rows = FIXTURE['snapshots'][query['emulated_run_id'][0].removeprefix('eq.')]
            offset = int(query['offset'][0])
            # Simulate a server cap smaller than the requested page size.
            return rows[offset:offset + min(30, int(query['limit'][0]))]
        raise AssertionError(path)

    def test_paginated_results_keep_all_samples_and_provenance(self):
        with patch.object(self.query, '_supabase_get', side_effect=self.read):
            result = self.query.get_run_results(2352)
        self.assertEqual([client['num_snapshots'] for client in result['clients']], [137, 137])
        self.assertEqual(result['measurement_contract']['script'], 'netem_cubic_benchmark_nines.py')
        self.assertTrue(result['fairness']['available'])

    def test_safety_limit_marks_partial_data_instead_of_silently_truncating(self):
        with patch.object(self.query, '_supabase_get', side_effect=self.read), patch.object(self.query, 'MAX_SNAPSHOT_ROWS', 100):
            result = self.query.get_run_results(2352)
        self.assertEqual([client['num_snapshots'] for client in result['clients']], [100, 100])
        self.assertFalse(result['fairness']['available'])
        self.assertEqual(sum(w['code'] == 'incomplete_snapshots' for w in result['warnings']), 2)

    def test_compare_uses_the_same_validated_summary_for_both_runs(self):
        with patch.object(self.query, '_supabase_get', side_effect=self.read):
            result = self.query.compare_runs(2352, 2352)
        self.assertEqual(result['run_1'], result['run_2'])
        self.assertIn('measurement_contract', result['run_1'])


if __name__ == '__main__':
    unittest.main()
