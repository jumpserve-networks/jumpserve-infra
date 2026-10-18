"""Actual isolated SQL/controller/worker checks; synthetic provider and Storage."""
import copy,io,json,os,sys,time,traceback
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_sources as sources,worker,scheduler,store,workflow
import autonomy_fixtures as fixture

def main():
 f.report.update(protocol='autonomous-assessment-protocol-v1',design='Actual local SQL/controller/arithmetic worker; explicit synthetic provider/auth/Storage/source. No actual networking or model evaluation.')
 try:
  f.bootstrap()
  payload=fixture.publish_fixture()
  def publication():
   f.rejects(lambda:f.rpc('publish_agent_prompt',dict(payload,p_report={})))
   bad=copy.deepcopy(payload);bad['p_report']['cases'].pop();f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['live_provider_calls']=14;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   bad=copy.deepcopy(payload);bad['p_report']['cases_sha256']='0'*64;f.rejects(lambda:f.rpc('publish_agent_prompt',bad))
   f.rpc('publish_agent_prompt',payload)
   return dict(malformed_and_missing_cases_rejected=True,synthetic_local_guard_exercise_only=True)
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
