"""Export nonprivate IPv6 protocols, prompt reviews, migrations and software validation."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT.parent/'jumpserve-front-end/public/module/ipv6-dns-study'
def main():
 members={}
 for folder,pattern in (('docs/ipv6-study-validation','*'),('test','ipv6-evaluation-cases-v*.json'),('database','*ipv6*.sql'),('database','seed-ipv6-agent-prompt-v*.json')):
  for p in sorted((ROOT/folder).glob(pattern)):
   if p.is_file() and p.suffix in ('.json','.png','.sql'):members[str(p.relative_to(ROOT))]=p.read_bytes()
 for p in (ROOT/'docs/ipv6-study-chat.md',):members[str(p.relative_to(ROOT))]=p.read_bytes()
 manifest={n:dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)) for n,raw in members.items()};members['member-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
 OUT.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(OUT/'validation.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for name,raw in sorted(members.items()):
   info=zipfile.ZipInfo(name,(2026,10,6,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw,compresslevel=9)
 p=OUT/'validation.zip';(OUT/'validation-manifest.json').write_text(json.dumps({p.name:dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,members=len(manifest),scope='Predeployment validation archive. Current deployed status is the public api/release response.')},indent=2)+'\n')
 print(json.dumps({p.name:dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,members=len(manifest))}))
if __name__=='__main__':main()
