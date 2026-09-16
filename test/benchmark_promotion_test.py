import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'ami'))
import promote
import cleanup

COMMIT = 'a' * 40


class PromotionTest(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(profile=None, region='us-east-1', apply=True, rollback=False)
        self.manifest = dict(account_id=promote.ACCOUNT, region=self.args.region, ami_id='ami-new', backend_commit=COMMIT)
        self.reports = [dict(status=s, amiId='ami-new', backendCommit=COMMIT) for s in ('completed', 'failed')]
        self.image = dict(OwnerId=promote.ACCOUNT, State='available', Public=False,
                          Tags=[dict(Key='Purpose', Value='BenchmarkAMI'), dict(Key='BackendCommit', Value=COMMIT)])

    def test_unverified_or_mismatched_candidate_cannot_be_selected(self):
        with patch.object(promote, 'aws') as aws:
            for reports in ([], self.reports[:1], [dict(r, amiId='ami-other') for r in self.reports]):
                with self.assertRaisesRegex(ValueError, 'verification reports'):
                    promote.validate_candidate(self.args, self.manifest, reports)
            aws.assert_not_called()

    def test_stale_backend_commit_cannot_replace_newer_main(self):
        with patch.object(promote, 'aws', return_value={'Images': [self.image]}), \
                patch.object(promote.subprocess, 'run', return_value=SimpleNamespace(stdout='b' * 40 + '\trefs/heads/main')):
            with self.assertRaisesRegex(ValueError, 'outdated commit'):
                promote.validate_candidate(self.args, self.manifest, self.reports)

    def test_update_preserves_template_and_every_other_parameter(self):
        stack = {'Parameters': [{'ParameterKey': 'BenchmarkAmiId', 'ParameterValue': 'ami-old'},
                                {'ParameterKey': 'Unrelated', 'ParameterValue': 'keep'}]}
        updated = {'Parameters': [{'ParameterKey': 'BenchmarkAmiId', 'ParameterValue': 'ami-new'}]}
        with patch.object(promote, 'aws') as aws, patch.object(promote, 'wait_for_stack'), \
                patch.object(promote, 'stack_info', return_value=updated):
            promote.select_image(self.args, stack, 'ami-new')
            options = aws.call_args.args
            self.assertIn('--use-previous-template', options)
            params = json.loads(options[options.index('--parameters') + 1])
            self.assertEqual(params, [{'ParameterKey': 'BenchmarkAmiId', 'ParameterValue': 'ami-new'},
                                      {'ParameterKey': 'Unrelated', 'UsePreviousValue': True}])

    def test_rollback_does_not_overwrite_a_newer_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = pathlib.Path(directory) / 'promotion.json'
            checkpoint.write_text(json.dumps(dict(account_id=promote.ACCOUNT, region=self.args.region,
                                                  candidate_ami='ami-new', previous_ami='ami-old')))
            self.args.rollback = True
            with patch.object(promote, 'CHECKPOINT', checkpoint), \
                    patch.object(promote, 'aws', return_value={'Account': promote.ACCOUNT}), \
                    patch.object(promote, 'wait_for_stack'), \
                    patch.object(promote, 'stack_info', return_value={'Parameters': [
                        {'ParameterKey': 'BenchmarkAmiId', 'ParameterValue': 'ami-newer'}]}), \
                    patch.object(promote, 'select_image') as select:
                promote.promote(self.args)
                select.assert_not_called()


class CleanupTest(unittest.TestCase):
    def test_cleanup_refuses_an_instance_with_different_job_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(profile=None, region='us-east-1', directory=directory)
            pathlib.Path(directory, 'benchmark-ami-verification-instances.json').write_text(json.dumps([
                dict(jobId='our-job', instanceId='i-other', amiId='ami-test')]))
            def aws(_args, service, operation, *options):
                if operation == 'get-caller-identity':
                    return {'Account': promote.ACCOUNT}
                self.assertEqual(operation, 'describe-instances')
                return {'Reservations': [{'Instances': [{'InstanceId': 'i-other', 'ImageId': 'ami-test',
                    'Tags': [dict(Key='Project', Value='JumpServe'), dict(Key='BenchmarkJobId', Value='other-job')]}]}]}
            with patch.object(cleanup, 'aws', side_effect=aws):
                with self.assertRaisesRegex(ValueError, 'ownership'):
                    cleanup.cleanup(args)


if __name__ == '__main__':
    unittest.main()
