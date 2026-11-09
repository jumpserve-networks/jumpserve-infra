"""Offline recorded-data diagnosis. Never calls AWS, Supabase, models or Docker."""
import collections
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACK = ROOT.parent / 'jumpserve-back-end'
sys.path.insert(0, str(BACK / 'research_workflow'))
import autonomous_repair as repair
import experiment_builder as builder
import network_spec
import netem_iperf
from workflow import canonical, digest, validate_protocol


def main():
    base = ROOT / '.test-artifacts/assessment-4055396e'
    source = sorted(base.glob('*/capture.json'))[-1]
    data = json.loads(source.read_bytes())
    supplement_path = sorted(base.glob('*/supplement.json'))[-1]
    supplement = json.loads(supplement_path.read_bytes())
    assert supplement['source_sha256'] == digest(source.read_bytes()) and data['capture_finished_at'] and supplement['finished_at']
    pins = json.loads((ROOT / 'research-workflow-runtime.json').read_bytes())
    assert all(digest((BACK / 'research_workflow' / n).read_bytes()) == h for n, h in pins['files'].items())
    out = base / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(mode=0o700)
    report = dict(version='builder-stall-offline-analysis-v1', recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(), source_capture=str(source.relative_to(ROOT)), supplement=str(supplement_path.relative_to(ROOT)), source_revision=pins['source_revision'], source_files=pins['files'], new_model_calls=0, new_experiments=0, production_writes=0, source_verified=True, tasks=[], native_boundaries=[], repair_controls=[], scope='Recorded-data reanalysis and deterministic software controls, not a paper experiment or live model qualification', reviewer=dict(identity='Codex implementing investigator', type='AI', human=False, independent=False))
    records = {r['record']['task_id']: r['record'] for r in supplement['repairs']}
    evidence = []
    for path in (source, supplement_path):
        evidence.append(dict(path=str(path.relative_to(ROOT)), sha256=digest(path.read_bytes())))
    for entry in data['artifact_reads']:
        assert entry['status'] == 'verified'
        raw = (source.parent / entry['file']).read_bytes()
        assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256']
        evidence.append(dict(path=str((source.parent / entry['file']).relative_to(ROOT)), sha256=digest(raw)))
    all_commands = []
    for task in data['tasks']:
        path = source.parent / (task['id'] + '-derived-history.json')
        history = json.loads(path.read_bytes())
        commands = [h for h in history if h['type'] == 'function_call']
        counts = dict(collections.Counter(c['name'] for c in commands))
        parents = [d for d in data['dispatches'] if d['task_id'] == task['id']]
        report['tasks'].append(dict(task_id=task['id'], claim_id=task['claim_id'], stage_at_capture=task['stage'], status_at_capture=task['status'], project_files=[x for x in task['examined_checkpoint_inventory'] if x['path'].startswith('project/')], tool_call_counts=counts, parent_dispatches=[dict(id=d['id'], status=d['status'], provider_calls=d['provenance'].get('provider_calls'), context_checkpoint=d['provenance'].get('context_checkpoint'), feedback=d['provenance'].get('feedback'), implementation_files=d['provenance'].get('work_progress', {}).get('implementation_files')) for d in parents], unchanged_slices=task['context'].get('builder_work_progress', {}).get('unchanged_slices')))
        all_commands.extend(dict(task_id=task['id'], **c) for c in commands)
        record = records[task['id']]
        assert record['state'] in repair.ACTIVE

        def transition(_task, original, state, reason, details):
            # A local counterfactual result, never a persisted event or timestamp.
            return dict(original, state=state, revision=original['revision'] + 1, reason=reason, evidence=details)

        reason = 'Builder remained unchanged after targeted replanning. Recorded integration/implementation repair is required before further spending; original checkpoint retained.'
        with patch.object(repair, 'enabled', return_value=True), patch.object(repair, 'rows', return_value=[record]), patch.object(repair, 'transition', side_effect=transition), patch.object(repair.store, 'rpc', side_effect=AssertionError('No database writes permitted')), patch.object(repair.store, 'artifact_bytes', side_effect=AssertionError('No network reads permitted')):
            value = repair.route(task, 'blocked', copy.deepcopy(task['context']), task['stage'], reason)
            assert value['status'] == 'queued' and value['context']['repair_progress']['state'] == 'diagnosing'
            control = dict(task_id=task['id'], kind='controlled-offline-state-transition', input_status='blocked', observed_status=value['status'], observed_repair_state=value['context']['repair_progress']['state'], demonstrated='The no-progress stop reason is converted to another queued repair; no model or database call occurred.', stopping_controls=[])
            for stop in ('budget', 'deadline', 'cancelled'):
                stopped = repair.route(task, stop, copy.deepcopy(task['context']), task['stage'], stop)
                assert stopped['status'] == stop
                control['stopping_controls'].append(stop)
            external = copy.deepcopy(task['context'])
            external['blockers'] = [dict(kind='equipment')]
            stopped = repair.route(task, 'blocked', external, task['stage'], 'Controlled external prerequisite')
            assert stopped['status'] == 'blocked'
            control['external_blocker_remains_blocked'] = True
            report['repair_controls'].append(control)
    for entry in supplement['requests']:
        path = supplement_path.parent / entry['file']
        original = path.read_bytes()
        assert digest(original) == entry['sha256']
        request = json.loads(original)
        assert request['model'] == 'gpt-6.1-sol' and len(original) <= builder.MAX_REQUEST and not request.get('previous_response_id') and not request.get('background')
        request.update(store=False, stream=True, model='gpt-6.1-sol')
        raw = canonical(request)
        independent = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        assert raw == independent and len(raw) > builder.CONTEXT_CHECKPOINT_BYTES
        messages = [x for x in request['input'] if x.get('role')]
        message_sizes = []
        for message in messages:
            content = message['content']
            text = content if isinstance(content, str) else '\n'.join(x.get('text', '') for x in content)
            message_sizes.append(dict(role=message['role'], utf8_text_bytes=len(text.encode())))
        outputs = [x for x in request['input'] if x.get('type') == 'function_call_output']
        report['native_boundaries'].append(dict(task_id=entry['task_id'], dispatch_id=entry['dispatch_id'], original_sha256=digest(original), reconstructed_admission_sha256=digest(raw), reconstructed_bytes=len(raw), boundary_bytes=builder.CONTEXT_CHECKPOINT_BYTES, over_by_bytes=len(raw) - builder.CONTEXT_CHECKPOINT_BYTES, message_sizes=message_sizes, tool_schema_bytes=len(canonical(request['tools'])), exposed_tools=[t['name'] for t in request['tools']], output_bytes=[len(x['output'].encode()) for x in outputs], mechanism='The exact production admission expression rejects this reconstructed request before provider admission. This proves the local size stop, not future model behavior.'))
        evidence.append(dict(path=str(path.relative_to(ROOT)), sha256=digest(original)))
    completed = [d for d in data['dispatches'] if d['status'] == 'complete']
    assert len(completed) == 13 and all(d['provenance'].get('context_checkpoint') and not d['provenance']['work_progress']['implementation_files'] for d in completed)
    report['summary'] = dict(claim_tasks=5, verified_original_artifacts=len(data['artifact_reads']) + len(supplement['requests']), selected_parent_dispatches=15, completed_context_stops=len(completed), unconfirmed_parent_dispatches=sum(d['status'] == 'unknown' for d in data['dispatches']), retained_native_tool_calls=len(all_commands), tool_call_counts=dict(collections.Counter(c['name'] for c in all_commands)), project_files=0, exact_boundaries_reproduced=5, no_progress_stop_requeued=5, budget_deadline_cancel_controls=15, external_blocker_controls=5)
    contracts = []
    for task in data['tasks']:
        parent = next(d for d in completed if d['task_id'] == task['id'])
        contract = json.loads(parent['request_raw'])['builder']['context']['runner_contracts']['netem-iperf-v1']['output_contract']
        assert contract['version'] == 'netem-observation-identities-v1' and 'loss:0' in contract['key_rule'] and 'null' in contract['missing']
        contracts.append(dict(task_id=task['id'], dispatch_id=parent['id'], contract_sha256=digest(canonical(contract)), output_contract=contract))
    report['already_supplied_observation_contracts'] = contracts
    # Only the three source-specified fields used by this allowance formula.
    # This is not an executable configuration or a newly chosen scientific input.
    budget_inputs = dict(rate_mbit=100, duration_seconds=30, loss_levels_pct=[0, 1, 2, 5, 10])
    required = netem_iperf.network_budget(budget_inputs)
    independent = 100 * 1000000 * 30 * 5 * 10 // 8 + 10000000
    assert required == independent == 18760000000 and required > 10000000000
    report['source_grid_admission_conflict'] = dict(source='Archived paper-text.json page 2 and page 5; original PDF SHA-256 77becb203ef79c5e5d0b69ee9cfc5553e5680d2c44128aaa6b8f2c545d533617', formula_inputs=budget_inputs, required_counter_allowance_bytes=required, maximum_execution_allowance_bytes=10000000000, fits_current_admission=False, headline_two_condition_allowance_bytes=netem_iperf.network_budget(dict(budget_inputs, loss_levels_pct=[0, 5])), scope='Per-host invocation enforcement allowance counting multiple veth interfaces, not measured traffic or billed Internet egress. Shared source/implementation assumptions; not a scientific finding. The exact full grid is inadmissible through this built-in single-invocation path under current bounds; other validated package/campaign designs were not tested.')
    report['published_values_or_new_scientific_measurements'] = None
    report['review_limits'] = ['Full checkpoint histories retained; 428 call argument records inventoried. Selected recent commands, exact five boundary requests, ten terminal native responses and current feedback examined; not every historical tool-output byte was substantively reviewed.', 'Two selected parent outcomes were unknown at capture and are not relabeled; no uncertain call was replayed.', 'No live clean-context versus retained-context model comparison; restarting or a narrower packet producing code is unproven.', 'Passing software qualification fixtures did not cover this full paper-context failure mode.', 'Separate database reads span a changing assessment. Commands and continuations are dependent observations, not independent replications.']
    report['original_artifact_manifest'] = evidence
    (out / 'analysis.json').write_bytes(canonical(report))
    (out / 'command-inventory.json').write_bytes(canonical(all_commands))
    (out / 'producer.py').write_bytes(Path(__file__).read_bytes())
    manifest = [dict(path=p.name, bytes=p.stat().st_size, sha256=digest(p.read_bytes()), independent_sha256=subprocess.check_output(['shasum', '-a', '256', str(p)], text=True).split()[0]) for p in sorted(out.iterdir()) if p.is_file()]
    assert all(a['sha256'] == a['independent_sha256'] for a in manifest)
    (out / 'manifest.json').write_bytes(canonical(manifest))
    print(json.dumps(dict(directory=str(out), summary=report['summary'], analysis_sha256=digest((out / 'analysis.json').read_bytes()))))


if __name__ == '__main__':
    main()
