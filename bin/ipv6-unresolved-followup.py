"""Fixed-study operator persistence and audit for nine authorized IPv6 follow-ups.

No deployment, migration, other study, publication, model or experiment instance
operations. Credentials and owner identifiers stay in process memory.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'jumpserve-back-end'
OUT = BACKEND / 'experiments/ipv6_dns/followups/20261007-v1'
STUDY = '76c70fd9-0217-464e-8c26-0a47832409a3'
sys.path.insert(0, str(BACKEND / 'research_workflow'))
import workflow
import store
import scheduler
import importer

spec = importlib.util.spec_from_file_location('guard', ROOT / 'bin/research-workflow-database.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)

def save(name, data):
    with (OUT / name).open('x') as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False) + '\n')

def connect():
    target = guard.targets()
    # CLI login-session credentials are resolved by the CLI, never by an older SDK.
    raw = subprocess.check_output(['aws', 'secretsmanager', 'get-secret-value', '--secret-id',
                                  'jumpserve/supabase-service-key', '--profile', 'jumpserve', '--region', 'us-east-1'], timeout=20)
    os.environ['SUPABASE_SERVICE_ROLE_KEY'] = json.loads(raw)['SecretString']
    os.environ['SUPABASE_URL'] = 'https://regphejnlvfpyokpniny.supabase.co'
    # Keep HTTPS verification enabled with the system CA trust used by the admin helper.
    os.environ['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
    owners = store.rows('study_owners', {'study_id': 'eq.' + STUDY, 'limit': 1})
    if len(owners) != 1:
        raise RuntimeError('Fixed study ownership not found')
    return target, owners[0]['owner_id']

def inspect(target, actor):
    snapshot = store.snapshot(STUDY, owner=True)
    jobs = scheduler.snapshot(STUDY, actor)
    records = snapshot['records']
    latest = {}
    for a in records['assessments']:
        latest[a['claim_id']] = a
    gaps = {}
    for g in records['gaps']:
        gaps[g['claim_id']] = g
    result = dict(targets=target, created_at=workflow.now(), read_only=True, study_id=STUDY,
        snapshot_bytes=len(workflow.canonical(snapshot)), coverage=snapshot['coverage'],
        claims=[dict(claim_id=c['id'], origin_claim_id=c['scope'].get('origin_claim_id'),
                     latest_assessment=latest.get(c['id']), latest_gap=gaps.get(c['id'])) for c in records['claims']],
        queue=jobs, actor_identity='Saved study owner, used by an authorized trusted operator; not an authenticated browser request. No owner identifier or credential retained.')
    save('production-before.json', result)
    print(json.dumps(dict(targets=target, snapshot_bytes=result['snapshot_bytes'], coverage=result['coverage'],
        labels={label: sum(a['label'] == label for a in latest.values()) for label in workflow.LABELS}, jobs=len(jobs['jobs'])), indent=2))

def persist(target, actor):
    prepared, raw, originals = importer.prepare(OUT / 'import-v4.json', '4aaf0cfe-4d48-4d52-a66e-7f61b432a918')
    if not store.owns(STUDY, actor):
        raise RuntimeError('Ownership mismatch')
    before = json.loads((OUT / 'production-before.json').read_bytes())
    current_claims = store.rows('claims', {'study_id': 'eq.' + STUDY})
    expected = {c['claim_id']: c['origin_claim_id'] for c in before['claims']}
    if {c['id']: c['scope'].get('origin_claim_id') for c in current_claims} != expected:
        raise RuntimeError('Claim identities changed since the recorded inspection')
    prior_assessments = store.rows('assessments', {'study_id': 'eq.' + STUDY})
    latest = {row['claim_id']: row for row in prior_assessments}
    for entry in prepared['records']:
        if entry['kind'] == 'assessments':
            row = entry['record']
            if latest[row['claim_id']]['id'] not in (row['supersedes_id'], row['id']):
                raise RuntimeError('Assessment changed; preserve history and reconcile before persistence')
    # Conservatively reserve room for server timestamps/IDs and numeric strings.
    # Never make the current interactive workspace unusable by exceeding its 4 MB export.
    predicted = before['snapshot_bytes'] + sum(len(workflow.canonical(e['record'])) + 120 for e in prepared['records'])
    if predicted > 4000000:
        raise RuntimeError(f'Interactive snapshot budget would be exceeded ({predicted} conservative bytes); split the evidence into retained artifacts before storing.')
    artifacts = []
    for name, original, media, provenance in [('import', raw, 'application/json', {'transformation': 'none; original scientific import'})] + [
        (a['path'], a['raw'], a['media_type'], {k: v for k, v in a.items() if k != 'raw'}) for a in originals]:
        record = store.artifact(STUDY, actor, original, str(__import__('uuid').uuid5(__import__('uuid').UUID(prepared['import_id']), name)), media, provenance)
        artifacts.append(dict(kind='artifacts', record=record))
    # Small ordered atomic batches preserve dependency order and bounded requests.
    # The writer rejects changed replay IDs and never replaces existing evidence.
    entries = artifacts + prepared['records']
    receipts = []
    for offset in range(0, len(entries), 160):
        batch = entries[offset:offset + 160]
        literal = guard.admin.literal
        response = guard.admin.query('select public.research_append_bundle(' + literal(STUDY) + '::uuid,' +
            literal(actor) + '::uuid,' + literal(json.dumps(batch, allow_nan=False)) + '::jsonb) as receipt', read_only=False)
        receipts.append(dict(offset=offset, records=len(batch), response=response))
        print('Preserved records', min(offset + len(batch), len(entries)), 'of', len(entries), flush=True)
    jobs = json.loads((OUT / 'queue-requests-v4.json').read_bytes())
    queue_results = []
    for request in jobs:
        result = scheduler.enqueue(STUDY, actor, request['enqueue'])
        action = scheduler.action(STUDY, actor, request['attach'])
        queue_results.append(dict(job_id=request['enqueue']['request_id'], enqueue_replayed=result['replayed'], attach_result=action))
    report = dict(targets=target, created_at=workflow.now(), study_id=STUDY, records=len(prepared['records']),
        artifacts=[dict(id=e['record']['id'], sha256=e['record']['sha256'], byte_count=e['record']['byte_count']) for e in artifacts],
        receipts=receipts, queue=queue_results, actor_identity='Authorized trusted operator using saved study ownership; not a Google session or browser authentication test.',
        published=False, deployment=False)
    save('production-persistence.json', report)
    print(json.dumps(dict(records=report['records'], stored_originals=len(artifacts), jobs=len(queue_results), published=False)))

def verify(target, actor):
    prepared, _, _ = importer.prepare(OUT / 'import-v4.json', '4aaf0cfe-4d48-4d52-a66e-7f61b432a918')
    snapshot = store.snapshot(STUDY, owner=True)
    records = snapshot['records']; by_kind = {kind: {r['id']: r for r in rows} for kind, rows in records.items()}
    for entry in prepared['records']:
        original = entry['record']; retrieved = by_kind[entry['kind']][original['id']]
        for field, value in original.items():
            actual = retrieved[field]
            if field == 'value' and actual is not None:
                from decimal import Decimal
                if Decimal(str(actual)) != Decimal(str(value)):
                    raise RuntimeError('Stored numeric value differs')
            elif actual != value:
                raise RuntimeError('Stored scientific field differs: ' + entry['kind'] + '.' + field)
    receipt = json.loads((OUT / 'production-persistence.json').read_bytes())
    verified = []
    for artifact in receipt['artifacts']:
        raw = store.artifact_bytes(STUDY, artifact['id'], maximum=10000000)
        if hashlib.sha256(raw).hexdigest() != artifact['sha256'] or len(raw) != artifact['byte_count']:
            raise RuntimeError('Stored artifact identity differs after retrieval')
        verified.append(artifact)
    # Independently check all expanded original members of the retrieved container.
    import io, tarfile
    container = next(a for a in receipt['artifacts'] if a['sha256'] == json.loads((OUT / 'input-manifest.json').read_bytes())['sha256'])
    original = store.artifact_bytes(STUDY, container['id'], maximum=10000000)
    manifest = json.loads((OUT / 'input-manifest.json').read_bytes()); covered = set()
    with tarfile.open(fileobj=io.BytesIO(original), mode='r:gz') as archive:
        for m in manifest['members']:
            raw = archive.extractfile(m['path']).read()
            if hashlib.sha256(raw).hexdigest() != m['sha256'] or len(raw) != m['byte_count']:
                raise RuntimeError('Stored expanded original identity differs')
            covered.add(m['path'])
    before = json.loads((OUT / 'production-before.json').read_bytes())
    latest = {r['claim_id']: r for r in records['assessments']}
    queue = scheduler.snapshot(STUDY, actor)
    original_jobs = {j['id']: j for j in before['queue']['jobs']}
    for job in queue['jobs']:
        if job['id'] in original_jobs:
            old = original_jobs[job['id']]
            if job['status'] != old['status'] or job['run_id'] != old['run_id']:
                raise RuntimeError('Original queue job changed')
    report = dict(targets=target, verified_at=workflow.now(), passed=True, study_id=STUDY,
        snapshot_bytes=len(workflow.canonical(snapshot)), stored_records_verified=len(prepared['records']),
        artifact_hashes_verified=verified, expanded_originals_verified=len(covered),
        coverage=snapshot['coverage'], latest_labels={label: sum(r['label'] == label for r in latest.values()) for label in workflow.LABELS},
        new_jobs=[j for j in queue['jobs'] if j['id'] not in original_jobs],
        original_jobs_unchanged=len(original_jobs), published=False,
        limitations=['Trusted operator persistence, not authenticated browser verification', 'AI implementer inspection, no independent or human review', 'Excluded scientific experiments are not software failures'])
    save('production-verification.json', report)
    print(json.dumps({k: report[k] for k in ('passed', 'snapshot_bytes', 'stored_records_verified', 'expanded_originals_verified', 'latest_labels', 'original_jobs_unchanged')}, indent=2))

def evidence(target, actor):
    """Save only the fixed follow-up reports and two examined archival sources."""
    files = ('local-verification.json', 'production-persistence.json', 'production-verification.json',
             'source-inventory.json', 'paired-sensitivity-check.json', 'report.md', 'report-v2.md', 'comparisons.csv')
    artifacts = []
    import uuid
    for name in files:
        raw = (OUT / name).read_bytes()
        media = 'text/markdown' if name.endswith('.md') else 'text/csv' if name.endswith('.csv') else 'application/json'
        record = store.artifact(STUDY, actor, raw, str(uuid.uuid5(uuid.UUID('60fd3146-aabc-4d2b-b17e-c74f03eec01f'), name)), media,
            dict(version='unresolved-followup-v1', transformation='None; original retained follow-up report bytes', name=name))
        store.append(STUDY, actor, 'artifacts', record)
        retrieved = store.artifact_bytes(STUDY, record['id'], maximum=10000000)
        if retrieved != raw:
            raise RuntimeError('Stored report bytes differ')
        artifacts.append(dict(name=name, id=record['id'], sha256=record['sha256'], byte_count=len(raw)))
    # Source records and sensitivity summary are scientific append-only metadata.
    rows = json.loads((OUT / 'evidence-records.json').read_bytes())
    store.append_bundle(STUDY, actor, rows)
    snapshot = store.snapshot(STUDY, owner=True)
    indexed = {kind: {r['id']: r for r in records} for kind, records in snapshot['records'].items()}
    for entry in rows:
        retrieved = indexed[entry['kind']][entry['record']['id']]
        if any(retrieved[k] != v for k, v in entry['record'].items()):
            raise RuntimeError('Stored supplementary evidence record differs')
    result = dict(targets=target, verified_at=workflow.now(), artifacts=artifacts,
        supplemental_records=len(rows), snapshot_bytes=len(workflow.canonical(snapshot)), hashes_verified=True,
        limitation='Operator persistence and AI inspection; no authenticated browser, publication or deployment.')
    save('supplementary-storage-verification.json', result)
    print(json.dumps(dict(stored_reports=len(artifacts), supplemental_records=len(rows), hashes_verified=True, snapshot_bytes=result['snapshot_bytes'])))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'persist', 'verify'])
    parser.add_argument('--evidence-only', action='store_true')
    args = parser.parse_args()
    target, actor = connect()
    if args.evidence_only:
        if args.command != 'persist':
            raise ValueError('Evidence storage is a persist operation')
        evidence(target, actor)
    else:
        {'inspect': inspect, 'persist': persist, 'verify': verify}[args.command](target, actor)

if __name__ == '__main__':
    main()
