"""Fixed-target PDF confirmation release and bounded native OpenClaw evaluation.

No operator-supplied SQL, command, model, URL or assessment identity is accepted.
"""
import argparse,datetime as dt,hashlib,importlib.util,io,json,os,subprocess,sys,time,uuid,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('paper_release_guard',ROOT/'bin/openclaw-release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/paper-confirmation-release'
CASE_PATH=ROOT/'test/paper-confirmation-live-cases-v1.json'
MIGRATION=ROOT/'database/202610230002_paper_confirmation.sql'
PROMPT='6117e5c5-84ce-5c31-aaa7-0d1d3522e62e'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

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

def reviewed():
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
 return dict(path=str((directory/'reviewed.json').relative_to(ROOT)),sha256=sha(raw),cases=5,reviewer=report['reviewer'])

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['freeze','run-local','inspect','migrate','diff','deploy','host-diff','host-deploy','verify']);args=parser.parse_args()
 if args.mode=='freeze':print(json.dumps(freeze()));return
 if args.mode=='run-local':run_local();return
 directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,mode=0o700)
 report=dict(protocol='paper-confirmation-production-release-v1',mode=args.mode,status='running',started_at=r.stamp(),measured_charges_usd=None)
 def save():(directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  report['targets']=r.target();report['runtime_manifest_sha256']=sha((ROOT/'research-workflow-runtime.json').read_bytes());report['prompt_pointers_before']=r.prior.pointers();save()
  if args.mode=='inspect':
   report['inspection']=dict(review_relation=r.admin.query("select to_regclass('public.research_paper_reviews') relation"),active=r.admin.query("select stage,status,count(*) from research_autonomy_tasks where status in ('running','queued','waiting') group by stage,status"),dispatch=r.admin.query("select status,count(*) from research_model_dispatches where status in ('queued','running','unknown') group by status"))
  elif args.mode=='migrate':
   report['live_review']=reviewed()
   if r.admin.query("select count(*) count from research_autonomy_tasks where status='running'")[0]['count'] or r.admin.query("select count(*) count from research_autonomy_turns where status='running'")[0]['count']:raise ValueError('Drain active autonomous leases/turns before migration')
   if r.admin.query("select to_regclass('public.research_paper_reviews') present")[0]['present'] is None:
    raw=MIGRATION.read_bytes();(directory/'migration-original.sql').write_bytes(raw);report['migration']=dict(path=MIGRATION.name,sha256=sha(raw),status='submitting');save();r.admin.query(raw.decode(),read_only=False);report['migration']['status']='applied'
   else:report['migration']=dict(path=MIGRATION.name,status='present-before-this-call')
   report['security']=security()
  elif args.mode in ('diff','deploy','host-diff','host-deploy'):
   report['live_review']=reviewed();report['cdk']=r.cdk('diff' if 'diff' in args.mode else 'deploy',directory,host=args.mode.startswith('host-'),activate=True)
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
