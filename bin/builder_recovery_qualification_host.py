"""Pinned production-platform controls and bounded live recovery qualification."""
import copy,importlib.util,json,os,pathlib,subprocess,sys,time,traceback,uuid
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'research_workflow'))
import autonomy_model as model,autonomy_methods,experiment_builder as builder,generated_package,network_spec,openclaw_runtime as runtime,repair_validation,store
from workflow import canonical,digest,validate_protocol
spec=importlib.util.spec_from_file_location('qualification_base',ROOT/'base_qualification.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
packet=base.packet

def prepare():
 assert os.environ.get('OPENCLAW_BUILDER_IMAGE')==packet['image']
 assert subprocess.check_output(['docker','image','inspect',packet['image'],'--format','{{.Id}} {{.Os}}/{{.Architecture}}'],text=True).strip()==packet['image']+' linux/amd64'
 runtime.verify_runtime();runtime.catalog(runtime.credential());package=builder.builder_package()
 inventory=subprocess.check_output(['docker','run','--rm','--network','none',packet['image'],'cat','/jumpserve-image-packages.txt'],timeout=20)
 image_root=ROOT/'.test-artifacts/builder-image';image_root.mkdir(parents=True)
 base.save(image_root/'continuation-v1.json',dict(status='passed',image=packet['image'],platform='linux/amd64',package_inventory_sha256=digest(inventory)))
 prompt=next(p for p in packet['prompts'] if p['module_id']==builder.MODULE)
 base.save(image_root/'published-prompt-v2.json',prompt)
 modules=ROOT/'experiments/openclaw_pilot/runtime/node_modules';modules.mkdir(parents=True)
 for name,target in [('openclaw',runtime.PACKAGE),('node',runtime.NODE.parents[1])]:
  (modules/name).symlink_to(target,target_is_directory=True)
 checks=[]
 for name in ('test_dispatch_recovery.py','test_experiment_builder.py','test_autonomous_repair.py'):
  result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'research_workflow/tests'),'-p',name],capture_output=True,timeout=180)
  (ROOT/(name+'.stdout.bin')).write_bytes(result.stdout);(ROOT/(name+'.stderr.bin')).write_bytes(result.stderr)
  checks.append(dict(name=name,exit_code=result.returncode,stdout_sha256=digest(result.stdout),stderr_sha256=digest(result.stderr)))
  assert result.returncode==0,checks[-1]
 base.save(ROOT/'prepared.json',dict(status='passed',image=packet['image'],platform='linux/amd64',builder_package=str(package),checks=checks,package_inventory_sha256=digest(inventory),credential_contents_emitted=False))

def live():
 assert not (ROOT/'live.json').exists(),'Never replay a dispatched campaign'
 assert json.loads((ROOT/'prepared.json').read_bytes())['status']=='passed' and json.loads((ROOT/'native.json').read_bytes())['status']=='passed'
 limits=packet['protocol']['resources'];inherited=packet.get('inherited');current_max=packet['amendment']['resources']['maximum_additional_provider_calls'] if inherited else limits['maximum_actual_provider_calls'];began=time.monotonic();artifacts={};report=dict(status='running',actual_calls=0,live_provider_calls_issued=0,admissions=0,reserved_cents=0,cases=[],new_scientific_experiments=0,measured_charges_usd=None,subscription_allocation_usd=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False))
 if inherited:report.update(cases=copy.deepcopy(inherited['planner_results']),inherited_actual_calls=inherited['actual_calls'],inherited_reserved_cents=inherited['reserved_cents'],inherited_archive=inherited['archive'])
 def save():base.save(ROOT/'live.json',report)
 def retain(job,name,raw,kind='builder-original'):
  ident=str(uuid.uuid5(uuid.UUID(job['id']),name));artifacts[ident]=raw;p=ROOT/'live-originals'/job['id']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  pointer=base.put(job['id']+'-'+name,raw);base.save(p.with_suffix(p.suffix+'.pointer.json'),pointer)
  return dict(artifact_id=ident,sha256=digest(raw),version=builder.VERSION)
 def transport(method,url,token,body):
  assert report['actual_calls']<current_max and time.monotonic()-began<limits['maximum_elapsed_seconds']-65
  report['actual_calls']+=1;report['live_provider_calls_issued']=report['actual_calls'];base.save(ROOT/('transport-'+str(report['actual_calls'])+'.json'),dict(request_sha256=digest(body),bytes=len(body)));save()
  return runtime.http_request(method,url,token,body,timeout_seconds=65)
 native_start=None
 def admit(op,job,**payload):
  if op=='begin':
   if report['admissions']>=current_max or native_start is not None and report['actual_calls']-native_start>=limits['maximum_native_case_calls'] or time.monotonic()-began>limits['maximum_elapsed_seconds']-205:return dict(denied='qualification-envelope')
   report['admissions']+=1;report['reserved_cents']+=100;result=dict(id=str(uuid.uuid4()))
  else:result={}
  event=dict(operation=op,job=job,payload=payload,result=result)
  with (ROOT/'live-ledger.jsonl').open('ab') as sink:sink.write(canonical(event)+b'\n');sink.flush();os.fsync(sink.fileno())
  base.put('ledger-'+digest(canonical(event))+'.json',canonical(event));save();return result
 save()
 try:
  for case in ([] if inherited else packet['planner_cases']):
   assert report['admissions']<limits['maximum_actual_provider_calls'];report['admissions']+=1;report['reserved_cents']+=100;save()
   answer,receipt=runtime.execute(case['request'],ROOT/('live-'+case['id']),transport=transport)
   item=dict(name=case['id'],id=case['id'],receipt=receipt,structural_checks_passed=False);report['cases'].append(item);save()
   assert answer and receipt['status']=='complete','Original model outcome needs reconciliation; no retry'
   output=model.parse(answer);model.validate_phase(output,case['context']);item['output']=output
   if case['id']=='missing-reference-and-exact-contract':
    assert output['action']=='propose' and output['assessment_label'] is None and not output['evidence_ids']
    p=network_spec.bind_inputs(output['proposal']['protocol']);validate_protocol(p);autonomy_methods.validate(p,case['context']['claim'])
    for key in ('hypotheses','configurations','metrics','execution','input_versions','planned_units','data_origin'):assert p[key]==case['expected_protocol'][key],key
    decision=p['decision'];groups={g['id']:g for g in decision['groups']};rule=decision['rules'][0]
    assert len(groups)==2 and len(decision['rules'])==1 and rule['operation']=='relative-percent-change'
    assert [groups[k]['observation_ids'] for k in rule['groups']]==[['loss:0'],['loss:5']] and str(rule['target'])=='35' and str(rule['tolerance_absolute'])=='1'
    assert all(g['metric']=='throughput_mbit_s' and g['units']=='Mbit/s' for g in groups.values())
   else:assert output['action']=='blocked' and any(b['kind']=='provider' for b in output['blockers']) and output['proposal'] is None and output['assessment_label'] is None and not output['evidence_ids']
   item.update(status='awaiting-substantive-review',structural_checks_passed=True);save()
  for name in ('native-file-path-repair','empty-implementation'):
   context=copy.deepcopy(packet['native_context'] if name=='native-file-path-repair' else packet['empty_context']);job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','task_id','lease_token')}
   work=ROOT/'builder-workspaces'/job['task_id']/'workspace';project=work/'project';work.mkdir(parents=True)
   item=dict(name=name,id=name,status='running',receipts=[],controls=[],structural_checks_passed=False);report['cases'].append(item);save()
   def command():return ['docker','run','--rm','--network','none','--read-only','--pids-limit','64','--memory','256m','--cpus','0.5','--cap-drop','ALL','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(work)+',dst=/workspace','--workdir','/workspace/project','-e','PYTHONDONTWRITEBYTECODE=1','-e','JUMPSERVE_SPEC=/workspace/control-input.json','-e','JUMPSERVE_OUTPUT=/workspace/control-output.json',packet['image'],'python3','/workspace/project/experiment.py']
   if name=='native-file-path-repair' and inherited:
    original=packet['original_program'].encode();raw=(ROOT/'inherited-checkpoint.zip').read_bytes();assert digest(raw)==inherited['checkpoint']['sha256'];builder.restore(raw,work)
    assert (project/'original_experiment.py').read_bytes()==original and digest((work/'previous-failure.log').read_bytes())==inherited['failure_sha256']
    item['inherited_receipts']=inherited['native_receipts'];item['scope']='Reused original model-authored project; fresh corrected validator and executable controls, no replacement model call.'
   elif name=='native-file-path-repair':
    project.mkdir();original=packet['original_program'].encode()
    for filename,raw in {'experiment.py':original,'original_experiment.py':original,'requirements.lock':b'','system-packages.lock.json':b'[]','build-evidence.json':canonical(dict(commands=[],checks=[],limitations=['Software qualification only']))}.items():(project/filename).write_bytes(raw)
    (work/'control-input.json').write_bytes(canonical(dict(value=7)));failed=subprocess.run(command(),capture_output=True,timeout=20)
    assert failed.returncode!=0 and b'JSONDecodeError' in failed.stderr
    (work/'previous-failure.log').write_bytes(failed.stderr);retain(job,'original-failure-stderr.bin',failed.stderr)
    diagnosis=canonical(dict(version='autonomous-repair-v1',failure_details=[dict(original_log_excerpts=[dict(name='stderr.bin',excerpt=failed.stderr.decode(),sha256=digest(failed.stderr),excerpt_complete=True)])],scope='Actual software control failure, no paper observation'))
    pointer=context['repair_packet']['diagnosis'];artifacts[pointer['artifact_id']]=diagnosis;context['repair_packet']['diagnosis']=dict(artifact_id=pointer['artifact_id'],sha256=digest(diagnosis),byte_count=len(diagnosis))
   else:(work/'control-input.json').write_bytes(canonical(dict(value=7)))
   prompt=next(p for p in packet['prompts'] if p['module_id']==builder.MODULE);authority=builder.action_policy()
   logical=dict(modelId=runtime.MODEL,system=[dict(text=prompt['system_prompt']+'\n\n'+prompt['research_context']),dict(text=model.TURN_POLICY['instruction']),dict(text=authority['document']['instruction']),dict(text=autonomy_methods.INSTRUCTION)],builder=dict(version=builder.VERSION,context=context,checkpoint=None,execution_authority={k:authority[k] for k in ('version','sha256')}))
   start_calls=report['actual_calls'];native_start=start_calls
   try:
    with patch.object(builder,'retain',side_effect=retain),patch.object(builder,'rpc',side_effect=admit),patch.object(store,'artifact_bytes',side_effect=lambda study,ident,**kw:artifacts[ident]):
     if name=='native-file-path-repair' and inherited:item['validation']=repair_validation.validate(job,work,context,retain)
     while not (name=='native-file-path-repair' and inherited) and report['actual_calls']-start_calls<limits['maximum_native_case_calls'] and time.monotonic()-began<limits['maximum_elapsed_seconds']-205:
      _,receipt=builder.execute(logical,ROOT/('live-'+name+'-'+str(len(item['receipts'])+1)),job,transport=transport);item['receipts'].append(receipt);save()
      assert receipt['status']=='complete' and not receipt.get('admission_denied'),'Native outcome or envelope needs reconciliation; no replay'
      if name=='native-file-path-repair':
       assert (project/'original_experiment.py').read_bytes()==original and (work/'previous-failure.log').read_bytes()==failed.stderr
       try:item['validation']=repair_validation.validate(job,work,context,retain);break
       except ValueError as error:context['builder_feedback']='Continue this exact repair: '+str(error)+'. Use either supported fixed metadata location, preserve completed work and execute actual checks. Do not write candidate.json.'
      elif all((project/f).is_file() for f in ('experiment.py','requirements.lock','system-packages.lock.json','build-evidence.json')):break
      else:context['builder_feedback']='No complete implementation exists yet. Write the actual four project files and execute a bounded check next. Do not repeat completed inspection or write candidate.json.'
      logical['builder']['checkpoint']=receipt['checkpoint'];job=dict(job,id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
    if name=='native-file-path-repair':assert item.get('validation'),'No executed incident-bound validation within the qualification envelope'
    for value in ((7,0,None) if name=='native-file-path-repair' else (11,0,None)):
     raw=canonical(dict(value=value));(work/'control-input.json').write_bytes(raw)
     if (work/'control-output.json').exists():(work/'control-output.json').unlink()
     control=subprocess.run(command(),capture_output=True,timeout=20);retain(job,'control-'+str(value)+'-stdout.bin',control.stdout);retain(job,'control-'+str(value)+'-stderr.bin',control.stderr)
     assert control.returncode==0 and (work/'control-input.json').read_bytes()==raw
     actual=json.loads((work/'control-output.json').read_bytes());expected=dict(value=None if value is None else value*2,scope='software-development-only');assert actual==expected,(actual,expected)
     item['controls'].append(dict(input=value,actual=actual,expected=expected,output_sha256=digest((work/'control-output.json').read_bytes())));retain(job,'control-'+str(value)+'-output.json',(work/'control-output.json').read_bytes())
    frozen=generated_package.freeze(project);retain(job,'generated-project.zip',frozen);item.update(status='awaiting-substantive-review',structural_checks_passed=True,project_sha256=digest(frozen),scientific_finding=None);save()
   finally:builder.container_action(job['task_id'],'remove')
  report['status']='awaiting-substantive-review'
 except Exception:report.update(status='failed-or-paused',failure=traceback.format_exc());raise
 finally:report.update(wall_seconds=time.monotonic()-began);save()

if __name__=='__main__':
 phase=sys.argv[1];assert phase in ('prepare','native','live','evidence')
 try:dict(prepare=prepare,native=base.native,live=live,evidence=base.evidence)[phase]()
 except Exception:base.save(ROOT/(phase+'-failure.json'),dict(status='failed',traceback=traceback.format_exc()));raise
