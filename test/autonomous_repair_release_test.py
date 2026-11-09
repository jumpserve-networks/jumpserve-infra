"""Exercise the actual repair release controller with isolated, synthetic evidence.

Cloud, database and model boundaries are adapters. Archives, canonical bytes,
hashes, policies, receipts and resume validation are processed by production code.
No historical private capsule, deployment, database write or provider is used.
"""
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import re
import shlex
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

from builder_continuation_release_test import archive, canonical, digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/autonomous-repair-release.py'
LEGACY_PIN = 'abfa36e381c69d2abc775de175e548090f4b1d01dd28da584d1bc2efc7d07330'


class AutonomousRepairRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='repair-release-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'infra'; self.back = self.root.parent / 'backend'; self.base = self.root / '.test-artifacts/autonomous-repair-release-v1'; self.source = self.base / '20261107T000000Z'; self.source.mkdir(parents=True)
        self.objects, self.evaluations, self.queries = {}, {}, []; self.corrupt_storage = False; self.corrupt_evaluation = False; self.present = False
        self.r = types.ModuleType('synthetic_repair_release'); self.r.sha = digest; self.r.stamp = lambda: '2026-11-07T00:00:00Z'; self.r.instance = Mock(return_value='i-087f1493809643115'); self.r.auth_maintenance_guard = Mock(); self.r.target = Mock(return_value={'synthetic_target': True}); self.r.ssm = Mock(return_value=dict(command_id='retained-command', instance_id='i-synthetic')); self.r.admin = types.SimpleNamespace(query=Mock(side_effect=self.query), literal=lambda value: "'" + value.replace("'", "''") + "'"); self.r.aws = Mock(side_effect=self.aws)
        self.r.prior = types.SimpleNamespace(PRIVATE=set(), security=Mock(return_value={'private_tables_verified': True}), functions=Mock(side_effect=lambda out, strict: copy.deepcopy(self.functions)), guard=types.SimpleNamespace(OPEN=types.SimpleNamespace(open=Mock(side_effect=self.open))))
        self.q = types.ModuleType('synthetic_continuation'); self.q.r = self.r; self.q.m = types.SimpleNamespace(storage=Mock(side_effect=self.storage)); self.q.save = self.save_path; self.q.selected = Mock(return_value=self.source); self.q.host = Mock(return_value='/synthetic/repair-host'); self.q.verify_worker = Mock(return_value=dict(command_id='retained-command', instance_id='i-synthetic')); self.q.dispatch = Mock(return_value={'dispatched': 'synthetic'})
        for name in ['status', 'collect_status', 'collect', 'verify_worker']: setattr(self.q, name, Mock(return_value={'status': 'synthetic', 'cases': ['private-detail']} if name != 'verify_worker' else dict(command_id='retained-command', instance_id='i-synthetic')))
        self.release = self.load(); self.release.ROOT = self.root; self.release.BACK = self.back; self.release.BASE = self.base; self.q.BASE = self.base
        original_path = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        self.model = types.ModuleType('autonomy_model'); self.model.OPENCLAW = False; self.model.MODEL = 'unpatched'; self.model.request = Mock(side_effect=lambda prompt, context: {'prompt': prompt, 'context': copy.deepcopy(context)}); self.model.request_fits = Mock(return_value=True)
        self.workflow = types.ModuleType('workflow'); self.workflow.canonical = canonical; self.workflow.digest = digest; self.repair = types.ModuleType('autonomous_repair'); self.repair.REPAIR_INSTRUCTION = 'Preserve original scientific criteria and diagnosis identity'
        self.enterContext(patch.dict(sys.modules, {'autonomy_model': self.model, 'autonomy_methods': types.ModuleType('autonomy_methods'), 'autonomous_repair': self.repair, 'experiment_builder': types.ModuleType('experiment_builder'), 'workflow': self.workflow}))
        self.git = self.enterContext(patch.object(self.release.subprocess, 'check_output', side_effect=lambda argv, **kwargs: '' if argv[1] == 'status' else 'a' * 40 + '\n')); self.sleep = self.enterContext(patch.object(self.release.time, 'sleep'))
        self.prompts = [dict(id=str(n) * 8 + '-0000-4000-8000-' + str(n) * 12, module_id=name, version=version, published_at='retained-published-time', system_prompt='Original synthetic system Ω', research_context='Original context', content_sha256=digest(name.encode())) for n, name, version in [(1, 'research-autonomy', 'research-autonomy-v10'), (2, 'research-experiment-builder', 'research-experiment-builder-v2')]]
        self.runtime_bytes = {'experiment_builder.py': b'# Original synthetic builder\n', 'repair_validation.py': b'# Original synthetic validation\n', 'policies/autonomous-repair-release-v1.json': b'{"old":true}\n'}
        for name, raw in self.runtime_bytes.items(): self.runtime(name, raw)
        self.manifest = dict(source_revision='a' * 40, files={name: digest(raw) for name, raw in self.runtime_bytes.items()}); self.write('research-workflow-runtime.json', canonical(self.manifest))
        self.protocol = {'version': 'synthetic-frozen-protocol', 'resources': {'maximum_actual_provider_calls': 12, 'maximum_elapsed_seconds': 600, 'maximum_qualification_commitments_cents': 1200}}
        self.write('docs/autonomous-repair-live-protocol-v1.json', canonical(self.protocol))
        for version in ['v2', 'v3', 'v4', 'v5']: self.write('docs/autonomous-repair-live-amendment-' + version + '.json', canonical({'version': version}))
        self.write('.test-artifacts/assessment-recovery-release-v1/20261028T224207510236Z/frozen.json', canonical({'live_cases': [{'id': 'old-' + str(i), 'context': {'shared_acquisitions': ['not-in-current-catalog'], 'claim': {'description': 'Synthetic original ' + str(i)}}} for i in range(2)]}))
        for name in ['builder_continuation_qualification_host.py', 'autonomous_repair_qualification_host.py']: self.write('bin/' + name, b'# Synthetic frozen host source, never executed\n')
        self.runtime('tests/prepare_builder_vendor.py', b'# Synthetic original vendoring entry point\n')
        self.migration = b'-- Synthetic repair migration; never executed by a SQL engine\n'; self.write('database/202610280004_autonomous_repair.sql', self.migration)
        self.pointer = dict(path='qualification/synthetic-original.zip', sha256=digest(b'Original evidence bytes')); self.objects[self.pointer['path']] = b'Original evidence bytes'
        self.frozen = dict(protocol=self.protocol, source_revision=self.manifest['source_revision'], prompts=self.prompts, runtime_manifest=self.manifest, native_context={'incident_sha256': 'f' * 64}, original_program='Original frozen source')
        self.save('frozen.json', self.frozen); self.save('host-status.json', {'evidence.json': self.pointer}); self.save('evaluations-recorded.json', {'status': 'passed', 'archive': self.pointer})
        self.live = dict(status='awaiting-substantive-review', actual_calls=6, reserved_cents=600, cases=[{'structural_checks_passed': True} for _ in range(3)]); self.save('live.json', self.live)
        self.review = dict(passed=True, reviewer={'type': 'AI', 'independent': False}, source_revision=self.manifest['source_revision']); self.save('reviewed.json', self.review)
        self.fence = dict(status='passed', real_unconfirmed_outcome_present=True, provider_calls=0); self.save('fences-verified.json', self.fence)
        self.security = [dict(relname=name, relrowsecurity=True, anon_read=False, browser_write=False) for name in ['research_autonomy_repair_events', 'research_autonomy_repairs']]; self.rpc = [dict(anon=False, browser=False)]
        self.invocations = [dict(Status='Success', StandardOutputContent=canonical(self.fence).decode())]
        self.functions = [dict(function=name, handler=handler, timeout=420, source_hashes=self.manifest['files']) for name, handler in [('synthetic-api', 'api.handler'), ('synthetic-autonomy', 'autonomy.handler'), ('synthetic-other', 'worker.handler')]]
        self.active = False; self.env_changes = {}; self.health = dict(status='ready', configuration={}, updated_at='retained-time'); self.poll_state = None
        self.resources = [dict(ResourceType='AWS::Events::Rule', LogicalResourceId='ResearchWorkflowAutonomyPollSynthetic', PhysicalResourceId='synthetic-rule'), dict(ResourceType='AWS::Other', LogicalResourceId='Unrelated', PhysicalResourceId='ignored')]
        self.capabilities = dict(autonomy=dict(enabled=False, defaults=dict(attempts_per_claim=None, maximum_spend_usd=100), runtime={'runtime': 'openclaw-production-v1'}))
        self.front = 'a' * 40; self.jobs = [dict(commitId='other', status='SUCCEED', jobId='older'), dict(commitId=self.front, status='SUCCEED', jobId='synthetic-amplify-job')]
        self.queue = dict(study={'id': self.release.STUDY}, autonomy={'workflows': [dict(study_id=self.release.STUDY, max_spend_cents=10000, max_attempts=None, created_at='retained-created', deadline_at='retained-deadline', committed_cents=800)], 'tasks': [dict(id='original-task', claim_id='original-claim', stage='building', status='pending', repair_progress=None), dict(id='intake-task', claim_id=None)]}, coverage={'jobs': [{'id': 'original-job'}]})

    def load(self):
        original = importlib.util.spec_from_file_location; continuation = self.q
        class Loader:
            def create_module(self, spec): return continuation
            def exec_module(self, module): return None
        def specification(label, location, *args, **kwargs):
            if Path(location) == ROOT / 'bin/builder-continuation-release.py': return importlib.machinery.ModuleSpec(label, Loader())
            return original(label, location, *args, **kwargs)
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=specification):
            spec = original('autonomous_repair_release_unit', SOURCE); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def runtime(self, name, raw):
        path = self.back / 'research_workflow' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def save_path(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(value)); path.chmod(0o600)
    def save(self, name, value, directory=None):
        path = (directory or self.source) / name; self.save_path(path, value); return path
    def storage(self, path, raw=None):
        if raw is not None:
            self.assertTrue(path not in self.objects or self.objects[path] == raw); self.objects[path] = raw
        return self.objects[path] + (b'changed' if self.corrupt_storage and raw is None else b'')
    def query(self, sql, **options):
        self.queries.append((sql, options))
        if sql.startswith('select v.id,'): return copy.deepcopy(self.prompts)
        if sql.encode() == self.migration: self.assertEqual(options, {'read_only': False}); return []
        if sql.startswith('select to_regclass'): return [{'present': self.present}]
        if sql.startswith('select c.relname,'): return copy.deepcopy(self.security)
        if sql.startswith('select has_function_privilege'): return copy.deepcopy(self.rpc)
        if sql.startswith('select status,configuration,'): return [copy.deepcopy(self.health)]
        if sql.startswith('insert into agent_prompt_evaluations('):
            self.assertEqual(options, {'read_only': False}); values = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]; prompt, outcome, raw, sha, pointer, reviewer = values
            self.assertEqual(digest(raw.encode()), sha); self.assertIn(outcome, ['passed', 'failed-or-paused']); self.assertIn('nonindependent', reviewer); self.assertEqual(json.loads(pointer)['sha256'], digest(self.objects[json.loads(pointer)['path']]))
            self.evaluations[(prompt, sha)] = raw; return []
        if sql.startswith('select report_raw from agent_prompt_evaluations'):
            values = re.findall(r"'((?:''|[^'])*)'", sql); return [{'report_raw': self.evaluations[tuple(values)] + ('changed' if self.corrupt_evaluation else '')}]
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        if (service, operation) == ('ssm', 'get-command-invocation'):
            self.assertEqual(args, ('--command-id', 'retained-command', '--instance-id', 'i-synthetic')); return copy.deepcopy(self.invocations.pop(0) if len(self.invocations) > 1 else self.invocations[0])
        if (service, operation) == ('lambda', 'get-function-configuration'):
            self.assertEqual(args[0], '--function-name'); handler = next(f['handler'] for f in self.functions if f['function'] == args[1]); env = dict(RESEARCH_AUTONOMY_ENABLED='true' if handler == 'autonomy.handler' else str(self.active).lower(), RESEARCH_BUILDER_ENABLED='true', RESEARCH_AI_RUNTIME='openclaw-production-v1', RESEARCH_AUTONOMY_REPAIR_ENABLED='true'); env.update(self.env_changes); return {'Environment': {'Variables': env}}
        if (service, operation) == ('cloudformation', 'list-stack-resources'): self.assertEqual(args, ('--stack-name', 'JumpServeBenchmarkStack')); return {'StackResourceSummaries': copy.deepcopy(self.resources)}
        if (service, operation) == ('events', 'describe-rule'): self.assertEqual(args, ('--name', 'synthetic-rule')); return {'State': self.poll_state or ('ENABLED' if self.active else 'DISABLED')}
        if (service, operation) == ('amplify', 'list-jobs'): self.assertEqual(args, ('--app-id', 'd24jvguj7brnkj', '--branch-name', 'main', '--max-results', '10')); return {'jobSummaries': copy.deepcopy(self.jobs)}
        raise AssertionError('Unexpected cloud operation: ' + str((service, operation, args)))
    def open(self, url, timeout):
        self.assertEqual(timeout, 30)
        if url.endswith('/research/capabilities'): return io.BytesIO(canonical(self.capabilities))
        self.assertTrue(url.endswith('/research/studies/' + self.release.STUDY + '/queue?public=1&diagnostics=1')); return io.BytesIO(canonical(self.queue))
    def freeze(self, previous=None, validation_only=False):
        directory = self.base / ('frozen-' + str(len(list(self.base.iterdir())))); directory.mkdir(); result = self.release.freeze(directory, previous, validation_only); return directory, json.loads((directory / 'frozen.json').read_bytes()), result
    def previous(self, changed=None):
        previous = self.base / 'previous'; previous.mkdir(); frozen = copy.deepcopy(self.frozen)
        if changed: frozen['runtime_manifest']['files'][changed] = 'e' * 64
        checkpoint_raw = archive({'project/experiment.py': b'# Synthetic retained corrected file\n', 'previous-failure.log': b'Original unaltered failure\n'}); checkpoint = dict(sha256=digest(checkpoint_raw))
        live = copy.deepcopy(self.live); live.update(status='failed-or-paused', actual_calls=8, inherited_actual_calls=2, reserved_cents=800, inherited_reserved_cents=200); live['cases'][2]['receipts'] = [dict(status='complete', checkpoint=checkpoint)]
        self.save('frozen.json', frozen, previous); self.save('live.json', live, previous); self.save('host-status.json', {'evidence.json': self.pointer}, previous); (previous / 'evidence.zip').write_bytes(archive({'retained/checkpoint.zip': checkpoint_raw, 'unrelated.bin': b'not-a-checkpoint'})); return previous

    def test_freeze_binds_original_sources_prompts_contexts_and_private_readback(self):
        source, frozen, result = self.freeze(); self.assertEqual(result['maximum_provider_calls'], 12); self.assertEqual(result['source_revision'], 'a' * 40); self.assertEqual(frozen['assessment'], self.release.STUDY); self.assertTrue(all(case['request']['context']['shared_acquisitions'] == [] for case in frozen['planner_cases'])); self.assertIn('Do not request it or invent', frozen['planner_cases'][0]['request']['context']['previous_feedback']); self.assertFalse(self.model.OPENCLAW); self.assertEqual(self.model.MODEL, 'unpatched'); self.assertEqual(self.model.request.call_count, 2)
        self.assertIn('json.loads(spec_path)', frozen['original_program']); self.assertIn('preserve null and zero', frozen['native_context']['claim']['description']); self.assertEqual(len(frozen['native_context']['repair_packet']['incident_sha256']), 64); self.assertEqual((self.base / 'selected.txt').read_text().strip(), source.name)
        raw = (source / 'candidate.zip').read_bytes(); pointer = json.loads((source / 'candidate.json').read_bytes()); self.assertEqual(self.objects[pointer['path']], raw); self.assertEqual(pointer['sha256'], digest(raw)); self.assertEqual((source / 'frozen.json').stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for row in json.loads(z.read('artifact-manifest.json')): self.assertEqual(digest(z.read(row['path'])), row['sha256']); self.assertEqual(len(z.read(row['path'])), row['bytes'])
            for name, original in self.runtime_bytes.items(): self.assertEqual(z.read('research_workflow/' + name), original)

    def test_freeze_rejects_dirty_revision_target_prompt_or_oversized_request_before_upload(self):
        for failure in ['dirty', 'revision', 'instance', 'prompt-version', 'unpublished', 'request-size']:
            with self.subTest(failure=failure), contextlib.ExitStack() as stack:
                if failure == 'dirty': stack.enter_context(patch.object(self.release.subprocess, 'check_output', return_value='dirty'))
                elif failure == 'revision': stack.enter_context(patch.object(self.release.subprocess, 'check_output', side_effect=['', 'b' * 40]))
                elif failure == 'instance': stack.enter_context(patch.object(self.r, 'instance', return_value='i-wrong'))
                elif failure.startswith('prompt') or failure == 'unpublished':
                    prompts = copy.deepcopy(self.prompts); prompts[0]['version' if failure == 'prompt-version' else 'published_at'] = 'wrong' if failure == 'prompt-version' else None; stack.enter_context(patch.object(self.r.admin, 'query', return_value=prompts))
                else: stack.enter_context(patch.object(self.model, 'request_fits', return_value=False))
                self.q.m.storage.reset_mock()
                with self.assertRaises(AssertionError): self.freeze()
                self.q.m.storage.assert_not_called()

    def test_freeze_requires_identical_candidate_storage_bytes(self):
        self.corrupt_storage = True
        with self.assertRaises(AssertionError): self.freeze()
        self.assertFalse((self.base / 'selected.txt').exists())

    def test_followups_preserve_checkpoint_and_cumulative_calls_with_declared_source_scope(self):
        for changed, revision, calls in [(None, 'v3', 6), ('experiment_builder.py', 'v4', 12), ('repair_validation.py', 'v4', 12)]:
            with self.subTest(changed=changed):
                previous = self.previous(changed); directory, frozen, result = self.freeze(previous); self.assertEqual(result['maximum_provider_calls'], calls); self.assertEqual(frozen['qualification_amendment']['version'], revision); self.assertEqual(frozen['inherited']['actual_calls'], 10); self.assertEqual(frozen['inherited']['reserved_cents'], 1000); self.assertEqual(frozen['inherited']['changed_files'], [changed] if changed else []); self.assertEqual(frozen['native_context']['incident_sha256'], 'f' * 64); self.assertEqual(frozen['original_program'], 'Original frozen source'); self.assertEqual(frozen['protocol']['resources']['maximum_qualification_commitments_cents'], calls * 100)
                with zipfile.ZipFile(directory / 'candidate.zip') as z: self.assertEqual(digest(z.read('inherited-checkpoint.zip')), frozen['inherited']['checkpoint']['sha256'])
                for p in previous.iterdir(): p.unlink()
                previous.rmdir()

    def test_validation_only_followup_authorizes_no_provider_calls_and_requires_validation_change(self):
        previous = self.previous('repair_validation.py'); _directory, frozen, result = self.freeze(previous, True); self.assertEqual(result['maximum_provider_calls'], 0); self.assertTrue(frozen['validation_only']); self.assertEqual(frozen['qualification_amendment']['version'], 'v5'); self.assertIn('No model call is authorized', frozen['native_context']['builder_feedback']); self.assertEqual(frozen['inherited']['native_receipts'][0]['status'], 'complete')
        original = json.loads((previous / 'frozen.json').read_bytes()); original['runtime_manifest']['files'] = self.manifest['files']; self.save('frozen.json', original, previous)
        with self.assertRaises(AssertionError): self.freeze(previous, True)

    def test_followup_rejects_unsettled_calls_changed_prompts_changed_scope_and_checkpoint_mismatch(self):
        previous = self.previous(); original_live = json.loads((previous / 'live.json').read_bytes()); original_frozen = json.loads((previous / 'frozen.json').read_bytes())
        for failure in ['status', 'calls', 'case-count', 'planner', 'receipt', 'prompt', 'scope', 'checkpoint']:
            with self.subTest(failure=failure):
                live, frozen = copy.deepcopy(original_live), copy.deepcopy(original_frozen)
                if failure == 'status': live['status'] = 'complete'
                elif failure == 'calls': live['actual_calls'] = 9
                elif failure == 'case-count': live['cases'].pop()
                elif failure == 'planner': live['cases'][0]['structural_checks_passed'] = False
                elif failure == 'receipt': live['cases'][2]['receipts'][0]['status'] = 'unknown'
                elif failure == 'prompt': frozen['prompts'][0]['content_sha256'] = 'wrong'
                elif failure == 'scope': frozen['runtime_manifest']['files']['policies/autonomous-repair-release-v1.json'] = 'wrong'
                else: live['cases'][2]['receipts'][0]['checkpoint']['sha256'] = 'wrong'
                self.save('live.json', live, previous); self.save('frozen.json', frozen, previous)
                with self.assertRaises(AssertionError): self.freeze(previous)

    def test_record_requires_original_archive_and_exact_evaluation_readback(self):
        result = self.release.record(self.source); self.assertEqual(result['status'], 'passed'); self.assertEqual(result['prompt_ids'], [p['id'] for p in self.prompts]); report = json.loads(next(iter(self.evaluations.values()))); self.assertFalse(report['scientific_completion']); self.assertFalse(report['prompt_publications_changed']); self.assertEqual(report['live']['actual_calls'], 6)
        self.corrupt_storage = True
        with self.assertRaises(AssertionError): self.release.record(self.source)
        self.corrupt_storage = False; self.corrupt_evaluation = True
        with self.assertRaises(AssertionError): self.release.record(self.source)

    def test_no_review_or_no_live_call_is_honestly_recorded_as_unqualified(self):
        (self.source / 'live.json').unlink(); (self.source / 'reviewed.json').unlink(); (self.source / 'fences-verified.json').unlink(); result = self.release.record(self.source); self.assertEqual(result['status'], 'failed-or-paused'); value = json.loads(self.evaluations[(self.prompts[0]['id'], result['report_sha256'])]); self.assertEqual(value['live']['actual_calls'], 0); self.assertEqual(value['live']['status'], 'failed-before-provider'); self.assertIsNone(value['review']); self.assertIsNone(value['uncertainty_fences'])

    def test_record_cannot_pass_without_ai_source_bound_review_complete_controls_and_real_uncertainty(self):
        for field, value in [('passed', False), ('reviewer', {'type': 'human', 'independent': False}), ('reviewer', {'type': 'AI', 'independent': True}), ('source_revision', 'wrong')]:
            with self.subTest(field=field, value=value):
                review = dict(self.review, **{field: value}); self.save('reviewed.json', review); self.assertEqual(self.release.record(self.source)['status'], 'failed-or-paused')
        self.save('reviewed.json', self.review)
        for failure in ['live-status', 'case-count', 'structural', 'fence-status', 'fence-unknown', 'fence-provider']:
            with self.subTest(failure=failure):
                live, fence = copy.deepcopy(self.live), copy.deepcopy(self.fence)
                if failure == 'live-status': live['status'] = 'running'
                elif failure == 'case-count': live['cases'].pop()
                elif failure == 'structural': live['cases'][2]['structural_checks_passed'] = False
                elif failure == 'fence-status': fence['status'] = 'failed'
                elif failure == 'fence-unknown': fence['real_unconfirmed_outcome_present'] = False
                else: fence['provider_calls'] = 1
                self.save('live.json', live); self.save('fences-verified.json', fence); self.assertEqual(self.release.record(self.source)['status'], 'failed-or-paused')

    def test_approval_hash_excludes_only_approval_policy_and_rejects_drift(self):
        value = self.release.approve(self.source); expected = digest(canonical({name: sha for name, sha in self.manifest['files'].items() if name != 'policies/autonomous-repair-release-v1.json'})); self.assertEqual(value['qualified_files_sha256'], expected); self.assertEqual(value['evidence_sha256'], self.pointer['sha256']); self.assertTrue(value['approved_for_lab_recovery']); self.assertEqual(json.loads((self.back / 'research_workflow/policies/autonomous-repair-release-v1.json').read_bytes()), value)
        with self.assertRaises(AssertionError): self.release.approve(self.source)
        self.save('evaluations-recorded.json', {'status': 'failed-or-paused'})
        with self.assertRaises(AssertionError): self.release.approve(self.source)

    def test_migration_retains_exact_original_and_never_reexecutes_present_schema(self):
        for present in [False, True]:
            with self.subTest(present=present):
                self.present = present; self.queries.clear(); result = self.release.migrate(self.source); self.assertEqual(result['present_before'], present); self.assertEqual(result['sha256'], digest(self.migration)); self.assertEqual(sum(sql.encode() == self.migration for sql, _ in self.queries), int(not present)); self.assertTrue(result['security']); self.assertEqual(self.objects['release-migrations/autonomous-repair-v1/' + digest(self.migration) + '-202610280004_autonomous_repair.sql'], self.migration)

    def test_migration_fails_closed_on_storage_security_or_browser_rpc_regressions(self):
        original = copy.deepcopy(self.security)
        for failure in ['storage', 'missing-table', 'rls', 'anon-read', 'browser-write', 'rpc']:
            with self.subTest(failure=failure):
                self.corrupt_storage = failure == 'storage'; self.security = copy.deepcopy(original); self.rpc = [dict(anon=False, browser=False)]
                if failure == 'missing-table': self.security.pop()
                elif failure == 'rls': self.security[0]['relrowsecurity'] = False
                elif failure == 'anon-read': self.security[0]['anon_read'] = True
                elif failure == 'browser-write': self.security[0]['browser_write'] = True
                elif failure == 'rpc': self.rpc[0]['browser'] = True
                with self.assertRaises(AssertionError): self.release.migrate(self.source)

    def test_uncertainty_check_is_a_scoped_no_provider_command_with_bounded_polling(self):
        self.invocations.insert(0, {'Status': 'InProgress'}); result = self.release.fences(self.source); self.assertEqual(result['provider_calls'], 0); self.assertEqual(self.sleep.call_count, 2); commands = self.r.ssm.call_args.args[0]; self.assertEqual(commands[:4], ['set -eu', 'set -a', '. /etc/jumpserve-openclaw.env', 'set +a']); code = shlex.split(commands[-1])[-1]; compile(code, '<synthetic-fence-command>', 'exec'); self.assertIn("side_effect=AssertionError('No provider invocation", code); self.assertIn('limit=20', code); self.assertIn("'eq.unknown'", code); self.assertIn('provider.call_count==0', code); self.assertIn('/synthetic/repair-host', code); self.assertTrue((self.source / 'fences-ssm.json').exists())

    def test_uncertainty_polling_rejects_timeout_failure_nonpassing_or_provider_invocation(self):
        for invocation in [dict(Status='Pending'), dict(Status='Failed'), dict(Status='Success', StandardOutputContent='{"status":"failed","provider_calls":0}'), dict(Status='Success', StandardOutputContent='{"status":"passed","provider_calls":1}')]:
            with self.subTest(invocation=invocation):
                self.invocations = [invocation]; self.sleep.reset_mock()
                with self.assertRaises(AssertionError): self.release.fences(self.source)
                self.assertEqual(self.sleep.call_count, 12 if invocation['Status'] == 'Pending' else 1)

    def verify(self, active=False):
        self.active = active; self.capabilities['autonomy']['enabled'] = active; self.save('migration-applied.json', {'status': 'passed'}); out = self.base / ('verification-' + str(len(list(self.base.iterdir())))); out.mkdir(); return self.release.verify(self.source, out, active)

    def test_held_and_active_verification_check_installed_sources_flags_private_data_and_worker(self):
        for active in [False, True]:
            with self.subTest(active=active):
                self.invocations = [dict(Status='Delayed'), dict(Status='Success', StandardOutputContent='Original worker verification output')]; result = self.verify(active); self.assertEqual(result['admission'], active); receipt = json.loads((self.source / ('active-verified.json' if active else 'held-verified.json')).read_bytes()); self.assertEqual(receipt['worker_stdout_sha256'], digest(b'Original worker verification output')); self.assertFalse(receipt['auth_upload_chat_reverified']); self.assertEqual(len(receipt['flags']), 2); self.assertEqual(receipt['polling'][0]['state'], 'ENABLED' if active else 'DISABLED'); self.assertIn('research_model_dispatches', self.r.prior.PRIVATE); self.assertEqual(receipt['runtime_files'], 3)

    def test_verification_rejects_incomplete_source_timeout_environment_health_capability_and_poll_checks(self):
        functions, capabilities = copy.deepcopy(self.functions), copy.deepcopy(self.capabilities)
        for failure in ['function-count', 'source-count', 'timeout', 'builder', 'runtime', 'repair', 'health', 'attempts', 'spend', 'cap-runtime', 'poll-state', 'poll-count', 'worker-command', 'instance']:
            with self.subTest(failure=failure):
                self.functions = copy.deepcopy(functions); self.capabilities = copy.deepcopy(capabilities); self.env_changes = {}; self.health['status'] = 'ready'; self.poll_state = None; self.resources = self.resources[:2]; self.invocations = [dict(Status='Success', StandardOutputContent='ok')]; self.r.instance.return_value = 'i-087f1493809643115'
                if failure == 'function-count': self.functions.pop()
                elif failure == 'source-count': self.functions[0]['source_hashes'] = {}
                elif failure == 'timeout': self.functions[1]['timeout'] = 60
                elif failure in ['builder', 'runtime', 'repair']: self.env_changes[{'builder': 'RESEARCH_BUILDER_ENABLED', 'runtime': 'RESEARCH_AI_RUNTIME', 'repair': 'RESEARCH_AUTONOMY_REPAIR_ENABLED'}[failure]] = 'wrong'
                elif failure == 'health': self.health['status'] = 'not-ready'
                elif failure == 'attempts': self.capabilities['autonomy']['defaults']['attempts_per_claim'] = 12
                elif failure == 'spend': self.capabilities['autonomy']['defaults']['maximum_spend_usd'] = 200
                elif failure == 'cap-runtime': self.capabilities['autonomy']['runtime']['runtime'] = 'wrong'
                elif failure == 'poll-state': self.poll_state = 'ENABLED'
                elif failure == 'poll-count': self.resources.append(copy.deepcopy(self.resources[0]))
                elif failure == 'worker-command': self.invocations = [dict(Status='Pending')]
                else: self.r.instance.return_value = 'i-wrong'
                with self.assertRaises(AssertionError): self.verify()

    def release_inputs(self):
        self.assertEqual(self.release.LEGACY_EVIDENCE_SHA256, LEGACY_PIN); legacy = archive({'original-synthetic-evidence.json': canonical({'missing': None, 'zero': 0})}); self.enterContext(patch.object(self.release, 'LEGACY_EVIDENCE_SHA256', digest(legacy))); self.write('.test-artifacts/autonomous-repair-local/20261029T010001267011Z/evidence.zip', legacy)
        self.save('active-verified.json', dict(status='passed', admission=True, source_revision=self.manifest['source_revision'])); before = copy.deepcopy(self.queue); before['autonomy']['workflows'][0]['committed_cents'] = 700; self.save('before-activation-queue.json', before)
        self.write('.test-artifacts/autonomous-repair-production-browser/20261107/report.json', canonical(dict(passed=True, conditional_gaps=['Original explicitly unverified route']))); self.write('.test-artifacts/autonomous-repair-production-browser/20261107/capture.png', b'Synthetic image bytes'); self.write('.test-artifacts/autonomous-repair-production-browser/20261107/ignored.txt', b'Not an allowed capture member')
        for name in ['autonomous-repair-release.py', 'verify-autonomous-repair-production.mjs']: self.write('bin/' + name, b'# Synthetic original producer bytes\n')
        self.write('docs/autonomous-repair-qualification-v1.json', canonical(dict(status='passed', independent=False, scientific_completion=False))); self.write('docs/autonomous-repair-release.md', b'Synthetic release method\n'); self.write(str((self.source / 'JumpServeBenchmarkStack.synthetic.zip').relative_to(self.root)), archive({'lambda.py': b'# Original synthetic lambda\n'})); self.save('worker-ssm.json', {'Status': 'Success'})
        for stamp, mode in [('20261028T000000Z', 'deploy'), ('20261107T000000Z', 'unrelated'), ('20261107T000001Z', 'deploy')]:
            prefix = '.test-artifacts/openclaw-release/' + stamp + '/'; self.write(prefix + 'receipt.json', canonical({'mode': mode})); self.write(prefix + 'cdk.log', b'Synthetic retained scoped diff\n'); self.write(prefix + 'ignored-private.json', b'Not on release allowlist'); (self.root / prefix / 'directory').mkdir()
        out = self.base / 'recorded-release'; out.mkdir(); return out

    def test_release_evidence_preserves_gaps_original_authorization_sources_and_archive_hashes(self):
        out = self.release_inputs(); result = self.release.record_release(self.source, out); self.assertEqual(result['status'], 'deployed-with-conditional-verification-gaps'); self.assertEqual(result['amplify_job'], 'synthetic-amplify-job'); pointer = result['evidence']; self.assertFalse(pointer['public']); raw = (out / 'release-evidence.zip').read_bytes(); self.assertEqual(self.objects[pointer['path']], raw); self.assertEqual(pointer['sha256'], digest(raw)); report = json.loads((self.root / 'docs/autonomous-repair-production-v1-status.json').read_bytes()); self.assertEqual(report['conditional_gaps'], ['Original explicitly unverified route']); self.assertIsNone(report['measured_charges_usd']); self.assertEqual(report['original_assessment_authorization']['commitments_before'], 700); self.assertEqual(report['original_assessment_authorization']['commitments_observed'], 800); self.assertEqual(len(report['recorded_assessment_snapshot']['claim_states']), 1)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist(); self.assertTrue(any(name.endswith('capture.png') for name in names)); self.assertFalse(any('ignored' in name for name in names)); self.assertFalse(any('20261028T000000Z' in name for name in names)); self.assertFalse(any('/20261107T000000Z/receipt.json' in name for name in names)); self.assertTrue(any('/20261107T000001Z/cdk.log' in name for name in names))
            for row in json.loads(z.read('artifact-manifest.json')): self.assertEqual(digest(z.read(row['path'])), row['sha256']); self.assertEqual(len(z.read(row['path'])), row['bytes'])
            for name, original in self.runtime_bytes.items(): self.assertEqual(z.read('runtime/research_workflow/' + name), original)
        self.assertEqual(len(self.evaluations), 2); evaluation = json.loads(next(iter(self.evaluations.values()))); self.assertFalse(evaluation['reviewer']['independent']); self.assertFalse(evaluation['reviewer']['human'])

    def test_release_cannot_change_original_limits_deadline_identity_or_reconcile_cost_by_reset(self):
        out = self.release_inputs(); original = copy.deepcopy(self.queue)
        for failure in ['study', 'limit', 'attempts', 'created', 'deadline', 'commitment-reset', 'over-limit', 'task', 'claim']:
            with self.subTest(failure=failure):
                self.queue = copy.deepcopy(original); workflow = self.queue['autonomy']['workflows'][0]
                if failure == 'study': self.queue['study']['id'] = 'wrong'
                elif failure in ['limit', 'attempts', 'created', 'deadline']: workflow[{'limit': 'max_spend_cents', 'attempts': 'max_attempts', 'created': 'created_at', 'deadline': 'deadline_at'}[failure]] = 'wrong'
                elif failure == 'commitment-reset': workflow['committed_cents'] = 0
                elif failure == 'over-limit': workflow['committed_cents'] = 10001
                else: self.queue['autonomy']['tasks'][0]['id' if failure == 'task' else 'claim_id'] = 'wrong'
                with self.assertRaises(AssertionError): self.release.record_release(self.source, out)
                self.assertFalse((out / 'release-evidence.zip').exists())

    def test_release_rejects_stale_sources_failed_browser_missing_amplify_success_and_corrupt_readbacks(self):
        out = self.release_inputs(); browser = self.root / '.test-artifacts/autonomous-repair-production-browser/20261107/report.json'
        for failure in ['admission', 'revision', 'browser', 'amplify', 'runtime', 'legacy', 'storage', 'evaluation']:
            with self.subTest(failure=failure):
                self.save('active-verified.json', dict(status='passed', admission=failure != 'admission', source_revision='wrong' if failure == 'revision' else self.manifest['source_revision'])); browser.write_bytes(canonical(dict(passed=failure != 'browser', conditional_gaps=[]))); self.jobs[-1]['status'] = 'FAILED' if failure == 'amplify' else 'SUCCEED'; self.runtime('experiment_builder.py', b'changed' if failure == 'runtime' else self.runtime_bytes['experiment_builder.py']); self.corrupt_storage = failure == 'storage'; self.corrupt_evaluation = failure == 'evaluation'
                with patch.object(self.release, 'LEGACY_EVIDENCE_SHA256', 'wrong' if failure == 'legacy' else self.release.LEGACY_EVIDENCE_SHA256), self.assertRaises((AssertionError, StopIteration)): self.release.record_release(self.source, out)

    def test_cli_dispatches_every_fixed_mode_and_records_success_or_failure_locally(self):
        routes = {'freeze': ('freeze', ()), 'freeze-followup': ('freeze', (self.source,)), 'freeze-validation': ('freeze', (self.source, True)), 'verify-fences': ('fences', (self.source,)), 'verify-held': ('verify', None), 'verify-active': ('verify', None), 'record-release': ('record_release', None), 'record-review': ('record', (self.source,)), 'approve': ('approve', (self.source,)), 'migrate': ('migrate', (self.source,))}
        for mode in [*routes, 'status', 'collect-status', 'collect', 'verify-worker', 'prepare', 'live', 'evidence']:
            with self.subTest(mode=mode), contextlib.ExitStack() as stack:
                operation = stack.enter_context(patch.object(self.release, routes[mode][0], return_value={'synthetic': mode})) if mode in routes else None
                output = io.StringIO(); stack.enter_context(patch.object(sys, 'argv', [str(SOURCE), mode])); stack.enter_context(contextlib.redirect_stdout(output)); self.release.main(); receipt = json.loads(output.getvalue()); self.assertEqual(receipt['status'], 'complete'); saved = json.loads((Path(receipt['directory']) / 'receipt.json').read_bytes()); self.assertEqual(saved['mode'], mode)
                if operation:
                    out = Path(receipt['directory'])
                    expected = (out, *routes[mode][1]) if mode.startswith('freeze') else (self.source, out, mode == 'verify-active') if mode in ['verify-held', 'verify-active'] else (self.source, out) if mode == 'record-release' else routes[mode][1]
                    operation.assert_called_once_with(*expected)
                elif mode in ['prepare', 'live', 'evidence']: self.q.dispatch.assert_called_with(self.source, mode)
                else: self.assertNotIn('cases', receipt['result'])
        with patch.object(sys, 'argv', [str(SOURCE), 'approve']), patch.object(self.release, 'approve', side_effect=ValueError('Original failure')), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(ValueError, 'Original failure'): self.release.main()
            receipt = json.loads(output.getvalue()); self.assertEqual(receipt['status'], 'failed'); self.assertEqual(receipt['reason'], 'Original failure')

    def test_unknown_cli_mode_is_rejected_before_target_or_output_creation(self):
        before = set(self.base.iterdir())
        with patch.object(sys, 'argv', [str(SOURCE), 'untrusted-command']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error: self.release.main()
        self.assertEqual(error.exception.code, 2); self.assertEqual(set(self.base.iterdir()), before); self.r.target.assert_not_called(); self.r.aws.assert_not_called()


if __name__ == '__main__': unittest.main()
