"""Production-verifier units with synthetic HTTP/AWS/database boundaries.

Exact source ZIPs and raw measurement artifacts are local fixtures. No cloud,
provider, database, Google session or actual scientific trial is used.
"""
import base64
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from builder_continuation_release_test import archive, canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/verify-research-production.py'
EXISTING = '76c70fd9-0217-464e-8c26-0a47832409a3'


class Response(io.BytesIO):
    def __init__(self, raw, status=200): super().__init__(raw); self.status = status


class ResearchProductionVerifier(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='research-verifier-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.directory = self.root / '.test-artifacts/research-release/unit'; self.directory.mkdir(parents=True)
        self.scheduler, self.store, self.preparation = [MagicMock() for _ in range(3)]
        self.store.ACCOUNT = '395567831870'; self.store.PROJECT = 'regphejnlvfpyokpniny'; self.preparation.VERSION = 'synthetic-preparation-v1'
        self.workflow = types.SimpleNamespace(canonical=canonical, digest=digest, now=lambda: '2026-11-07T00:00:00Z', paper_details=lambda value: copy.deepcopy(value), numerical_protocol=lambda *args: dict(resource_limits={}, configurations=args[-1]), protocol_record=lambda document, ident: dict(id=ident, document=copy.deepcopy(document), sha256=digest(canonical(document))), FIELDS={'assessments': ('id', 'value')})
        modules = dict(scheduler=self.scheduler, store=self.store, workflow=self.workflow, preparation=self.preparation)
        self.modules = modules
        original_path = list(sys.path); self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('research_production_verifier_unit', SOURCE); self.verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.verifier)
        self.v = self.verifier; self.v.ROOT = self.root; self.v.DIRECTORY = self.directory
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.ticks = 0; self.enterContext(patch.object(self.v.time, 'monotonic', side_effect=lambda: self.ticks)); self.enterContext(patch.object(self.v.time, 'sleep', side_effect=self.sleep))
        self.rows = {}; self.originals = {}; self.appends = []; self.operations = []; self.studies = {}; self.queues = {}; self.prepared = False; self.prepared_id = identity('prepared'); self.auto_snapshots = 0
        self.store.rows.side_effect = self.read; self.store.rpc.side_effect = self.rpc; self.store.append.side_effect = self.append; self.store.artifact_bytes.side_effect = lambda study, ident, **options: self.originals[ident]
        self.scheduler.enqueue.side_effect = self.enqueue; self.scheduler.snapshot.side_effect = self.snapshot
        self.preparation.status.side_effect = self.preparation_status; self.preparation.prepare.side_effect = self.prepare; self.preparation.enqueue.side_effect = self.enqueue_preparation; self.preparation.compiled.side_effect = lambda study, plan: dict(records=[dict(kind=kind, record=copy.deepcopy(row)) for kind in ['protocols', 'assessments'] for row in self.rows[kind]])
        self.http_original = self.v.http
        self.http = self.enterContext(patch.object(self.v, 'http', side_effect=self.http_response))

    def sleep(self, seconds): self.ticks += seconds
    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def read(self, kind, query, public=False):
        if public: return []
        study = str(query.get('study_id', query.get('id', ''))).removeprefix('eq.')
        if study == EXISTING: return [{'id': 'unchanged-existing-' + kind}]
        if kind == 'studies': return [dict(id=study, **self.studies[study])]
        if kind == 'study_owners': return [{'owner_id': identity('synthetic-operator')}]
        values = copy.deepcopy(self.rows.get(kind, [])); offset = int(query.get('offset', 0)); limit = int(query.get('limit', len(values)))
        return values[offset:offset + limit]
    def rpc(self, function, payload):
        self.operations.append((function, copy.deepcopy(payload))); self.assertEqual(function, 'research_create_study'); self.studies[payload['p_id']] = copy.deepcopy(payload['p_document']); return {'created': True}
    def append(self, study, actor, kind, record): self.appends.append((study, actor, kind, copy.deepcopy(record)))
    def enqueue(self, study, actor, payload): self.queues[payload['request_id']] = dict(id=payload['request_id'], execution_mode='automatic', status='running')
    def artifact_fixture(self, count):
        records = []
        for index in range(count):
            raw = canonical({'synthetic_original': index, 'zero': 0, 'missing': None}); ident = identity('raw-' + str(index)); self.originals[ident] = raw; records.append(dict(id=ident, sha256=digest(raw), byte_count=len(raw)))
        self.rows['artifacts'] = records
    def snapshot(self, study, actor):
        self.auto_snapshots += 1
        if self.prepared:
            jobs = list(copy.deepcopy(self.queues).values())
            if self.auto_snapshots == 1:
                for job in jobs:
                    if job['execution_mode'] == 'automatic': job['status'] = 'running'
            return dict(jobs=jobs, events=[])
        self.rows['runs'] = [dict(status='complete'), dict(status='partial')]; self.rows['measurements'] = [dict(status='missing', value=None), dict(status='recorded', value='0'), dict(status='recorded', value='1'), dict(status='recorded', value='2')]
        self.artifact_fixture(4)
        status = 'running' if self.auto_snapshots == 1 else 'awaiting-review'
        return dict(jobs=[dict(job, status=status) for job in self.queues.values()], events=[dict(event='claimed', details={'worker_id': identity('worker-' + str(index))}) for index in range(2)])
    def preparation_status(self, study):
        if not self.prepared: return dict(available_plan=dict(automatic_jobs=6, manual_jobs=14))
        jobs = [dict(job, status=self.queues.get(job['id'], {}).get('status', 'not-queued')) for job in self.prepared_jobs]
        return dict(prepared=[dict(id=self.prepared_id, queued_jobs=len(self.queues), status='partially-queued', jobs=jobs)])
    def prepare(self, study, actor, payload):
        if self.prepared: return dict(replayed=True, prepared={'id': self.prepared_id})
        self.prepared = True; self.prepared_jobs = [dict(id=identity('prepared-job-' + str(index)), execution_mode='automatic' if index < 6 else 'manual') for index in range(20)]
        self.rows['prepared_plans'] = [{'id': self.prepared_id}]; self.rows['protocols'] = [dict(id=identity('frozen-protocol'), document={'original_zero': 0, 'missing': None}, sha256='f' * 64)]
        self.rows['assessments'] = [dict(id=identity('assessment-' + str(index)), value='Original imported finding') for index in range(15)]
        self.rows['runs'] = [dict(status='complete', id=job['id']) for job in self.prepared_jobs[:6]]
        self.rows['published_values'] = [dict(id=identity('published-' + str(index)), value=index) for index in range(1152)]
        self.rows['measurements'] = [dict(published_id=row['id'], status='recorded', value=row['value'], details={'label': ['reproduced', 'discrepant', 'inconclusive'][index % 3]}) for index, row in enumerate(self.rows['published_values'])]
        self.artifact_fixture(2); return dict(prepared=dict(id=self.prepared_id, jobs=copy.deepcopy(self.prepared_jobs)))
    def enqueue_preparation(self, study, actor, payload):
        job = next(job for job in self.prepared_jobs if job['id'] == payload['job_id']); self.queues[job['id']] = dict(job, status='awaiting-review' if job['execution_mode'] == 'automatic' else 'manual')
    def http_response(self, path, method='GET', token=None):
        if path == '/capabilities': return 200, dict(queue={'workers_enabled': True, 'claim_labels_automatic': False}, arbitrary_code_execution=False, preparation=dict(version=self.preparation.VERSION, source_grounded_plans=True, automatic_claim_extraction=False))
        if path == '/studies' and method == 'GET': return 200, dict(access='published', studies=[])
        return (401 if method == 'POST' or '?mine=1' in path or path.endswith(('/queue', '/prepare')) else 404), {'error': 'Synthetic access denied'}

    def test_import_has_no_external_actions_and_http_preserves_method_bearer_and_error_status(self):
        self.store.rpc.assert_not_called(); self.store.rows.assert_not_called(); self.assertFalse(self.v.report['passed'])
        with patch.object(self.v.urllib.request, 'urlopen', return_value=Response(b'{"zero":0,"missing":null}')) as opener:
            status, result = self.http_original('/studies', 'POST', 'synthetic-session')
        self.assertEqual((status, result), (200, {'zero': 0, 'missing': None})); request = opener.call_args.args[0]
        self.assertEqual(request.full_url, self.v.ORIGIN + '/research/studies'); self.assertEqual(request.data, b'{}'); self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-session'); self.assertEqual(opener.call_args.kwargs, {'timeout': 25})
        error = urllib.error.HTTPError('https://synthetic.invalid', 401, 'Denied', {}, io.BytesIO(b'{"error":"Sign in"}'))
        with patch.object(self.v.urllib.request, 'urlopen', side_effect=error): self.assertEqual(self.http_original('/studies'), (401, {'error': 'Sign in'}))

    def test_public_checks_validate_preparation_contract_and_every_unauthenticated_operation(self):
        result = self.v.public_checks(); self.assertEqual(result['public_studies'], 0); self.assertTrue(result['forged_bearer_denied']); self.assertEqual(self.http.call_count, 9)
        self.v.PREPARATION_RELEASE = True; self.http.reset_mock(); self.v.public_checks(); self.assertEqual(self.http.call_count, 13)
        self.assertEqual(json.loads((self.directory / 'capabilities.json').read_bytes())['preparation']['version'], self.preparation.VERSION)
        with patch.object(self.v, 'http', return_value=(200, {'queue': {'workers_enabled': False}})), self.assertRaises(AssertionError): self.v.public_checks()

    def test_scheduled_fixture_preserves_zero_missingness_and_original_hashes_before_any_publication(self):
        result = self.v.scheduled_fixture(); self.assertEqual(result['run_statuses'], ['complete', 'partial']); self.assertEqual(result['measurements'], 4); self.assertEqual(result['recorded_zero'], 1); self.assertEqual(result['missing'], 1)
        self.assertEqual(result['claiming_invocations'], 2); self.assertEqual(self.auto_snapshots, 2); self.assertEqual(self.ticks, 5)
        self.assertFalse(result['published']); self.assertFalse(self.v.report['private_fixture']['published']); self.assertNotEqual(self.v.report['private_fixture']['actor_identity_kind'], 'Google user')
        self.assertEqual(len([record for _, _, kind, record in self.appends if kind == 'campaigns']), 2)
        for item in result['artifacts']: self.assertEqual(digest(self.originals[item['id']]), item['sha256'])
        self.assertEqual(json.loads((self.directory / 'recorded-measurements.json').read_bytes())[0]['value'], None)

    def test_preparation_resumes_partial_queue_without_changing_the_existing_workspace_or_frozen_assessments(self):
        result = self.v.preparation_fixture(); self.assertEqual(result['automatic_runs'], 6); self.assertEqual(result['manual_tasks'], 14); self.assertEqual(result['cells'], 1152)
        self.assertEqual(result['numerical_cell_labels'], dict(reproduced=384, discrepant=384, inconclusive=384)); self.assertEqual(result['assessments_changed'], 0); self.assertTrue(result['user_workspace_unchanged'])
        self.assertFalse(result['publication']); self.assertFalse(result['authenticated_google_request']); self.assertEqual(len(self.operations), 1)
        partial = json.loads((self.directory / 'preparation-partial-status.json').read_bytes()); self.assertEqual(partial['queued_jobs'], 2)
        self.assertEqual(self.v.report['existing_user_workspace']['before'], self.v.report['existing_user_workspace']['after'])

    def test_scheduled_timeout_preserves_the_original_fixture_instead_of_claiming_a_successful_or_empty_run(self):
        def pending(study, actor): return dict(jobs=[dict(job, status='running') for job in self.queues.values()], events=[])
        self.scheduler.snapshot.side_effect = pending
        with self.assertRaises(AssertionError): self.v.scheduled_fixture()
        self.assertEqual(self.ticks, 180); self.assertEqual(len(self.queues), 2)
        self.assertTrue((self.directory / 'fixture-definition.json').exists()); self.assertTrue((self.directory / 'fixture-input-0.json').exists()); self.assertFalse((self.directory / 'recorded-measurements.json').exists()); self.assertFalse(self.v.report['passed'])

    def test_preparation_timeout_retains_its_last_queue_snapshot_and_original_unpublished_records(self):
        def pending(study, actor):
            return dict(jobs=[dict(job, status='running' if job['execution_mode'] == 'automatic' else 'manual') for job in self.queues.values()], events=[])
        self.scheduler.snapshot.side_effect = pending
        with self.assertRaises(AssertionError): self.v.preparation_fixture()
        self.assertEqual(self.ticks, 240); snapshot = json.loads((self.directory / 'preparation-queue-snapshot.json').read_bytes())
        self.assertEqual(len(snapshot['jobs']), 20); self.assertEqual(len(self.rows['assessments']), 15); self.assertFalse(self.v.report['passed'])
        self.assertTrue(all(row['status'] in ['running', 'manual'] for row in snapshot['jobs']))

    def test_preparation_followup_is_read_only_and_reuses_original_failed_report_and_exact_frozen_records(self):
        self.v.preparation_fixture(); study = self.v.report['preparation_fixture']['study_id']; before = self.v.report['existing_user_workspace']['before']
        baseline = dict(protocol='research-preparation-production-protocol-v1', passed=False, preparation_fixture={'study_id': study}, existing_user_workspace={'before': before})
        previous = self.write('.test-artifacts/research-release/20261007T221548717353Z/production-server-report.json', canonical(baseline)); original = previous.read_bytes(); self.operations.clear(); self.v.PREPARATION_FOLLOWUP = True
        self.assertTrue(self.v.preparation_fixture()['user_workspace_unchanged']); self.assertEqual(self.operations, []); self.assertEqual(previous.read_bytes(), original)
        self.assertEqual(self.v.report['followup_of']['sha256'], digest(original)); self.assertFalse(self.v.report['followup_of']['experiment_repeated']); self.assertFalse(self.v.report['followup_of']['production_writes'])

    def configuration_fixture(self):
        self.raw = archive({'controller.py': b'# Exact retained synthetic controller\n'})
        self.write('research-workflow-runtime.json', canonical({'files': {'controller.py': digest(b'# Exact retained synthetic controller\n')}})); self.write('cdk.json', canonical({'context': {'supabaseAnonKey': 'synthetic-public-key'}}))
        self.clients = {name: MagicMock() for name in ['sts', 'cloudformation', 'lambda', 'events', 'secretsmanager']}
        self.clients['sts'].get_caller_identity.return_value = {'Account': self.store.ACCOUNT}
        self.clients['cloudformation'].describe_stacks.return_value = {'Stacks': [dict(StackStatus='UPDATE_COMPLETE', StackId='synthetic-stack-id')]}
        self.inventory = {'StackResourceSummaries': [dict(LogicalResourceId='ResearchWorkflowApiE04EBDAC', PhysicalResourceId='SyntheticApi'), dict(LogicalResourceId='ResearchWorkflowQueueWorker702E601D', PhysicalResourceId='SyntheticWorker'), dict(LogicalResourceId='ResearchWorkflowQueuePoll49F7FA3B', PhysicalResourceId='SyntheticQueuePoll')]}
        self.clients['cloudformation'].get_paginator.return_value.paginate.return_value.build_full_result.return_value = self.inventory
        self.clients['lambda'].get_function_configuration.side_effect = lambda FunctionName: dict(Runtime='python3.12', MemorySize=512, Timeout=180 if FunctionName == 'SyntheticWorker' else 29, Handler='worker.handler' if FunctionName == 'SyntheticWorker' else 'api.handler')
        self.clients['lambda'].get_function_concurrency.return_value = {}
        self.clients['lambda'].get_function.return_value = {'Code': {'Location': 'https://signed.example.test/original-code'}, 'Configuration': {'CodeSha256': base64.b64encode(bytes.fromhex(digest(self.raw))).decode()}}
        self.clients['lambda'].get_account_settings.return_value = {'AccountLimit': {'ConcurrentExecutions': 100, 'UnreservedConcurrentExecutions': 80}}
        self.clients['events'].describe_rule.return_value = dict(State='ENABLED', ScheduleExpression='rate(1 minute)')
        self.clients['events'].list_targets_by_rule.return_value = {'Targets': [{'RetryPolicy': dict(MaximumRetryAttempts=0, MaximumEventAgeInSeconds=60)}]}
        self.clients['secretsmanager'].get_secret_value.return_value = {'SecretString': 'synthetic-private-service-key'}
        self.boto = MagicMock(); self.boto.Session.return_value.client.side_effect = lambda name: self.clients[name]
        self.credentials = dict(AccessKeyId='synthetic-access-id', SecretAccessKey='synthetic-secret', SessionToken='synthetic-session')
        self.enterContext(patch.dict(sys.modules, {'boto3': self.boto})); self.cli = self.enterContext(patch.object(self.v.subprocess, 'check_output', return_value=canonical(self.credentials))); self.open = self.enterContext(patch.object(self.v.urllib.request, 'urlopen', side_effect=lambda *args, **options: Response(self.raw)))

    def test_configuration_hashes_original_lambda_bytes_and_keeps_ephemeral_credentials_out_of_receipts(self):
        self.configuration_fixture(); result = self.v.configuration_checks(); self.assertEqual(len(result['functions']), 2)
        self.assertEqual(result['account_concurrency'], 100); self.assertEqual(result['unreserved_pool'], 80)
        self.cli.assert_called_once_with(['aws', 'configure', 'export-credentials', '--profile', 'jumpserve', '--format', 'process'], timeout=20)
        self.assertEqual(self.boto.Session.call_args.kwargs['aws_session_token'], 'synthetic-session'); self.assertEqual(os.environ['SUPABASE_SERVICE_ROLE_KEY'], 'synthetic-private-service-key')
        for function in result['functions']: self.assertEqual(function['zip_original_sha256'], digest(self.raw)); self.assertIsNone(function['reserved_concurrency'])
        self.assertEqual((self.directory / 'api-lambda.zip').read_bytes(), self.raw); self.assertEqual((self.directory / 'worker-lambda.zip').read_bytes(), self.raw)
        self.assertNotIn('synthetic-private-service-key', json.dumps(result)); self.assertNotIn('synthetic-session', json.dumps(self.v.report))
        self.inventory['NextToken'] = 'truncated-inventory'
        with self.assertRaisesRegex(AssertionError, 'truncated'): self.v.configuration_checks()

    def test_main_selects_each_frozen_mode_and_writes_hashed_originals_without_reporting_google_or_scientific_validation(self):
        for index, mode in enumerate([[], ['--preparation'], ['--preparation-followup']]):
            self.v.DIRECTORY = self.root / '.test-artifacts/research-release' / str(index)
            def configuration():
                (self.v.DIRECTORY / 'retained-original.bin').write_bytes(b'Original zero=0 missing=null\n'); (self.v.DIRECTORY / 'subdirectory').mkdir(); return {'synthetic': True}
            with self.subTest(mode=mode), patch.object(sys, 'argv', ['verify-research-production.py', *mode]), patch.object(self.v, 'configuration_checks', side_effect=configuration), patch.object(self.v, 'public_checks', return_value={}), patch.object(self.v, 'scheduled_fixture', return_value={}) as scheduled, patch.object(self.v, 'preparation_fixture', return_value={}) as prepared, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.v.main(), 0)
            report = json.loads((self.v.DIRECTORY / 'production-server-report.json').read_bytes()); self.assertTrue(report['passed']); self.assertFalse(report['authenticated_google_request_verified']); self.assertIsNone(report['measured_charges_usd'])
            self.assertEqual(report['artifacts'][0]['sha256'], digest(b'Original zero=0 missing=null\n')); self.assertEqual(scheduled.call_count, 0 if mode == ['--preparation-followup'] else 1); self.assertEqual(prepared.call_count, 1 if mode else 0)
            if mode == ['--preparation-followup']: self.assertEqual(report['amendment'], 'research-preparation-production-amendment-v2')
            text = output.getvalue(); self.assertTrue(json.loads(text[text.index('{'):])['passed'])
        self.v.DIRECTORY = self.root / '.test-artifacts/research-release/failed'
        with patch.object(sys, 'argv', ['verify-research-production.py']), patch.object(self.v, 'configuration_checks', side_effect=RuntimeError('Synthetic private operational failure')), contextlib.redirect_stdout(io.StringIO()): self.assertEqual(self.v.main(), 1)
        report = json.loads((self.v.DIRECTORY / 'production-server-report.json').read_bytes()); self.assertFalse(report['passed']); self.assertEqual(report['failure_type'], 'RuntimeError'); self.assertFalse(report['checks'][0]['passed']); self.assertNotIn('Synthetic private operational failure', json.dumps(report))

    def test_entrypoint_rejects_unknown_modes_before_creating_a_campaign_or_starting_cloud_checks(self):
        # Execute the unchanged source with a temporary application-root identity.
        # The compiled filename stays bound to its exact original source bytes.
        self.write('bin/research-workflow-database.py', b'# Synthetic unused import boundary\n')
        with patch.dict(sys.modules, self.modules), patch.object(sys, 'argv', ['verify-research-production.py', '--unsupported']), self.assertRaisesRegex(SystemExit, 'Only --preparation'):
            exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), {'__name__': '__main__', '__file__': str(self.root / 'bin/verify-research-production.py')})
        self.store.rpc.assert_not_called(); self.assertFalse((self.root / '.test-artifacts/research-release' / self.v.STAMP).exists())


if __name__ == '__main__': unittest.main()
