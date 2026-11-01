"""Fair host admission against the complete migrated local PostgreSQL schema.

Synthetic tasks, clocks and transports only; no Docker, provider or cloud calls.
Existing database regressions run unchanged before this migration is installed.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from unittest.mock import patch

import check_persistence_polling_database as previous
import check_research_ideas_database as f
import autonomy
import autonomy_model as model
import model_dispatch as dispatch
import workflow

MIGRATION = '202611010006_platform_repair_fair_scheduling.sql'


def main():
    previous.main()
    f.report.update(protocol='platform-fair-scheduling-v1', passed=False)
    q = f.sql_text

    def js(sql, role=None):
        value = f.query(sql, role=role)
        return json.loads(value) if value else None

    def expect(value):
        if not value:
            raise AssertionError('Fair scheduling invariant failed.')

    def check(name, action):
        f.check(name, lambda: (action() or dict(passed=True)))

    def snapshot():
        tables = dict(tasks='platform_tasks', calls='research_builder_calls',
                      dispatches='research_model_dispatches', turns='research_autonomy_turns',
                      workflows='research_autonomy_workflows', budgets='autonomy_budget_categories')
        return {name: f.query('select jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text) from '+table+' t')
                for name, table in tables.items()}

    before = snapshot()
    raw = (f.ROOT/'database'/MIGRATION).read_bytes()
    f.query(raw.decode())
    f.report['migration_sha256'][MIGRATION] = workflow.digest(raw)
    check('installation preserves every retained task request outcome workflow deadline and budget',
          lambda: expect(snapshot() == before))
    # Retained incomplete originals remain immutable throughout the new cases.
    unknown_before = f.query("select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c where status='unknown'")
    worker = f.uid()
    policy = f.query('select a.policy_sha256 from platform_settings s join platform_authorizations a on a.version=s.authorization_version where s.id')

    def work(operation, task=None, token=None, payload=None, role='service_role'):
        return js('select public.platform_worker('+','.join([
            q(operation), q(worker), q(task)+'::uuid' if task else 'null',
            q(token)+'::uuid' if token else 'null', f.sql_json(payload or {})])+')', role)

    def claim(task=None):
        return work('claim', payload=dict(policy_sha256=policy, **({'only_task': task} if task else {})))

    def heartbeat():
        work('heartbeat', payload=dict(status='ready', reason='Isolated scheduling fixture.'))

    def parent():
        return f.rpc('research_autonomy_control', dict(p_operation='lease', p_actor=None, p_study=None, p_payload={}))

    def study():
        with patch.object(autonomy, 'wake', return_value={}):
            return autonomy.start(f.ACTOR, dict(request_id=f.uid(), autonomous=True,
                paper=dict(title='Synthetic scheduling fixture', paper_url='https://example.org/scheduling.pdf',
                           domain='Software', scope=__doc__)))['id']

    def stop_parent(task):
        autonomy.advance(task, 'waiting', reason='Synthetic turn drained without an external call.', delay=300)

    def task(deadline="clock_timestamp()+interval '1 hour'", **extra):
        ident = f.uid()
        f.query('insert into platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,priority,max_reserved_cents,deadline_at) select '+q(ident)+
                ",(select user_id from platform_operators where role='owner' limit 1),'Synthetic repair scheduling','Test host admission only.',array['jumpserve-networks/jumpserve-back-end'],authorization_version,'platform_repair',0,-1,"+deadline+' from platform_settings where id')
        if extra:
            f.query('update platform_tasks set '+','.join(key+'='+f.sql_json(value) if isinstance(value, dict)
                    else key+'='+q(value) for key, value in extra.items())+' where id='+q(ident))
        return ident

    def checkpoint(leased, status='blocked'):
        return work('checkpoint', leased['id'], leased['lease_token'],
                    dict(status=status, reason='Synthetic durable checkpoint; no provider call.', checkpoint=leased['checkpoint']))

    def clock_after_cooldown():
        f.query("update platform_host_turn set cooldown_until=clock_timestamp()-interval '1 second'")

    def reset():
        # Explicit fixture teardown, never used by the migration or production.
        # Clear only these isolated synthetic task leases; leave all call rows.
        f.query("update platform_tasks set status='blocked',lease_token=null,lease_until=null,checkpoint=checkpoint-'cleanup_unknown';"
                "update research_autonomy_tasks set status='blocked',lease_token=null,lease_until=null;"
                "update platform_host_turn set task_id=null,requested_at=null,expires_at=null,lease_token=null,cooldown_until='-infinity';"
                "update platform_settings set paused=false;"
                "insert into research_runtime_maintenance_releases(hold_id,reason) select id,'Isolated fixture handoff teardown.' from research_runtime_maintenance_holds on conflict do nothing;")
        # Prior race controls retain a synthetic running dispatch. Advance only
        # its isolated lease clock and use the actual RPC to retain it UNKNOWN;
        # never erase the row or manufacture a completed response.
        f.query("update research_model_dispatches set lease_until=clock_timestamp()-interval '1 second' where status='running'")
        expect(dispatch.rpc('claim', {}) is None)
        expect(f.query("select count(*) from research_model_dispatches where status='running'") == '0')
        heartbeat()

    # Previous controls intentionally stop the assessment budget at zero.
    f.query("update autonomy_budget_categories set max_spend_cents=-1,max_model_calls=-1,change_reason='Explicit isolated scheduling fixtures.' where category='research_assessment'")

    def access():
        for role in ('anon', 'authenticated'):
            f.rejects(lambda role=role: f.query('select * from platform_host_turn', role=role))
            f.rejects(lambda role=role: work('claim', payload=dict(policy_sha256=policy), role=role))
        for role in ('anon', 'authenticated', 'service_role'):
            for signature in ('platform_host_task_eligible(uuid)', 'platform_host_reservation_active()',
                              'platform_worker_before_fair_scheduling_v1(text,uuid,uuid,uuid,jsonb)',
                              'research_autonomy_before_fair_scheduling_v1(text,uuid,uuid,jsonb)'):
                expect(f.query('select has_function_privilege('+q(role)+','+q('public.'+signature)+",'EXECUTE')") == 'f')
            f.rejects(lambda role=role: f.query("update platform_host_turn set cooldown_until='-infinity'", role=role))
        reset()
        ident = task()
        prior = f.query('select to_jsonb(h) from platform_host_turn h')
        f.rejects(lambda: work('claim', payload=dict(policy_sha256='0'*64)))
        expect(f.query('select to_jsonb(h) from platform_host_turn h') == prior)
        expect(f.query('select lease_token is null from platform_tasks where id='+q(ident)) == 't')
        # Existing private/native admission RPC remains inaccessible.
        f.rejects(lambda: f.query("select public.research_model_dispatch_before_platform_v1('claim','{}')", role='service_role'))
    check('browser mutation direct delegation and invalid policy cannot bypass host admission', access)

    def drain_and_rotate():
        reset()
        first, second = task(), task()
        study()
        original = parent()
        expect(original is not None)
        expect(claim() is None)
        expiry = f.query('select expires_at from platform_host_turn')
        expect(parent() is None)
        expect(claim() is None and f.query('select expires_at from platform_host_turn') == expiry)
        # A parent admitted BEFORE the reservation can still start/finish its
        # original dispatch. Blocking dispatch claims here would deadlock it.
        prompt = f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
        request = model.request('Synthetic host admission test', dict(task='planning'))
        request['modelId'] = dispatch.MODEL
        turn = autonomy.control(original, 'begin', dict(id=f.uid(), request=request,
            request_raw=workflow.canonical(request).decode(), request_sha256=workflow.digest(workflow.canonical(request)),
            reserved_cents=100, prompt_version_id=prompt, model_id=dispatch.MODEL))
        dispatch.rpc('enqueue', dict(id=turn['id'], study_id=original['study_id'], task_id=original['id'],
            request_raw=turn['request_raw'], request_sha256=turn['request_sha256'], runtime=dispatch.VERSION))
        dispatch.rpc('heartbeat', dict(status='ready', configuration=dict(runtime=dispatch.VERSION, paid_fallback=False)))
        native = dispatch.rpc('claim', {})
        expect(native['id'] == turn['id'] and claim() is None)
        dispatch.rpc('finish', dict(id=turn['id'], token=native['lease_token'], status='failed',
            response_artifact_id=None, response_sha256=None, provenance=dict(provider_calls=0, reason='Explicit synthetic pre-provider failure.')))
        autonomy.control(original, 'finish', dict(id=turn['id'], status='invalid-output', raw_response='{}',
            output=None, usage={}, estimated_cents=None, reason='Synthetic transport; no actual inference.'))
        expect(claim() is None)  # parent still owns its original lease
        stop_parent(original)
        with ThreadPoolExecutor(max_workers=2) as pool:
            leases = list(pool.map(lambda _: claim(), range(2)))
        expect(sum(lease is not None for lease in leases) == 1)
        leased = next(lease for lease in leases if lease)
        expect(leased['id'] == first and parent() is None and dispatch.rpc('claim', {}) is None)
        checkpoint(leased, 'implementing')
        expect(claim() is None)  # sixty-second research admission window
        study()
        research = parent()
        expect(research is not None)
        stop_parent(research)
        clock_after_cooldown()
        expect(claim()['id'] == second)  # first cannot monopolize every turn
    check('continuous research yields after original dispatch drains and competing repairs receive separate turns', drain_and_rotate)

    def release_conditions():
        for condition in ('paused', 'cancelled', 'stale-worker', 'deadline', 'parent-stopped'):
            reset()
            ident = task()
            study()
            original = parent()
            if condition == 'parent-stopped':
                blocker = f.uid()
                f.query('insert into platform_assessment_blockers(id,study_id,assessment_task_id,source_kind,source_id,stage,source_status,diagnostic,original_reason_sha256,fingerprint) values('+','.join(map(q,[blocker,original['study_id'],original['id'],'task',original['id'],original['stage'],'blocked','Synthetic original blocker.','2'*64,workflow.digest(original['id'].encode())]))+')')
                f.query('insert into platform_assessment_repair_links(blocker_id,platform_task_id) values('+q(blocker)+','+q(ident)+')')
            expect(claim(ident) is None and parent() is None)
            if condition == 'paused':
                f.query('update platform_settings set paused=true')
            elif condition == 'cancelled':
                f.query('update platform_tasks set cancel_requested=true where id='+q(ident))
            elif condition == 'stale-worker':
                f.query("update platform_settings set worker_seen_at=clock_timestamp()-interval '61 seconds'")
            elif condition == 'parent-stopped':
                f.rpc('research_autonomy_control', dict(p_operation='cancel', p_actor=original['actor_id'], p_study=original['study_id'], p_payload={}))
            else:
                f.query("update platform_tasks set deadline_at=clock_timestamp()+interval '90 seconds' where id="+q(ident))
            study()
            expect(parent() is not None)  # no dependence on a worker cleanup poll
            expect(claim(ident) is None)
            expect(f.query('select task_id is null from platform_host_turn') == 't')
            expect(f.query('select lease_token from research_autonomy_tasks where id='+q(original['id'])) == original['lease_token'])
    check('pause cancellation stale heartbeat and insufficient original time release admission without interrupting a parent', release_conditions)

    def expiry():
        reset()
        ident = task()
        study()
        parent()
        expect(claim(ident) is None)
        f.query("update platform_host_turn set requested_at=statement_timestamp()-interval '11 minutes',expires_at=statement_timestamp()-interval '1 minute'")
        study()
        expect(parent() is not None)
        expect(claim(ident) is None and f.query('select task_id is null from platform_host_turn') == 't')
        expect(claim(ident) is None)
        f.rejects(lambda: f.query("update platform_host_turn set task_id="+q(ident)+",requested_at=statement_timestamp(),expires_at=statement_timestamp()+interval '11 minutes'"))
    check('drain reservation expires automatically cannot renew on polling and gives research a cooldown window', expiry)

    def expired_work():
        reset()
        expired = task("clock_timestamp()-interval '1 second'", checkpoint=dict(retained='original source pointer'))
        uncertain = task("clock_timestamp()-interval '1 second'")
        operation = f.uid()
        f.query('insert into platform_operations(id,task_id,kind,request_sha256,request,status) values('+q(operation)+','+q(uncertain)+",'deploy',"+q('f'*64)+",'{\"synthetic_unconfirmed_action\":true}','unknown')")
        original_operation = f.query('select to_jsonb(o) from platform_operations o where id='+q(operation))
        usable = task()
        retained = js('select to_jsonb(t) from platform_tasks t where id='+q(expired))
        expect(claim()['id'] == usable)
        after = js('select to_jsonb(t) from platform_tasks t where id='+q(expired))
        expect(after['status'] == 'deadline')
        for key in retained:
            if key not in ('status', 'reason', 'updated_at'):
                expect(after[key] == retained[key])
        expect(f.query('select status from platform_tasks where id='+q(uncertain)) == 'queued')
        expect(f.query('select to_jsonb(o) from platform_operations o where id='+q(operation)) == original_operation)
    check('expired queued repairs cannot consume turns or reset original source limits and commitments', expired_work)

    def upgrade_and_cleanup():
        reset()
        ident = task(status='implementing', lease_token=f.uid(), worker_id=worker)
        f.query("update platform_tasks set lease_until=clock_timestamp()-interval '1 second' where id="+q(ident))
        expect(parent() is None)
        leased = claim(ident)
        expect(leased['id'] == ident and leased['status'] == 'reconciling')
        f.query("update platform_host_turn set requested_at=statement_timestamp()-interval '11 minutes',expires_at=statement_timestamp()-interval '1 minute'")
        expect(parent() is None)  # reservation expiry cannot interrupt a lease
        f.rejects(lambda: work('checkpoint', ident, f.uid(), dict(status='blocked', reason='Invalid stale token', checkpoint={})))
        expect(parent() is None)
        checkpoint(leased)
        study()
        expect(parent() is not None)
        # A cleanup-unknown checkpoint must continue to fence both claim paths.
        reset()
        fence = task(status='reconciling', checkpoint=dict(cleanup_unknown=True))
        study()
        expect(parent() is None and dispatch.rpc('claim', {}) is None)
        other = task()
        expect(claim(other) is None)
        expect(f.query('select task_id is null from platform_host_turn') == 't')
        expect(claim(fence)['id'] == fence)
    check('in-place upgrades reconcile an original stale lease and preserve cleanup and wrong-token fences', upgrade_and_cleanup)

    def scoped():
        reset()
        first, other = task(), task()
        study()
        original = parent()
        expect(claim(first) is None)
        expect(claim(other) is None)
        expect(f.query('select task_id from platform_host_turn') == first)
        stop_parent(original)
        expect(claim(first)['id'] == first)
    check('a task-scoped claim never acquires a different reserved task', scoped)

    def multiple_reconciliations():
        reset()
        first, second = task(status='reconciling'), task(status='reconciling')
        expect(claim(first) is None)  # original scoped guard remains authoritative
        leased = claim()
        expect(leased['id'] == first)
        checkpoint(leased)
        clock_after_cooldown()
        expect(claim()['id'] == second)
    check('ordinary worker can reconcile multiple retained tasks without bypassing the scoped operator guard', multiple_reconciliations)

    def runtime_handoff():
        reset()
        first = task()
        qualified = task(status='publishing', checkpoint=dict(research_runtime=dict(certificate=dict(passed=True),
            scope=dict(version='research-controller-recovery-v1', scientific_and_request_content_unchanged=True,
                       existing_tests_unchanged=True, source_binding='9'*64))))
        leased = claim()
        expect(leased['id'] == first)
        expect(f.query('select count(*) from research_runtime_maintenance_holds where task_id='+q(qualified)) == '0')
        checkpoint(leased)
        clock_after_cooldown()
        expect(claim()['id'] == qualified)
        expect(f.query('select count(*) from research_runtime_maintenance_holds where task_id='+q(qualified)) == '1')
    check('qualified runtime maintenance holds bind only to the selected host turn and retain their original guards', runtime_handoff)

    def races():
        for _ in range(5):
            reset()
            ident = task()
            study()
            with ThreadPoolExecutor(max_workers=2) as pool:
                research = pool.submit(parent)
                platform = pool.submit(claim, ident)
                outcomes = (research.result(), platform.result())
            expect(sum(value is not None for value in outcomes) == 1)
            expect(f.query("select (select count(*) from research_autonomy_tasks where status='running' and lease_until>clock_timestamp())+(select count(*) from platform_tasks where lease_token is not null and lease_until>clock_timestamp())") == '1')
    check('concurrent parent and supervisor admission never obtain overlapping host turns', races)
    check('retained unknown native calls remain byte-for-byte unchanged without replay or inferred completion',
          lambda: expect(unknown_before == f.query("select jsonb_agg(to_jsonb(c) order by id) from research_builder_calls c where status='unknown'")))
    f.report['passed'] = True
    path = f.DIRECTORY/'platform-fair-scheduling-report.json'
    path.write_text(json.dumps(f.report, indent=2)+'\n')
    print(json.dumps(dict(passed=True, report=str(path), checks=len(f.report['checks']), provider_calls=0, production_mutations=0)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        f.report.update(passed=False, error_type=type(error).__name__, error=str(error))
        (f.DIRECTORY/'platform-fair-scheduling-failed-report.json').write_text(json.dumps(f.report, indent=2)+'\n')
        raise
