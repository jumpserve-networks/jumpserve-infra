"""Unlimited-default release controls with synthetic service boundaries.

Real source/evidence hashes, ZIPs, receipts and fixed SQL are checked locally.
No provider, database, GitHub, AWS or production endpoint is contacted.
"""
import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, Mock, patch
import zipfile

from builder_continuation_release_test import canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/assessment-budget-defaults-release.py'


class BudgetDefaultsRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='budget-default-release-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve() / 'jumpserve-infra'; self.back = self.root.parent / 'jumpserve-back-end'; self.front = self.root.parent / 'jumpserve-front-end'; self.base = self.root / '.test-artifacts/unlimited-defaults-release-v1'; self.base.mkdir(parents=True)
        self.modules = {name: types.ModuleType(name) for name in ['autonomy', 'autonomy_model', 'model_dispatch', 'store', 'workflow']}
        self.autonomy, self.model, self.dispatch, self.store, self.workflow = self.modules.values(); self.workflow.canonical = canonical; self.workflow.digest = digest; self.workflow.paper_details = lambda value: value
        self.autonomy.DEFAULTS = dict(maximum_spend_usd=None, elapsed_days=7); self.autonomy.control = Mock(); self.autonomy.start_payload = lambda study, paper: dict(initial_prompt=canonical(dict(paper=paper, defaults=self.autonomy.DEFAULTS)).decode())
        self.model.TURN_POLICY = {'instruction': 'Synthetic retained turn policy'}; self.model.call = Mock(side_effect=self.call_model); self.model.parse = lambda value: value; self.model.validate_phase = Mock(); self.dispatch.health = Mock(return_value={'status': 'ready'})
        self.store.rows = Mock(side_effect=self.rows); self.store.artifact_bytes = Mock(side_effect=lambda study, ident, **kw: self.objects[ident]); self.store.artifact = Mock(side_effect=self.artifact); self.store.append = Mock(); self.store.service_key = lambda: None
        self.objects = {}; self.sql = []; self.events = {}; self.present = False; self.intake_exists = False; self.intake_created = False; self.fail_db = False; self.policy_drift = False; self.proof = None
        self.enterContext(patch.dict(sys.modules, self.modules)); paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths)); self.release = self.load('budget_defaults_unit')
        for name, value in [('ROOT', self.root), ('BACK', self.back), ('FRONT', self.front), ('BASE', self.base)]: self.enterContext(patch.object(self.release, name, value))
        self.admin = MagicMock(); self.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"; self.admin.query.side_effect = self.query; self.admin.credential.return_value = 'synthetic-management-token'; self.enterContext(patch.object(self.release, 'admin', self.admin))
        self.enterContext(patch.object(self.release.urllib.request, 'urlopen', side_effect=self.open)); self.enterContext(patch.object(self.release.ssl, 'create_default_context', return_value='synthetic-TLS-context')); self.enterContext(patch.object(self.release.subprocess, 'check_output', return_value='synthetic-github-token\n'))
        self.old = {}
        for name in ['autonomy.py', 'policies/autonomy-turn-policy-v1.json', 'policies/autonomous-repair-release-v1.json', 'controller.py']:
            raw = canonical({'synthetic_source': name}) if name.endswith('.json') else ('# Synthetic source ' + name + '\n').encode(); self.runtime(name, raw); self.old[name] = digest(b'old source') if name in ['autonomy.py', 'policies/autonomy-turn-policy-v1.json'] else digest(raw)
        self.write('research-workflow-runtime.json', canonical({'files': self.old})); self.migration = (ROOT / 'database' / self.release.MIGRATION).read_bytes(); self.write('database/' + self.release.MIGRATION, self.migration)
        self.bodies = {name: re.search(r'create (?:or replace )?function public\.' + name + r'\(\) returns trigger.*?as \$\$(.*?)\$\$;', self.migration.decode(), re.S)[1] for name in ['research_autonomy_initial_budget', 'research_assessment_inherit_budget_policy']}
        self.before = [dict(proname='research_autonomy_initial_budget', arguments='', prosrc='Original budget trigger', acl='retained-acl'), dict(proname='research_autonomy_control', arguments='text', prosrc="Original intake 'maximum_spend_usd',100, metadata", acl='retained-acl'), dict(proname='research_unrelated', arguments='', prosrc='Original unrelated body', acl='retained-acl')]
        self.packet = None; self.turns = []; self.dispatches = []

    def load(self, name):
        spec = importlib.util.spec_from_file_location(name, SOURCE); module = importlib.util.module_from_spec(spec); addresses = socket.getaddrinfo; paths = sys.path[:]; original_mkdir = Path.mkdir; actual_base = ROOT / '.test-artifacts/unlimited-defaults-release-v1'
        def mkdir(path, *args, **kwargs): return None if path == actual_base else original_mkdir(path, *args, **kwargs)
        try:
            with patch.dict(os.environ), patch.object(socket, 'getaddrinfo', addresses), patch.object(Path, 'mkdir', mkdir): spec.loader.exec_module(module)
        finally: sys.path[:] = paths
        return module
    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def runtime(self, name, raw):
        path = self.back / 'research_workflow' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def prepare(self): self.packet = self.release.prepare(); return self.packet
    def read(self, name): return self.release.read(name)
    def save(self, name, value): self.release.save(name, value)
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.startswith('select owner_id'): return [{'owner_id': identity('operator')}]
        if sql == self.migration.decode(): self.assertFalse(options['read_only']); self.present = True; return []
        if sql.startswith('begin;'):
            self.assertFalse(options['read_only'])
            if self.fail_db: raise RuntimeError('Synthetic original transaction outcome unconfirmed')
            if "'start'" in sql: self.intake_created = True
            return []
        if sql.startswith('select w.status workflow_status'): return [dict(workflow_status='cancelled', task_status='cancelled')]
        if sql.startswith('select to_regclass('): return [{'present': self.present}]
        if sql.startswith('select p.proname,pg_get_function_identity_arguments'):
            rows = copy.deepcopy(self.before)
            if self.present:
                rows[0]['prosrc'] = self.bodies['research_autonomy_initial_budget']; rows[1]['prosrc'] = rows[1]['prosrc'].replace("'maximum_spend_usd',100,", "'maximum_spend_usd',null,")
                rows.append(dict(proname='research_assessment_inherit_budget_policy', arguments='', prosrc=self.bodies['research_assessment_inherit_budget_policy'], acl='new-private-acl'))
            return rows
        if sql.startswith('select id,max_spend_cents,authorization_text'): return [dict(id='unlimited-assessment-defaults-20261031', max_spend_cents=10000 if self.policy_drift else None, authorization_text='All active and future assessments', authorized_by='Lab operator via Codex conversation, 2026-10-31')]
        if sql.startswith('select prosrc from pg_proc'): return [{'prosrc': self.bodies[next(name for name in self.bodies if name in sql)]}]
        if sql.startswith('select c.relrowsecurity'): return [dict(rls=True, anon_read=False, browser_access=False, runtime_write=False, runtime_read=True)]
        if sql.startswith('select study_id from public.research_autonomy_workflows where status'): return []
        if sql.startswith('select study_id from public.research_autonomy_workflows where study_id='): return [{'study_id': 'retained'}] if self.intake_exists or self.intake_created else []
        if sql.startswith('select status,max_spend_cents,committed_cents'):
            self.assertTrue(self.intake_exists or self.intake_created); payload = self.autonomy.start_payload('unused', self.workflow.paper_details(dict(title='Release verification — future unlimited funding (software fixture)', domain='Software validation', scope='Validate new intake funding and immediately cancel before any model call or experiment.', paper_url='https://example.org/intake-software-fixture', study_kind='paper'))); initial = payload['initial_prompt']
            return [dict(status='cancelled', max_spend_cents=None, committed_cents=500, max_attempts=None, initial_sha256=digest(initial.encode()), initial_prompt=initial, deadline_at='2099-01-01T00:00:00Z')]
        if sql.startswith('select details from public.research_autonomy_events'): return [{'details': dict(max_spend_cents=None, authorization='All active and future assessments', policy_id='unlimited-assessment-defaults-20261031')}]
        if sql.startswith('select count(*)::int count'): return [{'count': 0}]
        if sql.startswith('select study_id,status,max_spend_cents'): return [dict(study_id='444d171c-2fac-4ba9-b33c-2b46304cb0ec', status='running', max_spend_cents=None, committed_cents=500, deadline_at='2099-01-01T00:00:00Z')]
        if sql.startswith('insert into public.platform_events('):
            self.assertFalse(options['read_only']); values = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]; ident, actor, kind, message, raw = values; self.events[ident] = dict(id=ident, kind=kind, message=message, details=json.loads(raw)); return []
        if sql.startswith('select id,kind,message,details'): return [self.events[re.findall(r"'((?:''|[^'])*)'", sql)[0]]]
        raise AssertionError('Unexpected SQL: ' + sql)
    def open(self, request, **options):
        url = request if isinstance(request, str) else request.full_url
        if url.startswith('https://api.supabase.com/'):
            self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-management-token'); self.assertEqual(options['context'], 'synthetic-TLS-context'); return io.BytesIO(canonical([dict(name='other', type='secret', api_key='not-selected'), dict(name='jumpserve_backend_20260921', type='secret', api_key='synthetic-backend-key')]))
        self.assertTrue(url.startswith('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/')); autonomy = dict(defaults={'maximum_spend_usd': None}, workflows=[dict(max_spend_cents=None)])
        return io.BytesIO(canonical({'autonomy': autonomy}))
    def call_model(self, task, context, control):
        self.assertTrue((self.base / 'live-call-intent.json').exists()); self.assertTrue((self.base / 'task-creation-intent.json').exists()); self.assertIsNone(context['remaining_commitment_cents']); self.assertEqual(context['resource_authorization']['committed_cents'], 500)
        return dict(status='complete', output=copy.deepcopy(self.packet['expected']), runtime={'status': 'ready'})
    def rows(self, kind, params):
        self.assertIn('study_id', params)
        if kind == 'autonomy_turns': return copy.deepcopy(self.turns)
        if kind == 'model_dispatches': return copy.deepcopy(self.dispatches)
        raise AssertionError(kind)
    def artifact(self, study, owner, raw, ident, media_type, provenance):
        self.assertEqual(media_type, 'application/zip'); self.assertFalse(provenance['scientific_claim']); self.objects[ident] = raw; return dict(id=ident, sha256=digest(raw), byte_count=len(raw), storage_path=study + '/' + digest(raw))
    def completed(self):
        self.prepare()
        with contextlib.redirect_stdout(io.StringIO()): self.release.qualify()
        raw = canonical(self.packet['expected']); ref = identity('completed-response'); self.objects[ref] = raw; turn = identity('completed-turn')
        self.turns = [dict(id=turn, status='complete', usage={'turn_policy': 'autonomy-turn-policy-v2'}, reserved_cents=100, request={'system': [{'text': 'Synthetic published system'}, {'text': self.model.TURN_POLICY['instruction']}]})]
        self.dispatches = [dict(id=turn, status='complete', response_artifact_id=ref, response_sha256=digest(raw))]
    def proofs(self):
        binding = self.packet['qualified_files_sha256']
        for component in ['frontend', 'infrastructure']:
            repository = 'jumpserve-networks/jumpserve-front-end' if component == 'frontend' else 'jumpserve-networks/jumpserve-infra'; intent = dict(component=component, operation_id=identity(component), repository=repository, revision='a' * 40, workflow_revision='b' * 40); self.save(component + '-verification-intent.json', intent)
            proof = dict(intent, passed=True, evidence={'stacks': [{'qualified_scope': [dict(qualified_files_sha256=binding, all_other_template_content_preserved=True)]}, {}]} if component == 'infrastructure' else {})
            self.save(component + '-production-verification.json', proof)

    def test_source_binding_allows_only_the_two_intended_runtime_changes_and_freezes_a_private_stable_fixture(self):
        old, current, binding = self.release.files(); self.assertEqual(old, self.old); self.assertEqual(binding, digest(canonical({name:value for name,value in sorted(current.items()) if name != 'policies/autonomous-repair-release-v1.json'})))
        first = self.prepare(); self.assertEqual(self.release.prepare(), first); self.assertEqual(first['resources'], dict(maximum_actual_provider_calls=1, maximum_reservation_cents=100, maximum_new_experiments=0, paid_fallback=False)); self.assertEqual((self.base / 'frozen.json').stat().st_mode & 0o777, 0o600)
        self.runtime('controller.py', b'# unrelated changed source\n')
        with self.assertRaises(AssertionError): self.release.files()

    def test_credential_selection_is_project_bound_memory_only_and_network_family_override_is_scoped(self):
        self.assertEqual(self.release.enable_store(), {'status': 'ready'}); self.assertEqual(self.store.service_key(), 'synthetic-backend-key'); self.assertEqual(list(self.base.iterdir()), [])
        with patch.object(self.release, 'original_addresses', return_value=['synthetic-address']) as addresses:
            self.assertEqual(self.release.addresses('api.supabase.com', 443, socket.AF_INET6), ['synthetic-address']); self.assertEqual(addresses.call_args.args[2], socket.AF_INET)
            self.release.addresses('other.invalid', 443, socket.AF_INET6); self.assertEqual(addresses.call_args.args[2], socket.AF_INET6)

    def test_qualification_retains_admission_intent_before_one_call_and_never_resends_its_original_identity(self):
        self.prepare()
        with contextlib.redirect_stdout(io.StringIO()): result = self.release.qualify()
        self.assertEqual(result['status'], 'complete'); self.model.call.assert_called_once(); original = self.read('live-call-intent.json'); before = len(self.sql)
        result = self.release.qualify(); self.assertEqual(result['status'], 'original-call-retained'); self.assertEqual(self.read('live-call-intent.json'), original); self.assertEqual(len(self.sql), before); self.model.call.assert_called_once()
        transaction = next(sql for sql, _ in self.sql if sql.startswith('begin;')); self.assertIn('free existing controller slot', transaction); self.assertIn('Retained qualification exists', transaction)

    def test_deadline_or_uncertain_task_creation_stops_before_model_admission_without_inventing_a_result(self):
        self.prepare(); self.packet['deadline_at'] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)).isoformat(); self.save('frozen.json', self.packet)
        with self.assertRaises(AssertionError): self.release.qualify()
        self.model.call.assert_not_called(); self.packet['deadline_at'] = '2099-01-01T00:00:00Z'; self.save('frozen.json', self.packet); self.fail_db = True
        with self.assertRaisesRegex(RuntimeError, 'transaction outcome unconfirmed'): self.release.qualify()
        self.assertTrue((self.base / 'task-creation-intent.json').exists()); self.assertFalse((self.base / 'live-call-intent.json').exists()); self.model.call.assert_not_called()

    def test_unknown_response_is_retained_without_qualification_and_completed_originals_are_hash_verified_in_private_archive(self):
        self.completed(); self.dispatches[0]['status'] = 'unknown'; result = self.release.collect(); self.assertEqual(result['status'], 'not-qualified'); self.assertTrue(result['provider_call_limit_preserved']); self.assertEqual(self.read('unconfirmed-live-state.json')['dispatch']['status'], 'unknown')
        self.dispatches[0]['status'] = 'complete'; result = self.release.collect(); self.assertTrue(result['passed']); self.assertEqual(result['actual_provider_calls'], 1); raw = (self.base / 'qualification-evidence.zip').read_bytes(); self.assertEqual(digest(raw), result['evidence']['sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as retained:
            self.assertEqual(retained.read('migration.sql'), self.migration); self.assertEqual(json.loads(retained.read('captured-response.json')), self.packet['expected']); self.assertFalse(json.loads(retained.read('qualification-report.json'))['reviewer']['independent']); self.assertNotIn(b'synthetic-backend-key', raw)
        repeated = self.release.collect(); self.assertTrue(repeated['retained_archive_reused']); self.assertEqual(self.store.artifact.call_count, 1); self.model.call.assert_called_once(); self.assertEqual(self.read('fixture-closure-verified.json'), dict(workflow_status='cancelled', task_status='cancelled'))

    def test_approval_requires_original_completed_call_and_administrative_closure_while_leaving_binding_stable(self):
        self.completed(); self.release.collect(); binding = self.release.files()[2]; result = self.release.approve(); self.assertTrue(result['approved_for_lab_recovery']); self.assertEqual(result['qualified_files_sha256'], binding); self.assertEqual(self.release.files()[2], binding)
        self.save('fixture-closure-verified.json', dict(workflow_status='running', task_status='running'))
        with self.assertRaises(AssertionError): self.release.approve()

    def test_production_receipts_follow_only_the_original_scoped_workflow_and_do_not_dispatch_a_replacement(self):
        self.prepare(); self.proofs(); self.proof = None; github = types.ModuleType('platform_supervisor.github'); releases = types.ModuleType('platform_supervisor.releases'); received = []
        github.GitHub = lambda credential: types.SimpleNamespace(token=credential()); releases.Releases = lambda client: types.SimpleNamespace(receipt=lambda value: received.append(value) or self.proof)
        with patch.dict(sys.modules, {'platform_supervisor.github': github, 'platform_supervisor.releases': releases}):
            self.assertEqual(self.release.production_proof('frontend'), {'status': 'waiting-for-original-workflow'}); self.proof = dict(passed=True, component='infrastructure'); self.assertEqual(self.release.production_proof('infrastructure'), self.proof)
        self.assertEqual(received[0]['id'], self.read('frontend-verification-intent.json')['operation_id']); self.assertNotIn('operation_id', received[0]['request']); self.assertEqual(self.read('infrastructure-production-verification.json'), self.proof)

    def test_exact_migration_preserves_other_function_bodies_and_acls_and_rechecks_immutable_policy_and_active_scope(self):
        self.completed(); self.release.collect(); self.proofs(); result = self.release.migrate(); self.assertTrue(result['passed']); self.assertFalse(result['present_before']); self.assertEqual(set(result['changed_functions']), {'research_autonomy_initial_budget', 'research_autonomy_control'}); self.assertTrue(result['other_research_functions_and_acl_preserved']); self.assertTrue(result['all_eligible_active_assessments_unlimited'])
        before = len([sql for sql, _ in self.sql if sql == self.migration.decode()]); self.assertTrue(self.release.migrate()['present_before']); self.assertEqual(len([sql for sql, _ in self.sql if sql == self.migration.decode()]), before)
        self.policy_drift = True
        with self.assertRaises(AssertionError): self.release.migrate()

    def test_new_intake_control_is_cancelled_atomically_without_model_turns_or_jobs_and_reuses_a_retained_intake(self):
        self.prepare(); self.save('migration-applied-and-verified.json', {'passed': True}); result = self.release.verify_intake(); self.assertTrue(result['production_intake_rpc_unlimited']); self.assertTrue(result['qualification_cancelled_before_worker_admission']); self.assertFalse(result['fresh_interactive_google_upload_tested']); self.assertEqual(result['new_model_calls'], 0); self.assertEqual(result['new_experiments'], 0)
        transactions = [sql for sql, _ in self.sql if sql.startswith('begin;')]; self.assertEqual(len(transactions), 1); self.assertIn("'start'", transactions[0]); self.assertIn("'cancel'", transactions[0]); self.release.verify_intake(); self.assertEqual(len([sql for sql, _ in self.sql if sql.startswith('begin;')]), 1); self.model.call.assert_not_called()

    def test_platform_updates_distinguish_in_progress_from_verified_active_defaults_and_retain_original_failed_attempts(self):
        self.prepare(); self.proofs(); (self.base / 'infrastructure-production-verification.json').unlink(); self.save('infrastructure-release-failed-attempt-1.json', {'status': 'failed', 'original_outcome': 'retained'}); result = self.release.record_update(); self.assertFalse(result['future_default_active']); progress = self.read('platform-progress-event-verified.json'); self.assertEqual(progress['details']['failed_attempts'][0]['original_outcome'], 'retained')
        self.proofs(); self.save('migration-applied-and-verified.json', {'passed': True}); self.save('production-new-intake-verified.json', {'passed': True}); self.save('iam-read-repair-verified.json', {'passed': True, 'source': 'synthetic-fixed-repair'}); result = self.release.record_update(); self.assertTrue(result['future_default_active']); complete = self.read('platform-completed-event-verified.json'); self.assertTrue(complete['details']['iam_metadata_repair']['passed']); self.assertNotEqual(progress['id'], complete['id']); self.assertEqual(len(self.events), 2)

    def test_public_reader_rejects_other_origins_and_cli_only_dispatches_fixed_actions_with_owner_identity_omitted(self):
        with self.assertRaises(AssertionError): self.release.public('/private/admin')
        actions = ['prepare', 'qualify', 'collect', 'approve', 'health', 'proof-frontend', 'proof-infrastructure', 'migrate', 'verify-intake', 'record-update']; packet = self.prepare()
        with contextlib.ExitStack() as stack:
            methods = {name: stack.enter_context(patch.object(self.release, name, return_value=packet if name == 'prepare' else {'synthetic': name})) for name in ['prepare', 'qualify', 'collect', 'approve', 'enable_store', 'production_proof', 'migrate', 'verify_intake', 'record_update']}
            for action in actions:
                with self.subTest(action=action), patch.object(sys, 'argv', [str(SOURCE), action]), contextlib.redirect_stdout(io.StringIO()) as stdout:
                    self.release.main(); result = json.loads(stdout.getvalue()); self.assertNotIn('owner_id', result)
            methods['production_proof'].assert_any_call('frontend'); methods['production_proof'].assert_any_call('infrastructure'); methods['enable_store'].assert_called_once()

    def test_entrypoint_rejects_unknown_actions_before_touching_credential_database_or_model_boundaries(self):
        # Re-importing a fresh module also checks import-time environment/DNS
        # restoration; argparse exits before any service operation.
        paths = sys.path[:]
        try:
            with patch.dict(os.environ), patch.object(socket, 'getaddrinfo', socket.getaddrinfo), patch.object(sys, 'argv', [str(SOURCE), 'unknown-unit-action']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                spec = importlib.util.spec_from_file_location('__main__', SOURCE); module = importlib.util.module_from_spec(spec); original_mkdir = Path.mkdir
                def mkdir(path, *args, **kwargs): return None if path == ROOT / '.test-artifacts/unlimited-defaults-release-v1' else original_mkdir(path, *args, **kwargs)
                with patch.object(Path, 'mkdir', mkdir): spec.loader.exec_module(module)
        finally: sys.path[:] = paths
        self.assertEqual(stopped.exception.code, 2); self.admin.query.assert_not_called(); self.model.call.assert_not_called()


if __name__ == '__main__': unittest.main()
