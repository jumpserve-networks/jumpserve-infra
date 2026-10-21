"""Fixed production IPv6 release positive control: read-only inspection or bounded normal worker invocation."""
import argparse,datetime as dt,hashlib,importlib.util,io,json,subprocess,sys,time,urllib.error,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/autonomy-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
admin=release.admin;aws=release.aws;OPEN=release.guard.OPEN
URL='https://pure.mpg.de/pubman/item/item_3670144_1/component/file_3670145/main.pdf'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('status','advance','archive','campaign','cancel','resume-assessment'));p.add_argument('--study',required=True,type=uuid.UUID);a=p.parse_args();study=str(a.study)
 directory=ROOT/'.test-artifacts/autonomy-positive-control'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
 report=dict(protocol='autonomous-assessment-production-protocol-v1',amendment='autonomous-assessment-production-amendment-v7',mode=a.mode,study_id=study,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),status='running',measured_charges_usd=None)
 try:
  release.guard.target()
  studies=admin.query('select id,title,paper_url from research_studies where id='+admin.literal(study)+'::uuid')
  if len(studies)!=1 or not studies[0]['title'].startswith('Production autonomous release verification') or studies[0]['paper_url']!=URL:raise RuntimeError('Only the declared IPv6 release positive-control study is allowed')
  if a.mode=='cancel':
   admin.query("select research_autonomy_control('cancel',(select owner_id from research_study_owners where study_id="+admin.literal(study)+"::uuid),"+admin.literal(study)+"::uuid,'{}'::jsonb)",read_only=False)
   report['operator_cancellation']='Release operator stopped this private positive control after a demonstrated phase-contract failure. This is a service-admin action, not a fabricated browser-authenticated cancellation.'
  if a.mode=='resume-assessment':
   if study!='b7bc978d-9a6a-4fc8-97fd-179be9989d24':raise RuntimeError('Only the second declared control may receive this one-time recovery')
   release.functions(directory,True);release.reviewed()
   admin.query("""do $$ declare t public.research_autonomy_tasks; w public.research_autonomy_workflows; begin
    select * into strict w from public.research_autonomy_workflows where study_id='b7bc978d-9a6a-4fc8-97fd-179be9989d24' for update;
    select * into strict t from public.research_autonomy_tasks where study_id=w.study_id and stage='assessment' and status='blocked' and reason='Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.' for update;
    if w.status<>'completed-with-blockers' or w.deadline_at<=clock_timestamp()+interval '180 seconds' or t.attempts>=25 or exists(select 1 from public.research_autonomy_turns where task_id=t.id and (stage='assessment' or status in ('running','unknown','failed'))) or exists(select 1 from public.research_autonomy_events where study_id=w.study_id and event='lossless-evidence-recovery') then raise exception 'Recovery preconditions differ'; end if;
    if (select count(*) from public.research_runs where study_id=w.study_id and status='complete')<>1 or (select count(*) from public.research_measurements where study_id=w.study_id)<>192 then raise exception 'Retained evidence coverage differs'; end if;
    insert into public.research_autonomy_events(study_id,task_id,event,details) values(w.study_id,t.id,'lossless-evidence-recovery',jsonb_build_object('operator','Primary Codex AI implementer; service-admin recovery, not a browser user action','protocol','autonomous-assessment-production-amendment-v10','old_workflow_status',w.status,'old_task_status',t.status,'old_reason',t.reason,'old_attempts',t.attempts,'old_committed_cents',w.committed_cents,'experiment_restarted',false));
    update public.research_autonomy_workflows set status='running',reason='One-time transport correction; reassess the same retained run without resetting limits.',updated_at=clock_timestamp() where study_id=w.study_id;
    update public.research_autonomy_tasks set status='queued',next_at=clock_timestamp(),reason='Lossless evidence transport correction; same run, original conditions and original limits.',context=context||jsonb_build_object('last_response_error','A confirmed pre-dispatch context limit stopped assessment. All 192 original records are now provided losslessly. Reassess the same evidence under the original claim scope; do not repeat the experiment or force a conclusion.'),updated_at=clock_timestamp() where id=t.id;
   end $$""",read_only=False)
   report['operator_recovery']='Known pre-dispatch context block only; original attempts, budgets, deadlines and one recorded run retained.'
  if a.mode=='campaign':
   tick=time.monotonic();report['children']=[]
   for _ in range(30):
    if time.monotonic()-tick>1740:break
    time.sleep(15)
    call=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'advance','--study',study],cwd=ROOT,capture_output=True,text=True,timeout=120)
    receipts=[p for p in (ROOT/'.test-artifacts/autonomy-positive-control').glob('*/report.json') if p.parent!=directory and json.loads(p.read_bytes()).get('mode')=='advance' and json.loads(p.read_bytes()).get('study_id')==study]
    latest=max(receipts,key=lambda p:p.parent.name);child=json.loads(latest.read_bytes());report['children'].append(dict(path=str(latest.relative_to(ROOT)),sha256=sha(latest.read_bytes()),status=child['status']));(directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(operator_calls=len(report['children']),status=child['status'],turns=child.get('turn_count'),runs=child.get('runs'),assessments=child.get('assessments'),tasks=[dict(stage=t['stage'],status=t['status'],label=t['label']) for t in child.get('tasks',[])])),flush=True)
    if call.returncode or child['status']!='complete':raise RuntimeError('Bounded operator campaign stopped after a failed child; inspect retained receipt')
    if child.get('completed_assessment_turns',0)>0 and child.get('runs',0)>0 or child.get('workflow_status')!='running':break
   report['status']='complete';return
  if a.mode=='advance':
   receipts=[json.loads(p.read_bytes()) for p in (ROOT/'.test-artifacts/autonomy-positive-control').glob('*/report.json')]
   previous=[r for r in receipts if r['study_id']==study and r['mode']=='advance']
   if len(previous)>=30:raise RuntimeError('Thirty operator invocations already attempted')
   now=dt.datetime.now(dt.timezone.utc)
   if previous and (now-dt.datetime.fromisoformat(max(r['started_at'] for r in previous))).total_seconds()<15:raise RuntimeError('Operator cadence is too fast')
   if previous and (now-dt.datetime.fromisoformat(min(r['started_at'] for r in previous))).total_seconds()>1800:raise RuntimeError('Operator campaign wall limit exceeded')
   resources=aws('cloudformation','list-stack-resources','--stack-name',release.queue.STACK)['StackResourceSummaries'];functions=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Lambda::Function' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyWorker')]
   if len(functions)!=1:raise RuntimeError('Deployed worker identity differs')
   (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
   report['invocation']=aws('lambda','invoke','--function-name',functions[0],'--payload','{}','--cli-binary-format','raw-in-base64-out',str(directory/'worker-response.json'))
   if report['invocation'].get('FunctionError'):raise RuntimeError('Normal worker invocation returned a function error')
  tables=('autonomy_workflows','autonomy_tasks','autonomy_turns','autonomy_events','autonomy_job_commitments','prepared_plans','queue_jobs','runs','measurements','assessments','artifacts')
  if a.mode=='archive':tables+=('sources','claims','protocols','configurations','campaigns','claim_checks','published_values','summaries','gaps','reviews','publications')
  data={name:admin.query("select "+("to_jsonb(r)||jsonb_build_object('value',r.value::text)" if name in ('measurements','published_values') else 'to_jsonb(r)')+' record from research_'+name+' r where study_id='+admin.literal(study)+'::uuid') for name in tables}
  data={k:[r['record'] for r in v] for k,v in data.items()}
  raw=json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();snapshot=directory/'private-parsed-snapshot.json';snapshot.write_bytes(raw);snapshot.chmod(0o600);report['private_snapshot_sha256']=sha(raw)
  workflow=data['autonomy_workflows'][0]
  assert workflow['max_spend_cents']==10000 and workflow['max_attempts'] is None and workflow['committed_cents']<=10000
  assert sha(workflow['initial_prompt'].encode())==workflow['initial_sha256']
  for row in data['autonomy_turns']:
   assert sha(row['request_raw'].encode())==row['request_sha256'] and json.loads(row['request_raw'])==row['request']
   if row['raw_response'] is not None:assert sha(row['raw_response'].encode())==row['response_sha256']
  assert all(type(t['attempts']) is int and t['attempts']>=0 for t in data['autonomy_tasks'])
  report['autonomous_assessments']=sum(r.get('tested_conditions',{}).get('automatic_controller')=='research-autonomy-v1' for r in data['assessments'])
  report['completed_assessment_turns']=sum(r['stage']=='assessment' and r['status']=='complete' for r in data['autonomy_turns'])
  report.update(workflow_status=workflow['status'],committed_cents=workflow['committed_cents'],deadline_at=workflow['deadline_at'],task_count=len(data['autonomy_tasks']),claim_count=sum(r['claim_id'] is not None for r in data['autonomy_tasks']),turn_count=len(data['autonomy_turns']),turn_statuses={s:sum(r['status']==s for r in data['autonomy_turns']) for s in sorted({r['status'] for r in data['autonomy_turns']})},tasks=[dict(id=t['id'],stage=t['stage'],status=t['status'],label=t['label'],attempts=t['attempts'],reason=t['reason']) for t in data['autonomy_tasks']],jobs=[dict(id=j['id'],status=j['status'],run_id=j['run_id']) for j in data['queue_jobs']],runs=len(data['runs']),measurements=len(data['measurements']),assessments=len(data['assessments']),prompt_hashes_verified=True,provider_token_usage=[r['usage'].get('tokens') for r in data['autonomy_turns']],known_estimated_model_cents=sum(r['estimated_cents'] for r in data['autonomy_turns'] if r['estimated_cents'] is not None),missing_cost_count=sum(r['estimated_cents'] is None for r in data['autonomy_turns']))
  if a.mode=='archive':
   key=aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key};base='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'
   buffer=io.BytesIO();manifest=[]
   with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('private-parsed-snapshot.json',raw)
    for artifact in data['artifacts']:
     if artifact['byte_count']>8000000 or artifact['storage_path']!=study+'/'+artifact['sha256']:raise RuntimeError('Artifact identity or bound differs')
     with OPEN.open(urllib.request.Request(base+artifact['storage_path'],headers=headers),timeout=30) as response:original=response.read(8000001)
     assert len(original)==artifact['byte_count'] and sha(original)==artifact['sha256']
     z.writestr('artifacts/'+artifact['sha256'],original);manifest.append(dict(id=artifact['id'],sha256=sha(original),bytes=len(original),retrieved_hash_verified=True))
    for capture in sorted((ROOT/'.test-artifacts/autonomy-production-browser').glob('*.png')):
     image=capture.read_bytes()
     if len(image)>8000000:raise RuntimeError('Private browser capture exceeds declared bound')
     z.writestr('private-browser/'+capture.name,image);manifest.append(dict(kind='authenticated-browser-capture',name=capture.name,sha256=sha(image),bytes=len(image),privacy='May include user identity in sticky header; private only'))
    browser_report=ROOT/'.test-artifacts/autonomy-production-browser/browser-report.json'
    if browser_report.exists():z.writestr('private-browser/browser-report.json',browser_report.read_bytes())
    z.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
   archive=buffer.getvalue()
   if len(archive)>32000000:raise RuntimeError('Private positive-control archive exceeds bound')
   path='release-verification/autonomy-positive-control/'+study+'/'+sha(archive)+'.zip';url=base+path
   with OPEN.open(urllib.request.Request(url,data=archive,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=60) as response:response.read(1000)
   with OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:retrieved=response.read(32000001)
   assert retrieved==archive
   public=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
   try:
    with OPEN.open(urllib.request.Request(url,headers={'apikey':public}),timeout=20) as response:response.read(1)
   except urllib.error.HTTPError as error:status=error.code
   assert status in (400,401,403,404)
   report['private_archive']=dict(bucket='research-workflow-raw',path=path,sha256=sha(archive),bytes=len(archive),download_hash_verified=True,anonymous_status=status,artifacts=manifest)
  report['status']='complete'
 except Exception as error:report.update(status='failed',reason=str(error));raise
 finally:
  report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();(directory/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('private_snapshot_sha256','tasks','provider_token_usage')},indent=2))
if __name__=='__main__':main()
