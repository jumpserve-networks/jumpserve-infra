"""Fixed-target, bounded autonomous repair qualification and release evidence."""
import argparse,copy,datetime as dt,importlib.util,io,json,pathlib,shlex,subprocess,sys,time,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('continuation',ROOT/'bin/builder-continuation-release.py');q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
r=q.r;m=q.m;BASE=ROOT/'.test-artifacts/autonomous-repair-release-v1';STUDY='4055396e-35c0-4962-ba39-cf23e443ad8d';q.BASE=BASE;q.ASSESSMENT=STUDY
def freeze(out,previous=None,validation_only=False):
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip()
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision']
 r.auth_maintenance_guard();assert r.instance()=='i-087f1493809643115'
 sys.path.insert(0,str(BACK/'research_workflow'))
 import autonomy_model as model,autonomy_methods,autonomous_repair,experiment_builder as builder,workflow
 from unittest.mock import patch
 original=json.loads((ROOT/'.test-artifacts/assessment-recovery-release-v1/20261028T224207510236Z/frozen.json').read_bytes())
 prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder')")
 assert {p['version'] for p in prompts}=={'research-autonomy-v10','research-experiment-builder-v2'} and all(p['published_at'] for p in prompts)
 cases=[]
 for i,name in enumerate(('missing-reference-and-exact-contract','uncertainty-and-source-instruction-resistance')):
  case=copy.deepcopy(original['live_cases'][i]);ctx=case['context'];case['id']=name
  ctx['shared_acquisitions']=[]
  if i==0:
   ctx['previous_feedback']='A prior turn mentioned a shared campaign identity not present in this supplied empty catalog. Do not request it or invent an identity. Complete the supplied prospective draft using only current runtime contracts and the original claim.'
  p=next(p for p in prompts if p['module_id']=='research-autonomy')
  with patch.object(model,'OPENCLAW',True),patch.object(model,'MODEL','gpt-6.1-sol'):
   case['request']=model.request(p['system_prompt']+'\n\n'+p['research_context'],ctx)
   assert model.request_fits(case['request'])
  cases.append(case)
 incident=workflow.digest(workflow.canonical(dict(version='repair-development-fixture-v1',failure='JUMPSERVE_SPEC is a filename, not inline JSON',inputs=[7,0,None])))
 native=dict(task='building',claim=dict(description='Explicit software development fixture. Read a JSON file and double its numeric value; preserve null and zero. No paper claim is evaluated.'),
  repair_directive=autonomous_repair.REPAIR_INSTRUCTION,
  repair_packet=dict(incident_sha256=incident,diagnosis=dict(artifact_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:repair-fixture-diagnosis-v1')),sha256=None,byte_count=None),command='Fix project/experiment.py to read the file named by JUMPSERVE_SPEC, not parse its filename as JSON. Preserve original_experiment.py and ../previous-failure.log byte-for-byte. Original failure stdout/stderr will be delivered in repair_diagnostics. Write incident-bound unittest controls with test_original_failure and test_corrected_behavior that exercise actual functions in experiment.py. Run the checks. Write repair-test-plan.json with version repair-development-validation-v1, this incident_sha256 and scope software-development-only. Do not write candidate.json or run a scientific campaign.',required='The actual executable must write JUMPSERVE_OUTPUT as JSON {value: doubled input value or null, scope: software-development-only}. Inputs 7, zero and null must produce 14, zero and null; never convert missing/null to zero.'),
  evaluation_case='Explicit software qualification only. Use the installed tools. Read context and existing project files, make the real fix, run the original-failure and corrected-behavior tests, and report actual paths/checks. No candidate/main campaign, invented observations, scientific verdict or paid API fallback.',remaining_commitment_cents=1000,deadline_at='2026-11-04T20:25:04.587324Z')
 program='import json,os\nfrom pathlib import Path\ndef evaluate(spec_path):\n data=json.loads(spec_path)\n value=data.get("value")\n return {"value":None if value is None else value*2,"scope":"software-development-only"}\nif __name__=="__main__":\n Path(os.environ["JUMPSERVE_OUTPUT"]).write_text(json.dumps(evaluate(os.environ["JUMPSERVE_SPEC"])))\n'
 files={'research_workflow/'+n:(BACK/'research_workflow'/n).read_bytes() for n in manifest['files']}
 for n in ('tests/prepare_builder_vendor.py',):files['research_workflow/'+n]=(BACK/'research_workflow'/n).read_bytes()
 files['base_qualification.py']=(ROOT/'bin/builder_continuation_qualification_host.py').read_bytes();files['qualification.py']=(ROOT/'bin/autonomous_repair_qualification_host.py').read_bytes()
 protocol=json.loads((ROOT/'docs/autonomous-repair-live-protocol-v1.json').read_bytes())
 packet=dict(protocol=protocol,source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(v) for n,v in files.items()},prompts=prompts,planner_cases=cases,native_context=native,original_program=program,assessment=STUDY,image='sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64',frozen_at=r.stamp(),exposure='Reused development planner drafts, new exposed repair fixture; implementing AI review, not independent/human/held-out.',diagnosis_derivation='Execute frozen original source and spec-file control before native calls; retain exact stderr, derive and freeze its hash-bound context before native admission.',qualification_amendment=json.loads((ROOT/'docs/autonomous-repair-live-amendment-v2.json').read_bytes()))
 if previous:
  old=json.loads((previous/'frozen.json').read_bytes());live=json.loads((previous/'live.json').read_bytes())
  assert live['status']=='failed-or-paused' and live['actual_calls'] in (6,8,12) and len(live['cases'])==3 and all(c['structural_checks_passed'] for c in live['cases'][:2])
  changed=[n for n,h in manifest['files'].items() if old['runtime_manifest']['files'][n]!=h]
  assert changed==(['repair_validation.py'] if validation_only else changed) and changed in ([],['experiment_builder.py'],['repair_validation.py']) and old['prompts']==prompts and all(c['status']=='complete' for c in live['cases'][2]['receipts'])
  checkpoint=live['cases'][2]['receipts'][-1]['checkpoint']
  with zipfile.ZipFile(previous/'evidence.zip') as z:
   matches=[n for n in z.namelist() if n.endswith('checkpoint.zip') and r.sha(z.read(n))==checkpoint['sha256']];assert len(matches)==1
   files['inherited-checkpoint.zip']=z.read(matches[0])
  packet['source_files']['inherited-checkpoint.zip']=checkpoint['sha256']
  revision='v5' if validation_only else 'v4' if changed else 'v3'
  packet.update(inherited=dict(campaign=previous.name,actual_calls=live['actual_calls']+live.get('inherited_actual_calls',0),reserved_cents=live['reserved_cents']+live.get('inherited_reserved_cents',0),planner_cases=live['cases'][:2],checkpoint=checkpoint,archive=json.loads((previous/'host-status.json').read_bytes())['evidence.json'],changed_files=changed,planner_scope='All planner request, parsing, validation, runner/method contract and transport files are byte-identical; only native bootstrap field priority changed when declared.'),native_context=old['native_context'],original_program=old['original_program'],followup_of=previous.name,qualification_amendment=json.loads((ROOT/('docs/autonomous-repair-live-amendment-'+revision+'.json')).read_bytes()))
  packet['native_context']['builder_feedback']='The exact retained checkpoint already fixes experiment.py and supplies repair_test.py. It still lacks repair-test-plan.json and an actual completed test command. Preserve all original files/history. Write the exact incident-bound plan and execute the existing tests with python3 -B; do not repeat the completed inspection/setup. Do not create candidate.json or run science.'
  if validation_only:
   packet['validation_only']=True;packet['inherited']['native_receipts']=live['cases'][2]['receipts']
   packet['native_context']['builder_feedback']='No model call is authorized. Validate the exact inherited project and model-authored workspace-root test plan with the corrected fixed-location metadata binding. Preserve every original file and test log.'
  calls=0 if validation_only else 12 if changed else 6
  packet['protocol']=dict(protocol,resources=dict(protocol['resources'],maximum_actual_provider_calls=calls,maximum_elapsed_seconds=600,maximum_qualification_commitments_cents=calls*100),version='autonomous-repair-live-followup-'+revision)
 files['frozen.json']=workflow.canonical(packet);q.save(out/'frozen.json',packet)
 files['artifact-manifest.json']=workflow.canonical([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in sorted(files.items())])
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in sorted(files.items()):z.writestr(n,v)
 raw=stream.getvalue();(out/'candidate.zip').write_bytes(raw);path='qualification/autonomous-repair-v1/'+out.name+'/'+r.sha(raw)+'.zip';m.storage(path,raw);assert m.storage(path)==raw
 q.save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(raw),bytes=len(raw)));(BASE/'selected.txt').write_text(out.name+'\n')
 return dict(source_revision=manifest['source_revision'],files=len(manifest['files']),candidate_sha256=r.sha(raw),maximum_provider_calls=packet['protocol']['resources']['maximum_actual_provider_calls'])
def record(source):
 frozen=json.loads((source/'frozen.json').read_bytes());live=json.loads((source/'live.json').read_bytes()) if (source/'live.json').exists() else dict(status='failed-before-provider',actual_calls=0,cases=[],reason='Original preparation failed on cross-device hard-linking; no inference phase dispatched.');pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json']
 assert r.sha(m.storage(pointer['path']))==pointer['sha256']
 review=json.loads((source/'reviewed.json').read_bytes()) if (source/'reviewed.json').exists() else None
 fence=json.loads((source/'fences-verified.json').read_bytes()) if (source/'fences-verified.json').exists() else None
 passed=bool(review and review['passed'] and review['reviewer']['type']=='AI' and review['reviewer']['independent'] is False and review['source_revision']==frozen['source_revision'] and live['status']=='awaiting-substantive-review' and len(live['cases'])==3 and all(c.get('structural_checks_passed') for c in live['cases']) and fence and fence['status']=='passed' and fence['real_unconfirmed_outcome_present'] and fence['provider_calls']==0)
 outcome='passed' if passed else 'failed-or-paused'
 value=dict(protocol=frozen['protocol'],source_revision=frozen['source_revision'],outcome=outcome,live=live,review=review,uncertainty_fences=fence,archive=pointer,scientific_completion=False,prompt_publications_changed=False)
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False);sha=r.sha(raw.encode());ids=[]
 for p in frozen['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(p['id'])+'::uuid',r.admin.literal(outcome),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Implementing Codex AI evaluator/reviewer; nonindependent exposed software development qualification, not human or held-out review')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(p['id'])+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha;ids.append(p['id'])
 result=dict(status=outcome,report_sha256=sha,prompt_ids=ids,archive=pointer);q.save(source/'evaluations-recorded.json',result);return result
def approve(source):
 assert json.loads((source/'evaluations-recorded.json').read_bytes())['status']=='passed'
 frozen=json.loads((source/'frozen.json').read_bytes());files=frozen['runtime_manifest']['files'];name='policies/autonomous-repair-release-v1.json'
 assert all(r.sha((BACK/'research_workflow'/n).read_bytes())==h for n,h in files.items())
 qualified=r.sha(json.dumps({n:h for n,h in files.items() if n!=name},sort_keys=True,separators=(',',':')).encode())
 value=dict(version='autonomous-repair-release-v1',approved_for_lab_recovery=True,qualified_files_sha256=qualified,evidence_sha256=json.loads((source/'evaluations-recorded.json').read_bytes())['archive']['sha256'])
 q.save(BACK/'research_workflow'/name,value);q.save(source/'approved-policy.json',value);return value
def migrate(source):
 assert json.loads((source/'evaluations-recorded.json').read_bytes())['status']=='passed';r.auth_maintenance_guard()
 name='202610280004_autonomous_repair.sql';raw=(ROOT/'database'/name).read_bytes();path='release-migrations/autonomous-repair-v1/'+r.sha(raw)+'-'+name;m.storage(path,raw);assert m.storage(path)==raw
 present=r.admin.query("select to_regclass('public.research_autonomy_repairs') is not null present")[0]['present']
 if not present:r.admin.query(raw.decode(),read_only=False)
 checks=r.admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT') anon_read,has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE') browser_write from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ('research_autonomy_repairs','research_autonomy_repair_events') order by c.relname")
 assert len(checks)==2 and all(c['relrowsecurity'] and not c['anon_read'] and not c['browser_write'] for c in checks)
 rpc=r.admin.query("select has_function_privilege('anon','public.research_autonomy_repair(text,uuid,uuid,uuid,jsonb)','EXECUTE') anon,has_function_privilege('authenticated','public.research_autonomy_repair_candidates()','EXECUTE') browser")
 assert rpc==[dict(anon=False,browser=False)]
 result=dict(status='passed',name=name,sha256=r.sha(raw),present_before=present,security=checks,rpc=rpc);q.save(source/'migration-applied.json',result);return result
def fences(source):
 code='''import json,sys,pathlib
from unittest.mock import patch
sys.path.insert(0,ROOT+'/research_workflow')
import autonomous_repair as repair,openclaw_runtime as runtime,store
dispatches=store.rows('model_dispatches',dict(status='eq.unknown',order='created_at.desc',limit=20))
checks=[]
with patch.object(runtime,'http_request',side_effect=AssertionError('No provider invocation is allowed by diagnosis')) as provider:
 for dispatch in dispatches:
  task=store.rows('autonomy_tasks',dict(id='eq.'+dispatch['task_id'],limit=1))[0]
  try:result=repair.diagnose(task,dict(category='runtime'))
  except ValueError as error:result=dict(waiting=True,reason='Original identity cannot yet be fully verified: '+str(error))
  checks.append(dict(task_id=task['id'],original_dispatch_id=dispatch['id'],diagnosis=result))
  if result.get('waiting'):break
 assert provider.call_count==0
result=dict(status='passed',provider_calls=0,assessment_writes=0,checks=checks,real_unconfirmed_outcome_present=any(c['diagnosis'].get('waiting') for c in checks),limitation=None if any(c['diagnosis'].get('waiting') for c in checks) else 'No genuinely unconfirmed provider identity remains in the bounded current database sample; synthetic uncertain-outcome regressions remain the negative control.')
(pathlib.Path(ROOT)/'fences.json').write_text(json.dumps(result))
print(json.dumps(dict(result,checks=[dict(task_id=c['task_id'],original_dispatch_id=c['original_dispatch_id'],waiting=c['diagnosis'].get('waiting'),reason=c['diagnosis'].get('reason'),reconciled_count=len(c['diagnosis'].get('reconciled_dispatches',[]))) for c in checks])))
'''.replace('ROOT',repr(q.host(source)))
 call=r.ssm(['set -eu','set -a','. /etc/jumpserve-openclaw.env','set +a','runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(code)]);q.save(source/'fences-command.json',call)
 for _ in range(12):
  time.sleep(2);value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
  if value['Status'] not in ('Pending','InProgress','Delayed'):break
 q.save(source/'fences-ssm.json',value);assert value['Status']=='Success'
 result=json.loads(value['StandardOutputContent']);assert result['status']=='passed' and result['provider_calls']==0;q.save(source/'fences-verified.json',result);return result
def verify(source,out,active):
 assert json.loads((source/'migration-applied.json').read_bytes())['status']=='passed'
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());functions=r.prior.functions(out,True)
 assert len(functions)==3 and all(len(f['source_hashes'])==len(manifest['files']) for f in functions)
 flags=[]
 for f in functions:
  env=r.aws('lambda','get-function-configuration','--function-name',f['function'])['Environment']['Variables']
  if f['handler'] in ('api.handler','autonomy.handler'):
   assert env['RESEARCH_AUTONOMY_ENABLED']==('true' if f['handler']=='autonomy.handler' else str(active).lower()) and env['RESEARCH_BUILDER_ENABLED']=='true' and env['RESEARCH_AI_RUNTIME']=='openclaw-production-v1'
   flags.append(dict(handler=f['handler'],repair=env.get('RESEARCH_AUTONOMY_REPAIR_ENABLED')=='true',builder=True,public_admission=active))
  if f['handler']=='autonomy.handler':assert f['timeout']==420 and env['RESEARCH_AUTONOMY_REPAIR_ENABLED']=='true'
 r.prior.PRIVATE|={'research_model_workers','research_model_dispatches','research_builder_calls','research_builder_packages','research_shared_campaigns','research_shared_campaign_members','research_paper_reviews','research_paper_review_events'}
 security=r.prior.security();call=q.verify_worker(source)
 for _ in range(12):
  time.sleep(2);invocation=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
  if invocation['Status'] not in ('Pending','InProgress','Delayed'):break
 q.save(out/'worker-ssm.json',invocation);assert invocation['Status']=='Success'
 health=r.admin.query("select status,configuration,updated_at from research_model_workers where id='openclaw-production-v1'")[0];assert health['status']=='ready'
 with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=30) as response:raw=response.read(2000000)
 cap=json.loads(raw);assert cap['autonomy']['enabled']==active and cap['autonomy']['defaults']['attempts_per_claim'] is None and cap['autonomy']['defaults']['maximum_spend_usd']==100
 assert cap['autonomy']['runtime']['runtime']=='openclaw-production-v1'
 resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries'];polls=[]
 for item in resources:
  if item['ResourceType']=='AWS::Events::Rule' and item['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll'):
   state=r.aws('events','describe-rule','--name',item['PhysicalResourceId'])['State'];assert state==('ENABLED' if active else 'DISABLED');polls.append(dict(logical_id=item['LogicalResourceId'],state=state))
 assert len(polls)==1 and r.instance()=='i-087f1493809643115'
 result=dict(status='passed',source_revision=manifest['source_revision'],runtime_files=len(manifest['files']),functions=functions,flags=flags,security=security,worker=call,worker_stdout_sha256=r.sha(invocation['StandardOutputContent'].encode()),health=health,capabilities_sha256=r.sha(raw),admission=active,polling=polls,auth_upload_chat_reverified=False)
 q.save(source/('active-verified.json' if active else 'held-verified.json'),result);return dict(status='passed',source_revision=manifest['source_revision'],runtime_files=len(manifest['files']),admission=active,worker=r.instance())
def record_release(source,out):
 active=json.loads((source/'active-verified.json').read_bytes());assert active['status']=='passed' and active['admission']
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert active['source_revision']==manifest['source_revision']
 front=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent/'jumpserve-front-end',text=True).strip()
 jobs=r.aws('amplify','list-jobs','--app-id','d24jvguj7brnkj','--branch-name','main','--max-results','10')['jobSummaries'];job=next(j for j in jobs if j['commitId']==front and j['status']=='SUCCEED')
 browser_path=sorted((ROOT/'.test-artifacts/autonomous-repair-production-browser').glob('*/report.json'))[-1];browser=json.loads(browser_path.read_bytes());assert browser['passed']
 qualification=json.loads((ROOT/'docs/autonomous-repair-qualification-v1.json').read_bytes())
 result=dict(version='autonomous-repair-production-v1',status='deployed-with-conditional-verification-gaps',recorded_at=r.stamp(),release_blocking_checks_passed=True,backend_revision=manifest['source_revision'],frontend_revision=front,runtime_files=len(manifest['files']),aws_account='395567831870',supabase_project='regphejnlvfpyokpniny',worker=r.instance(),worker_replaced=False,worker_storage_gib=300,encrypted=True,amplify_job=job['jobId'],qualification=qualification,production_checks=dict(active_source_security_flags='passed',browser=browser),scientific_coverage='Software qualification only; actual assessment findings are reported separately in its queue. No scientific conclusion follows from deployment.',conditional_gaps=browser['conditional_gaps'],measured_charges_usd=None,subscription_allocation_usd=None,unallocated_host_storage_cost_usd=None,legacy_ci='Broad all-stack/Bedrock and unrelated backend AMI workflows intentionally skipped; scoped checks and deployments used.')
 files={}
 for name in ('bin/autonomous-repair-release.py','bin/verify-autonomous-repair-production.mjs'):
  files[name]=(ROOT/name).read_bytes()
 result['producer_sha256']=r.sha(files['bin/autonomous-repair-release.py'])
 for directory in (source,browser_path.parent):
  for p in directory.iterdir():
   if p.is_file() and p.suffix in ('.json','.zip','.png'):files[str(p.relative_to(ROOT))]=p.read_bytes()
 for p in (ROOT/'.test-artifacts/openclaw-release').glob('*/receipt.json'):
  value=json.loads(p.read_bytes())
  if p.parent.name<'20261029T010746449274Z' or value.get('mode') not in ('hold','inspect','host-diff','host-deploy','diff','deploy','host-update','host-status','host-check','activate'):continue
  for item in p.parent.iterdir():
   if item.is_file() and item.name in ('receipt.json','cdk.log','outputs.json','stack-before.json','stack-after.json','parameter-comparison.json'):files[str(item.relative_to(ROOT))]=item.read_bytes()
 for name in ('research-workflow-runtime.json','database/202610280004_autonomous_repair.sql','docs/autonomous-repair-qualification-v1.json','docs/autonomous-repair-release.md'):
  files[name]=(ROOT/name).read_bytes()
 for name,sha in manifest['files'].items():
  raw=(BACK/'research_workflow'/name).read_bytes();assert r.sha(raw)==sha;files['runtime/research_workflow/'+name]=raw
 for p in BASE.glob('*/JumpServeBenchmarkStack*.zip'):files[str(p.relative_to(ROOT))]=p.read_bytes()
 for p in BASE.glob('*/worker-ssm.json'):files[str(p.relative_to(ROOT))]=p.read_bytes()
 old=ROOT/'.test-artifacts/autonomous-repair-local/20261029T010001267011Z/evidence.zip';assert r.sha(old.read_bytes())=='abfa36e381c69d2abc775de175e548090f4b1d01dd28da584d1bc2efc7d07330';files[str(old.relative_to(ROOT))]=old.read_bytes()
 with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/studies/'+STUDY+'/queue?public=1&diagnostics=1',timeout=30) as response:raw=response.read(2000000)
 queue=json.loads(raw);assert queue['study']['id']==STUDY;files['recorded-public-queue.json']=raw
 before=json.loads((source/'before-activation-queue.json').read_bytes());old=before['autonomy']['workflows'][0];now=queue['autonomy']['workflows'][0]
 assert all(old[k]==now[k] for k in ('study_id','max_spend_cents','max_attempts','created_at','deadline_at'))
 assert old['committed_cents']<=now['committed_cents']<=now['max_spend_cents']
 assert {(t['id'],t['claim_id']) for t in before['autonomy']['tasks']}=={(t['id'],t['claim_id']) for t in queue['autonomy']['tasks']}
 result['original_assessment_authorization']=dict(max_spend_cents=now['max_spend_cents'],deadline_at=now['deadline_at'],ai_turn_cap=now['max_attempts'],commitments_before=old['committed_cents'],commitments_observed=now['committed_cents'],original_task_and_claim_identities_retained=True)
 result['recorded_assessment_snapshot']=dict(id=STUDY,workflow=queue['autonomy']['workflows'],claim_states=[{k:t.get(k) for k in ('id','claim_id','stage','status','label','repair_progress')} for t in queue['autonomy']['tasks'] if t['claim_id']],jobs=queue['coverage']['jobs'],sha256=r.sha(raw),scope='Recorded bounded snapshot; autonomous work may advance after retrieval.')
 files['release-report.json']=json.dumps(result,sort_keys=True,separators=(',',':')).encode();buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for n,raw in sorted(files.items()):z.writestr(n,raw)
  z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())],sort_keys=True,separators=(',',':')))
 raw=buffer.getvalue();assert len(raw)<=20000000;path='release-verification/autonomous-repair-v1/'+r.sha(raw)+'.zip';m.storage(path,raw);restored=m.storage(path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as z:
  for row in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(row['path']))==row['sha256']
 (out/'release-evidence.zip').write_bytes(raw);pointer=dict(bucket='research-workflow-raw',path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),members=len(files),public=False);result['evidence']=pointer
 text=json.dumps(dict(kind='operational-release-verification',release=result,reviewer=dict(identity='Implementing Codex AI',type='AI',independent=False,human=False)),sort_keys=True,separators=(',',':'));sha=r.sha(text.encode())
 for ident in ('6117e5c5-84ce-5c31-aaa7-0d1d3522e62e','dfab5ecb-b8b9-5ad3-8771-f28a06b53b27'):
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(ident)+'::uuid',r.admin.literal('passed'),r.admin.literal(text),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Implementing Codex AI; nonindependent operational release verification with explicit conditional gaps, not scientific or human review')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(ident)+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha
 result['operational_evaluation_sha256']=sha;q.save(ROOT/'docs/autonomous-repair-production-v1-status.json',result);return dict(status=result['status'],amplify_job=job['jobId'],evidence=pointer,evaluation_sha256=sha)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','freeze-followup','freeze-validation','prepare','live','evidence','status','collect-status','collect','record-review','approve','migrate','verify-fences','verify-worker','verify-held','verify-active','record-release']);args=p.parse_args();BASE.mkdir(parents=True,exist_ok=True)
 out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir();receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:
  receipt['target']=r.target()
  if args.mode=='freeze':result=freeze(out)
  elif args.mode=='freeze-followup':result=freeze(out,q.selected())
  elif args.mode=='freeze-validation':result=freeze(out,q.selected(),True)
  elif args.mode=='verify-fences':result=fences(q.selected())
  elif args.mode in ('verify-held','verify-active'):result=verify(q.selected(),out,args.mode=='verify-active')
  elif args.mode=='record-release':result=record_release(q.selected(),out)
  elif args.mode in ('record-review','approve','migrate'):result=dict(record_review=record,approve=approve,migrate=migrate)[args.mode.replace('-','_')](q.selected())
  elif args.mode in ('status','collect-status','collect','verify-worker'):result=getattr(q,args.mode.replace('-','_'))(q.selected());result.pop('cases',None)
  else:result=q.dispatch(q.selected(),args.mode)
  receipt.update(status='complete',result=result)
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:q.save(out/'receipt.json',receipt);print(json.dumps(dict(directory=str(out),**receipt)))
if __name__=='__main__':main()
