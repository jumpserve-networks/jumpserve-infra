"""Frozen scientific scope, derived authority and exact live-template limits."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
gate=load('scope_gate',ROOT/'assets/platform/research-runtime-gate.py')
release=load('scoped_release',ROOT/'bin/research-runtime-release.py')
class RuntimeReleaseTests(unittest.TestCase):
 def test_scope_freezes_every_other_function_import_policy_and_existing_test(self):
  with tempfile.TemporaryDirectory() as tmp:
   before=Path(tmp)/'before/research_workflow';after=Path(tmp)/'after/research_workflow'
   files={'autonomy.py':b'X=1\ndef handler(event,context=None):\n return 1\ndef scientific():\n return X\n','policies/frozen.json':b'{}'}
   files[gate.APPROVAL]=gate.canonical(dict(approved_for_lab_recovery=True,qualified_files_sha256=gate.digest(gate.canonical({k:gate.digest(v) for k,v in files.items()})),evidence_sha256='a'*64))
   for root in (before,after):
    for name,raw in files.items():(root/name).parent.mkdir(parents=True,exist_ok=True);(root/name).write_bytes(raw)
    (root/'tests').mkdir();(root/'tests/test_frozen.py').write_bytes(b'assert True\n')
   manifest=dict(version=1,source_revision='b'*40,files={k:gate.digest(v) for k,v in files.items()})
   (after/'autonomy.py').write_bytes(files['autonomy.py'].replace(b'return 1',b'return 2'))
   scope=gate.inspect(before,after,manifest);self.assertEqual(scope['changed_files'],['autonomy.py'])
   for name,bad in [('autonomy.py',files['autonomy.py'].replace(b'return X',b'return 2')),('policies/frozen.json',b'{"weaken":true}'),('tests/test_frozen.py',b'assert False\n')]:
    old=(after/name).read_bytes();(after/name).write_bytes(bad)
    with self.assertRaises(gate.ScopeError):gate.inspect(before,after,manifest)
    (after/name).write_bytes(old)
   (after/'extra.py').write_bytes(b'import os\n')
   with self.assertRaises(gate.ScopeError):gate.inspect(before,after,manifest)
 def test_renderer_changes_only_three_controller_code_fields(self):
  old=dict(Resources={n:dict(Type='AWS::Lambda::Function',Properties=dict(Code={'unchanged':'old'},Role='frozen',Environment={'Variables':{'budget':'unchanged'}}),Metadata={'aws:asset:path':'old'}) for n in release.CONTROLLERS},Parameters={'p':{'Type':'String'}},Outputs={'o':{'Value':'frozen'}})
  old['Resources']['ScientificExecutor']=dict(Type='AWS::Lambda::Version',Properties={'FunctionName':'frozen'})
  new=release.render(old,'a'*64+'.zip')
  for name in release.CONTROLLERS:
   value=new['Resources'][name];value['Properties']['Code']=old['Resources'][name]['Properties']['Code'];value['Metadata']['aws:asset:path']='old'
  self.assertEqual(old,new)
  with self.assertRaises(ValueError):release.render(old,'../unqualified.zip')
 def test_approval_and_pin_are_exact_derived_metadata(self):
  scope=dict(version=gate.VERSION,scientific_and_request_content_unchanged=True,existing_tests_unchanged=True,source_binding='a'*64)
  self.assertEqual(gate.approval(scope,'b'*64)['qualified_files_sha256'],'a'*64)
  with self.assertRaises(gate.ScopeError):gate.approval(dict(scope,existing_tests_unchanged=False),'b'*64)
  with self.assertRaises(gate.ScopeError):gate.pin(dict(version=1,files={'a':'b'}),'a'*40,{'other':'b'})
if __name__=='__main__':unittest.main()
