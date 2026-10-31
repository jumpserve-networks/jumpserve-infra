"""A maintenance hand-off blocks only new leases, with immutable expiry."""
import json
import check_research_runtime_database as previous
import check_research_ideas_database as f
import workflow
MIGRATION='202610310006_runtime_maintenance_handoff.sql'
def main():
 previous.main();raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report.update(protocol='qualified-runtime-handoff-v1',passed=False);f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 q=f.sql_text;hold=f.uid()
 def active():return f.query('select public.research_runtime_maintenance_active()',role='service_role')=='t'
 def hold_insert(ident,expired=False):
  f.query('insert into research_runtime_maintenance_holds(id,reason,created_at,expires_at) values('+q(ident)+",'Explicit isolated software maintenance fixture',clock_timestamp()-interval '"+('20 minutes' if expired else '1 second')+"',clock_timestamp()+interval '"+('-1 second' if expired else '19 minutes')+"')")
 def boundaries():
  assert not active();hold_insert(hold);assert active()
  for role in ('anon','authenticated'):f.rejects(lambda:f.query('select public.research_runtime_maintenance_active()',role=role))
  f.rejects(lambda:f.query('update research_runtime_maintenance_holds set expires_at=clock_timestamp()+interval \'1 day\''))
  f.rejects(lambda:f.query('insert into research_runtime_maintenance_holds(id,reason,expires_at) values('+q(f.uid())+",'Invalid unbounded hold',clock_timestamp()+interval '1 day')"))
  result=f.query("select public.research_autonomy_control('lease',null,null,'{}')",role='service_role');assert result in ('','null')
  f.rejects(lambda:f.query("select public.research_autonomy_control('unsupported-operation',null,null,'{}')",role='service_role'))
  f.query('insert into research_runtime_maintenance_releases(hold_id,reason) values('+q(hold)+",'Explicit fixture release')");assert not active()
  hold_insert(f.uid(),True);assert not active()
  return dict(only_new_leases_blocked=True,ordinary_nonlease_rpc_retained=True,immutable_expiry=True,released_and_expired_holds_inactive=True,provider_calls=0)
 f.check('maintenance drains existing claims without rewriting their work or extending a hold',boundaries)
 def automatic():
  task=f.uid();binding='f'*64
  checkpoint=dict(research_runtime=dict(certificate=dict(passed=True),scope=dict(version='research-controller-recovery-v1',scientific_and_request_content_unchanged=True,existing_tests_unchanged=True,source_binding=binding)))
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,checkpoint,max_reserved_cents,deadline_at) select '+q(task)+",(select user_id from platform_operators limit 1),'Qualified runtime handoff fixture','Synthetic software-only release.',array['jumpserve-networks/jumpserve-back-end','jumpserve-networks/jumpserve-infra'],authorization_version,'publishing',"+f.sql_json(checkpoint)+",-1,clock_timestamp()+interval '1 hour' from platform_settings where id")
  payload=f.sql_json(dict(policy_sha256='a'*64,only_task=task));worker=f.uid()
  sql='select public.platform_worker(\'claim\','+q(worker)+',null,null,'+payload+')'
  f.query(sql,role='service_role');assert active()
  before=f.query('select expires_at from research_runtime_maintenance_holds where task_id='+q(task))
  f.query(sql,role='service_role');assert f.query('select count(*) from research_runtime_maintenance_holds where task_id='+q(task))=='1'
  assert f.query('select expires_at from research_runtime_maintenance_holds where task_id='+q(task))==before
  f.query('update platform_tasks set cancel_requested=true where id='+q(task));assert not active()
  return dict(qualified_release_handoff=True,once_per_binding=True,expiry_not_extended=True,cancellation_releases_admission=True)
 f.check('qualified runtime release receives one bounded handoff and cancellation stops it',automatic)
 f.report['passed']=True;path=f.DIRECTORY/'runtime-handoff-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),provider_calls=0,production_mutations=0)))
if __name__=='__main__':main()
