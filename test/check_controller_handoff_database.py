"""Controller queue reconciliation and incident-specific delivery in real SQL.

Retained isolated loopback PostgreSQL only. No Docker, production writes,
inference, experiments or scientific measurements.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import uuid
from unittest.mock import patch
import check_platform_fair_scheduling_database as previous
import check_research_ideas_database as f
import autonomy,workflow

MIGRATIONS=('202611010007_controller_queue_reconciliation.sql','202611010008_repair_incident_delivery.sql')


def main():
    previous.main();f.report.update(protocol='controller-repair-handoff-v1',passed=False)
    q=f.sql_text
    def js(sql,role=None):
        value=f.query(sql,role=role);return json.loads(value) if value else None
    def expect(value):
        if not value:raise AssertionError('Controller handoff invariant failed.')
    def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
    def snapshot():
        return f.query("select jsonb_build_object('calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t),'dispatches',(select jsonb_agg(to_jsonb(d) order by id) from research_model_dispatches d),'workflows',(select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w),'budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b),'platform',(select jsonb_agg(to_jsonb(t) order by id) from platform_tasks t))")
    before=snapshot()
    for name in MIGRATIONS:
        raw=(f.ROOT/'database'/name).read_bytes();f.query(raw.decode());f.report['migration_sha256'][name]=workflow.digest(raw)
    check('both handoff migrations preserve every retained call turn dispatch workflow budget and platform task',lambda:expect(snapshot()==before))
    unknown_before=f.query("select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c where status='unknown'")
    unknown_ids=js("select coalesce(jsonb_agg(id),'[]') from research_builder_calls where status='unknown'")
    prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
    def case(builder=False,parent='failed',status='queued'):
        with patch.object(autonomy,'wake',return_value={}):
            study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Synthetic controller handoff',paper_url='https://example.org/handoff.pdf',domain='Software',scope=__doc__)))['id']
        task=f.query('select id from research_autonomy_tasks where study_id='+q(study));ident=f.uid()
        request=dict(modelId='gpt-6.1-sol',messages=[dict(role='user',content='Synthetic ordinary controller request')])
        if builder:request['builder']=dict(context=dict(synthetic=True))
        raw=workflow.canonical(request).decode();h=workflow.digest(raw.encode())
        f.query("update research_autonomy_tasks set stage='building',status='waiting',attempts=3 where id="+q(task))
        f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,ended_at) values('+','.join([q(ident),q(study),q(task),'1',q('building'),q(prompt),q('gpt-6.1-sol'),f.sql_json(request),q(raw),q(h),q(parent),'100','null' if parent=='running' else 'clock_timestamp()'])+')')
        f.query('insert into research_model_dispatches(id,study_id,task_id,runtime,request_raw,request_sha256,status) values('+','.join([q(ident),q(study),q(task),q('openclaw-production-v1'),q(raw),q(h),q(status)])+')')
        return dict(id=ident,study_id=study,task_id=task,request_sha256=h)
    def reconcile(d,role='service_role',sha=None):return js('select public.research_model_reconcile_queued('+q(d['id'])+','+q(sha or d['request_sha256'])+')',role)
    def diag(d):return js('select public.research_queued_dispatch_diagnostic('+q(d['id'])+','+q(d['request_sha256'])+')')
    def terminal(d):return f.query('select to_jsonb(t) from research_autonomy_turns t where id='+q(d['id']))
    def limits(d):return f.query('select jsonb_build_object(\'workflow\',to_jsonb(w),\'task\',to_jsonb(t)) from research_autonomy_workflows w join research_autonomy_tasks t using(study_id) where t.id='+q(d['task_id']))
    def artifact(d,filename,kind='model-runtime-original',study=None):
        ident=f.uid();h=workflow.digest(ident.encode());study=study or d['study_id']
        f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(ident),q(study),q(h),'0',q(study+'/'+h),q('application/octet-stream'),f.sql_json(dict(kind=kind,filename=filename,dispatch_id=d['id'])),'clock_timestamp()'])+')')
        return ident,h
    ordinary=case()
    def ordinary_recovery():
        before_turn=terminal(ordinary);before_limits=limits(ordinary)
        expect(diag(ordinary)['eligible'] and diag(ordinary)['request_kind']=='controller')
        candidates=js('select coalesce(jsonb_agg(x),\'[]\') from public.research_model_reconciliation_candidates('+q(ordinary['id'])+') x','service_role')
        # Cursor ordering is unchanged. Direct exact-ID eligibility is tested
        # independently of which eight older candidates precede this UUID.
        expect(all(x['id']>ordinary['id'] for x in candidates))
        candidates=js('select coalesce(jsonb_agg(x),\'[]\') from public.research_model_reconciliation_candidates('+q(str(uuid.UUID(int=uuid.UUID(ordinary['id']).int-1)))+') x','service_role')
        expect(any(x['id']==ordinary['id'] for x in candidates))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:reconcile(ordinary),range(2)))
        expect(all(r['reconciled'] for r in results))
        row=js('select to_jsonb(r) from research_queued_dispatch_reconciliations r where dispatch_id='+q(ordinary['id']))
        expect(row['proof']['version']=='queued-dispatch-reconciliation-v2' and row['proof']['request_kind']=='controller')
        expect(row['proof']['provider_calls']==0 and row['proof']['provider_request_sent'] is False)
        expect(workflow.digest(row['snapshot_raw'].encode())==row['snapshot_sha256'])
        expect(json.loads(row['snapshot_raw'])['status']=='queued' and terminal(ordinary)==before_turn and limits(ordinary)==before_limits)
        expect(f.query('select count(*) from research_queued_dispatch_reconciliations where dispatch_id='+q(ordinary['id']))=='1')
        expect(reconcile(ordinary)==results[0])
    check('ordinary controller admission is discovered and atomically closed once without changing its terminal parent or limits',ordinary_recovery)
    def builder_compatibility():
        d=case(True);reconcile(d)
        proof=js('select proof from research_queued_dispatch_reconciliations where dispatch_id='+q(d['id']))
        expect(proof['version']=='queued-dispatch-reconciliation-v1' and 'request_kind' not in proof)
    check('legacy builder closure and immutable v1 proof remain compatible',builder_compatibility)
    def security():
        d=case();before=f.query('select to_jsonb(d) from research_model_dispatches d where id='+q(d['id']))
        f.rejects(lambda:reconcile(d,sha='0'*64))
        for role in ('anon','authenticated'):
            f.rejects(lambda role=role:reconcile(d,role))
            expect(f.query("select has_function_privilege("+q(role)+",'public.research_model_reconciliation_candidates(uuid)','EXECUTE')")=='f')
        for role in ('anon','authenticated','service_role'):
            f.rejects(lambda role=role:f.query('select public.research_queued_dispatch_diagnostic('+q(d['id'])+','+q(d['request_sha256'])+')',role=role))
            expect(f.query('select has_function_privilege('+q(role)+",'public.platform_repair_context_data_before_delivery_v5(uuid)','EXECUTE')")=='f')
        expect(f.query('select to_jsonb(d) from research_model_dispatches d where id='+q(d['id']))==before)
    check('changed request hashes browsers and direct private helper calls cannot perform or bypass reconciliation',security)
    def refusal():
        for defect,code in [('running-parent','parent-not-terminal'),('claimed','claim-fence-present'),('provenance','transport-or-outcome-record-present'),('unknown','dispatch-not-queued'),('artifact','dispatch-artifacts-present')]:
            d=case(parent='running' if defect=='running-parent' else 'failed',status='unknown' if defect=='unknown' else 'queued')
            if defect=='claimed':f.query('update research_model_dispatches set lease_token='+q(f.uid())+",lease_until=clock_timestamp()+interval '1 hour' where id="+q(d['id']))
            elif defect=='provenance':f.query("update research_model_dispatches set provenance='{\"retained\":true}' where id="+q(d['id']))
            elif defect=='artifact':artifact(d,'original.json')
            before=f.query('select to_jsonb(d) from research_model_dispatches d where id='+q(d['id']))
            value=reconcile(d);expect(value['reconciled'] is False and code in value['diagnostic']['reason_codes'])
            expect(f.query('select to_jsonb(d) from research_model_dispatches d where id='+q(d['id']))==before)
    check('live claimed touched unknown and artifact-bearing originals receive exact refusals without outcome changes',refusal)
    def native_fence():
        d=case();a,h=artifact(d,'original-native-request.json')
        f.query('insert into research_builder_calls(study_id,task_id,dispatch_id,number,prompt_version_id,model_id,request_artifact_id,request_sha256,request_bytes,status,reserved_cents) values('+','.join([q(d['study_id']),q(d['task_id']),q(d['id']),'1',q(prompt),q('gpt-6.1-sol'),q(a),q(h),'1',q('unknown'),'100'])+')')
        before=f.query('select to_jsonb(c) from research_builder_calls c where dispatch_id='+q(d['id']))
        expect('native-admission-present' in reconcile(d)['diagnostic']['reason_codes'])
        expect(f.query('select to_jsonb(c) from research_builder_calls c where dispatch_id='+q(d['id']))==before)
    check('an unknown native admission cannot be relabeled as a zero-transport controller closure',native_fence)

    def linked(d):
        platform,blocker=f.uid(),f.uid()
        f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,status,max_reserved_cents,deadline_at) select '+q(platform)+",(select user_id from platform_operators where role='owner' limit 1),'Incident delivery fixture','Synthetic original handoff.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'blocked',-1,clock_timestamp()+interval '1 hour' from platform_settings where id")
        f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join([q(blocker),q(d['study_id']),q(d['task_id']),q('dispatch'),q(d['id']),q('building'),q('queued'),q('Synthetic original handoff.'),q('a'*64),q(workflow.digest(blocker.encode()))])+')')
        f.query('insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(platform)+')')
        return platform
    def packet(platform):return js('select public.platform_repair_context_data('+q(platform)+')')
    def diagnostic_delivery():
        d=case();platform=linked(d);before=packet(platform)
        expect(before['queued_admission_diagnostics'][0]['eligible'])
        expect(before['queued_admission_diagnostics'][0]['request_kind']=='controller')
        f.query('update research_model_dispatches set lease_token='+q(f.uid())+' where id='+q(d['id']))
        after=packet(platform)
        expect('claim-fence-present' in after['queued_admission_diagnostics'][0]['reason_codes'])
        expect(after['evidence_revision']!=before['evidence_revision'])
        expect(packet(platform)['evidence_revision']==after['evidence_revision'])
        versions=after['recovery_contract']['queued_admission']['accepted_proof_versions']
        expect(versions==['queued-dispatch-reconciliation-v1','queued-dispatch-reconciliation-v2'])
    check('trusted repair context persists current eligibility or refusal with a stable semantic evidence revision',diagnostic_delivery)
    def delivery():
        d=case(True);platform=linked(d);expected={}
        for filename in ('context-delivery.json','checkpoint.zip','receipt.json','task.txt','action-policy.json','stdout.bin','stderr.bin'):
            ident,h=artifact(d,filename);expected[filename]=ident
        denied='native-request-'+'b'*64+'.json';ident,h=artifact(d,denied);expected[denied]=ident
        f.query('update research_model_dispatches set provenance='+f.sql_json(dict(denied_request=dict(filename=denied,received_sha256=h)))+' where id='+q(d['id']))
        # Real incident manifests must survive a long tail of transport files.
        for i in range(25):artifact(d,'irrelevant-'+str(i)+'.json')
        other=case();cross,_=artifact(d,'task.txt',study=other['study_id'])
        value=packet(platform);ids={a['id'] for a in value['artifacts']}
        expect(set(expected.values())<=ids and cross not in ids and len(ids)<=12)
        doc=next(x for x in value['incident_documents'] if x['dispatch_id']==d['id'])
        expect(doc['request_sha256']==d['request_sha256'])
        roles={r['role']:r['artifact_id'] for r in doc['references']}
        expect(roles['denied_request']==expected[denied] and roles['bootstrap']==expected['task.txt'])
        expect(roles['context_delivery']==expected['context-delivery.json'] and roles['checkpoint']==expected['checkpoint.zip'])
        before=value['evidence_revision']
        f.query("update research_autonomy_tasks set lease_until=clock_timestamp()+interval '5 minutes' where id="+q(d['task_id']))
        expect(packet(platform)['evidence_revision']==before)
    check('incident manifests bootstrap checkpoint and exact denied request survive log churn with the original 12-artifact and study boundaries',delivery)
    check('pre-existing uncertain native originals remain unchanged throughout every new handoff check',lambda:expect(unknown_before==f.query('select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c where id in ('+(','.join(map(q,unknown_ids)) if unknown_ids else 'null')+')')))
    f.report['passed']=True;path=f.DIRECTORY/'controller-handoff-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))


if __name__=='__main__':
    try:main()
    except Exception as error:
        f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'controller-handoff-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
