"""Retain this fixed release's evidence and retire only its qualification containers.

No inference, EC2 launches, prompt publication or assessment restarts occur here.
"""
import base64
import datetime as dt
import importlib.util
import io
import json
import pathlib
import shlex
import time
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'bin/openclaw-release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
CAMPAIGNS = ['20261027T190640638887Z', '20261027T191345373638Z',
             '20261027T192323207354Z', '20261027T193546166732Z',
             '20261027T195457951090Z']
BASE = ROOT / '.test-artifacts/experiment-builder-release'


def main():
    out = ROOT / '.test-artifacts/builder-release-final' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    report = dict(status='running', targets=r.target(), started_at=r.stamp(),
                  measured_charges_usd=None, subscription_allocation_usd=None)
    def save():
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    archives = {c: json.loads((BASE / c / 'archive.json').read_bytes()) for c in CAMPAIGNS}
    for c, a in archives.items():
        assert a['sha256'] == a['retrieved_sha256'] == r.sha((BASE / c / 'originals.zip').read_bytes())
    # Fixed inputs, exact original producer bytes, no auth/state/bridge files.
    program = '''import io,json,pathlib,subprocess,sys,uuid,zipfile
sys.path.insert(0,'/opt/jumpserve/runtime')
import experiment_builder as builder,store
from workflow import canonical,digest
expected=EXPECTED
files={};tasks=[];sources=[]
root=pathlib.Path('/var/lib/jumpserve-openclaw/builder-qualification')
for name,archive in expected.items():
 p=root/name
 assert subprocess.run(['systemctl','is-active','--quiet','jumpserve-builder-qualification-'+name.lower()+'.service']).returncode!=0
 assert json.loads((p/'archive.json').read_bytes())==archive
 frozen=json.loads((p/'frozen.json').read_bytes())
 assert digest((p/'producer.py').read_bytes())==frozen['producer_sha256']
 for leaf in ('producer.py','frozen.json','report.json','ledger.jsonl'):
  f=p/leaf
  if f.exists():files[name+'/'+leaf]=f.read_bytes()
 for task in sorted((p/'builder-workspaces').iterdir()):
  if task.is_symlink() or not task.is_dir():raise RuntimeError('Unexpected qualification directory')
  assert str(uuid.UUID(task.name))==task.name
  tasks.append(dict(campaign=name,task=task.name))
 sources.append(dict(campaign=name,producer_sha256=frozen['producer_sha256']))
image=pathlib.Path('/var/lib/jumpserve-builder-image')
for leaf in ('Dockerfile','base-digest.txt','image-id.txt','image.json','installed-packages.txt','base-pull.log','build.log'):
 f=image/leaf
 assert f.is_file() and not f.is_symlink() and f.stat().st_size<5000000
 files['image/'+leaf]=f.read_bytes()
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
 for name,raw in sorted(files.items()):z.writestr(name,raw)
 z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]))
raw=stream.getvalue();key='release-verification/experiment-builder/final-source-capsule/'+digest(raw)+'.zip'
url='/storage/v1/object/research-workflow-raw/'+key
try:store.request(url,'POST',raw)
except Exception:
 if store.request(url,raw=True)!=raw:raise
assert digest(store.request(url,raw=True))==digest(raw)
removed=[]
for task in tasks:
 ids=builder.container_action(task['task'],'remove')
 assert builder.container_action(task['task'],'stop')==[]
 removed.append(dict(**task,containers=ids))
print(json.dumps(dict(source_archive=dict(bucket='research-workflow-raw',path=key,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw),public=False),sources=sources,cleanup=removed,workspace_directories_preserved=True,dependency_wheel_original='Not independently retained; successful task container already retired. Exact wheel hash and pip output remain in original native tool evidence.',worker_active=subprocess.run(['systemctl','is-active','--quiet','jumpserve-openclaw.service']).returncode==0)))
'''.replace('EXPECTED', repr(archives))
    raw = program.encode()
    host = '/var/lib/jumpserve-openclaw/finalize-builder-' + r.sha(raw) + '.py'
    install = 'from pathlib import Path;import base64;p=Path(' + repr(host) + ');raw=base64.b64decode(' + repr(base64.b64encode(raw).decode()) + ');assert not p.exists() or p.read_bytes()==raw;p.write_bytes(raw);p.chmod(0o644)'
    command = 'set -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B ' + host
    call = r.ssm(['python3.12 -c ' + shlex.quote(install), command])
    report['ssm'] = call
    save()
    for _ in range(35):
        invocation = r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
        if invocation['Status'] not in ('Pending','InProgress','Delayed'):break
        time.sleep(2)
    (out / 'ssm-result.json').write_text(json.dumps(invocation,indent=2)+'\n')
    assert invocation['Status']=='Success', invocation['Status']
    report['host'] = json.loads(invocation['StandardOutputContent'])
    assert report['host']['worker_active']
    # Verify both worker runtime and restored admission, without exposing env secrets.
    report['lambda'] = []
    for kind, name in r.functions().items():
        config=r.aws('lambda','get-function-configuration','--function-name',name)
        env=config['Environment']['Variables']
        assert env['RESEARCH_AUTONOMY_ENABLED']=='true'
        assert env.get('RESEARCH_BUILDER_ENABLED','false')=='false'
        report['lambda'].append(dict(kind=kind,admission=True,builder_enabled=False,timeout=config['Timeout']))
    resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
    report['polling']=[]
    for item in resources:
        if item['ResourceType']=='AWS::Events::Rule' and item['LogicalResourceId'].startswith(('ResearchWorkflowAutonomyPoll','ResearchWorkflowQueuePoll')):
            state=r.aws('events','describe-rule','--name',item['PhysicalResourceId'])['State']
            assert state=='ENABLED'
            report['polling'].append(dict(logical_id=item['LogicalResourceId'],state=state))
    assert report['polling']
    report['prompts']=r.admin.query("select module_id,active_version_id from agent_prompt_settings where module_id in ('research-autonomy','research-experiment-builder') order by module_id")
    assert report['prompts']==[dict(module_id='research-autonomy',active_version_id='6117e5c5-84ce-5c31-aaa7-0d1d3522e62e'),dict(module_id='research-experiment-builder',active_version_id=None)]
    report['instances']=[]
    for p in sorted((ROOT/'.test-artifacts/experiment-builder-operational').glob('*/receipt.json')):
        value=json.loads(p.read_bytes())
        if value.get('instance',{}).get('id'):
            identity=value['instance']['id']
            reservations=r.aws('ec2','describe-instances','--instance-ids',identity)['Reservations']
            visible=[i for group in reservations for i in group['Instances']]
            state=visible[0]['State']['Name'] if visible else None
            # EC2 eventually removes terminated instances from describe results.
            # Absence is not a newly observed terminal-state timestamp.
            assert value['instance']['state']=='terminated' and state in (None,'terminated')
            report['instances'].append(dict(id=identity,current_state=state,
                current_lookup='returned' if visible else 'not-returned',
                recorded_state='terminated',case=value['case'],outcome=value['status']))
    assert len(report['instances'])==4
    report.update(status='complete',ended_at=r.stamp(),scientific_claims_assessed=0,
                  qualification_calls=55,operational_review_calls=10,
                  aggregate_reservation_bound_usd=85,publication_eligible=False)
    save()
    # Retrieve the host capsule on this separate client and check each member.
    key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
    headers={'apikey':key,'Authorization':'Bearer '+key}
    origin='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'
    capsule=report['host']['source_archive']
    request=urllib.request.Request(origin+capsule['path'],headers=headers)
    with r.prior.guard.OPEN.open(request,timeout=60) as response:raw=response.read(20000001)
    assert len(raw)<=20000000 and r.sha(raw)==capsule['sha256']
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
    (out/'original-source-capsule.zip').write_bytes(raw)
    files={}
    for path in sorted((ROOT/'docs').glob('experiment-*.json')):
        files[str(path.relative_to(ROOT))]=path.read_bytes()
    for leaf in ('experiment-builder.md','experiment-builder-release-2026-10-27.md'):
        files['docs/'+leaf]=(ROOT/'docs'/leaf).read_bytes()
    files['research-workflow-runtime.json']=(ROOT/'research-workflow-runtime.json').read_bytes()
    files['original-source-capsule.zip']=raw
    files['final-receipt.json']=(out/'receipt.json').read_bytes()
    for campaign in CAMPAIGNS:
        for leaf in ('archive.json','host-report.json','reviewed.json','frozen.json'):
            path=BASE/campaign/leaf
            if path.is_file():files['qualification/'+campaign+'/'+leaf]=path.read_bytes()
    for pattern in ('.test-artifacts/experiment-builder-operational/*/receipt.json',
                    '.test-artifacts/builder-production-browser/2026-10-27T19-25-04.601Z/report.json',
                    '.test-artifacts/builder-file-interface/20261027T203748410990Z/report.json',
                    '.test-artifacts/research-ideas/database/20261027T204038993805Z/autonomy-validation-report.json'):
        for path in ROOT.glob(pattern):files[str(path.relative_to(ROOT))]=path.read_bytes()
    manifest=[dict(path=n,sha256=r.sha(b),bytes=len(b)) for n,b in sorted(files.items())]
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):z.writestr(n,b)
        z.writestr('artifact-manifest.json',json.dumps(manifest,sort_keys=True))
    raw=stream.getvalue();object_path='release-verification/experiment-builder/final-release/'+r.sha(raw)+'.zip'
    request=urllib.request.Request(origin+object_path,data=raw,headers={**headers,'Content-Type':'application/zip'},method='POST')
    with r.prior.guard.OPEN.open(request,timeout=60) as response:response.read(10000)
    with r.prior.guard.OPEN.open(urllib.request.Request(origin+object_path,headers=headers),timeout=60) as response:restored=response.read(len(raw)+1)
    assert restored==raw
    (out/'release-evidence.zip').write_bytes(raw)
    report['release_archive']=dict(bucket='research-workflow-raw',path=object_path,
        sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),public=False)
    save()
    print(json.dumps(dict(directory=str(out),status=report['status'],host=report['host'],polling=report['polling'],instances=report['instances']),indent=2))


if __name__=='__main__':main()
