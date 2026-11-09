"""AMI receipts require independent candidate controls and a persisted live success."""
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ami_receipt_unit',ROOT/'bin/platform-ami-proof.py')
proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)


class AMIReceipt(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.enterContext(contextlib.chdir(self.root));(self.root/'cdk.out').mkdir()
        self.revision='a'*40;self.image='ami-0123456789abcdef0'
        self.enterContext(patch.dict(proof.os.environ,BACKEND_COMMIT=self.revision,PLATFORM_OPERATION_ID='11111111-1111-4111-8111-111111111111'))
        self.manifest=dict(backend_commit=self.revision,ami_id=self.image)
        self.environment=dict(AMI_ID=self.image,BENCHMARK_IMAGE_MODE='prebaked')
        self.metadata=dict(State='available',Tags=[dict(Key='BackendCommit',Value=self.revision)])
        self.candidate=[self.row('completed',10),self.row('failed',None)]
        self.live=[self.row('completed',11)]
        self.enterContext(patch.object(proof,'aws',side_effect=self.aws))
    def row(self,status,parent):
        return dict(status=status,parentRunId=parent,backendCommit=self.revision,amiId=self.image)
    def aws(self,*args):
        if args[0]=='lambda':return dict(Environment=dict(Variables=self.environment))
        if args[0]=='ec2':return dict(Images=[self.metadata])
        raise AssertionError(args)
    def run_receipt(self):
        for name,value in [('benchmark-ami.json',self.manifest),('benchmark-ami-verification.json',self.candidate),('benchmark-ami-live-verification.json',self.live)]:
            (self.root/'cdk.out'/name).write_text(json.dumps(value))
        proof.main()
        return json.loads((self.root/'production-verification.json').read_text())
    def test_candidate_success_and_failure_plus_independent_live_success_issue_bound_receipt(self):
        result=self.run_receipt();self.assertTrue(result['passed']);self.assertEqual(result['revision'],self.revision)
        self.assertEqual(result['evidence']['candidate_verification'],self.candidate)
        self.assertEqual(result['evidence']['live_verification'],self.live)
    def test_incomplete_duplicate_or_unpersisted_candidate_controls_are_rejected(self):
        valid=copy.deepcopy(self.candidate)
        for value in [None,[],[valid[0]],[valid[0],valid[0]],[valid[1],valid[1]],[valid[0],None],[dict(valid[0],parentRunId=None),valid[1]]]:
            self.candidate=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Candidate verification'):self.run_receipt()
            self.assertFalse((self.root/'production-verification.json').exists())
    def test_missing_failed_duplicate_or_unpersisted_live_success_is_rejected(self):
        valid=copy.deepcopy(self.live)
        for value in [None,[],[self.row('failed',None)],valid*2,[None],[dict(valid[0],parentRunId=None)]]:
            self.live=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Live verification'):self.run_receipt()
    def test_both_report_groups_must_match_exact_source_and_image(self):
        for group in ['candidate','live']:
            original=copy.deepcopy(getattr(self,group))
            for key,value in [('backendCommit','b'*40),('amiId','ami-different')]:
                records=copy.deepcopy(original);records[0][key]=value;setattr(self,group,records)
                with self.subTest(group=group,key=key),self.assertRaises(ValueError):self.run_receipt()
            setattr(self,group,original)
    def test_actual_launcher_and_image_must_still_select_this_source(self):
        for field,value in [('AMI_ID','ami-different'),('BENCHMARK_IMAGE_MODE','bootstrap')]:
            with self.subTest(field=field),patch.dict(self.environment,{field:value}),self.assertRaisesRegex(ValueError,'not selected'):self.run_receipt()
        for field,value in [('State','pending'),('Tags',[dict(Key='BackendCommit',Value='b'*40)])]:
            with self.subTest(field=field),patch.dict(self.metadata,{field:value}),self.assertRaisesRegex(ValueError,'not selected'):self.run_receipt()


if __name__=='__main__':unittest.main()
