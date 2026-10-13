"""Freeze the verified release's code and evidence for private preservation."""
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
OUT=BACK/'experiments/ipv6_dns/evidence/release-v1'

def git(root,*args):
 return subprocess.check_output(['git',*args],cwd=root,text=True).strip()

def main():
 if OUT.exists():raise RuntimeError('Preserve the frozen release; use a new version')
 report=json.loads((ROOT/'docs/ipv6-study-validation/production-validation-v1.json').read_text())
 if not report['release_blocking_checks_passed'] or report['software_status']!='deployed and production verified':raise RuntimeError('Release verification incomplete')
 paths={
  'infrastructure':(ROOT,set(git(ROOT,'diff-tree','--no-commit-id','--name-only','-r','b5aa090').splitlines())),
  'frontend':(FRONT,set(git(FRONT,'diff-tree','--no-commit-id','--name-only','-r','2ace33b2f5db86e748b52ed67f51de497fddb378').splitlines())),
  'experiments':(BACK,set(git(BACK,'ls-files','experiments/ipv6_dns').splitlines()))
 }
 paths['infrastructure'][1].update(str(p.relative_to(ROOT)) for p in (ROOT/'docs/ipv6-study-validation').glob('*') if p.is_file())
 paths['infrastructure'][1].add('bin/export-ipv6-release.py')
 manifest=[]
 for label,(root,names) in paths.items():
  for name in sorted(names):
   source=root/name
   if not source.is_file() or source.is_symlink():raise RuntimeError('Expected regular source file: '+name)
   target=OUT/label/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
   raw=target.read_bytes();manifest.append(dict(path=str(target.relative_to(OUT)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
 document=dict(id='ipv6-release-bundle-v1',files=manifest,source_revisions={label:git(root,'rev-parse','HEAD') for label,(root,_) in paths.items()},infrastructure_branch=git(ROOT,'branch','--show-current'),scope='Working bytes frozen after production checks; manifest hashes identify any validation/report follow-ups beyond the recorded commit. Original paper, literature and author data remain in their prior private bundles.')
 (OUT/'manifest.json').write_text(json.dumps(document,indent=2)+'\n')
 print(json.dumps(dict(files=len(manifest),bytes=sum(m['bytes'] for m in manifest),manifest_sha256=hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest())))

if __name__=='__main__':main()
