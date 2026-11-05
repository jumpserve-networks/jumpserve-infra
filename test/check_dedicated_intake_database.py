"""Actual local SQL admission, parallel identities and uncertainty boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
import check_platform_capability_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202611050001_dedicated_intake.sql'
def main():
 previous.main();raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 q=f.sql_text;j=f.sql_json
 def js(sql,role=None):return json.loads(f.query(sql,role=role) or 'null')
 def rpc(op,payload=None,role='service_role',name='research_intake_control'):
  return js('select public.'+name+'('+q(op)+','+j(payload or {})+')',role)
 def case():
  study,task,token=f.uid(),f.uid(),f.uid();context=dict(chunk_index=0,source_id=f.uid(),text_artifact_id=f.uid())
  f.query("update research_autonomy_workflows set status='cancelled';update research_intake_runtime set enabled=true,status='ready',seen_at=clock_timestamp() where id")
  f.query('insert into research_studies(id,title,paper_url,domain,scope) values('+q(study)+",'Synthetic intake','https://example.org/paper.pdf','Networking','Local software fixture');insert into research_study_owners(study_id,owner_id) values("+q(study)+','+q(f.ACTOR)+');insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256) values('+q(study)+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'));insert into research_paper_reviews(study_id) values("+q(study)+');insert into research_autonomy_tasks(id,study_id,stage,status,context,lease_token,lease_until) values('+q(task)+','+q(study)+",'intake','running',"+j(context)+','+q(token)+",clock_timestamp()+interval '420 seconds')")
  return dict(study=study,task=task,token=token)
 def chunks(c,values=None):return rpc('chunks',dict(task_id=c['task'],token=c['token'],chunks=values or [dict(index=i,sha256=str(i)*64) for i in (0,1)]))
 def private():
  assert rpc('health')['enabled'] is False
  for role in ('anon','authenticated'):
   f.rejects(lambda:rpc('health',role=role))
   f.rejects(lambda:f.query('select * from research_intake_runtime',role=role))
  f.rejects(lambda:f.query('update research_intake_runtime set enabled=true',role='service_role'))
  rpc('heartbeat',dict(version='warm-intake-v1',worker_id=f.uid(),status='ready',configuration=dict(native_version='2026.10.5',gateway_verified=True)),name='research_intake_dispatch')
  assert rpc('health')['enabled'] is False
 f.check('dedicated intake starts disabled; private heartbeat cannot authorize routing',private)
 def identities():
  c=case();before=f.query('select jsonb_build_array(deadline_at,max_spend_cents,committed_cents,initial_sha256) from research_autonomy_workflows where study_id='+q(c['study']))
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:chunks(c),range(2)))
  assert results==[dict(complete=0,remaining=2)]*2
  assert f.query('select count(*) from research_autonomy_tasks where intake_parent_id='+q(c['task']))=='2'
  assert f.query('select jsonb_build_array(deadline_at,max_spend_cents,committed_cents,initial_sha256) from research_autonomy_workflows where study_id='+q(c['study']))==before
  f.rejects(lambda:chunks(c,[dict(index=0,sha256='f'*64)]))
  for values in ([dict(index=0)],[dict(index=None,sha256='a'*64)],[dict(index=0,sha256='a'*64,extra=True)],[dict(index=0,sha256='a'*64)]*2):
   f.rejects(lambda:chunks(c,values))
  f.rejects(lambda:rpc('chunks',dict(task_id=c['task'],token=f.uid(),chunks=[dict(index=0,sha256='a'*64)])))
 f.check('concurrent chunk admission is idempotent and preserves original assessment limits and exact identities',identities)
 def parallel():
  c=case();chunks(c)
  f.query("update research_autonomy_tasks set status='waiting',lease_token=null,lease_until=null where id="+q(c['task']))
  # Existing supervisor leases deliberately remain present in this fixture.
  with ThreadPoolExecutor(max_workers=2) as pool:leased=list(pool.map(lambda _:rpc('lease'),range(2)))
  assert all(t and t['intake_parent_id']==c['task'] and t['intake_pool'] for t in leased)
  assert len({t['id'] for t in leased})==2;assert rpc('lease') is None
  child=leased[0]
  f.rpc('research_autonomy_control',dict(p_operation='advance',p_actor=f.ACTOR,p_study=c['study'],p_payload=dict(task_id=child['id'],token=child['lease_token'],status='finished',stage='intake',context=child['context'],reason='Synthetic validated chunk complete.',label=None,delay_seconds=0,usage={})))
  assert f.query('select status from research_paper_reviews where study_id='+q(c['study']))=='preparing'
  # A controller bug cannot declare the parent complete while a sibling is live.
  f.query("update research_autonomy_tasks set status='running',lease_token="+q(c['token'])+",lease_until=clock_timestamp()+interval '420 seconds' where id="+q(c['task']))
  f.rejects(lambda:f.rpc('research_autonomy_control',dict(p_operation='advance',p_actor=f.ACTOR,p_study=c['study'],p_payload=dict(task_id=c['task'],token=c['token'],status='finished',stage='intake',context={},reason='Synthetic premature root finish.',label=None,delay_seconds=0,usage={}))))
  f.query("update research_autonomy_tasks set status='waiting',lease_token=null,lease_until=null where id="+q(c['task']))
  assert rpc('lease') is None # parent cannot claim readiness while sibling runs
  f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(c['study']))
  assert rpc('lease') is None
 f.check('two independent chunks lease concurrently despite repair work; partial completion cannot mark the paper ready and cancellation stops admission',parallel)
 def uncertainty():
  c=case();turn=f.uid();prompt=f.query("select id from agent_prompt_versions where module_id='research-autonomy' and published_at is not null limit 1")
  f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents) values('+','.join([q(turn),q(c['study']),q(c['task']),'1',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'::jsonb",q('{}'),q(workflow.digest(b'{}')),q('unknown'),'100'])+')')
  assert chunks(c)['blocked'];assert f.query('select count(*) from research_autonomy_tasks where intake_parent_id='+q(c['task']))=='0'
 f.check('parallel child identities cannot bypass an original unknown intake call',uncertainty)
 def expiry_and_rollback():
  c=case();chunks(c)
  f.query("update research_autonomy_tasks set status='waiting',lease_token=null,lease_until=null where id="+q(c['task']))
  child=rpc('lease');assert child and child['intake_parent_id']==c['task']
  f.query("update research_autonomy_tasks set lease_until=clock_timestamp()-interval '1 second' where id="+q(child['id']))
  leases=[rpc('lease'),rpc('lease')];resumed=next((t for t in leases if t and t['id']==child['id']),None)
  assert resumed and resumed['lease_token']!=child['lease_token']
  # Disable routing during a rollback. General workers must not receive a child
  # or its partially extracted root, even if their next-at times are eligible.
  f.query('update research_intake_runtime set enabled=false where id')
  assert rpc('lease') is None
  definition=f.query("select string_agg(pg_get_functiondef(oid),E'\\n') from pg_proc where pronamespace='public'::regnamespace and proname like 'research_autonomy_%'")
  assert 'not exists(select 1 from public.research_autonomy_tasks ic where ic.intake_parent_id=a.id)' in definition
  assert 'a.intake_parent_id is null' in definition
  assert "coalesce(a.context->>'intake_pool_version','')<>'warm-intake-v1'" in definition
 f.check('expired controller-only chunk work keeps its identity; rollback pauses partial roots and children',expiry_and_rollback)
 def dispatch_lanes():
  f.query("update platform_tasks set status='blocked',lease_token=null,lease_until=null,checkpoint=checkpoint-'cleanup_unknown';update research_autonomy_tasks set status='blocked',lease_token=null,lease_until=null;update platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until='-infinity';update platform_settings set paused=false;insert into research_runtime_maintenance_releases(hold_id,reason) select id,'Dedicated intake local fixture teardown.' from research_runtime_maintenance_holds on conflict do nothing")
  c=case();chunks(c);f.query("update research_autonomy_tasks set status='waiting',lease_token=null,lease_until=null where id="+q(c['task']))
  children=[rpc('lease'),rpc('lease')];prompt=f.query("select id from agent_prompt_versions where module_id='research-autonomy' and published_at is not null limit 1")
  ids=[]
  for child in children:
   ident=f.uid();ids.append(ident)
   f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents) values('+','.join([q(ident),q(c['study']),q(child['id']),'1',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'::jsonb",q('{}'),q(workflow.digest(b'{}')),q('running'),'100'])+')')
   payload=dict(id=ident,study_id=c['study'],task_id=child['id'],request_raw='{}',request_sha256=workflow.digest(b'{}'),runtime='openclaw-production-v1')
   assert not rpc('enqueue',payload,name='research_intake_dispatch')['replayed']
   assert rpc('enqueue',payload,name='research_intake_dispatch')['replayed']
  # The old shared-host selector can never claim dedicated requests.
  assert rpc('claim',name='research_model_dispatch') is None
  jobs=[rpc('claim',name='research_intake_dispatch'),rpc('claim',name='research_intake_dispatch')]
  assert {job['id'] for job in jobs}==set(ids);assert rpc('claim',name='research_intake_dispatch') is None
  f.rejects(lambda:rpc('finish',dict(id=jobs[0]['id'],token=f.uid(),status='failed',provenance={}),name='research_intake_dispatch'))
  ident=f.uid();worker=f.uid();policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,priority,max_reserved_cents,deadline_at) select '+q(ident)+",(select user_id from platform_operators where role='owner' limit 1),'Synthetic independent repair','Local host admission only.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'platform_repair',0,-1,clock_timestamp()+interval '1 hour' from platform_settings where id")
  def work(op,payload):return js('select public.platform_worker('+','.join([q(op),q(worker),'null','null',j(payload)])+')','service_role')
  work('heartbeat',dict(status='ready',reason='Local intake independence fixture.'))
  admitted=work('claim',dict(policy_sha256=policy,only_task=ident))
  assert admitted and admitted['id']==ident
 f.check('two original intake dispatches claim in their own lane while the repair supervisor can lease its separate host',dispatch_lanes)
 def budget():
  c=case();f.query("update research_autonomy_tasks set status='queued',lease_token=null,lease_until=null where id="+q(c['task']))
  f.query("update autonomy_budget_categories set max_spend_cents=100,change_reason='Synthetic intake ceiling' where category='research_assessment'")
  before=f.query('select committed_cents from research_autonomy_workflows where study_id='+q(c['study']));assert rpc('lease') is None
  assert f.query('select committed_cents from research_autonomy_workflows where study_id='+q(c['study']))==before
  f.query("update autonomy_budget_categories set max_spend_cents=-1,change_reason='Restore local fixture' where category='research_assessment'")
 f.check('dedicated admission honors the shared assessment budget without resets',budget)
 f.report.update(passed=True,protocol='dedicated-warm-intake-v1');path=f.DIRECTORY/'dedicated-intake-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))

if __name__=='__main__':main()
