"""Read-only delivery check for the explicitly cancelled BBR study; never resumes it."""
import datetime as dt,hashlib,importlib.util,json,os,sys,urllib.request
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';STUDY='584e6ce7-b104-4f77-aa3a-2a2c0eac0f31'
os.environ['RESEARCH_AI_RUNTIME']='openclaw-production-v1';sys.path.insert(0,str(BACK/'research_workflow'))
import autonomy,autonomy_inputs as inputs,autonomy_model as model,store,workflow
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
def main():
 targets=r.target();s=r.admin.literal(STUDY)+'::uuid';base=ROOT/'.test-artifacts/study-cancellation'/STUDY;original=json.loads((base/'before.json').read_bytes())[0];w=original['workflow']
 claims=r.admin.query('select * from research_claims where study_id='+s);sources=r.admin.query('select * from research_sources where study_id='+s)
 bound=[t for t in original['tasks'] if t['claim_id'] and t['context'].get('text_artifact_id')];assert len(bound)==len(claims)==52
 text_id=bound[0]['context']['text_artifact_id'];artifact=r.admin.query('select * from research_artifacts where study_id='+s+' and id='+r.admin.literal(text_id)+'::uuid')[0]
 original_artifact=r.admin.query('select * from research_artifacts where study_id='+s+' and id='+r.admin.literal(artifact['provenance']['original_artifact_id'])+'::uuid')[0]
 assert artifact['storage_path']==STUDY+'/'+artifact['sha256'] and artifact['byte_count']<=10000000
 secret=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+artifact['storage_path']
 with r.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':secret,'Authorization':'Bearer '+secret}),timeout=30) as response:raw=response.read(10000001)
 assert len(raw)==artifact['byte_count'] and workflow.digest(raw)==artifact['sha256'];(base/'retained-text-original.json').write_bytes(raw);(base/'retained-text-original.json').chmod(0o600)
 records=dict(claims={c['id']:c for c in claims},sources={c['id']:c for c in sources},artifacts={a['id']:a for a in (artifact,original_artifact)})
 def lookup(kind,study,key):assert study==STUDY;return records[kind][key]
 seed=json.loads((ROOT/'database/seed-autonomy-v10.json').read_bytes());system=seed['system_prompt']+'\n\n'+seed['research_context'];sizes=[];anchored=0
 with patch.object(autonomy,'one',side_effect=lookup),patch.object(autonomy,'rows',return_value=[]),patch.object(store,'artifact_bytes',return_value=raw):
  for task in bound:
   t=dict(task,stage='planning',workflow=w);context=autonomy.build_context(t);material=context['source_material'];assert context['claim']['description'] in material['inline_passage']['text'];assert not material['complete_source_review'];anchored+=1
   wire=model.request(system,context);sizes.append(len(workflow.canonical(wire)));assert sizes[-1]<=96000
  material,fragments=inputs.source_text(dict(bound[0],workflow=w),records['claims'][bound[0]['claim_id']],sources[0],lookup)
  for page in json.loads(raw)['pages']:assert ''.join(f['text'] for f in fragments if f['page']==page['page'])==page['text']
 current=r.admin.query('select status,committed_cents,(select count(*) from research_autonomy_turns where study_id='+s+" and status='running') running_turns from research_autonomy_workflows where study_id="+s)[0]
 assert current==dict(status='cancelled',committed_cents=8695,running_turns=0)
 report=dict(protocol='autonomy-planning-context-protocol-v6',context_version=inputs.VERSION,input_implementation_sha256=hashlib.sha256(Path(inputs.__file__).read_bytes()).hexdigest(),kind='Read-only exposed structural check; no model inference or experiment execution',status='passed',study_id=STUDY,targets=targets,source_pdf_sha256=original_artifact['sha256'],retrieved_text_packet_sha256=workflow.digest(raw),candidate_claims_with_original_quote_delivered=anchored,all_original_extracted_text_reconstructs=True,page_count=material['page_count'],max_actual_v10_wire_bytes=max(sizes),provider_wire_limit=96000,complete_source_review_claimed=False,cancelled_study_unchanged=current,model_calls=0,database_writes=0,experiment_launches=0,checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),limitations='Shows that retained passages/contracts reach the proposed context. Does not demonstrate successful BBRv3 experiment design or implementation, examine figures/equations/supplements, or resolve any cancelled claim.')
 destination=ROOT/'docs/autonomy-planning-context-real-source-v4.json'
 if destination.exists():raise ValueError('Preserve this original check; version a new result before rechecking.')
 destination.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
