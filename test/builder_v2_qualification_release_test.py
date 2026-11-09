"""Builder qualification controller with offline originals and service adapters.

No SSM command, SQL engine, model, Docker process or deployment is invoked.
The actual controller freezes source bytes, generates scoped commands, and
validates retained archives and evaluation readbacks.
"""
import base64
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

from builder_continuation_release_test import archive, canonical, digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bin/qualify-experiment-builder.py'
WHEEL = 'six-1.17.0-py2.py3-none-any.whl'


class BuilderV2QualificationRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='builder-v2-qualification-unit-'); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name) / 'infra'; self.back = self.root.parent / 'backend'; self.base = self.root / '.test-artifacts/builder-qualification-v2'; self.source = self.base / '20261107T000000Z'; self.source.mkdir(parents=True); (self.base / 'selected.txt').write_text(self.source.name + '\n')
        self.r = types.ModuleType('synthetic_builder_release'); self.r.sha = digest; self.r.stamp = lambda: '2026-11-07T00:00:00Z'; self.r.target = Mock(return_value={'synthetic_target': True}); self.r.ssm = Mock(return_value=dict(command_id='original-command-id', instance_id='i-synthetic')); self.r.aws = Mock(side_effect=self.aws); self.r.subprocess = types.SimpleNamespace(check_output=Mock(return_value='a' * 40 + '\n')); self.r.admin = types.SimpleNamespace(query=Mock(side_effect=self.query), literal=lambda value: "'" + value.replace("'", "''") + "'"); self.r.prior = types.SimpleNamespace(guard=types.SimpleNamespace(OPEN=types.SimpleNamespace(open=Mock(side_effect=self.open))))
        self.objects = {}; self.evaluations = {}; self.corrupt_download = False; self.corrupt_evaluation = False; self.invocation = dict(Status='Success', StandardOutputContent='{}'); self.last = None
        self.model = types.ModuleType('autonomy_model'); self.model.BLOCKERS = ['implementation']; self.model.DETAILS = ['file-contract']; self.model.LIMIT_INPUT = 'exact-original-input'; self.builder = types.ModuleType('experiment_builder'); self.builder.canonical = canonical; self.builder.execution_contract = lambda: {'synthetic_contract': True}
        self.enterContext(patch.dict(sys.modules, {'autonomy_model': self.model, 'experiment_builder': self.builder})); paths = sys.path[:]; self.addCleanup(lambda: sys.path.__setitem__(slice(None), paths))
        self.release = self.load(); self.release.ROOT = self.root; self.release.BACK = self.back; self.release.BASE = self.base
        self.migration = b'-- Synthetic unpublished candidate prompt migration; never executed\n'; self.prompt = dict(id=self.release.PROMPT, version='synthetic-v2', system_prompt='Frozen synthetic system', research_context='Prospective synthetic context', content_sha256=digest(b'Synthetic prompt'), published_at=None)
        self.write('database/202610270006_experiment_builder_prompt_v2.sql', self.migration); self.write('docs/experiment-builder-live-amendment-v6.json', canonical({'version': 'synthetic-frozen-v6'})); self.write('docs/experiment-builder-live-amendment-v7.json', canonical({'version': 'synthetic-frozen-v7'})); self.write('research-workflow-runtime.json', canonical({'files': ['controller.py']}))
        cases = [dict(name='development-control', set='development'), dict(name='held-out-control', set='held-out')]
        for version in [1, 2]: self.write('test/experiment-builder-live-cases-v' + str(version) + '.json', canonical(dict(version='synthetic-input-v' + str(version), cases=cases)))
        for name in ['controller.py', 'openclaw-builder-patch.json', 'experiment-builder.Dockerfile', 'tests/check_experiment_builder_linux.py', 'tests/prepare_builder_vendor.py']: self.runtime(name, ('# Synthetic original ' + name + '\n').encode())
        for name in ['experiment_builder_qualification_v2_host.py', 'experiment_builder_feedback_followup_host.py', 'retain_builder_image_host.py']: self.write('bin/' + name, b'# Synthetic staged entry point, never executed\n')
        self.save('candidate.json', dict(path='qualification/original-candidate.zip', sha256='c' * 64)); self.save('host-report.json', dict(status='awaiting-review', live_provider_calls=3, started_at='2026-11-07T00:00:00Z')); self.save('archive.json', dict(path='qualification/original-archive.zip', sha256='d' * 64))

    def load(self, name='builder_v2_qualification_unit'):
        original = importlib.util.spec_from_file_location; release = self.r
        class SyntheticReleaseLoader:
            def create_module(self, spec): return release
            def exec_module(self, module): return None
        def specification(label, location, *args, **kwargs):
            if Path(location) == ROOT / 'bin/openclaw-release.py': return importlib.machinery.ModuleSpec(label, SyntheticReleaseLoader())
            return original(label, location, *args, **kwargs)
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=specification):
            spec = original(name, SOURCE); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def write(self, name, raw):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def runtime(self, name, raw):
        path = self.back / 'research_workflow' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); return path
    def save(self, name, value):
        path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(value)); return path
    def query(self, sql, **options):
        if sql.encode() == self.migration: self.assertEqual(options, {'read_only': False}); return []
        self.assertIn("where id='" + self.release.PROMPT + "'", sql); return [copy.deepcopy(self.prompt)]
    def aws(self, service, operation, *args):
        if (service, operation) == ('secretsmanager', 'get-secret-value'): self.assertEqual(args, ('--secret-id', 'jumpserve/supabase-service-key')); return {'SecretString': 'synthetic-memory-only-key'}
        self.assertEqual((service, operation), ('ssm', 'get-command-invocation')); self.assertEqual(args, ('--command-id', 'original-command-id', '--instance-id', 'i-synthetic')); return copy.deepcopy(self.invocation)
    def open(self, request, timeout):
        self.assertEqual(timeout, 60); self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-memory-only-key'); url = request.full_url; method = request.get_method(); storage = 'https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'
        if url.startswith(storage):
            key = url[len(storage):]
            if method == 'POST': self.assertTrue(key not in self.objects or self.objects[key] == request.data); self.objects[key] = request.data; return io.BytesIO(b'{}')
            value = self.objects[key]; return io.BytesIO(value + b'changed' if self.corrupt_download else value)
        self.assertTrue(url.startswith('https://regphejnlvfpyokpniny.supabase.co/rest/v1/agent_prompt_evaluations?'))
        if method == 'POST':
            item = json.loads(request.data); self.assertEqual(request.get_header('Prefer'), 'resolution=ignore-duplicates,return=minimal'); self.assertEqual(digest(item['report_raw'].encode()), item['report_sha256']); self.evaluations[item['report_sha256']] = item; return io.BytesIO(b'[]')
        sha = url.split('report_sha256=eq.')[1].split('&')[0]; raw = self.evaluations[sha]['report_raw']; return io.BytesIO(canonical([dict(report_raw=raw + ('changed' if self.corrupt_evaluation else ''))]))
    def call(self, mode):
        try:
            with patch.object(sys, 'argv', [str(SOURCE), mode]), contextlib.redirect_stdout(io.StringIO()) as output: self.release.main()
            return json.loads(output.getvalue())
        finally:
            receipts = list(self.base.glob('audit-*/receipt.json'))
            if receipts: self.last = json.loads(max(receipts, key=lambda path: path.stat().st_mtime_ns).read_bytes())
    def evidence(self, suffix, files):
        values = dict(files); values['artifact-manifest.json'] = canonical([dict(path=name, sha256=digest(raw), bytes=len(raw)) for name, raw in sorted(files.items())]); raw = archive(values); path = 'qualification/experiment-builder-v2/' + self.source.name + '/' + suffix + '/' + digest(raw) + '.zip'; self.objects[path] = raw; return dict(path=path, sha256=digest(raw), retrieved_sha256=digest(raw), bytes=len(raw)), raw
    def receipt(self, mode, value):
        self.save(mode + '-command.json', dict(command_id='original-command-id', instance_id='i-synthetic')); self.invocation = dict(Status='Success', StandardOutputContent=json.dumps(value))
    def retention_inputs(self):
        for name in ['experiment-builder-qualification-v2.md', 'experiment-builder-live-evaluation-v1.json', 'experiment-action-policy-live-amendment-v1.json', 'experiment-builder-portability-check-v2.json', 'experiment-builder-cost-review-v2.json', 'experiment-builder-actual-answer-review-v2-initial.json']: self.write('docs/' + name, b'Synthetic reviewed original\n')
        for name in ['compute.json', 'storage.json', 'egress.json', 'ipv4.json', 'ipv4-family.json', 'vpc-region.json', 'review.json']: self.write('.test-artifacts/builder-cost-review/' + name, canonical({'zero': 0, 'missing': None}))
        for name in ['database/202610270007_experiment_builder_v2_publication.sql', 'bin/qualify-experiment-builder.py', 'bin/review-builder-v2-evidence.py', 'bin/check-builder-v2-project.py', 'bin/prepare-experiment-builder-host.sh', 'bin/experiment-builder-release.py', 'bin/openclaw-release.py']: self.write(name, b'# Synthetic preserved release source\n')
        self.runtime('autonomy_costs.py', b'# Synthetic original cost logic\n'); self.runtime('policies/built-package-costs-v2.json', b'{}')
        for name in ['builder-v2-infra-tests-all.log', 'builder-v2-cli-contracts.log', 'builder-v2-autonomy-database.log']: self.write('.test-artifacts/' + name, b'Synthetic local test outcome\n')
        path = self.back / '.test-artifacts/builder-v2-backend-tests-final-v2.log'; path.parent.mkdir(parents=True); path.write_bytes(b'Synthetic backend test outcome\n')
        for stamp, leaf in [('20261027T224024286483Z', 'report.json'), ('20261027T224441360007Z', 'autonomy-validation-report.json')]:
            prefix = '.test-artifacts/research-ideas/database/' + stamp + '/'
            for name in [leaf, 'raw-original.json', 'database-fixture-snapshot.json', 'ignored-private.json']: self.write(prefix + name, canonical({'synthetic': name}))
            (self.root / prefix / 'directory').mkdir()
        for stamp in ['20261027T225907968869Z', '20261027T230543767200Z']: self.write('.test-artifacts/builder-v2-portability/' + stamp + '/nested/output.json', b'{}')
        for stamp in ['20261027T215002415721Z', '20261027T215141225797Z']:
            path = self.back / '.test-artifacts/experiment-builder' / stamp / 'report.json'; path.parent.mkdir(parents=True); path.write_bytes(b'{}')
        for name in ['followup-archive.json', 'supplement-archive.json', 'image-archive.json', 'image-manifest.json', 'followup-frozen.json', 'metadata-correction.json']: self.save(name, {'synthetic_pointer': True})
        wheel = (ROOT / 'test/fixtures' / WHEEL).read_bytes(); provenance = json.loads((ROOT / 'test/fixtures/six-1.17.0.provenance.json').read_bytes()); self.assertEqual(digest(wheel), provenance['sha256']); self.assertEqual(len(wheel), provenance['bytes']); (self.source / WHEEL).write_bytes(wheel)

    def test_campaign_selection_rejects_path_syntax_before_any_remote_command(self):
        self.assertEqual(self.release.selected(), self.source)
        for value in ['../outside', 'campaign/child', 'campaign-name', '']:
            with self.subTest(value=value):
                (self.base / 'selected.txt').write_text(value)
                with self.assertRaises(AssertionError): self.call('status')
                self.assertEqual(self.last['status'], 'failed')
        self.r.ssm.assert_not_called()

    def test_freeze_binds_unpublished_prompt_unchanged_held_out_cases_and_exact_source_bytes(self):
        (self.base / 'selected.txt').unlink(); result = self.call('freeze'); source = self.release.selected(); self.assertEqual(result['status'], 'complete'); self.assertNotEqual(source, self.source); frozen = json.loads((source / 'frozen.json').read_bytes()); self.assertEqual(frozen['prompt_id'], self.release.PROMPT); self.assertEqual(frozen['runtime_files']['controller.py'], digest((self.back / 'research_workflow/controller.py').read_bytes())); self.assertEqual(frozen['execution_contract_sha256'], digest(canonical(self.builder.execution_contract()))); self.assertTrue(frozen['source_dirty'])
        raw = (source / 'candidate.zip').read_bytes(); pointer = json.loads((source / 'candidate.json').read_bytes()); self.assertEqual(self.objects[pointer['path']], raw); self.assertEqual(result['candidate_sha256'], digest(raw))
        with zipfile.ZipFile(io.BytesIO(raw)) as capsule:
            for member in json.loads(capsule.read('candidate-manifest.json')): self.assertEqual(digest(capsule.read(member['path'])), member['sha256']); self.assertEqual(len(capsule.read(member['path'])), member['bytes'])
        self.r.ssm.assert_not_called(); self.r.admin.query.assert_any_call(self.migration.decode(), read_only=False)
        before = self.r.admin.query.call_count
        with self.assertRaisesRegex(AssertionError, 'already frozen'): self.call('freeze')
        self.assertEqual(self.r.admin.query.call_count, before)

    def test_a_changed_held_out_case_or_published_prompt_cannot_be_frozen(self):
        (self.base / 'selected.txt').unlink(); self.prompt['published_at'] = 'already-published'
        with self.assertRaises(AssertionError): self.call('freeze')
        self.prompt['published_at'] = None; self.write('test/experiment-builder-live-cases-v2.json', canonical(dict(version='changed', cases=[dict(name='substituted', set='held-out')])));
        with self.assertRaises(AssertionError): self.call('freeze')
        self.assertFalse((self.base / 'selected.txt').exists()); self.assertEqual(self.objects, {}); self.r.ssm.assert_not_called()

    def test_preparation_smoke_start_and_controls_are_scoped_commands_with_durable_replay_guards(self):
        for mode in ['prepare', 'smoke', 'start', 'control', 'retain-image', 'followup']:
            with self.subTest(mode=mode):
                result = self.call(mode); self.assertEqual(result['status'], 'complete'); commands = self.r.ssm.call_args.args[0]; joined = '\n'.join(commands); self.assertIn('/var/lib/jumpserve-openclaw/builder-qualification-v2/' + self.source.name, joined); self.assertNotIn('systemctl restart', joined); self.assertEqual(json.loads((self.source / (mode + '-command.json')).read_bytes()), result['ssm'])
                if mode == 'prepare': self.assertIn('--platform linux/amd64', joined); self.assertIn('BASE_IMAGE=ubuntu@sha256:', joined); program = shlex.split(commands[4])[-1]; compile(program, '<inspection-only>', 'exec'); self.assertIn("'..' not in name.parts", program); self.assertIn('exist_ok=False', program)
                if mode == 'start': self.assertIn('RuntimeMaxSec=3700', joined); self.assertIn("['status']=='passed'", shlex.split(commands[1])[-1])
                if mode == 'followup': self.assertIn('RuntimeMaxSec=1900', joined); packet = json.loads((self.source / 'followup-frozen.json').read_bytes()); self.assertEqual(packet['original_calls'], 3); self.assertEqual(packet['original_report_sha256'], digest((self.source / 'host-report.json').read_bytes()))
                if mode == 'retain-image': self.assertIn(base64.b64encode((self.root / 'bin/retain_builder_image_host.py').read_bytes()).decode(), joined)
                before = self.r.ssm.call_count
                with self.assertRaises(AssertionError): self.call(mode)
                self.assertEqual(self.r.ssm.call_count, before); self.assertEqual(self.last['status'], 'failed')

    def test_followup_requires_terminal_original_evidence_before_dispatch(self):
        self.save('host-report.json', dict(status='running'))
        with self.assertRaises(AssertionError): self.call('followup')
        self.r.ssm.assert_not_called(); self.assertFalse((self.source / 'followup-frozen.json').exists())

    def test_read_only_status_retains_each_original_invocation_and_bounded_public_tails(self):
        for mode in ['prepare', 'start', 'retain-image']: self.save(mode + '-command.json', dict(command_id='original-command-id', instance_id='i-synthetic'))
        self.invocation = dict(Status='Pending', StandardOutputContent='o' * 2500, StandardErrorContent='e' * 2000); result = self.call('status'); self.assertEqual(set(result) & {'prepare', 'smoke', 'start', 'control', 'evidence', 'retain-image'}, {'prepare', 'start', 'retain-image'}); self.assertEqual(len(result['prepare']['stdout']), 2000); self.assertEqual(len(result['prepare']['stderr']), 1500); self.assertEqual(json.loads((self.source / 'prepare-result.json').read_bytes()), self.invocation)
        result = self.call('followup-status'); self.assertEqual(result['status'], 'complete'); self.assertIn('/followup-v7', '\n'.join(self.r.ssm.call_args.args[0]))

    def test_snapshot_and_supplement_commands_preserve_scope_filters_and_hash_bindings(self):
        for mode in ['snapshot', 'evidence']:
            self.call(mode); program = shlex.split(self.r.ssm.call_args.args[0][-1])[-1]; compile(program, '<inspection-only>', 'exec'); self.assertIn('artifact-manifest.json', program); self.assertIn('store.request(url,raw=True)==raw', program)
            if mode == 'snapshot': self.assertIn("c['status']=='awaiting-review'", program); self.assertIn('is_relative_to', program)
            else: self.assertIn("'state' in p.relative_to(root).parts", program); self.assertIn("p.name=='config.json'", program); self.assertIn('patch[\'corrected_sha256\']', program)

    def test_collect_records_progress_without_inventing_a_terminal_archive(self):
        self.receipt('status', dict(report=dict(status='running', cases=[dict(name='original-case', status='running', provider_calls=2, private='not projected')])))
        result = self.call('collect'); self.assertEqual(result['progress'], {'status': 'running'}); self.assertEqual(result['cases'], [dict(name='original-case', status='running', provider_calls=2)]); self.assertNotIn('archive', result)
        self.receipt('status', {}); result = self.call('collect'); self.assertEqual(result['progress'], {}); self.assertEqual(result['cases'], [])

    def test_collect_verifies_both_archive_hashes_and_every_member_before_preserving_the_host_report(self):
        pointer, raw = self.evidence('originals', {'report.json': canonical({'status': 'awaiting-review'}), 'original.bin': b'Exact original transport bytes\n'}); self.receipt('status', dict(report={'status': 'awaiting-review', 'cases': []}, archive=pointer)); result = self.call('collect'); self.assertEqual(result['archive'], pointer); self.assertEqual((self.source / 'originals.zip').read_bytes(), raw); self.assertEqual(json.loads((self.source / 'host-report.json').read_bytes()), {'status': 'awaiting-review'})
        pointer['retrieved_sha256'] = 'e' * 64; self.receipt('status', dict(archive=pointer))
        with self.assertRaises(AssertionError): self.call('collect')
        self.assertEqual(self.last['status'], 'failed')

    def test_collect_rejects_failed_invocations_and_a_hash_valid_zip_with_changed_member_claims(self):
        self.receipt('status', {}); self.invocation['Status'] = 'Failed'
        with self.assertRaises(AssertionError): self.call('collect')
        raw = archive({'report.json': b'{}', 'artifact-manifest.json': canonical([dict(path='report.json', sha256='e' * 64)])}); path = 'qualification/changed-member.zip'; self.objects[path] = raw; pointer = dict(path=path, sha256=digest(raw), retrieved_sha256=digest(raw)); self.receipt('status', dict(archive=pointer))
        with self.assertRaises(AssertionError): self.call('collect')

    def test_followup_collection_requires_the_original_campaign_prefix_and_verified_report_bytes(self):
        self.receipt('followup-status', dict(report={'status': 'running'}, log_tail=None)); self.assertEqual(self.call('collect-followup')['progress'], {'status': 'running'})
        pointer, raw = self.evidence('followup-v7', {'report.json': canonical({'status': 'awaiting-review'}), 'response.bin': b'Original follow-up response'}); self.receipt('followup-status', dict(report={'status': 'awaiting-review'}, archive=pointer, log_tail='Original log tail')); result = self.call('collect-followup'); self.assertEqual(result['archive'], pointer); self.assertEqual((self.source / 'followup-originals.zip').read_bytes(), raw); self.assertEqual(json.loads((self.source / 'followup-report.json').read_bytes())['status'], 'awaiting-review')
        pointer['path'] = pointer['path'].replace(self.source.name, 'different-campaign'); self.receipt('followup-status', dict(report={}, archive=pointer))
        with self.assertRaises(AssertionError): self.call('collect-followup')

    def test_snapshot_collection_is_bound_to_its_campaign_and_original_object_hash(self):
        pointer, raw = self.evidence('snapshots', {'original.json': b'{"missing":null,"zero":0}'}); self.receipt('snapshot', pointer); result = self.call('collect-snapshot'); self.assertEqual(result['snapshot'], pointer); self.assertEqual((self.source / ('snapshot-' + pointer['sha256'] + '.zip')).read_bytes(), raw)
        pointer['path'] = 'qualification/other-campaign/snapshot.zip'; self.receipt('snapshot', pointer)
        with self.assertRaises(AssertionError): self.call('collect-snapshot')

    def test_supplement_collection_retains_a_zero_provider_negative_control_without_promoting_it_to_science(self):
        control = dict(status='passed', live_provider_calls=0, control_user='0:0', aligned_user='501:20', meaning='Expected synthetic software discrepancy, not a scientific finding'); pointer, raw = self.evidence('supplement', {'root-user-control.json': canonical(control)}); self.save('evidence-result.json', dict(Status='Success', StandardOutputContent=json.dumps(pointer))); result = self.call('collect-evidence'); self.assertEqual(result['negative_control']['meaning'], control['meaning']); self.assertEqual((self.source / 'supplement.zip').read_bytes(), raw)
        control['live_provider_calls'] = 1; pointer, _ = self.evidence('supplement', {'root-user-control.json': canonical(control)}); self.save('evidence-result.json', dict(Status='Success', StandardOutputContent=json.dumps(pointer)))
        with self.assertRaises(AssertionError): self.call('collect-evidence')

    def test_image_collection_checks_ordered_chunk_lengths_and_retains_the_original_manifest(self):
        manifest = dict(image='sha256:synthetic-image', compressed_bytes=5, chunks=[dict(bytes=2, sha256='a' * 64), dict(bytes=3, sha256='b' * 64)]); raw = canonical(manifest); pointer = dict(path='qualification/image-manifest.json', image=manifest['image'], sha256=digest(raw), retrieved_sha256=digest(raw)); self.objects[pointer['path']] = raw; self.save('retain-image-result.json', dict(Status='Success', StandardOutputContent=json.dumps(pointer))); self.assertEqual(self.call('collect-image')['image_archive'], pointer); self.assertEqual((self.source / 'image-manifest.json').read_bytes(), raw)
        pointer['image'] = 'sha256:different-image'; self.save('retain-image-result.json', dict(Status='Success', StandardOutputContent=json.dumps(pointer)))
        with self.assertRaises(AssertionError): self.call('collect-image')

    def test_evaluation_records_are_idempotent_hash_bound_and_explicitly_nonindependent(self):
        evaluation = dict(prompt_id=self.release.PROMPT, status='failed-substantive-review', turns=[{'original': True}], summary='Retain Ω, zero=0 and missing=null'); self.save('reviewed.json', evaluation); result = self.call('record'); self.assertEqual(result['evaluation_sha256'], result['retrieved_sha256']); self.assertEqual(result['retained_prompt_records'], 1); saved = next(iter(self.evaluations.values())); self.assertIn('nonindependent', saved['recorded_by']); self.assertEqual(json.loads(saved['report_raw']), evaluation); self.assertEqual(saved['original_artifacts'], json.loads((self.source / 'archive.json').read_bytes())); self.call('record'); self.assertEqual(len(self.evaluations), 1)
        self.corrupt_evaluation = True
        with self.assertRaises(AssertionError): self.call('record')

    def test_unreviewed_or_unrelated_prompt_evaluations_never_reach_the_write_boundary(self):
        for evaluation in [dict(prompt_id=self.release.PROMPT, status='running'), dict(prompt_id='unrelated', status='passed')]:
            self.save('reviewed.json', evaluation)
            with self.assertRaises(AssertionError): self.call('record')
        self.assertEqual(self.evaluations, {}); self.r.prior.guard.OPEN.open.assert_not_called()

    def test_local_validation_and_correction_archives_are_allowlisted_private_and_reused_without_uploading_again(self):
        self.retention_inputs(); (self.source / 'config.json').write_bytes(b'Synthetic excluded credential marker'); first = self.call('retain-validation')['archive']; raw = (self.source / 'local-evidence.zip').read_bytes(); self.assertEqual(digest(raw), first['sha256']); self.assertFalse(first['public'])
        with zipfile.ZipFile(io.BytesIO(raw)) as capsule:
            names = capsule.namelist(); self.assertFalse(any('ignored-private.json' in name or name.endswith('/config.json') for name in names)); self.assertEqual(capsule.read('later-independent-retrieval/' + WHEEL), (ROOT / 'test/fixtures' / WHEEL).read_bytes()); provenance = json.loads(capsule.read('later-independent-retrieval/provenance.json')); self.assertIsNone(provenance['exact_retrieval_timestamp']); self.assertIsNone(provenance['total_attempts']); self.assertIsNone(json.loads(capsule.read('scope.json'))['measured_charges_usd'])
            for member in json.loads(capsule.read('artifact-manifest.json')): self.assertEqual(digest(capsule.read(member['path'])), member['sha256'])
        before = len(self.objects); self.assertEqual(self.call('retain-validation')['archive'], first); self.assertEqual(len(self.objects), before); correction = self.call('retain-validation-correction')['archive']; self.assertNotEqual(correction['path'], first['path'])
        with zipfile.ZipFile(self.source / 'local-evidence-correction.zip') as capsule: self.assertEqual(json.loads(capsule.read('correction/local-evidence-archive.json')), first); self.assertIn('correction/metadata-correction.json', capsule.namelist())

    def test_local_validation_rejects_missing_linked_and_oversized_inputs_without_uploading_a_partial_capsule(self):
        self.retention_inputs(); path = self.root / 'docs/experiment-builder-qualification-v2.md'; original = path.read_bytes()
        for defect in ['missing', 'link', 'oversize']:
            with self.subTest(defect=defect):
                if path.exists() or path.is_symlink(): path.unlink()
                if defect == 'link': path.symlink_to(self.root / 'docs/experiment-builder-live-evaluation-v1.json')
                elif defect == 'oversize':
                    with path.open('wb') as stream: stream.truncate(6000000)
                with self.assertRaises(AssertionError): self.call('retain-validation')
                self.assertEqual(self.objects, {})
        path.unlink(); path.write_bytes(original)

    def test_local_validation_rejects_changed_remote_bytes_and_member_hashes_on_existing_pointer_readback(self):
        self.retention_inputs(); self.call('retain-validation'); self.corrupt_download = True
        with self.assertRaises(AssertionError): self.call('retain-validation')
        self.corrupt_download = False; raw = archive({'artifact-manifest.json': canonical([dict(path='original', sha256='e' * 64)]), 'original': b'changed'}); pointer = dict(path='qualification/synthetic-member-tamper.zip', sha256=digest(raw), retrieved_sha256=digest(raw)); self.objects[pointer['path']] = raw; self.save('local-evidence-archive.json', pointer)
        with self.assertRaises(AssertionError): self.call('retain-validation')

    def test_entrypoint_rejects_unknown_modes_before_audit_creation_or_service_boundaries(self):
        with patch.object(sys, 'argv', [str(SOURCE), 'unknown-unit-action']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped: self.load('__main__')
        self.assertEqual(stopped.exception.code, 2); self.r.target.assert_not_called(); self.r.ssm.assert_not_called(); self.r.admin.query.assert_not_called()


if __name__ == '__main__': unittest.main()
