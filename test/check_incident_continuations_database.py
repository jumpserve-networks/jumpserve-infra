"""Immutable incident continuations in disposable PostgreSQL; no cloud calls."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_platform_reconciliation_database as previous
import check_research_ideas_database as f
import autonomy,workflow,model_dispatch as dispatch

MIGRATION='202611020002_platform_incident_continuations.sql'

def main():
 previous.main();q=f.sql_text;js=lambda sql,role=None:json.loads(f.query(sql,role=role) or 'null')
 def expect(value):
  if not value:raise AssertionError('Incident continuation invariant failed')
 def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
 def snapshot():return f.query("select jsonb_build_object('tasks',(select jsonb_agg(to_jsonb(t) order by id) from platform_tasks t),'runs',(select jsonb_agg(to_jsonb(r) order by id) from platform_runs r),'links',(select jsonb_agg(to_jsonb(l) order by blocker_id) from platform_assessment_repair_links l),'assessments',(select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w),'budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b))")
 original=snapshot();raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 check('continuation migration leaves original tasks ledgers links assessments and budgets unchanged',lambda:expect(snapshot()==original))
 worker=f.uid();policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id');seed=js('select to_jsonb(c) from research_claims c limit 1')
 def rpc(op='maintenance',task=None,token=None,body=None,role='service_role'):
  return js('select public.platform_worker('+','.join([q(op),q(worker),q(task)+'::uuid' if task else 'null',q(token)+'::uuid' if token else 'null',f.sql_json(dict(policy_sha256=policy) if body is None else body)])+')',role)
 def reset():
  # Only this isolated fixture DB: previous cases are quiesced, never deleted.
  f.query("update research_autonomy_workflows set status='cancelled';update research_autonomy_tasks set status='cancelled',lease_token=null,lease_until=null;update platform_tasks set status='blocked',cancel_requested=true,lease_token=null,lease_until=null;update platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until='-infinity';update platform_settings set paused=false;update autonomy_budget_categories set max_spend_cents=-1,max_model_calls=-1,change_reason='Isolated continuation fixture';")
  f.query("insert into research_runtime_maintenance_releases(hold_id,reason) select id,'Synthetic continuation teardown' from research_runtime_maintenance_holds on conflict do nothing;update research_model_dispatches set lease_until=clock_timestamp()-interval '1 second' where status='running';")
  dispatch.rpc('claim',{});rpc('heartbeat',body=dict(status='ready',reason='Synthetic continuation fixture'))
 def case(status='deadline',run_status='failed'):
  reset()
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic incident continuation',paper_url='https://example.org/continuation.pdf',domain='Software',scope=__doc__)))['id']
  claim,source,task,blocker,root,artifact,run=[f.uid() for _ in range(7)]
  f.query('insert into research_sources select (jsonb_populate_record(null::research_sources,to_jsonb(s)||'+f.sql_json(dict(id=source,study_id=study))+')).* from research_sources s where id='+q(seed['source_id']))
  f.query('insert into research_claims(id,study_id,source_id,location,description,claim_type,scope,metrics,priority) select '+','.join([q(claim),q(study),q(source)])+',location,description,claim_type,scope,metrics,priority from research_claims where id='+q(seed['id']))
  f.query('insert into research_autonomy_tasks(id,study_id,claim_id,stage,status,label,context,reason) values('+','.join([q(task),q(study),q(claim),q('building'),q('waiting'),q('inconclusive'),f.sql_json(dict(frozen='unchanged scientific criterion')),q('Original unknown research outcome; inspect without replay')])+')')
  f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join([q(blocker),q(study),q(task),q('task'),q(task),q('building'),q('waiting'),q('Original implementation failure'),q('a'*64),q(workflow.digest(blocker.encode()))])+')')
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,budget_category,max_reserved_cents,committed_cents,deadline_at) select '+','.join([q(root),"(select user_id from platform_operators where role='owner' limit 1)",q('Original expired repair'),q('Repair the synthetic incident'),"array['jumpserve-networks/jumpserve-back-end']",'authorization_version',q(status),q('platform_repair'),'-1','100',"clock_timestamp()-interval '1 hour'"])+ ' from platform_settings where id')
  f.query('insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(root)+')')
  h=workflow.digest(b'original request');f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(artifact),q(root),q('original-request'),q(h),'16',q(root+'/'+h),q('application/json'),"'{}'"])+')')
  f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents,reason,ended_at) values('+','.join([q(run),q(root),'1',q(h),q(artifact),q(run_status),'100',q('Original retained result'),'clock_timestamp()'])+')')
  return dict(study=study,task=task,blocker=blocker,root=root,run=run)
 def attempts(c):return js('select coalesce(jsonb_agg(to_jsonb(a) order by generation),\'[]\') from platform_assessment_repair_attempts a where blocker_id='+q(c['blocker']))
 def originals(c):return f.query('select jsonb_build_object(\'task\',(select to_jsonb(p) from platform_tasks p where id='+q(c['root'])+'),\'run\',(select to_jsonb(r) from platform_runs r where id='+q(c['run'])+'),\'assessment\',(select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(c['study'])+'))')
 def child(c):return attempts(c)[-1]['platform_task_id']
 def settle(ident):f.query("update platform_tasks set status='deadline',lease_token=null,lease_until=null where id="+q(ident)+";update platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until='-infinity';")
 def changed(c):f.query('insert into research_autonomy_events(study_id,task_id,event,details) values('+','.join([q(c['study']),q(c['task']),q('new-retained-diagnostic'),f.sql_json(dict(artifact_sha256=workflow.digest(f.uid().encode())))])+')')
 def concurrent():
  c=case();before=originals(c)
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:rpc(),range(2)))
  rows=attempts(c);expect(len(rows)==1 and rows[0]['carried_cents']==100 and rows[0]['carried_calls']==1 and originals(c)==before)
  p=js('select to_jsonb(t) from platform_tasks t where id='+q(child(c)));expect(p['committed_cents']==100 and p['priority']==0 and p['budget_category']=='platform_repair')
  expect(f.query('select deadline_at<=(select deadline_at from research_autonomy_workflows where study_id='+q(c['study'])+') and deadline_at<=clock_timestamp()+interval \'6 hours\' from platform_tasks where id='+q(child(c)))=='t')
  leased=rpc('claim',body=dict(policy_sha256=policy));expect(leased['id']==child(c) and leased['assessment_repair'])
  context=js('select public.platform_repair_context('+','.join([q(worker),q(child(c)),q(leased['lease_token'])])+')','service_role');expect(context['incident_continuation']['previous_task_id']==c['root'] and context['continuation_contract']=='platform-incident-continuation-v1')
 check('concurrent maintenance creates one bounded claim-linked continuation with original evidence and carried reservations',concurrent)
 def unchanged():
  c=case();rpc();ident=child(c);settle(ident)
  for _ in range(3):rpc()
  expect(len(attempts(c))==1)
  f.query('update research_autonomy_tasks set next_at=clock_timestamp(),updated_at=clock_timestamp(),attempts=attempts+1 where id='+q(c['task']));rpc();expect(len(attempts(c))==1)
  changed(c);rpc();expect(len(attempts(c))==2 and attempts(c)[1]['previous_task_id']==ident)
 check('unchanged evidence clocks and polling cannot mint repeated attempts while genuine diagnostics can',unchanged)
 def operational_failures():
  c=case();rpc();ident=child(c);settle(ident)
  packet=js('select public.platform_repair_context_data('+q(ident)+')')
  f.query("update platform_tasks set status='blocked',deadline_at=clock_timestamp()+interval '1 hour',checkpoint=checkpoint||"+f.sql_json(dict(supervisor_failure=dict(version='platform-supervisor-failure-v1',fingerprint='d'*64,repeated=1),repair_guard=dict(version='platform-repair-handoff-v1',waiting=True,evidence_revision=packet['evidence_revision'])))+' where id='+q(ident))
  changed(c);rpc();expect(len(attempts(c))==2);expect(f.query('select status from platform_tasks where id='+q(ident))=='blocked');second=child(c);settle(second)
  expect(js('select public.platform_repair_context_data('+q(second)+')')['incident_continuation']['predecessor_failure']['fingerprint']=='d'*64)
  f.query('update platform_tasks set checkpoint=jsonb_set(checkpoint,\'{supervisor_failure,repeated}\',\'20\') where id='+q(ident));rpc();expect(len(attempts(c))==2)
  f.query('insert into platform_operations(id,task_id,kind,request_sha256,request,status,result) values('+','.join([q(f.uid()),q(second),q('deploy'),q('e'*64),"'{}'",q('failed'),f.sql_json(dict(status='definite-failure',production_revision_verified=False))])+')')
  rpc();expect(len(attempts(c))==3)
  expect(js('select public.platform_repair_context_data('+q(child(c))+')')['incident_continuation']['predecessor_operations'][0]['status']=='failed')
 check('new trusted controller faults and definite release failures permit follow-up while repetition counters do not',operational_failures)
 def fences():
  for kind in ('unknown','cleanup','external','cancel','parent-cancel','parent-deadline','paused'):
   c=case(run_status='unknown' if kind=='unknown' else 'failed');before=originals(c)
   if kind=='cleanup':f.query('update platform_tasks set checkpoint=\'{"cleanup_unknown":true}\' where id='+q(c['root']))
   elif kind=='external':f.query('insert into platform_operations(id,task_id,kind,request_sha256,request,status) values('+','.join([q(f.uid()),q(c['root']),q('deploy'),q('b'*64),"'{}'",q('unknown')])+')')
   elif kind=='cancel':f.query('update platform_tasks set cancel_requested=true where id='+q(c['root']))
   elif kind=='parent-cancel':f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(c['study']))
   elif kind=='parent-deadline':f.query("update research_autonomy_workflows set status='deadline' where study_id="+q(c['study']))
   elif kind=='paused':f.query('update platform_settings set paused=true where id')
   rpc();expect(attempts(c)==[])
   if kind=='unknown':expect(originals(c)==before)
 check('uncertain originals shared cleanup external operations cancellation and parent stops forbid continuation',fences)
 def budgets():
  for field in ('max_spend_cents','max_model_calls'):
   c=case();limit=100 if field=='max_spend_cents' else 1
   f.query('update autonomy_budget_categories set '+field+'='+str(limit)+",change_reason='Synthetic finite family limit' where category='platform_repair'");rpc();expect(attempts(c)==[])
   f.query('update autonomy_budget_categories set '+field+'='+str(limit*2)+",change_reason='Synthetic budget amendment' where category='platform_repair'");rpc();expect(len(attempts(c))==1)
   leased=rpc('claim',body=dict(policy_sha256=policy));expect(leased['id']==child(c));flags=rpc('lease',child(c),leased['lease_token'],{});expect(flags['model_calls']==1 and flags['committed_cents']==100)
   ref=f.uid();h=workflow.digest(b'new request');f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(ref),q(child(c)),q('new-request'),q(h),'11',q(child(c)+'/'+h),q('application/json'),"'{}'"])+')')
   run=f.uid();admitted=rpc('begin-run',child(c),leased['lease_token'],dict(id=run,request_sha256=h,request_artifact_id=ref));expect(admitted['status']=='running')
   rpc('finish-run',child(c),leased['lease_token'],dict(id=run,status='failed',reason='Synthetic definite failure',response_artifact_id=None,usage=None))
   denied=rpc('begin-run',child(c),leased['lease_token'],dict(id=f.uid(),request_sha256=h,request_artifact_id=ref));expect(denied['denied']=='budget')
 check('finite money and call limits span the entire incident family and never reset on a new attempt',budgets)
 def access():
  c=case();rpc();row=attempts(c)[0]
  for role in ('anon','authenticated'):f.rejects(lambda role=role:rpc(role=role))
  for role in ('anon','authenticated','service_role'):
   for signature in ('public.platform_continue_assessment_incidents()','public.platform_repair_family(uuid)','public.platform_worker_before_continuations_v9(text,uuid,uuid,uuid,jsonb)'):
    expect(f.query('select has_function_privilege('+q(role)+','+q(signature)+",'EXECUTE')")=='f')
  f.rejects(lambda:f.query("update platform_assessment_repair_attempts set proof='{}' where id="+q(row['id'])))
  f.rejects(lambda:f.query('select * from platform_assessment_repair_bindings',role='anon'))
  leased=rpc('claim',body=dict(policy_sha256=policy));f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(c['study']))
  expect(rpc('lease',child(c),leased['lease_token'],{})['cancel_requested'])
  expect(rpc('begin-run',child(c),leased['lease_token'],dict(id=f.uid()))['denied']=='assessment-stopped')
 check('continuation records and helpers stay private immutable and every inherited parent-stop gate sees new attempts',access)
 f.report.update(passed=True,protocol='platform-incident-continuations-v1');path=f.DIRECTORY/'incident-continuations-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))

if __name__=='__main__':
 try:main()
 except Exception as error:
  f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'incident-continuations-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
