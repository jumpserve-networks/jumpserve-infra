"""Idea-guide release controls with synthetic cloud/SQL/HTTP boundaries.

Original tar/ZIP evidence and source hashes are verified locally. No production
prompt publication, model request, CDK command or credential lookup runs.
"""
import base64
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from builder_continuation_release_test import archive, canonical, digest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('idea_interview_release_unit', ROOT / 'bin/idea-interview-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


def evidence_bundle(files, changed_manifest=False):
    manifest = [dict(path=name, sha256='0' * 64 if changed_manifest else digest(raw), bytes=len(raw)) for name, raw in sorted(files.items())]
    content = dict(files, **{'manifest.json': canonical(manifest)}); buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as retained:
        for name, raw in content.items():
            item = tarfile.TarInfo(name); item.size = len(raw); retained.addfile(item, io.BytesIO(raw))
    return buffer.getvalue()


class IdeaInterviewRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='idea-interview-release-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'jumpserve-infra'; self.evaluation = self.root / '.test-artifacts/evaluation'; self.evaluation.mkdir(parents=True)
        self.enterContext(patch.object(release, 'ROOT', self.root)); self.enterContext(patch.object(release, 'EVALUATION', self.evaluation))
        self.previous = MagicMock(); self.admin = MagicMock(); self.enterContext(patch.object(release, 'previous', self.previous)); self.enterContext(patch.object(release, 'admin', self.admin))
        self.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"; self.admin.query.side_effect = self.query
        self.previous.target.return_value = {'synthetic_target': True}; self.previous.inspect.side_effect = lambda: dict(pointers=copy.deepcopy(self.pointers), scientific_counts={'measurements': 0}); self.previous.verify.return_value = {'browser_writes_denied': True}
        self.pointers = [dict(module_id='research-verification', active_version_id=release.PRIOR), dict(module_id='other-module', active_version_id='unchanged-other-prompt')]; self.current = release.PRIOR; self.queries = []; self.drafts = []; self.objects = {}; self.upload_status = 200; self.anonymous_status = 403; self.corrupt_download = False
        self.seed = dict(system_prompt='Synthetic immutable policy', research_context='Synthetic recorded review context'); self.write('database/seed-research-ideas-prompt-v11.json', canonical(self.seed)); self.write('agent/handler.py', b'# Original synthetic agent source\n')
        self.report = dict(prompt_version_id=release.CANDIDATE, publication_eligible=True, reviewer={'type': 'AI', 'passed': True, 'independent': False}, prompt_content_sha256=digest((self.seed['system_prompt'] + '\n\n' + self.seed['research_context']).encode()), runtime_hashes={'agent/handler.py': digest(b'# Original synthetic agent source\n')}, cases=[])
        for index in range(21):
            name = 'case-' + str(index); output = ('Original synthetic answer ' + name + '\n').encode(); rendered = canonical({'zero': 0, 'missing': None, 'case': name})
            self.evidence(name + '-output.txt', output); self.evidence(name + '-rendered.json', rendered); self.report['cases'].append(dict(name=name, passed=True, status='complete', output_sha256=digest(output), rendered_sha256=digest(rendered)))
        self.evidence('evaluation-report.json', canonical(self.report))
        for name, document in [('idea-interview', 'idea-interview-validation-v1.json'), ('idea-review-source-fidelity', 'idea-review-source-fidelity-validation-v1.json')]:
            raw = evidence_bundle({'original-answer.bin': b'Original zero=0, missing=null\n'}); path = 'docs/' + name + '-evidence-v1.tar.gz'; self.write(path, raw)
            self.write('docs/' + document, canonical(dict(evidence_bundle=dict(path=path, sha256=digest(raw)), actual_answer_evaluation={'report_sha256': digest(canonical(self.report))})))
        self.write('docs/idea-interview-release-protocol-v1.json', canonical({'version': 'synthetic-protocol'})); self.write('docs/idea-interview-release-evidence-v1.tar.gz', evidence_bundle({'original-release.bin': b'Synthetic retained release original\n'}))
        for name in release.MIGRATIONS: self.write('database/' + name, ('-- Synthetic fixed migration: ' + name + '\n').encode())
        self.write('cdk.json', canonical({'context': {'supabaseAnonKey': 'synthetic-public-key'}}))
        self.code = archive({'handler.py': (self.root / 'agent/handler.py').read_bytes()}); self.layer = archive({'python/dependency.py': b'# synthetic pinned dependency\n'})
        self.config = dict(FunctionArn='arn:aws:lambda:us-east-1:395567831870:function:synthetic-agent', FunctionName='synthetic-agent', Environment={'Variables': {'SUPABASE_URL': 'https://regphejnlvfpyokpniny.supabase.co'}}, CodeSha256=self.aws_hash(self.code), MemorySize=1024, Timeout=29, LastModified='retained-time')
        self.build_log = b'Synthetic build: commit ' + b'a' * 40 + b'\n'; self.chunk = b'// Recorded declarations; Planning conversation history; synthetic client\n'; self.front_status = 'SUCCEED'
        chunks = self.root.parent / 'jumpserve-front-end/.next/static/chunks'; chunks.mkdir(parents=True); (chunks / 'guide.js').write_bytes(self.chunk)
        self.capabilities = dict(ideas=dict(version='research-ideas-v1', paper_required=False, packet_bytes=24000), networking={'runners': [{'id': 'custom-package-v1', 'enabled': False}]})
        self.previous.OPEN.open.side_effect = self.open
        self.enterContext(patch.object(release.subprocess, 'check_output', side_effect=self.command))
        self.run = self.enterContext(patch.object(release.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)))

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def evidence(self, name, raw):
        path = self.evaluation / name; path.write_bytes(raw); return path
    def aws_hash(self, raw):
        return base64.b64encode(bytes.fromhex(digest(raw))).decode()
    def query(self, sql, **options):
        self.queries.append((sql, options))
        if sql.startswith('select module_id,active_version_id'): return copy.deepcopy(self.pointers)
        if sql.startswith('select v.id,v.version'): return [dict(id=self.current, version='retained-version', content_sha256=self.report['prompt_content_sha256'], published_at='retained-publication')]
        if sql.startswith('select id from agent_prompt_versions'): return copy.deepcopy(self.drafts)
        if sql.startswith('select id,version,content_sha256,published_at'):
            return [dict(id=release.CANDIDATE, version='research-ideas-v11', content_sha256=self.report['prompt_content_sha256'], published_at=None)]
        if sql.startswith('-- Synthetic fixed migration:'): self.assertFalse(options['read_only']); return []
        if sql.startswith('select publish_agent_prompt('):
            self.assertFalse(options['read_only']); self.assertIn(release.PRIOR, sql); self.assertIn(release.CANDIDATE, sql); self.current = release.CANDIDATE; self.pointers[0]['active_version_id'] = release.CANDIDATE; return [{'published': True}]
        raise AssertionError('Unexpected SQL: ' + sql)
    def command(self, args, **options):
        self.assertEqual(args[0], 'aws'); self.assertEqual(args[-6:], ['--profile', 'jumpserve', '--region', 'us-east-1', '--output', 'json']); self.assertEqual(options['timeout'], 60)
        service, operation = args[1:3]
        if (service, operation) == ('cloudformation', 'describe-stack-resource'): value = {'StackResourceDetail': {'PhysicalResourceId': 'synthetic-agent'}}
        elif (service, operation) == ('lambda', 'get-function'): value = {'Configuration': copy.deepcopy(self.config), 'Code': {'Location': 'https://synthetic.invalid/code'}}
        elif (service, operation) == ('lambda', 'get-function-configuration'): value = {'Layers': [{'Arn': 'synthetic-layer-arn'}]}
        elif (service, operation) == ('lambda', 'get-layer-version-by-arn'): value = {'Content': dict(Location='https://synthetic.invalid/layer', CodeSha256=self.aws_hash(self.layer))}
        elif (service, operation) == ('configure', 'export-credentials'): value = dict(AccessKeyId='synthetic-access', SecretAccessKey='synthetic-secret', SessionToken='synthetic-session')
        elif (service, operation) == ('secretsmanager', 'get-secret-value'): value = {'SecretString': 'synthetic-private-service-key'}
        elif (service, operation) == ('amplify', 'get-job'): value = {'job': dict(summary={'status': self.front_status}, steps=[{'stepName': 'PROVISION', 'status': 'SUCCEED'}, {'stepName': 'BUILD', 'status': 'SUCCEED', 'logUrl': 'https://synthetic.invalid/build-log'}])}
        else: raise AssertionError(args)
        return canonical(value)
    def open(self, request, **options):
        url = request if isinstance(request, str) else request.full_url
        if url == 'https://synthetic.invalid/code': return io.BytesIO(self.code)
        if url == 'https://synthetic.invalid/layer': return io.BytesIO(self.layer)
        if url == 'https://synthetic.invalid/build-log': return io.BytesIO(self.build_log)
        if '/_next/static/chunks/' in url: return io.BytesIO(self.chunk)
        if '/storage/v1/object/' in url:
            if request.get_method() == 'POST':
                self.assertEqual(request.get_header('X-upsert'), 'false'); self.objects[url] = request.data
                if self.upload_status != 200: raise urllib.error.HTTPError(url, self.upload_status, 'Synthetic upload status', {}, io.BytesIO())
                return io.BytesIO()
            if not request.has_header('Authorization'):
                if self.anonymous_status == 200: return io.BytesIO(b'x')
                raise urllib.error.HTTPError(url, self.anonymous_status, 'Synthetic anonymous denial', {}, io.BytesIO())
            return io.BytesIO(self.objects[url] + (b'changed' if self.corrupt_download else b''))
        if url.endswith('/research/capabilities'): return io.BytesIO(canonical(self.capabilities))
        if '/research/studies/' in url or '.lambda-url.' in url: raise urllib.error.HTTPError(url, self.anonymous_status, 'Synthetic denial', {}, io.BytesIO())
        raise AssertionError(url)
    def cli(self, mode):
        with patch.object(sys, 'argv', ['idea-interview-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as stdout:
            release.main()
        printed = json.loads(stdout.getvalue()); directory = Path(printed['directory']); receipt = json.loads((directory / 'receipt.json').read_bytes())
        self.assertEqual(receipt['status'], 'complete'); self.assertEqual(receipt['new_model_calls'], 0); self.assertIsNone(receipt['measured_charges_usd']); self.assertNotIn('synthetic-private-service-key', canonical(receipt).decode()); self.assertNotIn('synthetic-secret', canonical(receipt).decode()); return directory, receipt

    def test_evaluation_verifies_every_original_answer_runtime_seed_and_both_tar_member_manifests(self):
        before = {str(path): path.read_bytes() for path in self.evaluation.iterdir()}; self.assertEqual(release.evaluated(), self.report); self.assertEqual(before, {str(path): path.read_bytes() for path in self.evaluation.iterdir()})
        corruptions = [('evaluation-report.json', self.evaluation / 'evaluation-report.json', 'Reviewed evaluation changed'), ('output', self.evaluation / 'case-0-output.txt', 'Original answer changed'), ('runtime', self.root / 'agent/handler.py', 'Evaluated runtime changed'), ('bundle', self.root / 'docs/idea-interview-evidence-v1.tar.gz', 'Evidence bundle changed')]
        for name, path, reason in corruptions:
            with self.subTest(name=name):
                raw = path.read_bytes(); path.write_bytes(raw + (b'\n' if name == 'evaluation-report.json' else b'changed'))
                try:
                    with self.assertRaisesRegex(RuntimeError, reason): release.evaluated()
                finally: path.write_bytes(raw)
        self.seed['system_prompt'] += ' changed'; self.write('database/seed-research-ideas-prompt-v11.json', canonical(self.seed))
        with self.assertRaisesRegex(RuntimeError, 'Candidate seed content changed'): release.evaluated()

    def test_ineligible_development_review_and_changed_tar_members_never_become_qualified(self):
        self.report['cases'][0]['passed'] = False; raw = canonical(self.report); self.evidence('evaluation-report.json', raw)
        path = self.root / 'docs/idea-review-source-fidelity-validation-v1.json'; record = json.loads(path.read_bytes()); record['actual_answer_evaluation']['report_sha256'] = digest(raw); path.write_bytes(canonical(record))
        with self.assertRaisesRegex(RuntimeError, 'Exact candidate'): release.evaluated()
        self.report['cases'][0]['passed'] = True; raw = canonical(self.report); self.evidence('evaluation-report.json', raw); record['actual_answer_evaluation']['report_sha256'] = digest(raw); path.write_bytes(canonical(record))
        bad = evidence_bundle({'original-answer.bin': b'changed original'}, changed_manifest=True); bundle = self.root / 'docs/idea-interview-evidence-v1.tar.gz'; bundle.write_bytes(bad); record_path = self.root / 'docs/idea-interview-validation-v1.json'; value = json.loads(record_path.read_bytes()); value['evidence_bundle']['sha256'] = digest(bad); record_path.write_bytes(canonical(value))
        with self.assertRaisesRegex(RuntimeError, 'Archived original differs'): release.evaluated()

    def test_deployed_verification_checks_aws_target_zip_hash_runtime_bytes_and_exact_published_prompt(self):
        directory = self.root / 'out'; directory.mkdir(); result = release.deployed(directory); self.assertEqual(result['zip_sha256'], digest(self.code)); self.assertEqual((directory / 'deployed-agent.zip').read_bytes(), self.code); self.assertEqual(result['layers'], [])
        self.current = release.CANDIDATE; self.assertEqual(release.deployed(directory, require_candidate=True)['active'][0]['id'], release.CANDIDATE)
        self.current = release.PRIOR
        with self.assertRaisesRegex(RuntimeError, 'Published candidate differs'): release.deployed(directory, require_candidate=True)
        self.config['FunctionArn'] = 'arn:aws:lambda:us-east-1:000000000000:function:other'
        with self.assertRaisesRegex(RuntimeError, 'target differs'): release.deployed(directory)
        self.config['FunctionArn'] = 'arn:aws:lambda:us-east-1:395567831870:function:synthetic-agent'; self.code += b'changed'
        with self.assertRaisesRegex(RuntimeError, 'ZIP checksum differs'): release.deployed(directory)
        self.code = archive({'handler.py': b'changed source'}); self.config['CodeSha256'] = self.aws_hash(self.code)
        with self.assertRaisesRegex(RuntimeError, 'Deployed runtime differs'): release.deployed(directory)

    def test_private_evidence_upload_is_immutable_hash_verified_and_denies_anonymous_reads_even_on_existing_objects(self):
        result = release.archive_evidence(); self.assertEqual(len(result['objects']), 5); self.assertTrue(result['retrieved_original_hashes_verified']); self.assertIsNone(result['measured_charges_usd']); self.assertTrue(all(item['anonymous_status'] == 403 for item in result['objects']))
        self.upload_status = 409; self.assertEqual(release.archive_evidence()['total_bytes'], result['total_bytes'])
        self.upload_status = 500
        with self.assertRaisesRegex(RuntimeError, 'HTTP 500'): release.archive_evidence()
        self.upload_status = 200; self.corrupt_download = True
        with self.assertRaisesRegex(RuntimeError, 'Retrieved original artifact differs'): release.archive_evidence()
        self.corrupt_download = False; self.anonymous_status = 200
        with self.assertRaisesRegex(RuntimeError, 'anonymous denial differs'): release.archive_evidence()
        self.write('docs/oversized-evidence.json', b'x' * 16000001)
        with self.assertRaisesRegex(RuntimeError, 'storage budget exceeded'): release.archive_evidence(('docs/oversized-evidence.json',))

    def test_public_capabilities_keep_custom_packages_disabled_and_each_private_endpoint_requires_authentication(self):
        result = release.public_checks(); self.assertEqual(len(result['anonymous_denials']), 4); self.assertEqual([item['method'] for item in result['anonymous_denials']], ['GET', 'POST', 'POST', 'POST']); self.assertEqual(result['authenticated_requests'], 0); self.assertEqual(result['new_model_calls'], 0)
        self.capabilities['ideas']['packet_bytes'] += 1
        with self.assertRaisesRegex(RuntimeError, 'Public idea capability'): release.public_checks()
        self.capabilities['ideas']['packet_bytes'] -= 1; self.capabilities['networking']['runners'][0]['enabled'] = True
        with self.assertRaisesRegex(RuntimeError, 'must stay disabled'): release.public_checks()
        self.capabilities['networking']['runners'][0]['enabled'] = False; self.anonymous_status = 404
        with self.assertRaisesRegex(RuntimeError, 'not denied'): release.public_checks()

    def test_inspect_migrations_and_layer_restore_preserve_prompt_pointers_scientific_counts_and_original_dependencies(self):
        _, inspected = self.cli('inspect'); self.assertIn('candidates', inspected)
        _, migrated = self.cli('migrate'); self.assertEqual([item['name'] for item in migrated['migrations']], list(release.MIGRATIONS)); self.assertTrue(all(item['status'] == 'complete' for item in migrated['migrations'])); self.assertEqual(self.current, release.PRIOR)
        _, prepared = self.cli('prepare-layer'); self.assertTrue(prepared['dependency_layer']['original_bytes_verified']); self.assertEqual((self.root / 'agent/layer/python/dependency.py').read_bytes(), b'# synthetic pinned dependency\n')
        with self.assertRaisesRegex(RuntimeError, 'empty clean-release'): self.cli('prepare-layer')

    def test_scoped_cdk_commands_preserve_prior_code_for_rollback_and_do_not_retain_session_credentials(self):
        for mode in ['diff', 'deploy']:
            with self.subTest(mode=mode):
                directory, receipt = self.cli(mode); command, = self.run.call_args.args
                self.assertEqual(command[:4], ['npx', 'cdk', mode, 'JumpServeAgentStack']); self.assertIn('--exclusively', command); self.assertNotIn('AWS_PROFILE', self.run.call_args.kwargs['env']); self.assertEqual(self.run.call_args.kwargs['env']['AWS_SESSION_TOKEN'], 'synthetic-session')
                if mode == 'deploy': self.assertEqual((directory / 'previous-agent.zip').read_bytes(), self.code); self.assertEqual(receipt['rollback']['zip_sha256'], digest(self.code))
                else: self.assertIn('--no-change-set', command)
        self.run.return_value = types.SimpleNamespace(returncode=1)
        with self.assertRaisesRegex(RuntimeError, 'Scoped CDK diff failed'): self.cli('diff')

    def test_publication_verifies_exact_candidate_and_other_module_pointers_then_retains_release_archive(self):
        _, result = self.cli('publish'); self.assertTrue(result['other_module_pointers_preserved']); self.assertEqual(self.current, release.CANDIDATE); self.assertEqual(self.pointers[1]['active_version_id'], 'unchanged-other-prompt')
        _, verified = self.cli('verify'); self.assertEqual(verified['public_checks']['new_model_calls'], 0)
        _, retained = self.cli('archive-release'); self.assertEqual(len(retained['release_archive']['objects']), 1)
        path = self.root / 'docs/idea-interview-release-evidence-v1.tar.gz'; path.write_bytes(evidence_bundle({'original.bin': b'changed'}, changed_manifest=True))
        with self.assertRaisesRegex(RuntimeError, 'Original release evidence hash differs'): self.cli('archive-release')

    def test_frontend_status_retains_private_bounded_build_logs_and_compares_actual_chunk_bytes(self):
        directory, receipt = self.cli('frontend-status'); self.assertEqual(receipt['frontend']['build_log']['commit_ids'], ['a' * 40]); self.assertNotIn('logUrl', canonical(receipt['frontend']).decode()); self.assertEqual((directory / 'amplify-build-private.log').stat().st_mode & 0o777, 0o600); self.assertEqual((directory / 'deployed-guide-client.js').read_bytes(), self.chunk); self.assertFalse(receipt['frontend']['guide_source_client']['authenticated_rendering_verified'])
        self.front_status = 'RUNNING'; _, receipt = self.cli('frontend-status'); self.assertNotIn('guide_source_client', receipt['frontend'])
        self.build_log = b'x' * 10000001
        with self.assertRaisesRegex(RuntimeError, 'collection bound'): self.cli('frontend-status')

    def test_cli_rejects_incompatible_state_and_retains_failed_receipts_without_overwriting_history(self):
        for mode, message in [('migrate', 'existing prompt'), ('diff', 'old prompt active'), ('publish', 'Unexpected active prompt')]:
            with self.subTest(mode=mode):
                self.current = release.CANDIDATE
                with self.assertRaisesRegex(RuntimeError, message): self.cli(mode)
        self.current = release.PRIOR; self.drafts = [{'id': release.CANDIDATE}]
        with self.assertRaisesRegex(RuntimeError, 'do not overwrite history'): self.cli('migrate')
        with self.assertRaisesRegex(RuntimeError, 'Expected published candidate'): self.cli('archive-release')
        receipts = [json.loads(path.read_bytes()) for path in (self.root / '.test-artifacts/idea-interview/release').glob('*/receipt.json')]
        self.assertTrue(receipts); self.assertTrue(all(item['status'] == 'failed' and item['ended_at'] and item['reason'] for item in receipts)); self.assertEqual(self.objects, {})

    def test_layer_restoration_rejects_wrong_layer_count_bad_checksum_and_archive_traversal(self):
        original = self.command
        for case, reason in [('count', 'Unexpected deployed layer set'), ('hash', 'ZIP checksum differs'), ('path', 'Invalid dependency layer path')]:
            with self.subTest(case=case):
                def aws(args, **options):
                    value = json.loads(original(args, **options))
                    if args[1:3] == ['lambda', 'get-function-configuration'] and case == 'count': value['Layers'] = []
                    if args[1:3] == ['lambda', 'get-layer-version-by-arn'] and case == 'hash': value['Content']['CodeSha256'] = 'changed'
                    return canonical(value)
                if case == 'path': self.layer = archive({'../escaped-dependency.py': b'never extract outside the layer'})
                with patch.object(release.subprocess, 'check_output', side_effect=aws), self.assertRaisesRegex(RuntimeError, reason): self.cli('prepare-layer')
        self.assertFalse((self.root / 'agent/escaped-dependency.py').exists())

    def test_migration_completion_requires_unchanged_other_pointers_counts_and_exact_unpublished_candidate(self):
        before = dict(pointers=copy.deepcopy(self.pointers), scientific_counts={'measurements': 0})
        for field, changed, reason in [('pointers', [], 'Active pointers changed'), ('scientific_counts', {'measurements': 1}, 'Scientific counts changed')]:
            with self.subTest(field=field):
                after = dict(before, **{field: changed})
                with patch.object(self.previous, 'inspect', side_effect=[before, after]), self.assertRaisesRegex(RuntimeError, reason): self.cli('migrate')
        original = self.query
        def query(sql, **options):
            value = original(sql, **options)
            if sql.startswith('select id,version,content_sha256,published_at from agent_prompt_versions where id='): value[0]['published_at'] = 'unexpected-existing-publication'
            return value
        with patch.object(self.admin, 'query', side_effect=query), self.assertRaisesRegex(RuntimeError, 'Draft differs'): self.cli('migrate')

    def test_publication_detects_concurrent_other_module_pointer_changes_without_recording_success(self):
        original = self.query
        def query(sql, **options):
            value = original(sql, **options)
            if sql.startswith('select publish_agent_prompt('): self.pointers[1]['active_version_id'] = 'changed-concurrent-pointer'
            return value
        with patch.object(self.admin, 'query', side_effect=query), self.assertRaisesRegex(RuntimeError, 'Unrelated prompt pointer changed'): self.cli('publish')
        receipts = list((self.root / '.test-artifacts/idea-interview/release').glob('*/receipt.json')); self.assertEqual(len(receipts), 1); receipt = json.loads(receipts[0].read_bytes()); self.assertEqual(receipt['status'], 'failed'); self.assertNotIn('other_module_pointers_preserved', receipt)

    def test_frontend_comparison_rejects_missing_clean_chunks_and_changed_downloaded_bytes(self):
        path = self.root.parent / 'jumpserve-front-end/.next/static/chunks/guide.js'; expected = path.read_bytes(); path.unlink()
        with self.assertRaisesRegex(RuntimeError, 'Expected one clean-build'): self.cli('frontend-status')
        path.write_bytes(expected); self.chunk = expected + b'changed deployed client'
        with self.assertRaisesRegex(RuntimeError, 'differs from the clean build'): self.cli('frontend-status')

    def test_entrypoint_rejects_unknown_modes_before_external_boundaries(self):
        path = ROOT / 'bin/idea-interview-release.py'
        with patch.object(sys, 'argv', [str(path), 'unsupported-unit-mode']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            exec(compile(path.read_bytes(), str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
        self.assertEqual(stopped.exception.code, 2); self.admin.query.assert_not_called(); self.run.assert_not_called()


if __name__ == '__main__': unittest.main()
