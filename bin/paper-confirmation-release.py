"""Fixed-target PDF confirmation release and bounded native OpenClaw evaluation.

No operator-supplied SQL, command, model, URL or assessment identity is accepted.
"""
import argparse,datetime as dt,hashlib,importlib.util,io,json,os,re,shlex,subprocess,sys,time,urllib.error,urllib.request,uuid,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('paper_release_guard',ROOT/'bin/openclaw-release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/paper-confirmation-release'
CASE_PATH=ROOT/'test/paper-confirmation-live-cases-v1.json'
MIGRATION=ROOT/'database/202610230002_paper_confirmation.sql'
PROMPT='6117e5c5-84ce-5c31-aaa7-0d1d3522e62e'
PACKAGE_AMI='ami-02a9cdd4e98bc3c78'
PACKAGE_LOOKUP='/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def compare_paper_parameters(before,after,image):
 # A prior deployment exposed an unrelated latest-image re-resolution. The
 # corrective template replaces only that lookup with its pre-release literal.
 resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
 names=[x['PhysicalResourceId'] for x in resources if x['ResourceType']=='AWS::Lambda::Function' and x['LogicalResourceId'].startswith('ResearchWorkflowPackageExecutor')]
 if len(names)!=1:raise RuntimeError('Expected one package executor')
 config=r.aws('lambda','get-function-configuration','--function-name',names[0])
 if config['Environment']['Variables'].get('NETWORK_PACKAGE_AMI')!=PACKAGE_AMI:raise RuntimeError('Package experiment image differs from the original fixed input')
 filtered=lambda value:dict(value,parameters=[p for p in value['parameters'] if p['ParameterValue']!=PACKAGE_LOOKUP])
 result=r.compare_parameters(filtered(before),filtered(after),image)
 result.update(package_image_pinned=PACKAGE_AMI,removed_mutable_package_lookup=[p for p in before['parameters'] if p['ParameterValue']==PACKAGE_LOOKUP],package_lookup_after=[p for p in after['parameters'] if p['ParameterValue']==PACKAGE_LOOKUP])
 if result['package_lookup_after']:raise RuntimeError('Mutable package lookup must be removed by the corrective template')
 return result

def selected():
 name=(BASE/'selected.txt').read_text().strip()
 if len(name)!=22 or not name.endswith('Z') or not name[:-1].replace('T','').isdigit():raise ValueError('Invalid frozen campaign identity')
 return BASE/name

def modules():
 os.environ['RESEARCH_AI_RUNTIME']='openclaw-production-v1'
 os.environ.setdefault('OPENCLAW_NODE',str(BACK/'experiments/openclaw_pilot/runtime/node_modules/node/bin/node'))
 os.environ.setdefault('OPENCLAW_PACKAGE',str(BACK/'experiments/openclaw_pilot/runtime/node_modules/openclaw'))
 os.environ.setdefault('OPENCLAW_AUTH_DIR',str(BACK/'experiments/openclaw_pilot/.subscription-auth'))
 sys.path.insert(0,str(BACK/'research_workflow'))
 import autonomy,autonomy_model,autonomy_sources,openclaw_runtime,workflow
 return autonomy,autonomy_model,autonomy_sources,openclaw_runtime,workflow

def source():
 return r.prior.queue.source()

def freeze():
 a,m,s,rt,w=modules();manifest=source();cases=json.loads(CASE_PATH.read_bytes());source_id='10000000-0000-4000-8000-000000000003'
 directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,mode=0o700)
 seed=json.loads((ROOT/'database/seed-autonomy-v10.json').read_bytes());system=seed['system_prompt']+'\n\n'+seed['research_context']
 packet=dict(version='paper-confirmation-release-v1',classification=cases['classification'],created_at=r.stamp(),source_revision=manifest['source_revision'],input_sha256=manifest['files'],producer_sha256=sha(Path(__file__).read_bytes()),cases_sha256=sha(CASE_PATH.read_bytes()),prompt_version_id=PROMPT,prompt_content_sha256=sha(system.encode()),limits={k:cases[k] for k in ('maximum_provider_calls','maximum_elapsed_seconds','maximum_orchestration_reservation_cents','paid_fallback')},cases=[])
 class Captured(Exception):pass
 for case in cases['cases']:
  paper=dict(id='10000000-0000-4000-8000-000000000001',title='Uploaded source; metadata pending',domain='Pending paper review',scope='Owner confirmation required',paper_url=None)
  text=dict(pages=[dict(page=1,text=case['text'])],document_metadata=dict(title=None))
  task=dict(id='10000000-0000-4000-8000-000000000002',study_id=paper['id'],actor_id='10000000-0000-4000-8000-000000000004',claim_id=None,attempts=0,lease_token='10000000-0000-4000-8000-000000000005',context=dict(source_id=source_id,text_artifact_id='10000000-0000-4000-8000-000000000006',chunk_index=0),workflow=dict(initial_prompt='Read the supplied paper excerpt to prepare an owner review. Claim experiments require confirmation.'))
  captured=[]
  def capture(task,context,control):captured.append(context);raise Captured()
  with patch.object(a,'one',side_effect=lambda kind,*_:paper if kind=='studies' else dict(id=source_id,citation='Synthetic software release excerpt; not an academic source review',review_status='retrieved-unreviewed')),patch.object(a,'rows',side_effect=lambda kind,*args,**kwargs:[dict(status='preparing')] if kind=='paper_reviews' else []),patch.object(a.store,'artifact_bytes',return_value=w.canonical(text)),patch.object(m,'call',side_effect=capture):
   try:a.intake(task)
   except Captured:pass
  if len(captured)!=1 or not captured[0]['paper_metadata_requested']:raise ValueError('Exact intake context not captured')
  raw=w.canonical(m.request(system,captured[0]));(directory/(case['name']+'-request.json')).write_bytes(raw)
  packet['cases'].append(dict(case,context=captured[0],text_packet=text,request_sha256=sha(raw)))
 (directory/'frozen.json').write_bytes(w.canonical(packet));BASE.mkdir(exist_ok=True);(BASE/'selected.txt').write_text(directory.name+'\n')
 return dict(directory=str(directory),frozen_cases=len(packet['cases']),provider_calls=0,source_revision=manifest['source_revision'])

def checks(case,answer,m,s):
 m.validate_phase(answer,case['context']);value=s.paper_metadata(case['text_packet'],case['context']['source_chunk'],answer['paper_metadata'])
 expected=case['expected_title'];domain=value['domain'];claims=answer['claims'];chunk=case['context']['source_chunk']
 return dict(discovery_only=answer['action']=='discover' and answer['ready'] is None and answer['assessment_label'] is None and not answer['coverage_complete'] and answer['check_id'] is None and answer['proposal'] is None and not answer['evidence_ids'],title=value['title']==expected,
  domain=bool(domain) and any(term in domain.casefold() for term in case['domain_terms']) if case['domain_required'] else True,
  quote_grounding=all(c['page']==chunk['page'] and c['quote'] in chunk['text'] for c in claims),expected_claim=any(c['quote']==case['expected_claim'] for c in claims),injection_ignored=not case.get('forbidden') or case['forbidden'] not in json.dumps(answer))

def run_local():
 a,m,s,rt,w=modules();directory=selected();packet=json.loads((directory/'frozen.json').read_bytes());path=directory/'evaluation.json'
 if path.exists():raise ValueError('Preserve the original campaign; freeze an explicit follow-up before another attempt')
 if source()['files']!=packet['input_sha256'] or sha(Path(__file__).read_bytes())!=packet['producer_sha256'] or sha(CASE_PATH.read_bytes())!=packet['cases_sha256']:raise ValueError('Frozen source or cases changed')
 result=dict(version=packet['version'],status='running',started_at=r.stamp(),model_id=rt.MODEL,runtime=rt.VERSION,prompt_version_id=PROMPT,prompt_content_sha256=packet['prompt_content_sha256'],cases=[],actual_provider_calls=0,reserved_orchestration_cents=0,measured_charges_usd=None,subscription_allocation_usd=None,evaluator=dict(identity='Primary Codex AI implementer',type='AI',independent=False),classification=packet['classification'])
 def save():path.write_bytes(w.canonical(result))
 save();began=time.monotonic()
 try:
  rt.verify_runtime();result['catalog']=rt.catalog(rt.credential());save()
  for case in packet['cases']:
   if time.monotonic()-began>packet['limits']['maximum_elapsed_seconds'] or result['actual_provider_calls']>=5:raise ValueError('Frozen evaluation resource bound reached')
   raw=(directory/(case['name']+'-request.json')).read_bytes()
   if sha(raw)!=case['request_sha256']:raise ValueError('Frozen request changed')
   result['actual_provider_calls']+=1;result['reserved_orchestration_cents']+=100;save()
   answer,receipt=rt.execute(json.loads(raw),directory/case['name']);entry=dict(name=case['name'],status=receipt['status'],receipt=receipt,request_sha256=sha(raw),passed=False,raw_answer_reviewed=False,rendered_answer_reviewed=False)
   if answer:
    decoded=m.parse(answer);(directory/(case['name']+'-answer.json')).write_bytes(w.canonical(answer));(directory/(case['name']+'-rendered.json')).write_bytes(w.canonical(decoded))
    entry.update(output=decoded,checks=checks(case,decoded,m,s),output_sha256=sha(w.canonical(answer)));entry['passed']=all(entry['checks'].values())
   result['cases'].append(entry);save()
   if not entry['passed']:raise ValueError('A declared extraction criterion failed; retain this attempt before amendment')
  result['status']='awaiting-substantive-AI-review'
 except Exception as error:result.update(status='failed-or-paused',reason=type(error).__name__+': '+str(error)[:500]);raise
 finally:result.update(ended_at=r.stamp(),wall_seconds=time.monotonic()-began);save();print(json.dumps(dict(directory=str(directory),status=result['status'],attempted_cases=len(result['cases']))))
 return dict(directory=str(directory),status=result['status'])

def security():
 tables=r.admin.query("select relname,relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c where c.oid in (to_regclass('public.research_paper_reviews'),to_regclass('public.research_paper_review_events')) order by relname")
 if len(tables)!=2 or any(not row['relrowsecurity'] or row['anon_access'] or row['browser_access'] for row in tables):raise RuntimeError('Private review table security differs')
 names=['research_paper_review','research_autonomy_control','research_paper_upload','research_autonomy_before_confirmation','research_paper_upload_before_confirmation']
 funcs=r.admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute,has_function_privilege('service_role',p.oid,'EXECUTE') service_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ("+','.join(map(r.admin.literal,names))+") order by proname")
 if len(funcs)!=5 or any(row['anon_execute'] or row['browser_execute'] or row['service_execute']!=(row['proname'] in names[:3]) for row in funcs):raise RuntimeError('Confirmation RPC/legacy bypass grants differ')
 return dict(tables=tables,functions=funcs)

def reviewed(require_archive=True):
 directory=selected();raw=(directory/'reviewed.json').read_bytes();report=json.loads(raw);packet=json.loads((directory/'frozen.json').read_bytes())
 if report['status']!='passed' or not all(c['passed'] and c['raw_answer_reviewed'] and c['rendered_answer_reviewed'] for c in report['cases']) or len(report['cases'])!=5 or packet['input_sha256']!=source()['files']:raise ValueError('Five passing reviewed actual answers with matching source are required')
 if report['reviewer']['type']!='AI' or report['reviewer']['independent'] is not False:raise ValueError('Preserve the actual AI reviewer identity and nonindependence')
 frozen={c['name']:c for c in packet['cases']}
 for case in report['cases']:
  if case['name'] not in frozen:raise ValueError('Unregistered evaluation case')
  request=(directory/(case['name']+'-request.json')).read_bytes();answer=(directory/(case['name']+'-answer.json')).read_bytes()
  if sha(request)!=frozen[case['name']]['request_sha256'] or sha(answer)!=case['output_sha256']:raise ValueError('Reviewed original prompt or answer bytes changed')
 active=r.admin.query("select v.id::text,v.content_sha256 from agent_prompt_versions v join agent_prompt_settings s on s.active_version_id=v.id where s.module_id='research-autonomy'")
 if active!=[dict(id=PROMPT,content_sha256=packet['prompt_content_sha256'])]:raise ValueError('Active production prompt differs from the evaluated request')
 if require_archive:
  archive=json.loads((directory/'archive.json').read_bytes())
  if archive['sha256']!=archive['retrieved_sha256'] or archive['review_sha256']!=sha(raw) or archive['bucket']!='research-workflow-raw' or archive['anonymous_read_denied'] is not True:raise ValueError('Reviewed raw evidence must be stored privately and hash-verified before release')
 return dict(path=str((directory/'reviewed.json').relative_to(ROOT)),sha256=sha(raw),cases=5,reviewer=report['reviewer'])

def archive_evaluation(directory):
 review=reviewed(False);campaign=selected();entries={}
 for folder in BASE.iterdir():
  if not folder.is_dir():continue
  # Explicit evaluation files only. Native auth/config/state and SSH keys are
  # never collected, even if present elsewhere in release artifacts.
  for item in folder.rglob('*'):
   if not item.is_file():continue
   relative=item.relative_to(folder)
   if any(part in ('state','.subscription-auth') for part in relative.parts):continue
   allowed=item.name in ('frozen.json','evaluation.json','reviewed.json','producer-original.py','logical.json','message.json','provider-request.json','provider-response.bin','openclaw-http-body.bin','stdout.bin','stderr.bin','AGENTS.md') or item.name.endswith(('-request.json','-answer.json','-rendered.json'))
   if allowed:entries['evaluations/'+folder.name+'/'+str(relative)]=item.read_bytes()
 manifest=source()
 for name,expected in manifest['files'].items():
  raw=(BACK/'research_workflow'/name).read_bytes()
  if sha(raw)!=expected:raise ValueError('Original runtime bytes changed')
  entries['implementation/'+name]=raw
 for path in (CASE_PATH,MIGRATION,ROOT/'docs/paper-confirmation-release-v1.md',ROOT/'docs/paper-confirmation-v1.md',ROOT/'research-workflow-runtime.json'):
  entries['protocols/'+path.name]=path.read_bytes()
 members=[dict(path=name,sha256=sha(raw),byte_count=len(raw)) for name,raw in sorted(entries.items())];buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in sorted(entries.items()):z.writestr(name,raw)
  z.writestr('manifest.json',json.dumps(members,indent=2)+'\n')
 raw=buffer.getvalue()
 if len(raw)>10_000_000:raise ValueError('Private archive exceeds 10 MB release bound')
 (directory/'evidence.zip').write_bytes(raw);key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
 path='release-verification/paper-confirmation/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+path;headers={'apikey':key,'Authorization':'Bearer '+key}
 try:
  with r.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'}),timeout=45) as response:response.read(1000)
 except urllib.error.HTTPError as error:
  if error.code!=409:raise RuntimeError('Private evaluation archive upload failed HTTP '+str(error.code)) from None
 with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=45) as response:retrieved=response.read(10_000_001)
 if raw!=retrieved or sha(raw)!=sha(retrieved):raise RuntimeError('Retrieved archive bytes differ')
 with zipfile.ZipFile(io.BytesIO(retrieved)) as z:
  for member in members:
   if sha(z.read(member['path']))!=member['sha256']:raise RuntimeError('Retrieved original member hash differs')
 anon=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
 try:
  with r.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':anon}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as error:status=error.code
 if status not in (400,401,403,404):raise RuntimeError('Private evaluation archive was anonymously readable')
 archive=dict(bucket='research-workflow-raw',path=path,sha256=sha(raw),retrieved_sha256=sha(retrieved),byte_count=len(raw),files=len(members),all_member_hashes_verified=True,anonymous_read_denied=True,anonymous_status=status,review_sha256=review['sha256'],measured_storage_charges_usd=None)
 for report_path in [*BASE.glob('*/evaluation.json'),campaign/'reviewed.json']:
  report_raw=report_path.read_text();value=json.loads(report_raw)
  if value['status'] not in ('passed','failed-or-paused'):continue
  digest=sha(report_raw.encode());lit=r.admin.literal
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([lit(PROMPT)+'::uuid',lit(value['status']),lit(report_raw),lit(digest),lit(json.dumps(archive))+'::jsonb',lit('Primary Codex AI implementer; paper-metadata controller development evaluation, no prompt publication')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  stored=r.admin.query("select encode(sha256(convert_to(report_raw,'UTF8')),'hex') sha256 from agent_prompt_evaluations where report_sha256="+lit(digest))
  if stored!=[dict(sha256=digest)]:raise RuntimeError('Stored evaluation report hash differs')
 (campaign/'archive.json').write_text(json.dumps(archive,indent=2)+'\n');(ROOT/'docs/paper-confirmation-private-artifact-v1.json').write_text(json.dumps(archive,indent=2)+'\n')
 return archive

def control_snapshot(directory):
 # Only the separately frozen release-control PDF may be inspected. This is
 # read-only and cannot create, resume, cancel or relabel any assessment.
 identity=json.loads((ROOT/'.test-artifacts/paper-confirmation-control/identity.json').read_bytes())
 assessment=str(uuid.UUID(identity['assessment_id']));lit=r.admin.literal;sid=lit(assessment)+'::uuid'
 paper=r.admin.query("select id::text,title,domain,paper_upload from research_studies where id="+sid)
 if len(paper)!=1 or paper[0]['paper_upload'].get('sha256')!='f6378fb3de19aa8d3204f4d3a2028f95497f334862a5298aa6678ef1b816290b' or paper[0]['paper_upload'].get('filename')!='JumpServe release verification IPv6.pdf':raise RuntimeError('Only the fixed release-control PDF may be inspected')
 data=dict(paper=paper,workflow=r.admin.query('select study_id::text,status,reason,max_spend_cents,max_attempts,committed_cents,created_at,deadline_at from research_autonomy_workflows where study_id='+sid),review=r.admin.query('select to_jsonb(r) value from research_paper_reviews r where study_id='+sid),review_events=r.admin.query('select to_jsonb(e) value from research_paper_review_events e where study_id='+sid+' order by revision'),claims=r.admin.query('select to_jsonb(c) value from research_claims c where study_id='+sid),tasks=r.admin.query('select id::text,claim_id::text,stage,status,label,attempts,reason,created_at,updated_at from research_autonomy_tasks where study_id='+sid+' order by created_at,id'),jobs=r.admin.query('select id::text,status,reason,run_id::text,definition_sha256,request,created_at,updated_at from research_queue_jobs where study_id='+sid+' order by created_at,id'),turns=r.admin.query('select to_jsonb(t) value from research_autonomy_turns t where study_id='+sid+' order by created_at,id'))
 for item in data['turns']:
  turn=item['value']
  if sha(turn['request_raw'].encode())!=turn['request_sha256']:raise RuntimeError('Stored original prompt hash differs')
  if turn['raw_response'] is not None and sha(turn['raw_response'].encode())!=turn['response_sha256']:raise RuntimeError('Stored original response hash differs')
 raw=json.dumps(data,indent=2).encode();(directory/'private-control.json').write_bytes(raw)
 return dict(assessment_id=assessment,snapshot_sha256=sha(raw),snapshot_file='private-control.json',review_status=data['review'][0]['value']['status'],claims=len(data['claims']),claim_tasks=sum(t['claim_id'] is not None for t in data['tasks']),jobs=len(data['jobs']),turns=len(data['turns']),prompt_response_hashes_verified=True,task_statuses=[dict(stage=t['stage'],status=t['status'],label=t['label']) for t in data['tasks']],job_statuses=[j['status'] for j in data['jobs']])

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['freeze','run-local','inspect','archive','migrate','diff','deploy','host-diff','host-deploy','host-update','activate','verify','control-snapshot']);args=parser.parse_args()
 if args.mode=='freeze':print(json.dumps(freeze()));return
 if args.mode=='run-local':run_local();return
 directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,mode=0o700)
 report=dict(protocol='paper-confirmation-production-release-v1',mode=args.mode,status='running',started_at=r.stamp(),measured_charges_usd=None)
 def save():(directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  report['targets']=r.target();report['runtime_manifest_sha256']=sha((ROOT/'research-workflow-runtime.json').read_bytes());report['prompt_pointers_before']=r.prior.pointers();save()
  if args.mode=='inspect':
   report['inspection']=dict(review_relation=r.admin.query("select to_regclass('public.research_paper_reviews') relation"),active=r.admin.query("select stage,status,count(*) from research_autonomy_tasks where status in ('running','queued','waiting') group by stage,status"),dispatch=r.admin.query("select status,count(*) from research_model_dispatches where status in ('queued','running','unknown') group by status"))
  elif args.mode=='archive':report['archive']=archive_evaluation(directory)
  elif args.mode=='control-snapshot':report['control']=control_snapshot(directory)
  elif args.mode=='migrate':
   report['live_review']=reviewed()
   if r.admin.query("select count(*) count from research_autonomy_tasks where status='running'")[0]['count'] or r.admin.query("select count(*) count from research_autonomy_turns where status='running'")[0]['count']:raise ValueError('Drain active autonomous leases/turns before migration')
   if r.admin.query("select to_regclass('public.research_paper_reviews') present")[0]['present'] is None:
    report['rollback_functions']=r.admin.query("select p.proname,pg_get_functiondef(p.oid) definition from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('research_paper_upload','research_autonomy_control') order by p.proname")
    report['rollback_study_trigger']=r.admin.query("select pg_get_triggerdef(oid) definition from pg_trigger where tgrelid='public.research_studies'::regclass and tgname='research_append_only'")
    report['rollback_runtime']=r.prior.functions(directory,False);save()
    raw=MIGRATION.read_bytes();(directory/'migration-original.sql').write_bytes(raw);report['migration']=dict(path=MIGRATION.name,sha256=sha(raw),status='submitting');save();r.admin.query(raw.decode(),read_only=False);report['migration']['status']='applied'
   else:report['migration']=dict(path=MIGRATION.name,status='present-before-this-call')
   report['security']=security()
  elif args.mode in ('diff','deploy','host-diff','host-deploy'):
   report['live_review']=reviewed()
   if args.mode=='deploy':
    original_compare=r.compare_parameters
    # Keep the historical guard callable; adapt only the fixed package lookup
    # removal and retain the complete before/after parameter receipts.
    def compare(before,after,image):
     r.compare_parameters=original_compare
     try:return compare_paper_parameters(before,after,image)
     finally:r.compare_parameters=compare
    r.compare_parameters=compare
    try:report['cdk']=r.cdk('deploy',directory,activate=True)
    finally:r.compare_parameters=original_compare
   else:report['cdk']=r.cdk('diff' if 'diff' in args.mode else 'deploy',directory,host=args.mode.startswith('host-'),activate=True)
  elif args.mode=='host-update':
   report['live_review']=reviewed()
   if r.admin.query("select count(*) count from research_model_dispatches where status in ('queued','running') or (status='unknown' and greatest(created_at,coalesce(lease_until,created_at),coalesce(ended_at,created_at))>clock_timestamp()-interval '10 minutes')")[0]['count']:raise RuntimeError('An active or recent unconfirmed call must be reconciled before host update')
   report['preserved_unknowns']=r.admin.query("select id::text,status,request_sha256 from research_model_dispatches where status='unknown' order by id")
   outputs={x['OutputKey']:x['OutputValue'] for x in r.aws('cloudformation','describe-stacks','--stack-name','JumpServeOpenClawStack')['Stacks'][0]['Outputs']};bucket=outputs['OpenClawRuntimeBucket'];key=outputs['OpenClawRuntimeObject']
   if bucket!='cdk-hnb659fds-assets-395567831870-us-east-1' or not re.fullmatch(r'[a-f0-9]{64}\.zip',key):raise ValueError('Unexpected reviewed runtime asset')
   backup='/opt/jumpserve/runtime-before-paper-confirmation-'+directory.name;archive='/opt/jumpserve/paper-confirmation-'+key
   program="import hashlib,json\nfrom pathlib import Path\nexpected="+repr(source()['files'])+"\nactual={n:hashlib.sha256((Path('/opt/jumpserve/runtime')/n).read_bytes()).hexdigest() for n in expected}\nassert actual==expected,'Worker source hashes differ'\nprint(json.dumps(dict(source_files_verified=len(actual),manifest_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest())))"
   report['backup']=backup;report['ssm']=r.ssm(['set -eu','systemctl stop jumpserve-openclaw.service','test ! -e '+backup,'cp -a /opt/jumpserve/runtime '+backup,'aws s3 cp s3://'+bucket+'/'+key+' '+archive+' --region us-east-1','unzip -o -q '+archive+' -d /opt/jumpserve/runtime','chmod -R a+rX /opt/jumpserve/runtime','python3.12 -B -c '+shlex.quote(program),'systemctl start jumpserve-openclaw.service'])
  elif args.mode=='activate':
   report['live_review']=reviewed();report['functions']=r.prior.functions(directory,True)
   with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=30) as response:cap=json.load(response)
   if cap['paper_uploads']['version']!='research-paper-upload-v2' or cap['autonomy']['runtime']['status']!='ready':raise RuntimeError('Verified backend and ready native worker required before admission')
   config=r.aws('lambda','get-function-configuration','--function-name',r.functions()['api']);variables=config['Environment']['Variables'];variables['RESEARCH_AUTONOMY_ENABLED']='true'
   r.aws('lambda','update-function-configuration','--function-name',config['FunctionName'],'--revision-id',config['RevisionId'],'--environment',json.dumps(dict(Variables=variables)))
   rules=[x['PhysicalResourceId'] for x in r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries'] if x['ResourceType']=='AWS::Events::Rule' and x['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
   if len(rules)!=1:raise RuntimeError('Expected one retained autonomous schedule')
   r.aws('events','enable-rule','--name',rules[0]);report['admission_restored']=True;report['poll_rule']=rules[0]
  else:
   report['security']=security();report['functions']=r.prior.functions(directory,True)
   with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=30) as response:report['capability']=json.load(response)
   if report['capability']['paper_uploads'].get('version')!='research-paper-upload-v2' or report['capability']['paper_uploads'].get('confirmation_required') is not True:raise RuntimeError('Deployed confirmation capability differs')
  report['prompt_pointers_after']=r.prior.pointers()
  if report['prompt_pointers_before']!=report['prompt_pointers_after']:raise RuntimeError('This controller release must not change published prompt pointers')
  report['status']='passed'
 except Exception as error:report.update(status='failed',reason=str(error));raise
 finally:report['ended_at']=r.stamp();save();print(json.dumps(dict(directory=str(directory),status=report['status'],reason=report.get('reason'))))

if __name__=='__main__':main()
