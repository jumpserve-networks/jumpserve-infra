"""Preserve ReliableSketch original bytes privately and verify every member after retrieval."""
import argparse,hashlib,importlib.util,io,json,os,sys,tarfile
from datetime import datetime,timezone
from pathlib import Path
import boto3,httpx
R=Path(__file__).resolve().parents[1];S=R.parent/'jumpserve-back-end/experiments/reliable_sketch';URL='https://regphejnlvfpyokpniny.supabase.co'
spec=importlib.util.spec_from_file_location('admin',R/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--release-evidence",action="store_true");args=parser.parse_args()
 boto3.setup_default_session(profile_name='jumpserve',region_name='us-east-1')
 if boto3.client('sts').get_caller_identity()['Account']!='395567831870' or admin.PROJECT_REF!='regphejnlvfpyokpniny' or json.loads((R/'cdk.json').read_text())['context']['supabaseUrl']!=URL:raise RuntimeError('Target identity mismatch')
 sys.path.insert(0,str(R/'agent'));from database import Database
 db=Database(URL);path=S/'evidence/assessment-v1.json';data=json.loads(path.read_text());assessment_sha=hashlib.sha256(path.read_bytes()).hexdigest()
 records=data['manifest']+[dict(path='evidence/assessment-v1.json',sha256=assessment_sha,bytes=path.stat().st_size)]
 if args.release_evidence:records=[dict(path=str(p.relative_to(S)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted((S/'evidence/release-v1').rglob('*')) if p.is_file()]
 version='release-v1' if args.release_evidence else 'assessment-v1'
 groups=[[]];size=0
 for m in records:
  if hashlib.sha256((S/m['path']).read_bytes()).hexdigest()!=m['sha256']:raise RuntimeError('Original bytes changed')
  if size+m['bytes']>24_000_000 and groups[-1]:groups.append([]);size=0
  groups[-1].append(m);size+=m['bytes']
 bundles=[]
 with httpx.Client(timeout=120,headers=db.headers()) as client:
  for i,group in enumerate(groups):
   buffer=io.BytesIO()
   with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
    for m in group:
     raw=(S/m['path']).read_bytes();info=tarfile.TarInfo(m['path']);info.size=len(raw);info.mtime=0;archive.addfile(info,io.BytesIO(raw))
   raw=buffer.getvalue();sha=hashlib.sha256(raw).hexdigest();key=f'{version}/bundle-{i}-{sha}.tar.gz'
   response=client.post(f'{URL}/storage/v1/object/reliable-study-raw/{key}',content=raw,headers={'Content-Type':'application/gzip','x-upsert':'false'})
   if response.status_code not in (200,201,400,409):response.raise_for_status()
   retrieved=client.get(f'{URL}/storage/v1/object/authenticated/reliable-study-raw/{key}');retrieved.raise_for_status()
   if hashlib.sha256(retrieved.content).hexdigest()!=sha:raise RuntimeError('Storage bundle hash differs')
   with tarfile.open(fileobj=io.BytesIO(retrieved.content),mode='r:gz') as archive:
    if len(archive.getmembers())!=len(group):raise RuntimeError('Storage member coverage differs')
    for m in group:
     if hashlib.sha256(archive.extractfile(m['path']).read()).hexdigest()!=m['sha256']:raise RuntimeError('Stored original bytes differ')
   bundles.append(dict(id=f'{version}-raw-bundle-{i}',sha256=sha,byte_count=len(raw),manifest=group,storage_path=key,payload={'round_trip_verified':True,'members':len(group)}));print('Verified bundle',i,'members',len(group),'bytes',len(raw),flush=True)
   admin.query('insert into reliable_study_artifacts select * from jsonb_populate_record(null::reliable_study_artifacts,'+admin.literal(json.dumps(bundles[-1]))+'::jsonb) on conflict(id) do nothing',read_only=False)
 manifest=dict(id='reliable-storage-v1',at=datetime.now(timezone.utc).isoformat(),project=admin.PROJECT_REF,visibility='private service-role-only',bundles=bundles,files=len(records),original_bytes=sum(m['bytes'] for m in records),stored_bytes=sum(m['byte_count'] for m in bundles),assessment_sha256=assessment_sha,charges_usd=None,limitations='Storage/transfer requests and charges not reconciled. No raw author bytes publicly redistributed.')
 out=R/'docs/reliable-study-validation';out.mkdir(parents=True,exist_ok=True);(out/('release-storage-manifest.json' if args.release_evidence else 'storage-manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
 public=dict(raw_storage_verified_files=len(records),raw_storage_verified_bytes=manifest['original_bytes'],raw_storage_stored_bytes=manifest['stored_bytes'],raw_storage_manifest_sha256=hashlib.sha256((out/('release-storage-manifest.json' if args.release_evidence else 'storage-manifest.json')).read_bytes()).hexdigest())
 if args.release_evidence:public={'release_'+k:v for k,v in public.items()}
 admin.query('update reliable_study_meta set provenance=provenance||'+admin.literal(json.dumps(public))+"::jsonb where id='assessment-v1'",read_only=False)
 print(json.dumps(public))
if __name__=='__main__':main()
