"""Exercise the installed parser subprocess before intake becomes available."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile


def verify(runtime=Path('/opt/jumpserve/intake-runtime')):
 sys.path.insert(0,str(runtime))
 import intake
 import pypdf
 if pypdf.__version__!='6.19.0':raise ValueError('Pinned intake PDF dependency differs.')
 writer=pypdf.PdfWriter();writer.add_blank_page(width=200,height=200)
 buffer=io.BytesIO();writer.write(buffer);original=buffer.getvalue()
 with tempfile.TemporaryDirectory(prefix='jumpserve-intake-pdf-check-') as folder:
  source=Path(folder)/'synthetic.pdf';output=Path(folder)/'text.json';source.write_bytes(original)
  intake.text_packet(source,output);packet=json.loads(output.read_bytes())
 if packet['original_sha256']!=hashlib.sha256(original).hexdigest() or packet['tool_version']!='6.19.0' or len(packet['pages'])!=1 or packet['pages'][0]['status']!='missing-text-layer':
  raise ValueError('Installed intake PDF subprocess verification differs.')
 return dict(passed=True,parser='pypdf',version=pypdf.__version__,actual_parser_subprocess=True,synthetic_control=True,provider_calls=0)


if __name__=='__main__':
 if len(sys.argv)!=1:raise SystemExit('This fixed installed parser check accepts no arguments.')
 print(json.dumps(verify()))
