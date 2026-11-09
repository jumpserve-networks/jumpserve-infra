"""Deployed read-only adapters: credentials, bounded replies and safe failures."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs
import persistence_monitor_test as monitor_fixtures

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('slack_api_boundaries',ROOT/'assets/platform/slack_api.py')
slack=importlib.util.module_from_spec(spec);spec.loader.exec_module(slack)


class RuntimeHttpBoundaries(unittest.TestCase):
    def test_slack_reads_have_exact_method_form_encoding_credential_header_and_no_proxy_or_tls_keylog(self):
        opener=Mock();opener.open.return_value=io.BytesIO(b'{"ok":true,"members":["UOWNER"]}')
        context=Mock()
        with patch.object(slack.ssl,'create_default_context',return_value=context),patch.object(slack.urllib.request,'build_opener',return_value=opener) as build:
            result=slack.slack_call('synthetic-private-token','conversations.members',channel='C&select=*',cursor='original cursor')
        self.assertEqual(result['members'],['UOWNER']);self.assertIsNone(context.keylog_filename)
        self.assertEqual(build.call_args.args[0].proxies,{})
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://slack.com/api/conversations.members')
        self.assertEqual(request.get_method(),'POST');self.assertNotIn('synthetic-private-token',request.full_url)
        self.assertEqual(request.get_header('Authorization'),'Bearer synthetic-private-token')
        self.assertEqual(parse_qs(request.data.decode()),{'channel':['C&select=*'],'cursor':['original cursor']})
        self.assertEqual(opener.open.call_args.kwargs,{'timeout':20})

    def test_slack_errors_are_bounded_and_only_safe_provider_error_codes_are_exposed(self):
        for value,reason in [({'ok':False,'error':'missing_scope'},'missing_scope'),({'ok':False,'error':'private token and details'},'unknown'),({'ok':False},'unknown')]:
            opener=Mock();opener.open.return_value=io.BytesIO(json.dumps(value).encode())
            with patch.object(slack.urllib.request,'build_opener',return_value=opener),self.assertRaisesRegex(ValueError,'Slack read failed: '+reason):slack.slack_call('synthetic','auth.test')
        opener=Mock();opener.open.return_value=io.BytesIO(b'x'*1000001)
        with patch.object(slack.urllib.request,'build_opener',return_value=opener),self.assertRaisesRegex(ValueError,'exceeds its bound'):slack.slack_call('synthetic','auth.test')
        with patch.object(slack.urllib.request,'build_opener') as build,self.assertRaisesRegex(ValueError,'Unexpected Slack'):slack.slack_call('synthetic','chat.postMessage')
        build.assert_not_called()
        with self.assertRaisesRegex(ValueError,'redirects are disabled'):slack.NoRedirect().redirect_request(None)

    def test_default_persistence_probe_disables_proxies_and_tls_key_logging_before_a_fixed_read(self):
        monitor=monitor_fixtures.monitor;context=Mock();opener=Mock()
        opener.open.return_value=monitor_fixtures.Response(b'[]')
        with patch.object(monitor.ssl,'create_default_context',return_value=context),patch.object(monitor.urllib.request,'build_opener',return_value=opener) as build:
            monitor.probe(monitor_fixtures.KEY)
        self.assertIsNone(context.keylog_filename);self.assertEqual(build.call_args.args[0].proxies,{})
        self.assertEqual(opener.open.call_args.args[0].full_url,monitor.URL)
        for key in [None,123,'x'*19,'x'*10001,'x'*20+'\n','x'*20+'\r']:
            with self.subTest(kind=type(key).__name__),self.assertRaisesRegex(ValueError,'Invalid probe credential'):monitor.probe(key,opener)


if __name__=='__main__':unittest.main()
