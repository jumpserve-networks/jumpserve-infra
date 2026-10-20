"""Fixed local evidence synthesis; does not run tests or contact any service."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / 'jumpserve-front-end'


def record(path, base=ROOT):
    raw = (base / path).read_bytes()
    return dict(repository=base.name, path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    destination = ROOT / 'docs/autonomy-bounded-followups-validation-v1.json'
    if destination.exists():
        raise RuntimeError('Preserve original report; a correction requires a new version.')
    database_path = '.test-artifacts/research-ideas/database/20261019T235728681004Z/autonomy-validation-report.json'
    browser_path = '.test-artifacts/research-autonomy/2026-10-19T23-40-53.593Z/validation-report.json'
    database = json.loads((ROOT / database_path).read_bytes())
    browser = json.loads((FRONTEND / browser_path).read_bytes())
    assert database['passed'] and len(database['checks']) == 11
    assert browser['passed'] and len(browser['checks']) == 7
    calls = reserved = estimated = input_tokens = output_tokens = 0
    campaigns = []
    for version in ('v1', 'v2', 'v3', 'v4'):
        path = '.test-artifacts/autonomy-followups/' + version + '/evaluation-report.json'
        result = json.loads((ROOT / path).read_bytes())
        campaigns.append(dict(version=version, original_report=record(path),
            frozen_inputs=record('.test-artifacts/autonomy-followups/' + version + '/frozen-inputs.json'),
            original_strict_passed_cases=sum(c['status'] == 'complete' and all(c.get('deterministic_checks', {}).values()) for c in result['cases']),
            total_cases=len(result['cases']), completion_passed=result.get('passed'),
            provider_calls=result['live_provider_calls'], reserved_cents=result['reserved_cents'], estimated_cents=result['known_estimated_cents']))
        calls += result['live_provider_calls']
        reserved += result['reserved_cents']
        estimated += result['known_estimated_cents']
        for case in result['cases']:
            usage = case.get('usage') or {}
            input_tokens += usage.get('inputTokens', 0)
            output_tokens += usage.get('outputTokens', 0)
    assert (calls, reserved, estimated) == (20, 945, 199)
    manifest = json.loads((ROOT / 'research-workflow-runtime.json').read_bytes())
    report = dict(version='autonomy-bounded-followups-validation-v1',
        protocol='autonomy-bounded-followups-protocol-v1', amendments=['v2-superseded', 'v3', 'v4-post-evaluation', 'v5-predeclared-completion', 'v6-fixture-correction'],
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(), passed=True,
        passed_scope='Selected local implementation and integration checks only; not model publication or production release readiness',
        publication_ready=False, release_status='blocked: predeclared two-turn completion criterion failed',
        report_producer='Primary Codex AI synthesis of retained reports and observed command results; command counts normalized from tool transcript, not original test stdout artifacts',
        reviewer=dict(identity='Primary Codex AI implementer', type='AI', independent=False, human_review=False),
        targets=dict(aws_account='395567831870', aws_region='us-east-1', supabase_project='regphejnlvfpyokpniny',
            aws_account_verified_after_sign_in=True, supabase_local_configuration_verified=True, remote_supabase_mutation=False, unrelated_connected_project_not_used=True),
        source_profile=dict(runtime_manifest=record('research-workflow-runtime.json'), files=manifest['files'], manifest_version=manifest['version'], uncommitted=True,
            base_commits=dict(backend='135184d13c7b4363ca9db9d5d640e5c3434fa0b6', frontend='5c43799d9651997f0a5be3eeb84d61be4b07b0af', infra='beb6cb8132550deb4812f50df6950030680b24f0'),
            limitation='source_revision is the previous clean base; revision_status and exact file hashes identify the local candidate. Commit and pin before a future authorized release.'),
        commands=[dict(repository='jumpserve-back-end', command='python3 -B -m unittest discover -s research_workflow/tests -v', passed=True, tests=161),
            dict(repository='jumpserve-front-end', command='npm test', passed=True, tests=187),
            dict(repository='jumpserve-front-end', command='npm run lint', passed=True, errors=0, warnings=1, warning='Pre-existing auth-button.tsx:153 internal window.location.assign'),
            dict(repository='jumpserve-front-end', command='npm run build', passed=True),
            dict(repository='jumpserve-infra', command='npm run build', passed=True),
            dict(repository='jumpserve-infra', command='env JUMPSERVE_BACKEND_CHECKOUT=/Users/Shared/allstar/jumpserve-back-end npm test -- --runInBand', passed=True, tests=93, suites=11, skipped=0),
            dict(repository='jumpserve-infra', command='npm run test:research:autonomy', passed=True, groups=11, report=record(database_path)),
            dict(repository='jumpserve-front-end', command='npm run verify:research:autonomy', passed=True, groups=7, report=record(browser_path, FRONTEND))],
        automated_tests_passed=441, database_checks=database['checks'], browser_checks=browser['checks'], migration_sha256=database['migration_sha256'],
        model=dict(model_id='us.anthropic.claude-opus-4-6-v1', temperature=0, maximum_output_tokens=4096, provider_retries=0,
            campaigns=campaigns, actual_provider_calls=calls, provider_call_failures=0, failed_evaluations_retained=True,
            original_v8_strict_passes=8, original_v8_strict_total=9, held_out=False,
            review='Primary AI inspected actual raw structured SDK and rendered answers; not independent or human review',
            raw_evidence='Original AWS CLI stdout and canonical SDK messages; original provider HTTP bytes unavailable',
            completion='Corrected frozen fixture accepted both scoped reads, but no final assessment within two turns; original criterion failed and publication remains blocked'),
        usage=dict(provider_input_tokens=input_tokens, provider_output_tokens=output_tokens, provider_total_tokens=input_tokens+output_tokens,
            known_token_based_conservative_estimate_usd=estimated/100, conservative_reservations_usd=reserved/100, reservation_ceiling_usd=10,
            missing_usage_calls=0, measured_charges_usd=None, storage_charges_usd=None, local_compute_charges_usd=None,
            unallocated_costs='Shared infrastructure, local compute and storage; missing charges are not zero'),
        scientific_scope=dict(archived_cells=1152, figures=['13a', '13b', '14a', '14b', '15a', '15b'], units='percent',
            archived='Numerical agreement under retained configurations/epochs and shared upstream inputs/parser; not raw-pcap completeness, causal, operational or whole-paper validation',
            new_local_tcp=dict(exchanges=2, stored_measurements=4, units=['ms', 'bytes'], environment='TCP over 127.0.0.1; controlled application delay', deployed_cloud=False, aws_transport='Explicit SDK fixture'),
            controlled_discrepancy='Deliberate development mutation in partial-run software regression; not a paper finding',
            uncertainty='Descriptive observations only; repeated exchanges share host/process/connection, no inferential interval'),
        bounds=dict(request_bytes=96000, maximum_final_v8_request_bytes=59620, full_1152_cell_assessment_request_bytes=29991,
            server_records=100000, server_bytes=32000000, reader_bytes=10000, paper_default_commitment_usd=100, paper_elapsed_days=7,
            model_attempts_per_claim=25, parallel_claims_per_paper=2, global_parallel_claims=4,
            tcp=dict(memory_mb=128, timeout_seconds=5, ephemeral_mb=512, max_payload_bytes=65536, max_exchanges=16, max_application_delay_ms=20, max_output_bytes=32000, reservation_cents=1, policy_expires='2026-11-19T00:00:00Z', ec2_instances=0)),
        conditional_gaps=['Deployed immutable TCP source/resources/IAM and watchdog execution', 'Legitimate authenticated Google owner request',
            'Actual provider-to-production-Supabase prompt/response persistence', 'Private remote archive upload/retrieval hash verification',
            'New-runner production exports/result charts', 'Other networking runner cost envelopes', 'Final judgment after the two scoped reads'],
        production_actions=dict(commits=0, pushes=0, merges=0, deployments=0, migrations=0, prompt_publications=0, cloud_network_experiments=0),
        artifact_inventory='docs/autonomy-bounded-followups-artifacts-v1.json',
        artifact_access='Raw bytes remain private in ignored local directories; future upload must verify private Supabase retrieval hashes',
        limitations=['AI implementer/reviewer share code and inputs; no independent, human or held-out validation.',
            'Hashes prove retained bytes, not source review completeness.', 'Passing local implementation tests does not establish release readiness.',
            'Conservative commitments do not cap AWS invoices, lifetime storage, taxes or unallocated charges.'])
    report['retained_database_runs'] = [dict(report=record(str(p.relative_to(ROOT))), passed=json.loads(p.read_bytes()).get('passed'), failure=json.loads(p.read_bytes()).get('failure')) for p in sorted((ROOT/'.test-artifacts/research-ideas/database').glob('20261019T*/autonomy-validation-report.json'))]
    report['retained_browser_runs'] = [dict(report=record(str(p.relative_to(FRONTEND)), FRONTEND), passed=json.loads(p.read_bytes()).get('passed'), failure=json.loads(p.read_bytes()).get('failure')) for p in sorted((FRONTEND/'.test-artifacts/research-autonomy').glob('2026-10-19T*/validation-report.json'))]
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report=str(destination), local_checks_passed=True, publication_ready=False, provider_calls=calls)))


if __name__ == '__main__':
    main()
