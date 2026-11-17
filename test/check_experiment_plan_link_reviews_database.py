"""Reviewed duplicate claim links; original failures stay immutable. Local only."""
import copy
import json
import subprocess
import check_paper_dependencies_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'
    code = """import {duplicatedClaimFixture} from './tests/support/experiment-plan-link-review-fixture.mjs';
import {reviewExperimentPlanLinks} from './lib/paper-experiment-plan-review.ts';
const f=duplicatedClaimFixture();Object.assign(f.row.request,{model:'gpt-5.4-mini-2026-03-17',reasoning:{effort:'low'},max_output_tokens:16000});console.log(JSON.stringify({...f,expected:reviewExperimentPlanLinks(f.row,f.keep)}));"""
    fixture = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, capture_output=True, text=True, check=True).stdout)
    tables = ['research_experiment_plans', 'research_experiment_plan_events', 'research_paper_intakes', 'research_experiment_plan_prompt_uses']

    def snapshots():
        return {table: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + table + ' t') for table in tables}

    before = snapshots()
    migration = (f.ROOT / 'database/202611150001_experiment_plan_link_reviews.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert before == snapshots()

    def prepare(plan, response_status='completed'):
        study = f.uid()
        f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Duplicate link software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role')
        f.query("update research_paper_intakes set status='ready',breakdown=" + f.sql_json(fixture['row']['confirmed_breakdown']) + ',reserved_cents=100,model_calls=1 where study_id=' + q(study))
        revision = int(f.query('select revision from research_paper_intakes where study_id=' + q(study)))
        def rpc(operation, payload):
            return json.loads(f.query('select research_experiment_plan(' + q(operation) + ',' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(payload) + ')', role='service_role'))
        row = rpc('confirm', dict(intake_revision=revision, confirmed_breakdown=fixture['row']['confirmed_breakdown'], request=fixture['row']['request']))
        response = dict(id='resp_' + study.replace('-', ''), status=response_status, output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(plan))])])
        rpc('submitted', dict(token=row['submit_token'], response_id=response['id'], response=dict(id=response['id'], status='queued')))
        failed = rpc('failed', dict(token=row['submit_token'], response=response, reason=fixture['row']['reason']))
        return study, failed

    study, original = prepare(fixture['plan'])
    payload = dict(review_id=f.uid(), base_revision=original['revision'], keep_validation_steps=fixture['keep'], reason='Synthetic software review: retain the final H3 evaluation and untag its measurement prerequisite.', reviewer_type='AI')

    def review(data, study=study, actor=f.ACTOR, role='service_role'):
        return json.loads(f.query('select research_review_experiment_plan_links(' + q(actor) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(data) + ')', role=role))

    for role in ['anon', 'authenticated']:
        f.rejects(lambda role=role: review(payload, role=role))
        f.rejects(lambda role=role: f.query('select * from research_experiment_plan_link_reviews', role=role))
    f.rejects(lambda: review(payload, actor=f.OTHER))
    for change in [lambda p: p.update(base_revision=p['base_revision']+1), lambda p: p.update(keep_validation_steps=[]), lambda p: p['keep_validation_steps'][0].update(step=1), lambda p: p['keep_validation_steps'].append(p['keep_validation_steps'][0]), lambda p: p.update(plan=fixture['plan'])]:
        bad = copy.deepcopy(payload)
        change(bad)
        f.rejects(lambda bad=bad: review(bad))
    counts = snapshots()
    saved = review(payload)
    assert saved['plan'] == fixture['expected']['plan'] and saved['changes'] == fixture['expected']['changes'], 'SQL and JS reviewed projections must match'
    assert counts == snapshots(), 'Original call, failure, prompt and intake remain unchanged'
    assert json.loads(f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study))) == original
    assert review(payload) == saved
    assert f.query("select count(*) from research_audit_events where study_id=" + q(study) + " and action='review-experiment-plan-links'") == '1'
    conflict = copy.deepcopy(payload)
    conflict['reason'] = 'Changed review identity'
    f.rejects(lambda: review(conflict))
    conflict['review_id'] = f.uid()
    f.rejects(lambda: review(conflict))
    for role in ['anon', 'authenticated', 'service_role']:
        f.rejects(lambda role=role: f.query('update research_experiment_plan_link_reviews set reason=\'changed\' where study_id=' + q(study), role=role))
        f.rejects(lambda role=role: f.query('delete from research_experiment_plan_link_reviews where study_id=' + q(study), role=role))
    f.rejects(lambda: f.query('update research_experiment_plan_link_reviews set reason=\'changed\' where study_id=' + q(study)))
    f.rejects(lambda: f.query("update research_experiment_plans set status='processing' where study_id=" + q(study)))
    for mutation in ['unknown source', 'incomplete response']:
        bad = copy.deepcopy(fixture['plan'])
        if mutation == 'unknown source':
            bad['experiments'][0]['stages'][1]['steps'][0]['source_refs'] = ['access-999']
        invalid_study, invalid = prepare(bad, 'incomplete' if mutation == 'incomplete response' else 'completed')
        invalid_payload = dict(payload, review_id=f.uid(), base_revision=invalid['revision'])
        f.rejects(lambda: review(invalid_payload, study=invalid_study))
    f.query("select research_delete_assessment(" + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid)', role='service_role')
    f.rejects(lambda: review(payload))
    for table in ['research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, checks=['idempotent additive migration', 'JS/SQL reviewed projection parity', 'only explicitly selected duplicate annotations change', 'original failed call, response, confirmation, events and limits unchanged', 'owner and private role guards', 'stale, incomplete, unrelated and conflicting reviews rejected', 'immutable idempotent review and audit record', 'deleted assessment review denied', 'no model or experiment dispatch'])))


if __name__ == '__main__':
    main()
