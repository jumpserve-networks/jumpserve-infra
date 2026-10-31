"""Actual isolated Postgres builder admission, persistence and publication guards.

Local synthetic publication fixture is deliberate; no live AI or production
prompt is evaluated/published. Real migration bytes are replayed unchanged.
"""
import json,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,store,workflow,autonomy_methods,dispatch_recovery,autonomous_repair
import autonomy_fixtures
import experiment_builder,network_spec,network_execution
from check_autonomy_completion_database import DurableStorage

def main():
 f.report.update(protocol='experiment-builder-validation-v1',design=__doc__,live_provider_calls=0,new_cloud_instances=0)
 try:
  f.files=DurableStorage(f.DIRECTORY/'durable-storage')
  f.bootstrap()
  for name in ('202610210003_partial_assessment_recovery.sql','202610280001_data_only_model_window.sql','202610280002_assessment_budget_amendments.sql','202610280003_controller_reconciliation_window.sql','202610280004_autonomous_repair.sql','202610290001_builder_reconciliation.sql','202610300001_optional_assessment_budget.sql','202610300002_native_call_reconciliation.sql'):
   migration=(f.ROOT/'database'/name).read_bytes();f.report['migration_sha256'][name]=workflow.digest(migration);f.query(migration.decode())
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
   raw=workflow.canonical(dict(model='gpt-6.1-sol',store=False,stream=True,input=[{'role':'user','content':'Synthetic native prompt '+str(index)}]))
   artifact=store.artifact(study,f.ACTOR,raw,f.uid(),'application/json',{'kind':'builder-original','version':'experiment-builder-v1'});store.append(study,f.ACTOR,'artifacts',artifact)
   return dict(request_artifact_id=artifact['id'],request_sha256=artifact['sha256'],request_bytes=len(raw))
  def finish(call,status='complete'):
   raw=b'data: {"type":"response.completed","response":{"status":"completed","model":"gpt-6.1-sol","output":[]}}\n\n'
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
    p['decision']=dict(version=autonomy_methods.DECISION_VERSION,claim_id=claim['record']['id'],kind='recorded-comparisons',coverage='complete-under-tested-conditions',rationale='Explicit synthetic 10-ms cell only; no actual scientific execution claimed.',groups=[dict(id='cell',configuration='fixture',metric='latency',units='ms',observation_ids=['synthetic-cell'])],rules=[dict(id='target',operation='value',groups=['cell'],target='10',tolerance_absolute='0')])
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
   # Preserve the exhaustion ledger; authorize a separate finite fixture cap
   # rather than refunding commitments to make subsequent controls runnable.
   f.query('select research_autonomy_set_budget('+','.join([f.sql_text(study)+'::uuid',f.sql_text(f.uid())+'::uuid','20000','false',f.sql_text('Synthetic test operator'),f.sql_text('Prospective local SQL test headroom; no production authority')])+')',role='service_role')
   # Fixture clock change requires bypassing immutable original authorization,
   # only in this isolated database. Application code has no such operation.
   deadline=f.query('select deadline_at from research_autonomy_workflows where study_id='+f.sql_text(study))
   f.query('alter table research_autonomy_workflows disable trigger research_autonomy_workflow_immutable;update research_autonomy_workflows set deadline_at=clock_timestamp()+interval \'60 seconds\' where study_id='+f.sql_text(study)+';alter table research_autonomy_workflows enable trigger research_autonomy_workflow_immutable')
   assert rpc('begin',**begin(5))['denied']=='deadline'
   f.query('alter table research_autonomy_workflows disable trigger research_autonomy_workflow_immutable;update research_autonomy_workflows set deadline_at='+f.sql_text(deadline)+'::timestamptz where study_id='+f.sql_text(study)+';alter table research_autonomy_workflows enable trigger research_autonomy_workflow_immutable')
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
  def reconciliation():
   third=rpc('begin',**begin(7))
   rpc('finish',id=third['id'],status='unknown',response_artifact_id=None,response_sha256=None,usage=None,response_received=None,http_status=None,reason='Synthetic lost finish acknowledgement; terminal bytes exist only in the worker spool.')
   terminal=b'data: {"type":"response.completed","response":{"status":"completed","model":"gpt-6.1-sol","output":[]}}\n\n'
   calls=store.rows('builder_calls',dict(study_id='eq.'+study,dispatch_id='eq.'+turn,order='number.asc'))
   checkpoint=store.artifact(study,f.ACTOR,b'Explicit checkpoint transport fixture; no execution',f.uid(),'application/octet-stream',dict(kind='builder-reconciled-workspace',dispatch_id=turn));store.append(study,f.ACTOR,'artifacts',checkpoint)
   proof=dict(version='builder-dispatch-reconciliation-v1',dispatch_id=turn,request_sha256=workflow.digest(raw),original_status='unknown',container_cleanup='stopped',checkpoint=dict(artifact_id=checkpoint['id'],sha256=checkpoint['sha256']),calls=[{k:c[k] for k in ('id','request_sha256','response_sha256')} for c in calls])
   proof['calls'][-1]['response_sha256']=workflow.digest(terminal)
   def submit(value,role=None):
    original=workflow.canonical(value);a=store.artifact(study,f.ACTOR,original,f.uid(),'application/json',dict(kind='builder-dispatch-reconciliation',dispatch_id=turn));store.append(study,f.ACTOR,'artifacts',a)
    payload=dict(p_dispatch=turn,p_artifact=a['id'],p_sha256=a['sha256'],p_proof=value)
    if role:return f.query('select research_model_reconcile('+','.join([f.sql_text(turn)+'::uuid',f.sql_text(a['id'])+'::uuid',f.sql_text(a['sha256']),f.sql_text(json.dumps(value))+'::jsonb'])+')',role=role)
    return f.rpc('research_model_reconcile',payload)
   f.rejects(lambda:submit(proof)) # Still a live dispatch/task, no cleanup proof may override it.
   f.rpc('research_model_dispatch',dict(p_operation='finish',p_payload=dict(id=turn,token=job['lease_token'],status='unknown',provenance=dict(reason='Explicit synthetic interrupted parent'))))
   autonomy.control(task,'finish',dict(id=turn,status='unknown',raw_response=None,output=None,reason='Synthetic missed parent completion; no replay.',usage={},estimated_cents=None))
   autonomy.advance(task,'waiting',reason='Explicit retained unknown fixture; no provider replay.')
   before=json.loads(f.query('select row_to_json(w) from research_autonomy_workflows w'))
   unknown=json.loads(f.query('select row_to_json(d) from research_model_dispatches d where id='+f.sql_text(turn)))
   f.rejects(lambda:submit(dict(proof,calls=proof['calls'][:1])))
   f.rejects(lambda:submit(dict(proof,calls=[proof['calls'][0],proof['calls'][0]])))
   f.rejects(lambda:submit(dict(proof,calls=[dict(c,request_sha256='0'*64) for c in proof['calls']])))
   f.rejects(lambda:submit(dict(proof,request_sha256='0'*64)))
   for role in ('anon','authenticated'):
    f.rejects(lambda role=role:f.query('select * from research_model_reconciliations',role=role))
    f.rejects(lambda role=role:f.query('select * from research_builder_call_reconciliations',role=role))
    f.rejects(lambda role=role:submit(proof,role))
   assert f.rpc('research_model_reconciliation_candidates',dict(p_after=None))[0]['id']==turn
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);directory=root/turn;directory.mkdir();(directory/'logical.json').write_bytes(raw)
    workspace=root/'builder-workspaces'/task['id']/'workspace';workspace.mkdir(parents=True);(workspace/'experiment.py').write_text('print("retained software fixture")\n')
    (directory/'call-3-response.bin').write_bytes(terminal)
    captured=dict(version=dispatch_recovery.CALL_VERSION,call_id=third['id'],dispatch_id=turn,study_id=study,task_id=task['id'],request_sha256=third['request_sha256'],response_filename='call-3-response.bin',response_sha256=workflow.digest(terminal),status='complete',response_received=True,http_status=200)
    (directory/'call-3-completion.json').write_bytes(workflow.canonical(captured))
    original_reconcile=dispatch_recovery._reconcile_dispatches
    def checked_reconcile(*args):
     try:return original_reconcile(*args)
     except Exception:
      f.report['retained_reconciliation_failure']=traceback.format_exc();print(f.report['retained_reconciliation_failure']);raise
    with patch.object(experiment_builder,'container_action',return_value=[]) as cleanup,patch.object(experiment_builder,'normalize_workspace',return_value=b'{"bytes_unchanged":true,"fixture":true}'),patch.object(dispatch_recovery,'_reconcile_dispatches',side_effect=checked_reconcile):
     recovered=dispatch_recovery.reconcile_spool(root)
    assert recovered==[turn],recovered
    cleanup.assert_called_once_with(task['id'],'stop')
   result=store.rows('model_reconciliations',dict(dispatch_id='eq.'+turn,study_id='eq.'+study))[0]
   confirmed=dispatch_recovery.confirmed(task,unknown,{},autonomous_repair.original,autonomous_repair.rows)
   assert confirmed['native_calls']==3 and result['proof']['calls']==proof['calls']
   native=store.rows('builder_call_reconciliations',dict(study_id='eq.'+study,call_id='eq.'+third['id']))[0]
   payload=dict(p_call=third['id'],p_artifact=native['artifact_id'],p_sha256=native['sha256'],p_proof=native['proof'])
   assert f.rpc('research_builder_call_reconcile',payload)==native
   f.rejects(lambda:f.rpc('research_builder_call_reconcile',dict(payload,p_proof=dict(native['proof'],request_sha256='0'*64))))
   f.rejects(lambda:f.query("update research_builder_call_reconciliations set proof='{}'",role='service_role'))
   assert f.query("select status from research_builder_calls where id="+f.sql_text(third['id']))=='unknown'
   assert f.query('select research_builder_unresolved('+f.sql_text(task['id'])+'::uuid)',role='service_role')=='f'
   assert f.rpc('research_model_reconciliation_candidates',dict(p_after=None))==[]
   f.rejects(lambda:f.query("update research_model_reconciliations set proof='{}'",role='service_role'))
   f.rejects(lambda:f.query('delete from research_model_reconciliations',role='service_role'))
   after=json.loads(f.query('select row_to_json(w) from research_autonomy_workflows w'))
   for key in ('max_spend_cents','committed_cents','max_attempts','deadline_at','initial_prompt','initial_sha256'):assert before[key]==after[key],key
   assert json.loads(f.query('select row_to_json(d) from research_model_dispatches d where id='+f.sql_text(turn)))==unknown
   assert f.query("select count(*) from research_autonomy_events where event='model-dispatch-reconciled'")=='1'
   assert f.query('select count(*) from research_queue_jobs')=='0'
   return dict(original_unknown_retained=True,original_native_unknown_retained=True,lost_native_completion_reconciled=True,idempotent=True,browser_access_denied=True,distinct_call_hash_coverage=True,active_work_fenced=True,limits_unchanged=True,scientific_measurements=0,actual_worker_to_database_reconciliation=True,cleanup='mocked here; real Docker qualified separately')
  f.check('separate immutable reconciliation accounts for finished native calls without replay or budget reset',reconciliation)
  tables=('autonomy_workflows','autonomy_tasks','autonomy_turns','model_dispatches','builder_calls','builder_call_reconciliations','model_reconciliations','artifacts','autonomy_events')
  (f.DIRECTORY/'database-snapshot.json').write_bytes(workflow.canonical({name:store.rows(name,dict(study_id='eq.'+study,limit=1000)) for name in tables}))
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error));raise
 finally:
  (f.DIRECTORY/'report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps({'report':str(f.DIRECTORY/'report.json'),'passed':f.report.get('passed')}))
if __name__=='__main__':main()
