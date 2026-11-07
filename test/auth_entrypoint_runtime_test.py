"""The auth profile admits exactly the reviewed entrypoint change."""
import copy,importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
gate=module('auth_gate',ROOT/'assets/platform/auth-entrypoint-runtime-gate.py')
class AuthGate(unittest.TestCase):
 def fixture(self,root):
  before,after=root/'before',root/'after'
  old=b"import {fileURLToPath, pathToFileURL} from 'node:url';\nif(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {\n validateScopes();\n}\n"
  self.enterContext(patch.object(gate,'PREVIOUS_AUTH',gate.digest(old)))
  for p in (before,after):
   (p/'policies').mkdir(parents=True);(p/'tests').mkdir();(p/'tests/test_old.py').write_text('assert True\n')
   (p/'openclaw_auth.mjs').write_bytes(old);(p/'siwc_protocol.py').write_text('KEEP_SCIENCE=True\n')
  files={n:gate.digest((before/n).read_bytes()) for n in ('openclaw_auth.mjs','siwc_protocol.py')}
  approval=dict(approved_for_lab_recovery=True,qualified_files_sha256=gate.digest(gate.encoded(files)),evidence_sha256='a'*64)
  for p in (before,after):(p/gate.APPROVAL).write_text(json.dumps(approval))
  files[gate.APPROVAL]=gate.digest((before/gate.APPROVAL).read_bytes());(after/'openclaw_auth.mjs').write_bytes(gate.correction(old))
  return before,after,dict(source_revision='a'*40,files=files)
 def test_exact_entrypoint_only_and_bound_predecessor(self):
  with tempfile.TemporaryDirectory() as tmp:
   before,after,manifest=self.fixture(Path(tmp));scope=gate.inspect(before,after,manifest)
   self.assertEqual(scope['changed_files'],['openclaw_auth.mjs']);self.assertEqual(scope['qualification_profile'],gate.PROFILE)
   self.assertEqual(gate.approval(scope,'b'*64)['qualified_files_sha256'],scope['source_binding'])
 def test_scopes_tokens_transport_old_tests_and_extra_code_cannot_change(self):
  for defect in ('auth-body','transport','old-test','extra-module','wrong-base','no-change'):
   with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
    before,after,manifest=self.fixture(Path(tmp))
    if defect=='auth-body':p=after/'openclaw_auth.mjs';p.write_bytes(p.read_bytes().replace(b'validateScopes()',b'skipScopes()'))
    elif defect=='transport':(after/'siwc_protocol.py').write_text('KEEP_SCIENCE=False\n')
    elif defect=='old-test':(after/'tests/test_old.py').write_text('pass\n')
    elif defect=='extra-module':(after/'new.py').write_text('pass\n')
    elif defect=='wrong-base':manifest['files']['openclaw_auth.mjs']='0'*64
    else:(after/'openclaw_auth.mjs').write_bytes((before/'openclaw_auth.mjs').read_bytes())
    with self.assertRaises(gate.ScopeError):gate.inspect(before,after,manifest)
 def test_release_retains_api_and_legacy_refusals(self):
  release=module('auth_release',ROOT/'bin/research-runtime-release.py');scope=dict(qualification_profile=gate.PROFILE)
  self.assertEqual(release.controller_targets(scope),release.CONTROLLERS-{release.HTTP_API})
  q=dict(scope=scope,previous_manifest=dict(files={'old':'a'}),manifest=dict(files={'new':'b'}))
  with patch.object(release,'installed',side_effect=[ValueError('old differs'),[]]):self.assertEqual(release.controller_baseline(None,{},q,release.controller_targets(scope)),'already-qualified-candidate')
  with patch.object(release,'installed',side_effect=ValueError('foreign')): 
   with self.assertRaises(ValueError):release.controller_baseline(None,{},q,release.controller_targets(scope))
  self.assertEqual(release.controller_targets({}),release.CONTROLLERS)
 def test_source_composition_is_closed_and_does_not_take_unrelated_main(self):
  previous=dict(source_revision='a'*40,source_overlay=dict(version='captured-provider-overlay-v1',base_revision='b'*40,paths=['dispatch_recovery.py',gate.APPROVAL],tests=[gate.CAPTURE_TEST]))
  overlay=gate.overlay(previous);self.assertEqual(overlay['paths'],gate.PATHS)
  invalid=copy.deepcopy(previous);invalid['source_overlay']['paths'].append('api.py')
  with self.assertRaises(gate.ScopeError):gate.overlay(invalid)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);base=root/'base';proposal=root/'proposal'
   for p in (base,proposal):(p/'research_workflow/policies').mkdir(parents=True);(p/'research_workflow/tests').mkdir()
   (base/'research_workflow/api.py').write_text('frozen API')
   (proposal/'research_workflow/api.py').write_text('unrelated main')
   for name in [*gate.PATHS,gate.CAPTURE_TEST,*gate.TESTS]:(proposal/'research_workflow'/name).write_text('reviewed '+name)
   target=gate.compose(base,proposal,root/'candidate')
   self.assertEqual((target/'research_workflow/api.py').read_text(),'frozen API')
   self.assertEqual((target/'research_workflow/openclaw_auth.mjs').read_text(),'reviewed openclaw_auth.mjs')
 def test_staging_and_profile_selection_bind_the_declared_auth_composition(self):
  stage=module('auth_stage',ROOT/'bin/prepare-research-runtime.py');release=module('auth_profile_release',ROOT/'bin/research-runtime-release.py')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);backend=root/'backend';(backend/'research_workflow/policies').mkdir(parents=True)
   overlay=gate.overlay(dict(source_overlay=dict(version='captured-provider-overlay-v1',base_revision='b'*40,paths=['dispatch_recovery.py',gate.APPROVAL],tests=[gate.CAPTURE_TEST])))
   values={'api.py':b'frozen API','dispatch_recovery.py':b'captured recovery','openclaw_auth.mjs':b'corrected entrypoint',gate.APPROVAL:b'{}'}
   for name,raw in values.items():(backend/'research_workflow'/name).write_bytes(raw)
   (backend/'research_workflow/api.py').write_bytes(b'unrelated main')
   stream=io.BytesIO()
   with tarfile.open(fileobj=stream,mode='w') as z:
    member=tarfile.TarInfo('base/research_workflow/api.py');member.size=len(values['api.py']);z.addfile(member,io.BytesIO(values['api.py']))
   manifest=dict(files={n:gate.digest(raw) for n,raw in values.items()},source_overlay=overlay)
   self.assertEqual(stage.verified_files(backend,manifest,stream.getvalue()),values)
   (root/'.pin/research-runtime-qualifications').mkdir(parents=True);(root/'assets/platform').mkdir(parents=True)
   (root/'assets/platform/auth-entrypoint-runtime-gate.py').write_bytes((ROOT/'assets/platform/auth-entrypoint-runtime-gate.py').read_bytes())
   (root/'.pin/research-workflow-runtime.json').write_text(json.dumps(manifest))
   binding=gate.digest(gate.encoded({n:h for n,h in manifest['files'].items() if n!=gate.APPROVAL}));certificate=root/'.pin/research-runtime-qualifications'/(binding+'.json')
   certificate.write_text(json.dumps(dict(scope=dict(qualification_profile=gate.PROFILE))))
   with patch.object(release,'ROOT',root):self.assertEqual(release.module().PROFILE,gate.PROFILE)
   certificate.write_text(json.dumps(dict(scope=dict(qualification_profile='unreviewed'))))
   with patch.object(release,'ROOT',root),self.assertRaises(ValueError):release.module()
if __name__=='__main__':unittest.main()
