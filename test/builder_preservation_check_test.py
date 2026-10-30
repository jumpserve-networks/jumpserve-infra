"""Exposed metadata-decoder regressions; no models, cloud calls or science."""
import base64,hashlib,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'bin'))
from builder_preservation_check import proof

class Preservation(unittest.TestCase):
 def test_identity_and_encoded_original_bytes_are_equivalent(self):
  raw=b'{ "runtime": [1,2], "zero": 0, "missing": null }\n'
  encoded=json.dumps(dict(original_bytes_base64=base64.b64encode(raw).decode(),original_sha256=hashlib.sha256(raw).hexdigest())).encode()
  self.assertEqual(proof(raw,raw)['encoding'],'identity');self.assertEqual(proof(encoded,raw)['encoding'],'json-base64-sha256')
 def test_bad_digest_or_changed_original_is_rejected(self):
  raw=b'original\n';value=dict(original_bytes_base64=base64.b64encode(raw).decode(),original_sha256=hashlib.sha256(raw).hexdigest())
  for altered in [dict(value,original_sha256='0'*64),dict(value,original_bytes_base64=base64.b64encode(b'changed').decode()),dict(value,original_bytes_base64=value['original_bytes_base64']+'!')]:self.assertIsNone(proof(json.dumps(altered).encode(),raw))
 def test_unsupported_notes_are_not_preservation(self):
  for raw in (b'null',b'[]',b'{"original_sha256":"claimed"}',b'not json'):self.assertIsNone(proof(raw,b'original'))

if __name__=='__main__':unittest.main()
