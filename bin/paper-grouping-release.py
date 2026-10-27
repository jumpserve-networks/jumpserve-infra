"""Guarded grouping-only release. No assessment creation, confirmation or restart."""
import argparse,base64,datetime as dt,hashlib,importlib.util,io,json,pathlib,re,shlex,subprocess,urllib.error,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
s=importlib.util.spec_from_file_location('grouping_release_prior',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/paper-grouping-release';EVAL=ROOT/'.test-artifacts/paper-grouping-release-evaluation';PROMPT='6117e5c5-84ce-5c31-aaa7-0d1d3522e62e'
sha=lambda b:hashlib.sha256(b).hexdigest()
def selected():
 name=(EVAL/'selected.txt').read_text().strip()
 if not re.fullmatch(r'[0-9]{8}T[0-9]{12}Z',name):raise ValueError('Invalid evaluation identity.')
 return EVAL/name
def security():
 tables=r.admin.query("select relname,relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c where c.oid in ('public.research_paper_reviews'::regclass,'public.research_paper_review_events'::regclass) order by relname")
 assert len(tables)==2 and all(t['relrowsecurity'] and not t['anon_access'] and not t['browser_access'] for t in tables)
 functions=r.admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_access,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_access,has_function_privilege('service_role',p.oid,'EXECUTE') service_access from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ('research_paper_review','research_paper_review_before_selection') order by proname")
 assert len(functions)==2 and all(not f['anon_access'] and not f['browser_access'] and f['service_access']==(f['proname']=='research_paper_review') for f in functions)
 return dict(tables=tables,functions=functions)
def gate(archived=True):
 path=selected();f=json.loads((path/'frozen.json').read_bytes());result=json.loads((path/'results.json').read_bytes());review=json.loads((path/'reviewed.json').read_bytes());manifest=r.prior.queue.source()
 assert review['status']=='passed' and review['reviewer']==dict(identity='Primary Codex AI implementer',type='AI',independent=False)
 assert review['results_sha256']==sha((path/'results.json').read_bytes()) and review['frozen_sha256']==sha((path/'frozen.json').read_bytes())
 assert len(result['cases'])==6 and all(c['passed'] for c in result['cases']) and result['cursor']==175 and len(result['calls'])<=32
 for n in ('paper_selection.py','autonomy_model.py','policies/paper-review-selection-policy-v2.json'):assert manifest['files'][n]==f['implementation_sha256'][n]
 assert r.admin.query("select v.id::text,v.content_sha256 from agent_prompt_versions v join agent_prompt_settings s on s.active_version_id=v.id where s.module_id='research-autonomy'")==[dict(id=PROMPT,content_sha256=f['system_sha256'])]
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip()
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision']
 if archived:
  a=json.loads((path/'archive.json').read_bytes());assert a['sha256']==a['retrieved_sha256'] and a['review_sha256']==sha((path/'reviewed.json').read_bytes()) and a['anonymous_read_denied']
 return dict(policy=f['policy']['version'],policy_sha256=f['policy_sha256'],review_sha256=sha((path/'reviewed.json').read_bytes()),source_revision=manifest['source_revision'])
def archive(directory):
 review=gate(False);campaign=selected();entries={}
 for name in ('frozen.json','results.json','reviewed.json','evaluator.py'):entries['evaluation/'+name]=(campaign/name).read_bytes()
 for call in campaign.glob('call-*'):
  for name in ('logical.json','provider-request.json','provider-response.bin','parsed.json','receipt.json','stdout.bin','stderr.bin'):
   if (call/name).is_file():entries['evaluation/'+call.name+'/'+name]=(call/name).read_bytes()
 manifest=r.prior.queue.source()
 for n in manifest['files']:entries['implementation/'+n]=(BACK/'research_workflow'/n).read_bytes()
 for n in ('database/202610240001_paper_review_selection.sql','test/paper-grouping-release-cases-v2.json','research-workflow-runtime.json'):entries['protocols/'+pathlib.Path(n).name]=(ROOT/n).read_bytes()
 members=[dict(path=k,sha256=sha(v),bytes=len(v)) for k,v in sorted(entries.items())];out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for k,v in sorted(entries.items()):z.writestr(k,v)
  z.writestr('manifest.json',json.dumps(members,indent=2)+'\n')
 raw=out.getvalue();assert len(raw)<10000000;(directory/'evidence.zip').write_bytes(raw)
 key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];path='release-verification/paper-grouping/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path;headers={'apikey':key,'Authorization':'Bearer '+key}
 try:
  with r.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=45) as response:response.read(1000)
 except urllib.error.HTTPError as error:
  if error.code!=409:raise RuntimeError('Private evidence upload failed HTTP '+str(error.code)) from None
 with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=45) as response:retrieved=response.read(10000001)
 assert retrieved==raw
 with zipfile.ZipFile(io.BytesIO(retrieved)) as z:
  for m in members:assert sha(z.read(m['path']))==m['sha256']
 anon=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
 try:
  with r.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':anon}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as error:status=error.code
 assert status in (400,401,403,404)
 info=dict(bucket='research-workflow-raw',path=path,sha256=sha(raw),retrieved_sha256=sha(retrieved),bytes=len(raw),files=len(members),anonymous_read_denied=True,review_sha256=review['review_sha256'],measured_storage_charges_usd=None)
 (campaign/'archive.json').write_text(json.dumps(info,indent=2)+'\n');(ROOT/'docs/paper-grouping-private-artifact-v2.json').write_text(json.dumps(info,indent=2)+'\n')
 text=(campaign/'reviewed.json').read_text();lit=r.admin.literal
 r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([lit(PROMPT)+'::uuid',lit('passed'),lit(text),lit(sha(text.encode())),lit(json.dumps(dict(info,kind='paper-grouping-controller-policy-v2',base_prompt_unchanged=True)))+'::jsonb',lit('Primary Codex AI implementer; nonindependent grouping policy release evaluation')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
 assert r.admin.query("select encode(sha256(convert_to(report_raw,'UTF8')),'hex') hash from agent_prompt_evaluations where report_sha256="+lit(sha(text.encode())))==[dict(hash=sha(text.encode()))]
 return info
def host_update(directory):
 assert r.admin.query("select count(*) n from research_model_dispatches where status in ('queued','running') or (status='unknown' and greatest(created_at,coalesce(lease_until,created_at),coalesce(ended_at,created_at))>clock_timestamp()-interval '10 minutes')")[0]['n']==0
 outputs={x['OutputKey']:x['OutputValue'] for x in r.aws('cloudformation','describe-stacks','--stack-name','JumpServeOpenClawStack')['Stacks'][0]['Outputs']};bucket=outputs['OpenClawRuntimeBucket'];key=outputs['OpenClawRuntimeObject']
 assert bucket=='cdk-hnb659fds-assets-395567831870-us-east-1' and re.fullmatch('[a-f0-9]{64}\\.zip',key)
 backup='/opt/jumpserve/runtime-before-grouping-'+directory.name;zip_path='/opt/jumpserve/grouping-'+key;expected=r.prior.queue.source()['files']
 program="from pathlib import Path\nimport hashlib,json\nexpected="+repr(expected)+"\nassert {n:hashlib.sha256((Path('/opt/jumpserve/runtime')/n).read_bytes()).hexdigest() for n in expected}==expected\nprint(json.dumps(dict(source_files_verified=len(expected))))"
 return dict(backup=backup,**r.ssm(['set -eu','systemctl stop jumpserve-openclaw.service','test ! -e '+backup,'cp -a /opt/jumpserve/runtime '+backup,'aws s3 cp s3://'+bucket+'/'+key+' '+zip_path+' --region us-east-1','unzip -o -q '+zip_path+' -d /opt/jumpserve/runtime','chmod -R a+rX /opt/jumpserve/runtime','python3.12 -B -c '+shlex.quote(program),'systemctl start jumpserve-openclaw.service']))
def host_smoke(directory):
 logical=(selected()/'call-1/logical.json').read_bytes();assert len(logical)<32000
 (directory/'host-smoke-request.json').write_bytes(logical)
 secret=r.aws('secretsmanager','describe-secret','--secret-id','jumpserve/supabase-service-key')['ARN'];assert secret.split(':')[4]=='395567831870'
 program="""import sys,json,base64,hashlib,io,zipfile
from pathlib import Path
sys.path.insert(0,'/opt/jumpserve/runtime')
import openclaw_runtime as rt,autonomy_model as model,paper_selection as selection,store
logical=json.loads(base64.b64decode(INPUT))
context=json.loads(logical['messages'][0]['content'][0]['text'])
rt.verify_runtime()
directory=Path('/var/lib/jumpserve-openclaw/grouping-release-checks')/RUN
answer,receipt=rt.execute(logical,directory)
if not answer:
 print(json.dumps(dict(status='failed',reason=receipt.get('error_code'),receipt=receipt)));raise SystemExit(2)
value=model.parse(answer);model.validate_phase(value,context)
chosen=selection.validate(value['paper_review_selection'],{c['id'] for c in context['candidates']})
labels={i['claim_id']:i['label'] for g in selection.GROUPS for i in chosen[g]}
rows=context['candidates'];assert set(labels)=={c['id'] for c in rows}
assert 'unprov' in labels[rows[1]['id']].lower() or 'proof' in labels[rows[1]['id']].lower()
assert any(t in labels[rows[2]['id']].lower() for t in ('target','derived','infer','impli','design'))
assert '16 KBps' in labels[rows[3]['id']]
data=io.BytesIO()
with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
 for n in ('logical.json','provider-request.json','provider-response.bin','receipt.json'):
  z.writestr(n,(directory/n).read_bytes())
 z.writestr('parsed.json',json.dumps(value,sort_keys=True))
raw=data.getvalue();digest=hashlib.sha256(raw).hexdigest();path='release-verification/paper-grouping/host/'+digest+'.zip'
store.request('/storage/v1/object/research-workflow-raw/'+path,method='POST',body=raw)
retrieved=store.request('/storage/v1/object/research-workflow-raw/'+path,raw=True)
assert retrieved==raw
print(json.dumps(dict(status='passed',model_id=rt.MODEL,runtime=rt.VERSION,source_revision=REVISION,request_sha256=hashlib.sha256((directory/'logical.json').read_bytes()).hexdigest(),usage=receipt.get('usage'),suggestions=chosen,archive=dict(bucket='research-workflow-raw',path=path,sha256=digest,bytes=len(raw),retrieved_hash_verified=True),no_assessment_created=True,paid_fallback=False)))
"""
 # Fixed, frozen synthetic release case; source content never selects code.
 program='INPUT='+repr(base64.b64encode(logical).decode())+'\nRUN='+repr(directory.name)+'\nREVISION='+repr(r.prior.queue.source()['source_revision'])+'\n'+program
 compile(program,'frozen-worker-smoke','exec')
 (directory/'host-smoke-program.py').write_text(program)
 command='runuser -u jumpserve -- env RESEARCH_AI_RUNTIME=openclaw-production-v1 SUPABASE_URL=https://regphejnlvfpyokpniny.supabase.co SUPABASE_SECRET_ARN='+shlex.quote(secret)+' /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)
 return r.ssm([command])
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','archive','migrate','diff','deploy','host-diff','host-deploy','host-update','host-smoke','host-result','activate','verify','final-verify','record-result']);p.add_argument('--command-id');args=p.parse_args();directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,mode=0o700)
 receipt=dict(version='paper-grouping-release-v1',mode=args.mode,started_at=r.stamp(),status='running',measured_charges_usd=None,authorization='Current explicit request to release the backend grouping update; frontend and authentication changes excluded.');save=lambda:(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');save()
 try:
  receipt['targets']=r.target();save()
  if args.mode=='inspect':receipt.update(functions=r.prior.functions(directory,False),state=r.prior.queue.state(),paper_count=r.admin.query("select count(*) n from research_studies where study_kind='paper'"))
  elif args.mode in ('diff','host-diff'):receipt['cdk']=r.cdk('diff',directory,host=args.mode=='host-diff',activate=False)
  else:
   receipt['evaluation']=gate(args.mode!='archive');save()
   if args.mode=='archive':receipt['archive']=archive(directory)
   elif args.mode=='migrate':
    assert r.admin.query("select count(*) n from research_autonomy_tasks where status='running'")[0]['n']==0
    exists=r.admin.query("select to_regprocedure('public.research_paper_review_before_selection(text,uuid,uuid,jsonb)') is not null present")[0]['present']
    if not exists:
     (directory/'rpc-before.json').write_text(json.dumps(r.admin.query("select pg_get_functiondef('public.research_paper_review(text,uuid,uuid,jsonb)'::regprocedure) definition"),indent=2)+'\n');raw=(ROOT/'database/202610240001_paper_review_selection.sql').read_bytes();(directory/'migration.sql').write_bytes(raw);r.admin.query(raw.decode(),read_only=False);receipt['migration']=dict(status='applied',sha256=sha(raw))
    else:receipt['migration']=dict(status='already-present')
    receipt['security']=security()
   elif args.mode in ('deploy','host-deploy'):receipt['cdk']=r.cdk('deploy',directory,host=args.mode=='host-deploy',activate=False)
   elif args.mode=='host-update':receipt['ssm']=host_update(directory)
   elif args.mode=='host-smoke':receipt['ssm']=host_smoke(directory)
   elif args.mode=='host-result':
    known=[json.loads(p.read_bytes()) for p in BASE.glob('*/receipt.json') if p.parent!=directory]
    parent=next((p for p in known if p['mode'] in ('host-update','host-smoke') and p.get('ssm',{}).get('command_id')==args.command_id),None)
    if parent is None:raise ValueError('Only this release helper\'s fixed administrative commands can be inspected.')
    result=r.aws('ssm','get-command-invocation','--command-id',args.command_id,'--instance-id',r.instance());receipt['command_status']=result['Status'];receipt['stdout']=result.get('StandardOutputContent','')[-12000:];receipt['stderr']=result.get('StandardErrorContent','')[-1000:]
    if result['Status']=='Failed':raise RuntimeError('The retained administrative worker command failed.')
    if result['Status']=='Success' and parent['mode']=='host-smoke':
     value=json.loads(receipt['stdout'].strip().splitlines()[-1]);assert value['status']=='passed' and value['source_revision']==r.prior.queue.source()['source_revision'];(selected()/'host-verification.json').write_text(json.dumps(value,indent=2)+'\n');receipt['host_verification']=value
   elif args.mode=='activate':
    verified=json.loads((selected()/'host-verification.json').read_bytes());assert verified['status']=='passed' and verified['source_revision']==r.prior.queue.source()['source_revision'];receipt['cdk']=r.cdk('deploy',directory,activate=True);receipt['admission_enabled']=True
   elif args.mode=='record-result':
    value=json.loads((selected()/'host-verification.json').read_bytes());a=value['archive'];key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/'+a['bucket']+'/'+a['path'];headers={'apikey':key,'Authorization':'Bearer '+key}
    with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=30) as response:raw=response.read(10000001)
    assert sha(raw)==a['sha256']
    with zipfile.ZipFile(io.BytesIO(raw)) as z:assert sha(z.read('logical.json'))==value['request_sha256']
    anon=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
    try:
     with r.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':anon}),timeout=20) as response:response.read(1)
    except urllib.error.HTTPError as error:status=error.code
    assert status in (400,401,403,404)
    report=dict(version='paper-grouping-production-model-check-v1',status='passed',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),judgment='Actual worker selection preserves proposed/unproved/observed/target/derived distinctions and 16 KBps units; no scientific validity or complete source review asserted.',evidence=value,anonymous_archive_read_denied=True,measured_charges_usd=None,subscription_allocation_usd=None);text=json.dumps(report,indent=2)+'\n';lit=r.admin.literal
    r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([lit(PROMPT)+'::uuid',lit('passed'),lit(text),lit(sha(text.encode())),lit(json.dumps(dict(a,kind='paper-grouping-production-model-check'))) + '::jsonb',lit('Primary Codex AI implementer; real deployed grouping inference, no assessment created')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
    assert r.admin.query("select encode(sha256(convert_to(report_raw,'UTF8')),'hex') hash from agent_prompt_evaluations where report_sha256="+lit(sha(text.encode())))==[dict(hash=sha(text.encode()))]
    receipt['production_model_report_sha256']=sha(text.encode());(ROOT/'docs/paper-grouping-production-model-check-v1.json').write_text(text)
   elif args.mode in ('verify','final-verify'):
    receipt['functions']=r.prior.functions(directory,True);receipt['security']=security()
    with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=30) as response:cap=json.load(response)
    assert cap['paper_uploads']['selection_version']=='paper-review-selection-v1';receipt['capability']=cap['paper_uploads'];receipt['autonomy_enabled']=cap['autonomy']['enabled']
    if args.mode=='final-verify':
     assert cap['autonomy']['enabled'] and cap['autonomy']['runtime']['status']=='ready'
     resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries'];rules=[x['PhysicalResourceId'] for x in resources if x['ResourceType']=='AWS::Events::Rule' and x['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')];assert len(rules)==1
     rule=r.aws('events','describe-rule','--name',rules[0]);assert rule['State']=='ENABLED';receipt['polling_enabled']=True
     status=200
     try:
      request=urllib.request.Request('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/paper-uploads',data=json.dumps(dict(action='organize',request_id='10000000-0000-4000-8000-000000000001')).encode(),headers={'Content-Type':'application/json'})
      with r.prior.guard.OPEN.open(request,timeout=20) as response:response.read(1000)
     except urllib.error.HTTPError as error:status=error.code
     assert status in (401,403);receipt['anonymous_organization_denied']=status
     with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/papers',timeout=20) as response:papers=json.load(response)
     receipt['public_paper_count']=papers['coverage']['papers'];receipt['host_verification']=json.loads((selected()/'host-verification.json').read_bytes())
  receipt['status']='passed'
 except Exception as error:receipt.update(status='failed',reason=type(error).__name__+': '+str(error)[:400]);raise
 finally:receipt['ended_at']=r.stamp();save();print(json.dumps(dict(directory=str(directory),status=receipt['status'],mode=args.mode)))
if __name__=='__main__':main()
