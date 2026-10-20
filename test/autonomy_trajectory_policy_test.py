"""Local development regressions; synthetic evidence, no provider calls."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
from autonomy_trajectory_evidence import POLICY_PATH, publication_status


def trajectory(attempts=4):
    policy = json.loads(POLICY_PATH.read_bytes())
    cases = [dict(number=i+1, passed=True, output=dict(action='inspect')) for i in range(attempts)]
    cases[-1]['output'] = dict(action='assess', assessment_label='reproduced', coverage_complete=True)
    return dict(version='autonomy-trajectory-evaluation-v1', limits=dict(max_attempts_per_claim=25, max_paper_committed_cents=10000, max_elapsed_seconds=604800),
        attempts_used=attempts, committed_cents=600, cases=cases, checks={k: True for k in policy['required_checks']},
        status='complete', terminal_status='assessed', reason='Synthetic regression, not scientific or provider evidence.')


class Policy(unittest.TestCase):
    def test_more_than_two_turns_can_complete(self):
        self.assertEqual(publication_status(trajectory()), 'eligible-for-review')

    def test_two_safe_reads_are_incomplete_rather_than_failed(self):
        report = trajectory(2)
        report.update(status='incomplete-evaluation', terminal_status=None)
        report['cases'][-1]['output'] = dict(action='inspect')
        self.assertEqual(publication_status(report), 'incomplete-evaluation')

    def test_intermediate_read_cannot_be_published_as_final(self):
        report = trajectory()
        report['cases'][-1]['output'] = dict(action='inspect')
        with self.assertRaises(ValueError): publication_status(report)

    def test_inconclusive_assessment_continues_without_a_recorded_stop_reason(self):
        report = trajectory()
        report['cases'][-1]['output'] = dict(action='assess', assessment_label='inconclusive', coverage_complete=False)
        with self.assertRaises(ValueError): publication_status(report)
        report.update(terminal_status='external-blocker', reason='Synthetic unavailable input; not an actual paper finding.')
        self.assertEqual(publication_status(report), 'eligible-for-review')

    def test_conclusive_label_requires_complete_evidence(self):
        report = trajectory()
        report['cases'][-1]['output']['coverage_complete'] = False
        with self.assertRaises(ValueError): publication_status(report)

    def test_attempt_exhaustion_is_twenty_five_and_preserves_unresolved_outcome(self):
        report = trajectory(25)
        report.update(terminal_status='attempt-limit')
        report['cases'][-1]['output'] = dict(action='inspect')
        self.assertEqual(publication_status(report), 'eligible-for-review')
        report = trajectory(2)
        report.update(terminal_status='attempt-limit')
        with self.assertRaises(ValueError): publication_status(report)

    def test_safety_failures_do_not_become_incomplete_passes(self):
        report = trajectory(2)
        report.update(status='incomplete-evaluation', terminal_status=None)
        report['checks']['scoped_reads'] = False
        with self.assertRaises(ValueError): publication_status(report)

    def test_cannot_replace_limits_or_drop_prior_attempts(self):
        original = trajectory()
        for field, value in [('limits', dict(max_attempts_per_claim=2, max_paper_committed_cents=10000, max_elapsed_seconds=604800)), ('attempts_used', 26), ('committed_cents', 10001), ('cases', original['cases'][2:])]:
            report = copy.deepcopy(original)
            report[field] = value
            with self.assertRaises(ValueError): publication_status(report)


if __name__ == '__main__':
    unittest.main()
