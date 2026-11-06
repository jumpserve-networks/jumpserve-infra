"""The dedicated recovery gate cannot change scientific or transport source."""
import importlib.util,json,tempfile,unittest,io,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('captured_gate',ROOT/'assets/platform/captured-failure-runtime-gate.py');gate=importlib.util.module_from_spec(s);s.loader.exec_module(gate)
class FailureGate(unittest.TestCase):
 def fixture(self,root):
  before=root/'before';after=root/'after'
  for p in (before,after):
   (p/'policies').mkdir(parents=True);(p/'tests').mkdir();(p/'tests/test_original.py').write_text('assert True\n')
   (p/'dispatch_recovery.py').write_text('import json\nVERSION="original"\ndef ledger(a,b,c,d):\n return None\ndef original_transport():\n return "frozen"\n')
   (p/'siwc_protocol.py').write_text('SCIENTIFIC_REQUEST="frozen"\n')
  files={n:gate.digest((before/n).read_bytes()) for n in ('dispatch_recovery.py','siwc_protocol.py')}
  approval=dict(approved_for_lab_recovery=True,qualified_files_sha256=gate.digest(gate.encoded(files)),evidence_sha256='a'*64)
  for p in (before,after):(p/gate.APPROVAL).write_text(json.dumps(approval))
  files[gate.APPROVAL]=gate.digest((before/gate.APPROVAL).read_bytes())
  manifest=dict(source_revision='a'*40,files=files)
  (after/'dispatch_recovery.py').write_text('import json\nVERSION="original"\nFAILURE_VERSION="captured-provider-failure-v1"\ndef ledger(a,b,c,d):\n return []\ndef captured_failure(request,response,status,reason):\n return None\ndef original_transport():\n return "frozen"\n')
  return before,after,manifest
 def test_dedicated_profile_preserves_existing_request_and_validation_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   before,after,manifest=self.fixture(Path(tmp));scope=gate.inspect(before,after,manifest)
   self.assertEqual(scope['qualification_profile'],gate.PROFILE);self.assertTrue(scope['scientific_and_request_content_unchanged']);self.assertEqual(scope['new_provider_calls'],0)
   self.assertEqual(gate.approval(scope,'b'*64)['qualified_files_sha256'],scope['source_binding'])
 def test_no_scientific_transport_import_test_or_arbitrary_execution_expansion(self):
  for defect in ('request','transport','import','old-test','new-module','credential','decorator','new-global'):
   with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
    before,after,manifest=self.fixture(Path(tmp));p=after/'dispatch_recovery.py';raw=p.read_text()
    if defect=='request':(after/'siwc_protocol.py').write_text('SCIENTIFIC_REQUEST="changed"\n')
    elif defect=='transport':p.write_text(raw.replace('return "frozen"','return "changed"'))
    elif defect=='import':p.write_text('import subprocess\n'+raw)
    elif defect=='old-test':(after/'tests/test_original.py').write_text('assert False\n')
    elif defect=='new-module':(after/'provider.py').write_text('pass\n')
    elif defect=='credential':p.write_text(raw.replace('return []','return credential()'))
    elif defect=='decorator':p.write_text(raw.replace('def captured_failure','@invoke()\ndef captured_failure'))
    else:p.write_text(raw+'ADMIT_UNKNOWNS=True\n')
    with self.assertRaises(gate.ScopeError):gate.inspect(before,after,manifest)
 def test_overlay_discards_unrelated_main_changes_and_keeps_fixed_source_identity(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);base=root/'base';proposal=root/'proposal'
   for p in (base,proposal):
    (p/'research_workflow/policies').mkdir(parents=True);(p/'research_workflow/tests').mkdir()
    (p/'research_workflow/dispatch_recovery.py').write_text('original recovery\n')
    (p/'research_workflow'/gate.APPROVAL).write_text('{}')
    (p/'research_workflow/api.py').write_text('original API\n')
   (proposal/'research_workflow/api.py').write_text('unrelated API changes\n')
   (proposal/'research_workflow/dispatch_recovery.py').write_text('reviewed recovery\n')
   (proposal/'research_workflow'/gate.TEST).write_text('assert True\n')
   composed=gate.compose(base,proposal,root/'qualified')
   self.assertEqual((composed/'research_workflow/api.py').read_text(),'original API\n')
   self.assertEqual((composed/'research_workflow/dispatch_recovery.py').read_text(),'reviewed recovery\n')
   self.assertEqual((proposal/'research_workflow/api.py').read_text(),'unrelated API changes\n')
   with self.assertRaises(gate.ScopeError):gate.compose(base,proposal,composed)
 def test_asset_staging_uses_verified_frozen_bytes_without_overwriting_backend_main(self):
  s=importlib.util.spec_from_file_location('runtime_files',ROOT/'bin/prepare-research-runtime.py');stage=importlib.util.module_from_spec(s);s.loader.exec_module(stage)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'research_workflow/policies').mkdir(parents=True)
   values={'dispatch_recovery.py':b'reviewed recovery','policies/autonomous-repair-release-v1.json':b'{}','api.py':b'frozen API'}
   for name,raw in values.items():(root/'research_workflow'/name).write_bytes(raw)
   (root/'research_workflow/api.py').write_bytes(b'unrelated main API')
   blob=io.BytesIO()
   with tarfile.open(fileobj=blob,mode='w') as archive:
    raw=values['api.py'];info=tarfile.TarInfo('source/research_workflow/api.py');info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
   manifest=dict(files={n:gate.digest(v) for n,v in values.items()},source_overlay=gate.overlay(dict(source_revision='a'*40)))
   actual=stage.verified_files(root,manifest,blob.getvalue());self.assertEqual(actual,values)
   self.assertEqual((root/'research_workflow/api.py').read_bytes(),b'unrelated main API')
   manifest['files']['api.py']='0'*64
   with self.assertRaises(ValueError):stage.verified_files(root,manifest,blob.getvalue())
if __name__=='__main__':unittest.main()
