"""Only an explicitly pinned, exact research skill may enter the runtime asset."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SKILL='skills/network-environment-repair-v1/SKILL.md'


class SkillStaging(unittest.TestCase):
    def staged(self,name,sha=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bin').mkdir();source=root/'backend/research_workflow'
            path=source/name;path.parent.mkdir(parents=True);path.write_bytes(b'versioned skill')
            shutil.copyfile(ROOT/'bin/prepare-research-runtime.py',root/'bin/prepare-research-runtime.py')
            (root/'research-workflow-runtime.json').write_text(json.dumps(dict(source_revision='a'*40,files={name:sha or hashlib.sha256(path.read_bytes()).hexdigest()})))
            result=subprocess.run([sys.executable,'-B',str(root/'bin/prepare-research-runtime.py'),'--backend',str(root/'backend')],capture_output=True,timeout=10)
            staged=root/'.runtime-backend/research_workflow'/name
            return result,staged.read_bytes() if staged.is_file() else None

    def test_exact_declared_skill_is_staged_byte_for_byte(self):
        result,raw=self.staged(SKILL)
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertEqual(raw,b'versioned skill')

    def test_skill_with_wrong_hash_cannot_enter_runtime(self):
        result,raw=self.staged(SKILL,'0'*64)
        self.assertNotEqual(result.returncode,0);self.assertIsNone(raw);self.assertIn(b'Runtime hash differs',result.stderr)

    def test_unreviewed_skill_paths_remain_rejected(self):
        for name in ('skills/arbitrary/SKILL.md','skills/network-environment-repair-v1/run.py','skills/network-environment-repair-v1/OTHER.md'):
            with self.subTest(name=name):
                result,raw=self.staged(name)
                self.assertNotEqual(result.returncode,0);self.assertIsNone(raw);self.assertIn(b'Unsafe runtime filename',result.stderr)


if __name__=='__main__':unittest.main()
