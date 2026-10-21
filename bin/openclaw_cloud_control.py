"""One declared cloud transport control, reusing exposed synthetic evaluation input."""
import base64,hashlib,json,shlex,uuid,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def prepare(directory):
 base=ROOT/'.test-artifacts/openclaw-evaluation/20261021T004429580770Z'
 packet=json.loads((base/'frozen.json').read_bytes());case=next(c for c in packet['cases'] if c['name']=='missing-inputs')
 raw=(base/'missing-inputs-request.json').read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest()
 if sha(raw)!=case['request_sha256']:raise ValueError('Frozen original transport control request differs')
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
 if manifest['files']!=packet['input_sha256']:raise ValueError('Reviewed source changed before cloud control')
 identity=str(uuid.uuid4());frozen=dict(protocol='openclaw-production-cloud-control-v1',id=identity,stage='exposed-software-control',request_sha256=sha(raw),source_sha256=manifest['files'],model='gpt-6.1-sol',maximum_provider_calls=1,maximum_wall_seconds=180,orchestration_reserve_cents=100,measured_charges_usd=None,subscription_allocation_usd=None,expected=dict(action='blocked',assessment_label=None,coverage_complete=False),limitations='Reuses an exposed synthetic case. No paper verdict, experiment measurement or independent validation.')
 (directory/'request.json').write_bytes(raw);(directory/'frozen-control.json').write_text(json.dumps(frozen,indent=2)+'\n')
 encoded=base64.b64encode(zlib.compress(raw,9)).decode()
 code="""import base64,hashlib,io,json,sys,zipfile,zlib
from pathlib import Path
sys.path.insert(0,'/opt/jumpserve/runtime')
import openclaw_runtime as r,autonomy_model as model,store
from workflow import canonical,digest
expected=EXPECTED
for name,sha in expected.items():assert digest((Path('/opt/jumpserve/runtime')/name).read_bytes())==sha,'Deployed source differs'
raw=zlib.decompress(base64.b64decode(ENCODED));assert digest(raw)==REQUESTHASH
directory=Path('/var/lib/jumpserve-openclaw/controls')/IDENTITY
r.verify_runtime();r.catalog(r.credential());answer,receipt=r.execute(json.loads(raw),directory)
decoded=model.parse(answer) if answer else None
if decoded:model.validate_phase(decoded,dict(task='planning'))
files={str(p.relative_to(directory)):p.read_bytes() for p in directory.iterdir() if p.is_file() and p.name!='config.json'}
files['workspace/AGENTS.md']=(directory/'workspace/AGENTS.md').read_bytes()
manifest=[dict(path=n,sha256=digest(b),byte_count=len(b)) for n,b in sorted(files.items())]
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
 for n,b in sorted(files.items()):archive.writestr(n,b)
 archive.writestr('manifest.json',canonical(manifest))
original=buffer.getvalue();path='release-verification/openclaw-cloud-control/'+IDENTITY+'/'+digest(original)+'.zip';url='/storage/v1/object/research-workflow-raw/'+path
store.request(url,'POST',original);retrieved=store.request(url,raw=True);assert digest(retrieved)==digest(original)
passed=receipt['status']=='complete' and decoded['action']=='blocked' and decoded['assessment_label'] is None and decoded['coverage_complete'] is False and not decoded['evidence_ids']
print(json.dumps(dict(protocol='openclaw-production-cloud-control-v1',id=IDENTITY,status=receipt['status'],passed=passed,output=decoded,receipt=receipt,source_files_verified=len(expected),archive=dict(bucket='research-workflow-raw',path=path,sha256=digest(original),retrieved_sha256=digest(retrieved),byte_count=len(original),originals=manifest),human_review=False)))
if not passed:raise RuntimeError('Actual cloud control failed; preserve this attempt before an amendment')
""".replace('EXPECTED',repr(manifest['files'])).replace('ENCODED',repr(encoded)).replace('REQUESTHASH',repr(sha(raw))).replace('IDENTITY',repr(identity))
 command='set -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(code)
 return frozen,command
