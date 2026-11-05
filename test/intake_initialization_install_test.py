"""Actual local file swaps and rollback, with service/DB effects mocked."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
import zipfile
from intake_initialization_gate_test import OLD,NEW,gate

spec=importlib.util.spec_from_file_location('intake_install',Path(__file__).resolve().parents[1]/'assets/platform/install-intake-initialization.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class IntakeInstallation(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.current=self.root/'intake-runtime';self.current.mkdir()
  self.original={'autonomy.py':OLD.encode(),'intake_worker.py':b'raise RuntimeError("never import in the test process")','policy.json':b'{"frozen":true}'}
  files={n:gate.digest(raw) for n,raw in self.original.items()}
  self.old=dict(version='warm-intake-v1',source_revision='a'*40,files=files,source_binding=gate.digest(gate.canonical(files)))
  for n,raw in self.original.items():(self.current/n).write_bytes(raw)
  (self.current/'intake-manifest.json').write_bytes(gate.canonical(self.old))
  self.new_files=dict(self.original,**{'autonomy.py':NEW.encode()});self.bundle=self.root/'bundle.zip'
  self.run=Mock();self.read=Mock(side_effect=lambda name:[dict(enabled=False)] if name=='runtime' else [])
  (self.root/'quota-state').write_text('original-cooldown')

 def packet(self,files=None):
  files=self.new_files if files is None else files
  hashes={n:gate.digest(raw) for n,raw in files.items()}
  new=dict(self.old,files=hashes,source_revision='b'*40,source_binding=gate.digest(gate.canonical(hashes)))
  with zipfile.ZipFile(self.bundle,'w',zipfile.ZIP_DEFLATED) as archive:
   for n,raw in files.items():archive.writestr(n,raw)
   archive.writestr('intake-manifest.json',gate.canonical(new))
  return dict(version=gate.VERSION,gate_sha256=gate.digest(Path(gate.__file__).read_bytes()),previous_manifest=self.old,manifest=new,
   scope=dict(files=hashes,changed_files=['autonomy.py']),production_mutations=0,bundle_sha256=gate.digest(self.bundle.read_bytes()),source_revision='b'*40,release_id='11111111-1111-4111-8111-111111111111')

 def test_exact_install_preserves_old_source_and_quota_state_and_keeps_routing_disabled(self):
  packet=self.packet();result=installer.install(packet,self.bundle,self.read,self.root,self.run)
  self.assertTrue(result['installed_files_verified']);self.assertFalse(result['routing_enabled'])
  self.assertTrue(result['requires_fresh_ready_heartbeat_before_resume']);self.assertTrue(self.current.is_symlink())
  self.assertEqual((self.current/'autonomy.py').read_bytes(),NEW.encode())
  self.assertEqual((self.root/'intake-releases'/self.old['source_binding']/'autonomy.py').read_bytes(),OLD.encode())
  self.assertEqual((self.root/'quota-state').read_text(),'original-cooldown')
  commands=[call.args[0] for call in self.run.call_args_list]
  self.assertEqual(commands[1],['systemctl','stop','jumpserve-intake.service'])
  self.assertEqual(commands[2],['systemctl','start','jumpserve-intake.service'])

 def test_active_routing_original_leases_or_dispatches_prevent_any_service_action(self):
  packet=self.packet()
  for blocked in ('runtime','leases','dispatches'):
   with self.subTest(blocked=blocked):
    self.read.side_effect=lambda name:[dict(enabled=True)] if name=='runtime' and blocked=='runtime' else [dict(enabled=False)] if name=='runtime' else ['original'] if name==blocked else []
    with self.assertRaises(ValueError):installer.install(packet,self.bundle,self.read,self.root,self.run)
    self.run.assert_not_called();self.assertFalse(self.current.is_symlink())

 def test_scientific_policy_edits_and_added_executables_fail_before_import_or_stop(self):
  for files in (dict(self.new_files,**{'policy.json':b'{"frozen":false}'}),dict(self.new_files,**{'subprocess.py':b'raise RuntimeError("never execute")'})):
   packet=self.packet(files)
   with self.assertRaises(ValueError):installer.install(packet,self.bundle,self.read,self.root,self.run)
   self.run.assert_not_called()

 def test_failed_start_restores_the_original_pointer_and_source(self):
  packet=self.packet();starts=[]
  def run(command,**kwargs):
   if command==['systemctl','start','jumpserve-intake.service']:
    starts.append(command)
    if len(starts)==1:raise subprocess.CalledProcessError(1,command)
  with self.assertRaises(subprocess.CalledProcessError):installer.install(packet,self.bundle,self.read,self.root,run)
  self.assertEqual(len(starts),2);self.assertEqual((self.current/'autonomy.py').read_bytes(),OLD.encode())
  self.assertEqual((self.root/'quota-state').read_text(),'original-cooldown')

 def test_existing_original_release_symlink_is_supported(self):
  previous=self.root/'intake-releases'/self.old['source_binding'];previous.parent.mkdir();self.current.rename(previous);self.current.symlink_to(previous,target_is_directory=True)
  result=installer.install(self.packet(),self.bundle,self.read,self.root,self.run)
  self.assertTrue(result['installed_files_verified']);self.assertEqual((previous/'autonomy.py').read_bytes(),OLD.encode())


if __name__=='__main__':unittest.main()
