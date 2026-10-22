"""Persist only the allowlisted planning release evidence; no prompt publication."""
import argparse,datetime as dt,hashlib,importlib.util,io,json,urllib.error,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
sha=lambda raw:hashlib.sha256(raw).hexdigest()
STUDY='584e6ce7-b104-4f77-aa3a-2a2c0eac0f31'
def inspect():
 result=dict(targets=r.target(),cancelled=r.admin.query("select status,committed_cents,(select count(*) from research_autonomy_turns where study_id='"+STUDY+"' and status='running') running_turns from research_autonomy_workflows where study_id='"+STUDY+"'"),dispatches=r.admin.query("select status,count(*) from research_model_dispatches where status in ('queued','running','unknown') group by status"),prompt=r.admin.query("select v.id,v.version,v.content_sha256 from agent_prompt_versions v join agent_prompt_settings s on s.active_version_id=v.id where s.module_id='research-autonomy'"))
 if result['cancelled']!=[dict(status='cancelled',committed_cents=8695,running_turns=0)]:raise RuntimeError('Cancelled study changed; do not resume it')
 if len(result['prompt'])!=1 or result['prompt'][0]['version']!='research-autonomy-v10':raise RuntimeError('Published production prompt changed')
 return result
def archive(directory):
 before=inspect();review_path=ROOT/'docs/planning-context-release-live-reviewed-v1.json';review=json.loads(review_path.read_bytes())
 if review['passed'] is not True or review['human_review'] is not False:raise RuntimeError('Exact substantive AI review required; do not claim human review')
 selected=ROOT/review['report'];raw=selected.read_bytes()
 if sha(raw)!=review['report_sha256']:raise RuntimeError('Reviewed original report changed')
 entries={}
 def add(path,expected=None):
  path=path.resolve()
  if not path.is_relative_to(ROOT) or any(p in ('state','workspace','.subscription-auth') for p in path.relative_to(ROOT).parts):raise RuntimeError('Out-of-scope or credential path')
  raw=path.read_bytes()
  if expected and sha(raw)!=expected:raise RuntimeError('Original artifact changed: '+path.name)
  entries[str(path.relative_to(ROOT))]=raw
 old_manifest=json.loads((ROOT/'docs/autonomy-planning-context-artifacts-v1.json').read_bytes())
 for item in old_manifest['artifacts']:add(ROOT/item['path'],item['sha256'])
 for pattern in ('autonomy-planning-context*','planning-context-release*'):
  for path in (ROOT/'docs').glob(pattern):
   if path.is_file():add(path)
 for path in (ROOT/'.test-artifacts/research-ideas/database').glob('*/planning-live-report.json'):
  base=path.parent
  for item in base.rglob('*'):
   if not item.is_file() or any(part in ('state','workspace') for part in item.relative_to(base).parts):continue
   if item.name in ('planning-live-report.json','planning-live-frozen.json','producer.py','source-original.pdf','turns.json','measurements.json','runs.json','artifacts.json','receipt.json','provider-response.bin','logical.json','message.json') or item.name.startswith('original-'):add(item)
 for name in ('planning-context-release-backend.log','planning-context-release-infra.log','planning-context-release-database.log'):
  path=(ROOT.parent/'jumpserve-back-end' if name.endswith('backend.log') else ROOT)/'.test-artifacts'/name
  if name.endswith('backend.log'):entries['backend-validation/'+name]=path.read_bytes()
  else:add(path)
 manifest=[dict(path=name,sha256=sha(data),bytes=len(data)) for name,data in sorted(entries.items())];buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,data in sorted(entries.items()):
   entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;z.writestr(entry,data)
  z.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
 raw=buffer.getvalue()
 if len(raw)>32000000:raise RuntimeError('Private archive exceeds bounded upload')
 (directory/'original-evidence.zip').write_bytes(raw)
 secret=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];key='release-verification/planning-context-20261022/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+key;headers={'apikey':secret,'Authorization':'Bearer '+secret}
 try:
  with r.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=60) as response:response.read(1000)
 except urllib.error.HTTPError as error:
  if error.code!=409:raise RuntimeError('Private evidence upload failed: HTTP '+str(error.code)) from None
 with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retrieved=response.read(32000001)
 if raw!=retrieved or sha(raw)!=sha(retrieved):raise RuntimeError('Retrieved original evidence hash differs')
 anon=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
 try:
  with r.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':anon}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as error:status=error.code
 if status not in (400,401,403,404):raise RuntimeError('Evidence archive must stay private')
 archive=dict(bucket='research-workflow-raw',path=key,sha256=sha(raw),retrieved_sha256=sha(retrieved),bytes=len(raw),files=len(manifest),anonymous_status=status,measured_storage_charges_usd=None)
 report=dict(version='planning-context-release-evidence-v1',targets=before['targets'],review=review,archive=archive,old_failures_preserved=True,prompt_publication_unchanged=True,kind='Controller software development follow-up; not independent scientific validation or a new prompt evaluation',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False))
 original=json.dumps(report,sort_keys=True,indent=2)+'\n';digest=sha(original.encode());literal=r.admin.literal
 r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([literal('6117e5c5-84ce-5c31-aaa7-0d1d3522e62e')+'::uuid',literal('passed'),literal(original),literal(digest),literal(json.dumps(archive))+'::jsonb',literal('Primary Codex AI implementer; controller integration follow-up; no publication')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
 stored=r.admin.query("select report_sha256,encode(sha256(convert_to(report_raw,'UTF8')),'hex') retrieved_sha256 from agent_prompt_evaluations where report_sha256="+literal(digest))
 if stored!=[dict(report_sha256=digest,retrieved_sha256=digest)]:raise RuntimeError('Stored review/report hash differs')
 (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return dict(report=report,stored_report=stored)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['inspect','archive']);args=parser.parse_args();directory=ROOT/'.test-artifacts/planning-context-release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,exist_ok=False)
 receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:receipt['result']=inspect() if args.mode=='inspect' else archive(directory);receipt['status']='complete'
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:receipt['ended_at']=r.stamp();(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(directory=str(directory),status=receipt['status'],reason=receipt.get('reason'))))
if __name__=='__main__':main()
