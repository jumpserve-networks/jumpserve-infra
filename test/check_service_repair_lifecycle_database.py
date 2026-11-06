"""Isolated Postgres regressions for consumed activations and completed intake incidents."""
import copy,json
from concurrent.futures import ThreadPoolExecutor
import check_platform_service_work_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202611060001_service_repair_lifecycle.sql'


def main():
 previous.main();q=f.sql_text;j=f.sql_json
 f.report.update(passed=False,protocol='service-repair-lifecycle-v1')
 def js(sql,role=None):return json.loads(f.query(sql,role=role) or 'null')
 def work(c,op,body=None):
  return js('select public.platform_worker('+','.join([q(op),q(c['worker']),q(c['parent']) if c.get('parent') else 'null',q(c['token']) if c.get('token') else 'null',j(body or {})])+')','service_role')
 def artifact(study,ident,h,kind,provenance=None):
  f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(ident),q(study),q(h),'20',q(study+'/'+h),q('application/json'),j(dict(provenance or {},kind=kind)),'clock_timestamp()'])+')')
 def platform_artifact(task,name='synthetic.json'):
  ident=f.uid();h=workflow.digest(ident.encode())
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(ident),q(task),q(name),q(h),'20',q(task+'/'+h),q('application/json'),"'{}'"])+')')
  return ident
 def platform_task(c,ident,status='implementing',deadline="clock_timestamp()+interval '1 hour'"):
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,status,max_reserved_cents,deadline_at,worker_id,lease_token,lease_until) select '+','.join([
   q(ident),"(select user_id from platform_operators where role='owner' limit 1)",q('Synthetic lifecycle repair'),q('Retain exact original incident.'),"array['jumpserve-networks/jumpserve-infra']",'authorization_version',q('platform_repair'),q(status),'-1',deadline,q(c['worker']),q(c['token']),"clock_timestamp()+interval '5 minutes'"])+ ' from platform_settings where id')
 def case(continuation=False,expired=False):
  c={name:f.uid() for name in ('study','root','parent','token','worker','blocker','original','text','failure','source')}
  f.query("update platform_settings set paused=false,automatic_releases=true where id;update autonomy_budget_categories set max_model_calls=-1,max_spend_cents=-1,change_reason='Synthetic lifecycle fixture' where category in ('platform_repair','research_assessment')")
  times="clock_timestamp()-interval '2 days',clock_timestamp()-interval '1 day'" if expired else "clock_timestamp(),clock_timestamp()+interval '7 days'"
  sql='insert into research_studies(id,title,paper_url,domain,scope) values('+q(c['study'])+",'Synthetic lifecycle paper','https://example.org/lifecycle.pdf','Networking','Synthetic software regression');"
  sql+='insert into research_study_owners(study_id,owner_id) values('+q(c['study'])+','+q(f.ACTOR)+');'
  sql+='insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256,created_at,deadline_at) values('+q(c['study'])+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'),"+times+');'
  sql+='insert into research_paper_reviews(study_id,status) values('+q(c['study'])+",'failed');insert into research_autonomy_tasks(id,study_id,stage,status,reason,context) values("+q(c['root'])+','+q(c['study'])+",'intake','blocked','Synthetic parser failure.',"+j(dict(intake_pool_version='warm-intake-v1'))+')'
  f.query(sql)
  platform_task(c,c['parent'])
  original_parent=c['parent']
  if continuation:
   original_parent=f.uid();platform_task(c,original_parent,'deadline',"clock_timestamp()-interval '1 minute'")
   f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(original_parent))
  c['original_parent']=original_parent
  f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join(map(q,[c['blocker'],c['study'],c['root'],'task',c['root'],'intake','blocked','Synthetic parser failure.',workflow.digest(b'Synthetic parser failure.'),workflow.digest(c['root'].encode())]))+');insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(c['blocker'])+','+q(original_parent)+')')
  if continuation:
   f.query('insert into platform_assessment_repair_attempts(blocker_id,root_task_id,previous_task_id,platform_task_id,generation,evidence_revision,carried_cents,carried_calls,proof) values('+','.join([q(c['blocker']),q(original_parent),q(original_parent),q(c['parent']),'1',q('a'*64),'0','0',"'{}'"])+')')
  artifact(c['study'],c['original'],'b'*64,'paper-original-upload')
  artifact(c['study'],c['failure'],'c'*64,'failed-text-extraction',dict(original_artifact_id=c['original']))
  artifact(c['study'],c['text'],'d'*64,'derived-pdf-text',dict(original_artifact_id=c['original'],original_sha256='b'*64))
  source=dict(id=c['source'],citation='Synthetic source',source_url=None,retrieved_url=None,kind='main paper',role='Synthetic parser fixture',retrieved_version='Synthetic',sha256='b'*64,byte_count=20,access_status='retrieved',review_status='retrieved-unreviewed',review_definition='Synthetic fixture',examined='Fixture bytes',unexamined='Scientific conclusions',retrieval_attempts=[],reviewer={},findings='None',limitations='Synthetic software regression')
  f.query('select public.research_append('+','.join([q(c['study']),q(f.ACTOR),q('sources'),j(source)])+')')
  return c
 def request(c,profile):
  c=dict(c,profile=profile,request=f.uid());spec=dict(version='platform-service-work-v1',profile=profile,objective='Synthetic lifecycle service.',acceptance=['Retain original evidence.'])
  a=platform_artifact(c['parent'],'infrastructure-service-request.json')
  result=js('select public.platform_service_work('+','.join([q('request'),q(c['worker']),q(c['parent']),q(c['token']),j(dict(id=c['request'],spec=spec,artifact_id=a))])+')','service_role')
  c['child']=result['implementation_task_id'];return c
 def activate(c,profile='intake-parser-recovery-v1',defer=False):
  c=request(c,profile);child=dict(c,parent=c['child'])
  f.query("update platform_tasks set status='deploying',worker_id="+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(c['child']))
  c.update(operation=f.uid(),revision='a'*40);body=dict(repository='jumpserve-networks/jumpserve-infra',component='infrastructure',revision=c['revision'])
  operation=work(child,'begin-operation',dict(id=c['operation'],kind='deploy',request=body,request_sha256=workflow.digest(workflow.canonical(body))))
  proof=dict(passed=True,profile=profile,request_id=c['request'],revision=c['revision'],scientific_completion=False,task_bound_evidence_verified=True,schema_sha256='b'*64)
  if profile=='intake-parser-recovery-v1':
   proof.update(intake_source_binding='e'*64,parser_version='6.19.0',failure_verified=True,provider_calls=0,intake_environment_verified=True,environment_command_id=f.uid(),environment_checked_at=js('select to_jsonb(clock_timestamp())'),failure_artifact_id=c['failure'],failure_sha256='c'*64,original_reason_sha256=workflow.digest(b'Synthetic parser failure.'),source_id=c['source'],original_artifact_id=c['original'],text_artifact_id=c['text'],text_sha256='d'*64)
   f.query("update research_intake_runtime set enabled=true,status='ready',seen_at=clock_timestamp(),configuration="+j(dict(gateway_verified=True,source_binding='e'*64))+' where id')
  manifest=dict(version='platform-service-manifest-v1',request_id=c['request'],profile=profile)
  assert js('select public.platform_service_release('+','.join([q(c['operation']),q(c['revision']),j(manifest),j(proof)])+')','service_role')['verified']
  if not defer:f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['parent']))
  work(child,'finish-operation',dict(id=c['operation'],request_sha256=operation['request_sha256'],status='confirmed',result={'synthetic_cloud_receipt':True}))
  work(child,'release',dict(id=f.uid(),component='infrastructure',repository='jumpserve-networks/jumpserve-infra',revision=c['revision'],status='verified',external_id=c['operation'],verification=dict(passed=True,revision=c['revision']),details=dict(synthetic_cloud_receipt=True)))
  work(child,'checkpoint',dict(status='completed',reason='Synthetic service receipt verified.',checkpoint=dict(service_work_request_id=c['request'])))
  return c
 def finish_intake(c,bad_hash=False):
  prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
  tasks=[]
  for index in range(2):
   ident=f.uid();tasks.append(ident)
   f.query('insert into research_autonomy_tasks(id,study_id,stage,status,context,intake_parent_id,intake_chunk_index) values('+','.join([q(ident),q(c['study']),q('intake'),q('finished'),j(dict(source_id=c['source'],text_artifact_id=c['text'],intake_pool_version='warm-intake-v1',intake_chunk_sha256=workflow.digest(str(index).encode()))),q(c['root']),str(index)])+')')
  turns=[]
  for task in tasks+[c['root']]:
   turn,response_artifact=f.uid(),f.uid();turns.append(turn);response=workflow.canonical(dict(synthetic_task=task)).decode();h=workflow.digest(response.encode())
   artifact(c['study'],response_artifact,h,'synthetic-model-response')
   f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,raw_response,response_sha256,output,ended_at) values('+','.join([q(turn),q(c['study']),q(task),'1',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'",q('{}'),q(workflow.digest(b'{}')),q('complete'),'100',q(response),q(h),"'{}'",'clock_timestamp()'])+')')
   f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status,response_artifact_id,response_sha256,ended_at,dispatch_lane) values('+','.join([q(turn),q(c['study']),q(task),q('openclaw-production-v1'),q('{}'),q(workflow.digest(b'{}')),q('complete'),q(response_artifact),q('f'*64 if bad_hash and task==tasks[0] else h),'clock_timestamp()',q('intake')])+')')
   if task!=c['root']:f.query("update research_autonomy_tasks set context=context||"+j(dict(last_turn_id=turn))+' where id='+q(task))
  f.query("update research_autonomy_tasks set status='finished',context=context||"+j(dict(chunk_index=2))+",lease_token=null,lease_until=null where id="+q(c['root']))
  selection=dict(version='paper-review-selection-v1',status='ready',candidate_count=1,cursor=1,last_turn_id=turns[-1])
  f.query("update research_paper_reviews set status='ready',seeds="+j([dict(id=f.uid(),description='Synthetic retained statement',source_id=c['source'])])+',metadata='+j(dict(selection=selection))+',revision=revision+1,updated_at=clock_timestamp() where study_id='+q(c['study']))
  c.update(chunks=tasks,turns=turns);return c
 def originals(c):
  return f.query("select jsonb_build_object('workflow',(select to_jsonb(w) from research_autonomy_workflows w where study_id="+q(c['study'])+"),'review',(select to_jsonb(v) from research_paper_reviews v where study_id="+q(c['study'])+"),'tasks',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_tasks t where study_id="+q(c['study'])+"),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t where study_id="+q(c['study'])+"),'dispatches',(select jsonb_agg(to_jsonb(t) order by id) from research_model_dispatches t where study_id="+q(c['study'])+"),'artifacts',(select jsonb_agg(to_jsonb(t) order by id) from research_artifacts t where study_id="+q(c['study'])+"),'sources',(select jsonb_agg(to_jsonb(t) order by id) from research_sources t where study_id="+q(c['study'])+"),'budgets',(select jsonb_agg(to_jsonb(t) order by category) from autonomy_budget_categories t))")
 def maintenance(c):
  policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
  return work(dict(c,parent=None,token=None),'maintenance',dict(policy_sha256=policy))
 def resolution(c):return js('select public.platform_assessment_incident_resolution('+q(c['blocker'])+')')

 old=activate(case(),'assessment-evidence-v1')
 f.query("update platform_tasks set status='blocked',checkpoint=(checkpoint-'service_work_activation')||"+j(dict(capability_wait={'id':f.uid()},not_before='2099-01-01T00:00:00Z'))+' where id='+q(old['parent']))
 old_before=f.query('select to_jsonb(t) from platform_tasks t where id='+q(old['parent']))
 research_before=originals(old);raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 def backfill():
  assert f.query('select count(*) from platform_service_work_resumptions where request_id='+q(old['request']))=='1'
  f.query('select public.platform_service_work_resume()');assert f.query('select to_jsonb(t) from platform_tasks t where id='+q(old['parent']))==old_before
  assert originals(old)==research_before
 f.check('historical consumption is backfilled from retained events without waking a new dependency or changing research records',backfill)

 def once():
  c=activate(case(),'assessment-evidence-v1',defer=True)
  f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['parent']))
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:f.query('select public.platform_service_work_resume()'),range(2)))
  assert f.query('select count(*) from platform_service_work_resumptions where request_id='+q(c['request']))=='1'
  f.query("update platform_tasks set status='blocked',checkpoint=checkpoint||"+j(dict(capability_wait={'id':f.uid()},not_before='2099-01-01T00:00:00Z'))+' where id='+q(c['parent']))
  before=f.query('select to_jsonb(t) from platform_tasks t where id='+q(c['parent']))
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:f.query('select public.platform_service_work_resume()'),range(2)))
  assert f.query('select to_jsonb(t) from platform_tasks t where id='+q(c['parent']))==before
  assert f.query("select count(*) from platform_events where task_id="+q(c['parent'])+" and kind='service-parent-resumed'")=='1'
  f.rejects(lambda:f.query('delete from platform_service_work_resumptions where request_id='+q(c['request'])))
 f.check('concurrent maintenance cannot consume the same activation again or erase a later wait and backoff',once)

 def completed():
  c=finish_intake(activate(case(continuation=True)));before=originals(c)
  prior=f.query('select to_jsonb(t) from platform_tasks t where id='+q(c['original_parent']))
  proof=resolution(c);assert proof and proof['completed_chunks']==2 and len(proof['continuation_witnesses'])==3
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:maintenance(c),range(2)))
  assert f.query('select status from platform_tasks where id='+q(c['parent']))=='completed'
  assert f.query('select to_jsonb(t) from platform_tasks t where id='+q(c['original_parent']))==prior
  assert f.query('select count(*) from platform_assessment_incident_closures where blocker_id='+q(c['blocker']))=='1'
  assert f.query("select count(*) from platform_events where task_id="+q(c['parent'])+" and kind='assessment-incident-closed'")=='1'
  assert originals(c)==before and proof['scientific_completion'] is False
 f.check('a hash-bound finished intake closes its continuation once without changing scope, budgets, source evidence or expired original attempts',completed)

 def refusals():
  for mode in ('chunk','context','witness','review','unknown','deadline','cancelled'):
   c=case(expired=True) if mode=='deadline' else finish_intake(activate(case()),bad_hash=mode=='witness')
   if mode=='chunk':f.query("update research_autonomy_tasks set status='blocked' where id="+q(c['chunks'][0]))
   elif mode=='context':f.query('update research_autonomy_tasks set context=context||'+j(dict(text_artifact_id=f.uid()))+' where id='+q(c['root']))
   elif mode=='review':f.query("update research_paper_reviews set status='preparing',revision=revision+1 where study_id="+q(c['study']))
   elif mode=='deadline':f.rejects(lambda:request(c,'intake-parser-recovery-v1'))
   elif mode=='cancelled':f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(c['study']))
   elif mode=='unknown':
    prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
    f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents) values('+','.join([q(f.uid()),q(c['study']),q(c['root']),'2',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'",q('{}'),q(workflow.digest(b'{}')),q('unknown'),'100'])+')')
   before=originals(c);assert resolution(c) is None;maintenance(c)
   assert f.query('select status from platform_tasks where id='+q(c['parent']))!='completed';assert originals(c)==before
 f.check('incomplete chunks, wrong text bindings, missing hash witnesses, unfinished review, uncertain calls and expired assessments cannot close an incident',refusals)

 def leased():
  c=finish_intake(activate(case(continuation=True)))
  f.query("update platform_tasks set status='implementing',worker_id="+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(c['parent']))
  flags=work(c,'lease');assert flags['incident_closure']['platform_task_id']==c['parent']
  assert work(c,'begin-run')['denied']=='incident-closed'
  work(c,'checkpoint',dict(status='completed',reason='Synthetic verified completion.',checkpoint=dict(incident_closure=flags['incident_closure'])))
  assert f.query('select status from platform_tasks where id='+q(c['parent']))=='completed'
 f.check('a leased continuation receives the proven closure at its normal admission boundary without another model reservation',leased)

 def dependencies():
  c=activate(case());f.query('update platform_tasks set worker_id='+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(c['parent']))
  pending=request(c,'assessment-evidence-v1');child=dict(c,parent=pending['child'])
  f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['parent']))
  request_artifact=platform_artifact(child['parent']);run=f.uid()
  f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([q(run),q(child['parent']),'1',q('f'*64),q(request_artifact),q('unknown'),'100'])+')')
  f.query("update platform_tasks set status='reconciling' where id="+q(child['parent']))
  retained=f.query('select to_jsonb(r) from platform_runs r where id='+q(run));c=finish_intake(c)
  unrelated=case();other=f.query('select to_jsonb(t) from platform_tasks t where id='+q(unrelated['parent']))
  before=originals(c)
  maintenance(c)
  assert f.query('select cancel_requested from platform_tasks where id='+q(child['parent']))=='t'
  assert f.query('select status from platform_tasks where id='+q(child['parent']))=='reconciling'
  assert f.query('select to_jsonb(r) from platform_runs r where id='+q(run))==retained
  assert originals(c)==before and f.query('select to_jsonb(t) from platform_tasks t where id='+q(unrelated['parent']))==other
  assert f.query('select status from platform_tasks where id='+q(c['parent']))=='completed'
 f.check('obsolete service dependencies stop new work but retain uncertain original outcomes and leave unrelated repairs untouched',dependencies)

 def second_activation():
  c=activate(case());first=c['request']
  f.query('update platform_tasks set worker_id='+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(c['parent']))
  second=activate(c,'assessment-evidence-v1')
  assert first!=second['request']
  assert f.query('select count(*) from platform_service_work_resumptions where parent_task_id='+q(c['parent']))=='2'
  assert f.query("select count(*) from platform_events where task_id="+q(c['parent'])+" and kind='service-parent-resumed'")=='2'
 f.check('a distinct newly verified service may resume the parent once after an earlier activation was consumed',second_activation)

 def immutable_changes():
  c=case();a=platform_artifact(c['parent']);b=platform_artifact(c['parent']);ident=f.uid()
  original=dict(id=ident,repository='jumpserve-networks/jumpserve-infra',base_sha='a'*40,tree_sha256='a'*64,summary='Synthetic immutable service manifest.',patch_artifact_id=a,checks_artifact_id=b,status='tested')
  work(c,'change',original);work(c,'change',dict(original,status='superseded'))
  before=f.query('select to_jsonb(c) from platform_changes c where id='+q(ident))
  rebased=dict(original,base_sha='b'*40,tree_sha256='b'*64,patch_artifact_id=platform_artifact(c['parent']),checks_artifact_id=platform_artifact(c['parent']))
  try:work(c,'change',rebased)
  except RuntimeError as error:assert 'Tested change identity is immutable' in str(error)
  else:raise AssertionError('A rebased candidate overwrote its original identity')
  work(c,'change',dict(rebased,id=f.uid()))
  assert f.query('select count(*) from platform_changes where task_id='+q(c['parent']))=='2'
  assert f.query('select to_jsonb(c) from platform_changes c where id='+q(ident))==before
 f.check('the actual RPC reproduces the 400 identity rejection and accepts a distinct rebased candidate without changing its superseded original',immutable_changes)

 def candidate_retirement():
  c=activate(case());f.query('update platform_tasks set worker_id='+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(c['parent']))
  change=dict(id=f.uid(),repository='jumpserve-networks/jumpserve-infra',base_sha='a'*40,tree_sha256='a'*64,summary='Synthetic retained candidate.',patch_artifact_id=platform_artifact(c['parent']),checks_artifact_id=platform_artifact(c['parent']),status='tested')
  work(c,'change',change);before=f.query('select to_jsonb(c) from platform_changes c where id='+q(change['id']))
  c=finish_intake(c);flags=work(c,'lease')
  assert flags['cancel_requested'] is True and 'incident_closure' not in flags,flags
  assert work(c,'begin-run')['denied']=='paused-cancelled-or-deadline'
  assert f.query('select count(*) from platform_runs where task_id='+q(c['parent']))=='0'
  work(c,'checkpoint',dict(status='cancelled',reason='Retired after exact intake completion.',checkpoint={}))
  assert f.query('select status from platform_tasks where id='+q(c['parent']))=='cancelled'
  assert f.query('select to_jsonb(c) from platform_changes c where id='+q(change['id']))==before
 f.check('resolved incidents retire unpublished root candidates at a safe boundary without certifying or overwriting their source',candidate_retirement)

 def confirmed_review():
  c=finish_intake(activate(case()));f.query("update research_paper_reviews set status='confirmed',confirmation='{}',confirmed_at=clock_timestamp(),revision=revision+1 where study_id="+q(c['study']))
  before=originals(c);maintenance(c);assert f.query('select status from platform_tasks where id='+q(c['parent']))=='completed'
  assert originals(c)==before
 f.check('existing owner scope confirmation remains unchanged when the earlier intake incident closes',confirmed_review)

 def legacy_resolution():
  c=case();pending=request(c,'assessment-evidence-v1');repair,turn,response_artifact=f.uid(),f.uid(),f.uid()
  incident=workflow.canonical(dict(version='autonomous-repair-v1',stage='intake',reason='Synthetic parser failure.')).decode();evidence=dict(validated=True,scope='Synthetic prior controller contract')
  f.query('insert into research_autonomy_repairs(id,study_id,task_id,version,category,original_stage,incident_raw,incident_sha256,original_context,state,revision,evidence,reason,updated_at) values('+','.join([q(repair),q(c['study']),q(c['root']),q('autonomous-repair-v1'),q('runtime'),q('intake'),q(incident),q(workflow.digest(incident.encode())),j(dict(intake_pool_version='warm-intake-v1')),q('resolved'),'3',j(evidence),q('Synthetic original repair validation'),"clock_timestamp()-interval '1 minute'"])+')')
  f.query('insert into research_autonomy_repair_events(repair_id,study_id,task_id,revision,state,details) values('+','.join([q(repair),q(c['study']),q(c['root']),'3',q('resolved'),j(dict(evidence=evidence))])+')')
  f.query("update research_autonomy_tasks set status='queued',context=context||"+j(dict(repair_progress=dict(id=repair,state='resolved',revision=3)))+' where id='+q(c['root']))
  response=workflow.canonical(dict(synthetic_legacy_continuation=True)).decode();h=workflow.digest(response.encode());artifact(c['study'],response_artifact,h,'synthetic-model-response')
  prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
  f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,raw_response,response_sha256,output,ended_at) values('+','.join([q(turn),q(c['study']),q(c['root']),'1',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'",q('{}'),q(workflow.digest(b'{}')),q('complete'),'100',q(response),q(h),"'{}'",'clock_timestamp()'])+')')
  f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status,response_artifact_id,response_sha256,ended_at) values('+','.join([q(turn),q(c['study']),q(c['root']),q('openclaw-production-v1'),q('{}'),q(workflow.digest(b'{}')),q('complete'),q(response_artifact),q(h),'clock_timestamp()'])+')')
  f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['parent']));before=originals(c)
  proof=resolution(c);assert proof['repair_id']==repair and 'resolution_kind' not in proof
  maintenance(c)
  assert f.query('select status from platform_tasks where id='+q(c['parent']))=='completed'
  assert f.query('select status from platform_tasks where id='+q(pending['child']))=='completed'
  assert originals(c)==before
 f.check('the previous validated-controller repair contract and its descendant closure remain intact after the lifecycle migration',legacy_resolution)

 def access():
  for role in ('anon','authenticated'):
   f.rejects(lambda:f.query('select * from platform_service_work_resumptions',role=role))
  for role in ('anon','authenticated','service_role'):
   for name in ('platform_intake_incident_resolution','platform_retire_intake_repair_dependencies'):
    signature=name+'('+('uuid' if name.endswith('resolution') else '')+')'
    assert f.query('select has_function_privilege('+q(role)+','+q('public.'+signature)+",'execute')")=='f'
  c=finish_intake(activate(case()));f.query('update platform_settings set paused=true where id');maintenance(c)
  assert f.query('select count(*) from platform_assessment_incident_closures where blocker_id='+q(c['blocker']))=='0'
  f.query('update platform_settings set paused=false where id');f.rejects(lambda:work(dict(c,token=f.uid()),'lease'))
 f.check('private resumption records and closure helpers retain browser/write denial, owner pause and lease authentication',access)
 f.report.update(passed=True,protocol='service-repair-lifecycle-v1');path=f.DIRECTORY/'service-repair-lifecycle-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))


if __name__=='__main__':
 try:main()
 except Exception as error:
  f.report.update(passed=False,error_type=type(error).__name__,error=str(error))
  (f.DIRECTORY/'service-repair-lifecycle-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n')
  raise
