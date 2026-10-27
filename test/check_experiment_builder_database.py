"""Actual isolated Postgres builder admission, persistence and publication guards.

Local synthetic publication fixture is deliberate; no live AI or production
prompt is evaluated/published. Real migration bytes are replayed unchanged.
"""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,store,workflow
import autonomy_fixtures
import experiment_builder,network_spec,network_execution

def main():
 f.report.update(protocol='experiment-builder-validation-v1',design=__doc__,live_provider_calls=0,new_cloud_instances=0)
 try:
  f.bootstrap()
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Builder software fixture',paper_url='https://example.org/builder-fixture.pdf',domain='Software verification',scope='Synthetic original prompt and native round-trip persistence only')))['id']
  initial=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  records=autonomy_fixtures.plan()['records'];source=next(r for r in records if r['kind']=='sources');claim=next(r for r in records if r['kind']=='claims')
  store.append_bundle(study,f.ACTOR,[source,claim]);autonomy.seed(initial,[claim['record']],{});autonomy.advance(initial,'finished',reason='Explicit synthetic intake fixture.')
  task=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  autonomy.advance(task,'queued',stage='building',reason='Synthetic implementation blocker.')
  task=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  prompt=f.uid()
  # Test-only, already-published fixture; never misrepresented as an evaluated
  # production candidate. The real draft remains unpublished.
  f.query("insert into agent_prompt_versions(id,module_id,version,system_prompt,research_context,published_at,created_by,updated_by) values("+f.sql_text(prompt)+",'research-experiment-builder','synthetic-builder-fixture','Explicit synthetic system','No scientific review',clock_timestamp(),'synthetic fixture','synthetic fixture');update agent_prompt_settings set active_version_id="+f.sql_text(prompt)+" where module_id='research-experiment-builder'")
  request={'modelId':'gpt-6.1-sol','builder':{'version':'experiment-builder-v1','context':{'task':'building'}}};raw=workflow.canonical(request);turn=f.uid()
  admitted=autonomy.control(task,'begin',dict(id=turn,request=request,request_raw=raw.decode(),request_sha256=workflow.digest(raw),reserved_cents=100,prompt_version_id=prompt,model_id='gpt-6.1-sol'))
  f.rpc('research_model_dispatch',dict(p_operation='enqueue',p_payload=dict(id=turn,study_id=study,task_id=task['id'],runtime='openclaw-production-v1',request_raw=raw.decode(),request_sha256=workflow.digest(raw))))
  f.rpc('research_model_dispatch',dict(p_operation='heartbeat',p_payload=dict(status='ready',configuration={'kind':'synthetic'})))
  job=f.rpc('research_model_dispatch',dict(p_operation='claim',p_payload={}))
  def rpc(op,**kw):return experiment_builder.rpc(op,job,**kw)
  def begin(index):
   raw=workflow.canonical(dict(model='gpt-6.1-sol',input=[{'role':'user','content':'Synthetic native prompt '+str(index)}]))
   artifact=store.artifact(study,f.ACTOR,raw,f.uid(),'application/json',{'kind':'builder-original','version':'experiment-builder-v1'});store.append(study,f.ACTOR,'artifacts',artifact)
   return dict(request_artifact_id=artifact['id'],request_sha256=artifact['sha256'],request_bytes=len(raw))
  def finish(call,status='complete'):
   raw=b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
   artifact=store.artifact(study,f.ACTOR,raw,f.uid(),'application/octet-stream',{'kind':'builder-original','version':'experiment-builder-v1'});store.append(study,f.ACTOR,'artifacts',artifact)
   return rpc('finish',id=call['id'],status=status,response_artifact_id=artifact['id'],response_sha256=artifact['sha256'],usage=None,response_received=True,http_status=200,reason=None)
  original_cents=int(f.query('select committed_cents from research_autonomy_workflows'))
  first=begin(1)
  def admission():
   call=rpc('begin',**first);assert call['reserved_cents']==0 and call['number']==admitted['number']
   assert rpc('begin',**first)['denied']=='retained-request'
   assert rpc('begin',**begin(2))['denied']=='unconfirmed-call'
   finish(call)
   second=rpc('begin',**begin(3));assert second['reserved_cents']==100 and second['number']==call['number']+1;finish(second)
   assert int(f.query('select committed_cents from research_autonomy_workflows'))==original_cents+100
   assert int(f.query('select attempts from research_autonomy_tasks where id='+f.sql_text(task['id'])))==2
   f.rejects(lambda:finish(second))
   assert rpc('begin',**first)['denied']=='retained-request'
   with patch.dict('os.environ',RESEARCH_BUILDER_ENABLED='true'):
    history=autonomy.history(study,task['id']);assert len(history['builder_calls'])==2 and history['coverage']['total']==2
   return {'native_calls':2,'additional_reservation_cents':100,'immutable_terminals':True}
  f.check('every native request admitted once with original paper commitments',admission)
  def packages():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);project=root/'project';project.mkdir()
    for name,value in {'experiment.py':'print("explicit software fixture")\n','requirements.lock':'','system-packages.lock.json':'[]','build-evidence.json':json.dumps(dict(commands=[],checks=[],limitations=['No execution claimed by this catalog fixture']))}.items():(project/name).write_text(value)
    config=dict(identity='fixture',details=dict(test_config=dict(mode='emulated',arguments=[],parameters={})))
    p=workflow.numerical_protocol(source['record']['sha256'],'latency','ms',0,[config]);p.update(hypotheses=claim['record']['description'],stage='pilot',data_origin='simulation',planned_units=1,prior_exposure='Exposed deterministic software fixture authored before this check; no independent scientific validation.')
    p['resource_limits'].update(wall_seconds=600,max_input_bytes=1000000)
    p['metrics'][0]['planned_observations']=1
    p['execution']=dict(version=network_spec.VERSION,runner='built-package-v1',replications=1,limits=dict(wall_seconds=600,max_instances=1,max_output_bytes=1000000,max_network_bytes=1000000))
    (root/'candidate.json').write_bytes(workflow.canonical(dict(protocol=p,experiment_type='independent-check')))
    candidate=experiment_builder.freeze_candidate(job,root)
    validated=autonomy.validate_proposal(task,candidate)
    row=store.rows('builder_packages',dict(study_id='eq.'+study,limit=1))[0]
    assert row['id']==job['id'] and row['status']=='candidate'
    assert experiment_builder.project_document(validated,study)['files'][0]['path']=='build-evidence.json'
    spec=network_spec.specs(validated['protocol'])[0]
    with patch.dict('os.environ',NETWORK_BUILT_PACKAGE_FUNCTION='arn:aws:lambda:us-east-1:395567831870:function:SyntheticOnly:1'):
     assert network_execution.validate_input(study,{'document':validated['protocol']},workflow.canonical(spec))==spec
    f.rejects(lambda:f.query("update research_builder_packages set version='rewrite'"))
    return {'catalog_status':'candidate, not reviewed','source_originals':'round-trip verified','frozen_input':'accepted','execution_claimed':False}
  f.check('freeze original files and register a source-specific immutable package candidate',packages)
  def limits():
   f.query('update research_autonomy_workflows set committed_cents=10000 where study_id='+f.sql_text(study))
   assert rpc('begin',**begin(4))['denied']=='budget'
   f.query('update research_autonomy_workflows set committed_cents='+str(original_cents+100)+' where study_id='+f.sql_text(study))
   # Fixture clock change requires bypassing immutable original authorization,
   # only in this isolated database. Application code has no such operation.
   f.query('alter table research_autonomy_workflows disable trigger research_autonomy_workflow_immutable;update research_autonomy_workflows set deadline_at=clock_timestamp()+interval \'60 seconds\' where study_id='+f.sql_text(study)+';alter table research_autonomy_workflows enable trigger research_autonomy_workflow_immutable')
   assert rpc('begin',**begin(5))['denied']=='deadline'
   return {'budget':'refused','deadline':'refused'}
  f.check('budget and original elapsed limits cannot admit extra calls',limits)
  def security():
   f.rejects(lambda:f.query('select * from research_builder_calls',role='anon'))
   f.rejects(lambda:f.query('update research_builder_calls set request_sha256=repeat(\'0\',64)',role='authenticated'))
   f.rejects(lambda:f.query("update research_builder_calls set reason='rewrite'"))
   f.rejects(lambda: f.rpc('research_builder_call',dict(p_operation='begin',p_payload=dict(dispatch_id=turn,token=f.uid(),**begin(6)))))
   candidate='6102d16d-c5cf-5f1c-8fc7-2df2899da972';sha=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(candidate))
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(p_version_id=candidate,p_expected_active_version_id=prompt,p_expected_content_sha256=sha,p_report={},p_actor='Synthetic fixture',p_module_id='research-experiment-builder')))
   authority=experiment_builder.action_policy()
   publication=dict(p_version_id=candidate,p_expected_active_version_id=prompt,p_expected_content_sha256=sha,p_actor='Synthetic fixture',p_module_id='research-experiment-builder')
   authority_report=dict(execution_policy_version=authority['version'],execution_policy_sha256=authority['sha256'],authority_amendment='experiment-action-policy-live-amendment-v1',authority_case_reviews=[])
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(publication,p_report=authority_report)))
   authority_report['authority_case_reviews']=[dict(name=n,passed=False,actual_answer_reviewed=True,provider_response_sha256='a'*64,review_notes='Deliberate failed synthetic judgment',source_set='development') for n in ('routine-setup-no-consent-loop','unsupported-capability-not-executed')]
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(publication,p_report=authority_report)))
   for case in authority_report['authority_case_reviews']:case['passed']=True
   # Authority notes alone cannot replace the original ten-case live guard.
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(publication,p_report=authority_report)))
   assert f.query('select published_at is null from agent_prompt_versions where id='+f.sql_text(candidate))=='t'
   v2='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27'
   v2_sha=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(v2))
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(publication,p_version_id=v2,p_expected_content_sha256=v2_sha,p_report=authority_report)))
   assert f.query('select published_at is null from agent_prompt_versions where id='+f.sql_text(v2))=='t'
   assert 'absolute filename' in f.query('select system_prompt from agent_prompt_versions where id='+f.sql_text(v2))
   return {'RLS':'enabled','browser_writes':'denied','stale_fence':'refused','draft_publication':'refused','authority_checks':'required; original live checks retained'}
  f.check('RLS, immutable history, fences and publication checks',security)
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error));raise
 finally:
  (f.DIRECTORY/'report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps({'report':str(f.DIRECTORY/'report.json'),'passed':f.report.get('passed')}))
if __name__=='__main__':main()
