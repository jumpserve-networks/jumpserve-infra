"""Read-only owner-study inspection and private original-byte release archive."""
import argparse,datetime as dt,hashlib,importlib.util,io,json,urllib.error,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['observe','archive']);p.add_argument('--study',required=True,type=uuid.UUID);a=p.parse_args();study=str(a.study)
 directory=ROOT/'.test-artifacts/openclaw-study-verification'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
 report=dict(protocol='openclaw-production-authenticated-control-v1',study_id=study,mode=a.mode,started_at=r.stamp(),status='running',measured_charges_usd=None,subscription_allocation_usd=None,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False))
 try:
  report['targets']=r.target();s=r.admin.query('select id,title,paper_upload from research_studies where id='+r.admin.literal(study)+'::uuid')
  if len(s)!=1 or not s[0]['title'].startswith('Production OpenClaw release verification') or s[0]['paper_upload']['sha256']!='f6378fb3de19aa8d3204f4d3a2028f95497f334862a5298aa6678ef1b816290b':raise ValueError('Only the declared production IPv6 PDF control is allowed')
  kinds=('autonomy_workflows','autonomy_tasks','autonomy_turns','autonomy_events','model_dispatches','queue_jobs','runs','measurements','assessments','artifacts','claims')
  data={}
  for kind in kinds:
   projection="to_jsonb(t)||jsonb_build_object('value',t.value::text)" if kind=='measurements' else 'to_jsonb(t)'
   data[kind]=[v['record'] for v in r.admin.query('select '+projection+' record from research_'+kind+' t where study_id='+r.admin.literal(study)+'::uuid')]
  raw=(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode();path=directory/'private-snapshot.json';path.write_bytes(raw);path.chmod(0o600)
  w=data['autonomy_workflows'][0];assert w['max_attempts'] is None and w['max_spend_cents']==10000 and w['committed_cents']<=10000 and sha(w['initial_prompt'].encode())==w['initial_sha256']
  for t in data['autonomy_turns']:
   assert sha(t['request_raw'].encode())==t['request_sha256'] and json.loads(t['request_raw'])==t['request'] and t['number']>=1
   assert t['model_id']=='gpt-6.1-sol' and t['prompt_version_id']=='6117e5c5-84ce-5c31-aaa7-0d1d3522e62e'
   if t['raw_response'] is not None:assert sha(t['raw_response'].encode())==t['response_sha256']
  assert len({t['id'] for t in data['model_dispatches']})==len(data['model_dispatches'])
  for d in data['model_dispatches']:
   assert sha(d['request_raw'].encode())==d['request_sha256']
   assert d['runtime']=='openclaw-production-v1'
   if d['status']=='complete':assert d['provenance']['paid_fallback'] is False and d['provenance']['provider_retries']==0
  count=lambda rows,key:{v:sum(t.get(key)==v for t in rows) for v in sorted({t.get(key) for t in rows},key=str)}
  report.update(workflow_status=w['status'],committed_cents=w['committed_cents'],deadline_at=w['deadline_at'],ai_turn_ceiling=None,claim_count=len(data['claims']),task_statuses=count(data['autonomy_tasks'],'status'),turn_statuses=count(data['autonomy_turns'],'status'),dispatch_statuses=count(data['model_dispatches'],'status'),run_statuses=count(data['runs'],'status'),measurement_statuses=count(data['measurements'],'status'),measurement_units=count(data['measurements'],'units'),assessment_labels=count(data['assessments'],'label'),tasks=[dict(id=t['id'],stage=t['stage'],status=t['status'],label=t['label'],attempts=t['attempts'],reason=t['reason']) for t in data['autonomy_tasks']],available_model_usage=[dict(turn=t['id'],tokens=t['usage'].get('tokens'),estimated_cents=t['estimated_cents']) for t in data['autonomy_turns']],private_snapshot_sha256=sha(raw),original_prompt_response_hashes_verified=True)
  report['execution_criteria_met']=any(t['status']=='complete' for t in data['autonomy_turns']) and any(t['status']=='complete' for t in data['runs']) and any(t['status']=='recorded' for t in data['measurements'])
  if a.mode=='archive':
   key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key};base='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/';buffer=io.BytesIO();manifest=[];total=len(raw)
   cache=ROOT/'.test-artifacts/openclaw-study-verification/original-byte-cache';cache.mkdir(exist_ok=True);seen=set()
   with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('private-snapshot.json',raw)
    for artifact in data['artifacts']:
     if artifact['storage_path']!=study+'/'+artifact['sha256'] or artifact['byte_count']>16000000:raise ValueError('Unexpected private artifact identity/bound')
     cached=cache/artifact['sha256']
     if cached.exists():original=cached.read_bytes()
     else:
      with r.prior.guard.OPEN.open(urllib.request.Request(base+artifact['storage_path'],headers=headers),timeout=30) as response:original=response.read(16000001)
      assert len(original)==artifact['byte_count'] and sha(original)==artifact['sha256'];cached.write_bytes(original);cached.chmod(0o600)
     assert len(original)==artifact['byte_count'] and sha(original)==artifact['sha256']
     if artifact['sha256'] not in seen:
      total+=len(original)
      if total>64000000:raise ValueError('Original archive exceeds 64 MB uncompressed; preserve this snapshot before amending')
      z.writestr('artifacts/'+artifact['sha256'],original);seen.add(artifact['sha256'])
     manifest.append(dict(id=artifact['id'],sha256=sha(original),byte_count=len(original)))
    for image in sorted((ROOT.parent/'jumpserve-front-end/.test-artifacts/openclaw-production-browser').glob('*.png')):
     original=image.read_bytes();z.writestr('private-browser/'+image.name,original);manifest.append(dict(kind='private-browser',name=image.name,sha256=sha(original),byte_count=len(original)))
    z.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
   original=buffer.getvalue()
   (directory/'private-originals.zip').write_bytes(original);(directory/'private-originals.zip').chmod(0o600)
   if len(original)>32000000:raise ValueError('Private compressed archive exceeds 32 MB; preserve before amending')
   archive_path='release-verification/openclaw-authenticated-control/'+study+'/'+sha(original)+'.zip';url=base+archive_path
   report['archive_candidate']=dict(path=archive_path,sha256=sha(original),byte_count=len(original),artifact_records=len(data['artifacts']),unique_artifacts=len(seen));(directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
   try:
    with r.prior.guard.OPEN.open(urllib.request.Request(url,data=original,headers=dict(headers,**{'Content-Type':'application/zip','x-upsert':'false'}),method='POST'),timeout=120) as response:response.read(1000)
   except (urllib.error.URLError,TimeoutError) as error:
    # The deterministic content address makes a successful read conclusive even
    # if the upload acknowledgement was lost. Never overwrite an existing object.
    report['upload_acknowledgement_error']=str(error)
   with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retrieved=response.read(32000001)
   assert sha(retrieved)==sha(original)
   report['private_archive']=dict(bucket='research-workflow-raw',path=archive_path,sha256=sha(original),retrieved_sha256=sha(retrieved),byte_count=len(original),original_file_count=len(manifest),private=True)
  report.update(status='verified',scientific_scope='Exposed archived numerical control; running/blocked claims are not complete validation. No new Internet measurement or independent human review.')
 except Exception as error:report.update(status='failed',reason=str(error));raise
 finally:
  report['ended_at']=r.stamp();(directory/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(directory),**{k:v for k,v in report.items() if k not in ('tasks','available_model_usage')}),indent=2))
if __name__=='__main__':main()
