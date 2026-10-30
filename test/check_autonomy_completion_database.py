"""Actual PDF/controller/native CLI/SQL queue/TCP/persistence integration.

Google identity, Storage transport, wake delivery, Lambda SDK transport and every
model judgment are explicit fixtures. No live provider, AWS launch or production
mutation. The native CLI, dispatch admission/outbox, PDF parser, controller,
Postgres, queue, TCP exchanges and evidence calculation are real implementations.
"""
import copy,io,json,os,sys,threading,time,traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ['RESEARCH_AI_RUNTIME']='openclaw-production-v1'
os.environ['RESEARCH_AUTONOMY_ENABLED']='true'
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_methods as methods,bounded_network,model_dispatch,network_spec,paper_uploads,openclaw_runtime as runtime,siwc_protocol as wire,store,worker,workflow

TITLE='Unattended TCP software verification fixture'
CLAIMS=['Each host-local TCP echo returns 32 bytes under the declared configuration.','Each host-local TCP echo returns 33 bytes under the declared configuration.']

def pdf():
 sys.path.insert(0,str(f.ROOT/'.runtime-autonomy-python/python'))
 from pypdf import PdfWriter
 from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
 writer=PdfWriter();page=writer.add_blank_page(width=650,height=400)
 font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
 page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
 content=DecodedStreamObject();content.set_data(('BT /F1 9 Tf 20 300 Td ('+TITLE+') Tj 0 -20 Td ('+CLAIMS[0]+') Tj 0 -20 Td ('+CLAIMS[1]+') Tj ET').encode());page[NameObject('/Contents')]=writer._add_object(content)
 output=io.BytesIO();writer.write(output);return output.getvalue()

def proposal(context):
 claim=context['claim'];cfg=dict(payload_bytes=32,exchanges=2,application_delay_ms=0)
 p=workflow.numerical_protocol(context['source']['sha256'],'received_bytes','bytes',0,[dict(identity='host-loopback',details=dict(test_config=cfg))])
 p.update(hypotheses=claim['description'],stage='pilot',data_origin='new-empirical',planned_units=1,prior_exposure='Exposed software fixture; synthetic judgments, no paper or model-quality validation.',statistics='Descriptive observed-byte comparison only; no confidence interval or population inference.',dependence='Two exchanges share a connection, process and host. Both claims share the exact acquisition.',replication_unit='One complete runner invocation, not individual exchanges.',sample_size_rationale='Two exchanges exercise identity matching and persistence; no statistical power claim.',coverage_limits='Only this host-local 32-byte configuration; no CUBIC, netem, Internet or broader paper validation.',stopping_rule='One invocation, two exchanges or the runner deadline. No outcome-based reacquisition.',exclusions='No failed observation discarded; missing/invalid data cannot produce a conclusive finding.')
 p['metrics']=[dict(name='received_bytes',units='bytes',planned_observations=2,lower_bound=0),dict(name='round_trip_time_ms',units='ms',planned_observations=2,lower_bound=0)]
 p['resource_limits'].update(wall_seconds=60,max_input_bytes=10000,max_observations=4)
 p['execution']=dict(version=network_spec.VERSION,runner='bounded-tcp-v1',replications=1,limits=dict(wall_seconds=60,max_instances=1,max_output_bytes=32000,max_network_bytes=1024),exclusive_resources=[])
 p['decision']=dict(version=methods.DECISION_VERSION,claim_id=claim['id'],kind='recorded-comparisons',coverage='complete-under-tested-conditions',rationale='Exposed software fixture: compare the prespecified mean received bytes with the exact quoted number. No scientific generalization.',groups=[dict(id='echo-bytes',configuration='host-loopback',metric='received_bytes',units='bytes',observation_ids=['0','1'])],rules=[dict(id='quoted-bytes',operation='value',groups=['echo-bytes'],target='33' if '33 bytes' in claim['description'] else '32',tolerance_absolute='0')])
 return dict(protocol=p,experiment_type='new-measurement')

def synthetic_decision(logical):
 c=json.loads(logical['messages'][0]['content'][0]['text']);stage=c['task']
 value=dict(action='blocked',reason='missing-required-inputs',blockers=[],claims=[],check_id=None,proposal=None,ready=None,coverage_complete=False,assessment_label=None,evidence_ids=[])
 if stage=='discover':
  value.update(action='discover',reason='text-extracted',claims=[dict(page=c['source_chunk']['page'],quote=q,claim_type='numerical') for q in CLAIMS])
  if c.get('paper_metadata_requested'):value['paper_metadata']=dict(title=dict(text=TITLE,quote=TITLE,page=1),domain=dict(text='Networking',quote=CLAIMS[0],page=1))
 elif stage=='paper-review-selection':
  candidates=c['candidates'];value.update(action='discover',reason='text-extracted',paper_review_selection=dict(central_claims=[dict(claim_id=candidates[0]['id'],label='First explicit software claim')],testable_findings=[dict(claim_id=candidates[1]['id'],label='Second explicit software claim')],rationale='Synthetic organization fixture, not AI or human scientific review.'))
 elif stage=='planning':value.update(action='propose',reason='prospective-pilot',proposal=proposal(c))
 elif stage in ('comprehension','critic'):value.update(action='review',reason='ready-within-scope',ready=True,coverage_complete=True)
 elif stage=='assessment':
  finding=c.get('controller_numeric_check');assert finding,'Complete controller evidence required'
  value.update(action='assess',reason='matched-numeric-check',assessment_label=finding['label'],coverage_complete=True)
 else:raise AssertionError('Unexpected phase '+stage)
 return value

class Response(io.BytesIO):
 status=200;headers={}
 def read1(self,n):return self.read(n)

def main():
 f.report.update(protocol='autonomy-completion-protocol-v1',design=__doc__,live_provider_calls=0,new_cloud_instances=0,synthetic_judgments=True,actual_native_cli=True,manual_running_campaign_edits=0)
 f.report['conditional_gaps']=['Live model answer quality','Real Google browser authentication','Remote Supabase Storage upload/CORS','Deployed Lambda/cloud-job execution','Actual retained paper assessment completion']
 protocol=(f.ROOT/'docs/autonomy-completion-protocol-v1.json').read_bytes();(f.DIRECTORY/'protocol.json').write_bytes(protocol)
 f.report['protocol_sha256']=workflow.digest(protocol)
 halt=threading.Event();errors=[];native=[];spool=f.DIRECTORY/'native-spool';spool.mkdir();requests=[]
 package=f.ROOT.parent/'jumpserve-back-end/experiments/openclaw_pilot/runtime/node_modules/openclaw';node=package.parent/'node/bin/node'
 assert node.exists() and json.loads((package/'package.json').read_bytes())['version']=='2026.10.5'
 def process(job):
  try:
   logical=json.loads(job['request_raw']);expected=workflow.canonical(wire.response_request(logical));calls=[]
   def transport(method,url,token,body):
    assert method=='POST' and url=='https://api.openai.com/v1/responses' and token=='explicit-synthetic-no-credential' and body==expected
    calls.append(workflow.digest(body));value=synthetic_decision(logical)
    completed=dict(type='response.completed',response=dict(status='completed',model=runtime.MODEL,output=[dict(type='message',role='assistant',content=[dict(type='output_text',text=workflow.canonical(value).decode())])],usage=dict(input_tokens=100,output_tokens=30,total_tokens=130)))
    return Response(b'data: '+workflow.canonical(completed)+b'\n\n')
   directory=spool/job['id'];answer,receipt=runtime.execute(logical,directory,token_source=lambda:'explicit-synthetic-no-credential',transport=transport)
   receipt.update(qualification_provider='explicit synthetic response; no live inference',usage_origin='synthetic development fixture, not measured model usage')
   assert receipt['status']=='complete' and len(calls)==1,receipt
   marker=runtime.save_completion(job,directory,answer,receipt,spool/'pending-completions');assert runtime.persist_completed(job,directory);marker.unlink()
   native.append(dict(dispatch=job['id'],original_request_sha256=job['request_sha256'],upstream_sha256=calls[0],sizes=receipt['request_sizes']))
  except Exception:errors.append(traceback.format_exc());halt.set()
 def pump():
  with ThreadPoolExecutor(max_workers=2) as pool:
   active=[]
   while not halt.is_set():
    active=[future for future in active if not future.done()]
    if len(active)<2:
     job=model_dispatch.rpc('claim',{})
     if job:active.append(pool.submit(process,job))
    halt.wait(.15)
 def sdk_invoke(**kwargs):
  assert kwargs['InvocationType']=='RequestResponse';event=json.loads(kwargs['Payload']);requests.append(event)
  return dict(StatusCode=200,Payload=io.BytesIO(workflow.canonical(bounded_network.handler(event))))
 try:
  f.bootstrap()
  migration=f.ROOT/'database/202610290001_builder_reconciliation.sql';f.query(migration.read_text());f.report['migration_sha256'][migration.name]=workflow.digest(migration.read_bytes())
  prompt=f.uid();f.query("insert into agent_prompt_versions(id,module_id,version,system_prompt,research_context,published_at,created_by,updated_by) values("+f.sql_text(prompt)+",'research-autonomy','research-autonomy-v10','Explicit synthetic integration prompt','No live model or scientific review',clock_timestamp(),'synthetic fixture','synthetic fixture');update agent_prompt_settings set active_version_id="+f.sql_text(prompt)+" where module_id='research-autonomy'")
  model_dispatch.rpc('heartbeat',dict(status='ready',configuration=dict(kind='explicit synthetic local provider',paid_fallback=False)))
  policy=json.loads(autonomy.autonomy_costs.POLICY_PATH.read_bytes())['bounded_tcp'];env=dict(NETWORK_BOUNDED_FUNCTION='arn:aws:lambda:us-east-1:395567831870:function:LocalCompletionFixture:1',NETWORK_BOUNDED_POLICY_SHA256=workflow.digest(workflow.canonical(policy)))
  client=SimpleNamespace(get_function_configuration=lambda **kwargs:dict(MemorySize=128,Timeout=5,Runtime='python3.12',Handler='index.handler',EphemeralStorage={'Size':512}),invoke=sdk_invoke)
  with patch.object(runtime,'NODE',node),patch.object(runtime,'PACKAGE',package),patch.object(autonomy,'wake',return_value=dict(status='explicit local notification fixture')),patch.dict(os.environ,env),patch('boto3.client',return_value=client),patch.object(model_dispatch,'WAIT_SECONDS',45):
   thread=threading.Thread(target=pump,daemon=True);thread.start()
   raw=pdf();study=f.uid();reserve=dict(action='reserve',request_id=study,filename='unattended-software-fixture.pdf',sha256=workflow.digest(raw),byte_count=len(raw))
   paper_uploads.submit(f.ACTOR,reserve);f.transport('/storage/v1/object/'+paper_uploads.BUCKET+'/'+study+'/'+reserve['sha256'],'POST',raw);paper_uploads.submit(f.ACTOR,dict(action='prepare',request_id=study))
   began=time.monotonic()
   def tick():
    assert time.monotonic()-began<480,'Local integration time limit'
    model_dispatch.rpc('heartbeat',dict(status='ready',configuration=dict(kind='explicit synthetic local provider',paid_fallback=False)))
    result=autonomy.handler({})
    if errors:raise AssertionError(errors[0])
    return result
   for _ in range(10):
    tick();review=paper_uploads.review(f.ACTOR,study)
    if review['status']=='ready':break
   else:raise AssertionError('Paper preparation did not become ready: '+str(review))
   assert len(review['claims'])==2 and f.query('select count(*) from research_queue_jobs')=='0'
   selected=[c['id'] for c in review['claims']]
   paper_uploads.submit(f.ACTOR,dict(action='confirm',request_id=study,title=review['title'],domain=review['domain'],revision=review['revision'],claim_ids=selected,selection=dict(central_claims=selected[:1],testable_findings=selected[1:])))
   original=store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
   before_claims=workflow.digest(workflow.canonical(store.rows('claims',dict(study_id='eq.'+study))))
   for cycle in range(20):
    tick();worker.handler({})
    tasks=store.rows('autonomy_tasks',dict(study_id='eq.'+study))
    if all(t['status'] in ('resolved','finished') for t in tasks):break
    # Real poll delay is honored; no database clock/status/criteria edits.
    waiting=[t for t in tasks if t['status']=='waiting']
    if waiting:halt.wait(5)
   else:raise AssertionError('Assessment did not finish: '+str([(t['stage'],t['status'],t['reason']) for t in tasks]))
   workflow_row=store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
   assert workflow_row['status']=='completed',workflow_row
   for field in ('initial_prompt','initial_sha256','max_spend_cents','deadline_at','max_attempts'):assert workflow_row[field]==original[field],field
   assert workflow.digest(workflow.canonical(store.rows('claims',dict(study_id='eq.'+study))))==before_claims
   jobs=store.rows('queue_jobs',dict(study_id='eq.'+study));runs=store.rows('runs',dict(study_id='eq.'+study));measurements=store.rows('measurements',dict(study_id='eq.'+study));assessments=store.rows('assessments',dict(study_id='eq.'+study))
   assert len(jobs)==len(runs)==len(requests)==1,(jobs,runs,requests)
   assert runs[0]['status']=='complete' and len(measurements)==4 and {a['label'] for a in assessments}=={'reproduced','discrepant'}
   assert all(m['status']=='recorded' for m in measurements)
   assert {str(m['value']) for m in measurements if m['metric']=='received_bytes'}=={'32'}
   assert f.query('select count(*) from research_shared_campaign_members')=='2'
   turns=store.rows('autonomy_turns',dict(study_id='eq.'+study,limit=100))
   assert len(native)==len(turns) and all(t['status']=='complete' and workflow.digest(t['request_raw'].encode())==t['request_sha256'] for t in turns)
   artifacts=store.rows('artifacts',dict(study_id='eq.'+study,limit=1000))
   for a in artifacts:
    restored=store.artifact_bytes(study,a['id']);assert len(restored)==a['byte_count'] and workflow.digest(restored)==a['sha256']
   assert f.query("select count(*) from research_model_dispatches where status!='complete'")=='0'
   assert f.query('select count(*) from research_autonomy_job_commitments')=='1'
   f.report['checks'].append(dict(name='PDF confirmation through durable native dispatch and shared TCP measurement to frozen assessments',passed=True,evidence=dict(study=study,workflow_status=workflow_row['status'],claims=2,synthetic_model_judgments=len(turns),live_provider_calls=0,native_dispatches=len(native),jobs=1,runs=1,actual_tcp_exchanges=2,measurements=4,labels=sorted(a['label'] for a in assessments),hash_verified_artifacts=len(artifacts),manual_running_campaign_edits=0,original_limits_preserved=True,wall_seconds=time.monotonic()-began)))
   tables=('autonomy_workflows','autonomy_tasks','autonomy_turns','model_dispatches','queue_jobs','queue_events','protocols','configurations','runs','measurements','assessments')
   (f.DIRECTORY/'database-snapshot.json').write_bytes(workflow.canonical({table:store.rows(table,dict(study_id='eq.'+study,limit=1000)) for table in tables}))
   f.report.update(passed=True,native=native,source_pdf_sha256=reserve['sha256'],final_commitments_cents=workflow_row['committed_cents'])
 except Exception as error:f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  halt.set()
  if 'thread' in locals():thread.join(timeout=140)
  if errors:f.report['worker_errors']=errors
  f.report['runtime_source_sha256']={p.name:workflow.digest(p.read_bytes()) for p in (f.ROOT.parent/'jumpserve-back-end/research_workflow').glob('*.py')}
  f.report['ended_at']=workflow.now();(f.DIRECTORY/'autonomy-completion-report.json').write_bytes(workflow.canonical(f.report));print(json.dumps(dict(report=str(f.DIRECTORY/'autonomy-completion-report.json'),passed=f.report.get('passed'),checks=f.report['checks'])))
if __name__=='__main__':main()
