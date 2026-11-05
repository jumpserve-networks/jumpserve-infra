"""Exercise the owner-only initializer recovery transaction in isolated Postgres."""
import json
import check_dedicated_intake_database as previous
import check_research_ideas_database as f


def main():
 previous.main();q=f.sql_text;j=f.sql_json
 template=(f.ROOT/'assets/platform/intake-initialization-resume.sql').read_text()
 body=template.split('begin;',1)[1].rsplit('commit;',1)[0]
 reason='Autonomous operation unconfirmed (KeyError); reconcile retained identities before continuing.'
 def case(change='',deadline="clock_timestamp()+interval '7 days'",created='clock_timestamp()'):
  study,task,release=f.uid(),f.uid(),f.uid()
  sql="begin; update research_autonomy_tasks set status='blocked',lease_token=null,lease_until=null;update research_model_dispatches set status='unknown' where status in ('queued','running');update platform_settings set paused=false;"
  sql+='update research_intake_runtime set enabled=false,status=\'ready\',seen_at=clock_timestamp(),configuration='+j(dict(source_binding='d'*64,gateway_verified=True,native_version='2026.10.5'))+' where id;'
  sql+='insert into research_studies(id,title,paper_url,domain,scope) values('+q(study)+",'Synthetic fresh intake','https://example.org/paper.pdf','Networking','Local initialization recovery');"
  sql+='insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256,created_at,deadline_at) values('+q(study)+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'),"+created+','+deadline+');'
  sql+='insert into research_paper_reviews(study_id,status,reason) values('+q(study)+",'failed',"+q(reason)+');'
  sql+='insert into research_autonomy_tasks(id,study_id,stage,status,context,reason) values('+q(task)+','+q(study)+",'intake','blocked',"+j(dict(intake_pool_version='warm-intake-v1'))+','+q(reason)+');'
  sql+="create temporary table before_recovery as select to_jsonb(w)-array['status','updated_at'] as workflow from research_autonomy_workflows w where study_id="+q(study)+';'
  if change=='unknown':
   prompt=f.query("select id from agent_prompt_versions where module_id='research-autonomy' and published_at is not null limit 1")
   sql+='insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents) values('+','.join([q(f.uid()),q(study),q(task),'1',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'::jsonb",q('{}'),"encode(sha256(convert_to('{}','UTF8')),'hex')",q('unknown'),'100'])+');'
  elif change=='pause':sql+='update platform_settings set paused=true;'
  elif change=='partial':sql+="update research_autonomy_tasks set context=context||'{\"last_turn_id\":\"retained\"}'::jsonb where id="+q(task)+';'
  elif change=='source':sql+="update research_intake_runtime set configuration=configuration||'{\"source_binding\":\"wrong\"}'::jsonb where id;"
  elif change=='stale':sql+="update research_intake_runtime set seen_at=clock_timestamp()-interval '2 minutes' where id;"
  for key,value in dict(STUDY=study,BINDING='d'*64,RELEASE=release,REVISION='c'*40).items():body_case=body.replace('@'+key+'@',value) if key=='STUDY' else body_case.replace('@'+key+'@',value)
  sql+=body_case
  sql+="do $$begin if not exists(select 1 from research_autonomy_tasks where id="+q(task)+" and status='queued' and attempts=0 and context='{\"intake_pool_version\":\"warm-intake-v1\"}'::jsonb) then raise exception 'Task recovery differs';end if;"
  sql+="if (select to_jsonb(w)-array['status','updated_at'] from research_autonomy_workflows w where study_id="+q(study)+") is distinct from (select workflow from before_recovery) then raise exception 'Original workflow limits or identity changed';end if;"
  sql+="if not exists(select 1 from research_paper_reviews where study_id="+q(study)+" and status='preparing' and revision=2 and confirmed_at is null) then raise exception 'Review recovery differs';end if;end $$; rollback;"
  return sql
 def reject(sql,message):
  try:f.query(sql)
  except RuntimeError as error:
   assert message in str(error),str(error);return
  raise AssertionError('Expected an explicit recovery refusal')
 f.check('fresh zero-call initialization recovery preserves every original workflow limit and identity',lambda:f.query(case()))
 f.check('an original unknown provider turn cannot be resumed by initializer recovery',lambda:reject(case('unknown'),'Only an untouched'))
 f.check('a retained partial context cannot be reclassified as a fresh paper',lambda:reject(case('partial'),'Only an untouched'))
 f.check('owner pause stops initialization recovery',lambda:reject(case('pause'),'Owner controls'))
 f.check('wrong source and stale heartbeats refuse initialization recovery',lambda:[reject(case(mode),'Routing must be disabled') for mode in ('source','stale')])
 f.check('expired original deadline cannot be extended by initialization recovery',lambda:reject(case(deadline="clock_timestamp()-interval '1 hour'",created="clock_timestamp()-interval '2 hours'"),'Only an untouched'))
 path=f.DIRECTORY/'intake-initialization-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),production_mutations=0,provider_calls=0)))


if __name__=='__main__':main()
