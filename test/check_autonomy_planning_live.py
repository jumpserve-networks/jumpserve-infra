"""Frozen real native planning -> fresh reviews -> TCP -> isolated Postgres."""
import hashlib,importlib.util,io,json,os,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
os.environ['RESEARCH_AI_RUNTIME']='openclaw-production-v1'
os.environ.setdefault('OPENCLAW_NODE',str(BACK/'experiments/openclaw_pilot/runtime/node_modules/node/bin/node'))
os.environ.setdefault('OPENCLAW_PACKAGE',str(BACK/'experiments/openclaw_pilot/runtime/node_modules/openclaw'))
os.environ.setdefault('OPENCLAW_AUTH_DIR',str(BACK/'experiments/openclaw_pilot/.subscription-auth'))
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_sources as sources,bounded_network,model_dispatch,network_spec,openclaw_runtime as runtime,store,worker,workflow
import autonomy_fixtures as fixture
spec=importlib.util.spec_from_file_location('handoff',ROOT/'test/check_autonomy_planning_inputs_database.py');handoff=importlib.util.module_from_spec(spec);spec.loader.exec_module(handoff)
QUOTE='In the specified loopback test, both of two 256-byte payload exchanges complete with 256 received bytes.'
METHOD='Methods: 256 payload bytes, two exchanges and 3 ms application delay on one local host.'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def main():
 directory=f.DIRECTORY;report=dict(protocol='planning-context-release-protocol-v1',status='running',model_calls=[],tcp_invocations=0,actual_charges_usd=None,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),design='Actual native OpenClaw, parser, controller, SQL and loopback TCP. Synthetic paper, Google owner, Storage API and AWS transport. No academic finding or production changes.');start=time.monotonic()
 def save():(directory/'planning-live-report.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  handoff.QUOTE=QUOTE;handoff.METHOD=METHOD;raw=handoff.pdf();(directory/'source-original.pdf').write_bytes(raw)
  manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());protocol=(ROOT/'docs/planning-context-release-protocol-v1.json').read_bytes()
  declaration=dict(protocol_sha256=sha(protocol),source_pdf_sha256=sha(raw),producer_sha256=sha(Path(__file__).read_bytes()),runtime_manifest=manifest,quote=QUOTE,methods=METHOD,max_native_calls=24,max_elapsed_seconds=1800,max_tcp_invocations=1,classification=report['design'])
  (directory/'planning-live-frozen.json').write_bytes(workflow.canonical(declaration));(directory/'producer.py').write_bytes(Path(__file__).read_bytes())
  for name,digest in manifest['files'].items():assert sha((BACK/'research_workflow'/name).read_bytes())==digest
  runtime.verify_runtime();report['catalog']=runtime.catalog(runtime.credential());save()
  f.bootstrap()
  for name in ('202610200010_openclaw_prompt_candidate.sql','202610210001_openclaw_prompt_v10.sql','202610210002_openclaw_publication_guard.sql'):
   f.query((ROOT/'database'/name).read_text())
  for version in ('v9','v10'):
   original=(ROOT/('docs/openclaw-production-evaluation-'+version+'.json')).read_text();retained=json.loads(original)
   f.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,recorded_by) values('+','.join([f.sql_text(retained['prompt_id'])+'::uuid',f.sql_text(retained['status']),f.sql_text(original),f.sql_text(sha(original.encode())),f.sql_text('Local control copies original historical evaluation; no new production publication')])+')')
  active=json.loads(f.query("select coalesce((select to_json(active_version_id) from agent_prompt_settings where module_id='research-autonomy'),'null'::json)"))
  f.rpc('publish_agent_prompt',dict(p_version_id=retained['prompt_id'],p_expected_active_version_id=active,p_expected_content_sha256=retained['prompt_sha256'],p_report=retained,p_actor='Local control; unchanged historically evaluated production prompt',p_module_id='research-autonomy'))
  prompt,system=model.load_prompt();report['prompt']=dict(id=prompt['id'],version=prompt['version'],sha256=sha(system.encode()));save()
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Native planning integration software release control',paper_url='https://example.org/native-planning-control.pdf',domain='Software',scope='Synthetic software control of the specified loopback methods only. No academic research result. No registered plan.',study_kind='paper')))['id']
  report['study_id']=study;report['database']=f.DATABASE;save()
  def native(request):
   assert len(report['model_calls'])<24 and time.monotonic()-start<1800,'Frozen live evaluation resources reached'
   index=len(report['model_calls'])+1;context=json.loads(request['messages'][0]['content'][0]['text']);entry=dict(number=index,task=context['task'],request_sha256=sha(workflow.canonical(request)));report['model_calls'].append(entry);save()
   if context['task']=='planning':assert context['source_material']['text_available'] and QUOTE in context['source_material']['inline_passage']['text'] and context['runner_contracts']['bounded-tcp-v1']['executor_configured']
   answer,receipt=runtime.execute(request,directory/('native-'+str(index)));entry['receipt']=receipt;save()
   if answer is None:raise ValueError('Native outcome unconfirmed; do not replay')
   entry['output']=model.parse(answer);entry['response_sha256']=sha(workflow.canonical(answer));save();answer.setdefault('usage',{})['research_runtime']=receipt
   return answer
  original_call=model.call
  def actual_call(task,context,control):return original_call(task,context,control,invoke_provider=native)
  def invoke(**kw):
   assert report['tcp_invocations']==0,'No repeated TCP invocation';event=json.loads(kw['Payload']);cfg=event['config'];assert cfg==dict(payload_bytes=256,exchanges=2,application_delay_ms=3),'Original source methods changed'
   report['tcp_invocations']+=1;save();actual=bounded_network.run(cfg);return dict(Payload=io.BytesIO(workflow.canonical(actual)))
  import boto3
  client=SimpleNamespace(get_function_configuration=lambda **_:dict(MemorySize=128,Timeout=5,EphemeralStorage=dict(Size=512),Runtime='python3.12',Handler='index.handler'),invoke=invoke)
  layer=ROOT/'.runtime-autonomy-python/python';sys.path.insert(0,str(layer));policy=json.loads(autonomy.autonomy_costs.POLICY_PATH.read_bytes())['bounded_tcp']
  env=dict(NETWORK_BOUNDED_FUNCTION='arn:aws:lambda:us-east-1:395567831870:function:LocalNativePlanningControl:1',NETWORK_BOUNDED_POLICY_SHA256=workflow.digest(workflow.canonical(policy)))
  errors=[];original_step=autonomy.step
  def traced(task):
   try:return original_step(task)
   except Exception:errors.append(traceback.format_exc());raise
  with patch.dict(os.environ,env),patch.object(sources,'fetch',return_value=(raw,'https://example.org/native-planning-control.pdf',[dict(status_code=200,media_type='application/pdf',software_fixture=True)])),patch.object(model,'call',side_effect=actual_call),patch.object(boto3,'client',return_value=client),patch.object(autonomy,'step',side_effect=traced):
   for cycle in range(40):
    assert time.monotonic()-start<1800,'Frozen elapsed resources reached'
    model_dispatch.rpc('heartbeat',dict(status='ready',configuration=dict(runtime=runtime.VERSION,local_native_bridge=True,paid_fallback=False)))
    f.query("update research_autonomy_tasks set next_at=clock_timestamp() where study_id="+f.sql_text(study)+" and status='waiting'")
    result=autonomy.handler({});worker.handler({});save()
    if errors:raise AssertionError(errors[0])
    if any(c.get('receipt',{}).get('status')!='complete' for c in report['model_calls']):raise ValueError('Native call failed; retain unknown outcome')
    runs=store.rows('runs',dict(study_id='eq.'+study))
    if runs:break
    tasks=store.rows('autonomy_tasks',dict(study_id='eq.'+study));assert not any(t['status'] in ('blocked','budget','deadline','provider-paused') for t in tasks),'Controller stopped with a retained blocker'
   else:raise ValueError('Evaluation ended before complete measured run')
  measurements=store.rows('measurements',dict(study_id='eq.'+study));assert len(runs)==1 and runs[0]['status']=='complete' and len(measurements)==4 and all(m['status']=='recorded' for m in measurements)
  assert sum(m['metric']=='received_bytes' and str(m['value'])=='256' and m['units']=='bytes' for m in measurements)==2
  assert sum(m['metric']=='round_trip_time_ms' and m['units']=='ms' and float(m['value'])>=0 for m in measurements)==2
  turns=store.rows('autonomy_turns',dict(study_id='eq.'+study));assert len(turns)==len(report['model_calls']) and all(t['status']=='complete' and sha(t['request_raw'].encode())==t['request_sha256'] and sha(t['raw_response'].encode())==t['response_sha256'] for t in turns)
  reviews=[t for t in turns if t['stage'] in ('comprehension','critic')];assert {t['stage'] for t in reviews}=={'comprehension','critic'} and all(t['output']['ready'] for t in reviews[-2:])
  originals=[]
  for artifact in store.rows('artifacts',dict(study_id='eq.'+study)):
   data=store.artifact_bytes(study,artifact['id']);assert sha(data)==artifact['sha256'];(directory/('original-'+artifact['sha256'])).write_bytes(data);originals.append(dict(id=artifact['id'],sha256=artifact['sha256'],byte_count=len(data),provenance=artifact['provenance']))
  for name,records in [('turns',turns),('measurements',measurements),('runs',runs),('artifacts',originals)]: (directory/(name+'.json')).write_text(json.dumps(records,indent=2)+'\n')
  assert not store.rows('assessments',dict(study_id='eq.'+study))
  f.rpc('research_autonomy_control',dict(p_operation='cancel',p_actor=f.ACTOR,p_study=study,p_payload={}))
  report.update(status='awaiting-substantive-review',stored_turns=len(turns),stored_measurements=4,original_hashes_verified=True,actual_fresh_ai_reviews=2,academic_assessments=0,cancelled_local_control=True)
 except Exception as error:report.update(status='failed',reason=str(error),traceback=traceback.format_exc());raise
 finally:report.update(wall_seconds=time.monotonic()-start,ended_at=workflow.now());save();print(json.dumps(dict(directory=str(directory),status=report['status'],calls=len(report['model_calls']),reason=report.get('reason'))))
if __name__=='__main__':main()
