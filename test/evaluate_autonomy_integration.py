"""Two fixed live context-builder integration calls; all earlier model results remain separate."""
import datetime as dt,json,os,subprocess,time
import evaluate_autonomy as e
def main():
 root=e.ROOT;lock=json.loads((root/'test/autonomy-integration-lock-v1.json').read_bytes());inputs=root/'test/autonomy-integration-inputs-v1.json';seed=json.loads((root/'database/seed-autonomy-v6.json').read_bytes());cases=json.loads(inputs.read_bytes())['cases']
 assert e.sha(inputs.read_bytes())==lock['integration_inputs_sha256'] and len(cases)==2
 for n,d in lock['files'].items():assert e.sha((e.BACKEND/n).read_bytes())==d
 assert subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--query','Account','--output','text'],text=True).strip()=='395567831870'
 base=root/'.test-artifacts/autonomy-integration';assert not list(base.glob('*/integration-report.json')),'Fixed integration already attempted'
 requests=[e.model.request(seed['system_prompt']+'\n\n'+seed['research_context'],c['model_context']) for c in cases];reserved=sum(e.model.reservation(r) for r in requests);assert reserved<=200
 directory=base/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
 report=dict(protocol='autonomous-assessment-production-amendment-v9',prompt_version_id=seed['id'],model_id=e.model.MODEL,live_provider_calls=0,reserved_cents=reserved,input_sha256=lock['files'],integration_inputs_sha256=lock['integration_inputs_sha256'],evaluator=dict(identity='Codex deterministic integration evaluator',type='AI',independent=False),reviewer=dict(identity='Primary Codex AI implementer; pending actual-answer inspection',type='AI',independent=False,passed=False),cases=[],measured_charges_usd=None,started_at=dt.datetime.now(dt.timezone.utc).isoformat())
 for n in ('test/autonomy-integration-inputs-v1.json','test/autonomy-integration-lock-v1.json','docs/autonomous-assessment-production-amendment-v9.md','test/evaluate_autonomy_integration.py'):
  p=directory/'inputs'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((root/n).read_bytes())
 for n in lock['files']:
  p=directory/'inputs/backend'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((e.BACKEND/n).read_bytes())
 def save():(directory/'integration-report.json').write_text(json.dumps(report,indent=2)+'\n')
 save();tick=time.monotonic()
 for case,request in zip(cases,requests):
  time.sleep(15);row=dict(name=case['name'],criterion=case['criterion'],status='running',passed=False,usage=None,raw_answer_reviewed=False,rendered_answer_reviewed=False);report['cases'].append(row);report['live_provider_calls']+=1;raw=e.canonical(request);p=directory/(case['name']+'-request.json');p.write_bytes(raw);row['request_sha256']=e.sha(raw);save()
  try:
   assert time.monotonic()-tick<=600
   result=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region','us-east-1','--cli-input-json','file://'+str(p),'--cli-read-timeout','90','--cli-connect-timeout','5','--output','json'],capture_output=True,timeout=120,env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''});(directory/(case['name']+'-provider.json')).write_bytes(result.stdout);row['provider_response_sha256']=e.sha(result.stdout)
   if result.returncode:
    (directory/(case['name']+'-error.bin')).write_bytes(result.stderr);raise RuntimeError('Integration provider failed; no retry')
   response=json.loads(result.stdout);message=e.canonical(response['output']['message']);(directory/(case['name']+'-message.json')).write_bytes(message);row.update(output_sha256=e.sha(message),usage=response.get('usage'),estimated_cents=e.model.estimate(response.get('usage')))
   value=e.model.parse(response);(directory/(case['name']+'-rendered.json')).write_bytes(e.canonical(value));checks=dict(schema=True,phase_action=value['action'] in e.model.phase_actions(case['model_context']['task']),no_new_proposal=value['proposal'] is None)
   if case['name']=='indexed-six-check-selection':checks['retained_identity']=value['action']=='choose-check' and value['check_id'] in {j['id'] for j in case['model_context']['registered_checks']}
   else:checks['explicit_review_or_external_blocker']=value['action']=='review' and isinstance(value['ready'],bool) or value['action']=='blocked' and bool(value['blockers']);checks['no_scientific_finding']=value['assessment_label'] is None
   row.update(status='complete',output=value,deterministic_checks=checks)
  except Exception as error:row.update(status='failed',reason=str(error))
  finally:save();print(json.dumps(dict(case=case['name'],status=row['status'],checks=row.get('deterministic_checks'))),flush=True)
 report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();save();print(str(directory),flush=True)
if __name__=='__main__':main()
