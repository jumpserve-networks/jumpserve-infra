"""Fixed-target release validation with real private archives and synthetic cloud/SQL adapters.

No model call, publication, migration or deployment reaches an external service.
"""
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('claim_design_release_unit', ROOT / 'bin/claim-design-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


class ClaimDesignRelease(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='claim-release-unit-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'infra'; self.back = Path(temp.name) / 'backend'; self.root.mkdir(); self.back.mkdir()
        self.enterContext(patch.object(release, 'ROOT', self.root)); self.enterContext(patch.object(release, 'BACKEND', self.back)); self.enterContext(patch.object(release, 'REPORT', self.root / 'docs/evaluation-reviewed.json'))
        self.queue, self.guard, self.admin = MagicMock(), MagicMock(), MagicMock()
        self.enterContext(patch.object(release, 'queue', self.queue)); self.enterContext(patch.object(release, 'guard', self.guard)); self.enterContext(patch.object(release, 'admin', self.admin))
        self.queue.PRIVATE = {'retained-private-table'}; self.queue.security.side_effect = self.queue_security
        self.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"
        self.admin.query.side_effect = self.query; self.guard.OPEN.open.side_effect = self.open; self.queue.aws.side_effect = self.aws
        self.guard.target.return_value = {'aws_account': '395567831870', 'supabase_project': 'regphejnlvfpyokpniny'}; self.guard.inspect.side_effect = self.inspect
        self.manifest = {'version': 16, 'source_revision': 'f' * 40, 'files': {'fixture.py': 'a' * 64}}; self.queue.source.return_value = self.manifest
        self.queue.archives.return_value = ([{'archive_sha256': 'a' * 64}], {'fixture': True})
        self.active_exists, self.active_id, self.claim_table, self.reuse_present = True, release.CANDIDATE, False, False
        self.definition = 'Synthetic definition calls publish_agent_prompt_before_claim_v6_exact'
        self.functions = [dict(proname=name, anon_execute=False, browser_execute=False) for name in ['research_initialize_claim_design', 'publish_agent_prompt', 'research_reuse_claim_packet']]
        self.applied, self.published, self.cloud_commands, self.objects = [], [], [], {}
        self.anonymous_status = 403; self.denial_status = 401; self.cdk_exit = 0; self.dirty = False; self.parameter_drift = False
        self.pointer_drift = False; self.scientific_drift = False; self.other_pointer = 'original-other-prompt'; self.publication_id = release.CANDIDATE
        self.parameters = [{'ParameterKey': 'Retained', 'ParameterValue': 'original'}]
        self.seed = {'system_prompt': 'Synthetic reviewed system', 'research_context': 'Synthetic recorded context'}; self.prompt_sha = release.sha((self.seed['system_prompt'] + '\n\n' + self.seed['research_context']).encode())
        self.report = dict(prompt_version_id=release.CANDIDATE, reviewer={'passed': True}, evaluation_kind='archived-model-output-replay', new_provider_calls=0, cases=[dict(passed=True, status='complete', raw_answer_reviewed=True, rendered_answer_reviewed=True) for _ in range(20)], input_sha256={}, prompt_content_sha256=self.prompt_sha)
        for name in ['handler.py', 'modules.py', 'research_ideas.py', 'claim_experiment_design.py', 'claim-decision-policy-v1.json']:
            self.write('agent/' + name, ('Synthetic original source: ' + name).encode())
        for name in ['agent/claim_experiment_design.py', 'agent/research_ideas.py']: self.report['input_sha256'][name] = release.sha((self.root / name).read_bytes())
        self.write('database/seed-claim-experiment-design-v6.json', json.dumps(self.seed).encode()); self.write('cdk.json', b'{"context":{"supabaseAnonKey":"synthetic-public-key"}}')
        self.save_report()
        for i, folder in enumerate(['claim-design-validation', 'claim-design-correction-validation', 'claim-design-followup-validation']):
            raw = ('Retained failed or successful original ' + folder).encode(); self.write('docs/' + folder + '/original.bin', raw)
            record = dict(path='original.bin', sha256=release.sha(raw), byte_count=len(raw)); entries = {'original.bin': record} if i == 0 else [record]
            self.write('docs/' + folder + '/artifact-manifest.json', json.dumps({'files': entries}).encode())
        for name in [*release.MIGRATIONS, '202610180001_claim_packet_reuse.sql']: self.write('database/' + name, ('-- Synthetic migration ' + name).encode())
        for name in ['claim-design-release-protocol-v1.md', 'claim-experiment-design-protocol.md', 'claim-design-production-release-v1.md', 'claim-packet-reuse-release-protocol-v1.md', 'claim-packet-reuse-production-release-v1.md', 'claim-design-authenticated-verification-protocol-v1.md', 'claim-design-authenticated-verification-v1.md', 'claim-design-authenticated-verification-v1.json']:
            self.write('docs/' + name, ('Synthetic retained protocol: ' + name).encode())
        for folder in ['claim-design-production-release-evidence', 'claim-packet-reuse-release-evidence-v1']: self.write('docs/' + folder + '/original.json', b'{"synthetic":true}')
        self.agent_raw = self.zip({p.name: p.read_bytes() for p in (self.root / 'agent').iterdir()}); self.agent_arn = 'arn:aws:lambda:us-east-1:395567831870:function:SyntheticAgent'
        self.agent_url = 'https://unit.example.test/agent-original.zip'; self.supabase_url = 'https://regphejnlvfpyokpniny.supabase.co'
        self.enterContext(patch.object(release.subprocess, 'check_output', side_effect=self.check_output)); self.enterContext(patch.object(release.subprocess, 'run', side_effect=self.run_cdk))

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def save_report(self): self.write('docs/evaluation-reviewed.json', json.dumps(self.report).encode())
    def zip(self, entries):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, raw in entries.items(): archive.writestr(name, raw)
        return buffer.getvalue()
    def queue_security(self):
        self.assertIn('research_claim_designs', self.queue.PRIVATE); return {'private_relations_checked': True}
    def pointer_rows(self):
        rows = [{'module_id': 'unrelated-module', 'active_version_id': self.other_pointer}]
        if self.active_exists: rows.append({'module_id': release.MODULE, 'active_version_id': self.active_id})
        return rows
    def inspect(self):
        return {'pointers': copy.deepcopy(self.pointer_rows()), 'scientific_counts': {'studies': 7, 'measurements': 14 if self.scientific_drift and self.applied else 13}}
    def query(self, sql, **options):
        if sql.startswith('select module_id,active_version_id'): return self.pointer_rows()
        if sql.startswith('select s.active_version_id'): return [dict(active_version_id=self.active_id, version='claim-v6', content_sha256=self.prompt_sha, published_at='2026-10-18T00:00:00Z' if self.active_id else None)] if self.active_exists else []
        if sql.startswith('select proname,'): return copy.deepcopy(self.functions)
        if sql.startswith('select pg_get_functiondef'): return [{'definition': self.definition}]
        if "to_regclass('public.research_claim_designs')" in sql: return [{'present': 'research_claim_designs' if self.claim_table else None}]
        if "to_regprocedure('public.research_reuse_claim_packet" in sql: return [{'present': 'reuse' if self.reuse_present else None}]
        if sql.startswith('-- Synthetic migration '):
            self.assertFalse(options['read_only']); name = sql.removeprefix('-- Synthetic migration '); self.applied.append(name)
            if name == '202610180001_claim_packet_reuse.sql': self.reuse_present = True
            else: self.claim_table, self.active_exists = True, True; self.active_id = None
            if self.pointer_drift: self.other_pointer = 'unexpected-other-prompt'
            return []
        if sql.startswith('select publish_agent_prompt('):
            self.assertFalse(options['read_only']); self.assertIn(self.prompt_sha, sql); self.published.append(sql); self.active_id = self.publication_id
            if self.pointer_drift: self.other_pointer = 'unexpected-other-prompt'
            return [{'published': True}]
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        self.cloud_commands.append((service, operation, args))
        if (service, operation) == ('cloudformation', 'describe-stack-resource'): return {'StackResourceDetail': {'PhysicalResourceId': 'SyntheticAgent'}}
        if (service, operation) == ('lambda', 'get-function'):
            return dict(Configuration=dict(FunctionArn=self.agent_arn, FunctionName='SyntheticAgent', Environment={'Variables': {'SUPABASE_URL': self.supabase_url}}, CodeSha256=base64.b64encode(hashlib.sha256(self.agent_raw).digest()).decode(), Runtime='python3.12', MemorySize=512, Timeout=235, LastModified='2026-10-18'), Code={'Location': self.agent_url})
        if (service, operation) == ('secretsmanager', 'get-secret-value'): return {'SecretString': 'synthetic-private-key'}
        if (service, operation) == ('configure', 'export-credentials'): return dict(AccessKeyId='synthetic-access', SecretAccessKey='synthetic-secret', SessionToken='synthetic-session')
        if (service, operation) == ('cloudformation', 'describe-stacks'): return {'Stacks': [{'StackStatus': 'UPDATE_COMPLETE', 'Parameters': copy.deepcopy(self.parameters)}]}
        if (service, operation) == ('amplify', 'list-jobs'): return {'jobSummaries': [{'jobId': 'recorded-job', 'status': 'SUCCEED'}]}
        if (service, operation) == ('amplify', 'start-job'): return {'jobSummary': {'jobId': 'synthetic-new-job', 'status': 'PENDING'}}
        raise AssertionError((service, operation, args))
    def response(self, raw): return io.BytesIO(raw)
    def open(self, request, **options):
        url = request if isinstance(request, str) else request.full_url
        if url == self.agent_url: return self.response(self.agent_raw)
        if '/storage/v1/object/' in url:
            method = request.get_method()
            if method == 'POST':
                self.assertEqual(request.get_header('X-upsert'), 'false'); self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-private-key')
                if url in self.objects: raise urllib.error.HTTPError(url, 409, 'Already retained', {}, None)
                self.objects[url] = request.data; return self.response(b'{}')
            if request.get_header('Apikey') == 'synthetic-public-key':
                if self.anonymous_status >= 400: raise urllib.error.HTTPError(url, self.anonymous_status, 'Synthetic denied', {}, None)
                return self.response(b'public')
            return self.response(self.objects[url])
        if url == release.API + '/capabilities': return self.response(b'{"preparation":{"claim_design_version":"claim-experiment-design-v1"}}')
        if url.startswith(release.API) or url == release.AGENT:
            if self.denial_status >= 400: raise urllib.error.HTTPError(url, self.denial_status, 'Synthetic denied', {}, None)
            return self.response(b'{}')
        raise AssertionError('Unexpected endpoint: ' + url)
    def check_output(self, command, **options):
        self.assertEqual(options['cwd'], self.back)
        if command == ['git', 'rev-parse', 'HEAD']: return self.manifest['source_revision'] + '\n'
        if command == ['git', 'status', '--porcelain']: return ' M changed.py\n' if self.dirty else ''
        raise AssertionError(command)
    def run_cdk(self, command, **options):
        self.assertEqual(command[:2], ['npx', 'cdk']); self.assertEqual(options['cwd'], self.root); self.assertEqual(options['timeout'], 1800)
        self.assertNotIn('AWS_PROFILE', options['env']); self.assertEqual(options['env']['AWS_ACCESS_KEY_ID'], 'synthetic-access')
        if self.parameter_drift: self.parameters[0]['ParameterValue'] = 'changed'
        options['stdout'].write('Synthetic CDK command output\n'); return subprocess.CompletedProcess(command, self.cdk_exit)
    def cli(self, mode):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['claim-design-release.py', mode]), contextlib.redirect_stdout(output): release.main()
        value = json.loads(output.getvalue()); return json.loads((Path(value['directory']) / 'receipt.json').read_bytes())
    def failed_receipt(self):
        return json.loads(sorted(self.root.glob('.test-artifacts/claim-design/release/*/receipt.json'))[-1].read_bytes())

    def test_reviewed_replay_requires_all_twenty_actual_answer_reviews_and_unchanged_sources(self):
        report, manifests = release.evaluated(); self.assertEqual(report, self.report); self.assertEqual(len(manifests), 3); self.assertTrue(all(v['files'] == 1 for v in manifests))
        original = copy.deepcopy(self.report)
        for change in [dict(prompt_version_id='other'), dict(new_provider_calls=1), dict(evaluation_kind='new-model-run'), dict(reviewer={'passed': False}), dict(cases=original['cases'][:-1]), dict(cases=[dict(c, raw_answer_reviewed=False) for c in original['cases']])]:
            self.report = dict(original, **change); self.save_report()
            with self.subTest(change=list(change)), self.assertRaisesRegex(RuntimeError, 'eligible'): release.evaluated()
        self.report = original; self.save_report(); self.write('agent/research_ideas.py', b'Changed after evaluation')
        with self.assertRaisesRegex(RuntimeError, 'agent source changed'): release.evaluated()

    def test_changed_prompt_or_archived_original_is_not_eligible(self):
        self.seed['system_prompt'] = 'Changed prompt'; self.write('database/seed-claim-experiment-design-v6.json', json.dumps(self.seed).encode())
        with self.assertRaisesRegex(RuntimeError, 'prompt content changed'): release.evaluated()
        self.seed['system_prompt'] = 'Synthetic reviewed system'; self.write('database/seed-claim-experiment-design-v6.json', json.dumps(self.seed).encode()); self.write('docs/claim-design-validation/original.bin', b'Changed original')
        with self.assertRaisesRegex(RuntimeError, 'Archived evidence differs'): release.evaluated()

    def test_security_restores_private_relation_inventory_and_requires_private_rpc_and_final_guard(self):
        original = set(self.queue.PRIVATE); result = release.security(); self.assertEqual(self.queue.PRIVATE, original); self.assertEqual(result['final_publication_guard_sha256'], release.sha(self.definition.encode()))
        for rows in [[], [dict(self.functions[0], anon_execute=True)], [dict(r, browser_execute=True) for r in self.functions]]:
            self.functions = rows
            with self.assertRaisesRegex(RuntimeError, 'RPC permissions'): release.security()
            self.assertEqual(self.queue.PRIVATE, original)
        self.queue.security.side_effect = RuntimeError('Synthetic queue-security failure')
        with self.assertRaisesRegex(RuntimeError, 'queue-security'): release.security()
        self.assertEqual(self.queue.PRIVATE, original)

    def test_agent_archives_are_exact_originals_bound_to_account_project_and_source(self):
        out = self.root / 'inspection'; out.mkdir(); result = release.agent_archive(out, expected=True)
        self.assertEqual((out / 'agent-original.zip').read_bytes(), self.agent_raw); self.assertEqual(len(result['source_hashes']), 5); self.assertEqual(result['layers'], [])
        self.agent_raw = self.zip({'handler.py': b'Synthetic older deployed handler'}); self.assertEqual(len(release.agent_archive(out)['source_hashes']), 1)
        with self.assertRaisesRegex(RuntimeError, 'source differs'): release.agent_archive(out, expected=True)
        self.agent_raw = self.zip({'handler.py': (self.root / 'agent/handler.py').read_bytes()})
        with self.assertRaisesRegex(RuntimeError, 'file absent'): release.agent_archive(out, expected=True)
        self.agent_arn = self.agent_arn.replace('395567831870', '000000000000')
        with self.assertRaisesRegex(RuntimeError, 'target differs'): release.agent_archive(out)

    def test_private_evidence_archives_roundtrip_originals_and_reconcile_existing_identity_without_overwrite(self):
        out = self.root / 'archives'; out.mkdir()
        for release_mode, reuse, expected in [(False, False, 'evaluation-originals'), (True, False, 'release-receipts'), (False, True, 'claim-packet-reuse-release-receipts')]:
            result = release.archive_evidence(out, release=release_mode, reuse=reuse); repeated = release.archive_evidence(out, release=release_mode, reuse=reuse)
            self.assertEqual(result, repeated); self.assertTrue(result['retrieved_hash_verified']); self.assertEqual(result['kind'], expected); self.assertEqual(result['anonymous_status'], 403); self.assertIsNone(result['measured_storage_charges_usd'])
            raw = next(value for value in self.objects.values() if release.sha(value) == result['sha256'])
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for entry in json.loads(archive.read('manifest.json')):
                    self.assertEqual(release.sha(archive.read(entry['path'])), entry['sha256']); self.assertEqual(archive.getinfo(entry['path']).date_time, (1980, 1, 1, 0, 0, 0))
        self.anonymous_status = 200
        with self.assertRaisesRegex(RuntimeError, 'anonymous access'): release.archive_evidence(out)

    def test_anonymous_request_checks_require_auth_denial_and_retain_the_method(self):
        self.assertEqual(release.deny(release.API + '/private')['method'], 'GET'); self.assertEqual(release.deny(release.AGENT, {'action': 'capabilities'})['method'], 'POST')
        for status in [200, 500]:
            self.denial_status = status
            with self.assertRaisesRegex(RuntimeError, 'not denied'): release.deny(release.API + '/private')

    def test_readonly_inspection_retains_original_archives_without_mutation_or_model_calls(self):
        receipt = self.cli('inspect'); self.assertEqual(receipt['status'], 'complete'); self.assertEqual(receipt['new_model_calls'], 0); self.assertEqual(receipt['new_experiment_instances'], 0); self.assertIsNone(receipt['measured_charges_usd'])
        self.assertIn('agent', receipt); self.assertIn('api_originals', receipt); self.assertEqual(receipt['evaluated_report_sha256'], release.sha(release.REPORT.read_bytes())); self.assertFalse(self.applied or self.published)
        self.assertFalse(any(operation == 'start-job' for _, operation, _ in self.cloud_commands))

    def test_migrations_record_every_exact_original_and_refuse_to_repeat_a_partially_applied_release(self):
        self.active_exists = False; receipt = self.cli('migrate'); self.assertEqual(self.applied, list(release.MIGRATIONS)); self.assertEqual(receipt['status'], 'complete')
        self.assertTrue(all(v['status'] == 'complete' for v in receipt['migrations'])); self.assertEqual(receipt['before']['scientific_counts'], receipt['after']['scientific_counts'])
        for item in receipt['migrations']: self.assertEqual(item['sha256'], release.sha((self.root / 'database' / item['name']).read_bytes()))
        count = len(self.applied)
        with self.assertRaisesRegex(RuntimeError, 'partly/presently applied'): self.cli('migrate')
        self.assertEqual(len(self.applied), count); self.assertEqual(self.failed_receipt()['status'], 'failed')

    def test_migration_checks_detect_unrelated_pointer_and_scientific_count_changes(self):
        self.active_exists = False; self.pointer_drift = True
        with self.assertRaisesRegex(RuntimeError, 'Unrelated prompt pointers'): self.cli('migrate')
        self.assertEqual(self.failed_receipt()['status'], 'failed')
        self.active_exists = False; self.claim_table = False; self.applied = []; self.other_pointer = 'original-other-prompt'; self.pointer_drift = False; self.scientific_drift = True
        with self.assertRaisesRegex(RuntimeError, 'Scientific counts changed'): self.cli('migrate')

    def test_owner_only_reuse_migration_preserves_all_prompt_pointers_and_original_receipt(self):
        self.claim_table = True; before = copy.deepcopy(self.pointer_rows()); receipt = self.cli('migrate-reuse')
        self.assertTrue(receipt['prompt_pointers_preserved']); self.assertEqual(self.pointer_rows(), before); self.assertEqual(self.applied, ['202610180001_claim_packet_reuse.sql'])
        with self.assertRaisesRegex(RuntimeError, 'already applied'): self.cli('migrate-reuse')

    def test_reuse_rejects_an_unexpected_active_prompt_missing_rpc_or_changed_pointer(self):
        self.active_id = 'unexpected'
        with self.assertRaisesRegex(RuntimeError, 'Unexpected active'): self.cli('migrate-reuse')
        self.assertFalse(self.applied); self.active_id = release.CANDIDATE; self.functions.pop()
        with self.assertRaisesRegex(RuntimeError, 'reuse RPC missing'): self.cli('migrate-reuse')
        self.reuse_present = False; self.functions.append(dict(proname='research_reuse_claim_packet', anon_execute=False, browser_execute=False)); self.pointer_drift = True
        with self.assertRaisesRegex(RuntimeError, 'pointer changed'): self.cli('migrate-reuse')

    def test_diff_and_deploy_commands_stay_scoped_to_the_requested_stack_with_exact_source_checks(self):
        for mode in ['diff-api', 'diff-agent', 'deploy-api', 'deploy-agent']:
            receipt = self.cli(mode); command = receipt['command']; self.assertEqual(command[2], 'deploy' if mode.startswith('deploy') else 'diff')
            self.assertEqual(command[3], 'JumpServeBenchmarkStack' if mode.endswith('api') else 'JumpServeAgentStack'); self.assertIn('--exclusively', command)
            self.assertEqual('--no-change-set' in command, mode.startswith('diff')); self.assertEqual('--require-approval' in command, mode.startswith('deploy'))
            self.assertNotIn('synthetic-secret', json.dumps(receipt)); self.assertEqual(receipt['status'], 'complete')
        self.assertEqual(len(list(self.root.glob('.test-artifacts/claim-design/release/*/before-agent/agent-original.zip'))), 1)
        self.assertTrue(any(call.args[0].name == 'before-api' for call in self.queue.archives.call_args_list))

    def test_dirty_sources_cdk_failure_and_parameter_drift_never_produce_a_complete_deployment_receipt(self):
        self.dirty = True
        with self.assertRaisesRegex(RuntimeError, 'clean committed backend'): self.cli('deploy-api')
        self.assertFalse(any(service == 'configure' for service, _, _ in self.cloud_commands))
        self.dirty = False; self.cdk_exit = 1
        with self.assertRaisesRegex(RuntimeError, 'Scoped CDK failed'): self.cli('deploy-agent')
        self.assertEqual(self.failed_receipt()['status'], 'failed'); self.cdk_exit = 0; self.parameter_drift = True
        with self.assertRaisesRegex(RuntimeError, 'stack parameters changed'): self.cli('deploy-api')
        self.assertEqual(self.failed_receipt()['status'], 'failed')

    def test_prompt_publication_requires_the_evaluated_content_and_private_originals_without_changing_other_modules(self):
        self.active_id = None; before = copy.deepcopy(self.pointer_rows()); receipt = self.cli('publish'); self.assertEqual(receipt['active'][0]['active_version_id'], release.CANDIDATE)
        self.assertEqual([r for r in self.pointer_rows() if r['module_id'] != release.MODULE], [r for r in before if r['module_id'] != release.MODULE]); self.assertEqual(len(self.published), 1)
        self.assertIn('Primary Codex AI implementer', self.published[0]); self.assertTrue(receipt['private_originals']['retrieved_hash_verified'])
        with self.assertRaisesRegex(RuntimeError, 'do not republish'): self.cli('publish')
        self.assertEqual(len(self.published), 1)

    def test_publication_mismatch_or_unrelated_pointer_change_stays_failed_with_original_receipts(self):
        self.active_id = None; self.publication_id = 'wrong-published-id'
        with self.assertRaisesRegex(RuntimeError, 'Published pointer differs'): self.cli('publish')
        self.assertEqual(self.failed_receipt()['status'], 'failed'); self.active_id = None; self.publication_id = release.CANDIDATE; self.pointer_drift = True
        with self.assertRaisesRegex(RuntimeError, 'Unrelated prompt pointers'): self.cli('publish')

    def test_readonly_production_verification_checks_capability_and_anonymous_denials_without_launching(self):
        receipt = self.cli('verify'); self.assertEqual(len(receipt['anonymous_denials']), 6); self.assertTrue(all(v['status'] == 401 for v in receipt['anonymous_denials'])); self.assertIn('coverage_limits', receipt)
        self.assertFalse(self.applied or self.published); self.assertEqual(receipt['new_model_calls'], 0)
        self.functions.pop()
        with self.assertRaisesRegex(RuntimeError, 'owner-only reuse RPC'): self.cli('verify')

    def test_frontend_release_and_status_and_archive_modes_require_the_compatible_published_prompt(self):
        self.assertEqual(self.cli('frontend-release')['job']['jobId'], 'synthetic-new-job'); self.assertEqual(self.cli('frontend-status')['jobs'][0]['jobId'], 'recorded-job')
        for mode in ['archive-release', 'archive-reuse']: self.assertTrue(self.cli(mode)['private_release_originals']['retrieved_hash_verified'])
        self.active_id = 'wrong-prompt'
        for mode in ['frontend-release', 'archive-release', 'archive-reuse']:
            with self.subTest(mode=mode), self.assertRaises(RuntimeError): self.cli(mode)

    def test_same_evidence_has_the_same_content_address_across_wall_clock_changes(self):
        out = self.root / 'stable-archive'; out.mkdir()
        with patch.object(release.zipfile.time, 'localtime', return_value=(2026, 10, 18, 0, 0, 0, 0, 0, 0)): first = release.archive_evidence(out)
        with patch.object(release.zipfile.time, 'localtime', return_value=(2026, 10, 18, 0, 0, 2, 0, 0, 0)): second = release.archive_evidence(out)
        self.assertEqual(first['path'], second['path']); self.assertEqual(first['sha256'], second['sha256'])

    def test_missing_final_publication_guard_and_changed_agent_zip_are_rejected(self):
        self.definition = 'Old publication function without the exact-unit guard'
        with self.assertRaisesRegex(RuntimeError, 'publication guard is missing'): release.security()
        out = self.root / 'changed-agent'; out.mkdir()
        with patch.object(self.guard.OPEN, 'open', return_value=io.BytesIO(self.agent_raw + b'Changed outside recorded ZIP hash')), self.assertRaisesRegex(RuntimeError, 'ZIP size/hash differs'): release.agent_archive(out)
        self.assertFalse((out / 'agent-original.zip').exists())

    def test_storage_upload_failures_and_changed_roundtrip_bytes_never_claim_verified_originals(self):
        out = self.root / 'failed-archive'; out.mkdir()
        with patch.object(self.guard.OPEN, 'open', side_effect=urllib.error.HTTPError('https://unit.example.test/storage', 503, 'Synthetic unavailable storage', {}, None)), self.assertRaisesRegex(RuntimeError, 'upload failed: HTTP 503'): release.archive_evidence(out)
        original_open = self.open
        def changed(request, **options):
            if not isinstance(request, str) and '/storage/v1/object/' in request.full_url and request.get_method() == 'GET' and request.get_header('Apikey') == 'synthetic-private-key': return io.BytesIO(b'Changed retrieved original')
            return original_open(request, **options)
        with patch.object(self.guard.OPEN, 'open', side_effect=changed), self.assertRaisesRegex(RuntimeError, 'original archive hash differs'): release.archive_evidence(out)

    def test_evidence_storage_budget_is_checked_before_credentials_or_upload(self):
        # Incompressible bytes exercise the actual ZIP transport budget rather
        # than changing the limit or fabricating a size in the coverage tool.
        self.write('docs/claim-design-production-release-evidence/incompressible.bin', os.urandom(32000001))
        out = self.root / 'oversize-archive'; out.mkdir(); before = len(self.cloud_commands)
        with self.assertRaisesRegex(RuntimeError, 'storage budget exceeded'): release.archive_evidence(out, release=True)
        self.assertEqual(len(self.cloud_commands), before); self.assertFalse(self.objects)

    def test_verification_requires_the_exact_active_publication_and_compatible_live_capability(self):
        self.active_exists = False
        with self.assertRaisesRegex(RuntimeError, 'not active/published'): self.cli('verify')
        self.active_exists = True; original_open = self.open
        def old_capability(request, **options):
            if request == release.API + '/capabilities': return io.BytesIO(b'{"preparation":{"claim_design_version":"older"}}')
            return original_open(request, **options)
        with patch.object(self.guard.OPEN, 'open', side_effect=old_capability), self.assertRaisesRegex(RuntimeError, 'capability differs'): self.cli('verify')
        self.assertFalse(self.published or self.applied)

    def test_script_help_exits_before_any_cloud_database_or_release_operation(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['claim-design-release.py', '--help']), contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as result:
            runpy.run_path(str(ROOT / 'bin/claim-design-release.py'), run_name='__main__')
        self.assertEqual(result.exception.code, 0); self.assertIn('frontend-status', output.getvalue()); self.assertEqual(self.cloud_commands, []); self.admin.query.assert_not_called()


if __name__ == '__main__': unittest.main()
