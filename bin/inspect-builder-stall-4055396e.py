"""Fixed-assessment, read-only capture; no model, execution, SQL writes or deployment."""
import datetime as dt
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stall_release', ROOT / 'bin/inspect-assessment-4055396e.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
r, m, release = original.r, original.m, original.release
STUDY = original.STUDY


def main():
    target = r.target()
    out = ROOT / '.test-artifacts/assessment-4055396e' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, mode=0o700)
    protocol = (ROOT / 'docs/assessment-4055396e-builder-stall-protocol-v1.json').read_bytes()
    (out / 'protocol.json').write_bytes(protocol)
    identity = r.admin.literal(STUDY) + '::uuid'
    data = dict(target=target, recorded_at=r.stamp(), protocol_sha256=r.sha(protocol), tasks=[], artifact_reads=[], native_calls=[], dispatches=[], turns=[])
    artifacts = {}
    total = 0

    def get(ref, role):
        nonlocal total
        ident = ref.get('artifact_id') or ref['id']
        if ident in artifacts:
            assert artifacts[ident]['sha256'] == ref['sha256']
            return (out / artifacts[ident]['file']).read_bytes()
        attempt = dict(id=ident, role=role, expected_sha256=ref['sha256'], status='pending')
        data['artifact_reads'].append(attempt)
        release.save(out / 'capture.json', data)
        try:
            a = r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id=' + identity + ' and id=' + r.admin.literal(ident) + '::uuid')[0]
            assert a['sha256'] == ref['sha256'] and total + a['byte_count'] <= 64000000
            raw = m.storage(a['storage_path'])
            assert r.sha(raw) == a['sha256'] and len(raw) == a['byte_count']
            name = 'original-' + ident + '.bin'
            (out / name).write_bytes(raw)
            total += len(raw)
            attempt.update(status='verified', sha256=r.sha(raw), bytes=len(raw), file=name)
            artifacts[ident] = attempt
            return raw
        except Exception as error:
            attempt.update(status='unavailable', error_type=type(error).__name__)
            return None
        finally:
            release.save(out / 'capture.json', data)

    data['workflow'] = r.admin.query('select to_jsonb(w) record from research_autonomy_workflows w where study_id=' + identity)
    tasks = r.admin.query('select to_jsonb(t) record from research_autonomy_tasks t where study_id=' + identity + ' and claim_id is not null order by created_at')
    assert len(tasks) == 5
    for row in tasks:
        task = row['record']
        data['tasks'].append(task)
        task_identity = r.admin.literal(task['id']) + '::uuid'
        dispatches = r.admin.query("select to_jsonb(d) record from research_model_dispatches d where study_id=" + identity + " and task_id=" + task_identity + " and request_raw::jsonb ? 'builder' order by created_at desc limit 3")
        for item in dispatches:
            d = item['record']
            assert d['study_id'] == STUDY and d['task_id'] == task['id'] and r.sha(d['request_raw'].encode()) == d['request_sha256']
            data['dispatches'].append(d)
            for a in d['provenance'].get('artifacts', []):
                if a['name'] in ('receipt.json', 'stdout.bin', 'stderr.bin', 'context-delivery.json', 'task.txt'):
                    get(a, 'parent:' + d['id'] + ':' + a['name'])
        turns = r.admin.query('select to_jsonb(t) record from research_autonomy_turns t where study_id=' + identity + ' and task_id=' + task_identity + ' order by number desc limit 2')
        data['turns'].extend(item['record'] for item in turns)
        calls = r.admin.query('select to_jsonb(c) record from research_builder_calls c where study_id=' + identity + ' and task_id=' + task_identity + ' order by created_at desc limit 2')
        for item in calls:
            c = item['record']
            data['native_calls'].append(c)
            for kind in ('request', 'response'):
                if c.get(kind + '_artifact_id') and c.get(kind + '_sha256'):
                    get(dict(artifact_id=c[kind + '_artifact_id'], sha256=c[kind + '_sha256']), 'native:' + c['id'] + ':' + kind)
        checkpoint = task['context'].get('builder_checkpoint')
        if checkpoint:
            raw = get(checkpoint, 'checkpoint:' + task['id'])
            if raw:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    task['examined_checkpoint_inventory'] = [dict(path=n, bytes=len(z.read(n)), sha256=r.sha(z.read(n))) for n in z.namelist()]
                    history = json.loads(z.read('native-tool-history.json'))
                    if isinstance(history, dict):
                        compressed = z.read('native-tool-history.json.gz')
                        assert r.sha(compressed) == history['compressed_sha256']
                        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                            expanded = stream.read(16000001)
                        assert len(expanded) <= 16000000 and r.sha(expanded) == history['sha256'] and len(expanded) == history['bytes']
                        decoded = json.loads(expanded)
                        assert len(decoded) == history['records']
                        history = decoded
                    assert isinstance(history, list)
                    release.save(out / (task['id'] + '-derived-history.json'), history)
    data.update(downloaded_bytes=total, capture_finished_at=r.stamp(), new_model_calls=0, production_writes=0, review_status='Retrieved selected originals; substantive review not implied')
    release.save(out / 'capture.json', data)
    manifest = [dict(file=p.name, bytes=p.stat().st_size, sha256=r.sha(p.read_bytes())) for p in sorted(out.iterdir()) if p.is_file()]
    release.save(out / 'manifest.json', manifest)
    print(json.dumps(dict(directory=str(out), tasks=len(data['tasks']), dispatches=len(data['dispatches']), native_calls=len(data['native_calls']), downloaded_bytes=total, verified_artifacts=len(artifacts), unavailable_artifacts=[a for a in data['artifact_reads'] if a['status'] != 'verified'])))


def supplement():
    """Adaptive read-only follow-up: largest request per completed builder."""
    target = r.target()
    base = ROOT / '.test-artifacts/assessment-4055396e'
    source = sorted(base.glob('*/capture.json'))[-1]
    data = json.loads(source.read_bytes())
    assert data['capture_finished_at'] and len(data['tasks']) == 5
    out = base / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(mode=0o700)
    report = dict(version='builder-stall-request-supplement-v1', target=target, source_capture=str(source.relative_to(ROOT)), source_sha256=r.sha(source.read_bytes()), recorded_at=r.stamp(), selection='Largest retained native request from each task latest completed sampled builder parent. Fixed five repair records and recent events. No model calls or writes.', requests=[], repairs=[], events=[])
    release.save(out / 'supplement.json', report)
    for task in data['tasks']:
        parents = [d for d in data['dispatches'] if d['task_id'] == task['id'] and d['status'] == 'complete']
        assert parents
        d = parents[0]
        requests = [a for a in d['provenance']['artifacts'] if a['name'].startswith('native-request-')]
        assert requests
        ref = max(requests, key=lambda a: a['byte_count'])
        artifact = r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id=' + r.admin.literal(STUDY) + '::uuid and id=' + r.admin.literal(ref['id']) + '::uuid')[0]
        raw = m.storage(artifact['storage_path'])
        assert r.sha(raw) == artifact['sha256'] == ref['sha256'] and len(raw) == artifact['byte_count'] == ref['byte_count']
        filename = task['id'] + '-native-request.json'
        (out / filename).write_bytes(raw)
        report['requests'].append(dict(task_id=task['id'], dispatch_id=d['id'], file=filename, sha256=r.sha(raw), bytes=len(raw)))
        rid = task['context']['repair_progress']['id']
        report['repairs'].extend(r.admin.query('select to_jsonb(r) record from research_autonomy_repairs r where study_id=' + r.admin.literal(STUDY) + '::uuid and id=' + r.admin.literal(rid) + '::uuid'))
        report['events'].extend(r.admin.query('select to_jsonb(e) record from research_autonomy_repair_events e where study_id=' + r.admin.literal(STUDY) + '::uuid and repair_id=' + r.admin.literal(rid) + '::uuid order by created_at desc limit 8'))
        release.save(out / 'supplement.json', report)
    report['finished_at'] = r.stamp()
    release.save(out / 'supplement.json', report)
    print(json.dumps(dict(directory=str(out), requests=report['requests'], repairs=len(report['repairs']), events=len(report['events']), model_calls=0, writes=0)))

def matched_checkpoints():
    """Bind replay inputs to the exact parent, not a later task-status read."""
    target=r.target();base=ROOT/'.test-artifacts/assessment-4055396e'
    source=sorted(base.glob('*/capture.json'))[-1];data=json.loads(source.read_bytes())
    supplement_path=sorted(base.glob('*/supplement.json'))[-1];supplement=json.loads(supplement_path.read_bytes())
    assert supplement['source_sha256']==r.sha(source.read_bytes())
    out=base/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(mode=0o700)
    report=dict(version='builder-stall-matched-checkpoints-v1',target=target,source_capture=str(source.relative_to(ROOT)),supplement=str(supplement_path.relative_to(ROOT)),checkpoints=[],model_calls=0,production_writes=0)
    for entry in supplement['requests']:
        d=next(d for d in data['dispatches'] if d['id']==entry['dispatch_id']);ref=d['provenance']['checkpoint']
        cached=next((a for a in data['artifact_reads'] if a['status']=='verified' and a['id']==ref['artifact_id']),None)
        if cached:raw=(source.parent/cached['file']).read_bytes()
        else:
            a=r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ref['artifact_id'])+'::uuid')[0]
            assert a['sha256']==ref['sha256'];raw=m.storage(a['storage_path']);assert len(raw)==a['byte_count']
        assert len(raw)<=4000000 and r.sha(raw)==ref['sha256']
        filename=entry['task_id']+'-checkpoint.zip';(out/filename).write_bytes(raw)
        report['checkpoints'].append(dict(task_id=entry['task_id'],dispatch_id=d['id'],file=filename,sha256=r.sha(raw),bytes=len(raw),artifact_id=ref['artifact_id']))
        release.save(out/'matched-checkpoints.json',report)
    print(json.dumps(dict(directory=str(out),checkpoints=len(report['checkpoints']),model_calls=0,writes=0)))


def planner_boundary():
    """Retrieve the exact known failure, never invoke/replay its model request."""
    target=r.target();identity=r.admin.literal(STUDY)+'::uuid'
    dispatch_id='6e5b884a-3322-508b-ae00-c01df7ec9307'
    records=r.admin.query('select to_jsonb(d) record from research_model_dispatches d where study_id='+identity+' and id='+r.admin.literal(dispatch_id)+'::uuid')
    assert len(records)==1;record=records[0]['record'];assert record['status']=='failed' and record['provenance']['provider_calls']==0
    assert r.sha(record['request_raw'].encode())==record['request_sha256']
    out=ROOT/'.test-artifacts/autonomy-completion-v1'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    protocol=(ROOT/'docs/autonomy-completion-protocol-v1.json').read_bytes();(out/'protocol.json').write_bytes(protocol)
    release.save(out/'dispatch.json',record)
    report=dict(version='retained-planner-boundary-v1',target=target,dispatch_id=dispatch_id,protocol_sha256=r.sha(protocol),artifacts=[],provider_calls=0,production_writes=0,review_status='retrieved; not yet reviewed')
    release.save(out/'retrieval.json',report)
    for ref in record['provenance']['artifacts']:
        if ref['name'] not in ('logical.json','message.json','receipt.json','stdout.bin','stderr.bin','openclaw-http-body.bin','provider-request.json'):continue
        row=r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id='+identity+' and id='+r.admin.literal(ref.get('id') or ref['artifact_id'])+'::uuid')[0]
        assert row['sha256']==ref['sha256'] and row['byte_count']<=1000000
        raw=m.storage(row['storage_path']);assert len(raw)==row['byte_count'] and r.sha(raw)==row['sha256']
        (out/ref['name']).write_bytes(raw);report['artifacts'].append(dict(name=ref['name'],bytes=len(raw),sha256=r.sha(raw),retrieved_sha256=r.sha(raw)))
        release.save(out/'retrieval.json',report)
    report['review_status']='originals retrieved and hash-verified; completeness not implied';release.save(out/'retrieval.json',report)
    print(json.dumps(dict(directory=str(out),artifacts=report['artifacts'],provider_calls=0,production_writes=0)))


if __name__ == '__main__':
    if sys.argv[1:] == ['--requests']:
        supplement()
    elif sys.argv[1:] == ['--matched-checkpoints']:
        matched_checkpoints()
    elif sys.argv[1:] == ['--planner-boundary']:
        planner_boundary()
    elif not sys.argv[1:]:
        main()
    else:
        raise SystemExit('Only fixed read-only --requests follow-up is supported.')
