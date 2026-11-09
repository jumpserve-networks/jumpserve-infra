"""Gateway startup and HTTP adapters without sockets, Slack or provider calls."""
import copy
import builtins
import io
import json
from pathlib import Path
import sys
import runpy
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import uuid

from platform_slack_test import gateway, Store, Transport, Wire


class SlackGatewayBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='slack-gateway-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve(); self.store = Store(); self.transport = Transport(); self.wire = Wire(); self.members = [gateway.OWNER, 'USECOND']; self.slack = Mock(side_effect=lambda *args, **kwargs: {'members': self.members}); self.bridge = gateway.Bridge(self.store, self.root / 'calls', self.transport, self.wire, self.slack); self.addCleanup(self.bridge.db.close)
    def request(self, **change):
        value = dict(model=gateway.MODEL, input='Synthetic original question', tools=[dict(type='function', name='jumpserve_status')]); value.update(change); return gateway.canonical(value)
    def envelope(self): return dict(actor=dict(team_id=gateway.TEAM, channel_id=gateway.CHANNEL, sender_id='USECOND', session_id=str(uuid.uuid4())), request_id=str(uuid.uuid4()), operation='jumpserve_status', payload={})
    def test_actor_rejects_extra_fields_wrong_workspace_bad_sender_or_session(self):
        original = self.envelope()['actor']
        for invalid in [None, dict(original, extra=True), dict(original, team_id='TOTHER'), dict(original, sender_id='invalid'), dict(original, session_id='invalid')]:
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError)): gateway.actor(invalid)
    def test_model_request_bounds_and_nonobject_input_fail_before_retention(self):
        for raw in [b'', b' ' * (gateway.MAXIMUM + 1), b'[]', b'null', b'not-json']:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError): self.bridge.inference(raw)
        self.assertEqual(self.transport.calls, 0); self.assertEqual(self.store.records, {})
    def test_native_configuration_failure_keeps_private_original_diagnostics(self):
        config = gateway.configuration(self.root, 'http://127.0.0.1:18000', 'synthetic-loopback-token', json.loads(Path(gateway.__file__).with_name('slack-channel-policy.json').read_bytes())); path = self.root / 'config.json'; completed = types.SimpleNamespace(returncode=1, stdout=b'Original stdout\x00', stderr=b'Original stderr\n')
        with patch.object(gateway.subprocess, 'run', return_value=completed) as command, self.assertRaisesRegex(RuntimeError, 'private diagnostics retained'): gateway.write_configuration(config, path, 'synthetic-node', 'synthetic-cli', {'FIXED': 'yes'}, True)
        self.assertEqual(command.call_args.args[0][:4], ['/usr/sbin/runuser', '-u', 'jumpserve', '--']); self.assertEqual(command.call_args.kwargs['timeout'], 120); self.assertEqual(path.with_suffix('.configure.log').read_bytes(), completed.stdout + completed.stderr); self.assertEqual(path.with_suffix('.configure.log').stat().st_mode & 0o777, 0o600)
    def test_native_configuration_checks_original_values_and_version_metadata(self):
        config = gateway.configuration(self.root, 'http://127.0.0.1:18000', 'synthetic-token', json.loads(Path(gateway.__file__).with_name('slack-channel-policy.json').read_bytes())); path = self.root / 'config.json'
        for failure in ['value', 'metadata']:
            def write(*args, **kwargs):
                actual = copy.deepcopy(config)
                if failure == 'value': actual['gateway']['port'] = 1
                path.write_bytes(gateway.canonical(actual)); return types.SimpleNamespace(returncode=0)
            with self.subTest(failure=failure), patch.object(gateway.subprocess, 'run', side_effect=write), self.assertRaisesRegex(ValueError, 'readback differs|metadata is missing'): gateway.write_configuration(config, path, 'node', 'cli', {})
    def test_evidence_limits_and_conflicting_local_or_remote_originals_are_rejected(self):
        ident = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, 'bound'): self.bridge.retain(ident, 'original', b'x' * 5000001)
        self.bridge.retain(ident, 'original', b'Original bytes')
        with self.assertRaisesRegex(ValueError, 'local evidence differs'): self.bridge.retain(ident, 'original', b'Changed bytes')
        record = str(uuid.uuid5(uuid.UUID(ident), 'original')); self.store.records[record]['byte_count'] += 1
        with self.assertRaisesRegex(ValueError, 'remote evidence differs'): self.bridge.retain(ident, 'original', b'Original bytes')
    def test_uncertain_upload_settles_only_by_exact_original_content_readback(self):
        original = self.store.request
        def uncertain(path, method='GET', body=None, raw=False):
            if path.startswith('/storage/') and method == 'POST': original(path, method, body, raw); raise RuntimeError('Synthetic uncertain upload')
            return original(path, method, body, raw)
        with patch.object(self.store, 'request', side_effect=uncertain): self.bridge.retain(str(uuid.uuid4()), 'original', b'Exact original')
        self.assertEqual(len(self.store.records), 1)
        def corrupt(path, method='GET', body=None, raw=False):
            if path.startswith('/storage/') and method == 'GET': return b'Changed readback'
            return original(path, method, body, raw)
        with patch.object(self.store, 'request', side_effect=corrupt), self.assertRaisesRegex(ValueError, 'readback differs'): self.bridge.retain(str(uuid.uuid4()), 'original', b'Another original')
        def uncertain_and_corrupt(path, method='GET', body=None, raw=False):
            if path.startswith('/storage/') and method == 'POST': raise RuntimeError('Original uncertain upload')
            if path.startswith('/storage/') and method == 'GET': return b'Different object'
            return original(path, method, body, raw)
        with patch.object(self.store, 'request', side_effect=uncertain_and_corrupt), self.assertRaisesRegex(RuntimeError, 'Original uncertain upload'): self.bridge.retain(str(uuid.uuid4()), 'original', b'Retained uncertain bytes')
    def test_response_tampering_never_causes_a_replayed_model_call(self):
        body = self.request(); self.bridge.inference(body); ident = self.bridge.db.execute('select id from calls').fetchone()[0]; (self.root / 'calls' / ident / 'response.bin').write_bytes(b'Changed original response')
        with self.assertRaisesRegex(ValueError, 'response hash differs'): self.bridge.inference(body)
        self.assertEqual(self.transport.calls, 1)
    def test_preparation_failures_are_definite_and_not_replayed(self):
        with patch.object(self.transport, 'credential', side_effect=RuntimeError('Synthetic refresh unavailable')), self.assertRaisesRegex(RuntimeError, 'refresh unavailable'): self.bridge.inference(self.request())
        self.assertEqual(self.bridge.db.execute('select status from calls').fetchone()[0], 'failed'); self.assertEqual(self.transport.calls, 0)
        with self.assertRaisesRegex(ValueError, 'cannot be replayed'): self.bridge.inference(self.request())
    def test_different_model_or_unregistered_tool_retains_failed_provider_evidence(self):
        for output in [dict(model='different-model', output=[]), dict(model=gateway.MODEL, output=[dict(type='function_call', name='host_shell')])]:
            with self.subTest(output=output), patch.object(self.wire, 'read_stream', side_effect=lambda response, sink, *args: sink.write(response.read()) and output), self.assertRaisesRegex(ValueError, 'outcome is not complete'): self.bridge.inference(self.request(input=str(output)))
        self.assertEqual(self.transport.calls, 2); self.assertEqual({row[0] for row in self.bridge.db.execute('select status from calls')}, {'failed'})
    def test_registered_model_tools_and_nonfunction_output_remain_valid(self):
        output = dict(model=gateway.MODEL, output=[dict(type='message'), dict(type='function_call', name='jumpserve_status')])
        with patch.object(self.wire, 'read_stream', side_effect=lambda response, sink, *args: sink.write(response.read()) and output): self.assertEqual(self.bridge.inference(self.request()), b'original provider stream')
    def test_restart_does_not_reclassify_a_missing_or_mismatched_receipt_as_completed(self):
        for with_receipt in [False, True]:
            with self.subTest(with_receipt=with_receipt):
                ident = str(uuid.uuid4()); directory = self.root / 'calls' / ident; directory.mkdir(); body = self.request(input=ident); sha = gateway.digest(body); self.bridge.db.execute('insert into calls values(?,?,?)', (sha, ident, 'dispatched')); self.bridge.db.commit()
                if with_receipt: gateway.save(directory / 'receipt.json', gateway.canonical(dict(version='different-version', status='complete', call_id=ident)))
        reopened = gateway.Bridge(self.store, self.root / 'calls', self.transport, self.wire, self.slack)
        try: self.assertEqual({row[0] for row in reopened.db.execute('select status from calls')}, {'dispatched'})
        finally: reopened.db.close()
    def test_retained_failed_receipts_are_settled_before_new_inference(self):
        self.transport.http_status = 429
        with self.assertRaises(ValueError): self.bridge.inference(self.request())
        self.bridge.db.execute("update calls set status='retained'"); self.bridge.db.commit(); self.transport.http_status = 200; self.assertEqual(self.bridge.inference(self.request(input='A distinct new question')), b'original provider stream'); self.assertEqual(self.transport.calls, 2)

    def test_retained_tampering_and_cached_persistence_errors_fence_further_inference(self):
        self.bridge.inference(self.request()); ident = self.bridge.db.execute('select id from calls').fetchone()[0]; original = self.store.request
        def unavailable(path, *args, **kwargs):
            if path.startswith('/rest/v1/platform_slack_records?'): raise RuntimeError('Synthetic persistence failure')
            return original(path, *args, **kwargs)
        with patch.object(self.store, 'request', side_effect=unavailable), self.assertRaisesRegex(RuntimeError, 'persistence failure'): self.bridge.inference(self.request())
        self.bridge.db.execute("update calls set status='retained'"); self.bridge.db.commit(); (self.root / 'calls' / ident / 'response.bin').write_bytes(b'Tampered original')
        with self.assertRaisesRegex(ValueError, 'response hash differs'): self.bridge.inference(self.request(input='New question'))
        self.assertEqual(self.transport.calls, 1); self.assertEqual(self.bridge.db.execute('select status from calls').fetchone()[0], 'retained')

    def test_a_receipt_retained_by_another_connection_is_settled_without_replaying(self):
        body = self.request(); self.bridge.inference(body); connection = self.bridge.db; other = gateway.sqlite3.connect(self.root / 'calls/calls.sqlite'); self.addCleanup(other.close)
        class ConcurrentRetention:
            def execute(self, sql, params=()):
                if sql == 'select id,status from calls where sha=?': other.execute("update calls set status='retained' where sha=?", params); other.commit()
                return connection.execute(sql, params)
            def commit(self): connection.commit()
        with patch.object(self.bridge, 'db', ConcurrentRetention()): self.assertEqual(self.bridge.inference(body), b'original provider stream')
        self.assertEqual(self.transport.calls, 1)

    def test_tool_envelopes_membership_pagination_and_improvement_requests_keep_bound_identities(self):
        for value in [None, [], dict(self.envelope(), untrusted=True)]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'tool envelope'): self.bridge.tool(value)
        self.slack.side_effect = [dict(members=[], response_metadata={'next_cursor': 'retained-next-page'}), dict(members=['USECOND'])]; envelope = dict(self.envelope(), operation='jumpserve_request'); envelope['payload'] = {'objective': 'Synthetic repair request', 'repositories': ['jumpserve-back-end']}; self.bridge.tool(envelope); self.assertEqual(self.slack.call_args_list[-1].kwargs['cursor'], 'retained-next-page'); path, params = self.store.tool_calls[-1]; self.assertTrue(path.endswith('/platform_slack_request')); self.assertEqual(params['p_request'], envelope['request_id']); self.assertEqual(params['p_session'], envelope['actor']['session_id']); self.assertEqual(params['p_payload'], envelope['payload'])
        self.slack.side_effect = None; self.slack.return_value = dict(members=[], response_metadata={'next_cursor': 'unending-cursor'}); self.slack.reset_mock()
        with self.assertRaisesRegex(ValueError, 'no longer in the shared channel'): self.bridge.tool(self.envelope())
        self.assertEqual(self.slack.call_count, 5); self.assertEqual(len(self.store.tool_calls), 1)

    def handler(self):
        observed = {}
        def server(address, handler): observed.update(address=address, handler=handler); return types.SimpleNamespace()
        with patch.object(gateway, 'ThreadingHTTPServer', side_effect=server): value = gateway.server_for(self.bridge, 'synthetic-bridge-token')
        self.assertEqual(observed['address'], ('127.0.0.1', 0)); self.assertTrue(value.daemon_threads); handler = object.__new__(observed['handler']); handler.wfile = io.BytesIO(); handler.send_response = Mock(); handler.send_header = Mock(); handler.end_headers = Mock(); handler.send_error = Mock(); handler.log_message('No private logs'); return handler
    def test_http_adapter_forwards_exact_bounded_model_and_tool_bytes(self):
        handler = self.handler(); raw = self.request(); handler.path = '/v1/responses'; handler.headers = {'Authorization': 'Bearer synthetic-bridge-token', 'Content-Length': str(len(raw))}; handler.rfile = io.BytesIO(raw); handler.do_POST(); handler.send_response.assert_called_once_with(200); self.assertIn(('Content-Type', 'text/event-stream'), [call.args for call in handler.send_header.call_args_list]); self.assertEqual(handler.wfile.getvalue(), b'original provider stream'); handler.send_error.assert_not_called()
        handler = self.handler(); envelope = self.envelope(); raw = gateway.canonical(envelope); handler.path = '/tools'; handler.headers = {'Authorization': 'Bearer synthetic-bridge-token', 'Content-Length': str(len(raw))}; handler.rfile = io.BytesIO(raw); handler.do_POST(); self.assertEqual(json.loads(handler.wfile.getvalue()), {'recorded': True}); self.assertIn(('Content-Type', 'application/json'), [call.args for call in handler.send_header.call_args_list]); self.assertEqual(self.store.tool_calls[-1][1]['p_sender'], 'USECOND')
    def test_http_adapter_rejects_bad_auth_size_truncation_paths_and_json_without_disclosing_errors(self):
        for failure in ['auth', 'missing-length', 'bad-length', 'oversized', 'truncated', 'path', 'json']:
            with self.subTest(failure=failure):
                handler = self.handler(); raw = b'{}'; handler.path = '/tools'; handler.headers = {'Authorization': 'Bearer synthetic-bridge-token', 'Content-Length': str(len(raw))}
                if failure == 'auth': handler.headers['Authorization'] = 'Bearer wrong-private-token'
                elif failure == 'missing-length': handler.headers.pop('Content-Length')
                elif failure == 'bad-length': handler.headers['Content-Length'] = 'invalid'
                elif failure == 'oversized': handler.headers['Content-Length'] = str(gateway.MAXIMUM + 1)
                elif failure == 'truncated': raw = b'x'
                elif failure == 'path': handler.path = '/unregistered'
                else: raw = b'xx'
                handler.rfile = io.BytesIO(raw); handler.do_POST(); handler.send_response.assert_not_called(); handler.send_error.assert_called_once_with(409, 'Operation unconfirmed; retained identities must reconcile before retry.'); self.assertEqual(handler.wfile.getvalue(), b'')
        self.assertEqual(self.transport.calls, 0); self.assertEqual(self.store.tool_calls, [])

    def startup(self, installed=None, package=None, status=0, stopped=False):
        root = self.root / 'service'; root.mkdir(exist_ok=True)
        if installed is not None: gateway.save(root / 'openclaw.json', gateway.canonical({'plugins': installed}))
        plugin = root / 'state/extensions/slack'; plugin.mkdir(parents=True, exist_ok=True); gateway.save(plugin / 'package.json', gateway.canonical(package or {'name': '@openclaw/slack', 'version': '2026.10.5'}))
        self.secret = dict(team_id=gateway.TEAM, channel_id=gateway.CHANNEL, app_id=gateway.APP, bot_token='synthetic-bot-token', app_token='synthetic-app-token'); self.identity = dict(team_id=gateway.TEAM, bot_id='SYNTHETICBOT'); self.operations = dict(version='platform-slack-operations-v2', tools=list(gateway.TOOLS), controls=list(gateway.CONTROLS), requires_additional_owner_approval=False)
        credential = types.SimpleNamespace(supabase='synthetic-private-store', secret=Mock(side_effect=lambda key: gateway.canonical(self.secret).decode())); credentials = types.ModuleType('platform_supervisor.credentials'); credentials.Credentials = Mock(return_value=credential); stores = types.ModuleType('platform_supervisor.store'); stores.Store = Mock(return_value=types.SimpleNamespace(request=Mock(side_effect=lambda *args: self.operations))); runtime = types.ModuleType('openclaw_runtime'); runtime.verify_runtime = Mock(); runtime.NODE = Path('/synthetic/node'); runtime.PACKAGE = Path('/synthetic/runtime'); slack_api = types.ModuleType('slack_api'); slack_api.slack_call = Mock(side_effect=lambda *args, **kwargs: copy.deepcopy(self.identity)); wire = types.ModuleType('siwc_protocol')
        modules = {'platform_supervisor': types.ModuleType('platform_supervisor'), 'platform_supervisor.credentials': credentials, 'platform_supervisor.store': stores, 'openclaw_runtime': runtime, 'siwc_protocol': wire, 'slack_api': slack_api}; self.enterContext(patch.dict(sys.modules, modules)); paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths)); self.enterContext(patch.dict(gateway.os.environ, SLACK_SECRET_ARN='synthetic-secret-arn')); self.enterContext(patch.object(gateway.os, 'umask'))
        self.server = types.SimpleNamespace(server_address=('127.0.0.1', 18891), serve_forever=Mock(), shutdown=Mock(), server_close=Mock()); self.thread = types.SimpleNamespace(start=Mock(), join=Mock()); self.process = types.SimpleNamespace(poll=Mock(return_value=0 if stopped else None), terminate=Mock(), wait=Mock(return_value=status)); self.signals = {}; self.configurations = []
        def writer(config, path, node, cli, env): self.configurations.append((copy.deepcopy(config), path, node, cli, copy.deepcopy(env))); gateway.save(path, gateway.canonical(dict(config, meta={'lastTouchedVersion': '2026.10.5'})))
        self.enterContext(patch.object(gateway, 'Path', side_effect=lambda value: root if str(value) == '/var/lib/jumpserve-platform-slack' else Path(value))); self.enterContext(patch.object(gateway, 'Bridge', return_value=self.bridge)); self.enterContext(patch.object(gateway, 'server_for', return_value=self.server)); self.enterContext(patch.object(gateway.threading, 'Thread', return_value=self.thread)); self.popen = self.enterContext(patch.object(gateway.subprocess, 'Popen', side_effect=lambda *args, **kwargs: self.capture_process(args, kwargs))); self.enterContext(patch.object(gateway.signal, 'signal', side_effect=lambda kind, callback: self.signals.update({kind: callback}))); self.enterContext(patch.object(gateway, 'write_configuration', side_effect=writer)); return root, credential, runtime, slack_api
    def capture_process(self, args, kwargs): self.process_args = args; self.process_options = kwargs; self.addCleanup(kwargs['stdout'].close); return self.process
    def test_startup_uses_service_credentials_isolated_state_and_closes_owned_resources(self):
        root, credential, runtime, slack = self.startup(); gateway.main(); runtime.verify_runtime.assert_called_once(); credential.secret.assert_called_once_with('synthetic-secret-arn'); slack.slack_call.assert_called_once_with('synthetic-bot-token', 'auth.test'); self.assertEqual(self.process_args[0], ['/synthetic/node', '/synthetic/runtime/openclaw.mjs', 'gateway', 'run']); self.assertEqual((root / 'workspace/AGENTS.md').read_bytes(), gateway.INSTRUCTION.encode()); self.assertEqual(self.configurations[0][0]['gateway']['port'], 18890); env = self.process_options['env']; self.assertEqual(env['JUMPSERVE_SLACK_BRIDGE'], 'http://127.0.0.1:18891'); self.assertEqual(env['SLACK_BOT_TOKEN'], 'synthetic-bot-token'); self.assertEqual(env['OPENCLAW_CONFIG_PATH'], str(root / 'openclaw.json')); self.assertNotIn('AWS_SECRET_ACCESS_KEY', env); self.thread.start.assert_called_once(); self.thread.join.assert_called_once_with(timeout=3); self.server.shutdown.assert_called_once(); self.server.server_close.assert_called_once(); self.process.terminate.assert_called_once(); self.signals[gateway.signal.SIGTERM](); self.signals[gateway.signal.SIGINT](); self.assertEqual(self.process.terminate.call_count, 3)
    def test_startup_preserves_only_verified_installed_slack_paths_and_provenance(self):
        root = self.root / 'service'; plugin = root / 'state/extensions/slack'; installed = {'installs': {'slack': {'version': '2026.10.5', 'provenance': 'synthetic-original'}}, 'entries': {'slack': {'enabled': True}}, 'load': {'paths': [str(plugin), str(plugin), str(root / 'state/other'), str(self.root / 'outside/slack')]}}
        self.startup(installed=installed, stopped=True); gateway.main(); config = self.configurations[0][0]; self.assertEqual(config['plugins']['installs'], installed['installs']); self.assertEqual(config['plugins']['entries']['slack'], {'enabled': True}); self.assertIn(str(plugin), config['plugins']['load']['paths']); self.assertNotIn(str(root / 'state/other'), config['plugins']['load']['paths']); self.assertNotIn(str(self.root / 'outside/slack'), config['plugins']['load']['paths']); self.process.terminate.assert_not_called()
    def test_empty_installed_plugin_metadata_does_not_require_or_invent_an_installation(self):
        self.startup(installed={}); gateway.main(); self.assertNotIn('installs', self.configurations[0][0]['plugins']); self.assertNotIn('slack', self.configurations[0][0]['plugins']['entries'])
    def test_unverified_installed_slack_package_cannot_start_the_native_gateway(self):
        root = self.root / 'service'; self.startup(installed={'load': {'paths': [str(root / 'state/extensions/slack')]}}, package={'name': 'unregistered-package', 'version': '2026.10.5'})
        with self.assertRaisesRegex(ValueError, 'plugin identity differs'): gateway.main()
        self.popen.assert_not_called()
    def test_gateway_exit_failure_still_closes_resources_and_preserves_private_host_log(self):
        self.startup(status=3)
        with self.assertRaisesRegex(RuntimeError, 'private host log'): gateway.main()
        self.server.shutdown.assert_called_once(); self.server.server_close.assert_called_once(); self.thread.join.assert_called_once_with(timeout=3)
    def test_startup_rejects_wrong_secret_or_slack_installation_before_starting_a_server(self):
        self.startup()
        original = copy.deepcopy(self.secret)
        for key, value in [('team_id', 'wrong'), ('channel_id', 'wrong'), ('app_id', 'wrong'), ('pending', True)]:
            self.secret = dict(original, **{key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'credentials are not configured'): gateway.main()
        self.secret = original
        for identity in [{'team_id': 'wrong', 'bot_id': 'bot'}, {'team_id': gateway.TEAM}]:
            self.identity = identity
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, 'installation identity differs'): gateway.main()
        self.thread.start.assert_not_called(); self.popen.assert_not_called()

    def test_script_entrypoint_runs_the_real_native_writer_with_only_service_adapters_replaced(self):
        root, _credential, _runtime, _slack = self.startup(); real_connect = gateway.sqlite3.connect
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs); self.addCleanup(connection.close); return connection
        def native_writer(command, **kwargs):
            self.assertEqual(command[-4:], ['patch', '--stdin', '--replace-path', 'plugins']); actual = json.loads(kwargs['input']); actual['meta'] = {'lastTouchedVersion': '2026.10.5'}; gateway.save(Path(kwargs['env']['OPENCLAW_CONFIG_PATH']), gateway.canonical(actual)); return types.SimpleNamespace(returncode=0)
        # The entrypoint imports these adapters itself. Keep filesystem/SQLite
        # operations real while replacing only the host-specific service edges.
        fake_os = types.SimpleNamespace(**vars(gateway.os)); fake_os.umask = Mock()
        adapters = {'pathlib': types.SimpleNamespace(Path=lambda value: root if str(value) == '/var/lib/jumpserve-platform-slack' else Path(value)), 'http.server': types.SimpleNamespace(BaseHTTPRequestHandler=gateway.BaseHTTPRequestHandler, ThreadingHTTPServer=Mock(return_value=self.server)), 'threading': types.SimpleNamespace(RLock=gateway.threading.RLock, Thread=Mock(return_value=self.thread)), 'subprocess': types.SimpleNamespace(run=native_writer, Popen=self.popen, STDOUT=gateway.subprocess.STDOUT), 'signal': types.SimpleNamespace(signal=Mock(), SIGTERM=gateway.signal.SIGTERM, SIGINT=gateway.signal.SIGINT), 'os': fake_os}
        original_import = builtins.__import__
        def service_import(name, globals=None, locals=None, fromlist=(), level=0): return adapters[name] if name in adapters else original_import(name, globals, locals, fromlist, level)
        with patch.object(gateway.sqlite3, 'connect', side_effect=connect): runpy.run_path(gateway.__file__, run_name='__main__', init_globals={'__builtins__': dict(vars(builtins), __import__=service_import)})
        config = json.loads((root / 'openclaw.json').read_bytes()); self.assertEqual(config['meta']['lastTouchedVersion'], '2026.10.5'); self.assertEqual(config['tools']['allow'], list(gateway.TOOLS)); self.assertEqual(config['models']['providers']['lab']['baseUrl'], 'http://127.0.0.1:18891/v1'); self.popen.assert_called_once(); self.server.shutdown.assert_called_once()


if __name__ == '__main__': unittest.main()
