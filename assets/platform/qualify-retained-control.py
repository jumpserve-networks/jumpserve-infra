"""Qualify retained software bytes without inventing model readiness or replay.

This is a new source-verification record. The original six-call trial remains
failed when the model omitted its readiness file. Its frozen acceptance tests,
original calls and source are preserved and actually re-executed read-only.
"""
import argparse,datetime as dt,io,json,os,subprocess,sys,time,uuid
from pathlib import Path

CHECK='from calc import double\nassert double(7)==14\nassert double(0)==0\nassert double(None) is None\nprint("three controls passed")\n'
def verify_envelope(envelope,runs,stops):
 if len(runs)!=6 or any(r['status']!='complete' for r in runs):raise ValueError('Exactly six settled original responses required; unknown calls cannot qualify.')
 if envelope.get('error',{}).get('kind')!='incomplete_turn' or envelope.get('assistantTurns',0)<=len(runs) or envelope.get('toolSummary',{}).get('failures')!=0:raise ValueError('Definite local admission stop without failed tools required.')
 if not any(s.get('denied')=='budget' and s.get('provider_dispatched') is False for s in stops):raise ValueError('Retained pre-provider admission receipt required.')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--original-root',type=Path,required=True);parser.add_argument('--original-task',required=True);parser.add_argument('--task',required=True);args=parser.parse_args()
 root=args.root.resolve();old=args.original_root.resolve();sys.path.insert(0,str(root/'source'))
 from platform_supervisor import native
 from platform_supervisor.common import canonical,digest,identity,save,POLICY_SHA256
 from platform_supervisor.credentials import Credentials
 from platform_supervisor.store import Store,BUCKET
 def forbidden(*a,**kw):raise AssertionError('This qualification cannot invoke a provider.')
 native.runtime.http_request=forbidden;native.runtime.credential=forbidden
 class VerificationStore(Store):
  def rpc(self,operation,payload=None):
   if operation=='claim':payload=dict(payload or {},only_task=str(uuid.UUID(args.task)))
   if operation=='begin-run':raise AssertionError('Zero new provider calls required.')
   return super().rpc(operation,payload)
 credentials=Credentials();store=VerificationStore(credentials.supabase,root/'spool',str(uuid.uuid5(uuid.UUID(args.task),'retained-source-control')))
 for _ in range(20):
  store.rpc('heartbeat',dict(status='verifying',reason='Verifying retained implementation and six original responses; no provider transport enabled.'))
  task=store.rpc('claim',dict(policy_sha256=POLICY_SHA256))
  if task:break
  time.sleep(15)
 else:raise ValueError('Original work has priority; verification was not admitted.')
 assert task['id']==str(uuid.UUID(args.task)) and task['committed_cents']==0;store.task=task
 original=Store(credentials.supabase,old/'spool',str(uuid.uuid5(uuid.UUID(args.original_task),'cloud-control')));original.task=dict(id=args.original_task)
 report=dict(version='platform-retained-source-control-v1',passed=False,live=True,new_provider_calls=0,provider_transport_disabled=True,original_task_id=args.original_task,original_source_bundle=old.name,model_declared_ready=False,original_trial_passed=False,scientific_claim=False,independent_review=False)
 try:
  store.artifact('retained-source-control-prospective.json',canonical(report))
  old_report=json.loads((old/'report.json').read_bytes());assert old_report['passed'] is False and old_report['result']['ready'] is False
  ledger=original.request('/rest/v1/platform_tasks?id=eq.'+args.original_task+'&select=status,committed_cents')[0];assert ledger['status']=='blocked' and ledger['committed_cents']==600
  runs=original.rows('runs');artifacts={a['id']:a for a in original.rows('artifacts')}
  def read(artifact_id):
   record=artifacts[artifact_id];assert record['storage_path'].startswith(args.original_task+'/') and record['byte_count']<=5000000
   raw=original.request('/storage/v1/object/'+BUCKET+'/'+record['storage_path'],raw=True)
   assert len(raw)==record['byte_count'] and digest(raw)==record['sha256'];return raw
  captures=[]
  for run in runs:
   request=read(run['request_artifact_id']);assert digest(request)==run['request_sha256']
   response=read(run['response_artifact_id'])
   terminal=native.wire.read_stream(io.BytesIO(response),io.BytesIO(),time.monotonic()+10,5000000)
   native.builder.validate_calls(terminal)
   captures.append(dict(run_id=run['id'],request_sha256=digest(request),response_sha256=digest(response),terminal_verified=True))
  envelopes=[a for a in artifacts.values() if a['name']=='native-stdout-slice.json'];assert len(envelopes)==1
  envelope=json.loads(read(envelopes[0]['id']))
  stops=[json.loads(read(a['id'])) for a in artifacts.values() if a['name'].startswith('model-admission-stop-')]
  verify_envelope(envelope,runs,stops)
  def worker_files(path):return {p.name:digest(p.read_bytes()) for p in (path/'source/platform_supervisor').iterdir() if p.is_file() and p.suffix in ('.py','.json')}
  assert worker_files(root)==worker_files(old),'Original worker code must be identical.'
  image=json.loads((root/'image.json').read_bytes());assert image['image']==old_report['image'] and image['recipe_sha256']==old_report['recipe_sha256']==digest((root/'Dockerfile').read_bytes())
  native.containers(native.container_prefix(args.original_task),old/'workspace')
  workspace=old/'workspace';assert (workspace/'project/check.py').read_text()==CHECK
  before={p.name:digest(p.read_bytes()) for p in (workspace/'project').iterdir() if p.is_file()}
  result=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,source='+str(workspace)+',target=/workspace,readonly','--workdir','/workspace',image['image'],'python3','-B','project/check.py'],capture_output=True,timeout=30)
  stdout=store.artifact('retained-source-check-stdout.txt',result.stdout);store.artifact('retained-source-check-stderr.txt',result.stderr)
  assert result.returncode==0 and result.stdout.strip()==b'three controls passed'
  assert (workspace/'project/check.py').read_text()==CHECK and before=={p.name:digest(p.read_bytes()) for p in (workspace/'project').iterdir() if p.is_file()}
  report.update(passed=True,actual_provider_calls=6,maximum_actual_provider_calls=6,original_report_sha256=digest((old/'report.json').read_bytes()),original_calls=captures,worker_files_sha256=digest(canonical(worker_files(root))),image=image['image'],recipe_sha256=image['recipe_sha256'],existing_test_unchanged=True,container_check_passed=True,verification_stdout_artifact_id=stdout['id'],task_id=task['id'],bundle_sha256=root.name,scope='Retained source passes unchanged software acceptance controls; the original model trial did not declare readiness.',verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
  artifact=store.artifact('retained-source-control-verified.json',canonical(report));report['artifact_id']=artifact['id']
  proof=json.loads((root/'production-verification.json').read_bytes());assert proof['passed']
  store.rpc('release',dict(id=identity(task['id'],'bootstrap-frontend-verification'),component=proof['component'],repository=proof['repository'],revision=proof['revision'],status='verified',external_id=proof['operation_id'],verification=proof,details=dict(origin='Existing verified frontend; software verification performed no deployment.')))
  store.checkpoint('completed','Retained source passed the unchanged acceptance controls and six original terminal streams. Zero new model calls; original failed trial remains unchanged.',dict(retained_source_control=report))
 except Exception:
  store.checkpoint('blocked','Retained-source verification did not pass. Original trial and unknown-call fences remain unchanged; no model call was issued.',report)
  raise
 finally:save(root/'report.json',canonical(report))
 print(json.dumps(report))
if __name__=='__main__':main()
