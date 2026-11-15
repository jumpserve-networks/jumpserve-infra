"""Section dependency persistence in isolated local Postgres; no remote or model calls."""
import copy
import hashlib
import json
import subprocess
import check_hierarchical_experiment_plans_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'
    code = """import {dependencyBreakdown,dependencyCases} from './tests/support/paper-dependency-fixture.mjs';
import {breakdownFixture} from './tests/support/experiment-plan-fixture.mjs';
import {implementationBreakdown} from './tests/support/implementation-plan-fixture.mjs';
import {evidencePaper} from './tests/support/paper-evidence-fixture.mjs';
import {validatePaperBreakdown} from './lib/research-paper-breakdown.ts';
import {planningInput} from './lib/paper-experiment-plan.ts';
import {experimentPlanRequest} from './lib/paper-experiment-plan-model.ts';
const breakdown=dependencyBreakdown(),cases=dependencyCases().map(c=>{let js_valid=true;try{validatePaperBreakdown(c.breakdown);}catch{js_valid=false;}return{...c,js_valid};});
console.log(JSON.stringify({breakdown,cases,legacy:breakdownFixture(),legacy_input:planningInput(breakdownFixture()),input:planningInput(breakdown),request:experimentPlanRequest(breakdown),review:implementationBreakdown(),paper:evidencePaper}));"""
    fixture = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, capture_output=True, text=True, check=True).stdout)
    tables = ['research_paper_intakes', 'research_paper_breakdown_reviews', 'research_experiment_plans', 'research_paper_prompt_versions']

    def snapshots():
        return {table: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + table + ' t') for table in tables}

    before = snapshots()
    migration = (f.ROOT / 'database/202611140001_paper_detail_dependencies.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert before == snapshots(), 'Migration must not rewrite retained evidence'
    for example in fixture['cases']:
        sql = 'select research_assert_paper_dependencies(' + f.sql_json(example['breakdown']) + ')'
        if example['valid']:
            f.query(sql)
        else:
            f.rejects(lambda sql=sql: f.query(sql))
        assert example['js_valid'] == example['valid'], example['name']
    for breakdown, expected in [(fixture['breakdown'], fixture['input']), (fixture['legacy'], fixture['legacy_input'])]:
        actual = json.loads(f.query('select research_experiment_plan_input(' + f.sql_json(breakdown) + ')'))
        assert actual == expected, 'SQL and JS planning projections must match'

    def reserve(breakdown):
        study = f.uid()
        row = json.loads(f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Dependency software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role'))
        breakdown = copy.deepcopy(breakdown)
        breakdown.update(source_id=row['source_id'], text_artifact_id=row['text_artifact_id'])
        f.query('update research_paper_intakes set status=\'ready\',breakdown=' + f.sql_json(breakdown) + ',paper_text=' + f.sql_json(fixture['paper']) + ',reserved_cents=100,model_calls=1 where study_id=' + q(study))
        row = json.loads(f.query('select to_jsonb(i) from research_paper_intakes i where study_id=' + q(study)))
        return study, row, breakdown

    study, intake, breakdown = reserve(fixture['breakdown'])
    request = copy.deepcopy(fixture['request'])
    request['input'] = json.dumps(fixture['input'])
    payload = dict(intake_revision=intake['revision'], confirmed_breakdown=breakdown, request=request)

    def plan_rpc(data, actor=f.ACTOR):
        return json.loads(f.query("select research_experiment_plan('confirm'," + q(actor) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(data) + ')', role='service_role'))

    orphan = copy.deepcopy(payload)
    orphan['confirmed_breakdown']['sections']['access'].pop(0)
    # Even an adversarial exact request projection must not admit orphaned scope.
    orphan['request']['input'] = f.query('select research_experiment_plan_input(' + f.sql_json(orphan['confirmed_breakdown']) + ')')
    f.rejects(lambda: plan_rpc(orphan))
    assert f.query('select count(*) from research_experiment_plans where study_id=' + q(study)) == '0'
    f.rejects(lambda: plan_rpc(payload, f.OTHER))
    plan = plan_rpc(payload)
    assert plan['confirmed_breakdown'] == breakdown
    assert plan['request']['input'] == request['input']
    assert plan_rpc(payload)['admitted'] is False

    review_study, review_intake, original = reserve(fixture['review'])
    instructions = 'Synthetic software correction: retain a supported dependent access detail.'
    corrected = copy.deepcopy(original)
    child = copy.deepcopy(corrected['sections']['access'][0])
    child.update(id='dependent-access', description='Use a single TCP stream on those hosts.', depends_on=[child['id']])
    corrected['sections']['access'].append(child)
    corrected['policy_sha256'] = hashlib.sha256(instructions.encode()).hexdigest()
    correction = dict(review_id=f.uid(), base_revision=review_intake['revision'], reason='Retain section dependency.', reviewer_type='AI', instructions=instructions, breakdown=corrected)

    def review_rpc(data):
        return json.loads(f.query('select research_review_paper_breakdown(' + q(f.ACTOR) + '::uuid,' + q(review_study) + '::uuid,' + f.sql_json(data) + ')', role='service_role'))

    reviewed = review_rpc(correction)
    assert reviewed['breakdown']['sections']['access'][1]['depends_on'] == child['depends_on']
    assert json.loads(f.query('select breakdown from research_paper_intakes where study_id=' + q(review_study))) == original
    cyclic = copy.deepcopy(correction)
    cyclic.update(review_id=f.uid(), base_revision=reviewed['revision'])
    cyclic['breakdown']['sections']['access'][0]['depends_on'] = ['dependent-access']
    f.rejects(lambda: review_rpc(cyclic))
    assert f.query('select count(*) from research_paper_breakdown_reviews where study_id=' + q(review_study)) == '1'
    for role in ['anon', 'authenticated']:
        f.rejects(lambda role=role: f.query('select research_assert_paper_dependencies(' + f.sql_json(breakdown) + ')', role=role))
    for table in ['research_autonomy_tasks', 'research_queue_jobs', 'research_model_dispatches']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, cases=len(fixture['cases']), checks=['idempotent migration without record rewrites', 'JS/SQL graph and planning input parity', 'orphan scope rejection and owner checks', 'dependency persistence through confirmation and versioned review', 'cycles rejected before storage', 'legacy input compatibility', 'no model or experiment dispatch'])))


if __name__ == '__main__':
    main()
