"""Frozen repair release qualification; no production assessment mutations."""
import importlib.util,json,os,pathlib,subprocess,sys,time,threading,traceback,uuid
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'research_workflow'))
import autonomy_model as model,autonomy_methods,autonomous_repair,experiment_builder as builder,generated_package,network_spec,openclaw_runtime as runtime,repair_validation,store
from workflow import canonical,digest,validate_protocol
spec=importlib.util.spec_from_file_location('base_qualification',ROOT/'base_qualification.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
packet=base.packet

def prepare():
 assert subprocess.check_output(['docker','image','inspect',packet['image'],'--format','{{.Id}} {{.Os}}/{{.Architecture}}'],text=True).strip()==packet['image']+' linux/amd64'
 runtime.verify_runtime();runtime.catalog(runtime.credential())
 package=builder.builder_package()
 base.save(ROOT/'prepared.json',dict(status='passed',image=packet['image'],platform='linux/amd64',builder_package=str(package),production_image_inspected=True,credential_contents_emitted=False))

def live():
 assert not (ROOT/'live.json').exists(),'Never replay a dispatched live campaign.'
 prepared=json.loads((ROOT/'prepared.json').read_bytes());assert prepared['status']=='passed'
 limits=packet['protocol']['resources'];start=time.monotonic();lock=threading.RLock();artifacts={}
 report=dict(protocol=packet['protocol']['version'],status='running',actual_calls=0,admissions=0,reserved_cents=0,cases=[],new_scientific_experiments=0,measured_charges_usd=None,subscription_allocation_usd=None,reviewer=dict(identity='Implementing Codex assistant',type='AI',independent=False,human=False,held_out=False))
 if packet.get('inherited'):report.update(cases=packet['inherited']['planner_cases'],inherited_actual_calls=packet['inherited']['actual_calls'],inherited_reserved_cents=packet['inherited']['reserved_cents'],inherited_archive=packet['inherited']['archive'])
 def write():base.save(ROOT/'live.json',report)
 def retain(job,name,raw,kind='builder-original'):
  identity=str(uuid.uuid5(uuid.UUID(job['id']),name));path=ROOT/'live-originals'/job['id']/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
  pointer=base.put(job['id']+'-'+name,raw);artifacts[identity]=raw;base.save(path.with_suffix(path.suffix+'.pointer.json'),pointer)
  return dict(artifact_id=identity,sha256=digest(raw),version=builder.VERSION)
 def admit(operation,job,**payload):
  with lock:
   if operation=='begin':
    if report['admissions']>=limits['maximum_actual_provider_calls'] or time.monotonic()-start>=limits['maximum_elapsed_seconds']:return dict(denied='qualification-budget')
    report['admissions']+=1;report['reserved_cents']+=100;result=dict(id=str(uuid.uuid4()))
   else:result={}
   event=dict(operation=operation,job=job,payload=payload,result=result,at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
   with (ROOT/'live-ledger.jsonl').open('ab') as sink:sink.write(canonical(event)+b'\n');sink.flush();os.fsync(sink.fileno())
   base.put('ledger-'+digest(canonical(event))+'.json',canonical(event));write();return result
 def transport(method,url,token,body):
  with lock:
   assert report['actual_calls']<limits['maximum_actual_provider_calls'] and time.monotonic()-start<limits['maximum_elapsed_seconds']
   report['actual_calls']+=1;event=dict(number=report['actual_calls'],request_sha256=digest(body),bytes=len(body),at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
   base.save(ROOT/('transport-'+str(report['actual_calls'])+'.json'),event);write()
  return runtime.http_request(method,url,token,body,timeout_seconds=65)
 write();job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','task_id','lease_token')}
 try:
  runtime.verify_runtime();runtime.catalog(runtime.credential())
  for case in ([] if packet.get('inherited') else packet['planner_cases']):
   assert report['admissions']<limits['maximum_actual_provider_calls'];report['admissions']+=1;report['reserved_cents']+=100;write()
   answer,receipt=runtime.execute(case['request'],ROOT/('live-'+case['id']),transport=transport)
   item=dict(id=case['id'],name=case['id'],receipt=receipt,status='failed-or-unreviewed');report['cases'].append(item);write()
   assert answer is not None and receipt['status']=='complete','Original data-only transport needs reconciliation; no retry.'
   output=model.parse(answer);model.validate_phase(output,case['context']);item['output']=output
   if case['id']=='missing-reference-and-exact-contract':
    assert output['action']=='propose' and output['ready'] is None and output['assessment_label'] is None and not output['evidence_ids']
    p=network_spec.bind_inputs(output['proposal']['protocol']);validate_protocol(p);autonomy_methods.validate(p,case['context']['claim'])
    for key in ('hypotheses','configurations','metrics','execution','input_versions','planned_units','data_origin'):assert p[key]==case['expected_protocol'][key],key
    decision=p['decision'];groups={g['id']:g for g in decision['groups']};rule=decision['rules'][0]
    assert len(groups)==2 and len(decision['rules'])==1 and rule['operation']=='relative-percent-change'
    assert [groups[k]['observation_ids'] for k in rule['groups']]==[['loss:0'],['loss:5']] and str(rule['target'])=='35' and str(rule['tolerance_absolute'])=='1'
    assert all(g['metric']=='throughput_mbit_s' and g['units']=='Mbit/s' for g in groups.values())
   else:assert output['action']=='blocked' and any(b['kind']=='provider' for b in output['blockers']) and output['proposal'] is None and output['assessment_label'] is None and not output['evidence_ids']
   item.update(status='awaiting-substantive-review',structural_checks_passed=True);write()
  context=packet['native_context'];p=next(p for p in packet['prompts'] if p['module_id']==builder.MODULE);authority=builder.action_policy()
  logical=dict(modelId=runtime.MODEL,system=[dict(text=p['system_prompt']+'\n\n'+p['research_context']),dict(text=model.TURN_POLICY['instruction']),dict(text=authority['document']['instruction']),dict(text=autonomy_methods.INSTRUCTION)],builder=dict(version=builder.VERSION,context=context,checkpoint=None,execution_authority={k:authority[k] for k in ('version','sha256')}))
  work=ROOT/'builder-workspaces'/job['task_id']/'workspace';project=work/'project';project.mkdir(parents=True)
  original=packet['original_program'].encode()
  for name,raw in {'experiment.py':original,'original_experiment.py':original,'requirements.lock':b'','system-packages.lock.json':b'[]','build-evidence.json':canonical(dict(commands=[],checks=[],limitations=['Explicit software qualification fixture; no scientific execution.']))}.items():(project/name).write_bytes(raw)
  (work/'control-input.json').write_bytes(canonical(dict(value=7)))
  def command():return ['docker','run','--rm','--network','none','--read-only','--pids-limit','64','--memory','256m','--cpus','0.5','--cap-drop','ALL','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(work)+',dst=/workspace','--workdir','/workspace/project','-e','PYTHONDONTWRITEBYTECODE=1','-e','JUMPSERVE_SPEC=/workspace/control-input.json','-e','JUMPSERVE_OUTPUT=/workspace/control-output.json',packet['image'],'python3','/workspace/project/experiment.py']
  failed=subprocess.run(command(),capture_output=True,timeout=20);assert failed.returncode!=0 and b'JSONDecodeError' in failed.stderr
  (work/'previous-failure.log').write_bytes(failed.stderr);base.save(ROOT/'original-failure.json',dict(exit_code=failed.returncode,stdout_sha256=digest(failed.stdout),stderr_sha256=digest(failed.stderr),program_sha256=digest(original)))
  retain(job,'original-failure-stdout.bin',failed.stdout);retain(job,'original-failure-stderr.bin',failed.stderr)
  diagnosis=dict(version=autonomous_repair.VERSION,failure_details=[dict(dispatch_id='explicit-software-fixture',status='failed',original_log_excerpts=[dict(name='stderr.bin',excerpt=failed.stderr.decode(),excerpt_complete=True,sha256=digest(failed.stderr))])],scope='Explicit software file-path failure, no paper measurement or provider retry.')
  raw=canonical(diagnosis);pointer=context['repair_packet']['diagnosis'];artifacts[pointer['artifact_id']]=raw;assert pointer['sha256']==digest(raw) if pointer.get('sha256') else True
  # The source/inputs/criteria are frozen; actual stderr bytes are captured by
  # the predeclared original-failure control before any native provider call.
  context['repair_packet']['diagnosis']=dict(artifact_id=pointer['artifact_id'],sha256=digest(raw),byte_count=len(raw))
  if packet.get('inherited'):
   checkpoint=packet['inherited']['checkpoint'];artifacts[checkpoint['artifact_id']]=(ROOT/'inherited-checkpoint.zip').read_bytes();assert digest(artifacts[checkpoint['artifact_id']])==checkpoint['sha256'];logical['builder']['checkpoint']=checkpoint
  base.save(ROOT/'native-resolved-context.json',dict(context=context,diagnosis_sha256=digest(raw),derivation='Frozen failure-control command produced original stderr; hash-bound pointer resolved before first native admission.'))
  native=dict(id='native-file-path-repair',name='native-file-path-repair',status='pending',receipts=[]);report['cases'].append(native);write()
  with patch.object(builder,'retain',side_effect=retain),patch.object(builder,'rpc',side_effect=admit),patch.object(store,'artifact_bytes',side_effect=lambda study,ident,**kw:artifacts[ident]),patch.dict(os.environ,OPENCLAW_BUILDER_IMAGE=packet['image'],OPENCLAW_BUILDER_PACKAGE=prepared['builder_package']):
   if packet.get('validation_only'):
    assert limits['maximum_actual_provider_calls']==0
    builder.restore(artifacts[packet['inherited']['checkpoint']['artifact_id']],work)
    native['receipts']=packet['inherited']['native_receipts'];native['validation']=repair_validation.validate(job,work,context,retain)
    assert (project/'original_experiment.py').read_bytes()==original and (work/'previous-failure.log').read_bytes()==failed.stderr
   while report['admissions']<limits['maximum_actual_provider_calls'] and time.monotonic()-start<limits['maximum_elapsed_seconds']:
    _,receipt=builder.execute(logical,ROOT/('live-native-'+str(len(native['receipts'])+1)),job,transport=transport);native['receipts'].append(receipt);write()
    assert receipt['status']=='complete','Native call outcome needs reconciliation; no replay.'
    assert (project/'original_experiment.py').read_bytes()==original and (work/'previous-failure.log').read_bytes()==failed.stderr
    if all((project/name).exists() for name in ('repair_test.py','repair-test-plan.json')):
     try:
      validation=repair_validation.validate(job,work,context,retain);native['validation']=validation;break
     except ValueError as error:context['builder_feedback']=str(error)
    else:context['builder_feedback']='Continue the actual file-path repair and incident-bound unittest controls. Do not reread already delivered context. No candidate.json is needed for this software qualification.'
    logical['builder']['checkpoint']=receipt['checkpoint'];job=dict(job,id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
   assert native.get('validation'),'No accepted software repair within the declared call/time limits.'
  controls=[]
  for value in (7,0,None):
   raw=canonical(dict(value=value));(work/'control-input.json').write_bytes(raw)
   result=subprocess.run(command(),capture_output=True,timeout=20);retain(job,'control-'+str(value)+'-stdout.bin',result.stdout);retain(job,'control-'+str(value)+'-stderr.bin',result.stderr)
   assert result.returncode==0 and (work/'control-input.json').read_bytes()==raw
   actual=json.loads((work/'control-output.json').read_bytes());expected=dict(value=None if value is None else value*2,scope='software-development-only');assert actual==expected,(actual,expected)
   controls.append(dict(input=value,expected=expected,actual=actual,output_sha256=digest((work/'control-output.json').read_bytes())))
   retain(job,'control-'+str(value)+'-output.json',(work/'control-output.json').read_bytes())
  frozen=generated_package.freeze(project);retain(job,'repaired-project.zip',frozen)
  native.update(status='awaiting-substantive-review',structural_checks_passed=True,controls=controls,project_sha256=digest(frozen),original_failure_preserved=True,scientific_finding=None)
  report['status']='awaiting-substantive-review';write()
 except Exception:report.update(status='failed-or-paused',failure=traceback.format_exc());write();raise
 finally:report.update(wall_seconds=time.monotonic()-start,ended_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat());write();builder.container_action(job['task_id'],'remove')

if __name__=='__main__':
 phase=sys.argv[1];assert phase in ('prepare','live','evidence')
 try:dict(prepare=prepare,live=live,evidence=base.evidence)[phase]()
 except Exception:base.save(ROOT/(phase+'-failure.json'),dict(status='failed',traceback=traceback.format_exc()));raise
