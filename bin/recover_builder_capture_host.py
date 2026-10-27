"""Recover one permission-failed qualification capture; no inference/code rerun."""
import datetime as dt,io,json,os,pathlib,sys,zipfile
sys.path.insert(0,'/opt/jumpserve/runtime')
import experiment_builder as builder,store
from workflow import canonical,digest
base=pathlib.Path('/var/lib/jumpserve-openclaw/builder-qualification/20261027T193546166732Z')
original_report=(base/'report.json').read_bytes();report=json.loads(original_report)
assert report['status']=='failed-or-paused' and report['live_provider_calls']==6 and not report['cases']
assert 'Permission denied' in report['reason']
frozen=json.loads((base/'frozen.json').read_bytes());assert digest((base/'producer.py').read_bytes())==frozen['producer_sha256']
events=[json.loads(line) for line in (base/'ledger.jsonl').read_bytes().splitlines()]
finished=[e for e in events if e['operation']=='finish'];assert len(finished)==6 and all(e['payload']['status']=='complete' for e in finished)
work=base/'builder-workspaces/608c8f25-6f2d-4ad6-b337-a34772286c61/workspace'
builder.container_action(work.parent.name,'stop')
normalization=builder.normalize_workspace(work,os.environ['OPENCLAW_BUILDER_IMAGE'])
(base/'capture-recovery-normalization.json').write_bytes(normalization)
assert (base/'report.json').read_bytes()==original_report
files={}
for p in base.rglob('*'):
 if p.is_symlink() or not p.is_file():continue
 parts=p.relative_to(base).parts
 if 'state' in parts or p.name=='config.json' or p.name=='run.log' or p.name=='archive.json':continue
 if 'workspace' in parts or 'retained' in parts or p.name in ('frozen.json','producer.py','report.json','ledger.jsonl','task.txt','logical.json','action-policy.json','receipt.json','stdout.bin','stderr.bin','capture-recovery-normalization.json') or p.name.startswith('native-request-') or p.name.startswith('call-'):
  files[str(p.relative_to(base))]=p.read_bytes()
stream=io.BytesIO()
manifest=[dict(path=n,sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())]
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(files.items()):z.writestr(n,b)
 z.writestr('artifact-manifest.json',canonical(manifest))
raw=stream.getvalue();key='release-verification/experiment-builder/'+base.name+'/capture-recovery/'+digest(raw)+'.zip';url='/storage/v1/object/research-workflow-raw/'+key
store.request(url,'POST',raw);assert digest(store.request(url,raw=True))==digest(raw)
archive=dict(bucket='research-workflow-raw',path=key,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw),public=False)
(base/'archive.json').write_bytes(canonical(archive))
entry=dict(name='new-implementation',set='development',passed=False,actual_answer_reviewed=False,recovered_from=base.name,original_receipt=json.loads((base/'new-implementation-slice-1/receipt.json').read_bytes()),
    capture_recovery=dict(kind='metadata-only correction and reanalysis',provider_calls_replayed=0,program_executions_replayed=0,bytes_unchanged=True,normalization_sha256=digest(normalization)),
    source_archive=archive,original_started_at=report['started_at'],files={str(p.relative_to(work)):dict(sha256=digest(p.read_bytes()),bytes=p.stat().st_size,archive_path=str(p.relative_to(base))) for p in work.rglob('*') if p.is_file()},
    provider_responses=[dict(path=n,sha256=digest(b)) for n,b in sorted(files.items()) if n.startswith('new-implementation-slice-1/call-') and n.endswith('-response.bin')])
(base/'recovered-entry.json').write_bytes(canonical(entry))
print(json.dumps(dict(archive=archive,recovered_entry=entry,original_report_sha256=digest(original_report),recovery_does_not_change_original_campaign_status=True)))
