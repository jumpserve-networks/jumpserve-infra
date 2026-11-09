"""Stage the separately pinned HTTP API without changing experiment workers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]

def prepare(backend: Path, root: Path = ROOT):
    manifest = json.loads((root/'research-api-runtime.json').read_bytes())
    destination = root/'.runtime-api/research_workflow'
    for name, expected in manifest['files'].items():
        if not re.fullmatch(r'(?:[a-z_]+\.(?:py|mjs)|openclaw-builder-patch\.json|(?:plans|policies)/[a-z0-9-]+\.json|skills/network-environment-repair-v1/SKILL\.md)', name):
            raise ValueError('Unsafe API runtime filename.')
        if hashlib.sha256((backend/'research_workflow'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('API runtime hash differs: '+name)
    destination.mkdir(parents=True, exist_ok=True)
    for file in destination.rglob('*'):
        if file.is_file() and str(file.relative_to(destination)) not in manifest['files']: file.unlink()
    for name in manifest['files']:
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backend/'research_workflow'/name, target)
    return dict(source_revision=manifest['source_revision'], files=len(manifest['files']), destination=str(destination))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path, default=ROOT.parent/'jumpserve-back-end')
    args = parser.parse_args()
    print(json.dumps(prepare(args.backend)))

if __name__ == '__main__': main()
