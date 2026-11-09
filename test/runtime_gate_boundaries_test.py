"""Trusted source eligibility rejects broadened manifests and overlays locally."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import auth_entrypoint_runtime_test as auth_fixtures
import captured_failure_runtime_test as captured_fixtures
import intake_initialization_gate_test as intake_fixtures

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('research_gate_boundaries',ROOT/'assets/platform/research-runtime-gate.py')
research=importlib.util.module_from_spec(spec);spec.loader.exec_module(research)


class RuntimeGateBoundaries(unittest.TestCase):
    def test_pins_require_exact_revision_and_unchanged_file_coverage(self):
        previous=dict(version=2,files={'original.py':'a'*64})
        for gate in [auth_fixtures.gate,captured_fixtures.gate,research]:
            self.assertEqual(gate.pin(previous,'b'*40,previous['files']),dict(version=3,source_revision='b'*40,files=previous['files']))
            for revision,files in [('short',previous['files']),('g'*40,previous['files']),('b'*40,{})]:
                with self.subTest(gate=gate.__name__,revision=revision),self.assertRaises(ValueError):gate.pin(previous,revision,files)

    def test_auth_and_captured_gates_reject_unbound_predecessors_and_invalid_qualification_certificates(self):
        for fixture_type,gate in [(auth_fixtures.AuthGate,auth_fixtures.gate),(captured_fixtures.FailureGate,captured_fixtures.gate)]:
            for change in ['missing-manifest','altered-approval','missing-test','symlink','empty-change','wrong-base']:
                with self.subTest(gate=gate.__name__,change=change),tempfile.TemporaryDirectory() as folder:
                    fixture=fixture_type();self.addCleanup(fixture.doCleanups)
                    before,after,manifest=fixture.fixture(Path(folder))
                    if change=='missing-manifest':manifest['files']={}
                    elif change=='wrong-base':manifest['files'][next(iter(manifest['files']))]='0'*64
                    elif change=='altered-approval':
                        (before/gate.APPROVAL).write_text('{}');manifest['files'][gate.APPROVAL]=gate.digest(b'{}')
                    elif change=='missing-test':
                        next((after/'tests').glob('*.py')).unlink()
                    elif change=='symlink':
                        path=next((before/'tests').glob('*.py'));path.unlink();path.symlink_to('../siwc_protocol.py')
                    else:
                        name='openclaw_auth.mjs' if gate is auth_fixtures.gate else 'dispatch_recovery.py'
                        (after/name).write_bytes((before/name).read_bytes())
                    with self.assertRaises((ValueError,FileNotFoundError)):gate.inspect(before,after,manifest)
            for scope,certificate in [({},'a'*64),({'qualification_profile':gate.PROFILE,'scientific_and_request_content_unchanged':True},'short')]:
                with self.assertRaises(ValueError):gate.approval(scope,certificate)
        with self.assertRaisesRegex(ValueError,'Frozen authentication'):auth_fixtures.gate.correction(b'foreign source')

    def test_captured_normalization_rejects_wrong_marker_and_import_time_effects(self):
        gate=captured_fixtures.gate
        self.assertEqual(gate.normalized('def ledger(a):\n return dict(original=1)'),gate.normalized('def ledger(a):\n return None'))
        for source in ["FAILURE_VERSION='unknown'", "FAILURE_VERSION=OTHER='captured-provider-failure-v1'",
                'def ledger(a=invoke()):\n return None', 'def ledger(a)->str:\n return None',
                'def captured_failure(*,arg=invoke()):\n return None']:
            with self.subTest(source=source),self.assertRaises(ValueError):gate.normalized(source)

    def test_overlay_base_and_inherited_profile_cannot_be_replaced_or_extended(self):
        captured=captured_fixtures.gate;auth=auth_fixtures.gate
        for previous in [dict(source_revision='invalid'),dict(source_revision='g'*40),dict(source_overlay={'version':'foreign'})]:
            with self.assertRaises(ValueError):captured.overlay(previous)
        for previous in [{},dict(source_overlay={'version':'foreign'}),dict(source_overlay={'version':captured.OVERLAY,'base_revision':'g'*40,'paths':['dispatch_recovery.py',auth.APPROVAL],'tests':[auth.CAPTURE_TEST]})]:
            with self.assertRaises(ValueError):auth.overlay(previous)
        self.assertEqual(captured.overlay(dict(source_revision='a'*40))['base_revision'],'a'*40)

    def test_auth_composition_accepts_only_fixed_paths_and_can_omit_new_candidate_checks_on_a_predecessor(self):
        gate=auth_fixtures.gate
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'base';proposal=root/'proposal'
            for tree in [base,proposal]:
                (tree/'research_workflow/policies').mkdir(parents=True);(tree/'research_workflow/tests').mkdir()
            for name in [*gate.PATHS,gate.CAPTURE_TEST]:(proposal/'research_workflow'/name).write_text('original '+name)
            result=gate.compose(base,proposal,root/'candidate')
            self.assertTrue((result/'research_workflow'/gate.CAPTURE_TEST).is_file())
            self.assertFalse((result/'research_workflow'/gate.TESTS[0]).exists())
            with self.assertRaises(ValueError):gate.compose(base,proposal,result)
            result=gate.compose(base,proposal,root/'without-tests',include_test=False)
            self.assertFalse((result/'research_workflow'/gate.CAPTURE_TEST).exists())

    def test_intake_gate_requires_original_manifest_initializer_and_retained_regressions(self):
        gate=intake_fixtures.gate
        with self.assertRaisesRegex(ValueError,'initializer'):gate.normalized('pass')
        with self.assertRaisesRegex(ValueError,'initializer'):gate.normalized(intake_fixtures.OLD+intake_fixtures.OLD)
        with self.assertRaisesRegex(ValueError,'source initialization'):gate.normalized(intake_fixtures.OLD.replace("context=sources.original(study,task['actor_id'])",'context={}'))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaisesRegex(ValueError,'missing'):gate.read(root,'absent.py')
            for path in ['../private','/private']:
                with self.assertRaisesRegex(ValueError,'Plain source'):gate.read(root,path)
            with self.assertRaisesRegex(ValueError,'manifest'):gate.inspect(root,root,{})
            old,new=root/'before',root/'after'
            for tree,source in [(old,intake_fixtures.OLD),(new,intake_fixtures.NEW)]:
                tree.mkdir();(tree/'autonomy.py').write_text(source)
            files={'autonomy.py':gate.digest((old/'autonomy.py').read_bytes())}
            manifest=dict(version='warm-intake-v1',files=files,source_binding=gate.digest(gate.canonical(files)),source_revision='a'*40)
            with self.assertRaisesRegex(ValueError,'Retained original'):gate.inspect(old,new,manifest)
            (old/'tests').mkdir();(new/'tests').mkdir()
            with self.assertRaisesRegex(ValueError,'regressions are missing'):gate.inspect(old,new,manifest)
            (old/'tests/one.py').write_text('pass');(new/'tests/one.py').write_text('pass')
            (new/'autonomy.py').write_text(intake_fixtures.OLD)
            with self.assertRaisesRegex(ValueError,'initializer correction required'):gate.inspect(old,new,manifest)
            (new/'autonomy.py').write_text(intake_fixtures.NEW)
            files['autonomy.py']='0'*64;manifest['source_binding']=gate.digest(gate.canonical(files))
            with self.assertRaisesRegex(ValueError,'source hash'):gate.inspect(old,new,manifest)

    def test_controller_ast_normalization_preserves_unrecognized_expressions_and_removes_only_fixed_reread_nodes(self):
        original="def parse():\n inspection_identifier(read)\n preserve_scientific_request()\n"
        expected="def parse():\n preserve_scientific_request()\n"
        self.assertEqual(research.protected_tree(original,'autonomy_model.py'),research.protected_tree(expected,'autonomy_model.py'))
        for path in [Path('/synthetic/missing')]:
            with self.assertRaises(ValueError):research.load(path)
        scope={'version':research.VERSION,'scientific_and_request_content_unchanged':True,'existing_tests_unchanged':True,'source_binding':'b'*64}
        self.assertEqual(research.approval(scope,'a'*64)['qualified_files_sha256'],'b'*64)
        for certificate in ['short','g'*64]:
            with self.assertRaises(ValueError):research.approval(scope,certificate)
        with self.assertRaises(ValueError):research.inspect('/before','/after',{'files':{}})

    def test_controller_manifest_rejects_changed_predecessors_noop_releases_and_unbound_inherited_evidence(self):
        for defect in ['none','predecessor','unchanged','approval']:
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);before=root/'before/research_workflow';after=root/'after/research_workflow'
                source=b'CONSTANT=1\ndef handler(event):\n return 1\ndef scientific():\n return CONSTANT\n'
                files={'autonomy.py':research.digest(source)}
                approval=dict(approved_for_lab_recovery=True,qualified_files_sha256=research.digest(research.canonical(files)),evidence_sha256='a'*64)
                for tree in [before,after]:
                    (tree/'policies').mkdir(parents=True);(tree/'tests/subdirectory').mkdir(parents=True)
                    (tree/'autonomy.py').write_bytes(source)
                    (tree/research.APPROVAL).write_bytes(research.canonical(approval))
                    (tree/'tests/original.py').write_text('assert True')
                    (tree/'tests/notes.txt').write_text('Retained nonexecutable notes')
                files[research.APPROVAL]=research.digest((before/research.APPROVAL).read_bytes())
                manifest=dict(source_revision='a'*40,files=files)
                if defect!='unchanged':(after/'autonomy.py').write_bytes(source.replace(b'return 1',b'return 2'))
                if defect=='predecessor':files['autonomy.py']='0'*64
                elif defect=='approval':
                    (before/research.APPROVAL).write_text('{}');files[research.APPROVAL]=research.digest(b'{}')
                if defect=='none':self.assertEqual(research.inspect(before,after,manifest)['changed_files'],['autonomy.py'])
                else:
                    with self.assertRaises(ValueError):research.inspect(before,after,manifest)


if __name__=='__main__':unittest.main()
