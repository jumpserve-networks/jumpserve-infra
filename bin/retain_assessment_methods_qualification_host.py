"""Archive original qualification evidence, excluding only derived Node caches."""
import io,json,pathlib,sys,zipfile
BASE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'research_workflow'))
import store
from workflow import canonical,digest
assert (BASE/'report.json').exists()
files={};excluded=[]
for p in BASE.rglob('*'):
    if not p.is_file() or p.is_symlink():continue
    relative=p.relative_to(BASE)
    if any(part in ('state','node_modules','node-compile-cache','__pycache__') for part in relative.parts) or p.name in ('config.json','archive.json','run.log','.report-writing.json'):
        excluded.append(dict(path=str(relative),bytes=p.stat().st_size,reason='Derived runtime/cache/state or credential-bearing ephemeral configuration, not source or research evidence.'));continue
    if p.stat().st_size>6000000:raise ValueError('Unexpected evidence-file bound; preserve it and amend before archiving.')
    files[str(relative)]=p.read_bytes()
files['archive-exclusions.json']=canonical(excluded)
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
    for name,raw in sorted(files.items()):z.writestr(name,raw)
    z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]))
raw=stream.getvalue();assert len(raw)<=20000000
path='qualification/autonomy-methods-v1/'+BASE.name+'/retained-'+digest(raw)+'.zip'
try:store.request('/storage/v1/object/research-workflow-raw/'+path,'POST',raw)
except Exception:
    if store.request('/storage/v1/object/research-workflow-raw/'+path,raw=True)!=raw:raise
restored=store.request('/storage/v1/object/research-workflow-raw/'+path,raw=True);assert restored==raw
item=dict(path=path,sha256=digest(raw),retrieved_sha256=digest(restored),bytes=len(raw),members=len(files),excluded_derived_files=len(excluded),provider_calls_replayed=0,public=False)
(BASE/'archive.json').write_bytes(canonical(item));print(json.dumps(item),flush=True)
