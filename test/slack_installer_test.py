"""Production installer decisions in a temporary filesystem with synthetic services."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('slack_installer', ROOT / 'assets/platform/install-slack-gateway.py')
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
INTEGRITY = 'sha512-AzWaSLfUQZWPwDdrLXzXeQ/AraXPEnkTTWKTKq4MFO39futFAxy+FulsYSStDYEd1B0YjtWGvXswBjdrmwRlBw=='


class InstallationFixture:
    def __init__(self, test, *, activate=False, existing=False, change=None):
        self.test = test; self.activate = activate; self.existing = existing; self.change = change or {}

    def __enter__(self):
        self.stack = contextlib.ExitStack()
        try: return self.prepare()
        except BaseException:
            self.stack.close(); raise

    def prepare(self):
        folder = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='slack-installer-unit-'))
        self.root = Path(folder).resolve(); self.base = self.root / 'var/lib/jumpserve-platform-slack'
        self.base.mkdir(parents=True); (self.base / 'install').mkdir()
        self.cli = self.root / 'opt/jumpserve/openclaw/openclaw.mjs'; self.cli.parent.mkdir(parents=True)
        (self.cli.parent / 'package.json').write_text(json.dumps({'version': self.change.get('openclaw', '2026.10.5')}))
        self.vendor = self.base / 'state/extensions/slack'; self.vendor.mkdir(parents=True)
        (self.vendor / 'package.json').write_text(json.dumps({'version': self.change.get('plugin_version', '2026.10.5')}))
        env = self.root / 'etc/jumpserve-platform.env'; env.parent.mkdir(parents=True)
        self.secret = 'arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/supabase-service-key-Ab1234'
        env.write_text("IGNORED LINE\nSUPABASE_SECRET_ARN='" + self.change.get('secret_arn', self.secret) + "'\n")
        systemd = self.root / 'etc/systemd/system'; systemd.mkdir(parents=True)
        if self.existing: (systemd / 'jumpserve-platform-slack.service').write_text('prior unit')
        source = {name: ('# synthetic original ' + name + '\n').encode() for name in installer.FILES if name != 'qualification.json'}
        source['slack-channel-policy.json'] = b'{"fixture":true}'
        proof = {'passed': True, 'node_version': '24.16.0', 'openclaw_version': '2026.10.5',
                 'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in source.items()}}
        proof.update(self.change.get('proof', {})); source['qualification.json'] = json.dumps(proof).encode()
        if 'source_bytes' in self.change: source.update(self.change['source_bytes'])
        if 'remove' in self.change: del source[self.change['remove']]
        if 'extra' in self.change: source['unexpected.py'] = b'pass\n'
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, 'w') as archive:
            for name, raw in source.items():
                member = zipfile.ZipInfo(name)
                if self.change.get('symlink') == name: member.create_system = 3; member.external_attr = 0o120777 << 16
                archive.writestr(member, raw)
            if self.change.get('duplicate'):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning); archive.writestr('slack_gateway.py', source['slack_gateway.py'])
        raw = memory.getvalue(); self.sha = hashlib.sha256(raw).hexdigest()
        (self.base / 'install' / (self.sha + '.zip')).write_bytes(b'changed original' if self.change.get('bundle_hash') else raw)
        self.release = self.root / 'opt/jumpserve/platform-slack-releases' / self.sha
        if self.change.get('frozen_source'):
            self.release.mkdir(parents=True); (self.release / 'slack_gateway.py').write_text('different existing bytes')
        if self.existing:
            (self.base / 'openclaw.json').write_text(json.dumps({'plugins': {'installs': {'retained': {}}, 'entries': {'slack': {'enabled': True, 'config': 'retained'}}}}))
            (self.base / 'slack-plugin-installed.json').write_text('{}')
            link = self.root / 'opt/jumpserve/platform-slack'; link.symlink_to(self.root / 'prior-release', target_is_directory=True)
            (self.root / 'opt/jumpserve/platform-slack.next').symlink_to(self.root / 'stale-next', target_is_directory=True)
        if self.change.get('unversioned'):
            (self.root / 'opt/jumpserve/platform-slack').mkdir()
        self.gateway = types.ModuleType('slack_gateway'); self.gateway.TOOLS = ('fixture_tool',)
        self.gateway.configuration = MagicMock(return_value={'plugins': {'load': {'paths': []}, 'entries': {}}})
        self.gateway.canonical = lambda value: json.dumps(value, sort_keys=True).encode()
        self.gateway.write_configuration = MagicMock()
        self.gateway.verify_operations = MagicMock(side_effect=ValueError('contract not installed') if self.change.get('operations') else None)
        self.credentials = MagicMock(); self.store = MagicMock()
        credentials_module = types.ModuleType('platform_supervisor.credentials'); credentials_module.Credentials = self.credentials
        store_module = types.ModuleType('platform_supervisor.store'); store_module.Store = self.store
        package = types.ModuleType('platform_supervisor'); package.__path__ = []
        self.stack.enter_context(patch.dict(sys.modules, {'slack_gateway': self.gateway, 'platform_supervisor': package,
            'platform_supervisor.credentials': credentials_module, 'platform_supervisor.store': store_module}))
        self.commands = []
        self.stack.enter_context(patch.object(installer, 'run', side_effect=self.run))
        self.stack.enter_context(patch.object(installer, 'BASE', self.base))
        self.stack.enter_context(patch.object(installer, 'CLI', self.cli))
        self.stack.enter_context(patch.object(installer, 'NODE', self.root / 'opt/jumpserve/node/bin/node'))
        self.stack.enter_context(patch.object(installer.os, 'geteuid', return_value=self.change.get('euid', 0)))
        self.stack.enter_context(patch.object(installer.os, 'chown'))
        self.stack.enter_context(patch.object(installer.os, 'umask'))
        self.stack.enter_context(patch.object(installer.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=1234, pw_gid=1235)))
        self.stack.enter_context(patch.object(installer, 'Path', self.path))
        self.stack.enter_context(patch.object(sys, 'path', list(sys.path)))
        argv = ['install-slack-gateway.py', self.change.get('argument_sha', self.sha)] + (['--activate'] if self.activate else [])
        self.stack.enter_context(patch.object(sys, 'argv', argv))
        self.output = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        return self

    def __exit__(self, *args): return self.stack.__exit__(*args)

    def path(self, value):
        raw = str(value)
        if raw.startswith(str(self.root)): return Path(value)
        self.test.assertTrue(raw.startswith(('/opt/jumpserve/', '/etc/')), f'Unexpected filesystem target {raw}')
        return self.root / raw.lstrip('/')

    def run(self, command, **options):
        self.commands.append((command, options))
        if command[:2] == ['aws', 'sts']: return json.dumps({'Account': self.change.get('account', '395567831870')}).encode()
        if command[-1] == '--version': return self.change.get('node', b'v24.16.0\n')
        if 'inspect' in command:
            index = command.index('inspect'); name = command[index + 1]
            if '--runtime' not in command:
                return json.dumps({'install': {'integrity': self.change.get('integrity', INTEGRITY)}, 'plugin': {'rootDir': str(self.root if self.change.get('outside_vendor') else self.vendor)}}).encode()
            return json.dumps({'plugin': {'status': self.change.get('plugin_status', 'loaded'),
                'toolNames': ['wrong'] if self.change.get('tools') else list(self.gateway.TOOLS),
                'trustedOfficialInstall': not self.change.get('untrusted')}}).encode()
        if 'validate' in command: return json.dumps({'valid': not self.change.get('configuration')}).encode()
        return b''


class SlackInstaller(unittest.TestCase):
    def test_stage_validates_exact_bundle_and_native_plugins_without_activating_a_service(self):
        with InstallationFixture(self) as fixture:
            installer.main()
            report = json.loads(fixture.output.getvalue()); self.assertTrue(report['staged']); self.assertFalse(report['service_started'])
            self.assertEqual(report['bundle_sha256'], fixture.sha)
            self.assertFalse(any(command[0] == 'systemctl' for command, _ in fixture.commands))
            fixture.gateway.verify_operations.assert_not_called(); fixture.credentials.assert_not_called()
            fixture.gateway.write_configuration.assert_called_once()
            written = fixture.gateway.write_configuration.call_args
            self.assertEqual(written.args[1], fixture.base / 'qualified-config.json'); self.assertTrue(written.kwargs['run_as_user'])
            self.assertEqual((fixture.base / 'qualified-config.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual((fixture.base / 'openclaw.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual((fixture.release / 'slack_gateway.py').stat().st_mode & 0o777, 0o644)
            self.assertIn('@openclaw/slack@2026.10.5', repr(fixture.commands))
            for command, options in fixture.commands:
                if 'env' in options:
                    self.assertEqual(options['env']['SLACK_BOT_TOKEN'], 'xoxb-synthetic-offline')
                    self.assertEqual(options['env']['OPENCLAW_SKIP_CHANNELS'], '1')

    def test_activation_qualifies_rpc_first_retains_state_and_switches_only_the_slack_service(self):
        for existing in [False, True]:
            with self.subTest(existing=existing), InstallationFixture(self, activate=True, existing=existing) as fixture:
                installer.main(); report = json.loads(fixture.output.getvalue())
                self.assertTrue(report['installed']); self.assertFalse(report['research_worker_restarted']); self.assertFalse(report['platform_worker_restarted'])
                self.assertFalse(report['live_slack_conversation_verified'])
                fixture.gateway.verify_operations.assert_called_once_with(fixture.store.return_value)
                self.assertEqual(fixture.gateway.write_configuration.call_count, 2)
                link = fixture.root / 'opt/jumpserve/platform-slack'; self.assertTrue(link.is_symlink()); self.assertEqual(link.resolve(), fixture.release)
                self.assertFalse((fixture.root / 'opt/jumpserve/platform-slack.next').is_symlink())
                env = fixture.root / 'etc/jumpserve-platform-slack.env'; self.assertEqual(env.stat().st_mode & 0o777, 0o600)
                self.assertIn('SUPABASE_SECRET_ARN=' + fixture.secret, env.read_text())
                commands = [command for command, _ in fixture.commands if command[0] == 'systemctl']
                self.assertEqual(commands[-3:], [['systemctl', 'daemon-reload'], ['systemctl', 'enable', '--now', 'jumpserve-platform-slack.service'], ['systemctl', 'is-active', '--quiet', 'jumpserve-platform-slack.service']])
                self.assertEqual(any(command[1] == 'stop' for command in commands), existing)
                if existing:
                    self.assertFalse(any('install' in command for command, _ in fixture.commands))
                    candidate = fixture.gateway.write_configuration.call_args.args[0]
                    self.assertEqual(candidate['plugins']['installs'], {'retained': {}})
                    self.assertEqual(candidate['plugins']['entries']['slack']['config'], 'retained')

    def test_incomplete_root_identity_or_bundle_checks_never_reach_service_or_secret_operations(self):
        cases = [({'euid': 1000}, 'Root'), ({'argument_sha': 'bad'}, 'exact qualified'), ({'account': 'wrong'}, 'account differs'),
                 ({'bundle_hash': True}, 'Bundle hash'), ({'remove': 'slack_gateway.py'}, 'inventory'), ({'extra': True}, 'inventory'),
                 ({'duplicate': True}, 'inventory'), ({'symlink': 'slack_gateway.py'}, 'Unsupported'),
                 ({'source_bytes': {'slack_gateway.py': b'x' * 5000001}}, 'Unsupported'), ({'frozen_source': True}, 'frozen source')]
        for change, message in cases:
            with self.subTest(change=list(change)), InstallationFixture(self, activate=True, change=change) as fixture:
                with self.assertRaisesRegex(ValueError, message): installer.main()
                fixture.gateway.verify_operations.assert_not_called(); fixture.store.assert_not_called()
                self.assertFalse(any(command[0] == 'systemctl' for command, _ in fixture.commands))

    def test_qualification_native_versions_plugin_provenance_and_tool_registration_are_all_required(self):
        cases = [({'proof': {'passed': False}}, 'Qualified native'), ({'proof': {'node_version': 'wrong'}}, 'Qualified native'),
                 ({'proof': {'files': {'unknown.py': 'a' * 64}}}, 'source identity'), ({'proof': {'files': {}}}, 'source inventory'),
                 ({'source_bytes': {'slack_gateway.py': b'changed bytes'}}, 'source identity'), ({'node': b'v22\n'}, 'Node version'),
                 ({'openclaw': 'wrong'}, 'OpenClaw version'), ({'secret_arn': 'wrong'}, 'secret target'),
                 ({'integrity': 'wrong'}, 'integrity'), ({'outside_vendor': True}, 'state is not isolated'),
                 ({'plugin_version': 'wrong'}, 'plugin version'), ({'configuration': True}, 'configuration validation'),
                 ({'plugin_status': 'error'}, 'failed to load'), ({'tools': True}, 'tool registration'), ({'untrusted': True}, 'provenance')]
        for change, message in cases:
            with self.subTest(change=change), InstallationFixture(self, activate=True, change=change) as fixture:
                with self.assertRaisesRegex(ValueError, message): installer.main()
                self.assertFalse(any(command[0] == 'systemctl' for command, _ in fixture.commands))

    def test_rpc_contract_failure_preserves_the_running_service_and_unversioned_installs_require_reconciliation(self):
        with InstallationFixture(self, activate=True, existing=True, change={'operations': True}) as fixture:
            with self.assertRaisesRegex(ValueError, 'contract not installed'): installer.main()
            self.assertFalse(any(command[0] == 'systemctl' for command, _ in fixture.commands))
        with InstallationFixture(self, activate=True, change={'unversioned': True}) as fixture:
            with self.assertRaisesRegex(ValueError, 'needs reconciliation'): installer.main()
            self.assertFalse(any(command[:2] == ['systemctl', 'enable'] for command, _ in fixture.commands))

    def test_fixed_check_failures_keep_bounded_diagnostics_private_and_never_return_success(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(installer, 'BASE', Path(folder)):
            result = types.SimpleNamespace(returncode=1, stdout=b'a' * 500001, stderr=b'b' * 500001)
            with patch.object(installer.subprocess, 'run', return_value=result) as run, self.assertRaisesRegex(RuntimeError, 'private installer log'):
                installer.run(['node', 'fixed-check', '--json', 'must-not-print-argument'])
            run.assert_called_once_with(['node', 'fixed-check', '--json', 'must-not-print-argument'], capture_output=True, timeout=300)
            log = Path(folder) / 'installer.log'; self.assertEqual(log.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(b'must-not-print-argument', log.read_bytes()); self.assertLess(len(log.read_bytes()), 1000100)
            with patch.object(installer.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=b'passed')):
                self.assertEqual(installer.run(['node', '--version']), b'passed')


if __name__ == '__main__': unittest.main()
