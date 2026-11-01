"""Installed contract plus real Python query against actual reconciliation SQL."""
import json,sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl,urlsplit
import check_repair_recovery_database as previous
import check_research_ideas_database as f
import autonomous_repair,store,workflow
sys.path.insert(0,str(Path(store.__file__).resolve().parents[1]))
from platform_supervisor import repair as delivery

MIGRATION='202611010004_platform_repair_recovery_contract.sql'


def main():
    previous.main();f.report.update(protocol='platform-repair-recovery-contract-v1',passed=False)
    q=f.sql_text
    def js(sql,role=None):
        value=f.query(sql,role=role);return json.loads(value) if value else None
    def expect(value):
        if not value:raise AssertionError('Recovery contract invariant failed.')
    def check(name,fn):f.check(name,lambda:(fn() or dict(passed=True)))
    def preserved():return f.query("select jsonb_build_object('tasks',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_tasks t),'repairs',(select jsonb_agg(to_jsonb(r) order by id) from research_autonomy_repairs r),'turns',(select jsonb_agg(to_jsonb(t) order by id) from research_autonomy_turns t),'calls',(select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c),'budgets',(select jsonb_agg(to_jsonb(b) order by category) from autonomy_budget_categories b))")
    before=preserved();raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
    link=js("select jsonb_build_object('platform',l.platform_task_id,'task',r.task_id,'study',r.study_id,'dispatch',r.dispatch_id) from platform_assessment_repair_links l join platform_assessment_blockers b on b.id=l.blocker_id join research_queued_dispatch_reconciliations r on r.task_id=b.assessment_task_id and r.study_id=b.study_id where not exists(select 1 from research_autonomy_repairs a where a.task_id=r.task_id) limit 1")
    expect(link)
    def packet():return js('select public.platform_repair_context_data('+q(link['platform'])+')')
    contract=packet()['recovery_contract'];queued=contract['queued_admission']
    check('contract migration preserves every original task repair turn call and budget',lambda:expect(preserved()==before))
    def schema():
        expect(contract['version']=='platform-repair-recovery-contract-v1')
        expect(queued['read']['order']=='created_at.asc,dispatch_id.asc' and 'id' not in queued['read']['actual_columns'])
        expect(set(queued['read']['columns'])<=set(queued['read']['actual_columns']))
        definition=f.query("select pg_get_functiondef('public.research_model_reconcile_queued(uuid,text)'::regprocedure)")
        expect(queued['reconcile']['definition'].strip()==definition.strip())
        expect(workflow.digest(queued['reconcile']['definition'].encode())==queued['reconcile']['sha256'])
        expect(queued['permissions']==dict(service_select=True,browser_select=False,service_mutation=False,browser_reconcile=False))
        expect(queued['constraints'] and queued['triggers'])
        expect(delivery.recovery_contract(packet())==contract)
        for role in ('anon','authenticated','service_role'):
            for fn in ('platform_repair_recovery_contract()','platform_repair_context_data_before_contract_v3(uuid)','platform_repair_context_data(uuid)'):
                expect(f.query('select has_function_privilege('+q(role)+','+q('public.'+fn)+",'EXECUTE')")=='f')
    check('installed definitions schema and access contract are exact and privately fenced',schema)
    operations=[];diagnosis_document={}
    def transport(path,method='GET',body=None,public=False,raw=False):
        parsed=urlsplit(path)
        if parsed.path!='/rest/v1/research_queued_dispatch_reconciliations':return f.transport(path,method,body,public,raw)
        # Only HTTP encoding is substituted. The actual client projection,
        # filters and ORDER BY execute against the migrated PostgreSQL table.
        expect(method=='GET' and body is None and not public and not raw)
        params=dict(parse_qsl(parsed.query));columns=params.pop('select').split(',');order=params.pop('order');limit=int(params.pop('limit'))
        allowed=queued['read']['actual_columns'];expect(set(columns)<=set(allowed) and 0<limit<=1000)
        ordering=[]
        for entry in order.split(','):
            column,direction=entry.split('.');expect(column.replace('_','').isalnum() and direction in ('asc','desc'));ordering.append(column+' '+direction)
        filters=[]
        for key,value in params.items():
            expect(key in ('study_id','task_id','dispatch_id') and value.startswith('eq.'));filters.append(key+'='+q(value[3:]))
        operations.append(dict(path=parsed.path,order=order))
        return js("select coalesce(json_agg(r),'[]') from (select "+','.join(columns)+' from research_queued_dispatch_reconciliations'+(' where '+' and '.join(filters) if filters else '')+' order by '+','.join(ordering)+' limit '+str(limit)+')r','service_role')
    def actual_diagnosis():
        with patch.object(store,'request',side_effect=transport):
            task=store.rows('autonomy_tasks',dict(study_id='eq.'+link['study'],id='eq.'+link['task'],limit=2))[0]
            document=autonomous_repair.diagnose(task,dict(category='implementation'))
        expect(document['waiting'] is False and document['validated'] is False)
        expect(any(r['id']==link['dispatch'] and r['kind']=='atomic-unclaimed-dispatch' for r in document['reconciled_dispatches']))
        expect(operations and all(o['order']=='created_at.asc,dispatch_id.asc' for o in operations))
        diagnosis_document.update(document)
        # Confirm the original production query actually fails on this schema.
        f.rejects(lambda:transport('/rest/v1/research_queued_dispatch_reconciliations?select=dispatch_id&order=created_at.asc,id.asc&limit=2'))
    check('actual diagnosis reads immutable proof through real client SQL ordering without HTTP 400',actual_diagnosis)
    def diagnoses():
        repair=js('select to_jsonb(r) from research_autonomy_repairs r where task_id='+q(link['task'])+' limit 1')
        if not repair:
            # Seed a synthetic active incident in this isolated database. Do
            # not modify any earlier terminal fixture or its immutable evidence.
            with patch.object(store,'request',side_effect=transport):task=store.rows('autonomy_tasks',dict(study_id='eq.'+link['study'],id='eq.'+link['task'],limit=2))[0]
            incident=workflow.canonical(dict(version='autonomous-repair-v1',reason='Synthetic persistence lookup failure',stage='building')).decode()
            ident=f.uid()
            f.query('insert into research_autonomy_repairs(id,study_id,task_id,version,category,original_stage,incident_raw,incident_sha256,original_context,state,revision,evidence,reason) values('+','.join([q(ident),q(link['study']),q(link['task']),q('autonomous-repair-v1'),q('implementation'),q('building'),q(incident),q(workflow.digest(incident.encode())),f.sql_json(task['context']),q('diagnosing'),'1',f.sql_json({}),q('Synthetic diagnosis')])+')')
            repair=js('select to_jsonb(r) from research_autonomy_repairs r where id='+q(ident))
        artifact=f.uid();raw=workflow.canonical(diagnosis_document);sha=workflow.digest(raw);size=len(raw)
        f.files['/storage/v1/object/research-workflow-raw/'+link['study']+'/'+sha]=raw
        f.query('insert into research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at) values('+','.join([q(artifact),q(link['study']),q(sha),str(size),q(link['study']+'/'+sha),q('application/json'),f.sql_json(dict(kind='autonomous-repair-diagnosis',version='autonomous-repair-v1')),'clock_timestamp()'])+')')
        initial=packet()['evidence_revision']
        evidence=dict(diagnosis_document,diagnosis=dict(artifact_id=artifact,sha256=sha,byte_count=size))
        f.query('update research_autonomy_repairs set revision=revision+1,evidence='+f.sql_json(evidence)+' where id='+q(repair['id']))
        f.query('insert into research_autonomy_repair_events(repair_id,study_id,task_id,revision,state,details) select id,study_id,task_id,revision,state,evidence from research_autonomy_repairs where id='+q(repair['id']))
        after=packet();expect(after['current_diagnoses'][0]['id']==artifact)
        expect(after['artifacts'][0]['id']==artifact and len(after['artifacts'])<=12 and after['evidence_revision']!=initial)
        expect(packet()['evidence_revision']==after['evidence_revision'])
    check('latest controller diagnosis is delivered even without task context pointer and changes evidence once',diagnoses)
    f.report['passed']=True;path=f.DIRECTORY/'repair-contract-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),provider_calls=0,production_mutations=0)))


if __name__=='__main__':
    try:main()
    except Exception as error:
        f.report.update(passed=False,error_type=type(error).__name__,error=str(error));(f.DIRECTORY/'repair-contract-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n');raise
