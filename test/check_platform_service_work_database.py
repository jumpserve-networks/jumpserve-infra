"""Actual isolated SQL handoffs, release receipts and retained intake recovery."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import datetime as dt
import sys
import check_dedicated_intake_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202611050003_infrastructure_service_work.sql'


def main():
 cache=f.ROOT/'.test-artifacts/service-work-database-base.json'
 original_query=f.query
 if '--reuse-base' in sys.argv:
  base=json.loads(cache.read_bytes())
  if not base['database'].startswith('jumpserve_research_ideas_test_'):raise ValueError('Isolated local baseline required.')
  for name,h in base['report']['migration_sha256'].items():
   if workflow.digest((f.ROOT/'database'/name).read_bytes())!=h:raise ValueError('Baseline migration changed; run the full regression chain.')
  f.ACTOR=base['actor'];f.report=base['report']
 else:
  previous.main();base=dict(database=f.DATABASE,actor=f.ACTOR,report=f.report)
  cache.write_text(json.dumps(base,indent=2))
 clone='jumpserve_research_ideas_test_service_'+f.uid().replace('-','')
 original_query('create database '+clone+' template '+base['database'],database='postgres')
 def query(sql,database=None,role=None):return original_query(sql,database=database or clone,role=role)
 f.query=query;f.DATABASE=clone;f.report['database']=clone
 q=f.sql_text;j=f.sql_json
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 def js(sql,role=None):return json.loads(f.query(sql,role=role) or 'null')
 def rpc(c,op,payload=None,role='service_role'):
  return js('select public.platform_service_work('+','.join([q(op),q(c['worker']),q(c['task']),q(c['token']),j(payload or {})])+')',role)
 def work(c,op,payload=None):return js('select public.platform_worker('+','.join([q(op),q(c['worker']),q(c['task']),q(c['token']),j(payload or {})])+')','service_role')
 def case(profile='assessment-evidence-v1'):
  study,root,task,token,worker,artifact,ident,blocker=[f.uid() for _ in range(8)]
  spec=dict(version='platform-service-work-v1',profile=profile,objective='Synthetic isolated service integration.',acceptance=['Verify retained fixture identity.'])
  f.query("update platform_settings set paused=false,automatic_releases=true where id;update autonomy_budget_categories set max_model_calls=-1,max_spend_cents=-1,change_reason='Local service fixture' where category in ('platform_repair','research_assessment')")
  f.query('insert into research_studies(id,title,paper_url,domain,scope) values('+q(study)+",'Synthetic service paper','https://example.org/paper.pdf','Networking','Synthetic service regression');insert into research_study_owners(study_id,owner_id) values("+q(study)+','+q(f.ACTOR)+');insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256) values('+q(study)+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'));insert into research_paper_reviews(study_id,status) values("+q(study)+",'failed');insert into research_autonomy_tasks(id,study_id,stage,status,reason,context) values("+q(root)+','+q(study)+",'intake','blocked','Synthetic PDF parser failure.',"+j(dict(intake_pool_version='warm-intake-v1'))+')')
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,status,max_reserved_cents,deadline_at,worker_id,lease_token,lease_until) select '+','.join([
   q(task),"(select user_id from platform_operators where role='owner' limit 1)",q('Synthetic service parent'),q(spec['objective']),"array['jumpserve-networks/jumpserve-back-end']",'authorization_version',q('platform_repair'),q('implementing'),'-1',"clock_timestamp()+interval '1 hour'",q(worker),q(token),"clock_timestamp()+interval '5 minutes'"])+ ' from platform_settings where id')
  f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join(map(q,[blocker,study,root,'task',root,'intake','blocked','Synthetic parser failure.',workflow.digest(b'Synthetic PDF parser failure.'),workflow.digest(root.encode())]))+');insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(task)+')')
  data=workflow.canonical(spec);sha=workflow.digest(data)
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(artifact),q(task),q('infrastructure-service-request.json'),q(sha),str(len(data)),q(task+'/'+sha),q('application/json'),"'{}'"])+')')
  return dict(study=study,root=root,task=task,token=token,worker=worker,artifact=artifact,id=ident,spec=spec)
 def request(c):return rpc(c,'request',dict(id=c['id'],spec=c['spec'],artifact_id=c['artifact']))
 def child(c,result):
  c=dict(c,task=result['implementation_task_id']);f.query("update platform_tasks set status='deploying',worker_id="+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(c['task']));return c
 def operation(c):
  op=f.uid();revision='a'*40;body=dict(repository='jumpserve-networks/jumpserve-infra',component='infrastructure',revision=revision)
  result=work(c,'begin-operation',dict(id=op,kind='deploy',request=body,request_sha256=workflow.digest(workflow.canonical(body))))
  return dict(id=op,revision=revision,sha=result['request_sha256'])
 def release(op,manifest=None,result=None,role='service_role'):
  return js('select public.platform_service_release('+','.join([q(op['id']),q(op['revision']),'null' if manifest is None else j(manifest),'null' if result is None else j(result)])+')',role)
 def manifest(c):return dict(version='platform-service-manifest-v1',request_id=c['id'],profile=c['spec']['profile'])
 def proof(c,op):return dict(passed=True,profile=c['spec']['profile'],request_id=c['id'],revision=op['revision'],scientific_completion=False,task_bound_evidence_verified=True,schema_sha256='b'*64)
 def confirm(c,op,result):
  work(c,'finish-operation',dict(id=op['id'],request_sha256=op['sha'],status='confirmed',result={'synthetic_cloud_receipt':True}))
  return work(c,'release',dict(id=f.uid(),component='infrastructure',repository='jumpserve-networks/jumpserve-infra',revision=op['revision'],status='verified',external_id=op['id'],verification=dict(passed=True,revision=op['revision']),details=dict(synthetic_cloud_receipt=True)))

 def admission():
  c=case();before=f.query('select jsonb_build_array(deadline_at,max_reserved_cents,committed_cents,repositories) from platform_tasks where id='+q(c['task']))
  with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(lambda _:request(c),range(2)))
  assert r[0]['implementation_task_id']==r[1]['implementation_task_id'];impl=child(c,r[0])
  assert js('select to_jsonb(repositories) from platform_tasks where id='+q(impl['task']))==['jumpserve-networks/jumpserve-infra']
  assert before==f.query('select jsonb_build_array(deadline_at,max_reserved_cents,committed_cents,repositories) from platform_tasks where id='+q(c['task']))
  assert f.query('select deadline_at from platform_tasks where id='+q(c['task']))==f.query('select deadline_at from platform_tasks where id='+q(impl['task']))
  context=rpc(impl,'context');assert context['implementation']['profile']==c['spec']['profile'];assert context['evidence']['assessment_id']==c['study']
  # Schema column names are diagnostic information, not private locations.
  assert all('storage_path' not in a for a in context['evidence']['artifacts'])
  assert 'owner_id' not in context['evidence'] and 'actor_id' not in context['evidence']
  assert f.query('select count(*) from platform_assessment_repair_bindings where platform_task_id='+q(impl['task']))=='1'
 f.check('service work creates one owning-infrastructure task under concurrency while retaining original scope, evidence privacy and limits',admission)

 def controls():
  for mode in ('pause','cancel','deadline','unknown','operation','token','artifact','profile'):
   c=case()
   if mode=='pause':f.query('update platform_settings set paused=true')
   elif mode=='cancel':f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
   elif mode=='deadline':f.query("update platform_tasks set deadline_at=clock_timestamp()-interval '1 second' where id="+q(c['task']))
   elif mode=='token':c['token']=f.uid()
   elif mode=='artifact':c['artifact']=f.uid()
   elif mode=='profile':c['spec']['profile']='arbitrary-sql'
   elif mode=='unknown':f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([q(f.uid()),q(c['task']),'1',q('b'*64),q(c['artifact']),q('unknown'),'100'])+')')
   else:operation(c)
   f.rejects(lambda:request(c));assert f.query('select count(*) from platform_service_work_requests where parent_task_id='+q(c['task']))=='0'
  f.query('update platform_settings set paused=false')
 f.check('pause, cancellation, deadlines, unknown calls, pending operations, wrong tokens, missing originals and unsupported profiles deny service work',controls)

 def receipts():
  c=case();impl=child(c,request(c));op=operation(impl);body=manifest(c);result=proof(c,op)
  assert release(op)['evidence']['assessment_id']==c['study']
  for invalid in (dict(body,command='arbitrary'),dict(body,request_id=f.uid())):f.rejects(lambda:release(op,invalid,result))
  f.rejects(lambda:release(op,body,dict(result,passed=False)))
  f.rejects(lambda:release(op,body,dict(result,task_bound_evidence_verified=False)))
  assert release(op,body,result)['verified'] is True
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='blocked'
  f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['task']))
  confirm(impl,op,result)
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='implementing'
  assert release(op)['verified'] is True
  assert f.query('select count(*) from platform_service_work_activations where request_id='+q(c['id']))=='1'
  assert f.query("select count(*) from platform_events where task_id="+q(c['task'])+" and kind='service-parent-resumed'")=='1'
 f.check('exact executed release proof, confirmed operation and verified source revision resume the parent once; proposals and stale receipts cannot activate',receipts)

 def family():
  c=case();impl=child(c,request(c));f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
  assert work(impl,'lease')['cancel_requested'] is True
  c=case();impl=child(c,request(c))
  f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([q(f.uid()),q(c['task']),'1',q('b'*64),q(c['artifact']),q('complete'),'100'])+')')
  f.query("update autonomy_budget_categories set max_model_calls=1,change_reason='Synthetic service category ceiling' where category='platform_repair'")
  flags=work(impl,'lease');assert flags['model_calls']==1 and flags['committed_cents']==100
  assert work(impl,'begin-run')=={'denied':'budget'}
  f.query("update autonomy_budget_categories set max_model_calls=-1,change_reason='Restore synthetic category' where category='platform_repair'")
 f.check('service children share family budgets and inherit ancestor cancellation without resetting counters or replacing provider calls',family)

 def intake():
  c=case('intake-parser-recovery-v1');impl=child(c,request(c));op=operation(impl);original,text,failure,source=[f.uid() for _ in range(4)]
  for ident,h,kind,provenance in ((original,'b'*64,'paper-original-upload',{}),(failure,'c'*64,'failed-text-extraction',{'original_artifact_id':original}),(text,'d'*64,'derived-pdf-text',{'original_artifact_id':original,'original_sha256':'b'*64})):
   f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(ident),q(c['study']),q(h),'20',q(c['study']+'/'+h),q('application/json'),j(dict(provenance,kind=kind)),'clock_timestamp()'])+')')
  row=dict(id=source,citation='Synthetic source',source_url=None,retrieved_url=None,kind='main paper',role='Synthetic parser fixture',retrieved_version='Synthetic',sha256='b'*64,byte_count=20,access_status='retrieved',review_status='retrieved-unreviewed',review_definition='No substantive review',examined='Synthetic bytes',unexamined='Scientific evidence',retrieval_attempts=[],reviewer={},findings='None',limitations='Synthetic fixture')
  f.query('select public.research_append('+','.join([q(c['study']),q(f.ACTOR),q('sources'),j(row)])+')')
  result=dict(proof(c,op),intake_source_binding='e'*64,parser_version='6.19.0',failure_verified=True,provider_calls=0,
   intake_environment_verified=True,environment_command_id=f.uid(),environment_checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),
   failure_artifact_id=failure,failure_sha256='c'*64,original_reason_sha256=workflow.digest(b'Synthetic PDF parser failure.'),source_id=source,original_artifact_id=original,text_artifact_id=text,text_sha256='d'*64)
  def health(age="clock_timestamp()",binding='e'*64):f.query('update research_intake_runtime set enabled=true,status=\'ready\',seen_at='+age+',configuration='+j(dict(gateway_verified=True,source_binding=binding))+' where id')
  health();before=f.query('select to_jsonb(w)-array[\'status\',\'updated_at\'] from research_autonomy_workflows w where study_id='+q(c['study']))
  positive='begin;select public.platform_service_release('+','.join([q(op['id']),q(op['revision']),j(manifest(c)),j(result)])+');'
  positive+='do $$begin if not exists(select 1 from research_autonomy_tasks where id='+q(c['root'])+" and status='queued' and attempts=0 and context->>'intake_pool_version'='warm-intake-v1' and context->>'text_artifact_id'="+q(text)+") then raise exception 'Original intake recovery differs';end if;"
  positive+='if (select to_jsonb(w)-array[\'status\',\'updated_at\'] from research_autonomy_workflows w where study_id='+q(c['study'])+') is distinct from '+j(json.loads(before))+" then raise exception 'Original limits or counters changed';end if;"
  positive+="if not exists(select 1 from research_paper_reviews where study_id="+q(c['study'])+" and status='preparing' and confirmed_at is null and seeds='[]'::jsonb) then raise exception 'Review scope changed';end if;end $$;rollback;"
  f.check('verified parser recovery reuses the original source, queues only missing intake work and preserves every original workflow limit and scope',lambda:f.query(positive))
  for mode in ('stale','binding','partial','unknown'):
   health()
   if mode=='stale':health("clock_timestamp()-interval '2 minutes'")
   elif mode=='binding':health(binding='f'*64)
   elif mode=='partial':f.query("update research_autonomy_tasks set context=context||'{\"last_turn_id\":\"retained\"}'::jsonb where id="+q(c['root']))
   else:
    prompt=f.query("select id from agent_prompt_versions where module_id='research-autonomy' and published_at is not null limit 1")
    f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents) values('+','.join([q(f.uid()),q(c['study']),q(c['root']),'1',q('intake'),q(prompt),q('gpt-6.1-sol'),"'{}'::jsonb",q('{}'),q(workflow.digest(b'{}')),q('unknown'),'100'])+')')
   f.rejects(lambda:release(op,manifest(c),result))
   if mode=='partial':f.query('update research_autonomy_tasks set context='+j(dict(intake_pool_version='warm-intake-v1'))+' where id='+q(c['root']))
   if mode=='unknown':
    # Original unknown rows remain immutable; no deletion forces success.
    return
  raise AssertionError('Expected the original unknown-call recovery fence.')
 f.check('parser recovery refuses stale/wrong runtime source, partial context and uncertain calls without deleting evidence',intake)

 def private():
  c=case()
  for role in ('anon','authenticated'):
   f.rejects(lambda:rpc(c,'context',role=role))
   f.rejects(lambda:f.query('select * from platform_service_work_requests',role=role))
  for role in ('anon','authenticated','service_role'):
   f.rejects(lambda:f.query('select public.platform_service_evidence('+q(c['task'])+')',role=role))
   f.rejects(lambda:f.query('select public.platform_service_work_resume()',role=role))
  f.rejects(lambda:rpc(c,'self-certify',{'passed':True}))
 f.check('service evidence remains private and lease-bound; browser reads and candidate self-certification are denied',private)
 f.report.update(passed=True,protocol='infrastructure-service-work-v1');path=f.DIRECTORY/'platform-service-work-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))


if __name__=='__main__':main()
