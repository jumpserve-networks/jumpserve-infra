"""Versioned paper-evidence reviews against isolated local Postgres, no model or production writes."""
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
    for name in ['202611110001_next_paper_intake.sql','202611110002_assessment_deletion.sql','202611110003_paper_prompt_catalog.sql','202611110004_confirmed_experiment_plans.sql','202611110005_reviewed_paper_evidence.sql','202611110006_phase_one_review_model.sql']:
        f.query((f.ROOT/'database'/name).read_text())
    front=f.ROOT.parent/'jumpserve-front-end'
    result=subprocess.run(['node','--import','./scripts/lib/register-typescript.mjs','--input-type=module','-e',"import {evidencePaper,evidenceBreakdown,evidencePlan} from './tests/support/paper-evidence-fixture.mjs';import {PAPER_REVIEW_INSTRUCTIONS} from './lib/paper-breakdown-review.ts';import {experimentPlanRequest} from './lib/paper-experiment-plan-model.ts';import {sha256,paperModelRequest} from './lib/paper-intake-model.ts';const original=evidenceBreakdown(),b=structuredClone(original);b.policy_sha256=sha256(PAPER_REVIEW_INSTRUCTIONS);console.log(JSON.stringify({paper:evidencePaper,intake_request:paperModelRequest(evidencePaper),original,breakdown:b,instructions:PAPER_REVIEW_INSTRUCTIONS,request:experimentPlanRequest(b),plan:evidencePlan()}));"],cwd=front,capture_output=True,text=True,check=True)
    fixture=json.loads(result.stdout)
    citations=[dict(page=1,quote=fixture['paper']['pages'][0]['text'][:n]) for n in range(20,32)]
    f.query('select research_assert_paper_citations('+f.sql_json(citations)+','+f.sql_json(fixture['paper'])+')')
    f.rejects(lambda:f.query('select research_assert_paper_citations('+f.sql_json(citations+[dict(page=1,quote=fixture['paper']['pages'][0]['text'][:32])])+','+f.sql_json(fixture['paper'])+')'))

    # Real admission uses the new phase-one model and generic prompt capture,
    # while old model calls, phase-two model and original limits stay unchanged.
    for model in ['gpt-5.4-2026-03-05','gpt-5.4-mini-2026-03-17']:
        admission_study=f.uid()
        reserved=json.loads(f.query("select research_paper_intake('reserve',"+q(f.ACTOR)+"::uuid,"+q(admission_study)+"::uuid,"+f.sql_json(dict(filename='Model admission fixture.pdf',sha256='a'*64,byte_count=100))+")",role='service_role'))
        request=dict(fixture['intake_request'],model=model)
        artifacts=[dict(id=reserved['original_artifact_id'],sha256='a'*64,byte_count=100,storage_path=admission_study+'/'+'a'*64,media_type='application/pdf',provenance=dict(kind='synthetic-test')),dict(id=reserved['text_artifact_id'],sha256='b'*64,byte_count=200,storage_path=admission_study+'/'+'b'*64,media_type='application/json',provenance=dict(kind='synthetic-test'))]
        payload=dict(model_id=model,request=request,paper_text=fixture['paper'],reserved_cents=100,artifacts=artifacts)
        def begin(data):return json.loads(f.query("select research_paper_intake('begin',"+q(f.ACTOR)+"::uuid,"+q(admission_study)+"::uuid,"+f.sql_json(data)+")",role='service_role'))
        f.rejects(lambda:begin(dict(payload,model_id='unapproved-model',request=dict(request,model='unapproved-model'))))
        f.query('update autonomy_budget_categories set max_spend_cents=99')
        f.rejects(lambda:begin(payload))
        f.query('update autonomy_budget_categories set max_spend_cents=-1')
        admitted=begin(payload)
        assert admitted['admitted'] is True and admitted['model_id']==model and admitted['model_calls']==1 and admitted['reserved_cents']==100
        assert admitted['deadline_at']==reserved['deadline_at']
        assert begin(payload)['admitted'] is False
        assert f.query('select count(*) from research_paper_prompt_uses where study_id='+q(admission_study))=='1'

    def intake():
        study=f.uid()
        f.query("select research_paper_intake('reserve',"+q(f.ACTOR)+"::uuid,"+q(study)+"::uuid,"+f.sql_json(dict(filename='Evidence software fixture.pdf',sha256='a'*64,byte_count=100))+")",role='service_role')
        f.query("update research_paper_intakes set status='ready',paper_text="+f.sql_json(fixture['paper'])+",breakdown="+f.sql_json(fixture['original'])+",reserved_cents=100,model_calls=1 where study_id="+q(study))
        row=json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study)))
        return study,row,dict(review_id=f.uid(),base_revision=row['revision'],reason='Source-grounded requested corrections.',reviewer_type='AI',instructions=fixture['instructions'],breakdown=fixture['breakdown'])

    def review(study,payload,actor=f.ACTOR,role='service_role'):
        return json.loads(f.query('select research_review_paper_breakdown('+q(actor)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(payload)+')',role=role))

    study,original,payload=intake()
    f.rejects(lambda:review(study,payload,actor=f.OTHER))
    for role in ['anon','authenticated']:
        f.rejects(lambda:review(study,payload,role=role))
        f.rejects(lambda:f.query('select * from research_paper_breakdown_reviews',role=role))
    for mutate in [lambda p:p.update(base_revision=999),lambda p:p['breakdown'].update(source_id='wrong'),lambda p:p['breakdown']['sections']['experiment'][0]['citations'][1].update(quote='Invented evidence'),lambda p:p['breakdown']['sections']['experiment'][0]['citations'][1].update(page=1),lambda p:p['breakdown']['sections']['validate'][0].update(criterion=None),lambda p:p['breakdown']['sections']['access'][0].update(specification={}),lambda p:p['breakdown']['sections']['experiment'][0].update(specification=None)]:
        bad=json.loads(json.dumps(payload));mutate(bad);f.rejects(lambda:review(study,bad))
    with ThreadPoolExecutor(max_workers=3) as pool: rows=list(pool.map(lambda _:review(study,payload),range(3)))
    assert all(r['id']==payload['review_id'] for r in rows)
    saved=rows[0];assert saved['revision']==original['revision']+1 and saved['model_calls']==0
    assert json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study)))==original
    assert f.query('select count(*) from research_paper_breakdown_reviews where study_id='+q(study))=='1'
    f.rejects(lambda:review(study,dict(payload,review_id=f.uid())))
    f.rejects(lambda:review(study,dict(payload,reviewer_type='human')))
    f.rejects(lambda:f.query("update research_paper_breakdown_reviews set reason='changed'"))
    f.rejects(lambda:f.query('delete from research_paper_breakdown_reviews'))
    catalog=f.query('select jsonb_build_object(\'instructions\',instructions,\'template\',input_template,\'config\',request_configuration) from research_paper_prompt_versions')
    assert 'invented mean goodputs are 30' not in catalog and 'operator_document_review' in catalog
    corrected=saved['breakdown'];request=dict(fixture['request'])
    js_input=json.loads(request['input'])
    assert json.loads(f.query('select research_experiment_plan_input('+f.sql_json(corrected)+')'))==js_input
    plan=fixture['plan'];assert f.query('select research_valid_experiment_plan('+f.sql_json(plan)+','+f.sql_json(corrected)+')')=='t'
    for change in ['missing','duplicate','unlinked','null-source']:
        bad=json.loads(json.dumps(plan))
        if change=='missing':bad['experiments'][0]['steps'].pop()
        if change=='duplicate':bad['experiments'][0]['steps'][2]['validation_ref']='validate-1'
        if change=='unlinked':bad['experiments'][0]['steps'][0]['source_refs']=['experiment-1']
        if change=='null-source':bad['experiments'][0]['steps'][0]['source_refs'].append(None)
        assert f.query('select research_valid_experiment_plan('+f.sql_json(bad)+','+f.sql_json(corrected)+')')=='f'
    def confirm(version,breakdown):
        return json.loads(f.query("select research_experiment_plan('confirm',"+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(intake_revision=version,confirmed_breakdown=breakdown,request=request))+')',role='service_role'))
    f.rejects(lambda:confirm(original['revision'],fixture['original']))
    admitted=confirm(saved['revision'],corrected)
    assert admitted['confirmed_breakdown']==corrected and admitted['deadline_at']==original['deadline_at']
    assert admitted['model_calls']==1 and admitted['reserved_cents']==100
    f.rejects(lambda:review(study,dict(payload,review_id=f.uid(),base_revision=saved['revision'])))
    assert json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study)))==original
    for table in ['research_autonomy_workflows','research_autonomy_tasks','research_model_dispatches','research_queue_jobs']:
        assert f.query('select count(*) from '+table+' where study_id='+q(study))=='0'
    deleted,_,deleted_payload=intake()
    f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(deleted)+'::uuid)',role='service_role')
    f.rejects(lambda:review(deleted,deleted_payload))
    print(json.dumps(dict(passed=True,database=f.DATABASE,checks=['new and legacy pinned model admissions with original limits','private immutable versioned review','exact multi-page citations','distinct claim coverage','original intake and deadline preserved','idempotent concurrent correction','stale and confirmed scope fences','generic prompt catalogue','JS/SQL planning input equality','no worker or experiment dispatch','owner and deletion checks'])))


if __name__=='__main__':main()
