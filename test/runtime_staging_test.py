"""Real staging logic against synthetic pinned files; no checkout/cloud mutation."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'bin' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


intake = module('prepare-intake-runtime')
api = module('prepare-research-api-runtime')


class RuntimeStaging(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='jumpserve-staging-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.backend = self.root / 'backend'
        self.source = self.backend / 'research_workflow'
        self.source.mkdir(parents=True)
        self.files = {}
        for name in ('intake_worker.py', 'intake_parallel.py', 'openclaw_runtime.py', 'policies/test-policy.json'):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = ('# synthetic original ' + name + '\n').encode()
            target.write_bytes(raw)
            self.files[name] = hashlib.sha256(raw).hexdigest()

    def manifest(self, *, kind='intake', **change):
        value = dict(version='warm-intake-v1', source_revision='a' * 40, files=self.files.copy())
        value.update(change)
        value['source_binding'] = hashlib.sha256(json.dumps(value['files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        filename = 'intake-worker-runtime.json' if kind == 'intake' else 'research-api-runtime.json'
        (self.root / filename).write_text(json.dumps(value))
        return value

    def test_intake_copies_exact_bytes_and_removes_only_undeclared_files(self):
        original = self.manifest()
        destination = self.root / '.runtime-intake'
        (destination / 'old/nested').mkdir(parents=True)
        (destination / 'old/nested/stale.py').write_text('stale')
        (destination / 'intake-manifest.json').write_text('older metadata')
        result = intake.prepare(self.backend, self.root)
        self.assertEqual(result, dict(version='warm-intake-v1', files=4, source_binding=original['source_binding'], deployed=False, provider_calls=0))
        for name in self.files:
            self.assertEqual((destination / name).read_bytes(), (self.source / name).read_bytes())
        self.assertFalse((destination / 'old/nested/stale.py').exists())
        self.assertTrue((destination / 'old/nested').is_dir())
        self.assertEqual(json.loads((destination / 'intake-manifest.json').read_bytes()), original)
        self.assertEqual(intake.prepare(self.backend, self.root), result)

    def test_intake_refuses_unqualified_revision_or_binding_before_staging(self):
        for change in ({'version': 'other'}, {'source_revision': 'main'}):
            self.manifest(**change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'Pinned intake revision'):
                intake.prepare(self.backend, self.root)
        value = self.manifest()
        value['source_binding'] = '0' * 64
        (self.root / 'intake-worker-runtime.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'source binding differs'):
            intake.prepare(self.backend, self.root)
        self.assertFalse((self.root / '.runtime-intake').exists())

    def test_intake_rejects_unsafe_paths_missing_files_symlinks_and_hash_changes(self):
        for name in ('../escape.py', str(self.root / 'absolute.py')):
            self.manifest(files={name: '0' * 64})
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Relative declared source'):
                intake.prepare(self.backend, self.root)
        self.manifest(files={'missing.py': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'Plain intake runtime source'):
            intake.prepare(self.backend, self.root)
        link = self.source / 'alias.py'; link.symlink_to(self.source / 'intake_worker.py')
        self.manifest(files={'alias.py': self.files['intake_worker.py']})
        with self.assertRaisesRegex(ValueError, 'Plain intake runtime source'):
            intake.prepare(self.backend, self.root)
        self.manifest(files={'intake_worker.py': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'Pinned intake source differs'):
            intake.prepare(self.backend, self.root)

    def test_intake_requires_all_three_warm_worker_entrypoints(self):
        for absent in ('intake_worker.py', 'intake_parallel.py', 'openclaw_runtime.py'):
            self.manifest(files={name: sha for name, sha in self.files.items() if name != absent})
            with self.subTest(absent=absent), self.assertRaisesRegex(ValueError, 'Incomplete warm intake runtime'):
                intake.prepare(self.backend, self.root)

    def test_api_stages_nested_originals_and_prunes_only_unlisted_files(self):
        manifest = self.manifest(kind='api')
        destination = self.root / '.runtime-api/research_workflow'
        (destination / 'old').mkdir(parents=True)
        (destination / 'old/stale.py').write_text('stale')
        result = api.prepare(self.backend, self.root)
        self.assertEqual(result, dict(source_revision=manifest['source_revision'], files=4, destination=str(destination)))
        self.assertTrue((destination / 'old').is_dir())
        self.assertFalse((destination / 'old/stale.py').exists())
        for name in self.files:
            self.assertEqual((destination / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(api.prepare(self.backend, self.root), result)

    def test_api_validates_every_input_before_pruning_a_prior_runtime(self):
        destination = self.root / '.runtime-api/research_workflow'
        destination.mkdir(parents=True)
        original = destination / 'retained.py'; original.write_text('retain original runtime')
        for files, message in [({'../escape.py': '0' * 64}, 'Unsafe API runtime filename'),
                               ({'intake_worker.py': '0' * 64}, 'API runtime hash differs')]:
            self.manifest(kind='api', files=files)
            with self.subTest(files=files), self.assertRaisesRegex(ValueError, message):
                api.prepare(self.backend, self.root)
            self.assertEqual(original.read_text(), 'retain original runtime')

    def test_cli_frontends_delegate_the_selected_backend_and_emit_results(self):
        for command in (intake, api):
            with self.subTest(command=command.__name__), patch.object(command, 'prepare', return_value={'files': 3}) as prepare, \
                    patch.object(sys, 'argv', [command.__file__, '--backend', str(self.backend)]), contextlib.redirect_stdout(io.StringIO()) as output:
                command.main()
                prepare.assert_called_once_with(self.backend)
                self.assertEqual(json.loads(output.getvalue()), {'files': 3})
            with patch.object(command, 'prepare', return_value={}) as prepare, patch.object(sys, 'argv', [command.__file__]), contextlib.redirect_stdout(io.StringIO()):
                command.main(); prepare.assert_called_once_with(command.ROOT.parent / 'jumpserve-back-end')

    def test_entrypoint_help_does_not_stage_a_runtime(self):
        for command in (intake, api):
            with self.subTest(command=command.__name__), patch.object(sys, 'argv', [command.__file__, '--help']), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
                runpy.run_path(command.__file__, run_name='__main__')
            self.assertEqual(error.exception.code, 0)


if __name__ == '__main__':
    unittest.main()
