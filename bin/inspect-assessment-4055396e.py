"""Read-only, fixed-assessment diagnostics. No model calls or database writes."""
import importlib.util,json,pathlib,datetime as dt,io,zipfile,shlex,time,sys,tempfile,subprocess,types
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
def worker_spool():
    """Fixed read-only inspection; never read auth/config files or execute work."""
    target=r.target()
    program='''import hashlib,json,pathlib
root=pathlib.Path('/var/lib/jumpserve-openclaw/spool')
ids=['af717ce4-6790-5647-9623-e67b5f9c4eca','353bf8b5-55e4-5e5e-b0a2-c0ffa757d765','45176ed6-af9f-5d6e-99af-fa2174d9f774']
records=[]
for identity in ids:
 directory=root/identity;files=[];record=dict(id=identity,exists=directory.is_dir(),files=files)
 if directory.is_dir():
  for p in sorted(directory.iterdir()):
   if not p.is_file() or p.is_symlink() or p.name=='config.json':continue
   raw=p.read_bytes();item=dict(name=p.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
   if p.name=='receipt.json':item['receipt']=json.loads(raw)
   elif p.name in ('stderr.bin','stdout.bin'):item['excerpt']=raw.decode(errors='replace')[-2500:]
   files.append(item)
 records.append(record)
print(json.dumps(records))
'''
    command=r.ssm(['/opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)])
    result={}
    for _ in range(45):
        result=r.aws('ssm','get-command-invocation','--command-id',command['command_id'],'--instance-id',command['instance_id'])
        if result['Status'] not in ('Pending','InProgress','Delayed'):break
        time.sleep(1)
    out=ROOT/'.test-artifacts/assessment-4055396e'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    release.save(out/'worker-spool-inspection.json',dict(target=target,command=command,result=result))
    print(json.dumps(dict(directory=str(out),status=result.get('Status'),stdout=result.get('StandardOutputContent'),stderr=result.get('StandardErrorContent'))))

def local_builder_replay():
    """Controlled old/new delivery comparison over retained incident bytes."""
    backend=ROOT.parent/'jumpserve-back-end';sys.path.insert(0,str(backend/'research_workflow'))
    import experiment_builder as builder
    from workflow import canonical,digest
    base=ROOT/'.test-artifacts/assessment-4055396e/20261029T201122273408Z'
    data=json.loads((base/'snapshot.json').read_bytes());task='1fa0b903-5ccd-5608-a57b-4ff01d75cf73'
    checkpoint=(base/(task+'-checkpoint.zip')).read_bytes()
    matches=[r['record'] for r in data['model_dispatches'] if r['record']['task_id']==task and (r['record']['provenance'].get('checkpoint') or {}).get('sha256')==digest(checkpoint)]
    assert len(matches)==1,'Exact retained dispatch/checkpoint binding required'
    dispatch=matches[0];logical=json.loads(dispatch['request_raw'])
    assert digest(dispatch['request_raw'].encode())==dispatch['request_sha256']
    with zipfile.ZipFile(io.BytesIO(checkpoint)) as z:
        context=json.loads(z.read('research-context.json'));history=json.loads(z.read('native-tool-history.json'))
    # _execute adds verified diagnosis data before bootstrap. Use that exact
    # delivered context, rather than invent a summary or reconstruct passages.
    logical['builder']['context']=context
    revision='74acf0090e5db7c932e982a05939ed399c38a40f'
    original=subprocess.check_output(['git','show',revision+':research_workflow/experiment_builder.py'],cwd=backend)
    old=types.ModuleType('retained_builder_baseline');old.__file__=str(backend/'research_workflow/experiment_builder.py');exec(compile(original,old.__file__,'exec'),old.__dict__)
    out=ROOT/'.test-artifacts/assessment-4055396e'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    report=dict(protocol='builder-recovery-validation-v3',kind='development-regression',live_model_calls=0,production_writes=0,
        dispatch_id=dispatch['id'],original_request_sha256=dispatch['request_sha256'],checkpoint_sha256=digest(checkpoint),context_sha256=digest(canonical(context)),history_sha256=digest(canonical(history)),
        baseline_revision=revision,baseline_source_sha256=digest(original),current_source_sha256=digest(pathlib.Path(builder.__file__).read_bytes()),
        reviewer=dict(identity='Codex',type='AI',independent=False),scope='Controlled old/new software delivery comparison over exact retained inputs; no model behavior or scientific reproduction established.')
    for name,implementation in [('baseline',old),('corrected',builder)]:
        work=out/name;work.mkdir();implementation.restore(checkpoint,work)
        text,manifest=implementation.bootstrap(logical,work,out,history)
        (out/(name+'-bootstrap.txt')).write_text(text)
        report[name]=dict(bytes=len(text.encode()),inline_fields=manifest['inline_fields'],sha256=digest(text.encode()),has_feedback='builder_feedback' in manifest['inline_fields'],has_next_action='No implementation files exist' in text)
    assert report['corrected']['bytes']<=16000 and report['corrected']['has_feedback'] and report['corrected']['has_next_action']
    import copy,autonomous_repair
    amended=copy.deepcopy(logical);amended['builder']['context']['builder_feedback']=autonomous_repair.REPAIR_INSTRUCTION
    sensitivity=dict(version='long-repair-feedback-sensitivity-v1',transformation='Replace only builder_feedback with the actual server repair instruction; all other recorded inputs fixed. Controlled sensitivity, not an original dispatch.',context_sha256=digest(canonical(amended['builder']['context'])))
    for name,implementation in [('baseline',old),('corrected',builder)]:
        work=out/('long-feedback-'+name);work.mkdir();implementation.restore(checkpoint,work)
        text,manifest=implementation.bootstrap(amended,work,out,history)
        (out/('long-feedback-'+name+'-bootstrap.txt')).write_text(text)
        sensitivity[name]=dict(bytes=len(text.encode()),inline_fields=manifest['inline_fields'],sha256=digest(text.encode()),has_feedback='builder_feedback' in manifest['inline_fields'])
    report['sensitivity']=sensitivity
    release.save(out/'report.json',dict(report,passed=False))
    assert not sensitivity['baseline']['has_feedback'] and sensitivity['corrected']['has_feedback']
    report['passed']=True
    manifest=[]
    for p in sorted(base.iterdir()):
        if p.is_file():raw=p.read_bytes();manifest.append(dict(path=str(p.relative_to(ROOT)),sha256=digest(raw),bytes=len(raw)))
    release.save(out/'original-artifact-manifest.json',manifest);release.save(out/'report.json',report)
    print(json.dumps(dict(directory=str(out),report=report)))

if __name__=='__main__':
    if sys.argv[1:]==['--worker-spool']:worker_spool()
    elif sys.argv[1:]==['--local-builder-replay']:local_builder_replay()
    elif sys.argv[1:]:raise SystemExit('Only fixed read-only --worker-spool or --local-builder-replay inspection is supported.')
    else:main()
