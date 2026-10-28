"""Isolated real SQL budget amendment/lease checks; zero model or AWS calls."""
import json,hashlib,traceback
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,workflow

def main():
 f.report.update(protocol='assessment-recovery-v1',design=__doc__,new_model_calls=0,new_cloud_instances=0)
 try:
  f.bootstrap()
  for name in ('202610280001_data_only_model_window.sql','202610280002_assessment_budget_amendments.sql','202610280003_controller_reconciliation_window.sql'):
   raw=(f.ROOT/'database'/name).read_bytes();f.report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();f.query(raw.decode())
  with patch.object(autonomy,'wake',return_value={}):
   study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Explicit software budget fixture',paper_url='https://example.org/fixture.pdf',domain='Software verification',scope='Synthetic budget amendment and lease checks; no scientific claims')))['id']
  def snapshot():return json.loads(f.query('select row_to_json(w) from research_autonomy_workflows w where study_id='+f.sql_text(study)))
  before=snapshot();request=f.uid()
  def amend(identifier=request,maximum=100000,role='service_role',reason='Explicit lab operator test authorization'):
   return json.loads(f.query('select research_autonomy_amend_budget('+','.join([f.sql_text(study)+'::uuid',f.sql_text(identifier)+'::uuid',str(maximum),f.sql_text('Synthetic lab operator'),f.sql_text(reason)])+')',role=role))
  def unaudited():
   f.rejects(lambda:f.query('update research_autonomy_workflows set max_spend_cents=100000 where study_id='+f.sql_text(study),role='service_role'))
   for role in ('anon','authenticated'):f.rejects(lambda:amend(role=role))
   for value in (9999,100001):f.rejects(lambda:amend(identifier=f.uid(),maximum=value))
   return dict(unaudited_write_denied=True,browser_rpc_denied=True,bounds_enforced=True)
  f.check('only audited bounded operator amendments can increase funding',unaudited)
  def positive():
   result=amend();after=snapshot();assert not result['replayed'] and after['max_spend_cents']==100000
   for field in before:
    if field not in ('max_spend_cents','updated_at'):assert after[field]==before[field],field
   assert amend()['replayed'];f.rejects(lambda:amend(reason='Conflicting replay'))
   f.rejects(lambda:amend(identifier=f.uid(),maximum=50000))
   event=json.loads(f.query('select details from research_autonomy_events where id='+f.sql_text(request)))
   assert event['previous_max_spend_cents']==10000 and event['max_spend_cents']==100000 and event['committed_cents']==before['committed_cents']
   f.rejects(lambda:f.query("update research_autonomy_events set details='{}' where id="+f.sql_text(request),role='service_role'))
   assert f.query("select column_default from information_schema.columns where table_name='research_autonomy_workflows' and column_name='max_spend_cents'")=='10000'
   f.rejects(lambda:f.query("update research_autonomy_workflows set deadline_at=deadline_at+interval '1 day' where study_id="+f.sql_text(study),role='service_role'))
   return dict(cap_cents=100000,defaults_cents=10000,old_authorization_retained=True,idempotent=True,old_usage_and_deadline_unchanged=True,tasks_not_resumed=True)
  f.check('an amendment preserves original records without resetting or resuming work',positive)
  def spending():
   prompt=f.uid()
   f.query("insert into agent_prompt_versions(id,module_id,version,system_prompt,research_context,published_at,created_by,updated_by) values("+f.sql_text(prompt)+",'research-autonomy','synthetic-budget-reservation-fixture','Synthetic SQL guard fixture','No provider or scientific review',clock_timestamp(),'synthetic fixture','synthetic fixture');update agent_prompt_settings set active_version_id="+f.sql_text(prompt)+" where module_id='research-autonomy'")
   task=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
   raw=workflow.canonical(dict(scope='Synthetic model reservation only; no provider invoked.')).decode()
   def reserve(cents):return autonomy.control(task,'begin',dict(id=f.uid(),request=json.loads(raw),request_raw=raw,request_sha256=workflow.digest(raw.encode()),reserved_cents=cents,prompt_version_id=prompt,model_id='synthetic-no-provider'))
   for cents in [6000,6000]+[10000]*8:
    result=reserve(cents);assert not result.get('denied'),result
    autonomy.control(task,'finish',dict(id=result['id'],status='invalid-output',raw_response='{}',output=None,reason='Synthetic SQL reservation; no model response or charge.',usage={},estimated_cents=None))
   committed=snapshot()['committed_cents'];assert 10000<committed<=100000
   assert reserve(10000)['denied']=='budget';assert snapshot()['committed_cents']==committed
   assert snapshot()['deadline_at']==before['deadline_at']
   return dict(aggregate_commitments_cents=committed,above_former_cap=True,new_cap_enforced=True,new_provider_calls=0)
  f.check('actual admission can cross the former cap and still denies overspending',spending)
  definition=f.query("select pg_get_functiondef('public.research_autonomy_before_confirmation(text,uuid,uuid,jsonb)'::regprocedure)")
  assert "lease_until=clock_timestamp()+interval '480 seconds'" in definition
  dispatch=f.query("select pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure)")
  assert "then interval '330 seconds' else interval '235 seconds'" in dispatch
  assert "then interval '350 seconds' else interval '240 seconds'" in dispatch
  f.report.update(passed=True,controller_lease_seconds=480,model_builder_lease_seconds=330,controller_builder_wait_seconds=350)
 except Exception as error:f.report.update(passed=False,error=str(error));traceback.print_exc();raise
 finally:
  f.report['ended_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat();(f.DIRECTORY/'assessment-recovery-report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(report=str(f.DIRECTORY/'assessment-recovery-report.json'),passed=f.report.get('passed'),checks=f.report['checks'])))
if __name__=='__main__':main()
