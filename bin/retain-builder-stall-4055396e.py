"""Append a private investigation artifact; never alter execution or findings."""
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BACK = ROOT.parent / 'jumpserve-back-end'
spec = importlib.util.spec_from_file_location('stall_capture', ROOT / 'bin/inspect-builder-stall-4055396e.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
r, m, release, STUDY = capture.r, capture.m, capture.release, capture.STUDY


def main():
    target = r.target()
    base = ROOT / '.test-artifacts/assessment-4055396e'
    analysis_path = sorted(base.glob('*/analysis.json'))[-1]
    analysis = json.loads(analysis_path.read_bytes())
    assert analysis['new_model_calls'] == analysis['new_experiments'] == analysis['production_writes'] == 0
    assert analysis['summary']['exact_boundaries_reproduced'] == analysis['summary']['no_progress_stop_requeued'] == 5
    directories = [analysis_path.parent, (ROOT / analysis['source_capture']).parent, (ROOT / analysis['supplement']).parent]
    out = base / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(mode=0o700)
    files = {}
    for directory in directories:
        for p in directory.iterdir():
            if p.is_file():
                files[str(p.relative_to(ROOT))] = p.read_bytes()
    for path in ('bin/inspect-builder-stall-4055396e.py', 'bin/analyze-builder-stall-4055396e.py', 'bin/retain-builder-stall-4055396e.py', 'docs/assessment-4055396e-builder-stall-protocol-v1.json', 'docs/assessment-4055396e-builder-stall-findings-v1.md', '.test-artifacts/assessment-4055396e/investigation-queue.json', '.test-artifacts/assessment-4055396e/investigation-final-queue.json'):
        files[path] = (ROOT / path).read_bytes()
    for path, sha in analysis['source_files'].items():
        raw = (BACK / 'research_workflow' / path).read_bytes()
        assert r.sha(raw) == sha
        files['backend/research_workflow/' + path] = raw
    report = dict(version='assessment-4055396e-builder-stall-retention-v1', assessment=STUDY, target=target, recorded_at=r.stamp(), kind='operational-software-investigation', status='investigated;runtime-unchanged', analysis=analysis, new_investigator_model_calls=0, new_investigator_experiments=0, metadata_write='Append this private evidence artifact only; no assessment execution, labels, limits, source or runtime changes', measured_charges_usd=None, subscription_allocation_usd=None, storage_charges_usd=None)
    files['investigation-report.json'] = json.dumps(report, sort_keys=True, separators=(',', ':')).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            z.writestr(name, raw)
        z.writestr('artifact-manifest.json', json.dumps([dict(path=n, sha256=r.sha(v), bytes=len(v)) for n, v in sorted(files.items())]))
    raw = stream.getvalue()
    assert len(raw) < 20000000
    (out / 'evidence.zip').write_bytes(raw)
    sha = r.sha(raw)
    path = STUDY + '/' + sha
    release.save(out / 'pending.json', dict(path=path, sha256=sha, bytes=len(raw), members=len(files)))
    m.storage(path, raw)
    restored = m.storage(path)
    assert restored == raw
    with zipfile.ZipFile(io.BytesIO(restored)) as z:
        for entry in json.loads(z.read('artifact-manifest.json')):
            assert r.sha(z.read(entry['path'])) == entry['sha256']
    actor = r.admin.query('select owner_id from research_study_owners where study_id=' + r.admin.literal(STUDY) + '::uuid')[0]['owner_id']
    ident = str(uuid.uuid5(uuid.UUID(STUDY), 'builder-stall-investigation:' + sha))
    record = dict(id=ident, sha256=sha, byte_count=len(raw), storage_path=path, media_type='application/zip', verified_at=r.stamp(), provenance=dict(kind=report['kind'], version=report['version'], status=report['status'], scientific_completion=False, new_model_calls=0, reviewer=analysis['reviewer']))
    r.admin.query('select public.research_append(' + ','.join([r.admin.literal(STUDY) + '::uuid', r.admin.literal(actor) + '::uuid', r.admin.literal('artifacts'), r.admin.literal(json.dumps(record)) + '::jsonb']) + ')', read_only=False)
    saved = r.admin.query('select sha256,byte_count from research_artifacts where study_id=' + r.admin.literal(STUDY) + '::uuid and id=' + r.admin.literal(ident) + '::uuid')[0]
    assert saved == dict(sha256=sha, byte_count=len(raw))
    receipt = dict(version=report['version'], assessment=STUDY, status=report['status'], artifact_id=ident, sha256=sha, retrieved_sha256=r.sha(restored), bytes=len(raw), members=len(files), public=False, analysis_sha256=r.sha(analysis_path.read_bytes()), source_revision=analysis['source_revision'], new_investigator_model_calls=0, new_investigator_experiments=0, assessment_execution_changed=False, deployed=False)
    release.save(out / 'receipt.json', receipt)
    release.save(ROOT / 'docs/assessment-4055396e-builder-stall-retention-v1.json', receipt)
    print(json.dumps(receipt))


def retain_fix():
    """Append the sealed LOCAL validation only; never approve or deploy it."""
    target=r.target();path=ROOT/'docs/builder-stall-fix-local-status-v1.json';report=json.loads(path.read_bytes())
    assert report['status']=='implemented-and-locally-verified;release-pending' and report['deployed'] is False and report['new_live_model_calls']==0
    raw=(ROOT/report['evidence']['path']).read_bytes();sha=r.sha(raw);assert sha==report['evidence']['sha256'] and len(raw)<20000000
    storage_path=STUDY+'/'+sha;m.storage(storage_path,raw);restored=m.storage(storage_path);assert restored==raw
    with zipfile.ZipFile(io.BytesIO(restored)) as archive:
        for entry in json.loads(archive.read('artifact-manifest.json')):assert r.sha(archive.read(entry['path']))==entry['sha256']
    actor=r.admin.query('select owner_id from research_study_owners where study_id='+r.admin.literal(STUDY)+'::uuid')[0]['owner_id']
    ident=str(uuid.uuid5(uuid.UUID(STUDY),'builder-stall-fix-local:'+sha))
    saved=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')
    if not saved:
        record=dict(id=ident,sha256=sha,byte_count=len(raw),storage_path=storage_path,media_type='application/zip',verified_at=r.stamp(),provenance=dict(kind='local-software-validation',version=report['version'],status=report['status'],scientific_completion=False,new_model_calls=0,deployed=False,reviewer=report['reviewer']))
        r.admin.query('select public.research_append('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(actor)+'::uuid',r.admin.literal('artifacts'),r.admin.literal(json.dumps(record))+'::jsonb'])+')',read_only=False)
        saved=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')
    assert saved==[dict(sha256=sha,byte_count=len(raw))]
    report['evidence'].update(remote_storage_verified=True,artifact_id=ident,retrieved_sha256=r.sha(restored),public=False)
    release.save(path,report);print(json.dumps(dict(status=report['status'],target=target,evidence=report['evidence'],deployed=False)))


if __name__ == '__main__':
    if sys.argv[1:]==['--fix-validation']:retain_fix()
    elif not sys.argv[1:]:main()
    else:raise SystemExit('Only the fixed --fix-validation evidence append is supported.')
