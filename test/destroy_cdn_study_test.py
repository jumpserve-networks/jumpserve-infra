import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cdn_retirement', Path(__file__).resolve().parents[1] / 'bin/destroy-cdn-study.py')
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)

class CdnDestructionTests(unittest.TestCase):
    def test_ownership_guard_rejects_other_resources_or_tags(self):
        name = 'jumpserve-cloudfront-exploratory'
        stack = {'StackName': name, 'StackId': 'arn:aws:cloudformation:us-east-1:395567831870:stack/' + name + '/original',
            'Tags': [{'Key': 'project', 'Value': retirement.PROJECT}]}
        resources = [{'ResourceType': 'AWS::CloudFront::Distribution', 'PhysicalResourceId': 'E199P1KDME1VNX'}]
        retirement.check_stack(name, stack, resources)
        changed = copy.deepcopy(stack); changed['Tags'][0]['Value'] = 'unrelated'
        with self.assertRaises(AssertionError): retirement.check_stack(name, changed, resources)
        with self.assertRaises(AssertionError): retirement.check_stack(name, stack, resources + [{'ResourceType': 'AWS::EC2::Instance'}])

    def test_purge_removes_versions_markers_and_incomplete_uploads(self):
        calls = []; pages = [{'Versions': [{'Key': 'objects/a', 'VersionId': 'v1'}],
            'DeleteMarkers': [{'Key': 'objects/a', 'VersionId': 'marker'}]}, {}]
        before = {'stacks': {'jumpserve-cdn-origin': {'stack': {'StackName': 'jumpserve-cdn-origin', 'StackId': 'original'}}}}
        def aws(*args):
            calls.append(args)
            if args[:2] == ('cloudformation', 'describe-stacks'): return {'Stacks': [{'StackStatus': 'DELETE_COMPLETE'}]}
            if args[:2] == ('s3api', 'get-bucket-tagging'): return {'TagSet': [{'Key': 'project', 'Value': retirement.PROJECT}]}
            if args[:2] == ('s3api', 'list-object-versions'): return pages.pop(0)
            if args[:2] == ('s3api', 'list-multipart-uploads'): return {'Uploads': [{'Key': 'objects/b', 'UploadId': 'unfinished'}]}
            return {}
        with patch.object(retirement, 'original', return_value=before), patch.object(retirement, 'aws', side_effect=aws), patch.object(retirement, 'save'), contextlib.redirect_stdout(io.StringIO()):
            retirement.purge_bucket()
        deletion = next(c for c in calls if c[:2] == ('s3api', 'delete-objects'))
        self.assertEqual(json.loads(deletion[-1])['Objects'], [{'Key': 'objects/a', 'VersionId': 'v1'}, {'Key': 'objects/a', 'VersionId': 'marker'}])
        self.assertTrue(any(c[:2] == ('s3api', 'abort-multipart-upload') for c in calls))
        self.assertEqual(calls[-1], ('s3api', 'delete-bucket', '--bucket', retirement.BUCKET, '--expected-bucket-owner', retirement.ACCOUNT))

    def test_purge_refuses_incomplete_stack_deletion(self):
        before = {'stacks': {'jumpserve-cdn-origin': {'stack': {'StackName': 'jumpserve-cdn-origin', 'StackId': 'original'}}}}
        with patch.object(retirement, 'original', return_value=before), patch.object(retirement, 'aws', return_value={'Stacks': [{'StackStatus': 'DELETE_IN_PROGRESS'}]}) as api:
            with self.assertRaises(AssertionError): retirement.purge_bucket()
        self.assertEqual(api.call_count, 1)

    def test_dns_cleanup_preserves_fastly_and_zone_records(self):
        records = [{'Name': 'origin.jumpserve.dev.', 'Type': 'A', 'TTL': 60, 'ResourceRecords': [{'Value': '192.0.2.1'}]},
            {'Name': 'fastly.jumpserve.dev.', 'Type': 'CNAME'}, {'Name': 'jumpserve.dev.', 'Type': 'NS'}]
        before = {'stacks': {'study': {'stack': {'StackId': 'original'}}}, 'dns': records}
        calls = []
        def aws(*args):
            calls.append(args)
            if args[0] == 'cloudformation': return {'Stacks': [{'StackStatus': 'DELETE_COMPLETE'}]}
            if args[1] == 'list-resource-record-sets': return {'ResourceRecordSets': records}
            return {'ChangeInfo': {'Status': 'PENDING'}}
        with patch.object(retirement, 'original', return_value=before), patch.object(retirement, 'aws', side_effect=aws), patch.object(retirement, 'save'), contextlib.redirect_stdout(io.StringIO()):
            retirement.clean_dns()
        batch = json.loads(calls[-1][-1])
        self.assertEqual([x['ResourceRecordSet']['Name'] for x in batch['Changes']], ['origin.jumpserve.dev.'])

if __name__ == '__main__': unittest.main()
