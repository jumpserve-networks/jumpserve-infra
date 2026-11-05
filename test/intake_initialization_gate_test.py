"""Initialization qualification admits two exact AST edits and freezes everything else."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('intake_initialization_gate',ROOT/'assets/platform/intake-initialization-gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
OLD="""def intake(task):
 context=task['context'].copy()
 if not context:
  context=sources.original(study,task['actor_id'])
  return advance(task,'queued',context=context)
 return inspect_existing(task,context['text_artifact_id'])
def science():
 return 'frozen criterion'
"""
NEW=OLD.replace('if not context:',"if not context or context=={'intake_pool_version':'warm-intake-v1'}:").replace("context=sources.original(study,task['actor_id'])","context=dict(context,**sources.original(study,task['actor_id']))")


class IntakeInitializationGate(unittest.TestCase):
 def test_exact_fix_preserves_every_other_ast_node(self):
  self.assertEqual(gate.normalized(OLD),gate.normalized(NEW,corrected=True))

 def test_broader_resets_source_changes_and_scientific_edits_are_rejected(self):
  for raw in (NEW.replace("context=={'intake_pool_version':'warm-intake-v1'}","True"),NEW.replace('dict(context,**sources.original','dict(**sources.original'),NEW.replace('context[\'text_artifact_id\']','None'),NEW.replace('frozen criterion','changed criterion')):
   with self.subTest(raw=raw):
    try:value=gate.normalized(raw,corrected=True)
    except ValueError:continue
    self.assertNotEqual(value,gate.normalized(OLD))

 def test_manifest_binding_and_existing_tests_are_required(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);old=root/'old';new=root/'new'
   for directory,raw in ((old,OLD),(new,NEW)):
    (directory/'tests').mkdir(parents=True);(directory/'autonomy.py').write_text(raw)
    (directory/'policy.json').write_text('{"frozen":true}')
    (directory/'tests/test_original.py').write_text('assert True\n')
   files={n:gate.digest((old/n).read_bytes()) for n in ('autonomy.py','policy.json')}
   manifest=dict(version='warm-intake-v1',source_revision='a'*40,source_binding=gate.digest(gate.canonical(files)),files=files)
   proof=gate.inspect(old,new,manifest)
   self.assertEqual(proof['changed_files'],['autonomy.py']);self.assertEqual(proof['provider_calls'],0)
   (new/'policy.json').write_text('{"frozen":false}')
   with self.assertRaises(ValueError):gate.inspect(old,new,manifest)
   (new/'policy.json').write_bytes((old/'policy.json').read_bytes())
   (new/'tests/test_original.py').write_text('assert False\n')
   with self.assertRaises(ValueError):gate.inspect(old,new,manifest)


if __name__=='__main__':unittest.main()
