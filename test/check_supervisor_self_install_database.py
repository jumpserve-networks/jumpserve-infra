"""Real SQL for one-time self-install admission and immutable activations."""
import copy,json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_incident_continuations_database as previous
import check_research_ideas_database as f
import workflow,autonomy

MIGRATION='202611020003_supervisor_self_install.sql'
def main():
 previous.main();q=f.sql_text;js=lambda sql,role='service_role':json.loads(f.query(sql,role=role) or 'null')
 def expect(value):
  if not value:raise AssertionError('Self-install admission invariant failed')
 def check(name,fn):f.check(name,lambda:(fn() or dict(passed=True)))
 before=f.query('select jsonb_build_object(\'tasks\',(select jsonb_agg(to_jsonb(t) order by id) from platform_tasks t),\'runs\',(select jsonb_agg(to_jsonb(r) order by id) from platform_runs r))')
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 check('self-install schema leaves every original task and call unchanged',lambda:expect(before==f.query('select jsonb_build_object(\'tasks\',(select jsonb_agg(to_jsonb(t) order by id) from platform_tasks t),\'runs\',(select jsonb_agg(to_jsonb(r) order by id) from platform_runs r))')))
 created=[]
 def case():
  # Synthetic old running fixtures become honestly uncertain, never successful.
  f.query("update platform_runs set status='unknown',ended_at=clock_timestamp() where status='running';update platform_settings set paused=false,automatic_releases=true;")
  if not created:
   # The preceding synthetic controller test intentionally retained a lease;
   # there is no process or provider transport behind it in this fixture.
   f.query("update platform_tasks set lease_token=null,lease_until=null;update platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until='-infinity';")
  if created:
   ids=','.join(q(v) for v in created)
   f.query("update platform_tasks set status='blocked',cancel_requested=true,lease_token=null,lease_until=null where id in ("+ids+");update platform_operations set status='failed',result='{\"synthetic_executor\":\"definite fixture teardown\"}' where status in ('pending','unknown') and task_id in ("+ids+');')
   f.query("insert into research_runtime_maintenance_releases(hold_id,reason) select id,'Definite synthetic executor teardown; no remote command exists in this fixture.' from research_runtime_maintenance_holds where task_id in ("+ids+') on conflict(hold_id) do nothing')
  task,op,artifact,token,worker=[f.uid() for _ in range(5)];revision='b'*40;h=workflow.digest(b'synthetic certificate')
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,deadline_at,worker_id,lease_token,lease_until) select '+','.join([q(task),"(select user_id from platform_operators where role='owner' limit 1)",q('Synthetic self update'),q(__doc__),"array['jumpserve-networks/jumpserve-back-end']",'authorization_version',q('deploying'),'-1',"clock_timestamp()+interval '1 hour'",q(worker),q(token),"clock_timestamp()+interval '5 minutes'"])+ ' from platform_settings where id')
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(artifact),q(task),q('supervisor-runtime-qualification.json'),q(h),'21',q(task+'/'+h),q('application/json'),"'{}'"])+')')
  request=dict(component='supervisor-runtime',revision=revision,repository='jumpserve-networks/jumpserve-back-end',qualification_artifact_id=artifact)
  f.query('insert into platform_operations(id,task_id,kind,request_sha256,request,status) values('+','.join([q(op),q(task),q('deploy'),q(workflow.digest(workflow.canonical(request))),f.sql_json(request),q('unknown')])+')')
  created.append(task);return dict(task=task,op=op,revision=revision,worker=worker,token=token)
 def admit(c,command=None,role='service_role'):
  return js('select public.platform_supervisor_install('+','.join([q(c['op']),q(c['revision']),q(command)+'::uuid' if command else 'null'])+')',role)
 def manifest(revision):return dict(version='platform-supervisor-self-repair-v1',source_revision=revision,bundle_sha256='a'*64,files={n:'1'*64 for n in ('policy.json','worker.py','self_runtime.py','store.py','common.py')})
 def activate(op,value,proof,role='service_role'):return js('select public.platform_supervisor_activate('+','.join([q(op)+'::uuid' if op else 'null',f.sql_json(value),f.sql_json(proof)])+')',role)
 def proof(value,command=None):return dict(passed=True,installed_files_verified=True,revision=value['source_revision'],bundle_sha256=value['bundle_sha256'],command_id=command)
 def concurrent():
  c=case()
  with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:admit(c),range(2)))
  expect(sum(r['dispatch_allowed'] for r in rows)==1);expect(admit(c)['dispatch_allowed'] is False)
  command=f.uid();admit(c,command);expect(admit(c)['command_id']==command)
  f.rejects(lambda:admit(c,f.uid()));f.rejects(lambda:f.query('delete from platform_supervisor_install_intents where operation_id='+q(c['op'])))
 check('concurrent self-update admits one SSM dispatch and lost acknowledgments retain immutable command identity',concurrent)
 def controls():
  for kind in ('pause','disabled','cancel','deadline','operation','certificate','handoff-window'):
   c=case()
   if kind=='pause':f.query('update platform_settings set paused=true where id')
   elif kind=='disabled':f.query('update platform_settings set automatic_releases=false where id')
   elif kind=='cancel':f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
   elif kind=='deadline':f.query("update platform_tasks set deadline_at=clock_timestamp()-interval '1 second' where id="+q(c['task']))
   elif kind=='operation':c['revision']='c'*40
   elif kind=='certificate':f.query("update platform_operations set request=request-'qualification_artifact_id' where id="+q(c['op']))
   else:f.query("insert into research_runtime_maintenance_holds(id,task_id,source_binding,reason,created_at,expires_at) select id,task_id,request_sha256,'Synthetic nearly expired handoff',clock_timestamp()-interval '9 minutes',clock_timestamp()+interval '1 minute' from platform_operations where id="+q(c['op']))
   f.rejects(lambda:admit(c));expect(f.query('select count(*) from platform_supervisor_install_intents where operation_id='+q(c['op']))=='0')
 check('pause cancellation deadlines exact operation and retained qualification fence new self-installation',controls)
 def asynchronous_handoff():
  c=case();f.query("update platform_tasks set lease_token=null,lease_until=null,status='reconciling' where id="+q(c['task']))
  parent=f.query('select id from research_autonomy_tasks limit 1');f.query('update research_autonomy_tasks set lease_token='+q(f.uid())+",lease_until=clock_timestamp()+interval '1 minute' where id="+q(parent))
  expect(admit(c)['wait_for_safe_boundary']);expiry=f.query('select expires_at from research_runtime_maintenance_holds where id='+q(c['op']))
  expect(js("select public.research_autonomy_control('lease',null,null,'{}')") is None)
  expect(admit(c)['wait_for_safe_boundary']);expect(f.query('select expires_at from research_runtime_maintenance_holds where id='+q(c['op']))==expiry)
  expect(f.query('select count(*) from platform_supervisor_install_intents where operation_id='+q(c['op']))=='0')
  f.query('update research_autonomy_tasks set lease_token=null,lease_until=null where id='+q(parent));expect(admit(c)['dispatch_allowed'])
 check('asynchronous release reserves one bounded drain handoff and installs after the polling lease is released',asynchronous_handoff)
 def receipt_after_cancel():
  c=case();admit(c);command=f.uid();f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']));expect(admit(c,command)['recorded']);expect(admit(c)['dispatch_allowed'] is False)
 check('already admitted outcomes remain recordable after cancellation without another install dispatch',receipt_after_cancel)
 def host_fencing():
  c=case();admit(c);other=f.uid();created.append(other)
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,max_reserved_cents,deadline_at) select '+q(other)+",requested_by,'Synthetic queued work',objective,repositories,authorization_version,-1,deadline_at from platform_tasks where id="+q(c['task']))
  policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
  payload=f.sql_json(dict(only_task=other,policy_sha256=policy))
  expect(js("select public.platform_worker('claim',"+q(f.uid())+'::uuid,null,null,'+payload+')') is None)
  expect(js("select public.research_model_dispatch('claim','{}')") is None)
  run=f.uid();count=f.query('select count(*) from platform_runs')
  result=js("select public.platform_worker('begin-run',"+','.join([q(c['worker']),q(c['task']),q(c['token']),f.sql_json(dict(id=run))])+')')
  expect(result['denied']=='supervisor-install-maintenance');expect(f.query('select count(*) from platform_runs')==count)
  f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
  expect(js("select public.research_autonomy_control('lease',null,null,'{}')") is None)
  expect(js("select public.research_model_dispatch('claim','{}')") is None)
  expect(f.query('select public.platform_supervisor_handoff_task()')==c['task'])
 check('admitted installation fences both workers and new model calls through cancellation until readback or bounded expiry',host_fencing)
 def activation():
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic capability wake',paper_url='https://example.org/wake.pdf',domain='Software',scope=__doc__)))['id']
  seed=js('select to_jsonb(c) from research_claims c limit 1',None);source,claim,task=[f.uid() for _ in range(3)]
  f.query('insert into research_sources select (jsonb_populate_record(null::research_sources,to_jsonb(s)||'+f.sql_json(dict(id=source,study_id=study))+')).* from research_sources s where id='+q(seed['source_id']))
  f.query('insert into research_claims(id,study_id,source_id,location,description,claim_type,scope,metrics,priority) select '+','.join([q(claim),q(study),q(source)])+',location,description,claim_type,scope,metrics,priority from research_claims where id='+q(seed['id']))
  f.query('insert into research_autonomy_tasks(id,study_id,claim_id,stage,status,label,context) values('+','.join([q(task),q(study),q(claim),q('building'),q('waiting'),q('untested'),"'{}'"])+')')
  initial=manifest('d'*40);initial_proof=proof(initial);activate(None,initial,initial_proof);before=f.query("select count(*) from research_autonomy_events where event='platform-supervisor-runtime-activated' and task_id="+q(task));expect(before=='1')
  expect(activate(None,initial,initial_proof)==initial);expect(f.query("select count(*) from research_autonomy_events where event='platform-supervisor-runtime-activated' and task_id="+q(task))==before)
  c=case();value=manifest(c['revision']);command=f.uid();admit(c);admit(c,command);expected=proof(value,command);expect(activate(c['op'],value,expected)==value)
  expect(activate(c['op'],value,expected)==value);expect(js('select public.platform_supervisor_runtime()')==value)
  expect(f.query("select count(*) from research_autonomy_events where event='platform-supervisor-runtime-activated' and task_id="+q(task))=='2')
  expect(f.query('select count(*) from research_runtime_maintenance_releases where hold_id='+q(c['op']))=='1')
  bad=copy.deepcopy(expected);bad['command_id']=f.uid();f.rejects(lambda:activate(c['op'],value,bad))
  for role in ('anon','authenticated'):f.rejects(lambda:activate(c['op'],value,expected,role))
  f.rejects(lambda:f.query("update platform_supervisor_activations set manifest='{}'"))
 check('only exact installed receipts advance immutable supervisor manifests and capability evidence is emitted once',activation)
 f.report.update(passed=True,protocol='supervisor-self-install-v1');path=f.DIRECTORY/'supervisor-self-install-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))
if __name__=='__main__':
 try:main()
 except Exception as error:
  f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'supervisor-self-install-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
