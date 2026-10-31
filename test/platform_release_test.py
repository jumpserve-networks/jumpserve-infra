import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('platform_production',ROOT/'bin/platform-production.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class PlatformReleaseTests(unittest.TestCase):
    def setUp(self):
        self.base=dict(Parameters={},Resources=dict(Function=dict(Type='AWS::Lambda::Function',Properties=dict(Role='existing-role',Code=dict(S3Bucket='existing-bucket',S3Key='old.zip')))))

    def test_frozen_lambda_code_update_is_supported(self):
        candidate=copy.deepcopy(self.base);candidate['Resources']['Function']['Properties']['Code']['S3Key']='new.zip'
        self.assertEqual(release.guard_template(self.base,candidate),[dict(logical_id='Function',type='AWS::Lambda::Function')])

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
