"""Actual private dispatch SQL with synthetic provider/Storage; no cloud calls."""
import json,traceback
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_fixtures as fixture,model_dispatch as dispatch,workflow

def main():
 f.report.update(protocol='openclaw-production-v1',actual_provider_calls=0,design='Exposed local SQL development controls, synthetic provider/Storage and owner; no actual ChatGPT inference or scientific finding.')
 try:
  f.bootstrap();pub=fixture.publish_fixture();f.rpc('publish_agent_prompt',pub)
  def fresh():
   with patch.object(autonomy,'wake',return_value={}):s=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic OpenClaw dispatch fixture',paper_url=fixture.URL,domain='Software',scope='SQL guards only')))
   t=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}));assert t['study_id']==s['id']
   request=model.request('Synthetic SQL request',dict(task='planning'));request['modelId']=dispatch.MODEL
   turn=autonomy.control(t,'begin',dict(id=f.uid(),request=request,request_raw=workflow.canonical(request).decode(),request_sha256=workflow.digest(workflow.canonical(request)),reserved_cents=100,prompt_version_id=pub['p_version_id'],model_id=dispatch.MODEL))
   body=dict(id=turn['id'],study_id=s['id'],task_id=t['id'],request_raw=turn['request_raw'],request_sha256=turn['request_sha256'],runtime=dispatch.VERSION)
   return t,turn,body
  def finish(t,turn):
   autonomy.control(t,'finish',dict(id=turn['id'],status='invalid-output',raw_response='{}',output=None,usage={},estimated_cents=None,reason='Synthetic SQL test ended; no provider call'))
   autonomy.advance(t,'blocked',reason='Synthetic local dispatch check ended')
  def heartbeat(status='ready'):return dispatch.rpc('heartbeat',dict(status=status,configuration=dict(runtime=dispatch.VERSION,paid_fallback=False)))
  def security():
   for role in ('anon','authenticated'):
    for table in ('research_model_dispatches','research_model_workers'):assert f.query("select has_table_privilege(current_user,"+f.sql_text(table)+",'SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
    assert f.query("select has_function_privilege(current_user,'research_model_dispatch(text,jsonb)','EXECUTE')",role=role)=='f'
   assert dispatch.health()['status']=='unavailable'
   return dict(private_relations=2,browser_rpc_denied=True,absent_status_not_ready=True)
  f.check('dispatch history and worker health are service-only with RLS',security)
  def admission():
   t,turn,body=fresh()
   f.rejects(lambda:dispatch.rpc('enqueue',dict(body,request_raw='{}')))
   first=dispatch.rpc('enqueue',body);assert first['replayed'] is False
   assert dispatch.rpc('enqueue',body)['replayed'] is True
   heartbeat('auth-required');assert dispatch.rpc('claim',{}) is None
   heartbeat();assert dispatch.health()['status']=='ready'
   with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:dispatch.rpc('claim',{}),range(2)))
   assert sum(c is not None for c in claims)==1
   job=next(c for c in claims if c)
   f.rejects(lambda:dispatch.rpc('finish',dict(id=turn['id'],token=f.uid(),status='failed',response_artifact_id=None,response_sha256=None,provenance={})))
   dispatch.rpc('finish',dict(id=turn['id'],token=job['lease_token'],status='paused-quota',response_artifact_id=None,response_sha256=None,provenance=dict(provider_retries=0,paid_fallback=False)))
   assert dispatch.rpc('claim',{}) is None
   assert dispatch.rpc('result',dict(id=turn['id'],study_id=t['study_id']))['status']=='paused-quota'
   f.rejects(lambda:f.query("update research_model_dispatches set status='queued' where id="+f.sql_text(turn['id'])))
   finish(t,turn)
   return dict(original_prompt_binding=True,duplicate_dispatch_not_executed=True,concurrent_claims=2,actual_claims=1,quota_pause_retained=True,terminal_receipt_immutable=True)
  f.check('one admitted turn produces at most one fenced dispatch; quota cannot trigger fallback',admission)
  def originals():
   t,turn,body=fresh();dispatch.rpc('enqueue',body);heartbeat();job=dispatch.rpc('claim',{})
   raw=b'{"output":{"message":"Synthetic response bytes"}}';record=f.store.artifact(t['study_id'],f.ACTOR,raw,f.uid(),'application/json',dict(kind='software-fixture',limitations='Not a model response'))
   f.store.append(t['study_id'],f.ACTOR,'artifacts',record)
   args=dict(id=turn['id'],token=job['lease_token'],status='complete',response_artifact_id=record['id'],response_sha256=record['sha256'],provenance=dict(runtime=dispatch.VERSION,measured_charges_usd=None))
   f.rejects(lambda:dispatch.rpc('finish',dict(args,response_sha256='a'*64)))
   dispatch.rpc('finish',args);result=dispatch.rpc('result',dict(id=turn['id'],study_id=t['study_id']))
   assert result['response_sha256']==workflow.digest(raw) and f.store.artifact_bytes(t['study_id'],record['id'])==raw
   assert 'lease_token' not in result and 'request_raw' not in result
   finish(t,turn)
   return dict(stored_response_hash_verified=True,wrong_hash_rejected=True,missing_cost_not_zero=True)
  f.check('completed dispatch requires a retained hash-verified private response',originals)
  def expiry():
   t,turn,body=fresh();dispatch.rpc('enqueue',body);heartbeat();job=dispatch.rpc('claim',{})
   f.query("update research_model_dispatches set lease_until=clock_timestamp()-interval '1 second' where id="+f.sql_text(turn['id']))
   assert dispatch.rpc('claim',{}) is None
   result=dispatch.rpc('result',dict(id=turn['id'],study_id=t['study_id']));assert result['status']=='unknown'
   f.rejects(lambda:dispatch.rpc('finish',dict(id=turn['id'],token=job['lease_token'],status='complete',response_artifact_id=None,response_sha256=None,provenance={})))
   finish(t,turn);heartbeat('paused-quota');assert dispatch.health()['status']=='paused-quota'
   return dict(expired_outcome_unknown=True,never_reclaimed=True,late_worker_refused=True)
  f.check('expired or paused provider work is never silently repeated',expiry)
  def temporary_recovery():
   t,turn,body=fresh();dispatch.rpc('enqueue',body)
   for reason in ('storage-low','refresh-temporary','client-configuration'):
    dispatch.rpc('heartbeat',dict(status='unavailable',configuration=dict(runtime=dispatch.VERSION,auth_recovery='openclaw-auth-recovery-v1',reason=reason,paid_fallback=False)))
    assert dispatch.health()['status']=='unavailable' and dispatch.rpc('claim',{}) is None
   heartbeat('auth-required');assert dispatch.rpc('claim',{}) is None
   heartbeat();job=dispatch.rpc('claim',{});assert job['id']==turn['id']
   dispatch.rpc('finish',dict(id=turn['id'],token=job['lease_token'],status='failed',response_artifact_id=None,response_sha256=None,provenance=dict(credential_status='unavailable',error_code='storage-unavailable',provider_request_sent=False,provider_calls=0,usage=None,paid_fallback=False)))
   result=dispatch.rpc('result',dict(id=turn['id'],study_id=t['study_id']))
   assert result['provenance']['provider_calls']==0 and result['provenance']['usage'] is None
   assert result['request_sha256']==body['request_sha256'] and result['status']=='failed'
   heartbeat();assert dispatch.rpc('claim',{}) is None
   f.rejects(lambda:f.query("update research_model_dispatches set status='queued' where id="+f.sql_text(turn['id'])))
   finish(t,turn)
   return dict(temporary_and_configuration_states_not_authentication=True,queued_identity_preserved_on_recovery=True,known_zero_provider_calls_preserved=True,missing_usage_not_zero=True,terminal_failed_attempt_not_replayed=True)
  f.check('availability recovery admits the original queued identity and preserves a pre-provider failure',temporary_recovery)
  def publication_guards():
   import copy,hashlib
   for name in ('202610200010_openclaw_prompt_candidate.sql','202610210001_openclaw_prompt_v10.sql','202610210002_openclaw_publication_guard.sql'):
    raw=(f.ROOT/'database'/name).read_bytes();f.report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();f.query(raw.decode())
   reports={v:(f.ROOT/('docs/openclaw-production-evaluation-'+v+'.json')).read_text() for v in ('v9','v10')}
   actual=json.loads(reports['v10']);args=dict(p_version_id=actual['prompt_id'],p_expected_active_version_id=pub['p_version_id'],p_expected_content_sha256=actual['prompt_sha256'],p_report=actual,p_actor='Synthetic local publication guard test; actual retained AI evaluation',p_module_id='research-autonomy')
   f.rejects(lambda:f.rpc('publish_agent_prompt',args))
   for version,raw in reports.items():
    report=json.loads(raw);f.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,recorded_by) values('+','.join([f.sql_text(report['prompt_id'])+'::uuid',f.sql_text(report['status']),f.sql_text(raw),f.sql_text(hashlib.sha256(raw.encode()).hexdigest()),f.sql_text('Local SQL fixture; original actual evaluation report')])+')')
   bad=copy.deepcopy(actual);bad['cases'][0]['raw_answer_reviewed']=False
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(args,p_report=bad)))
   rejected=json.loads(reports['v9'])
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(args,p_version_id=rejected['prompt_id'],p_expected_content_sha256=rejected['prompt_sha256'],p_report=rejected)))
   for role in ('anon','authenticated'):
    assert f.query("select has_table_privilege(current_user,'agent_prompt_evaluations','SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
   f.rejects(lambda:f.query("update agent_prompt_evaluations set outcome='passed'"))
   assert f.rpc('publish_agent_prompt',args)==actual['prompt_id']
   assert f.query("select count(*) from agent_prompt_evaluations where outcome='failed-substantive-review'")=='1'
   return dict(retained_actual_evaluations=2,failed_candidate_unpublishable=True,exact_sixteen_answer_report_required=True,ai_reviewer_nonindependent=True,private_immutable_reports=True,actual_provider_calls_in_sql_campaign=0)
  f.check('publication preserves failed candidate and requires the exact passing actual-answer review',publication_guards)
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  (f.DIRECTORY/'openclaw-validation-report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'))))
if __name__=='__main__':main()
