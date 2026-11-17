"""Step 4 shared scripts, rolling model profile and original-call preservation.

Uses only the existing isolated native Postgres fixture. No remote database,
provider calls, Docker, generated scripts or experiments are executed.
"""
import copy
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import check_step_commands_database as previous
import check_research_ideas_database as f


def main():
    previous.main()
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'
    code = """import {readFileSync} from 'node:fs';
import {experimentScriptsFixture,hierarchicalImplementationPlan,implementationBreakdown} from './tests/support/experiment-scripts-fixture.mjs';
import {experimentScriptsRequest} from './lib/paper-experiment-scripts-model.ts';
import {experimentPlanRequest} from './lib/paper-experiment-plan-model.ts';
import {stepCommandsRequest} from './lib/paper-step-commands-model.ts';
import {validateExperimentScripts,assertCompleteCommandBody} from './lib/paper-experiment-scripts.ts';
const {study}=JSON.parse(readFileSync(0,'utf8')),plan=hierarchicalImplementationPlan(),breakdown=implementationBreakdown();
const cases=[{name:'valid shared helper',set:experimentScriptsFixture(),valid:true}];
const large=experimentScriptsFixture();large.setup.commands='printf shared\\n'+'#'.repeat(80000);cases.push({name:'setup over old action cap',set:large,valid:true});
for(const [name,mutate] of [
 ['missing setup dependency',s=>s.actions['1.1.1'].prerequisites=[]],
 ['missing cleanup dependency',s=>s.cleanup.prerequisites=[]],
 ['late prerequisite',s=>s.actions['1.1.1'].prerequisites=['setup','1.4.3']],
 ['setup prerequisite',s=>s.setup.prerequisites=['1.1.1']],
 ['unclosed helper',s=>s.setup.commands=\"cat <<'PY'\\nprint(1)\"],
 ['unprivileged proc read',s=>s.setup.commands=\"os.readlink(f'/proc/{pid}/exe')\"],
 ['oversized setup',s=>s.setup.commands='#'.repeat(200001)],
 ['unblocked undefined criterion',s=>s.actions['1.4.3']={...s.actions['1.1.1']}],
 ['host tc after old setup limit',s=>s.setup.commands='#'.repeat(65000)+'\\nsudo tc qdisc add dev eth0 root netem delay 1ms'],
 ['package byte limit',s=>s.setup.commands='🙂'.repeat(70000)]
]){const set=experimentScriptsFixture();mutate(set);cases.push({name,set,valid:false});}
for(const c of cases){let valid=true;try{validateExperimentScripts(c.set,plan,breakdown,1);}catch{valid=false;}if(valid!==c.valid)throw Error(c.name);}
const bodies=[\"cat <<'PY'\\nprint(1)\\nPY\",'cat <<-PY\\n\\tprint(1)\\n\\tPY','cat <<PY\\na\\nPY\\ncat <<SH\\nb\\nSH','x=$((1 << 2))','cat <<< word',\"cat <<'PY'\\nprint(1)\",'cat <<PY\\na\\nPY '].map(commands=>{let valid=true;try{assertCompleteCommandBody(commands);}catch{valid=false;}return{commands,valid};});
console.log(JSON.stringify({plan,breakdown,cases,bodies,request:experimentScriptsRequest(study,1,plan,breakdown),plan_request:experimentPlanRequest(breakdown),step_request:stepCommandsRequest(study,1,'1.1.1',plan,breakdown)}));"""
    study = f.uid()
    fixture = json.loads(subprocess.run(['node', '--import', './scripts/lib/register-typescript.mjs', '--input-type=module', '-e', code], cwd=front, input=json.dumps(dict(study=study)), capture_output=True, text=True, check=True).stdout)
    tables = ['research_paper_intakes', 'research_experiment_plans', 'research_experiment_plan_events', 'research_terminal_commands', 'research_terminal_command_events', 'research_step_commands', 'research_step_command_events', 'research_paper_prompt_versions']

    def snapshots():
        return {table: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + table + ' t') for table in tables}

    before = snapshots()
    profile = (f.ROOT / 'database/202611170001_paper_assessment_model_profile.sql').read_text()
    f.query(profile)
    f.query(profile)
    assert before == snapshots(), 'Model profile migration must not alter existing requests'
    f.query("select research_paper_intake('reserve'," + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(dict(filename='Shared setup software fixture.pdf', sha256='a' * 64, byte_count=100)) + ')', role='service_role')
    f.query("update research_paper_intakes set status='ready',breakdown=" + f.sql_json(fixture['breakdown']) + ',reserved_cents=100,model_calls=1 where study_id=' + q(study))
    revision = int(f.query('select revision from research_paper_intakes where study_id=' + q(study)))

    def plan_rpc(op, payload):
        return json.loads(f.query('select research_experiment_plan(' + q(op) + ',' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid,' + f.sql_json(payload) + ')', role='service_role'))

    bad_profile = copy.deepcopy(fixture['plan_request']);bad_profile['model'] = 'unselected-model'
    f.rejects(lambda: plan_rpc('confirm', dict(intake_revision=revision, confirmed_breakdown=fixture['breakdown'], request=bad_profile)))
    planned = plan_rpc('confirm', dict(intake_revision=revision, confirmed_breakdown=fixture['breakdown'], request=fixture['plan_request']))
    assert planned['request']['model'] == 'gpt-5.4-2026-03-05' and planned['request']['reasoning']['effort'] == 'medium'
    plan_response = dict(id='resp_shared_plan_' + study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['plan']))])])
    plan_rpc('submitted', dict(token=planned['submit_token'], response_id=plan_response['id'], response=dict(id=plan_response['id'], status='queued')))
    planned = plan_rpc('finish', dict(token=planned['submit_token'], response_id=plan_response['id'], response=plan_response, plan=fixture['plan']))

    def old_rpc(op, payload, alias='research_step_commands_control'):
        return json.loads(f.query('select ' + alias + '(' + q(op) + ',' + q(f.ACTOR) + '::uuid,' + q(study) + "::uuid,1,'1.1.1'," + f.sql_json(payload) + ')', role='service_role'))

    old = old_rpc('generate', dict(request=fixture['step_request']))
    old_rpc('submitted', dict(token=old['submit_token'], response_id='resp_pending_old_shared_test', response=dict(id='resp_pending_old_shared_test', status='queued')))
    before = snapshots()
    migration = (f.ROOT / 'database/202611170002_shared_experiment_scripts.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert before == snapshots(), 'Shared migration must preserve old calls and evidence'

    def rpc(op, payload=None, actor=f.ACTOR, role='service_role'):
        return json.loads(f.query('select research_experiment_scripts_control(' + q(op) + ',' + q(actor) + '::uuid,' + q(study) + '::uuid,1,' + f.sql_json(payload or {}) + ')', role=role))

    f.rejects(lambda: rpc('generate', dict(request=fixture['request'])))
    f.rejects(lambda: old_rpc('generate', dict(request=fixture['step_request'])))
    f.rejects(lambda: old_rpc('generate', dict(request=fixture['step_request']), 'research_step_commands_control_before_shared_scripts'))
    old_rpc('cancel', dict(token=old['submit_token'], response=dict(id='resp_pending_old_shared_test', status='cancelled'), reason='Original legacy call explicitly cancelled by fixture owner.'))
    f.rejects(lambda: rpc('generate', dict(request=fixture['request']), actor=f.OTHER))
    for role in ['anon', 'authenticated']:
        f.rejects(lambda role=role: rpc('generate', dict(request=fixture['request']), role=role))
        for table in ['research_experiment_scripts', 'research_experiment_script_events', 'research_experiment_script_prompt_uses']:
            f.rejects(lambda role=role, table=table: f.query('select * from ' + table, role=role))
    for case in fixture['cases']:
        actual = f.query('select research_valid_experiment_scripts(' + f.sql_json(case['set']) + ',' + f.sql_json(fixture['plan']) + ',1,' + f.sql_json(fixture['breakdown']) + ')') == 't'
        assert actual == case['valid'], case['name']
    for case in fixture['bodies']:
        assert (f.query('select research_complete_script(' + q(case['commands']) + ')') == 't') == case['valid'], case
    assert json.loads(f.query('select research_experiment_scripts_input(' + q(study) + '::uuid,1,' + f.sql_json(fixture['plan']) + ',' + f.sql_json(fixture['breakdown']) + ')')) == json.loads(fixture['request']['input'])
    for mutate in [lambda r: r.update(model='gpt-5.4-mini-2026-03-17'), lambda r: r.update(reasoning=dict(effort='low')), lambda r: r.update(max_output_tokens=16000), lambda r: r.update(input='{}'), lambda r: r['text']['format']['schema']['properties']['actions']['required'].pop()]:
        bad = copy.deepcopy(fixture['request']);mutate(bad)
        f.rejects(lambda bad=bad: rpc('generate', dict(request=bad)))
    # Intake 100 + planning 100 + cancelled individual 200 + new shared 200.
    f.query('update autonomy_budget_categories set max_spend_cents=599')
    f.rejects(lambda: rpc('generate', dict(request=fixture['request'])))
    f.query('update autonomy_budget_categories set max_spend_cents=-1,max_model_calls=3')
    f.rejects(lambda: rpc('generate', dict(request=fixture['request'])))
    f.query('update autonomy_budget_categories set max_model_calls=-1')
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda _: rpc('generate', dict(request=fixture['request'])), range(3)))
    assert sum(row['admitted'] for row in rows) == 1
    row = rows[0]
    assert row['request'] == fixture['request'] and row['deadline_at'] == planned['deadline_at']
    assert row['source_plan'] == fixture['plan'] and row['plan_revision'] == planned['revision'] and row['reserved_cents'] == 200
    f.rejects(lambda: f.query("update research_experiment_scripts set reason='bypass' where id=" + q(row['id']), role='service_role'))
    f.rejects(lambda: f.query("update research_experiment_scripts set request='{}' where id=" + q(row['id'])))
    f.rejects(lambda: f.query('select research_delete_assessment(' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid)', role='service_role'))
    uncertain = rpc('uncertain', dict(token=row['submit_token'], reason='Synthetic lost acknowledgement.'))
    assert rpc('generate', dict(request=fixture['request']))['admitted'] is False
    f.rejects(lambda: rpc('cancel', dict(token=row['submit_token'], response=dict(id='resp_unknown', status='cancelled'))))
    response = dict(id='resp_shared_' + study.replace('-', ''), status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(fixture['cases'][0]['set']))])])
    submitted = rpc('submitted', dict(token=uncertain['submit_token'], response_id=response['id'], response=dict(id=response['id'], status='queued')))
    assert rpc('submitted', dict(token=row['submit_token'], response_id=response['id'], response=response)) == submitted
    finish = dict(token=row['submit_token'], response_id=response['id'], response=response, command_set=fixture['cases'][0]['set'])
    altered = copy.deepcopy(finish);altered['command_set']['setup']['commands'] = 'printf altered'
    f.rejects(lambda: rpc('finish', altered))
    saved = rpc('finish', finish)
    assert saved['status'] == 'ready' and saved['command_set'] == fixture['cases'][0]['set']
    f.rejects(lambda: f.query("update research_experiment_scripts set reason='changed' where id=" + q(row['id'])))
    catalog = f.query("select jsonb_agg(jsonb_build_object('template',p.input_template,'configuration',p.request_configuration)) from research_paper_prompt_versions p join research_experiment_script_prompt_uses u on u.prompt_version_id=p.id where u.study_id=" + q(study))
    assert 'paper-experiment-scripts-v1' in catalog and study not in catalog and 'invented mean goodputs' not in catalog
    retained = f.query('select to_jsonb(c) from research_experiment_scripts c where study_id=' + q(study))
    f.query('select research_delete_assessment(' + q(f.ACTOR) + '::uuid,' + q(study) + '::uuid)', role='service_role')
    assert retained == f.query('select to_jsonb(c) from research_experiment_scripts c where study_id=' + q(study))
    assert json.loads(f.query('select to_jsonb(p) from research_experiment_plans p where study_id=' + q(study))) == planned
    for table in ['research_autonomy_tasks', 'research_model_dispatches', 'research_queue_jobs']:
        assert f.query('select count(*) from ' + table + ' where study_id=' + q(study)) == '0'
    print(json.dumps(dict(passed=True, database=f.DATABASE, cases=len(fixture['cases']), checks=['idempotent nonrewriting model and shared migrations', 'full GPT-5.4 medium admission', 'JS/SQL input, block and heredoc parity', 'old pending reconciliation and retired individual admission', 'aggregate budgets and original deadlines', 'one concurrent admission and immutable provider/content identity', 'private grants and generic prompt catalogue', 'pending deletion protection and retained history', 'no model calls or experiment execution'])))


if __name__ == '__main__':
    main()
