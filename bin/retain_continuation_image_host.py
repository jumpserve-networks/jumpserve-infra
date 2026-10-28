"""Retain the staged, verified image's original Docker bytes in private chunks."""
import gzip,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,time
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'research_workflow'))
import store
from workflow import canonical,digest
assert os.getuid()!=0 and os.environ['SUPABASE_URL']=='https://regphejnlvfpyokpniny.supabase.co'
prepared=json.loads((ROOT/'prepared.json').read_bytes());assert prepared['status']=='passed' and prepared['platform']=='linux/amd64'
image=prepared['image'];assert image.startswith('sha256:') and len(image)==71
assert not (ROOT/'image-archive.json').exists(),'Verify the recorded image archive rather than repeat it.'
out=ROOT/'image-original.tar.gz';assert not out.exists(),'Preserve and reconcile an earlier archive attempt.'
raw_hash=hashlib.sha256();raw_bytes=0;began=time.monotonic()
process=subprocess.Popen(['docker','image','save',image],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
    with gzip.open(out,'wb',compresslevel=1) as sink:
        while part:=process.stdout.read(1000000):
            raw_bytes+=len(part);assert raw_bytes<=2000000000 and time.monotonic()-began<600
            raw_hash.update(part);sink.write(part)
    assert process.wait(timeout=10)==0
finally:
    if process.poll() is None:process.kill();process.wait(timeout=10)
with tarfile.open(out,'r:gz') as archive:
    manifest=json.load(archive.extractfile('manifest.json'));assert len(manifest)==1
    config=archive.extractfile(manifest[0]['Config']).read(1000001);assert len(config)<=1000000 and digest(config)==image.removeprefix('sha256:')
def put(path,raw):
    url='/storage/v1/object/research-workflow-raw/'+path
    try:store.request(url,'POST',raw)
    except Exception:
        if store.request(url,raw=True)!=raw:raise
    restored=store.request(url,raw=True);assert restored==raw
    return dict(path=path,sha256=digest(raw),retrieved_sha256=digest(restored),bytes=len(raw))
chunks=[];compressed=hashlib.sha256()
with out.open('rb') as source:
    while part:=source.read(8000000):
        compressed.update(part)
        path='qualification/builder-continuation-v1/'+ROOT.name+'/image/'+image.removeprefix('sha256:')+'/'+str(len(chunks)).zfill(4)+'-'+digest(part)+'.part'
        chunks.append(put(path,part))
record=dict(version='builder-continuation-image-archive-v1',image=image,platform='linux/amd64',format='Ordered private chunks of gzip-compressed original Docker image save bytes',raw_tar_bytes=raw_bytes,raw_tar_sha256=raw_hash.hexdigest(),compressed_bytes=out.stat().st_size,compressed_sha256=compressed.hexdigest(),chunks=chunks,producer_sha256=digest(pathlib.Path(__file__).read_bytes()),wall_seconds=time.monotonic()-began,measured_charges_usd=None,scope='Each original chunk retrieved byte-for-byte and hash checked. Docker config hash matches the qualified image. This is artifact integrity, not full dependency source review.')
raw=canonical(record);pointer=put('qualification/builder-continuation-v1/'+ROOT.name+'/image-manifest-'+digest(raw)+'.json',raw)
(ROOT/'image-archive.json').write_bytes(canonical(dict(bucket='research-workflow-raw',public=False,image=image,**pointer)))
print(json.dumps(dict(status='retained',image=image,chunks=len(chunks),bytes=record['compressed_bytes'],manifest_sha256=digest(raw))))
