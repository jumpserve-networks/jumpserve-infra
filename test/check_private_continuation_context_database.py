"""New continuation context stays private across differing default ACLs."""
import json
import check_supervisor_self_install_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202611020004_private_incident_continuation_context.sql'
def main():
 previous.main();before=f.query("select encode(sha256(convert_to(prosrc,'UTF8')),'hex') from pg_proc where oid='public.platform_repair_context_data(uuid)'::regprocedure")
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 def private():
  for role in ('anon','authenticated','service_role'):
   f.rejects(lambda:f.query('select public.platform_repair_context_data('+f.sql_text(f.uid())+'::uuid)',role=role))
  after=f.query("select encode(sha256(convert_to(prosrc,'UTF8')),'hex') from pg_proc where oid='public.platform_repair_context_data(uuid)'::regprocedure")
  assert after==before
  assert f.query("select has_function_privilege('service_role','public.platform_worker(text,uuid,uuid,uuid,jsonb)','EXECUTE')")=='t'
  binding=json.loads(f.query("select jsonb_build_object('task',a.platform_task_id,'study',b.study_id) from platform_assessment_repair_attempts a join platform_assessment_blockers b on b.id=a.blocker_id order by a.created_at desc limit 1"))
  worker,token=f.uid(),f.uid();q=f.sql_text
  # Revive only this synthetic local fixture's lease for a positive checked-RPC
  # read. No provider transport or production assessment is involved.
  f.query("update platform_settings set paused=false;update research_autonomy_workflows set status='running' where study_id="+q(binding['study'])+";update platform_tasks set status='investigating',cancel_requested=false,worker_id="+q(worker)+',lease_token='+q(token)+",lease_until=clock_timestamp()+interval '1 minute' where id="+q(binding['task']))
  call='select public.platform_repair_context('+','.join([q(worker),q(binding['task']),q(token)])+')'
  packet=json.loads(f.query(call,role='service_role'));assert packet['continuation_contract']=='platform-incident-continuation-v1' and packet['incident_continuation']['platform_task_id']==binding['task']
  for role in ('anon','authenticated'):f.rejects(lambda:f.query(call,role=role))
  f.rejects(lambda:f.query('select public.platform_repair_context('+','.join([q(worker),q(binding['task']),q(f.uid())])+')',role='service_role'))
  return dict(helper_denied_to_browser_and_direct_service=True,implementation_unchanged=True,leased_worker_rpc_retained=True)
 f.check('continuation context helper explicitly denies inherited browser and direct-service execution',private)
 f.report.update(passed=True,protocol='private-incident-continuation-context-v1');path=f.DIRECTORY/'private-continuation-context-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))
if __name__=='__main__':main()
