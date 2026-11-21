import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import contextlib
import io
import json
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('retirement', Path(__file__).resolve().parents[1] / 'bin/retire-hosted-assessments.py')
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)

class RetirementTests(unittest.TestCase):
    def template(self):
        return {'Resources': {
            'ResearchWorkflowApiE04EBDAC': {'Type': 'AWS::Lambda::Function', 'Properties': {'Environment': {'Variables': {
                'SUPABASE_URL': 'retained', 'NETWORK_BOUNDED_FUNCTION': {'Ref': 'ResearchWorkflowBoundedTcpX'}, 'RESEARCH_AUTONOMY_ENABLED': 'true'}}}},
            'ResearchWorkflowApiServiceRoleDefaultPolicy378FDA82': {'Type': 'AWS::IAM::Policy', 'Properties': {'PolicyDocument': {'Statement': [
                {'Action': 'secretsmanager:GetSecretValue', 'Resource': 'original-secret'},
                {'Action': 'lambda:InvokeFunction', 'Resource': {'Ref': 'ResearchWorkflowBoundedTcpX'}}]}}},
            'ResearchWorkflowBoundedTcpX': {'Type': 'AWS::Lambda::Function'},
            'ResearchWorkflowBoundedTcpLogs': {'Type': 'AWS::Logs::LogGroup', 'DeletionPolicy': 'Retain'},
            'PublicRead': {'Type': 'AWS::ApiGatewayV2::Route', 'Properties': {'RouteKey': 'GET /research/papers'}},
            'HostedWrite': {'Type': 'AWS::ApiGatewayV2::Route', 'Properties': {'RouteKey': 'POST /research/studies'}},
            'BenchmarkLaunch': {'Type': 'AWS::ApiGatewayV2::Route', 'Properties': {'RouteKey': 'POST /benchmarks'}},
        }}

    def test_preserves_unrelated_resources_reads_and_original_template(self):
        before = self.template(); original = copy.deepcopy(before)
        result, removed, changed = retirement.render('JumpServeBenchmarkStack', before)
        self.assertEqual(before, original)
        for key in ('PublicRead', 'BenchmarkLaunch'):
            self.assertEqual(result['Resources'][key], before['Resources'][key])
        self.assertIn('HostedWrite', removed)
        self.assertIn('ResearchWorkflowBoundedTcpLogs', removed)
        self.assertFalse(retirement.references(result) & set(removed))
        self.assertEqual(result['Resources']['ResearchWorkflowApiE04EBDAC']['Properties']['Environment']['Variables']['RESEARCH_AUTONOMY_ENABLED'], 'false')
        statements = result['Resources']['ResearchWorkflowApiServiceRoleDefaultPolicy378FDA82']['Properties']['PolicyDocument']['Statement']
        self.assertEqual(statements, [{'Action': 'secretsmanager:GetSecretValue', 'Resource': 'original-secret'}])

    def test_refuses_log_deletion_and_unapproved_stacks(self):
        original = self.template(); del original['Resources']['ResearchWorkflowBoundedTcpLogs']['DeletionPolicy']
        with self.assertRaises(AssertionError): retirement.render('JumpServeBenchmarkStack', original)
        with self.assertRaises(ValueError): retirement.render('UnrelatedStack', self.template())

    def test_frontend_retains_credentials_and_compute_role(self):
        template = {'Resources': {'Credentials': {'Type': 'AWS::SecretsManager::Secret'},
            'ComputeRole': {'Type': 'AWS::IAM::Role'}, 'PaperContinuationX': {'Type': 'AWS::Lambda::Function'},
            'PaperContinuationLogs': {'Type': 'AWS::Logs::LogGroup', 'DeletionPolicy': 'Retain'}}}
        result, removed, changed = retirement.render('JumpServeFrontendPaperIntakeStack', template)
        self.assertEqual(set(result['Resources']), {'Credentials', 'ComputeRole'})
        self.assertEqual(changed, [])

    def test_status_reconciles_deleted_stacks_using_original_ids(self):
        calls = []
        def aws(*args):
            calls.append(args)
            if args[0] == 'ec2': return {'Snapshots': []}
            return {'Stacks': [{'StackStatus': 'DELETE_COMPLETE'}]}
        before = {'stacks': {name: {'stack': {'StackId': 'original-id-' + name}} for name in retirement.STACKS}}
        with tempfile.TemporaryDirectory() as directory, patch.object(retirement, 'OUT', Path(directory)), patch.object(retirement, 'frozen_inventory', return_value=before), patch.object(retirement, 'aws', side_effect=aws), contextlib.redirect_stdout(io.StringIO()):
            retirement.status()
        for call in calls:
            if call[0] == 'cloudformation': self.assertTrue(call[3].startswith('original-id-'))

    def test_unreachable_region_remains_unverified_in_retained_scan(self):
        output = io.StringIO()
        with patch.object(retirement, 'aws', return_value={'Regions': [{'RegionName': 'unreachable-region'}]}), patch.object(retirement.subprocess, 'check_output', side_effect=subprocess.TimeoutExpired('aws', 25)), patch.object(retirement, 'save') as saved, contextlib.redirect_stdout(output):
            retirement.scan_experiments()
        report = json.loads(output.getvalue())
        self.assertEqual(report['regions_checked'], 0)
        self.assertEqual(report['unverified_regions'], ['unreachable-region'])
        self.assertIsNone(saved.call_args.args[1]['regions'][0]['instances'])

if __name__ == '__main__': unittest.main()
