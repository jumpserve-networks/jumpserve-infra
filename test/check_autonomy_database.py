"""Actual isolated SQL/controller/worker checks; synthetic provider and Storage."""
import copy,io,json,os,sys,time,traceback
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_sources as sources,worker,scheduler,store,workflow
import autonomy_fixtures as fixture
import network_execution,network_spec,bounded_network

def main():
 f.report.update(protocol='autonomy-bounded-followups-protocol-v1',amendment='autonomy-bounded-followups-amendment-v7',design='Actual local SQL/controller/arithmetic and bounded TCP loopback measurements; explicit synthetic provider/auth/Storage/source and AWS SDK. No Internet measurements or live model evaluation in this database campaign.')
 try:
  f.bootstrap()
  payload=fixture.publish_fixture()
  def publication():
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(payload,p_report={})))
   bad=copy.deepcopy(payload);bad['p_report']['cases'].pop();f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['live_provider_calls']=14;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['cases_sha256']='0'*64;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report'].pop('trajectory_report',None);f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['trajectory_report']['limits']['max_attempts_per_claim']=2;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['trajectory_report']['status']='incomplete-evaluation';f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['trajectory_report']['terminal_status']='attempt-limit';f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['trajectory_report']['cases'][-1]['output']['assessment_label']='inconclusive';f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['trajectory_report']['cases'][-1]['output']['coverage_complete']=False;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   # No short-window pass is needed: retain its failure and allow four-turn evidence.
   payload['p_report'].pop('completion_report',None)
   f.rpc('publish_agent_prompt',payload)
   rejected=copy.deepcopy(payload);rejected['p_expected_active_version_id']=payload['p_version_id'];t=rejected['p_report']['trajectory_report'];t['cases'].insert(1,dict(number=2,status='provider-rejected',passed=True,raw_answer_reviewed=False,rendered_answer_reviewed=False,no_answer_received=True,failure_reviewed=True,failure_code='ThrottlingException',failure_sha256='a'*64,provider_response_sha256=workflow.digest(b''),provider_attempt_not_replayed=True))
   for i,c in enumerate(t['cases']):c['number']=i+1
   t['attempts_used']=len(t['cases']);f.rpc('publish_agent_prompt',rejected)
   bad=copy.deepcopy(rejected);bad['p_report']['trajectory_report']['cases'][1]['failure_reviewed']=False;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(rejected);bad['p_report']['trajectory_report']['cases'][1]['failure_code']='UnknownTimeout';f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   return dict(malformed_and_missing_cases_rejected=True,synthetic_local_guard_exercise_only=True,four_turn_trajectory_accepted=True,two_attempt_limit_rejected=True,incomplete_evaluation_not_publishable=True)
  f.check('publication rejects incomplete evidence; fixture publication is explicitly synthetic',publication)
  body=dict(request_id=f.uid(),autonomous=True,paper=dict(title='Autonomy full-flow software fixture',paper_url=fixture.URL,domain='Software verification',scope='Synthetic recorded values only; no scientific claims',study_kind='paper'))
  with patch.object(autonomy,'wake',return_value=dict(status='fixture-deferred')):
   created=autonomy.start(f.ACTOR,body);again=autonomy.start(f.ACTOR,body)
  study=created['id'];assert again['id']==study
  def security():
   for role in ('anon','authenticated'):
    for name in ('workflows','tasks','turns','job_commitments','events'):
     assert f.query("select has_table_privilege(current_user,'research_autonomy_"+name+"','SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
    assert f.query("select has_function_privilege(current_user,'research_autonomy_control(text,uuid,uuid,jsonb)','EXECUTE')",role=role)=='f'
   f.rejects(lambda:f.rpc('research_autonomy_control',dict(p_operation='cancel',p_actor=f.OTHER,p_study=study,p_payload={})))
   row=created['autonomy'];assert row['max_spend_cents']==10000 and row['max_attempts']==25 and row['committed_cents']==500
   return dict(private_tables=5,owner_isolation=True,atomic_intake_replay=True,defaults=row)
  f.check('atomic intake defaults owner isolation RLS and browser denial',security)
  def full_flow():
   original_step=autonomy.step;errors=[]
   def traced(task):
    try:return original_step(task)
    except Exception as error:errors.append(traceback.format_exc());raise
   with patch.object(autonomy,'step',side_effect=traced),patch.object(fixture.preparation,'registered',side_effect=fixture.registered),patch.object(model,'invoke',side_effect=fixture.provider):
    for cycle in range(40):
     # Poll scheduling time is shortened only in the isolated fixture DB.
     f.query("update research_autonomy_tasks set next_at=clock_timestamp() where study_id="+f.sql_text(study)+" and status='waiting'")
     result=autonomy.handler({})
     if errors:raise AssertionError(errors[0])
     worker_result=worker.handler({})
     if any(x.get('status')=='unconfirmed' for x in result['outcomes']):raise AssertionError(result)
     state=f.store.rows('autonomy_workflows',{'study_id':'eq.'+study})[0]
     if state['status']!='running':break
    else:raise AssertionError('Controller did not reach terminal task outcomes')
   tasks=f.store.rows('autonomy_tasks',{'study_id':'eq.'+study});turns=f.store.rows('autonomy_turns',{'study_id':'eq.'+study,'limit':1000})
   labels={t['label'] for t in tasks};assert {'reproduced','discrepant','untested'}<=labels,tasks
   assert sum(t['status']=='resolved' for t in tasks)==2
   assert sum(t['status']=='blocked' for t in tasks)==1
   assert state['status']=='completed-with-blockers' and state['committed_cents']<=10000
   assert len(f.store.rows('queue_jobs',{'study_id':'eq.'+study}))==4
   assessments=f.store.rows('assessments',{'study_id':'eq.'+study});assert len(assessments)==2
   assert all(isinstance(e,dict) and set(e)=={'kind','id'} for a in assessments for e in a['evidence'])
   assert all(any(e['kind']=='runs' for e in a['evidence']) for a in assessments)
   for t in turns:
    assert workflow.digest(t['request_raw'].encode())==t['request_sha256'] and json.loads(t['request_raw'])==t['request']
   followups=[json.loads(t['request']['messages'][0]['content'][0]['text']) for t in turns if t['stage']=='planning' and t['number']>1]
   assert any('missing observation' in str(v.get('previous_feedback')) for v in followups)
   r=autonomy.history(study, next(t['id'] for t in tasks if t['status']=='resolved'))
   assert r['coverage']['total']==8 and len(r['turns'])==8
   terminal=turns[0];f.rejects(lambda:f.query("update research_autonomy_turns set request='{}' where id="+f.sql_text(terminal['id'])))
   return dict(cycles=cycle+1,tasks=len(tasks),model_fixture_calls=len(turns),queue_jobs=4,labels=sorted(l for l in labels if l),tailored_followup=True,original_prompts_verified=True,typed_evidence_references=True,real_provider_calls=0,cloud_instances=0)
  f.check('parallel claims execute recorded checks retry personalized gaps and retain external blockers',full_flow)
  # Additional workflows isolate admission/race checks from the completed study.
  def fresh():
   b=dict(body,request_id=f.uid())
   with patch.object(autonomy,'wake',return_value={}):return autonomy.start(f.ACTOR,b)['id']
  def lease():return f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  def pdf_extraction():
   layer=f.ROOT/'.runtime-autonomy-python/python';sys.path.insert(0,str(layer))
   from pypdf import PdfWriter
   from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
   writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
   font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
   page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
   content=DecodedStreamObject();content.set_data(b'BT /F1 12 Tf 40 50 Td (Synthetic latency is 10 ms.) Tj ET');page[NameObject('/Contents')]=writer._add_object(content)
   buffer=io.BytesIO();writer.write(buffer);raw=buffer.getvalue();study_pdf=fresh()
   study_row=autonomy.one('studies',study_pdf,study_pdf)
   with patch.object(sources,'fetch',return_value=(raw,fixture.URL,[dict(url=fixture.URL,status_code=200,media_type='application/pdf')])),patch.dict(os.environ,{'PYTHONPATH':str(layer)}):value=sources.original(study_row,f.ACTOR)
   packet=json.loads(store.artifact_bytes(study_pdf,value['text_artifact_id'],maximum=1000000))
   assert 'Synthetic latency is 10 ms.' in packet['pages'][0]['text']
   source=autonomy.one('sources',study_pdf,value['source_id']);assert source['sha256']==workflow.digest(raw) and source['review_status']=='retrieved-unreviewed'
   assert store.artifact_bytes(study_pdf,value['original_artifact_id'])==raw
   f.rpc('research_autonomy_control',dict(p_operation='cancel',p_actor=f.ACTOR,p_study=study_pdf,p_payload={}))
   return dict(actual_pypdf_version=packet['tool_version'],actual_parser_subprocess=True,synthetic_pdf=True,original_bytes_and_hash_verified=True,complete_review_claimed=False)
  f.check('actual PDF parser preserves original bytes and explicit source review omissions',pdf_extraction)
  def reserve(task,cents):
   request=model.request('Synthetic race prompt',{'fixed':True});data=dict(id=f.uid(),request=request,request_raw=workflow.canonical(request).decode(),request_sha256=workflow.digest(workflow.canonical(request)),reserved_cents=cents,prompt_version_id=payload['p_version_id'],model_id=model.MODEL)
   return autonomy.control(task,'begin',data)
  def budgets():
   study2=fresh();initial=lease();assert initial['study_id']==study2
   with patch.object(fixture.preparation,'registered',side_effect=fixture.registered):autonomy.process(initial)
   t=lease();other=lease();assert t['study_id']==other['study_id']==study2
   assert lease() is None
   before=int(f.query('select committed_cents from research_autonomy_workflows where study_id='+f.sql_text(study2)))
   with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda item:reserve(item,6000),(t,other)))
   assert sum(r.get('denied')=='budget' for r in results)==1,results
   assert int(f.query('select committed_cents from research_autonomy_workflows where study_id='+f.sql_text(study2)))==before+6000
   # Leave the uncertain successful invocation retained, fenced and charged.
   admitted=next(item for item,result in zip((t,other),results) if not result.get('denied'))
   assert reserve(admitted,1)['denied']=='in-flight'
   f.query("update research_autonomy_tasks set lease_until=clock_timestamp()-interval '1 second' where study_id="+f.sql_text(study2)+" and status='running'")
   remaining=lease();assert f.query('select status from research_autonomy_tasks where id='+f.sql_text(t['id']))=='blocked'
   assert f.query('select status from research_autonomy_turns where task_id='+f.sql_text(admitted['id']))=='unknown'
   if remaining:autonomy.advance(remaining,'blocked',reason='Synthetic capacity/lease test finished; no model invoked.')
   return dict(concurrent_overcommit_denied=True,model_commitments_cents=6000,controller_and_initial_commitments_cents=before,expired_provider_never_replayed=True)
  f.check('concurrent model reservations cannot exceed shared paper budget; expired calls retain unknown usage',budgets)
  def attempts():
   study3=fresh();t=lease();assert t['study_id']==study3
   for i in range(25):
    r=reserve(t,1);assert not r.get('denied')
    autonomy.control(t,'finish',dict(id=r['id'],status='invalid-output',raw_response='{}',output=None,usage={},estimated_cents=None,reason='Synthetic invalid answer retained'))
   assert reserve(t,1)['denied']=='attempt-limit'
   f.rejects(lambda:autonomy.control(dict(t,lease_token=f.uid()),'advance',dict(status='blocked',stage='intake',context={},reason='Bad token',label=None)))
   autonomy.advance(t,'attempt-limit',reason='Synthetic limit reached; invalid attempts retained.')
   return dict(attempts=25,next_attempt_denied=True,failed_attempts_preserved=True,stale_fence_denied=True)
  f.check('25 attempts include invalid responses and require current fenced lease',attempts)
  def deadline():
   study4=fresh()
   # Time travel is explicit and restricted to the isolated database, preserving
   # the production immutability guard. Change created/deadline consistently.
   f.query("alter table research_autonomy_workflows disable trigger research_autonomy_workflow_immutable; update research_autonomy_workflows set created_at=clock_timestamp()-interval '8 days',deadline_at=clock_timestamp()-interval '1 day' where study_id="+f.sql_text(study4)+"; alter table research_autonomy_workflows enable trigger research_autonomy_workflow_immutable")
   lease();assert f.query('select status from research_autonomy_workflows where study_id='+f.sql_text(study4))=='deadline'
   return dict(expired_work_not_dispatched=True,clock_fixture_only=True)
  f.check('seven-day elapsed deadline stops queued autonomous work',deadline)
  def global_capacity():
   for _ in range(4):fresh()
   with ThreadPoolExecutor(max_workers=4) as pool:tasks=list(pool.map(lambda _:lease(),range(4)))
   assert all(tasks) and len({t['id'] for t in tasks})==4
   assert lease() is None
   for t in tasks:autonomy.advance(t,'blocked',reason='Explicit synthetic global-capacity fixture; no source or provider action.')
   stopped=fresh();t=lease();assert t['study_id']==stopped
   f.query("update research_autonomy_tasks set lease_until=clock_timestamp()-interval '1 second' where id="+f.sql_text(t['id']))
   assert lease() is None
   assert f.query('select status from research_autonomy_workflows where study_id='+f.sql_text(stopped))=='completed-with-blockers'
   return dict(global_slots=4,per_paper_slots=2,fifth_lease_denied=True,actual_parallel_sql_claims=True,all_expired_workflows_stop=True)
  f.check('parallel SQL claims obey four global and two per-paper slots',global_capacity)
  def context_recovery():
   study=fresh();intake=lease()
   with patch.object(fixture.preparation,'registered',side_effect=fixture.registered):autonomy.process(intake)
   t=lease();assert t['study_id']==study
   first=autonomy.inventory(t)[0];scheduler.enqueue(study,f.ACTOR,first['request']);queued=f.rpc('research_queue_claim',dict(p_worker=f.uid()));assert queued['id']==first['id'];worker.execute_job(queued)
   legacy_reviews=[]
   for role in ('comprehension','critic'):
    f.query('update research_autonomy_tasks set stage='+f.sql_text(role)+' where id='+f.sql_text(t['id']))
    turn=reserve(t,1);output=dict(ready=True,coverage_complete=False)
    autonomy.control(t,'finish',dict(id=turn['id'],status='complete',raw_response=workflow.canonical(output).decode(),output=output,usage={},estimated_cents=None,reason='Explicit synthetic legacy review record; no model call.'))
    legacy_reviews.append(dict(turn_id=turn['id'],role=role,coverage_complete=False))
   t['attempts']=2
   legacy_context=dict(t['context'],selected_check_id=first['id'],completed_job_ids=[first['id']],reviews=legacy_reviews)
   reason='Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.'
   autonomy.advance(t,'blocked',stage='planning',context=legacy_context,reason=reason)
   before=f.store.rows('autonomy_workflows',{'study_id':'eq.'+study})[0]
   payload=dict(p_study=study,p_actor=f.ACTOR,p_task=t['id'],p_version='autonomy-evidence-v2')
   f.rejects(lambda:f.rpc('research_autonomy_resume_context',dict(payload,p_actor=f.OTHER)))
   f.rejects(lambda:f.rpc('research_autonomy_resume_context',dict(payload,p_version='reset-limits')))
   result=f.rpc('research_autonomy_resume_context',payload);assert result['status']=='queued' and result['attempts']==t['attempts']
   assert result['context']['completed_reviews'][first['id']]==legacy_reviews and 'selected_check_id' not in result['context']
   after=f.store.rows('autonomy_workflows',{'study_id':'eq.'+study})[0]
   assert all(after[k]==before[k] for k in ('created_at','deadline_at','committed_cents','initial_prompt','initial_sha256'))
   # Repeating this implementation's recovery is forbidden even if it blocks again.
   f.query("update research_autonomy_tasks set status='blocked',reason="+f.sql_text(reason)+' where id='+f.sql_text(t['id']))
   f.rejects(lambda:f.rpc('research_autonomy_resume_context',payload))
   for role in ('anon','authenticated'):
    assert f.query("select has_function_privilege(current_user,'research_autonomy_resume_context(uuid,uuid,uuid,text)','EXECUTE')",role=role)=='f'
    assert f.query("select has_function_privilege(current_user,'research_autonomy_context_candidates()','EXECUTE')",role=role)=='f'
   f.rpc('research_autonomy_control',dict(p_operation='cancel',p_actor=f.ACTOR,p_study=study,p_payload={}))
   return dict(original_limits_and_costs_preserved=True,one_recovery_per_implementation=True,wrong_owner_and_browser_denied=True)
  f.check('known context recovery preserves authorization and cannot reset or repeat attempts',context_recovery)
  def parallel_jobs():
   study=fresh();intake=lease()
   with patch.object(fixture.preparation,'registered',side_effect=fixture.registered):autonomy.process(intake)
   tasks=[lease(),lease()];assert all(t['study_id']==study for t in tasks)
   def reserve_job(t):return autonomy.control(t,'reserve-job',dict(job_id=f.uid(),definition_sha256='a'*64,reserved_cents=6000,required_seconds=60,quote=dict(kind='synthetic cost race; no cloud request',required_seconds=60)))
   with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve_job,tasks))
   assert sum(bool(r.get('denied')) for r in results)==1
   assert int(f.query('select committed_cents from research_autonomy_workflows where study_id='+f.sql_text(study)))<=10000
   f.rpc('research_autonomy_control',dict(p_operation='cancel',p_actor=f.ACTOR,p_study=study,p_payload={}))
   for t in tasks:autonomy.advance(t,'cancelled',reason='Synthetic job budget race finished; no cloud work dispatched.')
   return dict(parallel_experiment_overcommit_denied=True,real_cloud_calls=0,requested_commitments_cents=12000)
  f.check('parallel experiment commitments share one atomic paper budget',parallel_jobs)
  def bounded_tcp_pipeline():
   import boto3
   from types import SimpleNamespace
   study=f.uid();campaign=f.uid();protocol=f.uid();job_id=f.uid()
   f.rpc('research_create_study',dict(p_actor=f.ACTOR,p_id=study,p_document=workflow.paper_details(dict(title='Bounded TCP integration check',domain='Software verification',scope='Actual local loopback TCP; AWS and Google identity are fixtures',study_kind='idea',paper_url=None))))
   p=workflow.numerical_protocol('a'*64,'round_trip_time_ms','ms',0,[dict(identity='loopback',details=dict(test_config=dict(payload_bytes=32,exchanges=2,application_delay_ms=0)))])
   p.update(questions=['Does the bounded TCP execution retain actual observations?'],hypotheses='Software integration only; no academic claim or population inference.',prior_exposure='Development check declared before TCP exchange; no scientific validation.',data_origin='new-empirical',planned_units=1,statistics='Descriptive exchange values only; no inferential interval.',dependence='Two exchanges share one host, process and TCP connection; independence is not established.',replication_unit='One complete invocation; individual exchanges are repeated observations.',resource_limits=dict(max_input_bytes=10000,max_observations=4,wall_seconds=60),metrics=[dict(name='round_trip_time_ms',units='ms',planned_observations=2,lower_bound=0),dict(name='received_bytes',units='bytes',planned_observations=2,lower_bound=0)],execution=dict(version=network_spec.VERSION,runner='bounded-tcp-v1',replications=1,limits=dict(wall_seconds=60,max_instances=1,max_output_bytes=32000,max_network_bytes=128)))
   p.update(input_versions=[],algorithms=['bounded-tcp-v1: exact payload TCP exchanges with controlled application delay.'],controls=['Validate every returned payload byte; forbid remote destinations.'],sample_size_rationale='Two exchanges exercise transport/persistence; no power or population inference.',coverage_limits='Local host/process only; no Internet or CDN validation.',stopping_rule='Two complete exchanges or the monotonic deadline; retain completed observations on failure.')
   p['execution']['limits']['max_network_bytes']=1024
   p=network_spec.bind_inputs(p);spec=network_spec.specs(p)[0]
   document=dict({field:'Explicit local software fixture; no actual AI review or scientific claim.' for field in f.ideas.FIELDS},protocol=p)
   packet=f.ideas.save(study,f.ACTOR,dict(action='save',request_id=f.uid(),supersedes_id=None,document=document,reason='Freeze local bounded TCP integration fixture.'))
   idea_prompt='e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8';idea_sha=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(idea_prompt))
   declaration=dict(evaluation_kind='actual-model-development',module_id='research-verification',analysis_version='research-ideas-v1',prompt_version_id=idea_prompt,prompt_version='research-ideas-v2',prompt_content_sha256=idea_sha,model_id='synthetic-software-provider',cases_sha256='a'*64,cases=[dict(name=name,status='complete',passed=True,output_sha256='b'*64) for name in ['idea-planning','idea-comprehension','idea-critic','idea-missing','idea-novelty','idea-untrusted','idea-clear-plan','idea-scope']],reviewer=dict(identity='Synthetic local SQL declaration; no actual model evaluation',type='AI',independent=False,passed=True))
   f.rpc('publish_agent_prompt',dict(p_version_id=idea_prompt,p_expected_active_version_id=None,p_expected_content_sha256=idea_sha,p_report=declaration,p_actor='Synthetic local software fixture only',p_module_id='research-verification'))
   reviews={}
   for role in ('comprehension','critic'):
    review=f.rpc('research_begin_idea_run',dict(p_study=study,p_actor=f.ACTOR,p_user='software-fixture@example.invalid',p_id=f.uid(),p_packet=packet['id'],p_task=role,p_session=None,p_prompt='e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8',p_model='explicit-synthetic-provider',p_request=dict(task=role,fixture=True),p_provenance=dict(packet_sha256=packet['sha256'],context_policy='fresh-packet-only',history_messages=0)))
    answer=dict(summary='Synthetic development readiness only',questions=[],findings=[],verdict='ready')
    f.rpc('research_finish_idea_run',dict(p_study=study,p_actor=f.ACTOR,p_id=review['id'],p_status='complete',p_reason=None,p_raw=workflow.canonical(answer).decode(),p_output=answer,p_usage=dict(tokens=None,measured_charges_usd=None),p_provenance={},p_messages=None));reviews[role]=review['id']
   f.ideas.accept(study,f.ACTOR,dict(action='accept',request_id=f.uid(),packet_id=packet['id'],comprehension_run_id=reviews['comprehension'],critic_run_id=reviews['critic'],reason='Explicit synthetic software fixture reviews.'))
   prepared=f.ideas.prepare_campaign(dict(id=study,title='Bounded TCP local check'),f.ACTOR,dict(action='prepare-campaign',request_id=f.uid(),packet_id=packet['id'],title='Local TCP development execution',stage='pilot',claim_type='operational',experiment_type='new-measurement',planned_units=1))
   body=prepared['queue_requests'][0];job_id=body['request_id']
   policy=json.loads(autonomy.autonomy_costs.POLICY_PATH.read_bytes())['bounded_tcp'];env=dict(NETWORK_BOUNDED_FUNCTION='arn:aws:lambda:us-east-1:395567831870:function:LocalDevelopmentFixture:1',NETWORK_BOUNDED_POLICY_SHA256=workflow.digest(workflow.canonical(policy)))
   calls=[]
   def invoke(**kwargs):
    calls.append(kwargs);event=json.loads(kwargs['Payload']);actual=bounded_network.handler(event)
    return dict(Payload=io.BytesIO(workflow.canonical(actual)),StatusCode=200)
   client=SimpleNamespace(get_function_configuration=lambda **kw:dict(MemorySize=128,Timeout=5,Runtime='python3.12',Handler='index.handler',EphemeralStorage={'Size':512}),invoke=invoke)
   with patch.dict(os.environ,env),patch.object(boto3,'client',return_value=client):
    scheduler.enqueue(study,f.ACTOR,body);worker.handler({})
   run=f.store.rows('runs',{'study_id':'eq.'+study,'id':'eq.'+job_id})[0];assert run['status']=='complete'
   measurements=f.store.rows('measurements',{'study_id':'eq.'+study,'run_id':'eq.'+job_id});assert len(measurements)==4
   assert len(calls)==1 and calls[0]['InvocationType']=='RequestResponse'
   assert all(str(r['value'])=='32' for r in measurements if r['metric']=='received_bytes')
   artifacts=f.store.rows('artifacts',{'study_id':'eq.'+study});original=next(a for a in artifacts if a['provenance'].get('kind')=='bounded-tcp-original-lambda-response')
   raw=f.store.artifact_bytes(study,original['id']);assert workflow.digest(raw)==original['sha256']
   assert json.loads(raw)['usage']['remote_network_bytes']==0
   return dict(actual_local_tcp=True,stored_measurements=4,original_response_bytes=len(raw),original_sha256=original['sha256'],cloud_calls=0,cloud_transport='Explicit local SDK fixture; no deployed Lambda claim',socket_cleanup_verified=True)
  f.check('actual bounded TCP worker persists observations and hash-verified original response',bounded_tcp_pipeline)
  snapshot={}
  for table in ('research_studies','research_sources','research_claims','research_protocols','research_configurations','research_campaigns','research_claim_checks','research_runs','research_published_values','research_measurements','research_summaries','research_assessments','research_artifacts','research_queue_jobs','research_queue_events','research_autonomy_workflows','research_autonomy_tasks','research_autonomy_turns','research_autonomy_job_commitments','research_autonomy_events','agent_prompt_publications'):
   snapshot[table]=json.loads(f.query("select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) from public."+table+' r'))
  (f.DIRECTORY/'database-fixture-snapshot.json').write_text(json.dumps(dict(design='Parsed JSON export of isolated synthetic fixture database; not original network bytes or scientific observations.',database=f.DATABASE,records=snapshot),indent=2)+'\n')
  f.report['passed']=True
 except Exception as error:
  f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  f.report['ended_at']=f.dt.datetime.now(f.dt.timezone.utc).isoformat()
  path=f.DIRECTORY/'autonomy-validation-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'))))

if __name__=='__main__':main()
