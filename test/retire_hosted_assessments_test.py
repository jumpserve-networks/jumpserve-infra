import copy
import importlib.util
from pathlib import Path
import unittest

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

if __name__ == '__main__': unittest.main()
