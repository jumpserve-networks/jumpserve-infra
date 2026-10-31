import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('platform_production',ROOT/'bin/platform-production.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
spec=importlib.util.spec_from_file_location('platform_synthesize',ROOT/'bin/platform-synthesize.py');synthesis=importlib.util.module_from_spec(spec);spec.loader.exec_module(synthesis)
spec=importlib.util.spec_from_file_location('platform_diagnostics',ROOT/'bin/platform-deployment-diagnostics.py');diagnostics=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostics)
spec=importlib.util.spec_from_file_location('platform_input',ROOT/'bin/platform-release-input.py');release_input=importlib.util.module_from_spec(spec);spec.loader.exec_module(release_input)

class PlatformReleaseTests(unittest.TestCase):
    def setUp(self):
        self.base=dict(Parameters={},Resources=dict(Function=dict(Type='AWS::Lambda::Function',Properties=dict(Role='existing-role',Code=dict(S3Bucket='existing-bucket',S3Key='old.zip')))))

    def test_frozen_lambda_code_update_is_supported(self):
        candidate=copy.deepcopy(self.base);candidate['Resources']['Function']['Properties']['Code']['S3Key']='new.zip'
        self.assertEqual(release.guard_template(self.base,candidate),[dict(logical_id='Function',type='AWS::Lambda::Function')])

    def test_original_failure_diagnostics_are_bounded_read_only_and_omit_resource_inputs(self):
        operation='9567fb05-b800-5175-9d2d-ee164fb3a31f';token='platform-'+operation+'-JumpServeBenchmarkStack'
        cf=Mock();cf.describe_stacks.return_value=dict(Stacks=[dict(StackStatus='UPDATE_ROLLBACK_COMPLETE',Parameters=[dict(ParameterKey='BootstrapVersion',ParameterValue='/cdk-bootstrap/hnb659fds/version',ResolvedValue='31'),dict(ParameterKey='PrivateCredential',ParameterValue='must-not-appear')])])
        cf.get_template.return_value=dict(TemplateBody=self.base)
        cf.describe_stack_events.return_value=dict(StackEvents=[dict(ClientRequestToken=token,LogicalResourceId='Function',ResourceStatus='UPDATE_FAILED',ResourceStatusReason='Explicit fixture failure',ResourceProperties=dict(secret='must-not-appear')),dict(ClientRequestToken='unrelated',ResourceStatus='UPDATE_FAILED',ResourceStatusReason='unrelated')])
        session=Mock();session.client.return_value=cf;result=diagnostics.collect(session,operation)
        self.assertEqual(result['stack_status'],'UPDATE_ROLLBACK_COMPLETE');self.assertEqual(result['mutations'],0)
        self.assertEqual(len(result['matching_events']),1);self.assertNotIn('must-not-appear',json.dumps(result))
        self.assertEqual(session.client.call_args_list,[unittest.mock.call('cloudformation')])
        self.assertEqual([call[0] for call in cf.method_calls],['describe_stacks','get_template','describe_stack_events'])

    def test_qualified_release_mode_is_explicit_and_rejects_cross_component_use(self):
        revision='a'*40
        environment=dict(PLATFORM_COMPONENT='infrastructure',PLATFORM_REPOSITORY='jumpserve-networks/jumpserve-infra',PLATFORM_REVISION=revision,PLATFORM_OPERATION_ID='9567fb05-b800-5175-9d2d-ee164fb3a31f')
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(dict(object=dict(sha=revision))).encode()
        for qualified in ('false','true'):
            with patch.dict(os.environ,{**environment,'PLATFORM_QUALIFIED_DEFAULTS':qualified},clear=True),patch.object(release_input.urllib.request,'urlopen',return_value=Response()),patch.object(release_input.subprocess,'run') as run,patch('sys.argv',['platform-release-input.py','--execute']):release_input.main()
            self.assertEqual('--qualified-defaults' in run.call_args.args[0],qualified=='true')
        invalid={**environment,'PLATFORM_COMPONENT':'frontend','PLATFORM_REPOSITORY':'jumpserve-networks/jumpserve-front-end','PLATFORM_QUALIFIED_DEFAULTS':'true'}
        with patch.dict(os.environ,invalid,clear=True),patch.object(release_input.urllib.request,'urlopen') as network,self.assertRaises(ValueError):release_input.inputs()
        network.assert_not_called()

    def test_telemetry_rendering_preserves_existing_resource_and_other_changes(self):
        previous=copy.deepcopy(self.base);previous['Resources']['CDKMetadata']=dict(Type='AWS::CDK::Metadata',Properties=dict(Analytics='old-runtime'))
        candidate=copy.deepcopy(previous);candidate['Resources']['CDKMetadata']['Properties']['Analytics']='new-runtime'
        candidate['Resources']['Function']['Properties']['Code']['S3Key']='new.zip'
        rendered,proof=release.render_preserving_telemetry(previous,candidate)
        self.assertEqual(rendered['Resources']['CDKMetadata'],previous['Resources']['CDKMetadata'])
        self.assertEqual(proof,[dict(logical_id='CDKMetadata',resource_sha256=release.sha(release.encoded(previous['Resources']['CDKMetadata'])))])
        self.assertEqual(release.guard_template(previous,rendered),[dict(logical_id='Function',type='AWS::Lambda::Function')])
        self.assertEqual(candidate['Resources']['CDKMetadata']['Properties']['Analytics'],'new-runtime')
        with self.assertRaises(ValueError):release.guard_template(previous,candidate)
        for change in ('type','property','deletion','addition','metadata'):
            bad=copy.deepcopy(candidate);base=copy.deepcopy(previous)
            if change=='type':bad['Resources']['CDKMetadata']['Type']='AWS::IAM::Role'
            elif change=='property':bad['Resources']['CDKMetadata']['Properties']['Other']='unexpected'
            elif change=='deletion':del bad['Resources']['CDKMetadata']
            elif change=='addition':del base['Resources']['CDKMetadata']
            else:bad['Resources']['CDKMetadata']['Metadata']=dict(unexpected='value')
            with self.subTest(change=change),self.assertRaises(ValueError):release.guard_template(base,release.render_preserving_telemetry(base,bad)[0])

    def test_qualified_defaults_release_changes_only_three_controller_code_assets(self):
        scope=json.loads((ROOT/'assessment-budget-defaults-release.json').read_bytes())
        controllers=scope['controller_functions'];packages=scope['preserved_package_functions'];before=scope['previous_executor_version'];after=scope['generated_executor_version']
        old=dict(Parameters={},Resources={name:dict(Type='AWS::Lambda::Function',Properties=dict(Role='retained-role',Code=dict(S3Bucket=release.BUCKET,S3Key='a'*64+'.zip'),Environment=dict(Variables=dict(EXECUTOR={'Ref':before}))),Metadata={'aws:asset:path':'asset.'+'a'*64,'aws:asset:property':'Code','aws:asset:is-bundled':False}) for name in controllers+packages})
        old['Resources'][before]=dict(Type='AWS::Lambda::Version',Properties=dict(FunctionName={'Ref':packages[0]}))
        old['Resources']['Policy']=dict(Type='AWS::IAM::Policy',Properties=dict(PolicyDocument=dict(Statement=[dict(Action='lambda:InvokeFunction',Resource={'Ref':before})])))
        output_pin=scope['existing_output_pins']['BenchmarkImagePipelineRoleArn']
        old['Resources'][output_pin['role_logical_id']]=dict(Type='AWS::IAM::Role',Properties=dict(RoleName=output_pin['role_name']))
        old['Outputs']=dict(BenchmarkImagePipelineRoleArn=dict(Value={'Fn::GetAtt':[output_pin['role_logical_id'],'Arn']}))
        info=dict(Parameters=[],Outputs=[dict(OutputKey='BenchmarkImagePipelineRoleArn',OutputValue=output_pin['value'])])
        group=scope['existing_output_pins']['BenchmarkSecurityGroupId'];old['Resources'][group['resource_logical_id']]=dict(Type='AWS::EC2::SecurityGroup',Properties=dict(VpcId='vpc-software-fixture'))
        old['Outputs']['BenchmarkSecurityGroupId']=dict(Value={'Fn::GetAtt':[group['resource_logical_id'],'GroupId']})
        info['Outputs'].append(dict(OutputKey='BenchmarkSecurityGroupId',OutputValue=group['value']))
        for name,pin in scope['existing_parameter_pins'].items():
            old['Parameters'][name]=dict(Type=pin['parameter_type'],Default=pin['source_path'])
            info['Parameters'].append(dict(ParameterKey=name,ParameterValue=pin['source_path'],ResolvedValue=pin['resolved_value']))
        candidate=json.loads(json.dumps(old).replace(before,after))
        for name in controllers+packages:
            candidate['Resources'][name]['Properties']['Code']['S3Key']='b'*64+'.zip'
            candidate['Resources'][name]['Metadata']['aws:asset:path']='asset.'+'b'*64
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'assessment-budget-defaults-release.json').write_text(json.dumps(scope));(root/'research-workflow-runtime.json').write_bytes((ROOT/'research-workflow-runtime.json').read_bytes())
            rendered,proof=release.render_qualified_budget_controllers(old,candidate,root,info)
            baseline=copy.deepcopy(old);baseline['Parameters']=copy.deepcopy(rendered['Parameters'])
            self.assertEqual([item['logical_id'] for item in release.guard_template(baseline,rendered)],sorted(controllers))
            with self.assertRaises(ValueError):release.guard_template(old,rendered)
            for pin in proof[0]['parameter_pins']:
                self.assertEqual(rendered['Parameters'][pin['parameter_key']],dict(Type='String',Default=pin['resolved_value']))
            self.assertTrue(proof[0]['all_other_template_content_preserved'])
            for name in packages+[before,'Policy']:self.assertEqual(rendered['Resources'][name],old['Resources'][name])
            retained=copy.deepcopy(rendered)
            retained['Parameters']=copy.deepcopy(old['Parameters'])
            retained['Outputs']=copy.deepcopy(old['Outputs'])
            for name in controllers:
                retained['Resources'][name]['Properties']['Code']=copy.deepcopy(old['Resources'][name]['Properties']['Code'])
                retained['Resources'][name]['Metadata']['aws:asset:path']=old['Resources'][name]['Metadata']['aws:asset:path']
            self.assertEqual(retained,old)
            for attack in ('controller-role','handler','asset-pointer'):
                bad=copy.deepcopy(candidate)
                if attack=='controller-role':bad['Resources'][controllers[0]]['Properties']['Role']='different'
                elif attack=='handler':bad['Resources'][controllers[0]]['Properties']['Handler']='unexpected.handler'
                else:bad['Resources'][controllers[0]]['Metadata']['aws:asset:path']='asset.'+'c'*64
                with self.subTest(attack=attack),self.assertRaises(ValueError):release.render_qualified_budget_controllers(old,bad,root,info)
            for ignored in ('environment','executor-role','policy','addition','deletion','other-metadata'):
                bad=copy.deepcopy(candidate)
                if ignored=='environment':bad['Resources'][controllers[0]]['Properties']['Environment']['Variables']['EXTRA']='out-of-scope'
                elif ignored=='executor-role':bad['Resources'][packages[0]]['Properties']['Role']='different'
                elif ignored=='policy':bad['Resources']['Policy']['Properties']['PolicyDocument']['Statement'][0]['Action']='lambda:*'
                elif ignored=='addition':bad['Resources']['Unexpected']=dict(Type='AWS::IAM::Role')
                elif ignored=='deletion':del bad['Resources']['Policy']
                else:bad['Resources'][packages[0]]['Metadata']['aws:asset:is-bundled']=True
                with self.subTest(preserved=ignored):self.assertEqual(release.render_qualified_budget_controllers(old,bad,root,info)[0],rendered)
            for error in ('missing-resolved','changed-resolved','unexpected-parameter'):
                bad_info=copy.deepcopy(info);bad_old=copy.deepcopy(old)
                if error=='missing-resolved':bad_info['Parameters'][0].pop('ResolvedValue')
                elif error=='changed-resolved':bad_info['Parameters'][0]['ResolvedValue']='different'
                else:bad_old['Parameters']['Unexpected']=dict(Type='AWS::SSM::Parameter::Value<String>',Default='/unreviewed')
                with self.subTest(parameter_error=error),self.assertRaises(ValueError):release.render_qualified_budget_controllers(bad_old,candidate,root,bad_info)
            for error in ('changed-output','changed-role-path','changed-group','missing-vpc'):
                bad_info=copy.deepcopy(info);bad_old=copy.deepcopy(old)
                if error=='changed-output':bad_info['Outputs'][0]['OutputValue']='arn:aws:iam::395567831870:role/Unrelated'
                elif error=='changed-role-path':bad_old['Resources'][output_pin['role_logical_id']]['Properties']['Path']='/unreviewed/'
                elif error=='changed-group':bad_info['Outputs'][1]['OutputValue']='sg-00000000000000000'
                else:bad_old['Resources'][group['resource_logical_id']]['Properties'].pop('VpcId')
                with self.subTest(output_error=error),self.assertRaises(ValueError):release.render_qualified_budget_controllers(bad_old,candidate,root,bad_info)
            # Execute the actual deployment adapter against an explicit cloud
            # fixture, proving the frozen values reach UpdateStack and readback.
            assembly=root/'cdk.out';assembly.mkdir();(assembly/'Fixture.template.json').write_text(json.dumps(candidate))
            cf=Mock();cf.get_template.side_effect=[dict(TemplateBody=old),dict(TemplateBody=rendered)]
            expected_parameters=[dict(ParameterKey=name,ParameterValue=pin['resolved_value']) for name,pin in scope['existing_parameter_pins'].items()]
            cf.describe_stacks.side_effect=[dict(Stacks=[dict(StackStatus='UPDATE_COMPLETE',**info)]),dict(Stacks=[dict(StackStatus='UPDATE_COMPLETE',Parameters=expected_parameters,Outputs=info['Outputs'])])]
            cf.update_stack.return_value=dict(StackId='synthetic-cloudformation-fixture');session=Mock();session.client.return_value=cf
            previous_cwd=Path.cwd()
            try:
                os.chdir(root)
                generic=Mock();generic.get_template.return_value=dict(TemplateBody=old);generic.describe_stacks.return_value=dict(Stacks=[dict(StackStatus='UPDATE_COMPLETE',**info)])
                generic_session=Mock();generic_session.client.return_value=generic
                with patch.object(release,'STACKS',('Fixture',)),patch.object(release,'publish_assets') as generic_assets,self.assertRaises(ValueError):release.infrastructure(generic_session,root,'ordinary-operation')
                generic.update_stack.assert_not_called();generic_assets.assert_not_called()
                with patch.object(release,'STACKS',('Fixture',)),patch.object(release,'publish_assets',return_value=[]):result=release.infrastructure(session,root,'fixture-operation',qualified_defaults=True)
            finally:os.chdir(previous_cwd)
            self.assertEqual(cf.update_stack.call_args.kwargs['Parameters'],expected_parameters)
            self.assertEqual(result['stacks'][0]['status'],'UPDATE_COMPLETE')
            self.assertEqual(session.client.call_args_list,[unittest.mock.call('cloudformation')])
            manifest=json.loads((root/'research-workflow-runtime.json').read_bytes());manifest['files']['network_package.py']='0'*64;(root/'research-workflow-runtime.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):release.render_qualified_budget_controllers(old,candidate,root,info)

    def test_asset_create_without_list_permission_is_conditional_and_preserves_existing_objects(self):
        class HttpError(Exception):
            def __init__(self,status):self.response=dict(ResponseMetadata=dict(HTTPStatusCode=status))
        for concurrent in (False,True):
            with self.subTest(concurrent=concurrent),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);assembly=root/'cdk.out';assembly.mkdir();(assembly/'asset.txt').write_bytes(b'fixed code')
                manifest=dict(files=dict(asset=dict(source=dict(path='asset.txt',packaging='file'),destinations=dict(account=dict(bucketName=release.BUCKET,region='us-east-1',objectKey='a'*64+'.zip')))))
                (assembly/'Stack.assets.json').write_text(json.dumps(manifest))
                s3=Mock();s3.head_object.side_effect=[HttpError(403),dict(ContentLength=10,Metadata={})]
                if concurrent:s3.put_object.side_effect=HttpError(412)
                session=Mock();session.client.return_value=s3
                with patch.object(release,'STACKS',('Stack',)):proof=release.publish_assets(session,root)
                self.assertEqual(proof[0]['byte_count'],10);self.assertEqual(s3.put_object.call_count,1)
                self.assertEqual(s3.put_object.call_args.kwargs['IfNoneMatch'],'*')
                self.assertEqual(s3.put_object.call_args.kwargs['Body'],b'fixed code')

    def test_uncertain_asset_read_does_not_trigger_a_write(self):
        class HttpError(Exception):
            response=dict(ResponseMetadata=dict(HTTPStatusCode=503))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);assembly=root/'cdk.out';assembly.mkdir();(assembly/'asset').write_bytes(b'code')
            (assembly/'Stack.assets.json').write_text(json.dumps(dict(files=dict(asset=dict(source=dict(path='asset',packaging='file'),destinations=dict(account=dict(bucketName=release.BUCKET,region='us-east-1',objectKey='a'*64)))))))
            s3=Mock();s3.head_object.side_effect=HttpError();session=Mock();session.client.return_value=s3
            with patch.object(release,'STACKS',('Stack',)),self.assertRaises(HttpError):release.publish_assets(session,root)
            s3.put_object.assert_not_called()

    def test_storage_compute_iam_deletion_and_authority_changes_are_rejected(self):
        for kind in ('AWS::IAM::Role','AWS::EC2::Instance','AWS::S3::Bucket','AWS::CloudFormation::CustomResource'):
            candidate=copy.deepcopy(self.base);candidate['Resources']['New']=dict(Type=kind)
            with self.assertRaises(ValueError):release.guard_template(self.base,candidate)
        candidate=copy.deepcopy(self.base);candidate['Resources'].pop('Function')
        with self.assertRaises(ValueError):release.guard_template(self.base,candidate)
        for field in ('Role','FunctionName','VpcConfig','FileSystemConfigs','PackageType'):
            candidate=copy.deepcopy(self.base);candidate['Resources']['Function']['Properties'][field]='changed'
            with self.assertRaises(ValueError):release.guard_template(self.base,candidate)

    def test_template_parameters_transforms_and_new_function_identities_need_dedicated_release(self):
        for candidate in ({**self.base,'Parameters':dict(New=dict(Type='String'))},{**self.base,'Transform':'macro'}, {**self.base,'Unexpected':'value'}):
            with self.assertRaises(ValueError):release.guard_template(self.base,candidate)
        candidate=copy.deepcopy(self.base);candidate['Resources']['New']=copy.deepcopy(candidate['Resources']['Function'])
        with self.assertRaises(ValueError):release.guard_template(self.base,candidate)

    def test_workflow_has_oidc_and_no_static_aws_secret_dependency(self):
        source=(ROOT/'.github/workflows/platform-release.yml').read_text()
        self.assertIn('id-token: write',source);self.assertIn('role-to-assume: arn:aws:iam::395567831870:role/JumpServePlatformRelease',source)
        self.assertNotIn('secrets.AWS_ACCESS_KEY_ID',source);self.assertNotIn('secrets.AWS_SECRET_ACCESS_KEY',source)
        self.assertLess(source.index('synthesize without credentials'),source.index('Obtain renewable AWS role credentials'))

    def test_synthesis_uses_checkout_owner_and_retains_credential_free_container_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);recipe=root/'assets/platform/Dockerfile';recipe.parent.mkdir(parents=True);recipe.write_text('FROM fixed-reviewed-image\n')
            with patch.object(synthesis.Path,'cwd',return_value=root),patch.object(synthesis.os,'getuid',return_value=1001),patch.object(synthesis.os,'getgid',return_value=1002),patch.object(synthesis.subprocess,'run') as run:
                synthesis.main()
            containers=[call.args[0] for call in run.call_args_list if call.args[0][:2]==['docker','run']]
            self.assertEqual(len(containers),4)
            for command in containers:
                self.assertEqual(command[command.index('--user')+1],'1001:1002')
                self.assertEqual(command[command.index('--cap-drop')+1],'ALL')
                self.assertEqual(command[command.index('--security-opt')+1],'no-new-privileges')
                self.assertEqual([command[i+1] for i,value in enumerate(command) if value=='--env'],['HOME=/tmp'])
                self.assertNotIn('--cap-add',command);self.assertNotIn('--privileged',command)
            self.assertIn('--no-lookups',containers[-1]);self.assertIn('JumpServeBenchmarkStack',containers[-1])
            self.assertIn('node node_modules/ts-node/dist/bin.js --prefer-ts-exts bin/benchmark.ts',containers[-1])
            self.assertNotIn('JumpServeAgentStack',containers[-1])

if __name__=='__main__':unittest.main()
