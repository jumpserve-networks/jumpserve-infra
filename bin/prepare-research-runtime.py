"""Stage only the declared research Lambda files, verifying their exact hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backend',type=Path,default=ROOT.parent/'jumpserve-back-end');args=parser.parse_args()
    manifest=json.loads((ROOT/'research-workflow-runtime.json').read_text());destination=ROOT/'.runtime-backend/research_workflow'
    for name,sha in manifest['files'].items():
        if Path(name).name!=name or not name.endswith('.py'):raise ValueError('Unsafe runtime filename')
        path=args.backend/'research_workflow'/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('Runtime hash differs: '+name)
    destination.mkdir(parents=True,exist_ok=True)
    for name in manifest['files']:shutil.copyfile(args.backend/'research_workflow'/name,destination/name)
    print(json.dumps({'staged':list(manifest['files']),'destination':str(destination),'source_revision':manifest['source_revision'],'original_byte_verification':True}))
