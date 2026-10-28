"""Real local SQL migration/lease checks, with no model or cloud calls."""
import datetime as dt,json,traceback
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_fixtures as fixture,model_dispatch as dispatch,workflow

def main():
 f.report.update(protocol='data-only-window-v2',actual_provider_calls=0)
 try:
  f.bootstrap();pub=fixture.publish_fixture();f.rpc('publish_agent_prompt',pub)
  raw=(f.ROOT/'database/202610280001_data_only_model_window.sql').read_bytes();f.query(raw.decode());f.report['new_migration_sha256']=workflow.digest(raw)
  def fresh():
   with patch.object(autonomy,'wake',return_value={}):s=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic method-window control',paper_url=fixture.URL,domain='Software',scope='SQL timing guards only')))
   t=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
   request=model.request('Synthetic SQL transport request',dict(task='planning'));request['modelId']=dispatch.MODEL
   turn=autonomy.control(t,'begin',dict(id=f.uid(),request=request,request_raw=workflow.canonical(request).decode(),request_sha256=workflow.digest(workflow.canonical(request)),reserved_cents=100,prompt_version_id=pub['p_version_id'],model_id=dispatch.MODEL))
   dispatch.rpc('enqueue',dict(id=turn['id'],study_id=s['id'],task_id=t['id'],request_raw=turn['request_raw'],request_sha256=turn['request_sha256'],runtime=dispatch.VERSION));dispatch.rpc('heartbeat',dict(status='ready',configuration={'runtime':dispatch.VERSION}))
   return t,turn
  def security():
   for role in ('anon','authenticated'):
    assert f.query("select has_function_privilege(current_user,'research_model_dispatch(text,jsonb)','EXECUTE')",role=role)=='f'
   return dict(browser_rpc_denied=True)
  f.check('new timing preserves private dispatch authorization',security)
  def lease():
   t,turn=fresh();job=dispatch.rpc('claim',{});assert job and job['id']==turn['id']
   remaining=f.query("select extract(epoch from lease_until-clock_timestamp()) from research_model_dispatches where id="+f.sql_text(job['id']))
   assert 225<float(remaining)<=235
   dispatch.rpc('finish',dict(id=turn['id'],token=job['lease_token'],status='failed',response_artifact_id=None,response_sha256=None,provenance={'scope':'Synthetic window control; no provider call'}))
   autonomy.control(t,'finish',dict(id=turn['id'],status='invalid-output',raw_response='{}',output=None,usage={},estimated_cents=None,reason='No actual provider call'))
   autonomy.advance(t,'blocked',reason='Synthetic check finished')
   return dict(dispatch_seconds=float(remaining),controller_wait_seconds=dispatch.WAIT_SECONDS,provider_calls=0)
  f.check('data-only dispatch uses a fenced 235-second lease within controller wait',lease)
  def short_task():
   t,turn=fresh();f.query("update research_autonomy_tasks set lease_until=clock_timestamp()+interval '230 seconds' where id="+f.sql_text(t['id']))
   assert dispatch.rpc('claim',{}) is None
   assert dispatch.rpc('result',dict(id=turn['id'],study_id=t['study_id']))['status']=='queued'
   return dict(insufficient_task_window_not_dispatched=True,queued_identity_retained=True)
  f.check('insufficient remaining task time never starts provider work',short_task)
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  (f.DIRECTORY/'method-window-validation.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'))))

if __name__=='__main__':main()
