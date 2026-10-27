"""Fixed-target, isolated builder v2 qualification; never publish or deploy.

The candidate has its own runtime, vendor copy, image, spool and service units.
Production services, prompt pointers and worker environment are not changed.
"""
import argparse,base64,datetime as dt,importlib.util,io,json,pathlib,shlex,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/builder-qualification-v2';PROMPT='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27'
def storage(path,raw=None):
    key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
    url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path
    headers={'apikey':key,'Authorization':'Bearer '+key}
    request=urllib.request.Request(url,data=raw,headers={**headers,'Content-Type':'application/octet-stream'},method='POST') if raw is not None else urllib.request.Request(url,headers=headers)
    with r.prior.guard.OPEN.open(request,timeout=60) as response:return response.read(20000001)
def selected():
    identity=(BASE/'selected.txt').read_text().strip();assert identity.isalnum()
    return BASE/identity
def command(source,mode,commands):
    result=r.ssm(commands);(source/(mode+'-command.json')).write_text(json.dumps(result,indent=2)+'\n');return result
def retain_validation(source,correction=False):
    """Retain a fixed allowlist of local qualification evidence, never auth/config."""
    pointer=source/('local-evidence-correction-archive.json' if correction else 'local-evidence-archive.json')
    if pointer.exists():
        item=json.loads(pointer.read_bytes());raw=storage(item['path'])
        assert r.sha(raw)==item['sha256']==item['retrieved_sha256']
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for entry in json.loads(z.read('artifact-manifest.json')):
                assert r.sha(z.read(entry['path']))==entry['sha256']
        return item
    files={}
    def add(root,name,prefix):
        p=root/name;assert p.is_file() and not p.is_symlink(),name
        raw=p.read_bytes();assert len(raw)<6000000,name
        files[prefix+'/'+name]=raw
    if correction:
        for name in ('metadata-correction.json','local-evidence-archive.json'):
            add(source,name,'correction')
    for name in ('experiment-builder-qualification-v2.md','experiment-builder-live-evaluation-v1.json',
                 'experiment-action-policy-live-amendment-v1.json','experiment-builder-live-amendment-v6.json',
                 'experiment-builder-live-amendment-v7.json','experiment-builder-portability-check-v2.json',
                 'experiment-builder-cost-review-v2.json','experiment-builder-actual-answer-review-v2-initial.json'):
        add(ROOT/'docs',name,'protocols-and-reviews')
    for name in ('compute.json','storage.json','egress.json','ipv4.json','ipv4-family.json','vpc-region.json','review.json'):
        add(ROOT/'.test-artifacts/builder-cost-review',name,'original-price-list')
    for name in ('research-workflow-runtime.json','database/202610270006_experiment_builder_prompt_v2.sql',
                 'database/202610270007_experiment_builder_v2_publication.sql','bin/qualify-experiment-builder.py',
                 'bin/review-builder-v2-evidence.py','bin/check-builder-v2-project.py',
                 'bin/prepare-experiment-builder-host.sh','bin/experiment-builder-release.py','bin/openclaw-release.py'):
        add(ROOT,name,'current-release-source')
    for name in ('autonomy_costs.py','policies/built-package-costs-v2.json'):
        add(BACK/'research_workflow',name,'current-backend-source')
    for name in ('builder-v2-infra-tests-all.log','builder-v2-cli-contracts.log','builder-v2-autonomy-database.log'):
        add(ROOT/'.test-artifacts',name,'local-check-logs')
    add(BACK/'.test-artifacts','builder-v2-backend-tests-final-v2.log','local-check-logs')
    for identity,leaf in [('20261027T224024286483Z','report.json'),('20261027T224441360007Z','autonomy-validation-report.json')]:
        directory=ROOT/'.test-artifacts/research-ideas/database'/identity
        for p in sorted(directory.iterdir()):
            if p.is_file() and (p.name==leaf or p.name.startswith('raw-') or p.name=='database-fixture-snapshot.json'):
                add(directory,p.name,'local-database/'+identity)
    for identity in ('20261027T225907968869Z','20261027T230543767200Z'):
        directory=ROOT/'.test-artifacts/builder-v2-portability'/identity
        for p in sorted(directory.rglob('*')):
            if p.is_file():add(directory,str(p.relative_to(directory)),'wrapper-portability/'+identity)
    for identity in ('20261027T215002415721Z','20261027T215141225797Z'):
        add(BACK/'.test-artifacts/experiment-builder'/identity,'report.json','local-native/'+identity)
    for name in ('candidate.json','archive.json','followup-archive.json','supplement-archive.json','image-archive.json','image-manifest.json','followup-frozen.json'):
        add(source,name,'remote-original-pointers')
    wheel='six-1.17.0-py2.py3-none-any.whl';add(source,wheel,'later-independent-retrieval')
    assert r.sha((source/wheel).read_bytes())=='4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274'
    metadata=dict(url='https://files.pythonhosted.org/packages/b7/ce/149a00dd41f10bc29e5921b496af8b574d8413afcd5e30dfa0ed46c2cc5e/'+wheel,
                  version='six 1.17.0 wheel',status='retrieved-and-hash-verified',bytes=11050,
                  file_modified_at=dt.datetime.fromtimestamp((source/wheel).stat().st_mtime,dt.timezone.utc).isoformat(),
                  exact_retrieval_timestamp=None,successful_retrievals_observed=1,total_attempts=None,
                  scope='Later independent matching-byte retrieval; not the original native pip download. Timestamp above is filesystem metadata. Original source log supplies URL/hash; no full dependency source review claimed.')
    files['later-independent-retrieval/provenance.json']=json.dumps(metadata,indent=2).encode()
    files['scope.json']=json.dumps(dict(campaign=source.name,created_at=r.stamp(),purpose='Fixed local validation/price/source capsule; not another model campaign or production release.',
        backend_revision='f5453c866bfd74e770398fd6adfebae3265b01c6',measured_charges_usd=None,
        excluded='Authentication state, environment files, account credentials and image chunks. Image originals have their separate ordered manifest.'),indent=2).encode()
    manifest=[dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())]
    files['artifact-manifest.json']=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for n,raw in sorted(files.items()):z.writestr(n,raw)
    raw=stream.getvalue();assert len(raw)<=20000000
    kind='local-validation-metadata-correction' if correction else 'local-validation'
    path='qualification/experiment-builder-v2/'+source.name+'/'+kind+'/'+r.sha(raw)+'.zip'
    storage(path,raw);restored=storage(path);assert restored==raw
    with zipfile.ZipFile(io.BytesIO(restored)) as z:
        for entry in manifest:assert r.sha(z.read(entry['path']))==entry['sha256']
    item=dict(bucket='research-workflow-raw',path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),members=len(manifest),public=False)
    (source/('local-evidence-correction.zip' if correction else 'local-evidence.zip')).write_bytes(raw);pointer.write_text(json.dumps(item,indent=2)+'\n');return item
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','prepare','smoke','start','status','collect','snapshot','collect-snapshot','followup','followup-status','collect-followup','control','evidence','collect-evidence','retain-image','collect-image','retain-validation','retain-validation-correction','record']);a=p.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);audit=BASE/('audit-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));audit.mkdir()
    report=dict(mode=a.mode,status='running',targets=r.target(),measured_charges_usd=None)
    try:
        if a.mode=='freeze':
            assert not (BASE/'selected.txt').exists(),'This amendment is already frozen. Preserve it; a new campaign needs a new versioned protocol and cumulative resource accounting.'
            source=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');source.mkdir()
            # An unpublished prompt is experiment data; schema/publication changes wait for deployment.
            sql=(ROOT/'database/202610270006_experiment_builder_prompt_v2.sql').read_text();r.admin.query(sql,read_only=False)
            prompt=r.admin.query("select id,version,system_prompt,research_context,content_sha256,published_at from agent_prompt_versions where id='"+PROMPT+"'")[0]
            assert prompt['published_at'] is None
            amendment=json.loads((ROOT/'docs/experiment-builder-live-amendment-v6.json').read_bytes())
            cases=json.loads((ROOT/'test/experiment-builder-live-cases-v2.json').read_bytes())
            original=json.loads((ROOT/'test/experiment-builder-live-cases-v1.json').read_bytes())
            assert [x for x in cases['cases'] if x['set']=='held-out']==[x for x in original['cases'] if x['set']=='held-out']
            files=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())['files']
            files={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in [*files,'openclaw-builder-patch.json']}
            import sys
            sys.path.insert(0,str(BACK/'research_workflow'));import autonomy_model,experiment_builder as b
            packet=dict(protocol='experiment-builder-live-evaluation-v1',amendment=amendment,input_version=cases['version'],cases=cases['cases'],runtime_files=files,
                runtime_candidate_sha256=r.sha(json.dumps(files,sort_keys=True,separators=(',',':')).encode()),execution_contract_sha256=r.sha(b.canonical(b.execution_contract())),
                prompt_id=PROMPT,prompt_sha256=prompt['content_sha256'],system_prompt=prompt['system_prompt'],research_context=prompt['research_context'],
                producer_sha256=r.sha((ROOT/'bin/experiment_builder_qualification_v2_host.py').read_bytes()),
                blocker_contract=dict(kinds=list(autonomy_model.BLOCKERS),details=list(autonomy_model.DETAILS),capacity_required_input=autonomy_model.LIMIT_INPUT),
                frozen_at=r.stamp(),source_revision=r.subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip(),source_dirty=True,
                input_sha256=r.sha((ROOT/'test/experiment-builder-live-cases-v2.json').read_bytes()))
            (source/'frozen.json').write_text(json.dumps(packet,indent=2)+'\n')
            stage={('research_workflow/'+n):(BACK/'research_workflow'/n).read_bytes() for n in files}
            for leaf in ('experiment-builder.Dockerfile','tests/check_experiment_builder_linux.py','tests/prepare_builder_vendor.py'):
                stage['research_workflow/'+leaf]=(BACK/'research_workflow'/leaf).read_bytes()
            stage['experiment_builder_qualification_v2_host.py']=(ROOT/'bin/experiment_builder_qualification_v2_host.py').read_bytes()
            stage['frozen.json']=(source/'frozen.json').read_bytes()
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                for n,raw in sorted(stage.items()):z.writestr(n,raw)
                z.writestr('candidate-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(stage.items())]))
            raw=stream.getvalue();path='qualification/experiment-builder-v2/'+source.name+'/candidate-'+r.sha(raw)+'.zip'
            storage(path,raw);assert storage(path)==raw
            (source/'candidate.zip').write_bytes(raw);(source/'candidate.json').write_text(json.dumps(dict(path=path,sha256=r.sha(raw),bytes=len(raw)),indent=2)+'\n')
            (BASE/'selected.txt').write_text(source.name+'\n');report.update(campaign=source.name,candidate_sha256=r.sha(raw),frozen_sha256=r.sha((source/'frozen.json').read_bytes()))
        else:
            source=selected();host='/var/lib/jumpserve-openclaw/builder-qualification-v2/'+source.name
            report['campaign']=source.name
            if a.mode in ('retain-validation','retain-validation-correction'):
                report['archive']=retain_validation(source,correction=a.mode=='retain-validation-correction')
            elif a.mode=='prepare':
                assert not (source/'prepare-command.json').exists(),'Inspect existing preparation; never silently replay it.'
                item=json.loads((source/'candidate.json').read_bytes())
                install="""import io,json,pathlib,sys,zipfile
sys.path.insert(0,'/opt/jumpserve/runtime')
import store
from workflow import digest
raw=store.request('/storage/v1/object/research-workflow-raw/'+OBJECT,raw=True);assert digest(raw)==HASH
root=pathlib.Path(DEST);root.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 for item in json.loads(z.read('candidate-manifest.json')):
  name=pathlib.PurePosixPath(item['path']);assert not name.is_absolute() and '..' not in name.parts
  value=z.read(item['path']);assert digest(value)==item['sha256'];p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
(root/'.test-artifacts/builder-image').mkdir(parents=True)
(root/'experiments/openclaw_pilot/runtime').mkdir(parents=True)
(root/'experiments/openclaw_pilot/runtime/node_modules').symlink_to('/opt/jumpserve/openclaw/node_modules',target_is_directory=True)
""".replace('OBJECT',repr(item['path'])).replace('HASH',repr(item['sha256'])).replace('DEST',repr(host))
                vendor="import sys;from pathlib import Path;sys.path.insert(0,"+repr(host+'/research_workflow/tests')+");from prepare_builder_vendor import prepare;prepare(Path('/opt/jumpserve/openclaw/node_modules/openclaw'),Path("+repr(host+'/.test-artifacts/builder-vendor/node_modules/openclaw')+"),Path("+repr(host+'/research_workflow/openclaw-builder-patch.json')+"))"
                inspect="import json,pathlib,pwd,sys;p=pathlib.Path("+repr(host)+");d=json.load(sys.stdin)[0];u=pwd.getpwnam('jumpserve');v=dict(status='passed',image=d['Id'],uid=u.pw_uid,gid=u.pw_gid,platform=d['Os']+'/'+d['Architecture']);(p/'.test-artifacts/builder-image/selected.json').write_text(json.dumps(v));(p/'image-id.txt').write_text(d['Id']);print(json.dumps(v))"
                commands=['set -eu','set -a','. /etc/jumpserve-openclaw.env','set +a','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(install),
                    'chown -R jumpserve:jumpserve '+host,
                    'docker build --platform linux/amd64 --build-arg BASE_IMAGE=ubuntu@sha256:e0f80c829509ef4df9e76bd8944eb7b8ec25cbb379b112a7f9448b2c77a77c9b --build-arg WORKSPACE_UID="$(id -u jumpserve)" --build-arg WORKSPACE_GID="$(id -g jumpserve)" -t jumpserve-builder:qualification-v2 -f '+host+'/research_workflow/experiment-builder.Dockerfile '+host+'/research_workflow > '+host+'/image-build.log 2>&1',
                    "docker image inspect jumpserve-builder:qualification-v2 | /opt/jumpserve/python/bin/python -B -c "+shlex.quote(inspect),
                    '/opt/jumpserve/python/bin/python -B -c '+shlex.quote(vendor)]
                report['ssm']=command(source,'prepare',commands)
            elif a.mode=='smoke':
                assert not (source/'smoke-command.json').exists()
                program="""import importlib.util,json,pathlib,sys
root=pathlib.Path(ROOT);sys.path.insert(0,str(root/'research_workflow'))
spec=importlib.util.spec_from_file_location('native_smoke',root/'research_workflow/tests/check_experiment_builder_linux.py');module=importlib.util.module_from_spec(spec);sys.path.insert(0,str(root/'research_workflow/tests'));spec.loader.exec_module(module)
module.main()
(root/'smoke-complete.json').write_text(json.dumps(dict(status='passed',scope='Real native file/edit/exec/sudo/read/resume on Linux x86; synthetic model, zero provider calls.')))
""".replace('ROOT',repr(host))
                cmd='set -eu\nset -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)
                report['ssm']=command(source,'smoke',[cmd])
            elif a.mode=='start':
                assert not (source/'start-command.json').exists(),'Never replay a qualification dispatch.'
                cmd='set -eu\nset -a\n. /etc/jumpserve-openclaw.env\nset +a\nexport OPENCLAW_BUILDER_IMAGE="$(cat '+host+'/image-id.txt)"\nexport OPENCLAW_BUILDER_PACKAGE='+shlex.quote(host+'/.test-artifacts/builder-vendor/node_modules/openclaw')+'\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host+'/experiment_builder_qualification_v2_host.py > '+host+'/run.log 2>&1'
                check="import json,pathlib;assert json.loads(pathlib.Path("+repr(host+'/smoke-complete.json')+").read_bytes())['status']=='passed'"
                report['ssm']=command(source,'start',['set -eu','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(check),'systemd-run --unit=jumpserve-builder-qualification-v2-'+source.name.lower()+' --property=RuntimeMaxSec=3700 /bin/bash -c '+shlex.quote(cmd)])
            elif a.mode=='status':
                for kind in ('prepare','smoke','start','control','evidence','retain-image'):
                    path=source/(kind+'-command.json')
                    if path.exists():
                        call=json.loads(path.read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id']);(source/(kind+'-result.json')).write_text(json.dumps(value,indent=2)+'\n');report[kind]=dict(status=value['Status'],stdout=value.get('StandardOutputContent','')[-2000:],stderr=value.get('StandardErrorContent','')[-1500:])
                program="import json,pathlib;p=pathlib.Path("+repr(host)+");v=json.loads((p/'report.json').read_bytes()) if (p/'report.json').exists() else {};v['cases']=[{k:x[k] for k in ('name','set','status','provider_calls','reason') if k in x} for x in v.get('cases',[])];print(json.dumps(dict(report=v,archive=json.loads((p/'archive.json').read_bytes()) if (p/'archive.json').exists() else None,log_tail=(p/'run.log').read_text()[-1000:] if (p/'run.log').exists() else None)))"
                report['ssm']=command(source,'status',['/opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)])
            elif a.mode=='collect':
                call=json.loads((source/'status-command.json').read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id']);assert value['Status']=='Success'
                observed=json.loads(value['StandardOutputContent']);(source/'observed.json').write_text(json.dumps(observed,indent=2)+'\n')
                report['progress']={k:v for k,v in (observed.get('report') or {}).items() if k!='cases'};report['cases']=[dict(name=x['name'],status=x['status'],provider_calls=x['provider_calls']) for x in (observed.get('report') or {}).get('cases',[])]
                if observed.get('archive'):
                    archive=observed['archive'];raw=storage(archive['path']);assert r.sha(raw)==archive['sha256']==archive['retrieved_sha256'];(source/'originals.zip').write_bytes(raw)
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
                        (source/'host-report.json').write_bytes(z.read('report.json'))
                    (source/'archive.json').write_text(json.dumps(archive,indent=2)+'\n');report['archive']=archive
            elif a.mode=='control':
                assert not (source/'control-command.json').exists(),'Inspect the original control; do not silently replay it.'
                program="""import importlib.util,json,pathlib,sys
from unittest.mock import patch
root=pathlib.Path(ROOT);assert json.loads((root/'report.json').read_bytes())['status']!='running' and (root/'archive.json').exists()
sys.path.insert(0,str(root/'research_workflow'));sys.path.insert(0,str(root/'research_workflow/tests'))
spec=importlib.util.spec_from_file_location('native_control',root/'research_workflow/tests/check_experiment_builder_linux.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
before=set((root/'.test-artifacts/experiment-builder').glob('*'));original=module.builder.config
def root_user(*a,**kw):
 result=original(*a,**kw);result['agents']['defaults']['sandbox']['docker']['user']='0:0';return result
expected_failure=None
try:
 with patch.object(module.builder,'config',side_effect=root_user):module.main()
except (AssertionError,KeyError) as error:expected_failure=type(error).__name__+': '+str(error)
created=set((root/'.test-artifacts/experiment-builder').glob('*'))-before;assert len(created)==1 and expected_failure
directory=created.pop();outputs=[x for p in directory.glob('builder-workspaces/*/native-tool-history.json') for x in json.loads(p.read_bytes()) if x.get('type')=='function_call_output']
errors=[x for x in outputs if 'Write verification failed' in str(x)]
assert errors,'Expected root-owner readback discrepancy was not demonstrated'
(root/'root-user-control.json').write_text(json.dumps(dict(status='passed',meaning='Expected integration discrepancy demonstrated, not a scientific finding',expected_original_failure=expected_failure,control_user='0:0',aligned_user=str(__import__('os').getuid())+':'+str(__import__('os').getgid()),only_intentional_configuration_difference='Docker user UID:GID; same image, vendor correction, commands and synthetic responses',original_tool_errors=errors,directory=str(directory),live_provider_calls=0)))
""".replace('ROOT',repr(host))
                report['ssm']=command(source,'control',['set -eu','runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)])
            elif a.mode=='followup':
                assert not (source/'followup-command.json').exists(),'Never replay a feedback follow-up.'
                original=json.loads((source/'host-report.json').read_bytes());assert original['status']!='running' and (source/'archive.json').exists()
                code=(ROOT/'bin/experiment_builder_feedback_followup_host.py').read_bytes();amendment=(ROOT/'docs/experiment-builder-live-amendment-v7.json').read_bytes()
                frozen=dict(producer_sha256=r.sha(code),amendment_sha256=r.sha(amendment),original_report_sha256=r.sha((source/'host-report.json').read_bytes()),original_archive=json.loads((source/'archive.json').read_bytes()),original_calls=original['live_provider_calls'],original_start=original['started_at'])
                (source/'followup-frozen.json').write_text(json.dumps(frozen,indent=2)+'\n')
                child=host+'/followup-v7'
                install="from pathlib import Path;import base64;p=Path("+repr(child)+");p.mkdir(exist_ok=False);(p/'producer.py').write_bytes(base64.b64decode("+repr(base64.b64encode(code).decode())+"));(p/'frozen.json').write_bytes(base64.b64decode("+repr(base64.b64encode(json.dumps(frozen).encode()).decode())+"));(p/'amendment.json').write_bytes(base64.b64decode("+repr(base64.b64encode(amendment).decode())+"))"
                cmd='set -eu\nset -a\n. /etc/jumpserve-openclaw.env\nset +a\nexport OPENCLAW_BUILDER_IMAGE="$(cat '+host+'/image-id.txt)"\nexport OPENCLAW_BUILDER_PACKAGE='+shlex.quote(host+'/.test-artifacts/builder-vendor/node_modules/openclaw')+'\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+child+'/producer.py > '+child+'/run.log 2>&1'
                report['ssm']=command(source,'followup',['set -eu','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(install),'chown -R jumpserve:jumpserve '+child,'systemd-run --unit=jumpserve-builder-feedback-v7-'+source.name.lower()+' --property=RuntimeMaxSec=1900 /bin/bash -c '+shlex.quote(cmd)])
            elif a.mode=='followup-status':
                child=host+'/followup-v7'
                program="import json,pathlib;p=pathlib.Path("+repr(child)+");v=json.loads((p/'report.json').read_bytes()) if (p/'report.json').exists() else {};v['cases']=[{k:x[k] for k in ('name','status','original_provider_calls','cumulative_provider_calls','reason') if k in x} for x in v.get('cases',[])];print(json.dumps(dict(report=v,archive=json.loads((p/'archive.json').read_bytes()) if (p/'archive.json').exists() else None,log_tail=(p/'run.log').read_text()[-1000:] if (p/'run.log').exists() else None)))"
                report['ssm']=command(source,'followup-status',['/opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)])
            elif a.mode=='collect-followup':
                call=json.loads((source/'followup-status-command.json').read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id']);assert value['Status']=='Success'
                observed=json.loads(value['StandardOutputContent']);(source/'followup-observed.json').write_text(json.dumps(observed,indent=2)+'\n');report['progress']=observed['report'];report['log_tail']=observed.get('log_tail')
                if observed.get('archive'):
                    item=observed['archive'];assert item['path'].startswith('qualification/experiment-builder-v2/'+source.name+'/followup-v7/');raw=storage(item['path']);assert r.sha(raw)==item['sha256']==item['retrieved_sha256'];(source/'followup-originals.zip').write_bytes(raw)
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        for item2 in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item2['path']))==item2['sha256']
                        (source/'followup-report.json').write_bytes(z.read('report.json'))
                    (source/'followup-archive.json').write_text(json.dumps(item,indent=2)+'\n');report['archive']=item
            elif a.mode=='snapshot':
                program="""import io,json,pathlib,sys,zipfile
root=pathlib.Path(ROOT);sys.path.insert(0,str(root/'research_workflow'))
import store
from workflow import canonical,digest
report_raw=(root/'report.json').read_bytes();report=json.loads(report_raw);completed=[c for c in report['cases'] if c['status']=='awaiting-review'];files={'original-report.json':report_raw}
for case in completed:
 work=pathlib.Path(case['work']);assert work.is_relative_to(root/'builder-workspaces')
 for p in work.rglob('*'):
  if p.is_file() and not p.is_symlink():files[case['name']+'/'+str(p.relative_to(work))]=p.read_bytes()
files['snapshot-report.json']=canonical(dict(status='partial-snapshot',original_report_sha256=digest(report_raw),cases=completed,limits='Only terminal awaiting-review workspaces; no judgment or complete campaign review implied.'))
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(files.items()):z.writestr(n,b)
 z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]))
raw=stream.getvalue();key='qualification/experiment-builder-v2/'+root.name+'/snapshots/'+digest(raw)+'.zip';url='/storage/v1/object/research-workflow-raw/'+key
store.request(url,'POST',raw);assert store.request(url,raw=True)==raw
print(json.dumps(dict(path=key,sha256=digest(raw),bytes=len(raw),cases=[c['name'] for c in completed])))
""".replace('ROOT',repr(host))
                report['ssm']=command(source,'snapshot',['set -a','. /etc/jumpserve-openclaw.env','set +a','runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)])
            elif a.mode=='collect-snapshot':
                call=json.loads((source/'snapshot-command.json').read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id']);assert value['Status']=='Success'
                item=json.loads(value['StandardOutputContent']);assert item['path'].startswith('qualification/experiment-builder-v2/'+source.name+'/snapshots/')
                raw=storage(item['path']);assert r.sha(raw)==item['sha256'];(source/('snapshot-'+item['sha256']+'.zip')).write_bytes(raw);report['snapshot']=item
            elif a.mode=='evidence':
                program="""import io,json,pathlib,subprocess,sys,zipfile
root=pathlib.Path(ROOT);sys.path.insert(0,str(root/'research_workflow'))
import store
from workflow import canonical,digest
assert json.loads((root/'report.json').read_bytes())['status']!='running' and (root/'archive.json').exists()
files={}
for n in ('image-build.log','image-id.txt','smoke-complete.json','root-user-control.json'):
 p=root/n
 if p.exists():files[n]=p.read_bytes()
vendor=root/'.test-artifacts/builder-vendor/node_modules'
for n in ('builder-patch-original.mjs','builder-patch-receipt.json'):files[n]=(vendor/n).read_bytes()
patch=json.loads(files['builder-patch-receipt.json']);assert digest(files['builder-patch-original.mjs'])==patch['original_sha256']
files['builder-patch-corrected.mjs']=(vendor/'openclaw'/patch['path']).read_bytes();assert digest(files['builder-patch-corrected.mjs'])==patch['corrected_sha256']
for p in (root/'.test-artifacts/experiment-builder').rglob('*'):
 if not p.is_file() or p.is_symlink() or 'state' in p.relative_to(root).parts or p.name=='config.json':continue
 if p.name in ('report.json','receipt.json','stdout.bin','stderr.bin','logical.json','task.txt','workspace-normalization.json') or p.name.startswith(('call-','native-request-')):files[str(p.relative_to(root))]=p.read_bytes()
image=(root/'image-id.txt').read_text().strip()
files['installed-packages.txt']=subprocess.check_output(['docker','run','--rm','--network','none',image,'cat','/jumpserve-image-packages.txt'],timeout=20)
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(files.items()):z.writestr(n,b)
 z.writestr('artifact-manifest.json',canonical([dict(path=n,bytes=len(b),sha256=digest(b)) for n,b in sorted(files.items())]))
raw=stream.getvalue();key='qualification/experiment-builder-v2/'+root.name+'/supplement/'+digest(raw)+'.zip';url='/storage/v1/object/research-workflow-raw/'+key
store.request(url,'POST',raw);assert store.request(url,raw=True)==raw
print(json.dumps(dict(bucket='research-workflow-raw',path=key,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw),public=False)))
""".replace('ROOT',repr(host))
                report['ssm']=command(source,'evidence',['set -a','. /etc/jumpserve-openclaw.env','set +a','runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)])
            elif a.mode=='record':
                evaluation=json.loads((source/'reviewed.json').read_bytes());archive=json.loads((source/'archive.json').read_bytes());raw=json.dumps(evaluation,sort_keys=True,separators=(',',':'));sha=r.sha(raw.encode());lit=r.admin.literal
                assert evaluation['prompt_id']==PROMPT and evaluation['status'] in ('passed','failed-substantive-review','failed-or-paused')
                key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'}
                origin='https://regphejnlvfpyokpniny.supabase.co/rest/v1/agent_prompt_evaluations'
                record=dict(prompt_version_id=PROMPT,outcome=evaluation['status'],report_raw=raw,report_sha256=sha,original_artifacts=evaluation.get('archives',archive),recorded_by='Primary Codex AI implementer; nonindependent, not human review')
                request=urllib.request.Request(origin+'?on_conflict=prompt_version_id,report_sha256',data=json.dumps(record).encode(),headers={**headers,'Prefer':'resolution=ignore-duplicates,return=minimal'},method='POST')
                with r.prior.guard.OPEN.open(request,timeout=60) as response:response.read(10000)
                request=urllib.request.Request(origin+'?prompt_version_id=eq.'+PROMPT+'&report_sha256=eq.'+sha+'&select=report_raw',headers=headers)
                with r.prior.guard.OPEN.open(request,timeout=60) as response:restored=json.loads(response.read(20000001))
                assert len(restored)==1 and r.sha(restored[0]['report_raw'].encode())==sha
                report.update(evaluation_sha256=sha,retrieved_sha256=sha,retained_prompt_records=len(evaluation.get('turns',[])),report_bytes=len(raw.encode()))
            elif a.mode=='collect-evidence':
                value=json.loads((source/'evidence-result.json').read_bytes());assert value['Status']=='Success'
                item=json.loads(value['StandardOutputContent']);assert item['path'].startswith('qualification/experiment-builder-v2/'+source.name+'/supplement/')
                raw=storage(item['path']);assert r.sha(raw)==item['sha256']==item['retrieved_sha256'];(source/'supplement.zip').write_bytes(raw)
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
                    control=json.loads(z.read('root-user-control.json'));assert control['status']=='passed' and control['live_provider_calls']==0
                    (source/'root-user-control.json').write_text(json.dumps(control,indent=2)+'\n')
                (source/'supplement-archive.json').write_text(json.dumps(item,indent=2)+'\n');report.update(archive=item,negative_control=dict(status=control['status'],control_user=control['control_user'],aligned_user=control['aligned_user'],meaning=control['meaning']))
            elif a.mode=='retain-image':
                assert not (source/'retain-image-command.json').exists()
                raw=(ROOT/'bin/retain_builder_image_host.py').read_bytes();install="from pathlib import Path;import base64;p=Path("+repr(host+'/retain-image.py')+");assert not p.exists();p.write_bytes(base64.b64decode("+repr(base64.b64encode(raw).decode())+"));p.chmod(0o644)"
                cmd='set -eu\nset -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host+'/retain-image.py'
                report['ssm']=command(source,'retain-image',['set -eu','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(install),cmd])
            elif a.mode=='collect-image':
                value=json.loads((source/'retain-image-result.json').read_bytes());assert value['Status']=='Success'
                item=json.loads(value['StandardOutputContent']);raw=storage(item['path']);assert r.sha(raw)==item['sha256']==item['retrieved_sha256'];manifest=json.loads(raw)
                assert manifest['image']==item['image'] and sum(c['bytes'] for c in manifest['chunks'])==manifest['compressed_bytes']
                (source/'image-manifest.json').write_bytes(raw);(source/'image-archive.json').write_text(json.dumps(item,indent=2)+'\n');report['image_archive']=item
        report['status']='complete'
    except Exception as error:report.update(status='failed',reason=str(error));raise
    finally:(audit/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(audit),**report),indent=2))
if __name__=='__main__':main()
