"""Private-PDF release controls with synthetic cloud and database boundaries.

The blank PDF, ZIP evidence, retained bytes and hashes are real local artifacts.
No upload, database mutation, model request or production deployment is executed.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
import zipfile
from pypdf import PdfReader

from builder_continuation_release_test import canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('private_paper_release_unit', ROOT / 'bin/private-paper-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


class Response(io.BytesIO):
    status = 200


class PrivatePaperRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='private-paper-release-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'jumpserve-infra'; self.front = self.root.parent / 'jumpserve-front-end'; self.out = self.root / '.test-artifacts/private-paper-release/current'; self.out.mkdir(parents=True)
        self.enterContext(patch.object(release, 'ROOT', self.root)); self.prior = MagicMock(); self.enterContext(patch.object(release, 'prior', self.prior))
        paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths))
        self.prior.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"; self.prior.admin.query.side_effect = self.query; self.prior.aws.side_effect = self.aws; self.prior.guard.OPEN.open.side_effect = self.open
        self.prior.security.return_value = {'browser_writes_denied': True}; self.prior.pointers.side_effect = lambda: copy.deepcopy(self.pointers); self.prior.guard.target.return_value = {'synthetic_target': True}; self.prior.guard.inspect.return_value = {'retained_original_state': True}
        self.prior.queue.STACK = 'SyntheticResearchStack'; self.prior.queue.BASE = 'https://synthetic.invalid/research'; self.prior.queue.state.return_value = {'parameters': {'original': 'unchanged'}}; self.prior.queue.source.return_value = {'source_revision': 'a' * 40}; self.prior.queue.archives.return_value = ([{'original_package_verified': True}], 'original-queue-target')
        self.prior.functions.return_value = [dict(handler='api.handler', function='synthetic-api')]
        self.pointers = [dict(module_id='research-autonomy', active_version_id=release.PROMPT), dict(module_id='other-module', active_version_id='retained')]
        self.bucket = [dict(id='research-paper-uploads', public=False, file_size_limit=10000000, allowed_mime_types=['application/pdf'])]; self.functions = [dict(proname=name, anon_execute=False, browser_execute=False) for name in ['research_create_study', 'research_paper_upload']]
        self.schema = None; self.running = 0; self.sql = []; self.objects = {}; self.signed = {}; self.storage_failure = None; self.upload_status = 200; self.anonymous_status = 403; self.archive_status = 200; self.corrupt_archive = False; self.front_commit = 'cc03ebfa33042fd4a4856a1faf8f5c1fcd24f6e3'; self.log = b'Synthetic private build output\n'; self.clean = True
        self.capabilities = dict(paper_uploads=dict(version='research-paper-upload-v1', maximum_bytes=10000000, media_type='application/pdf'), autonomy=dict(enabled=True, defaults=dict(maximum_spend_usd=100, elapsed_days=7, attempts_per_claim=None, parallel_claims_per_paper=2, global_parallel_claims=4)))
        self.rules = [dict(ResourceType='AWS::Events::Rule', LogicalResourceId='ResearchWorkflowAutonomyPollFixture', PhysicalResourceId='synthetic-poll'), dict(ResourceType='AWS::Lambda::Function', LogicalResourceId='OtherResource', PhysicalResourceId='ignored')]
        self.enterContext(patch.object(release.subprocess, 'check_output', side_effect=self.command)); self.run = self.enterContext(patch.object(release.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)))
        self.write('cdk.json', canonical({'context': {'supabaseAnonKey': 'synthetic-public-key'}})); self.write('database/' + release.MIGRATION, b'-- Synthetic private PDF migration\n'); self.write('research-workflow-runtime.json', canonical({'version': 'synthetic-current-runtime'})); self.write('bin/private-paper-release.py', (ROOT / 'bin/private-paper-release.py').read_bytes()); self.write('test/private-paper-browser-recorder.mjs', b'// Synthetic recorder source\n')
        self.control = release.control(self.out); self.pdf = (self.out / self.control['filename']).read_bytes()
        expected = '41ca0ee1d6ec3a96190266e38063a2c20b7a9cea652eb73f395d461f62244077'; self.assertEqual(digest(self.pdf), expected, 'Pinned pypdf must generate the actual fixed blank control')
        self.study = dict(id=identity('blank-control'), title='JumpServe PDF upload release control R2', paper_url=None, paper_upload={'sha256': expected})
        initial = 'Original frozen qualification prompt'; self.data = dict(research_autonomy_workflows=[dict(initial_prompt=initial, initial_sha256=digest(initial.encode()), max_spend_cents=10000, max_attempts=None, status='completed-with-blockers')], research_autonomy_tasks=[dict(status='blocked')], research_autonomy_turns=[], research_sources=[], research_artifacts=[], research_claims=[], research_audit_events=[dict(action='synthetic-original')])
        packet = dict(tool_version='6.19.0', original_sha256=expected, pages=[dict(page=1, status='missing-text-layer', text='')])
        for kind, raw in [('paper-original-upload', self.pdf), ('derived-pdf-text', canonical(packet))]:
            sha = digest(raw); row = dict(id=identity(kind), storage_path=self.study['id'] + '/' + sha, sha256=sha, byte_count=len(raw), provenance={'kind': kind}); self.data['research_artifacts'].append(row); self.objects['https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/' + row['storage_path']] = raw
        self.upload = [dict(id=self.study['id'], status='started', reason=None, original_artifact_id=identity('paper-original-upload'))]

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def command(self, args, **options):
        if args == ['git', 'status', '--porcelain']: return '' if self.clean else ' M uncommitted.py\n'
        if args == ['git', 'rev-parse', 'HEAD']: return 'a' * 40 + '\n'
        raise AssertionError(args)
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.startswith('select id,public,file_size_limit'): return copy.deepcopy(self.bucket)
        if sql.startswith('select proname,has_function_privilege'): return copy.deepcopy(self.functions)
        if sql.startswith('select to_regclass('): return [{'present': self.schema}]
        if sql.startswith('select count(*) count from research_autonomy_'): return [{'count': self.running}]
        if sql.startswith('-- Synthetic private PDF migration'): self.assertFalse(options['read_only']); self.schema = 'research_paper_uploads'; return []
        if sql.startswith('select id,title,paper_url,paper_upload'): return [copy.deepcopy(self.study)]
        if sql.startswith('select id,status,reason,original_artifact_id'): return copy.deepcopy(self.upload)
        match = re.search(r' from (research_[a-z_]+) where study_id=', sql)
        if match: return copy.deepcopy(self.data[match[1]])
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        if (service, operation) == ('secretsmanager', 'get-secret-value'): return {'SecretString': 'synthetic-server-key'}
        if (service, operation) == ('configure', 'export-credentials'): return dict(AccessKeyId='synthetic-access', SecretAccessKey='synthetic-secret', SessionToken='synthetic-session')
        if (service, operation) == ('lambda', 'get-function-configuration'): return {'Environment': {'Variables': {'RESEARCH_AUTONOMY_ENABLED': 'false', 'ORIGINAL_SETTING': 'preserved'}}}
        if (service, operation) == ('lambda', 'update-function-configuration'): return {'LastUpdateStatus': 'InProgress'}
        if (service, operation) == ('cloudformation', 'list-stack-resources'): return {'StackResourceSummaries': copy.deepcopy(self.rules)}
        if (service, operation) == ('amplify', 'get-job'): return {'job': dict(summary=dict(jobId='118', status='SUCCEED', commitId=self.front_commit), steps=[dict(stepName='PROVISION', status='SUCCEED'), dict(stepName='BUILD', status='SUCCEED', logUrl='https://synthetic.invalid/build-log')])}
        raise AssertionError((service, operation, args))
    def error(self, url, status): raise urllib.error.HTTPError(url, status, 'Synthetic status', {}, Response(b'{"error":"retained synthetic rejection"}'))
    def open(self, request, **options):
        url = request if isinstance(request, str) else request.full_url
        if url == self.prior.queue.BASE + '/capabilities': return Response(canonical(self.capabilities))
        if url == 'https://synthetic.invalid/build-log': return Response(self.log)
        if url.startswith(self.prior.queue.BASE): return self.error(url, self.anonymous_status)
        method = request.get_method()
        if '/object/upload/sign/' in url:
            name = url.split('?')[0].rsplit('/', 1)[-1]
            if method == 'POST':
                if self.storage_failure == 'sign-status': return self.error(url, 500)
                relative = url.split('/storage/v1')[1] + '?token=synthetic-local-only'; self.signed[relative] = url.replace('/object/upload/sign/', '/object/')
                return Response(canonical({'url': '/wrong-scope' if self.storage_failure == 'sign-path' else relative}))
            self.assertEqual(method, 'PUT'); self.assertEqual(request.get_header('Apikey'), 'synthetic-public-key')
            if name == 'wrong-type.pdf': return self.error(url, 200 if self.storage_failure == 'mime' else 415)
            if name == 'oversize.pdf': self.assertEqual(len(request.data), 10000001); return self.error(url, 200 if self.storage_failure == 'oversize' else 413)
            target = self.signed[url.split('/storage/v1')[1]]
            if target in self.objects: return self.error(url, 200 if self.storage_failure == 'overwrite' else 409)
            if self.storage_failure == 'put': return self.error(url, 500)
            self.objects[target] = request.data; return Response(b'{}')
        if method == 'POST':
            self.assertEqual(request.get_header('X-upsert'), 'false'); self.objects[url] = request.data
            if self.archive_status != 200: return self.error(url, self.archive_status)
            return Response(b'{}')
        if not request.has_header('Authorization'):
            if self.anonymous_status != 200: return self.error(url, self.anonymous_status)
            return Response(b'Unexpected anonymous bytes')
        raw = self.objects[url]
        if self.storage_failure == 'bytes' or self.corrupt_archive: raw += b'changed original'
        return Response(raw)
    def cli(self, mode):
        with patch.object(sys, 'argv', ['private-paper-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as stdout: release.main()
        result = json.loads(stdout.getvalue()); directory = Path(result['directory']); receipt = json.loads((directory / 'receipt.json').read_bytes()); self.assertEqual(receipt['status'], 'complete'); self.assertEqual(receipt['new_application_model_calls'], 0); self.assertEqual(receipt['new_experiment_instances'], 0); self.assertNotIn('synthetic-secret', canonical(receipt).decode()); self.assertNotIn('synthetic-server-key', canonical(receipt).decode()); return directory, receipt
    def archive_fixture(self):
        original = b'Synthetic original record: zero=0, missing=null\n'; name = 'jumpserve-front-end/.test-artifacts/retained-original.json'; path = self.front / '.test-artifacts/retained-original.json'; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(original)
        profile = canonical({'version': 'synthetic-original-development-runtime'}); self.write('.test-artifacts/private-paper-release/original-local-profile/runtime-development-v28.json', profile)
        inventory = {'evidence': [dict(path=name, sha256=digest(original)), dict(path='jumpserve-infra/research-workflow-runtime.json', sha256=digest(profile))]}; self.write('docs/private-paper-uploads-validation-v1.json', canonical(inventory))
        for directory, names in [('.test-artifacts/private-paper-production-browser/retained', ['report.json', 'screen.png']), ('.test-artifacts/research-ideas/database/20261020T000000Z', ['raw-original.bin', 'fixture-report.json', 'database-fixture-snapshot.json', 'excluded.txt'])]:
            for item in names: self.write(directory + '/' + item, ('Synthetic retained ' + item + '\n').encode())
        for directory in ['private-paper-production-browser/retained', 'research-autonomy/2026-10-20T00-00-00', 'autonomy-release-production/2026-10-20T00-00-00']:
            base = self.front / '.test-artifacts' / directory; base.mkdir(parents=True, exist_ok=True)
            for name in ['report.json', 'screen.png', 'excluded.txt']: (base / name).write_bytes(('Synthetic ' + name).encode())

    def test_blank_control_is_a_real_single_page_pdf_without_a_text_layer_or_scientific_claim(self):
        document = PdfReader(io.BytesIO(self.pdf)); self.assertEqual(len(document.pages), 1); self.assertEqual(document.pages[0].extract_text(), ''); self.assertEqual(self.control['sha256'], digest(self.pdf)); self.assertEqual(self.control['text_claims'], 0); self.assertEqual(self.control['expected_state'], 'missing-text; no model call')
        self.assertEqual(json.loads((self.out / 'control.json').read_bytes()), self.control); self.prior.admin.query.assert_not_called()

    def test_security_requires_exact_private_pdf_bucket_and_both_service_only_rpcs(self):
        result = release.security(); self.assertTrue(result['browser_writes_denied']); self.assertEqual(result['upload_bucket'], self.bucket)
        self.bucket[0]['public'] = True
        with self.assertRaisesRegex(RuntimeError, 'bucket differs'): release.security()
        self.bucket[0]['public'] = False; self.functions[0]['browser_execute'] = True
        with self.assertRaisesRegex(RuntimeError, 'service-only'): release.security()

    def test_signed_storage_permissions_are_scoped_single_use_and_reject_wrong_mime_oversize_and_anonymous_reads(self):
        result = release.storage(self.out); self.assertEqual(result['original_sha256'], result['retrieved_sha256']); self.assertEqual(result['retrieved_bytes'], len(self.pdf)); self.assertEqual(result['anonymous_read_status'], 403); self.assertEqual(result['overwrite_status'], 409); self.assertEqual(result['wrong_mime_status'], 415); self.assertEqual(result['oversize_status'], 413); self.assertFalse(result['credentials_retained'])

    def test_signed_storage_failures_never_return_a_success_receipt(self):
        for failure, reason in [('sign-status', 'Signed permission failed'), ('sign-path', 'Scoped signed path differs'), ('put', 'Signed PDF PUT failed'), ('bytes', 'Remote original bytes differ'), ('overwrite', 'permits overwrite'), ('mime', 'Wrong MIME was accepted'), ('oversize', 'Oversize was accepted'), ('public', 'anonymously readable')]:
            with self.subTest(failure=failure):
                self.storage_failure = failure; self.anonymous_status = 200 if failure == 'public' else 403; self.objects = {key:value for key,value in self.objects.items() if '/research-workflow-raw/' in key}
                with self.assertRaisesRegex(RuntimeError, reason): release.storage(self.out)

    def test_browser_blank_control_requires_frozen_prompt_no_model_turns_original_pdf_and_actual_parser_packet(self):
        result = release.control_read(self.out); self.assertEqual(result['actual_pdf_parser']['missing_text_pages'], [1]); self.assertEqual(len(result['retrieved_artifacts']), 2); self.assertEqual(result['research_claims'], []); self.assertEqual(result['research_autonomy_turns'], []); self.assertIn('no scientific finding', result['data_origin'])
        for row in result['retrieved_artifacts']: self.assertEqual(digest((self.out / row['path']).read_bytes()), row['sha256'])
        original = copy.deepcopy(self.data)
        for failure, reason in [('turn', 'no claims or model turns'), ('prompt', 'prompt integrity'), ('running', 'explicit blank-PDF blocker'), ('bytes', 'artifact differs'), ('parser', 'actual pypdf'), ('original', 'Original PDF artifact missing'), ('upload', 'not finalized')]:
            with self.subTest(failure=failure):
                self.data = copy.deepcopy(original); self.storage_failure = None; self.upload[0]['status'] = 'started'
                if failure == 'turn': self.data['research_autonomy_turns'] = [{'id': 'unexpected'}]
                if failure == 'prompt': self.data['research_autonomy_workflows'][0]['initial_sha256'] = '0' * 64
                if failure == 'running': self.data['research_autonomy_tasks'][0]['status'] = 'running'
                if failure == 'bytes': self.storage_failure = 'bytes'
                if failure == 'parser': self.data['research_artifacts'] = self.data['research_artifacts'][:1]
                if failure == 'original': self.data['research_artifacts'] = self.data['research_artifacts'][1:]
                if failure == 'upload': self.upload[0]['status'] = 'reserved'
                with self.assertRaisesRegex(RuntimeError, reason): release.control_read(self.out)

    def test_evidence_archive_roundtrips_original_profile_and_every_member_hash_without_collecting_its_current_output(self):
        self.archive_fixture(); result = release.archive(self.out); self.assertTrue(result['all_member_hashes_verified']); self.assertEqual(result['anonymous_status'], 403); self.assertIsNone(result['measured_storage_charges_usd'])
        raw = (self.out / 'original-evidence.zip').read_bytes(); self.assertEqual(digest(raw), result['sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as retained:
            manifest = json.loads(retained.read('manifest.json')); self.assertEqual(len(manifest), result['files']); self.assertIn('development-input/research-workflow-runtime.json', retained.namelist()); self.assertFalse(any('/current/' in name for name in retained.namelist())); self.assertNotIn('jumpserve-infra/.test-artifacts/research-ideas/database/20261020T000000Z/excluded.txt', retained.namelist())
            for item in manifest: content = retained.read(item['path']); self.assertEqual(item['bytes'], len(content)); self.assertEqual(item['sha256'], digest(content))
        self.archive_status = 409; self.assertTrue(release.archive(self.out)['retrieved_hash_verified'])

    def test_archive_rejects_mutated_development_evidence_links_changed_downloads_and_anonymous_access(self):
        self.archive_fixture(); profile = self.root / '.test-artifacts/private-paper-release/original-local-profile/runtime-development-v28.json'; original = profile.read_bytes(); profile.write_bytes(original + b'changed')
        with self.assertRaisesRegex(RuntimeError, 'development profile bytes differ'): release.archive(self.out)
        profile.write_bytes(original); path = self.front / '.test-artifacts/retained-original.json'; original = path.read_bytes(); path.write_bytes(original + b'changed')
        with self.assertRaisesRegex(RuntimeError, 'Original local evidence changed'): release.archive(self.out)
        path.write_bytes(original); linked = self.root / '.test-artifacts/private-paper-production-browser/retained/link.bin'; linked.symlink_to(path)
        with self.assertRaisesRegex(RuntimeError, 'ordinary file'): release.archive(self.out)
        linked.unlink(); self.corrupt_archive = True
        with self.assertRaisesRegex(RuntimeError, 'Remote evidence archive hash differs'): release.archive(self.out)
        self.corrupt_archive = False; self.archive_status = 500
        with self.assertRaisesRegex(RuntimeError, 'upload failed HTTP 500'): release.archive(self.out)
        self.archive_status = 200; self.anonymous_status = 200
        with self.assertRaisesRegex(RuntimeError, 'anonymously accessible'): release.archive(self.out)

    def test_cli_inspects_migrates_verifies_and_retains_storage_control_and_archive_receipts_with_no_model_or_instance_calls(self):
        _, inspected = self.cli('inspect'); self.assertEqual(inspected['control']['text_claims'], 0)
        _, migrated = self.cli('migrate'); self.assertEqual(migrated['migration']['status'], 'complete'); self.assertEqual(migrated['migration']['sha256'], digest((self.root / 'database' / release.MIGRATION).read_bytes()))
        _, verified = self.cli('verify'); self.assertEqual(len(verified['anonymous_checks']), 2)
        _, stored = self.cli('storage'); self.assertFalse(stored['remote_storage']['credentials_retained'])
        _, parsed = self.cli('control-read'); self.assertEqual(parsed['browser_control']['actual_pdf_parser']['version'], '6.19.0')
        self.archive_fixture(); _, archived = self.cli('archive'); self.assertTrue(archived['original_evidence']['all_member_hashes_verified'])

    def test_cli_deployments_use_only_the_exact_stack_and_hold_admission_until_activation_preserving_every_other_api_setting(self):
        for mode in ['diff', 'deploy', 'activate', 'repair']:
            with self.subTest(mode=mode):
                self.run.reset_mock(); _, receipt = self.cli(mode); command = receipt['command']; self.assertEqual(command[:5], ['npm', 'run', 'cdk:benchmark', '--', 'diff' if mode == 'diff' else 'deploy']); self.assertIn('researchAutonomyAdmissionEnabled=' + ('true' if mode in ['activate', 'repair'] else 'false'), command)
                cdk = self.run.call_args_list[0]; self.assertEqual(cdk.kwargs['env']['AWS_SESSION_TOKEN'], 'synthetic-session'); self.assertNotIn('AWS_PROFILE', cdk.kwargs['env'])
                if mode in ['activate', 'repair']: self.assertEqual(receipt['autonomy_poll_restored'], 'synthetic-poll'); self.assertEqual(self.run.call_args_list[1].args[0][:3], ['aws', 'events', 'enable-rule'])
                if mode == 'repair':
                    changes = next(call for call in reversed(self.prior.aws.call_args_list) if call.args[:2] == ('lambda', 'update-function-configuration')); environment = json.loads(changes.args[-1])['Variables']; self.assertEqual(environment, {'RESEARCH_AUTONOMY_ENABLED': 'true', 'ORIGINAL_SETTING': 'preserved'})

    def test_cli_rejects_existing_schema_active_tasks_dirty_sources_failed_cdk_and_unexpected_runtime_activation(self):
        self.schema = 'already-present'
        with self.assertRaisesRegex(RuntimeError, 'schema already exists'): self.cli('migrate')
        self.schema = None; self.running = 1
        with self.assertRaisesRegex(RuntimeError, 'Drain running'): self.cli('migrate')
        self.clean = False
        with self.assertRaisesRegex(RuntimeError, 'Clean committed backend'): self.cli('deploy')
        self.clean = True; self.run.return_value.returncode = 1
        with self.assertRaisesRegex(RuntimeError, 'Scoped CDK command failed'): self.cli('deploy')
        self.run.return_value.returncode = 0
        with patch.object(self.prior.queue, 'state', side_effect=[{'parameters': {'original': True}}, {'parameters': {'original': False}}]), self.assertRaisesRegex(RuntimeError, 'stack parameters changed'): self.cli('deploy')
        self.rules = []
        with self.assertRaisesRegex(RuntimeError, 'rule inventory differs'): self.cli('activate')
        self.capabilities['paper_uploads']['maximum_bytes'] = 1
        with self.assertRaisesRegex(RuntimeError, 'PDF capability differs'): self.cli('verify')
        self.capabilities['paper_uploads']['maximum_bytes'] = 10000000; self.capabilities['autonomy']['enabled'] = False
        with self.assertRaisesRegex(RuntimeError, 'activation/defaults differ'): self.cli('verify')
        self.capabilities['autonomy']['enabled'] = True; self.anonymous_status = 404
        with self.assertRaisesRegex(RuntimeError, 'Private API anonymously accessible'): self.cli('verify')

    def test_cli_never_changes_prompt_pointers_and_frontend_logs_are_bounded_with_signed_urls_omitted(self):
        directory, receipt = self.cli('frontend-status'); self.assertEqual((directory / 'amplify-BUILD.log').read_bytes(), self.log); self.assertNotIn('logUrl', canonical(receipt).decode()); self.assertEqual(receipt['frontend']['steps'][1]['log_sha256'], digest(self.log))
        self.front_commit = 'changed-revision'
        with self.assertRaisesRegex(RuntimeError, 'Frontend source differs'): self.cli('frontend-status')
        self.front_commit = 'cc03ebfa33042fd4a4856a1faf8f5c1fcd24f6e3'; self.log = b'x' * 2000001
        with self.assertRaisesRegex(RuntimeError, 'log exceeds bound'): self.cli('frontend-status')
        before = copy.deepcopy(self.pointers); self.pointers[0]['active_version_id'] = 'unexpected'
        with self.assertRaisesRegex(RuntimeError, 'Unexpected active autonomy prompt'): self.cli('inspect')
        self.pointers = before
        with patch.object(self.prior, 'pointers', side_effect=[before, before + [{'module_id': 'unexpected', 'active_version_id': 'changed'}]]), self.assertRaisesRegex(RuntimeError, 'prompt pointers changed'): self.cli('inspect')
        receipts = [json.loads(path.read_bytes()) for path in self.out.parent.glob('*/receipt.json')]; self.assertTrue(any(row['status'] == 'failed' and row['reason'] and row['ended_at'] for row in receipts))

    def test_entrypoint_rejects_unknown_modes_before_any_cloud_or_database_access(self):
        path = ROOT / 'bin/private-paper-release.py'
        with patch.object(sys, 'argv', [str(path), 'unsupported-unit-mode']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            exec(compile(path.read_bytes(), str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
        self.assertEqual(stopped.exception.code, 2); self.prior.admin.query.assert_not_called(); self.run.assert_not_called()


if __name__ == '__main__': unittest.main()
