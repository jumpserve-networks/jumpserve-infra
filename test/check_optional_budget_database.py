"""Isolated PostgreSQL budget policy checks; no production, provider or cloud calls."""
import copy,json,traceback
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_fixtures,workflow,store

def main():
 f.report.update(protocol='optional-assessment-budget-v1',design=__doc__,new_model_calls=0,new_cloud_instances=0)
 try:
  f.bootstrap()
  for name in ('202610210003_partial_assessment_recovery.sql','202610280001_data_only_model_window.sql','202610280002_assessment_budget_amendments.sql','202610280003_controller_reconciliation_window.sql','202610280004_autonomous_repair.sql','202610290001_builder_reconciliation.sql','202610300001_optional_assessment_budget.sql'):
   raw=(f.ROOT/'database'/name).read_bytes();f.report['migration_sha256'][name]=workflow.digest(raw);f.query(raw.decode())
  with patch.object(autonomy,'wake',return_value={}):
   study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Explicit unlimited-budget software fixture',paper_url='https://example.org/fixture.pdf',domain='Software development',scope='Synthetic SQL accounting only; no scientific findings')))['id']
  identity=f.sql_text(study)+'::uuid'
  def snapshot():return json.loads(f.query('select to_jsonb(w) from research_autonomy_workflows w where study_id='+identity))
  def tasks():return json.loads(f.query('select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_tasks t where study_id='+identity))
  request=f.uid()
  def amend(maximum=None,resume=True,identifier=request,role='service_role',reason='Explicit synthetic lab operator authorization'):
   return json.loads(f.query('select research_autonomy_set_budget('+','.join([identity,f.sql_text(identifier)+'::uuid','null' if maximum is None else str(maximum),'true' if resume else 'false',f.sql_text('Synthetic lab operator'),f.sql_text(reason)])+')',role=role))
  original=snapshot();assert original['max_spend_cents']==10000
  prompt=f.uid()
  f.query("insert into agent_prompt_versions(id,module_id,version,system_prompt,research_context,published_at,created_by,updated_by) values("+f.sql_text(prompt)+",'research-autonomy','synthetic-optional-budget-fixture','Synthetic SQL guard fixture','No model or scientific review',clock_timestamp(),'synthetic fixture','synthetic fixture');update agent_prompt_settings set active_version_id="+f.sql_text(prompt)+" where module_id='research-autonomy'")
  def lease():return f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  initial=lease();records=autonomy_fixtures.plan()['records'];source=next(r for r in records if r['kind']=='sources');base=next(r for r in records if r['kind']=='claims')
  claims=[]
  for _ in range(4):
   item=copy.deepcopy(base);item['record']['id']=f.uid();claims.append(item)
  store.append_bundle(study,f.ACTOR,[source,*claims]);autonomy.seed(initial,[c['record'] for c in claims],{});autonomy.advance(initial,'finished',reason='Synthetic intake finished.')
  t=lease();raw=workflow.canonical(dict(builder=dict(scope='Explicit synthetic reservation; no provider called.'))).decode()
  def reserve(task,cents):return autonomy.control(task,'begin',dict(id=f.uid(),request=json.loads(raw),request_raw=raw,request_sha256=workflow.digest(raw.encode()),reserved_cents=cents,prompt_version_id=prompt,model_id='gpt-6.1-sol'))
  def finish(task,turn):return autonomy.control(task,'finish',dict(id=turn['id'],status='invalid-output',raw_response='{}',output=None,reason='Synthetic SQL fixture; no provider response or charge.',usage={},estimated_cents=None))
  turn=reserve(t,100)
  f.rpc('research_model_dispatch',dict(p_operation='enqueue',p_payload=dict(id=turn['id'],study_id=study,task_id=t['id'],runtime='openclaw-production-v1',request_raw=raw,request_sha256=workflow.digest(raw.encode()))))
  f.query("update research_model_dispatches set status='unknown',ended_at=clock_timestamp() where id="+f.sql_text(turn['id']))
  finish(t,turn)
  reconciled_task=lease();reconciled_turn=reserve(reconciled_task,100)
  f.rpc('research_model_dispatch',dict(p_operation='enqueue',p_payload=dict(id=reconciled_turn['id'],study_id=study,task_id=reconciled_task['id'],runtime='openclaw-production-v1',request_raw=raw,request_sha256=workflow.digest(raw.encode()))))
  f.query("update research_model_dispatches set status='unknown',ended_at=clock_timestamp() where id="+f.sql_text(reconciled_turn['id']));finish(reconciled_task,reconciled_turn)
  f.query("update research_autonomy_tasks set status='budget' where id="+f.sql_text(reconciled_task['id']))
  checkpoint=store.artifact(study,f.ACTOR,b'Explicit synthetic SQL checkpoint; not a real builder workspace.',f.uid(),'application/octet-stream',dict(kind='builder-reconciled-workspace',dispatch_id=reconciled_turn['id']))
  store.append(study,f.ACTOR,'artifacts',checkpoint)
  proof=dict(version='builder-dispatch-reconciliation-v1',dispatch_id=reconciled_turn['id'],request_sha256=workflow.digest(raw.encode()),original_status='unknown',container_cleanup='stopped',calls=[],checkpoint=dict(artifact_id=checkpoint['id'],sha256=checkpoint['sha256']))
  original_proof=store.artifact(study,f.ACTOR,workflow.canonical(proof),f.uid(),'application/json',dict(kind='builder-dispatch-reconciliation',dispatch_id=reconciled_turn['id']))
  store.append(study,f.ACTOR,'artifacts',original_proof)
  f.rpc('research_model_reconcile',dict(p_dispatch=reconciled_turn['id'],p_artifact=original_proof['id'],p_sha256=original_proof['sha256'],p_proof=proof))
  blocked=next(c['record']['id'] for c in claims if c['record']['id'] not in (t['claim_id'],reconciled_task['claim_id']))
  f.query('select research_autonomy_amend_budget('+','.join([identity,f.sql_text(f.uid())+'::uuid','100000',f.sql_text('Synthetic old operator'),f.sql_text('Retain a prior finite amendment')])+')',role='service_role')
  f.query("update research_autonomy_workflows set committed_cents=100000,status='budget' where study_id="+identity)
  f.query("update research_autonomy_tasks set status=case when claim_id="+f.sql_text(blocked)+"::uuid then 'blocked' else 'budget' end,context=context||'{\"retained_checkpoint_fixture\":\"unchanged\"}'::jsonb where study_id="+identity+" and claim_id is not null")
  before=snapshot();before_tasks=tasks()
  def security():
   for role in ('anon','authenticated'):f.rejects(lambda:amend(role=role))
   f.rejects(lambda:f.query('update research_autonomy_workflows set max_spend_cents=null where study_id='+identity,role='service_role'))
   for cents in (-1,0,9999):f.rejects(lambda:amend(maximum=cents,identifier=f.uid()))
   f.rejects(lambda:f.query('update research_autonomy_workflows set committed_cents=0 where study_id='+identity,role='service_role'))
   f.rejects(lambda:f.query("update research_autonomy_workflows set deadline_at=deadline_at+interval '1 day' where study_id="+identity,role='service_role'))
   return dict(browser_and_unaudited_writes_denied=True,refund_and_deadline_reset_denied=True)
  f.check('explicit service-only authorization, immutable usage and time',security)
  def unlimited():
   result=amend();f.report['resume_observation']=result;after=snapshot();after_tasks=tasks();assert not result['replayed'] and after['max_spend_cents'] is None and after['committed_cents']==100000 and after['status']=='running'
   for key in ('initial_prompt','initial_sha256','deadline_at','created_at','max_attempts'):assert before[key]==after[key],key
   assert len(result['resumed_task_ids'])==2
   for old,new in zip(before_tasks,after_tasks):
    for key in ('id','claim_id','stage','label','attempts','context','created_at'):assert old[key]==new[key],key
    if old['claim_id']==t['claim_id']:assert new['status']=='budget'
    elif old['claim_id']==blocked:assert new['status']=='blocked'
    elif old['claim_id'] is not None:assert new['status']=='queued'
   assert amend()['replayed'];assert tasks()==after_tasks
   f.rejects(lambda:amend(reason='Conflicting replay'))
   event=json.loads(f.query('select details from research_autonomy_events where id='+f.sql_text(request)))
   assert event['previous_max_spend_cents']==100000 and event['max_spend_cents'] is None and event['committed_cents']==100000
   f.rejects(lambda:f.query("update research_autonomy_events set details='{}' where id="+f.sql_text(request),role='service_role'))
   public=f.api.dispatch(dict(rawPath='/research/studies/'+study+'/queue',requestContext=dict(http=dict(method='GET')),queryStringParameters=dict(public='1',diagnostics='1')),None)
   assert public['autonomy']['workflows'][0]['max_spend_cents'] is None and public['autonomy']['workflows'][0]['committed_cents']==100000
   assert 'initial_prompt' not in public['autonomy']['workflows'][0] and public['coverage']['jobs']==0
   (f.DIRECTORY/'public-unlimited-queue.json').write_text(json.dumps(public,indent=2)+'\n')
   assert f.query('select status from research_model_dispatches where id='+f.sql_text(reconciled_turn['id']))=='unknown'
   return dict(explicit_null=True,commitments_cents=100000,resumed_budget_only=2,unknown_not_replayed=True,reconciled_unknown_can_continue=True,original_unknown_receipt_unchanged=True,originals_unchanged=True,idempotent=True,actual_public_api_preserves_null=True)
  f.check('unlimited amendment preserves evidence and resumes only safe budget-stopped tasks',unlimited)
  def admission():
   task=lease();assert task['claim_id']!=t['claim_id'] and task['claim_id']!=blocked
   for _ in range(2):
    attempt=reserve(task,6000);assert not attempt.get('denied'),attempt;finish(task,attempt)
   amount=snapshot()['committed_cents'];assert amount>100000
   ceiling=amount+100
   result=amend(maximum=ceiling,resume=False,identifier=f.uid());assert result['max_spend_cents']==ceiling
   f.rejects(lambda:amend(maximum=amount-1,identifier=f.uid()))
   assert reserve(task,101)['denied']=='budget';assert snapshot()['committed_cents']==amount
   attempt=reserve(task,100);assert not attempt.get('denied');finish(task,attempt)
   assert snapshot()['committed_cents']==ceiling and reserve(task,1)['denied']=='budget'
   assert snapshot()['deadline_at']==original['deadline_at'];assert f.query('select count(*) from research_queue_jobs')=='0'
   assert f.query("select column_default from information_schema.columns where table_name='research_autonomy_workflows' and column_name='max_spend_cents'")=='10000'
   f.query("update research_autonomy_workflows set status='cancelled' where study_id="+identity)
   f.rejects(lambda:amend(identifier=f.uid()))
   return dict(reservations_crossed_former_cap=True,restored_cap_cents=ceiling,restored_cap_enforced=True,cancellation_enforced=True,new_provider_calls=0,new_experiments=0,default_cents=10000)
  f.check('actual SQL admission accounts above the former cap and enforces a restored finite ceiling',admission)
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error));traceback.print_exc();raise
 finally:
  f.report['ended_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat();path=f.DIRECTORY/'optional-budget-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(report=str(path),passed=f.report.get('passed'),checks=f.report['checks'])))

if __name__=='__main__':main()
