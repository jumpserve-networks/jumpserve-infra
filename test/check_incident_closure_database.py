"""Isolated SQL closure and admission controls; no production/provider calls."""
import copy,json,uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_controller_terminal_database as previous
import check_research_ideas_database as f
import autonomy,workflow

def main():
 previous.main();q=f.sql_text;js=lambda sql,role=None:json.loads(f.query(sql,role=role) or 'null')
 def expect(value):
  if not value:raise AssertionError('Incident closure invariant failed')
 def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
 migration='202611010011_platform_incident_closure.sql';raw=(f.ROOT/'database'/migration).read_bytes()
 def originals():return f.query("select jsonb_build_object('research',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_tasks t),'repairs',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_repairs t),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t),'calls',(select jsonb_agg(to_jsonb(t) order by id) from research_builder_calls t),'budgets',(select jsonb_agg(to_jsonb(t) order by category) from autonomy_budget_categories t),'workflows',(select jsonb_agg(to_jsonb(t) order by study_id) from research_autonomy_workflows t))")
 before=originals();f.query(raw.decode());f.report['migration_sha256'][migration]=workflow.digest(raw)
 check('closure migration preserves all original assessment evidence usage authorizations and limits',lambda:expect(originals()==before))
 seed=js('select to_jsonb(c) from research_claims c limit 1');prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
 worker=f.query('select worker_id from platform_settings where id') or f.uid();policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
 payload=dict(policy_sha256=policy)
 def rpc(op='maintenance',task=None,token=None,role='service_role',body=None):
  return js('select public.platform_worker('+','.join([q(op),q(worker),q(task)+'::uuid' if task else 'null',q(token)+'::uuid' if token else 'null',f.sql_json(payload if body is None else body)])+')',role)
 def case(witness=True,linked=True,validated=True):
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic closed operational incident',paper_url='https://example.org/closure.pdf',domain='Software',scope=__doc__)))['id']
  task,source,claim,repair,blocker,platform,turn=[f.uid() for _ in range(7)];ctx=dict(frozen='original criterion',repair_progress=dict(id=repair,state='resolved',revision=3))
  f.query('insert into research_sources select (jsonb_populate_record(null::research_sources,to_jsonb(s)||'+f.sql_json(dict(id=source,study_id=study))+')).* from research_sources s where id='+q(seed['source_id']))
  f.query('insert into research_claims(id,study_id,source_id,location,description,claim_type,scope,metrics,priority) select '+','.join([q(claim),q(study),q(source)])+',location,description,claim_type,scope,metrics,priority from research_claims where id='+q(seed['id']))
  f.query('insert into research_autonomy_tasks(id,study_id,claim_id,stage,status,label,context,attempts) values('+','.join([q(task),q(study),q(claim),q('planning'),q('queued'),q('inconclusive'),f.sql_json(ctx),'3'])+')')
  incident=workflow.canonical(dict(version='autonomous-repair-v1',stage='planning',reason='Original fixed failure')).decode();evidence=dict(validated=validated,scope='Synthetic server validation')
  f.query("insert into research_autonomy_repairs(id,study_id,task_id,version,category,original_stage,incident_raw,incident_sha256,original_context,state,revision,evidence,reason,updated_at) values("+','.join([q(repair),q(study),q(task),q('autonomous-repair-v1'),q('runtime'),q('planning'),q(incident),q(workflow.digest(incident.encode())),f.sql_json(dict(frozen='original criterion')),q('resolved'),'3',f.sql_json(evidence),q('Validated operational continuation'),"clock_timestamp()-interval '1 minute'"])+')')
  f.query('insert into research_autonomy_repair_events(repair_id,study_id,task_id,revision,state,details) values('+','.join([q(repair),q(study),q(task),'3',q('resolved'),f.sql_json(dict(evidence=evidence))])+')')
  f.query("insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint,created_at) values("+','.join([q(blocker),q(study),q(task),q('repair'),q(repair),q('planning'),q('waiting'),q('Original fixed failure'),q('a'*64),q(workflow.digest(blocker.encode())),"clock_timestamp()-interval '2 minutes'"])+')')
  if linked:
   f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,deadline_at) select '+q(platform)+",(select user_id from platform_operators where role='owner' limit 1),'Synthetic closure','Original operational incident.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'investigating',-1,clock_timestamp()+interval '1 hour' from platform_settings where id")
   f.query('insert into platform_assessment_repair_links values('+q(blocker)+','+q(platform)+',clock_timestamp())')
  if witness:
   response=workflow.canonical(dict(fixture='completed controller continuation')).decode();h=workflow.digest(response.encode());artifact=f.uid()
   f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(artifact),q(study),q(h),str(len(response)),q(study+'/'+h),q('application/json'),"'{}'",'clock_timestamp()'])+')')
   f.query("insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,raw_response,response_sha256,output,created_at,ended_at) values("+','.join([q(turn),q(study),q(task),'1',q('planning'),q(prompt),q('gpt-6.1-sol'),"'{}'",q('{}'),q(workflow.digest(b'{}')),q('complete'),'100',q(response),q(h),"'{}'","clock_timestamp()-interval '20 seconds'","clock_timestamp()-interval '1 second'"])+')')
   f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status,response_artifact_id,response_sha256,ended_at) values('+','.join([q(turn),q(study),q(task),q('openclaw-production-v1'),q('{}'),q(workflow.digest(b'{}')),q('complete'),q(artifact),q(h),'clock_timestamp()'])+')')
  return dict(study=study,task=task,repair=repair,blocker=blocker,platform=platform,turn=turn)
 def resolution(c):return js('select public.platform_assessment_incident_resolution('+q(c['blocker'])+')')
 f.query('update platform_settings set paused=false where id')
 target=case()
 def concurrent():
  before=originals();proof=resolution(target);expect(proof and not proof['qualified_platform_change'] and not proof['scientific_completion'])
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:rpc(),range(2)))
  expect(f.query('select status from platform_tasks where id='+q(target['platform']))=='completed')
  expect(f.query('select count(*) from platform_assessment_incident_closures where blocker_id='+q(target['blocker']))=='1')
  expect(f.query("select count(*) from platform_events where task_id="+q(target['platform'])+" and kind='assessment-incident-closed'")=='1')
  expect(originals()==before)
 check('concurrent workers close one proven incident exactly once without research changes or a qualified release claim',concurrent)
 def refusals():
  for c in (case(witness=False),case(validated=False)):
   expect(resolution(c) is None);rpc();expect(f.query('select status from platform_tasks where id='+q(c['platform']))!='completed')
  c=case();f.query("update research_autonomy_tasks set status='blocked',reason='New independent failure' where id="+q(c['task']));expect(resolution(c) is None)
 check('resolved labels without validated evidence or a later complete recorded turn cannot close incidents',refusals)
 def uncertainty():
  c=case();f.query("insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents) values("+','.join([q(f.uid()),q(c['study']),q(c['task']),'2',q('planning'),q(prompt),q('gpt-6.1-sol'),"'{}'",q('{}'),q(workflow.digest(b'{}')),q('unknown'),'100'])+')');before=originals();expect(resolution(c) is None);rpc();expect(originals()==before)
  c=case();run=f.uid();artifact=f.uid();h=workflow.digest(b'synthetic operation')
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(artifact),q(c['platform']),q('fixture'),q(h),'19',q(c['platform']+'/'+h),q('application/json'),"'{}'"])+')')
  f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([q(run),q(c['platform']),'1',q(h),q(artifact),q('unknown'),'100'])+')');rpc();expect(f.query('select status from platform_tasks where id='+q(c['platform']))!='completed')
 check('unknown controller and supervisor outcomes retain their fences and original bytes',uncertainty)
 def controls():
  c=case();f.query('update platform_settings set paused=true where id');rpc();expect(f.query('select status from platform_tasks where id='+q(c['platform']))!='completed');f.query('update platform_settings set paused=false where id')
  f.query('update platform_tasks set cancel_requested=true where id='+q(c['platform']));rpc();expect(f.query('select status from platform_tasks where id='+q(c['platform']))!='completed')
  for role in ('anon','authenticated','service_role'):
   for signature in ('public.platform_assessment_incident_resolution(uuid)','public.platform_close_resolved_incidents(uuid)'):
    expect(f.query('select has_function_privilege('+q(role)+','+q(signature)+",'EXECUTE')")=='f')
  f.rejects(lambda:f.query("update platform_assessment_incident_closures set proof='{}' where blocker_id="+q(target['blocker'])))
 check('owner pause cancellation browser access helper bypass and immutable closure guards remain enforced',controls)
 def leased():
  c=case();token=f.uid();f.query("update platform_tasks set status='implementing',lease_token="+q(token)+",lease_until=clock_timestamp()+interval '5 minutes',worker_id="+q(worker)+' where id='+q(c['platform']))
  before=f.query('select committed_cents from platform_tasks where id='+q(c['platform']))
  flags=rpc('lease',c['platform'],token);expect(flags['incident_closure']['platform_task_id']==c['platform'])
  result=rpc('begin-run',c['platform'],token,body={});expect(result['denied']=='incident-closed')
  expect(f.query('select committed_cents from platform_tasks where id='+q(c['platform']))==before)
  other=case();f.rejects(lambda:rpc('lease',other['platform'],f.uid()));expect(f.query('select count(*) from platform_assessment_incident_closures where blocker_id='+q(other['blocker']))=='0')
  # Release only the synthetic fixture lease, through its original checkpoint.
  f.rejects(lambda:rpc('checkpoint',c['platform'],token,body=dict(status='completed',reason='Unproven completion',checkpoint={})))
  rpc('checkpoint',c['platform'],token,body=dict(status='completed',reason='Synthetic verified closure',checkpoint=dict(incident_closure=flags['incident_closure'])))
 check('a valid live lease gets closure before reservation while stale tokens cannot create closure or model usage',leased)
 def terminal_and_stopped():
  c=case();f.query("update platform_tasks set status='deadline',deadline_at=clock_timestamp()-interval '1 minute' where id="+q(c['platform']));before=f.query('select to_jsonb(t) from platform_tasks t where id='+q(c['platform']));rpc();expect(f.query('select to_jsonb(t) from platform_tasks t where id='+q(c['platform']))==before)
  c=case();f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(c['study']));expect(resolution(c) is None)
 check('expired original task outcomes and stopped assessments are not converted into successful repairs',terminal_and_stopped)
 def checkpoint_wake():
  c=case(witness=False);h=workflow.digest(b'original controller plan');artifact=f.uid()
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(artifact),q(c['platform']),q('repair-source-refresh-plan.json'),q(h),'24',q(c['platform']+'/'+h),q('application/json'),"'{}'"])+')')
  f.query("update platform_tasks set status='blocked' where id="+q(c['platform']));before=f.query('select jsonb_build_array(deadline_at,committed_cents,max_reserved_cents) from platform_tasks where id='+q(c['platform']));rpc()
  expect(f.query('select status from platform_tasks where id='+q(c['platform']))=='investigating')
  packet=js('select public.platform_repair_context_data('+q(c['platform'])+')')
  checkpoint=dict(working_evidence_contract='platform-working-evidence-v1',repair_guard=dict(version='platform-repair-handoff-v1',waiting=True,evidence_revision=packet['evidence_revision']))
  f.query("update platform_tasks set status='blocked',checkpoint="+f.sql_json(checkpoint)+' where id='+q(c['platform']));rpc()
  expect(f.query('select status from platform_tasks where id='+q(c['platform']))=='blocked')
  expect(f.query("select count(*) from platform_events where task_id="+q(c['platform'])+" and kind='working-checkpoint-delivery-available'")=='1')
  expect(f.query('select jsonb_build_array(deadline_at,committed_cents,max_reserved_cents) from platform_tasks where id='+q(c['platform']))==before)
 check('checkpoint capability wakes retained work once without resetting limits or rearming unchanged model retries',checkpoint_wake)
 def outbox():
  c=case(linked=False);expect(resolution(c) is not None);rpc()
  expect(f.query('select count(*) from platform_assessment_incident_closures where blocker_id='+q(c['blocker']))=='1')
  expect(f.query('select count(*) from platform_assessment_repair_links where blocker_id='+q(c['blocker']))=='0')
  packet=js('select public.platform_repair_context_data('+q(target['platform'])+')');expect(packet['working_checkpoint_delivery']=='platform-working-evidence-v1' and packet['incident_closure']['proof']['blocker_id']==target['blocker'])
 check('resolved outbox entries cannot mint replacement tasks and private context exposes the versioned delivery contract',outbox)
 f.report.update(passed=True,protocol='platform-incident-closure-v1');path=f.DIRECTORY/'incident-closure-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))

if __name__=='__main__':
 try:main()
 except Exception as e:
  f.report.update(passed=False,error_type=type(e).__name__,error=str(e));(f.DIRECTORY/'incident-closure-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
