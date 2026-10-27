"""Retain only the exact qualified image in bounded private Storage chunks."""
import gzip,hashlib,json,pathlib,shutil,subprocess,sys,time,tarfile
root=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(root/'research_workflow'))
import store
from workflow import canonical,digest
image=(root/'image-id.txt').read_text().strip();assert image=='sha256:ef390fb5c927fc11773da987e96c3264b618118fd39b8715139cf977b1b4320a'
out=root/'image-retention';out.mkdir(exist_ok=False)
assert shutil.disk_usage(out).free>3000000000
started=time.monotonic();raw_hash=hashlib.sha256();raw_bytes=0;archive=out/'original-image.tar.gz'
process=subprocess.Popen(['docker','image','save',image],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
 with gzip.open(archive,'wb',compresslevel=1) as sink:
  while True:
   part=process.stdout.read(1000000)
   if not part:break
   raw_bytes+=len(part);assert raw_bytes<=2000000000 and time.monotonic()-started<600
   raw_hash.update(part);sink.write(part)
 assert process.wait(timeout=10)==0
finally:
 if process.poll() is None:process.kill();process.wait(timeout=10)
with tarfile.open(archive,'r:gz') as tar:
 manifest=json.load(tar.extractfile('manifest.json'));assert len(manifest)==1
 config=tar.extractfile(manifest[0]['Config']).read();assert digest(config)==image.removeprefix('sha256:')
def put(path,raw):
 url='/storage/v1/object/research-workflow-raw/'+path
 try:store.request(url,'POST',raw)
 except Exception:
  if store.request(url,raw=True)!=raw:raise
 assert store.request(url,raw=True)==raw
 return dict(path=path,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw))
chunks=[];compressed_hash=hashlib.sha256()
with archive.open('rb') as source:
 while part:=source.read(8000000):
  compressed_hash.update(part);key='qualification/experiment-builder-v2/'+root.name+'/image/'+image.removeprefix('sha256:')+'/'+str(len(chunks)).zfill(4)+'-'+digest(part)+'.part'
  chunks.append(put(key,part))
record=dict(version='qualified-builder-image-archive-v1',format='gzip-compressed Docker archive in ordered chunks',image=image,platform='linux/amd64',raw_tar_bytes=raw_bytes,raw_tar_sha256=raw_hash.hexdigest(),compressed_bytes=archive.stat().st_size,compressed_sha256=compressed_hash.hexdigest(),chunks=chunks,verification='Each original chunk retrieved byte-for-byte from private Supabase Storage before recording. Docker archive config hash equals qualified image ID. This is artifact integrity, not a full package/source audit.',wall_seconds=time.monotonic()-started,measured_charges_usd=None)
raw=canonical(record);pointer=put('qualification/experiment-builder-v2/'+root.name+'/image-manifest-'+digest(raw)+'.json',raw)
(out/'manifest.json').write_bytes(raw);(root/'image-archive.json').write_bytes(canonical(dict(bucket='research-workflow-raw',**pointer,public=False)))
print(json.dumps(dict(bucket='research-workflow-raw',**pointer,public=False,compressed_bytes=record['compressed_bytes'],chunks=len(chunks),image=image)))
