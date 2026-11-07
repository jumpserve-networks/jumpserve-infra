"""Stage only the declared research Lambda files, verifying their exact hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re
import io,tarfile,urllib.request
ROOT=Path(__file__).resolve().parents[1]
def verified_files(backend,manifest,base_archive=None):
    overlay=manifest.get('source_overlay');base=None
    if overlay is not None:
        compositions={
            'captured-provider-overlay-v1':(['dispatch_recovery.py','policies/autonomous-repair-release-v1.json'],['tests/test_captured_provider_failures.py']),
            'auth-entrypoint-overlay-v1':(['dispatch_recovery.py','openclaw_auth.mjs','policies/autonomous-repair-release-v1.json'],['tests/test_captured_provider_failures.py','tests/openclaw_auth_entrypoint_test.mjs','tests/test_openclaw_auth_entrypoints.py']),
        }
        if (set(overlay)!={'version','base_revision','paths','tests'} or overlay.get('version') not in compositions
            or (overlay['paths'],overlay['tests'])!=compositions[overlay['version']]
            or not re.fullmatch('[a-f0-9]{40}',overlay['base_revision'])):
            raise ValueError('Unknown runtime source composition.')
        if base_archive is None:
            # Public exact-revision source only; no credentials or code execution.
            request=urllib.request.Request('https://codeload.github.com/jumpserve-networks/jumpserve-back-end/tar.gz/'+overlay['base_revision'],headers={'User-Agent':'JumpServe-Runtime-Source'})
            with urllib.request.urlopen(request,timeout=60) as response:base_archive=response.read(100000001)
            if len(base_archive)>100000000:raise ValueError('Frozen source archive exceeds its bound.')
        base=tarfile.open(fileobj=io.BytesIO(base_archive),mode='r:*')
    result={}
    try:
        for name,sha in manifest['files'].items():
            if not re.fullmatch(r'(?:[a-z_]+\.(?:py|mjs)|openclaw-builder-patch\.json|(?:plans|policies)/[a-z0-9-]+\.json|skills/network-environment-repair-v1/SKILL\.md)',name):raise ValueError('Unsafe runtime filename')
            if base is not None and name not in overlay['paths']:
                matches=[m for m in base.getmembers() if m.name.endswith('/research_workflow/'+name)]
                if len(matches)!=1 or not matches[0].isfile() or matches[0].size>2000000:raise ValueError('Exact plain frozen source member required: '+name)
                raw=base.extractfile(matches[0]).read(2000001)
            else:
                path=Path(backend)/'research_workflow'/name
                if any(p.is_symlink() for p in [path,*path.parents] if p.is_relative_to(Path(backend))):raise ValueError('Runtime source cannot follow links.')
                raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Runtime hash differs: '+name)
            result[name]=raw
    finally:
        if base is not None:base.close()
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backend',type=Path,default=ROOT.parent/'jumpserve-back-end');args=parser.parse_args()
    manifest=json.loads((ROOT/'research-workflow-runtime.json').read_text());destination=ROOT/'.runtime-backend/research_workflow'
    files=verified_files(args.backend,manifest)
    destination.mkdir(parents=True,exist_ok=True)
    # Remove only previously staged declared-runtime files that are no longer
    # in the manifest. Undeclared files cannot quietly enter a Lambda asset.
    for path in destination.rglob('*'):
        if path.is_file() and str(path.relative_to(destination)) not in manifest['files']:path.unlink()
    for name in manifest['files']:
        (destination/name).parent.mkdir(parents=True,exist_ok=True)
        (destination/name).write_bytes(files[name])
    print(json.dumps({'staged':list(manifest['files']),'destination':str(destination),'source_revision':manifest['source_revision'],'original_byte_verification':True}))
