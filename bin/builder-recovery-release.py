"""Fixed-target, versioned recovery qualification and scoped release operations."""
import argparse,copy,datetime as dt,importlib.util,io,json,pathlib,shlex,subprocess,sys,time,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('prior_repair',ROOT/'bin/autonomous-repair-release.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
q=prior.q;r=q.r;m=q.m;BASE=ROOT/'.test-artifacts/builder-recovery-release-v1';q.BASE=BASE;q.ASSESSMENT=prior.STUDY

def pin():
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip(),'Commit the reviewed backend first'
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());names=sorted(set(manifest['files'])|{'dispatch_recovery.py','policies/builder-recovery-validation-v3.json'})
 value=dict(version=manifest['version']+1,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip(),files={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in names})
 q.save(ROOT/'research-workflow-runtime.json',value)
 return dict(source_revision=value['source_revision'],files=len(names),version=value['version'])

def freeze(out,previous=None):
 r.auth_maintenance_guard();manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip() and subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision']
 assert r.instance()=='i-087f1493809643115' and all(r.sha((BACK/'research_workflow'/n).read_bytes())==h for n,h in manifest['files'].items())
 oldname=(ROOT/'.test-artifacts/autonomous-repair-release-v1/selected.txt').read_text().strip();old=json.loads((ROOT/'.test-artifacts/autonomous-repair-release-v1'/oldname/'frozen.json').read_bytes())
 prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder')")
 assert {p['module_id']:p for p in prompts}=={p['module_id']:p for p in old['prompts']},'Published prompt drift requires a new case review'
 context=copy.deepcopy(old['native_context']);context.pop('builder_feedback',None)
 empty=dict(task='building',claim=dict(description='Explicit software-only fixture: double a number read from a JSON spec file and preserve null. No networking or academic claim is being assessed.'),
  evaluation_case='Build a working versioned Python package from scratch in project/. Supply experiment.py, empty requirements.lock, system-packages.lock.json containing [], and build-evidence.json recording your actual checks and software-only limitations. Use standard library only. experiment.py must expose evaluate(spec_path), read the JSON file named by spec_path, and return exactly {value: double the input value or null, scope: software-development-only}. Its main reads the filename from JUMPSERVE_SPEC and writes JSON to the filename JUMPSERVE_OUTPUT. Check with the existing /workspace/control-input.json (value 7). Preserve missing/null and zero distinctly. Do not write candidate.json, execute a scientific campaign, alter limits, or claim a paper result. Write and execute the implementation rather than repeat read-only setup.',
  source_material=dict(origin='explicit-software-fixture',text='D(7)=14; D(0)=0; D(null)=null. Input and output paths are filenames; no measured paper data supplied.'),
  builder_feedback='There is no existing project implementation. Write project/experiment.py and its actual development check now, plus the three package metadata files. Inspect only missing essentials; no candidate.json is needed for this software qualification.',remaining_commitment_cents=1600,deadline_at='2026-11-04T20:25:04.587324Z')
 protocol=json.loads((ROOT/'docs/builder-recovery-release-protocol-v1.json').read_bytes())
 files={'research_workflow/'+n:(BACK/'research_workflow'/n).read_bytes() for n in manifest['files']}
 extras=['experiment-builder.Dockerfile','tests/check_experiment_builder_linux.py','tests/prepare_builder_image.py','tests/prepare_builder_vendor.py','tests/test_dispatch_recovery.py','tests/test_experiment_builder.py','tests/test_autonomous_repair.py','policies/builder-continuation-validation-v1.json','policies/builder-continuation-validation-v2.json']
 for n in extras:files['research_workflow/'+n]=(BACK/'research_workflow'/n).read_bytes()
 # Unit fixtures may inspect original non-active policies as negative controls.
 for path in (BACK/'research_workflow/policies').glob('*.json'):files['research_workflow/policies/'+path.name]=path.read_bytes()
 files['base_qualification.py']=(ROOT/'bin/builder_continuation_qualification_host.py').read_bytes();files['qualification.py']=(ROOT/'bin/builder_recovery_qualification_host.py').read_bytes()
 packet=dict(protocol=protocol,source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(v) for n,v in files.items()},prompts=prompts,planner_cases=old['planner_cases'],native_context=context,empty_context=empty,original_program=old['original_program'],assessment=prior.STUDY,image='sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64',frozen_at=r.stamp(),exposure='Exposed development cases, AI implementing reviewer; not independent, human or held-out validation')
 if previous:
  first=json.loads((previous/'frozen.json').read_bytes());live=json.loads((previous/'live.json').read_bytes());archive=json.loads((previous/'host-status.json').read_bytes())['evidence.json']
  assert json.loads((previous/'evaluations-recorded.json').read_bytes())['status']=='failed-or-paused' and live['status']=='failed-or-paused' and live['actual_calls']==18 and len(live['cases'])==3
  unchanged=('autonomy_model.py','autonomy_methods.py','openclaw_runtime.py','siwc_protocol.py','network_spec.py','autonomy_inputs.py')
  assert all(first['runtime_manifest']['files'][n]==manifest['files'][n] for n in unchanged) and {p['module_id']:p for p in first['prompts']}=={p['module_id']:p for p in prompts}
  assert all(c['structural_checks_passed'] for c in live['cases'][:2]) and all(v['status']=='complete' and v.get('native_tool_cleanup') is True and v['container_cleanup']=='stopped' for v in live['cases'][2]['receipts'])
  checkpoint=live['cases'][2]['receipts'][-1]['checkpoint']
  with zipfile.ZipFile(previous/'evidence.zip') as z:
   candidates=[n for n in z.namelist() if n.endswith('checkpoint.zip') and r.sha(z.read(n))==checkpoint['sha256']];assert len(candidates)==1
   raw=z.read(candidates[0]);files['inherited-checkpoint.zip']=raw;packet['source_files']['inherited-checkpoint.zip']=r.sha(raw)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:failure_sha=r.sha(z.read('previous-failure.log'))
  packet.update(protocol=dict(protocol,version='builder-recovery-release-followup-v2'),amendment=json.loads((ROOT/'docs/builder-recovery-release-amendment-v2.json').read_bytes()),followup_of=previous.name,
   inherited=dict(actual_calls=live['actual_calls'],reserved_cents=live['reserved_cents'],archive=archive,checkpoint=checkpoint,failure_sha256=failure_sha,planner_results=live['cases'][:2],native_receipts=live['cases'][2]['receipts'],unchanged_planner_files={n:manifest['files'][n] for n in unchanged}))
 files['frozen.json']=json.dumps(packet,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();q.save(out/'frozen.json',packet)
 files['artifact-manifest.json']=json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in sorted(files.items())]).encode()
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in sorted(files.items()):z.writestr(n,v)
 raw=stream.getvalue();(out/'candidate.zip').write_bytes(raw);path='qualification/builder-recovery-v1/'+out.name+'/'+r.sha(raw)+'.zip';m.storage(path,raw);assert m.storage(path)==raw
 q.save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(raw),bytes=len(raw)));(BASE/'selected.txt').write_text(out.name+'\n')
 original=r.admin.query("select to_jsonb(w) workflow from research_autonomy_workflows w where study_id='"+prior.STUDY+"'")[0]['workflow'];q.save(out/'assessment-before.json',original)
 return dict(source_revision=manifest['source_revision'],files=len(manifest['files']),maximum_provider_calls=protocol['resources']['maximum_actual_provider_calls'],candidate_sha256=r.sha(raw))

def record(source):
 frozen=json.loads((source/'frozen.json').read_bytes());live=json.loads((source/'live.json').read_bytes());review=json.loads((source/'reviewed.json').read_bytes()) if (source/'reviewed.json').exists() else None
 pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json'];assert r.sha(m.storage(pointer['path']))==pointer['sha256']
 expected={c['id'] for c in frozen['protocol']['cases']};limits=frozen['protocol']['resources']
 passed=bool(review and review['passed'] and review['reviewer']['type']=='AI' and review['reviewer']['independent'] is False and review['source_revision']==frozen['source_revision'] and len(review['cases'])==4 and {c['id'] for c in review['cases']}==expected and all(c['passed'] and c['actual_answer_reviewed'] and len(c['notes'])>=20 for c in review['cases']) and live['status']=='awaiting-substantive-review' and len(live['cases'])==4 and {c['name'] for c in live['cases']}==expected and all(c['structural_checks_passed'] for c in live['cases']) and live['actual_calls']+live.get('inherited_actual_calls',0)<=limits['maximum_actual_provider_calls'] and live['reserved_cents']+live.get('inherited_reserved_cents',0)<=limits['maximum_qualification_commitments_cents'] and live['wall_seconds']<=limits['maximum_elapsed_seconds'] and json.loads((source/'prepared.json').read_bytes())['status']=='passed' and json.loads((source/'native.json').read_bytes())['status']=='passed')
 outcome='passed' if passed else 'failed-or-paused';value=dict(protocol=frozen['protocol'],source_revision=frozen['source_revision'],outcome=outcome,live=live,review=review,archive=pointer,scientific_completion=False,prompt_publications_changed=False)
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False);sha=r.sha(raw.encode())
 for p in frozen['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(p['id'])+'::uuid',r.admin.literal(outcome),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI evaluator/reviewer; nonindependent exposed development qualification, not human or held-out')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(p['id'])+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha
 result=dict(status=outcome,report_sha256=sha,archive=pointer);q.save(source/'evaluations-recorded.json',result);return result

def migrate(source):
 assert json.loads((source/'evaluations-recorded.json').read_bytes())['status']=='passed';r.auth_maintenance_guard()
 name='202610290001_builder_reconciliation.sql';raw=(ROOT/'database'/name).read_bytes();path='release-migrations/builder-recovery-v1/'+r.sha(raw)+'-'+name;m.storage(path,raw);assert m.storage(path)==raw
 present=r.admin.query("select to_regclass('public.research_model_reconciliations') is not null present")[0]['present']
 if not present:r.admin.query(raw.decode(),read_only=False)
 security=r.admin.query("select relrowsecurity,has_table_privilege('anon',c.oid,'SELECT') anon_read,has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE') browser_write,has_table_privilege('service_role',c.oid,'INSERT,UPDATE,DELETE') direct_service_write from pg_class c where c.oid='public.research_model_reconciliations'::regclass")
 assert security==[dict(relrowsecurity=True,anon_read=False,browser_write=False,direct_service_write=False)]
 rpc=r.admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon,has_function_privilege('authenticated',p.oid,'EXECUTE') browser from pg_proc p where p.oid in ('public.research_model_reconcile(uuid,uuid,text,jsonb)'::regprocedure,'public.research_model_reconciliation_candidates(uuid)'::regprocedure)")
 assert len(rpc)==2 and all(not p['anon'] and not p['browser'] for p in rpc)
 result=dict(status='passed',name=name,sha256=r.sha(raw),present_before=present,security=security,rpc=rpc);q.save(source/'migration-applied.json',result);return result

def preview(source,out):
 code='''import hashlib,json,pathlib
root=pathlib.Path(QUALIFICATION_ROOT);report=json.loads((root/'live.json').read_bytes());projects=[]
for task in sorted((root/'builder-workspaces').iterdir()):
 if not task.is_dir() or task.is_symlink():continue
 files=[]
 for path in sorted((task/'workspace'/'project').glob('*')):
  if path.is_file() and not path.is_symlink():
   raw=path.read_bytes();files.append(dict(name=path.name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),text=raw[:3000].decode(errors='replace'),complete=len(raw)<=3000))
 history=task/'native-tool-history.json';recent=json.loads(history.read_bytes())[-8:] if history.exists() else []
 projects.append(dict(task=task.name,files=files,recent=[dict(type=x['type'],name=x.get('name'),call_id=x['call_id'],excerpt=json.dumps(x,ensure_ascii=False)[:700],complete=len(json.dumps(x,ensure_ascii=False))<=700) for x in recent]))
print(json.dumps(dict(status=report['status'],actual_calls=report['actual_calls'],cases=[dict(name=c['name'],status=c.get('status'),receipts=[dict(status=r['status'],provider_calls=r.get('provider_calls'),feedback=r.get('feedback')) for r in c.get('receipts',[])],output=c.get('output')) for c in report['cases']],failure=report.get('failure'),projects=projects)))
'''.replace('QUALIFICATION_ROOT',repr(q.host(source)))
 call=r.ssm(['/opt/jumpserve/python/bin/python -B -c '+shlex.quote(code)]);q.save(out/'command.json',call)
 for _ in range(30):
  value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
  if value['Status'] not in ('Pending','InProgress','Delayed'):break
  time.sleep(1)
 q.save(out/'ssm.json',value);assert value['Status']=='Success';data=json.loads(value['StandardOutputContent']);q.save(out/'preview.json',data);return data

def snapshot(source,out):
 """Fixed assessment read-only audit; never restart work or change limits."""
 identity=r.admin.literal(prior.STUDY)+'::uuid'
 workflow=r.admin.query('select to_jsonb(w) record from research_autonomy_workflows w where study_id='+identity)[0]['record']
 before=json.loads((source/'assessment-before.json').read_bytes())
 assert all(workflow[k]==before[k] for k in ('max_spend_cents','deadline_at','max_attempts','initial_sha256'))
 assert workflow['committed_cents']>=before['committed_cents'],'Historical commitments must not be reset'
 assert 0<=workflow['committed_cents']<=workflow['max_spend_cents'],'Observed commitments exceed the authorized ceiling'
 baseline=json.loads((ROOT/'.test-artifacts/assessment-4055396e/20261029T213731633407Z/snapshot.json').read_bytes())
 dispatches=r.admin.query('select id,status,request_sha256 from research_model_dispatches where study_id='+identity+' order by created_at')
 indexed={d['id']:d for d in dispatches}
 for row in baseline['model_dispatches']:
  old=row['record'];assert all(indexed[old['id']][k]==old[k] for k in ('status','request_sha256')),'Original parent outcome or request identity changed'
 tasks=r.admin.query('select id,claim_id,stage,status,label,reason,attempts,updated_at from research_autonomy_tasks where study_id='+identity+' order by created_at')
 reconciled=r.admin.query('select to_jsonb(r) record from research_model_reconciliations r where study_id='+identity+' order by created_at')
 proofs=[]
 for row in reconciled:
  record=row['record'];proof=record['proof'];assert proof['dispatch_id']==record['dispatch_id'] and proof['request_sha256']==indexed[record['dispatch_id']]['request_sha256'] and proof['original_status']==indexed[record['dispatch_id']]['status']
  for kind,ref in (('proof',dict(artifact_id=record['artifact_id'],sha256=record['sha256'])),('checkpoint',proof['checkpoint'])):
   a=r.admin.query('select storage_path,sha256,byte_count from research_artifacts where study_id='+identity+' and id='+r.admin.literal(ref['artifact_id'])+'::uuid')[0]
   raw=m.storage(a['storage_path']);assert r.sha(raw)==a['sha256']==ref['sha256'] and len(raw)==a['byte_count']
   (out/(record['dispatch_id']+'-'+kind+('.json' if kind=='proof' else '.zip'))).write_bytes(raw)
   if kind=='proof':assert json.loads(raw)==proof
  calls=r.admin.query('select id,status,request_sha256,response_sha256 from research_builder_calls where dispatch_id='+r.admin.literal(record['dispatch_id'])+'::uuid order by created_at')
  assert len(calls)==len(proof['calls']) and all(c['status']=='complete' for c in calls)
  assert {c['id']:(c['request_sha256'],c['response_sha256']) for c in calls}=={c['id']:(c['request_sha256'],c['response_sha256']) for c in proof['calls']}
  proofs.append(dict(dispatch_id=record['dispatch_id'],original_status=proof['original_status'],native_calls=len(calls),proof_sha256=record['sha256'],checkpoint_sha256=proof['checkpoint']['sha256']))
 jobs=r.admin.query('select status,count(*) count from research_queue_jobs where study_id='+identity+' group by status')
 result=dict(recorded_at=r.stamp(),assessment=prior.STUDY,workflow=workflow,tasks=tasks,original_parent_identities_preserved=True,original_parents_checked=len(baseline['model_dispatches']),reconciliations=proofs,dispatches=dispatches,jobs=jobs,scope='Bounded separate database reads; live work may advance during retrieval. Operational reconciliation is not scientific validation.')
 q.save(out/'assessment-snapshot.json',result);q.save(source/'latest-assessment-snapshot.json',dict(path=str(out/'assessment-snapshot.json'),sha256=r.sha((out/'assessment-snapshot.json').read_bytes())))
 return dict(assessment=prior.STUDY,limits_preserved=True,original_parents_checked=result['original_parents_checked'],reconciliations=proofs,committed_cents=workflow['committed_cents'],maximum_cents=workflow['max_spend_cents'],tasks=tasks,jobs=jobs)

def record_release(source,out):
 """Archive verified release bytes, keeping operational and scientific scope apart."""
 active=json.loads((source/'active-verified.json').read_bytes());assert active['status']=='passed' and active['admission']
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert active['source_revision']==manifest['source_revision']
 browser_path=sorted((ROOT/'.test-artifacts/autonomous-repair-production-browser').glob('*/report.json'))[-1]
 browser=json.loads(browser_path.read_bytes());assert browser['passed'] and browser['assessment']==prior.STUDY and browser_path.stat().st_mtime>(source/'active-verified.json').stat().st_mtime
 reference=json.loads((source/'latest-assessment-snapshot.json').read_bytes());snapshot_path=pathlib.Path(reference['path']);raw=snapshot_path.read_bytes();assert r.sha(raw)==reference['sha256']
 state=json.loads(raw);assert state['original_parent_identities_preserved']
 expected={'af717ce4-6790-5647-9623-e67b5f9c4eca','353bf8b5-55e4-5e5e-b0a2-c0ffa757d765','45176ed6-af9f-5d6e-99af-fa2174d9f774','dc5d5273-f29c-5e9a-aea6-dcc8d17c0985','8983af13-bebc-5def-bd84-8d5b521c2ece'}
 assert expected<={x['dispatch_id'] for x in state['reconciliations']},'Original blockers must have stored verified supplemental proofs'
 volume=r.aws('ec2','describe-volumes','--volume-ids','vol-0993b9127ac7a8231')['Volumes'][0]
 assert volume['Size']==300 and volume['Encrypted'] and any(a['InstanceId']=='i-087f1493809643115' for a in volume['Attachments']) and r.instance()=='i-087f1493809643115'
 revisions={name:subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent/name,text=True).strip() for name in ('jumpserve-back-end','jumpserve-infra','jumpserve-front-end')}
 assert revisions['jumpserve-back-end']==manifest['source_revision']
 value=dict(version='builder-recovery-production-v1',status='deployed-with-conditional-verification-gaps',recorded_at=r.stamp(),release_blocking_checks_passed=True,revisions=revisions,runtime_manifest_version=manifest['version'],runtime_files=len(manifest['files']),aws_account='395567831870',supabase_project='regphejnlvfpyokpniny',worker=r.instance(),worker_replaced=False,worker_storage_gib=300,encrypted=True,frontend_changed=False,qualification=json.loads((ROOT/'docs/builder-recovery-qualification-v1.json').read_bytes()),migration=json.loads((source/'migration-applied.json').read_bytes()),deployed_source_security_flags='passed',browser=browser,original_assessment_authorization={k:state['workflow'][k] for k in ('study_id','max_spend_cents','deadline_at','max_attempts','committed_cents')},original_parent_identities_preserved=True,reconciliations=state['reconciliations'],assessment_tasks=[{k:t[k] for k in ('id','claim_id','stage','status','label','attempts')} for t in state['tasks']],queue_jobs=state['jobs'],scientific_scope='Software release verification; no scientific verdict follows. Actual bounded assessment snapshot is reported separately and can change after retrieval.',conditional_gaps=browser['conditional_gaps'],measured_charges_usd=None,subscription_allocation_usd=None,unallocated_host_storage_cost_usd=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False))
 value['browser_harness_amendment']=json.loads((ROOT/'docs/builder-recovery-browser-amendment-v2.json').read_bytes())
 value['conditional_gaps'].append('Intermittent navigation delays exceeded the earlier 20-second harness limit. The final instrumented run passed with content ready in 7429 ms; the cause of earlier delays and general performance are unverified.')
 value['browser_runs']=[]
 files={}
 for directory in (source,snapshot_path.parent,browser_path.parent):
  for p in directory.iterdir():
   if p.is_file() and p.suffix in ('.json','.zip','.png'):files[str(p.relative_to(ROOT))]=p.read_bytes()
 for p in (ROOT/'.test-artifacts/openclaw-release').glob('*/receipt.json'):
  if p.parent.name<'20261029T214341538952Z':continue
  files[str(p.relative_to(ROOT))]=p.read_bytes()
  for name in ('cdk.log','outputs.json','parameter-comparison.json'):
   a=p.parent/name
   if a.exists():files[str(a.relative_to(ROOT))]=a.read_bytes()
 for p in BASE.glob('*/receipt.json'):
  if p.parent!=out:files[str(p.relative_to(ROOT))]=p.read_bytes()
 for p in (ROOT/'.test-artifacts/autonomous-repair-production-browser').glob('*/report.json'):
  if p.parent.name<'2026-10-29T22-42-00.666Z':continue
  report=json.loads(p.read_bytes());value['browser_runs'].append(dict(path=str(p.relative_to(ROOT)),sha256=r.sha(p.read_bytes()),passed=report['passed']))
  for a in p.parent.iterdir():
   if a.is_file() and a.suffix in ('.json','.png'):files[str(a.relative_to(ROOT))]=a.read_bytes()
 for name in ('bin/builder-recovery-release.py','bin/verify-autonomous-repair-production.mjs','docs/builder-recovery-release-protocol-v1.json','docs/builder-recovery-release-amendment-v2.json','docs/builder-recovery-browser-amendment-v2.json','database/202610290001_builder_reconciliation.sql','research-workflow-runtime.json'):files[name]=(ROOT/name).read_bytes()
 files['public-page.html']=(source/'public-page.html').read_bytes()
 for name in ('.test-artifacts/builder-recovery-v3-unit-validator-followup-final.log','.test-artifacts/repair-validation-linux/20261029T221234601819Z/report.json'):
  files['jumpserve-back-end/'+name]=(BACK/name).read_bytes()
 files['isolated-database-report.json']=(ROOT/'.test-artifacts/research-ideas/database/20261029T215305296218Z/report.json').read_bytes()
 files['release-report.json']=json.dumps(value,sort_keys=True,separators=(',',':')).encode();buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in sorted(files.items()):z.writestr(name,raw)
  z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())]))
 raw=buffer.getvalue();assert len(raw)<20000000;path='release-verification/builder-recovery-v1/'+r.sha(raw)+'.zip';m.storage(path,raw);restored=m.storage(path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as z:
  for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
 (out/'release-evidence.zip').write_bytes(raw);pointer=dict(bucket='research-workflow-raw',path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),members=len(files),public=False);value['evidence']=pointer
 report=json.dumps(dict(kind='operational-release-verification',release=value),sort_keys=True,separators=(',',':'));sha=r.sha(report.encode())
 for prompt in json.loads((source/'frozen.json').read_bytes())['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(prompt['id'])+'::uuid',r.admin.literal('passed'),r.admin.literal(report),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI; nonindependent operational verification, not human or scientific validation')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(prompt['id'])+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha
 value['operational_evaluation_sha256']=sha;q.save(ROOT/'docs/builder-recovery-production-v1-status.json',value)
 return dict(status=value['status'],evidence=pointer,evaluation_sha256=sha)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pin','freeze','freeze-followup','prepare','native','live','evidence','status','collect-status','collect','preview','snapshot','record-review','approve','migrate','verify-held','verify-active','record-release']);args=p.parse_args();BASE.mkdir(parents=True,exist_ok=True)
 out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir();receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:
  receipt['targets']=r.target()
  if args.mode=='pin':result=pin()
  elif args.mode=='freeze':result=freeze(out)
  elif args.mode=='freeze-followup':result=freeze(out,q.selected())
  elif args.mode=='record-review':result=record(q.selected())
  elif args.mode=='approve':result=prior.approve(q.selected())
  elif args.mode=='migrate':result=migrate(q.selected())
  elif args.mode=='preview':result=preview(q.selected(),out)
  elif args.mode=='snapshot':result=snapshot(q.selected(),out)
  elif args.mode=='record-release':result=record_release(q.selected(),out)
  elif args.mode in ('verify-held','verify-active'):
   r.prior.PRIVATE.add('research_model_reconciliations');result=prior.verify(q.selected(),out,args.mode=='verify-active')
  elif args.mode in ('status','collect-status','collect'):result=getattr(q,args.mode.replace('-','_'))(q.selected());result.pop('cases',None)
  else:result=q.dispatch(q.selected(),args.mode)
  receipt.update(status='complete',result=result)
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:q.save(out/'receipt.json',receipt);print(json.dumps(dict(directory=str(out),**receipt)))
if __name__=='__main__':main()
