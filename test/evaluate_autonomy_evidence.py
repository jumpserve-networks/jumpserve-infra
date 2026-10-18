"""One fixed live assessment of the complete, losslessly encoded control evidence."""
import datetime as dt,json,os,subprocess
import evaluate_autonomy as e
def main():
 root=e.ROOT;lock=json.loads((root/'test/autonomy-evidence-lock-v1.json').read_bytes());base=root/'.test-artifacts/autonomy-evidence';inputs=base/'inputs-v1.json';assert e.sha(inputs.read_bytes())==lock['inputs_sha256']
 for n,h in lock['files'].items():assert e.sha((e.BACKEND/n).read_bytes())==h
 assert not list(base.glob('*/evidence-report.json')),'Single evidence call already attempted'
 assert subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--query','Account','--output','text'],text=True).strip()=='395567831870'
 seed=json.loads((root/'database/seed-autonomy-v6.json').read_bytes());case=json.loads(inputs.read_bytes())['cases'][0];request=e.model.request(seed['system_prompt']+'\n\n'+seed['research_context'],case['model_context']);reserved=e.model.reservation(request);assert reserved<=200
 directory=base/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir();(directory/'inputs.json').write_bytes(inputs.read_bytes());(directory/'source-lock.json').write_bytes((root/'test/autonomy-evidence-lock-v1.json').read_bytes())
 for n in lock['files']:
  p=directory/'backend'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((e.BACKEND/n).read_bytes())
 raw=e.canonical(request);p=directory/(case['name']+'-request.json');p.write_bytes(raw)
 row=dict(name=case['name'],criterion=case['criterion'],status='running',passed=False,raw_answer_reviewed=False,rendered_answer_reviewed=False,usage=None,request_sha256=e.sha(raw))
 report=dict(protocol='autonomous-assessment-production-amendment-v10',prompt_version_id=seed['id'],model_id=e.model.MODEL,live_provider_calls=1,reserved_cents=reserved,input_sha256=lock['files'],inputs_sha256=lock['inputs_sha256'],cases=[row],measured_charges_usd=None,evaluator=dict(identity='Codex deterministic evidence evaluator',type='AI',independent=False),reviewer=dict(identity='Primary Codex AI implementer; pending inspection',type='AI',independent=False,passed=False),started_at=dt.datetime.now(dt.timezone.utc).isoformat())
 def save():(directory/'evidence-report.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  result=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region','us-east-1','--cli-input-json','file://'+str(p),'--cli-read-timeout','90','--cli-connect-timeout','5','--output','json'],capture_output=True,timeout=120,env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''});(directory/(case['name']+'-provider.json')).write_bytes(result.stdout);row['provider_response_sha256']=e.sha(result.stdout)
  if result.returncode:
   (directory/'provider-error.bin').write_bytes(result.stderr);raise RuntimeError('Provider failed; no retry')
  response=json.loads(result.stdout);message=e.canonical(response['output']['message']);(directory/(case['name']+'-message.json')).write_bytes(message);value=e.model.parse(response);(directory/(case['name']+'-rendered.json')).write_bytes(e.canonical(value))
  from autonomy import evidence_records
  records=evidence_records(case['model_context']['measurements']);known={r['id'] for r in records}|{r['id'] for r in case['model_context']['runs']}
  row.update(status='complete',output=value,output_sha256=e.sha(message),usage=response.get('usage'),estimated_cents=e.model.estimate(response.get('usage')),deterministic_checks=dict(schema=True,phase_assessment=value['action']=='assess',inconclusive_scope=value['assessment_label']=='inconclusive' and value['coverage_complete'] is False,actual_evidence_references=set(value['evidence_ids'])<=known,complete_packet=len(records)==192))
 except Exception as error:row.update(status='failed',reason=str(error))
 finally:report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();save();print(json.dumps(dict(directory=str(directory),status=row['status'],checks=row.get('deterministic_checks'))),flush=True)
if __name__=='__main__':main()
