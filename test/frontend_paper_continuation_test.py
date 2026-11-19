import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

path = Path(__file__).resolve().parents[1]/'assets/frontend-paper-continuation/index.py'
spec = importlib.util.spec_from_file_location('frontend_paper_continuation', path)
module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'boto3': types.SimpleNamespace(client=lambda name:None)}):
    spec.loader.exec_module(module)


class ContinuationTest(unittest.TestCase):
    def test_only_fixed_signed_request_reaches_next_controller(self):
        secret = MagicMock()
        secret.get_secret_value.return_value = {'SecretString':json.dumps({'OPENAI_API_KEY':'offline-api-key','SUPABASE_SECRET_KEY':'never-in-request'})}
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"version":"paper-background-v1","advanced":1,"unavailable":0}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict(os.environ, {'SECRET_ARN':'arn:offline-secret'}), patch.object(module.boto3,'client',return_value=secret), patch.object(module.time,'time',return_value=1795000000), patch.object(module.urllib.request,'build_opener',return_value=opener):
            result = module.handler({'url':'https://attacker.invalid','owner':'other'},None)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://jumpserve.quaint-lab.org/research-verification/api/paper-background')
        self.assertEqual(request.data,b'{"limit":2}')
        self.assertNotIn('never-in-request',repr(request.headers))
        self.assertNotIn('offline-api-key',repr(request.headers))
        self.assertEqual(request.get_header('X-jumpserve-paper-signature'),module.signature('offline-api-key','1795000000','{"limit":2}'))
        self.assertEqual(opener.open.call_args.kwargs['timeout'],90)
        self.assertEqual(result,{'advanced':1,'unavailable':0})

    def test_redirects_and_sensitive_failure_details_are_not_forwarded(self):
        self.assertIsNone(module.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://attacker.invalid'))
        secret = MagicMock();secret.get_secret_value.return_value = {'SecretString':'{"OPENAI_API_KEY":"offline-key"}'}
        opener = MagicMock();opener.open.side_effect=module.urllib.error.URLError('private-provider-token')
        with patch.dict(os.environ,{'SECRET_ARN':'arn:offline'}),patch.object(module.boto3,'client',return_value=secret),patch.object(module.urllib.request,'build_opener',return_value=opener):
            with self.assertRaisesRegex(RuntimeError,'temporarily unavailable') as error:
                module.handler({},None)
        self.assertNotIn('private-provider-token',str(error.exception))


if __name__=='__main__':
    unittest.main()
