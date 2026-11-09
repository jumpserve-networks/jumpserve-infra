"""Staged qualification orchestration with synthetic runtime/service adapters.

No native worker, Docker container or provider runs. Source hashes, checkpoint
bytes, evidence ZIPs and changed-input calculations are exercised locally; the
fixture program is a test adapter, not an actual model qualification.
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
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

from builder_continuation_release_test import archive, canonical, digest, identity

SOURCE = Path(__file__).resolve().parents[1] / 'bin/builder_continuation_qualification_host.py'
CALCULATION = '''import json
from pathlib import Path
p=Path('.')
c=json.loads((p/'research-context.json').read_bytes())['required_source_packet']['source_cells']
b=float(c['baseline_mbit_s']);t=float(c['treatment_mbit_s'])
# INPUT_GUARD
answer=dict(baseline_mbit_s=b,treatment_mbit_s=t,relative_change_percent=round(100*(t-b)/b,10),missing_value=None,scope='source-consistency-only',main_campaign_executed=False,prior_failure_preserved=True)
for name in ('calculation-output.json','answer.json'):(p/name).write_text(json.dumps(answer))
'''


class ContinuationQualificationHost(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='continuation-host-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve()
        self.modules = {name: types.ModuleType(name) for name in ['autonomy', 'autonomy_methods', 'autonomy_model', 'experiment_builder', 'network_spec', 'openclaw_runtime', 'shared_campaigns', 'store', 'workflow']}
        self.autonomy, self.methods, self.model, self.builder, self.network, self.runtime, self.shared, self.store, self.workflow = self.modules.values()
        for name, values in {
            'workflow': dict(canonical=canonical, digest=digest, validate_protocol=Mock()),
            'autonomy_methods': dict(INSTRUCTION='Synthetic frozen method policy', validate=Mock()),
            'autonomy_model': dict(TURN_POLICY={'instruction': 'Synthetic retained turn policy'}, request=Mock(side_effect=lambda system, context: dict(system=system, context=copy.deepcopy(context))), parse=lambda value: value, validate_phase=Mock()),
            'network_spec': dict(bind_inputs=lambda value: copy.deepcopy(value)),
            'experiment_builder': dict(MODULE='research-experiment-builder', VERSION='synthetic-builder-version', action_policy=lambda: dict(version='synthetic-authority', sha256='c' * 64, document={'instruction': 'Retain the frozen test-only authority.'}), builder_package=Mock(return_value='synthetic-package'), container_action=Mock(), retain=Mock(), rpc=Mock()),
            'openclaw_runtime': dict(MODEL='synthetic-model', PACKAGE=self.root / 'vendor/openclaw', NODE=self.root / 'vendor/node/bin/node', verify_runtime=Mock(), credential=Mock(return_value='synthetic-memory-only-credential'), catalog=Mock()),
            'shared_campaigns': dict(identity=Mock(return_value=('synthetic-acquisition', 'd' * 64))),
        }.items(): self.modules[name].__dict__.update(values)
        for path in [self.runtime.PACKAGE, self.runtime.NODE.parent]: path.mkdir(parents=True)
        self.write('research_workflow/controller.py', b'# Original synthetic staged runtime\n')
        self.packet = dict(source_files={'research_workflow/controller.py': digest(b'# Original synthetic staged runtime\n')}, prompts=[dict(module_id=name, id=identity(name), version='retained-v1', system_prompt='Synthetic trusted policy', research_context='Synthetic prospective context', content_sha256=digest(b'Synthetic trusted policy\n\nSynthetic prospective context')) for name in ['research-autonomy', 'research-experiment-builder']], assessment=identity('source-assessment'), protocol={'resources': dict(maximum_native_case_calls=3, maximum_real_provider_calls=5, maximum_elapsed_seconds=300)}, native_context={'required_source_packet': {'source_cells': {'baseline_mbit_s': '72.0', 'treatment_mbit_s': '97.2'}}}, planning_context=dict(claim=dict(source_id=identity('source'), description='Frozen synthetic hypothesis'), reusable_protocol={'input_versions': [{'sha256': 'a' * 64}]}), expected_acquisition_sha256='d' * 64)
        self.write('frozen.json', canonical(self.packet)); self.write('prepared.json', canonical({'image': 'sha256:synthetic-test-image'})); self.objects = {}; self.store.request = Mock(side_effect=self.request); self.store.rows = Mock(); self.store.artifact = Mock(); self.store.append = Mock()
        self.store.artifact_bytes = Mock()
        self.containers = set(); self.native_calls = 0; self.native_stop = None; self.planner_missing = False; self.store_conflict = False; self.corrupt_read = False; self.actual_run = subprocess.run
        self.builder.execute = Mock(side_effect=self.execute_builder); self.builder.reap = Mock(side_effect=self.reap); self.autonomy.numeric_finding = Mock(side_effect=self.finding); self.runtime.execute = Mock(side_effect=self.planning)
        self.enterContext(patch.dict(sys.modules, self.modules)); self.enterContext(patch.dict(os.environ, SUPABASE_URL='https://regphejnlvfpyokpniny.supabase.co')); self.enterContext(patch.object(subprocess, 'run', side_effect=self.command)); self.enterContext(patch.object(os, 'getuid', return_value=501)); paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths))
        self.module = self.load('continuation_host_unit')
        self.planning_output = dict(action='propose', proposal={'protocol': dict(hypotheses=self.packet['planning_context']['claim']['description'], input_versions=[{'sha256': 'a' * 64}])}, coverage_complete=False, assessment_label=None)

    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def load(self, name):
        # Keep the source's real __file__ for coverage attribution, while the
        # one staged-root lookup resolves to this unit's isolated file tree.
        module = types.ModuleType(name); module.__file__ = str(SOURCE); original_resolve = Path.resolve
        def staged(path, *args, **options): return self.root / SOURCE.name if path == SOURCE else original_resolve(path, *args, **options)
        with patch.object(Path, 'resolve', staged): exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), module.__dict__)
        return module
    def request(self, path, method='GET', body=None, public=False, raw=False):
        if method == 'POST':
            self.assertIsInstance(body, bytes); self.assertTrue(path not in self.objects or self.objects[path] == body); self.objects[path] = body
            if self.store_conflict: raise OSError('Synthetic uncertain upload acknowledgement')
            return None
        value = self.objects[path]
        if self.corrupt_read: value += b'changed'
        return value if raw else json.loads(value)
    def command(self, command, **options):
        if command[0] == '/opt/jumpserve/python/bin/python':
            self.write('.test-artifacts/builder-image/continuation-v1.json', canonical(dict(status='passed', platform='linux/amd64', image='sha256:synthetic-test-image', package_inventory_sha256='e' * 64)))
            return types.SimpleNamespace(returncode=0, stdout=b'Synthetic image inventory output\n', stderr=b'')
        self.assertEqual(command[0], 'docker')
        if command[1] == 'create': self.assertIn('--read-only', command); self.assertIn('none', command); self.containers.add(command[command.index('--name') + 1]); return types.SimpleNamespace(returncode=0)
        if command[1] == 'inspect': return types.SimpleNamespace(returncode=0 if command[2] in self.containers else 1)
        self.assertEqual(command[1], 'run'); self.assertIn('--read-only', command); self.assertIn('none', command); self.assertIn('--rm', command)
        mount = command[command.index('--mount') + 1]; control = Path(mount.split('src=')[1].split(',dst=')[0]); self.assertEqual(control.parent, self.root)
        return self.actual_run([sys.executable, str(control / 'calculation.py')], cwd=control, capture_output=True, timeout=10)
    def execute_builder(self, logical, directory, job):
        self.native_calls += 1; admitted = self.builder.rpc('begin', job, request_sha256=digest(canonical(logical))); self.assertIn('id', admitted)
        checkpoint_raw = archive({'original-context.json': canonical({'zero': 0, 'missing': None})}); checkpoint = self.builder.retain(job, 'checkpoint.zip', checkpoint_raw)
        self.assertEqual(self.store.artifact_bytes(job['study_id'], checkpoint['artifact_id']), checkpoint_raw); self.builder.rpc('complete', job, observed_usage={'tokens': 0})
        if self.native_calls == 1 and not self.native_stop: return None, dict(status='complete', provider_calls=1, checkpoint=checkpoint, feedback='Synthetic continuation boundary')
        if self.native_stop: return None, dict(status=self.native_stop, error_code='original-unknown-provider-outcome', provider_calls=1, checkpoint=checkpoint)
        workspace = self.root / 'builder-workspaces' / job['task_id'] / 'workspace'; self.populate_program(workspace)
        return None, dict(status='complete', provider_calls=1, checkpoint=checkpoint)
    def populate_program(self, workspace, inherited=False):
        workspace.mkdir(parents=True, exist_ok=True); program = CALCULATION.replace('# INPUT_GUARD', 'assert b==72 and t==97.2' if inherited else '# Prospective changed-input software control')
        (workspace / 'calculation.py').write_text(program); (workspace / 'research-context.json').write_bytes(canonical({'required_source_packet': self.packet['native_context']['required_source_packet']})); (workspace / 'native-tool-history.json').write_bytes(canonical([dict(type='function_call', name='exec', arguments=json.dumps({'command': 'python3 calculation.py'})), dict(type='other-original-record')]))
        result = self.actual_run([sys.executable, str(workspace / 'calculation.py')], cwd=workspace, capture_output=True, timeout=10); self.assertEqual(result.returncode, 0, result.stderr.decode())
    def planning(self, logical, directory): return (None, dict(status='unknown', provider_calls=1)) if self.planner_missing else (copy.deepcopy(self.planning_output), dict(status='complete', provider_calls=1))
    def finding(self, task):
        self.store.request('/original-input', raw=True)
        if task['id'] == 'invalid': raise ValueError('Original method gap retained')
        if task['id'] == 'write-attempt': self.store.request('/forbidden', 'POST', b'forbidden')
        return None if task['id'] == 'missing' else ('reproduced', [], {'synthetic_only': True})
    def reap(self, root):
        # Synthetic builder adapter: only this fixture's containers/receipts.
        for name in list(self.containers):
            task = next((root / 'builder-workspaces').iterdir()); pending = task / 'retirement-pending.json'; original = (task / 'retired.json').read_bytes(); history = task / 'retirement-history'; history.mkdir(exist_ok=True); (history / (digest(original) + '.json')).write_bytes(original)
            self.store.rows('autonomy_tasks'); self.store.rows('autonomy_workflows'); self.store.rows('study_owners'); self.store.artifact('study', 'owner', canonical({'original_retirement': name}), identity(name + str(self.store.artifact.call_count)))
            if pending.exists(): pending.unlink()
            self.containers.remove(name)

    def test_atomic_receipts_and_private_put_verify_downloaded_original_even_after_an_uncertain_upload(self):
        path = self.root / 'receipt.json'; self.module.save(path, {'zero': 0, 'missing': None}); self.assertEqual(json.loads(path.read_bytes()), {'zero': 0, 'missing': None}); self.assertFalse(path.with_suffix('.writing').exists())
        raw = b'Original retained bytes\n'; item = self.module.put('original.bin', raw); self.assertEqual(item['sha256'], item['retrieved_sha256']); self.assertFalse(item['public']); self.assertEqual(item['bytes'], len(raw))
        self.store_conflict = True; self.assertEqual(self.module.put('original.bin', raw)['sha256'], digest(raw)); self.corrupt_read = True
        with self.assertRaises(OSError): self.module.put('original.bin', raw)

    def test_image_preparation_preserves_stdout_package_hash_and_existing_exact_runtime_links(self):
        self.module.prepare(); result = json.loads((self.root / 'prepared.json').read_bytes()); self.assertEqual(result['status'], 'passed'); self.assertEqual(result['package_inventory_sha256'], 'e' * 64); self.assertIsNone(result['measured_charges_usd']); self.assertEqual((self.root / 'prepare-stdout.bin').read_bytes(), b'Synthetic image inventory output\n')
        self.module.prepare(); selected = json.loads((self.root / '.test-artifacts/builder-image/published-prompt-v2.json').read_bytes()); self.assertEqual(selected['module_id'], 'research-experiment-builder')
        link = self.root / 'experiments/openclaw_pilot/runtime/node_modules/openclaw'; link.unlink(); link.symlink_to(self.runtime.NODE.parents[1], target_is_directory=True)
        with self.assertRaises(AssertionError): self.module.prepare()

    def test_native_control_executes_only_the_staged_test_and_retires_repeated_synthetic_containers_with_unique_receipts(self):
        code = "from pathlib import Path\nimport json\ndef main():\n p=Path(__file__).resolve().parents[2]/'.test-artifacts/experiment-builder/run/report.json'\n p.parent.mkdir(parents=True,exist_ok=True)\n p.write_text(json.dumps(dict(status='passed',live_provider_calls=0,slots=3)))\n"
        self.write('research_workflow/tests/check_experiment_builder_linux.py', code.encode()); self.module.packet['amendment'] = {'synthetic': True}; self.module.native(); report = json.loads((self.root / 'native.json').read_bytes()); self.assertEqual(report['report']['live_provider_calls'], 0); self.assertEqual(report['repeated_retirement_control']['real_container_retirements'], 2); self.assertTrue(report['repeated_retirement_control']['original_preserved']); self.assertEqual(self.containers, set()); self.builder.container_action.assert_called_once()
        with self.assertRaisesRegex(AssertionError, 'Never replay'): self.module.native()

    def test_read_only_replay_retains_every_original_read_and_reports_missing_methods_without_writing_assessments(self):
        tasks = [dict(id=name, claim_id=identity(name), context={'proposal': {'protocol': {'decision': {'version': 'synthetic'}}}}) for name in ['complete', 'missing', 'invalid', 'write-attempt']] + [dict(id='intake', claim_id=None), dict(id='legacy', claim_id='original-claim', context={})]
        self.objects['/tasks'] = canonical(tasks); self.objects['/original-input'] = canonical({'missing': None, 'zero': 0}); self.store.rows.side_effect = lambda *args, **kwargs: self.store.request('/tasks')
        self.module.replay(); result = json.loads((self.root / 'replay.json').read_bytes()); self.assertEqual(result['production_writes'], 0); self.assertEqual([item['status'] for item in result['results']], ['computed-read-only', 'no-complete-decision', 'method-or-integrity-gap', 'method-or-integrity-gap']); self.assertTrue(all(not item['scientific_assessment_written'] for item in result['results']))
        for row in result['reads']: raw = (self.root / 'replay-originals' / row['file']).read_bytes(); self.assertEqual(row['sha256'], digest(raw)); self.assertEqual(row['bytes'], len(raw))
        self.assertFalse(any(call.args[1:2] == ('POST',) for call in self.store.request.call_args_list))
        with self.assertRaisesRegex(AssertionError, 'Retain the previous'): self.module.replay()

    def test_live_orchestration_retains_checkpoints_uses_changed_input_controls_and_never_claims_independent_scientific_completion(self):
        self.module.live(); report = json.loads((self.root / 'live.json').read_bytes()); self.assertEqual(report['status'], 'awaiting-substantive-review'); self.assertEqual(report['admissions'], 3); self.assertEqual(report['live_provider_calls_issued'], 3); self.assertEqual(report['reserved_cents'], 300); self.assertEqual(len(report['cases']), 2); self.assertFalse(report['reviewer']['independent']); self.assertIsNone(report['measured_charges_usd']); self.assertTrue(all(not case['actual_answer_reviewed'] for case in report['cases']))
        native, planner = report['cases']; self.assertEqual(native['changed_input_control']['output']['relative_change_percent'], 25); self.assertEqual(native['answer']['relative_change_percent'], 35); self.assertIsNone(native['answer']['missing_value']); self.assertEqual(planner['output'], self.planning_output)
        for job, name in [(path.parent.name, path.name) for path in (self.root / 'live-originals').glob('*/*.zip')]: self.assertEqual((self.root / 'live-originals' / job / name).read_bytes()[:2], b'PK')
        ledger = [json.loads(line) for line in (self.root / 'live-ledger.jsonl').read_bytes().splitlines()]; self.assertEqual([item['operation'] for item in ledger], ['begin', 'complete', 'begin', 'complete']); self.builder.container_action.assert_called_once()
        with self.assertRaisesRegex(AssertionError, 'Never replay'): self.module.live()

    def test_unknown_native_outcomes_are_retained_and_cleaned_up_without_replacement_planning(self):
        self.native_stop = 'unknown'
        with self.assertRaisesRegex(ValueError, 'needs reconciliation'): self.module.live()
        report = json.loads((self.root / 'live.json').read_bytes()); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['live_provider_calls_issued'], 1); self.assertEqual(report['admissions'], 1); self.assertIn('original-unknown-provider-outcome', report['failure']); self.runtime.execute.assert_not_called(); self.builder.container_action.assert_called_once()

    def test_inherited_program_is_not_reexecuted_as_a_native_call_and_changed_source_inputs_are_rejected_with_original_failure_preserved(self):
        raw = archive({'fixture.txt': b'Original inherited checkpoint\n'}); self.write('inherited-native-checkpoint.zip', raw); self.module.packet['inherited_native'] = dict(checkpoint_sha256=digest(raw)); self.builder.restore = Mock(side_effect=lambda original, workspace: self.populate_program(workspace, inherited=True))
        self.module.live()
        report = json.loads((self.root / 'live.json').read_bytes()); native = report['cases'][0]; self.assertEqual(native['changed_input_control']['kind'], 'original-input-positive-and-altered-input-integrity-rejection'); self.assertTrue(native['changed_input_control']['original_failed_control_preserved']); self.assertEqual(report['admissions'], 1); self.builder.execute.assert_not_called(); self.assertTrue((self.root / 'changed-input-control/original-output.json').exists()); self.assertFalse((self.root / 'changed-input-control/answer.json').exists())

    def test_unknown_planner_outcome_is_retained_as_a_failed_development_check(self):
        self.planner_missing = True
        with self.assertRaisesRegex(ValueError, 'Planner outcome needs reconciliation'): self.module.live()
        report = json.loads((self.root / 'live.json').read_bytes()); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['live_provider_calls_issued'], 3); self.assertEqual(len(report['cases']), 1); self.builder.container_action.assert_called_once()

    def test_planning_cannot_invent_an_input_hash_or_change_the_frozen_acquisition_after_native_work(self):
        self.planning_output['proposal']['protocol']['input_versions'][0]['sha256'] = 'f' * 64
        with self.assertRaisesRegex(AssertionError, 'invented an input hash'): self.module.live()
        report = json.loads((self.root / 'live.json').read_bytes()); self.assertEqual(report['status'], 'failed-or-paused'); self.assertEqual(report['live_provider_calls_issued'], 3); self.assertEqual(len(report['cases']), 1); self.builder.container_action.assert_called_once()

    def test_native_admission_limit_denies_extra_slots_before_any_replacement_planner_call(self):
        self.module.packet['protocol']['resources']['maximum_native_case_calls'] = 1
        def execute(logical, directory, job):
            self.assertIn('id', self.builder.rpc('begin', job)); self.assertEqual(self.builder.rpc('begin', job), {'denied': 'qualification-budget'})
            return None, dict(status='unknown', provider_calls=0, error_code='synthetic-outcome-unconfirmed')
        self.builder.execute.side_effect = execute
        with self.assertRaisesRegex(ValueError, 'needs reconciliation'): self.module.live()
        report = json.loads((self.root / 'live.json').read_bytes()); self.assertEqual(report['admissions'], 1); self.assertEqual(report['live_provider_calls_issued'], 0); self.runtime.execute.assert_not_called()

    def test_evidence_capsule_includes_originals_and_hash_manifest_but_excludes_state_config_links_and_vendor_code(self):
        keep = {'original.bin': b'Original private bytes\n', 'task.txt': b'Synthetic fixed task\n', 'nested/result.json': canonical({'zero': 0, 'missing': None})}
        for name, raw in keep.items(): self.write(name, raw)
        for name in ['state/auth.json', 'config.json', 'evidence.json', 'node_modules/package.json', 'builder-vendor/package.json', 'experiments/retained.log', 'excluded.png']: self.write(name, b'Excluded synthetic fixture\n')
        self.write('oversize.log', b'x' * 5000001); (self.root / 'linked.bin').symlink_to(self.root / 'original.bin')
        with contextlib.redirect_stdout(io.StringIO()) as stdout: self.module.evidence()
        result = json.loads(stdout.getvalue()); self.assertEqual(result['status'], 'retained'); pointer = result['archive']; self.assertFalse(pointer['public']); raw = self.objects['/storage/v1/object/research-workflow-raw/' + pointer['path']]
        with zipfile.ZipFile(io.BytesIO(raw)) as retained:
            members = retained.namelist(); self.assertTrue(all(name in members for name in keep)); self.assertFalse(any(name in members for name in ['config.json', 'evidence.json', 'linked.bin', 'oversize.log', 'excluded.png'])); self.assertFalse(any(name.startswith(('state/', 'node_modules/', 'builder-vendor/', 'experiments/')) for name in members))
            for item in json.loads(retained.read('artifact-manifest.json')): content = retained.read(item['path']); self.assertEqual(item['sha256'], digest(content)); self.assertEqual(item['bytes'], len(content))

    def test_entrypoint_records_failed_original_stage_and_rejects_unlisted_actions_without_dispatching_tools(self):
        self.write('prepared.json', canonical({'image': 'synthetic'})); self.native_stop = 'unknown'
        with patch.object(sys, 'argv', [str(SOURCE), 'live']), self.assertRaisesRegex(ValueError, 'needs reconciliation'):
            self.load('__main__')
        self.assertEqual(json.loads((self.root / 'live-failure.json').read_bytes())['status'], 'failed'); self.assertEqual(json.loads((self.root / 'live.json').read_bytes())['status'], 'failed-or-paused')
        before = self.builder.execute.call_count
        with patch.object(sys, 'argv', [str(SOURCE), 'unlisted']), self.assertRaises(AssertionError): self.load('__main__')
        self.assertEqual(self.builder.execute.call_count, before)


if __name__ == '__main__': unittest.main()
