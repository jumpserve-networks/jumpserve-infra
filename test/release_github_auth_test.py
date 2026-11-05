"""Live release revision guards authenticate reads without changing source checks."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def load(name):
 spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'bin'/name);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class GitHubReleaseAuth(unittest.TestCase):
 def test_infrastructure_exact_main_guard_uses_only_workflow_read_token(self):
  module=load('platform-release-input.py');seen=[]
  def open(request,**kwargs):seen.append(request);return io.BytesIO(json.dumps({'object':{'sha':'a'*40}}).encode())
  env=dict(PLATFORM_COMPONENT='infrastructure',PLATFORM_REPOSITORY='jumpserve-networks/jumpserve-infra',PLATFORM_REVISION='a'*40,PLATFORM_OPERATION_ID='11111111-1111-4111-8111-111111111111',GH_TOKEN='synthetic-workflow-read-token')
  with patch.dict(os.environ,env),patch.object(module.urllib.request,'urlopen',open):module.inputs()
  self.assertEqual(seen[0].get_header('Authorization'),'Bearer synthetic-workflow-read-token')
  env['PLATFORM_REVISION']='b'*40
  with patch.dict(os.environ,env),patch.object(module.urllib.request,'urlopen',open):
   with self.assertRaises(ValueError):module.inputs()

 def test_research_main_read_uses_the_same_narrow_workflow_credential(self):
  module=load('research-runtime-release.py');seen=[]
  def open(request,**kwargs):seen.append(request);return io.BytesIO(json.dumps({'object':{'sha':'a'*40}}).encode())
  with patch.dict(os.environ,GH_TOKEN='synthetic-read-token'),patch.object(module.urllib.request,'urlopen',open):self.assertEqual(module.public_main('jumpserve-back-end'),'a'*40)
  self.assertEqual(seen[0].get_header('Authorization'),'Bearer synthetic-read-token')

 def test_workflows_bind_tokens_to_trusted_revision_checks(self):
  for name in ('platform-release.yml','research-runtime-release.yml','supervisor-runtime-release.yml'):
   text=(ROOT/'.github/workflows'/name).read_text();self.assertIn('GH_TOKEN: ${{ github.token }}',text);self.assertIn('contents: read',text)
  source=(ROOT/'bin/supervisor-runtime-release.py').read_text();self.assertIn("headers['Authorization']='Bearer '+token",source)
  self.assertIn("if main!=revision:raise ValueError",source)


if __name__=='__main__':unittest.main()
