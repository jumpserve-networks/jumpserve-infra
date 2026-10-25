"""Bounded grouping release evaluation. No production writes or deployment."""
import argparse,datetime as dt,importlib.util,json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('grouping_replay',ROOT/'bin/evaluate-paper-selection.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/paper-grouping-release-evaluation'
CASES=ROOT/'test/paper-grouping-release-cases-v2.json'

def freeze():
 original=json.loads((ROOT/'.test-artifacts/tcp88-selection/20261025T134858201414Z/frozen.json').read_bytes())
 cases=json.loads(CASES.read_bytes())
 directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,mode=0o700)
 packet=dict(version='paper-grouping-release-evaluation-v2',frozen_at=r.now(),classification=cases['classification'],
  cases=cases['cases'],candidates=original['candidates'],system=original['system'],system_sha256=original['system_sha256'],
  paper_sha256=original['input']['paper_sha256'],prompt_version_id=original['prompt_version_id'],
  policy=r.selection.POLICY,policy_sha256=r.digest(r.canonical(r.selection.POLICY)),
  implementation_sha256={n:r.digest((r.BACK/'research_workflow'/n).read_bytes()) for n in ('paper_selection.py','autonomy_model.py','openclaw_runtime.py','openclaw_auth.mjs','siwc_protocol.py','policies/paper-review-selection-policy-v2.json')},
  producer_sha256=r.digest(pathlib.Path(__file__).read_bytes()),cases_sha256=r.digest(CASES.read_bytes()),
  limits=dict(maximum_provider_calls=32,maximum_elapsed_seconds=1800,maximum_operational_retries=4,maximum_retries_per_request=1,paid_fallback=False,maximum_orchestration_reservation_cents=3200),
  criteria=['All six typed release cases pass source identity, phase and declared content checks.',
   'All 175 TCP88 candidates reach a completed batch; no truncation or omitted candidate is hidden.',
   'A final AI implementer review accepts qualifiers, units, category usefulness and bounded conclusions before release. Not independent or human review.'],
  stopping='Stop on semantic/structural failure. At most one unchanged-request retry for overload/temporary provider error, four total. Preserve failed calls.',
  uncertainty='Descriptive development checks; no inferential interval or general extraction accuracy is supported.')
 (directory/'frozen.json').write_bytes(r.canonical(packet));(directory/'evaluator.py').write_bytes(pathlib.Path(__file__).read_bytes());(BASE/'selected.txt').write_text(directory.name+'\n')
 print(json.dumps(dict(directory=str(directory),cases=len(packet['cases']),candidates=len(packet['candidates']),provider_calls=0)))

def content_checks(case,selected):
 items=[i for g in r.selection.GROUPS for i in selected[g]];labels={i['claim_id']:i['label'] for i in items};ids=set(labels);rows=case['candidates'];e=case['expected'];checks={}
 if e.get('empty'):checks['no_invented_contribution']=not ids
 checks['required_findings_retained']=all(rows[i]['id'] in ids for i in e.get('required_indices',[]))
 checks['instructions_not_selected']=all(rows[i]['id'] not in ids for i in e.get('forbidden_indices',[]))
 if 'equivalent_indices' in e:checks['semantic_duplicate_removed']=sum(rows[i]['id'] in ids for i in e['equivalent_indices'])==e['equivalent_selected']
 if 'unproved_index' in e:checks['unproved_qualified']=any(t in labels.get(rows[e['unproved_index']]['id'],'').lower() for t in ('unproved','unproven','conjectur','without proof','proof omitted','proof not','unproved argument'))
 if 'target_or_derived_index' in e:checks['target_not_reported_as_measurement']=any(t in labels.get(rows[e['target_or_derived_index']]['id'],'').lower() for t in ('target','derived','infer','impli','design'))
 for index,unit in e.get('units',{}).items():checks['unit_'+index]=unit in labels.get(rows[int(index)]['id'],'')
 for index,term in e.get('condition_terms',{}).items():checks['condition_'+index]=term in labels.get(rows[int(index)]['id'],'')
 return checks

def run():
 directory=BASE/(BASE/'selected.txt').read_text().strip();packet=json.loads((directory/'frozen.json').read_bytes());path=directory/'results.json'
 if path.exists():raise ValueError('Preserve the existing evaluation; freeze a new version for an amendment.')
 assert r.digest(pathlib.Path(__file__).read_bytes())==packet['producer_sha256']
 assert r.digest(CASES.read_bytes())==packet['cases_sha256']
 for n,sha in packet['implementation_sha256'].items():assert r.digest((r.BACK/'research_workflow'/n).read_bytes())==sha
 result=dict(version=packet['version'],started_at=r.now(),status='running',calls=[],cases=[],cursor=0,seen_ids=[],operational_retries=0,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),measured_charges_usd=None,subscription_allocation_usd=None)
 save=lambda:path.write_bytes(r.canonical(result));save();began=time.monotonic()
 def invoke(context,name):
  logical=r.model.request(packet['system'],context);attempt=0
  while True:
   if len(result['calls'])>=32 or time.monotonic()-began>1650:raise ValueError('Frozen evaluation resource limit reached.')
   item=dict(number=len(result['calls'])+1,name=name,request_sha256=r.digest(r.canonical(logical)),status='admitted');result['calls'].append(item);save()
   answer,receipt=r.runtime.execute(logical,directory/('call-'+str(item['number'])));item.update(status=receipt['status'],receipt=receipt);save()
   if answer:
    value=r.model.parse(answer);r.model.validate_phase(value,context)
    assert value['action']=='discover'
    allowed={c['id'] for c in context['candidates']}|{i['claim_id'] for g in r.selection.GROUPS for i in context['prior_shortlist'][g]}
    selected=r.selection.validate(value.get('paper_review_selection'),allowed)
    (directory/('call-'+str(item['number']))/'parsed.json').write_bytes(r.canonical(value));item['structural_passed']=True;save();return selected
   if receipt.get('error_code') not in ('server_is_overloaded','server_error','http-502','http-503') or attempt>=1 or result['operational_retries']>=4:raise ValueError('Provider failed outside the frozen operational-retry allowance.')
   attempt+=1;result['operational_retries']+=1;save();time.sleep(2)
 try:
  r.runtime.verify_runtime()
  for case in packet['cases']:
   context=r.selection.context(dict(title=case['title']),case['candidates'],0,{})
   selected=invoke(context,case['name']);checks=content_checks(case,selected);entry=dict(name=case['name'],checks=checks,selection=selected,passed=all(checks.values()));result['cases'].append(entry);save();print(json.dumps(dict(case=case['name'],passed=entry['passed'],checks=checks)),flush=True)
   if not entry['passed']:raise ValueError('Declared content criterion failed; preserve before amendment.')
  previous={}
  while result['cursor']<len(packet['candidates']):
   context=r.selection.context(dict(title='Congestion Avoidance and Control'),packet['candidates'],result['cursor'],previous)
   previous=invoke(context,'tcp88-'+str(result['cursor']));result['seen_ids'].extend(c['id'] for c in context['candidates']);result['cursor']+=len(context['candidates']);result['selection']=previous;save();print(json.dumps(dict(tcp88_processed=result['cursor'],central=len(previous['central_claims']),findings=len(previous['testable_findings']))),flush=True)
  assert result['seen_ids']==[c['id'] for c in packet['candidates']]
  assert previous['central_claims'] and previous['testable_findings']
  result['status']='awaiting-AI-implementer-review'
 except Exception as error:result.update(status='failed',reason=type(error).__name__+': '+str(error)[:400]);raise
 finally:result.update(ended_at=r.now(),wall_seconds=time.monotonic()-began);save();print(json.dumps(dict(directory=str(directory),status=result['status'],calls=len(result['calls']),processed=result['cursor'])))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['freeze','run']);args=parser.parse_args()
 freeze() if args.mode=='freeze' else run()
