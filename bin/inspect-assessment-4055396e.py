"""Read-only, fixed-assessment diagnostics. No model calls or database writes."""
import importlib.util,json,pathlib,datetime as dt,io,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/builder-continuation-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
r=release.r;m=release.m
STUDY='4055396e-35c0-4962-ba39-cf23e443ad8d'
def main():
    target=r.target();out=ROOT/'.test-artifacts/assessment-4055396e'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    data={}
    for kind in ('autonomy_workflows','autonomy_tasks','model_dispatches','builder_calls'):
        data[kind]=r.admin.query('select to_jsonb(t) record from research_'+kind+' t where study_id='+r.admin.literal(STUDY)+'::uuid order by created_at')
    release.save(out/'snapshot.json',data)
    diagnostic=[]
    for row in data['model_dispatches']:
        d=row['record']
        if d['status']=='complete':continue
        item=dict(id=d['id'],status=d['status'],provenance=d['provenance'])
        for a in d['provenance'].get('artifacts',[]):
            if a['name'] not in ('stdout.bin','stderr.bin','logical.json','openclaw-http-body.bin','receipt.json'):continue
            record=r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(a['id'])+'::uuid')[0]
            raw=m.storage(record['storage_path']);assert r.sha(raw)==record['sha256']==a['sha256'] and len(raw)==record['byte_count']
            (out/(d['id']+'-'+a['name'])).write_bytes(raw)
            if a['name'] in ('stdout.bin','stderr.bin'):item[a['name']]=raw.decode(errors='replace')[-6000:]
        diagnostic.append(item)
    native=[]
    for row in data['builder_calls'][-8:]:
        c=row['record']
        if c['status']!='complete' or not c.get('response_artifact_id'):continue
        a=r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(c['response_artifact_id'])+'::uuid')[0]
        raw=m.storage(a['storage_path']);assert r.sha(raw)==a['sha256']==c['response_sha256'] and len(raw)==a['byte_count']
        (out/(c['id']+'-native-response.bin')).write_bytes(raw)
        for line in raw.decode().splitlines():
            if not line.startswith('data: {'):continue
            event=json.loads(line[6:])
            if event.get('type')=='response.completed':native.append(dict(id=c['id'],task=c['task_id'],output=event['response']['output']))
    release.save(out/'diagnostics.json',dict(target=target,failures=diagnostic,native=native))
    history=[]
    for row in data['autonomy_tasks']:
        task=row['record'];checkpoint=task['context'].get('builder_checkpoint')
        if not checkpoint:continue
        a=r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(checkpoint['artifact_id'])+'::uuid')[0]
        raw=m.storage(a['storage_path']);assert r.sha(raw)==a['sha256']==checkpoint['sha256'] and len(raw)==a['byte_count']
        (out/(task['id']+'-checkpoint.zip')).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            record=json.loads(z.read('native-tool-history.json'))
            history.append(dict(task=task['id'],files=z.namelist(),history=record))
    release.save(out/'checkpoint-history.json',history)
    print(json.dumps(dict(directory=str(out),target=target,failures=[dict(id=x['id'],status=x['status'],stdout=x.get('stdout.bin'),stderr=x.get('stderr.bin')) for x in diagnostic],native=native)))
if __name__=='__main__':main()
