"""Stage the declared private OpenClaw worker dependency inputs; no deployment."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
source=ROOT.parent/'jumpserve-back-end/openclaw_worker'
destination=ROOT/'.runtime-openclaw'
lock=json.loads((ROOT/'openclaw-worker-runtime.json').read_bytes())
for name,sha in lock['files'].items():
 path=(source/name) if name in ('package.json','package-lock.json','requirements.txt') else ROOT/'assets/openclaw'/name
 if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('OpenClaw dependency input differs: '+name)
 destination.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination/name)
print(json.dumps(dict(staged=list(lock['files']),deployment=False)))
