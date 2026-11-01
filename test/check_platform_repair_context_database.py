"""Current wrapper order, scoped evidence and event-driven repair reactivation.

Fresh retained loopback PostgreSQL fixture only; no production or model calls.
"""
import json
import check_integrated_native_reconciliation_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202611010001_platform_repair_context.sql'


def main():
    previous.main();f.report.update(protocol='platform-repair-handoff-v1',passed=False)
    q=f.sql_text
    def js(sql,role=None):
        result=f.query(sql,role=role);return json.loads(result) if result else None
    def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
    def expect(value):
        if not value:raise AssertionError('Repair handoff invariant failed.')
    original_worker=f.query("select pg_get_functiondef('public.platform_worker(text,uuid,uuid,uuid,jsonb)'::regprocedure)")
    before=f.query("select jsonb_build_object('budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b),'workflows',(select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w),'calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c))")
    data=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(data.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(data)
    check('migration retains prior wrappers budgets workflows and original call rows',lambda:expect(
        f.query("select jsonb_build_object('budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b),'workflows',(select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w),'calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c))")==before
        and f.query("select pg_get_functiondef('public.platform_worker_before_repair_context_v1(text,uuid,uuid,uuid,jsonb)'::regprocedure)").replace('platform_worker_before_repair_context_v1','platform_worker',1)==original_worker))
    task=js("select to_jsonb(t) from research_autonomy_tasks t join research_autonomy_workflows w using(study_id) where w.status in ('running','completed-with-blockers') and w.deadline_at>clock_timestamp()+interval '1 hour' and not exists(select 1 from research_autonomy_repairs r where r.task_id=t.id) limit 1")
    assert task
    platform,blocker,worker,token=f.uid(),f.uid(),f.uid(),f.uid()
    f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,committed_cents,deadline_at,worker_id,lease_token,lease_until) select '+q(platform)+",(select user_id from platform_operators where role='owner' limit 1),'Repair evidence fixture','Read scoped original diagnostics.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'implementing',-1,17200,clock_timestamp()+interval '1 hour',"+q(worker)+','+q(token)+",clock_timestamp()+interval '4 minutes' from platform_settings where id")
    f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join([q(blocker),q(task['study_id']),q(task['id']),q('task'),q(task['id']),q(task['stage']),q('blocked'),q('Synthetic recorded diagnostic.'),q('a'*64),q('b'*64)])+')')
    f.query('insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(platform)+')')
    f.query('update platform_settings set paused=false where id')
    def context(w=worker,t=platform,k=token,role='service_role'):
        return js('select public.platform_repair_context('+','.join(map(q,[w,t,k]))+')',role)
    # Include one original incident, one semantic event and an old referenced
    # checkpoint among newer transport artifacts. No artifact is executed.
    incident=json.dumps(dict(version='fixture-incident-v1',reason='Original diagnostic.'),sort_keys=True)
    repair_id=f.uid()
    f.query('insert into research_autonomy_repairs(id,study_id,task_id,version,category,original_stage,incident_raw,incident_sha256,original_context,state,reason) values('+','.join([q(repair_id),q(task['study_id']),q(task['id']),q('autonomous-repair-v1'),q('runtime'),q(task['stage']),q(incident),q(workflow.digest(incident.encode())),f.sql_json(task['context']),q('diagnosing'),q('Original diagnostic.')])+')')
    diagnostic=dict(reason='Original diagnostic.',revision=0,at='fixture-clock-0')
    def event(details,kind='recorded-diagnosis',study=task['study_id'],linked_task=task['id']):
        f.query('insert into research_autonomy_events(id,study_id,task_id,event,details) values('+','.join([q(f.uid()),q(study),q(linked_task),q(kind),f.sql_json(details)])+')')
    event(diagnostic)
    checkpoint=f.uid();sha='c'*64
    def artifact(ident,provenance,study=task['study_id']):
        f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(ident),q(study),q(sha),'0',q(study+'/'+sha),q('application/octet-stream'),f.sql_json(provenance),'clock_timestamp()'])+')')
    artifact(checkpoint,dict(filename='checkpoint.zip'))
    f.query('update research_autonomy_tasks set context=context||'+f.sql_json(dict(builder_checkpoint=dict(artifact_id=checkpoint,sha256=sha)))+' where id='+q(task['id']))
    for i in range(15):artifact(f.uid(),dict(task_id=task['id'],filename='call-'+str(i)+'-request.json'))
    other=js('select jsonb_build_object(\'id\',id,\'study_id\',study_id) from research_autonomy_tasks where study_id<>'+q(task['study_id'])+' limit 1')
    assert other
    private_artifact=f.uid();artifact(private_artifact,dict(task_id=task['id'],filename='diagnosis.json'),study=other['study_id'])
    unrelated_artifact=f.uid();artifact(unrelated_artifact,dict(task_id=other['id'],filename='diagnosis.json'))
    event(dict(reason='Cross-study evidence must not be delivered.'),study=other['study_id'],linked_task=task['id'])
    packet=context()
    check('service RPC binds complete operational packet to immutable assessment link',lambda:expect(packet['platform_task_id']==platform and packet['assessment_id']==task['study_id'] and packet['assessment_task_id']==task['id'] and packet['version']=='platform-repair-handoff-v1' and 'native_calls' in packet and 'repairs' in packet and 'repair_events' in packet and 'coverage' in packet))
    check('referenced checkpoint survives recent log churn and cross-study records stay private',lambda:expect(checkpoint in [a['id'] for a in packet['artifacts']] and private_artifact not in [a['id'] for a in packet['artifacts']] and unrelated_artifact not in [a['id'] for a in packet['artifacts']] and all(e['details'].get('reason')!='Cross-study evidence must not be delivered.' for e in packet['events'])))
    def denied():
        for role in ('anon','authenticated'):
            f.rejects(lambda role=role:context(role=role))
            f.rejects(lambda role=role:f.query('select public.platform_repair_context_data('+q(platform)+')',role=role))
        f.rejects(lambda:context(w=f.uid()));f.rejects(lambda:context(k=f.uid()))
        f.rejects(lambda:f.query('select public.platform_repair_context_data('+q(platform)+')',role='service_role'))
        f.rejects(lambda:f.query("select public.platform_worker_before_repair_context_v1('lease',"+','.join(map(q,[worker,platform,token]))+",'{}')",role='service_role'))
    check('browser stale lease wrong worker and direct helper bypass are denied',denied)
    def stopped_authority():
        f.query('update platform_settings set paused=true where id');f.rejects(context)
        f.query('update platform_settings set paused=false where id')
        f.query('update platform_tasks set lease_until=clock_timestamp()-interval \'1 second\' where id='+q(platform));f.rejects(context)
        f.query('update platform_tasks set lease_until=clock_timestamp()+interval \'8 minutes\' where id='+q(platform))
        f.query('update platform_tasks set cancel_requested=true where id='+q(platform));f.rejects(context)
        f.query('update platform_tasks set cancel_requested=false where id='+q(platform))
        original_status=f.query('select status from research_autonomy_workflows where study_id='+q(task['study_id']))
        f.query('update research_autonomy_workflows set status=\'cancelled\' where study_id='+q(task['study_id']));f.rejects(context)
        f.query('update research_autonomy_workflows set status='+q(original_status)+' where study_id='+q(task['study_id']))
    check('pause lease expiry cancellation and stopped parent fence diagnostic access',stopped_authority)
    def stable():
        f.query('update research_autonomy_tasks set lease_until=clock_timestamp()+interval \'9 minutes\' where id='+q(task['id']))
        f.query('update platform_tasks set lease_until=clock_timestamp()+interval \'8 minutes\' where id='+q(platform))
        expect(context()['evidence_revision']==packet['evidence_revision'])
    check('lease renewals do not masquerade as new incident evidence',stable)
    def bookkeeping():
        # The original incident/evidence is unchanged despite phase revisions,
        # clock updates, duplicate events and a rolled bounded display window.
        f.query('update research_autonomy_repairs set state=\'waiting\',revision=revision+1 where id='+q(repair_id))
        f.query('update research_autonomy_tasks set context=context||'+f.sql_json(dict(repair_progress=dict(state='waiting',revision=100,updated_at='new-clock')))+' where id='+q(task['id']))
        for i in range(26):event(dict(diagnostic,revision=i+1,at='fixture-clock-'+str(i+1)))
        expect(context()['evidence_revision']==packet['evidence_revision'])
    check('phase revisions and duplicate timestamp events cannot restart blocked repair',bookkeeping)
    def counts():return js('select jsonb_build_object(\'committed_cents\',committed_cents,\'deadline_at\',deadline_at,\'id\',id) from platform_tasks where id='+q(platform))
    retained=counts();revision=packet['evidence_revision']
    guard=dict(repair_guard=dict(version='platform-repair-handoff-v1',waiting=True,evidence_revision=revision,unchanged_slices=2))
    f.query('update platform_tasks set status=\'blocked\',checkpoint='+f.sql_json(guard)+',lease_token=null,lease_until=null where id='+q(platform))
    policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
    def maintenance():return js("select public.platform_worker('maintenance',"+q(worker)+",null,null,"+f.sql_json(dict(policy_sha256=policy))+')','service_role')
    def status():return f.query('select status from platform_tasks where id='+q(platform))
    maintenance();maintenance()
    check('unchanged blocked incident remains blocked without a timer or new task',lambda:expect(status()=='blocked' and counts()==retained))
    event(dict(reason='New diagnostic is available.',original_call_id=f.uid()),kind='new-original-diagnosis')
    maintenance()
    check('changed original diagnostic reactivates same task without resetting commitments or deadline',lambda:expect(status()=='investigating' and counts()==retained))
    new_revision=f.query('select public.platform_repair_context_data('+q(platform)+")->>'evidence_revision'")
    expect(new_revision!=revision)
    check('one event records evidence change without altering original outcome',lambda:expect(f.query("select count(*) from platform_events where task_id="+q(platform)+" and kind='repair-evidence-updated'")=='1'))
    def claim_binding():
        def claim(ident):return js("select public.platform_worker('claim',"+q(worker)+",null,null,"+f.sql_json(dict(policy_sha256=policy,only_task=ident))+')','service_role')
        def release(ident,lease):return js("select public.platform_worker('checkpoint',"+','.join(map(q,[worker,ident,lease]))+','+f.sql_json(dict(status='blocked',reason='Synthetic claim check; no provider call.',checkpoint=guard))+')','service_role')
        # The preceding handoff cancellation fixture intentionally retains its
        # lease. Preserve that fence, then acknowledge the cancelled fixture via
        # its normal RPC only after proving it has no provider/release actions.
        held=js('select coalesce(jsonb_agg(to_jsonb(t)),\'[]\') from platform_tasks t where cancel_requested and lease_token is not null')
        if held:expect(claim(platform) is None)
        for cancelled in held:
            expect(f.query('select (select count(*) from platform_runs where task_id='+q(cancelled['id'])+')+(select count(*) from platform_operations where task_id='+q(cancelled['id'])+')')=='0')
            js("select public.platform_worker('checkpoint',"+','.join(map(q,[cancelled['worker_id'],cancelled['id'],cancelled['lease_token']]))+','+f.sql_json(dict(status='cancelled',reason='Acknowledge prior synthetic cancellation fixture; no dispatched action.'))+')','service_role')
        leased=claim(platform);expect(leased is not None and leased['id']==platform and leased['assessment_repair'] is True)
        expect(context(k=leased['lease_token'])['assessment_id']==task['study_id']);release(platform,leased['lease_token'])
        ordinary=f.uid()
        f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,deadline_at) select '+q(ordinary)+",requested_by,'Ordinary owner fixture','No assessment link.',repositories,authorization_version,'queued',-1,deadline_at from platform_tasks where id="+q(platform))
        leased=claim(ordinary);expect(leased is not None and leased['assessment_repair'] is False)
        expect(context(t=ordinary,k=leased['lease_token']) is None);release(ordinary,leased['lease_token'])
        expect(counts()==retained)
    check('actual claim adds assessment flag only for immutable linked tasks',claim_binding)
    def cancellation():
        f.query('update platform_tasks set status=\'blocked\',checkpoint='+f.sql_json(guard)+' where id='+q(platform))
        f.query('update platform_settings set paused=true where id');maintenance();expect(status()=='blocked' and counts()==retained)
        f.query('update platform_settings set paused=false where id')
        f.query('update platform_tasks set status=\'blocked\',cancel_requested=true,checkpoint='+f.sql_json(guard)+' where id='+q(platform))
        maintenance();expect(status()=='blocked' and counts()==retained)
    check('paused or cancelled repair cannot reactivate on new evidence',cancellation)
    def expiry():
        f.query('update platform_tasks set cancel_requested=false,deadline_at=clock_timestamp()-interval \'1 second\' where id='+q(platform))
        maintenance();expect(status()=='blocked')
    check('original deadline still fences reactivation',expiry)
    f.report['passed']=True;path=f.DIRECTORY/'platform-repair-handoff-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),provider_calls=0,production_mutations=0)))


if __name__=='__main__':
    try:main()
    except Exception as error:
        f.report.update(passed=False,error_type=type(error).__name__,error=str(error))
        (f.DIRECTORY/'platform-repair-handoff-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n')
        raise
