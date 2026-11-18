"""Qualify three repair/re-review rounds on the isolated native Postgres fixture.
No remote writes, provider inference, Docker or generated experiment execution.
"""
import copy
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import check_paper_quality_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    tables = ['research_paper_intakes', 'research_experiment_plans', 'research_experiment_scripts',
              'research_paper_quality_workflows', 'research_paper_quality_calls',
              'research_paper_quality_events', 'research_paper_quality_prompt_uses']
    def fingerprints():
        return {t: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + t + ' t') for t in tables}
    before = fingerprints()
    guards = f.query("select jsonb_object_agg(proname,md5(prosrc)) from pg_proc where pronamespace='public'::regnamespace and (proname like 'research_quality_%' or proname in ('research_assert_quality_budget','research_valid_quality_candidate','research_valid_quality_review'))")
    migration = (f.ROOT / 'database/202611180002_paper_quality_review_rounds.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert fingerprints() == before
    assert guards == f.query("select jsonb_object_agg(proname,md5(prosrc)) from pg_proc where pronamespace='public'::regnamespace and (proname like 'research_quality_%' or proname in ('research_assert_quality_budget','research_valid_quality_candidate','research_valid_quality_review'))")
    assert f.query("select has_function_privilege('service_role','research_paper_quality_control(text,uuid,uuid,jsonb)','execute') and not has_function_privilege('anon','research_paper_quality_control(text,uuid,uuid,jsonb)','execute') and not has_function_privilege('authenticated','research_paper_quality_control(text,uuid,uuid,jsonb)','execute')") == 't'
    front = f.ROOT.parent / 'jumpserve-front-end'
    calls = 0
    with_context = '--with-context' in sys.argv
    def fixture(payload):
        result = subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', 'tests/support/paper-quality-database.mjs'], cwd=front, input=json.dumps(payload), capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)
    def quality(w, op, payload=None):
        if with_context and op == 'admit':
            payload = dict(payload or {}, review_context_version='paper-quality-context-v1')
        return json.loads(f.query('select research_paper_quality_control('+q(op)+','+q(f.ACTOR)+'::uuid,'+q(w['id'])+'::uuid,'+f.sql_json(payload or {})+')', role='service_role'))
    def load(study, step):
        return json.loads(f.query('select research_quality_result(id) from research_paper_quality_workflows where study_id='+q(study)+' and step='+str(step)))
    def draft(w, kind, revise=False):
        nonlocal calls
        calls += 1
        return fixture(dict(mode=kind, workflow=w, response_id='resp_round_fixture_'+str(calls), revise=revise))
    def admit(w, pending):
        saved = quality(w, 'admit', dict(source_sha256=pending['source_sha256']))
        assert saved['admitted'] is True
        position = 2*w['round']+(2 if w['status'] == 'repair_pending' else 1)
        assert saved['call']['position'] == position
        assert saved['call']['kind'] == ('repair' if position % 2 == 0 else 'review')
        assert saved['phase'] == ('repairing' if position % 2 == 0 else 'checking' if w['step'] == 4 else 'reviewing')
        identity = dict(call_id=saved['call']['id'], token=saved['call']['submit_token'])
        if with_context and 'review_context' in saved:
            assert saved['call']['policy_snapshot']['quality_context'] is True
            assert json.loads(pending['request']['input'])['review_context'] == saved['review_context']
            bad = copy.deepcopy(pending['request']); body = json.loads(bad['input']); body.pop('review_context'); bad['input'] = json.dumps(body)
            f.rejects(lambda: quality(w, 'request', dict(identity, request=bad)))
            bad = copy.deepcopy(pending['request']); body = json.loads(bad['input']); body['review_context']['generation_instructions'] = 'Changed contract'; bad['input'] = json.dumps(body)
            f.rejects(lambda: quality(w, 'request', dict(identity, request=bad)))
            if w['round']:
                bad = copy.deepcopy(pending['request']); body = json.loads(bad['input']); body['review_context']['finding_ledger'] = []; bad['input'] = json.dumps(body)
                f.rejects(lambda: quality(w, 'request', dict(identity, request=bad)))
        quality(w, 'request', dict(identity, request=pending['request']))
        quality(w, 'submitted', dict(identity, response_id=pending['response']['id'], response=dict(id=pending['response']['id'], status='queued')))
        return identity
    def complete(w, pending, identity):
        payload = dict(identity, response=pending['response'], checks=pending['checks'])
        if 'candidate' in pending:
            payload['candidate'] = pending['candidate']
            operation = 'repaired'
        else:
            payload['review'] = pending['review']
            operation = 'reviewed'
            if with_context and pending['review'].get('resolutions'):
                for resolutions in [[], [dict(r, status='open') for r in pending['review']['resolutions']]]:
                    bad = copy.deepcopy(payload); bad['review'] = dict(decision='pass', summary='Forged approval with unresolved history.', findings=[], resolutions=resolutions)
                    bad['response']['output'][-1]['content'][0]['text'] = json.dumps(bad['review'])
                    f.rejects(lambda: quality(w, operation, bad))
        saved = quality(w, operation, payload)
        assert quality(w, operation, payload)['status'] == saved['status']
        return saved, operation, payload
    def review(w, revise=False):
        pending = draft(w, 'review', revise)
        return complete(w, pending, admit(w, pending))[0]
    def repair(w):
        pending = draft(w, 'repair')
        return complete(w, pending, admit(w, pending))[0]
    def source(step):
        study = f.uid()
        intake = json.loads(f.query('select research_paper_intake(\'reserve\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(filename='Review rounds '+study+'.pdf', sha256=hashlib.sha256(study.encode()).hexdigest(), byte_count=100))+')', role='service_role'))
        data = fixture(dict(mode='initial', study=study, source_id=intake['source_id'], text_artifact_id=intake['text_artifact_id']))
        response = data['intake_response']; response['id'] = 'resp_original_'+study.replace('-', '')
        f.query('update research_paper_intakes set status=\'ready\',request='+f.sql_json(data['intake_request'])+',paper_text='+f.sql_json(data['paper'])+',breakdown='+f.sql_json(data['breakdown'])+',provider_response_id='+q(response['id'])+',response='+f.sql_json(response)+',reserved_cents=100,model_calls=1 where study_id='+q(study))
        if step == 2:
            return load(study, 2)
        b = review(load(study, 2))['candidate']['breakdown']
        data = fixture(dict(mode='initial', study=study, source_id=intake['source_id'], text_artifact_id=intake['text_artifact_id'], breakdown=b))
        plan = json.loads(f.query('select research_experiment_plan(\'confirm\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(intake_revision=int(f.query('select revision from research_paper_intakes where study_id='+q(study))), confirmed_breakdown=b, request=data['plan_request']))+')', role='service_role'))
        def finish(function, token, value, key, extra=''):
            response = dict(id='resp_'+key+'_'+study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(value))])])
            for op, payload in [('submitted', dict(token=token, response_id=response['id'], response=dict(id=response['id'], status='queued'))), ('finish', dict(token=token, response_id=response['id'], response=response, **{key: value}))]:
                f.query('select '+function+'('+q(op)+','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+extra+f.sql_json(payload)+')', role='service_role')
        finish('research_experiment_plan', plan['submit_token'], data['plan'], 'plan')
        if step == 3:
            return load(study, 3)
        plan = review(load(study, 3))['candidate']
        data = fixture(dict(mode='initial', study=study, source_id=intake['source_id'], text_artifact_id=intake['text_artifact_id'], breakdown=b, plan=plan))
        scripts = json.loads(f.query('select research_experiment_scripts_control(\'generate\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,1,'+f.sql_json(dict(request=data['scripts_request']))+')', role='service_role'))
        finish('research_experiment_scripts_control', scripts['submit_token'], data['scripts'], 'command_set', '1,')
        return load(study, 4)
    if with_context:
        # Freeze a legacy request before upgrading, then reconcile that very
        # response after the migration. No rewrite or replacement call is needed.
        legacy = source(2); pending = draft(legacy, 'review'); identity = admit(legacy, pending)
        immutable_tables = tables + ['research_paper_prompt_versions']
        def all_fingerprints():
            return {t: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + t + ' t') for t in immutable_tables}
        before_context = all_fingerprints()
        fixed_guards = ['research_assert_quality_budget', 'research_valid_quality_candidate', 'research_quality_checker_code', 'research_quality_source', 'research_quality_canonical', 'research_quality_history']
        guard_sql = 'select jsonb_object_agg(proname,md5(prosrc)) from pg_proc where pronamespace=\'public\'::regnamespace and proname in ('+','.join(q(n) for n in fixed_guards)+')'
        before_guards = f.query(guard_sql)
        migration = (f.ROOT / 'database/202611180003_paper_quality_review_context.sql').read_text()
        f.query(migration); f.query(migration)
        assert all_fingerprints() == before_context and f.query(guard_sql) == before_guards
        w = complete(legacy, pending, identity)[0]
        assert w['status'] == 'approved' and w['call']['request'] == pending['request']
        assert 'resolutions' not in w['review']
        # The old deployed app can still admit/finish during the migration-first
        # rollout. New app admissions opt in to the strict context requirement.
        rollout = source(2); old_row = copy.deepcopy(rollout); old_row.pop('review_context')
        old_pending = draft(old_row, 'review')
        saved = json.loads(f.query('select research_paper_quality_control(\'admit\','+q(f.ACTOR)+'::uuid,'+q(rollout['id'])+'::uuid,'+f.sql_json(dict(source_sha256=old_pending['source_sha256']))+')', role='service_role'))
        assert saved['call']['policy_snapshot']['quality_context'] is False
        old_identity = dict(call_id=saved['call']['id'], token=saved['call']['submit_token'])
        quality(rollout, 'request', dict(old_identity, request=old_pending['request']))
        quality(rollout, 'submitted', dict(old_identity, response_id=old_pending['response']['id'], response=dict(id=old_pending['response']['id'], status='queued')))
        assert complete(rollout, old_pending, old_identity)[0]['status'] == 'approved'
        # The context read is owner-checked and read-only, and helpers remain private.
        history = all_fingerprints(); quality(w, 'context'); assert all_fingerprints() == history
        for role in ['anon', 'authenticated']:
            f.rejects(lambda role=role: f.query('select research_paper_quality_control(\'context\','+q(f.ACTOR)+'::uuid,'+q(w['id'])+'::uuid)', role=role))
        f.rejects(lambda: f.query('select research_paper_quality_control(\'context\','+q(f.OTHER)+'::uuid,'+q(w['id'])+'::uuid)', role='service_role'))
        for signature in ['research_quality_review_context(research_paper_quality_workflows)', 'research_valid_quality_resolutions(jsonb,jsonb)', 'research_valid_quality_review_v1(jsonb)']:
            assert f.query('select not has_function_privilege(\'service_role\','+q(signature)+',\'execute\') and not has_function_privilege(\'anon\','+q(signature)+',\'execute\')') == 't'
    for step in [2, 3, 4]:
        for passing in [False, True]:
            w = source(step)
            original = copy.deepcopy(w['source_json'])
            deadline = w['deadline_at']
            w = review(w, True)
            for round_number in range(1, 4):
                assert w['status'] == 'repair_pending'
                previous_candidate = copy.deepcopy(w['candidate'])
                w = repair(w)
                assert w['round'] == round_number and w['status'] == 'review_pending'
                assert w['candidate'] != previous_candidate
                if with_context:
                    context = w['review_context']
                    assert context['previous_candidate'] == previous_candidate
                    assert len(context['finding_ledger']) == round_number
                    assert [e['key'] for e in context['finding_ledger']] == ['review-'+str(p)+':zero-delay' for p in range(1, 2*round_number, 2)]
                    assert context['generation_instructions'] == w['original_request']['instructions']
                    assert context['generation_input'] == w['original_request']['input']
                    breakdown = w['source_json']['confirmed_breakdown']
                    expected_refs = {section+'-'+str(i+1): d['id'] for section, details in breakdown['sections'].items() for i,d in enumerate(details)} if breakdown else {}
                    assert context['reference_map'] == expected_refs
                w = review(w, not (passing and round_number == 3))
            assert w['status'] == ('approved' if passing else 'needs_attention')
            assert w['source_json'] == original and w['deadline_at'] == deadline
            assert f.query('select count(*) from research_paper_quality_calls where workflow_id='+q(w['id'])) == '7'
            assert quality(w, 'admit', dict(source_sha256='0'*64))['admitted'] is False
            f.rejects(lambda: f.query('update research_paper_quality_workflows set round=0 where id='+q(w['id'])))
    # Admission at repair round two is concurrent, deduplicated and reconcilable.
    w = review(source(3), True); w = repair(w); w = review(w, True)
    assert w['round'] == 1
    pending = draft(w, 'repair')
    with ThreadPoolExecutor(max_workers=3) as pool:
        admitted = list(pool.map(lambda _: quality(w, 'admit', dict(source_sha256=pending['source_sha256'])), range(3)))
    assert sum(a['admitted'] for a in admitted) == 1
    c = next(a['call'] for a in admitted if a['admitted'])
    assert c['position'] == 4
    identity = dict(call_id=c['id'], token=c['submit_token'])
    quality(w, 'request', dict(identity, request=pending['request']))
    uncertain = quality(w, 'uncertain', dict(identity, reason='Lost acknowledgement at repair round two'))
    assert uncertain['status'] == 'uncertain'
    assert quality(w, 'admit', dict(source_sha256=pending['source_sha256']))['admitted'] is False
    f.rejects(lambda: quality(w, 'cancel', dict(identity)))
    quality(w, 'submitted', dict(identity, response_id=pending['response']['id'], response=dict(id=pending['response']['id'], status='queued')))
    w, old_op, old_payload = complete(w, pending, identity)
    w = review(w, True); assert w['round'] == 2 and w['status'] == 'repair_pending'
    policies = json.loads(f.query('select jsonb_agg(to_jsonb(t)) from autonomy_budget_categories t'))
    f.query('update autonomy_budget_categories set max_model_calls=8')  # two generation + one earlier-stage review + five current-stage calls
    pending = draft(w, 'repair')
    f.rejects(lambda: quality(w, 'admit', dict(source_sha256=pending['source_sha256'])))
    for policy in policies:
        f.query('update autonomy_budget_categories set max_model_calls='+str(policy['max_model_calls'])+' where category='+q(policy['category']))
    current = quality(w, 'admit', dict(source_sha256=pending['source_sha256']))
    assert current['call']['position'] == 6
    assert quality(w, old_op, old_payload)['call']['id'] == current['call']['id']
    identity = dict(call_id=current['call']['id'], token=current['call']['submit_token'])
    quality(w, 'request', dict(identity, request=pending['request']))
    quality(w, 'submitted', dict(identity, response_id=pending['response']['id'], response=dict(id=pending['response']['id'], status='queued')))
    f.rejects(lambda: f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(w['study_id'])+'::uuid)', role='service_role'))
    stopped = quality(w, 'cancel', dict(identity, response=dict(id=pending['response']['id'], status='cancelled'), reason='Confirmed cancellation of third repair'))
    assert stopped['status'] == 'cancelled' and stopped['round'] == 2
    print(json.dumps(dict(passed=True, database=f.DATABASE, review_context=with_context, checks=['idempotent capacity migration without row/event rewrites', 'three repairs and four reviews for each step', 'approve or stop after seven calls', 'latest candidate and original frozen inputs retained', 'private roles and all source/sandbox guards preserved', 'later-round concurrent deduplication', 'uncertain later call reconciled without replay', 'stale completed acknowledgement cannot replace a newer call', 'original aggregate budgets and deadline retained', 'third-repair cancellation and deletion guard'] + (['legacy response reconciliation', 'database-owned original contract and canonical aliases', 'cumulative findings and prior candidate retained', 'forged context and incomplete resolutions rejected'] if with_context else []))))


if __name__ == '__main__':
    main()
