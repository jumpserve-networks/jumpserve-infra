import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('retire_benchmarks',Path(__file__).resolve().parents[1]/'bin/retire-cloud-benchmarks.py')
retire=importlib.util.module_from_spec(spec)
spec.loader.exec_module(retire)

class RetirementGuards(unittest.TestCase):
    def template(self):
        return {'Resources': {
            'RealWorldTestsApiBB989716': {'Type':'AWS::Lambda::Function','Properties':{'Environment':{'Variables':{
                'SUPABASE_URL':'retained','STATE_MACHINE_ARN':{'Ref':'RealWorldTestsLifecycle'},'INSTANCE_PROFILE_ARN':{'Ref':'RealWorldTestsInstanceProfile'}}}}},
            'RealWorldTestsApiServiceRoleDefaultPolicyX': {'Type':'AWS::IAM::Policy','Properties':{'PolicyDocument':{'Statement':[
                {'Action':'secretsmanager:GetSecretValue','Resource':'secret'},
                {'Action':'states:StartExecution','Resource':{'Ref':'RealWorldTestsLifecycle'}},
                {'Action':['ec2:DescribeRegions'],'Resource':'*'}]}}},
            'RealWorldTestsLifecycle':{'Type':'AWS::StepFunctions::StateMachine'},
            'RealWorldTestsInstanceProfile':{'Type':'AWS::IAM::InstanceProfile'},
            'LaunchBenchmarkFnX':{'Type':'AWS::Lambda::Function'},
            'LaunchBenchmarkFnLogs':{'Type':'AWS::Logs::LogGroup','DeletionPolicy':'Retain'},
            'BenchmarkApiGETrealworldregionsRealWorldIntegration6767E782':{'Type':'AWS::ApiGatewayV2::Integration','Properties':{'IntegrationUri':{'Fn::GetAtt':['RealWorldTestsApiBB989716','Arn']}}},
            'Reports':{'Type':'AWS::ApiGatewayV2::Route','Properties':{'RouteKey':'GET /real-world/reports','Target':{'Ref':'BenchmarkApiGETrealworldregionsRealWorldIntegration6767E782'}}},
            'Launch':{'Type':'AWS::ApiGatewayV2::Route','Properties':{'RouteKey':'POST /benchmarks'}},
            'ResearchApi':{'Type':'AWS::Lambda::Function','Properties':{'marker':'unchanged'}},
        }}

    def test_read_api_integration_and_secret_preserved_without_execution_authority(self):
        original=self.template(); unchanged=copy.deepcopy(original)
        result,removed,modified=retire.render(original)
        self.assertEqual(original,unchanged)
        for key in ('Reports','ResearchApi','BenchmarkApiGETrealworldregionsRealWorldIntegration6767E782'):
            self.assertEqual(result['Resources'][key],original['Resources'][key])
        self.assertIn('Launch',removed)
        self.assertFalse(retire.refs(result)&set(removed))
        self.assertEqual(result['Resources']['RealWorldTestsApiBB989716']['Properties']['Environment']['Variables'],{'SUPABASE_URL':'retained'})
        self.assertEqual(result['Resources']['RealWorldTestsApiServiceRoleDefaultPolicyX']['Properties']['PolicyDocument']['Statement'],[{'Action':'secretsmanager:GetSecretValue','Resource':'secret'}])

    def test_refuses_historical_log_deletion_and_hidden_sub_references(self):
        template=self.template(); del template['Resources']['LaunchBenchmarkFnLogs']['DeletionPolicy']
        with self.assertRaises(AssertionError): retire.render(template)
        template=self.template();template['Resources']['Reports']['Properties']['Other']={'Fn::Sub':'${LaunchBenchmarkFnX.Arn}'}
        with self.assertRaises(AssertionError): retire.render(template)

    def test_incomplete_or_unencrypted_snapshot_never_allows_volume_deletion(self):
        for snapshot in ({'State':'pending'}, {'State':'completed','Encrypted':False}):
            with patch.object(retire,'aws',return_value={'Snapshots':[snapshot]}) as aws:
                with self.assertRaises(AssertionError): retire.disk()
                self.assertEqual(aws.call_count,1)

    def test_concurrent_stack_update_blocks_asset_deletion(self):
        before={'stacks':{'Public':{'template':{'original':True}}}}
        def read(name): return before if name=='garbage-before.json' else {'layers':[],'assets':[]}
        def aws(*args):
            if args[1]=='describe-stacks': return {'Stacks':[{'StackName':'Public','StackId':'id','StackStatus':'UPDATE_COMPLETE'}]}
            if args[1]=='get-template': return {'TemplateBody':{'changed':True}}
            self.fail('Unexpected mutation')
        with patch.object(retire,'retired'),patch.object(retire,'read',side_effect=read),patch.object(retire,'aws',side_effect=aws):
            with self.assertRaises(AssertionError): retire.garbage_prune()

    def test_current_function_layer_cannot_be_pruned(self):
        arn='arn:aws:lambda:us-east-1:395567831870:layer:retained:1'
        def read(name): return {'stacks':{}} if name=='garbage-before.json' else {'layers':[{'LayerVersionArn':arn}],'assets':[]}
        def aws(*args):
            if args[1]=='describe-stacks': return {'Stacks':[]}
            if args[1]=='list-functions': return {'Functions':[{'FunctionName':'chat'}]}
            if args[1]=='list-versions-by-function': return {'Versions':[{'Layers':[{'Arn':arn}]}]}
            self.fail('Unexpected mutation')
        with patch.object(retire,'retired'),patch.object(retire,'read',side_effect=read),patch.object(retire,'aws',side_effect=aws):
            with self.assertRaises(AssertionError): retire.garbage_prune()

if __name__=='__main__': unittest.main()
