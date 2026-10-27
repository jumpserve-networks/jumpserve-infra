"""Frozen AWS-native answer qualification. No production RPCs or paper verdicts.

The private qualification ledger admits at most 30 real provider calls and USD30
of reservations. Production Supabase admission is tested separately, not mocked
and then described as a live database check. Never automatically replay a call.
"""
import datetime as dt, hashlib, io, json, os, pathlib, sys, threading, time, uuid, zipfile
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, '/opt/jumpserve/runtime')
import experiment_builder as builder, openclaw_runtime as runtime, store
from workflow import canonical, digest

base=pathlib.Path(sys.argv[1]); packet=json.loads((base/'frozen.json').read_bytes())
report_path=base/'report.json'
if report_path.exists():raise RuntimeError('This frozen qualification was already attempted; preserve it.')
report=dict(protocol=packet['protocol'],status='running',started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    live_provider_calls=packet.get('prior_provider_calls',0),reserved_cents=100*packet.get('prior_provider_calls',0),measured_charges_usd=None,subscription_allocation_usd=None,cases=[],
    prior_campaign_provider_calls=packet.get('prior_campaign_provider_calls'),prior_campaign_reserved_cents=packet.get('prior_campaign_reserved_cents'),
    evaluator=dict(identity='Primary Codex AI implementation author',type='AI',independent=False),
    limitation='Actual native tools and subscription calls; qualification-only local admission ledger, not production Supabase admission or scientific validation.')
artifacts={}; began=time.monotonic();ledger_lock=threading.RLock()
def save():
    with ledger_lock:
        temporary=base/'.report-writing.json';temporary.write_bytes(canonical(report));temporary.replace(report_path)
def retain(job,name,raw,kind='builder-original'):
    identity=str(uuid.uuid5(uuid.UUID(job['id']),name)); path=base/'retained'/job['id']/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    artifacts[identity]=path
    assert digest(path.read_bytes())==digest(raw)
    return dict(artifact_id=identity,sha256=digest(raw),version=builder.VERSION)
def rpc(operation,job,**payload):
    with ledger_lock:
        if operation=='begin':
            if report['live_provider_calls']>=30 or time.monotonic()-began>=1800:return dict(denied='qualification-budget')
            report['live_provider_calls']+=1;report['reserved_cents']+=100;save()
            result=dict(id=str(uuid.uuid4()))
        else:result={}
        with (base/'ledger.jsonl').open('ab') as f:f.write(canonical(dict(operation=operation,job=job,payload=payload,result=result))+b'\n');f.flush();os.fsync(f.fileno())
        return result
builder.retain=retain;builder.rpc=rpc
builder.store.artifact_bytes=lambda study,identity,**kw:artifacts[identity].read_bytes()
save()
try:
    for name,sha in packet['runtime_files'].items():assert digest((pathlib.Path('/opt/jumpserve/runtime')/name).read_bytes())==sha,name
    assert digest(pathlib.Path(__file__).read_bytes())==packet['producer_sha256']
    runtime.verify_runtime();runtime.catalog(runtime.credential())
    recovered=packet.get('recovered_case')
    if recovered:
        original=recovered['source_archive'];raw=store.request('/storage/v1/object/'+original['bucket']+'/'+original['path'],raw=True);assert digest(raw)==original['sha256']
        destination=base/'recovered/new-implementation/workspace';destination.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name,item in recovered['files'].items():
                relative=pathlib.PurePosixPath(name)
                assert not relative.is_absolute() and '..' not in relative.parts
                value=z.read(item['archive_path']);assert digest(value)==item['sha256']
                target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
        recovered['work']=str(destination);report['cases']=[recovered];report['live_provider_calls']=6;report['reserved_cents']=600
        report['resumed_at']=report['started_at'];report['started_at']=recovered['original_started_at']
        began=time.monotonic()-(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(report['started_at'])).total_seconds()
        (base/'recovered-entry.json').write_bytes(canonical(recovered));save()
    def run_case(case):
        if time.monotonic()-began>=1800:raise RuntimeError('Qualification elapsed-time limit reached.')
        job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','task_id','lease_token')}
        work=base/'builder-workspaces'/job['task_id']/'workspace';work.mkdir(parents=True)
        if case['name']=='dependency-repair':(work/'bad-requirements.lock').write_text('six==1.17.0 --hash=sha256:'+'0'*64+'\n')
        if case['name']=='checkpoint-resume':
            (work/'retained-context.json').write_bytes(canonical(dict(maximum_cents=10000,committed_cents=2300,deadline_at='2026-11-03T19:00:00Z')))
            (work/'previous-failure.log').write_text('Prior attempt failed: connection refused. Keep this original failure.\n')
        before=digest((work/'retained-context.json').read_bytes()) if (work/'retained-context.json').exists() else None
        authority=builder.action_policy()
        logical=dict(modelId=runtime.MODEL,system=[dict(text=packet['system_prompt']),dict(text=packet['research_context'])],builder=dict(version=builder.VERSION,
            context=dict(task='building',question=case['question'],qualification=True,protocol_contract=None,blocker_contract=packet['blocker_contract']),checkpoint=None,
            execution_authority={k:authority[k] for k in ('version','sha256')}))
        receipts=[]
        while True:
            if report['live_provider_calls']>=30 or time.monotonic()-began>=1800:raise RuntimeError('Qualification cumulative call/time limit reached.')
            _,receipt=builder.execute(logical,base/(case['name']+'-slice-'+str(len(receipts)+1)),job)
            receipts.append(receipt)
            if receipt['status']!='complete' or (work/'answer.json').exists() or (work/'blocker.json').exists():break
            logical['builder']['checkpoint']=receipt['checkpoint']
            logical['builder']['context']['previous_slice']=dict(receipt=receipt,instruction='Continue saved work; do not repeat completed setup. The native provider window is reserved before each new inference.')
            job=dict(job,id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
        files={str(p.relative_to(work)):dict(sha256=digest(p.read_bytes()),bytes=p.stat().st_size) for p in work.rglob('*') if p.is_file() and not p.is_symlink()}
        entry=dict(name=case['name'],set=case['set'],receipt=receipt,slices=receipts,files=files,actual_answer_reviewed=False,passed=False,work=str(work),context_preserved=(not before or digest((work/'retained-context.json').read_bytes())==before))
        with ledger_lock:report['cases'].append(entry);save()
        builder.container_action(job['task_id'],'remove')
        print(json.dumps(dict(name=case['name'],status=receipt['status'],provider_calls=receipt['provider_calls'],files=list(files))),flush=True)
        if receipt['status']!='complete':raise RuntimeError('Actual native call failed; preserve before a versioned follow-up.')
    remaining=[case for case in packet['cases'] if not recovered or case['name']!=recovered['name']]
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run_case,remaining))
    report['status']='awaiting-substantive-review'
except BaseException as error:
    report.update(status='failed-or-paused',reason=str(error));raise
finally:
    report.update(wall_seconds=time.monotonic()-began,ended_at=dt.datetime.now(dt.timezone.utc).isoformat());save()
    # Never archive bridge configs, local auth or generated native state caches.
    files={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file() and not p.is_symlink() and
        (p.name in ('frozen.json','producer.py','report.json','ledger.jsonl','recovered-entry.json','task.txt','logical.json','action-policy.json','receipt.json','stdout.bin','stderr.bin','workspace-normalization.json') or
         p.name.startswith('native-request-') or p.name.startswith('call-') or 'retained' in p.relative_to(base).parts or
         ('workspace' in p.relative_to(base).parts and 'state' not in p.relative_to(base).parts))}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):z.writestr(name,raw)
        z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]))
    raw=buffer.getvalue();key='release-verification/experiment-builder/'+base.name+'/'+digest(raw)+'.zip';url='/storage/v1/object/research-workflow-raw/'+key
    store.request(url,'POST',raw);restored=store.request(url,raw=True);assert digest(restored)==digest(raw)
    (base/'archive.json').write_bytes(canonical(dict(bucket='research-workflow-raw',path=key,sha256=digest(raw),retrieved_sha256=digest(restored),bytes=len(raw),public=False)))
    print(json.dumps(dict(status=report['status'],live_provider_calls=report['live_provider_calls'],archive=json.loads((base/'archive.json').read_bytes()))),flush=True)
