"""Fixed staged continuation qualification; no production runtime replacement."""
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_workflow'))
import autonomy,autonomy_methods,autonomy_model,experiment_builder as builder
import network_spec,openclaw_runtime as runtime,shared_campaigns,store
from workflow import canonical,digest,validate_protocol

packet=json.loads((ROOT/'frozen.json').read_bytes())
for name,sha in packet['source_files'].items():
    assert digest((ROOT/name).read_bytes())==sha,name
assert os.getuid()!=0 and os.environ['SUPABASE_URL']=='https://regphejnlvfpyokpniny.supabase.co'
prompts={p['module_id']:p for p in packet['prompts']}
for p in prompts.values():assert digest((p['system_prompt']+'\n\n'+p['research_context']).encode())==p['content_sha256']

def save(path,value):
    temp=path.with_suffix('.writing');temp.write_bytes(canonical(value));temp.replace(path)

def put(name,raw):
    path='qualification/builder-continuation-v1/'+ROOT.name+'/'+digest(raw)+'-'+name
    url='/storage/v1/object/research-workflow-raw/'+path
    try:store.request(url,'POST',raw)
    except Exception:
        if store.request(url,raw=True)!=raw:raise
    assert store.request(url,raw=True)==raw
    return dict(bucket='research-workflow-raw',path=path,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw),public=False)

def prepare():
    result=subprocess.run(['/opt/jumpserve/python/bin/python','-B',str(ROOT/'research_workflow/tests/prepare_builder_image.py')],capture_output=True,timeout=660)
    (ROOT/'prepare-stdout.bin').write_bytes(result.stdout);(ROOT/'prepare-stderr.bin').write_bytes(result.stderr)
    assert result.returncode==0,'Prepared image check failed; original output retained.'
    image=json.loads((ROOT/'.test-artifacts/builder-image/continuation-v1.json').read_bytes())
    assert image['status']=='passed' and image['platform']=='linux/amd64'
    modules=ROOT/'experiments/openclaw_pilot/runtime/node_modules';modules.mkdir(parents=True,exist_ok=True)
    for name,target in [('openclaw',runtime.PACKAGE),('node',runtime.NODE.parents[1])]:
        p=modules/name
        if p.exists():assert p.resolve()==target.resolve()
        else:p.symlink_to(target,target_is_directory=True)
    template=prompts[builder.MODULE]
    (ROOT/'.test-artifacts/builder-image/published-prompt-v2.json').write_bytes(canonical({k:template[k] for k in ('id','module_id','version','system_prompt','research_context','content_sha256')}))
    save(ROOT/'prepared.json',dict(status='passed',image=image['image'],platform=image['platform'],package_inventory_sha256=image['package_inventory_sha256'],measured_charges_usd=None))

def native():
    assert not (ROOT/'native.json').exists(),'Never replay a dispatched native control.'
    sys.path.insert(0,str(ROOT/'research_workflow/tests'))
    spec=importlib.util.spec_from_file_location('native_control',ROOT/'research_workflow/tests/check_experiment_builder_linux.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    package=builder.builder_package();module.prepare=lambda *_:package
    module.main()
    reports=sorted((ROOT/'.test-artifacts/experiment-builder').glob('*/report.json'));assert len(reports)==1
    report=json.loads(reports[0].read_bytes());assert report['status']=='passed' and report['live_provider_calls']==0 and report['slots']==3
    cleanup=reaper_control() if packet.get('amendment') else None
    save(ROOT/'native.json',dict(status='passed',report=report,report_sha256=digest(reports[0].read_bytes()),production_equivalent_restrictions=True,repeated_retirement_control=cleanup))

def reaper_control():
    """Real Docker cleanup; explicitly synthetic task and artifact transport."""
    task=str(uuid.uuid4());study=str(uuid.uuid4());root=ROOT/'cleanup-control';path=root/'builder-workspaces'/task;path.mkdir(parents=True)
    image=json.loads((ROOT/'prepared.json').read_bytes())['image'];prefix='js-build-'+task.replace('-','')+'-cleanup-fixture'
    original=b'{"kind":"synthetic prior retirement fixture"}'
    for name in ('retired.json','retirement-pending.json'):(path/name).write_bytes(original)
    captured=[]
    def rows(kind,*args,**kwargs):
        return [dict(id=task,study_id=study,status='resolved')] if kind=='autonomy_tasks' else [dict(status='completed',deadline_at='2030-01-01T00:00:00Z')] if kind=='autonomy_workflows' else [dict(owner_id=str(uuid.uuid4()))]
    def artifact(study,owner,raw,identity,*args):
        captured.append(dict(id=identity,sha256=digest(raw)));(root/('receipt-'+str(len(captured))+'.json')).write_bytes(raw);return dict(id=identity)
    try:
        with patch.object(store,'rows',side_effect=rows),patch.object(store,'artifact',side_effect=artifact),patch.object(store,'append'):
            for _ in range(2):
                subprocess.run(['docker','create','--name',prefix,'--network','none','--read-only','--pids-limit','32','--memory','128m',image,'true'],capture_output=True,check=True,timeout=15)
                builder.reap(root)
                assert subprocess.run(['docker','inspect',prefix],capture_output=True,timeout=10).returncode!=0
            builder.reap(root)
        assert len(captured)==2 and len({x['id'] for x in captured})==2
        assert (path/'retirement-history'/(digest(original)+'.json')).read_bytes()==original
        return dict(status='passed',real_container_retirements=2,receipts=captured,original_preserved=True,task_and_storage_transport='Explicit synthetic fixture; not production task records.')
    finally:builder.container_action(task,'remove')

def replay():
    assert not (ROOT/'replay.json').exists(),'Retain the previous reanalysis.'
    original=store.request;reads=[];out=ROOT/'replay-originals';out.mkdir()
    def read(path,method='GET',body=None,public=False,raw=False):
        if method!='GET' or body is not None:raise ValueError('Reanalysis forbids writes, model calls and execution.')
        data=original(path,method=method,public=public,raw=True)
        name=str(len(reads)).zfill(4)+'-'+digest(data)+'.bin';(out/name).write_bytes(data)
        reads.append(dict(path=path,sha256=digest(data),bytes=len(data),file=name))
        return data if raw else json.loads(data)
    results=[]
    with patch.object(store,'request',side_effect=read):
        tasks=store.rows('autonomy_tasks',dict(study_id='eq.'+packet['assessment'],limit=100))
        for task in tasks:
            if not task.get('claim_id') or not task.get('context',{}).get('proposal',{}).get('protocol',{}).get('decision'):continue
            try:
                finding=autonomy.numeric_finding(task)
                results.append(dict(task_id=task['id'],status='computed-read-only' if finding else 'no-complete-decision',finding=finding,scientific_assessment_written=False))
            except ValueError as error:
                results.append(dict(task_id=task['id'],status='method-or-integrity-gap',reason=str(error),scientific_assessment_written=False))
    assert results,'No retained numerical candidate was exercised.'
    save(ROOT/'replay.json',dict(status='passed',scope='GET-only reanalysis of original recorded inputs; no production assessment or criterion changed.',results=results,reads=reads,production_writes=0))

def live():
    assert not (ROOT/'live.json').exists(),'Never replay a dispatched live campaign.'
    limits=packet['protocol']['resources'];began=time.monotonic();lock=threading.RLock();artifacts={}
    report=dict(status='running',started_at=dt.datetime.now(dt.timezone.utc).isoformat(),admissions=0,reserved_cents=0,live_provider_calls_issued=0,cases=[],usage=None,measured_charges_usd=None,subscription_allocation_usd=None,reviewer=dict(type='AI',identity='Implementing Codex assistant',independent=False,human=False))
    def write():save(ROOT/'live.json',report)
    def retain(job,name,raw,kind='builder-original'):
        identity=str(uuid.uuid5(uuid.UUID(job['id']),name));p=ROOT/'live-originals'/job['id']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        pointer=put(job['id']+'-'+name,raw);artifacts[identity]=raw
        p.with_suffix(p.suffix+'.pointer.json').write_bytes(canonical(pointer))
        return dict(artifact_id=identity,sha256=digest(raw),version=builder.VERSION)
    def admit(operation,job,**payload):
        with lock:
            if operation=='begin':
                if report['admissions']>=limits['maximum_native_case_calls'] or time.monotonic()-began>=limits['maximum_elapsed_seconds']:return dict(denied='qualification-budget')
                report['admissions']+=1;report['reserved_cents']+=100;result={'id':str(uuid.uuid4())}
            else:result={}
            event=dict(operation=operation,job=job,payload=payload,result=result,at=dt.datetime.now(dt.timezone.utc).isoformat())
            with (ROOT/'live-ledger.jsonl').open('ab') as sink:sink.write(canonical(event)+b'\n');sink.flush();os.fsync(sink.fileno())
            put('ledger-'+digest(canonical(event))+'.json',canonical(event));write();return result
    write();job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','task_id','lease_token')}
    image=json.loads((ROOT/'prepared.json').read_bytes())['image'];p=prompts[builder.MODULE]
    context=packet['native_context'];authority=builder.action_policy()
    logical=dict(modelId=runtime.MODEL,system=[dict(text=p['system_prompt']+'\n\n'+p['research_context']),dict(text=autonomy_model.TURN_POLICY['instruction']),dict(text=authority['document']['instruction']),dict(text=autonomy_methods.INSTRUCTION)],builder=dict(version=builder.VERSION,context=context,checkpoint=None,execution_authority={k:authority[k] for k in ('version','sha256')}))
    case=dict(name='bounded-context-source-calculation',status='pending',receipts=[],actual_answer_reviewed=False)
    report['cases'].append(case)
    work=ROOT/'builder-workspaces'/job['task_id']/'workspace';work.mkdir(parents=True)
    failure=b'Explicit synthetic earlier development failure fixture: exit 3; no successful result.\n';(work/'previous-failure.log').write_bytes(failure)
    inherited=packet.get('inherited_native')
    if inherited:
        original=(ROOT/'inherited-native-checkpoint.zip').read_bytes();assert digest(original)==inherited['checkpoint_sha256']
        builder.restore(original,work)
        case['inherited_native_evidence']=inherited
    try:
        runtime.verify_runtime();runtime.catalog(runtime.credential())
        with patch.object(builder,'retain',side_effect=retain),patch.object(builder,'rpc',side_effect=admit),patch.object(store,'artifact_bytes',side_effect=lambda study,identity,**kw:artifacts[identity]),patch.dict(os.environ,OPENCLAW_BUILDER_IMAGE=image):
            while not inherited and report['admissions']<limits['maximum_native_case_calls'] and time.monotonic()-began<limits['maximum_elapsed_seconds']:
                directory=ROOT/('live-native-'+str(len(case['receipts'])+1))
                _,receipt=builder.execute(logical,directory,job);case['receipts'].append(receipt)
                report['live_provider_calls_issued']+=receipt.get('provider_calls',0);write()
                if receipt['status']!='complete':raise ValueError('Native outcome needs reconciliation: '+str(receipt.get('error_code')))
                if (work/'answer.json').exists():break
                logical['builder']['checkpoint']=receipt['checkpoint'];context['builder_feedback']=receipt.get('feedback')
                job=dict(job,id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
        assert (work/'answer.json').exists(),'Native answer not completed within declared limits.'
        answer=json.loads((work/'answer.json').read_bytes());computed=json.loads((work/'calculation-output.json').read_bytes())
        assert answer==computed,'Answer differs from the retained calculation output.'
        expected=dict(baseline_mbit_s=72,treatment_mbit_s=97.2,relative_change_percent=35,missing_value=None,scope='source-consistency-only',main_campaign_executed=False,prior_failure_preserved=True)
        assert answer==expected,answer
        assert (work/'previous-failure.log').read_bytes()==failure
        retained=json.loads((work/'research-context.json').read_bytes())
        assert retained['required_source_packet']==packet['native_context']['required_source_packet']
        assert (work/'calculation.py').stat().st_size>0
        history=json.loads((work/'native-tool-history.json').read_bytes())
        commands=[json.loads(h['arguments']).get('command','') for h in history if h.get('type')=='function_call' and h.get('name')=='exec']
        assert any('calculation.py' in c for c in commands),'No actual calculation command retained.'
        assert not any(re.search(r'\b(?:apt(?:-get)?|dnf)\s+install\b',c) for c in commands),'Prepared networking dependencies were redundantly installed.'
        # A changed-input correctness control is separate from the source fixture
        # and never appended as a paper observation. Execute unchanged code.
        control=ROOT/'changed-input-control';control.mkdir()
        for name in ('calculation.py','previous-failure.log'):shutil.copyfile(work/name,control/name)
        context_bytes=(work/'research-context.json').read_bytes()
        changed=json.loads(context_bytes)
        changed['required_source_packet']['source_cells'].update(baseline_mbit_s='80.0',treatment_mbit_s='100.0')
        (control/'research-context.json').write_bytes(context_bytes if inherited else canonical(changed))
        command=['docker','run','--rm','--network','none','--read-only','--pids-limit','64','--memory','256m','--cpus','0.5','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(control)+',dst=/workspace',image,'python3','/workspace/calculation.py']
        check=subprocess.run(command,capture_output=True,timeout=20)
        (control/'stdout.bin').write_bytes(check.stdout);(control/'stderr.bin').write_bytes(check.stderr)
        assert check.returncode==0,'Generated code failed the original-input software control.'
        altered=json.loads((control/'calculation-output.json').read_bytes())
        if inherited:
            assert altered==expected
            (control/'original-context.json').write_bytes(context_bytes);(control/'original-output.json').write_bytes((control/'calculation-output.json').read_bytes())
            for name in ('calculation-output.json','answer.json'):(control/name).unlink()
            modified=canonical(changed);(control/'changed-context.json').write_bytes(modified);(control/'research-context.json').write_bytes(modified)
            negative=subprocess.run(command,capture_output=True,timeout=20)
            (control/'changed-stdout.bin').write_bytes(negative.stdout);(control/'changed-stderr.bin').write_bytes(negative.stderr)
            assert negative.returncode!=0 and b'AssertionError' in negative.stderr
            assert not (control/'calculation-output.json').exists() and not (control/'answer.json').exists()
        else:
            assert altered==dict(expected,baseline_mbit_s=80,treatment_mbit_s=100,relative_change_percent=25),'Generated program copied the expected answer instead of computing from input.'
        assert digest((control/'calculation.py').read_bytes())==digest((work/'calculation.py').read_bytes())
        case.update(status='awaiting-substantive-review',answer=answer,commands=commands,files={n:dict(sha256=digest((work/n).read_bytes()),bytes=(work/n).stat().st_size) for n in ('answer.json','calculation.py','calculation-output.json','previous-failure.log')})
        case['changed_input_control']=dict(status='passed',kind='original-input-positive-and-altered-input-integrity-rejection' if inherited else 'changed-numerical-input',command=command,output=altered,unchanged_program_sha256=digest((control/'calculation.py').read_bytes()),original_failed_control_preserved=bool(inherited))
        write()
        assert report['admissions']<limits['maximum_real_provider_calls'] and time.monotonic()-began<limits['maximum_elapsed_seconds']
        context=packet['planning_context'];p=prompts['research-autonomy'];logical=autonomy_model.request(p['system_prompt']+'\n\n'+p['research_context'],context)
        report['admissions']+=1;report['reserved_cents']+=100;write()
        original=canonical(logical);retain(job,'planning-logical.json',original)
        response,receipt=runtime.execute(logical,ROOT/'live-planning');report['live_provider_calls_issued']+=1 if response else receipt.get('provider_calls',0)
        if not response:raise ValueError('Planner outcome needs reconciliation: '+str(receipt.get('status')))
        output=autonomy_model.parse(response);autonomy_model.validate_phase(output,context)
        assert output['action']=='propose' and output['proposal'] and not output['coverage_complete'] and output['assessment_label'] is None
        proposal=output['proposal'];p=proposal['protocol'];claim=context['claim'];assert p['hypotheses']==claim['description']
        autonomy_methods.validate(p,claim);validate_protocol(network_spec.bind_inputs(p))
        assert shared_campaigns.identity(proposal,claim['source_id'])[1]==packet['expected_acquisition_sha256'],'Planner changed the frozen reusable acquisition.'
        known={x['sha256'] for x in context['reusable_protocol']['input_versions']}
        assert all(v['sha256'] in known for v in p['input_versions']),'Planner invented an input hash.'
        report['cases'].append(dict(name='shared-acquisition-planning',status='awaiting-substantive-review',output=output,receipt=receipt,actual_answer_reviewed=False,request_sha256=digest(original)))
        report['status']='awaiting-substantive-review'
    except Exception:
        report.update(status='failed-or-paused',failure=traceback.format_exc());raise
    finally:
        report.update(ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),wall_seconds=time.monotonic()-began)
        write();builder.container_action(job['task_id'],'remove')

def evidence():
    selected={}
    for p in ROOT.rglob('*'):
        if not p.is_file() or p.is_symlink():continue
        rel=p.relative_to(ROOT);parts=rel.parts
        if any(x in parts for x in ('state','node_modules','builder-vendor')) or p.name in ('config.json','evidence.json'):continue
        if str(rel).startswith('experiments/'):continue
        allowed=(p.suffix in ('.json','.jsonl','.py','.mjs','.bin','.txt','.log','.Dockerfile','.zip') or p.name in ('task.txt','Dockerfile.original'))
        if not allowed:continue
        raw=p.read_bytes()
        if len(raw)>5000000:continue
        selected[str(rel)]=raw
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(selected.items()):archive.writestr(name,raw)
        archive.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(v),bytes=len(v)) for n,v in sorted(selected.items())]))
    assert len(stream.getvalue())<=20000000
    pointer=put('evidence.zip',stream.getvalue());save(ROOT/'evidence.json',pointer)
    print(json.dumps(dict(status='retained',archive=pointer)))

if __name__=='__main__':
    action=sys.argv[1];assert action in ('prepare','native','replay','live','evidence')
    try:globals()[action]()
    except Exception:
        save(ROOT/(action+'-failure.json'),dict(status='failed',traceback=traceback.format_exc()));raise
