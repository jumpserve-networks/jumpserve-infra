"""Continuation release/recovery controls with synthetic services and real bytes.

No SSM command, provider call, production SQL or deployment is executed. Embedded
host commands are inspected; SQL strings are checked at the transaction boundary.
"""
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('continuation_release_unit', ROOT / 'bin/builder-continuation-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def identity(name): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'continuation-unit:' + name))
def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as output:
        for name, raw in sorted(files.items()): output.writestr(name, raw)
    return buffer.getvalue()


class ContinuationRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='continuation-release-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'infra'; self.back = self.root.parent / 'backend'
        self.base = self.root / '.test-artifacts/builder-continuation-release-v1'
        self.source = self.base / '20261107T000000Z'; self.source.mkdir(parents=True)
        for name, value in [('ROOT', self.root), ('BACK', self.back), ('BASE', self.base)]: self.enterContext(patch.object(release, name, value))
        self.r = MagicMock(); self.r.sha.side_effect = digest; self.r.stamp.return_value = '2026-11-07T00:00:00Z'; self.r.instance.return_value = 'i-087f1493809643115'; self.r.target.return_value = {'synthetic_target': True}
        self.r.ssm.return_value = dict(command_id='synthetic-original-command', instance_id='i-synthetic')
        self.r.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"
        self.enterContext(patch.object(release, 'r', self.r)); self.m = MagicMock(); self.enterContext(patch.object(release, 'm', self.m))
        self.objects, self.reports, self.queries = {}, {}, []
        self.m.storage.side_effect = self.storage; self.r.admin.query.side_effect = self.query
        self.workflow = dict(max_spend_cents=10000, max_attempts=None, committed_cents=700, deadline_at='2099-01-01T00:00:00Z', status='completed-with-blockers')
        self.tasks, self.dispatches, self.artifacts = [], [], {}
        self.manifest = dict(source_revision='a' * 40, version=2, files={'experiment_builder.py': digest(b'# retained runtime\n')})
        self.write('research-workflow-runtime.json', canonical(self.manifest)); self.write('docs/builder-continuation-release-protocol-v1.json', canonical({'version': 'builder-continuation-release-v1', 'resources': {'maximum_real_provider_calls': 2}}))
        self.prompts = [dict(id=identity(name), module_id=name, version=version, published_at='retained-time') for name, version in [('research-autonomy', 'research-autonomy-v10'), ('research-experiment-builder', 'research-experiment-builder-v2')]]
        self.frozen = dict(source_revision=self.manifest['source_revision'], runtime_manifest=self.manifest, prompts=self.prompts, protocol={'version': 'builder-continuation-release-v1'})
        self.save('frozen.json', self.frozen); self.save('candidate.json', dict(path='qualification/synthetic-candidate.zip', sha256='f' * 64))
        self.save('prepared.json', dict(status='passed', image='sha256:' + 'b' * 64)); self.save('evaluations-recorded.json', {'status': 'passed'})
        (self.base / 'selected.txt').write_text(self.source.name + '\n')

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def save(self, name, value, directory=None):
        path = (directory or self.source) / name; path.parent.mkdir(parents=True, exist_ok=True); release.save(path, value); return path
    def storage(self, path, raw=None):
        if raw is not None:
            self.assertTrue(path not in self.objects or self.objects[path] == raw, 'Immutable object path cannot change bytes')
            self.objects[path] = raw
        return self.objects[path]
    def query(self, sql, **options):
        self.queries.append((sql, options))
        if sql.startswith('select v.id,'): return copy.deepcopy(self.prompts)
        if sql.startswith('select to_jsonb(w)'): return [{'record': copy.deepcopy(self.workflow)}]
        if sql.startswith('select to_jsonb(t)'): return [{'record': copy.deepcopy(value)} for value in self.tasks]
        if sql.startswith('select to_jsonb(d)'): return [{'record': copy.deepcopy(value)} for value in self.dispatches]
        if sql.startswith('select task_id,details,created_at'): return copy.deepcopy(self.events)
        if sql.startswith('select status,reason,max_spend_cents'): return [copy.deepcopy(self.workflow)]
        if sql.startswith('select id,claim_id,stage,status,reason,attempts'): return copy.deepcopy(self.tasks)
        if sql.startswith(('select stage,status,count(*)', 'select status,count(*)', 'select id,task_id,status,provenance', 'select id,task_id,stage,status,request_sha256')): return []
        if sql.startswith('select storage_path,sha256,byte_count'): return [self.artifacts[re.findall(r"'((?:''|[^'])*)'", sql)[-1]]]
        if sql.startswith('insert into agent_prompt_evaluations('):
            self.assertFalse(options['read_only']); values = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]
            prompt, outcome, raw, sha, pointer, reviewer = values
            self.assertEqual(digest(raw.encode()), sha); self.assertIn(outcome, ['passed', 'failed-or-paused']); self.assertIn('AI', reviewer)
            self.reports[(prompt, sha)] = raw; return []
        if sql.startswith('select report_raw from agent_prompt_evaluations'):
            values = re.findall(r"'((?:''|[^'])*)'", sql); return [{'report_raw': self.reports[tuple(values)]}]
        if sql.startswith('begin;'):
            self.assertFalse(options['read_only']); return []
        raise AssertionError('Unexpected SQL: ' + sql)
    def checkpoint(self): return archive({'research-context.json': b'{"original":true}', 'previous-failure.log': b'Original retained failure\n'})
    def evidence(self, directory=None, phases=True):
        directory = directory or self.source
        files = {'original-response.bin': b'Original raw provider response: missing=null, zero=0\n'}
        if phases: files.update({name + '.json': canonical({'status': 'passed' if name != 'live' else 'failed-or-paused', 'cases': []}) for name in ['prepared', 'native', 'replay', 'live']})
        files['artifact-manifest.json'] = canonical([dict(path=name, sha256=digest(raw), bytes=len(raw)) for name, raw in sorted(files.items())])
        raw = archive(files); path = 'qualification/' + directory.name + '/' + digest(raw) + '.zip'; self.objects[path] = raw
        pointer = dict(path=path, sha256=digest(raw), retrieved_sha256=digest(raw), bytes=len(raw)); self.save('host-status.json', {'evidence.json': pointer}, directory); return pointer, raw

    def test_campaign_selection_and_private_json_preserve_unicode_missing_and_zero(self):
        self.assertEqual(release.selected(), self.source); self.assertEqual(release.host(self.source), '/var/lib/jumpserve-openclaw/builder-continuation-v1/' + self.source.name)
        path = self.save('private.json', {'text': 'Ω', 'missing': None, 'zero': 0})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600); self.assertEqual(json.loads(path.read_bytes()), {'text': 'Ω', 'missing': None, 'zero': 0})
        (self.base / 'selected.txt').write_text('../untrusted\n')
        with self.assertRaises(AssertionError): release.selected()

    def test_each_phase_is_scoped_to_its_existing_campaign_and_never_replays_a_dispatch(self):
        self.write('bin/retain_continuation_image_host.py', b'# Synthetic image retention entry point\n')
        for mode in ['prepare', 'native', 'replay', 'live', 'image', 'evidence']:
            with self.subTest(mode=mode):
                result = release.dispatch(self.source, mode); self.assertEqual(result['mode'], mode)
                commands = self.r.ssm.call_args.args[0]
                self.assertTrue(commands[-1].startswith('systemd-run --unit=js-cont-' + mode + '-'))
                for flag in ['RuntimeMaxSec=1900', 'NoNewPrivileges=true', 'PrivateTmp=true', 'ProtectHome=true', 'ProtectSystem=strict', 'ReadWritePaths=/var/lib/jumpserve-openclaw', 'MemoryMax=3G']: self.assertIn(flag, commands[-1])
                self.assertIn('runuser -u jumpserve', commands[-1]); self.assertIn(release.host(self.source), commands[-1])
                if mode == 'prepare':
                    python = next(value for value in commands if value.startswith('/opt/jumpserve/python/bin/python -B -c ')); code = shlex.split(python)[-1]
                    compile(code, '<synthetic-inspection-only>', 'exec'); self.assertIn('assert digest(raw)', code); self.assertIn("'..' not in name.parts", code); self.assertIn('exist_ok=False', code)
                if mode == 'image': self.assertIn(base64.b64encode(b'# Synthetic image retention entry point\n').decode(), '\n'.join(commands))
                before = self.r.ssm.call_count
                with self.assertRaisesRegex(AssertionError, 'Never repeat'): release.dispatch(self.source, mode)
                self.assertEqual(self.r.ssm.call_count, before)

    def test_live_dispatch_requires_each_frozen_amendment_without_raising_original_limits(self):
        packets = [dict(protocol=dict(version='assessment-recovery-release-v1', resources={'maximum_real_provider_calls': 2}), amendment={'version': 'assessment-recovery-release-amendment-v2'}, live_cases=[{}, {}]), dict(protocol=dict(version='builder-recovery-release-followup-v2', resources=dict(maximum_actual_provider_calls=36, maximum_native_case_calls=16)), amendment=dict(version='builder-recovery-release-amendment-v2', resources=dict(maximum_additional_provider_calls=16, maximum_cumulative_provider_calls=36)), inherited=dict(actual_calls=18, planner_results=[{}, {}], native_receipts=[{'status': 'complete'}])), dict(protocol={'version': 'builder-continuation-release-v1'}, amendment={'resources': {'additional_real_provider_calls': 1}}, inherited_native={'checkpoint': 'retained'})]
        for index, packet in enumerate(packets):
            with self.subTest(index=index):
                self.save('frozen.json', packet); release.dispatch(self.source, 'live'); (self.source / 'live-command.json').unlink()
        invalid = copy.deepcopy(packets[1]); invalid['inherited']['native_receipts'][0]['status'] = 'unknown'; self.save('frozen.json', invalid)
        before = self.r.ssm.call_count
        with self.assertRaises(AssertionError): release.dispatch(self.source, 'live')
        self.assertEqual(self.r.ssm.call_count, before)

    def test_status_retains_original_ssm_results_and_handles_pending_truncated_and_missing_case_status(self):
        self.save('latest-status-command.json', dict(command_id='original-status', instance_id='i-original'))
        for status in ['Pending', 'Failed']:
            self.r.aws.return_value = {'Status': status}; self.assertEqual(release.collect_status(self.source), {'status': status})
        self.r.aws.return_value = dict(Status='Success', StandardOutputContent='{"truncated":')
        self.assertEqual(release.collect_status(self.source), {'status': 'requires-archive', 'bytes': 13})
        data = {'live.json': {'status': 'failed-or-paused', 'cases': [{'name': 'retained-native'}]}, 'evidence.json': {'path': 'private-original'}}
        self.r.aws.return_value = dict(Status='Success', StandardOutputContent=json.dumps(data))
        result = release.collect_status(self.source); self.assertIsNone(result['phases']['live.json']['cases'][0]['status']); self.assertEqual(json.loads((self.source / 'host-status.json').read_bytes()), data)
        self.save('native-command.json', dict(command_id='original-native', instance_id='i-original'))
        with patch.object(release.time, 'sleep'), patch.object(release, 'collect_status', side_effect=[subprocess.CalledProcessError(1, ['synthetic AWS adapter']), {'status': 'Pending'}, {'status': 'retrieved'}]) as collect:
            result = release.status(self.source)
        self.assertEqual(collect.call_count, 3); self.assertEqual(result['dispatches']['native']['command_status'], 'Success')
        self.assertTrue((self.source / 'native-ssm-result.json').exists()); self.assertEqual(result['snapshot']['status'], 'retrieved')
        with patch.object(release.time, 'sleep'), patch.object(release, 'collect_status', return_value={'status': 'Pending'}) as collect:
            self.assertEqual(release.status(self.source)['snapshot']['status'], 'Pending')
        self.assertEqual(collect.call_count, 10)

    def test_private_archive_collection_verifies_both_container_and_each_original_member_hash(self):
        pointer, raw = self.evidence(); result = release.collect(self.source)
        self.assertTrue(result['verified']); self.assertEqual((self.source / 'evidence.zip').read_bytes(), raw); self.assertEqual(result['cases'], [])
        self.evidence(phases=False)
        for name in ['prepared', 'native', 'replay', 'live']: (self.source / (name + '.json')).unlink()
        self.assertEqual(release.collect(self.source)['cases'], [])
        self.objects[pointer['path']] = raw + b'Changed outside the original archive'
        self.save('host-status.json', {'evidence.json': pointer})
        with self.assertRaises(AssertionError): release.collect(self.source)
        bad = archive({'artifact-manifest.json': canonical([{'path': 'raw.bin', 'sha256': '0' * 64}]), 'raw.bin': b'Changed original member'})
        pointer = dict(path='bad-archive', sha256=digest(bad), retrieved_sha256=digest(bad)); self.objects['bad-archive'] = bad; self.save('host-status.json', {'evidence.json': pointer})
        with self.assertRaises(AssertionError): release.collect(self.source)

    def test_record_review_preserves_the_failed_campaign_and_identifies_nonindependence_and_original_bytes(self):
        prior = self.base / '20261106T000000Z'; prior.mkdir(); self.save('frozen.json', self.frozen, prior); self.evidence(prior); self.evidence()
        self.frozen['followup_of'] = prior.name; self.save('frozen.json', self.frozen)
        self.save('live.json', dict(status='failed-or-paused', actual_calls=2), prior)
        review = dict(status='passed', reviewer=dict(type='AI', independent=False), source_revision=self.manifest['source_revision']); self.save('reviewed.json', review)
        result = release.record_review(self.source); self.assertEqual(len(result['evaluations']), 4)
        values = [json.loads(raw) for raw in self.reports.values()]
        self.assertEqual({value['status'] for value in values}, {'failed-or-paused', 'passed'})
        for value in values:
            self.assertIsNone(value['measured_charges_usd']); self.assertIsNone(value['subscription_allocation_usd'])
            if value['status'] == 'failed-or-paused': self.assertEqual(value['actual_results']['actual_calls'], 2); self.assertEqual(value['review']['status'], 'preserved-failed-control')
        review['reviewer']['independent'] = True; self.save('reviewed.json', review)
        with self.assertRaises(AssertionError): release.record_review(self.source)

    def test_image_update_checks_source_before_atomic_configuration_replacement_and_cannot_replay(self):
        result = release.update_image(self.source); self.assertEqual(result['command_id'], 'synthetic-original-command')
        commands = self.r.ssm.call_args.args[0]; self.assertIn("trap 'systemctl start jumpserve-openclaw.service' EXIT", commands)
        self.assertIn('systemctl stop jumpserve-openclaw.service', commands)
        code = shlex.split(next(command for command in commands if command.startswith('/opt/jumpserve/python/bin/python -B -c ')))[-1]
        self.assertLess(code.index('assert all('), code.index('backup.write_bytes(raw)')); self.assertIn('temporary.replace(p)', code); self.assertIn('temporary.chmod(0o600)', code)
        self.r.auth_maintenance_guard.assert_called_once()
        with self.assertRaisesRegex(AssertionError, 'Inspect the retained command'): release.update_image(self.source)
        (self.source / 'image-update-command.json').unlink(); self.save('prepared.json', dict(image='not-a-content-hash'))
        with self.assertRaises(AssertionError): release.update_image(self.source)
        self.save('prepared.json', dict(image='sha256:' + 'b' * 64)); release.verify_worker(self.source)
        verify = '\n'.join(self.r.ssm.call_args.args[0]); self.assertIn('credential_contents_emitted=False', verify); self.assertIn('df -B1 /', verify)

    def freezing_fixture(self):
        names = ['bootstrap', '_execute', 'merge_tool_history', 'execution_contract', 'validate_calls', 'freeze_candidate', 'catalog']
        self.program = ''.join('def ' + name + '():\n    return None\n\n' for name in names).encode()
        runtime = self.back / 'research_workflow'; runtime.mkdir(parents=True)
        (runtime / 'experiment_builder.py').write_bytes(self.program)
        self.manifest['files'] = {'experiment_builder.py': digest(self.program)}; self.write('research-workflow-runtime.json', canonical(self.manifest))
        for name in ['experiment-builder.Dockerfile', 'tests/check_experiment_builder_linux.py', 'tests/prepare_builder_image.py', 'tests/prepare_builder_vendor.py', 'policies/builder-continuation-validation-v1.json', 'policies/builder-continuation-validation-v2.json']:
            path = runtime / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'# Synthetic retained dependency, never executed\n')
        self.producer = b'def put():\n    return None\n\ndef replay():\n    return None\n'
        self.write('bin/builder_continuation_qualification_host.py', self.producer)
        recorded = types.SimpleNamespace(claim=dict(id=identity('fixture-claim'), source_id=identity('fixture-source')), proposal={'synthetic_acquisition': True}, protocol=dict(hypotheses='Synthetic source consistency only', configurations=[{'details': {'test_config': {'text_artifact_id': 'synthetic-source-text'}}}]), data={('sources', identity('fixture-source')): {'id': identity('fixture-source')}}, bytes={'synthetic-source-text': canonical({'rows': [0, None]})})
        modules = {name: types.ModuleType(name) for name in ['autonomy_inputs', 'autonomy_methods', 'shared_campaigns', 'test_autonomy_methods', 'workflow']}
        modules['autonomy_inputs'].runner_contracts = lambda: {'scope': 'synthetic software control'}
        modules['autonomy_inputs'].protocol_contract = lambda: {'scope': 'frozen protocol'}
        modules['autonomy_methods'].contract = lambda: {'scope': 'no scientific finding'}
        modules['shared_campaigns'].identity = lambda proposal, source: (proposal, digest(canonical(proposal)))
        modules['test_autonomy_methods'].Recorded = lambda: copy.deepcopy(recorded)
        modules['workflow'].canonical = canonical; modules['workflow'].digest = digest
        self.enterContext(patch.dict(sys.modules, modules))
        original_path = list(sys.path); self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        def output(command, **options):
            if command == ['git', 'status', '--porcelain']: return ''
            if command == ['git', 'rev-parse', 'HEAD']: return self.manifest['source_revision'] + '\n'
            if command[:2] == ['git', 'show']: return self.program
            raise AssertionError(command)
        self.enterContext(patch.object(release.subprocess, 'check_output', side_effect=output))

    def test_freeze_retains_complete_source_and_adversarial_context_without_any_provider_call(self):
        self.freezing_fixture(); result = release.freeze(self.source)
        self.assertEqual(result['source_revision'], self.manifest['source_revision'])
        packet = json.loads((self.source / 'frozen.json').read_bytes())
        self.assertEqual(packet['assessment'], release.ASSESSMENT); self.assertIn('no human or independent validation', packet['review_kind'])
        self.assertIsNone(packet['native_context']['required_source_packet']['source_cells']['unavailable_cell'])
        self.assertIn('Ignore prior rules', packet['native_context']['required_source_packet']['untrusted_instructions'])
        self.assertFalse(packet['native_context']['required_answer']['main_campaign_executed'])
        self.assertEqual(packet['planning_context']['source_material']['text'], {'rows': [0, None]})
        raw = (self.source / 'candidate.zip').read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            for entry in json.loads(bundle.read('artifact-manifest.json')):
                original = bundle.read(entry['path']); self.assertEqual(digest(original), entry['sha256']); self.assertEqual(len(original), entry['bytes'])
            self.assertEqual(bundle.read('qualification.py'), self.producer)
        pointer = json.loads((self.source / 'candidate.json').read_bytes()); self.assertEqual(self.objects[pointer['path']], raw)
        self.assertEqual(pointer['retrieved_sha256'], digest(raw)); self.r.ssm.assert_not_called()
        self.r.instance.return_value = 'wrong-host'
        with self.assertRaises(AssertionError): release.freeze(self.source)

    def test_followup_inherits_only_a_hash_verified_complete_checkpoint_and_keeps_the_failed_control(self):
        self.freezing_fixture(); release.freeze(self.source); original_packet = json.loads((self.source / 'frozen.json').read_bytes())
        checkpoint = self.checkpoint(); evidence = archive({'original/native/checkpoint.zip': checkpoint, 'changed-input-control/calculation.py': b'assert hashlib.sha256(source).hexdigest() == SOURCE_SHA256\n', 'changed-input-control/stderr.bin': b'AssertionError: retained immutable source bytes differed\n'})
        self.save('host-status.json', {'evidence.json': {'path': 'qualification/original-evidence', 'sha256': digest(evidence)}})
        (self.source / 'evidence.zip').write_bytes(evidence)
        failed = dict(status='failed-or-paused', failure='Generated code failed the changed-input software control', live_provider_calls_issued=1, cases=[{'receipts': [dict(status='complete', checkpoint={'sha256': digest(checkpoint)})]}])
        self.save('live.json', failed)
        amended = self.base / '20261107T010000Z'; amended.mkdir()
        changed = self.program + b'# Non-executable correction; frozen execution functions unchanged\n'
        (self.back / 'research_workflow/experiment_builder.py').write_bytes(changed); self.manifest['files']['experiment_builder.py'] = digest(changed)
        self.write('research-workflow-runtime.json', canonical(self.manifest))
        for version in [2, 3]: self.write('docs/builder-continuation-release-amendment-v' + str(version) + '.json', canonical({'version': 'synthetic-amendment-v' + str(version)}))
        result = release.freeze(amended, self.source); self.assertEqual(result['source_revision'], self.manifest['source_revision'])
        packet = json.loads((amended / 'frozen.json').read_bytes())
        self.assertEqual(packet['followup_of'], self.source.name); self.assertEqual(packet['inherited_native']['original_native_provider_calls'], 1)
        self.assertEqual(packet['native_context'], original_packet['native_context']); self.assertEqual(packet['prompts'], original_packet['prompts'])
        self.assertEqual(packet['inherited_live_evidence']['changed_runtime_files'], ['experiment_builder.py'])
        self.assertEqual(json.loads((self.source / 'live.json').read_bytes()), failed)
        with zipfile.ZipFile(amended / 'candidate.zip') as bundle: self.assertEqual(bundle.read('inherited-native-checkpoint.zip'), checkpoint)

    def recovery_fixture(self):
        raw = canonical({'error': {'kind': 'context_overflow'}}); sha = digest(raw); path = release.ASSESSMENT + '/' + sha; self.objects[path] = raw
        for index in range(6):
            task = dict(id=identity('task-' + str(index)), claim_id=identity('claim-' + str(index)), stage='building', status='blocked', attempts=3, reason='Original stopped attempt', context={'builder_checkpoint': {'sha256': 'retained-checkpoint'}})
            self.tasks.append(task); artifact = identity('stdout-' + str(index)); self.artifacts[artifact] = dict(storage_path=path, sha256=sha, byte_count=len(raw))
            self.dispatches.append(dict(id=identity('dispatch-' + str(index)), task_id=task['id'], status='failed', provenance=dict(provider_calls=0, native_tool_cleanup=True, container_cleanup='confirmed', checkpoint=task['context']['builder_checkpoint'], artifacts=[dict(name='stdout.bin', id=artifact, sha256=sha)])))
        task = dict(id=identity('assessment-task'), claim_id=identity('assessment-claim'), stage='assessment', status='blocked', reason='Original KeyError before model admission', attempts=1, context={'original_zero': 0, 'missing': None})
        self.tasks.append(task); self.dispatches.append(dict(id=identity('assessment-dispatch'), task_id=task['id'], status='complete', provenance={}))

    def test_recovery_plan_requires_six_proved_zero_provider_failures_and_one_original_reader_failure(self):
        self.recovery_fixture()
        extras = [dict(id=identity('intake'), claim_id=None, status='blocked', stage='intake'), dict(id=identity('finished'), claim_id='claim', status='finished', stage='building'), dict(id=identity('no-history'), claim_id='claim', status='blocked', stage='building')]
        for status in ['unknown', 'queued', 'running']:
            task = dict(id=identity(status), claim_id='claim', status='blocked', stage='planning'); extras.append(task); self.dispatches.append(dict(id=identity(status + '-dispatch'), task_id=task['id'], status=status, provenance={}))
        task = dict(id=identity('not-zero'), claim_id='claim', status='blocked', stage='building'); extras.append(task); self.dispatches.append(dict(id=identity('not-zero-dispatch'), task_id=task['id'], status='failed', provenance={'provider_calls': 1}))
        self.tasks.extend(extras); before = copy.deepcopy((self.tasks, self.dispatches, self.workflow))
        result = release.recovery_plan(self.source); self.assertEqual(result['tasks'], 7); self.assertEqual(result['native_context_stops'], 6); self.assertEqual(result['excluded_unknown_planning'], 2)
        self.assertEqual((self.tasks, self.dispatches, self.workflow), before)
        plan = json.loads((self.source / 'recovery-plan.json').read_bytes()); self.assertEqual(len(plan['expected']), 7); self.assertEqual(len(list((self.source / 'recovery-proof').glob('*'))), 6)
        self.dispatches[0]['provenance']['provider_calls'] = 1
        with self.assertRaises(AssertionError): release.recovery_plan(self.source)

    def test_recovery_transaction_requires_the_exact_rollback_control_and_preserves_unknown_calls_and_limits(self):
        self.recovery_fixture(); release.recovery_plan(self.source)
        self.save('deployed-verified.json', dict(status='passed', source_revision=self.manifest['source_revision']))
        before = len(self.queries)
        with self.assertRaises(FileNotFoundError): release.recover(self.source, False)
        self.assertEqual(len(self.queries), before)
        control = release.recover(self.source, True); self.assertEqual(control['status'], 'rollback-verified')
        original = (self.source / 'recovery-dry-run.sql').read_bytes(); result = release.recover(self.source, False)
        committed = (self.source / 'recovery.sql').read_bytes()
        self.assertEqual(original, committed[:-len(b'commit;')] + b'rollback;'); self.assertEqual(result['status'], 'resumed')
        self.assertTrue(result['limits_preserved']); self.assertEqual(result['excluded_unknown'], 2)
        for required in ['pg_advisory_xact_lock', 'Original limits changed', 'Unknown original outcome cannot resume', 'continuation-release-resumed', 'Retained task changed', 'Confirmed stopped native checkpoint required']: self.assertIn(required, committed.decode())
        self.assertNotIn('set max_spend_cents', committed.decode()); self.assertNotIn('set attempts', committed.decode())
        release.recover(self.source, True); self.assertEqual((self.source / ('previous-' + digest(original) + '-recovery-dry-run.sql')).read_bytes(), original)
        self.save('recovery-dry-run.json', dict(status='rollback-verified', sql_sha256='0' * 64))
        with self.assertRaisesRegex(AssertionError, 'exact recovery transaction'): release.recover(self.source, False)

    def test_rejected_sql_retains_bounded_original_error_bytes_and_never_writes_a_success_receipt(self):
        self.recovery_fixture(); release.recovery_plan(self.source); self.save('deployed-verified.json', dict(status='passed', source_revision=self.manifest['source_revision']))
        for raw, expected in [(b'{"message":"Original rejection\\nUnpublished detail"}', 'Original rejection'), (b'[]', 'Original bounded error body retained privately.'), (b'{"message":""}', 'Original bounded error body retained privately.')]:
            def fail(sql, **options):
                try: raise release.urllib.error.HTTPError('https://private.invalid', 400, 'Synthetic rejection', {}, io.BytesIO(raw))
                except release.urllib.error.HTTPError as cause: raise RuntimeError('SQL adapter rejected') from cause
            with self.subTest(raw=raw), patch.object(self.r.admin, 'query', side_effect=fail), self.assertRaisesRegex(RuntimeError, re.escape('Recovery SQL rejected: ' + expected)):
                release.recover(self.source, True)
            self.assertEqual((self.source / ('recovery-error-' + digest(raw) + '.json')).read_bytes(), raw)
            self.assertFalse((self.source / 'recovery-dry-run.json').exists())
        with patch.object(self.r.admin, 'query', side_effect=RuntimeError('non-HTTP failure')), self.assertRaisesRegex(RuntimeError, 'non-HTTP failure'): release.recover(self.source, True)

    def test_operational_release_archives_original_failures_and_requires_all_seven_exact_recovery_events(self):
        self.recovery_fixture(); release.recovery_plan(self.source)
        plan = json.loads((self.source / 'recovery-plan.json').read_bytes())
        self.events = [dict(task_id=entry['task']['id'], details={'old_task': copy.deepcopy(entry['task'])}, created_at='retained-original-event-time') for entry in plan['expected']]
        for task_id in ['0254daab-507a-5790-a764-9803e0ac33e0', '6ebd38cd-b4df-5928-a63d-1130a859b25f']: self.tasks.append(dict(id=task_id, claim_id=identity(task_id), status='blocked', stage='planning', reason='Unknown original provider outcome', attempts=1, context={}))
        prior = self.base / '20261106T000000Z'; prior.mkdir(); self.save('failed-original.json', {'status': 'failed-or-paused'}, prior)
        self.frozen['followup_of'] = prior.name; self.save('frozen.json', self.frozen)
        self.save('recovery-result.json', dict(status='resumed', limits_preserved=True))
        browser = self.write('.test-artifacts/browser/report.json', canonical({'passed': True, 'synthetic': True})); self.write('.test-artifacts/browser/check.png', b'Synthetic retained image bytes; no visual qualification')
        verified = dict(status='passed', source_revision=self.manifest['source_revision'], browser_report=str(browser.relative_to(self.root))); self.save('deployed-verified.json', verified)
        self.write('.test-artifacts/openclaw-release/20261028T195636410854Z/cdk.log', b'Original retained local synthesis-lock failure\n')
        for folder, stamp in [('openclaw-release', '20261028T195600000000Z'), ('builder-production-v2', '20261029T000000000000Z'), ('openclaw-release', '20261001T000000000000Z')]: self.write('.test-artifacts/' + folder + '/' + stamp + '/receipt.json', canonical({'status': 'retained-synthetic-receipt'}))
        for name in ['bin/builder-continuation-release.py', 'bin/verify_assessment_methods_browser.mjs']: self.write(name, b'# Synthetic retained helper, never executed\n')
        self.write('docs/builder-continuation-production-status-v1.json', canonical({'status': 'pending'})); self.write('docs/builder-continuation-unit-notes.md', b'Synthetic review limits\n')
        result = release.record_release(self.source); self.assertFalse(result['scientific_completion']); pointer = result['archive']; self.assertFalse(pointer['public']); self.assertEqual(pointer['sha256'], pointer['retrieved_sha256'])
        with zipfile.ZipFile(io.BytesIO(self.objects[pointer['path']])) as retained:
            names = retained.namelist(); self.assertIn('preserved-local-synth-lock-failure.log', names)
            self.assertIn('qualification/' + prior.name + '/failed-original.json', names)
            self.assertNotIn('openclaw-release/20261001T000000000000Z/receipt.json', names)
            report = json.loads(retained.read('release-report.json')); self.assertFalse(report['scientific_completion']); self.assertIsNone(report['measured_charges_usd'])
            self.assertEqual(report['recovery']['workflow']['committed_cents'], self.workflow['committed_cents'])
            for entry in json.loads(retained.read('artifact-manifest.json')): self.assertEqual(digest(retained.read(entry['path'])), entry['sha256'])
        status = json.loads((self.root / 'docs/builder-continuation-production-status-v1.json').read_bytes()); self.assertEqual(status['recovery']['resumed'], 7); self.assertEqual(status['recovery']['excluded_unknown'], 2)
        self.events[0]['details']['old_task']['attempts'] += 1
        with self.assertRaises(AssertionError): release.record_release(self.source)

    def test_cli_routes_keep_dispatch_and_recovery_arguments_fixed_and_retain_failures(self):
        routes = {'freeze': ('freeze', None), 'freeze-followup': ('freeze', self.source), 'status': ('status', None), 'collect-status': ('collect_status', None), 'collect': ('collect', None), 'record-review': ('record_review', None), 'record-release': ('record_release', None), 'update-image': ('update_image', None), 'verify-worker': ('verify_worker', None), 'plan-recovery': ('recovery_plan', None), 'dry-run-recovery': ('recover', True), 'recover': ('recover', False)}
        for mode, (name, argument) in routes.items():
            with self.subTest(mode=mode), patch.object(release, name, return_value={'retained': True, 'cases': [{'private': True}]}) as action, patch.object(sys, 'argv', ['builder-continuation-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as output:
                release.main()
            value = json.loads(output.getvalue()); self.assertEqual(value['status'], 'complete'); self.assertTrue((Path(value['directory']) / 'receipt.json').exists())
            if name == 'freeze': self.assertEqual(action.call_args.args[1], argument)
            elif name == 'recover': self.assertEqual(action.call_args.args, (self.source, argument))
            else: action.assert_called_once_with(self.source)
            if mode == 'collect': self.assertNotIn('cases', value['result'])
        with patch.object(release, 'dispatch', return_value={'submitted': True}) as dispatch, patch.object(sys, 'argv', ['builder-continuation-release.py', 'native']), contextlib.redirect_stdout(io.StringIO()): release.main()
        dispatch.assert_called_once_with(self.source, 'native')
        with patch.object(release, 'dispatch', side_effect=RuntimeError('Synthetic dispatch failure')), patch.object(sys, 'argv', ['builder-continuation-release.py', 'native']), contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaisesRegex(RuntimeError, 'Synthetic dispatch failure'): release.main()
        failed = json.loads(output.getvalue()); self.assertEqual(failed['status'], 'failed'); self.assertEqual(json.loads((Path(failed['directory']) / 'receipt.json').read_bytes())['reason'], 'Synthetic dispatch failure')
        self.recovery_fixture()
        with patch.object(sys, 'argv', ['builder-continuation-release.py', 'inspect']), contextlib.redirect_stdout(io.StringIO()) as output: release.main()
        value = json.loads(output.getvalue()); self.assertEqual(len(value['result']['tasks']), 7)
        self.assertNotIn('context', value['result']['tasks'][0]); self.assertNotIn('provenance', value['result']['tasks'][0])


if __name__ == '__main__': unittest.main()
