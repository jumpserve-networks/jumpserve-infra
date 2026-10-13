"""Preserve and round-trip-check only pinned HTTP/2 original bytes in verified JumpServe."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import boto3
import httpx

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT.parent/'jumpserve-back-end/experiments/http2_compliance'
PROJECT='https://regphejnlvfpyokpniny.supabase.co'
BUCKET='http2-study-artifacts'
CAMPAIGN='http2-compliance-artifact-v2'

def main():
    boto3.setup_default_session(profile_name='jumpserve',region_name='us-east-1')
    assert boto3.client('sts').get_caller_identity()['Account']=='395567831870','Wrong AWS account'
    assert json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']==PROJECT,'Wrong project'
    spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
    assert admin.PROJECT_REF=='regphejnlvfpyokpniny'
    sys.path.insert(0,str(ROOT/'agent'))
    from database import Database
    db=Database(PROJECT)
    campaigns=db.get('http2_study_campaigns',params={'id':'eq.'+CAMPAIGN,'select':'id,protocol_sha256,analysis_sha256'})
    assembled=json.loads((STUDY/'results/assessment-v3.json').read_text())
    assert len(campaigns)==1 and campaigns[0]['protocol_sha256']==assembled['campaign']['protocol_sha256']
    assert campaigns[0]['analysis_sha256']==assembled['campaign']['analysis_sha256'],'Changed analysis'
    repository=STUDY/'sources/HTTP2-Compliance-Tests'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repository,text=True).strip()=='03bcd5d88c98cb82fac0c2afb626bb16ec2fa402'
    originals=[]
    for row in assembled['sources']:
        if not row.get('sha256'):continue
        n=row['reference_number']
        candidates=[STUDY/'sources/main-paper.pdf'] if n==0 else [STUDY/'sources'/f'ref-{n:02}.{ext}' for ext in ('pdf','web','txt')]
        path=next(p for p in candidates if p.is_file())
        originals.append(('source-'+str(n),path,row['sha256']))
    for row in assembled['artifacts']:
        path=repository/row['source_path']
        assert repository.resolve() in path.resolve().parents,'Invalid original path'
        originals.append((row['id'],path,row['sha256']))
    # Validate every byte hash before performing any storage mutation.
    for identifier,path,digest in originals:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,('Original hash differs',identifier)
    admin.query((ROOT/'database/202610040010_http2_raw_storage.sql').read_text(),read_only=False)
    headers=db.headers();records=[]
    with httpx.Client(timeout=60,headers=headers) as client:
        for identifier,path,digest in originals:
            key=f'{CAMPAIGN}/{identifier}/{digest}{path.suffix}'
            url=f'{PROJECT}/storage/v1/object/{BUCKET}/{key}'
            raw=path.read_bytes()
            response=client.post(url,content=raw,headers={'Content-Type':'application/octet-stream','x-upsert':'false'})
            if response.status_code not in (200,201,400,409):response.raise_for_status()
            # A duplicate/400 must still round-trip identical bytes, or fail.
            retrieved=client.get(f'{PROJECT}/storage/v1/object/authenticated/{BUCKET}/{key}');retrieved.raise_for_status()
            assert hashlib.sha256(retrieved.content).hexdigest()==digest,('Stored bytes differ',identifier)
            records.append(dict(id=identifier,bucket=BUCKET,object_path=key,sha256=digest,bytes=len(raw),original_path=str(path.relative_to(STUDY)),round_trip='pass'))
    assert len(records)==97,'Unexpected original-file coverage'
    prior=db.get('http2_study_artifacts',params={'campaign_id':'eq.'+CAMPAIGN,'id':'eq.original-byte-storage-v1','select':'payload,sha256'})
    manifest=dict(version='http2-original-byte-storage-v1',stored_at=datetime.now(timezone.utc).isoformat(),project='regphejnlvfpyokpniny',visibility='private, service-role only',files=records,total_bytes=sum(r['bytes'] for r in records),source_files=40,author_json_files=57,limitation='Storage charges and transfer requests are not reconciled billing. Unavailable full texts remain unavailable.')
    if prior:
        assert len(prior)==1 and prior[0]['payload']['files']==records,'Stored manifest differs'
        # Rechecking byte copies must not replace the original storage timestamp
        # or point public provenance at a manifest that was never persisted.
        # JSONB can reorder keys, so recover the original serialization too.
        candidates=(ROOT/'.test-artifacts/http2-original-storage.json',ROOT/'docs/http2-validation/original-storage-manifest.json')
        saved=next((p for p in candidates if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==prior[0]['sha256']),None)
        assert saved is not None,'Original manifest bytes unavailable; do not replace its identity'
        manifest=json.loads(saved.read_text())
        assert manifest==prior[0]['payload'],'Original manifest payload differs'
    raw=(json.dumps(manifest,indent=2)+'\n').encode();digest=hashlib.sha256(raw).hexdigest()
    if prior:assert digest==prior[0]['sha256'],'Stored manifest hash differs'
    directory=ROOT/'.test-artifacts';directory.mkdir(exist_ok=True);(directory/'http2-original-storage.json').write_bytes(raw)
    payload={'campaign_id':CAMPAIGN,'id':'original-byte-storage-v1','sha256':digest,'source_path':'private-storage-manifest-v1.json','byte_count':len(raw),'payload':manifest}
    admin.query('insert into http2_study_artifacts select * from jsonb_populate_record(null::http2_study_artifacts,'+admin.literal(json.dumps(payload))+"::jsonb) on conflict(campaign_id,id) do nothing",read_only=False)
    admin.query("update http2_study_campaigns set provenance=provenance||"+admin.literal(json.dumps({'raw_storage_manifest_sha256':digest,'raw_storage_files':len(records),'raw_storage_bytes':manifest['total_bytes']}))+"::jsonb where id="+admin.literal(CAMPAIGN),read_only=False)
    print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2))

if __name__=='__main__':main()
