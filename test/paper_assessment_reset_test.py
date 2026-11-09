"""Paper reset backup and transaction guards against a synthetic database edge.

No database connection or real deletion occurs. Real local backup bytes, hashes,
pagination, private archive readback and generated transaction scope are tested.
"""
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile

from builder_continuation_release_test import canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/reset-paper-assessments-v2.py'


class PaperAssessmentReset(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='paper-reset-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name); self.base = self.root / 'reset'; self.base.mkdir(); self.ids = sorted([identity('paper-one'), identity('paper-two')]); self.idea = identity('preserved-idea'); self.studies = [dict(id=ident, title='Synthetic paper ' + str(index), study_kind='paper', created_at='2026-11-07T00:00:00Z', published=index == 0) for index, ident in enumerate(self.ids)]
        names = ['research_studies', 'research_paper_uploads', 'research_sources', 'research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs', 'research_network_executions', 'research_autonomy_turns', 'research_paper_review_events']
        self.catalog = dict(tables=[dict(name=name, rls=True, columns=['id'] + ([] if name in ['research_studies', 'research_paper_uploads'] else ['study_id']) + (['phase'] if name == 'research_network_executions' else ['status']), primary_key=['id']) for name in names] + [dict(name='research_global_prompt', rls=True, columns=['id', 'content'], primary_key=['id'])], fks=[dict(child=child, parent=parent, name=child + '_fk', definition='FOREIGN KEY synthetic') for child, parent in [('research_autonomy_tasks', 'research_studies'), ('research_model_dispatches', 'research_autonomy_tasks'), ('research_queue_jobs', 'research_studies'), ('research_network_executions', 'research_queue_jobs'), ('research_studies', 'research_studies')]], triggers=[dict(table_name=name, name='guard_' + str(index), enabled=enabled, definition=definition) for index, (name, enabled, definition) in enumerate([('research_studies', 'O', 'BEFORE DELETE'), ('research_autonomy_tasks', 'A', 'AFTER DELETE'), ('research_queue_jobs', 'R', 'BEFORE DELETE'), ('research_model_dispatches', 'D', 'BEFORE DELETE'), ('research_model_dispatches', 'O', 'BEFORE UPDATE'), ('research_sources', 'O', 'BEFORE DELETE')])])
        self.target = {}; self.preserved = {}; self.sql = []; self.objects = {}; self.active = 0; self.inventory_changed = False; self.schema_changed = False; self.empty_page = False; self.backup_drift = False; self.preserved_drift = False; self.committed = False; self.transaction_failure = False; self.bucket_public = False; self.anonymous_status = 403; self.upload_error = None; self.corrupt_read = False
        for name in names:
            count = 0 if name == 'research_sources' else 11 if name == 'research_autonomy_turns' else 26 if name == 'research_paper_review_events' else 2
            self.target[name] = [json.dumps(dict(id=self.ids[index] if name in ['research_studies', 'research_paper_uploads'] else identity(name + str(index)), study_id=self.ids[0], value=0 if index % 2 else None, original='Synthetic Ω'), sort_keys=True, ensure_ascii=False) for index in range(count)]
            self.preserved[name] = [json.dumps(dict(id=self.idea, study_id=self.idea, original='Preserved synthetic idea'), sort_keys=True)]
        self.r = types.ModuleType('synthetic_reset_release'); self.r.target = Mock(return_value={'synthetic_target': True}); self.r.admin = types.SimpleNamespace(query=Mock(side_effect=self.query), literal=lambda value: "'" + str(value).replace("'", "''") + "'"); self.r.aws = Mock(return_value={'SecretString': 'synthetic-memory-only-key'}); self.r.prior = types.SimpleNamespace(guard=types.SimpleNamespace(OPEN=types.SimpleNamespace(open=Mock(side_effect=self.open))))
        self.release = self.load(); self.release.ROOT = self.root; self.release.BASE = self.base; (self.root / 'cdk.json').write_bytes(canonical({'context': {'supabaseAnonKey': 'synthetic-anon-key'}}))
    def load(self, name='paper_reset_unit'):
        original = importlib.util.spec_from_file_location; release = self.r
        class ReleaseLoader:
            def create_module(self, spec): return release
            def exec_module(self, module): return None
        def specification(label, location, *args, **options): return importlib.machinery.ModuleSpec(label, ReleaseLoader()) if Path(location) == ROOT / 'bin/openclaw-release.py' else original(label, location, *args, **options)
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=specification): spec = original(name, SOURCE); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def fingerprint(self, rows): return dict(n=len(rows), hash=digest(''.join(digest(raw.encode()) for raw in rows).encode()))
    def scoped(self): return [table for table in self.catalog['tables'] if table['name'] in self.target]
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.startswith('select c.relname name,c.relrowsecurity'): return copy.deepcopy(self.catalog['tables']) + ([dict(name='research_changed', columns=['id'], primary_key=['id'], rls=True)] if self.schema_changed else [])
        if sql.startswith('select child.relname'): return copy.deepcopy(self.catalog['fks'])
        if sql.startswith('select c.relname table_name,t.tgname'): return copy.deepcopy(self.catalog['triggers'])
        if sql.startswith('select s.id,s.title'): return copy.deepcopy(self.studies)
        if sql.startswith('select study_kind,count(*)'): return [dict(study_kind='idea', n=1)]
        if ' table_name,count(*) n from public.' in sql: return [dict(table_name=table['name'], n=len(self.target[table['name']])) for table in self.scoped()]
        if sql.startswith('select "status" state') or sql.startswith('select "phase" state'): return [dict(state='cancelled', n=2)]
        if sql.startswith('select id from research_studies'): return [dict(id=ident) for ident in self.ids + ([identity('new-paper')] if self.inventory_changed else [])]
        if sql.startswith('select (select count(*) from research_autonomy_tasks'): return [{'n': self.active}]
        if ' table_name,(select to_jsonb(x)' in sql:
            return [dict(table_name=table['name'], target=dict(self.fingerprint(self.target[table['name']]), **({'hash': 'f' * 64} if self.backup_drift else {})), preserved=self.fingerprint(self.preserved[table['name']])) for table in self.scoped()]
        if sql.startswith('select to_jsonb(t)::text raw'):
            table = re.search(r'from public\."([a-z_]+)"', sql)[1]; offset = int(re.search(r' offset ([0-9]+)', sql)[1]); limit = int(re.search(r' limit ([0-9]+)', sql)[1]); return [] if self.empty_page else [dict(raw=raw) for raw in self.target[table][offset:offset + limit]]
        if sql.startswith('select public from storage.buckets'): return [{'public': self.bucket_public}]
        if sql.startswith('begin; set local lock_timeout'):
            self.assertEqual(options, {'read_only': False})
            if self.transaction_failure: raise TimeoutError('Original synthetic transaction acknowledgement is unconfirmed')
            if sql.endswith('commit;'): self.committed = True
            return []
        if sql.startswith("select count(*) n from research_studies where study_kind='paper'"): return [{'n': 0 if self.committed else len(self.ids)}]
        if ' fingerprint from (select 1)z' in sql: return [dict(name=name, fingerprint=dict(self.fingerprint(rows), **({'hash': 'e' * 64} if self.preserved_drift else {}))) for name, rows in self.preserved.items()]
        raise AssertionError('Unexpected synthetic SQL: ' + sql)
    def open(self, request, timeout):
        if isinstance(request, str): self.assertEqual(request, 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/papers'); self.assertEqual(timeout, 30); return io.BytesIO(canonical({'papers': [], 'coverage': {'papers': 0}, 'next_cursor': None}))
        url = request.full_url; self.assertTrue(url.startswith('https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'))
        if request.get_header('Apikey') == 'synthetic-anon-key':
            self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-anon-key'); self.assertEqual(timeout, 20)
            if self.anonymous_status != 200: raise urllib.error.HTTPError(url, self.anonymous_status, 'Synthetic anonymous denial', {}, None)
            return io.BytesIO(b'Unexpected anonymous access')
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-memory-only-key'); self.assertEqual(timeout, 60)
        if request.get_method() == 'POST':
            self.assertTrue(url not in self.objects or self.objects[url] == request.data); self.objects[url] = request.data
            if self.upload_error: raise urllib.error.HTTPError(url, self.upload_error, 'Synthetic upload result', {}, None)
            return io.BytesIO(b'{}')
        raw = self.objects[url]; return io.BytesIO(raw + b'changed' if self.corrupt_read else raw)
    def quiet(self, function, *args):
        with contextlib.redirect_stdout(io.StringIO()): return function(*args)
    def inspect(self): self.quiet(self.release.inspect); return self.release.selected()
    def backup(self): self.inspect(); self.quiet(self.release.backup); return self.release.selected()[0]
    def archived(self): out = self.backup(); self.quiet(self.release.archive); return out
    def transaction(self, dry_run=True): self.quiet(self.release.apply, dry_run)
    def writes(self): return [sql for sql, options in self.sql if options.get('read_only') is False]

    def test_identifiers_and_scope_predicates_reject_untrusted_syntax_and_keep_ideas_outside_the_target(self):
        self.assertEqual(self.release.ident('research_studies'), '"research_studies"'); self.assertEqual(self.release.predicate('research_sources', []), 'false')
        for name in ['bad-name', 'a.b', 'UPPER', 'x;delete', '1name']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unsafe schema'): self.release.ident(name)
        for name in ['research_studies', 'research_paper_uploads']: self.assertIn('t."id" in (', self.release.predicate(name, self.ids))
        self.assertIn('t."study_id" in (', self.release.predicate('research_sources', self.ids)); self.assertNotIn(self.idea, self.release.predicate('research_sources', self.ids))
        with self.assertRaises(ValueError): self.release.predicate('research_sources', ['not-a-uuid'])

    def test_inspection_freezes_paper_identities_schema_counts_states_and_preserved_nonpaper_scope(self):
        out, data = self.inspect(); self.assertEqual(data['ids'], self.ids); self.assertEqual(data['nonpaper_studies'], [dict(study_kind='idea', n=1)]); self.assertTrue(data['catalog']['tables'][0]['rls']); self.assertEqual(out.stat().st_mode & 0o777, 0o700); self.assertEqual(set(data['states']), {'research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs', 'research_network_executions'}); self.assertNotIn('research_global_prompt', {row['table_name'] for row in data['counts']}); self.assertEqual(self.writes(), [])
        (self.base / 'selected.txt').write_text('../outside')
        with self.assertRaises(AssertionError): self.release.selected()

    def test_changed_frozen_identity_digest_and_empty_paper_inventory_cannot_begin_backup(self):
        out, data = self.inspect(); data['ids'].append(identity('substituted-paper')); (out / 'inventory.json').write_bytes(canonical(data))
        with self.assertRaises(AssertionError): self.release.selected()
        self.studies = []; self.ids = []; self.inspect()
        with self.assertRaisesRegex(AssertionError, 'No papers to delete'): self.release.backup()
        self.assertEqual(self.writes(), [])

    def test_changed_inventory_schema_and_active_execution_each_fence_backup_before_any_snapshot(self):
        out, _ = self.inspect()
        for field in ['inventory_changed', 'schema_changed', 'active']:
            with self.subTest(field=field):
                setattr(self, field, True)
                with self.assertRaises(AssertionError): self.release.backup()
                self.assertFalse((out / 'backup-manifest.json').exists()); setattr(self, field, False)

    def test_backup_preserves_exact_jsonl_bytes_pagination_fingerprints_and_private_file_modes(self):
        out = self.backup(); packet = json.loads((out / 'backup-manifest.json').read_bytes()); self.assertEqual(packet['status'], 'backup-verified'); self.assertEqual((out / 'backup-manifest.json').stat().st_mode & 0o777, 0o600)
        for name, item in packet['tables'].items():
            raw = (out / item['file']).read_bytes(); self.assertEqual(raw, b''.join(row.encode() + b'\n' for row in self.target[name])); self.assertEqual(item['sha256'], digest(raw)); self.assertEqual(item['target'], self.fingerprint(self.target[name])); self.assertEqual(item['preserved'], self.fingerprint(self.preserved[name])); self.assertEqual((out / item['file']).stat().st_mode & 0o777, 0o600)
        pages = [sql for sql, _ in self.sql if sql.startswith('select to_jsonb(t)::text raw')]; self.assertTrue(any('"research_autonomy_turns"' in sql and ' offset 10 limit 10' in sql for sql in pages)); self.assertTrue(any('"research_model_dispatches"' in sql and ' limit 10' in sql for sql in pages)); self.assertTrue(any('"research_paper_review_events"' in sql and ' offset 25 limit 25' in sql for sql in pages)); self.assertTrue(any(' limit 500' in sql for sql in pages)); self.assertEqual(self.writes(), [])
        with self.assertRaisesRegex(AssertionError, 'existing backup'): self.release.backup()

    def test_incomplete_or_changed_backup_rows_keep_a_partial_manifest_and_never_become_verified(self):
        self.inspect(); self.empty_page = True
        with self.assertRaisesRegex(AssertionError, 'Incomplete backup page'): self.quiet(self.release.backup)
        out, _ = self.release.selected(); self.assertEqual(json.loads((out / 'backup-manifest.json').read_bytes())['status'], 'backing-up'); self.empty_page = False; self.inspect(); self.backup_drift = True
        with self.assertRaisesRegex(AssertionError, 'Backup changed'): self.quiet(self.release.backup)
        out, _ = self.release.selected(); self.assertEqual(json.loads((out / 'backup-manifest.json').read_bytes())['status'], 'backing-up'); self.assertEqual(self.writes(), [])

    def test_backup_archive_is_private_hash_verified_and_retains_the_exact_producer_and_all_manifest_members(self):
        out = self.archived(); pointer = json.loads((out / 'backup-archive.json').read_bytes()); raw = (out / 'backup.zip').read_bytes(); self.assertEqual(pointer['sha256'], digest(raw)); self.assertEqual(pointer['sha256'], pointer['retrieved_sha256']); self.assertTrue(pointer['private']); self.assertEqual(pointer['anonymous_read_status'], 403); self.assertEqual(pointer['backup_manifest_sha256'], digest((out / 'backup-manifest.json').read_bytes()))
        with zipfile.ZipFile(io.BytesIO(raw)) as capsule:
            self.assertEqual(capsule.read('reset-producer.py'), SOURCE.read_bytes())
            for row in json.loads(capsule.read('artifact-manifest.json')): self.assertEqual(row['sha256'], digest(capsule.read(row['path']))); self.assertEqual(row['bytes'], len(capsule.read(row['path'])))
        self.assertEqual(self.writes(), [])

    def test_archive_requires_private_storage_and_original_backup_file_hashes(self):
        out = self.backup(); self.bucket_public = True
        with self.assertRaises(AssertionError): self.quiet(self.release.archive)
        self.bucket_public = False; file = out / 'research_studies.jsonl'; file.write_bytes(file.read_bytes() + b'changed')
        with self.assertRaises(AssertionError): self.quiet(self.release.archive)
        self.assertEqual(self.objects, {}); self.assertFalse((out / 'backup-archive.json').exists())

    def test_upload_conflicts_are_reconciled_only_by_identical_download_and_other_http_errors_remain_failures(self):
        out = self.backup(); self.upload_error = 409; self.quiet(self.release.archive); self.assertTrue((out / 'backup-archive.json').exists()); self.corrupt_read = True
        with self.assertRaises(AssertionError): self.quiet(self.release.archive)
        self.corrupt_read = False; self.upload_error = 500
        with self.assertRaises(urllib.error.HTTPError): self.quiet(self.release.archive)

    def test_anonymous_backup_read_access_blocks_archival_and_any_reset_transaction(self):
        out = self.backup(); self.anonymous_status = 200
        with self.assertRaisesRegex(AssertionError, 'anonymous-readable'): self.quiet(self.release.archive)
        self.assertFalse((out / 'backup-archive.json').exists()); self.anonymous_status = 403; self.quiet(self.release.archive); self.anonymous_status = 200
        with self.assertRaisesRegex(AssertionError, 'accessible to the anonymous'): self.transaction()
        self.assertEqual(self.writes(), [])

    def test_dry_run_and_commit_are_single_guarded_transactions_with_child_first_deletion_and_original_trigger_modes(self):
        out = self.archived(); before = copy.deepcopy(self.preserved); self.transaction(); rolled = json.loads((out / 'dry-run-receipt.json').read_bytes()); self.assertEqual(rolled['status'], 'rolled-back-verified'); self.assertFalse(self.committed); self.transaction(False); applied = json.loads((out / 'apply-receipt.json').read_bytes()); self.assertEqual(applied['status'], 'committed'); self.assertTrue(self.committed); self.assertEqual(self.preserved, before)
        sql = self.writes()[-1]; self.assertTrue(sql.startswith('begin;')); self.assertTrue(sql.endswith('commit;')); self.assertIn('pg_advisory_xact_lock', sql); self.assertIn('in exclusive mode', sql); self.assertIn('Paper inventory changed', sql); self.assertIn('Preserved records changed', sql)
        self.assertLess(sql.index('delete from public."research_model_dispatches"'), sql.index('delete from public."research_autonomy_tasks"')); self.assertLess(sql.index('delete from public."research_autonomy_tasks"'), sql.index('delete from public."research_studies"')); self.assertIn('enable always trigger "guard_1"', sql); self.assertIn('enable replica trigger "guard_2"', sql); self.assertIn('enable trigger "guard_0"', sql); self.assertNotIn('disable trigger "guard_3"', sql); self.assertNotIn('disable trigger "guard_4"', sql); self.assertNotIn('disable trigger "guard_5"', sql); self.assertNotIn('delete from public."research_global_prompt"', sql); self.assertNotIn('storage.objects', sql); self.assertIn('role', json.loads((out / 'backup-access-verification.json').read_bytes()))
        with self.assertRaisesRegex(AssertionError, 'Preserve original receipts'): self.transaction(False)
        self.assertEqual(len(self.writes()), 2)

    def test_commit_requires_a_matching_rolled_back_dry_run_and_unchanged_backup_manifest(self):
        out = self.archived()
        with self.assertRaises(FileNotFoundError): self.transaction(False)
        self.transaction(); prior = json.loads((out / 'dry-run-receipt.json').read_bytes()); prior['backup_manifest_sha256'] = 'e' * 64; (out / 'dry-run-receipt.json').write_bytes(canonical(prior))
        with self.assertRaises(AssertionError): self.transaction(False)
        self.assertEqual(len(self.writes()), 1); self.assertFalse(self.committed)

    def test_schema_execution_and_local_original_drift_each_fence_the_transaction(self):
        out = self.archived(); self.schema_changed = True
        with self.assertRaisesRegex(AssertionError, 'Schema changed'): self.transaction()
        self.schema_changed = False; self.active = 1
        with self.assertRaisesRegex(AssertionError, 'Drain/cancel'): self.transaction()
        self.active = 0; file = out / 'research_studies.jsonl'; file.write_bytes(file.read_bytes() + b'changed')
        with self.assertRaises(AssertionError): self.transaction()
        self.assertEqual(self.writes(), [])

    def test_foreign_key_cycles_are_rejected_before_sql_or_receipt_admission(self):
        self.catalog['fks'].append(dict(child='research_studies', parent='research_autonomy_tasks', name='synthetic_cycle', definition='FOREIGN KEY synthetic')); out = self.archived()
        with self.assertRaisesRegex(AssertionError, 'foreign-key cycle'): self.transaction()
        self.assertEqual(self.writes(), []); self.assertFalse((out / 'dry-run.sql').exists())

    def test_uncertain_transaction_failure_retains_its_original_sql_and_failure_receipt_without_claiming_rollback(self):
        out = self.archived(); self.transaction_failure = True
        with self.assertRaises(TimeoutError): self.transaction()
        result = json.loads((out / 'dry-run-receipt.json').read_bytes()); self.assertEqual(result['status'], 'failed'); self.assertIn('acknowledgement is unconfirmed', result['reason']); self.assertEqual(result['sql_sha256'], digest((out / 'dry-run.sql').read_bytes())); self.assertIn('ended_at', result); self.assertNotIn('deleted_rows', result)
        with self.assertRaisesRegex(AssertionError, 'Preserve original receipts'): self.transaction()
        self.assertEqual(len(self.writes()), 1)

    def test_verification_requires_a_commit_unchanged_schema_and_preserved_nonpaper_fingerprints(self):
        out = self.archived(); self.transaction(); self.transaction(False); self.quiet(self.release.verify); result = json.loads((out / 'verification.json').read_bytes()); self.assertEqual(result['paper_assessments_remaining'], 0); self.assertEqual(result['paper_assessments_deleted'], 2); self.assertTrue(result['private_raw_storage_retained']); self.assertEqual(result['nonpaper_studies'], [dict(study_kind='idea', n=1)]); self.assertEqual(json.loads((out / 'public-paper-catalog.json').read_bytes())['papers'], [])
        self.preserved_drift = True
        with self.assertRaises(AssertionError): self.release.verify()
        self.preserved_drift = False; self.schema_changed = True
        with self.assertRaisesRegex(AssertionError, 'RLS, columns'): self.release.verify()

    def test_cli_dispatches_only_fixed_actions_and_invalid_entrypoints_touch_no_services(self):
        with contextlib.ExitStack() as stack:
            actions = {name: stack.enter_context(patch.object(self.release, name)) for name in ['inspect', 'backup', 'archive', 'verify', 'apply']}
            for mode in ['inspect', 'backup', 'archive', 'verify', 'dry-run', 'apply']:
                with patch.object(sys, 'argv', [str(SOURCE), mode]): self.release.main()
            for name in ['inspect', 'backup', 'archive', 'verify']: actions[name].assert_called_once_with()
            self.assertEqual(actions['apply'].call_args_list[0].args, (True,)); self.assertEqual(actions['apply'].call_args_list[1].args, (False,))
        with patch.object(sys, 'argv', [str(SOURCE), 'unknown-unit-mode']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped: self.load('__main__')
        self.assertEqual(stopped.exception.code, 2); self.r.target.assert_not_called(); self.r.admin.query.assert_not_called()


if __name__ == '__main__': unittest.main()
