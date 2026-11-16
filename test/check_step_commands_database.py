"""Individual action admission and immutable history. Isolated Postgres only."""
import copy
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import check_granular_experiment_plan_capacity_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'
    code = """import {stepCommandFixture,stepPlan,stepBreakdown} from './tests/support/step-command-fixture.mjs';
import {stepCommandsRequest,STEP_COMMANDS_INSTRUCTIONS} from './lib/paper-step-commands-model.ts';
import {stepCommandsInput,validateStepCommandSet} from './lib/paper-step-commands.ts';
import {terminalCommandsRequest} from './lib/paper-terminal-commands-model.ts';
import {terminalCommandFixture} from './tests/support/terminal-command-fixture.mjs';
import {experimentPlanRequest} from './lib/paper-experiment-plan-model.ts';
import {readFileSync} from 'node:fs';
const {study}=JSON.parse(readFileSync(0,'utf8')),plan=stepPlan(),breakdown=stepBreakdown(),refs=['1.1.1','1.2.1','1.3.1','1.4.1'];
const cases=refs.map(ref=>({ref,set:stepCommandFixture(ref),valid:true}));
const prior=stepCommandFixture('1.2.1');prior.actions['1.2.1'].prerequisites=['1.1.1'];cases.push({ref:'1.2.1',set:prior,valid:true});
for(const mutate of [s=>s.actions['1.1.1']=s.actions['1.2.1'],s=>s.actions['1.2.1'].prerequisites=['1.4.1'],s=>s.actions['1.2.1'].prerequisites=['setup'],s=>s.actions['1.2.1'].commands='tc qdisc add dev eth0 root netem delay 20ms',s=>s.actions['1.2.1'].commands='python3 "$HELPER" run',s=>s.actions['1.2.1'].commands=\"os.readlink(f'/proc/{pid}/exe')\"]){const set=structuredClone(prior);mutate(set);cases.push({ref:'1.2.1',set,valid:false});}
const unblocked=stepCommandFixture('1.4.1');unblocked.actions['1.4.1']=stepCommandFixture().actions['1.1.1'];cases.push({ref:'1.4.1',set:unblocked,valid:false});
for(const c of cases){let valid=true;try{validateStepCommandSet(c.set,plan,breakdown,1,c.ref);}catch{valid=false;}if(valid!==c.valid)throw Error('JS fixture mismatch');}
console.log(JSON.stringify({study,plan,breakdown,cases,plan_request:experimentPlanRequest(breakdown),legacy_request:terminalCommandsRequest(study,1,plan,breakdown),legacy_commands:terminalCommandFixture(),requests:Object.fromEntries(refs.map(ref=>[ref,stepCommandsRequest(study,1,ref,plan,breakdown)]))}));"""
    study = f.uid()
    fixture = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, input=json.dumps(dict(study=study)), capture_output=True, text=True, check=True).stdout)
    f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Individual action software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role')
    f.query("update research_paper_intakes set status='ready',breakdown=" + f.sql_json(fixture['breakdown']) + ',reserved_cents=100,model_calls=1 where study_id=' + q(study))
    revision = int(f.query('select revision from research_paper_intakes where study_id=' + q(study)))
    def plan_rpc(op, payload):
        return json.loads(f.query('select research_experiment_plan(' + q(op) + ',' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(payload) + ')', role='service_role'))
    planned = plan_rpc('confirm', dict(intake_revision=revision, confirmed_breakdown=fixture['breakdown'], request=fixture['plan_request']))
    plan_response = dict(id='resp_plan_' + study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['plan']))])])
    plan_rpc('submitted', dict(token=planned['submit_token'], response_id=plan_response['id'], response=dict(id=plan_response['id'], status='queued')))
    planned = plan_rpc('finish', dict(token=planned['submit_token'], response_id=plan_response['id'], response=plan_response, plan=fixture['plan']))

    def legacy(op, payload):
        return json.loads(f.query('select research_terminal_commands_control(' + q(op) + ',' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,1,' + f.sql_json(dict(payload, command_layout='per-step-v1')) + ')', role='service_role'))
    old = legacy('generate', dict(request=fixture['legacy_request']))
    old_response = dict(id='resp_prior_' + study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['legacy_commands']))])])
    legacy('submitted', dict(token=old['submit_token'], response_id=old_response['id'], response=dict(id=old_response['id'], status='queued')))
    tables = ['research_paper_intakes', 'research_experiment_plans', 'research_experiment_plan_events', 'research_terminal_commands', 'research_terminal_command_events', 'research_paper_prompt_versions']
    def snapshots():
        return {table: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + table + ' t') for table in tables}
    before = snapshots()
    migration = (f.ROOT / 'database/202611160003_individual_step_commands.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert before == snapshots(), 'Migration must not rewrite any existing evidence or call'

    def rpc(op, ref, payload, actor=f.ACTOR, role='service_role'):
        return json.loads(f.query('select research_step_commands_control(' + q(op) + ',' + q(actor) + '::uuid,' + q(study) + '::uuid,1,' + q(ref) + ',' + f.sql_json(payload) + ')', role=role))
    first = '1.1.1'
    f.rejects(lambda: rpc('generate', first, dict(request=fixture['requests'][first])))
    legacy('finish', dict(token=old['submit_token'], response_id=old_response['id'], response=old_response, command_set=fixture['legacy_commands']))
    f.rejects(lambda: legacy('generate', dict(request=fixture['legacy_request'])))
    for role in ['anon', 'authenticated']:
        f.rejects(lambda role=role: rpc('generate', first, dict(request=fixture['requests'][first]), role=role))
        for table in ['research_step_commands', 'research_step_command_events', 'research_step_command_prompt_uses']:
            f.rejects(lambda role=role, table=table: f.query('select * from ' + table, role=role))
    f.rejects(lambda: rpc('generate', first, dict(request=fixture['requests'][first]), actor=f.OTHER))
    for case in fixture['cases']:
        actual = f.query('select research_valid_step_commands(' + f.sql_json(case['set']) + ',' + f.sql_json(fixture['plan']) + ',1,' + q(case['ref']) + ',' + f.sql_json(fixture['breakdown']) + ')') == 't'
        assert actual == case['valid'], case['ref']
    for ref, request in fixture['requests'].items():
        actual = json.loads(f.query('select research_step_commands_input(' + q(study) + '::uuid,1,' + q(ref) + ',' + f.sql_json(fixture['plan']) + ',' + f.sql_json(fixture['breakdown']) + ')'))
        assert actual == json.loads(request['input']), 'Exact JS/SQL selected-step input parity'
    for mutate in [lambda r: r.update(input='{}'), lambda r: r.update(max_output_tokens=64000), lambda r: r['text']['format']['schema']['properties']['actions']['required'].append('1.2.1')]:
        bad = copy.deepcopy(fixture['requests'][first]);mutate(bad)
        f.rejects(lambda bad=bad: rpc('generate', first, dict(request=bad)))
    f.query('update autonomy_budget_categories set max_spend_cents=599')
    f.rejects(lambda: rpc('generate', first, dict(request=fixture['requests'][first])))
    f.query('update autonomy_budget_categories set max_spend_cents=-1,max_model_calls=3')
    f.rejects(lambda: rpc('generate', first, dict(request=fixture['requests'][first])))
    f.query('update autonomy_budget_categories set max_model_calls=-1')
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda _: rpc('generate', first, dict(request=fixture['requests'][first])), range(3)))
    assert sum(row['admitted'] for row in rows) == 1
    row = rows[0]
    assert row['source_plan'] == fixture['plan'] and row['plan_revision'] == planned['revision'] and row['action_ref'] == first
    assert row['deadline_at'] == planned['deadline_at'] and row['model_calls'] == 1 and row['reserved_cents'] == 200
    assert row['command_layout'] == 'action-v1'
    f.rejects(lambda: f.query('update research_step_commands set action_ref=\'1.2.1\' where id=' + q(row['id'])))
    f.rejects(lambda: f.query('update research_step_commands set reason=\'direct write\' where id=' + q(row['id']), role='service_role'))
    f.rejects(lambda: rpc('submitted', '1.2.1', dict(token=row['submit_token'], response_id='resp_wrong_step')))
    response = dict(id='resp_action_' + study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['cases'][0]['set']))])])
    submitted = rpc('submitted', first, dict(token=row['submit_token'], response_id=response['id'], response=dict(id=response['id'], status='queued')))
    assert rpc('submitted', first, dict(token=row['submit_token'], response_id=response['id'], response=response)) == submitted
    finish = dict(token=row['submit_token'], response_id=response['id'], response=response, command_set=fixture['cases'][0]['set'])
    altered = copy.deepcopy(finish);altered['command_set']['actions'][first]['commands'] = 'printf altered'
    f.rejects(lambda: rpc('finish', first, altered))
    saved = rpc('finish', first, finish)
    assert saved['status'] == 'ready' and set(saved['command_set']['actions']) == {first}
    f.rejects(lambda: f.query('update research_step_commands set reason=\'altered\' where id=' + q(saved['id'])))
    second = '1.2.1'
    f.query('update autonomy_budget_categories set max_spend_cents=799')
    f.rejects(lambda: rpc('generate', second, dict(request=fixture['requests'][second])))
    f.query('update autonomy_budget_categories set max_spend_cents=-1')
    pending = rpc('generate', second, dict(request=fixture['requests'][second]))
    rpc('uncertain', second, dict(token=pending['submit_token'], reason='Synthetic lost acknowledgement; never replay.'))
    assert rpc('generate', second, dict(request=fixture['requests'][second]))['admitted'] is False
    f.rejects(lambda: rpc('cancel', second, dict(token=pending['submit_token'], response=dict(id='resp_unknown', status='cancelled'))))
    f.rejects(lambda: f.query('select research_delete_assessment(' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid)', role='service_role'))
    rpc('submitted', second, dict(token=pending['submit_token'], response_id='resp_reconciled_action', response=dict(id='resp_reconciled_action', status='queued')))
    rpc('cancel', second, dict(token=pending['submit_token'], response=dict(id='resp_reconciled_action', status='cancelled'), reason='Synthetic cancellation confirmed.'))
    assert json.loads(f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study))) == planned
    catalogue = f.query('select jsonb_agg(jsonb_build_object(\'instructions\',p.instructions,\'template\',p.input_template,\'configuration\',p.request_configuration)) from research_paper_prompt_versions p join research_step_command_prompt_uses u on u.prompt_version_id=p.id where u.study_id=' + q(study))
    assert 'paper_step_commands_v1' in catalogue and 'invented mean goodputs are 30' not in catalogue
    retained = f.query('select jsonb_agg(to_jsonb(c) order by action_ref) from research_step_commands c where study_id=' + q(study))
    f.query('select research_delete_assessment(' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid)', role='service_role')
    assert retained == f.query('select jsonb_agg(to_jsonb(c) order by action_ref) from research_step_commands c where study_id=' + q(study))
    f.rejects(lambda: rpc('generate', first, dict(request=fixture['requests'][first])))
    for table in ['research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, cases=len(fixture['cases']), checks=['idempotent nonrewriting migration', 'exact JS/SQL step input and validator parity', 'one selected action and original frozen plan revision', 'owner/private-role protections and immutable request/result history', 'aggregate original budgets include legacy and all individual calls', 'concurrent same-step deduplication', 'independent step tokens and uncertain-call fencing', 'old pending calls reconcile without new experiment-wide admissions', 'source-bound original response and private prompt catalogue', 'pending deletion guard and retained evidence', 'no provider calls or experiment execution'])))


if __name__ == '__main__':
    main()
