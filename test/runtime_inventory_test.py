import tempfile
from pathlib import Path
import unittest
from runtime_inventory import source_files


class RuntimeInventory(unittest.TestCase):
    def test_new_unloaded_runtime_sources_cannot_disappear_from_the_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            names=['agent/new-module.py','assets/platform/new-runtime.py','assets/platform/research-runtime-gate.py',
                'assets/platform/research-runtime-checks.py','assets/platform/install-slack-gateway.py',
                'bin/operator-release.py','agent/package/dependency.py','assets/node_modules/dependency.py']
            for name in names:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('pass\n')
            runtime={Path(path).relative_to(root).as_posix() for path in source_files(root)}
            self.assertEqual(runtime,set(names[:3]))
            all_sources={Path(path).relative_to(root).as_posix() for path in source_files(root,True)}
            self.assertEqual(all_sources,set(names[:6]))


if __name__=='__main__':unittest.main()
