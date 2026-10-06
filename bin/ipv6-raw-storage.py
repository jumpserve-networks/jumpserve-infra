"""Private chunked preservation; verify retrieved bundles, chunks and original file hashes."""
import argparse,gzip,hashlib,importlib.util,io,json,sys,tarfile
from datetime import datetime,timezone
from pathlib import Path
import boto3,httpx
R=Path(__file__).resolve().parents[1];S=R.parent/'jumpserve-back-end/experiments/ipv6_dns';URL='https://regphejnlvfpyokpniny.supabase.co'
spec=importlib.util.spec_from_file_location('study',R/'bin/ipv6-study-database.py');study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)
def main():
 parser=argparse.ArgumentParser(description=__doc__);modes=parser.add_mutually_exclusive_group();modes.add_argument('--release-evidence',action='store_true');modes.add_argument('--amendment',action='store_true');args=parser.parse_args()
 study.targets();boto3.setup_default_session(profile_name='jumpserve',region_name='us-east-1');sys.path.insert(0,str(R/'agent'));from database import Database
 db=Database(URL);p=S/('evidence/assessment-v2.json' if args.amendment else 'evidence/assessment-v1.json');d=json.loads(p.read_text());sha=hashlib.sha256(p.read_bytes()).hexdigest();version='release-v1' if args.release_evidence else 'assessment-v2' if args.amendment else 'assessment-v1'
 out=R/'docs/ipv6-study-validation'/f'storage-{version}.json'
 if out.exists():raise RuntimeError('Preserve previous storage report before any writes')
 records=d['manifest']+[dict(path=str(p.relative_to(S)),sha256=sha,bytes=p.stat().st_size)]
 if args.release_evidence:records=[dict(path=str(p.relative_to(S)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted((S/'evidence/release-v1').rglob('*')) if p.is_file()]
 if args.amendment:
  old={m['path'] for m in json.loads((R/'docs/ipv6-study-validation/storage-assessment-v1.json').read_text())['original_files']}
  records=[m for m in records if m['path'] not in old]
 if not records:raise RuntimeError('No original files to preserve')
 groups=[[]];size=0
 for m in records:
  raw=(S/m['path']).read_bytes()
  if hashlib.sha256(raw).hexdigest()!=m['sha256']:raise RuntimeError('Original bytes changed')
  for offset in range(0,len(raw) or 1,16_000_000):
   chunk=raw[offset:offset+16_000_000];part=dict(original_path=m['path'],offset=offset,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest(),archive_name=m['path']+f'.chunk-{offset}')
   if size+len(chunk)>24_000_000 and groups[-1]:groups.append([]);size=0
   groups[-1].append(part);size+=len(chunk)
 bundles=[];digests={m['path']:hashlib.sha256() for m in records};offsets={m['path']:0 for m in records}
 with httpx.Client(timeout=120,headers=db.headers()) as client:
  for i,group in enumerate(groups):
   buffer=io.BytesIO()
   with gzip.GzipFile(fileobj=buffer,mode='wb',mtime=0) as zipped:
    with tarfile.open(fileobj=zipped,mode='w') as archive:
     for m in group:
      with (S/m['original_path']).open('rb') as f:f.seek(m['offset']);chunk=f.read(m['bytes'])
      info=tarfile.TarInfo(m['archive_name']);info.size=len(chunk);info.mtime=0;archive.addfile(info,io.BytesIO(chunk))
   raw=buffer.getvalue();digest=hashlib.sha256(raw).hexdigest();key=f'{version}/bundle-{i}-{digest}.tar.gz'
   prior=study.admin.query('select sha256 from ipv6_study_artifacts where id='+study.admin.literal(f'{version}-raw-bundle-{i}'))
   if prior and prior[0]['sha256']!=digest:raise RuntimeError('Preserve prior bundle; version changed inputs separately')
   response=client.post(f'{URL}/storage/v1/object/ipv6-study-raw/{key}',content=raw,headers={'Content-Type':'application/gzip','x-upsert':'false'})
   if response.status_code not in (200,201,400,409):response.raise_for_status()
   retrieved=client.get(f'{URL}/storage/v1/object/authenticated/ipv6-study-raw/{key}');retrieved.raise_for_status()
   if hashlib.sha256(retrieved.content).hexdigest()!=digest:raise RuntimeError('Bundle hash differs')
   with tarfile.open(fileobj=io.BytesIO(retrieved.content),mode='r:gz') as archive:
    if len(archive.getmembers())!=len(group):raise RuntimeError('Chunk coverage differs')
    for m in group:
     chunk=archive.extractfile(m['archive_name']).read();path=m['original_path']
     if hashlib.sha256(chunk).hexdigest()!=m['sha256'] or offsets[path]!=m['offset']:raise RuntimeError('Chunk identity/order differs')
     digests[path].update(chunk);offsets[path]+=len(chunk)
   b=dict(id=f'{version}-raw-bundle-{i}',sha256=digest,byte_count=len(raw),manifest=group,storage_path=key,payload={'chunk_round_trip_verified':True});bundles.append(b);study.insert('artifacts',[b]);print('Verified bundle',i,'chunks',len(group),'bytes',len(raw),flush=True)
 for m in records:
  if offsets[m['path']]!=m['bytes'] or digests[m['path']].hexdigest()!=m['sha256']:raise RuntimeError('Reassembled original hash differs')
 manifest=dict(id=f'ipv6-storage-{version}',at=datetime.now(timezone.utc).isoformat(),project=study.admin.PROJECT_REF,visibility='private service-role-only',original_files=records,bundles=bundles,files=len(records),original_bytes=sum(m['bytes'] for m in records),stored_bytes=sum(b['byte_count'] for b in bundles),assessment_sha256=sha,round_trip_verified=True,charges_usd=None,limitations='Storage/transfer requests and charges not reconciled. No copyrighted full source redistribution.')
 out.write_text(json.dumps(manifest,indent=2)+'\n');public={f'{version}_raw_storage':dict(files=len(records),original_bytes=manifest['original_bytes'],stored_bytes=manifest['stored_bytes'],manifest_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),round_trip_verified=True)}
 study.admin.query('update ipv6_study_meta set provenance=provenance||'+study.admin.literal(json.dumps(public))+"::jsonb where id='assessment-v2'",read_only=False);print(json.dumps(public))
if __name__=='__main__':main()
