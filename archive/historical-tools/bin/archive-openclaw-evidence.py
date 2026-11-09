"""Archive only declared grant-free release evidence, then verify private retrieval."""
import hashlib,importlib.util,io,json,urllib.error,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('openclaw_release',ROOT/'bin/openclaw-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def main():
 target=release.target();entries={}
 for campaign in ('20261021T001226693527Z','20261021T004429580770Z'):
  base=ROOT/'.test-artifacts/openclaw-evaluation'/campaign
  # Exact model inputs/outputs and source snapshots; transient CLI databases and
  # loopback credential configs are deliberately excluded, not claimed archived.
  for path in sorted(base.rglob('*')):
   relative=path.relative_to(base)
   if not path.is_file() or 'state' in relative.parts or path.name=='config.json':continue
   if len(relative.parts)==1 or relative.parts[0]=='inputs' or len(relative.parts)==2 and path.name in ('logical.json','message.json','openclaw-http-body.bin','provider-request.json','provider-response.bin','stdout.bin','stderr.bin','receipt.json') or len(relative.parts)==3 and relative.parts[1:] == ('workspace','AGENTS.md'):
    entries['evaluations/'+campaign+'/'+str(relative)]=path.read_bytes()
 for pattern in ('docs/openclaw-production-*.json','database/*openclaw*.sql','test/openclaw-answer-cases-v*.json'):
  for path in sorted(ROOT.glob(pattern)):entries[str(path.relative_to(ROOT))]=path.read_bytes()
 entries['research-workflow-runtime.json']=(ROOT/'research-workflow-runtime.json').read_bytes()
 manifest=dict(protocol='openclaw-production-v1',targets=target,entries=[dict(path=n,sha256=sha(raw),byte_count=len(raw)) for n,raw in sorted(entries.items())],excluded='OAuth grants, native host authorization database/logs, per-turn transient state databases and ephemeral bridge configs. Original request/SSE/native output and exact source snapshots are included.',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),measured_charges_usd=None)
 raw_manifest=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode();entries['manifest.json']=raw_manifest
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,raw in sorted(entries.items()):archive.writestr(zipfile.ZipInfo(name,date_time=(2026,10,21,0,0,0)),raw,compress_type=zipfile.ZIP_DEFLATED)
 raw=buffer.getvalue()
 if len(raw)>16000000:raise ValueError('Declared evidence archive exceeds 16 MB; preserve it before a versioned amendment.')
 folder=ROOT/'.test-artifacts/openclaw-release';folder.mkdir(exist_ok=True);(folder/'evaluation-evidence-v1.zip').write_bytes(raw)
 key=release.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key};path='release-verification/openclaw-production-v1/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path
 try:
  with release.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,headers=dict(headers,**{'Content-Type':'application/zip','x-upsert':'false'}),method='POST'),timeout=60) as response:response.read()
 except urllib.error.HTTPError as error:
  body=error.read()
  if error.code!=409 and not (error.code==400 and b'Duplicate' in body):raise RuntimeError('Private original upload failed with HTTP '+str(error.code)) from None
 with release.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retained=response.read(16000001)
 if sha(retained)!=sha(raw):raise ValueError('Private archive retrieval differs from original bytes.')
 with zipfile.ZipFile(io.BytesIO(retained)) as archive:
  for entry in manifest['entries']:
   if sha(archive.read(entry['path']))!=entry['sha256']:raise ValueError('Retrieved original file differs.')
 record=dict(protocol=manifest['protocol'],bucket='research-workflow-raw',path=path,sha256=sha(raw),retrieved_sha256=sha(retained),byte_count=len(raw),manifest_sha256=sha(raw_manifest),original_file_count=len(manifest['entries']),public=False,excluded=manifest['excluded'],storage_charges_usd=None)
 (ROOT/'docs/openclaw-production-private-artifact.json').write_text(json.dumps(record,indent=2)+'\n');(folder/'evaluation-manifest-v1.json').write_bytes(raw_manifest);print(json.dumps(record))
if __name__=='__main__':main()
