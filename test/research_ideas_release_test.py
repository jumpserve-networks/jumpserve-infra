"""Research-idea release units with synthetic SQL, Storage and CDK adapters."""
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
import zipfile
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/research-ideas-release.py'


class ResearchIdeasRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='idea-release-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.admin = types.SimpleNamespace(PROJECT_REF='synthetic-project',
            credential=Mock(return_value='synthetic-management-key'), query=Mock(),
            literal=lambda value: "'" + str(value).replace("'", "''") + "'")
        self.db = types.ModuleType('synthetic_research_admin')
        self.db.admin = self.admin
        self.db.targets = Mock(return_value={'account': 'synthetic-account'})
        self.opener = Mock()
        self.release = self.load()
        self.release.ROOT = self.root
        self.release.OPEN = self.opener
        self.output = self.root / 'output'
        self.output.mkdir()
        self.private_rows = [dict(relname=name, relrowsecurity=True, anon_access=False, browser_access=False) for name in self.release.PRIVATE]
        self.functions = [dict(proname=name, anon_execute=False, browser_execute=False) for name in [
            'research_save_idea_packet', 'research_begin_idea_run', 'research_finish_idea_run',
            'research_accept_idea_plan', 'research_prepare_idea_campaign', 'research_idea_ready', 'research_idea_owner']]
        self.pointer = [{'module_id': 'research-verification', 'active_version_id': None}]

    def specification(self, original, label, path, *args, **kwargs):
        if Path(path) != ROOT / 'bin/research-workflow-database.py':
            return original(label, path, *args, **kwargs)
        database = self.db
        class Loader:
            def create_module(self, spec): return database
            def exec_module(self, module): pass
        return importlib.machinery.ModuleSpec(label, Loader())

    def load(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)):
            spec = original('research_ideas_release_unit', SOURCE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def response(self, raw=b'', status=200):
        response = io.BytesIO(raw)
        response.status = status
        return response

    def security(self):
        return [copy.deepcopy(self.private_rows), copy.deepcopy(self.functions), [{'count': 0}], [{'public': False}], copy.deepcopy(self.pointer)]

    def test_target_requires_exact_project_identity_and_uses_management_auth(self):
        for identifier in ['synthetic-project', 'different-project', None]:
            self.opener.open.return_value = self.response(json.dumps({'id': identifier}).encode())
            if identifier == self.admin.PROJECT_REF:
                self.assertEqual(self.release.target(), {'account': 'synthetic-account', 'supabase_project_identity_verified': True})
            else:
                with self.assertRaisesRegex(RuntimeError, 'identity mismatch'):
                    self.release.target()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.supabase.com/v1/projects/synthetic-project')
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-management-key')
        self.assertEqual(self.opener.open.call_args.kwargs, {'timeout': 20})

    def test_inspect_reads_security_pointers_and_scientific_counts_without_mutations(self):
        values = [[{'original': key}] for key in ['relations', 'columns', 'pointers', 'publication_guard', 'scientific_counts']]
        self.admin.query.side_effect = values
        self.assertEqual(self.release.inspect(), dict(zip(['relations', 'columns', 'pointers', 'publication_guard', 'scientific_counts'], values)))
        self.assertTrue(all(not call.kwargs for call in self.admin.query.call_args_list))

    def test_verification_requires_private_rls_rpc_denial_origin_integrity_and_private_storage(self):
        self.admin.query.side_effect = self.security()
        result = self.release.verify()
        self.assertTrue(result['passed'])
        self.assertEqual(result['security'], self.private_rows)
        self.assertEqual(result['rpc'], self.functions)
        self.assertEqual(result['private_originals'], [{'public': False}])
        self.assertEqual(result['pointers'], self.pointer)
        cases = [('missing-table', 0), ('rls', 0), ('anonymous-read', 0), ('browser-write', 0),
            ('missing-rpc', 1), ('anonymous-rpc', 1), ('browser-rpc', 1), ('origin', 2), ('bucket-missing', 3), ('bucket-public', 3)]
        for failure, index in cases:
            values = self.security()
            if failure.startswith('missing-') or failure == 'bucket-missing': values[index].pop()
            elif failure == 'rls': values[0][0]['relrowsecurity'] = False
            elif failure == 'anonymous-read': values[0][0]['anon_access'] = True
            elif failure == 'browser-write': values[0][0]['browser_access'] = True
            elif failure == 'anonymous-rpc': values[1][0]['anon_execute'] = True
            elif failure == 'browser-rpc': values[1][0]['browser_execute'] = True
            elif failure == 'origin': values[2][0]['count'] = 1
            else: values[3][0]['public'] = True
            self.admin.query.side_effect = values
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                self.release.verify()

    def originals(self):
        folder = self.root / '.test-artifacts/research-ideas/evaluations/20261013T002350223340Z'
        folder.mkdir(parents=True)
        (folder / 'failed-output.txt').write_bytes(b'\xfforiginal failed provider output\n')
        (folder / 'successful-output.txt').write_bytes(b'original successful provider output\n')
        (folder / 'directory-is-not-a-file').mkdir()
        docs = self.root / 'docs'
        docs.mkdir(exist_ok=True)
        for name in ['research-ideas-protocol-v1.json', 'research-ideas-amendment-v2.json']:
            (docs / name).write_bytes(b'{"original":true,"zero":0}\n')
        (self.root / 'cdk.json').write_text(json.dumps({'context': {'supabaseAnonKey': 'synthetic-anonymous-key'}}))
        return folder

    def storage(self, upload_status=200, public_status=403, auth_status=200, readback=None):
        self.requests = []
        retained = {}
        def open_(request, timeout):
            self.requests.append(request)
            self.assertEqual(timeout, 20)
            if request.get_method() == 'POST':
                retained['raw'] = request.data
                self.assertEqual(request.get_header('X-upsert'), 'false')
                self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-service-key')
                if upload_status != 200:
                    raise urllib.error.HTTPError(request.full_url, upload_status, 'synthetic upload', {}, None)
                return self.response()
            if request.full_url.endswith('/auth/v1/settings'):
                return self.response(status=auth_status)
            if request.get_header('Apikey') == 'synthetic-anonymous-key':
                if public_status != 200:
                    raise urllib.error.HTTPError(request.full_url, public_status, 'synthetic private denial', {}, None)
                return self.response(b'public')
            return self.response(retained['raw'] if readback is None else readback)
        self.opener.open.side_effect = open_
        return patch.object(self.release.subprocess, 'check_output', return_value=json.dumps({'SecretString': 'synthetic-service-key'}).encode())

    def test_original_bundle_is_deterministic_hash_verified_and_anonymously_denied(self):
        self.originals()
        with self.storage():
            first = self.release.artifact_bundle(self.output)
            original = (self.output / 'evaluation-artifacts.zip').read_bytes()
            second = self.release.artifact_bundle(self.output)
        self.assertEqual(first, second)
        self.assertEqual(first['sha256'], self.release.sha(original))
        self.assertEqual(first['byte_count'], len(original))
        self.assertEqual(first['anonymous_read_status'], 403)
        self.assertIsNone(first['measured_charges_usd'])
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest, first['original_file_manifest'])
            self.assertEqual(len(manifest), 4)
            for item in manifest:
                raw = archive.read(item['path'])
                self.assertEqual(self.release.sha(raw), item['sha256'])
                self.assertEqual(len(raw), item['byte_count'])
            self.assertEqual(archive.read('evaluations/20261013T002350223340Z/failed-output.txt'), b'\xfforiginal failed provider output\n')

    def test_existing_content_addressed_upload_requires_identical_private_readback(self):
        self.originals()
        with self.storage(upload_status=409):
            self.assertTrue(self.release.artifact_bundle(self.output)['stored_bytes_verified_after_retrieval'])
        for settings, message in [({'upload_status': 503}, 'upload failed'), ({'readback': b'different'}, 'hash differs'),
                                  ({'auth_status': 401}, 'credential validation'), ({'public_status': 200}, 'became public')]:
            with self.subTest(settings=settings), self.storage(**settings), self.assertRaisesRegex(RuntimeError, message):
                self.release.artifact_bundle(self.output)

    def test_unconfirmed_auth_response_cleanup_cannot_become_successful_artifact_verification(self):
        self.originals()
        class UnconfirmedResponse(io.BytesIO):
            status = 200
            def __exit__(self, *args):
                super().__exit__(*args)
                raise OSError('Synthetic auth response close unconfirmed')
        with self.storage():
            original_open = self.opener.open.side_effect
            def open_(request, timeout):
                if request.full_url.endswith('/auth/v1/settings'):
                    return UnconfirmedResponse()
                return original_open(request, timeout)
            self.opener.open.side_effect = open_
            with self.assertRaisesRegex(OSError, 'close unconfirmed'):
                self.release.artifact_bundle(self.output)
        self.assertFalse(any(request.get_header('Apikey') == 'synthetic-anonymous-key' for request in self.requests))

    def test_missing_or_oversized_original_bundle_fails_before_credentials_or_storage(self):
        with patch.object(self.release.subprocess, 'check_output') as credentials, self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.release.artifact_bundle(self.output)
        credentials.assert_not_called()
        folder = self.originals()
        (folder / 'large-output.bin').write_bytes(random.Random(0).randbytes(2000001))
        with patch.object(self.release.subprocess, 'check_output') as credentials, self.assertRaisesRegex(RuntimeError, 'release budget'):
            self.release.artifact_bundle(self.output)
        credentials.assert_not_called()
        self.opener.open.assert_not_called()

    def evaluation(self):
        directory = self.root / 'docs/research-ideas-release-evidence'
        directory.mkdir(parents=True)
        original = self.root / '.test-artifacts/research-ideas/evaluations/20261013T002350223340Z'
        original.mkdir(parents=True)
        cases = []
        for index in range(8):
            name = 'synthetic-' + str(index)
            raw = ('original answer ' + str(index)).encode()
            (original / (name + '-output.txt')).write_bytes(raw)
            cases.append(dict(name=name, passed=True, output_sha256=self.release.sha(raw)))
        runtime = self.root / 'synthetic-runtime.py'
        runtime.write_bytes(b'# retained evaluated source\n')
        report = dict(prompt_version_id=self.release.CANDIDATE, reviewer={'passed': True}, cases=cases,
            runtime_hashes={'synthetic-runtime.py': self.release.sha(runtime.read_bytes())}, prompt_content_sha256='a' * 64)
        path = directory / 'evaluation-reviewed-v2.json'
        path.write_text(json.dumps(report))
        return path, report

    def test_publication_requires_all_cases_reviewer_runtime_and_original_output_hashes(self):
        path, original = self.evaluation()
        for failure in ['candidate', 'reviewer', 'count', 'case', 'runtime', 'answer']:
            report = copy.deepcopy(original)
            if failure == 'candidate': report['prompt_version_id'] = 'different'
            elif failure == 'reviewer': report['reviewer']['passed'] = False
            elif failure == 'count': report['cases'].pop()
            elif failure == 'case': report['cases'][0]['passed'] = False
            elif failure == 'runtime': report['runtime_hashes']['synthetic-runtime.py'] = 'b' * 64
            else: report['cases'][0]['output_sha256'] = 'b' * 64
            path.write_text(json.dumps(report))
            with self.subTest(failure=failure), patch.object(self.release, 'artifact_bundle') as bundle, self.assertRaises(RuntimeError):
                self.release.publish(self.output)
            bundle.assert_not_called()
        self.admin.query.assert_not_called()

    def test_publication_is_idempotent_and_refuses_unexpected_previous_pointers(self):
        self.evaluation()
        for rows, message in [([], 'settings missing'), ([{'active_version_id': 'unexpected'}], 'Unexpected prior')]:
            self.admin.query.return_value = rows
            with self.subTest(rows=rows), patch.object(self.release, 'artifact_bundle', return_value={'sha256': 'original'}), self.assertRaisesRegex(RuntimeError, message):
                self.release.publish(self.output)
        self.admin.query.return_value = [{'active_version_id': self.release.CANDIDATE}]
        with patch.object(self.release, 'artifact_bundle', return_value={'sha256': 'original'}):
            self.assertEqual(self.release.publish(self.output), dict(replayed=True, active_version_id=self.release.CANDIDATE, artifact={'sha256': 'original'}))

    def test_publication_submits_exact_evaluated_identity_then_verifies_the_saved_pointer(self):
        _, report = self.evaluation()
        active = [dict(id=self.release.CANDIDATE, content_sha256=report['prompt_content_sha256'], version='evaluated-v2')]
        self.admin.query.side_effect = [[{'active_version_id': None}], [{'published': True}], active]
        with patch.object(self.release, 'artifact_bundle', return_value={'sha256': 'original'}):
            result = self.release.publish(self.output)
        self.assertEqual(result['active'], active)
        submission = self.admin.query.call_args_list[-2]
        self.assertEqual(submission.kwargs, {'read_only': False})
        self.assertIn('publish_agent_prompt(', submission.args[0])
        self.assertIn(self.release.CANDIDATE, submission.args[0])
        for readback in [[], [dict(id='wrong', content_sha256=report['prompt_content_sha256'])], [dict(id=self.release.CANDIDATE, content_sha256='wrong')]]:
            self.admin.query.side_effect = [[{'active_version_id': None}], [], readback]
            with self.subTest(readback=readback), patch.object(self.release, 'artifact_bundle', return_value={}), self.assertRaisesRegex(RuntimeError, 'pointer differs'):
                self.release.publish(self.output)

    def call(self, mode):
        output = io.StringIO()
        try:
            with patch.object(sys, 'argv', [str(SOURCE), mode]), contextlib.redirect_stdout(output):
                self.release.main()
        finally:
            if output.getvalue():
                self.last = json.loads(output.getvalue())
                self.receipt = json.loads((Path(self.last['directory']) / 'receipt.json').read_bytes())
        return self.receipt

    def test_read_and_publication_modes_retain_their_results_and_terminal_receipts(self):
        for mode, field in [('inspect', 'inspection'), ('verify', 'verification'), ('publish', 'publication')]:
            with self.subTest(mode=mode), patch.object(self.release, 'target', return_value={'verified': True}), patch.object(self.release, mode, return_value={'original': mode}) as operation:
                result = self.call(mode)
            self.assertEqual(result[field], {'original': mode})
            self.assertEqual(result['status'], 'complete')
            self.assertIsNone(result['measured_charges_usd'])
            self.assertIn('ended_at', result)
            if mode == 'publish': operation.assert_called_once_with(Path(self.last['directory']))
            else: operation.assert_called_once_with()

    def test_migrations_retain_exact_bytes_hashes_and_do_not_change_existing_scientific_counts_or_prompts(self):
        directory = self.root / 'database'
        directory.mkdir()
        originals = {}
        for name in self.release.MIGRATIONS:
            raw = (ROOT / 'database' / name).read_bytes()
            (directory / name).write_bytes(raw)
            originals[name] = raw
        inspection = dict(relations=[], scientific_counts=[{'count': 3}], pointers=self.pointer)
        with patch.object(self.release, 'target', return_value={}), patch.object(self.release, 'inspect', side_effect=[inspection, copy.deepcopy(inspection)]), patch.object(self.release, 'verify', return_value={'passed': True}):
            result = self.call('migrate')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['migrations']), len(originals))
        for entry, submission in zip(result['migrations'], self.admin.query.call_args_list):
            self.assertEqual(entry['status'], 'complete')
            self.assertEqual(entry['sha256'], self.release.sha(originals[entry['name']]))
            self.assertEqual(entry['byte_count'], len(originals[entry['name']]))
            self.assertEqual(submission.args, (originals[entry['name']].decode(),))
            self.assertEqual(submission.kwargs, {'read_only': False})
        for failure in ['existing', 'counts', 'pointers']:
            before = copy.deepcopy(inspection)
            after = copy.deepcopy(inspection)
            if failure == 'existing': before['relations'] = [{'relname': self.release.PRIVATE[0]}]
            elif failure == 'counts': after['scientific_counts'][0]['count'] = 4
            else: after['pointers'][0]['active_version_id'] = 'changed'
            with self.subTest(failure=failure), patch.object(self.release, 'target', return_value={}), patch.object(self.release, 'inspect', side_effect=[before, after]), patch.object(self.release, 'verify', return_value={'passed': True}), self.assertRaisesRegex(RuntimeError, 'already exists|counts changed|pointers changed'):
                self.call('migrate')
            self.assertEqual(self.receipt['status'], 'failed')

    def test_uncertain_migration_retains_running_identity_and_stops_without_reapplication(self):
        (self.root / 'database').mkdir()
        name = self.release.MIGRATIONS[0]
        raw = (ROOT / 'database' / name).read_bytes()
        (self.root / 'database' / name).write_bytes(raw)
        self.admin.query.side_effect = TimeoutError('Synthetic original submission unconfirmed')
        with patch.object(self.release, 'target', return_value={}), patch.object(self.release, 'inspect', return_value=dict(relations=[])), self.assertRaises(TimeoutError):
            self.call('migrate')
        self.assertEqual(len(self.receipt['migrations']), 1)
        self.assertEqual(self.receipt['migrations'][0]['status'], 'running')
        self.assertEqual(self.receipt['migrations'][0]['sha256'], self.release.sha(raw))
        self.assertEqual(self.admin.query.call_count, 1)

    def test_cdk_modes_build_only_scoped_commands_and_keep_credentials_out_of_receipts(self):
        credentials = dict(AccessKeyId='synthetic-access', SecretAccessKey='synthetic-secret', SessionToken='synthetic-session')
        for mode in ['diff', 'deploy']:
            self.admin.query.return_value = [{'active_version_id': self.release.CANDIDATE}]
            with self.subTest(mode=mode), patch.object(self.release, 'target', return_value={}), patch.object(self.release, 'verify') as verify, patch.object(self.release.subprocess, 'check_output', return_value=json.dumps(credentials).encode()), patch.object(self.release.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, patch.dict(os.environ, {'AWS_PROFILE': 'synthetic-profile'}):
                result = self.call(mode)
            command = run.call_args.args[0]
            self.assertEqual(command[:5], ['npx', 'cdk', mode, 'JumpServeBenchmarkStack', 'JumpServeAgentStack'])
            self.assertNotIn('AWS_PROFILE', run.call_args.kwargs['env'])
            self.assertEqual(run.call_args.kwargs['env']['AWS_SESSION_TOKEN'], 'synthetic-session')
            self.assertEqual(result['command'], command)
            self.assertNotIn('synthetic-secret', json.dumps(result))
            if mode == 'diff': self.assertIn('--no-change-set', command); verify.assert_not_called()
            else: self.assertIn('--outputs-file', command); verify.assert_called_once_with()

    def test_deployment_preconditions_and_process_failure_never_report_release_success(self):
        self.admin.query.return_value = [{'active_version_id': 'different'}]
        with patch.object(self.release, 'target', return_value={}), patch.object(self.release, 'verify'), patch.object(self.release.subprocess, 'check_output') as credentials, self.assertRaisesRegex(RuntimeError, 'not active'):
            self.call('deploy')
        credentials.assert_not_called()
        with patch.object(self.release, 'target', return_value={}), patch.object(self.release.subprocess, 'check_output', return_value=json.dumps(dict(AccessKeyId='a', SecretAccessKey='b', SessionToken='c')).encode()), patch.object(self.release.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)), self.assertRaisesRegex(RuntimeError, 'Scoped CDK diff failed'):
            self.call('diff')
        self.assertEqual(self.receipt['status'], 'failed')
        self.assertTrue((Path(self.last['directory']) / 'cdk.log').is_file())

    def test_unknown_cli_mode_exits_before_target_or_external_operations(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)), patch.object(sys, 'argv', [str(SOURCE), 'arbitrary-command']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            runpy.run_path(str(SOURCE), run_name='__main__')
        self.assertEqual(caught.exception.code, 2)
        self.db.targets.assert_not_called()
        self.admin.query.assert_not_called()


if __name__ == '__main__':
    unittest.main()
