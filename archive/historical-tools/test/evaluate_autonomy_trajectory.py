"""Fixed live model -> real controller/SQL/queue trajectory. Never deploys."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'bin'), str(ROOT.parent / 'jumpserve-back-end/research_workflow')]
import autonomy, autonomy_model as model, preparation, store, worker, workflow
import check_research_ideas_database as fixture
import autonomy_fixtures
from autonomy_trajectory_evidence import POLICY_PATH, publication_status

BASE = ROOT / '.test-artifacts/autonomy-followups/application-trajectory-v1'
PROTOCOL = ROOT / 'docs/autonomy-bounded-followups-release-protocol-v1.md'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepare():
    BASE.mkdir(parents=True, exist_ok=True)
    target = BASE / 'frozen-inputs.json'
    if target.exists():
        raise RuntimeError('Preserve original trajectory; no overwrite or reset.')
    if BASE.name in ('application-trajectory-v2', 'application-trajectory-v3'):
        recovered = BASE.name == 'application-trajectory-v3'
        previous = BASE.parent / ('application-trajectory-v2' if recovered else 'application-trajectory-v1')
        packet = json.loads((previous / 'frozen-inputs.json').read_bytes())
        original_report = json.loads((previous / 'evaluation-report.json').read_bytes())
        if original_report['live_provider_calls'] != (10 if recovered else 0): raise RuntimeError('Recovery differs from the retained known failure')
        packet = dict(packet)
        packet.update(producer_sha256=sha(Path(__file__).read_bytes()),
            recovery_protocol_sha256=sha((ROOT / 'docs/autonomy-bounded-followups-release-amendment-v2.md').read_bytes()),
            previous_frozen_inputs_sha256=sha((previous / 'frozen-inputs.json').read_bytes()))
        for source in previous.glob('turn-*'):
            if source.is_file(): (BASE / source.name).write_bytes(source.read_bytes())
        for source in (previous / 'storage-originals').rglob('*'):
            if source.is_file():
                destination = BASE / source.relative_to(previous); destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(source.read_bytes())
        for source in (previous / 'inputs').rglob('*'):
            if source.is_file():
                destination = BASE / source.relative_to(previous); destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(source.read_bytes())
        (BASE / 'inputs/test/evaluate_autonomy_trajectory.py').write_bytes(Path(__file__).read_bytes())
        if recovered:
            fixture.DATABASE = packet['database']; fixture.ACTOR = packet['actor']; fixture.query.__defaults__ = (packet['database'], None); store.request = fixture.transport
            task = autonomy.one('autonomy_tasks', packet['study_id'], packet['task_id'])
            state = autonomy.rows('autonomy_workflows', packet['study_id'])[0]
            error = (previous / 'turn-10-error.bin').read_bytes()
            if b'ThrottlingException' not in error or (previous / 'turn-10-provider.json').read_bytes() or task['attempts'] != 10 or task['status'] != 'blocked' or state['max_spend_cents'] != 10000 or state['max_attempts'] != 25:
                raise RuntimeError('Known rejection/authorization differs; no recovery')
            turn = autonomy.rows('autonomy_turns', packet['study_id'], task_id='eq.'+task['id'], number='eq.10')[0]
            if turn['raw_response'] is not None or turn['status'] != 'failed': raise RuntimeError('A provider answer or uncertain state needs separate reconciliation')
            for row in autonomy.rows('artifacts', packet['study_id']):
                path = '/storage/v1/object/' + store.BUCKET + '/' + row['storage_path']
                entry = packet['storage'].get(path)
                source = previous / entry['path'] if entry else previous / 'local-artifacts' / ('raw-' + sha(path.encode()))
                raw = source.read_bytes()
                if sha(raw) != row['sha256']: raise RuntimeError('Prior run artifact differs')
                destination = BASE / 'storage-originals' / row['sha256']; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(raw)
                packet['storage'][path] = dict(path=str(destination.relative_to(BASE)), sha256=sha(raw))
            prior_cases = json.loads(json.dumps(original_report['cases'])); rejected = prior_cases[-1]
            rejected.update(status='provider-rejected', passed=True, no_answer_received=True, failure_code='ThrottlingException', failure_sha256=sha(error),
                provider_attempt_not_replayed=True, exact_response_verified=True, response_availability='No SDK answer; explicit service rejection', failure_reviewed=False)
            packet.update(prior_cases=prior_cases, previous_report_sha256=sha((previous/'evaluation-report.json').read_bytes()),
                recovery_protocol_sha256=sha((ROOT/'docs/autonomy-bounded-followups-release-amendment-v3.md').read_bytes()),
                original_attempts=10, original_committed_cents=state['committed_cents'], provider_spacing_seconds=20)
            # Audited isolated-DB operator action, never a reset or same-turn replay.
            fixture.query("begin; do $$ begin if exists(select 1 from research_autonomy_events where task_id="+fixture.sql_text(task['id'])+" and event='release-throttle-reconciliation') then raise exception 'Recovery already used'; end if; end $$; insert into research_autonomy_events(study_id,task_id,event,details) values("+fixture.sql_text(task['study_id'])+","+fixture.sql_text(task['id'])+",'release-throttle-reconciliation',"+fixture.sql_json(dict(failure_sha256=sha(error),operator='Primary Codex AI release evaluator; isolated SQL only',attempts_preserved=10,committed_cents_preserved=state['committed_cents'],same_turn_replayed=False))+ "); update research_autonomy_workflows set status='running',reason='Explicit rejection reconciled; original authorization retained.' where study_id="+fixture.sql_text(task['study_id'])+"; update research_autonomy_tasks set status='queued',next_at=clock_timestamp(),reason='Next numbered attempt after verified throttle rejection; no budget or deadline reset.' where id="+fixture.sql_text(task['id'])+"; commit;")
        save(target, packet)
        print(json.dumps(dict(frozen=str(target), database=packet['database'], task_id=packet['task_id'], previous_provider_calls=10 if recovered else 0)))
        return
    fixture.bootstrap()
    fixture.rpc('publish_agent_prompt', autonomy_fixtures.publish_fixture())
    original = ROOT.parent / 'jumpserve-back-end/research_workflow/plans/ipv6-archive-v1.json'
    plan = json.loads(original.read_bytes())
    with patch.object(autonomy, 'wake', return_value={'status': 'isolated-local'}):
        created = autonomy.start(fixture.ACTOR, dict(request_id=fixture.uid(), autonomous=True,
            paper=dict(title='Release trajectory: retained IPv6 absolute numerical cells',
                paper_url=plan['paper_urls'][0], domain='Internet measurement', study_kind='paper',
                scope='Only the retained absolute folded metrics claim; other paper claims excluded from this evaluation.')))
    study = created['id']
    intake = fixture.rpc('research_autonomy_control', dict(p_operation='lease', p_actor=None, p_study=None, p_payload={}))
    if intake['study_id'] != study or intake['stage'] != 'intake':
        raise RuntimeError('Unexpected isolated intake identity')
    study_row = autonomy.one('studies', study, study)
    prepared = preparation.prepare(study_row, fixture.ACTOR, dict(action='prepare', request_id=fixture.uid()))
    claim = next(c for c in autonomy.rows('claims', study) if c['description'] == 'Published absolute folded metrics')
    autonomy.seed(intake, [claim], dict(prepared_id=prepared['prepared']['id']))
    autonomy.advance(intake, 'finished', reason='Release trajectory explicitly scopes one retained claim.')
    task = next(t for t in autonomy.rows('autonomy_tasks', study) if t['claim_id'] == claim['id'])
    manifest = json.loads((ROOT / 'research-workflow-runtime.json').read_bytes())
    for name, expected in manifest['files'].items():
        raw = (original.parent.parent / name).read_bytes()
        if sha(raw) != expected: raise RuntimeError('Runtime source differs: ' + name)
        copy = BASE / 'inputs/backend' / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(raw)
    originals = {}
    for name, raw in fixture.files.items():
        copy = BASE / 'storage-originals' / sha(raw)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(raw)
        originals[name] = dict(path=str(copy.relative_to(BASE)), sha256=sha(raw))
    packet = dict(version='autonomy-trajectory-inputs-v1', database=fixture.DATABASE, actor=fixture.ACTOR,
        study_id=study, task_id=task['id'], claim_id=claim['id'], policy_sha256=sha(POLICY_PATH.read_bytes()),
        protocol_sha256=sha(PROTOCOL.read_bytes()), producer_sha256=sha(Path(__file__).read_bytes()),
        input_sha256=manifest['files'], source_plan_sha256=sha(original.read_bytes()), storage=originals,
        limits=dict(max_attempts_per_claim=25, max_paper_committed_cents=10000, max_elapsed_seconds=604800),
        evaluation_limits=dict(committed_cents=3000, wall_seconds=2700, controller_cycles=100),
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        prompt=json.loads((ROOT / 'database/seed-autonomy-v8.json').read_bytes()),
        fixture_scope='Local Google identity/HTTP/Storage and synthetic local prompt activation; actual Bedrock/controller/SQL/arithmetic.')
    for source in (PROTOCOL, POLICY_PATH, Path(__file__)):
        copy = BASE / 'inputs' / source.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(source.read_bytes())
    save(target, packet)
    print(json.dumps(dict(frozen=str(target), database=fixture.DATABASE, task_id=task['id'])))


def live():
    packet = json.loads((BASE / 'frozen-inputs.json').read_bytes())
    target = BASE / 'evaluation-report.json'
    if target.exists(): raise RuntimeError('Trajectory already attempted; never replay unknown calls.')
    if sha(Path(__file__).read_bytes()) != packet['producer_sha256'] or sha(PROTOCOL.read_bytes()) != packet['protocol_sha256'] or sha(POLICY_PATH.read_bytes()) != packet['policy_sha256']:
        raise RuntimeError('Frozen producer/protocol/policy differs')
    for name, expected in packet['input_sha256'].items():
        if sha((ROOT.parent / 'jumpserve-back-end/research_workflow' / name).read_bytes()) != expected:
            raise RuntimeError('Frozen implementation differs: ' + name)
    account = subprocess.check_output(['aws', 'sts', 'get-caller-identity', '--profile', 'jumpserve', '--region', 'us-east-1', '--query', 'Account', '--output', 'text'], text=True).strip()
    if account != '395567831870' or json.loads((ROOT / 'cdk.json').read_bytes())['context']['supabaseUrl'] != 'https://regphejnlvfpyokpniny.supabase.co':
        raise RuntimeError('Fixed account/project differs')
    fixture.DATABASE = packet['database']; fixture.ACTOR = packet['actor']
    # The isolated helper binds DATABASE at definition time; restore that exact
    # default too. This adapter-only correction never resets the SQL records.
    fixture.query.__defaults__ = (packet['database'], None)
    if fixture.query('select current_database()') != packet['database']: raise RuntimeError('Frozen local database identity differs')
    fixture.DIRECTORY = BASE / 'local-artifacts'; fixture.DIRECTORY.mkdir(exist_ok=True)
    for path, entry in packet['storage'].items():
        raw = (BASE / entry['path']).read_bytes()
        if sha(raw) != entry['sha256']: raise RuntimeError('Frozen original artifact differs')
        fixture.files[path] = raw
    store.request = fixture.transport
    study, task_id = packet['study_id'], packet['task_id']
    report = dict(version='autonomy-trajectory-evaluation-v1', limits=packet['limits'], policy_sha256=packet['policy_sha256'],
        input_sha256=packet['input_sha256'], protocol_sha256=packet['protocol_sha256'],
        frozen_inputs_sha256=sha((BASE / 'frozen-inputs.json').read_bytes()),
        status='incomplete-evaluation', terminal_status=None, reason='Live trajectory in progress.', attempts_used=0,
        committed_cents=500, cases=[], live_provider_calls=0, known_estimated_cents=0, measured_charges_usd=None,
        reviewer=dict(identity='Primary Codex AI implementer; inspection pending', type='AI', independent=False, passed=False),
        fixture_scope=packet['fixture_scope'], checks=dict(exact_prompts_retained=True, scoped_reads=True,
            evidence_decisions=True, authorization_preserved=True, no_unknown_call_replay=True))
    if packet.get('prior_cases'):
        report.update(cases=packet['prior_cases'], live_provider_calls=len(packet['prior_cases']), attempts_used=packet['original_attempts'], committed_cents=packet['original_committed_cents'],
            prior_provider_calls=len(packet['prior_cases']), prior_report_sha256=packet['previous_report_sha256'], operator_reconciliation='One exact retained throttle rejection; no attempt/budget/deadline reset.')
    began = time.monotonic()
    elapsed_before = max(0, (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(packet['created_at'])).total_seconds())

    def checkpoint(): save(target, report)

    def invoke(request):
        if packet.get('provider_spacing_seconds'): time.sleep(packet['provider_spacing_seconds'])
        number = len(report['cases']) + 1
        state = autonomy.rows('autonomy_workflows', study)[0]
        if state['committed_cents'] > packet['evaluation_limits']['committed_cents'] or time.monotonic() - began + elapsed_before > packet['evaluation_limits']['wall_seconds']:
            raise RuntimeError('Separate evaluation-only resource bound reached; no provider dispatch.')
        name = 'turn-' + str(number).zfill(2)
        raw = workflow.canonical(request)
        request_path = BASE / (name + '-request.json'); request_path.write_bytes(raw)
        row = dict(name=name, number=number, status='running', passed=False, request_sha256=sha(raw), request_bytes=len(raw),
            reserved_cents=model.reservation(request), raw_answer_reviewed=False, rendered_answer_reviewed=False)
        report['cases'].append(row); report['live_provider_calls'] += 1; checkpoint()
        result = subprocess.run(['aws', 'bedrock-runtime', 'converse', '--profile', 'jumpserve', '--region', 'us-east-1', '--cli-input-json', 'file://' + str(request_path), '--cli-connect-timeout', '5', '--cli-read-timeout', '90', '--output', 'json'], capture_output=True, timeout=120,
            env={**os.environ, 'AWS_MAX_ATTEMPTS': '1', 'AWS_RETRY_MODE': 'standard', 'AWS_PAGER': ''})
        (BASE / (name + '-provider.json')).write_bytes(result.stdout); row['provider_response_sha256'] = sha(result.stdout)
        if result.returncode:
            error = BASE / (name + '-error.bin'); error.write_bytes(result.stderr); error.chmod(0o600)
            row.update(status='provider-failed', reason='Original diagnostic private; no retry.'); checkpoint()
            raise RuntimeError('Provider call failed or unconfirmed; no replay')
        response = json.loads(result.stdout)
        message = workflow.canonical(response['output']['message']); (BASE / (name + '-message.json')).write_bytes(message)
        row.update(output_sha256=sha(message), usage=response.get('usage'), estimated_cents=model.estimate(response.get('usage')))
        try:
            output = model.parse(response)
            (BASE / (name + '-rendered.json')).write_bytes(workflow.canonical(output)); row['output'] = output
        except Exception as error:
            row.update(status='invalid-response', reason=str(error)); checkpoint(); raise
        row['status'] = 'received'; checkpoint()
        return response

    checkpoint()
    try:
        with patch.object(model, 'invoke', side_effect=invoke):
            for cycle in range(packet['evaluation_limits']['controller_cycles']):
                if time.monotonic() - began + elapsed_before > packet['evaluation_limits']['wall_seconds']:
                    report['reason'] = 'Separate 45-minute evaluation window ended; application outcome remains unverified.'; break
                fixture.query("update research_autonomy_tasks set next_at=clock_timestamp() where study_id=" + fixture.sql_text(study) + " and status='waiting'")
                leased = fixture.rpc('research_autonomy_control', dict(p_operation='lease', p_actor=None, p_study=None, p_payload={}))
                count = len(report['cases'])
                if leased:
                    if leased['id'] != task_id: raise RuntimeError('Unexpected isolated claim identity')
                    outcome = autonomy.process(leased)
                    if len(report['cases']) > count:
                        row = report['cases'][-1]
                        after = autonomy.one('autonomy_tasks', study, task_id)
                        row['controller_outcome'] = outcome
                        turn = autonomy.rows('autonomy_turns', study, task_id='eq.' + task_id, number='eq.' + str(row['number']))[0]
                        row['stage'] = turn['stage']
                        row['exact_request_verified'] = sha(turn['request_raw'].encode()) == row['request_sha256']
                        if turn['raw_response'] is None:
                            error = (BASE / (row['name'] + '-error.bin')).read_bytes()
                            if b'ThrottlingException' not in error or (BASE / (row['name'] + '-provider.json')).read_bytes(): raise RuntimeError('Unknown provider outcome; no retry permitted')
                            row.update(status='provider-rejected', no_answer_received=True, failure_code='ThrottlingException', failure_sha256=sha(error), provider_attempt_not_replayed=True, failure_reviewed=False)
                            row['exact_response_verified'] = True
                        else: row['exact_response_verified'] = sha(turn['raw_response'].encode()) == row.get('output_sha256')
                        if row.get('output', {}).get('action') == 'inspect':
                            read = after['context'].get('evidence_read')
                            row['scoped_read_accepted'] = bool(read and read.get('requested_by_turn_id') == turn['id'])
                            if read:
                                raw = workflow.canonical(read); (BASE / (row['name'] + '-tool-result.json')).write_bytes(raw); row['tool_result_sha256'] = sha(raw)
                        row['passed'] = (turn['status'] == 'complete' or row['status']=='provider-rejected' and after['status']=='blocked') and row['exact_request_verified'] and row['exact_response_verified'] and row.get('scoped_read_accepted', True)
                        if row['status']!='provider-rejected': row['status'] = 'complete' if row['passed'] else 'failed'
                        if not row['passed']: raise RuntimeError('Actual controller/answer provenance check failed')
                        print(json.dumps(dict(turn=row['number'], stage=turn['stage'], action=row.get('output',{}).get('action'), task_status=after['status'])), flush=True)
                worker.handler({})
                task = autonomy.one('autonomy_tasks', study, task_id)
                state = autonomy.rows('autonomy_workflows', study)[0]
                report.update(attempts_used=task['attempts'], committed_cents=state['committed_cents'], task_status=task['status'], task_label=task['label'])
                if task['status'] in ('resolved', 'blocked', 'attempt-limit', 'budget-limit', 'deadline'):
                    report.update(status='complete', terminal_status={'resolved': 'assessed', 'blocked': 'external-blocker'}.get(task['status'], task['status']), reason=task['reason'])
                    if task['status'] == 'resolved':
                        assessment = autonomy.one('assessments', study, task['context']['assessment_id'])
                        save(BASE / 'assessment.json', assessment); report['assessment_sha256'] = sha((BASE / 'assessment.json').read_bytes())
                        report['checks']['evidence_decisions'] = assessment['label'] == task['label'] and assessment['tested_conditions']['coverage'].get('covered_cells') == 1152
                    break
                checkpoint()
            report['checks']['authorization_preserved'] = report['attempts_used'] <= 25 and report['committed_cents'] <= 10000
            report['checks']['exact_prompts_retained'] = all(c.get('exact_request_verified') and c.get('exact_response_verified') for c in report['cases'])
            report['checks']['scoped_reads'] = all(c.get('scoped_read_accepted', True) for c in report['cases'])
            report['validation_status'] = publication_status(report)
    except Exception as error:
        report.update(status='failed', reason=str(error)); raise
    finally:
        report.update(known_estimated_cents=sum(c.get('estimated_cents') or 0 for c in report['cases']),
            missing_usage_calls=sum(c.get('estimated_cents') is None for c in report['cases']), ended_at=dt.datetime.now(dt.timezone.utc).isoformat(), wall_seconds=time.monotonic()-began)
        checkpoint()
        print(json.dumps(dict(report=str(target), status=report['status'], terminal=report['terminal_status'], calls=report['live_provider_calls'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--prepare', action='store_true'); parser.add_argument('--live', action='store_true'); parser.add_argument('--campaign', choices=['v1','v2','v3'], default='v3'); args = parser.parse_args()
    BASE = ROOT / ('.test-artifacts/autonomy-followups/application-trajectory-' + args.campaign)
    if args.prepare == args.live: parser.error('Choose prepare or live')
    prepare() if args.prepare else live()
