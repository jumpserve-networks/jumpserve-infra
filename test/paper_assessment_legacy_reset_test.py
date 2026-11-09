"""The frozen legacy reset controller against a synthetic database adapter.

Only temporary JSON/SQL files are written. No SQL engine, cloud command, Storage
operation or deletion is invoked. The real approved identity pin is preserved.
"""
import contextlib
import builtins
import copy
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

from builder_continuation_release_test import canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/reset-paper-assessments.py'
APPROVED_PIN = '74195063e952f0821383fdfdfbfec22e364d1f70b158f7d5f548237c44b602e5'


class LegacyPaperReset(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='legacy-paper-reset-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve(); self.base = self.root / '.test-artifacts/assessment-reset'; self.base.mkdir(parents=True)
        self.ids = sorted(identity('synthetic-approved-paper-' + str(n)) for n in range(31)); self.idea = identity('preserved-synthetic-idea'); self.studies = [dict(id=value, title='Original synthetic paper ' + str(n), study_kind='paper', created_at='2026-11-07T00:00:00Z') for n, value in enumerate(self.ids)]
        self.catalog = dict(tables=[dict(name=name, columns=['id'] + ([] if name in ['research_studies', 'research_paper_uploads'] else ['study_id'])) for name in ['research_studies', 'research_paper_uploads', 'research_autonomy_turns', 'research_model_dispatches', 'research_queue_jobs']] + [dict(name='research_global_settings', columns=['id', 'value'])], fks=[dict(table=child, target=parent) for child, parent in [('research_studies', 'research_studies'), ('research_paper_uploads', 'research_studies'), ('research_queue_jobs', 'research_studies'), ('research_model_dispatches', 'research_queue_jobs'), ('research_autonomy_turns', 'research_studies')]], triggers=[dict(table=table, name=name, enabled=enabled, definition=definition) for table, name, enabled, definition in [('research_studies', 'guard_studies', 'O', 'BEFORE DELETE'), ('research_queue_jobs', 'guard_queue', 'O', 'BEFORE DELETE'), ('research_model_dispatches', 'disabled_guard', 'D', 'BEFORE DELETE'), ('research_paper_uploads', 'update_only', 'O', 'BEFORE UPDATE'), ('research_global_settings', 'unrelated_guard', 'O', 'BEFORE DELETE')]])
        self.target_rows = {}; self.preserved_rows = {}; self.queries = []; self.active = 0; self.empty_page = False; self.overflow_page = False; self.bad_fingerprint = False; self.transaction_failure = False
        for table in self.catalog['tables']:
            name = table['name']
            if name == 'research_global_settings': continue
            count = 0 if name == 'research_model_dispatches' else 26 if name == 'research_autonomy_turns' else 31
            self.target_rows[name] = [json.dumps(dict(id=self.ids[n] if name in ['research_studies', 'research_paper_uploads'] else identity(name + str(n)), study_id=self.ids[0], original='Synthetic Ω\nretained', measurement=0 if n % 2 else None), sort_keys=True, ensure_ascii=False) for n in range(count)]
            self.preserved_rows[name] = [json.dumps(dict(id=self.idea, study_id=self.idea, original='Preserved synthetic idea'), sort_keys=True)]
        self.admin = types.ModuleType('synthetic_legacy_reset_admin'); self.admin.PROJECT_REF = 'regphejnlvfpyokpniny'; self.admin.literal = lambda value: "'" + value.replace("'", "''") + "'"; self.admin.query = Mock(side_effect=self.query)
        self.release = self.load(); self.assertEqual(self.release.APPROVED_IDS_SHA256, APPROVED_PIN); self.release.ROOT = self.root; self.release.BASE = self.base; self.enterContext(patch.object(self.release, 'APPROVED_IDS_SHA256', digest(canonical(self.ids)))); self.cloud = self.enterContext(patch.object(self.release.subprocess, 'check_output', return_value=canonical({'Account': '395567831870'})))
        self.write('cdk.json', canonical({'context': {'supabaseUrl': 'https://regphejnlvfpyokpniny.supabase.co'}})); self.write('.test-artifacts/assessment-reset/catalog-before.json', canonical(self.catalog)); self.directory = None

    def specification(self, original, label, location, *args, **kwargs):
        admin = self.admin
        class Loader:
            def create_module(self, spec): return admin
            def exec_module(self, module): return None
        return importlib.machinery.ModuleSpec(label, Loader()) if Path(location) == ROOT / 'bin/agent-prompts.py' else original(label, location, *args, **kwargs)
    def load(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)):
            spec = original('legacy_reset_unit', SOURCE); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def fingerprint(self, rows): return dict(n=len(rows), hash=digest(''.join(digest(raw.encode()) for raw in rows).encode()))
    def query(self, sql, **options):
        self.queries.append((sql, options))
        if sql == 'select current_database() database': return [{'database': 'synthetic'}]
        if sql.startswith('select id,title,study_kind,created_at'): return copy.deepcopy(self.studies)
        if sql.startswith('select (select count(*) from research_autonomy_tasks'): return [{'n': self.active}]
        if sql.startswith('select c.relname table_name,'): return [dict(table_name=name, cols=['id', 'study_id'] if name == 'research_autonomy_turns' else ['id']) for name in self.target_rows]
        if sql.startswith('select count(*) n,encode('):
            name = re.search(r'from public\."([a-z_]+)"', sql)[1]; value = self.fingerprint(self.preserved_rows[name] if 'where not (' in sql else self.target_rows[name]); return [dict(value, **({'hash': 'f' * 64} if self.bad_fingerprint and 'where not (' not in sql else {}))]
        if sql.startswith('select to_jsonb(t)::text raw'):
            name = re.search(r'from public\."([a-z_]+)"', sql)[1]; offset = int(re.search(r' offset ([0-9]+)', sql)[1]); limit = int(re.search(r' limit ([0-9]+)', sql)[1]); rows = self.target_rows[name][offset:offset + limit]
            if self.empty_page: rows = []
            if self.overflow_page: rows = self.target_rows[name] * 2
            return [{'raw': raw} for raw in rows]
        if sql.startswith('begin; set local lock_timeout'):
            self.assertEqual(options, {'read_only': False})
            if self.transaction_failure: raise TimeoutError('Synthetic acknowledgement lost; private details')
            return []
        raise AssertionError('Unexpected SQL: ' + sql)
    def backup(self):
        with contextlib.redirect_stdout(io.StringIO()) as output: self.release.backup()
        self.directory = self.base / (self.base / 'selected.txt').read_text().strip(); self.packet = json.loads((self.directory / 'backup-manifest.json').read_bytes()); return output.getvalue()
    def apply(self, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()) as output: self.release.apply(dry_run)
        return json.loads(output.getvalue())
    def transaction_calls(self): return [(sql, options) for sql, options in self.queries if sql.startswith('begin;')]

    def test_fixed_target_checks_account_project_and_exact_url_before_querying(self):
        self.assertEqual(self.release.target(), dict(aws_account='395567831870', supabase_project='regphejnlvfpyokpniny')); self.assertEqual(self.cloud.call_args.args[0], ['aws', 'sts', 'get-caller-identity', '--profile', 'jumpserve']); self.assertEqual(self.cloud.call_args.kwargs['timeout'], 20)
        for failure in ['account', 'project', 'url']:
            with self.subTest(failure=failure), contextlib.ExitStack() as stack:
                if failure == 'account': stack.enter_context(patch.object(self.release.subprocess, 'check_output', return_value=canonical({'Account': 'wrong'})))
                elif failure == 'project': stack.enter_context(patch.object(self.admin, 'PROJECT_REF', 'wrong'))
                else: self.write('cdk.json', canonical({'context': {'supabaseUrl': 'https://other.invalid'}}))
                self.admin.query.reset_mock()
                with self.assertRaises(AssertionError): self.release.target()
                self.admin.query.assert_not_called()

    def test_identifiers_predicates_and_fingerprints_quote_only_the_frozen_uuid_scope(self):
        self.assertEqual(self.release.ident('research_table'), '"research_table"')
        for name in ['public.table', 'table;delete', 'MixedCase', '', 'a1']:
            with self.subTest(name=name), self.assertRaises(ValueError): self.release.ident(name)
        for table in ['research_studies', 'research_paper_uploads', 'research_autonomy_turns']:
            predicate = self.release.condition(table, self.ids[:2]); self.assertTrue(predicate.startswith('t."id"' if table != 'research_autonomy_turns' else 't."study_id"')); self.assertEqual(predicate.count('::uuid'), 2); sql = self.release.fingerprint(table, predicate, 't."id"'); self.assertIn('to_jsonb(t)::text', sql); self.assertIn('order by t."id"', sql)
        with self.assertRaises(ValueError): self.release.condition('research_studies', ['not-a-uuid'])

    def test_backup_retains_original_json_bytes_aggregate_fingerprints_and_foreign_key_order(self):
        output = self.backup(); packet = self.packet; self.assertEqual(packet['status'], 'backup-verified'); self.assertEqual(packet['ids'], self.ids); self.assertIn('no object deletions', packet['raw_storage_objects']); self.assertNotIn('research_global_settings', packet['tables']); self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700); self.assertIn('"assessments": 31', output)
        for name, row in packet['tables'].items():
            raw = (self.directory / row['file']).read_bytes(); self.assertEqual(raw, ''.join(value + '\n' for value in self.target_rows[name]).encode()); self.assertEqual(row['sha256'], digest(raw)); self.assertEqual(row['bytes'], len(raw)); self.assertEqual(row['database_hash'], self.fingerprint(self.target_rows[name])['hash']); self.assertEqual(row['nonpaper'], self.fingerprint(self.preserved_rows[name])); self.assertEqual(row['count'], len(self.target_rows[name]))
        pages = [sql for sql, _ in self.queries if sql.startswith('select to_jsonb') and '"research_autonomy_turns"' in sql]; self.assertEqual(len(pages), 2); self.assertIn('offset 0 limit 25', pages[0]); self.assertIn('offset 25 limit 25', pages[1]); self.assertIn('order by t."id",t."study_id"', pages[0]); self.assertLess(packet['delete_order'].index('research_model_dispatches'), packet['delete_order'].index('research_queue_jobs')); self.assertEqual(packet['delete_order'][-1], 'research_studies'); self.assertEqual(self.transaction_calls(), [])

    def test_backup_rejects_changed_count_identity_or_active_execution_before_writing_a_packet(self):
        for failure in ['count', 'identity', 'active']:
            with self.subTest(failure=failure):
                original = copy.deepcopy(self.studies); self.studies = original[:-1] if failure == 'count' else copy.deepcopy(original)
                if failure == 'identity': self.studies[0]['id'] = identity('different-unapproved-paper')
                self.active = int(failure == 'active')
                with self.assertRaisesRegex(ValueError, '31 assessments|identities differ|Drain active'): self.backup()
                self.assertFalse((self.base / 'selected.txt').exists()); self.assertEqual(list(self.base.glob('*/backup-manifest.json')), []); self.studies = original

    def test_backup_rejects_foreign_key_cycles(self):
        self.catalog['fks'].append(dict(table='research_studies', target='research_queue_jobs')); self.write('.test-artifacts/assessment-reset/catalog-before.json', canonical(self.catalog))
        with self.assertRaisesRegex(ValueError, 'FK cycle'): self.backup()
        self.assertFalse((self.base / 'selected.txt').exists())

    def test_incomplete_or_changed_backup_cannot_be_marked_verified_or_selected(self):
        for failure in ['empty', 'fingerprint', 'overflow']:
            with self.subTest(failure=failure):
                self.empty_page = failure == 'empty'; self.bad_fingerprint = failure == 'fingerprint'; self.overflow_page = failure == 'overflow'
                with self.assertRaisesRegex(ValueError, 'Incomplete backup page|Database changed or backup bytes differ'): self.backup()
                self.assertFalse((self.base / 'selected.txt').exists()); self.assertEqual(self.transaction_calls(), [])
        for path in self.base.glob('*/backup-manifest.json'): self.assertEqual(json.loads(path.read_bytes())['status'], 'backing-up')

    def test_dry_run_transaction_checks_originals_restores_delete_guards_and_preserves_ideas(self):
        self.backup(); result = self.apply(True); sql = (self.directory / 'dry-run.sql').read_text(); self.assertEqual(result['status'], 'rolled-back-verified'); self.assertTrue(sql.endswith('rollback;')); self.assertEqual(result['sql_sha256'], digest(sql.encode())); self.assertEqual(result['backup_manifest_sha256'], digest((self.directory / 'backup-manifest.json').read_bytes())); self.assertTrue(result['rls_and_foreign_keys_preserved']); self.assertTrue(result['nonpaper_data_verified_unchanged']); self.assertTrue(result['delete_guards_restored']); self.assertEqual(result['assessments'], 31); self.assertEqual(sql.count(' disable trigger '), 2); self.assertEqual(sql.count(' enable trigger '), 2); self.assertIn('pg_advisory_xact_lock', sql); self.assertIn(' in exclusive mode;', sql); self.assertIn('Backup no longer matches', sql); self.assertIn('Nonpaper data changed', sql); self.assertIn('Paper rows remain', sql); self.assertNotIn(self.idea, sql); self.assertNotIn('research_global_settings', sql); self.assertNotIn('disabled_guard', sql); self.assertNotIn('update_only', sql); self.assertNotIn('disable row level security', sql.lower()); self.assertNotIn('replication_role', sql.lower()); self.assertNotIn('cascade', sql.lower())
        positions = [sql.index('delete from public."' + name + '"') for name in self.packet['delete_order']]; self.assertEqual(positions, sorted(positions)); self.assertEqual(self.transaction_calls(), [(sql, {'read_only': False})])

    def test_apply_requires_the_exact_successful_dry_run_manifest_and_never_repeats_a_receipt(self):
        self.backup()
        with self.assertRaises(FileNotFoundError): self.apply()
        self.assertEqual(self.transaction_calls(), []); self.apply(True); result = self.apply(); sql = (self.directory / 'apply.sql').read_text(); self.assertTrue(sql.endswith('commit;')); self.assertEqual(result['status'], 'committed'); self.assertEqual(result['rows'], sum(len(rows) for rows in self.target_rows.values())); before = len(self.transaction_calls())
        for dry in [False, True]:
            with self.subTest(dry=dry), self.assertRaisesRegex(ValueError, 'Preserve previous reset receipts'): self.apply(dry)
        self.assertEqual(len(self.transaction_calls()), before)

    def test_changed_backup_bytes_or_manifest_and_failed_dry_run_cannot_admit_apply(self):
        self.backup(); self.apply(True); manifest = self.directory / 'backup-manifest.json'; original = manifest.read_bytes(); prior_path = self.directory / 'dry-run-receipt.json'; prior = json.loads(prior_path.read_bytes())
        manifest.write_bytes(original + b'\n')
        with self.assertRaises(AssertionError): self.apply()
        manifest.write_bytes(original); prior_path.write_bytes(canonical(dict(prior, status='failed-transaction-outcome-unconfirmed')))
        with self.assertRaises(AssertionError): self.apply()
        prior_path.write_bytes(canonical(prior)); name = next(iter(self.packet['tables'])); path = self.directory / self.packet['tables'][name]['file']; path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaises(AssertionError): self.apply()
        self.assertEqual(len(self.transaction_calls()), 1)

    def test_unverified_duplicate_or_unapproved_ids_are_rejected_before_transaction_creation(self):
        self.backup(); path = self.directory / 'backup-manifest.json'
        for failure in ['status', 'count', 'duplicate', 'identity']:
            packet = copy.deepcopy(self.packet)
            if failure == 'status': packet['status'] = 'backing-up'
            elif failure == 'count': packet['ids'].pop()
            elif failure == 'duplicate': packet['ids'][0] = packet['ids'][1]
            else: packet['ids'][0] = identity('not-approved')
            path.write_bytes(canonical(packet))
            with self.subTest(failure=failure), self.assertRaises(AssertionError): self.apply(True)
            self.assertFalse((self.directory / 'dry-run.sql').exists())
        self.assertEqual(self.transaction_calls(), [])

    def test_transaction_failure_retains_original_request_and_error_type_without_claiming_rollback(self):
        self.backup(); self.transaction_failure = True
        with self.assertRaises(TimeoutError), contextlib.redirect_stdout(io.StringIO()): self.release.apply(True)
        receipt = json.loads((self.directory / 'dry-run-receipt.json').read_bytes()); self.assertEqual(receipt['status'], 'failed-transaction-outcome-unconfirmed'); self.assertEqual(receipt['reason'], 'TimeoutError'); self.assertNotIn('private details', json.dumps(receipt)); self.assertIn('ended_at', receipt); sql = (self.directory / 'dry-run.sql').read_bytes(); self.assertEqual(receipt['sql_sha256'], digest(sql))
        with self.assertRaisesRegex(ValueError, 'Preserve previous reset receipts'): self.apply(True)
        self.assertEqual(len(self.transaction_calls()), 1)

    def test_unknown_cli_mode_cannot_dispatch_any_query_or_stage_a_backup(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)), patch.object(sys, 'argv', [str(SOURCE), 'delete-anything']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error: runpy.run_path(str(SOURCE), run_name='__main__')
        self.assertEqual(error.exception.code, 2); self.assertEqual(self.queries, []); self.cloud.assert_not_called(); self.assertFalse((self.base / 'selected.txt').exists())

    def test_cli_modes_keep_the_real_authorization_pin_and_do_not_admit_unapproved_or_missing_backups(self):
        original_specification = importlib.util.spec_from_file_location; original_import = builtins.__import__; synthetic_source = self.root / 'bin/reset-paper-assessments.py'
        def service_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'pathlib': return types.SimpleNamespace(Path=lambda value: synthetic_source if str(value) == str(SOURCE) else Path(value))
            return original_import(name, globals, locals, fromlist, level)
        def specification(label, location, *args, **kwargs):
            return self.specification(original_specification, label, ROOT / 'bin/agent-prompts.py' if Path(location) == self.root / 'bin/agent-prompts.py' else location, *args, **kwargs)
        for mode in ['backup', 'dry-run', 'apply']:
            with self.subTest(mode=mode), patch.object(importlib.util, 'spec_from_file_location', side_effect=specification), patch.object(sys, 'argv', [str(SOURCE), mode]):
                with self.assertRaisesRegex(ValueError, 'identities differ') if mode == 'backup' else self.assertRaises(FileNotFoundError):
                    runpy.run_path(str(SOURCE), run_name='__main__', init_globals={'__builtins__': dict(vars(builtins), __import__=service_import)})
        self.assertFalse((self.base / 'selected.txt').exists()); self.assertEqual(self.transaction_calls(), [])


if __name__ == '__main__': unittest.main()
