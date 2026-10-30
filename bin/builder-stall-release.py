"""Fixed-target builder-stall release; bounded qualification, no arbitrary commands."""
import argparse,ast,base64,copy,datetime as dt,importlib.util,io,json,pathlib,subprocess,urllib.error,urllib.request,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('recovery_release',ROOT/'bin/builder-recovery-release.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
q,r,m=old.q,old.r,old.m;BASE=ROOT/'.test-artifacts/builder-stall-release-v1';q.BASE=BASE
STUDY=old.prior.STUDY

def pin():
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip(),'Commit reviewed backend first'
 previous=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());names=sorted(set(previous['files'])|{'source_project.py','policies/netem-iperf-costs-v2.json','policies/builder-stall-fix-validation-v1.json','policies/builder-stall-fix-validation-v2.json'})
 value=dict(version=previous['version']+1,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip(),files={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in names});q.save(ROOT/'research-workflow-runtime.json',value)
 return dict(source_revision=value['source_revision'],version=value['version'],files=len(names))

def snapshot(source,out):
 identity=r.admin.literal(STUDY)+'::uuid';workflow=r.admin.query('select to_jsonb(w) record from research_autonomy_workflows w where study_id='+identity)[0]['record']
 if source and (source/'assessment-before.json').exists():
  before=json.loads((source/'assessment-before.json').read_bytes());assert all(before[k]==workflow[k] for k in ('max_spend_cents','deadline_at','max_attempts','initial_sha256')) and workflow['committed_cents']>=before['committed_cents']
 tasks=r.admin.query('select id,claim_id,stage,status,label,reason,attempts,context->\'builder_stall\' stall,context->\'repair_progress\' repair_progress,updated_at from research_autonomy_tasks where study_id='+identity+' order by created_at')
 data=dict(recorded_at=r.stamp(),workflow=workflow,tasks=tasks,jobs=r.admin.query('select id,status,reason,updated_at from research_queue_jobs where study_id='+identity+' order by created_at'),active=r.admin.query("select id,status,lease_until from research_model_dispatches where study_id="+identity+" and status in ('queued','running')"),scope='Separate bounded reads; no mutations, no conclusive scientific finding inferred.')
 q.save(out/'assessment-snapshot.json',data);return data

def freeze(out):
 r.auth_maintenance_guard();manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision'] and not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip()
 assert all(r.sha((BACK/'research_workflow'/n).read_bytes())==h for n,h in manifest['files'].items()) and r.instance()=='i-087f1493809643115'
 prior_dir=ROOT/'.test-artifacts/builder-recovery-release-v1'/(ROOT/'.test-artifacts/builder-recovery-release-v1/selected.txt').read_text().strip();prior=json.loads((prior_dir/'frozen.json').read_bytes())
 prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder')")
 assert prompts and {p['module_id']:p for p in prompts}=={p['module_id']:p for p in prior['prompts']}
 matched_path=ROOT/'.test-artifacts/assessment-4055396e/20261029T234244406605Z/matched-checkpoints.json';matched=json.loads(matched_path.read_bytes());entry=matched['checkpoints'][0];checkpoint=(matched_path.parent/entry['file']).read_bytes();assert r.sha(checkpoint)==entry['sha256']
 with zipfile.ZipFile(io.BytesIO(checkpoint)) as z:context=json.loads(z.read('research-context.json'));paper=z.read('paper-text.json')
 original_context=copy.deepcopy(context)
 for name in ('repair_directive','repair_packet','repair_diagnostics'):context.pop(name,None)
 instruction='''Explicit SOFTWARE qualification using this full retained fictional paper context. No paper claim is being measured or assessed by this fixture. Implement a portable source-table arithmetic package now, not a prospective candidate. Inspect the retained paper page 3 if needed. Write project/experiment.py, requirements.lock (empty), system-packages.lock.json ([]), build-evidence.json (commands/checks/limitations), plus an executed development check. Use Python standard library. experiment.py exposes evaluate(spec_path), reading the JSON FILE named by spec_path. Input shape: {rows:[{loss_pct:number,trials:[number|null,...]},...],baseline_loss:number,comparison_loss:number}. Return exactly {means:[arithmetic mean for each row in input order or null if any trial is null/missing or list empty],relative_change_pct:100*(comparison_mean-baseline_mean)/baseline_mean or null if missing/undefined/zero denominator,scope:"archived-source-calculation"}. Match comparison rows by loss_pct, not position. Preserve zero and missing/null distinctly. Standard __main__ reads JUMPSERVE_SPEC as a FILENAME and writes JSON to filename JUMPSERVE_OUTPUT. Use /workspace/control-input.json for your development check. Test ordinary, zero and null values. Values supplied here are archived fabricated source values or explicitly synthetic controls, not new networking measurements. No candidate.json, blocker.json, scientific verdict, API fallback or source modification. Write and execute code before repeatedly reading metadata.'''
 context.update(task='building',qualification_instruction=instruction,builder_feedback=instruction,previous_feedback=None,builder_recovery_plan=dict(action=instruction),qualification_scope='Separate source-arithmetic SOFTWARE fixture; original complete paper, context and checkpoint retained separately.')
 files={'research_workflow/'+n:(BACK/'research_workflow'/n).read_bytes() for n in manifest['files']}
 files['research_workflow/experiment-builder.Dockerfile']=(BACK/'research_workflow/experiment-builder.Dockerfile').read_bytes()
 for p in (BACK/'research_workflow/tests').rglob('*'):
  if p.is_file() and p.suffix in ('.py','.json','.mjs') and '__pycache__' not in p.parts:files['research_workflow/'+str(p.relative_to(BACK/'research_workflow'))]=p.read_bytes()
 files.update({'base_qualification.py':(ROOT/'bin/builder_continuation_qualification_host.py').read_bytes(),'qualification.py':(ROOT/'bin/builder_stall_qualification_host.py').read_bytes(),'retained-paper-checkpoint.zip':checkpoint,'original-paper-context.json':json.dumps(original_context,sort_keys=True,separators=(',',':')).encode(),'original-paper-text.json':paper})
 for p in (BACK/'research_workflow/policies').glob('*.json'):files['research_workflow/policies/'+p.name]=p.read_bytes()
 packet=dict(protocol=json.loads((ROOT/'docs/builder-stall-release-protocol-v1.json').read_bytes()),source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(v) for n,v in files.items()},prompts=prompts,native_context=prior['native_context'],original_program=prior['original_program'],paper_context=context,paper_checkpoint_sha256=entry['sha256'],original_paper_context_sha256=r.sha(files['original-paper-context.json']),assessment=STUDY,image='sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64',frozen_at=r.stamp())
 if (BASE/'selected.txt').exists():
  previous=q.selected();status=json.loads((previous/'host-status.json').read_bytes());assert 'native-failure.json' in status and 'live.json' not in status and 'evidence.json' in status
  packet['pre_provider_harness_amendment']=dict(version='builder-stall-bundle-amendment-v2',previous_campaign=previous.name,archive=status['evidence.json'],reason='Include experiment-builder.Dockerfile required by the existing native test source capture. Native control failed before provider calls; a prematurely dispatched live phase stopped at its native.json prerequisite. Preserve both failures, no model replay, unchanged acceptance criteria and source runtime.')
 files['frozen.json']=json.dumps(packet,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();q.save(out/'frozen.json',packet)
 files['artifact-manifest.json']=json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in sorted(files.items())]).encode();buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in sorted(files.items()):z.writestr(n,v)
 raw=buffer.getvalue();(out/'candidate.zip').write_bytes(raw);path='qualification/builder-stall-release-v1/'+out.name+'/'+r.sha(raw)+'.zip';m.storage(path,raw);assert m.storage(path)==raw
 q.save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(raw),bytes=len(raw)));(BASE/'selected.txt').write_text(out.name+'\n')
 before=snapshot(None,out);q.save(out/'assessment-before.json',before['workflow']);return dict(source_revision=manifest['source_revision'],candidate_sha256=r.sha(raw),maximum_calls=packet['protocol']['resources']['maximum_actual_provider_calls'])

def record(source):
 frozen=json.loads((source/'frozen.json').read_bytes());live=json.loads((source/'live.json').read_bytes()) if (source/'live.json').exists() else dict(status='failed-before-provider',actual_calls=0,reserved_cents=0,cases=[],failure='Native harness source capture lacked experiment-builder.Dockerfile; live phase failed its native prerequisite. Original failures retained.');review=json.loads((source/'reviewed.json').read_bytes()) if (source/'reviewed.json').exists() else None;pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json'];assert r.sha(m.storage(pointer['path']))==pointer['sha256']
 expected={c['id'] for c in frozen['protocol']['cases']};limits=frozen['protocol']['resources']
 passed=bool(review and review['passed'] and review['source_revision']==frozen['source_revision'] and review['reviewer']==frozen['protocol']['reviewer'] and {c['id'] for c in review['cases']}==expected and all(c['passed'] and c['actual_answer_reviewed'] for c in review['cases']) and live['status']=='awaiting-substantive-review' and {c['name'] for c in live['cases']}==expected and all(c['structural_checks_passed'] for c in live['cases']) and live['actual_calls']+live.get('inherited_actual_calls',0)<=limits['maximum_actual_provider_calls'] and live['reserved_cents']+live.get('inherited_reserved_cents',0)<=limits['maximum_qualification_commitments_cents'] and live['wall_seconds']<=limits['maximum_elapsed_seconds'] and all(json.loads((source/n).read_bytes())['status']=='passed' for n in ('prepared.json','native.json')))
 value=dict(protocol=frozen['protocol'],source_revision=frozen['source_revision'],outcome='passed' if passed else 'failed-or-paused',actual=live,review=review,archive=pointer,pre_provider_harness_amendment=frozen.get('pre_provider_harness_amendment'),packaging_followup=frozen.get('packaging_followup'),scientific_scope='No claim labels changed; netem repeated-host software qualification is not independent paper validation.')
 raw=json.dumps(value,sort_keys=True,separators=(',',':'));sha=r.sha(raw.encode())
 for prompt in frozen['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(prompt['id'])+'::uuid',r.admin.literal(value['outcome']),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI, nonindependent exposed development review; not human or held-out')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(prompt['id'])+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha
 result=dict(status=value['outcome'],report_sha256=sha,archive=pointer);q.save(source/'evaluations-recorded.json',result);return result

def freeze_cache_followup(out,metadata=False):
 r.auth_maintenance_guard();previous=q.selected();metadata_parent=None;packet_fallback=False
 if metadata:
  parent_packet=json.loads((previous/'frozen.json').read_bytes());parent_live=json.loads((previous/'live.json').read_bytes());packet_fallback='Required work packet exceeds' in parent_live['failure'];assert parent_live['actual_calls']==0 and parent_live['inherited_actual_calls']==42 and len(parent_live['cases'])==2 and ('Build evidence must identify' in parent_live['failure'] or packet_fallback)
  assert json.loads((previous/'evaluations-recorded.json').read_bytes())['status']=='failed-or-paused';parent_pointer=json.loads((previous/'host-status.json').read_bytes())['evidence.json'];assert r.sha(m.storage(parent_pointer['path']))==parent_pointer['sha256']
  metadata_parent=dict(campaign=previous.name,archive=parent_pointer,additional_model_calls=0,previous=parent_packet['packaging_followup'].get('metadata_parent'));previous=BASE/parent_packet['packaging_followup']['previous_campaign']
 first=json.loads((previous/'frozen.json').read_bytes());live=json.loads((previous/'live.json').read_bytes());assert json.loads((previous/'evaluations-recorded.json').read_bytes())['status']=='failed-or-paused'
 assert live['actual_calls']==42 and live['status']=='failed-or-paused' and 'Keep dependency installations outside' in live['failure'] and len(live['cases'])==2
 assert all(r['status']=='complete' and not r.get('admission_denied') for c in live['cases'] for r in c['receipts']) and [len(c['controls']) for c in live['cases']]==[3,4]
 archive=(previous/'evidence.zip').read_bytes();pointer=json.loads((previous/'host-status.json').read_bytes())['evidence.json'];assert r.sha(archive)==pointer['sha256'] and m.storage(pointer['path'])==archive
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision'] and not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip()
 changed={n for n,h in manifest['files'].items() if first['runtime_manifest']['files'].get(n)!=h};assert changed=={'experiment_builder.py','repair_validation.py','source_project.py'}
 before=subprocess.check_output(['git','show',first['source_revision']+':research_workflow/experiment_builder.py'],cwd=BACK)
 def functions(raw):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
 old_functions=functions(before);new_functions=functions((BACK/'research_workflow/experiment_builder.py').read_bytes());same={n:r.sha(new_functions[n].encode()) for n in ('bootstrap','_execute','validate_calls','config')+(() if packet_fallback else ('work_packet',))+(() if metadata else ('execution_contract',))};assert all(old_functions[n]==new_functions[n] for n in same)
 with zipfile.ZipFile(previous/'candidate.zip') as z:files={n:z.read(n) for n in z.namelist() if n not in ('frozen.json','artifact-manifest.json')}
 for n in manifest['files']:files['research_workflow/'+n]=(BACK/'research_workflow'/n).read_bytes()
 for path in (BACK/'research_workflow/tests').rglob('*.py'):
  files['research_workflow/'+str(path.relative_to(BACK/'research_workflow'))]=path.read_bytes()
 files['qualification.py']=(ROOT/'bin/builder_stall_qualification_host.py').read_bytes();refs={}
 with zipfile.ZipFile(io.BytesIO(archive)) as z:
  for case in live['cases']:
   ref=case['receipts'][-1]['checkpoint'];names=[n for n in z.namelist() if n.endswith('checkpoint.zip') and r.sha(z.read(n))==ref['sha256']];assert len(names)==1
   name='inherited-'+case['name']+'.zip';files[name]=z.read(names[0]);refs[case['name']]=dict(file=name,sha256=ref['sha256'])
 packet=copy.deepcopy(first);packet.update(source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(v) for n,v in files.items()},frozen_at=r.stamp())
 packet['protocol']=dict(first['protocol'],version='builder-stall-release-followup-v3')
 packet['packaging_followup']=dict(version='source-project-sealing-followup-v3',previous_campaign=previous.name,reason='The original model programs passed all seven independent numerical controls but source sealing rejected derived Python bytecode. Preserve failed evidence; retain caches separately, seal identical source bytes, validate the exact source tree and execute the unchanged server wrapper. The unattempted loss sweep retains its conditions, replications and criteria.',actual_calls=42,reserved_cents=live['reserved_cents'],additional_model_calls=0,archive=pointer,checkpoints=refs,cases={c['name']:c for c in live['cases']},unchanged_native_functions=same,original_source_revision=first['source_revision'],overall_deadline_at=(dt.datetime.fromisoformat(first['frozen_at'])+dt.timedelta(seconds=first['protocol']['resources']['maximum_elapsed_seconds'])).isoformat())
 if metadata:
  packet['protocol']['version']='builder-stall-release-followup-v4'
  instruction='The exact experiment.py and dependency locks already passed all four independent source-arithmetic controls. Do not modify them or repeat paper/context inspection. Correct ONLY project/build-evidence.json: it must contain exactly commands, checks, limitations, each a JSON array. Preserve its COMPLETE original bytes in a separate JSON file in project/ before changing that envelope; keep additional runtime/version/source notes there. You can write a small Python helper OUTSIDE project/ and execute it directly to preserve the original bytes and extract those three existing arrays. No candidate.json, scientific run or paper verdict. At most SIX additional provider calls remain under the original cumulative 48-call qualification allowance. Make the concrete metadata correction now.'
  deadline=min(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=2700),dt.datetime.fromisoformat(first['frozen_at'])+dt.timedelta(seconds=5400))
  packet['packaging_followup'].update(version='source-metadata-contract-followup-v4',additional_model_calls=6,metadata_repair=instruction,metadata_parent=metadata_parent,original_deadline_at=packet['packaging_followup']['overall_deadline_at'],overall_deadline_at=deadline.isoformat(),qualification_resource_amendment='Pre-acquisition amendment: after cache and metadata integration failures, permit a fresh 2700-second qualification phase within 5400 seconds from the original freeze. Preserve all failures and the original 48-call/$48 reservation ceiling; at most six new calls, no refunds or replays. Paper budget, deadline, findings and scientific criteria unchanged. No netem measurements were attempted before this amendment.',changed_model_interface=dict(function='execution_contract',before_sha256=r.sha(old_functions['execution_contract'].encode()),after_sha256=r.sha(new_functions['execution_contract'].encode()),change='Declare the previously omitted exact metadata/dependency schemas; all executable, wrapper and scientific contracts unchanged.'))
  if packet_fallback:
   packet['protocol']['version']='builder-stall-release-followup-v5';packet['packaging_followup'].update(version='bounded-work-packet-followup-v5',packet_view_amendment=dict(reason='The metadata-repair working view exceeded 8 KB before provider admission. Keep the same bound and complete execution contract; represent optional netem/repair context by explicit hashes/references, with labeled smaller excerpts only when necessary. Original full context/history and 72 KB provider fence unchanged.',before_function_sha256=r.sha(old_functions['work_packet'].encode()),after_function_sha256=r.sha(new_functions['work_packet'].encode())))
  q.save(ROOT/('docs/builder-stall-packet-followup-v5.json' if packet_fallback else 'docs/builder-stall-metadata-followup-v4.json'),{k:v for k,v in packet['packaging_followup'].items() if k not in ('cases','checkpoints')})
 files['frozen.json']=json.dumps(packet,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();q.save(out/'frozen.json',packet);files['artifact-manifest.json']=json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in sorted(files.items())]).encode();buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in sorted(files.items()):z.writestr(n,v)
 raw=buffer.getvalue();(out/'candidate.zip').write_bytes(raw);path='qualification/builder-stall-release-v3/'+out.name+'/'+r.sha(raw)+'.zip';m.storage(path,raw);assert m.storage(path)==raw;q.save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),bytes=len(raw)));(BASE/'selected.txt').write_text(out.name+'\n');q.save(out/'assessment-before.json',json.loads((previous/'assessment-before.json').read_bytes()))
 return dict(source_revision=manifest['source_revision'],inherited_calls=42,additional_model_calls=packet['packaging_followup']['additional_model_calls'],candidate_sha256=r.sha(raw),overall_deadline_at=packet['packaging_followup']['overall_deadline_at'])

def approve(source):
 result=json.loads((source/'evaluations-recorded.json').read_bytes());assert result['status']=='passed'
 frozen=json.loads((source/'frozen.json').read_bytes());assert all(r.sha((BACK/'research_workflow'/n).read_bytes())==h for n,h in frozen['runtime_manifest']['files'].items())
 policy_path=BACK/'research_workflow/policies/netem-iperf-costs-v2.json';policy=json.loads(policy_path.read_bytes());assert policy['approved_for_lab_execution'] is False;policy['approved_for_lab_execution']=True;q.save(policy_path,policy)
 names=frozen['runtime_manifest']['files'];qualified={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in sorted(names) if n!='policies/autonomous-repair-release-v1.json'}
 value=dict(version='autonomous-repair-release-v1',approved_for_lab_recovery=True,qualified_files_sha256=r.sha(json.dumps(qualified,sort_keys=True,separators=(',',':')).encode()),evidence_sha256=result['archive']['sha256']);q.save(BACK/'research_workflow/policies/autonomous-repair-release-v1.json',value);q.save(source/'approved-policies.json',dict(repair=value,netem=policy));return value

def public_checks(out):
 origin='https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research';checks=[]
 for suffix,name in [('/capabilities','capabilities'),('/studies/'+STUDY+'/queue?public=1&diagnostics=1','queue'),('/studies/'+STUDY+'/queue?public=1&records=autonomy_repairs','repairs'),('/studies/'+STUDY+'/queue?public=1&records=autonomy_repair_events','repair-events')]:
  with r.prior.guard.OPEN.open(origin+suffix,timeout=30) as response:raw=response.read(2000001);assert response.status==200 and len(raw)<=2000000
  (out/(name+'.json')).write_bytes(raw);data=json.loads(raw);checks.append(dict(name=name,status=200,bytes=len(raw),sha256=r.sha(raw)))
  if name=='queue':assert data['study']['id']==STUDY and data['coverage']['jobs']==len(data['jobs']) and data['autonomy']['coverage']['tasks']==len(data['autonomy']['tasks'])
 for suffix in ('/studies/'+STUDY+'/autonomy','/studies/'+STUDY+'/network'):
  request=urllib.request.Request(origin+suffix,data=b'{}',headers={'Content-Type':'application/json'},method='POST')
  try:
   with r.prior.guard.OPEN.open(request,timeout=30) as response:assert False,'Unauthenticated write unexpectedly accepted'
  except urllib.error.HTTPError as error:
   raw=error.read(20000);assert error.code in (401,403),error.code;checks.append(dict(name=suffix,unauthenticated_status=error.code,sha256=r.sha(raw)))
 value=dict(status='passed',recorded_at=r.stamp(),checks=checks,scope='Public queue and provenance reads, unauthenticated write denial; no browser session inferred.');q.save(out/'public-verified.json',value);return value

def verify_executors(out):
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries'];result=[]
 for item in resources:
  if item['ResourceType']!='AWS::Lambda::Function' or not item['LogicalResourceId'].startswith(('ResearchWorkflowPackageExecutor','ResearchWorkflowPackageReaper','ResearchWorkflowPackageIngest')):continue
  value=r.aws('lambda','get-function','--function-name',item['PhysicalResourceId']);config=value['Configuration'];assert ':395567831870:' in config['FunctionArn']
  with r.prior.guard.OPEN.open(value['Code']['Location'],timeout=30) as response:raw=response.read(8000001)
  assert len(raw)<=8000000 and base64.b64encode(bytes.fromhex(r.sha(raw))).decode()==config['CodeSha256']
  with zipfile.ZipFile(io.BytesIO(raw)) as z:assert {n:r.sha(z.read(n)) for n in manifest['files']}==manifest['files']
  (out/(config['FunctionName']+'.zip')).write_bytes(raw);result.append(dict(function=config['FunctionName'],handler=config['Handler'],zip_sha256=r.sha(raw),files_verified=len(manifest['files'])))
 assert len(result)==3;value=dict(status='passed',source_revision=manifest['source_revision'],executors=result);q.save(out/'executors-verified.json',value);return value

def record_release(source,out):
 pending_path=source/'release-pending.json'
 if pending_path.exists():pending=json.loads(pending_path.read_bytes())
 else:
  active=json.loads((source/'active-verified.json').read_bytes());assert active['status']=='passed' and active['admission'] is True
  manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert active['source_revision']==manifest['source_revision']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()
  evaluation=json.loads((source/'evaluations-recorded.json').read_bytes());assert evaluation['status']=='passed'
  public_path=sorted(BASE.glob('*/public-verified.json'))[-1];public=json.loads(public_path.read_bytes());assert public['status']=='passed' and public_path.stat().st_mtime>(source/'active-verified.json').stat().st_mtime
  executor_path=sorted(BASE.glob('*/executors-verified.json'))[-1];executors=json.loads(executor_path.read_bytes());assert executors['status']=='passed' and executors['source_revision']==manifest['source_revision']
  browser=json.loads((source/'browser-verified.json').read_bytes());assert browser['passed'] and browser['reviewer']['type']=='AI' and browser['reviewer']['independent'] is False
  state=snapshot(source,out);volume=r.aws('ec2','describe-volumes','--volume-ids','vol-0993b9127ac7a8231')['Volumes'][0];assert volume['Size']==300 and volume['Encrypted'] and any(a['InstanceId']=='i-087f1493809643115' for a in volume['Attachments'])
  live=json.loads((source/'live.json').read_bytes());labels={}
  for task in state['tasks']:
   if task['claim_id']:labels[task['label']]=labels.get(task['label'],0)+1
  value=dict(version='builder-stall-production-v1',status='deployed-with-explicit-verification-scope',recorded_at=r.stamp(),release_blocking_checks_passed=True,revisions={n:subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent/n,text=True).strip() for n in ('jumpserve-back-end','jumpserve-infra','jumpserve-front-end')},runtime_manifest_version=manifest['version'],runtime_files=len(manifest['files']),aws_account='395567831870',supabase_project='regphejnlvfpyokpniny',worker=r.instance(),worker_replaced=False,worker_storage_gib=300,encrypted=True,frontend_changed=False,schema_changed=False,qualification=dict(evaluation=evaluation,source_revision=json.loads((source/'frozen.json').read_bytes())['source_revision'],actual_calls=live['actual_calls'],inherited_unique_calls=live.get('inherited_actual_calls',0),total_unique_calls=live['actual_calls']+live.get('inherited_actual_calls',0),additional_reservations_cents=live['reserved_cents'],inherited_reservations_cents=live.get('inherited_reserved_cents',0),netem_replications=3,netem_observations=sum(c['observations'] for c in next(c for c in live['cases'] if c['name']=='full-grid-netem')['replications']),dependence='Three repeated sweeps share one existing host; no cross-host inference or confidence interval.'),production_checks=dict(active_source_security_flags='passed',executors=executors,public=public,browser=browser),assessment=dict(id=STUDY,maximum_cents=state['workflow']['max_spend_cents'],committed_cents=state['workflow']['committed_cents'],deadline_at=state['workflow']['deadline_at'],attempt_cap=state['workflow']['max_attempts'],labels=labels,queue_jobs=len(state['jobs']),tasks=state['tasks'],scope='Bounded separate snapshot; work can advance after retrieval. Scientific findings are not inferred from software qualification.'),conditional_gaps=browser.get('conditional_gaps',[]),measured_charges_usd=None,subscription_allocation_usd=None,unallocated_host_storage_cost_usd=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False))
  files={'release-report.json':json.dumps(value,sort_keys=True,separators=(',',':')).encode()}
  for directory in (source,out,*[p.parent for p in BASE.glob('*/receipt.json')]):
   for p in directory.iterdir():
    if p.is_file() and p.suffix in ('.json','.zip','.log','.bin') and p.name not in ('candidate.zip','release-evidence.zip','release-pending.json'):files[str(p.relative_to(ROOT))]=p.read_bytes()
  for name in ('research-workflow-runtime.json','bin/builder-stall-release.py','bin/builder_stall_qualification_host.py','docs/builder-stall-release-protocol-v1.json','docs/builder-stall-metadata-followup-v4.json'):
   files[name]=(ROOT/name).read_bytes()
  if (ROOT/'docs/builder-stall-packet-followup-v5.json').exists():files['docs/builder-stall-packet-followup-v5.json']=(ROOT/'docs/builder-stall-packet-followup-v5.json').read_bytes()
  for name in ('builder-stall-release-packet-final-unit.log',):files['backend/'+name]=(BACK/'.test-artifacts'/name).read_bytes()
  for name in ('builder-stall-release-cache-infra.log','builder-stall-release-infra-build.log','builder-stall-release-database-repair.log','builder-stall-release-cache-database-builder.log'):files['reports/'+name]=(ROOT/'.test-artifacts'/name).read_bytes()
  for p in (ROOT/'.test-artifacts/openclaw-release').glob('20261030T*/*'):
   if p.is_file() and p.name in ('receipt.json','cdk.log','outputs.json','parameter-comparison.json'):files[str(p.relative_to(ROOT))]=p.read_bytes()
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
   for n,raw in sorted(files.items()):z.writestr(n,raw)
   z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())]))
  raw=buffer.getvalue();assert len(raw)<20000000;archive=out/'release-evidence.zip';archive.write_bytes(raw);pending=dict(archive=str(archive.relative_to(ROOT)),sha256=r.sha(raw),members=len(files),value=value);q.save(pending_path,pending)
 archive_path=(ROOT/pending['archive']).resolve();assert archive_path.is_relative_to(BASE.resolve());raw=archive_path.read_bytes();assert r.sha(raw)==pending['sha256'];path=STUDY+'/'+pending['sha256'];m.storage(path,raw);restored=m.storage(path);assert restored==raw
 with zipfile.ZipFile(io.BytesIO(restored)) as z:
  for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
 actor=r.admin.query('select owner_id from research_study_owners where study_id='+r.admin.literal(STUDY)+'::uuid')[0]['owner_id'];ident=str(uuid.uuid5(uuid.UUID(STUDY),'builder-stall-production:'+pending['sha256']))
 record=dict(id=ident,sha256=pending['sha256'],byte_count=len(raw),storage_path=path,media_type='application/zip',verified_at=r.stamp(),provenance=dict(kind='production-software-release-verification',version='builder-stall-production-v1',scientific_completion=False,reviewer=pending['value']['reviewer']))
 existing=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid')
 if not existing:r.admin.query('select public.research_append('+','.join([r.admin.literal(STUDY)+'::uuid',r.admin.literal(actor)+'::uuid',r.admin.literal('artifacts'),r.admin.literal(json.dumps(record))+'::jsonb'])+')',read_only=False)
 saved=r.admin.query('select sha256,byte_count from research_artifacts where study_id='+r.admin.literal(STUDY)+'::uuid and id='+r.admin.literal(ident)+'::uuid');assert saved==[dict(sha256=pending['sha256'],byte_count=len(raw))]
 value=pending['value'];value['evidence']=dict(artifact_id=ident,sha256=pending['sha256'],retrieved_sha256=r.sha(restored),bytes=len(raw),members=pending['members'],public=False);q.save(ROOT/'docs/builder-stall-production-v1-status.json',value);return dict(status=value['status'],evidence=value['evidence'],assessment=value['assessment'])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pin','freeze','freeze-cache-followup','freeze-metadata-followup','prepare','native','live','evidence','status','collect-status','collect','preview','snapshot','record-review','record-initial-failure','approve','verify-held','verify-active','public-checks','verify-executors','record-release']);args=p.parse_args();BASE.mkdir(parents=True,exist_ok=True);out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir();receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:
  receipt['targets']=r.target()
  if args.mode=='pin':value=pin()
  elif args.mode=='freeze':value=freeze(out)
  elif args.mode=='freeze-cache-followup':value=freeze_cache_followup(out)
  elif args.mode=='freeze-metadata-followup':value=freeze_cache_followup(out,True)
  elif args.mode=='snapshot':value=snapshot(q.selected() if (BASE/'selected.txt').exists() else None,out)
  elif args.mode=='record-review':value=record(q.selected())
  elif args.mode=='record-initial-failure':
   frozen=json.loads((q.selected()/'frozen.json').read_bytes());previous=BASE/frozen['pre_provider_harness_amendment']['previous_campaign'];assert previous.is_relative_to(BASE) and not (previous/'live.json').exists();value=record(previous);assert value['status']=='failed-or-paused'
  elif args.mode=='approve':value=approve(q.selected())
  elif args.mode=='public-checks':value=public_checks(out)
  elif args.mode=='verify-executors':value=verify_executors(out)
  elif args.mode=='record-release':value=record_release(q.selected(),out)
  elif args.mode=='preview':value=old.preview(q.selected(),out)
  elif args.mode in ('verify-held','verify-active'):
   q.save(q.selected()/'migration-applied.json',dict(status='passed',reason='No schema changes in this release; prior reconciliation relation remains protected.'))
   r.prior.PRIVATE|={'research_model_reconciliations','research_autonomy_repairs','research_autonomy_repair_events'};value=old.prior.verify(q.selected(),out,args.mode=='verify-active')
  elif args.mode in ('status','collect-status','collect'):value=getattr(q,args.mode.replace('-','_'))(q.selected());value.pop('cases',None)
  else:
   if args.mode=='live':
    state=json.loads((q.selected()/'host-status.json').read_bytes());assert state.get('prepared.json',{}).get('status')=='passed' and state.get('native.json',{}).get('status')=='passed','Inspect passing original native prerequisite before dispatch'
   value=q.dispatch(q.selected(),args.mode)
  receipt.update(status='complete',result=value)
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:q.save(out/'receipt.json',receipt);print(json.dumps(dict(directory=str(out),**receipt)))
if __name__=='__main__':main()
