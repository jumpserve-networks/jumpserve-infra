"""Qualify managed paper repairs locally; no Docker, remote writes or inference."""
import copy
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import check_paper_quality_rounds_database as previous
import check_research_ideas_database as f


def main():
    if '--with-context' not in sys.argv:
        sys.argv.append('--with-context')
    previous.main()
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'

    def fixture(payload, agent=False):
        script = 'paper-agent-database.mjs' if agent else 'paper-quality-database.mjs'
        result = subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', 'tests/support/'+script], cwd=front, input=json.dumps(payload), capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)

    original_fields = ['id', 'workflow_id', 'study_id', 'owner_id', 'position', 'kind', 'source_sha256', 'submit_token', 'request', 'provider_response_id', 'response', 'policy_snapshot', 'created_at']
    original = f.query('select md5(jsonb_agg(jsonb_build_array('+','.join('c.'+x for x in original_fields)+') order by id)::text) from research_paper_quality_calls c')
    for name in ['202611180004_managed_paper_agents.sql', '202611180005_paper_background_continuation.sql']:
        migration = (f.ROOT/'database'/name).read_text()
        f.query(migration)
        f.query(migration)
    assert original == f.query('select md5(jsonb_agg(jsonb_build_array('+','.join('c.'+x for x in original_fields)+') order by id)::text) from research_paper_quality_calls c')

    def quality(w, op, payload=None):
        return json.loads(f.query('select research_paper_quality_control('+q(op)+','+q(f.ACTOR)+'::uuid,'+q(w['id'])+'::uuid,'+f.sql_json(payload or {})+')', role='service_role'))

    def native(w, op, payload=None, actor=None, role='service_role'):
        return json.loads(f.query('select research_paper_agent_control('+q(op)+','+q(actor or f.ACTOR)+'::uuid,'+q(w['call']['id'])+'::uuid,'+f.sql_json(payload or {})+')', role=role))

    def load(study, step):
        return json.loads(f.query('select research_quality_result(id) from research_paper_quality_workflows where study_id='+q(study)+' and step='+str(step)))

    sequence = 0

    def review(w, revise=False):
        nonlocal sequence
        sequence += 1
        pending = fixture(dict(mode='review', workflow=w, response_id='resp_managed_review_'+str(sequence), revise=revise))
        w = quality(w, 'admit', dict(source_sha256=pending['source_sha256'], review_context_version='paper-quality-context-v1'))
        identity = dict(call_id=w['call']['id'], token=w['call']['submit_token'])
        quality(w, 'request', dict(identity, request=pending['request']))
        quality(w, 'submitted', dict(identity, response_id=pending['response']['id'], response=dict(id=pending['response']['id'], status='queued')))
        return quality(w, 'reviewed', dict(identity, response=pending['response'], review=pending['review'], checks=pending['checks']))

    def seed():
        study = f.uid()
        intake = json.loads(f.query('select research_paper_intake(\'reserve\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(filename='Managed fixture.pdf', sha256=hashlib.sha256(study.encode()).hexdigest(), byte_count=100))+')', role='service_role'))
        data = fixture(dict(mode='initial', study=study, source_id=intake['source_id'], text_artifact_id=intake['text_artifact_id']))
        response = data['intake_response'];response['id'] = 'resp_original_'+study.replace('-', '')
        f.query('update research_paper_intakes set status=\'ready\',request='+f.sql_json(data['intake_request'])+',paper_text='+f.sql_json(data['paper'])+',breakdown='+f.sql_json(data['breakdown'])+',provider_response_id='+q(response['id'])+',response='+f.sql_json(response)+',reserved_cents=100,model_calls=1 where study_id='+q(study))
        return study, intake, data

    def admit(w):
        body = dict(source_sha256=fixture(dict(mode='checks', workflow=dict(w, agent=dict(candidate=w['candidate']))), True)['source_sha256'], review_context_version='paper-quality-context-v1', repair_runtime='managed-agents-v1')
        with ThreadPoolExecutor(max_workers=2) as pool:
            admitted = list(pool.map(lambda _: quality(w, 'admit', body), range(2)))
        assert sum(item['admitted'] for item in admitted) == 1
        w = next(item for item in admitted if item['admitted'])
        assert w['call']['provider_type'] == 'managed_agent' and w['agent']['candidate'] == w['candidate']
        request = fixture(dict(mode='request', workflow=w), True)
        w = native(w, 'request', dict(request=request))
        assert w['agent']['request'] == request
        f.rejects(lambda: native(w, 'request', dict(request=dict(request, environment=dict(type='openai_hosted')))))
        session = dict(id='sess_'+w['call']['id'].replace('-', ''), metadata=request['metadata'], agent=dict(model='gpt-5.4', reasoning=dict(effort='medium'), multi_agent=dict(enabled=False)), environment=dict(type='none'), status='in_progress', required_actions=[])
        # Lost creation acknowledgement remains uncertain, never a replacement call.
        w = native(w, 'uncertain', dict(reason='Fixture uncertain submission'))
        f.rejects(lambda: native(w, 'cancelled', dict(reason='No provider ID')))
        w = native(w, 'submitted', dict(session=session))
        f.rejects(lambda: quality(w, 'submitted', dict(call_id=w['call']['id'],token=w['call']['submit_token'],response_id='resp_wrong_runtime',response=dict(id='resp_wrong_runtime',status='queued'))))
        assert native(w, 'submitted', dict(session=session))['agent']['provider_session_id'] == session['id']
        fake = dict(session, id='sess_wrong')
        f.rejects(lambda: native(w, 'observed', dict(session=fake)))
        return w, session

    def action(w, session, name, args, evaluated):
        nonlocal sequence
        sequence += 1
        turn = dict(id='turn_'+w['call']['id'].replace('-', ''), session_id=session['id'], subagent_id=None, status='waiting')
        pending = dict(type='function_call', turn_id=turn['id'], call_id='call_'+str(sequence), name=name, arguments=args)
        session = dict(session, status='requires_action', required_actions=[pending])
        w = native(w, 'observed', dict(session=session, turn=turn))
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: native(w, 'action_claim', dict(action=pending)), range(2)))
        assert sum(claim['admitted'] for claim in claims) == 1
        claim = next(claim for claim in claims if claim['admitted'])
        payload = dict(action_id=claim['id'], lease_token=claim['lease_token'], candidate_version=claim['candidate_version'], **evaluated)
        f.rejects(lambda: native(w, 'action_result', dict(payload, candidate_version=999)))
        w = native(w, 'action_result', payload)
        assert native(w, 'action_ack', dict(turn_id=turn['id'],call_id=pending['call_id'])) is True
        assert native(w, 'action_result', payload)['agent']['candidate_version'] == w['agent']['candidate_version']
        again = native(w, 'action_claim', dict(action=pending))
        assert not again['admitted'] and again['result'] == evaluated['result']
        return w, session, turn

    def repair(w):
        w, session = admit(w)
        for role in ['anon', 'authenticated']:
            f.rejects(lambda role=role: native(w, 'limits', role=role))
        f.rejects(lambda: native(w, 'limits', actor=f.OTHER))
        patch = fixture(dict(mode='patch', workflow=w), True)
        args = patch.pop('arguments')
        w, session, turn = action(w, session, 'apply_patch', args, patch)
        assert w['candidate'] != w['agent']['candidate']  # Repair stays private and unapproved.
        checks = fixture(dict(mode='checks', workflow=w), True)
        completed_session = dict(session, status='idle', required_actions=[])
        completed_turn = dict(turn, status='completed')
        final = dict(session=completed_session, turn=completed_turn, items=[], checks=checks)
        f.rejects(lambda: native(w, 'completed', final))  # Must actually run final validator.
        evaluated = fixture(dict(mode='validator', workflow=w), True)
        w, session, turn = action(w, session, 'run_validator', {}, evaluated)
        final.update(session=dict(session, status='idle', required_actions=[]), turn=dict(turn, status='completed'))
        w = native(w, 'observed', dict(session=final['session'],turn=final['turn']))
        item=dict(id='msg_'+w['call']['id'],type='message',content=[dict(type='output_text',text='Fixture repair complete; independent review is still required.')])
        manifest=native(w,'history_item',dict(item=item))
        assert native(w,'history_item',dict(item=item)) == manifest
        f.rejects(lambda:native(w,'history_item',dict(item=dict(item,content=[]))))
        final['items']=[manifest]
        native(w, 'controller_checks', dict(checks=checks))
        w = native(w, 'completed', final)
        assert w['status'] == 'review_pending' and w['round'] == 1 and w['agent']['status'] == 'completed'
        assert w['review_context']['previous_candidate'] == w['agent']['initial_candidate']
        assert native(w, 'completed', final)['round'] == 1
        f.rejects(lambda: f.query('update research_paper_quality_calls set provider_type=\'responses\' where id='+q(w['call']['id'])))
        return review(w)

    study, intake, data = seed()
    originals = {'intake': f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))}
    w = review(load(study, 2), True)
    f.query("update autonomy_budget_categories set max_spend_cents=10000 where category='research_assessment'")
    f.rejects(lambda: admit(w))
    assert f.query('select count(*) from research_paper_agent_sessions where study_id='+q(study)) == '0'
    f.query("update autonomy_budget_categories set max_spend_cents=-1 where category='research_assessment'")
    w = repair(w);assert w['status'] == 'approved'
    assert originals['intake'] == f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))
    breakdown = w['candidate']['breakdown']
    data = fixture(dict(mode='initial', study=study, source_id=intake['source_id'], text_artifact_id=intake['text_artifact_id'], breakdown=breakdown))
    plan = json.loads(f.query('select research_experiment_plan(\'confirm\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(intake_revision=int(f.query('select revision from research_paper_intakes where study_id='+q(study))), confirmed_breakdown=breakdown, request=data['plan_request']))+')', role='service_role'))

    def finish(function, token, value, key, extra=''):
        response = dict(id='resp_'+key+'_'+study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(value))])])
        for op, payload in [('submitted', dict(token=token, response_id=response['id'], response=dict(id=response['id'], status='queued'))), ('finish', dict(token=token, response_id=response['id'], response=response, **{key:value}))]:
            f.query('select '+function+'('+q(op)+','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+extra+f.sql_json(payload)+')', role='service_role')
    finish('research_experiment_plan', plan['submit_token'], data['plan'], 'plan')
    saved_plan = f.query('select to_jsonb(p) from research_experiment_plans p where study_id='+q(study))
    w = repair(review(load(study, 3), True));assert w['status'] == 'approved'
    assert saved_plan == f.query('select to_jsonb(p) from research_experiment_plans p where study_id='+q(study))
    data = fixture(dict(mode='initial', study=study, source_id=intake['source_id'], text_artifact_id=intake['text_artifact_id'], breakdown=breakdown, plan=w['candidate']))
    scripts = json.loads(f.query('select research_experiment_scripts_control(\'generate\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,1,'+f.sql_json(dict(request=data['scripts_request']))+')', role='service_role'))
    finish('research_experiment_scripts_control', scripts['submit_token'], data['scripts'], 'command_set', '1,')
    w = repair(review(load(study, 4), True));assert w['status'] == 'approved' and w['checks']['sandbox']['result']['passed']
    assert f.query('select count(*) from research_paper_agent_prompt_uses where study_id='+q(study)) == '3'
    catalog = f.query('select jsonb_agg(to_jsonb(p)) from research_paper_prompt_versions p join research_paper_agent_prompt_uses u on u.prompt_version_id=p.id where u.study_id='+q(study))
    assert study not in catalog and 'Fixture uncertain' not in catalog and 'sess_' not in catalog
    # Cancellation requires confirmed provider terminal evidence, not HTTP acceptance.
    cancel_study, _, _ = seed()
    pending, session = admit(review(load(cancel_study, 2), True))
    pending = native(pending, 'cancel_requested', dict(reason='Fixture owner cancellation'))
    f.rejects(lambda: native(pending, 'cancelled', dict(session=session, turn=dict(id='turn_cancel', session_id=session['id'], subagent_id=None, status='in_progress'))))
    cancelled = native(pending, 'cancelled', dict(session=dict(session, status='idle'), turn=dict(id='turn_cancel', session_id=session['id'], subagent_id=None, status='cancelled'), items=[]))
    assert cancelled['status'] == 'cancelled'
    cleanup_id=cancelled['call']['id']
    cleanup=lambda op,payload={}:json.loads(f.query('select research_paper_agent_cleanup_control('+q(op)+','+q(cleanup_id)+'::uuid,'+f.sql_json(payload)+')',role='service_role'))
    assert cleanup('context')['done'] is False
    f.rejects(lambda:cleanup('record',dict(receipt=dict(id=session['id']))))
    cleanup('record',dict(receipt=dict(id=session['id'],deleted=True)))
    assert cleanup('context')['done'] is True
    for table in ['research_paper_agent_sessions', 'research_paper_agent_actions', 'research_paper_agent_events', 'research_paper_agent_items', 'research_paper_agent_prompt_uses', 'research_paper_background_leases', 'research_paper_agent_cleanups']:
        for role in ['anon', 'authenticated']:
            f.rejects(lambda role=role,table=table: f.query('select * from '+table, role=role))
    for role in ['anon', 'authenticated']:
        f.rejects(lambda role=role: f.query("select research_paper_background_control('claim','{\"limit\":2}')", role=role))
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _:json.loads(f.query("select research_paper_background_control('claim','{\"limit\":2}')", role='service_role')), range(2)))
    keys = [item['work_key'] for batch in claims for item in batch]
    assert len(keys) == len(set(keys))
    f.report['managed_paper_agents'] = dict(passed=True, steps=[2,3,4], original_sources_preserved=True, independent_reviews_required=True, finite_limits_fail_closed=True, concurrent_admission_and_actions=True, durable_result_replay=True, cancellation_confirmed=True, database_writes='isolated local fixture only', provider_calls=0)
    (f.DIRECTORY/'managed-paper-agents.json').write_text(json.dumps(f.report['managed_paper_agents'], indent=2)+'\n')
    print(json.dumps(f.report['managed_paper_agents']))


if __name__ == '__main__':
    main()
