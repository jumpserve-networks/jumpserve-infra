"""Continue only runtime-rejected v6 outputs; keep original budgets and bytes."""
import datetime as dt,io,json,pathlib,subprocess,sys,threading,time,uuid,zipfile
base=pathlib.Path(__file__).resolve().parent;original=base.parent
sys.path.insert(0,str(original/'research_workflow'))
import experiment_builder as builder,openclaw_runtime as runtime,store
from workflow import canonical,digest
packet=json.loads((original/'frozen.json').read_bytes());old_raw=(original/'report.json').read_bytes();old=json.loads(old_raw)
frozen=json.loads((base/'frozen.json').read_bytes());assert digest(pathlib.Path(__file__).read_bytes())==frozen['producer_sha256']
assert old['status']!='running' and (original/'archive.json').exists()
assert subprocess.run(['systemctl','is-active','--quiet','jumpserve-builder-qualification-v2-'+original.name.lower()+'.service']).returncode!=0
assert not (base/'report.json').exists(),'Never replay this follow-up.'
limit=packet['amendment']['resources'];deadline=dt.datetime.fromisoformat(old['started_at']).timestamp()+limit['maximum_elapsed_seconds']
report=dict(amendment='experiment-builder-live-amendment-v7',status='running',original_report_sha256=digest(old_raw),
    original_start=old['started_at'],original_calls=old['live_provider_calls'],additional_calls=0,cumulative_calls=old['live_provider_calls'],cases=[],measured_charges_usd=None)
artifacts={};lock=threading.RLock();owners={};counts={};new_pointers=[]
for p in (original/'retained').glob('*/*'):
    if p.is_file() and not p.name.endswith('.pointer.json'):artifacts[str(uuid.uuid5(uuid.UUID(p.parent.name),p.name))]=p
def save():(base/'report.json').write_bytes(canonical(report))
def put(key,raw):
    url='/storage/v1/object/research-workflow-raw/'+key
    try:store.request(url,'POST',raw)
    except Exception:
        if store.request(url,raw=True)!=raw:raise
    assert store.request(url,raw=True)==raw
    return dict(bucket='research-workflow-raw',path=key,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw),public=False)
def retain(job,name,raw,kind='builder-original'):
    p=base/'retained'/job['id']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    pointer=put('qualification/experiment-builder-v2/'+original.name+'/followup-v7/calls/'+job['id']+'/'+digest(raw)+'-'+name,raw)
    identity=str(uuid.uuid5(uuid.UUID(job['id']),name));artifacts[identity]=p;new_pointers.append(pointer)
    return dict(artifact_id=identity,sha256=digest(raw),version=builder.VERSION)
def rpc(operation,job,**payload):
    with lock:
        name=owners[job['id']]
        if operation=='begin':
            if report['cumulative_calls']>=limit['maximum_live_calls'] or time.time()>=deadline or counts[name]>=limit['maximum_calls_per_case']:return dict(denied='qualification-budget')
            report['additional_calls']+=1;report['cumulative_calls']+=1;counts[name]+=1;result=dict(id=str(uuid.uuid4()))
        else:result={}
        event=dict(operation=operation,case=name,job=job,payload=payload,result=result,at=dt.datetime.now(dt.timezone.utc).isoformat())
        with (base/'ledger.jsonl').open('ab') as f:f.write(canonical(event)+b'\n');f.flush();__import__('os').fsync(f.fileno())
        put('qualification/experiment-builder-v2/'+original.name+'/followup-v7/journal/'+digest(canonical(event))+'.json',canonical(event));save();return result
builder.retain=retain;builder.rpc=rpc;builder.store.artifact_bytes=lambda study,identity,**kw:artifacts[identity].read_bytes()
save()
try:
    for n,sha in packet['runtime_files'].items():assert digest((original/'research_workflow'/n).read_bytes())==sha
    authority=builder.action_policy();runtime.verify_runtime();runtime.catalog(runtime.credential())
    eligible=[case for case in old['cases'] if case['slices'] and case['slices'][-1]['status']=='complete' and case['slices'][-1].get('feedback')]
    assert eligible,'No deterministic rejected output eligible for follow-up.'
    for case in eligible:
        name=case['name'];counts[name]=case['provider_calls'];work=pathlib.Path(case['work']);assert work.is_relative_to(original/'builder-workspaces')
        question=next(c['question'] for c in packet['cases'] if c['name']==name)
        prior=case['slices'][-1];state=dict(name=name,status='pending',original_provider_calls=counts[name],slices=[],work=str(work),original_feedback=prior['feedback']);report['cases'].append(state);save()
        logical=dict(modelId=runtime.MODEL,system=[dict(text=packet['system_prompt']),dict(text=packet['research_context'])],builder=dict(version=builder.VERSION,
            context=dict(task='building',qualification=True,question=question,protocol_contract=None,blocker_contract=packet['blocker_contract'],
                         builder_feedback=prior['feedback'],previous_slice=dict(receipt=prior,instruction='Address the retained deterministic runtime feedback, as the production controller requires. Preserve original failures; do not reset limits. This remains the separately funded qualification, not permission to perform exhausted paper work.')),
            checkpoint=prior['checkpoint'],execution_authority={k:authority[k] for k in ('version','sha256')}))
        while counts[name]<limit['maximum_calls_per_case'] and report['cumulative_calls']<limit['maximum_live_calls'] and time.time()<deadline:
            job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','lease_token')};job['task_id']=work.parent.name;owners[job['id']]=name
            directory=original/(name+'-followup-v7-slice-'+str(len(state['slices'])+1));_,receipt=builder.execute(logical,directory,job);state['slices'].append(receipt)
            if receipt['status']!='complete':state.update(status='failed-or-paused',reason='Native outcome incomplete; never replay.');break
            required=name in ('budget-stop','missing-data','missing-equipment')
            if not receipt.get('feedback') and (work/'answer.json').exists() and (not required or receipt.get('build_state')=='external-blocked'):
                json.loads((work/'answer.json').read_bytes());state['status']='awaiting-review';break
            logical['builder']['checkpoint']=receipt['checkpoint'];logical['builder']['context']['builder_feedback']=receipt.get('feedback');logical['builder']['context']['previous_slice']['receipt']=receipt
        if state['status']=='pending':state.update(status='not-completed',reason='Original cumulative/per-case call or elapsed ceiling reached.')
        state['cumulative_provider_calls']=counts[name];state['files']={str(p.relative_to(work)):dict(sha256=digest(p.read_bytes()),bytes=p.stat().st_size) for p in work.rglob('*') if p.is_file() and not p.is_symlink()};save()
        builder.container_action(work.parent.name,'remove')
    report['status']='awaiting-review' if all(c['status']=='awaiting-review' for c in report['cases']) else 'failed-or-paused'
except BaseException as error:
    report.update(status='failed-or-paused',reason=type(error).__name__+': '+str(error));raise
finally:
    assert (original/'report.json').read_bytes()==old_raw
    report.update(ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),original_report_unchanged=True);save()
    files={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='archive.json'}
    for c in report['cases']:
        work=pathlib.Path(c['work'])
        for p in work.rglob('*'):
            if p.is_file() and not p.is_symlink():files['workspace/'+c['name']+'/'+str(p.relative_to(work))]=p.read_bytes()
        for directory in original.glob(c['name']+'-followup-v7-slice-*'):
            for p in directory.iterdir():
                if p.is_file() and p.name!='config.json':files['slices/'+directory.name+'/'+p.name]=p.read_bytes()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):z.writestr(n,b)
        z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]))
    archive=put('qualification/experiment-builder-v2/'+original.name+'/followup-v7/archive/'+digest(stream.getvalue())+'.zip',stream.getvalue());(base/'archive.json').write_bytes(canonical(archive))
    print(json.dumps(dict(status=report['status'],additional_calls=report['additional_calls'],cumulative_calls=report['cumulative_calls'],archive=archive)),flush=True)
