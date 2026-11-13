"""Fixed local Postgres confirmation/planning regressions. No remote DB or model calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import check_research_ideas_database as f


def main():
    f.bootstrap(include_deleted_at=False)
    q=f.sql_text
    f.query("create schema auth;create table auth.users(id uuid primary key,is_anonymous boolean);create table auth.identities(user_id uuid references auth.users(id),provider text)")
    f.query("insert into auth.users values("+q(f.ACTOR)+",false),("+q(f.OTHER)+",false);insert into auth.identities values("+q(f.ACTOR)+",'google'),("+q(f.OTHER)+",'email')")
    f.query("create table public.autonomy_budget_categories(category text primary key,max_spend_cents integer,max_model_calls integer,revision integer);insert into public.autonomy_budget_categories values('research_assessment',-1,-1,1)")
    source=(f.ROOT/'database/202610310003_category_budgets.sql').read_text()
    for name in ['autonomy_assessment_budget_terms','autonomy_budget_allows']:
        start=source.index('create function public.'+name+'(')
        end=source.index('$$;',source.index('$$',start)+2)+3
        f.query(source[start:end])
    for name in ['202611110001_next_paper_intake.sql','202611110002_assessment_deletion.sql','202611110003_paper_prompt_catalog.sql','202611110004_confirmed_experiment_plans.sql']:
        f.query((f.ROOT/'database'/name).read_text())
    front=f.ROOT.parent/'jumpserve-front-end'
    result=subprocess.run(['node','--import','./scripts/lib/register-typescript.mjs','--input-type=module','-e',"import {breakdownFixture,planFixture,legacyPlanRequestFixture} from './tests/support/experiment-plan-fixture.mjs';import {planningInput} from './lib/paper-experiment-plan.ts';console.log(JSON.stringify({breakdown:breakdownFixture(),plan:planFixture(),request:legacyPlanRequestFixture(planningInput(breakdownFixture()))}));"],cwd=front,capture_output=True,text=True,check=True)
    fixture=json.loads(result.stdout)

    def intake(empty=False,status='ready',actor=f.ACTOR):
        study=f.uid()
        row=json.loads(f.query("select public.research_paper_intake('reserve',"+q(actor)+"::uuid,"+q(study)+"::uuid,"+f.sql_json(dict(filename='Planning fixture.pdf',sha256='a'*64,byte_count=100))+")",role='service_role'))
        b=json.loads(json.dumps(fixture['breakdown']))
        if empty:b['sections']['experiment']=[]
        f.query("update research_paper_intakes set status="+q(status)+",breakdown="+f.sql_json(b)+",reserved_cents=100,model_calls=1 where study_id="+q(study))
        row=json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study)))
        return study,dict(intake_revision=row['revision'],confirmed_breakdown=b,request=None if empty else fixture['request'])

    def rpc(op,study,payload=None,actor=f.ACTOR,role='service_role'):
        return json.loads(f.query('select research_experiment_plan('+q(op)+','+q(actor)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(payload or {})+')',role=role))

    study,payload=intake()
    original=f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))
    f.rejects(lambda:rpc('finish',study))
    f.rejects(lambda:rpc('confirm',study,payload,actor=f.OTHER))
    for role in ['anon','authenticated']:
        f.rejects(lambda:rpc('confirm',study,payload,role=role))
        for table in ['research_experiment_plans','research_experiment_plan_events','research_experiment_plan_prompt_uses']:
            f.rejects(lambda:f.query('select * from '+table,role=role))
    f.rejects(lambda:rpc('confirm',study,dict(payload,intake_revision=999)))
    for mutate in [lambda p:p['confirmed_breakdown']['sections']['access'][0].update(quote='Invented quote'),lambda p:p['confirmed_breakdown']['sections']['experiment'][0].update(page=2),lambda p:p['confirmed_breakdown']['sections']['data'].append(p['confirmed_breakdown']['sections']['data'][0]),lambda p:p['request'].update(input='{}')]:
        bad=json.loads(json.dumps(payload));mutate(bad);f.rejects(lambda:rpc('confirm',study,bad))
    f.query('update autonomy_budget_categories set max_model_calls=1')
    f.rejects(lambda:rpc('confirm',study,payload)) # phase one already reserved a call
    f.query('update autonomy_budget_categories set max_model_calls=-1,max_spend_cents=199')
    f.rejects(lambda:rpc('confirm',study,payload))
    f.query('update autonomy_budget_categories set max_spend_cents=-1')
    with ThreadPoolExecutor(max_workers=3) as pool: rows=list(pool.map(lambda _:rpc('confirm',study,payload),range(3)))
    assert sum(r['admitted'] for r in rows)==1
    row=rows[0];token=row['submit_token']
    assert row['model_calls']==1 and row['reserved_cents']==100
    assert f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))==original
    assert f.query('select p.deadline_at=i.deadline_at from research_experiment_plans p join research_paper_intakes i using(study_id) where study_id='+q(study))=='t'
    assert f.query('select count(*) from research_experiment_plan_events where study_id='+q(study))=='1'
    assert f.query('select count(*) from research_experiment_plan_prompt_uses where study_id='+q(study))=='1'
    catalog=f.query('select jsonb_build_object(\'instructions\',instructions,\'input_template\',input_template,\'request_configuration\',request_configuration) from research_paper_prompt_versions')
    assert 'Original access quote' not in catalog and 'experiment-original' not in catalog
    assert 'confirmed_experiment_details_with_source_quotes' in catalog
    for table in ['research_autonomy_workflows','research_autonomy_tasks','research_model_dispatches','research_queue_jobs']:
        assert f.query('select count(*) from '+table+' where study_id='+q(study))=='0'
    f.rejects(lambda:f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid)',role='service_role'))
    f.rejects(lambda:rpc('submitted',study,dict(token=f.uid(),response_id='resp_plan')))
    row=rpc('submitted',study,dict(token=token,response_id='resp_plan',response=dict(id='resp_plan',status='queued')))
    assert rpc('submitted',study,dict(token=token,response_id='resp_plan'))['revision']==row['revision']
    f.rejects(lambda:rpc('submitted',study,dict(token=token,response_id='resp_other')))
    finish=dict(token=token,response_id='resp_plan',response=dict(id='resp_plan',status='completed'),plan=fixture['plan'])
    f.rejects(lambda:rpc('finish',study,dict(finish,plan=dict(experiments=[]))))
    invalid=json.loads(json.dumps(finish));invalid['plan']['experiments'][0]['steps'][0]['source_refs']=['data-999']
    f.rejects(lambda:rpc('finish',study,invalid))
    assert rpc('finish',study,finish)['status']=='ready'
    assert rpc('confirm',study,payload)['admitted'] is False
    f.rejects(lambda:f.query("update research_experiment_plans set confirmed_breakdown='{}' where study_id="+q(study)))
    f.rejects(lambda:f.query('delete from research_experiment_plan_events'))
    # Successful plans permit owner deletion while retaining both phases.
    assert json.loads(f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid)',role='service_role'))==dict(id=study,deleted=True)
    assert f.query('select count(*) from research_experiment_plans where study_id='+q(study))=='1'
    edited,edited_payload=intake()
    edited_payload['confirmed_breakdown']['sections']['access']=[]
    edited_payload['confirmed_breakdown']['sections']['data'][0]['description']='Owner-corrected units and storage description'
    edited_payload['request']=json.loads(json.dumps(fixture['request']))
    edited_payload['request']['input']=f.query('select research_experiment_plan_input('+f.sql_json(edited_payload['confirmed_breakdown'])+')')
    changed=rpc('confirm',edited,edited_payload)
    assert changed['confirmed_breakdown']['sections']['access']==[]
    assert changed['confirmed_breakdown']['sections']['data'][0]['description']=='Owner-corrected units and storage description'
    assert f.query('select count(*) from research_paper_prompt_versions')=='1' # input text never changes template identity
    empty,empty_payload=intake(empty=True)
    ready=rpc('confirm',empty,empty_payload)
    assert ready['status']=='ready' and ready['model_calls']==0 and ready['plan']==dict(experiments=[])
    assert f.query('select count(*) from research_experiment_plan_prompt_uses where study_id='+q(empty))=='0'
    pending,pending_payload=intake(status='uploaded')
    f.rejects(lambda:rpc('confirm',pending,pending_payload))
    non_google,non_google_payload=intake(actor=f.OTHER)
    f.rejects(lambda:rpc('confirm',non_google,non_google_payload,actor=f.OTHER))
    unknown,unknown_payload=intake()
    admitted=rpc('confirm',unknown,unknown_payload)
    assert rpc('uncertain',unknown,dict(token=admitted['submit_token'],reason='Lost original response'))['status']=='uncertain'
    assert rpc('confirm',unknown,unknown_payload)['admitted'] is False
    f.rejects(lambda:rpc('cancel',unknown,dict(token=admitted['submit_token'],response=dict(status='cancelled'))))
    f.rejects(lambda:f.query('update research_studies set deleted_at=clock_timestamp() where id='+q(unknown)))
    # Explicit cancellation must refer to the retained provider and terminal state.
    stop,stop_payload=intake();admitted=rpc('confirm',stop,stop_payload);token=admitted['submit_token']
    rpc('submitted',stop,dict(token=token,response_id='resp_stop',response=dict(id='resp_stop',status='queued')))
    f.rejects(lambda:rpc('cancel',stop,dict(token=token,response=dict(id='resp_stop',status='in_progress'))))
    assert rpc('cancel',stop,dict(token=token,response=dict(id='resp_stop',status='cancelled'),reason='Owner cancelled'))['status']=='cancelled'
    f.query('update research_studies set deleted_at=clock_timestamp() where id='+q(stop))
    f.rejects(lambda:rpc('confirm',stop,stop_payload))
    assert f.query('select count(*) from research_experiment_plans where study_id='+q(stop))=='1'
    print(json.dumps(dict(passed=True,database=f.DATABASE,checks=['explicit Google owner confirmation','four-section source preservation','stale review rejection','original deadline and cumulative budget','one admission under concurrency','immutable confirmation and event history','private records and generic prompt catalogue','verified output coverage','no execution/worker dispatch','empty experiments need no model call','uncertain and cancelled call fences','deletion retains evidence'])))


if __name__=='__main__':main()
