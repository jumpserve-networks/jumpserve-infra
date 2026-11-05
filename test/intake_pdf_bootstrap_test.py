"""The installed intake environment must run its actual PDF child parser."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


class IntakePdfBootstrap(unittest.TestCase):
 def test_real_pinned_parser_subprocess_and_no_provider_call(self):
  code="import runpy,json,pathlib; m=runpy.run_path('assets/openclaw/verify-intake-pdf.py'); print(json.dumps(m['verify'](pathlib.Path('.runtime-intake'))))"
  result=subprocess.run([sys.executable,'-S','-B','-c',code],cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT/'.runtime-autonomy-python/python')),capture_output=True,text=True,timeout=45)
  self.assertEqual(result.returncode,0,result.stderr)
  receipt=json.loads(result.stdout);self.assertTrue(receipt['actual_parser_subprocess']);self.assertTrue(receipt['synthetic_control']);self.assertEqual(receipt['provider_calls'],0)

 def test_missing_pdf_package_fails_before_intake_can_start(self):
  code="import runpy,pathlib; runpy.run_path('assets/openclaw/verify-intake-pdf.py')['verify'](pathlib.Path('.runtime-intake'))"
  result=subprocess.run([sys.executable,'-S','-B','-c',code],cwd=ROOT,env=dict(os.environ,PYTHONPATH=''),capture_output=True,text=True,timeout=15)
  self.assertNotEqual(result.returncode,0);self.assertIn("No module named 'pypdf'",result.stderr)

 def test_service_requires_successful_parser_preflight(self):
  service=(ROOT/'assets/openclaw/jumpserve-intake.service').read_text()
  self.assertIn('ExecStartPre=/opt/jumpserve/python/bin/python -B /opt/jumpserve/intake-pdf-check.py',service)
  self.assertLess(service.index('ExecStartPre='),service.index('ExecStart='))


if __name__=='__main__':unittest.main()
