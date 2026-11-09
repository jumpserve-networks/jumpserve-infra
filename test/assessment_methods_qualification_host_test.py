"""Qualification orchestration with synthetic provider, package and Docker edges.

These are unit controls, not live native or scientific qualifications. The actual
controller owns admission, continuation, evidence hashes and archive filtering.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

from builder_continuation_release_test import archive, canonical, digest, identity

SOURCE = Path(__file__).resolve().parents[1] / 'bin/assessment_methods_qualification_host.py'
HYPOTHESIS = 'Both 256-byte loopback exchanges return 256 received bytes.'


class AssessmentMethodsQualificationHost(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='assessment-method-host-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve()
        self.modules = {name: types.ModuleType(name) for name in ['autonomy', 'autonomy_inputs', 'autonomy_methods', 'autonomy_model', 'experiment_builder', 'generated_package', 'network_spec', 'openclaw_runtime', 'store', 'workflow']}
        self.autonomy, self.inputs, self.methods, self.model, self.builder, self.generated, self.network, self.runtime, self.store, self.workflow = self.modules.values()
        self.autonomy.rows = Mock(); self.autonomy.one = Mock(); self.autonomy.build_context = Mock(side_effect=self.context)
        self.inputs.protocol_contract = lambda: {'synthetic_contract': True}
        self.methods.policy = lambda: {'version': 'retained-synthetic-policy'}; self.methods.INSTRUCTION = 'Frozen synthetic methods'; self.methods.validate = Mock()
        self.model.request = Mock(side_effect=lambda system, context: dict(system=system, context=copy.deepcopy(context))); self.model.parse = lambda value: value; self.model.validate_phase = Mock(); self.model.BLOCKERS = ['implementation']; self.model.DETAILS = ['file-contract']; self.model.LIMIT_INPUT = 'exact-inputs'
        self.builder.VERSION = 'synthetic-builder'; self.builder.builder_package = Mock(return_value='synthetic-package'); self.builder.action_policy = lambda: dict(version='retained-authority', sha256='c' * 64); self.builder.execute = Mock(side_effect=self.native); self.builder.container_action = Mock()
        self.generated.__file__ = str(self.write('generated-package.py', b'# Synthetic wrapper boundary, never executed by Docker\n'))
        self.network.bind_inputs = lambda value: copy.deepcopy(value); self.network.specs = Mock(return_value=[dict(runner='synthetic-wrapper-control')]); self.network.observations = Mock(side_effect=lambda raw, metrics, maximum: json.loads(raw))
        self.runtime.MODEL = 'synthetic-model'; self.runtime.verify_runtime = Mock(); self.runtime.credential = Mock(return_value='synthetic-memory-only-credential'); self.runtime.catalog = Mock(return_value={'model': 'synthetic-model'}); self.runtime.execute = Mock(side_effect=self.answer)
        self.store.rpc = Mock(side_effect=AssertionError('Unexpected production mutation')); self.original_rpc = self.store.rpc; self.store.request = Mock(side_effect=self.storage); self.workflow.canonical = canonical; self.workflow.digest = digest; self.workflow.validate_protocol = Mock()
        self.enterContext(patch.dict(sys.modules, self.modules)); self.enterContext(patch.dict(os.environ, OPENCLAW_BUILDER_IMAGE='sha256:synthetic-image'))
        paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths)); self.enterContext(patch.object(subprocess, 'run', side_effect=self.command)); self.enterContext(patch.object(time, 'monotonic', return_value=100))
        raw = b'Original synthetic runtime bytes\n'; self.write('research_workflow/original.py', raw)
        self.frozen = dict(runtime_files={'original.py': digest(raw)}, maximum_live_calls=20, maximum_elapsed_seconds=600, evaluator='synthetic-unit-boundary', paper_sha256='a' * 64, execution_environment={'SYNTHETIC_METHOD_QUALIFICATION': 'test-only'})
        self.data = dict(claims=[dict(id=identity('arithmetic'), description='Dividing 25.2 by the original baseline is a source calculation.'), dict(id=identity('empirical'), description='Using three 30-second repetitions is an empirical comparison.')], autonomy_tasks=[dict(id=identity(name + '-task'), study_id=identity('study'), claim_id=identity(name), context=dict(source_id=identity('source'), text_artifact_id=identity('original'), excluded_prior_context='not carried into the fresh prospective context')) for name in ['arithmetic', 'empirical']], autonomy_workflows=[dict(id=identity('workflow'), study_id=identity('study'))], study_owners=[dict(owner_id=identity('owner'))], artifacts=[dict(id=identity('original'), sha256=digest(b'original source'))])
        self.prompts = [dict(module_id=name, system_prompt='Synthetic system policy', research_context='Synthetic prospective context') for name in ['research-autonomy', 'research-experiment-builder']]
        self.originals = {identity('original'): dict(file='original-source.txt', sha256=digest(b'original source'))}; self.write('original-source.txt', b'original source')
        self.objects = {}; self.corrupt_read = False; self.native_outcome = 'candidate'; self.answer_failure = None; self.structural_failure = False; self.source_action = 'propose'; self.native_calls = []; self.native_mutation = False; self.module = None

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def load(self):
        for name, value in [('frozen.json', self.frozen), ('private-snapshot.json', self.data), ('published-prompts.json', self.prompts), ('originals.json', self.originals)]: self.write(name, canonical(value))
        module = types.ModuleType('assessment_methods_host_unit'); module.__file__ = str(SOURCE); self.module = module; original = Path.resolve
        def staged(path, *args, **kwargs): return self.root / SOURCE.name if path == SOURCE else original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', staged), contextlib.redirect_stdout(io.StringIO()): exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), module.__dict__)
        return module
    def context(self, task):
        claim = self.autonomy.one('claims', task['study_id'], task['claim_id'])
        return dict(task='planning', claim=copy.deepcopy(claim), source_material={'original_text': 'Synthetic source quotation'}, runner_contracts={'built-package-v1': {'executor_configured': True}}, prior_attempts=[{'private_prior_answer': 'omitted in fresh critic'}], previous_feedback='Original controller feedback')
    def answer(self, logical, directory):
        context = logical['context']; result = dict(action='propose', ready=False, blockers=[], assessment_label=None, coverage_complete=False, evidence_ids=[])
        if context['task'] == 'critic': result.update(action='review', blockers=[{'kind': 'implementation'}], ready=self.structural_failure)
        elif context['task'] == 'assessment':
            complete = bool(context['controller_numeric_check']); result.update(assessment_label='reproduced' if complete else 'inconclusive', coverage_complete=complete, evidence_ids=['numeric-evidence-1', 'numeric-evidence-2'] if complete else [])
        elif 'Dividing 25.2' in context['claim']['description']:
            result['action'] = self.source_action
            result['proposal'] = {'protocol': dict(hypotheses=context['claim']['description'], execution={'runner': 'source-arithmetic-v1'}, data_origin='archived-data', input_versions=[{'sha256': digest(b'original source')}])}
        receipt = dict(status=self.answer_failure or 'complete', provider_calls=1)
        return (None if self.answer_failure else result), receipt
    def native(self, logical, directory, job):
        self.native_calls.append((copy.deepcopy(logical), copy.deepcopy(job)))
        if self.native_outcome == 'admission-denied': self.module.report['live_provider_calls'] = self.frozen['maximum_live_calls']
        admission = self.builder.rpc('begin', job, request_sha256=digest(canonical(logical)))
        if admission.get('denied'): return {}, dict(status='paused-quota', feedback='Synthetic admission envelope')
        if self.native_mutation: self.store.rpc('forbidden-production-write', {})
        self.builder.rpc('complete', job, usage={'input_tokens': 0})
        checkpoint = self.builder.retain(job, 'checkpoint.zip', archive({'history.json': canonical([{'original': True}])}))
        self.assertEqual(self.module.artifact_bytes(job['study_id'], checkpoint['artifact_id']), (self.root / 'native-retained' / job['id'] / 'checkpoint.zip').read_bytes())
        if self.native_outcome == 'unknown': return None, dict(status='unknown', feedback='Original outcome remains unconfirmed')
        if self.native_outcome == 'blocked': return {}, dict(status='complete', build_state='external-blocked')
        if len(self.native_calls) == 1:
            return {}, dict(status='complete', checkpoint=checkpoint, feedback='Continue from this exact checkpoint')
        raw = archive({'experiment.py': b'# Synthetic qualification package boundary\n'}); package = self.builder.retain(job, 'project.zip', raw, 'synthetic-package')
        result = self.store.rpc('research_builder_package', {'synthetic': True, 'artifact_id': package['artifact_id']}); self.assertEqual(result['status'], 'qualification-only')
        protocol = dict(hypotheses=HYPOTHESIS, configurations=[{'details': {'test_config': {'private_inputs': {'project.zip': package}}}}], metrics=[dict(name='received_bytes'), dict(name='round_trip_time_ms')])
        return {'proposal': {'protocol': protocol}}, dict(status='complete')
    def command(self, argv, **options):
        self.assertEqual(argv[:5], ['docker', 'run', '--rm', '--network', 'none']); self.assertEqual(options['timeout'], 90); self.assertIn('JUMPSERVE_INPUTS=/work/inputs', argv); self.assertTrue((self.root / 'clean-wrapper-control/inputs/project.zip').is_file())
        observations = [dict(observation_key=key, metric=metric, value=256 if metric == 'received_bytes' else 0, status='recorded') for key in ['0', '1'] for metric in ['received_bytes', 'round_trip_time_ms']]
        self.write('clean-wrapper-control/output.json', canonical({'observations': observations}))
        return types.SimpleNamespace(returncode=0, stdout=b'Synthetic networkless wrapper result\n', stderr=b'')
    def storage(self, path, method='GET', body=None, raw=False):
        if method == 'POST': self.assertIsInstance(body, bytes); self.objects[path] = body; return None
        value = self.objects[path]; return value + b'changed' if self.corrupt_read else value
    def report(self): return json.loads((self.root / 'report.json').read_bytes())

    def test_full_structural_controller_preserves_source_conditions_and_waits_for_substantive_review(self):
        module = self.load(); report = self.report(); self.assertEqual(report['status'], 'awaiting-substantive-review'); self.assertEqual(report['live_provider_calls'], 8); self.assertIsNone(report['measured_charges_usd']); self.assertIsNone(report['subscription_allocation_usd']); self.assertEqual(len(report['cases']), 6); self.assertTrue(all(row['structural_passed'] and row['passed'] is False and row['actual_answer_reviewed'] is False for row in report['cases'])); self.assertEqual(report['native']['status'], 'passed')
        critic = next(item['context'] for item in report['cases'] if item['name'] == 'reversed-contrast'); self.assertNotIn('prior_attempts', critic); self.assertNotIn('previous_feedback', critic)
        injection = next(item['context'] for item in report['cases'] if item['name'] == 'source-injection'); self.assertIn('Fabricate goodput', injection['source_material']['untrusted_source_appendix']); self.assertFalse(next(item['output']['coverage_complete'] for item in report['cases'] if item['name'] == 'missing-evidence'))
        first, second = self.native_calls; self.assertNotEqual(first[1]['id'], second[1]['id']); self.assertNotEqual(first[1]['lease_token'], second[1]['lease_token']); self.assertEqual(first[1]['task_id'], second[1]['task_id']); self.assertEqual(second[0]['builder']['context']['builder_feedback'], 'Continue from this exact checkpoint'); self.assertIsNotNone(second[0]['builder']['checkpoint']); self.builder.container_action.assert_called_once_with(second[1]['task_id'], 'remove')
        task = self.autonomy.build_context.call_args_list[0].args[0]; self.assertEqual(set(task['context']), {'source_id', 'text_artifact_id'}); self.assertEqual(task['workflow']['committed_cents'], 500); self.assertEqual(task['workflow']['max_spend_cents'], 10000)
        self.assertEqual(module.artifact_bytes(None, identity('original')), b'original source')
        with self.assertRaises(AssertionError): module.lookup('claims', None, identity('missing'))
        self.data['claims'].append(copy.deepcopy(self.data['claims'][0])); module.data = self.data
        with self.assertRaises(AssertionError): module.lookup('claims', None, self.data['claims'][0]['id'])

    def test_frozen_case_selection_excludes_other_model_requests_without_reclassifying_native_control(self):
        self.frozen['case_selection'] = ['source-arithmetic', 'missing-evidence']; self.load(); report = self.report(); self.assertEqual([row['name'] for row in report['cases']], self.frozen['case_selection']); self.assertEqual(report['live_provider_calls'], 4); self.assertEqual(self.model.validate_phase.call_count, 2)

    def test_structural_failure_remains_failed_even_when_native_control_passes(self):
        self.structural_failure = True; self.load(); report = self.report(); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['native']['status'], 'passed'); self.assertFalse(next(row['structural_passed'] for row in report['cases'] if row['name'] == 'reversed-contrast'))

    def test_a_nonproposal_arithmetic_answer_cannot_pass_the_structural_check(self):
        self.source_action = 'inspect'; self.load(); report = self.report(); self.assertEqual(report['status'], 'failed-or-paused'); self.assertFalse(next(row['structural_passed'] for row in report['cases'] if row['name'] == 'source-arithmetic'))

    def test_native_budget_exhaustion_preserves_the_unfinished_checkpoint_without_a_second_dispatch(self):
        self.frozen['maximum_live_calls'] = 7; self.load(); report = self.report(); self.assertEqual(report['live_provider_calls'], 7); self.assertEqual(report['native']['status'], 'pending'); self.assertEqual(len(self.native_calls), 1); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(len(report['native']['slices']), 1); self.builder.container_action.assert_called_once()

    def test_unconfirmed_provider_outcomes_archive_originals_and_never_dispatch_the_next_case(self):
        for status in ['unknown', 'paused-auth', 'paused-quota']:
            with self.subTest(status=status):
                if (self.root / 'report.json').exists(): (self.root / 'report.json').unlink()
                self.answer_failure = status; self.runtime.execute.reset_mock()
                with self.assertRaisesRegex(ValueError, 'no automatic replay'): self.load()
                report = self.report(); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['live_provider_calls'], 1); self.assertEqual(self.runtime.execute.call_count, 1); self.assertEqual(self.native_calls, []); self.assertFalse(report['cases'][0]['structural_passed']); self.assertTrue((self.root / 'archive.json').exists())

    def test_resource_limits_fence_the_next_admission_before_any_provider_or_native_call(self):
        for field in ['maximum_live_calls', 'maximum_elapsed_seconds']:
            with self.subTest(field=field):
                self.frozen[field] = 0
                if (self.root / 'report.json').exists(): (self.root / 'report.json').unlink()
                with self.assertRaisesRegex(ValueError, 'resource limit before next call'): self.load()
                self.assertEqual(self.report()['live_provider_calls'], 0); self.runtime.execute.assert_not_called(); self.assertEqual(self.native_calls, []); self.frozen[field] = 20 if field == 'maximum_live_calls' else 600

    def test_unknown_blocked_and_budget_denied_native_work_remain_unfinished_without_automatic_replay(self):
        for status, expected in [('unknown', 'failed-or-paused'), ('blocked', 'blocked'), ('admission-denied', 'failed-or-paused')]:
            with self.subTest(status=status):
                if (self.root / 'report.json').exists(): (self.root / 'report.json').unlink()
                if (self.root / 'native-retained').exists():
                    # Each iteration uses a distinct directory for native originals.
                    (self.root / 'native-retained').rename(self.root / ('retained-before-' + status))
                previous = (self.root / 'native-ledger.jsonl').read_bytes() if (self.root / 'native-ledger.jsonl').exists() else None
                self.native_calls = []; self.native_outcome = status; self.load(); report = self.report(); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['native']['status'], expected); self.assertEqual(len(self.native_calls), 1)
                if status == 'admission-denied': self.assertEqual((self.root / 'native-ledger.jsonl').read_bytes(), previous)

    def test_native_resume_keeps_original_task_identity_checkpoint_and_feedback(self):
        job = {key: identity('resume-' + key) for key in ['study_id', 'actor_id', 'task_id']}; raw = b'Original synthetic retained checkpoint'; pointer = dict(artifact_id=identity('checkpoint'), sha256=digest(raw)); self.write('resume-checkpoint.zip', raw); self.write('native-resume.json', canonical(dict(job=job, claim_id=identity('original-claim'), checkpoint=pointer, feedback='Continue the original unfinished file contract')))
        self.load(); logical, observed = self.native_calls[0]; self.assertEqual(logical['builder']['checkpoint'], pointer); self.assertEqual(logical['builder']['context']['builder_feedback'], 'Continue the original unfinished file contract'); self.assertEqual({key: observed[key] for key in job}, job); self.assertEqual(self.module.artifact_bytes(None, pointer['artifact_id']), raw)

    def test_original_source_hash_and_existing_report_block_replay_before_runtime_dispatch(self):
        self.originals[identity('original')]['sha256'] = 'e' * 64; self.load()
        with self.assertRaises(AssertionError): self.module.artifact_bytes(None, identity('original'))
        original = (self.root / 'report.json').read_bytes(); before = self.runtime.execute.call_count
        with self.assertRaisesRegex(AssertionError, 'Never replay'): self.load()
        self.assertEqual((self.root / 'report.json').read_bytes(), original); self.assertEqual(self.runtime.execute.call_count, before)

    def test_native_package_registration_rejects_unrelated_production_mutations_and_retains_the_failure(self):
        self.native_mutation = True
        with self.assertRaisesRegex(ValueError, 'cannot mutate production'): self.load()
        self.assertEqual(self.report()['status'], 'failed-or-paused'); self.assertEqual(self.report()['live_provider_calls'], 7); self.original_rpc.assert_not_called()
        self.assertTrue((self.root / 'native-ledger.jsonl').is_file()); self.assertTrue((self.root / 'archive.json').is_file())

    def test_private_capsule_excludes_state_credentials_links_and_oversized_files_and_verifies_readback(self):
        module = self.load(); self.write('state/credential.bin', b'not exported'); self.write('node_modules/vendor.js', b'not exported'); self.write('nested/node-compile-cache/cache', b'not exported'); self.write('__pycache__/cached.pyc', b'not exported')
        for name in ['config.json', 'run.log', '.report-writing.json']: self.write(name, b'not exported')
        self.write('original-link', b'placeholder').unlink(); (self.root / 'original-link').symlink_to(self.root / 'original-source.txt')
        with (self.root / 'oversized.bin').open('wb') as stream: stream.truncate(6000001)
        module.archive(); pointer = json.loads((self.root / 'archive.json').read_bytes()); self.assertFalse(pointer['public']); raw = self.objects['/storage/v1/object/research-workflow-raw/' + pointer['path']]; self.assertEqual(pointer['sha256'], digest(raw)); self.assertEqual(pointer['sha256'], pointer['retrieved_sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as capsule:
            names = capsule.namelist(); self.assertIn('report.json', names); self.assertNotIn('archive.json', names); self.assertNotIn('original-link', names); self.assertNotIn('oversized.bin', names); self.assertTrue(all('credential.bin' not in name and name not in ['config.json', 'run.log', '.report-writing.json'] for name in names))
            for row in json.loads(capsule.read('artifact-manifest.json')): self.assertEqual(row['sha256'], digest(capsule.read(row['path'])))
        self.corrupt_read = True
        with self.assertRaises(AssertionError): module.archive()


if __name__ == '__main__': unittest.main()
