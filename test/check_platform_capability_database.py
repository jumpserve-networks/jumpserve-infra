"""Real local capability admission and activation; synthetic cloud receipts only."""
from concurrent.futures import ThreadPoolExecutor
import json
import check_platform_slack_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202611040003_supervisor_capabilities.sql'


def main():
 previous.main();q=f.sql_text
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode())
 f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 def js(sql,role=None):return json.loads(f.query(sql,role=role) or 'null')
 def operation(c,op,payload=None,role='service_role'):
  return js('select public.platform_capability_worker('+','.join([q(op),q(c['worker']),q(c['task']),q(c['token']),f.sql_json(payload or {})])+')',role)
 def worker(c,op,payload=None):
  return js('select public.platform_worker('+','.join([q(op),q(c['worker']),q(c['task']),q(c['token']),f.sql_json(payload or {})])+')','service_role')
 def case(name='json-count'):
  task,token,worker_id,artifact,ident=[f.uid() for _ in range(5)]
  spec=dict(version='platform-capability-request-v1',id=name,minimum_revision=1,
   objective='Synthetic local tool pack fixture; no cloud or provider invocation.',acceptance=['Count actual fixture records.'])
  data=workflow.canonical(spec);sha=workflow.digest(data)
  f.query('update platform_settings set paused=false,automatic_releases=true where id')
  f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,status,max_reserved_cents,deadline_at,worker_id,lease_token,lease_until) select '+
   ','.join([q(task),"(select user_id from platform_operators where role='owner' limit 1)",q('Synthetic capability parent'),q(spec['objective']),
    "array['jumpserve-networks/jumpserve-front-end']",'authorization_version',q('platform_manual'),q('implementing'),'-1',"clock_timestamp()+interval '1 hour'",q(worker_id),q(token),"clock_timestamp()+interval '5 minutes'"])+
   ' from platform_settings where id')
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([
   q(artifact),q(task),q('capability-request.json'),q(sha),str(len(data)),q(task+'/'+sha),q('application/json'),"'{}'"])+')')
  return dict(task=task,token=token,worker=worker_id,id=ident,artifact=artifact,spec=spec)
 def request(c,**changes):return operation(c,'request',dict(id=c['id'],spec=c['spec'],artifact_id=c['artifact'])|changes)
 def child(c,result):
  value=dict(c,task=result['implementation_task_id'])
  f.query("update platform_tasks set status='implementing',worker_id="+q(c['worker'])+',lease_token='+q(c['token'])+",lease_until=clock_timestamp()+interval '5 minutes' where id="+q(value['task']))
  return value
 def release(c,revision='c'*40,module_sha='d'*64):
  op,release_id,activation=[f.uid() for _ in range(3)]
  module='capability_'+c['spec']['id'].replace('-','_')+'.py'
  body=dict(component='supervisor-runtime',repository='jumpserve-networks/jumpserve-back-end',revision=revision)
  manifest=dict(version='platform-supervisor-self-repair-v1',files={module:module_sha},source_revision=revision)
  f.query('insert into platform_operations(id,task_id,kind,request_sha256,request,status) values('+','.join([
   q(op),q(c['task']),q('deploy'),q(workflow.digest(workflow.canonical(body))),f.sql_json(body),q('confirmed')])+')')
  f.query('insert into platform_releases(id,task_id,component,repository,revision,status,external_id) values('+','.join([
   q(release_id),q(c['task']),q('supervisor-runtime'),q(body['repository']),q(revision),q('verified'),q(op)])+')')
  f.query('insert into platform_supervisor_activations(id,operation_id,source_revision,bundle_sha256,manifest,verification) values('+','.join([
   q(activation),q(op),q(revision),q('e'*64),f.sql_json(manifest),f.sql_json(dict(passed=True,installed_files_verified=True))])+')')
  return dict(op=op,release=release_id,activation=activation,payload=dict(request_id=c['id'],module_sha256=module_sha,revision=1,source_revision=revision))

 def admission():
  c=case();before=js('select jsonb_build_array(deadline_at,committed_cents,max_reserved_cents,repositories) from platform_tasks where id='+q(c['task']))
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:request(c),range(2)))
  assert results[0]['implementation_task_id']==results[1]['implementation_task_id']
  assert f.query('select count(*) from platform_capability_requests where parent_task_id='+q(c['task']))=='1'
  assert before==js('select jsonb_build_array(deadline_at,committed_cents,max_reserved_cents,repositories) from platform_tasks where id='+q(c['task']))
  detail=js('select to_jsonb(t) from platform_tasks t where id='+q(results[0]['implementation_task_id']))
  assert detail['deadline_at']==before[0] and detail['repositories']==['jumpserve-networks/jumpserve-back-end']
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='blocked'
  context=operation(child(c,results[0]),'context')
  assert context['spec']==c['spec'] and context['requires_further_owner_approval'] is False
  f.rejects(lambda:request(c,spec=dict(c['spec'],objective='Changed request')))
  nested=child(c,results[0]);nested['id']=f.uid();nested['artifact']=f.uid()
  content=workflow.canonical(nested['spec']);sha=workflow.digest(content)
  f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([
   q(nested['artifact']),q(nested['task']),q('capability-request.json'),q(sha),str(len(content)),q(nested['task']+'/'+sha),q('application/json'),"'{}'"])+')')
  f.rejects(lambda:request(nested))
  assert f.query('select count(*) from platform_capability_requests where parent_task_id='+q(nested['task']))=='0'
 f.check('capability requests create one linked implementation under concurrency without resetting parent limits or scope',admission)

 def accounting():
  c=case('family-tool');impl=child(c,request(c));sha=workflow.digest(workflow.canonical(c['spec']))
  f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([
   q(f.uid()),q(c['task']),'1',q(sha),q(c['artifact']),q('complete'),'100'])+');update platform_tasks set committed_cents=100 where id='+q(c['task']))
  f.query("update autonomy_budget_categories set max_model_calls=1,change_reason='Synthetic capability ceiling' where category='platform_manual'")
  flags=worker(impl,'lease');assert flags['model_calls']==1 and flags['committed_cents']==100
  assert worker(impl,'begin-run')=={'denied':'budget'}
  assert f.query('select committed_cents from platform_tasks where id='+q(impl['task']))=='0'
  f.query("update autonomy_budget_categories set max_model_calls=-1,change_reason='Restore synthetic unlimited calls' where category='platform_manual'")
 f.check('capability work shares original family reservations and finite call ceilings',accounting)

 def controls():
  for kind in ('pause','cancel','deadline','unknown','operation','token','evidence'):
   c=case('stopped-tool')
   if kind=='pause':f.query('update platform_settings set paused=true where id')
   elif kind=='cancel':f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
   elif kind=='deadline':f.query("update platform_tasks set deadline_at=clock_timestamp()-interval '1 minute' where id="+q(c['task']))
   elif kind=='token':c['token']=f.uid()
   elif kind=='evidence':c['artifact']=f.uid()
   elif kind=='unknown':
    f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([
     q(f.uid()),q(c['task']),'1',q(workflow.digest(workflow.canonical(c['spec']))),q(c['artifact']),q('unknown'),'100'])+')')
   else:
    f.query('insert into platform_operations(id,task_id,kind,request_sha256,request,status) values('+','.join([
     q(f.uid()),q(c['task']),q('deploy'),q('a'*64),"'{}'",q('unknown')])+')')
   f.rejects(lambda:request(c))
   assert f.query('select count(*) from platform_capability_requests where parent_task_id='+q(c['task']))=='0'
  f.query('update platform_settings set paused=false where id')
  c=case('cancel-chain');impl=child(c,request(c))
  f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
  assert worker(impl,'lease')['cancel_requested'] is True
 f.check('controls and unresolved original calls or effects fence new capability work and parent cancellation reaches children',controls)

 def activation():
  c=case('activated-tool');impl=child(c,request(c))
  payload=dict(request_id=c['id'],module_sha256='d'*64,revision=1,source_revision='c'*40)
  f.rejects(lambda:operation(impl,'activate',payload))
  proof=release(impl);f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['task']))
  f.query("update platform_releases set status='pending' where id="+q(proof['release']))
  f.rejects(lambda:operation(impl,'activate',payload))
  f.query("update platform_releases set status='verified' where id="+q(proof['release']))
  f.rejects(lambda:operation(impl,'activate',dict(payload,module_sha256='0'*64)))
  result=operation(impl,'activate',payload)
  assert result['available'] is True and result['parent_resumed'] is True
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='implementing'
  assert operation(impl,'activate',payload)['replayed'] is True
  assert f.query('select count(*) from platform_capability_activations where request_id='+q(c['id']))=='1'
  f.rejects(lambda:f.query('delete from platform_capability_activations where request_id='+q(c['id'])))
 f.check('only exact installed source and its verified release activate a capability and resume its parent idempotently',activation)

 def delayed_resume():
  c=case('paused-activation');impl=child(c,request(c));proof=release(impl,revision='f'*40)
  f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['task'])+';update platform_settings set paused=true where id')
  assert operation(impl,'activate',proof['payload'])['available'] is True
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='blocked'
  f.query('update platform_settings set paused=false where id')
  policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
  worker(impl,'maintenance',dict(policy_sha256=policy))
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='implementing'
  f.query("update platform_tasks set status='blocked',reason='Unrelated later blocker' where id="+q(c['task']))
  worker(impl,'maintenance',dict(policy_sha256=policy))
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='blocked'
 f.check('installed receipts survive pause and maintenance wakes eligible parents once after pause clears',delayed_resume)

 def unresolved_parent():
  c=case('uncertain-activation');impl=child(c,request(c));proof=release(impl,revision='1'*40)
  run=f.uid();sha=workflow.digest(workflow.canonical(c['spec']))
  f.query('insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values('+','.join([
   q(run),q(c['task']),'1',q(sha),q(c['artifact']),q('unknown'),'100'])+');update platform_tasks set lease_token=null,lease_until=null where id='+q(c['task']))
  before=f.query('select to_jsonb(r) from platform_runs r where id='+q(run))
  assert operation(impl,'activate',proof['payload'])['available'] is True
  assert f.query('select status from platform_tasks where id='+q(c['task']))=='blocked'
  assert f.query('select to_jsonb(r) from platform_runs r where id='+q(run))==before
 f.check('an available capability never clears or resumes a parent with an unresolved original provider call',unresolved_parent)

 def private():
  c=case('private-tool')
  for role in ('anon','authenticated'):
   f.rejects(lambda:operation(c,'context',role=role))
   f.rejects(lambda:f.query('select * from platform_capability_requests',role=role))
  for role in ('anon','authenticated','service_role'):
   f.rejects(lambda:f.query('select public.platform_capability_resume()',role=role))
   f.rejects(lambda:f.query('select * from public.platform_capability_ancestors('+q(c['task'])+')',role=role))
  f.rejects(lambda:operation(c,'self-certify',{'passed':True}))
 f.check('private capability records and lease-checked operations deny browser access and self-certification',private)

 f.report.update(passed=True,protocol='platform-capability-acquisition-v1')
 path=f.DIRECTORY/'platform-capability-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))


if __name__=='__main__':main()
