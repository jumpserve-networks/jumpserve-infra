"""Isolated SQL: exact auth-profile extension keeps original worker guards."""
import json,sys
import check_captured_provider_failures_database as previous
import check_research_ideas_database as f
import workflow
MIGRATION='202611070001_auth_entrypoint_worker_install.sql'
OLD="or t.checkpoint->'research_runtime'->'scope'->>'qualification_profile' is distinct from 'captured-provider-failures-v1'"
NEW="or coalesce(t.checkpoint->'research_runtime'->'scope'->>'qualification_profile','') not in ('captured-provider-failures-v1','auth-helper-entrypoint-v1')"
def main():
 previous.main();f.report.update(passed=False,protocol='auth-entrypoint-worker-release-v1')
 before=f.query("select prosrc from pg_proc where oid='public.research_runtime_worker_install(uuid,text,uuid)'::regprocedure")
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 after=f.query("select prosrc from pg_proc where oid='public.research_runtime_worker_install(uuid,text,uuid)'::regprocedure")
 assert before.count(OLD)==1 and after==before.replace(OLD,NEW)
 f.check('auth migration changes only the exact worker qualification allowlist; all former operation and scientific guards stay exact',lambda:dict(passed=True))
 q,j=f.sql_text,f.sql_json
 def admission(profile,passed=True,cancelled=False,paused=False):
  task,operation=f.uid(),f.uid();revision='b'*40
  checkpoint=dict(research_runtime=dict(scope=dict(qualification_profile=profile,source_binding='a'*64),certificate=dict(passed=passed)))
  body=dict(component='research-runtime',repository='jumpserve-networks/jumpserve-back-end',revision=revision)
  sql="""begin;
  update platform_settings set paused=PAUSED,automatic_releases=true where id;
  update research_autonomy_tasks set lease_until=null where status='running';
  update research_model_dispatches set status='failed',ended_at=clock_timestamp() where status in ('queued','running');
  update research_builder_calls set status='unknown',ended_at=clock_timestamp() where status='running';
  insert into research_runtime_maintenance_releases(hold_id,reason) select h.id,'Synthetic isolated peer drain' from research_runtime_maintenance_holds h where not exists(select 1 from research_runtime_maintenance_releases r where r.hold_id=h.id);
  insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,status,max_reserved_cents,deadline_at,cancel_requested,checkpoint)
   select TASK,ACTOR,'Synthetic auth installer','Exact auth CLI repair',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'platform_manual','deploying',-1,clock_timestamp()+interval '1 hour',CANCELLED,CHECKPOINT from platform_settings where id;
  insert into platform_operations(id,task_id,kind,request_sha256,request) values(OP,TASK,'deploy',SHA,BODY);
  do $test$ declare result jsonb;begin
   result=public.research_runtime_worker_install(OP,REV,null);
   if result->'dispatch_allowed' is distinct from 'true'::jsonb then raise exception 'Qualified auth profile was not admitted';end if;
   result=public.research_runtime_worker_install(OP,REV,null);
   if result->'dispatch_allowed' is distinct from 'false'::jsonb then raise exception 'Duplicate worker command admitted';end if;
  end $test$;rollback;"""
  for key,value in dict(PAUSED=str(paused).lower(),CANCELLED=str(cancelled).lower(),CHECKPOINT=j(checkpoint),TASK=q(task),ACTOR=q(f.ACTOR),OP=q(operation)+'::uuid',REV=q(revision),SHA=q(workflow.digest(workflow.canonical(body))),BODY=j(body)).items():sql=sql.replace(key,value)
  f.query(sql)
 f.check('new auth and existing captured-recovery profiles both admit one original install intent',lambda:[admission(p) for p in ('auth-helper-entrypoint-v1','captured-provider-failures-v1')])
 f.check('unknown or absent qualification profiles never admit worker installation',lambda:[f.rejects(lambda p=p:admission(p)) for p in (None,'unreviewed-profile')])
 f.check('auth profile retains certificate, cancellation and owner pause guards',lambda:[f.rejects(lambda kwargs=kwargs:admission('auth-helper-entrypoint-v1',**kwargs)) for kwargs in (dict(passed=False),dict(cancelled=True),dict(paused=True))])
 def permissions():
  for role in ('anon','authenticated'):assert f.query('select has_function_privilege('+q(role)+",'public.research_runtime_worker_install(uuid,text,uuid)','execute')")=='f'
  assert f.query("select has_function_privilege('service_role','public.research_runtime_worker_install(uuid,text,uuid)','execute')")=='t'
 f.check('extended installer remains service-only',permissions)
 f.report['passed']=True;path=f.DIRECTORY/'auth-entrypoint-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))
if __name__=='__main__':main()
