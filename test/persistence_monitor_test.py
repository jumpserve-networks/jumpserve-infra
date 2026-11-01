"""Read-only outage probes and credential-safe telemetry, without AWS/network."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('persistence_monitor', ROOT/'assets/persistence-monitor/monitor.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
KEY = 'synthetic-service-key-that-must-never-appear-in-logs'
ARN = 'arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/supabase-service-key'


class Response(io.BytesIO):
    status = 200


class MonitorTests(unittest.TestCase):
    def setUp(self):
        monitor._key = None
        monitor._key_until = 0

    def test_probe_uses_one_fixed_bounded_get_and_no_credentials_in_url(self):
        opener = Mock()
        opener.open.return_value = Response(b'[{"id":"openclaw-production-v1"}]')
        monitor.probe(KEY, opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, monitor.URL)
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 5})
        self.assertNotIn(KEY, request.full_url)

    def test_unexpected_body_size_projection_and_redirects_are_rejected(self):
        for raw in (b'x'*4097, b'{}', b'invalid', b'[{"private":"unexpected"}]'):
            opener = Mock()
            opener.open.return_value = Response(raw)
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                monitor.probe(KEY, opener)
        with self.assertRaises(ValueError):
            monitor.NoRedirect().redirect_request(None, None, 302, None, None, 'https://unexpected.example')

    def invoke(self, failed=False, arn=ARN, metric_failure=False):
        secrets = Mock()
        secrets.get_secret_value.return_value = {'SecretString': KEY}
        metrics = Mock()
        if metric_failure:
            metrics.put_metric_data.side_effect = TimeoutError('Synthetic AWS failure')

        def client(name, **kwargs):
            return {'secretsmanager': secrets, 'cloudwatch': metrics}[name]

        output = io.StringIO()
        with patch.dict('os.environ', SUPABASE_SECRET_ARN=arn), patch('boto3.client', side_effect=client), \
                patch.object(monitor, 'probe', side_effect=TimeoutError(KEY) if failed else None) as probe, \
                contextlib.redirect_stdout(output):
            if metric_failure:
                with self.assertRaises(TimeoutError):
                    monitor.handler({}, None)
                result = None
            else:
                result = monitor.handler({}, None)
        self.assertNotIn(KEY, output.getvalue())
        return result, metrics, secrets, probe

    def test_success_and_failure_are_emitted_to_aws_without_saving_to_supabase(self):
        for failed in (False, True):
            monitor._key = None
            result, metrics, secrets, probe = self.invoke(failed)
            self.assertEqual(result['reachable'], not failed)
            body = metrics.put_metric_data.call_args.kwargs
            self.assertEqual(body['Namespace'], 'JumpServe/Persistence')
            self.assertEqual(body['MetricData'][0]['Value'], int(not failed))
            self.assertEqual(body['MetricData'][0]['Dimensions'], [{'Name': 'Project', 'Value': monitor.PROJECT}])
            self.assertEqual(set(secrets.method_calls[0].kwargs), {'SecretId'})
            probe.assert_called_once_with(KEY)
            self.assertNotIn(KEY, json.dumps(body))

    def test_wrong_secret_target_emits_failure_without_retrieving_it(self):
        result, metrics, secrets, probe = self.invoke(arn=ARN.replace('395567831870', '111111111111'))
        self.assertFalse(result['reachable'])
        secrets.get_secret_value.assert_not_called()
        probe.assert_not_called()

    def test_full_secret_arn_and_failed_metric_publication_remain_detectable(self):
        self.assertTrue(self.invoke(arn=ARN+'-Ab123X')[0]['reachable'])
        self.invoke(metric_failure=True)


if __name__ == '__main__':
    unittest.main()
