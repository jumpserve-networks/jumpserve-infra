"""Software release receipts with synthetic services and real private file archives.

These checks do not claim a provider qualification or a scientific reproduction.
No cloud API, database connection or production command is executed.
"""
import copy
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import re
import shlex
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('methods_release_unit', ROOT / 'bin/assessment-methods-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
STAMP = '2026-11-01T00:00:00+00:00'
OWNER = 'd48a7797-00a6-4bed-897e-3305ec24e307'
NEW = 'c1553a58-1257-4112-a44d-ae4459500624'


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
def uid(name): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'release-unit:' + name))


class MethodsRelease(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='methods-release-unit-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'infra'; self.back = Path(temp.name) / 'backend'
        self.base = self.root / '.test-artifacts/assessment-methods-release-v1'; self.out = self.base / 'campaign'; self.out.mkdir(parents=True)
        for name, value in [('ROOT', self.root), ('BACK', self.back), ('BASE', self.base)]: self.enterContext(patch.object(release, name, value))
        self.r = MagicMock(); self.r.sha.side_effect = digest; self.r.stamp.return_value = STAMP
        self.r.target.return_value = {'aws_account': 'synthetic-account', 'supabase_project': 'synthetic-project'}
        self.r.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"
        self.r.functions.return_value = {'autonomy': 'synthetic-autonomy'}
        self.enterContext(patch.object(release, 'r', self.r))
        self.pdf, self.text = b'%PDF synthetic original', b'{"pages":[{"page":1,"text":"Synthetic selected statements"}]}'
        self.enterContext(patch.object(release, 'PDF_SHA', digest(self.pdf)))
        self.objects = {release.ORIGINAL + '/' + digest(raw): raw for raw in [self.pdf, self.text]}
        self.storage = self.enterContext(patch.object(release, 'storage', side_effect=self.object))
        claims = [uid('claim-' + str(i)) for i in range(9)]; source_id = uid('source')
        self.data = dict(
            studies=[dict(id=release.ORIGINAL, study_kind='paper', paper_upload={'sha256': digest(self.pdf)}, title='Synthetic paper', paper_url=None, domain='networking', scope='Selected statements', origin_module='research-verification')],
            study_owners=[dict(study_id=release.ORIGINAL, owner_id=OWNER)],
            autonomy_workflows=[dict(status='finished')],
            autonomy_tasks=[dict(id=uid('task-' + c), claim_id=c, status='finished') for c in claims] + [dict(id=uid('intake'), claim_id=None, status='finished')],
            sources=[dict(id=source_id, sha256=digest(self.pdf), retrieval_attempts=[], limitations='Synthetic source fixture')],
            claims=[dict(id=c, source_id=source_id, scope={'page': i + 1}, description='Synthetic statement ' + str(i)) for i, c in enumerate(claims)],
            artifacts=[dict(id=uid(kind), storage_path=release.ORIGINAL + '/' + digest(raw), sha256=digest(raw), byte_count=len(raw), provenance={'kind': kind}) for kind, raw in [('paper-original-upload', self.pdf), ('derived-pdf-text', self.text)]],
            paper_reviews=[dict(status='confirmed', metadata={'authors': ['Synthetic Author'], 'owner_selection': {'central_claims': claims[:4], 'testable_findings': claims[4:]}})])
        self.data['artifacts'].append(dict(id=uid('other'), provenance={'kind': 'unrelated-output'}))
        self.prompts = [dict(version='research-autonomy-v10'), dict(version='research-experiment-builder-v2')]
        self.evaluations = {}; self.new_rows = []; self.invocation = dict(Status='Success', StandardOutputContent='Pinned host source hashes verified: 50')
        self.definition = "else interval '235 seconds' end"; self.grants = [dict(anon=False, authenticated=False)]
        self.r.admin.query.side_effect = self.query; self.r.aws.side_effect = self.aws
        self.write('docs/autonomy-methods-release-protocol-v1.md', b'Synthetic fixed qualification protocol\n')
        self.write('bin/assessment_methods_qualification_host.py', b'# synthetic host entry point\n')
        self.manifest = {'files': {'controller.py': digest(b'# controller\n')}, 'source_revision': 'synthetic-revision'}
        self.write('research-workflow-runtime.json', canonical(self.manifest))
        for name in ['controller.py', 'autonomy_methods.py']:
            path = self.back / 'research_workflow' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(('# ' + name + '\n').encode())

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def saved(self, name, value, directory=None):
        path = (directory or self.out) / name; path.parent.mkdir(parents=True, exist_ok=True); release.save(path, value); return path
    def object(self, path, raw=None):
        if raw is not None:
            self.assertNotIn(path, self.objects); self.objects[path] = raw; return b''
        return self.objects[path]
    def query(self, sql, **options):
        if sql.startswith('select to_jsonb(t) record from public.research_'):
            kind = sql.split('public.research_')[1].split()[0]; self.assertIn(release.ORIGINAL, sql)
            return [{'record': copy.deepcopy(v)} for v in self.data[kind]]
        if sql.startswith('select v.id,v.module_id'): return copy.deepcopy(self.prompts)
        if sql.startswith('select id from public.research_studies'): return copy.deepcopy(self.new_rows)
        if sql.startswith('select s.id,w.status'): return copy.deepcopy(self.new_rows)
        if sql.startswith('begin;'):
            self.assertFalse(options['read_only']); self.executed_sql = sql; return []
        if sql.startswith('select pg_get_functiondef'): return [{'definition': self.definition}]
        if sql.startswith('select has_function_privilege'): return self.grants
        if sql.startswith('insert into agent_prompt_evaluations'):
            self.assertFalse(options['read_only']); values = [v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", sql)]
            prompt, outcome, raw, sha = values[:4]; self.assertEqual(digest(raw.encode()), sha)
            self.evaluations[(prompt, sha)] = raw; return []
        if sql.startswith('select report_raw from agent_prompt_evaluations'):
            values = [v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", sql)]
            return [{'report_raw': self.evaluations[tuple(values)]}]
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        if (service, operation) == ('lambda', 'get-function-configuration'):
            return {'Environment': {'Variables': {'NETWORK_EXECUTOR_FUNCTION': 'executor', 'NETWORK_PACKAGE_POLICY_SHA256': 'f' * 64, 'NETWORK_SECRET': 'private', 'OTHER_FUNCTION': 'excluded'}}}
        if (service, operation) == ('ssm', 'get-command-invocation'): return self.invocation
        if (service, operation) == ('cloudformation', 'describe-stacks'): return {'Stacks': [{'StackStatus': 'UPDATE_COMPLETE'}]}
        raise AssertionError((service, operation, args))

    def test_private_snapshot_retrieves_only_exact_originals_and_fixed_published_prompts(self):
        result = release.inspect(self.out)
        self.assertEqual((result['selected_claims'], result['originals_verified']), (9, 2))
        originals = json.loads((self.out / 'originals.json').read_bytes())
        for record in originals.values():
            path = self.out / record['file']; self.assertEqual(digest(path.read_bytes()), record['sha256']); self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.out / 'private-snapshot.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.storage.call_args_list), 2)

    def test_inspection_rejects_changed_source_identity_running_work_and_bad_original_bytes(self):
        mutations = [lambda: self.data['studies'][0].update(study_kind='idea'), lambda: self.data['studies'][0]['paper_upload'].update(sha256='0' * 64), lambda: self.data['autonomy_tasks'][0].update(status='waiting'), lambda: self.data['autonomy_tasks'].pop(0), lambda: self.data['artifacts'][0].update(storage_path='another-assessment/object'), lambda: self.data['artifacts'][0].update(byte_count=1), lambda: self.objects.update({release.ORIGINAL + '/' + digest(self.pdf): b'altered'}), lambda: self.prompts.pop()]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data, objects, prompts = copy.deepcopy(self.data), dict(self.objects), list(self.prompts)
                mutation()
                with self.assertRaises(AssertionError): release.inspect(self.out)
                self.data, self.objects, self.prompts = data, objects, prompts

    def test_freeze_retains_runtime_originals_and_exact_archive_manifest_without_private_environment(self):
        result = release.freeze(self.out); self.assertEqual(result['runtime_files'], 2)
        packet = json.loads((self.out / 'frozen.json').read_bytes())
        self.assertEqual(packet['execution_environment'], {'NETWORK_EXECUTOR_FUNCTION': 'executor', 'NETWORK_PACKAGE_POLICY_SHA256': 'f' * 64})
        self.assertEqual((packet['maximum_live_calls'], packet['maximum_elapsed_seconds']), (30, 3600))
        self.assertFalse(packet['evaluator']['independent']); self.assertEqual(release.current(), self.out)
        item = json.loads((self.out / 'candidate.json').read_bytes()); raw = self.objects[item['path']]
        self.assertEqual((digest(raw), len(raw)), (item['sha256'], item['bytes']))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for entry in json.loads(archive.read('candidate-manifest.json')):
                original = archive.read(entry['path']); self.assertEqual((digest(original), len(original)), (entry['sha256'], entry['bytes']))
            self.assertEqual(archive.read('research_workflow/autonomy_methods.py'), (self.back / 'research_workflow/autonomy_methods.py').read_bytes())

    def test_followup_preserves_call_accounting_and_elapsed_time_instead_of_resetting(self):
        self.saved('followup.json', dict(previous_campaign='original', previous_provider_calls=22, remaining_seconds=900))
        release.freeze(self.out); packet = json.loads((self.out / 'frozen.json').read_bytes())
        self.assertEqual((packet['followup_of'], packet['maximum_live_calls'], packet['maximum_elapsed_seconds'], packet['case_selection']), ('original', 8, 900, ['source-injection']))
        next_out = self.base / 'continuation'; next_out.mkdir()
        self.saved('followup.json', dict(previous_campaign='original', previous_provider_calls=30, remaining_seconds=500, maximum_aggregate_calls=50, aggregate_started_at=STAMP, case_selection=[]), next_out)
        release.freeze(next_out); packet = json.loads((next_out / 'frozen.json').read_bytes())
        self.assertEqual((packet['maximum_live_calls'], packet['aggregate_started_at'], packet['case_selection']), (20, STAMP, []))

    def test_unconfirmed_candidate_roundtrip_does_not_select_a_campaign(self):
        def changed(path, raw=None):
            if raw is not None: return self.object(path, raw)
            return b'changed'
        self.storage.side_effect = changed
        with self.assertRaises(AssertionError): release.freeze(self.out)
        self.assertFalse((self.base / 'selected.txt').exists())

    def test_prepare_installs_verified_manifest_and_rejects_traversal_or_changed_bytes(self):
        release.freeze(self.out); self.r.ssm.return_value = {'command_id': 'synthetic-command'}
        self.assertEqual(release.prepare(self.out), {'command_id': 'synthetic-command'})
        receipt = json.loads((self.out / 'prepare-command.json').read_bytes()); commands = self.r.ssm.call_args.args[0]
        self.assertTrue(commands[-1].endswith(receipt['host'])); program = shlex.split(commands[-2])[-1]
        host = self.root / 'host'; program = program.replace(repr(receipt['host']), repr(str(host)))
        store = types.ModuleType('store'); store.request = lambda path, **kw: self.objects[path.split('research-workflow-raw/')[1]]
        workflow = types.ModuleType('workflow'); workflow.digest = digest
        with patch.dict(sys.modules, {'store': store, 'workflow': workflow}), patch.object(sys, 'path', list(sys.path)):
            exec(compile(program, '<manifest-install>', 'exec'), {})
        self.assertEqual((host / 'research_workflow/controller.py').read_bytes(), (self.back / 'research_workflow/controller.py').read_bytes())
        with self.assertRaises(AssertionError): release.prepare(self.out)
        for path in ['../escape', '/absolute']:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                archive.writestr('candidate-manifest.json', json.dumps([{'path': path, 'sha256': digest(b'payload')}]))
                archive.writestr(path, b'payload')
            altered = buffer.getvalue(); attack = program.replace(repr(str(host)), repr(str(self.root / ('bad-' + path.replace('/', '_')))))
            attack = attack.replace(repr(json.loads((self.out / 'candidate.json').read_bytes())['sha256']), repr(digest(altered)))
            store.request = lambda *a, **kw: altered
            with self.subTest(path=path), patch.dict(sys.modules, {'store': store, 'workflow': workflow}), patch.object(sys, 'path', list(sys.path)), self.assertRaises(AssertionError): exec(compile(attack, '<manifest-install>', 'exec'), {})

    def rerun_plan(self):
        release.inspect(self.out)
        workflow = types.ModuleType('workflow'); workflow.FIELDS = {k: tuple(self.data[k][0]) for k in ['sources', 'claims']}; workflow.canonical = canonical
        workflow.validate_record = MagicMock(side_effect=lambda kind, record: record)
        autonomy = types.ModuleType('autonomy'); autonomy.start_payload = MagicMock(return_value={'initial_prompt': '{"version":"synthetic"}'})
        with patch.dict(sys.modules, {'workflow': workflow, 'autonomy': autonomy}), patch.object(sys, 'path', list(sys.path)):
            result = release.plan_rerun(self.out)
        return result

    def test_rerun_plan_is_stable_atomic_owner_bound_and_copies_no_measurements_or_verdicts(self):
        selected = self.data['paper_reviews'][0]['metadata']['owner_selection']
        self.data['paper_reviews'][0]['metadata']['selection'] = {'central_claims': [{'claim_id': v} for v in selected['central_claims']] + [{'claim_id': uid('unselected')}], 'testable_findings': [{'claim_id': v} for v in selected['testable_findings']], 'nested': {'ids': [selected['central_claims'][0], 0, None]}}
        before = copy.deepcopy(self.data); first = self.rerun_plan(); sql = (self.out / 'new-assessment.sql').read_text()
        self.assertEqual(self.rerun_plan(), first); self.assertEqual((self.out / 'new-assessment.sql').read_text(), sql); self.assertEqual(self.data, before)
        self.assertTrue(sql.startswith('begin;')); self.assertTrue(sql.endswith('commit;\n')); self.assertIn('pg_advisory_xact_lock', sql)
        for operation in ['research_paper_upload', 'research_append_bundle', 'research_autonomy_control', 'research_paper_review']:
            self.assertIn(operation, sql)
        self.assertIn(OWNER, sql); self.assertNotIn('insert into public.research_measurements', sql); self.assertNotIn('insert into public.research_assessments', sql)
        plan = json.loads((self.out / 'rerun-plan.json').read_bytes()); self.assertEqual((len(plan['mapped_claims']), plan['selected_claims']), (9, 9))
        self.assertEqual(digest(sql.encode()), plan['sql_sha256']); self.assertEqual(first['status'], 'planned-not-created')
        self.assertEqual((self.out / 'new-assessment.sql').stat().st_mode & 0o777, 0o600)
        self.assertFalse(any(c.kwargs.get('read_only') is False for c in self.r.admin.query.call_args_list))

    def test_rerun_dry_run_rolls_back_and_preserves_original_snapshot(self):
        self.rerun_plan(); result = release.create_rerun(self.out, dry_run=True)
        self.assertEqual(result['mode'], 'rollback-dry-run'); self.assertTrue(self.executed_sql.endswith('rollback;\n'))
        self.assertFalse((self.out / 'new-assessment-original-copy-receipt.json').exists())

    def test_rerun_creation_requires_qualified_release_copies_exact_originals_and_reconciles_existing_identity(self):
        self.rerun_plan(); plan = json.loads((self.out / 'rerun-plan.json').read_bytes())
        self.saved('release-verified.json', {'status': 'passed', 'campaign': self.out.name}, self.base)
        query = self.query
        def created(sql, **kw):
            if sql.startswith('select s.id,w.status'): return [{'id': plan['id'], 'max_spend_cents': 10000, 'max_attempts': None, 'claims': 9}]
            return query(sql, **kw)
        self.r.admin.query.side_effect = created; result = release.create_rerun(self.out)
        self.assertEqual(result['mode'], 'created'); self.assertTrue(result['original_unchanged'])
        copies = json.loads((self.out / 'new-assessment-original-copy-receipt.json').read_bytes())
        self.assertEqual(len(copies), 2); self.assertTrue(all(v['sha256'] == v['retrieved_sha256'] for v in copies))
        self.new_rows = [{'id': plan['id']}]
        with self.assertRaisesRegex(AssertionError, 'already exists'): release.create_rerun(self.out)

    def test_changed_rerun_sql_and_changed_originals_are_not_executed(self):
        self.rerun_plan(); sql = self.out / 'new-assessment.sql'; sql.write_text(sql.read_text() + '-- altered')
        with self.assertRaises(AssertionError): release.create_rerun(self.out, dry_run=True)
        self.assertFalse(hasattr(self, 'executed_sql'))

    def test_model_window_migration_is_guarded_idempotent_and_verifies_actual_definition(self):
        migration = self.write('database/202610280001_data_only_model_window.sql', b'-- synthetic migration')
        result = release.migrate_window(); self.assertTrue(result['present_before']); self.assertEqual(result['sha256'], digest(migration.read_bytes())); self.r.auth_maintenance_guard.assert_called_once()
        self.definition = "else interval '100 seconds' end"; query = self.query
        def apply(sql, **options):
            if sql == migration.read_text(): self.definition = "else interval '235 seconds' end"; self.assertFalse(options['read_only']); return []
            return query(sql, **options)
        self.r.admin.query.side_effect = apply; self.assertFalse(release.migrate_window()['present_before'])
        self.r.auth_maintenance_guard.side_effect = RuntimeError('active uncertain call')
        self.r.admin.query.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'uncertain'): release.migrate_window()
        self.r.admin.query.assert_not_called()

    def test_held_verification_requires_all_three_functions_and_completed_stack(self):
        self.saved('qualification-recorded.json', {'status': 'passed', 'campaign': self.out.name}, self.base)
        self.r.prior.functions.return_value = [{'source_hashes': {str(i): 'a' * 64 for i in range(50)}} for _ in range(3)]
        self.assertTrue(release.verify_held(self.out, self.out)['admission_held'])
        self.r.prior.functions.return_value.pop()
        with self.assertRaises(AssertionError): release.verify_held(self.out, self.out)

    def test_production_verification_requires_matching_source_and_later_successful_host_receipt(self):
        self.saved('qualification-recorded.json', {'status': 'passed', 'campaign': self.out.name}, self.base)
        self.saved('frozen.json', {'runtime_files': self.manifest['files']}); self.saved('qualification-report.json', {'ended_at': '2026-10-30'})
        activated = dict(mode='activated', status='complete', functions=[{'source_files_verified': 50, 'built_executor': 'arn:aws:lambda:region:account:function:fixed-executor:7'}], security={'private': True}, polling={'enabled': True})
        self.write('.test-artifacts/builder-production-v2/01/receipt.json', canonical(activated))
        self.write('.test-artifacts/builder-production-v2/02/receipt.json', canonical(dict(mode='executor', status='complete', function='fixed-executor')))
        self.write('.test-artifacts/openclaw-release/01/receipt.json', canonical(dict(mode='host-check', started_at='2026-10-31', ssm={'command_id': 'retained-command', 'instance_id': 'i-087f1493809643115'})))
        self.r.instance.return_value = 'i-087f1493809643115'
        result = release.verify_release(self.out); self.assertEqual(result['runtime_files_verified'], 50); self.assertEqual(len(result['conditional_gaps']), 2)
        self.assertIsNone(result['measured_charges_usd']); self.assertNotIn('qualification', result)
        for field, value in [('Status', 'Failed'), ('StandardOutputContent', 'nothing verified')]:
            previous = self.invocation[field]; self.invocation[field] = value
            with self.assertRaises(AssertionError): release.verify_release(self.out)
            self.invocation[field] = previous
        self.grants = [dict(anon=True, authenticated=False)]
        with self.assertRaises(AssertionError): release.verify_release(self.out)

    def test_progress_preserves_unknown_cost_and_retains_private_details_separately(self):
        self.saved('rerun-plan.json', {'id': NEW}); queries = []
        def query(sql, **kw):
            queries.append(sql); self.assertIn(NEW, sql); self.assertNotIn('read_only', kw)
            if 'from research_autonomy_tasks' in sql: return [dict(claim_id=uid('claim'), stage='build', status='waiting', label=None, attempts=2, reason='Retained repair')]
            if 'from research_autonomy_turns' in sql: return [{'status': 'unknown'}, {'status': 'completed'}, {'status': 'completed'}]
            return []
        self.r.admin.query.side_effect = query; result = release.observe_rerun(self.out, self.out)
        self.assertEqual(result['turn_statuses'], {'unknown': 1, 'completed': 2}); self.assertIsNone(result['measured_charges_usd'])
        self.assertEqual(len(queries), 7); self.assertEqual(json.loads((self.out / 'private-progress.json').read_bytes())['id'], NEW)

    def archive(self, values):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, raw in values.items(): archive.writestr(name, raw)
            archive.writestr('artifact-manifest.json', json.dumps([{'path': name, 'sha256': digest(raw), 'bytes': len(raw)} for name, raw in values.items()]))
        return stream.getvalue()

    def qualification_history(self):
        previous = None
        for i, calls in enumerate([6, 16, 8, 20]):
            campaign = self.out if i == 3 else self.base / ('prior-' + str(i)); campaign.mkdir(exist_ok=True)
            frozen = {'runtime_files': {'controller.py': 'f' * 64}}
            if previous is not None: frozen['followup_of'] = previous.name
            self.saved('frozen.json', frozen, campaign)
            report = {'status': 'awaiting-substantive-review' if i == 3 else 'failed-or-paused', 'live_provider_calls': calls}
            self.saved('qualification-report.json', report, campaign)
            (campaign / 'qualification.zip').write_bytes(self.archive({'report.json': canonical(report), 'actual-output.txt': ('retained-output-' + str(i)).encode()}))
            previous = campaign
        review = dict(status='passed', campaign=self.out.name, reviewer={'type': 'AI', 'independent': False})
        self.write('docs/autonomy-methods-actual-answer-review-v1.json', canonical(review))
        self.write('.test-artifacts/autonomy-methods-v1-infra-unit.log', b'Synthetic infrastructure unit receipt')
        self.write('.test-artifacts/research-ideas/database/20261028T022109194960Z/method-window-validation.json', b'{"synthetic":true}')
        self.write('database/202610280001_data_only_model_window.sql', b'-- synthetic migration')
        backend_log = self.back / '.test-artifacts/autonomy-methods-v1/release-backend-unit-v4.log'; backend_log.parent.mkdir(parents=True); backend_log.write_bytes(b'Synthetic backend unit receipt')

    def test_qualification_preserves_all_failed_campaigns_and_records_only_final_review_as_passed(self):
        self.qualification_history(); result = release.record_qualification(self.out)
        self.assertEqual((result['aggregate_provider_calls'], len(result['evaluations'])), (50, 8))
        self.assertEqual([v['outcome'] for v in result['evaluations']], ['failed-or-paused'] * 6 + ['passed'] * 2)
        self.assertEqual(len(self.evaluations), 8); self.assertFalse(result['archive']['public'])
        for raw in self.evaluations.values():
            value = json.loads(raw); self.assertFalse(value['reviewer']['independent']); self.assertIsNone(value['measured_charges_usd'])
            self.assertEqual(len(value['history']), 4); self.assertTrue(value['historical_prompt_publication_unchanged'])
            self.assertEqual(value['review'] is None, value['status'] != 'passed')
        with zipfile.ZipFile(io.BytesIO(self.objects[result['archive']['path']])) as archive:
            for entry in json.loads(archive.read('artifact-manifest.json')):
                self.assertEqual(digest(archive.read(entry['path'])), entry['sha256'])
            self.assertIn('prior-0/qualification.zip', archive.namelist()); self.assertIn('actual-answer-review.json', archive.namelist())

    def test_qualification_rejects_excess_calls_unreviewed_or_corrupted_evidence_before_recording(self):
        self.qualification_history(); report_path = self.out / 'qualification-report.json'; original = report_path.read_bytes()
        report = json.loads(original); report['live_provider_calls'] += 1; report_path.write_bytes(canonical(report))
        with self.assertRaises(AssertionError): release.record_qualification(self.out)
        self.assertFalse(self.evaluations); report_path.write_bytes(original)
        review = self.root / 'docs/autonomy-methods-actual-answer-review-v1.json'; original_review = review.read_bytes()
        value = json.loads(original_review); value['reviewer']['independent'] = True; review.write_bytes(canonical(value))
        with self.assertRaises(AssertionError): release.record_qualification(self.out)
        review.write_bytes(original_review)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('artifact-manifest.json', json.dumps([{'path': 'original', 'sha256': digest(b'original')}]))
            archive.writestr('original', b'changed')
        (self.out / 'qualification.zip').write_bytes(stream.getvalue())
        with self.assertRaises(AssertionError): release.record_qualification(self.out)
        self.assertFalse(self.evaluations); self.assertFalse(any(c.args[1:] for c in self.storage.call_args_list))

    def release_receipts(self):
        self.saved('release-verified.json', dict(status='passed', campaign=self.out.name, backend_revision='synthetic-revision', conditional_gaps=['Scientific completion remains unproven.']), self.base)
        self.saved('rerun-created.json', {'mode': 'created', 'id': NEW, 'original_unchanged': True})
        self.saved('report.json', {'passed': True, 'assessment_id': NEW}, self.base / 'browser/20261101')
        self.saved('private-snapshot.json', {'private': 'excluded'}); self.saved('published-prompts.json', {'private': 'excluded'}); self.saved('rerun-plan.json', {'private': 'excluded'})
        for name in ['docs/autonomy-methods-v1-validation.md', 'docs/autonomy-methods-actual-answer-review-v1.json', 'docs/autonomy-methods-qualification-artifacts-v1.json', 'bin/assessment-methods-release.py', 'bin/verify_assessment_methods_browser.mjs', 'database/202610280001_data_only_model_window.sql']:
            self.write(name, b'Synthetic release input: ' + name.encode())
        for name in ['receipt.json', 'cdk.log', 'outputs.json', 'parameter-comparison.json', 'candidate.zip', 'excluded.txt']:
            self.write('.test-artifacts/openclaw-release/20261101/' + name, b'Synthetic retained original ' + name.encode())
        self.write('.test-artifacts/openclaw-release/20261001/receipt.json', b'Old unselected receipt')
        (self.out / 'excluded.txt').write_text('Not a release input')

    def test_release_archive_keeps_operational_and_scientific_outcomes_distinct(self):
        self.release_receipts(); result = release.record_release(self.out, self.out)
        self.assertFalse(result['scientific_completion']); self.assertEqual(result['assessment_id'], NEW); self.assertEqual(result['maximum_spend_usd'], 100)
        self.assertIsNone(result['measured_charges_usd']); self.assertEqual(len(self.evaluations), 2)
        value = json.loads(next(iter(self.evaluations.values())))
        self.assertEqual(value['status'], 'passed-software-gates-background-scientific-assessment-running'); self.assertFalse(value['reviewer']['human']); self.assertFalse(value['reviewer']['independent'])
        raw = self.objects[value['archive']['path']]
        self.assertEqual(digest(raw), result['archive']['sha256']); self.assertEqual(result['archive']['sha256'], result['archive']['retrieved_sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            self.assertIn('openclaw-release/20261101/candidate.zip', names)
            self.assertNotIn('openclaw-release/20261001/receipt.json', names)
            self.assertFalse(any(Path(name).name in ['private-snapshot.json', 'published-prompts.json', 'rerun-plan.json', 'excluded.txt'] for name in names))
        self.assertEqual(json.loads((self.root / 'docs/autonomy-methods-production-status-v1.json').read_bytes()), result)

    def test_release_record_requires_exact_created_assessment_and_successful_browser_check(self):
        self.release_receipts(); path = self.base / 'browser/20261101/report.json'
        for report in [{'passed': False, 'assessment_id': NEW}, {'passed': True, 'assessment_id': uid('wrong-assessment')}]:
            path.write_bytes(canonical(report))
            with self.assertRaises(AssertionError): release.record_release(self.out, self.out)
        self.assertFalse(self.evaluations); self.storage.assert_not_called()

    def cli(self, mode):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['assessment-methods-release.py', mode]), contextlib.redirect_stdout(output): release.main()
        return json.loads(output.getvalue())

    def selected(self): (self.base / 'selected.txt').write_text(self.out.name + '\n')

    def test_cli_dispatch_writes_complete_or_failed_receipt_and_never_replays_start(self):
        self.selected(); self.saved('prepare-command.json', {'command_id': 'prepared', 'instance_id': 'synthetic-instance', 'host': '/synthetic/host'})
        self.saved('frozen.json', {'maximum_live_calls': 30}); self.r.ssm.return_value = {'command_id': 'original-dispatch', 'instance_id': 'synthetic-instance'}
        receipt = self.cli('start'); self.assertEqual(receipt['status'], 'complete'); self.assertEqual(receipt['aggregate_remaining_seconds'], 3600)
        commands = self.r.ssm.call_args.args[0]; self.assertIn('RuntimeMaxSec=3600', commands[0]); self.assertIn('/synthetic/host/qualify.py', commands[0])
        self.r.ssm.reset_mock()
        with self.assertRaisesRegex(AssertionError, 'Never replay'): self.cli('start')
        self.r.ssm.assert_not_called()
        receipts = sorted(self.base.glob('*/receipt.json')); failed = [json.loads(p.read_bytes()) for p in receipts if json.loads(p.read_bytes())['status'] == 'failed']
        self.assertEqual(len(failed), 1); self.assertIn('Never replay', failed[0]['reason']); self.assertIn('ended_at', failed[0])

    def test_cli_retained_pending_does_not_download_and_completed_retention_verifies_original(self):
        self.selected(); self.saved('retain-command.json', {'command_id': 'retained', 'instance_id': 'synthetic-instance'})
        for status in ['Pending', 'InProgress', 'Delayed']:
            self.invocation = {'Status': status}; self.assertEqual(self.cli('retained')['status'], 'pending')
        self.storage.assert_not_called()
        raw = self.archive({'report.json': canonical({'status': 'failed-or-paused', 'live_provider_calls': 3}), 'provider-output.txt': b'Original unconfirmed output'})
        item = dict(path='retained-archive', sha256=digest(raw), retrieved_sha256=digest(raw)); self.objects[item['path']] = raw
        self.invocation = {'Status': 'Success', 'StandardOutputContent': json.dumps(item)}
        self.assertEqual(self.cli('retained')['status'], 'complete'); self.assertEqual((self.out / 'qualification.zip').read_bytes(), raw)
        self.assertEqual(json.loads((self.out / 'qualification-report.json').read_bytes())['status'], 'failed-or-paused')
        self.invocation = {'Status': 'Failed', 'StandardErrorContent': 'Actual host failure'}
        with self.assertRaisesRegex(AssertionError, 'Actual host failure'): self.cli('retained')

    def test_cli_collection_without_archive_keeps_partial_state_and_does_not_claim_verification(self):
        self.selected(); self.saved('status-command.json', {'command_id': 'status-command', 'instance_id': 'synthetic-instance'})
        self.invocation = {'Status': 'Success', 'StandardOutputContent': json.dumps({'status': 'running', 'calls': 2, 'archive': None})}
        result = self.cli('collect'); self.assertEqual(result['remote']['status'], 'running'); self.assertNotIn('archive_verified', result); self.storage.assert_not_called()
        self.assertFalse((self.out / 'qualification-report.json').exists())

    def test_cli_routes_named_operations_and_records_the_exact_result_under_the_selected_campaign(self):
        self.selected()
        routes = [('prepare', 'prepare', 'command'), ('record-qualification', 'record_qualification', 'qualification'), ('migrate-window', 'migrate_window', 'migration'), ('verify-release', 'verify_release', 'verification'), ('verify-held', 'verify_held', 'verification'), ('observe-rerun', 'observe_rerun', 'progress'), ('record-release', 'record_release', 'release_record'), ('plan-rerun', 'plan_rerun', 'rerun'), ('dry-run-rerun', 'create_rerun', 'rerun'), ('create-rerun', 'create_rerun', 'rerun')]
        for mode, function, key in routes:
            with self.subTest(mode=mode), patch.object(release, function, return_value={'operation': mode}) as handler:
                receipt = self.cli(mode); self.assertEqual(receipt[key], {'operation': mode}); self.assertEqual(receipt['campaign'], self.out.name); self.assertEqual(receipt['status'], 'complete')
                handler.assert_called_once()
                if function == 'create_rerun': self.assertEqual(handler.call_args.kwargs, {'dry_run': mode == 'dry-run-rerun'})
                if mode != 'migrate-window': self.assertEqual(handler.call_args.args[0], self.out)
        inspected = self.cli('inspect'); self.assertEqual(inspected['inspection']['selected_claims'], 9)

    def test_cli_freeze_refuses_to_replace_a_selected_campaign_and_amendment_is_pre_dispatch_only(self):
        first = self.cli('freeze'); selected = release.current(); self.assertEqual(first['candidate']['runtime_files'], 2)
        with self.assertRaisesRegex(AssertionError, 'already frozen'): self.cli('freeze')
        amendment = self.cli('amend'); revised = release.current(); self.assertNotEqual(revised, selected)
        record = json.loads((revised / 'pre-live-amendment.json').read_bytes()); self.assertEqual(record['previous_campaign'], selected.name); self.assertEqual(record['previous_provider_calls'], 0)
        self.assertEqual(amendment['status'], 'complete'); self.r.ssm.assert_not_called()
        self.saved('prepare-command.json', {'command_id': 'already-dispatched'}, revised)
        with self.assertRaisesRegex(AssertionError, 'pre-dispatch'): self.cli('amend')

    def test_followup_preserves_original_unknown_request_and_subtracts_calls_and_elapsed_time(self):
        self.selected(); started = dt.datetime.now(dt.timezone.utc).isoformat()
        self.saved('qualification-report.json', dict(status='failed-or-paused', live_provider_calls=6, started_at=started))
        self.saved('archive-recovery.json', {'sha256': 'a' * 64, 'retrieved_sha256': 'a' * 64})
        result = self.cli('followup'); frozen = json.loads((release.current() / 'frozen.json').read_bytes())
        self.assertEqual(result['status'], 'complete'); self.assertEqual(frozen['maximum_live_calls'], 24); self.assertLessEqual(frozen['maximum_elapsed_seconds'], 3600); self.assertGreater(frozen['maximum_elapsed_seconds'], 180)
        self.assertEqual(frozen['followup_of'], self.out.name); self.assertEqual(json.loads((self.out / 'qualification-report.json').read_bytes())['status'], 'failed-or-paused')

    def resume_archive(self, continuation=False):
        checkpoint = b'Original retained native checkpoint'; job = {'id': uid('native-job')}; reference = {'sha256': digest(checkpoint)}
        values = {'native-ledger.jsonl': canonical({'job': job}) + b'\n', 'native-slice-2/receipt.json': canonical({'checkpoint': reference}), 'candidate/candidate-compiled.json': canonical({'protocol': {'decision': {'claim_id': uid('claim')}}}), 'native/' + job['id'] + '/checkpoint.zip': checkpoint}
        (self.out / 'qualification.zip').write_bytes(self.archive(values))
        if continuation: return checkpoint, job, reference
        return checkpoint

    def test_repair_followup_and_contract_amendment_restore_retained_checkpoint_without_repeating_setup(self):
        self.selected(); first = self.base / 'first'; first.mkdir(); self.saved('qualification-report.json', {'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}, first)
        self.saved('frozen.json', {'followup_of': first.name, 'previous_provider_calls': 6})
        self.saved('qualification-report.json', {'status': 'failed-or-paused', 'reason': 'ValueError: A package needs mode, package, arguments and parameters.', 'live_provider_calls': 16})
        checkpoint = self.resume_archive(); result = self.cli('repair-followup'); repaired = release.current()
        self.assertEqual(result['status'], 'complete'); self.assertEqual((repaired / 'resume-checkpoint.zip').read_bytes(), checkpoint)
        resume = json.loads((repaired / 'native-resume.json').read_bytes()); self.assertIn('mode=loopback is invalid', resume['feedback'])
        frozen = json.loads((repaired / 'frozen.json').read_bytes()); self.assertEqual((frozen['previous_provider_calls'], frozen['maximum_live_calls']), (22, 8))
        amended = self.cli('contract-amend'); target = release.current(); self.assertEqual(amended['status'], 'complete')
        self.assertEqual((target / 'resume-checkpoint.zip').read_bytes(), checkpoint); self.assertIn('ONLY name and units', json.loads((target / 'native-resume.json').read_bytes())['feedback'])
        self.r.ssm.assert_not_called()

    def test_native_continuation_keeps_all_thirty_prior_calls_and_the_original_absolute_deadline(self):
        self.selected(); checkpoint, job, reference = self.resume_archive(True); started = dt.datetime.now(dt.timezone.utc).isoformat()
        self.saved('native-resume.json', {'feedback': 'Original feedback'})
        self.saved('frozen.json', {'previous_provider_calls': 22, 'aggregate_started_at': started})
        self.saved('qualification-report.json', {'status': 'failed-or-paused', 'live_provider_calls': 8, 'native': {'slices': [{'admission_denied': 'qualification-budget', 'checkpoint': reference}]}})
        result = self.cli('native-continuation'); target = release.current(); self.assertEqual(result['status'], 'complete')
        self.assertEqual((target / 'resume-checkpoint.zip').read_bytes(), checkpoint); frozen = json.loads((target / 'frozen.json').read_bytes())
        self.assertEqual((frozen['previous_provider_calls'], frozen['maximum_live_calls'], frozen['aggregate_started_at']), (30, 20, started)); self.assertEqual(json.loads((target / 'native-resume.json').read_bytes())['job'], job)

    def test_start_followup_cannot_reset_expired_aggregate_deadline_or_dispatch_an_unprepared_host(self):
        self.selected(); prior = self.base / 'prior'; prior.mkdir(); self.saved('qualification-report.json', {'started_at': (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=59)).isoformat()}, prior)
        self.saved('prepare-command.json', {'command_id': 'prepared', 'instance_id': 'synthetic-instance', 'host': '/synthetic/host'})
        self.saved('frozen.json', {'followup_of': prior.name})
        with self.assertRaisesRegex(AssertionError, 'elapsed-time'): self.cli('start')
        self.r.ssm.assert_not_called()
        self.saved('qualification-report.json', {'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}, prior)
        self.r.ssm.return_value = {'command_id': 'bounded-continuation'}
        result = self.cli('start'); self.assertGreater(result['aggregate_remaining_seconds'], 180); self.assertLessEqual(result['aggregate_remaining_seconds'], 3590)

    def test_status_and_diagnostics_execute_only_bounded_metadata_reads(self):
        self.selected(); host = self.root / 'synthetic-host'; host.mkdir(); self.saved('prepare-command.json', {'host': str(host)})
        (host / 'run.log').write_text('z' * 1200); (host / 'report.json').write_bytes(canonical({'status': 'running', 'live_provider_calls': 2, 'summaries': ['synthetic']}))
        (host / 'archive.json').write_bytes(canonical({'sha256': 'a' * 64}))
        case = host / 'answer-case'; case.mkdir(); (case / 'receipt.json').write_bytes(canonical({'status': 'failed', 'request_hash': 'b' * 64, 'private': 'must-not-appear'})); (case / 'config.json').write_text('must-not-appear')
        (host / 'node_modules').mkdir(); (host / 'node_modules/private-file').write_text('private')
        for mode in ['status', 'diagnose']:
            with self.subTest(mode=mode):
                self.r.ssm.return_value = {'command_id': mode}; self.assertEqual(self.cli(mode)['status'], 'complete')
                command = self.r.ssm.call_args.args[0]; self.assertEqual(len(command), 1); program = shlex.split(command[0])[-1]
                output = io.StringIO()
                with contextlib.redirect_stdout(output): exec(compile(program, '<bounded-host-inspection>', 'exec'), {})
                record = json.loads(output.getvalue()); self.assertNotIn('must-not-appear', output.getvalue())
                if mode == 'status': self.assertEqual((record['status'], record['calls'], len(record['log_tail'])), ('running', 2, 1000))
                else: self.assertNotIn('config.json', [v['name'] for v in record['receipts'][0]['files']]); self.assertFalse(any('node_modules' in v['path'] for v in record['largest_files']))

    def test_retention_uses_exact_host_source_and_collection_verifies_the_retained_archive(self):
        self.selected(); self.saved('prepare-command.json', {'host': '/synthetic/host'})
        self.write('bin/retain_assessment_methods_qualification_host.py', b'# exact synthetic retention implementation\n')
        self.r.ssm.return_value = {'command_id': 'retain', 'instance_id': 'synthetic-instance'}
        self.assertEqual(self.cli('retain')['status'], 'complete'); command = self.r.ssm.call_args.args[0]
        self.assertTrue(command[-1].endswith('/synthetic/host/retain-evidence.py')); self.assertIn('assert not p.exists()', command[1])
        self.saved('status-command.json', {'command_id': 'status', 'instance_id': 'synthetic-instance'})
        raw = self.archive({'report.json': canonical({'status': 'failed-or-paused', 'live_provider_calls': 3})}); self.objects['actual-archive'] = raw
        self.invocation = {'Status': 'Success', 'StandardOutputContent': json.dumps({'archive': {'path': 'actual-archive', 'sha256': digest(raw)}})}
        result = self.cli('collect'); self.assertTrue(result['archive_verified']); self.assertEqual((self.out / 'qualification.zip').read_bytes(), raw)


class StorageReconciliation(unittest.TestCase):
    def test_uncertain_write_reads_same_object_once_and_never_replays_post(self):
        r = MagicMock(); r.aws.return_value = {'SecretString': 'synthetic-private-key'}
        response = MagicMock(); response.__enter__.return_value.read.return_value = b'original'
        with patch.object(release, 'r', r):
            for failure in [TimeoutError('timeout'), urllib.error.URLError('connection lost')]:
                r.prior.guard.OPEN.open.side_effect = [failure, response]
                self.assertEqual(release.storage('content-addressed', b'original'), b'')
                calls = r.prior.guard.OPEN.open.call_args_list[-2:]
                self.assertEqual([c.args[0].get_method() for c in calls], ['POST', 'GET']); self.assertEqual(calls[0].args[0].full_url, calls[1].args[0].full_url)
                self.assertEqual(calls[0].args[0].data, b'original')
            r.prior.guard.OPEN.open.side_effect = [TimeoutError(), response]; response.__enter__.return_value.read.return_value = b'changed'
            with self.assertRaisesRegex(RuntimeError, 'unconfirmed'): release.storage('same-original-identity', b'original')
            r.prior.guard.OPEN.open.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError): release.storage('read-only')
            r.prior.guard.OPEN.open.side_effect = None; r.prior.guard.OPEN.open.return_value = response
            response.__enter__.return_value.read.return_value = b'original'
            self.assertEqual(release.storage('direct'), b'original'); response.__enter__.return_value.read.assert_called_with(20000001)


if __name__ == '__main__': unittest.main()
