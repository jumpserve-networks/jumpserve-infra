"""Retained read-only project and privacy safeguards with synthetic adapters."""
import copy
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/research-security.py'


class ResearchSecurity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='research-security-unit-')
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
            spec = original('research_security_unit', SOURCE)
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
