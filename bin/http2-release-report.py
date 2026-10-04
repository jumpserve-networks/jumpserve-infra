"""Freeze HTTP/2 release evidence; optionally save its immutable private DB record."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'jumpserve-back-end'
FRONTEND = ROOT.parent / 'jumpserve-front-end'
STUDY = BACKEND / 'experiments/http2_compliance'
CAMPAIGN = 'http2-compliance-artifact-v2'
PROJECT = 'regphejnlvfpyokpniny'
ACCOUNT = '395567831870'
REPORT = ROOT / 'docs/http2-release-report.json'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate():
    if REPORT.exists():
        raise RuntimeError("Release report v1 is frozen; use --save or create a new report version")
    data = read(STUDY / 'results/assessment-v3.json')
    scientific = read(STUDY / 'evidence/assessment-v3.json')
    sources = read(STUDY / 'evidence/source-hash-validation.json')
    deployed = read(ROOT / '.test-artifacts/http2-deployed-agent-verification.json')
    http = read(FRONTEND / '.test-artifacts/http2-verify-production.json')
    storage = read(ROOT / '.test-artifacts/http2-original-storage.json')
    prompt = read(FRONTEND / 'public/module/http2-compliance-study/chat-release.json')
    evaluation = prompt['evaluation']
    assert scientific['status'] == deployed['status'] == 'pass'
    assert sources['status'] == 'pass' and sources['hash_verified'] == 40 and sources['unavailable'] == 9
    assert sources['inventory_sha256'] == digest(STUDY / 'literature.json'), 'Changed source inventory'
    assert http['passed'] and all(c['passed'] for c in http['checks'])
    assert http['origin'] == 'https://jumpserve.quaint-lab.org', 'Not production verification'
    assert deployed['aws_account'] == ACCOUNT and deployed['supabase_project'] == PROJECT
    assert storage['project'] == PROJECT and len(storage['files']) == 97
    assert all(f['round_trip'] == 'pass' for f in storage['files'])
    assert len(evaluation['cases']) == 8 and all(c['passed'] for c in evaluation['cases'])
    assert evaluation['human_review']['passed'] is True
    assert evaluation['prompt_content_sha256'] == prompt['content_sha256']
    assert data['campaign']['id'] == CAMPAIGN and len(data['measurements']) == 7176
    directory = ROOT / 'docs/http2-validation'
    directory.mkdir(exist_ok=True)
    evidence = []
    for path, name in (
        (ROOT / '.test-artifacts/http2-deployed-agent-verification.json', 'agent-verification.json'),
        (FRONTEND / '.test-artifacts/http2-verify-production.json', 'production-http.json'),
        (ROOT / '.test-artifacts/http2-original-storage.json', 'original-storage-manifest.json'),
    ):
        shutil.copyfile(path, directory / name)
        evidence.append({'path': 'docs/http2-validation/' + name, 'sha256': digest(path)})
    screenshots = []
    for name in ('desktop', 'mobile-dark', 'mobile-light'):
        path = Path('/private/tmp') / ('http2-production-' + name + '.png')
        target = directory / (name + '.png')
        shutil.copyfile(path, target)
        screenshots.append({'path': 'docs/http2-validation/' + target.name, 'sha256': digest(target)})
    downloads = []
    expected = {c['name']: c['evidence'] for c in http['checks']}
    for path, name, comparison in (
        (Path('/private/tmp/http2-production-browser.csv'), 'CSV', 'complete CSV with missing error codes'),
        (Path('/private/tmp/http2-production-chat-release.json'), 'prompt/answers JSON', 'published prompt and evaluated answer provenance'),
    ):
        actual = digest(path)
        assert actual == expected[comparison]['sha256'], 'Browser download changed'
        downloads.append({'format': name, 'sha256': actual, 'status': 'pass'})
    reports = [read(p) for p in sorted((ROOT / '.test-artifacts').glob('http2-agent-evaluation-*.json'))]
    assert len(reports) == 12 and all(r['module_id'] == 'http2-compliance-study' for r in reports)
    calls = [u for r in reports for c in r['cases'] for key in ('answer_usage', 'judge_usage') if (u := c.get(key))]
    costs = {
        'evaluation_records': len(reports),
        'input_tokens': sum(u['tokens'].get('inputTokens', 0) for u in calls),
        'output_tokens': sum(u['tokens'].get('outputTokens', 0) for u in calls),
        'estimated_model_cost_usd': sum(u['estimated_usd'] for u in calls),
        'failed_scenarios_without_complete_usage': sum(c.get('status') == 'failed' and not c.get('answer_usage') for r in reports for c in r['cases']),
        'incremental_purchased_experiment_compute_usd': 0,
        'aws_experiment_instances': 0,
        'raw_storage_bytes': storage['total_bytes'],
        'limitation': 'Token list-price estimate, not reconciled billing. Missing failed-call charges, workstation allocation, Codex orchestration, existing hosting/build, storage and transfer charges remain unavailable or unallocated.',
        'models': {},
    }
    for r in reports:
        model = costs['models'].setdefault(r['model_id'], {'input_tokens': 0, 'output_tokens': 0, 'estimated_usd': 0, 'pricing': r['pricing']})
        for c in r['cases']:
            for key in ('answer_usage', 'judge_usage'):
                if usage := c.get(key):
                    model['input_tokens'] += usage['tokens'].get('inputTokens', 0)
                    model['output_tokens'] += usage['tokens'].get('outputTokens', 0)
                    model['estimated_usd'] += usage['estimated_usd']
    browser = {
        'status': 'pass within recorded scope',
        'engine': 'Chromium through agent-browser on macOS; viewport checks, not physical mobile-device tests',
        'viewports': [{'width': 1280, 'height': 900}, {'width': 390, 'height': 844}],
        'checked': [
            'Completed results, methods and 49-entry literature pages; desktop sidebar and mobile Sheet navigation',
            'Dark and Light themes; stable light-theme screenshot after menu animation settled',
            'All four charts visible with SVG titles; no document horizontal overflow at either recorded viewport',
            'Primary Apache 156 cases and Mitmproxy 11.1.0 156 cases/129 unknown rows',
            'All-archive selector has 57 configurations; Envoy-1.34.1-H2H1 has 78 case rows and separately labeled unreported published counts',
            'Methods contain 14 claims, six protocols, failed-run reasons and evaluated prompt link',
            'Literature has 49 records and review counts 3 complete/29 partial/8 unreviewed/9 unavailable',
            'Google sign-in redirect retains editable Mitmproxy configuration deep link',
            'Browser CSV and published prompt downloads match independently verified HTTP hashes',
            'No page errors in inspected browser sessions',
        ],
        'downloads': downloads, 'screenshots': screenshots,
        'gaps': ['No legitimate Google session: actual authenticated deployed chat and OAuth completion not exercised.', 'Safari, Firefox and physical mobile hardware not checked.'],
    }
    report = {
        'version': 'http2-release-report-v1',
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'software_release': 'deployed and verified within stated scope',
        'scientific_coverage': 'partial reproduction; no independent historical proxy/cloud fleet replication',
        'targets': {'aws_account': ACCOUNT, 'aws_profile': 'jumpserve', 'aws_region': 'us-east-1', 'supabase_project': PROJECT},
        'urls': {'module': 'https://jumpserve.quaint-lab.org/module/http2-compliance-study', 'results': 'https://jumpserve.quaint-lab.org/module/http2-compliance-study/test-results', 'methods': 'https://jumpserve.quaint-lab.org/module/http2-compliance-study/methods', 'literature': 'https://jumpserve.quaint-lab.org/module/http2-compliance-study/literature', 'data': 'https://jumpserve.quaint-lab.org/module/http2-compliance-study/api/results', 'prompt_and_answers': 'https://jumpserve.quaint-lab.org/module/http2-compliance-study/chat-release.json'},
        'release': {'frontend_commit': '8ff00eab249e79c355e6ce7c34326ef6f89f31cf', 'amplify_app': 'd24jvguj7brnkj', 'amplify_job': '100', 'amplify_status': 'SUCCEED', 'amplify_ended_at': '2026-10-04T18:31:35.488000-05:00', 'evaluated_agent_implementation_commit': '4c2e56bb4899fcf0fae9ccf273260476963de72f', 'infra_branch': 'study/http2-compliance', 'backend_commit_at_verification': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip(), 'agent_stack': 'JumpServeAgentStack', 'agent_status': 'UPDATE_COMPLETE', 'scope': 'Only Agent stack and existing frontend Amplify build; no experiment instances or unrelated infrastructure deployment.'},
        'paper': {'doi': '10.1145/3730567.3764447', 'version': 'ACM version of record supplied by user', 'sha256': digest(STUDY / 'sources/main-paper.pdf'), 'review': '16 pages, Figures 1–8, Tables 1–9, Appendices A–B; all pages visually examined. Figure 4 raster cells not all independently checked.'},
        'literature': {'entries': len(data['sources']), 'review_counts': dict(Counter(s['review_status'] for s in data['sources'])), 'original_hashes_checked': 40, 'unavailable_reference_numbers': [s['reference_number'] for s in data['sources'] if s['review_status'] == 'unavailable'], 'inventory': 'jumpserve-back-end/experiments/http2_compliance/literature.json', 'review_notes': 'jumpserve-back-end/experiments/http2_compliance/review-notes.json', 'hash_validation': 'jumpserve-back-end/experiments/http2_compliance/evidence/source-hash-validation.json', 'scope': 'Main plus 48 direct citations; no recursive bibliography expansion. Downloaded/unreviewed and partial reviews do not establish complete literature coverage.'},
        'protocols': data['protocols'],
        'reproduction_commands': 'jumpserve-back-end/experiments/http2_compliance/README.md',
        'artifact_commit': data['campaign']['artifact_commit'],
        'frozen_bundle_sha256': digest(STUDY / 'results/assessment-v3.json'),
        'counts': {'configurations': len(data['configurations']), 'successful_archived_runs': 57, 'failed_runs': 3, 'saved_runs': len(data['runs']), 'archived_measurements': len(data['measurements']), 'summaries': len(data['summaries']), 'loopback_pilot_measurements': 12, 'loopback_main_measurements': 72, 'source_records': 49, 'claim_records': 14, 'original_storage_files': 97},
        'claim_status_counts': dict(Counter(c['assessment'] for c in data['claims'])),
        'claim_assessment': data['claims'],
        'scientific_validation': scientific,
        'database': {'migrations': [p.name for p in sorted((ROOT / 'database').glob('2026100400*.sql')) if '202610040003' <= p.name[:12] <= '202610040010'], 'relations': 'Ten public SELECT-only result relations and one backend-only artifact relation; RLS retained and browser writes denied.', 'raw_originals': {'files': 97, 'bytes': storage['total_bytes'], 'source_files': 40, 'author_json_files': 57, 'bucket': 'http2-study-artifacts', 'visibility': 'private; browser read/write denied by restrictive policy', 'all_round_trip_hashes': 'pass', 'manifest_sha256': digest(ROOT / '.test-artifacts/http2-original-storage.json')}, 'missing_data': 'Missing dates, resource counts and unavailable values remain null. Unknown classifier outcomes remain explicit. Published values remain separate.'},
        'chat': {'prompt_id': prompt['id'], 'prompt_version': prompt['version'], 'prompt_content_sha256': prompt['content_sha256'], 'published_at': prompt['published_at'], 'evaluation_id': evaluation['id'], 'evaluation_version': evaluation['evaluation_version'], 'model_id': evaluation['model_id'], 'model_temperature': evaluation['model_temperature'], 'analysis_version': evaluation['analysis_version'], 'renderer_version': evaluation['renderer_version'], 'passed_cases': [c['name'] for c in evaluation['cases']], 'secondary_review': evaluation['human_review'], 'review_label_limitation': 'Historical human_review key and human-review wording identify an AI agent in reviewer_type. No human scientific review or user approval is claimed.', 'history': [{'id': r['id'], 'version': r.get('evaluation_version'), 'prompt_version': r['prompt_version'], 'model_id': r['model_id'], 'started_at': r['started_at'], 'ended_at': r.get('ended_at'), 'passed_cases': sum(c.get('passed') is True for c in r['cases']), 'failed_scenarios': sum(c.get('status') == 'failed' for c in r['cases']), 'secondary_review_passed': r.get('human_review', {}).get('passed')} for r in reports], 'limitations': ['Eight fixed regression questions, one response each; not a reliability sample.', 'Earlier free-form/typed rounds and failures retained. Automatic-only v3 publication was disabled after AI secondary review found a false claim, before HTTP2 backend deployment.', 'Model selects bounded evidence topics; backend renders recorded numerical claims. Extra topics/duplicate explanations can occur.', 'No actual Google-authenticated deployed chat request was possible.']},
        'checks': {'scientific': 'Independent integer conservation, ID/pair universe, published comparator, raw-frame units and source hash checks pass; discrepancies remain findings.', 'frontend': {'tests_passed': 105, 'lint': 'pass', 'production_build': 'pass'}, 'backend_agent': {'python_tests_passed': 71, 'infra_jest_passed': 69, 'infra_jest_skipped': 5, 'typescript_build': 'pass'}, 'database': 'Isolated transactional PostgreSQL checks pass for migrations 003–010, public SELECT/write denial, uint32 bounds, module ownership, prompt publication, answer provenance and restrictive private Storage policy; fixtures rolled back.', 'production_http': http, 'deployed_agent': deployed, 'browser': browser},
        'costs': costs,
        'retained_validation_files': evidence,
        'remaining_work': ['Nine full texts unavailable; 29 partial and eight unreviewed supporting entries remain incomplete.', 'Independent historical proxy/cloud fleet and TLS causality, exploits/prevalence, normative-suite intervention and complete case-level RFC semantics remain uncovered.', 'Figure 4 individual raster cells not all independently checked; Figure 7/8 checks cover transcribed numerical claims, not every plotted bar.', 'Actual Google-authenticated deployed chat/OAuth completion unavailable; signed-out routing and anonymous API denial verified.', 'Failed-call costs and total service billing are not reconciled.'],
    }
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    return {'path': str(REPORT), 'sha256': digest(REPORT), 'software_release': report['software_release'], 'scientific_coverage': report['scientific_coverage']}


def save():
    account = subprocess.check_output(['aws', 'sts', 'get-caller-identity', '--profile', 'jumpserve', '--query', 'Account', '--output', 'text'], text=True).strip()
    assert account == ACCOUNT, 'Wrong AWS account'
    spec = importlib.util.spec_from_file_location('prompt_admin', ROOT / 'bin/agent-prompts.py')
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    assert admin.PROJECT_REF == PROJECT
    report = read(REPORT)
    assert report['targets']['aws_account'] == ACCOUNT and report['targets']['supabase_project'] == PROJECT
    rows = admin.query("select protocol_sha256,analysis_sha256 from http2_study_campaigns where id=" + admin.literal(CAMPAIGN))
    original = read(STUDY / 'results/assessment-v3.json')['campaign']
    assert len(rows) == 1 and all(rows[0][k] == original[k] for k in ('protocol_sha256', 'analysis_sha256'))
    active = admin.query("select active_version_id from agent_prompt_settings where module_id='http2-compliance-study'")
    assert len(active) == 1 and active[0]['active_version_id'] == report['chat']['prompt_id'], 'Changed active prompt'
    sha = digest(REPORT)
    payload = {'campaign_id': CAMPAIGN, 'id': 'release-report-v1', 'sha256': sha, 'source_path': 'docs/http2-release-report.json', 'byte_count': REPORT.stat().st_size, 'payload': report}
    admin.query('insert into http2_study_artifacts select * from jsonb_populate_record(null::http2_study_artifacts,' + admin.literal(json.dumps(payload)) + '::jsonb) on conflict(campaign_id,id) do nothing', read_only=False)
    stored = admin.query("select sha256,payload from http2_study_artifacts where campaign_id=" + admin.literal(CAMPAIGN) + " and id='release-report-v1'")
    assert len(stored) == 1 and stored[0]['sha256'] == sha and stored[0]['payload'] == report, 'Immutable saved report differs; use a new version'
    return {'project': PROJECT, 'artifact_id': 'release-report-v1', 'sha256': sha, 'round_trip': 'pass'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save', action='store_true', help='Save existing report immutably after checking AWS/Supabase targets')
    args = parser.parse_args()
    print(json.dumps(save() if args.save else generate(), indent=2))
