"""Bounded granular plans and immutable annotation recovery. Local Postgres only."""
import json
import subprocess
import check_terminal_commands_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'
    code = """import {hierarchyBreakdown,hierarchyPlanCases,maximumHierarchyPlan} from './tests/support/hierarchical-plan-cases.mjs';
import {validateExperimentPlan} from './lib/paper-experiment-plan.ts';
import {experimentPlanRequest} from './lib/paper-experiment-plan-model.ts';
import {duplicatedClaimFixture} from './tests/support/experiment-plan-link-review-fixture.mjs';
import {reviewExperimentPlanLinks} from './lib/paper-experiment-plan-review.ts';
const breakdown=hierarchyBreakdown(),cases=hierarchyPlanCases().map(c=>{let js_valid=true;try{validateExperimentPlan(c.plan,breakdown);}catch{js_valid=false;}return{...c,js_valid};});
const {row}=duplicatedClaimFixture(),plan=maximumHierarchyPlan(30);
Object.assign(plan.experiments[0].stages[0].steps[0],{title:'Measure idle RTT',instructions:'Measure and retain idle RTT samples before the final H3 evaluation.',source_refs:['validate-3','experiment-1'],validation_ref:'validate-3'});
row.response.output[0].content[0].text=JSON.stringify(plan);
const keep=[{claim_ref:'validate-3',experiment:1,stage:4,step:6}];
console.log(JSON.stringify({breakdown,cases,row,plan,keep,expected:reviewExperimentPlanLinks(row,keep)}));"""
    fixture = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, capture_output=True, text=True, check=True).stdout)
    tables = ['research_paper_intakes', 'research_experiment_plans', 'research_experiment_plan_events', 'research_experiment_plan_link_reviews', 'research_experiment_plan_prompt_uses', 'research_paper_prompt_versions', 'research_terminal_commands', 'research_terminal_command_events']

    def snapshots():
        return {table: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + table + ' t') for table in tables}

    study = f.uid()
    f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Granular plan software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role')
    f.query("update research_paper_intakes set status='ready',breakdown=" + f.sql_json(fixture['breakdown']) + ',reserved_cents=100,model_calls=1 where study_id=' + q(study))
    revision = int(f.query('select revision from research_paper_intakes where study_id=' + q(study)))

    def rpc(operation, payload):
        return json.loads(f.query('select research_experiment_plan(' + q(operation) + ',' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(payload) + ')', role='service_role'))

    row = rpc('confirm', dict(intake_revision=revision, confirmed_breakdown=fixture['breakdown'], request=fixture['row']['request']))
    response = dict(id='resp_' + study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['plan']))])])
    rpc('submitted', dict(token=row['submit_token'], response_id=response['id'], response=dict(id=response['id'], status='queued')))
    original = rpc('failed', dict(token=row['submit_token'], response=response, reason=fixture['row']['reason']))
    payload = dict(review_id=f.uid(), base_revision=original['revision'], keep_validation_steps=fixture['keep'], reason='Retain the final H3 evaluation; its earlier RTT action collects supporting measurements.', reviewer_type='AI')

    def review():
        return json.loads(f.query('select research_review_experiment_plan_links(' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(payload) + ')', role='service_role'))

    # Establish that this repair needs the capacity update as well as link review.
    f.rejects(review)
    before = snapshots()
    migration = (f.ROOT / 'database/202611160002_granular_experiment_plan_capacity.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert before == snapshots(), 'Capacity migration must never rewrite historical rows or calls'
    for case in fixture['cases']:
        actual = f.query('select research_valid_experiment_plan(' + f.sql_json(case['plan']) + ',' + f.sql_json(fixture['breakdown']) + ')') == 't'
        assert actual == case['valid'] == case['js_valid'], case['name']
    for role in ['anon', 'authenticated']:
        for function in ['research_valid_flat_experiment_plan', 'research_valid_experiment_plan']:
            f.rejects(lambda role=role, function=function: f.query('select ' + function + "('{}','{}')", role=role))
    saved = review()
    assert saved['plan'] == fixture['expected']['plan'] and saved['changes'] == fixture['expected']['changes']
    assert review() == saved
    assert json.loads(f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study))) == original
    assert f.query('select count(*) from research_experiment_plan_events where study_id=' + q(study)) == '3'
    assert sum(len(stage['steps']) for stage in saved['plan']['experiments'][0]['stages']) == 30

    # Command admission consumes the exact reviewed 30-action source, while
    # leaving undefined scientific acceptance rules blocked. No model is called.
    command_code = """import {readFileSync} from 'node:fs';
import {terminalCommandsRequest} from './lib/paper-terminal-commands-model.ts';
import {terminalActionRefs,terminalBlockedActionRefs} from './lib/paper-terminal-commands.ts';
const f=JSON.parse(readFileSync(0,'utf8'));console.log(JSON.stringify({request:terminalCommandsRequest(f.study,1,f.plan,f.breakdown),refs:terminalActionRefs(f.plan,1),blocked:terminalBlockedActionRefs(f.plan,1,f.breakdown)}));"""
    commands = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', command_code], cwd=front, input=json.dumps(dict(study=study, plan=saved['plan'], breakdown=fixture['breakdown'])), capture_output=True, text=True, check=True).stdout)
    assert json.loads(f.query('select research_terminal_action_refs(' + f.sql_json(saved['plan']) + ',1)')) == commands['refs']
    assert json.loads(f.query('select research_terminal_blocked_refs(' + f.sql_json(saved['plan']) + ',1,' + f.sql_json(fixture['breakdown']) + ')')) == commands['blocked'] == ['1.4.4', '1.4.6']
    admitted = json.loads(f.query("select research_terminal_commands_control('generate'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,1,' + f.sql_json(dict(request=commands['request'], command_layout='per-step-v1')) + ')', role='service_role'))
    assert admitted['source_plan'] == saved['plan'] and admitted['deadline_at'] == original['deadline_at']
    assert admitted['plan_revision'] == original['revision'] and admitted['model_calls'] == 1 and admitted['reserved_cents'] == 200
    assert json.loads(f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study))) == original
    for table in ['research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, cases=len(fixture['cases']), checks=['nonrewriting idempotent capacity migration', 'JS/SQL parity through 64 hierarchical actions; legacy flat bound retained', '30-action immutable review preserves all action text and original call', 'reviewed plan binds terminal admission to the exact original revision', 'undefined claim criteria remain blocked', 'private grants, original deadlines and budgets retained', 'no provider or experiment execution'])))


if __name__ == '__main__':
    main()
