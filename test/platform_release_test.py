import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('platform_production',ROOT/'bin/platform-production.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class PlatformReleaseTests(unittest.TestCase):
    def setUp(self):
        self.base=dict(Parameters={},Resources=dict(Function=dict(Type='AWS::Lambda::Function',Properties=dict(Role='existing-role',Code=dict(S3Bucket='existing-bucket',S3Key='old.zip')))))

    def test_frozen_lambda_code_update_is_supported(self):
        candidate=copy.deepcopy(self.base);candidate['Resources']['Function']['Properties']['Code']['S3Key']='new.zip'
        self.assertEqual(release.guard_template(self.base,candidate),[dict(logical_id='Function',type='AWS::Lambda::Function')])

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

if __name__=='__main__':unittest.main()
