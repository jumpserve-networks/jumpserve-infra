"""One fixed five-call provider-throttling recovery; not a general retry runner."""
import copy,datetime as dt,json,os,subprocess,time
from pathlib import Path
import evaluate_autonomy as e

def main():
 root=e.ROOT;base=root/'.test-artifacts/autonomy-evaluation';source=base/'20261018T191138801845Z'
 prior=json.loads((source/'evaluation-report.json').read_bytes())
 names=('partial-claim-coverage','no-result-forcing','source-omissions','budget-exhaustion','measured-evidence-only')
 assert subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--query','Account','--output','text'],text=True).strip()=='395567831870'
 assert prior['prompt_version_id']=='cc0c5299-e41d-588f-9d00-cf4d817bf72b' and prior['live_provider_calls']==14
 previous=[json.loads(p.read_bytes()) for p in base.glob('*/evaluation-report.json')]
 assert len(previous)==5 and sum(r['live_provider_calls'] for r in previous)==70
 assert not list(base.glob('*/recovery-report.json')),'Fixed recovery already attempted'
 lock=json.loads((root/'test/autonomy-implementation-lock-v5.json').read_bytes())
 for name,digest in lock['files'].items():assert e.sha((e.BACKEND/name).read_bytes())==digest
 assert e.sha(e.canonical(e.model.TOOLS))==lock['response_channel_sha256']
 cases=json.loads((root/'test/autonomy-evaluation-inputs-v1.json').read_bytes())['cases'];seed=json.loads((root/'database/seed-autonomy-v5.json').read_bytes())
 requests={c['name']:e.model.request(seed['system_prompt']+'\n\n'+seed['research_context'],c['model_context']) for c in cases}
 for row in prior['cases']:
  assert (source/(row['name']+'-request.json')).read_bytes()==e.canonical(requests[row['name']])
  if row['name'] in names:
   assert row['status']=='failed' and row.get('usage') is None and (source/(row['name']+'-provider.json')).read_bytes()==b''
   assert b'ThrottlingException' in (source/(row['name']+'-provider-error.bin')).read_bytes()
  else:assert row['status']=='complete' and all(row['deterministic_checks'].values())
 reserved=sum(e.model.reservation(requests[n]) for n in names)
 assert reserved<=500 and sum(r['reserved_cents'] for r in previous)+reserved<=3000
 directory=base/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir()
 report=copy.deepcopy(prior);report.update(release_amendment='autonomous-assessment-production-amendment-v6',recovery_source_report=str(source.relative_to(root)/'evaluation-report.json'),recovery_source_sha256=e.sha((source/'evaluation-report.json').read_bytes()),prior_live_provider_calls=14,prior_failed_provider_calls=5,new_provider_calls=0,reused_answer_count=9,live_provider_calls=14,reserved_cents=prior['reserved_cents']+reserved,recovery_reserved_cents=reserved,started_at=dt.datetime.now(dt.timezone.utc).isoformat())
 report['reviewer']=dict(identity='Primary Codex AI implementer; pending recovery inspection',type='AI',independent=False,passed=False)
 report['cases']=[]
 for row in prior['cases']:
  r=copy.deepcopy(row);r['answer_provenance']='new-provider-call' if row['name'] in names else 'reused-completed-answer';r['original_campaign']=str(source.relative_to(root))
  if row['name'] in names:
   r=dict(name=row['name'],criterion=row['criterion'],status='pending',passed=False,usage=None,raw_answer_reviewed=False,rendered_answer_reviewed=False,answer_provenance='new-provider-call',original_campaign=str(source.relative_to(root)))
  else:
   for suffix in ('-request.json','-provider.json','-message.json','-rendered.json'):(directory/(row['name']+suffix)).write_bytes((source/(row['name']+suffix)).read_bytes())
  report['cases'].append(r)
 (directory/'recovery-protocol.md').write_bytes((root/'docs/autonomous-assessment-production-amendment-v6.md').read_bytes())
 def save():(directory/'recovery-report.json').write_text(json.dumps(report,indent=2)+'\n')
 save();tick=time.monotonic()
 for case in cases:
  name=case['name']
  if name not in names:continue
  row=next(r for r in report['cases'] if r['name']==name)
  if time.monotonic()-tick>600:row.update(status='excluded',reason='Recovery wall limit');save();break
  time.sleep(15)
  raw=(source/(name+'-request.json')).read_bytes();path=directory/(name+'-request.json');path.write_bytes(raw);row['request_sha256']=e.sha(raw)
  started=time.monotonic()
  try:
   report['new_provider_calls']+=1;report['live_provider_calls']+=1;row['status']='running';save()
   result=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region','us-east-1','--cli-input-json','file://'+str(path),'--cli-connect-timeout','5','--cli-read-timeout','90','--output','json'],capture_output=True,timeout=120,env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''})
   (directory/(name+'-provider.json')).write_bytes(result.stdout);row['provider_response_sha256']=e.sha(result.stdout)
   if result.returncode:
    error=directory/(name+'-provider-error.bin');error.write_bytes(result.stderr);error.chmod(0o600);row['error_sha256']=e.sha(result.stderr);raise RuntimeError('Recovery provider failed; no further retries permitted')
   response=json.loads(result.stdout);row['usage']=response.get('usage');row['estimated_cents']=e.model.estimate(row['usage']);message=e.canonical(response['output']['message']);row['output_sha256']=e.sha(message);(directory/(name+'-message.json')).write_bytes(message)
   value=e.model.parse(response);row.update(output=value,deterministic_checks=e.check_answer(name,case['model_context'],value),status='complete');(directory/(name+'-rendered.json')).write_bytes(e.canonical(value))
  except Exception as error:row.update(status='failed',reason=str(error))
  finally:row['wall_seconds']=time.monotonic()-started;save();print(json.dumps(dict(case=name,status=row['status'],checks=row.get('deterministic_checks'))),flush=True)
 report.update(ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),estimated_cents=None,answered_call_estimate_cents=sum(r.get('estimated_cents') or 0 for r in report['cases']),failed_call_charges_usd=None);save();print(str(directory),flush=True)

if __name__=='__main__':main()
