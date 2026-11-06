"""Actual isolated SQL: retained service refinements and captured failure proofs."""
import copy,io,json,sys,uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_service_repair_lifecycle_database as previous
import check_research_ideas_database as f
import dispatch_recovery as recovery,autonomous_repair as repair,store,workflow,siwc_protocol as wire

MIGRATIONS=('202611060002_service_refinement_evidence.sql','202611060003_captured_provider_failures.sql','202611060004_captured_failure_worker_install.sql')

def main():
 cache=f.ROOT/'.test-artifacts/provider-failure-database-base.json';original_query=f.query
 if '--reuse-base' in sys.argv:
  if cache.exists():base=json.loads(cache.read_bytes())
  else:
   reports=sorted((f.ROOT/'.test-artifacts/research-ideas/database').glob('*/service-repair-lifecycle-report.json'))
   report=json.loads(reports[-1].read_bytes());assert report['passed'] and len(report['checks'])==159
   base=dict(database=report['database'],report=report)
  for name,h in base['report']['migration_sha256'].items():assert workflow.digest((f.ROOT/'database'/name).read_bytes())==h
  f.report=base['report']
 else:
  previous.main();base=dict(database=f.DATABASE,report=f.report);cache.write_text(json.dumps(base,indent=2))
 assert base['database'].startswith('jumpserve_research_ideas_test_')
 clone='jumpserve_research_ideas_test_failures_'+f.uid().replace('-','')
 original_query('create database '+clone+' template '+base['database'],database='postgres')
 def query(sql,database=None,role=None):return original_query(sql,database=database or clone,role=role)
 f.query=query;f.DATABASE=clone;f.report.update(database=clone,passed=False,protocol='captured-provider-failures-v1')
 q=f.sql_text;j=f.sql_json
 def js(sql,role=None):return json.loads(f.query(sql,role=role) or 'null')
 f.ACTOR=f.query("select user_id from platform_operators where role='owner' order by created_at,user_id limit 1")
 prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
 before=f.query("select jsonb_build_object('calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t),'dispatches',(select jsonb_agg(to_jsonb(d) order by id) from research_model_dispatches d),'budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b))")
 for name in MIGRATIONS:
  raw=(f.ROOT/'database'/name).read_bytes();f.query(raw.decode());f.report['migration_sha256'][name]=workflow.digest(raw)
 assert before==f.query("select jsonb_build_object('calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t),'dispatches',(select jsonb_agg(to_jsonb(d) order by id) from research_model_dispatches d),'budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b))")
 f.check('forward failure and refinement migrations preserve all original calls, turns, dispatches and category limits',lambda:dict(passed=True))
 blobs={}
 def artifact(c,raw,kind,name='fixture',ident=None):
  ident=ident or f.uid();h=workflow.digest(raw);blobs[ident]=raw
  f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(ident),q(c['study_id']),q(h),str(len(raw)),q(c['study_id']+'/'+h),q('application/octet-stream'),j(dict(kind=kind,filename=name,dispatch_id=c['dispatch_id'],task_id=c['id'])),'clock_timestamp()'])+')')
  return dict(artifact_id=ident,sha256=h)
 def case(builder=False,http=200,status='failed'):
  c=dict(id=f.uid(),study_id=f.uid(),dispatch_id=f.uid(),actor_id=f.ACTOR,status='waiting')
  logical=dict(builder=dict(context={})) if builder else dict(modelId='gpt-6.1-sol',system=[dict(text='Synthetic policy')],messages=[dict(role='user',content=[dict(text='Synthetic context')])],toolConfig=dict(tools=[dict(toolSpec=dict(inputSchema=dict(json={}))) ]))
  raw=workflow.canonical(logical)
  f.query('insert into research_studies(id,title,paper_url,domain,scope) values('+q(c['study_id'])+",'Synthetic captured failure','https://example.org/failure.pdf','Software','Synthetic regression');insert into research_study_owners(study_id,owner_id) values("+q(c['study_id'])+','+q(f.ACTOR)+');insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256) values('+q(c['study_id'])+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'));insert into research_autonomy_tasks(id,study_id,stage,status,reason) values("+q(c['id'])+','+q(c['study_id'])+",'building','waiting','Synthetic retained failure')")
  f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,ended_at) values('+','.join([q(c['dispatch_id']),q(c['study_id']),q(c['id']),'1',q('building'),q(prompt),q('gpt-6.1-sol'),j(logical),q(raw.decode()),q(workflow.digest(raw)),q('failed'),'100','clock_timestamp()'])+')')
  reason='server_is_overloaded' if http==200 else 'subscription_sharing_user_unavailable'
  receipt=dict(runtime='openclaw-production-v1',model_id='gpt-6.1-sol',status=status,error_code=reason,http_status=http,provider_calls=1,provider_request_sent=True,response_received=True,provider_retries=0,paid_fallback=False)
  error=(b'data: '+workflow.canonical(dict(type='error',error=dict(code=reason)))+b'\n\n'+b'data: {"partial":') if http==200 else workflow.canonical(dict(error=dict(code=reason)))
  refs=[]
  if not builder:
   for name,data in [('logical.json',raw),('provider-request.json',workflow.canonical(wire.response_request(logical))),('provider-response.bin',error),('receipt.json',workflow.canonical(receipt))]:
    ref=artifact(c,data,'model-runtime-original',name);refs.append(dict(id=ref['artifact_id'],sha256=ref['sha256'],byte_count=len(data),name=name))
  provenance=dict(receipt,artifacts=refs)
  f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status,provenance,ended_at) values('+','.join([q(c['dispatch_id']),q(c['study_id']),q(c['id']),q('openclaw-production-v1'),q(raw.decode()),q(workflow.digest(raw)),q(status),j(provenance),'clock_timestamp()'])+')')
  c.update(dispatch=js('select to_jsonb(d) from research_model_dispatches d where id='+q(c['dispatch_id'])),receipt=receipt,error=error)
  return c
 def rows(c,kind,**filters):
  table={'builder_calls':'research_builder_calls','builder_call_reconciliations':'research_builder_call_reconciliations','model_reconciliations':'research_model_reconciliations'}[kind]
  where=['study_id='+q(c['study_id'])]
  for name,value in filters.items():
   if name in ('order','limit'):continue
   assert name in ('dispatch_id','call_id') and value.startswith('eq.');where.append(name+'='+q(value[3:]))
  return js('select coalesce(jsonb_agg(to_jsonb(x)),\'[]\') from '+table+' x where '+' and '.join(where))
 def original(c,ref,maximum=150000):
  raw=blobs[ref.get('artifact_id') or ref['id']];assert len(raw)<=maximum and workflow.digest(raw)==ref['sha256'];return raw
 def rpc(name,payload,role='service_role'):
  assert name in ('research_builder_call_reconcile','research_controller_dispatch_reconcile','research_model_reconcile')
  ident=payload.get('p_call') or payload['p_dispatch']
  return js('select public.'+name+'('+','.join([q(ident),q(payload['p_artifact']),q(payload['p_sha256']),j(payload['p_proof'])])+')',role)
 def native(c,status='failed'):
  req=artifact(c,workflow.canonical(dict(model='gpt-6.1-sol',store=False,stream=True,tools=[dict(type='function',name='read')])),'builder-native-request')
  response=artifact(c,c['error'],'builder-native-response');ident=f.uid()
  f.query('insert into research_builder_calls(id,study_id,task_id,dispatch_id,number,prompt_version_id,model_id,request_artifact_id,request_sha256,request_bytes,status,reserved_cents,response_artifact_id,response_sha256,response_received,http_status,reason,ended_at) values('+','.join([q(ident),q(c['study_id']),q(c['id']),q(c['dispatch_id']),'1',q(prompt),q('gpt-6.1-sol'),q(req['artifact_id']),q(req['sha256']),str(len(blobs[req['artifact_id']])),q(status),'100',q(response['artifact_id']),q(response['sha256']),'true',str(c['receipt']['http_status']),q(c['receipt']['error_code']),'clock_timestamp()'])+')')
  return ident
 def snapshot(c):return f.query("select jsonb_build_object('task',(select to_jsonb(t) from research_autonomy_tasks t where id="+q(c['id'])+"),'workflow',(select to_jsonb(w) from research_autonomy_workflows w where study_id="+q(c['study_id'])+"),'turn',(select to_jsonb(t) from research_autonomy_turns t where id="+q(c['dispatch_id'])+"),'dispatch',(select to_jsonb(d) from research_model_dispatches d where id="+q(c['dispatch_id'])+"),'calls',(select jsonb_agg(to_jsonb(x) order by id) from research_builder_calls x where task_id="+q(c['id'])+'))')
 def native_failures():
  for http in (200,503):
   c=case(True,http);ident=native(c);before=snapshot(c)
   with patch.object(repair,'rows',side_effect=rows),patch.object(repair,'original',side_effect=original),patch.object(store,'rpc',side_effect=rpc):
    recovery.reconcile_native_calls(c,c['dispatch'],f.DIRECTORY,lambda name,raw,kind:artifact(c,raw,kind,name))
    calls=recovery.ledger(c,c['dispatch'],original,rows)
   assert calls[0]['status']=='failed' and snapshot(c)==before
   checkpoint=artifact(c,b'synthetic retained checkpoint','builder-reconciled-workspace')
   proof=dict(version=recovery.VERSION,dispatch_id=c['dispatch_id'],request_sha256=c['dispatch']['request_sha256'],original_status='failed',container_cleanup='stopped',calls=calls,checkpoint=checkpoint)
   ref=artifact(c,workflow.canonical(proof),'builder-dispatch-reconciliation')
   rpc('research_model_reconcile',dict(p_dispatch=c['dispatch_id'],p_artifact=ref['artifact_id'],p_sha256=ref['sha256'],p_proof=proof))
   assert snapshot(c)==before
 f.check('captured HTTP and framed stream failures reconcile native ledgers and dispatch cleanup without changing originals or usage',native_failures)
 def controller():
  c=case();before=snapshot(c);proof=recovery.controller_failure(c,c['dispatch'],c['receipt'],original,rows);assert proof
  ref=artifact(c,workflow.canonical(proof),'controller-dispatch-reconciliation')
  payload=dict(p_dispatch=c['dispatch_id'],p_artifact=ref['artifact_id'],p_sha256=ref['sha256'],p_proof=proof)
  with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(lambda _:rpc('research_controller_dispatch_reconcile',payload),range(2)))
  assert result[0]==result[1] and snapshot(c)==before
  assert f.query('select public.research_controller_dispatch_accounted(d) from research_model_dispatches d where id='+q(c['dispatch_id']))=='t'
  for role in ('anon','authenticated'):f.rejects(lambda role=role:rpc('research_controller_dispatch_reconcile',payload,role))
  invalid=copy.deepcopy(payload);invalid['p_proof']['failure']['response_forwarded_to_agent']=True
  f.rejects(lambda:rpc('research_controller_dispatch_reconcile',invalid));assert snapshot(c)==before
 f.check('data-only controller failures close once under concurrency while accepted decisions, original rows and browser denial remain intact',controller)
 def unknown():
  c=case(True,status='unknown');ident=native(c,'unknown');before=snapshot(c)
  payload=dict(p_call=ident,p_artifact=f.uid(),p_sha256='a'*64,p_proof=dict(version=recovery.FAILURE_VERSION))
  f.rejects(lambda:rpc('research_builder_call_reconcile',payload));assert snapshot(c)==before
  assert f.query('select public.research_builder_unresolved('+q(c['id'])+')')=='t'
 f.check('unknown native outcomes cannot be converted to failures or resumed by this adapter',unknown)
 def platform(c):
  task,token,worker,blocker=[f.uid() for _ in range(4)]
  f.query('update platform_settings set paused=false,automatic_releases=true where id')
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,status,max_reserved_cents,deadline_at,worker_id,lease_token,lease_until) select '+','.join([q(task),q(f.ACTOR),q('Synthetic service refinement'),q('Synthetic runtime observation'),"array['jumpserve-networks/jumpserve-back-end']",'authorization_version',q('platform_repair'),q('implementing'),'-1',"clock_timestamp()+interval '1 hour'",q(worker),q(token),"clock_timestamp()+interval '5 minutes'"])+ ' from platform_settings where id')
  f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join(map(q,[blocker,c['study_id'],c['id'],'task',c['id'],'building','waiting','Synthetic missing observation.','a'*64,workflow.digest(blocker.encode())]))+');insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(task)+')')
  return dict(task=task,token=token,worker=worker)
 def service_request(p,spec,ident=None):
  raw=workflow.canonical(spec);h=workflow.digest(raw);artifact_id=f.uid()
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(artifact_id),q(p['task']),q('infrastructure-service-request.json'),q(h),str(len(raw)),q(p['task']+'/'+h),q('application/json'),"'{}'"])+')')
  payload=dict(id=ident or f.uid(),spec=spec,artifact_id=artifact_id)
  sql='select public.platform_service_work('+','.join([q('request'),q(p['worker']),q(p['task']),q(p['token']),j(payload)])+')'
  return sql,payload
 context={}
 def refinements():
  c=case(True,status='unknown');native(c,'unknown');p=platform(c);spec=dict(version='platform-service-work-v1',profile='assessment-evidence-v1',objective='Read recorded schema.',acceptance=['Verify task scope.'])
  sql,_=service_request(p,spec);first=js(sql,'service_role');original_request=f.query('select to_jsonb(q) from platform_service_work_requests q where id='+q(first['id']))
  spec=dict(spec,objective='Inspect original worker spool and deliver the installed runtime source.')
  sql,payload=service_request(p,spec)
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:js(sql,'service_role'),range(2)))
  assert results[0]==results[1] and results[0]['requires_implementation'] is True and results[0]['id']==first['id']
  assert original_request==f.query('select to_jsonb(q) from platform_service_work_requests q where id='+q(first['id']))
  assert f.query('select count(*) from platform_service_work_refinements where parent_task_id='+q(p['task']))=='1'
  assert f.query('select count(*) from platform_service_work_requests where parent_task_id='+q(p['task']))=='1'
  for role in ('anon','authenticated'):f.rejects(lambda role=role:js(sql,role))
  context.update(c=c,p=p,refinement=payload['id'])
 f.check('changed service requirements are immutable refinements with one child and no HTTP 400 or duplicate activation loop',refinements)
 def observations():
  c=context['c'];before=snapshot(c)
  cursor=str(uuid.UUID(int=uuid.UUID(c['dispatch_id']).int-1))
  candidates=js('select coalesce(jsonb_agg(x),\'[]\') from public.research_model_reconciliation_candidates('+q(cursor)+') x','service_role')
  assert any(d.get('runtime_observation_request_id')==context['refinement'] for d in candidates)
  # An owner-authored provenance label alone cannot enter the trusted view.
  forged=artifact(c,b'forged source','worker-installed-source-v1','autonomy.py')
  assert not js('select public.platform_service_evidence('+q(context['p']['task'])+')')['runtime_observations']
  sources=[]
  for name in ('autonomy_read_progress.py','autonomy.py','autonomy_model.py','dispatch_recovery.py','siwc_protocol.py'):
   raw=('Synthetic passive source '+name).encode();ref=artifact(c,raw,'worker-installed-source-v1',name)
   sources.append(dict(filename=name,sha256=ref['sha256'],byte_count=len(raw),artifact=ref))
  proof=dict(version='worker-runtime-diagnostics-v1',study_id=c['study_id'],task_id=c['id'],dispatch_id=c['dispatch_id'],request_sha256=c['dispatch']['request_sha256'],runtime_source_binding='a'*64,sources=sources,
   calls=[],worker_pid=123,observed_at='2026-11-06T00:00:00Z',observation_request_id=context['refinement'],provider_calls=0,reconciliation_performed=False,cleanup_performed=False,scientific_completion=False)
  ref=artifact(c,workflow.canonical(proof),'worker-runtime-diagnostics-v1');payload=dict(p_dispatch=c['dispatch_id'],p_artifact=ref['artifact_id'],p_sha256=ref['sha256'],p_proof=proof)
  for role in ('anon','authenticated'):f.rejects(lambda role=role:rpc('research_model_reconcile',payload,role))
  result=rpc('research_model_reconcile',payload);assert result==rpc('research_model_reconcile',payload)
  view=js('select public.platform_service_evidence('+q(context['p']['task'])+')')['runtime_observations']
  assert {ref['artifact_id'],*[s['artifact']['artifact_id'] for s in sources]}=={r['id'] for r in view}
  assert forged['artifact_id'] not in {r['id'] for r in view} and snapshot(c)==before
  assert f.query('select count(*) from research_model_reconciliations where dispatch_id='+q(c['dispatch_id']))=='0'
  assert f.query('select public.research_builder_unresolved('+q(c['id'])+')')=='t'
  candidates=js('select coalesce(jsonb_agg(x),\'[]\') from public.research_model_reconciliation_candidates('+q(cursor)+') x','service_role')
  assert not any(d.get('runtime_observation_request_id')==context['refinement'] for d in candidates)
  f.rejects(lambda:f.query('update research_runtime_observations set proof=\'{}\' where artifact_id='+q(ref['artifact_id'])))
 f.check('worker-only observations deliver exact task-bound sources while forged provenance stays hidden and unknown calls remain fenced',observations)
 def privacy():
  for table in ('platform_service_work_refinements','research_runtime_observations'):
   for role in ('anon','authenticated'):f.rejects(lambda role=role,table=table:f.query('select * from '+table,role=role))
  for name in ('research_builder_call_reconcile_before_failures_v1(uuid,uuid,text,jsonb)','research_model_reconcile_before_diagnostics_v1(uuid,uuid,text,jsonb)','research_model_reconciliation_candidates_before_observations_v1(uuid)'):
   for role in ('anon','authenticated','service_role'):assert f.query('select has_function_privilege('+q(role)+','+q('public.'+name)+",'execute')")=='f'
 f.check('new records remain immutable and private; service-only entry points cannot bypass their former frozen adapters',privacy)
 def worker_install():
  c=case();p=platform(c);operation,command=f.uid(),f.uid();revision='b'*40
  manifest=dict(source_revision=revision,files={'dispatch_recovery.py':'c'*64,'policies/autonomous-repair-release-v1.json':'d'*64},source_overlay=None)
  scope=dict(qualification_profile='captured-provider-failures-v1',source_binding='a'*64,files={'dispatch_recovery.py':'c'*64},source_overlay=None)
  checkpoint=dict(research_runtime=dict(scope=scope,certificate=dict(passed=True),approval_sha256='d'*64))
  body=dict(component='research-runtime',repository='jumpserve-networks/jumpserve-back-end',revision=revision,pin_revision='e'*40)
  f.query('update platform_tasks set checkpoint='+j(checkpoint)+' where id='+q(p['task'])+';insert into platform_operations(id,task_id,kind,request_sha256,request) values('+','.join([q(operation),q(p['task']),q('deploy'),q(workflow.digest(workflow.canonical(body))),j(body)])+')')
  proof=dict(passed=True,revision=revision,command_id=command,source_binding='a'*64,installed_files_verified=True,spool_unchanged=True,credentials_unchanged=True,provider_calls=0,scientific_completion=False)
  original=f.query("select jsonb_build_object('tasks',(select jsonb_agg(to_jsonb(x) order by id) from research_autonomy_tasks x),'dispatches',(select jsonb_agg(to_jsonb(x) order by id) from research_model_dispatches x),'calls',(select jsonb_agg(to_jsonb(x) order by id) from research_builder_calls x))")
  # Drain only synthetic peer fixtures inside a transaction, then roll every
  # fixture change back. This is not a production force-drain or outcome edit.
  sql="""begin;
  update research_autonomy_tasks set lease_until=null where status='running';
  update research_model_dispatches set status='failed',ended_at=clock_timestamp() where status in ('queued','running');
  update research_builder_calls set status='unknown',ended_at=clock_timestamp() where status='running';
  insert into research_runtime_maintenance_releases(hold_id,reason) select h.id,'Synthetic isolated peer drain' from research_runtime_maintenance_holds h where not exists(select 1 from research_runtime_maintenance_releases r where r.hold_id=h.id);
  do $test$ declare a jsonb;b jsonb;begin
   insert into public.research_runtime_maintenance_holds(id,task_id,source_binding,reason,expires_at)
    values(md5(OP::text||':existing-qualified-handoff')::uuid,TASK,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','Same task and qualified source handoff',clock_timestamp()+interval '20 minutes');
   insert into public.research_runtime_maintenance_holds(id,reason,expires_at)
    values(md5(OP::text||':foreign-handoff')::uuid,'Unrelated active maintenance',clock_timestamp()+interval '20 minutes');
   a=public.research_runtime_worker_install(OP,REV,null);
   if a->'wait_for_safe_boundary' is distinct from 'true'::jsonb then raise exception 'Unrelated handoff was bypassed';end if;
   insert into public.research_runtime_maintenance_releases(hold_id,reason)
    values(md5(OP::text||':foreign-handoff')::uuid,'Synthetic foreign maintenance completed');
   a=public.research_runtime_worker_install(OP,REV,null);
   if a->'dispatch_allowed' is distinct from 'true'::jsonb then raise exception 'Initial worker admission failed';end if;
   b=public.research_runtime_worker_install(OP,REV,null);
   if b->'dispatch_allowed' is distinct from 'false'::jsonb then raise exception 'Repeated dispatch admitted';end if;
   update platform_tasks set cancel_requested=true where id=TASK;
   if not public.research_runtime_maintenance_active() then raise exception 'Cancellation dropped an admitted worker fence';end if;
   perform public.research_runtime_worker_install(OP,REV,CMD);
   b=public.research_runtime_worker_install(OP,REV,null);
   if b->>'command_id' is distinct from CMD::text then raise exception 'Original command not retained';end if;
   perform public.research_runtime_worker_activate(OP,MANIFEST,PROOF);
   perform public.research_runtime_worker_activate(OP,MANIFEST,PROOF);
   if not exists(select 1 from research_runtime_maintenance_releases where hold_id=OP) then raise exception 'Verified readback did not release hold';end if;
   if (select count(*) from research_runtime_worker_activations where operation_id=OP)<>1 then raise exception 'Duplicate activation';end if;
  end $test$;rollback;""".replace('MANIFEST',j(manifest)).replace('PROOF',j(proof)).replace('TASK',q(p['task'])).replace('CMD',q(command)+'::uuid').replace('REV',q(revision)).replace('OP',q(operation)+'::uuid')
  f.query(sql)
  assert original==f.query("select jsonb_build_object('tasks',(select jsonb_agg(to_jsonb(x) order by id) from research_autonomy_tasks x),'dispatches',(select jsonb_agg(to_jsonb(x) order by id) from research_model_dispatches x),'calls',(select jsonb_agg(to_jsonb(x) order by id) from research_builder_calls x))")
 f.check('worker installation admits one command, preserves cancellation fencing and releases its bounded hold only after exact readback',worker_install)
 def worker_controls():
  for table in ('research_runtime_worker_install_intents','research_runtime_worker_install_receipts','research_runtime_worker_activations'):
   for role in ('anon','authenticated'):f.rejects(lambda role=role,table=table:f.query('select * from '+table,role=role))
  for signature in ('research_runtime_worker_install(uuid,text,uuid)','research_runtime_worker_activate(uuid,jsonb,jsonb)'):
   for role in ('anon','authenticated'):assert f.query('select has_function_privilege('+q(role)+','+q('public.'+signature)+",'execute')")=='f'
  c=case();p=platform(c);operation=f.uid();revision='b'*40;body=dict(component='research-runtime',repository='jumpserve-networks/jumpserve-back-end',revision=revision)
  f.query('insert into platform_operations(id,task_id,kind,request_sha256,request) values('+','.join([q(operation),q(p['task']),q('deploy'),q('a'*64),j(body)])+')')
  f.rejects(lambda:f.query('select research_runtime_worker_install('+q(operation)+','+q(revision)+',null)',role='service_role'))
  assert f.query('select count(*) from research_runtime_worker_install_intents where operation_id='+q(operation))=='0'
 f.check('unqualified worker installs, browser callers and private installer records retain their original access boundaries',worker_controls)
 f.report['passed']=True;path=f.DIRECTORY/'captured-provider-failures-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))

if __name__=='__main__':
 try:main()
 except Exception as error:
  f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'captured-provider-failures-failed.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
