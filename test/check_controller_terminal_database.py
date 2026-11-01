"""Actual isolated SQL: terminal controller closure, evidence and resumption.

Runs all previous controls unchanged. No production, provider or Docker calls.
"""
from concurrent.futures import ThreadPoolExecutor
import copy,json,sys,uuid
from pathlib import Path
from unittest.mock import patch
import check_controller_handoff_database as previous
import check_research_ideas_database as f
import autonomy,workflow
MIGRATIONS=('202611010009_controller_terminal_recovery.sql','202611010010_controller_incident_evidence.sql')

class Fixture:
 """Independent RPC fixture; runtime byte validation has separate controls."""
 def __init__(self):
  self.task=dict(id=f.uid(),study_id=f.uid());self.blobs={}
  self.logical=dict(modelId='gpt-6.1-sol',system=[dict(text='Synthetic policy')],messages=[dict(role='user',content=[dict(text='Synthetic context')])],toolConfig=dict(tools=[dict(toolSpec=dict(inputSchema=dict(json={}))) ]))
  raw=workflow.canonical(self.logical)
  self.d=dict(id=f.uid(),task_id=self.task['id'],study_id=self.task['study_id'],status='invalid-output',request_raw=raw.decode(),request_sha256=workflow.digest(raw))
  self.receipt=dict(runtime='openclaw-production-v1',model_id='gpt-6.1-sol',status='invalid-output',error_code='invalid-structured-decision',provider_calls=1,provider_request_sent=True,response_received=True,http_status=200,provider_retries=0,paid_fallback=False)
  self.terminal=dict(id='synthetic-response',status='completed',model='gpt-6.1-sol',output=[])
  import siwc_protocol as wire
  contents={'logical.json':raw,'provider-request.json':workflow.canonical(wire.response_request(self.logical)),'receipt.json':workflow.canonical(self.receipt),'provider-response.bin':b'data: '+workflow.canonical(dict(type='response.completed',response=self.terminal))+b'\n\n'}
  self.refs=[]
  for name,raw in contents.items():
   ident=f.uid();self.blobs[ident]=raw;self.refs.append(dict(id=ident,name=name,sha256=workflow.digest(raw),byte_count=len(raw)))
  self.d['provenance']=dict(self.receipt,artifacts=self.refs)
 def proof(self):
  return dict(version='controller-terminal-reconciliation-v1',dispatch_id=self.d['id'],study_id=self.task['study_id'],task_id=self.task['id'],request_sha256=self.d['request_sha256'],original_status='invalid-output',request_kind='controller',provider_calls=1,provider_request_sent=True,response_received=True,http_status=200,provider_retries=0,terminal_status='completed',response_id=self.terminal['id'],terminal_sha256=workflow.digest(workflow.canonical(self.terminal)),decision_accepted=False,error_code='invalid-structured-decision',references={r['name']:dict(artifact_id=r['id'],sha256=r['sha256']) for r in self.refs})

def main():
 previous.main();f.report.update(protocol='controller-terminal-recovery-v1',passed=False);q=f.sql_text
 def js(sql,role=None):return json.loads(f.query(sql,role=role))
 def expect(value):
  if not value:raise AssertionError('Controller terminal recovery invariant failed')
 def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
 def all_originals():return f.query("select jsonb_build_object('dispatches',(select jsonb_agg(to_jsonb(x) order by id) from research_model_dispatches x),'turns',(select jsonb_agg(to_jsonb(x) order by id) from research_autonomy_turns x),'tasks',(select jsonb_agg(to_jsonb(x) order by id) from research_autonomy_tasks x),'calls',(select jsonb_agg(to_jsonb(x) order by id) from research_builder_calls x),'budgets',(select jsonb_agg(to_jsonb(x) order by category) from autonomy_budget_categories x),'workflows',(select jsonb_agg(to_jsonb(x) order by study_id) from research_autonomy_workflows x))")
 before=all_originals();unknown_before=f.query("select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c where status='unknown'")
 unknown_ids=js("select coalesce(jsonb_agg(id),'[]') from research_builder_calls where status='unknown'")
 for name in MIGRATIONS:
  raw=(f.ROOT/'database'/name).read_bytes();f.query(raw.decode());f.report['migration_sha256'][name]=workflow.digest(raw)
 check('forward migrations preserve all existing dispatches turns tasks native calls authorizations and limits',lambda:expect(all_originals()==before))
 seed=js('select to_jsonb(c) from research_claims c limit 1');prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
 def art(fx,ident,raw,kind,filename):
  h=workflow.digest(raw);f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(ident),q(fx.task['study_id']),q(h),str(len(raw)),q(fx.task['study_id']+'/'+h),q('application/octet-stream'),f.sql_json(dict(kind=kind,filename=filename,dispatch_id=fx.d['id'])),'clock_timestamp()'])+')')
  return dict(artifact_id=ident,sha256=h)
 def case(status='invalid-output',task_status='waiting'):
  fx=Fixture()
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic terminal controller fixture',paper_url='https://example.org/terminal.pdf',domain='Software',scope=__doc__)))['id']
  source,claim,ident=f.uid(),f.uid(),f.uid()
  f.query('insert into research_sources select (jsonb_populate_record(null::research_sources,to_jsonb(s)||'+f.sql_json(dict(id=source,study_id=study))+')).* from research_sources s where id='+q(seed['source_id']))
  f.query('insert into research_claims(id,study_id,source_id,location,description,claim_type,scope,metrics,priority) select '+','.join([q(claim),q(study),q(source)])+',location,description,claim_type,scope,metrics,priority from research_claims where id='+q(seed['id']))
  f.query('insert into research_autonomy_tasks(id,study_id,claim_id,stage,status,label,attempts,context,reason) values('+','.join([q(ident),q(study),q(claim),q('planning'),q(task_status),q('inconclusive'),'3',f.sql_json(dict(frozen='retained')),q('Evidence page byte budget is outside the reader bound.')])+')')
  fx.task.update(id=ident,study_id=study,claim_id=claim,actor_id=f.ACTOR,status=task_status)
  fx.d.update(task_id=ident,study_id=study,status=status)
  f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,ended_at) values('+','.join([q(fx.d['id']),q(study),q(ident),'1',q('planning'),q(prompt),q('gpt-6.1-sol'),f.sql_json(fx.logical),q(fx.d['request_raw']),q(fx.d['request_sha256']),q('invalid-output'),'100','clock_timestamp()'])+')')
  for ref in fx.refs:art(fx,ref['id'],fx.blobs[ref['id']],'model-runtime-original',ref['name'])
  f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status,provenance,ended_at) values('+','.join([q(fx.d['id']),q(study),q(ident),q('openclaw-production-v1'),q(fx.d['request_raw']),q(fx.d['request_sha256']),q(status),f.sql_json(fx.d['provenance']),'clock_timestamp()'])+')')
  proof=fx.proof() if status=='invalid-output' else dict(Fixture().proof(),dispatch_id=fx.d['id'],task_id=ident,study_id=study,request_sha256=fx.d['request_sha256'])
  pointer=art(fx,f.uid(),workflow.canonical(proof),'controller-dispatch-reconciliation','proof.json')
  return fx,proof,pointer
 def reconcile(item,role='service_role',proof=None):
  fx,value,pointer=item
  return js('select public.research_controller_dispatch_reconcile('+','.join([q(fx.d['id']),q(pointer['artifact_id']),q(pointer['sha256']),f.sql_json(proof or value)])+')',role)
 def snapshot(fx):return f.query('select jsonb_build_object(\'task\',(select to_jsonb(t) from research_autonomy_tasks t where id='+q(fx.task['id'])+'),\'turn\',(select to_jsonb(t) from research_autonomy_turns t where id='+q(fx.d['id'])+'),\'dispatch\',(select to_jsonb(d) from research_model_dispatches d where id='+q(fx.d['id'])+'),\'workflow\',(select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(fx.task['study_id'])+'))')
 target=case()
 def closure():
  fx,proof,_=target;before=snapshot(fx)
  cursor=str(uuid.UUID(int=uuid.UUID(fx.d['id']).int-1));candidates=js('select coalesce(jsonb_agg(x),\'[]\') from public.research_model_reconciliation_candidates('+q(cursor)+') x','service_role')
  expect(any(x['id']==fx.d['id'] for x in candidates))
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:reconcile(target),range(2)))
  expect(results[0]==results[1] and results[0]['proof']==proof and snapshot(fx)==before)
  expect(f.query('select count(*) from research_model_reconciliations where dispatch_id='+q(fx.d['id']))=='1')
  expect(f.query('select public.research_controller_dispatch_accounted(d) from research_model_dispatches d where id='+q(fx.d['id']))=='t')
 check('one rejected controller operation gets one immutable supplemental proof under concurrent workers without rewriting originals',closure)
 def security():
  item=case();before=snapshot(item[0])
  for role in ('anon','authenticated'):f.rejects(lambda role=role:reconcile(item,role))
  for role in ('anon','authenticated','service_role'):
   expect(f.query('select has_function_privilege('+q(role)+",'public.research_controller_dispatch_accounted(public.research_model_dispatches)','EXECUTE')")=='f')
  bad=copy.deepcopy(item[1]);bad['request_sha256']='0'*64;f.rejects(lambda:reconcile(item,proof=bad))
  bad=copy.deepcopy(item[1]);bad['provider_calls']=True;f.rejects(lambda:reconcile(item,proof=bad))
  bad=copy.deepcopy(item[1]);bad['references'].pop('provider-response.bin');f.rejects(lambda:reconcile(item,proof=bad))
  expect(snapshot(item[0])==before)
  f.rejects(lambda:f.query('update research_model_reconciliations set proof=\'{}\' where dispatch_id='+q(target[0].d['id'])))
 check('browser callers helper bypass changed requests receipt-only proofs and proof mutation are denied',security)
 def quiescence():
  for state,task_status in [('unknown','waiting'),('invalid-output','running')]:
   item=case(status=state,task_status=task_status);before=snapshot(item[0]);f.rejects(lambda:reconcile(item));expect(snapshot(item[0])==before)
  item=case();fx=item[0];ref=fx.refs[0]
  f.query('insert into research_builder_calls(study_id,task_id,dispatch_id,number,prompt_version_id,model_id,request_artifact_id,request_sha256,request_bytes,status,reserved_cents) values('+','.join([q(fx.task['study_id']),q(fx.task['id']),q(fx.d['id']),'1',q(prompt),q('gpt-6.1-sol'),q(ref['id']),q(ref['sha256']),str(ref['byte_count']),q('unknown'),'100'])+')')
  before=snapshot(fx);f.rejects(lambda:reconcile(item));expect(snapshot(fx)==before)
 check('an unknown operation live task or native admission cannot use the data-only rejection adapter',quiescence)
 def scoped_artifacts():
  first,second=case(),case();bad=copy.deepcopy(first[1]);bad['references']['provider-response.bin']=second[1]['references']['provider-response.bin']
  before=snapshot(first[0]);f.rejects(lambda:reconcile(first,proof=bad));expect(snapshot(first[0])==before)
 check('original response references cannot cross a study or dispatch boundary',scoped_artifacts)
 def linked(fx):
  platform,blocker=f.uid(),f.uid()
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,deadline_at) select '+q(platform)+",(select user_id from platform_operators where role='owner' limit 1),'Terminal evidence fixture','Synthetic original transport.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'blocked',-1,clock_timestamp()+interval '1 hour' from platform_settings where id")
  f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join([q(blocker),q(fx.task['study_id']),q(fx.task['id']),q('dispatch'),q(fx.d['id']),q('planning'),q('invalid-output'),q('Synthetic terminal evidence.'),q('a'*64),q(workflow.digest(blocker.encode()))])+')')
  f.query('insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(platform)+')');return platform
 def delivery():
  item=case();fx=item[0];platform=linked(fx)
  for i in range(25):art(fx,f.uid(),str(i).encode(),'model-runtime-original','irrelevant-'+str(i)+'.json')
  value=js('select public.platform_repair_context_data('+q(platform)+')')
  expect({r['id'] for r in fx.refs}<={r['id'] for r in value['artifacts']} and len(value['artifacts'])<=12)
  document=value['incident_documents'][0];expect(document['dispatch_id']==fx.d['id'])
  expect({'logical_request','provider_request','provider_response','receipt'}<={r['role'] for r in document['references']})
  revision=value['evidence_revision'];expect(js('select public.platform_repair_context_data('+q(platform)+')')['evidence_revision']==revision)
 check('original logical request provider request terminal response and receipt survive log churn in the bounded private context',delivery)
 def resumption():
  item=case(task_status='blocked');fx=item[0];platform=linked(fx);release,pin=f.uid(),f.uid();binding='a'*64
  proof=dict(passed=True,revision='b'*40,component='research-runtime',pin_revision='c'*40,source_binding=binding,all_other_template_content_preserved=True,scientific_and_request_content_unchanged=True,existing_tests_unchanged=True)
  f.query('insert into platform_releases(id,task_id,component,repository,revision,status,verification) values('+','.join([q(release),q(platform),q('research-runtime'),q('jumpserve-networks/jumpserve-back-end'),q('b'*40),q('verified'),f.sql_json(proof)])+')')
  def resume():return js('select public.research_runtime_resume('+q(release)+')','service_role')
  f.rejects(resume)
  f.query('insert into platform_releases(id,task_id,component,repository,revision,status,verification) values('+','.join([q(pin),q(platform),q('research-runtime-pin'),q('jumpserve-networks/jumpserve-infra'),q('c'*40),q('verified'),f.sql_json(dict(source_binding=binding))])+')')
  f.query("update platform_settings set paused=false where id;update autonomy_budget_categories set max_spend_cents=-1,max_model_calls=-1,change_reason='Synthetic resumption control' where category='research_assessment'")
  expect(fx.task['id'] not in resume()['resumed_task_ids']);reconcile(item)
  f.query('update platform_settings set paused=true where id');expect(resume()['resumed_task_ids']==[]);f.query('update platform_settings set paused=false where id')
  before=js('select to_jsonb(t) from research_autonomy_tasks t where id='+q(fx.task['id']));workflow_before=f.query('select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(fx.task['study_id']))
  result=resume();after=js('select to_jsonb(t) from research_autonomy_tasks t where id='+q(fx.task['id']))
  expect(fx.task['id'] in result['resumed_task_ids'] and after['status']=='queued')
  expect(all(after[k]==before[k] for k in ('id','study_id','claim_id','context','label','stage','attempts','created_at')))
  current=js('select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(fx.task['study_id']));old=json.loads(workflow_before)
  expect(all(current[k]==old[k] for k in ('initial_prompt','initial_sha256','deadline_at','max_spend_cents','max_attempts','committed_cents')))
  f.query("update research_autonomy_tasks set status='blocked',reason='Evidence page byte budget is outside the reader bound.' where id="+q(fx.task['id']));expect(fx.task['id'] not in resume()['resumed_task_ids'])
  other=case(task_status='blocked');reconcile(other);f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(other[0].task['study_id']));expect(other[0].task['id'] not in resume()['resumed_task_ids'])
  other=case(task_status='blocked');reconcile(other);f.query("update autonomy_budget_categories set max_model_calls=0,change_reason='Synthetic admission denial' where category='research_assessment'");expect(other[0].task['id'] not in resume()['resumed_task_ids'])
 check('only a verified release and matching pin can resume a proven reader failure once while preserving cancellation budgets original context criteria and counters',resumption)
 check('genuinely incomplete pre-existing native calls remain byte-for-byte unchanged',lambda:expect(unknown_before==f.query('select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c where id in ('+(','.join(map(q,unknown_ids)) if unknown_ids else 'null')+')')))
 f.report['passed']=True;path=f.DIRECTORY/'controller-terminal-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))

if __name__=='__main__':
 try:main()
 except Exception as error:
  f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'controller-terminal-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
