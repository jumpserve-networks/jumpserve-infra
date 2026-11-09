"""Archive this fixed release's evidence privately; no experiment or model calls."""
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bounded_release', ROOT / 'bin/autonomy-followup-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def main():
    if sys.argv[1:] != ['--upload']: raise RuntimeError('Only the fixed reviewed production evidence upload is supported')
    directory = ROOT / '.test-artifacts/autonomy-production-archive/v1'
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / 'receipt.json'
    if receipt_path.exists(): raise RuntimeError('Preserve this archive attempt; inspect it before any versioned correction')
    receipt = dict(status='running',started_at=dt.datetime.now(dt.timezone.utc).isoformat(),new_model_calls=0,new_experiments=0,measured_storage_charges_usd=None)
    def save(): receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    save()
    try:
        release.reviewed(); receipt['targets']=release.prior.guard.target(); save()
        frontend_status=release.prior.aws('amplify','get-job','--app-id','d24jvguj7brnkj','--branch-name','main','--job-id','117',
            '--query','job.{summary:summary.{jobId:jobId,commitId:commitId,status:status,startTime:startTime,endTime:endTime},steps:steps[].{name:stepName,status:status}}')
        stack_status=release.prior.aws('cloudformation','describe-stacks','--stack-name','JumpServeBenchmarkStack',
            '--query','Stacks[0].{stack:StackName,status:StackStatus,updated:LastUpdatedTime}')
        if frontend_status['summary']['commitId']!='7b8768198fb3970b120d92490b79a838a92e650e' or frontend_status['summary']['status']!='SUCCEED' or stack_status['status']!='UPDATE_COMPLETE':raise RuntimeError('Expected production release is not complete')
        for name,value in (('frontend-status.json',frontend_status),('stack-status.json',stack_status)):
            with (directory/name).open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
        entries={}
        def add(path, root=ROOT):
            if not path.is_file() or path.is_symlink(): raise RuntimeError('Only retained ordinary evidence files are allowed')
            entries[root.name+'/'+str(path.relative_to(root))]=path
        for name in ('frontend-status.json','stack-status.json'):add(directory/name)
        companion=json.loads((ROOT/'docs/autonomy-bounded-followups-production-validation-v1.json').read_bytes())
        for evidence in companion['evidence']:
            root=ROOT if evidence['repository']=='jumpserve-infra' else ROOT.parent/'jumpserve-front-end'
            path=ROOT.parent/evidence['path'];relative=path.resolve().relative_to(root.resolve())
            if relative.parts[0]!='.test-artifacts':raise RuntimeError('Companion evidence must be retained test artifacts')
            original=path.read_bytes()
            if sha(original)!=evidence['sha256'] or len(original)!=evidence['bytes']:raise RuntimeError('Companion evidence original bytes changed')
            add(path,root)
        for sub in ('v1','v2'):
            for path in (ROOT/'.test-artifacts/bounded-autonomy-production'/sub).iterdir():
                if path.is_file(): add(path)
        add(ROOT/'.test-artifacts/bounded-autonomy-production/security-v1.json')
        for base in (ROOT/'.test-artifacts/autonomy-followup-release').iterdir():
            for path in base.iterdir():
                if path.is_file() and (path.name in ('receipt.json','cdk.log','outputs.json','bounded-original.zip') or path.name.startswith('JumpServeBenchmarkStack-') and path.suffix=='.zip'):add(path)
        for name in ('20261020T002630488692Z','20261020T002818802027Z'):
            for path in (ROOT/'.test-artifacts/autonomy-release'/name).iterdir():
                if path.is_file() and (path.name=='receipt.json' or path.suffix=='.zip'):add(path)
        frontend=ROOT.parent/'jumpserve-front-end'
        for base in (frontend/'.test-artifacts/autonomy-release-production').iterdir():
            for path in base.iterdir():
                if path.is_file() and path.suffix in ('.json','.png'):add(path,frontend)
        for name in ('autonomy-bounded-followups-production-validation-v1.md','autonomy-bounded-followups-production-validation-v1.json','autonomy-bounded-followups-release-validation-v1.md','autonomy-bounded-followups-release-protocol-v1.md'):
            add(ROOT/'docs'/name)
        for name in ('verify-bounded-autonomy-release.py','autonomy-followup-release.py','archive-autonomy-production-evidence.py'):add(ROOT/'bin'/name)
        manifest=[]; buffer=io.BytesIO();total=0
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name,path in sorted(entries.items()):
                raw=path.read_bytes();total+=len(raw)
                if total>100000000:raise RuntimeError('Original production evidence exceeds 100 MB bound')
                manifest.append(dict(path=name,sha256=sha(raw),bytes=len(raw)))
                entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(entry,raw)
            archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
        raw=buffer.getvalue()
        if len(raw)>32000000:raise RuntimeError('Compressed production evidence exceeds 32 MB bound')
        (directory/'original-evidence.zip').write_bytes(raw)
        key=release.prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
        path='release-verification/autonomy-followups-production-20261020/'+sha(raw)+'.zip'
        url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path
        headers={'apikey':key,'Authorization':'Bearer '+key}
        if release.prior.admin.query("select public from storage.buckets where id='research-workflow-raw'")!=[{'public':False}]:raise RuntimeError('Archive bucket must be private')
        try:
            with release.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=60) as response:response.read(1000)
        except urllib.error.HTTPError as error:
            if error.code!=409:raise RuntimeError('Private production archive upload failed: HTTP '+str(error.code)) from None
        with release.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retrieved=response.read(32000001)
        if retrieved!=raw or sha(retrieved)!=sha(raw):raise RuntimeError('Stored original archive bytes differ after retrieval')
        with zipfile.ZipFile(io.BytesIO(retrieved)) as archive:
            if json.loads(archive.read('manifest.json'))!=manifest:raise RuntimeError('Stored manifest differs')
            for member in manifest:
                content=archive.read(member['path'])
                if len(content)!=member['bytes'] or sha(content)!=member['sha256']:raise RuntimeError('Stored original member hash differs')
        public=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
        try:
            with release.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':public,'Authorization':'Bearer '+public}),timeout=20) as response:response.read(1)
        except urllib.error.HTTPError as error:status=error.code
        if status not in (400,401,403,404):raise RuntimeError('Private production evidence is anonymously accessible')
        receipt.update(status='complete',bucket='research-workflow-raw',path=path,sha256=sha(raw),bytes=len(raw),original_bytes=total,files=len(manifest),manifest=manifest,
            retrieved_hash_verified=True,all_member_hashes_verified=True,anonymous_status=status)
    except Exception as error:
        receipt.update(status='failed',reason=str(error));raise
    finally:
        receipt['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();save()
        print(json.dumps(dict(status=receipt['status'],path=str(receipt_path),sha256=receipt.get('sha256'),files=receipt.get('files'))))
    output=ROOT/'docs/autonomy-bounded-followups-production-artifacts-v1.json'
    with output.open('x') as stream:stream.write(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
