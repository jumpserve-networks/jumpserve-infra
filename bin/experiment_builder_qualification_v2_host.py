"""Isolated corrected-candidate qualification. No production runtime replacement."""
import datetime as dt,io,json,os,pathlib,sys,threading,time,uuid,zipfile
from concurrent.futures import ThreadPoolExecutor
base=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(base/'research_workflow'))
import experiment_builder as builder,openclaw_runtime as runtime,store
from workflow import canonical,digest
packet=json.loads((base/'frozen.json').read_bytes());limits=packet['amendment']['resources']
assert not (base/'report.json').exists(),'Never replay a dispatched campaign.'
report=dict(protocol='experiment-builder-live-evaluation-v1',amendment=packet['amendment']['version'],
    status='running',started_at=dt.datetime.now(dt.timezone.utc).isoformat(),live_provider_calls=0,
    reserved_cents=0,measured_charges_usd=None,subscription_allocation_usd=None,cases=[],
    evaluator=dict(identity='Primary Codex AI implementation author',type='AI',independent=False),
    scope='Actual native tools/subscription model in isolated candidate directories. Qualification-only admission journal, not production RPC admission or paper evidence.')
lock=threading.RLock();began=time.monotonic();artifacts={};owners={};case_counts={};entries={}
def save():
    with lock:
        p=base/'.report-writing.json';p.write_bytes(canonical(report));p.replace(base/'report.json')
def put(key,raw):
    url='/storage/v1/object/research-workflow-raw/'+key
    try:store.request(url,'POST',raw)
    except Exception:
        if store.request(url,raw=True)!=raw:raise
    assert digest(store.request(url,raw=True))==digest(raw)
    return dict(bucket='research-workflow-raw',path=key,sha256=digest(raw),bytes=len(raw),retrieved_sha256=digest(raw),public=False)
def retain(job,name,raw,kind='builder-original'):
    identity=str(uuid.uuid5(uuid.UUID(job['id']),name));p=base/'retained'/job['id']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    pointer=put('qualification/experiment-builder-v2/'+base.name+'/calls/'+job['id']+'/'+digest(raw)+'-'+name,raw)
    artifacts[identity]=p
    (p.with_suffix(p.suffix+'.pointer.json')).write_bytes(canonical(pointer))
    return dict(artifact_id=identity,sha256=digest(raw),version=builder.VERSION)
def rpc(operation,job,**payload):
    with lock:
        name=owners[job['id']]
        if operation=='begin':
            if report['live_provider_calls']>=limits['maximum_live_calls'] or time.monotonic()-began>=limits['maximum_elapsed_seconds'] or case_counts[name]>=limits['maximum_calls_per_case']:
                return dict(denied='qualification-budget')
            report['live_provider_calls']+=1;report['reserved_cents']+=100;case_counts[name]+=1
            result=dict(id=str(uuid.uuid4()))
        else:result={}
        event=dict(operation=operation,case=name,job=job,payload=payload,result=result,at=dt.datetime.now(dt.timezone.utc).isoformat())
        with (base/'ledger.jsonl').open('ab') as f:f.write(canonical(event)+b'\n');f.flush();os.fsync(f.fileno())
        put('qualification/experiment-builder-v2/'+base.name+'/journal/'+digest(canonical(event))+'.json',canonical(event))
        save();return result
builder.retain=retain;builder.rpc=rpc
builder.store.artifact_bytes=lambda study,identity,**kw:artifacts[identity].read_bytes()
def slice_case(case):
    name=case['name'];state=entries[name];job=state['job'];owners[job['id']]=name
    work=base/'builder-workspaces'/job['task_id']/'workspace'
    directory=base/(name+'-slice-'+str(len(state['slices'])+1))
    try:
        _,receipt=builder.execute(state['logical'],directory,job)
        state['slices'].append(receipt)
        if receipt['status']!='complete':state.update(status='failed-or-paused',reason=receipt.get('error_code','Native outcome not complete'))
        elif not receipt.get('feedback') and (work/'answer.json').exists() and (name not in ('budget-stop','missing-data','missing-equipment') or receipt.get('build_state')=='external-blocked'):
            json.loads((work/'answer.json').read_bytes());state['status']='awaiting-review'
        elif case_counts[name]>=limits['maximum_calls_per_case']:state.update(status='failed-or-paused',reason='Declared case call limit reached')
        else:
            state['logical']['builder']['checkpoint']=receipt['checkpoint']
            state['logical']['builder']['context']['builder_feedback']=receipt.get('feedback')
            state['logical']['builder']['context']['previous_slice']=dict(receipt=receipt,instruction='Continue retained work and address deterministic runtime feedback; an answer file cannot waive invalid blocker/candidate feedback. Do not repeat completed setup or reset limits.')
            state['job']=dict(job,id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
    except Exception as error:state.update(status='failed-or-paused',reason=type(error).__name__+': '+str(error))
    finally:
        with lock:
            state['files']={str(p.relative_to(work)):dict(sha256=digest(p.read_bytes()),bytes=p.stat().st_size) for p in work.rglob('*') if p.is_file() and not p.is_symlink()}
            state['provider_calls']=case_counts[name]
            report['cases']=[{k:v for k,v in entries[c['name']].items() if k not in ('job','logical')} for c in packet['cases']]
            save()
        print(json.dumps(dict(name=name,status=state['status'],provider_calls=state['provider_calls'])),flush=True)

save()
try:
    for name,sha in packet['runtime_files'].items():assert digest((base/'research_workflow'/name).read_bytes())==sha,name
    assert digest(pathlib.Path(__file__).read_bytes())==packet['producer_sha256']
    runtime.verify_runtime();runtime.catalog(runtime.credential());builder.builder_package()
    authority=builder.action_policy()
    for case in packet['cases']:
        name=case['name'];job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','task_id','lease_token')};work=base/'builder-workspaces'/job['task_id']/'workspace';work.mkdir(parents=True)
        if name=='dependency-repair':(work/'bad-requirements.lock').write_text('six==1.17.0 --hash=sha256:'+'0'*64+'\n')
        if name=='checkpoint-resume':
            (work/'retained-context.json').write_bytes(canonical(dict(maximum_cents=10000,committed_cents=2300,deadline_at='2026-11-03T19:00:00Z')))
            (work/'previous-failure.log').write_text('Prior attempt failed: connection refused. Keep this original failure.\n')
        logical=dict(modelId=runtime.MODEL,system=[dict(text=packet['system_prompt']),dict(text=packet['research_context'])],builder=dict(version=builder.VERSION,
            context=dict(task='building',qualification=True,question=case['question'],protocol_contract=None,blocker_contract=packet['blocker_contract']),checkpoint=None,
            execution_authority={k:authority[k] for k in ('version','sha256')}))
        entries[name]=dict(name=name,set=case['set'],status='pending',slices=[],provider_calls=0,work=str(work),job=job,logical=logical,actual_answer_reviewed=False,passed=False)
        case_counts[name]=0
    while any(x['status']=='pending' for x in entries.values()):
        if time.monotonic()-began>=limits['maximum_elapsed_seconds'] or report['live_provider_calls']>=limits['maximum_live_calls']:break
        # A fair round gives every unfinished claim one scheduling slot.
        pending=[c for c in packet['cases'] if entries[c['name']]['status']=='pending']
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(slice_case,pending))
    for state in entries.values():
        if state['status']=='pending':state.update(status='not-completed',reason='Declared global call/time stop')
    report['cases']=[{k:v for k,v in entries[c['name']].items() if k not in ('job','logical')} for c in packet['cases']]
    report['status']='awaiting-substantive-review' if all(x['status']=='awaiting-review' for x in entries.values()) else 'failed-or-paused'
except BaseException as error:report.update(status='failed-or-paused',reason=type(error).__name__+': '+str(error));raise
finally:
    report.update(ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),wall_seconds=time.monotonic()-began);save()
    files={}
    for p in base.rglob('*'):
        if not p.is_file() or p.is_symlink():continue
        parts=p.relative_to(base).parts
        if any(part in ('state','node_modules','builder-vendor') for part in parts) or p.name in ('config.json','archive.json','run.log'):continue
        if 'workspace' in parts or 'retained' in parts or 'research_workflow' in parts or p.name in ('experiment_builder_qualification_v2_host.py','frozen.json','report.json','ledger.jsonl','task.txt','logical.json','action-policy.json','runner-contract.json','receipt.json','stdout.bin','stderr.bin','workspace-normalization.json') or p.name.startswith(('call-','native-request-')):
            files[str(p.relative_to(base))]=p.read_bytes()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):z.writestr(n,b)
        z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]))
    archive=put('qualification/experiment-builder-v2/'+base.name+'/archive/'+digest(stream.getvalue())+'.zip',stream.getvalue())
    (base/'archive.json').write_bytes(canonical(archive))
    # Evidence is retained before retiring this campaign's isolated environments.
    for state in entries.values():builder.container_action(state['job']['task_id'],'remove')
    print(json.dumps(dict(status=report['status'],calls=report['live_provider_calls'],archive=archive)),flush=True)
