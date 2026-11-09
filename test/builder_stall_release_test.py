"""Builder-stall release controls with synthetic services and real evidence ZIPs.

No external API, model, SQL engine, deployment or host process is contacted.
The tests exercise the release controller, immutable bytes and read-back checks.
"""
import base64
import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
import zipfile

from builder_continuation_release_test import archive, canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('builder_stall_release_unit', ROOT / 'bin/builder-stall-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


class Response(io.BytesIO):
    def __init__(self, raw, status=200): super().__init__(raw); self.status = status


class BuilderStallRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='builder-stall-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'infra'; self.back = self.root.parent / 'backend'
        self.base = self.root / '.test-artifacts/builder-stall-release-v1'; self.source = self.base / '20261107T000000Z'; self.source.mkdir(parents=True)
        for name, value in [('ROOT', self.root), ('BACK', self.back), ('BASE', self.base)]: self.enterContext(patch.object(release, name, value))
        self.enterContext(patch.object(release.q, 'BASE', self.base))
        self.r = MagicMock(); self.r.sha.side_effect = digest; self.r.stamp.return_value = '2026-11-07T00:00:00+00:00'; self.r.instance.return_value = 'i-087f1493809643115'
        self.r.target.return_value = {'synthetic': True}; self.r.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"
        self.enterContext(patch.object(release, 'r', self.r)); self.m = MagicMock(); self.enterContext(patch.object(release, 'm', self.m))
        self.objects, self.reports, self.sql, self.artifacts, self.saved_artifacts = {}, {}, [], {}, {}
        self.m.storage.side_effect = self.storage; self.r.admin.query.side_effect = self.query; self.r.aws.side_effect = self.aws
        self.names = ['bootstrap', '_execute', 'validate_calls', 'config', 'work_packet', 'execution_contract']
        self.program = ''.join('def ' + name + '():\n    return None\n\n' for name in self.names).encode()
        self.manifest = dict(version=3, source_revision='a' * 40, files={'experiment_builder.py': digest(self.program)})
        self.write('research-workflow-runtime.json', canonical(self.manifest))
        self.runtime('experiment_builder.py', self.program); self.runtime('experiment-builder.Dockerfile', b'# Synthetic Docker recipe, never built\n')
        self.runtime('tests/test_fixture.py', b'# Synthetic unit source, never executed\n'); self.runtime('tests/fixture.json', b'{"zero":0,"missing":null}'); self.runtime('tests/fixture.mjs', b'// Synthetic test source\n'); self.runtime('tests/ignore.txt', b'Not runtime source'); self.runtime('tests/__pycache__/ignored.py', b'# Generated cache, never bundle\n')
        self.runtime('policies/netem-iperf-costs-v2.json', canonical(dict(version=2, approved_for_lab_execution=False)))
        self.runtime('policies/builder-stall-fix-validation-v1.json', b'{}'); self.runtime('policies/builder-stall-fix-validation-v2.json', b'{}'); self.runtime('source_project.py', b'# Synthetic source project\n')
        self.protocol = dict(version='builder-stall-release-v1', cases=[{'id': name} for name in ['native-control', 'retained-paper-implementation', 'full-grid-netem']], reviewer={'type': 'AI', 'independent': False}, resources=dict(maximum_actual_provider_calls=48, maximum_qualification_commitments_cents=4800, maximum_elapsed_seconds=2700))
        self.write('docs/builder-stall-release-protocol-v1.json', canonical(self.protocol))
        self.prompts = [dict(id=identity(name), module_id=name, version=version) for name, version in [('research-autonomy', 'research-autonomy-v10'), ('research-experiment-builder', 'research-experiment-builder-v2')]]
        self.workflow = dict(max_spend_cents=-1, max_attempts=None, deadline_at='2099-01-01T00:00:00Z', committed_cents=123, initial_sha256='c' * 64)
        self.tasks = [dict(id=identity('task'), claim_id=identity('claim'), stage='building', status='blocked', label='inconclusive', reason='Original recorded blocker', attempts=2)]
        self.jobs, self.active, self.dispatches = [], [], []
        self.frozen = dict(protocol=self.protocol, runtime_manifest=copy.deepcopy(self.manifest), source_revision=self.manifest['source_revision'], prompts=self.prompts, frozen_at=self.r.stamp.return_value)
        self.save('frozen.json', self.frozen); self.save('assessment-before.json', self.workflow); self.select(self.source)
        self.image = 'sha256:' + 'b' * 64
        self.write('bin/builder_continuation_qualification_host.py', b'# Synthetic source, never executed\n'); self.write('bin/builder_stall_qualification_host.py', b'# Synthetic source, never executed\n')
        self.enterContext(patch.object(release.subprocess, 'check_output', side_effect=self.command))

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def runtime(self, name, raw):
        path = self.back / 'research_workflow' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def save(self, name, value, directory=None):
        path = (directory or self.source) / name; path.parent.mkdir(parents=True, exist_ok=True); release.q.save(path, value); return path
    def select(self, directory): (self.base / 'selected.txt').write_text(directory.name + '\n')
    def out(self, name):
        path = self.base / name; path.mkdir(); return path
    def command(self, command, **options):
        if command[:2] == ['git', 'show']: return self.program
        if command == ['git', 'rev-parse', 'HEAD']: return self.manifest['source_revision'] + '\n'
        if command == ['git', 'status', '--porcelain']: return ''
        raise AssertionError(command)
    def storage(self, path, raw=None):
        if raw is not None:
            self.assertTrue(path not in self.objects or self.objects[path] == raw, 'An immutable path cannot acquire changed bytes'); self.objects[path] = raw
        return self.objects[path]
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.startswith('select v.id,'): return copy.deepcopy(self.prompts)
        if sql.startswith('select to_jsonb(w)'): return [{'record': copy.deepcopy(self.workflow)}]
        if sql.startswith('select id,claim_id,stage,status,label'): return copy.deepcopy(self.tasks)
        if sql.startswith('select id,status,reason,updated_at'): return copy.deepcopy(self.jobs)
        if sql.startswith('select id,status,lease_until'): return copy.deepcopy(self.active)
        if sql.startswith('select id,task_id,status,provenance'): return copy.deepcopy(self.dispatches)
        if sql.startswith('select storage_path,sha256,byte_count'): return [self.artifacts[re.findall(r"'((?:''|[^'])*)'", sql)[-1]]]
        if sql.startswith('insert into agent_prompt_evaluations('):
            self.assertFalse(options['read_only']); prompt, outcome, raw, sha, pointer, reviewer = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]
            self.assertEqual(digest(raw.encode()), sha); self.assertIn('nonindependent', reviewer); self.reports[prompt, sha] = raw; return []
        if sql.startswith('select report_raw from agent_prompt_evaluations'): return [{'report_raw': self.reports[tuple(re.findall(r"'((?:''|[^'])*)'", sql))]}]
        if sql.startswith('select owner_id'): return [{'owner_id': identity('synthetic-owner')}]
        if sql.startswith('select sha256,byte_count'):
            ident = re.findall(r"'((?:''|[^'])*)'", sql)[-1]; return [self.saved_artifacts[ident]] if ident in self.saved_artifacts else []
        if sql.startswith('select public.research_append('):
            self.assertFalse(options['read_only']); values = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]; study, actor, kind, raw = values; record = json.loads(raw)
            self.assertEqual(study, release.STUDY); self.assertEqual(kind, 'artifacts'); self.assertFalse(record['provenance']['scientific_completion']); self.saved_artifacts[record['id']] = dict(sha256=record['sha256'], byte_count=record['byte_count']); return []
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        if (service, operation) == ('ec2', 'describe-volumes'): return {'Volumes': [dict(Size=300, Encrypted=True, Attachments=[{'InstanceId': 'i-087f1493809643115'}])]}
        raise AssertionError((service, operation, args))
    def retain(self, files, directory=None):
        directory = directory or self.source; raw = archive(files); pointer = dict(path='qualification/' + directory.name + '/' + digest(raw), sha256=digest(raw), retrieved_sha256=digest(raw), bytes=len(raw))
        self.objects[pointer['path']] = raw; (directory / 'evidence.zip').write_bytes(raw); self.save('host-status.json', {'evidence.json': pointer}, directory); return pointer, raw
    def assert_bundle(self, directory):
        raw = (directory / 'candidate.zip').read_bytes(); pointer = json.loads((directory / 'candidate.json').read_bytes()); self.assertEqual(self.objects[pointer['path']], raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            for entry in json.loads(bundle.read('artifact-manifest.json')):
                original = bundle.read(entry['path']); self.assertEqual(digest(original), entry['sha256']); self.assertEqual(len(original), entry['bytes'])
        return json.loads((directory / 'frozen.json').read_bytes())

    def test_pin_uses_clean_exact_backend_and_includes_the_four_required_runtime_files(self):
        result = release.pin(); self.assertEqual(result['version'], 4)
        value = json.loads((self.root / 'research-workflow-runtime.json').read_bytes())
        self.assertEqual(value['source_revision'], self.manifest['source_revision']); self.assertEqual(len(value['files']), 5)
        for name, sha in value['files'].items(): self.assertEqual(digest((self.back / 'research_workflow' / name).read_bytes()), sha)
        with patch.object(release.subprocess, 'check_output', return_value=' M experiment_builder.py\n'), self.assertRaisesRegex(AssertionError, 'Commit reviewed backend'): release.pin()

    def test_snapshot_preserves_original_limits_and_never_mutates_scientific_records(self):
        before = copy.deepcopy(self.workflow); result = release.snapshot(self.source, self.source)
        self.assertEqual(result['workflow'], before); self.assertEqual(result['tasks'], self.tasks); self.assertTrue(all(options.get('read_only', True) for _, options in self.sql))
        for key, changed in [('max_spend_cents', 1000), ('deadline_at', '2099-02-01T00:00:00Z'), ('max_attempts', 1), ('initial_sha256', '0' * 64), ('committed_cents', 122)]:
            self.workflow[key] = changed
            with self.subTest(key=key), self.assertRaises(AssertionError): release.snapshot(self.source, self.source)
            self.workflow = copy.deepcopy(before)

    def freeze_fixture(self):
        context = dict(task='building', repair_directive='Prior directive', repair_packet={'original': True}, repair_diagnostics={'zero': 0, 'missing': None}, original_failure='Retain original failure and source text')
        checkpoint = archive({'research-context.json': canonical(context), 'paper-text.json': canonical({'pages': [{'page': 3, 'text': 'Fictional retained source: 0 and null are distinct.'}]})})
        prefix = '.test-artifacts/assessment-4055396e/20261029T234244406605Z/'
        self.write(prefix + 'original-checkpoint.zip', checkpoint); self.write(prefix + 'matched-checkpoints.json', canonical({'checkpoints': [dict(file='original-checkpoint.zip', sha256=digest(checkpoint))]}))
        prior = dict(prompts=self.prompts, native_context={'synthetic': True}, original_program='Retained synthetic native program')
        self.write('.test-artifacts/builder-recovery-release-v1/selected.txt', b'prior-campaign\n'); self.write('.test-artifacts/builder-recovery-release-v1/prior-campaign/frozen.json', canonical(prior))
        return context, checkpoint

    def test_freeze_keeps_complete_original_context_separate_from_qualification_and_verifies_all_members(self):
        context, checkpoint = self.freeze_fixture(); (self.base / 'selected.txt').unlink()
        result = release.freeze(self.source); packet = self.assert_bundle(self.source)
        self.assertEqual(result['maximum_calls'], 48); self.assertEqual(packet['paper_checkpoint_sha256'], digest(checkpoint)); self.assertEqual(packet['assessment'], release.STUDY)
        self.assertEqual(packet['paper_context']['original_failure'], context['original_failure']); self.assertIsNone(packet['paper_context']['previous_feedback'])
        for key in ['repair_directive', 'repair_packet', 'repair_diagnostics']: self.assertNotIn(key, packet['paper_context'])
        with zipfile.ZipFile(self.source / 'candidate.zip') as bundle:
            self.assertEqual(json.loads(bundle.read('original-paper-context.json')), context); self.assertEqual(bundle.read('retained-paper-checkpoint.zip'), checkpoint)
            self.assertIn('research_workflow/tests/fixture.mjs', bundle.namelist()); self.assertNotIn('research_workflow/tests/ignore.txt', bundle.namelist()); self.assertNotIn('research_workflow/tests/__pycache__/ignored.py', bundle.namelist())
        followup = self.out('20261107T010000Z'); self.save('host-status.json', {'native-failure.json': {'failure': 'Original pre-provider harness failure'}, 'evidence.json': {'path': 'retained-original-archive'}})
        release.freeze(followup); packet = self.assert_bundle(followup); self.assertEqual(packet['pre_provider_harness_amendment']['previous_campaign'], self.source.name)
        self.assertEqual(packet['paper_checkpoint_sha256'], digest(checkpoint)); self.r.ssm.assert_not_called()

    def passing_fixture(self):
        names = [case['id'] for case in self.protocol['cases']]
        live = dict(status='awaiting-substantive-review', actual_calls=4, inherited_actual_calls=42, reserved_cents=400, inherited_reserved_cents=4200, wall_seconds=50, cases=[dict(name=name, structural_checks_passed=True) for name in names])
        review = dict(passed=True, source_revision=self.manifest['source_revision'], reviewer=self.protocol['reviewer'], cases=[dict(id=name, passed=True, actual_answer_reviewed=True) for name in names])
        self.save('live.json', live); self.save('reviewed.json', review)
        for phase in ['prepared', 'native']: self.save(phase + '.json', {'status': 'passed'})
        self.retain({'original-output.bin': b'Original zero=0, missing=null\n'})
        return live, review

    def test_evaluation_requires_reviewed_actual_answers_original_limits_and_both_native_prerequisites(self):
        live, review = self.passing_fixture(); self.assertEqual(release.record(self.source)['status'], 'passed')
        report = json.loads(next(iter(self.reports.values()))); self.assertEqual(report['actual']['inherited_actual_calls'], 42); self.assertIn('not independent paper validation', report['scientific_scope'])
        variations = [('review', dict(review, passed=False)), ('review', dict(review, source_revision='changed')), ('review', dict(review, reviewer={'type': 'human'})), ('review', dict(review, cases=[])), ('review', dict(review, cases=[dict(case, actual_answer_reviewed=False) for case in review['cases']])), ('live', dict(live, actual_calls=7)), ('live', dict(live, reserved_cents=601)), ('live', dict(live, wall_seconds=2701)), ('live', dict(live, cases=[dict(case, structural_checks_passed=False) for case in live['cases']])), ('live', dict(live, status='failed-or-paused')), ('live', dict(live, cases=[]))]
        for kind, changed in variations:
            self.save('live.json', live); self.save('reviewed.json', review); self.save('reviewed.json' if kind == 'review' else 'live.json', changed)
            with self.subTest(kind=kind, changed=changed): self.assertEqual(release.record(self.source)['status'], 'failed-or-paused')
        self.save('live.json', live); self.save('reviewed.json', review); self.save('native.json', {'status': 'failed'})
        self.assertEqual(release.record(self.source)['status'], 'failed-or-paused')
        (self.source / 'reviewed.json').unlink(); (self.source / 'live.json').unlink()
        self.assertEqual(release.record(self.source)['status'], 'failed-or-paused')
        last = json.loads(list(self.reports.values())[-1]); self.assertEqual(last['actual']['actual_calls'], 0); self.assertIsNone(last['review'])

    def test_policy_approval_requires_passed_retained_evidence_and_exact_frozen_source(self):
        self.passing_fixture(); release.record(self.source)
        original = json.loads((self.back / 'research_workflow/policies/netem-iperf-costs-v2.json').read_bytes()); result = release.approve(self.source)
        self.assertTrue(result['approved_for_lab_recovery']); self.assertEqual(result['evidence_sha256'], json.loads((self.source / 'evaluations-recorded.json').read_bytes())['archive']['sha256'])
        approved = json.loads((self.back / 'research_workflow/policies/netem-iperf-costs-v2.json').read_bytes()); self.assertEqual(approved, dict(original, approved_for_lab_execution=True))
        with self.assertRaises(AssertionError): release.approve(self.source)
        self.runtime('policies/netem-iperf-costs-v2.json', canonical(original)); self.runtime('experiment_builder.py', self.program + b'# changed\n')
        with self.assertRaises(AssertionError): release.approve(self.source)

    def test_public_checks_require_complete_recorded_counts_and_deny_unauthenticated_writes(self):
        queue = dict(study={'id': release.STUDY}, coverage={'jobs': 0}, jobs=[], autonomy=dict(coverage={'tasks': 1}, tasks=[{'id': identity('task')}]))
        calls = []
        def open_request(request, **options):
            calls.append(request)
            if not isinstance(request, str):
                self.assertEqual(request.method, 'POST'); self.assertEqual(request.data, b'{}')
                raise urllib.error.HTTPError(request.full_url, 401 if request.full_url.endswith('/autonomy') else 403, 'Synthetic denied', {}, io.BytesIO(b'{"error":"Sign in"}'))
            return Response(canonical(queue if 'diagnostics=1' in request else {'original_zero': 0, 'missing': None}))
        with patch.object(self.r.prior.guard.OPEN, 'open', side_effect=open_request): result = release.public_checks(self.source)
        self.assertEqual(result['status'], 'passed'); self.assertEqual(len(result['checks']), 6); self.assertEqual(len(calls), 6)
        self.assertEqual(json.loads((self.source / 'queue.json').read_bytes()), queue)
        queue['coverage']['jobs'] = 1
        with patch.object(self.r.prior.guard.OPEN, 'open', side_effect=open_request), self.assertRaises(AssertionError): release.public_checks(self.source)
        with patch.object(self.r.prior.guard.OPEN, 'open', return_value=Response(b'{}', 503)), self.assertRaises(AssertionError): release.public_checks(self.source)

    def postrelease_fixture(self):
        records = []
        for index, status in enumerate(['failed', 'complete']):
            raw = canonical({'status': status, 'original_zero': 0, 'missing': None}); sha = digest(raw); ident = identity('artifact-' + str(index)); path = release.STUDY + '/' + sha
            self.objects[path] = raw; self.artifacts[ident] = dict(storage_path=path, sha256=sha, byte_count=len(raw))
            artifact = dict(name='receipt.json', sha256=sha, **({'id': ident} if index == 0 else {'artifact_id': ident}))
            records.append(dict(id=identity('dispatch-' + str(index)), task_id=identity('task'), status=status, provenance={'artifacts': [artifact, {'name': 'private-not-selected.json'}]}))
        self.dispatches = records

    def test_postrelease_is_bounded_read_only_and_retains_zero_missing_and_original_failed_outcomes(self):
        self.postrelease_fixture(); result = release.postrelease(self.source)
        self.assertEqual(result['recorded_outcomes'], 2); self.assertEqual(result['status_counts'], {'failed': 1, 'complete': 1}); self.assertGreater(result['retrieved_bytes'], 0)
        report = json.loads((self.source / 'postrelease.json').read_bytes()); self.assertEqual((report['writes'], report['model_calls']), (0, 0))
        for record in report['dispatches']:
            self.assertEqual(len(record['retrieved_artifacts']), 1); item = record['retrieved_artifacts'][0]; raw = (self.source / item['file']).read_bytes(); self.assertEqual(digest(raw), item['sha256']); self.assertIsNone(json.loads(raw)['missing'])
        self.assertTrue(all(options.get('read_only', True) for _, options in self.sql)); self.assertIn('limit 6', self.sql[0][0])
        self.artifacts[next(iter(self.artifacts))]['byte_count'] = 8_000_001
        with self.assertRaises(AssertionError): release.postrelease(self.source)

    def test_postrelease_archive_resumes_its_exact_pending_bytes_and_checks_each_member_and_registration(self):
        self.postrelease_fixture(); release.postrelease(self.source); self.save('postrelease-review.json', dict(reviewer={'type': 'AI', 'independent': False}))
        self.write('bin/builder-stall-release.py', b'# Synthetic retained helper\n'); (self.source / 'unrelated.txt').write_bytes(b'Do not include unrelated extension')
        out = self.out('20261107T020000Z'); result = release.retain_postrelease(out)
        self.assertFalse(result['public']); self.assertEqual(result['sha256'], result['retrieved_sha256'])
        pending = json.loads((self.source / 'postrelease-pending.json').read_bytes()); original = (self.root / pending['archive']).read_bytes()
        with zipfile.ZipFile(io.BytesIO(original)) as bundle:
            self.assertNotIn('unrelated.txt', bundle.namelist()); self.assertIn('release-helper.py', bundle.namelist())
            for item in json.loads(bundle.read('artifact-manifest.json')): self.assertEqual(digest(bundle.read(item['path'])), item['sha256'])
        self.assertEqual(release.retain_postrelease(out)['artifact_id'], result['artifact_id']); self.assertEqual((self.root / pending['archive']).read_bytes(), original)
        self.save('postrelease-pending.json', dict(pending, archive='../outside.zip'))
        with self.assertRaises(AssertionError): release.retain_postrelease(out)

    def test_executor_verification_requires_three_exact_account_bound_zips_and_every_manifest_file(self):
        raw = archive({'experiment_builder.py': self.program}); resources = [dict(ResourceType='AWS::Lambda::Function', LogicalResourceId='UnrelatedFunction', PhysicalResourceId='unrelated'), dict(ResourceType='AWS::S3::Bucket', LogicalResourceId='ResearchWorkflowPackageExecutorBucket', PhysicalResourceId='unrelated-bucket')]
        resources.extend(dict(ResourceType='AWS::Lambda::Function', LogicalResourceId='ResearchWorkflowPackage' + kind + 'Fixture', PhysicalResourceId='synthetic-' + kind.lower()) for kind in ['Executor', 'Reaper', 'Ingest'])
        def aws(service, operation, *args):
            if operation == 'list-stack-resources': return {'StackResourceSummaries': resources}
            name = args[1]; return {'Configuration': dict(FunctionArn='arn:aws:lambda:us-east-1:395567831870:function:' + name, CodeSha256=base64.b64encode(bytes.fromhex(digest(raw))).decode(), FunctionName=name, Handler='synthetic.handler'), 'Code': {'Location': 'https://signed.example.test/' + name}}
        with patch.object(self.r, 'aws', side_effect=aws), patch.object(self.r.prior.guard.OPEN, 'open', side_effect=lambda *args, **kwargs: Response(raw)):
            result = release.verify_executors(self.source)
        self.assertEqual(len(result['executors']), 3); self.assertEqual(result['status'], 'passed'); self.assertTrue(all(item['files_verified'] == 1 for item in result['executors']))
        resources.pop()
        with patch.object(self.r, 'aws', side_effect=aws), patch.object(self.r.prior.guard.OPEN, 'open', side_effect=lambda *args, **kwargs: Response(raw)), self.assertRaises(AssertionError): release.verify_executors(self.source)

    def cache_fixture(self):
        original_metadata = canonical(dict(commands=['python3 development-control.py'], checks=[dict(value=0, missing=None)], limitations=['Synthetic exposed source arithmetic only'], original_extra_notes={'version': 'retained Ω'}))
        self.project = {'project/experiment.py': b'def evaluate(spec_path):\n    return None\n', 'project/requirements.lock': b'', 'project/system-packages.lock.json': b'[]\n', 'project/build-evidence.json': original_metadata}
        checkpoint = archive(self.project); native_checkpoint = archive({'calculation.py': b'# Synthetic retained native control\n'})
        old_files = dict(self.manifest['files'], **{'repair_validation.py': digest(b'# original validator\n'), 'source_project.py': digest(b'# original source project\n')})
        self.frozen['runtime_manifest']['files'] = old_files
        self.save('frozen.json', self.frozen)
        (self.source / 'candidate.zip').write_bytes(archive({'qualification.py': b'# Retained original controller\n', 'frozen.json': canonical(self.frozen), 'artifact-manifest.json': b'[]'}))
        cases = [dict(name='native-control', controls=[{'passed': True}] * 3, receipts=[dict(status='complete', provider_calls=20, checkpoint={'sha256': digest(native_checkpoint)})]), dict(name='retained-paper-implementation', controls=[{'passed': True}] * 4, receipts=[dict(status='complete', provider_calls=22, checkpoint={'sha256': digest(checkpoint)})])]
        live = dict(status='failed-or-paused', actual_calls=42, reserved_cents=4200, failure='Keep dependency installations outside the frozen source tree', cases=cases)
        self.save('live.json', live); self.save('evaluations-recorded.json', {'status': 'failed-or-paused'})
        self.retain({'native/checkpoint.zip': native_checkpoint, 'paper/checkpoint.zip': checkpoint})
        changed = self.program + b'# Source sealing amendment, execution functions unchanged\n'
        self.runtime('experiment_builder.py', changed); self.runtime('repair_validation.py', b'# Revised cache-preserving validator\n'); self.runtime('source_project.py', b'# Revised source project\n')
        self.manifest['files'] = {name: digest((self.back / 'research_workflow' / name).read_bytes()) for name in old_files}
        self.write('research-workflow-runtime.json', canonical(self.manifest))
        return original_metadata, checkpoint

    def test_cache_followup_inherits_both_exact_checkpoints_and_all_42_calls_without_reexecution(self):
        self.cache_fixture(); before = (self.source / 'live.json').read_bytes(); out = self.out('20261107T010000Z')
        result = release.freeze_cache_followup(out); packet = self.assert_bundle(out)
        self.assertEqual(result['inherited_calls'], 42); self.assertEqual(result['additional_model_calls'], 0)
        self.assertEqual(packet['packaging_followup']['reserved_cents'], 4200); self.assertEqual(packet['protocol']['resources']['maximum_actual_provider_calls'], 48)
        self.assertEqual((self.source / 'live.json').read_bytes(), before); self.assertEqual(json.loads((out / 'assessment-before.json').read_bytes()), self.workflow)
        self.assertEqual(packet['packaging_followup']['overall_deadline_at'], '2026-11-07T00:45:00+00:00')
        with zipfile.ZipFile(out / 'candidate.zip') as bundle:
            for reference in packet['packaging_followup']['checkpoints'].values(): self.assertEqual(digest(bundle.read(reference['file'])), reference['sha256'])
        self.r.ssm.assert_not_called()

    def test_metadata_and_packet_followups_retain_failed_parents_and_the_cumulative_48_call_ceiling(self):
        self.cache_fixture(); original = self.source
        parent = self.out('20261107T010000Z'); release.freeze_cache_followup(parent)
        first = json.loads((parent / 'frozen.json').read_bytes()); self.save('evaluations-recorded.json', {'status': 'failed-or-paused'}, parent); self.retain({'failure.bin': b'Original metadata contract failure before provider admission\n'}, parent)
        self.save('live.json', dict(actual_calls=0, inherited_actual_calls=42, failure='Build evidence must identify complete commands', cases=[{}, {}]), parent)
        class FrozenDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None): return cls(2026, 11, 7, 0, 30, tzinfo=dt.timezone.utc)
        for index, fallback in enumerate([False, True]):
            self.select(parent)
            if fallback: self.save('live.json', dict(actual_calls=0, inherited_actual_calls=42, failure='Required work packet exceeds the frozen working-view size', cases=[{}, {}]), parent)
            out = self.out('20261107T0' + str(index + 2) + '0000Z')
            with self.subTest(fallback=fallback), patch.object(release.dt, 'datetime', FrozenDatetime): result = release.freeze_cache_followup(out, metadata=True)
            packet = self.assert_bundle(out); inherited = packet['packaging_followup']
            self.assertEqual(packet['protocol']['version'], 'builder-stall-release-followup-v5' if fallback else 'builder-stall-release-followup-v4')
            self.assertEqual(result['additional_model_calls'], 6); self.assertEqual(inherited['actual_calls'], 42); self.assertEqual(inherited['reserved_cents'], 4200)
            self.assertEqual(packet['protocol']['resources']['maximum_actual_provider_calls'], 48); self.assertEqual(packet['protocol']['resources']['maximum_qualification_commitments_cents'], 4800)
            self.assertEqual(inherited['metadata_parent']['campaign'], parent.name); self.assertEqual(inherited['previous_campaign'], original.name)
            self.assertEqual(inherited['original_deadline_at'], '2026-11-07T00:45:00+00:00'); self.assertEqual(inherited['overall_deadline_at'], '2026-11-07T01:15:00+00:00')
            self.assertEqual(first['paper_context'] if 'paper_context' in first else None, packet.get('paper_context'))
        self.r.ssm.assert_not_called()

    def test_preservation_followup_accepts_only_lossless_original_metadata_and_unchanged_executable_sources(self):
        original_metadata, original_checkpoint = self.cache_fixture(); parent = self.out('20261107T010000Z'); release.freeze_cache_followup(parent)
        representation = canonical(dict(original_sha256=digest(original_metadata), original_bytes_base64=base64.b64encode(original_metadata).decode()))
        metadata = json.loads(original_metadata); project = dict(self.project, **{'project/build-evidence.json': canonical({key: metadata[key] for key in ['commands', 'checks', 'limitations']}), 'project/build-evidence-original.json': representation})
        checkpoint = archive(project)
        self.save('live.json', dict(actual_calls=4, inherited_actual_calls=42, reserved_cents=400, failure='Preserve the complete original metadata bytes in a verified envelope', cases=[dict(name='native-control', receipts=[], inherited_receipts=[{'status': 'complete'}]), dict(name='retained-paper-implementation', receipts=[dict(status='complete', provider_calls=4, native_tool_cleanup=True, checkpoint={'sha256': digest(checkpoint)})])]), parent)
        self.save('evaluations-recorded.json', {'status': 'failed-or-paused'}, parent)
        self.retain({'completed/checkpoint.zip': checkpoint}, parent)
        for name in ['prepared', 'native']: self.save(name + '.json', {'status': 'passed'}, parent)
        self.write('bin/builder_preservation_check.py', (ROOT / 'bin/builder_preservation_check.py').read_bytes())
        out = self.out('20261107T020000Z'); result = release.freeze_preservation_followup(out); packet = self.assert_bundle(out)
        self.assertEqual(result['inherited_unique_calls'], 46); self.assertEqual(result['additional_model_calls'], 0); self.assertTrue(result['native_controls_inherited_without_replay'])
        self.assertEqual(result['proof']['encoding'], 'json-base64-sha256'); self.assertEqual(result['proof']['sha256'], digest(original_metadata))
        self.assertEqual(packet['packaging_followup']['reserved_cents'], 4600); self.assertEqual(packet['runtime_manifest'], self.manifest)
        with zipfile.ZipFile(out / 'candidate.zip') as bundle:
            self.assertEqual(bundle.read('original-build-evidence.bin'), original_metadata); self.assertEqual(bundle.read('completed-metadata-checkpoint.zip'), checkpoint)
        self.assertTrue(packet['packaging_followup']['equivalent_preservation_amendment']['scientific_criteria_unchanged']); self.r.ssm.assert_not_called()

    def production_fixture(self):
        live, _ = self.passing_fixture()
        next(case for case in live['cases'] if case['name'] == 'full-grid-netem')['replications'] = [{'observations': 10}, {'observations': 10}, {'observations': 10}]
        self.save('live.json', live); release.record(self.source)
        self.save('active-verified.json', dict(status='passed', admission=True, source_revision=self.manifest['source_revision']))
        active = self.source / 'active-verified.json'; os.utime(active, (100, 100))
        observed = self.out('20261107T010000Z'); public = self.save('public-verified.json', {'status': 'passed'}, observed); os.utime(public, (101, 101))
        self.save('executors-verified.json', dict(status='passed', source_revision=self.manifest['source_revision']), observed)
        self.save('browser-verified.json', dict(passed=True, reviewer={'type': 'AI', 'independent': False}, conditional_gaps=['Synthetic local receipt; not a live release']))
        self.tasks.append(dict(id=identity('intake'), claim_id=None, stage='intake', status='finished', label=None))
        for name in ['bin/builder-stall-release.py', 'bin/builder_stall_qualification_host.py', 'bin/builder_preservation_check.py', 'bin/review-builder-stall-evidence.py', 'test/builder_preservation_check_test.py', 'docs/builder-stall-preservation-followup-v6.json', 'docs/builder-stall-metadata-followup-v4.json', 'docs/builder-stall-production-v1.md']:
            self.write(name, b'Synthetic retained software release evidence\n')
        for name in ['builder-stall-release-packet-final-unit.log', 'builder-stall-release-approved-unit.log']:
            path = self.back / '.test-artifacts' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'Synthetic retained test result\n')
        for name in ['builder-stall-release-cache-infra.log', 'builder-stall-release-infra-build.log', 'builder-stall-release-approved-infra.log', 'builder-stall-release-approved-build.log', 'builder-stall-release-database-repair.log', 'builder-stall-release-cache-database-builder.log']: self.write('.test-artifacts/' + name, b'Synthetic retained report\n')
        self.write('.test-artifacts/openclaw-release/20261030T000000Z/receipt.json', canonical({'status': 'retained synthetic receipt'})); self.write('.test-artifacts/openclaw-release/20261030T000000Z/session.json', b'PRIVATE DO NOT SELECT'); self.write('.test-artifacts/openclaw-release/20261030T000000Z/directory/ignored', b'not a selected file')
        self.save('receipt.json', {'status': 'retained source receipt'}); (self.source / 'unrelated.txt').write_bytes(b'Unrelated extension')
        return observed

    def test_production_record_requires_current_checks_and_preserves_its_exact_pending_archive_on_retry(self):
        self.production_fixture(); out = self.out('20261107T020000Z'); result = release.record_release(self.source, out)
        self.assertEqual(result['assessment']['maximum_cents'], -1); self.assertIsNone(result['assessment']['attempt_cap']); self.assertEqual(result['assessment']['committed_cents'], 123)
        self.assertEqual(result['assessment']['labels'], {'inconclusive': 1}); self.assertFalse(result['evidence']['public'])
        pending = json.loads((self.source / 'release-pending.json').read_bytes()); raw = (self.root / pending['archive']).read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            report = json.loads(bundle.read('release-report.json')); self.assertEqual(report['qualification']['total_unique_calls'], 46); self.assertEqual(report['qualification']['netem_observations'], 30)
            self.assertIsNone(report['measured_charges_usd']); self.assertIsNone(report['unallocated_host_storage_cost_usd']); self.assertFalse(report['reviewer']['independent'])
            self.assertNotIn('.test-artifacts/openclaw-release/20261030T000000Z/session.json', bundle.namelist()); self.assertNotIn(str((self.source / 'candidate.zip').relative_to(self.root)), bundle.namelist())
            for item in json.loads(bundle.read('artifact-manifest.json')): self.assertEqual(digest(bundle.read(item['path'])), item['sha256'])
        self.assertEqual(release.record_release(self.source, out)['evidence']['artifact_id'], result['evidence']['artifact_id'])
        self.assertEqual((self.root / pending['archive']).read_bytes(), raw)
        (self.source / 'release-pending.json').unlink(); self.write('docs/builder-stall-packet-followup-v5.json', canonical({'retained': True})); out2 = self.out('20261107T030000Z')
        updated = release.record_release(self.source, out2); self.assertNotEqual(updated['evidence']['sha256'], result['evidence']['sha256'])
        pending2 = json.loads((self.source / 'release-pending.json').read_bytes()); self.save('release-pending.json', dict(pending2, archive='../outside.zip'))
        with self.assertRaises(AssertionError): release.record_release(self.source, out2)

    def test_main_routes_keep_arguments_fixed_and_preserve_receipts_for_failed_live_prerequisites(self):
        routes = {'pin': 'pin', 'freeze': 'freeze', 'freeze-cache-followup': 'freeze_cache_followup', 'freeze-metadata-followup': 'freeze_cache_followup', 'freeze-preservation-followup': 'freeze_preservation_followup', 'snapshot': 'snapshot', 'record-review': 'record', 'approve': 'approve', 'public-checks': 'public_checks', 'postrelease': 'postrelease', 'retain-postrelease': 'retain_postrelease', 'verify-executors': 'verify_executors', 'record-release': 'record_release'}
        for mode, action in routes.items():
            with self.subTest(mode=mode), patch.object(release, action, return_value={'synthetic': True}) as call, patch.object(sys, 'argv', ['builder-stall-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as output: release.main()
            value = json.loads(output.getvalue()); self.assertEqual(value['status'], 'complete'); self.assertEqual(value['result'], {'synthetic': True}); self.assertEqual(json.loads((Path(value['directory']) / 'receipt.json').read_bytes())['status'], 'complete')
            if mode == 'freeze-metadata-followup': self.assertIs(call.call_args.args[-1], True)
            if mode in ['record-review', 'approve']: call.assert_called_once_with(self.source)
        (self.base / 'selected.txt').unlink()
        with patch.object(release, 'snapshot', return_value={}) as snapshot, patch.object(sys, 'argv', ['builder-stall-release.py', 'snapshot']), contextlib.redirect_stdout(io.StringIO()): release.main()
        self.assertIsNone(snapshot.call_args.args[0]); self.select(self.source)
        prior = self.out('20261106T000000Z'); self.frozen['pre_provider_harness_amendment'] = {'previous_campaign': prior.name}; self.save('frozen.json', self.frozen)
        with patch.object(release, 'record', return_value={'status': 'failed-or-paused'}) as record, patch.object(sys, 'argv', ['builder-stall-release.py', 'record-initial-failure']), contextlib.redirect_stdout(io.StringIO()): release.main()
        record.assert_called_once_with(prior)
        for mode in ['status', 'collect-status', 'collect']:
            with self.subTest(mode=mode), patch.object(release.q, mode.replace('-', '_'), return_value={'retained': True, 'cases': ['private detail']}) as action, patch.object(sys, 'argv', ['builder-stall-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as output: release.main()
            self.assertNotIn('cases', json.loads(output.getvalue())['result']); action.assert_called_once_with(self.source)
        with patch.object(release.old, 'preview', return_value={}) as preview, patch.object(sys, 'argv', ['builder-stall-release.py', 'preview']), contextlib.redirect_stdout(io.StringIO()): release.main()
        self.assertEqual(preview.call_args.args[0], self.source)
        self.r.prior.PRIVATE = set()
        for mode in ['verify-held', 'verify-active']:
            with patch.object(release.old.prior, 'verify', return_value={}) as verify, patch.object(sys, 'argv', ['builder-stall-release.py', mode]), contextlib.redirect_stdout(io.StringIO()): release.main()
            self.assertIs(verify.call_args.args[-1], mode == 'verify-active'); self.assertEqual(json.loads((self.source / 'migration-applied.json').read_bytes())['status'], 'passed')
        self.assertEqual(self.r.prior.PRIVATE, {'research_model_reconciliations', 'research_autonomy_repairs', 'research_autonomy_repair_events'})
        for mode in ['prepare', 'native', 'evidence', 'live']:
            self.save('host-status.json', {'prepared.json': {'status': 'passed'}, 'native.json': {'status': 'passed'}})
            with patch.object(release.q, 'dispatch', return_value={}) as dispatch, patch.object(sys, 'argv', ['builder-stall-release.py', mode]), contextlib.redirect_stdout(io.StringIO()): release.main()
            dispatch.assert_called_once_with(self.source, mode)
        self.save('host-status.json', {'prepared.json': {'status': 'passed'}, 'native.json': {'status': 'failed'}})
        with patch.object(release.q, 'dispatch') as dispatch, patch.object(sys, 'argv', ['builder-stall-release.py', 'live']), contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaisesRegex(AssertionError, 'Inspect passing original native prerequisite'): release.main()
        self.assertEqual(json.loads(output.getvalue())['status'], 'failed'); dispatch.assert_not_called()


if __name__ == '__main__': unittest.main()
