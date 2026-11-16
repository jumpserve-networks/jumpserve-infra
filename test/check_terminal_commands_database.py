"""Owner-only command generation and persistence in isolated Postgres. No execution."""
import copy
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import check_experiment_plan_link_reviews_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    code = """import {terminalCommandFixture,legacyTerminalCommandFixture,hierarchicalImplementationPlan,implementationBreakdown} from './tests/support/terminal-command-fixture.mjs';
import {terminalActionRefs,terminalBlockedActionRefs,terminalCommandsInput,validateTerminalCommandSet} from './lib/paper-terminal-commands.ts';
import {terminalCommandsRequest} from './lib/paper-terminal-commands-model.ts';
const plan=hierarchicalImplementationPlan(),breakdown=implementationBreakdown();
console.log(JSON.stringify({plan,breakdown,commands:terminalCommandFixture(),legacy:legacyTerminalCommandFixture(),refs:terminalActionRefs(plan,1),blocked:terminalBlockedActionRefs(plan,1,breakdown)}));"""
    front = f.ROOT.parent / 'jumpserve-front-end'
    fixture = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, capture_output=True, text=True, check=True).stdout)
    f.query((f.ROOT / 'database/202611150002_paper_terminal_commands.sql').read_text())
    study = f.uid()
    f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Terminal command software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role')
    f.query("update research_paper_intakes set status='ready',breakdown=" + f.sql_json(fixture['breakdown']) + ',reserved_cents=100,model_calls=1 where study_id=' + q(study))
    # Initial synthetic terminal source fixture, with the real terminal immutability guard active.
    f.query('insert into research_experiment_plans(study_id,owner_id,intake_revision,confirmed_breakdown,deadline_at,status,submit_token,provider_response_id,request,response,plan,reserved_cents,model_calls,policy_snapshot) values(' + q(study) + ',' + q(f.ACTOR) + ',2,' + f.sql_json(fixture['breakdown']) + ",clock_timestamp()+interval '1 day','ready'," + q(f.uid()) + ",'resp_command_source_" + study.replace('-', '') + "','{}','{}'," + f.sql_json(fixture['plan']) + ",100,1,'{}')")
    request_code = """import {terminalCommandsInput} from './lib/paper-terminal-commands.ts';import {terminalCommandsRequest} from './lib/paper-terminal-commands-model.ts';import {readFileSync} from 'node:fs';const f=JSON.parse(readFileSync(0,'utf8'));console.log(JSON.stringify({input:terminalCommandsInput(f.study,1,f.plan,f.breakdown),request:terminalCommandsRequest(f.study,1,f.plan,f.breakdown)}));"""
    request = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', request_code], cwd=front, input=json.dumps(dict(fixture, study=study)), capture_output=True, text=True, check=True).stdout)
    def rpc(op, data, actor=f.ACTOR, index=1, role='service_role', layout='per-step-v1'):
        payload = dict(data, command_layout=layout) if layout is not None else data
        return json.loads(f.query('select research_terminal_commands_control(' + q(op) + ',' + q(actor) + '::uuid,' + q(study) + '::uuid,' + str(index) + ',' + f.sql_json(payload) + ')', role=role))

    # Seed the earlier format through its original RPC before applying the upgrade.
    legacy_request = copy.deepcopy(request['request'])
    legacy_request['instructions'] = 'Legacy shared-script software fixture; no model call or experiment execution.'
    schema = legacy_request['text']['format']['schema']['properties']
    schema['setup'] = copy.deepcopy(schema['actions']['properties'][fixture['refs'][0]])
    schema['setup']['properties']['commands']['maxLength'] = 64000
    for block in [schema['setup'], schema['cleanup'], *schema['actions']['properties'].values()]:
        block['properties']['prerequisites'] = dict(type='array', maxItems=24, items=dict(type='string', enum=['setup', *fixture['refs']]))
    old = rpc('generate', dict(request=legacy_request), layout=None)
    old_events = f.query('select jsonb_agg(snapshot order by revision) from research_terminal_command_events where command_id=' + q(old['id']))
    migration = (f.ROOT / 'database/202611160001_standalone_terminal_commands.sql').read_text()
    f.query(migration)
    migrated = json.loads(f.query('select to_jsonb(c) from research_terminal_commands c where id=' + q(old['id'])))
    assert migrated.pop('command_layout') == 'shared-setup-v1' and migrated == {k: v for k, v in old.items() if k != 'admitted'}
    f.query(migration)
    assert f.query('select jsonb_agg(snapshot order by revision) from research_terminal_command_events where command_id=' + q(old['id'])) == old_events
    f.rejects(lambda: f.query("update research_terminal_commands set command_layout='per-step-v1' where id=" + q(old['id'])))
    f.rejects(lambda: rpc('generate', dict(request=request['request'])))
    rpc('uncertain', dict(token=old['submit_token'], reason='Legacy uncertain fixture.'), layout=None)
    f.rejects(lambda: rpc('generate', dict(request=request['request'])))
    rpc('submitted', dict(token=old['submit_token'], response_id='resp_legacy_terminal_test', response=dict(id='resp_legacy_terminal_test', status='queued')), layout=None)
    f.rejects(lambda: rpc('generate', dict(request=request['request'])))
    old_response = dict(id='resp_legacy_terminal_test', status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['legacy']))])])
    legacy = rpc('finish', dict(token=old['submit_token'], response_id=old_response['id'], response=old_response, command_set=fixture['legacy']), layout=None)
    legacy_snapshot = f.query('select to_jsonb(c) from research_terminal_commands c where id=' + q(legacy['id']))
    actual = json.loads(f.query('select research_terminal_commands_input(' + q(study) + ',1,' + f.sql_json(fixture['plan']) + ',' + f.sql_json(fixture['breakdown']) + ')'))
    assert actual == request['input']
    assert json.loads(f.query('select research_terminal_action_refs(' + f.sql_json(fixture['plan']) + ',1)')) == fixture['refs']
    assert json.loads(f.query('select research_terminal_blocked_refs(' + f.sql_json(fixture['plan']) + ',1,' + f.sql_json(fixture['breakdown']) + ')')) == fixture['blocked']
    assert f.query('select research_valid_terminal_commands(' + f.sql_json(fixture['commands']) + ',' + f.sql_json(fixture['refs']) + ')') == 't'
    assert f.query('select research_valid_standalone_terminal_commands(' + f.sql_json(fixture['commands']) + ',' + f.sql_json(fixture['refs']) + ',' + f.sql_json(fixture['blocked']) + ')') == 't'
    assert f.query('select research_valid_standalone_terminal_commands(' + f.sql_json(fixture['legacy']) + ',' + f.sql_json(fixture['refs']) + ')') == 'f'
    for change in [lambda c: c['actions'][fixture['refs'][0]].update(prerequisites=['setup']), lambda c: c['actions'][fixture['refs'][0]].update(commands='python3 "$HELPER" run'), lambda c: c['cleanup'].update(commands='source "$JUMPSERVE_WORKSPACE/common.sh"'), lambda c: c['actions'][fixture['refs'][0]].update(commands="os.readlink(f'/proc/{pid}/exe')")]:
        bad = copy.deepcopy(fixture['commands'])
        change(bad)
        assert f.query('select research_valid_standalone_terminal_commands(' + f.sql_json(bad) + ',' + f.sql_json(fixture['refs']) + ')') == 'f'
    unblocked = copy.deepcopy(fixture['commands'])
    unblocked['actions'][fixture['blocked'][0]] = copy.deepcopy(unblocked['actions'][fixture['refs'][0]])
    assert f.query('select research_valid_terminal_commands(' + f.sql_json(unblocked) + ',' + f.sql_json(fixture['refs']) + ',' + f.sql_json(fixture['blocked']) + ')') == 'f'
    for mutate in [lambda c: c['actions'].pop(fixture['refs'][0]), lambda c: c['setup'].update(prerequisites=['setup']), lambda c: c['actions'][fixture['refs'][0]].update(prerequisites=[fixture['refs'][-1]]), lambda c: c['inputs'][0].update(name='HOME'), lambda c: c['actions'][fixture['refs'][1]].update(commands='echo invalid')]:
        bad = copy.deepcopy(fixture['commands'])
        mutate(bad)
        assert f.query('select research_valid_terminal_commands(' + f.sql_json(bad) + ',' + f.sql_json(fixture['refs']) + ')') == 'f'

    original = f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study))
    for role in ['anon', 'authenticated']:
        f.rejects(lambda role=role: rpc('generate', dict(request=request['request']), role=role))
        for table in ['research_terminal_commands', 'research_terminal_command_events', 'research_terminal_command_prompt_uses']:
            f.rejects(lambda table=table, role=role: f.query('select * from ' + table, role=role))
    f.rejects(lambda: rpc('generate', dict(request=request['request']), actor=f.OTHER))
    f.rejects(lambda: rpc('generate', dict(request=request['request']), index=2))
    f.rejects(lambda: rpc('generate', dict(request=legacy_request)))
    f.rejects(lambda: rpc('generate', dict(request=request['request']), layout='unrecognized'))
    bad = copy.deepcopy(request['request'])
    bad['input'] = '{}'
    f.rejects(lambda: rpc('generate', dict(request=bad)))
    f.query('update autonomy_budget_categories set max_model_calls=3')
    f.rejects(lambda: rpc('generate', dict(request=request['request'])))
    f.query('update autonomy_budget_categories set max_model_calls=-1,max_spend_cents=599')
    f.rejects(lambda: rpc('generate', dict(request=request['request'])))
    f.query('update autonomy_budget_categories set max_spend_cents=-1')
    with ThreadPoolExecutor(max_workers=3) as pool:
        admitted = list(pool.map(lambda _: rpc('generate', dict(request=request['request'])), range(3)))
    assert sum(r['admitted'] for r in admitted) == 1
    row = admitted[0]
    assert row['deadline_at'] == json.loads(original)['deadline_at'] and row['request'] == request['request']
    assert row['source_plan'] == fixture['plan'] and row['model_calls'] == 1 and row['reserved_cents'] == 200
    assert row['command_layout'] == 'per-step-v1' and row['id'] != legacy['id']
    f.rejects(lambda: rpc('submitted', dict(token=legacy['submit_token'], response_id='resp_wrong_layout')))
    f.rejects(lambda: f.query('select research_delete_assessment(' + q(f.ACTOR) + ',' + q(study) + ')', role='service_role'))
    rpc('uncertain', dict(token=row['submit_token'], reason='Synthetic lost acknowledgement.'))
    assert rpc('generate', dict(request=request['request']))['admitted'] is False
    f.rejects(lambda: rpc('cancel', dict(token=row['submit_token'], response=dict(id='resp_missing', status='cancelled'))))
    rpc('submitted', dict(token=row['submit_token'], response_id='resp_terminal_test', response=dict(id='resp_terminal_test', status='queued')))
    f.rejects(lambda: rpc('submitted', dict(token=row['submit_token'], response_id='resp_other')))
    response = dict(id='resp_terminal_test', status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['commands']))])])
    payload = dict(token=row['submit_token'], response_id=response['id'], response=response, command_set=fixture['commands'])
    bad = copy.deepcopy(payload)
    bad['command_set']['setup']['commands'] = 'echo changed'
    f.rejects(lambda: rpc('finish', bad))
    saved = rpc('finish', payload)
    assert saved['status'] == 'ready' and saved['command_set'] == fixture['commands'] and saved['response'] == response
    assert rpc('generate', dict(request=request['request']))['admitted'] is False
    assert f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study)) == original
    assert f.query('select to_jsonb(c) from research_terminal_commands c where id=' + q(legacy['id'])) == legacy_snapshot
    for sql in ['update research_terminal_commands set status=\'processing\' where study_id=' + q(study), 'delete from research_terminal_command_events where study_id=' + q(study)]:
        f.rejects(lambda sql=sql: f.query(sql))
    catalog = f.query('select jsonb_build_object(\'instructions\',instructions,\'input_template\',input_template) from research_paper_prompt_versions where id in(select prompt_version_id from research_terminal_command_prompt_uses where study_id=' + q(study) + ')')
    assert study not in catalog and 'invented mean goodputs' not in catalog
    f.query('select research_delete_assessment(' + q(f.ACTOR) + ',' + q(study) + ')', role='service_role')
    assert f.query('select count(*) from research_terminal_commands where study_id=' + q(study)) == '2'
    for table in ['research_queue_jobs', 'research_model_dispatches', 'research_autonomy_tasks']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, checks=['idempotent layout migration preserves pre-existing calls and events', 'JS/SQL source, action and standalone dependency parity', 'legacy pending and uncertain requests fence replacement', 'owner/RLS denial and immutable layout', 'budget includes intake, planning and earlier layout calls', 'single concurrent admission per layout', 'layout-scoped original token and response identity', 'response-bound immutable commands and history', 'private prompt snapshots', 'pending deletion guard retains both completed versions', 'no experiments or workers'])))


if __name__ == '__main__':
    main()
