"""Staged, bounded subscription qualification. No production task changes."""
import importlib.util,json,os,pathlib,sys,time,traceback
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'research_workflow'))
import autonomy_model as model,autonomy_methods,network_spec,openclaw_runtime as runtime
from workflow import canonical,digest,validate_protocol
spec=importlib.util.spec_from_file_location('base_qualification',ROOT/'base_qualification.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
packet=base.packet
def prepare():
 image=packet['image'];import subprocess
 result=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}} {{.Os}}/{{.Architecture}}'],text=True);assert result.strip()==image+' linux/amd64'
 modules=ROOT/'experiments/openclaw_pilot/runtime/node_modules';modules.mkdir(parents=True)
 for name,target in [('openclaw',runtime.PACKAGE),('node',runtime.NODE.parents[1])]: (modules/name).symlink_to(target,target_is_directory=True)
 path=ROOT/'.test-artifacts/builder-image';path.mkdir(parents=True)
 base.save(path/'continuation-v1.json',dict(status='passed',image=image,platform='linux/amd64',scope='Existing exact image inspected; no rebuild in this qualification.'))
 p=next(p for p in packet['prompts'] if p['module_id']=='research-experiment-builder');base.save(path/'published-prompt-v2.json',{k:p[k] for k in ('id','module_id','version','system_prompt','research_context','content_sha256')})
 base.save(ROOT/'prepared.json',dict(status='passed',image=image,platform='linux/amd64',existing_prepared_image=True))
def live():
 assert not (ROOT/'live.json').exists(),'Never replay a dispatched live campaign.'
 report=dict(protocol=packet['protocol']['version'],status='running',calls=0,cases=[],new_experiments=0,measured_charges_usd=None,subscription_allocation_usd=None);start=time.monotonic();base.save(ROOT/'live.json',report)
 def transport(method,url,token,body):
  assert report['calls']<packet['protocol']['resources']['maximum_real_provider_calls'] and time.monotonic()-start<900
  report['calls']+=1;event=dict(call=report['calls'],request_sha256=digest(body),bytes=len(body),at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat());base.save(ROOT/('admission-'+str(report['calls'])+'.json'),event);base.put('admission-'+str(report['calls'])+'.json',canonical(event));base.save(ROOT/'live.json',report)
  return runtime.http_request(method,url,token,body,timeout_seconds=65)
 try:
  runtime.verify_runtime()
  for case in packet['live_cases']:
   directory=ROOT/('live-'+case['id']);answer,receipt=runtime.execute(case['request'],directory,transport=transport)
   item=dict(id=case['id'],name=case['id'],status='failed-or-unreviewed',receipt=receipt,request_sha256=digest(canonical(case['request'])));report['cases'].append(item);base.save(ROOT/'live.json',report)
   assert receipt['status']=='complete','Inspect the preserved original provider/CLI outcome; no retry.'
   output=model.parse(answer);model.validate_phase(output,case['context']);item['output']=output
   if case['id']=='netem-observation-identities':
    assert output['action']=='propose' and output['assessment_label'] is None and output['ready'] is None and not output['evidence_ids']
    p=network_spec.bind_inputs(output['proposal']['protocol']);validate_protocol(p);autonomy_methods.validate(p,case['context']['claim'])
    expected=case['expected_protocol']
    for key in ('hypotheses','configurations','metrics','execution','planned_units','data_origin','input_versions'):assert p[key]==expected[key],key
    decision=p['decision'];groups={g['id']:g for g in decision['groups']};assert len(groups)==2 and len(decision['rules'])==1
    rule=decision['rules'][0];assert rule['operation']=='relative-percent-change' and [groups[k]['observation_ids'] for k in rule['groups']]==[['loss:0'],['loss:5']]
    assert str(rule['target'])=='35' and str(rule['tolerance_absolute'])=='1' and decision['coverage']=='complete-under-tested-conditions'
    assert all(g['metric']=='throughput_mbit_s' and g['units']=='Mbit/s' for g in groups.values())
   else:assert output['action']=='blocked' and any(b['kind']=='provider' for b in output['blockers']) and output['proposal'] is None and output['assessment_label'] is None and not output['evidence_ids']
   item.update(status='awaiting-substantive-review',structural_checks_passed=True);base.save(ROOT/'live.json',report)
  report['status']='awaiting-substantive-review'
 except Exception:report.update(status='failed-or-paused',failure=traceback.format_exc());raise
 finally:report['wall_seconds']=time.monotonic()-start;base.save(ROOT/'live.json',report)
if __name__=='__main__':
 action=sys.argv[1];assert action in ('prepare','native','live','evidence')
 try:({'prepare':prepare,'native':base.native,'live':live,'evidence':base.evidence}[action])()
 except Exception:base.save(ROOT/(action+'-failure.json'),dict(status='failed',traceback=traceback.format_exc()));raise
