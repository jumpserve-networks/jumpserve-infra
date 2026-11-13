"""Hierarchical plans in isolated local Postgres; no remote DB, provider or worker calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import check_paper_evidence_reviews_database as previous
import check_research_ideas_database as f


def main():
    # Also exercises v1/v2 migrations and reviewed evidence before the new DDL.
    previous.main()
    q=f.sql_text
    front=f.ROOT.parent/'jumpserve-front-end'
    code="""import {hierarchyBreakdown,hierarchyPlanCases} from './tests/support/hierarchical-plan-cases.mjs';
import {hierarchicalImplementationPlan} from './tests/support/implementation-plan-fixture.mjs';
import {validateExperimentPlan} from './lib/paper-experiment-plan.ts';
import {experimentPlanRequest} from './lib/paper-experiment-plan-model.ts';
const breakdown=hierarchyBreakdown(),cases=hierarchyPlanCases().map(c=>{let js_valid=true;try{validateExperimentPlan(c.plan,breakdown);}catch{js_valid=false;}return{...c,js_valid};});
console.log(JSON.stringify({breakdown,plan:hierarchicalImplementationPlan(),request:experimentPlanRequest(breakdown),cases}));"""
    result=subprocess.run(['node','--import','./scripts/lib/register-typescript.mjs','--input-type=module','-e',code],cwd=front,capture_output=True,text=True,check=True)
    fixture=json.loads(result.stdout)
    study=f.uid()
    f.query("select research_paper_intake('reserve',"+q(f.ACTOR)+"::uuid,"+q(study)+"::uuid,"+f.sql_json(dict(filename='Hierarchy software fixture.pdf',sha256='a'*64,byte_count=100))+")",role='service_role')
    f.query("update research_paper_intakes set status='ready',breakdown="+f.sql_json(fixture['breakdown'])+",reserved_cents=100,model_calls=1 where study_id="+q(study))
    original=json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study)))
    payload=dict(intake_revision=original['revision'],confirmed_breakdown=fixture['breakdown'],request=fixture['request'])

    def rpc(op,data=None,actor=f.ACTOR,role='service_role'):
        return json.loads(f.query('select research_experiment_plan('+q(op)+','+q(actor)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(data or {})+')',role=role))

    # An older schema rejects before confirmation, reservation or provider use.
    f.rejects(lambda:rpc('confirm',payload))
    assert f.query('select count(*) from research_experiment_plans where study_id='+q(study))=='0'
    tables=['research_paper_intakes','research_experiment_plans','research_experiment_plan_events','research_paper_breakdown_reviews','research_paper_prompt_versions']
    def snapshots():return {table:f.query('select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,\'[]\')) from '+table+' t') for table in tables}
    before=snapshots()
    migration=(f.ROOT/'database/202611120001_hierarchical_experiment_plans.sql').read_text()
    f.query(migration);f.query(migration)
    assert snapshots()==before

    for case in fixture['cases']:
        actual=f.query('select research_valid_experiment_plan('+f.sql_json(case['plan'])+','+f.sql_json(fixture['breakdown'])+')')=='t'
        assert actual==case['valid']==case['js_valid'],case['name']
    # A pre-migration in-flight v2 call still finishes against its frozen format.
    legacy=json.loads(f.query("select to_jsonb(p) from research_experiment_plans p where status='submitting' and request->'text'->'format'->>'name'='paper_experiment_steps_v2' order by study_id limit 1"))
    def old_rpc(op,data):return json.loads(f.query('select research_experiment_plan('+q(op)+','+q(f.ACTOR)+'::uuid,'+q(legacy['study_id'])+'::uuid,'+f.sql_json(data)+')',role='service_role'))
    old_rpc('submitted',dict(token=legacy['submit_token'],response_id='resp_legacy_layout',response=dict(id='resp_legacy_layout',status='queued')))
    old_finish=dict(token=legacy['submit_token'],response_id='resp_legacy_layout',response=dict(id='resp_legacy_layout',status='completed'),plan=fixture['plan'])
    f.rejects(lambda:old_rpc('finish',old_finish))
    old_finish['plan']=fixture['cases'][0]['plan']
    assert old_rpc('finish',old_finish)['status']=='ready'
    for role in ['anon','authenticated']:
        f.rejects(lambda:rpc('confirm',payload,role=role))
        for table in ['research_experiment_plans','research_experiment_plan_events','research_experiment_plan_prompt_uses']:
            f.rejects(lambda:f.query('select * from '+table,role=role))
        f.rejects(lambda:f.query('select research_valid_flat_experiment_plan(\'{}\',\'{}\')',role=role))
    f.rejects(lambda:rpc('confirm',payload,actor=f.OTHER))
    f.query('update autonomy_budget_categories set max_model_calls=1')
    f.rejects(lambda:rpc('confirm',payload))
    f.query('update autonomy_budget_categories set max_model_calls=-1,max_spend_cents=199')
    f.rejects(lambda:rpc('confirm',payload))
    f.query('update autonomy_budget_categories set max_spend_cents=-1')
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows=list(pool.map(lambda _:rpc('confirm',payload),range(3)))
    assert sum(row['admitted'] for row in rows)==1
    admitted=rows[0];token=admitted['submit_token']
    assert admitted['request']==fixture['request'] and admitted['model_calls']==1 and admitted['reserved_cents']==100
    assert admitted['deadline_at']==original['deadline_at']
    assert json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study)))==original
    rpc('submitted',dict(token=token,response_id='resp_hierarchy',response=dict(id='resp_hierarchy',status='queued')))
    response=dict(id='resp_hierarchy',status='completed',output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(fixture['plan']))])])
    finish=dict(token=token,response_id='resp_hierarchy',response=response,plan=fixture['plan'])
    # A v3 admission cannot finish with a valid but flat historical projection.
    f.rejects(lambda:rpc('finish',dict(finish,plan=fixture['cases'][0]['plan'])))
    bad=json.loads(json.dumps(fixture['plan']));bad['experiments'][0]['stages'][-1]['steps'].pop()
    f.rejects(lambda:rpc('finish',dict(finish,plan=bad)))
    saved=rpc('finish',finish)
    assert saved['status']=='ready' and saved['plan']==fixture['plan'] and saved['response']==response
    assert rpc('confirm',payload)['admitted'] is False
    catalog=f.query('select jsonb_build_object(\'instructions\',instructions,\'template\',input_template,\'config\',request_configuration) from research_paper_prompt_versions where id in(select prompt_version_id from research_experiment_plan_prompt_uses where study_id='+q(study)+')')
    assert 'invented mean goodputs are 30' not in catalog and 'paper_experiment_steps_v3' in catalog
    f.rejects(lambda:f.query("update research_experiment_plans set plan='{}' where study_id="+q(study)))
    f.rejects(lambda:f.query('delete from research_experiment_plan_events where study_id='+q(study)))
    for table in ['research_autonomy_workflows','research_autonomy_tasks','research_model_dispatches','research_queue_jobs']:
        assert f.query('select count(*) from '+table+' where study_id='+q(study))=='0'
    assert json.loads(f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid)',role='service_role'))==dict(id=study,deleted=True)
    assert json.loads(f.query('select plan from research_experiment_plans where study_id='+q(study)))==fixture['plan']
    print(json.dumps(dict(passed=True,database=f.DATABASE,cases=len(fixture['cases']),checks=['idempotent nonrewriting migration','legacy and hierarchical JS/SQL parity','bounded stages and atomic actions','distinct claim and source coverage','original response and hierarchy persistence','owner/RLS and original budget/deadline','single concurrent admission','generic prompt privacy','deletion preserves evidence','no worker or experiment dispatch'])))


if __name__=='__main__':main()
