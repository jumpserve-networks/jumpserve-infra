"""Fixed read-only diagnostics retain hash-verified synthetic incident originals."""
import contextlib
import copy
import gzip
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import re
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid5
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/inspect-builder-stall-4055396e.py'
STUDY = '4055396e-35c0-4962-ba39-cf23e443ad8d'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def uid(name): return str(uuid5(UUID(STUDY), 'synthetic-unit:' + name))
def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


class BuilderDiagnosticCapture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='builder-capture-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'docs').mkdir()
        for name in ['assessment-4055396e-builder-stall-protocol-v1.json', 'autonomy-completion-protocol-v1.json']:
            (self.root / 'docs' / name).write_bytes((ROOT / 'docs' / name).read_bytes())
        self.blobs, self.artifacts, self.queries = {}, {}, []
        self.release = types.SimpleNamespace(save=lambda path, value: path.write_bytes(encoded(value)))
        self.r = types.SimpleNamespace(target=Mock(return_value={'synthetic_target_verified': True}),
            stamp=lambda: '2026-11-01T00:00:00Z', sha=sha,
            admin=types.SimpleNamespace(literal=lambda value: "'" + str(value).replace("'", "''") + "'", query=Mock(side_effect=self.query)))
        self.m = types.SimpleNamespace(storage=Mock(side_effect=lambda path: self.blobs[path]))
        self.original = types.ModuleType('synthetic_original_inspector')
        self.original.r, self.original.m, self.original.release, self.original.STUDY = self.r, self.m, self.release, STUDY
        self.module = self.load(); self.module.ROOT = self.root
        self.fixture()

    def specification(self, original, label, path, *args, **kwargs):
        if Path(path) != ROOT / 'bin/inspect-assessment-4055396e.py': return original(label, path, *args, **kwargs)
        module = self.original
        class Loader:
            def create_module(self, spec): return module
            def exec_module(self, module): pass
        return importlib.machinery.ModuleSpec(label, Loader())

    def load(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)):
            spec = original('builder_diagnostic_capture_unit', SOURCE)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def artifact(self, label, raw, name=None):
        identity = uid('artifact-' + label); path = 'synthetic/' + identity
        self.blobs[path] = raw
        self.artifacts[identity] = dict(storage_path=path, sha256=sha(raw), byte_count=len(raw))
        return dict(id=identity, name=name or label, sha256=sha(raw), byte_count=len(raw))

    def checkpoint(self, compressed=False, bad_records=False):
        history = encoded([dict(type='function_call', name='read', arguments='{"path":"project/source.py"}')])
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            if compressed:
                zipped = gzip.compress(history, mtime=0)
                index = dict(compressed_sha256=sha(zipped), sha256=sha(history), bytes=len(history), records=2 if bad_records else 1)
                archive.writestr('native-tool-history.json', encoded(index))
                archive.writestr('native-tool-history.json.gz', zipped)
            else: archive.writestr('native-tool-history.json', history)
            archive.writestr('project/source.py', b'# passive original; never executed\n')
        return self.artifact('checkpoint', output.getvalue())

    def fixture(self, compressed=False, bad_records=False):
        checkpoint = self.checkpoint(compressed, bad_records)
        receipt = self.artifact('receipt', b'{"provider_calls":0,"zero":0}', 'receipt.json')
        stdout = self.artifact('stdout', b'Original diagnostics\x00\xff', 'stdout.bin')
        ignored = self.artifact('ignored', b'original ignored bytes', 'unrelated.bin')
        small = self.artifact('small-request', b'{"input":[]}', 'native-request-' + 'a' * 64 + '.json')
        large = self.artifact('large-request', b'{"input":[{"role":"user","content":"retained"}]}', 'native-request-' + 'b' * 64 + '.json')
        self.tasks, self.dispatches, self.calls = [], {}, {}
        for index in range(5):
            task = dict(id=uid('task-' + str(index)), claim_id=uid('claim-' + str(index)), context=dict(
                builder_checkpoint={'artifact_id': checkpoint['id'], 'sha256': checkpoint['sha256']}, repair_progress={'id': uid('repair-' + str(index))}))
            self.tasks.append(task)
            request = encoded({'builder': {'context': {'retained': True}}, 'zero': 0}).decode()
            dispatch = dict(id=uid('dispatch-' + str(index)), study_id=STUDY, task_id=task['id'], status='complete', request_raw=request,
                request_sha256=sha(request.encode()), provenance=dict(artifacts=copy.deepcopy([receipt, stdout, ignored, small, large]),
                checkpoint={'artifact_id': checkpoint['id'], 'sha256': checkpoint['sha256']}))
            self.dispatches[task['id']] = [dispatch]
            self.calls[task['id']] = [dict(id=uid('call-' + str(index)), task_id=task['id'], request_artifact_id=small['id'], request_sha256=small['sha256']),
                                       dict(id=uid('empty-call-' + str(index)), task_id=task['id'])]
        self.boundary = dict(id='6e5b884a-3322-508b-ae00-c01df7ec9307', study_id=STUDY, status='failed',
            request_raw='{"original":true}', request_sha256=sha(b'{"original":true}'),
            provenance={'provider_calls': 0, 'artifacts': [receipt, stdout, ignored]})

    def query(self, sql):
        self.queries.append(sql)
        self.assertTrue(sql.startswith('select '), 'Diagnostic capture must be read-only.')
        if ' from research_artifacts ' in sql:
            identity = re.search(r" and id='([^']+)'::uuid", sql).group(1)
            return [copy.deepcopy(self.artifacts[identity])]
        if ' from research_autonomy_workflows ' in sql: return [{'record': {'study_id': STUDY, 'committed_cents': 0}}]
        if ' from research_autonomy_tasks ' in sql: return [{'record': copy.deepcopy(row)} for row in self.tasks]
        if ' from research_model_dispatches ' in sql:
            if 'task_id=' not in sql: return [{'record': copy.deepcopy(self.boundary)}]
            task = re.search(r"task_id='([^']+)'::uuid", sql).group(1)
            return [{'record': copy.deepcopy(row)} for row in self.dispatches[task]]
        if ' from research_autonomy_turns ' in sql: return [{'record': {'status': 'retained-unknown'}}]
        if ' from research_builder_calls ' in sql:
            task = re.search(r"task_id='([^']+)'::uuid", sql).group(1)
            return [{'record': copy.deepcopy(row)} for row in self.calls[task]]
        if ' from research_autonomy_repairs ' in sql: return [{'record': {'state': 'original-state'}}]
        if ' from research_autonomy_repair_events ' in sql: return [{'record': {'kind': 'original-event'}}]
        raise AssertionError('Unexpected synthetic read: ' + sql)

    def call(self, operation):
        output = io.StringIO()
        with contextlib.redirect_stdout(output): getattr(self.module, operation)()
        return json.loads(output.getvalue())

    def capture(self):
        result = self.call('main'); out = Path(result['directory'])
        return result, out, json.loads((out / 'capture.json').read_bytes())

    def test_capture_hash_verifies_and_deduplicates_originals_without_executing_checkpoint_content(self):
        result, out, data = self.capture()
        self.assertEqual(result['tasks'], 5); self.assertEqual(result['dispatches'], 5); self.assertEqual(result['native_calls'], 10)
        self.assertEqual(result['unavailable_artifacts'], [])
        self.assertEqual(self.m.storage.call_count, result['verified_artifacts'])
        self.assertEqual(data['new_model_calls'], 0); self.assertEqual(data['production_writes'], 0)
        self.assertIn('substantive review not implied', data['review_status'])
        self.assertEqual(data['workflow'][0]['record']['committed_cents'], 0)
        for entry in data['artifact_reads']:
            raw = (out / entry['file']).read_bytes()
            self.assertEqual(sha(raw), entry['expected_sha256']); self.assertEqual(len(raw), entry['bytes'])
        for task in self.tasks:
            history = json.loads((out / (task['id'] + '-derived-history.json')).read_bytes())
            self.assertEqual(history[0]['name'], 'read')
        manifest = json.loads((out / 'manifest.json').read_bytes())
        self.assertTrue(all(sha((out / entry['file']).read_bytes()) == entry['sha256'] for entry in manifest))

    def test_compressed_history_is_verified_before_derivation_and_bad_record_count_stops_capture(self):
        self.fixture(compressed=True)
        _result, out, data = self.capture()
        self.assertTrue(any(member['path'] == 'native-tool-history.json.gz' for member in data['tasks'][0]['examined_checkpoint_inventory']))
        self.assertEqual(len(json.loads((out / (self.tasks[0]['id'] + '-derived-history.json')).read_bytes())), 1)
        self.fixture(compressed=True, bad_records=True)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AssertionError): self.module.main()

    def test_missing_or_unavailable_checkpoints_remain_unexamined_without_invented_history(self):
        for missing in ['absent', 'unavailable']:
            self.fixture()
            task = self.tasks[0]
            checkpoint = task['context']['builder_checkpoint']
            if missing == 'absent': del task['context']['builder_checkpoint']
            else: self.blobs.pop(self.artifacts[checkpoint['artifact_id']]['storage_path'])
            _result, out, data = self.capture()
            row = next(row for row in data['tasks'] if row['id'] == task['id'])
            self.assertNotIn('examined_checkpoint_inventory', row)
            self.assertFalse((out / (task['id'] + '-derived-history.json')).exists())

    def test_unavailable_or_oversized_originals_remain_unavailable_with_a_retained_failure_record(self):
        for failure in ['size', 'hash', 'read']:
            self.fixture()
            original = self.dispatches[self.tasks[0]['id']][0]['provenance']['artifacts'][1]
            record = self.artifacts[original['id']]
            if failure == 'size': record['byte_count'] = 64000001
            elif failure == 'hash': self.blobs[record['storage_path']] = b'changed bytes'
            else: del self.blobs[record['storage_path']]
            result, _out, data = self.capture()
            unavailable = [row for row in data['artifact_reads'] if row['id'] == original['id']]
            with self.subTest(failure=failure):
                self.assertTrue(unavailable); self.assertTrue(all(row['status'] == 'unavailable' for row in unavailable))
                self.assertTrue(result['unavailable_artifacts'])
                self.assertEqual(data['production_writes'], 0)

    def test_supplement_selects_largest_exact_original_per_parent_and_retains_repair_events(self):
        self.capture()
        result = self.call('supplement'); out = Path(result['directory'])
        report = json.loads((out / 'supplement.json').read_bytes())
        self.assertEqual(len(report['requests']), 5); self.assertEqual(len(report['repairs']), 5); self.assertEqual(len(report['events']), 5)
        self.assertEqual(result['model_calls'], 0); self.assertEqual(result['writes'], 0)
        for entry in report['requests']:
            raw = (out / entry['file']).read_bytes()
            self.assertIn(b'retained', raw); self.assertEqual(sha(raw), entry['sha256'])
            parent = self.dispatches[entry['task_id']][0]
            self.assertEqual(entry['dispatch_id'], parent['id'])

    def test_matched_checkpoint_delivery_uses_verified_cached_bytes_or_retrieves_the_bound_original(self):
        _result, capture_path, data = self.capture()
        self.call('supplement')
        for use_cache in [True, False]:
            if not use_cache:
                checkpoint_id = self.tasks[0]['context']['builder_checkpoint']['artifact_id']
                data['artifact_reads'] = [row for row in data['artifact_reads'] if row['id'] != checkpoint_id]
                (capture_path / 'capture.json').write_bytes(encoded(data))
                supplement = sorted((self.root / '.test-artifacts/assessment-4055396e').glob('*/supplement.json'))[-1]
                value = json.loads(supplement.read_bytes()); value['source_sha256'] = sha((capture_path / 'capture.json').read_bytes())
                supplement.write_bytes(encoded(value))
            self.m.storage.reset_mock()
            result = self.call('matched_checkpoints')
            report = json.loads((Path(result['directory']) / 'matched-checkpoints.json').read_bytes())
            self.assertEqual(len(report['checkpoints']), 5)
            self.assertEqual(self.m.storage.call_count, 0 if use_cache else 5)
            for entry in report['checkpoints']:
                raw = (Path(result['directory']) / entry['file']).read_bytes()
                self.assertEqual(len(raw), entry['bytes']); self.assertEqual(sha(raw), entry['sha256'])

    def test_planner_boundary_requires_zero_provider_calls_and_hash_verified_permitted_originals(self):
        result = self.call('planner_boundary'); out = Path(result['directory'])
        report = json.loads((out / 'retrieval.json').read_bytes())
        self.assertEqual([row['name'] for row in report['artifacts']], ['receipt.json', 'stdout.bin'])
        self.assertEqual(report['provider_calls'], 0); self.assertEqual(report['production_writes'], 0)
        self.assertIn('completeness not implied', report['review_status'])
        for row in report['artifacts']:
            self.assertEqual(sha((out / row['name']).read_bytes()), row['retrieved_sha256'])
        self.boundary['provenance']['provider_calls'] = 1
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AssertionError): self.module.planner_boundary()

    def test_cli_accepts_only_fixed_read_only_modes_and_checks_target_before_file_or_service_work(self):
        class TargetUnavailable(Exception): pass
        self.r.target.side_effect = TargetUnavailable('Synthetic target verification unavailable')
        original = importlib.util.spec_from_file_location
        for args in [[], ['--requests'], ['--matched-checkpoints'], ['--planner-boundary'], ['arbitrary']]:
            with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *a, **kw: self.specification(original, *a, **kw)), \
                    patch.object(sys, 'argv', [str(SOURCE), *args]):
                with self.assertRaises(SystemExit if args == ['arbitrary'] else TargetUnavailable): runpy.run_path(str(SOURCE), run_name='__main__')
        self.assertEqual(self.queries, []); self.m.storage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
