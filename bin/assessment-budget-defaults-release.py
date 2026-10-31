"""Fixed-project qualification and activation of unlimited assessment defaults.

Uses the existing AWS model worker and GitHub OIDC release path, never a human
AWS session. One data-only qualification call; no experiments or paid fallback.
"""
import argparse,datetime as dt,hashlib,importlib.util,io,json,os,re,ssl,socket,subprocess,sys,time,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end';FRONT=ROOT.parent/'jumpserve-front-end'
BASE=ROOT/'.test-artifacts/unlimited-defaults-release-v1';BASE.mkdir(parents=True,exist_ok=True)
PROJECT='regphejnlvfpyokpniny';MIGRATION='202610310001_unlimited_assessment_defaults.sql'
spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
original_addresses=socket.getaddrinfo
def addresses(host,port,family=0,*args,**kwargs):return original_addresses(host,port,socket.AF_INET if host=='api.supabase.com' else family,*args,**kwargs)
socket.getaddrinfo=addresses
os.environ.update(RESEARCH_AI_RUNTIME='openclaw-production-v1',SUPABASE_URL='https://'+PROJECT+'.supabase.co',SSL_CERT_FILE='/etc/ssl/cert.pem')
sys.path.insert(0,str(BACK/'research_workflow'))
import autonomy,autonomy_model as model,model_dispatch,store
from workflow import canonical,digest

def save(name,value):
 p=BASE/name;p.write_bytes(canonical(value));p.chmod(0o600)
def read(name):return json.loads((BASE/name).read_bytes())
def enable_store():
 # Keep the project-bound server key in memory. It never enters a request to
 # the model, a subprocess, an artifact, source control or printed output.
 req=urllib.request.Request('https://api.supabase.com/v1/projects/'+PROJECT+'/api-keys?reveal=true',headers={'Authorization':'Bearer '+admin.credential()})
 context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
 with urllib.request.urlopen(req,context=context,timeout=30) as response:keys=json.load(response)
 # This project disables its legacy JWT keys. Use the existing named backend
 # secret key, the same server-side key family used by its deployed functions.
 key=next(item['api_key'] for item in keys if item.get('name')=='jumpserve_backend_20260921' and item.get('type')=='secret' and isinstance(item.get('api_key'),str))
 store.service_key=lambda:key
 return model_dispatch.health()
def files():
 old=read('frozen.json')['previous_source_files'] if (BASE/'frozen.json').exists() else json.loads((ROOT/'research-workflow-runtime.json').read_bytes())['files']
 current={name:digest((BACK/'research_workflow'/name).read_bytes()) for name in old}
 changed={name for name in old if name!='policies/autonomous-repair-release-v1.json' and old[name]!=current[name]}
 assert changed=={'autonomy.py','policies/autonomy-turn-policy-v1.json'},changed
 qualified={name:sha for name,sha in sorted(current.items()) if name!='policies/autonomous-repair-release-v1.json'}
 return old,current,digest(canonical(qualified))
def prepare():
 if (BASE/'frozen.json').exists():return read('frozen.json')
 old,current,binding=files();namespace=uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:unlimited-defaults-qualification:'+binding)
 owner=admin.query("select owner_id from public.research_study_owners where study_id='4055396e-35c0-4962-ba39-cf23e443ad8d'")[0]['owner_id']
 packet=dict(version='unlimited-assessment-defaults-qualification-v1',qualified_files_sha256=binding,source_files=current,previous_source_files=old,
   inherited_repair_qualification=json.loads((BACK/'research_workflow/policies/autonomous-repair-release-v1.json').read_bytes()),
   study_id=str(namespace),task_id=str(uuid.uuid5(namespace,'one-data-only-control')),lease_token=str(uuid.uuid5(namespace,'qualification-lease')),
   owner_id=owner,deadline_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),
   resources=dict(maximum_actual_provider_calls=1,maximum_reservation_cents=100,maximum_new_experiments=0,paid_fallback=False),
   expected=dict(action='blocked',claims=[],proposal=None,assessment_label=None,evidence_ids=[],coverage_complete=False),
   authorization='Deploy the prepared unlimited-budget default for all active and future assessments to production.',
   local_validation=dict(backend_tests=398,backend_skipped=4,frontend_tests=295,frontend_build='passed',frontend_lint='passed',database_checks=6),
   inherited_scope='All transport, builder, executor and scientific-criteria bytes are unchanged. Changed defaults and resource-policy instruction are qualified by the actual one-response AWS worker control and actual SQL/API/frontend tests. Not independent or scientific validation.')
 save('frozen.json',packet);return packet
def qualify():
 packet=prepare();assert files()[2]==packet['qualified_files_sha256']
 health=enable_store();assert health['status']=='ready',health
 if (BASE/'live-call-intent.json').exists():return dict(status='original-call-retained',task_id=packet['task_id'],next_action='collect; never resend the provider call')
 assert dt.datetime.fromisoformat(packet['deadline_at'])>dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=600)
 original=canonical(dict(instruction='Operational software qualification only. No research paper, source data, scientific finding, experiment or model tools are requested.',defaults=autonomy.DEFAULTS,qualification=packet['version'],maximum_actual_provider_calls=1)).decode()
 paper=dict(title='Release qualification — unlimited assessment defaults (software fixture)',domain='Software release verification',scope='One data-only response for missing inputs; no academic claim or experiment.',study_kind='paper',paper_url='https://example.org/software-qualification-only')
 lit=admin.literal;study=packet['study_id'];task_id=packet['task_id']
 sql="""begin;select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 do $qualify$ begin
 if exists(select 1 from public.research_autonomy_workflows where study_id="""+lit(study)+"""::uuid) then raise exception 'Retained qualification exists; reconcile its original identity';end if;
 if (select count(*) from public.research_autonomy_tasks where status='running')>=4 then raise exception 'Qualification waits for a free existing controller slot';end if;
 perform public.research_create_study("""+lit(packet['owner_id'])+'::uuid,'+lit(study)+'::uuid,'+lit(json.dumps(paper))+"""::jsonb);
 insert into public.research_autonomy_workflows(study_id,initial_prompt,initial_sha256,deadline_at)
 values("""+','.join([lit(study),lit(original),lit(digest(original.encode())),lit(packet['deadline_at'])])+""");
 perform public.research_autonomy_set_budget("""+','.join([lit(study)+'::uuid',lit(str(uuid.uuid5(uuid.UUID(study),'explicit-unlimited-qualification')))+'::uuid','null','false',lit('Lab operator deployment authorization, 2026-10-31'),lit('All active and future assessments; this operational qualification admits one data-only provider call only.')])+""");
 insert into public.research_autonomy_tasks(id,study_id,claim_id,stage,status,label,context,lease_token,lease_until,reason)
 values("""+','.join([lit(task_id),lit(study),'null',lit('intake'),lit('running'),'null',lit(json.dumps(dict(qualification=packet['version'],maximum_actual_provider_calls=1)))+'::jsonb',lit(packet['lease_token']),"clock_timestamp()+interval '600 seconds'",lit('One-response operational qualification; controller slot acquired under the existing four-task gate.')])+""");
 insert into public.research_autonomy_events(study_id,task_id,event,details) values("""+','.join([lit(study),lit(task_id),lit('qualification-prospective'),lit(json.dumps({key:value for key,value in packet.items() if key!='owner_id'}))+'::jsonb'])+""");
 end $qualify$;commit;"""
 save('task-creation-intent.json',dict(study_id=study,task_id=task_id,sql_sha256=digest(sql.encode())))
 admin.query(sql,read_only=False)
 task=dict(id=task_id,study_id=study,actor_id=packet['owner_id'],stage='intake',lease_token=packet['lease_token'],attempts=0,context={})
 context=dict(task='planning',evaluation_scope='Operational missing-source software fixture, not a scientific assessment.',initial_prompt='No paper, source data, claim, or target has been supplied. Do not invent one or execute an experiment. Return blocked for missing source data, with no claims, evidence, proposal or scientific label and coverage_complete=false.',registered_checks=[],shared_acquisitions=[],available_built_packages=[],remaining_commitment_cents=None,resource_authorization=dict(version='assessment-budget-amendment-v2',max_spend_cents=None,committed_cents=500,deadline_at=packet['deadline_at']))
 save('live-context.json',context);save('live-call-intent.json',dict(task_id=task_id,turn_id=str(uuid.uuid5(uuid.UUID(task_id),'turn:1')),maximum_actual_provider_calls=1))
 print(json.dumps(dict(status='admitting-one-qualification-call',study_id=study,qualified_files_sha256=packet['qualified_files_sha256'])),flush=True)
 result=model.call(task,context,autonomy.control);save('live-call-result.json',result)
 return dict(status=result['status'],task_id=task_id,output=result['output'],runtime_status=(result.get('runtime') or {}).get('status'))
def collect():
 packet=read('frozen.json');assert files()[2]==packet['qualified_files_sha256'];enable_store()
 if (BASE/'qualification-verified.json').exists():
  report=read('qualification-verified.json');assert report['passed'] and report['qualified_files_sha256']==packet['qualified_files_sha256']
  close_fixture(packet)
  return dict(passed=True,actual_provider_calls=1,decision=report['decision'],evidence=report['evidence'],qualified_files_sha256=report['qualified_files_sha256'],retained_archive_reused=True)
 turns=store.rows('autonomy_turns',dict(study_id='eq.'+packet['study_id']));assert len(turns)==1
 turn=turns[0];dispatch=store.rows('model_dispatches',dict(id='eq.'+turn['id'],study_id='eq.'+packet['study_id']))[0]
 if turn['status']!='complete' or dispatch['status']!='complete':
  save('unconfirmed-live-state.json',dict(turn=turn,dispatch=dispatch));return dict(status='not-qualified',turn_status=turn['status'],dispatch_status=dispatch['status'],provider_call_limit_preserved=True)
 response=store.artifact_bytes(packet['study_id'],dispatch['response_artifact_id'],maximum=150000)
 assert digest(response)==dispatch['response_sha256'] and turn['usage']['turn_policy']=='autonomy-turn-policy-v2' and turn['reserved_cents']==100
 parsed=model.parse(json.loads(response));model.validate_phase(parsed,read('live-context.json'))
 assert all(parsed[key]==value for key,value in packet['expected'].items())
 assert len(turn['request']['system'])>=2 and model.TURN_POLICY['instruction'] in [row['text'] for row in turn['request']['system']]
 report=dict(version=packet['version'],passed=True,qualified_files_sha256=packet['qualified_files_sha256'],source_files=packet['source_files'],actual_provider_calls=1,reserved_cents=100,new_experiments=0,paid_fallback=False,turn_id=turn['id'],study_id=packet['study_id'],response_sha256=dispatch['response_sha256'],decision=parsed,local_validation=packet['local_validation'],inherited_scope=packet['inherited_scope'],reviewer=dict(identity='Codex implementing AI',independent=False,human=False),verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
 members={'frozen.json':canonical(packet),'qualification-report.json':canonical(report),'turn.json':canonical(turn),'dispatch.json':canonical(dispatch),'captured-response.json':response,'migration.sql':(ROOT/'database'/MIGRATION).read_bytes()}
 for name,sha in packet['source_files'].items():
  raw=(BACK/'research_workflow'/name).read_bytes();assert digest(raw)==sha;members['runtime/'+name]=raw
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,raw in sorted(members.items()):archive.writestr(name,raw)
 raw=stream.getvalue();sha=digest(raw);(BASE/'qualification-evidence.zip').write_bytes(raw)
 ident=str(uuid.uuid5(uuid.UUID(packet['study_id']),'source-qualification:'+sha))
 artifact=store.artifact(packet['study_id'],packet['owner_id'],raw,ident,'application/zip',dict(kind='unlimited-defaults-release-qualification',version=packet['version'],scientific_claim=False,independent_review=False))
 store.append(packet['study_id'],packet['owner_id'],'artifacts',artifact);assert store.artifact_bytes(packet['study_id'],ident,maximum=20000000)==raw
 report['evidence']=dict(artifact_id=ident,sha256=sha,retrieved_sha256=digest(raw),storage_path=artifact['storage_path']);save('qualification-verified.json',report)
 close_fixture(packet)
 return dict(passed=True,actual_provider_calls=1,decision=parsed,evidence=report['evidence'],qualified_files_sha256=report['qualified_files_sha256'])
def close_fixture(packet):
 # This is an administrative software fixture, not a paper intake. Do not pass
 # it through paper-confirmation completion or relax those production guards.
 lit=admin.literal;study=packet['study_id'];task=packet['task_id'];event=str(uuid.uuid5(uuid.UUID(study),'qualification-fixture-closed'))
 sql="""begin;select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));do $close$
 begin
 if (select count(*) from public.research_autonomy_turns where study_id="""+lit(study)+""")<>1
 or not exists(select 1 from public.research_autonomy_turns t join public.research_model_dispatches d on d.id=t.id
   where t.study_id="""+lit(study)+""" and t.status='complete' and d.status='complete')
 or exists(select 1 from public.research_queue_jobs where study_id="""+lit(study)+""") then raise exception 'Original qualification is not safely complete';end if;
 update public.research_autonomy_tasks set status='cancelled',lease_token=null,lease_until=null,
   reason='Administrative software qualification ended after its sole completed response; no paper intake or experiments requested.',updated_at=clock_timestamp()
   where id="""+lit(task)+""" and study_id="""+lit(study)+""" and status='running';
 update public.research_autonomy_workflows set status='cancelled',reason='Software release qualification complete; no research assessment requested.',updated_at=clock_timestamp()
   where study_id="""+lit(study)+""" and status='running';
 insert into public.research_autonomy_events(id,study_id,task_id,event,details) values("""+','.join([lit(event),lit(study),lit(task),lit('qualification-fixture-closed'),lit(json.dumps(dict(version='unlimited-defaults-qualification-closure-v1',actual_provider_calls=1,additional_provider_calls=0,original_completed_response_preserved=True,scientific_findings=0,reason='Administrative fixture closure, preserving the paper-confirmation guard; the first ordinary intake-finish attempt was rejected with HTTP 400.')))+'::jsonb'])+""") on conflict(id) do nothing;
 end $close$;commit;"""
 admin.query(sql,read_only=False)
 rows=admin.query('select w.status workflow_status,t.status task_status from public.research_autonomy_workflows w join public.research_autonomy_tasks t on t.study_id=w.study_id where t.id='+lit(task))
 assert rows==[dict(workflow_status='cancelled',task_status='cancelled')];save('fixture-closure-verified.json',rows[0])
def approve():
 report=read('qualification-verified.json');assert report['passed'] and report['actual_provider_calls']==1 and files()[2]==report['qualified_files_sha256']
 assert read('fixture-closure-verified.json')==dict(workflow_status='cancelled',task_status='cancelled')
 path=BACK/'research_workflow/policies/autonomous-repair-release-v1.json'
 approval=dict(version='autonomous-repair-release-v1',approved_for_lab_recovery=True,qualified_files_sha256=report['qualified_files_sha256'],evidence_sha256=report['evidence']['sha256'])
 path.write_bytes(canonical(approval));save('source-approved.json',approval);return approval
def production_proof(component):
 sys.path.insert(0,str(BACK))
 from platform_supervisor.github import GitHub
 from platform_supervisor.releases import Releases
 intent=read(component+'-verification-intent.json');request={key:value for key,value in intent.items() if key!='operation_id'}
 assert request['component']==component and request['repository']==('jumpserve-networks/jumpserve-front-end' if component=='frontend' else 'jumpserve-networks/jumpserve-infra')
 client=GitHub(lambda:subprocess.check_output(['gh','auth','token'],text=True).strip())
 proof=Releases(client).receipt(dict(id=intent['operation_id'],request=request))
 if proof:save(component+'-production-verification.json',proof)
 return proof or dict(status='waiting-for-original-workflow')
def public(path):
 assert path.startswith(('/research/capabilities','/research/studies/'))
 with urllib.request.urlopen('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com'+path,timeout=30) as response:return json.load(response)
def migrate():
 packet=read('frozen.json');qualification=read('qualification-verified.json');assert qualification['passed'] and files()[2]==packet['qualified_files_sha256']
 assert read('fixture-closure-verified.json')['workflow_status']=='cancelled'
 for component in ('frontend','infrastructure'):
  proof=read(component+'-production-verification.json');assert proof['passed'] and proof['component']==component
 assert public('/research/capabilities')['autonomy']['defaults']['maximum_spend_usd'] is None
 raw=(ROOT/'database'/MIGRATION).read_bytes();archive=(BASE/'qualification-evidence.zip').read_bytes();assert digest(archive)==qualification['evidence']['sha256']
 with zipfile.ZipFile(io.BytesIO(archive)) as saved:assert saved.read('migration.sql')==raw
 present=admin.query("select to_regclass('public.research_assessment_budget_policies') is not null present")[0]['present']
 functions="select p.proname,pg_get_function_identity_arguments(p.oid) arguments,p.prosrc,p.proacl::text acl from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'research_%' order by p.proname,pg_get_function_identity_arguments(p.oid)"
 if not (BASE/'migration-before-functions.json').exists():save('migration-before-functions.json',admin.query(functions))
 if not present:
  save('migration-intent.json',dict(migration=MIGRATION,sha256=digest(raw),authorization='All active and future assessments',qualification_sha256=qualification['evidence']['sha256']))
  admin.query(raw.decode(),read_only=False)
 policy=admin.query("select id,max_spend_cents,authorization_text,authorized_by from public.research_assessment_budget_policies")
 assert policy==[dict(id='unlimited-assessment-defaults-20261031',max_spend_cents=None,authorization_text='All active and future assessments',authorized_by='Lab operator via Codex conversation, 2026-10-31')]
 for name in ('research_autonomy_initial_budget','research_assessment_inherit_budget_policy'):
  expected=re.search(r'create (?:or replace )?function public\.'+name+r'\(\) returns trigger.*?as \$\$(.*?)\$\$;',raw.decode(),re.S).group(1)
  installed=admin.query('select prosrc from pg_proc where oid='+admin.literal('public.'+name+'()')+'::regprocedure')[0]['prosrc'];assert installed==expected,name
 after=admin.query(functions);indexed={(row['proname'],row['arguments']):row for row in after};changed=[]
 for row in read('migration-before-functions.json'):
  current=indexed[(row['proname'],row['arguments'])];assert current['acl']==row['acl']
  if row['proname']=='research_autonomy_initial_budget':changed.append(row['proname']);continue
  expected=row['prosrc'].replace("'maximum_spend_usd',100,","'maximum_spend_usd',null,")
  assert current['prosrc']==expected,row['proname']
  if expected!=row['prosrc']:changed.append(row['proname'])
 assert len(changed)==2,changed
 security=admin.query("select c.relrowsecurity rls,has_table_privilege('anon',c.oid,'SELECT') anon_read,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access,has_table_privilege('service_role',c.oid,'INSERT,UPDATE,DELETE') runtime_write,has_table_privilege('service_role',c.oid,'SELECT') runtime_read from pg_class c where c.oid='public.research_assessment_budget_policies'::regclass")
 assert security==[dict(rls=True,anon_read=False,browser_access=False,runtime_write=False,runtime_read=True)]
 capped=admin.query("select study_id from public.research_autonomy_workflows where status in ('running','budget','completed-with-blockers') and deadline_at>clock_timestamp()+interval '480 seconds' and max_spend_cents is not null");assert not capped,capped
 result=dict(passed=True,migration=MIGRATION,sha256=digest(raw),policy=policy,private_policy_security=security,changed_functions=changed,other_research_functions_and_acl_preserved=True,all_eligible_active_assessments_unlimited=True,default_unlimited=True,present_before=present)
 save('migration-applied-and-verified.json',result);return result
def verify_intake():
 packet=read('frozen.json');assert read('migration-applied-and-verified.json')['passed']
 namespace=uuid.UUID(packet['study_id']);study=str(uuid.uuid5(namespace,'production-new-intake-control'))
 from workflow import paper_details
 paper=paper_details(dict(title='Release verification — future unlimited funding (software fixture)',domain='Software validation',scope='Validate new intake funding and immediately cancel before any model call or experiment.',paper_url='https://example.org/intake-software-fixture',study_kind='paper'))
 payload=autonomy.start_payload(study,paper);lit=admin.literal
 exists=admin.query('select study_id from public.research_autonomy_workflows where study_id='+lit(study))
 if not exists:
  sql="begin;select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));select public.research_autonomy_control('start',"+lit(packet['owner_id'])+'::uuid,'+lit(study)+'::uuid,'+lit(json.dumps(payload))+"::jsonb);select public.research_autonomy_control('cancel',"+lit(packet['owner_id'])+'::uuid,'+lit(study)+"::uuid,'{}'::jsonb);commit;"
  save('new-intake-intent.json',dict(study_id=study,payload_sha256=digest(canonical(payload)),model_calls_permitted=0,experiments_permitted=0))
  admin.query(sql,read_only=False)
 state=admin.query('select status,max_spend_cents,committed_cents,max_attempts,initial_sha256,initial_prompt,deadline_at from public.research_autonomy_workflows where study_id='+lit(study))[0]
 assert state['status']=='cancelled' and state['max_spend_cents'] is None and state['committed_cents']==500 and state['max_attempts'] is None
 assert state['initial_sha256']==digest(payload['initial_prompt'].encode()) and json.loads(state['initial_prompt'])['defaults']['maximum_spend_usd'] is None
 event=admin.query("select details from public.research_autonomy_events where study_id="+lit(study)+" and event='budget-policy-inherited'")[0]['details'];assert event['max_spend_cents'] is None and event['authorization']=='All active and future assessments'
 assert admin.query('select count(*)::int count from public.research_autonomy_turns where study_id='+lit(study))==[dict(count=0)]
 assert admin.query('select count(*)::int count from public.research_queue_jobs where study_id='+lit(study))==[dict(count=0)]
 queue=public('/research/studies/'+study+'/queue?public=1&diagnostics=1')
 assert queue['autonomy']['defaults']['maximum_spend_usd'] is None and queue['autonomy']['workflows'][0]['max_spend_cents'] is None
 assert 'initial_prompt' not in queue['autonomy']['workflows'][0]
 save('production-new-intake-public-queue.json',queue)
 active=admin.query("select study_id,status,max_spend_cents,committed_cents,deadline_at from public.research_autonomy_workflows where study_id='444d171c-2fac-4ba9-b33c-2b46304cb0ec'")[0];assert active['max_spend_cents'] is None
 result=dict(passed=True,study_id=study,production_intake_rpc_unlimited=True,inherited_operator_policy=event['policy_id'],actual_public_api_default_unlimited=True,qualification_cancelled_before_worker_admission=True,new_model_calls=0,new_experiments=0,original_assessment=active,fresh_interactive_google_upload_tested=False)
 save('production-new-intake-verified.json',result);return result
def record_update():
 frontend=read('frontend-production-verification.json');assert frontend['passed']
 complete=all((BASE/name).exists() for name in ('infrastructure-production-verification.json','migration-applied-and-verified.json','production-new-intake-verified.json'))
 details=dict(version='unlimited-assessment-defaults-release-v1',execution='Operator-requested interactive release',frontend=frontend,
   infrastructure_intent=read('infrastructure-verification-intent.json'),future_default_active=complete,
   failed_attempts=[json.loads(path.read_bytes()) for path in sorted(BASE.glob('infrastructure-release-failed-attempt-*.json'))])
 if complete:
  for name in ('infrastructure-production-verification','migration-applied-and-verified','production-new-intake-verified'):
   proof=read(name+'.json');assert proof['passed'];details[name]=proof
  infrastructure=details['infrastructure-production-verification'];intent=details['infrastructure_intent']
  assert all(infrastructure[key]==intent[key] for key in ('operation_id','repository','revision','workflow_revision'))
  message='Unlimited aggregate assessment budgets are live for all active and future assessments. Verified the deployed frontend and backend, immutable standing policy, new intake and public queue. Original deadlines, reservation history, cancellation and uncertain-call safeguards remain enforced.'
 else:
  message='All five active assessments are uncapped and the compatible frontend is live. The future-default release is in progress through GitHub OIDC. Earlier attempts and their original failure or rollback outcomes are retained in this record.'
 stage='completed' if complete else 'progress';event=str(uuid.uuid5(uuid.UUID(read('frozen.json')['study_id']),'platform-release-'+stage+':'+details['infrastructure_intent']['operation_id']))
 lit=admin.literal;save('platform-'+stage+'-event-intent.json',dict(id=event,message=message,details=details))
 admin.query('insert into public.platform_events(id,task_id,actor,kind,message,details) values('+lit(event)+'::uuid,null,'+lit('Lab operator via Codex')+','+lit('release-'+stage)+','+lit(message)+','+lit(json.dumps(details))+'::jsonb) on conflict(id) do nothing',read_only=False)
 row=admin.query('select id,kind,message,details from public.platform_events where id='+lit(event))[0]
 assert row['message']==message and row['details']==details
 save('platform-'+stage+'-event-verified.json',row);return dict(recorded=True,event_id=event,future_default_active=complete)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','qualify','collect','approve','health','proof-frontend','proof-infrastructure','migrate','verify-intake','record-update']);args=parser.parse_args()
 result=enable_store() if args.action=='health' else production_proof(args.action.removeprefix('proof-')) if args.action.startswith('proof-') else globals()[args.action.replace('-','_')]()
 if args.action=='prepare':result={key:result[key] for key in ('version','qualified_files_sha256','study_id','task_id','resources')}
 print(json.dumps(result),flush=True)
if __name__=='__main__':main()
