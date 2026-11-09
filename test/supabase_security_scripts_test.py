"""Credential-operation contracts against synthetic adapters; no live account access."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


audit = load('audit_supabase_security')
with patch.dict(sys.modules, {'audit_supabase_security': audit}): rotate = load('rotate_supabase_keys')
KEYS = {'publishable': 'sb_publishable_fixture_only', 'secret': 'sb_secret_fixture_only'}


class SecurityAudit(unittest.TestCase):
    def test_management_credentials_use_environment_or_decode_the_keychain_without_output(self):
        token = 'sbp_fixture_only'
        with patch.dict(os.environ, {'SUPABASE_ACCESS_TOKEN': ' ' + token + ' '}, clear=True), patch.object(audit.subprocess, 'run') as run:
            self.assertEqual(audit.access_token(), token); run.assert_not_called()
        for encoded in [token, 'go-keyring-encoded:' + token.encode().hex(), 'go-keyring-base64:' + base64.b64encode(token.encode()).decode()]:
            with self.subTest(encoded=encoded), patch.dict(os.environ, {}, clear=True), patch.object(audit.subprocess, 'run', return_value=MagicMock(stdout=encoded + '\n')) as run, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(audit.access_token(), token)
                self.assertEqual(run.call_args.args[0], ['security', 'find-generic-password', '-s', 'Supabase CLI', '-a', 'supabase', '-w'])
                self.assertTrue(run.call_args.kwargs['capture_output']); self.assertTrue(run.call_args.kwargs['check'])
                self.assertEqual(output.getvalue(), '')
        with patch.dict(os.environ, {'SUPABASE_ACCESS_TOKEN': 'wrong-format'}, clear=True), self.assertRaisesRegex(RuntimeError, 'unavailable'):
            audit.access_token()

    def test_management_requests_keep_token_in_headers_and_use_the_selected_tls_trust(self):
        for custom, system_file, expected in [(None, True, '/etc/ssl/cert.pem'), (None, False, None), ('/fixture/trust.pem', False, '/fixture/trust.pem')]:
            env = {'SUPABASE_ACCESS_TOKEN': 'sbp_fixture_only'}
            if custom: env['SSL_CERT_FILE'] = custom
            with self.subTest(expected=expected), patch.dict(os.environ, env, clear=True), patch.object(audit.os.path, 'isfile', return_value=system_file), patch.object(audit.ssl, 'create_default_context', return_value='fixture-context') as tls, patch.object(audit.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"rows": []}')) as fetch:
                self.assertEqual(audit.management('database/query', {'query': 'select 1'}, 'POST'), {'rows': []})
                tls.assert_called_once_with(cafile=expected)
                request = fetch.call_args.args[0]
                self.assertEqual(request.full_url, f'https://api.supabase.com/v1/projects/{audit.PROJECT}/database/query')
                self.assertEqual(request.headers['Authorization'], 'Bearer sbp_fixture_only')
                self.assertEqual(json.loads(request.data), {'query': 'select 1'})
                self.assertEqual(fetch.call_args.kwargs, {'timeout': 45, 'context': 'fixture-context'})

    def test_management_errors_redact_credentials_and_query_parameters_and_limit_response_reads(self):
        body = io.BytesIO(b'eyJfixture.payload.signature sbp_fixture sb_secret_fixture sb_publishable_fixture ' + b'x' * 3000)
        error = urllib.error.HTTPError('https://fixture.invalid', 403, 'Forbidden', {}, body)
        with patch.object(audit, 'access_token', return_value='sbp_fixture_only'), patch.object(audit.ssl, 'create_default_context'), patch.object(audit.urllib.request, 'urlopen', side_effect=error), self.assertRaises(RuntimeError) as caught:
            audit.management('api-keys?private-query=must-not-appear')
        message = str(caught.exception)
        self.assertIn('api-keys returned HTTP 403', message); self.assertEqual(message.count('[redacted]'), 4)
        self.assertNotIn('fixture', message); self.assertNotIn('private-query', message); self.assertLess(len(message), 2100)
        self.assertEqual(body.tell(), 2000)

    def test_schema_and_all_audits_request_read_only_projections_without_printing_key_material(self):
        keys = [{'id': 'public-id', 'name': 'fixture-name', 'type': 'publishable', 'api_key': KEYS['publishable'], 'extra_secret': KEYS['secret']}]
        for section in ['schema', 'all']:
            requests = []
            def management(path, payload=None):
                requests.append((path, payload))
                return keys if path == 'api-keys?reveal=false' else []
            with self.subTest(section=section), patch.object(audit, 'management', side_effect=management), patch.object(sys, 'argv', ['audit', section]), contextlib.redirect_stdout(io.StringIO()) as output:
                audit.main()
                self.assertNotIn(KEYS['publishable'], output.getvalue()); self.assertNotIn(KEYS['secret'], output.getvalue())
                queries = [payload['query'] for path, payload in requests if path == 'database/query']
                self.assertTrue(all(sql.strip().lower().startswith('select ') for sql in queries))
                self.assertTrue(any('information_schema.columns' in sql for sql in queries))
                if section == 'all':
                    self.assertIn('public-id', output.getvalue())
                    self.assertTrue(any('relrowsecurity' in sql for sql in queries))
                    self.assertTrue(any('role_table_grants' in sql for sql in queries))
                    self.assertIn('advisors/security', [p for p, _ in requests])

    def test_log_audit_uses_seven_contiguous_bounded_windows_and_aggregated_counts(self):
        with patch.object(audit, 'management', return_value=[]) as management, patch.object(sys, 'argv', ['audit', 'logs']), contextlib.redirect_stdout(io.StringIO()):
            audit.main()
        self.assertEqual(management.call_count, 7)
        windows = [urllib.parse.parse_qs(call.args[0].split('?', 1)[1]) for call in management.call_args_list]
        for i, window in enumerate(windows):
            self.assertIn('count(*)', window['sql'][0]); self.assertIn('limit 500', window['sql'][0]); self.assertNotIn('select *', window['sql'][0])
            self.assertTrue(window['iso_timestamp_start'][0].endswith('Z'))
            if i: self.assertEqual(window['iso_timestamp_end'], windows[i - 1]['iso_timestamp_start'])

    def test_command_help_exits_without_keychain_or_network_access(self):
        for name in ['audit_supabase_security', 'rotate_supabase_keys']:
            with self.subTest(name=name), patch.dict(sys.modules, {'audit_supabase_security': audit}), patch.object(sys, 'argv', [name, '--help']), patch.object(audit.subprocess, 'run') as process, patch.object(audit.urllib.request, 'urlopen') as network, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
                runpy.run_path(str(ROOT / 'scripts' / (name + '.py')), run_name='__main__')
            self.assertEqual(result.exception.code, 0); process.assert_not_called(); network.assert_not_called()

    def test_signing_status_entrypoint_calls_the_read_only_action_without_printing_private_fields(self):
        with patch.dict(sys.modules, {'audit_supabase_security': audit}), patch.object(audit, 'management', return_value={'keys': [{'id': 'fixture', 'private_key': 'must-not-print'}]}) as request, patch.object(sys, 'argv', ['rotate_supabase_keys', 'signing-status']), contextlib.redirect_stdout(io.StringIO()) as output:
            runpy.run_path(str(ROOT / 'scripts/rotate_supabase_keys.py'), run_name='__main__')
        request.assert_called_once_with('config/auth/signing-keys')
        self.assertNotIn('must-not-print', output.getvalue()); self.assertIn('fixture', output.getvalue())


class KeyRotation(unittest.TestCase):
    def records(self): return [dict(type=kind, name=rotate.KEY_NAMES[kind], api_key=value, disabled=False) for kind, value in KEYS.items()]

    def test_replacement_keys_are_reused_or_created_with_explicit_service_role_template(self):
        with patch.object(rotate, 'management', return_value=self.records()) as management:
            self.assertEqual(rotate.keys(), KEYS); management.assert_called_once_with('api-keys?reveal=true')
        def management(path, payload=None, method=None):
            return [] if method is None else dict(payload, api_key=KEYS[payload['type']])
        with patch.object(rotate, 'management', side_effect=management) as request:
            self.assertEqual(rotate.keys(create=True), KEYS)
            self.assertEqual(request.call_args_list[-1].args, ('api-keys?reveal=true', {'type': 'secret', 'name': rotate.KEY_NAMES['secret'], 'secret_jwt_template': {'role': 'service_role'}}, 'POST'))
        for records in [[], [dict(self.records()[0], disabled=True)], [dict(self.records()[0], api_key='wrong-format')]]:
            with patch.object(rotate, 'management', return_value=records), self.assertRaisesRegex(RuntimeError, 'replacement publishable key unavailable'): rotate.keys()

    def test_compatibility_probes_use_only_the_supplied_headers_and_preserve_http_status(self):
        for bearer in [None, 'fixture-bearer']:
            response = MagicMock(); response.__enter__.return_value.status = 200
            with self.subTest(bearer=bearer), patch.object(rotate.ssl, 'create_default_context'), patch.object(rotate.urllib.request, 'urlopen', return_value=response) as request:
                self.assertEqual(rotate.probe(KEYS['publishable'], bearer), 200)
                sent = request.call_args.args[0]; self.assertEqual(sent.headers['Apikey'], KEYS['publishable'])
                self.assertEqual(sent.headers.get('Authorization'), None if bearer is None else 'Bearer fixture-bearer')
                self.assertTrue(sent.full_url.endswith('select=id&limit=0'))
        error = urllib.error.HTTPError('https://fixture.invalid', 401, 'Unauthorized', {}, io.BytesIO())
        with patch.object(rotate.ssl, 'create_default_context'), patch.object(rotate.urllib.request, 'urlopen', side_effect=error): self.assertEqual(rotate.probe('invalid'), 401)

    def test_aws_paramfiles_keep_secrets_out_of_process_arguments_and_are_private_and_removed(self):
        for returncode, stdout in [(0, '{"version": 1}'), (0, ''), (1, 'secret-output-must-not-appear')]:
            with self.subTest(returncode=returncode, stdout=stdout), tempfile.TemporaryDirectory() as folder, patch.object(rotate, 'ROOT', Path(folder)):
                captured = []
                def run(command, **options):
                    self.assertNotIn(KEYS['secret'], repr(command)); self.assertTrue(options['capture_output'])
                    path = Path(command[command.index('--cli-input-json') + 1].removeprefix('file://')); captured.append(path)
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(json.loads(path.read_text()), {'SecretString': KEYS['secret']})
                    return subprocess.CompletedProcess(command, returncode, stdout, 'private stderr')
                with patch.object(rotate.subprocess, 'run', side_effect=run):
                    if returncode:
                        with self.assertRaises(RuntimeError) as error: rotate.aws('secretsmanager', 'put-secret-value', {'SecretString': KEYS['secret']})
                        self.assertNotIn('secret-output', str(error.exception)); self.assertNotIn('private stderr', str(error.exception))
                    else: self.assertEqual(rotate.aws('secretsmanager', 'put-secret-value', {'SecretString': KEYS['secret']}), {'version': 1} if stdout else {})
                self.assertFalse(captured[0].exists())

    def test_prepare_probes_before_updating_only_public_local_configuration(self):
        for has_env in [True, False]:
            with tempfile.TemporaryDirectory() as folder, patch.object(rotate, 'keys', return_value=KEYS) as keys, patch.object(rotate, 'probe', return_value=200) as probe, contextlib.redirect_stdout(io.StringIO()) as output:
                root = Path(folder) / 'infra'; root.mkdir(); config = root / 'cdk.json'; config.write_text('{"context":{"keep":"original"}}')
                env = Path(folder) / 'jumpserve-front-end/.env.local'
                if has_env: env.parent.mkdir(); env.write_text('KEEP=original\nNEXT_PUBLIC_SUPABASE_ANON_KEY=old\n')
                with patch.object(rotate, 'ROOT', root): rotate.prepare()
                keys.assert_called_once_with(create=True); self.assertEqual(probe.call_count, 4)
                self.assertEqual(json.loads(config.read_text()), {'context': {'keep': 'original', 'supabaseAnonKey': KEYS['publishable']}})
                if has_env: self.assertEqual(env.read_text(), 'KEEP=original\nNEXT_PUBLIC_SUPABASE_ANON_KEY=' + KEYS['publishable'] + '\n')
                self.assertNotIn(KEYS['secret'], output.getvalue()); self.assertNotIn(KEYS['publishable'], output.getvalue())
        with patch.object(rotate, 'keys', return_value=KEYS), patch.object(rotate, 'probe', return_value=403), self.assertRaisesRegex(RuntimeError, 'probe returned 403'): rotate.prepare()

    def test_install_checks_account_and_paused_launcher_before_any_credential_write(self):
        for account, concurrency, message in [('wrong', 0, 'outside'), ('395567831870', 1, 'Pause')]:
            def aws(service, operation, payload): return {'Account': account} if service == 'sts' else {'ReservedConcurrentExecutions': concurrency}
            with self.subTest(account=account), patch.object(rotate, 'keys', return_value=KEYS), patch.object(rotate, 'aws', side_effect=aws) as calls, self.assertRaisesRegex(RuntimeError, message): rotate.install()
            self.assertFalse(any(call.args[1] in ['put-secret-value', 'put-role-policy'] for call in calls.call_args_list))

    def test_install_refreshes_only_known_project_consumers_with_revision_checks_and_retains_other_env(self):
        def aws(service, operation, payload):
            if operation == 'get-caller-identity': return {'Account': '395567831870'}
            if operation == 'get-function-concurrency': return {'ReservedConcurrentExecutions': 0}
            if operation == 'list-functions': return {'Functions': [{'FunctionName': name} for name in ['OtherStack-function', 'JumpServeBenchmarkStack-active', 'JumpServeAgentStack-active', 'JumpServeBenchmarkStack-other-project']]}
            if operation == 'get-function-configuration':
                name = payload['FunctionName']
                env = {'SUPABASE_URL': f'https://{rotate.PROJECT}.supabase.co/', 'KEEP': 'retained'}
                if name.endswith('other-project'): env['SUPABASE_URL'] = 'https://different-project.example.test'
                if name.startswith('JumpServeBenchmarkStack'): env['SUPABASE_ANON_KEY'] = 'old'
                return {'RevisionId': 'fixture-revision', 'Environment': {'Variables': env}}
            if operation == 'get-app': return {'app': {'environmentVariables': {'KEEP': 'retained'}}}
            if operation == 'get-branch': return {'branch': {}}
            if operation == 'start-job': return {'jobSummary': {'jobId': 'fixture-job'}}
            return {}
        with patch.object(rotate, 'keys', return_value=KEYS), patch.object(rotate, 'aws', side_effect=aws) as calls, contextlib.redirect_stdout(io.StringIO()) as output:
            rotate.install()
        updates = [call.args[2] for call in calls.call_args_list if call.args[1] == 'update-function-configuration']
        self.assertEqual(len(updates), 2)
        self.assertTrue(all(update['RevisionId'] == 'fixture-revision' for update in updates))
        self.assertTrue(all(update['Environment']['Variables']['KEEP'] == 'retained' for update in updates))
        self.assertEqual(updates[0]['Environment']['Variables']['SUPABASE_ANON_KEY'], KEYS['publishable'])
        self.assertNotIn('SUPABASE_ANON_KEY', updates[1]['Environment']['Variables'])
        operations = [call.args[1] for call in calls.call_args_list]
        self.assertLess(operations.index('put-role-policy'), operations.index('put-secret-value'))
        self.assertEqual(operations[-1], 'start-job')
        self.assertNotIn(KEYS['secret'], output.getvalue()); self.assertNotIn(KEYS['publishable'], output.getvalue())

    def test_revoke_requires_both_legacy_denial_and_healthy_replacements_and_reconciles_already_disabled(self):
        legacy = 'fixture-legacy'
        for already_disabled in [False, True]:
            def management(path, *args, **kwargs):
                if path == 'api-keys?reveal=true': return [{'id': 'service_role', 'api_key': legacy}]
                if already_disabled: raise RuntimeError('HTTP 422 keys were already disabled')
                return {}
            with patch.object(rotate, 'management', side_effect=management), patch.object(rotate, 'keys', return_value=KEYS), patch.object(rotate, 'probe', side_effect=[401, 403, 200, 200]) as probe, contextlib.redirect_stdout(io.StringIO()) as output:
                rotate.revoke()
                self.assertEqual(probe.call_args_list[1].args, (KEYS['publishable'], legacy))
                self.assertNotIn(legacy, output.getvalue())
        for statuses, message in [([200], 'Revocation verification'), ([401, 403, 500], 'Replacement publishable key stopped')]:
            with patch.object(rotate, 'management', return_value=[{'id': 'service_role', 'api_key': legacy}]), patch.object(rotate, 'keys', return_value=KEYS), patch.object(rotate, 'probe', side_effect=statuses), contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, message): rotate.revoke()
        with patch.object(rotate, 'management', side_effect=[[{'id': 'service_role', 'api_key': legacy}], RuntimeError('HTTP 500 fixture')]), self.assertRaisesRegex(RuntimeError, 'HTTP 500'): rotate.revoke()

    def test_signing_rotation_reuses_standby_and_refuses_legacy_revocation_before_new_key_is_active(self):
        active = {'id': 'active', 'status': 'in_use', 'algorithm': 'ES256'}
        standby = {'id': 'standby', 'status': 'standby', 'algorithm': 'ES256'}
        for current in [[active], [standby], [{'id': 'old', 'status': 'in_use', 'algorithm': 'HS256'}], []]:
            writes = []
            def management(path, payload=None, method=None):
                if method: writes.append((path, payload, method)); return standby
                return {'keys': current or [standby]}
            # Explicitly return an empty first inventory to exercise legacy-key registration.
            seen = [False]
            def request(path, payload=None, method=None):
                if not current and not method and not seen[0]: seen[0] = True; return {'keys': []}
                return management(path, payload, method)
            with self.subTest(current=current), patch.object(rotate, 'management', side_effect=request), contextlib.redirect_stdout(io.StringIO()): rotate.rotate_signing()
            if current == [active]: self.assertEqual(writes, [])
            else: self.assertEqual(writes[-1], ('config/auth/signing-keys/standby', {'status': 'in_use'}, 'PATCH'))
        with patch.object(rotate, 'management', return_value={'keys': [standby]}), patch.object(rotate, 'revoke') as revoke, self.assertRaisesRegex(RuntimeError, 'Rotate to ES256'): rotate.revoke_signing()
        revoke.assert_not_called()
        for status in ['in_use', 'revoked']:
            with patch.object(rotate, 'management', side_effect=[{'keys': [active]}, {'id': 'old', 'status': status}, {}]) as request, patch.object(rotate, 'revoke') as revoke:
                rotate.revoke_signing(); revoke.assert_called_once()
                self.assertEqual(request.call_count, 2 if status == 'revoked' else 3)
        with patch.object(rotate, 'management', return_value={'keys': [dict(active, private_key='must-not-print')]}), contextlib.redirect_stdout(io.StringIO()) as output:
            rotate.signing_status(); self.assertNotIn('must-not-print', output.getvalue()); self.assertIn('ES256', output.getvalue())


if __name__ == '__main__': unittest.main()
