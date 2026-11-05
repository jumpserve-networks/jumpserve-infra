"""Prepare exact local intake assets; no cloud calls, provider calls or deployment."""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backend',type=Path,default=ROOT.parent/'jumpserve-back-end');args=parser.parse_args();BACK=args.backend
manifest=json.loads((ROOT/'intake-worker-runtime.json').read_bytes())
if manifest.get('version')!='warm-intake-v1' or not re.fullmatch('[a-f0-9]{40}',manifest.get('source_revision','')):raise ValueError('Pinned intake revision required.')
if hashlib.sha256(json.dumps(manifest['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()!=manifest['source_binding']:raise ValueError('Pinned intake source binding differs.')
OUT=ROOT/'.runtime-intake';OUT.mkdir(exist_ok=True)
files={}
for name,sha in manifest['files'].items():
 relative=Path(name)
 if relative.is_absolute() or '..' in relative.parts:raise ValueError('Relative declared source required.')
 source=BACK/'research_workflow'/relative
 if not source.is_file() or source.is_symlink():raise ValueError('Plain intake runtime source required.')
 raw=source.read_bytes();name=relative.as_posix();files[name]=hashlib.sha256(raw).hexdigest()
 if files[name]!=sha:raise ValueError('Pinned intake source differs: '+name)
 target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
for name in ('intake_worker.py','intake_parallel.py','openclaw_runtime.py'):
 if name not in files:raise ValueError('Incomplete warm intake runtime.')
for path in OUT.rglob('*'):
 if path.is_file() and path.relative_to(OUT).as_posix() not in files and path.name!='intake-manifest.json':path.unlink()
(OUT/'intake-manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
print(json.dumps(dict(version=manifest['version'],files=len(files),source_binding=manifest['source_binding'],deployed=False,provider_calls=0)))
