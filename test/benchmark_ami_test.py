import importlib.util
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ami_build', pathlib.Path(__file__).parents[1] / 'ami/build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
COMMIT = 'a' * 40


class AmiBuildTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.args = SimpleNamespace(profile='default', region='us-east-1', base_ami='ami-base',
                                    subnet_id='subnet-test', security_group_id='sg-test',
                                    backend_commit=COMMIT, apply=True,
                                    output=str(pathlib.Path(self.temp.name) / 'image.json'))
        self.calls = []
        self.account = builder.ACCOUNT
        self.provisioned = True

    def aws(self, args, service, operation, *options):
        self.calls.append((operation, options))
        if operation == 'get-caller-identity':
            return {'Account': self.account}
        if operation == 'describe-images':
            return {'Images': [{'OwnerId': '099720109477', 'Architecture': 'x86_64',
                                'State': 'available', 'Name': 'ubuntu-jammy-22.04-test',
                                'RootDeviceName': '/dev/sda1'}]}
        if operation == 'run-instances':
            return {'Instances': [{'InstanceId': 'i-builder'}]}
        if operation == 'describe-instances':
            return {'Reservations': [{'Instances': [{'State': {'Name': 'stopped'}}]}]}
        if operation == 'describe-instance-information':
            return {'InstanceInformationList': [{'PingStatus': 'Online'}]}
        if operation == 'send-command':
            return {'Command': {'CommandId': 'command-test'}}
        if operation == 'list-command-invocations':
            return {'CommandInvocations': [{'Status': 'Success' if self.provisioned else 'Failed'}]}
        if operation == 'create-image':
            return {'ImageId': 'ami-ready'}
        if operation == 'terminate-instances':
            self.assertEqual(options, ('--instance-ids', 'i-builder'))
            return {}
        if service == 'iam':
            return {}
        raise AssertionError(operation)

    def run_build(self):
        with patch.object(builder, 'aws', side_effect=self.aws), patch.object(builder.time, 'sleep'), patch('builtins.print'):
            builder.build(self.args)

    def test_success_captures_stopped_sealed_builder_and_cleans_up(self):
        self.run_build()
        operations = [call[0] for call in self.calls]
        self.assertLess(operations.index('describe-instances'), operations.index('create-image'))
        self.assertLess(operations.index('list-command-invocations'), operations.index('create-image'))
        self.assertIn('terminate-instances', operations)
        self.assertEqual(operations[-1], 'delete-role')
        manifest = json.loads(pathlib.Path(self.args.output).read_text())
        self.assertEqual(manifest['ami_id'], 'ami-ready')

    def test_builder_has_only_ssm_permissions_and_stops_for_snapshot(self):
        self.run_build()
        options = next(options for operation, options in self.calls if operation == 'run-instances')
        request = json.loads(options[1])
        self.assertTrue(request['IamInstanceProfile']['Name'].startswith('JumpServeAmiBuilder-'))
        policies = [options for operation, options in self.calls if operation == 'attach-role-policy']
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0][-1], 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        self.assertNotIn('KeyName', request)
        self.assertEqual(request['InstanceInitiatedShutdownBehavior'], 'stop')
        self.assertTrue(request['BlockDeviceMappings'][0]['Ebs']['DeleteOnTermination'])

    def test_failed_provisioning_never_creates_image_and_terminates_builder(self):
        self.provisioned = False
        with self.assertRaisesRegex(RuntimeError, 'provisioning failed'):
            self.run_build()
        operations = [call[0] for call in self.calls]
        self.assertNotIn('create-image', operations)
        self.assertIn('terminate-instances', operations)
        self.assertEqual(operations[-1], 'delete-role')

    def test_dry_run_is_read_only(self):
        self.args.apply = False
        self.run_build()
        self.assertEqual([call[0] for call in self.calls], ['get-caller-identity', 'describe-images'])

    def test_wrong_account_is_rejected_before_ec2_calls(self):
        self.account = '000000000000'
        with self.assertRaisesRegex(ValueError, 'Expected AWS account'):
            self.run_build()
        self.assertEqual(len(self.calls), 1)

    def test_backend_must_be_pinned(self):
        self.args.backend_commit = 'main'
        with self.assertRaisesRegex(ValueError, 'full, lowercase Git commit'):
            self.run_build()
        self.assertNotIn('run-instances', [call[0] for call in self.calls])


if __name__ == '__main__':
    unittest.main()
