"""Paper-confirmation release guards with synthetic runtime/cloud/DB adapters.

Original request/answer files, immutable archives and private receipts are real.
Synthetic answers and review declarations do not qualify a production release.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('paper_confirmation_unit', ROOT / 'bin/paper-confirmation-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


class PaperConfirmationRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='paper-release-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name) / 'infra'; self.back = self.root.parent / 'backend'; self.root.mkdir(); (self.back / 'research_workflow').mkdir(parents=True)
        self.enterContext(patch.object(release, 'ROOT', self.root)); self.enterContext(patch.object(release, 'BACK', self.back)); self.base = self.root / 'releases'; self.enterContext(patch.object(release, 'BASE', self.base)); self.base.mkdir(); self.enterContext(patch.object(release, 'CASE_PATH', self.root / 'cases.json')); self.enterContext(patch.object(release, 'MIGRATION', self.root / 'migration.sql'))
        (self.root / 'cases.json').write_bytes((ROOT / 'test/paper-confirmation-live-cases-v1.json').read_bytes()); (self.root / 'migration.sql').write_bytes(b'-- Synthetic migration, never executed externally\n')
        self.seed = dict(system_prompt='Synthetic trusted instruction', research_context='Synthetic context, not scientific evidence'); self.write('database/seed-autonomy-v10.json', canonical(self.seed))
        self.manifest = dict(source_revision='a' * 40, version=1, files={'worker.py': release.sha(b'# Synthetic original runtime\n')}); (self.back / 'research_workflow/worker.py').write_bytes(b'# Synthetic original runtime\n'); self.write('research-workflow-runtime.json', canonical(self.manifest))
        for name in ['paper-confirmation-release-v1.md', 'paper-confirmation-v1.md']: self.write('docs/' + name, b'Synthetic retained original release protocol\n')
        self.write('cdk.json', b'{"context":{"supabaseAnonKey":"synthetic-public-key"}}')
        self.r = MagicMock(); self.enterContext(patch.object(release, 'r', self.r)); self.r.stamp.return_value = '2026-11-01T00:00:00Z'; self.r.prior.queue.source.return_value = self.manifest; self.r.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"; self.r.admin.query.side_effect = self.query; self.r.aws.side_effect = self.aws; self.r.prior.guard.OPEN.open.side_effect = self.open
        self.a, self.m, self.s, self.rt = MagicMock(), MagicMock(), MagicMock(), MagicMock(); self.w = types.SimpleNamespace(canonical=canonical)
        self.modules_function = release.modules; self.enterContext(patch.object(release, 'modules', return_value=(self.a, self.m, self.s, self.rt, self.w)))
        self.a.intake.side_effect = self.intake; self.m.request.side_effect = lambda system, context: dict(system=system, context=context); self.m.parse.side_effect = lambda value: value
        self.s.paper_metadata.side_effect = lambda packet, chunk, values: dict(title=values['title'], domain=values['domain'])
        self.rt.MODEL = 'synthetic-native-model'; self.rt.VERSION = 'synthetic-native-runtime'; self.rt.catalog.return_value = {'status': 'ready'}; self.rt.credential.return_value = 'synthetic-credential-never-retained'; self.rt.execute.side_effect = self.execute
        self.calls = []; self.mode = 'success'; self.objects = {}; self.active = True; self.anonymous_status = 403; self.sql = []; self.reports = {}; self.force_conflict = False; self.corrupt_get = False; self.upload_error = None
        self.tables = [dict(relname=name, relrowsecurity=True, anon_access=False, browser_access=False) for name in ['research_paper_reviews', 'research_paper_review_events']]
        names = ['research_paper_review', 'research_autonomy_control', 'research_paper_upload', 'research_autonomy_before_confirmation', 'research_paper_upload_before_confirmation']; self.functions = [dict(proname=name, anon_execute=False, browser_execute=False, service_execute=index < 3) for index, name in enumerate(names)]
        self.control = None; self.present = False; self.active_tasks = 0; self.active_dispatches = 0; self.pointer_drift = False; self.capability_ready = True; self.cloud_calls = []; self.control_artifacts = []; self.corrupt_archive = False
        self.r.target.return_value = dict(aws_account='395567831870', supabase_project='regphejnlvfpyokpniny'); self.r.functions.return_value = {'api': 'SyntheticApi'}; self.r.prior.pointers.side_effect = self.pointers; self.r.prior.functions.return_value = {'original_runtime_verified': True}; self.r.cdk.side_effect = self.cdk; self.r.compare_parameters.return_value = {'literal_parameters_unchanged': True}; self.r.ssm.return_value = {'command_id': 'synthetic-host-update', 'instance_id': 'synthetic-worker'}
    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def intake(self, task):
        paper = self.a.one('studies', task['study_id']); packet = json.loads(self.a.store.artifact_bytes(task['study_id'], task['context']['text_artifact_id'])); chunk = packet['pages'][0]
        self.m.call(task, dict(paper_metadata_requested=True, paper=paper, source_chunk=chunk), {})
    def freeze(self):
        with contextlib.redirect_stdout(io.StringIO()): result = release.freeze()
        self.directory = Path(result['directory']); self.packet = json.loads((self.directory / 'frozen.json').read_bytes()); return result
    def execute(self, request, directory):
        self.calls.append((copy.deepcopy(request), directory)); case = next(c for c in self.packet['cases'] if c['context'] == request['context']); answer = dict(action='discover', ready=None, assessment_label=None, coverage_complete=False, check_id=None, proposal=None, evidence_ids=[], claims=[dict(page=1, quote=case['expected_claim'])], paper_metadata={'title': case['expected_title'], 'domain': 'Computer networking'})
        if self.mode == 'no-answer': return None, {'status': 'failed'}
        if self.mode == 'invalid': answer['coverage_complete'] = True
        return answer, {'status': 'complete', 'provider_calls': 1, 'measured_charges_usd': None}
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.startswith("select to_regclass('public.research_paper_reviews')"): return [{'present': 'research_paper_reviews' if self.present else None, 'relation': 'research_paper_reviews' if self.present else None}]
        if sql.startswith("select count(*) count from research_autonomy_tasks where status='running'") or sql.startswith("select count(*) count from research_autonomy_turns where status='running'"): return [{'count': self.active_tasks}]
        if sql.startswith("select count(*) count from research_model_dispatches where status in"): return [{'count': self.active_dispatches}]
        if sql.startswith(('select stage,status,count(*) from research_autonomy_tasks', 'select status,count(*) from research_model_dispatches', 'select p.proname,pg_get_functiondef', 'select pg_get_triggerdef', 'select id::text,status,request_sha256 from research_model_dispatches')): return []
        if sql.startswith('-- Synthetic migration, never executed externally'):
            self.assertFalse(options['read_only']); self.present = True; return []
        if self.control is not None:
            if sql.startswith('select paper_upload from research_studies'): return [{'paper_upload': self.control['paper'][0]['paper_upload']}]
            if sql.startswith('select id::text,sha256,byte_count,storage_path,media_type from research_artifacts'): return copy.deepcopy(self.control_artifacts)
            for prefix, name in [('select id::text,title,domain,paper_upload from research_studies', 'paper'), ('select study_id::text,status,reason,max_spend_cents', 'workflow'), ('select to_jsonb(r) value from research_paper_reviews', 'review'), ('select to_jsonb(e) value from research_paper_review_events', 'review_events'), ('select to_jsonb(c) value from research_claims', 'claims'), ('select id::text,claim_id::text,stage,status,label,attempts', 'tasks'), ('select id::text,status,reason,run_id::text,definition_sha256', 'jobs'), ('select to_jsonb(t) value from research_autonomy_turns', 'turns'), ('select to_jsonb(v) value from research_runs', 'runs'), ('select run_id::text,status,count(*) count from research_measurements', 'measurement_status_counts'), ('select to_jsonb(v) value from research_summaries', 'summaries')]:
                if sql.startswith(prefix): return copy.deepcopy(self.control[name])
        if sql.startswith('select v.id::text,v.content_sha256'): return [dict(id=release.PROMPT, content_sha256=self.packet['prompt_content_sha256'])] if self.active else []
        if sql.startswith('select relname,relrowsecurity'): return copy.deepcopy(self.tables)
        if sql.startswith('select proname,has_function_privilege'): return copy.deepcopy(self.functions)
        if sql.startswith('insert into agent_prompt_evaluations('):
            self.assertFalse(options['read_only']); values = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]; prompt, outcome, raw, digest, archive, producer = values
            self.assertEqual(prompt, release.PROMPT); self.assertIn(outcome, ['passed', 'failed-or-paused']); self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), digest); self.assertFalse(json.loads(archive).get('public', False)); self.reports[digest] = raw; return []
        if sql.startswith("select encode(sha256(convert_to(report_raw,'UTF8'))"):
            digest = re.findall(r"'((?:''|[^'])*)'", sql)[-1]; return [dict(sha256=hashlib.sha256(self.reports[digest].encode()).hexdigest())]
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        self.cloud_calls.append((service, operation, args))
        if (service, operation) == ('secretsmanager', 'get-secret-value'): return {'SecretString': 'synthetic-private-key'}
        if (service, operation) == ('cloudformation', 'list-stack-resources'): return {'StackResourceSummaries': [dict(ResourceType='AWS::Lambda::Function', LogicalResourceId='ResearchWorkflowPackageExecutorFixture', PhysicalResourceId='SyntheticPackage'), dict(ResourceType='AWS::Events::Rule', LogicalResourceId='ResearchWorkflowAutonomyPollFixture', PhysicalResourceId='SyntheticAutonomyPoll')]}
        if (service, operation) == ('cloudformation', 'describe-stacks'): return {'Stacks': [{'Outputs': [dict(OutputKey='OpenClawRuntimeBucket', OutputValue='cdk-hnb659fds-assets-395567831870-us-east-1'), dict(OutputKey='OpenClawRuntimeObject', OutputValue='f' * 64 + '.zip')]}]}
        if (service, operation) == ('lambda', 'get-function-configuration'): return dict(FunctionName='SyntheticApi', RevisionId='original-revision', Environment={'Variables': {'NETWORK_PACKAGE_AMI': release.PACKAGE_AMI, 'RESEARCH_AUTONOMY_ENABLED': 'false', 'ORIGINAL_SETTING': 'retained'}})
        if (service, operation) in [('lambda', 'update-function-configuration'), ('events', 'enable-rule')]: return {'submitted': True}
        raise AssertionError((service, operation, args))
    def open(self, request, **options):
        if isinstance(request, str):
            self.assertEqual(request, 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities'); return io.BytesIO(canonical(dict(paper_uploads=dict(version='research-paper-upload-v2', confirmation_required=True), autonomy={'runtime': {'status': 'ready' if self.capability_ready else 'blocked'}})))
        url = request.full_url; self.assertIn('/storage/v1/object/research-workflow-raw/', url)
        if request.get_method() == 'POST':
            self.assertEqual(request.get_header('X-upsert'), 'false'); self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-private-key')
            if self.upload_error: raise urllib.error.HTTPError(url, self.upload_error, 'Synthetic upload failure', {}, None)
            if url in self.objects: raise urllib.error.HTTPError(url, 409, 'Synthetic immutable conflict', {}, None)
            self.objects[url] = request.data
            if self.force_conflict: raise urllib.error.HTTPError(url, 409, 'Synthetic concurrent immutable upload', {}, None)
            return io.BytesIO(b'{}')
        if request.get_header('Apikey') == 'synthetic-public-key':
            if self.anonymous_status != 200: raise urllib.error.HTTPError(url, self.anonymous_status, 'Synthetic anonymous denied', {}, None)
            return io.BytesIO(b'Unexpected public bytes')
        return io.BytesIO(b'Changed response bytes' if self.corrupt_get or self.corrupt_archive and '/production/' in url else self.objects[url])
    def pointers(self):
        return [{'module': 'research-autonomy', 'active_version_id': 'changed' if self.pointer_drift and self.r.prior.pointers.call_count % 2 == 0 else release.PROMPT}]
    def cdk(self, action, directory, **options):
        self.assertIn(action, ['diff', 'deploy']); self.assertTrue(options['activate'])
        if action == 'deploy' and not options.get('host'): self.r.compare_parameters({'parameters': []}, {'parameters': []}, {'ami_id': 'synthetic'})
        return dict(action=action, host=options.get('host', False), submitted=True)
    def run_local(self):
        with contextlib.redirect_stdout(io.StringIO()): return release.run_local()
    def cli(self, mode):
        with patch.object(sys, 'argv', ['paper-confirmation-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as output: release.main()
        directory = Path(json.loads(output.getvalue())['directory']); return json.loads((directory / 'receipt.json').read_bytes())
    def reviewed_fixture(self):
        self.freeze(); self.run_local(); report = json.loads((self.directory / 'evaluation.json').read_bytes()); report.update(status='passed', reviewer=dict(type='AI', independent=False, identity='Synthetic unit-review declaration'))
        for case in report['cases']: case.update(raw_answer_reviewed=True, rendered_answer_reviewed=True)
        (self.directory / 'reviewed.json').write_bytes(canonical(report)); self.report = report
        archive = dict(sha256='b' * 64, retrieved_sha256='b' * 64, review_sha256=release.sha(canonical(report)), bucket='research-workflow-raw', anonymous_read_denied=True); (self.directory / 'archive.json').write_bytes(canonical(archive)); return archive
    def control_fixture(self):
        identity, claim, other = [str(uuid.uuid4()) for _ in range(3)]; title = 'Release verification — Synthetic networking control'; domain = 'Synthetic networking'; review = dict(status='confirmed', confirmation=dict(title=title, domain=domain, claim_ids=[claim]))
        turn = dict(status='complete', request_raw='{"original_request":true}', raw_response='{"original_response":true}', usage={'tokens': {'inputTokens': 4, 'outputTokens': 2, 'totalTokens': 6}}); turn.update(request_sha256=release.sha(turn['request_raw'].encode()), response_sha256=release.sha(turn['raw_response'].encode()))
        self.control = dict(paper=[dict(id=identity, title=title, domain=domain, paper_upload=dict(sha256='f6378fb3de19aa8d3204f4d3a2028f95497f334862a5298aa6678ef1b816290b', filename='JumpServe release verification IPv6.pdf'))], workflow=[dict(max_spend_cents=10000, max_attempts=None, created_at='2026-01-01T00:00:00Z', deadline_at='2026-01-02T00:00:00Z')], review=[{'value': review}], review_events=[{'value': {'snapshot': copy.deepcopy(review)}}], claims=[{'value': dict(id=claim, description='Published absolute folded metrics')}, {'value': dict(id=other, description='Unselected original claim')}], tasks=[dict(claim_id=None, stage='intake', status='resolved', label=None), dict(claim_id=claim, stage='planning', status='running', label='inconclusive')], jobs=[dict(id='original-job', status='running')], turns=[{'value': turn}, {'value': dict(turn, status='failed', raw_response=None, response_sha256=None, usage={})}], runs=[{'value': {'status': 'complete'}}, {'value': {'status': 'failed'}}], measurement_status_counts=[dict(run_id='original-run', status='recorded', count=0)], summaries=[{'value': {'original_zero': 0, 'original_missing': None}}])
        self.write('.test-artifacts/paper-confirmation-control/identity.json', canonical({'assessment_id': identity})); return identity
    def operational_archive_fixture(self):
        identity = self.control_fixture(); (self.root / '.test-artifacts/paper-worker-repair/prior').mkdir(parents=True); self.write('.test-artifacts/paper-worker-repair/prior/receipt.json', canonical({'status': 'failed', 'scope': 'Synthetic retained diagnostic'})); self.write('.test-artifacts/paper-worker-repair/prior/session.json', b'PRIVATE-DO-NOT-ARCHIVE'); self.write('.test-artifacts/paper-worker-repair/not-a-folder', b'Synthetic unrelated file')
        for stamp in ['20261024T171303860323Z', '20261024T171309049767Z', '20261024T171345106208Z', '20261024T172148312155Z', '20261024T172806376787Z', '20261024T172949010453Z', '20261024T173316951538Z']: self.write('.test-artifacts/openclaw-release/' + stamp + '/receipt.json', canonical({'status': 'synthetic retained operator receipt'}))
        self.write('.test-artifacts/paper-confirmation-control/main.pdf', b'%PDF-Synthetic local control fixture, not a research paper'); self.write('.test-artifacts/paper-confirmation-control/frozen-control.json', canonical({'classification': 'Synthetic unit control declaration'}))
        frontend = self.root.parent / 'jumpserve-front-end/.test-artifacts/paper-confirmation-production'; frontend.mkdir(parents=True)
        for name, raw in [('retained.png', b'Synthetic screenshot fixture bytes, not visual validation'), ('browser-observations.json', canonical({'synthetic': True})), ('browser-follow-up.json', canonical({'synthetic': True})), ('cookies.json', b'PRIVATE-DO-NOT-ARCHIVE')]: (frontend / name).write_bytes(raw)
        for name in ['docs/paper-confirmation-production-release-v1.json', 'docs/paper-confirmation-release-amendments-v1.md', 'docs/paper-confirmation-private-artifact-v1.json', 'bin/paper-confirmation-release.py', 'bin/paper-worker-repair.py', 'database/202610230002_paper_confirmation.sql']: self.write(name, b'Synthetic retained release evidence\n')
        raw = b'Original retained control output'; sha = release.sha(raw); path = identity + '/' + sha; record = dict(id=str(uuid.uuid4()), sha256=sha, byte_count=len(raw), storage_path=path, media_type='application/octet-stream'); self.control_artifacts = [record]; self.objects['https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/' + path] = raw
        return raw

    def test_freezing_captures_each_exact_intake_request_without_admitting_any_provider_call(self):
        result = self.freeze(); self.assertEqual(result['provider_calls'], 0); self.assertEqual(result['frozen_cases'], 5); self.rt.execute.assert_not_called(); self.assertEqual(self.packet['producer_sha256'], release.sha(Path(release.__file__).read_bytes())); self.assertEqual(self.packet['cases_sha256'], release.sha((self.root / 'cases.json').read_bytes())); self.assertEqual(self.packet['limits']['maximum_provider_calls'], 5)
        self.assertEqual(release.selected(), self.directory)
        for case in self.packet['cases']:
            raw = (self.directory / (case['name'] + '-request.json')).read_bytes(); self.assertEqual(release.sha(raw), case['request_sha256']); self.assertEqual(json.loads(raw)['context'], case['context']); self.assertEqual(case['context']['source_chunk']['text'], case['text']); self.assertTrue(case['context']['paper_metadata_requested'])
        (self.base / 'selected.txt').write_text('../untrusted\n')
        with self.assertRaisesRegex(ValueError, 'campaign identity'): release.selected()

    def test_local_campaign_retains_actual_answer_bytes_and_awaits_review_after_all_five_checks(self):
        self.freeze(); result = self.run_local(); self.assertEqual(result['status'], 'awaiting-substantive-AI-review'); report = json.loads((self.directory / 'evaluation.json').read_bytes()); self.assertEqual(report['actual_provider_calls'], 5); self.assertEqual(report['reserved_orchestration_cents'], 500); self.assertIsNone(report['measured_charges_usd']); self.assertEqual(len(self.calls), 5)
        for case in report['cases']: self.assertTrue(case['passed']); self.assertFalse(case['raw_answer_reviewed']); self.assertFalse(case['rendered_answer_reviewed']); self.assertEqual(release.sha((self.directory / (case['name'] + '-answer.json')).read_bytes()), case['output_sha256'])
        with self.assertRaisesRegex(ValueError, 'Preserve the original campaign'): self.run_local()
        self.assertNotIn('synthetic-credential-never-retained', ''.join(p.read_text() for p in self.directory.glob('*.json')))

    def test_failed_or_missing_answer_stops_at_one_attempt_with_original_failure_and_zero_billing_inference(self):
        for mode in ['invalid', 'no-answer']:
            self.freeze(); self.mode = mode; self.calls.clear()
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'extraction criterion'): self.run_local()
            report = json.loads((self.directory / 'evaluation.json').read_bytes()); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['actual_provider_calls'], 1); self.assertFalse(report['cases'][0]['passed']); self.assertIsNone(report['measured_charges_usd']); self.assertEqual(len(self.calls), 1)

    def test_changed_frozen_source_cases_or_request_refuse_a_new_provider_admission(self):
        for change in ['source', 'cases', 'request']:
            self.freeze(); original_cases = (self.root / 'cases.json').read_bytes(); original_manifest = copy.deepcopy(self.manifest)
            if change == 'source': self.manifest['files'] = dict(self.manifest['files'], unexpected='c' * 64)
            elif change == 'cases': (self.root / 'cases.json').write_bytes(original_cases + b' ')
            else: (self.directory / (self.packet['cases'][0]['name'] + '-request.json')).write_bytes(b'Changed original request')
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'source or cases changed|Frozen request changed'): self.run_local()
            self.assertEqual(len(self.calls), 0); self.manifest.clear(); self.manifest.update(original_manifest); (self.root / 'cases.json').write_bytes(original_cases)

    def test_reviewer_original_bytes_active_prompt_and_private_archive_are_all_required(self):
        archive = self.reviewed_fixture(); result = release.reviewed(); self.assertEqual(result['cases'], 5); self.assertEqual(result['sha256'], release.sha((self.directory / 'reviewed.json').read_bytes()))
        for change in [dict(status='failed'), dict(cases=self.report['cases'][:-1]), dict(reviewer=dict(type='human', independent=False)), dict(reviewer=dict(type='AI', independent=True))]:
            (self.directory / 'reviewed.json').write_bytes(canonical(dict(self.report, **change)))
            with self.subTest(change=list(change)), self.assertRaises(ValueError): release.reviewed()
        (self.directory / 'reviewed.json').write_bytes(canonical(self.report)); self.active = False
        with self.assertRaisesRegex(ValueError, 'Active production prompt differs'): release.reviewed()
        self.active = True
        for change in [dict(retrieved_sha256='0' * 64), dict(review_sha256='0' * 64), dict(bucket='public'), dict(anonymous_read_denied=False)]:
            (self.directory / 'archive.json').write_bytes(canonical(dict(archive, **change)))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'stored privately and hash-verified'): release.reviewed()
        (self.directory / 'archive.json').write_bytes(canonical(archive)); path = self.directory / (self.report['cases'][0]['name'] + '-answer.json'); path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'original prompt or answer bytes changed'): release.reviewed()

    def test_private_review_security_requires_all_relations_and_service_only_rpc_grants(self):
        self.assertEqual(len(release.security()['tables']), 2)
        for key in ['relrowsecurity', 'anon_access', 'browser_access']:
            original = copy.deepcopy(self.tables); self.tables[0][key] = key != 'relrowsecurity'
            with self.subTest(table_key=key), self.assertRaisesRegex(RuntimeError, 'table security differs'): release.security()
            self.tables = original
        original = copy.deepcopy(self.functions)
        for key in ['anon_execute', 'browser_execute', 'service_execute']:
            self.functions = copy.deepcopy(original); self.functions[0][key] = key != 'service_execute'
            with self.subTest(function_key=key), self.assertRaisesRegex(RuntimeError, 'bypass grants differ'): release.security()
        self.functions = original[:-1]
        with self.assertRaisesRegex(RuntimeError, 'bypass grants differ'): release.security()

    def test_native_campaign_enforces_its_own_frozen_call_and_reservation_limits_before_another_attempt(self):
        original = json.loads((self.root / 'cases.json').read_bytes())
        for limit in [dict(maximum_provider_calls=1), dict(maximum_orchestration_reservation_cents=150)]:
            (self.root / 'cases.json').write_bytes(canonical(dict(original, **limit))); self.freeze(); self.calls.clear()
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, 'Frozen evaluation resource bound'): self.run_local()
            report = json.loads((self.directory / 'evaluation.json').read_bytes()); self.assertEqual(report['actual_provider_calls'], 1); self.assertEqual(report['reserved_orchestration_cents'], 100); self.assertEqual(len(self.calls), 1); self.assertEqual(report['status'], 'failed-or-paused')

    def test_actual_answer_checks_keep_discovery_only_grounded_claims_and_injection_rejection_separate(self):
        self.freeze(); case = self.packet['cases'][0]; request = json.loads((self.directory / (case['name'] + '-request.json')).read_bytes()); answer, _ = self.execute(request, self.directory / 'synthetic'); baseline = release.checks(case, answer, self.m, self.s); self.assertTrue(all(baseline.values()))
        for key, value in [('action', 'assess'), ('ready', True), ('assessment_label', 'reproduced'), ('check_id', 'selected'), ('proposal', {}), ('evidence_ids', ['unexecuted'])]:
            with self.subTest(key=key): self.assertFalse(release.checks(case, dict(answer, **{key: value}), self.m, self.s)['discovery_only'])
        wrong_quote = dict(answer, claims=[dict(page=2, quote='Not in the source')]); checks = release.checks(case, wrong_quote, self.m, self.s); self.assertFalse(checks['quote_grounding']); self.assertFalse(checks['expected_claim'])
        untrusted = dict(case, forbidden='INJECTION_SUCCESS', domain_required=False); checks = release.checks(untrusted, dict(answer, injected='INJECTION_SUCCESS', paper_metadata={'title': case['expected_title'], 'domain': None}), self.m, self.s); self.assertTrue(checks['domain']); self.assertFalse(checks['injection_ignored'])

    def test_archive_retains_original_answers_and_failed_campaigns_but_excludes_auth_state_and_unknown_files(self):
        self.reviewed_fixture(); self.force_conflict = True
        for name in ['state/AGENTS.md', '.subscription-auth/provider-response.bin', 'cookies.json']:
            path = self.directory / name; path.parent.mkdir(exist_ok=True); path.write_bytes(b'SYNTHETIC-PRIVATE-CREDENTIAL-CANARY')
        (self.directory / 'stdout.bin').write_bytes(b'Original bounded native diagnostics'); (self.directory / 'unexpected.txt').write_bytes(b'Never collect arbitrary files'); (self.base / 'not-a-directory').write_bytes(b'Not an evaluation folder')
        failed = self.base / '20261001T000000000000Z'; failed.mkdir(); (failed / 'evaluation.json').write_text(json.dumps(dict(status='failed-or-paused', original_failure='Retained failed control', measured_charges_usd=None)))
        output = self.root / 'archive-output'; output.mkdir(); result = release.archive_evaluation(output); raw = (output / 'evidence.zip').read_bytes(); self.assertEqual(result['sha256'], release.sha(raw)); self.assertEqual(result['retrieved_sha256'], release.sha(raw)); self.assertTrue(result['anonymous_read_denied']); self.assertTrue(result['all_member_hashes_verified']); self.assertIsNone(result['measured_storage_charges_usd']); self.assertEqual(len(self.reports), 2)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = json.loads(archive.read('manifest.json')); self.assertEqual(result['files'], len(members)); contents = b''.join(archive.read(item['path']) for item in members); self.assertNotIn(b'SYNTHETIC-PRIVATE-CREDENTIAL-CANARY', contents); self.assertNotIn(b'Never collect arbitrary files', contents); self.assertIn(b'Retained failed control', contents)
            for member in members: self.assertEqual(release.sha(archive.read(member['path'])), member['sha256']); self.assertEqual(len(archive.read(member['path'])), member['byte_count'])
        self.assertEqual(json.loads((self.directory / 'archive.json').read_bytes()), result); self.assertEqual(release.reviewed()['cases'], 5)

    def test_private_archive_upload_retrieval_and_anonymous_security_failures_are_never_confirmed(self):
        for failure in ['upload', 'retrieval', 'public']:
            self.reviewed_fixture(); output = self.root / ('archive-' + failure); output.mkdir(); self.upload_error = 503 if failure == 'upload' else None; self.corrupt_get = failure == 'retrieval'; self.anonymous_status = 200 if failure == 'public' else 403
            with self.subTest(failure=failure), self.assertRaisesRegex(RuntimeError, 'upload failed|Retrieved archive bytes differ|anonymously readable'): release.archive_evaluation(output)
            self.assertEqual(self.reports, {}); self.upload_error = None; self.corrupt_get = False; self.anonymous_status = 403

    def test_oversized_archive_or_changed_runtime_is_rejected_before_credentials_or_upload(self):
        self.reviewed_fixture(); output = self.root / 'archive-output'; output.mkdir(); (self.back / 'research_workflow/worker.py').write_bytes(b'Changed runtime after review')
        with self.assertRaisesRegex(ValueError, 'Original runtime bytes changed'): release.archive_evaluation(output)
        self.r.aws.assert_not_called(); self.assertFalse(self.objects); (self.back / 'research_workflow/worker.py').write_bytes(b'# Synthetic original runtime\n'); (self.directory / 'stdout.bin').write_bytes(os.urandom(10000001))
        with self.assertRaisesRegex(ValueError, '10 MB release bound'): release.archive_evaluation(output)
        self.r.aws.assert_not_called(); self.assertFalse(self.objects)

    def test_control_snapshot_is_fixed_target_read_only_and_hashes_original_prompts_responses_and_missing_values(self):
        identity = self.control_fixture(); output = self.base / '20261101T000000000000Z'; output.mkdir(); result = release.control_snapshot(output); raw = (output / 'private-control.json').read_bytes(); self.assertEqual(result['assessment_id'], identity); self.assertEqual(result['snapshot_sha256'], release.sha(raw)); self.assertEqual(result['claims'], 2); self.assertEqual(result['claim_tasks'], 1); self.assertEqual(result['turns'], 2); self.assertTrue(result['prompt_response_hashes_verified']); self.assertEqual(json.loads(raw), self.control); self.assertTrue(all(options.get('read_only', True) for sql, options in self.sql)); self.r.aws.assert_not_called()
        for field in ['request_raw', 'raw_response']:
            before = copy.deepcopy(self.control); self.control['turns'][0]['value'][field] = 'Changed captured original'
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, 'original prompt hash differs|original response hash differs'): release.control_snapshot(output)
            self.control = before
        self.control['paper'][0]['paper_upload']['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'Only the fixed release-control PDF'): release.control_snapshot(output)

    def test_confirmation_control_preserves_frozen_claims_and_limits_and_reports_partial_usage_coverage(self):
        identity = self.control_fixture(); before = copy.deepcopy(self.control); before['review'][0]['value'] = {'status': 'ready', 'confirmation': None}; before['jobs'] = []; before['tasks'] = [before['tasks'][0]]; before['paper'][0]['title'] = 'Synthetic title awaiting confirmation'; before['review_events'] = []
        original = self.base / '20261001T000000000000Z'; original.mkdir(); (original / 'private-control.json').write_bytes(canonical(before)); output = self.base / '20261101T000000000000Z'; output.mkdir(); result = release.verify_control(output)
        self.assertEqual(result['assessment_id'], identity); self.assertTrue(all(result['checks'].values())); self.assertEqual(result['complete_runs'], 1); self.assertEqual(result['recorded_tokens'], {'inputTokens': 4, 'outputTokens': 2, 'totalTokens': 6}); self.assertEqual(result['usage_coverage'], {'turns': 2, 'turns_with_usage': 1}); self.assertEqual(result['turn_status_counts'], {'complete': 1, 'failed': 1}); self.assertIsNone(result['measured_charges_usd']); self.assertEqual(result['measurement_status_counts'], self.control['measurement_status_counts'])
        self.control['workflow'][0]['deadline_at'] = '2026-01-03T00:00:00Z'
        with self.assertRaisesRegex(RuntimeError, 'original_deadline_and_budget_preserved'): release.verify_control(output)
        (original / 'private-control.json').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Retained ready and pre-confirmation snapshots'): release.verify_control(output)

    def test_release_cli_migration_scoped_cdk_host_update_and_activation_keep_prompt_pointers_and_existing_settings(self):
        self.reviewed_fixture(); original_compare = self.r.compare_parameters
        for mode in ['inspect', 'migrate', 'migrate', 'diff', 'deploy', 'host-diff', 'host-deploy', 'host-update', 'activate', 'verify']:
            with self.subTest(mode=mode):
                report = self.cli(mode); self.assertEqual(report['status'], 'passed'); self.assertEqual(report['prompt_pointers_before'], report['prompt_pointers_after']); self.assertEqual(report['runtime_manifest_sha256'], release.sha((self.root / 'research-workflow-runtime.json').read_bytes())); self.assertIsNone(report['measured_charges_usd'])
                if mode == 'migrate': self.assertIn(report['migration']['status'], ['applied', 'present-before-this-call']); self.assertEqual(len(report['security']['functions']), 5)
                if mode == 'host-update':
                    commands = self.r.ssm.call_args.args[0]; self.assertEqual(commands[1], 'systemctl stop jumpserve-openclaw.service'); self.assertEqual(commands[-1], 'systemctl start jumpserve-openclaw.service'); self.assertTrue(any('cp -a /opt/jumpserve/runtime' in command for command in commands)); self.assertTrue(any('assert actual==expected' in command for command in commands)); self.assertFalse(any('auth/' in command or 'rm ' in command for command in commands))
        self.assertIs(self.r.compare_parameters, original_compare); self.assertEqual(sum(sql.startswith('-- Synthetic migration') for sql, _ in self.sql), 1)
        update = next(args for service, operation, args in self.cloud_calls if (service, operation) == ('lambda', 'update-function-configuration')); environment = json.loads(update[update.index('--environment') + 1]); self.assertEqual(environment['Variables']['RESEARCH_AUTONOMY_ENABLED'], 'true'); self.assertEqual(environment['Variables']['ORIGINAL_SETTING'], 'retained'); self.assertEqual(update[update.index('--revision-id') + 1], 'original-revision')

    def test_active_work_unready_worker_and_prompt_drift_leave_failed_receipts_without_followup_actions(self):
        self.reviewed_fixture(); self.active_tasks = 1
        with self.assertRaisesRegex(ValueError, 'Drain active autonomous'): self.cli('migrate')
        self.assertFalse(self.present); self.active_tasks = 0; self.active_dispatches = 1
        with self.assertRaisesRegex(RuntimeError, 'must be reconciled before host update'): self.cli('host-update')
        self.r.ssm.assert_not_called(); self.active_dispatches = 0; self.capability_ready = False
        with self.assertRaisesRegex(RuntimeError, 'ready native worker required'): self.cli('activate')
        self.assertFalse(any(operation == 'update-function-configuration' for _, operation, _ in self.cloud_calls)); self.capability_ready = True; self.pointer_drift = True; self.r.prior.pointers.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'must not change published prompt pointers'): self.cli('verify')
        reports = [json.loads(path.read_bytes()) for path in self.base.glob('*/receipt.json')]; self.assertEqual(len(reports), 4); self.assertTrue(all(report['status'] == 'failed' and report['reason'] for report in reports))

    def test_cli_freeze_and_run_local_are_fixed_entrypoints_and_help_never_contacts_services(self):
        for mode, name in [('freeze', 'freeze'), ('run-local', 'run_local')]:
            with patch.object(sys, 'argv', ['paper-confirmation-release.py', mode]), patch.object(release, name, return_value={'synthetic': True}) as action, contextlib.redirect_stdout(io.StringIO()): release.main()
            action.assert_called_once_with()
        with patch.object(sys, 'argv', ['paper-confirmation-release.py', '--help']), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error: runpy.run_path(str(ROOT / 'bin/paper-confirmation-release.py'), run_name='__main__')
        self.assertEqual(error.exception.code, 0); self.r.target.assert_not_called()

    def test_operational_archive_verifies_retained_control_objects_and_excludes_browser_and_native_credentials(self):
        self.reviewed_fixture(); original = self.operational_archive_fixture(); report = self.cli('archive-release'); result = report['archive']; self.assertEqual(report['status'], 'passed'); self.assertTrue(result['all_member_hashes_verified']); self.assertTrue(result['anonymous_read_denied']); self.assertEqual(result['original_control_artifacts_retrieved_and_verified'], 1); self.assertEqual(result['original_control_artifact_bytes'], len(original)); self.assertIsNone(result['measured_storage_charges_usd'])
        url = next(url for url in self.objects if '/production/' in url); raw = self.objects[url]; self.assertEqual(result['sha256'], release.sha(raw)); self.assertEqual(result['retrieved_sha256'], release.sha(raw))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = json.loads(archive.read('manifest.json')); self.assertEqual(result['files'], len(members)); contents = b''.join(archive.read(item['path']) for item in members); self.assertNotIn(b'PRIVATE-DO-NOT-ARCHIVE', contents); self.assertEqual(archive.read('control-original-artifacts/' + release.sha(original)), original); self.assertIn('browser/retained.png', archive.namelist()); self.assertIn('browser/browser-observations.json', archive.namelist()); self.assertIn('browser/browser-follow-up.json', archive.namelist())
            for item in members: self.assertEqual(release.sha(archive.read(item['path'])), item['sha256']); self.assertEqual(len(archive.read(item['path'])), item['byte_count'])
        self.assertEqual(json.loads((self.root / 'docs/paper-confirmation-production-artifact-v1.json').read_bytes()), result)

    def test_operational_archive_rejects_other_control_targets_incomplete_coverage_and_changed_object_bytes(self):
        self.operational_archive_fixture(); output = self.base / 'archive-output'; output.mkdir(); paper = copy.deepcopy(self.control['paper']); records = copy.deepcopy(self.control_artifacts)
        for failure in ['target', 'count', 'bytes', 'path', 'hash', 'retrieval']:
            self.control['paper'] = copy.deepcopy(paper); self.control_artifacts = copy.deepcopy(records); self.corrupt_get = False
            if failure == 'target': self.control['paper'][0]['paper_upload']['sha256'] = '0' * 64
            elif failure == 'count': self.control_artifacts *= 501
            elif failure == 'bytes': self.control_artifacts[0]['byte_count'] = 32000001
            elif failure == 'path': self.control_artifacts[0]['storage_path'] = 'another-assessment/' + records[0]['sha256']
            elif failure == 'hash': self.control_artifacts[0].update(sha256='invalid', storage_path=self.control['paper'][0]['id'] + '/invalid')
            else: self.corrupt_get = True
            with self.subTest(failure=failure), self.assertRaisesRegex(RuntimeError, 'fixed release-control artifacts|500-record/32-MB bound|artifact identity differs|control artifact bytes differ'): release.archive_release(output)
            self.assertFalse((self.root / 'docs/paper-confirmation-production-artifact-v1.json').exists())

    def test_operational_archive_enforces_its_size_roundtrip_and_anonymous_denial_requirements(self):
        self.operational_archive_fixture(); output = self.base / 'archive-output'; output.mkdir(); self.corrupt_archive = True
        with self.assertRaisesRegex(RuntimeError, 'operational evidence bytes differ'): release.archive_release(output)
        self.corrupt_archive = False; self.anonymous_status = 200
        # An earlier upload can have succeeded despite unconfirmed verification.
        # Fresh evidence is content-addressed; reset only this synthetic adapter.
        self.objects = {url: raw for url, raw in self.objects.items() if '/production/' not in url}
        with self.assertRaisesRegex(RuntimeError, 'anonymously readable'): release.archive_release(output)
        self.anonymous_status = 403; self.write('.test-artifacts/paper-confirmation-control/main.pdf', os.urandom(10000001))
        with self.assertRaisesRegex(RuntimeError, '10 MB bound'): release.archive_release(output)

    def test_controller_cli_routes_preserve_the_selected_private_output_directory(self):
        self.reviewed_fixture()
        for mode, name in [('archive', 'archive_evaluation'), ('control-snapshot', 'control_snapshot'), ('control-verify', 'verify_control')]:
            with patch.object(release, name, return_value={'synthetic_boundary': True}) as action: report = self.cli(mode)
            self.assertEqual(report['status'], 'passed'); action.assert_called_once(); self.assertEqual(action.call_args.args[0].parent, self.base)

    def test_native_module_configuration_sets_only_the_fixed_runtime_and_returns_imported_adapters(self):
        modules = {name: types.ModuleType('synthetic_' + name) for name in ['autonomy', 'autonomy_model', 'autonomy_sources', 'openclaw_runtime', 'workflow']}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {}, clear=True), patch.object(sys, 'path', list(sys.path)):
            result = self.modules_function(); self.assertEqual(result, tuple(modules[name] for name in ['autonomy', 'autonomy_model', 'autonomy_sources', 'openclaw_runtime', 'workflow'])); self.assertEqual(os.environ['RESEARCH_AI_RUNTIME'], 'openclaw-production-v1'); self.assertTrue(os.environ['OPENCLAW_PACKAGE'].startswith(str(self.back))); self.assertEqual(sys.path[0], str(self.back / 'research_workflow'))

    def test_missing_exact_context_or_unregistered_review_case_cannot_be_frozen_or_approved(self):
        for intake in [lambda task: None, lambda task: self.m.call(task, {'paper_metadata_requested': False}, {})]:
            self.a.intake.side_effect = intake
            with self.assertRaisesRegex(ValueError, 'Exact intake context not captured'): self.freeze()
        self.a.intake.side_effect = self.intake; self.reviewed_fixture(); report = copy.deepcopy(self.report); report['cases'][0]['name'] = 'unregistered-case'; (self.directory / 'reviewed.json').write_bytes(canonical(report))
        with self.assertRaisesRegex(ValueError, 'Unregistered evaluation case'): release.reviewed()

    def test_changed_executor_inventory_runtime_asset_schedule_or_confirmation_contract_refuses_release(self):
        self.reviewed_fixture(); original = self.aws
        with patch.object(self.r, 'aws', return_value={'StackResourceSummaries': []}), self.assertRaisesRegex(RuntimeError, 'Expected one package executor'): release.compare_paper_parameters({'parameters': []}, {'parameters': []}, {})
        for defect in ['asset', 'schedule']:
            def aws(service, operation, *args):
                value = original(service, operation, *args)
                if defect == 'asset' and operation == 'describe-stacks': value['Stacks'][0]['Outputs'][0]['OutputValue'] = 'unreviewed-bucket'
                if defect == 'schedule' and operation == 'list-stack-resources': value['StackResourceSummaries'] = [item for item in value['StackResourceSummaries'] if item['ResourceType'] != 'AWS::Events::Rule']
                return value
            with patch.object(self.r, 'aws', side_effect=aws), self.subTest(defect=defect), self.assertRaisesRegex(ValueError if defect == 'asset' else RuntimeError, 'Unexpected reviewed runtime asset|Expected one retained autonomous schedule'): self.cli('host-update' if defect == 'asset' else 'activate')
        original_open = self.open
        def open(request, **options):
            if isinstance(request, str): return io.BytesIO(canonical({'paper_uploads': {'version': 'old', 'confirmation_required': False}}))
            return original_open(request, **options)
        with patch.object(self.r.prior.guard.OPEN, 'open', side_effect=open), self.assertRaisesRegex(RuntimeError, 'confirmation capability differs'): self.cli('verify')

    def test_archive_report_registration_requires_exact_stored_report_hash(self):
        self.reviewed_fixture(); output = self.root / 'archive-output'; output.mkdir(); original = self.query
        def query(sql, **options):
            if sql.startswith("select encode(sha256(convert_to(report_raw,'UTF8'))"): return [{'sha256': '0' * 64}]
            return original(sql, **options)
        with patch.object(self.r.admin, 'query', side_effect=query), self.assertRaisesRegex(RuntimeError, 'Stored evaluation report hash differs'): release.archive_evaluation(output)


if __name__ == '__main__': unittest.main()
