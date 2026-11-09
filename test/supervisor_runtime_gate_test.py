"""Untrusted candidate code is inspected as bytes/AST, never imported by these checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('supervisor_runtime_gate', ROOT / 'assets/platform/supervisor-runtime-gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SupervisorRuntimeGate(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='supervisor-gate-unit-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name); self.old = self.root / 'previous'; self.new = self.root / 'candidate'
        self.old.mkdir(); (self.old / 'tests').mkdir()
        self.write(self.old, 'policy.json', '{"version":"synthetic-policy"}')
        self.write(self.old, 'worker.py', '''class Controller:
    def boundary(self): return 'frozen boundary'
    def operation(self): return 'frozen operation'
    def coding_available(self): return False
    def reconcile_pending(self): return 'frozen reconciliation'
    def run(self): return 'frozen admission'
def main(): return 'frozen main'
def display(): return 'previous'
''')
        self.write(self.old, 'native.py', 'def execute(): return 1\ndef containers(): return 2\ndef container_prefix(): return 3\ndef failure_status(): return 4\ndef reconcile(): return 5\ndef display(): return "previous"\n')
        self.write(self.old, 'checks.py', 'def execute(): return "frozen checks"\ndef label(): return "previous"\n')
        self.write(self.old, 'call_recovery.py', 'def http_failure(): return 1\ndef effective_status(): return 2\ndef reconcile_http(): return 3\ndef label(): return "previous"\n')
        self.write(self.old, 'helper.py', '"""Installed operational helper."""\nimport json\nVALUE = 1\ndef operate(): return "previous"\nasync def fetch(): return "retained"\nclass Details:\n    value = 2\n    def label(self): return "retained"\n')
        self.write(self.old, 'capabilities.py', 'def descriptor(raw, name):\n    if b"CAPABILITY = \'fixture\'" not in raw: raise ValueError("Capability descriptor missing")\n    return {"name": name}\n')
        self.write(self.old, 'tests/test_existing.py', 'def test_original(): assert 1 == 1\n')
        shutil.copytree(self.old, self.new)
        self.manifest = dict(version=gate.VERSION, source_revision='a' * 40, files=gate.files(self.old))

    def write(self, root, name, text):
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

    def change(self, name='helper.py', before='return "previous"', after='return "candidate"'):
        path = self.new / name; original = path.read_text()
        self.assertIn(before, original); path.write_text(original.replace(before, after))

    def inspect(self): return gate.inspect(self.old, self.new, self.manifest)

    def test_qualified_operational_body_change_retains_exact_predecessor_hashes_and_original_tests(self):
        self.change(); self.write(self.new, 'tests/test_new.py', 'def test_added(): assert True\n')
        report = self.inspect()
        self.assertEqual(report['changed_files'], ['helper.py'])
        self.assertEqual(report['previous_revision'], 'a' * 40)
        self.assertEqual(report['previous_files'], self.manifest['files'])
        expected = {'platform_supervisor/helper.py': hashlib.sha256((self.new / 'helper.py').read_bytes()).hexdigest(),
                    'platform_supervisor/tests/test_new.py': hashlib.sha256((self.new / 'tests/test_new.py').read_bytes()).hexdigest()}
        self.assertEqual(report['candidate_paths'], expected)
        self.assertEqual(report['source_binding'], hashlib.sha256(json.dumps(report['files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        self.assertTrue(report['existing_checks_unchanged']); self.assertTrue(report['authority_and_transport_unchanged'])
        self.assertFalse(report['scientific_completion'])

    def test_predecessor_version_file_identity_revision_and_actual_source_must_match(self):
        self.change()
        original = self.manifest.copy()
        for change in [dict(version='wrong'), dict(files={}), dict(source_revision='A' * 40), dict(source_revision='a' * 39)]:
            with self.subTest(change=change):
                self.manifest = dict(original, **change)
                with self.assertRaisesRegex(ValueError, 'predecessor identity'): self.inspect()
        self.manifest = original; self.write(self.old, 'helper.py', 'def operate(): return "changed installed bytes"\n')
        with self.assertRaisesRegex(ValueError, 'predecessor identity'): self.inspect()

    def test_unchanged_source_and_test_only_changes_are_not_operational_repairs(self):
        with self.assertRaisesRegex(ValueError, 'No operational'): self.inspect()
        self.write(self.new, 'tests/test_extra.py', 'def test_extra(): pass\n')
        with self.assertRaisesRegex(ValueError, 'No operational'): self.inspect()

    def test_authority_files_deletions_and_new_json_are_never_admitted_as_operational_repairs(self):
        for name, operation in [('policy.json', 'edit'), ('capabilities.py', 'edit'), ('helper.py', 'delete'), ('new.json', 'create')]:
            with self.subTest(name=name):
                target = self.new / name; original = target.read_bytes() if target.exists() else None
                if operation == 'delete': target.unlink()
                else: target.write_text('{}')
                with self.assertRaisesRegex(ValueError, 'authority/transport broker or source deletion'): self.inspect()
                if original is None: target.unlink()
                else: target.write_bytes(original)

    def test_module_assignments_import_time_calls_and_class_bases_remain_unchanged(self):
        original = (self.new / 'helper.py').read_text()
        for candidate in [original.replace('VALUE = 1', 'VALUE = 2'), original + '\noperate()\n', original.replace('class Details:', 'class Details(object):'), original.replace('value = 2', 'value = 3')]:
            with self.subTest(candidate=candidate):
                self.write(self.new, 'helper.py', candidate)
                with self.assertRaisesRegex(ValueError, 'module-level execution'): self.inspect()

    def test_protected_controller_transport_check_and_uncertain_call_methods_cannot_be_replaced_or_deleted(self):
        cases = [('worker.py', 'return \'frozen boundary\''), ('worker.py', 'return \'frozen operation\''),
                 ('worker.py', 'return False'), ('worker.py', 'return \'frozen reconciliation\''),
                 ('worker.py', 'return \'frozen admission\''), ('worker.py', 'return \'frozen main\''),
                 ('native.py', 'return 1'), ('native.py', 'return 2'), ('native.py', 'return 3'), ('native.py', 'return 4'), ('native.py', 'return 5'),
                 ('checks.py', 'return "frozen checks"'), ('call_recovery.py', 'return 1'), ('call_recovery.py', 'return 2'), ('call_recovery.py', 'return 3')]
        for name, old in cases:
            original = (self.new / name).read_text()
            with self.subTest(name=name, old=old):
                self.write(self.new, name, original.replace(old, 'return "untrusted"'))
                with self.assertRaisesRegex(ValueError, 'Frozen supervisor admission/qualification method'): self.inspect()
                self.write(self.new, name, original)
        self.write(self.new, 'checks.py', 'def label(): return "new"\n')
        with self.assertRaisesRegex(ValueError, 'Frozen supervisor admission/qualification method'): self.inspect()

    def test_nonprotected_helpers_in_frozen_method_modules_can_be_updated(self):
        for name in ['worker.py', 'native.py', 'checks.py', 'call_recovery.py']:
            if name == 'worker.py': self.change(name, "return 'previous'", "return 'candidate'")
            else: self.change(name)
        self.assertEqual(self.inspect()['changed_files'], ['call_recovery.py', 'checks.py', 'native.py', 'worker.py'])

    def test_new_passive_module_is_qualified_without_executing_its_function_bodies(self):
        marker = self.root / 'never-execute'
        self.write(self.new, 'feature.py', f'''"""New operational capability."""
import pathlib
from typing import Any
VALUE: int = 3
OPTIONS = {{'enabled': True, 'attempts': [1, 2]}}
def run(value: int = 1, /, *items: str, limit: int = 2, **kwargs: Any) -> str:
    pathlib.Path({str(marker)!r}).write_text('must never run')
    return 'candidate'
async def fetch(): return 'candidate'
''')
        report = self.inspect(); self.assertEqual(report['changed_files'], ['feature.py'])
        self.assertFalse(marker.exists())

    def test_new_module_rejects_effectful_defaults_annotations_decorators_classes_and_assignments(self):
        candidates = ['X = invoke()\n', 'invoke()\n', 'if True:\n    pass\n', 'class Effect:\n    pass\n',
                      '@decorate\ndef run(): pass\n', 'def run(value=invoke()): pass\n', 'def run(*, value=invoke()): pass\n',
                      'def run(value: invoke()): pass\n', 'def run(*args: invoke()): pass\n', 'def run(**kwargs: invoke()): pass\n', 'def run() -> invoke(): pass\n']
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.write(self.new, 'feature.py', candidate)
                with self.assertRaises(ValueError): self.inspect()

    def test_changed_existing_function_headers_cannot_execute_code_at_import(self):
        original = (self.new / 'helper.py').read_text()
        for replacement in ['def operate(value=invoke()):', '@decorate\ndef operate():', 'def operate() -> invoke():']:
            with self.subTest(replacement=replacement):
                self.write(self.new, 'helper.py', original.replace('def operate():', replacement))
                with self.assertRaisesRegex(ValueError, 'function import-time effects'): self.inspect()
        self.write(self.new, 'helper.py', original.replace('async def fetch(): return "retained"', 'async def fetch(): return "candidate"'))
        self.assertEqual(self.inspect()['changed_files'], ['helper.py'])
        self.write(self.new, 'helper.py', original.replace('return "retained"', 'return "candidate"'))
        self.assertEqual(self.inspect()['changed_files'], ['helper.py'])

    def test_candidate_capability_uses_only_the_installed_descriptor_contract(self):
        self.write(self.new, 'capability_fixture.py', "CAPABILITY = 'fixture'\ndef run(): return 'passive body'\n")
        self.assertEqual(self.inspect()['changed_files'], ['capability_fixture.py'])
        self.write(self.new, 'capability_fixture.py', "CAPABILITY = 'unregistered'\n")
        with self.assertRaisesRegex(ValueError, 'Capability descriptor missing'): self.inspect()

    def test_existing_tests_cannot_be_changed_deleted_or_replaced_with_links(self):
        self.change(); target = self.new / 'tests/test_existing.py'; original = target.read_bytes()
        target.write_text('def test_original(): pass\n')
        with self.assertRaisesRegex(ValueError, 'Existing supervisor checks changed'): self.inspect()
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'Existing supervisor checks changed'): self.inspect()
        external = self.root / 'external.py'; external.write_bytes(original); target.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'Existing supervisor checks changed'): self.inspect()

    def test_new_tests_and_source_cannot_reference_external_files_with_symlinks(self):
        self.change(); external = self.root / 'external.py'; external.write_text('def run(): pass\n')
        (self.new / 'tests/test_link.py').symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'New supervisor checks cannot be links'): self.inspect()
        (self.new / 'tests/test_link.py').unlink(); (self.new / 'linked.py').symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'source cannot contain links'): self.inspect()

    def test_plain_identifiers_are_required_and_non_source_files_do_not_enter_the_hash_inventory(self):
        self.change(); self.write(self.new, 'bad-name.py', 'pass\n')
        with self.assertRaisesRegex(ValueError, 'plain Python identifiers'): self.inspect()
        (self.new / 'bad-name.py').unlink(); self.write(self.new, 'README.md', 'not executable source')
        (self.new / 'empty-directory').mkdir()
        self.assertNotIn('README.md', self.inspect()['files'])


if __name__ == '__main__': unittest.main()
