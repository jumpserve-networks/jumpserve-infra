"""Real isolated SQL: timing churn, semantic upgrade and orphan queue races."""
import concurrent.futures,json,time
from unittest.mock import patch
import check_platform_repair_context_database as previous
import check_research_ideas_database as f
import autonomy,workflow

MIGRATIONS=['202611010002_queued_dispatch_recovery.sql','202611010003_platform_repair_semantic_evidence.sql']

def main():
    previous.main();f.report.update(protocol='repair-semantic-and-queued-recovery-v2',passed=False)
    q=f.sql_text
    def js(sql,role=None):
        value=f.query(sql,role=role);return json.loads(value) if value else None
    def expect(value):
        if not value:raise AssertionError('Repair recovery invariant failed.')
    def check(name,fn):f.check(name,lambda:(fn() or dict(passed=True)))
    prompt=f.query('select active_version_id from agent_prompt_settings where module_id=\'research-autonomy\'')
    def case(parent='failed',status='queued'):
        with patch.object(autonomy,'wake',return_value={}):
            study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic orphaned dispatch',paper_url='https://example.org/fixture.pdf',domain='Software validation',scope=__doc__)))['id']
        task=f.query('select id from research_autonomy_tasks where study_id='+q(study));ident=f.uid()
        raw=workflow.canonical(dict(modelId='gpt-6.1-sol',builder=dict(context=dict(synthetic=True)))).decode();h=workflow.digest(raw.encode())
        f.query('update research_autonomy_tasks set stage=\'building\',status=\'waiting\',attempts=3 where id='+q(task))
        values=[q(ident),q(study),q(task),'1',q('building'),q(prompt),q('gpt-6.1-sol'),f.sql_json(json.loads(raw)),q(raw),q(h),q(parent),'100','null' if parent=='running' else 'clock_timestamp()']
        f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,ended_at) values('+','.join(values)+')')
        f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status) values('+','.join([q(ident),q(study),q(task),q('openclaw-production-v1'),q(raw),q(h),q(status)])+')')
        return dict(id=ident,study_id=study,task_id=task,request_sha256=h)
    original=case()
    platform,blocker,worker=f.uid(),f.uid(),f.uid()
    f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,committed_cents,deadline_at) select '+q(platform)+",(select user_id from platform_operators where role='owner' limit 1),'Semantic recovery fixture','Synthetic original queue diagnosis.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'blocked',-1,17700,clock_timestamp()+interval '1 hour' from platform_settings where id")
    f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join([q(blocker),q(original['study_id']),q(original['task_id']),q('dispatch'),q(original['id']),q('building'),q('queued'),q('Original dispatch remains admitted.'),q('a'*64),q('d'*64)])+')')
    f.query('insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(platform)+')')
    def event(details,kind='task-advanced'):
        f.query('insert into research_autonomy_events(study_id,task_id,event,details) values('+','.join([q(original['study_id']),q(original['task_id']),q(kind),f.sql_json(details)])+')')
    diagnostic=dict(status='waiting',reason='Original dispatch remains admitted.',attempts=3,usage=dict(controller_wall_seconds=0.05,hosting_configured_memory_mb='1024',measured_charges_usd=None))
    event(diagnostic)
    def packet():return js('select public.platform_repair_context_data('+q(platform)+')')
    old_packet=packet();guard=dict(version='platform-repair-handoff-v1',waiting=True,unchanged_slices=2,evidence_revision=old_packet['evidence_revision'],progress_sha256='f'*64)
    f.query('update platform_tasks set checkpoint='+f.sql_json(dict(repair_guard=guard))+' where id='+q(platform))
    def preserved():return f.query("select jsonb_build_object('budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t),'calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c),'claims',(select jsonb_agg(to_jsonb(c) order by id) from research_claims c),'workflow',(select to_jsonb(w) from research_autonomy_workflows w where study_id="+q(original['study_id'])+'))')
    before=preserved()
    for name in MIGRATIONS:
        raw=(f.ROOT/'database'/name).read_bytes();f.query(raw.decode());f.report['migration_sha256'][name]=workflow.digest(raw)
    check('forward migrations preserve original turns calls claims and category limits',lambda:expect(preserved()==before))
    baseline=packet()['evidence_revision']
    def platform_state():return js('select jsonb_build_object(\'status\',status,\'checkpoint\',checkpoint,\'committed_cents\',committed_cents,\'deadline_at\',deadline_at) from platform_tasks where id='+q(platform))
    retained=platform_state()
    check('fingerprint upgrade appends a baseline without restarting or replacing old blocked evidence',lambda:expect(retained['status']=='blocked' and all(retained['checkpoint']['repair_guard'][k]==v for k,v in guard.items()) and retained['checkpoint']['repair_guard']['semantic_baseline']['evidence_revision']==baseline))
    policy=f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')
    def maintenance():return js("select public.platform_worker('maintenance',"+q(worker)+",null,null,"+f.sql_json(dict(policy_sha256=policy))+')','service_role')
    def stable_timing():
        for i in range(4):
            event(dict(diagnostic,attempts=100+i,usage=dict(controller_wall_seconds=0.1+i,hosting_configured_memory_mb='2048',measured_charges_usd=i)))
            event(dict(usage=dict(controller_wall_seconds=900+i)),kind='controller-usage-only')
            f.query('update research_autonomy_tasks set attempts=attempts+1,status='+q('running' if i%2 else 'waiting')+',lease_until=clock_timestamp()+interval \'1 minute\' where id='+q(original['task_id']))
            maintenance();expect(packet()['evidence_revision']==baseline and platform_state()['status']=='blocked')
        expect(platform_state()==retained)
    check('nested controller usage clocks counters and polling cannot wake blocked repair',stable_timing)
    def security():
        for role in ('anon','authenticated'):
            f.rejects(lambda role=role:f.query('select * from research_queued_dispatch_reconciliations',role=role))
            f.rejects(lambda role=role:js('select public.research_model_reconcile_queued('+q(original['id'])+','+q(original['request_sha256'])+')',role))
        for function in ('platform_repair_event_evidence(jsonb)','platform_repair_context_data_before_semantic_v2(uuid)'):
            expect(f.query('select has_function_privilege(\'service_role\','+q('public.'+function)+',\'EXECUTE\')')=='f')
        f.rejects(lambda:f.query('update research_queued_dispatch_reconciliations set proof=\'{}\'',role='service_role'))
        f.rejects(lambda:js('select public.research_model_reconcile_queued('+q(original['id'])+','+q('0'*64)+')','service_role'))
    check('proofs are private immutable and cannot be supplied by a browser or changed request',security)
    def reconcile(row):return js('select public.research_model_reconcile_queued('+q(row['id'])+','+q(row['request_sha256'])+')','service_role')
    dispatch_before=f.query('select to_jsonb(d)::text from research_model_dispatches d where id='+q(original['id']))
    parent_before=f.query('select to_jsonb(t)::text from research_autonomy_turns t where id='+q(original['id']))
    def closes():
        candidates=js("select coalesce(jsonb_agg(value),'[]') from public.research_model_reconciliation_candidates(null) value",'service_role')
        expect(original['id'] in [v['id'] for v in candidates]);expect(reconcile(original)['reconciled'])
        record=js('select to_jsonb(r) from research_queued_dispatch_reconciliations r where dispatch_id='+q(original['id']),'service_role')
        expect(record['snapshot_raw']==dispatch_before and record['snapshot_sha256']==workflow.digest(dispatch_before.encode()))
        expect(record['proof']['provider_calls']==0 and record['proof']['provider_request_sent'] is False)
        expect(f.query('select status from research_model_dispatches where id='+q(original['id']))=='failed')
        expect(f.query('select to_jsonb(t)::text from research_autonomy_turns t where id='+q(original['id']))==parent_before)
        expect(preserved()==before)
        expect('container_cleanup' not in record['proof'])
        expect(reconcile(original)['reconciled'])
        expect(f.query('select count(*) from research_queued_dispatch_reconciliations where dispatch_id='+q(original['id']))=='1')
        f.rejects(lambda:f.query('update research_queued_dispatch_reconciliations set proof=\'{}\' where dispatch_id='+q(original['id'])))
        f.rejects(lambda:f.query('update research_model_dispatches set status=\'queued\' where id='+q(original['id'])))
    check('orphan closure stores exact original snapshot and is idempotent without altering terminal parent',closes)
    def genuine_wake():
        maintenance();after=platform_state();expect(after['status']=='investigating' and all(after[k]==retained[k] for k in ('committed_cents','deadline_at')))
        expect(len(packet()['queued_reconciliations'])==1 and packet()['queued_reconciliations'][0]['dispatch_id']==original['id'])
        maintenance();expect(f.query("select count(*) from platform_events where task_id="+q(platform)+" and kind='repair-evidence-updated'")=='1')
    check('actual reconciliation evidence wakes the same task exactly once with original limits',genuine_wake)
    def uncertain_cases():
        for status in ('unknown','running'):
            row=case(status=status);before=f.query('select to_jsonb(d)::text from research_model_dispatches d where id='+q(row['id']))
            expect(not reconcile(row)['reconciled']);expect(f.query('select to_jsonb(d)::text from research_model_dispatches d where id='+q(row['id']))==before)
        for column,value in [('lease_token',q(f.uid())),('lease_until',"clock_timestamp()-interval '1 minute'"),('provenance',"'{\"worker_touched\":true}'::jsonb")]:
            row=case();f.query('update research_model_dispatches set '+column+'='+value+' where id='+q(row['id']));expect(not reconcile(row)['reconciled'])
        active=case(parent='running');expect(not reconcile(active)['reconciled'])
        f.query('update research_autonomy_turns set status=\'failed\',ended_at=clock_timestamp() where id='+q(active['id']));expect(reconcile(active)['reconciled'])
        row=case();artifact=f.uid();sha='9'*64
        f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(artifact),q(row['study_id']),q(sha),'1',q(row['study_id']+'/'+sha),q('application/octet-stream'),f.sql_json(dict(dispatch_id=row['id'])),'clock_timestamp()'])+')')
        f.query('insert into research_builder_calls(study_id,task_id,dispatch_id,number,prompt_version_id,model_id,request_artifact_id,request_sha256,request_bytes,status,reserved_cents) values('+','.join([q(row['study_id']),q(row['task_id']),q(row['id']),'1',q(prompt),q('gpt-6.1-sol'),q(artifact),q(sha),'1',q('unknown'),'100'])+')')
        before=f.query('select to_jsonb(c)::text from research_builder_calls c where dispatch_id='+q(row['id']))
        expect(not reconcile(row)['reconciled']);expect(f.query('select to_jsonb(c)::text from research_builder_calls c where dispatch_id='+q(row['id']))==before)
    def claim_race():
        row=case(parent='running')
        f.query('update research_autonomy_tasks set status=\'running\',lease_token='+q(f.uid())+',lease_until=clock_timestamp()+interval \'9 minutes\' where id='+q(row['task_id']))
        # All calls remain SQL-only. The real claim holds its dispatch row and
        # transaction open while the parent finishes and recovery races it.
        f.query("select public.research_model_dispatch('heartbeat',"+f.sql_json(dict(status='ready',configuration=dict(synthetic=True)))+')',role='service_role')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            claim=pool.submit(f.query,"set local application_name='queued-recovery-claim-race';select public.research_model_dispatch('claim','{}');select pg_sleep(0.7)",role='service_role')
            for _ in range(100):
                if f.query("select count(*) from pg_stat_activity where application_name='queued-recovery-claim-race' and wait_event='PgSleep'")=='1':break
                time.sleep(0.01)
            else:raise AssertionError('Real claim transaction did not reach its recorded race boundary.')
            f.query('update research_autonomy_turns set status=\'failed\',ended_at=clock_timestamp() where id='+q(row['id']))
            expect(not reconcile(row)['reconciled']);claim.result()
        current=js('select to_jsonb(d) from research_model_dispatches d where id='+q(row['id']))
        expect(current['status']=='running' and current['lease_token'] is not None)
        f.rejects(lambda:f.query('update research_model_dispatches set status=\'queued\' where id='+q(row['id'])))
        f.rejects(lambda:js("select public.research_builder_call('begin',"+f.sql_json(dict(dispatch_id=original['id'],token=f.uid()))+')','service_role'))
    check('real worker claim wins concurrent closure and closed admissions cannot later transport',claim_race)
    check('running unknown leased touched and active-parent work cannot become zero-transport proof',uncertain_cases)
    def completed_fairness():
        closed=[]
        for _ in range(9):
            row=case(parent='unknown');before=f.query('select to_jsonb(t)::text from research_autonomy_turns t where id='+q(row['id']))
            expect(reconcile(row)['reconciled']);closed.append(row['id'])
            expect(f.query('select to_jsonb(t)::text from research_autonomy_turns t where id='+q(row['id']))==before)
        candidates=js("select coalesce(jsonb_agg(value),'[]') from public.research_model_reconciliation_candidates(null) value",'service_role')
        expect(all(c['id'] not in closed for c in candidates))
    check('accounted queue records cannot fill the scan and unknown parent originals remain unchanged',completed_fairness)
    f.report['passed']=True;path=f.DIRECTORY/'repair-recovery-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),provider_calls=0,production_mutations=0)))

if __name__=='__main__':
    try:main()
    except Exception as error:
        f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'repair-recovery-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
