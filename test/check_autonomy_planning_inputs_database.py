"""New-paper handoff: actual PDF/SQL/controller/local TCP; explicit model fixtures."""
import io,json,os,sys,traceback
from types import SimpleNamespace
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_sources as sources,bounded_network,network_execution,network_spec,store,worker,workflow
import autonomy_fixtures as fixture

QUOTE='A local echo service returns every requested payload byte.'
METHOD='Methods: 256 payload bytes, two exchanges and 3 ms application delay on one local host.'
URL='https://example.org/new-paper-planning-context-fixture.pdf'
def pdf():
 content=('BT /F1 12 Tf 20 230 Td ('+QUOTE+') Tj 0 -20 Td ('+METHOD+') Tj ET').encode()
 objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 800 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream'];raw=b'%PDF-1.4\n';offsets=[]
 for i,body in enumerate(objects,1):offsets.append(len(raw));raw+=str(i).encode()+b' 0 obj\n'+body+b'\nendobj\n'
 start=len(raw);raw+=b'xref\n0 6\n0000000000 65535 f \n'
 for offset in offsets:raw+=('%010d 00000 n \n'%offset).encode()
 return raw+b'trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'

def protocol(source):
 p=workflow.numerical_protocol(source['sha256'],'received_bytes','bytes',0,[dict(identity='declared-loopback',details=dict(test_config=dict(payload_bytes=256,exchanges=2,application_delay_ms=3)))])
 p.update(hypotheses=QUOTE,questions=['Does the declared software fixture retain both complete payload exchanges?'],stage='pilot',data_origin='new-empirical',planned_units=1,prior_exposure='Exposed synthetic paper/provider development fixture; not scientific validation.',statistics='Descriptive exchange measurements only; no confidence interval.',dependence='Two exchanges share a single local host and connection.',replication_unit='One complete invocation; exchanges are repeated observations.',sample_size_rationale='Two exchanges reproduce the synthetic software methods and verify persistence; no population inference.',coverage_limits='Local software fixture only; no paper or Internet validation.',resource_limits=dict(max_input_bytes=10000,max_observations=4,wall_seconds=60),metrics=[dict(name='received_bytes',units='bytes',planned_observations=2,lower_bound=0),dict(name='round_trip_time_ms',units='ms',planned_observations=2,lower_bound=0)],execution=dict(version=network_spec.VERSION,runner='bounded-tcp-v1',replications=1,limits=dict(wall_seconds=60,max_instances=1,max_output_bytes=32000,max_network_bytes=1024)))
 return p

def main():
 f.report.update(protocol='autonomy-planning-context-protocol-v1',design='Actual isolated PostgreSQL, PDF parser, controller, queue and loopback TCP. Synthetic paper, model replies, Google identity, Supabase Storage transport and AWS SDK. No live provider or production experiment.',conditional_gaps=['Actual native-model planning with the amended context','Deployed corrected API/worker; this is a local candidate'])
 try:
  f.bootstrap();f.rpc('publish_agent_prompt',fixture.publish_fixture());calls=[];observed=[];errors=[]
  body=dict(request_id=f.uid(),autonomous=True,paper=dict(title='Explicit new-paper planning handoff software fixture',paper_url=URL,domain='Software',scope='Declared software fixture; no scientific result',study_kind='paper'))
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,body)['id']
  def provider(request):
   c=json.loads(request['messages'][0]['content'][0]['text']);observed.append(c)
   out=dict(action='blocked',reason='missing-required-inputs',blockers=[],claims=[],check_id=None,proposal=None,ready=None,coverage_complete=False,assessment_label=None,evidence_ids=[])
   if c['task']=='discover':
    assert QUOTE in c['source_chunk']['text'] and METHOD in c['source_chunk']['text'];out.update(action='discover',reason='text-extracted',claims=[dict(page=1,quote=QUOTE,claim_type='operational')])
   elif c['task']=='planning':
    material=c.get('source_material',{});contracts=c.get('runner_contracts',{})
    if METHOD not in (material.get('inline_passage') or {}).get('text','') or 'test_config_schema' not in contracts.get('bounded-tcp-v1',{}):
     out['blockers']=[dict(kind='missing-data',detail='missing-source-data',required_input='The source passage and executable runner schema must reach the planner.')]
    else:
     assert c['registered_checks']==[] and c['proposal_contract']['field_shapes']['stage']=='pilot';out.update(action='propose',reason='prospective-pilot',proposal=dict(protocol=protocol(c['source']),experiment_type='new-measurement'))
   elif c['task'] in ('comprehension','critic'):
    assert METHOD in c['source_material']['inline_passage']['text'];assert set(c['runner_contracts'])=={'bounded-tcp-v1'};assert 'prior_attempts' not in c and 'previous_feedback' not in c
    out.update(action='review',reason='ready-within-scope',ready=True,coverage_complete=True)
   else:raise AssertionError('Fixture stops after measured execution; no scientific final label is synthesized.')
   return dict(stopReason='tool_use',output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(toolUseId='synthetic-planning-inputs',name='submit_assessment_step',input=out))])),usage=dict(inputTokens=100,outputTokens=100,totalTokens=200))
  import boto3
  def invoke(**kw):
   calls.append(kw);event=json.loads(kw['Payload']);actual=bounded_network.run(event['config']);return dict(Payload=io.BytesIO(workflow.canonical(actual)))
  client=SimpleNamespace(get_function_configuration=lambda **_:dict(MemorySize=128,Timeout=5,EphemeralStorage=dict(Size=512),Runtime='python3.12',Handler='index.handler'),invoke=invoke)
  policy=json.loads(autonomy.autonomy_costs.POLICY_PATH.read_bytes())['bounded_tcp'];layer=f.ROOT/'.runtime-autonomy-python/python'
  sys.path.insert(0,str(layer)) # The real parser explicitly forwards trusted sys.path entries.
  env=dict(PYTHONPATH=str(layer),NETWORK_BOUNDED_FUNCTION='arn:aws:lambda:us-east-1:395567831870:function:LocalPlanningInputsFixture:1',NETWORK_BOUNDED_POLICY_SHA256=workflow.digest(workflow.canonical(policy)))
  actual_step=autonomy.step
  def traced(task):
   try:return actual_step(task)
   except Exception:errors.append(traceback.format_exc());raise
  def full_flow():
   with patch.dict(os.environ,env),patch.object(sources,'fetch',return_value=(pdf(),URL,[dict(url=URL,status_code=200,media_type='application/pdf')])),patch.object(model,'invoke',side_effect=provider),patch.object(boto3,'client',return_value=client),patch.object(autonomy,'step',side_effect=traced):
    for cycle in range(16):
     f.query("update research_autonomy_tasks set next_at=clock_timestamp() where study_id="+f.sql_text(study)+" and status='waiting'")
     autonomy.handler({});worker.handler({})
     if errors:raise AssertionError(errors[0])
     runs=f.store.rows('runs',dict(study_id='eq.'+study))
     if runs:break
    else:raise AssertionError('New-paper path did not execute its reviewed prospective check')
   assert len(runs)==1 and runs[0]['status']=='complete' and len(calls)==1
   measurements=f.store.rows('measurements',dict(study_id='eq.'+study));assert len(measurements)==4 and all(m['status']=='recorded' for m in measurements)
   assert all(str(m['value'])=='256' for m in measurements if m['metric']=='received_bytes')
   assert {c['task'] for c in observed}=={'discover','planning','comprehension','critic'}
   return dict(cycles=cycle+1,actual_pdf_parser=True,registered_prepared_plans=0,source_passage_and_runner_contract_required=True,fresh_reviews=2,real_local_tcp_invocations=len(calls),measurements=len(measurements),live_model_calls=0,aws_calls=0)
  f.check('unregistered paper reaches actual measured TCP through source-bound planning and fresh reviews',full_flow)
  def originals():
   turns=f.store.rows('autonomy_turns',dict(study_id='eq.'+study));assert len(turns)==4 and all(t['status']=='complete' for t in turns)
   for turn in turns:assert workflow.digest(turn['request_raw'].encode())==turn['request_sha256'] and workflow.digest(turn['raw_response'].encode())==turn['response_sha256']
   artifacts=f.store.rows('artifacts',dict(study_id='eq.'+study));original=next(a for a in artifacts if a['provenance'].get('kind')=='bounded-tcp-original-lambda-response');raw=f.store.artifact_bytes(study,original['id']);assert workflow.digest(raw)==original['sha256']
   assert len(f.store.rows('assessments',dict(study_id='eq.'+study)))==0
   return dict(numbered_prompts=4,original_hashes_verified=True,original_response_sha256=original['sha256'],scientific_conclusion_not_fabricated=True)
  f.check('exact prompts originals configurations and observations persist without a manufactured verdict',originals)
  def cancellation():
   before=f.store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0];f.rpc('research_autonomy_control',dict(p_operation='cancel',p_actor=f.ACTOR,p_study=study,p_payload={}));autonomy.handler({});after=f.store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
   assert after['status']=='cancelled' and all(before[k]==after[k] for k in ('committed_cents','deadline_at','initial_prompt','initial_sha256','max_attempts'))
   assert len(f.store.rows('autonomy_turns',dict(study_id='eq.'+study)))==4
   return dict(cancellation_admits_no_new_calls=True,original_limits_and_evidence_preserved=True)
  f.check('cancelled work retains original history and admits no additional model calls',cancellation)
  f.report.update(passed=True,study_id=study,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False))
 except Exception as error:f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  (f.DIRECTORY/'planning-inputs-validation-report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'))))
if __name__=='__main__':main()
