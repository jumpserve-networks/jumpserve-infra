"""Build the fixed pure-Python PDF layer; never accepts commands or packages."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def main():
 if len(sys.argv)!=1:raise ValueError('Fixed dependency preparation only.')
 wheels=ROOT/'.test-artifacts/autonomy-dependencies';wheels.mkdir(parents=True,exist_ok=True)
 lock=json.loads((ROOT/'autonomy-pdf-runtime.json').read_bytes())
 wheel=wheels/lock['wheel']
 if not wheel.exists():
  subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--no-deps','--disable-pip-version-check','--dest',str(wheels),lock['requirement']],check=True,timeout=120)
 raw=wheel.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=lock['sha256']:raise ValueError('Original dependency wheel SHA256 differs; retain it and investigate before use.')
 target=ROOT/'.runtime-autonomy-python/python';target.mkdir(parents=True,exist_ok=True)
 files={}
 with zipfile.ZipFile(wheel) as archive:
  for name in archive.namelist():
   if name.endswith('/'):continue
   if name.startswith('/') or '..' in Path(name).parts:raise ValueError('Unsafe wheel member.')
   data=archive.read(name);path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
   files[name]=hashlib.sha256(data).hexdigest()
 (target.parent/'manifest.json').write_text(json.dumps(dict(lock,files=files),indent=2)+'\n')
 print(json.dumps(dict(wheel_sha256=lock['sha256'],files=len(files),destination=str(target),original_byte_verification=True)))
if __name__=='__main__':main()
