"""Fixed recovery controller with synthetic cloud/SQL/model boundaries.

Real source/evidence ZIPs, original-byte hashes and transaction strings are
checked locally. These units do not execute production SQL or qualify a release.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
import zipfile

from builder_continuation_release_test import archive, canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('assessment_recovery_unit', ROOT / 'bin/assessment-recovery-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


class AssessmentRecovery(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='assessment-recovery-unit-'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'jumpserve-infra'; self.back = self.root.parent / 'jumpserve-back-end'
        self.base = self.root / '.test-artifacts/assessment-recovery-release-v1'; self.source = self.base / '20261107T000000Z'; self.source.mkdir(parents=True)
        for module in [release, release.q]:
            for name, value in [('ROOT', self.root), ('BACK', self.back), ('BASE', self.base)]: self.enterContext(patch.object(module, name, value))
        self.r = MagicMock(); self.m = MagicMock()
        for module in [release, release.q]: self.enterContext(patch.object(module, 'r', self.r)); self.enterContext(patch.object(module, 'm', self.m))
        self.r.sha.side_effect = digest; self.r.stamp.return_value = '2026-11-07T00:00:00Z'; self.r.instance.return_value = 'i-087f1493809643115'; self.r.target.return_value = {'synthetic_targets': True}
        self.r.admin.literal.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"; self.r.admin.query.side_effect = self.query; self.r.aws.side_effect = self.aws; self.r.ssm.return_value = dict(command_id='original-verification', instance_id='i-synthetic')
        self.objects, self.reports, self.sql, self.artifacts, self.registered = {}, {}, [], {}, {}; self.m.storage.side_effect = self.storage
        self.revision, self.front_revision = 'a' * 40, 'f' * 40
        self.manifest = dict(version=3, source_revision=self.revision, files={'controller.py': digest(b'# Synthetic retained controller\n')})
        self.runtime('controller.py', b'# Synthetic retained controller\n'); self.write('research-workflow-runtime.json', canonical(self.manifest))
        self.prompts = [dict(id=identity(name), module_id=name, version=version, system_prompt='Synthetic system policy', research_context='Synthetic retained context', published_at='retained-time') for name, version in [('research-autonomy', 'research-autonomy-v10'), ('research-experiment-builder', 'research-experiment-builder-v2')]]
        self.frozen = dict(protocol={'version': 'assessment-recovery-release-v1'}, source_revision=self.revision, runtime_manifest=self.manifest, prompts=self.prompts, image='sha256:' + 'b' * 64)
        self.save('frozen.json', self.frozen); self.save('prepared.json', {'image': self.frozen['image']}); self.save('evaluations-recorded.json', {'status': 'passed'})
        (self.base / 'selected.txt').write_text(self.source.name + '\n')
        self.workflow = dict(max_spend_cents=10000, committed_cents=9980, max_attempts=None, initial_prompt='Original frozen prompt', initial_sha256='c' * 64, deadline_at='2099-01-01T00:00:00Z', status='completed-with-blockers', created_at='2026-11-01T00:00:00Z', overhead_reservation_cents=5)
        self.data = {name: [] for name in ['autonomy_tasks', 'autonomy_turns', 'model_dispatches', 'builder_calls', 'queue_jobs', 'autonomy_events', 'runs', 'measurements', 'assessments']}; self.data['autonomy_workflows'] = [self.workflow]
        self.authorized = dict(max_spend_cents=100000, authorized_by='Synthetic recorded operator'); self.migrations_present = True; self.applied = []; self.count_drift = False
        self.functions = [dict(handler=handler, timeout=420 if handler == 'autonomy.handler' else 29, source_hashes={str(i): 'd' * 64 for i in range(50)}) for handler in ['autonomy.handler', 'api.handler', 'worker.handler']]
        self.r.prior.functions.return_value = self.functions; self.r.prior.security.return_value = {'browser_writes_denied': True}; self.r.prior.PRIVATE = set()
        self.invocation = dict(Status='Success', StandardOutputContent='{"runtime_files_verified":50}')
        self.enterContext(patch.object(release.subprocess, 'check_output', side_effect=self.command)); self.enterContext(patch.object(release.time, 'sleep'))
        self.write('docs/assessment-recovery-release-amendment-v2.json', canonical({'version': 'assessment-recovery-release-amendment-v2'})); self.write('docs/assessment-recovery-release-amendment-v3.json', canonical({'version': 'synthetic-operator-amendment'}))

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def runtime(self, name, raw):
        path = self.back / 'research_workflow' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def save(self, name, value, directory=None):
        path = (directory or self.source) / name; path.parent.mkdir(parents=True, exist_ok=True); release.q.save(path, value); return path
    def out(self, name):
        path = self.base / name; path.mkdir(); return path
    def storage(self, path, raw=None):
        if raw is not None:
            self.assertTrue(path not in self.objects or self.objects[path] == raw, 'Retained object identities cannot change original bytes'); self.objects[path] = raw
        return self.objects[path]
    def command(self, args, **options):
        if args == ['git', 'status', '--porcelain']: return ''
        if args == ['git', 'rev-parse', 'HEAD']: return (self.front_revision if options.get('cwd', Path()).name == 'jumpserve-front-end' else self.revision) + '\n'
        raise AssertionError(args)
    def query(self, sql, **options):
        self.sql.append((sql, options))
        if sql.startswith('select v.id,'): return copy.deepcopy(self.prompts)
        if sql.startswith('insert into agent_prompt_evaluations('):
            self.assertFalse(options['read_only']); prompt, outcome, raw, sha, pointer, reviewer = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]
            self.assertEqual(digest(raw.encode()), sha); self.assertIn(outcome, ['passed', 'failed-or-paused']); self.assertIn('AI', reviewer); self.reports[prompt, sha] = raw; return []
        if sql.startswith('select report_raw from agent_prompt_evaluations'): return [{'report_raw': self.reports[tuple(re.findall(r"'((?:''|[^'])*)'", sql))]}]
        if sql.startswith('select p.proname,'): return [{'proname': 'synthetic-function', 'definition': 'Original retained definition'}]
        if sql.startswith(('select to_regprocedure(', 'select strpos(')): return [{'present': self.migrations_present or any(name in sql for name in self.applied)}]
        if sql.startswith('-- Synthetic migration '): self.assertFalse(options['read_only']); self.applied.append(sql.splitlines()[0].split()[-1]); return []
        if sql.startswith('select has_function_privilege('): return [{'anon_execute': False, 'browser_execute': False}]
        if sql.startswith('select details from research_autonomy_events'): return [{'details': copy.deepcopy(self.authorized)}]
        if sql.startswith('select public.research_autonomy_amend_budget('): self.assertFalse(options['read_only']); self.workflow['max_spend_cents'] = 100000; return [{'result': {'amended': True}}]
        if sql.startswith('select to_jsonb(w)'): return [{'record': copy.deepcopy(self.workflow)}]
        if sql.startswith('select status,configuration,updated_at'): return [{'status': 'ready', 'configuration': {'credential_contents_retained': False}}]
        if sql.startswith('select to_jsonb(t) record from research_'):
            kind = re.search(r'from research_([a-z_]+) ', sql)[1]; return [{'record': copy.deepcopy(row)} for row in self.data[kind]]
        if sql.startswith('select count(*) count from research_'):
            kind = re.search(r'from research_([a-z_]+) ', sql)[1]; return [{'count': len(self.data[kind]) + int(self.count_drift)}]
        if sql.startswith('select storage_path,sha256,byte_count'): return [self.artifacts[re.findall(r"'((?:''|[^'])*)'", sql)[-1]]]
        if sql.startswith('begin;'): self.assertFalse(options['read_only']); return []
        if sql.startswith('select owner_id'): return [{'owner_id': identity('synthetic-owner')}]
        if sql.startswith('select public.research_append('):
            self.assertFalse(options['read_only']); values = [value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)]; record = json.loads(values[-1]); self.registered[record['id']] = dict(sha256=record['sha256'], byte_count=record['byte_count']); return []
        if sql.startswith('select sha256,byte_count'): return [self.registered[re.findall(r"'((?:''|[^'])*)'", sql)[-1]]]
        raise AssertionError('Unexpected SQL: ' + sql)
    def aws(self, service, operation, *args):
        if (service, operation) == ('amplify', 'list-jobs'): return {'jobSummaries': [dict(commitId=self.front_revision, status='SUCCEED', jobId='synthetic-amplify-job')]}
        if (service, operation) == ('amplify', 'get-job'): return {'job': {'summary': dict(commitId=self.front_revision, status='SUCCEED'), 'steps': [{'status': 'SUCCEED'}]}}
        if (service, operation) == ('cloudformation', 'describe-stacks'): return {'Stacks': [{'StackStatus': 'UPDATE_COMPLETE'}]}
        if (service, operation) == ('ssm', 'get-command-invocation'): return copy.deepcopy(self.invocation)
        if (service, operation) == ('ec2', 'describe-volumes'): return {'Volumes': [dict(Size=300, Encrypted=True, Attachments=[{'InstanceId': 'i-087f1493809643115'}])]}
        if (service, operation) == ('ec2', 'describe-snapshots'): return {'Snapshots': [{'State': 'completed'}]}
        raise AssertionError((service, operation, args))
    def retain(self, directory, raw):
        pointer = dict(path='qualification/' + directory.name + '/' + digest(raw), sha256=digest(raw)); self.objects[pointer['path']] = raw; self.save('host-status.json', {'evidence.json': pointer}, directory); return pointer

    def backend_modules(self, **exports):
        modules = {name: types.ModuleType(name) for name in exports}
        for name, values in exports.items(): modules[name].__dict__.update(values)
        self.enterContext(patch.dict(sys.modules, modules)); paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths))
        return modules

    def recovery_inventory(self):
        def retain(name, value, raw=False):
            content = value if raw else canonical(value); key = identity(name); path = 'synthetic-originals/' + key; self.objects[path] = content
            self.artifacts[key] = dict(storage_path=path, sha256=digest(content), byte_count=len(content)); return dict(id=key, artifact_id=key, sha256=digest(content))
        def wire(request):
            # Exact transport boundary sizes are inputs to this controller unit.
            # Wire serialization itself is tested in backend protocol tests.
            size = 96866 if request.get('old_transport') else 87220
            return {'padding': 'x' * (size - len(canonical({'padding': ''})))}
        self.backend_modules(autonomy_model={'parse': lambda value: value}, openclaw_runtime={'translate': lambda body, logical: {'old_transport': True}}, siwc_protocol={'response_request': wire}, workflow={'canonical': canonical})
        for index in range(5):
            task_id, dispatch_id = identity('task-' + str(index)), identity('dispatch-' + str(index))
            stage = 'building' if index == 4 else 'planning'; unknown = index >= 3
            checkpoint = retain('checkpoint-' + str(index), archive({'retained-failure.log': b'Original failure, no observations\n'}), raw=True) if index == 0 else None
            task = dict(id=task_id, claim_id=identity('claim-' + str(index)), stage=stage, status='budget' if index == 0 else 'blocked', attempts=index, context={'builder_checkpoint': checkpoint} if checkpoint else {}, label=None, updated_at='retained-time')
            logical = {'synthetic': True, 'observations': None, 'zero': 0}; request_sha = digest(canonical(logical))
            response = retain('response-' + str(index), {'assessment_label': None, 'evidence_ids': []})
            provenance = {}
            if index == 1:
                provenance['checkpoint'] = retain('dispatch-checkpoint', archive({'original-context.json': canonical({'measurements': None})}), raw=True)
            if unknown:
                receipt = dict(provider_calls=0, native_tool_cleanup=True, container_cleanup='confirmed', admission_unconfirmed=True, bridge_errors=['Research persistence request failed (HTTP 400)'])
                refs = {name: retain(str(index) + '-' + name, value) for name, value in [('receipt.json', receipt), ('logical.json', logical), ('openclaw-http-body.bin', {'synthetic_transport': True})]}
                provenance['artifacts'] = [dict(ref, name=name) for name, ref in refs.items()]
            self.data['autonomy_tasks'].append(task)
            self.data['autonomy_turns'].append(dict(id=dispatch_id, task_id=task_id, request_sha256=request_sha, stage=stage, created_at='2026-11-07T00:01:00Z'))
            self.data['model_dispatches'].append(dict(id=dispatch_id, task_id=task_id, status='unknown' if unknown else 'complete', request_sha256=request_sha, response_sha256=None if unknown else response['sha256'], response_artifact_id=None if unknown else response['id'], provenance=provenance))
        # Intake records are not claim tasks and must not be resumed as claims.
        self.data['autonomy_tasks'].append(dict(id=identity('intake'), claim_id=None, status='complete'))
        self.data['builder_calls'].append(dict(task_id=self.data['autonomy_tasks'][0]['id'], dispatch_id=identity('earlier-complete-native-call'), status='complete'))

    def ready_recovery(self):
        self.recovery_inventory(); release.plan_recovery(self.source)
        self.save('budget-applied.json', {'status': 'passed'}); self.save('deployed-verified.json', {'source_revision': self.revision})

    def test_freeze_retains_exact_candidate_sources_and_prospective_protocol_without_claiming_observations(self):
        originals = dict(claim={'source_id': identity('source'), 'description': 'Original claim'}, protocol={'decision': {'original': True}, 'retained': 'original draft'})
        seen = []
        modules = self.backend_modules(
            autonomy_inputs={'runner_contracts': lambda: {'netem-iperf-v1': {'version': 'synthetic-runner-contract'}}, 'protocol_contract': lambda: {'synthetic': True}},
            autonomy_model={'request': lambda system, ctx: {'system': [{'text': system}], 'context': copy.deepcopy(ctx)}, 'resource_instruction': lambda ctx: 'Retain the recorded resource authorization.'},
            autonomy_methods={'contract': lambda: {'decision': 'synthetic-contract'}}, netem_iperf={'METRICS': {'goodput': 'Mbps'}, 'network_budget': lambda cfg: 1500000},
            network_spec={'bind_inputs': lambda value: dict(value, bound=True)}, workflow={'canonical': canonical, 'validate_protocol': lambda value: seen.append(copy.deepcopy(value))},
            network_execution={'enabled': lambda: False}, test_autonomy_methods={'Recorded': lambda: types.SimpleNamespace(**originals)})
        extras = ['tests/check_experiment_builder_linux.py', 'tests/prepare_builder_image.py', 'tests/prepare_builder_vendor.py', 'experiment-builder.Dockerfile', 'policies/builder-continuation-validation-v1.json', 'policies/builder-continuation-validation-v2.json']
        for name in extras: self.runtime(name, ('Synthetic source: ' + name + '\n').encode())
        for name in ['builder_continuation_qualification_host.py', 'assessment_recovery_qualification_host.py']: self.write('bin/' + name, b'# Synthetic qualification entry point\n')
        self.write('docs/assessment-recovery-release-protocol-v1.json', canonical({'version': 'assessment-recovery-release-v1'})); out = self.out('new-frozen')
        result = release.freeze(out); self.assertEqual(result['maximum_provider_calls'], 2)
        frozen = json.loads((out / 'frozen.json').read_bytes()); first, second = frozen['live_cases']
        self.assertEqual(first['context']['draft_protocol'], seen[0]); self.assertNotIn('decision', seen[0]); self.assertEqual(seen[0]['execution']['replications'], 3); self.assertIsNone(seen[0]['resource_limits']['estimated_cost_usd'])
        self.assertEqual(first['context']['remaining_commitment_cents'], 90020); self.assertEqual(second['context']['remaining_commitment_cents'], 1); self.assertFalse(second['context']['source_material']['trusted_instructions']); self.assertEqual(second['context']['prior_dispatch']['status'], 'unknown')
        self.assertEqual(originals['protocol'], {'decision': {'original': True}, 'retained': 'original draft'}); self.assertEqual(originals['claim']['description'], 'Original claim')
        raw = (out / 'candidate.zip').read_bytes(); self.assertEqual(digest(raw), result['candidate_sha256']); self.assertTrue(any(value == raw for value in self.objects.values()))
        with zipfile.ZipFile(io.BytesIO(raw)) as retained:
            for item in json.loads(retained.read('artifact-manifest.json')):
                value = retained.read(item['path']); self.assertEqual(item['sha256'], digest(value)); self.assertEqual(item['bytes'], len(value))
            self.assertEqual(json.loads(retained.read('frozen.json')), frozen)
        self.assertFalse(modules['network_execution'].enabled()); self.r.ssm.assert_not_called()

    def test_recovery_plan_requires_original_hashes_and_separately_proves_no_provider_admission(self):
        self.recovery_inventory(); before = copy.deepcopy(self.data)
        result = release.plan_recovery(self.source); self.assertEqual(result['tasks'], 5); self.assertEqual(result['completed_dispatches'], 3); self.assertEqual(result['confirmed_pre_provider_dispatches'], 2); self.assertEqual(result['experiment_jobs'], 0)
        plan = json.loads((self.source / 'recovery-plan.json').read_bytes()); self.assertEqual(self.data, before); self.assertEqual(plan['workflow']['committed_cents'], 9980)
        proofs = plan['reconciled_dispatches']; self.assertEqual(proofs[3]['original_derived_bytes'], 96866); self.assertEqual(proofs[3]['corrected_bytes'], 87220); self.assertEqual(proofs[4]['kind'], 'confirmed-pre-provider-admission-failure'); self.assertIsNone(proofs[4]['response_sha256'])
        for item in plan['expected'][:2]:
            raw = (self.source / 'recovery-originals' / (item['task']['id'] + '-checkpoint.zip')).read_bytes(); self.assertEqual(digest(raw), item['checkpoint']['sha256'])
        self.assertTrue(all('assessment-recovery-resumed' not in sql for sql, _ in self.sql))

    def test_recovery_plan_fences_incomplete_inventory_acquisition_unknown_native_and_changed_original_bytes(self):
        self.recovery_inventory(); original = copy.deepcopy(self.data); original_objects = copy.deepcopy(self.objects)
        cases = ['incomplete-inventory', 'acquisition', 'unknown-native', 'changed-original', 'provider-response', 'active-dispatch', 'original-verdict']
        for case in cases:
            with self.subTest(case=case):
                self.data = copy.deepcopy(original); self.objects = copy.deepcopy(original_objects); self.count_drift = case == 'incomplete-inventory'
                if case == 'acquisition': self.data['queue_jobs'].append({'id': identity('acquisition')})
                if case == 'unknown-native': self.data['builder_calls'][0]['status'] = 'unknown'
                if case == 'changed-original': self.objects[next(iter(self.objects))] += b'changed bytes'
                if case == 'provider-response': self.data['model_dispatches'][3]['provenance']['artifacts'].append({'name': 'provider-response.bin'})
                if case == 'active-dispatch': self.data['model_dispatches'][0]['status'] = 'running'
                if case == 'original-verdict':
                    self.enterContext(patch.object(sys.modules['autonomy_model'], 'parse', return_value={'assessment_label': 'supported', 'evidence_ids': []}))
                with self.assertRaises(AssertionError): release.plan_recovery(self.source)
        self.r.ssm.assert_not_called()

    def test_recovery_requires_identical_successful_rollback_and_keeps_original_usage_attempts_and_unknown_receipts(self):
        self.ready_recovery(); before = copy.deepcopy(self.data)
        with self.assertRaises(FileNotFoundError): release.recover(self.source, False)
        result = release.recover(self.source, True); self.assertEqual(result['status'], 'rollback-verified')
        dry = (self.source / 'recovery-dry-run.sql').read_text(); self.assertTrue(dry.startswith('begin;')); self.assertTrue(dry.endswith('rollback;')); self.assertIn("pg_advisory_xact_lock", dry)
        for guard in ['Original usage/deadline', 'Original dispatch changed', 'Retained task changed', 'Unknown provider outcome lacks original-byte no-provider proof', 'Acquisition appeared; preserve experiment identities']:
            self.assertIn(guard, dry)
        result = release.recover(self.source, False); self.assertEqual(result['status'], 'resumed'); committed = (self.source / 'recovery.sql').read_text(); self.assertEqual(committed[:-7] + 'rollback;', dry); self.assertEqual(self.data, before)
        self.save('evaluations-recorded.json', {'status': 'passed', 'changed': True}); before_queries = len(self.sql)
        with self.assertRaisesRegex(AssertionError, 'Identical successful rollback'): release.recover(self.source, False)
        self.assertEqual(len(self.sql), before_queries)

    def test_recovery_retains_original_sql_failure_body_and_raises_a_bounded_typed_error(self):
        self.ready_recovery()
        bodies = [(b'{"message":"Original database rejection\\nprivate detail"}', 'Original database rejection'), (b'not JSON', 'Recovery SQL rejected'), (b'[]', 'Recovery SQL rejected'), (b'{"message":""}', 'Recovery SQL rejected'), (b'{"message":null}', 'Recovery SQL rejected'), (canonical({'message': 'x' * 800}), 'x' * 500)]
        for raw, expected in bodies:
            with self.subTest(raw=raw[:80]):
                def rejected(sql, **options):
                    try: raise urllib.error.HTTPError('https://synthetic.invalid', 400, 'Rejected', {}, io.BytesIO(raw))
                    except urllib.error.HTTPError: raise RuntimeError('Research persistence request failed (HTTP 400)')
                with patch.object(self.r.admin, 'query', side_effect=rejected), self.assertRaisesRegex(RuntimeError, '^' + re.escape(expected) + '$'): release.recover(self.source, True)
                self.assertEqual((self.source / ('recovery-error-' + digest(raw) + '.json')).read_bytes(), raw)
        original = RuntimeError('Synthetic non-HTTP transport failure')
        with patch.object(self.r.admin, 'query', side_effect=original), self.assertRaises(RuntimeError) as caught: release.recover(self.source, True)
        self.assertIs(caught.exception, original); self.assertFalse((self.source / 'recovery-result.json').exists())

    def ready_record(self):
        self.recovery_inventory(); previous = copy.deepcopy(self.workflow); self.workflow['max_spend_cents'] = 100000; self.workflow['status'] = 'running'
        self.data['autonomy_events'] = [dict(event='assessment-recovery-resumed', task_id=task['id'], created_at='2026-11-07T00:00:00Z') for task in self.data['autonomy_tasks'] if task['claim_id']]
        self.save('deployed-verified.json', {'status': 'passed'}); self.save('budget-applied.json', dict(status='passed', previous=previous)); self.save('recovery-result.json', {'status': 'resumed'}); self.save('migrations-applied.json', {'migrations': [{'name': 'synthetic-exact-migration', 'status': 'present-before-release'}]})
        self.save('reviewed.json', dict(passed=True, actual_calls=2, usage=dict(actual_input_tokens=14527, actual_output_tokens=1891), reviewer=dict(type='AI', independent=False)))
        activated = dict(mode='activated', status='complete', preserved_worker='i-087f1493809643115', functions=[{'source_files_verified': 50}], capabilities={'autonomy_enabled': True}, polling={'interval_seconds': 15}, prompts=[dict(module_id='research-autonomy', id='6117e5c5-84ce-5c31-aaa7-0d1d3522e62e')])
        for mode, value in [('activated', activated), ('executor', dict(mode='executor', status='complete'))]: self.save('receipt.json', value, self.root / '.test-artifacts/builder-production-v2' / ('20261107T000000Z-' + mode))
        self.save('receipt.json', {'mode': 'activated', 'status': 'stale'}, self.root / '.test-artifacts/builder-production-v2/20261001T000000Z')
        browser = dict(amended=True, passed=True, actual_authenticated_request=False, checks=[dict(themes=['light', 'dark'], rendered_budget_matches_record=True)] + [dict(public_read=True) for _ in range(3)])
        self.save('report.json', browser, self.base / 'browser/20261107T000000Z'); self.save('report.json', {'amended': False}, self.base / 'browser/20261106T000000Z')
        self.save('host-status.json', {'original_failed_outcome': True}, self.base / '20261028T223546360526Z')
        for name in ['openclaw-release', 'autonomy-release']:
            for stamp in ['20261001T000000Z', '20261107T000000Z']:
                directory = self.root / '.test-artifacts' / name / stamp; self.save('receipt.json', {'original': stamp}, directory); (directory / 'cdk.log').write_text('Synthetic retained build output\n'); (directory / 'excluded.txt').write_text('Excluded ancillary note\n')
            (self.root / '.test-artifacts' / name / 'selected.txt').write_text('not a campaign directory\n')
        for name in ['docs/assessment-4055396e-recovery-protocol-v1.json', 'docs/assessment-recovery-release-protocol-v1.json', 'docs/assessment-recovery-release-amendment-v4.json', 'docs/assessment-recovery-actual-answer-review-v1.json', '.test-artifacts/assessment-recovery-release-v1/frontend-budget-label-followup.json', '.test-artifacts/assessment-recovery-release-v1/progress-after-activation-public.json']: self.write(name, canonical({'retained_synthetic_fixture': name}))
        self.write('docs/assessment-4055396e-recovery-validation-v1.json', canonical(dict(checks={'backend_tests': 1, 'isolated_sql': 'synthetic-only'}, windows_seconds={'local_unit_only': 1})))
        for name in ['202610280002_assessment_budget_amendments.sql', '202610280003_controller_reconciliation_window.sql']: self.write('database/' + name, b'-- Synthetic original migration bytes\n')
        self.write('bin/assessment-recovery-release.py', (ROOT / 'bin/assessment-recovery-release.py').read_bytes()); self.write('bin/verify_assessment_recovery_browser.mjs', b'// Synthetic browser verifier source\n')
        (self.source / 'retained-zero-null.bin').write_bytes(canonical({'zero': 0, 'missing': None})); (self.source / 'excluded-note.txt').write_text('Synthetic ancillary note\n')

    def test_recorded_release_verifies_original_archive_and_labels_development_checks_and_missing_scientific_results(self):
        self.ready_record(); out = self.out('recorded-release')
        result = release.record_release(self.source, out); self.assertEqual(result['status'], 'deployed-with-conditional-verification-gap'); self.assertTrue(result['release_blocking_checks_passed']); self.assertFalse(result['authenticated_upload_chat_reverified']); self.assertEqual(result['tasks_resumed'], 5)
        report = json.loads((out / 'production-status-retained.json').read_bytes()); self.assertFalse(report['scientific_completion']); self.assertFalse(report['qualification']['independent']); self.assertFalse(report['qualification']['held_out']); self.assertIsNone(report['measured_charges_usd']); self.assertIsNone(report['budget']['ai_turn_cap']); self.assertEqual(report['recovery']['recorded_measurements'], 0); self.assertEqual(report['recovery']['model_turns_after_resumption'], 5)
        self.assertEqual(report, json.loads((self.root / 'docs/assessment-recovery-production-status-v1.json').read_bytes())); evidence = result['evidence']; self.assertFalse(evidence['public']); self.assertEqual(evidence['sha256'], evidence['retrieved_sha256'])
        raw = self.objects[release.STUDY + '/' + evidence['sha256']]
        with zipfile.ZipFile(io.BytesIO(raw)) as retained:
            self.assertIsNone(retained.testzip()); entries = json.loads(retained.read('artifact-manifest.json')); self.assertEqual(len(entries), evidence['members'])
            self.assertFalse(any(item['path'].endswith('excluded-note.txt') or item['path'].endswith('excluded.txt') for item in entries))
            self.assertFalse(any('/autonomy-release/20261001' in item['path'] for item in entries))
            for item in entries:
                content = retained.read(item['path']); self.assertEqual(item['sha256'], digest(content)); self.assertEqual(item['bytes'], len(content))
            zero = retained.read(str((self.source / 'retained-zero-null.bin').relative_to(self.root))); self.assertEqual(json.loads(zero), {'zero': 0, 'missing': None})
        self.assertEqual(len(self.registered), 1); self.assertEqual(len(self.reports), 2)
        self.assertTrue(all(json.loads(value)['new_qualification_calls_in_recording'] == 0 for value in self.reports.values())); self.r.ssm.assert_not_called()

    def test_recording_fences_count_drift_changed_frozen_policy_and_missing_recovery_events_before_retaining_success(self):
        self.ready_record(); original = copy.deepcopy(self.data)
        for case in ['count-drift', 'changed-deadline', 'missing-event']:
            with self.subTest(case=case):
                self.data = copy.deepcopy(original); self.count_drift = case == 'count-drift'
                if case == 'changed-deadline': self.data['autonomy_workflows'][0]['deadline_at'] = '2100-01-01T00:00:00Z'
                if case == 'missing-event': self.data['autonomy_events'].pop()
                with self.assertRaises(AssertionError): release.record_release(self.source, self.out('failed-' + case))
                self.assertEqual(self.registered, {}); self.assertEqual(self.reports, {})

    def test_cli_dispatches_only_fixed_modes_records_private_receipts_and_strips_unbounded_status_cases(self):
        modes = ['freeze', 'prepare', 'native', 'live', 'evidence', 'status', 'collect-status', 'collect', 'record-review', 'migrate', 'verify-held', 'budget', 'plan-recovery', 'dry-run-recovery', 'recover', 'record-release']
        with contextlib.ExitStack() as stack:
            actions = {name: stack.enter_context(patch.object(release, name, return_value={'status': 'synthetic-complete'})) for name in ['freeze', 'record_review', 'migrate', 'verify_held', 'budget', 'plan_recovery', 'recover', 'record_release']}
            dispatch = stack.enter_context(patch.object(release.q, 'dispatch', return_value={'status': 'synthetic-complete'}))
            bounded = {name: stack.enter_context(patch.object(release.q, name, side_effect=lambda source: {'status': 'synthetic-complete', 'cases': ['large original payload']})) for name in ['status', 'collect_status', 'collect']}
            for mode in modes:
                with self.subTest(mode=mode), patch.object(sys, 'argv', ['assessment-recovery-release.py', mode]), contextlib.redirect_stdout(io.StringIO()) as stdout:
                    release.main(); printed = json.loads(stdout.getvalue()); receipt_path = Path(printed['directory']) / 'receipt.json'; receipt = json.loads(receipt_path.read_bytes())
                    self.assertEqual(printed['mode'], mode); self.assertEqual(receipt['status'], 'complete'); self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
                    if mode in ['status', 'collect-status', 'collect']: self.assertNotIn('cases', receipt['result']); bounded[mode.replace('-', '_')].assert_called_with(self.source)
                    if mode == 'live': self.assertEqual(receipt['operator_amendment_sha256'], digest((self.root / 'docs/assessment-recovery-release-amendment-v3.json').read_bytes()))
            self.assertEqual(actions['recover'].call_args_list[0].args, (self.source, True)); self.assertEqual(actions['recover'].call_args_list[1].args, (self.source, False)); self.assertEqual(dispatch.call_count, 4)
            actions['freeze'].side_effect = RuntimeError('Synthetic freeze failed')
            with patch.object(sys, 'argv', ['assessment-recovery-release.py', 'freeze']), contextlib.redirect_stdout(io.StringIO()) as stdout, self.assertRaisesRegex(RuntimeError, 'Synthetic freeze failed'): release.main()
            receipt = json.loads(stdout.getvalue()); self.assertEqual(receipt['status'], 'failed'); self.assertEqual(receipt['reason'], 'Synthetic freeze failed')

    def test_cli_entrypoint_rejects_unknown_modes_before_touching_external_services(self):
        source = ROOT / 'bin/assessment-recovery-release.py'
        with patch.object(sys, 'argv', [str(source), 'unsupported-unit-mode']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            exec(compile(source.read_bytes(), str(source), 'exec'), {'__name__': '__main__', '__file__': str(source)})
        self.assertEqual(stopped.exception.code, 2); self.r.ssm.assert_not_called(); self.r.admin.query.assert_not_called()

    def test_review_retains_both_exposed_live_answers_and_failed_pre_provider_campaign_with_exact_hashes(self):
        self.save('reviewed.json', dict(passed=True, source_revision=self.revision, reviewer={'type': 'AI', 'independent': False})); self.save('native.json', {'status': 'passed'}); self.save('live.json', dict(status='awaiting-substantive-review', actual_calls=2, cases=[{'structural_checks_passed': True}, {'structural_checks_passed': True}]))
        pointer = self.retain(self.source, archive({'original-answer.json': canonical({'zero': 0, 'missing': None})})); prior = self.out('20261028T223546360526Z'); self.retain(prior, archive({'original-failure.bin': b'Original pre-provider harness failure\n'}))
        result = release.record_review(self.source); self.assertEqual(result['status'], 'passed'); self.assertEqual(len(self.reports), 4); self.assertNotEqual(result['report_sha256'], result['original_failed_report_sha256'])
        reports = [json.loads(raw) for raw in self.reports.values()]
        self.assertTrue(any(value.get('original_live_provider_calls') == 0 for value in reports)); self.assertTrue(any(value.get('actual_answers', {}).get('actual_calls') == 2 for value in reports)); self.assertTrue(all(not value.get('scientific_completion', False) for value in reports))
        self.objects[pointer['path']] += b'changed bytes'
        with self.assertRaises(AssertionError): release.record_review(self.source)

    def test_migrations_require_passed_evaluation_preserve_exact_bytes_and_recheck_browser_denials(self):
        names = ['202610280002_assessment_budget_amendments.sql', '202610280003_controller_reconciliation_window.sql']
        for name in names: self.write('database/' + name, ('-- Synthetic migration ' + ('research_autonomy_amend_budget' if 'budget' in name else '480 seconds') + '\n').encode())
        self.assertEqual([item['status'] for item in release.migrate(self.source)['migrations']], ['present-before-release'] * 2)
        self.migrations_present = False
        result = release.migrate(self.source); self.assertEqual([item['status'] for item in result['migrations']], ['applied-exact-retained-bytes'] * 2); self.assertEqual(len(self.applied), 2)
        for item in result['migrations']:
            raw = (self.root / 'database' / item['name']).read_bytes(); self.assertEqual(item['sha256'], digest(raw)); self.assertTrue(any(value == raw for value in self.objects.values()))
        self.save('evaluations-recorded.json', {'status': 'failed-or-paused'})
        with self.assertRaises(AssertionError): release.migrate(self.source)

    def test_budget_amendment_requires_compatible_deployment_exact_frontend_and_recorded_authorization(self):
        self.save('deployed-verified.json', dict(status='passed', source_revision=self.revision)); original = copy.deepcopy(self.workflow)
        result = release.budget(self.source); self.assertEqual(result['maximum_usd'], 1000); self.assertTrue(result['tasks_not_resumed']); self.assertEqual(self.workflow['committed_cents'], original['committed_cents'])
        for key in ['initial_prompt', 'initial_sha256', 'deadline_at', 'max_attempts', 'status']: self.assertEqual(self.workflow[key], original[key])
        recorded = json.loads((self.source / 'budget-applied.json').read_bytes()); self.assertEqual(recorded['previous'], original); self.assertEqual(recorded['amended']['max_spend_cents'], 100000)
        self.authorized['max_spend_cents'] = 200000; before = len([sql for sql, _ in self.sql if sql.startswith('select public.research_autonomy_amend_budget')])
        with self.assertRaises(AssertionError): release.budget(self.source)
        self.assertEqual(len([sql for sql, _ in self.sql if sql.startswith('select public.research_autonomy_amend_budget')]), before)

    def test_held_release_checks_all_fifty_source_hashes_and_preserves_the_existing_worker_before_admission(self):
        self.save('migrations-applied.json', {'status': 'passed'})
        cap = dict(autonomy=dict(enabled=False, defaults=dict(attempts_per_claim=None, maximum_spend_usd=100), runtime={'status': 'ready'}), networking={'runners': [dict(id=name, enabled=True) for name in ['netem-iperf-v1', 'built-package-v1']]})
        with patch.object(self.r.prior.guard.OPEN, 'open', return_value=io.BytesIO(canonical(cap))): result = release.verify_held(self.source, self.source)
        self.assertTrue(result['admission_held']); self.assertEqual(result['runtime_files'], 50); self.assertEqual(result['worker'], 'i-087f1493809643115')
        verified = json.loads((self.source / 'deployed-verified.json').read_bytes()); self.assertFalse(verified['auth_upload_chat_reverified']); self.assertEqual(verified['capabilities_sha256'], digest(canonical(cap)))
        self.r.aws.side_effect = [dict(Stacks=[dict(StackStatus='UPDATE_COMPLETE')])] * 2 + [dict(Status='Pending')] * 12
        with self.assertRaises(AssertionError): release.verify_held(self.source, self.source)
        self.assertEqual(json.loads((self.source / 'worker-verification.json').read_bytes())['Status'], 'Pending')


if __name__ == '__main__': unittest.main()
