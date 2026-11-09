"""Importer orchestration with private temporary evidence and synthetic service adapters.

The crosswalk and record schema belong to the backend's separate unit suite;
these tests exercise transport, completeness, identity, ownership and publication.
"""
import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import random
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAMP = '2026-11-01T00:00:00+00:00'


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(raw): return hashlib.sha256(raw).hexdigest()
def identity(study, name): return str(uuid.uuid5(uuid.UUID(study), name))


class ArchivedAssessmentImport(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='archived-import-unit-'); self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name).resolve(); self.root = self.workspace / 'jumpserve-infra'; self.backend = self.workspace / 'jumpserve-back-end'
        self.out = self.root / '.test-artifacts/archived-assessments-v1'; self.out.mkdir(parents=True)
        self.workflow = types.ModuleType('workflow'); self.workflow.now = lambda: STAMP; self.workflow.digest = digest; self.workflow.canonical = canonical
        self.workflow.validate_record = MagicMock(side_effect=lambda kind, value: value)
        self.archive = types.ModuleType('archive'); self.archive.VERSION = 'synthetic-import-unit-v1'; self.archive.REVIEWER = {'type': 'AI', 'independence': 'Synthetic unit fixture'}
        self.archive.uid = identity; self.archive.build = MagicMock(side_effect=self.build)
        self.store = types.ModuleType('store')
        for name in ['rpc', 'rows', 'owns', 'artifact', 'artifact_bytes', 'append', 'snapshot']:
            setattr(self.store, name, MagicMock(side_effect=AssertionError('Unexpected storage operation: ' + name)))
        spec = importlib.util.spec_from_file_location('archived_import_unit', ROOT / 'bin/import-archived-assessments.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'workflow': self.workflow, 'archive': self.archive, 'store': self.store}), patch.object(sys, 'path', list(sys.path)):
            spec.loader.exec_module(self.module)
        self.enterContext(patch.object(self.module, 'ROOT', self.root)); self.enterContext(patch.object(self.module, 'BACKEND', self.backend)); self.enterContext(patch.object(self.module, 'OUT', self.out))
        self.definitions = copy.deepcopy(self.module.MODULES)
        self.modules = {key: dict(value, tables=['sources', 'summaries']) for key, value in self.definitions.items() if key in ['propagation-delay-study', 'ipv6-dns-study']}
        self.enterContext(patch.object(self.module, 'MODULES', self.modules))
        self.target = {'aws_account': 'fixture-account', 'supabase_project': 'fixture-project'}
        self.guard = MagicMock(); self.guard.targets.return_value = self.target; self.guard.admin.PROJECT_REF = 'fixture-project'
        self.guard.verify.return_value = {'passed': True}
        self.guard.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"
        self.enterContext(patch.object(self.module, 'guard', self.guard))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.protocol = b'Synthetic frozen import protocol\n'
        self.write(self.root / 'docs/archived-assessment-import-protocol-v1.md', self.protocol)
        for name in ['archived-assessment-import-serialization-v2.md', 'archived-assessment-import-serialization-v3.md']:
            self.write(self.root / 'docs' / name, b'Synthetic serialization contract\n')
        self.implementation = b'# synthetic executed implementation\n'; self.write(self.backend / 'research_workflow/archive.py', self.implementation)
        for name in ['primary.pdf', 'PRIMARY_READING.md', 'RESULTS.md']:
            self.write(self.backend / 'experiments/nines2026_delay_equalization' / ('literature/primary.pdf' if name == 'primary.pdf' else name), b'Synthetic historical original ' + name.encode())
        self.table_rows = {definition['prefix'] + suffix: ['{"id":"fixture","value":0.1234567890123456789}'] for definition in self.modules.values() for suffix in definition['tables']}
        self.counts = [{'relation': key, 'records': len(rows)} for key, rows in self.table_rows.items()]
        self.old_studies = [dict(id=str(uuid.uuid4()), claims=4, runs=5, published_version=1)]
        self.guard.admin.query.side_effect = self.query
        self.module.save('inventory-v1.json', dict(counts=self.counts, studies=self.old_studies))
        self.browser = self.workspace / 'jumpserve-front-end/.test-artifacts/archived-assessments/20261101/browser-report.json'
        self.write(self.browser, canonical(dict(mode='exact prepared component preview', passed=True, checks=[{}] * 20)))

    def write(self, path, raw): path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    def query(self, sql, **options):
        if 'current_database()' in sql: return [{'database': 'fixture-database'}]
        if 'information_schema.columns' in sql: return [dict(table_name=key, column_name='id', data_type='text') for key in self.table_rows]
        if 'count(*) as records' in sql: return copy.deepcopy(self.counts)
        if 'research_studies' in sql: return copy.deepcopy(self.old_studies)
        if sql.startswith('select to_jsonb(t)::text as row from public.'):
            name = sql.split('from public.', 1)[1].split()[0]; return [{'row': raw} for raw in self.table_rows[name]]
        if sql.startswith('select public.research_append_bundle'): return [{'receipt': 'fixture'}]
        raise AssertionError('Unexpected SQL: ' + sql)

    def build(self, path, definition, backend, protocol_sha):
        native = json.loads(path.read_bytes()); module = native['module']; study = str(uuid.uuid5(uuid.NAMESPACE_URL, module))
        source, claim, run = [identity(study, name) for name in ['source', 'claim', 'run']]
        records = [dict(kind='sources', record=dict(id=source, citation='Synthetic original')),
                   dict(kind='claims', record=dict(id=claim, source_id=source, description='Synthetic selected claim')),
                   dict(kind='runs', record=dict(id=run, provenance={'implementation_sha256': digest(self.implementation)}, started_at=STAMP)),
                   dict(kind='measurements', record=dict(id=identity(study, 'measurement'), run_id=run, value='0.000125'))]
        return dict(study_id=study, input_sha256=digest(path.read_bytes()), provenance={'import_protocol_sha256': protocol_sha},
                    paper={'origin_module': module}, original_artifact=path.name, records=records,
                    coverage={kind: 1 for kind in ['sources', 'claims', 'runs', 'measurements']}, claim_labels={'untested': 1})

    def prepare(self):
        self.module.export(); self.module.prepare(); return self.module.prepared()

    def connected(self):
        return self.enterContext(patch.object(self.module, 'connect', return_value=(self.target, 'fixture-owner')))

    def stored(self, values):
        snapshots = {}
        for item, value in values:
            snapshot = {'coverage': value['coverage'], 'records': {kind: [] for kind in value['coverage']}}
            for entry in value['records']: snapshot['records'][entry['kind']].append(copy.deepcopy(entry['record']))
            snapshots[value['study_id']] = snapshot
        self.store.snapshot.side_effect = lambda study, **options: snapshots[study]
        return snapshots

    def test_retained_evidence_is_immutable_and_nonfinite_json_is_never_saved(self):
        self.module.save('evidence.json', {'zero': 0}); first = (self.out / 'evidence.json').read_bytes()
        self.module.save('evidence.json', {'zero': 0}); self.assertEqual((self.out / 'evidence.json').read_bytes(), first)
        with self.assertRaisesRegex(RuntimeError, 'Retained evidence already exists'): self.module.save('evidence.json', {'zero': 1})
        with self.assertRaises(ValueError): self.module.save('nonfinite.json', {'value': float('nan')})
        self.assertFalse((self.out / 'nonfinite.json').exists())

    def test_inspection_checks_targets_and_uses_only_the_fixed_scientific_relation_inventory(self):
        # Inventory snapshots have immutable names; inspect each mode in its own version.
        (self.out / 'inventory-v1.json').unlink(); self.module.inspect()
        self.guard.targets.assert_called_once(); self.guard.verify.assert_called_once_with(self.target, queue=True, preparation=True)
        self.module.inspect(supabase_only=True)
        snapshot = json.loads((self.out / 'inventory-supabase-v1.json').read_bytes())
        self.assertTrue(snapshot['read_only']); self.assertIsNone(snapshot['targets']['aws_account'])
        for table in ['private_owner_rows', 'delay_study_unsafe;drop']:
            self.guard.admin.query.side_effect = lambda sql: [dict(table_name=table)] if 'information_schema' in sql else []
            with self.assertRaisesRegex(RuntimeError, 'Unexpected legacy relation'): self.module.inspect()

    def test_export_keeps_decimal_tokens_and_all_record_counts_and_reuses_identical_retained_exports(self):
        self.module.export(); manifest = json.loads((self.out / 'native-manifest-v1.json').read_bytes())
        self.assertEqual(len(manifest['originals']), 2)
        for item in manifest['originals']:
            raw = (self.out / item['path']).read_bytes(); value = json.loads(raw)
            self.assertEqual(value['data']['summaries'][0]['value'], '0.1234567890123456789')
            self.assertEqual(digest(raw), item['sha256']); self.assertEqual(len(raw), item['byte_count'])
        with patch.object(self.module.time, 'monotonic', return_value=0):
            (self.out / 'native-manifest-v1.json').unlink(); self.module.export()
        self.assertEqual(self.archive.build.call_count, 0)

    def test_export_rejects_changed_native_coverage_and_oversized_retained_artifacts(self):
        key = next(iter(self.table_rows)); self.table_rows[key] = []
        with self.assertRaisesRegex(RuntimeError, 'coverage changed during export'): self.module.export()
        self.table_rows[key] = ['{"id":"fixture"}']
        first = next(iter(self.modules)); self.write(self.out / (first + '-native-v1.json'), canonical({'data': {}, 'padding': 'x' * 10_000_000}))
        with self.assertRaisesRegex(RuntimeError, 'exceeds the frozen budget'): self.module.export()

    def test_preparation_validates_hashes_schema_foreign_keys_and_versioned_projections(self):
        values = self.prepare(); self.assertEqual(len(values), 2)
        self.assertEqual({item['prepared_path'].split('-prepared-')[1] for item, _ in values}, {'v2.json', 'v3.json'})
        self.assertEqual(self.archive.build.call_count, 2); self.module.prepare(); self.assertEqual(self.archive.build.call_count, 2)
        self.assertEqual(self.workflow.validate_record.call_count, 16)
        self.write(self.root / 'docs/archived-assessment-import-protocol-v1.md', b'changed protocol')
        with self.assertRaisesRegex(RuntimeError, 'Import protocol changed'): self.module.prepare()
        with self.assertRaisesRegex(RuntimeError, 'Declared protocol hash changed'): self.module.prepared()

    def test_preparation_rejects_changed_input_foreign_keys_duplicate_ids_and_stale_prepared_metadata(self):
        self.module.export(); manifest = json.loads((self.out / 'native-manifest-v1.json').read_bytes()); original = manifest['originals'][0]
        path = self.out / original['path']; raw = path.read_bytes(); path.write_bytes(raw + b' ')
        with self.assertRaisesRegex(RuntimeError, 'Native export hash changed'): self.module.prepare()
        path.write_bytes(raw)
        valid = self.build(path, {}, self.backend, digest(self.protocol))
        for change, message in [('duplicate', 'Duplicate shared'), ('foreign', 'foreign-key identity'), ('input', 'another input'), ('protocol', 'another input')]:
            value = copy.deepcopy(valid)
            if change == 'duplicate': value['records'][1]['record']['id'] = value['records'][0]['record']['id']
            elif change == 'foreign': value['records'][1]['record']['source_id'] = 'unavailable-id'
            elif change == 'input': value['input_sha256'] = 'wrong'
            else: value['provenance']['import_protocol_sha256'] = 'wrong'
            prepared = self.out / (original['module'] + '-prepared-v2.json'); self.write(prepared, canonical(value))
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, message): self.module.prepare()
            prepared.unlink()
        self.workflow.validate_record.side_effect = ValueError('schema rejected')
        with self.assertRaisesRegex(ValueError, 'schema rejected'): self.module.prepare()

    def test_prepared_reads_reject_changed_projection_or_study_identity(self):
        values = self.prepare(); item, value = values[0]; path = self.out / item['prepared_path']; raw = path.read_bytes()
        path.write_bytes(raw + b' ')
        with self.assertRaisesRegex(RuntimeError, 'projection hash differs'): self.module.prepared()
        path.write_bytes(raw)
        manifest = json.loads((self.out / 'prepared-manifest-v3.json').read_bytes())
        manifest['studies'][0]['study_id'] = 'different'
        (self.out / 'prepared-manifest-v3.json').write_bytes(canonical(manifest))
        with self.assertRaisesRegex(RuntimeError, 'study identity differs'): self.module.prepared()

    def test_connect_uses_private_process_credentials_and_requires_one_previously_authorized_owner(self):
        self.write(self.workspace / 'jumpserve-front-end/.env.local', b'KEEP=fixture\nNEXT_PUBLIC_SUPABASE_ANON_KEY="fixture-public"\n')
        self.store.rows.side_effect = None; self.store.rows.return_value = [{'owner_id': 'fixture-owner'}]
        with patch.dict(os.environ, {}, clear=True), patch.object(self.module.subprocess, 'check_output', return_value=b'{"SecretString":"fixture-private"}') as aws:
            self.assertEqual(self.module.connect(), (self.target, 'fixture-owner'))
            self.assertEqual(os.environ['SUPABASE_ANON_KEY'], 'fixture-public'); self.assertEqual(os.environ['SUPABASE_SERVICE_ROLE_KEY'], 'fixture-private')
            self.assertNotIn('fixture-private', repr(aws.call_args.args))
            self.store.rows.return_value = []
            with self.assertRaisesRegex(RuntimeError, 'owner is unavailable'): self.module.connect()

    def test_browser_report_requires_complete_successful_prepublication_checks(self):
        self.assertEqual(self.module.browser_report()[0], self.browser)
        self.write(self.browser, canonical(dict(mode='exact prepared component preview', passed=True, checks=[])))
        with self.assertRaisesRegex(RuntimeError, 'coverage incomplete'): self.module.browser_report()
        self.write(self.browser, canonical(dict(mode='public production', passed=True, checks=[{}] * 26)))
        with self.assertRaisesRegex(RuntimeError, 'have not passed'): self.module.browser_report()

    def test_apply_preserves_original_bytes_and_uses_bounded_atomic_batches_without_publication(self):
        values = self.prepare(); self.connected(); self.store.rpc.side_effect = None; self.store.owns.side_effect = None; self.store.owns.return_value = True
        def artifact(study, actor, raw, id, media, provenance): return dict(id=id, sha256=digest(raw), byte_count=len(raw), media_type=media, provenance=provenance)
        self.store.artifact.side_effect = artifact
        self.module.apply(); receipt = json.loads((self.out / 'persistence-v1.json').read_bytes())
        self.assertFalse(receipt['published']); self.assertFalse(receipt['deployment']); self.assertEqual(len(receipt['studies']), 2)
        self.assertEqual({call.args[4] for call in self.store.artifact.call_args_list}, {'application/pdf', 'text/markdown', 'application/json', 'text/x-python'})
        self.assertTrue(all(call.args[0] == 'research_create_study' for call in self.store.rpc.call_args_list))
        writes = [call for call in self.guard.admin.query.call_args_list if call.kwargs.get('read_only') is False]
        self.assertEqual(len(writes), 2); self.assertTrue(all('research_append_bundle' in call.args[0] for call in writes))
        self.assertEqual(len((self.out / 'write-progress-v1.jsonl').read_text().splitlines()), 2)

    def test_apply_stops_on_ownership_or_missing_executed_source_before_artifact_uploads(self):
        self.prepare(); self.connected(); self.store.rpc.side_effect = None; self.store.owns.side_effect = None; self.store.owns.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'ownership mismatch'): self.module.apply()
        self.store.artifact.assert_not_called(); self.store.owns.return_value = True
        (self.backend / 'research_workflow/archive.py').unlink()
        with self.assertRaisesRegex(RuntimeError, 'implementation bytes unavailable'): self.module.apply()
        self.store.artifact.assert_not_called()

    def test_private_and_public_verification_compare_decimal_values_timestamp_instants_and_original_hashes(self):
        values = self.prepare(); self.connected(); snapshots = self.stored(values)
        artifact = dict(id='fixture-artifact', sha256=digest(b'original'), byte_count=8)
        self.module.save('persistence-v1.json', {'studies': [dict(study_id=value['study_id'], artifacts=[artifact]) for _, value in values]})
        self.store.artifact_bytes.side_effect = None; self.store.artifact_bytes.return_value = b'original'
        for snapshot in snapshots.values():
            snapshot['records']['measurements'][0]['value'] = .000125
            snapshot['records']['runs'][0]['started_at'] = '2026-10-31T20:00:00-04:00'
        for public in [False, True]: self.module.verify(public=public)
        report = json.loads((self.out / 'public-verification-v1.json').read_bytes())
        self.assertTrue(report['public_anonymous_read']); self.assertTrue(report['passed'])
        self.assertTrue(report['studies'][0]['timestamp_serializations'][0]['same_instant'])
        self.assertEqual(self.store.snapshot.call_args.kwargs, {'owner': False})

    def test_verification_rejects_missing_records_changed_counts_values_times_originals_or_prior_history(self):
        values = self.prepare(); self.connected(); snapshots = self.stored(values)
        self.module.save('persistence-v1.json', {'studies': [dict(study_id=value['study_id'], artifacts=[dict(id='fixture-artifact', sha256=digest(b'original'), byte_count=8)]) for _, value in values]})
        self.store.artifact_bytes.side_effect = None; self.store.artifact_bytes.return_value = b'original'
        study = values[0][1]['study_id']; baseline = copy.deepcopy(snapshots[study])
        for kind, message in [('missing', 'snapshot missing'), ('count', 'coverage differs'), ('numeric', 'numerical value'), ('time', 'timestamp instant'), ('naive', 'timestamp instant'), ('field', 'Stored field'), ('original', 'artifact identity')]:
            snapshots[study] = copy.deepcopy(baseline); current = snapshots[study]
            if kind == 'missing': snapshots[study] = None
            elif kind == 'count': current['coverage'] = dict(current['coverage'], claims=2)
            elif kind == 'numeric': current['records']['measurements'][0]['value'] = 1
            elif kind == 'time': current['records']['runs'][0]['started_at'] = '2026-11-02T00:00:00+00:00'
            elif kind == 'naive': current['records']['runs'][0]['started_at'] = '2026-11-01T00:00:00'
            elif kind == 'field': current['records']['claims'][0]['description'] = 'changed'
            else: self.store.artifact_bytes.return_value = b'changed'
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, message): self.module.verify()
            self.store.artifact_bytes.return_value = b'original'
        snapshots[study] = baseline; self.counts[0]['records'] += 1
        with self.assertRaisesRegex(RuntimeError, 'native relation counts changed'): self.module.verify()
        self.counts[0]['records'] -= 1; self.old_studies[0]['runs'] += 1
        with self.assertRaisesRegex(RuntimeError, 'Pre-existing study coverage'): self.module.verify()

    def test_publish_requires_verified_storage_native_pages_and_browser_checks_and_preserves_review_limits(self):
        values = self.prepare(); self.connected(); self.store.append.side_effect = None; self.store.rpc.side_effect = None; self.store.rpc.return_value = {'version': 1, 'status': 'published'}
        self.module.save('private-verification-v1.json', {'passed': True}); self.module.save('native-public-availability-v1.json', dict(passed=True, checks=[{'observed_http_status': 200}] * 10))
        self.module.publish(); result = json.loads((self.out / 'publication-v1.json').read_bytes())
        self.assertFalse(result['application_deployment']); self.assertEqual(len(result['studies']), 2)
        self.assertEqual(self.store.append.call_count, 4)
        for call in self.store.append.call_args_list:
            review = call.args[3]; self.assertIn('no human or independent', review['limitations'])
            if review['scope'] == 'scientific': self.assertFalse(review['judgments']['new_experiments'])
        for call in self.store.rpc.call_args_list: self.assertEqual(call.args[0], 'research_publish'); self.assertFalse(call.args[1]['p_withdraw'])
        (self.out / 'private-verification-v1.json').write_bytes(canonical({'passed': False}))
        with self.assertRaisesRegex(RuntimeError, 'verification did not pass'): self.module.publish()
        (self.out / 'private-verification-v1.json').write_bytes(canonical({'passed': True})); (self.out / 'native-public-availability-v1.json').write_bytes(canonical(dict(passed=True, checks=[])))
        with self.assertRaisesRegex(RuntimeError, 'availability did not pass'): self.module.publish()

    def test_cli_dispatch_and_read_only_flags_cannot_admit_an_import_or_publication(self):
        for command, function in [('inspect', 'inspect'), ('export', 'export'), ('prepare', 'prepare'), ('apply', 'apply'), ('verify', 'verify'), ('publish', 'publish'), ('retain-evidence', 'retain_evidence')]:
            with self.subTest(command=command), patch.object(sys, 'argv', ['importer', command]), patch.object(self.module, function) as action:
                self.module.main(); action.assert_called_once()
        for flag, command in [('--supabase-only', 'apply'), ('--public', 'publish')]:
            with patch.object(sys, 'argv', ['importer', command, flag]), self.assertRaises(ValueError): self.module.main()

    def retention_fixture(self):
        studies = [dict(module=module, study_id=str(uuid.uuid5(uuid.NAMESPACE_URL, module))) for module in [
            'propagation-delay-study', 'leo-emergency-failover', 'http2-compliance-study', 'ipv6-dns-study', 'reliable-sketch-study']]
        self.enterContext(patch.object(self.module, 'prepared', return_value=[(item, {}) for item in studies]))
        self.connected()
        names = ['persistence-v1.json', 'native-manifest-v1.json', 'prepared-manifest-v3.json', 'private-verification-v1.json',
                 'native-public-availability-v1.json', 'local-validation-v1.json', 'local-validation-v2.json',
                 'verification-failures-v1.json', 'publication-failures-v1.json', 'import-operator-v1.py', 'workflow-before-review-scope-fix.py']
        for name in names: self.write(self.out / name, canonical({'fixture': name}))
        self.write(self.out / 'persistence-v1.json', canonical({'stored_payload_bytes': 100}))
        self.write(self.out / 'public-verification-v1.json', canonical({'passed': True, 'studies': studies}))
        self.write(self.out / 'publication-v1.json', canonical({'studies': [dict(item, status='published') for item in studies]}))
        report = self.browser.parent.parent / '20261102/browser-report.json'
        self.write(report, canonical(dict(mode='public production', passed=True, checks=[{}] * 26)))
        for item in studies:
            for width in [1365, 390]:
                for theme in ['light', 'dark']: self.write(report.parent / (item['module'] + '-' + str(width) + '-' + theme + '.png'), b'Synthetic PNG original ' + str(width).encode() + theme.encode())
        self.write(self.backend / 'research_workflow/workflow.py', b'# synthetic retained workflow\n')
        self.write(self.backend / 'research_workflow/tests/test_workflow.py', b'# synthetic retained tests\n')
        self.write(self.workspace / 'jumpserve-front-end/scripts/verify-archived-assessments.mjs', b'// synthetic browser verifier\n')
        originals = {}
        def artifact(study, actor, raw, id, media, provenance):
            originals[id] = raw; return dict(id=id, sha256=digest(raw), byte_count=len(raw))
        self.store.artifact.side_effect = artifact; self.store.artifact_bytes.side_effect = lambda study, id, **options: originals[id]
        self.store.append.side_effect = None; self.store.rows.side_effect = lambda kind, query, **options: [{'version': 1, 'id': query['study_id']}]
        self.enterContext(patch.object(self.module.time, 'monotonic', return_value=10))
        return studies, report, originals

    def test_retained_validation_archives_round_trip_every_original_and_keep_publication_versions_unchanged(self):
        studies, report, originals = self.retention_fixture(); self.module.retain_evidence()
        result = json.loads((self.out / 'validation-retention-v1.json').read_bytes())
        self.assertTrue(result['passed']); self.assertFalse(result['deployment']); self.assertEqual(len(result['studies']), 5)
        self.assertEqual(self.store.artifact.call_count, 5); self.store.rpc.assert_not_called()
        for item in result['studies']:
            raw = originals[item['artifact_id']]
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(len(archive.namelist()), item['members_verified'] + 1)
                for member in manifest['files']:
                    original = archive.read(member['name']); self.assertEqual(digest(original), member['sha256'])
                    self.assertEqual(len(original), member['byte_count']); self.assertEqual(archive.getinfo(member['name']).date_time, (1980, 1, 1, 0, 0, 0))
        first = {item['module']: (self.out / (item['module'] + '-validation-v1.zip')).read_bytes() for item in studies}
        self.module.retain_evidence()
        self.assertEqual(first, {item['module']: (self.out / (item['module'] + '-validation-v1.zip')).read_bytes() for item in studies})

    def test_retention_requires_complete_public_and_production_browser_evidence_before_writes(self):
        studies, report, _ = self.retention_fixture()
        public = self.out / 'public-verification-v1.json'; baseline = public.read_bytes()
        public.write_bytes(canonical({'passed': False, 'studies': studies}))
        with self.assertRaisesRegex(RuntimeError, 'Successful public verification'): self.module.retain_evidence()
        public.write_bytes(baseline); report.write_bytes(canonical(dict(mode='public production', passed=True, checks=[])))
        with self.assertRaisesRegex(RuntimeError, 'Complete five-study production'): self.module.retain_evidence()
        report.write_bytes(canonical(dict(mode='public production', passed=False, checks=[{}] * 26)))
        with self.assertRaisesRegex(RuntimeError, 'Complete five-study production'): self.module.retain_evidence()
        self.store.artifact.assert_not_called()

    def test_retention_refuses_changed_archives_original_byte_bounds_or_aggregate_budget_overflow(self):
        studies, report, _ = self.retention_fixture()
        target = self.out / (studies[0]['module'] + '-validation-v1.zip'); target.write_bytes(b'previous evidence')
        with self.assertRaisesRegex(RuntimeError, 'Retained validation ZIP differs'): self.module.retain_evidence()
        target.unlink()
        image = report.parent / (studies[0]['module'] + '-1365-light.png'); original = image.read_bytes(); image.write_bytes(b'x' * 10_000_001)
        with self.assertRaisesRegex(RuntimeError, 'Validation original exceeds'): self.module.retain_evidence()
        image.write_bytes(original); (self.out / 'persistence-v1.json').write_bytes(canonical({'stored_payload_bytes': 50_000_000}))
        with self.assertRaisesRegex(RuntimeError, 'aggregate bound'): self.module.retain_evidence()
        self.store.artifact.assert_not_called()

    def test_retained_archives_cannot_change_after_upload_or_change_the_existing_publication(self):
        self.retention_fixture(); self.store.artifact_bytes.side_effect = lambda *args, **kwargs: b'changed original'
        with self.assertRaisesRegex(RuntimeError, 'original bytes differ after retrieval'): self.module.retain_evidence()
        self.store.artifact_bytes.side_effect = lambda study, id, **options: next(call.args[2] for call in self.store.artifact.call_args_list if call.args[3] == id)
        self.store.rows.side_effect = [[{'version': 1}], [{'version': 2}]]
        with self.assertRaisesRegex(RuntimeError, 'Publication changed'): self.module.retain_evidence()

    def test_archive_validation_rejects_missing_extra_duplicate_manifest_and_changed_member_bytes(self):
        raw = b'retained original'; manifest = dict(files=[dict(name='original.txt', sha256=digest(raw), byte_count=len(raw))])
        for failure in [None, 'missing', 'extra', 'duplicate', 'manifest', 'bytes', 'length']:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as bundle:
                if failure != 'missing': bundle.writestr('original.txt', b'changed original' if failure == 'bytes' else raw + b' ' if failure == 'length' else raw)
                if failure == 'extra': bundle.writestr('extra.txt', b'unexpected')
                if failure == 'duplicate':
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning); bundle.writestr('original.txt', raw)
                bundle.writestr('manifest.json', b'wrong manifest' if failure == 'manifest' else canonical(manifest))
            with self.subTest(failure=failure):
                if failure:
                    with self.assertRaises(RuntimeError): self.module.verify_validation_archive(buffer.getvalue(), manifest)
                else: self.module.verify_validation_archive(buffer.getvalue(), manifest)

    def test_compressed_archive_bound_is_enforced_independently_of_each_member_bound(self):
        self.retention_fixture(); original = random.Random(7).randbytes(4_000_000)
        for path in [self.out / 'import-operator-v1.py', self.out / 'workflow-before-review-scope-fix.py', self.backend / 'research_workflow/workflow.py']:
            path.write_bytes(original)
        with self.assertRaisesRegex(RuntimeError, 'Validation ZIP exceeds'): self.module.retain_evidence()
        self.store.artifact.assert_not_called()

    def test_apply_bounds_each_original_and_never_appends_a_partial_bundle_after_oversize(self):
        self.prepare(); self.connected(); self.store.rpc.side_effect = None; self.store.owns.side_effect = None; self.store.owns.return_value = True
        self.store.artifact.side_effect = lambda study, actor, raw, id, media, provenance: dict(id=id, sha256=digest(raw), byte_count=len(raw))
        self.write(self.browser, canonical(dict(mode='exact prepared component preview', passed=True, checks=[{}] * 20, padding='x' * 10_000_000)))
        with self.assertRaisesRegex(RuntimeError, 'Original artifact exceeds'): self.module.apply()
        self.assertFalse((self.out / 'persistence-v1.json').exists())
        self.assertFalse(any(call.kwargs.get('read_only') is False for call in self.guard.admin.query.call_args_list))

    def test_actual_help_entrypoint_does_not_dispatch_database_storage_or_process_operations(self):
        with patch.dict(sys.modules, {'workflow': self.workflow, 'archive': self.archive, 'store': self.store}), patch.object(sys, 'path', list(sys.path)), patch.object(sys, 'argv', ['importer', '--help']), patch.object(self.module.subprocess, 'check_output') as process, self.assertRaises(SystemExit) as result:
            runpy.run_path(str(ROOT / 'bin/import-archived-assessments.py'), run_name='__main__')
        self.assertEqual(result.exception.code, 0); process.assert_not_called(); self.store.rpc.assert_not_called()

    def test_aggregate_original_budget_is_checked_across_all_five_studies(self):
        self.modules.update({key: dict(value, tables=['sources', 'summaries']) for key, value in self.definitions.items()})
        self.table_rows.update({definition['prefix'] + suffix: ['{"id":"fixture"}'] for definition in self.modules.values() for suffix in definition['tables']})
        self.counts[:] = [{'relation': key, 'records': len(rows)} for key, rows in self.table_rows.items()]
        self.write(self.out / 'inventory-v1.json', canonical(dict(counts=self.counts, studies=self.old_studies)))
        self.protocol = b'p' * 8_000_000; self.write(self.root / 'docs/archived-assessment-import-protocol-v1.md', self.protocol)
        self.write(self.root / 'docs/archived-assessment-import-serialization-v2.md', b's' * 3_000_000)
        self.prepare(); self.connected(); self.store.rpc.side_effect = None; self.store.owns.side_effect = None; self.store.owns.return_value = True
        self.store.artifact.side_effect = lambda study, actor, raw, id, media, provenance: dict(id=id, sha256=digest(raw), byte_count=len(raw))
        with self.assertRaisesRegex(RuntimeError, 'Logical original storage exceeds'): self.module.apply()
        self.assertFalse((self.out / 'persistence-v1.json').exists())
        self.assertEqual(len((self.out / 'write-progress-v1.jsonl').read_text().splitlines()), 5)

    def test_large_imports_append_complete_records_in_batches_of_at_most_one_hundred(self):
        values = self.prepare(); item, value = values[0]; value = copy.deepcopy(value)
        template = value['records'][1]['record']
        value['records'] += [dict(kind='claims', record=dict(template, id=identity(value['study_id'], 'claim-' + str(n)))) for n in range(205)]
        self.connected(); self.store.rpc.side_effect = None; self.store.owns.side_effect = None; self.store.owns.return_value = True
        self.store.artifact.side_effect = lambda study, actor, raw, id, media, provenance: dict(id=id, sha256=digest(raw), byte_count=len(raw))
        with patch.object(self.module, 'prepared', return_value=[(item, value)]): self.module.apply()
        progress = [json.loads(line) for line in (self.out / 'write-progress-v1.jsonl').read_text().splitlines()]
        self.assertEqual([row['offset'] for row in progress], [0, 100, 200])
        self.assertTrue(all(0 < row['records'] <= 100 for row in progress)); self.assertEqual(sum(row['records'] for row in progress), 219)


if __name__ == '__main__': unittest.main()
