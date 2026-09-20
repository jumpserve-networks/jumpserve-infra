import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from comparison import compare_validity
from run_analysis import summarize_run

FIXTURE = json.loads((ROOT / 'test/fixtures/run-2352.json').read_text())


def summary(run_id, cca, workload=50):
    parent, runs = copy.deepcopy(FIXTURE['parent']), copy.deepcopy(FIXTURE['runs'])
    parent['id'] = run_id
    for run in runs:
        run['congestion_control_algorithms']['name'] = cca
        run['client_file_size_megabytes'] = workload
    return summarize_run(parent, runs, {}, {'script': 'netem_nines.py'})


class ComparisonTest(unittest.TestCase):
    def test_unmatched_workloads_do_not_produce_algorithm_deltas(self):
        result = compare_validity(summary(1, 'bbr', 5), summary(2, 'cubic', 500))
        self.assertFalse(result['configuration_matched'])
        self.assertIn('clients', result['differing_configuration_fields'])
        self.assertEqual(result['client_fct_deltas'], [])

    def test_matched_settings_are_descriptive_without_replication(self):
        a, b = summary(1, 'bbr'), summary(2, 'cubic')
        b['clients'][0]['flow_completion_time_ms'] = a['clients'][0]['flow_completion_time_ms'] - 4930
        result = compare_validity(a, b)
        self.assertTrue(result['configuration_matched'])
        self.assertFalse(result['algorithm_effect_supported'])
        self.assertIsNone(result['confidence_interval'])
        self.assertEqual(result['parent_run_repetitions_per_algorithm'], {'bbr': 1, 'cubic': 1})
        self.assertEqual(result['client_fct_deltas'][0]['cubic_minus_bbr_seconds'], -4.93)
        self.assertEqual(compare_validity(b, a)['client_fct_deltas'], result['client_fct_deltas'])

    def test_missing_metadata_or_repeating_same_run_cannot_imply_pairing(self):
        a = summary(1, 'bbr')
        self.assertFalse(compare_validity(a, a)['configuration_matched'])
        self.assertFalse(compare_validity({'error': 'not found'}, a)['configuration_matched'])
        missing = summarize_run(FIXTURE['parent'], FIXTURE['runs'], {})
        self.assertFalse(missing['comparison_configuration']['eligible'])

    def test_competing_flow_delay_and_launch_settings_are_checked(self):
        for mutate in [lambda s: s['clients'][1].update(delay_ms=99), lambda s: s['launch'].update(loss_pct=5), lambda s: s.update(rate_mbps=80)]:
            a, b = summary(1, 'bbr'), summary(2, 'cubic')
            mutate(b['comparison_configuration']['settings'])
            self.assertFalse(compare_validity(a, b)['configuration_matched'])

    def test_missing_client_start_and_mixed_algorithms_are_ineligible(self):
        for mutate in [lambda r: r[1].update(client_start_delay_ms=None), lambda r: r[1]['congestion_control_algorithms'].update(name='cubic'), lambda r: r.pop()]:
            runs = copy.deepcopy(FIXTURE['runs']); mutate(runs)
            result = summarize_run(FIXTURE['parent'], runs, {}, {'script': 'netem_nines.py'})
            self.assertFalse(result['comparison_configuration']['eligible'])

    def test_launch_metadata_is_not_an_experimental_setting(self):
        a = summarize_run(FIXTURE['parent'], FIXTURE['runs'], {}, {'script': 'netem_nines.py', 'notes': 'A hypothesis', 'tags': ['paper']})
        b = summarize_run(FIXTURE['parent'], FIXTURE['runs'], {}, {'script': 'netem_nines.py', 'notes': 'An unrelated hypothesis'})
        self.assertEqual(a['comparison_configuration'], b['comparison_configuration'])

    def test_invalid_fct_is_not_zero_and_does_not_create_a_delta(self):
        a, b = summary(1, 'bbr'), summary(2, 'cubic')
        b['clients'][0]['flow_completion_time_ms'] = None
        result = compare_validity(a, b)
        self.assertEqual(len(result['client_fct_deltas']), 1)
        self.assertIn('Client 1: FCT unavailable; no delta', result['reasons'])

    def test_conflicting_launch_configuration_is_ineligible(self):
        result = summarize_run(FIXTURE['parent'], FIXTURE['runs'], {}, {'script': 'netem_nines.py', 'client_file_sizes_mbytes': [5, 500]})
        self.assertIn('Stored results conflict with launch configuration', result['comparison_configuration']['reasons'])


if __name__ == '__main__':
    unittest.main()
