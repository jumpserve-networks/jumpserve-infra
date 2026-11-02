"""Native failure reconciliation and fair scheduling in an isolated loopback DB.

All existing database regressions run first. Fixtures never contact providers,
AWS, Storage or production. Original unknown rows and their reservations stay
immutable; fixture clocks/leases are controlled only inside this disposable DB.
"""
import copy,json
from concurrent.futures import ThreadPoolExecutor
import check_incident_closure_database as previous
import check_research_ideas_database as f
import model_dispatch as dispatch
import workflow

MIGRATION='202611020001_platform_reconciliation_progress.sql'
VERSION='platform-native-http-reconciliation-v1'


def main():
    previous.main();q=f.sql_text;js=lambda sql,role=None:json.loads(f.query(sql,role=role) or 'null')
    def expect(value):
        if not value:raise AssertionError('Native reconciliation/scheduling invariant failed')
    def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
    before=f.query("select jsonb_build_object('tasks',(select jsonb_agg(to_jsonb(t) order by id) from platform_tasks t),'runs',(select jsonb_agg(to_jsonb(t) order by id) from platform_runs t),'workflows',(select jsonb_agg(to_jsonb(t) order by study_id) from research_autonomy_workflows t),'budgets',(select jsonb_agg(to_jsonb(t) order by category) from autonomy_budget_categories t))")
    raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
    after=f.query("select jsonb_build_object('tasks',(select jsonb_agg(to_jsonb(t) order by id) from platform_tasks t),'runs',(select jsonb_agg(to_jsonb(t) order by id) from platform_runs t),'workflows',(select jsonb_agg(to_jsonb(t) order by study_id) from research_autonomy_workflows t),'budgets',(select jsonb_agg(to_jsonb(t) order by category) from autonomy_budget_categories t))")
    check('migration preserves every task original model outcome workflow deadline and budget',lambda:expect(before==after))
    worker=f.uid();policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
    def rpc(op,task=None,token=None,payload=None,role='service_role'):
        return js('select public.platform_worker('+','.join([q(op),q(worker),q(task)+'::uuid' if task else 'null',q(token)+'::uuid' if token else 'null',f.sql_json(payload or {})])+')',role)
    def task(status='reconciling',leased=True,expired=False):
        ident,token=f.uid(),f.uid()
        f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,committed_cents,deadline_at,worker_id,lease_token,lease_until) select '+','.join([q(ident),"(select user_id from platform_operators where role='owner' limit 1)",q('Synthetic isolated call recovery'),q(__doc__),"array['jumpserve-networks/jumpserve-back-end']",'authorization_version',q(status),'-1','100',"clock_timestamp()+interval '-1 hour'" if expired else "clock_timestamp()+interval '1 hour'",q(worker),q(token) if leased else 'null',"clock_timestamp()+interval '5 minutes'" if leased else 'null'])+' from platform_settings where id')
        return ident,token
    def artifact(ident,name,raw,provenance=None):
        key=f.uid();h=workflow.digest(raw)
        f.query('insert into platform_artifacts(id,task_id,name,sha256,byte_count,storage_path,media_type,provenance) values('+','.join([q(key),q(ident),q(name),q(h),str(len(raw)),q(ident+'/'+h),q('application/json'),f.sql_json(provenance or {})])+')')
        return dict(artifact_id=key,sha256=h,byte_count=len(raw))
    def case(expired=False):
        ident,token=task(expired=expired);run=f.uid()
        request=workflow.canonical(dict(model='gpt-6.1-sol',store=False,stream=True,tools=[dict(type='function',name='exec')]))
        response=b'Service Unavailable\n';request_ref=artifact(ident,'request-'+run,request);response_ref=artifact(ident,'response-'+run,response)
        record=dict(id=run,task_id=ident,status='unknown',reason='Provider HTTP 503.',request_sha256=request_ref['sha256'])
        receipt=dict(id=run,status='unknown',request_sha256=request_ref['sha256'],response_sha256=response_ref['sha256'],usage=None,reason=record['reason'],http_status=503)
        receipt_ref=artifact(ident,'receipt-'+run,workflow.canonical(receipt),dict(kind='platform-native-original-receipt-v1',run_id=run,request_sha256=request_ref['sha256']))
        f.query("insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,response_artifact_id,status,reserved_cents,reason,created_at,ended_at) values("+','.join([q(run),q(ident),'1',q(request_ref['sha256']),q(request_ref['artifact_id']),q(response_ref['artifact_id']),q('unknown'),'100',q(record['reason']),"clock_timestamp()-interval '13 hours'","clock_timestamp()-interval '13 hours'"])+')')
        # Synthetic certificate exercises the real SQL boundary. Backend bridge
        # and original-byte validation have their own supervisor regressions;
        # CI must not depend on an unpinned sibling checkout for this fixture.
        proof=dict(version=VERSION,transport='buffered-native-function-only-v1',run_id=run,task_id=ident,
            request_sha256=request_ref['sha256'],response_sha256=response_ref['sha256'],http_status=503,
            status='failed',original_status='unknown',response_forwarded_to_agent=False,tool_calls_executed_from_response=0,
            provider_calls=1,provider_processing_unknown=True,measured_charges_usd=None,provider_replay=False,scientific_completion=False,
            references=dict(request=request_ref,response=response_ref,receipt=receipt_ref))
        return dict(task=ident,token=token,run=run,proof=proof)
    def certificate(c,proof=None):
        proof=copy.deepcopy(c['proof'] if proof is None else proof)
        ref=artifact(c['task'],'certificate-'+f.uid(),workflow.canonical(proof),dict(kind=VERSION,run_id=c['run'],request_sha256=proof['request_sha256'],proof=proof))
        return dict(id=c['run'],artifact_id=ref['artifact_id'],proof=proof)
    def old(c):return f.query('select to_jsonb(r) from platform_runs r where id='+q(c['run']))
    def limits(c):return f.query('select jsonb_build_array(committed_cents,max_reserved_cents,deadline_at,cancel_requested) from platform_tasks where id='+q(c['task']))
    def reconcile(c,payload=None,**kwargs):return rpc('reconcile-http-error',c['task'],c['token'],payload or certificate(c),**kwargs)

    def valid():
        c=case(expired=True);payload=certificate(c);original=old(c);resources=limits(c)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:reconcile(c,payload),range(2)))
        expect(all(r['reconciled'] and r['original_status']=='unknown' and r['supplemental_outcome']=='failed' for r in results))
        expect(old(c)==original and limits(c)==resources)
        expect(f.query('select count(*) from platform_run_reconciliations where run_id='+q(c['run']))=='1')
        expect(f.query("select count(*) from platform_events where task_id="+q(c['task'])+" and kind='model-http-error-reconciled'")=='1')
        # The reconciliation clears no task deadline or cancellation gate.
        denied=rpc('begin-run',c['task'],c['token'],dict(id=f.uid(),request_sha256=c['proof']['request_sha256'],request_artifact_id=c['proof']['references']['request']['artifact_id']))
        expect(denied['denied']=='paused-cancelled-or-deadline')
    check('concurrent proof append is idempotent original unknown bytes and reservations remain unchanged and expired work cannot restart',valid)

    def invalid():
        mutations=[('http_status',200),('http_status',None),('request_sha256','0'*64),('response_sha256','0'*64),('status','complete'),('response_forwarded_to_agent',True),('tool_calls_executed_from_response',1),('provider_processing_unknown',False),('provider_replay',True),('measured_charges_usd',0),('scientific_completion',True),('task_id',f.uid())]
        for field,value in mutations:
            c=case();proof=copy.deepcopy(c['proof']);proof[field]=value;before=old(c)
            f.rejects(lambda:reconcile(c,certificate(c,proof)));expect(old(c)==before)
            expect(f.query('select count(*) from platform_run_reconciliations where run_id='+q(c['run']))=='0')
        c=case();payload=certificate(c);payload['proof']['references']['receipt']['artifact_id']=c['proof']['references']['request']['artifact_id']
        f.rejects(lambda:reconcile(c,payload))
        c=case();payload=certificate(c);payload['artifact_id']=c['proof']['references']['response']['artifact_id'];f.rejects(lambda:reconcile(c,payload))
    check('forged status missing fields cost claims changed hashes cross-artifact references and certificates cannot clear unknown calls',invalid)

    def access():
        c=case();payload=certificate(c)
        for role in ('anon','authenticated'):f.rejects(lambda role=role:reconcile(c,payload,role=role))
        token=c['token'];c['token']=f.uid();f.rejects(lambda:reconcile(c,payload));c['token']=token
        for role in ('anon','authenticated','service_role'):
            expect(f.query('select has_function_privilege('+q(role)+','+q('public.platform_worker_before_http_recovery_v8(text,uuid,uuid,uuid,jsonb)')+",'EXECUTE')")=='f')
        f.query('update platform_settings set paused=true where id');f.query('update platform_tasks set cancel_requested=true where id='+q(c['task']))
        original=old(c);reconcile(c,payload);expect(old(c)==original)
        denied=rpc('begin-run',c['task'],c['token'],dict(id=f.uid(),request_sha256=c['proof']['request_sha256'],request_artifact_id=c['proof']['references']['request']['artifact_id']))
        expect(denied['denied']=='paused-cancelled-or-deadline');f.query('update platform_settings set paused=false where id')
    check('only a live service lease can reconcile and pause cancellation helper privacy and original outcome immutability remain enforced',access)

    def immutable():
        c=case();payload=certificate(c);reconcile(c,payload)
        changed=copy.deepcopy(c['proof']);changed['provider_calls']=2;f.rejects(lambda:reconcile(c,certificate(c,changed)))
        f.rejects(lambda:f.query("update platform_run_reconciliations set proof='{}' where run_id="+q(c['run'])))
        f.rejects(lambda:rpc('finish-run',c['task'],c['token'],dict(id=c['run'],status='failed',response_artifact_id=c['proof']['references']['response']['artifact_id'])))
        f.rejects(lambda:f.query("update platform_runs set status='failed' where id="+q(c['run']),role='service_role'))
    check('supplemental proof and historical terminal outcomes remain immutable',immutable)

    def reset():
        # Local synthetic fixtures only: make independent scheduling cases
        # quiescent without deleting call records or inventing terminal success.
        f.query("update platform_tasks set status='blocked',lease_token=null,lease_until=null,checkpoint=checkpoint-'cleanup_unknown';update research_autonomy_tasks set status='blocked',lease_token=null,lease_until=null;update platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until='-infinity';update platform_settings set paused=false;")
        f.query("insert into research_runtime_maintenance_releases(hold_id,reason) select id,'Synthetic native recovery teardown.' from research_runtime_maintenance_holds on conflict do nothing")
        f.query("update research_model_dispatches set lease_until=clock_timestamp()-interval '1 second' where status='running'")
        dispatch.rpc('claim',{})
        expect(f.query("select count(*) from research_model_dispatches where status='running'")=='0')
        rpc('heartbeat',payload=dict(status='ready',reason='Isolated native reconciliation scheduling fixture.'))
    def claim():return rpc('claim',payload=dict(policy_sha256=policy))
    def served(ident):f.query("insert into platform_events(id,task_id,actor,kind,message) values("+','.join([q(f.uid()),q(ident),q('supervisor'),q('claimed'),q('Synthetic earlier attempt')])+')')
    def release(leased):
        rpc('checkpoint',leased['id'],leased['lease_token'],dict(status='reconciling',reason='Synthetic unknown retained.',checkpoint=leased['checkpoint']))
        f.query("update platform_host_turn set cooldown_until=clock_timestamp()-interval '1 second'")
    def fair():
        reset();c=case(expired=True);f.query('update platform_tasks set lease_token=null,lease_until=null where id='+q(c['task']));served(c['task'])
        other,_=task(status='queued',leased=False);before=old(c);chosen=claim();expect(chosen['id']==other)
        release(chosen);f.query("update platform_tasks set status='blocked' where id="+q(other))
        chosen=claim();expect(chosen['id']==c['task']);expect(old(c)==before);release(chosen)
    check('a thirteen-hour-old unknown result cannot monopolize the next independent repair turn',fair)

    def backoff():
        reset();blocked,_=task(leased=False);f.query('update platform_tasks set checkpoint='+f.sql_json(dict(not_before='2099-01-01T00:00:00Z',reconciliation_wait=dict(version='platform-reconciliation-backoff-v1')))+' where id='+q(blocked))
        other,_=task(status='queued',leased=False);chosen=claim();expect(chosen['id']==other);release(chosen)
    check('task-local reconciliation backoff leaves independent repairs eligible',backoff)

    def priorities():
        reset();repair,_=task(status='queued',leased=False);maintenance,_=task(status='queued',leased=False)
        f.query('update platform_tasks set priority=0 where id='+q(repair));f.query('update platform_tasks set priority=100 where id='+q(maintenance));served(repair)
        chosen=claim();expect(chosen['id']==repair);release(chosen)
    check('assessment repair priority is preserved ahead of never-served general maintenance',priorities)

    def urgent():
        for kind in ('cleanup','external','live-call'):
            reset();old_task,_=task(status='queued',leased=False);shared,_=task(leased=False);served(shared)
            if kind=='cleanup':f.query('update platform_tasks set checkpoint='+f.sql_json(dict(cleanup_unknown=True))+' where id='+q(shared))
            elif kind=='external':
                body=workflow.canonical(dict(fixture='unknown deployment'))
                f.query("insert into platform_operations(id,task_id,kind,request_sha256,request,status) values("+','.join([q(f.uid()),q(shared),q('deploy'),q(workflow.digest(body)),f.sql_json(dict(fixture='unknown deployment')),q('unknown')])+')')
            else:
                ref=artifact(shared,'running-request',b'{}')
                f.query("insert into platform_runs(id,task_id,number,request_sha256,request_artifact_id,status,reserved_cents) values("+','.join([q(f.uid()),q(shared),'1',q(ref['sha256']),q(ref['artifact_id']),q('running'),'100'])+')')
            chosen=claim();expect(chosen['id']==shared);release(chosen)
    check('shared container cleanup live calls and unresolved external mutations retain their urgent fences',urgent)

    def concurrent_claim():
        reset();first,_=task(status='queued',leased=False);second,_=task(status='queued',leased=False)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
        leased=[r for r in results if r is not None];expect(len(leased)==1 and leased[0]['id'] in (first,second));release(leased[0])
    check('concurrent claims retain a single host lease and never overlap coding',concurrent_claim)
    f.report.update(passed=True,protocol='platform-reconciliation-progress-v1');path=f.DIRECTORY/'platform-reconciliation-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))


if __name__=='__main__':
    try:main()
    except Exception as error:
        f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'platform-reconciliation-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
