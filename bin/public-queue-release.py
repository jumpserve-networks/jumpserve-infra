"""Fixed-target shared queue release; no arbitrary SQL, shell or study inputs."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_queue_prior', ROOT / 'bin/openclaw-release.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
STUDY = 'e79f5cab-d28f-4cea-bf0c-3407933c8cfd'
BACKEND = '2b67fba72e7a672e6b25a73e9e7b9339a019e32e'
EXPECTED_TITLE = 'Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays'
BASE = 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research'
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def title_evidence(directory):
    """Read only the fixed paper's retained packet; never re-extract or persist it."""
    study = r.admin.query("select title,paper_upload from research_studies where id='" + STUDY + "'")
    if len(study) != 1: raise RuntimeError('Expected retained uploaded study.')
    upload = study[0]['paper_upload']; original_sha = upload['sha256']
    if not re.fullmatch('[a-f0-9]{64}', original_sha): raise RuntimeError('Invalid original PDF identity.')
    records = r.admin.query("select id::text,sha256,byte_count,storage_path from research_artifacts where study_id='" + STUDY + "' and provenance->>'kind'='derived-pdf-text' and provenance->>'original_sha256'='" + original_sha + "' order by created_at desc,id desc limit 1")
    if len(records) != 1: raise RuntimeError('The retained original has no text packet.')
    record = records[0]
    if record['byte_count'] > 8_000_000 or record['storage_path'] != STUDY + '/' + record['sha256']: raise RuntimeError('Invalid retained packet identity or bound.')
    key = r.aws('secretsmanager', 'get-secret-value', '--secret-id', 'jumpserve/supabase-service-key')['SecretString']
    url = 'https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/' + record['storage_path']
    req = urllib.request.Request(url, headers={'apikey': key, 'Authorization': 'Bearer ' + key})
    with r.prior.guard.OPEN.open(req, timeout=30) as response: raw = response.read(8_000_001)
    if len(raw) != record['byte_count'] or sha(raw) != record['sha256']: raise RuntimeError('Retained packet bytes/hash differ.')
    packet = json.loads(raw)
    if packet['original_sha256'] != original_sha or packet['pages'][0]['page'] != 1: raise RuntimeError('Retained first-page identity differs.')
    lines = [line.strip() for line in packet['pages'][0]['text'].splitlines() if line.strip()][:12]
    if not any(' '.join(lines[:n]) == EXPECTED_TITLE for n in range(1, 5)): raise RuntimeError('Expected title was not independently found at the start of page 1.')
    (directory / 'retained-title-text-packet.json').write_bytes(raw)
    prompt = r.admin.query("select initial_sha256 from research_autonomy_workflows where study_id='" + STUDY + "'")
    return dict(study_id=STUDY, expected_title=EXPECTED_TITLE, retained_study_title=study[0]['title'],
        original_pdf_sha256=original_sha, text_artifact_id=record['id'], text_packet_sha256=sha(raw), text_packet_bytes=len(raw),
        first_page_front_matter=lines[:4], initial_prompt_identity=prompt,
        study_identity_sha256=sha(json.dumps(study, sort_keys=True, separators=(',', ':')).encode()),
        stored_packet_hash_verified=True, independent_title_check='Exact concatenation of first 1–4 nonempty lines; no model or production title helper.',
        limitation='Title inspection only, not substantive review or claim verification.')

def request(path, method='GET'):
    req = urllib.request.Request(BASE + path, data=b'{}' if method == 'POST' else None,
        method=method, headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
    try:
        with r.prior.guard.OPEN.open(req, timeout=35) as response: return response.status, response.read(4_000_001)
    except urllib.error.HTTPError as error: return error.code, error.read(10000)

def public_check(directory):
    code, raw = request('/studies/' + STUDY + '/queue?public=1')
    if code != 200 or len(raw) > 4_000_000: raise RuntimeError('Public queue is unavailable or exceeds its byte budget.')
    data = json.loads(raw)
    if data['version'] != 'research-public-queue-v1' or data['access'] != 'public-read-only' or data['study']['id'] != STUDY:
        raise RuntimeError('Shared queue identity/access differs.')
    if data['study']['title'] != EXPECTED_TITLE: raise RuntimeError('Public queue still lacks the retained paper title.')
    forbidden = {'owner_id', 'actor_id', 'requester_email', 'initial_prompt', 'initial_sha256', 'request', 'request_raw',
        'raw_response', 'output', 'usage', 'context', 'required_inputs', 'lease_token', 'exclusive_resources',
        'storage_path', 'paper_upload', 'input_artifact_id', 'original_artifact_id', 'details', 'events'}
    def inspect(value):
        if isinstance(value, dict):
            if set(value) & forbidden: raise RuntimeError('Private fields were included in public status.')
            for item in value.values(): inspect(item)
        elif isinstance(value, list):
            for item in value: inspect(item)
    inspect(data)
    (directory / 'public-status-original.json').write_bytes(raw)
    actual_tasks = r.admin.query("select id::text,study_id::text,claim_id::text,stage,status,label,attempts from research_autonomy_tasks where study_id='" + STUDY + "' order by id")
    keys = ('id', 'study_id', 'claim_id', 'stage', 'status', 'label', 'attempts')
    observed = sorted([{k: t[k] for k in keys} for t in data['autonomy']['tasks']], key=lambda t: t['id'])
    if observed != actual_tasks or data['autonomy']['coverage']['tasks'] != len(actual_tasks): raise RuntimeError('Public task coverage differs from the recorded paper.')
    actual_jobs = r.admin.query("select j.id::text,j.study_id::text,j.status,j.execution_mode,r.status run_status from research_queue_jobs j left join research_runs r on r.id=j.run_id and r.study_id=j.study_id where j.study_id='" + STUDY + "' order by j.id")
    job_keys = ('id', 'study_id', 'status', 'execution_mode', 'run_status')
    observed_jobs = sorted([{k: j[k] for k in job_keys} for j in data['jobs']], key=lambda j: j['id'])
    if observed_jobs != actual_jobs or data['coverage']['jobs'] != len(actual_jobs): raise RuntimeError('Public job coverage differs.')
    workflow = r.admin.query("select status,max_spend_cents,committed_cents,max_attempts from research_autonomy_workflows where study_id='" + STUDY + "'")
    observed_workflows = [{k: w[k] for k in ('status', 'max_spend_cents', 'committed_cents', 'max_attempts')} for w in data['autonomy']['workflows']]
    if workflow != observed_workflows: raise RuntimeError('Public workflow commitments/status differ.')
    denials = []
    for path, method in [('/queue', 'GET'), ('/studies?mine=1', 'GET'), ('/studies/' + STUDY + '/queue', 'GET'),
                         ('/studies/' + STUDY + '/autonomy', 'GET'), ('/studies/' + STUDY + '/queue-actions', 'POST'),
                         ('/studies/' + STUDY + '/autonomy', 'POST')]:
        status, _ = request(path, method)
        if status != 401: raise RuntimeError('Anonymous private access/write was not denied.')
        denials.append(dict(path=path, method=method, status=status))
    status, _ = request('/studies/00000000-0000-4000-8000-000000000001/queue?public=1')
    if status != 404: raise RuntimeError('Unknown paper must be unavailable, not an empty queue.')
    ideas = r.admin.query("select id::text from research_studies where study_kind='idea' order by id limit 1")
    idea_denied = None
    if ideas:
        status, _ = request('/studies/' + ideas[0]['id'] + '/queue?public=1')
        if status != 404: raise RuntimeError('Unpublished idea was exposed as a paper queue.')
        idea_denied = True
    return dict(study_id=STUDY, paper_title=data['study']['title'], public_response_sha256=sha(raw), response_bytes=len(raw), tasks=len(actual_tasks),
        candidate_claims=sum(t['claim_id'] is not None for t in actual_tasks), jobs=len(actual_jobs), workflow=workflow,
        database_identity_coverage_matches=True, private_fields_absent=True, anonymous_denials=denials,
        missing_paper_status=404, unpublished_idea_denied=idea_denied,
        limitation='Separate status/database reads; this paper was stopped and stable during verification. No experiment was restarted.')

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=['diff', 'deploy', 'public-check', 'title-preview']); args = parser.parse_args()
    directory = ROOT / '.test-artifacts/public-queue-release' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    manifest_raw = (ROOT / 'research-workflow-runtime.json').read_bytes(); manifest = json.loads(manifest_raw)
    if manifest['version'] != 37 or manifest['source_revision'] != BACKEND: raise RuntimeError('Unexpected release revision.')
    report = dict(protocol='paper-queue-title-production-release-v1', mode=args.mode, status='running', runtime_manifest_sha256=sha(manifest_raw),
        backend_revision=BACKEND, started_at=dt.datetime.now(dt.timezone.utc).isoformat(), measured_charges_usd=None)
    try:
        report['targets'] = r.target()
        report['title_evidence'] = title_evidence(directory)
        if args.mode in ('diff', 'deploy'): report['cdk'] = r.cdk(args.mode, directory, activate=True)
        elif args.mode == 'public-check': report['public_check'] = public_check(directory)
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error)); raise
    finally:
        report['ended_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        (directory / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(directory=str(directory), **report), indent=2))

if __name__ == '__main__': main()
