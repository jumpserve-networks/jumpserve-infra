"""Initial supervisor preparation and dispatch using synthetic cloud/DB adapters.

Real source packages, private review packets, OCI blobs and dispatch journals are
used. No AWS, GitHub, Supabase, Docker or service process is contacted.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('platform_bootstrap_unit', ROOT / 'bin/platform-supervisor.py')
bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)
ASSETS = ['jumpserve-platform.service', 'install-platform.sh', 'qualify-platform-host.py', 'reconcile-platform-host.py', 'qualify-retained-control.py', 'Dockerfile', 'research-runtime-gate.py', 'research-runtime-checks.py', 'supervisor-runtime-gate.py', 'captured-failure-runtime-gate.py', 'captured-failure-runtime-checks.py']


class PlatformBootstrap(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='platform-bootstrap-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name) / 'infra'; self.back = self.root.parent / 'backend'
        self.root.mkdir(); (self.back / 'platform_supervisor').mkdir(parents=True); (self.root / 'database').mkdir(); (self.root / 'assets/platform').mkdir(parents=True)
        self.enterContext(patch.object(bootstrap, 'ROOT', self.root)); self.enterContext(patch.object(bootstrap, 'BACK', self.back))
        self.policy = dict(version='synthetic-authority-v1', repositories=['jumpserve-networks/jumpserve-' + name for name in ['front-end', 'back-end', 'infra']])
        (self.back / 'platform_supervisor/policy.json').write_text(json.dumps(self.policy)); (self.back / 'platform_supervisor/worker.py').write_bytes(b'# Synthetic source, never executed\n')
        for name in ASSETS: (self.root / 'assets/platform' / name).write_bytes(('# Synthetic retained ' + name + '\n').encode())
        (self.back / 'platform_supervisor/Dockerfile').write_bytes((self.root / 'assets/platform/Dockerfile').read_bytes())
        for name in bootstrap.MIGRATIONS: (self.root / 'database' / name).write_text('-- Synthetic migration ' + name)
        self.worker = 'i-087f1493809643115'; self.metadata = dict(HttpTokens='required', HttpPutResponseHopLimit=1, State='applied'); self.account = '395567831870'
        self.secret = {'Name': 'jumpserve/platform-supervisor', 'ARN': 'arn:aws:secretsmanager:us-east-1:395567831870:secret:SyntheticSupervisor'}
        self.cloud, self.commands, self.sql = [], [], []; self.dispatched, self.invocations = [], {}; self.dispatch_error = False; self.existing_migrations = True; self.authority_changed = False; self.paused = True; self.dirty = False; self.main_revision = 'a' * 40; self.check_passed = True
        self.aws = self.enterContext(patch.object(bootstrap, 'aws', side_effect=self.cloud_call)); self.run = self.enterContext(patch.object(bootstrap.subprocess, 'run', side_effect=self.command)); self.output = self.enterContext(patch.object(bootstrap.subprocess, 'check_output', side_effect=self.check_output))
        self.db = MagicMock(); self.db.query.side_effect = self.query; self.db.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"; self.enterContext(patch.object(bootstrap, 'admin', return_value=self.db))
        self.owners = self.root / 'owners.json'; self.owners.write_text('["owner@example.test"]'); self.directory = self.root / 'prepared'

    def check_output(self, command, **options):
        if command == ['git', 'rev-parse', 'HEAD']: return 'a' * 40 + '\n'
        if command == ['git', 'status', '--porcelain']: return ' M worker.py\n' if self.dirty else ''
        if command[-1] == 'repos/jumpserve-networks/jumpserve-back-end/commits/main': return json.dumps({'sha': self.main_revision})
        if '/check-runs?' in command[-1]: return json.dumps({'check_runs': [dict(name='Platform validation', conclusion='success' if self.check_passed else 'failure')]})
        if command[:2] == ['gh', 'api']: return json.dumps(dict(use_immutable_subject=False, use_default=True, sub_claim_prefix='repo:jumpserve-networks/jumpserve-infra')).encode()
        raise AssertionError(command)
    def command(self, command, **options):
        self.commands.append((command, options)); self.assertEqual(command[:2], ['npx', 'cdk']); self.assertEqual(options['cwd'], self.root); self.assertTrue(options['check']); return subprocess.CompletedProcess(command, 0)
    def cloud_call(self, service, action, *arguments, **options):
        self.cloud.append((service, action, arguments))
        if (service, action) == ('sts', 'get-caller-identity'): return {'Account': self.account}
        if (service, action) == ('cloudformation', 'list-stack-resources'): return {'StackResourceSummaries': [dict(ResourceType='AWS::EC2::Instance', PhysicalResourceId=self.worker), dict(ResourceType='AWS::IAM::Role', PhysicalResourceId='JumpServeOpenClawStack-SyntheticRole')]}
        if (service, action) == ('ec2', 'describe-instances'): return {'Reservations': [{'Instances': [{'MetadataOptions': copy.deepcopy(self.metadata)}]}]}
        if (service, action) == ('ec2', 'modify-instance-metadata-options'): return {'requested': True}
        if (service, action) == ('ssm', 'get-command-invocation'): return self.invocations[arguments[1]]
        if (service, action) == ('ssm', 'list-commands'): return {'Commands': self.dispatched}
        if (service, action) == ('ssm', 'send-command'):
            identity = 'synthetic-install-' + str(len(self.dispatched)); self.dispatched.append({'CommandId': identity, 'Comment': arguments[arguments.index('--comment') + 1], 'InstanceIds': [self.worker]})
            if not self.dispatched[-1]['Comment'].startswith('supervisor-baseline-'): self.assertTrue((self.directory / 'install-intent.json').exists(), 'Dispatch intent must survive a lost acknowledgment')
            if self.dispatch_error: raise subprocess.CalledProcessError(1, ['synthetic AWS command'])
            return {'Command': {'CommandId': identity}}
        if (service, action) == ('secretsmanager', 'list-secrets'): return {'SecretList': [self.secret] if self.secret else []}
        if (service, action) == ('s3api', 'put-object'): return {'recorded': True}
        if (service, action) == ('s3api', 'head-object'): raise subprocess.CalledProcessError(1, ['synthetic missing object'])
        if (service, action) == ('s3', 'cp'): return None
        if (service, action) == ('secretsmanager', 'get-secret-value'): return {'SecretString': self.github_token}
        raise AssertionError((service, action, arguments, options))
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.endswith(' is not null present'): return [{'present': self.existing_migrations}]
        if sql.startswith('-- Synthetic migration '): self.assertFalse(options['read_only']); return []
        if sql.startswith(('insert into public.platform_operator_enrollments', 'insert into public.platform_authorizations', 'update public.platform_settings')): self.assertFalse(options['read_only']); return []
        if sql.startswith('select policy_sha256 from public.platform_authorizations'): return [{'policy_sha256': 'changed' if self.authority_changed else self.packet['policy_sha256']}]
        if sql == 'select paused from public.platform_settings where id': return [{'paused': self.paused}]
        if sql.startswith('select public.platform_supervisor_activate('): self.assertFalse(options['read_only']); return [{'activated': True}]
        raise AssertionError('Unexpected SQL: ' + sql)
    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.prepare(self.owners, self.directory)
        self.packet_path = self.directory / 'private-packet.json'; self.packet = json.loads(self.packet_path.read_bytes()); return json.loads(output.getvalue())
    def qualified(self):
        self.prepare(); report = dict(passed=True, live=True, recipe_sha256=bootstrap.sha((self.root / 'assets/platform/Dockerfile').read_bytes()), actual_provider_calls=2, existing_test_unchanged=True, container_check_passed=True, image='sha256:' + 'b' * 64, bundle_sha256=self.packet['bundle_sha256'])
        self.qualification = dict(command_id='synthetic-qualification', report=report, source_files=copy.deepcopy(self.packet['files'])); (self.directory / 'cloud-qualified.json').write_text(json.dumps(self.qualification)); self.invocations['synthetic-qualification'] = dict(Status='Success', StandardOutputContent='Retained diagnostic\n' + json.dumps(report) + '\n'); return report
    def local_image(self, report=True):
        self.prepare(); folder = self.back / '.test-artifacts/platform-native'; (folder / 'qualification').mkdir(parents=True)
        path, image, _ = SavedImageIdentity().archive(self.directory); path.rename(self.directory / 'platform-image.tar.gz')
        value = dict(recipe_sha256=bootstrap.sha((self.back / 'platform_supervisor/Dockerfile').read_bytes()), image=image); (folder / 'image.json').write_text(json.dumps(value))
        (folder / 'qualification/report.json').write_text(json.dumps(dict(passed=report, live=report, image=image))); return folder

    def test_preparation_packages_exact_source_deterministically_and_keeps_owners_private_and_admission_paused(self):
        source = self.back / 'platform_supervisor'; (source / 'notes.txt').write_text('Not runtime code'); (source / 'directory').mkdir(); (source / 'linked.py').symlink_to(source / 'worker.py')
        result = self.prepare(); self.assertTrue(result['prepared']); self.assertFalse(result['aws_static_keys']); self.assertFalse(result['worker_replaced']); self.assertTrue(result['initially_paused']); self.assertNotIn('owner@example.test', json.dumps(result))
        self.assertEqual(self.packet_path.stat().st_mode & 0o777, 0o600); self.assertEqual(self.packet['owners'], ['owner@example.test']); self.assertEqual(self.packet['backend_revision'], 'a' * 40)
        raw = (self.directory / 'runtime.zip').read_bytes(); self.assertEqual(bootstrap.validate(self.packet), raw); self.assertEqual(bootstrap.package()[0], raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), set(self.packet['files'])); self.assertNotIn('platform_supervisor/linked.py', archive.namelist()); self.assertNotIn('platform_supervisor/notes.txt', archive.namelist()); self.assertNotIn('owner@example.test', str(archive.namelist()))
            for name, expected in self.packet['files'].items(): self.assertEqual(bootstrap.sha(archive.read(name)), expected); self.assertEqual(archive.getinfo(name).date_time, (1980, 1, 1, 0, 0, 0))
        self.assertIn('synth', self.commands[0][0]); self.assertIn('JumpServePlatformAccessStack', self.commands[0][0]); self.assertFalse(any(c[1] in ['modify-instance-metadata-options', 'send-command', 'put-object'] for c in self.cloud))

    def test_complete_migration_inventory_is_resumable_and_authority_is_immutable(self):
        self.prepare()
        for exists in [True, False]:
            self.existing_migrations = exists; self.sql.clear()
            with contextlib.redirect_stdout(io.StringIO()): bootstrap.migrate(self.packet)
            markers = [sql for sql, _ in self.sql if sql.endswith(' is not null present')]; self.assertEqual(len(markers), len(bootstrap.MIGRATIONS)); self.assertTrue(any('platform_capability_worker' in sql for sql in markers))
            applied = [sql for sql, _ in self.sql if sql.startswith('-- Synthetic migration')]; self.assertEqual(len(applied), 0 if exists else len(bootstrap.MIGRATIONS)); self.assertTrue(any('paused=true' in sql for sql, _ in self.sql))
        self.authority_changed = True
        with self.assertRaisesRegex(ValueError, 'immutable authority differs'): bootstrap.migrate(self.packet)
        self.assertFalse(self.sql[-1][0].startswith('update public.platform_settings'))

    def test_invalid_owners_targets_oidc_and_changed_recipes_stop_preparation(self):
        for owners in [None, [], ['Owner@example.test'], ['owner@example.test'] * 2, ['invalid'], ['x' + str(i) + '@example.test' for i in range(21)]]:
            self.owners.write_text(json.dumps(owners))
            with self.subTest(owners=owners), self.assertRaisesRegex(ValueError, 'owner address list'): bootstrap.prepare(self.owners, self.directory)
        self.owners.write_text('["owner@example.test"]'); self.account = 'other'
        with self.assertRaisesRegex(ValueError, 'AWS target differs'): bootstrap.prepare(self.owners, self.directory)
        self.account = '395567831870'; self.worker = 'i-other'
        with self.assertRaisesRegex(ValueError, 'Worker target differs'): bootstrap.prepare(self.owners, self.directory)
        self.worker = 'i-087f1493809643115'
        with patch.object(bootstrap.subprocess, 'check_output', return_value=b'{"use_default":false}'), self.assertRaisesRegex(ValueError, 'OIDC subject format'): bootstrap.prepare(self.owners, self.directory)
        (self.back / 'platform_supervisor/Dockerfile').write_bytes(b'Changed recipe')
        with self.assertRaisesRegex(ValueError, 'recipes differ'): bootstrap.prepare(self.owners, self.directory)

    def test_source_policy_and_fixed_target_changes_invalidate_the_packet(self):
        self.prepare()
        for field, value in [('aws_account', 'other'), ('supabase_project', 'other'), ('bucket', 'other'), ('policy_sha256', '0' * 64), ('policy', {'version': 'other'}), ('files', {})]:
            packet = dict(self.packet, **{field: value})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'source changed|authorization differs'): bootstrap.validate(packet)
        (self.back / 'platform_supervisor/worker.py').write_bytes(b'Changed source')
        with self.assertRaisesRegex(ValueError, 'platform source changed'): bootstrap.validate(self.packet)

    def test_metadata_hardening_is_requested_only_when_needed_and_never_claims_verification(self):
        self.prepare()
        for tokens, hops, modifications in [('required', 1, 0), ('optional', 1, 1), ('required', 2, 1)]:
            self.metadata.update(HttpTokens=tokens, HttpPutResponseHopLimit=hops); self.cloud.clear()
            with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.harden(self.packet)
            self.assertEqual(sum(c[1] == 'modify-instance-metadata-options' for c in self.cloud), modifications); self.assertTrue(json.loads(output.getvalue())['verification_required'])

    def test_access_and_repository_protection_keep_exact_reviewed_roles_and_required_checks(self):
        self.prepare(); bootstrap.access(self.packet); command, options = self.commands[-1]; self.assertIn('deploy', command); self.assertIn('JumpServePlatformAccessStack', command); self.assertIn('platformWorkerRoleName=' + self.packet['worker_role'], command); self.assertEqual(options['timeout'], 900)
        calls = []
        def protect(command, **options):
            calls.append((command, options)); return subprocess.CompletedProcess(command, 0)
        with patch.object(bootstrap.subprocess, 'run', side_effect=protect), contextlib.redirect_stdout(io.StringIO()): bootstrap.protect(self.packet)
        self.assertEqual(len(calls), 3)
        for (command, options), repository in zip(calls, self.policy['repositories']):
            self.assertIn('repos/' + repository + '/branches/main/protection', command); body = json.loads(options['input']); self.assertEqual(body['required_status_checks'], {'strict': True, 'contexts': ['Platform validation']}); self.assertTrue(body['enforce_admins']); self.assertFalse(body['allow_force_pushes']); self.assertFalse(body['allow_deletions'])

    def test_cloud_install_requires_exact_successful_live_qualification_and_metadata_isolation(self):
        report = self.qualified()
        mutations = [dict(passed=False), dict(live=False), dict(recipe_sha256='0' * 64), dict(actual_provider_calls=0), dict(actual_provider_calls=7), dict(existing_test_unchanged=False), dict(container_check_passed=False), dict(image='image:latest')]
        for change in mutations:
            bad = dict(report, **change); self.qualification['report'] = bad; (self.directory / 'cloud-qualified.json').write_text(json.dumps(self.qualification)); self.invocations['synthetic-qualification']['StandardOutputContent'] = json.dumps(bad)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'source-bound cloud software control'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.qualification['report'] = report; (self.directory / 'cloud-qualified.json').write_text(json.dumps(self.qualification)); self.invocations['synthetic-qualification']['StandardOutputContent'] = json.dumps(report)
        self.paused = False
        with self.assertRaisesRegex(ValueError, 'Pause admission'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.paused = True; self.metadata['State'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'Applied metadata isolation'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.metadata['State'] = 'applied'; self.secret = None
        with self.assertRaisesRegex(ValueError, 'publisher service secret'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.assertFalse(self.dispatched)

    def test_lost_cloud_install_acknowledgment_reconciles_exact_original_command_without_redispatch(self):
        self.qualified(); self.dispatch_error = True
        with self.assertRaises(subprocess.CalledProcessError): bootstrap.install_cloud(self.packet, self.packet_path)
        self.assertEqual(len(self.dispatched), 1); self.assertFalse((self.directory / 'install-command.json').exists()); self.assertTrue((self.directory / 'install-intent.json').exists())
        self.dispatch_error = False
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.install_cloud(self.packet, self.packet_path)
        self.assertEqual(json.loads(output.getvalue()), dict(command_id=self.dispatched[0]['CommandId'], reconciled=True)); self.assertEqual(len(self.dispatched), 1)
        self.dispatched.append(copy.deepcopy(self.dispatched[0]))
        with self.assertRaisesRegex(ValueError, 'remains unconfirmed'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.assertEqual(sum(c[1] == 'send-command' for c in self.cloud), 1)

    def test_successful_cloud_install_records_source_bound_intent_and_reuses_original_receipt(self):
        report = self.qualified()
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.install_cloud(self.packet, self.packet_path)
        saved = json.loads(output.getvalue()); self.assertEqual(saved['instance_id'], self.worker); self.assertEqual(saved, json.loads((self.directory / 'install-command.json').read_bytes()))
        intent = json.loads((self.directory / 'install-intent.json').read_bytes()); self.assertEqual(intent['cloud_qualification_sha256'], bootstrap.sha(json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode())); self.assertEqual(intent['image'], report['image'])
        command = next(c for c in self.cloud if c[1] == 'send-command'); payload = json.loads(command[2][command[2].index('--parameters') + 1]); self.assertIn('sha256sum --check', '\n'.join(payload['commands'])); self.assertIn('qualified-host', payload['commands'][-1]); self.assertNotIn('owner@example.test', json.dumps(payload))
        with contextlib.redirect_stdout(io.StringIO()) as repeated: bootstrap.install_cloud(self.packet, self.packet_path)
        self.assertEqual(json.loads(repeated.getvalue()), saved); self.assertEqual(len(self.dispatched), 1)

    def test_cloud_install_reuses_only_the_initial_installer_fix_and_requires_original_ssm_ack(self):
        report = self.qualified(); self.invocations['synthetic-qualification']['Status'] = 'InProgress'
        with self.assertRaisesRegex(ValueError, 'has not succeeded'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.invocations['synthetic-qualification']['Status'] = 'Success'; self.invocations['synthetic-qualification']['StandardOutputContent'] = '{}'
        with self.assertRaisesRegex(ValueError, 'acknowledgement differs'): bootstrap.install_cloud(self.packet, self.packet_path)
        report['bundle_sha256'] = 'c' * 64; self.invocations['synthetic-qualification']['StandardOutputContent'] = json.dumps(report); self.qualification['report'] = report
        self.qualification['source_files']['platform_supervisor/worker.py'] = 'other'; (self.directory / 'cloud-qualified.json').write_text(json.dumps(self.qualification))
        with self.assertRaisesRegex(ValueError, 'Only an initial installer repair'): bootstrap.install_cloud(self.packet, self.packet_path)
        self.qualification['source_files'] = dict(self.packet['files'], **{'install-platform.sh': 'previous-installer-hash'}); (self.directory / 'cloud-qualified.json').write_text(json.dumps(self.qualification))
        with contextlib.redirect_stdout(io.StringIO()): bootstrap.install_cloud(self.packet, self.packet_path)
        self.assertEqual(len(self.dispatched), 1)

    def test_local_install_transports_verified_archives_and_reconciles_uncertain_dispatch(self):
        self.local_image(); self.dispatch_error = True
        with self.assertRaises(subprocess.CalledProcessError): bootstrap.install(self.packet, self.packet_path)
        self.assertEqual(len(self.dispatched), 1); intent = json.loads((self.directory / 'install-intent.json').read_bytes()); self.assertTrue(intent['image'].startswith('sha256:')); self.assertEqual(intent['image_archive_sha256'], bootstrap.sha((self.directory / 'platform-image.tar.gz').read_bytes()))
        uploads = [c for c in self.cloud if c[1] == 'cp']; self.assertEqual(len(uploads), 2); self.assertTrue(all('--sse' in c[2] and 'AES256' in c[2] for c in uploads))
        self.dispatch_error = False
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.install(self.packet, self.packet_path)
        self.assertTrue(json.loads(output.getvalue())['reconciled']); self.assertEqual(len(self.dispatched), 1)
        self.dispatched.clear()
        with self.assertRaisesRegex(ValueError, 'remains uncertain'): bootstrap.install(self.packet, self.packet_path)
        self.assertEqual(sum(c[1] == 'send-command' for c in self.cloud), 1)

    def test_local_install_never_accepts_unqualified_image_changed_archive_or_pending_metadata(self):
        folder = self.local_image(False); self.metadata['State'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'Verify applied IMDSv2'): bootstrap.install(self.packet, self.packet_path)
        self.metadata['State'] = 'applied'
        with self.assertRaisesRegex(ValueError, 'Passed bounded live coding control'): bootstrap.install(self.packet, self.packet_path)
        image = json.loads((folder / 'image.json').read_bytes()); (folder / 'qualification/report.json').write_text(json.dumps(dict(passed=True, live=True, image=image['image'])))
        changed = dict(image, recipe_sha256='0' * 64); (folder / 'image.json').write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'recipe changed'): bootstrap.install(self.packet, self.packet_path)
        (folder / 'image.json').write_text(json.dumps(image)); (self.directory / 'runtime.zip').write_bytes(b'Changed runtime archive')
        with self.assertRaisesRegex(ValueError, 'runtime archive changed'): bootstrap.install(self.packet, self.packet_path)
        self.assertFalse(self.dispatched)

    def test_local_install_creates_service_secret_via_stdin_after_all_repository_permissions_pass(self):
        self.local_image(); self.secret = None; self.github_token = '{"github_token":"synthetic-private-service-token"}'
        github = MagicMock(); github.request.return_value = {'permissions': {'push': True}}; github_class = MagicMock(return_value=github); github_module = types.ModuleType('platform_supervisor.github'); github_module.GitHub = github_class
        original_command = self.command
        def command(args, **options):
            if args[:3] == ['aws', 'secretsmanager', 'create-secret']:
                self.assertEqual(args[args.index('--secret-string') + 1], 'file:///dev/stdin'); self.assertNotIn('synthetic-private-service-token', ' '.join(args)); self.assertEqual(json.loads(options['input']), {'github_token': 'synthetic-private-service-token'})
                return subprocess.CompletedProcess(args, 0, b'{"ARN":"arn:synthetic:private-secret"}')
            return original_command(args, **options)
        with patch.dict(sys.modules, {'platform_supervisor.github': github_module}), patch.object(bootstrap.subprocess, 'run', side_effect=command), contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.install(self.packet, self.packet_path)
        github_class.assert_called_once_with('synthetic-private-service-token'); self.assertEqual([call.args for call in github.request.call_args_list], [('GET', '/repos/' + repo) for repo in self.policy['repositories']]); self.assertTrue(json.loads(output.getvalue())['submitted']); self.assertFalse(json.loads(output.getvalue())['production_verified'])
        self.assertNotIn('synthetic-private-service-token', ''.join(p.read_text() for p in self.directory.glob('*.json')))

    def test_missing_or_read_only_github_credential_cannot_create_a_service_secret(self):
        self.local_image(); self.secret = None
        github = MagicMock(); github.request.return_value = {'permissions': {'push': False}}; github_module = types.ModuleType('platform_supervisor.github'); github_module.GitHub = MagicMock(return_value=github)
        for token, message in [('{}', 'token is unavailable'), ('synthetic-raw-token', 'lacks push permission')]:
            self.github_token = token
            with patch.dict(sys.modules, {'platform_supervisor.github': github_module}), self.subTest(token=token), self.assertRaisesRegex(ValueError, message): bootstrap.install(self.packet, self.packet_path)
        self.assertFalse(self.dispatched); self.run.assert_called_once()  # preparation synth only

    def test_local_install_saves_then_compresses_a_missing_image_archive_with_stable_gzip_metadata(self):
        self.local_image(); archive = self.directory / 'platform-image.tar.gz'; import gzip
        original_tar = gzip.decompress(archive.read_bytes()); archive.unlink(); original_command = self.command
        def command(args, **options):
            if args[:2] == ['docker', 'save']:
                Path(args[args.index('--output') + 1]).write_bytes(original_tar); return subprocess.CompletedProcess(args, 0)
            return original_command(args, **options)
        with patch.object(bootstrap.subprocess, 'run', side_effect=command), contextlib.redirect_stdout(io.StringIO()): bootstrap.install(self.packet, self.packet_path)
        self.assertEqual(gzip.decompress(archive.read_bytes()), original_tar); self.assertEqual(archive.read_bytes()[4:8], b'\0' * 4); self.assertFalse((self.directory / 'platform-image.tar').exists())

    def test_cli_requires_private_inputs_and_dispatches_only_its_fixed_actions(self):
        self.prepare()
        for arguments in [['prepare'], ['install']]:
            with patch.object(sys, 'argv', ['platform-supervisor.py', *arguments]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error: bootstrap.main()
            self.assertEqual(error.exception.code, 2)
        for action in ['prepare', 'migrate', 'access', 'protect', 'harden', 'install', 'install-cloud', 'activate-self-runtime']:
            name = action.replace('-', '_'); arguments = ['prepare', '--owners-file', str(self.owners), '--output', str(self.directory)] if action == 'prepare' else [action, '--packet', str(self.packet_path)]
            with patch.object(sys, 'argv', ['platform-supervisor.py', *arguments]), patch.object(bootstrap, name) as operation: bootstrap.main()
            expected = (self.owners, self.directory) if action == 'prepare' else (self.packet, self.packet_path) if action in ['install', 'install-cloud', 'activate-self-runtime'] else (self.packet,); operation.assert_called_once_with(*expected)
        with patch.object(sys, 'argv', ['platform-supervisor.py', '--help']), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error: runpy.run_path(str(ROOT / 'bin/platform-supervisor.py'), run_name='__main__')
        self.assertEqual(error.exception.code, 0)

    def test_self_activation_requires_fixed_host_exact_clean_main_and_passing_protected_checks(self):
        self.prepare()
        for field, value, message in [('worker_id', 'i-00000000000000000', 'Fixed supervisor'), ('backend_revision', 'invalid', 'exact committed')]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message): bootstrap.activate_self_runtime(dict(self.packet, **{field: value}), self.packet_path)
        self.dirty = True
        with self.assertRaisesRegex(ValueError, 'clean committed'): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.dirty = False; self.main_revision = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'Exact protected backend main checks'): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.main_revision = 'a' * 40; self.check_passed = False
        with self.assertRaisesRegex(ValueError, 'Exact protected backend main checks'): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.assertFalse(self.dispatched); self.assertFalse(self.sql)

    def test_self_activation_reconciles_original_readback_and_rejects_pending_failed_or_changed_proofs(self):
        self.prepare(); comment = 'supervisor-baseline-' + self.packet['bundle_sha256'][:32]; command = dict(CommandId='synthetic-baseline', Comment=comment, InstanceIds=[self.worker]); self.dispatched = [command]
        marker = self.directory / 'self-runtime-verification-command.json'
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.assertTrue(json.loads(output.getvalue())['pending']); self.assertEqual(json.loads(marker.read_bytes()), {'command_id': 'synthetic-baseline'}); self.assertFalse(any(c[1] == 'send-command' for c in self.cloud)); self.assertFalse(self.sql)
        for status in ['Pending', 'InProgress', 'Delayed']:
            self.invocations['synthetic-baseline'] = {'Status': status}
            with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.activate_self_runtime(self.packet, self.packet_path)
            self.assertTrue(json.loads(output.getvalue())['pending']); self.assertFalse(self.sql)
        for status, response in [('Failed', 1), ('Success', 1)]:
            self.invocations['synthetic-baseline'] = {'Status': status, 'ResponseCode': response}
            with self.subTest(status=status, response=response), self.assertRaisesRegex(ValueError, 'readback did not pass'): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        proof = dict(passed=True, installed_files_verified=True, bundle_sha256=self.packet['bundle_sha256'], revision=self.packet['backend_revision'])
        self.invocations['synthetic-baseline'] = dict(Status='Success', ResponseCode=0, StandardOutputContent=json.dumps(dict(proof, revision='changed')))
        with self.assertRaisesRegex(ValueError, 'source receipt differs'): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.invocations['synthetic-baseline']['StandardOutputContent'] = 'Original diagnostics\n' + json.dumps(proof)
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.assertTrue(json.loads(output.getvalue())['activated']); saved = json.loads((self.directory / 'self-runtime-activation.json').read_bytes()); self.assertEqual(saved['manifest']['source_revision'], self.packet['backend_revision']); self.assertEqual(saved['manifest']['bundle_files'], self.packet['files']); self.assertEqual(saved['manifest']['files'], {'policy.json': self.packet['files']['platform_supervisor/policy.json'], 'worker.py': self.packet['files']['platform_supervisor/worker.py']}); self.assertEqual(saved['verification'], dict(proof, command_id='synthetic-baseline')); self.assertEqual(len(self.sql), 1)

    def test_ambiguous_self_readback_is_not_adopted_and_a_lost_dispatch_ack_is_not_replayed(self):
        self.prepare(); comment = 'supervisor-baseline-' + self.packet['bundle_sha256'][:32]; entry = dict(CommandId='ambiguous', Comment=comment, InstanceIds=[self.worker]); self.dispatched = [entry, copy.deepcopy(entry)]
        with self.assertRaisesRegex(ValueError, 'Ambiguous original baseline'): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.dispatched.clear(); self.dispatch_error = True
        with self.assertRaises(subprocess.CalledProcessError): bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.assertEqual(len(self.dispatched), 1); self.assertFalse((self.directory / 'self-runtime-verification-command.json').exists())
        with contextlib.redirect_stdout(io.StringIO()) as output: bootstrap.activate_self_runtime(self.packet, self.packet_path)
        self.assertTrue(json.loads(output.getvalue())['pending']); self.assertEqual(sum(c[1] == 'send-command' for c in self.cloud), 1)


class CloudAndAdminAdapters(unittest.TestCase):
    def test_fixed_aws_profile_region_output_and_empty_response(self):
        with patch.object(bootstrap.subprocess, 'check_output', side_effect=[b'{"Account":"395567831870"}', b' ']) as command:
            self.assertEqual(bootstrap.aws('sts', 'get-caller-identity'), {'Account': '395567831870'}); self.assertIsNone(bootstrap.aws('synthetic', 'empty', timeout=3))
            self.assertEqual(command.call_args.args[0], ['aws', 'synthetic', 'empty', '--profile', 'jumpserve', '--region', 'us-east-1', '--output', 'json']); self.assertEqual(command.call_args.kwargs['timeout'], 3)

    def test_admin_adapter_requires_the_fixed_supabase_project_before_returning_a_client(self):
        loader = MagicMock(); spec = types.SimpleNamespace(loader=loader); fake = types.ModuleType('synthetic_admin'); fake.PROJECT_REF = 'regphejnlvfpyokpniny'
        with patch.object(bootstrap.importlib.util, 'spec_from_file_location', return_value=spec), patch.object(bootstrap.importlib.util, 'module_from_spec', return_value=fake):
            self.assertIs(bootstrap.admin(), fake); fake.PROJECT_REF = 'different-project'
            with self.assertRaisesRegex(ValueError, 'Supabase target differs'): bootstrap.admin()


class SavedImageIdentity(unittest.TestCase):
    def archive(self, root, platform=None, index=True, choices=1, bad_digest=False):
        blobs = {}
        def blob(value):
            raw = json.dumps(value).encode(); identity = 'sha256:' + hashlib.sha256(raw).hexdigest(); blobs['blobs/sha256/' + identity.split(':')[1]] = raw; return identity
        config = blob(platform or dict(architecture='amd64', os='linux')); manifest = blob({'config': {'digest': config}}); qualified = blob({'manifests': [dict(platform=dict(architecture='amd64', os='linux'), digest=manifest)] * choices}) if index else manifest
        if bad_digest: blobs['blobs/sha256/' + qualified.split(':')[1]] = b'Changed original blob'
        path = root / 'image.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, raw in blobs.items(): item = tarfile.TarInfo(name); item.size = len(raw); archive.addfile(item, io.BytesIO(raw))
        return path, qualified, config

    def test_oci_and_classic_manifest_share_the_same_verified_linux_amd64_config(self):
        with tempfile.TemporaryDirectory() as folder:
            for index in [True, False]:
                path, qualified, expected = self.archive(Path(folder), index=index); self.assertEqual(bootstrap.classic_image(path, qualified), expected)

    def test_changed_blobs_ambiguous_platform_and_malformed_digests_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for options, message in [(dict(bad_digest=True), 'blob differs'), (dict(choices=0), 'Exactly one'), (dict(choices=2), 'Exactly one'), (dict(platform=dict(architecture='arm64', os='linux')), 'platform differs')]:
                path, qualified, _ = self.archive(root, **options)
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, message): bootstrap.classic_image(path, qualified)
            with self.assertRaisesRegex(ValueError, 'Malformed'): bootstrap.classic_image(path, 'sha256:invalid')


if __name__ == '__main__': unittest.main()
