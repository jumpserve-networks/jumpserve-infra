"""Profile release verification against synthetic SQL/HTTP and real migration bytes."""
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/profile-release.py'
OWNER = '(( SELECT auth.uid() AS uid ) = id)'
SIGNED_IN = "(((SELECT auth.uid() AS uid) IS NOT NULL) AND ((SELECT (auth.jwt() ->> 'is_anonymous'::text)) IS DISTINCT FROM 'true'::text))"


class ProfileRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='profile-release-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name); self.sql = []; self.empty = False; self.http_status = 403; self.http_error = True; self.migration_failure = False
        self.r = types.ModuleType('synthetic_profile_release'); self.r.target = Mock(return_value={'synthetic_target': True}); self.r.admin = types.SimpleNamespace(query=Mock(side_effect=self.query)); self.r.aws = Mock(return_value={'jobSummaries': [{'jobId': 'synthetic-amplify-job', 'status': 'SUCCEED'}]}); self.r.prior = types.SimpleNamespace(pointers=Mock(return_value={'unchanged-active-version': 'original'}), guard=types.SimpleNamespace(OPEN=types.SimpleNamespace(open=Mock(side_effect=self.open))))
        self.release = self.load(); self.release.ROOT = self.root; self.release.MIGRATION = self.root / 'database/202610230001_user_profiles.sql'; self.release.MIGRATION.parent.mkdir(); self.original = (ROOT / 'database/202610230001_user_profiles.sql').read_bytes(); self.assertEqual(self.release.sha(self.original), self.release.EXPECTED); self.release.MIGRATION.write_bytes(self.original); (self.root / 'cdk.json').write_text(json.dumps({'context': {'supabaseAnonKey': 'synthetic-anonymous-key'}}))
        self.data = dict(columns=[dict(column_name=name, data_type=kind, is_nullable=nullable) for name, kind, nullable in [('id', 'uuid', 'NO'), ('first_name', 'text', 'NO'), ('last_name', 'text', 'NO'), ('timezone', 'text', 'YES')]], query_context=[dict(reader='synthetic-read-only-role', browser_execute=True)], table=[dict(relrowsecurity=True)], policies=[dict(policyname='profile_owner_' + name, permissive='PERMISSIVE', roles=['authenticated'], cmd=cmd, qual=None if cmd == 'INSERT' else OWNER, with_check=None if cmd == 'SELECT' else OWNER) for name, cmd in [('read', 'SELECT'), ('insert', 'INSERT'), ('update', 'UPDATE')]] + [dict(policyname='jumpserve_require_signed_in_user', permissive='RESTRICTIVE', roles=['anon', 'authenticated'], cmd='ALL', qual=SIGNED_IN, with_check=SIGNED_IN)], constraints=[dict(contype=kind, definition=definition) for kind, definition in [('p', 'PRIMARY KEY (id)'), ('f', 'FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE'), ('c', 'CHECK (char_length(first_name) <= 100)'), ('c', 'CHECK (char_length(last_name) <= 100)'), ('c', 'CHECK (profile_timezone_valid(timezone))')]], function=[dict(provolatile='s', prosecdef=False, proconfig=['search_path=""'], definition='Original stable validator definition')])
        self.checks = [dict(ny=True, tokyo=True, utc=True, missing=True, invalid=False, blank=False)]; self.grants = [dict(role='anon', can_read=False, can_insert=False, can_update=False, can_delete=False), dict(role='authenticated', can_read=True, can_insert=True, can_update=True, can_delete=False)]
    def specification(self, original, label, location, *args, **kwargs):
        release = self.r
        class Loader:
            def create_module(self, spec): return release
            def exec_module(self, module): return None
        return importlib.machinery.ModuleSpec(label, Loader()) if Path(location) == ROOT / 'bin/openclaw-release.py' else original(label, location, *args, **kwargs)
    def load(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)):
            spec = original('profile_release_unit', SOURCE); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.encode() == self.original:
            self.assertEqual(options, {'read_only': False})
            if self.migration_failure: raise TimeoutError('Synthetic migration acknowledgement unavailable')
            self.empty = False; return []
        mapping = [('select column_name,', 'columns'), ('select current_user ', 'query_context'), ('select relrowsecurity ', 'table'), ('select policyname,', 'policies'), ('select contype,', 'constraints'), ('select p.provolatile,', 'function')]
        for prefix, key in mapping:
            if sql.startswith(prefix): return [] if self.empty and key in ['columns', 'table', 'function'] else copy.deepcopy(self.data[key])
        if sql.startswith('select public.profile_timezone_valid('): self.assertEqual(options, {'read_only': False}); return copy.deepcopy(self.checks)
        if sql.startswith('select role,has_any_column_privilege('): return copy.deepcopy(self.grants)
        raise AssertionError('Unexpected SQL: ' + sql)
    def open(self, request, timeout):
        self.assertEqual(request.full_url, 'https://regphejnlvfpyokpniny.supabase.co/rest/v1/profiles?select=id&limit=1'); self.assertEqual(request.get_header('Apikey'), 'synthetic-anonymous-key'); self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-anonymous-key'); self.assertEqual(timeout, 25)
        if self.http_error: raise urllib.error.HTTPError(request.full_url, self.http_status, 'Synthetic anonymous denial', {}, None)
        response = io.BytesIO(b''); response.status = self.http_status; return response
    def call(self, mode):
        output = io.StringIO()
        try:
            with patch.object(sys, 'argv', [str(SOURCE), mode]), contextlib.redirect_stdout(output): self.release.main()
            return json.loads(output.getvalue())
        finally:
            if output.getvalue(): self.last = json.loads(output.getvalue())
    def test_inspection_preserves_every_original_security_field_without_mutation(self):
        original = copy.deepcopy(self.data); self.assertEqual(self.release.inspect(), original); self.assertEqual(self.data, original); self.assertEqual(len(self.sql), 6); self.assertTrue(all(not options for _, options in self.sql)); self.r.prior.guard.OPEN.open.assert_not_called()
    def test_verification_checks_owner_policies_grants_timezone_and_anonymous_http_denial(self):
        for status in [401, 403]:
            with self.subTest(status=status):
                self.http_status = status; result = self.release.verify(); self.assertEqual(result['anonymous_profile_http_status'], status); self.assertEqual(result['grants'], self.grants); self.assertEqual(result['timezone_checks'], self.checks); self.assertIn('no data writes', result['validator_probe']); self.assertEqual(result['columns'], self.data['columns'])
        probes = [sql for sql, options in self.sql if options]; self.assertTrue(all(sql.startswith('select public.profile_timezone_valid(') for sql in probes)); self.assertEqual(len(probes), 2)
    def test_column_shape_rls_and_missing_owner_policies_fail_closed(self):
        original = copy.deepcopy(self.data)
        for failure in ['column', 'rls', 'missing-owner']:
            self.data = copy.deepcopy(original)
            if failure == 'column': self.data['columns'][1]['is_nullable'] = 'YES'
            elif failure == 'rls': self.data['table'][0]['relrowsecurity'] = False
            else: self.data['policies'].pop(0)
            with self.subTest(failure=failure), self.assertRaisesRegex(RuntimeError, 'columns differ|RLS is not enabled|owner policies are missing'): self.release.verify()
        self.r.prior.guard.OPEN.open.assert_not_called()
    def test_each_owner_policy_requires_exact_role_command_permissiveness_and_ownership_expression(self):
        original = copy.deepcopy(self.data['policies'])
        for failure in ['role', 'command', 'permissive', 'select-expression', 'insert-expression', 'update-expression']:
            self.data['policies'] = copy.deepcopy(original)
            if failure == 'role': self.data['policies'][0]['roles'] = ['anon', 'authenticated']
            elif failure == 'command': self.data['policies'][0]['cmd'] = 'ALL'
            elif failure == 'permissive': self.data['policies'][0]['permissive'] = 'RESTRICTIVE'
            else: row = self.data['policies'][{'select-expression': 0, 'insert-expression': 1, 'update-expression': 2}[failure]]; row['with_check' if row['cmd'] == 'INSERT' else 'qual'] = 'true'
            with self.subTest(failure=failure), self.assertRaisesRegex(RuntimeError, 'role/command|Owner policy expression'): self.release.verify()
    def test_global_signed_in_restriction_requires_exact_predicates_and_no_extra_policies(self):
        original = copy.deepcopy(self.data['policies'])
        for failure in ['count', 'name', 'roles', 'command', 'permissive', 'qual', 'with_check']:
            self.data['policies'] = copy.deepcopy(original); restriction = self.data['policies'][-1]
            if failure == 'count': self.data['policies'].append(dict(restriction, policyname='unrelated-permissive-policy'))
            elif failure == 'name': restriction['policyname'] = 'different-safety-policy'
            else: restriction[{'roles': 'roles', 'command': 'cmd', 'permissive': 'permissive', 'qual': 'qual', 'with_check': 'with_check'}[failure]] = ['anon'] if failure == 'roles' else 'true'
            with self.subTest(failure=failure), self.assertRaisesRegex(RuntimeError, 'safety policy|signed-in-user'): self.release.verify()
    def test_constraints_and_validator_security_cannot_be_weakened(self):
        original = copy.deepcopy(self.data)
        for failure in ['constraints-count', 'foreign-key', 'primary-key', 'timezone-check', 'function-count', 'volatility', 'security-definer', 'search-path']:
            self.data = copy.deepcopy(original)
            if failure == 'constraints-count': self.data['constraints'].pop()
            elif failure in ['foreign-key', 'primary-key', 'timezone-check']: self.data['constraints'][{'foreign-key': 1, 'primary-key': 0, 'timezone-check': 4}[failure]]['definition'] = 'unprotected'
            elif failure == 'function-count': self.data['function'] = []
            else: self.data['function'][0][{'volatility': 'provolatile', 'security-definer': 'prosecdef', 'search-path': 'proconfig'}[failure]] = True if failure == 'security-definer' else 'wrong'
            with self.subTest(failure=failure), self.assertRaisesRegex(RuntimeError, 'constraints differ|validator security'): self.release.verify()
    def test_timezone_behavior_and_column_grants_are_verified_before_http_access(self):
        original = copy.deepcopy(self.checks); self.checks[0]['invalid'] = True
        with self.assertRaisesRegex(RuntimeError, 'validator behavior'): self.release.verify()
        self.checks = original; self.grants[0]['can_read'] = True
        with self.assertRaisesRegex(RuntimeError, 'grants differ'): self.release.verify()
        self.r.prior.guard.OPEN.open.assert_not_called()
    def test_anonymous_http_success_or_unexpected_failure_cannot_pass_verification(self):
        for status, error in [(200, False), (200, True), (500, True)]:
            self.http_status, self.http_error = status, error
            with self.subTest(status=status, error=error), self.assertRaisesRegex(RuntimeError, 'HTTP read was not denied'): self.release.verify()
        self.http_status, self.http_error = 403, False; self.assertEqual(self.release.verify()['anonymous_profile_http_status'], 403)
    def test_inspect_and_frontend_status_modes_retain_exact_hash_and_unchanged_prompt_pointers(self):
        for mode in ['inspect', 'frontend-status']:
            result = self.call(mode); self.assertEqual(result['status'], 'passed'); self.assertEqual(result['migration_sha256'], self.release.EXPECTED); self.assertTrue(result['active_prompt_settings_preserved']); self.assertIsNone(result['measured_charges_usd']); self.assertEqual(json.loads((Path(result['directory']) / 'receipt.json').read_bytes())['status'], 'passed')
        self.r.aws.assert_called_once_with('amplify', 'list-jobs', '--app-id', 'd24jvguj7brnkj', '--branch-name', 'main', '--max-results', '3'); self.assertFalse(any(sql.encode() == self.original for sql, _ in self.sql))
    def test_existing_profile_schema_is_verified_without_reapplying_a_migration(self):
        for mode in ['apply', 'verify']:
            result = self.call(mode); self.assertEqual(result['status'], 'passed'); self.assertFalse(result['migration_applied']); self.assertEqual(result['verification']['anonymous_profile_http_status'], 403)
        self.assertFalse(any(sql.encode() == self.original for sql, _ in self.sql))
    def test_clean_apply_retains_original_sql_before_submission_and_then_verifies(self):
        self.empty = True; result = self.call('apply'); self.assertTrue(result['migration_applied']); self.assertTrue(result['migration_submission_started']); self.assertEqual((Path(result['directory']) / 'migration-original.sql').read_bytes(), self.original); self.assertEqual(sum(sql.encode() == self.original for sql, _ in self.sql), 1); self.assertEqual(result['status'], 'passed')
    def test_partial_existing_schema_cannot_be_overwritten(self):
        existing = copy.deepcopy(self.data); existing['columns'] = []
        with patch.object(self.release, 'inspect', return_value=existing), self.assertRaisesRegex(RuntimeError, 'partially existing'): self.call('apply')
        self.assertEqual(self.last['status'], 'failed'); self.assertFalse(any(sql.encode() == self.original for sql, _ in self.sql))
    def test_migration_drift_fails_before_target_or_queries_and_preserves_a_failed_receipt(self):
        self.release.MIGRATION.write_bytes(self.original + b'\n-- changed')
        with self.assertRaisesRegex(RuntimeError, 'Unexpected migration bytes'): self.call('apply')
        self.r.target.assert_not_called(); self.assertEqual(self.sql, []); self.assertEqual(self.last['status'], 'failed'); self.assertIn('ended_at', self.last)
    def test_migration_submission_failure_retains_originals_and_does_not_claim_success(self):
        self.empty = True; self.migration_failure = True
        with self.assertRaises(TimeoutError): self.call('apply')
        self.assertEqual(self.last['status'], 'failed'); self.assertTrue(self.last['migration_submission_started']); self.assertNotIn('migration_applied', self.last); self.assertEqual((Path(self.last['directory']) / 'migration-original.sql').read_bytes(), self.original)
    def test_changed_prompt_pointer_makes_an_otherwise_successful_operation_fail(self):
        self.r.prior.pointers.side_effect = [{'active': 'original'}, {'active': 'changed'}]
        with self.assertRaisesRegex(RuntimeError, 'Active prompt settings changed'): self.call('inspect')
        self.assertEqual(self.last['status'], 'failed'); self.assertNotIn('active_prompt_settings_preserved', self.last)
    def test_unknown_cli_mode_exits_before_hash_reads_or_service_adapters(self):
        original = importlib.util.spec_from_file_location
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda *args, **kwargs: self.specification(original, *args, **kwargs)), patch.object(sys, 'argv', [str(SOURCE), 'arbitrary-command']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error: runpy.run_path(str(SOURCE), run_name='__main__')
        self.assertEqual(error.exception.code, 2); self.r.target.assert_not_called(); self.assertEqual(self.sql, []); self.assertFalse((self.root / '.test-artifacts').exists())


if __name__ == '__main__': unittest.main()
