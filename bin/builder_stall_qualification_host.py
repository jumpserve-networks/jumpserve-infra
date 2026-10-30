"""Frozen production-platform builder checks; no arbitrary experiment inputs."""
import copy,datetime as dt,importlib.util,json,os,pathlib,subprocess,sys,time,traceback,uuid
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'research_workflow'))
import experiment_builder as builder,generated_package,netem_iperf,openclaw_runtime as runtime,repair_validation,source_project,store
from workflow import canonical,digest
spec=importlib.util.spec_from_file_location('qualification_base',ROOT/'base_qualification.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
packet=base.packet

def prepare():
 assert os.environ.get('OPENCLAW_BUILDER_IMAGE')==packet['image']
 assert subprocess.check_output(['docker','image','inspect',packet['image'],'--format','{{.Id}} {{.Os}}/{{.Architecture}}'],text=True).strip()==packet['image']+' linux/amd64'
 runtime.verify_runtime();runtime.catalog(runtime.credential());package=builder.builder_package()
 inventory=subprocess.check_output(['docker','run','--rm','--network','none',packet['image'],'cat','/jumpserve-image-packages.txt'],timeout=20)
 path=ROOT/'.test-artifacts/builder-image';path.mkdir(parents=True)
 base.save(path/'continuation-v1.json',dict(status='passed',image=packet['image'],platform='linux/amd64',package_inventory_sha256=digest(inventory)))
 base.save(path/'published-prompt-v2.json',next(p for p in packet['prompts'] if p['module_id']==builder.MODULE))
 modules=ROOT/'experiments/openclaw_pilot/runtime/node_modules';modules.mkdir(parents=True)
 for name,target in [('openclaw',runtime.PACKAGE),('node',runtime.NODE.parents[1])]:(modules/name).symlink_to(target,target_is_directory=True)
 checks=[]
 for name in ('test_builder_work_packet.py','test_dispatch_recovery.py','test_experiment_builder.py','test_autonomous_repair.py'):
  c=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'research_workflow/tests'),'-p',name],capture_output=True,timeout=180)
  (ROOT/(name+'.stdout.bin')).write_bytes(c.stdout);(ROOT/(name+'.stderr.bin')).write_bytes(c.stderr)
  checks.append(dict(name=name,exit_code=c.returncode));assert c.returncode==0,checks[-1]
 base.save(ROOT/'prepared.json',dict(status='passed',image=packet['image'],platform='linux/amd64',checks=checks,builder_package=str(package),package_inventory_sha256=digest(inventory)))

def live():
 assert not (ROOT/'live.json').exists(),'Never replay a dispatched campaign'
 assert json.loads((ROOT/'prepared.json').read_bytes())['status']=='passed' and json.loads((ROOT/'native.json').read_bytes())['status']=='passed'
 limits=packet['protocol']['resources'];began=time.monotonic();artifacts={};report=dict(status='running',actual_calls=0,admissions=0,reserved_cents=0,cases=[],measured_charges_usd=None,subscription_allocation_usd=None,reviewer=packet['protocol']['reviewer'])
 inherited=packet.get('packaging_followup')
 if inherited:report.update(inherited_actual_calls=inherited['actual_calls'],inherited_reserved_cents=inherited['reserved_cents'],original_archive=inherited['archive'],scope='Validation-only packaging correction using unchanged completed model answers; zero additional inference allowed.')
 def save():base.save(ROOT/'live.json',report)
 def retain(job,name,raw,kind='builder-original'):
  ident=str(uuid.uuid5(uuid.UUID(job['id']),name));artifacts[ident]=raw;p=ROOT/'live-originals'/job['id']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  base.save(p.with_suffix(p.suffix+'.pointer.json'),base.put(job['id']+'-'+name,raw))
  return dict(artifact_id=ident,sha256=digest(raw),version=builder.VERSION)
 def transport(method,url,token,body):
  assert not inherited or inherited.get('additional_model_calls',0)>0,'Validation-only follow-up cannot invoke a model'
  assert report['actual_calls']<(inherited['additional_model_calls'] if inherited else limits['maximum_actual_provider_calls']) and time.monotonic()-began<limits['maximum_elapsed_seconds']-65
  report['actual_calls']+=1;base.save(ROOT/('transport-'+str(report['actual_calls'])+'.json'),dict(request_sha256=digest(body),bytes=len(body)));save()
  return runtime.http_request(method,url,token,body,timeout_seconds=65)
 case_start=0
 def admit(op,job,**payload):
  if op=='begin':
   if report['admissions']>=(inherited.get('additional_model_calls',0) if inherited else limits['maximum_actual_provider_calls']) or report['actual_calls']-case_start>=limits['maximum_native_case_calls'] or time.monotonic()-began>limits['maximum_elapsed_seconds']-205:return dict(denied='qualification-envelope')
   report['admissions']+=1;report['reserved_cents']+=100;result=dict(id=str(uuid.uuid4()))
  else:result={}
  event=dict(operation=op,job=job,payload=payload,result=result)
  with (ROOT/'live-ledger.jsonl').open('ab') as s:s.write(canonical(event)+b'\n');s.flush();os.fsync(s.fileno())
  base.put('ledger-'+digest(canonical(event))+'.json',canonical(event));save();return result
 save()
 try:
  for name in ('native-file-path-repair','retained-paper-implementation'):
   case_start=report['actual_calls'];context=copy.deepcopy(packet['native_context'] if name=='native-file-path-repair' else packet['paper_context']);job={k:str(uuid.uuid4()) for k in ('id','study_id','actor_id','task_id','lease_token')}
   work=ROOT/'builder-workspaces'/job['task_id']/'workspace';project=work/'project';work.mkdir(parents=True)
   item=dict(name=name,status='running',receipts=[],controls=[],structural_checks_passed=False);report['cases'].append(item);save()
   def command():return ['docker','run','--rm','--network','none','--read-only','--pids-limit','64','--memory','256m','--cpus','0.5','--cap-drop','ALL','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(work)+',dst=/workspace','--workdir','/workspace/project','-e','PYTHONDONTWRITEBYTECODE=1','-e','JUMPSERVE_SPEC=/workspace/control-input.json','-e','JUMPSERVE_OUTPUT=/workspace/control-output.json',packet['image'],'python3','/workspace/project/experiment.py']
   if inherited:
    ref=inherited['checkpoints'][name];raw=(ROOT/ref['file']).read_bytes();assert digest(raw)==ref['sha256'];builder.restore(raw,work)
    item['inherited_receipts']=inherited['cases'][name]['receipts'];item['original_checkpoint_sha256']=ref['sha256']
    original=packet['original_program'].encode()
    if name=='native-file-path-repair':
     assert (project/'original_experiment.py').read_bytes()==original
     item['validation']=repair_validation.validate(job,work,context,retain)
   elif name=='native-file-path-repair':
    project.mkdir();original=packet['original_program'].encode()
    for filename,raw in {'experiment.py':original,'original_experiment.py':original,'requirements.lock':b'','system-packages.lock.json':b'[]','build-evidence.json':canonical(dict(commands=[],checks=[],limitations=['Software qualification only']))}.items():(project/filename).write_bytes(raw)
    (work/'control-input.json').write_bytes(canonical(dict(value=7)));failed=subprocess.run(command(),capture_output=True,timeout=20);assert failed.returncode!=0 and b'JSONDecodeError' in failed.stderr
    (work/'previous-failure.log').write_bytes(failed.stderr);retain(job,'original-failure-stderr.bin',failed.stderr)
    diagnosis=canonical(dict(version='autonomous-repair-v1',failure_details=[dict(original_log_excerpts=[dict(name='stderr.bin',excerpt=failed.stderr.decode(),sha256=digest(failed.stderr),excerpt_complete=True)])],scope='Actual software control failure, no paper observation'))
    ref=context['repair_packet']['diagnosis'];artifacts[ref['artifact_id']]=diagnosis;context['repair_packet']['diagnosis']=dict(artifact_id=ref['artifact_id'],sha256=digest(diagnosis),byte_count=len(diagnosis))
   else:
    raw=(ROOT/'retained-paper-checkpoint.zip').read_bytes();assert digest(raw)==packet['paper_checkpoint_sha256'];builder.restore(raw,work)
    # The source checkpoint has no implementation. Retain its complete history;
    # this new qualification task supplies a separate, explicit software scope.
    assert not project.exists() or not list(project.glob('*.py'))
    (work/'control-input.json').write_bytes(canonical(dict(rows=[dict(loss_pct=0,trials=[71.2,72,72.8]),dict(loss_pct=5,trials=[96,97.2,98.4])],baseline_loss=0,comparison_loss=5)))
   prompt=next(p for p in packet['prompts'] if p['module_id']==builder.MODULE);authority=builder.action_policy()
   logical=dict(modelId=runtime.MODEL,system=[dict(text=prompt['system_prompt']+'\n\n'+prompt['research_context']),dict(text=context.get('qualification_instruction','')),dict(text=authority['document']['instruction'])],builder=dict(version=builder.VERSION,context=context,checkpoint=None,execution_authority={k:authority[k] for k in ('version','sha256')}))
   try:
    if inherited and inherited.get('metadata_repair') and name=='retained-paper-implementation':
     baseline={p.name:p.read_bytes() for p in project.iterdir() if p.is_file() and p.name in ('experiment.py','requirements.lock','system-packages.lock.json')};original_metadata=(project/'build-evidence.json').read_bytes();context['builder_feedback']=inherited['metadata_repair'];logical['system'].append(dict(text=inherited['metadata_repair']))
     with patch.object(builder,'retain',side_effect=retain),patch.object(builder,'rpc',side_effect=admit),patch.object(store,'artifact_bytes',side_effect=lambda study,ident,**kw:artifacts[ident]):
      _,receipt=builder.execute(logical,ROOT/'live-metadata-repair',job,transport=transport);item['receipts'].append(receipt);save()
     assert receipt['status']=='complete' and receipt.get('native_tool_cleanup') is True,'Every issued call and tool must complete; no uncertain retry'
     assert all((project/n).read_bytes()==raw for n,raw in baseline.items()),'Metadata repair cannot change the executable or dependencies'
     assert any(p.is_file() and p.name!='build-evidence.json' and p.read_bytes()==original_metadata for p in project.glob('*.json')),'Preserve the complete original metadata bytes in the project'
    with patch.object(builder,'retain',side_effect=retain),patch.object(builder,'rpc',side_effect=admit),patch.object(store,'artifact_bytes',side_effect=lambda study,ident,**kw:artifacts[ident]):
     while not inherited and report['actual_calls']-case_start<limits['maximum_native_case_calls'] and time.monotonic()-began<limits['maximum_elapsed_seconds']-205:
      _,receipt=builder.execute(logical,ROOT/('live-'+name+'-'+str(len(item['receipts'])+1)),job,transport=transport);item['receipts'].append(receipt);save()
      assert receipt['status']=='complete' and not receipt.get('admission_denied'),'Native outcome/envelope requires reconciliation; no replay'
      if name=='native-file-path-repair':
       assert (project/'original_experiment.py').read_bytes()==original and (work/'previous-failure.log').read_bytes()==failed.stderr
       try:item['validation']=repair_validation.validate(job,work,context,retain);break
       except ValueError as error:context['builder_feedback']='Continue the exact repair, retaining original bytes: '+str(error)+'. Write the required incident-bound tests/plan and execute them; do not create candidate.json.'
      elif all((project/f).is_file() for f in ('experiment.py','requirements.lock','system-packages.lock.json','build-evidence.json')):break
      else:context['builder_feedback']='The required package is still incomplete. Write and execute actual project files. Read work-packet.json and source page 3 only if still needed; avoid repeated metadata reads. No candidate.json or scientific verdict.'
      logical['builder']['checkpoint']=receipt['checkpoint'];job=dict(job,id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
    if name=='native-file-path-repair':assert item.get('validation'),'No completed incident-bound repair validation'
    controls=[(dict(value=x),dict(value=None if x is None else x*2,scope='software-development-only')) for x in (7,0,None)] if name=='native-file-path-repair' else [
     (dict(rows=[dict(loss_pct=0,trials=[71.2,72,72.8]),dict(loss_pct=5,trials=[96,97.2,98.4])],baseline_loss=0,comparison_loss=5),dict(means=[72.0,97.2],relative_change_pct=35.0,scope='archived-source-calculation')),
     (dict(rows=[dict(loss_pct=0,trials=[0,0,0]),dict(loss_pct=5,trials=[0,0,0])],baseline_loss=0,comparison_loss=5),dict(means=[0.0,0.0],relative_change_pct=None,scope='archived-source-calculation')),
     (dict(rows=[dict(loss_pct=0,trials=[10,None,20]),dict(loss_pct=5,trials=[20,30,40])],baseline_loss=0,comparison_loss=5),dict(means=[None,30.0],relative_change_pct=None,scope='archived-source-calculation')),
     (dict(rows=[dict(loss_pct=0,trials=[20,30,40]),dict(loss_pct=5,trials=[10,15,20])],baseline_loss=0,comparison_loss=5),dict(means=[30.0,15.0],relative_change_pct=-50.0,scope='archived-source-calculation'))]
    sealed=source_project.freeze(job,project,retain)
    if inherited:
     inputs=work/'portable-inputs';inputs.mkdir();(inputs/'project.zip').write_bytes(sealed);(work/'server-wrapper.py').write_bytes(pathlib.Path(generated_package.__file__).read_bytes())
    for index,(data,expected) in enumerate(controls):
     raw=canonical(data);(work/'control-input.json').write_bytes(raw)
     if (work/'control-output.json').exists():(work/'control-output.json').unlink()
     argv=command()
     if inherited:
      (work/('wrapper-case-'+str(index))).mkdir();argv=['docker','run','--rm','--network','none','--read-only','--pids-limit','64','--memory','256m','--cpus','0.5','--cap-drop','ALL','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(work)+',dst=/workspace','--workdir','/workspace/wrapper-case-'+str(index),'-e','PYTHONDONTWRITEBYTECODE=1','-e','JUMPSERVE_SPEC=/workspace/control-input.json','-e','JUMPSERVE_INPUTS=/workspace/portable-inputs','-e','JUMPSERVE_OUTPUT=/workspace/control-output.json',packet['image'],'python3','/workspace/server-wrapper.py']
     c=subprocess.run(argv,capture_output=True,timeout=20);retain(job,'control-'+str(index)+'-stdout.bin',c.stdout);retain(job,'control-'+str(index)+'-stderr.bin',c.stderr)
     assert c.returncode==0 and (work/'control-input.json').read_bytes()==raw
     actual=json.loads((work/'control-output.json').read_bytes())
     if name=='retained-paper-implementation' and actual.get('relative_change_pct') is not None:actual['relative_change_pct']=round(actual['relative_change_pct'],8)
     assert actual==expected,(actual,expected)
     item['controls'].append(dict(input=data,expected=expected,actual=actual));retain(job,'control-'+str(index)+'-output.json',(work/'control-output.json').read_bytes())
    frozen=source_project.freeze(job,project,retain);assert frozen==sealed;retain(job,'generated-project.zip',frozen);item.update(status='awaiting-substantive-review',structural_checks_passed=True,project_sha256=digest(frozen),scientific_finding=None,portable_wrapper_tested=bool(inherited));save()
   finally:builder.container_action(job['task_id'],'remove')
  config=dict(cca='cubic',loss_levels_pct=[0,1,2,5,10],rate_mbit=100,one_way_delay_ms=20,duration_seconds=30,queue_packets=1000,mtu=1500,socket_buffer_bytes=131072,seed=773,loss_seed=None,ping_count=3)
  item=dict(name='full-grid-netem',status='running',structural_checks_passed=False,replications=[],scope='New empirical software qualification on one existing worker; three repeated trials share the host, no cross-host inference.');report['cases'].append(item);save()
  assert netem_iperf.network_budget(config)==18760000000
  for replication in range(3):
   if inherited:assert dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(inherited['overall_deadline_at'])-dt.timedelta(seconds=500),'Original qualification elapsed envelope exhausted'
   path=ROOT/('netem-'+str(replication));path.mkdir();value=dict(runner=netem_iperf.VERSION,config=config,replication=replication,implementation_sha256=digest(pathlib.Path(netem_iperf.__file__).read_bytes()));base.save(path/'spec.json',value)
   code="import json;import netem_iperf;v=netem_iperf.run(json.load(open('/spec.json')));print(json.dumps(v))"
   started_at=dt.datetime.now(dt.timezone.utc).isoformat();c=subprocess.run(['docker','run','--rm','--privileged','--network','none','--cpus','2','--memory','512m','--pids-limit','256','--mount','type=bind,src='+str(path/'spec.json')+',dst=/spec.json,readonly','--mount','type=bind,src='+str(pathlib.Path(netem_iperf.__file__).parent)+',dst=/runner,readonly','-e','PYTHONPATH=/runner','-e','PYTHONDONTWRITEBYTECODE=1',packet['image'],'python3','-B','-c',code],capture_output=True,timeout=500);ended_at=dt.datetime.now(dt.timezone.utc).isoformat()
   (path/'stdout.bin').write_bytes(c.stdout);(path/'stderr.bin').write_bytes(c.stderr);assert c.returncode==0,c.stderr[-2000:]
   output=json.loads(c.stdout);base.save(path/'output.json',output);rows=output['observations']
   assert len(rows)==25 and {r['observation_key'] for r in rows}=={'loss:'+str(x) for x in config['loss_levels_pct']}
   assert not output['provenance'].get('failure')
   assert all(r['status']=='recorded' and r['value'] is not None for r in rows if r['metric']=='throughput_mbit_s'),(replication,rows)
   assert all((r['value'] is None and r['status']=='missing') or (r['value'] is not None and r['status']=='recorded') for r in rows)
   item['replications'].append(dict(replication=replication,started_at=started_at,ended_at=ended_at,observations=len(rows),sha256=digest(c.stdout),output=output));save()
  item.update(status='awaiting-substantive-review',structural_checks_passed=True);report['status']='awaiting-substantive-review'
 except Exception:report.update(status='failed-or-paused',failure=traceback.format_exc());raise
 finally:report['wall_seconds']=time.monotonic()-began;save()

if __name__=='__main__':
 phase=sys.argv[1];assert phase in ('prepare','native','live','evidence')
 try:dict(prepare=prepare,native=base.native,live=live,evidence=base.evidence)[phase]()
 except Exception:base.save(ROOT/(phase+'-failure.json'),dict(status='failed',traceback=traceback.format_exc()));raise
